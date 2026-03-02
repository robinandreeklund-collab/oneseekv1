# Compare v1 — Fullständig Kodanalys & Audit

> **Datum:** 2026-03-02
> **Scope:** Hela /compare-funktionen — backend + frontend (Spotlight Arena)
> **Analyserade filer:** 24 filer (14 backend, 10 frontend)
> **Senast uppdaterad:** 2026-03-02 (initial analys)

---

## Sammanfattning

Compare-funktionen (Spotlight Arena) är **välarkitekterad** med en tydlig P4-baserad pipeline, ren separering mellan domänplanering, subagent-spawning, kriteriebaserad bedömning, convergence och syntes. Koden följer konsekvent det etablerade P4-mönstret med bra felhantering och progressiv SSE-streaming.

Den initiala analysen identifierar **6 buggar** (varav 1 kritisk), **8 kodkvalitetsproblem**, **10 optimeringsmöjligheter** och **2 säkerhetsobservationer**.

### Åtgärdsstatus

| Kategori | Totalt | Fixade | Kvar | IDs |
|----------|--------|--------|------|-----|
| Buggar (P0–P2) | 6 | 0 | **6** | BUG-01–BUG-06 |
| Kodkvalitet (KQ) | 8 | 0 | **8** | KQ-01–KQ-08 |
| Optimeringar (OPT) | 10 | 0 | **10** | OPT-01–OPT-10 |
| Säkerhet (SEC) | 2 | 0 | **2** | SEC-01–SEC-02 |
| **Totalt** | **26** | **0** | **26** | |

### Prioriterad Åtgärdslista

| Prioritet | Typ | Antal | Mest kritiskt |
|-----------|-----|-------|---------------|
| P0 (Kritisk) | Bugg | 1 | Module-level Semaphore i multi-worker |
| P1 (Hög) | Bugg + Kvalitet | 3 | Silent exception swallowing, duplikated sanitering |
| P2 (Medium) | Bugg + Kvalitet | 8 | Legacy dead code, inkonsekvent poäng-källa |
| P3 (Låg) | Optimering | 14 | Parallellisering, caching, minnesbesparing |

---

## 1. Buggar

### BUG-01 [P0/Kritisk]: Module-level asyncio.Semaphore i compare_criterion_evaluator — EJ FIXAD ⚠️

**Fil:** `compare_criterion_evaluator.py:39-40`

```python
_MAX_CONCURRENT = 4
_GLOBAL_CRITERION_SEM = asyncio.Semaphore(_MAX_CONCURRENT)
```

**Problem:** `asyncio.Semaphore` skapas på modul-nivå. Om applikationen kör multiple event loops (t.ex. vid Celery workers, tester med `pytest-asyncio`, eller hot reload) binds semaforen till den event loop som importerar modulen först. Efterföljande event loops som försöker använda `async with _GLOBAL_CRITERION_SEM` kan få `RuntimeError: Task attached to a different loop` eller, i nyare Python (3.10+), inga fel men semaforen skyddar inte korrekt mellan loopar (den har ingen effekt i en ny loop).

**Verklig risk:** I produktion med uvicorn + single worker är risken låg (en event loop). Men vid:
- Celery workers (var och en med egen loop): Semaforen delas inte → 4 × antal workers concurrent calls
- `pytest` med `event_loop_policy`: Alla tester delar samma modul-semafor → potentiella deadlocks
- Uvicorn med `--workers > 1`: Varje process importerar sin egen → OK (process-isolering), men
  om man bytar till `--reload` under utveckling kan det hända

**Fix:**
```python
# Alternativ 1: Lazy initialization per event loop
import weakref

_loop_semaphores: weakref.WeakValueDictionary[int, asyncio.Semaphore] = (
    weakref.WeakValueDictionary()
)

def _get_criterion_sem() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    sem = _loop_semaphores.get(loop_id)
    if sem is None:
        sem = asyncio.Semaphore(_MAX_CONCURRENT)
        _loop_semaphores[loop_id] = sem
    return sem

# I _invoke_criterion_llm:
async with _get_criterion_sem():
    ...
```

