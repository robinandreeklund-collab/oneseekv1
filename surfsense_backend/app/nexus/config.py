"""NEXUS configuration — constants, zone definitions, thresholds.

Single source of truth for all NEXUS-specific configuration values.
"""

from dataclasses import dataclass
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


def get_all_zone_prefixes() -> dict[str, str]:
    """Return zone prefixes for ALL domains (seed + legacy).

    New domains get a prefix derived from the first 5 chars of their id.
    """
    from app.seeds.intent_domains import get_default_intent_domains

    prefixes = dict(ZONE_PREFIXES)
    for domain_id in get_default_intent_domains():
        if domain_id not in prefixes:
            tag = domain_id[:5].upper().replace("-", "")
            prefixes[domain_id] = f"[{tag}] "
    return prefixes


# Namespace prefix → zone mapping (aligned with platform routing)
NAMESPACE_ZONE_MAP: dict[str, str] = {
    "tools/knowledge": Zone.KUNSKAP,
    "tools/weather": "väder-och-klimat",
    "tools/politik": "politik-och-beslut",
    "tools/statistics": "ekonomi-och-skatter",
    "tools/trafik": "trafik-och-transport",
    "tools/bolag": "näringsliv-och-bolag",
    "tools/marketplace": "handel-och-marknad",
    "tools/action": Zone.SKAPANDE,
    "tools/code": Zone.SKAPANDE,
    "tools/kartor": Zone.SKAPANDE,
    "tools/compare": Zone.JAMFORELSE,
    "tools/general": Zone.KUNSKAP,
    "tools/web": Zone.KUNSKAP,
    "tools/media": Zone.SKAPANDE,
    "tools/map": Zone.SKAPANDE,
}


# ---------------------------------------------------------------------------
# Agent Architecture — the middle layer between Intent/Zone and Tools
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NexusAgent:
    """An agent definition for NEXUS routing.

    Each agent belongs to a zone (domain/intent) and owns a set of tool
    namespace prefixes.  Routing: Intent → Agent → Tool.

    ``zone`` is a string that can be any domain_id (e.g. "väder-och-klimat")
    or a legacy Zone enum value (e.g. "kunskap").
    """

    name: str
    zone: str
    description: str
    primary_namespaces: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


def _build_nexus_agents_from_seeds() -> tuple[NexusAgent, ...]:
    """Build NexusAgent list from seed agent definitions.

    Each agent's zone is its domain_id from the seed data.
    """
    from app.seeds.agent_definitions import DEFAULT_AGENT_DEFINITIONS

    agents: list[NexusAgent] = []
    for agent_def in DEFAULT_AGENT_DEFINITIONS:
        agent_id = agent_def.get("agent_id", "")
        if not agent_id:
            continue
        domain_id = agent_def.get("domain_id", Zone.KUNSKAP)
        keywords = agent_def.get("keywords", [])
        ns_raw = agent_def.get("primary_namespaces", [])
        ns_tuple = tuple(
            "/".join(ns) if isinstance(ns, list) else str(ns)
            for ns in ns_raw
        )
        agents.append(
            NexusAgent(
                name=agent_id,
                zone=domain_id,
                description=agent_def.get("description", ""),
                primary_namespaces=ns_tuple,
                keywords=tuple(str(k) for k in keywords),
            )
        )
    return tuple(agents)


# 13 agents built from seed definitions.
# primary_namespaces control which tools belong to each agent.
NEXUS_AGENTS: tuple[NexusAgent, ...] = _build_nexus_agents_from_seeds()

# Lookup helpers (static fallbacks — overridden at runtime by DB agents)
AGENT_BY_NAME: dict[str, NexusAgent] = {a.name: a for a in NEXUS_AGENTS}
AGENTS_BY_ZONE: dict[str, list[NexusAgent]] = {}
for _a in NEXUS_AGENTS:
    AGENTS_BY_ZONE.setdefault(_a.zone, []).append(_a)


def _resolve_namespaces_from_flow_tools(
    flow_tools: list[dict],
) -> tuple[str, ...]:
    """Resolve real namespace prefixes by looking up each flow_tool in the platform.

    Admin flow stores tool-to-agent mappings as flow_tools.  The actual
    namespace for each tool comes from bigtool_store / platform_bridge, not
    from the agent's own namespace field.  This function collects the unique
    namespace *prefixes* (first two segments, e.g. "tools/knowledge") that
    the agent's tools actually belong to.

    Falls back to an empty tuple if no tools can be resolved.
    """
    try:
        from app.nexus.platform_bridge import get_platform_tools
        tools_by_id = {t.tool_id: t for t in get_platform_tools()}
    except Exception:
        return ()

    prefixes: list[str] = []
    for ft in flow_tools:
        tid = ft.get("tool_id", "")
        pt = tools_by_id.get(tid)
        if pt and len(pt.namespace) >= 2:
            prefix = f"{pt.namespace[0]}/{pt.namespace[1]}"
            if prefix not in prefixes:
                prefixes.append(prefix)
    return tuple(prefixes)


