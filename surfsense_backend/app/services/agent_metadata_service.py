from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_prompt_service import (
    get_global_prompt_overrides,
    upsert_global_prompt_overrides,
)

_AGENT_METADATA_OVERRIDE_PREFIX = "agent.metadata."

_DEFAULT_AGENT_METADATA: tuple[dict[str, Any], ...] = (
    {
        "agent_id": "åtgärd",
        "label": "Åtgärd",
        "description": "Realtime actions som vader, resor och verktygskorningar.",
        "keywords": [
            "väder",
            "vädret",
            "vader",
            "vadret",
            "smhi",
            "resa",
            "tåg",
            "tag",
            "avgår",
            "avgar",
            "tidtabell",
            "trafik",
            "rutt",
            "karta",
            "kartbild",
            "geoapify",
            "adress",
        ],
        "namespace": ["agents", "action"],
        "prompt_key": "action",
        "routes": ["skapande"],
        "flow_tools": [
            {"tool_id": "search_knowledge_base", "label": "Kunskapsbas"},
            {"tool_id": "link_preview", "label": "Länk Förhandsgranskning"},
            {"tool_id": "scrape_webpage", "label": "Scrape Webbsida"},
        ],
        "main_identifier": "Atgardsagent",
        "core_activity": "Kor realtidsverktyg for vader, resor och generella actions",
        "unique_scope": "Generell action-agent for verktygskorningar som inte tillhor en specialiserad agent",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["statistik", "bolag", "riksdagen"],
    },
    {
        "agent_id": "väder",
        "label": "Väder",
        "description": "SMHI vaderprognoser, snodata, vaderanalyser och meteorologiska observationer.",
        "keywords": [
            "väder",
            "vädret",
            "smhi",
            "vader",
            "vadret",
            "temperatur",
            "regn",
            "snö",
            "sno",
            "vind",
            "prognos",
            "nederbörd",
            "nederbord",
            "observation",
        ],
        "namespace": ["agents", "weather"],
        "prompt_key": "action",
        "routes": ["väder-och-klimat"],
        "flow_tools": [
            {"tool_id": "smhi_weather", "label": "SMHI Prognos"},
            {"tool_id": "smhi_vaderprognoser_metfcst", "label": "SMHI MetFcst"},
            {"tool_id": "smhi_vaderprognoser_snow1g", "label": "SMHI Snö"},
            {"tool_id": "smhi_vaderanalyser_mesan2g", "label": "SMHI MESAN"},
            {"tool_id": "smhi_vaderobservationer_metobs", "label": "SMHI MetObs"},
        ],
        "main_identifier": "Vaderagent",
        "core_activity": "Hamtar vaderprognoser och observationer fran SMHI",
        "unique_scope": "Enbart vader, temperatur, nederbord, vind – inte hydrologi, hav eller brandrisk",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["olycka", "ko", "vagarbete", "statistik"],
    },
    {
        "agent_id": "väder-vatten",
        "label": "Hydrologi & Hav",
        "description": "SMHI hydrologiska och oceanografiska data – vattenstand, vattenföring, havsniva.",
        "keywords": [
            "hydrologi",
            "vattenstånd",
            "vattenstand",
            "vattenföring",
            "vattenforing",
            "grundvatten",
            "oceanografi",
            "hav",
            "havsnivå",
            "havsniva",
            "våghöjd",
            "vaghojd",
            "havstemperatur",
            "sjö",
            "sjo",
        ],
        "namespace": ["agents", "weather", "hydro"],
        "prompt_key": "action",
        "routes": ["väder-och-klimat"],
        "flow_tools": [
            {"tool_id": "smhi_hydrologi_hydroobs", "label": "SMHI HydroObs"},
            {"tool_id": "smhi_hydrologi_pthbv", "label": "SMHI PTHBV"},
            {"tool_id": "smhi_oceanografi_ocobs", "label": "SMHI Oceanografi"},
        ],
        "main_identifier": "VattenAgent",
        "core_activity": "Hamtar hydrologiska och oceanografiska data fran SMHI",
        "unique_scope": "Enbart vatten- och havsdata fran SMHI",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["olycka", "ko", "vagarbete", "statistik", "trafik"],
    },
    {
        "agent_id": "väder-risk",
        "label": "Brandrisk & Sol",
        "description": "SMHI brandrisk (FWI-index) och solstralning (UV, irradians, PAR).",
        "keywords": [
            "brandrisk",
            "eldningsförbud",
            "eldningsforbud",
            "fwi",
            "brand",
            "skogsbrand",
            "solstrålning",
            "solstralning",
            "uv",
            "uv-index",
            "irradians",
            "sol",
            "solenergi",
            "par",
        ],
        "namespace": ["agents", "weather", "risk"],
        "prompt_key": "action",
        "routes": ["väder-och-klimat"],
        "flow_tools": [
            {"tool_id": "smhi_brandrisk_fwif", "label": "SMHI Brandrisk FWIF"},
            {"tool_id": "smhi_brandrisk_fwia", "label": "SMHI Brandrisk FWIA"},
            {"tool_id": "smhi_solstralning_strang", "label": "SMHI Solstrålning"},
        ],
        "main_identifier": "RiskAgent",
        "core_activity": "Hamtar brandrisk och solstralning fran SMHI",
        "unique_scope": "Enbart brandrisk- och solstralningsdata fran SMHI",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["olycka", "ko", "vagarbete", "statistik", "trafik"],
    },
    {
        "agent_id": "kartor",
        "label": "Kartor",
        "description": "Skapa statiska kartbilder och markorer.",
        "keywords": [
            "karta",
            "kartor",
            "kartbild",
            "map",
            "geoapify",
            "adress",
            "plats",
            "koordinat",
            "vägarbete",
            "vagarbete",
            "väg",
            "vag",
            "rutt",
        ],
        "namespace": ["agents", "kartor"],
        "prompt_key": "kartor",
        "routes": ["skapande"],
        "flow_tools": [
            {"tool_id": "geoapify_static_map", "label": "Statisk Karta"},
        ],
        "main_identifier": "Kartagent",
        "core_activity": "Skapar statiska kartbilder med markorer och rutter via Geoapify",
        "unique_scope": "Enbart kartgenerering och geocoding, inte navigering eller reseplanering",
        "geographic_scope": "Globalt med fokus pa Sverige",
        "excludes": ["trafik", "vader", "statistik"],
    },
    {
        "agent_id": "statistik",
        "label": "Statistik",
        "description": "SCB och officiell svensk statistik samt Kolada kommundata.",
        "keywords": [
            "statistik",
            "scb",
            "kolada",
            "skolverket statistik",
            "salsa",
            "nyckeltal",
            "kommun",
            "kommundata",
            "befolkning",
            "kpi",
            "äldreomsorg",
            "aldreomsorg",
            "hemtjänst",
            "hemtjanst",
            "behörighet",
            "behorighet",
            "skattesats",
        ],
        "namespace": ["agents", "statistics"],
        "prompt_key": "statistics",
        "routes": ["ekonomi-och-skatter"],
        "flow_tools": [
            {"tool_id": "scb_befolkning", "label": "SCB Befolkning"},
            {"tool_id": "scb_arbetsmarknad", "label": "SCB Arbetsmarknad"},
            {"tool_id": "scb_boende_byggande", "label": "SCB Boende"},
            {"tool_id": "scb_priser_konsumtion", "label": "SCB Priser"},
            {"tool_id": "scb_utbildning", "label": "SCB Utbildning"},
            {"tool_id": "kolada_municipality", "label": "Kolada Kommun"},
        ],
        "main_identifier": "Statistikagent",
        "core_activity": "Hamtar officiell svensk statistik fran SCB och Kolada kommundata",
        "unique_scope": "Enbart officiell statistik och kommunala nyckeltal, inte realtidsdata",
        "geographic_scope": "Sverige, rikstackande och kommunalt",
        "excludes": ["vader", "trafik", "bolag", "realtid"],
    },
    {
        "agent_id": "media",
        "label": "Media",
        "description": "Podcast, bild och media-generering.",
        "keywords": ["podcast", "podd", "media", "bild", "ljud"],
        "namespace": ["agents", "media"],
        "prompt_key": "media",
        "routes": ["skapande"],
        "flow_tools": [
            {"tool_id": "generate_podcast", "label": "Podcast"},
            {"tool_id": "display_image", "label": "Visa Bild"},
        ],
        "main_identifier": "Mediaagent",
        "core_activity": "Genererar podcast, bilder och annat medieinnehall",
        "unique_scope": "Enbart mediagenerering som podcast och bildvisning",
        "geographic_scope": "",
        "excludes": ["statistik", "trafik", "vader", "kod"],
    },
    {
        "agent_id": "kunskap",
        "label": "Kunskap",
        "description": "SurfSense, Tavily och generell kunskap.",
        "keywords": [
            "kunskap",
            "surfsense",
            "tavily",
            "docs",
            "note",
            "skolverket",
            "läroplan",
            "laroplan",
            "kursplan",
            "ämnesplan",
            "amnesplan",
            "skolenhet",
            "komvux",
            "vuxenutbildning",
        ],
        "namespace": ["agents", "knowledge"],
        "prompt_key": "knowledge",
        "routes": ["kunskap"],
        "flow_tools": [
            {"tool_id": "search_surfsense_docs", "label": "SurfSense Docs"},
            {"tool_id": "save_memory", "label": "Spara Minne"},
            {"tool_id": "recall_memory", "label": "Hämta Minne"},
            {"tool_id": "tavily_search", "label": "Tavily Sök"},
        ],
        "main_identifier": "Kunskapsagent",
        "core_activity": "Soker i interna dokument, minnen och extern webbkunskap via SurfSense och Tavily",
        "unique_scope": "Generell kunskapssokning i egna dokument och extern webb, inte specialiserade datakallor",
        "geographic_scope": "Globalt",
        "excludes": ["vader", "trafik", "statistik", "bolag"],
    },
    {
        "agent_id": "webb",
        "label": "Webb",
        "description": "Webbsokning och scraping.",
        "keywords": ["webb", "browser", "sök", "sok", "nyheter", "url"],
        "namespace": ["agents", "browser"],
        "prompt_key": "browser",
        "routes": ["kunskap"],
        "flow_tools": [
            {"tool_id": "scrape_webpage", "label": "Scrape Webbsida"},
            {"tool_id": "link_preview", "label": "Länk Förhandsgranskning"},
            {"tool_id": "public_web_search", "label": "Webbsökning"},
        ],
        "main_identifier": "Webbagent",
        "core_activity": "Soker pa webben och scrapar webbsidor for information",
        "unique_scope": "Enbart oppen webbsokning och scraping, inte interna dokument eller API-kallor",
        "geographic_scope": "Globalt",
        "excludes": ["statistik", "vader", "bolag"],
    },
    {
        "agent_id": "kod",
        "label": "Kod",
        "description": "Kalkyler och kodrelaterade uppgifter.",
        "keywords": [
            "kod",
            "beräkna",
            "berakna",
            "script",
            "python",
            "fil",
            "filer",
            "file",
            "filesystem",
            "filsystem",
            "skriv fil",
            "läs fil",
            "las fil",
            "create file",
            "read file",
            "write file",
            "sandbox",
            "docker",
            "bash",
            "terminal",
        ],
        "namespace": ["agents", "code"],
        "prompt_key": "code",
        "routes": ["skapande"],
        "flow_tools": [
            {"tool_id": "sandbox_execute", "label": "Sandbox Execute"},
            {"tool_id": "sandbox_write_file", "label": "Sandbox Write"},
            {"tool_id": "sandbox_read_file", "label": "Sandbox Read"},
            {"tool_id": "sandbox_ls", "label": "Sandbox LS"},
            {"tool_id": "sandbox_replace", "label": "Sandbox Replace"},
            {"tool_id": "sandbox_release", "label": "Sandbox Release"},
        ],
        "main_identifier": "Kodagent",
        "core_activity": "Kor Python-kod, skript och filoperationer i en sandlademiljo",
        "unique_scope": "Enbart kodexekvering och filhantering i sandbox, inte databaser eller API:er",
        "geographic_scope": "",
        "excludes": ["vader", "trafik", "statistik", "bolag"],
    },
    {
        "agent_id": "bolag",
        "label": "Bolag",
        "description": "Bolagsverket och foretagsdata (orgnr, agare, ekonomi).",
        "keywords": [
            "bolag",
            "bolagsverket",
            "företag",
            "foretag",
            "orgnr",
            "organisationsnummer",
            "styrelse",
            "firmatecknare",
            "årsredovisning",
            "arsredovisning",
            "f-skatt",
            "moms",
            "konkurs",
        ],
        "namespace": ["agents", "bolag"],
        "prompt_key": "bolag",
        "routes": ["näringsliv-och-bolag"],
        "flow_tools": [
            {"tool_id": "bolagsverket_sok_orgnr", "label": "Sök Orgnr"},
            {"tool_id": "bolagsverket_info_grunddata", "label": "Grunddata"},
            {"tool_id": "bolagsverket_funktionarer", "label": "Funktionärer"},
            {"tool_id": "bolagsverket_registrering", "label": "Registrering"},
            {"tool_id": "bolagsverket_dokument_lista", "label": "Dokumentlista"},
        ],
        "main_identifier": "Bolagsagent",
        "core_activity": "Hamtar foretagsinformation fran Bolagsverket som orgnr, styrelse och ekonomi",
        "unique_scope": "Enbart svenska foretagsuppgifter via Bolagsverket, inte statistik eller trafik",
        "geographic_scope": "Sverige",
        "excludes": ["vader", "trafik", "statistik", "riksdagen"],
    },
    {
        "agent_id": "trafik-tag",
        "label": "Tågtrafik",
        "description": "Taginformation – forseningar, tidtabeller, stationer, installda tag, resplanering.",
        "keywords": [
            "tåg",
            "tag",
            "järnväg",
            "jarnvag",
            "tågförsening",
            "tagforsening",
            "försening",
            "forsening",
            "tidtabell",
            "avgång",
            "avgang",
            "ankomst",
            "station",
            "inställd",
            "installd",
            "resplanering",
            "kollektivtrafik",
            "buss",
            "pendeltåg",
            "pendeltag",
            "sj",
        ],
        "namespace": ["agents", "trafik", "tag"],
        "prompt_key": "trafik",
        "routes": ["trafik-och-transport"],
        "flow_tools": [
            {"tool_id": "trafikverket_tag_forseningar", "label": "Tågförseningar"},
            {"tool_id": "trafikverket_tag_tidtabell", "label": "Tidtabell"},
            {"tool_id": "trafikverket_tag_stationer", "label": "Stationer"},
            {"tool_id": "trafikverket_tag_installda", "label": "Inställda"},
            {"tool_id": "trafikverket_prognos_tag", "label": "Tågprognos"},
            {"tool_id": "trafiklab_route", "label": "Resplanerare"},
        ],
        "main_identifier": "TågAgent",
        "core_activity": "Hamtar taginformation och resplanering fran Trafikverket och Trafiklab",
        "unique_scope": "Enbart tagtrafik, tidtabeller och resplanering",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["vader", "temperatur", "statistik", "bolag"],
    },
    {
        "agent_id": "trafik-vag",
        "label": "Vägtrafik",
        "description": "Vagtrafik – storningar, olyckor, koer, vagarbeten, kameror, vagstatus, prognoser.",
        "keywords": [
            "trafikverket",
            "trafik",
            "väg",
            "vag",
            "störning",
            "storning",
            "olycka",
            "kö",
            "ko",
            "köer",
            "koer",
            "vägarbete",
            "vagarbete",
            "kamera",
            "trafikkamera",
            "hastighet",
            "avstängning",
            "avstangning",
            "restid",
            "trafikprognos",
            "framkomlighet",
        ],
        "namespace": ["agents", "trafik", "vag"],
        "prompt_key": "trafik",
        "routes": ["trafik-och-transport"],
        "flow_tools": [
            {"tool_id": "trafikverket_trafikinfo_storningar", "label": "Störningar"},
            {"tool_id": "trafikverket_trafikinfo_olyckor", "label": "Olyckor"},
            {"tool_id": "trafikverket_trafikinfo_koer", "label": "Köer"},
            {"tool_id": "trafikverket_trafikinfo_vagarbeten", "label": "Vägarbeten"},
            {"tool_id": "trafikverket_vag_status", "label": "Vägstatus"},
            {"tool_id": "trafikverket_vag_underhall", "label": "Underhåll"},
            {"tool_id": "trafikverket_vag_hastighet", "label": "Hastighet"},
            {"tool_id": "trafikverket_vag_avstangningar", "label": "Avstängningar"},
            {"tool_id": "trafikverket_kameror_lista", "label": "Kameror"},
            {"tool_id": "trafikverket_kameror_snapshot", "label": "Snapshot"},
            {"tool_id": "trafikverket_kameror_status", "label": "Kamerastatus"},
            {"tool_id": "trafikverket_prognos_trafik", "label": "Trafikprognos"},
            {"tool_id": "trafikverket_prognos_vag", "label": "Vägprognos"},
        ],
        "main_identifier": "VägAgent",
        "core_activity": "Hamtar vagtrafikdata som storningar, olyckor, koer, kameror och vagstatus",
        "unique_scope": "Enbart vagtrafik och trafikläge, inte tagtrafik eller väderprognoser",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["vader", "temperatur", "statistik", "bolag"],
    },
    {
        "agent_id": "trafik-vagvader",
        "label": "Vägväder",
        "description": "Trafikverkets vagvader – halka, isrisk, vind pa broar, temperatur vid vagnatet.",
        "keywords": [
            "vägväder",
            "vagvader",
            "väglag",
            "vaglag",
            "halka",
            "isrisk",
            "is",
            "vind",
            "temperatur",
            "väderstation",
            "vaderstation",
            "mätpunkt",
            "matpunkt",
            "bro",
        ],
        "namespace": ["agents", "trafik", "vagvader"],
        "prompt_key": "trafik",
        "routes": ["trafik-och-transport"],
        "flow_tools": [
            {"tool_id": "trafikverket_vader_stationer", "label": "Väderstationer"},
            {"tool_id": "trafikverket_vader_halka", "label": "Halka"},
            {"tool_id": "trafikverket_vader_vind", "label": "Vind"},
            {"tool_id": "trafikverket_vader_temperatur", "label": "Temperatur"},
        ],
        "main_identifier": "VägväderAgent",
        "core_activity": "Hamtar vagvader, halka och vaglag fran Trafikverkets vaderstationer",
        "unique_scope": "Enbart vagvader och vaglag fran Trafikverket",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["statistik", "bolag"],
    },
    {
        "agent_id": "riksdagen-dokument",
        "label": "Riksdagen Dokument",
        "description": "Riksdagens dokument: propositioner, motioner, betankanden, SOU, Ds, interpellationer.",
        "keywords": [
            "riksdag",
            "riksdagen",
            "proposition",
            "prop",
            "motion",
            "mot",
            "betänkande",
            "betankande",
            "interpellation",
            "fråga",
            "fraga",
            "sou",
            "ds",
            "direktiv",
            "utskott",
            "lagförslag",
            "lagforslag",
            "riksdagsskrivelse",
        ],
        "namespace": ["agents", "riksdagen", "dokument"],
        "prompt_key": "riksdagen-dokument",
        "routes": ["politik-och-beslut"],
        "flow_tools": [
            {"tool_id": "riksdag_dokument", "label": "Dokument Sök"},
            {"tool_id": "riksdag_dokumentstatus", "label": "Dokumentstatus"},
        ],
        "main_identifier": "RiksdagenDokumentAgent",
        "core_activity": "Soker riksdagsdokument: propositioner, motioner, betankanden, SOU",
        "unique_scope": "Riksdagens dokumentarkiv, inte debatter eller ledamoter",
        "geographic_scope": "Sverige",
        "excludes": ["vader", "trafik", "statistik", "bolag"],
    },
    {
        "agent_id": "riksdagen-debatt",
        "label": "Riksdagen Debatt & Voteringar",
        "description": "Riksdagsdebatter, anforanden och voteringsresultat.",
        "keywords": [
            "debatt",
            "anförande",
            "anforande",
            "tal",
            "votering",
            "omröstning",
            "omrostning",
            "röstning",
            "rostning",
            "frågestund",
            "fragestund",
            "kammare",
            "röstresultat",
            "rostresultat",
        ],
        "namespace": ["agents", "riksdagen", "debatt"],
        "prompt_key": "riksdagen-debatt",
        "routes": ["politik-och-beslut"],
        "flow_tools": [
            {"tool_id": "riksdag_anforanden", "label": "Anföranden"},
            {"tool_id": "riksdag_voteringar", "label": "Voteringar"},
        ],
        "main_identifier": "RiksdagenDebattAgent",
        "core_activity": "Soker debatter, anforanden och voteringar i riksdagen",
        "unique_scope": "Riksdagens debatt- och voteringsdata, inte dokument eller ledamoter",
        "geographic_scope": "Sverige",
        "excludes": ["vader", "trafik", "statistik", "bolag"],
    },
    {
        "agent_id": "riksdagen-ledamoter",
        "label": "Riksdagen Ledamöter & Kalender",
        "description": "Riksdagsledamoter per parti och valkrets, samt riksdagens kalender.",
        "keywords": [
            "ledamot",
            "ledamöter",
            "ledamoter",
            "riksdagsledamot",
            "parti",
            "valkrets",
            "kalender",
            "schema",
            "möte",
            "mote",
            "sammanträde",
            "sammantrade",
        ],
        "namespace": ["agents", "riksdagen", "ledamoter"],
        "prompt_key": "riksdagen-ledamoter",
        "routes": ["politik-och-beslut"],
        "flow_tools": [
            {"tool_id": "riksdag_ledamoter", "label": "Ledamöter"},
            {"tool_id": "riksdag_kalender", "label": "Kalender"},
        ],
        "main_identifier": "RiksdagenLedamoterAgent",
        "core_activity": "Soker riksdagsledamoter och riksdagskalender",
        "unique_scope": "Riksdagens ledamoter och kalender, inte dokument eller debatter",
        "geographic_scope": "Sverige",
        "excludes": ["vader", "trafik", "statistik", "bolag"],
    },
    {
        "agent_id": "marknad",
        "label": "Marknad",
        "description": "Sok och jamfor annonser pa Blocket och Tradera for begagnade varor.",
        "keywords": [
            "blocket",
            "tradera",
            "köp",
            "kop",
            "köpa",
            "kopa",
            "sälj",
            "salj",
            "sälja",
            "salja",
            "begagnat",
            "annons",
            "annonser",
            "marknadsplats",
            "auktion",
            "bilar",
            "båtar",
            "batar",
            "mc",
            "motorcykel",
            "pris",
            "prisjämförelse",
            "prisjamforelse",
            "jämför",
            "jamfor",
            "kategorier",
            "regioner",
            "sök",
            "sok",
            "hitta",
        ],
        "namespace": ["agents", "marketplace"],
        "prompt_key": "agent.marketplace.system",
        "routes": ["handel-och-marknad"],
        "flow_tools": [
            {"tool_id": "marketplace_unified_search", "label": "Unified Search"},
            {"tool_id": "marketplace_blocket_search", "label": "Blocket Sök"},
            {"tool_id": "marketplace_blocket_cars", "label": "Blocket Bilar"},
            {"tool_id": "marketplace_blocket_boats", "label": "Blocket Båtar"},
            {"tool_id": "marketplace_blocket_mc", "label": "Blocket MC"},
            {"tool_id": "marketplace_tradera_search", "label": "Tradera Sök"},
            {"tool_id": "marketplace_compare_prices", "label": "Prisjämförelse"},
        ],
        "main_identifier": "Marknadsagent",
        "core_activity": "Soker och jamfor annonser pa Blocket och Tradera for begagnade varor",
        "unique_scope": "Enbart marknadsplatser for begagnade varor, inte nyproducerade eller butiker",
        "geographic_scope": "Sverige",
        "excludes": ["vader", "trafik", "statistik", "bolag"],
    },
    {
        "agent_id": "syntes",
        "label": "Syntes",
        "description": "Syntes och jamforelser av flera kallor och modeller.",
        "keywords": [
            "synthesis",
            "syntes",
            "jämför",
            "jamfor",
            "compare",
            "sammanfatta",
        ],
        "namespace": ["agents", "synthesis"],
        "prompt_key": "synthesis",
        "routes": ["jämförelse"],
        "flow_tools": [
            {"tool_id": "external_model_compare", "label": "Modelljämförelse"},
        ],
        "main_identifier": "Syntesagent",
        "core_activity": "Jamfor svar fran flera AI-modeller och sammanstaller synteser",
        "unique_scope": "Enbart korsmodell-jamforelse och syntes, inte enskild kunskapssokning",
        "geographic_scope": "",
        "excludes": ["vader", "trafik", "bolag"],
    },
)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_optional_text(value: Any) -> str | None:
    text = _normalize_text(value)
    return text or None


