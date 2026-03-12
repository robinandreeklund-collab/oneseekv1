# Intent Layer Redesign — Full Implementation Plan

## Vision

Replace the current 4-route enum system (kunskap/skapande/konversation/jämförelse) with a **3-level DB-driven hierarchy**:

```
DOMÄNER (~15-20)          → AGENTER (~5-50 per domän)      → VERKTYG (~5-50 per agent)
väder-och-klimat          → smhi, yr_no, copernicus...     → smhi_forecast_hourly, smhi_warnings...
ekonomi-och-skatter       → skatteverket, riksbanken...    → skatt_inkomst, riksbank_ränta...
trafik-och-transport      → trafikverket, sl, voi...       → trafik_realtid, sl_avgångar...
```

At full scale: ~15 intents × ~20 agents × ~15 tools = **~4,500 tools**.

The LangGraph graph is **fully regenerated from DB** at session/worker start.

The Route enum is **kept as fallback** for backward compatibility.

---

## Phase 1: Database Schema (New Tables + Migrations)

### 1.1 New Table: `intent_domains`

Replaces `intent_definitions_global` as the primary intent store, adding domain hierarchy.

```python
class IntentDomain(BaseModel, TimestampMixin):
    __tablename__ = "intent_domains"

    domain_id = Column(String(80), nullable=False, unique=True, index=True)  # "väder-och-klimat"
    definition_payload = Column(JSONB, nullable=False, default={})
    # payload: {
    #   "domain_id": str,
    #   "label": str,                    # "Väder & Klimat"
    #   "description": str,              # Used for embedding + LLM selection
    #   "keywords": list[str],           # ["väder", "temperatur", "regn", "smhi", ...]
    #   "priority": int,                 # Lower = higher ranking bonus
    #   "enabled": bool,
    #   "fallback_route": str,           # "kunskap" — backward-compat Route enum value
    #   "citations_enabled": bool,
    #   "main_identifier": str,
    #   "core_activity": str,
    #   "unique_scope": str,
    #   "geographic_scope": str,
    #   "excludes": list[str],
    #   "complexity_override": str|null,  # Force trivial/simple/complex for this domain
    #   "execution_strategy_hint": str|null,  # "inline"/"parallel"/"subagent" hint
    # }
    sort_order = Column(Integer, nullable=False, default=500)
    updated_by_id = Column(UUID, ForeignKey("user.id"), nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), index=True)
```

### 1.2 New Table: `agent_definitions`

Replaces the hardcoded agent_definitions list in supervisor_agent.py.

```python
class AgentDefinition(BaseModel, TimestampMixin):
    __tablename__ = "agent_definitions"

    agent_id = Column(String(80), nullable=False, unique=True, index=True)  # "smhi"
    domain_id = Column(String(80), ForeignKey("intent_domains.domain_id"), nullable=False, index=True)
    definition_payload = Column(JSONB, nullable=False, default={})
    # payload: {
    #   "agent_id": str,
    #   "domain_id": str,
    #   "label": str,                       # "SMHI Väderdata"
    #   "description": str,                 # For retrieval + LLM
    #   "keywords": list[str],
    #   "priority": int,
    #   "enabled": bool,
    #   "prompt_key": str,                  # "smhi_prompt" — resolves to prompt text
    #   "prompt_text": str|null,            # Direct prompt override
    #   "primary_namespaces": list[list[str]],   # [["tools","weather","smhi"]]
    #   "fallback_namespaces": list[list[str]],
    #   "worker_config": {                  # Optional worker pool config
    #     "max_concurrency": int,
    #     "timeout_seconds": int,
    #   },
    #   "main_identifier": str,
    #   "core_activity": str,
    #   "unique_scope": str,
    #   "geographic_scope": str,
    #   "excludes": list[str],
    # }
    sort_order = Column(Integer, nullable=False, default=500)
    updated_by_id = Column(UUID, ForeignKey("user.id"), nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), index=True)
```

### 1.3 New Table: `tool_definitions`

Replaces hardcoded ROUTE_TOOL_SETS, TOOL_NAMESPACE_OVERRIDES, and _AGENT_TOOL_PROFILES.

```python
class ToolDefinition(BaseModel, TimestampMixin):
    __tablename__ = "tool_definitions"

    tool_id = Column(String(160), nullable=False, unique=True, index=True)  # "smhi_forecast_hourly"
    agent_id = Column(String(80), ForeignKey("agent_definitions.agent_id"), nullable=False, index=True)
    definition_payload = Column(JSONB, nullable=False, default={})
    # payload: {
    #   "tool_id": str,
    #   "agent_id": str,
    #   "label": str,
    #   "description": str,
    #   "keywords": list[str],
    #   "example_queries": list[str],
    #   "category": str,
    #   "enabled": bool,
    #   "priority": int,
    #   "namespace": list[str],           # ["tools", "weather", "smhi"]
    #   "main_identifier": str,
    #   "core_activity": str,
    #   "unique_scope": str,
    #   "geographic_scope": str,
    #   "excludes": list[str],
    #   "callable_path": str|null,        # "app.agents.new_chat.tools.smhi:forecast_hourly"
    # }
    sort_order = Column(Integer, nullable=False, default=500)
    updated_by_id = Column(UUID, ForeignKey("user.id"), nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), index=True)
```

### 1.4 History Tables

Add `intent_domain_history`, `agent_definition_history`, `tool_definition_history` following the existing pattern (previous_payload, new_payload, updated_by).

### 1.5 Keep Existing Tables

- `intent_definitions_global` — kept for backward compat, marked deprecated
- `tool_metadata_overrides_global` — kept, applies on top of tool_definitions
- `tool_retrieval_tuning_global` — kept as-is

### 1.6 Alembic Migration

Single migration that:
1. Creates the 3 new tables + 3 history tables
2. Seeds default domains from current `_DEFAULT_INTENT_DEFINITIONS`
3. Seeds default agents from current `agent_definitions` list in supervisor_agent.py
4. Seeds default tools from current `ROUTE_TOOL_SETS` + `_AGENT_TOOL_PROFILES`
5. Does NOT drop old tables

