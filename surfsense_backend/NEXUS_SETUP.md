# NEXUS — Installationsguide

Komplett guide för att installera, konfigurera och starta NEXUS Retrieval Intelligence Platform.

---

## 1. Systemkrav

- Python 3.12+
- PostgreSQL 15+ med PGVector-extension
- Redis (för Celery-workers)
- Node.js 18+ med pnpm
- LLM-server (LM Studio, Ollama, eller cloud-API)

---

## 2. Backend-beroenden

### 2.1 Python-paket (installeras via uv)

```bash
cd surfsense_backend
uv sync
```

Alla NEXUS-beroenden finns redan i `pyproject.toml`:
- `spacy>=3.8.7` — Query Understanding Layer (NER, tokenizer)
- `scipy` — Platt-kalibrering (L-BFGS-B optimering)
- `faiss-cpu` — KNN-baserad OOD-detektion
- `numpy` — Vektorberäkningar
- `sentence-transformers` — Embedding-modell
- `rerankers` — Cross-encoder reranking
- `litellm` — LLM-abstraktion

### 2.2 spaCy-modell (KRÄVS)

NEXUS QUL-lager använder spaCy för svensk NER och tokenisering.

```bash
python -m spacy download sv_core_news_lg
```

**Storlek:** ~560 MB. Innehåller NER, POS-tagging, dependency parsing för svenska.

Om `sv_core_news_lg` inte kan laddas ner, fallbackar NEXUS automatiskt till `sv_core_news_sm` (mindre men sämre NER):

```bash
python -m spacy download sv_core_news_sm
```

---

## 3. Miljövariabler (.env)

Se till att dessa variabler finns i `surfsense_backend/.env`:

```bash
# === Databas ===
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/oneseek

# === Embedding-modell (NEXUS Space Auditor + routing) ===
EMBEDDING_MODEL=KBLab/sentence-bert-swedish-cased

# === Reranker (NEXUS routing pipeline) ===
RERANKERS_ENABLED=TRUE
RERANKERS_MODEL_NAME=ms-marco-MultiBERT-L-12
RERANKERS_MODEL_TYPE=flashrank

# === Redis (Celery) ===
CELERY_BROKER_URL=redis://localhost:6379/0
```

### 3.1 LLM-konfiguration

NEXUS Synth Forge och Auto Loop kräver en LLM. Konfigurera i `global_llm_config.yaml`:

```yaml
# Fil: surfsense_backend/global_llm_config.yaml
# ID -1 = global LLM-config som NEXUS använder

- id: -1
  name: "LM Studio (local)"
  provider: "CUSTOM"
  custom_provider: "openai"
  model_name: "nvidia/nemotron-3-nano"
  api_key: "lm-studio"
  api_base: "http://192.168.50.170:8000/v1"
  litellm_params:
    temperature: 0.3
    max_tokens: 4096
```

**Alternativ LLM-konfigurationer:**

```yaml
# OpenAI
- id: -1
  name: "OpenAI"
  provider: "OPENAI"
  model_name: "gpt-4o-mini"
  api_key: "sk-..."

# Anthropic
- id: -1
  name: "Claude"
  provider: "ANTHROPIC"
  model_name: "claude-sonnet-4-20250514"
  api_key: "sk-ant-..."

# Ollama (lokal)
- id: -1
  name: "Ollama"
  provider: "CUSTOM"
  custom_provider: "ollama"
  model_name: "llama3.1"
  api_base: "http://localhost:11434"
```

---

## 4. Databasmigration

NEXUS skapar 9 egna tabeller (alla med `nexus_`-prefix). Kör migrationen:

```bash
cd surfsense_backend
alembic upgrade head
```

### Tabeller som skapas:

| Tabell | Beskrivning |
|--------|-------------|
| `nexus_zone_config` | 4 zoner med centroid-embeddings |
| `nexus_routing_events` | Varje routing-beslut med band/zon/tool |
| `nexus_space_snapshots` | UMAP-koordinater per verktyg |
| `nexus_synthetic_cases` | LLM-genererade testfrågor |
| `nexus_auto_loop_runs` | Auto-loop körhistorik |
| `nexus_pipeline_metrics` | 5-stegs pipeline-metriker |
| `nexus_calibration_params` | Platt-kalibrering per zon |
| `nexus_dark_matter_queries` | OOD-frågor (okända) |
| `nexus_hard_negatives` | Svåra negativa par |

---

## 5. Starta systemet

### 5.1 Backend

```bash
cd surfsense_backend
python main.py --reload
```

### 5.2 Frontend

```bash
cd surfsense_web
pnpm install
pnpm dev
```

### 5.3 Celery-worker (valfritt, för bakgrundsjobb)

```bash
cd surfsense_backend
celery -A app.celery_app worker --loglevel=info
```

---

## 6. Initialisera NEXUS

### 6.1 Populera basdata (seed)

Navigera till `/admin/nexus` i webben, eller kör via API:

```bash
# Seed: zoner, routing-events, snapshots, metriker, kalibrering, dark matter
curl -X POST http://localhost:8000/api/v1/nexus/seed \
  -H "Authorization: Bearer <din-token>" \
  -H "Content-Type: application/json"
```

### 6.2 Generera syntetiska testfall

