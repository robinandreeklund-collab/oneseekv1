# Implementeringsplan: Riksbank API, Elpris API & Bolagsverket-analys

## Sammanfattning

Tre uppgifter:
1. **Riksbank API** — Ny integration med 3 API:er (SWEA, SWESTR, Prognoser), placeras i domän `ekonomi-och-skatter`
2. **Elpris API** — Ny integration med elprisetjustnu.se, placeras i domän `energi-och-miljö`
3. **Bolagsverket API** — Analys av nuvarande integration (ingen kodning)

---

## 1. Riksbank API Integration

### 1.1 API-översikt (3 API:er)

| API | Bas-URL | Beskrivning |
|-----|---------|-------------|
| **SWEA** | `api.riksbank.se/swea/v1/` | Räntor (~60 serier) och växelkurser (~50 serier) |
| **SWESTR** | `api.riksbank.se/swestr/v1/` | Svensk dagslåneränta (referensränta) |
| **Prognoser** | `api.riksbank.se/forecasts/v1/` | Makroekonomiska prognoser och utfall (från 2020) |

**Autentisering:** Valfritt. Utan API-nyckel: 5 anrop/min, 1000/dag. Med nyckel (Ocp-Apim-Subscription-Key): 200 anrop/min, 30 000/vecka.

### 1.2 Filer att skapa

| Fil | Beskrivning |
|-----|-------------|
| `surfsense_backend/app/services/riksbank_service.py` | Kärntjänst: HTTP-klient, endpoints för SWEA/SWESTR/Prognoser |
| `surfsense_backend/app/agents/new_chat/tools/riksbank.py` | Verktygsimplementationer + definitioner |
| `surfsense_backend/tests/test_riksbank_service.py` | Enhets- och integrationstester |
| `docs/API/Riksbank.md` | Fullständig dokumentation (SCB-format) |

### 1.3 RiksbankService (kärntjänst)

```python
class RiksbankService:
    # SWEA endpoints
    async def get_interest_rate_latest(self, series_id: str) -> dict
    async def get_interest_rates_by_group(self, group_id: str) -> dict
    async def get_interest_rate_observations(self, series_id: str, start: str, end: str) -> dict
    async def get_exchange_rate_latest(self, series_id: str) -> dict
    async def get_exchange_rates_by_group(self, group_id: str) -> dict
    async def get_exchange_rate_observations(self, series_id: str, start: str, end: str) -> dict
    async def get_cross_rates(self, series1: str, series2: str, from_date: str) -> dict
    async def list_series(self) -> dict
    async def list_groups(self) -> dict

    # SWESTR endpoints
    async def get_swestr_latest(self) -> dict
    async def get_swestr_observations(self, from_date: str, to_date: str) -> dict
    async def get_swestr_average(self, from_date: str, to_date: str) -> dict

    # Prognoser endpoints
    async def get_forecasts(self, indicator: str | None = None) -> dict
    async def get_forecast_indicators(self) -> dict
```

Features: persistent httpx.AsyncClient, circuit breaker, retry med exponential backoff, Redis-cache (TTL 1h för räntor, 24h för metadata).

### 1.4 Verktyg (8 st, grupperade)

| Tool ID | Namn | API | Beskrivning |
|---------|------|-----|-------------|
| `riksbank_ranta_styrranta` | Riksbanken Styrränta | SWEA | Aktuell styrränta och historik |
| `riksbank_ranta_marknadsrantor` | Riksbanken Marknadsräntor | SWEA | Statsobligationsräntor, STIBOR, bostadsräntor |
| `riksbank_valuta_kurser` | Riksbanken Valutakurser | SWEA | SEK-kurser mot alla valutor |
| `riksbank_valuta_korsrantor` | Riksbanken Korsräntor | SWEA | Cross-rates mellan valfria valutor |
| `riksbank_swestr` | Riksbanken SWESTR | SWESTR | Svensk dagslåneränta (referensränta) |
| `riksbank_prognos_inflation` | Riksbanken Inflationsprognos | Prognoser | KPI, KPIF-prognoser |
| `riksbank_prognos_bnp` | Riksbanken BNP-prognos | Prognoser | BNP-prognoser och utfall |
| `riksbank_prognos_ovrigt` | Riksbanken Makroprognoser | Prognoser | Arbetslöshet, repo-prognos, etc. |

