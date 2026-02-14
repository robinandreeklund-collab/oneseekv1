import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import (
    GlobalIntentDefinitionHistory,
    SearchSpaceMembership,
    User,
    get_async_session,
)
from app.schemas.admin_intent_definitions import (
    IntentDefinitionHistoryResponse,
    IntentDefinitionsResponse,
    IntentDefinitionsUpdateRequest,
)
from app.services.intent_definition_service import (
    get_default_intent_definitions,
    get_effective_intent_definitions,
    get_global_intent_definition_overrides,
    normalize_intent_definition_payload,
    upsert_global_intent_definition_overrides,
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
            detail="You don't have permission to manage intent definitions",
        )


async def _build_intent_response(session: AsyncSession) -> dict[str, list[dict]]:
    defaults = get_default_intent_definitions()
    overrides = await get_global_intent_definition_overrides(session)
    effective = await get_effective_intent_definitions(session)
    items: list[dict] = []
    for definition in effective:
        intent_id = str(definition.get("intent_id") or "").strip().lower()
        items.append(
            {
                "intent_id": intent_id,
                "route": definition.get("route"),
                "label": definition.get("label"),
                "description": definition.get("description") or "",
                "keywords": list(definition.get("keywords") or []),
                "priority": int(definition.get("priority") or 500),
                "enabled": bool(definition.get("enabled", True)),
                "has_override": intent_id in overrides
                and normalize_intent_definition_payload(
                    overrides.get(intent_id) or {},
                    intent_id=intent_id,
                )
                != normalize_intent_definition_payload(
                    defaults.get(intent_id) or {"intent_id": intent_id},
                    intent_id=intent_id,
                ),
            }
        )
    return {"items": items}


@router.get(
    "/intent-definitions",
    response_model=IntentDefinitionsResponse,
)
async def get_intent_definitions(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    return await _build_intent_response(session)


@router.put(
    "/intent-definitions",
    response_model=IntentDefinitionsResponse,
)
async def update_intent_definitions(
    payload: IntentDefinitionsUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    defaults = get_default_intent_definitions()
    current_overrides = await get_global_intent_definition_overrides(session)
    updates: list[tuple[str, dict | None]] = []
    for item in payload.items:
        intent_id = str(item.intent_id or "").strip().lower()
        if not intent_id:
            raise HTTPException(status_code=400, detail="intent_id is required")
        if item.clear_override:
            updates.append((intent_id, None))
            continue
        base_payload = (
            current_overrides.get(intent_id)
            or defaults.get(intent_id)
            or {"intent_id": intent_id}
        )
        merged = dict(base_payload)
        if item.route is not None:
            merged["route"] = item.route
        if item.label is not None:
            merged["label"] = item.label
        if item.description is not None:
            merged["description"] = item.description
        if item.keywords is not None:
            merged["keywords"] = list(item.keywords)
        if item.priority is not None:
            merged["priority"] = item.priority
        if item.enabled is not None:
            merged["enabled"] = bool(item.enabled)
        updates.append(
            (
                intent_id,
                normalize_intent_definition_payload(merged, intent_id=intent_id),
            )
        )
    try:
        await upsert_global_intent_definition_overrides(
            session,
            updates,
            updated_by_id=user.id,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to update intent definitions")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update intent definitions: {exc!s}",
        ) from exc
    return await _build_intent_response(session)


@router.get(
    "/intent-definitions/{intent_id}/history",
    response_model=IntentDefinitionHistoryResponse,
)
async def get_intent_definition_history(
    intent_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    normalized_intent_id = str(intent_id or "").strip().lower()
    if not normalized_intent_id:
        raise HTTPException(status_code=400, detail="intent_id is required")
    result = await session.execute(
        select(GlobalIntentDefinitionHistory)
        .filter(GlobalIntentDefinitionHistory.intent_id == normalized_intent_id)
        .order_by(GlobalIntentDefinitionHistory.created_at.desc())
        .limit(50)
    )
    items = []
    for row in result.scalars().all():
        items.append(
            {
                "intent_id": row.intent_id,
                "previous_payload": row.previous_payload,
                "new_payload": row.new_payload,
                "updated_at": row.created_at.isoformat(),
                "updated_by_id": str(row.updated_by_id)
                if row.updated_by_id
                else None,
            }
        )
    return {"items": items}
