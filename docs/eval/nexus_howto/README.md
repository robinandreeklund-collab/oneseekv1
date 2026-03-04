# NEXUS — Retrieval Intelligence Platform

> Komplett dokumentation: Från fråga till svar, integration med OneSeek, och hur NEXUS
> förbättrar val av intent, agent och verktyg.

---

## Innehållsförteckning

1. [Vad är NEXUS?](#1-vad-är-nexus)
2. [Arkitekturöversikt](#2-arkitekturöversikt)
3. [Hur en fråga flödar genom systemet](#3-hur-en-fråga-flödar-genom-systemet)
4. [Integration med OneSeek](#4-integration-med-oneseek)
5. [Routing Pipeline — Steg för steg](#5-routing-pipeline--steg-för-steg)
6. [5-Lager Evalueringsstack](#6-5-lager-evalueringsstack)
7. [Hur NEXUS förbättrar Intent-val](#7-hur-nexus-förbättrar-intent-val)
8. [Hur NEXUS förbättrar Agent-val](#8-hur-nexus-förbättrar-agent-val)
9. [Hur NEXUS förbättrar Verktygs-val](#9-hur-nexus-förbättrar-verktygs-val)
10. [Confidence Band Cascade](#10-confidence-band-cascade)
11. [Kalibrering & OOD-detektion](#11-kalibrering--ood-detektion)
12. [Dashboard & Övervakning](#12-dashboard--övervakning)
13. [API-referens](#13-api-referens)
14. [Filstruktur](#14-filstruktur)

---

## 1. Vad är NEXUS?

NEXUS (Nexus Evaluation & eXperimental Utility System) är OneSeeks **precisions-routing och
självförbättrande evalueringsplattform**. Systemet körs parallellt med produktionsroutingen
och ansvarar för:

- **Precision Routing** — Avgör vilken intent, agent och verktyg som bäst matchar en fråga
- **Embedding-rymdanalys** — Övervakar hur väl separerade verktyg är i vektorutrymmet
- **Syntetisk testgenerering** — Skapar testfrågor automatiskt med LLM
- **Självförbättrande loop** — Identifierar och fixar routing-svagheter autonomt
- **Triple-gate deploy** — Kvalitetssäkrar verktyg innan de når produktion

### Nyckelprinciper

| Princip | Beskrivning |
|---------|-------------|
| **Ingen duplicering** | NEXUS importerar verktygsdefinitioner direkt från plattformen |
| **Read-only observation** | Shadow Observer ändrar aldrig produktionsroutingen |
| **Riktiga modeller** | Använder samma embeddings och reranker som produktionssystemet |
| **Embedding-first** | Cosine similarity är bassignalen, inte keywords |
| **Onormaliserade scores** | Scores i [0, 1] matchar band-trösklar direkt |

---

## 2. Arkitekturöversikt

```
┌──────────────────────────────────────────────────────────────────────┐
│                         NEXUS PLATTFORM                              │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    ROUTING PIPELINE                             │  │
│  │                                                                │  │
│  │  Fråga → QUL → StR → Rerank → Kalibrering → OOD → Band → SV  │  │
│  │         (1)    (2)    (3)       (4)          (5)   (6)   (7)   │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐  ┌───────┐  │
│  │  SPACE   │  │  SYNTH   │  │   AUTO   │  │  EVAL   │  │DEPLOY │  │
│  │ AUDITOR  │  │  FORGE   │  │   LOOP   │  │ LEDGER  │  │CONTROL│  │
│  │ (Lager 1)│  │ (Lager 2)│  │ (Lager 3)│  │(Lager 4)│  │(L. 5) │  │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘  └───────┘  │
│                                                                      │
│  ┌────────────────────┐  ┌─────────────────────────────────────┐    │
│  │  PLATFORM BRIDGE   │  │          SHADOW OBSERVER             │    │
│  │  (verktygimport)   │  │  (jämför med produktionsrouting)     │    │
│  └────────────────────┘  └─────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    DATABAS (nexus_* tabeller)                   │  │
│  │  routing_events | synthetic_cases | auto_loop_runs | zones ... │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
         │                                    ▲
         │ importerar verktyg                 │ läser feedback
         ▼                                    │
┌──────────────────────────────────────────────────────────────────────┐
│                      ONESEEK PLATTFORM                               │
│                                                                      │
│  bigtool_store.py → ToolIndexEntry, TOOL_KEYWORDS                    │
│  tools/registry.py → BUILTIN_TOOLS, domain *_TOOL_DEFINITIONS       │
│  retrieval_feedback → success/failure-signaler                       │
│  config → embedding-modell, LiteLLM                                  │
│  intent_definition_service → intent-definitioner                     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Hur en fråga flödar genom systemet

### 3.1 Komplett flöde — Exempelquery

**Fråga:** *"Vad är vädret i Stockholm imorgon?"*

```
┌─────────────────┐
│ Användare skriver│
│ "Vad är vädret  │
│ i Stockholm     │
│ imorgon?"       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ STEG 1: Query Understanding Layer (QUL)     │
│                                             │
│ • Normalisering: "vad är väder stockholm    │
│   imorgon"                                  │
│ • Entiteter:                                │
│   - locations: ["Stockholm"]                │
│   - times: ["imorgon"]                      │
│ • Domain hints: ["väder", "smhi"]           │
│ • Zon-kandidater: ["kunskap"]               │
│ • Komplexitet: "simple"                     │
│ • Multi-intent: false                       │
│                                             │
│ Tid: <5 ms (ingen LLM, ingen DB)           │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ STEG 2: Select-Then-Route (StR)             │
│                                             │
│ • Välj zoner: ["kunskap"]                   │
│ • Ladda verktyg från Platform Bridge        │
│ • Per-zon retrieval (top-5 per zon):        │
│                                             │
│   smhi_weather         0.92                 │
│   scb_population       0.15                 │
│   trafikverket_kameror 0.08                 │
│   kolada_nyckeltal     0.06                 │
│   riksdagen_ledamoter  0.04                 │
│                                             │
│ • Merge & sortera → max 15 kandidater       │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ STEG 3: Cross-encoder Reranking             │
│                                             │
│ • flashrank ms-marco-MultiBERT-L-12         │
│ • Rerankar top-kandidater:                  │
│                                             │
│   smhi_weather         0.95                 │
│   scb_population       0.18                 │
│   trafikverket_kameror 0.12                 │
│                                             │
│ Tid: ~50 ms                                 │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ STEG 4: Platt-kalibrering                   │
│                                             │
│ • Sigmoid-transform: P = 1/(1+exp(A*x-B))  │
│ • Raw 0.95 → Calibrated 0.94               │
│ • Raw 0.18 → Calibrated 0.11               │
│                                             │
│ Margin: 0.94 - 0.11 = 0.83                 │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ STEG 5: OOD-detektion (Out-of-Distribution) │
│                                             │
│ • Energy Score = -2.1                       │
│   (under threshold -5.0 → in-distribution) │
│ • is_ood = false                            │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ STEG 6: Confidence Band Classification      │
│                                             │
│ • top_score=0.94, margin=0.83               │
│ • Band 0: score≥0.95 & margin≥0.20? NEJ    │
│ • Band 1: score≥0.80 & margin≥0.10? JA ✓   │
│                                             │
│ → Band 1 (VERIFY): Snabb namespace-check    │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ STEG 7: Schema Verification                 │
│                                             │
│ • Verktyg: smhi_weather                     │
│ • Required params: ["location"]             │
│ • Query har location="Stockholm" ✓          │
│ • Geographic scope: "sweden"                │
│ • Stockholm i Sverige ✓                     │
│ • schema_verified = true                    │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ RESULTAT: RoutingDecision                   │
│                                             │
│ {                                           │
│   selected_tool: "smhi_weather",            │
│   calibrated_confidence: 0.94,              │
│   band: 1,                                  │
│   band_name: "VERIFY",                      │
│   is_ood: false,                            │
│   schema_verified: true,                    │
│   resolved_zone: "kunskap",                 │
│   latency_ms: 145                           │
│ }                                           │
└─────────────────────────────────────────────┘
```

### 3.2 Parallellt: Shadow Observer

Samtidigt som NEXUS kör sin pipeline jämförs beslutet med produktionssystemets routing:

```
NEXUS valde:   smhi_weather  (confidence 0.94)
Produktion:    smhi_weather  (live retrieval score)
→ Agreement: true  (loggas till shadow report)
```

---

## 4. Integration med OneSeek

### 4.1 Platform Bridge — Ingen duplicering

NEXUS importerar **direkt** från produktionskoden. Inga kopior, inga egna verktygsdefinitioner.

```python
# platform_bridge.py importerar från:
from app.agents.new_chat.bigtool_store import (
    TOOL_KEYWORDS,
    TOOL_NAMESPACE_OVERRIDES,
    namespace_for_tool,
)
from app.agents.new_chat.tools.registry import BUILTIN_TOOLS
from app.agents.new_chat.tools.smhi_tools import SMHI_TOOL_DEFINITIONS
from app.agents.new_chat.tools.scb_tools import SCB_TOOL_DEFINITIONS
# ... alla domänverktyg
```

Varje verktyg representeras som en `PlatformTool`:

| Fält | Beskrivning | Exempel |
|------|-------------|---------|
| `tool_id` | Unikt verktygs-ID | `smhi_weather` |
| `name` | Visningsnamn | `SMHI Väderprognos` |
| `description` | Kort beskrivning | `Hämtar väderdata...` |
| `category` | Domängrupp | `smhi` |
| `namespace` | Hierarkisk plats | `("tools", "weather", "smhi")` |
| `zone` | Intent-zon | `kunskap` |
| `keywords` | Söktermer | `["väder", "prognos", "temperatur"]` |
| `geographic_scope` | Geoområde | `sweden` |
| `temporal_scope` | Tidsomfång | `forecast` |

### 4.2 Fyra zoner = Fyra intents

NEXUS zon-system är **direkt mappat** till OneSeeks intent-definitioner:

| Zon | Prefix | Intent | Beskrivning |
|-----|--------|--------|-------------|
| **kunskap** | `[KUNSK]` | kunskap | Sökning, väder, statistik, politik |
| **skapande** | `[SKAP]` | skapande | Kod, kartor, media, podcasts |
| **jämförelse** | `[JAMFR]` | jämförelse | Jämför externa AI-modeller |
| **konversation** | `[KONV]` | konversation | Smalltalk, hälsningar |

Namespace-mappning:
```
tools/knowledge  → kunskap
tools/weather    → kunskap
tools/politik    → kunskap
tools/statistics → kunskap
tools/trafik     → kunskap
tools/bolag      → kunskap
tools/action     → skapande
tools/code       → skapande
tools/kartor     → skapande
tools/compare    → jämförelse
```

### 4.3 Produktion vs NEXUS — Två parallella vägar

```
Användarfråga
    │
    ├───► PRODUKTION (live routing)
    │     supervisor_v2 → intent_node → planner → executor
    │     bigtool_store.smart_retrieve_tools_with_breakdown()
    │     ToolRetrievalTuning (vikter: name=5.0, keyword=3.0, ...)
    │
    └───► NEXUS (analys & utvärdering)
          QUL → StR → Rerank → Calibrate → OOD → Band → Schema
          Loggar resultat, jämför med produktion via Shadow Observer
```

NEXUS **ändrar aldrig** produktionens routing direkt. Istället:
1. Analyserar routing-kvalitet
2. Identifierar svagheter (confusion, OOD, felrouting)
3. Genererar förbättringsförslag (metadata, keywords, descriptions)
4. Föreslår ändringar som en människa granskar och godkänner

### 4.4 Delade resurser

| Resurs | Fil | Hur NEXUS använder |
|--------|-----|-------------------|
| Embedding-modell | `app/config` | Samma KBLab sentence-bert |
| Reranker | `RerankerService` | Samma flashrank cross-encoder |
| Databas | `app/db.py` | Delar Base/Session, egna `nexus_*` tabeller |
| Auth | `app/users.py` | Samma JWT-autentisering |
| LLM | LiteLLM config | Synth Forge & Deploy Gate 3 |
| Verktygsregister | `bigtool_store.py` | Read-only import |
| Retrieval feedback | `retrieval_feedback.py` | Läser success/failure-signaler |

### 4.5 Minimal påverkan på existerande kod

NEXUS kräver bara **2 rader** i befintlig kod:

```python
# app/app.py — EN rad
app.include_router(nexus_router, prefix="/api/v1")

# celery_worker.py — EN rad (om auto-loop tasks behövs)
from app.nexus.tasks import *  # noqa
```

---

## 5. Routing Pipeline — Steg för steg

### Steg 1: Query Understanding Layer (QUL)

**Fil:** `app/nexus/routing/qul.py`

QUL analyserar frågan **utan LLM och utan databasanrop** (mål: <5 ms).

**Delsteg:**

| # | Delsteg | Vad det gör |
|---|---------|-------------|
| 1 | Svensk normalisering | Expanderar förkortningar (smhi → Sveriges meteorologiska...) |
| 2 | Entitetsextraktion | Hittar platser (290 kommuner), tider, organisationer, ämnen |
| 3 | Multi-intent-detektion | Upptäcker sammansatta frågor ("väder OCH trafikinfo") |
| 4 | Domain-hint scoring | Matchar keywords mot domänbanker |
| 5 | Zon-kandidat-resolution | Avgör vilka zoner som är relevanta |
| 6 | Komplexitetsklassificering | `simple` / `compound` / `complex` |

**Gazetteers & banker:**
- 290 svenska kommuner + förkortningar (sthlm, gbg, etc.)
- Tidsuttryck: "imorgon", "idag", "nästa vecka", "2024-03-15"
- Svenska myndigheter: SMHI, SCB, Riksdagen, Trafikverket, etc.
- Domain hints per zon (50+ keywords per kategori)

### Steg 2: Select-Then-Route (StR)

**Fil:** `app/nexus/routing/select_then_route.py`

StR-mönstret undviker cross-zone pollution genom zonspecifik retrieval:

1. **Välj zoner** baserat på QUL:s zon-kandidater (max 2)
2. **Per-zon retrieval** — top-5 verktyg per vald zon
3. **Merge** — sammanfoga alla kandidater
4. **Score** — embedding cosine similarity som bassignal

Scoring-strategi:
```
raw_score = embedding_similarity(query, tool_description)  # [0, 1]
raw_score += 0.05  om zon matchar QUL:s kandidater
raw_score += 0.02  per matchande keyword
raw_score = min(1.0, raw_score)  # Klipp till [0, 1]
```

### Steg 3: Cross-encoder Reranking

**Fil:** `app/nexus/embeddings.py`

Använder `flashrank ms-marco-MultiBERT-L-12` (samma modell som produktion) för att
reordna kandidater med mer semantisk förståelse.

### Steg 4: Platt-kalibrering

**Fil:** `app/nexus/calibration/platt_scaler.py`

Konverterar raw reranker-scores till kalibrerade sannolikheter:

```
P(correct) = 1 / (1 + exp(A × raw_score - B))
```

Parametrar A och B fittas på historiska routing-events via L-BFGS-B optimering.

### Steg 5: OOD-detektion

**Fil:** `app/nexus/routing/ood_detector.py`

Dual-gate approach för att fånga "dark matter" (frågor utan matchande verktyg):

| Gate | Metod | Tröskel | Syfte |
|------|-------|---------|-------|
| Gate 1 | Energy Score | -5.0 | Primär OOD-detektion |
| Gate 2 | KNN Distance (FAISS, k=5) | 2.5 | Backup för borderline-fall |

OOD-frågor klassificeras i 6 kategorier:
- `no_tool` — Inget matchande verktyg finns
- `geo_scope` — Utanför geografisk räckvidd (t.ex. "väder i Paris")
- `temporal_scope` — Historiska/framtida datum utanför scope
- `ambiguous` — Flertydig fråga
- `conflicting` — Motstridiga krav
- `underspecified` — Information saknas

### Steg 6: Confidence Band Cascade

Se [sektion 10](#10-confidence-band-cascade) för detaljer.

### Steg 7: Schema Verification

**Fil:** `app/nexus/routing/schema_verifier.py`

Post-selection validering som kontrollerar att det valda verktygets krav matchar frågan:

| Check | Vad det kontrollerar | Penalty |
|-------|---------------------|---------|
| Required params | Saknad location, municipality, etc. | -0.10 per param |
| Geographic scope | Utländsk fråga för Sverige-verktyg | -0.15 |
| Temporal scope | Historisk fråga för prognos-verktyg | -0.10 |

Om penalty sänker confidence under nästa band-tröskel → verktyget nedgraderas eller avvisas.

---

## 6. 5-Lager Evalueringsstack

NEXUS har 5 lager som kontinuerligt förbättrar routing-kvaliteten:

### Lager 1: Space Auditor

**Fil:** `app/nexus/layers/space_auditor.py`

Analyserar embedding-utrymmet:

- **UMAP 2D-projektion** — Visualiserar alla verktyg i 2D
- **Silhouette score** — Mäter klusterseparation (mål: >0.60)
- **Confusion pairs** — Identifierar verktyg som är farligt nära varandra
- **Hubness detection** — Hittar verktyg som dyker upp som nearest-neighbor oproportionerligt ofta
- **Cluster purity** — Hur rena zon-klustren är (mål: >0.85)

### Lager 2: Synth Forge

**Fil:** `app/nexus/layers/synth_forge.py`

Genererar syntetiska testfrågor automatiskt med LLM:

| Svårighetsgrad | Beskrivning | Syfte |
|----------------|-------------|-------|
| **EASY** | Frågor som tydligt mappar till verktyget | Baseline-verifiering |
| **MEDIUM** | Verktyget behövs men nämns inte explicit | Semantisk förståelse |
| **HARD** | Disambiguation mot liknande verktyg | Separation-test |
| **ADVERSARIAL** | Ska INTE välja detta verktyg | Negativ träning |

Varje fråga genomgår **roundtrip-verifiering**: `query → retrieve → kontrollera om rätt verktyg
är i top-k`.

Mål: 16 testfrågor per verktyg (4 svårigheter × 4 frågor).

### Lager 3: Auto Loop

**Fil:** `app/nexus/layers/auto_loop.py`

7-stegs självförbättrande pipeline:

```
┌─────────────────────────────────────────────────┐
│ 1. GENERERA testfrågor (Synth Forge)            │
│    ↓                                            │
│ 2. EVALUERA mot aktuell routing                 │
│    ↓                                            │
│ 3. KLUSTRA feltyper (DBSCAN)                    │
│    "Alla SMHI-verktyg förväxlas med varandra"    │
│    ↓                                            │
│ 4. LLM ROOT CAUSE per kluster                   │
│    "Beskrivningarna är för lika"                 │
│    ↓                                            │
│ 5. TESTA FIX i isolation (embedding delta)       │
│    "Ny beskrivning ger +0.05 separation"         │
│    ↓                                            │
│ 6. HUMAN REVIEW-kö                              │
│    Visa förslag med diff + motivering            │
│    ↓                                            │
│ 7. DEPLOY & REINDEX (om godkänt)                │
│    Uppdatera metadata, räkna om embeddings       │
└─────────────────────────────────────────────────┘
```

Statusar: `pending → running → analyzing → proposing → review → approved/rejected → deployed`

### Lager 4: Eval Ledger

**Fil:** `app/nexus/layers/eval_ledger.py`

Spårar precision-metriker i 5 pipeline-steg:

| Steg | Namn | Vad mäts |
|------|------|----------|
| 1 | Intent routing | Rätt zon vald? |
| 2 | Route selection | Rätt verktygskandidat? |
| 3 | Bigtool retrieval | Rätt i top-k? |
| 4 | Reranker effect | Förbättring efter reranking? |
| 5 | End-to-end | Hela kedjan korrekt? |

Metriker per steg:
- **Precision@1** — Rätt verktyg på plats 1
- **Precision@5** — Rätt verktyg i top 5
- **MRR@10** — Mean Reciprocal Rank i top 10
- **nDCG@5** — Normalized Discounted Cumulative Gain
- **Hard negative precision** — Korrekt avvisade hard negatives
- **Reranker delta** — Skillnad pre/post reranking

### Lager 5: Deploy Control

**Fil:** `app/nexus/layers/deploy_control.py`

Triple-gate lifecycle: `REVIEW → STAGING → LIVE`

| Gate | Namn | Krav |
|------|------|------|
| **Gate 1** | Separation | Silhouette score ≥ 0.65 |
| **Gate 2** | Eval | Success ≥ 80%, hard neg ≥ 85%, adversarial ≥ 80% |
| **Gate 3** | LLM Judge | Description clarity ≥ 4.0, keyword relevance ≥ 4.0, disambiguation ≥ 4.0 |

Gate 3 använder en riktig LLM (via LiteLLM) som bedömer verktygets metadata kvalitativt
på en 1-5-skala.

---

## 7. Hur NEXUS förbättrar Intent-val

### Problemet utan NEXUS

OneSeeks supervisor agent rotar intent baserat på LLM-klassificering:

```
Fråga → LLM → "kunskap" / "skapande" / "jämförelse" / "konversation"
```

Problem:
- LLM-anrop kostar tid (~200ms) och pengar
- Ingen kalibrering av confidence
- Gränsfall hanteras dåligt (t.ex. "skapa en karta över SCB-statistik" = skapande ELLER kunskap?)

### Hur NEXUS förbättrar

1. **QUL pre-screening (<5ms):** Identifierar zon-kandidater genom keyword-matchning och
   entitetsextraktion — UTAN LLM-anrop

2. **Zone-aware retrieval:** StR hämtar verktyg från kandidat-zoner separat, undviker cross-zone
   pollution

3. **Multi-intent detection:** Upptäcker sammansatta frågor ("väder OCH trafikinfo") och kan
   föreslå decomposition

4. **Band-0 direct routing:** >80% av frågorna kan routas DIREKT (band 0) utan LLM-anrop
   baserat på embedding-similarity — sparar tid och kostnad

5. **Continuous monitoring:** Eval Ledger steg 1 mäter intent routing precision och identifierar
   trender

---

## 8. Hur NEXUS förbättrar Agent-val

### Problemet utan NEXUS

OneSeeks supervisor väljer agent baserat på intent:
- kunskap → `kunskap`-agent
- skapande → `skapande`-agent
- jämförelse → `compare`-agent

Agenten har ett namespace med tillgängliga verktyg, men:
- Agent-val baseras på intent, inte verktygskvalitet
- Ingen feedback-loop vid felval
- Ingen spårning av agent-verktyg-koppling

### Hur NEXUS förbättrar

1. **Namespace purity tracking:** NEXUS mäter hur ofta rätt agent/namespace väljs via
   `namespace_purity` metriken (mål: >92%)

2. **Shadow comparison:** Shadow Observer jämför NEXUS routing-beslut med produktionens
   agent-val och loggar avvikelser

3. **Auto Loop metadata-förslag:** Om Auto Loop identifierar att verktyg hamnar i fel
   agent-namespace, föreslår den namespace-ändring

4. **Dark Matter-analys:** Frågor som hamnar i OOD (ingen agent matchar) klustras och
   analyseras — kan leda till nya agent-definitioner

---

## 9. Hur NEXUS förbättrar Verktygs-val

### Problemet utan NEXUS

Bigtool Store hämtar verktyg via viktad scoring:
```
score = name_match×5.0 + keyword×3.0 + embedding×4.0 + ...
```

Problem:
- Vikterna är heuristiska, inte kalibrerade
- Ingen OOD-detektion (väljer alltid "nåt")
- Confusion mellan liknande verktyg (smhi_weather vs smhi_temperature)
- Ingen schema-validering (väljer verktyg utan nödvändiga parametrar)

### Hur NEXUS förbättrar

1. **Embedding-first scoring:** NEXUS använder cosine similarity som bassignal istället för
   heuristiska vikter. Bonusar för zon/keyword-matchning är små tillägg (+0.05, +0.02)

2. **Cross-encoder reranking:** Flashrank-modellen rerankar top-kandidater med djupare
   semantisk förståelse

3. **Platt-kalibrering:** Raw scores kalibreras till sannolikheter, vilket gör band-trösklar
   meningsfulla ("0.95 = 95% sannolikhet att detta är rätt verktyg")

4. **Schema verification:** Post-selection kontroll säkerställer att frågan innehåller
   nödvändiga parametrar (location, tidsperiod, etc.)

5. **Confusion pair monitoring:** Space Auditor identifierar verktygspar som är farligt lika
   i embedding-space och flaggar dem för separation

6. **Hard negative mining:** Systematisk identifiering av verktyg som ofta felaktigt väljs
   istället för det korrekta verktyget

7. **Syntetisk testning:** Forge genererar adversarial-frågor som testar disambiguation

8. **Självförbättring:** Auto Loop identifierar routing-fel, analyserar orsaker, och föreslår
   metadataförbättringar (bättre beskrivningar, keywords, etc.)

---

## 10. Confidence Band Cascade

Routing-beslut klassificeras i 5 band baserat på kalibrerad confidence:

| Band | Score | Margin | Namn | Åtgärd | Latens |
|------|-------|--------|------|--------|--------|
| **0** | ≥0.95 | ≥0.20 | DIRECT | Direkt routing, ingen LLM | ~5ms |
| **1** | ≥0.80 | ≥0.10 | VERIFY | Snabb namespace-verifiering | ~50ms |
| **2** | ≥0.60 | — | TOP-3 LLM | Presentera top-3, LLM väljer | ~150ms |
| **3** | ≥0.40 | — | DECOMPOSE | Dela upp/reformulera frågan | ~200ms |
| **4** | <0.40 | — | OOD FALLBACK | Ingen matchning, generell fallback | — |

**Mål:** >80% av alla frågor ska hamna i Band 0 (DIRECT) = routing utan LLM-anrop.

**Margin** = absolut skillnad mellan top-1 och top-2 score. Hög margin = hög separation =
säkrare val.

---

## 11. Kalibrering & OOD-detektion

### Platt-kalibrering

Konverterar raw reranker-scores till kalibrerade sannolikheter. Fittas på historiska
routing-events med `scipy.optimize.minimize` (L-BFGS-B).

```
P(correct) = 1 / (1 + exp(A × raw_score - B))
```

**Mål:** ECE (Expected Calibration Error) <0.05 för band 0-1, <0.10 för band 2.

### DATS (Distance-Aware Temperature Scaling)

Per-zone kalibrering som tar hänsyn till avstånd från zone centroid:

```
T_effective = T_base × (1 + α × distance_from_centroid)
```

Zoner långt från centroid får högre temperatur (mer osäkerhet).

### OOD-detektion

**Dual-gate approach:**

1. **Energy Score:** `E(x) = -log(Σ exp(f_i(x)))` — hög energi = ovanlig input
2. **KNN Distance:** FAISS-baserad nearest-neighbor search — stort avstånd = OOD

**Borderline-fall:** Om energy score är i gråzonen (mellan threshold och threshold×0.7),
aktiveras KNN som backup.

**Dark Matter:** OOD-frågor klustras med DBSCAN och presenteras i dashboarden som
potentiella nya verktyg.

---

## 12. Dashboard & Övervakning

NEXUS har ett komplett admin-dashboard tillgängligt på `/admin/nexus` med 6 flikar:

### Översikt

Precision-dashboard med 4 sektioner:

| Sektion | Metriker |
|---------|----------|
| **Routing Health** | Band-0 rate, ECE, OOD rate |
| **Calibration** | Platt-kalibrerad, namespace purity |
| **Retrieval Quality** | Total events, tools, hard negatives |
| **Embedding Health** | Multi-intent rate, schema match, reranker delta |

Plus: Fas & Retrieval-vikter panel med live routing-konfiguration.

### RYMD (Space Auditor)

- UMAP 2D-visualisering av alla verktyg
- Silhouette score, cluster purity, confusion risk
- Hubness-varningar
- Confusion matrix

### FORGE (Synth Forge)

- Generera testfrågor per verktyg/kategori
- Visa frågor grupperade per verktyg och svårighetsgrad
- Roundtrip-verifieringsstatus

### LOOP (Auto Loop)

- Starta/pausa auto-loop per kategori/namespace/verktyg
- Visa loop-historik med status
- Metadata-förslag med embedding delta
- Per-förslag godkänn/avvisa

### LEDGER (Eval Ledger)

- 5-stage pipeline metriker
- Per-namespace breakdown
- 30-dagars trend
- Reranker pre/post delta

### DEPLOY (Deploy Control)

- Triple-gate status per verktyg
- Promote/Rollback med bekräftelsedialog
- Detaljer per gate med krav och tröskelförklaringar

---

## 13. API-referens

### Health & Config

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/health` | GET | Systemstatus, version, antal zoner |
| `/api/v1/nexus/zones` | GET | Alla zon-konfigurationer |
| `/api/v1/nexus/config` | GET | Komplett NEXUS-konfiguration |
| `/api/v1/nexus/tools` | GET | Lista alla plattformsverktyg |
| `/api/v1/nexus/overview/metrics` | GET | Aggregerade precision-metriker |

### Routing

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/routing/analyze` | POST | QUL-analys (ingen DB/LLM) |
| `/api/v1/nexus/routing/route` | POST | Full routing pipeline |
| `/api/v1/nexus/routing/events` | GET | Routing-historik (paginated) |
| `/api/v1/nexus/routing/band-distribution` | GET | Band-fördelning |
| `/api/v1/nexus/routing/events/{id}/feedback` | POST | Logga feedback |

### Space Auditor

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/space/health` | GET | Separation-metriker |
| `/api/v1/nexus/space/snapshot` | GET | UMAP-koordinater |
| `/api/v1/nexus/space/confusion` | GET | Confusion-par |
| `/api/v1/nexus/space/hubness` | GET | Hubness-varningar |

### Synth Forge

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/forge/generate` | POST | Generera testfrågor |
| `/api/v1/nexus/forge/cases` | GET | Lista testfall |
| `/api/v1/nexus/forge/cases/{id}` | DELETE | Radera testfall |

### Auto Loop

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/loop/start` | POST | Starta auto-loop |
| `/api/v1/nexus/loop/runs` | GET | Lista körningar |
| `/api/v1/nexus/loop/runs/{id}` | GET | Detaljerad körningsinfo |
| `/api/v1/nexus/loop/runs/{id}/approve` | POST | Godkänn förslag |

### Eval Ledger

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/ledger/metrics` | GET | Pipeline-metriker |
| `/api/v1/nexus/ledger/trend` | GET | 30-dagars trend |

### Deploy Control

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/deploy/gates/{tool_id}` | GET | Gate-status |
| `/api/v1/nexus/deploy/promote/{tool_id}` | POST | Promota verktyg |
| `/api/v1/nexus/deploy/rollback/{tool_id}` | POST | Rulla tillbaka |

### Kalibrering

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/calibration/params` | GET | Kalibreringsparametrar |
| `/api/v1/nexus/calibration/fit` | POST | Fitta Platt-skalare |
| `/api/v1/nexus/calibration/ece` | GET | ECE per zon |

### Dark Matter

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/dark-matter/clusters` | GET | OOD-kluster |
| `/api/v1/nexus/dark-matter/{id}/review` | POST | Granska kluster |

### Shadow Observer

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/shadow/report` | GET | Jämförelserapport |

### Admin

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/v1/nexus/reset` | POST | Nollställ all NEXUS-data |
| `/api/v1/nexus/tools/live-routing` | GET | Live routing-konfiguration |

---

## 14. Filstruktur

### Backend

```
surfsense_backend/app/nexus/
├── __init__.py
├── config.py                          # Zoner, band-trösklar, konstanter
├── models.py                          # SQLAlchemy: 9 nexus_* tabeller
├── schemas.py                         # Pydantic request/response-typer
├── service.py                         # Orchestrator: kopplar alla komponenter
├── routes.py                          # FastAPI endpoints (/api/v1/nexus/...)
├── platform_bridge.py                 # Import från produktion (verktyg, intents)
├── embeddings.py                      # Koppling till embedding-modell & reranker
├── llm.py                             # LiteLLM-anrop (Forge, Deploy Gate 3)
│
├── routing/
│   ├── qul.py                         # Query Understanding Layer
│   ├── select_then_route.py           # Select-Then-Route pattern
│   ├── confidence_bands.py            # 5-band cascade
│   ├── ood_detector.py                # Energy + KNN OOD-detektion
│   ├── schema_verifier.py             # Post-selection param/geo/temporal check
│   ├── zone_manager.py                # Zone-arkitektur
│   ├── hard_negative_bank.py          # False-negative mining
│   └── shadow_observer.py             # Jämför NEXUS vs produktion
│
├── calibration/
│   ├── platt_scaler.py                # Platt sigmoid-kalibrering
│   ├── dats_scaler.py                 # Distance-Aware Temperature Scaling
│   └── ece_monitor.py                 # Expected Calibration Error
│
└── layers/
    ├── space_auditor.py               # UMAP, silhouette, confusion, hubness
    ├── synth_forge.py                 # LLM-genererade testfrågor (4 svårigheter)
    ├── auto_loop.py                   # 7-stegs självförbättring
    ├── eval_ledger.py                 # 5-stage pipeline-metriker
    └── deploy_control.py              # Triple-gate lifecycle
```

### Frontend

```
surfsense_web/
├── app/admin/nexus/
│   ├── page.tsx                       # /admin/nexus huvudsida
│   └── layout.tsx
│
├── components/admin/nexus/
│   ├── nexus-dashboard.tsx            # Tab-orchestrator + Översikt
│   ├── tabs/
│   │   ├── space-tab.tsx              # RYMD: UMAP + separation + confusion
│   │   ├── forge-tab.tsx              # FORGE: Testgenerering
│   │   ├── loop-tab.tsx               # LOOP: Auto-loop status & kontroll
│   │   ├── ledger-tab.tsx             # LEDGER: Pipeline-metriker
│   │   └── deploy-tab.tsx             # DEPLOY: Triple-gate lifecycle
│   └── shared/
│       ├── zone-health-card.tsx       # Zon-hälso-widget
│       ├── confusion-matrix.tsx       # Confusion-par
│       ├── band-distribution.tsx      # Band-fördelning chart
│       └── dark-matter-panel.tsx      # OOD-kluster
│
└── lib/apis/
    └── nexus-api.service.ts           # TypeScript API-klient
```

### Databas (nexus_* tabeller)

| Tabell | Syfte |
|--------|-------|
| `nexus_routing_events` | Varje routing-beslut |
| `nexus_synthetic_cases` | Genererade testfrågor |
| `nexus_auto_loop_runs` | Auto-loop körningar |
| `nexus_space_snapshots` | UMAP embeddings |
| `nexus_dark_matter_queries` | OOD-frågor |
| `nexus_zone_config` | Zon-metriker |
| `nexus_calibration_params` | Platt A/B parametrar |
| `nexus_pipeline_metrics` | Eval Ledger steg-metriker |
| `nexus_hard_negatives` | Hard negative bank |
| `nexus_deploy_states` | Lifecycle-status per verktyg |

---

## Målmetriker

| Metrik | Mål | Beskrivning |
|--------|-----|-------------|
| Band-0 Throughput | >80% | Andel frågor som routas direkt utan LLM |
| ECE Global | <0.05 | Kalibrerad confidence matchar faktisk precision |
| Namespace Purity | >92% | Rätt zon/namespace varje gång |
| OOD Rate | <3% | Andel frågor utan matchande verktyg |
| Reranker Delta | >+12pp | Cross-encoder förbättrar över bi-encoder |
| Syntetiska testfall/verktyg | 16 | 4 svårigheter × 4 frågor |
| Schema Match Rate | >95% | Valda verktyg har nödvändiga parametrar |
| Multi-intent Detection | >90% | Sammansatta frågor identifieras korrekt |
