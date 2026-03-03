# Code Review: PR #60 — Admin Tools Dashboard v3 Implementation

**Reviewer:** Claude (automated)
**Branch:** `feat/admin-tools-v3`
**Files changed:** 10 (+3,725 / −2 lines)

---

## Sammanfattning

PR:n ersätter den befintliga 3-flikars `ToolAdminPage` (98 rader, som i sin tur lazy-laddar
`MetadataTab`, `CalibrationTab` och `OverviewTab`) med en ny 5-panelers
`ToolAdminDashboard`. De nya panelerna är: Pipeline Explorer, Katalog,
Tuning, Eval & Audit, och Deploy & Ops.

### Grundläggande bedömning

PR:n har **allvarliga strukturella problem** som gör att den inte bör mergas i sitt nuvarande
skick. Nedan redovisas samtliga fynd.

---

## KRITISKA PROBLEM (Blockerare)

### K1. Gamla komponenten tas inte bort — dead code + dubbla importer möjliga

`page.tsx` ändras till att importera `ToolAdminDashboard`, men den gamla
`components/admin/tool-admin-page.tsx` (och dess subtabs `metadata-tab.tsx`,
`calibration-tab.tsx`, `overview-tab.tsx`) tas **inte bort**. Detta leder till:
- Dead code i produktionsbundeln (lazy-importerade moduler finns kvar)
- Förvirring kring vilken som är den aktiva implementeringen
- Risk att framtida utvecklare redigerar fel fil

**Åtgärd:** Ta bort `tool-admin-page.tsx` eller markera den som deprecated
med en migrationsplan. Eventuellt ta bort `tabs/metadata-tab.tsx`,
`tabs/calibration-tab.tsx`, `tabs/overview-tab.tsx` om de inte används
annanstans.

### K2. Backend-endpoint saknar autentiseringskontroll — `debug-retrieval` ger full scoring-data till alla autentiserade användare

Endpointen `GET /tool-settings/debug-retrieval` har `current_active_user` men
saknar admin-kontroll. Alla inloggade användare kan köra godtyckliga
retrieval-frågor och se fullständig scoring-breakdown för samtliga verktyg.
Jämför med övriga endpoints i filen som har admin-guard via
`require_admin_user` eller liknande.

**Åtgärd:** Lägg till samma admin-guard som övriga endpoints i filen.

### K3. `useToolCatalog`-hooken duplicerar data-fetching — varje panel gör egna queries

`useToolCatalog` anropas separat av `ToolCatalogPanel`, `TuningPanel`,
`EvalPanel`, och `PipelineExplorerPanel`. Varje anrop skapar egna
`useQuery`-instanser med **samma query keys** men utan delad cache-garanti
vid mount-tidpunkt. Dessutom hämtar varje panel full lifecycle + settings +
catalog trots att de flesta bara behöver en bråkdel.

**Problem:**
- 4× redundanta `getToolLifecycleList()` anrop vid initial-laddning
- 4× redundanta `getToolSettings()` anrop
- React Query's `staleTime: 30_000` hjälper bara om alla paneler mountas
  *exakt samtidigt*, vilket inte sker p.g.a. lazy-loading

**Åtgärd:** Lyft data-hämtning till `ToolAdminDashboard` och skicka ned via
props eller React Context. Alternativt, använd en gemensam provider-komponent.

### K4. `confirm()` i `bulkPromoteToLive` — blockerande browser-dialog i admin-verktyg

`deploy-panel.tsx:312` använder `window.confirm()` för en kritisk bulk-operation.
Detta är:
- Inkonsekvent med resten av koden som använder `AlertDialog`/`AlertDialogAction`
- Inte stylat — raw browser-dialog i ett polerat admin-UI
- Blockerar JS-eventkön (synkron)

**Åtgärd:** Använd `AlertDialog` som redan finns importerad och används för
rollback-dialogen i samma fil.

---

## ALLVARLIGA PROBLEM

### A1. Pipeline Explorer visar en 3-stegs visualisering men hämtar bara verktygsdata

`PipelineExplorerPanel` visar tre steg: Intent → Agent → Tool.
Men backend-endpointen `debug-retrieval` returnerar:
```json
{
  "intent": null,
  "agents": [],
  "tools": [...],
  ...
}
```

