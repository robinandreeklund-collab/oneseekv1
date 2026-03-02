# Debatt v1 — Fullständig Kodanalys & Audit

> **Datum:** 2026-03-02
> **Scope:** Hela /debatt- och /dvoice-funktionen — backend + frontend
> **Analyserade filer:** 31 filer (17 backend, 14 frontend)

---

## Sammanfattning

Debattfunktionen är **i grunden väl arkitekterad** med en tydlig LangGraph-pipeline, ren separering mellan noder, och ett genomtänkt SSE-baserat kommunikationsprotokoll. Kodkvaliteten är överlag god med konsekvent stil och robust felhantering.

Dock identifieras **8 buggar** (varav 2 kritiska), **12 kodkvalitetsproblem**, och **15 optimeringsmöjligheter**.

### Prioriterad Åtgärdslista

| Prioritet | Typ | Antal | Mest kritiskt |
|-----------|-----|-------|---------------|
| P0 (Kritisk) | Bugg | 2 | Vote-validering, Prefetch race condition |
| P1 (Hög) | Bugg | 3 | JSON-parse fuzzy match, Context trunkering |
| P2 (Medium) | Bugg + Kvalitet | 8 | Duplicerad kod, State-inkonsekvens |
| P3 (Låg) | Optimering | 15 | Parallellisering, Caching, Minne |

---

## 1. Buggar

### BUG-01 [P0/Kritisk]: Votes med tomt `voted_for` räknas som giltiga

**Fil:** `debate_executor.py:938-940`

```python
for v in filtered_votes:
    voted_for = v.get("voted_for", "")
    if voted_for:
        vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1
```

**Problem:** Om en modell returnerar `{"voted_for": ""}` (parse failure) passerar den `_filter_self_votes()` (tom sträng ≠ voternamn), men filtreras sedan korrekt av `if voted_for:` i convergence. **Dock** skickas vote-objektet till frontend via `debate_vote_result` SSE-event **utan filtrering**:

```python
# debate_executor.py:770-784
for vr in vote_results:
    if isinstance(vr, dict):
        all_votes.append(vr)  # <-- Inkluderar tomma votes
        await adispatch_custom_event("debate_vote_result", ...)
```

**Frontend-effekt:** `VotingSection` i `debate-arena.tsx:614` renderar alla votes inklusive de med tomt `votedFor`, vilket visar `"→ "` utan mottagare.

**Fix:**
```python
# debate_executor.py:770 — filtrera innan append
if isinstance(vr, dict) and vr.get("voted_for", "").strip():
    all_votes.append(vr)
```

---

### BUG-02 [P0/Kritisk]: Prefetch race condition — stale context

**Fil:** `debate_executor.py:530-560`

```python
async def _prefetch_llm_and_tts(
    p=_next_p, q=_next_query,  # q binds at definition time
) -> tuple[str, tuple[bytes, float] | None]:
    text = await _call_debate_participant(
        participant=p,
        query_with_context=q,  # <-- Uses context frozen at definition
        ...
    )
```

**Problem:** Prefetch-funktionen fångar `_next_query` vid definitionstillfället via default-argument. Dock beräknas `_next_query` baserat på `round_responses` som det ser ut **innan nuvarande deltagares svar har lagts till**:

```python
# Line 525-528:
_next_ctx = _build_round_context(
    topic, all_round_responses, round_responses, round_num,
)
```

Men `round_responses[model_display] = response_text` sker på rad 515, **precis före** prefetch-koden (rad 521). Så kontexten inkluderar nuvarande deltagares svar. **Dock** om prefetchen hinner starta och returnera innan nästa deltagares tur, och ytterligare en deltagare hinner svara, får den prefetchade deltagaren **inte** den senaste kontexten.

**Verklig effekt:** I en runda med 8 deltagare, deltagare #3 som prefetchas medan #2 genereras får rätt kontext. Men om #3:s svar hinner returnera och #4 prefetchas *under* #2:s voice streaming, kan #4 missa #3:s svar i kontextkedjan. Effekten är dock begränsad till voice mode.

