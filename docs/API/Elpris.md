# Elpris API Integration

## Översikt

Integration med elprisetjustnu.se — ett öppet API för svenska elpriser (spotpriser).

| Egenskap | Värde |
|----------|-------|
| **API-URL** | `elprisetjustnu.se/api/v1/prices/{YYYY}/{MM-DD}_{ZONE}.json` |
| **Autentisering** | Ingen krävs |
| **Dataformat** | JSON |
| **Historik** | Från 2022-11-01 |
| **Intervall** | 15-minuters spotpriser |

## Priszoner

| Zon | Namn | Område |
|-----|------|--------|
| SE1 | Luleå | Norra Sverige |
| SE2 | Sundsvall | Mellersta Sverige |
| SE3 | Stockholm | Södra Mellansverige |
| SE4 | Malmö | Södra Sverige |

## Dataformat

Varje prispunkt innehåller:

```json
{
  "SEK_per_kWh": 0.45,
  "EUR_per_kWh": 0.04,
  "EXR": 11.25,
  "time_start": "2025-01-15T00:00:00+01:00",
  "time_end": "2025-01-15T00:15:00+01:00"
}
```

**Notera:** Priser exkluderar moms och avgifter (elnätsavgift, energiskatt etc.).

## Verktyg (4 st)

| Tool ID | Namn | Beskrivning |
|---------|------|-------------|
| `elpris_idag` | Elpris Idag | Dagens elpriser per zon |
| `elpris_imorgon` | Elpris Imorgon | Morgondagens priser (efter 13:00) |
| `elpris_historik` | Elpris Historik | Historiska priser per datum/period |
| `elpris_jamforelse` | Elpris Zonjämförelse | Jämför priser alla 4 zoner |

## Agent- och Domänkonfiguration

- **Agent:** `elpris` i domän `energi-och-miljö`
- **Primära namespaces:** `["tools", "elpris", "energi"]`
- **Fallback namespaces:** `["tools", "elpris"]`

## Cache-strategi

| Data | TTL |
|------|-----|
| Dagens priser | 15 minuter |
| Historiska priser | 24 timmar |

## Begränsningar

- Datumintervall max 31 dagar per anrop
- Morgondagens priser publiceras efter ca 13:00
- Data tillgänglig från 2022-11-01
- Priser exkluderar moms och övriga avgifter

## Filer

| Fil | Beskrivning |
|-----|-------------|
| `surfsense_backend/app/services/elpris_service.py` | HTTP-klient med cache |
| `surfsense_backend/app/agents/new_chat/tools/elpris.py` | Verktygsimplementationer |
| `surfsense_backend/tests/test_elpris_service.py` | Tester |

## Miljövariabler

| Variabel | Standard | Beskrivning |
|----------|---------|-------------|
| `ELPRIS_BASE_URL` | `https://www.elprisetjustnu.se/api/v1/prices` | API bas-URL |
| `ELPRIS_TIMEOUT` | 10.0 | HTTP timeout (sekunder) |
| `ELPRIS_CACHE_TTL_TODAY` | 900 | Cache TTL dagens priser (sekunder) |
| `ELPRIS_CACHE_TTL_HISTORY` | 86400 | Cache TTL historik (sekunder) |
