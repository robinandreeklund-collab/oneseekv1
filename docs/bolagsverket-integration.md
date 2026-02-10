# Bolagsverket Open Data API (v2.0) – OnSeek Integration

Denna guide beskriver hur Bolagsverket Open Data API (v2.0) är integrerad i OnSeek via `langgraph-bigtool`.
Syftet är att ge snabba, fokuserade verktyg för bolagsdata utan att explodera kontexten.

## Översikt

- **Namespace:** `tools/bolag/bolagsverket_*`
- **Autentisering:** `X-Api-Key` via `BOLAGSVERKET_API_KEY`
- **Caching:** Redis TTL 1 dag (för GET‑anrop)
- **Rate‑limit:** Exponentiell backoff vid 429 (retry)
- **Citations:** Alla verktyg ingestas som `TOOL_OUTPUT` för citat med `chunk_id`

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

Lägg till i `.env`:

```
BOLAGSVERKET_API_KEY="..."
```

Redis används om `REDIS_APP_URL` är satt. Om Redis saknas körs verktygen utan cache.

## Kodpekare

- Service: `app/services/bolagsverket_service.py`
- Tools: `app/agents/new_chat/tools/bolagsverket.py`
- Registry: `app/agents/new_chat/tools/registry.py`
- Bigtool metadata: `app/agents/new_chat/bigtool_store.py`