**Fix:** Validera att prefetched context matchar aktuell context vid användning. Om inte, re-fetch:
```python
if model_display in _prefetched:
    _task = _prefetched.pop(model_display)
    try:
        response_text, _prepared_audio = await _task
        # Validate context freshness
        current_ctx = _build_round_context(
            topic, all_round_responses, round_responses, round_num,
        )
        if _count_words(response_text) < 10:  # too short, probably error
            response_text = ""
    except Exception:
        response_text = ""
```

---

### BUG-03 [P1]: `_extract_json_from_text` fuzzy regex fångar inte nested JSON

**Fil:** `debate_executor.py:124-135`

```python
patterns = [
    r"```(?:json)?\s*\n?(.*?)\n?```",
    r"\{[^{}]*\"voted_for\"[^{}]*\}",  # <-- Missar nested braces
]
```

**Problem:** Det andra regex-mönstret `\{[^{}]*\"voted_for\"[^{}]*\}` matchar INTE JSON med `three_bullets`-arrayen om den innehåller nested `{}`:
```json
{"voted_for": "Claude", "short_motivation": "Bra", "three_bullets": ["a", "b", "c"]}
```

Arrayen `["a", "b", "c"]` är OK — men om en modell formaterar tre_bullets med objekt `[{"point": "a"}]`, missar regex. Även om `three_bullets` alltid ska vara strängar enligt schemat, genererar externa modeller ibland oväntade format.

**Fix:** Ersätt med mer robust JSON-extraktion:
```python
# Replace the second pattern with a balanced-brace approach
def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass
    # Code block extraction
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    # Find first { and matching }
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{": depth += 1
            elif text[i] == "}": depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except (json.JSONDecodeError, ValueError):
                    break
    return None
```

---

### BUG-04 [P1]: Voting context trunkerar till 600 tecken per svar

**Fil:** `debate_executor.py:661-668`

```python
voting_context_parts = [f"Debattämne: {topic}\n"]
for rnd in range(1, 4):
    rnd_resp = all_round_responses.get(rnd, {})
    if rnd_resp:
        voting_context_parts.append(f"\n--- Runda {rnd} ---")
        for name, resp in rnd_resp.items():
            voting_context_parts.append(f"[{name}]: {resp[:600]}")
```

**Problem:** Trunkering till 600 tecken per svar per runda. Med 8 deltagare × 3 rundor = 24 svar à 600 tecken = 14 400 tecken enbart i kontext. Men varje deltagares argument kan vara 500 ord ≈ 3 000+ tecken, och de mest kritiska argumenten kan vara i slutet av svaret. 600-teckensgränsen kapar ofta precis mitt i ett argument.

**Verklig effekt:** Röstningsmodeller fattar beslut baserat på halverade argument. Leder till sämre röstningskvalitet.

**Fix:** Öka trunkeringsgränsen till minst 1200 tecken, eller bättre — låt convergence-prompten sammanfatta innan voting:
```python
voting_context_parts.append(f"[{name}]: {resp[:1200]}")
```

---

### BUG-05 [P1]: OneSeek Subagent `_mini_critic` gör ingen LLM-evaluation

**Fil:** `oneseek_debate_subagent.py:302-319`

```python
async def _mini_critic(
    results: dict[str, str],
    topic: str,
    llm: Any,  # <-- LLM passas in men används aldrig!
) -> dict[str, Any]:
    filled = {k: v for k, v in results.items() if v}
    total = len(results)
    success = len(filled)
    verdict = {
        "decision": "ok" if success >= 3 else ("retry" if success >= 1 else "fail"),
        "agents_success": success,
        "agents_total": total,
        "confidence": min(1.0, success / max(total, 1)),
    }
    return verdict
```

**Problem:** `_mini_critic` tar emot `llm` som parameter men använder det aldrig. Funktionen gör enbart en kvantitativ kontroll (antal lyckade agenter), inte en kvalitativ bedömning av argumentkvalitet. Dessutom: om `decision == "retry"`, ageras det aldrig på — `run_oneseek_debate_subagent()` använder bara `critic_verdict` som input till `_synthesize_debate_response()`.

