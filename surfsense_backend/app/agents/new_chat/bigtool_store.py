from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from langchain_core.tools import BaseTool
from langgraph.store.memory import InMemoryStore

from app.agents.new_chat.statistics_agent import (
    SCB_TOOL_DEFINITIONS,
    build_scb_tool_registry,
)
from app.agents.new_chat.kolada_tools import (
    KOLADA_TOOL_DEFINITIONS,
    build_kolada_tool_registry,
)
from app.agents.new_chat.skolverket_tools import (
    SKOLVERKET_TOOL_DEFINITIONS,
    build_skolverket_tool_registry,
)
from app.agents.new_chat.marketplace_tools import (
    MARKETPLACE_TOOL_DEFINITIONS,
    build_marketplace_tool_registry,
)
from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.geoapify_maps import GEOAPIFY_TOOL_DEFINITIONS
from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS
from app.services.reranker_service import RerankerService
from app.services.cache_control import is_cache_disabled
from app.agents.new_chat.retrieval_feedback import get_global_retrieval_feedback_store
from app.agents.new_chat.sandbox_runtime import sandbox_config_from_runtime_flags
from app.agents.new_chat.tools.registry import (
    build_tools_async,
    get_default_enabled_tools,
)

_SKOLVERKET_DEFINITION_BY_ID = {
    definition.tool_id: definition for definition in SKOLVERKET_TOOL_DEFINITIONS
}
_SKOLVERKET_TOOL_IDS = set(_SKOLVERKET_DEFINITION_BY_ID.keys())


@dataclass(frozen=True)
class ToolIndexEntry:
    tool_id: str
    namespace: tuple[str, ...]
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str
    embedding: list[float] | None = None
    base_path: str | None = None


TOOL_NAMESPACE_OVERRIDES: dict[str, tuple[str, ...]] = {
    "search_knowledge_base": ("tools", "knowledge", "kb"),
    "search_surfsense_docs": ("tools", "knowledge", "docs"),
    "search_tavily": ("tools", "knowledge", "web"),
    "save_memory": ("tools", "knowledge", "memory"),
    "recall_memory": ("tools", "knowledge", "memory"),
    "generate_podcast": ("tools", "action", "media"),
    "display_image": ("tools", "action", "media"),
    "link_preview": ("tools", "action", "web"),
    "scrape_webpage": ("tools", "action", "web"),
    "sandbox_execute": ("tools", "code", "sandbox"),
    "smhi_weather": ("tools", "weather", "smhi"),
    "trafiklab_route": ("tools", "action", "travel"),
    "libris_search": ("tools", "action", "data"),
    "jobad_links_search": ("tools", "action", "data"),
    "write_todos": ("tools", "general", "planning"),
    "reflect_on_progress": ("tools", "general", "reflection"),
    "call_grok": ("tools", "compare", "external"),
    "call_gpt": ("tools", "compare", "external"),
    "call_claude": ("tools", "compare", "external"),
    "call_gemini": ("tools", "compare", "external"),
    "call_deepseek": ("tools", "compare", "external"),
    "call_perplexity": ("tools", "compare", "external"),
    "call_qwen": ("tools", "compare", "external"),
    # Riksdagen tools - all under tools/politik
    "riksdag_dokument": ("tools", "politik", "dokument"),
    "riksdag_ledamoter": ("tools", "politik", "ledamoter"),
    "riksdag_voteringar": ("tools", "politik", "voteringar"),
    "riksdag_anforanden": ("tools", "politik", "anforanden"),
    "riksdag_dokumentstatus": ("tools", "politik", "status"),
    # Riksdagen document sub-tools
    "riksdag_dokument_proposition": ("tools", "politik", "dokument", "proposition"),
    "riksdag_dokument_motion": ("tools", "politik", "dokument", "motion"),
    "riksdag_dokument_betankande": ("tools", "politik", "dokument", "betankande"),
    "riksdag_dokument_interpellation": ("tools", "politik", "dokument", "interpellation"),
    "riksdag_dokument_fraga": ("tools", "politik", "dokument", "fraga"),
    "riksdag_dokument_protokoll": ("tools", "politik", "dokument", "protokoll"),
    "riksdag_dokument_sou": ("tools", "politik", "dokument", "sou"),
    "riksdag_dokument_ds": ("tools", "politik", "dokument", "ds"),
    "riksdag_dokument_dir": ("tools", "politik", "dokument", "dir"),
    "riksdag_dokument_rskr": ("tools", "politik", "dokument", "rskr"),
    "riksdag_dokument_eu": ("tools", "politik", "dokument", "eu"),
    "riksdag_dokument_rir": ("tools", "politik", "dokument", "rir"),
    # Riksdagen anförande sub-tools
    "riksdag_anforanden_debatt": ("tools", "politik", "anforanden", "debatt"),
    "riksdag_anforanden_fragestund": ("tools", "politik", "anforanden", "fragestund"),
    # Riksdagen ledamot sub-tools
    "riksdag_ledamoter_parti": ("tools", "politik", "ledamoter", "parti"),
    "riksdag_ledamoter_valkrets": ("tools", "politik", "ledamoter", "valkrets"),
    # Riksdagen votering sub-tools
    "riksdag_voteringar_resultat": ("tools", "politik", "voteringar", "resultat"),
    # Marketplace tools - all under tools/marketplace
    "marketplace_unified_search": ("tools", "marketplace", "search"),
    "marketplace_blocket_search": ("tools", "marketplace", "search"),
    "marketplace_blocket_cars": ("tools", "marketplace", "vehicles"),
    "marketplace_blocket_boats": ("tools", "marketplace", "vehicles"),
    "marketplace_blocket_mc": ("tools", "marketplace", "vehicles"),
    "marketplace_tradera_search": ("tools", "marketplace", "search"),
    "marketplace_compare_prices": ("tools", "marketplace", "compare"),
    "marketplace_categories": ("tools", "marketplace", "reference"),
    "marketplace_regions": ("tools", "marketplace", "reference"),
}

