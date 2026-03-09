# NEXUS Intent & Agent Training Guide

Komplett guide: Från tomt system till fungerande precision routing.

## Innehåll

1. [Arkitekturmodell](#1-arkitekturmodell)
2. [Steg 1: Skapa Intent-domäner](#2-steg-1-skapa-intent-domäner)
3. [Steg 2: Skapa agenter](#3-steg-2-skapa-agenter)
4. [Steg 3: Tilldela verktyg till agenter](#4-steg-3-tilldela-verktyg-till-agenter)
5. [Steg 4: Seeda NEXUS-infrastruktur](#5-steg-4-seeda-nexus-infrastruktur)
6. [Steg 5: Generera syntetiska testfall (Forge)](#6-steg-5-generera-syntetiska-testfall-forge)
7. [Steg 6: Kör Auto-Loop (eval)](#7-steg-6-kör-auto-loop-eval)
8. [Steg 7: Granska och godkänn förslag](#8-steg-7-granska-och-godkänn-förslag)
9. [Steg 8: Kalibrera Platt-skalning](#9-steg-8-kalibrera-platt-skalning)
10. [Steg 9: Validera med Pipeline Explorer](#10-steg-9-validera-med-pipeline-explorer)
11. [Steg 10: Deploy-gating](#11-steg-10-deploy-gating)
12. [Felsökning](#12-felsökning)
13. [Referens: API-endpoints](#13-referens-api-endpoints)

---

## 1. Arkitekturmodell

Routing i NEXUS följer en tre-lagers hierarki:

```
Intent (domän)          →  Agent           →  Verktyg
─────────────────────      ──────────────     ───────────────────────
väder-och-klimat        →  väder           →  smhi_vaderprognoser_metfcst
                                           →  smhi_vaderobservationer_metobs
                                           →  smhi_vaderanalyser_mesan2g
trafik-och-transport    →  trafik          →  trafikverket_trafikinfo_storningar
                                           →  trafikverket_vader_stationer
ekonomi-och-skatter     →  statistik       →  scb_statistik
                        →  skatt           →  skatteverket_momsperioder
```

**Varje fråga genomgår denna kedja:**

1. **QUL (Query Understanding Layer)** — Analyserar frågan, identifierar domän-kandidater via keywords + embeddings
2. **Agent Resolver** — Väljer agent(er) inom matchade domäner
3. **Select-Then-Route (StR)** — Hämtar verktyg per zon, scorar med embeddings
4. **Reranking** — Cross-encoder omrankar kandidater (om konfigurerat)
5. **Platt-kalibrering** — Omvandlar raw scores till kalibrerade sannolikheter
6. **Band Cascade** — Klassificerar konfidens i band 0-4:
   - **Band 0** (score ≥ 0.95, margin ≥ 0.20): Direkt routing, inget LLM-anrop
   - **Band 1** (score ≥ 0.80, margin ≥ 0.10): Namespace-verifiering
   - **Band 2** (score ≥ 0.60): Top-3 kandidater → LLM väljer
   - **Band 3** (score ≥ 0.40): Dekomponering / reformulering
   - **Band 4** (score < 0.40): Out-of-Distribution (OOD)

**Målet:** Maximera Band 0-throughput (≥80%) med lågt ECE (<0.05).

---

## 2. Steg 1: Skapa Intent-domäner

Domäner definierar de övergripande kategorierna som användarfrågor kan tillhöra.

### Via Admin UI

1. Gå till **Admin → Flow Overview** (`/admin/flow`)
2. Välj **Routing view** (inte Pipeline view)
3. Klicka **"+ Intent"** (uppe till vänster)
4. Fyll i:
   - **Intent ID**: `mina-ärenden` (slug-format, bindestreck)
   - **Label**: `Mina Ärenden` (visningsnamn)
   - **Beskrivning**: Förklara vad domänen täcker
   - **Nyckelord**: `ärende, förfrågan, ansökan, status, beslut` (kommaseparerade)
   - **Route**: Välj fallback (`kunskap`, `skapande`, `jämförelse`, `konversation`)
   - **Prioritet**: 100-900 (lägre = högre prioritet)
5. Klicka **Skapa**

### Via Seed-fil (för nya installationer)

Redigera `surfsense_backend/app/seeds/intent_domains.py`:

```python
{
    "domain_id": "mina-ärenden",
    "label": "Mina Ärenden",
    "description": "Frågor om personliga ärenden, ansökningar och beslut.",
    "keywords": [
        "ärende", "ansökan", "beslut", "status",
        "handläggningstid", "förfrågan",
    ],
    "priority": 200,
    "enabled": True,
    "fallback_route": "kunskap",
    "citations_enabled": True,
    "main_identifier": "ÄrendeDomän",
    "core_activity": "Identifierar frågor om personliga ärenden och ansökningar",
    "unique_scope": "Ärendehantering, ansökningar, beslut",
    "geographic_scope": "Sverige",
    "excludes": ["väder", "trafik"],
}
```

**Viktiga fält:**
- `keywords` — Avgörande för QUL-matchning. Lägg till alla relevanta svenska ord, inklusive böjningsformer
- `excludes` — Undviker förväxling med andra domäner
- `main_identifier`, `core_activity`, `unique_scope` — Används för embedding-diskriminering mellan domäner

### Via API

```bash
PUT /api/v1/admin/flow-graph/intent
Content-Type: application/json

{
  "intent_id": "mina-ärenden",
  "label": "Mina Ärenden",
  "description": "Frågor om personliga ärenden",
  "keywords": ["ärende", "ansökan", "beslut"],
  "route": "kunskap",
  "priority": 200
}
```

---

## 3. Steg 2: Skapa agenter

Agenter är mellannivån: en domän kan ha flera agenter, varje agent äger en grupp verktyg.

### Via Admin UI

1. I **Flow Overview → Routing view**
2. Klicka **"+ Agent"** (i agentkolumnen)
3. Fyll i:
   - **Agent ID**: `försäkringskassan` (slug-format)
   - **Label**: `Försäkringskassan`
   - **Beskrivning**: Vad agenten gör
   - **Nyckelord**: `sjukpenning, föräldrapenning, bostadsbidrag, fk` (kommaseparerade)
   - **Prompt-nyckel**: `fk_prompt` (referens till systemprompt)
   - **Namespace**: `agents/försäkringskassan` (standard: `agents/<agent_id>`)
   - **Routes/intents**: `mina-ärenden` (kommaseparerad lista med domän-ID:n)
4. Klicka **Skapa**

### Via Seed-fil

Redigera `surfsense_backend/app/seeds/agent_definitions.py`:

```python
{
    "agent_id": "försäkringskassan",
    "domain_id": "mina-ärenden",
    "label": "Försäkringskassan",
    "description": "Hämtar information om socialförsäkringar, bidrag och ersättningar.",
    "keywords": [
        "sjukpenning", "föräldrapenning", "bostadsbidrag",
        "barnbidrag", "försäkringskassan", "fk",
    ],
    "priority": 100,
    "enabled": True,
    "prompt_key": "fk_prompt",
    "primary_namespaces": [["tools", "ärenden", "fk"]],
    "fallback_namespaces": [["tools", "ärenden"]],
    "worker_config": {"max_concurrency": 4, "timeout_seconds": 120},
    "main_identifier": "FKAgent",
    "core_activity": "Hämtar information om socialförsäkringar",
    "unique_scope": "FK:s förmåner och ersättningar",
    "geographic_scope": "Sverige",
    "excludes": ["väder", "trafik", "bolag"],
}
```

**Viktiga fält:**
- `primary_namespaces` — Bestämmer vilka verktyg som tillhör agenten. Format: `[["tools", "<kategori>", "<underkategori>"]]`
- `keywords` — Används av AgentResolver för att disambiguera mellan agenter i samma domän
- `domain_id` — Måste matcha en existerande domän

### Via API

```bash
PUT /api/v1/admin/flow-graph/agent
Content-Type: application/json

{
  "agent_id": "försäkringskassan",
  "label": "Försäkringskassan",
  "description": "Hämtar socialförsäkringsdata",
  "keywords": ["sjukpenning", "föräldrapenning"],
  "prompt_key": "fk_prompt",
  "namespace": "agents/försäkringskassan",
  "routes": ["mina-ärenden"]
}
```

---

## 4. Steg 3: Tilldela verktyg till agenter

Verktyg registreras automatiskt via platform_bridge från `bigtool_store`. Tilldelning till agenter sker via:

### Via Admin UI (drag-and-drop)

1. I **Flow Overview → Routing view**, se verktygsgrupperna till höger
2. **Dra verktyg** mellan agentgrupper
3. Eller klicka en agent → se dess verktyg i detaljpanelen
4. Ändra tilldelning via PATCH-anrop

### Via API

```bash
# Ändra vilka verktyg en agent äger
PATCH /api/v1/admin/flow-graph/agent-tools
Content-Type: application/json

{
  "agent_id": "försäkringskassan",
  "tool_ids": ["fk_sjukpenning", "fk_foraldrapenning", "fk_bostadsbidrag"]
}
```

### Namespace-konvention

Namespaces styr routing. Formatet är hierarkiskt:

```
tools/weather/smhi          → Väderagentens SMHI-verktyg
tools/trafik/trafikverket   → Trafikagentens verktyg
tools/ärenden/fk            → FK-agentens verktyg
```

Agentens `primary_namespaces` matchar verktygens namespace-prefix. Om ett verktyg har namespace `["tools", "weather", "smhi"]` och agenten har `primary_namespaces: [["tools", "weather", "smhi"]]`, tillhör verktyget den agenten.

---

## 5. Steg 4: Seeda NEXUS-infrastruktur

Innan eval-loopen kan köras behöver NEXUS grundläggande infrastrukturdata.

### Via Admin UI

1. Gå till **Admin → NEXUS** (`/admin/nexus`)
2. Klicka **Nollställ NEXUS** om du startar om från scratch (bekräfta i dialogen)
3. Seed-data skapas automatiskt första gången NEXUS startar

### Via API

```bash
# Seeda grunddata (zonkonfigurationer, initial calibration)
POST /api/v1/nexus/seed

# Eller nollställ allt och börja om
POST /api/v1/nexus/reset
```

---

## 6. Steg 5: Generera syntetiska testfall (Forge)

Syntetiska testfall är frågor som LLM genererar per verktyg i 4 svårighetsgrader.

### Via Admin UI

1. Gå till **Admin → NEXUS → Forge**
2. Välj filtrering:
   - **Alla verktyg** — Genererar för hela katalogen
   - **Per kategori** — T.ex. bara "smhi" eller "trafikverket"
   - **Per namespace** — T.ex. "tools/weather"
3. Klicka **Generera**
4. Vänta — generering tar ~30 sek per verktyg (LLM-anrop)
5. Granska genererade testfall i listan

### Via API

```bash
# Generera för alla verktyg
POST /api/v1/nexus/forge/generate
Content-Type: application/json
{
  "questions_per_difficulty": 4
}

# Generera för specifik kategori
POST /api/v1/nexus/forge/generate
{
  "category": "smhi",
  "questions_per_difficulty": 4
}

# Generera för specifika verktyg
POST /api/v1/nexus/forge/generate
{
  "tool_ids": ["smhi_vaderprognoser_metfcst", "smhi_vaderobservationer_metobs"],
  "questions_per_difficulty": 4
}

# Lista genererade testfall
GET /api/v1/nexus/forge/cases
```

### Svårighetsgrader

| Grad | Beskrivning | Exempel |
|------|-------------|---------|
| `easy` | Direkt nämner verktygets namn/funktion | "Visa SMHI-prognosen för Stockholm" |
| `medium` | Beskriver behovet utan att nämna verktyget | "Hur blir vädret imorgon?" |
| `hard` | Tvetydig, kan matcha flera verktyg | "Bör jag ta regnjacka till jobbet?" |
| `adversarial` | Lurar systemet mot fel verktyg | "Vilken temperatur visar Trafikverkets väderstationer?" |

**Mål:** Minst 4 testfall per svårighetsgrad per verktyg = 16 testfall per verktyg.

---

## 7. Steg 6: Kör Auto-Loop (eval)

Auto-loopen kör alla testfall genom routing-pipelinen och jämför NEXUS-val med förväntat verktyg.

### Via Admin UI

1. Gå till **Admin → NEXUS → Loop** (eller **Admin → Verktyg → Kalibrering**)
2. Välj scope:
   - **Allt** — Alla syntetiska testfall
   - **Per kategori** — T.ex. bara "smhi"
   - **Per namespace** — T.ex. "tools/weather"
3. Klicka **Starta loop**
4. Vänta — loopen processar alla testfall

### Via API

```bash
# Starta inline (blockerar tills klar)
POST /api/v1/nexus/loop/start
Content-Type: application/json
{
  "max_iterations": 1,
  "batch_size": 200
}

# Starta med streaming (SSE för progress)
POST /api/v1/nexus/loop/start-stream
Content-Type: application/json
{
  "max_iterations": 1
}

# Filtrera per kategori
POST /api/v1/nexus/loop/start
{
  "category": "smhi",
  "max_iterations": 1
}

# Lista tidigare körningar
GET /api/v1/nexus/loop/runs

# Hämta specifik körning med resultat
GET /api/v1/nexus/loop/runs/{run_id}
```

### Vad loopen gör

1. Laddar alla matchande syntetiska testfall
2. För varje testfall:
   - Kör QUL-analys (query understanding)
   - Kör Select-Then-Route (verktygsval)
   - Jämför valt verktyg med förväntat (`expected_tool_id`)
   - Loggar routing-event med band, score, margin
3. Samlar Platt-kalibrerings-data (raw scores + labels)
4. Om iteration 1 och ≥10 samples: försöker auto-fitta Platt-skalaren
5. Klustrar felaktiga resultat och genererar förbättringsförslag

### Tolka resultaten

| Metrik | Bra | Dåligt | Åtgärd |
|--------|-----|--------|--------|
| Success rate | ≥80% | <60% | Förbättra keywords, embeddings, metadata |
| Band 0 throughput | ≥40% | <10% | Förbättra keyword/embedding-diskriminering |
| OOD rate | <5% | >50% | Kontrollera att domän-keywords täcker frågorna |
| Namespace purity | ≥90% | <50% | Rätta namespace-tilldelning |

---

## 8. Steg 7: Granska och godkänn förslag

Auto-loopen genererar förbättringsförslag baserat på felanalys.

### Via API

```bash
# Hämta körning med proposals
GET /api/v1/nexus/loop/runs/{run_id}

# Godkänn förslag (applicera ändringar)
POST /api/v1/nexus/loop/runs/{run_id}/approve
```

### Typer av förslag

- **Keyword-tillägg** — Nya keywords för domäner/agenter som missade frågor
- **Metadata-förbättringar** — Bättre descriptions, example queries, eller exclude-listor
- **Namespace-korrigeringar** — Verktyg som bör byta agent

---

## 9. Steg 8: Kalibrera Platt-skalning

Platt-skalning omvandlar raw reranker-scores till kalibrerade sannolikheter så att band-trösklar fungerar korrekt.

### Via Admin UI

1. Gå till **Admin → NEXUS → Översikt**
2. Kontrollera **Platt-kalibrerad**: Ja/Nej
3. Om Nej, gå till **Admin → NEXUS → Optimizer**
4. Klicka **Fit Platt** (kräver ≥10 routing-events med korrekta labels)

### Via API

```bash
# Fitta Platt-skalning manuellt
POST /api/v1/nexus/calibration/fit

# Kolla aktuella parametrar
GET /api/v1/nexus/calibration/params

# Kolla ECE (Expected Calibration Error)
GET /api/v1/nexus/calibration/ece
```

### Tolka kalibrering

| Metrik | Mål | Kris |
|--------|-----|------|
| Global ECE | <0.05 | >0.15 |
| Platt A-parameter | -5 till -1 (negativt!) | >0 (degenererad) |
| Platt B-parameter | -2 till 2 | |

**OBS:** Om Platt-skalaren ger degenererade resultat (alla outputs ~0 eller ~1), faller systemet automatiskt tillbaka till raw scores (sedan fixat i senaste update).

---

## 10. Steg 9: Validera med Pipeline Explorer

### Via Admin UI

1. Gå till **Admin → NEXUS → Pipeline Explorer**
2. Skriv en testfråga, t.ex. "Hur blir vädret i Stockholm imorgon?"
3. Se:
   - **QUL-analys**: Identifierade domäner, keywords, entiteter
   - **Kandidater**: Top-5 verktyg med raw + calibrated scores
   - **Band-klassificering**: Vilket band frågan hamnar i
   - **Valt verktyg**: Slutgiltigt val

### Via API

```bash
# Analysera en fråga (QUL only)
POST /api/v1/nexus/routing/analyze
{
  "query": "Hur blir vädret i Stockholm imorgon?"
}

# Full routing (QUL + StR + Rerank + Band)
POST /api/v1/nexus/routing/route
{
  "query": "Hur blir vädret i Stockholm imorgon?",
  "llm_judge": true
}
```

### Vad du bör kontrollera

1. **Rätt domän identifieras** — Om "väder" inte identifieras, lägg till keywords
2. **Rätt agent väljs** — Om fel agent, kontrollera agent-keywords och namespace
3. **Rätt verktyg rankas högst** — Om fel verktyg, förbättra description/example queries
4. **Score-margin** — Skillnaden mellan #1 och #2 bör vara >0.10 för Band 0-1
5. **Band** — Bör vara Band 0 eller 1 för tydliga frågor

---

## 11. Steg 10: Deploy-gating

Triple-gate-systemet avgör om ett verktyg är redo för produktion.

### De tre grindarna

| Grind | Krav | Kontrollerar |
|-------|------|-------------|
| **1. Separation** | Score ≥ 0.65 | Embedding-separering från grannverktyg |
| **2. Eval** | Success ≥ 80%, HN ≥ 85% | Korrekthet på testfall och hard negatives |
| **3. LLM Judge** | Clarity ≥ 4.0 | Metadatakvalitet bedömd av LLM |

### Via API

```bash
# Kontrollera gate-status för ett verktyg
GET /api/v1/nexus/deploy/gates/{tool_id}

# Promovera till produktion
POST /api/v1/nexus/deploy/promote/{tool_id}

# Rollback
POST /api/v1/nexus/deploy/rollback/{tool_id}
```

---

## 12. Felsökning

### "4720% Namespace Purity"

**Orsak:** Schema-verified count räknade OOD-events men delade med non-OOD count.
**Fix:** Uppdatera till senaste version (fixat).

### "Alla calibrated scores = 0.000"

**Orsak:** Platt-skalaren fittad med degenererade data.
**Fix:** Systemet avvisar nu degenererade fits automatiskt. Kör `POST /nexus/reset` och börja om, eller kör `POST /nexus/calibration/fit` med bättre data.

### "97.9% OOD rate"

**Orsak:** De flesta frågor matchar inget verktyg med score ≥ 0.40.
**Möjliga åtgärder:**
1. Kontrollera att embedding-modellen är laddad (`EMBEDDING_MODEL` env var)
2. Lägg till fler keywords i domäner och agenter
3. Kör Forge för att generera testfall som matchar verktygens faktiska capability
4. Kontrollera att verktyg har bra descriptions och example_queries

### "Band 0 throughput <10%"

**Orsak:** Scores hamnar under 0.95-tröskeln.
**Möjliga åtgärder:**
1. Förbättra verktygs-descriptions (mer specifika, inkludera relevanta svenska termer)
2. Lägg till `example_queries` i verktygsmetadata
3. Kontrollera keyword-overlap mellan närliggande verktyg
4. Kontrollera att zone prefixes i embeddings fungerar korrekt

### "Reranker Delta negativ"

**Orsak:** Cross-encoder-reranking försämrar ordningen jämfört med embedding-retrieval.
**Möjliga åtgärder:**
1. Kontrollera reranker-modellens kvalitet för svenska
2. Stäng av reranker tillfälligt (`RERANKERS_ENABLED=FALSE`)
3. Testa annan reranker-modell

---

## 13. Referens: API-endpoints

### Konfiguration

| Metod | Endpoint | Beskrivning |
|-------|----------|-------------|
| GET | `/nexus/health` | Systemstatus |
| GET | `/nexus/zones` | Zonkonfigurationer |
| GET | `/nexus/config` | Full NEXUS-konfiguration |
| GET | `/nexus/overview/metrics` | Översiktsmetriker |
| GET | `/nexus/tools` | Verktygsregister |
| GET | `/nexus/tools/categories` | Verktygskategorier |
| GET | `/nexus/tools/agents` | Agent-lista |

### Routing

| Metod | Endpoint | Beskrivning |
|-------|----------|-------------|
| POST | `/nexus/routing/analyze` | QUL-analys |
| POST | `/nexus/routing/route` | Full routing pipeline |
| GET | `/nexus/routing/events` | Routing-historik |
| GET | `/nexus/routing/band-distribution` | Band-fördelning |
| POST | `/nexus/routing/events/{id}/feedback` | Tumme upp/ner på routing-resultat |

### Forge

| Metod | Endpoint | Beskrivning |
|-------|----------|-------------|
| POST | `/nexus/forge/generate` | Generera syntetiska testfall |
| GET | `/nexus/forge/cases` | Lista testfall |
| DELETE | `/nexus/forge/cases/{id}` | Ta bort testfall |

### Loop

| Metod | Endpoint | Beskrivning |
|-------|----------|-------------|
| POST | `/nexus/loop/start` | Starta eval-loop (inline) |
| POST | `/nexus/loop/start-stream` | Starta eval-loop (SSE) |
| GET | `/nexus/loop/runs` | Lista körningar |
| GET | `/nexus/loop/runs/{id}` | Detaljer för körning |
| POST | `/nexus/loop/runs/{id}/approve` | Godkänn förslag |

### Kalibrering

| Metod | Endpoint | Beskrivning |
|-------|----------|-------------|
| POST | `/nexus/calibration/fit` | Fitta Platt-skalning |
| GET | `/nexus/calibration/params` | Aktuella parametrar |
| GET | `/nexus/calibration/ece` | ECE-rapport |

### Space Auditor

| Metod | Endpoint | Beskrivning |
|-------|----------|-------------|
| GET | `/nexus/space/health` | Embedding space hälsa |
| GET | `/nexus/space/snapshot` | Aktuell space snapshot |
| POST | `/nexus/space/refresh` | Uppdatera space-analys |
| GET | `/nexus/space/confusion` | Förväxlingspar |
| GET | `/nexus/space/hubness` | Hubness-rapport |

### Deploy

| Metod | Endpoint | Beskrivning |
|-------|----------|-------------|
| GET | `/nexus/deploy/gates/{tool_id}` | Gate-status |
| POST | `/nexus/deploy/promote/{tool_id}` | Promovera |
| POST | `/nexus/deploy/rollback/{tool_id}` | Rollback |

### Admin Flow Graph (intent/agent CRUD)

| Metod | Endpoint | Beskrivning |
|-------|----------|-------------|
| GET | `/admin/flow-graph` | Hämta hela routing-grafen |
| PUT | `/admin/flow-graph/intent` | Skapa/uppdatera intent-domän |
| DELETE | `/admin/flow-graph/intent` | Ta bort intent-domän |
| PUT | `/admin/flow-graph/agent` | Skapa/uppdatera agent |
| DELETE | `/admin/flow-graph/agent` | Ta bort agent |
| PATCH | `/admin/flow-graph/agent-routes` | Ändra agentens domän-kopplingar |
| PATCH | `/admin/flow-graph/agent-tools` | Ändra agentens verktyg |

---

## Snabb-checklista: Nytt verktyg från scratch

1. [ ] Skapa domän i Flow Overview (om den inte finns)
2. [ ] Skapa agent under domänen (om den inte finns)
3. [ ] Implementera verktyget i `surfsense_backend/app/agents/new_chat/tools/`
4. [ ] Registrera verktyget i bigtool_store
5. [ ] Tilldela verktyget till agenten via Flow Overview eller API
6. [ ] Kör `POST /nexus/forge/generate` med `tool_ids: ["mitt_verktyg"]`
7. [ ] Kör `POST /nexus/loop/start` för att evaluera
8. [ ] Kontrollera resultat i Pipeline Explorer
9. [ ] Om score <0.80: förbättra keywords, description, example_queries
10. [ ] Upprepa steg 6-9 tills Band 0 eller 1
11. [ ] Kör `POST /nexus/calibration/fit`
12. [ ] Kontrollera deploy gates: `GET /nexus/deploy/gates/{tool_id}`
13. [ ] Promovera: `POST /nexus/deploy/promote/{tool_id}`
