import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.bigtool_store import clear_tool_caches
from app.agents.new_chat.supervisor_agent import clear_agent_combo_cache
from app.db import AgentComboCache, SearchSpaceMembership, User
from app.db import get_async_session
from app.schemas.admin_cache import (
    CacheClearResponse,
    CacheStateResponse,
    CacheToggleRequest,
)
from app.services.cache_control import is_cache_disabled, set_cache_disabled
from app.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


async def _require_admin(
    session: AsyncSession,
    user: User,
) -> None:
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
            detail="You don't have permission to manage cache settings",
        )


@router.get(
    "/cache",
    response_model=CacheStateResponse,
)
async def get_cache_state(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    return {"disabled": is_cache_disabled()}


@router.post(
    "/cache/disable",
    response_model=CacheStateResponse,
)
async def update_cache_state(
    payload: CacheToggleRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    set_cache_disabled(payload.disabled)
    return {"disabled": is_cache_disabled()}


@router.post(
    "/cache/clear",
    response_model=CacheClearResponse,
)
async def clear_cache(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    cleared: dict[str, int | str] = {}

    clear_agent_combo_cache()
    clear_tool_caches()
    cleared["in_memory"] = 1

    try:
        result = await session.execute(delete(AgentComboCache))
        await session.commit()
        cleared["agent_combo_db_rows"] = int(result.rowcount or 0)
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to clear agent combo cache")
        cleared["agent_combo_db_error"] = str(exc)

    try:
        from app.services.trafikverket_service import TrafikverketService

        service = TrafikverketService()
        redis_client = service._get_redis()
        if redis_client:
            cleared["redis_flushed"] = int(redis_client.flushdb())
        else:
            cleared["redis_flushed"] = 0
    except Exception as exc:
        logger.exception("Failed to flush redis cache")
        cleared["redis_error"] = str(exc)

    return {"cleared": cleared}
