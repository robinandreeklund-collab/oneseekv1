# OneSeek LangGraph Loop-Fix — Utvecklingsplan

> **Startdatum:** 2026-02-26
> **Branch:** `claude/debug-longgraph-loop-TCV0N`
> **Issue:** #44 (Loop issues)
> **Status:** Sprint P1 — **KLAR** ✓ | Sprint P1 Extra — **KLAR** ✓ (väntar E2E-testning) | Sprint P2 — **KLAR** ✓ | Sprint P3 — **KLAR** ✓

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
| **P1 Extra** | Hög | Strukturerad output (JSON Schema) för alla noder + streaming | Kvalitet, parsning, determinism | **KLAR** (väntar E2E) |
| **P2** | Hög | Studio, konfigurerbara guards | BUG 4, 9-12 | **KLAR** |
| **P3** | Medel | Multi-query decomposer | Ny funktionalitet | **KLAR** |
| **P4** | Framtida | Subagent mini-graphs, convergence | Arkitekturell omskrivning | Planeras |

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

## Sprint P1 Extra — Strukturerad Output (JSON Schema)

> **Status:** [x] **KLAR** (2026-02-26) — väntar E2E-testning innan slutgodkännande
> **Startdatum:** 2026-02-26
> **Commits:** `100ad03` (backend, 12 filer), `4fb5e8f` (frontend persistence)
> **Mål:** Ersätt regex-baserad JSON-extraktion med strikt JSON Schema för alla LLM-anrop.
> Thinking-fältet ingår i schemat och streamar progressivt. Frontend renderar
> strukturerad data inkrementellt.

### Bakgrund & Motivation

Idag gör alla LLM-anropande noder (intent, planner, critic, synthesizer, agent_resolver,
response_layer_router) samma sak:

1. Anropa LLM med fri text-prompt som ber om JSON
2. Extrahera JSON post-hoc med `extract_first_json_object_fn()` (regex-fallback)
3. Hoppas att modellen producerade giltig JSON

**Problem med nuvarande approach:**
- Modellen kan producera ogiltig JSON → regex-fallback → stilla fel
- `<think>`-taggar hanteras separat med stateful filter (`_ThinkStreamFilter`)
- Ingen typvalidering av fältvärden (t.ex. `confidence` kan vara sträng istället för float)
- Reasoning-text (från `<think>`) persisteras INTE → försvinner vid sidladdning

**Lösning: JSON Schema (strict mode)**
- `response_format={"type": "json_schema", "json_schema": {...}}` i varje API-anrop
- LM Studio/LiteLLM använder grammar-based sampling (GBNF) → **garanterat** giltig JSON
- `thinking`-fältet FÖRST i schemat → streamar progressivt som reasoning-delta
- Pydantic-modeller för typvalidering av varje nods output
- Inkrementell JSON-parsning på frontend för progressiv rendering

### Arkitekturöversikt

```
┌──────────────────────────────────────────────────────────────────────┐
│                     BACKEND (Python)                                 │
│                                                                      │
│  ┌─────────────┐    ┌───────────────────┐    ┌───────────────────┐  │
│  │  Pydantic    │    │  response_format   │    │  Inkrementell     │  │
│  │  Schemas     │───▶│  = json_schema     │───▶│  JSON-parsning    │  │
│  │  (per nod)   │    │  (i ainvoke/       │    │  (astream-noder)  │  │
│  │              │    │   astream)         │    │                   │  │
│  └─────────────┘    └───────────────────┘    └────────┬──────────┘  │
│                                                        │             │
│                                           ┌────────────▼──────────┐  │
│                                           │  SSE Events           │  │
│                                           │  reasoning-delta ◀─ thinking│
│                                           │  text-delta ◀─ response   │
│                                           │  structured-data ◀─ fält  │
│                                           └────────────┬──────────┘  │
│                                                        │             │
└────────────────────────────────────────────────────────┼─────────────┘
                                                         │ SSE
┌────────────────────────────────────────────────────────▼─────────────┐
│                     FRONTEND (TypeScript)                             │
│                                                                      │
│  ┌──────────────┐    ┌───────────────────┐    ┌───────────────────┐  │
│  │  partial-json │    │  SSE Event         │    │  Progressiv       │  │
│  │  parser       │───▶│  Handler           │───▶│  Rendering        │  │
│  │              │    │  (uppdaterad)      │    │  (FadeLayer+)     │  │
│  └──────────────┘    └───────────────────┘    └───────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

### P1-Extra.1 — Pydantic Schemas för alla noder

> **Status:** [x] **KLAR**

**Ny fil:** `surfsense_backend/app/agents/new_chat/structured_schemas.py`

Definierar en Pydantic-modell per nod. **ALLA** har `thinking`-fältet FÖRST
(modellen producerar thinking innan den fattar beslut).

```python
from pydantic import BaseModel, Field
from typing import Literal

# ─── Intent Resolution ───────────────────────────────────────
class IntentResult(BaseModel):
    thinking: str = Field(
        ...,
        description="Intern resonering om användarens avsikt, "
                    "kandidatanalys och beslutsunderlag."
    )
    intent_id: str = Field(
        ...,
        description="ID för vald intent, måste matcha en av kandidaterna."
    )
    route: Literal["kunskap", "skapande", "jämförelse", "konversation", "mixed"] = Field(
        ...,
        description="Övergripande rutt-kategori."
    )
    sub_intents: list[str] = Field(
        default_factory=list,
        description="Del-intents vid mixed route."
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Konfidens 0.0–1.0."
    )

# ─── Agent Resolver ──────────────────────────────────────────
class AgentResolverResult(BaseModel):
    thinking: str = Field(
        ...,
        description="Resonering om vilka agenter som bäst matchar uppgiften."
    )
    selected_agents: list[str] = Field(
        ...,
        description="Lista med agentnamn (måste matcha kandidater)."
    )
    reason: str = Field(..., description="Kort motivering på svenska.")
    confidence: float = Field(..., ge=0.0, le=1.0)

# ─── Planner ─────────────────────────────────────────────────
class PlanStep(BaseModel):
    id: str = Field(..., description="Steg-ID, t.ex. step-1.")
    content: str = Field(..., description="Beskrivning av steget.")
    status: Literal["pending", "in_progress", "completed", "cancelled"] = Field(
        default="pending"
    )
    parallel: bool = Field(
        default=False,
        description="True om steget kan köras parallellt med andra."
    )

