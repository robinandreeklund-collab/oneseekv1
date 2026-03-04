# NEXUS — Retrieval Intelligence Platform: Utvecklingsplan

> **Datum:** 2026-03-04
> **Källa:** `docs/eval/nexus.md` (komplett specifikation)
> **Mål:** Bygga NEXUS från grunden som ett fristående system, 100% oberoende av det befintliga eval-systemet
> **Branch:** `claude/nexus-dev-plan-hjhsk`
> **Princip:** Ingen kod delas med `tool_evaluation_service.py`, `metadata_audit_service.py`, eller `eval/` JSON-filer

---

## Beslut

| Fråga | Beslut |
|-------|--------|
| Relation till gamla eval | **Helt oberoende** — noll koppling till befintligt eval-system |
| Startpunkt | **Sprint 1 + DB setup** — fullständig modulstruktur + databas + grundläggande routing |
| Frontend-strategi | **Incrementellt** — varje sprint inkluderar sin del av UI:t |

---

## Arkitektur — Fristående modul

```
surfsense_backend/app/nexus/          ← HELT NY katalog, oberoende av eval-systemet
├── __init__.py
├── models.py                         ← SQLAlchemy-modeller (nexus_* tabeller)
├── schemas.py                        ← Pydantic request/response-schemas
├── config.py                         ← NEXUS-specifik konfiguration & konstanter
│
├── layers/                           ← De 5 NEXUS-lagren
│   ├── __init__.py
│   ├── space_auditor.py              ← Lager 1: Embedding-rymd-analys
│   ├── synth_forge.py                ← Lager 2: LLM-genererade testfrågor
│   ├── auto_loop.py                  ← Lager 3: Självförbättrande loop
│   ├── eval_ledger.py                ← Lager 4: Pipeline-steg-metriker
│   └── deploy_control.py             ← Lager 5: Triple-gate lifecycle
│
├── routing/                          ← Precision Routing Stack
│   ├── __init__.py
│   ├── qul.py                        ← Query Understanding Layer (spaCy, gazetteer)
│   ├── confidence_bands.py           ← 5-band cascade med Platt + DATS
│   ├── zone_manager.py               ← Zone-arkitektur ([KUNSK], [MYNDG], etc.)
│   ├── select_then_route.py          ← StR-pattern
│   ├── schema_verifier.py            ← Post-selection parameter/geo/temporal check
│   ├── ood_detector.py               ← Energy Score + KNN backup
│   └── hard_negative_bank.py         ← False-negative-medveten mining
│
├── calibration/                      ← Kalibreringssystem
│   ├── __init__.py
│   ├── platt_scaler.py               ← Platt sigmoid-kalibrering
│   ├── dats_scaler.py                ← Distance-Aware Temperature Scaling per zon
│   └── ece_monitor.py                ← Expected Calibration Error-tracking
│
├── routes.py                         ← FastAPI-endpoints (/api/v1/nexus/...)
└── service.py                        ← Orchestration-service (kopplar lagren)

surfsense_web/
├── app/admin/nexus/                  ← HELT NY admin-sektion
│   ├── page.tsx                      ← Huvudsida med 5 tabs
│   └── layout.tsx
├── components/admin/nexus/           ← NEXUS UI-komponenter (byggs incrementellt)
│   ├── nexus-dashboard.tsx           ← Tab-orchestrator (Sprint 1)
│   ├── tabs/
│   │   ├── space-tab.tsx             ← RYMD: UMAP + separation + confusion (Sprint 2)
│   │   ├── forge-tab.tsx             ← FORGE: Syntetisk testgenerering (Sprint 3)
│   │   ├── loop-tab.tsx              ← LOOP: Auto-loop status & kontroll (Sprint 3)
│   │   ├── ledger-tab.tsx            ← LEDGER: Pipeline-metriker (Sprint 3)
│   │   └── deploy-tab.tsx            ← DEPLOY: Triple-gate lifecycle (Sprint 4)
│   └── shared/
│       ├── zone-health-card.tsx      ← Återanvändbar zon-hälso-widget (Sprint 1)
│       ├── confusion-matrix.tsx      ← Confusion-par-visualisering (Sprint 2)
│       ├── band-distribution.tsx     ← Confidence band distribution chart (Sprint 1)
│       └── dark-matter-panel.tsx     ← OOD-kluster-vy (Sprint 3)
└── lib/apis/nexus-api.service.ts     ← API-klient för NEXUS-endpoints (Sprint 1, utökas varje sprint)

surfsense_backend/alembic/versions/
└── xxx_create_nexus_tables.py        ← EN enda migration för alla NEXUS-tabeller
```

