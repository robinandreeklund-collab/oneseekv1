import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.bigtool_store import (
    build_global_tool_registry,
    build_tool_index,
    clear_tool_caches,
)
from app.db import (
    GlobalToolMetadataOverrideHistory,
    SearchSpaceMembership,
    User,
    get_async_session,
)
from app.schemas.admin_tool_settings import (
    ToolApplySuggestionsRequest,
    ToolApplySuggestionsResponse,
    ToolCategoryResponse,
    ToolEvaluationRequest,
    ToolEvaluationResponse,
    ToolMetadataHistoryResponse,
    ToolMetadataItem,
    ToolMetadataUpdateItem,
    ToolSettingsUpdateRequest,
    ToolSuggestionRequest,
    ToolSuggestionResponse,
    ToolSettingsResponse,
)
from app.services.connector_service import ConnectorService
from app.services.llm_service import get_agent_llm
from app.services.tool_evaluation_service import (
    compute_metadata_version_hash,
    generate_tool_metadata_suggestions,
    run_tool_evaluation,
)
from app.services.tool_metadata_service import (
    get_global_tool_metadata_overrides,
    merge_tool_metadata_overrides,
    normalize_tool_metadata_payload,
    tool_metadata_payload_equal,
    upsert_global_tool_metadata_overrides,
)
from app.users import current_active_user
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


async def _require_admin(
    session: AsyncSession,
    user: User,
) -> list[int]:
    result = await session.execute(
        select(SearchSpaceMembership.search_space_id)
        .filter(
            SearchSpaceMembership.user_id == user.id,
            SearchSpaceMembership.is_owner.is_(True),
        )
    )
    owned_search_space_ids = [int(row[0]) for row in result.all() if row and row[0] is not None]
    if not owned_search_space_ids:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to manage tool settings",
        )
    return owned_search_space_ids


def _category_name(category_id: str) -> str:
    cleaned = (category_id or "general").replace("_", " ").replace("/", " / ")
    words = [word.capitalize() for word in cleaned.split()]
    return " ".join(words) or "General"


def _metadata_payload_from_item(item: ToolMetadataUpdateItem) -> dict[str, Any]:
    return normalize_tool_metadata_payload(
        {
            "name": item.name,
            "description": item.description,
            "keywords": item.keywords,
            "example_queries": item.example_queries,
            "category": item.category,
            "base_path": item.base_path,
        }
    )


def _metadata_payload_from_entry(entry) -> dict[str, Any]:
    return normalize_tool_metadata_payload(
        {
            "name": entry.name,
            "description": entry.description,
            "keywords": list(entry.keywords),
            "example_queries": list(entry.example_queries),
            "category": entry.category,
            "base_path": entry.base_path,
        }
    )


def _tool_item_from_entry(entry, *, has_override: bool) -> ToolMetadataItem:
    return ToolMetadataItem(
        tool_id=entry.tool_id,
        name=entry.name,
        description=entry.description,
        keywords=list(entry.keywords),
        example_queries=list(entry.example_queries),
        category=entry.category,
        base_path=entry.base_path,
        has_override=has_override,
    )


def _group_tool_index_by_category(
    tool_index: list[Any],
    *,
    persisted_overrides: dict[str, dict[str, Any]],
) -> list[ToolCategoryResponse]:
    grouped: dict[str, list[ToolMetadataItem]] = {}
    for entry in tool_index:
        category_id = entry.category or "general"
        grouped.setdefault(category_id, []).append(
            _tool_item_from_entry(
                entry,
                has_override=entry.tool_id in persisted_overrides,
            )
        )
    categories: list[ToolCategoryResponse] = []
    for category_id in sorted(grouped.keys()):
        tools = sorted(grouped[category_id], key=lambda tool: tool.name.lower())
        categories.append(
            ToolCategoryResponse(
                category_id=category_id,
                category_name=_category_name(category_id),
                tools=tools,
            )
        )
    return categories


def _patch_map_from_updates(
    updates: list[ToolMetadataUpdateItem],
) -> dict[str, dict[str, Any]]:
    patch_map: dict[str, dict[str, Any]] = {}
    for item in updates:
        patch_map[item.tool_id] = _metadata_payload_from_item(item)
    return patch_map