**Files to create/modify:**
- `surfsense_backend/app/db.py` — Add 6 new model classes
- `surfsense_backend/alembic/versions/xxx_intent_layer_redesign.py` — Migration

---

## Phase 2: Services Layer

### 2.1 `intent_domain_service.py` (NEW)

```python
# CRUD for IntentDomain table
async def get_all_intent_domains(session) -> list[dict]
async def get_intent_domain(session, domain_id) -> dict | None
async def upsert_intent_domain(session, domain_id, payload, user_id) -> dict
async def delete_intent_domain(session, domain_id, user_id) -> bool
async def get_effective_intent_domains(session) -> list[dict]  # Merged defaults + DB
```

### 2.2 `agent_definition_service.py` (NEW)

```python
# CRUD for AgentDefinition table
async def get_agents_for_domain(session, domain_id) -> list[dict]
async def get_all_agents(session) -> list[dict]
async def get_agent(session, agent_id) -> dict | None
async def upsert_agent(session, agent_id, payload, user_id) -> dict
async def delete_agent(session, agent_id, user_id) -> bool
async def get_effective_agents(session) -> dict[str, list[dict]]  # domain_id → agents
```

### 2.3 `tool_definition_service.py` (NEW)

```python
# CRUD for ToolDefinition table
async def get_tools_for_agent(session, agent_id) -> list[dict]
async def get_all_tools(session) -> list[dict]
async def upsert_tool(session, tool_id, payload, user_id) -> dict
async def delete_tool(session, tool_id, user_id) -> bool
async def get_effective_tools(session) -> dict[str, list[dict]]  # agent_id → tools
```

### 2.4 `graph_registry_service.py` (NEW)

Responsible for loading the complete hierarchy and building the graph config:

```python
@dataclass
class GraphRegistry:
    """Complete snapshot of all domains, agents, and tools for graph construction."""
    domains: list[dict]               # All enabled IntentDomains
    agents_by_domain: dict[str, list[dict]]  # domain_id → agent payloads
    tools_by_agent: dict[str, list[dict]]    # agent_id → tool payloads
    domain_index: dict[str, dict]     # domain_id → domain payload (fast lookup)
    agent_index: dict[str, dict]      # agent_id → agent payload
    tool_index: dict[str, dict]       # tool_id → tool payload
    route_fallback_map: dict[str, str]  # domain_id → Route enum value
    tuning: dict                      # Retrieval tuning config

async def load_graph_registry(session) -> GraphRegistry
```

**Files to create:**
- `surfsense_backend/app/services/intent_domain_service.py`
- `surfsense_backend/app/services/agent_definition_service.py`
- `surfsense_backend/app/services/tool_definition_service.py`
- `surfsense_backend/app/services/graph_registry_service.py`

---

## Phase 3: Intent Resolver Redesign

### 3.1 Modify `nodes/intent.py`

Replace the current intent resolver to work with domain-level intents:

```python
def build_intent_resolver_node(
    *,
    llm,
    graph_registry: GraphRegistry,
    ...
) -> Callable:
    """
    Phase 1: Resolve user query → domain(s).

    Flow:
    1. Rank all enabled domains via hybrid lexical+embedding scoring
    2. Shortlist top K (from tuning: intent_candidate_top_k)
    3. If live routing enabled, LLM selects from shortlist
    4. Output: resolved_intent = {
         "domain_id": str,
         "route": str,          # fallback_route from domain
         "confidence": float,
         "reason": str,
         "sub_intents": list[str],  # For multi-domain queries
       }
    """
```

Key changes:
- Candidates come from `graph_registry.domains` instead of hardcoded `_DEFAULT_INTENT_DEFINITIONS`
- Scoring uses same hybrid lexical+embedding approach but against domain metadata
- Route is derived from domain's `fallback_route` for backward compat
- Multi-domain detection: if confidence margin < threshold, include top-2 as sub_intents

### 3.2 Modify `intent_router.py`

Update `resolve_route_from_intents()` to:
- Accept domain definitions instead of flat intent definitions
- Score against domain keywords/descriptions
- Return domain_id in addition to route

### 3.3 Modify `dispatcher.py`

Update `dispatch_route_with_trace()` to:
- Load domains from `graph_registry` instead of intent definitions
- Rule-based routing still works (greeting → konversation, /compare → jämförelse)
- Intent retrieval uses domains as candidates
- Return `domain_id` in trace metadata

---

## Phase 4: Agent Resolver Redesign

### 4.1 Modify `nodes/agent_resolver.py`

Update to resolve agents **within the selected domain(s)**:

```python
def build_agent_resolver_node(
    *,
    llm,
    graph_registry: GraphRegistry,
    ...
) -> Callable:
    """
    Phase 2a: Given domain(s), select agent(s).

    Flow:
    1. Get agents for resolved domain(s) from graph_registry.agents_by_domain
    2. Rank agents via hybrid scoring (keywords, embeddings, retrieval feedback)
    3. Shortlist top K
    4. If complex: LLM selects agent(s) from shortlist
    5. If simple: auto-select top-1
    6. Output: selected_agents list
    """
```

Key changes:
- Agent pool is scoped by domain_id, not route
- Multi-domain queries: merge agent pools from multiple domains
- Agent definitions come from DB, not hardcoded list
- Prompt resolution: agent's `prompt_text` or `prompt_key` → resolved prompt

### 4.2 Modify `supervisor_routing.py`

- `_route_allowed_agents()` → `_domain_allowed_agents(domain_id, registry)`
- `_route_default_agent()` → `_domain_default_agent(domain_id, registry)`
- Keep backward-compat aliases for old route values

---

## Phase 5: Tool Resolver Redesign

### 5.1 Modify `nodes/tool_resolver.py`

Update to resolve tools **within the selected agent(s)**:

```python
def build_tool_resolver_node(
    *,
    graph_registry: GraphRegistry,
    ...
) -> Callable:
    """
    Phase 2c: Given agent(s), select tool(s).

    Flow:
    1. Get tools for each selected agent from graph_registry.tools_by_agent
    2. Rank via bigtool scoring
    3. Shortlist top K per agent
    4. Output: resolved_tools_by_agent
    """
```

Key changes:
- Tool pool scoped by agent_id
- Tool metadata from DB, not hardcoded profiles
- Namespace resolution from tool's definition_payload

### 5.2 Modify `bigtool_store.py`

- `smart_retrieve_tools()` accepts tool index entries built from `graph_registry.tools_by_agent`
- ToolIndexEntry construction from DB payloads instead of hardcoded TOOL_NAMESPACE_OVERRIDES

---

## Phase 6: Dynamic Graph Construction

### 6.1 New File: `graph_builder.py`

The core of the redesign — builds LangGraph StateGraph from `GraphRegistry`:

```python
async def build_graph_from_registry(
    *,
    registry: GraphRegistry,
    llm,
    dependencies: dict,
    checkpointer,
    feature_flags: dict,   # compare_mode, debate_mode, hybrid_mode, speculative_enabled
) -> CompiledGraph:
    """
    Build complete LangGraph graph from DB-driven registry.

    Steps:
    1. Build intent resolver node from registry.domains
    2. Build agent resolver node from registry.agents_by_domain
    3. Build tool resolver node from registry.tools_by_agent
    4. Build executor with dynamically-registered tools
    5. Wire standard pipeline: intent → memory → agent → plan → tools → execute → synthesis
    6. Add conditional edges for compare/debate/hybrid modes
    7. Compile and return
    """
```

### 6.2 Modify `complete_graph.py`

```python
async def build_complete_graph(...) -> CompiledGraph:
    # 1. Load registry from DB
    async with get_async_session() as session:
        registry = await load_graph_registry(session)

    # 2. Build graph from registry
    return await build_graph_from_registry(
        registry=registry,
        llm=llm,
        dependencies=dependencies,
        checkpointer=checkpointer,
        feature_flags={...},
    )
```

### 6.3 Modify `supervisor_agent.py`

Refactor `create_supervisor_agent()` to:
1. Accept `GraphRegistry` instead of hardcoded agent/tool lists
2. Build worker pool dynamically from `registry.agents_by_domain`
3. Build agent definitions from `registry.agent_index`
4. Build tool profiles from `registry.tool_index`
5. Wire nodes using factory functions that close over the registry

This is the largest refactoring. The 7000+ line file will be split:
- **`supervisor_agent.py`** — Slimmed down, delegates to graph_builder
- **`graph_builder.py`** — New file with graph construction logic
- **`worker_pool.py`** — Extract worker pool creation
- Keep prompts, constants, and routing in their existing files

---

## Phase 7: Complexity Classification Update

### 7.1 Modify `hybrid_state.py`

Update `classify_graph_complexity()` to use domain metadata:

```python
def classify_graph_complexity(
    *,
    resolved_intent: dict,
    user_query: str,
    domain_config: dict | None = None,  # NEW: domain's definition_payload
) -> str:
    # Check domain-level override
    if domain_config and domain_config.get("complexity_override"):
        return domain_config["complexity_override"]

    # Existing logic, but use domain_id instead of route for matching
    domain_id = resolved_intent.get("domain_id", "")
    ...
```

---

## Phase 8: Routing Backward Compatibility

### 8.1 Keep Route Enum

`routing.py` keeps the Route enum unchanged. Each domain has a `fallback_route` field that maps to a Route value.

### 8.2 Route Coercion

New utility:

```python
def domain_to_route(domain_id: str, registry: GraphRegistry) -> Route:
    """Map domain_id → Route enum for backward compat."""
    domain = registry.domain_index.get(domain_id)
    if domain:
        fallback = domain.get("fallback_route", "kunskap")
        try:
            return Route(fallback)
        except ValueError:
            pass
    return Route.KUNSKAP
```

This is used everywhere the existing code expects a Route enum.

### 8.3 Update `ROUTE_TOOL_SETS`

Generated dynamically from registry:

```python
def build_route_tool_sets(registry: GraphRegistry) -> dict[Route, list[str]]:
    """Build ROUTE_TOOL_SETS from DB hierarchy."""
    result: dict[Route, list[str]] = {route: [] for route in Route}
    for domain_id, agents in registry.agents_by_domain.items():
        route = domain_to_route(domain_id, registry)
        for agent in agents:
            agent_id = agent["agent_id"]
            for tool in registry.tools_by_agent.get(agent_id, []):
                result[route].append(tool["tool_id"])
    return result
```

---

## Phase 9: API Routes for Admin CRUD

### 9.1 New Route File: `routes/graph_config.py`

REST endpoints for managing the hierarchy:

```
GET    /api/v1/graph/domains              — List all domains
POST   /api/v1/graph/domains              — Create/update domain
DELETE /api/v1/graph/domains/{domain_id}  — Delete domain

GET    /api/v1/graph/agents               — List all agents (filterable by domain_id)
POST   /api/v1/graph/agents               — Create/update agent
DELETE /api/v1/graph/agents/{agent_id}    — Delete agent

GET    /api/v1/graph/tools                — List all tools (filterable by agent_id)
POST   /api/v1/graph/tools                — Create/update tool
DELETE /api/v1/graph/tools/{tool_id}      — Delete tool

GET    /api/v1/graph/registry             — Full registry snapshot (read-only)
POST   /api/v1/graph/reload               — Trigger graph rebuild
```

### 9.2 Pydantic Schemas

Add request/response schemas in `surfsense_backend/app/schemas/graph_config.py`.

---

## Phase 10: Seeding & Migration Strategy

### 10.1 Default Seed Data

Create `surfsense_backend/app/seeds/intent_domains.py` with the initial ~15 domains:

```python
DEFAULT_DOMAINS = [
    {"domain_id": "väder-och-klimat", "label": "Väder & Klimat", "fallback_route": "kunskap", ...},
    {"domain_id": "trafik-och-transport", "label": "Trafik & Transport", "fallback_route": "kunskap", ...},
    {"domain_id": "ekonomi-och-skatter", "label": "Ekonomi & Skatter", "fallback_route": "kunskap", ...},
    {"domain_id": "arbetsmarknad", "label": "Arbetsmarknad", "fallback_route": "kunskap", ...},
    {"domain_id": "befolkning-och-demografi", "label": "Befolkning & Demografi", "fallback_route": "kunskap", ...},
    {"domain_id": "utbildning", "label": "Utbildning", "fallback_route": "kunskap", ...},
    {"domain_id": "näringsliv-och-bolag", "label": "Näringsliv & Bolag", "fallback_route": "kunskap", ...},
    {"domain_id": "fastighet-och-mark", "label": "Fastighet & Mark", "fallback_route": "kunskap", ...},
    {"domain_id": "energi-och-miljö", "label": "Energi & Miljö", "fallback_route": "kunskap", ...},
    {"domain_id": "naturvetenskap", "label": "Naturvetenskap", "fallback_route": "kunskap", ...},
    {"domain_id": "handel-och-marknad", "label": "Handel & Marknad", "fallback_route": "kunskap", ...},
    {"domain_id": "politik-och-beslut", "label": "Politik & Beslut", "fallback_route": "kunskap", ...},
    {"domain_id": "hälsa-och-vård", "label": "Hälsa & Vård", "fallback_route": "kunskap", ...},
    {"domain_id": "rättsväsende", "label": "Rättsväsende", "fallback_route": "kunskap", ...},
    {"domain_id": "skapande", "label": "Skapande & Produktion", "fallback_route": "skapande", ...},
    {"domain_id": "konversation", "label": "Konversation", "fallback_route": "konversation", ...},
    {"domain_id": "jämförelse", "label": "Jämförelse & Analys", "fallback_route": "jämförelse", ...},
]
```

### 10.2 Agent Seeds

Map current 13 hardcoded agents to their domains:

```python
DEFAULT_AGENTS = [
    {"agent_id": "smhi", "domain_id": "väder-och-klimat", ...},
    {"agent_id": "trafik", "domain_id": "trafik-och-transport", ...},
    {"agent_id": "statistik", "domain_id": "ekonomi-och-skatter", ...},
    {"agent_id": "bolag", "domain_id": "näringsliv-och-bolag", ...},
    {"agent_id": "riksdagen", "domain_id": "politik-och-beslut", ...},
    {"agent_id": "marknad", "domain_id": "handel-och-marknad", ...},
    {"agent_id": "webb", "domain_id": "konversation", ...},  # General-purpose
    {"agent_id": "kod", "domain_id": "skapande", ...},
    {"agent_id": "kartor", "domain_id": "skapande", ...},
    {"agent_id": "media", "domain_id": "skapande", ...},
    {"agent_id": "kunskap", "domain_id": "konversation", ...},  # Fallback
    {"agent_id": "syntes", "domain_id": "jämförelse", ...},
    {"agent_id": "smalltalk", "domain_id": "konversation", ...},
]
```

### 10.3 Tool Seeds

Map current ROUTE_TOOL_SETS + _AGENT_TOOL_PROFILES to tools:

```python
DEFAULT_TOOLS = [
    {"tool_id": "smhi_weather", "agent_id": "smhi", ...},
    {"tool_id": "smhi_vaderprognoser_metfcst", "agent_id": "smhi", ...},
    # ... ~70 tools from current codebase
]
```

---

## Implementation Order

### Sprint 1: Foundation (DB + Services)
1. Add DB models to `db.py`
2. Create Alembic migration
3. Create seed data files
4. Create 4 service files (domain, agent, tool, registry)
5. Add API routes for admin CRUD

### Sprint 2: Intent Resolver
6. Refactor `intent_router.py` to use domains
7. Refactor `nodes/intent.py` to use `GraphRegistry`
8. Refactor `dispatcher.py` to use domains
9. Update `hybrid_state.py` complexity classification

### Sprint 3: Agent + Tool Resolvers
10. Refactor `nodes/agent_resolver.py` to use domain-scoped agents
11. Refactor `nodes/tool_resolver.py` to use agent-scoped tools
12. Refactor `supervisor_routing.py` for domain-based routing
13. Update `bigtool_store.py` to build index from registry

### Sprint 4: Dynamic Graph
14. Create `graph_builder.py` — dynamic graph construction
15. Refactor `complete_graph.py` to use registry-based builder
16. Refactor `supervisor_agent.py` — slim down, delegate to builder
17. Update worker pool creation from registry

### Sprint 5: Backward Compat + Testing
18. Add `domain_to_route()` coercion utility
19. Update all existing code that references Route enum directly
20. Add tests for new services and graph construction
21. Migration testing with seed data

---

## Files Modified (Summary)

| File | Action | Description |
|------|--------|-------------|
| `app/db.py` | MODIFY | Add 6 new model classes |
| `alembic/versions/xxx.py` | CREATE | Migration + seed data |
| `app/services/intent_domain_service.py` | CREATE | Domain CRUD |
| `app/services/agent_definition_service.py` | CREATE | Agent CRUD |
| `app/services/tool_definition_service.py` | CREATE | Tool CRUD |
| `app/services/graph_registry_service.py` | CREATE | Registry loader |
| `app/seeds/intent_domains.py` | CREATE | Default domain seeds |
| `app/seeds/agent_definitions.py` | CREATE | Default agent seeds |
| `app/seeds/tool_definitions.py` | CREATE | Default tool seeds |
| `app/routes/graph_config.py` | CREATE | Admin API endpoints |
| `app/schemas/graph_config.py` | CREATE | Pydantic schemas |
| `app/agents/new_chat/graph_builder.py` | CREATE | Dynamic graph builder |
| `app/agents/new_chat/nodes/intent.py` | MODIFY | Domain-based intent resolution |
| `app/agents/new_chat/intent_router.py` | MODIFY | Domain scoring |
| `app/agents/new_chat/dispatcher.py` | MODIFY | Domain dispatch |
| `app/agents/new_chat/nodes/agent_resolver.py` | MODIFY | Domain-scoped agent selection |
| `app/agents/new_chat/nodes/tool_resolver.py` | MODIFY | Agent-scoped tool selection |
| `app/agents/new_chat/supervisor_routing.py` | MODIFY | Domain-based routing |
| `app/agents/new_chat/supervisor_agent.py` | MODIFY | Delegate to graph_builder |
| `app/agents/new_chat/complete_graph.py` | MODIFY | Use registry |
| `app/agents/new_chat/routing.py` | MODIFY | Add domain_to_route() |
| `app/agents/new_chat/hybrid_state.py` | MODIFY | Domain complexity override |
| `app/agents/new_chat/bigtool_store.py` | MODIFY | Registry-based index |
| `tests/` | CREATE | New test files |

