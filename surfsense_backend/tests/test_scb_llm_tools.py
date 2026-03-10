"""Tests for app.agents.new_chat.tools.scb_llm_tools — 7-tool SCB pipeline."""

from __future__ import annotations

import asyncio
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
_is_v2_expression = _mod._is_v2_expression
_estimate_v2_expression_size = _mod._estimate_v2_expression_size
create_scb_search_tool = _mod.create_scb_search_tool
create_scb_browse_tool = _mod.create_scb_browse_tool
create_scb_inspect_tool = _mod.create_scb_inspect_tool
create_scb_validate_tool = _mod.create_scb_validate_tool
create_scb_fetch_tool = _mod.create_scb_fetch_tool
create_scb_preview_tool = _mod.create_scb_preview_tool
create_scb_codelist_tool = _mod.create_scb_codelist_tool


# ---------------------------------------------------------------------------
# _format_table_inspection (legacy compat)
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

    def test_eliminable_flag(self):
        meta = self._make_metadata([
            {
                "code": "Kon",
                "text": "kön",
                "values": ["1", "2"],
                "valueTexts": ["män", "kvinnor"],
                "elimination": True,
                "eliminationValueCode": "TOT",
            },
        ])
        result = _format_table_inspection("TAB123", "Test", meta)
        var = result["variables"][0]
        assert var["eliminable"] is True


# ---------------------------------------------------------------------------
# Fuzzy matching helpers
# ---------------------------------------------------------------------------


class TestFindClosestVariables:
    def test_exact_substring(self):
        result = _find_closest_variables("Reg", ["Region", "Tid", "Kon"])
        assert "Region" in result

    def test_no_match_returns_all(self):
        result = _find_closest_variables("zzz", ["Region", "Tid", "Kon"])
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
        assert len(result) > 0


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
# v2 expression detection
# ---------------------------------------------------------------------------


class TestV2Expressions:
    def test_top(self):
        assert _is_v2_expression("TOP(5)") is True
        assert _is_v2_expression("top(3)") is True
        assert _is_v2_expression("TOP(5, 2)") is True

    def test_bottom(self):
        assert _is_v2_expression("BOTTOM(3)") is True

    def test_from_to_range(self):
        assert _is_v2_expression("FROM(2020)") is True
        assert _is_v2_expression("TO(2024)") is True
        assert _is_v2_expression("RANGE(2020,2024)") is True

    def test_wildcards(self):
        assert _is_v2_expression("*") is True
        assert _is_v2_expression("01*") is True
        assert _is_v2_expression("*01") is True
        assert _is_v2_expression("?????") is True

    def test_not_expressions(self):
        assert _is_v2_expression("2023") is False
        assert _is_v2_expression("0180") is False
        assert _is_v2_expression("BE0101N1") is False

    def test_size_estimation(self):
        assert _estimate_v2_expression_size("TOP(5)", 100) == 5
        assert _estimate_v2_expression_size("*", 50) == 50
        assert _estimate_v2_expression_size("BOTTOM(10)", 100) == 10
        assert _estimate_v2_expression_size("TOP(200)", 100) == 100  # Capped


# ---------------------------------------------------------------------------
# Tool factory smoke tests (mock ScbService)
# ---------------------------------------------------------------------------


