"""Tests for ElprisService and Elpris tools."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.elpris_service import (
    ELPRIS_SOURCE,
    VALID_ZONES,
    ZONE_NAMES,
    ElprisService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    return ElprisService(
        base_url="https://www.elprisetjustnu.se/api/v1/prices",
        timeout=5.0,
    )


SAMPLE_PRICES = [
    {
        "SEK_per_kWh": 0.45,
        "EUR_per_kWh": 0.04,
        "EXR": 11.25,
        "time_start": "2025-01-15T00:00:00+01:00",
        "time_end": "2025-01-15T00:15:00+01:00",
    },
    {
        "SEK_per_kWh": 0.52,
        "EUR_per_kWh": 0.046,
        "EXR": 11.25,
        "time_start": "2025-01-15T00:15:00+01:00",
        "time_end": "2025-01-15T00:30:00+01:00",
    },
    {
        "SEK_per_kWh": 0.38,
        "EUR_per_kWh": 0.034,
        "EXR": 11.25,
        "time_start": "2025-01-15T00:30:00+01:00",
        "time_end": "2025-01-15T00:45:00+01:00",
    },
]


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestElprisService:
    @pytest.mark.asyncio
    async def test_get_prices(self, service):
        with patch.object(service, "_fetch_prices", new_callable=AsyncMock, return_value=SAMPLE_PRICES):
            prices = await service.get_prices("2025-01-15", "SE3")
            assert len(prices) == 3
            assert prices[0]["SEK_per_kWh"] == 0.45

    @pytest.mark.asyncio
    async def test_get_today_prices(self, service):
        with patch.object(service, "_fetch_prices", new_callable=AsyncMock, return_value=SAMPLE_PRICES):
            prices = await service.get_today_prices("SE3")
            assert len(prices) == 3

    @pytest.mark.asyncio
    async def test_get_tomorrow_prices(self, service):
        with patch.object(service, "_fetch_prices", new_callable=AsyncMock, return_value=SAMPLE_PRICES):
            prices = await service.get_tomorrow_prices("SE3")
            assert len(prices) == 3

    @pytest.mark.asyncio
    async def test_get_tomorrow_prices_empty(self, service):
        with patch.object(service, "_fetch_prices", new_callable=AsyncMock, return_value=[]):
            prices = await service.get_tomorrow_prices("SE3")
            assert prices == []

    @pytest.mark.asyncio
    async def test_get_average_price(self, service):
        with patch.object(service, "_fetch_prices", new_callable=AsyncMock, return_value=SAMPLE_PRICES):
            result = await service.get_average_price("2025-01-15", "SE3")
            assert result["date"] == "2025-01-15"
            assert result["zone"] == "SE3"
            assert result["zone_name"] == "Stockholm"
            assert result["min_sek_per_kwh"] == 0.38
            assert result["max_sek_per_kwh"] == 0.52
            assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_get_price_comparison(self, service):
        with patch.object(service, "_fetch_prices", new_callable=AsyncMock, return_value=SAMPLE_PRICES):
            result = await service.get_price_comparison("2025-01-15")
            assert result["date"] == "2025-01-15"
            assert "SE1" in result["zones"]
            assert "SE2" in result["zones"]
            assert "SE3" in result["zones"]
            assert "SE4" in result["zones"]

    @pytest.mark.asyncio
    async def test_get_prices_range(self, service):
        with patch.object(service, "_fetch_prices", new_callable=AsyncMock, return_value=SAMPLE_PRICES):
            prices = await service.get_prices_range("2025-01-15", "2025-01-16", "SE3")
            # Called twice (2 days), each returns 3 prices
            assert len(prices) == 6

    @pytest.mark.asyncio
    async def test_get_prices_range_too_long(self, service):
        with pytest.raises(ValueError, match="exceed 31 days"):
            await service.get_prices_range("2025-01-01", "2025-03-15", "SE3")


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_validate_zone_valid(self, service):
        assert service._validate_zone("SE1") == "SE1"
        assert service._validate_zone("se3") == "SE3"
        assert service._validate_zone(" SE4 ") == "SE4"

    def test_validate_zone_invalid(self, service):
        with pytest.raises(ValueError, match="Invalid zone"):
            service._validate_zone("SE5")

    def test_build_url(self, service):
        url = service._build_url("2025-01-15", "SE3")
        assert url == "https://www.elprisetjustnu.se/api/v1/prices/2025/01-15_SE3.json"

    def test_build_url_invalid_date(self, service):
        with pytest.raises(ValueError, match="Invalid date format"):
            service._build_url("20250115", "SE3")


# ---------------------------------------------------------------------------
# Aggregation tests
# ---------------------------------------------------------------------------


class TestAggregation:
    def test_aggregate(self):
        result = ElprisService._aggregate(SAMPLE_PRICES)
        assert result["min_sek_per_kwh"] == 0.38
        assert result["max_sek_per_kwh"] == 0.52
        assert result["count"] == 3
        assert 0.44 < result["average_sek_per_kwh"] < 0.46

    def test_aggregate_empty(self):
        result = ElprisService._aggregate([])
        assert result["min"] is None
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_close(self, service):
        await service.close()  # Should not raise


# ---------------------------------------------------------------------------
# Tool definitions validation
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    def test_all_definitions_have_required_fields(self):
        from app.agents.new_chat.tools.elpris import ELPRIS_TOOL_DEFINITIONS

        for defn in ELPRIS_TOOL_DEFINITIONS:
            assert defn.tool_id, "tool_id must not be empty"
            assert defn.name, "name must not be empty"
            assert defn.description, "description must not be empty"
            assert len(defn.keywords) >= 3, f"{defn.tool_id}: needs at least 3 keywords"
            assert len(defn.example_queries) >= 2, f"{defn.tool_id}: needs at least 2 example queries"

    def test_unique_tool_ids(self):
        from app.agents.new_chat.tools.elpris import ELPRIS_TOOL_DEFINITIONS

        ids = [d.tool_id for d in ELPRIS_TOOL_DEFINITIONS]
        assert len(ids) == len(set(ids)), "Duplicate tool IDs found"

    def test_tool_count(self):
        from app.agents.new_chat.tools.elpris import ELPRIS_TOOL_DEFINITIONS

        assert len(ELPRIS_TOOL_DEFINITIONS) == 4

    def test_create_all_tools(self):
        from app.agents.new_chat.tools.elpris import (
            ELPRIS_TOOL_DEFINITIONS,
            create_elpris_tool,
        )

        for defn in ELPRIS_TOOL_DEFINITIONS:
            tool_instance = create_elpris_tool(defn)
            assert tool_instance is not None
            assert tool_instance.name == defn.tool_id
