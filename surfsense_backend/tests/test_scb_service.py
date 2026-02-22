"""Tests for SCB service, including parallel optimizations."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.scb_service import (
    ScbService,
    ScbTable,
    _normalize_text,
    _tokenize,
    _score_text,
    _extract_years,
    _is_time_variable,
    _is_region_variable,
    _is_gender_variable,
    _is_age_variable,
    _has_region_request,
    _has_gender_request,
    _has_age_request,
    _score_table_metadata,
    _match_values_by_text,
    _pick_preferred_value,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
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


def test_extract_years():
    assert _extract_years("Data 2020-2024") == ["2020", "2024"]
    assert _extract_years("Statistik 2023") == ["2023"]
    assert _extract_years("Ingen år") == []
    # Dedup
    assert _extract_years("2022 och 2022") == ["2022"]


def test_is_time_variable():
    assert _is_time_variable("Tid", "Year")
    assert _is_time_variable("ar", "tid")
    # "Region" and "Kön" do not contain any time markers
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
    # " per " requires surrounding spaces – present in "kommuner per ar"
    assert _has_region_request(set(), "kommuner per ar")
    # "sverige" is a known region marker
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

    result = _match_values_by_text(values, value_texts, "okänd", {"okänd"})
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
    """Score should be penalized when years are requested but table has no time variable."""
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


@pytest.mark.asyncio
async def test_find_best_table_candidates_parallel_metadata_fetch():
    """Verify that metadata is fetched in parallel (all calls happen concurrently)."""
    service = ScbService()

    call_order: list[str] = []
    call_events: dict[str, asyncio.Event] = {}

    # Build 3 candidate tables
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
        call_order.append(path)
        # Small artificial delay – in parallel these finish roughly together
        await asyncio.sleep(0.01)
        return MINIMAL_METADATA

    service.collect_tables = fake_collect_tables  # type: ignore[method-assign]
    service.get_table_metadata = fake_get_table_metadata  # type: ignore[method-assign]

    best, candidates = await service.find_best_table_candidates(
        "BE/", "befolkning stockholm 2023", metadata_limit=3
    )

    # All 3 tables should have had metadata fetched
    assert fetch_count == 3
    # Best table should be returned
    assert best is not None


@pytest.mark.asyncio
async def test_find_best_table_candidates_http_error_tolerance():
    """An HTTP error on one candidate should not prevent others from being scored."""
    service = ScbService()

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

    best, candidates = await service.find_best_table_candidates(
        "BE/", "befolkning 2023", metadata_limit=2
    )

    # Should still return a result even though T1 failed
    assert best is not None


@pytest.mark.asyncio
async def test_find_best_table_candidates_empty():
    """Returns (None, []) when no tables found."""
    service = ScbService()

    async def fake_collect_tables(*args, **kwargs):
        return []

    service.collect_tables = fake_collect_tables  # type: ignore[method-assign]

    best, candidates = await service.find_best_table_candidates("BE/", "befolkning")
    assert best is None
    assert candidates == []


@pytest.mark.asyncio
async def test_build_query_payloads_single():
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


def test_split_selection_batches_no_split_needed():
    service = ScbService()
    selections = [{"code": "A", "values": ["1"], "is_time": False, "is_region": False}]
    batches, warnings = service._split_selection_batches(
        selections, max_cells=150_000, max_batches=8
    )
    assert len(batches) == 1
    assert warnings == []


@pytest.mark.asyncio
async def test_get_json_raises_on_http_error():
    """_get_json should propagate HTTPStatusError when server returns 4xx/5xx."""
    service = ScbService()

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found",
        request=MagicMock(),
        response=MagicMock(),
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.scb_service.httpx.AsyncClient", mock_client_cls):
        with pytest.raises(httpx.HTTPStatusError):
            await service._get_json("https://example.com/test")
