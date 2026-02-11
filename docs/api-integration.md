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

## Bolagsverket (Open Data API v2.0)

**Purpose:** Company registry data (orgnr, status, owners, economy).  
**Namespace:** `tools/bolag/bolagsverket_*`  
**Citations:** TOOL_OUTPUT ingestion enabled.  

### Categories
- bolagsverket_info
- bolagsverket_sok
- bolagsverket_ekonomi
- bolagsverket_styrelse
- bolagsverket_registrering

### Tools
- bolagsverket_info_basic
- bolagsverket_info_status
- bolagsverket_info_adress
- bolagsverket_sok_namn
- bolagsverket_sok_orgnr
- bolagsverket_sok_bransch
- bolagsverket_sok_region
- bolagsverket_sok_status
- bolagsverket_ekonomi_bokslut
- bolagsverket_ekonomi_arsredovisning
- bolagsverket_ekonomi_nyckeltal
- bolagsverket_styrelse_ledning
- bolagsverket_styrelse_agarstruktur
- bolagsverket_styrelse_firmatecknare
- bolagsverket_registrering_fskatt
- bolagsverket_registrering_moms
- bolagsverket_registrering_konkurs
- bolagsverket_registrering_andringar

---

## Trafikverket (Open API v2.0)

**Purpose:** Traffic data (roads, trains, cameras, weather).  
**Namespace:** `tools/trafik/trafikverket_*`  
**Citations:** TOOL_OUTPUT ingestion enabled.  

### Categories
- trafikverket_trafikinfo
- trafikverket_tag
- trafikverket_vag
- trafikverket_vader
- trafikverket_kameror
- trafikverket_prognos

### Tools
- trafikverket_trafikinfo_storningar
- trafikverket_trafikinfo_olyckor
- trafikverket_trafikinfo_koer
- trafikverket_trafikinfo_vagarbeten
- trafikverket_tag_forseningar
- trafikverket_tag_tidtabell
- trafikverket_tag_stationer
- trafikverket_tag_installda
- trafikverket_vag_status
- trafikverket_vag_underhall
- trafikverket_vag_hastighet
- trafikverket_vag_avstangningar
- trafikverket_vader_stationer
- trafikverket_vader_halka
- trafikverket_vader_vind
- trafikverket_vader_temperatur
- trafikverket_kameror_lista
- trafikverket_kameror_snapshot
- trafikverket_kameror_status
- trafikverket_prognos_trafik
- trafikverket_prognos_vag
- trafikverket_prognos_tag

---

## Trafiklab (Realtime transit)

**Purpose:** Public transport departures and route matching.  
**Namespace:** `tools/action/travel`  
**Citations:** TOOL_OUTPUT ingestion enabled.  

### Tools
- trafiklab_route

---

## Libris (Library catalog)

**Purpose:** Search the Libris XL catalog (books/media).  
**Namespace:** `tools/action/data`  
**Citations:** TOOL_OUTPUT ingestion enabled.  

### Tools
- libris_search

---

## Notes

- All tools are registered via `langgraph-bigtool` with namespace-aware selection.
- Tool outputs are ingested as `TOOL_OUTPUT` documents for citations.
