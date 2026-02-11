from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.agents.new_chat.tools.smhi_weather import _geocode_location
from app.services.geoapify_service import (
    GEOAPIFY_SOURCE,
    GEOAPIFY_STATIC_MAP_BASE_URL,
    GEOAPIFY_STYLE_OPTIONS,
    GeoapifyService,
)


@dataclass(frozen=True)
class GeoapifyToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    base_path: str
    category: str


GEOAPIFY_TOOL_DEFINITIONS: list[GeoapifyToolDefinition] = [
    GeoapifyToolDefinition(
        tool_id="geoapify_static_map",
        name="Geoapify Static Map",
        description=(
            "Skapa en statisk karta (PNG/JPG) för plats, adress eller koordinater. "
            "Stödjer zoom, storlek och markörer."
        ),
        keywords=[
            "karta",
            "kartbild",
            "statisk karta",
            "map",
            "geoapify",
            "plats",
            "adress",
            "vägarbete",
            "trafik",
            "position",
            "koordinat",
        ],
        example_queries=[
            "Visa en karta över Slussen i Stockholm",
            "Skapa en statisk karta för 59.3293, 18.0686",
            "Kartbild med markörer för vägarbeten i Göteborg",
        ],
        base_path="/v1/staticmap",
        category="kartor/geoapify",
    )
]


def _parse_center_string(
    value: str, markers: list[dict[str, Any]] | None = None
) -> tuple[float | None, float | None]:
    cleaned = (value or "").strip()
    if not cleaned or "," not in cleaned:
        return None, None
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if len(parts) != 2:
        return None, None
    try:
        first = float(parts[0])
        second = float(parts[1])
        if abs(first) > 90 and abs(second) <= 90:
            return second, first
        if markers:
            marker = markers[0]
            cand_a = (first, second)
            cand_b = (second, first)
            dist_a = abs(marker["lat"] - cand_a[0]) + abs(marker["lon"] - cand_a[1])
            dist_b = abs(marker["lat"] - cand_b[0]) + abs(marker["lon"] - cand_b[1])
            if dist_b < dist_a:
                return cand_b
        return first, second
    except ValueError:
        return None, None


def _normalize_markers(markers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for marker in markers or []:
        try:
            lat = marker.get("lat")
            lon = marker.get("lon")
            if lat is None or lon is None:
                continue
            label = str(marker.get("label") or "").strip().upper()
            label = re.sub(r"[^A-Z0-9]", "", label)
            label = label[:2] if label else None
            size = str(marker.get("size") or "").strip().lower()
            if size not in {"tiny", "small", "medium", "large"}:
                size = "medium"
            normalized.append(
                {
                    "lat": float(lat),
                    "lon": float(lon),
                    "color": marker.get("color"),
                    "label": label,
                    "size": size,
                }
            )
        except (TypeError, ValueError):
            continue
    return normalized


def _normalize_style(value: str | None) -> str:
    if not value:
        return "osm-carto"
    cleaned = value.strip().lower().replace("_", "-")
    if cleaned in GEOAPIFY_STYLE_OPTIONS:
        return cleaned
    return "osm-carto"


def create_geoapify_static_map_tool() -> BaseTool:
    service = GeoapifyService()

    @tool("geoapify_static_map", description=GEOAPIFY_TOOL_DEFINITIONS[0].description)
    async def geoapify_static_map(
        location: str | None = None,
        center: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        zoom: int | None = 12,
        width: int | None = 640,
        height: int | None = 400,
        markers: list[dict[str, Any]] | None = None,
        style: str | None = "osm-carto",
        image_format: str | None = "png",
        country_code: str | None = "se",
    ) -> dict[str, Any]:
        """
        Skapar en statisk karta via Geoapify Static Maps API.

        Args:
            location: Ort/adress som geokodas om lat/lon saknas.
            center: "lon,lat" som text (alternativ till lat/lon).
            lat/lon: Koordinater för kartans center.
            zoom: Zoom-nivå (1-20).
            width/height: Kartans storlek i pixlar.
            markers: Lista av markörer ({lat, lon, color, label, size}).
            style: Kartstil (t.ex. "osm-carto").
            image_format: "png" eller "jpg".
            country_code: ISO-landkod för geocoding (default "se").
        """
        try:
            center_lat = lat
            center_lon = lon
            resolved_location: dict[str, Any] | None = None
            marker_list = _normalize_markers(markers)

            if (center_lat is None or center_lon is None) and center:
                parsed_lat, parsed_lon = _parse_center_string(center, marker_list)
                center_lat = center_lat if center_lat is not None else parsed_lat
                center_lon = center_lon if center_lon is not None else parsed_lon

            if (center_lat is None or center_lon is None) and location:
                resolved_location = await _geocode_location(location, country_code)
                if not resolved_location:
                    return {
                        "status": "error",
                        "error": f"Could not geocode location: {location}",
                    }
                center_lat = float(resolved_location.get("lat"))
                center_lon = float(resolved_location.get("lon"))

            if (center_lat is None or center_lon is None) and marker_list:
                center_lat = marker_list[0]["lat"]
                center_lon = marker_list[0]["lon"]

            if center_lat is None or center_lon is None:
                return {
                    "status": "error",
                    "error": "Missing map center. Provide lat/lon, center, or location.",
                }

            if not marker_list:
                marker_list = [
                    {"lat": center_lat, "lon": center_lon, "color": "#e11d48", "size": "medium"}
                ]

            style_value = _normalize_style(style)
            image_url = service.build_static_map_url(
                center_lat=center_lat,
                center_lon=center_lon,
                zoom=int(zoom or 12),
                width=int(width or 640),
                height=int(height or 400),
                style=style_value,
                image_format=image_format or "png",
                markers=marker_list,
            )
            return {
                "status": "success",
                "tool": "geoapify_static_map",
                "source": GEOAPIFY_SOURCE,
                "base_path": GEOAPIFY_STATIC_MAP_BASE_URL,
                "query": {
                    "location": location,
                    "center": center,
                    "lat": center_lat,
                    "lon": center_lon,
                    "zoom": zoom,
                    "width": width,
                    "height": height,
                    "style": style_value,
                    "format": image_format,
                },
                "center": {
                    "lat": center_lat,
                    "lon": center_lon,
                    "name": resolved_location.get("display_name")
                    if resolved_location
                    else None,
                },
                "zoom": int(zoom or 12),
                "size": {"width": int(width or 640), "height": int(height or 400)},
                "markers": marker_list,
                "image_url": image_url,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    return geoapify_static_map


__all__ = ["GEOAPIFY_TOOL_DEFINITIONS", "create_geoapify_static_map_tool"]