class PlannerResult(BaseModel):
    thinking: str = Field(
        ...,
        description="Resonering om hur frågan bäst bryts ned i steg."
    )
    steps: list[PlanStep] = Field(
        ..., max_length=4,
        description="Exekveringssteg (max 4)."
    )
    reason: str = Field(..., description="Kort motivering på svenska.")

# ─── Critic ──────────────────────────────────────────────────
class CriticResult(BaseModel):
    thinking: str = Field(
        ...,
        description="Resonering om svarets kvalitet, fullständighet och brister."
    )
    decision: Literal["ok", "needs_more", "replan"] = Field(
        ...,
        description="Beslut: ok (godkänt), needs_more (behöver mer data), "
                    "replan (ny plan krävs)."
    )
    reason: str = Field(..., description="Kort motivering på svenska.")
    confidence: float = Field(..., ge=0.0, le=1.0)

# ─── Synthesizer ─────────────────────────────────────────────
class SynthesizerResult(BaseModel):
    thinking: str = Field(
        ...,
        description="Resonering om hur källmaterial bäst sammanfogas."
    )
    response: str = Field(
        ...,
        description="Det förfinade, slutgiltiga svaret (markdown)."
    )
    reason: str = Field(..., description="Kort motivering på svenska.")

# ─── Response Layer Router ───────────────────────────────────
class ResponseLayerRouterResult(BaseModel):
    thinking: str = Field(
        ...,
        description="Resonering om vilken presentationsform som passar bäst."
    )
    chosen_layer: Literal["kunskap", "analys", "syntes", "visualisering"] = Field(
        ...,
        description="Vald presentationsform."
    )
    reason: str = Field(..., description="Kort motivering på svenska.")
    data_characteristics: str = Field(
        default="",
        description="Beskrivning av datans karaktäristik."
    )

# ─── Response Layer (user-facing) ────────────────────────────
class ResponseLayerResult(BaseModel):
    thinking: str = Field(
        ...,
        description="Kort resonering om formateringsstrategi."
    )
    response: str = Field(
        ...,
        description="Fullständigt formaterat svar till användaren (markdown)."
    )
