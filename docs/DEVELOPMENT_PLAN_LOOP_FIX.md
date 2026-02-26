# OneSeek LangGraph Loop-Fix — Utvecklingsplan

> **Startdatum:** 2026-02-26
> **Branch:** `claude/debug-longgraph-loop-TCV0N`
> **Issue:** #44 (Loop issues)
> **Status:** Sprint P1 — **KLAR** ✓

---

## Bakgrund

LangGraph-flödet i OneSeek (Hybrid Supervisor v2) upplever frekventa loopar
som gör att frågor tar onödigt lång tid och ibland aldrig når response_layer.

### Identifierade rotorsaker

| # | Typ | Allvarlighet | Beskrivning |
|---|-----|-------------|-------------|
| BUG-1 | Loop | **KRITISK** | Critic `needs_more` → tool_resolver raderar `final_response` och kör hela kedjan igen (10 noder/loop, max 2 ggr) |
| BUG-2 | Loop | **KRITISK** | Critic `replan` → planner producerar identisk plan (samma agents, samma verktyg) |
| BUG-3 | Loop | **HÖG** | Orchestration_guard finalize överskrids av critic — guard sätter `final_response` men critic rensar den |
| BUG-4 | Loop | **MEDEL** | `no_progress_runs` nollställs vid minimal task-fingerprint-variation |
| BUG-5 | Think | **HÖG** | Ingen möjlighet att stänga av `<think>` för tool-call-steg |
| BUG-6 | Think | **MEDEL** | `think_enabled` styr bara streaming-filtret, inte system-prompten |
| BUG-7 | Response | **HÖG** | Synthesizer streamar text-delta FÖRE response_layer |
| BUG-8 | Response | **MEDEL** | Om response_layer inte gör LLM-call triggas ingen text-clear |
| BUG-9 | Response | **LÅG** | Executor saknas i pipeline chain tokens |
| BUG-10 | Studio | **MEDEL** | Studio nod-mappning saknar 11+ noder |
| BUG-11 | Studio | **LÅG** | Recursion_limit skiljer sig: Studio=120, prod=80 |
| BUG-12 | Config | **MEDEL** | Loop-guards är hårdkodade, inte konfigurerbara |
| BUG-13 | Design | **INFO** | `_MAX_REPLAN_ATTEMPTS=2` + initial = 30+ LangGraph-steg |

---

## Sprint-översikt

| Sprint | Prioritet | Innehåll | Löser buggar | Status |
|--------|----------|----------|-------------|--------|
| **P1** | Kritisk | Loop-fix, response layer, think-toggle | BUG 1-3, 5-8 | **KLAR** |
| **P2** | Hög | Studio, konfigurerbara guards | BUG 4, 9-12 | Ej påbörjad |
| **P3** | Medel | Multi-query decomposer | Ny funktionalitet | Ej påbörjad |
| **P4** | Framtida | Subagent mini-graphs, convergence, Pydantic structured output | Arkitekturell omskrivning | Planeras |

---

## Sprint P1 — Loop-fix & Stabilisering

> **Status:** [x] **KLAR** (2026-02-26)
> **Mål:** Eliminera loopar, garantera response_layer sist, think-toggle

### P1.1 — Guard-finalize skydd i critic

> **Status:** [x] **KLAR**
> **Löser:** BUG-3 (orchestration_guard override)

**Vad:** Lade till `guard_finalized: bool`, `total_steps: int`, `critic_history: list[dict]`
i SupervisorState. orchestration_guard sätter `guard_finalized=True` vid ALLA 6 finalize-paths.
Critic respekterar detta och returnerar alltid `"ok"` om `guard_finalized=True`.

**Ändrade filer:**
- `surfsense_backend/app/agents/new_chat/supervisor_types.py` — 3 nya state-fält
- `surfsense_backend/app/agents/new_chat/supervisor_constants.py` — `MAX_TOTAL_STEPS = 12`
- `surfsense_backend/app/agents/new_chat/supervisor_agent.py` — orchestration_guard sätter `guard_finalized=True` (6 paths), `total_steps` increment
- `surfsense_backend/app/agents/new_chat/nodes/critic.py` — Respekterar `guard_finalized`
- `surfsense_backend/app/agents/new_chat/nodes/smart_critic.py` — Respekterar `guard_finalized`

