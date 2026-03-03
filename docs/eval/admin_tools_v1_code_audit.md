# Admin Tools — Fullständig Kodanalys & Audit

> **Datum:** 2026-03-03
> **Scope:** Intent/Agent/Tool-routing + Admin dashboard + Eval-system + Kalibrering
> **Analyserade filer:** 32 filer (20 backend, 12 frontend)
> **Senast uppdaterad:** 2026-03-03

---

## Sammanfattning

Admin Tools-systemet är **funktionellt komplett** med 3-lagers retrieval, fasad utrullning, auto-loop-kalibrering, BSSS-separation och livscykelhantering. Systemet hanterar 215 verktyg med hög precision (medel topp-1 score: 2.997).

Den initiala analysen identifierar **10 buggar**, **12 kodkvalitetsproblem**, **8 optimeringsmöjligheter** och **5 arkitekturförslag**.

### Åtgärdsstatus

| Kategori | Totalt | Status |
|----------|--------|--------|
| Buggar (BUG) | 10 | Öppna |
| Kodkvalitet (KQ) | 12 | Öppna |
| Optimeringar (OPT) | 8 | Öppna |
| Arkitektur (ARK) | 5 | Förslag |
| **Totalt** | **35** | |

### Prioriterad Åtgärdslista

| Prioritet | Typ | Antal | Mest kritiskt |
|-----------|-----|-------|---------------|
| P0 (Kritisk) | Bugg | 2 | Holdout-suite valideras ej, trösklar ur synk |
| P1 (Hög) | Bugg + Kvalitet | 6 | Race condition, duplicerad default-def, monolitiska komponenter |
| P2 (Medium) | Bugg + Kvalitet | 12 | Eval-jobbstädning, duplicerad logik, BSSS-override-logg |
| P3 (Låg) | Optimering + Arkitektur | 15 | Refaktorering, caching, dashboard-omstrukturering |

---

## 1. Buggar

### BUG-01 [P0/Kritisk]: Holdout-suite genereras men valideras aldrig

**Fil(er):** `admin_tool_settings_routes.py:6162-6295`

```python
# Auto-loop bakgrundsjobb
if use_holdout_suite:
    holdout_tests = generate_holdout(...)  # genereras ✓
    # ... loop körs mot eval-set ...
    # ... MEN holdout_tests används ALDRIG för slutvalidering ✗
    result.best_success_rate = eval_success_rate  # ← rapporterar eval-set, inte holdout
```

**Problem:** `use_holdout_suite=true` skapar reserverade testfrågor men slutresultatet valideras aldrig mot dem. Rapporterad `best_success_rate` kan vara överanpassad till eval-set.

**Risk:** Administratörer tror de har uppnått 85% precision men holdout-validering hade kanske visat 72%.

**Fix:** Kör avslutande eval mot `holdout_tests` och rapportera `holdout_success_rate` separat:
```python
if use_holdout_suite and holdout_tests:
    holdout_result = await run_evaluation(holdout_tests, ...)
    result.holdout_success_rate = holdout_result.success_rate
    result.overfit_delta = result.best_success_rate - holdout_result.success_rate
```

---

### BUG-02 [P0/Kritisk]: Score-trösklar ur synk med embedding-distribution

**Fil(er):** `embed/audit_1.yaml:36-47`, `tool_retrieval_tuning_service.py:13-37`

```yaml
# Kalibrering visar:
tool_auto_score_threshold:   nuvarande=0.60   föreslagen=3.32   delta=+2.72 ◀
agent_auto_score_threshold:  nuvarande=0.55   föreslagen=2.83   delta=+2.28 ◀
```

**Problem:** Nuvarande `tool_auto_score_threshold=0.60` med `KBLab/sentence-bert-swedish-cased` ger auto-select i 65% av fallen (32/49). Kalibreringsskriptet rekommenderar 3.32 men detta har inte applicerats. De nuvarande trösklarna är kalibrerade för en annan embedding-modell.

**Risk:** Auto-select triggas för ofta → verktyg auto-väljs med låg konfidens → felaktiga svar.

