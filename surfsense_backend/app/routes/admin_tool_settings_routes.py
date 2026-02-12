import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.geoapify_maps import GEOAPIFY_TOOL_DEFINITIONS
from app.db import SearchSpaceMembership, User, get_async_session
from app.schemas.admin_tool_settings import (
    ToolCategoryResponse,
    ToolMetadataItem,
    ToolSettingsResponse,
)
from app.users import current_active_user
from sqlalchemy.future import select

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
            detail="You don't have permission to manage tool settings",
        )


@router.get(
    "/tool-settings",
    response_model=ToolSettingsResponse,
)
async def get_tool_settings(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get all tool definitions organized by category."""
    await _require_admin(session, user)

    categories: list[ToolCategoryResponse] = []

    # Riksdagen tools
    riksdagen_tools = [
        ToolMetadataItem(
            tool_id=tool.tool_id,
            name=tool.name,
            description=tool.description,
            keywords=list(tool.keywords),
            example_queries=list(tool.example_queries),
            category=tool.category,
            base_path=None,
        )
        for tool in RIKSDAGEN_TOOL_DEFINITIONS
    ]
    if riksdagen_tools:
        categories.append(
            ToolCategoryResponse(
                category_id="riksdagen",
                category_name="Riksdagen",
                tools=riksdagen_tools,
            )
        )

    # SCB tools
    scb_tools = [
        ToolMetadataItem(
            tool_id=tool.tool_id,
            name=tool.name,
            description=tool.description,
            keywords=list(tool.keywords),
            example_queries=list(tool.example_queries),
            category="statistics",
            base_path=tool.base_path,
        )
        for tool in SCB_TOOL_DEFINITIONS
    ]
    if scb_tools:
        categories.append(
            ToolCategoryResponse(
                category_id="scb",
                category_name="SCB Statistik",
                tools=scb_tools,
            )
        )

    # Bolagsverket tools
    bolagsverket_tools = [
        ToolMetadataItem(
            tool_id=tool.tool_id,
            name=tool.name,
            description=tool.description,
            keywords=list(tool.keywords),
            example_queries=list(tool.example_queries),
            category=tool.category,
            base_path=tool.base_path,
        )
        for tool in BOLAGSVERKET_TOOL_DEFINITIONS
    ]
    if bolagsverket_tools:
        categories.append(
            ToolCategoryResponse(
                category_id="bolagsverket",
                category_name="Bolagsverket",
                tools=bolagsverket_tools,
            )
        )

    # Trafikverket tools
    trafikverket_tools = [
        ToolMetadataItem(
            tool_id=tool.tool_id,
            name=tool.name,
            description=tool.description,
            keywords=list(tool.keywords),
            example_queries=list(tool.example_queries),
            category=tool.category,
            base_path=tool.base_path,
        )
        for tool in TRAFIKVERKET_TOOL_DEFINITIONS
    ]
    if trafikverket_tools:
        categories.append(
            ToolCategoryResponse(
                category_id="trafikverket",
                category_name="Trafikverket",
                tools=trafikverket_tools,
            )
        )

    # Geoapify tools
    geoapify_tools = [
        ToolMetadataItem(
            tool_id=tool.tool_id,
            name=tool.name,
            description=tool.description,
            keywords=list(tool.keywords),
            example_queries=list(tool.example_queries),
            category=tool.category,
            base_path=tool.base_path,
        )
        for tool in GEOAPIFY_TOOL_DEFINITIONS
    ]
    if geoapify_tools:
        categories.append(
            ToolCategoryResponse(
                category_id="geoapify",
                category_name="Geoapify Maps",
                tools=geoapify_tools,
            )
        )

    return ToolSettingsResponse(categories=categories)
