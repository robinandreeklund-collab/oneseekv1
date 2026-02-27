"""Constants and configuration for the supervisor agent."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from app.agents.new_chat.tools.external_models import EXTERNAL_MODEL_SPECS
from app.agents.new_chat.tools.smhi import SMHI_TOOL_DEFINITIONS
from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.marketplace_tools import MARKETPLACE_TOOL_DEFINITIONS


_AGENT_CACHE_TTL = timedelta(minutes=20)
_AGENT_COMBO_CACHE: dict[str, tuple[datetime, list[str]]] = {}

# Specialized agents that have their own WorkerConfig with specific primary_namespaces
# These should NOT be overridden by route_policy if explicitly selected
# This scales to 100s of APIs without needing regex patterns for each one
_SPECIALIZED_AGENTS = {
    "marknad",      # Blocket/Tradera tools
    "statistik",    # SCB/Kolada tools
    "riksdagen",    # Parliament data tools
    "bolag",        # Company registry tools
    "trafik",       # Traffic/transport tools
    "väder",        # Weather-specific tools
    "kartor",       # Map generation tools
}
# Backward compat: accept old English agent names
_COMPAT_AGENT_NAMES: dict[str, str] = {
    "action": "åtgärd",
    "weather": "väder",
    "statistics": "statistik",
    "knowledge": "kunskap",
    "browser": "webb",
    "code": "kod",
    "marketplace": "marknad",
    "synthesis": "syntes",
}
_COMPAT_AGENT_NAMES_REVERSE: dict[str, str] = {v: k for k, v in _COMPAT_AGENT_NAMES.items()}

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
    return _LIVE_ROUTING_PHASE_ORDER.get(current_phase, 0) >= _LIVE_ROUTING_PHASE_ORDER.get(
        minimum_phase, 0
    )


@dataclass(frozen=True)
class AgentToolProfile:
    tool_id: str
    category: str
    description: str
    keywords: tuple[str, ...]


def _build_agent_tool_profiles() -> dict[str, list[AgentToolProfile]]:
    profiles: dict[str, list[AgentToolProfile]] = {
        "väder": [],
        "trafik": [],
        "statistik": [],
        "riksdagen": [],
        "bolag": [],
        "marknad": [],
    }
    for definition in SMHI_TOOL_DEFINITIONS:
        profiles["väder"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "väder")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    for definition in TRAFIKVERKET_TOOL_DEFINITIONS:
        profiles["trafik"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "trafik")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    for definition in SCB_TOOL_DEFINITIONS:
        profiles["statistik"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "base_path", "statistik")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    for definition in RIKSDAGEN_TOOL_DEFINITIONS:
        profiles["riksdagen"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "riksdagen")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    for definition in BOLAGSVERKET_TOOL_DEFINITIONS:
        profiles["bolag"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "bolag")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    for definition in MARKETPLACE_TOOL_DEFINITIONS:
        profiles["marknad"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "marknad")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
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
_MAX_AGENT_HOPS_PER_TURN = 3
# P1 loop-fix: hard cap on total meaningful steps across the entire flow.
# At this threshold the flow is forced to synthesis regardless of critic decision.
MAX_TOTAL_STEPS = 8
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
    # Traffic
    "traffic_information": "trafik",
    "traffic_info": "trafik",
    "traffic_agent": "trafik",
    "road_works_planner": "trafik",
    "roadworks_planner": "trafik",
    "road_work_planner": "trafik",
    "roadworks": "trafik",
    # Statistics → statistik
    "municipality_agent": "statistik",
    "statistic_agent": "statistik",
    "statistics_agent": "statistik",
    "statistics": "statistik",
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
    "jämförelse": {"syntes", "statistik", "kunskap"},
    # Backward compat for old string values
    "compare": {"syntes", "statistik", "kunskap"},
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
