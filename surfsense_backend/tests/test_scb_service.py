"""Tests for SCB service, including v2 migration, parallel optimizations, and tool definitions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.agents.new_chat.scb_tool_definitions import (
    SCB_KEYWORD_INDEX,
    SCB_NORMALIZED_NAMES,
    SCB_NORMALIZED_TABLE_CODES,
    SCB_TOOL_DEFINITIONS,
    _score_tool,
    retrieve_scb_tools,
)
from app.services.scb_service import (
    SCB_BASE_URL_V1,
    SCB_OUTPUT_FORMATS,
    ScbService,
    ScbTable,
    _extract_years,
    _has_age_request,
    _has_gender_request,
    _has_region_request,
    _is_age_variable,
    _is_gender_variable,
    _is_region_variable,
    _is_time_variable,
    _match_values_by_text,
    _pick_preferred_value,
    _score_table_metadata,
)
from app.utils.text import (
    normalize_text as _normalize_text,
    score_text as _score_text,
    tokenize as _tokenize,
)

# ---------------------------------------------------------------------------
# Unit tests for centralized text helpers
# ---------------------------------------------------------------------------


def test_normalize_text():
    assert _normalize_text("Göteborg") == "goteborg"
    assert _normalize_text("Malmö") == "malmo"
    assert _normalize_text("Älvsborg") == "alvsborg"
    assert _normalize_text("") == ""
    assert _normalize_text("Test-string 123") == "test string 123"


def test_tokenize():
    assert _tokenize("Befolkning i Sverige") == ["befolkning", "i", "sverige"]
    assert _tokenize("") == []
    assert _tokenize("  multiple   spaces  ") == ["multiple", "spaces"]


def test_score_text():
    tokens = {"befolkning", "sverige"}
    assert _score_text(tokens, "Befolkning i Sverige") == 2
    assert _score_text(tokens, "Arbetsmarknad") == 0
    assert _score_text(set(), "anything") == 0
    assert _score_text(tokens, "") == 0


# ---------------------------------------------------------------------------
# Unit tests for SCB-specific helper functions
# ---------------------------------------------------------------------------


def test_extract_years():
    assert _extract_years("Data 2020-2024") == ["2020", "2024"]
    assert _extract_years("Statistik 2023") == ["2023"]
    assert _extract_years("Ingen år") == []
    assert _extract_years("2022 och 2022") == ["2022"]


def test_is_time_variable():
    assert _is_time_variable("Tid", "Year")
    assert _is_time_variable("ar", "tid")
    assert not _is_time_variable("Kon", "Kön")


def test_is_region_variable():
    assert _is_region_variable("Region", "Region")
    assert _is_region_variable("Kommun", "Kommuner")
    assert not _is_region_variable("Tid", "Ar")


def test_is_gender_variable():
    assert _is_gender_variable("Kon", "Kön")
    assert _is_gender_variable("sex", "gender")
    assert not _is_gender_variable("Tid", "Year")


def test_is_age_variable():
    assert _is_age_variable("Alder", "Ålder")
    assert _is_age_variable("age", "Age group")
    assert not _is_age_variable("Region", "Lan")


def test_has_region_request():
    tokens = {"befolkning", "stockholm"}
    assert _has_region_request(tokens, "befolkning stockholm")
    assert _has_region_request(set(), "kommuner per ar")
    assert _has_region_request({"bnp", "sverige"}, "bnp sverige")


def test_has_gender_request():
    tokens = {"kvinna", "man"}
    assert _has_gender_request(tokens, "kvinna man")
    assert _has_gender_request(set(), "kvinliga")
    assert not _has_gender_request({"befolkning"}, "befolkning")


def test_has_age_request():
    tokens = {"alder"}
    assert _has_age_request(tokens, "befolkning alder")
    assert not _has_age_request({"befolkning"}, "befolkning")


def test_match_values_by_text():
    values = ["01", "02", "03"]
    value_texts = ["Stockholm", "Uppsala", "Södermanland"]
    result = _match_values_by_text(values, value_texts, "stockholm", {"stockholm"})
    assert result == ["01"]

    result = _match_values_by_text(values, value_texts, "okand", {"okand"})
    assert result == []


def test_pick_preferred_value():
    values = ["0", "1", "TOT"]
    value_texts = ["Okänd", "Man", "Totalt"]
    result = _pick_preferred_value(values, value_texts, ["tot", "total"])
    assert result == ["TOT"]

    result = _pick_preferred_value(values, value_texts, ["saknas"])
    assert result == ["0"]

    assert _pick_preferred_value([], [], ["tot"]) == []


def test_score_table_metadata_time_match():
    metadata = {
        "variables": [
            {
                "code": "Tid",
                "text": "Year",
                "values": ["2022", "2023", "2024"],
                "valueTexts": ["2022", "2023", "2024"],
            }
        ]
    }
    score = _score_table_metadata(
        metadata=metadata,
        query_tokens={"befolkning"},
        query_norm="befolkning",
        requested_years=["2023"],
        wants_region=False,
        wants_gender=False,
        wants_age=False,
    )
    assert score > 0


def test_score_table_metadata_no_time_penalty():
    metadata = {
        "variables": [
            {
                "code": "Region",
                "text": "Region",
                "values": ["01"],
                "valueTexts": ["Stockholm"],
            }
        ]
    }
    score = _score_table_metadata(
        metadata=metadata,
        query_tokens={"befolkning"},
        query_norm="befolkning",
        requested_years=["2023"],
        wants_region=False,
        wants_gender=False,
        wants_age=False,
    )
    assert score < 0


# ---------------------------------------------------------------------------
# Integration tests for ScbService
# ---------------------------------------------------------------------------


MINIMAL_METADATA = {
    "variables": [
        {
            "code": "Tid",
            "text": "Year",
            "values": ["2022", "2023", "2024"],
            "valueTexts": ["2022", "2023", "2024"],
        },
        {
            "code": "Region",
            "text": "Region",
            "values": ["00", "01"],
            "valueTexts": ["Riket", "Stockholm"],
        },
    ]
}


def _make_v1_service() -> ScbService:
    return ScbService(base_url=SCB_BASE_URL_V1)


def test_find_best_table_candidates_parallel_metadata_fetch():
    service = _make_v1_service()

    tables = [
        ScbTable(id=f"T{i}", path=f"BE/T{i}", title=f"Table {i}")
        for i in range(3)
    ]

    async def fake_collect_tables(*args, **kwargs):
        return tables

    fetch_count = 0

    async def fake_get_table_metadata(path: str) -> dict:
        nonlocal fetch_count
        fetch_count += 1
        await asyncio.sleep(0.01)
        return MINIMAL_METADATA

    service.collect_tables = fake_collect_tables  # type: ignore[method-assign]
    service.get_table_metadata = fake_get_table_metadata  # type: ignore[method-assign]

    best, candidates = asyncio.get_event_loop().run_until_complete(
        service.find_best_table_candidates(
            "BE/", "befolkning stockholm 2023", metadata_limit=3
        )
    )
    assert fetch_count == 3
    assert best is not None


def test_find_best_table_candidates_http_error_tolerance():
    service = _make_v1_service()

    tables = [
        ScbTable(id="T0", path="BE/T0", title="Good Table"),
        ScbTable(id="T1", path="BE/T1", title="Bad Table"),
    ]

    async def fake_collect_tables(*args, **kwargs):
        return tables

    async def fake_get_table_metadata(path: str) -> dict:
        if "T1" in path:
            raise httpx.HTTPError("Simulated error")
        return MINIMAL_METADATA

    service.collect_tables = fake_collect_tables  # type: ignore[method-assign]
    service.get_table_metadata = fake_get_table_metadata  # type: ignore[method-assign]

    best, candidates = asyncio.get_event_loop().run_until_complete(
        service.find_best_table_candidates("BE/", "befolkning 2023", metadata_limit=2)
    )
    assert best is not None


def test_find_best_table_candidates_empty():
    service = _make_v1_service()

    async def fake_collect_tables(*args, **kwargs):
        return []

    service.collect_tables = fake_collect_tables  # type: ignore[method-assign]

    best, candidates = asyncio.get_event_loop().run_until_complete(
        service.find_best_table_candidates("BE/", "befolkning")
    )
    assert best is None
    assert candidates == []


def test_build_query_payloads_single():
    service = ScbService()
    payloads, summary, warnings, batch_summaries = service.build_query_payloads(
        MINIMAL_METADATA, "befolkning stockholm 2023"
    )
    assert len(payloads) >= 1
    assert isinstance(summary, list)
    assert isinstance(warnings, list)
    assert len(batch_summaries) == len(payloads)


def test_build_query_payload_no_variables():
    service = ScbService()
    payload, summary, warnings = service.build_query_payload({}, "test")
    assert payload == {}
    assert any("No selectable variables" in w for w in warnings)


def test_selection_cell_count():
    service = ScbService()
    selections = [
        {"code": "A", "values": ["1", "2", "3"]},
        {"code": "B", "values": ["x", "y"]},
    ]
    assert service._selection_cell_count(selections) == 6
    assert service._selection_cell_count([]) == 0


def test_selection_cell_count_empty_values():
    """BUG-5: _selection_cell_count with empty values list should return 0."""
    service = ScbService()
    selections = [
        {"code": "A", "values": []},
        {"code": "B", "values": ["x", "y"]},
    ]
    assert service._selection_cell_count(selections) == 0


def test_split_selection_batches_no_split_needed():
    service = ScbService()
    selections = [{"code": "A", "values": ["1"], "is_time": False, "is_region": False}]
    batches, warnings = service._split_selection_batches(
        selections, max_cells=150_000, max_batches=8
    )
    assert len(batches) == 1
    assert warnings == []


# ---------------------------------------------------------------------------
# v2 specific tests
# ---------------------------------------------------------------------------


def test_v2_detection():
    v2_service = ScbService(base_url="https://statistikdatabasen.scb.se/api/v2/")
    assert v2_service._is_v2 is True

    v1_service = ScbService(base_url=SCB_BASE_URL_V1)
    assert v1_service._is_v2 is False


def test_convert_payload_to_v2():
    v1_payload = {
        "query": [
            {"code": "Region", "selection": {"filter": "item", "values": ["00", "01"]}},
            {"code": "Tid", "selection": {"filter": "item", "values": ["2023"]}},
        ],
        "response": {"format": "json-stat2"},
    }
    v2_payload = ScbService._convert_payload_to_v2(v1_payload)

    assert "selection" in v2_payload
    assert len(v2_payload["selection"]) == 2
    assert v2_payload["selection"][0]["variableCode"] == "Region"
    assert v2_payload["selection"][0]["valueCodes"] == ["00", "01"]
    assert v2_payload["selection"][1]["variableCode"] == "Tid"
    assert v2_payload["outputFormat"] == "json-stat2"


def test_convert_payload_already_v2():
    v2_payload = {
        "selection": [
            {"variableCode": "Region", "valueCodes": ["00"]},
        ],
        "outputFormat": "json-stat2",
    }
    result = ScbService._convert_payload_to_v2(v2_payload)
    assert result is v2_payload


def test_normalize_v2_metadata():
    v2_metadata = {
        "variables": [
            {
                "code": "Tid",
                "label": "Year",
                "values": [
                    {"code": "2022", "label": "2022"},
                    {"code": "2023", "label": "2023"},
                ],
            },
            {
                "code": "Region",
                "label": "Region",
                "values": [
                    {"code": "00", "label": "Riket"},
                    {"code": "01", "label": "Stockholm"},
                ],
            },
        ]
    }
    result = ScbService._normalize_v2_metadata(v2_metadata)

    assert len(result["variables"]) == 2
    tid_var = result["variables"][0]
    assert tid_var["code"] == "Tid"
    assert tid_var["text"] == "Year"
    assert tid_var["values"] == ["2022", "2023"]
    assert tid_var["valueTexts"] == ["2022", "2023"]

    region_var = result["variables"][1]
    assert region_var["values"] == ["00", "01"]
    assert region_var["valueTexts"] == ["Riket", "Stockholm"]


def test_normalize_v2_metadata_already_v1():
    result = ScbService._normalize_v2_metadata(MINIMAL_METADATA)
    assert result == MINIMAL_METADATA


def test_payload_from_selections_v1():
    selections = [
        {"code": "Tid", "values": ["2023"]},
        {"code": "Region", "values": ["00"]},
    ]
    result = ScbService._payload_from_selections_v1(selections)
    assert "query" in result
    assert result["response"]["format"] == "json-stat2"
    assert result["query"][0]["code"] == "Tid"
    assert result["query"][0]["selection"]["filter"] == "item"


def test_payload_from_selections_v2():
    selections = [
        {"code": "Tid", "values": ["2023"]},
        {"code": "Region", "values": ["00"]},
    ]
    result = ScbService._payload_from_selections_v2(selections)
    assert "selection" in result
    assert result["outputFormat"] == "json-stat2"
    assert result["selection"][0]["variableCode"] == "Tid"
    assert result["selection"][0]["valueCodes"] == ["2023"]


def test_persistent_client_reuse():
    service = ScbService()
    client1 = service._get_client()
    client2 = service._get_client()
    assert client1 is client2

    async def cleanup():
        await service.close()

    asyncio.get_event_loop().run_until_complete(cleanup())


def test_search_tables_v2():
    service = ScbService(base_url="https://statistikdatabasen.scb.se/api/v2/")

    mock_response = {
        "tables": [
            {"id": "TAB001", "label": "Befolkning", "updated": "2024-01-01"},
            {"id": "TAB002", "label": "Arbetslöshet", "updated": "2024-02-01"},
        ]
    }

    async def fake_get_json(url, *, params=None):
        assert "tables" in url
        assert params["query"] == "befolkning"
        return mock_response

    service._get_json = fake_get_json  # type: ignore[method-assign]

    tables = asyncio.get_event_loop().run_until_complete(
        service.search_tables("befolkning", limit=10)
    )
    assert len(tables) == 2
    assert tables[0].id == "TAB001"
    assert tables[0].title == "Befolkning"


def test_search_tables_v1_returns_empty():
    service = _make_v1_service()
    tables = asyncio.get_event_loop().run_until_complete(
        service.search_tables("befolkning")
    )
    assert tables == []


def test_collect_tables_timeout():
    service = _make_v1_service()

    call_count = 0

    async def slow_list_nodes(path: str):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.5)
        return [
            {"id": f"item{call_count}", "type": "l", "text": f"Folder {call_count}"},
        ]

    service.list_nodes = slow_list_nodes  # type: ignore[method-assign]

    asyncio.get_event_loop().run_until_complete(
        service.collect_tables("BE/", "test", total_timeout=0.6)
    )
    assert call_count <= 3


def test_cache_lock_exists():
    service = _make_v1_service()
    assert hasattr(service, "_cache_lock")
    assert isinstance(service._cache_lock, asyncio.Lock)


def test_get_json_with_persistent_client():
    service = ScbService()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"test": True})

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    service._client = mock_client

    result = asyncio.get_event_loop().run_until_complete(
        service._get_json("https://example.com/test")
    )
    assert result == {"test": True}
    mock_client.get.assert_called_once()

    asyncio.get_event_loop().run_until_complete(service.close())


def test_encode_path():
    """_encode_path should encode all path segments."""
    service = ScbService()
    encoded = service._encode_path("BE/BE0101/test")
    # Each segment should be individually encoded
    assert encoded == "BE/BE0101/test"

    # Swedish characters should be percent-encoded
    encoded_swedish = service._encode_path("BE/Ålder")
    assert "%C3%85" in encoded_swedish  # Å encoded


# ---------------------------------------------------------------------------
# TTL-cache tests (OPT-4)
# ---------------------------------------------------------------------------


def test_ttl_cache_type():
    """Caches should be TTLCache instances, not plain dicts."""
    from cachetools import TTLCache

    service = ScbService()
    assert isinstance(service._node_cache, TTLCache)
    assert isinstance(service._metadata_cache, TTLCache)
    assert isinstance(service._codelist_cache, TTLCache)


def test_ttl_cache_custom_ttl():
    """Custom cache_ttl should be honoured."""
    service = ScbService(cache_ttl=120)
    # TTLCache instances store ttl as attribute
    assert service._node_cache.ttl == 120
    assert service._metadata_cache.ttl == 120
    assert service._codelist_cache.ttl == 120


# ---------------------------------------------------------------------------
# Codelist tests (#16)
# ---------------------------------------------------------------------------


def test_codelist_v1_returns_empty():
    """v1 service should return empty dict for codelist requests."""
    service = _make_v1_service()
    result = asyncio.get_event_loop().run_until_complete(
        service.get_codelist("some_codelist")
    )
    assert result == {}


def test_codelist_v2_success():
    """v2 service should fetch and cache codelists."""
    service = ScbService(base_url="https://statistikdatabasen.scb.se/api/v2/")

    mock_codelist = {
        "id": "Regions",
        "values": [
            {"code": "00", "label": "Riket"},
            {"code": "01", "label": "Stockholm"},
        ],
    }

    call_count = 0

    async def fake_get_json(url, *, params=None):
        nonlocal call_count
        call_count += 1
        assert "codelists" in url
        return mock_codelist

    service._get_json = fake_get_json  # type: ignore[method-assign]

    # First call — should fetch from API
    result1 = asyncio.get_event_loop().run_until_complete(
        service.get_codelist("Regions")
    )
    assert result1["id"] == "Regions"
    assert call_count == 1

    # Second call — should use cache
    result2 = asyncio.get_event_loop().run_until_complete(
        service.get_codelist("Regions")
    )
    assert result2["id"] == "Regions"
    assert call_count == 1  # No additional fetch


def test_codelist_v2_http_error():
    """HTTP errors during codelist fetch should return empty dict."""
    service = ScbService(base_url="https://statistikdatabasen.scb.se/api/v2/")

    async def fake_get_json(url, *, params=None):
        raise httpx.HTTPError("Simulated error")

    service._get_json = fake_get_json  # type: ignore[method-assign]

    result = asyncio.get_event_loop().run_until_complete(
        service.get_codelist("nonexistent")
    )
    assert result == {}


# ---------------------------------------------------------------------------
# Output format tests (#15)
# ---------------------------------------------------------------------------


def test_output_formats_constant():
    """SCB_OUTPUT_FORMATS should contain expected formats."""
    assert "json-stat2" in SCB_OUTPUT_FORMATS
    assert "csv" in SCB_OUTPUT_FORMATS
    assert "parquet" in SCB_OUTPUT_FORMATS
    assert "xlsx" in SCB_OUTPUT_FORMATS


def test_query_table_v2_output_format():
    """v2 query_table should honour output_format parameter."""
    service = ScbService(base_url="https://statistikdatabasen.scb.se/api/v2/")

    captured_payload = {}

    async def fake_post_json(url, payload):
        captured_payload.update(payload)
        return {"data": []}

    service._post_json = fake_post_json  # type: ignore[method-assign]

    v2_payload = {
        "selection": [
            {"variableCode": "Tid", "valueCodes": ["2023"]},
        ],
        "outputFormat": "json-stat2",
    }
    asyncio.get_event_loop().run_until_complete(
        service.query_table("TAB001", v2_payload, output_format="csv")
    )
    assert captured_payload["outputFormat"] == "csv"


# ---------------------------------------------------------------------------
# Parallel BFS tests (OPT-2 + BUG-2)
# ---------------------------------------------------------------------------


def test_collect_tables_parallel_fetch():
    """collect_tables should fetch multiple branches in parallel."""
    service = _make_v1_service()

    fetch_order = []

    async def tracking_list_nodes(path: str):
        fetch_order.append(path)
        if path == "BE/":
            return [
                {"id": "A", "type": "l", "text": "Folder A"},
                {"id": "B", "type": "l", "text": "Folder B"},
            ]
        elif "A" in path:
            return [{"id": "T1", "type": "t", "text": "Table 1"}]
        elif "B" in path:
            return [{"id": "T2", "type": "t", "text": "Table 2"}]
        return []

    service.list_nodes = tracking_list_nodes  # type: ignore[method-assign]

    tables = asyncio.get_event_loop().run_until_complete(
        service.collect_tables("BE/", "test", max_concurrent=5, total_timeout=5.0)
    )
    assert len(tables) == 2
    assert len(fetch_order) >= 3  # Root + at least 2 children


def test_collect_tables_priority_ordering():
    """High-scoring branches should be explored before low-scoring ones."""
    service = _make_v1_service()

    explored = []

    async def tracking_list_nodes(path: str):
        explored.append(path)
        if path == "BE/":
            return [
                {"id": "Low", "type": "l", "text": "Irrelevant"},
                {"id": "High", "type": "l", "text": "befolkning"},
            ]
        return [{"id": "TAB1", "type": "t", "text": "Some table"}]

    service.list_nodes = tracking_list_nodes  # type: ignore[method-assign]

    asyncio.get_event_loop().run_until_complete(
        service.collect_tables("BE/", "befolkning", max_concurrent=1, total_timeout=5.0)
    )
    # "High" (matching "befolkning") should be explored before or same level as "Low"
    assert "BE/" in explored
    high_idx = next((i for i, p in enumerate(explored) if "High" in p), None)
    low_idx = next((i for i, p in enumerate(explored) if "Low" in p), None)
    assert high_idx is not None
    # High-scoring branch should come first
    if low_idx is not None:
        assert high_idx <= low_idx


# ---------------------------------------------------------------------------
# Tool definition tests (KQ-3, #17, OPT-7)
# ---------------------------------------------------------------------------


def test_tool_definitions_count():
    """Should have 47 tool definitions (21 broad + 26 specific)."""
    assert len(SCB_TOOL_DEFINITIONS) == 47


def test_tool_definitions_unique_ids():
    """All tool IDs should be unique."""
    ids = [d.tool_id for d in SCB_TOOL_DEFINITIONS]
    assert len(ids) == len(set(ids))


def test_new_tools_present():
    """5 new tools from #17 should be present."""
    tool_ids = {d.tool_id for d in SCB_TOOL_DEFINITIONS}
    assert "scb_befolkning_dodsfall" in tool_ids
    assert "scb_befolkning_invandring" in tool_ids
    assert "scb_arbetsmarknad_lonestruktur" in tool_ids
    assert "scb_handel_detaljhandel" in tool_ids
    assert "scb_nationalrakenskaper_bnp_kvartal" in tool_ids


