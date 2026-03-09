"""Admin API routes for managing the intent→agent→tool graph hierarchy.

All mutations bump the registry version counter and send a PG NOTIFY
so that all workers invalidate their cached ``GraphRegistry``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import SearchSpaceMembership, User, get_async_session
from app.schemas.graph_config import (
    AgentDeleteResponse,
    AgentPayload,
    AgentResponse,
    DomainDeleteResponse,
    DomainPayload,
    DomainResponse,
    RegistryReloadResponse,
    RegistrySnapshotResponse,
    ToolDeleteResponse,
    ToolPayload,
    ToolResponse,
)
from app.services.agent_definition_service import (
    delete_agent,
    get_agents_for_domain,
    get_all_agents,
    upsert_agent,
)
from app.services.graph_registry_service import RegistryCache, load_graph_registry
from app.services.intent_domain_service import (
    delete_intent_domain,
    get_all_intent_domains,
    upsert_intent_domain,
)
from app.services.registry_events import bump_registry_version, notify_registry_changed
from app.services.tool_definition_service import (
    delete_tool,
    get_all_tools,
    get_tools_for_agent,
    upsert_tool,
)
from app.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/graph", tags=["admin-graph"])


async def _require_admin(session: AsyncSession, user: User) -> None:
    result = await session.execute(
        select(SearchSpaceMembership)
        .filter(
            SearchSpaceMembership.user_id == user.id,
            SearchSpaceMembership.is_owner.is_(True),
        )
        .limit(1)
    )
    if result.scalars().first() is None:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to manage graph configuration",
        )


# ── Domain endpoints ──────────────────────────────────────────────────


@router.get("/domains")
async def list_domains(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    await _require_admin(session, user)
    return await get_all_intent_domains(session)


@router.post("/domains", response_model=DomainResponse)
async def upsert_domain_endpoint(
    payload: DomainPayload,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> DomainResponse:
    await _require_admin(session, user)
    result = await upsert_intent_domain(
        session, payload.domain_id, payload.model_dump(), updated_by_id=user.id
    )
    new_version = await bump_registry_version(session)
    await session.commit()
    await notify_registry_changed(session, new_version)
    await RegistryCache.invalidate()
    return DomainResponse(status="ok", version=new_version, domain=result)


@router.delete("/domains/{domain_id}", response_model=DomainDeleteResponse)
async def delete_domain_endpoint(
    domain_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> DomainDeleteResponse:
    await _require_admin(session, user)
    deleted = await delete_intent_domain(session, domain_id, updated_by_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    new_version = await bump_registry_version(session)
    await session.commit()
    await notify_registry_changed(session, new_version)
    await RegistryCache.invalidate()
    return DomainDeleteResponse(status="ok", version=new_version, deleted=True)


# ── Agent endpoints ───────────────────────────────────────────────────


@router.get("/agents")
async def list_agents(
    domain_id: str | None = Query(default=None),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    await _require_admin(session, user)
    if domain_id:
        return await get_agents_for_domain(session, domain_id)
    return await get_all_agents(session)


@router.post("/agents", response_model=AgentResponse)
async def upsert_agent_endpoint(
    payload: AgentPayload,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> AgentResponse:
    await _require_admin(session, user)
    result = await upsert_agent(
        session, payload.agent_id, payload.model_dump(), updated_by_id=user.id
    )
    new_version = await bump_registry_version(session)
    await session.commit()
    await notify_registry_changed(session, new_version)
    await RegistryCache.invalidate()
    return AgentResponse(status="ok", version=new_version, agent=result)


@router.delete("/agents/{agent_id}", response_model=AgentDeleteResponse)
async def delete_agent_endpoint(
    agent_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> AgentDeleteResponse:
    await _require_admin(session, user)
    deleted = await delete_agent(session, agent_id, updated_by_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    new_version = await bump_registry_version(session)
    await session.commit()
    await notify_registry_changed(session, new_version)
    await RegistryCache.invalidate()
    return AgentDeleteResponse(status="ok", version=new_version, deleted=True)


# ── Tool endpoints ────────────────────────────────────────────────────


@router.get("/tools")
async def list_tools(
    agent_id: str | None = Query(default=None),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    await _require_admin(session, user)
    if agent_id:
        return await get_tools_for_agent(session, agent_id)
    return await get_all_tools(session)


@router.post("/tools", response_model=ToolResponse)
async def upsert_tool_endpoint(
    payload: ToolPayload,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ToolResponse:
    await _require_admin(session, user)
    result = await upsert_tool(
        session, payload.tool_id, payload.model_dump(), updated_by_id=user.id
    )
    new_version = await bump_registry_version(session)
    await session.commit()
    await notify_registry_changed(session, new_version)
    await RegistryCache.invalidate()
    return ToolResponse(status="ok", version=new_version, tool=result)


@router.delete("/tools/{tool_id}", response_model=ToolDeleteResponse)
async def delete_tool_endpoint(
    tool_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ToolDeleteResponse:
    await _require_admin(session, user)
    deleted = await delete_tool(session, tool_id, updated_by_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")
    new_version = await bump_registry_version(session)
    await session.commit()
    await notify_registry_changed(session, new_version)
    await RegistryCache.invalidate()
    return ToolDeleteResponse(status="ok", version=new_version, deleted=True)


# ── Registry endpoints ────────────────────────────────────────────────


@router.get("/registry", response_model=RegistrySnapshotResponse)
async def get_registry_snapshot(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> RegistrySnapshotResponse:
    """Return the full registry snapshot (read-only)."""
    await _require_admin(session, user)
    registry = await load_graph_registry(session)
    return RegistrySnapshotResponse(
        version=registry.version,
        domain_count=len(registry.domains),
        agent_count=len(registry.agent_index),
        tool_count=len(registry.tool_index),
        domains=registry.domains,
        agents_by_domain=registry.agents_by_domain,
        tools_by_agent=registry.tools_by_agent,
    )


@router.post("/reload", response_model=RegistryReloadResponse)
async def reload_registry(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> RegistryReloadResponse:
    """Force reload the cached registry."""
    await _require_admin(session, user)
    await RegistryCache.invalidate()
    registry = await RegistryCache.get(session)
    return RegistryReloadResponse(
        status="ok",
        version=registry.version,
        domain_count=len(registry.domains),
        agent_count=len(registry.agent_index),
        tool_count=len(registry.tool_index),
    )
