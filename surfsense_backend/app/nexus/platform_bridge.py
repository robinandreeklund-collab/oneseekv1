"""Platform Bridge — connects NEXUS to the real OneSeek tool/agent/intent registry.

NEXUS must operate on the ACTUAL platform tools, agents, and intents — not
a hand-maintained copy.  This module is the single integration point.

It imports from:
  - bigtool_store.py → TOOL_NAMESPACE_OVERRIDES, TOOL_KEYWORDS, ToolIndexEntry
  - Domain tool definitions → SMHI, SCB, Kolada, Riksdagen, Trafikverket,
    Bolagsverket, Marketplace, Skolverket, Geoapify
  - intent_definition_service → default intent definitions (kunskap, skapande, etc.)
  - supervisor_agent → agent definitions (väder, statistik, marknad, etc.)
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

# The real platform uses these 4 intents (from intent_definition_service.py)
PLATFORM_INTENTS = ("kunskap", "skapande", "jämförelse", "konversation")

# Map namespace prefixes → intent zones (mirrors real supervisor routing)
_NAMESPACE_TO_ZONE: dict[str, str] = {
    "tools/knowledge": "kunskap",
    "tools/weather": "kunskap",  # weather is a knowledge-intent (lookup)
    "tools/politik": "kunskap",
    "tools/statistics": "kunskap",
    "tools/trafik": "kunskap",
    "tools/bolag": "kunskap",
    "tools/marketplace": "kunskap",
    "tools/action": "skapande",
    "tools/code": "skapande",
    "tools/kartor": "skapande",
    "tools/compare": "jämförelse",
    "tools/general": "kunskap",
}

# Map agent names → intent zones
_AGENT_TO_ZONE: dict[str, str] = {
    "åtgärd": "kunskap",
    "väder": "kunskap",
    "kartor": "skapande",
    "statistik": "kunskap",
    "media": "skapande",
    "kunskap": "kunskap",
    "webb": "kunskap",
    "kod": "skapande",
    "bolag": "kunskap",
    "trafik": "kunskap",
    "riksdagen": "kunskap",
    "marknad": "kunskap",
    "syntes": "kunskap",
}


def _zone_from_namespace(ns: tuple[str, ...]) -> str:
    """Determine intent zone from a namespace tuple."""
    if len(ns) >= 2:
        prefix = f"{ns[0]}/{ns[1]}"
        if prefix in _NAMESPACE_TO_ZONE:
            return _NAMESPACE_TO_ZONE[prefix]
    return "kunskap"


# ---------------------------------------------------------------------------
# Load all platform tools
# ---------------------------------------------------------------------------

_CACHE: list[PlatformTool] | None = None


def _load_domain_definitions() -> list[PlatformTool]:
    """Import and normalize all domain tool definitions."""
    tools: list[PlatformTool] = []

    try:
        from app.agents.new_chat.tools.smhi import SMHI_TOOL_DEFINITIONS
    except Exception:
        SMHI_TOOL_DEFINITIONS = []  # noqa: N806

    try:
        from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS
    except Exception:
        TRAFIKVERKET_TOOL_DEFINITIONS = []  # noqa: N806

    try:
        from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
    except Exception:
        BOLAGSVERKET_TOOL_DEFINITIONS = []  # noqa: N806

    try:
        from app.agents.new_chat.tools.geoapify_maps import GEOAPIFY_TOOL_DEFINITIONS
    except Exception:
        GEOAPIFY_TOOL_DEFINITIONS = []  # noqa: N806

    try:
        from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
    except Exception:
        SCB_TOOL_DEFINITIONS = []  # noqa: N806

    try:
        from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
    except Exception:
        RIKSDAGEN_TOOL_DEFINITIONS = []  # noqa: N806

    try:
        from app.agents.new_chat.kolada_tools import KOLADA_TOOL_DEFINITIONS
    except Exception:
        KOLADA_TOOL_DEFINITIONS = []  # noqa: N806

    try:
        from app.agents.new_chat.marketplace_tools import MARKETPLACE_TOOL_DEFINITIONS
    except Exception:
        MARKETPLACE_TOOL_DEFINITIONS = []  # noqa: N806

    try:
        from app.agents.new_chat.skolverket_tools import SKOLVERKET_TOOL_DEFINITIONS
    except Exception:
        SKOLVERKET_TOOL_DEFINITIONS = []  # noqa: N806

    # Try to import namespace overrides and keywords from bigtool_store
    try:
        from app.agents.new_chat.bigtool_store import (
            TOOL_KEYWORDS,
            TOOL_NAMESPACE_OVERRIDES,
        )
    except Exception:
        TOOL_KEYWORDS = {}  # noqa: N806
        TOOL_NAMESPACE_OVERRIDES = {}  # noqa: N806

    def _def_to_tool(
        d: Any,
        *,
        category: str,
        default_ns: tuple[str, ...],
        geographic_scope: str = "",
        temporal_scope: str = "",
        required_params: list[str] | None = None,
    ) -> PlatformTool:
        tid = str(getattr(d, "tool_id", "") or "").strip()
        name = str(getattr(d, "name", "") or tid.replace("_", " ").title()).strip()
        desc = str(getattr(d, "description", "") or "").strip()
        kw = list(getattr(d, "keywords", []) or [])
        examples = list(getattr(d, "example_queries", []) or [])
        ns = TOOL_NAMESPACE_OVERRIDES.get(tid, default_ns)
        extra_kw = TOOL_KEYWORDS.get(tid, [])
        merged_kw = list(dict.fromkeys(kw + extra_kw))  # dedup preserving order
        return PlatformTool(
            tool_id=tid,
            name=name,
            description=desc,
            category=category,
            namespace=ns,
            zone=_zone_from_namespace(ns),
            keywords=merged_kw,
            geographic_scope=geographic_scope or getattr(d, "geographic_scope", ""),
            temporal_scope=temporal_scope or getattr(d, "temporal_scope", ""),
            required_params=required_params or [],
            example_queries=examples,
        )

    # SMHI
    for d in SMHI_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="smhi",
                default_ns=("tools", "weather", "smhi"),
                geographic_scope="sweden",
            )
        )

    # Trafikverket
    for d in TRAFIKVERKET_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="trafikverket",
                default_ns=("tools", "trafik"),
                geographic_scope="sweden",
            )
        )

    # Bolagsverket
    for d in BOLAGSVERKET_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="bolagsverket",
                default_ns=("tools", "bolag"),
                geographic_scope="sweden",
            )
        )

    # SCB
    for d in SCB_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="scb",
                default_ns=("tools", "statistics"),
                geographic_scope="sweden",
            )
        )

    # Riksdagen
    for d in RIKSDAGEN_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="riksdagen",
                default_ns=("tools", "politik"),
                geographic_scope="sweden",
            )
        )

    # Kolada
    for d in KOLADA_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="kolada",
                default_ns=("tools", "statistics"),
                geographic_scope="sweden",
                required_params=["municipality"],
            )
        )

    # Marketplace
    for d in MARKETPLACE_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="marketplace",
                default_ns=("tools", "marketplace"),
                geographic_scope="sweden",
            )
        )

    # Skolverket
    for d in SKOLVERKET_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="skolverket",
                default_ns=("tools", "knowledge"),
                geographic_scope="sweden",
            )
        )

    # Geoapify
    for d in GEOAPIFY_TOOL_DEFINITIONS:
        tools.append(
            _def_to_tool(
                d,
                category="geoapify",
                default_ns=("tools", "kartor"),
            )
        )

    # Built-in tools (not from domain definitions)
    builtin_tools = [
        PlatformTool(
            tool_id="search_knowledge_base",
            name="Sök kunskapsbas",
            description="Söker i användarens personliga kunskapsbas",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "search_knowledge_base", ("tools", "knowledge", "kb")
            ),
            zone="kunskap",
            keywords=TOOL_KEYWORDS.get("search_knowledge_base", []),
        ),
        PlatformTool(
            tool_id="search_tavily",
            name="Webbsökning",
            description="Sök på webben via Tavily",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "search_tavily", ("tools", "knowledge", "web")
            ),
            zone="kunskap",
            keywords=TOOL_KEYWORDS.get("search_tavily", []),
        ),
        PlatformTool(
            tool_id="search_surfsense_docs",
            name="SurfSense docs",
            description="Söker i SurfSense dokumentation",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "search_surfsense_docs", ("tools", "knowledge", "docs")
            ),
            zone="kunskap",
            keywords=TOOL_KEYWORDS.get("search_surfsense_docs", []),
        ),
        PlatformTool(
            tool_id="generate_podcast",
            name="Generera podcast",
            description="Genererar en ljudpodd från innehåll",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "generate_podcast", ("tools", "action", "media")
            ),
            zone="skapande",
            keywords=TOOL_KEYWORDS.get("generate_podcast", []),
        ),
        PlatformTool(
            tool_id="display_image",
            name="Visa bild",
            description="Visar en bild i chatten",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "display_image", ("tools", "action", "media")
            ),
            zone="skapande",
            keywords=TOOL_KEYWORDS.get("display_image", []),
        ),
        PlatformTool(
            tool_id="scrape_webpage",
            name="Skrapa webbsida",
            description="Extraherar innehåll från webbsidor",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "scrape_webpage", ("tools", "action", "web")
            ),
            zone="kunskap",
            keywords=TOOL_KEYWORDS.get("scrape_webpage", []),
        ),
        PlatformTool(
            tool_id="link_preview",
            name="Länkförhandsvisning",
            description="Hämtar metadata för en URL",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "link_preview", ("tools", "action", "web")
            ),
            zone="kunskap",
            keywords=TOOL_KEYWORDS.get("link_preview", []),
        ),
        PlatformTool(
            tool_id="sandbox_execute",
            name="Kör kod",
            description="Kör kommandon i en isolerad sandbox",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "sandbox_execute", ("tools", "code", "sandbox")
            ),
            zone="skapande",
            keywords=TOOL_KEYWORDS.get("sandbox_execute", []),
        ),
        PlatformTool(
            tool_id="trafiklab_route",
            name="Kollektivtrafik",
            description="Sök resor och avgångar i kollektivtrafiken",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "trafiklab_route", ("tools", "action", "travel")
            ),
            zone="kunskap",
            keywords=TOOL_KEYWORDS.get("trafiklab_route", []),
            geographic_scope="sweden",
            required_params=["origin", "destination"],
        ),
        PlatformTool(
            tool_id="libris_search",
            name="Bibliotekssökning",
            description="Sök i Libris - Sveriges nationella bibliotekskatalog",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "libris_search", ("tools", "action", "data")
            ),
            zone="kunskap",
            keywords=TOOL_KEYWORDS.get("libris_search", []),
        ),
        PlatformTool(
            tool_id="jobad_links_search",
            name="Jobbsökning",
            description="Sök bland jobbannonser",
            category="builtin",
            namespace=TOOL_NAMESPACE_OVERRIDES.get(
                "jobad_links_search", ("tools", "action", "data")
            ),
            zone="kunskap",
            keywords=TOOL_KEYWORDS.get("jobad_links_search", []),
        ),
    ]

    # External model tools
    for model_name in (
        "call_gpt",
        "call_claude",
        "call_grok",
        "call_gemini",
        "call_deepseek",
        "call_perplexity",
        "call_qwen",
    ):
        builtin_tools.append(
            PlatformTool(
                tool_id=model_name,
                name=model_name.replace("call_", "").upper(),
                description=f"Anropa extern AI-modell: {model_name.replace('call_', '')}",
                category="external_model",
                namespace=TOOL_NAMESPACE_OVERRIDES.get(
                    model_name, ("tools", "compare", "external")
                ),
                zone="jämförelse",
                keywords=TOOL_KEYWORDS.get(model_name, []),
            )
        )

    tools.extend(builtin_tools)

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
        _CACHE = _load_domain_definitions()
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


def invalidate_cache() -> None:
    """Clear cached tools (call after tool registry changes)."""
    global _CACHE
    _CACHE = None


# ---------------------------------------------------------------------------
# Intent definitions from real platform
# ---------------------------------------------------------------------------


def get_platform_intents() -> dict[str, dict[str, Any]]:
    """Get intent definitions from the real intent_definition_service."""
    try:
        from app.services.intent_definition_service import (
            get_default_intent_definitions,
        )

        return dict(get_default_intent_definitions())
    except Exception:
        # Fallback
        return {
            "kunskap": {"intent_id": "kunskap", "keywords": []},
            "skapande": {"intent_id": "skapande", "keywords": []},
            "jämförelse": {"intent_id": "jämförelse", "keywords": []},
            "konversation": {"intent_id": "konversation", "keywords": []},
        }
