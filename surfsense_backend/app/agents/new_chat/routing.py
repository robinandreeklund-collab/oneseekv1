from enum import Enum


class Route(str, Enum):
    KNOWLEDGE = "knowledge"
    ACTION = "action"
    SMALLTALK = "smalltalk"
    COMPARE = "compare"


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
        "generate_podcast",
        "smhi_weather",
        "trafiklab_route",
        "libris_search",
        "jobad_links_search",
    ],
    Route.SMALLTALK: [],
}


ROUTE_CITATIONS_ENABLED: dict[Route, bool] = {
    Route.KNOWLEDGE: True,
    Route.ACTION: False,
    Route.SMALLTALK: False,
}
