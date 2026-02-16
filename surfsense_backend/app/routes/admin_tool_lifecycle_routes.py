"""
Admin routes for Tool Lifecycle Management.

Provides endpoints for managing tool lifecycle status, viewing metrics,
and performing emergency rollbacks.
"""

import logging
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import (
    GlobalToolLifecycleStatus,
    SearchSpaceMembership,
    ToolLifecycleStatus,
    User,
    get_async_session,
)
from app.services.tool_lifecycle_service import (
    get_all_tool_lifecycle_statuses,
    get_tool_lifecycle_status,
    set_tool_status,
    initialize_tool_lifecycle_statuses,
)
from app.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ToolLifecycleStatusResponse(BaseModel):
    """Response model for a single tool lifecycle status."""
    
    tool_id: str
    status: str
    success_rate: Optional[float] = None
    total_tests: Optional[int] = None
    last_eval_at: Optional[datetime] = None
    required_success_rate: float
    changed_by_id: Optional[str] = None
    changed_at: datetime
    notes: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ToolLifecycleListResponse(BaseModel):
    """Response model for list of tool lifecycle statuses."""
    
    tools: list[ToolLifecycleStatusResponse]
    total_count: int
    live_count: int
    review_count: int


class ToolLifecycleUpdateRequest(BaseModel):
    """Request model for updating tool lifecycle status."""
    
    status: str = Field(..., pattern="^(review|live)$")
    notes: Optional[str] = None


class ToolLifecycleRollbackRequest(BaseModel):
    """Request model for emergency rollback."""
    
    notes: str = Field(..., min_length=1, description="Reason for emergency rollback")


# ============================================================================
# Helper Functions
# ============================================================================


async def _require_admin(
    session: AsyncSession,
    user: User,
) -> None:
    """Verify user has admin permissions (is owner of at least one search space)."""
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
            detail="You don't have permission to manage tool lifecycle",
        )


# ============================================================================
# Routes
# ============================================================================


@router.get(
    "/tool-lifecycle",
    response_model=ToolLifecycleListResponse,
)
async def list_tool_lifecycle(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    List all tool lifecycle statuses with metrics.
    
    Returns summary counts and detailed status for each tool.
    Automatically initializes tools if table is empty.
    """
    await _require_admin(session, user)
    
    # Get all lifecycle statuses
    statuses = await get_all_tool_lifecycle_statuses(session)
    
    # If empty, initialize with all registered tools
    if not statuses:
        from app.agents.new_chat.tools.registry import get_all_tool_names
        
        tool_names = get_all_tool_names()
        if tool_names:
            await initialize_tool_lifecycle_statuses(
                session, 
                tool_names, 
                default_status=ToolLifecycleStatus.REVIEW
            )
            # Re-fetch after initialization
            statuses = await get_all_tool_lifecycle_statuses(session)
    
    # Calculate summary stats
    live_count = sum(1 for s in statuses if s.status == ToolLifecycleStatus.LIVE)
    review_count = sum(1 for s in statuses if s.status == ToolLifecycleStatus.REVIEW)
    
    # Convert to response models
    tool_responses = [
        ToolLifecycleStatusResponse(
            tool_id=s.tool_id,
            status=s.status.value,
            success_rate=s.success_rate,
            total_tests=s.total_tests,
            last_eval_at=s.last_eval_at,
            required_success_rate=s.required_success_rate,
            changed_by_id=str(s.changed_by_id) if s.changed_by_id else None,
            changed_at=s.changed_at,
            notes=s.notes,
            created_at=s.created_at,
        )
        for s in statuses
    ]
    
    return ToolLifecycleListResponse(
        tools=tool_responses,
        total_count=len(statuses),
        live_count=live_count,
        review_count=review_count,
    )


@router.put(
    "/tool-lifecycle/{tool_id}",
    response_model=ToolLifecycleStatusResponse,
)
async def update_tool_lifecycle(
    tool_id: str,
    request: ToolLifecycleUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Update tool lifecycle status.
    
    Validates that the tool meets requirements before allowing promotion to live.
    """
    await _require_admin(session, user)
    
    # Parse status
    try:
        new_status = ToolLifecycleStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {request.status}. Must be 'review' or 'live'.",
        )
    
    # If promoting to live, check if tool meets threshold
    if new_status == ToolLifecycleStatus.LIVE:
        existing = await get_tool_lifecycle_status(session, tool_id)
        if existing and existing.success_rate is not None:
            if existing.success_rate < existing.required_success_rate:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Tool does not meet required success rate. "
                        f"Current: {existing.success_rate:.2%}, "
                        f"Required: {existing.required_success_rate:.2%}"
                    ),
                )
    
    # Update status
    updated = await set_tool_status(
        session,
        tool_id,
        new_status,
        user_id=user.id,
        notes=request.notes,
    )
    
    logger.info(f"Tool {tool_id} status updated to {new_status.value} by user {user.id}")
    
    return ToolLifecycleStatusResponse(
        tool_id=updated.tool_id,
        status=updated.status.value,
        success_rate=updated.success_rate,
        total_tests=updated.total_tests,
        last_eval_at=updated.last_eval_at,
        required_success_rate=updated.required_success_rate,
        changed_by_id=str(updated.changed_by_id) if updated.changed_by_id else None,
        changed_at=updated.changed_at,
        notes=updated.notes,
        created_at=updated.created_at,
    )


