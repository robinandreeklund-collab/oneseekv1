# SCB Data Extraction Tool — Fullständig Analys & Förbättringsförslag

## 1. NULÄGESANALYS

### 1.1 Befintlig arkitektur (3-stegs hybrid LLM-flow)

```
Användare: "Hur många bor i Stockholm?"
    │
    ▼
┌──────────────────────────────────┐
│  Tool 1: scb_search_and_inspect  │  Söker tabeller, returnerar variabelstruktur
│  - v2 fulltext-sökning           │  (max 5 tabeller inspekteras)
│  - v1 tree-traversal (fallback)  │
│  - 47 domänverktyg via bigtool   │
└──────────┬───────────────────────┘
           │ LLM ser variabler, koder, labels
           ▼
┌──────────────────────────────────┐
│  Tool 2: scb_validate_selection  │  Torrkörning: validerar selection
│  - Alla variabler täckta?        │  mot metadata
│  - Fuzzy region/kön-matchning    │
│  - Estimerar cellantal           │
└──────────┬───────────────────────┘
           │ LLM korrigerar vid fel
           ▼
┌──────────────────────────────────┐
│  Tool 3: scb_fetch_validated     │  Hämtar data, batchning vid behov
│  - JSON-stat2 output             │
│  - Auto-batch >150k celler       │
│  - Ingest till kunskapsbas       │
└──────────────────────────────────┘
```

**Starka sidor:**
- LLM ser variabelstrukturen (inte gömda heuristiker)
- Fuzzy-matchning för regioner (312 fördefinierade), kön, ålder
- 47 domänverktyg med keyword-baserad retrieval
- 3-tier TTL-cache (noder, metadata, codelist)
- Parallel metadata-fetch (asyncio.gather)
- Smart batchning vid stora urval

### 1.2 Identifierade brister

| # | Problem | Konsekvens | Prioritet |
|---|---------|-----------|-----------|
| 1 | **LLM tolkar JSON-stat2 dåligt** | Rå JSON-stat2 är komplex — LLM gör felaktiga avläsningar, blandar dimensioner | KRITISK |
| 2 | **Ingen data-tabell-formatering** | LLM måste själv mappa flerdimensionell data → text, ofta fel | KRITISK |
| 3 | **25 värden max visas** | Tabeller med 290 kommuner — LLM ser bara 25, kan inte välja rätt | HÖG |
| 4 | **Inga v2 filteruttryck** | `TOP(5)`, `FROM(2020)`, `RANGE(2015,2020)`, `*` — oanvända! | HÖG |
| 5 | **Ingen navigering i SCB:s träd** | LLM kan inte "bläddra" i ämnesområden | MEDEL |
| 6 | **Inga fotnoter/metadata-notes** | SCB-tabeller har viktiga kvalitetsnoteringar som ignoreras | MEDEL |
| 7 | **Ingen multi-tabell-korrelering** | Kan inte jämföra data från flera tabeller | MEDEL |
| 8 | **Inget stöd för codelists (v2)** | Gemensamma kodlistor (län, kommuner) inte utnyttjade | MEDEL |
| 9 | **Rate limit okänd/ohanterad** | 30 anrop/10 sek gräns — ingen backoff | LÅG |
| 10 | **Tidskontroll saknas** | Inga varningar om tabell inte täcker önskad period | LÅG |

### 1.3 SCB v2 API — Funktioner vi INTE använder idag

**Testade och verifierade v2-funktioner:**

```
Wildcard:    {"valueCodes": ["*"]}          → alla värden
TOP(n):      {"valueCodes": ["TOP(5)"]}     → senaste 5 perioder
BOTTOM(n):   {"valueCodes": ["BOTTOM(3)"]}  → äldsta 3 perioder
FROM(val):   {"valueCodes": ["FROM(2020)"]} → från 2020 och framåt
RANGE(a,b):  {"valueCodes": ["RANGE(2015,2020)"]} → intervall
```