```python
# Alternativ 2: Skapa semaforen i spawner-noden och skicka den
# som parameter (ren dependency injection, enklare att testa)
```

---

### BUG-02 [P1/Hög]: Silent exception swallowing i on_criterion_complete callback — EJ FIXAD ⚠️

**Fil:** `compare_criterion_evaluator.py:316-317` och `compare_executor.py:367`

```python
# compare_criterion_evaluator.py:316-317
if on_criterion_complete:
    try:
        await on_criterion_complete(...)
    except Exception:
        pass  # <-- Sväljer alla fel
```

```python
# compare_executor.py:367
except Exception:
    pass  # non-critical
```

**Problem:** Om `on_criterion_complete` kastar ett undantag (t.ex. vid SSE-streaming-fel, nätverksfel till frontend, eller en bugg i event-dispatching) loggas inget. Detta gör debugging extremt svårt i produktion. Om SSE-kanalen har stängts tidigt kan alla 32 criterion-events tyst misslyckas utan att operatören vet varför frontend inte uppdateras.

**Fix:**
```python
if on_criterion_complete:
    try:
        await on_criterion_complete(...)
    except Exception:
        logger.debug(
            "criterion_evaluator[%s/%s]: on_criterion_complete callback failed: %s",
            model_display_name, criterion, exc,
            exc_info=True,
        )
```

Samma mönster i `compare_executor.py:367` och alla andra `except Exception: pass`-block som hanterar SSE-events.

---

### BUG-03 [P1/Hög]: Research-agentens research_context = None i criterion eval — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:397`

```python
eval_result = await evaluate_model_response(
    domain=domain,
    model_response=response_text,
    ...
    research_context=None,  # <-- Alltid None
    ...
)
```

**Problem:** Korrekthetsbedömaren har en speciell gren som injicerar research-data för faktakontroll:

```python
# compare_criterion_evaluator.py:127-128
if research_context and criterion == "korrekthet":
    user_content += f"\nResearch-data (webbkällor):\n{research_context[:3000]}\n"
```

Men `research_context` skickas alltid som `None` till varje extern modells criterion eval. Detta innebär att korrekthetsbedömaren **aldrig** har tillgång till research-data som referens vid bedömning av externa modeller. Research-agentens huvudsyfte är att ge faktaunderlag — men det når aldrig de bedömare som behöver det.

**Orsak:** Research-domänen körs parallellt med externa modeller i `asyncio.gather`. Research-svaret finns inte tillgängligt när externa modellers kriterieeval startar.

**Fix:** Tvåfas-approach:
```python
# Fas 1: Kör alla domäner parallellt (modeller + research)
# Fas 2: Kör kriterieeval för externa modeller MED research-context

# Eller: Kör research först (kort timeout), sedan övriga parallellt
# med research_context injicerad
```

Alternativt (enklare): Kör criterion eval i convergence-noden istället, där alla domäner redan har returnerat.

---

### BUG-04 [P2/Medium]: Race condition vid module-level `import re` i compare_research_worker — EJ FIXAD ⚠️

**Fil:** `compare_research_worker.py:146`

```python
async def _decompose_query(query: str, llm: Any) -> list[str]:
    ...
    try:
        ...
    except Exception:
        ...
        import re  # <-- Import inne i except-block
        json_match = re.search(r"\{[^{}]*\}", raw_content)
```

**Problem:** `import re` sker inne i en fallback-kodväg istället för på modul-nivå. Medan detta inte är en bugg i strikt mening (Python cachar imports), är det en kodlukt som antyder att `re` glömdes i toppen och bara lades till i fallback-koden. Om fallback-vägen aldrig körs under tester kan det dölja att `re` inte är tillgänglig.

**Fix:** Flytta `import re` till modul-nivå (rad 22-området).

---

