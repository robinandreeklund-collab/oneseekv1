# SCB Perfekt Datahämtning — Implementationsförslag

## Sammanfattning

**Mål**: Det mest kompletta SCB-verktyget som finns. Alla frågor ska ge korrekt data.

**Arkitektur**: 5 specialiserade verktyg i en pipeline, där varje steg är enkelt och verifierbart. Extra LLM-anrop är OK — korrekthet är allt.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        LLM AGENT (Statistik)                           │
│                                                                        │
│  Användare: "Befolkning i Stockholm och Göteborg 2020-2024"            │
│                                                                        │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │ 1. SÖK   │──▶│ 2. BROWSE│──▶│3.INSPECT │──▶│4.VALIDATE│──▶ FETCH   │
│  │ tabeller │   │ (opt.)   │   │ metadata │   │ + auto-  │   + decode │
│  │          │   │ trädnav. │   │          │   │ complete │   → tabell  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘            │
│       ↑                                            │                   │
│       └────────────── retry vid fel ───────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## De 5 verktygen

### Verktyg 1: `scb_search` (hitta rätt tabell)

**Syfte**: Fulltextsökning bland SCB:s ~2000 tabeller. Returnerar en kompakt lista.

**Input**:
```python
async def scb_search(
    query: str,              # Sökfråga på svenska, t.ex. "befolkning ålder kommun"
    max_results: int = 15,   # Max antal träffar
    past_days: int | None = None,  # Bara nyligen uppdaterade tabeller
) -> str:
```

**Output** (JSON → LLM):
```json
{
  "query": "befolkning ålder kommun",
  "results": [
    {
      "id": "TAB638",
      "title": "Folkmängden efter region, civilstånd, ålder och kön. År 1968-2024",
      "period": "1968-2024",
      "subject": "Befolkning",
      "updated": "2025-02-21",
      "variables": ["Region", "Civilstånd", "Ålder", "Kön", "ContentsCode", "Tid"]
    },
    ...
  ],
  "total_hits": 47,
  "next_step": "Välj en tabell och kör scb_inspect(table_id='TAB638') för full metadata."
}
```

**Förändring vs nuvarande**: Renare output. Visar variabelnamn direkt (från v2 /tables endpoint). Ingen metadata-hämtning i detta steg — snabbt och billigt.

---

### Verktyg 2: `scb_browse` (trädnavigering) — NYTT

**Syfte**: Navigera SCB:s ämnesträd steg för steg. För explorativa frågor som "Vad finns det för arbetsmarknadsstatistik?".

**Input**:
```python
async def scb_browse(
    path: str = "",  # Tom = visa toppnivån. "AM" = visa under Arbetsmarknad
) -> str:
```

**Output** (JSON → LLM):
```json
{
  "path": "AM",
  "breadcrumb": ["Arbetsmarknad"],
  "items": [
    {"id": "AM0101", "type": "folder", "text": "Arbetsmarknadsdata (AKU)"},
    {"id": "AM0110", "type": "folder", "text": "Lönestrukturstatistik"},
    {"id": "AM0301", "type": "folder", "text": "Korttidsstatistik"},
    {"id": "TAB1234", "type": "table", "text": "Arbetslösa 15-74 år. Månad 2005M01-2024M12", "updated": "2025-01-15"}
  ],
  "next_step": "Navigera djupare med scb_browse(path='AM/AM0101') eller inspektera en tabell med scb_inspect(table_id='TAB1234')."
}
```

**API**: Använder v1-trädnavigering (`GET /ssd/AM/`) som returnerar `[{"id": "AM0101", "type": "l"}, ...]`. v2 saknar trädstruktur, men v1 fungerar perfekt för detta.

---

### Verktyg 3: `scb_inspect` (full metadata)

**Syfte**: Visa ALLT som behövs för att bygga en korrekt selection. Det här steget är kritiskt — LLM:en måste se variabelkoder, tillåtna värden och defaults.

**Input**:
```python
async def scb_inspect(
    table_id: str,  # T.ex. "TAB638" eller "BefolkningNy"
) -> str:
```