---

## Databasschema — Nya tabeller (alla med `nexus_` prefix)

### Migration: `xxx_create_nexus_tables.py`

```sql
-- 1. Syntetiska testfall (Synth Forge)
CREATE TABLE nexus_synthetic_cases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tool_id TEXT NOT NULL,
  namespace TEXT NOT NULL,
  question TEXT NOT NULL,
  difficulty TEXT NOT NULL,          -- 'easy'|'medium'|'hard'|'adversarial'
  expected_tool TEXT,
  expected_not_tools TEXT[],         -- adversarial: bör INTE välja dessa
  generation_model TEXT,
  generation_run_id UUID,
  roundtrip_verified BOOL DEFAULT FALSE,
  quality_score FLOAT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_nexus_synth_tool_id ON nexus_synthetic_cases(tool_id);
CREATE INDEX ix_nexus_synth_difficulty ON nexus_synthetic_cases(difficulty);

-- 2. Embedding-rymd snapshots (Space Auditor)
CREATE TABLE nexus_space_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_at TIMESTAMPTZ DEFAULT now(),
  tool_id TEXT NOT NULL,
  namespace TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  umap_x FLOAT8,
  umap_y FLOAT8,
  cluster_label INT,
  silhouette_score FLOAT8,
  nearest_neighbor_tool TEXT,
  nearest_neighbor_distance FLOAT8
);
CREATE INDEX ix_nexus_space_snapshot_at ON nexus_space_snapshots(snapshot_at);
CREATE INDEX ix_nexus_space_tool_id ON nexus_space_snapshots(tool_id);

-- 3. Auto-loop körningar
CREATE TABLE nexus_auto_loop_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  loop_number INT NOT NULL,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  total_tests INT,
  failures INT,
  metadata_proposals JSONB,
  approved_proposals INT,
  embedding_delta FLOAT8,
  status TEXT DEFAULT 'pending'     -- 'pending'|'running'|'waiting_review'|'done'|'failed'
);
CREATE INDEX ix_nexus_loop_status ON nexus_auto_loop_runs(status);

-- 4. Pipeline-steg metriker (Eval Ledger)
CREATE TABLE nexus_pipeline_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL,
  stage INT NOT NULL,               -- 1=intent, 2=route, 3=bigtool, 4=rerank, 5=e2e
  stage_name TEXT NOT NULL,
  namespace TEXT,
  precision_at_1 FLOAT8,
  precision_at_5 FLOAT8,
  mrr_at_10 FLOAT8,
  ndcg_at_5 FLOAT8,
  hard_negative_precision FLOAT8,
  reranker_delta FLOAT8,
  recorded_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_nexus_pipeline_run_id ON nexus_pipeline_metrics(run_id);
CREATE INDEX ix_nexus_pipeline_stage ON nexus_pipeline_metrics(stage);

-- 5. Confidence calibration per zon
CREATE TABLE nexus_calibration_params (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zone TEXT NOT NULL,
  calibration_method TEXT NOT NULL,  -- 'platt'|'temperature'|'dats'
  param_a FLOAT8,
  param_b FLOAT8,
  temperature FLOAT8,
  ece_score FLOAT8,
  fitted_on_samples INT,
  fitted_at TIMESTAMPTZ DEFAULT now(),
  is_active BOOL DEFAULT TRUE
);
CREATE INDEX ix_nexus_calib_zone ON nexus_calibration_params(zone);

-- 6. OOD / Dark Matter register
CREATE TABLE nexus_dark_matter_queries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text TEXT NOT NULL,
  energy_score FLOAT8 NOT NULL,
  knn_distance FLOAT8,
  uaq_category TEXT,               -- no_tool|geo_scope|temporal_scope|ambiguous|conflicting|underspecified
  cluster_id INT,
  reviewed BOOL DEFAULT FALSE,
  new_tool_candidate TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_nexus_dm_cluster ON nexus_dark_matter_queries(cluster_id);
CREATE INDEX ix_nexus_dm_reviewed ON nexus_dark_matter_queries(reviewed);

-- 7. Hard negative bank
CREATE TABLE nexus_hard_negatives (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  anchor_tool TEXT NOT NULL,
  negative_tool TEXT NOT NULL,
  mining_method TEXT NOT NULL,     -- 'semantic'|'bm25'|'adversarial'|'production_error'
  similarity_score FLOAT8,
  is_false_negative BOOL DEFAULT FALSE,
  adversarial_query TEXT,
  confusion_frequency FLOAT8,
  added_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(anchor_tool, negative_tool)
);
CREATE INDEX ix_nexus_hn_anchor ON nexus_hard_negatives(anchor_tool);

-- 8. Zone-konfiguration + hälsa
CREATE TABLE nexus_zone_config (
  zone TEXT PRIMARY KEY,
  prefix_token TEXT NOT NULL,
  centroid_embedding VECTOR(768),
  silhouette_score FLOAT8,
  inter_zone_min_distance FLOAT8,
  last_reindexed TIMESTAMPTZ,
  ood_energy_threshold FLOAT8 DEFAULT -5.0,
  band0_rate FLOAT8,
  ece_score FLOAT8
);

-- 9. Routing precision events
CREATE TABLE nexus_routing_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text TEXT,
  query_hash TEXT,
  band INT NOT NULL,               -- 0-4
  resolved_zone TEXT,
  selected_tool TEXT,
  raw_reranker_score FLOAT8,
  calibrated_confidence FLOAT8,
  is_multi_intent BOOL,
  sub_query_count INT,
  schema_verified BOOL,
  is_ood BOOL DEFAULT FALSE,
  implicit_feedback TEXT,          -- 'reformulation'|'follow_up'|null
  explicit_feedback INT,           -- -1, 0, 1
  routed_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_nexus_routing_band ON nexus_routing_events(band);
CREATE INDEX ix_nexus_routing_zone ON nexus_routing_events(resolved_zone);
CREATE INDEX ix_nexus_routing_at ON nexus_routing_events(routed_at);
```