**Alla v2 API-endpoints (fullständig lista):**
```
GET  /config                         → API-version, rate limits, format-stöd
GET  /tables?query=X&lang=sv         → Fulltextsökning med paginering (pageSize, pageNumber)
GET  /tables?pastDays=30             → Nyligen uppdaterade tabeller
GET  /tables/{id}                    → Tabell-info (period, ämne, sökväg)
GET  /tables/{id}/metadata           → JSON-stat2 dimensioner + codelist-refs
GET  /tables/{id}/defaultselection   → Default-urval (!)
GET  /tables/{id}/data               → GET-baserad datahämtning (URL-parametrar)
POST /tables/{id}/data?outputFormat= → POST-baserad datahämtning (json-stat2, csv, xlsx, parquet, html, px, json-px)
GET  /codelists/{id}                 → Delade kodlistor (regionkoder, value sets, aggregeringar)
POST /savedqueries                   → Spara en fråga
GET  /savedqueries/{id}              → Hämta sparad fråga
GET  /savedqueries/{id}/data         → Kör sparad fråga
```

**Komplett v2 selektionsuttryck (verifierade live):**
```
*                     → Alla värden (wildcard)
00*                   → Prefix-wildcard (alla koder som börjar med "00")
*01                   → Suffix-wildcard
?????                 → Teckenmask (exakt 5 tecken)
TOP(n)                → Senaste n perioder (verifierat ✓)
TOP(n, offset)        → Senaste n med offset
BOTTOM(n)             → Äldsta n perioder (verifierat ✓)
BOTTOM(n, offset)     → Äldsta n med offset
FROM(value)           → Från värde och framåt (verifierat ✓)
TO(value)             → Till ett värde
RANGE(from, to)       → Inklusivt intervall (verifierat ✓)
```

**v2 extra POST-fält vi inte använder:**
- `codelist` per variabel: `{"variableCode": "Region", "codelist": "vs_RegionKommun07", "valueCodes": ["0180"]}` — Välj bland grupperade kodlistor (län, kommun, storstäder etc.)
- `placement` — styr pivot: `{"heading": ["Tid"], "stub": ["Region", "Kon"]}` — Kontrollerar tabellayout i CSV/HTML
- `defaultselection` endpoint — SCB:s rekommenderade standardurval

**v2 CSV/XLSX extra parametrar:**
- `UseCodes`, `UseTexts`, `UseCodesAndTexts` — kontrollera labelformat
- `ExcludeZerosAndMissingValues` — filtrera bort tomma celler
- `SeparatorTab`, `SeparatorSemicolon` — separatorval

**Viktiga metadata-fält vi inte använder:**
- `extension.elimination` / `eliminationValueCode` — säger vilka variabler som kan utelämnas och default-värde
- `role.time` / `role.metric` — exakt vilka dimensioner som är tid respektive mått
- `category.unit` — enhet och decimaler per ContentsCode: `{"BE0101N1": {"base": "number of persons", "decimals": 0}}`
- `extension.refperiod` — referensperiod: `{"BE0101N1": "31 December each year"}`
- `extension.measuringType` — mättyp: `Stock`, `Flow`, etc.
- `firstPeriod` / `lastPeriod` — ger periodomfång utan att hämta metadata
- `subjectCode` — ämnesklassificering
- `note[]` — fotnoter med kvalitetsinformation
- `status` — markerar speciella värden i data: `".."` = saknas/sekretessbelagt
- `extension.px.official-statistics` — om tabellen är officiell statistik

---

## 2. FÖRSLAG: Nästa generations SCB-verktyg

### 2.1 Ny arkitektur — 5-stegs adaptiv flow

