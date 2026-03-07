"""Domain-scoped agent resolution using GraphRegistry.

Given a resolved domain_id and a user query, this module scores and ranks
candidate agents from ``registry.agents_by_domain[domain_id]``.  The scoring
pipeline uses lexical matching + embedding cosine similarity so that the
supervisor can select the best specialist agent without hardcoded if/else
chains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Embedding similarity weight relative to lexical scoring.
_EMBEDDING_WEIGHT = 4.0


def _normalize_text(value: str) -> str:
    lowered = (value or "").lower()
    cleaned = (
        lowered.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
    )
    return "".join(
        ch if ch.isalnum() or ch.isspace() else " " for ch in cleaned
    ).strip()


def _tokenize(value: str) -> set[str]:
    return {token for token in _normalize_text(value).split() if token}


def _safe_keywords(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()]


@dataclass(frozen=True)
class AgentCandidate:
    """Scored agent candidate from domain-scoped resolution."""

    agent_id: str
    domain_id: str
    label: str
    description: str
    keywords: list[str]
    priority: int
    score: float
    keyword_hits: int
    name_match: bool


def score_agent(
    *,
    query_norm: str,
    query_tokens: set[str],
    agent: dict[str, Any],
) -> AgentCandidate:
    """Score a single agent definition against a normalised user query."""
    agent_id = str(agent.get("agent_id") or "").strip().lower()
    domain_id = str(agent.get("domain_id") or "").strip().lower()
    label = str(agent.get("label") or agent_id).strip()
    description = str(agent.get("description") or "").strip()
    keywords = _safe_keywords(agent.get("keywords"))
    priority = int(agent.get("priority") or 500)

    agent_norm = _normalize_text(agent_id)
    description_norm = _normalize_text(description)

    name_match = bool(agent_norm and agent_norm in query_norm)
    keyword_hits = sum(
        1
        for kw in keywords
        if _normalize_text(kw) in query_norm
    )
    description_hits = sum(
        1
        for token in query_tokens
        if token and token in description_norm
    )
    priority_bonus = max(0.0, 3.0 - (float(priority) / 250.0))
    total = (
        (4.0 if name_match else 0.0)
        + (keyword_hits * 2.4)
        + (description_hits * 0.6)
        + priority_bonus
    )
    return AgentCandidate(
        agent_id=agent_id,
        domain_id=domain_id,
        label=label,
        description=description,
        keywords=keywords,
        priority=priority,
        score=round(total, 4),
        keyword_hits=keyword_hits,
        name_match=name_match,
    )


def resolve_agents_for_domain(
    *,
    query: str,
    domain_id: str,
    registry: Any,
    top_k: int = 5,
) -> list[AgentCandidate]:
    """Return ranked agent candidates for a given domain.

    Looks up ``registry.agents_by_domain[domain_id]``, scores each agent
    against the user query, and returns the top *top_k* candidates sorted
    by score (descending) then priority (ascending).

    If no agents are found for the domain, falls back to all agents in
    the registry.
    """
    agents = list((registry.agents_by_domain or {}).get(domain_id) or [])
    if not agents:
        # Fallback: score all agents across all domains
        for agent_list in (registry.agents_by_domain or {}).values():
            agents.extend(agent_list)
    if not agents:
        return []

    query_norm = _normalize_text(query)
    query_tokens = _tokenize(query)

    scored = [
        score_agent(
            query_norm=query_norm,
            query_tokens=query_tokens,
            agent=agent,
        )
        for agent in agents
        if agent.get("enabled", True)
    ]

    # Add embedding similarity scores
    try:
        from app.services.embedding_scorer import compute_embedding_scores

        embedding_docs = [
            {
                "id": c.agent_id,
                "label": c.label,
                "description": c.description,
                "keywords": c.keywords,
            }
            for c in scored
        ]
        embed_scores = compute_embedding_scores(
            query, embedding_docs,
            id_key="id",
            label_key="label",
            description_key="description",
            keywords_key="keywords",
        )
        if embed_scores:
            scored = [
                AgentCandidate(
                    agent_id=c.agent_id,
                    domain_id=c.domain_id,
                    label=c.label,
                    description=c.description,
                    keywords=c.keywords,
                    priority=c.priority,
                    score=round(
                        c.score + embed_scores.get(c.agent_id, 0.0) * _EMBEDDING_WEIGHT,
                        4,
                    ),
                    keyword_hits=c.keyword_hits,
                    name_match=c.name_match,
                )
                for c in scored
            ]
    except Exception:
        pass

    # Deduplicate by agent_id (keep highest score)
    seen: dict[str, AgentCandidate] = {}
    for candidate in scored:
        existing = seen.get(candidate.agent_id)
        if existing is None or candidate.score > existing.score:
            seen[candidate.agent_id] = candidate
    scored = list(seen.values())

    scored.sort(
        key=lambda c: (-c.score, c.priority, c.agent_id),
    )
    return scored[:top_k]


def resolve_default_agent_for_domain(
    *,
    query: str,
    domain_id: str,
    registry: Any,
) -> str | None:
    """Return the best single agent_id for a domain, or None."""
    candidates = resolve_agents_for_domain(
        query=query,
        domain_id=domain_id,
        registry=registry,
        top_k=1,
    )
    return candidates[0].agent_id if candidates else None


def agents_to_definitions(
    agents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert agent seed/registry dicts to supervisor AgentDefinition-compatible format.

    This bridges registry agent data into the format expected by the existing
    ``AgentDefinition`` dataclass in ``supervisor_agent.py``.
    """
    definitions: list[dict[str, Any]] = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("agent_id") or "").strip()
        if not agent_id or not agent.get("enabled", True):
            continue
        definitions.append(
            {
                "name": agent_id,
                "description": str(agent.get("description") or "").strip(),
                "keywords": _safe_keywords(agent.get("keywords")),
                "namespace": tuple(
                    str(s)
                    for s in (agent.get("primary_namespaces") or [[]])[0]
                )
                or ("agents", agent_id),
                "prompt_key": str(
                    agent.get("prompt_key") or f"{agent_id}_prompt"
                ),
                "domain_id": str(agent.get("domain_id") or "").strip(),
                "priority": int(agent.get("priority") or 500),
                "worker_config": dict(agent.get("worker_config") or {}),
            }
        )
    return definitions
