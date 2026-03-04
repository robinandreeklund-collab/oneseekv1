"""NEXUS configuration — constants, zone definitions, thresholds.

Single source of truth for all NEXUS-specific configuration values.
"""

from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# Zone Architecture
# ---------------------------------------------------------------------------


class Zone(StrEnum):
    """Zones aligned with the real platform intents (intent_definition_service.py).

    The platform routes to 4 intents: kunskap, skapande, jämförelse, konversation.
    NEXUS uses these same intents as its zone system so that metrics, calibration,
    and routing evaluation are directly comparable to live routing decisions.
    """

    KUNSKAP = "kunskap"
    SKAPANDE = "skapande"
    JAMFORELSE = "jämförelse"
    KONVERSATION = "konversation"


# Backward-compat aliases for old zone names used in tests/existing code
Zone.MYNDIGHETER = Zone.KUNSKAP  # type: ignore[attr-defined]
Zone.HANDLING = Zone.SKAPANDE  # type: ignore[attr-defined]


ZONE_PREFIXES: dict[str, str] = {
    Zone.KUNSKAP: "[KUNSK] ",
    Zone.SKAPANDE: "[SKAP] ",
    Zone.JAMFORELSE: "[JAMFR] ",
    Zone.KONVERSATION: "[KONV] ",
}

# Namespace prefix → zone mapping (aligned with platform routing)
NAMESPACE_ZONE_MAP: dict[str, Zone] = {
    "tools/knowledge": Zone.KUNSKAP,
    "tools/weather": Zone.KUNSKAP,
    "tools/politik": Zone.KUNSKAP,
    "tools/statistics": Zone.KUNSKAP,
    "tools/trafik": Zone.KUNSKAP,
    "tools/bolag": Zone.KUNSKAP,
    "tools/marketplace": Zone.KUNSKAP,
    "tools/action": Zone.SKAPANDE,
    "tools/code": Zone.SKAPANDE,
    "tools/kartor": Zone.SKAPANDE,
    "tools/compare": Zone.JAMFORELSE,
    "tools/general": Zone.KUNSKAP,
}


# ---------------------------------------------------------------------------
# Agent Architecture — the middle layer between Intent/Zone and Tools
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NexusAgent:
    """An agent definition for NEXUS routing.

    Each agent belongs to a zone (intent) and owns a set of tool namespace
    prefixes.  Routing: Intent → Agent → Tool.
    """

    name: str
    zone: Zone
    description: str
    primary_namespaces: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


# 13 agents aligned with production supervisor_agent.py AgentDefinition list.
# primary_namespaces control which tools belong to each agent.
NEXUS_AGENTS: tuple[NexusAgent, ...] = (
    NexusAgent(
        name="åtgärd",
        zone=Zone.KUNSKAP,
        description="Generella uppgifter, realtidsåtgärder och verktygsexekvering",
        primary_namespaces=("tools/action", "tools/general"),
        keywords=("åtgärd", "gör", "utför", "verktyg"),
    ),
    NexusAgent(
        name="väder",
        zone=Zone.KUNSKAP,
        description="SMHI väderdata, prognoser och Trafikverket vägväder",
        primary_namespaces=("tools/weather",),
        keywords=(
            "väder", "vädret", "smhi", "temperatur", "regn", "prognos",
            "snö", "vind", "vägväder",
        ),
    ),
    NexusAgent(
        name="kartor",
        zone=Zone.SKAPANDE,
        description="Kartgenerering via Geoapify",
        primary_namespaces=("tools/kartor",),
        keywords=("karta", "kartbild", "geoapify", "plats", "visa på karta"),
    ),
    NexusAgent(
        name="media",
        zone=Zone.SKAPANDE,
        description="Podcast- och mediagenerering",
        primary_namespaces=(),
        keywords=("podcast", "media", "ljud", "bild", "generera"),
    ),
    NexusAgent(
        name="kunskap",
        zone=Zone.KUNSKAP,
        description="Intern kunskapsbas, SurfSense-docs och webbsökning via Tavily",
        primary_namespaces=("tools/knowledge",),
        keywords=(
            "dokument", "docs", "kunskap", "sök", "search", "notion",
            "slack", "github", "sammanfatta",
        ),
    ),
    NexusAgent(
        name="webb",
        zone=Zone.KUNSKAP,
        description="Webbskrapning och länkförhandsgranskning",
        primary_namespaces=(),
        keywords=("webb", "länk", "url", "nyheter", "scrape"),
    ),
    NexusAgent(
        name="kod",
        zone=Zone.SKAPANDE,
        description="Sandbox-kodexekvering och beräkningar",
        primary_namespaces=("tools/code",),
        keywords=("kod", "python", "script", "sandbox", "exekvera", "kör"),
    ),
    NexusAgent(
        name="bolag",
        zone=Zone.KUNSKAP,
        description="Bolagsverket företagsinformation",
        primary_namespaces=("tools/bolag",),
        keywords=("bolag", "bolagsverket", "företag", "org", "organisationsnummer"),
    ),
    NexusAgent(
        name="statistik",
        zone=Zone.KUNSKAP,
        description="SCB, Kolada, Skolverket statistik och nyckeltal",
        primary_namespaces=("tools/statistics",),
        keywords=(
            "statistik", "scb", "kolada", "befolkning", "nyckeltal",
            "skolverket", "utbildning", "kommun",
        ),
    ),
    NexusAgent(
        name="trafik",
        zone=Zone.KUNSKAP,
        description="Trafikverket realtidstrafik, tåg och vägdata",
        primary_namespaces=("tools/trafik",),
        keywords=(
            "trafik", "trafiken", "trafikverket", "tåg", "väg", "kamera",
            "järnväg", "störning",
        ),
    ),
    NexusAgent(
        name="riksdagen",
        zone=Zone.KUNSKAP,
        description="Riksdagsdokument, voteringar och propositioner",
        primary_namespaces=("tools/politik",),
        keywords=(
            "riksdagen", "proposition", "betänkande", "motion", "votering",
            "ledamot", "politik",
        ),
    ),
    NexusAgent(
        name="marknad",
        zone=Zone.KUNSKAP,
        description="Blocket, Tradera och marknadsplatser",
        primary_namespaces=("tools/marketplace",),
        keywords=("blocket", "tradera", "marknadsplats", "annons", "begagnat"),
    ),
    NexusAgent(
        name="syntes",
        zone=Zone.KUNSKAP,
        description="Sammanfattning och syntes av resultat",
        primary_namespaces=(),
        keywords=("sammanfatta", "syntes", "summera"),
    ),
)

