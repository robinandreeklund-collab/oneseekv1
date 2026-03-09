# Riksbank API Integration

## Översikt

Integration med tre av Riksbankens REST-API:er:

| API | Bas-URL | Beskrivning |
|-----|---------|-------------|
| **SWEA** | `api.riksbank.se/swea/v1/` | Räntor (~60 serier) och växelkurser (~50 serier) |
| **SWESTR** | `api.riksbank.se/swestr/v1/` | Svensk dagslåneränta (referensränta) |
| **Prognoser** | `api.riksbank.se/forecasts/v1/` | Makroekonomiska prognoser och utfall (från 2020) |

**Portal:** [developer.api.riksbank.se](https://developer.api.riksbank.se/)
**Kontakt:** API@riksbank.se

## Autentisering

| Nivå | Anrop/min | Daglig/Veckotak |
|------|-----------|-----------------|
| **Anonym** (ingen nyckel) | 5/min | 1 000/dag |
| **Registrerad** (med nyckel) | 200/min | 30 000/vecka |

API-nyckeln skickas via headern `Ocp-Apim-Subscription-Key` eller query-parametern `?subscription-key=<key>`.

Nyckeln konfigureras via miljövariabeln `RIKSBANK_API_KEY`.

## Endpoints

### SWEA API

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/Groups` | GET | Hierarkiskt träd av alla seriegrupper |
| `/Series` | GET | Alla dataserier med metadata |
| `/Observations/Latest/{seriesId}` | GET | Senaste observation för en serie |
| `/Observations/Latest/ByGroup/{groupId}` | GET | Senaste observation per serie i en grupp |
| `/Observations/{seriesId}/{fromDate}/{toDate}` | GET | Observationer i datumintervall |
| `/CrossRates/{seriesId1}/{seriesId2}/{date}` | GET | Korskurs mellan två valutor |

### SWESTR API

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/latest/SWESTR` | GET | Senaste SWESTR-observation |
| `/all/SWESTR?fromDate={date}&toDate={date}` | GET | SWESTR-observationer i datumintervall |

### Prognoser API

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/forecasts?indicator={id}` | GET | Prognoser och utfall |
| `/indicators` | GET | Lista tillgängliga indikatorer |

## Verktyg (8 st)

| Tool ID | Namn | API | Beskrivning |
|---------|------|-----|-------------|
| `riksbank_ranta_styrranta` | Riksbanken Styrränta | SWEA | Aktuell styrränta och historik |
| `riksbank_ranta_marknadsrantor` | Riksbanken Marknadsräntor | SWEA | STIBOR, statsobligationer, bostadsräntor |
| `riksbank_valuta_kurser` | Riksbanken Valutakurser | SWEA | SEK-kurser mot alla valutor |
| `riksbank_valuta_korsrantor` | Riksbanken Korsräntor | SWEA | Cross-rates mellan valfria valutor |
| `riksbank_swestr` | Riksbanken SWESTR | SWESTR | Svensk dagslåneränta |
| `riksbank_prognos_inflation` | Riksbanken Inflationsprognos | Prognoser | KPI, KPIF-prognoser |
| `riksbank_prognos_bnp` | Riksbanken BNP-prognos | Prognoser | BNP-prognoser |
| `riksbank_prognos_ovrigt` | Riksbanken Makroprognoser | Prognoser | Arbetslöshet, reporänteprognos m.m. |

## Agent- och Domänkonfiguration

- **Agent:** `riksbank-ekonomi` i domän `ekonomi-och-skatter`
- **Primära namespaces:** `["tools", "riksbank", "ekonomi"]`
- **Fallback namespaces:** `["tools", "riksbank"]`

## Viktiga serieID:n

| SerieID | Beskrivning |
|---------|-------------|
| `SECBREPOEFF` | Styrränta (reporänta) |
| `SECBDEPOEFF` | Inlåningsränta |
| `SECBLENDEFF` | Utlåningsränta |
| `SECBREFEFF` | Referensränta |
| `SEKEURPMI` | EUR/SEK |
| `SEKUSDPMI` | USD/SEK |

## Gruppkoder

| Grupp | Beskrivning |
|-------|-------------|
| 2 | Riksbankens styrräntor |
| 3 | STIBOR |
| 130 | Valutor mot SEK |
| 131 | Korskurser |

## Dataformat

- **Responsformat:** JSON
- **Datumformat:** `YYYY-MM-DD` (ISO 8601)
- **Numeriska värden:** Decimaltal
- **SWESTR-schema:** rate, date, pctl12_5, pctl87_5, volume, numberOfTransactions, numberOfAgents, publicationTime

## Användningsvillkor

- Fritt att använda utan kostnad
- Öppna data — fritt att anpassa och använda
- **Krav:** Ange alltid "Källa: Sveriges Riksbank"

## Filer

| Fil | Beskrivning |
|-----|-------------|
| `surfsense_backend/app/services/riksbank_service.py` | HTTP-klient med cache |
| `surfsense_backend/app/agents/new_chat/tools/riksbank.py` | Verktygsimplementationer |
| `surfsense_backend/tests/test_riksbank_service.py` | Tester |

## Miljövariabler

| Variabel | Standard | Beskrivning |
|----------|---------|-------------|
| `RIKSBANK_API_KEY` | (tom) | API-nyckel (valfri) |
| `RIKSBANK_SWEA_BASE_URL` | `https://api.riksbank.se/swea/v1` | SWEA bas-URL |
| `RIKSBANK_SWESTR_BASE_URL` | `https://api.riksbank.se/swestr/v1` | SWESTR bas-URL |
| `RIKSBANK_FORECASTS_BASE_URL` | `https://api.riksbank.se/forecasts/v1` | Prognoser bas-URL |
| `RIKSBANK_TIMEOUT` | 15.0 | HTTP timeout (sekunder) |
| `RIKSBANK_CACHE_TTL_RATES` | 3600 | Cache TTL räntor (sekunder) |
| `RIKSBANK_CACHE_TTL_META` | 86400 | Cache TTL metadata (sekunder) |