@router.post(
    "/tool-lifecycle/{tool_id}/rollback",
    response_model=ToolLifecycleStatusResponse,
)
async def emergency_rollback_tool(
    tool_id: str,
    request: ToolLifecycleRollbackRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Emergency rollback: immediately set tool to review status.
    
    Used when a live tool is causing issues and needs to be taken offline quickly.
    """
    await _require_admin(session, user)
    
    # Get current status
    existing = await get_tool_lifecycle_status(session, tool_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Tool {tool_id} not found in lifecycle management",
        )
    
    if existing.status != ToolLifecycleStatus.LIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Tool {tool_id} is not live, cannot rollback",
        )
    
    # Perform rollback
    notes = f"EMERGENCY ROLLBACK: {request.notes}"
    updated = await set_tool_status(
        session,
        tool_id,
        ToolLifecycleStatus.REVIEW,
        user_id=user.id,
        notes=notes,
    )
    
    logger.warning(
        f"Emergency rollback performed for tool {tool_id} by user {user.id}: {request.notes}"
    )
    
    return ToolLifecycleStatusResponse(
        tool_id=updated.tool_id,
        status=updated.status.value,
        success_rate=updated.success_rate,
        total_tests=updated.total_tests,
        last_eval_at=updated.last_eval_at,
        required_success_rate=updated.required_success_rate,
        changed_by_id=str(updated.changed_by_id) if updated.changed_by_id else None,
        changed_at=updated.changed_at,
        notes=updated.notes,
        created_at=updated.created_at,
    )


@router.post(
    "/tool-lifecycle/bulk-promote",
)
async def bulk_promote_tools_to_live(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Bulk promote all tools in REVIEW status to LIVE status.
    
    This is intended for initial setup to promote existing production tools
    that were initialized as REVIEW. Bypasses success rate threshold checks.
    
    Use with caution - only for migrating existing tools to the lifecycle system.
    """
    await _require_admin(session, user)
    
    # Get all tools in REVIEW status
    statuses = await get_all_tool_lifecycle_statuses(session)
    review_tools = [s for s in statuses if s.status == ToolLifecycleStatus.REVIEW]
    
    if not review_tools:
        return {
            "message": "No tools in REVIEW status to promote",
            "promoted_count": 0,
        }
    
    # Promote all to LIVE (bypass threshold check)
    promoted_count = 0
    for tool_status in review_tools:
        try:
            await set_tool_status(
                session,
                tool_status.tool_id,
                ToolLifecycleStatus.LIVE,
                user_id=user.id,
                notes="Bulk promotion: Existing production tool migrated to lifecycle system",
            )
            promoted_count += 1
        except Exception as e:
            logger.error(f"Failed to promote tool {tool_status.tool_id}: {e}")
    
    logger.info(
        f"Bulk promotion completed by user {user.id}: "
        f"{promoted_count}/{len(review_tools)} tools promoted to LIVE"
    )
    
    return {
        "message": f"Successfully promoted {promoted_count} tools to LIVE status",
        "promoted_count": promoted_count,
        "total_review_tools": len(review_tools),
    }