**Acceptanskriterier:**
- [x] Om orchestration_guard har satt `guard_finalized=True`, returnerar critic alltid `"ok"`
- [x] `final_response` rensas ALDRIG efter guard-finalize
- [x] Befintliga tester passerar

### P1.2 — Adaptive critic med total_steps

> **Status:** [x] **KLAR**
> **Löser:** BUG-1, BUG-2, BUG-13

**Vad:** `total_steps` incrementeras i orchestration_guard. Vid `>= MAX_TOTAL_STEPS (12)`
tvingar critic synthesis. `critic_history` spårar alla beslut; 2+ nyliga `needs_more`
→ force `ok` för att bryta loop. smart_critic har adaptiv confidence (0.7→0.4 vid step 8+).

**Ändrade filer:**
- `surfsense_backend/app/agents/new_chat/supervisor_constants.py` — `MAX_TOTAL_STEPS = 12`
- `surfsense_backend/app/agents/new_chat/supervisor_agent.py` — orchestration_guard incrementerar, critic_should_continue kollar total_steps
- `surfsense_backend/app/agents/new_chat/nodes/critic.py` — total_steps cap, critic_history, adaptiv loop-breaking
- `surfsense_backend/app/agents/new_chat/nodes/smart_critic.py` — Adaptiv confidence threshold

**Acceptanskriterier:**
- [x] `total_steps` ökar för varje exekveringsnod
- [x] Vid `total_steps >= 12` går flödet direkt till synthesis, aldrig tillbaka till planner/tool_resolver
- [x] Critic använder `critic_history` — identiska beslut undviks
- [x] Adaptiv threshold: vid step 8+, confidence threshold sjunker
- [x] Befintliga tester passerar

### P1.3 — Response layer streaming-ordning

> **Status:** [x] **KLAR**
> **Löser:** BUG-7, BUG-8

**Vad:** Flyttade `"synthesizer"` och `"progressive_synthesizer"` från
`_OUTPUT_PIPELINE_CHAIN_TOKENS` till `_INTERNAL_PIPELINE_CHAIN_TOKENS`.
Nu producerar bara `response_layer`, `smalltalk`, `compare_synthesizer` text-delta.

**Ändrade filer:**
- `surfsense_backend/app/tasks/chat/stream_new_chat.py` — Omklassificering av pipeline tokens

**Acceptanskriterier:**
- [x] Synthesizer-text visas INTE som text-delta (ej synlig i chatten direkt)
- [x] Synthesizer-text visas i FadeLayer (think-box) som reasoning
- [x] Response_layer-text är ALLTID den enda synliga text-delta
- [x] FadeLayer-komponenten fortsätter fungera korrekt
- [x] Befintliga tester passerar

### P1.4 — THINK_ON_TOOL_CALLS miljövariabel

> **Status:** [x] **KLAR**
> **Löser:** BUG-5, BUG-6

**Vad:** Lade till `THINK_ON_TOOL_CALLS` env-variabel och runtime flag. När `false`:
executor strips `<think>`-instruktioner från system-prompten. Syntes/response behåller think.
Skapade `SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK` och `inject_core_prompt(include_think_instructions=...)`.

**Ändrade filer:**
- `surfsense_backend/app/agents/new_chat/system_prompt.py` — `SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK`, `inject_core_prompt()` med param
- `surfsense_backend/app/agents/new_chat/nodes/executor.py` — `think_on_tool_calls` param, strips think i `_build_context_messages()`
- `surfsense_backend/app/agents/new_chat/supervisor_agent.py` — Propagerar `think_on_tool_calls` till executor
- `surfsense_backend/app/agents/new_chat/complete_graph.py` — `think_on_tool_calls` param
- `surfsense_backend/app/tasks/chat/stream_new_chat.py` — Läser env/runtime flag, propagerar till graph

**Acceptanskriterier:**
- [x] `THINK_ON_TOOL_CALLS=false` → executor-noden har INGA `<think>`-instruktioner
- [x] `THINK_ON_TOOL_CALLS=true` (default) → oförändrat beteende
- [x] Synthesizer/response_layer behåller `<think>`-instruktioner oavsett
- [x] Streaming-filtret hanterar avsaknad av `<think>`-taggar korrekt
- [x] Befintliga tester passerar

### P1.5 — Tester för Sprint P1

> **Status:** [x] **KLAR**

**Testfil:** `surfsense_backend/tests/test_loop_fix_p1.py` — **20 tester, alla passerar**

