# Supervisor Architecture (Bigtool + Workers)

This document describes the current multi-agent architecture with a lightweight
Supervisor, Bigtool-based Workers, tool namespaces, and cross-workflow support.
It also explains how data flows between agents and tools, plus how to add new
tools or agents.

---

## Table of contents

1. Overview
2. Core components
3. Tool namespaces and registry
4. Execution flow (end-to-end)
5. Supervisor state and planning
6. Worker behavior and cross-workflows
7. Data flow and citations
8. Tracing + UI steps
9. Adding a new tool
10. Adding a new agent
11. Common extension patterns

---

## 1) Overview

We use a Supervisor-driven architecture that delegates work to specialized
Workers. Each Worker uses `langgraph-bigtool` to retrieve only the relevant
tools from a global store (InMemoryStore now, PostgresStore later).

Key goals:
- Scale to many tools without prompt/tool-list explosion
- Allow cross-workflows (e.g., statistics -> media) in one session
- Keep routing deterministic and lightweight
- Keep tool usage and citations consistent
- Cache common agent combinations for sub-second reuse

---

## 2) Core components

**Top-level Router**
- Route: `knowledge`, `action`, `statistics`, or `smalltalk`
- Determines whether to use Supervisor or Smalltalk deep agent

**Supervisor Agent**
- Lightweight planner and delegator
- Uses only 4 tools:
  - `retrieve_agents`
  - `call_agent`
  - `write_todos`
  - `reflect_on_progress`
- Maintains `active_plan` across turns

**Workers (Bigtool Agents)**
- Knowledge Worker
- Action Worker
- Statistics Worker
- Media Worker (action/media namespace)
- Browser Worker (knowledge/web namespace)
- Code Worker (general namespace fallback)

**Tool Store**
- Global registry of tools (built at runtime)
- Namespaced for targeted retrieval

**Connector Service**
- External ingestion (e.g., SCB tool outputs stored for citations)

**Trace + Streaming**
- SSE steps show routing, tool calls, plan updates, and reflections

---

## 3) Tool namespaces and registry

All tools are indexed into a global store with namespaces. Examples:

- `tools/statistics/*`
  - `scb_*` tools (top-level + subtools)
- `tools/action/*`
  - `generate_podcast`, `smhi_weather`, `trafiklab_route`, etc.
- `tools/knowledge/*`
  - `search_knowledge_base`, `search_surfsense_docs`, `search_tavily`
- `tools/general/*`
  - `write_todos`, `reflect_on_progress`, `save_memory`, `recall_memory`

Namespace-first retrieval keeps context small and reduces tool mismatch.

---

## 4) Execution flow (end-to-end)

```mermaid
flowchart TD
    A[User message] --> B{Is /compare?}
    B -- yes --> C[stream_compare_chat]
    B -- no --> D[stream_new_chat]

    D --> E[dispatch_route]
    E -->|smalltalk| S[Smalltalk DeepAgent]
    E -->|knowledge/action/statistics| G[Supervisor Agent]

    subgraph SUP["Supervisor"]
        G0[retrieve_agents] --> G1[write_todos plan]
        G1 --> G2[call_agent(worker)]
        G2 --> G3[reflect_on_progress]
        G3 --> G4[final response]
    end

    subgraph WORK["Workers (Bigtool)"]
        W1[Knowledge Worker]
        W2[Action Worker]
        W3[Statistics Worker]
        W4[Media Worker]
        W5[Browser Worker]
    end

    G2 --> WORK

    subgraph STORE["Global Tool Store"]
        T1[tools/knowledge/*]
        T2[tools/action/*]
        T3[tools/statistics/*]
        T4[tools/general/*]
    end

    WORK --> STORE
```

---

## 5) Supervisor state and planning

Supervisor state includes:
- `active_plan`: list of steps + status
- `plan_complete`: boolean flag
- `recent_agent_calls`: rolling window of last 2-3 calls
- `route_hint`: router hint (knowledge/action/statistics)