**Output** (JSON → LLM):
```json
{
  "table_id": "TAB638",
  "title": "Folkmängden efter region, civilstånd, ålder och kön. År 1968-2024",
  "source": "SCB",
  "updated": "2025-02-21T08:00:00Z",
  "official_statistics": true,
  "contact": "information@scb.se",
  "footnotes": ["Uppgifterna avser 31 december respektive år."],

  "variables": [
    {
      "code": "Region",
      "label": "region",
      "eliminable": true,
      "default_value": "00",
      "total_values": 312,
      "sample_values": [
        {"code": "00", "label": "Riket"},
        {"code": "01", "label": "Stockholms län"},
        {"code": "0180", "label": "Stockholm"},
        {"code": "1280", "label": "Malmö"},
        {"code": "1480", "label": "Göteborg"}
      ],
      "codelists": ["vs_RegionLän", "vs_RegionKommun07", "vs_RegionStorstad"],
      "hint": "312 värden. Använd codelist 'vs_RegionLän' för enbart län (21 st), 'vs_RegionKommun07' för kommuner (290 st)."
    },
    {
      "code": "Civilstand",
      "label": "civilstånd",
      "eliminable": true,
      "default_value": null,
      "total_values": 4,
      "all_values": [
        {"code": "OG", "label": "ogifta"},
        {"code": "G", "label": "gifta"},
        {"code": "ANKL", "label": "änkor/änklingar"},
        {"code": "SK", "label": "skilda"}
      ]
    },
    {
      "code": "Alder",
      "label": "ålder",
      "eliminable": true,
      "default_value": "tot",
      "total_values": 102,
      "sample_values": [
        {"code": "0", "label": "0 år"},
        {"code": "18", "label": "18 år"},
        {"code": "65", "label": "65 år"},
        {"code": "100+", "label": "100+ år"},
        {"code": "tot", "label": "totalt ålder"}
      ],
      "hint": "102 värden (0-100+, tot). Använd 'tot' för total."
    },
    {
      "code": "Kon",
      "label": "kön",
      "eliminable": true,
      "default_value": null,
      "total_values": 2,
      "all_values": [
        {"code": "1", "label": "män"},
        {"code": "2", "label": "kvinnor"}
      ]
    },
    {
      "code": "ContentsCode",
      "label": "tabellinnehåll",
      "eliminable": false,
      "total_values": 2,
      "all_values": [
        {
          "code": "BE0101N1",
          "label": "Folkmängd",
          "unit": "antal personer",
          "decimals": 0,
          "ref_period": "31 december resp. år",
          "measuring_type": "Stock"
        },
        {
          "code": "BE0101N2",
          "label": "Folkökning",
          "unit": "antal personer",
          "decimals": 0,
          "ref_period": "Under året",
          "measuring_type": "Flow"
        }
      ]
    },
    {
      "code": "Tid",
      "label": "år",
      "eliminable": false,
      "total_values": 57,
      "first": "1968",
      "last": "2024",
      "sample_values": [
        {"code": "2020", "label": "2020"},
        {"code": "2021", "label": "2021"},
        {"code": "2022", "label": "2022"},
        {"code": "2023", "label": "2023"},
        {"code": "2024", "label": "2024"}
      ],
      "hint": "57 år (1968-2024). Använd TOP(5) för senaste 5 åren, RANGE(2020,2024) för intervall."
    }
  ],

  "default_selection": {
    "Region": ["00"],
    "Civilstand": ["*"],
    "Alder": ["tot"],
    "Kon": ["1", "2"],
    "ContentsCode": ["BE0101N1"],
    "Tid": ["TOP(5)"]
  },

  "next_step": "Bygg din selection och kör scb_fetch(table_id='TAB638', selection={...}). Tips: utelämna variabler du inte bryr dig om — de auto-fylls med defaults."
}
```

**Kritiska förbättringar vs nuvarande**:
1. **`default_selection`** — Hämtas från v2 `/tables/{id}/defaultselection` endpoint
2. **`codelists`** — Visar tillgängliga kodlistor per variabel
3. **`hint`** — Genererade tips om v2-uttryck (TOP, RANGE, FROM)
4. **`sample_values`** — Visar inte alla 312 regionkoder, bara de 5 viktigaste + totalt antal
5. **ContentsCode enrichment** — Enhet, decimaler, referensperiod, mättyp
6. **`eliminable`** + `default_value` — LLM:en vet vad den kan utelämna

