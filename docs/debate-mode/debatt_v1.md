# Debatt v1 — Komplett Teknisk Dokumentation

> Live Debate Mode + Voice Debate Mode for OneSeek
> Senast uppdaterad: 2026-03-01

---

## Innehall

1. [Oversikt](#1-oversikt)
2. [Arkitektur](#2-arkitektur)
3. [Backend — Filstruktur](#3-backend--filstruktur)
4. [Frontend — Filstruktur](#4-frontend--filstruktur)
5. [Dataflode (SSE Events)](#5-dataflode-sse-events)
6. [Voice Debate Mode (/dvoice)](#6-voice-debate-mode-dvoice)
7. [Admin — Debatt-installningar](#7-admin--debatt-installningar)
8. [Admin Flow Pipeline](#8-admin-flow-pipeline)
9. [Prompt Registry](#9-prompt-registry)
10. [State Management](#10-state-management)
11. [Algoritmdetaljer](#11-algoritmdetaljer)
12. [Konfiguration](#12-konfiguration)
13. [Testning](#13-testning)
14. [Framtida arbete](#14-framtida-arbete)

---

## 1. Oversikt

Debattlaget ar ett komplett subgraph-system i OneSeek dar 8 AI-modeller (7 externa + OneSeek) debatterar i 4 rundor med sekventiell kontextkedja, parallell rostning, och AI-syntes.

### Kommandon

| Kommando | Beskrivning |
|----------|-------------|
| `/debatt <amne>` | Textdebatt — 4 rundor, rostning, syntes |
| `/dvoice <amne>` | Rostdebatt — samma + live TTS via OpenAI API |

### Deltagare (8 st)

| Nyckel | Display | Roll |
|--------|---------|------|
| `call_grok` | Grok | Extern modell |
| `call_claude` | Claude | Extern modell |
| `call_gpt` | ChatGPT | Extern modell |
| `call_gemini` | Gemini | Extern modell |
| `call_deepseek` | DeepSeek | Extern modell |
| `call_perplexity` | Perplexity | Extern modell |
| `call_qwen` | Qwen | Extern modell |
| `call_oneseek` | OneSeek | Intern LLM + Tavily realtidssok |

### 4 Rundor

| Runda | Typ | Ordgrans | Korning |
|-------|-----|----------|---------|
| 1 | Introduktion | 300 ord | Sekventiell, slumpad ordning |
| 2 | Argument | 500 ord | Sekventiell, slumpad ordning |
| 3 | Fordjupning | 500 ord | Sekventiell, slumpad ordning |
| 4 | Rostning | JSON-schema | **Parallell** (asyncio.gather) |

---

## 2. Arkitektur

### Graph-flode (LangGraph StateGraph)

```
resolve_intent
    |
    v
debate_domain_planner    (deterministisk — alla deltagare)
    |
    v
debate_round_executor    (4 rundor inline)
    |                        |
    |                    [om /dvoice]
    |                        |
    |                    debate_voice_pipeline (TTS pipelining)
    |
    v
debate_convergence       (rostaggreering + tiebreaker)
    |
    v
debate_synthesizer       (slutgiltig analys med debate-arena-data JSON)
    |
    v
END
```

### Kontextkedja (per runda)

Varje deltagare ser:
1. Debattamnet
2. Alla svar fran **alla tidigare rundor** (trunkerade till 600 tecken/svar)
3. Alla svar fran **nuvarande runda hittills** (de som svarat fore dem)

Detta ger en progressivt rikare kontextbild — den sista deltagaren i runda 3 har sett allt.

### Mutual Exclusion med Compare Mode

Debate och Compare ar omsesidigt exklusiva subgrapher:
- Om `debate_mode == True`: `compare_mode` setts aldrig till `True`
- Guard i `stream_new_chat.py` rad ~1862: `if route == Route.JAMFORELSE and not debate_mode`
- Supervisorns systemprompt injiceras med antingen debate-instruktioner ELLER compare-instruktioner, aldrig bada

---

## 3. Backend — Filstruktur

### 3.1 `debate_executor.py`

**Skvag**: `surfsense_backend/app/agents/new_chat/debate_executor.py`
**Storlek**: ~990 rader

#### Konstanter

```python
MAX_RESPONSE_TOKENS = 800       # Token-budget per deltagarsvar
VOTE_TIMEOUT_SECONDS = 60       # Timeout for rostning per modell
RESPONSE_TIMEOUT_SECONDS = 90   # Timeout for vanligt svar per modell

ROUND_PROMPTS = {
    1: DEBATE_ROUND1_INTRO_PROMPT,
    2: DEBATE_ROUND2_ARGUMENT_PROMPT,
    3: DEBATE_ROUND3_DEEPENING_PROMPT,
    4: DEBATE_ROUND4_VOTING_PROMPT,
}

ONESEEK_ROUND_PROMPTS = {
    1: ONESEEK_DEBATE_ROUND1_PROMPT,
    2: ONESEEK_DEBATE_ROUND2_PROMPT,
    3: ONESEEK_DEBATE_ROUND3_PROMPT,
    4: ONESEEK_DEBATE_ROUND4_PROMPT,
}

VOTE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "voted_for": {"type": "string"},
        "short_motivation": {"type": "string", "maxLength": 200},
        "three_bullets": {
            "type": "array", "items": {"type": "string"},
            "minItems": 3, "maxItems": 3,
        },
    },
    "required": ["voted_for", "short_motivation", "three_bullets"],
}
```

#### Hjalp-funktioner

| Funktion | Beskrivning |
|----------|-------------|
| `_extract_json_from_text(text)` | Extraherar JSON fran text (direct parse + regex fallback) |
| `_count_words(text)` | Ordrakning for tiebreaker |
| `_filter_self_votes(votes)` | Tar bort rostsedlar dar voter == voted_for |
| `_resolve_winner(vote_counts, word_counts)` | Valjaren: flest roster → tiebreaker via ordrakning |

#### Node Builders

| Builder | Graph-nod | Beskrivning |
|---------|-----------|-------------|
| `build_debate_domain_planner_node(...)` | `debate_domain_planner` | Deterministisk — skapar domain_plans for alla deltagare |
| `build_debate_round_executor_node(...)` | `debate_round_executor` | Kor alla 4 rundor: R1-R3 sekventiellt, R4 parallellt |
| `build_debate_convergence_node(...)` | `debate_convergence` | Aggregerar roster, filtrerar self-votes, beraknar vinnare |
| `build_debate_synthesizer_node(...)` | `debate_synthesizer` | Slutgiltig LLM-analys med debate-arena-data JSON |

#### `build_debate_round_executor_node` Signatur

```python
def build_debate_round_executor_node(
    *,
    llm: Any,
    call_external_model_fn: Any | None = None,
    tavily_search_fn: Any | None = None,
    execution_timeout_seconds: float = RESPONSE_TIMEOUT_SECONDS,
    prompt_overrides: dict[str, str] | None = None,
    voice_mode: bool = False,
)
```

#### Intern logik for rundor

```
FOR round_num IN 1..3:
    round_order = shuffle(participants)
    FOR position, participant IN round_order:
        context = build_context_chain(topic, prev_rounds, current_round)
        IF is_oneseek:
            response = _run_oneseek_debate_turn(llm, context, tavily, ...)
        ELSE:
            response = call_external_model(spec, context, round_prompt)

        emit("debate_participant_start", ...)
        emit("debate_participant_end", ...)
        emit("model_response_ready", ...)

        IF voice_mode AND response_text:
            await schedule_voice_generation(...)  # TTS pipelining
    emit("debate_round_end", ...)

# Round 4: Parallel Voting
tasks = [_cast_vote(p) for p in participants]
results = asyncio.gather(*tasks)
FOR vote IN results:
    emit("debate_vote_result", ...)
```

#### `_run_oneseek_debate_turn` (intern)

```python
async def _run_oneseek_debate_turn(
    *,
    llm: Any,
    query: str,
    tavily_search_fn: Any | None = None,
    topic: str,
    round_num: int,
    timeout: float = 90,
    system_prompt: str | None = None,
    round_prompt: str | None = None,
) -> str
```

- Gor valfri Tavily-sokning (upp till 3 resultat, 300 tecken/resultat, 15s timeout)
- Kombinerar system_prompt + round_prompt + datetime-kontext
- Returnerar `response.content`

#### `_call_oneseek_vote` (intern)

```python
async def _call_oneseek_vote(
    llm: Any,
    vote_prompt: str,
    system_hint: str = "",
) -> str
```

- OneSeeks rostning anvander intern LLM med JSON-enforced output

---

### 3.2 `debate_prompts.py`

**Skvag**: `surfsense_backend/app/agents/new_chat/debate_prompts.py`

| Konstant | Rader | Beskrivning |
|----------|-------|-------------|
| `DEBATE_SUPERVISOR_INSTRUCTIONS` | 12-29 | Supervisor-instruktioner (injiceras i systemprompt) |
| `DEFAULT_DEBATE_ANALYSIS_PROMPT` | 34-82 | Synthesizer-prompt med debate-arena-data JSON-mall |
| `DEFAULT_DEBATE_DOMAIN_PLANNER_PROMPT` | 87-99 | Planner for domaner (deterministisk) |
| `DEFAULT_DEBATE_MINI_PLANNER_PROMPT` | 104-129 | Mini-planner for subagenter |
| `DEFAULT_DEBATE_MINI_CRITIC_PROMPT` | 134-157 | Mini-critic for svarskvalitet |
| `DEFAULT_DEBATE_CONVERGENCE_PROMPT` | 162-208 | Convergence med rost- och ordrakningslogik |
| `DEBATE_ROUND1_INTRO_PROMPT` | 213-226 | Runda 1: Introduktion (max 300 ord) |
| `DEBATE_ROUND2_ARGUMENT_PROMPT` | 228-241 | Runda 2: Argument (max 500 ord) |
| `DEBATE_ROUND3_DEEPENING_PROMPT` | 243-257 | Runda 3: Fordjupning (max 500 ord) |
| `DEBATE_ROUND4_VOTING_PROMPT` | 259-277 | Runda 4: Rostning (JSON-schema enforced) |
| `ONESEEK_DEBATE_SYSTEM_PROMPT` | 282-294 | OneSeek-specifikt systemprompt |
| `ONESEEK_DEBATE_ROUND1_PROMPT` | 299-312 | OneSeek Runda 1 |
| `ONESEEK_DEBATE_ROUND2_PROMPT` | 314-326 | OneSeek Runda 2 |
| `ONESEEK_DEBATE_ROUND3_PROMPT` | 328-341 | OneSeek Runda 3 |
| `ONESEEK_DEBATE_ROUND4_PROMPT` | 343-359 | OneSeek Runda 4 |
| `DEFAULT_DEBATE_RESEARCH_PROMPT` | 364-376 | Research Agent prompt |

#### Funktion

```python
def build_debate_synthesis_prompt(
    base_prompt: str,
    *,
    citations_enabled: bool,
    citation_instructions: str | None = None,
) -> str
```

---

### 3.3 `debate_voice.py`

**Skvag**: `surfsense_backend/app/agents/new_chat/debate_voice.py`

TTS-pipeline som anvander OpenAI SDK direkt via `httpx` (INTE litellm) for streaming PCM-ljud.

#### Konstanter

```python
DEFAULT_DEBATE_VOICE_MAP = {
    "Grok": "fable", "Claude": "nova", "ChatGPT": "echo",
    "Gemini": "shimmer", "DeepSeek": "alloy", "Perplexity": "onyx",
    "Qwen": "fable", "OneSeek": "nova",
}

PCM_SAMPLE_RATE = 24000    # 24 kHz
PCM_BIT_DEPTH = 16         # 16-bit signed little-endian
PCM_CHANNELS = 1           # mono
DEFAULT_CHUNK_BYTES = 4800  # ~100ms audio per chunk
DEFAULT_TTS_MODEL = "tts-1"
```

#### Funktioner

| Funktion | Signatur | Beskrivning |
|----------|----------|-------------|
| `_resolve_voice_settings` | `(state) -> dict` | Lasar voice settings fran graph state eller env |
| `_env_api_key` | `() -> str` | Fallback: DEBATE_VOICE_API_KEY eller TTS_SERVICE_API_KEY |
| `get_voice_for_participant` | `(display, voice_map) -> str` | Slaar upp TTS-rost for deltagare |
| `generate_voice_stream` | `async gen(text, voice, api_key, ...) -> bytes` | Streamar PCM-chunks via httpx POST |
| `_emit_voice_events` | `async(text, participant, ..., config) -> int` | Emitterar SSE: speaker, chunk, done, error |
| `schedule_voice_generation` | `async(text, ..., state, config) -> Task\|None` | Skapar asyncio.Task for TTS |
| `collect_all_audio_for_export` | `async(round_responses, ...) -> list[tuple]` | Full PCM for MP3-export |

#### API-anrop (httpx)

```python
POST {api_base}/audio/speech
Headers: Authorization: Bearer {api_key}
Body: {
    "model": "tts-1",
    "input": text,
    "voice": voice,
    "response_format": "pcm",
    "speed": 1.0
}
Response: Streaming binary PCM (24kHz/16-bit/mono)
```

---

### 3.4 `supervisor_agent.py` (Debate-block)

**Skvag**: `surfsense_backend/app/agents/new_chat/supervisor_agent.py`
**Debatt-block**: rad ~6910-7010

```python
# Funktionssignatur (utdrag)
async def build_graph(
    ...,
    debate_mode: bool = False,      # rad 1792
    voice_debate_mode: bool = False, # rad 1793
    ...,
)
```

#### Graph-uppbyggnad (nar `debate_mode == True`)

```python
# Noder
graph_builder.add_node("debate_domain_planner", ...)
graph_builder.add_node("debate_round_executor", ...)
graph_builder.add_node("debate_convergence", ...)
graph_builder.add_node("debate_synthesizer", ...)

# Edges
resolve_intent -> debate_domain_planner
debate_domain_planner -> debate_round_executor
debate_round_executor -> debate_convergence
debate_convergence -> debate_synthesizer
debate_synthesizer -> END
```

#### Tavily-sokning for OneSeek

Skapar `_debate_tavily_search_fn` fran connector service — max 5 resultat, 300 tecken/styck, 15s timeout. Anvander separat API-nyckel fran Tavily-connector.

---

### 3.5 `supervisor_types.py` (State keys)

**Skvag**: `surfsense_backend/app/agents/new_chat/supervisor_types.py`

```python
class SupervisorState(TypedDict):
    # ... (ovriga nycklar) ...

    # Debate state keys (rad 186-200)
    debate_participants: Annotated[list[dict[str, Any]], _replace]
    debate_topic: Annotated[str | None, _replace]
    debate_current_round: Annotated[int | None, _replace]
    debate_round_responses: Annotated[dict[int, dict[str, str]], _replace]
    debate_votes: Annotated[list[dict[str, Any]], _replace]
    debate_word_counts: Annotated[dict[str, int], _replace]
    debate_status: Annotated[str | None, _replace]
    debate_voice_settings: Annotated[dict[str, Any] | None, _replace]
```

**Viktigt**: Alla nycklar MASTE vara deklarerade i TypedDict — annars droppar LangGraph dem tyst!

---

### 3.6 `structured_schemas.py` (Pydantic-modeller)

```python
class DebateVoteResult(BaseModel):
    voted_for: str
    short_motivation: str = Field(max_length=200)
    three_bullets: list[str] = Field(min_length=3, max_length=3)

class DebateConvergenceResult(BaseModel):
    thinking: str
    merged_summary: str
    overlap_score: float
    conflicts: list[dict[str, str]]
    agreements: list[str]
    disagreements: list[str]
    vote_results: dict[str, int]
    winner: str
    tiebreaker_used: bool
    word_counts: dict[str, int]
    comparative_summary: str
```

---

### 3.7 `stream_new_chat.py` (Routing + SSE Bridge)

**Skvag**: `surfsense_backend/app/tasks/chat/stream_new_chat.py`

#### Kommando-detektion

```python
DEBATE_PREFIX = "/debatt"   # rad 135
DVOICE_PREFIX = "/dvoice"   # rad 136

def _is_debate_request(user_query) -> bool      # True for bade /debatt och /dvoice
def _is_voice_debate_request(user_query) -> bool # True BARA for /dvoice
def _extract_debate_query(user_query) -> str     # Extraherar amnet efter prefix
```

#### Mode-detektion (rad ~1690)

```python
debate_mode = _is_debate_request(user_query)
voice_debate_mode = _is_voice_debate_request(user_query) if debate_mode else False
debate_query = _extract_debate_query(user_query) if debate_mode else ""
if debate_mode and debate_query:
    user_query = debate_query
```

#### Voice settings fran Redis (rad ~2555)

```python
if voice_debate_mode:
    from app.routes.admin_debate_routes import load_debate_voice_settings
    _voice_settings = load_debate_voice_settings()
    if _voice_settings:
        input_state["debate_voice_settings"] = _voice_settings
```

#### SSE Event Bridge (rad ~3096-3140)

All mappning fran backend-events (snake_case) till frontend SSE (kebab-case):

| Backend Event | SSE Event | Payload |
|---------------|-----------|---------|
| `debate_init` | `debate-init` | participants, topic, total_rounds, voice_mode, timestamp |
| `debate_round_start` | `debate-round-start` | round, type, order, timestamp |
| `debate_participant_start` | `debate-participant-start` | model, model_key, round, position, timestamp |
| `debate_participant_end` | `debate-participant-end` | model, model_key, round, position, word_count, latency_ms, response_preview, timestamp |
| `debate_round_end` | `debate-round-end` | round, participant_count, timestamp |
| `debate_vote_result` | `debate-vote-result` | voter, voted_for, motivation, bullets, timestamp |
| `debate_results` | `debate-results` | winner, vote_counts, tiebreaker_used, word_counts, total_votes, timestamp |
| `debate_synthesis_complete` | `debate-synthesis-complete` | winner, vote_counts, synthesis_length, timestamp |
| `debate_voice_speaker` | `debate-voice-speaker` | model, model_key, round, voice, timestamp |
| `debate_voice_chunk` | `debate-voice-chunk` | model, model_key, round, chunk_index, pcm_b64, sample_rate, bit_depth, channels, timestamp |
| `debate_voice_done` | `debate-voice-done` | model, model_key, round, total_bytes, total_chunks, timestamp |
| `debate_voice_error` | `debate-voice-error` | model, round, error, timestamp |

---

### 3.8 `admin_debate_routes.py` (REST API)

**Skvag**: `surfsense_backend/app/routes/admin_debate_routes.py`

#### Endpoints

| Metod | URL | Beskrivning |
|-------|-----|-------------|
| `GET` | `/api/v1/admin/debate/voice-settings` | Hamta rostinstellningar |
| `PUT` | `/api/v1/admin/debate/voice-settings` | Uppdatera rostinstellningar |

#### Pydantic-schema

```python
class DebateVoiceSettings(BaseModel):
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "tts-1"
    speed: float = 1.0  # 0.25 - 4.0
    voice_map: dict[str, str] = DEFAULT_VOICE_MAP
```

#### Lagring

- **Redis-nyckel**: `debate:voice_settings`
- **Format**: JSON-serialiserad `DebateVoiceSettings`
- **Redis-URL**: Fran `CELERY_BROKER_URL` env-var (default `redis://localhost:6379/0`)

#### Helper

```python
def load_debate_voice_settings() -> dict | None
```

Anvands av `stream_new_chat.py` for att ladda installningar vid runtime.

---

### 3.9 `admin_flow_graph_routes.py` (Pipeline-noder)

#### Debatt-noder (9 st + voice pipeline)

| Node ID | Label | Stage |
|---------|-------|-------|
| `node:debate_domain_planner` | Debate Domain Planner | debate |
| `node:debate_round_executor` | Debate Round Executor | debate |
| `node:debate_oneseek_agent` | OneSeek Debate Agent | debate |
| `node:debate_round_1` | Runda 1: Introduktion | debate |
| `node:debate_round_2` | Runda 2: Argument | debate |
| `node:debate_round_3` | Runda 3: Fordjupning | debate |
| `node:debate_round_4_voting` | Runda 4: Rostning | debate |
| `node:debate_convergence` | Debate Convergence | debate |
| `node:debate_synthesizer` | Debate Synthesizer | debate |
| `node:debate_voice_pipeline` | Voice Pipeline | debate |

#### Debatt-kanter (12 st)

```
debate_domain_planner -> debate_round_executor
debate_domain_planner -> debate_oneseek_agent  (label: "OneSeek")
debate_oneseek_agent -> debate_round_1          (label: "deltar i rundor")
debate_round_executor -> debate_round_1         (label: "runda 1")
debate_round_1 -> debate_round_2
debate_round_2 -> debate_round_3
debate_round_3 -> debate_round_4_voting
debate_round_4_voting -> debate_convergence
debate_convergence -> debate_synthesizer
debate_round_executor -> debate_voice_pipeline  (conditional, label: "/dvoice")
```

#### Stage

```python
{"id": "debate", "label": "Debatt", "color": "amber"}
```

---

## 4. Frontend — Filstruktur

### 4.1 `debate.types.ts`

**Skvag**: `surfsense_web/contracts/types/debate.types.ts`

#### Core Interfaces

```typescript
interface DebateParticipant {
    key: string;                    // "call_grok", "call_oneseek"
    display: string;                // "Grok", "OneSeek"
    toolName: string;
    configId: number;
    isOneseek: boolean;
    totalWordCount: number;
    responses: Record<number, DebateParticipantResponse>;
    vote?: DebateVote;
}

interface DebateParticipantResponse {
    round: number;
    position: number;
    text: string;
    wordCount: number;
    latencyMs: number;
    status: "waiting" | "speaking" | "complete" | "error";
}

interface DebateVote {
    voter: string;
    voterKey: string;
    votedFor: string;
    shortMotivation: string;
    threeBullets: string[];
}

interface DebateRoundInfo {
    round: number;
    type: "introduction" | "argument" | "deepening" | "voting";
    order: string[];
    status: "pending" | "active" | "complete";
}

interface DebateResults {
    winner: string;
    voteCounts: Record<string, number>;
    wordCounts: Record<string, number>;
    tiebreakerUsed: boolean;
    totalVotes: number;
    selfVotesFiltered: number;
}

interface DebateState {
    topic: string;
    participants: DebateParticipant[];
    rounds: DebateRoundInfo[];
    currentRound: number;
    totalRounds: number;
    status: "initializing" | "round_1" | "round_2" | "round_3"
          | "voting" | "results" | "synthesis" | "complete";
    results?: DebateResults;
    votes: DebateVote[];
    voiceMode?: boolean;
}
```

#### Voice Interfaces

```typescript
interface DebateVoiceSpeakerEvent { model, model_key, round, voice, timestamp }
interface DebateVoiceChunkEvent { model, model_key, round, chunk_index, pcm_b64, sample_rate, bit_depth, channels, timestamp }
interface DebateVoiceDoneEvent { model, model_key, round, total_bytes, total_chunks, timestamp }
interface DebateVoiceErrorEvent { model, round, error, timestamp }

interface DebateVoiceState {
    enabled: boolean;
    currentSpeaker: string | null;
    playbackStatus: "idle" | "playing" | "paused" | "buffering";
    volume: number;
    waveformData: Uint8Array | null;
    collectedChunks: Record<string, ArrayBuffer[]>;
}
```

#### Display-konstanter

```typescript
DEBATE_TOOL_NAMES = Set(["call_grok", "call_claude", ...])

DEBATE_MODEL_DISPLAY = {
    call_grok: "Grok", call_claude: "Claude", call_gpt: "ChatGPT",
    call_gemini: "Gemini", call_deepseek: "DeepSeek",
    call_perplexity: "Perplexity", call_qwen: "Qwen", call_oneseek: "OneSeek",
}

DEBATE_MODEL_COLORS = {
    grok: "#1a1a2e", claude: "#d4a574", gpt: "#10a37f",
    gemini: "#4285f4", deepseek: "#0066ff", perplexity: "#20b2aa",
    qwen: "#7c3aed", oneseek: "#6366f1",
}

ROUND_LABELS = { 1: "Introduktion", 2: "Argument", 3: "Fordjupning", 4: "Rostning" }
```

---

### 4.2 `use-debate-audio.ts`

**Skvag**: `surfsense_web/hooks/use-debate-audio.ts`

Web Audio API-hook for live rostuppspelning.

#### Returnerar

```typescript
{
    voiceState: DebateVoiceState;
    enqueueChunk: (speaker: string, b64: string) => void;
    onSpeakerChange: (speaker: string) => void;
    togglePlayPause: () => void;
    setVolume: (vol: number) => void;
    exportAudioBlob: () => Blob | null;
}
```

#### Intern arkitektur

1. **AudioContext** (24kHz sample rate)
2. **GainNode** for volymkontroll
3. **AnalyserNode** (fftSize=256) for waveform-visualisering
4. **Chunk-ko** (`chunkQueueRef`) — chunks spelas sekventiellt
5. **PCM-avkodning**: base64 -> Uint8Array -> Int16Array -> Float32Array -> AudioBuffer
6. **WAV-export**: Bygger WAV-header + samlar all PCM for nedladdning

---

### 4.3 `debate-arena.tsx`

**Skvag**: `surfsense_web/components/debate/debate-arena.tsx`

#### Exporterade Context

```typescript
export const DebateArenaActiveContext = createContext(false);
export const LiveDebateStateContext = createContext<DebateState | null>(null);
export const DebateVoiceContext = createContext<{
    voiceState: DebateVoiceState;
    togglePlayPause: () => void;
    setVolume: (v: number) => void;
    exportAudioBlob: () => Blob | null;
} | null>(null);
```

#### Komponenter

| Komponent | Beskrivning |
|-----------|-------------|
| `DebateArenaLayout` | Huvudkomponent — header, rundtabbar, progressbar, deltagarkort, rostresultat, vinnarbanner |
| `ParticipantCard` | Enskilt deltagarkort med auto-expand/collapse, voice-glow |
| `VotingSection` | Rostresultat med staplars och individuella rostmotiveringar |
| `WinnerBanner` | Vinnarbanner med krona och rostantal |
| `VoiceControlBar` | Play/pause, waveform-canvas, volymslider, LIVE-badge, nedladdning |

#### Progressiv kortvisning

- `visibleParticipants`: Filtrerar deltagare som har svar i aktiv runda
- `currentSpeaker`: Detekterar "speaking" status
- `autoExpanded`: Talande kort ar alltid expanderat; senaste klara kortet expanderas om ingen talar
- `manualToggle` med auto-reset nar autoExpanded andras

#### Voice UI

- Header visar "Rostdebatt" med Mic-ikon for /dvoice
- LIVE-badge (rod, pulserande) nar ljud spelas
- VoiceControlBar med waveform-canvas (64 bars, rod nar aktiv)
- Rod glow-effekt pa deltagarkort med aktiv rostuppspelning: `border-red-500/40 ring-1 ring-red-500/20`

---

### 4.4 `new-chat-page.tsx` (SSE-hanterare)

**Skvag**: `surfsense_web/app/dashboard/[search_space_id]/new-chat/new-chat-page.tsx`

#### State

```typescript
const [debateState, setDebateState] = useState<DebateState | null>(null);
const isVoiceDebate = debateState?.voiceMode === true;
const debateAudio = useDebateAudio(isVoiceDebate);
```

#### SSE Event Handlers (2 block — ny meddelande + regenerering)

Varje event foljer monstret:
```typescript
case "data-{event-name}": {
    const d = parsed.data as Record<string, unknown>;
    setDebateState((prev) => {
        if (!prev) return prev;
        return { ...prev, /* immutable update */ };
    });
    break;
}
```

**8 debatt-events** + **4 voice-events** per block = 24 case-satser totalt.

#### Context Providers (renderingstruk)

```tsx
<LiveDebateStateContext.Provider value={debateState}>
    <DebateVoiceContext.Provider value={isVoiceDebate ? {...debateAudio} : null}>
        {/* ... children ... */}
    </DebateVoiceContext.Provider>
</LiveDebateStateContext.Provider>
```

---

### 4.5 `assistant-message.tsx` (Mutual Exclusion Guard)

```typescript
const isDebate = debateState !== null;

// SpotlightArena (compare) visas ALDRIG nar debatt ar aktiv
{isCompare && !isDebate && <SpotlightArenaLayout />}

// DebateArena visas nar debatt ar aktiv
{isDebate && debateState && <DebateArenaLayout debateState={debateState} />}
```

---

### 4.6 `debate-settings-page.tsx` (Admin)

**Skvag**: `surfsense_web/components/admin/debate-settings-page.tsx`

- API-nyckel (password-falt)
- API Base URL
- TTS-modell (tts-1 / tts-1-hd)
- Hastighetsslider (0.25x - 4.0x)
- Rostkarta: 8 deltagare x 6 roster (alloy, echo, fable, nova, onyx, shimmer)
- Spara-knapp med Redis-persistens
- Anvandningsinstruktioner

---

### 4.7 `admin-debate-api.service.ts`

**Skvag**: `surfsense_web/lib/apis/admin-debate-api.service.ts`

```typescript
class AdminDebateApiService {
    getVoiceSettings(): Promise<DebateVoiceSettingsResponse>
    updateVoiceSettings(settings): Promise<DebateVoiceSettingsResponse>
}
```

Anvander Zod-validering via `baseApiService.get/put`.

---

## 5. Dataflode (SSE Events)

### Sekvensdiagram

```
Backend (debate_executor)     stream_new_chat.py (SSE bridge)     Frontend (new-chat-page)
========================     =============================     ========================

debate_init              -->  debate-init                  -->  setDebateState({...init})
  |
  |- debate_round_start  -->  debate-round-start           -->  update currentRound, status
  |
  |- debate_participant   -->  debate-participant-start     -->  add response with "speaking"
  |    _start
  |
  |- (model call...)
  |
  |- debate_participant   -->  debate-participant-end       -->  update response to "complete"
  |    _end
  |
  |- [voice] debate_voice -->  debate-voice-speaker         -->  debateAudio.onSpeakerChange
  |            _speaker
  |- [voice] debate_voice -->  debate-voice-chunk (xN)      -->  debateAudio.enqueueChunk
  |            _chunk
  |- [voice] debate_voice -->  debate-voice-done            -->  (auto-continues from queue)
  |            _done
  |
  |- (repeat for each participant)
  |
  |- debate_round_end    -->  debate-round-end             -->  mark round "complete"
  |
  |- (repeat for rounds 1-3)
  |
  |- debate_round_start  -->  (round 4, type "voting")     -->  status = "voting"
  |    (parallel voting)
  |
  |- debate_vote_result  -->  debate-vote-result (x8)      -->  append to votes[]
  |    (per participant)
  |
  |- debate_results      -->  debate-results               -->  status = "results", results obj
  |
  |- debate_synthesis    -->  debate-synthesis-complete     -->  status = "complete"
       _complete
```

---

## 6. Voice Debate Mode (/dvoice)

### Arkitekturstrategi: Strategy B (Pipelined Asyncio)

1. Deltagare genererar textsvar (vanlig debattflode)
2. **Direkt efter** varje textsvar skapas en asyncio.Task for TTS
3. TTS-tasken streamar PCM-chunks via `adispatch_custom_event`
4. Chunks gar via SSE-bridge till frontend
5. Frontend dekodar base64 -> PCM -> AudioBuffer
6. Uppspelning sker sekventiellt genom chunk-kon

### PCM-format

| Parameter | Varde |
|-----------|-------|
| Sample Rate | 24,000 Hz |
| Bit Depth | 16-bit signed LE |
| Channels | 1 (mono) |
| Chunk Size | ~4,800 bytes (~100ms) |
| Encoding | Base64 i SSE |

### TTS API

- **Provider**: OpenAI (direkt via httpx, INTE litellm)
- **Endpoint**: `POST /audio/speech`
- **Modell**: `tts-1` (standard) eller `tts-1-hd` (hog kvalitet)
- **roster**: alloy, echo, fable, nova, onyx, shimmer

### Frontend Audio Pipeline

```
SSE chunk (base64)
    -> atob() -> Uint8Array
    -> Int16Array view
    -> Float32Array (/ 32768)
    -> AudioBuffer (24kHz, 1ch)
    -> BufferSource -> GainNode -> AnalyserNode -> destination
```

---

## 7. Admin — Debatt-installningar

### Navigation

Admin sidebar → "Debatt" (Mic-ikon) → `/admin/debate`

### Installningar (Redis-persisterade)

| Falt | Typ | Default | Beskrivning |
|------|-----|---------|-------------|
| `api_key` | string | `""` | OpenAI TTS API-nyckel |
| `api_base` | string | `https://api.openai.com/v1` | TTS API base URL |
| `model` | string | `tts-1` | TTS-modell (tts-1, tts-1-hd) |
| `speed` | float | `1.0` | Hastighet (0.25 - 4.0) |
| `voice_map` | dict | Se DEFAULT_DEBATE_VOICE_MAP | Rostmappning per deltagare |

---

## 8. Admin Flow Pipeline

### Positioner (flow-graph-page.tsx)

```typescript
"node:debate_domain_planner":  { x: 240, y: 1920 }
"node:debate_round_executor":  { x: 800, y: 1920 }
"node:debate_round_1":         { x: 800, y: 2080 }
"node:debate_round_2":         { x: 1080, y: 2080 }
"node:debate_round_3":         { x: 1360, y: 2080 }
"node:debate_round_4_voting":  { x: 1640, y: 2080 }
"node:debate_oneseek_agent":   { x: 520, y: 2240 }
"node:debate_convergence":     { x: 1080, y: 2400 }
"node:debate_synthesizer":     { x: 1360, y: 2400 }
"node:debate_voice_pipeline":  { x: 240, y: 2400 }
```

Stage-farg: `debate: "hsl(38 92% 50%)"` (amber)

---

## 9. Prompt Registry

### Registrerade nycklar (16 st)

| Nyckel | Prompt-konstant | Beskrivning |
|--------|-----------------|-------------|
| `debate.supervisor.instructions` | `DEBATE_SUPERVISOR_INSTRUCTIONS` | Supervisor-instruktioner |
| `debate.domain_planner.system` | `DEFAULT_DEBATE_DOMAIN_PLANNER_PROMPT` | Domain planner |
| `debate.mini_planner.system` | `DEFAULT_DEBATE_MINI_PLANNER_PROMPT` | Mini-planner |
| `debate.mini_critic.system` | `DEFAULT_DEBATE_MINI_CRITIC_PROMPT` | Mini-critic |
| `debate.convergence.system` | `DEFAULT_DEBATE_CONVERGENCE_PROMPT` | Convergence |
| `debate.analysis.system` | `DEFAULT_DEBATE_ANALYSIS_PROMPT` | Synthesizer |
| `debate.research.system` | `DEFAULT_DEBATE_RESEARCH_PROMPT` | Research Agent |
| `debate.oneseek.system` | `ONESEEK_DEBATE_SYSTEM_PROMPT` | OneSeek systemprompt |
| `debate.round.1.introduction` | `DEBATE_ROUND1_INTRO_PROMPT` | Runda 1 |
| `debate.round.2.argument` | `DEBATE_ROUND2_ARGUMENT_PROMPT` | Runda 2 |
| `debate.round.3.deepening` | `DEBATE_ROUND3_DEEPENING_PROMPT` | Runda 3 |
| `debate.round.4.voting` | `DEBATE_ROUND4_VOTING_PROMPT` | Runda 4 |
| `debate.oneseek.round.1` | `ONESEEK_DEBATE_ROUND1_PROMPT` | OneSeek Runda 1 |
| `debate.oneseek.round.2` | `ONESEEK_DEBATE_ROUND2_PROMPT` | OneSeek Runda 2 |
| `debate.oneseek.round.3` | `ONESEEK_DEBATE_ROUND3_PROMPT` | OneSeek Runda 3 |
| `debate.oneseek.round.4` | `ONESEEK_DEBATE_ROUND4_PROMPT` | OneSeek Runda 4 |

### Prompt Override-system

Alla prompts kan overridas fran Admin -> Agent Prompts. Resolvering:
```python
resolved = (prompt_overrides or {}).get(key) or DEFAULT_CONSTANT
```

---

## 10. State Management

### Backend State (SupervisorState TypedDict)

| Nyckel | Typ | Reducer | Satt av |
|--------|-----|---------|---------|
| `debate_participants` | `list[dict]` | _replace | domain_planner |
| `debate_topic` | `str \| None` | _replace | domain_planner |
| `debate_current_round` | `int \| None` | _replace | round_executor |
| `debate_round_responses` | `dict[int, dict[str, str]]` | _replace | round_executor |
| `debate_votes` | `list[dict]` | _replace | round_executor |
| `debate_word_counts` | `dict[str, int]` | _replace | round_executor |
| `debate_status` | `str \| None` | _replace | round_executor, convergence |
| `debate_voice_settings` | `dict \| None` | _replace | input_state (fran Redis) |

### Frontend State (React useState)

```typescript
debateState: DebateState | null    // null = debatt inte aktiv
debateAudio: useDebateAudio(...)   // Voice audio hook
```

### Status-livscykel

```
null → initializing → round_1 → round_2 → round_3 → voting → results → complete
```

---

## 11. Algoritmdetaljer

### Rostning (Runda 4)

1. Alla deltagare roster **parallellt** (`asyncio.gather`)
2. Varje roster maste folja JSON-schema:
   ```json
   {"voted_for": "namn", "short_motivation": "max 200 tecken", "three_bullets": ["1", "2", "3"]}
   ```
3. Self-votes filtreras bort (`voter != voted_for`)
4. Rostraknas per modell
5. **Vinnare**: Flest roster
6. **Tiebreaker**: Hogst totalt ordantal over alla rundor

### Kontextuppbyggnad

```
kontext_for_participant(round, position):
    parts = ["Debattamne: {topic}"]
    for prev_round in 1..round-1:
        parts += [f"--- Runda {prev_round} ---"]
        for name, resp in prev_round_responses:
            parts += [f"[{name}]: {resp[:600]}"]
    if current_round_responses:
        parts += [f"--- Runda {round} (hittills) ---"]
        for name, resp in current_round_responses:
            parts += [f"[{name}]: {resp[:600]}"]
    return "\n".join(parts)
```

### OneSeek Tavily-sokning

- Gor valfri Tavily-sokning per runda (0-4 sökningar)
- Max 3 resultat per sokning, 300 tecken per resultat
- 15s timeout
- Sökresultat integreras i kontexten: `[Tavily Result] {title}: {content}`

---

## 12. Konfiguration

### Miljovariabler

| Variabel | Anvands av | Beskrivning |
|----------|-----------|-------------|
| `CELERY_BROKER_URL` | admin_debate_routes.py | Redis URL for debatt-installningar |
| `DEBATE_VOICE_API_KEY` | debate_voice.py | TTS API-nyckel (fallback) |
| `TTS_SERVICE_API_KEY` | debate_voice.py | TTS API-nyckel (andra fallback) |

### Admin-installningar (Redis)

Alla rostinstellningar lagras i Redis under nyckel `debate:voice_settings` som JSON.
Laddas vid varje /dvoice-anrop fran `stream_new_chat.py`.

---

## 13. Testning

### Backend

```bash
cd surfsense_backend
python -m pytest tests/ -v -k debate  # Kör debatt-specifika tester
```

### Frontend

Inga frontend-tester konfigurerade (se CLAUDE.md).

### Manuell testning

```
# Textdebatt
/debatt Bor AI regleras?

# Rostdebatt
/dvoice Ar klimatforändringarna manniskopaverkade?
```

### Verifiering

1. Alla 8 deltagare ska svara i varje runda
2. Ordning ska vara slumpmassig per runda
3. Rostning ska ske parallellt
4. Self-votes ska filtreras
5. Vinnare ska visas med korrekt rostantal
6. Voice: PCM-ljud ska spelas sekventiellt
7. Admin: Rostinstellningar ska sparas och laddas korrekt

---

## 14. Framtida arbete

### Planerat

- [ ] MP3-export av hel debatt (FFmpeg-merge av samlade PCM-chunks)
- [ ] STT-input (tal → debattamne)
- [ ] Turtagning med live audio-feedback (Kokoro local TTS som fallback)
- [ ] Streaming text under debatt (token-for-token istallet for hela svar pa en gang)
- [ ] Debattmallar (forslagda amnen)

### Potentiella forbattringar

- Rate limiting for TTS API-anrop (kostnadshantering)
- Fallback till litellm.aspeech() om OpenAI API failar
- Caching av TTS-resultat for upprepade debatter
- Web Worker for PCM-avkodning (avlasta main thread)
- Debatthistorik (spara och atervisa tidigare debatter)

---

## Filindex

### Backend (Python)

| Fil | Rad | Beskrivning |
|-----|-----|-------------|
| `app/agents/new_chat/debate_executor.py` | ~990 | Rundexekvering, rostning, convergence, syntes |
| `app/agents/new_chat/debate_prompts.py` | ~392 | Alla prompt-mallar |
| `app/agents/new_chat/debate_voice.py` | ~240 | TTS-pipeline med OpenAI SDK direkt |
| `app/agents/new_chat/supervisor_agent.py` | 6910-7010 | Debate subgraph-uppbyggnad |
| `app/agents/new_chat/supervisor_types.py` | 186-200 | State TypedDict-nycklar |
| `app/agents/new_chat/structured_schemas.py` | — | DebateVoteResult, DebateConvergenceResult |
| `app/agents/new_chat/prompt_registry.py` | 219-235, 654-750 | 16 registrerade promptnycklar |
| `app/tasks/chat/stream_new_chat.py` | 135-160, 1690-1700, 3096-3140 | Routing, SSE bridge |
| `app/routes/admin_debate_routes.py` | ~138 | REST API for rostinstellningar |
| `app/routes/admin_flow_graph_routes.py` | 340-400, 540-555 | Pipeline-noder och kanter |
| `app/routes/__init__.py` | 8, 88 | Router-registrering |

### Frontend (TypeScript/React)

| Fil | Beskrivning |
|-----|-------------|
| `contracts/types/debate.types.ts` | Alla TypeScript-interfaces och konstanter |
| `hooks/use-debate-audio.ts` | Web Audio API hook |
| `components/debate/debate-arena.tsx` | Huvudkomponent + VoiceControlBar |
| `components/admin/debate-settings-page.tsx` | Admin Debatt-sida |
| `components/admin/admin-layout.tsx` | Admin navigation (Debatt-tab) |
| `components/assistant-ui/assistant-message.tsx` | Mutual exclusion guard |
| `app/admin/debate/page.tsx` | Admin route-sida |
| `app/dashboard/[search_space_id]/new-chat/new-chat-page.tsx` | SSE-hanterare, state, context providers |
| `lib/apis/admin-debate-api.service.ts` | API-service for admin-installningar |
| `components/admin/flow-graph-page.tsx` | Pipeline-nodpositioner |

### Mockups

| Fil | Beskrivning |
|-----|-------------|
| `docs/debate-mode/mockups/01-debate-arena.html` | Debattarena UI-mockup |
| `docs/debate-mode/mockups/02-voting-results.html` | Rostresultat-mockup |
| `docs/debate-mode/mockups/03-podcast-presentation.html` | Podcast-presentation |
| `docs/debate-mode/mockups/04-round-timeline.html` | Tidslinje-mockup |
| `docs/debate-mode/mockups/05-mobile-debate.html` | Mobil-mockup |
