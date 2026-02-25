from enum import Enum


class ExecutionMode(str, Enum):
    """First-class routing decision (Nivå 1).

    Determines *how* the system should process the user's query:
    - TOOL_REQUIRED:  External structured data is needed (API calls).
    - TOOL_OPTIONAL:  LLM may know the answer; tools available as fallback.
    - TOOL_FORBIDDEN: No tools — pure LLM response (smalltalk, greetings).
    - MULTI_SOURCE:   Multiple domain agents or comparison across sources.
    """

    TOOL_REQUIRED = "tool_required"
    TOOL_OPTIONAL = "tool_optional"
    TOOL_FORBIDDEN = "tool_forbidden"
    MULTI_SOURCE = "multi_source"

    @classmethod
    def _missing_(cls, value: object):
        _COMPAT = {
            # Old graph_complexity / route values → execution mode
            "kunskap": cls.TOOL_REQUIRED,
            "knowledge": cls.TOOL_REQUIRED,
            "skapande": cls.TOOL_REQUIRED,
            "action": cls.TOOL_REQUIRED,
            "konversation": cls.TOOL_FORBIDDEN,
            "smalltalk": cls.TOOL_FORBIDDEN,
            "jämförelse": cls.MULTI_SOURCE,
            "compare": cls.MULTI_SOURCE,
            "statistics": cls.TOOL_REQUIRED,
            "mixed": cls.MULTI_SOURCE,
            # Old complexity values
            "trivial": cls.TOOL_FORBIDDEN,
            "simple": cls.TOOL_REQUIRED,
            "complex": cls.TOOL_REQUIRED,
        }
        if isinstance(value, str):
            return _COMPAT.get(value.strip().lower())
        return None


class Route(str, Enum):
    KUNSKAP = "kunskap"
    SKAPANDE = "skapande"
    KONVERSATION = "konversation"
    JAMFORELSE = "jämförelse"

    # ── Backward-compat aliases (kept so old DB rows / logs still parse) ──
    @classmethod
    def _missing_(cls, value: object):
        _COMPAT = {
            "knowledge": cls.KUNSKAP,
            "action": cls.SKAPANDE,
            "smalltalk": cls.KONVERSATION,
            "compare": cls.JAMFORELSE,
            "statistics": cls.KUNSKAP,  # merged into kunskap
        }
        if isinstance(value, str):
            return _COMPAT.get(value.strip().lower())
        return None


# ── Route → default ExecutionMode mapping ─────────────────────────────
ROUTE_TO_EXECUTION_MODE: dict[Route, ExecutionMode] = {
    Route.KUNSKAP: ExecutionMode.TOOL_REQUIRED,
    Route.SKAPANDE: ExecutionMode.TOOL_REQUIRED,
    Route.KONVERSATION: ExecutionMode.TOOL_FORBIDDEN,
    Route.JAMFORELSE: ExecutionMode.MULTI_SOURCE,
}


# ── Tool allow-lists per route ────────────────────────────────────────
# Kunskap: all information-retrieval tools (weather, traffic, marketplace,
# knowledge base, web, statistics …).
# Skapande: tools that *create* artifacts (podcast, maps, code sandbox).
ROUTE_TOOL_SETS: dict[Route, list[str]] = {
    Route.KUNSKAP: [
        # Internal knowledge
        "search_surfsense_docs",
        "save_memory",
        "recall_memory",
        "search_knowledge_base",
        # Web / browser
        "link_preview",
        "scrape_webpage",
        "public_web_search",
        "tavily_search",
        "libris_search",
        "jobad_links_search",
        # Weather (SMHI)
        "smhi_weather",
        "smhi_vaderprognoser_metfcst",
        "smhi_vaderprognoser_snow1g",
        "smhi_vaderanalyser_mesan2g",
        "smhi_vaderobservationer_metobs",
        "smhi_hydrologi_hydroobs",
        "smhi_hydrologi_pthbv",
        "smhi_oceanografi_ocobs",
        "smhi_brandrisk_fwif",
        "smhi_brandrisk_fwia",
        # Traffic
        "trafiklab_route",
        # Marketplace
        "marketplace_unified_search",
        "marketplace_blocket_search",
        "marketplace_blocket_cars",
        "marketplace_blocket_boats",
        "marketplace_blocket_mc",
        "marketplace_tradera_search",
        "marketplace_compare_prices",
        "marketplace_categories",
        "marketplace_regions",
    ],
    Route.SKAPANDE: [
        "display_image",
        "geoapify_static_map",
        "generate_podcast",
    ],
    Route.KONVERSATION: [],
    Route.JAMFORELSE: [],
}


ROUTE_CITATIONS_ENABLED: dict[Route, bool] = {
    Route.KUNSKAP: True,
    Route.SKAPANDE: False,
    Route.KONVERSATION: False,
    Route.JAMFORELSE: True,
}