async def _resolve_search_space_id(
    session: AsyncSession,
    user: User,
    *,
    requested_search_space_id: int | None,
) -> tuple[list[int], int]:
    owned_search_space_ids = await _require_admin(session, user)
    if requested_search_space_id is not None:
        if requested_search_space_id not in owned_search_space_ids:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to use this search space for admin eval",
            )
        return owned_search_space_ids, requested_search_space_id
    return owned_search_space_ids, owned_search_space_ids[0]


async def _build_tool_index_for_search_space(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
    metadata_patch: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    connector_service = ConnectorService(
        session,
        search_space_id=search_space_id,
        user_id=str(user.id),
    )
    dependencies = {
        "search_space_id": search_space_id,
        "db_session": session,
        "connector_service": connector_service,
        "user_id": str(user.id),
        "thread_id": 0,
    }
    tool_registry = await build_global_tool_registry(
        dependencies=dependencies,
        include_mcp_tools=False,
    )
    persisted_overrides = await get_global_tool_metadata_overrides(session)
    effective_overrides = merge_tool_metadata_overrides(
        persisted_overrides,
        metadata_patch,
    )
    tool_index = build_tool_index(
        tool_registry,
        metadata_overrides=effective_overrides,
    )
    return tool_index, persisted_overrides, effective_overrides


async def _build_tool_settings_response(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
) -> ToolSettingsResponse:
    tool_index, persisted_overrides, _effective_overrides = (
        await _build_tool_index_for_search_space(
            session,
            user,
            search_space_id=search_space_id,
            metadata_patch=None,
        )
    )
    categories = _group_tool_index_by_category(
        tool_index,
        persisted_overrides=persisted_overrides,
    )
    return ToolSettingsResponse(
        categories=categories,
        metadata_version_hash=compute_metadata_version_hash(tool_index),
        search_space_id=search_space_id,
    )


async def _apply_tool_metadata_updates(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
    updates: list[ToolMetadataUpdateItem],
) -> ToolSettingsResponse:
    connector_service = ConnectorService(
        session,
        search_space_id=search_space_id,
        user_id=str(user.id),
    )
    dependencies = {
        "search_space_id": search_space_id,
        "db_session": session,
        "connector_service": connector_service,
        "user_id": str(user.id),
        "thread_id": 0,
    }
    tool_registry = await build_global_tool_registry(
        dependencies=dependencies,
        include_mcp_tools=False,
    )
    default_tool_index = build_tool_index(tool_registry)
    defaults_by_tool = {entry.tool_id: _metadata_payload_from_entry(entry) for entry in default_tool_index}
    update_rows: list[tuple[str, dict[str, Any] | None]] = []
    for item in updates:
        if item.tool_id not in defaults_by_tool:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown tool_id in payload: {item.tool_id}",
            )
        normalized_payload = _metadata_payload_from_item(item)
        default_payload = defaults_by_tool[item.tool_id]
        override_payload = (
            None
            if tool_metadata_payload_equal(normalized_payload, default_payload)
            else normalized_payload
        )
        update_rows.append((item.tool_id, override_payload))
    try:
        await upsert_global_tool_metadata_overrides(
            session,
            update_rows,
            updated_by_id=user.id,
        )
        await session.commit()
        clear_tool_caches()
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to update tool metadata")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update tool metadata: {exc!s}",
        ) from exc
    return await _build_tool_settings_response(
        session,
        user,
        search_space_id=search_space_id,
    )


@router.get(
    "/tool-settings",
    response_model=ToolSettingsResponse,
)
async def get_tool_settings(
    search_space_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get effective tool metadata organized by category."""
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=search_space_id,
    )
    return await _build_tool_settings_response(
        session,
        user,
        search_space_id=resolved_search_space_id,
    )


@router.put(
    "/tool-settings",
    response_model=ToolSettingsResponse,
)
async def update_tool_settings(
    payload: ToolSettingsUpdateRequest,
    search_space_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Persist tool metadata overrides."""
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=search_space_id,
    )
    return await _apply_tool_metadata_updates(
        session,
        user,
        search_space_id=resolved_search_space_id,
        updates=payload.tools,
    )