# Lookup helpers (static fallbacks — overridden at runtime by DB agents)
AGENT_BY_NAME: dict[str, NexusAgent] = {a.name: a for a in NEXUS_AGENTS}
AGENTS_BY_ZONE: dict[Zone, list[NexusAgent]] = {}
for _a in NEXUS_AGENTS:
    AGENTS_BY_ZONE.setdefault(_a.zone, []).append(_a)


def build_agents_from_metadata(
    agent_metadata_list: list[dict],
) -> tuple[dict[str, NexusAgent], dict[Zone, list[NexusAgent]]]:
    """Build NEXUS agent lookups from DB-backed agent metadata.

    Converts the output of get_effective_agent_metadata() into NexusAgent
    objects and lookup dicts, enabling dynamic agent resolution.

    Args:
        agent_metadata_list: List of agent metadata dicts from
            agent_metadata_service.get_effective_agent_metadata().

    Returns:
        Tuple of (agent_by_name, agents_by_zone) dicts.
    """
    agents: list[NexusAgent] = []

    for meta in agent_metadata_list:
        agent_id = meta.get("agent_id", "")
        if not agent_id:
            continue

        # Map routes (intent names) to Zone enum values
        routes = meta.get("routes", [])
        zone = Zone.KUNSKAP  # default
        for route_name in routes:
            try:
                zone = Zone(route_name)
                break  # Use first valid zone
            except ValueError:
                continue

        # Build namespace tuple from metadata namespace field
        # Admin stores as list like ["agents", "weather"] → "tools/weather"
        ns_parts = meta.get("namespace", [])
        primary_namespaces: tuple[str, ...] = ()
        if isinstance(ns_parts, list) and len(ns_parts) >= 2:
            # Map "agents/X" style to "tools/X" for NEXUS compatibility
            ns_prefix = ns_parts[0] if ns_parts[0] != "agents" else "tools"
            primary_namespaces = (f"{ns_prefix}/{ns_parts[1]}",)
        elif isinstance(ns_parts, str) and ns_parts:
            primary_namespaces = (ns_parts,)

        # Keywords
        keywords = meta.get("keywords", [])
        if isinstance(keywords, list):
            keywords_tuple = tuple(str(k) for k in keywords)
        else:
            keywords_tuple = ()

        agents.append(
            NexusAgent(
                name=agent_id,
                zone=zone,
                description=meta.get("description", ""),
                primary_namespaces=primary_namespaces,
                keywords=keywords_tuple,
            )
        )

    # Build lookup dicts
    by_name: dict[str, NexusAgent] = {a.name: a for a in agents}
    by_zone: dict[Zone, list[NexusAgent]] = {}
    for a in agents:
        by_zone.setdefault(a.zone, []).append(a)

    return by_name, by_zone


