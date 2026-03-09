"""Riksdagen agent — shared dataclass and combined re-exports.

The actual tool definitions and builders live in:
  - riksdagen_dokument_agent.py  (documents + status)
  - riksdagen_debatt_agent.py    (speeches + votes)
  - riksdagen_ledamoter_agent.py (members + calendar)

This module keeps the RiksdagenToolDefinition dataclass (imported by the
sub-agents) and re-exports the combined RIKSDAGEN_TOOL_DEFINITIONS list
plus a combined build_riksdagen_tool_registry for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.connector_service import ConnectorService
from app.services.riksdagen_service import RiksdagenService


@dataclass(frozen=True)
class RiksdagenToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    doktyp: str | None = None  # Document type filter for sub-tools
    anftyp: str | None = None  # Speech type filter for sub-tools
    category: str = "riksdagen"


# Lazy helpers to avoid circular imports at module level
def _get_dokument_definitions() -> list[RiksdagenToolDefinition]:
    from app.agents.new_chat.riksdagen_dokument_agent import (
        RIKSDAGEN_DOKUMENT_TOOL_DEFINITIONS,
    )

    return RIKSDAGEN_DOKUMENT_TOOL_DEFINITIONS


def _get_debatt_definitions() -> list[RiksdagenToolDefinition]:
    from app.agents.new_chat.riksdagen_debatt_agent import (
        RIKSDAGEN_DEBATT_TOOL_DEFINITIONS,
    )

    return RIKSDAGEN_DEBATT_TOOL_DEFINITIONS


def _get_ledamoter_definitions() -> list[RiksdagenToolDefinition]:
    from app.agents.new_chat.riksdagen_ledamoter_agent import (
        RIKSDAGEN_LEDAMOTER_TOOL_DEFINITIONS,
    )

    return RIKSDAGEN_LEDAMOTER_TOOL_DEFINITIONS


def _all_definitions() -> list[RiksdagenToolDefinition]:
    return (
        _get_dokument_definitions()
        + _get_debatt_definitions()
        + _get_ledamoter_definitions()
    )


# Backward-compatible constant: combined list of all definitions across agents
RIKSDAGEN_TOOL_DEFINITIONS: list[RiksdagenToolDefinition] = _all_definitions()


def build_riksdagen_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    riksdagen_service: RiksdagenService | None = None,
) -> dict[str, Any]:
    """Build combined registry of ALL Riksdagen tools (backward-compatible)."""
    from app.agents.new_chat.riksdagen_debatt_agent import (
        build_riksdagen_debatt_tool_registry,
    )
    from app.agents.new_chat.riksdagen_dokument_agent import (
        build_riksdagen_dokument_tool_registry,
    )
    from app.agents.new_chat.riksdagen_ledamoter_agent import (
        build_riksdagen_ledamoter_tool_registry,
    )

    service = riksdagen_service or RiksdagenService()
    kwargs: dict[str, Any] = {
        "connector_service": connector_service,
        "search_space_id": search_space_id,
        "user_id": user_id,
        "thread_id": thread_id,
        "riksdagen_service": service,
    }

    registry: dict[str, Any] = {}
    registry.update(build_riksdagen_dokument_tool_registry(**kwargs))
    registry.update(build_riksdagen_debatt_tool_registry(**kwargs))
    registry.update(build_riksdagen_ledamoter_tool_registry(**kwargs))
    return registry