---

### Verktyg 4: `scb_fetch` (hämta data + dekoda till tabell) — KRAFTIGT FÖRBÄTTRAT

**Syfte**: Hämta data, dekoda JSON-stat2 till läsbar markdown-tabell, returnera med metadata.

**Input**:
```python
async def scb_fetch(
    table_id: str,                    # "TAB638"
    selection: dict[str, list[str]],  # {"Region": ["0180","1480"], "Tid": ["TOP(3)"], "ContentsCode": ["BE0101N1"]}
    codelist: dict[str, str] | None = None,  # {"Region": "vs_RegionLän"} — optional
    max_rows: int = 100,              # Trunkering av output
) -> str:
```

**Intern logik (4 steg)**:

```
1. AUTO-COMPLETE: Hämta metadata → fyll i saknade variabler med elimination-defaults
2. VALIDERA: Kontrollera att koder finns, estimera cellantal, varna vid >150k
3. HÄMTA: POST till /tables/{id}/data med v2-format (stödjer TOP/FROM/RANGE)
4. DEKODA: JSON-stat2 → markdown-tabell med labels, enheter och fotnoter
```

**Output** (JSON → LLM):
```json
{
  "table_id": "TAB638",
  "title": "Folkmängden efter region, civilstånd, ålder och kön",
  "source": "SCB, Statistikdatabasen",
  "updated": "2025-02-21",
  "unit": "antal personer",
  "ref_period": "31 december resp. år",
  "footnotes": ["Uppgifterna avser 31 december respektive år."],

  "selection_used": {
    "Region": ["0180 (Stockholm)", "1480 (Göteborg)"],
    "Civilstand": ["* (auto: eliminable)"],
    "Alder": ["tot (auto: default)"],
    "Kon": ["1 (män)", "2 (kvinnor)"],
    "ContentsCode": ["BE0101N1 (Folkmängd)"],
    "Tid": ["2022", "2023", "2024"]
  },

  "data_table": "| Region | Kön | År | Folkmängd |\n|---|---|---|---:|\n| Stockholm | män | 2022 | 504 232 |\n| Stockholm | män | 2023 | 510 118 |\n| Stockholm | män | 2024 | 514 937 |\n| Stockholm | kvinnor | 2022 | 498 761 |\n| Stockholm | kvinnor | 2023 | 503 459 |\n| Stockholm | kvinnor | 2024 | 507 218 |\n| Göteborg | män | 2022 | 295 112 |\n| Göteborg | män | 2023 | 298 447 |\n| Göteborg | män | 2024 | 301 023 |\n| Göteborg | kvinnor | 2022 | 291 854 |\n| Göteborg | kvinnor | 2023 | 294 617 |\n| Göteborg | kvinnor | 2024 | 296 891 |",

  "total_rows": 12,
  "truncated": false,

  "auto_completed_variables": ["Civilstand", "Alder"],
  "warnings": []
}
```

**DEN AVGÖRANDE ALGORITMEN — JSON-stat2 → Markdown-tabell**:

```python
def decode_jsonstat2_to_table(response: dict) -> tuple[list[str], list[list[str]]]:
    """Dekoda JSON-stat2 flat value-array till tabell med headers + rows.

    JSON-stat2 lagrar data som en platt array i row-major ordning.
    Dimensioner definieras i 'id' med storlekar i 'size'.

    Exempel: id=["Region","Kon","Tid"], size=[2,2,3]
    Index för (Region=1, Kon=0, Tid=2) = 1*2*3 + 0*3 + 2 = 8

    Algoritm:
    1. Läs dimensionerna (id, size)
    2. Skapa label-mappningar från dimension.X.category.label
    3. Iterera genom alla kombinationer (cartesian product)
    4. Mappa varje kombination till platt index
    5. Hämta värdet från value[index]
    6. Formatera som tabell
    """
    dim_ids = response["id"]           # ["Region", "Kon", "Tid"]
    sizes = response["size"]           # [2, 2, 3]
    values = response["value"]         # [504232, 510118, ...]
    status = response.get("status", {})
    dimensions = response["dimension"]

    # 1. Bygg label-mappning per dimension
    dim_labels = {}      # {"Region": "region", ...}
    value_labels = {}    # {"Region": {"0180": "Stockholm", ...}, ...}
    for dim_id in dim_ids:
        dim = dimensions[dim_id]
        dim_labels[dim_id] = dim.get("label", dim_id)
        cat = dim.get("category", {})
        value_labels[dim_id] = cat.get("label", {})

    # 2. Skapa ordnade listor av koderna per dimension
    dim_codes = []
    for dim_id in dim_ids:
        cat = dimensions[dim_id]["category"]
        index_map = cat.get("index", {})
        # index_map: {"0180": 0, "1480": 1} — sortera efter position
        codes = sorted(index_map.keys(), key=lambda k: index_map[k])
        dim_codes.append(codes)

    # 3. Identifiera ContentsCodes enhet
    unit_info = {}
    if "ContentsCode" in dimensions:
        cc = dimensions["ContentsCode"].get("category", {})
        unit_info = cc.get("unit", {})

    # 4. Headers
    headers = [dim_labels.get(d, d) for d in dim_ids]

    # 5. Generera rader via cartesian product
    from itertools import product
    rows = []
    for combo in product(*dim_codes):
        # Beräkna flat index
        flat_idx = 0
        for i, code in enumerate(combo):
            pos = dimensions[dim_ids[i]]["category"]["index"][code]
            stride = 1
            for j in range(i + 1, len(dim_ids)):
                stride *= sizes[j]
            flat_idx += pos * stride

        # Hämta värde
        val = values[flat_idx] if flat_idx < len(values) else None
        str_idx = str(flat_idx)
        if str_idx in status:
            val_str = status[str_idx]  # T.ex. ".."
        elif val is None:
            val_str = ".."
        elif isinstance(val, float):
            val_str = f"{val:,.{unit_info.get(combo[dim_ids.index('ContentsCode')] if 'ContentsCode' in dim_ids else '', {}).get('decimals', 0)}f}" if unit_info else f"{val:,.0f}"
        elif isinstance(val, int):
            val_str = f"{val:,}"
        else:
            val_str = str(val)

        # Mappa koder → labels
        row = []
        for i, code in enumerate(combo):
            label = value_labels[dim_ids[i]].get(code, code)
            row.append(label)
        row.append(val_str)
        rows.append(row)

    return headers, rows
```

**Formatera som markdown**:
```python
def format_markdown_table(headers: list[str], rows: list[list[str]], max_rows: int = 100) -> str:
    # Separera dimensionskolumner från värdekolumner
    # Högerställ numeriska kolumner (---: i separator)
    # Truncate vid max_rows med "[...N fler rader utelämnade]"
    # Använd tusentalsavgränsare (mellanslag, inte komma — svensk standard)
    ...
```

---

### Verktyg 5: `scb_codelist` (kodlistor) — NYTT

**Syfte**: Hämta detaljerna för en specifik kodlista. Används när LLM:en vill välja "bara län" eller "bara kommuner" istället för alla 312 regionkoder.

**Input**:
```python
async def scb_codelist(
    codelist_id: str,  # "vs_RegionLän", "vs_RegionKommun07", etc.
) -> str:
```

**Output**:
```json
{
  "id": "vs_RegionLän",
  "label": "Län",
  "type": "ValueSet",
  "values": [
    {"code": "01", "label": "Stockholms län"},
    {"code": "03", "label": "Uppsala län"},
    {"code": "04", "label": "Södermanlands län"},
    ...
  ],
  "total_values": 21
}
```

---

## Flödesexempel (komplett)

### Fråga: "Hur många bor i Stockholm och Göteborg, uppdelat på kön, senaste 3 åren?"

