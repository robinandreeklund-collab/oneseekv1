import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.prompt_registry import (
    ACTIVE_PROMPT_DEFINITION_MAP,
    get_prompt_definitions,
)
from sqlalchemy.future import select

from app.db import GlobalAgentPromptOverrideHistory, SearchSpaceMembership, User
from app.db import get_async_session
from app.schemas.agent_prompts import (
    AgentPromptsResponse,
    AgentPromptHistoryResponse,
    AgentPromptsUpdateRequest,
)
from app.services.agent_prompt_service import (
    get_global_prompt_overrides,
    upsert_global_prompt_overrides,
)
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
            detail="You don't have permission to manage agent prompts",
        )


@router.get(
    "/agent-prompts",
    response_model=AgentPromptsResponse,
)
async def get_agent_prompts(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    overrides = await get_global_prompt_overrides(session)
    items = []
    for definition in get_prompt_definitions(active_only=True):
        items.append(
            {
                "key": definition.key,
                "label": definition.label,
                "description": definition.description,
                "node_group": definition.node_group,
                "node_group_label": definition.node_group_label,
                "default_prompt": definition.default_prompt,
                "override_prompt": overrides.get(definition.key),
            }
        )
    return {"items": items}


@router.put(
    "/agent-prompts",
    response_model=AgentPromptsResponse,
)
async def update_agent_prompts(
    payload: AgentPromptsUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    updates = []
    for item in payload.items:
        if item.key not in ACTIVE_PROMPT_DEFINITION_MAP:
            raise HTTPException(
                status_code=400, detail=f"Unknown prompt key: {item.key}"
            )
        updates.append((item.key, item.override_prompt))

    try:
        await upsert_global_prompt_overrides(
            session,
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

    overrides = await get_global_prompt_overrides(session)
    items = []
    for definition in get_prompt_definitions(active_only=True):
        items.append(
            {
                "key": definition.key,
                "label": definition.label,
                "description": definition.description,
                "node_group": definition.node_group,
                "node_group_label": definition.node_group_label,
                "default_prompt": definition.default_prompt,
                "override_prompt": overrides.get(definition.key),
            }
        )
    return {"items": items}


@router.get(
    "/agent-prompts/{prompt_key}/history",
    response_model=AgentPromptHistoryResponse,
)
async def get_agent_prompt_history(
    prompt_key: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    if prompt_key not in ACTIVE_PROMPT_DEFINITION_MAP:
        raise HTTPException(status_code=400, detail="Unknown prompt key")

    result = await session.execute(
        select(GlobalAgentPromptOverrideHistory)
        .filter(
            GlobalAgentPromptOverrideHistory.key == prompt_key,
        )
        .order_by(GlobalAgentPromptOverrideHistory.created_at.desc())
        .limit(50)
    )
    items = []
    for row in result.scalars().all():
        items.append(
            {
                "key": row.key,
                "previous_prompt": row.previous_prompt_text,
                "new_prompt": row.new_prompt_text,
                "updated_at": row.created_at.isoformat(),
                "updated_by_id": str(row.updated_by_id)
                if row.updated_by_id
                else None,
            }
        )
    return {"items": items}