### BUG-05 [P2/Medium]: Inkonsekvent score priority mellan backend och frontend — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:951-958` vs `spotlight-arena.tsx:1254-1284`

**Backend (convergence synthesis context):**
```python
# Prefer criterion_scores from handoffs over convergence
model_scores = convergence.get("model_scores", {})
for s in summaries:
    domain = s.get("domain", "unknown")
    cs = s.get("criterion_scores", {})
    if cs and domain not in model_scores:  # <-- Convergence wins
        model_scores[domain] = cs
```

**Frontend:**
```typescript
// Score priority:
// 1. criterion_scores from tool result  ← ALWAYS preferred
// 2. live SSE criterion scores
// 3. model_scores from convergence
```

**Problem:** Backend-logiken ger **convergence** `model_scores` prioritet (den skrivs först, och subagent-scores läggs bara till om domänen saknas). Frontenden ger `criterion_scores` i tool result prioritet. Normalt sammanfaller dessa, men vid edge cases (t.ex. convergence LLM:en ändrar poäng) kan backend-syntes och frontend-ranking visa olika ordning.

**Fix:** Konsekvent prioritera `criterion_scores` från handoff (de faktiska isolerade bedömarnas poäng) i båda kodvägarna:
```python
# Backend: handoff criterion_scores först, convergence som fallback
for s in summaries:
    cs = s.get("criterion_scores", {})
    if cs:
        model_scores[s["domain"]] = cs  # Alltid skriv handoff-poäng
# Fyll i saknade domäner från convergence
for domain, scores in convergence.get("model_scores", {}).items():
    if domain not in model_scores:
        model_scores[domain] = scores
```

---

### BUG-06 [P2/Medium]: `hasFinalScoresFromResult` logik duplicerad med olika variabelnamn — EJ FIXAD ⚠️

**Fil:** `spotlight-arena.tsx:761-762` och `spotlight-arena.tsx:940-945`

```typescript
// DuelCard (rad 761-762)
const hasFinalScoresFromResult = Object.keys(model.criterionPodInfo).length === 4
    || (model.hasRealScores && !domainLive);

// RunnerUpCard (rad 940-945)
const hasFinalScoresFromResult2 = Object.keys(model.criterionPodInfo).length === 4
    || (model.hasRealScores && !domainLive);
const allLiveDone2 = domainLive ? (...) : false;
const criteriaFinalized2 = hasFinalScoresFromResult2 || allLiveDone2;
```

**Problem:** Exakt samma logik upprepas med suffix `2` i variabelnamnen. Om en buggfix görs i DuelCard men inte i RunnerUpCard (eller vice versa) divergerar beteendet.

**Fix:** Extrahera till en hook eller hjälpfunktion:
```typescript
function useCriteriaFinalized(model: RankedModel) {
  const liveScores = useContext(LiveCriterionContext);
  const domainLive = liveScores[model.domain];
  const hasFinalFromResult = Object.keys(model.criterionPodInfo).length === 4
    || (model.hasRealScores && !domainLive);
  const allLiveDone = domainLive
    ? (domainLive.relevans != null && domainLive.djup != null
       && domainLive.klarhet != null && domainLive.korrekthet != null)
    : false;
  return {
    criteriaFinalized: hasFinalFromResult || allLiveDone,
    isEvaluating: model.status === "complete" && !(hasFinalFromResult || allLiveDone),
    domainLive,
  };
}
```

---

## 2. Kodkvalitet

### KQ-01: Duplicerad sanitering backend ↔ frontend — EJ FIXAD ⚠️

**Fil(er):** `compare_executor.py:1064-1158` och `spotlight-arena.tsx:322-348`

Backend (`_sanitize_synthesis_text`) och frontend (`sanitizeSynthesisText`) implementerar **identisk** sanerings-logik med nästan samma regex-mönster och fältnamn.

**Problem:** Duplicerad affärslogik som kan divergera vid ändringar. Om ett nytt fältnamn läggs till i `_LEAKED_JSON_FIELDS` på backend men inte i frontend (eller vice versa) kan läckt JSON visas i UI.

