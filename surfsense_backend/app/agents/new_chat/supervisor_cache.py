"""Cache management for supervisor agent - cache key building, get/set, DB persistence."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.bigtool_store import _tokenize
from app.agents.new_chat.supervisor_constants import (
    _AGENT_CACHE_TTL,
    _AGENT_COMBO_CACHE,
    _AGENT_EMBED_CACHE,
    _AGENT_STOPWORDS,
)
from app.db import AgentComboCache
from app.services.cache_control import is_cache_disabled


def _build_cache_key(
    query: str,
    route_hint: str | None,
    recent_agents: list[str] | None,
    sub_intents: list[str] | None = None,
) -> tuple[str, str]:
    tokens = [
        token
        for token in _tokenize(query)
        if token and token not in _AGENT_STOPWORDS
    ]
    token_slice = " ".join(tokens[:6])
    recent_slice = ",".join((recent_agents or [])[-2:])
    # Include sorted sub_intents in cache key for multi-domain support
    sub_intents_slice = ""
    if sub_intents:
        sorted_intents = sorted(str(i) for i in sub_intents if i)
        sub_intents_slice = ",".join(sorted_intents)
    pattern = f"{route_hint or 'none'}|{recent_slice}|{token_slice}|{sub_intents_slice}"
    key = hashlib.sha256(pattern.encode("utf-8")).hexdigest()
    return key, pattern


def _get_cached_combo(cache_key: str) -> list[str] | None:
    if is_cache_disabled():
        return None
    entry = _AGENT_COMBO_CACHE.get(cache_key)
    if not entry:
        return None
    expires_at, agents = entry
    if expires_at < datetime.now(UTC):
        _AGENT_COMBO_CACHE.pop(cache_key, None)
        return None
    return agents


def _set_cached_combo(cache_key: str, agents: list[str]) -> None:
    if is_cache_disabled():
        return
    _AGENT_COMBO_CACHE[cache_key] = (datetime.now(UTC) + _AGENT_CACHE_TTL, agents)


def clear_agent_combo_cache() -> None:
    _AGENT_COMBO_CACHE.clear()
    _AGENT_EMBED_CACHE.clear()


async def _fetch_cached_combo_db(
    session: AsyncSession | None, cache_key: str
) -> list[str] | None:
    if is_cache_disabled():
        return None
    if session is None:
        return None
    result = await session.execute(
        select(AgentComboCache).where(AgentComboCache.cache_key == cache_key)
    )
    row = result.scalars().first()
    if not row:
        return None
    agents = row.agents if isinstance(row.agents, list) else []
    row.hit_count = int(row.hit_count or 0) + 1
    row.last_used_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return [str(agent) for agent in agents if agent]


async def _store_cached_combo_db(
    session: AsyncSession | None,
    *,
    cache_key: str,
    route_hint: str | None,
    pattern: str,
    recent_agents: list[str],
    agents: list[str],
) -> None:
    if is_cache_disabled():
        return
    if session is None:
        return
    result = await session.execute(
        select(AgentComboCache).where(AgentComboCache.cache_key == cache_key)
    )
    row = result.scalars().first()
    if row:
        row.agents = agents
        row.recent_agents = recent_agents
        row.route_hint = route_hint
        row.pattern = pattern
        row.updated_at = datetime.now(UTC)
        row.last_used_at = datetime.now(UTC)
    else:
        row = AgentComboCache(
            cache_key=cache_key,
            route_hint=route_hint,
            pattern=pattern,
            recent_agents=recent_agents,
            agents=agents,
            hit_count=0,
            last_used_at=datetime.now(UTC),
        )
        session.add(row)
    await session.commit()
