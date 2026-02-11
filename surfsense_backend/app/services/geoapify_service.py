from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

GEOAPIFY_STATIC_MAP_BASE_URL = "https://maps.geoapify.com/v1/staticmap"
GEOAPIFY_SOURCE = "Geoapify Static Maps API"


def _normalize_color(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"
    return cleaned


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
        params.append(("style", style))
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