```
┌────────────────────────────────────────────────────────────────┐
│                    SCB INTELLIGENT NAVIGATOR                    │
│                                                                │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │  Tool 1      │  │  Tool 2       │  │  Tool 3               │ │
│  │  NAVIGATE    │  │  SEARCH       │  │  INSPECT              │ │
│  │  Bläddra i   │  │  Fulltext +   │  │  Metadata +           │ │
│  │  ämnesträdet  │  │  smart rank   │  │  alla värden +        │ │
│  │              │  │              │  │  filteruttryck         │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────────────┘ │
│         │                 │                  │                  │
│         └────────┬────────┘──────────────────┘                  │
│                  ▼                                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Tool 4: QUERY                                           │  │
│  │  Bygg + validera + hämta i ETT steg                      │  │
│  │  - v2 filteruttryck (TOP, FROM, RANGE, *)                │  │
│  │  - Auto-complete saknade variabler med elimination-defaults│ │
│  │  - Smart batchning                                       │  │
│  │  - Rate limit respekterande                              │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Tool 5: FORMAT & ANALYZE                                │  │
│  │  JSON-stat2 → läsbar tabell med rubriker                 │  │
│  │  - Pivot-tabeller (konfigurerbar rad/kolumn)             │  │
│  │  - Procentuell förändring                                │  │
│  │  - Ranking                                               │  │
│  │  - Fotnoter och kvalitetsinfo                            │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Detaljerade verktyg

---

#### Tool 1: `scb_navigate` (NY)

**Syfte:** Låt LLM bläddra i SCB:s hierarkiska ämnesträd.

```python
async def scb_navigate(
    path: str = "",          # "" = rot, "BE" = Befolkning, "BE/BE0101" = Folkmängd
    lang: str = "sv",
) -> str:
    """Navigera i SCB:s ämnesträd.

    Returnerar barn-noder (undermappar och tabeller).
    Använd detta för att utforska vilka statistikområden som finns,
    INNAN du söker efter specifika tabeller.

    Exempel:
        scb_navigate("")           → Alla ämnesområden (BE, AM, BO, ...)
        scb_navigate("BE")        → Befolkningsstatistik (underkategorier)
        scb_navigate("BE/BE0101") → Folkmängd (specifika tabeller)
    """
```

**Returnerar:**
```json
{
  "path": "BE",
  "label": "Befolkning",
  "children": [
    {"id": "BE0101", "label": "Folkmängd", "type": "folder", "path": "BE/BE0101"},
    {"id": "BE0401", "label": "Befolkningsframskrivningar", "type": "folder"},
    ...
  ],
  "tables": [
    {"id": "TAB1234", "label": "Folkmängd efter...", "period": "1968-2024", "variables": ["region","kön","ålder","år"]}
  ]
}
```

**Varför:** Idag kan LLM bara söka — den kan inte "bläddra". Många frågor kräver att man förstår vilka underkategorier som finns. T.ex. "vilken statistik finns om boende?" — då vill man se hela BO-trädet.

---

#### Tool 2: `scb_search` (FÖRBÄTTRAD)

**Syfte:** Intelligent sökning med pre-flight metadata.

```python
async def scb_search(
    query: str,              # Söktermer (svenska ger bäst resultat)
    subject_area: str = "",  # Filtrera på ämne: "BE", "AM", "NR", etc.
    time_filter: str = "",   # "recent" = uppdaterade senaste 2 åren
    max_results: int = 10,
) -> str:
    """Sök SCB-tabeller med smart ranking.

    Returnerar tabeller med sammanfattad metadata — INTE full variabelstruktur.
    Använd scb_inspect för att se detaljerad struktur av en specifik tabell.
    """
```

**Förbättringar:**
- Använder v2 `tables?query=` med `subjectCode`-filtrering
- Pre-flight info: `firstPeriod`, `lastPeriod`, `variableNames` utan att hämta metadata
- Rankar efter: query-relevans, uppdateringsdatum, periodtäckning
- Returnerar **kort** sammanfattning per tabell (inte full metadata)

---

#### Tool 3: `scb_inspect` (KRAFTIGT FÖRBÄTTRAD)

**Syfte:** Djupinspektion av EN tabell — visa ALLA värden, filteruttryck, och smarta defaults.

```python
async def scb_inspect(
    table_id: str,
    variable_filter: str = "",  # Visa bara en specifik variabel: "Region", "Tid"
    show_all_values: bool = False,  # True = visa ALLA 290 kommuner, inte bara 25
) -> str:
    """Inspektera en SCB-tabell i detalj.

    Visar alla variabler med deras koder, etiketter, och metadata.
    Ger även filteruttryck-tips (TOP, FROM, RANGE) och smarta defaults.
    """