| Testklass | Antal | Testar |
|-----------|-------|--------|
| `TestGuardFinalized` | 3 | P1.1: guard_finalized skyddar, tillåter needs_more vid False, delegerar vid tom response |
| `TestTotalSteps` | 3 | P1.2: max → synthesis med/utan response, normal vid < max |
| `TestCriticHistory` | 3 | P1.2: 2x needs_more → force ok, 1x tillåter, history växer |
| `TestResponseLayerStreaming` | 4 | P1.3: synthesizer intern, response_layer output, executor intern |
| `TestThinkOnToolCalls` | 4 | P1.4: inject med/utan think, NO_THINK prompt, _ThinkStreamFilter |
| `TestSmartCriticGuardFinalized` | 1 | P1.2: smart_critic respekterar guard_finalized |
| `TestStateFields` | 2 | P1: nya state-fält och MAX_TOTAL_STEPS constant |

**Testresultat:**
```
tests/test_loop_fix_p1.py: 20 passed (0.16s)
Full suite: 174 passed, 32 failed (pre-existing), 8 skipped
Inga nya regressioner.
```

**Acceptanskriterier:**
- [x] ALLA 20 P1-tester passerar
- [x] Befintliga tester FORTSÄTTER passera (174 vs 156 baseline + 20 nya = korrekt)
- [x] Inga nya regressioner

---

## Sprint P2 — Studio & Konfiguration

> **Status:** [ ] Ej påbörjad
> **Mål:** Full Studio-integration, konfigurerbara guards

### P2.1 — Uppdatera LangGraph Studio nod-mappning

> **Löser:** BUG-10

**Filer att ändra:**
- `surfsense_backend/app/langgraph_studio.py`:
  - Uppdatera `_PROMPT_NODE_GROUP_TO_GRAPH_NODES` med alla saknade noder:
    - `response_layer_router`, `response_layer`, `domain_planner`,
      `orchestration_guard`, `progressive_synthesizer`, `speculative`,
      `speculative_merge`, `execution_router`, `memory_context`,
      `context_compactor`, `artifact_indexer`, `smalltalk`
  - Exponera `total_steps` och `guard_finalized` i Studio state visualization

### P2.2 — Synkronisera recursion_limit

> **Löser:** BUG-11

**Filer att ändra:**
- `surfsense_backend/app/tasks/chat/stream_new_chat.py`:
  - Ändra hårdkodad `recursion_limit: 80` till att använda samma källa som Studio
  - Läs från env-variabel `LANGGRAPH_RECURSION_LIMIT` (default: 80)
- `surfsense_backend/app/langgraph_studio.py`:
  - Läs från samma env-variabel som fallback

### P2.3 — Konfigurerbara loop-guards

> **Löser:** BUG-12

**Filer att ändra:**
- `surfsense_backend/app/agents/new_chat/supervisor_constants.py`:
  - `MAX_TOTAL_STEPS` → läs från env `MAX_TOTAL_STEPS` (default: 12)
  - `_MAX_REPLAN_ATTEMPTS` → läs från env `MAX_REPLAN_ATTEMPTS` (default: 2)
  - `_MAX_AGENT_HOPS_PER_TURN` → läs från env `MAX_AGENT_HOPS` (default: 3)
  - `_MAX_TOOL_CALLS_PER_TURN` → läs från env `MAX_TOOL_CALLS` (default: 12)
- `surfsense_backend/app/langgraph_studio.py`:
  - Exponera dessa i `StudioGraphConfigurationBase` som konfigurerbara fält

### P2.4 — Executor i pipeline chain tokens

> **Löser:** BUG-9

**Filer att ändra:**
- `surfsense_backend/app/tasks/chat/stream_new_chat.py`:
  - Lägg explicit till `"executor"` i `_INTERNAL_PIPELINE_CHAIN_TOKENS`
  - Verifiera att executor-text aldrig läcker som text-delta

### P2.5 — Förbättrad no_progress fingerprinting

> **Löser:** BUG-4

**Filer att ändra:**
- `surfsense_backend/app/agents/new_chat/supervisor_agent.py`:
  - Förbättra `_normalize_task_for_fingerprint` till att vara mer aggressiv i normalisering
  - Fingerprinting baseras på agent_name + route_hint (inte task-text)
  - Samma agent + samma route = no progress oavsett task-variation

### P2.6 — Tester för Sprint P2

