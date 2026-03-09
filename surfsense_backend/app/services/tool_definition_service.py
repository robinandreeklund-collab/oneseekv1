"""CRUD service for agent tool definitions (``tool_definitions`` table).

Provides functions to read, create, update and delete tool definitions
at the bottom of the intent → agent → tool hierarchy.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AgentToolDefinition, AgentToolDefinitionHistory
from app.seeds.tool_definitions import get_default_tool_definitions

# ── Normalization helpers ─────────────────────────────────────────────


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_int(value: Any, *, default: int = 500) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(10000, parsed))


def _normalize_keywords(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [str(s).strip() for s in values if str(s).strip()]


# ── Payload normalization ─────────────────────────────────────────────


def normalize_tool_payload(
    payload: Mapping[str, Any],
    *,
    tool_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize a tool definition payload."""
    resolved_tool = _normalize_text(tool_id or payload.get("tool_id")).lower()
    if not resolved_tool:
        resolved_tool = "custom"
    resolved_agent = _normalize_text(agent_id or payload.get("agent_id")).lower()

    return {
        "tool_id": resolved_tool,
        "agent_id": resolved_agent,
        "label": _normalize_text(payload.get("label"))
        or resolved_tool.replace("_", " ").title(),
        "description": _normalize_text(payload.get("description")),
        "keywords": _normalize_keywords(payload.get("keywords")),
        "example_queries": _normalize_keywords(payload.get("example_queries")),
        "category": _normalize_text(payload.get("category")),
        "enabled": bool(payload.get("enabled", True)),
        "priority": _normalize_int(payload.get("priority"), default=500),
        "namespace": _normalize_string_list(payload.get("namespace")),
        "main_identifier": _normalize_text(payload.get("main_identifier")),
        "core_activity": _normalize_text(payload.get("core_activity")),
        "unique_scope": _normalize_text(payload.get("unique_scope")),
        "geographic_scope": _normalize_text(payload.get("geographic_scope")),
        "excludes": _normalize_keywords(payload.get("excludes")),
        "callable_path": _normalize_text(payload.get("callable_path")) or None,
    }


# ── Read operations ───────────────────────────────────────────────────


async def get_all_tools(session: AsyncSession) -> list[dict[str, Any]]:
    """Return all tool definitions from DB."""
    result = await session.execute(
        select(AgentToolDefinition).order_by(AgentToolDefinition.sort_order)
    )
    tools: list[dict[str, Any]] = []
    for row in result.scalars().all():
        payload = (
            row.definition_payload if isinstance(row.definition_payload, dict) else {}
        )
        normalized = normalize_tool_payload(
            payload, tool_id=row.tool_id, agent_id=row.agent_id
        )
        tools.append(normalized)
    return tools


async def get_tools_for_agent(
    session: AsyncSession, agent_id: str
) -> list[dict[str, Any]]:
    """Return all tools for a specific agent."""
    result = await session.execute(
        select(AgentToolDefinition)
        .filter(AgentToolDefinition.agent_id == agent_id)
        .order_by(AgentToolDefinition.sort_order)
    )
    tools: list[dict[str, Any]] = []
    for row in result.scalars().all():
        payload = (
            row.definition_payload if isinstance(row.definition_payload, dict) else {}
        )
        normalized = normalize_tool_payload(
            payload, tool_id=row.tool_id, agent_id=row.agent_id
        )
        tools.append(normalized)
    return tools


async def get_effective_tools(
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    """Return merged default + DB tools, grouped by agent_id."""
    defaults = get_default_tool_definitions()
    db_tools = await get_all_tools(session)
    merged: dict[str, dict[str, Any]] = {}
    for tool_id, tool in defaults.items():
        merged[tool_id] = normalize_tool_payload(tool, tool_id=tool_id)
    for tool in db_tools:
        tool_id = tool.get("tool_id", "")
        if tool_id:
            merged[tool_id] = tool

    by_agent: dict[str, list[dict[str, Any]]] = {}
    for tool in merged.values():
        if not tool.get("enabled", True):
            continue
        agent_id = tool.get("agent_id", "")
        by_agent.setdefault(agent_id, []).append(tool)

    for agent_tools in by_agent.values():
        agent_tools.sort(
            key=lambda t: (int(t.get("priority", 500)), str(t.get("tool_id", "")))
        )
    return by_agent


# ── Write operations ──────────────────────────────────────────────────


async def upsert_tool(
    session: AsyncSession,
    tool_id: str,
    payload: dict[str, Any],
    updated_by_id: Any = None,
) -> dict[str, Any]:
    """Create or update a tool definition. Returns the normalized payload."""
    normalized_id = _normalize_text(tool_id).lower()
    if not normalized_id:
        normalized_id = "custom"
    agent_id = _normalize_text(payload.get("agent_id")).lower()
    normalized = normalize_tool_payload(
        payload, tool_id=normalized_id, agent_id=agent_id
    )

    result = await session.execute(
        select(AgentToolDefinition).filter(AgentToolDefinition.tool_id == normalized_id)
    )
    existing = result.scalars().first()
    previous_payload = (
        normalize_tool_payload(
            existing.definition_payload,
            tool_id=normalized_id,
            agent_id=existing.agent_id,
        )
        if existing and isinstance(existing.definition_payload, dict)
        else None
    )

    if existing:
        existing.definition_payload = normalized
        existing.agent_id = agent_id
        existing.sort_order = normalized.get("priority", 500)
        if updated_by_id is not None:
            existing.updated_by_id = updated_by_id
    else:
        session.add(
            AgentToolDefinition(
                tool_id=normalized_id,
                agent_id=agent_id,
                definition_payload=normalized,
                sort_order=normalized.get("priority", 500),
                updated_by_id=updated_by_id,
            )
        )

    if previous_payload != normalized:
        session.add(
            AgentToolDefinitionHistory(
                tool_id=normalized_id,
                previous_payload=previous_payload,
                new_payload=normalized,
                updated_by_id=updated_by_id,
            )
        )

    return normalized


async def delete_tool(
    session: AsyncSession,
    tool_id: str,
    updated_by_id: Any = None,
) -> bool:
    """Delete a tool definition. Returns True if deleted."""
    result = await session.execute(
        select(AgentToolDefinition).filter(AgentToolDefinition.tool_id == tool_id)
    )
    existing = result.scalars().first()
    if not existing:
        return False

    previous_payload = (
        normalize_tool_payload(
            existing.definition_payload,
            tool_id=tool_id,
            agent_id=existing.agent_id,
        )
        if isinstance(existing.definition_payload, dict)
        else None
    )
    session.add(
        AgentToolDefinitionHistory(
            tool_id=tool_id,
            previous_payload=previous_payload,
            new_payload=None,
            updated_by_id=updated_by_id,
        )
    )
    await session.delete(existing)
    return True