**Fix:** Uppdatera trösklar till kalibrerade värden, eller kör `calibrate_embedding_thresholds.py` automatiskt vid modellbyte:
```python
# tool_retrieval_tuning_service.py
DEFAULT_TOOL_RETRIEVAL_TUNING = {
    "tool_auto_score_threshold": 3.32,    # var 0.60
    "tool_auto_margin_threshold": 0.28,   # var 0.25
    "agent_auto_score_threshold": 2.83,   # var 0.55
    "agent_auto_margin_threshold": 0.21,  # var 0.18
}
```

---

### BUG-03 [P1/Hög]: Race condition i metadata-uppdatering vs BSSS-lock-validering

**Fil(er):** `admin_tool_settings_routes.py:4094-4373`

```python
# Steg 1: Läs aktuellt tillstånd
current_state = await get_metadata_catalog(db)

# Steg 2: Validera mot BSSS-lås (baserat på current_state)
validate_bsss_locks(current_state, proposed_changes)

# ← Annan request kan uppdatera metadata här

# Steg 3: Skriv till DB
await update_metadata(db, proposed_changes)  # ← kan bryta BSSS-lås
```

**Problem:** Mellan validering (steg 2) och skrivning (steg 3) kan en annan request ändra metadata. BSSS-lock-validering kan bli ogiltig.

**Risk:** Två samtidiga metadata-uppdateringar kan bryta BSSS-separationslåsen.

**Fix:** Använd databas-lås eller optimistisk låsning:
```python
# Optimistisk låsning med metadata_version_hash
async with db.begin():
    current = await get_metadata_catalog(db)
    if current.version_hash != expected_hash:
        raise ConflictError("Metadata ändrad sedan senaste hämtning")
    validate_bsss_locks(current, proposed_changes)
    await update_metadata(db, proposed_changes)
```

---

### BUG-04 [P1/Hög]: Eval-jobb städas ej upp vid timeout/krasch

**Fil(er):** `admin_tool_settings_routes.py:2155`

```python
_MAX_EVAL_JOBS = 100

def _prune_eval_jobs():
    # Begränsar till 100 jobb men städar INTE baserat på tid
    if len(_eval_jobs) > _MAX_EVAL_JOBS:
        oldest_keys = sorted(_eval_jobs, key=lambda k: _eval_jobs[k].started_at)
        for key in oldest_keys[:len(_eval_jobs) - _MAX_EVAL_JOBS]:
            del _eval_jobs[key]
```

**Problem:** Jobb som kraschar eller tar timeout förblir i minnet tills 100-gränsen nås. Inga time-based cleanups.

**Risk:** Minnesläcka vid långvarig drift. Stale jobb blockerar nya.

**Fix:** Lägg till tidbaserad städning:
```python
def _prune_eval_jobs():
    cutoff = datetime.now() - timedelta(hours=24)
    expired = [k for k, v in _eval_jobs.items() if v.started_at < cutoff]
    for key in expired:
        del _eval_jobs[key]
    # ... befintlig storleksbegränsning
```

---

### BUG-05 [P2/Medium]: BSSS lock-override loggas men sparas ej i audit trail

**Fil(er):** `admin_tool_settings_routes.py:4346-4351`

```python
if allow_lock_override:
    logger.warning("BSSS lock override by user %s: %s", user_id, override_reason)
    # ← loggar men sparar INTE till DB
    # Ingen audit trail i GlobalMetadataLockOverrideAudit
```

**Problem:** Admin kan överrida BSSS-lås med `allow_lock_override=true`, men detta sparas bara i applikationsloggen — inte i databasen.

**Risk:** Ingen spårbarhet i admin-UI för vem som överskred lås och varför.

---

### BUG-06 [P2/Medium]: Partiella eval-resultat sparas vid krasch

**Fil(er):** `admin_tool_settings_routes.py:3548`

**Problem:** Stage-körningar sparas till DB under eval-exekvering. Om eval kraschar mitt i, sparas partiella resultat utan markering.

**Risk:** Inkonsekvent eval-historik. Trenddiagram kan visa felaktiga success rates.

---

### BUG-07 [P2/Medium]: Ingen rate-limiting på LLM-anrop vid metadata-audit

**Fil(er):** `metadata_audit_service.py` — parallella LLM-anrop

**Problem:** `per_stage_parallelism` (upp till 12) kör parallella LLM-anrop men utan global rate-limiter. Med flera samtidiga audit-körningar kan LLM-providern överbelastas.

---