---

## Phase 11: Reactive Admin Flow (Live Propagation)

When an admin changes a domain/agent/tool in the UI, all running sessions and graph instances must react **immediately** — no restart, no stale cache.

### 11.1 Registry Version & Cache

```python
# In graph_registry_service.py

class RegistryCache:
    """Process-level singleton with version tracking."""

    _instance: GraphRegistry | None = None
    _version: int = 0           # Monotonically increasing
    _loaded_at: float = 0.0
    _lock: asyncio.Lock

    @classmethod
    async def get(cls, session: AsyncSession | None = None) -> GraphRegistry:
        """Return cached registry, reload if version changed."""
        if cls._instance and not await cls._is_stale(session):
            return cls._instance
        return await cls._reload(session)

    @classmethod
    async def invalidate(cls) -> None:
        """Force next get() to reload from DB."""
        cls._instance = None

    @classmethod
    async def _is_stale(cls, session) -> bool:
        """Check DB version counter against cached version."""
        db_version = await _read_registry_version(session)
        return db_version > cls._version
```

### 11.2 Version Counter Table

```python
class RegistryVersion(BaseModel):
    __tablename__ = "registry_version"

    key = Column(String(40), primary_key=True, default="global")
    version = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(TIMESTAMP(timezone=True))
```

Every mutation (upsert/delete) to `intent_domains`, `agent_definitions`, or `tool_definitions` increments this counter in the same transaction:

```python
async def _bump_registry_version(session: AsyncSession) -> int:
    result = await session.execute(
        update(RegistryVersion)
        .where(RegistryVersion.key == "global")
        .values(version=RegistryVersion.version + 1, updated_at=func.now())
        .returning(RegistryVersion.version)
    )
    return result.scalar_one()
```

### 11.3 PostgreSQL NOTIFY/LISTEN for Cross-Process Propagation

For multi-worker deployments (uvicorn with multiple workers, separate Celery workers):

```python
# In app/services/registry_events.py

REGISTRY_CHANNEL = "registry_invalidation"

async def notify_registry_changed(session: AsyncSession, version: int) -> None:
    """Send PG NOTIFY after registry mutation."""
    await session.execute(
        text(f"NOTIFY {REGISTRY_CHANNEL}, :payload"),
        {"payload": json.dumps({"version": version, "timestamp": time.time()})}
    )

async def listen_registry_changes(on_change: Callable[[int], Awaitable[None]]) -> None:
    """Background task: listen for PG NOTIFY and invalidate cache."""
    # Uses asyncpg raw connection for LISTEN
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.add_listener(REGISTRY_CHANNEL, lambda *args: ...)
    # On notification: call RegistryCache.invalidate()
```

### 11.4 Graph Hot-Reload

The compiled LangGraph graph is held in a `GraphHolder` singleton:

```python
class GraphHolder:
    """Holds the currently active compiled graph. Hot-swappable."""

    _graph: CompiledGraph | None = None
    _registry_version: int = 0

    @classmethod
    async def get_graph(cls, *, llm, dependencies, checkpointer, feature_flags) -> CompiledGraph:
        registry = await RegistryCache.get()
        if cls._graph and registry.version == cls._registry_version:
            return cls._graph
        # Rebuild graph from new registry
        cls._graph = await build_graph_from_registry(
            registry=registry, llm=llm, dependencies=dependencies,
            checkpointer=checkpointer, feature_flags=feature_flags,
        )
        cls._registry_version = registry.version
        return cls._graph
```

**Important**: Active sessions keep their existing graph instance for the duration of the session. Only new sessions pick up the new graph. This prevents mid-conversation breakage.

### 11.5 Admin API Mutation Flow

Every admin write endpoint follows this pattern:

```python
@router.post("/api/v1/graph/domains")
async def upsert_domain(payload: DomainUpsertRequest, session: AsyncSession, user: User):
    # 1. Validate + write to DB
    result = await upsert_intent_domain(session, payload.domain_id, payload.dict(), user.id)

    # 2. Bump version counter (same transaction)
    new_version = await _bump_registry_version(session)

    # 3. Commit
    await session.commit()

    # 4. Notify all workers
    await notify_registry_changed(session, new_version)

    # 5. Invalidate local cache
    await RegistryCache.invalidate()

    return {"status": "ok", "version": new_version, "domain": result}
```

### 11.6 Frontend Real-Time via Electric-SQL

The `intent_domains`, `agent_definitions`, and `tool_definitions` tables are added to the Electric-SQL sync shape, so the admin UI gets **live updates** when another admin makes changes:

```typescript
// In surfsense_web/lib/electric.ts
const domainShape = useShape({
  url: `${ELECTRIC_URL}/v1/shape`,
  params: { table: "intent_domains", columns: ["domain_id", "definition_payload", "updated_at"] },
});
```

### 11.7 Propagation Sequence Diagram

