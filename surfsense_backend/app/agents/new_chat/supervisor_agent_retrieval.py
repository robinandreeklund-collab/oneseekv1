"""Agent retrieval, ranking, and reranking logic for supervisor agent."""
from __future__ import annotations

from typing import Any

from app.agents.new_chat.bigtool_store import _normalize_text, _tokenize
from app.agents.new_chat.supervisor_constants import (
    _AGENT_EMBED_CACHE,
    AGENT_EMBEDDING_WEIGHT,
    AGENT_RERANK_CANDIDATES,
)
from app.agents.new_chat.supervisor_types import AgentDefinition
from app.services.cache_control import is_cache_disabled
from app.services.reranker_service import RerankerService


def _score_agent(definition: AgentDefinition, query_norm: str, tokens: set[str]) -> int:
    score = 0
    name_norm = _normalize_text(definition.name)
    desc_norm = _normalize_text(definition.description)
    if name_norm and name_norm in query_norm:
        score += 4
    for keyword in definition.keywords:
        if _normalize_text(keyword) in query_norm:
            score += 3
    for token in tokens:
        if token and token in desc_norm:
            score += 1
    return score


def _normalize_vector(vector: Any) -> list[float] | None:
    if vector is None:
        return None
    if isinstance(vector, list):
        return vector
    try:
        return [float(value) for value in vector]
    except Exception:
        return None


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


def _build_agent_rerank_text(definition: AgentDefinition) -> str:
    parts: list[str] = []
    if definition.name:
        parts.append(definition.name)
    if definition.description:
        parts.append(definition.description)
    if definition.keywords:
        parts.append("Keywords: " + ", ".join(definition.keywords))
    return "\n".join(part for part in parts if part)


def _get_agent_embedding(definition: AgentDefinition) -> list[float] | None:
    if not is_cache_disabled():
        cached = _AGENT_EMBED_CACHE.get(definition.name)
        if cached is not None:
            return cached
    text = _build_agent_rerank_text(definition)
    if not text:
        return None
    try:
        from app.config import config

        embedding = config.embedding_model_instance.embed(text)
    except Exception:
        return None
    normalized = _normalize_vector(embedding)
    if normalized is None:
        return None
    if not is_cache_disabled():
        _AGENT_EMBED_CACHE[definition.name] = normalized
    return normalized


def _rerank_agents(
    query: str,
    *,
    candidates: list[AgentDefinition],
    scores_by_name: dict[str, float],
) -> list[AgentDefinition]:
    if len(candidates) <= 1:
        return candidates
    reranker = RerankerService.get_reranker_instance()
    if not reranker:
        return candidates
    documents: list[dict[str, Any]] = []
    for agent in candidates:
        content = _build_agent_rerank_text(agent) or agent.name
        documents.append(
            {
                "document_id": agent.name,
                "content": content,
                "score": float(scores_by_name.get(agent.name, 0.0)),
                "document": {
                    "id": agent.name,
                    "title": agent.name,
                    "document_type": "AGENT",
                },
            }
        )
    reranked = reranker.rerank_documents(query, documents)
    if not reranked:
        return candidates
    reranked_names = [
        str(doc.get("document_id"))
        for doc in reranked
        if doc.get("document_id")
    ]
    by_name = {agent.name: agent for agent in candidates}
    ordered: list[AgentDefinition] = []
    seen: set[str] = set()
    for name in reranked_names:
        if name in by_name and name not in seen:
            ordered.append(by_name[name])
            seen.add(name)
    for agent in candidates:
        if agent.name not in seen:
            ordered.append(agent)
            seen.add(agent.name)
    return ordered


def _smart_retrieve_agents_with_breakdown(
    query: str,
    *,
    agent_definitions: list[AgentDefinition],
    recent_agents: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    query_norm = _normalize_text(query)
    tokens = set(_tokenize(query_norm))
    query_embedding: list[float] | None = None
    if query:
        try:
            from app.config import config

            query_embedding = _normalize_vector(
                config.embedding_model_instance.embed(query)
            )
        except Exception:
            query_embedding = None
    recent_agents = [agent for agent in (recent_agents or []) if agent]
    scored: list[tuple[AgentDefinition, float]] = []
    scores_by_name: dict[str, float] = {}
    for definition in agent_definitions:
        base_score = float(_score_agent(definition, query_norm, tokens))
        semantic_score = 0.0
        if query_embedding:
            agent_embedding = _get_agent_embedding(definition)
            if agent_embedding:
                semantic_score = _cosine_similarity(query_embedding, agent_embedding)
        total_score = base_score + (semantic_score * AGENT_EMBEDDING_WEIGHT)
        scored.append((definition, total_score))
        scores_by_name[definition.name] = total_score
    if recent_agents:
        for idx, (definition, score) in enumerate(scored):
            if definition.name in recent_agents:
                scored[idx] = (definition, score + 4)
                scores_by_name[definition.name] = score + 4
    scored.sort(key=lambda item: item[1], reverse=True)
    candidates = [definition for definition, _ in scored[:AGENT_RERANK_CANDIDATES]]
    reranked = _rerank_agents(
        query, candidates=candidates, scores_by_name=scores_by_name
    )
    reranked = reranked[: max(1, int(limit))]
    return [
        {
            "definition": definition,
            "name": definition.name,
            "score": float(scores_by_name.get(definition.name, 0.0)),
        }
        for definition in reranked
    ]


def _smart_retrieve_agents(
    query: str,
    *,
    agent_definitions: list[AgentDefinition],
    recent_agents: list[str] | None = None,
    limit: int = 5,
) -> list[AgentDefinition]:
    ranked = _smart_retrieve_agents_with_breakdown(
        query,
        agent_definitions=agent_definitions,
        recent_agents=recent_agents,
        limit=limit,
    )
    return [
        item.get("definition")
        for item in ranked
        if isinstance(item, dict) and item.get("definition") is not None
    ]