@router.get(
    "/tool-settings/history/{tool_id}",
    response_model=ToolMetadataHistoryResponse,
)
async def get_tool_settings_history(
    tool_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    result = await session.execute(
        select(GlobalToolMetadataOverrideHistory)
        .filter(GlobalToolMetadataOverrideHistory.tool_id == tool_id)
        .order_by(GlobalToolMetadataOverrideHistory.created_at.desc())
        .limit(50)
    )
    items = []
    for row in result.scalars().all():
        items.append(
            {
                "tool_id": row.tool_id,
                "previous_payload": row.previous_payload,
                "new_payload": row.new_payload,
                "updated_at": row.created_at.isoformat(),
                "updated_by_id": str(row.updated_by_id) if row.updated_by_id else None,
            }
        )
    return {"items": items}


@router.post(
    "/tool-settings/evaluate",
    response_model=ToolEvaluationResponse,
)
async def evaluate_tool_settings(
    payload: ToolEvaluationRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    if not payload.tests:
        raise HTTPException(
            status_code=400,
            detail="Evaluation payload must include at least one test case",
        )
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=payload.search_space_id,
    )
    patch_map = _patch_map_from_updates(payload.metadata_patch)
    tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_index_for_search_space(
            session,
            user,
            search_space_id=resolved_search_space_id,
            metadata_patch=patch_map,
        )
    )
    llm = await get_agent_llm(session, resolved_search_space_id)
    evaluation = await run_tool_evaluation(
        tests=[
            {
                "id": test.id,
                "question": test.question,
                "expected": {
                    "tool": test.expected.tool if test.expected else None,
                    "category": test.expected.category if test.expected else None,
                },
                "allowed_tools": list(test.allowed_tools),
            }
            for test in payload.tests
        ],
        tool_index=tool_index,
        llm=llm,
        retrieval_limit=payload.retrieval_limit,
    )
    suggestions = await generate_tool_metadata_suggestions(
        evaluation_results=evaluation["results"],
        tool_index=tool_index,
        llm=llm,
    )
    return {
        "eval_name": payload.eval_name,
        "target_success_rate": payload.target_success_rate,
        "metrics": evaluation["metrics"],
        "results": evaluation["results"],
        "suggestions": suggestions,
        "metadata_version_hash": compute_metadata_version_hash(tool_index),
        "search_space_id": resolved_search_space_id,
    }


@router.post(
    "/tool-settings/suggestions",
    response_model=ToolSuggestionResponse,
)
async def generate_tool_suggestions(
    payload: ToolSuggestionRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=payload.search_space_id,
    )
    patch_map = _patch_map_from_updates(payload.metadata_patch)
    tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_index_for_search_space(
            session,
            user,
            search_space_id=resolved_search_space_id,
            metadata_patch=patch_map,
        )
    )
    llm = await get_agent_llm(session, resolved_search_space_id)
    failed_case_dicts = [
        {
            "test_id": case.test_id,
            "question": case.question,
            "expected_tool": case.expected_tool,
            "expected_category": case.expected_category,
            "selected_tool": case.selected_tool,
            "selected_category": case.selected_category,
            "passed_tool": case.passed_tool,
            "passed_category": case.passed_category,
            "passed": case.passed,
        }
        for case in payload.failed_cases
    ]
    suggestions = await generate_tool_metadata_suggestions(
        evaluation_results=failed_case_dicts,
        tool_index=tool_index,
        llm=llm,
    )
    return {"suggestions": suggestions}


@router.post(
    "/tool-settings/apply-suggestions",
    response_model=ToolApplySuggestionsResponse,
)
async def apply_tool_suggestions(
    payload: ToolApplySuggestionsRequest,
    search_space_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=search_space_id,
    )
    updates: list[ToolMetadataUpdateItem] = []
    for suggestion in payload.suggestions:
        if suggestion.proposed_metadata.tool_id != suggestion.tool_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Suggestion payload mismatch: proposed_metadata.tool_id must "
                    "match suggestion.tool_id"
                ),
            )
        updates.append(suggestion.proposed_metadata)
    settings = await _apply_tool_metadata_updates(
        session,
        user,
        search_space_id=resolved_search_space_id,
        updates=updates,
    )
    return {
        "applied_tool_ids": [update.tool_id for update in updates],
        "settings": settings,
    }