### BUG-08 [P2/Medium]: Stabilitets-lås uppdateras ej vid audit-fel

**Fil(er):** `admin_tool_settings_routes.py:4930-4932`

**Problem:** Om stabilitets-lås-uppdatering misslyckas, loggas felet men auditen fortsätter med gammal lås-status. UI visar inkorrekt låsstatus.

---

### BUG-09 [P2/Medium]: Tool registry kan vara stale vid metadata-update

**Fil(er):** `admin_tool_settings_routes.py:3981`

**Problem:** Validerar `tool_id` mot byggt register, men registret kan vara föråldrat om nya verktyg lagts till sedan senaste uppstart.

---

### BUG-10 [P3/Låg]: `breakdown_by_id` kan sakna poster för reranked tools

**Fil(er):** `bigtool_store.py:1800-1815`

```python
for rank_index, tool_id in enumerate(reranked_ids):
    entry = tool_index_by_id.get(tool_id)      # kan vara None
    breakdown = breakdown_by_id.get(tool_id, {})  # tom dict som fallback
    # ...
    "name": entry.name if entry else tool_id,
```

**Problem:** Om reranking lägger till ett verktyg som inte scorats i steg 1, saknas breakdown-data. Defensivt hanterat men kan ge felaktiga breakdown-rapporter.

---

## 2. Kodkvalitet

### KQ-01 [P1/Hög]: `DEFAULT_TOOL_RETRIEVAL_TUNING` definierat på 2 ställen

**Fil(er):**
- `bigtool_store.py:436-463` — som dataclass `ToolRetrievalTuning()`
- `tool_retrieval_tuning_service.py:13-37` — som dict

**Problem:** Identiska standardvärden underhålls på två ställen. Om ett ändras och det andra inte gör det uppstår subtila buggar.

**Rekommendation:** En enda källa. Låt `tool_retrieval_tuning_service.py` importera från `bigtool_store.py`:
```python
# tool_retrieval_tuning_service.py
from app.agents.new_chat.bigtool_store import DEFAULT_TOOL_RETRIEVAL_TUNING

DEFAULT_TUNING_DICT = asdict(DEFAULT_TOOL_RETRIEVAL_TUNING)
```

---

### KQ-02 [P1/Hög]: Monolitisk frontend-komponent — 5 283 rader

**Fil(er):** `tool-settings-page.tsx` (5 283 rader)

**Problem:** En enda TSX-fil hanterar:
- 6 flikar med helt olika funktionalitet
- 15+ lokala state-variabler
- 10+ API-anrop
- 5+ polling-loopar

**Rekommendation:** Bryt ut varje flik till egen komponent:
```
tool-settings-page.tsx (orchestrator, ~200 rader)
├── metadata-editor-tab.tsx (~800 rader)
├── eval-workflow-tab.tsx (~1200 rader)
├── agent-stats-tab.tsx (~500 rader)
├── tool-stats-tab.tsx (~500 rader)
└── api-input-stats-tab.tsx (~500 rader)
```

---

### KQ-03 [P1/Hög]: Monolitisk frontend-komponent — 4 221 rader

**Fil(er):** `metadata-catalog-tab.tsx` (4 221 rader)

**Problem:** Blandar audit-flöde, separation-logik, stabilitets-lås, safe-rename och verktygsranking i en enda komponent.

**Rekommendation:** Bryt ut i delkomponenter:
```
metadata-catalog-tab.tsx (orchestrator)
├── audit-runner.tsx
├── stability-locks-panel.tsx
├── collision-separator.tsx
└── tool-ranking-snapshot.tsx
```

---

### KQ-04 [P2/Medium]: 8 nästan identiska if-block i `build_tool_index()`

**Fil(er):** `bigtool_store.py:2049-2112`

```python
if tool_id in scb_by_id:
    definition = scb_by_id[tool_id]
    description = definition.description
    keywords = list(definition.keywords)
    example_queries = list(definition.example_queries)
    category = "statistics"
    base_path = definition.base_path
# ... UPPREPAS 7 gånger till för kolada, skolverket, bolagsverket, trafikverket, smhi, geoapify, riksdagen, marketplace
```

