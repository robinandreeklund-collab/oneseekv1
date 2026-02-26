from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.agents.new_chat.circuit_breaker import get_breaker
from app.agents.new_chat.tools.smhi_weather import (
    DEFAULT_SMHI_MAX_HOURS,
    MAX_SMHI_MAX_HOURS,
    _geocode_location,
    _parse_iso_datetime,
)
from app.services.smhi_service import (
    SMHI_HYDROOBS_BASE_URL,
    SMHI_METANALYS_BASE_URL,
    SMHI_METFCST_BASE_URL,
    SMHI_METOBS_BASE_URL,
    SMHI_OCOBS_BASE_URL,
    SMHI_SOURCE,
    SMHI_STRANG_BASE_URL,
    SmhiService,
    build_source_url,
    extract_grid_point,
    normalize_timeseries_entry,
    parse_observation_value,
    summarize_parameter_maps,
)

logger = logging.getLogger(__name__)

SMHI_CATEGORY_VADEROBS = "smhi_vaderobservationer"
SMHI_CATEGORY_VADERPROGNOS = "smhi_vaderprognoser"
SMHI_CATEGORY_VADERANALYS = "smhi_vaderanalyser"
SMHI_CATEGORY_HYDROLOGI = "smhi_hydrologi"
SMHI_CATEGORY_OCEANOGRAFI = "smhi_oceanografi"
SMHI_CATEGORY_BRANDRISK = "smhi_brandrisk"
SMHI_CATEGORY_SOLSTRALNING = "smhi_solstralning"


@dataclass(frozen=True)
class SmhiToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str
    base_path: str


