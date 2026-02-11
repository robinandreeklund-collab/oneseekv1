"""Trafikverket tools entrypoint (refactored)."""

from __future__ import annotations

from app.agents.new_chat.tools.trafikverket_definitions import (
    TRAFIKVERKET_TOOL_DEFINITIONS,
    TRAFIKVERKET_TOOL_DEFINITION_MAP,
)
from app.agents.new_chat.tools.trafikverket_factory import (
    build_trafikverket_tool_registry,
    create_trafikverket_tool,
)

__all__ = [
    "TRAFIKVERKET_TOOL_DEFINITIONS",
    "TRAFIKVERKET_TOOL_DEFINITION_MAP",
    "build_trafikverket_tool_registry",
    "create_trafikverket_tool",
]
