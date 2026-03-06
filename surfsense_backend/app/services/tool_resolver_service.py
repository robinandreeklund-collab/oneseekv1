"""Agent-scoped tool resolution using GraphRegistry.

Given a resolved agent_id and a user query, this module scores and ranks
candidate tools from ``registry.tools_by_agent[agent_id]``.  Tools are
scored lexically against the query so the planner/executor can bind the
most relevant tools without hardcoded tool sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
class ToolCandidate:
    """Scored tool candidate from agent-scoped resolution."""

    tool_id: str
    agent_id: str
    label: str
    description: str
    keywords: list[str]
    category: str
    namespace: list[str]
    priority: int
    score: float
    keyword_hits: int
    name_match: bool


def score_tool(
    *,
    query_norm: str,
    query_tokens: set[str],
    tool: dict[str, Any],
) -> ToolCandidate:
    """Score a single tool definition against a normalised user query."""
    tool_id = str(tool.get("tool_id") or "").strip().lower()
    agent_id = str(tool.get("agent_id") or "").strip().lower()
    label = str(tool.get("label") or tool_id).strip()
    description = str(tool.get("description") or "").strip()
    keywords = _safe_keywords(tool.get("keywords"))
    category = str(tool.get("category") or "").strip()
    namespace = list(tool.get("namespace") or [])
    priority = int(tool.get("priority") or 500)

    tool_norm = _normalize_text(tool_id)
    description_norm = _normalize_text(description)

    name_match = bool(tool_norm and tool_norm in query_norm)
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
    priority_bonus = max(0.0, 2.0 - (float(priority) / 250.0))
    total = (
        (3.0 if name_match else 0.0)
        + (keyword_hits * 2.0)
        + (description_hits * 0.5)
        + priority_bonus
    )
    return ToolCandidate(
        tool_id=tool_id,
        agent_id=agent_id,
        label=label,
        description=description,
        keywords=keywords,
        category=category,
        namespace=namespace,
        priority=priority,
        score=round(total, 4),
        keyword_hits=keyword_hits,
        name_match=name_match,
    )


def resolve_tools_for_agent(
    *,
    query: str,
    agent_id: str,
    registry: Any,
    top_k: int = 15,
    include_all: bool = False,
) -> list[ToolCandidate]:
    """Return ranked tool candidates for a given agent.

    Looks up ``registry.tools_by_agent[agent_id]``, scores each tool
    against the user query, and returns the top *top_k* candidates.

    When *include_all* is True, returns all enabled tools for the agent
    (still sorted by score), ignoring top_k.
    """
    tools = list((registry.tools_by_agent or {}).get(agent_id) or [])
    if not tools:
        return []

    query_norm = _normalize_text(query)
    query_tokens = _tokenize(query)

    scored = [
        score_tool(
            query_norm=query_norm,
            query_tokens=query_tokens,
            tool=tool,
        )
        for tool in tools
        if tool.get("enabled", True)
    ]
    scored.sort(
        key=lambda c: (-c.score, c.priority, c.tool_id),
    )
    if include_all:
        return scored
    return scored[:top_k]


def resolve_tool_ids_for_agent(
    *,
    query: str,
    agent_id: str,
    registry: Any,
    top_k: int = 15,
) -> list[str]:
    """Return just the tool_id strings for the top-k tools."""
    candidates = resolve_tools_for_agent(
        query=query,
        agent_id=agent_id,
        registry=registry,
        top_k=top_k,
    )
    return [c.tool_id for c in candidates]


def tools_to_agent_tool_profiles(
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert tool seed/registry dicts to AgentToolProfile-compatible format.

    Bridges registry tool data into the format consumed by the existing
    ``_AGENT_TOOL_PROFILES`` dict in ``supervisor_constants.py``.
    """
    profiles: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_id = str(tool.get("tool_id") or "").strip()
        if not tool_id or not tool.get("enabled", True):
            continue
        profiles.append(
            {
                "tool_id": tool_id,
                "category": str(tool.get("category") or "").strip(),
                "description": str(tool.get("description") or "").strip(),
                "keywords": tuple(_safe_keywords(tool.get("keywords"))),
            }
        )
    return profiles