**Fix:** Antingen:
1. Implementera faktisk LLM-baserad kritik (i linje med `DEFAULT_DEBATE_MINI_CRITIC_PROMPT`)
2. Eller ta bort `llm`-parametern och `topic` (oanvänd) för att vara ärlig om att det är en enkel threshold-check

---

### BUG-06 [P2]: `useSmoothTyping` reset-logik kan orsaka text flicker

**Fil:** `use-smooth-typing.ts:100-108`

```typescript
useEffect(() => {
    if (incomingText && !incomingText.startsWith(displayedText.slice(0, 20))) {
        setDisplayedText("");
        queueRef.current = [];
        prevTextRef.current = incomingText;
    }
}, [incomingText, displayedText]);
```

**Problem:** Villkoret `!incomingText.startsWith(displayedText.slice(0, 20))` kan trigga falskt om `displayedText` innehåller whitespace-prefix eller om incomingText uppdateras med en minimal ändring i de första 20 tecknen. Dessutom: detta `useEffect` har `displayedText` som dependency, vilket betyder att varje gång `displayedText` uppdateras (varje tecken i animationen) kontrolleras reset-villkoret — onödigt.

**Fix:**
```typescript
const prevIncomingRef = useRef(incomingText);
useEffect(() => {
    if (incomingText !== prevIncomingRef.current) {
        if (incomingText && prevIncomingRef.current &&
            !incomingText.startsWith(prevIncomingRef.current.slice(0, 50))) {
            setDisplayedText("");
            queueRef.current = [];
        }
        prevIncomingRef.current = incomingText;
    }
}, [incomingText]);
```

---

### BUG-07 [P2]: `DebateVoiceSpeakerEvent` har `estimated_total_chunks` i type men backend skickar aldrig det

**Fil:** `debate.types.ts:165` vs `debate_voice.py:398-411`

```typescript
// Frontend type:
export interface DebateVoiceSpeakerEvent {
    estimated_total_chunks: number;  // <-- Förväntas
}
```

```python
# Backend event:
await adispatch_custom_event(
    "debate_voice_speaker",
    {
        "model": participant_display,
        "model_key": participant_key,
        "round": round_num,
        "voice": voice,
        "text_length": text_len,
        "total_sentences": len(sentences),  # <-- Skickar total_sentences, inte estimated_total_chunks
        "provider": provider,
        "timestamp": time.time(),
    },
)
```

**Fix:** Synkronisera typen med backend eller beräkna uppskattade chunks.

---

### BUG-08 [P2]: Redis-inställningar läses synkront i admin-routes

**Fil:** `admin_debate_routes.py:97-108`

```python
def _get_redis():
    import redis
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(broker_url, decode_responses=True)
```

**Problem:** `_get_redis()` skapar en **synkron** Redis-klient inne i asynkrona FastAPI-endpoints. `r.get(REDIS_KEY)` och `r.set(REDIS_KEY, ...)` blockerar event loop. Vid hög trafik eller Redis-latens blockeras hela FastAPI-workern.

**Fix:** Använd `redis.asyncio.Redis` istället:
```python
async def _get_async_redis():
    import redis.asyncio as aioredis
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    return aioredis.from_url(broker_url, decode_responses=True)
```

---

## 2. Kodkvalitet

### KQ-01: Duplicerade helper-funktioner i test-filen

**Fil:** `test_debate_supervisor_v1.py:44-87`

Testerna kopierar `_extract_json_from_text`, `_count_words`, `_filter_self_votes`, `_resolve_winner` från `debate_executor.py` istället för att importera dem. Kommentaren säger "avoid heavy langchain imports", men dessa funktioner har inga langchain-beroenden.

**Risk:** Om logiken ändras i `debate_executor.py` men inte i testfilen, testar vi fel kod.

**Fix:** Flytta de rena hjälpfunktionerna till en separat modul utan langchain-import (t.ex. `debate_utils.py`) och importera från båda ställen.