def build_agents_from_metadata(
    agent_metadata_list: list[dict],
) -> tuple[dict[str, NexusAgent], dict[str, list[NexusAgent]]]:
    """Build NEXUS agent lookups from DB-backed agent metadata.

    Converts the output of get_effective_agent_metadata() into NexusAgent
    objects and lookup dicts, enabling dynamic agent resolution.

    Each agent's zone is its domain_id (from ``routes``), which may be a
    fine-grained domain like "väder-och-klimat" or a legacy zone like
    "kunskap".

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

        # Use domain_id (from routes) directly as zone — no enum restriction
        routes = meta.get("routes", [])
        zone = routes[0] if routes else Zone.KUNSKAP.value

        # Build namespace prefixes from the agent's actual flow_tools.
        flow_tools = meta.get("flow_tools", [])
        primary_namespaces: tuple[str, ...] = ()
        if flow_tools:
            primary_namespaces = _resolve_namespaces_from_flow_tools(flow_tools)

        # Fallback: derive from the namespace field if flow_tools didn't resolve
        if not primary_namespaces:
            ns_parts = meta.get("namespace", [])
            if isinstance(ns_parts, list) and len(ns_parts) >= 2:
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
    by_zone: dict[str, list[NexusAgent]] = {}
    for a in agents:
        by_zone.setdefault(a.zone, []).append(a)

    return by_name, by_zone


def build_hints_from_metadata(
    agent_metadata_list: list[dict],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Build dynamic DOMAIN_HINTS and CATEGORY_HINTS from DB agent metadata.

    Generates domain-level and agent-level keyword lookups from the effective
    agent metadata, so QUL keyword matching reflects admin flow changes.

    Each agent's domain_id (from ``routes``) is used directly as the zone
    key, preserving fine-grained domain separation.

    Args:
        agent_metadata_list: List of agent metadata dicts from
            agent_metadata_service.get_effective_agent_metadata().

    Returns:
        Tuple of (domain_hints, category_hints) dicts.
        - domain_hints: domain_id → list of keywords
        - category_hints: agent_name → list of keywords
    """
    domain_hints: dict[str, list[str]] = {}
    category_hints: dict[str, list[str]] = {}

    for meta in agent_metadata_list:
        agent_id = meta.get("agent_id", "")
        if not agent_id:
            continue

        # Get keywords
        keywords = meta.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        kw_list = [str(k).lower() for k in keywords if k]

        # Build category hints (agent-level)
        if kw_list:
            category_hints[agent_id] = kw_list

        # Use domain_id from routes directly — no Zone enum restriction
        routes = meta.get("routes", [])
        zone_name = routes[0] if routes else Zone.KUNSKAP.value

        # Add keywords to the domain's hints
        if zone_name not in domain_hints:
            domain_hints[zone_name] = []
        for kw in kw_list:
            if kw not in domain_hints[zone_name]:
                domain_hints[zone_name].append(kw)

        # Also add description-derived terms
        for extra_field in ("main_identifier", "core_activity", "unique_scope"):
            val = meta.get(extra_field, "")
            if val and isinstance(val, str):
                for word in val.lower().split():
                    if len(word) > 3 and word not in domain_hints[zone_name]:
                        domain_hints[zone_name].append(word)

    return domain_hints, category_hints


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

def _build_domain_hints_from_seeds() -> dict[str, list[str]]:
    """Build DOMAIN_HINTS dynamically from seed domain data.

    Each domain_id becomes its own zone key with its own keyword list,
    replacing the old 4-zone system where everything was lumped under
    "kunskap".
    """
    from app.seeds.intent_domains import DEFAULT_INTENT_DOMAINS

    hints: dict[str, list[str]] = {}
    for domain in DEFAULT_INTENT_DOMAINS:
        domain_id = domain.get("domain_id", "")
        if not domain_id:
            continue
        keywords = domain.get("keywords", [])
        if keywords:
            hints[domain_id] = list(keywords)
    return hints


# Domain hints — keywords that suggest specific zones/domains.
# Built dynamically from seed data so each domain has distinct keywords.
DOMAIN_HINTS: dict[str, list[str]] = _build_domain_hints_from_seeds()


# ---------------------------------------------------------------------------
# Category Hints — maps keywords to specific agent names for fine-grained
# routing.  DOMAIN_HINTS resolves only to zone; CATEGORY_HINTS resolves to
# the agent *within* that zone so the AgentResolver can boost the right one.
# ---------------------------------------------------------------------------

def _build_category_hints_from_seeds() -> dict[str, list[str]]:
    """Build CATEGORY_HINTS from seed agent definitions."""
    from app.seeds.agent_definitions import DEFAULT_AGENT_DEFINITIONS

    hints: dict[str, list[str]] = {}
    for agent in DEFAULT_AGENT_DEFINITIONS:
        agent_id = agent.get("agent_id", "")
        keywords = agent.get("keywords", [])
        if agent_id and keywords:
            hints[agent_id] = list(keywords)
    return hints


CATEGORY_HINTS: dict[str, list[str]] = _build_category_hints_from_seeds()


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