```

**Nyckelförbättringar:**

1. **Elimination-defaults:** Om variabeln har `elimination=true` med `eliminationValueCode`, visa: "Denna variabel kan utelämnas (default: Riket)"
2. **Smarta filteruttryck:** Istället för att lista 290 kommuner:
   ```
   Region: 290 värden tillgängliga
     Filteruttryck:
       - Använd "*" för ALLA regioner
       - Eller ange specifika koder: "0180" (Stockholm), "1480" (Göteborg)
     Vanliga val:
       - "00" = Riket (hela Sverige)
       - "01" = Stockholms län
       - "0180" = Stockholms kommun
   ```
3. **Tids-intelligens:**
   ```
   Tid: 57 årsvärden (1968-2024)
     Filteruttryck:
       - TOP(5) = senaste 5 åren (2020-2024)
       - FROM(2020) = från 2020 och framåt
       - RANGE(2015,2020) = intervall
       - "*" = alla år
     Senast uppdaterad: 2025-02-20
   ```
4. **ContentsCode-beskrivning:** Tydlig label + enhet för varje mått
5. **Fotnoter:** Visa relevanta `note[]` från metadata
6. **Variabelfiltrering:** `variable_filter="Region"` visar bara den variabeln med ALLA 290 värden

---

#### Tool 4: `scb_query` (SAMMANSLAGEN validate + fetch)

**Syfte:** Bygg, validera och hämta data i ETT anrop — med v2 filteruttryck.

```python
async def scb_query(
    table_id: str,
    selection: dict[str, list[str]],
    # Stöder v2-uttryck: {"Tid": ["TOP(5)"], "Region": ["*"], "Kon": ["1","2"]}
    output_format: str = "readable",  # "readable" | "json-stat2" | "csv"
    auto_complete: bool = True,  # Fyll i saknade variabler med elimination-defaults
) -> str:
    """Bygg, validera och hämta SCB-data i ett steg.

    Stöder v2 filteruttryck:
      - "*" = alla värden
      - "TOP(n)" = senaste n perioder
      - "BOTTOM(n)" = äldsta n perioder
      - "FROM(value)" = från ett värde
      - "TO(value)" = till ett värde
      - "RANGE(from,to)" = intervall

    Med auto_complete=True fylls saknade variabler i automatiskt
    med SCB:s elimination-defaults (t.ex. Region → Riket).
    """
```

**Nyckelförbättringar:**

1. **v2 filteruttryck:** Skickar `TOP(5)`, `FROM(2020)` etc. direkt till SCB API — slipper lista alla värden
2. **Auto-complete:** Läser `extension.elimination` + `eliminationValueCode` från metadata och fyller i saknade variabler automatiskt
3. **Readable output:** Konverterar JSON-stat2 → tabell i markdown:
   ```
   | Region      | Kön     | 2022      | 2023      | 2024      |
   |-------------|---------|-----------|-----------|-----------|
   | Stockholm   | Män     | 1,234,567 | 1,245,678 | 1,256,789 |
   | Stockholm   | Kvinnor | 1,267,890 | 1,278,901 | 1,289,012 |
   | Göteborg    | Män     |   543,210 |   549,876 |   556,543 |
   ```
4. **Automatisk validering:** Körs internt — vid fel returneras felmeddelande med förslag (ingen extra tool-call behövs)
5. **Rate limit-hantering:** Max 30 anrop/10s med async semaphore + exponential backoff
6. **Period-kontroll:** Varnar om begärd period inte täcks av tabellen

---

#### Tool 5: `scb_format` (NY — post-processing)

**Syfte:** Transformera redan hämtad data för bättre presentation.

```python
async def scb_format(
    data: dict,            # JSON-stat2 data från scb_query
    pivot: str = "auto",   # "auto" | "time_columns" | "region_rows" | "flat"
    calculate: str = "",   # "change_pct" | "change_abs" | "rank" | "share_pct"
    top_n: int = 0,        # Visa bara top N (efter sortering)
    sort_by: str = "",     # Sortera efter variabel/värde
) -> str:
    """Formatera och analysera SCB-data.

    Konverterar JSON-stat2 till läsbara tabeller med valfria beräkningar.
    """
