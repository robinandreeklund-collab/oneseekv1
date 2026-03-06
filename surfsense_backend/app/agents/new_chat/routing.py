from enum import Enum


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


# ── Domain-to-Route backward compatibility ───────────────────────────
# Maps domain_id (from the new DB-driven hierarchy) to the legacy Route
# enum.  Used during the transition period so that existing code that
# expects a Route value can operate on domain-based intent results.

_DOMAIN_ROUTE_MAP: dict[str, Route] = {
    # Knowledge / information domains → KUNSKAP
    "väder-och-klimat": Route.KUNSKAP,
    "trafik-och-transport": Route.KUNSKAP,
    "ekonomi-och-skatter": Route.KUNSKAP,
    "arbetsmarknad": Route.KUNSKAP,
    "befolkning-och-demografi": Route.KUNSKAP,
    "utbildning": Route.KUNSKAP,
    "näringsliv-och-bolag": Route.KUNSKAP,
    "fastighet-och-mark": Route.KUNSKAP,
    "energi-och-miljö": Route.KUNSKAP,
    "handel-och-marknad": Route.KUNSKAP,
    "politik-och-beslut": Route.KUNSKAP,
    "hälsa-och-vård": Route.KUNSKAP,
    "rättsväsende": Route.KUNSKAP,
    "kunskap": Route.KUNSKAP,
    # Creation domain → SKAPANDE
    "skapande": Route.SKAPANDE,
    # Conversation domain → KONVERSATION
    "konversation": Route.KONVERSATION,
    # Compare domain → JAMFORELSE
    "jämförelse": Route.JAMFORELSE,
}


def domain_to_route(domain_id: str) -> Route:
    """Map a domain_id to a legacy Route enum value.

    Returns ``Route.KUNSKAP`` as fallback for unknown domains.
    """
    normalized = str(domain_id or "").strip().lower()
    return _DOMAIN_ROUTE_MAP.get(normalized, Route.KUNSKAP)


def route_to_domains(route: Route) -> list[str]:
    """Return all domain_ids that map to the given Route.

    Useful for expanding a legacy route hint into domain candidates.
    """
    return [
        domain_id
        for domain_id, mapped_route in _DOMAIN_ROUTE_MAP.items()
        if mapped_route == route
    ]