def test_keyword_index_populated():
    """OPT-7: Pre-computed keyword index should cover all tools."""
    assert len(SCB_KEYWORD_INDEX) == len(SCB_TOOL_DEFINITIONS)
    for definition in SCB_TOOL_DEFINITIONS:
        assert definition.tool_id in SCB_KEYWORD_INDEX
        assert len(SCB_KEYWORD_INDEX[definition.tool_id]) == len(definition.keywords)


def test_normalized_names_populated():
    """OPT-7: Pre-computed normalized names should cover all tools."""
    assert len(SCB_NORMALIZED_NAMES) == len(SCB_TOOL_DEFINITIONS)
    for definition in SCB_TOOL_DEFINITIONS:
        assert definition.tool_id in SCB_NORMALIZED_NAMES
        assert isinstance(SCB_NORMALIZED_NAMES[definition.tool_id], str)


def test_normalized_table_codes_populated():
    """OPT-7: Pre-computed table codes should cover all tools."""
    assert len(SCB_NORMALIZED_TABLE_CODES) == len(SCB_TOOL_DEFINITIONS)


def test_score_tool_uses_precomputed():
    """_score_tool should produce non-zero score for matching queries."""
    definition = next(d for d in SCB_TOOL_DEFINITIONS if d.tool_id == "scb_befolkning")
    score = _score_tool(definition, "befolkning stockholm", {"befolkning", "stockholm"})
    assert score > 0


