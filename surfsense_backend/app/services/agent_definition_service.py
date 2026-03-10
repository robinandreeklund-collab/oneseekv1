"""CRUD service for domain agent definitions (``agent_definitions`` table).

Provides functions to read, create, update and delete agent definitions
that sit in the middle of the intent → agent → tool hierarchy.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import DomainAgentDefinition, DomainAgentDefinitionHistory
from app.seeds.agent_definitions import get_default_agent_definitions

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


def _normalize_namespace_list(values: Any) -> list[list[str]]:
    if not isinstance(values, list):
        return []
    result: list[list[str]] = []
    for item in values:
        if isinstance(item, (list, tuple)):
            ns = [str(s).strip() for s in item if str(s).strip()]
            if ns:
                result.append(ns)
    return result


# ── Payload normalization ─────────────────────────────────────────────


def normalize_agent_payload(
    payload: Mapping[str, Any],
    *,
    agent_id: str | None = None,
    domain_id: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize an agent definition payload."""
    resolved_agent = _normalize_text(agent_id or payload.get("agent_id")).lower()
    if not resolved_agent:
        resolved_agent = "custom"
    resolved_domain = _normalize_text(domain_id or payload.get("domain_id")).lower()

    worker_config = payload.get("worker_config")
    if isinstance(worker_config, dict):
        worker_config = {
            "max_concurrency": _normalize_int(
                worker_config.get("max_concurrency"), default=4
            ),
            "timeout_seconds": _normalize_int(
                worker_config.get("timeout_seconds"), default=120
            ),
        }
    else:
        worker_config = {"max_concurrency": 4, "timeout_seconds": 120}

    return {
        "agent_id": resolved_agent,
        "domain_id": resolved_domain,
        "label": _normalize_text(payload.get("label"))
        or resolved_agent.replace("-", " ").title(),
        "description": _normalize_text(payload.get("description")),
        "keywords": _normalize_keywords(payload.get("keywords")),
        "priority": _normalize_int(payload.get("priority"), default=500),
        "enabled": bool(payload.get("enabled", True)),
        "prompt_key": _normalize_text(payload.get("prompt_key")) or resolved_agent,
        "prompt_text": _normalize_text(payload.get("prompt_text")) or None,
        "primary_namespaces": _normalize_namespace_list(
            payload.get("primary_namespaces")
        ),
        "fallback_namespaces": _normalize_namespace_list(
            payload.get("fallback_namespaces")
        ),
        "worker_config": worker_config,
        "main_identifier": _normalize_text(payload.get("main_identifier")),
        "core_activity": _normalize_text(payload.get("core_activity")),
        "unique_scope": _normalize_text(payload.get("unique_scope")),
        "geographic_scope": _normalize_text(payload.get("geographic_scope")),
        "excludes": _normalize_keywords(payload.get("excludes")),
    }


# ── Read operations ───────────────────────────────────────────────────


async def get_all_agents(session: AsyncSession) -> list[dict[str, Any]]:
    """Return all agent definitions from DB."""
    result = await session.execute(
        select(DomainAgentDefinition).order_by(DomainAgentDefinition.sort_order)
    )
    agents: list[dict[str, Any]] = []
    for row in result.scalars().all():
        payload = (
            row.definition_payload if isinstance(row.definition_payload, dict) else {}
        )
        normalized = normalize_agent_payload(
            payload, agent_id=row.agent_id, domain_id=row.domain_id
        )
        agents.append(normalized)
    return agents


async def get_agents_for_domain(
    session: AsyncSession, domain_id: str
) -> list[dict[str, Any]]:
    """Return all agents for a specific domain."""
    result = await session.execute(
        select(DomainAgentDefinition)
        .filter(DomainAgentDefinition.domain_id == domain_id)
        .order_by(DomainAgentDefinition.sort_order)
    )
    agents: list[dict[str, Any]] = []
    for row in result.scalars().all():
        payload = (
            row.definition_payload if isinstance(row.definition_payload, dict) else {}
        )
        normalized = normalize_agent_payload(
            payload, agent_id=row.agent_id, domain_id=row.domain_id
        )
        agents.append(normalized)
    return agents