```bash
# Forge: LLM genererar 4 svårighetsgrader × 4 frågor per verktyg
curl -X POST http://localhost:8000/api/v1/nexus/forge/generate \
  -H "Authorization: Bearer <din-token>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 6.3 Kör auto-loop (eval)

```bash
# Loop: testar alla syntetiska frågor mot routing-pipeline
curl -X POST http://localhost:8000/api/v1/nexus/loop/start \
  -H "Authorization: Bearer <din-token>"
```

### 6.4 Kalibrera

```bash
# Fit: Platt-kalibrering baserat på routing-events
curl -X POST http://localhost:8000/api/v1/nexus/calibration/fit \
  -H "Authorization: Bearer <din-token>"
```

---

## 7. Verifiera att allt fungerar

### 7.1 Health-check

```bash
curl http://localhost:8000/api/v1/nexus/health \
  -H "Authorization: Bearer <din-token>"
```

Förväntat svar:
```json
{
  "status": "ok",
  "version": "2.0.0",
  "zones_configured": 4,
  "total_routing_events": 40,
  "total_synthetic_cases": 0,
  "embedding_model": {
    "status": "available",
    "model": "KBLab/sentence-bert-swedish-cased",
    "dimension": 768
  },
  "reranker": {
    "status": "available",
    "model": "ms-marco-MultiBERT-L-12",
    "type": "flashrank"
  }
}
```

### 7.2 Testa routing

```bash
curl -X POST http://localhost:8000/api/v1/nexus/routing/analyze \
  -H "Authorization: Bearer <din-token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "Vad blir vädret i Stockholm imorgon?"}'
```

### 7.3 Kör tester

```bash
cd surfsense_backend
python -m pytest tests/test_nexus_*.py -v
```

---

## 8. NEXUS Dashboard (UI)

Navigera till: **http://localhost:3000/admin/nexus**

### Tabs:

| Tab | Funktion | Kräver |
|-----|----------|--------|
| **Översikt** | Zonhälsa + band-distribution | Seed-data |
| **Rymd** | UMAP-visualisering, confusion-par, hubness | Seed-data + embedding-modell |
| **Forge** | Generera testfrågor via LLM | LLM konfigurerad |
| **Loop** | Auto-loop med eval + proposals | Forge-data |
| **Ledger** | 5-stegs pipeline-metriker | Seed-data |
| **Deploy** | Triple-gate lifecycle (separation, eval, LLM-judge) | Eval-data |

---

## 9. API-endpoints (komplett)

```
# Health & Config
GET    /api/v1/nexus/health
GET    /api/v1/nexus/zones
GET    /api/v1/nexus/config

# Routing
POST   /api/v1/nexus/routing/analyze
POST   /api/v1/nexus/routing/route
GET    /api/v1/nexus/routing/events
GET    /api/v1/nexus/routing/band-distribution
POST   /api/v1/nexus/routing/events/{id}/feedback

# Space Auditor
GET    /api/v1/nexus/space/health
GET    /api/v1/nexus/space/snapshot
GET    /api/v1/nexus/space/confusion
GET    /api/v1/nexus/space/hubness

# Synth Forge
POST   /api/v1/nexus/forge/generate
GET    /api/v1/nexus/forge/cases

# Auto Loop
POST   /api/v1/nexus/loop/start
GET    /api/v1/nexus/loop/runs
POST   /api/v1/nexus/loop/runs/{id}/approve

# Eval Ledger
GET    /api/v1/nexus/ledger/metrics
GET    /api/v1/nexus/ledger/trend

# Dark Matter
GET    /api/v1/nexus/dark-matter/clusters
POST   /api/v1/nexus/dark-matter/{id}/review

# Deploy Control
GET    /api/v1/nexus/deploy/gates/{tool_id}
POST   /api/v1/nexus/deploy/promote/{tool_id}
POST   /api/v1/nexus/deploy/rollback/{tool_id}

# Calibration
GET    /api/v1/nexus/calibration/params
POST   /api/v1/nexus/calibration/fit
GET    /api/v1/nexus/calibration/ece

# Seed
POST   /api/v1/nexus/seed
```

---

## 10. Felsökning

### "NEXUS LLM: Could not load global LLM config (id=-1)"
- Kontrollera att `global_llm_config.yaml` finns och har en post med `id: -1`
- Kontrollera att LLM-servern (LM Studio) är igång på rätt adress

### "No tools found in schema registry"
- `TOOL_SCHEMAS` i `app/nexus/routing/schema_verifier.py` måste ha verktyg
- Kör `POST /nexus/seed` för att populera basdata

### "Embedding model not available"
- Se till att `EMBEDDING_MODEL=KBLab/sentence-bert-swedish-cased` finns i `.env`
- Första gången laddas modellen ner (~90 MB) — det kan ta en stund

### "Reranker not available"
- Se till att `RERANKERS_ENABLED=TRUE` i `.env`
- flashrank laddar ner `ms-marco-MultiBERT-L-12` (~34 MB) automatiskt

### spaCy-fel
```bash
# Installera om spaCy-modellen
python -m spacy download sv_core_news_lg
# Eller verifiera
python -c "import spacy; nlp = spacy.load('sv_core_news_lg'); print('OK')"
```

### Migrationsproblem
```bash
# Visa vilken migration som är aktiv
alembic current

# Kör om migration
alembic upgrade head
```
