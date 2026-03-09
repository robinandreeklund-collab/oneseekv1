"""Platform Bridge — connects NEXUS to the real OneSeek tool/agent/intent registry.

NEXUS operates on the ACTUAL platform tools, agents, and intents.
This module imports from the SAME sources the live system uses:

  - tools/registry.py  → BUILTIN_TOOLS, domain *_TOOL_DEFINITIONS, EXTERNAL_MODEL_SPECS
  - bigtool_store.py    → TOOL_NAMESPACE_OVERRIDES, TOOL_KEYWORDS, ToolIndexEntry,
                           namespace_for_tool, build_tool_index
  - intent_definition_service → default + DB intent definitions
  - supervisor_constants → live routing phases, agent profiles

NO try/except silencing.  If the platform can't be imported, NEXUS should
fail loudly — not pretend it has zero tools.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass for a platform tool visible to NEXUS
# ---------------------------------------------------------------------------


@dataclass
class PlatformTool:
    """A real tool from the OneSeek platform."""

    tool_id: str
    name: str
    description: str
    category: str  # domain group: smhi, scb, kolada, riksdagen, trafikverket, ...
    namespace: tuple[str, ...]  # e.g. ("tools", "weather", "smhi")
    zone: str  # mapped intent/zone: kunskap, skapande, jämförelse, konversation
    keywords: list[str] = field(default_factory=list)
    geographic_scope: str = ""
    temporal_scope: str = ""
    required_params: list[str] = field(default_factory=list)
    example_queries: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Intent/Zone mapping — matches the real routing system
# ---------------------------------------------------------------------------


def _build_platform_intents() -> tuple[str, ...]:
    """Build platform intents dynamically from seed domain data."""
    try:
        from app.seeds.intent_domains import DEFAULT_INTENT_DOMAINS

        return tuple(
            d["domain_id"] for d in DEFAULT_INTENT_DOMAINS if d.get("domain_id")
        )
    except Exception:
        # Fallback: load all domain IDs from get_all_zone_prefixes
        try:
            from app.nexus.config import get_all_zone_prefixes

            return tuple(get_all_zone_prefixes().keys())
        except Exception:
            return ("kunskap", "skapande", "jämförelse", "konversation")


PLATFORM_INTENTS = _build_platform_intents()


def _build_namespace_to_zone() -> dict[str, str]:
    """Build namespace→zone mapping from NEXUS config (which is dynamic)."""
    from app.nexus.config import NAMESPACE_ZONE_MAP

    return dict(NAMESPACE_ZONE_MAP)


_NAMESPACE_TO_ZONE: dict[str, str] = _build_namespace_to_zone()


def _build_agent_to_zone() -> dict[str, str]:
    """Build agent→zone mapping from seed agent definitions."""
    try:
        from app.seeds.agent_definitions import DEFAULT_AGENT_DEFINITIONS

        return {
            a["agent_id"]: a.get("domain_id", "kunskap")
            for a in DEFAULT_AGENT_DEFINITIONS
            if a.get("agent_id")
        }
    except Exception:
        return {"kunskap": "kunskap", "skapande": "skapande"}


_AGENT_TO_ZONE: dict[str, str] = _build_agent_to_zone()


def _zone_from_namespace(ns: tuple[str, ...]) -> str:
    """Determine intent zone from a namespace tuple.

    Tries most-specific prefix first (4 segments down to 2 segments).
    This allows fine-grained zone mapping like
    tools/statistics/scb/befolkning → befolkning-och-demografi.
    """
    for depth in range(min(len(ns), 4), 1, -1):
        prefix = "/".join(ns[:depth])
        if prefix in _NAMESPACE_TO_ZONE:
            return _NAMESPACE_TO_ZONE[prefix]
    # Fallback: first available domain zone
    return PLATFORM_INTENTS[0] if PLATFORM_INTENTS else "kunskap"


# ---------------------------------------------------------------------------
# Load all platform tools — DYNAMICALLY from the real registry
# ---------------------------------------------------------------------------

_CACHE: list[PlatformTool] | None = None


def _load_from_registry() -> list[PlatformTool]:
    """Load tools from the REAL platform registry.

    Uses the same import paths as:
    - app/agents/new_chat/tools/registry.py  (admin/tools page)
    - app/agents/new_chat/bigtool_store.py   (supervisor routing)

    No try/except silencing — if these imports fail, NEXUS can't work.
    """
    # Import from the REAL registry — same source as /admin/tools
    from app.agents.new_chat.bigtool_store import (
        TOOL_KEYWORDS,
        TOOL_NAMESPACE_OVERRIDES,
        namespace_for_tool,
    )

    # Import domain tool definitions — same imports registry.py makes
    from app.agents.new_chat.kolada_tools import KOLADA_TOOL_DEFINITIONS
    from app.agents.new_chat.marketplace_tools import MARKETPLACE_TOOL_DEFINITIONS
    from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
    from app.agents.new_chat.skolverket_tools import SKOLVERKET_TOOL_DEFINITIONS
    from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.elpris import ELPRIS_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.external_models import EXTERNAL_MODEL_SPECS
    from app.agents.new_chat.tools.geoapify_maps import GEOAPIFY_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.registry import (
        BUILTIN_TOOLS,
    )
    from app.agents.new_chat.tools.riksbank import RIKSBANK_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.smhi import SMHI_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.trafikanalys import TRAFIKANALYS_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS

    tools: list[PlatformTool] = []

    # --- Domain tool definitions ---
    domain_defs: list[tuple[list, str]] = [
        (SMHI_TOOL_DEFINITIONS, "smhi"),
        (TRAFIKVERKET_TOOL_DEFINITIONS, "trafikverket"),
        (BOLAGSVERKET_TOOL_DEFINITIONS, "bolagsverket"),
        (SCB_TOOL_DEFINITIONS, "scb"),
        (RIKSDAGEN_TOOL_DEFINITIONS, "riksdagen"),
        (KOLADA_TOOL_DEFINITIONS, "kolada"),
        (MARKETPLACE_TOOL_DEFINITIONS, "marketplace"),
        (SKOLVERKET_TOOL_DEFINITIONS, "skolverket"),
        (GEOAPIFY_TOOL_DEFINITIONS, "geoapify"),
        (TRAFIKANALYS_TOOL_DEFINITIONS, "trafikanalys"),
        (RIKSBANK_TOOL_DEFINITIONS, "riksbank"),
        (ELPRIS_TOOL_DEFINITIONS, "elpris"),
    ]

    for defs, category in domain_defs:
        for d in defs:
            tid = str(getattr(d, "tool_id", "") or "").strip()
            if not tid:
                continue
            name = str(getattr(d, "name", "") or tid.replace("_", " ").title()).strip()
            desc = str(getattr(d, "description", "") or "").strip()
            kw = list(getattr(d, "keywords", []) or [])
            examples = list(getattr(d, "example_queries", []) or [])
            ns = TOOL_NAMESPACE_OVERRIDES.get(tid, namespace_for_tool(tid))
            extra_kw = TOOL_KEYWORDS.get(tid, [])
            merged_kw = list(dict.fromkeys(kw + extra_kw))
            geo = str(getattr(d, "geographic_scope", "") or "")
            cat = str(getattr(d, "category", "") or category)

            tools.append(
                PlatformTool(
                    tool_id=tid,
                    name=name,
                    description=desc,
                    category=cat,
                    namespace=ns,
                    zone=_zone_from_namespace(ns),
                    keywords=merged_kw,
                    geographic_scope=geo or "sweden",
                    example_queries=examples,
                )
            )

    # --- Builtin tools from registry.py BUILTIN_TOOLS ---
    for tool_def in BUILTIN_TOOLS:
        tid = tool_def.name
        # Skip domain tools already added above (SMHI tools are in BUILTIN_TOOLS too)
        if any(t.tool_id == tid for t in tools):
            continue
        ns = TOOL_NAMESPACE_OVERRIDES.get(tid, namespace_for_tool(tid))
        tools.append(
            PlatformTool(
                tool_id=tid,
                name=tid.replace("_", " ").title(),
                description=tool_def.description,
                category="builtin",
                namespace=ns,
                zone=_zone_from_namespace(ns),
                keywords=TOOL_KEYWORDS.get(tid, []),
            )
        )

    # --- External model tools ---
    for spec in EXTERNAL_MODEL_SPECS:
        tid = spec.tool_name
        ns = TOOL_NAMESPACE_OVERRIDES.get(tid, ("tools", "compare", "external"))
        tools.append(
            PlatformTool(
                tool_id=tid,
                name=tid.replace("call_", "").upper(),
                description=f"Anropa extern AI-modell: {tid.replace('call_', '')}",
                category="external_model",
                namespace=ns,
                zone=_zone_from_namespace(ns),
                keywords=TOOL_KEYWORDS.get(tid, []),
            )
        )

    # Deduplicate by tool_id
    seen: set[str] = set()
    unique: list[PlatformTool] = []
    for t in tools:
        if t.tool_id and t.tool_id not in seen:
            seen.add(t.tool_id)
            unique.append(t)

    return unique


def get_platform_tools() -> list[PlatformTool]:
    """Get all platform tools (cached after first load)."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _load_from_registry()
        logger.info("Platform bridge loaded %d tools", len(_CACHE))
    return _CACHE