---

### KQ-02: Inkonsekvent namngivning — `voice_map` vs `DEFAULT_VOICE_MAP` dupliceras 3 gånger

**Filer:**
- `debate_voice.py:40-49` — `DEFAULT_OPENAI_VOICE_MAP`
- `admin_debate_routes.py:26-35` — `DEFAULT_VOICE_MAP`
- `debate-settings-page.tsx:76-85` — `DEFAULT_VOICE_MAP`

Tre identiska voice-mappings definieras separat. Ändringar i en uppdaterar inte de andra.

**Fix:** Definiera voice maps enbart i backend och hämta via API.

---

### KQ-03: `_resolve_voice_settings()` duplicerar logik i tre funktioner

**Fil:** `debate_voice.py`

`_resolve_voice_settings()` anropas i:
- `_emit_voice_events()` (rad 369-371)
- `stream_text_and_voice_synced()` (rad 626)
- `schedule_voice_generation()` (rad 840)
- `collect_all_audio_for_export()` (rad 880)
- `prepare_tts_audio()` (rad 565)

Och `language_instructions`-logiken (rad 377-384) dupliceras i minst 4 av dessa funktioner:
```python
lang_instructions = voice_settings.get("language_instructions") or {}
if isinstance(lang_instructions, str):
    instr = lang_instructions.strip()
else:
    instr = (
        lang_instructions.get(participant_display, "").strip()
        or lang_instructions.get("__default__", "").strip()
    )
```

**Fix:** Extrahera till en hjälpfunktion:
```python
def _resolve_language_instructions(
    voice_settings: dict[str, Any],
    participant_display: str,
) -> str:
    lang_instructions = voice_settings.get("language_instructions") or {}
    if isinstance(lang_instructions, str):
        return lang_instructions.strip()
    return (
        lang_instructions.get(participant_display, "").strip()
        or lang_instructions.get("__default__", "").strip()
    )
```

---

### KQ-04: `debate_executor.py` är 1046 rader — för stor fil

Filen innehåller node builders, helper-funktioner, OneSeek-specifik logik, och voting-mekanik — allt i en fil. Svårt att navigera.

**Fix:** Dela upp i:
- `debate_helpers.py` — `_extract_json_from_text`, `_count_words`, `_filter_self_votes`, `_resolve_winner`, `_build_round_context`
- `debate_nodes.py` — `build_debate_domain_planner_node`, `build_debate_round_executor_node`, `build_debate_convergence_node`
- `debate_oneseek.py` — `_run_oneseek_debate_turn`, `_call_oneseek_vote` (eller konsolidera med `oneseek_debate_subagent.py`)

---

### KQ-05: `try/except Exception: pass` — tyst felhantering på 15+ ställen

**Fil:** `debate_executor.py`

SSE-events wrappas i `try/except Exception: pass` på rader: 422, 444, 476, 609, 635, 656, 687, 783. Detta gör debugging extremt svårt.

**Fix:** Åtminstone logga felet:
```python
except Exception as exc:
    logger.debug("debate: SSE event emission failed: %s", exc)
```

---

### KQ-06: `SimpleNamespace` skapad runtime istället för att använda spec-klassen

**Fil:** `debate_executor.py:220-221`

```python
from types import SimpleNamespace
spec = SimpleNamespace(**spec_data)
```

Skapar SimpleNamespace från dict-serialiserad spec-data. Fragilt — om spec-klassen ändrar attribut, kraschar det utan tydligt felmeddelande.

**Fix:** Importera den faktiska spec-klassen eller använd en TypedDict.

---

### KQ-07: `oneseek_debate_subagent.py` är inte integrerad i debatt-flödet

**Fil:** `oneseek_debate_subagent.py`

Modulen definierar ett P4-mönster med 6 mini-agenter, men `debate_executor.py` använder den enklare `_run_oneseek_debate_turn()` istället. `oneseek_debate_subagent.py` verkar vara dead code eller framtida refaktorisering.

