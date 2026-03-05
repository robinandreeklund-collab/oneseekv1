"""Graph registry service — loads the complete domain→agent→tool hierarchy.

The ``GraphRegistry`` dataclass holds a frozen snapshot of the entire
configuration tree.  ``RegistryCache`` is a process-level singleton that
avoids reloading on every request by checking the ``registry_version``
counter in the database.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import RegistryVersion
from app.services.agent_definition_service import get_effective_agents
from app.services.intent_domain_service import get_effective_intent_domains
from app.services.tool_definition_service import get_effective_tools

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphRegistry:
    """Complete, immutable snapshot of the intent→agent→tool hierarchy."""

    domains: list[dict[str, Any]]
    agents_by_domain: dict[str, list[dict[str, Any]]]
    tools_by_agent: dict[str, list[dict[str, Any]]]
    domain_index: dict[str, dict[str, Any]]
    agent_index: dict[str, dict[str, Any]]
    tool_index: dict[str, dict[str, Any]]
    route_fallback_map: dict[str, str]
    version: int = 0
    loaded_at: float = 0.0


async def _read_registry_version(session: AsyncSession) -> int:
    """Read the current registry version counter from DB."""
    result = await session.execute(
        select(RegistryVersion.version).filter(RegistryVersion.key == "global")
    )
    row = result.scalar_one_or_none()
    return int(row) if row is not None else 0


async def load_graph_registry(session: AsyncSession) -> GraphRegistry:
    """Load the complete hierarchy from the database and build indices."""

    domains = await get_effective_intent_domains(session)
    agents_by_domain = await get_effective_agents(session)
    tools_by_agent = await get_effective_tools(session)
    version = await _read_registry_version(session)

    # Build lookup indices
    domain_index: dict[str, dict[str, Any]] = {}
    for domain in domains:
        domain_id = domain.get("domain_id", "")
        if domain_id:
            domain_index[domain_id] = domain

    agent_index: dict[str, dict[str, Any]] = {}
    for agent_list in agents_by_domain.values():
        for agent in agent_list:
            agent_id = agent.get("agent_id", "")
            if agent_id:
                agent_index[agent_id] = agent

    tool_index: dict[str, dict[str, Any]] = {}
    for tool_list in tools_by_agent.values():
        for tool in tool_list:
            tool_id = tool.get("tool_id", "")
            if tool_id:
                tool_index[tool_id] = tool

    route_fallback_map: dict[str, str] = {}
    for domain in domains:
        domain_id = domain.get("domain_id", "")
        fallback = domain.get("fallback_route", "kunskap")
        if domain_id:
            route_fallback_map[domain_id] = fallback

    return GraphRegistry(
        domains=domains,
        agents_by_domain=agents_by_domain,
        tools_by_agent=tools_by_agent,
        domain_index=domain_index,
        agent_index=agent_index,
        tool_index=tool_index,
        route_fallback_map=route_fallback_map,
        version=version,
        loaded_at=time.monotonic(),
    )


class RegistryCache:
    """Process-level singleton with version-based staleness detection.

    Avoids reloading the full hierarchy on every request.  When any
    admin mutation bumps ``registry_version``, the cache detects the
    mismatch and reloads on the next ``get()`` call.
    """

    _instance: GraphRegistry | None = None
    _version: int = 0
    _loaded_at: float = 0.0
    _lock: asyncio.Lock | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get(cls, session: AsyncSession) -> GraphRegistry:
        """Return cached registry, reloading if the DB version changed."""
        if cls._instance is not None and not await cls._is_stale(session):
            return cls._instance

        async with cls._get_lock():
            # Double-check after acquiring lock
            if cls._instance is not None and not await cls._is_stale(session):
                return cls._instance
            return await cls._reload(session)

    @classmethod
    async def invalidate(cls) -> None:
        """Force next ``get()`` to reload from DB."""
        cls._instance = None
        cls._version = 0
        logger.info("RegistryCache invalidated — will reload on next access")

    @classmethod
    async def _is_stale(cls, session: AsyncSession) -> bool:
        """Check DB version counter against cached version."""
        try:
            db_version = await _read_registry_version(session)
        except Exception:
            logger.warning("Failed to read registry version — assuming stale")
            return True
        return db_version > cls._version

    @classmethod
    async def _reload(cls, session: AsyncSession) -> GraphRegistry:
        """Load fresh registry from DB and update cache."""
        logger.info("RegistryCache reloading from database …")
        registry = await load_graph_registry(session)
        cls._instance = registry
        cls._version = registry.version
        cls._loaded_at = registry.loaded_at
        logger.info(
            "RegistryCache loaded: %d domains, %d agents, %d tools (version=%d)",
            len(registry.domains),
            len(registry.agent_index),
            len(registry.tool_index),
            registry.version,
        )
        return registry