SMHI_TOOL_DEFINITIONS: list[SmhiToolDefinition] = [
    SmhiToolDefinition(
        tool_id="smhi_weather",
        name="SMHI Weather (legacy)",
        description=(
            "Bakåtkompatibelt verktyg för väderprognoser från SMHI (metfcst pmp3g). "
            "Ange platsnamn via location (t.ex. location='Malmö') — verktyget geocodar automatiskt till lat/long. "
            "Du behöver INTE ange lat/lon separat om du anger location."
        ),
        keywords=["smhi", "vader", "väder", "prognos", "temperatur", "vind", "regn"],
        example_queries=[
            "Vad blir vädret i Göteborg imorgon?",
            "Temperatur i Stockholm nu",
        ],
        category=SMHI_CATEGORY_VADERPROGNOS,
        base_path="/api/category/pmp3g/version/2/geotype/point/lon/{lon}/lat/{lat}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_vaderprognoser_metfcst",
        name="SMHI Väderprognoser - Metfcst",
        description=(
            "Väderprognoser från SMHI:s pmp3g-modell (temperatur, vind, nederbörd, moln). "
            "Ange platsnamn via location (t.ex. location='Stockholm') — verktyget geocodar automatiskt till lat/long. "
            "Du behöver INTE ange lat/lon separat om du anger location."
        ),
        keywords=["metfcst", "pmp3g", "prognos", "vader", "väder", "temperatur"],
        example_queries=[
            "Väderprognos för Malmö kommande 24 timmar",
            "Vind och nederbörd i Uppsala",
        ],
        category=SMHI_CATEGORY_VADERPROGNOS,
        base_path="/api/category/pmp3g/version/2/geotype/point/lon/{lon}/lat/{lat}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_vaderprognoser_snow1g",
        name="SMHI Väderprognoser - Snow1g",
        description=(
            "Snörelaterade prognoser från snow1g (snödjup, frusen nederbörd, symboler). "
            "Ange platsnamn via location (t.ex. location='Sundsvall') — verktyget geocodar automatiskt till lat/long. "
            "Du behöver INTE ange lat/lon separat om du anger location."
        ),
        keywords=["snow1g", "sno", "snö", "snodjup", "frozen precipitation"],
        example_queries=[
            "Hur mycket snö väntas i Sundsvall?",
            "Snörisk i Östersund kommande dygn",
        ],
        category=SMHI_CATEGORY_VADERPROGNOS,
        base_path="/api/category/snow1g/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_vaderanalyser_mesan2g",
        name="SMHI Väderanalyser - Mesan2g",
        description=(
            "Gridbaserad väderanalys från MESAN (moln, strålning, temperatur, nederbörd). "
            "Ange platsnamn via location — verktyget geocodar automatiskt till lat/long. "
            "Du behöver INTE ange lat/lon separat om du anger location."
        ),
        keywords=["mesan2g", "analys", "metanalys", "moln", "stralning", "vind"],
        example_queries=[
            "Väderanalys för Norrköping senaste dygnet",
            "Molntäcke och strålning i Göteborg",
        ],
        category=SMHI_CATEGORY_VADERANALYS,
        base_path="/api/category/mesan2g/version/2/geotype/point/lon/{lon}/lat/{lat}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_vaderobservationer_metobs",
        name="SMHI Väderobservationer - Metobs",
        description=(
            "Stationsbaserade meteorologiska observationer (realtid/historik) från SMHI metobs.\n"
            "Vanliga parameter_key-värden:\n"
            "  1  = Lufttemperatur instant (°C)\n"
            "  2  = Lufttemperatur dygnsmedel (°C)\n"
            "  3  = Vindriktning 10 min (grader)\n"
            "  4  = Vindhastighet 10 min (m/s)\n"
            "  6  = Relativ fuktighet (%)\n"
            "  7  = Nederbördsmängd (mm)\n"
            "  8  = Snödjup (cm)\n"
            "  9  = Lufttryck reducerat (hPa)\n"
            "  10 = Solskenstid (h)\n"
            "  12 = Sikt (m)\n"
            "  13 = Byvind (m/s)\n"
            "  16 = Total molntäckning (1/8)\n"
            "  39 = Daggpunktstemperatur (°C)\n"
            "Standard: parameter_key=1 (lufttemperatur). "
            "Ange platsnamn via location — verktyget geocodar automatiskt till lat/long och hittar närmaste station. "
            "Du behöver INTE ange lat/lon separat om du anger location."
        ),
        keywords=["metobs", "observation", "station", "lufttemperatur", "lufttryck"],
        example_queries=[
            "Senaste temperaturmätningar vid närmaste station",
            "Lufttrycksobservationer i Stockholm",
        ],
        category=SMHI_CATEGORY_VADEROBS,
        base_path="/api/version/latest/parameter/{parameter_key}/station/{station_key}/period/{period_key}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_hydrologi_hydroobs",
        name="SMHI Hydrologi - Hydroobs",
        description=(
            "Hydrologiska observationer från stationer (vattenstånd, vattenföring, temperatur).\n"
            "Vanliga parameter_key-värden:\n"
            "  1 = Vattenstånd (cm)\n"
            "  2 = Vattenföring (m³/s)\n"
            "  3 = Vattentemperatur (°C)\n"
            "  4 = Is\n"
            "  5 = Grundvattenstånd\n"
            "Standard: parameter_key=3 (vattentemperatur). "
            "Ange platsnamn via location — verktyget geocodar automatiskt till lat/long och hittar närmaste station. "
            "Du behöver INTE ange lat/lon separat om du anger location."
        ),
        keywords=["hydroobs", "vattenstand", "vattenstånd", "vattenforing", "hydrologi"],
        example_queries=[
            "Vattenstånd i Mälaren senaste dygnet",
            "Vattenföring i närmaste vattendrag",
        ],
        category=SMHI_CATEGORY_HYDROLOGI,
        base_path="/api/version/latest/parameter/{parameter_key}/station/{station_key}/period/{period_key}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_hydrologi_pthbv",
        name="SMHI Hydrologi - PTHBV",
        description=(
            "Hydrologisk analys (PTHBV) för punktdata över perioder, t.ex. nederbörd/temperatur. "
            "Ange platsnamn via location — verktyget geocodar automatiskt till lat/long."
        ),
        keywords=["pthbv", "hydrologi", "nederbord", "nederbörd", "temperatur", "analys"],
        example_queries=[
            "Månadsvis nederbörd och temperatur för punkt i Dalarna",
            "Hydrologisk punktanalys 2020-2025",
        ],
        category=SMHI_CATEGORY_HYDROLOGI,
        base_path="/api/category/pthbv1g/version/1/geotype/multipoint/from/{from}/to/{to}/period/{period}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_oceanografi_ocobs",
        name="SMHI Oceanografi - Ocobs",
        description=(
            "Oceanografiska observationer (havsvattenstånd, vågor, temperatur, strömmar).\n"
            "Vanliga parameter_key-värden:\n"
            "  1  = Havsvattenstånd (cm)\n"
            "  6  = Havsvattentemperatur (°C)\n"
            "  7  = Strömriktning (grader)\n"
            "  8  = Strömhastighet (cm/s)\n"
            "  15 = Salthalt (PSU)\n"
            "  21 = Signifikant våghöjd (cm)\n"
            "Standard: parameter_key=6 (havsvattentemperatur). "
            "Ange platsnamn via location — verktyget geocodar automatiskt till lat/long och hittar närmaste station. "
            "Du behöver INTE ange lat/lon separat om du anger location."
        ),
        keywords=["ocobs", "oceanografi", "hav", "vaghojd", "våghöjd", "havsniva"],
        example_queries=[
            "Havsvattenstånd vid närmaste kuststation",
            "Oceanografiska mätningar i Östersjön",
        ],
        category=SMHI_CATEGORY_OCEANOGRAFI,
        base_path="/api/version/latest/parameter/{parameter_key}/station/{station_key}/period/{period_key}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_solstralning_strang",
        name="SMHI Solstrålning - STRÅNG",
        description=(
            "Solstrålningsdata från SMHI STRÅNG-modellen (timvärden). "
            "Täckning: lat 52–70 N, lon 2–30 E (Sverige och Skandinavien).\n"
            "Tillgängliga parameter-id:\n"
            "  116 = Global irradians (W/m²) [standard]\n"
            "  117 = Direkt normalirradians (W/m²)\n"
            "  118 = Diffus irradians (W/m²)\n"
            "  120 = UV-strålning (W/m²)\n"
            "  122 = PAR – fotosyntetiskt aktiv strålning (W/m²)\n"
            "Valfria filter: from_date/to_date (ISO datetime, t.ex. '2024-06-01T00:00:00'). "
            "Ange platsnamn via location — verktyget geocodar automatiskt till lat/long."
        ),
        keywords=["strang", "solstralning", "solstrålning", "uv", "par", "irradians", "sol", "solenergi"],
        example_queries=[
            "Hur mycket solstrålning är det i Göteborg idag?",
            "UV-strålning i Stockholm senaste veckan",
            "PAR-mätningar för Sundsvall i juni",
        ],
        category=SMHI_CATEGORY_SOLSTRALNING,
        base_path="/api/{parameter}",
    ),
    SmhiToolDefinition(
        tool_id="smhi_brandrisk_fwif",
        name="SMHI Brandrisk - FWIF",
        description=(
            "Brandriskprognoser (Fire Weather Index Forecast) med daily/hourly tidsupplösning. "
            "Ange platsnamn via location — verktyget geocodar automatiskt till lat/long."
        ),
        keywords=["fwif", "brandrisk", "fwi", "isi", "ffmc", "prognos"],
        example_queries=[
            "Brandriskprognos i Värmland idag",
            "FWI-index i skogsområde nära Umeå",
        ],
        category=SMHI_CATEGORY_BRANDRISK,
        base_path="/api/category/fwif1g/version/1/{period}/geotype/point/lon/{lon}/lat/{lat}/data.json",
    ),
    SmhiToolDefinition(
        tool_id="smhi_brandrisk_fwia",
        name="SMHI Brandrisk - FWIA",
        description=(
            "Brandriskanalys (Fire Weather Index Analysis) med daily/hourly tidsupplösning. "
            "Ange platsnamn via location — verktyget geocodar automatiskt till lat/long."
        ),
        keywords=["fwia", "brandrisk", "analys", "fwi", "isi", "ffmc"],
        example_queries=[
            "Brandriskanalys i Dalarna senaste dygnet",
            "FWIA i skogsområde nära Gävle",
        ],
        category=SMHI_CATEGORY_BRANDRISK,
        base_path="/api/category/fwia1g/version/1/{period}/geotype/point/lon/{lon}/lat/{lat}/data.json",
    ),
]

