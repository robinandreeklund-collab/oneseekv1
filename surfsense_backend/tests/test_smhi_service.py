"""Unit tests for SMHI service helpers."""

from app.services.smhi_service import (
    SmhiService,
    normalize_timeseries_entry,
    parse_observation_value,
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