### 1.5 Agent- och Domänkonfiguration

**Ny agent i `agent_definitions.py`:**
```python
{
    "agent_id": "riksbank-ekonomi",
    "domain_id": "ekonomi-och-skatter",
    "label": "Riksbanken Räntor, Valutor & Prognoser",
    "keywords": ["riksbanken", "styrränta", "ränta", "valutakurs", "sek", "swestr",
                 "inflationsprognos", "bnp-prognos", "växelkurs", "stibor"],
    "primary_namespaces": [["tools", "riksbank", "ekonomi"]],
    "fallback_namespaces": [["tools", "riksbank"]],
}
```

**Uppdatera `intent_domains.py` — `ekonomi-och-skatter`:**
Lägg till keywords: `"styrränta"`, `"växelkurs"`, `"valutakurs"`, `"sek"`, `"swestr"`, `"stibor"`, `"reporänta"`, `"dagslåneränta"`, `"penningpolitik"`, `"valuta"`

Uppdatera description att inkludera "riksbankens räntor, valutakurser, prognoser".

### 1.6 Registrering

- Registrera verktyg i `registry.py` (BUILTIN_TOOLS)
- Registrera i `bigtool_store.py` med korrekta namespaces
- Lägg till i `tool_identity_defaults.py`

### 1.7 Testsvit

~20-30 tester:
- Unit: HTTP-mocking, cache, retry, circuit breaker
- Verktygsval: scoring och retrieval
- Integration: mock-data mot endpoints

---

## 2. Elpris API Integration

### 2.1 API-översikt

| Endpoint | URL-mönster | Beskrivning |
|----------|-------------|-------------|
| JSON dagspriser | `elprisetjustnu.se/api/v1/prices/{YYYY}/{MM-DD}_{ZONE}.json` | Spotpriser per 15-min (sedan okt 2025) |
| RSS-feed | `elprisetjustnu.se/rss/prices/{ZONE}` | RSS-flöde |

**Priszoner:** SE1 (Luleå), SE2 (Sundsvall), SE3 (Stockholm), SE4 (Malmö)
**Autentisering:** Ingen krävs. Helt öppet API.
**Data:** SEK_per_kWh, EUR_per_kWh, EXR, time_start, time_end. Exkl moms/avgifter.
**Historik:** Från 2022-11-01.

### 2.2 Filer att skapa

| Fil | Beskrivning |
|-----|-------------|
| `surfsense_backend/app/services/elpris_service.py` | HTTP-klient, prisinhämtning, aggregering |
| `surfsense_backend/app/agents/new_chat/tools/elpris.py` | Verktygsimplementationer + definitioner |
| `surfsense_backend/tests/test_elpris_service.py` | Tester |
| `docs/API/Elpris.md` | Fullständig dokumentation (SCB-format) |

### 2.3 ElprisService

```python
class ElprisService:
    async def get_prices(self, date: str, zone: str) -> list[dict]
    async def get_prices_range(self, start: str, end: str, zone: str) -> list[dict]
    async def get_today_prices(self, zone: str) -> list[dict]
    async def get_tomorrow_prices(self, zone: str) -> list[dict]  # Finns efter 13:00
    async def get_average_price(self, date: str, zone: str) -> dict
    async def get_price_comparison(self, date: str) -> dict  # Alla zoner
```

Features: persistent httpx.AsyncClient, cache (TTL 15 min för idag, 24h för historik), prisaggregering (min/max/medel per dag).

### 2.4 Verktyg (4 st)

| Tool ID | Namn | Beskrivning |
|---------|------|-------------|
| `elpris_idag` | Elpris Idag | Dagens elpriser per zon (15-min intervall) |
| `elpris_imorgon` | Elpris Imorgon | Morgondagens priser (tillgängliga efter 13:00) |
| `elpris_historik` | Elpris Historik | Historiska priser för ett datum/period |
| `elpris_jamforelse` | Elpris Zonjämförelse | Jämför priser mellan alla 4 zoner |