TOOL_KEYWORDS: dict[str, list[str]] = {
    "search_knowledge_base": ["sok", "search", "note", "calendar", "knowledge"],
    "search_surfsense_docs": ["surfsense", "docs", "manual", "guide"],
    "search_tavily": ["nyheter", "webb", "news", "tavily", "extern"],
    "generate_podcast": ["podcast", "podd", "audio", "ljud"],
    "display_image": ["image", "bild", "illustration"],
    "geoapify_static_map": [
        "karta",
        "kartbild",
        "map",
        "geoapify",
        "plats",
        "adress",
        "koordinat",
    ],
    "link_preview": ["lank", "link", "preview", "url"],
    "scrape_webpage": ["scrape", "skrapa", "webb", "article"],
    "sandbox_execute": [
        "sandbox",
        "docker",
        "shell",
        "bash",
        "python",
        "script",
        "kod",
        "code",
        "terminal",
    ],
    "smhi_weather": [
        "weather",
        "vader",
        "vadret",
        "väder",
        "vädret",
        "prognos",
        "forecast",
        "smhi",
        "temperatur",
    ],
    "trafiklab_route": [
        "trafik",
        "resa",
        "route",
        "kollektivtrafik",
        "tåg",
        "tag",
        "train",
        "avgår",
        "departure",
        "tidtabell",
        "nasta",
        "nästa",
    ],
    "libris_search": ["libris", "bok", "bibliotek"],
    "jobad_links_search": ["jobb", "job", "annons", "arbetsformedlingen"],
    "write_todos": ["plan", "todo", "planera", "steg"],
    "reflect_on_progress": ["reflektion", "sammanfatta", "status"],
    "call_grok": ["grok", "xai", "modell"],
    "call_gpt": ["gpt", "chatgpt", "openai", "modell"],
    "call_claude": ["claude", "anthropic", "modell"],
    "call_gemini": ["gemini", "google", "modell"],
    "call_deepseek": ["deepseek", "modell"],
    "call_perplexity": ["perplexity", "modell"],
    "call_qwen": ["qwen", "alibaba", "modell"],
    # Riksdagen tools keywords
    "riksdag_dokument": ["riksdag", "dokument", "riksdagen", "söka", "sök"],
    "riksdag_ledamoter": ["ledamot", "ledamöter", "riksdagsledamot", "politiker"],
    "riksdag_voteringar": ["votering", "voteringar", "omröstning", "röstning"],
    "riksdag_anforanden": ["anförande", "anföranden", "tal", "debatt", "kammare"],
    "riksdag_dokumentstatus": ["status", "ärendehistorik", "handläggning", "dokumentstatus"],
    "riksdag_dokument_proposition": ["proposition", "prop", "regeringen", "förslag"],
    "riksdag_dokument_motion": ["motion", "mot", "förslag", "ledamot"],
    "riksdag_dokument_betankande": ["betänkande", "bet", "utskott", "beslutsförslag"],
    "riksdag_dokument_interpellation": ["interpellation", "ip", "fråga", "minister"],
    "riksdag_dokument_fraga": ["fråga", "fr", "frs", "skriftlig"],
    "riksdag_dokument_protokoll": ["protokoll", "prot", "kammarprotokoll", "debatt"],
    "riksdag_dokument_sou": ["sou", "utredning", "offentlig"],
    "riksdag_dokument_ds": ["ds", "departement", "skrivelse"],
    "riksdag_dokument_dir": ["direktiv", "dir", "kommitté"],
    "riksdag_dokument_rskr": ["riksdagsskrivelse", "rskr", "beslut"],
    "riksdag_dokument_eu": ["eu", "kom", "europa", "europeiska"],
    "riksdag_dokument_rir": ["rir", "riksrevisionen", "granskning", "rapport"],
    "riksdag_anforanden_debatt": ["debatt", "allmän", "budget", "utrikes", "anförande"],
    "riksdag_anforanden_fragestund": ["frågestund", "statsråd", "fråga"],
    "riksdag_ledamoter_parti": ["parti", "socialdemokraterna", "moderaterna", "sverigedemokraterna"],
    "riksdag_ledamoter_valkrets": ["valkrets", "län", "stockholms", "skåne", "västra"],
    "riksdag_voteringar_resultat": ["resultat", "röstresultat", "detaljerat", "parti"],
    # Kolada tools keywords
    "kolada_aldreomsorg": ["aldreomsorg", "äldreomsorg", "aldrevard", "äldrevård", "hemtjanst", "hemtjänst", "sarskilt", "särskilt", "boende", "alderdomshem", "älderdomshem", "kolada"],
    "kolada_lss": ["lss", "funktionshinder", "funktionsnedsattning", "funktionsnedsättning", "personlig", "assistans", "boende", "sarskild", "särskild", "service", "kolada"],
    "kolada_ifo": ["ifo", "individomsorg", "familjeomsorg", "ekonomiskt", "bistand", "bistånd", "socialbidrag", "familjehem", "missbruk", "beroende", "kolada"],
    "kolada_barn_unga": ["barn", "unga", "ungdom", "placering", "oppenvard", "öppenvård", "barnvard", "barnvård", "ungdomsvard", "ungdomsvård", "kolada"],
    "kolada_forskola": ["forskola", "förskola", "dagis", "barn", "barnomsorg", "pedagog", "forskolelarare", "förskolelärare", "kolada"],
    "kolada_grundskola": ["grundskola", "skola", "elev", "larare", "lärare", "behorighet", "behörighet", "betyg", "resultat", "kolada"],
    "kolada_gymnasieskola": ["gymnasieskola", "gymnasium", "gymnasie", "elev", "examen", "behorighet", "behörighet", "genomstromning", "genomströmning", "kolada"],
    "kolada_halsa": ["halsa", "hälsa", "vard", "vård", "sjukvard", "sjukvård", "lakare", "läkare", "primarvard", "primärvård", "sjukhus", "kolada"],
    "kolada_ekonomi": ["ekonomi", "skattesats", "kostnad", "intakt", "intäkt", "budget", "kommunal", "finansiell", "kolada"],
    "kolada_miljo": ["miljo", "miljö", "avfall", "atervinning", "återvinning", "koldioxid", "utsläpp", "utslapp", "energi", "klimat", "kolada"],
    "kolada_boende": ["boende", "bostad", "bostader", "byggande", "nybyggnation", "bostadsbestand", "bostadsbestånd", "hyra", "bostadsko", "bostadskö", "kolada"],
    "kolada_sammanfattning": ["sammanfattning", "oversikt", "översikt", "allmant", "allmänt", "nyckeltal", "kommun", "kommundata", "kolada"],
    "kolada_kultur": ["kultur", "bibliotek", "museum", "teater", "fritid", "idrottsanlaggning", "idrottsanläggning", "kulturhus", "kolada"],
    "kolada_arbetsmarknad": ["arbetsmarknad", "sysselsattning", "sysselsättning", "arbetsloshet", "arbetslöshet", "arbete", "jobb", "arbetsmarknadsatgard", "arbetsmarknadsåtgärd", "kolada"],
    "kolada_demokrati": ["demokrati", "val", "valdeltagande", "medborgarengagemang", "medborgarservice", "kommunikation", "deltagande", "kolada"],
    # Marketplace tools keywords
    "marketplace_unified_search": ["marknadsplats", "sök", "köp", "sälj", "begagnat", "annons"],
    "marketplace_blocket_search": ["blocket", "sök", "köp", "sälj", "begagnat", "annons"],
    "marketplace_blocket_cars": ["bilar", "bil", "fordon", "volvo", "bmw", "toyota", "begagnad"],
    "marketplace_blocket_boats": ["båtar", "båt", "segelbåt", "motorbåt", "sjö"],
    "marketplace_blocket_mc": ["motorcykel", "mc", "moped", "cross", "harley", "yamaha"],
    "marketplace_tradera_search": ["tradera", "auktion", "budgivning", "samlarobjekt", "antikt"],
    "marketplace_compare_prices": ["jämför", "prisjämförelse", "billigast", "pris", "compare"],
    "marketplace_categories": ["kategorier", "kategori", "ämnesområde", "avdelning"],
    "marketplace_regions": ["regioner", "platser", "orter", "län", "städer"],
}