**Rekommendation:**
```python
_DEFINITION_SOURCES = [
    (scb_by_id, "statistics"),
    (kolada_by_id, "statistics"),
    (skolverket_by_id, "statistics"),
    (bolagsverket_by_id, "company"),
    (trafikverket_by_id, "traffic"),
    (smhi_by_id, "weather"),
    (geoapify_by_id, "maps"),
    (riksdagen_by_id, "politics"),
    (marketplace_by_id, "marketplace"),
]

for source_dict, default_category in _DEFINITION_SOURCES:
    if tool_id in source_dict:
        definition = source_dict[tool_id]
        description = definition.description
        keywords = list(definition.keywords)
        example_queries = list(definition.example_queries)
        category = default_category
        base_path = definition.base_path
        break
```

---

### KQ-05 [P2/Medium]: Duplicerad eval-logik — 1 468 rader

**Fil(er):** `tool_evaluation_service.py`

- `run_tool_evaluation()`: 664 rader (rad 2362)
- `run_tool_api_input_evaluation()`: 804 rader (rad 3841)

**Problem:** Nästan identisk logik med mindre avvikelser (API-input testar `schema_checks`, `field_value_checks`).

**Rekommendation:** Extrahera gemensam baslogik:
```python
async def _run_evaluation_base(test_cases, eval_type, ...):
    """Gemensam loop: setup → run tests → record → suggest."""
    ...

async def run_tool_evaluation(...):
    return await _run_evaluation_base(test_cases, eval_type="tool_selection", ...)

async def run_tool_api_input_evaluation(...):
    return await _run_evaluation_base(test_cases, eval_type="api_input", ...)
```

---

### KQ-06 [P2/Medium]: 8 `_namespace_for_*` funktioner med manuell dispatcher

**Fil(er):** `bigtool_store.py:586-757`

**Problem:** Manuell if-kedja i `namespace_for_tool()` som routar till 8 specialiserade funktioner. Att lägga till ny provider kräver ändringar på 3 ställen.

**Rekommendation:** Registry-mönster:
```python
_NAMESPACE_BUILDERS: dict[str, Callable] = {
    "scb_": _namespace_for_scb_tool,
    "kolada_": _namespace_for_kolada_tool,
    # ...
}

def namespace_for_tool(tool_id: str) -> tuple[str, ...]:
    for prefix, builder in _NAMESPACE_BUILDERS.items():
        if tool_id.startswith(prefix):
            return builder(tool_id)
    return _default_namespace(tool_id)
```

---

### KQ-07 [P2/Medium]: Dubbel API-funktion för tool retrieval

**Fil(er):** `bigtool_store.py:1863-1903`

- `smart_retrieve_tools()` → returnerar `list[str]`
- `smart_retrieve_tools_with_breakdown()` → returnerar `tuple[list[str], list[dict]]`

**Problem:** Båda delegerar till `_run_smart_retrieval()`. Onödig dubblering.

**Rekommendation:** En funktion med valfri breakdown:
```python
def smart_retrieve_tools(
    ..., include_breakdown: bool = False
) -> list[str] | tuple[list[str], list[dict]]:
```

---

### KQ-08 [P2/Medium]: Inkonsekvent validering i API-service

**Fil(er):** `admin-tool-settings-api.service.ts:65-432`

**Problem:** Alla 20+ metoder följer exakt samma mönster:
```typescript
const parsed = schema.safeParse(request);
if (!parsed.success) {
    throw new ValidationError(...);
}
return baseApiService.post(url, responseSchema, { body: parsed.data });
```

**Rekommendation:** Extrahera till hjälpfunktion:
```typescript
private async validatedPost<TReq, TRes>(
    url: string, reqSchema: z.Schema<TReq>, resSchema: z.Schema<TRes>, data: TReq
): Promise<TRes> {
    const parsed = reqSchema.safeParse(data);
    if (!parsed.success) throw new ValidationError(...);
    return baseApiService.post(url, resSchema, { body: parsed.data });
}
```

---

### KQ-09 [P3/Låg]: JSON.stringify för deep equality

**Fil(er):** `tool-settings-page.tsx:105-111`

```typescript
function isEqualTool(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
}
```

**Problem:** `JSON.stringify` är ordningskänslig — objekt med samma nycklar i olika ordning ger `false`. Fungerar i praktiken eftersom objekt skapas konsekvent, men är fragilt.

---