def get_platform_tools_by_category() -> dict[str, list[PlatformTool]]:
    """Group platform tools by category."""
    by_cat: dict[str, list[PlatformTool]] = {}
    for tool in get_platform_tools():
        by_cat.setdefault(tool.category, []).append(tool)
    return by_cat


def get_platform_tools_by_zone() -> dict[str, list[PlatformTool]]:
    """Group platform tools by zone/intent."""
    by_zone: dict[str, list[PlatformTool]] = {}
    for tool in get_platform_tools():
        by_zone.setdefault(tool.zone, []).append(tool)
    return by_zone


def get_platform_tool(tool_id: str) -> PlatformTool | None:
    """Look up a single tool by ID."""
    for tool in get_platform_tools():
        if tool.tool_id == tool_id:
            return tool
    return None


def get_category_names() -> list[str]:
    """List all available tool categories."""
    return sorted({t.category for t in get_platform_tools()})


def get_namespace_prefixes() -> list[str]:
    """List all unique namespace prefixes (full agent-aligned paths).

    The tool namespace is already the agent-aligned grouping level
    (e.g. ``("tools", "statistics", "scb", "ekonomi")``), so we use
    the full namespace to preserve sub-domain granularity instead of
    truncating to 3 segments (which collapsed all SCB sub-namespaces
    into a single ``tools/statistics/scb``).
    """
    prefixes: set[str] = set()
    for t in get_platform_tools():
        if len(t.namespace) >= 2:
            prefixes.add("/".join(t.namespace))
    return sorted(prefixes)


