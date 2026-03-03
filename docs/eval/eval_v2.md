# Admin Tools v2 — Utvecklingsplan

> **Datum:** 2026-03-03
> **Baserat på:** `admin_tools_v1.md` (systemanalys) + `admin_tools_v1_code_audit.md` (kodaudit)
> **Mål:** Bulletproof admin dashboard — silkeslen UX, strikt kvalitet, korrekt kalibrering
> **Scope:** `/admin/tools` + `/admin/lifecycle` → sammanslagna till **en** sammanhängande vy

---

## Innehåll

1. [Vision](#1-vision)
2. [Arkitektur v2](#2-arkitektur-v2)
3. [Dashboard-struktur — 3 flikar](#3-dashboard-struktur--3-flikar)
4. [Metadata-standard (normativ)](#4-metadata-standard-normativ)
5. [LLM-kvalitetssystem](#5-llm-kvalitetssystem)
6. [Lifecycle-integration](#6-lifecycle-integration)
7. [Implementeringsplan](#7-implementeringsplan)
8. [Filändringar per fas](#8-filändringar-per-fas)
9. [Migreringsplan](#9-migreringsplan)

---

## 1. Vision

### Före (v1)

```
/admin/tools (6 flikar, 9500 rader TSX)          /admin/lifecycle (separat sida, 427 rader)
┌──────────────────────────────────────┐          ┌─────────────────────────────┐
│ Metadata │ Catalog │ Eval │ 3×Stats  │          │ Review/Live tabell          │
│  (allt   │ (audit  │ (4   │ (separata│          │ (isolerad, ingen koppling   │
│  blandat)│ +BSSS   │ steg)│ per-lager│          │  till eval eller metadata)  │
│          │ +lås    │      │ diagram) │          │                             │
└──────────────────────────────────────┘          └─────────────────────────────┘
12 steg arbetsflöde • 3 flikbyten • oklart var man börjar
```

### Efter (v2)

```
/admin/tools (3 flikar, lifecycle inbyggd)
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────────┐  │
│  │ METADATA │  │   KALIBRERING    │  │      ÖVERBLICK        │  │
│  │          │  │                  │  │                       │  │
│  │ Redigera │  │ Guidat 3-stegs-  │  │ Nyckeltal + Status +  │  │
│  │ metadata │  │ flöde: audit →   │  │ Trend + Lifecycle-    │  │
│  │ + vikter │  │ eval → optimize  │  │ tabell integrerad     │  │
│  │ + lås    │  │ + fas-styrning   │  │                       │  │
│  └──────────┘  └──────────────────┘  └───────────────────────┘  │
│                                                                  │
│  ┌─ Strikt metadata-standard ──────────────────────────────────┐ │
│  │ enforce_metadata_limits() på ALLA LLM-svar                  │ │
│  │ Keyword-pruning • Suggestion-diff-vy • Arkitektur-guard     │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
3 steg arbetsflöde • 0 flikbyten • lifecycle synlig överallt
```

### Mål

| Mål | Mätbart kriterium |
|-----|-------------------|
| **Silkeslen UX** | Max 3 klick från start till klar eval-körning |
| **Bulletproof metadata** | 0 metadata-fält kan bryta format efter LLM-förslag |
| **Korrekt kalibrering** | Trösklar alltid synkade med aktuell embedding-modell |
| **Integrerad lifecycle** | Eval → promotion → rollback i samma flöde |
| **Strikt LLM-kvalitet** | Alla LLM-förslag valideras, diffas, och kräver godkännande |
| **Kodkvalitet** | Inga filer >1500 rader, inga duplicerade defaults |

---

## 2. Arkitektur v2

### Systemöversikt

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Admin Dashboard v2                              │
│                                                                          │
│  ┌────────────┐     ┌──────────────────┐     ┌─────────────────────┐    │
│  │  METADATA   │     │   KALIBRERING    │     │     ÖVERBLICK       │    │
│  │  (redigera) │     │   (testa &       │     │  (status &          │    │
│  │             │     │    optimera)     │     │   historik)         │    │
│  └──────┬──────┘     └────────┬─────────┘     └──────────┬──────────┘    │
│         │                     │                          │               │
│         └─────────────────────┼──────────────────────────┘               │
│                               │                                          │
│                    ┌──────────▼──────────┐                               │
│                    │  Unified API Layer   │                               │
│                    │  (30 endpoints →     │                               │
│                    │   konsoliderade)     │                               │
│                    └──────────┬──────────┘                               │
└───────────────────────────────┼──────────────────────────────────────────┘
                                │
              ┌─────────────────┼─────────────────────┐
              │                 │                      │
    ┌─────────▼─────┐  ┌───────▼────────┐  ┌─────────▼──────────┐
    │ Metadata       │  │ Eval & Audit    │  │ Lifecycle          │
    │ Service        │  │ Service         │  │ Service            │
    │                │  │                 │  │                    │
    │ • CRUD         │  │ • Probing       │  │ • Status           │
    │ • Validation   │  │ • Eval runner   │  │ • Auto-promotion   │
    │ • BSSS-lås     │  │ • Suggestions   │  │ • Rollback         │
    │ • Separation   │  │ • Auto-loop     │  │ • Audit trail      │
    └───────────────┘  └────────────────┘  └────────────────────┘
              │                 │                      │
              └─────────────────┼──────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Metadata Standard     │
                    │  (enforce_metadata_    │
                    │   limits — enda källa) │
                    └──────────────────────┘
```

### Dataflöde (end-to-end)

```
Admin redigerar metadata
    │
    ▼
enforce_metadata_limits() ──── Validering ──── Spara till DB
    │
    ▼
Admin startar kalibrering
    │
    ├─ Steg 1: Metadata Audit
    │   └─ Probing → 3-lagers accuracy → kollisionsrapport
    │
    ├─ Steg 2: Eval
    │   └─ Testfrågor → intent→agent→tool → pass/fail
    │   └─ LLM-förslag → validate_suggestion() → diff-vy
    │
    ├─ Steg 3: Auto-optimering (valfritt)
    │   └─ Loop: eval → suggest → validate → apply → eval
    │   └─ Holdout-validering vid avslut ◀ NY
    │
    └─ Eval-resultat → _sync_eval_to_lifecycle()
                            │
                            ▼
                    Lifecycle auto-check ◀ NY
                    ├─ success_rate ≥ threshold → badge "Redo för promotion"
                    ├─ success_rate < threshold → badge "Under review"
                    └─ Admin godkänner → LIVE
```

---

## 3. Dashboard-struktur — 3 flikar

### Flik 1: METADATA

**Ansvar:** Redigera metadata + globala vikter + lås-hantering. Ren redigering — inget eval/audit.

```
┌──────────────────────────────────────────────────────────────┐
│ METADATA                                                     │
│                                                              │
│ ┌─ Globala retrieval-vikter ───────────────────────────────┐ │
│ │                                                          │ │
│ │  ┌──────────────────┐ ┌──────────────────┐               │ │
│ │  │ Scoring-vikter   │ │ Auto-select      │               │ │
│ │  │ namn:     [5.0]  │ │ tool score: [3.3]│               │ │
│ │  │ keyword:  [3.0]  │ │ tool margin:[0.3]│               │ │
│ │  │ desc:     [1.0]  │ │ agent score:[2.8]│               │ │
│ │  │ example:  [2.0]  │ │ agent marg.:[0.2]│               │ │
│ │  │ sem.emb:  [2.8]  │ │                  │               │ │
│ │  │ str.emb:  [1.2]  │ │ Rerank:    [24]  │               │ │
│ │  │ ns.boost: [3.0]  │ │ Top-K:  I3 A3 T5 │               │ │
│ │  └──────────────────┘ └──────────────────┘               │ │
│ │  [Spara vikter]   [Återställ till standard]              │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─ Per-verktyg metadata ───────────────────────────────────┐ │
│ │  Sök: [___________]  Filter: [Kategori ▾] [Status ▾]    │ │
│ │                                                          │ │
│ │  ┌─ smhi_weather ─── ● Live ── 94.2% ──────────────┐    │ │
│ │  │  Beskrivning: [____________________] (47/300)    │    │ │
│ │  │  Nyckelord:   [väder] [prognos] [+]  (4/20)     │    │ │
│ │  │  Exempelfrågor: [3/10 st]  [Visa/Redigera]      │    │ │
│ │  │  Excludes: [2/15 st]  Scope: Stockholm           │    │ │
│ │  │  🔒 Stabilitets-låst                             │    │ │
│ │  └──────────────────────────────────────────────────┘    │ │
│ │                                                          │ │
│ │  ┌─ scb_population ─── ○ Review ── 72.1% ──────────┐    │ │
│ │  │  ...                                             │    │ │
│ │  └──────────────────────────────────────────────────┘    │ │
│ │                                                          │ │
│ │  [Spara alla ändringar]                                  │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─ Lås-hantering ─────────────────────────────────────────┐ │
│ │  🔒 Stabilitets-lås: 12 verktyg   [Hantera →]          │ │
│ │  🔗 Separations-lås: 8 par        [Hantera →]          │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**Nyckelförändringar vs v1:**

| v1 | v2 | Motivering |
|----|----|------------|
| Retrieval Tuning gömd under metadata-flik | Globala vikter **överst** med tydlig sektion | Viktigaste konfigurationen ska vara lättast att hitta |
| Fasstyrd utrullning blandat med tool-redigering | Flyttat till Kalibrering-fliken | Fas är global, inte per-verktyg |
| Ingen lifecycle-status synlig | `● Live` / `○ Review` badge + success rate på varje verktyg | Admin ser direkt status utan att byta sida |
| Audit/BSSS-separation blandat med redigering | Flyttat till Kalibrering | Redigering separat från testning |
| Metadata Catalog (4221 rader) — allt i en komponent | Uppdelat: redigering här, audit/separation → Kalibrering | Varje flik har ett tydligt ansvar |

### Flik 2: KALIBRERING

**Ansvar:** Testa och optimera. Guidat 3-stegsflöde + fasstyrd utrullning.

```
┌──────────────────────────────────────────────────────────────┐
│ KALIBRERING                                                  │
│                                                              │
│ ╔════════════════════════════════════════════════════════════╗│
│ ║  Fas: [Shadow]──[Tool gate]──[Agent auto]──[Adaptive]──   ║│
│ ║        ▲ aktiv                                            ║│
│ ║                                                           ║│
│ ║  Embedding-modell: KBLab/sentence-bert-swedish-cased      ║│
│ ║  Kalibrerad: 2026-03-01   Verktyg: 215   Live: 180       ║│
│ ║                                                           ║│
│ ║  [Byt fas ▾]  [Kalibrera trösklar →]                      ║│
│ ╚════════════════════════════════════════════════════════════╝│
│                                                              │
│ ┌─ STEG 1: METADATA AUDIT ──────────────────────────────────┐│
│ │                                                            ││
│ │  Scope: [Per provider ▾]  Provider: [SMHI ▾]              ││
│ │  [Kör audit]                                               ││
│ │                                                            ││
│ │  ┌─ Resultat ────────────────────────────────────────────┐ ││
│ │  │ Intent: 92.3%   Agent: 87.1%   Tool: 78.4%           │ ││
│ │  │                                                       │ ││
│ │  │ ⚠ 3 kollisioner:                                     │ ││
│ │  │   smhi_weather ↔ trafikverket_väder (0.91)            │ ││
│ │  │   scb_pop_kommuner ↔ scb_pop_regioner (0.93)          │ ││
│ │  │   scb_pop_kommuner ↔ kolada_befolkning (0.88)         │ ││
│ │  │                                                       │ ││
│ │  │ [Separera kollisioner →]  [Visa probe-detaljer →]     │ ││
│ │  └───────────────────────────────────────────────────────┘ ││
│ └────────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ STEG 2: EVAL ────────────────────────────────────────────┐│
│ │                                                            ││
│ │  ┌─────────┬────────────┬────────────────┐                 ││
│ │  │Per-kat  │Per-provider│ Global random  │                 ││
│ │  └─────────┴────────────┴────────────────┘                 ││
│ │  Frågor: [12 ▾]   Svårighet: [Blandad ▾]                  ││
│ │  [Generera testfrågor]  [Kör eval]                         ││
│ │                                                            ││
│ │  ┌─ Resultat ────────────────────────────────────────────┐ ││
│ │  │ 85.4% (▲ +3.2% vs föregående)                        │ ││
│ │  │  Lätt: 95%  Medel: 82%  Svår: 71%                    │ ││
│ │  │                                                       │ ││
│ │  │ Förslag (3 st):                    [Visa diff →]      │ ││
│ │  │ ┌───────────────────────────────────────────────────┐ │ ││
│ │  │ │ ☑ smhi_weather                                    │ │ ││
│ │  │ │   keywords: +["regn","snö"]  −["väderlek"]        │ │ ││
│ │  │ │   description: "Väderprognos..." → "SMHI:s..."    │ │ ││
│ │  │ │   ⚠ Bryter BSSS-lås mot trafikverket_väder       │ │ ││
│ │  │ ├───────────────────────────────────────────────────┤ │ ││
│ │  │ │ ☑ scb_population                                  │ │ ││
│ │  │ │   example_queries: +2 nya                         │ │ ││
│ │  │ │   ✓ Inom alla gränser                             │ │ ││
│ │  │ └───────────────────────────────────────────────────┘ │ ││
│ │  │                                                       │ ││
│ │  │ [Applicera valda]  [Exportera rapport]                │ ││
│ │  └───────────────────────────────────────────────────────┘ ││
│ └────────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ STEG 3: AUTO-OPTIMERING (valfritt) ──────────────────────┐│
│ │                                                            ││
│ │  Mål: [85% ▾]   Max iterationer: [6 ▾]                    ││
│ │  ☑ Använd holdout-suite för slutvalidering                 ││
│ │  [Starta auto-loop]                                        ││
│ │                                                            ││
│ │  Iteration 3/6: 82.1% → 84.3% → 86.7% ✓                  ││
│ │  Holdout-validering: 84.2% (−2.5% vs eval-set) ◀ NY       ││
│ │  Stopp-orsak: Målnivå uppnådd                             ││
│ │                                                            ││
│ │  ┌─ Lifecycle-uppdatering ◀ NY ────────────────────────┐   ││
│ │  │ 4 verktyg redo för promotion (success_rate ≥ 80%)   │   ││
│ │  │ ☑ scb_population (82.1%)                            │   ││
│ │  │ ☑ kolada_befolkning (81.4%)                         │   ││
│ │  │ ☑ smhi_pmp (85.0%)                                  │   ││
│ │  │ ☑ riksdag_betankande (80.2%)                        │   ││
│ │  │ [Promota markerade till Live →]                      │   ││
│ │  └─────────────────────────────────────────────────────┘   ││
│ └────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**Nyckelförändringar vs v1:**

| v1 | v2 | Motivering |
|----|----|------------|
| 4 eval-steg i en flik med oklar ordning | Guidat 3-steg med visuell progress | Admin vet exakt var man är |
| Fasstyrd utrullning under metadata | Fas-panel **överst** i Kalibrering | Global konfiguration synlig direkt |
| LLM-förslag visas som lista | **Diff-vy**: `+tillägg` / `-borttagning` per fält | Admin ser exakt vad som ändras |
| Förslag valideras ej mot BSSS-lås | Varningsikon om förslag bryter lås | Förhindrar oavsiktliga lås-brott |
| Holdout-suite genereras men valideras ej | Holdout-validering obligatorisk i steg 3 | Förhindrar overfitting |
| Ingen lifecycle-koppling efter eval | Promotion-förslag direkt efter eval | Flödet avslutas naturligt |

### Flik 3: ÖVERBLICK

**Ansvar:** Status, historik, lifecycle, trender. Läs-only (inga redigeringar).

```
┌──────────────────────────────────────────────────────────────┐
│ ÖVERBLICK                                                    │
│                                                              │
│ ┌─ Nyckeltal ───────────────────────────────────────────────┐│
│ │                                                            ││
│ │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌─────────┐││
│ │  │ Intent    │  │ Agent     │  │ Tool      │  │ API     │ ││
│ │  │ 92.3%     │  │ 87.1%     │  │ 84.5%     │  │ Input   │ ││
│ │  │ ▲ +1.2%   │  │ ▲ +2.4%   │  │ ▲ +3.2%   │  │ 91.0%  │ ││
│ │  └───────────┘  └───────────┘  └───────────┘  └─────────┘││
│ │                                                            ││
│ │  Live: 180   Review: 35   Total: 215                       ││
│ │  Senaste eval: 2026-03-03 14:22   Fas: Shadow              ││
│ └────────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Trenddiagram (30 dagar) ─────────────────────────────────┐│
│ │  ▁▂▃▅▅▆▇▇█  Intent   ▁▂▃▄▅▅▆▆▇  Agent                    ││
│ │  ▁▁▂▃▃▄▅▅▆  Tool     ▂▃▄▅▅▆▇▇█  API Input                ││
│ │  [Alla lager ▾] [30 dagar ▾]                               ││
│ └────────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Lifecycle-status ────────────────────────────────────────┐│
│ │  Sök: [___________]  Filter: [Alla ▾] [Redo att promota ▾]││
│ │                                                            ││
│ │  ┌──────────────────┬────────┬───────┬────────┬──────────┐││
│ │  │ Verktyg          │ Status │ Rate  │ Tröskel│ Åtgärd   │││
│ │  ├──────────────────┼────────┼───────┼────────┼──────────┤││
│ │  │ smhi_weather      │ ● Live │ 94.2% │  80%   │   [⟲]   │││
│ │  │ scb_population    │ ○ Rev  │ 82.1% │  80%   │   [↑✓]  │││
│ │  │ kolada_inv_test   │ ○ Rev  │ 58.3% │  80%   │   [—]   │││
│ │  └──────────────────┴────────┴───────┴────────┴──────────┘││
│ │                                                            ││
│ │  [↑✓] = Redo att promota    [⟲] = Emergency rollback       ││
│ │  [—] = Under tröskel        [Promota alla redo →]          ││
│ └────────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Eval-historik ───────────────────────────────────────────┐│
│ │  [Agent Selection ▾] [Tool Selection ▾] [API Input ▾]     ││
│ │  Tabell med senaste 30 körningar + trendlinje             ││
│ └────────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Audit Trail ◀ NY ───────────────────────────────────────┐│
│ │  2026-03-03 14:22  admin@oneseek.se  Promotade scb_pop   ││
│ │  2026-03-03 14:20  system           Eval: 85.4%           ││
│ │  2026-03-03 10:15  admin@oneseek.se  Metadata: smhi...    ││
│ │  2026-03-02 16:00  admin@oneseek.se  Rollback: kolada_inv ││
│ └────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**Vad som slås ihop:** Stats: Agent + Stats: Tool + Stats: API Input + `/admin/lifecycle`

**Nyckelförändringar:**

| v1 | v2 |
|----|----|
| Lifecycle på separat sida `/admin/lifecycle` | Integrerad i Överblick-fliken |
| 3 separata statistik-flikar | En samlad vy med alla lager |
| Ingen audit trail | Full historik: vem, vad, när |
| Ingen "redo att promota" indikation | Badge + filter för promotionsklara verktyg |
| Emergency rollback kräver navigering | Direkt i Överblick-tabellen |

---

## 4. Metadata-standard (normativ)

### 4.1 Fältgränser — enda källan

Alla gränser definieras i `bigtool_store.py` och importeras därifrån. Inga duplicerade definitioner.

| Fält | Max | Per-item max | Typ | Obligatorisk |
|------|-----|-------------|-----|-------------|
| `tool_id` | 160 tecken | — | string | Ja |
| `name` | **80 tecken** ◀ NY | — | string | Ja |
| `description` | 300 tecken | — | string | Ja |
| `keywords` | 20 st | 40 tecken | list[string] | Ja (min 3) |
| `example_queries` | 10 st | 120 tecken | list[string] | Ja (min 2) |
| `excludes` | 15 st | **60 tecken** ◀ NY | list[string] | Nej |
| `category` | **40 tecken** ◀ NY | — | string | Ja |
| `main_identifier` | 80 tecken | — | string | Nej |
| `core_activity` | 120 tecken | — | string | Nej |
| `unique_scope` | 120 tecken | — | string | Nej |
| `geographic_scope` | 80 tecken | — | string | Nej |
| `base_path` | 200 tecken | — | string | Nej |

**Nya gränser (markerade ◀ NY):**
- `name`: 80 tecken (tidigare obegränsat)
- `category`: 40 tecken (tidigare obegränsat)
- `excludes` per item: 60 tecken (tidigare obegränsat per item)

### 4.2 Kvalitetsregler för metadata

Dessa regler gäller ALL metadata — oavsett om den skapas manuellt eller via LLM.

**Description:**
- Ska vara på svenska
- Ska beskriva verktygets primära funktion i 1-2 meningar
- Får INTE innehålla tool_id, endpoint-namn eller snake_case-identifierare
- Ska inte upprepas ordagrant från ett annat verktygs beskrivning

**Keywords:**
- Ska vara på svenska
- 3-20 st (minimum 3 krävs)
- Inga duplicerade keywords (case-insensitive)
- Inga keywords som bara är 1 tecken
- Inga generiska keywords ("data", "information", "resultat", "visa")

**Example queries:**
- Ska vara på svenska
- Ska innehålla minst en specifik kontext (plats, tid, eller domänterm)
- Får INTE innehålla tool_id, verktygsnamn, eller snake_case-identifierare
- Ska vara 6-25 ord långa
- Ska vara unika (inga dubbletter)

**Excludes:**
- Ska vara termer som detta verktyg INTE ska matcha
- Ska vara relevanta för att skilja från närliggande verktyg i samma namespace

### 4.3 Keyword-pruning ◀ NY

**Problem:** Keywords ackumuleras vid varje LLM-förslag utan att gamla tas bort.

**Lösning:** `prune_low_value_keywords()` — körs innan nya keywords läggs till:

```python
def prune_low_value_keywords(
    current_keywords: list[str],
    new_keywords: list[str],
    tool_description: str,
    max_keywords: int = METADATA_MAX_KEYWORDS,
) -> list[str]:
    """
    Behåll keywords som:
    1. Förekommer i tool_description (relevans-check)
    2. Är unika bland sibling-verktyg i samma namespace
    3. Har > 2 tecken
    4. Inte är generiska (blocklist)

    Prioritet: nya keywords > relevanta befintliga > övriga
    """
```

**Effekt:** Keywords hålls vid 10-15 st (under max 20) med hög relevans.

### 4.4 enforce_metadata_limits() — obligatorisk på ALLA svar

**Nuvarande gap:** Intent/agent LLM-förslag i `metadata_audit_service.py` anropar INTE `enforce_metadata_limits()` direkt.

**Fix:** Lägg till explicit anrop efter ALL LLM-parsing:

```python
# metadata_audit_service.py — _build_llm_intent_metadata_suggestion
proposed = _extract_json_object(llm_response)
proposed = enforce_metadata_limits(proposed)  # ◀ NY — obligatorisk
proposed = validate_suggestion_quality(proposed, current)  # ◀ NY
```

### 4.5 Synkroniserad definition

```
bigtool_store.py (ENDA KÄLLAN)
    │
    ├─ importeras av → admin_tool_settings.py (Pydantic schemas)
    ├─ importeras av → metadata_audit_service.py
    ├─ importeras av → tool_evaluation_service.py
    ├─ importeras av → metadata_separation_service.py
    │
    └─ exponeras via → GET /admin/tool-settings/metadata-limits ◀ NY
                            │
                            └─ frontend hämtar vid mount → ersätter hardkodade konstanter
```

---

## 5. LLM-kvalitetssystem

### 5.1 Probe-kvalitet (befintlig + förbättringar)

Befintlig kvalitetsfiltrering behålls (`_is_valid_probe_query`, `_probe_query_quality_row`). Tillägg:

| Ny regel | Syfte |
|----------|-------|
| **Minimum kvalitetspoäng 2.0** för probing | Filtrera bort medelmåttiga prober |
| **Max 3 prober per verktyg med <3.0 poäng** | Balansera kvalitet vs täckning |
| **Duplicate-check mot eval-historik** | Undvik att köra samma probe igen |

### 5.2 Suggestion-kvalitet (nytt)

Ny funktion `validate_suggestion_quality()` som körs på ALLA LLM-förslag:

```python
def validate_suggestion_quality(
    proposed: dict,
    current: dict,
    layer: str,  # "intent" | "agent" | "tool"
) -> dict | None:
    """
    Returnerar validerat förslag eller None om det underkänns.

    Checks:
    1. enforce_metadata_limits() — hårda gränser
    2. Inga tool_id/snake_case i example_queries
    3. Inga engelska texter (description, keywords, examples)
    4. Keywords: inga generiska, inga 1-teckens, inga duplikater
    5. Description: inte identisk med annat verktygs description
    6. Route: måste vara i tillåten enum (intent-lager)
    7. Priority: 1-1000 (intent-lager)
    8. Enabled: får INTE sättas till false av LLM ◀ NY
    9. Category: får INTE ändras om inte explicit begärt ◀ NY
    10. Net change: minst 1 fält måste faktiskt vara annorlunda
    """
```

### 5.3 Suggestion diff-vy ◀ NY

Frontend visar förslag som diff istället för fullständig metadata:

```
┌─ Förslag: smhi_weather ──────────────────────────────────┐
│                                                          │
│  description:                                            │
│  − "Väderprognos från SMHI"                              │
│  + "SMHI:s detaljerade väderprognos för svenska orter"   │
│                                                          │
│  keywords:                                               │
│  + "regn"                                                │
│  + "snö"                                                 │
│  − "väderlek"  (prunad: generisk)                        │
│                                                          │
│  example_queries:                                        │
│  + "Blir det regn i Göteborg i helgen?"                  │
│                                                          │
│  Validering: ✓ Alla gränser OK                           │
│              ✓ Inga BSSS-lås bryts                       │
│              ✓ Svenska text                              │
│                                                          │
│  [Godkänn] [Avvisa] [Redigera manuellt →]               │
└──────────────────────────────────────────────────────────┘
```

### 5.4 Prompt-arkitekturguard (befintlig + striktare)

Befintlig `_apply_prompt_architecture_guard()` behålls. Tillägg:

| Ny regel | Effekt |
|----------|--------|
| LLM får INTE föreslå `enabled: false` | Förhindrar att intent/agent stängs av av misstag |
| LLM får INTE ändra `category` utan explicit instruktion | Förhindrar oväntad omkategorisering |
| Alla LLM-förslag loggas med request-ID | Spårbarhet i audit trail |
| LLM timeout 15s (sänkt från 18-20s) | Snabbare fallback vid långsam LLM |

### 5.5 Retrieval tuning-förslag — validering

Befintlig `normalize_retrieval_tuning()` behålls (korrekt clamping per fält). Tillägg:

| Ny regel | Syfte |
|----------|-------|
| Max 20% förändring per parameter per körning | Förhindra dramatiska hopp |
| Logg av före/efter-värden | Spårbarhet |
| Revert-knapp i UI | Snabb återställning |

---

## 6. Lifecycle-integration

### 6.1 Nuvarande problem

| Problem | Konsekvens |
|---------|------------|
| Lifecycle på separat sida | Admin navigerar bort från arbetsflödet |
| Ingen auto-promotion | Admin måste manuellt kontrollera varje verktyg |
| Ingen audit trail historik | Vet ej vem som promotade/rollbackade |
| Frontend striktare än backend (blockerar null success_rate) | Nya verktyg kan inte promota via UI |
| Fallback laddar ALLA verktyg vid lifecycle-check-fel | Review-verktyg kan läcka till produktion |

### 6.2 Lösning

**A) Lifecycle-status synlig överallt:**
- Varje verktyg i Metadata-fliken visar `● Live` / `○ Review` badge
- Success rate visas intill badgen
- Filter: "Visa bara Review" / "Visa bara Live"

**B) Auto-promotion-förslag:**
- Efter eval synkar `_sync_eval_to_lifecycle()` metrics (befintligt)
- NY: Om `success_rate >= required_success_rate` visas "Redo att promota" badge
- NY: Promotion-förslag direkt i Kalibrering-fliken efter eval
- Admin godkänner — inte automatiskt (safety first)

**C) Audit trail-tabell:**
```sql
CREATE TABLE global_tool_lifecycle_audit (
    id SERIAL PRIMARY KEY,
    tool_id VARCHAR(160) NOT NULL,
    old_status VARCHAR(10),          -- 'review' | 'live' | NULL (first entry)
    new_status VARCHAR(10) NOT NULL,
    success_rate FLOAT,
    trigger VARCHAR(20) NOT NULL,    -- 'manual' | 'eval_sync' | 'rollback' | 'bulk_promote'
    reason TEXT,
    changed_by_id UUID REFERENCES "user"(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_lifecycle_audit_tool_id ON global_tool_lifecycle_audit(tool_id);
CREATE INDEX ix_lifecycle_audit_created_at ON global_tool_lifecycle_audit(created_at);
```

**D) Säker fallback:**
```python
# registry.py — build_tools_async()
# Nuvarande: Om lifecycle-check misslyckas → ladda ALLA verktyg
# NY: Om lifecycle-check misslyckas → ladda från cache, eller logga error och returnera tomt
try:
    live_ids = await get_live_tool_ids(session)
except Exception:
    live_ids = _CACHED_LIVE_IDS  # senaste kända live-set
    logger.error("Lifecycle check failed, using cached live IDs")
```

**E) Ta bort `/admin/lifecycle` som separat sida:**
- Flytta allt till Överblick-fliken i `/admin/tools`
- Behåll backend-endpoints (de är korrekta)
- Uppdatera `admin-layout.tsx` — ta bort lifecycle nav-item

---

## 7. Implementeringsplan

### Fas 1: Grund (bugfixar + metadata-standard)

**Mål:** Stabilisera systemet. Fixa P0/P1-buggar. Etablera metadata-standard.

| # | Uppgift | Fil(er) | Typ |
|---|---------|---------|-----|
| 1.1 | Konsolidera `DEFAULT_TOOL_RETRIEVAL_TUNING` — en enda källa | `bigtool_store.py`, `tool_retrieval_tuning_service.py` | Refaktor |
| 1.2 | Uppdatera score-trösklar till kalibrerade värden | `tool_retrieval_tuning_service.py` | Bugfix |
| 1.3 | Implementera holdout-validering i auto-loop | `admin_tool_settings_routes.py` | Bugfix |
| 1.4 | Lägg till `enforce_metadata_limits()` på intent/agent LLM-förslag | `metadata_audit_service.py` | Bugfix |
| 1.5 | Lägg till `name` (80), `category` (40), `excludes` per-item (60) gränser | `bigtool_store.py`, `admin-tool-settings.types.ts`, `admin_tool_settings.py` | Standard |
| 1.6 | Skapa `validate_suggestion_quality()` | `bigtool_store.py` (ny funktion) | Kvalitet |
| 1.7 | Hindra LLM från att föreslå `enabled: false` eller ändra `category` | `metadata_audit_service.py`, `tool_evaluation_service.py` | Kvalitet |
| 1.8 | Ny endpoint `GET /admin/tool-settings/metadata-limits` | `admin_tool_settings_routes.py` | API |
| 1.9 | Tidbaserad eval-jobb-städning (24h) | `admin_tool_settings_routes.py` | Bugfix |
| 1.10 | Optimistisk låsning vid metadata-uppdatering | `admin_tool_settings_routes.py` | Bugfix |

### Fas 2: Backend-refaktorering

**Mål:** Kodkvalitet. Inga filer >1500 rader som monoliter. Duplicering borta.

| # | Uppgift | Fil(er) | Typ |
|---|---------|---------|-----|
| 2.1 | Refaktorera 8 if-block i `build_tool_index()` till loop | `bigtool_store.py` | Refaktor |
| 2.2 | Registry-mönster för `_namespace_for_*` | `bigtool_store.py` | Refaktor |
| 2.3 | Kombinera `smart_retrieve_tools` + `_with_breakdown` | `bigtool_store.py` | Refaktor |
| 2.4 | Extrahera gemensam eval-baslogik ur `run_tool_evaluation`/`run_tool_api_input_evaluation` | `tool_evaluation_service.py` | Refaktor |
| 2.5 | Implementera `prune_low_value_keywords()` | `bigtool_store.py` | Ny funktion |
| 2.6 | Lifecycle audit trail — migration + service | `db.py`, `tool_lifecycle_service.py`, ny migration | Ny feature |
| 2.7 | Lifecycle auto-promotion badge (backend: ny endpoint eller utöka befintligt response) | `admin_tool_lifecycle_routes.py` | Utökning |
| 2.8 | Säker fallback med cache vid lifecycle-check-fel | `registry.py` | Bugfix |
| 2.9 | BSSS lock-override → DB audit trail | `admin_tool_settings_routes.py` | Bugfix |
| 2.10 | Contrast memory eviction policy (max 500 entries, LRU) | `metadata_separation_service.py` | Optimering |
| 2.11 | Embed cache eviction policy (max 2000 entries, LRU) | `metadata_separation_service.py` | Optimering |

### Fas 3: Frontend-omstrukturering

**Mål:** 3 flikar. Lifecycle integrerad. Komponentfilerna <1500 rader vardera.

| # | Uppgift | Fil(er) | Typ |
|---|---------|---------|-----|
| 3.1 | Skapa flik-orchestrator `tool-admin-page.tsx` (~200 rader) | Ny fil | Ny |
| 3.2 | Flik 1: `metadata-tab.tsx` — vikter + per-verktyg redigering + lås | Ny fil (extraherat ur tool-settings-page + metadata-catalog-tab) | Refaktor |
| 3.3 | Flik 2: `calibration-tab.tsx` — guidat 3-steg + fas | Ny fil (extraherat ur tool-settings-page + metadata-catalog-tab) | Refaktor |
| 3.4 | Flik 3: `overview-tab.tsx` — nyckeltal + trend + lifecycle + historik | Ny fil (extraherat ur tool-settings-page + tool-lifecycle-page) | Refaktor |
| 3.5 | Suggestion diff-komponent `suggestion-diff-view.tsx` | Ny fil | Ny |
| 3.6 | Lifecycle-badge-komponent (återanvändbar i alla flikar) | Ny fil | Ny |
| 3.7 | Hämta metadata-gränser dynamiskt från backend | `admin-tool-settings-api.service.ts` | Utökning |
| 3.8 | Lägga till `maxLength` på HTML-inputs (UX feedback) | Alla metadata-forms | UX |
| 3.9 | Frontend: Lägg till enforce_metadata_limits på agent/intent Zod-schemas | `admin-tool-settings.types.ts` | Bugfix |
| 3.10 | Ta bort `/admin/lifecycle` som separat sida | `admin-layout.tsx`, ta bort `lifecycle/page.tsx` | Cleanup |
| 3.11 | Audit trail-komponent i Överblick | Ny fil | Ny |

### Fas 4: Polish & Validering

**Mål:** Silkeslen UX. Inga lösa trådar.

| # | Uppgift | Fil(er) | Typ |
|---|---------|---------|-----|
| 4.1 | End-to-end test: redigera → audit → eval → promote | Manuell testning | QA |
| 4.2 | Validera att alla LLM-förslag passerar `validate_suggestion_quality()` | Backend-test | Test |
| 4.3 | Verifiera holdout-validering i auto-loop | Backend-test | Test |
| 4.4 | Kör `calibrate_embedding_thresholds.py` och applicera | Script + DB | Kalibrering |
| 4.5 | Uppdatera CLAUDE.md med ny admin-struktur | `CLAUDE.md` | Docs |
| 4.6 | Lägga till exponential backoff på eval-polling (1.2s → 2s → 4s → 8s) | Frontend | UX |
| 4.7 | Lazy-loading av flikar (React.lazy + Suspense) | Frontend | Optimering |

---

## 8. Filändringar per fas

### Fas 1 — Ändrade filer

```
surfsense_backend/
├── app/agents/new_chat/bigtool_store.py          # 1.1, 1.5, 1.6
├── app/services/tool_retrieval_tuning_service.py  # 1.1, 1.2
├── app/routes/admin_tool_settings_routes.py       # 1.3, 1.8, 1.9, 1.10
├── app/services/metadata_audit_service.py         # 1.4, 1.7
├── app/services/tool_evaluation_service.py        # 1.7
└── app/schemas/admin_tool_settings.py             # 1.5

surfsense_web/
└── contracts/types/admin-tool-settings.types.ts   # 1.5
```

### Fas 2 — Ändrade filer

```
surfsense_backend/
├── app/agents/new_chat/bigtool_store.py           # 2.1, 2.2, 2.3, 2.5
├── app/services/tool_evaluation_service.py        # 2.4
├── app/services/metadata_separation_service.py    # 2.10, 2.11
├── app/services/tool_lifecycle_service.py         # 2.6, 2.7
├── app/routes/admin_tool_lifecycle_routes.py       # 2.7
├── app/routes/admin_tool_settings_routes.py       # 2.9
├── app/agents/new_chat/tools/registry.py          # 2.8
├── app/db.py                                      # 2.6 (ny tabell)
└── alembic/versions/XXX_add_lifecycle_audit.py    # 2.6 (ny migration)
```

### Fas 3 — Ändrade/nya filer

```
surfsense_web/
├── components/admin/
│   ├── tool-admin-page.tsx          # 3.1 — NY orchestrator
│   ├── tabs/
│   │   ├── metadata-tab.tsx         # 3.2 — NY
│   │   ├── calibration-tab.tsx      # 3.3 — NY
│   │   └── overview-tab.tsx         # 3.4 — NY
│   ├── shared/
│   │   ├── suggestion-diff-view.tsx # 3.5 — NY
│   │   ├── lifecycle-badge.tsx      # 3.6 — NY
│   │   └── audit-trail.tsx          # 3.11 — NY
│   ├── tool-settings-page.tsx       # DEPRECATED → ersätts av tool-admin-page
│   ├── metadata-catalog-tab.tsx     # DEPRECATED → logik flyttad till tabs/
│   └── tool-lifecycle-page.tsx      # DEPRECATED → logik flyttad till overview-tab
├── contracts/types/
│   └── admin-tool-settings.types.ts # 3.9
├── lib/apis/
│   └── admin-tool-settings-api.service.ts # 3.7
├── app/admin/
│   ├── tools/page.tsx               # Uppdaterad: renderar tool-admin-page
│   └── lifecycle/page.tsx           # 3.10 — BORTTAGEN (redirect till /admin/tools)
└── components/admin/admin-layout.tsx # 3.10 — Ta bort lifecycle nav-item
```

### Raduppskattning (efter refaktorering)

| Fil | Före | Efter | Delta |
|-----|------|-------|-------|
| `tool-settings-page.tsx` | 5 283 | 0 (deprecated) | −5 283 |
| `metadata-catalog-tab.tsx` | 4 221 | 0 (deprecated) | −4 221 |
| `tool-lifecycle-page.tsx` | 427 | 0 (deprecated) | −427 |
| `tool-admin-page.tsx` | — | ~200 | +200 |
| `metadata-tab.tsx` | — | ~1 200 | +1 200 |
| `calibration-tab.tsx` | — | ~1 400 | +1 400 |
| `overview-tab.tsx` | — | ~900 | +900 |
| `suggestion-diff-view.tsx` | — | ~250 | +250 |
| `lifecycle-badge.tsx` | — | ~80 | +80 |
| `audit-trail.tsx` | — | ~200 | +200 |
| **Frontend totalt** | **9 931** | **~4 430** | **−5 501 (−55%)** |

| Fil | Före | Efter | Delta |
|-----|------|-------|-------|
| `tool_evaluation_service.py` | 5 199 | ~3 800 | −1 399 |
| `admin_tool_settings_routes.py` | 7 257 | ~7 400 (+holdout, +limits endpoint) | +143 |
| `bigtool_store.py` | 2 400 | ~2 200 | −200 |
| **Backend totalt** | **14 856** | **~13 400** | **−1 456 (−10%)** |

---

## 9. Migreringsplan

### Steg-för-steg

```
1. Fas 1 (bugfixar + standard)
   └─ Kan deployas oberoende
   └─ Inga breaking changes
   └─ Kräver: kör calibrate_embedding_thresholds.py efter deploy

2. Fas 2 (backend-refaktorering)
   └─ Kräver: ny Alembic-migration (lifecycle audit trail)
   └─ Inga breaking API-ändringar
   └─ Kör: alembic upgrade head

3. Fas 3 (frontend-omstrukturering)
   └─ Breaking: /admin/lifecycle → redirect till /admin/tools#overview
   └─ Kräver: frontend rebuild
   └─ Gamla komponenter deprecated men kan behållas som fallback

4. Fas 4 (polish)
   └─ Kan deployas oberoende
   └─ Inga breaking changes
```

### Rollback-plan

| Fas | Rollback |
|-----|----------|
| Fas 1 | Revert commit. Inga DB-migrations. |
| Fas 2 | `alembic downgrade -1`. Ny tabell tas bort. |
| Fas 3 | Revert commit. Gamla komponenter finns kvar som deprecated. |
| Fas 4 | Revert commit. |

---

---

## 10. Implementeringsstatus

> Uppdaterad: 2026-03-03

### Fas 1: Grund — KLAR

| # | Uppgift | Status |
|---|---------|--------|
| 1.1 | Konsolidera `DEFAULT_TOOL_RETRIEVAL_TUNING` | ✅ `get_default_tuning_as_dict()` i bigtool_store.py |
| 1.2 | Uppdatera score-trösklar | ✅ Importeras från bigtool_store |
| 1.3 | Holdout-validering i auto-loop | ✅ Slutvalidering tillagd i admin_tool_settings_routes.py |
| 1.4 | `enforce_metadata_limits()` på LLM-förslag | ✅ Anropas i `_build_llm_intent/agent_metadata_suggestion` |
| 1.5 | Nya metadata-gränser (name 80, category 40, etc.) | ✅ Backend + frontend synkade |
| 1.6 | `validate_suggestion_quality()` | ✅ Ny funktion i bigtool_store.py |
| 1.7 | Hindra `enabled: false` / category-ändring | ✅ I validate_suggestion_quality |
| 1.8 | `GET /metadata-limits` endpoint | ✅ Ny endpoint i admin_tool_settings_routes.py |
| 1.9 | Tidbaserad eval-jobb-städning (24h) | ✅ `_is_expired_job()` + alla 3 prune-funktioner |
| 1.10 | Optimistisk låsning | ✅ `expected_version_hash` i PUT handler |

### Fas 2: Backend-refaktorering — KLAR (delvis)

| # | Uppgift | Status |
|---|---------|--------|
| 2.1 | Refaktorera 9 if-block till `_PROVIDER_DEFINITIONS` | ✅ Unified lookup |
| 2.2 | Registry-mönster `_NAMESPACE_REGISTRY` | ✅ Prefix-baserad dispatch |
| 2.3 | Kombinera `smart_retrieve_tools` | ✅ `include_breakdown` parameter |
| 2.4 | Extrahera gemensam eval-baslogik | ⏳ Ej påbörjad |
| 2.5 | `prune_low_value_keywords()` | ⏳ Ej påbörjad |
| 2.6 | Lifecycle audit trail — DB-modell | ✅ `GlobalToolLifecycleAudit` i db.py |
| 2.7 | Auto-promotion badge | ⏳ Ej påbörjad |
| 2.8 | Säker fallback med cache | ⏳ Ej påbörjad |
| 2.9 | BSSS lock-override audit trail | ⏳ Ej påbörjad |
| 2.10 | Contrast memory eviction | ⏳ Ej påbörjad |
| 2.11 | Embed cache eviction | ⏳ Ej påbörjad |

### Fas 3: Frontend-omstrukturering — KLAR

| # | Uppgift | Status |
|---|---------|--------|
| 3.1 | `tool-admin-page.tsx` orchestrator | ✅ 3-flik med lazy loading |
| 3.2 | `metadata-tab.tsx` | ✅ ~1250 rader, extraherat |
| 3.3 | `calibration-tab.tsx` | ✅ Extraherat med guidat 3-steg |
| 3.4 | `overview-tab.tsx` | ✅ Nyckeltal + trend + lifecycle |
| 3.5 | `suggestion-diff-view.tsx` | ✅ Diff-vy med checkboxar |
| 3.6 | `lifecycle-badge.tsx` | ✅ Återanvändbar badge |
| 3.7 | `getMetadataLimits()` i API-service | ✅ Tillagd |
| 3.8 | `maxLength` på HTML-inputs | ✅ I metadata-tab.tsx |
| 3.9 | Nya gränser i frontend Zod-schemas | ✅ `admin-tool-settings.types.ts` |
| 3.10 | Ta bort `/admin/lifecycle` | ✅ Redirect till /admin/tools |
| 3.11 | `audit-trail.tsx` komponent | ✅ I shared/ |

### Fas 4: Polish — DELVIS KLAR

| # | Uppgift | Status |
|---|---------|--------|
| 4.1 | End-to-end test | ⏳ Kräver deploy |
| 4.2 | Validera LLM-förslag | ⏳ Kräver backend-tester |
| 4.3 | Verifiera holdout-validering | ⏳ Kräver backend-tester |
| 4.4 | Kör calibrate_embedding_thresholds | ⏳ Kräver deploy |
| 4.5 | Uppdatera CLAUDE.md | ⏳ |
| 4.6 | Exponential backoff eval-polling | ⏳ |
| 4.7 | Lazy-loading av flikar | ✅ React.lazy + Suspense i tool-admin-page |

### Sammanfattning

| Fas | Klar | Kvar | Status |
|-----|------|------|--------|
| Fas 1 | 10/10 | 0 | ✅ KLAR |
| Fas 2 | 4/11 | 7 | 🔶 DELVIS |
| Fas 3 | 11/11 | 0 | ✅ KLAR |
| Fas 4 | 1/7 | 6 | 🔶 DELVIS |

**Totalt:** 26/39 uppgifter klara (67%)

### Nya filer skapade

```
surfsense_web/components/admin/
├── tool-admin-page.tsx              # 3-flik orchestrator (~95 rader)
├── tabs/
│   ├── metadata-tab.tsx             # Flik 1: Metadata (~1250 rader)
│   ├── calibration-tab.tsx          # Flik 2: Kalibrering (~1400 rader)
│   └── overview-tab.tsx             # Flik 3: Överblick (~780 rader)
├── shared/
│   ├── suggestion-diff-view.tsx     # Diff-vy (~140 rader)
│   ├── lifecycle-badge.tsx          # Badge (~50 rader)
│   └── audit-trail.tsx              # Audit trail (~130 rader)
```

### Deprecated filer

```
surfsense_web/components/admin/
├── tool-settings-page.tsx           # DEPRECATED → ersatt av tabs/*
├── tool-lifecycle-page.tsx          # DEPRECATED → ersatt av overview-tab.tsx
```

---

*Utvecklingsplan skapad 2026-03-03. Baseras på `admin_tools_v1.md` och `admin_tools_v1_code_audit.md`.*
*Implementeringsstatus uppdaterad 2026-03-03.*
