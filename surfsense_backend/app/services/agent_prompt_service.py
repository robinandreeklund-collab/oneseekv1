from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AgentPromptOverride


async def get_prompt_overrides(
    session: AsyncSession, search_space_id: int
) -> dict[str, str]:
    result = await session.execute(
        select(AgentPromptOverride).filter(
            AgentPromptOverride.search_space_id == search_space_id
        )
    )
    overrides = {}
    for row in result.scalars().all():
        if row.prompt_text is not None:
            overrides[row.key] = row.prompt_text
    return overrides


async def upsert_prompt_overrides(
    session: AsyncSession,
    search_space_id: int,
    updates: Iterable[tuple[str, str | None]],
    *,
    updated_by_id=None,
) -> None:
    for key, prompt_text in updates:
        if prompt_text is None or not str(prompt_text).strip():
            await session.execute(
                AgentPromptOverride.__table__.delete().where(
                    AgentPromptOverride.search_space_id == search_space_id,
                    AgentPromptOverride.key == key,
                )
            )
            continue
        result = await session.execute(
            select(AgentPromptOverride).filter(
                AgentPromptOverride.search_space_id == search_space_id,
                AgentPromptOverride.key == key,
            )
        )
        existing = result.scalars().first()
        if existing:
            existing.prompt_text = str(prompt_text)
            if updated_by_id is not None:
                existing.updated_by_id = updated_by_id
        else:
            session.add(
                AgentPromptOverride(
                    search_space_id=search_space_id,
                    key=key,
                    prompt_text=str(prompt_text),
                    updated_by_id=updated_by_id,
                )
            )