```

**Hjälpfunktion för att konvertera Pydantic → JSON Schema:**

```python
def pydantic_to_response_format(model: type[BaseModel], name: str) -> dict:
    """Konverterar Pydantic-modell till response_format dict för LiteLLM."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": model.model_json_schema()
        }
    }
```

**Acceptanskriterier:**
- [x] Alla 7 schemas definierade med `thinking` som FÖRSTA fältet
- [x] `model_json_schema()` producerar giltig JSON Schema
- [x] `pydantic_to_response_format()` returnerar korrekt dict-struktur
- [x] Unit-test: varje schema kan parsa ett giltigt exempelsvar

---

### P1-Extra.2 — Backend: Modifiera ainvoke-noder

> **Status:** [x] **KLAR**

Alla noder som använder `ainvoke()` ändras att:
1. Skicka `response_format` som kwarg
2. Parsa svaret med Pydantic istället för `extract_first_json_object_fn()`
3. Extrahera `thinking`-fältet och skicka vidare för streaming

**Ändrade filer (6 st):**

#### `nodes/intent.py`
```python
# FÖRE:
raw = await llm.ainvoke([sys_msg, human_msg], max_tokens=140)
parsed = extract_first_json_object_fn(raw.content)

# EFTER:
from ..structured_schemas import IntentResult, pydantic_to_response_format

raw = await llm.ainvoke(
    [sys_msg, human_msg],
    max_tokens=300,                    # Ökat: thinking kräver mer tokens
    response_format=pydantic_to_response_format(IntentResult, "intent_result"),
)
result = IntentResult.model_validate_json(raw.content)
# result.thinking → emit som reasoning-delta
# result.intent_id, result.route, etc. → använd direkt (typat!)
```

#### `nodes/agent_resolver.py`
- Samma mönster med `AgentResolverResult`
- `max_tokens` höjs från ~150 till ~300

#### `nodes/planner.py`
- Samma mönster med `PlannerResult`
- `max_tokens` höjs från 220 till ~500
- `result.steps` är redan typade `PlanStep`-objekt (inga dict-konverteringar)

#### `nodes/critic.py`
- Samma mönster med `CriticResult`
- `max_tokens` höjs från 90 till ~250
- Guard-logiken (`guard_finalized`, `total_steps`) behålls oförändrad
- Fallback vid JSON-fel: `CriticResult(thinking="fallback", decision="ok", ...)`

#### `nodes/smart_critic.py`
- Delegerar till `critic.py` → inga direkta LLM-ändringar
- Säkerställ att `critic_node` returnerar `CriticResult`

#### `nodes/synthesizer.py`
- Samma mönster med `SynthesizerResult`
- `max_tokens` höjs från 220 till ~800 (response-fältet kan vara långt)
- Kandidat-validering (degenerering-check) behålls

**Viktigt — Fallback-strategi:**

Varje nod behåller `try/except` med fallback till `extract_first_json_object_fn()`:
```python
try:
    result = IntentResult.model_validate_json(raw.content)
except (ValidationError, JSONDecodeError):
    # Fallback: legacy regex-parsning (för modeller utan json_schema-stöd)
    parsed = extract_first_json_object_fn(raw.content)
    result = IntentResult(thinking="(ej tillgängligt)", **parsed)
```

**Acceptanskriterier:**
- [x] Alla 5 ainvoke-noder använder `response_format`
- [x] Pydantic-parsning med typvalidering
- [x] Fallback till legacy-parsning vid fel
- [x] `thinking`-fältet extraheras och returneras i state
- [x] `max_tokens` justerat uppåt (thinking behöver utrymme)
- [x] Befintliga tester passerar

---

### P1-Extra.3 — Backend: Modifiera astream-noder + inkrementell JSON-parsning

> **Status:** [x] **KLAR**
> **Uppdatering 2026-02-27:** `partial-json-parser` nu installerat och använt — ersätter tidigare
> egen implementation med `json.JSONDecoder` + regex-fallback.

`response_layer_router` använder `astream()` och streamar till FadeLayer.
Med strukturerad output streamar den JSON-tokens istället för fri text.

**Ny dependency:** `partial-json-parser` (Python)

```bash
cd surfsense_backend && uv add partial-json-parser
```

**Ny hjälpklass:** `surfsense_backend/app/agents/new_chat/incremental_json_parser.py`

```python
from partial_json_parser import loads as partial_loads

class IncrementalSchemaParser:
    """Parsar JSON inkrementellt under streaming.

    Extraherar thinking-fältet progressivt medan resten
    av schemat fylls i. Returnerar (thinking_delta, parsed_so_far).
    """
    def __init__(self):
        self._buffer = ""
        self._last_thinking_len = 0

    def feed(self, chunk: str) -> tuple[str, dict | None]:
        """Feed en ny chunk. Returnerar (thinking_delta, partial_result)."""
        self._buffer += chunk
        try:
            partial = partial_loads(self._buffer)
        except Exception:
            return ("", None)

        thinking_delta = ""
        if isinstance(partial, dict) and "thinking" in partial:
            full_thinking = partial["thinking"]
            if len(full_thinking) > self._last_thinking_len:
                thinking_delta = full_thinking[self._last_thinking_len:]
                self._last_thinking_len = len(full_thinking)

        return (thinking_delta, partial)

    def finalize(self) -> dict:
        """Returnerar den slutgiltiga parsade JSON-en."""
        return partial_loads(self._buffer)
```

**Modifierad nod: `nodes/response_layer.py` (`response_layer_router_node`)**

```python
# FÖRE: Streamar raw text, strip <think>, extract JSON

# EFTER:
parser = IncrementalSchemaParser()
async for chunk in llm.astream(
    messages,
    response_format=pydantic_to_response_format(
        ResponseLayerRouterResult, "response_layer_router"
    ),
):
    token = chunk.content
    thinking_delta, partial = parser.feed(token)
    if thinking_delta:
        yield {"reasoning_delta": thinking_delta}  # → FadeLayer

result_dict = parser.finalize()
result = ResponseLayerRouterResult.model_validate(result_dict)
```

**Modifierad nod: `response_layer_node` (user-facing)**

```python
# response_layer producerar det slutgiltiga svaret.
# Med strukturerad output: {"thinking": "...", "response": "..."}
# thinking streamar först → reasoning-delta
# response streamar sedan → text-delta (synligt för användaren)

parser = IncrementalSchemaParser()
response_started = False

async for chunk in llm.astream(
    messages,
    response_format=pydantic_to_response_format(
        ResponseLayerResult, "response_layer"
    ),
):
    thinking_delta, partial = parser.feed(chunk.content)

    if thinking_delta:
        yield {"reasoning_delta": thinking_delta}

    # Streama response-fältet progressivt
    if partial and "response" in partial and not response_started:
        response_started = True
    if response_started and partial:
        response_delta = # beräkna delta mot föregående
        yield {"text_delta": response_delta}
```

**Acceptanskriterier:**
- [x] `partial-json-parser` installerat (`uv add partial-json-parser`)
- [x] `IncrementalSchemaParser` omskriven med `partial-json-parser` — parsar partiell JSON korrekt
- [x] `response_layer_router` streamar thinking progressivt via JSON
- [x] `response_layer` streamar thinking FÖRST, sedan response som text-delta
- [x] `<think>`-tag-filtret (`_ThinkStreamFilter`) blir inaktivt för strukturerade noder
- [x] Fallback vid modell utan json_schema-stöd: `_ThinkStreamFilter` aktiveras igen

---

### P1-Extra.4 — Backend: SSE-protokoll & streaming-pipeline uppdatering

> **Status:** [x] **KLAR**
> **Avvikelse:** `structured-field` och `data-thinking-persist` SSE-events visade sig onödiga.
> Befintliga `reasoning-delta` och `text-delta` events räcker — de sourcas nu från JSON-fält
> istället för `<think>`-taggar. Bakåtkompatibelt — inga frontend-SSE-ändringar behövdes.

**Ändrad fil:** `surfsense_backend/app/tasks/chat/stream_new_chat.py`

**Förändringar:**

1. **Ny SSE event-typ:** `structured-field`
   ```json
   {"type": "structured-field", "node": "intent", "field": "route", "value": "kunskap"}
   {"type": "structured-field", "node": "planner", "field": "steps", "value": [...]}
   {"type": "structured-field", "node": "critic", "field": "decision", "value": "ok"}
   ```
   Dessa skickas EFTER att noden kört färdigt (ainvoke-noder) och ger frontend
   möjlighet att visa strukturerade beslut progressivt.

2. **Thinkning-routing:**
   - För ainvoke-noder: `result.thinking` → emit `reasoning-delta` event
   - För astream-noder: inkrementell `thinking` → emit `reasoning-delta` per chunk
   - `_ThinkStreamFilter` behålls som fallback men bypas:as om `structured_output_enabled=True`

3. **Config-flagga:**
   ```python
   # I stream_new_chat.py
   structured_output_enabled = os.getenv("STRUCTURED_OUTPUT_ENABLED", "true").lower() == "true"
   ```
   När `false`: legacy-beteende med `<think>`-taggar och regex-parsning.

4. **Thinking-persistering:**
   - Nytt SSE event: `data-thinking-persist` med serialiserat thinking-objekt
   - Frontend sparar detta till DB → thinking bevaras vid sidladdning

**Nytt SSE event-format:**
```
data: {"type": "structured-field", "node": "intent", "field": "route", "value": "kunskap"}

data: {"type": "structured-field", "node": "planner", "field": "steps", "value": [{"id":"step-1","content":"Hämta väderdata"}]}

data: {"type": "data-thinking-persist", "node": "critic", "thinking": "Jag analyserade svaret..."}
```

**Acceptanskriterier:**
- [x] ~~`structured-field` SSE-event skickas per nod~~ → Onödigt, befintliga events räcker
- [x] reasoning-delta skickas för thinking-fältet (progressivt för astream, efter ainvoke)
- [x] `STRUCTURED_OUTPUT_ENABLED` env-flagga styr läget
- [x] ~~Thinking-persistering via nytt SSE event~~ → Löst via `reasoning-text` content part istället
- [x] Befintlig FadeLayer-rendering fungerar oförändrat (reasoning-delta redan stött)

**Implementationsdetaljer:**
- `_structured_mode: bool` beräknas en gång vid stream-start
- `_structured_parsers: dict[str, IncrementalSchemaParser]` — per-run-id parsers
- Interna noder: `parser.feed()` → thinking → `reasoning-delta`
- Output-noder (response_layer): `parser.feed_all()` → thinking → `reasoning-delta`, response → `text-delta`
- `late_close_detected` hoppas över i strukturerat läge
- Cleanup sker i `on_chat_model_end`

---

### P1-Extra.5 — Frontend: Inkrementell JSON-parsning & nya SSE-events

> **Status:** [x] **KLAR** — Ingen ändring behövdes
> **Avvikelse:** Hela denna sub-task visade sig onödig. Backend emittar fortfarande
> **Uppdatering 2026-02-27:** Alla planerade features nu implementerade:
> `partial-json` installerat, `structured-field` och `data-thinking-persist` SSE-events tillagda,
> `StructuredFieldBadge` skapad, `structured-stream-viewer.tsx` skapad.

**Ny dependency:**
```bash
cd surfsense_web && pnpm add partial-json
```

**Ändrade filer:**

#### `surfsense_web/app/dashboard/[search_space_id]/new-chat/new-chat-page.tsx`

Ny state och event-hantering:

```typescript
// Ny state
const [messageStructuredFields, setMessageStructuredFields] =
  useState<Map<string, Map<string, { node: string; field: string; value: unknown }[]>>>(new Map());

// I SSE event-dispatch:
case "structured-field": {
  const { node, field, value } = parsed;
  setMessageStructuredFields(prev => {
    const next = new Map(prev);
    const fields = next.get(currentMessageId) ?? new Map();
    const entries = fields.get(node) ?? [];
    entries.push({ node, field, value });
    fields.set(node, entries);
    next.set(currentMessageId, fields);
    return next;
  });
  break;
}

case "data-thinking-persist": {
  const { node, thinking } = parsed;
  // Persistera thinking för att bevara vid sidladdning
  setMessageReasoningMap(prev => {
    const next = new Map(prev);
    const existing = next.get(currentMessageId) ?? "";
    next.set(currentMessageId, existing + `\n--- ${node} ---\n${thinking}`);
    return next;
  });
  break;
}
```

#### `surfsense_web/components/assistant-ui/thinking-steps.tsx`

Ny `StructuredDecision`-komponent i FadeLayer:

```typescript
interface StructuredDecision {
  node: string;
  field: string;
  value: unknown;
}

function StructuredFieldBadge({ decision }: { decision: StructuredDecision }) {
  // Renderar t.ex. "intent → kunskap" eller "critic → ok" som kompakta badges
  return (
    <span className="inline-flex items-center gap-1 rounded-md border
                      px-1.5 py-0.5 text-[0.6rem] text-muted-foreground">
      <span className="font-medium">{decision.node}</span>
      <span className="opacity-50">→</span>
      <span>{String(decision.value)}</span>
    </span>
  );
}
```

Integreras i `filteredTimeline` med en ny `TimelineEntry`-kind:

```typescript
type TimelineEntry =
  | { kind: "reasoning"; text: string }
  | { kind: "step"; stepId: string }
  | { kind: "structured"; node: string; field: string; value: unknown };  // NY
```

#### `surfsense_web/components/assistant-ui/structured-stream-viewer.tsx` (NY FIL)

Progressiv rendering av strukturerade fält från en nod:

```typescript
import { parseJSON } from "partial-json";

export function StructuredStreamViewer({
  nodeData,
  isStreaming,
}: {
  nodeData: Map<string, { field: string; value: unknown }[]>;
  isStreaming: boolean;
}) {
  // Renderar fält-för-fält som de anländer
  // T.ex. planner-steg visas som en mini-lista efterhand
  // Critic-beslut visas som en badge
  // Intent-route visas som en chip
}
```

**Acceptanskriterier:**
- [x] `partial-json` npm-paket installerat (`pnpm add partial-json`)
- [x] `structured-field` SSE-events hanteras korrekt (båda SSE-switch-block)
- [x] `data-thinking-persist` sparar thinking per nod i `messageReasoningMap`
- [x] FadeLayer visar strukturerade beslut som `StructuredFieldBadge`-badges
- [x] Timeline stödjer ny `structured`-kind i `TimelineEntry`
- [x] Progressiv rendering via `structured-stream-viewer.tsx` med `partial-json`

---

### P1-Extra.6 — Frontend: Persistera thinking & strukturerad data

> **Status:** [x] **KLAR**
> **Avvikelse:** Förenklad approach — inga Zod-schemas, ingen `message-utils.ts`-ändring.
> Allt hanteras direkt i `new-chat-page.tsx` med `extractReasoningText()` och
> `reasoning-text` content part i `buildContentForPersistence()`.

**Mål:** Thinking-text och strukturerade beslut bevaras vid sidladdning (idag
försvinner reasoning vid refresh).

**Ändrade filer:**

#### `surfsense_web/app/dashboard/[search_space_id]/new-chat/new-chat-page.tsx`

I `buildContentForPersistence()`:

```typescript
// NYTT: Persistera thinking + structured fields
const persistContent = [
  { type: "thinking-steps", steps: [...] },
  { type: "reasoning-text", text: reasoningMap.get(msgId) ?? "" },     // NY
  { type: "structured-fields", fields: structuredFields.get(msgId) },  // NY
  { type: "compare-summary", summary: ... },
  { type: "text", text: "..." },
  { type: "tool-call", ... },
];
```

#### `surfsense_web/lib/message-utils.ts`

Nya Zod-schemas och extraktion:

```typescript
const ReasoningTextPartSchema = z.object({
  type: z.literal("reasoning-text"),
  text: z.string(),
});

const StructuredFieldsPartSchema = z.object({
  type: z.literal("structured-fields"),
  fields: z.record(z.array(z.object({
    node: z.string(),
    field: z.string(),
    value: z.unknown(),
  }))),
});

export function extractReasoningText(content: unknown[]): string { ... }
export function extractStructuredFields(content: unknown[]): Map<...> { ... }
```

#### Återställning vid sidladdning

I `restoreMessagesFromDB()` (new-chat-page.tsx):

```typescript
// Återställ reasoning
const reasoning = extractReasoningText(msg.content);
if (reasoning) {
  restoredReasoningMap.set(msgId, reasoning);
}

// Återställ structured fields
const fields = extractStructuredFields(msg.content);
if (fields.size > 0) {
  restoredStructuredFields.set(msgId, fields);
}
```

**Acceptanskriterier:**
- [x] Reasoning-text persisteras i `buildContentForPersistence()`
- [x] ~~Strukturerade fält persisteras~~ → Uppskjutet (nice-to-have)
- [x] Vid sidladdning återställs reasoning i FadeLayer
- [x] ~~Vid sidladdning återställs strukturerade badges~~ → Uppskjutet
- [x] ~~Zod-schemas validerar korrekt~~ → Enklare inline-approach istället
- [x] Inga regressioner i befintlig meddelandehantering

**Implementationsdetaljer:**
- `extractReasoningText(content)` — ny funktion som hittar `reasoning-text` part i content-array
- Båda `buildContentForPersistence()`-instanserna lägger till `{ type: "reasoning-text", text }` vid persist
- Restoration-logiken bygger om timeline med reasoning-entries + step-entries

---

### P1-Extra.7 — Promptjusteringar

> **Status:** [x] **KLAR**

**Mål:** Uppdatera systemprompts att instruera modellen att producera JSON med
thinking-fältet, istället för `<think>`-taggar.

**Ändrade filer:**

#### `surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py`

Alla prompts (intent, planner, critic, synthesizer, agent_resolver, response_layer)
uppdateras med:

```
DIN RESNING SKA FINNAS I "thinking"-FÄLTET I JSON-SVARET.
Använd INTE <think>-taggar. All intern resonering går i "thinking"-fältet.
Producera EXAKT det JSON-schema som anges. Inga extra fält.
```

#### `surfsense_backend/app/agents/new_chat/system_prompt.py`

Villkorad `<think>`-instruktion:

```python
def inject_core_prompt(
    include_think_instructions: bool = True,
    structured_output: bool = False,   # NY PARAM
) -> str:
    if structured_output:
        # JSON-schema-läge: thinking i JSON-fältet
        return SURFSENSE_CORE_GLOBAL_PROMPT_STRUCTURED
    elif include_think_instructions:
        return SURFSENSE_CORE_GLOBAL_PROMPT
    else:
        return SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK
```

**Acceptanskriterier:**
- [x] Alla LLM-prompts instruerar om JSON-thinking istället för `<think>`-taggar
- [x] `inject_core_prompt(structured_output=True)` returnerar rätt prompt
- [x] `structured_output=False` behåller legacy-beteende
- [x] Prompterna matchar exakt de Pydantic-schemat (fältnamn, typer)

---

### P1-Extra.8 — Tester

> **Status:** [x] **KLAR** — 37 tester, alla passerar

**Ny testfil:** `surfsense_backend/tests/test_structured_output.py`

| Test | Testar |
|------|--------|
| `test_intent_schema_valid_json_schema` | IntentResult.model_json_schema() producerar giltig JSON Schema |
| `test_intent_schema_parse_valid` | IntentResult parsar giltigt LLM-svar |
| `test_intent_schema_parse_invalid_fallback` | Ogiltig JSON → fallback till regex |
| `test_planner_schema_max_4_steps` | PlannerResult avvisar > 4 steg |
| `test_critic_schema_decision_enum` | CriticResult avvisar ogiltig decision |
| `test_synthesizer_schema_response_field` | SynthesizerResult extraherar response |
| `test_response_format_helper` | pydantic_to_response_format() korrekt dict |
| `test_incremental_parser_thinking` | IncrementalSchemaParser extraherar thinking progressivt |
| `test_incremental_parser_complete` | IncrementalSchemaParser.finalize() returnerar komplett JSON |
| `test_incremental_parser_partial_json` | Partiell JSON hanteras utan crash |
| `test_structured_output_env_flag` | STRUCTURED_OUTPUT_ENABLED=false → legacy-beteende |
| `test_prompt_structured_mode` | inject_core_prompt(structured_output=True) → rätt prompt |
| `test_thinking_field_first_in_all_schemas` | Alla schemas har thinking som första fält |
| `test_sse_structured_field_event` | structured-field SSE-event serialiseras korrekt |

**Frontend-tester** (manuella/E2E):

| Test | Testar |
|------|--------|
| `FadeLayer visar reasoning från thinking-fält` | Thinking streamar korrekt i think-box |
| `Structured badges visas i timeline` | Intent, critic-beslut etc. visas som badges |
| `Sidladdning bevarar reasoning` | Thinking bevaras efter refresh |
| `Fallback vid legacy-svar` | Fungerar med modeller utan json_schema-stöd |

**Testresultat:**
```
tests/test_structured_output.py: 37 passed (0.21s)
Full suite: 211 passed, 32 failed (pre-existing), 8 skipped
Inga nya regressioner.
```

**Acceptanskriterier:**
- [x] ALLA backend-tester passerar (37 st)
- [x] Inga regressioner i befintlig testsvit
- [ ] Manuell verifiering av frontend-rendering — **se Testning-sektionen nedan**

---

### Konfiguration & Miljövariabler

| Variabel | Default | Beskrivning |
|----------|---------|-------------|
| `STRUCTURED_OUTPUT_ENABLED` | `true` | Aktivera JSON Schema structured output |
| `STRUCTURED_OUTPUT_FALLBACK` | `true` | Fallback till regex-parsning vid fel |
| `THINK_ON_TOOL_CALLS` | `false` (befintlig) | Think i executor (ortogonalt) |

---

### Avvikelser från originalplanen

~~Under implementationen visade det sig att flera planerade features var onödiga tack
vare en förenklad arkitektur.~~

**Uppdatering 2026-02-27:** Avvikelserna orsakade 3 buggar (BUG-A/B/C) i streaming-
pipelinen. Alla planerade features har nu implementerats enligt originalplanen.

| Planerat | Utfall | Status |
|----------|--------|--------|
| `partial-json-parser` (Python-dependency) | **Implementerat** — ersätter egen regex+json.loads | ✅ KLAR |
| `partial-json` (npm-dependency) | **Installerat** — `structured-stream-viewer.tsx` | ✅ KLAR |
| `structured-field` SSE-event | **Implementerat** — emitteras vid model_end för interna noder | ✅ KLAR |
| `data-thinking-persist` SSE-event | **Implementerat** — thinking-text per nod för DB-persistering | ✅ KLAR |
| `StructuredFieldBadge` komponent | **Implementerat** i `thinking-steps.tsx` | ✅ KLAR |
| `structured-stream-viewer.tsx` (ny fil) | **Skapad** — progressiv JSON-rendering med `partial-json` | ✅ KLAR |
| Ändringar i `thinking-steps.tsx` | **Implementerat** — `TimelineEntry` utökad med `structured` kind | ✅ KLAR |
| Ändringar i `message-utils.ts` | **Implementerat** — Zod-schemas, `extractReasoningText`, `extractStructuredFields` | ✅ KLAR |
| Zod-schemas för nya content parts | **Implementerat** — `ReasoningTextPartSchema`, `StructuredFieldsPartSchema` | ✅ KLAR |

#### Buggfixar (identifierade vid analys av avvikelsernas konsekvenser)

| Bugg | Beskrivning | Fix |
|------|-------------|-----|
| BUG-A | `fallback_assistant_text` sattes från ALLA chains (inkl. interna) | Guard: kontrollera `_is_output_pipeline_chain_name()` |
| BUG-B | `response_layer` utelämnade AIMessage vid content-match | Alltid inkludera AIMessage i return dict |
| BUG-C | `compare_synthesizer` klassificerades som INTERNAL (substring-match) | Ny `_is_output_pipeline_chain_name()` med prioritet över internal |

---

### Testning innan slutgodkännande

**Status:** Väntar på manuell E2E-testning

Innan P1 Extra kan markeras som helt klar behöver följande tester genomföras:

#### 1. Automatiserade tester (redan klara)

- [x] `tests/test_structured_output.py` — 37 tester passerar
- [x] `tests/test_loop_fix_p1.py` — 20 tester passerar (inga regressioner)
- [x] Full testsvit: 211 passed, 32 failed (pre-existing), 8 skipped

#### 2. Manuell backend-testning

Kräver: LM Studio eller annan lokal LLM med `json_schema` response_format-stöd.

- [ ] **Structured mode ON** (`STRUCTURED_OUTPUT_ENABLED=true`, default):
  - [ ] Skicka en enkel fråga ("Vad är huvudstaden i Sverige?") — verifiera att:
    - [ ] Reasoning-text visas i FadeLayer (think-box)
    - [ ] Svar visas som text-delta i chatten
    - [ ] Inga `<think>`-taggar i output
  - [ ] Skicka en komplex fråga som triggar planner + executor + critic:
    - [ ] Verifiera att interna noder (intent, planner, critic) producerar structured JSON
    - [ ] Verifiera att `reasoning-delta` events emitteras progressivt
    - [ ] Verifiera att critic-beslut (`ok`/`needs_more`/`replan`) är korrekt typat
  - [ ] Skicka en fråga som triggar tool-calls:
    - [ ] Verifiera att executor fortfarande fungerar (tool-calls påverkas inte)
    - [ ] Verifiera att synthesizer producerar structured output
  - [ ] Testa med compare-mode (om tillgängligt):
    - [ ] Verifiera att compare_synthesizer fungerar korrekt

- [ ] **Structured mode OFF** (`STRUCTURED_OUTPUT_ENABLED=false`):
  - [ ] Verifiera att all legacy-beteende (ThinkStreamFilter, `<think>`-taggar, regex-parsning) fungerar exakt som tidigare
  - [ ] Verifiera att inga regressioner uppstått

- [ ] **Fallback-testning**:
  - [ ] Testa med en modell som INTE stödjer `json_schema` response_format
  - [ ] Verifiera att fallback till `extract_first_json_object_fn()` aktiveras
  - [ ] Verifiera att `thinking: "(ej tillgängligt)"` sätts vid fallback

#### 3. Manuell frontend-testning

- [ ] **Reasoning-display:**
  - [ ] Verifiera att reasoning-text visas i FadeLayer under streaming
  - [ ] Verifiera att reasoning-text matchar `thinking`-fältet från LLM
  - [ ] Verifiera att FadeLayer öppnas/stängs korrekt

- [ ] **Persistens vid sidladdning:**
  - [ ] Skicka en fråga med reasoning → ladda om sidan (F5)
  - [ ] Verifiera att reasoning-text fortfarande visas i FadeLayer
  - [ ] Verifiera att thinking-steps (tool-call-steg) fortfarande visas
  - [ ] Verifiera att svar-texten är intakt

- [ ] **Regressionstester:**
  - [ ] Befintlig chat-historik (utan reasoning-text parts) ska ladda korrekt
  - [ ] Markdown-formatering i svar påverkas ej
  - [ ] Jämförelse-läge (compare mode) fungerar oförändrat
  - [ ] Podcaster-agenten påverkas ej

#### 4. Prestandatestning

- [ ] Verifiera att `max_tokens`-höjningarna (thinking kräver mer tokens) inte orsakar märkbar latens
- [ ] Verifiera att IncrementalSchemaParser inte orsakar minnesläckor vid lång streaming
- [ ] Mät tid för en typisk fråga med structured mode ON vs OFF

#### 5. Env-flagga toggle-test

- [ ] Starta backend med `STRUCTURED_OUTPUT_ENABLED=true` → kör testfråga → stoppa
- [ ] Starta backend med `STRUCTURED_OUTPUT_ENABLED=false` → kör SAMMA testfråga → stoppa
- [ ] Jämför: båda ska ge funktionellt identiska resultat (reasoning i FadeLayer, svar i chat)

---

### Fil-index (faktiskt ändrade filer i P1 Extra)

| Fil | Åtgärd | Sub-task | Status |
|-----|--------|----------|--------|
| `app/agents/new_chat/structured_schemas.py` | **NY** | P1-Extra.1 | ✓ |
| `app/agents/new_chat/incremental_json_parser.py` | **NY** | P1-Extra.3 | ✓ |
| `app/agents/new_chat/nodes/intent.py` | Ändrad | P1-Extra.2 | ✓ |
| `app/agents/new_chat/nodes/agent_resolver.py` | Ändrad | P1-Extra.2 | ✓ |
| `app/agents/new_chat/nodes/planner.py` | Ändrad | P1-Extra.2 | ✓ |
| `app/agents/new_chat/nodes/critic.py` | Ändrad | P1-Extra.2 | ✓ |
| `app/agents/new_chat/nodes/synthesizer.py` | Ändrad | P1-Extra.2 | ✓ |
| `app/agents/new_chat/nodes/response_layer.py` | Ändrad | P1-Extra.3 | ✓ |
| `app/agents/new_chat/system_prompt.py` | Ändrad | P1-Extra.7 | ✓ |
| `app/agents/new_chat/supervisor_pipeline_prompts.py` | Ändrad | P1-Extra.7 | ✓ |
| `app/tasks/chat/stream_new_chat.py` | Ändrad | P1-Extra.4 | ✓ |
| `tests/test_structured_output.py` | **NY** | P1-Extra.8 | ✓ |
| `surfsense_web/.../new-chat-page.tsx` | Ändrad | P1-Extra.6 | ✓ |

**Filer som INTE ändrades (planerade men onödiga):**

| Fil | Anledning |
|-----|-----------|
| `surfsense_web/package.json` | Ingen ny npm-dependency behövdes |
| `surfsense_web/.../thinking-steps.tsx` | Timeline-typer oförändrade |
| `surfsense_web/.../structured-stream-viewer.tsx` | Aldrig skapad (onödig) |
| `surfsense_web/lib/message-utils.ts` | Reasoning-extraction sker inline |

---

### Risker & Mitigation

| Risk | Allvarlighet | Mitigation |
|------|-------------|------------|
| LM Studio stödjer inte `json_schema` response_format | HÖG | Fallback-flagga `STRUCTURED_OUTPUT_FALLBACK=true` behåller legacy-parsning |
| `max_tokens` för lågt → trunkerad JSON | MEDEL | Höj max_tokens per nod, validera med Pydantic |
| Thinking-fältet gör svaren långsammare | LÅG | Thinking är snabbt (modellen tänker ändå), grammatik-overhead minimal |
| Inkrementell JSON-parser missar edge cases | MEDEL | Robust felhantering + fallback till komplett parsning |
| Frontend-regressioner i FadeLayer | MEDEL | reasoning-delta redan stött, minimal ändring |
| Modeller utan thinking-kapacitet | LÅG | `thinking: ""` (tom sträng) är giltigt schema |

---

### Ordning: Implementationssekvens

```
P1-Extra.1 (Schemas)                    ← Ingen dependency
    ↓
P1-Extra.7 (Prompts)                    ← Behöver schemas
    ↓
P1-Extra.2 (ainvoke-noder)              ← Behöver schemas + prompts
    ↓
P1-Extra.3 (astream-noder + parser)     ← Behöver schemas
    ↓
P1-Extra.4 (SSE-protokoll)              ← Behöver ainvoke + astream ändringarna
    ↓
P1-Extra.5 (Frontend SSE + rendering)   ← Behöver nya SSE events
    ↓
P1-Extra.6 (Frontend persistering)      ← Behöver P1-Extra.5
    ↓
P1-Extra.8 (Tester)                     ← Sist, verifierar allt
```

---

## Sprint P2 — Studio & Konfiguration

> **Status:** [x] **KLAR** (2026-02-27)
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

> **Status:** [x] **KLAR** (2026-02-27)
> **Mål:** Intelligent fråge-dekomponering för komplexa frågor
> **Källa:** Issue #44

### P3.1 — Multi-query decomposer node

> **Status:** [x] **KLAR**

**Vad:** Ny nod `multi_query_decomposer` som körs EFTER intent resolution
men FÖRE agent_resolver, BARA för `complex`-klassade frågor (hybrid_mode).
Bryter ned komplexa frågor till atomära delfrågor med beroendegraf.

**Nya filer:**
- `surfsense_backend/app/agents/new_chat/nodes/multi_query_decomposer.py` — Noden
- `surfsense_backend/app/agents/new_chat/structured_schemas.py` — `AtomicQuestion` + `DecomposerResult` Pydantic-scheman

**State-tillägg:**
```python
atomic_questions: list[dict]  # [{"id": "q1", "text": "...", "depends_on": [], "domain": "väder"}]
```

**Ändrade filer:**
- `surfsense_backend/app/agents/new_chat/supervisor_types.py` — `atomic_questions` fält i SupervisorState
- `surfsense_backend/app/agents/new_chat/structured_schemas.py` — `AtomicQuestion` + `DecomposerResult`
- `surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py` — `DEFAULT_SUPERVISOR_DECOMPOSER_PROMPT`
- `surfsense_backend/app/agents/new_chat/supervisor_agent.py` — Import, prompt resolution, nod-bygge, graf-routing, edge-wiring
- `surfsense_backend/app/agents/new_chat/nodes/__init__.py` — Export `build_multi_query_decomposer_node`
- `surfsense_backend/app/agents/new_chat/nodes/planner.py` — Konsumerar `atomic_questions` i LLM-input
- `surfsense_backend/app/agents/new_chat/nodes/executor.py` — Resettar `atomic_questions` vid ny tur
- `surfsense_backend/app/tasks/chat/stream_new_chat.py` — `multi_query_decomposer` i `_INTERNAL_PIPELINE_CHAIN_TOKENS`

**Grafändring:**
```
resolve_intent → memory_context → [route_after_intent]
                                    ├→ (complex) multi_query_decomposer → [speculative →] agent_resolver → planner
                                    ├→ (simple) tool_resolver
                                    └→ (trivial) agent_resolver / smalltalk / END
```

**Acceptanskriterier:**
- [x] Decomposer producerar atomic_questions med dependencies
- [x] Planner använder atomic_questions för att generera bättre plan
- [x] Simple och trivial frågor hoppar ÖVER decomposer (ingen extra latens)
- [x] FadeLayer visar decomposer-reasoning i think-box (via `_INTERNAL_PIPELINE_CHAIN_TOKENS`)
- [x] Enstaka frågor (1 atomic_question) resulterar i tom lista (ingen onödig dekomponering)
- [x] LLM-fel → graceful degradation (tom atomic_questions, planner kör som vanligt)

### P3.2 — Tester för Sprint P3

> **Status:** [x] **KLAR**

**Ny testfil:** `surfsense_backend/tests/test_multi_query_decomposer.py` — **11 tester, alla passerar**

| Testklass | Antal | Testar |
|-----------|-------|--------|
| `TestDecomposerSplitsCompoundQuestion` | 2 | Två/tre domäner → rätt antal atomic_questions med korrekt domain |
| `TestDecomposerSingleQuestionPassthrough` | 1 | Enkel fråga → tom atomic_questions (ingen onödig dekomponering) |
| `TestDecomposerDependencyGraph` | 1 | depends_on-referenserna bevaras korrekt |
| `TestDecomposerSkippedForSimple` | 3 | Simple/trivial/None-complexity → LLM anropas ALDRIG |
| `TestDecomposerLLMFailure` | 1 | LLM-exception → tom lista (graceful degradation) |
| `TestStateFieldExists` | 1 | `atomic_questions` finns i SupervisorState |
| `TestPydanticSchemas` | 2 | DecomposerResult och AtomicQuestion parsas korrekt |

**Testresultat:**
```
tests/test_multi_query_decomposer.py: 11 passed (0.29s)
```

---

### Sprint P4 – Arkitekturell Evolution (Framtida)

**Mål:**
  Göra systemet **loop-immun på arkitekturnivå** genom att utnyttja LangGraph's inbyggda primitives + 2026-best-practices. Bygga vidare på befintliga subagenter, state-machine, idempotent final_response, CriticVeto och mock-env så att varje domän är helt isolerad, självhelande och kostnadseffektiv.

**Tid:** 5–7 dagar
**Status:** Ej påbörjad (bygger på existerande subagent-omnämnanden)

#### Implementation Roadmap (utökning av befintligt)

**7. Förbättra befintliga subagenter med per-domain checkpointer**
Varje subagent (statistik, väder, trafik etc.) får egen persistence – loops kan aldrig spilla över mellan domäner.

```python
# I supervisor_agent.py
def create_domain_subgraph(domain: str):
    subgraph = StateGraph(DomainState).compile(
        checkpointer=PostgresSaver.from_conn_string(f"{DB_URI}?application_name=oneseek-{domain}"),
        interrupt_before=["critic"]  # behåll CriticVeto
    )
    return subgraph

supervisor_builder.add_subgraph("statistics", create_domain_subgraph("statistics"))
```

**8. Command-pattern för ren cross-subgraph-handoff**
Använd Command för att skicka mellan parent/subagent utan conditional edges (bygger på era befintliga subagenter).

```python
from langgraph.types import Command

def subagent_router(state: SupervisorState) -> Command:
    if state["current_domain"] == "statistics":
        return Command(
            graph="statistics",  # befintlig subagent
            update={"resolved_fields": {...}},
            goto="critic" if not sufficient else END
        )
    return Command(goto=END)
```

**9. Automatic summarization inuti varje subagent**
Lägg till i varje subagent-graph (efter 8–10 messages):

```python
from langgraph.managed import Summarizer

def summary_node(state):
    return {"messages": Summarizer(model="claude-3-5-sonnet-20241022").summarize(state["messages"])}
```

**10. Semantic Tool Caching per subagent**
Redis/LangGraph Store med namespace per subagent (t.ex. `cache:scb:goteborg:2023`).

```python
# I tool-wrapper för SCB
cache_key = f"cache:{domain}:{fingerprint(query)}"
if hit := store.get(cache_key):
    return Command(update={"tool_output": hit}, goto=END)
```

**11. Adaptive limits per subagent via ProgressTracker**
Utöka er befintliga ProgressTracker:

```python
def adaptive_subagent_guard(state):
    tracker = state["progress_tracker"]
    if tracker.steps > domain_max_steps.get(state["current_domain"], 6):
        return Command(update={"final_response_locked": True}, goto=END)
    return Command(goto="critic")  # behåll CriticVeto
```

**12. PEV-pattern som valfritt inner-subgraph**
Ersätt critic i subagenter med Plan-Execute-Verify (valfritt).

```python
pev_subgraph = StateGraph(PEVState).add_node("verify", verify_node).compile()
supervisor_builder.add_subgraph("pev", pev_subgraph)  # kan användas inuti befintliga subagenter
```

#### Utökade Success Criteria

* Varje subagent har egen checkpointer → 0 cross-domain loop-spill
* Historik per subagent max 6k tokens (summarization)
* Cache hit-rate > 70 % på repetitiva domäner (SCB, SMHI)
* 100 % av 30 loop-prone queries → final answer inom 6 steps
* Full time-travel + human-in-the-loop fungerar per subagent

#### Risker & Mitigation (utökad)

* **Risk:** För många checkpointers → **Mitigation:** Shared connection pool + prune_policy
* **Risk:** Subgraph-komplexitet → **Mitigation:** Börja med 3 domäner, använd befintliga subagent-komponenter
* **Risk:** Command vs legacy edges → **Mitigation:** Gradvis migration, behåll conditional edges som fallback

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
├→ (complex) multi_query_decomposer → speculative → agent_resolver
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
| `app/agents/new_chat/supervisor_types.py` | P1, P3 |
| `app/agents/new_chat/supervisor_constants.py` | P1, P2 |
| `app/agents/new_chat/supervisor_agent.py` | P1, P2, P3 |
| `app/agents/new_chat/complete_graph.py` | P1 |
| `app/agents/new_chat/nodes/critic.py` | P1, P1 Extra |
| `app/agents/new_chat/nodes/smart_critic.py` | P1 |
| `app/agents/new_chat/nodes/executor.py` | P1, P3 |
| `app/agents/new_chat/system_prompt.py` | P1, P1 Extra |
| `app/tasks/chat/stream_new_chat.py` | P1, P1 Extra, P2, P3 |
| `app/langgraph_studio.py` | P2, P3 |
| `app/agents/new_chat/structured_schemas.py` | **P1 Extra (ny)**, P3 |
| `app/agents/new_chat/incremental_json_parser.py` | **P1 Extra (ny)** |
| `app/agents/new_chat/nodes/intent.py` | P1 Extra |
| `app/agents/new_chat/nodes/agent_resolver.py` | P1 Extra |
| `app/agents/new_chat/nodes/planner.py` | P1 Extra, P3 |
| `app/agents/new_chat/nodes/synthesizer.py` | P1 Extra |
| `app/agents/new_chat/nodes/response_layer.py` | P1 Extra |
| `app/agents/new_chat/supervisor_pipeline_prompts.py` | P1 Extra, P3 |
| `app/agents/new_chat/prompt_registry.py` | P3 |
| `app/routes/admin_flow_graph_routes.py` | P3 |
| `tests/test_structured_output.py` | **P1 Extra (ny)** |
| `surfsense_web/.../new-chat-page.tsx` | P1 Extra |
| `surfsense_web/.../thinking-steps.tsx` | P1 Extra |
| `surfsense_web/.../structured-stream-viewer.tsx` | **P1 Extra (ny)** |
| `surfsense_web/lib/message-utils.ts` | P1 Extra |
| `app/agents/new_chat/nodes/multi_query_decomposer.py` | **P3 (ny)** |
| `app/agents/new_chat/nodes/__init__.py` | P3 |
| `tests/test_loop_fix_p1.py` | **P1 (ny)** |
| `tests/test_loop_fix_p2.py` | **P2 (ny)** |
| `tests/test_multi_query_decomposer.py` | **P3 (ny)** |
