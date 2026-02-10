# API Integration (OnSeek)

This document tracks API integrations that are live in the OnSeek system, with
their tools and categories. More APIs will be added over time.

## SCB (PxWeb API 2.0)

**Purpose:** Official Swedish statistics (population, labor market, prices, etc).  
**Namespace:** `tools/statistics/scb/...`  
**Citations:** Enabled via TOOL_OUTPUT chunk ingestion.  

### Categories (top-level tools)
- scb_arbetsmarknad
- scb_befolkning
- scb_boende_byggande
- scb_demokrati
- scb_energi
- scb_finansmarknad
- scb_handel
- scb_hushall
- scb_halsa_sjukvard
- scb_jordbruk
- scb_kultur
- scb_levnadsforhallanden
- scb_miljo
- scb_nationalrakenskaper
- scb_naringsverksamhet
- scb_offentlig_ekonomi
- scb_priser_konsumtion
- scb_socialtjanst
- scb_transporter
- scb_utbildning
- scb_amnesovergripande

### Focused sub-tools
**Befolkning**
- scb_befolkning_folkmangd
- scb_befolkning_forandringar
- scb_befolkning_fodda

**Arbetsmarknad**
- scb_arbetsmarknad_arbetsloshet
- scb_arbetsmarknad_sysselsattning
- scb_arbetsmarknad_lon

**Utbildning**
- scb_utbildning_gymnasie
- scb_utbildning_hogskola
- scb_utbildning_forskning

**Naringsliv**
- scb_naringsliv_foretag
- scb_naringsliv_omsattning
- scb_naringsliv_nyforetagande

**Miljo**
- scb_miljo_utslapp
- scb_miljo_energi

**Priser / Konsumtion**
- scb_priser_kpi
- scb_priser_inflation

**Transporter**
- scb_transporter_person
- scb_transporter_gods

**Boende / Byggande**
- scb_boende_bygglov
- scb_boende_nybyggnation
- scb_boende_bestand

---

## SMHI (Weather API)

**Purpose:** Weather forecasts and current conditions.  
**Namespace:** `tools/action/travel`  
**Citations:** TOOL_OUTPUT ingestion enabled.  

### Tools
- smhi_weather

---

## Notes

- All tools are registered via `langgraph-bigtool` with namespace-aware selection.
- Tool outputs are ingested as `TOOL_OUTPUT` documents for citations.
