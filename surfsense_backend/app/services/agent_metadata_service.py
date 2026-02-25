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
            "vader",
            "vadret",
            "smhi",
            "resa",
            "tag",
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
        "routes": ["kunskap"],
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
        "description": "SMHI-vaderprognoser och Trafikverkets vagvaderdata for svenska orter och vagar.",
        "keywords": [
            "smhi",
            "vader",
            "temperatur",
            "regn",
            "sno",
            "vind",
            "prognos",
            "halka",
            "isrisk",
            "vaglag",
        ],
        "namespace": ["agents", "weather"],
        "prompt_key": "action",
        "routes": ["kunskap"],
        "flow_tools": [
            {"tool_id": "smhi_weather", "label": "SMHI Prognos"},
            {"tool_id": "smhi_vaderprognoser_metfcst", "label": "SMHI MetFcst"},
            {"tool_id": "smhi_vaderprognoser_snow1g", "label": "SMHI Snö"},
            {"tool_id": "smhi_vaderanalyser_mesan2g", "label": "SMHI MESAN"},
            {"tool_id": "smhi_vaderobservationer_metobs", "label": "SMHI MetObs"},
            {"tool_id": "smhi_hydrologi_hydroobs", "label": "SMHI HydroObs"},
            {"tool_id": "smhi_hydrologi_pthbv", "label": "SMHI PTHBV"},
            {"tool_id": "smhi_oceanografi_ocobs", "label": "SMHI Oceanografi"},
            {"tool_id": "smhi_brandrisk_fwif", "label": "SMHI Brandrisk FWIF"},
            {"tool_id": "smhi_brandrisk_fwia", "label": "SMHI Brandrisk FWIA"},
            {"tool_id": "smhi_solstralning_strang", "label": "SMHI Solstrålning"},
            {"tool_id": "trafikverket_vader_stationer", "label": "Trafikverket Väder Stationer"},
            {"tool_id": "trafikverket_vader_halka", "label": "Trafikverket Väder Halka"},
            {"tool_id": "trafikverket_vader_vind", "label": "Trafikverket Väder Vind"},
            {"tool_id": "trafikverket_vader_temperatur", "label": "Trafikverket Väder Temperatur"},
        ],
        "main_identifier": "Vaderagent",
        "core_activity": "Hamtar vaderprognoser och vagvaderdata fran SMHI och Trafikverket",
        "unique_scope": "Enbart vader, temperatur, nederbord, vind och vaglag – inte trafiklaget i sig",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["olycka", "ko", "vagarbete", "statistik"],
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
            "vagarbete",
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
            "aldreomsorg",
            "hemtjanst",
            "behorighet",
            "skattesats",
        ],
        "namespace": ["agents", "statistics"],
        "prompt_key": "statistics",
        "routes": ["kunskap", "jämförelse"],
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
            "laroplan",
            "kursplan",
            "amnesplan",
            "skolenhet",
            "komvux",
            "vuxenutbildning",
        ],
        "namespace": ["agents", "knowledge"],
        "prompt_key": "knowledge",
        "routes": ["kunskap", "jämförelse"],
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
        "keywords": ["webb", "browser", "sok", "nyheter", "url"],
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
            "berakna",
            "script",
            "python",
            "fil",
            "filer",
            "file",
            "filesystem",
            "filsystem",
            "skriv fil",
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
            "foretag",
            "orgnr",
            "organisationsnummer",
            "styrelse",
            "firmatecknare",
            "arsredovisning",
            "f-skatt",
            "moms",
            "konkurs",
        ],
        "namespace": ["agents", "bolag"],
        "prompt_key": "bolag",
        "routes": ["kunskap"],
        "flow_tools": [
            {"tool_id": "bolagsverket_info_basic", "label": "Företagsinfo"},
            {"tool_id": "bolagsverket_info_status", "label": "Företagsstatus"},
            {"tool_id": "bolagsverket_sok_namn", "label": "Sök Namn"},
            {"tool_id": "bolagsverket_sok_orgnr", "label": "Sök Orgnr"},
            {"tool_id": "bolagsverket_ekonomi_bokslut", "label": "Bokslut"},
        ],
        "main_identifier": "Bolagsagent",
        "core_activity": "Hamtar foretagsinformation fran Bolagsverket som orgnr, styrelse och ekonomi",
        "unique_scope": "Enbart svenska foretagsuppgifter via Bolagsverket, inte statistik eller trafik",
        "geographic_scope": "Sverige",
        "excludes": ["vader", "trafik", "statistik", "riksdagen"],
    },
    {
        "agent_id": "trafik",
        "label": "Trafik",
        "description": "Trafikverket realtidsdata (vag, tag, kameror).",
        "keywords": [
            "trafikverket",
            "trafik",
            "vag",
            "tag",
            "storning",
            "olycka",
            "ko",
            "kamera",
        ],
        "namespace": ["agents", "trafik"],
        "prompt_key": "trafik",
        "routes": ["kunskap"],
        "flow_tools": [
            {"tool_id": "trafikverket_situation", "label": "Trafikläge"},
            {"tool_id": "trafikverket_road_condition", "label": "Väglag"},
            {"tool_id": "trafikverket_camera", "label": "Kameror"},
            {"tool_id": "trafikverket_ferry", "label": "Färjor"},
            {"tool_id": "trafikverket_railway", "label": "Järnväg"},
            {"tool_id": "trafiklab_route", "label": "Resplanerare"},
        ],
        "main_identifier": "Trafikagent",
        "core_activity": "Hamtar realtids trafikdata fran Trafikverket som olyckor, koer, kameror och tagstorningar",
        "unique_scope": "Enbart trafikhändelser och realtidsläge, inte väderprognoser eller statistik",
        "geographic_scope": "Sverige, rikstackande",
        "excludes": ["vader", "temperatur", "statistik", "bolag"],
    },
    {
        "agent_id": "riksdagen",
        "label": "Riksdagen",
        "description": "Riksdagens oppna data: propositioner, motioner, voteringar, ledamoter.",
        "keywords": [
            "riksdag",
            "riksdagen",
            "proposition",
            "prop",
            "motion",
            "mot",
            "votering",
            "omrostning",
            "ledamot",
            "ledamoter",
            "betankande",
            "interpellation",
            "fraga",
            "anforande",
            "debatt",
            "kammare",
            "sou",
            "ds",
            "utskott",
            "parti",
        ],
        "namespace": ["agents", "riksdagen"],
        "prompt_key": "riksdagen",
        "routes": ["kunskap"],
        "flow_tools": [
            {"tool_id": "riksdagen_dokument_sok", "label": "Dokument Sök"},
            {"tool_id": "riksdagen_votering", "label": "Voteringar"},
            {"tool_id": "riksdagen_ledamot", "label": "Ledamöter"},
        ],
        "main_identifier": "Riksdagsagent",
        "core_activity": "Soker i riksdagens oppna data for propositioner, motioner, voteringar och ledamoter",
        "unique_scope": "Enbart riksdagens formella dokument och beslutsprocesser, inte allmanna nyheter",
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
            "kop",
            "kopa",
            "salj",
            "salja",
            "begagnat",
            "annons",
            "annonser",
            "marknadsplats",
            "auktion",
            "bilar",
            "batar",
            "mc",
            "motorcykel",
            "pris",
            "prisjamforelse",
            "jamfor",
            "kategorier",
            "regioner",
            "sok",
            "hitta",
        ],
        "namespace": ["agents", "marketplace"],
        "prompt_key": "agent.marketplace.system",
        "routes": ["kunskap"],
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
        "keywords": ["synthesis", "syntes", "jamfor", "compare", "sammanfatta"],
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
    fallback_description = _normalize_optional_text(default_payload.get("description")) or ""
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
    description = _normalize_optional_text(payload.get("description")) or fallback_description
    keywords = _normalize_keywords(payload.get("keywords")) or fallback_keywords
    prompt_key = _normalize_optional_text(payload.get("prompt_key")) or fallback_prompt_key
    namespace = _normalize_namespace(payload.get("namespace")) or fallback_namespace
    routes = _normalize_routes(payload.get("routes")) if "routes" in payload else fallback_routes
    flow_tools = (
        _normalize_flow_tools(payload.get("flow_tools"))
        if "flow_tools" in payload
        else fallback_flow_tools
    )
    main_identifier = _normalize_text(payload.get("main_identifier")) or fallback_main_identifier
    core_activity = _normalize_text(payload.get("core_activity")) or fallback_core_activity
    unique_scope = _normalize_text(payload.get("unique_scope")) or fallback_unique_scope
    geographic_scope = _normalize_text(payload.get("geographic_scope")) or fallback_geographic_scope
    excludes = _normalize_text_list(payload.get("excludes")) or fallback_excludes
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


def agent_metadata_payload_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
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
        agent_id = (
            key[len(_AGENT_METADATA_OVERRIDE_PREFIX) :]
            .strip()
            .lower()
        )
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


async def get_effective_agent_metadata(session: AsyncSession) -> list[dict[str, Any]]:
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