async def get_agent(session: AsyncSession, agent_id: str) -> dict[str, Any] | None:
    """Return a single agent by ID."""
    result = await session.execute(
        select(DomainAgentDefinition).filter(DomainAgentDefinition.agent_id == agent_id)
    )
    row = result.scalars().first()
    if not row:
        return None
    payload = row.definition_payload if isinstance(row.definition_payload, dict) else {}
    return normalize_agent_payload(
        payload, agent_id=row.agent_id, domain_id=row.domain_id
    )


async def get_effective_agents(
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    """Return merged default + DB agents, grouped by domain_id."""
    defaults = get_default_agent_definitions()
    db_agents = await get_all_agents(session)
    merged: dict[str, dict[str, Any]] = {}
    for agent_id, agent in defaults.items():
        merged[agent_id] = normalize_agent_payload(agent, agent_id=agent_id)
    for agent in db_agents:
        agent_id = agent.get("agent_id", "")
        if agent_id:
            merged[agent_id] = agent

    by_domain: dict[str, list[dict[str, Any]]] = {}
    for agent in merged.values():
        if not agent.get("enabled", True):
            continue
        domain_id = agent.get("domain_id", "")
        by_domain.setdefault(domain_id, []).append(agent)

    for domain_agents in by_domain.values():
        domain_agents.sort(
            key=lambda a: (int(a.get("priority", 500)), str(a.get("agent_id", "")))
        )
    return by_domain


# ── Write operations ──────────────────────────────────────────────────


async def upsert_agent(
    session: AsyncSession,
    agent_id: str,
    payload: dict[str, Any],
    updated_by_id: Any = None,
) -> dict[str, Any]:
    """Create or update an agent definition. Returns the normalized payload."""
    normalized_id = _normalize_text(agent_id).lower()
    if not normalized_id:
        normalized_id = "custom"
    domain_id = _normalize_text(payload.get("domain_id")).lower()

    result = await session.execute(
        select(DomainAgentDefinition).filter(
            DomainAgentDefinition.agent_id == normalized_id
        )
    )
    existing = result.scalars().first()

    # Preserve existing domain_id when payload doesn't supply one
    if not domain_id and existing:
        domain_id = existing.domain_id or ""

    if not domain_id and not existing:
        logger.warning(
            "upsert_agent: skipping %s — no domain_id could be resolved",
            normalized_id,
        )
        return normalize_agent_payload(payload, agent_id=normalized_id, domain_id="")

    normalized = normalize_agent_payload(
        payload, agent_id=normalized_id, domain_id=domain_id
    )

    previous_payload = (
        normalize_agent_payload(
            existing.definition_payload,
            agent_id=normalized_id,
            domain_id=existing.domain_id,
        )
        if existing and isinstance(existing.definition_payload, dict)
        else None
    )

    if existing:
        existing.definition_payload = normalized
        existing.domain_id = domain_id
        existing.sort_order = normalized.get("priority", 500)
        if updated_by_id is not None:
            existing.updated_by_id = updated_by_id
    else:
        session.add(
            DomainAgentDefinition(
                agent_id=normalized_id,
                domain_id=domain_id,
                definition_payload=normalized,
                sort_order=normalized.get("priority", 500),
                updated_by_id=updated_by_id,
            )
        )

    if previous_payload != normalized:
        session.add(
            DomainAgentDefinitionHistory(
                agent_id=normalized_id,
                previous_payload=previous_payload,
                new_payload=normalized,
                updated_by_id=updated_by_id,
            )
        )

    return normalized


async def delete_agent(
    session: AsyncSession,
    agent_id: str,
    updated_by_id: Any = None,
) -> bool:
    """Delete an agent definition. Returns True if deleted."""
    result = await session.execute(
        select(DomainAgentDefinition).filter(DomainAgentDefinition.agent_id == agent_id)
    )
    existing = result.scalars().first()
    if not existing:
        return False

    previous_payload = (
        normalize_agent_payload(
            existing.definition_payload,
            agent_id=agent_id,
            domain_id=existing.domain_id,
        )
        if isinstance(existing.definition_payload, dict)
        else None
    )
    session.add(
        DomainAgentDefinitionHistory(
            agent_id=agent_id,
            previous_payload=previous_payload,
            new_payload=None,
            updated_by_id=updated_by_id,
        )
    )
    await session.delete(existing)
    return True