```
LLM: scb_search(query="befolkning folkmängd kommun")
→ Resultat: [{id: "TAB638", title: "Folkmängden efter region...", ...}, ...]

LLM: scb_inspect(table_id="TAB638")
→ Resultat: Alla variabler med koder, eliminable-flaggor, defaults, hints

LLM: scb_fetch(
    table_id="TAB638",
    selection={
        "Region": ["0180", "1480"],
        "ContentsCode": ["BE0101N1"],
        "Kon": ["1", "2"],
        "Tid": ["TOP(3)"]
    }
    # OBS: Civilstand och Alder UTELÄMNADE — auto-fylls med elimination-defaults
)
→ Auto-complete: Civilstand=alla (eliminable), Alder=tot (eliminationValueCode)
→ Resultat:

| region | kön | år | Folkmängd |
|---|---|---|---:|
| Stockholm | män | 2022 | 504 232 |
| Stockholm | män | 2023 | 510 118 |
| Stockholm | män | 2024 | 514 937 |
| Stockholm | kvinnor | 2022 | 498 761 |
| Stockholm | kvinnor | 2023 | 503 459 |
| Stockholm | kvinnor | 2024 | 507 218 |
| Göteborg | män | 2022 | 295 112 |
| Göteborg | män | 2023 | 298 447 |
| Göteborg | män | 2024 | 301 023 |
| Göteborg | kvinnor | 2022 | 291 854 |
| Göteborg | kvinnor | 2023 | 294 617 |
| Göteborg | kvinnor | 2024 | 296 891 |
```

### Fråga: "Vad finns det för statistik om utbildning?"

```
LLM: scb_browse(path="")
→ Resultat: [{id: "UF", type: "folder", text: "Utbildning och forskning"}, ...]

LLM: scb_browse(path="UF")
→ Resultat: [{id: "UF0506", type: "folder", text: "Befolkningens utbildning"}, ...]

LLM: scb_browse(path="UF/UF0506")
→ Resultat: [{id: "TAB4532", type: "table", text: "Utbildningsnivå 25-64 år..."}, ...]

LLM: scb_inspect(table_id="TAB4532")
→ Full metadata
```

### Fråga: "Arbetslöshet i alla län 2024"

```
LLM: scb_search(query="arbetslöshet AKU")
→ Resultat: [{id: "TAB1234", ...}]

LLM: scb_inspect(table_id="TAB1234")
→ Variabler: Region (codelist: vs_RegionLän), Tid, ContentsCode, ...

LLM: scb_fetch(
    table_id="TAB1234",
    selection={
        "ContentsCode": ["AM0401B1"],
        "Tid": ["2024"]
    },
    codelist={"Region": "vs_RegionLän"}
    # Region utelämnad i selection → auto-complete: alla värden i kodlistan
)
→ Tabell med alla 21 län
```

---

## Filändringar

### 1. `surfsense_backend/app/services/scb_service.py` — Ny metod

```python
# Nytt: JSON-stat2 dekoder
def decode_jsonstat2(self, response: dict, *, max_rows: int = 100) -> dict[str, Any]:
    """Dekoda JSON-stat2 till markdown-tabell med metadata."""

# Nytt: Hämta defaultselection
async def get_default_selection(self, table_id: str) -> dict[str, list[str]]:
    """GET /tables/{id}/defaultselection"""

# Nytt: Hämta codelist
async def get_codelist(self, codelist_id: str) -> dict[str, Any]:
    """GET /codelists/{id}"""

# Nytt: Auto-complete selection
def auto_complete_selection(
    self, metadata: dict, selection: dict[str, list[str]],
    default_selection: dict[str, list[str]] | None = None
) -> tuple[dict[str, list[str]], list[str]]:
    """Fyll i saknade variabler med elimination-defaults."""

# Nytt: Navigera v1-träd
async def browse_tree(self, path: str = "") -> list[dict[str, Any]]:
    """GET /ssd/{path} via v1 API — returnerar noder och tabeller."""
```

### 2. `surfsense_backend/app/agents/new_chat/tools/scb_llm_tools.py` — Ersätt/utöka

Ersätt de 3 nuvarande verktygen med 5 nya:
- `scb_search` (renare version av scb_search_and_inspect)
- `scb_browse` (NYTT — trädnavigering)
- `scb_inspect` (renare version av inspect-delen)
- `scb_fetch` (KRAFTIGT förbättrad — auto-complete + dekoder)
- `scb_codelist` (NYTT — kodlistor)

### 3. `surfsense_backend/app/agents/new_chat/statistics_prompts.py` — Uppdaterat prompt