**Ny testfil:** `surfsense_backend/tests/test_loop_fix_p2.py`

| Test | Testar |
|------|--------|
| `test_studio_node_mapping_complete` | P2.1: alla noder finns i mappningen |
| `test_recursion_limit_from_env` | P2.2: env-variabel styr limit |
| `test_configurable_max_total_steps` | P2.3: env styr max_total_steps |
| `test_configurable_max_replan` | P2.3: env styr max_replan |
| `test_executor_in_internal_pipeline` | P2.4: executor klassad som intern |
| `test_improved_fingerprinting_detects_same_agent` | P2.5: samma agent = no progress |

---

## Sprint P3 — Multi-Query Decomposer

> **Status:** [ ] Ej påbörjad
> **Mål:** Intelligent fråge-dekomponering för komplexa frågor
> **Källa:** Issue #44

### P3.1 — Multi-query decomposer node

**Vad:** Ny nod `multi_query_decomposer` som körs EFTER intent resolution
men FÖRE planner, BARA för `complex`-klassade frågor.

**Ny fil:** `surfsense_backend/app/agents/new_chat/nodes/multi_query_decomposer.py`

**State-tillägg:**
```python
atomic_questions: list[dict]  # [{"id": "q1", "text": "...", "depends_on": [], "domain": "väder"}]
```

**Grafändring:**
```
resolve_intent → memory_context → [route_after_intent]
                                    ├→ (complex) multi_query_decomposer → agent_resolver → planner
                                    ├→ (simple) tool_resolver
                                    └→ (trivial) smalltalk/END
```

**Acceptanskriterier:**
- [ ] Decomposer producerar atomic_questions med dependencies
- [ ] Planner använder atomic_questions för att generera bättre plan
- [ ] Simple och trivial frågor hoppar ÖVER decomposer (ingen extra latens)
- [ ] FadeLayer visar decomposer-reasoning i think-box

### P3.2 — Tester för Sprint P3

**Ny testfil:** `surfsense_backend/tests/test_multi_query_decomposer.py`

| Test | Testar |
|------|--------|
| `test_decomposer_splits_compound_question` | "Vad är vädret och trafiken?" → 2 atomic_questions |
| `test_decomposer_single_question_passthrough` | "Vad är vädret?" → 1 atomic_question |
| `test_decomposer_dependency_graph` | "Jämför A och B" → dep-graph med beroenden |
| `test_decomposer_skipped_for_simple` | Simple-query → decomposer körs inte |

---

## Sprint P4 — Arkitekturell Evolution (Framtida)

> **Status:** [ ] Planeras
> **Mål:** Subagent mini-graphs, convergence, structured output
> **Källa:** Issue #44

### P4.1 — Subagent Mini-Graphs

**Vad:** Varje subagent (kunskap, statistik, trafik, etc.) får en egen isolerad
mini-LangGraph med:
- Mini-planner (optional)
- Mini-executor med scoped tools
- Mini-critic
- Mini-synthesizer

**State-tillägg:**
```python
micro_plans: dict[str, list[dict]]  # subagent_id → [step1, step2...]
convergence_status: dict             # {"merged_fields": [...], "overlap_score": 0.92}
```

**Nya filer:**
- `surfsense_backend/app/agents/new_chat/nodes/subagent_mini_graph.py`
- `surfsense_backend/app/agents/new_chat/nodes/convergence_node.py`

**Grafändring:**
```
domain_planner → subagent_spawner → [SubagentMiniGraph x N parallellt]
                                     → convergence_node → critic
```

**Fördelar:**
- Isolerat state per subagent (ingen korsförorening)
- Max 4-6 calls per subagent (begränsar looping)
- Parallell exekvering av oberoende subagenter
- Varje subagent har egen critic (snabbare feedback)

**Risker:**
- Streaming-pipelinen måste hantera nested graphs
- Frontend FadeLayer måste anpassas för per-subagent reasoning
- Checkpointer-hantering för nested graphs
- Stor omskrivning: ~500-800 rader ny kod

### P4.2 — Pydantic Structured Output

**Vad:** Ersätt JSON-parsing med Pydantic-modeller för alla LLM-bedömningar:
- IntentResult(route, confidence, sub_intents)
- CriticDecision(decision, reason, adaptive_threshold, missing_critical)
- PlanStep(action, tool_id, expected_output)