@dataclass(frozen=True)
class ToolRetrievalTuning:
    name_match_weight: float = 5.0
    keyword_weight: float = 3.0
    description_token_weight: float = 1.0
    example_query_weight: float = 2.0
    namespace_boost: float = 3.0
    embedding_weight: float = 4.0
    rerank_candidates: int = 24
    retrieval_feedback_db_enabled: bool = False


DEFAULT_TOOL_RETRIEVAL_TUNING = ToolRetrievalTuning()
_TOOL_EMBED_CACHE: dict[str, tuple[str, list[float]]] = {}
_TOOL_RERANK_TRACE: dict[tuple[str, str], list[dict[str, Any]]] = {}


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    cleaned = (
        lowered.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
    )
    return "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in cleaned).strip()


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_text(text)
    return [token for token in normalized.split() if token]


def _namespace_for_scb_tool(tool_id: str) -> tuple[str, ...]:
    parts = tool_id.split("_")
    if len(parts) >= 3:
        return ("tools", "statistics", "scb", parts[1])
    return ("tools", "statistics", "scb")


def _namespace_for_kolada_tool(tool_id: str) -> tuple[str, ...]:
    """Map Kolada tools to namespaces based on category."""
    # Find the tool definition to get its category
    for definition in KOLADA_TOOL_DEFINITIONS:
        if definition.tool_id == tool_id:
            category = definition.category
            if category == "omsorg":
                return ("tools", "statistics", "kolada", "omsorg")
            elif category == "skola":
                return ("tools", "statistics", "kolada", "skola")
            elif category == "halsa":
                return ("tools", "statistics", "kolada", "halsa")
            elif category == "ekonomi":
                return ("tools", "statistics", "kolada", "ekonomi")
            elif category == "miljo":
                return ("tools", "statistics", "kolada", "miljo")
            elif category == "boende":
                return ("tools", "statistics", "kolada", "boende")
            elif category == "ovrig":
                # Extract subcategory from tool_id (e.g., kolada_kultur -> kultur)
                parts = tool_id.split("_")
                if len(parts) >= 2:
                    return ("tools", "statistics", "kolada", parts[1])
                return ("tools", "statistics", "kolada", "ovrig")
    
    # Default fallback
    return ("tools", "statistics", "kolada")


def _namespace_for_skolverket_tool(tool_id: str) -> tuple[str, ...]:
    definition = _SKOLVERKET_DEFINITION_BY_ID.get(tool_id)
    if definition:
        category = str(definition.category or "").strip().lower()
        if category == "statistics":
            return ("tools", "statistics", "skolverket")
        if category == "knowledge":
            return ("tools", "knowledge", "skolverket")
        if category == "general":
            return ("tools", "general", "skolverket")
        return ("tools", "knowledge", "skolverket")
    return ("tools", "knowledge", "skolverket")


def _namespace_for_bolagsverket_tool(tool_id: str) -> tuple[str, ...]:
    parts = tool_id.split("_")
    if len(parts) >= 2:
        return ("tools", "bolag", f"bolagsverket_{parts[1]}")
    return ("tools", "bolag")


def _namespace_for_trafikverket_tool(tool_id: str) -> tuple[str, ...]:
    if _is_weather_tool(tool_id):
        return ("tools", "weather", "trafikverket_vader")
    parts = tool_id.split("_")
    if len(parts) >= 2:
        return ("tools", "trafik", f"trafikverket_{parts[1]}")
    return ("tools", "trafik")