```

**Funktioner:**
- **Pivot-tabeller:** Automatisk pivot baserat på datastruktur (tid som kolumner, regioner som rader)
- **Procentuell förändring:** Beräkna förändring mellan perioder
- **Ranking:** Top/bottom N per variabel
- **Andelar:** Beräkna procentuell andel av totalen
- **Fotnoter:** Inkludera SCB:s kvalitetsnoteringar

---

### 2.3 JSON-stat2 → Readable Table Converter (KRITISK KOMPONENT)

**Detta är den enskilt viktigaste förbättringen.** Idag returnerar vi rå JSON-stat2 som LLM måste tolka. JSON-stat2 använder flat arrays med implicit dimensionsordning — extremt svårt för en LLM att läsa korrekt.

**Problemet — JSON-stat2 struktur:**
```json
{
  "id": ["Region", "Kon", "Tid"],
  "size": [2, 2, 3],
  "dimension": {
    "Region": {"category": {"index": {"0180": 0, "1480": 1}, "label": {"0180": "Stockholm", "1480": "Göteborg"}}},
    "Kon": {"category": {"index": {"1": 0, "2": 1}, "label": {"1": "män", "2": "kvinnor"}}},
    "Tid": {"category": {"index": {"2022": 0, "2023": 1, "2024": 2}, "label": {...}}}
  },
  "value": [501234, 523456, 535678, 512345, 534567, 546789, 289012, 291234, 293456, 290123, 292345, 294567]
}
```

LLM måste förstå att `value[0]` = Stockholm + män + 2022, `value[3]` = Stockholm + kvinnor + 2022 (row-major order). **Detta misslyckas regelbundet.**

**Lösning — `jsonstat2_to_table()`:**

Konverterar automatiskt till:
```
| region      | kön     | 2022      | 2023      | 2024      |
|-------------|---------|-----------|-----------|-----------|
| Stockholm   | män     | 501 234   | 523 456   | 535 678   |
| Stockholm   | kvinnor | 512 345   | 534 567   | 546 789   |
| Göteborg    | män     | 289 012   | 291 234   | 293 456   |
| Göteborg    | kvinnor | 290 123   | 292 345   | 294 567   |
```

Implementationsdetaljer:
- Automatisk pivot: tid som kolumner, övriga dimensioner som rader
- Talformatering med tusenavskiljare (svenska standard: mellanslag)
- Hanterar missing values (`.` i JSON-stat2)
- Inkluderar fotnoter under tabellen
- Stöder flat-format (en rad per cell) för stora datamängder

---

### 2.4 Uppdaterad systemprompt

```
Du är OneSeek Statistik-agent. Du hjälper till att hämta officiell statistik från SCB.

## Arbetsflöde

### Steg 1: HITTA rätt tabell
- `scb_search(query="...")` — Sök tabeller med nyckelord
- `scb_navigate(path="BE")` — Bläddra i ämnesträdet om du vill utforska
- Titta på tabellens period, variabler och ämne

### Steg 2: INSPEKTERA tabellen
- `scb_inspect(table_id="TABxxxx")` — Se alla variabler, koder, filteruttryck
- Om 290 kommuner: `scb_inspect(table_id="...", variable_filter="Region", show_all_values=True)`
- Notera elimination-defaults (variabler som kan utelämnas)

### Steg 3: HÄMTA data
- `scb_query(table_id="...", selection={...})` — Bygg, validera och hämta i ETT steg
- Använd filteruttryck istället för att lista alla värden:
  - `"Tid": ["TOP(5)"]` — senaste 5 åren
  - `"Region": ["*"]` — alla regioner
  - `"Tid": ["FROM(2020)"]` — från 2020
  - `"Tid": ["RANGE(2015,2020)"]` — intervall
- `auto_complete=True` fyller i saknade variabler automatiskt

