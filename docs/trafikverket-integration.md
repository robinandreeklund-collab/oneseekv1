# Trafikverket Open API (v3.0) – OnSeek Integration

Denna guide beskriver Trafikverket Open API‑integrationen (v3.0) i OnSeek.
Målet är realtidsnära trafikdata via fokuserade `langgraph-bigtool`‑verktyg.

## Översikt

- **Namespace:** `tools/trafik/trafikverket_*`
- **Autentisering:** `X-Api-Key` via `TRAFIKVERKET_API_KEY`
- **Caching:** Redis TTL 5 minuter (realtidsdata)
- **Rate‑limit:** Exponentiell backoff vid 429
- **Citations:** TOOL_OUTPUT ingestion för chunk‑citat

## Namespace‑struktur

- `tools/trafik/trafikverket_trafikinfo` – störningar, olyckor, köer, vägarbeten  
- `tools/trafik/trafikverket_tag` – tågförseningar, tidtabeller, stationer, inställda  
- `tools/trafik/trafikverket_vag` – vägstatus, underhåll, hastighet, avstängningar  
- `tools/trafik/trafikverket_vader` – väderstationer, halka, vind, temperatur  
- `tools/trafik/trafikverket_kameror` – kamera‑lista, snapshot, status  
- `tools/trafik/trafikverket_prognos` – trafik, väg och tågprognoser  

## Verktyg (22 st)

### Trafikinfo
1. trafikverket_trafikinfo_storningar  
2. trafikverket_trafikinfo_olyckor  
3. trafikverket_trafikinfo_koer  
4. trafikverket_trafikinfo_vagarbeten  

### Tåg
5. trafikverket_tag_forseningar  
6. trafikverket_tag_tidtabell  
7. trafikverket_tag_stationer  
8. trafikverket_tag_installda  

### Väg
9. trafikverket_vag_status  
10. trafikverket_vag_underhall  
11. trafikverket_vag_hastighet  
12. trafikverket_vag_avstangningar  

### Väder
13. trafikverket_vader_stationer  
14. trafikverket_vader_halka  
15. trafikverket_vader_vind  
16. trafikverket_vader_temperatur  

### Kameror
17. trafikverket_kameror_lista  
18. trafikverket_kameror_snapshot  
19. trafikverket_kameror_status  

### Prognos
20. trafikverket_prognos_trafik  
21. trafikverket_prognos_vag  
22. trafikverket_prognos_tag  

## Konfiguration

Lägg till i `.env`:

```
TRAFIKVERKET_API_KEY="..."
```

Redis används om `REDIS_APP_URL` är satt. Utan Redis körs verktygen utan cache.

## Kodpekare

- Service: `app/services/trafikverket_service.py`  
- Tools: `app/agents/new_chat/tools/trafikverket.py`  
- Registry: `app/agents/new_chat/tools/registry.py`  
- Bigtool metadata: `app/agents/new_chat/bigtool_store.py`
