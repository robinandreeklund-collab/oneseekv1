# NEXUS — Gap-analys: Vision vs Implementation

> **Datum:** 2026-03-04
> **Källa:** `docs/eval/nexus.md` (vision), `docs/eval/nexus_dev_plan.md` (dev-plan)
> **Branch:** `claude/nexus-dev-plan-hjhsk`

---

## Sammanfattning

NEXUS har en fungerande grundstruktur med 6 tabs (Översikt, Rymd, Forge, Loop, Ledger, Deploy),
komplett backend-service med routing pipeline, och API-klient. Men flera kritiska features
som beskrivs i visionen saknas eller är trasiga. Detta dokument listar varje gap.

---

## 1. ÖVERSIKT-tab

### Fixade problem (denna session)

| Problem | Rotorsak | Fix |
|---------|----------|-----|
| Band 0-2 = 0% | Min-max normalisering + Platt sigmoid (a=1,b=0) förstörde scores | Embedding-first scoring, passthrough vid unfitted |
| OOD Rate 39.4% | Alla queries hamnade i Band 3/4 | Scoring-fix → korrekta bands |
| Zone-metriker "—" | DB-rader hade NULL | `_update_zone_metrics()` beräknar från events |
| Ledger saknade bigtool | Bara 4 av 5 stages | Alla 5 stages skrivs nu |

### Kvarvarande gap

| # | Gap | Visionens krav | Nuläge | Åtgärd |
|---|-----|----------------|--------|--------|
| 1.1 | **Bara 2 av 4 zoner visas** | 4 zoner: kunskap, skapande, konversation, jämförelse | DB har bara kunskap + jämförelse seedade | Seeda alla 4 i DB-startup |
| 1.2 | **Dark Matter panel ej monterad** | OOD-kluster synliga i översikt | Komponent finns men monteras aldrig | Lägg till i OverviewTab |
| 1.3 | **Routing events viewer saknas** | Visa senaste routing-beslut | `getRoutingEvents()` finns i API men ingen UI | Bygg RoutingEventsTable |
| 1.4 | **Calibration UI saknas** | Fit-knapp, ECE per zon, Platt A/B | Endpoints finns men ingen UI | Bygg CalibrationPanel |
| 1.5 | **Feedback-logging saknas** | Thumbs up/down per routing event | Backend stödjer det men ingen UI | Lägg till i routing events |

---

## 2. RYMD-tab (Space Auditor)

| # | Gap | Visionens krav | Nuläge | Åtgärd |
|---|-----|----------------|--------|--------|
| 2.1 | **Separation Score låg** | ≥60% (target 73%) | 20.4% | Förbättras av scoring-fix + zone-prefix |
| 2.2 | **UMAP ej interaktiv** | Zoom, pan, filter per zon | Statisk canvas | Lägg till interaktivitet |
| 2.3 | **Confusion pairs okalibrerade** | Alla >98% | Utan zone-prefix alla tools nära | Fixat i scoring — prefix-trick appliceras |
| 2.4 | **Hubness alerts visas inte tydligt** | Per-verktyg "false magnet" varningar | Finns men inga triggers p.g.a. dåliga scores | Beräknas korrekt efter fix |

---

## 3. FORGE-tab

| # | Gap | Visionens krav | Nuläge | Åtgärd |
|---|-----|----------------|--------|--------|
| 3.1 | **0 verifierade cases** | Roundtrip-verifiering i top-3 | `retrieve_fn` var None | **Fixat** — riktig retrieve_fn nu |
| 3.2 | **Quality score ej synlig** | Visa quality_score per case | Lagras i DB men visas inte | Lägg till i ForgeTab UI |
| 3.3 | **Kan ej radera cases** | DELETE endpoint + UI | Endpoint saknas i backend + frontend | Implementera DELETE + UI-knapp |
| 3.4 | **Case-godkännande workflow** | Approve/reject per case | Saknas helt | Bygg approval-toggle i UI |
| 3.5 | **Sök bland cases** | Sökfält i case-listan | Saknas | Lägg till sökfunktion |

---

## 4. LOOP-tab

| # | Gap | Visionens krav | Nuläge | Åtgärd |
|---|-----|----------------|--------|--------|
| 4.1 | **Proposals visas inte** | Diff-vy: current → proposed metadata | Bara "0 approved" i tabell | Bygg proposals-expansion med diff |
| 4.2 | **Godkänn/Avvisa per proposal** | Knappar per metadata-förslag | Endpoint finns men ingen UI | Lägg till approve/reject per proposal |
| 4.3 | **Steg-för-steg progress** | 7-stegs pipeline-indikator under körning | Bara status-badge | Bygg progress-stepper |
| 4.4 | **Root causes visas inte** | LLM root cause per failure cluster | Beräknas men returneras aldrig till UI | Exponera i API-response + visa |
| 4.5 | **Hard negatives minerade** | Visa antal nya hard neg per run | Beräknas men visas aldrig | Lägg till i run-detaljer |
| 4.6 | **Band distribution per run** | Visa hur queries fördelades | Sparas i metadata_proposals men visas inte | Lägg till i expanderad vy |