Intent är **alltid `null`** och agents är **alltid `[]`** i svaret.
Gränssnittet visar sedan "Väntar på körning..." för Intent och Agent, men
dessa värden kommer aldrig populeras med den nuvarande backend-koden.
Användaren får en vilseledande upplevelse.

**Åtgärd:** Antingen implementera fullständig intent/agent-debug i backenden,
eller ta bort/dölj Intent och Agent-stegen i frontend tills de finns.

### A2. `TrendBars` i deploy-panel har osäker type-access

`deploy-panel.tsx:118-132` casts `point.success_rate` direkt utan
TypeScript-säkerhet:
```tsx
const raw = point.success_rate;
const numeric = typeof raw === "number" ? raw : 0;
```
Men `points` är typad som `Array<Record<string, unknown>>`, dvs helt otypad.
Dessutom accessas `point.run_at`, `point.eval_name` utan någon validering.

**Åtgärd:** Använd `ToolEvaluationStageHistoryItem`-typen som redan finns
definierad, istället för `Record<string, unknown>`.

### A3. `StageHistorySection` triggar infinite re-render-loop

`deploy-panel.tsx:163-166`:
```tsx
useEffect(() => {
    if (effectiveCategory && effectiveCategory !== selectedCategory) {
        onSelectCategory(effectiveCategory);
    }
}, [effectiveCategory, selectedCategory, onSelectCategory]);
```

`onSelectCategory` är `setAgentHistoryCategory` (en state-setter).
Sekvensen: parent renderar → effectiveCategory beräknas → `useEffect` kallar
`onSelectCategory` → parent re-renderar → `useEffect` körs igen.

Om `onSelectCategory` inte har stabil identitet (React state-setters har det,
men det antas implicit), eller om `effectiveCategory` beräknas till ett nytt
värde varje render, får vi en loop.

**Risk:** Fungerar sannolikt i praktiken pga React state-setter stabilitet,
men designen är fragil och anti-pattern.

### A4. `_canToggle` definieras men används aldrig

`deploy-panel.tsx:277` definierar `_canToggle` med understreck-prefix (konvention
för "unused"), men funktionen borde sannolikt användas som disabled-guard på
promote-knappen. Dess logik dupliceras inline i `toggleToolStatus`.

### A5. Eval batch-polling saknar cleanup vid unmount

`eval-panel.tsx:347-369` — `runOne` pollar med `while (!done)` och
`setTimeout`. Om komponenten unmountas under polling:
- `setBatchJobs(...)` kallas på en unmountad komponent → React warning
- Det finns ingen `AbortController` eller ref-check för att avbryta polling
- Jämför med single-eval polling som har cleanup via `useEffect` return

### A6. Audit trail i deploy-panel är en tom placeholder

`deploy-panel.tsx:340`:
```tsx
const [auditEntries] = useState<AuditTrailEntry[]>([]);
```
Kommentaren säger "placeholder; will be populated when backend supports it" —
men `AuditTrail` har redan data i den gamla `OverviewTab` som hämtar från
lifecycle API:t. Backenden stödjer det.

**Åtgärd:** Koppla in den befintliga audit-trail-datan.

---

## KVALITETSPROBLEM

### Q1. 8 Biome-lintvarningar

Biome check hittar 8 warnings:
- **6× `noArrayIndexKey`** — Array-index som React `key` i:
  - `deploy-panel.tsx:128` (TrendBars)
  - `deploy-panel.tsx:201` (StageHistorySection tabell)
  - `eval-panel.tsx:547`, `836`
  - `pipeline-explorer-panel.tsx:392`
  - `tool-catalog-panel.tsx:183`, `236`

- **1× `noUnusedFunctionParameters`** — `tool` parameter i `ToolEditor`
  (tool-catalog-panel.tsx:84) tas emot men används aldrig

Kodbasen kräver unika, stabila `key`-props (se `.rules/require-unique-id-props`).

### Q2. Duplicerad `formatPercent`/`formatSignedPercent`

`formatPercent` definieras i **två** filer:
- `use-tool-catalog.ts` (exporterad)
- `deploy-panel.tsx` (lokal)

`formatSignedPercent` definieras i **två** filer:
- `use-tool-catalog.ts` (exporterad)
- `deploy-panel.tsx` (lokal)

`eval-panel.tsx` importerar `formatPercent` från hooken (korrekt).
`deploy-panel.tsx` definierar sin egen lokala version.

### Q3. Hardcoded domänkategorisering i hooken