### KQ-10 [P3/Låg]: Metadata-gränser definierade på 3 ställen

**Fil(er):**
- `admin-tool-settings.types.ts:6-15` — TypeScript-konstanter
- `bigtool_store.py:524-583` — Python-konstanter
- `metadata_audit_service.py` — Egna gränser (500 chars description vs 300)

**Problem:** Tre separata definitioner av max-gränser. `metadata_audit_service.py` tillåter 500 tecken beskrivning medan `bigtool_store.py` trunkerar vid 300.

---

### KQ-11 [P3/Låg]: Frontend-pollning med fixed interval

**Fil(er):** `tool-settings-page.tsx` — `refetchInterval: 1200-1400`

**Problem:** Pollar eval-jobb var 1.2s oavsett belastning. Ingen exponentiell backoff.

---

### KQ-12 [P3/Låg]: Inline `useEffect` i `StageHistoryTabContent`

**Fil(er):** `tool-settings-page.tsx:322-326`

```typescript
useEffect(() => {
    if (effectiveCategory && effectiveCategory !== selectedCategory) {
        onSelectCategory(effectiveCategory);
    }
}, [effectiveCategory, selectedCategory, onSelectCategory]);
```

**Problem:** Onödig synkronisering. `effectiveCategory` kan beräknas direkt utan effect.

---

## 3. Optimeringar

### OPT-01 [P2/Medium]: Embedding-cachning per request

**Fil(er):** `bigtool_store.py`

**Nuvarande:** Fråge-embedding beräknas på varje retrieval-anrop.

**Förslag:** Cachelagra fråge-embeddings per session/conversation:
```python
_QUERY_EMBED_CACHE: dict[str, list[float]] = {}

def _get_query_embedding(query: str) -> list[float]:
    key = hashlib.sha1(query.encode()).hexdigest()
    if key not in _QUERY_EMBED_CACHE:
        _QUERY_EMBED_CACHE[key] = encode(query)
    return _QUERY_EMBED_CACHE[key]
```

**Uppskattad effekt:** ~50ms sparad per retrieval-anrop vid cache-hit.

---

### OPT-02 [P2/Medium]: Parallellisera 3-lagers audit

**Fil(er):** `metadata_audit_service.py`

**Nuvarande:** Intent → Agent → Tool retrieval körs sekventiellt per probe.

**Förslag:** Kör intent + agent + tool parallellt per probe (de är oberoende för probe-analys):
```python
intent_task = asyncio.create_task(retrieve_intents(query))
agent_task = asyncio.create_task(retrieve_agents(query))
tool_task = asyncio.create_task(retrieve_tools(query))
intent_r, agent_r, tool_r = await asyncio.gather(intent_task, agent_task, tool_task)
```

**Uppskattad effekt:** ~3x snabbare audit (3 × 200ms → 200ms per probe).

---

### OPT-03 [P2/Medium]: Lazy-loading av flikar i admin dashboard

**Fil(er):** `tool-settings-page.tsx`

**Nuvarande:** Alla 6 flikar renderas och laddar data vid mount.

**Förslag:** React.lazy + Suspense per flik:
```tsx
const EvalWorkflowTab = React.lazy(() => import("./eval-workflow-tab"));
```

---

### OPT-04 [P3/Låg]: Pre-compute namespace mapping

**Fil(er):** `bigtool_store.py:679-757`

**Nuvarande:** `namespace_for_tool()` kör if-kedja per anrop.

**Förslag:** Bygg lookup-tabell vid startup:
```python
_NAMESPACE_CACHE: dict[str, tuple[str, ...]] = {}
# Populeras i build_tool_index()
```

---

### OPT-05 [P3/Låg]: Batcha eval-resultat vid skrivning

**Fil(er):** `tool_evaluation_service.py`

**Nuvarande:** Varje testresultat skrivs individuellt till DB.

**Förslag:** Samla resultat och skriv i batch efter eval-körning.

---

### OPT-06 [P3/Låg]: Dedup contrastive description-konstruktion

**Fil(er):** `bigtool_store.py`

**Nuvarande:** Contrastive descriptions byggs on-the-fly vid varje retrieval.

**Förslag:** Cachelagra vid `build_tool_index()`.

---

### OPT-07 [P3/Låg]: Reduce re-renders i MetadataCatalogTab