**Rekommendation:** Backend bör returnera redan sanerad text. Frontend-sanitering behålls som defense-in-depth men bör dokumenteras som fallback. Alternativt: dela fältlistan via ett gemensamt kontrakt/konstant-fil.

---

### KQ-02: Duplicerade CO2/energi-konstanter — EJ FIXAD ⚠️

**Fil(er):** `compare-model.tsx:100-101` och `spotlight-arena.tsx:193-194`

```typescript
// Identiskt i båda filer:
const ENERGY_WH_PER_1K_TOKENS = 0.2;
const CO2G_PER_1K_TOKENS = 0.1;
```

**Rekommendation:** Extrahera till en delad konstant-fil (t.ex. `lib/constants/energy.ts`) och importera.

---

### KQ-03: Duplicerad MODEL_LOGOS-mapping — EJ FIXAD ⚠️

**Fil(er):** `compare-model.tsx:58-67` och `spotlight-arena.tsx:153-162`

Båda filerna definierar sin egen `MODEL_LOGOS`-mapping med samma data men olika struktur (objekt med `{src, alt}` vs ren sträng).

**Rekommendation:** Extrahera till en delad komponent eller konstant. Enhetlig struktur.

---

### KQ-04: Duplicerad `formatLatency` funktion — EJ FIXAD ⚠️

**Fil(er):** `compare-model.tsx:69-72` och `spotlight-arena.tsx:293-297`

Identisk logik i båda filer.

**Rekommendation:** Extrahera till `lib/utils/format.ts`.

---

### KQ-05: Legacy dead code bevarad — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:1326-1355`

```python
# Legacy compat: keep old function signatures for imports
async def compare_fan_out(state): ...
async def compare_collect(state): ...
async def compare_tavily(state): ...
async def compare_synthesizer(state, prompt_override=None): ...
```

**Problem:** 4 legacy-funktioner hålls kvar "för imports" men varnar bara med `logger.warning`. Om de verkligen inte anropas bör de tas bort. Om de anropas i tester bör testerna uppdateras.

**Rekommendation:** Sök efter imports/anrop. Om oanvända: ta bort. Om använda i tester: markera med `@deprecated` decorator och skapa migration-plan.

---

### KQ-06: Stor fil compare_executor.py (1354 rader) — EJ FIXAD ⚠️

**Fil:** `compare_executor.py`

En enda fil innehåller:
- Domain planner (rad 46–111)
- Subagent spawner (rad 119–866) — inklusive sandbox-logik
- Scoring-algoritmer (rad 869–925)
- Synthesis context builders (rad 928–1061)
- Text sanitizer (rad 1064–1158)
- Synthesizer node (rad 1161–1323)
- Legacy compat (rad 1326–1355)

**Rekommendation:** Dela upp i:
- `compare_domain_planner.py` — Planering
- `compare_subagent_spawner.py` — Spawning + sandbox
- `compare_scoring.py` — Weighted scoring + ranking
- `compare_synthesizer.py` — Syntes-nod
- `compare_sanitizer.py` — Text-sanitering
- (Behåll `compare_executor.py` som re-export-punkt)

---

### KQ-07: Inkonsekvent `from types import SimpleNamespace` inuti funktion — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:310-312`

```python
for attempt in range(_max_retries_external + 1):
    try:
        from types import SimpleNamespace  # <-- Import inuti loop
        spec = SimpleNamespace(**spec_data)
```

**Problem:** `from types import SimpleNamespace` importeras inuti retry-loopen. Bör vara på modul-nivå.

---

### KQ-08: `build_compare_synthesis_prompt` — oanvänd parameter — EJ FIXAD ⚠️

**Fil:** `compare_prompts.py:339-350`

```python
def build_compare_synthesis_prompt(
    base_prompt: str,
    *,
    citations_enabled: bool,       # <-- Aldrig använd
    citation_instructions: str | None = None,
) -> str:
    prompt = append_datetime_context(base_prompt.strip())
    _ = citations_enabled           # <-- Explicit ignorerad
    explicit = str(citation_instructions or "").strip()
    if not explicit:
        return prompt
    return prompt + "\n\n" + explicit
```

