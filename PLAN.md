# Plan: Compare Supervisor v2 — Unified Architecture

## Sammanfattning

Ersätta den linjära compare-pipelinen (`fan_out → collect → tavily → synthesizer`) med **samma P4-arkitektur** som normal mode använder: isolerade subagent mini-graphs, convergence node, mini-critic, adaptive guard, och proper handoff contracts. Varje extern modell + en ny research-agent blir **isolerade subagenter** med egna mini-graphs. Frontenden uppdateras med **Spotlight Arena**.

### Kärnprincip

> **En teknik, två modes.** Normal mode och compare mode ska använda identisk infrastruktur (`subagent_mini_graph.py`, `convergence_node.py`). Skillnaden ligger i *vilka* subagenter som spawnas och *hur* convergence-noden mergar resultaten — inte i *pipelinens struktur*.

---

## Nuläge vs Mål

### Nuläge (separat linjär pipeline)
```
Normal mode:
  resolve_intent → memory_context → agent_resolver → planner → tool_resolver
  → execution_router → [subagent_spawner → SubagentMiniGraph × N] → convergence
  → critic → synthesizer → response_layer → END

Compare mode:
  resolve_intent → compare_fan_out → compare_collect → compare_tavily
  → compare_synthesizer → END
```

### Mål (unified P4 architecture)
```
Normal mode:
  resolve_intent → memory_context → agent_resolver → planner → tool_resolver
  → execution_router → [subagent_spawner → SubagentMiniGraph × N] → convergence
  → critic → synthesizer → response_layer → END

Compare mode:
  resolve_intent → compare_domain_planner → [compare_subagent_spawner
    → CompareSubagentMiniGraph × 8 (7 modeller + 1 research)]
  → compare_convergence → compare_critic → compare_synthesizer → END
```

Båda modes använder nu:
- **Subagent mini-graphs** med planner → executor → critic → adaptive guard
- **Convergence node** med LLM-driven merge, overlap, conflict detection
- **Handoff contracts** (status, confidence, summary, findings)
- **Isolerade checkpoint namespaces** per subagent
- **Adaptive thresholds** (confidence sjunker vid retries)

---

## Del 1: Backend — Compare Supervisor v2

### Steg 1: Compare Domain Planner

**Ny funktion:** `build_compare_domain_planner_node()` i `compare_executor.py`

Denna nod ersätter `compare_fan_out`. Den genererar `domain_plans` — samma format som normal mode's `domain_planner`:

```python
domain_plans = {
    "grok": {
        "agent": "external_model",
        "tools": ["call_grok"],
        "rationale": "Extern modell: Grok (xAI)",
        "spec": EXTERNAL_MODEL_SPECS[0],
    },
    "deepseek": { ... },
    "gemini": { ... },
    "gpt": { ... },
    "claude": { ... },
    "perplexity": { ... },
    "qwen": { ... },
    "research": {
        "agent": "research",
        "tools": ["search_tavily"],
        "rationale": "Webb-research agent med Tavily-sökning",
    },
}
```

Denna nod är **deterministisk** (inget LLM-anrop) — alla 8 domäner inkluderas alltid. Sätter `domain_plans` i state.

### Steg 2: Compare Subagent Spawner (återanvänder P4)

**Återanvänd:** `build_subagent_spawner_node()` från `nodes/subagent_mini_graph.py`

Varje domän (extern modell + research) får en **isolerad subagent mini-graph**:

```
Per extern modell (grok, deepseek, etc.):
  mini_planner → mini_executor (call_external_model) → mini_critic → (retry | handoff)

Research-agent:
  mini_planner → mini_executor (Tavily × N) → mini_critic → (retry | handoff)
```

**Mini-planner för externa modeller:** Trivial — bara "kör modellen med frågan". Kan skippa LLM-anrop och returnera en fast plan.

**Mini-planner för research:** LLM-driven — decomponerar frågan till 1-3 sökfrågor.