def _make_mock_service():
    """Create a mock ScbService with basic methods."""
    service = MagicMock()
    service.max_cells = 100000
    service.base_url = "https://statistikdatabasen.scb.se/api/v2/"
    service._is_v2 = True

    # search_tables returns SearchResult-like objects
    table = MagicMock()
    table.id = "TAB001"
    table.title = "Folkmängd efter region"
    table.path = "BE/BE0101/BE0101A/TAB001"
    table.updated = "2025-02-21"
    table.breadcrumb = ("Befolkning",)
    service.search_tables = AsyncMock(return_value=[table])

    # list_nodes for browse
    service.list_nodes = AsyncMock(return_value=[
        {"id": "BE", "type": "l", "text": "Befolkning"},
        {"id": "AM", "type": "l", "text": "Arbetsmarknad"},
    ])

    # get_table_metadata returns variable structure
    service.get_table_metadata = AsyncMock(return_value={
        "variables": [
            {
                "code": "Region",
                "text": "region",
                "values": ["00", "0180", "1480"],
                "valueTexts": ["Riket", "Stockholm", "Göteborg"],
                "elimination": True,
                "eliminationValueCode": "00",
            },
            {
                "code": "Tid",
                "text": "år",
                "values": ["2022", "2023"],
                "valueTexts": ["2022", "2023"],
                "elimination": False,
            },
            {
                "code": "ContentsCode",
                "text": "tabellinnehåll",
                "values": ["BE0101N1"],
                "valueTexts": ["Folkmängd"],
                "elimination": False,
            },
        ],
    })

    # get_default_selection
    service.get_default_selection = AsyncMock(return_value={
        "Region": ["00"],
        "Tid": ["TOP(5)"],
        "ContentsCode": ["BE0101N1"],
    })

    # get_codelist
    service.get_codelist = AsyncMock(return_value={
        "id": "vs_RegionLän",
        "label": "Län",
        "type": "ValueSet",
        "values": [
            {"code": "01", "label": "Stockholms län"},
            {"code": "03", "label": "Uppsala län"},
        ],
    })

    # auto_complete_selection
    service.auto_complete_selection = MagicMock(side_effect=lambda meta, sel, ds=None: (
        {**sel, **{
            v["code"]: [v.get("eliminationValueCode") or v["values"][0]]
            for v in meta.get("variables", [])
            if v["code"] not in sel
        }},
        [f"{v['code']}: auto-completed" for v in meta.get("variables", []) if v["code"] not in sel],
    ))

    # query_table returns JSON-stat2
    service.query_table = AsyncMock(return_value={
        "id": ["Region", "Tid", "ContentsCode"],
        "size": [1, 1, 1],
        "dimension": {
            "Region": {
                "label": "region",
                "category": {"index": {"00": 0}, "label": {"00": "Riket"}},
            },
            "Tid": {
                "label": "år",
                "category": {"index": {"2023": 0}, "label": {"2023": "2023"}},
            },
            "ContentsCode": {
                "label": "tabellinnehåll",
                "category": {
                    "index": {"BE0101N1": 0},
                    "label": {"BE0101N1": "Folkmängd"},
                    "unit": {"BE0101N1": {"base": "antal", "decimals": 0}},
                },
            },
        },
        "value": [10521556],
        "source": "SCB",
    })

    # decode_jsonstat2_to_markdown
    service.decode_jsonstat2_to_markdown = MagicMock(return_value={
        "data_table": "| region | år | Folkmängd |\n|---|---|---:|\n| Riket | 2023 | 10 521 556 |",
        "row_count": 1,
        "truncated": False,
        "unit": "antal",
        "ref_period": None,
        "footnotes": [],
        "source": "SCB",
    })

    return service


class TestSearchTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_search_tool(scb_service=service)
        assert tool_fn.name == "scb_search"

    def test_search_returns_results(self):
        service = _make_mock_service()
        tool_fn = create_scb_search_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"query": "befolkning"})
        )
        data = json.loads(result)
        assert "results" in data
        assert len(data["results"]) > 0
        assert data["results"][0]["id"] == "TAB001"

    def test_empty_query(self):
        service = _make_mock_service()
        tool_fn = create_scb_search_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"query": ""})
        )
        data = json.loads(result)
        assert "error" in data


class TestBrowseTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_browse_tool(scb_service=service)
        assert tool_fn.name == "scb_browse"

    def test_browse_top_level(self):
        service = _make_mock_service()
        tool_fn = create_scb_browse_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"path": ""})
        )
        data = json.loads(result)
        assert "items" in data
        assert len(data["items"]) == 2
        assert data["items"][0]["type"] == "folder"


class TestInspectTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_inspect_tool(scb_service=service)
        assert tool_fn.name == "scb_inspect"

    def test_inspect_table(self):
        service = _make_mock_service()
        tool_fn = create_scb_inspect_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"table_id": "TAB001"})
        )
        data = json.loads(result)
        assert data["table_id"] == "TAB001"
        assert "variables" in data
        assert "default_selection" in data
        assert "auto_complete_note" in data

    def test_inspect_shows_eliminable(self):
        service = _make_mock_service()
        tool_fn = create_scb_inspect_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"table_id": "TAB001"})
        )
        data = json.loads(result)
        region_var = next(v for v in data["variables"] if v["code"] == "Region")
        assert region_var["eliminable"] is True

    def test_empty_table_id(self):
        service = _make_mock_service()
        tool_fn = create_scb_inspect_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"table_id": ""})
        )
        data = json.loads(result)
        assert "error" in data


class TestValidateTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_tool(scb_service=service)
        assert tool_fn.name == "scb_validate"

    def test_valid_selection_with_auto_complete(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Tid": ["2023"],
                    "ContentsCode": ["BE0101N1"],
                    # Region omitted — should be auto-completed
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "valid"
        # Region should have been auto-completed
        assert "Region" in data["selection"]
        assert len(data["auto_completed"]) > 0

    def test_v2_expression_passthrough(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["00"],
                    "Tid": ["TOP(3)"],  # v2 expression
                    "ContentsCode": ["BE0101N1"],
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "valid"
        assert "TOP(3)" in data["selection"]["Tid"]

    def test_invalid_value_code(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["9999"],
                    "Tid": ["2023"],
                    "ContentsCode": ["BE0101N1"],
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "invalid"

    def test_region_fuzzy_resolution(self):
        service = _make_mock_service()
        tool_fn = create_scb_validate_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "Region": ["Stockholm"],
                    "Tid": ["2023"],
                    "ContentsCode": ["BE0101N1"],
                },
            })
        )
        data = json.loads(result)
        assert data["status"] == "valid"
        assert "0180" in data["selection"]["Region"]

    def test_gender_alias_resolution(self):
        service = _make_mock_service()
        service.get_table_metadata = AsyncMock(return_value={
            "variables": [
                {
                    "code": "Region",
                    "text": "region",
                    "values": ["00"],
                    "valueTexts": ["Riket"],
                    "elimination": True,
                    "eliminationValueCode": "00",
                },
                {
                    "code": "Kon",
                    "text": "kön",
                    "values": ["1", "2", "TOT"],
                    "valueTexts": ["män", "kvinnor", "totalt"],
                    "elimination": True,
                },
                {
                    "code": "Tid",
                    "text": "år",
                    "values": ["2023"],
                    "valueTexts": ["2023"],
                    "elimination": False,
                },
                {
                    "code": "ContentsCode",
                    "text": "tabellinnehåll",
                    "values": ["BE01"],
                    "valueTexts": ["Folkmängd"],
                    "elimination": False,
                },
            ],
        })
        tool_fn = create_scb_validate_tool(scb_service=service)

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
        tool_fn = create_scb_validate_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"table_id": "", "selection": {}})
        )
        data = json.loads(result)
        assert "error" in data


class TestFetchTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_fetch_tool(scb_service=service)
        assert tool_fn.name == "scb_fetch"

    def test_basic_fetch_returns_markdown(self):
        service = _make_mock_service()
        tool_fn = create_scb_fetch_tool(scb_service=service)

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
        assert "data_table" in data
        assert "Riket" in data["data_table"] or "region" in data["data_table"]
        assert data["table_id"] == "TAB001"
        assert data["source"] == "SCB"

    def test_fetch_with_auto_complete(self):
        service = _make_mock_service()
        tool_fn = create_scb_fetch_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({
                "table_id": "TAB001",
                "selection": {
                    "ContentsCode": ["BE0101N1"],
                    "Tid": ["2023"],
                    # Region omitted
                },
            })
        )
        data = json.loads(result)
        assert "data_table" in data
        assert "auto_completed" in data
        assert len(data["auto_completed"]) > 0

    def test_empty_selection(self):
        service = _make_mock_service()
        tool_fn = create_scb_fetch_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"table_id": "TAB001", "selection": {}})
        )
        data = json.loads(result)
        assert "error" in data


class TestPreviewTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_preview_tool(scb_service=service)
        assert tool_fn.name == "scb_preview"


class TestCodelistTool:
    def test_create_tool(self):
        service = _make_mock_service()
        tool_fn = create_scb_codelist_tool(scb_service=service)
        assert tool_fn.name == "scb_codelist"

    def test_fetch_codelist(self):
        service = _make_mock_service()
        tool_fn = create_scb_codelist_tool(scb_service=service)

        result = asyncio.get_event_loop().run_until_complete(
            tool_fn.ainvoke({"codelist_id": "vs_RegionLän"})
        )
        data = json.loads(result)
        assert data["id"] == "vs_RegionLän"
        assert len(data["values"]) > 0