```
Admin UI                Frontend             Backend API          PostgreSQL          Other Workers
   │                      │                      │                    │                    │
   ├─ Save domain ───────►│                      │                    │                    │
   │                      ├─ POST /graph/domains►│                    │                    │
   │                      │                      ├─ UPDATE table ────►│                    │
   │                      │                      ├─ INCREMENT version►│                    │
   │                      │                      ├─ COMMIT ──────────►│                    │
   │                      │                      ├─ PG NOTIFY ───────►├─ NOTIFY payload──►│
   │                      │                      ├─ Invalidate cache  │                    ├─ Invalidate cache
   │                      │                      │◄─ {status: ok} ────│                    │
   │                      │◄─ Response ──────────│                    │                    │
   │                      │                      │                    │                    │
   │                      │◄─ Electric-SQL sync──│◄─── WAL stream ───│                    │
   │◄─ Live UI update ────│                      │                    │                    │
   │                      │                      │                    │                    │
   │   [Next user query]  │                      │                    │                    │
   │                      │                      ├─ RegistryCache.get│                    │
   │                      │                      │  (stale? reload)  │                    │
   │                      │                      ├─ GraphHolder.get  │                    │
   │                      │                      │  (version changed?│                    │
   │                      │                      │   rebuild graph)  │                    │
```

---

## Phase 12: supervisor_agent.py Refactoring

The current `supervisor_agent.py` is **7,163 lines** — a monolithic file that handles everything from prompt setup to graph compilation. This phase breaks it into clean, focused modules.

### 12.1 New Module Structure

```
surfsense_backend/app/agents/new_chat/
├── supervisor_agent.py          # SLIM: ~200 lines, just create_supervisor_agent() entry point
├── supervisor_types.py          # EXISTS: SupervisorState TypedDict (keep as-is)
├── supervisor_constants.py      # EXISTS: Constants (keep as-is)
├── supervisor_routing.py        # EXISTS: Routing helpers (keep as-is)
├── supervisor_prompt_setup.py   # NEW: ~180 lines — prompt resolution + injection
├── supervisor_worker_config.py  # NEW: ~200 lines — WorkerConfig definitions from registry
├── supervisor_agent_defs.py     # NEW: ~150 lines — agent definition building from registry
├── supervisor_runtime_config.py # NEW: ~280 lines — episodic memory, feedback, live routing setup
├── supervisor_tool_registry.py  # NEW: ~250 lines — tool registry, speculative setup, adaptive thresholds
├── supervisor_call_tools.py     # NEW: ~800 lines — call_agent() + call_agents_parallel() @tool defs
├── supervisor_custom_nodes.py   # NEW: ~460 lines — memory_context, smalltalk, post_tools, artifact_indexer, context_compactor
├── supervisor_guards.py         # NEW: ~250 lines — orchestration_guard, loop detection
├── supervisor_routing_fns.py    # NEW: ~170 lines — graph routing functions (route_after_intent, etc.)
├── supervisor_graph_assembly.py # NEW: ~440 lines — StateGraph node/edge wiring (compare/debate/normal)
├── supervisor_helpers.py        # NEW: ~400 lines — utility functions (coercion, scoring, fingerprinting)
├── graph_builder.py             # NEW: ~150 lines — top-level build_graph_from_registry()
└── complete_graph.py            # EXISTS: simplified wrapper
```

### 12.2 Extraction Map (What Moves Where)

| Current Lines | Current Content | New File |
|---------------|----------------|----------|
| 352-540 | Tool payload utils, message filtering | `supervisor_helpers.py` |
| 542-803 | Tool coercion & validation | `supervisor_helpers.py` |
| 804-884 | Guard/message utilities | `supervisor_helpers.py` |
| 891-1129 | Contract & result analysis | `supervisor_helpers.py` |
| 1129-1280 | Agent call analysis | `supervisor_helpers.py` |
| 1283-1490 | Subagent utilities | `supervisor_call_tools.py` |
| 1492-1687 | Loop detection & tool tracking | `supervisor_guards.py` |
| 1808-1980 | Prompt resolution | `supervisor_prompt_setup.py` |
| 2113-2260 | Worker configs | `supervisor_worker_config.py` |
| 2262-2575 | Agent definitions + metadata merge | `supervisor_agent_defs.py` |
| 2576-2850 | Runtime config (memory, feedback, live routing) | `supervisor_runtime_config.py` |
| 2821-3070 | Tool registry, adaptive thresholds, live tool selection | `supervisor_tool_registry.py` |
| 3071-3250 | Speculative execution | `supervisor_tool_registry.py` |
| 3250-4030 | Subagent task prep, context building | `supervisor_call_tools.py` |
| 4045-4220 | Sandbox & code tool handling | `supervisor_call_tools.py` |
| 4220-5790 | call_agent() + call_agents_parallel() tools | `supervisor_call_tools.py` |
| 5700-5830 | Reflect/todos tools + misc node builders | `supervisor_custom_nodes.py` |
| 5852-6308 | Custom node implementations | `supervisor_custom_nodes.py` |
| 6309-6550 | Orchestration guard | `supervisor_guards.py` |
| 6560-6727 | Routing functions | `supervisor_routing_fns.py` |
| 6728-7163 | Graph assembly | `supervisor_graph_assembly.py` |

### 12.3 New `supervisor_agent.py` (~200 lines)

After extraction, the entry point becomes a clean orchestrator:

```python
"""Supervisor agent entry point — delegates to modular components."""

from app.agents.new_chat.supervisor_prompt_setup import resolve_all_prompts
from app.agents.new_chat.supervisor_worker_config import build_worker_configs
from app.agents.new_chat.supervisor_agent_defs import build_agent_definitions
from app.agents.new_chat.supervisor_runtime_config import build_runtime_config
from app.agents.new_chat.supervisor_tool_registry import build_tool_registry
from app.agents.new_chat.supervisor_call_tools import build_call_tools
from app.agents.new_chat.supervisor_custom_nodes import build_custom_nodes
from app.agents.new_chat.supervisor_guards import build_orchestration_guard
from app.agents.new_chat.supervisor_routing_fns import build_routing_functions
from app.agents.new_chat.supervisor_graph_assembly import assemble_graph
from app.services.graph_registry_service import GraphRegistry


async def create_supervisor_agent(
    *,
    registry: GraphRegistry,   # NEW: replaces hardcoded configs
    llm,
    dependencies: dict,
    checkpointer,
    feature_flags: dict,
    tool_prompt_overrides: dict | None = None,
) -> CompiledGraph:
    # 1. Resolve prompts
    prompts = resolve_all_prompts(
        registry=registry,
        tool_prompt_overrides=tool_prompt_overrides,
    )

    # 2. Build worker configs from registry
    worker_configs = build_worker_configs(registry=registry, prompts=prompts)

    # 3. Build agent definitions from registry
    agent_defs = build_agent_definitions(registry=registry)

    # 4. Initialize runtime config
    runtime = await build_runtime_config(
        registry=registry,
        dependencies=dependencies,
    )

    # 5. Build tool registry
    tool_reg = build_tool_registry(
        registry=registry,
        runtime=runtime,
    )

    # 6. Build call_agent / call_agents_parallel tools
    call_tools = build_call_tools(
        registry=registry,
        worker_configs=worker_configs,
        runtime=runtime,
        tool_reg=tool_reg,
        prompts=prompts,
        llm=llm,
        dependencies=dependencies,
    )

    # 7. Build custom nodes
    nodes = build_custom_nodes(
        registry=registry,
        runtime=runtime,
        prompts=prompts,
        llm=llm,
    )

    # 8. Build guards
    guards = build_orchestration_guard(runtime=runtime)

    # 9. Build routing functions
    routing_fns = build_routing_functions(
        registry=registry,
        feature_flags=feature_flags,
    )

    # 10. Assemble and compile graph
    return assemble_graph(
        registry=registry,
        llm=llm,
        checkpointer=checkpointer,
        feature_flags=feature_flags,
        prompts=prompts,
        worker_configs=worker_configs,
        agent_defs=agent_defs,
        runtime=runtime,
        tool_reg=tool_reg,
        call_tools=call_tools,
        nodes=nodes,
        guards=guards,
        routing_fns=routing_fns,
    )
```

### 12.4 Registry-Driven Worker Configs

Currently, worker configs are hardcoded (lines 2113-2260). After refactoring:

```python
# supervisor_worker_config.py

def build_worker_configs(
    *,
    registry: GraphRegistry,
    prompts: dict[str, str],
) -> dict[str, WorkerConfig]:
    """Build WorkerConfig for each agent in the registry."""
    configs: dict[str, WorkerConfig] = {}
    for agent_id, agent_def in registry.agent_index.items():
        payload = agent_def.get("definition_payload", agent_def)
        primary_ns = [tuple(ns) for ns in payload.get("primary_namespaces", [])]
        fallback_ns = [tuple(ns) for ns in payload.get("fallback_namespaces", [])]
        prompt_key = payload.get("prompt_key", agent_id)
        prompt_text = payload.get("prompt_text") or prompts.get(prompt_key, "")

        configs[agent_id] = WorkerConfig(
            name=agent_id,
            system_prompt=prompt_text,
            primary_namespaces=primary_ns,
            fallback_namespaces=fallback_ns,
            max_concurrency=payload.get("worker_config", {}).get("max_concurrency", 4),
            timeout_seconds=payload.get("worker_config", {}).get("timeout_seconds", 120),
        )
    return configs
```

### 12.5 Registry-Driven Agent Definitions

```python
# supervisor_agent_defs.py

def build_agent_definitions(
    *,
    registry: GraphRegistry,
) -> list[dict]:
    """Convert registry agents to the format expected by agent_resolver node."""
    defs = []
    for agent_id, agent_def in registry.agent_index.items():
        payload = agent_def if isinstance(agent_def, dict) else {}
        defs.append({
            "name": agent_id,
            "description": payload.get("description", ""),
            "keywords": payload.get("keywords", []),
            "domain_id": payload.get("domain_id", ""),
            "namespace": tuple(payload.get("primary_namespaces", [[]])[0]) if payload.get("primary_namespaces") else (),
            "prompt_key": payload.get("prompt_key", agent_id),
        })
    return defs
```

### 12.6 Dependency Injection Pattern

Each extracted module uses a **factory function** that returns callables/configs. No module-level globals or singletons (except RegistryCache). Dependencies flow through the `create_supervisor_agent()` orchestrator.

```
create_supervisor_agent(registry, llm, deps, ...)
    ├─ resolve_all_prompts(registry)           → prompts dict
    ├─ build_worker_configs(registry, prompts)  → worker_configs dict
    ├─ build_agent_definitions(registry)        → agent_defs list
    ├─ build_runtime_config(registry, deps)     → runtime dataclass
    ├─ build_tool_registry(registry, runtime)   → tool_reg dataclass
    ├─ build_call_tools(registry, ...)          → call_tools (tool functions)
    ├─ build_custom_nodes(registry, ...)        → nodes (node functions)
    ├─ build_orchestration_guard(runtime)       → guards
    ├─ build_routing_functions(registry, flags) → routing_fns
    └─ assemble_graph(all of the above)         → CompiledGraph
```

---

## Updated Implementation Order

### Sprint 1: Foundation (DB + Services)
1. Add DB models to `db.py` (6 new tables + RegistryVersion)
2. Create Alembic migration
3. Create seed data files
4. Create 4 service files (domain, agent, tool, registry)
5. Create `registry_events.py` (PG NOTIFY/LISTEN)
6. Add API routes for admin CRUD with version bumping

### Sprint 2: supervisor_agent.py Refactor
7. Extract `supervisor_helpers.py` (utility functions)
8. Extract `supervisor_prompt_setup.py`
9. Extract `supervisor_worker_config.py`
10. Extract `supervisor_agent_defs.py`
11. Extract `supervisor_runtime_config.py`
12. Extract `supervisor_tool_registry.py`
13. Extract `supervisor_call_tools.py`
14. Extract `supervisor_custom_nodes.py`
15. Extract `supervisor_guards.py`
16. Extract `supervisor_routing_fns.py`
17. Extract `supervisor_graph_assembly.py`
18. Slim down `supervisor_agent.py` to orchestrator