**Fil(er):** `metadata-catalog-tab.tsx`

**Nuvarande:** Stora state-objekt orsakar re-renders av hela 4221-raders-komponenten.

**Förslag:** useMemo + React.memo på delkomponenter.

---

### OPT-08 [P3/Låg]: WebSocket istället för polling för eval-jobb

**Fil(er):** `tool-settings-page.tsx`

**Nuvarande:** Pollar eval-status var 1.2s.

**Förslag:** SSE eller WebSocket-push för jobb-status.

---

## 4. Arkitekturförslag

### ARK-01: Konsolidera admin-dashboard till 3 flikar

**Nuvarande:** 6 flikar (Metadata, Metadata Catalog, Eval Workflow, Stats: Agent, Stats: Tool, Stats: API Input) + separat Tool Lifecycle-sida.

**Förslag:** 3 flikar — se `admin_tools_v1.md` sektion 16:
1. **Metadata** — redigering + vikter + lås
2. **Kalibrering** — guidat flöde (audit → eval → auto-loop) + fasstyrd utrullning
3. **Överblick** — alla stats + lifecycle + nyckeltal

**Motivering:**
- Minskar kognitiv belastning (6 → 3)
- Guidat flöde ersätter 12 manuella steg med flikbyten
- Fasstyrd utrullning synlig som toppelement (nu gömd)
- Statistik samlad istället för uppdelad per lager

---

### ARK-02: Automatisk kalibrering vid embedding-modellbyte

**Nuvarande:** `calibrate_embedding_thresholds.py` körs manuellt. Trösklar uppdateras inte automatiskt.

**Förslag:** Integrera kalibrering i startup-flödet:
```python
# app.py lifespan
async def lifespan(app):
    current_model = config.EMBEDDING_MODEL
    stored_model = await get_calibrated_model(db)
    if current_model != stored_model:
        new_thresholds = await run_calibration(current_model)
        await update_thresholds(db, new_thresholds)
        await store_calibrated_model(db, current_model)
```

**Alternativt:** Admin-endpoint som triggar kalibrering:
```
POST /admin/tool-settings/calibrate-embedding
  → Kör calibrate_embedding_thresholds
  → Föreslår nya trösklar (utan att applicera)
  → Admin granskar och applicerar
```

---

### ARK-03: Enhetlig metadata-gränskälla

**Nuvarande:** Gränser (max chars, max keywords) definieras i 3 filer.

**Förslag:** En enda källa i backend, exponerad via API:
```python
# bigtool_store.py (enda källan)
METADATA_LIMITS = {
    "max_description_chars": 300,
    "max_keywords": 20,
    "max_keyword_chars": 40,
    "max_example_queries": 10,
    "max_example_query_chars": 120,
    "max_excludes": 15,
}

# GET /admin/tool-settings/metadata-limits
# Frontend hämtar och använder dynamiskt
```

---

### ARK-04: Separation av eval-tjänster

**Nuvarande:** `tool_evaluation_service.py` (5 199 rader) hanterar eval, suggestions, history, API-input.

**Förslag:** Bryt ut i fokuserade tjänster:
```
tool_evaluation_service.py → eval_runner.py (~800 rader)
                            → eval_suggestion_generator.py (~600 rader)
                            → eval_history_service.py (~300 rader)
                            → api_input_evaluator.py (~800 rader)
```

---

### ARK-05: Retrieval tuning som konfigurationsobjekt

**Nuvarande:** `ToolRetrievalTuning` är en dataclass i `bigtool_store.py` och en dict i `tool_retrieval_tuning_service.py`.

**Förslag:** En Pydantic-modell som validerar vid skapande och serialiserar till/från DB:
```python
class ToolRetrievalTuning(BaseModel):
    name_match_weight: float = Field(5.0, ge=0, le=25)
    keyword_weight: float = Field(3.0, ge=0, le=25)
    # ... alla fält med validering

    class Config:
        frozen = True
```

---

## 5. Embedding-specifika förslag

### EMB-01: Stärk contrastive excludes för statistics-domänen

**Problem:** `tools/statistics` har 45 par med >0.85 likhet (26 par >0.90).