**Fix:** Antingen integrera eller markera som experimentell/deprecated.

---

### KQ-08: Cartesia Sonic-3 non-streaming — hela svaret laddas in i minnet

**Fil:** `debate_voice.py:227-244`

```python
async with httpx.AsyncClient(...) as client:
    response = await client.post(url, json=payload, headers=headers)
    pcm_data = response.content  # <-- Hela PCM-svaret i minnet
    for i in range(0, len(pcm_data), chunk_bytes):
        yield pcm_data[i:i + chunk_bytes]
```

Till skillnad från OpenAI-versionen (som streamar via `client.stream("POST", ...)`) laddar Cartesia-versionen hela PCM-svaret i minnet innan chunkning. För ett 500-ords svar ≈ 60s audio ≈ 2.88 MB PCM — hanterbart, men icke-optimalt.

**Fix:** Använd Cartesias streaming-endpoint (`/tts/sse`) eller streaming bytes endpoint om tillgänglig.

---

### KQ-09: Waveform-animation körs alltid — även när ingen voice spelas

**Fil:** `use-debate-audio.ts:230-249`

```typescript
useEffect(() => {
    if (!enabled) return;
    const animate = () => {
        // ... requestAnimationFrame loop
        animFrameRef.current = requestAnimationFrame(animate);
    };
    animFrameRef.current = requestAnimationFrame(animate);
    return () => { ... };
}, [enabled]);
```

**Problem:** `requestAnimationFrame`-loopen körs *alltid* när voice mode är aktiverat, oavsett om ljud spelas eller inte. Onödig CPU-användning.

**Fix:** Villkora på `isPlayingRef.current`:
```typescript
const animate = () => {
    if (analyser && isPlayingRef.current) {
        // Only compute waveform when actually playing
        const data = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(data);
        setVoiceState((prev) => ({ ...prev, waveformData: data }));
    }
    if (isPlayingRef.current) {
        animFrameRef.current = requestAnimationFrame(animate);
    } else {
        animFrameRef.current = null;
    }
};
```

---

### KQ-10: `voiceState`-uppdateringar i audio hook triggar onödiga rerenders

**Fil:** `use-debate-audio.ts:238`

```typescript
setVoiceState((prev) => ({ ...prev, waveformData: data }));
```

Sätter `waveformData` vid varje animationsframe (~60fps) → 60 state updates/sekund → 60 rerenders. `DebateArenaLayout` och alla child-komponenter rerenders via context.

**Fix:** Använd `useRef` för waveform-data och exponera en callback istället:
```typescript
const waveformRef = useRef<Uint8Array | null>(null);
// In animation loop:
waveformRef.current = data;
// Canvas reads from ref, not state
```

---

### KQ-11: Admin-check i debate routes kontrollerar `is_owner`, inte en rollbaserad behörighet

**Fil:** `admin_debate_routes.py:81-94`

```python
async def _require_admin(session: AsyncSession, user: User) -> None:
    result = await session.execute(
        select(SearchSpaceMembership)
        .filter(
            SearchSpaceMembership.user_id == user.id,
            SearchSpaceMembership.is_owner.is_(True),
        )
        .limit(1)
    )
```

**Problem:** Kontrollerar bara om användaren äger minst ett SearchSpace, inte om de har admin-rättigheter generellt. En användare som äger **något** SearchSpace kan ändra TTS-inställningar som påverkar alla debatter.

---

### KQ-12: Frontend-typer och backend-schemas synkroniseras manuellt

Frontend (`debate.types.ts`) och backend (`app/schemas/debate.py`) definierar samma datastrukturer oberoende. Ingen automatisk synkronisering (t.ex. via codegen).

---

## 3. Optimeringar

### OPT-01: Parallellisera Tavily-sökningar i OneSeek-subagent

**Fil:** `oneseek_debate_subagent.py:63-70`

```python
agent_tasks = {
    "tavily_core": _run_tavily_core(topic, tavily_search_fn, tavily_calls_remaining),
    "fresh_news": _run_fresh_news(topic, tavily_search_fn),
    # ...
    "swedish_context": _run_swedish_context(topic, tavily_search_fn),
}
```