---

## 5. LEDGER-tab

| # | Gap | Visionens krav | Nuläge | Åtgärd |
|---|-----|----------------|--------|--------|
| 5.1 | **Saknade bigtool stage** | 5 stages: intent→route→bigtool→rerank→e2e | Bara 4 stages skrevs | **Fixat** |
| 5.2 | **30-dagars trendgrafer** | Sparklines/kurvor per stage | `getLedgerTrend()` finns men anropas aldrig | Bygg trendgraf-komponent |
| 5.3 | **Per-namespace filter** | Filtrera metriker per namespace | Backend har fältet men UI filtrerar inte | Lägg till namespace-dropdown |
| 5.4 | **Reranker before/after** | Visuell jämförelse pre/post rerank | Bara ett nummer | Bygg delta-visualisering |

---

## 6. DEPLOY-tab

| # | Gap | Visionens krav | Nuläge | Åtgärd |
|---|-----|----------------|--------|--------|
| 6.1 | **Bekräftelse-dialog vid rollback** | Confirm innan destructive action | Direkt rollback utan confirm | Lägg till AlertDialog |
| 6.2 | **Gate-detaljer expanderbara** | Visa krav + rekommendationer per gate | Bara score + pass/fail | Bygg expanderbar gate-sektion |
| 6.3 | **Deploy-historik** | Visa tidigare promotions/rollbacks | Saknas helt | Bygg historik-vy (behöver backend-stöd) |

---

## 7. Backend — Saknade endpoints & features

| # | Gap | Spec (dev-plan) | Nuläge | Åtgärd |
|---|-----|-----------------|--------|--------|
| 7.1 | **DELETE /nexus/forge/cases/{id}** | Radera enskilt testfall | Saknas | Implementera |
| 7.2 | **GET /nexus/loop/runs/{id}** | Detaljerad vy per loop-run | Saknas (bara list) | Implementera med proposals + root causes |
| 7.3 | **POST /nexus/dark-matter/{id}/review** | Markera OOD-kluster som granskat | Saknas | Implementera |
| 7.4 | **Celery tasks** | `forge_generate_task`, `auto_loop_task` | Allt körs inline | Implementera bakgrundsjobb |
| 7.5 | **Zone seeding vid startup** | Alla 4 zoner i nexus_zone_config | Bara 2 seedade | Seeda vid app-startup |
| 7.6 | **Shadow observer rapport** | Jämför NEXUS vs plattform | Endpoint finns men ingen UI | Exponera i dashboard |
| 7.7 | **Loop run detalj-response** | proposals, root_causes, band_dist, hard_neg_count | Beräknas men inte exponerat | Utöka API-response |

---

## 8. Frontend — Saknade komponenter

| # | Komponent | Beskrivet i | Nuläge | Var monteras |
|---|-----------|-------------|--------|-------------|
| 8.1 | **RoutingEventsTable** | Sprint 3 | Saknas helt | Översikt-tab |
| 8.2 | **CalibrationPanel** | Sprint 4 (4.8) | Saknas helt | Översikt-tab eller ny sektion |
| 8.3 | **FeedbackButtons** | Sprint 3 (3.7) | Saknas helt | Routing events viewer |
| 8.4 | **ProposalDiffView** | Sprint 3 (3.12) | Saknas helt | Loop-tab (expanderad run) |
| 8.5 | **TrendChart** | Sprint 3 (3.13) | Saknas helt | Ledger-tab |
| 8.6 | **ShadowReport** | Sprint 4 | Saknas helt | Ny sektion eller Översikt |
| 8.7 | **RollbackConfirmDialog** | Sprint 4 (4.6) | Saknas | Deploy-tab |

---

## Prioritetsordning

### P0 — Kritiska (pipeline fungerar inte korrekt utan dessa)
1. Seeda alla 4 zoner i DB (1.1)
2. Dark Matter panel i Översikt (1.2)
3. Loop proposals-vy med diff + godkänn/avvisa (4.1, 4.2)
4. Saknade backend-endpoints (7.1–7.3, 7.7)

### P1 — Viktiga (vision-features som saknas)
5. Routing events viewer (1.3)
6. Calibration UI (1.4)
7. Ledger trendgrafer (5.2)
8. Forge quality score + delete + sök (3.2–3.5)
9. Deploy bekräftelse + gate-detaljer (6.1–6.2)

### P2 — Förbättringar
10. Celery tasks (7.4)
11. Shadow observer UI (7.6)
12. Feedback UI (1.5)
13. Per-namespace filter i Ledger (5.3)
14. Deploy-historik (6.3)
15. UMAP interaktivitet (2.2)
