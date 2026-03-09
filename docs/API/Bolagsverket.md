# Bolagsverket API — Analys och Rekommendationer

## Nuvarande integration

**Bas-URL:** `https://gw.api.bolagsverket.se/vardefulla-datamangder/v1`

Nuvarande `BolagsverketService` använder API:t för **Värdefulla datamängder** — ett gratis, öppet API lanserat 2025-02-03 enligt EU-krav.

## Vad gratis-API:t faktiskt erbjuder

### Tillgängliga endpoints

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `isalive` | GET | Health check |
| `organisationer` | POST | Sök organisation per orgnr (JSON body) |
| `dokumentlista` | POST | Lista dokument för organisation |
| `dokument/{id}` | GET | Hämta specifikt dokument |

### Data som inkluderas

- Organisationsnamn, juridisk form, adresser, SNI-koder
- Verksamhetsbeskrivning, aktiekapital, firmateckning
- Funktionärer (styrelse, VD)
- F-skatt, moms, arbetsgivarstatus
- Digitalt inlämnade årsredovisningar (från 2020+)

### Begränsningar

- Sök **enbart** på organisationsnummer — ingen namnsökning
- Ingen personsökning
- Inga ärendeuppgifter
- Ingen aktiekapitalhistorik
- Rate limit: 60 anrop/min
- Autentisering: OAuth 2.0 (gratis credentials)

## Problem med nuvarande integration

### Kritiska problem

#### 1. 18 verktyg — men bara 3 endpoints
Verktygen `bolagsverket_info_basic`, `bolagsverket_info_status`, `bolagsverket_info_adress`, `bolagsverket_styrelse_*`, `bolagsverket_registrering_*` kallar alla `get_organisationer()` som returnerar **samma data** oavsett verktyg.

#### 2. Sökning fungerar inte som verktyget antyder
`bolagsverket_sok_namn`, `_bransch`, `_region`, `_status` anropar alla `get_organisationer()`, men API:t stöder **bara organisationsnummer-sökning**.

#### 3. Ekonomi-verktyg returnerar dokumentlista — inte finansdata
`get_financial_statements()`, `get_annual_reports()`, `get_key_ratios()` returnerar alla `get_dokumentlista()` — en lista av dokumentreferenser, inte strukturerad finansdata.

#### 4. Ägare-verktyg saknar API-stöd
`get_owners` anropar `get_organisationer()` som inte returnerar ägardata.

## Rekommendation

### Kortsiktigt (utan betalt API)

Reducera till **6 verktyg** som matchar gratis-API:ts faktiska möjligheter:

| Tool ID | Beskrivning |
|---------|-------------|
| `bolagsverket_sok_orgnr` | Sök organisation via organisationsnummer |
| `bolagsverket_info_grunddata` | Grunddata (namn, form, SNI, adress, styrelse) |
| `bolagsverket_dokument_lista` | Lista dokument/årsredovisningar |
| `bolagsverket_dokument_hamta` | Hämta specifikt dokument |
| `bolagsverket_funktionarer` | Styrelse/VD (extraherat från organisationer-svaret) |
| `bolagsverket_registrering` | F-skatt/moms/arbetsgivare (extraherat) |

**Bör tas bort:**
- `bolagsverket_sok_namn` — gratis-API:t stöder inte namnsökning
- `bolagsverket_sok_bransch` — gratis-API:t stöder inte branschsökning
- `bolagsverket_sok_region` — gratis-API:t stöder inte regionssökning
- `bolagsverket_sok_status` — gratis-API:t stöder inte statussökning
- `bolagsverket_ekonomi_nyckeltal` — returnerar dokumentlista, inte nyckeltal
- `bolagsverket_styrelse_agarstruktur` — ägardata finns inte i API:t
- Alla dubbletter som kallar samma endpoint med olika namn

### Långsiktigt (med betalt API)

| Funktion | Gratis | Betald |
|----------|--------|--------|
| Sök på namn | Nej | Ja |
| Sök på person | Nej | Ja |
| Ärendedata | Nej | Ja |
| Aktiekapitalhistorik | Nej | Ja (från 2003) |
| Detaljerade engagemang | Nej | Ja |
| Testmiljö | Nej | Ja |
| Strukturerad finansdata | Nej (bara dokument) | Ja |

## Filer

| Fil | Beskrivning |
|-----|-------------|
| `surfsense_backend/app/services/bolagsverket_service.py` | HTTP-klient |
| `surfsense_backend/app/agents/new_chat/tools/bolagsverket.py` | Verktyg (18 st → bör reduceras till 6) |
