from enum import Enum


class Route(str, Enum):
    KNOWLEDGE = "knowledge"
    ACTION = "action"
    SMALLTALK = "smalltalk"
    COMPARE = "compare"
    STATISTICS = "statistics"


ROUTE_TOOL_SETS: dict[Route, list[str]] = {
    Route.KNOWLEDGE: [
        "search_surfsense_docs",
        "save_memory",
        "recall_memory",
    ],
    Route.ACTION: [
        "search_knowledge_base",
        "link_preview",
        "scrape_webpage",
        "display_image",
        "geoapify_static_map",
        "generate_podcast",
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
        "trafiklab_route",
        "libris_search",
        "jobad_links_search",
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
    Route.SMALLTALK: [],
    Route.STATISTICS: [],
}


ROUTE_CITATIONS_ENABLED: dict[Route, bool] = {
    Route.KNOWLEDGE: True,
    Route.ACTION: False,
    Route.SMALLTALK: False,
    Route.COMPARE: True,
    Route.STATISTICS: True,
}
