"""
SMHI weather tool for SurfSense agent.

Fetches forecast data from SMHI's open data API using lat/lon coordinates.
If only a location name is provided, the tool will geocode it to coordinates
before calling SMHI.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
import httpx
from langchain_core.tools import tool

from app.config import config

logger = logging.getLogger(__name__)

SMHI_BASE_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2"
)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_SMHI_MAX_HOURS = 48
MAX_SMHI_MAX_HOURS = 120


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _format_coord(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _params_to_maps(parameters: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    units: dict[str, str] = {}
    for param in parameters:
        name = param.get("name")
        if not name:
            continue
        param_values = param.get("values")
        if isinstance(param_values, list):
            values[name] = param_values[0] if len(param_values) == 1 else param_values
        else:
            values[name] = param_values
        unit = param.get("unit")
        if unit:
            units[name] = unit
    return values, units


def _build_summary(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature_c": parameters.get("t"),
        "wind_speed_m_s": parameters.get("ws"),
        "wind_gust_m_s": parameters.get("gust"),
        "wind_direction_deg": parameters.get("wd"),
        "relative_humidity": parameters.get("r"),
        "pressure_hpa": parameters.get("msl"),
        "cloud_cover": parameters.get("tcc_mean"),
        "weather_symbol": parameters.get("Wsymb2"),
        "precipitation_mean": parameters.get("pmean"),
    }


async def _geocode_location(
    location: str, country_code: str | None = None
) -> dict[str, Any] | None:
    user_agent = (
        config.GEOCODING_USER_AGENT or "SurfSense/1.0 (+https://surfsense.ai)"
    )
    params = {
        "q": location,
        "format": "jsonv2",
        "limit": 5,
        "addressdetails": 1,
    }
    if country_code:
        params["countrycodes"] = country_code

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": user_agent},
        )
        response.raise_for_status()
        results = response.json()

    if not isinstance(results, list) or not results:
        return None

    return results[0]


async def _fetch_smhi_forecast(
    lat: float, lon: float
) -> tuple[dict[str, Any], float, float, int]:
    rounding_steps = [6, 5, 4, 3]
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        for decimals in rounding_steps:
            lat_str = _format_coord(lat, decimals)
            lon_str = _format_coord(lon, decimals)
            url = f"{SMHI_BASE_URL}/geotype/point/lon/{lon_str}/lat/{lat_str}/data.json"
            try:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
                return payload, float(lat_str), float(lon_str), decimals
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response is not None and exc.response.status_code == 404:
                    continue
                raise
            except Exception as exc:
                last_error = exc
                raise

    if last_error:
        raise last_error
    raise RuntimeError("SMHI request failed without response.")


def create_smhi_weather_tool():
    """
    Factory for the SMHI weather tool.

    Uses the SMHI open data API and optional Nominatim geocoding.
    """

    @tool
    async def smhi_weather(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        include_raw: bool = False,
        max_hours: int | None = DEFAULT_SMHI_MAX_HOURS,
    ) -> dict[str, Any]:
        """
        Fetch weather data from SMHI for a location or coordinates.

        Use this tool when the user asks about current weather or forecast
        for a specific place in Sweden. If only a place name is provided,
        the tool will geocode it to lat/lon before calling SMHI.

        Args:
            location: Place name (e.g., "Goteborg"). Optional if lat/lon provided.
            lat: Latitude in decimal degrees.
            lon: Longitude in decimal degrees.
            country_code: Optional ISO country code to bias geocoding (e.g., "se").
            include_raw: Include raw SMHI response (default: False, truncated to max_hours).
            max_hours: Optional limit for forecast hours returned from now (default: 48, capped).

        Returns:
            A dictionary containing location info, current conditions,
            time series data, and optional raw payload.
        """
        if lat is None or lon is None:
            if not location:
                return {
                    "status": "error",
                    "error": "Provide either lat/lon or a location name.",
                }

            try:
                geocoded = await _geocode_location(location, country_code=country_code)
            except Exception as exc:
                logger.error("SMHI geocoding failed: %s", exc)
                return {
                    "status": "error",
                    "error": f"Geocoding failed: {exc!s}",
                    "location": {"query": location},
                }

            if not geocoded:
                return {
                    "status": "error",
                    "error": "Could not resolve location.",
                    "location": {"query": location},
                }

            try:
                lat = float(geocoded.get("lat"))
                lon = float(geocoded.get("lon"))
            except (TypeError, ValueError):
                return {
                    "status": "error",
                    "error": "Geocoding returned invalid coordinates.",
                    "location": {"query": location},
                }

            resolved_location = {
                "name": location,
                "display_name": geocoded.get("display_name"),
                "lat": lat,
                "lon": lon,
                "source": "nominatim",
            }
        else:
            resolved_location = {
                "name": location,
                "lat": lat,
                "lon": lon,
                "source": "user",
            }

        try:
            forecast, smhi_lat, smhi_lon, smhi_decimals = await _fetch_smhi_forecast(
                lat=lat, lon=lon
            )
        except Exception as exc:
            logger.error("SMHI forecast fetch failed: %s", exc)
            return {
                "status": "error",
                "error": f"SMHI request failed: {exc!s}",
                "location": resolved_location,
            }

        time_series = forecast.get("timeSeries") if isinstance(forecast, dict) else None
        if not isinstance(time_series, list) or not time_series:
            return {
                "status": "error",
                "error": "SMHI response did not include time series data.",
                "location": resolved_location,
            }

        if max_hours is None:
            max_hours = DEFAULT_SMHI_MAX_HOURS
        if max_hours > MAX_SMHI_MAX_HOURS:
            max_hours = MAX_SMHI_MAX_HOURS

        now = datetime.now(UTC)
        parsed_series: list[tuple[datetime, dict[str, Any]]] = []
        for entry in time_series:
            valid_time = _parse_iso_datetime(entry.get("validTime", ""))
            if not valid_time:
                continue
            parsed_series.append((valid_time, entry))

        if not parsed_series:
            return {
                "status": "error",
                "error": "SMHI time series could not be parsed.",
                "location": resolved_location,
            }

        current_time, current_entry = min(
            parsed_series, key=lambda item: abs(item[0] - now)
        )

        current_params, current_units = _params_to_maps(
            current_entry.get("parameters", [])
        )
        current_summary = _build_summary(current_params)

        limit_time = now + timedelta(hours=max_hours)
        timeseries_out: list[dict[str, Any]] = []
        raw_time_series: list[dict[str, Any]] = []
        for valid_time, entry in parsed_series:
            if limit_time and valid_time > limit_time:
                continue
            params_map, _ = _params_to_maps(entry.get("parameters", []))
            timeseries_out.append(
                {
                    "valid_time": valid_time.isoformat(),
                    "parameters": params_map,
                }
            )
            raw_time_series.append(entry)

        source_url = (
            f"{SMHI_BASE_URL}/geotype/point/lon/{_format_coord(smhi_lon, smhi_decimals)}"
            f"/lat/{_format_coord(smhi_lat, smhi_decimals)}/data.json"
        )
        geometry = forecast.get("geometry") if isinstance(forecast, dict) else None
        grid_point = None
        if isinstance(geometry, dict):
            coords = geometry.get("coordinates")
            if (
                isinstance(coords, list)
                and coords
                and isinstance(coords[0], list)
                and len(coords[0]) >= 2
            ):
                grid_point = {"lon": coords[0][0], "lat": coords[0][1]}

        result: dict[str, Any] = {
            "status": "ok",
            "attribution": "Data from SMHI",
            "source": {
                "provider": "SMHI",
                "url": source_url,
                "requested_point": {"lat": smhi_lat, "lon": smhi_lon},
                "grid_point": grid_point,
            },
            "location": resolved_location,
            "current": {
                "valid_time": current_time.isoformat(),
                "parameters": current_params,
                "summary": current_summary,
                "units": current_units,
            },
            "timeseries": timeseries_out,
            "max_hours": max_hours,
        }

        if include_raw:
            raw_payload = dict(forecast) if isinstance(forecast, dict) else {}
            raw_payload["timeSeries"] = raw_time_series
            raw_payload["raw_truncated"] = True
            result["raw"] = raw_payload

        return result

    return smhi_weather
