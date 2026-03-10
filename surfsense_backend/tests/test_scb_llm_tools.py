"""Tests for app.agents.new_chat.tools.scb_llm_tools — LLM-driven SCB tools."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Direct-import the module file to bypass tools/__init__.py which triggers Config init
# (the __init__.py chain loads smhi_weather → app.config → embedding model setup).
import importlib.util as _ilu
import pathlib

_module_path = pathlib.Path(__file__).resolve().parent.parent / "app" / "agents" / "new_chat" / "tools" / "scb_llm_tools.py"
_spec = _ilu.spec_from_file_location("scb_llm_tools", _module_path)
_mod = _ilu.module_from_spec(_spec)
sys.modules["scb_llm_tools"] = _mod
_spec.loader.exec_module(_mod)

_find_closest_values = _mod._find_closest_values
_find_closest_variables = _mod._find_closest_variables
_format_table_inspection = _mod._format_table_inspection
_fuzzy_match_values = _mod._fuzzy_match_values
create_scb_search_and_inspect_tool = _mod.create_scb_search_and_inspect_tool
create_scb_validate_selection_tool = _mod.create_scb_validate_selection_tool
create_scb_fetch_validated_tool = _mod.create_scb_fetch_validated_tool


# ---------------------------------------------------------------------------
# _format_table_inspection
# ---------------------------------------------------------------------------


class TestFormatTableInspection:
    """Test the table inspection formatting."""

    def _make_metadata(self, variables):
        return {"variables": variables}

    def test_basic_formatting(self):
        meta = self._make_metadata([
            {
                "code": "Region",
                "text": "region",
                "values": ["00", "0180"],
                "valueTexts": ["Riket", "Stockholm"],
            },
            {
                "code": "Tid",
                "text": "år",
                "values": ["2022", "2023"],
                "valueTexts": ["2022", "2023"],
            },
        ])
        result = _format_table_inspection("TAB123", "Test Table", meta)

        assert result["table_id"] == "TAB123"
        assert result["title"] == "Test Table"
        assert len(result["variables"]) == 2
        assert result["selection_rules"]["all_variables_required"] is True

    def test_variable_type_detection(self):
        meta = self._make_metadata([
            {"code": "Region", "text": "region", "values": ["00"], "valueTexts": ["Riket"]},
            {"code": "Tid", "text": "år", "values": ["2023"], "valueTexts": ["2023"]},
            {"code": "Kon", "text": "kön", "values": ["1", "2"], "valueTexts": ["män", "kvinnor"]},
            {"code": "ContentsCode", "text": "tabellinnehåll", "values": ["BE01"], "valueTexts": ["Folkmängd"]},
        ])
        result = _format_table_inspection("TAB123", "Test", meta)

        var_types = {v["code"]: v["type"] for v in result["variables"]}
        assert var_types["Region"] == "region"
        assert var_types["Tid"] == "time"
        assert var_types["Kon"] == "gender"
        assert var_types["ContentsCode"] == "measure"

    def test_value_truncation(self):
        """When there are more values than _MAX_VALUES_TO_SHOW, only show a sample."""
        many_values = [str(i) for i in range(100)]
        meta = self._make_metadata([
            {
                "code": "Region",
                "text": "region",
                "values": many_values,
                "valueTexts": many_values,
            },
        ])
        result = _format_table_inspection("TAB123", "Test", meta)
        var = result["variables"][0]
        assert var["total_values"] == 100
        assert len(var["values"]) <= 25
        assert "note" in var

    def test_time_hint(self):
        meta = self._make_metadata([
            {"code": "Tid", "text": "år", "values": ["2020", "2021", "2022", "2023"], "valueTexts": []},
        ])
        result = _format_table_inspection("TAB123", "Test", meta)
        var = result["variables"][0]
        assert "hint" in var
        assert "2023" in var["hint"]  # Latest
        assert "2020" in var["hint"]  # Earliest

    def test_empty_variables(self):
        meta = self._make_metadata([])
        result = _format_table_inspection("TAB123", "Test", meta)
        assert result["variables"] == []

    def test_gender_hint(self):
        meta = self._make_metadata([
            {"code": "Kon", "text": "kön", "values": ["1", "2", "TOT"], "valueTexts": ["män", "kvinnor", "totalt"]},
        ])
        result = _format_table_inspection("TAB123", "Test", meta)
        var = result["variables"][0]
        assert "hint" in var
        assert "män" in var["hint"] or "1=" in var["hint"]

    def test_measure_hint(self):
        meta = self._make_metadata([
            {"code": "ContentsCode", "text": "tabellinnehåll", "values": ["BE01"], "valueTexts": ["Folkmängd"]},
        ])
        result = _format_table_inspection("TAB123", "Test", meta)
        var = result["variables"][0]
        assert var["type"] == "measure"
        assert "REQUIRED" in var.get("hint", "")


# ---------------------------------------------------------------------------
# Fuzzy matching helpers
# ---------------------------------------------------------------------------


class TestFindClosestVariables:
    def test_exact_substring(self):
        result = _find_closest_variables("Reg", ["Region", "Tid", "Kon"])
        assert "Region" in result

    def test_no_match_returns_all(self):
        result = _find_closest_variables("zzz", ["Region", "Tid", "Kon"])
        # Should return up to 5 of the available codes as fallback
        assert len(result) <= 5
        assert "Region" in result or "Tid" in result


class TestFindClosestValues:
    def test_exact_match_in_text(self):
        result = _find_closest_values(
            "Stockholm",
            ["0180", "1480"],
            ["Stockholm", "Göteborg"],
        )
        assert any("0180" in s for s in result)

    def test_normalized_match(self):
        result = _find_closest_values(
            "Goteborg",
            ["0180", "1480"],
            ["Stockholm", "Göteborg"],
        )
        assert any("1480" in s for s in result)

    def test_no_match_returns_sample(self):
        result = _find_closest_values(
            "Narnia",
            ["0180", "1480"],
            ["Stockholm", "Göteborg"],
        )
        assert len(result) > 0  # Should return sample values


class TestFuzzyMatchValues:
    def test_normalized_exact(self):
        result = _fuzzy_match_values(
            "Goteborg",
            ["0180", "1480"],
            ["Stockholm", "Göteborg"],
        )
        assert result == ["1480"]

    def test_code_exact(self):
        result = _fuzzy_match_values(
            "0180",
            ["0180", "1480"],
            ["Stockholm", "Göteborg"],
        )
        assert result == ["0180"]

    def test_word_boundary_match(self):
        result = _fuzzy_match_values(
            "Stockholm",
            ["0180"],
            ["Stockholm kommun"],
        )
        assert result == ["0180"]

    def test_no_match(self):
        result = _fuzzy_match_values(
            "Narnia",
            ["0180", "1480"],
            ["Stockholm", "Göteborg"],
        )
        assert result == []


# ---------------------------------------------------------------------------
# Tool factory smoke tests (mock ScbService)
# ---------------------------------------------------------------------------


def _make_mock_service():
    """Create a mock ScbService with basic methods."""
    service = MagicMock()
    service.max_cells = 100000
    service.base_url = "https://api.scb.se/OV0104/v2beta/api/v2/"

    # search_tables returns SearchResult-like objects
    table = MagicMock()
    table.id = "TAB001"
    table.title = "Folkmängd efter region"
    table.path = "BE/BE0101/BE0101A/BesijlkFod662N"
    service.search_tables = AsyncMock(return_value=[table])

    # get_table_metadata returns variable structure
    service.get_table_metadata = AsyncMock(return_value={
        "variables": [
            {
                "code": "Region",
                "text": "region",
                "values": ["00", "0180", "1480"],
                "valueTexts": ["Riket", "Stockholm", "Göteborg"],
            },
            {
                "code": "Tid",
                "text": "år",
                "values": ["2022", "2023"],
                "valueTexts": ["2022", "2023"],
            },
            {
                "code": "ContentsCode",
                "text": "tabellinnehåll",
                "values": ["BE0101N1"],
                "valueTexts": ["Folkmängd"],
            },
        ],
    })

    # query_table returns data
    service.query_table = AsyncMock(return_value={"columns": [], "data": []})

    return service


class TestSearchAndInspectTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_search_and_inspect_tool(scb_service=service)
        assert tool_fn.name == "scb_search_and_inspect"

    def test_inspect_by_table_id(self):
        service = _make_mock_service()
        tool_fn = create_scb_search_and_inspect_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"query": "", "table_id": "TAB001"})
        )
        data = json.loads(result)
        assert data["table_id"] == "TAB001"
        assert "variables" in data

    def test_search_returns_tables(self):
        service = _make_mock_service()
        tool_fn = create_scb_search_and_inspect_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"query": "befolkning"})
        )
        data = json.loads(result)
        assert "tables" in data or "tables_inspected" in data

    def test_empty_query_and_table_id(self):
        service = _make_mock_service()
        tool_fn = create_scb_search_and_inspect_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"query": ""})
        )
        data = json.loads(result)
        assert "error" in data


class TestValidateSelectionTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_selection_tool(scb_service=service)
        assert tool_fn.name == "scb_validate_selection"

    def test_valid_selection(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_selection_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["00"],
                    "Tid": ["2023"],
                    "ContentsCode": ["BE0101N1"],
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "valid"
        assert data["estimated_cells"] == 1

    def test_missing_variable(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_selection_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["00"],
                    # Missing Tid and ContentsCode
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "invalid"
        assert len(data["errors"]) >= 1
        # Should mention missing variables
        error_vars = [e["variable"] for e in data["errors"]]
        assert "Tid" in error_vars or "ContentsCode" in error_vars

    def test_invalid_value_code(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_selection_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["9999"],  # Invalid code
                    "Tid": ["2023"],
                    "ContentsCode": ["BE0101N1"],
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "invalid"

    def test_region_fuzzy_resolution(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_selection_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["Stockholm"],  # Name instead of code
                    "Tid": ["2023"],
                    "ContentsCode": ["BE0101N1"],
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "valid"
        # Should have resolved "Stockholm" to "0180"
        assert "0180" in data["selection"]["Region"]
        assert len(data["warnings"]) > 0

    def test_gender_alias_resolution(self):
        """Test that 'man'/'kvinna' resolve to '1'/'2'."""
        service = _make_mock_service()
        # Add gender variable
        service.get_table_metadata = AsyncMock(return_value={
            "variables": [
                {
                    "code": "Region",
                    "text": "region",
                    "values": ["00"],
                    "valueTexts": ["Riket"],
                },
                {
                    "code": "Kon",
                    "text": "kön",
                    "values": ["1", "2", "TOT"],
                    "valueTexts": ["män", "kvinnor", "totalt"],
                },
                {
                    "code": "Tid",
                    "text": "år",
                    "values": ["2023"],
                    "valueTexts": ["2023"],
                },
                {
                    "code": "ContentsCode",
                    "text": "tabellinnehåll",
                    "values": ["BE01"],
                    "valueTexts": ["Folkmängd"],
                },
            ],
        })
        tool_fn = create_scb_validate_selection_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["00"],
                    "Kon": ["man", "kvinna"],
                    "Tid": ["2023"],
                    "ContentsCode": ["BE01"],
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "valid"
        assert "1" in data["selection"]["Kon"]
        assert "2" in data["selection"]["Kon"]

    def test_empty_table_id(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_selection_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"table_id": "", "selection": {}})
        )
        data = json.loads(result)
        assert "error" in data


class TestFetchValidatedTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_fetch_validated_tool(scb_service=service)
        assert tool_fn.name == "scb_fetch_validated"

    def test_basic_fetch(self):
        service = _make_mock_service()
        tool_fn = create_scb_fetch_validated_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["00"],
                    "Tid": ["2023"],
                    "ContentsCode": ["BE0101N1"],
                },
            })
        )
        data = json.loads(result)
        assert data["source"] == "SCB PxWeb"
        assert data["table_id"] == "TAB001"
        assert "data" in data

    def test_empty_selection(self):
        service = _make_mock_service()
        tool_fn = create_scb_fetch_validated_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"table_id": "TAB001", "selection": {}})
        )
        data = json.loads(result)
        assert "error" in data
