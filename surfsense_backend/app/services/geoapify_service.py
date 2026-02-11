from __future__ import annotations

import os
from typing import Any
import re
from urllib.parse import urlencode

GEOAPIFY_STATIC_MAP_BASE_URL = "https://maps.geoapify.com/v1/staticmap"
GEOAPIFY_SOURCE = "Geoapify Static Maps API"
GEOAPIFY_STYLE_OPTIONS = {
    "osm-carto",
    "carto",
    "dark-matter",
    "klokantech-basic",
    "osm-bright",
    "toner",
    "toner-grey",
    "osm-liberty",
    "maptiler-3d",
    "positron",
    "dark-matter-brown",
    "dark-matter-dark-grey",
    "dark-matter-dark-purple",
    "dark-matter-purple-roads",
    "dark-matter-yellow-roads",
    "osm-bright-grey",
    "osm-bright-smooth",
    "positron-blue",
    "positron-red",
}

GEOAPIFY_NAMED_COLORS = {
    "red": "#ef4444",
    "blue": "#3b82f6",
    "green": "#22c55e",
    "yellow": "#eab308",
    "orange": "#f97316",
    "purple": "#a855f7",
    "pink": "#ec4899",
    "black": "#111827",
    "white": "#ffffff",
    "gray": "#6b7280",
    "grey": "#6b7280",
}


def _normalize_color(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned in GEOAPIFY_NAMED_COLORS:
        return GEOAPIFY_NAMED_COLORS[cleaned]
    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"
    if re.fullmatch(r"#([0-9a-f]{6}|[0-9a-f]{3})", cleaned):
        return cleaned
    return None


def _normalize_style(value: str | None) -> str:
    if not value:
        return "osm-carto"
    cleaned = value.strip().lower().replace("_", "-")
    if cleaned in GEOAPIFY_STYLE_OPTIONS:
        return cleaned
    return "osm-carto"


class GeoapifyService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = GEOAPIFY_STATIC_MAP_BASE_URL,
    ) -> None:
        self.api_key = (api_key or os.getenv("GEOAPIFY_API_KEY") or "").strip()
        self.base_url = base_url.rstrip("/")

    def build_static_map_url(
        self,
        *,
        center_lat: float,
        center_lon: float,
        zoom: int,
        width: int,
        height: int,
        style: str,
        image_format: str,
        markers: list[dict[str, Any]] | None = None,
    ) -> str:
        if not self.api_key:
            raise ValueError("Missing GEOAPIFY_API_KEY for Geoapify Static Maps.")

        params: list[tuple[str, str]] = []
        params.append(("style", _normalize_style(style)))
        params.append(("width", str(width)))
        params.append(("height", str(height)))
        params.append(("zoom", str(zoom)))
        params.append(("center", f"lonlat:{center_lon},{center_lat}"))
        params.append(("format", image_format))

        for marker in markers or []:
            lat = marker.get("lat")
            lon = marker.get("lon")
            if lat is None or lon is None:
                continue
            parts = [f"lonlat:{lon},{lat}"]
            color = _normalize_color(marker.get("color"))
            if color:
                parts.append(f"color:{color}")
            label = str(marker.get("label") or "").strip()
            if label:
                parts.append(f"text:{label[:3]}")
            size = str(marker.get("size") or "").strip()
            if size:
                parts.append(f"size:{size}")
            params.append(("marker", ";".join(parts)))

        params.append(("apiKey", self.api_key))
        return f"{self.base_url}?{urlencode(params)}"