def _normalize_keywords(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _normalize_text_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw)
        if not text:
            continue
        lowered = text.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(text)
    return deduped


def _normalize_namespace(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for raw in values:
        text = _normalize_text(raw)
        if text:
            normalized.append(text)
    return normalized


def _normalize_routes(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw).lower()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _normalize_flow_tools(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, dict):
            continue
        tool_id = _normalize_text(raw.get("tool_id"))
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        label = _normalize_text(raw.get("label")) or tool_id
        normalized.append({"tool_id": tool_id, "label": label})
    return normalized


def normalize_agent_metadata_payload(
    payload: Mapping[str, Any],
    *,
    agent_id: str | None = None,
    default_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    default_payload = default_payload or {}
    resolved_agent_id = _normalize_text(agent_id or payload.get("agent_id")).lower()
    if not resolved_agent_id:
        resolved_agent_id = "custom"
    fallback_label = (
        _normalize_optional_text(default_payload.get("label"))
        or resolved_agent_id.replace("_", " ").title()
    )
    fallback_description = (
        _normalize_optional_text(default_payload.get("description")) or ""
    )
    fallback_keywords = _normalize_keywords(default_payload.get("keywords"))
    fallback_prompt_key = _normalize_optional_text(default_payload.get("prompt_key"))
    fallback_namespace = _normalize_namespace(default_payload.get("namespace"))
    fallback_routes = _normalize_routes(default_payload.get("routes"))
    fallback_flow_tools = _normalize_flow_tools(default_payload.get("flow_tools"))
    fallback_main_identifier = _normalize_text(default_payload.get("main_identifier"))
    fallback_core_activity = _normalize_text(default_payload.get("core_activity"))
    fallback_unique_scope = _normalize_text(default_payload.get("unique_scope"))
    fallback_geographic_scope = _normalize_text(default_payload.get("geographic_scope"))
    fallback_excludes = _normalize_text_list(default_payload.get("excludes"))
    label = _normalize_optional_text(payload.get("label")) or fallback_label
    description = (
        _normalize_optional_text(payload.get("description")) or fallback_description
    )
    keywords = _normalize_keywords(payload.get("keywords")) or fallback_keywords
    prompt_key = (
        _normalize_optional_text(payload.get("prompt_key")) or fallback_prompt_key
    )
    namespace = _normalize_namespace(payload.get("namespace")) or fallback_namespace
    routes = (
        _normalize_routes(payload.get("routes"))
        if "routes" in payload
        else fallback_routes
    )
    flow_tools = (
        _normalize_flow_tools(payload.get("flow_tools"))
        if "flow_tools" in payload
        else fallback_flow_tools
    )
    main_identifier = (
        _normalize_text(payload.get("main_identifier")) or fallback_main_identifier
    )
    core_activity = (
        _normalize_text(payload.get("core_activity")) or fallback_core_activity
    )
    unique_scope = _normalize_text(payload.get("unique_scope")) or fallback_unique_scope
    geographic_scope = (
        _normalize_text(payload.get("geographic_scope")) or fallback_geographic_scope
    )
    excludes = _normalize_text_list(payload.get("excludes")) or fallback_excludes
    # Preserve primary_namespaces for NEXUS namespace-based tool filtering
    primary_namespaces = payload.get("primary_namespaces") or default_payload.get(
        "primary_namespaces", []
    )
    return {
        "agent_id": resolved_agent_id,
        "label": label,
        "description": description,
        "keywords": keywords,
        "prompt_key": prompt_key,
        "namespace": namespace,
        "routes": routes,
        "flow_tools": flow_tools,
        "main_identifier": main_identifier,
        "core_activity": core_activity,
        "unique_scope": unique_scope,
        "geographic_scope": geographic_scope,
        "excludes": excludes,
        "primary_namespaces": primary_namespaces,
    }


def get_default_agent_metadata() -> dict[str, dict[str, Any]]:
    defaults: dict[str, dict[str, Any]] = {}
    for payload in _DEFAULT_AGENT_METADATA:
        normalized = normalize_agent_metadata_payload(
            payload,
            agent_id=payload.get("agent_id"),
            default_payload=payload,
        )
        defaults[normalized["agent_id"]] = normalized
    return defaults


def _serialize_override_payload(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)


def agent_metadata_payload_equal(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    left_norm = normalize_agent_metadata_payload(left, agent_id=left.get("agent_id"))
    right_norm = normalize_agent_metadata_payload(right, agent_id=right.get("agent_id"))
    return left_norm == right_norm


async def get_global_agent_metadata_overrides(
    session: AsyncSession,
) -> dict[str, dict[str, Any]]:
    prompt_overrides = await get_global_prompt_overrides(session)
    overrides: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in prompt_overrides.items():
        key = str(raw_key or "").strip()
        if not key.startswith(_AGENT_METADATA_OVERRIDE_PREFIX):
            continue
        agent_id = key[len(_AGENT_METADATA_OVERRIDE_PREFIX) :].strip().lower()
        if not agent_id:
            continue
        payload: dict[str, Any] | None = None
        text_value = str(raw_value or "").strip()
        if text_value:
            try:
                parsed = json.loads(text_value)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {"agent_id": agent_id, "description": text_value}
        if payload is None:
            continue
        overrides[agent_id] = normalize_agent_metadata_payload(
            payload,
            agent_id=agent_id,
        )
    return overrides


def _registry_agents_to_metadata(
    registry: Any,
) -> list[dict[str, Any]]:
    """Convert GraphRegistry agents into the old agent-metadata format.

    The old format expects: agent_id, label, description, keywords,
    prompt_key, namespace, routes, flow_tools, main_identifier, …
    """
    results: list[dict[str, Any]] = []
    for domain_id, agents in (registry.agents_by_domain or {}).items():
        for agent in agents:
            agent_id = agent.get("agent_id", "")
            if not agent_id:
                continue
            if not agent.get("enabled", True):
                continue
            raw_ns = agent.get("primary_namespaces") or []
            namespace = raw_ns[0] if raw_ns else ["agents", agent_id]
            # Build flow_tools from registry tools_by_agent
            tools = (registry.tools_by_agent or {}).get(agent_id, [])
            flow_tools = [
                {"tool_id": t.get("tool_id", ""), "label": t.get("label", "")}
                for t in tools
                if t.get("tool_id")
            ]
            results.append(
                {
                    "agent_id": agent_id,
                    "label": agent.get("label", agent_id),
                    "description": agent.get("description", ""),
                    "keywords": agent.get("keywords", []),
                    "prompt_key": agent.get("prompt_key", ""),
                    "namespace": namespace,
                    "routes": [domain_id] if domain_id else [],
                    "flow_tools": flow_tools,
                    "main_identifier": agent.get("main_identifier", ""),
                    "core_activity": agent.get("core_activity", ""),
                    "unique_scope": agent.get("unique_scope", ""),
                    "geographic_scope": agent.get("geographic_scope", ""),
                    "excludes": agent.get("excludes", []),
                    "primary_namespaces": raw_ns,
                }
            )
    return results


async def get_effective_agent_metadata(session: AsyncSession) -> list[dict[str, Any]]:
    """Return merged agent metadata.

    Tries the new GraphRegistry first (agents from domain hierarchy).
    Falls back to old hardcoded defaults + prompt-based overrides if the
    registry is empty or unavailable.
    """
    try:
        from app.services.graph_registry_service import load_graph_registry

        registry = await load_graph_registry(session)
        if registry.agents_by_domain:
            return _registry_agents_to_metadata(registry)
    except Exception:
        pass

    # Fallback: old hardcoded system
    defaults = get_default_agent_metadata()
    overrides = await get_global_agent_metadata_overrides(session)
    merged: dict[str, dict[str, Any]] = {}
    for agent_id, default_payload in defaults.items():
        override_payload = overrides.get(agent_id)
        if override_payload is None:
            merged[agent_id] = default_payload
            continue
        merged[agent_id] = normalize_agent_metadata_payload(
            override_payload,
            agent_id=agent_id,
            default_payload=default_payload,
        )
    for agent_id, payload in overrides.items():
        if agent_id in merged:
            continue
        merged[agent_id] = normalize_agent_metadata_payload(
            payload,
            agent_id=agent_id,
        )
    ordered_ids = [
        payload["agent_id"]
        for payload in _DEFAULT_AGENT_METADATA
        if payload.get("agent_id")
    ]
    for agent_id in sorted(merged.keys()):
        if agent_id not in ordered_ids:
            ordered_ids.append(agent_id)
    return [merged[agent_id] for agent_id in ordered_ids if agent_id in merged]


async def upsert_global_agent_metadata_overrides(
    session: AsyncSession,
    updates: Iterable[tuple[str, Mapping[str, Any] | None]],
    *,
    updated_by_id=None,
) -> None:
    # Load existing overrides so partial updates can merge with stored data
    # instead of silently wiping unmentioned fields.
    existing_overrides = await get_global_agent_metadata_overrides(session)
    defaults = get_default_agent_metadata()

    prompt_updates: list[tuple[str, str | None]] = []
    for raw_agent_id, payload in updates:
        agent_id = _normalize_text(raw_agent_id).lower()
        if not agent_id:
            continue
        key = f"{_AGENT_METADATA_OVERRIDE_PREFIX}{agent_id}"
        if payload is None:
            prompt_updates.append((key, None))
            continue
        # Build a merged base: start from hardcoded default, layer on the
        # previously stored override, then apply the incoming partial payload.
        base: dict[str, Any] = {}
        default_payload = defaults.get(agent_id) or {}
        if default_payload:
            base.update(default_payload)
        existing = existing_overrides.get(agent_id)
        if existing:
            base.update(existing)
        # Apply incoming fields on top (only keys actually present in payload)
        base.update({k: v for k, v in dict(payload).items() if v is not None})
        normalized_payload = normalize_agent_metadata_payload(
            base,
            agent_id=agent_id,
            default_payload=default_payload or None,
        )
        prompt_updates.append((key, _serialize_override_payload(normalized_payload)))
    if not prompt_updates:
        return
    await upsert_global_prompt_overrides(
        session,
        prompt_updates,
        updated_by_id=updated_by_id,
    )
