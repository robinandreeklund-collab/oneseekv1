"""Tests for RiksbankService and Riksbank tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.riksbank_service import (
    RIKSBANK_SOURCE,
    SERIES_POLICY_RATE,
    GROUP_EXCHANGE_RATES_SEK,
    GROUP_KEY_RATES,
    GROUP_STIBOR,
    RiksbankService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    return RiksbankService(
        swea_base_url="https://api.riksbank.se/swea/v1",
        swestr_base_url="https://api.riksbank.se/swestr/v1",
        forecasts_base_url="https://api.riksbank.se/forecasts/v1",
        api_key="",
        timeout=5.0,
    )


def _mock_response(data, status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = data
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    return response


# ---------------------------------------------------------------------------
# SWEA API tests
# ---------------------------------------------------------------------------


class TestSweaAPI:
    @pytest.mark.asyncio
    async def test_get_latest_observation(self, service):
        mock_data = {"date": "2025-01-15", "value": 2.5}
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_latest_observation(SERIES_POLICY_RATE)
            assert data == mock_data
            assert cached is False

    @pytest.mark.asyncio
    async def test_get_latest_observation_cached(self, service):
        mock_data = {"date": "2025-01-15", "value": 2.5}
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data1, cached1 = await service.get_latest_observation(SERIES_POLICY_RATE)
            data2, cached2 = await service.get_latest_observation(SERIES_POLICY_RATE)
            assert cached1 is False
            assert cached2 is True
            assert data1 == data2

    @pytest.mark.asyncio
    async def test_get_observations(self, service):
        mock_data = [
            {"date": "2025-01-01", "value": 2.5},
            {"date": "2025-01-15", "value": 2.75},
        ]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_observations(SERIES_POLICY_RATE, "2025-01-01", "2025-01-31")
            assert data == mock_data
            assert cached is False

    @pytest.mark.asyncio
    async def test_get_latest_by_group(self, service):
        mock_data = [
            {"seriesId": "SECBREPOEFF", "date": "2025-01-15", "value": 2.5},
            {"seriesId": "SECBDEPOEFF", "date": "2025-01-15", "value": 1.75},
        ]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_latest_by_group(GROUP_KEY_RATES)
            assert len(data) == 2
            assert cached is False

    @pytest.mark.asyncio
    async def test_get_cross_rates(self, service):
        mock_data = [{"date": "2025-01-15", "value": 1.085}]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_cross_rates("SEKEURPMI", "SEKUSDPMI", "2025-01-15")
            assert data == mock_data
            assert cached is False

    @pytest.mark.asyncio
    async def test_list_series(self, service):
        mock_data = [
            {"seriesId": "SECBREPOEFF", "shortDescription": "Policy rate"},
        ]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.list_series()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_groups(self, service):
        mock_data = [{"groupId": "2", "label": "Key rates"}]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.list_groups()
            assert isinstance(data, list)


# ---------------------------------------------------------------------------
# SWESTR API tests
# ---------------------------------------------------------------------------


class TestSwestrAPI:
    @pytest.mark.asyncio
    async def test_get_swestr_latest(self, service):
        mock_data = {
            "rate": 3.66,
            "date": "2025-01-15",
            "pctl12_5": 3.60,
            "pctl87_5": 3.70,
            "volume": 25000000000,
            "numberOfTransactions": 42,
            "numberOfAgents": 12,
        }
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_swestr_latest()
            assert data["rate"] == 3.66
            assert cached is False

    @pytest.mark.asyncio
    async def test_get_swestr_observations(self, service):
        mock_data = [
            {"rate": 3.66, "date": "2025-01-14"},
            {"rate": 3.67, "date": "2025-01-15"},
        ]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_swestr_observations("2025-01-14", "2025-01-15")
            assert len(data) == 2


# ---------------------------------------------------------------------------
# Forecasts API tests
# ---------------------------------------------------------------------------


class TestForecastsAPI:
    @pytest.mark.asyncio
    async def test_get_forecasts(self, service):
        mock_data = [{"indicator": "KPIF", "value": 2.1, "date": "2025-Q1"}]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_forecasts(indicator="KPIF")
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_forecast_indicators(self, service):
        mock_data = ["KPIF", "GDP", "Unemployment"]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_forecast_indicators()
            assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Convenience methods
# ---------------------------------------------------------------------------


class TestConvenience:
    @pytest.mark.asyncio
    async def test_get_policy_rate(self, service):
        mock_data = {"date": "2025-01-15", "value": 2.5}
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_policy_rate()
            assert data["value"] == 2.5

    @pytest.mark.asyncio
    async def test_get_policy_rate_history(self, service):
        mock_data = [
            {"date": "2024-01-01", "value": 4.0},
            {"date": "2025-01-01", "value": 2.5},
        ]
        with patch.object(service, "_get_json", new_callable=AsyncMock, return_value=mock_data):
            data, cached = await service.get_policy_rate_history("2024-01-01", "2025-01-31")
            assert len(data) == 2


# ---------------------------------------------------------------------------
# HTTP client lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_close(self, service):
        # Should not raise even when no client exists
        await service.close()

    def test_api_key_header(self):
        svc = RiksbankService(api_key="test-key-123")
        client = svc._get_client()
        assert client.headers.get("Ocp-Apim-Subscription-Key") == "test-key-123"

    def test_no_api_key_header(self, service):
        client = service._get_client()
        assert "Ocp-Apim-Subscription-Key" not in client.headers


# ---------------------------------------------------------------------------
# Tool definitions validation
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    def test_all_definitions_have_required_fields(self):
        from app.agents.new_chat.tools.riksbank import RIKSBANK_TOOL_DEFINITIONS

        for defn in RIKSBANK_TOOL_DEFINITIONS:
            assert defn.tool_id, "tool_id must not be empty"
            assert defn.name, "name must not be empty"
            assert defn.description, "description must not be empty"
            assert len(defn.keywords) >= 3, f"{defn.tool_id}: needs at least 3 keywords"
            assert len(defn.example_queries) >= 2, f"{defn.tool_id}: needs at least 2 example queries"
            assert defn.category, "category must not be empty"

    def test_unique_tool_ids(self):
        from app.agents.new_chat.tools.riksbank import RIKSBANK_TOOL_DEFINITIONS

        ids = [d.tool_id for d in RIKSBANK_TOOL_DEFINITIONS]
        assert len(ids) == len(set(ids)), "Duplicate tool IDs found"

    def test_tool_count(self):
        from app.agents.new_chat.tools.riksbank import RIKSBANK_TOOL_DEFINITIONS

        assert len(RIKSBANK_TOOL_DEFINITIONS) == 8

    def test_create_all_tools(self):
        from app.agents.new_chat.tools.riksbank import (
            RIKSBANK_TOOL_DEFINITIONS,
            create_riksbank_tool,
        )

        for defn in RIKSBANK_TOOL_DEFINITIONS:
            tool_instance = create_riksbank_tool(defn)
            assert tool_instance is not None
            assert tool_instance.name == defn.tool_id
