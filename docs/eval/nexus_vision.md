# Nexus Vision — Eval & Kalibreringssystem

> **System:** Nexus Vision — OneSeeks eval-, kalibrerings- och retrieval-diagnostiksystem
> **Version:** v2 (admin dashboard v2 + eval-bibliotek)
> **Senast uppdaterad:** 2026-03-04
> **Scope:** `docs/eval/` + `eval/api/`

---

## Innehåll

1. [Vad är Nexus Vision?](#1-vad-är-nexus-vision)
2. [Katalogens struktur](#2-katalogens-struktur)
3. [3-lagers retrieval-kaskad](#3-3-lagers-retrieval-kaskad)
4. [Eval-biblioteket (testdata)](#4-eval-biblioteket-testdata)
5. [Admin Dashboard v2 — 3-fliksarkitektur](#5-admin-dashboard-v2--3-fliksarkitektur)
6. [Metadata-standard](#6-metadata-standard)
7. [LLM-kvalitetssystem](#7-llm-kvalitetssystem)
8. [Lifecycle-integration](#8-lifecycle-integration)
9. [Implementeringsstatus](#9-implementeringsstatus)
10. [Kända buggar & problem](#10-kända-buggar--problem)
11. [Relaterade filer](#11-relaterade-filer)

---

## 1. Vad är Nexus Vision?

**Nexus Vision** är det system som säkerställer att OneSeeks AI-agent väljer rätt verktyg för varje användarfråga. Det täcker hela kedjan från rådata-insamling till automatiserad kalibrering och produktion:

```
Användarfråga
    │
    ▼
┌───────────────────────────────────────┐
│  Nexus Vision — 3-lagers kaskad       │
│                                       │
│  Lager 1: Intent-klassificering       │
│     "Vad handlar frågan om?"          │
│     → väder / statistik / trafik …   │
│                                       │
│  Lager 2: Agent-val                   │
│     "Vilken agent löser det?"         │
│     → väder-agent / statistik-agent … │
│                                       │
│  Lager 3: Verktygsval (Bigtool)       │
│     "Vilket specifikt API?"           │
│     → smhi_weather / scb_population … │
└───────────────────────────────────────┘
    │
    ▼
Eval → Kalibrering → Lifecycle → Produktion
```

### Nyckeltal

| Mätpunkt | Värde |
|----------|-------|
| Antal verktyg | 215 |
| Embedding-modell | KBLab/sentence-bert-swedish-cased (768 dim) |
| Embedding-typer per verktyg | 2 (semantisk + strukturell) |
| Scoring-komponenter | 6 |
| Rerank-kandidater | 24 |
| Fasad utrullning | 5 steg |
| Eval-filer i biblioteket | 18 JSON-filer |
| Admin-endpoints | 30 st |

---

## 2. Katalogens struktur

```
docs/eval/
├── nexus_vision.md            ← Den här filen
├── admin_tools_v1.md          ← Fullständig systemanalys (v1)
├── admin_tools_v1_code_audit.md ← Kodaudit: buggar, kvalitet, optimeringar
└── eval_v2.md                 ← Utvecklingsplan dashboard v2

eval/
└── api/
    ├── scb/
    │   ├── all_categories/
    │   │   └── scb-provider_20260214_v1.json
    │   └── be/
    │       └── scb-be_20260212_v1.json
    ├── smhi/
    │   ├── all_categories/
    │   │   ├── smhi-provider_20260213_v1.json
    │   │   ├── smhi-provider_20260213_v2.json
    │   │   ├── smhi-provider_20260214_v1.json  ← v3
    │   │   ├── smhi-provider_20260214_v2.json  ← v4
    │   │   ├── smhi-provider_20260214_v3.json  ← v5
    │   │   └── smhi-provider_20260218_v4.json  ← v6 (senaste)
    │   └── weather/
    │       └── smhi-weather_20260213_v1.json
    ├── trafikverket/
    │   ├── all_categories/          ← 9 versioner (v1–v3 per datum)
    │   └── trafikverket_vag/        ← 5 versioner väg-specifikt
    ├── riksdagen/
    │   └── all_categories/
    │       └── riksdagen-provider_20260214_v1.json
    └── skolverket/
        ├── all_categories/          ← 2 versioner
        ├── general/
        │   └── skolverket-general_20260222_v1.json
        └── statistics/
            └── skolverket-statistics_20260222_v1.json
```

---

## 3. 3-lagers retrieval-kaskad

### Scoring-formel (Lager 3 — Bigtool)

```
pre_rerank_score =
    (name_match        × 5.0)
  + (keyword_hits      × 3.0)   ← normaliserad: hits / total_keywords
  + (description_tokens× 1.0)   ← normaliserad: overlap / total_tokens
  + (example_hits      × 2.0)   ← normaliserad: matches / total_examples
  + (semantic_sim      × 2.8)   ← cosine mot semantisk embedding
  + (structural_sim    × 1.2)   ← cosine mot strukturell embedding
  + (namespace_bonus   × 3.0)   ← +3.0 om primärt namespace
  + (feedback_boost)             ← [−2.0, +2.0] baserat på historik
```

### Score-distribution (49 testfrågor, 215 verktyg)

| Komponent | Medel | P90 | Max |
|-----------|-------|-----|-----|
| Semantisk cosine (rå) | 0.187 | 0.382 | 0.849 |
| Strukturell cosine (rå) | 0.107 | 0.229 | 0.402 |
| Pre-rerank (alla) | 0.682 | 1.317 | 8.106 |
| Topp-1 score | 2.997 | 4.061 | 8.106 |
| Marginal (topp1 − topp2) | 0.707 | 1.562 | 6.650 |

### Fasstyrd utrullning (5 steg)

```
Shadow ──→ Tool gate ──→ Agent auto ──→ Adaptive ──→ Intent finjustering
  (1)          (2)            (3)           (4)              (5)
```

| Fas | Beteende |
|-----|----------|
| **Shadow** | Observera, ingen auto-select |
| **Tool gate** | Verktyg auto-selekteras vid hög konfidens |
| **Agent auto** | Även agenter auto-selekteras |
| **Adaptive** | Trösklar minskar per retry |
| **Intent finjustering** | Intent-shortlist + vikter optimeras |

### Kalibrerade trösklar (KBLab-modellen)

| Parameter | Nuvarande | Kalibrerat | Delta |
|-----------|-----------|------------|-------|
| `tool_auto_score_threshold` | 0.60 | **3.32** | +2.72 |
| `tool_auto_margin_threshold` | 0.25 | **0.28** | +0.03 |
| `agent_auto_score_threshold` | 0.55 | **2.83** | +2.28 |
| `agent_auto_margin_threshold` | 0.18 | **0.21** | +0.03 |

> ⚠ **OBS:** Nuvarande trösklar är **inte synkade** med KBLab-embedding. Se BUG-02.

---

## 4. Eval-biblioteket (testdata)

### Format

Varje JSON-fil är ett eval-set med följande struktur:

```json
{
  "eval_type": "tool_selection",
  "eval_name": "smhi-provider",
  "tests": [
    {
      "id": "case-1",
      "question": "Vad är vädret i Stockholm idag?",
      "difficulty": "lätt",
      "expected": {
        "tool": "smhi_weather",
        "route": "weather",
        "agent": "weather",
        "plan_requirements": [
          "route:weather",
          "agent:weather",
          "tool:smhi_weather"
        ]
      },
      "allowed_tools": ["smhi_weather"]
    }
  ]
}
```

### Providers och täckning

| Provider | Filer | Domän | Svårigheter |
|----------|-------|-------|-------------|
| **SMHI** | 6 filer | Väder, klimat, prognoser | lätt / medel / svår |
| **Trafikverket** | 9 filer | Väg, tåg, störningar, olyckor | lätt / medel / svår |
| **SCB** | 2 filer | Befolkning, ekonomi, inflation | lätt / medel / svår |
| **Skolverket** | 4 filer | Skolstatistik, betyg, personal | lätt / medel |
| **Riksdagen** | 1 fil | Motioner, betänkanden, protokoll | lätt / medel |

### Versionering

Filnamnsformat: `{provider}-{scope}_{datum}_v{version}.json`

- Datum: `YYYYMMDD`
- Version: Inkrementell per dag
- Senaste version per provider används vid eval-körning

### BSSS-problemområden (intra-namespace likhet)

| Namespace | Par >0.85 | Par >0.90 | Status |
|-----------|-----------|-----------|--------|
| tools/statistics | 45 | 26 | 🔴 Kritiskt |
| tools/politik | 21 | 8 | 🟠 Högt |
| tools/trafik | 17 | 3 | 🟠 Högt |
| tools/weather | 9 | 1 | 🟡 Medel |
| tools/knowledge | 8 | 3 | 🟡 Medel |
| tools/bolag | 3 | 1 | 🟢 OK |

---

## 5. Admin Dashboard v2 — 3-fliksarkitektur

Dashboard v2 (beskriven i `eval_v2.md`) samlar allt i **3 flikar** istället för v1:s 6 separata flikar + en separat lifecycle-sida.

### Flik 1: METADATA

**Ansvar:** Redigera metadata + globala vikter + lås-hantering.

```
┌──────────────────────────────────────────┐
│ METADATA                                 │
│                                          │
│ ┌─ Globala retrieval-vikter ───────────┐ │
│ │  Scoring: namn(5.0) kw(3.0) desc(1.0)│ │
│ │  Auto-select: tool_score(3.3) …      │ │
│ └─────────────────────────────────────┘ │
│                                          │
│ ┌─ Per-verktyg metadata ──────────────┐ │
│ │  ● Live 94.2%  smhi_weather         │ │
│ │  ○ Review 72%  scb_population       │ │
│ └─────────────────────────────────────┘ │
│                                          │
│ ┌─ Lås-hantering ─────────────────────┐ │
│ │  🔒 Stabilitets-lås: 12 verktyg     │ │
│ │  🔗 Separations-lås: 8 par (BSSS)   │ │
│ └─────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

### Flik 2: KALIBRERING

**Ansvar:** Guidat 3-stegsflöde — audit → eval → auto-optimering.

```
STEG 1: Metadata Audit
   → Probing mot aktuell metadata
   → 3-lagers accuracy-rapport
   → Kollisionsdetektering

STEG 2: Eval
   → Testfrågor per kategori/provider/globalt
   → Pass/fail per steg
   → LLM-förslag med diff-vy
   → Validering mot BSSS-lås

STEG 3: Auto-optimering (valfritt)
   → Iterativ loop mot målnivå
   → Holdout-validering
   → Promotion-förslag
```

### Flik 3: ÖVERBLICK

**Ansvar:** Status, trender, lifecycle, audit trail.

```
Nyckeltal:  Intent 92.3%  Agent 87.1%  Tool 84.5%
Trender:    30-dagarsdiagram per lager
Lifecycle:  ● Live (180)  ○ Review (35)  Total (215)
Audit:      Vem gjorde vad och när
```

### Före vs efter

| Före (v1) | Efter (v2) |
|-----------|------------|
| 6 flikar + separat lifecycle-sida | 3 flikar (lifecycle integrerad) |
| 12 steg, 3 flikbyten | Guidat 3-stegsflöde |
| 9 931 rader frontend | ~4 430 rader (−55%) |
| Lifecycle isolerad | Lifecycle synlig överallt |
| Ingen audit trail | Full historik: vem, vad, när |

---

## 6. Metadata-standard

Alla gränser definieras i `bigtool_store.py` — **en enda källa**.

### Fältgränser

| Fält | Max | Per-item max | Obligatorisk |
|------|-----|-------------|--------------|
| `name` | 80 tecken | — | Ja |
| `description` | 300 tecken | — | Ja |
| `keywords` | 20 st | 40 tecken | Ja (min 3) |
| `example_queries` | 10 st | 120 tecken | Ja (min 2) |
| `excludes` | 15 st | 60 tecken | Nej |
| `category` | 40 tecken | — | Ja |
| `tool_id` | 160 tecken | — | Ja |

### Kvalitetsregler

- **Språk:** All metadata på svenska
- **Keywords:** Inga generiska ("data", "information", "resultat")
- **Example queries:** 6–25 ord, innehåller specifik kontext (plats/tid/domän)
- **Description:** Unik per verktyg, 1-2 meningar, ingen snake_case
- **enforce_metadata_limits():** Obligatorisk på ALLA LLM-svar

### Keyword-pruning

`prune_low_value_keywords()` körs innan nya keywords läggs till:
1. Ta bort generiska keywords (blocklist)
2. Ta bort keywords utan träff i description
3. Ta bort keywords <3 tecken
4. Prioritera: nya > relevanta befintliga > övriga
5. Håll vid 10–15 st (under max 20)

---

## 7. LLM-kvalitetssystem

### validate_suggestion_quality()

Körs på **alla** LLM-förslag:

| Check | Syfte |
|-------|-------|
| `enforce_metadata_limits()` | Hårda tecken/antal-gränser |
| Inga snake_case i example_queries | Rent språk |
| Ingen engelska text | Svenska genomgående |
| Inga generiska/duplikata keywords | Hög keyword-kvalitet |
| `enabled` får ej sättas till `false` | Förhindrar oavsiktlig avstängning |
| `category` får ej ändras utan explicit instruktion | Förhindrar omkategorisering |
| Minst 1 fält måste faktiskt ändras | Ingen tom diff |
| Varning om BSSS-lås bryts | Synlig i diff-vy |

### Suggestion diff-vy

Förslag visas som diff, inte fullständig metadata:

```
description:
−  "Väderprognos från SMHI"
+  "SMHI:s detaljerade väderprognos för svenska orter"

keywords:
+  "regn"
+  "snö"
−  "väderlek"  (prunad: generisk)

Validering: ✓ Alla gränser OK
            ✓ Inga BSSS-lås bryts
            ✓ Svensk text
```

### Prompt-arkitekturguard

| Regel | Effekt |
|-------|--------|
| LLM ej `enabled: false` | Förhindrar oavsiktlig avstängning |
| LLM ej ändra `category` utan instruktion | Förhindrar omkategorisering |
| Alla LLM-förslag loggas med request-ID | Spårbarhet |
| LLM timeout 15s | Snabbare fallback |

---

## 8. Lifecycle-integration

### Statusmaskin

```
[review] ──── success_rate ≥ tröskel ────→ [live]
   ▲                                          │
   └──────── emergency rollback ◀─────────────┘
```

### Auto-promotion-flöde

```
Eval-körning klar
    │
    ▼
_sync_eval_to_lifecycle() uppdaterar success_rate
    │
    ├─ success_rate ≥ required_success_rate
    │   → Badge "Redo för promotion" visas i UI
    │   → Admin godkänner manuellt (ej automatiskt)
    │
    └─ success_rate < required_success_rate
        → Badge "Under review" kvarstår
```

### Audit trail (DB-tabell)

```sql
CREATE TABLE global_tool_lifecycle_audit (
    id SERIAL PRIMARY KEY,
    tool_id VARCHAR(160) NOT NULL,
    old_status VARCHAR(10),          -- 'review' | 'live'
    new_status VARCHAR(10) NOT NULL,
    success_rate FLOAT,
    trigger VARCHAR(20) NOT NULL,    -- 'manual' | 'eval_sync' | 'rollback'
    reason TEXT,
    changed_by_id UUID REFERENCES "user"(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Säker fallback

```python
# Vid lifecycle-check-fel: använd cache, läck INTE Review-verktyg till produktion
try:
    live_ids = await get_live_tool_ids(session)
except Exception:
    live_ids = _CACHED_LIVE_IDS
    logger.error("Lifecycle check failed, using cached live IDs")
```

---

## 9. Implementeringsstatus

> Uppdaterad: 2026-03-03

| Fas | Uppgifter | Klara | Status |
|-----|-----------|-------|--------|
| **Fas 1:** Grund (bugfixar + metadata-standard) | 10 | 10 | ✅ KLAR |
| **Fas 2:** Backend-refaktorering | 11 | 4 | 🔶 DELVIS |
| **Fas 3:** Frontend-omstrukturering | 11 | 11 | ✅ KLAR |
| **Fas 4:** Polish & validering | 7 | 1 | 🔶 DELVIS |
| **Totalt** | **39** | **26 (67%)** | |

### Fas 2 — Återstående

| # | Uppgift |
|---|---------|
| 2.4 | Extrahera gemensam eval-baslogik ur run_tool_evaluation / run_tool_api_input_evaluation |
| 2.5 | Implementera `prune_low_value_keywords()` |
| 2.7 | Auto-promotion badge (ny endpoint eller utökat response) |
| 2.8 | Säker fallback med cache vid lifecycle-check-fel |
| 2.9 | BSSS lock-override → DB audit trail |
| 2.10 | Contrast memory eviction (max 500 entries, LRU) |
| 2.11 | Embed cache eviction (max 2000 entries, LRU) |

### Fas 4 — Återstående

| # | Uppgift |
|---|---------|
| 4.1 | End-to-end test: redigera → audit → eval → promote |
| 4.2 | Validera att alla LLM-förslag passerar validate_suggestion_quality() |
| 4.3 | Verifiera holdout-validering i auto-loop |
| 4.4 | Kör calibrate_embedding_thresholds.py och applicera kalibrerade trösklar |
| 4.5 | Uppdatera CLAUDE.md med ny admin-struktur |
| 4.6 | Exponential backoff på eval-polling (1.2s → 2s → 4s → 8s) |

### Nya frontend-filer (skapade i Fas 3)

```
surfsense_web/components/admin/
├── tool-admin-page.tsx              # 3-flik orchestrator (~95 rader)
├── tabs/
│   ├── metadata-tab.tsx             # Flik 1: Metadata (~1250 rader)
│   ├── calibration-tab.tsx          # Flik 2: Kalibrering (~1400 rader)
│   └── overview-tab.tsx             # Flik 3: Överblick (~780 rader)
└── shared/
    ├── suggestion-diff-view.tsx     # Diff-vy (~140 rader)
    ├── lifecycle-badge.tsx          # Badge (~50 rader)
    └── audit-trail.tsx              # Audit trail (~130 rader)
```

---

## 10. Kända buggar & problem

### P0 — Kritiska

| ID | Problem | Fil |
|----|---------|-----|
| **BUG-01** | Holdout-suite genereras men valideras **aldrig** — `best_success_rate` kan vara överanpassad | `admin_tool_settings_routes.py:6162` |
| **BUG-02** | Score-trösklar ur synk med KBLab-embedding — auto-select triggar för aggressivt (65% av frågor) | `tool_retrieval_tuning_service.py:13` |

### P1 — Höga

| ID | Problem | Fil |
|----|---------|-----|
| **BUG-03** | Race condition i metadata-uppdatering vs BSSS-lock-validering | `admin_tool_settings_routes.py:4094` |
| **BUG-04** | Eval-jobb städas ej vid timeout/krasch (ingen tidbaserad pruning) | `admin_tool_settings_routes.py:2155` |
| **KQ-01** | `DEFAULT_TOOL_RETRIEVAL_TUNING` definierat på 2 ställen | `bigtool_store.py` + `tool_retrieval_tuning_service.py` |

### P2 — Medium

| ID | Problem |
|----|---------|
| **BUG-05** | BSSS lock-override loggas men sparas ej i audit trail (DB) |
| **BUG-06** | Partiella eval-resultat sparas vid krasch utan markering |
| **BUG-07** | Ingen rate-limiting på LLM-anrop vid metadata-audit (up to 12 parallellt) |
| **KQ-04** | 8 nästan identiska if-block i `build_tool_index()` |
| **KQ-05** | Duplicerad eval-logik (~1468 rader) i `tool_evaluation_service.py` |
| **KQ-10** | Metadata-gränser definierade på 3 ställen (Python + TypeScript + audit-service) |

### Embedding-specifikt

| Problem | Domän | Åtgärd |
|---------|-------|--------|
| 45 par >0.85 likhet | tools/statistics (SCB) | Stärk `excludes`, specifiera unika datakällor |
| 21 par >0.85 likhet | tools/politik (Riksdagen) | Differentiera dokumenttyper tydligare |
| 17 par >0.85 likhet | tools/trafik | Separera störningar/olyckor/prognos |
| Strukturell embedding bidrar lite (medel 0.107) | Alla | Öka `structural_embedding_weight` eller berika schema |

---

## 11. Relaterade filer

### Dokumentation

| Fil | Beskrivning |
|-----|-------------|
| `docs/eval/admin_tools_v1.md` | Fullständig systemanalys: retrieval-kaskad, scoring, fasstyrd utrullning, dashboard |
| `docs/eval/admin_tools_v1_code_audit.md` | Kodaudit: 10 buggar, 12 kvalitetsproblem, 8 optimeringar, 5 arkitekturförslag |
| `docs/eval/eval_v2.md` | Utvecklingsplan dashboard v2: arkitektur, UI-mockups, implementeringsplan, status |
| `docs/supervisor-architecture.md` | Övergripande arkitektur för Hybrid Supervisor v2 |

### Backend (nyckelfiler)

| Fil | Rader | Ansvar |
|-----|-------|--------|
| `surfsense_backend/app/agents/new_chat/bigtool_store.py` | 2 400 | Verktygsindex, scoring, namespace, BSSS |
| `surfsense_backend/app/routes/admin_tool_settings_routes.py` | 7 257 | 30 admin-endpoints |
| `surfsense_backend/app/services/tool_evaluation_service.py` | 5 199 | Eval-körning, förslag, historik |
| `surfsense_backend/app/services/metadata_audit_service.py` | 2 677 | 3-lagers audit, probe-generering |
| `surfsense_backend/app/services/metadata_separation_service.py` | 3 297 | BSSS-separation, par-lås |
| `surfsense_backend/app/services/tool_retrieval_tuning_service.py` | 391 | Tuning CRUD + normalisering |
| `surfsense_backend/scripts/calibrate_embedding_thresholds.py` | 676 | Offline-kalibrering av trösklar |

### Frontend (nyckelfiler)

| Fil | Ansvar |
|-----|--------|
| `surfsense_web/components/admin/tool-admin-page.tsx` | 3-flik orchestrator (v2) |
| `surfsense_web/components/admin/tabs/metadata-tab.tsx` | Flik 1: Metadata |
| `surfsense_web/components/admin/tabs/calibration-tab.tsx` | Flik 2: Kalibrering |
| `surfsense_web/components/admin/tabs/overview-tab.tsx` | Flik 3: Överblick |
| `surfsense_web/components/admin/shared/suggestion-diff-view.tsx` | Diff-vy för LLM-förslag |
| `surfsense_web/contracts/types/admin-tool-settings.types.ts` | TypeScript-kontrakt |
| `surfsense_web/lib/apis/admin-tool-settings-api.service.ts` | API-klient |

### Eval-körkonfiguration

```bash
# Kör kalibreringsskript (efter embedding-modellbyte)
cd surfsense_backend
python scripts/calibrate_embedding_thresholds.py

# Kör backend-tester
python -m pytest tests/ -v -k "eval or tool_selection or metadata"

# Admin-dashboard
open http://localhost:3000/admin/tools
```

---

*Nexus Vision — OneSeeks eval och kalibreringssystem. Genererat 2026-03-04.*
*Se `admin_tools_v1.md` för fullständig systemanalys och `eval_v2.md` för v2-implementeringsplan.*