---

## Sprint-plan — 4 sprints (UI inkluderat i varje sprint)

---

### Sprint 1: Grund + Fundamental Precision (2 veckor)

**Mål:** Modulstruktur, databas, QUL, kalibrering, OOD-detektion + grundläggande UI-shell.

#### Backend

| # | Uppgift | Fil(er) | Beskrivning |
|---|---------|---------|-------------|
| 1.1 | Skapa NEXUS-modulstruktur | `app/nexus/__init__.py`, alla `__init__.py` | Komplett katalogstruktur med alla submoduler |
| 1.2 | NEXUS config & konstanter | `app/nexus/config.py` | Zone-definitioner (`ZONE_PREFIXES`), band-trösklar, OOD-thresholds, metadata-limits |
| 1.3 | SQLAlchemy-modeller | `app/nexus/models.py` | Alla 9 tabeller ovan som SQLAlchemy ORM-klasser |
| 1.4 | Alembic-migration | `alembic/versions/xxx_create_nexus_tables.py` | EN enda migration för samtliga tabeller + index |
| 1.5 | Pydantic-schemas | `app/nexus/schemas.py` | Request/response-typer: `QueryAnalysis`, `RoutingDecision`, `ZoneConfig`, `SystemHealth`, etc. |
| 1.6 | QUL — Query Understanding Layer | `app/nexus/routing/qul.py` | spaCy `sv_core_news_lg` NER, municipality gazetteer (290 kommuner + förkortningar), intent margin gate (threshold 0.15), Swedish normalization bank |
| 1.7 | Platt-kalibrering | `app/nexus/calibration/platt_scaler.py` | `PlattCalibratedReranker.fit()` + `.calibrate()` — sigmoid-transform, scipy minimize L-BFGS-B |
| 1.8 | Energy Score OOD-detektion | `app/nexus/routing/ood_detector.py` | `DarkMatterDetector` — energy score (threshold -5.0) + KNN backup (FAISS, k=5, threshold 2.5) |
| 1.9 | Confidence Band Cascade | `app/nexus/routing/confidence_bands.py` | 5 bands: [0.95-1.0] direkt, [0.80-0.94] verify, [0.60-0.79] top-3, [0.40-0.59] decompose, [<0.40] OOD |
| 1.10 | Zone Manager grund | `app/nexus/routing/zone_manager.py` | 4 zoner: `kunskap` [KUNSK], `myndigheter` [MYNDG], `handling` [HANDL], `jämförelse` [JAMFR] + namespace→zone mapping |
| 1.11 | NEXUS service (orchestrator) | `app/nexus/service.py` | `NexusService` som kopplar QUL → OOD → bands → zone |
| 1.12 | FastAPI-routes (grund) | `app/nexus/routes.py` | `GET /nexus/health`, `GET /nexus/zones`, `GET /nexus/config`, `POST /nexus/routing/analyze` |
| 1.13 | Registrera NEXUS-router | `app/app.py` (minimal ändring) | `app.include_router(nexus_router, prefix="/api/v1")` |
| 1.14 | Tester Sprint 1 | `tests/test_nexus_qul.py`, `tests/test_nexus_calibration.py`, `tests/test_nexus_ood.py`, `tests/test_nexus_bands.py` | Enhetstester |

