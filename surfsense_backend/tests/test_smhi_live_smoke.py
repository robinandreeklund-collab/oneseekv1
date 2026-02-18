"""Optional live smoke tests for SMHI endpoints.

These tests are skipped unless SMHI_LIVE_TESTS=1.
"""

import os

import pytest

from app.services.smhi_service import (
    SMHI_METANALYS_BASE_URL,
    SMHI_METFCST_BASE_URL,
    SMHI_METOBS_BASE_URL,
    SmhiService,
)


pytestmark = pytest.mark.skipif(
    os.getenv("SMHI_LIVE_TESTS") != "1",
    reason="Set SMHI_LIVE_TESTS=1 to run live SMHI smoke tests",
)


@pytest.mark.asyncio
async def test_smhi_live_metfcst_smoke():
    service = SmhiService(timeout=20.0)
    payload, _, _, _, _ = await service.fetch_grid_point_data(
        base_url=SMHI_METFCST_BASE_URL,
        category="pmp3g",
        version="2",
        lon=18.0686,
        lat=59.3293,
    )
    assert isinstance(payload.get("timeSeries"), list)
    assert payload.get("approvedTime")


@pytest.mark.asyncio
async def test_smhi_live_metobs_smoke():
    service = SmhiService(timeout=20.0)
    result = await service.fetch_observation_series(
        base_url=SMHI_METOBS_BASE_URL,
        parameter_key="1",
        lat=59.3293,
        lon=18.0686,
        limit_values=8,
    )
    assert result["parameter"]["key"] in {"1", 1}
    assert result["station"]["key"]
    assert isinstance(result["values"], list)


@pytest.mark.asyncio
async def test_smhi_live_pthbv_smoke():
    service = SmhiService(timeout=20.0)
    payload, source_url = await service.fetch_pthbv_data(
        lon=15.0,
        lat=60.0,
        from_year=2022,
        to_year=2023,
        period="monthly",
        variables=["p", "t"],
        epsg=4326,
    )
    assert "pthbv1g" in source_url
    assert isinstance(payload.get("dates"), list)
    assert isinstance(payload.get("point_values"), list)


@pytest.mark.asyncio
async def test_smhi_live_fwia_smoke():
    service = SmhiService(timeout=20.0)
    payload, _, _, _, _ = await service.fetch_grid_point_data(
        base_url=SMHI_METANALYS_BASE_URL,
        category="fwia1g",
        version="1",
        period="hourly",
        lon=18.0686,
        lat=59.3293,
    )
    assert isinstance(payload.get("timeSeries"), list)