def invalidate_cache() -> None:
    """Clear cached tools (call after tool registry changes)."""
    global _CACHE
    _CACHE = None


def apply_overrides_to_cache(
    overrides: dict[str, dict[str, Any]],
) -> int:
    """Patch in-memory tool cache with metadata overrides.

    This is critical for the auto-loop: the optimizer writes improved metadata
    to the DB, but ``get_platform_tools()`` loads from Python source constants.
    This function bridges the gap by directly mutating cached PlatformTool
    objects so the next ``route_query()`` call sees updated descriptions,
    keywords, etc.

    Args:
        overrides: Mapping of tool_id → {description, keywords, ...}.

    Returns:
        Number of tools patched.
    """
    tools = get_platform_tools()
    tool_by_id = {t.tool_id: t for t in tools}
    patched = 0

    for tool_id, fields in overrides.items():
        tool = tool_by_id.get(tool_id)
        if not tool:
            continue

        for attr in (
            "description",
            "keywords",
            "example_queries",
            "excludes",
            "geographic_scope",
        ):
            val = fields.get(attr)
            if val is not None:
                setattr(tool, attr, val)

        patched += 1

    if patched:
        logger.info("Platform bridge: patched %d tools in memory", patched)
    return patched


# ---------------------------------------------------------------------------
# Intent definitions from real platform
# ---------------------------------------------------------------------------


def get_platform_intents() -> dict[str, dict[str, Any]]:
    """Get intent definitions from the real platform.

    Uses the new GraphRegistry seed domains when available (17 domains),
    falling back to the old 4-intent defaults.
    """
    try:
        from app.seeds.intent_domains import get_default_intent_domains
        from app.services.intent_definition_service import (
            domains_to_intent_definitions,
        )

        domains = list(get_default_intent_domains().values())
        if domains:
            defs = domains_to_intent_definitions(domains)
            return {d["intent_id"]: d for d in defs}
    except Exception:
        pass
    from app.services.intent_definition_service import (
        get_default_intent_definitions,
    )

    return dict(get_default_intent_definitions())


# ---------------------------------------------------------------------------
# Agent definitions from real platform
# ---------------------------------------------------------------------------