def test_retrieve_scb_tools_returns_correct_tools():
    """retrieve_scb_tools should return relevant tools."""
    tools = retrieve_scb_tools("befolkning folkmangd", limit=3)
    assert len(tools) == 3
    # scb_befolkning or scb_befolkning_folkmangd should be high-ranking
    assert any("befolkning" in t for t in tools)


def test_retrieve_scb_tools_new_tool_dodsfall():
    """New dödsfall tool should be retrievable."""
    tools = retrieve_scb_tools("dodsfall mortalitet", limit=5)
    assert "scb_befolkning_dodsfall" in tools


def test_retrieve_scb_tools_new_tool_bnp_kvartal():
    """New BNP kvartal tool should be retrievable."""
    tools = retrieve_scb_tools("bnp kvartal", limit=5)
    assert "scb_nationalrakenskaper_bnp_kvartal" in tools


def test_retrieve_scb_tools_new_tool_detaljhandel():
    """New detaljhandel tool should be retrievable."""
    tools = retrieve_scb_tools("detaljhandel butik", limit=5)
    assert "scb_handel_detaljhandel" in tools


def test_retrieve_scb_tools_empty_query():
    """Empty-ish query should return first N tools."""
    tools = retrieve_scb_tools("", limit=2)
    assert len(tools) == 2


