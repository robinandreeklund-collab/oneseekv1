# NEXUS — Retrieval Intelligence Platform

> **Version:** 2.2.0
> **Källa:** `docs/eval/nexus.md` (komplett specifikation)
> **Princip:** Fristående system — 0 beroenden till gammalt eval-system

---

## Arkitektur

```
NEXUS — 5 Lager + Precision Routing Stack
┌─────────────────────────────────────────────────────────────────────────────┐
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐│
│  │  SPACE     │  │  SYNTH    │  │   AUTO    │  │   EVAL    │  │  DEPLOY   ││
│  │  AUDITOR   │  │  FORGE    │  │   LOOP    │  │  LEDGER   │  │  CONTROL  ││
│  │  Lager 1   │  │  Lager 2  │  │  Lager 3  │  │  Lager 4  │  │  Lager 5  ││
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘│
│        │               │               │               │               │    │
│  Visa embedding  Generera LLM-  Förbättra    Logga pipeline-  Deploya      │
│  rymd-hälsa     testfrågor      metadata     steg-metriker   godkänt      │
└────────┴───────────────┴───────────────┴───────────────┴───────────────┴────┘

Precision Routing Stack (QUL → OOD → StR → Bands → Schema)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Query → [QUL] → [OOD Gate] → [Select-Then-Route] → [Rerank] →           │
│          [Platt Calibrate] → [DATS Zone] → [Confidence Band] → [Schema]   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Modulstruktur

```
app/nexus/
├── __init__.py
├── config.py                    ← Konstanter, trösklar, zone-definitioner
├── models.py                    ← SQLAlchemy (9 nexus_* tabeller)
├── schemas.py                   ← Pydantic request/response-schemas
├── routes.py                    ← FastAPI endpoints (/api/v1/nexus/...)
├── service.py                   ← Orchestration (kopplar alla lager)
├── llm.py                       ← LiteLLM-integration (Forge, Loop, Gate 3)
├── embeddings.py                ← KBLab sentence-bert + cross-encoder rerank
├── platform_bridge.py           ← Importerar RIKTIGA verktyg från OneSeek
├── seed.py                      ← DB-seed med initial data
│
├── layers/
│   ├── space_auditor.py         ← Lager 1: UMAP, silhouette, confusion, hubness
│   ├── synth_forge.py           ← Lager 2: LLM-genererade testfrågor (4 nivåer)
│   ├── auto_loop.py             ← Lager 3: 7-steg förbättringsloop + LLM root cause
│   ├── eval_ledger.py           ← Lager 4: MRR@10, nDCG@5, P@1, P@5, reranker delta
│   └── deploy_control.py        ← Lager 5: Triple-gate (separation, eval, LLM-judge)
│
├── routing/
│   ├── qul.py                   ← Query Understanding Layer (NER, gazetteer, normalisering)
│   ├── confidence_bands.py      ← 5-band cascade (Band 0-4)
│   ├── zone_manager.py          ← 4 zoner: kunskap, skapande, jämförelse, konversation
│   ├── select_then_route.py     ← Zone-selection → per-zone retrieval → cross-encoder rerank
│   ├── schema_verifier.py       ← Post-selection parameter/geo/temporal check
│   ├── ood_detector.py          ← Energy Score + KNN backup + UAEval4RAG kategorier
│   ├── hard_negative_bank.py    ← Positive-aware hard negative mining (4 metoder)
│   └── shadow_observer.py       ← Jämför NEXUS vs plattformens routing read-only
│
└── calibration/
    ├── platt_scaler.py          ← Platt sigmoid-kalibrering (scipy L-BFGS-B)
    ├── dats_scaler.py           ← Distance-Aware Temperature Scaling per zon
    └── ece_monitor.py           ← Expected Calibration Error tracking
