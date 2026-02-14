# Kolada API Integration

## Översikt

Kolada API (v3) är integrerad i OnSeek-systemet som ett statistikverktyg under samma `statistics`-intent som SCB. Integrationen ger tillgång till kommunala nyckeltal (KPIs) från svenska kommuner och regioner.

**Base URL:** `https://api.kolada.se/v3`

## Arkitektur

Kolada-integrationen följer exakt samma mönster som SCB-integrationen:

```
KoladaService (kolada_service.py)
    ↓
KoladaToolDefinitions (kolada_tools.py)
    ↓
bigtool_store.py (namespace mapping + TOOL_KEYWORDS)
    ↓
supervisor_agent.py (statistics agent routing)
```

## Verktyg

Systemet innehåller **15 Kolada-verktyg** uppdelade i kategorier:

### Omsorg (4 verktyg)

| Tool ID | Verksamhetsområde | Beskrivning |
|---------|-------------------|-------------|
| `kolada_aldreomsorg` | V21 | Äldreomsorg - hemtjänst, särskilt boende, kvalitetsindikatorer |
| `kolada_lss` | V23 | LSS - personlig assistans, boende med särskild service |
| `kolada_ifo` | V25 | IFO - ekonomiskt bistånd, familjehem, missbruks- och beroendevård |
| `kolada_barn_unga` | V26 | Barn och unga - placeringar, öppenvård |

### Skola (3 verktyg)

| Tool ID | Verksamhetsområde | Beskrivning |
|---------|-------------------|-------------|
| `kolada_forskola` | V11 | Förskola - antal barn, pedagogtäthet, kostnader |
| `kolada_grundskola` | V15 | Grundskola - elevantal, lärartäthet, behörighet, betyg |
| `kolada_gymnasieskola` | V17 | Gymnasieskola - genomströmning, examen, behörighet |

### Hälsa (1 verktyg)

| Tool ID | Verksamhetsområde | Beskrivning |
|---------|-------------------|-------------|
| `kolada_halsa` | V45 | Hälso- och sjukvård - vårdkostnader, läkarbesök, primärvård |

### Ekonomi/Miljö/Boende (3 verktyg)

| Tool ID | Verksamhetsområde | Beskrivning |
|---------|-------------------|-------------|
| `kolada_ekonomi` | - | Kommunal ekonomi - skattesats, kostnader, intäkter |
| `kolada_miljo` | - | Miljö och klimat - avfall, återvinning, koldioxid |
| `kolada_boende` | - | Boende och bostäder - bostadsbestånd, nybyggnation |

### Övrigt (4 verktyg)

| Tool ID | Verksamhetsområde | Beskrivning |
|---------|-------------------|-------------|
| `kolada_sammanfattning` | - | Allmänna nyckeltal och översikt |
| `kolada_kultur` | - | Kultur och fritid - bibliotek, kulturhus |
| `kolada_arbetsmarknad` | - | Arbetsmarknad - sysselsättning, arbetslöshet |
| `kolada_demokrati` | - | Demokrati och medborgarservice - valdeltagande |

## Runtime-prompts

Varje verktyg har en rik runtime-prompt som inkluderar:

1. **Beskrivning** - Vad verktyget gör
2. **Verksamhetsområde** - V-kod (om tillämpligt)
3. **KPI-ID** - Exempel på relevanta KPI-ID
4. **Parametrar** - Dokumentation med typer och exempel
5. **Exempelfrågor** - 5+ konkreta användningsexempel
6. **Viktigt-sektion** - Edge cases och användningsanvisningar

### Exempel: kolada_aldreomsorg

