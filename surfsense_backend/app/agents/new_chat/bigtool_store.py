from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from langchain_core.tools import BaseTool
from langgraph.store.memory import InMemoryStore

from app.agents.new_chat.statistics_agent import (
    SCB_TOOL_DEFINITIONS,
    build_scb_tool_registry,
)
from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
from app.services.reranker_service import RerankerService
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

TOOL_RERANK_CANDIDATES = 24
TOOL_EMBEDDING_WEIGHT = 4.0
_TOOL_EMBED_CACHE: dict[str, list[float]] = {}
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


def _namespace_for_bolagsverket_tool(tool_id: str) -> tuple[str, ...]:
    parts = tool_id.split("_")
    if len(parts) >= 2:
        return ("tools", "bolag", f"bolagsverket_{parts[1]}")
    return ("tools", "bolag")


def namespace_for_tool(tool_id: str) -> tuple[str, ...]:
    if tool_id.startswith("scb_"):
        return _namespace_for_scb_tool(tool_id)
    if tool_id.startswith("bolagsverket_"):
        return _namespace_for_bolagsverket_tool(tool_id)
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
    if tool_id in _TOOL_EMBED_CACHE:
        return _TOOL_EMBED_CACHE[tool_id]
    if not text:
        return None
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
    _TOOL_EMBED_CACHE[tool_id] = normalized
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
    if not trace_key or not query_norm:
        return
    _TOOL_RERANK_TRACE[(str(trace_key), query_norm)] = ranked_tools


def get_tool_rerank_trace(
    trace_key: str | None,
    *,
    query: str,
) -> list[dict[str, Any]] | None:
    if not trace_key or not query:
        return None
    query_norm = _normalize_text(query)
    return _TOOL_RERANK_TRACE.get((str(trace_key), query_norm))


def smart_retrieve_tools(
    query: str,
    *,
    tool_index: list[ToolIndexEntry],
    primary_namespaces: list[tuple[str, ...]],
    fallback_namespaces: list[tuple[str, ...]] | None = None,
    limit: int = 2,
    trace_key: str | None = None,
) -> list[str]:
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

    for entry in tool_index:
        base_score = float(_score_entry(entry, query_tokens, query_norm))
        semantic_score = 0.0
        if query_embedding and entry.embedding:
            semantic_score = _cosine_similarity(query_embedding, entry.embedding)
        total_score = base_score + (semantic_score * TOOL_EMBEDDING_WEIGHT)
        namespace_score = 0
        if any(_match_namespace(entry.namespace, prefix) for prefix in primary_namespaces):
            namespace_score = 3
            primary_scored.append((entry.tool_id, total_score + namespace_score))
        elif any(_match_namespace(entry.namespace, prefix) for prefix in fallback_namespaces):
            fallback_scored.append((entry.tool_id, total_score))

    primary_scored.sort(key=lambda item: item[1], reverse=True)
    fallback_scored.sort(key=lambda item: item[1], reverse=True)

    tool_index_by_id = {entry.tool_id: entry for entry in tool_index}
    scores_by_id = {tool_id: score for tool_id, score in primary_scored}
    scores_by_id.update({tool_id: score for tool_id, score in fallback_scored})

    candidate_ids: list[str] = []
    if primary_scored and primary_scored[0][1] > 0:
        candidate_ids = [
            tool_id for tool_id, _ in primary_scored[:TOOL_RERANK_CANDIDATES]
        ]
    elif fallback_scored and fallback_scored[0][1] > 0:
        candidate_ids = [
            tool_id for tool_id, _ in fallback_scored[:TOOL_RERANK_CANDIDATES]
        ]
    elif primary_scored:
        candidate_ids = [
            tool_id for tool_id, _ in primary_scored[:TOOL_RERANK_CANDIDATES]
        ]
    else:
        candidate_ids = [
            tool_id for tool_id, _ in fallback_scored[:TOOL_RERANK_CANDIDATES]
        ]

    reranked_ids, rerank_scores = _rerank_tool_candidates(
        query,
        candidate_ids=candidate_ids,
        tool_index_by_id=tool_index_by_id,
        scores_by_id=scores_by_id,
    )
    if trace_key and candidate_ids:
        ranked_tools: list[dict[str, Any]] = []
        for tool_id in reranked_ids:
            entry = tool_index_by_id.get(tool_id)
            ranked_tools.append(
                {
                    "tool_id": tool_id,
                    "name": entry.name if entry else tool_id,
                    "rerank_score": rerank_scores.get(tool_id),
                    "score": float(scores_by_id.get(tool_id, 0.0)),
                }
            )
        record_tool_rerank(trace_key, query_norm=query_norm, ranked_tools=ranked_tools)
    return reranked_ids[:limit]


def make_smart_retriever(
    *,
    tool_index: list[ToolIndexEntry],
    primary_namespaces: list[tuple[str, ...]],
    fallback_namespaces: list[tuple[str, ...]],
    limit: int = 2,
    trace_key: str | None = None,
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
    bolagsverket_by_id = {
        definition.tool_id: definition for definition in BOLAGSVERKET_TOOL_DEFINITIONS
    }
    entries: list[ToolIndexEntry] = []

    for tool_id, tool in tool_registry.items():
        description = getattr(tool, "description", "") or ""
        keywords = TOOL_KEYWORDS.get(tool_id, [])
        example_queries: list[str] = []
        category = "general"
        base_path: str | None = None
        if tool_id in scb_by_id:
            definition = scb_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = "statistics"
            base_path = definition.base_path
        if tool_id in bolagsverket_by_id:
            definition = bolagsverket_by_id[tool_id]
            description = definition.description
            keywords = list(definition.keywords)
            example_queries = list(definition.example_queries)
            category = definition.category
            base_path = definition.base_path
        entry = ToolIndexEntry(
            tool_id=tool_id,
            namespace=namespace_for_tool(tool_id),
            name=getattr(tool, "name", tool_id),
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
