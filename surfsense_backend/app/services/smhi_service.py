from __future__ import annotations

import csv
import io
import logging
import math
from typing import Any
from urllib.parse import urlencode

import httpx

SMHI_SOURCE = "SMHI Open Data"

SMHI_METFCST_BASE_URL = "https://opendata-download-metfcst.smhi.se/api"
SMHI_METANALYS_BASE_URL = "https://opendata-download-metanalys.smhi.se/api"
SMHI_METOBS_BASE_URL = "https://opendata-download-metobs.smhi.se/api"
SMHI_HYDROOBS_BASE_URL = "https://opendata-download-hydroobs.smhi.se/api"
SMHI_OCOBS_BASE_URL = "https://opendata-download-ocobs.smhi.se/api"

_DEFAULT_USER_AGENT = "SurfSense/1.0 (+https://surfsense.ai)"
_OBS_PERIOD_PRIORITY = (
    "latest-hour",
    "latest-day",
    "latest-month",
    "latest-months",
    "corrected-archive",
)

logger = logging.getLogger(__name__)


def _format_coord(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_sq(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return (lat1 - lat2) ** 2 + (lon1 - lon2) ** 2


def _is_json_content_type(content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return "application/json" in lowered


class SmhiService:
    """Shared helpers for SMHI Open Data endpoints."""

    def __init__(self, *, timeout: float = 15.0, user_agent: str = _DEFAULT_USER_AGENT):
        self.timeout = timeout
        self.user_agent = user_agent

    async def _fetch_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params, headers=request_headers)
            response.raise_for_status()
            if not _is_json_content_type(response.headers.get("content-type", "")):
                sample = response.text[:120].replace("\n", " ")
                raise RuntimeError(
                    f"Expected JSON from SMHI endpoint but got "
                    f"{response.headers.get('content-type', 'unknown')} ({sample})"
                )
            return response.json()

    async def _fetch_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update(headers)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params, headers=request_headers)
            response.raise_for_status()
            return response.text

    async def fetch_grid_point_data(
        self,
        *,
        base_url: str,
        category: str,
        version: str,
        lon: float,
        lat: float,
        period: str | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], float, float, int, str]:
        """
        Fetch point/grid data for forecast/analysis style endpoints.

        Returns:
            (payload, rounded_lat, rounded_lon, decimals_used, source_url)
        """
        rounding_steps = [6, 5, 4, 3]
        last_error: Exception | None = None
        for decimals in rounding_steps:
            lat_str = _format_coord(lat, decimals)
            lon_str = _format_coord(lon, decimals)
            period_part = f"/{period.strip('/')}" if period else ""
            url = (
                f"{base_url.rstrip('/')}/category/{category}/version/{version}"
                f"{period_part}/geotype/point/lon/{lon_str}/lat/{lat_str}/data.json"
            )
            try:
                payload = await self._fetch_json(url, params=query_params)
                if not isinstance(payload, dict):
                    raise RuntimeError("SMHI endpoint returned non-object JSON payload.")
                return payload, float(lat_str), float(lon_str), decimals, url
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response is not None and exc.response.status_code == 404:
                    continue
                raise
            except Exception as exc:
                last_error = exc
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("SMHI request failed without response.")

    async def fetch_grid_parameters(
        self,
        *,
        base_url: str,
        category: str,
        version: str,
        period: str | None = None,
    ) -> dict[str, Any]:
        period_part = f"/{period.strip('/')}" if period else ""
        url = (
            f"{base_url.rstrip('/')}/category/{category}/version/{version}"
            f"{period_part}/parameter.json"
        )
        payload = await self._fetch_json(url)
        if not isinstance(payload, dict):
            raise RuntimeError("SMHI parameter endpoint returned non-object JSON payload.")
        return payload

    async def fetch_latest_catalog(self, *, base_url: str) -> dict[str, Any]:
        url = f"{base_url.rstrip('/')}/version/latest.json"
        payload = await self._fetch_json(url)
        if not isinstance(payload, dict):
            raise RuntimeError("SMHI catalog endpoint returned non-object JSON payload.")
        return payload

    @staticmethod
    def choose_station(
        *,
        stations: list[dict[str, Any]],
        station_key: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
    ) -> dict[str, Any]:
        if not stations:
            raise RuntimeError("No stations found for this parameter.")

        if station_key:
            normalized_key = str(station_key).strip()
            for station in stations:
                if str(station.get("key", "")).strip() == normalized_key:
                    return station
            raise RuntimeError(f"Station '{station_key}' was not found.")

        active_stations = [
            station for station in stations if bool(station.get("active", False))
        ]
        candidates = active_stations or stations

        if lat is not None and lon is not None:
            with_coords: list[tuple[float, dict[str, Any]]] = []
            for station in candidates:
                station_lat = _coerce_float(station.get("latitude"))
                station_lon = _coerce_float(station.get("longitude"))
                if station_lat is None or station_lon is None:
                    continue
                with_coords.append(
                    (_distance_sq(lat, lon, station_lat, station_lon), station)
                )
            if with_coords:
                with_coords.sort(key=lambda item: item[0])
                return with_coords[0][1]

        return candidates[0]

    @staticmethod
    def choose_period(
        *,
        periods: list[dict[str, Any]],
        period_key: str | None = None,
        priorities: tuple[str, ...] = _OBS_PERIOD_PRIORITY,
    ) -> dict[str, Any]:
        if not periods:
            raise RuntimeError("No periods available for this station.")

        if period_key:
            normalized_key = str(period_key).strip()
            for period in periods:
                if str(period.get("key", "")).strip() == normalized_key:
                    return period
            raise RuntimeError(f"Period '{period_key}' was not found.")

        keyed_periods = {
            str(period.get("key", "")).strip(): period for period in periods
        }
        for priority in priorities:
            if priority in keyed_periods:
                return keyed_periods[priority]
        return periods[0]

    @staticmethod
    def _normalize_station(station_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "key": station_payload.get("key") or station_payload.get("id"),
            "name": station_payload.get("name")
            or station_payload.get("title")
            or station_payload.get("summary"),
            "owner": station_payload.get("owner"),
            "active": station_payload.get("active"),
            "latitude": station_payload.get("latitude"),
            "longitude": station_payload.get("longitude"),
            "height": station_payload.get("height"),
            "region": station_payload.get("region"),
            "summary": station_payload.get("summary"),
        }

    @staticmethod
    def _extract_data_links(period_payload: dict[str, Any]) -> list[dict[str, Any]]:
        data_entries = period_payload.get("data")
        if not isinstance(data_entries, list) or not data_entries:
            return []
        first = data_entries[0]
        if not isinstance(first, dict):
            return []
        links = first.get("link")
        if not isinstance(links, list):
            return []
        return [link for link in links if isinstance(link, dict)]

    @staticmethod
    def _parse_csv_rows(csv_payload: str, *, limit_values: int = 120) -> tuple[list[dict[str, Any]], bool]:
        """
        Parse CSV payload into list[dict].

        Returns:
            (rows, truncated)
        """
        if not csv_payload.strip():
            return [], False
        lines = csv_payload.splitlines()
        if not lines:
            return [], False

        sample = "\n".join(lines[:10])
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ";"

        stream = io.StringIO(csv_payload)
        reader = csv.DictReader(stream, delimiter=delimiter)
        rows: list[dict[str, Any]] = []
        truncated = False
        for idx, row in enumerate(reader):
            if idx >= limit_values:
                truncated = True
                break
            cleaned = {
                str(key).strip(): (value.strip() if isinstance(value, str) else value)
                for key, value in (row or {}).items()
                if key is not None
            }
            rows.append(cleaned)
        return rows, truncated

    async def fetch_observation_series(
        self,
        *,
        base_url: str,
        parameter_key: str,
        station_key: str | None = None,
        period_key: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        limit_values: int = 120,
    ) -> dict[str, Any]:
        parameter_url = (
            f"{base_url.rstrip('/')}/version/latest/parameter/{parameter_key}.json"
        )
        parameter_payload = await self._fetch_json(parameter_url)
        if not isinstance(parameter_payload, dict):
            raise RuntimeError("SMHI parameter payload was not a JSON object.")

        stations_raw = parameter_payload.get("station")
        stations = (
            [station for station in stations_raw if isinstance(station, dict)]
            if isinstance(stations_raw, list)
            else []
        )
        selected_station = self.choose_station(
            stations=stations,
            station_key=station_key,
            lat=lat,
            lon=lon,
        )
        resolved_station_key = str(selected_station.get("key", "")).strip()
        if not resolved_station_key:
            raise RuntimeError("Selected station is missing key.")

        station_url = (
            f"{base_url.rstrip('/')}/version/latest/parameter/{parameter_key}"
            f"/station/{resolved_station_key}.json"
        )
        station_payload = await self._fetch_json(station_url)
        if not isinstance(station_payload, dict):
            raise RuntimeError("SMHI station payload was not a JSON object.")

        periods_raw = station_payload.get("period")
        periods = (
            [period for period in periods_raw if isinstance(period, dict)]
            if isinstance(periods_raw, list)
            else []
        )
        selected_period = self.choose_period(periods=periods, period_key=period_key)
        resolved_period_key = str(selected_period.get("key", "")).strip()
        if not resolved_period_key:
            raise RuntimeError("Selected period is missing key.")

        # Observation APIs use version 1.0 for the station/period/data path in links.
        period_url = (
            f"{base_url.rstrip('/')}/version/1.0/parameter/{parameter_key}"
            f"/station/{resolved_station_key}/period/{resolved_period_key}.json"
        )
        period_payload = await self._fetch_json(period_url)
        if not isinstance(period_payload, dict):
            raise RuntimeError("SMHI period payload was not a JSON object.")

        data_links = self._extract_data_links(period_payload)
        json_link = next(
            (
                link
                for link in data_links
                if str(link.get("type", "")).strip().lower().startswith("application/json")
            ),
            None,
        )
        csv_link = next(
            (
                link
                for link in data_links
                if str(link.get("type", "")).strip().lower() == "text/plain"
            ),
            None,
        )

        values: list[dict[str, Any]]
        data_format: str
        data_source_url: str | None = None
        truncated = False

        if json_link and isinstance(json_link.get("href"), str):
            data_source_url = str(json_link.get("href"))
            data_payload = await self._fetch_json(data_source_url)
            if isinstance(data_payload, dict):
                raw_values = data_payload.get("value")
                values = (
                    [item for item in raw_values if isinstance(item, dict)]
                    if isinstance(raw_values, list)
                    else []
                )
            else:
                values = []
            if len(values) > limit_values:
                values = values[:limit_values]
                truncated = True
            data_format = "json"
        elif csv_link and isinstance(csv_link.get("href"), str):
            data_source_url = str(csv_link.get("href"))
            csv_payload = await self._fetch_text(data_source_url)
            values, truncated = self._parse_csv_rows(
                csv_payload, limit_values=limit_values
            )
            data_format = "csv"
        else:
            values = []
            data_format = "none"

        return {
            "parameter": {
                "key": parameter_payload.get("key") or parameter_key,
                "title": parameter_payload.get("title"),
                "summary": parameter_payload.get("summary"),
                "unit": parameter_payload.get("unit"),
            },
            "station": self._normalize_station(station_payload),
            "period": {
                "key": period_payload.get("key") or resolved_period_key,
                "summary": period_payload.get("summary"),
                "from": period_payload.get("from"),
                "to": period_payload.get("to"),
            },
            "values": values,
            "value_count": len(values),
            "truncated": truncated,
            "data_format": data_format,
            "parameter_url": parameter_url,
            "station_url": station_url,
            "period_url": period_url,
            "data_source_url": data_source_url,
            "data_links": data_links,
        }

    async def fetch_pthbv_data(
        self,
        *,
        lon: float,
        lat: float,
        from_year: int,
        to_year: int,
        period: str,
        variables: list[str],
        epsg: int = 4326,
    ) -> tuple[dict[str, Any], str]:
        if not variables:
            raise RuntimeError("At least one variable is required for pthbv1g.")
        path = (
            "/category/pthbv1g/version/1/geotype/multipoint/"
            f"from/{int(from_year)}/to/{int(to_year)}/period/{period}/data.json"
        )
        params: dict[str, Any] = {
            "epsg": int(epsg),
            "ll": f"{lon},{lat}",
            "var": variables,
        }
        payload = await self._fetch_json(
            f"{SMHI_METANALYS_BASE_URL}{path}",
            params=params,
            headers={"Accept-Encoding": "gzip"},
        )
        if not isinstance(payload, dict):
            raise RuntimeError("PTHBV endpoint returned non-object JSON payload.")
        query = urlencode({"epsg": int(epsg), "ll": f"{lon},{lat}"}, doseq=True)
        var_query = "&".join(f"var={value}" for value in variables)
        source_url = f"{SMHI_METANALYS_BASE_URL}{path}?{query}&{var_query}"
        return payload, source_url