#### Frontend (Sprint 1 UI)

| # | Uppgift | Fil(er) | Beskrivning |
|---|---------|---------|-------------|
| 1.15 | NEXUS API-klient (grund) | `lib/apis/nexus-api.service.ts` | `getNexusHealth()`, `getZones()`, `analyzeQuery()` |
| 1.16 | NEXUS dashboard page | `app/admin/nexus/page.tsx`, `layout.tsx` | Ny admin-sida `/admin/nexus` |
| 1.17 | Dashboard orchestrator | `components/admin/nexus/nexus-dashboard.tsx` | 5-tab layout shell (RYMD, FORGE, LOOP, LEDGER, DEPLOY) — placeholder-innehåll i tabs som inte är klara |
| 1.18 | Zone health card | `components/admin/nexus/shared/zone-health-card.tsx` | Visar zon-status: band0-rate, ECE, silhouette |
| 1.19 | Band distribution | `components/admin/nexus/shared/band-distribution.tsx` | Visualiserar confidence band-fördelning (bar chart) |
| 1.20 | Admin sidebar update | `components/admin/admin-layout.tsx` | Lägg till "NEXUS" nav-item |

**Nya Python-beroenden (Sprint 1):**
```
spacy>=3.7 (+ sv_core_news_lg modell)
scipy>=1.12
faiss-cpu>=1.8
numpy (redan installerat)
```

**Koppling till existerande kod (read-only):**
- `bigtool_store.py` → `ToolIndexEntry` — read-only import för att hämta verktygsmetadata
- `app/config/__init__.py` → `Config` — databas-URL, embedding-modell
- `app/db.py` → `Base`, `AsyncSession` — delar SQLAlchemy metadata men EGNA tabeller

---

### Sprint 2: Zone Architecture + Space Auditor (2 veckor)

**Mål:** Zonbaserad retrieval, prefix-embeddings, StR, Space Auditor med visualisering.

#### Backend

| # | Uppgift | Fil(er) | Beskrivning |
|---|---------|---------|-------------|
| 2.1 | Zone-prefix embeddings | `app/nexus/routing/zone_manager.py` (utöka) | `embed_tool_with_zone()`, `embed_query_with_hint()` — KBLab sentence-bert med zone-prefix |
| 2.2 | Select-Then-Route | `app/nexus/routing/select_then_route.py` | Zone-selector → per-zone retrieval (top-5 per zon) → cross-encoder rerank på ~15 kandidater |
| 2.3 | Schema Verifier | `app/nexus/routing/schema_verifier.py` | `TOOL_SCHEMAS` dict, `SchemaVerifier.verify()` — required params, geographic_scope, temporal_scope |
| 2.4 | DATS per-zone kalibrering | `app/nexus/calibration/dats_scaler.py` | `ZonalTemperatureScaler` — distance-aware temperature baserat på centroid-avstånd |
| 2.5 | ECE Monitor | `app/nexus/calibration/ece_monitor.py` | `compute_ece()` per zon, targets: <0.05 band-0/1, <0.10 band-2 |
| 2.6 | Space Auditor | `app/nexus/layers/space_auditor.py` | `SpaceAuditor.compute_separation_matrix()` — UMAP 2D, silhouette score, confusion pairs, hubness detection |
| 2.7 | Full routing pipeline | `app/nexus/service.py` (utöka) | `POST /nexus/routing/route` — QUL → OOD → StR → rerank → bands → schema verify |
| 2.8 | Space + zone endpoints | `app/nexus/routes.py` (utöka) | `GET /nexus/space/health`, `GET /nexus/space/snapshot`, `GET /nexus/space/confusion`, `GET /nexus/space/hubness`, `GET /nexus/zones/{zone}/metrics` |
| 2.9 | Seed zone config | Data seed i migration eller startup | Populera `nexus_zone_config` med 4 zoner, initiala centroids |
| 2.10 | Tester Sprint 2 | `tests/test_nexus_zones.py`, `tests/test_nexus_str.py`, `tests/test_nexus_space.py`, `tests/test_nexus_schema.py` | Enhetstester |

