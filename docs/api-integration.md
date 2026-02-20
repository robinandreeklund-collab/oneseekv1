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

## SMHI (Open Data API)

**Purpose:** Weather forecasts/analysis/observations, hydrology, oceanography and fire risk.  
**Namespace:** `tools/weather/smhi`  
**Citations:** TOOL_OUTPUT ingestion enabled.  

### Categories
- smhi_vaderprognoser
- smhi_vaderanalyser
- smhi_vaderobservationer
- smhi_hydrologi
- smhi_oceanografi
- smhi_brandrisk

### Tools
- smhi_weather (legacy alias for metfcst forecasts)
- smhi_vaderprognoser_metfcst
- smhi_vaderprognoser_snow1g
- smhi_vaderanalyser_mesan2g
- smhi_vaderobservationer_metobs
- smhi_hydrologi_hydroobs
- smhi_hydrologi_pthbv
- smhi_oceanografi_ocobs
- smhi_brandrisk_fwif
- smhi_brandrisk_fwia

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

## Riksdagen (Öppna data API)

**Purpose:** Swedish Parliament's open data (propositions, motions, votes, members).  
**Namespace:** `tools/politik/*`  
**Citations:** TOOL_OUTPUT ingestion enabled.  

### Top-level Tools (5)
- **riksdag_dokument** - All 70+ document types
- **riksdag_ledamoter** - All members of parliament
- **riksdag_voteringar** - All voting records
- **riksdag_anforanden** - All speeches in chamber
- **riksdag_dokumentstatus** - Document status/history

### Document Sub-tools (12)
- **riksdag_dokument_proposition** (prop) - Government proposals
- **riksdag_dokument_motion** (mot) - Member proposals
- **riksdag_dokument_betankande** (bet) - Committee reports
- **riksdag_dokument_interpellation** (ip) - Questions to ministers (answered in chamber)
- **riksdag_dokument_fraga** (fr, frs) - Written questions
- **riksdag_dokument_protokoll** (prot) - Chamber protocols
- **riksdag_dokument_sou** (sou) - Government inquiries
- **riksdag_dokument_ds** (ds) - Ministry documents
- **riksdag_dokument_dir** (dir) - Committee directives
- **riksdag_dokument_rskr** (rskr) - Parliament resolutions
- **riksdag_dokument_eu** (KOM) - EU documents
- **riksdag_dokument_rir** (rir) - National Audit Office reports

### Anförande Sub-tools (2)
- **riksdag_anforanden_debatt** - Debate speeches (general, budget, foreign affairs)
- **riksdag_anforanden_fragestund** - Question time speeches

### Ledamot Sub-tools (2)
- **riksdag_ledamoter_parti** - Members filtered by party
- **riksdag_ledamoter_valkrets** - Members filtered by electoral district

### Votering Sub-tools (1)
- **riksdag_voteringar_resultat** - Detailed vote results

### API Parameters
- **sokord** - Search term
- **doktyp** - Document type (prop, mot, bet, etc.)
- **rm** - Parliamentary year (e.g., "2023/24", "2024/25")
- **from_datum**, **tom_datum** - Date range (YYYY-MM-DD)
- **organ** - Committee (FiU, FöU, SoU, etc.)
- **parti** - Party code (s, m, sd, c, v, kd, mp, l, -)
- **antal** - Max results (default 20, max 100)
- **anftyp** - Speech type (kam-ad, kam-bu, kam-fs, etc.)
- **valkrets** - Electoral district
- **fnamn**, **enamn** - First/last name
- **iid** - Member ID

### Usage Examples
**User:** "Propositioner om NATO 2024"  
→ `riksdag_dokument_proposition` (sokord="NATO", rm="2023/24")

**User:** "Hur röstade SD om budgeten?"  
→ `riksdag_voteringar` (sokord="budget", parti="sd")

**User:** "Ledamöter från Stockholms län"  
→ `riksdag_ledamoter_valkrets` (valkrets="Stockholms län")

**User:** "SOU om migration senaste året"  
→ `riksdag_dokument_sou` (sokord="migration", from_datum="2024-01-01")

### Namespace Structure
```
tools/politik/
├── dokument/                    ← top-level + sub-tools
│   ├── proposition
│   ├── motion
│   ├── betankande
│   ├── interpellation
│   ├── fraga
│   ├── protokoll
│   ├── sou
│   ├── ds
│   ├── dir
│   ├── rskr
│   ├── eu
│   └── rir
├── voteringar/                  ← top-level + resultat
│   └── resultat
├── ledamoter/                   ← top-level + parti/valkrets
│   ├── parti
│   └── valkrets
├── anforanden/                  ← top-level + debatt/fragestund
│   ├── debatt
│   └── fragestund
└── status/                      ← dokumentstatus
```

---

## Notes

- All tools are registered via `langgraph-bigtool` with namespace-aware selection.
- Tool outputs are ingested as `TOOL_OUTPUT` documents for citations.