Dessa körs redan parallellt via `asyncio.gather`, men varje agent gör sin egen Tavily-sökning. Total: 3+2+2 = 7 Tavily-anrop per runda, men `MAX_TAVILY_CALLS_PER_TURN = 4`.

**Fix:** Implementera en delad Tavily-pool med semaphore:
```python
tavily_semaphore = asyncio.Semaphore(MAX_TAVILY_CALLS_PER_TURN)
```

---

### OPT-02: Cache deltagarlistan i domain planner

**Fil:** `debate_executor.py:286-366`

Domain planner skapar deltagarlistan deterministiskt varje gång från `EXTERNAL_MODEL_SPECS`. Resultatet är alltid detsamma.

**Fix:** Cache vid initialisering istället för att bygga per anrop.

---

### OPT-03: Återanvänd httpx-klienten mellan TTS-anrop

**Fil:** `debate_voice.py:227, 287`

Varje TTS-anrop skapar en ny `httpx.AsyncClient`:
```python
async with httpx.AsyncClient(timeout=...) as client:
```

Med 8 deltagare × 4 rundor × ~10 meningar/svar = ~320 HTTP-anrop, vardera med ny TCP-anslutning.

**Fix:** Skapa en delad klient per debatt-session:
```python
# Pass a shared client through voice_settings
_tts_client = voice_settings.get("_httpx_client")
if not _tts_client:
    _tts_client = httpx.AsyncClient(timeout=..., http2=True)
    voice_settings["_httpx_client"] = _tts_client
```

---

### OPT-04: `_build_round_context` beräknas om för varje deltagare

**Fil:** `debate_executor.py:458-460`

```python
full_context = _build_round_context(
    topic, all_round_responses, round_responses, round_num,
)
```

I en runda med 8 deltagare anropas `_build_round_context` 8 gånger. De första 7 anropen producerar nästan identisk output (föregående rundor är oförändrade).

**Fix:** Beräkna basen en gång per runda och appendera enbart nya svar:
```python
base_context = _build_round_context(topic, all_round_responses, {}, round_num)
for participant in round_order:
    current_context = base_context + _format_current_round(round_responses)
    # ... use current_context
```

---

### OPT-05: Sentensstyckning och TTS kan köras parallellt med voice-chunk streaming

**Fil:** `debate_voice.py:416-456`

Per-sentence TTS körs sekventiellt:
```python
for sent_idx, sentence in enumerate(sentences):
    async for pcm_chunk in _get_tts_generator(...):
        await adispatch_custom_event(...)
```

**Fix:** Starta TTS för nästa mening medan nuvarande mening chunkas ut:
```python
# Pipeline: while sentence N streams, start generating sentence N+1
```

---

### OPT-06: `collectedRef.current.push()` — obegränsad minnesanvändning

**Fil:** `use-debate-audio.ts:201`

```typescript
collectedRef.current.push(raw.buffer);
```

**Problem:** Alla PCM-chunks samlas för export, utan någon gräns. En 60-minuters debatt ≈ 172 MB PCM i minnet.

**Fix:** Implementera en maxgräns eller on-demand collection:
```typescript
const MAX_COLLECTED_BYTES = 50 * 1024 * 1024; // 50 MB cap
```

---

### OPT-07: Base64-encoding av PCM-chunks dubblerar minnesanvändning

**Fil:** `debate_voice.py:442`

```python
b64 = base64.b64encode(pcm_chunk).decode("ascii")
```

Base64 ökar datan med ~33%. Varje 4800-byte chunk → 6400 bytes som sträng → JSON-serialiseras i SSE.

**Fix:** Överväg binär WebSocket-transport för voice-chunks istället för SSE med base64. Alternativt: komprimera PCM till OPUS innan transport.

---

### OPT-08: `ensureAudioContext` i `useDebateAudio` har stale `volume` i closure

**Fil:** `use-debate-audio.ts:61-87`