```
**Beskrivning:** Nyckeltal för äldreomsorg från Kolada. Omfattar hemtjänst, 
särskilt boende, vård och omsorg för äldre samt kvalitetsindikatorer.

**Verksamhetsområde:** V21

**KPI-ID:** N00945, N00946, N00947, N00955, N00956

**Parametrar:**
- `question` (str): Fråga i naturligt språk
- `municipality` (str, optional): Kommun (namn eller 4-siffrig kod)
- `years` (list[str], optional): Lista med år, t.ex. ['2022', '2023', '2024']

**Exempelfrågor:**
- Hemtjänst i Stockholm 2022-2024
- Antal platser särskilt boende Göteborg 2023
- Äldreomsorgskostnader per kommun 2024
- Kvalitetsindikatorer äldreomsorg Malmö 2020-2024
- Andel personer med hemtjänst Uppsala 2023

**Viktigt:**
- Använd för frågor om hemtjänst, särskilt boende, äldreomsorgskostnader.
- Specificera kommun för att få lokala data.
- År kan anges som lista.
- Verktyget hanterar svenska tecken (å, ä, ö) automatiskt.
```

## Parametrar

Alla Kolada-verktyg använder samma parametrar:

| Parameter | Typ | Obligatorisk | Beskrivning | Exempel |
|-----------|-----|--------------|-------------|---------|
| `question` | str | Ja | Fråga i naturligt språk | "Hemtjänst i Stockholm 2023" |
| `municipality` | str | Nej | Kommun (namn eller 4-siffrig kod) | "Stockholm", "0180", "Göteborg", "1480" |
| `years` | list[str] | Nej | Lista med år | ["2022", "2023", "2024"] |
| `max_kpis` | int | Nej | Max antal KPIs att returnera (default: 5) | 5 |

## API-endpoints

### KoladaService Methods

| Method | Endpoint | Beskrivning |
|--------|----------|-------------|
| `search_kpis()` | `/kpi` | Sök KPIs baserat på titel och verksamhetsområde |
| `get_kpi()` | `/kpi/{kpi_id}` | Hämta specifik KPI med ID |
| `resolve_municipality()` | `/municipality/{id}` | Översätt kommunnamn till ID eller validera ID |
| `get_values()` | `/data/kpi/{kpi}/municipality/{muni}` | Hämta data för en KPI och kommun |
| `get_values_multi()` | - | Hämta data för flera KPIs parallellt |
| `query()` | - | High-level convenience method |

### Exempel API-anrop

```python
# Sök KPIs
kpis = await kolada_service.search_kpis(
    "hemtjänst",
    operating_area="V21",
    per_page=50
)

# Hämta specifik KPI
kpi = await kolada_service.get_kpi("N00945")

# Översätt kommunnamn
municipality = await kolada_service.resolve_municipality("Stockholm")
# → KoladaMunicipality(id="0180", title="Stockholm", type="K")

# Hämta data
values = await kolada_service.get_values(
    kpi_id="N00945",
    municipality_id="0180",
    years=["2022", "2023", "2024"]
)

# High-level query
results = await kolada_service.query(
    question="hemtjänst Stockholm",
    operating_area="V21",
    municipality="Stockholm",
    years=["2023"],
    max_kpis=5
)
```

## Rate Limiting och Retry

KoladaService implementerar exponentiell backoff vid HTTP 429 (rate limiting):

- **max_retries**: 3 (default)
- **backoff**: 2^attempt seconds (1s, 2s, 4s)

```python
service = KoladaService(
    base_url="https://api.kolada.se/v3",
    timeout=25.0,
    max_retries=3
)
```

## Caching

KoladaService använder in-memory caching:

- **`_kpi_cache`**: KPI-objekt indexerade per ID
- **`_municipality_cache`**: Kommune-objekt indexerade per ID

Cache är session-baserad och har ingen TTL.

## Kända Kommuner

Service innehåller en uppsättning av 20+ vanliga kommuner för snabb översättning:

```python
_KNOWN_MUNICIPALITIES = {
    "stockholm": "0180",
    "goteborg": "1480",
    "göteborg": "1480",
    "malmo": "1280",
    "malmö": "1280",
    "uppsala": "0380",
    ...
}
```

## Citations och Datakälla

Data från Kolada-verktyg lagras via `connector_service.ingest_tool_output()`:

```python
metadata = {
    "source": "Kolada",
    "operating_area": "V21",
    "municipality": "Stockholm",
    "years": "2022,2023,2024"
}
```

Svaret inkluderar citation till datakällan via `format_documents_for_context()`.

## Jämförelse: SCB vs Kolada