_SMHI_TOOL_BY_ID = {definition.tool_id: definition for definition in SMHI_TOOL_DEFINITIONS}


def _coerce_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _coerce_period(value: str | None, *, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in allowed:
        return normalized
    return default


# Regex patterns to extract a location name from a natural-language query
# such as "Vilken temperatur väntas i Malmö imorgon?"
_LOCATION_EXTRACTION_PATTERNS = [
    # "i Malmö", "i Stockholm", "för Göteborg", "vid Lund"
    re.compile(
        r"\b(?:i|för|vid|nära|runt|kring|från|till|over|över)\s+"
        r"([A-ZÅÄÖ][a-zåäöé]+(?:\s+[A-ZÅÄÖ][a-zåäöé]+)*)",
    ),
    # "Malmös väder", "Göteborgs temperatur" (possessive)
    re.compile(r"\b([A-ZÅÄÖ][a-zåäöé]+)s\s+(?:väder|temperatur|prognos|snö)"),
]


def _extract_location_from_query(query: str) -> str | None:
    """Try to extract a location name from a natural-language query string."""
    if not query:
        return None
    for pattern in _LOCATION_EXTRACTION_PATTERNS:
        match = pattern.search(query)
        if match:
            return match.group(1).strip()
    return None


async def _resolve_coordinates(
    *,
    location: str | None,
    lat: float | None,
    lon: float | None,
    country_code: str | None = None,
    query: str | None = None,
) -> tuple[float | None, float | None, dict[str, Any]]:
    if lat is not None and lon is not None:
        return float(lat), float(lon), {
            "name": location,
            "lat": lat,
            "lon": lon,
            "source": "user",
        }

    # Fallback: if location is missing, try to extract from query
    effective_location = location
    if not effective_location and query:
        # Try to extract a proper location name from the query string
        extracted = _extract_location_from_query(query)
        effective_location = extracted or query
    if not effective_location:
        return None, None, {
            "status": "error",
            "error": "Provide either lat/lon or a location name.",
        }

    geocoded = await _geocode_location(effective_location, country_code=country_code)
    if not geocoded and effective_location != (location or ""):
        # If we used the extracted/query and it failed, try the raw query too
        extracted = _extract_location_from_query(effective_location)
        if extracted and extracted != effective_location:
            geocoded = await _geocode_location(extracted, country_code=country_code)
            if geocoded:
                effective_location = extracted
    if not geocoded:
        return None, None, {
            "status": "error",
            "error": "Could not resolve location.",
            "location": {"query": effective_location},
        }

    resolved_lat = _parse_float(geocoded.get("lat"))
    resolved_lon = _parse_float(geocoded.get("lon"))
    if resolved_lat is None or resolved_lon is None:
        return None, None, {
            "status": "error",
            "error": "Geocoding returned invalid coordinates.",
            "location": {"query": effective_location},
        }

    return resolved_lat, resolved_lon, {
        "name": effective_location,
        "display_name": geocoded.get("display_name"),
        "lat": resolved_lat,
        "lon": resolved_lon,
        "source": "nominatim",
    }


def _parse_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_units_from_series_entry(entry: dict[str, Any]) -> dict[str, str]:
    parameters = entry.get("parameters")
    if not isinstance(parameters, list):
        return {}
    units: dict[str, str] = {}
    for item in parameters:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        unit = item.get("unit")
        if name and unit:
            units[str(name)] = str(unit)
    return units


def _normalize_grid_timeseries(
    payload: dict[str, Any],
    *,
    max_hours: int | None = None,
    max_points: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, str]]:
    series_raw = payload.get("timeSeries")
    if not isinstance(series_raw, list) or not series_raw:
        return [], None, {}

    now = datetime.now(UTC)
    limit_time = now + timedelta(hours=max_hours) if max_hours is not None else None
    normalized: list[tuple[datetime | None, dict[str, Any], dict[str, Any]]] = []
    for raw_entry in series_raw:
        if not isinstance(raw_entry, dict):
            continue
        valid_time_raw, parameters = normalize_timeseries_entry(raw_entry)
        valid_dt = _parse_iso_datetime(valid_time_raw) if valid_time_raw else None
        if limit_time and valid_dt and valid_dt > limit_time:
            continue
        normalized.append((valid_dt, {"valid_time": valid_time_raw, "parameters": parameters}, raw_entry))

    if not normalized:
        return [], None, {}

    if max_points is not None and max_points > 0 and len(normalized) > max_points:
        normalized = normalized[:max_points]

    current_tuple = min(
        normalized,
        key=lambda item: abs((item[0] - now).total_seconds()) if item[0] else float("inf"),
    )
    current_data = current_tuple[1]
    current_units = _extract_units_from_series_entry(current_tuple[2])

    return [item[1] for item in normalized], current_data, current_units


