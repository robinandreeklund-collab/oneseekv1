import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.prompt_registry import PROMPT_DEFINITION_MAP, get_prompt_definitions
from app.db import Permission, User
from app.schemas.agent_prompts import (
    AgentPromptsResponse,
    AgentPromptsUpdateRequest,
)
from app.services.agent_prompt_service import (
    get_prompt_overrides,
    upsert_prompt_overrides,
)
from app.users import current_active_user
from app.utils.rbac import check_permission
from app.utils.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/search-spaces/{search_space_id}/agent-prompts",
    response_model=AgentPromptsResponse,
)
async def get_agent_prompts(
    search_space_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await check_permission(
        session,
        user,
        search_space_id,
        Permission.SETTINGS_UPDATE.value,
        "You don't have permission to manage agent prompts",
    )
    overrides = await get_prompt_overrides(session, search_space_id)
    items = []
    for definition in get_prompt_definitions():
        items.append(
            {
                "key": definition.key,
                "label": definition.label,
                "description": definition.description,
                "default_prompt": definition.default_prompt,
                "override_prompt": overrides.get(definition.key),
            }
        )
    return {"items": items}


@router.put(
    "/search-spaces/{search_space_id}/agent-prompts",
    response_model=AgentPromptsResponse,
)
async def update_agent_prompts(
    search_space_id: int,
    payload: AgentPromptsUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await check_permission(
        session,
        user,
        search_space_id,
        Permission.SETTINGS_UPDATE.value,
        "You don't have permission to manage agent prompts",
    )
    updates = []
    for item in payload.items:
        if item.key not in PROMPT_DEFINITION_MAP:
            raise HTTPException(
                status_code=400, detail=f"Unknown prompt key: {item.key}"
            )
        updates.append((item.key, item.override_prompt))

    try:
        await upsert_prompt_overrides(
            session,
            search_space_id,
            updates,
            updated_by_id=user.id,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to update agent prompts")
        raise HTTPException(
            status_code=500, detail=f"Failed to update agent prompts: {exc!s}"
        ) from exc

    overrides = await get_prompt_overrides(session, search_space_id)
    items = []
    for definition in get_prompt_definitions():
        items.append(
            {
                "key": definition.key,
                "label": definition.label,
                "description": definition.description,
                "default_prompt": definition.default_prompt,
                "override_prompt": overrides.get(definition.key),
            }
        )
    return {"items": items}
