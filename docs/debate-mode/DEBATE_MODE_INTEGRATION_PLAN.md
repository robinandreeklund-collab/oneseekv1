# Debattläge v1 — Komplett Integrationsplan

> **Issue:** [#48 — \[FEATURE\] debatt](https://github.com/robinandreeklund-collab/oneseekv1/issues/48)
> **Datum:** 2026-03-01
> **Status:** Planering & Mockups
> **Baserat på:** `/compare` (Spotlight Arena) — P4 Hybrid Supervisor v2

---

## 1. Sammanfattning

Debattläge är en ny interaktionsmod i OneSeek där **7–9 AI-deltagare** (6–8 externa modeller + OneSeek) engagerar sig i en **flerrundig, naturlig diskussion** kring ett användargivet ämne. Till skillnad från `/compare` (som kör alla modeller parallellt med samma fråga och rankar dem) skapar Debattläge en **sekventiell konversationskedja** där varje deltagare ser och bygger på vad föregående deltagare sagt.

### Jämförelse: Compare vs Debatt

| Dimension | `/compare` (Spotlight Arena) | `/debatt` (Debate Arena) |
|-----------|------------------------------|--------------------------|
| Modell-interaktion | Parallellt, isolerat | Sekventiellt per runda, kedjad kontext |
| Antal rundor | 1 (fan-out → convergence) | 4 (intro → argument × 2 → röstning) |
| Ordning | Deterministisk (alla samtidigt) | Slumpmässig per runda |
| Bedömning | 4 kriterier (relevans/djup/klarhet/korrekthet) | Deltagarröstning + ordräkning tiebreaker |
| OneSeek-roll | Research-agent (faktakontroll) | Jämställd debattör med P4-subagent |
| Resultatvy | Ranked scorecards + analysis | Podcastpresentation med waveform |
| Backend-graf | compare_executor subgraph | debate_supervisor subgraph |
| Frontend-komponent | `spotlight-arena.tsx` | `debate-arena.tsx` (ny) |

---

## 2. Arkitektur — Teknisk Integrationsöversikt

### 2.1 Backend — LangGraph Subgraf

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEBATE SUPERVISOR SUBGRAPH                    │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │ debate_init  │───▶│         ROUND 1: Introduktion        │   │
│  │  (setup +    │    │  random_order() → sequential_chain   │   │
│  │   shuffle)   │    │  model[0]: query + intro_prompt      │   │
│  └──────────────┘    │  model[1..N]: query + full_chain     │   │
│                      └──────────────┬───────────────────────┘   │
│                                     │                           │
│                      ┌──────────────▼───────────────────────┐   │
│                      │      ROUND 2: Argument (debate)      │   │
│                      │  new_random_order() → sequential     │   │
│                      │  model[0]: prior_rounds + query      │   │
│                      │  model[1..N]: prior + chain          │   │
│                      └──────────────┬───────────────────────┘   │
│                                     │                           │
│                      ┌──────────────▼───────────────────────┐   │
│                      │      ROUND 3: Fördjupning            │   │
│                      │  new_random_order() → sequential     │   │
│                      │  (samma mönster som runda 2)         │   │
│                      └──────────────┬───────────────────────┘   │
│                                     │                           │
│                      ┌──────────────▼───────────────────────┐   │
│                      │      ROUND 4: Röstning               │   │
│                      │  PARALLEL fan-out (alla samtidigt)   │   │
│                      │  enforced JSON schema per modell     │   │
│                      │  self-vote filter + word tiebreaker  │   │
│                      └──────────────┬───────────────────────┘   │
│                                     │                           │
│                      ┌──────────────▼───────────────────────┐   │
│                      │    debate_results_aggregator         │   │
│                      │  vote_count + tiebreaker + winner    │   │
│                      │  → podcast_presentation_tool         │   │
│                      └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 OneSeek Debate Subagent (P4-mönster)

OneSeek deltar som jämställd debattör men med verktygsstöd via P4-arkitekturen:

```
┌───────────────────────────────────────────────────────┐
│              ONESEEK DEBATE SUBAGENT                   │
│                                                       │
│  ┌─────────────┐                                      │
│  │ Mini-Planner │─── structured JSON plan             │
│  └──────┬──────┘                                      │
│         │                                             │
│  ┌──────▼──────────────────────────────────────┐      │
│  │     6 Parallella Mini-Agenter (pods)        │      │
│  │  ┌────────┐ ┌────────┐ ┌──────────────┐    │      │
│  │  │ Tavily │ │ Fresh  │ │   Counter-   │    │      │
│  │  │ Core   │ │ News   │ │   Evidence   │    │      │
│  │  └────────┘ └────────┘ └──────────────┘    │      │
│  │  ┌────────┐ ┌────────┐ ┌──────────────┐    │      │
│  │  │Swedish │ │  Fact   │ │   Clarity    │    │      │
│  │  │Context │ │ Consol. │ │   Agent      │    │      │
│  │  └────────┘ └────────┘ └──────────────┘    │      │
│  └──────────────────┬─────────────────────────┘      │
│                     │                                 │
│  ┌──────────────────▼──────────────────────┐          │
│  │ Mini-Critic → structured JSON verdict   │          │
│  └──────────────────┬──────────────────────┘          │
│                     │                                 │
│  ┌──────────────────▼──────────────────────┐          │
│  │ Final Synthesizer → natural text output │          │
│  └─────────────────────────────────────────┘          │
│                                                       │
│  Constraints: max 4 Tavily calls, context offload     │
└───────────────────────────────────────────────────────┘
```

### 2.3 Frontend — Komponenthierarki

```
┌─────────────────────────────────────────────────────┐
│                   DebateArena                        │
│  (motsvarar SpotlightArena för /compare)            │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │  DebateHeader                               │     │
│  │  - Ämne/fråga                               │     │
│  │  - Antal deltagare                          │     │
│  │  - Aktuell runda (1-4)                      │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │  DebateRoundView                            │     │
│  │  ┌─────────────────────────────────────┐    │     │
│  │  │  ParticipantCard (per deltagare)    │    │     │
│  │  │  - Modell-logo + namn              │    │     │
│  │  │  - Argument-text (streaming)       │    │     │
│  │  │  - Ordräkning + latency            │    │     │
│  │  └─────────────────────────────────────┘    │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │  VotingPanel (runda 4)                      │     │
│  │  - Röstningsbubblor                         │     │
│  │  - Motiveringar                             │     │
│  │  - Vinnarbadge                              │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │  PodcastPresentation (post-runda 4)         │     │
│  │  - Waveform-visualisering                   │     │
│  │  - Playback-kontroller                      │     │
│  │  - Modell-logos                             │     │
│  │  - Scrollbar transkript med tidsstämplar    │     │
│  │  - Vinnarbadge + röstningsbubblor           │     │
│  └─────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

### 2.4 Dataflöde (SSE Streaming Protocol)

Debattläget använder samma Vercel AI Data Stream-protokoll som `/compare`, men med utökade event-typer:

```
SSE Event Flow:
────────────────────────────────────────────────────────

1. debate_init         → { participants: [...], topic, total_rounds: 4 }
2. round_start         → { round: 1, type: "introduction", order: [...] }
3. participant_start   → { model: "grok", round: 1, position: 1 }
4. participant_stream  → { model: "grok", chunk: "..." }  (progressive)
5. participant_end     → { model: "grok", word_count: 342, latency_ms: 2100 }
   ... (repeat 3-5 for each participant in round)
6. round_end           → { round: 1, summaries: [...] }
7. round_start         → { round: 2, type: "argument", order: [...] }
   ... (repeat for rounds 2-3)
8. round_start         → { round: 4, type: "voting", order: "parallel" }
9. vote_result         → { model: "grok", vote: { voted_for, motivation, bullets } }
   ... (repeat for each model)
10. debate_results     → { winner, votes, tiebreaker_used, rankings }
11. podcast_ready      → { transcript, waveform_data, timestamps }
```

---

## 3. Filstruktur — Nya och Uppdaterade Filer

### 3.1 Backend — Nya filer

```
surfsense_backend/app/agents/new_chat/
├── debate_supervisor.py           # Huvudgrafen för debattläge
├── debate_prompts.py              # Alla promptmallar för debatt
├── oneseek_debate_subagent.py     # P4-subagent för OneSeeks deltagande
└── debate/
    └── mini_agents/
        ├── __init__.py
        ├── tavily_core.py         # Tavily Core Search mini-agent
        ├── fresh_news.py          # Fresh News mini-agent
        ├── counter_evidence.py    # Counter-Evidence mini-agent
        ├── swedish_context.py     # Swedish Context mini-agent
        ├── fact_consolidation.py  # Fact Consolidation mini-agent
        └── clarity.py             # Clarity mini-agent
```

### 3.2 Backend — Uppdaterade filer

```
surfsense_backend/app/agents/new_chat/
├── supervisor_agent.py            # Lägg till debate_mode parameter + routing
├── supervisor_constants.py        # Lägg till debate-specifika konstanter
├── complete_graph.py              # Lägg till debate_mode: bool parameter
├── bigtool_store.py               # Registrera debate-verktyg
└── tools/
    └── external_models.py         # Utöka med debate-specifik kontext-kedjning

surfsense_backend/app/
├── schemas/                       # Nya Pydantic-modeller för debatt
│   └── debate.py                  # DebateRound, DebateVote, DebateResult
└── routes/
    └── chat.py                    # Nytt query-param: debate_mode=true
```

### 3.3 Frontend — Nya filer

```
surfsense_web/components/
├── tool-ui/
│   └── debate-arena.tsx           # Huvudkomponent (motsv. spotlight-arena.tsx)
├── debate/
│   ├── debate-header.tsx          # Ämne, rundor, deltagare
│   ├── debate-round-view.tsx      # Rundvy med deltagarkort
│   ├── debate-participant-card.tsx # Individuell deltagare
│   ├── debate-voting-panel.tsx    # Röstningsvy
│   ├── debate-podcast-view.tsx    # Podcastpresentation
│   ├── debate-timeline.tsx        # Tidslinje-vy
│   └── debate-waveform.tsx        # Waveform-visualisering
```

### 3.4 Frontend — Uppdaterade filer

```
surfsense_web/
├── components/new-chat/model-selector.tsx   # Lägg till debattläge-toggle
├── contracts/                               # Nya TypeScript-typer
│   └── debate.ts                            # Debate-specifika interfaces
├── atoms/                                   # Jotai atoms
│   └── debate.ts                            # debateModeAtom, debateStateAtom
└── app/dashboard/[search_space_id]/
    └── new-chat/new-chat-page.tsx           # Koppla debate_mode till API-anrop
```

---

## 4. Implementationssteg — Fasplan

### Fas 1: Backend — Debate Supervisor Subgraf (Prio 1)

**Mål:** Fungerande LangGraph-subgraf som kör 4 rundor av debatt.

| Steg | Beskrivning | Filer | Beroenden |
|------|-------------|-------|-----------|
| 1.1 | Definiera debate state schema (`DebateState` TypedDict) | `debate_supervisor.py` | — |
| 1.2 | Skapa `debate_init` node (shuffle, participant selection) | `debate_supervisor.py` | 1.1 |
| 1.3 | Skapa `debate_round_executor` node (sekventiell kedjning) | `debate_supervisor.py` | 1.1, 1.2 |
| 1.4 | Skapa `debate_vote_executor` node (parallell, JSON schema) | `debate_supervisor.py` | 1.1 |
| 1.5 | Skapa `debate_results_aggregator` node (räkning + tiebreaker) | `debate_supervisor.py` | 1.4 |
| 1.6 | Skapa debate-specifika prompts | `debate_prompts.py` | — |
| 1.7 | Skapa OneSeek debate subagent med P4-mönster | `oneseek_debate_subagent.py` | 1.3 |
| 1.8 | Skapa 6 mini-agenter | `debate/mini_agents/*.py` | 1.7 |
| 1.9 | Integrera subgraf i `supervisor_agent.py` | `supervisor_agent.py` | 1.1–1.8 |
| 1.10 | Uppdatera `complete_graph.py` med `debate_mode` | `complete_graph.py` | 1.9 |

### Fas 2: Backend — API & Streaming (Prio 1)

| Steg | Beskrivning | Filer | Beroenden |
|------|-------------|-------|-----------|
| 2.1 | Definiera Pydantic-scheman för debatt | `schemas/debate.py` | — |
| 2.2 | Lägg till `debate_mode` query-param i chat route | `routes/chat.py` | 2.1 |
| 2.3 | Implementera debate SSE event-typer | `debate_supervisor.py` | 1.3, 2.2 |
| 2.4 | Uppdatera bigtool registry | `bigtool_store.py` | 1.6 |

### Fas 3: Frontend — Debate Arena UI (Prio 1)

| Steg | Beskrivning | Filer | Beroenden |
|------|-------------|-------|-----------|
| 3.1 | Skapa debate TypeScript-typer | `contracts/debate.ts` | — |
| 3.2 | Skapa `DebateArena` huvudkomponent | `debate-arena.tsx` | 3.1 |
| 3.3 | Skapa `DebateRoundView` med deltagarkort | `debate-round-view.tsx` | 3.1 |
| 3.4 | Skapa `DebateVotingPanel` | `debate-voting-panel.tsx` | 3.1 |
| 3.5 | Skapa `DebatePodcastView` med waveform | `debate-podcast-view.tsx` | 3.1 |
| 3.6 | Integrera debattläge-toggle i model-selector | `model-selector.tsx` | 3.2 |
| 3.7 | Koppla Jotai atoms och SSE-lyssnare | `atoms/debate.ts` | 3.2 |

### Fas 4: Testning & Dokumentation (Prio 2)

| Steg | Beskrivning | Filer | Beroenden |
|------|-------------|-------|-----------|
| 4.1 | Enhetstester för debate supervisor | `tests/test_debate_supervisor_v1.py` | Fas 1 |
| 4.2 | Enhetstester för vote-aggregering | `tests/test_debate_voting.py` | 1.4, 1.5 |
| 4.3 | Integrationstester | `tests/test_debate_integration.py` | Fas 1–3 |
| 4.4 | HTML-prototyper/mockups | `docs/debate-mode/mockups/` | — |
| 4.5 | Arkitekturdokumentation | `docs/debate-mode/` | — |

---

## 5. Teknisk Integration — Detaljer

### 5.1 State Schema (Backend)

```python
class DebateState(TypedDict):
    """State för debattlägets LangGraph-subgraf."""
    messages: Annotated[list[AnyMessage], add_messages]
    topic: str
    participants: list[str]  # ["grok", "claude", "gpt", ...]
    current_round: int  # 1-4
    round_order: dict[int, list[str]]  # {1: ["claude", "grok", ...], ...}
    round_responses: dict[int, dict[str, str]]  # {1: {"claude": "...", ...}}
    word_counts: dict[str, int]  # total word count per participant
    votes: list[DebateVote]
    winner: str | None
    debate_status: str  # "initializing" | "round_1" | ... | "voting" | "complete"
    oneseek_research_cache: dict[str, Any]  # P4 subagent results
```

### 5.2 Routing Integration

Debattläget aktiveras via samma mekanism som compare:

```python
# complete_graph.py
async def build_complete_graph(
    *,
    # ... existing params ...
    compare_mode: bool = False,
    debate_mode: bool = False,   # ← NY PARAMETER
):
    return await create_supervisor_agent(
        # ... pass debate_mode through ...
    )
```

```python
# supervisor_agent.py — routing logic
if debate_mode:
    # Build debate subgraph instead of normal flow
    debate_graph = build_debate_supervisor_subgraph(
        llm=llm,
        external_model_specs=EXTERNAL_MODEL_SPECS,
        dependencies=dependencies,
    )
    graph.add_node("debate_supervisor", debate_graph)
    graph.add_edge("resolve_intent", "debate_supervisor")
    graph.add_edge("debate_supervisor", END)
```

### 5.3 SSE Streaming Integration

Debattläget använder samma `data_stream_encoder` som compare, men med nya event-typer:

```python
# Nya SSE-event typer (prefix: "debate_")
DEBATE_SSE_EVENTS = {
    "debate_init": "8:",        # Custom data event
    "debate_round_start": "8:",
    "debate_participant_start": "8:",
    "debate_participant_chunk": "0:",  # Text stream
    "debate_participant_end": "8:",
    "debate_round_end": "8:",
    "debate_vote": "8:",
    "debate_results": "8:",
    "debate_podcast_ready": "8:",
}
```

### 5.4 Röstning — JSON Schema Enforcement

```python
VOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "voted_for": {"type": "string"},
        "short_motivation": {"type": "string", "maxLength": 200},
        "three_bullets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3
        }
    },
    "required": ["voted_for", "short_motivation", "three_bullets"]
}
```

Self-vote filter:
```python
def filter_self_votes(votes: list[DebateVote]) -> list[DebateVote]:
    return [v for v in votes if v.voter != v.voted_for]
```

Tiebreaker:
```python
def resolve_tiebreaker(
    vote_counts: dict[str, int],
    word_counts: dict[str, int]
) -> str:
    max_votes = max(vote_counts.values())
    tied = [m for m, v in vote_counts.items() if v == max_votes]
    if len(tied) == 1:
        return tied[0]
    # Tiebreaker: highest total word count across all rounds
    return max(tied, key=lambda m: word_counts.get(m, 0))
```

### 5.5 Frontend Integration — Parallell med /compare

```typescript
// contracts/debate.ts
interface DebateParticipant {
  model: string;
  displayName: string;
  logo: string;
  responses: Record<number, string>;  // round → response
  wordCount: number;
  vote?: DebateVote;
}

interface DebateVote {
  voter: string;
  votedFor: string;
  shortMotivation: string;
  threeBullets: string[];
}

interface DebateState {
  topic: string;
  participants: DebateParticipant[];
  currentRound: number;
  totalRounds: number;
  roundOrder: Record<number, string[]>;
  status: "initializing" | "round_1" | "round_2" | "round_3" | "voting" | "results" | "podcast";
  winner?: string;
  votes: DebateVote[];
}
```

### 5.6 Podcastpresentation — Verktygskoppling

Podcastverktyget är en separat, återanvändbar komponent som invokeras efter debattresultaten:

```python
# debate_supervisor.py — post round 4
async def debate_results_aggregator(state: DebateState) -> dict:
    results = aggregate_votes(state["votes"], state["word_counts"])

    # Invoke podcast presentation tool
    podcast_data = await generate_podcast_presentation(
        topic=state["topic"],
        participants=state["participants"],
        rounds=state["round_responses"],
        votes=state["votes"],
        winner=results["winner"],
    )

    return {
        "winner": results["winner"],
        "debate_status": "complete",
        "podcast_data": podcast_data,
    }
```

---

## 6. Riskhantering

| Risk | Sannolikhet | Åtgärd |
|------|-------------|--------|
| Token-budget overflow (4 rundor × 8 modeller) | Hög | Max 800 tokens per svar, early-stop i runda 4, context offload |
| JSON-röstning misslyckas (modell ignorerar schema) | Medium | JSON fallback parsing, regex extraction, retry 1x |
| Pod-läcka (OneSeek subagent) | Låg | Pod-leasing med TTL, automatic cleanup |
| Extern modell timeout | Medium | 90s timeout per anrop, skip + markera som "error" |
| Oändlig debatt-loop | Låg | Max 5 rundor totalt (hård gräns), round counter guard |
| SSE-connection drop | Medium | Reconnection med state-rehydration från checkpoint |

---

## 7. Testplan

### 7.1 Enhetstester

```python
# test_debate_supervisor_v1.py
class TestDebateSupervisor:
    def test_round_order_is_random_and_unique()
    def test_all_participants_included_each_round()
    def test_context_chain_grows_per_participant()
    def test_self_votes_filtered()
    def test_tiebreaker_by_word_count()
    def test_vote_json_schema_validation()
    def test_round_4_parallel_execution()
    def test_max_rounds_guard()
    def test_oneseek_subagent_p4_structure()
    def test_debate_state_schema_complete()
```

### 7.2 Integrationstester

```python
# test_debate_integration.py
class TestDebateIntegration:
    def test_full_debate_flow_4_rounds()
    def test_sse_events_in_correct_order()
    def test_debate_mode_routing()
    def test_podcast_generation_after_voting()
```

### 7.3 Frontend-tester

Manuell testning via HTML-mockups (se `/docs/debate-mode/mockups/`).

---

## 8. Mockups

Fem HTML-prototyper finns i `docs/debate-mode/mockups/`:

| # | Mockup | Beskrivning |
|---|--------|-------------|
| 1 | `01-debate-arena.html` | Huvudvy — debattarena med rundnavigering och deltagarkort |
| 2 | `02-voting-results.html` | Röstnings- och resultatvy med vinnarbadge |
| 3 | `03-podcast-presentation.html` | Podcastpresentation med waveform och transkript |
| 4 | `04-round-timeline.html` | Runda-för-runda tidslinje med argumentkedja |
| 5 | `05-mobile-debate.html` | Mobilanpassad debattvy med swipe-navigering |

---

## 9. Beroenden & Kompatibilitet

### Inga nya pip/npm-paket krävs

Debattläget återanvänder befintliga beroenden:
- **Backend:** LangGraph, LiteLLM, langchain-core (redan installerade)
- **Frontend:** @assistant-ui/react, framer-motion, shadcn/ui (redan installerade)
- **Waveform:** Canvas API (inbyggd i webbläsaren)

### Kompatibilitet

- Debattläge är helt isolerat från `/compare` — de delar infra men inte state
- Existerande compare-tester påverkas ej
- Inget breaking change i API:t (debate_mode är ny optional param)

---

## 10. Tidsuppskattning per fas

| Fas | Beskrivning | Komplexitet |
|-----|-------------|-------------|
| Fas 1 | Backend subgraf + P4 subagent | Hög |
| Fas 2 | API & streaming | Medium |
| Fas 3 | Frontend UI | Hög |
| Fas 4 | Testning & dokumentation | Medium |

---

## 11. Ordlista

| Term | Förklaring |
|------|-----------|
| P4-mönster | Planner → Parallel agents → Critic → Synthesizer |
| Spotlight Arena | Befintlig jämförelsevy i `/compare` |
| Debate Arena | Ny debattvy (denna feature) |
| Fan-out | Parallell exekvering av flera agenter |
| Context offload | Spara mellantillstånd för att minska kontextfönstret |
| SSE | Server-Sent Events — realtidsstreaming till frontend |
| Tiebreaker | Ordräkning vid lika röstantal |

---

*Denna plan är baserad på issue #48 och den befintliga `/compare`-arkitekturen. Alla tekniska beslut följer etablerade mönster i kodbasen.*