### 2.5 Agent- och Domänkonfiguration

**Ny agent i `agent_definitions.py`:**
```python
{
    "agent_id": "elpris",
    "domain_id": "energi-och-miljö",
    "label": "Elpriser & Spotpriser",
    "keywords": ["elpris", "elpriser", "spotpris", "kwh", "elzon", "se1", "se2",
                 "se3", "se4", "elområde", "elavtal", "timpris", "elmarknad"],
    "primary_namespaces": [["tools", "elpris", "energi"]],
    "fallback_namespaces": [["tools", "elpris"]],
}
```

**Uppdatera `intent_domains.py` — `energi-och-miljö`:**
Lägg till keywords: `"elpris"`, `"elpriser"`, `"spotpris"`, `"kwh"`, `"elzon"`, `"elområde"`, `"timpris"`, `"elmarknad"`, `"elräkning"`, `"elavtal"`

Uppdatera description att inkludera "aktuella elpriser, spotpriser och elmarknadsdata".

### 2.6 Registrering

Samma mönster som Riksbank — registrera i registry, bigtool_store, tool_identity_defaults.

### 2.7 Testsvit

~15-20 tester: mock HTTP, cache, zonvalidering, prisaggregering.

---

## 3. Bolagsverket API — Analys (INGEN KODNING)

### 3.1 Nuvarande integration

**Bas-URL:** `https://gw.api.bolagsverket.se/vardefulla-datamangder/v1`

Nuvarande `BolagsverketService` använder API:t för **Värdefulla datamängder** (gratis, öppet API). Lanserat 2025-02-03 enligt EU-krav.

### 3.2 Vad gratis-API:t faktiskt erbjuder

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `isalive` | GET | Health check |
| `organisationer` | POST | Sök organisation per orgnr (JSON body) |
| `dokumentlista` | POST | Lista dokument för organisation |
| `dokument/{id}` | GET | Hämta specifikt dokument |

**Data som inkluderas:**
- Organisationsnamn, juridisk form, adresser, SNI-koder
- Verksamhetsbeskrivning, aktiekapital, firmateckning
- Funktionärer (styrelse, VD)
- F-skatt, moms, arbetsgivarstatus
- Digitalt inlämnade årsredovisningar (från 2020+)

**Begränsningar:**
- Sök **enbart** på organisationsnummer — ingen namnsökning!
- Ingen personsökning
- Inga ärendeuppgifter
- Ingen aktiekapitalhistorik
- Rate limit: 60 anrop/min
- Autentisering: OAuth 2.0 (gratis credentials, bara email + telefon)

### 3.3 Problem med nuvarande integration

**Kritiska problem:**

1. **18 verktyg exponeras — men bara 3 endpoints finns i gratis-API:t.** Verktygen `bolagsverket_info_basic`, `bolagsverket_info_status`, `bolagsverket_info_adress`, `bolagsverket_styrelse_*`, `bolagsverket_registrering_*` kallar alla `get_organisationer()` som returnerar **samma data** oavsett verktyg. Det finns ingen specifik endpoint för styrelse, ägare, firmatecknare, F-skatt, moms, konkurs, bokslut, nyckeltal.

2. **Sökning fungerar inte som verktyget antyder.** `bolagsverket_sok_namn`, `_bransch`, `_region`, `_status` anropar alla `get_organisationer()` med olika payload-format, men gratis-API:t stöder troligen bara organisationsnummer-sökning.

3. **Ekonomi-verktyg (bokslut, årsredovisning, nyckeltal) returnerar dokumentlista**, inte faktisk finansiell data. `get_financial_statements()`, `get_annual_reports()`, `get_key_ratios()` returnerar alla `get_dokumentlista()` — dvs en lista av dokumentreferenser, inte strukturerad finansdata.

4. **Ägare-verktyg (`get_owners`) finns inte** i gratis-API:t. Det anropar `get_organisationer()` som inte returnerar ägardata.

