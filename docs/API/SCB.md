# SCB API Integration — Fullständig Dokumentation

> **Version:** 5.0
> **Datum:** 2026-03-10
> **Status:** Produktion — 7-verktygspipeline med JSON-stat2-dekoder & auto-complete (v5.0)
> **Författare:** OneSeek-teamet

---

## Innehåll

1. [Översikt](#1-översikt)
2. [Arkitektur](#2-arkitektur)
3. [Filstruktur](#3-filstruktur)
4. [SCB PxWeb API — v1 (legacy)](#4-scb-pxweb-api--v1-legacy)
5. [SCB PxWebApi v2 — Aktiv](#5-scb-pxwebapi-v2--aktiv)
6. [ScbService — Kärntjänst](#6-scbservice--kärntjänst)
7. [Statistics Agent — LangGraph Bigtool](#7-statistics-agent--langgraph-bigtool)
8. [Verktygsregistret — 47 domänverktyg](#8-verktygsregistret--47-domänverktyg)
9. [Domain Fan-Out](#9-domain-fan-out)
10. [Routing och Intent Detection](#10-routing-och-intent-detection)
11. [Kodkvalitetsanalys](#11-kodkvalitetsanalys)
12. [Buggar](#12-buggar)
13. [Optimeringar](#13-optimeringar)
14. [Kompletthetsanalys](#14-kompletthetsanalys)
15. [Testsvit](#15-testsvit)
16. [Evalueringsdata](#16-evalueringsdata)
17. [Konfiguration och Environment](#17-konfiguration-och-environment)
18. [7-verktygspipeline (v5.0)](#18-7-verktygspipeline-v50)
19. [Framtida Arbete](#19-framtida-arbete)

---

## 1. Översikt

SCB-integrationen (Statistiska Centralbyrån) ger OneSeek tillgång till hela Sveriges officiella statistikdatabas via PxWeb API. Systemet:

- **7 LLM-drivna verktyg** för sökning, navigering, inspektion, preview, validering och datahämtning
- **47 domänverktyg** som alternativa ingångar per ämnesområde
- **JSON-stat2-dekoder** som konverterar rå API-data till läsbara markdown-tabeller
- **Auto-complete** som fyller saknade variabler med elimination-defaults
- **v2-uttryck** (TOP, FROM, RANGE, *) för förenklade frågor
- **Trädnavigering** för explorativa frågor
- Hanterar batching vid stora datamängder (>150 000 celler)
- Lagrar resultat i OneSeek:s kunskapsbas via ConnectorService

**Täckning:** 20+ ämnesområden, 47 domänverktyg + 7 LLM-verktyg, ~2000+ tabeller

---

## 2. Arkitektur

```
┌──────────────────────────────────────────────────────────────────┐
│                     Supervisor Agent (Phase 2)                    │
│   Intent: "statistik" → route till Statistics Agent               │
└──────────────┬───────────────────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │  Statistics Agent    │  (LangGraph Bigtool)
    │  - retrieve_tools() │  ← Vektorliknande sökning bland 47+7 verktyg
    │  - NormalizingChat   │
    │  - max 2 tools/turn │
    └──────┬────────┬─────┘
           │        │
    ┌──────▼──┐  ┌──▼───────────────────────┐
    │ 47 dom- │  │ 7 LLM-verktyg (v5.0)     │
    │ änverk- │  │                           │
    │ tyg     │  │ Discovery:                │
    │         │  │  scb_search, scb_browse   │
    │ scb_    │  │                           │
    │ befol-  │  │ Inspektion:               │
    │ kning,  │  │  scb_inspect, scb_codelist│
    │ scb_    │  │                           │
    │ arbets- │  │ Data:                     │
    │ marknad │  │  scb_preview, scb_validate│
    │ ...     │  │  scb_fetch                │
    └────┬────┘  └────────────┬─────────────┘
         │                    │
         └────────┬───────────┘
                  │
       ┌──────────▼──────────────┐
       │      ScbService           │
       │  - search_tables()        │
       │  - list_nodes() (v1 tree) │
       │  - get_table_metadata()   │
       │  - get_default_selection() │
       │  - get_codelist()         │
       │  - auto_complete_selection│
       │  - query_table()          │
       │  - decode_jsonstat2_to_   │
       │    markdown()             │
       └──────────┬────────────────┘
                  │
       ┌──────────▼────────────┐
       │  SCB PxWebApi (v2)       │
       │  statistikdatabasen.scb. │
       │  se/api/v2/              │
       │  - GET /tables?query=    │
       │  - GET /tables/{id}/meta │
       │  - GET /tables/{id}/     │
       │    defaultselection      │
       │  - POST /tables/{id}/data│
       │  - GET /codelists/{id}   │
       │  (v1 fallback: list_nodes)│
       └─────────────────────────┘
                  │
       ┌──────────▼────────────┐
       │  ConnectorService       │
       │  - ingest_tool_output() │
       │  → PostgreSQL + PGVector│
       └─────────────────────────┘
```

### Domain Fan-Out (parallell exekvering)

```
Fråga: "Jämför befolkning och arbetslöshet i Sverige"
                    │
         ┌──────────┼───────────┐
         ▼          ▼           ▼
   scb_befolkning  scb_arbetsmarknad  scb_priser_konsumtion
         │          │           │
         └──────────┼───────────┘
                    ▼
            Samlat resultat
```

---

## 3. Filstruktur

```
surfsense_backend/
├── app/
│   ├── services/
│   │   ├── scb_service.py              # Kärntjänst: HTTP, navigering, JSON-stat2-dekoder, auto-complete, v2+v1
│   │   └── scb_regions.py              # Fullständigt regionregister (290+21+Riket) med diakritiknormalisering
│   │
│   ├── utils/
│   │   └── text.py                     # Centraliserad textnormalisering (KQ-1)
│   │
│   └── agents/new_chat/
│       ├── scb_tool_definitions.py      # 47 SCB-verktygsdefinitioner + scoring (KQ-3)
│       ├── statistics_agent.py          # Agent-fabrik + tool-bygger
│       ├── statistics_prompts.py        # System prompt med 7-verktygsflöde
│       ├── bigtool_store.py             # Bigtool store med SCB-verktygsregistrering
│       ├── domain_fan_out.py            # Parallell exekvering per domän
│       ├── supervisor_constants.py      # Routing-konstanter inkl. SCB
│       ├── supervisor_routing.py        # Intent detection + agent-alias
│       ├── tool_identity_defaults.py    # Metadata per SCB-verktyg
│       └── tools/
│           ├── scb_llm_tools.py         # 7 LLM-drivna verktyg (v5.0)
│           └── registry.py              # ToolDefinition-registrering för alla 7+47 SCB-verktyg
│
├── tests/
│   ├── test_scb_llm_tools.py           # 46 tester för de 7 LLM-verktygen
│   ├── test_scb_service.py             # 72 tester för ScbService
│   └── test_scb_regions.py             # 36 tester för regionregistret
│
eval/api/scb/
├── be/scb-be_20260212_v1.json          # Eval: befolkningskategori
└── all_categories/scb-provider_20260214_v1.json  # Eval: alla kategorier
```

---

## 4. SCB PxWeb API — v1 (legacy, används för trädnavigering)

### Bas-URL

```
https://api.scb.se/OV0104/v1/doris/sv/ssd/
```

### Endpoints

| Operation | Metod | URL-mönster | Beskrivning |
|-----------|-------|-------------|-------------|
| Lista noder | GET | `{base}/{path}/` | Navigerar trädstruktur, returnerar `[{id, type, text, updated}]` |
| Tabellmetadata | GET | `{base}/{path}/{tabell}` | Returnerar variabler, värden och valueTexts |
| Hämta data | POST | `{base}/{path}/{tabell}` | Skickar query-payload, returnerar json-stat2 |

### Nodtyper

- `"l"` — Länk/mapp (har barn-noder)
- `"t"` — Tabell (blad-nod, innehåller data)

### Query Payload (v1)

```json
{
  "query": [
    {
      "code": "Region",
      "selection": {
        "filter": "item",
        "values": ["00"]
      }
    },
    {
      "code": "Tid",
      "selection": {
        "filter": "item",
        "values": ["2023", "2024"]
      }
    }
  ],
  "response": {
    "format": "json-stat2"
  }
}
```

### Begränsningar (v1)

| Begränsning | Värde |
|-------------|-------|
| Max celler per fråga | 150 000 |
| Rate limit | 30 anrop / 10 sekunder (per IP) |
| Timeout | 25s (konfigurerat i ScbService) |
| Responsformat | json-stat2 (default) |

---

## 5. SCB PxWebApi v2 — Aktiv (primär)

### Bakgrund

SCB lanserade PxWebApi 2.0 i oktober 2025 som ersättare för v1. Den nya API:n har RESTful design, stabilare URL-struktur och stöd för fler output-format. **v2 är nu default i OneSeek.**

### Ny Bas-URL

```
https://statistikdatabasen.scb.se/api/v2/
```

### Nya Endpoints (v2)

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/tables` | GET | Lista alla tabeller med filtrering (query, pastDays, pageNumber) |
| `/tables/{id}` | GET | Hämta tabell-info (id, label, description, updated, variableNames) |
| `/tables/{id}/metadata` | GET | Detaljerad metadata med variabler och kodsystem |
| `/tables/{id}/defaultselection` | GET | Standardval för parametrar |
| `/tables/{id}/data` | GET/POST | Hämta data med val och output-format |
| `/codelists/{id}` | GET | Hämta kodlista med värdemap |
| `/config` | GET | API-konfiguration och capabilities |

### Query-parametrar (v2 GET /data)

```
/tables/{id}/data?valuecodes[Region]=00,01&valuecodes[Tid]=2023,2024&outputFormat=json-stat2&lang=sv
```

### POST body (v2 /data)

```json
{
  "selection": [
    {
      "variableCode": "Region",
      "codelist": null,
      "valueCodes": ["00", "01"]
    }
  ],
  "placement": {
    "heading": ["Tid"],
    "stub": ["Region"]
  }
}
```

### Output-format (v2)

| Format | Identifierare |
|--------|---------------|
| JSON-stat 2.0 | `json-stat2` |
| CSV | `csv` |
| Excel | `xlsx` |
| Parquet | `parquet` |
| HTML | `html` |
| PX | `px` |
| JSON-PX | `json-px` |

### HTTP-statuskoder (v2)

| Kod | Betydelse |
|-----|-----------|
| 200 | OK |
| 400 | Ogiltig förfrågan |
| 403 | Överskrider max celler |
| 404 | Tabell/resurs ej funnen |
| 429 | Rate limit överskriden |

### Migrationsmatris: v1 → v2

| Funktion | v1 (nuvarande) | v2 (mål) | Förändring |
|----------|-----------------|-----------|------------|
| **Bas-URL** | `api.scb.se/OV0104/v1/doris/sv/ssd/` | `statistikdatabasen.scb.se/api/v2/` | Nytt domännamn |
| **Navigering** | GET med sökväg i URL | GET `/tables` med `query`-param | Platt sökning istället för trädnavigering |
| **Metadata** | GET på tabellsökväg | GET `/tables/{id}/metadata` | Dedikerat endpoint |
| **Datahämtning** | POST med `query[]`-array | GET/POST `/tables/{id}/data` | GET med query-params eller POST med `selection[]` |
| **Tabell-ID** | Sökvägsbaserat (`BE/BE0101/BE0101A/BesijK18`) | ID-baserat (`TAB4537`) | Stabilare, ej påverkat av omstrukturering |
| **Svarformat** | Enbart json-stat2 | json-stat2, csv, xlsx, parquet, html, px | Fler format |
| **Sökning** | Manuell trädnavigering | `GET /tables?query=befolkning` | Inbyggd textsökning |
| **Paginering** | Ingen | `pageNumber` + `pageSize` | Stöd för paginering |
| **Kodsystem** | Ingen dedikerad | `/codelists/{id}` | Centraliserade kodlistor |

### Migrationssteg (prioriterad ordning)

#### Steg 1: Dual-URL-stöd (P1)

```python
# scb_service.py — Ändra SCB_BASE_URL
SCB_BASE_URL_V1 = "https://api.scb.se/OV0104/v1/doris/sv/ssd/"
SCB_BASE_URL_V2 = "https://statistikdatabasen.scb.se/api/v2/"
SCB_BASE_URL = SCB_BASE_URL_V2  # Default till v2
```

**Påverkan:** `ScbService.__init__()`, alla anrop via `self.base_url`

#### Steg 2: Ny tabellsökning via `/tables` (P1)

Ersätt den rekursiva trädnavigeringen i `collect_tables()` med:

```python
async def search_tables(self, query: str, *, limit: int = 80) -> list[ScbTable]:
    """Search tables via v2 /tables endpoint instead of tree traversal."""
    params = {"query": query, "pageSize": limit, "lang": "sv"}
    url = f"{self.base_url}tables"
    data = await self._get_json_with_params(url, params)
    tables = []
    for item in data.get("tables", []):
        tables.append(ScbTable(
            id=item["id"],
            path=item["id"],  # v2 uses ID-based paths
            title=item.get("label", ""),
            updated=item.get("updated"),
        ))
    return tables
```

**Vinst:** Eliminerar ~140 HTTP-anrop för trädnavigering till 1 sökanrop.

#### Steg 3: Uppdaterad metadata-hämtning (P1)

```python
async def get_table_metadata_v2(self, table_id: str) -> dict[str, Any]:
    """Fetch metadata via v2 /tables/{id}/metadata."""
    url = f"{self.base_url}tables/{table_id}/metadata"
    return await self._get_json(url)
```

#### Steg 4: Ny query-byggare för v2 POST-format (P2)

v2 använder `selection[]` istället för `query[]`:

```python
def _payload_from_selections_v2(self, selections: list[dict]) -> dict:
    return {
        "selection": [
            {
                "variableCode": sel["code"],
                "valueCodes": sel["values"],
            }
            for sel in selections if sel.get("values")
        ]
    }
```

#### Steg 5: Stöd för nya output-format (P3)

Lägg till `outputFormat`-parameter för CSV, parquet etc.

#### Steg 6: Kodsystem-integration (P3)

Integrera `/codelists/{id}` för bättre variabelupplösning.

### Bakåtkompatibilitet

SCB har angett att v2 är bakåtkompatibelt med v2-beta-formatet. Dock krävs anpassning av:
- URL-struktur (sökvägsbaserad → ID-baserad)
- Request body-format (`query[]` → `selection[]`)
- Response-hantering (nya fält, paginering)

**Status:** Implementerat. v2 är default med automatisk v1-fallback.

---

## 6. ScbService — Kärntjänst

**Fil:** `surfsense_backend/app/services/scb_service.py` (1200+ rader)

### Klass-API

```python
class ScbService:
    def __init__(self, base_url: str = SCB_BASE_URL, timeout: float = 25.0)

    # HTTP-lager
    async def _get_json(self, url: str) -> Any
    async def _post_json(self, url: str, payload: dict) -> Any

    # Navigering
    async def list_nodes(self, path: str) -> list[dict]           # v1 trädnavigering
    async def search_tables(self, query, *, limit=80) -> list      # v2 textsökning
    async def collect_tables(self, base_path, query, ...) -> list[ScbTable]

    # Tabellval
    async def get_table_metadata(self, table_path: str) -> dict
    async def get_default_selection(self, table_id: str) -> dict[str, list[str]]  # NYI v5.0
    async def get_codelist(self, codelist_id: str) -> dict[str, Any]              # NYI v5.0
    async def find_best_table_candidates(self, ...) -> tuple[ScbTable | None, list[ScbTable]]

    # Auto-complete & validering (v5.0)
    def auto_complete_selection(                                                   # NYI v5.0
        self, metadata, selection, default_selection=None
    ) -> tuple[dict[str, list[str]], list[str]]

    # Frågebyggare
    def build_query_payload(self, metadata, query, ...) -> tuple[dict, list[str], list[str]]
    def build_query_payloads(self, metadata, query, ...) -> tuple[list[dict], ...]

    # Datahämtning & dekodning
    async def query_table(self, table_path: str, payload: dict) -> dict
    @staticmethod
    def decode_jsonstat2_to_markdown(response, *, max_rows=100) -> dict  # NYI v5.0
```

### Nya metoder i v5.0

#### `get_default_selection(table_id)` → `dict[str, list[str]]`
Hämtar SCB:s rekommenderade urval via `GET /tables/{id}/defaultselection`.
Returnerar `{"Region": ["00"], "Tid": ["2024"], ...}`.

#### `get_codelist(codelist_id)` → `dict`
Hämtar en kodlista via `GET /codelists/{id}`.
Returnerar `{"id": "vs_RegionLän", "values": [{"code": "01", "label": "Stockholm"}]}`.

#### `auto_complete_selection(metadata, selection, default_selection?)` → `(selection, log)`
Fyller i saknade variabler automatiskt:
1. `elimination=true` + `eliminationValueCode` → använd det
2. `elimination=true` utan eliminationValueCode → defaultselection → "tot"/"total" → `"*"`
3. `elimination=false` → defaultselection → första värdet + varning

#### `decode_jsonstat2_to_markdown(response, max_rows=100)` → `dict`
**DEN KRITISKA NYA METODEN.** Konverterar JSON-stat2 flat value-array till läsbar markdown-tabell:
1. Läser `id[]` (dimensioner), `size[]`, `value[]` (platt array)
2. Bygger label-mappningar via `dimension.X.category.label`
3. Cartesian product av dimensionskoder → rader
4. Flat-index via stride-multiplikation (row-major ordning)
5. Hanterar `status`-markörer (saknade värden → "..")
6. Formaterar med svenska tusentalsavgränsare (mellanslag)
7. Trunkerar vid `max_rows`

Returnerar: `{data_table, row_count, truncated, unit, ref_period, footnotes, source}`

### Dataklasser

```python
@dataclass(frozen=True)
class ScbTable:
    id: str              # Tabellkod, t.ex. "BefolkFowordsK18"
    path: str            # Fullständig sökväg, t.ex. "BE/BE0101/BE0101A/BefolkFowordsK18"
    title: str           # Tabelltitel
    updated: str | None  # ISO-datum för senaste uppdatering
    breadcrumb: tuple[str, ...]  # Navigeringsspår

@dataclass(frozen=True)
class ScbQueryResult:
    table: ScbTable
    payload: dict
    data: dict
    selection_summary: list[str]
    warnings: list[str]
```

### Tabellsökningsalgoritm

Sökningen sker i tre faser:

**Fas 1: Trädnavigering** (`collect_tables`)
1. BFS genom SCB:s mappstruktur med prioriterad köordning
2. Varje nod poängsätts mot sökfrågan (token-matchning)
3. Högst rankade grenar expanderas först
4. Begränsning: max 80 tabeller, max 4 djup, max 140 noder

**Fas 2: Metadata-scoring** (`find_best_table_candidates`)
1. De 10 bästa tabellerna från fas 1 hämtas parallellt (asyncio.gather)
2. Varje tabells metadata poängsätts mot:
   - Variabelnamn-matchning (+3 per match)
   - Tidsperiod-matchning (+3 per år-träff, -4 om år saknas)
   - Region-variabel bonus (+4 om frågan nämner region)
   - Kön-variabel bonus (+3 om frågan nämner kön)
   - Ålder-variabel bonus (+2 om frågan nämner ålder)
   - Värdetext-matchning (+2 om relevanta värden finns)

**Fas 3: Resultatrankning**
1. Kombinerad poäng (bas + metadata) sorteras
2. Bästa tabell + upp till 5 kandidater returneras

### Variabelval

`_build_selections()` implementerar intelligent variabelval:

| Variabeltyp | Detektionslogik | Standardval |
|-------------|-----------------|-------------|
| **Tid** | Kod/label innehåller "tid", "time", "ar", "year" | Senaste N värden |
| **Region** | Kod/label innehåller "region", "lan", "kommun" | Riket/Sverige |
| **Kön** | Kod/label innehåller "kon", "sex", "gender" | Totalt |
| **Ålder** | Kod/label innehåller "alder", "age" | Totalt |
| **Övriga** | Textmatchning mot sökfrågan | Totalt/alla, annars första värdet |

### Batching-strategi

När celltalet överstiger 150 000:
1. Identifiera variabel med flest värden (prioritet: tid > region > övriga)
2. Dela upp värdena i chunks som ryms under gränsen
3. Generera separata payloads per chunk
4. Max 8 batchar (konfigurerbart)

### Cache

- **Nodcache** (`_node_cache`): Cacher GET-svar per URL — undviker dubbletter vid BFS
- **Metadatacache** (`_metadata_cache`): Cacher tabellmetadata per URL

---

## 7. Statistics Agent — LangGraph Bigtool

**Fil:** `surfsense_backend/app/agents/new_chat/statistics_agent.py` (~330 rader)

### Agent-skapande

```python
def create_statistics_agent(
    *,
    llm,                          # LiteLLM-modell
    connector_service,            # ConnectorService
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    checkpointer: Checkpointer | None,
    scb_base_url: str | None = None,
)
```

Agenten skapas med `langgraph_bigtool.create_agent()`:
- **limit=2**: Max 2 verktyg per tur
- **retrieve_tools_function**: `retrieve_scb_tools()` — poängbaserad sökning bland 47+7 verktyg
- **NormalizingChatWrapper**: Normaliserar LLM-input

### Verktygsval

`retrieve_scb_tools(query, limit=2)` poängsätter alla 47 domänverktyg:

```python
Poängsättning:
  +5  om verktygets namn matchas i frågan
  +3  per keyword-match
  +6  per tabellkod-match
  +1  per token i beskrivningen
```

De 7 LLM-verktygen (scb_search, scb_browse, etc.) registreras separat via `tools/registry.py` som `BUILTIN_TOOLS` och är alltid tillgängliga.

### System Prompt (v5.0)

Prompten i `statistics_prompts.py` dokumenterar alla 7 verktyg med arbetsflöden:

```
Du har 7 SCB-verktyg:

Discovery:
- scb_search(query)  — Sök tabeller med nyckelord
- scb_browse(path)   — Navigera SCB:s ämnesträd

Inspektion:
- scb_inspect(table_id)     — Full metadata, defaults, hints
- scb_codelist(codelist_id) — Hämta kodlista (län, kommuner)

Data:
- scb_preview(table_id, selection?) — Snabb förhandsvisning (~20 rader)
- scb_validate(table_id, selection) — Torrkörning utan datahämtning
- scb_fetch(table_id, selection, codelist?) — Hämta data som markdown-tabell

Typiskt arbetsflöde (3 steg):
1. scb_search("befolkning") → hitta tabell
2. scb_inspect("TAB638")    → se variabler, defaults
3. scb_fetch("TAB638", {"Region": ["0180"], "Tid": ["TOP(3)"]}) → data
```

---

## 8. Verktygsregistret — 47 domänverktyg + 7 LLM-verktyg

### Ämnesområden (20 breda + 20 specifika)

| # | Tool ID | Bas-path | Ämnesområde |
|---|---------|----------|-------------|
| 1 | `scb_arbetsmarknad` | `AM/` | Arbetsmarknadsstatistik |
| 2 | `scb_befolkning` | `BE/` | Befolkningsstatistik |
| 3 | `scb_boende_byggande` | `BO/` | Boende, byggande |
| 4 | `scb_demokrati` | `ME/` | Demokrati, val |
| 5 | `scb_energi` | `EN/` | Energi |
| 6 | `scb_finansmarknad` | `FM/` | Finansmarknad |
| 7 | `scb_handel` | `HA/` | Handel |
| 8 | `scb_hushall` | `HE/` | Hushållens ekonomi |
| 9 | `scb_halsa_sjukvard` | `HS/` | Hälso- och sjukvård |
| 10 | `scb_jordbruk` | `JO/` | Jordbruk, skogsbruk, fiske |
| 11 | `scb_kultur` | `KU/` | Kultur och fritid |
| 12 | `scb_levnadsforhallanden` | `LE/` | Levnadsförhållanden |
| 13 | `scb_miljo` | `MI/` | Miljö |
| 14 | `scb_nationalrakenskaper` | `NR/` | Nationalräkenskaper |
| 15 | `scb_naringsverksamhet` | `NV/` | Näringsverksamhet |
| 16 | `scb_offentlig_ekonomi` | `OE/` | Offentlig ekonomi |
| 17 | `scb_priser_konsumtion` | `PR/` | Priser och konsumtion |
| 18 | `scb_socialtjanst` | `SO/` | Socialtjänst |
| 19 | `scb_transporter` | `TK/` | Transporter |
| 20 | `scb_utbildning` | `UF/` | Utbildning och forskning |
| 21 | `scb_amnesovergripande` | `AA/` | Ämnesövergripande |
| 22 | `scb_befolkning_folkmangd` | `BE/BE0101/BE0101A/` | Folkmängd (specifik) |
| 23 | `scb_befolkning_forandringar` | `BE/BE0101/BE0101G/` | Befolkningsförändringar |
| 24 | `scb_befolkning_fodda` | `BE/BE0101/BE0101H/` | Födda |
| 25 | `scb_arbetsmarknad_arbetsloshet` | `AM/AM0401/` | Arbetslöshet (specifik) |
| 26 | `scb_arbetsmarknad_sysselsattning` | `AM/AM0301/` | Sysselsättning (specifik) |
| 27 | `scb_arbetsmarknad_lon` | `AM/AM0403/` | Löner (specifik) |
| 28 | `scb_utbildning_gymnasie` | `UF/UF0104/` | Gymnasieskola |
| 29 | `scb_utbildning_hogskola` | `UF/UF0202/` | Högskola |
| 30 | `scb_utbildning_forskning` | `UF/UF0301/` | Forskning |
| 31 | `scb_naringsliv_foretag` | `NV/NV0101/` | Företag |
| 32 | `scb_naringsliv_omsattning` | `NV/NV0109/` | Omsättning |
| 33 | `scb_naringsliv_nyforetagande` | `NV/NV0006/` | Nyföretagande |
| 34 | `scb_miljo_utslapp` | `MI/MI0106/` | Utsläpp |
| 35 | `scb_miljo_energi` | `MI/MI0107/` | Miljö-energi |
| 36 | `scb_priser_kpi` | `PR/PR0101/` | KPI |
| 37 | `scb_priser_inflation` | `PR/PR0301/` | Inflation |
| 38 | `scb_transporter_person` | `TK/TK1001/` | Persontransporter |
| 39 | `scb_transporter_gods` | `TK/TK1201/` | Godstransporter |
| 40 | `scb_boende_bygglov` | `BO/BO0301/` | Bygglov |
| 41 | `scb_boende_nybyggnation` | `BO/BO0101/` | Nybyggnation |
| 42 | `scb_boende_bestand` | `BO/BO0201/` | Bostadsbestånd |

### Verktygsdatastruktur

```python
@dataclass(frozen=True)
class ScbToolDefinition:
    tool_id: str              # Unikt verktygs-ID
    name: str                 # Visningsnamn (svenska)
    base_path: str            # SCB-sökväg (t.ex. "BE/")
    description: str          # Beskrivning
    keywords: list[str]       # Sökord för retrieval
    example_queries: list[str]  # Exempelfrågor
    table_codes: list[str]    # Vanliga tabellkoder
    typical_filters: list[str]  # Typiska filterdimensioner
```

---

## 9. Domain Fan-Out

**Fil:** `surfsense_backend/app/agents/new_chat/domain_fan_out.py`

### SCB Fan-Out Konfiguration

```python
SCB_CATEGORIES = (
    FanOutCategory(name="befolkning",    tool_ids=("scb_befolkning",),         priority=0),
    FanOutCategory(name="arbetsmarknad", tool_ids=("scb_arbetsmarknad",),      priority=1),
    FanOutCategory(name="priser",        tool_ids=("scb_priser_konsumtion",),  priority=2),
    FanOutCategory(name="utbildning",    tool_ids=("scb_utbildning",),         priority=3),
    FanOutCategory(name="naringsliv",    tool_ids=("scb_naringsverksamhet",),  priority=4),
    FanOutCategory(name="miljo",         tool_ids=("scb_miljo",),              priority=5),
)
```

**Max parallella:** 3
**Timeout:** 30s
**Selektiv:** Ja — triggas av keyword-matchning

### Trigger-ord per kategori

| Kategori | Trigger-ord |
|----------|-------------|
| befolkning | befolkning, invånare, folkmängd, invandring, utvandring, födda, döda |
| arbetsmarknad | arbetsmarknad, arbetslöshet, sysselsättning, lön, löner, jobb |
| priser | pris, priser, inflation, kpi, konsument |
| utbildning | utbildning, skola, gymnasium, högskola, universitet |
| naringsliv | företag, näringsliv, omsättning, nyföretagande |
| miljo | miljö, utsläpp, energi, klimat |

---

## 10. Routing och Intent Detection

### Supervisor → Statistik-agent

```python
# supervisor_constants.py
_SPECIALIZED_AGENTS = {
    "statistik",    # SCB/Kolada tools
    ...
}

_COMPAT_AGENT_NAMES = {
    "statistics": "statistik",
}
```

### Agent-alias

```python
# supervisor_routing.py — _guess_agent_from_alias()
token_rules = [
    (("stat", "scb", "data"), "statistik"),
]
```

### Route-policies

```python
_ROUTE_STRICT_AGENT_POLICIES = {
    "jämförelse": {"syntes", "statistik", "kunskap"},
    "compare": {"syntes", "statistik", "kunskap"},
}
```

---

## 11. Kodkvalitetsanalys

### KQ-1: Duplicerad `_normalize_text()` (P2 — Medel) — FIXAD

**Problem:** `_normalize_text()` finns i **två** filer med nästan identisk logik:
- `scb_service.py:45` — Använder `str.maketrans` med dict
- `statistics_agent.py:856` — Använder manuella `.replace()`-anrop

**Effekt:** Inkonsistent beteende vid framtida ändringar.
**Fix:** Centralisera till en gemensam utility, t.ex. `app/utils/text.py`.

### KQ-2: httpx.AsyncClient skapas per anrop (P2 — Medel) — FIXAD

**Problem:** Varje `_get_json()` och `_post_json()` skapar en ny `httpx.AsyncClient`:

```python
async def _get_json(self, url: str) -> Any:
    async with httpx.AsyncClient(timeout=self.timeout) as client:  # ← Ny connection pool
        response = await client.get(url)
```

**Effekt:** Connection-overhead vid varje anrop. Under `collect_tables()` kan detta innebära ~100+ nya TCP-anslutningar.
**Fix:** Använd en persistent `httpx.AsyncClient` som skapas i `__init__` eller som context manager.

### KQ-3: Stora fil-längder (P3 — Låg)

| Fil | Rader | Kommentar |
|-----|-------|-----------|
| `statistics_agent.py` | 1151 | Verktygsdefinitioner utgör ~800 rader |
| `scb_service.py` | 693 | Acceptabel men kan delas |
| `bigtool_store.py` | 2000+ | Flera domäner, ej bara SCB |

**Fix:** Flytta `SCB_TOOL_DEFINITIONS` till en separat fil, t.ex. `scb_tool_definitions.py`.

### KQ-4: Ingen typ-annotation för `_scb_tool`-returtyp (P3 — Låg)

**Problem:** Den dynamiska tool-funktionen `_scb_tool` saknar explicit returtyp i signaturen.
**Effekt:** Svårare att validera.
**Fix:** Lägg till `-> str` på `_scb_tool`.

### KQ-5: `ScbQueryResult` oanvänd (P3 — Låg) — FIXAD

**Problem:** `ScbQueryResult` definieras i `scb_service.py:37` men refereras aldrig i någon annan fil.
**Effekt:** Död kod.
**Fix:** Antingen använda den i `query_table()`-returen eller ta bort den.

### KQ-6: Privat metod `_serialize_external_document` (P2 — Medel) — FIXAD

**Problem:** `statistics_agent.py:1034` anropar `connector_service._serialize_external_document()`:
```python
serialized = connector_service._serialize_external_document(document, score=1.0)
```
**Effekt:** Brott mot encapsulation; privat API kan ändras utan varning.
**Fix:** Exponera som publik metod eller skapa en dedikerad serialiseringsmetod.

### KQ-7: Monkey-patching av BigtoolToolNode (P2 — Medel)

**Problem:** `create_statistics_agent()` monkey-patchar `BigtoolToolNode`:
```python
if not hasattr(BigtoolToolNode, "inject_tool_args") and hasattr(
    BigtoolToolNode, "_inject_tool_args"
):
    BigtoolToolNode.inject_tool_args = _inject_tool_args_compat
```
**Effekt:** Fragil koppling till specifik version av langgraph_bigtool.
**Fix:** Versionsuppgradering av `langgraph_bigtool` eller PR till upstream.

---

## 12. Buggar

### BUG-1: Race condition i cache (P1 — Hög) — FIXAD

**Problem:** `_node_cache` och `_metadata_cache` är vanliga dict:ar som inte är trådsäkra vid concurrent access. Med `asyncio.gather()` kan flera coroutines läsa/skriva samma cache-key simultant.

**Plats:** `scb_service.py:238-239`

**Effekt:** I sällsynta fall kan cache-data bli korrupt eller gå förlorad.

**Fix:**
```python
# Alternativ 1: asyncio.Lock per cache
self._cache_lock = asyncio.Lock()

async def list_nodes(self, path: str) -> list[dict]:
    url = self._build_url(path, trailing=True)
    async with self._cache_lock:
        if url in self._node_cache:
            return list(self._node_cache[url])
    data = await self._get_json(url)
    async with self._cache_lock:
        self._node_cache[url] = data
    return list(data)
```

**Sannolikhet:** Låg (single event loop) men bör åtgärdas för korrekthet.

### BUG-2: `collect_tables` BFS utan djupbegränsning per gren (P2 — Medel)

**Problem:** `queue.pop(0)` gör BFS, men `max_depth=4` kontrolleras bara vid tillägg av barn. Om SCB:s trädstruktur har breda noder vid djup 1, kan alla 140 noder förbrukas utan att hitta tabeller.

**Plats:** `scb_service.py:304-353`

**Effekt:** Vissa smala ämnesområden (t.ex. `HS/` med bara `HS0301`) hittas inte om bredare grenar konsumerar alla noder.

**Fix:** Prioritera djupet-först för redan poängsatta grenar, eller öka `max_nodes`.

### BUG-3: `_match_values_by_text` false positives (P2 — Medel) — FIXAD

**Problem:** Substrings kan matcha fel:
```python
if normalized in query_norm:  # "malmo" matchar "malmö kommun" men också "malmöanpassning"
```

**Plats:** `scb_service.py:213`

**Effekt:** Felaktiga regionval vid delsträngsmatchning.

**Fix:** Använd ordgräns-matchning eller tokenbaserad jämförelse.

### BUG-4: Saknar timeout-hantering i `collect_tables` (P2 — Medel) — FIXAD

**Problem:** Enskilda `list_nodes()`-anrop har httpx-timeout (25s), men den totala tiden för `collect_tables()` har ingen övre gräns. Med 140 noder kan totaltiden bli ~140 * 25s = 58 minuter.

**Plats:** `scb_service.py:287-353`

**Effekt:** Extremt lång väntetid vid nätverksproblem.

**Fix:** Lägg till en total timeout-parameter och `asyncio.wait_for()`.

### BUG-5: `_selection_cell_count` returnerar 0 för tom lista (P3 — Låg)

**Problem:** `prod([])` returnerar 1 (matematisk konvention), men koden returnerar 0 via `if lengths else 0`. Detta är korrekt men inkonsistent med `math.prod`:

```python
def _selection_cell_count(self, selections):
    lengths = [max(len(sel.get("values") or []), 1) for sel in selections]
    return prod(lengths) if lengths else 0
```

**Plats:** `scb_service.py:607-609`

**Effekt:** Ingen praktisk bugg, men förvirrande logik.

### BUG-7: `_normalize_v2_metadata` hanterade inte JSON-stat2 (P1 — Kritisk) — FIXAD

**Problem:** v2 `/tables/{id}/metadata`-endpointen returnerar JSON-stat2-format med `id` (dimensionslista) och `dimension` (dict med `category.index`/`category.label`), men `_normalize_v2_metadata` letade efter `data.get("variables")` som inte finns i JSON-stat2. Resulterade i tom variabellista → inga payloads → "No valid SCB query payloads could be built." på **alla** frågor.

**Fix:** Uppdaterade `_normalize_v2_metadata` att först kontrollera JSON-stat2-format (`id` + `dimension` keys), extrahera variabler från `dimension`-objektet med korrekt ordning via `category.index`, och konvertera till v1-kompatibelt format.

**Plats:** `scb_service.py:_normalize_v2_metadata`

### BUG-6: Encoding-problem i API-URL (P3 — Låg) — FIXAD

**Problem:** SCB v1 API-URL:er kan innehålla svenska tecken i tabellnamn. `_build_url()` gör ingen URL-encoding:

```python
def _build_url(self, path: str, *, trailing: bool) -> str:
    cleaned = (path or "").lstrip("/")
    url = f"{self.base_url}{cleaned}"
```

**Effekt:** Potentiella `httpx.InvalidURL`-fel vid ovanliga tabellnamn.

**Fix:** Använd `urllib.parse.quote()` för path-komponenter.

---

## 13. Optimeringar

### OPT-1: Persistent HTTP-klient (P1 — Hög vinst) — IMPLEMENTERAD

**Nuvarande:** Ny `httpx.AsyncClient` per HTTP-anrop.
**Förbättring:** Återanvänd klient med connection pooling.

```python
class ScbService:
    def __init__(self, base_url=SCB_BASE_URL, timeout=25.0):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self):
        await self._client.aclose()
```

**Estimerad vinst:** ~40-60% latensreduktion för `collect_tables()`.

### OPT-2: Parallell trädnavigering (P1 — Hög vinst)

**Nuvarande:** BFS med sekventiella `list_nodes()`-anrop.
**Förbättring:** Batcha `list_nodes()` med `asyncio.gather()`:

```python
async def collect_tables_parallel(self, base_path, query, *, max_concurrent=5):
    semaphore = asyncio.Semaphore(max_concurrent)
    async def _fetch_bounded(path):
        async with semaphore:
            return await self.list_nodes(path)
    # Expandera nivå för nivå parallellt
```

**Estimerad vinst:** ~3-5x snabbare navigering.

### OPT-3: v2 Table Search ersätter trädnavigering (P1 — Hög vinst) — IMPLEMENTERAD

**Nuvarande:** 50-140 HTTP-anrop för att navigera SCB:s träd.
**Förbättring:** 1 anrop till `GET /tables?query=...`.

**Estimerad vinst:** ~50-100x färre HTTP-anrop.

### OPT-4: Cache-TTL (P2 — Medel vinst)

**Nuvarande:** Cache lagras under ScbService-objektets livstid (per request).
**Förbättring:** Implementera TTL-cache (t.ex. 1 timme) med lru_cache eller cachetools.

```python
from cachetools import TTLCache

class ScbService:
    _shared_node_cache = TTLCache(maxsize=1000, ttl=3600)
```

**Estimerad vinst:** Snabbare svarstider vid upprepade frågor.

### OPT-5: Reduce payload-storlek med JSON-stat2 compact (P3 — Låg vinst)

**Nuvarande:** Hela json-stat2-svaret returneras.
**Förbättring:** Extrahera bara nödvändig data (dimensions, values) innan lagring.

### OPT-6: Parallell batch-exekvering redan implementerad (Bekräftat OK)

`statistics_agent.py:973` använder redan `asyncio.gather()` för parallella batch-anrop:
```python
raw_results = await asyncio.gather(
    *(scb_service.query_table(table.path, p) for p in payloads)
)
```

### OPT-7: Verktygsval-cache (P3 — Låg vinst)

**Nuvarande:** `retrieve_scb_tools()` itererar alla 40 verktyg vid varje anrop.
**Förbättring:** Pre-beräkna normaliserade keywords och cache:a.

---

## 14. Kompletthetsanalys

### SCB Ämnesområden — Täckningsmatris

| SCB Kod | Ämnesområde | Bred kategori | Specifika verktyg | Status |
|---------|-------------|---------------|-------------------|--------|
| AA | Ämnesövergripande | `scb_amnesovergripande` | — | Täckt |
| AM | Arbetsmarknad | `scb_arbetsmarknad` | `_arbetsloshet`, `_sysselsattning`, `_lon` | Täckt |
| BE | Befolkning | `scb_befolkning` | `_folkmangd`, `_forandringar`, `_fodda` | Täckt |
| BO | Boende, byggande | `scb_boende_byggande` | `_bygglov`, `_nybyggnation`, `_bestand` | Täckt |
| EN | Energi | `scb_energi` | — | Delvis (inga specifika) |
| FM | Finansmarknad | `scb_finansmarknad` | — | Delvis |
| HA | Handel | `scb_handel` | — | Delvis |
| HE | Hushållens ekonomi | `scb_hushall` | — | Delvis |
| HS | Hälso- och sjukvård | `scb_halsa_sjukvard` | — | Delvis (bara 1 tabellkod) |
| JO | Jord- och skogsbruk | `scb_jordbruk` | — | Delvis |
| KU | Kultur och fritid | `scb_kultur` | — | Delvis |
| LE | Levnadsförhållanden | `scb_levnadsforhallanden` | — | Delvis |
| ME | Demokrati | `scb_demokrati` | — | Delvis |
| MI | Miljö | `scb_miljo` | `_utslapp`, `_energi` | Täckt |
| NR | Nationalräkenskaper | `scb_nationalrakenskaper` | — | Delvis |
| NV | Näringsverksamhet | `scb_naringsverksamhet` | `_foretag`, `_omsattning`, `_nyforetagande` | Täckt |
| OE | Offentlig ekonomi | `scb_offentlig_ekonomi` | — | Delvis |
| PR | Priser och konsumtion | `scb_priser_konsumtion` | `_kpi`, `_inflation` | Täckt |
| SO | Socialtjänst | `scb_socialtjanst` | — | Delvis (bara 1 tabellkod) |
| TK | Transporter | `scb_transporter` | `_person`, `_gods` | Täckt |
| UF | Utbildning och forskning | `scb_utbildning` | `_gymnasie`, `_hogskola`, `_forskning` | Täckt |

### Saknade områden eller luckor

1. **Dödsfallsstatistik** — `BE/BE0101/BE0101I/` saknar dedikerat verktyg (täcks delvis av `scb_befolkning`)
2. **Invandring/utvandring** — Specifika verktyg saknas (täcks av `scb_befolkning_forandringar`)
3. **Lönestruktur (SLS)** — `AM/AM0110/` saknas som specifikt verktyg
4. **Detaljhandel** — `HA/HA0103/` (omsättningsstatistik) saknar specifikt verktyg
5. **BNP per kvartal** — `NR/NR0103/` saknar specifikt verktyg trots hög efterfrågan

### Fan-Out täckning

Av 42 verktyg ingår bara 6 i domain fan-out. Många specifika underverktyg (t.ex. `scb_priser_kpi`) triggas inte vid fan-out trots att de är mer precisa.

**Rekommendation:** Utöka fan-out med specifika verktyg:
```python
FanOutCategory(name="kpi", tool_ids=("scb_priser_kpi",), priority=2),
```

---

## 15. Testsvit

**154 tester** fördelade på 3 testfiler:

### `tests/test_scb_llm_tools.py` — 46 tester (v5.0)

| Kategori | Antal | Tester |
|----------|-------|--------|
| _format_table_inspection | 8 | basic, variable_type, truncation, time_hint, empty, gender, measure, eliminable |
| _find_closest_variables | 2 | exact_substring, no_match_returns_all |
| _find_closest_values | 3 | exact_match, normalized, no_match_sample |
| _fuzzy_match_values | 4 | normalized_exact, code_exact, word_boundary, no_match |
| v2-uttryck | 6 | TOP, BOTTOM, FROM/TO/RANGE, wildcards, not_expressions, size_estimation |
| scb_search | 3 | create_tool, returns_results, empty_query |
| scb_browse | 2 | create_tool, browse_top_level |
| scb_inspect | 4 | create_tool, inspect_table, shows_eliminable, empty_table_id |
| scb_validate | 6 | create_tool, valid+auto_complete, v2_passthrough, invalid_code, region_fuzzy, gender_alias |
| scb_fetch | 4 | create_tool, basic_markdown, auto_complete, empty_selection |
| scb_preview | 1 | create_tool |
| scb_codelist | 3 | create_tool, fetch_codelist, empty |

### `tests/test_scb_service.py` — 72 tester

| Kategori | Antal | Tester |
|----------|-------|--------|
| Text-helpers | 3 | normalize_text, tokenize, score_text |
| SCB-helpers | 11 | extract_years, is_time/region/gender/age, etc. |
| ScbService integration | 7 | find_best_table (3), build_query (2), cell_count (2) |
| v2-specifika | 12 | v2_detection, convert_payload, normalize_metadata, etc. |
| TTL-cache | 2 | ttl_cache_type, ttl_cache_custom_ttl |
| Codelist | 3 | v1_returns_error, v2_success, v2_http_error |
| Output format | 2 | output_formats_constant, query_table_v2_output_format |
| Parallell BFS | 2 | parallel_fetch, priority_ordering |
| Verktygsdef | 7 | count (47), unique_ids, new_tools_present, keyword_index, normalized_names |
| Scoring | 5 | score_tool, retrieve_tools (4) |
| Domain fan-out | 3 | new_categories, new_tool_ids, select_handel |
| Diverse | 4+ | split_batches, collect_tables_timeout, cache_lock, get_json_persistent |

### `tests/test_scb_regions.py` — 36 tester

| Kategori | Antal | Tester |
|----------|-------|--------|
| Registry integrity | 7 | not_empty, one_country, 21_counties, 290_municipalities, unique_codes, etc. |
| normalize_diacritik | 9 | swedish chars, already_ascii, case_insensitive, etc. |
| find_region_by_code | 5 | municipality, county, country, not_found, strips_whitespace |
| find_region_by_name | 3 | exact, case_insensitive, not_found |
| find_region_fuzzy | 10 | exact, diacritik, jonkoping, alias (sthlm/gbg/riket/skane), etc. |
| resolve_region_codes | 5 | basic, with_table_values, not_in_table, fuzzy_in_table, empty |
| format_region_for_llm | 3 | municipality, county, country |

### Testtäckning

| Område | Status |
|--------|--------|
| 7 LLM-verktyg (v5.0) | Fullständig (46 tester) |
| Helper-funktioner | Fullständig |
| ScbService navigering | Fullständig (BFS, timeout, parallell) |
| ScbService query-byggare | Fullständig (payloads, batching, cell count) |
| v2 API-integration | Fullständig (metadata, search, query, codelist) |
| Regionregister | Fullständig (36 tester) |
| Verktygsval/scoring | Fullständig |
| Domain fan-out | Fullständig |

---

## 16. Evalueringsdata

### `eval/api/scb/be/scb-be_20260212_v1.json`

Testar verktygsval för befolkningskategorin:
- 3+ testfall med frågor som "Folkmängd i Sverige 2023"
- Verifierar att rätt SCB-verktyg väljs

### `eval/api/scb/all_categories/scb-provider_20260214_v1.json`

Bredare eval över alla kategorier:
- Testar routing till rätt verktyg per ämnesområde
- Inkluderar svårighetsgrader (lätt, medel)
- Verifierar intent → route → agent → tool-kedjan

---

## 17. Konfiguration och Environment

### Konfigurerbara parametrar

| Parameter | Plats | Default | Beskrivning |
|-----------|-------|---------|-------------|
| `SCB_BASE_URL` | `scb_service.py:12` | `api.scb.se/OV0104/v1/...` | API bas-URL |
| `SCB_MAX_CELLS` | `scb_service.py:13` | 150 000 | Max celler per fråga |
| `timeout` | `ScbService.__init__` | 25.0s | HTTP-timeout |
| `max_tables` | `collect_tables()` | 80 | Max tabeller att samla |
| `max_depth` | `collect_tables()` | 4 | Max träddjup |
| `max_nodes` | `collect_tables()` | 140 | Max noder att besöka |
| `max_children` | `collect_tables()` | 8 | Max barn per nod |
| `metadata_limit` | `find_best_table_candidates()` | 10 | Max tabeller för metadata-hämtning |
| `candidate_limit` | `find_best_table_candidates()` | 5 | Max alternativa kandidater |
| `max_values_per_variable` | `build_query_payloads()` | 6 | Max värden per variabel |
| `max_batches` | `build_query_payloads()` | 8 | Max parallella batchar |
| `max_parallel` (fan-out) | `domain_fan_out.py` | 3 | Max parallella fan-out |
| `timeout_seconds` (fan-out) | `domain_fan_out.py` | 30.0 | Fan-out timeout |

### Miljövariabler (implementerade)

| Variabel | Default | Beskrivning |
|----------|---------|-------------|
| `SCB_API_VERSION` | `v2` | API-version (`v2` eller `v1`) |
| `SCB_BASE_URL` | `https://statistikdatabasen.scb.se/api/v2/` | v2 bas-URL |
| `SCB_BASE_URL_V1` | `https://api.scb.se/OV0104/v1/doris/sv/ssd/` | v1 fallback-URL |
| `SCB_MAX_CELLS` | `150000` | Max celler per API-anrop |
| `SCB_TIMEOUT` | `25.0` | HTTP-timeout i sekunder |
| `SCB_CACHE_TTL` | `3600` | Cache-livstid i sekunder (TTLCache) |

---

## 18. 7-verktygspipeline (v5.0)

> **Implementerad:** 2026-03-10
> **Inspirerad av:** [isakskogstad/SCB-MCP](https://github.com/isakskogstad/SCB-MCP)

### Bakgrund — Varför 7 verktyg?

v4.0 hade 3 LLM-verktyg (`scb_search_and_inspect`, `scb_validate_selection`, `scb_fetch_validated`). Problemen:

1. **Oläsbar data** — Rå JSON-stat2 med platt value-array returnerades direkt
2. **Saknade variabler** → krascher (SCB kräver alla dimensioner)
3. **Ingen trädnavigering** — bara textsökning
4. **Ingen preview** — omöjligt att snabbt kontrollera data
5. **Inga kodlistor** — svårt att använda läns/kommunfilter

### Arkitektur

```
┌─ DISCOVERY ─────────────────────────────────────────────────┐
│  scb_search         Fulltextsökning bland tabeller          │
│  scb_browse         Navigera ämnesträd steg för steg (v1)   │
├─ INSPEKTION ────────────────────────────────────────────────┤
│  scb_inspect        Full metadata + defaults + hints        │
│  scb_codelist       Hämta kodlista (län, kommuner, etc.)    │
├─ DATA ──────────────────────────────────────────────────────┤
│  scb_preview        Auto-begränsad förhandsvisning (~20 rader) │
│  scb_validate       Dry-run validering utan datahämtning    │
│  scb_fetch          Hämta data → dekodad markdown-tabell    │
└─────────────────────────────────────────────────────────────┘
```

### Arbetsflöden

**Typiskt (3 anrop):** `scb_search` → `scb_inspect` → `scb_fetch`
**Explorativt (4 anrop):** `scb_browse` → `scb_browse` → `scb_inspect` → `scb_fetch`
**Osäker fråga (4 anrop):** `scb_search` → `scb_inspect` → `scb_preview` → `scb_fetch`

De 47 domänverktygen fungerar fortfarande som alternativa ingångar — de söker inom sitt domänområde och returnerar tabell-inspektioner som LLM:en sedan följer upp med `scb_fetch`.

### Verktygs-API

#### `scb_search(query, max_results?, past_days?)`

Fulltextsökning via v2 `GET /tables?query=`. Returnerar kompakt lista:

```json
{
  "results": [
    {"id": "TAB638", "title": "Folkmängd efter region, kön och år", "period": "1968-2024", "variables": 4}
  ],
  "total": 23
}
```

#### `scb_browse(path?)`

Navigerar SCB:s ämnesträd via v1 `list_nodes()`. Tom path → toppnivå.

```json
{
  "path": "BE",
  "items": [
    {"id": "BE0101", "type": "folder", "text": "Befolkningsstatistik"},
    {"id": "TAB638", "type": "table", "text": "Folkmängd..."}
  ]
}
```

#### `scb_inspect(table_id)`

Full metadata med elimination-info, defaults, hints och kodlistor:

```json
{
  "table_id": "TAB638",
  "title": "Folkmängd efter region, kön och år",
  "variables": [
    {
      "code": "Region",
      "label": "Region",
      "type": "region",
      "total_values": 312,
      "eliminable": true,
      "default_value": "00",
      "codelists": ["vs_RegionLän", "vs_RegionKommun"],
      "sample_values": [{"code": "00", "label": "Riket"}, ...],
      "usage_examples": {"single": ["0180"], "all": ["*"], "codelist": "vs_RegionLän"}
    }
  ],
  "default_selection": {"Region": ["00"], "Tid": ["2024"]}
}
```

#### `scb_codelist(codelist_id)`

Hämtar alla värden i en kodlista:

```json
{
  "id": "vs_RegionLän",
  "label": "Län",
  "values": [
    {"code": "01", "label": "Stockholms län"},
    {"code": "03", "label": "Uppsala län"}
  ],
  "total_values": 21
}
```

#### `scb_preview(table_id, selection?)`

Auto-begränsad förhandsvisning. Tid → `TOP(1)`, stora dimensioner → första 2 värden:

```json
{
  "preview": true,
  "data_table": "| Region | Kön | År | Folkmängd |\n|---|---|---|---:|\n| Riket | män | 2024 | 5 321 437 |",
  "note": "Begränsad preview. Använd scb_fetch för full data."
}
```

#### `scb_validate(table_id, selection)`

Torrkörning med auto-complete för saknade variabler:

```json
{
  "status": "valid",
  "selection": {"Region": ["0180"], "Kon": ["1+2"], "ContentsCode": ["BE0101N1"], "Tid": ["TOP(3)"]},
  "auto_completed": ["Kon: auto → '1+2' (elimination default)", "ContentsCode: auto → ['BE0101N1'] (defaultselection)"],
  "estimated_cells": 3,
  "warnings": []
}
```

#### `scb_fetch(table_id, selection, codelist?, max_rows?)`

Full datahämtning med auto-complete + JSON-stat2-dekodning till markdown:

```json
{
  "table_id": "TAB638",
  "title": "Folkmängd efter region, kön och år",
  "source": "SCB",
  "unit": "antal",
  "data_table": "| Region | Kön | År | Folkmängd |\n|---|---|---|---:|\n| Stockholm | totalt | 2024 | 984 748 |\n| Stockholm | totalt | 2023 | 978 770 |",
  "row_count": 3,
  "auto_completed": ["Kon: auto → '1+2' (elimination default)"],
  "selection_used": {"Region": ["0180"], "Tid": ["TOP(3)"], ...}
}
```

### Nyckelförbättringar

| Aspekt | v4.0 (3 verktyg) | v5.0 (7 verktyg) |
|--------|---|---|
| Dataformat | Rå JSON-stat2 (oläsbar) | Markdown-tabell med labels |
| Saknade variabler | → kraschar | → auto-complete med defaults |
| Navigation | Bara textsökning | Trädnavigering + textsökning |
| Preview | Nej | Auto-begränsad (~20 rader) |
| Kodlistor | Ej integrerade | scb_codelist + codelist i fetch |
| v2-uttryck | Ej stödda | TOP, FROM, RANGE, *, wildcards |
| Validering | Strikt (fel vid saknade) | Auto-complete + förslag |
| Precision | Medel | Hög |

### Filer

| Fil | Syfte | Rader |
|-----|-------|-------|
| `tools/scb_llm_tools.py` | 7 LLM-verktyg + hjälpfunktioner | ~1230 |
| `services/scb_service.py` | Kärntjänst med dekoder + auto-complete | ~1200 |
| `services/scb_regions.py` | Regionregister (290+21+Riket) + fuzzy-matchning | ~450 |
| `statistics_prompts.py` | Systemprompt med 7-verktygsflöde | ~100 |
| `tools/registry.py` | 7 ToolDefinitions registrerade | ~500 |
| `bigtool_store.py` | 7 verktyg i TOOL_NAMESPACE_OVERRIDES + TOOL_KEYWORDS | ~2500 |

### v2-uttryck

LLM:en kan använda PxWeb v2:s filteruttryck istället för att lista specifika koder:

| Uttryck | Betydelse | Exempel |
|---------|-----------|---------|
| `TOP(n)` | Senaste n perioder | `{"Tid": ["TOP(5)"]}` |
| `BOTTOM(n)` | Äldsta n perioder | `{"Tid": ["BOTTOM(3)"]}` |
| `FROM(x)` | Från och med x | `{"Tid": ["FROM(2020)"]}` |
| `TO(x)` | Till och med x | `{"Tid": ["TO(2020)"]}` |
| `RANGE(x,y)` | Inklusivt intervall | `{"Tid": ["RANGE(2018,2024)"]}` |
| `*` | Alla värden | `{"Region": ["*"]}` |
| Prefix-wildcard | Alla med prefix | `{"Region": ["01*"]}` |

---

## 19. Implementeringslogg

Alla uppgifter från den ursprungliga analysen (P1, P2, P3) är nu implementerade.

### P1 — Kritiskt (v2-migration + prestanda) — ALLA KLARA

| # | Uppgift | Status | Filer |
|---|---------|--------|-------|
| 1 | Migrera till PxWebApi v2 bas-URL | KLAR | `scb_service.py` |
| 2 | Implementera `/tables?query=` sökning | KLAR | `scb_service.py` |
| 3 | Persistent httpx.AsyncClient | KLAR | `scb_service.py` |
| 4 | Uppdatera query-payload till v2-format | KLAR | `scb_service.py` |
| 5 | Ny metadata-hämtning via `/tables/{id}/metadata` | KLAR | `scb_service.py` |

### P2 — Viktigt (kodkvalitet + buggar) — ALLA KLARA

| # | Uppgift | Status | Filer |
|---|---------|--------|-------|
| 6 | Centralisera `_normalize_text()` (KQ-1) | KLAR | `app/utils/text.py` |
| 7 | Exponera `serialize_external_document` (KQ-6) | KLAR | `connector_service.py` + 7 anropare |
| 8 | Cache-lås (asyncio.Lock) (BUG-1) | KLAR | `scb_service.py` |
| 9 | Total timeout i `collect_tables` (BUG-4) | KLAR | `scb_service.py` |
| 10 | Ta bort oanvänd `ScbQueryResult` (KQ-5) | KLAR | `scb_service.py` |

### P3 — Önskvärt (komplettering + framtid) — ALLA KLARA

| # | Uppgift | Status | Filer |
|---|---------|--------|-------|
| 11 | Utöka fan-out med specifika verktyg | KLAR | `domain_fan_out.py` |
| 12 | TTL-cache (cachetools) (OPT-4) | KLAR | `scb_service.py` |
| 13 | Miljövariabler för SCB-konfiguration | KLAR | `config/__init__.py` |
| 14 | 61 tester (BFS, codelist, output format, scoring) | KLAR | `tests/test_scb_service.py` |
| 15 | Stöd för CSV/parquet output-format (v2) | KLAR | `scb_service.py` |
| 16 | Kodlistintegration (`/codelists/{id}`) | KLAR | `scb_service.py` |
| 17 | 5 nya specifika verktyg (dödsfall, invandring, lönestruktur, detaljhandel, BNP kvartal) | KLAR | `scb_tool_definitions.py` |

### Ytterligare åtgärder (utöver ursprunglig plan)

| # | Uppgift | Status | Filer |
|---|---------|--------|-------|
| 18 | Extrahera SCB_TOOL_DEFINITIONS till separat fil (KQ-3) | KLAR | `scb_tool_definitions.py` |
| 19 | Return type annotation `-> str` (KQ-4) | KLAR | `statistics_agent.py` |
| 20 | Pre-compute normalized keywords (OPT-7) | KLAR | `scb_tool_definitions.py` |
| 21 | Parallell trädnavigering med semaphore (OPT-2) | KLAR | `scb_service.py` |
| 22 | Prioriterad BFS (BUG-2) | KLAR | `scb_service.py` |
| 23 | Fix `_selection_cell_count` edge case (BUG-5) | KLAR | `scb_service.py` |
| 24 | URL-encoding för svenska tecken (BUG-6) | KLAR | `scb_service.py` |
| 25 | Ordgräns-matchning i `_match_values_by_text` (BUG-3) | KLAR | `scb_service.py` |
| 26 | Fan-out handel-kategori med trigger-keywords | KLAR | `domain_fan_out.py` |

---

## 20. Historik: Hybrid LLM-driven Variabelförståelse (v4.0)

> **Ersatt av:** v5.0 (7-verktygspipeline, se sektion 18)
> **Implementerad:** 2026-03-10
> **Inspirerad av:** [isakskogstad/SCB-MCP](https://github.com/isakskogstad/SCB-MCP)

### Bakgrund — Varför hybrid?

Den tidigare implementationen (v3.0) hade ett fundamentalt problem: **LLM:en var blind**. All variabelhantering skedde via heuristik (`_build_selections()`) utan att LLM:en någonsin såg SCB:s variabelstruktur. Resultatet:

- Fel tabeller valdes (heuristisk scoring räckte inte)
- Fel variabelvärden (regex-matchning av t.ex. "Stockholm" mot regionkoder)
- Ingen möjlighet till korrigering (inget feedback-loop)
- Saknade kommuner (gazetteeren hade ~70 av 290)

**SCB-MCP-projektet** visade att LLM:er som *ser* variabelstrukturen och *resonerar* om den ger dramatiskt bättre precision, även om det kostar fler LLM-anrop.

### Hybrid-arkitekturen

v4.0 kombinerar det bästa från båda systemen:

| Från OneSeek (v3.0) | Från SCB-MCP | v4.0 | v5.0 |
|---|---|---|---|
| 47 domänverktyg | LLM ser variabelstruktur | 3 LLM-verktyg | **7 LLM-verktyg** |
| Dual v1+v2 sökning | Dry-run validering | Regionregister (290+21) | **JSON-stat2-dekoder** |
| TTL-cache (1h) | Fuzzy matchning | Diakritiknormalisering | **Auto-complete** |
| Connection pooling | Strukturerade felförslag | QUL-koppling | **Trädnavigering** |
| Batching (>150k celler) | NL → kodöversättning | Retry-loop | **Preview + v2-uttryck** |

### v4.0 dataflöde (ersatt av v5.0 — se sektion 18)

```
┌──────────────────────────────────────────────────────────┐
│  STEG 1: scb_search_and_inspect  (→ ersatt av scb_search + scb_inspect)
│                                                          │
│  Bigtool routing → domänverktyg → dual v1+v2 sökning     │
│  Returnerar: Top 5 tabeller MED variabelstruktur         │
│                                                          │
│  ★ LLM:en SER kandidaterna och VÄLJER tabell             │
│    baserat på vilka variabler som matchar frågan          │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│  STEG 2: scb_validate_selection  (→ ersatt av scb_validate)
│                                                          │
│  LLM:en bygger selection baserat på variabelförståelse   │
│  Validering utan datahämtning:                           │
│  - Alla dimensioner täckta?                              │
│  - Alla värdekoder giltiga?                              │
│  - Fuzzy regionmatchning ("Goteborg" → "1480")           │
│  - "Did you mean?"-förslag vid near-miss                 │
│                                                          │
│  ★ Vid fel → LLM:en KORRIGERAR (max 2 retries)          │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│  STEG 3: scb_fetch_validated  (→ ersatt av scb_fetch)    │
│                                                          │
│  Validerad selection → query_table()                     │
│  Automatisk batching om >150k celler                     │
│  Returnerar strukturerad data + källa                    │
└──────────────────────────────────────────────────────────┘
```

### Filer (v4.0 → uppgraderade i v5.0)

| Fil | Syfte | Status i v5.0 |
|-----|-------|---------------|
| `app/services/scb_regions.py` | Regionregister (290+21+Riket) | Behållen |
| `app/agents/new_chat/tools/scb_llm_tools.py` | LLM-verktyg | Uppgraderad: 3 → 7 verktyg |
| `statistics_prompts.py` | Systemprompt | Uppgraderad: 7-verktygsflöde |
| `tools/registry.py` | ToolDefinitions | Uppgraderad: 3 → 7 registreringar |
| `app/services/scb_service.py` | Kärntjänst | Utökad: dekoder, auto-complete, defaultselection |

### Verktygs-API (v4.0 — BORTTAGEN, se sektion 18 för v5.0 API)

#### `scb_search_and_inspect(query, base_path?, table_id?)` — ERSATT av `scb_search` + `scb_inspect`

Sökte SCB-tabeller och returnerade variabelstruktur:

```json
{
  "tables": [{
    "table_id": "TAB1234",
    "title": "Folkmängd efter region, ålder och kön",
    "variables": [
      {
        "code": "Region",
        "label": "Region",
        "type": "region",
        "total_values": 312,
        "values": [{"code": "00", "label": "Riket"}, {"code": "01", "label": "Stockholms län"}, ...],
        "hint": "Use scb_validate_selection to resolve region names to codes. 00=Riket."
      },
      {
        "code": "Tid",
        "label": "År",
        "type": "time",
        "total_values": 56,
        "values": [{"code": "1968", "label": "1968"}, ...],
        "hint": "Latest: 2024, Earliest: 1968"
      }
    ],
    "selection_rules": {
      "all_variables_required": true,
      "note": "SCB requires ALL variables to have at least one value selected."
    }
  }]
}
```

#### `scb_validate_selection(table_id, selection)` — ERSATT av `scb_validate`

Validerade utan datahämtning:

```json
// Input
{"table_id": "TAB1234", "selection": {"Region": ["Göteborg"], "Tid": ["2023"], "Kon": ["1"]}}

// Output (vid framgång)
{"status": "valid", "selection": {"Region": ["1480"], "Tid": ["2023"], "Kon": ["1"]}, "estimated_cells": 1, "warnings": ["Resolved region 'Göteborg' → ['1480'] (Göteborg)"]}

// Output (vid fel)
{"status": "invalid", "errors": [{"variable": "ContentsCode", "error": "Missing from selection — SCB requires ALL variables.", "suggestion": "Suggested: ['BE0101N1']"}]}
```

#### `scb_fetch_validated(table_id, selection)` — ERSATT av `scb_fetch`

Hämtade data med validerad selection. Hanterade batching automatiskt. **Returnerade rå JSON-stat2 — detta var det största problemet.** v5.0:s `scb_fetch` returnerar istället läsbar markdown-tabell via `decode_jsonstat2_to_markdown()`.

### Regionregistret (`scb_regions.py`)

Komplett register med alla svenska administrativa regioner:

| Typ | Antal | Kodformat | Exempel |
|-----|-------|-----------|---------|
| Land | 1 | 2-siffrig | `00` = Riket |
| Län | 21 | 2-siffrig | `01` = Stockholms län |
| Kommun | 290 | 4-siffrig | `0180` = Stockholm |

**Diakritiknormalisering:**

```python
normalize_diacritik("Göteborg")   # → "goteborg"
normalize_diacritik("Jönköping")  # → "jonkoping"
normalize_diacritik("Malmö")      # → "malmo"
```

**Fuzzy-matchning:**

```python
find_region_fuzzy("Goteborg")     # → [ScbRegion("1480", "Göteborg", "municipality")]
find_region_fuzzy("sthlm")        # → [ScbRegion("0180", "Stockholm", "municipality")]
find_region_fuzzy("skane")        # → [ScbRegion("12", "Skåne län", "county")]
```

### QUL-koppling

QUL:s entitetsextraktion (`nexus/routing/qul.py`) utökad med:
1. **Fullständigt regionregister** — alla 290+21 regioner (var ~70)
2. **Diakritiknormalisering** — "goteborg", "jonkoping" fungerar nu
3. **Bakåtkompatibel** — befintlig gazetteer+alias bibehållen som snabb sökväg

### Jämförelse: v3.0 → v4.0 → v5.0

| Aspekt | v3.0 (heuristik) | v4.0 (3 verktyg) | v5.0 (7 verktyg) |
|--------|---|---|---|
| Tabellval | `_score_table_metadata()` | LLM ser variabler | LLM ser + browse/search |
| Variabelval | `_build_selections()` regex | LLM bygger manuellt | **Auto-complete** + LLM |
| Dataformat | Rå JSON-stat2 | Rå JSON-stat2 | **Markdown-tabell** |
| Navigation | Bara trädnavigering | Bara textsökning | **Träd + textsökning** |
| Regionmatchning | ~70 hårdkodade | 290+21 + fuzzy | 290+21 + fuzzy + diacritik |
| Validering | Ingen | Dry-run, strikt | **Auto-complete + förslag** |
| Preview | Ingen | Ingen | **Auto-begränsad preview** |
| Kodlistor | Inga | Inga | **Integrerade** |
| v2-uttryck | Inga | Inga | **TOP, FROM, RANGE, \*** |
| LLM-anrop/fråga | 1-2 | 3-5 | 3-5 |
| Precision | Låg | Medel | **Hög** |

### v5.0 Implementeringslogg

| # | Uppgift | Status | Filer |
|---|---------|--------|-------|
| 27 | Bevara rik metadata i `_normalize_v2_metadata` (elimination, unit, refperiod) | KLAR | `scb_service.py` |
| 28 | `decode_jsonstat2_to_markdown()` — JSON-stat2 → markdown-tabell | KLAR | `scb_service.py` |
| 29 | `get_default_selection()` via v2 endpoint | KLAR | `scb_service.py` |
| 30 | `auto_complete_selection()` med elimination-defaults | KLAR | `scb_service.py` |
| 31 | 7 nya LLM-verktyg (search, browse, inspect, codelist, preview, validate, fetch) | KLAR | `scb_llm_tools.py` |
| 32 | Systemprompt med 7-verktygsflöde | KLAR | `statistics_prompts.py` |
| 33 | 7 ToolDefinitions i registry + bigtool_store | KLAR | `registry.py`, `bigtool_store.py` |
| 34 | Uppdatera domänverktygens references (scb_validate, scb_fetch) | KLAR | `statistics_agent.py`, `scb_tool_definitions.py` |
| 35 | 46 nya tester för LLM-verktygen | KLAR | `test_scb_llm_tools.py` |
| 36 | Uppdatera SCB-dokumentation till v5.0 | KLAR | `docs/API/SCB.md` |

---

## 21. Framtida Arbete

| Prioritet | Uppgift | Beskrivning |
|-----------|---------|-------------|
| P1 | Caching av codelist-resultat | TTL-cache för kodlistor (ofta återanvända) |
| P2 | Dedikerat SCB Tool UI | Frontend-komponent med tabell-rendering istället för generisk ToolFallback |
| P2 | Multi-tabell korrelation | Kombinera data från flera SCB-tabeller i en analys |
| P3 | Diagram-generering | Automatisk visualisering av tidsserier från scb_fetch |
| P3 | CSV/Parquet export | Låt användaren ladda ner data i andra format |

---

## Referenser

| Resurs | URL |
|--------|-----|
| SCB PxWebApi 2.0 (info) | https://www.scb.se/vara-tjanster/oppna-data/pxwebapi/ |
| Swagger UI (v2) | https://statistikdatabasen.scb.se/api/v2/index.html |
| OpenAPI-specifikation (YAML) | https://github.com/statisticssweden/PxApiSpecs/blob/master/PxAPI-2.yml |
| PxWebApi källkod | https://github.com/PxTools/PxWebApi |
| SCB v1 API (legacy) | https://api.scb.se/OV0104/v1/doris/sv/ssd/ |
| SCB-MCP (referensimplementation) | https://github.com/isakskogstad/SCB-MCP |
| SCB kontakt | px@scb.se |