### Sprint 3: Intent Resolver
19. Refactor `intent_router.py` to use domains
20. Refactor `nodes/intent.py` to use `GraphRegistry`
21. Refactor `dispatcher.py` to use domains
22. Update `hybrid_state.py` complexity classification

### Sprint 4: Agent + Tool Resolvers
23. Refactor `nodes/agent_resolver.py` to use domain-scoped agents
24. Refactor `nodes/tool_resolver.py` to use agent-scoped tools
25. Refactor `supervisor_routing.py` for domain-based routing
26. Update `bigtool_store.py` to build index from registry

### Sprint 5: Dynamic Graph + Reactive Admin
27. Create `graph_builder.py` — top-level graph construction
28. Refactor `complete_graph.py` to use registry-based builder
29. Implement `RegistryCache` + `GraphHolder`
30. Wire PG NOTIFY/LISTEN for cross-worker invalidation
31. Add Electric-SQL shapes for admin tables
32. Add `domain_to_route()` backward compat

### Sprint 6: Testing + Migration
33. Add tests for new services
34. Add tests for graph construction
35. Add tests for registry invalidation
36. Migration testing with seed data
37. Feature flag (`USE_DOMAIN_REGISTRY`) for gradual rollout

---

## Files Modified (Complete Summary)

| File | Action | Description |
|------|--------|-------------|
| **DB & Migrations** | | |
| `app/db.py` | MODIFY | Add 7 new model classes (3 entities + 3 history + RegistryVersion) |
| `alembic/versions/xxx.py` | CREATE | Migration + seed data |
| **Services** | | |
| `app/services/intent_domain_service.py` | CREATE | Domain CRUD |
| `app/services/agent_definition_service.py` | CREATE | Agent CRUD |
| `app/services/tool_definition_service.py` | CREATE | Tool CRUD |
| `app/services/graph_registry_service.py` | CREATE | Registry loader + cache |
| `app/services/registry_events.py` | CREATE | PG NOTIFY/LISTEN + invalidation |
| **Seeds** | | |
| `app/seeds/intent_domains.py` | CREATE | Default domain seeds |
| `app/seeds/agent_definitions.py` | CREATE | Default agent seeds |
| `app/seeds/tool_definitions.py` | CREATE | Default tool seeds |
| **API** | | |
| `app/routes/graph_config.py` | CREATE | Admin API endpoints |
| `app/schemas/graph_config.py` | CREATE | Pydantic schemas |
| **Supervisor Refactor** | | |
| `app/agents/new_chat/supervisor_agent.py` | REWRITE | Slim orchestrator (~200 lines) |
| `app/agents/new_chat/supervisor_prompt_setup.py` | CREATE | Prompt resolution |
| `app/agents/new_chat/supervisor_worker_config.py` | CREATE | Registry-driven worker configs |
| `app/agents/new_chat/supervisor_agent_defs.py` | CREATE | Registry-driven agent defs |
| `app/agents/new_chat/supervisor_runtime_config.py` | CREATE | Runtime config setup |
| `app/agents/new_chat/supervisor_tool_registry.py` | CREATE | Tool registry + speculative |
| `app/agents/new_chat/supervisor_call_tools.py` | CREATE | call_agent/call_agents_parallel |
| `app/agents/new_chat/supervisor_custom_nodes.py` | CREATE | Custom node implementations |
| `app/agents/new_chat/supervisor_guards.py` | CREATE | Orchestration guard + loop detection |
| `app/agents/new_chat/supervisor_routing_fns.py` | CREATE | Graph routing functions |
| `app/agents/new_chat/supervisor_graph_assembly.py` | CREATE | Graph node/edge wiring |
| `app/agents/new_chat/graph_builder.py` | CREATE | Top-level graph builder |
| **Intent/Agent/Tool Resolvers** | | |
| `app/agents/new_chat/nodes/intent.py` | MODIFY | Domain-based intent resolution |
| `app/agents/new_chat/intent_router.py` | MODIFY | Domain scoring |
| `app/agents/new_chat/dispatcher.py` | MODIFY | Domain dispatch |
| `app/agents/new_chat/nodes/agent_resolver.py` | MODIFY | Domain-scoped agent selection |
| `app/agents/new_chat/nodes/tool_resolver.py` | MODIFY | Agent-scoped tool selection |
| `app/agents/new_chat/supervisor_routing.py` | MODIFY | Domain-based routing |
| `app/agents/new_chat/routing.py` | MODIFY | Add domain_to_route() |
| `app/agents/new_chat/hybrid_state.py` | MODIFY | Domain complexity override |
| `app/agents/new_chat/bigtool_store.py` | MODIFY | Registry-based index |
| `app/agents/new_chat/complete_graph.py` | MODIFY | Use registry + GraphHolder |
| **Tests** | | |
| `tests/test_intent_domain_service.py` | CREATE | Domain service tests |
| `tests/test_agent_definition_service.py` | CREATE | Agent service tests |
| `tests/test_tool_definition_service.py` | CREATE | Tool service tests |
| `tests/test_graph_registry.py` | CREATE | Registry loading tests |
| `tests/test_graph_builder.py` | CREATE | Graph construction tests |
| `tests/test_registry_invalidation.py` | CREATE | Cache invalidation tests |

---

## Risk Mitigation

1. **Backward compat**: Route enum kept, old tables kept, domain has `fallback_route`
2. **Incremental migration**: Phase 1-2 can run in parallel with old system (dual-read)
3. **Feature flag**: `USE_DOMAIN_REGISTRY=true/false` env var to toggle new vs old path
4. **Seed data**: All current behavior preserved in seed defaults
5. **Graph hot-reload**: Via `GraphHolder` + PG NOTIFY — no restart needed
6. **Session safety**: Active sessions keep their graph instance; only new sessions pick up changes
7. **Supervisor refactor**: Extract-only (no logic changes) in Sprint 2 — verify identical behavior before modifying logic
8. **Atomic DB mutations**: Version bump + NOTIFY in same transaction — no race conditions