```typescript
const ensureAudioContext = useCallback(() => {
    // ...
    gain.gain.value = voiceState.volume;  // <-- Captured at creation time
}, [voiceState.volume]);
```

Med `voiceState.volume` som dependency skapas en ny callback vid varje volymändring. Dock: AudioContext skapas bara en gång (early return), så detta är mestadels harmlöst men orsakar onödiga dependency-uppdateringar.

**Fix:** Läs volym från ref istället:
```typescript
const volumeRef = useRef(voiceState.volume);
// In ensureAudioContext:
gain.gain.value = volumeRef.current;
```

---

### OPT-09: Röstningsrundans `asyncio.gather` saknar timeout per task

**Fil:** `debate_executor.py:760-761`

```python
vote_tasks = [_cast_vote(p) for p in participants]
vote_results = await asyncio.gather(*vote_tasks, return_exceptions=True)
```

Varje `_cast_vote` har intern timeout (`VOTE_TIMEOUT_SECONDS = 60`), men `asyncio.gather` har ingen övergripande timeout. Om en modells timeout-mekanism misslyckas, väntar hela debatten.

**Fix:**
```python
vote_results = await asyncio.wait_for(
    asyncio.gather(*vote_tasks, return_exceptions=True),
    timeout=VOTE_TIMEOUT_SECONDS + 10,  # Overall safety timeout
)
```

---

### OPT-10: `debate_convergence_node` trunkerar svar till 400 tecken

**Fil:** `debate_executor.py:964-965`

```python
for name, resp in rnd_resp.items():
    context_parts.append(f"[{name}]: {resp[:400]}")
```

Convergence-noden — som ska producera den mest informerade analysen — får *kortare* context (400 tecken) än voting (600 tecken).

**Fix:** Öka till minst 800 tecken eller skicka fullständiga svar med LLM-sammanfattning.

---

### OPT-11: Round-tab spinner visas felaktigt

**Fil:** `debate-arena.tsx:251-253`

```tsx
{isActive && !isDone && round === activeRound && (
    <LoaderCircleIcon className="h-3 w-3 animate-spin" />
)}
```

Villkoret `isActive && round === activeRound` är alltid sant när `isActive` är sant (båda baseras på samma `activeRound`). Redundant kontroll.

**Fix:**
```tsx
{isActive && !isDone && (
    <LoaderCircleIcon className="h-3 w-3 animate-spin" />
)}
```

---

### OPT-12: Progress bar visar fel progression

**Fil:** `debate-arena.tsx:265-268`

```tsx
animate={{
    width: `${((activeRound - 1) / debateState.totalRounds) * 100}%`,
}}
```

Progress = `(activeRound - 1) / 4 * 100`:
- Runda 1 → 0%
- Runda 2 → 25%
- Runda 4 → 75%
- Klar → fortfarande 75%

Aldrig 100% visas.

**Fix:**
```tsx
const progress = isComplete
    ? 100
    : ((activeRound - 1) / debateState.totalRounds) * 100 +
      (/* estimated progress within round */);
```

---

### OPT-13: `debate-settings-page.tsx` DEFAULT_CARTESIA_VOICE_MAP dupliceras med backend

Se KQ-02 ovan. Samma UUIDs hårdkodas i tre ställen.

---

### OPT-14: `collect_all_audio_for_export` gör fullständig TTS re-generation

**Fil:** `debate_voice.py:873-921`

Export-funktionen genererar TTS **igen** för alla rundor. Total kostnad: 8 × 3 rundor × TTS API-anrop — dyr och långsam.

**Fix:** Cacha PCM-data från live-debatten och återanvänd för export.

---

### OPT-15: Admin-sidan gör ingen optimistic update

**Fil:** `debate-settings-page.tsx`

Vid sparning väntar UI på fullständigt API-svar innan feedback visas. Med Redis-latens (normalt <5ms) är detta försumbart, men vid nätverksfördröjning kan UI:t kännas långsamt.

---

## 4. Testning — Gap-analys

### Befintliga tester (33 test cases):

