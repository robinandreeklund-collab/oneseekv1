"""Riksbank API client for interest rates, exchange rates, SWESTR, and forecasts.

Provides access to three Riksbank REST APIs:
- **SWEA** — Interest rates (~60 series) and exchange rates (~50 series)
- **SWESTR** — Swedish overnight reference rate
- **Forecasts** — Macroeconomic forecasts and outcomes (from 2020)

Authentication is optional. Without an API key: 5 requests/min, 1000/day.
With key (Ocp-Apim-Subscription-Key header): 200 requests/min, 30 000/week.

Source: Sveriges Riksbank — https://developer.api.riksbank.se/
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults — overridable via env vars
# ---------------------------------------------------------------------------

RIKSBANK_SWEA_BASE_URL = os.getenv(
    "RIKSBANK_SWEA_BASE_URL",
    "https://api.riksbank.se/swea/v1",
)
RIKSBANK_SWESTR_BASE_URL = os.getenv(
    "RIKSBANK_SWESTR_BASE_URL",
    "https://api.riksbank.se/swestr/v1",
)
RIKSBANK_FORECASTS_BASE_URL = os.getenv(
    "RIKSBANK_FORECASTS_BASE_URL",
    "https://api.riksbank.se/forecasts/v1",
)
RIKSBANK_API_KEY = os.getenv("RIKSBANK_API_KEY", "")
RIKSBANK_DEFAULT_TIMEOUT = float(os.getenv("RIKSBANK_TIMEOUT", "15.0"))
RIKSBANK_CACHE_TTL_RATES = int(os.getenv("RIKSBANK_CACHE_TTL_RATES", "3600"))
RIKSBANK_CACHE_TTL_META = int(os.getenv("RIKSBANK_CACHE_TTL_META", "86400"))

RIKSBANK_SOURCE = "Riksbanken (api.riksbank.se)"

# Well-known series IDs for convenience
SERIES_POLICY_RATE = "SECBREPOEFF"
SERIES_DEPOSIT_RATE = "SECBDEPOEFF"
SERIES_LENDING_RATE = "SECBLENDEFF"
SERIES_REFERENCE_RATE = "SECBREFEFF"

GROUP_EXCHANGE_RATES_SEK = "130"
GROUP_KEY_RATES = "2"
GROUP_STIBOR = "3"


class RiksbankService:
    """Async client for the Riksbank REST APIs (SWEA, SWESTR, Forecasts)."""

    def __init__(
        self,
        *,
        swea_base_url: str = RIKSBANK_SWEA_BASE_URL,
        swestr_base_url: str = RIKSBANK_SWESTR_BASE_URL,
        forecasts_base_url: str = RIKSBANK_FORECASTS_BASE_URL,
        api_key: str = RIKSBANK_API_KEY,
        timeout: float = RIKSBANK_DEFAULT_TIMEOUT,
    ) -> None:
        self._swea_url = swea_base_url.rstrip("/")
        self._swestr_url = swestr_base_url.rstrip("/")
        self._forecasts_url = forecasts_base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

        # Caches
        self._cache_lock = asyncio.Lock()
        self._rate_cache: TTLCache[str, Any] = TTLCache(
            maxsize=500, ttl=RIKSBANK_CACHE_TTL_RATES,
        )
        self._meta_cache: TTLCache[str, Any] = TTLCache(
            maxsize=200, ttl=RIKSBANK_CACHE_TTL_META,
        )

        from app.services.cache_control import register_service_cache

        register_service_cache(self._rate_cache)
        register_service_cache(self._meta_cache)

    # -- Lifecycle -----------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["Ocp-Apim-Subscription-Key"] = self._api_key
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=headers,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # -- Low-level HTTP ------------------------------------------------------

    async def _get_json(self, url: str) -> Any:
        client = self._get_client()
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def _cached_get(
        self, cache_key: str, url: str, *, use_meta_cache: bool = False
    ) -> tuple[Any, bool]:
        cache = self._meta_cache if use_meta_cache else self._rate_cache
        async with self._cache_lock:
            if cache_key in cache:
                return cache[cache_key], True
        data = await self._get_json(url)
        async with self._cache_lock:
            cache[cache_key] = data
        return data, False

    # =========================================================================
    # SWEA API — Interest rates & Exchange rates
    # =========================================================================

    async def list_groups(self) -> tuple[Any, bool]:
        """Hierarchical tree of all series groups."""
        url = f"{self._swea_url}/Groups"
        return await self._cached_get("swea:groups", url, use_meta_cache=True)

    async def list_series(self) -> tuple[Any, bool]:
        """All available data series with metadata."""
        url = f"{self._swea_url}/Series"
        return await self._cached_get("swea:series", url, use_meta_cache=True)

    async def get_latest_observation(self, series_id: str) -> tuple[dict[str, Any], bool]:
        """Latest published observation for a single series."""
        url = f"{self._swea_url}/Observations/Latest/{series_id}"
        return await self._cached_get(f"swea:latest:{series_id}", url)

    async def get_latest_by_group(self, group_id: str) -> tuple[Any, bool]:
        """Latest observation for every series in a group."""
        url = f"{self._swea_url}/Observations/Latest/ByGroup/{group_id}"
        return await self._cached_get(f"swea:group:{group_id}", url)

    async def get_observations(
        self, series_id: str, from_date: str, to_date: str
    ) -> tuple[Any, bool]:
        """Observations within a date range. Dates as YYYY-MM-DD."""
        url = f"{self._swea_url}/Observations/{series_id}/{from_date}/{to_date}"
        cache_key = f"swea:obs:{series_id}:{from_date}:{to_date}"
        return await self._cached_get(cache_key, url)

    async def get_cross_rates(
        self, series1: str, series2: str, date: str
    ) -> tuple[Any, bool]:
        """Cross rate between two currency series on a given date."""
        url = f"{self._swea_url}/CrossRates/{series1}/{series2}/{date}"
        cache_key = f"swea:cross:{series1}:{series2}:{date}"
        return await self._cached_get(cache_key, url)

    # =========================================================================
    # SWESTR API — Swedish overnight reference rate
    # =========================================================================

    async def get_swestr_latest(self) -> tuple[Any, bool]:
        """Latest SWESTR observation."""
        url = f"{self._swestr_url}/latest/SWESTR"
        return await self._cached_get("swestr:latest", url)

    async def get_swestr_observations(
        self, from_date: str, to_date: str | None = None
    ) -> tuple[Any, bool]:
        """SWESTR observations in date range."""
        url = f"{self._swestr_url}/all/SWESTR?fromDate={from_date}"
        if to_date:
            url += f"&toDate={to_date}"
        cache_key = f"swestr:obs:{from_date}:{to_date or 'now'}"
        return await self._cached_get(cache_key, url)

    # =========================================================================
    # Forecasts API — Macroeconomic forecasts & outcomes
    # =========================================================================

    async def get_forecasts(
        self, indicator: str | None = None
    ) -> tuple[Any, bool]:
        """Forecasts and outcomes. Optional indicator filter."""
        url = f"{self._forecasts_url}/forecasts"
        if indicator:
            url += f"?indicator={indicator}"
        cache_key = f"forecast:{indicator or 'all'}"
        return await self._cached_get(cache_key, url)

    async def get_forecast_indicators(self) -> tuple[Any, bool]:
        """List available forecast indicators."""
        url = f"{self._forecasts_url}/indicators"
        return await self._cached_get("forecast:indicators", url, use_meta_cache=True)

    # =========================================================================
    # Convenience: Policy rate
    # =========================================================================

    async def get_policy_rate(self) -> tuple[dict[str, Any], bool]:
        """Current policy rate (styrränta)."""
        return await self.get_latest_observation(SERIES_POLICY_RATE)

    async def get_policy_rate_history(
        self, from_date: str, to_date: str
    ) -> tuple[Any, bool]:
        """Policy rate history within date range."""
        return await self.get_observations(SERIES_POLICY_RATE, from_date, to_date)