# ---------------------------------------------------------------------------
# Domain fan-out tests
# ---------------------------------------------------------------------------


def test_domain_fan_out_new_categories():
    """Fan-out config should include handel category."""
    from app.agents.new_chat.domain_fan_out import SCB_CATEGORIES

    names = {cat.name for cat in SCB_CATEGORIES}
    assert "handel" in names
    assert "nationalrakenskaper" in names
    assert "befolkning" in names


def test_domain_fan_out_new_tool_ids_in_categories():
    """New tool IDs should be included in fan-out categories."""
    from app.agents.new_chat.domain_fan_out import SCB_CATEGORIES

    all_tool_ids = set()
    for cat in SCB_CATEGORIES:
        all_tool_ids.update(cat.tool_ids)

    assert "scb_befolkning_invandring" in all_tool_ids
    assert "scb_arbetsmarknad_lonestruktur" in all_tool_ids
    assert "scb_nationalrakenskaper_bnp_kvartal" in all_tool_ids
    assert "scb_handel_detaljhandel" in all_tool_ids


def test_domain_fan_out_select_handel():
    """Query about handel should select the handel category."""
    from app.agents.new_chat.domain_fan_out import select_categories

    cats = select_categories("statistik", "detaljhandel i Sverige")
    cat_names = {c.name for c in cats}
    assert "handel" in cat_names