**Mini-critic för alla:** Evaluerar resultatkvalitet:
- Extern modell: Fick vi ett meningsfullt svar? Inte bara "jag kan inte svara"?
- Research: Fick vi relevanta webbkällor? Matchar de frågan?

**Mini-executor:**
- Extern modell: `call_external_model(spec, query)` — samma som idag
- Research: Tavily-sökning via `connector_service.search_tavily()`

**Adaptive guard:** Max 1 retry för externa modeller (API-timeout), max 2 för research.

**Handoff contract (identiskt med P4):**
```python
{
    "subagent_id": "sa-mini_grok-abc123",
    "status": "complete" | "partial" | "error",
    "confidence": 0.85,
    "summary": "Grok svarade med...",
    "findings": ["Kvantdatorer har...", "IBM lanserade..."],
    "artifact_refs": [],
    "used_tools": ["call_grok"],
}
```

### Steg 3: Compare Workers

**Modifiera:** `supervisor_agent.py`

Skapa specialiserade workers för compare mode som registreras i worker pool:

```python
# Worker för varje extern modell
for spec in EXTERNAL_MODEL_SPECS:
    worker_pool.register(
        f"external_{spec.key}",
        create_external_model_worker(spec),
    )

# Worker för research
worker_pool.register(
    "research",
    create_research_worker(connector_service, search_space_id, user_id),
)
```

Alternativt: Eftersom compare-workers är enkla (ett API-anrop var), kan `_run_single_domain` overridas med en `compare_run_single_domain` som hanterar den specifika logiken utan att behöva registrera i worker pool. Välj det enklaste alternativet.

### Steg 4: Compare Convergence Node (återanvänder P4)

**Återanvänd:** `build_convergence_node()` från `nodes/convergence_node.py`

Compare convergence gör exakt samma sak som normal convergence:
1. Tar `subagent_summaries` (8 handoffs)
2. `_flatten_summaries()` — hanterar ev. sub-spawned results
3. LLM-driven merge med:
   - **overlap_score**: Hur mycket överensstämmer modellerna?
   - **conflicts**: Var säger modellerna olika?
   - **merged_summary**: Unified faktaunderlag
   - **source_domains**: ["grok", "deepseek", ..., "research"]
   - **domain_statuses**: per-domän status

Compare-specifik tillägg i convergence-prompten:
```
Research-domänens resultat ska prioriteras för faktapåståenden.
Notera konflikter mellan modeller och research-agenten explicit.
```

### Steg 5: Compare Critic (återanvänder P4-mönster)

**Ny funktion:** `build_compare_critic_node()`

Enkel critic som evaluerar convergence-resultatet:
- Har alla domäner leverat? (success count)
- Är merged_summary tillräckligt?
- Finns det ouppklarade konflikter?

Om allt ser bra ut → `"ok"` → synthesizer.
Om critical failures → `"needs_more"` → retry (med adaptive guard, max 1 retry).

### Steg 6: Compare Synthesizer (uppdatera befintlig)

**Modifiera:** `compare_executor.py` och `compare_prompts.py`

Synthesizern läser nu `convergence_status` istället för `compare_outputs`:

```python
async def compare_synthesizer(state, *, prompt_override=None):
    convergence = state.get("convergence_status", {})
    subagent_summaries = state.get("subagent_summaries", [])

    context = _build_synthesis_from_convergence(
        user_query=user_query,
        convergence=convergence,
        summaries=subagent_summaries,
    )
    # ... LLM-anrop som idag
```

**Uppdatera prompt** för att hantera convergence-data:
```
Indatastruktur:
- Convergence merged_summary med overlap_score och conflicts
- Per-domän handoffs med confidence och findings
- Research-agentens verifierade webbkällor
```

### Steg 7: Research Agent Worker

**Ny fil:** `surfsense_backend/app/agents/new_chat/compare_research_worker.py`

Research-agentens executor. Använder samma pattern som P4 mini-executor men med specifik logik:

```python
async def run_research_executor(
    query: str,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
) -> dict[str, Any]:
    """Research agent: query decomposition → parallel Tavily → synthesis."""

    # 1. Decompose query (LLM-driven, max 3 sub-queries)
    sub_queries = await _decompose_query(query)

    # 2. Parallel Tavily searches
    results = await asyncio.gather(*[
        connector_service.search_tavily(
            user_query=_ensure_sweden_bias(q),
            search_space_id=search_space_id,
            top_k=3,
            user_id=user_id,
        )
        for q in sub_queries
    ])

    # 3. Structure results with citation chunk IDs
    return {
        "status": "success",
        "source": "OneSeek Research",
        "queries_used": sub_queries,
        "web_sources": [...],
        "synthesis": "...",
        "citation_chunk_ids": [...],
    }
```

### Steg 8: Graph Assembly (supervisor_agent.py)

**Modifiera:** `supervisor_agent.py` (rad ~6640-6668)

Ersätt den linjära compare-pipelinen med P4-mönstret:

```python
if compare_mode:
    from functools import partial
    from app.agents.new_chat.compare_executor import (
        build_compare_domain_planner_node,
        build_compare_synthesizer_node,
    )
    from app.agents.new_chat.nodes.subagent_mini_graph import (
        build_subagent_spawner_node,
    )
    from app.agents.new_chat.nodes.convergence_node import (
        build_convergence_node,
    )

    compare_domain_planner = build_compare_domain_planner_node(
        external_model_specs=EXTERNAL_MODEL_SPECS,
        include_research=True,
    )

    compare_spawner = build_subagent_spawner_node(
        llm=llm,
        spawner_prompt_template=compare_spawner_prompt,
        mini_planner_prompt_template=compare_mini_planner_prompt,
        mini_critic_prompt_template=compare_mini_critic_prompt,
        mini_synthesizer_prompt_template=compare_mini_synth_prompt,
        adaptive_guard_prompt_template=adaptive_guard_prompt,
        latest_user_query_fn=_latest_user_query,
        extract_first_json_object_fn=_extract_first_json_object,
        worker_pool=worker_pool,  # Inkl. compare workers
        build_subagent_id_fn=build_subagent_id,
        build_handoff_payload_fn=build_handoff_payload,
        base_thread_id=base_thread_id,
        parent_checkpoint_ns=parent_checkpoint_ns,
        subagent_isolation_enabled=True,
        subagent_result_max_chars=12000,
        execution_timeout_seconds=90,
        max_nesting_depth=1,  # Ingen rekursiv nesting i compare
    )

    compare_convergence = build_convergence_node(
        llm=llm,
        convergence_prompt_template=compare_convergence_prompt,
        latest_user_query_fn=_latest_user_query,
        extract_first_json_object_fn=_extract_first_json_object,
    )

    compare_synthesizer_node = build_compare_synthesizer_node(
        prompt_override=compare_synthesizer_prompt_template,
    )

    # Graph assembly
    graph_builder.add_node("compare_domain_planner", ...)
    graph_builder.add_node("compare_spawner", ...)
    graph_builder.add_node("compare_convergence", ...)
    graph_builder.add_node("compare_synthesizer", ...)

    graph_builder.set_entry_point("resolve_intent")
    graph_builder.add_edge("resolve_intent", "compare_domain_planner")
    graph_builder.add_edge("compare_domain_planner", "compare_spawner")
    graph_builder.add_edge("compare_spawner", "compare_convergence")
    graph_builder.add_edge("compare_convergence", "compare_synthesizer")
    graph_builder.add_edge("compare_synthesizer", END)
```

### Steg 9: Prompts (P4-mönster)

**Modifiera:** `compare_prompts.py`

Lägg till prompter som matchar P4:s mönster:

```python
COMPARE_MINI_PLANNER_PROMPT = """
Du är mini-planner för compare mode. Skapa en kort plan per domän.
..."""

COMPARE_MINI_CRITIC_PROMPT = """
Du är mini-critic för compare mode. Utvärdera subagentens resultat.
..."""

COMPARE_CONVERGENCE_PROMPT = """
Du är convergence-noden för compare mode. Merga resultat från
{N} subagenter (externa modeller + research).
Identifiera:
- overlap_score: Hur mycket överensstämmer svaren
- conflicts: Var säger domänerna olika
- merged_summary: Unified sammanfattning
Research-agentens resultat ska prioriteras för faktapåståenden.
..."""
```

### Steg 10: State-kompatibilitet

**Modifiera:** `supervisor_types.py`

Säkerställ att `SupervisorState` redan har alla P4-fält som compare-grafen behöver:
- `domain_plans` ✓ (redan P4)
- `spawned_domains` ✓
- `subagent_summaries` ✓
- `subagent_handoffs` ✓
- `micro_plans` ✓
- `convergence_status` ✓
- `compare_outputs` (behåll för bakåtkompatibilitet med frontend)

Lägg till mapper från convergence → compare_outputs så att frontend-korten fortfarande renderas korrekt.

### Steg 11: SSE-streaming

**Modifiera:** `stream_new_chat.py`

Streaming ska nu hantera P4-events från compare mode:
- `subagent_spawner` emittar per-domän thinking steps
- Varje extern modell får sin egen thinking step (som idag)
- Research-agenten får en thinking step med "Söker webben..."
- Convergence emittar merged result
- Synthesizer emittar final text

### Steg 12: Registrering

**Modifiera:** `bigtool_store.py`

```python
TOOL_NAMESPACE_OVERRIDES["call_oneseek"] = ("tools", "compare", "research")
TOOL_KEYWORDS["call_oneseek"] = ["oneseek", "research", "fakta", "webb", "sök"]
```

### Steg 13: Ta bort legacy compare-noder

**Ta bort:** `compare_fan_out`, `compare_collect`, `compare_tavily` från `compare_executor.py`

Behåll `compare_synthesizer` (uppdaterad) och `_build_synthesis_context` (uppdaterad).

---

## Del 2: Frontend — Spotlight Arena

### Steg 14: OneSeek Research ModelCard

**Modifiera:** `surfsense_web/components/tool-ui/compare-model.tsx`

Anpassa `OneseekToolUI` (redan registrerad) för research-agentens output:
- OneSeek-logga med "Research Agent" badge
- Visar använda sökfrågor som chips
- Visar webbkällor med titel + URL
- Visar syntesen (faktaunderlag, inte modell-respons)
- Latency + antal källor istället för token usage
- Confidence-indikator från handoff contract

### Steg 15: Spotlight Arena layout

**Ny fil:** `surfsense_web/components/tool-ui/spotlight-arena.tsx`

Layout-komponent:
- OneSeek Research-kortet i "spotlight"-position (centrerat, gradient-glow)
- Externa modellkort i responsivt grid nedanför (2-3 kolumner)
- Convergence-sammanfattning som expanderbar sektion
- Konflikter markerade med varningsikon
- Overlap-score som visuell indikator (progress bar)
- Design: shadcn/ui, oklch CSS-variabler, dark mode

### Steg 16: Thread-integration

**Modifiera:** `surfsense_web/components/assistant-ui/thread.tsx`

Detektera compare tool-calls → rendera `<SpotlightArena>`.

### Steg 17: Message utils

**Modifiera:** `surfsense_web/lib/chat/message-utils.ts`

Skicka `compare-summary` till Spotlight Arena istället för att filtrera bort.

---

## Flödesdiagram (Compare Supervisor v2)