| Aspekt | SCB | Kolada |
|--------|-----|--------|
| **Datakälla** | Nationell statistik | Kommunal statistik |
| **Struktur** | Hierarkisk tabell-struktur | KPI-baserad |
| **Sök** | Breadth-first search i mappar | Direkt KPI-sökning |
| **Filter** | Variabel-baserade selektioner | År + kommun |
| **Coverage** | Hela Sverige, län, kommuner | Kommuner och regioner |
| **Use case** | Nationell statistik, demografi | Kommunal jämförelse, nyckeltal |

## Felsökning

### Problem: Kommun hittas inte

**Symptom:** Varning "Kunde inte hitta kommun: X"

**Lösning:**
- Kontrollera stavning (med och utan å/ä/ö)
- Använd 4-siffrig kommunkod istället (t.ex. "0180" för Stockholm)
- Kolla lista på [kolada.se](https://www.kolada.se)

### Problem: Inga KPIs matchas

**Symptom:** Tom resultatlista

**Lösning:**
- Kontrollera verksamhetsområde (V-kod)
- Bredda sökfrågan
- Testa utan `operating_area`-filter
- Kontrollera att KPI finns i Kolada API

### Problem: Rate limiting

**Symptom:** HTTP 429-fel

**Lösning:**
- Service gör automatisk retry med backoff
- Minska antal parallella anrop
- Öka `max_retries` om nödvändigt

### Problem: Långsam respons

**Symptom:** Timeout-fel

**Lösning:**
- Minska `max_kpis`
- Begränsa `years`-listan
- Öka `timeout` (default 25s)

## Exempelfrågor

### Äldreomsorg

```
"Hur många personer har hemtjänst i Stockholm 2023?"
"Jämför äldreomsorgskostnader mellan Göteborg och Malmö 2020-2024"
"Antal platser i särskilt boende Uppsala"
```

### Skola

```
"Behöriga lärare i grundskolan per kommun 2024"
"Genomströmning gymnasieskola Linköping 2022-2024"
"Kostnader per barn i förskola Stockholm 2023"
```

### Ekonomi

```
"Skattesats i svenska kommuner 2024"
"Kommunala kostnader Umeå senaste 5 åren"
"Jämför ekonomiska nyckeltal Skåne-kommuner"
```

### Miljö

```
"Återvinningsgrad per kommun 2023"
"Koldioxidutsläpp Göteborg 2015-2024"
"Avfallsmängd per invånare Stockholm"
```

## Teknisk Implementation

### Namespace Mapping

Kolada-verktyg mappas till namespaces baserat på kategori:

```python
kolada_aldreomsorg → ("tools", "statistics", "kolada", "omsorg")
kolada_forskola → ("tools", "statistics", "kolada", "skola")
kolada_halsa → ("tools", "statistics", "kolada", "halsa")
kolada_ekonomi → ("tools", "statistics", "kolada", "ekonomi")
```

### TOOL_KEYWORDS

Varje verktyg har keywords med både å/ä/ö-varianter:

```python
"kolada_aldreomsorg": [
    "aldreomsorg", "äldreomsorg",
    "hemtjanst", "hemtjänst",
    "sarskilt", "särskilt",
    "kolada"
]
```

### Tool Retrieval

Verktyg hämtas via `build_global_tool_registry()` som:

1. Bygger standard tools
2. Bygger SCB tools
3. Bygger Kolada tools ← **NYT**
4. Mergar till global registry

## Tester

Tester finns i:

- **`tests/test_kolada_service.py`** - Service-metoder, caching, retry, error-handling
- **`tests/test_kolada_tools.py`** - Tool definitions, builders, registry, store
- **`tests/test_kolada_bigtool_integration.py`** - Namespace mapping, keywords, integration

Kör tester:

```bash
cd surfsense_backend
pytest tests/test_kolada_service.py -v
pytest tests/test_kolada_tools.py -v
pytest tests/test_kolada_bigtool_integration.py -v
```

## Referenser

- [Kolada API v3 Documentation](https://www.kolada.se)
- [SCB Integration](./bolagsverket-integration.md)
- [Supervisor Architecture](./supervisor-architecture.md)