**Problem:** `citations_enabled` accepteras som parameter men ignoreras med `_ = citations_enabled`. Om den inte behövs bör den tas bort ur signaturen. Om den planeras att användas bör det dokumenteras.

---

## 3. Optimeringar

### OPT-01 [P3]: Research-kontext bör injiceras i korrekthetsbedömare — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:370-410`

**Status:** Relaterat till BUG-03. Research-agentens svar når aldrig korrekthetsbedömaren. Om denna bugg fixas (tvåfas-approach) frigörs korrekthetsbedömarens fulla potential.

**Uppskattad effekt:** Signifikant förbättrad korrekthetsbedömning — research-data ger faktareferens.

---

### OPT-02 [P3]: Batcha criterion LLM-anrop med bulk API — EJ FIXAD ⚠️

**Fil:** `compare_criterion_evaluator.py`

32 LLM-anrop (8 domäner × 4 kriterier) körs genom en semafor (max 4 samtida). Med LiteLLMs batch API eller provider-specifik batching kunde man minska overhead.

**Uppskattad effekt:** ~30-50% latensreduktion vid hög load.

---

### OPT-03 [P3]: Cachelagra research-resultat för identiska queries — EJ FIXAD ⚠️

**Fil:** `compare_research_worker.py`

Om samma `/compare`-fråga körs igen (t.ex. vid retry eller liknande fråga) görs helt nya Tavily-sökningar. En TTL-cache (5 min) på query → web_sources kunde spara API-anrop.

**Uppskattad effekt:** Snabbare retries, lägre Tavily-kostnad.

---

### OPT-04 [P3]: Sänk criterion_timeout från 90s till 30s — EJ FIXAD ⚠️

**Fil:** `compare_criterion_evaluator.py:204`

```python
timeout_seconds: float = 90,
```

**Problem:** Kriterium-bedömaren har en timeout på 90s, men den genererar max 300 tokens. De flesta LLM:er svarar inom 5-15s. 90s timeout innebär att en hängande LLM-anslutning blockerar en semafor-slot i 90 sekunder.

**Rekommendation:** Sänk till 30s. Om modellen inte svarat inom 30s med 300 tokens max, är det sannolikt ett connectivity-problem.

---

### OPT-05 [P3]: Lazy-load compare_criterion_evaluator i spawner — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:387-389`

```python
from app.agents.new_chat.compare_criterion_evaluator import (
    evaluate_model_response,
)
```

Import sker inuti varje domän-körning. Bör importeras en gång i spawner-closuren.

---

### OPT-06 [P3]: Token estimation med `len(text) / 4` är grov — EJ FIXAD ⚠️

**Fil(er):** `compare-model.tsx:112-113` och `spotlight-arena.tsx:249-258`

```typescript
function estimateTokensFromText(text: string): number {
    return Math.max(1, Math.round(text.length / 4));
}
```

**Problem:** `text.length / 4` ger en grov uppskattning (English ~4 chars/token, men Svenska kan vara 3-5, CJK 1-2). Användare kan tro att CO₂-estimat är exakta.

**Rekommendation:** Märk tydligare som uppskattning, eller använd `tiktoken` / `gpt-tokenizer` för mer exakt räkning.

---

### OPT-07 [P3]: Undvik re-compilation av regex i `_sanitize_synthesis_text` — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:1106-1113`

```python
def _sanitize_synthesis_text(text: str) -> str:
    cleaned = re.sub(
        r"```spotlight-arena-data\s*\n[\s\S]*?```\s*\n?",
        "", text,
    )
    cleaned = re.sub(r"```json\s*\n[\s\S]*?```\s*\n?", "", cleaned)
```