```
User Input (/compare query)
    ↓
resolve_intent
    ↓
compare_domain_planner (deterministisk — 8 domäner alltid)
    ↓
compare_subagent_spawner (asyncio.gather, semaphore=8)
    ├─→ SubagentMiniGraph[grok]
    │   ├─ mini_planner (fast plan)
    │   ├─ mini_executor (call_external_model → xAI API)
    │   ├─ mini_critic (evaluate response)
    │   └─ handoff {status, confidence, summary, findings}
    │
    ├─→ SubagentMiniGraph[deepseek]
    │   └─ (samma mönster)
    │
    ├─→ SubagentMiniGraph[gemini|gpt|claude|perplexity|qwen]
    │   └─ (samma mönster × 5)
    │
    └─→ SubagentMiniGraph[research]    ← NY
        ├─ mini_planner (LLM query decomposition → 1-3 sub-queries)
        ├─ mini_executor (parallel Tavily search)
        ├─ mini_critic (evaluate web source quality)
        └─ handoff {status, confidence, summary, findings, web_sources}
    ↓
compare_convergence (LLM-driven merge)
    ├─ overlap_score: 0.82
    ├─ conflicts: [{domain_a: "grok", domain_b: "claude", field: "..."}]
    ├─ merged_summary: "Unified faktaunderlag..."
    └─ source_domains: ["grok", ..., "research"]
    ↓
compare_synthesizer (final LLM synthesis)
    ↓
END → Stream Spotlight Arena till frontend
```

---

## Jämförelse: Gammal vs Ny

| Aspekt | Gammal (linjär) | Ny (P4 unified) |
|--------|----------------|-----------------|
| Pipeline-struktur | Egen linjär pipeline | Samma P4-infra som normal mode |
| Per-modell isolation | Ingen | Full (subagent_id, checkpoint_ns, sandbox) |
| Per-modell critic | Ingen | Mini-critic per subagent |
| Retry-logik | Ingen | Adaptive guard per subagent |
| Resultat-merge | Enkel concat | LLM-driven convergence (overlap, conflicts) |
| Research agent | Ingen (placeholder) | Isolerad subagent med Tavily |
| Handoff contracts | Ingen | Proper (status, confidence, summary, findings) |
| State-fält | `compare_outputs` (custom) | `domain_plans`, `subagent_summaries`, `convergence_status` (P4) |
| Prompts | Egna, inte registrerade | Registrerade i prompt_registry, admin-anpassbara |
| Rekursiv nesting | Nej | Möjlig (depth=1 default) |
| Frontend-rendering | Individuella tool-calls | Spotlight Arena med convergence-data |

---

## Filer

**Nya filer:**
- `surfsense_backend/app/agents/new_chat/compare_research_worker.py`
- `surfsense_web/components/tool-ui/spotlight-arena.tsx`

**Modifierade filer:**
- `surfsense_backend/app/agents/new_chat/compare_executor.py` (stor omskrivning)
- `surfsense_backend/app/agents/new_chat/compare_prompts.py` (nya P4-prompter)
- `surfsense_backend/app/agents/new_chat/supervisor_agent.py` (graph assembly)
- `surfsense_backend/app/agents/new_chat/supervisor_types.py` (kompatibilitetsmappning)
- `surfsense_backend/app/agents/new_chat/bigtool_store.py` (registrering)
- `surfsense_backend/app/agents/new_chat/prompt_registry.py` (nya prompt keys)
- `surfsense_backend/app/tasks/chat/stream_new_chat.py` (P4 events i compare)
- `surfsense_web/components/tool-ui/compare-model.tsx` (research card)
- `surfsense_web/components/assistant-ui/thread.tsx` (Spotlight Arena)
- `surfsense_web/app/dashboard/[search_space_id]/new-chat/new-chat-page.tsx`
- `surfsense_web/lib/chat/message-utils.ts`

**Återanvända P4-filer (ingen ändring):**
- `surfsense_backend/app/agents/new_chat/nodes/subagent_mini_graph.py`
- `surfsense_backend/app/agents/new_chat/nodes/convergence_node.py`
- `surfsense_backend/app/agents/new_chat/structured_schemas.py`