**Nya Python-beroenden (Sprint 2):**
```
umap-learn>=0.5
scikit-learn>=1.4 (silhouette_score, DBSCAN)
```

#### Frontend (Sprint 2 UI)

| # | Uppgift | Fil(er) | Beskrivning |
|---|---------|---------|-------------|
| 2.11 | RYMD tab | `components/admin/nexus/tabs/space-tab.tsx` | UMAP-visualisering (canvas/SVG), silhouette scores per zon, confusion register med sorterbara par |
| 2.12 | Confusion matrix | `components/admin/nexus/shared/confusion-matrix.tsx` | Visar top-N confusion-par med similarity score + trend |
| 2.13 | API-klient utökning | `lib/apis/nexus-api.service.ts` (utöka) | `getSpaceHealth()`, `getSpaceSnapshot()`, `getConfusion()`, `getHubness()` |

---

### Sprint 3: Self-Improvement Loop (2 veckor)

**Mål:** Synth Forge, Hard Negatives, Auto Loop, Eval Ledger.

#### Backend

| # | Uppgift | Fil(er) | Beskrivning |
|---|---------|---------|-------------|
| 3.1 | Synth Forge | `app/nexus/layers/synth_forge.py` | LLM-generering: 4 svårighetsnivåer × 4 frågor per verktyg via LiteLLM, `SYNTH_PROMPT` template, roundtrip-filter (query → retrieve → top-3 check) |
| 3.2 | Hard Negative Bank | `app/nexus/routing/hard_negative_bank.py` | `HardNegativeMiner` — positive-aware filter (threshold 0.80), semi-hard zone (margin 0.15), domain-overlap + parameter-skillnad |
| 3.3 | Eval Ledger | `app/nexus/layers/eval_ledger.py` | 5-stage pipeline metrics: intent → route → bigtool → rerank → e2e. Per-namespace breakdown. Reranker pre/post delta. MRR@10, nDCG@5 |
| 3.4 | Auto Loop | `app/nexus/layers/auto_loop.py` | 7-steg pipeline: generera → eval → cluster failures (DBSCAN) → LLM root cause → testa fix isolerat (embedding delta) → human review queue → deploy & reindex |
| 3.5 | Dark Matter clustering | `app/nexus/routing/ood_detector.py` (utöka) | DBSCAN på OOD-queries, `new_tool_candidate` förslag, kluster-dashboard-data |
| 3.6 | Routing event logging | `app/nexus/service.py` (utöka) | Logga varje routing-beslut till `nexus_routing_events`: band, zone, tool, confidence, multi-intent, schema match |
| 3.7 | Feedback-integration | `app/nexus/service.py` (utöka) | `log_implicit_feedback()` — omformuleringsdetektering, `log_explicit_feedback()` — thumbs up/down kopplas till tool-chain |
| 3.8 | Celery tasks | `app/nexus/tasks.py` (ny) | `forge_generate_task`, `auto_loop_task` — bakgrundsjobb via Celery |
| 3.9 | API-endpoints Sprint 3 | `app/nexus/routes.py` (utöka) | `POST /nexus/forge/generate`, `GET /nexus/forge/cases`, `POST /nexus/loop/start`, `GET /nexus/loop/runs`, `POST /nexus/loop/runs/{id}/approve`, `GET /nexus/ledger/metrics`, `GET /nexus/ledger/trend`, `GET /nexus/dark-matter/clusters`, `GET /nexus/routing/events` |
| 3.10 | Tester Sprint 3 | `tests/test_nexus_forge.py`, `tests/test_nexus_loop.py`, `tests/test_nexus_ledger.py`, `tests/test_nexus_hn.py` | Enhetstester |

#### Frontend (Sprint 3 UI)