### 3.4 Vad betalda API:t hade erbjudit (men saknas)

| Funktion | Gratis | Betald |
|----------|--------|--------|
| Sök på namn | Nej | Ja |
| Sök på person | Nej | Ja |
| Ärendedata | Nej | Ja |
| Aktiekapitalhistorik | Nej | Ja (från 2003) |
| Detaljerade engagemang | Nej | Ja |
| Testmiljö | Nej | Ja |
| Strukturerad finansdata | Nej (bara dokument) | Ja |

### 3.5 Rekommendation

**Kortsiktigt (utan betalt API):**
1. Reducera till ~6 verktyg som faktiskt matchar gratis-API:ts möjligheter:
   - `bolagsverket_sok_orgnr` — Sök organisation (POST organisationer)
   - `bolagsverket_info_grunddata` — Grunddata (namn, form, SNI, adress, styrelse, allt i ett)
   - `bolagsverket_dokument_lista` — Lista dokument/årsredovisningar
   - `bolagsverket_dokument_hamta` — Hämta specifikt dokument
   - `bolagsverket_funktionarer` — Styrelse/VD (extrahera från organisationer-svaret)
   - `bolagsverket_registrering` — F-skatt/moms/arbetsgivare-status (extrahera från organisationer-svaret)

2. Ta bort vilseledande verktyg (sok_namn, sok_bransch, sok_region, ekonomi_nyckeltal, styrelse_agarstruktur) som inte fungerar korrekt.

3. Uppdatera verktygsbeskrivningar så de korrekt beskriver vad som returneras.

**Långsiktigt (med betalt API):**
- Uppgradera till betalda API:t för fullständig funktionalitet
- Kräver avtal med Bolagsverket + månadskostnad
- Ger namnbaserad sökning, persondata, detaljerad finansdata

---

## 4. Arbetsordning

### Fas 1: Riksbank (störst scope)
1. Skapa `riksbank_service.py` med alla 3 API:er
2. Skapa `tools/riksbank.py` med 8 verktyg
3. Uppdatera `intent_domains.py` — ekonomi-och-skatter keywords
4. Lägg till agent `riksbank-ekonomi` i `agent_definitions.py`
5. Registrera verktyg i registry, bigtool_store, tool_identity_defaults
6. Skapa tester `test_riksbank_service.py`
7. Skapa dokumentation `docs/API/Riksbank.md`

### Fas 2: Elpris (mindre scope)
1. Skapa `elpris_service.py`
2. Skapa `tools/elpris.py` med 4 verktyg
3. Uppdatera `intent_domains.py` — energi-och-miljö keywords
4. Lägg till agent `elpris` i `agent_definitions.py`
5. Registrera verktyg
6. Skapa tester `test_elpris_service.py`
7. Skapa dokumentation `docs/API/Elpris.md`

### Fas 3: Bolagsverket (ingen kodning)
- Dokumentation `docs/API/Bolagsverket.md` med analys och rekommendationer

---

## 5. Berörda filer (sammanfattning)

### Nya filer
- `surfsense_backend/app/services/riksbank_service.py`
- `surfsense_backend/app/agents/new_chat/tools/riksbank.py`
- `surfsense_backend/app/services/elpris_service.py`
- `surfsense_backend/app/agents/new_chat/tools/elpris.py`
- `surfsense_backend/tests/test_riksbank_service.py`
- `surfsense_backend/tests/test_elpris_service.py`
- `docs/API/Riksbank.md`
- `docs/API/Elpris.md`
- `docs/API/Bolagsverket.md`

### Ändrade filer
- `surfsense_backend/app/seeds/intent_domains.py` — Nya keywords för ekonomi + energi
- `surfsense_backend/app/seeds/agent_definitions.py` — 2 nya agenter
- `surfsense_backend/app/agents/new_chat/tools/registry.py` — Registrering
- `surfsense_backend/app/agents/new_chat/bigtool_store.py` — Namespace-registrering
- `surfsense_backend/app/agents/new_chat/tool_identity_defaults.py` — Metadata
