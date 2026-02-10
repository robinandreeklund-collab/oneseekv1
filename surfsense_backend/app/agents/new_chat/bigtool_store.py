from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from langchain_core.tools import BaseTool
from langgraph.store.memory import InMemoryStore

from app.agents.new_chat.statistics_agent import (
    SCB_TOOL_DEFINITIONS,
    build_scb_tool_registry,
)
from app.agents.new_chat.tools.registry import (
    build_tools_async,
    get_default_enabled_tools,
)


@dataclass(frozen=True)
class ToolIndexEntry:
    tool_id: str
    namespace: tuple[str, ...]
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str


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
    "smhi_weather": ("tools", "action", "travel"),
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
}

TOOL_KEYWORDS: dict[str, list[str]] = {
    "search_knowledge_base": ["sok", "search", "note", "calendar", "knowledge"],
    "search_surfsense_docs": ["surfsense", "docs", "manual", "guide"],
    "search_tavily": ["nyheter", "webb", "news", "tavily", "extern"],
    "generate_podcast": ["podcast", "podd", "audio", "ljud"],
    "display_image": ["image", "bild", "illustration"],
    "link_preview": ["lank", "link", "preview", "url"],
    "scrape_webpage": ["scrape", "skrapa", "webb", "article"],
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
}


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


def namespace_for_tool(tool_id: str) -> tuple[str, ...]:
    if tool_id.startswith("scb_"):
        return _namespace_for_scb_tool(tool_id)
    return TOOL_NAMESPACE_OVERRIDES.get(tool_id, ("tools", "general"))


def _match_namespace(entry_namespace: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    if not prefix:
        return False
    if len(entry_namespace) < len(prefix):
        return False
    return entry_namespace[: len(prefix)] == prefix


def _score_entry(entry: ToolIndexEntry, query_tokens: set[str], query_norm: str) -> int:
    score = 0
    name_norm = _normalize_text(entry.name)
    desc_norm = _normalize_text(entry.description)
    if name_norm and name_norm in query_norm:
        score += 5
    for keyword in entry.keywords:
        if _normalize_text(keyword) in query_norm:
            score += 3
    for token in query_tokens:
        if token and token in desc_norm:
            score += 1
    for example in entry.example_queries:
        if _normalize_text(example) in query_norm:
            score += 2
    return score


def smart_retrieve_tools(
    query: str,
    *,
    tool_index: list[ToolIndexEntry],
    primary_namespaces: list[tuple[str, ...]],
    fallback_namespaces: list[tuple[str, ...]] | None = None,
    limit: int = 2,
) -> list[str]:
    query_norm = _normalize_text(query)
    query_tokens = set(_tokenize(query_norm))
    fallback_namespaces = fallback_namespaces or []

    primary_scored: list[tuple[str, int]] = []
    fallback_scored: list[tuple[str, int]] = []

    for entry in tool_index:
        base_score = _score_entry(entry, query_tokens, query_norm)
        namespace_score = 0
        if any(_match_namespace(entry.namespace, prefix) for prefix in primary_namespaces):
            namespace_score = 3
            primary_scored.append((entry.tool_id, base_score + namespace_score))
        elif any(_match_namespace(entry.namespace, prefix) for prefix in fallback_namespaces):
            fallback_scored.append((entry.tool_id, base_score))

    primary_scored.sort(key=lambda item: item[1], reverse=True)
    fallback_scored.sort(key=lambda item: item[1], reverse=True)

    if primary_scored and primary_scored[0][1] > 0:
        return [tool_id for tool_id, _ in primary_scored[:limit]]
    if fallback_scored and fallback_scored[0][1] > 0:
        return [tool_id for tool_id, _ in fallback_scored[:limit]]
    if primary_scored:
        return [tool_id for tool_id, _ in primary_scored[:limit]]
    return [tool_id for tool_id, _ in fallback_scored[:limit]]


def make_smart_retriever(
    *,
    tool_index: list[ToolIndexEntry],
    primary_namespaces: list[tuple[str, ...]],
    fallback_namespaces: list[tuple[str, ...]],
    limit: int = 2,
):
    def retrieve_tools(query: str) -> list[str]:
        """Select relevant tool IDs using namespace-aware scoring."""
        return smart_retrieve_tools(
            query,
            tool_index=tool_index,
            primary_namespaces=primary_namespaces,
            fallback_namespaces=fallback_namespaces,
            limit=limit,
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
    return registry


def build_tool_index(
    tool_registry: dict[str, BaseTool],
) -> list[ToolIndexEntry]:
    scb_by_id = {definition.tool_id: definition for definition in SCB_TOOL_DEFINITIONS}
    entries: list[ToolIndexEntry] = []

    for tool_id, tool in tool_registry.items():
        description = getattr(tool, "description", "") or ""
        keywords = TOOL_KEYWORDS.get(tool_id, [])
        example_queries: list[str] = []
        category = "general"
        if tool_id in scb_by_id:
            definition = scb_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = "statistics"
        entries.append(
            ToolIndexEntry(
                tool_id=tool_id,
                namespace=namespace_for_tool(tool_id),
                name=getattr(tool, "name", tool_id),
                description=description,
                keywords=keywords,
                example_queries=example_queries,
                category=category,
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
            },
        )
    return store