| # | Uppgift | Fil(er) | Beskrivning |
|---|---------|---------|-------------|
| 3.11 | FORGE tab | `components/admin/nexus/tabs/forge-tab.tsx` | Generera testfrågor: välj verktyg/provider, status-indikator, visa frågor per svårighetsgrad med roundtrip-status |
| 3.12 | LOOP tab | `components/admin/nexus/tabs/loop-tab.tsx` | Auto-loop: starta/pausa, visa aktiv loop-status, failure clusters, metadata-förslag med diff-vy, [Godkänn]/[Avvisa] |
| 3.13 | LEDGER tab | `components/admin/nexus/tabs/ledger-tab.tsx` | 5-stage pipeline bars, per-namespace breakdown, reranker pre/post delta, 30-dagars trend |
| 3.14 | Dark matter panel | `components/admin/nexus/shared/dark-matter-panel.tsx` | OOD-kluster med antal queries, föreslagna nya verktyg, review-knappar |
| 3.15 | API-klient utökning | `lib/apis/nexus-api.service.ts` (utöka) | Alla Sprint 3 endpoints |

---

### Sprint 4: Deploy Control + Polish (1-2 veckor)

**Mål:** Triple-gate lifecycle, real-time metrics, polish.

#### Backend

| # | Uppgift | Fil(er) | Beskrivning |
|---|---------|---------|-------------|
| 4.1 | Deploy Control | `app/nexus/layers/deploy_control.py` | Triple-gate: Gate 1 (separation score ≥ 0.65), Gate 2 (eval thresholds: success ≥ 80%, hard neg ≥ 85%, adversarial ≥ 80%), Gate 3 (LLM-judge: description clarity ≥ 4.0, keyword relevance ≥ 4.0, disambiguation ≥ 4.0) |
| 4.2 | Deploy endpoints | `app/nexus/routes.py` (utöka) | `GET /nexus/deploy/gates/{tool_id}`, `POST /nexus/deploy/promote/{tool_id}`, `POST /nexus/deploy/rollback/{tool_id}` |
| 4.3 | Calibration endpoints | `app/nexus/routes.py` (utöka) | `GET /nexus/calibration/params`, `POST /nexus/calibration/fit`, `GET /nexus/calibration/ece` |
| 4.4 | Real-time metrics aggregation | `app/nexus/service.py` (utöka) | Band-0 throughput rate, multi-intent detection rate, schema match rate, OOD rate — aggregerade över senaste 24h/7d/30d |
| 4.5 | Tester Sprint 4 | `tests/test_nexus_deploy.py`, `tests/test_nexus_integration.py` | Deploy gate-tester, integration end-to-end |

#### Frontend (Sprint 4 UI)

| # | Uppgift | Fil(er) | Beskrivning |
|---|---------|---------|-------------|
| 4.6 | DEPLOY tab | `components/admin/nexus/tabs/deploy-tab.tsx` | Triple-gate vy per verktyg, lifecycle REVIEW→STAGING→LIVE, override med bekräftelse, rollback |
| 4.7 | Real-time precision dashboard | LEDGER tab (utöka) | Band-0 throughput, multi-intent detect, schema match rate, OOD rate — real-time gauges |
| 4.8 | ECE calibration vy | Space tab eller ny sektion | ECE per zon, Platt A/B params, rekalibrerings-trigger |
| 4.9 | API-klient final | `lib/apis/nexus-api.service.ts` (slutgiltig) | Alla kvarvarande endpoints |
| 4.10 | Polish & e2e-test | Alla filer | Responsiv UI, loading states, error handling, manuell testning |

---

## Integrationspunkter med existerande kod

| Vad | Existerande fil | Hur NEXUS använder | Typ |
|-----|----------------|-------------------|-----|
| Verktygsmetadata | `bigtool_store.py` → `ToolIndexEntry` | **Import read-only** — tool_id, namespace, embeddings, keywords | Read |
| Embedding-modell | `bigtool_store.py` → embedding-funktion | Återanvänder samma KBLab sentence-bert | Read |
| LLM-anrop | `app/config/__init__.py` → LiteLLM config | Synth Forge + Auto Loop + Deploy Gate 3 | Read |
| Databas | `app/db.py` → `Base`, `AsyncSession` | Delar SQLAlchemy Base + session, EGNA `nexus_*` tabeller | Shared |
| FastAPI | `app/app.py` → app factory | `include_router(nexus_router)` — EN rad tillagd | Minimal write |
| Auth | `app/users.py` → FastAPI-Users JWT | NEXUS-endpoints skyddas med samma auth | Read |
| Celery | `celery_worker.py` → worker config | Auto Loop + Forge tasks registreras | Minimal write |