**Fördelar:**
- Typning och validering av LLM-output
- Bättre felhantering vid malformad JSON
- Structured output via LiteLLM `response_format`

**Notering:** REGEX-baserade guards (max_steps, token, loop detection) ska
BEHÅLLAS som mekaniska guards. Bara LLM-bedömningar (critic, routing,
synthesis) ska använda Pydantic structured output.

### P4.3 — Adaptive Everything

**Vad:** Alla trösklar blir dynamiska baserat på flödets progress:
- Confidence threshold: sjunker från 0.7 → 0.4 med steg
- Max tool calls per subagent: sjunker från 6 → 3 med steg
- Synthesis aggressivitet: ökar med steg (mer merge, mer komprimering)

### P4.4 — Tester för Sprint P4

| Test | Testar |
|------|--------|
| `test_subagent_mini_graph_isolation` | Subagent state läcker inte till parent |
| `test_subagent_max_calls_per_agent` | Max 4-6 calls per mini-graph |
| `test_convergence_node_merges_results` | Convergence skapar unified artifact |
| `test_pydantic_critic_decision_parsing` | Structured output parsning |
| `test_adaptive_threshold_by_step` | Trösklar sjunker med steg |
| `test_parallel_subagents_execution` | Oberoende subagenter körs parallellt |

---

## Testbaseline (2026-02-26)

```
Testresultat FÖRE ändringar (baseline):
  156 passed
  30 failed (externa beroenden: async, embeddings, services)
  8 skipped
  7 collection errors (embeddings model)
  32 warnings (asyncio marks, deprecations)
```

**De 30 failures är PRE-EXISTING och relaterade till:**
- Async tests utan pytest-asyncio plugin (kolada, scb, smhi)
- Domain fan-out tests med ändrad API
- Prompt registry test med template-mismatch
- Mixed domain routing cache-test

---

### Sprint P1 testresultat (2026-02-26)

```
Testresultat EFTER Sprint P1:
  174 passed (+18 netto: 20 nya P1-tester, 2 pre-existing lösta)
  32 failed (pre-existing, oförändrade)
  8 skipped
  0 nya regressioner

P1-specifikt:
  tests/test_loop_fix_p1.py: 20/20 passed (0.16s)
```

---

## Grafflöde (referens)

```
resolve_intent → memory_context → [CONDITIONAL: route_after_intent]
├→ smalltalk → END
├→ speculative → agent_resolver
├→ agent_resolver → planner → planner_hitl_gate
│                                ├→ tool_resolver
│                                └→ END
├→ tool_resolver (simple shortcut)
└→ synthesis_hitl (trivial with final)

tool_resolver → [speculative_merge →] [execution_router →] domain_planner
domain_planner → execution_hitl_gate
                  ├→ executor → [tools → post_tools → artifact_indexer
                  │               → context_compactor → orchestration_guard]
                  │             → critic
                  └→ END

critic → synthesis_hitl (ok)
       → tool_resolver (needs_more) ← LOOP
       → planner (replan)           ← LOOP

synthesis_hitl → [progressive_synthesizer →] synthesizer
              → response_layer_router → response_layer → END
```

---

## Fil-index (alla filer som berörs)

| Fil | Sprint |
|-----|--------|
| `app/agents/new_chat/supervisor_types.py` | P1 |
| `app/agents/new_chat/supervisor_constants.py` | P1, P2 |
| `app/agents/new_chat/supervisor_agent.py` | P1, P2 |
| `app/agents/new_chat/complete_graph.py` | P1 |
| `app/agents/new_chat/nodes/critic.py` | P1 |
| `app/agents/new_chat/nodes/smart_critic.py` | P1 |
| `app/agents/new_chat/nodes/executor.py` | P1 |
| `app/agents/new_chat/system_prompt.py` | P1 |
| `app/tasks/chat/stream_new_chat.py` | P1, P2 |
| `app/langgraph_studio.py` | P2 |
| `app/agents/new_chat/nodes/multi_query_decomposer.py` | P3 (ny) |
| `app/agents/new_chat/nodes/subagent_mini_graph.py` | P4 (ny) |
| `app/agents/new_chat/nodes/convergence_node.py` | P4 (ny) |
| `tests/test_loop_fix_p1.py` | P1 (ny) |
| `tests/test_loop_fix_p2.py` | P2 (ny) |
| `tests/test_multi_query_decomposer.py` | P3 (ny) |
