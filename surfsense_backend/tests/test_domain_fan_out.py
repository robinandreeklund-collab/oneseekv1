"""Tests for domain_fan_out module: category selection, parallel execution, context formatting."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.new_chat.domain_fan_out import (
    DOMAIN_FAN_OUT_CONFIGS,
    DomainFanOutConfig,
    FanOutCategory,
    FanOutResult,
    execute_domain_fan_out,
    format_fan_out_context,
    get_fan_out_tool_ids,
    is_fan_out_enabled,
    select_categories,
)


# ---------------------------------------------------------------------------
# is_fan_out_enabled
# ---------------------------------------------------------------------------

class TestIsFanOutEnabled:
    def test_weather_enabled(self):
        assert is_fan_out_enabled("väder") is True

    def test_weather_english_enabled(self):
        assert is_fan_out_enabled("weather") is True

    def test_trafik_enabled(self):
        assert is_fan_out_enabled("trafik") is True

    def test_statistik_enabled(self):
        assert is_fan_out_enabled("statistik") is True

    def test_unknown_agent_disabled(self):
        assert is_fan_out_enabled("bolag") is False

    def test_empty_string_disabled(self):
        assert is_fan_out_enabled("") is False

    def test_none_disabled(self):
        assert is_fan_out_enabled(None) is False


# ---------------------------------------------------------------------------
# get_fan_out_tool_ids
# ---------------------------------------------------------------------------

class TestGetFanOutToolIds:
    def test_weather_returns_smhi_tools(self):
        ids = get_fan_out_tool_ids("väder")
        assert "smhi_vaderprognoser_metfcst" in ids
        assert "smhi_vaderobservationer_metobs" in ids
        assert "smhi_vaderanalyser_mesan2g" in ids

    def test_trafik_returns_trafikverket_tools(self):
        ids = get_fan_out_tool_ids("trafik")
        assert "trafikverket_trafikinfo_storningar" in ids
        assert "trafikverket_trafikinfo_koer" in ids

    def test_unknown_returns_empty(self):
        assert get_fan_out_tool_ids("unknown") == []


# ---------------------------------------------------------------------------
# select_categories
# ---------------------------------------------------------------------------

class TestSelectCategories:
    def test_weather_basic_query_includes_prognos(self):
        cats = select_categories("väder", "Vad blir vädret i Göteborg?")
        names = [c.name for c in cats]
        # prognos has no triggers → always included as baseline
        assert "prognos" in names

    def test_weather_snow_query_includes_sno(self):
        cats = select_categories("väder", "Kommer det snö i Sundsvall?")
        names = [c.name for c in cats]
        assert "prognos" in names
        assert "sno" in names

    def test_weather_observation_query(self):
        cats = select_categories("väder", "Senaste observation från station i Stockholm")
        names = [c.name for c in cats]
        assert "prognos" in names
        assert "observation" in names

    def test_weather_brandrisk_query(self):
        cats = select_categories("väder", "Finns det brandrisk i Dalarna?")
        names = [c.name for c in cats]
        assert "brandrisk" in names

    def test_weather_ocean_query(self):
        cats = select_categories("väder", "Havsvattenstånd vid kusten")
        names = [c.name for c in cats]
        assert "oceanografi" in names

    def test_weather_max_parallel_cap(self):
        config = DOMAIN_FAN_OUT_CONFIGS["väder"]
        # A comprehensive query that triggers many categories
        cats = select_categories(
            "väder",
            "snö brandrisk sol observation analys hydrologi hav",
        )
        assert len(cats) <= config.max_parallel

    def test_trafik_basic_includes_storningar(self):
        cats = select_categories("trafik", "Trafikläget på E6")
        names = [c.name for c in cats]
        assert "storningar" in names

    def test_trafik_olycka_query(self):
        cats = select_categories("trafik", "Finns det olyckor på E4?")
        names = [c.name for c in cats]
        assert "olyckor" in names

    def test_trafik_tag_query(self):
        cats = select_categories("trafik", "Tågförseningar Stockholm C")
        names = [c.name for c in cats]
        assert "tag_forseningar" in names

    def test_trafik_halka_query(self):
        cats = select_categories("trafik", "Risk för halka på vägarna")
        names = [c.name for c in cats]
        assert "vader_halka" in names

    def test_unknown_agent_returns_empty(self):
        assert select_categories("unknown", "Anything") == []

    def test_disabled_config_returns_empty(self):
        config = DomainFanOutConfig(enabled=False)
        assert select_categories("väder", "Vad blir vädret?", config=config) == []

    def test_non_selective_includes_all(self):
        config = DomainFanOutConfig(
            enabled=True,
            max_parallel=10,
            categories=(
                FanOutCategory(name="a", tool_ids=("t1",), priority=0),
                FanOutCategory(name="b", tool_ids=("t2",), priority=1),
            ),
            selective=False,
        )
        cats = select_categories("test", "any query", config=config)
        assert len(cats) == 2

    def test_categories_sorted_by_priority(self):
        cats = select_categories(
            "väder",
            "snö brandrisk observation",
        )
        priorities = [c.priority for c in cats]
        assert priorities == sorted(priorities)

    def test_statistik_befolkning_query(self):
        cats = select_categories("statistik", "Befolkning i Malmö kommun")
        names = [c.name for c in cats]
        assert "befolkning" in names

    def test_statistik_arbetsmarknad_query(self):
        cats = select_categories("statistik", "Arbetslöshet i Sverige")
        names = [c.name for c in cats]
        assert "arbetsmarknad" in names


# ---------------------------------------------------------------------------
# execute_domain_fan_out
# ---------------------------------------------------------------------------

class TestExecuteDomainFanOut:
    @pytest.mark.asyncio
    async def test_basic_execution_with_mock_tools(self):
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = "Temperature: 12°C, Wind: 5 m/s"

        tool_registry = {
            "smhi_vaderprognoser_metfcst": mock_tool,
        }

        results = await execute_domain_fan_out(
            agent_name="väder",
            query="Vad blir vädret i Göteborg?",
            tool_registry=tool_registry,
        )

        assert len(results) >= 1
        success = [r for r in results if r.status == "success"]
        assert len(success) >= 1
        assert success[0].tool_id == "smhi_vaderprognoser_metfcst"
        assert "12°C" in success[0].content

    @pytest.mark.asyncio
    async def test_missing_tools_return_error(self):
        # Empty registry — tools not found
        results = await execute_domain_fan_out(
            agent_name="väder",
            query="Vad blir vädret?",
            tool_registry={},
        )
        # No tools available → empty results
        assert results == []

    @pytest.mark.asyncio
    async def test_tool_exception_returns_error_result(self):
        mock_tool = AsyncMock()
        mock_tool.ainvoke.side_effect = RuntimeError("API unavailable")

        results = await execute_domain_fan_out(
            agent_name="väder",
            query="Vad blir vädret?",
            tool_registry={"smhi_vaderprognoser_metfcst": mock_tool},
        )

        assert len(results) >= 1
        errors = [r for r in results if r.status == "error"]
        assert len(errors) >= 1
        assert "API unavailable" in errors[0].error

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_result(self):
        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(10)
            return "late"

        mock_tool = AsyncMock()
        mock_tool.ainvoke.side_effect = slow_invoke

        config = DomainFanOutConfig(
            enabled=True,
            max_parallel=1,
            timeout_seconds=0.1,  # Very short timeout
            categories=(
                FanOutCategory(name="prognos", tool_ids=("slow_tool",), priority=0),
            ),
            selective=False,
        )

        results = await execute_domain_fan_out(
            agent_name="test",
            query="anything",
            tool_registry={"slow_tool": mock_tool},
            config=config,
        )

        assert len(results) == 1
        assert results[0].status == "timeout"

    @pytest.mark.asyncio
    async def test_disabled_agent_returns_empty(self):
        results = await execute_domain_fan_out(
            agent_name="unknown_agent",
            query="Anything",
            tool_registry={"some_tool": AsyncMock()},
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_parallel_execution_is_truly_parallel(self):
        """Verify that multiple tools execute concurrently, not sequentially."""
        call_times: list[float] = []

        async def timed_invoke(*args, **kwargs):
            import time
            start = time.monotonic()
            await asyncio.sleep(0.1)
            end = time.monotonic()
            call_times.append(end - start)
            return "result"

        tool_a = AsyncMock()
        tool_a.ainvoke.side_effect = timed_invoke
        tool_b = AsyncMock()
        tool_b.ainvoke.side_effect = timed_invoke

        config = DomainFanOutConfig(
            enabled=True,
            max_parallel=2,
            timeout_seconds=5.0,
            categories=(
                FanOutCategory(name="a", tool_ids=("tool_a",), priority=0),
                FanOutCategory(name="b", tool_ids=("tool_b",), priority=1),
            ),
            selective=False,
        )

        import time
        t0 = time.monotonic()
        results = await execute_domain_fan_out(
            agent_name="test",
            query="test",
            tool_registry={"tool_a": tool_a, "tool_b": tool_b},
            config=config,
        )
        total_elapsed = time.monotonic() - t0

        assert len(results) == 2
        # If parallel: ~0.1s total. If sequential: ~0.2s total.
        # Allow some margin but verify it's faster than sequential.
        assert total_elapsed < 0.18, f"Expected parallel execution, took {total_elapsed:.3f}s"


# ---------------------------------------------------------------------------
# format_fan_out_context
# ---------------------------------------------------------------------------

class TestFormatFanOutContext:
    def test_empty_results(self):
        assert format_fan_out_context([]) == ""

    def test_single_success(self):
        results = [
            FanOutResult(
                tool_id="smhi_vaderprognoser_metfcst",
                category="prognos",
                status="success",
                content="Temperature: 12°C",
                elapsed_ms=150.0,
            ),
        ]
        ctx = format_fan_out_context(results)
        assert "<domain_fan_out_results>" in ctx
        assert "smhi_vaderprognoser_metfcst" in ctx
        assert "Temperature: 12°C" in ctx
        assert "</domain_fan_out_results>" in ctx

    def test_multiple_results(self):
        results = [
            FanOutResult(
                tool_id="smhi_vaderprognoser_metfcst",
                category="prognos",
                status="success",
                content="Forecast data",
                elapsed_ms=100.0,
            ),
            FanOutResult(
                tool_id="smhi_vaderobservationer_metobs",
                category="observation",
                status="success",
                content="Observation data",
                elapsed_ms=200.0,
            ),
        ]
        ctx = format_fan_out_context(results)
        assert "smhi_vaderprognoser_metfcst" in ctx
        assert "smhi_vaderobservationer_metobs" in ctx
        assert "Forecast data" in ctx
        assert "Observation data" in ctx

    def test_error_result_included_as_comment(self):
        results = [
            FanOutResult(
                tool_id="broken_tool",
                category="test",
                status="error",
                error="Connection refused",
                elapsed_ms=50.0,
            ),
        ]
        ctx = format_fan_out_context(results)
        assert "broken_tool" in ctx
        assert "error" in ctx
        assert "Connection refused" in ctx

    def test_truncation_per_tool(self):
        results = [
            FanOutResult(
                tool_id="big_tool",
                category="test",
                status="success",
                content="x" * 10000,
                elapsed_ms=100.0,
            ),
        ]
        ctx = format_fan_out_context(results, max_chars_per_tool=500)
        # Content should be truncated
        assert len(ctx) < 10000

    def test_total_char_limit(self):
        results = [
            FanOutResult(
                tool_id=f"tool_{i}",
                category="test",
                status="success",
                content="y" * 5000,
                elapsed_ms=100.0,
            )
            for i in range(10)
        ]
        ctx = format_fan_out_context(results, max_total_chars=8000)
        assert len(ctx) <= 9000  # Allow some overhead for tags

    def test_only_errors_no_content(self):
        results = [
            FanOutResult(
                tool_id="err1",
                category="test",
                status="error",
                error="Timeout",
                elapsed_ms=0.0,
            ),
        ]
        ctx = format_fan_out_context(results)
        # Should still have the wrapper since there's error content
        assert "err1" in ctx
