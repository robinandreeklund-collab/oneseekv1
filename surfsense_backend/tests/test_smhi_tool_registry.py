"""Tests for SMHI tool registry construction."""

import pytest

try:
    from app.agents.new_chat.tools.smhi import (
        SMHI_TOOL_DEFINITIONS,
        build_smhi_tool_registry,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - optional local deps
    pytest.skip(
        f"Skipping SMHI tool registry tests because optional dependency is missing: {exc}",
        allow_module_level=True,
    )


def test_smhi_tool_registry_contains_all_definitions():
    registry = build_smhi_tool_registry()
    expected_ids = {definition.tool_id for definition in SMHI_TOOL_DEFINITIONS}

    assert set(registry.keys()) == expected_ids


def test_smhi_tools_have_matching_names():
    registry = build_smhi_tool_registry()
    for definition in SMHI_TOOL_DEFINITIONS:
        tool = registry[definition.tool_id]
        assert tool.name == definition.tool_id