```

---

## 5 Lager — Detaljer

### Lager 1: SPACE AUDITOR
Mäter kontinuerligt embedding-rymd-hälsa:
- **Silhouette score** per zon (global + per-namespace)
- **UMAP 2D** projektioner (PCA fallback utan umap-learn)
- **Namespace-filtrering** — visa rymden för ett specifikt namespace eller zon
- **Confusion pairs** — verktyg som är för nära varandra (threshold 0.85)
- **Hubness detection** — verktyg som dominerar NN-resultat (threshold 0.08)
- **Inter-zone distances** — centroid-avstånd mellan zoner
- **Snapshot namespace** — varje punkt inkluderar namespace för filtrering i UI

### Lager 2: SYNTH FORGE
LLM-genererade testfrågor via LiteLLM (konfigurerad modell):
- **4 svårighetsnivåer**: easy, medium, hard, adversarial
- **4 frågor per nivå per verktyg** = 16 testfall/verktyg
- **Roundtrip-verifiering**: query → retrieve → check top-3
- **Adversarial cases** → hard negative bank
- **Expected intent/agent**: deriveras automatiskt från verktygets zon och namespace-mappning

### Lager 3: AUTO LOOP
7-stegs självförbättrande pipeline:
1. Ladda testfall (från Synth Forge)
2. Evaluera mot NEXUS routing + plattformsrouting (shadow compare)
3. Klustra misslyckanden (DBSCAN på embeddings)
4. **LLM root cause analysis** per kluster
5. Testa fix isolerat (**beräkna embedding delta**)
6. Köa för human review
7. Om godkänt: deploya & reindexera

**3-nivå pipeline-mätning (Intent → Agent → Tool):**
- Varje testfall har `expected_intent`, `expected_agent` och `expected_tool`
- Auto-loop mäter accuracy på alla tre nivåer per iteration
- Kaskadeffekter synliggörs — fel intent → troligen fel agent → troligen fel tool
- Metriker: `intent_accuracy`, `agent_accuracy`, `precision_at_1` (tool)

**LLM Tool Judge:**
- Kör parallellt med NEXUS embedding-baserade scoring
- Skickar top-5 kandidater till LLM som väljer bästa verktyg med motivering
- Dubbelsidigt: jämför NEXUS accuracy vs LLM accuracy mot expected_tool
- 2x2 korsmatris: båda rätt, bara NEXUS rätt, bara LLM rätt, båda fel
- Oenigheter loggas med winner-klassificering (nexus/llm/neither/tie)

### Lager 4: EVAL LEDGER
5-stegs pipeline-metriker:
1. Intent routing
2. Route selection
3. Bigtool retrieval
4. Reranker effekt (pre/post delta)
5. End-to-end quality

Per-namespace breakdown. MRR@10, nDCG@5, P@1, P@5.

### Lager 5: DEPLOY CONTROL
Triple-gate lifecycle med **DB-persisterad state**:
- **Gate 1** — Separation: silhouette score ≥ 0.65
- **Gate 2** — Eval: success rate ≥ 80%, hard neg ≥ 85%, adversarial ≥ 80%
- **Gate 3** — LLM Judge: description clarity ≥ 4.0, keyword relevance ≥ 4.0, disambiguation ≥ 4.0
- Lifecycle: `REVIEW → STAGING → LIVE → (ROLLED_BACK)`
- State persisteras i `nexus_routing_events` med deploy-metadata

---

## Precision Routing Stack v2.1

### Pipeline: QUL → OOD → StR → Rerank → Calibrate → Band → Schema

| Steg | Modul | Beskrivning |
|------|-------|-------------|
| 1. QUL | `routing/qul.py` | Svenska NER, kommun-gazetteer (290+), normalisering, multi-intent detection |
| 2. OOD Gate | `routing/ood_detector.py` | Energy score (threshold -5.0) + KNN backup (FAISS, k=5, threshold 2.5) |
| 3. Select-Then-Route | `routing/select_then_route.py` | Zone-selection → per-zone retrieval (top-5/zon) → merge |
| 4. Rerank | `embeddings.py` | Cross-encoder reranking på ~15 kandidater |
| 5. Calibrate | `calibration/platt_scaler.py` | Platt sigmoid → calibrated probability |
| 6. DATS | `calibration/dats_scaler.py` | Distance-Aware Temperature per zon |
| 7. Confidence Band | `routing/confidence_bands.py` | Band 0 [≥0.95]: direkt, Band 1 [≥0.80]: verify, Band 2 [≥0.60]: top-3, Band 3 [≥0.40]: decompose, Band 4 [<0.40]: OOD |
| 8. Schema Verify | `routing/schema_verifier.py` | Required params, geographic scope, temporal scope |

### Confidence Bands

| Band | Score Range | Margin | Action |
|------|-------------|--------|--------|
| 0 | ≥ 0.95 | ≥ 0.20 | Direkt routing, ingen LLM |
| 1 | ≥ 0.80 | ≥ 0.10 | Namespace-verifiering, minimal LLM |
| 2 | ≥ 0.60 | — | Top-3 kandidater, LLM väljer |
| 3 | ≥ 0.40 | — | Decompose / reformulera |
| 4 | < 0.40 | — | OOD → fallback |

### UAEval4RAG — 6 OOD-kategorier

| Kategori | Beskrivning |
|----------|-------------|
| `no_tool` | Ingen matchande verktyg finns |
| `geo_scope` | Fråga utanför geografisk räckvidd (t.ex. "väder i Paris") |
| `temporal_scope` | Fråga utanför temporal räckvidd (t.ex. "1987") |
| `ambiguous` | Tvetydig fråga, flera möjliga tolkningar |
| `conflicting` | Motstridiga krav i frågan |
| `underspecified` | Saknar nödvändig information |

---

## Databas — 9 Tabeller

Alla tabeller har `nexus_` prefix. Separata från legacy eval-systemet.

| Tabell | Beskrivning |
|--------|-------------|
| `nexus_synthetic_cases` | Synth Forge-genererade testfall (inkl. expected_intent, expected_agent) |
| `nexus_space_snapshots` | Embedding-rymd snapshots (UMAP coords) |
| `nexus_auto_loop_runs` | Auto-loop körningshistorik |
| `nexus_pipeline_metrics` | Pipeline-steg metriker (5 stages) |
| `nexus_calibration_params` | Platt/DATS kalibrering per zon |
| `nexus_dark_matter_queries` | OOD queries med UAEval4RAG-kategori |
| `nexus_hard_negatives` | Hard negative par (4 mining-metoder) |
| `nexus_zone_config` | Zone-konfiguration med centroids |
| `nexus_routing_events` | Alla routing-beslut med feedback |

---

## API Endpoints

```
# Health & Config
GET    /api/v1/nexus/health
GET    /api/v1/nexus/zones
GET    /api/v1/nexus/config