### Regler
- Svara alltid på svenska
- Använd filteruttryck (TOP, FROM, RANGE, *) istället för långa värdelistor
- Vid tveksamhet: inspektera tabellen först
- Presentera data som formaterad tabell med källa
- Inkludera fotnoter om de finns
- Vid fel: korrigera och försök igen (max 2 retries)
```

---

### 2.5 Implementationsplan (6 faser)

#### Fas 1: JSON-stat2 formatter (KRITISKT — störst ROI)
**Filer:**
- `app/services/scb_formatter.py` (NY) — `jsonstat2_to_table()`, `jsonstat2_to_flat_records()`
- Uppdatera `scb_llm_tools.py` → `scb_fetch_validated` returnerar formaterad tabell
- `tests/test_scb_formatter.py` (NY)

#### Fas 2: v2 filteruttryck + auto-complete
**Filer:**
- Uppdatera `scb_service.py` — stöd `TOP()`, `FROM()`, `RANGE()`, `*` i payloads
- Uppdatera `scb_llm_tools.py` — `scb_validate_selection` tillåter och validerar filteruttryck
- Läs `extension.elimination` + `eliminationValueCode` för auto-complete

#### Fas 3: Navigeringsverktyg
**Filer:**
- `scb_llm_tools.py` — ny tool `scb_navigate`
- `scb_service.py` — ny metod `navigate(path)` med v1 tree-API

#### Fas 4: Sammanslagen query-tool (`scb_query`)
**Filer:**
- `scb_llm_tools.py` — ny tool `scb_query` (validate+fetch+format i ett)
- Intern validering + formatering + fotnoter

#### Fas 5: Rate limiting + robusthet
**Filer:**
- `scb_service.py` — async semaphore (30 req/10s), exponential backoff
- Period-validering mot `firstPeriod`/`lastPeriod`
- Retry-logik för nätverksfel

#### Fas 6: Prompt & integration
**Filer:**
- `statistics_prompts.py` — uppdaterad systemprompt
- `tools/registry.py` — registrera nya verktyg
- `statistics_agent.py` — uppdatera agent
- Tester för alla nya funktioner

---

## 3. SAMMANFATTNING

### Före (nuvarande)
```
Användare: "Folkmängd i Stockholm senaste 5 åren"
  → Tool 1: Söker, hittar tabell, visar 25 av 290 kommuner
  → Tool 2: LLM gissar koder, validerar (ofta fel → retry)
  → Tool 3: Hämtar JSON-stat2 (rå, svårtolkad)
  → LLM: Försöker tolka flat value-array... ofta fel
  = 3-5 tool calls, ofta felaktig data
```

### Efter (föreslaget)
```
Användare: "Folkmängd i Stockholm senaste 5 åren"
  → Tool: scb_search("folkmängd") → ser perioder, variabler direkt
  → Tool: scb_inspect("TABxxxx") → ser filteruttryck, elimination-defaults
  → Tool: scb_query("TABxxxx", {"Region": ["0180"], "Tid": ["TOP(5)"]}, auto_complete=True)
  → Returnerar formaterad markdown-tabell + fotnoter
  = 2-3 tool calls, korrekt formaterad data varje gång
```

### Top 5 förbättringar (prioritetsordning)
1. **JSON-stat2 → Markdown-tabell** — LLM kan läsa data korrekt (eliminerar huvudproblemet)
2. **v2 filteruttryck (TOP, FROM, RANGE, *, prefix-wildcard)** — drastiskt enklare urval
3. **Auto-complete med elimination-defaults + defaultselection** — färre fel, färre tool-calls
4. **Codelists (vs_RegionLän, vs_RegionKommun)** — välj aggregeringsnivå
5. **Rate limiting (30 req/10s)** — robusthet i produktion

---

## 4. APPENDIX: v1 vs v2 API-skillnader

| Feature | v1 | v2 |
|---------|----|----|
| Navigation | Sökvägsbaserad trädnavigering (GET `/ssd/BE/BE0101`) | `/tables` sökning + stabila tabell-ID:n |
| Tabell-ID | Sökvägsbaserade namn (`BefolkningNy`) | Stabila ID:n (`TAB638`) |
| Query-metod | Enbart POST | GET och POST |
| Selection-syntax | Filter-typer (`item`, `top`, `all`, `vs:`, `agg:`) | Uttryck i valueCodes (`top(n)`, `range()`, `from()`, `*`, `?`) |
| Responsformat | 4 (json-stat2, json, csv, px) | 7 (+ xlsx, html, json-px, parquet) |
| Kodlistor | Via filterprefix (`vs:`, `agg:`) | Dedikerad `/codelists/{id}` + `codelist`-fält |
| Sparade frågor | Ej tillgängligt | Full CRUD via `/savedqueries` |
| Rate limit | 30 req/10s (per IP) | 30 req/10s (per IP) |
| Max celler | 150 000 | 150 000 |
| Felkoder | 400, 403, 404 | 400, 403, 404, 429 (rate limited) |