# ---------------------------------------------------------------------------
# Confidence Band Cascade
# ---------------------------------------------------------------------------


class Band(StrEnum):
    """Confidence bands — determines routing behavior."""

    BAND_0 = "band_0"  # Direct route, no LLM
    BAND_1 = "band_1"  # Namespace verify, minimal LLM
    BAND_2 = "band_2"  # Top-3 candidates, LLM chooses
    BAND_3 = "band_3"  # Decompose / reformulate
    BAND_4 = "band_4"  # OOD detection → fallback


@dataclass(frozen=True)
class BandThresholds:
    """Thresholds for confidence band classification."""

    band_0_min_score: float = 0.95
    band_0_min_margin: float = 0.20
    band_1_min_score: float = 0.80
    band_1_min_margin: float = 0.10
    band_2_min_score: float = 0.60
    band_3_min_score: float = 0.40
    # Below band_3_min_score → Band 4 (OOD)


BAND_THRESHOLDS = BandThresholds()


# ---------------------------------------------------------------------------
# OOD Detection
# ---------------------------------------------------------------------------

OOD_ENERGY_THRESHOLD: float = -5.0
OOD_KNN_K: int = 5
OOD_KNN_THRESHOLD: float = 2.5
OOD_ENERGY_BORDERLINE_FACTOR: float = 0.8


# ---------------------------------------------------------------------------
# QUL — Query Understanding Layer
# ---------------------------------------------------------------------------

MULTI_INTENT_MARGIN_THRESHOLD: float = 0.15
SPACY_MODEL: str = "sv_core_news_lg"
MIN_ENTITY_CONFIDENCE: float = 0.70

# Swedish normalization bank — common abbreviations → canonical forms
SWEDISH_NORMALIZATION_BANK: dict[str, str] = {
    "sl": "Storstockholms Lokaltrafik",
    "smhi": "Sveriges meteorologiska och hydrologiska institut",
    "scb": "Statistiska centralbyrån",
    "sj": "Statens Järnvägar",
    "svt": "Sveriges Television",
    "sr": "Sveriges Radio",
    "msb": "Myndigheten för samhällsskydd och beredskap",
    "skv": "Skatteverket",
    "fk": "Försäkringskassan",
    "af": "Arbetsförmedlingen",
    "tvårumma": "tvårumslägenhet",
    "trerumma": "trerumslägenhet",
    "fyrarumma": "fyrarumslägenhet",
    "dagis": "förskola",
    "gympa": "idrott",
    "moms": "mervärdesskatt",
    "sthlm": "Stockholm",
    "gbg": "Göteborg",
    "cph": "Köpenhamn",
}

# Domain hints — keywords that suggest specific zones.
# Aligned with real intent_definition_service.py keywords.
DOMAIN_HINTS: dict[str, list[str]] = {
    Zone.KUNSKAP: [
        # From real intent_definition_service "kunskap" keywords
        "dokument",
        "docs",
        "kunskap",
        "sök",
        "search",
        "notion",
        "slack",
        "github",
        "sammanfatta",
        # Weather / SMHI
        "väder",
        "vädret",
        "vader",
        "vadret",
        "smhi",
        "temperatur",
        "regn",
        "prognos",
        # Traffic
        "trafik",
        "trafiken",
        "trafikverket",
        "tåg",
        "väg",
        # Statistics
        "statistik",
        "scb",
        "befolkning",
        "kolada",
        "nyckeltal",
        # Company
        "bolag",
        "bolagsverket",
        # Parliament
        "riksdagen",
        "proposition",
        "betänkande",
        "motion",
        # Marketplace
        "blocket",
        "tradera",
        "marknadsplats",
        "annons",
        "begagnat",
        # Web
        "webb",
        "länk",
        "nyheter",
        "nyheter",
        # General knowledge
        "vad är",
        "hur mycket",
        "hur många",
        "hitta",
        "information",
        # Education
        "skola",
        "utbildning",
        "kursplan",
        "skolverket",
        # Municipality
        "kommun",
        "region",
    ],
    Zone.SKAPANDE: [
        # From real intent_definition_service "skapande" keywords
        "skapa",
        "generera",
        "gör",
        "rita",
        "podcast",
        "bild",
        "karta",
        "kartbild",
        "kod",
        "script",
        "python",
        "sandbox",
        "fil",
        "skriv",
        "exekvera",
        "kör",
    ],
    Zone.JAMFORELSE: [
        # From real intent_definition_service "jämförelse" keywords
        "/compare",
        "compare",
        "jämför",
        "jamfor",
        "jämförelse",
        "modeller",
        "ai",
        "gpt",
        "claude",
        "grok",
        "gemini",
    ],
    Zone.KONVERSATION: [
        # From real intent_definition_service "konversation" keywords
        "hej",
        "tjena",
        "hallå",
        "hur mår du",
        "konversation",
        "smalltalk",
    ],
}