**Problem:** `re.sub` med strängar kompilerar regex vid varje anrop. De precompilerade regexen (`_TRAILING_JSON_RE`, `_NAKED_JSON_RE`) används för steg 3-4, men steg 1-2 kompilerar om varje gång.

**Fix:** Precompilera alla regex-mönster som modul-konstanter.

---

### OPT-08 [P3]: Undvik `json.dumps` + `json.loads` roundtrip i ToolMessage — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:842-844`

```python
tool_messages.append(ToolMessage(
    name=tool_name,
    content=json.dumps(raw_with_scores, ensure_ascii=False),
    tool_call_id=tc_id,
))
```

Resultatet serialiseras till JSON-sträng, skickas som `ToolMessage.content`, och parsas sedan i frontend med `JSON.parse`. Om LangGraph stödjer strukturerad content (dict) kan roundtripen undvikas.

**Uppskattad effekt:** Minimal — men renare kontrakt.

---

### OPT-09 [P3]: Frontend `useMemo` för `rankedModels` har bred dependency array — EJ FIXAD ⚠️

**Fil:** `spotlight-arena.tsx:1232-1335`

```typescript
const rankedModels = useMemo((): RankedModel[] => {
    // ... ~100 rader logik
}, [messageContent, externalModelScores, liveCriterionScores]);
```

**Problem:** `liveCriterionScores` uppdateras vid varje `criterion_complete` SSE-event (upp till 32 gånger). Varje uppdatering triggar en full re-parse och re-sort av alla modeller.

**Rekommendation:** Separera score-merge från ranking. Håll modell-parsing separat och merga bara scores vid uppdatering.

---

### OPT-10 [P3]: `_build_synthesis_from_convergence` bygger stora strängar — EJ FIXAD ⚠️

**Fil:** `compare_executor.py:931-1035`

Funktionen bygger syntes-kontexten genom strängkonkatenering i en lista och `"\n".join()`. Med 8 domäner med vardera 500-tecken-sammanfattningar + convergence-data kan strängen bli mycket stor (>10KB).

**Rekommendation:** Trunkerera per-domän-sammanfattningar mer aggressivt (t.ex. 300 tecken istället för 500) för att hålla kontexten under LLM:ens optimala input-storlek.

---

## 4. Testning — Gap-analys

### Befintliga tester

| Testfil | Vad den testar | Compare-relevans |
|---------|----------------|------------------|
| `test_dispatcher_routing.py` | Route-detektion inkl. `/compare` | Direkt — testar att `/compare` → Route.JAMFORELSE |
| `test_loop_fix_p4.py` | P4 subagent infrastruktur | Indirekt — compare bygger på samma infrastruktur |
| `test_prompt_template_registry.py` | Prompt-registrering | Indirekt — testar att compare-promptar finns |
| `test_synthesizer_guardrail_regression.py` | Syntes-guardrails | Indirekt — applicerbar på compare syntes |

### Saknade tester

| Testtyp | Beskrivning | Prioritet |
|---------|-------------|-----------|
| `test_compare_domain_planner.py` | Testar att 8 domäner alltid planeras | P1 |
| `test_compare_criterion_evaluator.py` | Testar scoring, retry, fallback=50, semafor | P1 |
| `test_compare_scoring.py` | Testar `compute_weighted_score`, `rank_models_by_weighted_score` | P1 |
| `test_compare_research_worker.py` | Testar decompose, Tavily-mock, syntes | P2 |
| `test_compare_sanitizer.py` | Testar `_sanitize_synthesis_text` med div. input | P2 |
| `test_compare_synthesizer.py` | Testar syntes-noden med mock-convergence | P2 |
| `test_compare_e2e.py` | End-to-end med mock-modeller | P3 |
| Frontend: Spotlight Arena | Testar ranking, score priority, fas-indikation | P3 |

---

## 5. Säkerhet

### SEC-01: API-nycklar sätts i `os.environ` globalt — EJ FIXAD ⚠️

**Fil:** `external_models.py:90-127`