Behavior:
- If plan exists and not complete: continue
- If plan complete or topic shift: create new plan
- `write_todos` updates plan + can set `plan_complete`
- When `plan_complete` is true, the next message starts a fresh plan
- `reflect_on_progress` runs after each step

### 5.1) Agent-combo cache (sub-second reuse)

The Supervisor caches common agent combinations to avoid recomputing
`retrieve_agents()` on repeated patterns (e.g., statistics -> media).

- **In-memory cache**: fastest path for repeated queries
- **Database cache**: persistent across restarts (`agent_combo_cache`)
- Cache key includes route hint + recent agent calls + query tokens
- TTL: ~20 minutes (in-memory), DB keeps hit_count/last_used_at

---

## 6) Worker behavior and cross-workflows

Workers run `retrieve_tools` with namespace preference:

**Knowledge Worker**
- Primary: `tools/knowledge/*`
- Fallback: `tools/action/*`, `tools/statistics/*`, `tools/general/*`

**Action Worker**
- Primary: `tools/action/*`
- Fallback: `tools/knowledge/*`, `tools/statistics/*`, `tools/general/*`

**Statistics Worker**
- Primary: `tools/statistics/*`
- Fallback: `tools/action/*`, `tools/knowledge/*`, `tools/general/*`

This allows:
1. Statistics -> Media (podcast)
2. Weather -> Knowledge fallback
3. Tools across namespaces without re-routing

---

## 7) Data flow and citations

Example: SCB tool call

```text
User -> Supervisor -> Statistics Worker -> scb_* tool
     -> SCB query -> tool output -> ConnectorService.ingest_tool_output
     -> Stored Document + Chunks -> Citations usable in response
```

Key points:
- Tool output ingested into Search History
- Citations reference stored chunk IDs
- Worker output flows back through Supervisor

---

## 8) Tracing + UI steps

Steps show:
- Routing
- retrieve_agents + selected agents
- call_agent + task + short result
- retrieve_tools + selected tools
- write_todos plan updates
- reflect_on_progress notes

Critic output (quality check) is shown in steps, not user response.
The critic micro-step runs after each worker call to detect missing data
(`needs_more`) and can keep the plan active.

---

## 9) Add a new tool

### Step-by-step
1. Create tool implementation in:
   `surfsense_backend/app/agents/new_chat/tools/<tool>.py`
2. Register in `tools/registry.py`:
   - name
   - description
   - factory
   - dependencies
3. Map tool to namespace in `bigtool_store.py`:
   - add to `TOOL_NAMESPACE_OVERRIDES`
   - add keywords in `TOOL_KEYWORDS`
4. (Optional) if tool produces data for citations:
   - call `connector_service.ingest_tool_output(...)`
5. Test with Supervisor:
   - ensure retrieve_tools finds the tool

---

## 10) Add a new agent

### Step-by-step
1. Create a worker prompt (or reuse existing):
   - add new prompt key in `prompt_registry.py`
2. Add a WorkerConfig in `supervisor_agent.py`:
   - primary namespaces
   - fallback namespaces
3. Add AgentDefinition in `supervisor_agent.py`:
   - name, description, keywords
4. Add optional routing hint (if needed)

Example:
```text
name: "energy"
primary: tools/statistics/energy
fallback: tools/knowledge, tools/action
```

---

## 11) Common extension patterns

### A) Add more SCB subtools
- Extend `SCB_TOOL_DEFINITIONS` in `statistics_agent.py`
- Include table codes + typical filters + example queries

### B) Add new live APIs (e.g., Trafikverket, Nord Pool)
- Create tool + add to registry
- Add keywords for retrieval
- Add namespace under `tools/action/*` or `tools/statistics/*`

### C) Switch to PostgresStore later
- Replace InMemoryStore in `bigtool_store.py`
- Keep namespaces identical

---

## Appendix: Example cross-workflow

```
User: "Hur många bor i Hjo?"
Supervisor -> statistics -> SCB

User: "Gör en podcast av det"
Supervisor -> media -> generate_podcast
```

Everything runs in one session without re-routing.
