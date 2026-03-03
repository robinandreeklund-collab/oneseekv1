# Admin Tools — Fullständig Analys av Intent, Agent & Tool-val

> Hur OneSeek väljer rätt intent, agent och verktyg — och hur admin-dashboarden styr kalibrering, eval och utrullning.
> Senast uppdaterad: 2026-03-03 (v1.0 — 3-lagers retrieval, fasstyrd utrullning, auto-loop kalibrering)

---

## Innehåll

1. [Översikt](#1-översikt)
2. [Arkitektur — 3-lagers retrieval-kaskad](#2-arkitektur--3-lagers-retrieval-kaskad)
3. [Fas 1: Intent-klassificering](#3-fas-1-intent-klassificering)
4. [Fas 2: Agent-val](#4-fas-2-agent-val)
5. [Fas 3: Verktygsval (Bigtool Retrieval)](#5-fas-3-verktygsval-bigtool-retrieval)
6. [Scoring-pipeline i detalj](#6-scoring-pipeline-i-detalj)
7. [Embedding-strategi](#7-embedding-strategi)
8. [Retrieval Tuning — parametrar](#8-retrieval-tuning--parametrar)
9. [Fasstyrd utrullning (Phased Rollout)](#9-fasstyrd-utrullning-phased-rollout)
10. [Metadata Audit & BSSS-separation](#10-metadata-audit--bsss-separation)
11. [Eval-ramverket](#11-eval-ramverket)
12. [Auto-loop kalibrering](#12-auto-loop-kalibrering)
13. [Tool Lifecycle](#13-tool-lifecycle)
14. [Admin-dashboard — nuvarande vy](#14-admin-dashboard--nuvarande-vy)
15. [Problemanalys — vad som är rörigt idag](#15-problemanalys--vad-som-är-rörigt-idag)
16. [Föreslagen optimal dashboard](#16-föreslagen-optimal-dashboard)
17. [Filstruktur](#17-filstruktur)
18. [Kalibrerings­rapport — KBLab/sentence-bert-swedish-cased](#18-kalibreringsrapport--kblabsentence-bert-swedish-cased)

---

## 1. Översikt

OneSeek använder en **3-lagers retrieval-kaskad** för att välja rätt verktyg:

```
Användarfråga
    ↓
┌─────────────────────────────────────┐
│ Lager 1 — Intent-klassificering     │  "Vad handlar frågan om?"
│   • Lexikal + semantisk scoring     │  → väder / statistik / trafik / …
│   • Komplexitetsbedömning           │  → trivial / simple / complex
└───────────────┬─────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ Lager 2 — Agent-val                 │  "Vilken agent kan lösa detta?"
│   • Namespace-baserad filtrering    │  → väder-agent / statistik-agent / …
│   • Smart retrieval med reranking   │
└───────────────┬─────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ Lager 3 — Verktygsval (Bigtool)     │  "Vilket specifikt API/verktyg?"
│   • 4-stegs scoring-pipeline        │  → smhi_weather / scb_population / …
│   • Contrastive metadata            │
│   • Cross-encoder reranking         │
└─────────────────────────────────────┘
```

### Nyckeltal

| Mätpunkt | Värde |
|----------|-------|
| Antal verktyg i index | 215 |
| Embedding-modell | KBLab/sentence-bert-swedish-cased (768 dim) |
| Embedding-typer per verktyg | 2 (semantisk + strukturell) |
| Scoring-komponenter | 6 (namn, nyckelord, beskrivning, exempelfrågor, embedding, namespace) |
| Rerank-kandidater | 24 |
| Top-K intent | 3 |
| Top-K agent | 3 |
| Top-K verktyg | 5 |
| Fasad utrullning | 5 steg (shadow → tool_gate → agent_auto → adaptive → intent_finetune) |
| Admin-endpoints | 30 st |
| Frontend-rader (admin/tools) | 9 504 (tool-settings-page + metadata-catalog-tab) |
| Backend-rader (services + routes) | 18 430 |

---

## 2. Arkitektur — 3-lagers retrieval-kaskad

### End-to-end flöde

```
┌──────────────────────────────────────────────────────────────────┐
│                      Hybrid Supervisor v2                        │
│                                                                  │
│  resolve_intent ─→ agent_resolver ─→ tool_resolver ─→ executor  │
│       ▲                 ▲                  ▲              │      │
│       │                 │                  │              ▼      │
│  ┌────┴────┐      ┌────┴────┐       ┌────┴────┐    ┌────────┐  │
│  │ Intent  │      │ Agent   │       │ Bigtool │    │  Tools  │  │
│  │ Router  │      │Retrieval│       │  Store  │    │  Node   │  │
│  └────┬────┘      └────┬────┘       └────┬────┘    └────────┘  │
│       │                 │                  │                     │
│       ▼                 ▼                  ▼                     │
│  ┌─────────────────────────────────────────────┐                │
│  │      ToolRetrievalTuning (DB-driven)        │                │
│  │  vikter · trösklar · faser · feedback       │                │
│  └─────────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────────┘
         ▲                                   ▲
         │                                   │
    ┌────┴─────────────────┐  ┌──────────────┴──────────┐
    │  Admin Dashboard     │  │  Calibration Script      │
    │  /admin/tools        │  │  calibrate_embedding_    │
    │  (30 endpoints)      │  │  thresholds.py           │
    └──────────────────────┘  └─────────────────────────┘
```

### Datamodell

Varje lager har sin egen retrieval-index:

| Lager | Index-typ | Källa | Override |
|-------|-----------|-------|----------|
| Intent | `IntentDefinition` | `supervisor_routing.py` | `GlobalIntentDefinitionOverride` (DB) |
| Agent | `AgentDefinition` | `supervisor_constants.py` | `GlobalAgentMetadataOverride` (DB) |
| Verktyg | `ToolIndexEntry` | `bigtool_store.py` + verktygsregister | `GlobalToolMetadataOverride` (DB) |

All metadata kan överridas via admin-dashboard utan kodändringar.

---

## 3. Fas 1: Intent-klassificering

**Fil:** `nodes/intent.py` (494 rader)

### Scoring

```
Intent-score = (Lexikal × intent_lexical_weight) + (Semantisk × intent_embedding_weight)
```

**Lexikal scoring:**

| Komponent | Poäng |
|-----------|-------|
| Intent-ID matchar fråga | +2 |
| Route matchar fråga | +2 |
| Nyckelord-träff | +1 per träff |
| Token-överlappning | +1 per token |

**Semantisk scoring:**
- Cosine similarity mellan fråga-embedding och intent-embedding

### Komplexitetsbedömning

| Komplexitet | Villkor | Åtgärd |
|-------------|---------|--------|
| `trivial` | Hälsningsfras, småprat | Direkt svar, inga verktyg |
| `simple` | En agent, ett steg | Inline-exekvering |
| `complex` | Flera agenter/steg | Planering → subagent-spawning |

### State-output

```python
resolved_intent = {
    "intent_id": "väder_query",
    "route": "weather",
    "confidence": 0.92,
    "reason": "Lexikal match + hög semantisk likhet",
    "sub_intents": []  # för mixed-routes
}
graph_complexity = "simple"
speculative_candidates = [{"tool_id": "smhi_weather", "probability": 0.85}]
```

---

## 4. Fas 2: Agent-val

**Fil:** `nodes/agent_resolver.py` (309 rader)

### Agenter i systemet

| Agent | Namespace | Domän |
|-------|-----------|-------|
| `kunskap` | tools/knowledge | Dokument, kunskapsbas |
| `åtgärd` | tools/action | Kreativa uppgifter |
| `syntes` | tools/knowledge | Jämförelse/syntes |
| `statistik` | tools/statistics | SCB, Kolada, Skolverket |
| `väder` | tools/weather | SMHI |
| `trafik` | tools/trafik | Trafikverket |
| `kartor` | tools/kartor | Geoapify |
| `webb` | tools/knowledge/web | Webbsökning |
| `media` | tools/action/media | Podcast |
| `kod` | tools/code | Sandbox-exekvering |
| `bolag` | tools/bolag | Bolagsverket |
| `riksdagen` | tools/politik | Riksdagsdokument |
| `marknad` | tools/marketplace | Blocket, Tradera |
| `kolada` | tools/statistics | Kommunal statistik |
| `skolverket` | tools/statistics | Skolstatistik |

### Retrieval-flöde

```
1. Hybrid lexikal + semantisk scoring av agenter
2. Route-baserad filtrering (t.ex. "weather" → bara väder-agent)
3. Deranking av nyligen använda agenter (senaste 3)
4. Cross-encoder reranking
5. Auto-select OM: margin ≥ 0.18 OCH score ≥ 0.55
6. Annars: LLM-resolver väljer bland topp-kandidater
```

---

## 5. Fas 3: Verktygsval (Bigtool Retrieval)

**Fil:** `bigtool_store.py` (2 400 rader)

### 8-stegs retrieval-pipeline

```
┌─────────────────────────────────────────────┐
│ 1. Lexikal scoring (4 komponenter)          │
│    namn · nyckelord · beskrivning · exempel │
├─────────────────────────────────────────────┤
│ 2. Embedding scoring (2 vektorer)           │
│    semantisk (×2.8) + strukturell (×1.2)    │
├─────────────────────────────────────────────┤
│ 3. Namespace-bonus (+3.0 primärt)           │
├─────────────────────────────────────────────┤
│ 4. Retrieval feedback boost (±2.0)          │
├─────────────────────────────────────────────┤
│ 5. Kandidat-urval (primärt → fallback)      │
├─────────────────────────────────────────────┤
│ 6. Vector-recall fusion (topp 5 vektor)     │
├─────────────────────────────────────────────┤
│ 7. Cross-encoder reranking (24 kandidater)  │
├─────────────────────────────────────────────┤
│ 8. Auto-select / returnera topp-K           │
└─────────────────────────────────────────────┘
```

### Contrastive descriptions

Verktyg i samma namespace-kluster får "excludes"-fält:

```
trafikverket_trafikinfo_storningar
  → excludes: "olycka", "krock", "kö"

trafikverket_trafikinfo_olyckor
  → excludes: "störning", "driftstörning"
```

Tryckt isär i embedding-rymden — minskar kollisioner.

---

## 6. Scoring-pipeline i detalj

### Formel

```
pre_rerank_score =
    (name_match × 5.0)
  + (keyword_hits × 3.0)       # normaliserad: hits / total_keywords
  + (description_tokens × 1.0) # normaliserad: overlap / total_tokens
  + (example_hits × 2.0)       # normaliserad: matches / total_examples
  + (semantic_sim × 2.8)       # cosine mot semantisk embedding
  + (structural_sim × 1.2)     # cosine mot strukturell embedding
  + (namespace_bonus × 3.0)    # +3.0 om primärt namespace
  + (feedback_boost)            # [-2.0, +2.0] baserat på historik
```

### Score-distribution (49 testfrågor, 215 verktyg)

| Komponent | Medel | StdDev | P90 | Max |
|-----------|-------|--------|-----|-----|
| Semantisk cosine (rå) | 0.187 | 0.147 | 0.382 | 0.849 |
| Strukturell cosine (rå) | 0.107 | 0.090 | 0.229 | 0.402 |
| Embedding viktad (sem×2.8 + struct×1.2) | 0.653 | 0.476 | 1.273 | 2.697 |
| Pre-rerank score (alla) | 0.682 | 0.533 | 1.317 | 8.106 |
| Topp-1 score | 2.997 | 1.147 | 4.061 | 8.106 |
| Topp-2 score | 2.289 | 0.735 | 3.242 | 3.615 |
| Marginal (topp1 − topp2) | 0.707 | 1.020 | 1.562 | 6.650 |

---

## 7. Embedding-strategi

### Nuvarande modell

| Parameter | Värde |
|-----------|-------|
| Modell | KBLab/sentence-bert-swedish-cased |
| Dimensioner | 768 |
| Max embedding-text | 800 tecken |

### Två embedding-typer per verktyg

**Semantisk embedding** — fångar *vad verktyget gör*:
```
{name} + {main_identifier} + {core_activity} + {description}
+ {keywords} + {scope} + {examples} + {excludes}
→ max 800 tecken → encode → 768-dim vektor
```

**Strukturell embedding** — fångar *vilken data verktyget konsumerar*:
```
{required_input_fields} + {input_schema} + {example_input_json}
+ {expected_output_hint}
→ max 800 tecken → encode → 768-dim vektor
```

### BSSS-analys (intra-namespace likhet)

| Namespace | Par | Medel | Max | >.85 | >.90 |
|-----------|-----|-------|-----|------|------|
| tools/statistics | 2211 | 0.530 | 0.976 | 45 | 26 |
| tools/politik | 231 | 0.703 | 0.970 | 21 | 8 |
| tools/trafik | 153 | 0.669 | 0.935 | 17 | 3 |
| tools/weather | 105 | 0.628 | 0.956 | 9 | 1 |
| tools/knowledge | 780 | 0.462 | 0.949 | 8 | 3 |
| tools/bolag | 153 | 0.608 | 0.917 | 3 | 1 |
| tools/code | 21 | 0.707 | 0.894 | 2 | 0 |

**7 namespace har verktygspar >0.85** — rekommendation: sänk tröskeln eller förstärk contrastive excludes.

### Embedding-förbättringsförslag

| Problem | Förslag |
|---------|---------|
| `tools/statistics` har 45 par >0.85 | Stärk `excludes`-fält, specifiera unika datakällor per verktyg |
| Strukturell embedding tillför lite (medel 0.107) | Öka `structural_embedding_weight` eller berika schema-beskrivningar |
| 800-teckens-gräns kort för komplexa verktyg | Överväg chunk-embedding eller viktad pooling |
| Ingen fine-tuning av embedding-modell | Träna adapter med contrastive loss på verktygspar |

---

## 8. Retrieval Tuning — parametrar

### Aktuella standardvärden

| Parameter | Typ | Standard | Intervall | Påverkar |
|-----------|-----|----------|-----------|----------|
| `name_match_weight` | float | 5.0 | 0–25 | Exakt namnmatch |
| `keyword_weight` | float | 3.0 | 0–25 | Nyckelord-träffar |
| `description_token_weight` | float | 1.0 | 0–25 | Beskrivnings-tokens |
| `example_query_weight` | float | 2.0 | 0–25 | Exempelfråge-match |
| `semantic_embedding_weight` | float | 2.8 | 0–25 | Semantisk cosine |
| `structural_embedding_weight` | float | 1.2 | 0–25 | Strukturell cosine |
| `namespace_boost` | float | 3.0 | 0–10 | Primärt namespace |
| `rerank_candidates` | int | 24 | 1–100 | Cross-encoder batchstorlek |
| `tool_auto_score_threshold` | float | 0.60 | 0–5 | Auto-select minimiscore |
| `tool_auto_margin_threshold` | float | 0.25 | 0–5 | Auto-select marginal |
| `agent_auto_score_threshold` | float | 0.55 | 0–5 | Agent auto-select score |
| `agent_auto_margin_threshold` | float | 0.18 | 0–5 | Agent auto-select marginal |
| `adaptive_threshold_delta` | float | 0.08 | 0–1 | Tröskel-minskning per retry |
| `adaptive_min_samples` | int | 8 | 1–100 | Min sampel för adaptiv |
| `intent_candidate_top_k` | int | 3 | 1–20 | Intent-kandidater |
| `agent_candidate_top_k` | int | 3 | 1–20 | Agent-kandidater |
| `tool_candidate_top_k` | int | 5 | 1–20 | Verktygs-kandidater |
| `retrieval_feedback_db_enabled` | bool | false | — | Spara feedback i DB |
| `live_routing_enabled` | bool | false | — | Aktivera fasad utrullning |
| `live_routing_phase` | str | "shadow" | 5 faser | Aktuell fas |

### Nuvarande vs föreslagna trösklar (från kalibrering)

| Parameter | Nuvarande | Föreslagen | Delta |
|-----------|-----------|------------|-------|
| `tool_auto_score_threshold` | 0.60 | 3.32 | +2.72 |
| `tool_auto_margin_threshold` | 0.25 | 0.28 | +0.03 |
| `agent_auto_score_threshold` | 0.55 | 2.83 | +2.28 |
| `agent_auto_margin_threshold` | 0.18 | 0.21 | +0.03 |

**Auto-select rate med nuvarande trösklar:** Tool 65% (32/49), Agent 74% (36/49)

---

## 9. Fasstyrd utrullning (Phased Rollout)

### 5 faser

```
Shadow ─→ Tool gate ─→ Agent auto ─→ Adaptive ─→ Intent finjustering
  (1)        (2)          (3)          (4)            (5)
```

| Fas | Beteende | Auto-select |
|-----|----------|-------------|
| **Shadow** | Observera, ingen auto-select | Nej |
| **Tool gate** | Verktyg auto-selekteras vid hög konfidens | Verktyg: ja, Agent: nej |
| **Agent auto** | Även agenter auto-selekteras | Verktyg: ja, Agent: ja |
| **Adaptive** | Trösklar minskar per retry | Dynamiska trösklar |
| **Intent finjustering** | Intent-shortlist + vikter optimeras | Alla lager |

### Auto-select logik

```python
# Tool auto-select (fas ≥ 2)
if top1_score >= tool_auto_score_threshold \
   and (top1_score - top2_score) >= tool_auto_margin_threshold:
    auto_selected = True  # skippar LLM-resolver

# Agent auto-select (fas ≥ 3)
if top1_score >= agent_auto_score_threshold \
   and margin >= agent_auto_margin_threshold:
    auto_selected = True

# Adaptive (fas 4)
adjusted = tool_auto_score_threshold - (adaptive_threshold_delta × retry_count)
if top1_score >= adjusted:
    auto_selected = True
```

---

## 10. Metadata Audit & BSSS-separation

### Arbetsflöde idag

```
┌──────────────────────────────────────────────────┐
│ Steg A: Metadata Audit                           │
│   POST /metadata-audit/run                       │
│   → Genererar LLM-prober per verktyg             │
│   → Kör intent → agent → tool retrieval          │
│   → Rapporterar accuracy per lager               │
│   → Auto-låser stabila verktyg                   │
├──────────────────────────────────────────────────┤
│ Steg B: Förslag                                  │
│   POST /metadata-audit/suggestions               │
│   → LLM analyserar misslyckade prober            │
│   → Genererar metadata-förbättringar             │
│   → Filtrerar mot BSSS- och stabilitets-lås      │
├──────────────────────────────────────────────────┤
│ Steg C: Bottom-up separation                     │
│   POST /metadata-audit/separate-collisions       │
│   → Identifierar liknande verktygspar            │
│   → Genererar separations-patchar                │
│   → Skapar pair-locks                            │
├──────────────────────────────────────────────────┤
│ Steg D: Applicera                                │
│   PUT /metadata-catalog                          │
│   → Validerar mot BSSS-locks                     │
│   → Atomisk uppdatering (3 lager)                │
│   → Rensar cacher                                │
└──────────────────────────────────────────────────┘
```

### Låssystem

| Lås-typ | Syfte | Tillämpning |
|---------|-------|-------------|
| **Stabilitets-lås** | Förhindra ändringar av högpresterande verktyg | Auto vid audit, manuell via UI |
| **Separations-parlås (BSSS)** | Förhindra att liknande verktyg konvergerar | Vid separation, valideras vid update (409) |

### Audit-kvalitetskrav för prober

- 12–180 tecken lång
- Minst 3 tokens (efter stopword-rensning)
- Innehåller svenska diakritiska tecken (å, ä, ö)
- Undviker generiska mönster ("relevant data", "hjälp mig")
- Stad- och tidsreferenser ger bonuspoäng

---

## 11. Eval-ramverket

### 3 eval-typer

| Typ | Testar | Stage |
|-----|--------|-------|
| **Tool Selection** | Intent → Route → Agent → Verktyg → Plan | `agent`, `tool` |
| **API Input** | Parameterfyllning, schemakorrekthet | `api_input` |
| **Auto-loop** | Iterativ optimering mot målnivå | Alla |

### Eval-flöde

```
1. GENERERA testfrågor
   ├─ Per kategori / Per provider / Global random
   ├─ Svårighetsprofil: lätt / medel / svår / blandad
   └─ 1–100 frågor per körning

2. KÖR eval
   ├─ Async job (polling var 1.2s)
   ├─ Per test: intent → agent → tool → plan → pass/fail
   └─ Score-breakdown per svårighetsnivå

3. ANALYSERA resultat
   ├─ Jämförelse mot föregående körning (trend)
   ├─ Metadata-förslag (beskrivning, nyckelord, exempel)
   ├─ Prompt-förslag (router/agent/tool)
   └─ Retrieval tuning-förslag (vikter, trösklar)

4. APPLICERA förslag
   ├─ Selektiv: checkboxar per förslag
   ├─ Direkt → spara till DB
   └─ Draft → granska först
```

### Eval-bibliotek (befintliga testfiler)

```
eval/api/
├── scb/           # 2 filer (provider + kategori)
├── smhi/          # 5 filer (4 provider-versioner + 1 kategori)
├── trafikverket/  # 6 filer (3 provider + 3 kategori)
├── riksdagen/     # 1 fil
└── skolverket/    # 4 filer (2 provider + 2 kategori)
```

---

## 12. Auto-loop kalibrering

### Algoritm

```
Input:
  target_success_rate = 0.85
  max_iterations = 6
  patience = 2
  min_improvement_delta = 0.005

Loop:
  for i in 1..max_iterations:
    1. Generera testfrågor (varierande per iteration)
    2. Kör eval
    3. Om success_rate ≥ target: STOPP ✓
    4. Om ingen förbättring i [patience] iterationer: STOPP ✗
    5. Generera metadata-förslag från failures
    6. Applicera bästa förslag
    7. Rensa cacher, upprepa

Output:
  best_success_rate
  iterations_completed
  stop_reason: "target_reached" | "no_improvement" | "max_iterations_reached"
  metadata_suggestions (applicerade)
  prompt_suggestions
  retrieval_tuning_suggestions
```

### Holdout-suite

- Separata testfrågor reserverade för slutvalidering
- Förhindrar overfitting mot eval-set
- **Nuvarande bugg:** Holdout-frågor genereras men används ej för slutvalidering (se audit)

---

## 13. Tool Lifecycle

### Statusmaskin

```
[review] ──── uppfyller success_rate ────→ [live]
   ▲                                         │
   │                                         │
   └──────── emergency rollback ◀────────────┘
```

| Status | Betydelse | Villkor för promotion |
|--------|-----------|----------------------|
| `review` | Under utvärdering | Ingen |
| `live` | I produktion | `success_rate ≥ required_success_rate` |

**Emergency rollback:** Sätter direkt till `review` med motivering.

---

## 14. Admin-dashboard — nuvarande vy

### Flikar i `/admin/tools`

```
┌─────────┬──────────────────┬────────────┬─────────────────┬─────────────────┬───────────────┐
│Metadata │ Metadata Catalog │ Eval       │ Stats: Agent    │ Stats: Tool     │ Stats: API    │
│         │                  │ Workflow   │ Selection       │ Selection       │ Input         │
└─────────┴──────────────────┴────────────┴─────────────────┴─────────────────┴───────────────┘
```

| Flik | Rader (TSX) | Innehåll | Problem |
|------|-------------|----------|---------|
| **Metadata** | ~2000 | Verktygsredigering + Retrieval Tuning + Fasstyrd utrullning | Allt i en flik — för mycket |
| **Metadata Catalog** | 4221 | Audit, BSSS, stabilitets-lås, separation, rename | Extremt komplex, kräver djup förståelse |
| **Eval Workflow** | ~2500 | 4 eval-steg + auto-loop + förslag | Många modala flöden, svårt att följa |
| **Stats: Agent** | ~500 | Historik, trenddiagram | OK |
| **Stats: Tool** | ~500 | Historik, trenddiagram | OK |
| **Stats: API Input** | ~500 | Historik, trenddiagram | OK |

### API-endpoints (30 st)

| Grupp | Endpoints | Syfte |
|-------|-----------|-------|
| Metadata CRUD | 4 | Läsa/skriva verktygsmetadata |
| Metadata Catalog | 3 | Full katalog med 3 lager |
| Audit & Separation | 5 | Probing, förslag, BSSS-lås |
| Eval | 8 | Tool-eval, API-input-eval, async jobs |
| Auto-loop | 2 | Iterativ kalibrering |
| Eval Library | 4 | Generera/läsa testfiler |
| Retrieval Tuning | 2 | Läsa/skriva vikter |
| Förslag & Historik | 4 | LLM-förslag, audit trail |

---

## 15. Problemanalys — vad som är rörigt idag

### P1: Dashboard-struktur

| Problem | Konsekvens |
|---------|------------|
| 6 flikar med otydlig hierarki | Användaren vet ej var man börjar |
| Retrieval Tuning gömt under "Metadata"-fliken | Viktig funktion svår att hitta |
| Fasstyrd utrullning blandat med tool-redigering | Globala inställningar blandat med per-tool |
| Metadata Catalog (4221 rader) gör för mycket | Audit + separation + lås + rename i en vy |
| Eval Workflow har 4 understeg men ser ut som ett | Steg-flöde ej tydligt separerat |
| 3 statistik-flikar (agent/tool/api) är separata | Borde vara ett sammanhängande dashboard |

### P2: Arbetsflödes-komplexitet

```
NUVARANDE arbetsflöde (12 steg):
1. Redigera metadata (Metadata-flik)
2. Spara ändringar
3. Byt till Metadata Catalog-flik
4. Kör metadata audit
5. Granska audit-resultat
6. Generera förslag
7. Kör bottom-up separation
8. Applicera förslag
9. Byt till Eval Workflow-flik
10. Generera eval-frågor
11. Kör eval
12. Granska resultat, applicera förslag

→ 12 steg, 3 flikbyten, inget guidat flöde
```

### P3: Kodkvalitet

| Problem | Fil | Rader |
|---------|-----|-------|
| Monolitisk komponent | `tool-settings-page.tsx` | 5 283 |
| Monolitisk komponent | `metadata-catalog-tab.tsx` | 4 221 |
| `DEFAULT_TOOL_RETRIEVAL_TUNING` definierat på 2 ställen | `bigtool_store.py` + `tool_retrieval_tuning_service.py` | — |
| 8 nästan identiska if-block | `bigtool_store.py:build_tool_index()` | ~70 rader |
| `run_tool_evaluation()` och `run_tool_api_input_evaluation()` duplicerar logik | `tool_evaluation_service.py` | 664 + 804 |
| Holdout-suite genereras men valideras ej | `admin_tool_settings_routes.py` | — |

### P4: Konceptuell förvirring

| Term | Var det finns | Förvirring |
|------|---------------|------------|
| "Metadata" | Flik 1 + Flik 2 | Är det samma sak? |
| "Eval" | Flik 3 + Auto-loop + Kalibrerings­script | Tre olika eval-system |
| "Tuning" | Under Metadata-flik | Inte metadata — det är retrieval-config |
| "Statistik" | Flik 4-6 | Samma data, olika vinklar |

---

## 16. Föreslagen optimal dashboard

### Princip: 3 perspektiv, 1 guidat flöde

```
┌──────────────────────────────────────────────────────────────┐
│                    /admin/tools                              │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ METADATA │  │  KALIBRERING │  │      ÖVERBLICK         │ │
│  │ Redigera │  │  Testa &     │  │  Status & Historik     │ │
│  │          │  │  Optimera    │  │                        │ │
│  └──────────┘  └──────────────┘  └────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Flik 1: METADATA (redigera)

**Syfte:** Allt som handlar om att *ändra* verktygs-, agent- och intent-metadata.

```
┌──────────────────────────────────────────────────┐
│ METADATA                                         │
│                                                  │
│ ┌────────────────────────────────────────┐       │
│ │ Globala inställningar                   │       │
│ │  • Embedding-vikter (sem/struct)        │       │
│ │  • Scoring-vikter (namn/nyckelord/…)    │       │
│ │  • Namespace boost                      │       │
│ │  • Rerank-kandidater                    │       │
│ │  [Spara]                                │       │
│ └────────────────────────────────────────┘       │
│                                                  │
│ ┌────────────────────────────────────────┐       │
│ │ Per-verktyg metadata                    │       │
│ │  [Kategori-accordion]                   │       │
│ │  • Namn, beskrivning, nyckelord         │       │
│ │  • Exempelfrågor, scope-fält            │       │
│ │  • Excludes                             │       │
│ │  [Spara enskild] [Spara alla]           │       │
│ └────────────────────────────────────────┘       │
│                                                  │
│ ┌────────────────────────────────────────┐       │
│ │ Stabilitets- & separations-lås          │       │
│ │  🔒 12 låsta verktyg                    │       │
│ │  🔗 8 par-lås (BSSS)                   │       │
│ │  [Lås stabila] [Lås upp markerade]      │       │
│ └────────────────────────────────────────┘       │
└──────────────────────────────────────────────────┘
```

**Vad som slås ihop:** Metadata-flik + delar av Metadata Catalog (per-item editing, lås-hantering)
**Vad som flyttas bort:** Retrieval Tuning (nu "Globala inställningar" överst), Audit-funktioner (→ Kalibrering)

### Flik 2: KALIBRERING (testa & optimera)

**Syfte:** Guidat flöde för att testa och förbättra retrieval-precision. Ersätter Eval Workflow + Metadata Audit + Fasad utrullning.

```
┌──────────────────────────────────────────────────┐
│ KALIBRERING                                      │
│                                                  │
│ ╔════════════════════════════════════════════╗    │
│ ║ Fas: Shadow ──●── Tool gate ── Agent auto ║    │
│ ║       ▲           ── Adaptive ── Intent   ║    │
│ ║   (nuvarande)                              ║    │
│ ║   [Byt fas ▾]                              ║    │
│ ╚════════════════════════════════════════════╝    │
│                                                  │
│ ┌─ STEG 1: METADATA AUDIT ──────────────────┐   │
│ │  Kör probe-test mot aktuell metadata       │   │
│ │  [Provider ▾] [Kategori ▾] [Kör audit]     │   │
│ │                                            │   │
│ │  Resultat: Intent 92% · Agent 87% · Tool 78%  │
│ │  ⚠ 3 kollisioner detekterade               │   │
│ │  [Visa detaljer] [Separera kollisioner]     │   │
│ └────────────────────────────────────────────┘   │
│                                                  │
│ ┌─ STEG 2: EVAL ────────────────────────────┐   │
│ │  ┌─────────┬────────────┬────────────────┐ │   │
│ │  │Per-kat  │Per-provider│ Global random  │ │   │
│ │  └─────────┴────────────┴────────────────┘ │   │
│ │  Frågor: [12 ▾]  Svårighet: [Blandad ▾]   │   │
│ │  [Generera testfrågor]                     │   │
│ │  [Kör eval]                                │   │
│ │                                            │   │
│ │  Resultat: 85.4% ▲ (+3.2% vs föregående)  │   │
│ │  └─ Lätt: 95% · Medel: 82% · Svår: 71%   │   │
│ │                                            │   │
│ │  Förslag:                                  │   │
│ │  ☑ smhi_weather: lägg till nyckelord "regn"│   │
│ │  ☑ scb_population: förbättra beskrivning   │   │
│ │  [Applicera valda]                         │   │
│ └────────────────────────────────────────────┘   │
│                                                  │
│ ┌─ STEG 3: AUTO-OPTIMERING (valfritt) ──────┐   │
│ │  Mål: [85% ▾]  Max iterationer: [6 ▾]     │   │
│ │  [Starta auto-loop]                        │   │
│ │                                            │   │
│ │  Iteration 3/6: 82.1% → 84.3% → 86.7% ✓  │   │
│ │  Stopp-orsak: Målnivå uppnådd             │   │
│ └────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

**Vad som slås ihop:** Metadata Audit + Eval Workflow + Auto-loop + Fasstyrd utrullning
**Logik:** Ett guidat 3-stegs-flöde istället för 12 steg med flikbyten.

### Flik 3: ÖVERBLICK (status & historik)

**Syfte:** Dashboardvy med alla nyckeltal. Ersätter 3 statistik-flikar + Tool Lifecycle.

```
┌──────────────────────────────────────────────────┐
│ ÖVERBLICK                                        │
│                                                  │
│ ┌─── Nyckeltal ─────────────────────────────┐    │
│ │ Intent: 92.3%  Agent: 87.1%  Tool: 84.5%  │    │
│ │ Live: 42 verktyg  Review: 8 verktyg        │    │
│ │ Senaste eval: 2026-03-03 14:22             │    │
│ └────────────────────────────────────────────┘    │
│                                                  │
│ ┌─── Trenddiagram ──────────────────────────┐    │
│ │ ▁▂▃▅▅▆▇▇█  Intent accuracy (30 dagar)     │    │
│ │ ▁▂▃▄▅▅▆▆▇  Agent accuracy                 │    │
│ │ ▁▁▂▃▃▄▅▅▆  Tool accuracy                  │    │
│ └────────────────────────────────────────────┘    │
│                                                  │
│ ┌─── Verktygs-livscykel ────────────────────┐    │
│ │ Sök: [___________]                         │    │
│ │ ┌────────────────┬────────┬────────┬──────┐│    │
│ │ │ Verktyg        │ Status │ Rate   │      ││    │
│ │ ├────────────────┼────────┼────────┼──────┤│    │
│ │ │ smhi_weather   │ ● Live │ 94.2%  │ [⟲] ││    │
│ │ │ scb_population │ ○ Rev  │ 72.1%  │ [↑] ││    │
│ │ └────────────────┴────────┴────────┴──────┘│    │
│ └────────────────────────────────────────────┘    │
│                                                  │
│ ┌─── Eval-historik ─────────────────────────┐    │
│ │ [Agent ▾] [Tool ▾] [API Input ▾]           │    │
│ │ Senaste 30 körningar med trendlinje        │    │
│ └────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

**Vad som slås ihop:** Stats: Agent + Stats: Tool + Stats: API Input + Tool Lifecycle

### Sammanfattning — före vs efter

| Före (6 flikar) | Efter (3 flikar) |
|-----------------|-------------------|
| Metadata (tool-redigering + tuning + fas) | **Metadata** (tool-redigering + vikter + lås) |
| Metadata Catalog (audit + BSSS + lås + rename) | ↗ Redigering → Metadata, Audit → Kalibrering |
| Eval Workflow (4 steg + auto-loop) | **Kalibrering** (audit + eval + auto-loop + fas) |
| Stats: Agent Selection | **Överblick** (alla stats + lifecycle + nyckeltal) |
| Stats: Tool Selection | ↗ Sammanslaget i Överblick |
| Stats: API Input | ↗ Sammanslaget i Överblick |

### Fördelar

1. **3 flikar** istället för 6 — tydligare mental modell
2. **Guidat flöde** i Kalibrering — steg 1→2→3 istället för 12 steg med flikbyten
3. **Fasad utrullning** tydligt synlig överst i Kalibrering — inte gömd
4. **Överblick** ger hela bilden på en sida — intent + agent + tool + lifecycle
5. **Metadata** är ren redigering — inget audit/eval blandat in
6. **Lås-hantering** tydligt placerad under Metadata — nära det den påverkar

---

## 17. Filstruktur

### Backend

| Fil | Rader | Ansvar |
|-----|-------|--------|
| `bigtool_store.py` | 2 400 | Verktygsindex, scoring, namespace, contrastive |
| `supervisor_agent.py` | 7 163 | Grafkonstruktion, noder |
| `admin_tool_settings_routes.py` | 7 257 | 30 admin-endpoints |
| `tool_evaluation_service.py` | 5 199 | Eval-körning, förslag, historik |
| `metadata_separation_service.py` | 3 297 | BSSS-separation, par-lås, kontrastminne |
| `metadata_audit_service.py` | 2 677 | 3-lagers audit, probe-generering |
| `calibrate_embedding_thresholds.py` | 676 | Offline-kalibreringsskript |
| `nodes/intent.py` | 494 | Intent-klassificering |
| `tool_retrieval_tuning_service.py` | 391 | Tuning CRUD + normalisering |
| `nodes/agent_resolver.py` | 309 | Agent-val |
| `intent_router.py` | 247 | Intent-retrieval |
| `supervisor_routing.py` | 214 | Route-mappning |
| `supervisor_agent_retrieval.py` | 209 | Agent embedding-retrieval |
| `retrieval_feedback.py` | 198 | Feedback-loop |
| `nodes/tool_resolver.py` | 153 | Verktygsval per agent |

### Frontend

| Fil | Rader | Ansvar |
|-----|-------|--------|
| `tool-settings-page.tsx` | 5 283 | Metadata + Eval Workflow + Stats |
| `metadata-catalog-tab.tsx` | 4 221 | Audit + BSSS + Lås + Separation |
| `tool-lifecycle-page.tsx` | ~300 | Livscykel review/live |
| `admin-tool-settings.types.ts` | ~400 | TypeScript-kontrakt |
| `admin-tool-settings-api.service.ts` | 434 | API-klient (30 endpoints) |

### Kalibrering

| Fil | Typ | Ansvar |
|-----|-----|--------|
| `scripts/calibrate_embedding_thresholds.py` | Script | Offline embedding-kalibrering |
| `embed/audit_1.yaml` | Rapport | Kalibrerings­rapport (senaste) |
| `eval/api/**/*.json` | Testdata | 18 eval-filer per provider/kategori |

---

## 18. Kalibrerings­rapport — KBLab/sentence-bert-swedish-cased

### Sammanfattning

| Mätpunkt | Värde |
|----------|-------|
| Modell | KBLab/sentence-bert-swedish-cased |
| Dimensioner | 768 |
| Verktyg i index | 215 |
| Testfrågor | 49 (10 domäner) |
| Kalibreringstid | 1.1s |

### Score-distribution

```
Semantisk cosine:     ░░░░░░░░░░░░░░ medel=0.187, p90=0.382
Strukturell cosine:   ░░░░░░░░░      medel=0.107, p90=0.229
Embedding viktad:     ░░░░░░░░░░░░░░░░░ medel=0.653, p90=1.273
Pre-rerank (alla):    ░░░░░░░░░░░░░░░░░░ medel=0.682, p90=1.317
Topp-1 score:         ░░░░░░░░░░░░░░░░░░░░░░░░░░░░ medel=2.997
Marginal (t1-t2):     ░░░░░░░░░░░░░░░ medel=0.707
```

### Domänresultat (urval)

| Fråga | Topp-1 verktyg | Score | Marginal | Auto |
|-------|---------------|-------|----------|------|
| "Hur blir vädret i Stockholm imorgon?" | smhi_vaderprognoser_metfcst | 1.99 | 0.21 | AGENT |
| "Visa väderprognos för Uppsala" | smhi_vaderprognoser_metfcst | 4.20 | 1.03 | TOOL |
| "Trafikstörningar på E6" | trafikverket_trafikinfo_storningar | 8.11 | 6.65 | TOOL |
| "Befolkningsstatistik per kommun" | scb_be_befolkningens_sammansattning | 2.44 | 0.03 | — |
| "Riksdagsmotioner om klimat" | riksdag_dokument_motion | 3.97 | 0.43 | TOOL |

### Problemområden

| Domän | Problem | Åtgärd |
|-------|---------|--------|
| Statistik (SCB) | 45 par >0.85 likhet | Stärk excludes, specifiera datakällor |
| Politik (Riksdagen) | 21 par >0.85 | Differentiera dokumenttyper tydligare |
| Trafik | 17 par >0.85 | Separera störningar/olyckor/prognos |
| Väder | 9 par >0.85 | SMHI vs Trafikverket väder-stationer |

---

*Rapporten genererad 2026-03-03. Se `docs/eval/admin_tools_v1_code_audit.md` för kodanalys och buggar.*