def _namespace_for_geoapify_tool(tool_id: str) -> tuple[str, ...]:
    parts = tool_id.split("_")
    if len(parts) >= 2:
        return ("tools", "kartor", f"geoapify_{parts[1]}")
    return ("tools", "kartor")


def _is_weather_tool(tool_id: str) -> bool:
    normalized = str(tool_id or "").strip().lower()
    if not normalized:
        return False
    if normalized == "smhi_weather":
        return True
    if normalized.startswith("trafikverket_vader_"):
        return True
    return False


def _namespace_for_weather_tool(tool_id: str) -> tuple[str, ...]:
    normalized = str(tool_id or "").strip().lower()
    if normalized == "smhi_weather":
        return ("tools", "weather", "smhi")
    if normalized.startswith("trafikverket_vader_"):
        return ("tools", "weather", "trafikverket_vader")
    return ("tools", "weather")


def namespace_for_tool(tool_id: str) -> tuple[str, ...]:
    if _is_weather_tool(tool_id):
        return _namespace_for_weather_tool(tool_id)
    if tool_id.startswith("scb_"):
        return _namespace_for_scb_tool(tool_id)
    if tool_id.startswith("kolada_"):
        return _namespace_for_kolada_tool(tool_id)
    if tool_id in _SKOLVERKET_TOOL_IDS:
        return _namespace_for_skolverket_tool(tool_id)
    if tool_id.startswith("bolagsverket_"):
        return _namespace_for_bolagsverket_tool(tool_id)
    if tool_id.startswith("trafikverket_"):
        return _namespace_for_trafikverket_tool(tool_id)
    if tool_id.startswith("geoapify_"):
        return _namespace_for_geoapify_tool(tool_id)
    return TOOL_NAMESPACE_OVERRIDES.get(tool_id, ("tools", "general"))