```python
def _apply_provider_env(provider: str, api_key: str) -> None:
    if provider_key == "XAI":
        os.environ.setdefault("XAI_API_KEY", api_key)
    elif provider_key == "DEEPSEEK":
        os.environ.setdefault("DEEPSEEK_API_KEY", api_key)
    # ... etc
```

**Problem:** `os.environ.setdefault` sätter API-nycklar i processens globala miljö. Dessa kan:
1. Läcka via `os.environ` i stacktraces/crash dumps
2. Finnas kvar i minnet även efter att de inte behövs
3. Vara synliga via `/proc/<pid>/environ` på Linux

**Risk:** Låg i typisk deployment (single-purpose container), men bryter mot principle of least privilege.

**Rekommendation:** Skicka `api_key` direkt till `litellm.acompletion()` (redan gjort via `api_key=api_key` parametern). `_apply_provider_env` bör markeras som legacy eller tas bort om LiteLLM inte behöver env-vars som fallback.

---

### SEC-02: Ingen input-validering av `/compare`-frågan — EJ FIXAD ⚠️

**Fil:** `stream_compare_chat.py:99-105` och `dispatcher.py:71-72`

```python
def extract_compare_query(user_query: str) -> str | None:
    # Removes "/compare" prefix and returns the question
```

**Problem:** Frågan efter `/compare` skickas utan sanitering till 7+ externa API:er och Tavily. En användare kan injicera prompt-instruktioner som påverkar externa modellers beteende.

**Risk:** Låg — detta är by design (användaren vill ställa sin fråga), men det finns ingen längdgräns eller innehållsfiltrering.

**Rekommendation:** Lägg till maxlängd (t.ex. 4000 tecken) för frågan. Logga ovanligt långa eller misstänkta queries.

---

## 6. Arkitekturella Rekommendationer

### Kortsikt (1–2 veckor)

1. **Fixa BUG-01** (semafor) — Lazy initialization per event loop. Effort: S.
2. **Fixa BUG-02** (silent exceptions) — Lägg till `logger.debug` i alla `except: pass`-block. Effort: S.
3. **Fixa BUG-03** (research context) — Tvåfas-approach för criterion eval. Effort: M.
4. **KQ-05** — Ta bort eller deprecera legacy-funktioner. Effort: S.
5. **Skriv tester** — Prioritera `test_compare_criterion_evaluator.py` och `test_compare_scoring.py`. Effort: M.

### Medellång sikt (2–4 veckor)

6. **KQ-01** — Unify sanitering backend/frontend. Effort: M.
7. **KQ-06** — Dela upp `compare_executor.py` i mindre moduler. Effort: M.
8. **OPT-04** — Sänk criterion timeout till 30s. Effort: S.
9. **BUG-05** — Konsekvent score priority backend/frontend. Effort: S.
10. **KQ-02–04** — Deduplica frontend-konstanter. Effort: S.

### Långsikt (1–3 månader)

11. **OPT-01** — Tvåfas criterion eval med research-data. Effort: L.
12. **OPT-02** — Batch criterion LLM-anrop. Effort: L.
13. **OPT-09** — Optimera frontend re-renders under SSE-storm. Effort: M.
14. Dynamiska vikter per fråge-typ. Effort: L.
15. Historisk poäng-tracking per modell. Effort: L.

---

## Slutsats

Compare v1 (Spotlight Arena) är en **solid implementation** med god arkitektur som återanvänder P4-mönstret konsekvent. De identifierade problemen är mestadels:

- **Duplicerad kod** (frontend/backend sanitering, konstanter) — lättåtgärdat
- **Silent error handling** — potentiellt problematisk i produktion
- **En kritisk concurrency-bugg** (modul-nivå semafor) — låg risk i standard-deployment men bör fixas
- **Oanvänd kapabilitet** (research context till korrekthetsbedömare) — störst potentiell förbättring

Inga blockerande säkerhetsproblem identifierades. Den befintliga test-täckningen är indirekt (via P4-tester) och bör kompletteras med dedicerade compare-tester.
