# Bolagsverket API – OnSeek Integration

Denna guide beskriver hur Bolagsverket‑API:er är integrerade i OnSeek via `langgraph-bigtool`.
Syftet är att ge snabba, fokuserade verktyg för bolagsdata utan att explodera kontexten.

## Översikt

- **Namespace:** `tools/bolag/bolagsverket_*`
- **Autentisering:**  
  - `X-Api-Key` via `BOLAGSVERKET_API_KEY`, eller  
  - `Ocp-Apim-Subscription-Key` via `BOLAGSVERKET_SUBSCRIPTION_KEY`, eller  
  - OAuth2 client credentials via `BOLAGSVERKET_CLIENT_ID` + `BOLAGSVERKET_CLIENT_SECRET`  
- **Caching:** Redis TTL 1 dag (för GET‑anrop)
- **Rate‑limit:** Exponentiell backoff vid 429 (retry)
- **Citations:** Alla verktyg ingestas som `TOOL_OUTPUT` för citat med `chunk_id`

## Endpoint‑varianter

OnSeek stödjer två varianter (styrt av `BOLAGSVERKET_BASE_URL`):

### 1) Värdefulla datamängder (gateway)
- **Base URL:** `https://gw.api.bolagsverket.se/vardefulla-datamangder/v1`
- **Endpoints:**
  - `GET /isalive`
  - `POST /organisationer`
  - `POST /dokumentlista`
  - `GET /dokument/{dokumentId}`

### 2) Open Data API (v2)
- **Base URL:** `https://api.bolagsverket.se/open-data/v2`
- **Endpoints:** `/foretag/...` m.fl.

## Namespace‑struktur

- `tools/bolag/bolagsverket_info` – grunddata, status, adress  
- `tools/bolag/bolagsverket_sok` – namn-, orgnr-, bransch- och regionsök  
- `tools/bolag/bolagsverket_ekonomi` – bokslut, årsredovisningar, nyckeltal  
- `tools/bolag/bolagsverket_styrelse` – ägare, styrelse, firmatecknare  
- `tools/bolag/bolagsverket_registrering` – F‑skatt, moms, konkurs, ändringar  

## Verktyg (18 st)

### Info
1. **bolagsverket_info_basic**  
   - Grunddata om företag (namn, orgnr, form, registreringsdatum)  
   - Base path: `/foretag/{orgnr}`

2. **bolagsverket_info_status**  
   - Status (aktivt, vilande, avvecklat)  
   - Base path: `/foretag/{orgnr}/status`

3. **bolagsverket_info_adress**  
   - Registrerad adress och kontakt  
   - Base path: `/foretag/{orgnr}/adress`

### Sök
4. **bolagsverket_sok_namn**  
   - Sök bolag på namn  
   - Base path: `/foretag?namn=`

5. **bolagsverket_sok_orgnr**  
   - Sök bolag på orgnr  
   - Base path: `/foretag?orgnr=`

6. **bolagsverket_sok_bransch**  
   - Sök bolag på SNI/bransch  
   - Base path: `/foretag?sni=`

7. **bolagsverket_sok_region**  
   - Sök bolag på län/region  
   - Base path: `/foretag?lan=`

8. **bolagsverket_sok_status**  
   - Sök bolag på status  
   - Base path: `/foretag?status=`

### Ekonomi
9. **bolagsverket_ekonomi_bokslut**  
   - Bokslut per år  
   - Base path: `/foretag/{orgnr}/bokslut`

10. **bolagsverket_ekonomi_arsredovisning**  
   - Årsredovisningar  
   - Base path: `/foretag/{orgnr}/arsredovisning`

11. **bolagsverket_ekonomi_nyckeltal**  
   - Nyckeltal (omsättning, resultat, soliditet)  
   - Base path: `/foretag/{orgnr}/nyckeltal`

### Styrelse / Ägare
12. **bolagsverket_styrelse_ledning**  
   - Styrelse och ledning  
   - Base path: `/foretag/{orgnr}/styrelse`

13. **bolagsverket_styrelse_agarstruktur**  
   - Ägare / ägarstruktur  
   - Base path: `/foretag/{orgnr}/agare`

14. **bolagsverket_styrelse_firmatecknare**  
   - Firmatecknare  
   - Base path: `/foretag/{orgnr}/firmatecknare`

### Registrering
15. **bolagsverket_registrering_fskatt**  
   - F‑skattestatus  
   - Base path: `/foretag/{orgnr}/fskatt`

16. **bolagsverket_registrering_moms**  
   - Momsregistrering  
   - Base path: `/foretag/{orgnr}/moms`

17. **bolagsverket_registrering_konkurs**  
   - Konkursstatus  
   - Base path: `/foretag/{orgnr}/konkurs`

18. **bolagsverket_registrering_andringar**  
   - Ändringshistorik  
   - Base path: `/foretag/{orgnr}/andringar`

## Exempel på flöde

1. **User:** “Har bolaget 556703‑7485 F‑skatt?”  
2. **Supervisor:** väljer `bolag`‑agent  
3. **Tool:** `bolagsverket_registrering_fskatt(orgnr="556703-7485")`  
4. **Svar:** returneras med citat via `TOOL_OUTPUT`

## Konfiguration

Lägg till i `.env` (välj ett av alternativen):

**Base URL (gateway eller open data):**
```
BOLAGSVERKET_BASE_URL="https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"
```

**Alternativ A – API‑nyckel**
```
BOLAGSVERKET_API_KEY="..."
```

**Alternativ B – API‑gateway subscription key**
```
BOLAGSVERKET_SUBSCRIPTION_KEY="..."
```

**Alternativ C – Client credentials**
```
BOLAGSVERKET_CLIENT_ID="..."
BOLAGSVERKET_CLIENT_SECRET="..."
BOLAGSVERKET_TOKEN_URL="..."
# (valfritt)
BOLAGSVERKET_SCOPE=""
```

**Tvinga OAuth även mot gateway (valfritt)**
```
BOLAGSVERKET_USE_OAUTH=TRUE
```

Redis används om `REDIS_APP_URL` är satt. Om Redis saknas körs verktygen utan cache.

## Kodpekare

- Service: `app/services/bolagsverket_service.py`
- Tools: `app/agents/new_chat/tools/bolagsverket.py`
- Registry: `app/agents/new_chat/tools/registry.py`
- Bigtool metadata: `app/agents/new_chat/bigtool_store.py`
