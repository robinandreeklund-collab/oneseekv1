"""Unit tests for SMHI service helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.smhi_service import (
    SMHI_STRANG_BASE_URL,
    SmhiService,
    _first_not_none,
    normalize_timeseries_entry,
    parse_observation_value,
    summarize_parameter_maps,
)


def test_normalize_timeseries_entry_with_parameter_list():
    entry = {
        "validTime": "2026-02-18T12:00:00Z",
        "parameters": [
            {"name": "t", "values": [2.4], "unit": "C"},
            {"name": "ws", "values": [5.6], "unit": "m/s"},
        ],
    }

    valid_time, parameters = normalize_timeseries_entry(entry)
    assert valid_time == "2026-02-18T12:00:00Z"
    assert parameters == {"t": 2.4, "ws": 5.6}


def test_normalize_timeseries_entry_with_data_map():
    entry = {
        "time": "2026-02-18T12:00:00Z",
        "data": {"snowdepth": 14, "frozenprecipitation": 0},
    }

    valid_time, parameters = normalize_timeseries_entry(entry)
    assert valid_time == "2026-02-18T12:00:00Z"
    assert parameters == {"snowdepth": 14, "frozenprecipitation": 0}


def test_choose_station_prefers_nearest_active():
    stations = [
        {"key": "1", "active": True, "latitude": 55.5, "longitude": 13.0},
        {"key": "2", "active": True, "latitude": 59.4, "longitude": 18.1},
        {"key": "3", "active": False, "latitude": 59.2, "longitude": 18.0},
    ]

    selected = SmhiService.choose_station(stations=stations, lat=59.3, lon=18.0)
    assert selected["key"] == "2"


def test_choose_period_uses_priority():
    periods = [
        {"key": "corrected-archive"},
        {"key": "latest-day"},
        {"key": "latest-hour"},
    ]

    selected = SmhiService.choose_period(periods=periods)
    assert selected["key"] == "latest-hour"


def test_parse_csv_rows_handles_semicolon_delimiter_and_truncation():
    csv_payload = "Datum;Tid (UTC);Value\n2026-02-18;10:00;1.2\n2026-02-18;11:00;1.3\n"
    rows, truncated = SmhiService._parse_csv_rows(csv_payload, limit_values=1)

    assert len(rows) == 1
    assert rows[0]["Datum"] == "2026-02-18"
    assert rows[0]["Value"] == "1.2"
    assert truncated is True


def test_parse_observation_value_coercion():
    assert parse_observation_value("12") == 12
    assert parse_observation_value("12.5") == 12.5
    assert parse_observation_value("  abc  ") == "abc"
    assert parse_observation_value("") is None


# ---------------------------------------------------------------------------
# Tests for _first_not_none helper
# ---------------------------------------------------------------------------


def test_first_not_none_returns_first_present():
    params = {"a": 1, "b": 2}
    assert _first_not_none(params, "a", "b") == 1


def test_first_not_none_skips_absent_keys():
    params = {"b": 5}
    assert _first_not_none(params, "a", "b") == 5


def test_first_not_none_does_not_skip_zero():
    """Zero is a valid value and must NOT be skipped (the original `or` bug)."""
    params = {"a": 0, "b": 99}
    assert _first_not_none(params, "a", "b") == 0


def test_first_not_none_does_not_skip_false():
    params = {"a": False, "b": True}
    assert _first_not_none(params, "a", "b") is False


def test_first_not_none_all_absent_returns_none():
    assert _first_not_none({}, "x", "y") is None


# ---------------------------------------------------------------------------
# Tests for summarize_parameter_maps
# ---------------------------------------------------------------------------


def test_summarize_zero_temperature():
    """0 °C must not be treated as falsy and replaced by a fallback."""
    result = summarize_parameter_maps({"t": 0, "air_temperature": 15.0})
    assert result["temperature_c"] == 0


def test_summarize_zero_precipitation():
    result = summarize_parameter_maps({"pmean": 0, "precipitation_amount_mean": 5.0})
    assert result["precipitation_mean"] == 0


def test_summarize_pmp3g_parameters():
    """All pmp3g-specific keys should be captured."""
    params = {
        "t": 18.5,
        "td": 10.0,
        "ws": 4.2,
        "gust": 8.1,
        "wd": 270,
        "r": 65,
        "msl": 1013.2,
        "tcc_mean": 5,
        "lcc_mean": 2,
        "mcc_mean": 1,
        "hcc_mean": 3,
        "pmean": 0.3,
        "pmin": 0.0,
        "pmax": 1.2,
        "pmedian": 0.4,
        "pcat": 1,
        "spp": 0,
        "vis": 35000,
        "Wsymb2": 3,
    }
    result = summarize_parameter_maps(params)
    assert result["temperature_c"] == 18.5
    assert result["dew_point_c"] == 10.0
    assert result["wind_speed_m_s"] == 4.2
    assert result["wind_gust_m_s"] == 8.1
    assert result["wind_direction_deg"] == 270
    assert result["relative_humidity"] == 65
    assert result["pressure_hpa"] == 1013.2
    assert result["cloud_cover_total"] == 5
    assert result["cloud_cover_low"] == 2
    assert result["cloud_cover_medium"] == 1
    assert result["cloud_cover_high"] == 3
    assert result["precipitation_mean"] == 0.3
    assert result["precipitation_min"] == 0.0
    assert result["precipitation_max"] == 1.2
    assert result["precipitation_median"] == 0.4
    assert result["precipitation_category"] == 1
    assert result["snow_fraction_pct"] == 0
    assert result["visibility_m"] == 35000
    assert result["weather_symbol"] == 3


def test_summarize_snow1g_parameters():
    params = {"sd": 0.25, "Wsymb": 7}
    result = summarize_parameter_maps(params)
    assert result["snow_depth_m"] == 0.25
    assert result["weather_symbol"] == 7


def test_summarize_fwi_parameters():
    """FWI subindices should all be captured."""
    params = {"fwi": 12.4, "isi": 3.1, "ffmc": 82.0, "dmc": 14.0, "dc": 120.0, "bui": 18.5}
    result = summarize_parameter_maps(params)
    assert result["fwi"] == 12.4
    assert result["isi"] == 3.1
    assert result["ffmc"] == 82.0
    assert result["dmc"] == 14.0
    assert result["dc"] == 120.0
    assert result["bui"] == 18.5


def test_summarize_fwi_fallback_key():
    """'fwiindex' key should fall back into the 'fwi' summary field."""
    params = {"fwiindex": 7.7}
    result = summarize_parameter_maps(params)
    assert result["fwi"] == 7.7


def test_summarize_wave_height():
    params = {"hs": 1.8}
    result = summarize_parameter_maps(params)
    assert result["wave_height_m"] == 1.8


def test_summarize_empty_returns_all_none():
    result = summarize_parameter_maps({})
    assert all(v is None for v in result.values())


# ---------------------------------------------------------------------------
# Tests for SmhiService.fetch_strang_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_strang_data_success():
    service = SmhiService()
    fake_payload = {
        "time": ["2024-06-01T12:00:00Z", "2024-06-01T13:00:00Z"],
        "values": [450.2, 380.1],
    }

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=fake_payload)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.smhi_service.httpx.AsyncClient", mock_client_cls):
        result = await service.fetch_strang_data(parameter=116, lat=57.7, lon=11.97)

    assert result["time"] == fake_payload["time"]
    assert result["values"] == fake_payload["values"]

    # Verify correct URL and params were used
    call_args = mock_client.get.call_args
    assert str(call_args.args[0]).endswith("/116")
    assert call_args.kwargs["params"]["lat"] == 57.7
    assert call_args.kwargs["params"]["lon"] == 11.97
    assert "from" not in call_args.kwargs["params"]


@pytest.mark.asyncio
async def test_fetch_strang_data_with_dates():
    service = SmhiService()
    fake_payload = {"time": [], "values": []}

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=fake_payload)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.smhi_service.httpx.AsyncClient", mock_client_cls):
        await service.fetch_strang_data(
            parameter=120,
            lat=59.33,
            lon=18.07,
            from_date="2024-06-01T00:00:00",
            to_date="2024-06-30T23:59:59",
        )

    call_args = mock_client.get.call_args
    assert call_args.kwargs["params"]["from"] == "2024-06-01T00:00:00"
    assert call_args.kwargs["params"]["to"] == "2024-06-30T23:59:59"


@pytest.mark.asyncio
async def test_fetch_strang_data_raises_on_http_error():
    service = SmhiService()

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

    with patch("app.services.smhi_service.httpx.AsyncClient", mock_client_cls):
        with pytest.raises(httpx.HTTPStatusError):
            await service.fetch_strang_data(parameter=116, lat=57.7, lon=11.97)


def test_strang_base_url_exported():
    assert SMHI_STRANG_BASE_URL == "https://strang.smhi.se/api"