# Routing
POST   /api/v1/nexus/routing/analyze
POST   /api/v1/nexus/routing/route
GET    /api/v1/nexus/routing/events

# Space Auditor (Lager 1)
GET    /api/v1/nexus/space/health
GET    /api/v1/nexus/space/snapshot
GET    /api/v1/nexus/space/confusion
GET    /api/v1/nexus/space/hubness

# Synth Forge (Lager 2)
POST   /api/v1/nexus/forge/generate
GET    /api/v1/nexus/forge/cases
DELETE /api/v1/nexus/forge/cases/{id}

# Auto Loop (Lager 3)
POST   /api/v1/nexus/loop/start
POST   /api/v1/nexus/loop/start-stream    # SSE med 3-nivå metrics + LLM Judge
GET    /api/v1/nexus/loop/runs
GET    /api/v1/nexus/loop/runs/{id}
POST   /api/v1/nexus/loop/runs/{id}/approve

# Eval Ledger (Lager 4)
GET    /api/v1/nexus/ledger/metrics
GET    /api/v1/nexus/ledger/trend

# Deploy Control (Lager 5)
GET    /api/v1/nexus/deploy/gates/{tool_id}
POST   /api/v1/nexus/deploy/promote/{tool_id}
POST   /api/v1/nexus/deploy/rollback/{tool_id}

# Dark Matter
GET    /api/v1/nexus/dark-matter/clusters
POST   /api/v1/nexus/dark-matter/{id}/review

# Calibration
GET    /api/v1/nexus/calibration/params
POST   /api/v1/nexus/calibration/fit
GET    /api/v1/nexus/calibration/ece

# Shadow (Platform Comparison)
GET    /api/v1/nexus/shadow/report
POST   /api/v1/nexus/shadow/compare
```

---

## Frontend — Admin UI

```
surfsense_web/
├── app/admin/nexus/page.tsx          ← /admin/nexus
├── components/admin/nexus/
│   ├── nexus-dashboard.tsx           ← 6-tab orchestrator
│   ├── tabs/
│   │   ├── space-tab.tsx             ← UMAP med namespace/zon-filter + hubness + confusion
│   │   ├── forge-tab.tsx             ← Generera testfrågor per verktyg/kategori
│   │   ├── loop-tab.tsx              ← Auto-loop med 3-nivå metrics + LLM Judge korsmatris
│   │   ├── ledger-tab.tsx            ← 5-stage pipeline metriker
│   │   └── deploy-tab.tsx            ← Triple-gate per verktyg, promote/rollback
│   └── shared/
│       ├── zone-health-card.tsx      ← Zon-hälsa med ECE, Band-0, OOD rate
│       ├── band-distribution.tsx     ← Confidence band-fördelning
│       ├── confusion-matrix.tsx      ← Confusion-par
│       └── dark-matter-panel.tsx     ← OOD-kluster
└── lib/apis/nexus-api.service.ts     ← 27+ API-metoder
```

### Overview Tab Metrics
- **Band-0 Throughput Rate** — % queries som routas direkt utan LLM (mål: >80%)
- **ECE Global** — Expected Calibration Error (mål: <0.05)
- **OOD Rate** — % queries klassade som dark matter (mål: <3%)
- **Namespace Purity** — % korrekt zon per query (mål: >92%)

---

## Platform Bridge

`platform_bridge.py` importerar RIKTIGA verktyg från OneSeek:
- `app/agents/new_chat/tools/registry.py` → BUILTIN_TOOLS
- `app/agents/new_chat/bigtool_store.py` → TOOL_NAMESPACE_OVERRIDES, TOOL_KEYWORDS
- 9 domän-moduler: SMHI, SCB, Kolada, Riksdagen, Trafikverket, Bolagsverket, Marketplace, Skolverket, Geoapify
- Extern model specs (compare mode)
- Intent definitions från `intent_definition_service`
- Agent-lista dynamiskt från `supervisor_constants`

**Ingen try/except silencing** — om plattformen inte kan importeras, fail loudly.

---

## Målbild

| Metrik | Target |
|--------|--------|
| Band-0 Throughput | >80% |
| ECE Global | <0.05 |
| Namespace Purity | >92% |
| OOD Rate | <3% |
| Reranker Delta | >+12pp |
| Syntetiska testfall/verktyg | 16 |
| Auto Loop-förbättring | Mätbar separation-ökning per vecka |
| Intent Accuracy | >90% |
| Agent Accuracy | >85% |
| Tool Accuracy (P@1) | >80% |
| LLM Judge Agreement | >75% |
