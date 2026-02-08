from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import (
    AgentPromptOverride,
    AgentPromptOverrideHistory,
    GlobalAgentPromptOverride,
    GlobalAgentPromptOverrideHistory,
)


async def get_global_prompt_overrides(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(GlobalAgentPromptOverride))
    overrides = {}
    for row in result.scalars().all():
        if row.prompt_text is not None:
            overrides[row.key] = row.prompt_text
    return overrides


async def get_prompt_overrides(
    session: AsyncSession, search_space_id: int
) -> dict[str, str]:
    # Deprecated: keep for backward compatibility with search-space scoped endpoints.
    return await get_global_prompt_overrides(session)


async def upsert_global_prompt_overrides(
    session: AsyncSession,
    updates: Iterable[tuple[str, str | None]],
    *,
    updated_by_id=None,
) -> None:
    for key, prompt_text in updates:
        normalized = str(prompt_text).strip() if prompt_text is not None else None
        result = await session.execute(
            select(GlobalAgentPromptOverride).filter(
                GlobalAgentPromptOverride.key == key,
            )
        )
        existing = result.scalars().first()
        previous_text = existing.prompt_text if existing else None
        new_text = normalized if normalized else None

        if new_text is None:
            if existing:
                await session.delete(existing)
        else:
            if existing:
                existing.prompt_text = new_text
                if updated_by_id is not None:
                    existing.updated_by_id = updated_by_id
            else:
                session.add(
                    GlobalAgentPromptOverride(
                        key=key,
                        prompt_text=new_text,
                        updated_by_id=updated_by_id,
                    )
                )

        if previous_text != new_text:
            session.add(
                GlobalAgentPromptOverrideHistory(
                    key=key,
                    previous_prompt_text=previous_text,
                    new_prompt_text=new_text,
                    updated_by_id=updated_by_id,
                )
            )


async def upsert_prompt_overrides(
    session: AsyncSession,
    search_space_id: int,
    updates: Iterable[tuple[str, str | None]],
    *,
    updated_by_id=None,
) -> None:
    # Deprecated: keep for backward compatibility with search-space scoped endpoints.
    await upsert_global_prompt_overrides(
        session,
        updates,
        updated_by_id=updated_by_id,
    )
