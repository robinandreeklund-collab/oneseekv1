"""Constants and configuration for the supervisor agent."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import timedelta

# NOTE: Tool definition imports (SCB, Kolada, SMHI, Trafikverket, Riksdagen,
# Bolagsverket, Marketplace) are lazy-imported inside _build_agent_tool_profiles()
# to avoid circular imports via tools/__init__ → tools/registry → *_tools.
from app.agents.new_chat.tools.external_models import EXTERNAL_MODEL_SPECS

_AGENT_CACHE_TTL = timedelta(minutes=20)
_AGENT_COMBO_CACHE: dict[str, tuple[datetime, list[str]]] = {}

# Specialized agents that have their own WorkerConfig with specific primary_namespaces
# These should NOT be overridden by route_policy if explicitly selected
# This scales to 100s of APIs without needing regex patterns for each one
_SPECIALIZED_AGENTS = {
    "marknad",  # Blocket/Tradera tools
    "statistik-ekonomi",  # SCB/Kolada economic statistics
    "statistik-befolkning",  # SCB population/demographics
    "statistik-arbetsmarknad",  # SCB/Kolada labor market
    "statistik-utbildning",  # SCB/Kolada education
    "statistik-halsa",  # SCB/Kolada health & social care
    "statistik-miljo",  # SCB/Kolada environment & energy
    "statistik-fastighet",  # SCB/Kolada housing & property
    "statistik-naringsliv",  # SCB business/enterprise
    "statistik-samhalle",  # SCB/Kolada society catch-all
    "riksdagen",  # Parliament data + demokrati statistics
    "bolag",  # Company registry tools
    "trafik-tag",  # Train/rail + route planning tools
    "trafik-vag",  # Road traffic/incidents/cameras tools
    "trafik-vagvader",  # Road weather tools
    "väder",  # Weather forecast/observation tools
    "väder-vatten",  # Hydrology/oceanography tools
    "väder-risk",  # Fire risk/solar radiation tools
    "kartor",  # Map generation tools
    "skolverket-kursplaner",  # Skolverket curricula/syllabi
    "skolverket-skolenheter",  # Skolverket school units
    "skolverket-vuxenutbildning",  # Skolverket adult education
    "skolverket-referens",  # Skolverket reference data & statistics
}
# Backward compat: accept old English agent names
_COMPAT_AGENT_NAMES: dict[str, str] = {
    "action": "åtgärd",
    "weather": "väder",
    "statistics": "statistik-ekonomi",
    "knowledge": "kunskap",
    "browser": "webb",
    "code": "kod",
    "marketplace": "marknad",
    "synthesis": "syntes",
}
_COMPAT_AGENT_NAMES_REVERSE: dict[str, str] = {
    v: k for k, v in _COMPAT_AGENT_NAMES.items()
}

_AGENT_STOPWORDS = {
    "hur",
    "vad",
    "var",
    "när",
    "nar",
    "är",
    "ar",
    "och",
    "eller",
    "för",
    "for",
    "till",
    "fran",
    "från",
    "en",
    "ett",
    "i",
    "på",
    "pa",
    "av",
    "med",
    "som",
    "om",
    "den",
    "det",
    "de",
}
_EXTERNAL_MODEL_TOOL_NAMES = {spec.tool_name for spec in EXTERNAL_MODEL_SPECS}
_AGENT_EMBED_CACHE: dict[str, list[float]] = {}
AGENT_RERANK_CANDIDATES = 6
AGENT_EMBEDDING_WEIGHT = 4.0
_DYNAMIC_TOOL_QUERY_MARKERS = (
    "skolverket",
    "mcp",
    "laroplan",
    "läroplan",
    "kursplan",
    "amnesplan",
    "ämnesplan",
    "skolenhet",
    "vuxenutbildning",
    "komvux",
    "syllabus",
    "curriculum",
    "blocket",
    "tradera",
    "begagnat",
    "annons",
    "marknadsplats",
)

_LIVE_ROUTING_PHASE_ORDER = {
    "shadow": 0,
    "tool_gate": 1,
    "agent_auto": 2,
    "adaptive": 3,
    "intent_finetune": 4,
}


def _normalize_live_routing_phase(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _LIVE_ROUTING_PHASE_ORDER:
        return normalized
    return "shadow"


def _live_phase_enabled(config: dict[str, Any], minimum_phase: str) -> bool:
    enabled = bool(config.get("enabled", False))
    if not enabled:
        return False
    current_phase = _normalize_live_routing_phase(config.get("phase"))
    return _LIVE_ROUTING_PHASE_ORDER.get(
        current_phase, 0
    ) >= _LIVE_ROUTING_PHASE_ORDER.get(minimum_phase, 0)


@dataclass(frozen=True)
class AgentToolProfile:
    tool_id: str
    category: str
    description: str
    keywords: tuple[str, ...]


def _build_agent_tool_profiles() -> dict[str, list[AgentToolProfile]]:
    # Lazy imports to avoid circular dependency:
    # supervisor_constants → *_tools → tools/__init__ → tools/registry → *_tools
    from app.agents.new_chat.kolada_tools import KOLADA_TOOL_DEFINITIONS
    from app.agents.new_chat.marketplace_tools import MARKETPLACE_TOOL_DEFINITIONS
    from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
    from app.agents.new_chat.skolverket_tools import SKOLVERKET_TOOL_DEFINITIONS
    from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.smhi import SMHI_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS

    profiles: dict[str, list[AgentToolProfile]] = {
        "väder": [],
        "väder-vatten": [],
        "väder-risk": [],
        "trafik-tag": [],
        "trafik-vag": [],
        "trafik-vagvader": [],
        "statistik-ekonomi": [],
        "statistik-befolkning": [],
        "statistik-arbetsmarknad": [],
        "statistik-utbildning": [],
        "statistik-halsa": [],
        "statistik-miljo": [],
        "statistik-fastighet": [],
        "statistik-naringsliv": [],
        "statistik-samhalle": [],
        "riksdagen": [],
        "bolag": [],
        "marknad": [],
        "skolverket-kursplaner": [],
        "skolverket-skolenheter": [],
        "skolverket-vuxenutbildning": [],
        "skolverket-referens": [],
    }
    # SMHI: split by category → sub-agent
    _smhi_agent_by_category = {
        "smhi_vaderprognoser": "väder",
        "smhi_vaderanalyser": "väder",
        "smhi_vaderobservationer": "väder",
        "smhi_hydrologi": "väder-vatten",
        "smhi_oceanografi": "väder-vatten",
        "smhi_brandrisk": "väder-risk",
        "smhi_solstralning": "väder-risk",
    }
    for definition in SMHI_TOOL_DEFINITIONS:
        category = str(getattr(definition, "category", ""))
        sub_agent = _smhi_agent_by_category.get(category, "väder")
        profiles[sub_agent].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=category,
                description=str(getattr(definition, "description", "")),
                keywords=tuple(
                    str(item) for item in list(getattr(definition, "keywords", []))
                ),
            )
        )
    # Trafikverket: split by category → sub-agent
    _trafik_agent_by_category = {
        "trafikverket_tag": "trafik-tag",
        "trafikverket_trafikinfo": "trafik-vag",
        "trafikverket_vag": "trafik-vag",
        "trafikverket_kameror": "trafik-vag",
        "trafikverket_prognos": "trafik-vag",
        "trafikverket_vader": "trafik-vagvader",
    }
    _trafik_tool_override = {
        "trafikverket_prognos_tag": "trafik-tag",
    }
    for definition in TRAFIKVERKET_TOOL_DEFINITIONS:
        tool_id = str(getattr(definition, "tool_id", ""))
        category = str(getattr(definition, "category", ""))
        sub_agent = _trafik_tool_override.get(
            tool_id, _trafik_agent_by_category.get(category, "trafik-vag")
        )
        profiles[sub_agent].append(
            AgentToolProfile(
                tool_id=tool_id,
                category=category,
                description=str(getattr(definition, "description", "")),
                keywords=tuple(
                    str(item) for item in list(getattr(definition, "keywords", []))
                ),
            )
        )
    # SCB: split by tool_id prefix → sub-agent
    _scb_agent_by_prefix = {
        "scb_befolkning": "statistik-befolkning",
        "scb_arbetsmarknad": "statistik-arbetsmarknad",
        "scb_utbildning": "statistik-utbildning",
        "scb_halsa": "statistik-halsa",
        "scb_socialtjanst": "statistik-halsa",
        "scb_levnadsforhallanden": "statistik-halsa",
        "scb_miljo": "statistik-miljo",
        "scb_energi": "statistik-miljo",
        "scb_boende": "statistik-fastighet",
        "scb_naringsverksamhet": "statistik-naringsliv",
        "scb_naringsliv": "statistik-naringsliv",
        "scb_nationalrakenskaper": "statistik-ekonomi",
        "scb_priser": "statistik-ekonomi",
        "scb_finansmarknad": "statistik-ekonomi",
        "scb_offentlig": "statistik-ekonomi",
        "scb_hushall": "statistik-ekonomi",
        "scb_handel": "statistik-ekonomi",
        "scb_transporter": "statistik-samhalle",
        "scb_demokrati": "riksdagen",
        "scb_kultur": "statistik-samhalle",
        "scb_jordbruk": "statistik-samhalle",
        "scb_amnesovergripande": "statistik-samhalle",
    }
    for definition in SCB_TOOL_DEFINITIONS:
        tool_id = str(getattr(definition, "tool_id", ""))
        sub_agent = "statistik-samhalle"  # default
        for prefix, agent in _scb_agent_by_prefix.items():
            if tool_id.startswith(prefix):
                sub_agent = agent
                break
        profiles[sub_agent].append(
            AgentToolProfile(
                tool_id=tool_id,
                category=str(getattr(definition, "base_path", "statistik")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(
                    str(item) for item in list(getattr(definition, "keywords", []))
                ),
            )
        )
    # Kolada: split by tool_id prefix → sub-agent
    _kolada_agent_by_prefix = {
        "kolada_aldreomsorg": "statistik-halsa",
        "kolada_lss": "statistik-halsa",
        "kolada_ifo": "statistik-halsa",
        "kolada_barn_unga": "statistik-halsa",
        "kolada_halsa": "statistik-halsa",
        "kolada_forskola": "statistik-utbildning",
        "kolada_grundskola": "statistik-utbildning",
        "kolada_gymnasieskola": "statistik-utbildning",
        "kolada_ekonomi": "statistik-ekonomi",
        "kolada_miljo": "statistik-miljo",
        "kolada_boende": "statistik-fastighet",
        "kolada_arbetsmarknad": "statistik-arbetsmarknad",
        "kolada_demokrati": "riksdagen",
        "kolada_kultur": "statistik-samhalle",
        "kolada_sammanfattning": "statistik-samhalle",
    }
    for definition in KOLADA_TOOL_DEFINITIONS:
        tool_id = str(getattr(definition, "tool_id", ""))
        sub_agent = "statistik-samhalle"  # default
        for prefix, agent in _kolada_agent_by_prefix.items():
            if tool_id.startswith(prefix):
                sub_agent = agent
                break
        profiles[sub_agent].append(
            AgentToolProfile(
                tool_id=tool_id,
                category=str(getattr(definition, "category", "kolada")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(
                    str(item) for item in list(getattr(definition, "keywords", []))
                ),
            )
        )
    for definition in RIKSDAGEN_TOOL_DEFINITIONS:
        profiles["riksdagen"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "riksdagen")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(
                    str(item) for item in list(getattr(definition, "keywords", []))
                ),
            )
        )
    for definition in BOLAGSVERKET_TOOL_DEFINITIONS:
        profiles["bolag"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "bolag")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(
                    str(item) for item in list(getattr(definition, "keywords", []))
                ),
            )
        )
    for definition in MARKETPLACE_TOOL_DEFINITIONS:
        profiles["marknad"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "marknad")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(
                    str(item) for item in list(getattr(definition, "keywords", []))
                ),
            )
        )
    # Skolverket: split by tool_id → sub-agent
    _skolverket_agent_by_tool = {
        "search_subjects": "skolverket-kursplaner",
        "get_subject_details": "skolverket-kursplaner",
        "get_subject_versions": "skolverket-kursplaner",
        "search_courses": "skolverket-kursplaner",
        "get_course_details": "skolverket-kursplaner",
        "get_course_versions": "skolverket-kursplaner",
        "search_programs": "skolverket-kursplaner",
        "get_program_details": "skolverket-kursplaner",
        "get_program_versions": "skolverket-kursplaner",
        "get_programs_v4": "skolverket-kursplaner",
        "search_curriculums": "skolverket-kursplaner",
        "get_curriculum_details": "skolverket-kursplaner",
        "get_curriculum_versions": "skolverket-kursplaner",
        "search_school_units": "skolverket-skolenheter",
        "search_school_units_v4": "skolverket-skolenheter",
        "get_school_unit_details": "skolverket-skolenheter",
        "search_school_units_by_name": "skolverket-skolenheter",
        "get_school_units_by_status": "skolverket-skolenheter",
        "get_school_unit_education_events": "skolverket-skolenheter",
        "get_school_unit_documents": "skolverket-skolenheter",
        "get_school_unit_statistics": "skolverket-skolenheter",
        "search_adult_education": "skolverket-vuxenutbildning",
        "get_adult_education_details": "skolverket-vuxenutbildning",
        "filter_adult_education_by_distance": "skolverket-vuxenutbildning",
        "filter_adult_education_by_pace": "skolverket-vuxenutbildning",
        "count_adult_education_events": "skolverket-vuxenutbildning",
        "get_adult_education_areas_v4": "skolverket-vuxenutbildning",
        "search_education_events": "skolverket-vuxenutbildning",
        "count_education_events": "skolverket-vuxenutbildning",
        "get_geographical_areas_v4": "skolverket-vuxenutbildning",
        "get_education_areas": "skolverket-vuxenutbildning",
        "get_directions": "skolverket-vuxenutbildning",
    }
    for definition in SKOLVERKET_TOOL_DEFINITIONS:
        tool_id = str(getattr(definition, "tool_id", ""))
        sub_agent = _skolverket_agent_by_tool.get(tool_id, "skolverket-referens")
        profiles[sub_agent].append(
            AgentToolProfile(
                tool_id=tool_id,
                category=str(getattr(definition, "category", "skolverket")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(
                    str(item) for item in list(getattr(definition, "keywords", []))
                ),
            )
        )
    return profiles


_AGENT_TOOL_PROFILES = _build_agent_tool_profiles()
_AGENT_TOOL_PROFILE_BY_ID: dict[str, AgentToolProfile] = {
    profile.tool_id: profile
    for profiles in _AGENT_TOOL_PROFILES.values()
    for profile in profiles
    if profile.tool_id
}

# Message pruning constants for progressive context management
MESSAGE_PRUNING_THRESHOLD = 20  # Start pruning when total messages exceed this
TOOL_MSG_THRESHOLD = 8  # Trigger aggressive pruning when tool messages exceed this
KEEP_TOOL_MSG_COUNT = 6  # Number of recent tool message exchanges to preserve
TOOL_CONTEXT_MAX_CHARS = 1200
TOOL_CONTEXT_MAX_ITEMS = 5
_CONTEXT_COMPACTION_MIN_MESSAGES = 16
_CONTEXT_COMPACTION_DEFAULT_TRIGGER_RATIO = 0.65
_CONTEXT_COMPACTION_DEFAULT_SUMMARY_MAX_CHARS = 1600
_CONTEXT_COMPACTION_DEFAULT_STEP_KEEP = 8
TOOL_CONTEXT_DROP_KEYS = {
    "raw",
    "data",
    "entries",
    "matching_entries",
    "results",
    "content",
    "chunks",
    "documents",
    "rows",
    "timeSeries",
    "origin_lookup",
    "destination_lookup",
    "timetable",
}
_LOOP_GUARD_TOOL_NAMES = {
    "retrieve_agents",
    "reflect_on_progress",
    "write_todos",
}
_LOOP_GUARD_MAX_CONSECUTIVE = 4  # Was 12 — unreachable given _MAX_AGENT_HOPS_PER_TURN=3
_MAX_AGENT_HOPS_PER_TURN = int(os.environ.get("MAX_AGENT_HOPS", "3"))
# P1 loop-fix: hard cap on total meaningful steps across the entire flow.
# At this threshold the flow is forced to synthesis regardless of critic decision.
MAX_TOTAL_STEPS = int(os.environ.get("MAX_TOTAL_STEPS", "8"))
_SANDBOX_CODE_TOOL_IDS = (
    "sandbox_write_file",
    "sandbox_read_file",
    "sandbox_ls",
    "sandbox_replace",
    "sandbox_execute",
    "sandbox_release",
)
_AGENT_NAME_ALIAS_MAP = {
    # Weather → väder
    "weather": "väder",
    "weather_agent": "väder",
    "smhi": "väder",
    "smhi_agent": "väder",
    "vader": "väder",
    # Traffic → trafik sub-agents
    "traffic_information": "trafik-vag",
    "traffic_info": "trafik-vag",
    "traffic_agent": "trafik-vag",
    "road_works_planner": "trafik-vag",
    "roadworks_planner": "trafik-vag",
    "road_work_planner": "trafik-vag",
    "roadworks": "trafik-vag",
    "trafik": "trafik-vag",
    "train": "trafik-tag",
    "train_agent": "trafik-tag",
    "rail": "trafik-tag",
    # Statistics → statistik-ekonomi (default for backward compat)
    "municipality_agent": "statistik-ekonomi",
    "statistic_agent": "statistik-ekonomi",
    "statistics_agent": "statistik-ekonomi",
    "statistics": "statistik-ekonomi",
    "statistik": "statistik-ekonomi",
    # Maps
    "map_agent": "kartor",
    "maps_agent": "kartor",
    # Parliament
    "parliament_agent": "riksdagen",
    # Company
    "company_agent": "bolag",
    # Code → kod
    "code_agent": "kod",
    "code": "kod",
    # Marketplace → marknad
    "marketplace_agent": "marknad",
    "market_agent": "marknad",
    "blocket_agent": "marknad",
    "tradera_agent": "marknad",
    "marketplace": "marknad",
    # Knowledge → kunskap
    "knowledge": "kunskap",
    "knowledge_agent": "kunskap",
    # Browser → webb
    "browser": "webb",
    "browser_agent": "webb",
    # Synthesis → syntes
    "synthesis": "syntes",
    "synthesis_agent": "syntes",
    # Action → åtgärd (legacy)
    "action": "åtgärd",
    "action_agent": "åtgärd",
    # Skolverket → sub-agents
    "skolverket": "skolverket-kursplaner",
    "skolverket_agent": "skolverket-kursplaner",
    "skolverket_kursplaner": "skolverket-kursplaner",
    "skolverket_skolenheter": "skolverket-skolenheter",
    "skolverket_vuxenutbildning": "skolverket-vuxenutbildning",
    "skolverket_referens": "skolverket-referens",
}

_TRAFFIC_INTENT_RE = re.compile(
    r"\b("
    r"trafikverket|trafikinfo|trafik|"
    r"olycka|storing|storning|störning|"
    r"koer|köer|ko|kö|"
    r"vagarbete|vägarbete|avstangning|avstängning|omledning|framkomlighet|"
    r"tag|tåg|jarnvag|järnväg|"
    r"kamera|kameror|"
    r"vaglag|väglag|hastighet|"
    r"e\d+|rv\s?\d+|riksvag|riksväg|vag\s?\d+|väg\s?\d+"
    r")\b",
    re.IGNORECASE,
)
_TRAFFIC_STRICT_INTENT_RE = re.compile(
    r"\b("
    r"trafikverket|"
    r"olycka|storing|storning|störning|"
    r"koer|köer|ko|kö|"
    r"vagarbete|vägarbete|avstangning|avstängning|omledning|framkomlighet|"
    r"kamera|kameror|"
    r"vaglag|väglag|hastighet|"
    r"e\d+|rv\s?\d+|riksvag|riksväg|vag\s?\d+|väg\s?\d+"
    r")\b",
    re.IGNORECASE,
)
_TRAFFIC_INCIDENT_STRICT_RE = re.compile(
    r"\b("
    r"trafikverket|"
    r"olycka|storing|storning|störning|"
    r"koer|köer|ko|kö|"
    r"vagarbete|vägarbete|avstangning|avstängning|omledning|framkomlighet|"
    r"kamera|kameror|"
    r"tagforsening|tågförsening|forsening|försening|installd|inställd|"
    r"trafikinfo"
    r")\b",
    re.IGNORECASE,
)
_WEATHER_INTENT_RE = re.compile(
    r"\b("
    r"smhi|vader(et)?|väder(et)?|temperatur(en)?|regn(et)?|sno(n)?|snö(n)?|"
    r"vind(en|ar)?|vindhastighet(en)?|"
    r"halka(n)?|isrisk(en)?|vaglag(et)?|väglag(et)?|vagvader|vägväder|"
    r"nederbord(en)?|nederbörd(en)?|prognos(en)?|sol(en)?|moln(et|en)?|"
    r"luftfuktighet(en)?|graderna|grader"
    r")\b",
    re.IGNORECASE,
)
_MAP_INTENT_RE = re.compile(
    r"\b(karta|kartbild|kartor|map|marker|markor|pin|"
    r"rutt|route|vagbeskrivning|vägbeskrivning)\b",
    re.IGNORECASE,
)
_MARKETPLACE_INTENT_RE = re.compile(
    r"\b("
    r"blocket|tradera|marknadsplats|marknadsplatser|"
    r"begagnat|begagnad|begagnade|annons|annonser|auktion|auktioner|"
    r"prisj[aä]mf[oö]relse|j[aä]mf[oö]r pris|"
    r"motorcykel|motorcyklar|mc|moped|bilar|båtar|batar|båt|bat"
    r")\b",
    re.IGNORECASE,
)
_MARKETPLACE_PROVIDER_RE = re.compile(
    r"\b(blocket|tradera|marknadsplats|marknadsplatser|annons|annonser|auktion|auktioner)\b",
    re.IGNORECASE,
)
_FILESYSTEM_INTENT_RE = re.compile(
    r"((?:/tmp|/workspace)(?:/[A-Za-z0-9._\-]+)+)"
    r"|"
    r"\b("
    r"fil|filer|file|files|filepath|filename|"
    r"filsystem|filesystem|"
    r"mapp|katalog|directory|folder|"
    r"read_file|write_file|"
    r"sandbox(?:_[a-z]+)?|"
    r"touch|cat|chmod|chown|"
    r"append|replace|ers[aä]tt|"
    r"terminal|bash|shell"
    r")\b",
    re.IGNORECASE,
)
_EXPLICIT_FILE_READ_RE = re.compile(
    r"(l[aä]s|read).*(hela|whole).*(fil|file)",
    re.IGNORECASE,
)
_FILESYSTEM_NOT_FOUND_MARKERS = (
    "does not exist",
    "directory not found",
    "no such file",
    "finns inte",
    "saknas",
    "hittades inte",
)
_MISSING_SIGNAL_RE = re.compile(
    r"\b(saknar|behöver|behover|ange|specificera|uppge|oklart|otydligt)\b",
    re.IGNORECASE,
)
_UNAVAILABLE_RESPONSE_MARKERS = (
    "finns inte tillganglig",
    "finns inte tillgänglig",
    "publiceras inte",
    "inte tillganglig",
    "inte tillgänglig",
    "framtida ar",
    "framtida år",
    "har inte publicerats",
    "saknas for",
    "saknas för",
)
_ALTERNATIVE_RESPONSE_MARKERS = (
    "senaste tillgangliga",
    "senaste tillgängliga",
    "istallet",
    "istället",
    "vill du ha",
    "kan ge",
    "kan visa",
    "2023",
    "2024",
)
_BLOCKED_RESPONSE_MARKERS = (
    "jag kan inte",
    "jag kunde inte",
    "kan tyvarr inte",
    "kan tyvärr inte",
    "saknar tillgang",
    "saknar tillgång",
    "utan tillgang",
    "utan tillgång",
    "annan agent behovs",
    "annan agent behövs",
    "behover annan agent",
    "behöver annan agent",
)
_MISSING_FIELD_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("datum", ("datum", "period", "vecka", "manad", "månad", "ar", "år")),
    ("tid", ("tid", "klockslag", "timme", "avgangstid", "avgångstid")),
    ("plats", ("plats", "ort", "stad", "kommun", "adress", "koordinat")),
    ("stracka", ("stracka", "sträcka", "riktning", "vagnummer", "vägnummer")),
    ("id", ("id", "organisationsnummer", "personnummer", "beteckning")),
    ("kategori", ("kategori", "typ", "slag")),
)
_RESULT_STATUS_VALUES = {"success", "partial", "blocked", "error"}
_ROUTE_STRICT_AGENT_POLICIES: dict[str, set[str]] = {
    # Jämförelse locks to syntes + relevant kunskap agents
    "jämförelse": {"syntes", "statistik-ekonomi", "kunskap"},
    # Backward compat for old string values
    "compare": {"syntes", "statistik-ekonomi", "kunskap"},
}
_COMPARE_FOLLOWUP_RE = re.compile(
    r"\b(jamfor|jämför|jamforelse|jämförelse|skillnad|dessa två|de två|båda|bada)\b",
    re.IGNORECASE,
)
_SUBAGENT_ARTIFACT_RE = re.compile(
    r"(artifact://[A-Za-z0-9._/\-]+|/workspace/[A-Za-z0-9._/\-]+)",
    re.IGNORECASE,
)
_SUBAGENT_DEFAULT_CONTEXT_MAX_CHARS = 1400
_SUBAGENT_DEFAULT_RESULT_MAX_CHARS = 1000
_SUBAGENT_DEFAULT_MAX_CONCURRENCY = 3
_SUBAGENT_MAX_HANDOFFS_IN_PROMPT = 6
_ARTIFACT_DEFAULT_OFFLOAD_THRESHOLD_CHARS = 4_000
_ARTIFACT_DEFAULT_MAX_ENTRIES = 36
_ARTIFACT_OFFLOAD_PER_PASS_LIMIT = 2
_ARTIFACT_CONTEXT_MAX_ITEMS = 6
_ARTIFACT_LOCAL_ROOT = "/tmp/oneseek-artifacts"
_ARTIFACT_DEFAULT_STORAGE_MODE = "auto"
_ARTIFACT_INTERNAL_TOOL_NAMES = {
    "call_agent",
    "call_agents_parallel",
    "retrieve_agents",
    "write_todos",
    "reflect_on_progress",
}
_SANDBOX_ALIAS_TOOL_IDS = {"list_directory"}