# ---------------------------------------------------------------------------
# Category Hints — maps keywords to specific agent names for fine-grained
# routing.  DOMAIN_HINTS resolves only to zone; CATEGORY_HINTS resolves to
# the agent *within* that zone so the AgentResolver can boost the right one.
# ---------------------------------------------------------------------------

CATEGORY_HINTS: dict[str, list[str]] = {
    "väder": ["väder", "vädret", "vader", "vadret", "smhi", "temperatur", "regn", "prognos", "väderleksrapport"],
    "statistik": ["statistik", "scb", "befolkning", "kolada", "nyckeltal", "skolverket", "skola", "kursplan"],
    "trafik": ["trafik", "trafiken", "trafikverket", "tåg", "väg", "vägarbete", "förseningar"],
    "bolag": ["bolag", "bolagsverket", "företag", "organisationsnummer"],
    "riksdagen": ["riksdagen", "proposition", "betänkande", "motion", "votering"],
    "marknad": ["blocket", "tradera", "marknadsplats", "annons", "begagnat"],
    "kunskap": ["dokument", "docs", "kunskap", "sök", "search", "notion", "slack", "github", "sammanfatta"],
    "webb": ["webb", "länk", "nyheter", "url", "scrape"],
    "kartor": ["karta", "kartbild", "geoapify", "visa på karta"],
    "kod": ["kod", "python", "script", "sandbox", "exekvera"],
    "media": ["podcast", "media", "ljud", "generera bild"],
}


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

# ECE targets per band range
ECE_TARGET_BAND_01: float = 0.05
ECE_TARGET_BAND_2: float = 0.10

# Platt scaling defaults
PLATT_DEFAULT_A: float = 1.0
PLATT_DEFAULT_B: float = 0.0


# ---------------------------------------------------------------------------
# Zone Health Targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneHealthTargets:
    """Target metrics for zone health monitoring."""

    intra_zone_silhouette_min: float = 0.45
    intra_zone_silhouette_target: float = 0.60
    inter_zone_distance_min: float = 0.40
    inter_zone_distance_target: float = 0.55
    confusion_risk_max: float = 0.40
    confusion_risk_target: float = 0.25
    zone_purity_min: float = 0.80
    zone_purity_target: float = 0.90
    hubness_max: float = 0.08
    hubness_target: float = 0.03


ZONE_HEALTH_TARGETS = ZoneHealthTargets()


# ---------------------------------------------------------------------------
# Pipeline Stages (Eval Ledger)
# ---------------------------------------------------------------------------


class PipelineStage(StrEnum):
    """The 6 stages of the precision routing pipeline."""

    INTENT = "intent"
    AGENT = "agent"
    ROUTE = "route"
    BIGTOOL = "bigtool"
    RERANK = "rerank"
    E2E = "e2e"


PIPELINE_STAGES: list[tuple[int, str]] = [
    (1, PipelineStage.INTENT),
    (2, PipelineStage.AGENT),
    (3, PipelineStage.ROUTE),
    (4, PipelineStage.BIGTOOL),
    (5, PipelineStage.RERANK),
    (6, PipelineStage.E2E),
]


# ---------------------------------------------------------------------------
# Deploy Control — Triple Gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeployGateThresholds:
    """Thresholds for the triple-gate deployment system."""

    # Gate 1: Separation
    min_separation_score: float = 0.65

    # Gate 2: Eval
    min_success_rate: float = 0.80
    min_hard_negative_rate: float = 0.85
    min_adversarial_rate: float = 0.80

    # Gate 3: LLM Judge
    min_description_clarity: float = 4.0
    min_keyword_relevance: float = 4.0
    min_disambiguation_quality: float = 4.0


DEPLOY_GATE_THRESHOLDS = DeployGateThresholds()


# ---------------------------------------------------------------------------
# Synth Forge
# ---------------------------------------------------------------------------

SYNTH_DIFFICULTIES: list[str] = ["easy", "medium", "hard", "adversarial"]
SYNTH_QUESTIONS_PER_DIFFICULTY: int = 4
SYNTH_ROUNDTRIP_TOP_K: int = 3