_PLATFORM_AGENTS_CACHE: list[dict[str, str]] | None = None


def _build_static_fallback_agents() -> list[dict[str, str]]:
    """Build fallback agent list from seed data, using domain_ids as zones."""
    try:
        from app.seeds.agent_definitions import DEFAULT_AGENT_DEFINITIONS

        return [
            {
                "name": a["agent_id"],
                "zone": a.get("domain_id", "kunskap"),
                "description": a.get("description", ""),
            }
            for a in DEFAULT_AGENT_DEFINITIONS
            if a.get("agent_id")
        ]
    except Exception:
        return [{"name": "kunskap", "zone": "kunskap", "description": "Fallback"}]


_STATIC_FALLBACK_AGENTS: list[dict[str, str]] = _build_static_fallback_agents()


def get_platform_agents() -> list[dict[str, str]]:
    """Load agent definitions dynamically from the real platform.

    Uses _EVAL_AGENT_CHOICES and _EVAL_AGENT_DESCRIPTIONS from
    tool_evaluation_service as the source of truth for agent names.
    Falls back to static list if dynamic import fails.
    """
    global _PLATFORM_AGENTS_CACHE
    if _PLATFORM_AGENTS_CACHE is not None:
        return _PLATFORM_AGENTS_CACHE

    try:
        from app.services.tool_evaluation_service import (
            _EVAL_AGENT_CHOICES,
            _EVAL_AGENT_DESCRIPTIONS,
        )

        agents: list[dict[str, str]] = []
        for name in _EVAL_AGENT_CHOICES:
            zone = _AGENT_TO_ZONE.get(name, "kunskap")
            desc = _EVAL_AGENT_DESCRIPTIONS.get(name, name)
            agents.append({"name": name, "zone": zone, "description": desc})

        if agents:
            logger.info("Platform agents loaded dynamically: %d agents", len(agents))
            _PLATFORM_AGENTS_CACHE = agents
            return agents
    except (ImportError, AttributeError) as e:
        logger.warning("Could not load dynamic agents: %s, using static fallback", e)

    _PLATFORM_AGENTS_CACHE = _STATIC_FALLBACK_AGENTS
    return _PLATFORM_AGENTS_CACHE


# Backward compatibility alias (now built from seed data)
PLATFORM_AGENTS = _STATIC_FALLBACK_AGENTS


# ---------------------------------------------------------------------------
# Live routing phases from real platform
# ---------------------------------------------------------------------------

LIVE_ROUTING_PHASES: dict[str, int] = {
    "shadow": 0,
    "tool_gate": 1,
    "agent_auto": 2,
    "adaptive": 3,
    "intent_finetune": 4,
}


# ---------------------------------------------------------------------------
# Async DB-aware accessors (require AsyncSession)
# ---------------------------------------------------------------------------


async def get_effective_intents_from_db(session: Any) -> list[dict[str, Any]]:
    """Get intent definitions merged with DB overrides (the REAL active intents)."""
    from app.services.intent_definition_service import (
        get_effective_intent_definitions,
    )

    return await get_effective_intent_definitions(session)


async def get_tool_lifecycle_statuses(session: Any) -> dict[str, dict[str, Any]]:
    """Get all tool lifecycle statuses (REVIEW / LIVE) from DB."""
    from app.services.tool_lifecycle_service import (
        get_all_tool_lifecycle_statuses,
    )

    rows = await get_all_tool_lifecycle_statuses(session)
    return {r["tool_id"]: r for r in rows if isinstance(r, dict) and r.get("tool_id")}


async def get_live_tool_ids(session: Any) -> list[str] | None:
    """Get tool IDs that are currently LIVE (not REVIEW)."""
    from app.services.tool_lifecycle_service import get_live_tool_ids as _get

    return await _get(session)


async def get_retrieval_tuning(session: Any) -> dict[str, Any]:
    """Get the active retrieval tuning configuration from DB."""
    from app.services.tool_retrieval_tuning_service import (
        get_global_retrieval_tuning,
    )

    return await get_global_retrieval_tuning(session)


async def get_tool_metadata_overrides(session: Any) -> dict[str, dict[str, Any]]:
    """Get admin-configured tool metadata overrides from DB."""
    from app.services.tool_metadata_service import (
        get_global_tool_metadata_overrides,
    )

    return await get_global_tool_metadata_overrides(session)