**Totalt antal ändrade befintliga filer:** 2 (en rad vardera i `app.py` och `celery_worker.py`)

---

## API-endpoints (komplett)

```
# Health & Config (Sprint 1)
GET    /api/v1/nexus/health                    → SystemHealth
GET    /api/v1/nexus/zones                     → list[ZoneConfig]
GET    /api/v1/nexus/config                    → NexusConfig

# Routing — Precision Stack (Sprint 1-2)
POST   /api/v1/nexus/routing/analyze           → QueryAnalysis (QUL output)
POST   /api/v1/nexus/routing/route             → RoutingDecision (full stack)
GET    /api/v1/nexus/routing/events            → list[RoutingEvent] (paginated)

# Space Auditor — Lager 1 (Sprint 2)
GET    /api/v1/nexus/space/health              → SpaceHealthReport
GET    /api/v1/nexus/space/snapshot            → SpaceSnapshot (UMAP coords)
GET    /api/v1/nexus/space/confusion           → list[ConfusionPair]
GET    /api/v1/nexus/space/hubness             → list[HubnessReport]

# Synth Forge — Lager 2 (Sprint 3)
POST   /api/v1/nexus/forge/generate            → ForgeRunResult
GET    /api/v1/nexus/forge/cases               → list[SyntheticCase]
DELETE /api/v1/nexus/forge/cases/{id}          → OK

# Auto Loop — Lager 3 (Sprint 3)
POST   /api/v1/nexus/loop/start               → AutoLoopRun
GET    /api/v1/nexus/loop/runs                 → list[AutoLoopRun]
GET    /api/v1/nexus/loop/runs/{id}            → AutoLoopRunDetail
POST   /api/v1/nexus/loop/runs/{id}/approve    → OK

# Eval Ledger — Lager 4 (Sprint 3)
GET    /api/v1/nexus/ledger/metrics            → PipelineMetricsSummary
GET    /api/v1/nexus/ledger/metrics/{stage}    → StageMetrics
GET    /api/v1/nexus/ledger/trend              → MetricsTrend

# Deploy Control — Lager 5 (Sprint 4)
GET    /api/v1/nexus/deploy/gates/{tool_id}    → GateStatus
POST   /api/v1/nexus/deploy/promote/{tool_id}  → PromotionResult
POST   /api/v1/nexus/deploy/rollback/{tool_id} → RollbackResult

# Dark Matter (Sprint 3)
GET    /api/v1/nexus/dark-matter/clusters      → list[DarkMatterCluster]
POST   /api/v1/nexus/dark-matter/{id}/review   → OK

# Calibration (Sprint 4)
GET    /api/v1/nexus/calibration/params        → list[CalibrationParams]
POST   /api/v1/nexus/calibration/fit           → CalibrationResult
GET    /api/v1/nexus/calibration/ece           → ECEReport
```

---

## Nya Python-beroenden

Lägg till i `surfsense_backend/pyproject.toml`:

```toml
# NEXUS dependencies
spacy = ">=3.7"
umap-learn = ">=0.5"
scikit-learn = ">=1.4"
scipy = ">=1.12"
faiss-cpu = ">=1.8"
```

Post-install:
```bash
python -m spacy download sv_core_news_lg
```

---

## Verifiering & Testning

### Backend
```bash
cd surfsense_backend
python -m pytest tests/test_nexus_*.py -v
```

### Frontend
```bash
cd surfsense_web && pnpm dev
# Navigera till /admin/nexus — verifiera tabs laddar och visar data
```

### Linting
```bash
cd surfsense_backend && ruff check app/nexus/ --fix && ruff format app/nexus/
cd surfsense_web && pnpm lint
```

---

## Målbild efter alla sprints

| Metrik | Target |
|--------|--------|
| Band-0 Throughput | >80% (direkt routing utan LLM) |
| ECE Global | <0.05 (kalibrerad confidence) |
| Namespace Purity | >92% (rätt zon varje gång) |
| OOD Rate | <3% (dark matter hanterat) |
| Reranker Delta | >+12pp (reranker faktiskt hjälper) |
| Syntetiska testfall/verktyg | 16 (4 svårigheter × 4 frågor) |
| Auto Loop-förbättring | Mätbar separation-ökning per vecka |
| Antal ändrade befintliga filer | 2 (en rad vardera) |
| Antal nya backend-filer | ~25 |
| Antal nya frontend-filer | ~15 |