Nytt systemprompt som beskriver 5-stegs-flödet med fokus på:
- "Du har 5 verktyg: search, browse, inspect, fetch, codelist"
- "Du behöver INTE specificera alla variabler — saknade auto-fylls"
- "Använd TOP(n), FROM(x), RANGE(x,y) istället för att lista år"
- "Data returneras som läsbar tabell — citera direkt"

### 4. `surfsense_backend/app/agents/new_chat/tools/registry.py` — Registrera nya verktyg

Lägg till de 5 verktygen i `BUILTIN_TOOLS`.

### 5. `surfsense_backend/app/agents/new_chat/statistics_agent.py` — Uppdatera agent

Uppdatera `create_statistics_agent` för att inkludera nya verktyg.

---

## Auto-complete-logik (detaljerad)

```python
def auto_complete_selection(
    metadata: dict,
    selection: dict[str, list[str]],
    default_selection: dict[str, list[str]] | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """
    För varje variabel i metadata som INTE finns i selection:

    1. Om variabeln har elimination=true OCH eliminationValueCode finns:
       → Använd [eliminationValueCode]
       → Logga: "Alder: auto-fylld med 'tot' (eliminable)"

    2. Om variabeln har elimination=true men INTE eliminationValueCode:
       → Kolla defaultselection
       → Om det finns: använd defaultselection-värdet
       → Annars: Sök efter "tot", "total", "alla" bland values
       → Sista utväg: Använd ["*"] (alla värden)
       → Logga: "Civilstand: auto-fylld med '*' (alla, eliminable)"

    3. Om variabeln har elimination=false:
       → Kolla defaultselection
       → Om det finns: använd defaultselection-värdet
       → Annars: Använd första värdet
       → Logga varning: "ContentsCode: auto-fylld med 'BE0101N1' (ej eliminable, kontrollera!)"

    Returnera: (komplett_selection, lista_av_loggrader)
    """
```

---

## Trunkerings- och storleksstrategi

```
Cellantal < 5 000     → Returnera allt (max 100 rader i tabellen)
Cellantal 5 000-50 000 → Returnera, men trunkera till 50 rader + sammanfattning
Cellantal 50 000-150k  → Varna, föreslå snävare urval, men kör om LLM insisterar
Cellantal > 150 000    → NEKA med förklaring + förslag på hur man minskar
```

---

## Test-scenarier

| # | Fråga | Förväntat flöde | Verifierar |
|---|-------|-----------------|------------|
| 1 | "Befolkning Stockholm 2024" | search → inspect → fetch | Grundflödet |
| 2 | "Befolkning alla län senaste 5 åren" | search → inspect → fetch med codelist + TOP(5) | Codelist + v2-uttryck |
| 3 | "Vad finns det för hälsostatistik?" | browse("") → browse("HE") | Trädnavigering |
| 4 | "BNP-tillväxt kvartal 2020-2024" | search → inspect → fetch med RANGE | Kvartalsdata + RANGE |
| 5 | Bara ContentsCode + Tid, resten utelämnat | Auto-complete alla eliminable | Auto-complete |
| 6 | Felaktig regionkod "stockholm" | Fuzzy match → 0180 | Felhantering |
| 7 | >150k celler (alla kommuner × alla åldrar × alla år) | NEKA med förslag | Cellgräns |
| 8 | Tabell med status ".." (sekretess) | Visa ".." i tabell | Missing data |
| 9 | "Medianinkomst 25-64 år per kommun" | search → inspect → fetch med codelist | Inkomstdata |
| 10 | Månad/kvartaldata med "2024M06" | Korrekt tidsformat | Tidsformat |

---

## Sammanfattning: Varför detta är perfekt

1. **JSON-stat2 dekodas till läsbar tabell** → LLM:en kan faktiskt läsa datan
2. **Auto-complete eliminerar den vanligaste felkällan** → saknade variabler
3. **v2-uttryck (TOP, RANGE, FROM)** → enklare queries, inga gissade årtal
4. **Kodlistor** → "alla län" utan att lista 21 koder
5. **Trädnavigering** → explorativa frågor fungerar
6. **Rich metadata** → enhet, referensperiod, fotnoter i varje svar
7. **Trunkeringslogik** → fungerar med stora dataset utan att spränga context
8. **Behåller 47 domänverktyg** → routingen som redan funkar rörs inte