**Förslag:** Automatisk generering av contrastive excludes baserat på BSSS-matris:
```python
for tool_a, tool_b in high_similarity_pairs:
    # Hitta unika tokens per verktyg
    unique_a = keywords_a - keywords_b
    unique_b = keywords_b - keywords_a
    # Lägg till som excludes
    tool_a.excludes += list(unique_b)[:5]
    tool_b.excludes += list(unique_a)[:5]
```

---

### EMB-02: Öka structural embedding-bidrag

**Problem:** Strukturell cosine (medel 0.107) bidrar mycket lite jämfört med semantisk (0.187). Med vikterna `struct×1.2` vs `sem×2.8` blir skillnaden ännu större.

**Förslag:** Antingen:
1. Berika strukturella embedding-texter med mer schema-information
2. Öka `structural_embedding_weight` till 2.0-2.5
3. Kombinera med explicit schema-matching (ej embedding-baserad)

---

### EMB-03: Embedding-text trunkering vid 800 tecken

**Problem:** Komplexa verktyg (t.ex. SCB med många underkategorier) trunkeras vid 800 tecken, förlorar differentierande information.

**Förslag:** Viktad pooling av chunk-embeddings:
```python
def embed_tool(text: str, max_chunks: int = 3) -> list[float]:
    if len(text) <= 800:
        return encode(text)
    chunks = split_into_chunks(text, max_len=800, overlap=100)[:max_chunks]
    embeddings = [encode(chunk) for chunk in chunks]
    # Vikta första chunken högre (innehåller namn + beskrivning)
    weights = [0.5, 0.3, 0.2][:len(embeddings)]
    return weighted_average(embeddings, weights)
```

---

### EMB-04: Contrastive fine-tuning av embedding-modell

**Problem:** Generell svensk BERT-modell ej optimerad för verktygsdiskriminering.

**Förslag:** Träna adapter (LoRA) med contrastive loss:
```python
# Träningsdata: (fråga, korrekt_verktyg, fel_verktyg) tripletter
# Loss: triplet margin loss
# Källa: eval-historik (pass/fail) + audit-prober
loss = max(0, margin + d(q, pos) - d(q, neg))
```

---

## 6. Sammanfattande prioritering

### Sprint 1 (Kritiskt)

| ID | Typ | Beskrivning | Uppskattning |
|----|-----|-------------|-------------|
| BUG-02 | Bugg | Uppdatera score-trösklar till kalibrerade värden | 1h |
| KQ-01 | Kvalitet | Konsolidera `DEFAULT_TOOL_RETRIEVAL_TUNING` | 2h |
| BUG-01 | Bugg | Implementera holdout-validering i auto-loop | 4h |

### Sprint 2 (Hög prioritet)

| ID | Typ | Beskrivning | Uppskattning |
|----|-----|-------------|-------------|
| KQ-04 | Kvalitet | Refaktorera 8 if-block i `build_tool_index()` | 2h |
| KQ-05 | Kvalitet | Extrahera gemensam eval-baslogik | 6h |
| BUG-03 | Bugg | Optimistisk låsning för metadata-uppdatering | 4h |
| BUG-04 | Bugg | Tidbaserad eval-jobb-städning | 2h |
| ARK-03 | Arkitektur | Enhetlig metadata-gränskälla | 3h |

### Sprint 3 (Dashboard-omstrukturering)

| ID | Typ | Beskrivning | Uppskattning |
|----|-----|-------------|-------------|
| KQ-02 | Kvalitet | Bryt ut `tool-settings-page.tsx` | 8h |
| KQ-03 | Kvalitet | Bryt ut `metadata-catalog-tab.tsx` | 6h |
| ARK-01 | Arkitektur | Omstrukturera till 3 flikar | 12h |
| ARK-02 | Arkitektur | Automatisk kalibrering vid modellbyte | 6h |

### Backlog

| ID | Typ | Beskrivning |
|----|-----|-------------|
| OPT-01–08 | Optimering | Caching, parallellisering, lazy-loading |
| EMB-01–04 | Embedding | Contrastive excludes, chunk-embedding, fine-tuning |
| KQ-06–12 | Kvalitet | Registry-mönster, API-service-refaktor, metadata-gränser |
| BUG-05–10 | Buggar | Audit trail, rate-limiting, stale registry |

---

*Rapport genererad 2026-03-03. Se `docs/eval/admin_tools_v1.md` för fullständig systemdokumentation.*