`use-tool-catalog.ts:73-105` — `categorizeTool()` har hårdkodad logik som
mappnar tool_id-prefix till domäner (`smhi_` → weather, `riksdag_` → politik, etc.).
Detta bryter mot "DB-driven flow graph" principen i CLAUDE.md och
kommer kräva kodändringar varje gång ett nytt verktyg läggs till med ett
namn som inte matchar mönstren.

### Q4. Inkonsekvent felhantering

- `pipeline-explorer-panel.tsx` visar `toast.error()` + separat error card
- `eval-panel.tsx` visar bara `toast.error()`
- `deploy-panel.tsx` visar `toast.error()` + ingen visuell error state
- `tuning-panel.tsx` visar `toast.error()` + ingen visuell error state
- `tool-catalog-panel.tsx` visar inline error card

### Q5. `_topTool` unused variable i pipeline-explorer

`pipeline-explorer-panel.tsx:286`:
```tsx
const _topTool = result?.tools?.[0] ?? null;
```
Prefixad med `_` men borde antingen användas eller tas bort.

### Q6. `genMode` och `categoryId` state med unused setters

`eval-panel.tsx:227-228`:
```tsx
const [genMode, _setGenMode] = useState<GenerationMode>("category");
const [categoryId, _setCategoryId] = useState("");
```
Setters prefixade med `_` men aldrig använda — användaren kan inte byta
genereringsläge eller välja kategori i single-eval-mode trots att UI:t
antyder det genom att ha genereringskonfiguration.

### Q7. `useToolCatalog` hook anropas med och utan argument

- `PipelineExplorerPanel` kallar `useToolCatalog()` utan argument
- `TuningPanel` kallar `useToolCatalog()` utan argument
- `EvalPanel` kallar `useToolCatalog()` utan argument
- `ToolCatalogPanel` kallar `useToolCatalog()` utan argument

Men hook-funktionen accepterar `searchSpaceId?: number`. Alla konsumenter
förlitar sig på att hooken internt hämtar `searchSpaceId` från `getToolSettings`,
men detta betyder att hook-parametern `searchSpaceId` aldrig används och
leder till förvirrande API-design.

### Q8. Backend-endpoint returnerar format som inte matchar frontend-typer

Backend `debug-retrieval` returnerar:
```python
{
    "intent": None,
    "agents": [],
    "tools": [...],
    "thresholds": {...},
    "query": query,
}
```

Men frontends `DebugRetrievalResult` interface förväntar sig:
```tsx
interface DebugRetrievalResult {
    intent: DebugIntentResult | null;
    agents: DebugAgentCandidate[];
    tools: DebugToolCandidate[];
    thresholds: { ... agent_auto_margin: number } | null;
    timing_ms: number;  // <-- Finns inte i backend-svaret
    error?: string;
}
```

`timing_ms` saknas helt i backend-svaret. Frontend visar `0ms` eller
undefined-beteende.

`thresholds.agent_auto_margin` saknas i backend-svaret (backend skickar
`agent_auto_score` men inte `agent_auto_margin`).

---

## SAMMANFATTANDE REKOMMENDATION

**Åtgärd: Begär omarbetning (Request changes)**

### Måste fixas innan merge:
1. Lägg till admin-guard på `debug-retrieval` (K2)
2. Fixa eller ta bort den vilseledande Intent/Agent-visningen i Pipeline Explorer (A1)
3. Ersätt `confirm()` med `AlertDialog` (K4)
4. Fixa backend-response format att matcha frontend-typer — lägg till `timing_ms` (Q8)
5. Ta bort dead code: den gamla `tool-admin-page.tsx` (K1)
6. Koppla in audit-trail-data istället för tom placeholder (A6)

### Bör fixas:
7. Lyft `useToolCatalog` till dashboard-nivå för att undvika redundanta API-anrop (K3)
8. Använd `ToolEvaluationStageHistoryItem` typ istället för `Record<string, unknown>` (A2)
9. Ta bort duplicerade utility-funktioner (Q2)
10. Fixa unused variables (`_topTool`, `_canToggle`, `genMode`/`categoryId`) (A4, Q5, Q6)
11. Lägg till abort/cleanup för batch-polling vid unmount (A5)
12. Fixa Biome-lint warnings (array index keys, unused params) (Q1)

### Överväg:
13. Ersätt hårdkodad domänkategorisering med datadriven approach (Q3)
14. Standardisera felhantering across paneler (Q4)