def normalize_timeseries_entry(entry: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """Normalize mixed SMHI time series formats into (valid_time, parameters)."""
    valid_time = entry.get("validTime") or entry.get("time")
    params = entry.get("parameters")
    if isinstance(params, list):
        normalized: dict[str, Any] = {}
        for item in params:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            values = item.get("values")
            if not name:
                continue
            if isinstance(values, list):
                normalized[str(name)] = values[0] if len(values) == 1 else values
            else:
                normalized[str(name)] = values
        return valid_time, normalized
    if isinstance(params, dict):
        return valid_time, dict(params)
    data = entry.get("data")
    if isinstance(data, dict):
        return valid_time, dict(data)
    return valid_time, {}


def extract_grid_point(payload: dict[str, Any]) -> dict[str, Any] | None:
    geometry = payload.get("geometry")
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return None
    first = coords[0]
    if not isinstance(first, list) or len(first) < 2:
        return None
    return {"lon": first[0], "lat": first[1]}


def build_source_url(
    *,
    base_url: str,
    category: str,
    version: str,
    lon: float,
    lat: float,
    decimals: int,
    period: str | None = None,
    query_params: dict[str, Any] | None = None,
) -> str:
    period_part = f"/{period.strip('/')}" if period else ""
    url = (
        f"{base_url.rstrip('/')}/category/{category}/version/{version}{period_part}"
        f"/geotype/point/lon/{_format_coord(lon, decimals)}/lat/{_format_coord(lat, decimals)}"
        "/data.json"
    )
    if not query_params:
        return url

    normalized_params: dict[str, Any] = {}
    for key, value in query_params.items():
        if value is None:
            continue
        if isinstance(value, list):
            normalized_params[key] = [item for item in value if item is not None]
        else:
            normalized_params[key] = value
    if not normalized_params:
        return url
    return f"{url}?{urlencode(normalized_params, doseq=True)}"


def summarize_parameter_maps(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature_c": parameters.get("t") or parameters.get("air_temperature"),
        "wind_speed_m_s": parameters.get("ws") or parameters.get("wind_speed"),
        "wind_gust_m_s": parameters.get("gust") or parameters.get("wind_speed_of_gust"),
        "wind_direction_deg": parameters.get("wd") or parameters.get("wind_from_direction"),
        "relative_humidity": parameters.get("r") or parameters.get("relative_humidity"),
        "pressure_hpa": parameters.get("msl")
        or parameters.get("air_pressure_at_mean_sea_level"),
        "cloud_cover": parameters.get("tcc_mean")
        or parameters.get("cloud_area_fraction"),
        "weather_symbol": parameters.get("Wsymb2") or parameters.get("symbol_code"),
        "precipitation_mean": parameters.get("pmean")
        or parameters.get("precipitation_amount_mean"),
        "fwi_index": parameters.get("fwiindex"),
        "fwi": parameters.get("fwi"),
    }


def parse_observation_value(
    raw_value: Any,
) -> float | int | str | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        if isinstance(raw_value, float) and math.isnan(raw_value):
            return None
        return raw_value
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return None
        try:
            if "." in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped
    return str(raw_value)


__all__ = [
    "SMHI_SOURCE",
    "SMHI_METFCST_BASE_URL",
    "SMHI_METANALYS_BASE_URL",
    "SMHI_METOBS_BASE_URL",
    "SMHI_HYDROOBS_BASE_URL",
    "SMHI_OCOBS_BASE_URL",
    "SmhiService",
    "normalize_timeseries_entry",
    "extract_grid_point",
    "build_source_url",
    "summarize_parameter_maps",
    "parse_observation_value",
]