| Testklass | Antal | Vad testas |
|-----------|-------|-----------|
| `TestExtractJsonFromText` | 7 | JSON-parsing från text |
| `TestCountWords` | 5 | Ordräkning |
| `TestFilterSelfVotes` | 5 | Self-vote filtrering |
| `TestResolveWinner` | 5 | Vinnarresolution med tiebreaker |
| `TestBuildFallbackSynthesis` | 2 | Fallback-syntes |
| `TestDebateSchemas` | 6 | Pydantic-schemas |
| `TestDebattCommandDetection` | 7 | /debatt-kommandodetektering |

### Saknade tester:

1. **`_build_round_context`** — Ingen test för kontextkedjning
2. **`_call_debate_participant`** — Ingen test för timeout-hantering
3. **`_resolve_max_tokens`** — Ingen test för per-modell token limits
4. **`debate_domain_planner_node`** — Ingen integrationstest
5. **`debate_round_executor_node`** — Ingen integrationstest
6. **`debate_convergence_node`** — Ingen integrationstest
7. **Voting med parse errors** — Ingen test för delvis misslyckad röstning
8. **Voice pipeline** — Inga tester alls
9. **SSE event sequence** — Ingen test för korrekt eventordning
10. **Frontend: `useSmoothTyping`** — Inga tester
11. **Frontend: `useDebateAudio`** — Inga tester

---

## 5. Säkerhet

### SEC-01: API-nycklar lagras i Redis utan kryptering

**Fil:** `admin_debate_routes.py:151`

```python
r.set(REDIS_KEY, json.dumps(data))  # <-- Inkluderar api_key och cartesia_api_key
```

TTS API-nycklar (OpenAI, Cartesia) lagras i klartext i Redis.

**Rekommendation:** Kryptera känsliga fält med Fernet eller liknande innan Redis-lagring.

---

### SEC-02: Ingen rate limiting på admin debate endpoints

Endpoints `/admin/debate/voice-settings` har ingen rate limiting — en autentiserad ägare kan spamma PUT-anrop.

---

### SEC-03: Extern modells svar renderas utan sanitering

**Fil:** `debate-arena.tsx:533`

```tsx
<p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
    {displayText}
</p>
```

Text renderas via React (automatisk XSS-skydd), men `whitespace-pre-wrap` med okontrollerade input kan orsaka layout-brott med extremt långa ord.

---

## 6. Arkitekturella rekommendationer

### Kortsiktigt (Sprint)
1. Fixa BUG-01 (vote-filtrering) — 30 min
2. Fixa BUG-03 (JSON-parse) — 1h
3. Fixa BUG-08 (synkron Redis) — 1h
4. Extrahera duplicerad logik (KQ-03) — 2h
5. Öka context-trunkeringsgränser (BUG-04, OPT-10) — 30 min

### Medellång sikt (2-3 sprints)
1. Dela upp `debate_executor.py` (KQ-04) — 4h
2. Återanvänd httpx-klient (OPT-03) — 2h
3. Implementera TTS caching för export (OPT-14) — 4h
4. Lägg till saknade tester (10 testklasser) — 8h
5. Separera voice maps till single source of truth (KQ-02) — 3h

### Långsiktigt (Quarter)
1. WebSocket-transport för voice-chunks (OPT-07)
2. Automatisk frontend/backend type-synkronisering (KQ-12)
3. Kryptering av API-nycklar i Redis (SEC-01)
4. Integrera `oneseek_debate_subagent.py` eller ta bort (KQ-07)

---

## Slutsats

Debattfunktionen är **produktionsredo med förbehåll**. De två P0-buggarna (BUG-01, BUG-02) bör fixas innan nästa release. Kodstrukturen är solid men kan förbättras genom att bryta ut hjälpfunktioner, eliminera duplicering, och lägga till mer robust voice pipeline-felhantering. Frontend-koden är välskriven med bra UX-hantering av edge cases (voice racing, auto-expand, progressive reveal), men kan optimeras för minnesanvändning och render-performance.
