from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.retrieval_feedback import query_pattern_hash
from app.db import GlobalRetrievalFeedbackSignal, async_session_maker


def _normalize_tool_id(tool_id: str) -> str:
    return str(tool_id or "").strip().lower()


async def upsert_retrieval_feedback_signal(
    session: AsyncSession,
    *,
    tool_id: str,
    query: str,
    success: bool,
) -> bool:
    normalized_tool_id = _normalize_tool_id(tool_id)
    pattern_hash = query_pattern_hash(query)
    if not normalized_tool_id or not pattern_hash:
        return False

    success_inc = 1 if bool(success) else 0
    failure_inc = 0 if bool(success) else 1
    now = datetime.now(UTC)
    statement = insert(GlobalRetrievalFeedbackSignal).values(
        tool_id=normalized_tool_id,
        query_pattern_hash=pattern_hash,
        successes=success_inc,
        failures=failure_inc,
        updated_at=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["tool_id", "query_pattern_hash"],
        set_={
            "successes": GlobalRetrievalFeedbackSignal.successes + success_inc,
            "failures": GlobalRetrievalFeedbackSignal.failures + failure_inc,
            "updated_at": now,
        },
    )
    await session.execute(statement)
    return True


async def persist_retrieval_feedback_signal(
    *,
    tool_id: str,
    query: str,
    success: bool,
) -> bool:
    async with async_session_maker() as session:
        try:
            persisted = await upsert_retrieval_feedback_signal(
                session,
                tool_id=tool_id,
                query=query,
                success=success,
            )
            if persisted:
                await session.commit()
            else:
                await session.rollback()
            return persisted
        except Exception:
            await session.rollback()
            return False


async def load_retrieval_feedback_snapshot(
    session: AsyncSession,
    *,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 10000))
    result = await session.execute(
        select(GlobalRetrievalFeedbackSignal)
        .order_by(GlobalRetrievalFeedbackSignal.updated_at.desc())
        .limit(safe_limit)
    )
    rows: list[dict[str, Any]] = []
    for item in result.scalars().all():
        rows.append(
            {
                "tool_id": str(item.tool_id or "").strip().lower(),
                "query_pattern_hash": str(item.query_pattern_hash or "").strip().lower(),
                "successes": int(item.successes or 0),
                "failures": int(item.failures or 0),
            }
        )
    return rows
