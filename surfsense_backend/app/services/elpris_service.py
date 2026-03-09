"""Elpris API client for Swedish electricity spot prices.

Fetches spot prices from elprisetjustnu.se — an open API with no
authentication required.

Price zones: SE1 (Luleå), SE2 (Sundsvall), SE3 (Stockholm), SE4 (Malmö).
Data: SEK_per_kWh, EUR_per_kWh, EXR, time_start, time_end.
Prices exclude VAT and surcharges.
Historical data available from 2022-11-01.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

ELPRIS_BASE_URL = os.getenv(
    "ELPRIS_BASE_URL",
    "https://www.elprisetjustnu.se/api/v1/prices",
)
ELPRIS_DEFAULT_TIMEOUT = float(os.getenv("ELPRIS_TIMEOUT", "10.0"))
ELPRIS_CACHE_TTL_TODAY = int(os.getenv("ELPRIS_CACHE_TTL_TODAY", "900"))  # 15 min
ELPRIS_CACHE_TTL_HISTORY = int(os.getenv("ELPRIS_CACHE_TTL_HISTORY", "86400"))  # 24h

ELPRIS_SOURCE = "elprisetjustnu.se"

VALID_ZONES = {"SE1", "SE2", "SE3", "SE4"}
ZONE_NAMES = {
    "SE1": "Luleå",
    "SE2": "Sundsvall",
    "SE3": "Stockholm",
    "SE4": "Malmö",
}


class ElprisService:
    """Async client for elprisetjustnu.se spot price API."""

    def __init__(
        self,
        *,
        base_url: str = ELPRIS_BASE_URL,
        timeout: float = ELPRIS_DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._cache_lock = asyncio.Lock()
        self._today_cache: TTLCache[str, list[dict[str, Any]]] = TTLCache(
            maxsize=50, ttl=ELPRIS_CACHE_TTL_TODAY,
        )
        self._history_cache: TTLCache[str, list[dict[str, Any]]] = TTLCache(
            maxsize=500, ttl=ELPRIS_CACHE_TTL_HISTORY,
        )

    # -- Lifecycle -----------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # -- Internal ------------------------------------------------------------

    @staticmethod
    def _validate_zone(zone: str) -> str:
        z = zone.upper().strip()
        if z not in VALID_ZONES:
            raise ValueError(f"Invalid zone '{zone}'. Valid zones: {', '.join(sorted(VALID_ZONES))}")
        return z

    def _build_url(self, date_str: str, zone: str) -> str:
        """Build URL: /prices/{YYYY}/{MM-DD}_{ZONE}.json"""
        # date_str should be YYYY-MM-DD
        parts = date_str.split("-")
        if len(parts) != 3:
            raise ValueError(f"Invalid date format '{date_str}', expected YYYY-MM-DD")
        year = parts[0]
        month_day = f"{parts[1]}-{parts[2]}"
        return f"{self._base_url}/{year}/{month_day}_{zone}.json"

    async def _fetch_prices(self, date_str: str, zone: str) -> list[dict[str, Any]]:
        zone = self._validate_zone(zone)
        cache_key = f"{date_str}:{zone}"

        # Check if today
        today = datetime.now().strftime("%Y-%m-%d")
        is_today = date_str == today
        cache = self._today_cache if is_today else self._history_cache

        async with self._cache_lock:
            if cache_key in cache:
                return list(cache[cache_key])

        url = self._build_url(date_str, zone)
        client = self._get_client()
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            return []

        async with self._cache_lock:
            cache[cache_key] = data
        return list(data)

    @staticmethod
    def _aggregate(prices: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute min/max/average from a list of price entries."""
        if not prices:
            return {"min": None, "max": None, "average": None, "count": 0}
        sek_values = [p["SEK_per_kWh"] for p in prices if "SEK_per_kWh" in p]
        if not sek_values:
            return {"min": None, "max": None, "average": None, "count": 0}
        return {
            "min_sek_per_kwh": round(min(sek_values), 4),
            "max_sek_per_kwh": round(max(sek_values), 4),
            "average_sek_per_kwh": round(sum(sek_values) / len(sek_values), 4),
            "count": len(sek_values),
        }

    # =========================================================================
    # Public API
    # =========================================================================

    async def get_prices(self, date: str, zone: str) -> list[dict[str, Any]]:
        """Spot prices for a specific date and zone."""
        return await self._fetch_prices(date, zone)

    async def get_today_prices(self, zone: str) -> list[dict[str, Any]]:
        """Today's spot prices."""
        today = datetime.now().strftime("%Y-%m-%d")
        return await self._fetch_prices(today, zone)

    async def get_tomorrow_prices(self, zone: str) -> list[dict[str, Any]]:
        """Tomorrow's prices (available after ~13:00)."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        return await self._fetch_prices(tomorrow, zone)

    async def get_average_price(self, date: str, zone: str) -> dict[str, Any]:
        """Aggregated stats (min/max/avg) for a date and zone."""
        prices = await self._fetch_prices(date, zone)
        stats = self._aggregate(prices)
        return {
            "date": date,
            "zone": zone,
            "zone_name": ZONE_NAMES.get(zone.upper(), zone),
            **stats,
        }

    async def get_price_comparison(self, date: str) -> dict[str, Any]:
        """Compare prices across all 4 zones for a date."""
        results = await asyncio.gather(
            *[self._fetch_prices(date, zone) for zone in sorted(VALID_ZONES)],
            return_exceptions=True,
        )
        comparison: dict[str, Any] = {"date": date, "zones": {}}
        for zone, result in zip(sorted(VALID_ZONES), results, strict=False):
            if isinstance(result, Exception):
                comparison["zones"][zone] = {
                    "zone_name": ZONE_NAMES.get(zone, zone),
                    "error": str(result),
                }
            else:
                stats = self._aggregate(result)
                comparison["zones"][zone] = {
                    "zone_name": ZONE_NAMES.get(zone, zone),
                    **stats,
                }
        return comparison

    async def get_prices_range(
        self, start: str, end: str, zone: str
    ) -> list[dict[str, Any]]:
        """Fetch prices for a date range (inclusive). Max 31 days."""
        zone = self._validate_zone(zone)
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        if (end_dt - start_dt).days > 31:
            raise ValueError("Date range cannot exceed 31 days")

        all_prices: list[dict[str, Any]] = []
        current = start_dt
        while current <= end_dt:
            date_str = current.strftime("%Y-%m-%d")
            try:
                prices = await self._fetch_prices(date_str, zone)
                all_prices.extend(prices)
            except httpx.HTTPStatusError:
                logger.warning("No price data for %s zone %s", date_str, zone)
            current += timedelta(days=1)
        return all_prices
