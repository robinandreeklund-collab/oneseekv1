# Compare v1 — Komplett Teknisk Dokumentation

> Spotlight Arena: Multi-LLM jämförelse med kriteriebaserad ranking
> Senast uppdaterad: 2026-03-02 (v1.0 — P4-arkitektur, kriteriebaserad scoring, Spotlight Arena UI)

---

## Innehåll

1. [Översikt](#1-översikt)
2. [Arkitektur](#2-arkitektur)
3. [Backend — Filstruktur](#3-backend--filstruktur)
4. [Frontend — Filstruktur](#4-frontend--filstruktur)
5. [Dataflöde (SSE Events)](#5-dataflöde-sse-events)
6. [Kriteriebaserad Utvärdering](#6-kriteriebaserad-utvärdering)
7. [Convergence & Syntes](#7-convergence--syntes)
8. [Research Agent (OneSeek)](#8-research-agent-oneseek)
9. [Admin — Prompt Registry](#9-admin--prompt-registry)
10. [State Management](#10-state-management)
11. [Algoritmdetaljer](#11-algoritmdetaljer)
12. [Konfiguration](#12-konfiguration)
13. [Sandbox-isolering](#13-sandbox-isolering)
14. [Testning](#14-testning)
15. [Framtida arbete](#15-framtida-arbete)

---

## 1. Översikt

Compare-läget (Spotlight Arena) är ett subgraph-system i OneSeek som kör samma fråga mot 7 externa AI-modeller + 1 intern research-agent parallellt, utvärderar varje svar på 4 kriterier via isolerade LLM-bedömare, och syntetiserar en jämförande analys med strukturerad ranking.

### Kommandon

| Kommando | Beskrivning |
|----------|-------------|
| `/compare <fråga>` | Kör frågan mot alla externa modeller + research-agent, utvärderar och rankar svaren i Spotlight Arena |

### Deltagare (8 st)

| Nyckel | Display | Typ | config_id |
|--------|---------|-----|-----------|
| `call_grok` | Grok | Extern modell (xAI) | -20 |
| `call_deepseek` | DeepSeek | Extern modell | -21 |
| `call_gemini` | Gemini | Extern modell (Google) | -22 |
| `call_gpt` | ChatGPT | Extern modell (OpenAI) | -23 |
| `call_claude` | Claude | Extern modell (Anthropic) | -24 |
| `call_perplexity` | Perplexity | Extern modell | -25 |
| `call_qwen` | Qwen | Extern modell (Alibaba) | -26 |
| `call_oneseek` | OneSeek Research | Intern LLM + Tavily-sökning | — |

### 4 Utvärderingskriterier

| Kriterium | Vikt | Mäter |
|-----------|------|-------|
| Korrekthet | 35% | Faktamässig precision, stämmer siffror/datum/namn |
| Relevans | 25% | Besvaras kärnfrågan? On-topic? |
| Djup | 20% | Detalj, nyanser, kontext, kantfall |
| Klarhet | 20% | Struktur, tydlighet, logiskt flöde |

---

## 2. Arkitektur

### Graph-flöde (LangGraph StateGraph)

```
resolve_intent
    │
    ▼
    [route == "jämförelse"] ?
    │ ja
    ▼
compare_domain_planner       (deterministisk — alltid 8 domäner)
    │
    ▼
compare_subagent_spawner     (P4 mini-grafer × 8 parallellt)
    ├─ grok-domän ──── call_external_model → 4× criterion_eval → handoff
    ├─ deepseek-domän ── call_external_model → 4× criterion_eval → handoff
    ├─ gemini-domän ─── call_external_model → 4× criterion_eval → handoff
    ├─ gpt-domän ────── call_external_model → 4× criterion_eval → handoff
    ├─ claude-domän ─── call_external_model → 4× criterion_eval → handoff
    ├─ perplexity-domän call_external_model → 4× criterion_eval → handoff
    ├─ qwen-domän ───── call_external_model → 4× criterion_eval → handoff
    └─ research-domän ─ decompose → tavily → synthesize → 4× criterion_eval → handoff
    │
    ▼
compare_convergence          (LLM-driven merge med overlap/conflict-detektion)
    │
    ▼
compare_synthesizer          (slutgiltig syntes + Spotlight Arena JSON)
    │
    ▼
END
```

### Per-domän Mini-Graph (P4-mönster)

Varje domän kör som en isolerad subagent:

```
┌─────────────────────────────────────────────────┐
│  Subagent mini-graph (per domän)                │
│                                                  │
│  1. Extern modell-anrop ELLER Tavily research   │
│     ↓                                            │
│  2. model_response_ready event (SSE)            │
│     ↓                                            │
│  3. criterion_evaluation_started event (SSE)    │
│     ↓                                            │
│  4. 4× parallella LLM-bedömare (bakom semafor) │
│     ├─ relevans  ─── criterion_complete (SSE)   │
│     ├─ djup      ─── criterion_complete (SSE)   │
│     ├─ klarhet   ─── criterion_complete (SSE)   │
│     └─ korrekthet ── criterion_complete (SSE)   │
│     ↓                                            │
│  5. Handoff med criterion_scores + confidence   │
└─────────────────────────────────────────────────┘
```

### Ömsesidig Exklusion med Debate Mode

Compare och Debate är ömsesidigt exklusiva subgrafer:
- Frontend kontrollerar `isCompare && !isDebate` innan Spotlight Arena renderas
- Route-detektion dirigerar till rätt subgraph via `Route.JAMFORELSE`

---

## 3. Backend — Filstruktur

```
surfsense_backend/app/agents/new_chat/
├── compare_executor.py           # 1354 rader — Huvud-orkestrator (4 noder)
│   ├── build_compare_domain_planner_node()
│   ├── build_compare_subagent_spawner_node()
│   ├── build_compare_convergence_node()  (via supervisor_agent)
│   ├── build_compare_synthesizer_node()
│   ├── compute_weighted_score()
│   ├── rank_models_by_weighted_score()
│   └── _sanitize_synthesis_text()
│
├── compare_criterion_evaluator.py # 356 rader — Per-kriterium LLM-bedömare
│   ├── evaluate_criterion()        # Enskilt kriterium med retry
│   ├── evaluate_model_response()   # Alla 4 kriterier per modell
│   └── _GLOBAL_CRITERION_SEM      # Global semafor (max 4 concurrent)
│
├── compare_research_worker.py     # 398 rader — Research-agent med Tavily
│   ├── run_research_executor()     # Decompose → sök → syntetisera
│   ├── ResearchWorker              # Minimal worker-interface
│   └── build_compare_external_model_worker()
│
├── compare_prompts.py             # 351 rader — Alla compare-promptar
│   ├── DEFAULT_COMPARE_ANALYSIS_PROMPT
│   ├── COMPARE_SUPERVISOR_INSTRUCTIONS
│   ├── DEFAULT_COMPARE_DOMAIN_PLANNER_PROMPT
│   ├── DEFAULT_COMPARE_MINI_PLANNER_PROMPT
│   ├── DEFAULT_COMPARE_MINI_CRITIC_PROMPT
│   ├── DEFAULT_COMPARE_CONVERGENCE_PROMPT
│   ├── DEFAULT_COMPARE_CRITERION_*_PROMPT (×4)
│   └── DEFAULT_COMPARE_RESEARCH_PROMPT
│
├── tools/external_models.py       # 406 rader — Externa modell-specifikationer
│   ├── EXTERNAL_MODEL_SPECS        # 7 modell-spec dataklasser
│   ├── call_external_model()       # LiteLLM-wrapper
│   └── create_external_model_tool()
│
├── structured_schemas.py          # Pydantic-scheman
│   ├── CriterionEvalResult
│   ├── ResearchDecomposeResult
│   ├── ArenaAnalysisResult
│   ├── ConvergenceResult
│   └── CompareSynthesisResult
│
├── supervisor_agent.py            # Supervisor-integration (compare_mode flag)
├── supervisor_types.py            # State-fält: compare_outputs, criterion_events
├── supervisor_routing.py          # Compare route-detektion
├── dispatcher.py                  # /compare prefix-detektering
├── prompt_registry.py             # 8 compare-prompts registrerade
└── complete_graph.py              # build_complete_graph(compare_mode=True)

surfsense_backend/app/tasks/chat/
└── stream_compare_chat.py         # 1407 rader — DEPRECATED legacy implementation
    ├── is_compare_request()        # (fortfarande använd för kommando-detektion)
    └── extract_compare_query()     # (fortfarande använd)
```

---

## 4. Frontend — Filstruktur

```
surfsense_web/components/
├── tool-ui/
│   ├── spotlight-arena.tsx        # 1414 rader — Spotlight Arena layout
│   │   ├── SpotlightArenaActiveContext  # Boolean context
│   │   ├── LiveCriterionContext          # SSE live poäng-kontext
│   │   ├── LiveCriterionPodContext       # Pod-metadata kontext
│   │   ├── ScoreBar                      # Animerade poäng-staplar
│   │   ├── PhaseIndicator                # 4-fas progress
│   │   ├── DuelCard                      # Topp-2 modeller (stor vy)
│   │   ├── VsDuel                        # VS-layout
│   │   ├── RunnerUpCard                  # Plats 3+ (kompakt vy)
│   │   ├── ConvergenceSummary            # Slutanalys-kort
│   │   ├── MetaBadges                    # Latens/tokens/CO2-märken
│   │   ├── PodDebugPanel                 # Pod-info (power-user)
│   │   ├── ExpandableResponse            # Fullständigt svar
│   │   └── SpotlightArenaLayout          # Huvud-layout-komponent
│   │
│   ├── compare-model.tsx          # 416 rader — Individuella modell-kort
│   │   ├── ExternalModelArgsSchema (Zod)
│   │   ├── ExternalModelResultSchema (Zod)
│   │   ├── ModelCard, ModelLogo, ModelErrorState, ModelLoading
│   │   └── 8× ToolUI-exporter (Grok, Claude, GPT, Gemini, DeepSeek, Perplexity, Qwen, OneSeek)
│   │
│   └── index.ts                   # Re-export av alla compare ToolUIs
│
├── assistant-ui/
│   └── assistant-message.tsx      # Compare-detektering + arena-rendering
│       ├── COMPARE_TOOL_NAMES Set
│       ├── isCompare detection
│       └── SpotlightArenaLayout rendering
│
└── new-chat/
    └── new-chat-page.tsx          # SSE-eventhantering för compare

surfsense_web/lib/chat/
└── message-utils.ts               # compare-summary filtrering

surfsense_web/contracts/types/
└── agent-prompts.types.ts         # Compare prompt-nycklar
```

---

## 5. Dataflöde (SSE Events)

### Backend → Frontend Streaming

Compare-flödet emitterar 4 typer av custom events via LangGraph `adispatch_custom_event`:

| SSE Event | Tidpunkt | Data | Frontend-effekt |
|-----------|----------|------|-----------------|
| `model_response_ready` | Direkt efter API-svar | `{domain, tool_call_id, tool_name, result}` | Modell-kort visas omedelbart |
| `criterion_evaluation_started` | Bedömning påbörjas | `{domain, timestamp}` | Spinners visas på poäng-staplar |
| `criterion_complete` | Per kriterium, stegvis | `{domain, criterion, score, reasoning, pod_id, latency_ms}` | Individuella poäng uppdateras live |
| `model_complete` | Alla 4 kriterier klara | `{domain, tool_call_id, tool_name, result}` | Slutlig kortstatus (med alla poäng) |

### Frontend SSE Event Handlers (`new-chat-page.tsx`)

```typescript
// data-model-response-ready: Lägg till modell-kort direkt
case "data-model-response-ready": {
  // Uppdatera tool-call med result för omedelbar rendering
  break;
}

// data-criterion-evaluation-started: Markera domän som "evaluating"
case "data-criterion-evaluation-started": {
  // Aktivera spinners på poäng-staplar
  break;
}

// data-criterion-complete: Uppdatera live-poäng progressivt
case "data-criterion-complete": {
  // Uppdatera LiveCriterionContext med ny poäng
  // Lagra pod-metadata i LiveCriterionPodContext
  break;
}

// data-compare-summary: Slutgiltig jämförelse-sammanfattning
case "data-compare-summary": {
  compareSummary = parsed.data;
  break;
}
```

### Progressiv Rendering-pipeline

```
Backend (parallella API-anrop)
    │
    ├─ model_response_ready (Grok klar)
    │   → Frontend: Grok-kort visas (utan poäng)
    │
    ├─ criterion_evaluation_started (Grok)
    │   → Frontend: Spinners på Groks poäng-staplar
    │
    ├─ criterion_complete (Grok/relevans: 85)
    │   → Frontend: Relevans-stapel fylls, ✓ visas
    │
    ├─ model_response_ready (Claude klar)
    │   → Frontend: Claude-kort visas
    │
    ├─ criterion_complete (Grok/djup: 72)
    │   → Frontend: Djup-stapel fylls
    │
    │ ... (fler events mellanvävda)
    │
    ├─ model_complete (alla domäner klara)
    │   → Frontend: Alla kort har fullständiga poäng
    │
    └─ Syntes-text + spotlight-arena-data JSON
        → Frontend: ConvergenceSummary renderas
```

### Meddelande-persistens

Compare-sammanfattningen sparas i meddelandets content-array:

```typescript
[
  { type: "thinking-steps", steps: [...] },
  { type: "compare-summary", summary: {...} },
  { type: "text", text: "Syntestext..." },
  { type: "tool-call", toolName: "call_grok", args: {...}, result: {...} },
  // ... fler tool-calls
]
```

Vid rendering filtreras `compare-summary` bort från synlig text (sparas enbart i persistens-lagret).

---

## 6. Kriteriebaserad Utvärdering

### Arkitektur

Varje domän (7 modeller + 1 research) utvärderas av 4 isolerade LLM-bedömare.
Total: 8 domäner × 4 kriterier = 32 LLM-anrop.

### Concurrency Control

```python
# Global semafor — delad mellan ALLA domäner och kriterier
_MAX_CONCURRENT = 4
_GLOBAL_CRITERION_SEM = asyncio.Semaphore(_MAX_CONCURRENT)

# 32 tasks skapas, men max 4 körs samtidigt
async with _GLOBAL_CRITERION_SEM:
    raw = await asyncio.wait_for(llm.ainvoke(messages), timeout=90)
```

### Retry-strategi

```
Attempt 1: Kör direkt
    │ Fail → vänta 2s
Attempt 2: Retry
    │ Fail → vänta 5s
Attempt 3: Sista försöket
    │ Fail → score=50 (neutral fallback)
```

### Per-kriterium Promptar

Varje kriterium har en isolerad prompt som ENBART bedömer sin dimension:

- **Relevans**: "Besvarar svaret kärnfrågan? Är informationen on-topic?"
- **Djup**: "Hur detaljerat och nyanserat är svaret? Inkluderar det kontext?"
- **Klarhet**: "Hur tydligt och välstrukturerat är svaret? Logiskt flöde?"
- **Korrekthet**: "Hur faktamässigt korrekt? Stämmer siffror, datum, namn?"

Korrekthetsbedömaren får även research-data (max 3000 tecken) som referens.

### Poängskala

| Poäng | Nivå |
|-------|------|
| 90–100 | Utmärkt |
| 70–89 | Bra |
| 50–69 | Medel |
| 30–49 | Svag |
| 0–29 | Mycket svag |

### Structured Output

Varje bedömare returnerar strikt JSON:

```json
{
  "thinking": "Intern resonering (ej visad)",
  "score": 85,
  "reasoning": "En mening som motiverar poängen."
}
```

Parsing: Pydantic `CriterionEvalResult` → fallback regex-extraktion → fallback score=50.

---

## 7. Convergence & Syntes

### Convergence Node

Tar emot handoffs från alla 8 domäner och skapar en enhetlig analys:

**Input:**
- Per-domän: summary, findings, confidence, criterion_scores, criterion_reasonings

**Output (JSON):**
```json
{
  "thinking": "...",
  "merged_summary": "Sammanslagen markdown-sammanfattning",
  "overlap_score": 0.72,
  "conflicts": [
    {"domain_a": "grok", "domain_b": "claude", "field": "datum", "description": "..."}
  ],
  "model_scores": {
    "grok": {"relevans": 82, "djup": 65, "klarhet": 78, "korrekthet": 71}
  },
  "agreements": ["Alla modeller är överens om X"],
  "disagreements": ["Grok hävdar X medan Claude hävdar Y"],
  "unique_insights": {"claude": "Enda modellen som nämner X"},
  "comparative_summary": "Djup jämförande analys..."
}
```

### Synthesizer Node

Skapar det slutgiltiga svaret med Spotlight Arena JSON-block:

**Output-format:**
````
```spotlight-arena-data
{
  "arena_analysis": {
    "consensus": ["Alla modeller är överens om X"],
    "disagreements": [
      {"topic": "Kort ämne", "sides": {"Grok,Gemini": "Hävdar X", "Claude,GPT": "Hävdar Y"}, "verdict": "Research stödjer Y"}
    ],
    "unique_contributions": [
      {"model": "Claude", "insight": "Enda modellen som nämner X"}
    ],
    "winner_rationale": "[#1-modellen] levererar det mest kompletta svaret...",
    "reliability_notes": "Research-agenten bekräftar Z."
  }
}
```

[Markdown-svar med jämförande analys]

<!-- possible_next_steps:
- Uppföljningsfråga 1
- Uppföljningsfråga 2
-->
````

### Sanitering av Syntes-text

Mindre LLM:er kan läcka rå-JSON i den synliga texten. Backend (`_sanitize_synthesis_text`) och frontend (`sanitizeSynthesisText`) kör parallella saneringsstrategier:

1. Ta bort `spotlight-arena-data`-block
2. Ta bort `json`-fenced blocks
3. Ta bort trailing JSON-blobbar
4. Ta bort inline naked JSON med kända fältnamn
5. Rad-för-rad brace-balansering (fånga kvarvarande fragment)

---

## 8. Research Agent (OneSeek)

### Pipeline

```
1. Query Decomposition (LLM-driven)
   │  Input: "Vad är Sveriges BNP?"
   │  Output: ["Sveriges BNP 2025", "BNP per capita Sverige"]
   ▼
2. Parallella Tavily-sökningar (max 3 queries × 3 resultat)
   │  Timeout: 45s per sökning
   ▼
3. URL-deduplicering
   ▼
4. LLM-syntes av webbkällor
   │  Max 12 källor, 600 tecken per snippet
   │  Timeout: 30s
   ▼
5. Strukturerat resultat (P4 handoff-kontrakt)
```

### Konfiguration

| Parameter | Värde |
|-----------|-------|
| `_MAX_RESEARCH_QUERIES` | 3 |
| `_MAX_TAVILY_RESULTS_PER_QUERY` | 3 |
| `_RESEARCH_TIMEOUT_SECONDS` | 45 |
| `_RESEARCH_SYNTHESIS_TIMEOUT` | 30 |

### Prioriteringsordning vid konflikter

1. **ONESEEK_RESEARCH** (verifierad webbdata)
2. Färskhet (nyaste källa)
3. Modellkonsensus
4. Intern kunskap (med disclaimer)

---

## 9. Admin — Prompt Registry

### Registrerade Compare-promptar

| Nyckel | Grupp | Beskrivning |
|--------|-------|-------------|
| `compare.supervisor.instructions` | compare | Supervisor-instruktioner |
| `compare.analysis.system` | compare | Slutsyntes-prompt |
| `compare.external.system` | compare | Extern modell-systemprompt |
| `compare.domain_planner.system` | compare_mini | Domänplanering |
| `compare.mini_planner.system` | compare_mini | Per-domän mikroplanering |
| `compare.mini_critic.system` | compare_mini | Resultatkvalitetsbedömning |
| `compare.convergence.system` | compare_mini | Resultat-merge |
| `compare.criterion.relevans` | compare_mini | Relevans-bedömare |
| `compare.criterion.djup` | compare_mini | Djup-bedömare |
| `compare.criterion.klarhet` | compare_mini | Klarhet-bedömare |
| `compare.criterion.korrekthet` | compare_mini | Korrekthet-bedömare |
| `compare.research.system` | compare_mini | Research-agent |

### Prompt-override-flöde

1. Admin ändrar prompt i `/admin/prompts`
2. Sparas i `global_agent_prompt`-tabell
3. Vid runtime: `resolve_prompt()` hämtar override → fallback till default
4. Effekt: Omedelbar — nästa `/compare` använder ny prompt

---

## 10. State Management

### Backend (SupervisorState)

```python
class SupervisorState(TypedDict):
    # Compare-specifika fält:
    compare_outputs: Annotated[list[dict], _append_compare_outputs]  # Modellsvar
    criterion_events: list[dict[str, Any]]         # Kriterium-events för SSE
    model_complete_events: list[dict[str, Any]]    # Modell-klar events
    compare_arena_data: dict[str, Any] | None      # Arena-analys från synthesizer
```

**Reducer `_append_compare_outputs`:** Mergar nya modellsvar med deduplicering via `tool_call_id`.

### Frontend (React State)

```typescript
// Contexts (provided by assistant-message.tsx)
SpotlightArenaActiveContext  // boolean — styr om arena-vy är aktiv
LiveCriterionContext         // Record<domain, Partial<ModelScore>>
LiveCriterionPodContext      // Record<domain, Partial<Record<criterion, PodMeta>>>

// State i new-chat-page.tsx
let compareSummary: unknown | null = null;
const [liveCriterionScores, setLiveCriterionScores] = useState({});
const [liveCriterionPodInfo, setLiveCriterionPodInfo] = useState({});
```

---

## 11. Algoritmdetaljer

### Confidence-Weighted Scoring

```python
CRITERION_WEIGHTS = {
    "korrekthet": 0.35,   # Accuracy (35%)
    "relevans":   0.25,   # Relevance (25%)
    "djup":       0.20,   # Depth (20%)
    "klarhet":    0.20,   # Clarity (20%)
}

def compute_weighted_score(scores: dict) -> float:
    total_weight = 0.0
    weighted_sum = 0.0
    for criterion, weight in CRITERION_WEIGHTS.items():
        value = scores.get(criterion, 0)
        weighted_sum += weight * float(value)
        total_weight += weight
    return round(weighted_sum / total_weight, 1)
```

### Ranking-algoritm

1. Beräkna viktat poäng per modell (0–100)
2. Research-agent (`domain == "research"`) exkluderas från ranking
3. Sortera fallande efter viktat poäng
4. Tilldela rank 1, 2, 3, ...
5. Frontend sorterar: complete-status först, sedan fallande viktat poäng

### Score Priority (Frontend)

```
1. criterion_scores i tool-result  (slutgiltiga LLM-bedömningar)
2. Live SSE criterion scores       (partiella, saknade → 0)
3. model_scores från convergence   (LLM-merge-bedömning)
4. Nollpoäng {relevans: 0, ...}   (väntar på bedömning)
```

### Convergence Confidence-beräkning

```python
# Per modell: genomsnitt av 4 kriterier → confidence 0.0–1.0
avg_score = eval_result.get("total", 200) / 4
confidence = round(avg_score / 100, 2)

# Research-agent: baserat på antal webbkällor
confidence = min(0.9, 0.3 + 0.1 * len(web_sources))
```

---

## 12. Konfiguration

### Timeout-värden

| Parameter | Värde | Fil |
|-----------|-------|-----|
| `EXTERNAL_MODEL_TIMEOUT_SECONDS` | 90s | `external_models.py` |
| `execution_timeout_seconds` | 90s | `compare_executor.py` |
| `criterion_timeout_seconds` | 90s | `compare_criterion_evaluator.py` |
| `_RESEARCH_TIMEOUT_SECONDS` | 45s | `compare_research_worker.py` |
| `_RESEARCH_SYNTHESIS_TIMEOUT` | 30s | `compare_research_worker.py` |

### Textgränser

| Parameter | Värde | Beskrivning |
|-----------|-------|-------------|
| `MAX_EXTERNAL_MODEL_RESPONSE_CHARS` | 12 000 | Max svarslängd per modell |
| `MAX_EXTERNAL_MODEL_SUMMARY_CHARS` | 280 | Kort sammanfattning |
| Model response i criterion eval | 6 000 | Trunkerad input till bedömare |
| Research context i korrekthetsbedömare | 3 000 | Max research-kontext |

### Concurrency

| Parameter | Värde | Beskrivning |
|-----------|-------|-------------|
| `_MAX_CONCURRENT` (criterion sem) | 4 | Max parallella kriterium-LLM-anrop |
| Domain semaphore | 10 | Max parallella domän-exekveringar |
| `_MAX_RETRIES` (criterion) | 2 | Retry-gräns per kriterium |
| `_RETRY_DELAYS` | (2.0, 5.0) | Backoff-intervall i sekunder |

### Miljö-/energi-konstanter

```typescript
ENERGY_WH_PER_1K_TOKENS = 0.2;   // Wh per 1000 tokens
CO2G_PER_1K_TOKENS = 0.1;        // gram CO₂e per 1000 tokens
```

---

## 13. Sandbox-isolering

### Domän-nivå

Varje compare-domän kan köras i isolerad sandbox (K8s pod / Docker container):

```python
_sandbox_active = bool(sandbox_enabled)

# Per domän:
lease = await _acquire_sandbox_for_domain(subagent_id, thread_id)
# ... kör modell-anrop ...
await _release_sandbox_for_domain(subagent_id, thread_id)
```

### Kriterium-nivå

Individuella kriterium-bedömare kan också isoleras (ej standard):

```python
pod_id = f"pod-crit-{domain}-{criterion}-{uuid}"
# Scope: "criterion" (jämfört med "subagent" för domäner)
```

### Konfiguration

- `sandbox_enabled=True`: Aktiverar sandbox per domän
- `sandbox_isolation_enabled`: Ytterligare opt-in för fullständig isolering
- Fallback: Non-blocking — om sandbox-lease misslyckas, kör ändå

---

## 14. Testning

### Befintliga tester

| Testfil | Relevans |
|---------|----------|
| `test_dispatcher_routing.py` | Testar `/compare`-prefix-detektion och Route.JAMFORELSE |
| `test_loop_fix_p4.py` | Testar P4-infrastruktur som compare bygger på |
| `test_prompt_template_registry.py` | Testar att compare-promptar registreras korrekt |
| `test_synthesizer_guardrail_regression.py` | Testar syntes-guardrails |

### Saknade tester

- **Ingen dedicerad compare-testfil** (t.ex. `test_compare_executor.py`)
- Kriterium-evaluator saknar unit tests
- Research worker saknar unit tests
- Frontend: Inga tester (generellt i projektet)

---

## 15. Framtida arbete

- Dedikerade enhetstester för `compare_executor.py`, `compare_criterion_evaluator.py`, `compare_research_worker.py`
- Dynamiska vikter (admin-konfigurerbara via prompt registry eller DB)
- Historisk poäng-jämförelse (trend-tracking per modell över tid)
- Modell-specifika system-promptar (anpassade per provider)
- Streaming av syntes-text (idag genereras allt innan det skickas)
- Utöka research-agent med fler sök-backends (Google, Bing)
- Per-fråga-typ viktning (faktafrågor → korrekthet viktigare, kreativa → djup viktigare)