def _tool_metadata(tool: BaseTool) -> dict[str, Any]:
    metadata = getattr(tool, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _is_mcp_tool(tool: BaseTool) -> bool:
    metadata = _tool_metadata(tool)
    return bool(metadata.get("mcp_transport"))


_MCP_KEYWORD_STOPWORDS = {
    "tool",
    "tools",
    "get",
    "search",
    "list",
    "fetch",
    "call",
    "data",
    "api",
    "mcp",
    "for",
    "the",
    "with",
    "and",
}
_MCP_SKOLVERKET_KNOWLEDGE_HINTS = (
    "skolverket",
    "syllabus",
    "curriculum",
    "laroplan",
    "läroplan",
    "amnesplan",
    "ämnesplan",
    "kursplan",
    "course",
    "subject",
    "program",
    "utbildning",
    "education",
    "skolenhet",
    "school unit",
    "komvux",
    "vuxenutbildning",
)
_MCP_SKOLVERKET_STATISTICS_HINTS = (
    "statistik",
    "statistics",
    "salsa",
    "count",
    "andel",
    "proportion",
)


def _contains_any_marker(text: str, markers: Iterable[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(marker).lower() in lowered for marker in markers if str(marker).strip())


def _namespace_for_mcp_tool(
    tool_id: str,
    *,
    metadata: dict[str, Any],
    description: str,
) -> tuple[str, ...]:
    connector_name = str(metadata.get("mcp_connector_name") or "")
    connector_url = str(metadata.get("mcp_url") or "")
    normalized_blob = " ".join(
        [
            _normalize_text(tool_id.replace("_", " ")),
            _normalize_text(description),
            _normalize_text(connector_name),
            _normalize_text(connector_url),
        ]
    )

    if _contains_any_marker(
        normalized_blob,
        ("skolverket", "skolverket mcp", "skolverket api"),
    ):
        if _contains_any_marker(normalized_blob, _MCP_SKOLVERKET_STATISTICS_HINTS):
            return ("tools", "statistics", "skolverket")
        if _contains_any_marker(normalized_blob, _MCP_SKOLVERKET_KNOWLEDGE_HINTS):
            return ("tools", "knowledge", "skolverket")
        return ("tools", "knowledge", "skolverket")

    if _contains_any_marker(normalized_blob, ("statistics", "statistik", "timeseries")):
        return ("tools", "statistics", "mcp")
    if _contains_any_marker(normalized_blob, ("weather", "väder", "vader")):
        return ("tools", "weather", "mcp")
    if _contains_any_marker(normalized_blob, ("traffic", "trafik", "route", "resa")):
        return ("tools", "action", "mcp")
    return ("tools", "knowledge", "mcp")


def _keywords_from_text(text: str, *, max_keywords: int = 18) -> list[str]:
    results: list[str] = []
    for token in _tokenize(text):
        if len(token) < 3:
            continue
        if token in _MCP_KEYWORD_STOPWORDS:
            continue
        results.append(token)
        if len(results) >= max(1, int(max_keywords)):
            break
    return results


def _unique_keywords(
    keywords: Iterable[str],
    *,
    max_keywords: int = 20,
) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for raw in keywords:
        token = str(raw or "").strip()
        if not token:
            continue
        normalized = _normalize_text(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(token)
        if len(results) >= max(1, int(max_keywords)):
            break
    return results


def _keywords_for_mcp_tool(
    tool_id: str,
    *,
    metadata: dict[str, Any],
    description: str,
) -> list[str]:
    connector_name = str(metadata.get("mcp_connector_name") or "")
    connector_url = str(metadata.get("mcp_url") or "")
    generated: list[str] = []
    generated.extend(_keywords_from_text(tool_id.replace("_", " ")))
    generated.extend(_keywords_from_text(description))
    generated.extend(_keywords_from_text(connector_name))
    generated.extend(_keywords_from_text(connector_url))

    if _contains_any_marker(
        f"{tool_id} {description} {connector_name} {connector_url}",
        ("skolverket",),
    ):
        generated.extend(
            [
                "skolverket",
                "skola",
                "kurs",
                "amne",
                "ämne",
                "laroplan",
                "läroplan",
                "utbildning",
                "komvux",
                "gymnasium",
                "vuxenutbildning",
            ]
        )

    return _unique_keywords(generated, max_keywords=24)


def _category_for_namespace(namespace: tuple[str, ...]) -> str:
    if len(namespace) >= 2 and namespace[1]:
        return str(namespace[1])
    return "general"


def _match_namespace(entry_namespace: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    if not prefix:
        return False
    if len(entry_namespace) < len(prefix):
        return False
    return entry_namespace[: len(prefix)] == prefix


def _bounded_float(
    value: Any,
    *,
    default: float,
    min_value: float,
    max_value: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _bounded_int(
    value: Any,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def normalize_retrieval_tuning(
    tuning: ToolRetrievalTuning | dict[str, Any] | None,
) -> ToolRetrievalTuning:
    if isinstance(tuning, ToolRetrievalTuning):
        return tuning
    payload = tuning or {}
    return ToolRetrievalTuning(
        name_match_weight=_bounded_float(
            payload.get("name_match_weight"),
            default=DEFAULT_TOOL_RETRIEVAL_TUNING.name_match_weight,
            min_value=0.0,
            max_value=25.0,
        ),
        keyword_weight=_bounded_float(
            payload.get("keyword_weight"),
            default=DEFAULT_TOOL_RETRIEVAL_TUNING.keyword_weight,
            min_value=0.0,
            max_value=25.0,
        ),
        description_token_weight=_bounded_float(
            payload.get("description_token_weight"),
            default=DEFAULT_TOOL_RETRIEVAL_TUNING.description_token_weight,
            min_value=0.0,
            max_value=10.0,
        ),
        example_query_weight=_bounded_float(
            payload.get("example_query_weight"),
            default=DEFAULT_TOOL_RETRIEVAL_TUNING.example_query_weight,
            min_value=0.0,
            max_value=10.0,
        ),
        namespace_boost=_bounded_float(
            payload.get("namespace_boost"),
            default=DEFAULT_TOOL_RETRIEVAL_TUNING.namespace_boost,
            min_value=0.0,
            max_value=10.0,
        ),
        embedding_weight=_bounded_float(
            payload.get("embedding_weight"),
            default=DEFAULT_TOOL_RETRIEVAL_TUNING.embedding_weight,
            min_value=0.0,
            max_value=25.0,
        ),
        rerank_candidates=_bounded_int(
            payload.get("rerank_candidates"),
            default=DEFAULT_TOOL_RETRIEVAL_TUNING.rerank_candidates,
            min_value=1,
            max_value=100,
        ),
        retrieval_feedback_db_enabled=_coerce_bool(
            payload.get("retrieval_feedback_db_enabled"),
            default=DEFAULT_TOOL_RETRIEVAL_TUNING.retrieval_feedback_db_enabled,
        ),
    )


def _score_entry_components(
    entry: ToolIndexEntry,
    query_tokens: set[str],
    query_norm: str,
    tuning: ToolRetrievalTuning,
) -> dict[str, Any]:
    name_norm = _normalize_text(entry.name)
    desc_norm = _normalize_text(entry.description)
    name_match_hits = 1 if name_norm and name_norm in query_norm else 0
    keyword_hits = 0
    for keyword in entry.keywords:
        if _normalize_text(keyword) in query_norm:
            keyword_hits += 1
    description_hits = 0
    for token in query_tokens:
        if token and token in desc_norm:
            description_hits += 1
    example_hits = 0
    for example in entry.example_queries:
        if _normalize_text(example) in query_norm:
            example_hits += 1
    lexical_score = (
        (name_match_hits * tuning.name_match_weight)
        + (keyword_hits * tuning.keyword_weight)
        + (description_hits * tuning.description_token_weight)
        + (example_hits * tuning.example_query_weight)
    )
    return {
        "name_match_hits": int(name_match_hits),
        "keyword_hits": int(keyword_hits),
        "description_hits": int(description_hits),
        "example_hits": int(example_hits),
        "lexical_score": float(lexical_score),
    }


def _build_rerank_text(entry: ToolIndexEntry) -> str:
    parts: list[str] = []
    if entry.name:
        parts.append(entry.name)
    if entry.description:
        parts.append(entry.description)
    if entry.keywords:
        parts.append("Keywords: " + ", ".join(entry.keywords))
    if entry.example_queries:
        parts.append("Examples: " + " | ".join(entry.example_queries))
    return "\n".join(part for part in parts if part)


def _normalize_vector(vector: Any) -> list[float] | None:
    if vector is None:
        return None
    if isinstance(vector, list):
        return vector
    try:
        return [float(value) for value in vector]
    except Exception:
        return None


def _get_embedding_for_tool(tool_id: str, text: str) -> list[float] | None:
    if not text:
        return None
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not is_cache_disabled() and tool_id in _TOOL_EMBED_CACHE:
        cached_text_hash, cached_embedding = _TOOL_EMBED_CACHE[tool_id]
        if cached_text_hash == text_hash:
            return cached_embedding
    try:
        from app.config import config
    except Exception:
        return None
    try:
        embedding = config.embedding_model_instance.embed(text)
    except Exception:
        return None
    normalized = _normalize_vector(embedding)
    if normalized is None:
        return None
    if not is_cache_disabled():
        _TOOL_EMBED_CACHE[tool_id] = (text_hash, normalized)
    return normalized


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for a, b in zip(left, right):
        dot += a * b
        norm_left += a * a
        norm_right += b * b
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / ((norm_left**0.5) * (norm_right**0.5))


def _rerank_tool_candidates(
    query: str,
    *,
    candidate_ids: list[str],
    tool_index_by_id: dict[str, ToolIndexEntry],
    scores_by_id: dict[str, float],
) -> tuple[list[str], dict[str, float]]:
    if len(candidate_ids) <= 1:
        return candidate_ids, {}
    reranker = RerankerService.get_reranker_instance()
    if not reranker:
        return candidate_ids, {}
    documents: list[dict[str, Any]] = []
    for tool_id in candidate_ids:
        entry = tool_index_by_id.get(tool_id)
        if not entry:
            continue
        content = _build_rerank_text(entry) or entry.name or tool_id
        documents.append(
            {
                "document_id": tool_id,
                "content": content,
                "score": float(scores_by_id.get(tool_id, 0)),
                "document": {
                    "id": tool_id,
                    "title": entry.name or tool_id,
                    "document_type": "TOOL",
                },
            }
        )
    if not documents:
        return candidate_ids, {}
    reranked = reranker.rerank_documents(query, documents)
    if not reranked:
        return candidate_ids, {}
    reranked_ids = [
        str(doc.get("document_id"))
        for doc in reranked
        if doc.get("document_id")
    ]
    rerank_scores = {
        str(doc.get("document_id")): float(doc.get("score") or 0.0)
        for doc in reranked
        if doc.get("document_id")
    }
    seen: set[str] = set()
    ordered: list[str] = []
    for tool_id in reranked_ids + candidate_ids:
        if tool_id and tool_id not in seen:
            ordered.append(tool_id)
            seen.add(tool_id)
    return ordered, rerank_scores


def record_tool_rerank(
    trace_key: str | None,
    *,
    query_norm: str,
    ranked_tools: list[dict[str, Any]],
) -> None:
    if is_cache_disabled():
        return
    if not trace_key or not query_norm:
        return
    _TOOL_RERANK_TRACE[(str(trace_key), query_norm)] = ranked_tools


def clear_tool_caches() -> None:
    _TOOL_EMBED_CACHE.clear()
    _TOOL_RERANK_TRACE.clear()


def get_tool_rerank_trace(
    trace_key: str | None,
    *,
    query: str,
) -> list[dict[str, Any]] | None:
    if not trace_key or not query:
        return None
    query_norm = _normalize_text(query)
    return _TOOL_RERANK_TRACE.get((str(trace_key), query_norm))


def _run_smart_retrieval(
    query: str,
    *,
    tool_index: list[ToolIndexEntry],
    primary_namespaces: list[tuple[str, ...]],
    fallback_namespaces: list[tuple[str, ...]] | None = None,
    limit: int = 2,
    trace_key: str | None = None,
    tuning: ToolRetrievalTuning | dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    normalized_tuning = normalize_retrieval_tuning(tuning)
    retrieval_feedback_store = get_global_retrieval_feedback_store()
    query_norm = _normalize_text(query)
    query_tokens = set(_tokenize(query_norm))
    fallback_namespaces = fallback_namespaces or []
    query_embedding: list[float] | None = None
    if query:
        try:
            from app.config import config

            query_embedding = _normalize_vector(
                config.embedding_model_instance.embed(query)
            )
        except Exception:
            query_embedding = None

    primary_scored: list[tuple[str, float]] = []
    fallback_scored: list[tuple[str, float]] = []
    breakdown_by_id: dict[str, dict[str, Any]] = {}

    for entry in tool_index:
        breakdown = _score_entry_components(
            entry,
            query_tokens,
            query_norm,
            normalized_tuning,
        )
        semantic_score = 0.0
        if query_embedding and entry.embedding:
            semantic_score = _cosine_similarity(query_embedding, entry.embedding)
        embedding_weighted = semantic_score * normalized_tuning.embedding_weight
        is_primary = any(
            _match_namespace(entry.namespace, prefix) for prefix in primary_namespaces
        )
        is_fallback = any(
            _match_namespace(entry.namespace, prefix) for prefix in fallback_namespaces
        )
        namespace_bonus = normalized_tuning.namespace_boost if is_primary else 0.0
        retrieval_feedback_boost = retrieval_feedback_store.get_boost(
            tool_id=entry.tool_id,
            query=query_norm or query,
        )
        pre_rerank_score = (
            breakdown["lexical_score"]
            + embedding_weighted
            + namespace_bonus
            + retrieval_feedback_boost
        )
        breakdown_by_id[entry.tool_id] = {
            "tool_id": entry.tool_id,
            "name": entry.name,
            "category": entry.category,
            "name_match_hits": breakdown["name_match_hits"],
            "keyword_hits": breakdown["keyword_hits"],
            "description_hits": breakdown["description_hits"],
            "example_hits": breakdown["example_hits"],
            "lexical_score": float(breakdown["lexical_score"]),
            "embedding_score_raw": float(semantic_score),
            "embedding_score_weighted": float(embedding_weighted),
            "namespace_bonus": float(namespace_bonus),
            "retrieval_feedback_boost": float(retrieval_feedback_boost),
            "pre_rerank_score": float(pre_rerank_score),
            "namespace_scope": "primary" if is_primary else ("fallback" if is_fallback else "none"),
        }
        if is_primary:
            primary_scored.append((entry.tool_id, pre_rerank_score))
        elif is_fallback:
            fallback_scored.append((entry.tool_id, pre_rerank_score))

    primary_scored.sort(key=lambda item: item[1], reverse=True)
    fallback_scored.sort(key=lambda item: item[1], reverse=True)

    tool_index_by_id = {entry.tool_id: entry for entry in tool_index}
    scores_by_id = {tool_id: score for tool_id, score in primary_scored}
    scores_by_id.update({tool_id: score for tool_id, score in fallback_scored})

    candidate_ids: list[str] = []
    if primary_scored and primary_scored[0][1] > 0:
        candidate_ids = [
            tool_id
            for tool_id, _ in primary_scored[: normalized_tuning.rerank_candidates]
        ]
    elif fallback_scored and fallback_scored[0][1] > 0:
        candidate_ids = [
            tool_id
            for tool_id, _ in fallback_scored[: normalized_tuning.rerank_candidates]
        ]
    elif primary_scored:
        candidate_ids = [
            tool_id
            for tool_id, _ in primary_scored[: normalized_tuning.rerank_candidates]
        ]
    else:
        candidate_ids = [
            tool_id
            for tool_id, _ in fallback_scored[: normalized_tuning.rerank_candidates]
        ]

    reranked_ids, rerank_scores = _rerank_tool_candidates(
        query,
        candidate_ids=candidate_ids,
        tool_index_by_id=tool_index_by_id,
        scores_by_id=scores_by_id,
    )

    ranked_tools: list[dict[str, Any]] = []
    for rank_index, tool_id in enumerate(reranked_ids):
        entry = tool_index_by_id.get(tool_id)
        breakdown = breakdown_by_id.get(tool_id, {})
        pre_score = float(
            breakdown.get("pre_rerank_score", scores_by_id.get(tool_id, 0.0))
        )
        rerank_score = rerank_scores.get(tool_id)
        ranked_tools.append(
            {
                "tool_id": tool_id,
                "name": entry.name if entry else tool_id,
                "category": entry.category if entry else None,
                "rank": rank_index + 1,
                "rerank_score": float(rerank_score)
                if rerank_score is not None
                else None,
                "score": pre_score,
                "pre_rerank_score": pre_score,
                "name_match_hits": int(breakdown.get("name_match_hits", 0)),
                "keyword_hits": int(breakdown.get("keyword_hits", 0)),
                "description_hits": int(breakdown.get("description_hits", 0)),
                "example_hits": int(breakdown.get("example_hits", 0)),
                "lexical_score": float(breakdown.get("lexical_score", 0.0)),
                "embedding_score_raw": float(breakdown.get("embedding_score_raw", 0.0)),
                "embedding_score_weighted": float(
                    breakdown.get("embedding_score_weighted", 0.0)
                ),
                "namespace_bonus": float(breakdown.get("namespace_bonus", 0.0)),
                "retrieval_feedback_boost": float(
                    breakdown.get("retrieval_feedback_boost", 0.0)
                ),
                "namespace_scope": breakdown.get("namespace_scope"),
            }
        )

    if trace_key and candidate_ids:
        record_tool_rerank(trace_key, query_norm=query_norm, ranked_tools=ranked_tools)
    return reranked_ids[:limit], ranked_tools


def smart_retrieve_tools(
    query: str,
    *,
    tool_index: list[ToolIndexEntry],
    primary_namespaces: list[tuple[str, ...]],
    fallback_namespaces: list[tuple[str, ...]] | None = None,
    limit: int = 2,
    trace_key: str | None = None,
    tuning: ToolRetrievalTuning | dict[str, Any] | None = None,
) -> list[str]:
    tool_ids, _ranked = _run_smart_retrieval(
        query,
        tool_index=tool_index,
        primary_namespaces=primary_namespaces,
        fallback_namespaces=fallback_namespaces,
        limit=limit,
        trace_key=trace_key,
        tuning=tuning,
    )
    return tool_ids


def smart_retrieve_tools_with_breakdown(
    query: str,
    *,
    tool_index: list[ToolIndexEntry],
    primary_namespaces: list[tuple[str, ...]],
    fallback_namespaces: list[tuple[str, ...]] | None = None,
    limit: int = 2,
    trace_key: str | None = None,
    tuning: ToolRetrievalTuning | dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    return _run_smart_retrieval(
        query,
        tool_index=tool_index,
        primary_namespaces=primary_namespaces,
        fallback_namespaces=fallback_namespaces,
        limit=limit,
        trace_key=trace_key,
        tuning=tuning,
    )


def make_smart_retriever(
    *,
    tool_index: list[ToolIndexEntry],
    primary_namespaces: list[tuple[str, ...]],
    fallback_namespaces: list[tuple[str, ...]],
    limit: int = 2,
    trace_key: str | None = None,
    retrieval_tuning: ToolRetrievalTuning | dict[str, Any] | None = None,
):
    def retrieve_tools(query: str) -> list[str]:
        """Select relevant tool IDs using namespace-aware scoring."""
        return smart_retrieve_tools(
            query,
            tool_index=tool_index,
            primary_namespaces=primary_namespaces,
            fallback_namespaces=fallback_namespaces,
            limit=limit,
            trace_key=trace_key,
            tuning=retrieval_tuning,
        )

    async def aretrieve_tools(query: str) -> list[str]:
        """Async wrapper for namespace-aware tool selection."""
        return retrieve_tools(query)

    return retrieve_tools, aretrieve_tools


async def build_global_tool_registry(
    *,
    dependencies: dict[str, Any],
    include_mcp_tools: bool = True,
) -> dict[str, BaseTool]:
    enabled_tools = list(get_default_enabled_tools())
    runtime_hitl = dependencies.get("runtime_hitl")
    sandbox_config = sandbox_config_from_runtime_flags(
        runtime_hitl if isinstance(runtime_hitl, dict) else None
    )
    if sandbox_config.enabled and "sandbox_execute" not in enabled_tools:
        enabled_tools.append("sandbox_execute")
    for extra in ("write_todos", "reflect_on_progress"):
        if extra not in enabled_tools:
            enabled_tools.append(extra)
    tools = await build_tools_async(
        dependencies,
        enabled_tools=enabled_tools,
        include_mcp_tools=include_mcp_tools,
    )
    registry: dict[str, BaseTool] = {tool.name: tool for tool in tools}
    scb_registry = build_scb_tool_registry(
        connector_service=dependencies["connector_service"],
        search_space_id=dependencies["search_space_id"],
        user_id=dependencies.get("user_id"),
        thread_id=dependencies.get("thread_id"),
    )
    registry.update(scb_registry)
    kolada_registry = build_kolada_tool_registry(
        connector_service=dependencies["connector_service"],
        search_space_id=dependencies["search_space_id"],
        user_id=dependencies.get("user_id"),
        thread_id=dependencies.get("thread_id"),
    )
    registry.update(kolada_registry)
    skolverket_registry = build_skolverket_tool_registry(
        connector_service=dependencies["connector_service"],
        search_space_id=dependencies["search_space_id"],
        user_id=dependencies.get("user_id"),
        thread_id=dependencies.get("thread_id"),
    )
    registry.update(skolverket_registry)
    marketplace_registry = build_marketplace_tool_registry(
        connector_service=dependencies["connector_service"],
        search_space_id=dependencies["search_space_id"],
        user_id=dependencies.get("user_id"),
        thread_id=dependencies.get("thread_id"),
    )
    registry.update(marketplace_registry)
    return registry


def build_tool_index(
    tool_registry: dict[str, BaseTool],
    *,
    metadata_overrides: dict[str, dict[str, Any]] | None = None,
) -> list[ToolIndexEntry]:
    scb_by_id = {definition.tool_id: definition for definition in SCB_TOOL_DEFINITIONS}
    kolada_by_id = {definition.tool_id: definition for definition in KOLADA_TOOL_DEFINITIONS}
    skolverket_by_id = {
        definition.tool_id: definition for definition in SKOLVERKET_TOOL_DEFINITIONS
    }
    bolagsverket_by_id = {
        definition.tool_id: definition for definition in BOLAGSVERKET_TOOL_DEFINITIONS
    }
    trafikverket_by_id = {
        definition.tool_id: definition for definition in TRAFIKVERKET_TOOL_DEFINITIONS
    }
    geoapify_by_id = {
        definition.tool_id: definition for definition in GEOAPIFY_TOOL_DEFINITIONS
    }
    riksdagen_by_id = {
        definition.tool_id: definition for definition in RIKSDAGEN_TOOL_DEFINITIONS
    }
    marketplace_by_id = {
        definition.tool_id: definition for definition in MARKETPLACE_TOOL_DEFINITIONS
    }
    entries: list[ToolIndexEntry] = []

    for tool_id, tool in tool_registry.items():
        namespace = namespace_for_tool(tool_id)
        description = getattr(tool, "description", "") or ""
        keywords = TOOL_KEYWORDS.get(tool_id, [])
        example_queries: list[str] = []
        category = "weather" if _is_weather_tool(tool_id) else "general"
        base_path: str | None = None
        name = getattr(tool, "name", tool_id)
        metadata = _tool_metadata(tool)
        if tool_id in scb_by_id:
            definition = scb_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = "statistics"
            base_path = definition.base_path
        if tool_id in kolada_by_id:
            definition = kolada_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = "statistics"
            # Use operating_area as base_path for Kolada tools, default to empty string if None
            base_path = definition.operating_area if definition.operating_area else ""
        if tool_id in skolverket_by_id:
            definition = skolverket_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = str(definition.category or "knowledge")
            base_path = "https://api.skolverket.se"
        if tool_id in bolagsverket_by_id:
            definition = bolagsverket_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = definition.category
            base_path = definition.base_path
        if tool_id in trafikverket_by_id:
            definition = trafikverket_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = definition.category
            base_path = definition.base_path
        if tool_id in geoapify_by_id:
            definition = geoapify_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = definition.category
            base_path = definition.base_path
        if tool_id in riksdagen_by_id:
            definition = riksdagen_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = definition.category
            base_path = None  # Riksdagen tools don't use base_path
        if tool_id in marketplace_by_id:
            definition = marketplace_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = definition.category
            base_path = None  # Marketplace tools don't use base_path
        if _is_weather_tool(tool_id):
            # Keep weather tools grouped together across providers.
            category = "weather"
        if metadata_overrides and tool_id in metadata_overrides:
            override = metadata_overrides[tool_id]
            override_name = str(override.get("name") or "").strip()
            override_description = str(override.get("description") or "").strip()
            override_category = str(override.get("category") or "").strip()
            override_base_path = override.get("base_path")
            if override_name:
                name = override_name
            if override_description:
                description = override_description
            if override_category:
                category = override_category
            if isinstance(override_base_path, str):
                base_path = override_base_path.strip() or None
            elif override_base_path is None and "base_path" in override:
                base_path = None

            override_keywords = override.get("keywords")
            if isinstance(override_keywords, list):
                keywords = [
                    keyword.strip()
                    for keyword in override_keywords
                    if isinstance(keyword, str) and keyword.strip()
                ]
            override_examples = override.get("example_queries")
            if isinstance(override_examples, list):
                example_queries = [
                    example.strip()
                    for example in override_examples
                    if isinstance(example, str) and example.strip()
                ]
        if _is_weather_tool(tool_id) and str(category or "").strip().lower() in {
            "",
            "weather",
            "trafikverket_vader",
        }:
            category = "weather"
        if _is_mcp_tool(tool):
            namespace = _namespace_for_mcp_tool(
                tool_id,
                metadata=metadata,
                description=description,
            )
            inferred_keywords = _keywords_for_mcp_tool(
                tool_id,
                metadata=metadata,
                description=description,
            )
            keywords = _unique_keywords([*keywords, *inferred_keywords], max_keywords=24)
            if str(category or "").strip().lower() in {"", "general"}:
                category = _category_for_namespace(namespace)
        entry = ToolIndexEntry(
            tool_id=tool_id,
            namespace=namespace,
            name=name,
            description=description,
            keywords=keywords,
            example_queries=example_queries,
            category=category,
        )
        embedding_text = _build_rerank_text(entry)
        embedding = _get_embedding_for_tool(tool_id, embedding_text)
        entries.append(
            ToolIndexEntry(
                tool_id=entry.tool_id,
                namespace=entry.namespace,
                name=entry.name,
                description=entry.description,
                keywords=entry.keywords,
                example_queries=entry.example_queries,
                category=entry.category,
                embedding=embedding,
                base_path=base_path,
            )
        )
    return entries


def build_bigtool_store(tool_index: Iterable[ToolIndexEntry]) -> InMemoryStore:
    store = InMemoryStore()
    for entry in tool_index:
        store.put(
            entry.namespace,
            entry.tool_id,
            {
                "name": entry.name,
                "description": entry.description,
                "category": entry.category,
                "keywords": entry.keywords,
                "example_queries": entry.example_queries,
                "base_path": entry.base_path,
            },
        )
    return store
