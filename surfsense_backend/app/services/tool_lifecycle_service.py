"""
Tool Lifecycle Management Service

Manages the lifecycle of tools from review to live status.
Includes integration with eval metrics and audit trail tracking.
"""

import logging
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import GlobalToolLifecycleStatus, ToolLifecycleStatus

logger = logging.getLogger(__name__)


async def get_live_tool_ids(session: AsyncSession) -> list[str]:
    """
    Get all tool IDs that have 'live' status.
    
    Args:
        session: Database session
        
    Returns:
        List of tool IDs with live status
    """
    try:
        result = await session.execute(
            select(GlobalToolLifecycleStatus.tool_id).filter(
                GlobalToolLifecycleStatus.status == ToolLifecycleStatus.LIVE
            )
        )
        return [row[0] for row in result.fetchall()]
    except Exception as e:
        logger.exception("Failed to fetch live tool IDs")
        # Fallback: return empty list, tools will be loaded via default behavior
        return []


async def set_tool_status(
    session: AsyncSession,
    tool_id: str,
    status: ToolLifecycleStatus,
    user_id: Optional[UUID] = None,
    notes: Optional[str] = None,
) -> GlobalToolLifecycleStatus:
    """
    Update tool status with audit trail.
    
    Args:
        session: Database session
        tool_id: Tool identifier
        status: New status (review or live)
        user_id: ID of user making the change
        notes: Optional notes about the change
        
    Returns:
        Updated GlobalToolLifecycleStatus record
    """
    # Get or create record
    result = await session.execute(
        select(GlobalToolLifecycleStatus).filter(
            GlobalToolLifecycleStatus.tool_id == tool_id
        )
    )
    record = result.scalar_one_or_none()
    
    if record is None:
        # Create new record
        record = GlobalToolLifecycleStatus(
            tool_id=tool_id,
            status=status,
            changed_by_id=user_id,
            changed_at=datetime.now(UTC),
            notes=notes,
        )
        session.add(record)
        logger.info(f"Created new lifecycle status for tool {tool_id}: {status}")
    else:
        # Update existing record
        old_status = record.status
        record.status = status
        record.changed_by_id = user_id
        record.changed_at = datetime.now(UTC)
        if notes:
            record.notes = notes
        logger.info(f"Updated tool {tool_id} status: {old_status} -> {status}")
    
    await session.commit()
    await session.refresh(record)
    return record


async def update_eval_metrics(
    session: AsyncSession,
    tool_id: str,
    success_rate: float,
    total_tests: int,
) -> GlobalToolLifecycleStatus:
    """
    Update eval metrics for a tool from eval results.
    
    Args:
        session: Database session
        tool_id: Tool identifier
        success_rate: Success rate from eval (0.0 to 1.0)
        total_tests: Number of tests run
        
    Returns:
        Updated GlobalToolLifecycleStatus record
    """
    # Get or create record
    result = await session.execute(
        select(GlobalToolLifecycleStatus).filter(
            GlobalToolLifecycleStatus.tool_id == tool_id
        )
    )
    record = result.scalar_one_or_none()
    
    if record is None:
        # Create new record with default review status
        record = GlobalToolLifecycleStatus(
            tool_id=tool_id,
            status=ToolLifecycleStatus.REVIEW,
            success_rate=success_rate,
            total_tests=total_tests,
            last_eval_at=datetime.now(UTC),
        )
        session.add(record)
        logger.info(f"Created lifecycle status for tool {tool_id} with eval metrics")
    else:
        # Update metrics
        record.success_rate = success_rate
        record.total_tests = total_tests
        record.last_eval_at = datetime.now(UTC)
        logger.info(f"Updated eval metrics for tool {tool_id}: {success_rate:.2%}")
    
    await session.commit()
    await session.refresh(record)
    return record


async def get_all_tool_lifecycle_statuses(
    session: AsyncSession,
) -> list[GlobalToolLifecycleStatus]:
    """
    Get all tool lifecycle statuses for admin UI.
    
    Args:
        session: Database session
        
    Returns:
        List of all GlobalToolLifecycleStatus records
    """
    result = await session.execute(
        select(GlobalToolLifecycleStatus).order_by(
            GlobalToolLifecycleStatus.status,
            GlobalToolLifecycleStatus.tool_id,
        )
    )
    return list(result.scalars().all())


async def get_tool_lifecycle_status(
    session: AsyncSession,
    tool_id: str,
) -> Optional[GlobalToolLifecycleStatus]:
    """
    Get lifecycle status for a specific tool.
    
    Args:
        session: Database session
        tool_id: Tool identifier
        
    Returns:
        GlobalToolLifecycleStatus record or None if not found
    """
    result = await session.execute(
        select(GlobalToolLifecycleStatus).filter(
            GlobalToolLifecycleStatus.tool_id == tool_id
        )
    )
    return result.scalar_one_or_none()


async def initialize_tool_lifecycle_statuses(
    session: AsyncSession,
    tool_ids: list[str],
    default_status: ToolLifecycleStatus = ToolLifecycleStatus.REVIEW,
) -> int:
    """
    Initialize lifecycle statuses for tools that don't have one.
    Useful for bootstrapping existing tools.
    
    Args:
        session: Database session
        tool_ids: List of tool IDs to initialize
        default_status: Default status to assign (default: REVIEW)
        
    Returns:
        Number of new records created
    """
    created_count = 0
    
    for tool_id in tool_ids:
        result = await session.execute(
            select(GlobalToolLifecycleStatus).filter(
                GlobalToolLifecycleStatus.tool_id == tool_id
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing is None:
            record = GlobalToolLifecycleStatus(
                tool_id=tool_id,
                status=default_status,
            )
            session.add(record)
            created_count += 1
    
    if created_count > 0:
        await session.commit()
        logger.info(f"Initialized {created_count} tool lifecycle statuses")
    
    return created_count