def _build_grid_payload(
    *,
    tool_id: str,
    category: str,
    payload: dict[str, Any],
    source_url: str,
    requested_lat: float,
    requested_lon: float,
    location: dict[str, Any],
    timeseries: list[dict[str, Any]],
    current: dict[str, Any] | None,
    units: dict[str, str] | None = None,
    include_raw: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_parameters = current.get("parameters") if isinstance(current, dict) else {}
    summary = (
        summarize_parameter_maps(current_parameters)
        if isinstance(current_parameters, dict)
        else {}
    )
    result: dict[str, Any] = {
        "status": "ok",
        "tool": tool_id,
        "category": category,
        "attribution": "Data from SMHI",
        "source": {
            "provider": SMHI_SOURCE,
            "url": source_url,
            "requested_point": {"lat": requested_lat, "lon": requested_lon},
            "grid_point": extract_grid_point(payload),
        },
        "location": location,
        "current": {
            "valid_time": current.get("valid_time") if isinstance(current, dict) else None,
            "parameters": current_parameters,
            "summary": summary,
            "units": units or {},
        },
        "timeseries": timeseries,
    }
    if include_raw:
        result["raw"] = payload
    if extra:
        result.update(extra)
    return result


_SMHI_REGISTRY_CACHE: dict[str, BaseTool] | None = None


def build_smhi_tool_registry() -> dict[str, BaseTool]:
    global _SMHI_REGISTRY_CACHE
    if _SMHI_REGISTRY_CACHE is not None:
        return _SMHI_REGISTRY_CACHE

    service = SmhiService()

    async def _run_with_breaker(
        *,
        tool_id: str,
        query: dict[str, Any],
        operation,
    ) -> dict[str, Any]:
        breaker = get_breaker("smhi")
        if not breaker.can_execute():
            return {
                "status": "error",
                "tool": tool_id,
                "query": query,
                "error": f"Service {breaker.name} temporarily unavailable (circuit open)",
            }
        try:
            result = await operation()
            breaker.record_success()
            return result
        except Exception as exc:
            breaker.record_failure()
            logger.exception("SMHI tool %s failed: %s", tool_id, exc)
            return {
                "status": "error",
                "tool": tool_id,
                "query": query,
                "error": f"SMHI request failed: {exc!s}",
            }

    async def _run_metfcst(
        *,
        tool_id: str,
        location: str | None,
        lat: float | None,
        lon: float | None,
        country_code: str | None,
        include_raw: bool,
        max_hours: int | None,
        query: str | None = None,
    ) -> dict[str, Any]:
        resolved_lat, resolved_lon, resolved_location = await _resolve_coordinates(
            location=location,
            lat=lat,
            lon=lon,
            country_code=country_code,
            query=query,
        )
        if resolved_lat is None or resolved_lon is None:
            return resolved_location

        if max_hours is None:
            max_hours = DEFAULT_SMHI_MAX_HOURS
        max_hours = _coerce_int(
            max_hours,
            default=DEFAULT_SMHI_MAX_HOURS,
            minimum=1,
            maximum=MAX_SMHI_MAX_HOURS,
        )

        payload, smhi_lat, smhi_lon, smhi_decimals, _ = await service.fetch_grid_point_data(
            base_url=SMHI_METFCST_BASE_URL,
            category="pmp3g",
            version="2",
            lon=resolved_lon,
            lat=resolved_lat,
        )
        timeseries, current, units = _normalize_grid_timeseries(
            payload,
            max_hours=max_hours,
            max_points=max_hours + 8,
        )
        if not timeseries or not current:
            return {
                "status": "error",
                "tool": tool_id,
                "error": "SMHI response did not include parseable time series data.",
                "location": resolved_location,
            }
        source_url = build_source_url(
            base_url=SMHI_METFCST_BASE_URL,
            category="pmp3g",
            version="2",
            lon=smhi_lon,
            lat=smhi_lat,
            decimals=smhi_decimals,
        )
        return _build_grid_payload(
            tool_id=tool_id,
            category=SMHI_CATEGORY_VADERPROGNOS,
            payload=payload,
            source_url=source_url,
            requested_lat=smhi_lat,
            requested_lon=smhi_lon,
            location=resolved_location,
            timeseries=timeseries,
            current=current,
            units=units,
            include_raw=include_raw,
            extra={"max_hours": max_hours, "forecast_model": "pmp3g"},
        )

    @tool("smhi_weather", description=_SMHI_TOOL_BY_ID["smhi_weather"].description)
    async def smhi_weather(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        include_raw: bool = False,
        max_hours: int | None = DEFAULT_SMHI_MAX_HOURS,
        query: str | None = None,
    ) -> dict[str, Any]:
        return await _run_with_breaker(
            tool_id="smhi_weather",
            query={
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "include_raw": include_raw,
                "max_hours": max_hours,
            },
            operation=lambda: _run_metfcst(
                tool_id="smhi_weather",
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                include_raw=include_raw,
                max_hours=max_hours,
                query=query,
            ),
        )

    @tool(
        "smhi_vaderprognoser_metfcst",
        description=_SMHI_TOOL_BY_ID["smhi_vaderprognoser_metfcst"].description,
    )
    async def smhi_vaderprognoser_metfcst(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        include_raw: bool = False,
        max_hours: int | None = DEFAULT_SMHI_MAX_HOURS,
        query: str | None = None,
    ) -> dict[str, Any]:
        return await _run_with_breaker(
            tool_id="smhi_vaderprognoser_metfcst",
            query={
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "include_raw": include_raw,
                "max_hours": max_hours,
            },
            operation=lambda: _run_metfcst(
                tool_id="smhi_vaderprognoser_metfcst",
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                include_raw=include_raw,
                max_hours=max_hours,
                query=query,
            ),
        )

    @tool(
        "smhi_vaderprognoser_snow1g",
        description=_SMHI_TOOL_BY_ID["smhi_vaderprognoser_snow1g"].description,
    )
    async def smhi_vaderprognoser_snow1g(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        max_points: int = 72,
        include_raw: bool = False,
        include_parameters: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        async def _operation() -> dict[str, Any]:
            resolved_lat, resolved_lon, resolved_location = await _resolve_coordinates(
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                query=query,
            )
            if resolved_lat is None or resolved_lon is None:
                return resolved_location

            payload, smhi_lat, smhi_lon, smhi_decimals, _ = (
                await service.fetch_grid_point_data(
                    base_url=SMHI_METFCST_BASE_URL,
                    category="snow1g",
                    version="1",
                    lon=resolved_lon,
                    lat=resolved_lat,
                )
            )
            points_limit = _coerce_int(max_points, default=72, minimum=1, maximum=240)
            timeseries, current, units = _normalize_grid_timeseries(
                payload,
                max_points=points_limit,
            )
            if not timeseries or not current:
                return {
                    "status": "error",
                    "tool": "smhi_vaderprognoser_snow1g",
                    "error": "SMHI response did not include parseable time series data.",
                    "location": resolved_location,
                }

            source_url = build_source_url(
                base_url=SMHI_METFCST_BASE_URL,
                category="snow1g",
                version="1",
                lon=smhi_lon,
                lat=smhi_lat,
                decimals=smhi_decimals,
            )
            result = _build_grid_payload(
                tool_id="smhi_vaderprognoser_snow1g",
                category=SMHI_CATEGORY_VADERPROGNOS,
                payload=payload,
                source_url=source_url,
                requested_lat=smhi_lat,
                requested_lon=smhi_lon,
                location=resolved_location,
                timeseries=timeseries,
                current=current,
                units=units,
                include_raw=include_raw,
                extra={"forecast_model": "snow1g", "max_points": points_limit},
            )
            if include_parameters:
                result["parameters"] = await service.fetch_grid_parameters(
                    base_url=SMHI_METFCST_BASE_URL,
                    category="snow1g",
                    version="1",
                )
            return result

        return await _run_with_breaker(
            tool_id="smhi_vaderprognoser_snow1g",
            query={
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "max_points": max_points,
                "include_raw": include_raw,
                "include_parameters": include_parameters,
            },
            operation=_operation,
        )

    @tool(
        "smhi_vaderanalyser_mesan2g",
        description=_SMHI_TOOL_BY_ID["smhi_vaderanalyser_mesan2g"].description,
    )
    async def smhi_vaderanalyser_mesan2g(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        max_points: int = 48,
        include_raw: bool = False,
        include_parameters: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        async def _operation() -> dict[str, Any]:
            resolved_lat, resolved_lon, resolved_location = await _resolve_coordinates(
                location=location,
                lat=lat,
                lon=lon,
                query=query,
                country_code=country_code,
            )
            if resolved_lat is None or resolved_lon is None:
                return resolved_location

            payload, smhi_lat, smhi_lon, smhi_decimals, _ = (
                await service.fetch_grid_point_data(
                    base_url=SMHI_METANALYS_BASE_URL,
                    category="mesan2g",
                    version="2",
                    lon=resolved_lon,
                    lat=resolved_lat,
                )
            )
            points_limit = _coerce_int(max_points, default=48, minimum=1, maximum=240)
            timeseries, current, units = _normalize_grid_timeseries(
                payload,
                max_points=points_limit,
            )
            if not timeseries or not current:
                return {
                    "status": "error",
                    "tool": "smhi_vaderanalyser_mesan2g",
                    "error": "SMHI response did not include parseable time series data.",
                    "location": resolved_location,
                }

            source_url = build_source_url(
                base_url=SMHI_METANALYS_BASE_URL,
                category="mesan2g",
                version="2",
                lon=smhi_lon,
                lat=smhi_lat,
                decimals=smhi_decimals,
            )
            result = _build_grid_payload(
                tool_id="smhi_vaderanalyser_mesan2g",
                category=SMHI_CATEGORY_VADERANALYS,
                payload=payload,
                source_url=source_url,
                requested_lat=smhi_lat,
                requested_lon=smhi_lon,
                location=resolved_location,
                timeseries=timeseries,
                current=current,
                units=units,
                include_raw=include_raw,
                extra={"analysis_model": "mesan2g", "max_points": points_limit},
            )
            if include_parameters:
                result["parameters"] = await service.fetch_grid_parameters(
                    base_url=SMHI_METANALYS_BASE_URL,
                    category="mesan2g",
                    version="2",
                )
            return result

        return await _run_with_breaker(
            tool_id="smhi_vaderanalyser_mesan2g",
            query={
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "max_points": max_points,
                "include_raw": include_raw,
                "include_parameters": include_parameters,
            },
            operation=_operation,
        )

    @tool(
        "smhi_brandrisk_fwif",
        description=_SMHI_TOOL_BY_ID["smhi_brandrisk_fwif"].description,
    )
    async def smhi_brandrisk_fwif(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        period: str | None = "hourly",
        max_points: int = 72,
        include_raw: bool = False,
        include_parameters: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        async def _operation() -> dict[str, Any]:
            resolved_lat, resolved_lon, resolved_location = await _resolve_coordinates(
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                query=query,
            )
            if resolved_lat is None or resolved_lon is None:
                return resolved_location

            resolved_period = _coerce_period(
                period, allowed={"hourly", "daily"}, default="hourly"
            )
            payload, smhi_lat, smhi_lon, smhi_decimals, _ = (
                await service.fetch_grid_point_data(
                    base_url=SMHI_METFCST_BASE_URL,
                    category="fwif1g",
                    version="1",
                    period=resolved_period,
                    lon=resolved_lon,
                    lat=resolved_lat,
                )
            )
            points_limit = _coerce_int(max_points, default=72, minimum=1, maximum=240)
            timeseries, current, units = _normalize_grid_timeseries(
                payload,
                max_points=points_limit,
            )
            if not timeseries or not current:
                return {
                    "status": "error",
                    "tool": "smhi_brandrisk_fwif",
                    "error": "SMHI response did not include parseable time series data.",
                    "location": resolved_location,
                }

            source_url = build_source_url(
                base_url=SMHI_METFCST_BASE_URL,
                category="fwif1g",
                version="1",
                period=resolved_period,
                lon=smhi_lon,
                lat=smhi_lat,
                decimals=smhi_decimals,
            )
            result = _build_grid_payload(
                tool_id="smhi_brandrisk_fwif",
                category=SMHI_CATEGORY_BRANDRISK,
                payload=payload,
                source_url=source_url,
                requested_lat=smhi_lat,
                requested_lon=smhi_lon,
                location=resolved_location,
                timeseries=timeseries,
                current=current,
                units=units,
                include_raw=include_raw,
                extra={
                    "risk_model": "fwif1g",
                    "period": resolved_period,
                    "max_points": points_limit,
                },
            )
            if include_parameters:
                result["parameters"] = await service.fetch_grid_parameters(
                    base_url=SMHI_METFCST_BASE_URL,
                    category="fwif1g",
                    version="1",
                    period=resolved_period,
                )
            return result

        return await _run_with_breaker(
            tool_id="smhi_brandrisk_fwif",
            query={
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "period": period,
                "max_points": max_points,
                "include_raw": include_raw,
                "include_parameters": include_parameters,
            },
            operation=_operation,
        )

    @tool(
        "smhi_brandrisk_fwia",
        description=_SMHI_TOOL_BY_ID["smhi_brandrisk_fwia"].description,
    )
    async def smhi_brandrisk_fwia(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        period: str | None = "hourly",
        from_date: str | None = None,
        to_date: str | None = None,
        max_points: int = 72,
        include_raw: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        async def _operation() -> dict[str, Any]:
            resolved_lat, resolved_lon, resolved_location = await _resolve_coordinates(
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                query=query,
            )
            if resolved_lat is None or resolved_lon is None:
                return resolved_location

            resolved_period = _coerce_period(
                period, allowed={"hourly", "daily"}, default="hourly"
            )
            query_params: dict[str, Any] = {}
            if from_date:
                query_params["from"] = from_date
            if to_date:
                query_params["to"] = to_date

            payload, smhi_lat, smhi_lon, smhi_decimals, _ = (
                await service.fetch_grid_point_data(
                    base_url=SMHI_METANALYS_BASE_URL,
                    category="fwia1g",
                    version="1",
                    period=resolved_period,
                    lon=resolved_lon,
                    lat=resolved_lat,
                    query_params=query_params or None,
                )
            )
            points_limit = _coerce_int(max_points, default=72, minimum=1, maximum=240)
            timeseries, current, units = _normalize_grid_timeseries(
                payload,
                max_points=points_limit,
            )
            if not timeseries or not current:
                return {
                    "status": "error",
                    "tool": "smhi_brandrisk_fwia",
                    "error": "SMHI response did not include parseable time series data.",
                    "location": resolved_location,
                }

            source_url = build_source_url(
                base_url=SMHI_METANALYS_BASE_URL,
                category="fwia1g",
                version="1",
                period=resolved_period,
                lon=smhi_lon,
                lat=smhi_lat,
                decimals=smhi_decimals,
                query_params=query_params,
            )
            return _build_grid_payload(
                tool_id="smhi_brandrisk_fwia",
                category=SMHI_CATEGORY_BRANDRISK,
                payload=payload,
                source_url=source_url,
                requested_lat=smhi_lat,
                requested_lon=smhi_lon,
                location=resolved_location,
                timeseries=timeseries,
                current=current,
                units=units,
                include_raw=include_raw,
                extra={
                    "analysis_model": "fwia1g",
                    "period": resolved_period,
                    "from_date": from_date,
                    "to_date": to_date,
                    "max_points": points_limit,
                },
            )

        return await _run_with_breaker(
            tool_id="smhi_brandrisk_fwia",
            query={
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "period": period,
                "from_date": from_date,
                "to_date": to_date,
                "max_points": max_points,
                "include_raw": include_raw,
            },
            operation=_operation,
        )

    async def _run_observation(
        *,
        tool_id: str,
        base_url: str,
        category: str,
        default_parameter_key: str,
        location: str | None,
        lat: float | None,
        lon: float | None,
        country_code: str | None,
        parameter_key: str | None,
        station_key: str | None,
        period_key: str | None,
        limit_values: int,
        include_catalog: bool,
        query: str | None = None,
    ) -> dict[str, Any]:
        # Fallback: use query as location if not provided
        effective_location = location or query
        resolved_lat = lat
        resolved_lon = lon
        resolved_location = {
            "name": effective_location,
            "lat": lat,
            "lon": lon,
            "source": "user" if lat is not None and lon is not None else None,
        }
        if (resolved_lat is None or resolved_lon is None) and effective_location:
            g_lat, g_lon, loc = await _resolve_coordinates(
                location=effective_location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                query=query,
            )
            if g_lat is not None and g_lon is not None:
                resolved_lat, resolved_lon = g_lat, g_lon
                resolved_location = loc

        chosen_parameter_key = str(parameter_key or default_parameter_key).strip()
        if not chosen_parameter_key:
            return {
                "status": "error",
                "tool": tool_id,
                "error": "Missing parameter_key.",
            }

        limit_values = _coerce_int(limit_values, default=120, minimum=1, maximum=1000)

        # Fetch observation series and (optionally) catalog in parallel.
        if include_catalog:
            obs_payload, catalog_raw = await asyncio.gather(
                service.fetch_observation_series(
                    base_url=base_url,
                    parameter_key=chosen_parameter_key,
                    station_key=station_key,
                    period_key=period_key,
                    lat=_parse_float(resolved_lat),
                    lon=_parse_float(resolved_lon),
                    limit_values=limit_values,
                ),
                service.fetch_latest_catalog(base_url=base_url),
            )
        else:
            obs_payload = await service.fetch_observation_series(
                base_url=base_url,
                parameter_key=chosen_parameter_key,
                station_key=station_key,
                period_key=period_key,
                lat=_parse_float(resolved_lat),
                lon=_parse_float(resolved_lon),
                limit_values=limit_values,
            )
            catalog_raw = None

        values = obs_payload.get("values")
        normalized_values: list[dict[str, Any]] = []
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, dict):
                    continue
                normalized_values.append(
                    {str(key): parse_observation_value(value) for key, value in item.items()}
                )
        result: dict[str, Any] = {
            "status": "ok",
            "tool": tool_id,
            "category": category,
            "attribution": "Data from SMHI",
            "source": {
                "provider": SMHI_SOURCE,
                "base_url": base_url,
                "parameter_url": obs_payload.get("parameter_url"),
                "station_url": obs_payload.get("station_url"),
                "period_url": obs_payload.get("period_url"),
                "data_source_url": obs_payload.get("data_source_url"),
                "data_format": obs_payload.get("data_format"),
            },
            "location": resolved_location,
            "parameter": obs_payload.get("parameter"),
            "station": obs_payload.get("station"),
            "period": obs_payload.get("period"),
            "values": normalized_values,
            "value_count": obs_payload.get("value_count"),
            "truncated": obs_payload.get("truncated"),
        }
        if catalog_raw is not None:
            resources = catalog_raw.get("resource")
            result["catalog"] = {
                "title": catalog_raw.get("title"),
                "updated": catalog_raw.get("updated"),
                "resource_count": len(resources) if isinstance(resources, list) else 0,
                "resources": resources[:80] if isinstance(resources, list) else [],
            }
        return result

    @tool(
        "smhi_vaderobservationer_metobs",
        description=_SMHI_TOOL_BY_ID["smhi_vaderobservationer_metobs"].description,
    )
    async def smhi_vaderobservationer_metobs(
        parameter_key: str = "1",
        station_key: str | None = None,
        period_key: str | None = None,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        limit_values: int = 120,
        include_catalog: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        return await _run_with_breaker(
            tool_id="smhi_vaderobservationer_metobs",
            query={
                "parameter_key": parameter_key,
                "station_key": station_key,
                "period_key": period_key,
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "limit_values": limit_values,
                "include_catalog": include_catalog,
            },
            operation=lambda: _run_observation(
                tool_id="smhi_vaderobservationer_metobs",
                base_url=SMHI_METOBS_BASE_URL,
                category=SMHI_CATEGORY_VADEROBS,
                default_parameter_key="1",
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                parameter_key=parameter_key,
                station_key=station_key,
                period_key=period_key,
                limit_values=limit_values,
                include_catalog=include_catalog,
                query=query,
            ),
        )

    @tool(
        "smhi_hydrologi_hydroobs",
        description=_SMHI_TOOL_BY_ID["smhi_hydrologi_hydroobs"].description,
    )
    async def smhi_hydrologi_hydroobs(
        parameter_key: str = "3",
        station_key: str | None = None,
        period_key: str | None = None,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        limit_values: int = 120,
        include_catalog: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        return await _run_with_breaker(
            tool_id="smhi_hydrologi_hydroobs",
            query={
                "parameter_key": parameter_key,
                "station_key": station_key,
                "period_key": period_key,
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "limit_values": limit_values,
                "include_catalog": include_catalog,
            },
            operation=lambda: _run_observation(
                tool_id="smhi_hydrologi_hydroobs",
                base_url=SMHI_HYDROOBS_BASE_URL,
                category=SMHI_CATEGORY_HYDROLOGI,
                default_parameter_key="3",
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                parameter_key=parameter_key,
                station_key=station_key,
                period_key=period_key,
                limit_values=limit_values,
                include_catalog=include_catalog,
                query=query,
            ),
        )

    @tool(
        "smhi_oceanografi_ocobs",
        description=_SMHI_TOOL_BY_ID["smhi_oceanografi_ocobs"].description,
    )
    async def smhi_oceanografi_ocobs(
        parameter_key: str = "6",
        station_key: str | None = None,
        period_key: str | None = None,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        limit_values: int = 120,
        include_catalog: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        return await _run_with_breaker(
            tool_id="smhi_oceanografi_ocobs",
            query={
                "parameter_key": parameter_key,
                "station_key": station_key,
                "period_key": period_key,
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "limit_values": limit_values,
                "include_catalog": include_catalog,
            },
            operation=lambda: _run_observation(
                tool_id="smhi_oceanografi_ocobs",
                base_url=SMHI_OCOBS_BASE_URL,
                category=SMHI_CATEGORY_OCEANOGRAFI,
                default_parameter_key="6",
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                parameter_key=parameter_key,
                station_key=station_key,
                period_key=period_key,
                limit_values=limit_values,
                include_catalog=include_catalog,
                query=query,
            ),
        )

    @tool(
        "smhi_hydrologi_pthbv",
        description=_SMHI_TOOL_BY_ID["smhi_hydrologi_pthbv"].description,
    )
    async def smhi_hydrologi_pthbv(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        from_year: int = 2022,
        to_year: int = 2024,
        period: str = "monthly",
        variables: list[str] | None = None,
        epsg: int = 4326,
        include_raw: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        async def _operation() -> dict[str, Any]:
            resolved_lat, resolved_lon, resolved_location = await _resolve_coordinates(
                location=location,
                lat=lat,
                lon=lon,
                query=query,
                country_code=country_code,
            )
            if resolved_lat is None or resolved_lon is None:
                return resolved_location

            resolved_period = _coerce_period(
                period,
                allowed={"monthly", "yearly", "daily"},
                default="monthly",
            )
            resolved_from_year = _coerce_int(
                from_year, default=2022, minimum=1900, maximum=2100
            )
            resolved_to_year = _coerce_int(
                to_year, default=resolved_from_year, minimum=1900, maximum=2100
            )
            if resolved_to_year < resolved_from_year:
                resolved_from_year, resolved_to_year = (
                    resolved_to_year,
                    resolved_from_year,
                )
            resolved_variables = variables or ["p", "t"]
            resolved_variables = [
                str(item).strip().lower()
                for item in resolved_variables
                if str(item).strip()
            ]
            if not resolved_variables:
                resolved_variables = ["p", "t"]

            payload, source_url = await service.fetch_pthbv_data(
                lon=resolved_lon,
                lat=resolved_lat,
                from_year=resolved_from_year,
                to_year=resolved_to_year,
                period=resolved_period,
                variables=resolved_variables,
                epsg=_coerce_int(epsg, default=4326, minimum=2000, maximum=9999),
            )
            result: dict[str, Any] = {
                "status": "ok",
                "tool": "smhi_hydrologi_pthbv",
                "category": SMHI_CATEGORY_HYDROLOGI,
                "attribution": "Data from SMHI",
                "source": {
                    "provider": SMHI_SOURCE,
                    "url": source_url,
                    "requested_point": {"lat": resolved_lat, "lon": resolved_lon},
                },
                "location": resolved_location,
                "query": {
                    "from_year": resolved_from_year,
                    "to_year": resolved_to_year,
                    "period": resolved_period,
                    "variables": resolved_variables,
                    "epsg": epsg,
                },
                "dates": payload.get("dates"),
                "coord_sys_info": payload.get("coord_sys_info"),
                "point_values": payload.get("point_values"),
            }
            if include_raw:
                result["raw"] = payload
            return result

        return await _run_with_breaker(
            tool_id="smhi_hydrologi_pthbv",
            query={
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "from_year": from_year,
                "to_year": to_year,
                "period": period,
                "variables": variables,
                "epsg": epsg,
                "include_raw": include_raw,
            },
            operation=_operation,
        )

    _STRANG_PARAMETER_NAMES: dict[int, str] = {
        116: "Global irradians",
        117: "Direkt normalirradians",
        118: "Diffus irradians",
        120: "UV-strålning",
        122: "PAR (fotosyntetiskt aktiv strålning)",
    }
    _STRANG_ALLOWED_PARAMETERS: frozenset[int] = frozenset(_STRANG_PARAMETER_NAMES)

    @tool(
        "smhi_solstralning_strang",
        description=_SMHI_TOOL_BY_ID["smhi_solstralning_strang"].description,
    )
    async def smhi_solstralning_strang(
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        country_code: str | None = None,
        parameter: int = 116,
        from_date: str | None = None,
        to_date: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        async def _operation() -> dict[str, Any]:
            resolved_lat, resolved_lon, resolved_location = await _resolve_coordinates(
                location=location,
                lat=lat,
                lon=lon,
                country_code=country_code,
                query=query,
            )
            if resolved_lat is None or resolved_lon is None:
                return resolved_location

            resolved_parameter = (
                parameter if parameter in _STRANG_ALLOWED_PARAMETERS else 116
            )

            payload = await service.fetch_strang_data(
                parameter=resolved_parameter,
                lat=resolved_lat,
                lon=resolved_lon,
                from_date=from_date,
                to_date=to_date,
            )

            time_data = payload.get("time") if isinstance(payload, dict) else None
            value_data = payload.get("values") if isinstance(payload, dict) else None

            timeseries: list[dict[str, Any]] = []
            if isinstance(time_data, list) and isinstance(value_data, list):
                for t, v in zip(time_data, value_data, strict=False):
                    timeseries.append({"time": t, "value_wm2": v})

            source_url = f"{SMHI_STRANG_BASE_URL}/{resolved_parameter}?lat={resolved_lat}&lon={resolved_lon}"
            if from_date:
                source_url += f"&from={from_date}"
            if to_date:
                source_url += f"&to={to_date}"

            return {
                "status": "ok",
                "tool": "smhi_solstralning_strang",
                "category": SMHI_CATEGORY_SOLSTRALNING,
                "attribution": "Data from SMHI STRÅNG",
                "source": {
                    "provider": SMHI_SOURCE,
                    "url": source_url,
                    "requested_point": {"lat": resolved_lat, "lon": resolved_lon},
                },
                "location": resolved_location,
                "parameter": {
                    "id": resolved_parameter,
                    "name": _STRANG_PARAMETER_NAMES.get(resolved_parameter, str(resolved_parameter)),
                    "unit": "W/m²",
                },
                "timeseries": timeseries,
                "value_count": len(timeseries),
                "query": {
                    "from_date": from_date,
                    "to_date": to_date,
                },
            }

        return await _run_with_breaker(
            tool_id="smhi_solstralning_strang",
            query={
                "location": location,
                "lat": lat,
                "lon": lon,
                "country_code": country_code,
                "parameter": parameter,
                "from_date": from_date,
                "to_date": to_date,
            },
            operation=_operation,
        )

    registry: dict[str, BaseTool] = {
        "smhi_weather": smhi_weather,
        "smhi_vaderprognoser_metfcst": smhi_vaderprognoser_metfcst,
        "smhi_vaderprognoser_snow1g": smhi_vaderprognoser_snow1g,
        "smhi_vaderanalyser_mesan2g": smhi_vaderanalyser_mesan2g,
        "smhi_vaderobservationer_metobs": smhi_vaderobservationer_metobs,
        "smhi_hydrologi_hydroobs": smhi_hydrologi_hydroobs,
        "smhi_hydrologi_pthbv": smhi_hydrologi_pthbv,
        "smhi_oceanografi_ocobs": smhi_oceanografi_ocobs,
        "smhi_brandrisk_fwif": smhi_brandrisk_fwif,
        "smhi_brandrisk_fwia": smhi_brandrisk_fwia,
        "smhi_solstralning_strang": smhi_solstralning_strang,
    }
    _SMHI_REGISTRY_CACHE = registry
    return registry


def create_smhi_tool(definition: SmhiToolDefinition) -> BaseTool:
    registry = build_smhi_tool_registry()
    return registry[definition.tool_id]


def create_smhi_weather_tool() -> BaseTool:
    registry = build_smhi_tool_registry()
    return registry["smhi_weather"]


__all__ = [
    "SMHI_TOOL_DEFINITIONS",
    "SmhiToolDefinition",
    "build_smhi_tool_registry",
    "create_smhi_tool",
    "create_smhi_weather_tool",
]
