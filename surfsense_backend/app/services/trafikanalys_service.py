"""Trafikanalys API client for Swedish transport statistics.

Provides access to Trafikanalys (trafa.se) REST API for transport statistics
covering road vehicles, traffic volumes, rail, maritime, aviation, and more.

The API uses a pipe-separated query format:
    query=PRODUCT|MEASURE|DIMENSION:filter1,filter2|...

Two endpoints:
- **Structure** — metadata about products, dimensions, measures
- **Data** — actual statistical observations

Authentication: None required. No API key needed.
Rate limits: Not formally specified; caching strongly recommended.

Source: Trafikanalys — https://www.trafa.se/sidor/oppen-data-api/
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

TRAFIKANALYS_BASE_URL = os.getenv(
    "TRAFIKANALYS_BASE_URL",
    "https://api.trafa.se/api",
)
TRAFIKANALYS_DEFAULT_TIMEOUT = float(os.getenv("TRAFIKANALYS_TIMEOUT", "20.0"))
TRAFIKANALYS_CACHE_TTL_DATA = int(os.getenv("TRAFIKANALYS_CACHE_TTL_DATA", "3600"))
TRAFIKANALYS_CACHE_TTL_META = int(os.getenv("TRAFIKANALYS_CACHE_TTL_META", "86400"))

TRAFIKANALYS_SOURCE = "Trafikanalys (api.trafa.se)"

# ---------------------------------------------------------------------------
# Well-known product codes
# ---------------------------------------------------------------------------

# Vägtrafik (Road traffic)
PRODUCT_PERSONBILAR = "t10016"
PRODUCT_LASTBILAR = "t10013"
PRODUCT_BUSSAR = "t10011"
PRODUCT_MOTORCYKLAR = "t10014"
PRODUCT_MOPEDER = "t10015"
PRODUCT_SLAPVAGNAR = "t10017"
PRODUCT_TRAKTORER = "t10018"
PRODUCT_TERRANGSKOTRAR = "t10019"
PRODUCT_FORDON_PA_VAG = "t10010"
PRODUCT_NYREGISTRERINGAR = "t10030"
PRODUCT_KORKORT = "t10012"
PRODUCT_TRAFIKARBETE = "t0401"
PRODUCT_TRANSPORTARBETE_VAG = "t04021"
PRODUCT_VAGTRAFIK_SKADOR = "t1004"
PRODUCT_LASTBILSTRAFIK_AR = "t10061"
PRODUCT_LASTBILSTRAFIK_KVARTAL = "t10062"

# Luftfart (Aviation)
PRODUCT_LUFTFART = "t0501"

# Sjöfart (Maritime)
PRODUCT_SJOTRAFIK = "t0802"
PRODUCT_SJOTRAFIK_KVARTAL = "t08021"
PRODUCT_FARTYG = "t0808"

# Järnväg (Railway)
PRODUCT_JARNVAG_TRANSPORT = "t0603"
PRODUCT_BANTRAFIK_SKADOR = "t0602"
PRODUCT_PUNKTLIGHET_STM = "t0604"

# Kollektivtrafik (Public transport)
PRODUCT_FARDTJANST = "t1201"
PRODUCT_LINJETRAFIK_VAG = "t1202"
PRODUCT_REGIONAL_LINJETRAFIK = "t1203"
PRODUCT_LINJETRAFIK_VATTEN = "t1204"

# Övrigt
PRODUCT_VARUFLODEN = "t1102"
PRODUCT_RVU = "t1101"
PRODUCT_UTLANDSKA_LASTBILAR = "t0301"
PRODUCT_POSTVERKSAMHET = "t0701"

# Common measures
MEASURE_I_TRAFIK = "itrfslut"
MEASURE_AVSTÄLLDA = "avstslut"
MEASURE_NYREGISTRERINGAR = "nyregunder"
MEASURE_AVREGISTRERINGAR = "avregunder"

# Common dimensions
DIMENSION_AR = "ar"
DIMENSION_DRIVMEDEL = "drivm"
DIMENSION_AGARKATEGORI = "agarkat"
DIMENSION_KON = "kon"


class TrafikanalysService:
    """Async client for the Trafikanalys REST API (structure + data)."""

    def __init__(
        self,
        *,
        base_url: str = TRAFIKANALYS_BASE_URL,
        timeout: float = TRAFIKANALYS_DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

        # Caches
        self._cache_lock = asyncio.Lock()
        self._data_cache: TTLCache[str, Any] = TTLCache(
            maxsize=500,
            ttl=TRAFIKANALYS_CACHE_TTL_DATA,
        )
        self._meta_cache: TTLCache[str, Any] = TTLCache(
            maxsize=200,
            ttl=TRAFIKANALYS_CACHE_TTL_META,
        )

    # -- Lifecycle -----------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
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
        cache = self._meta_cache if use_meta_cache else self._data_cache
        async with self._cache_lock:
            if cache_key in cache:
                return cache[cache_key], True
        data = await self._get_json(url)
        async with self._cache_lock:
            cache[cache_key] = data
        return data, False

    # -- Query builder -------------------------------------------------------

    @staticmethod
    def build_query(
        product: str,
        *parts: str,
    ) -> str:
        """Build a pipe-separated query string.

        Example::

            build_query("t10016", "itrfslut", "ar:2024")
            # => "t10016|itrfslut|ar:2024"

            build_query("t10016", "itrfslut", "ar:2023,2024", "drivm")
            # => "t10016|itrfslut|ar:2023,2024|drivm"
        """
        segments = [product] + [p for p in parts if p]
        return "|".join(segments)

    # =========================================================================
    # Structure API — metadata about products, dimensions, measures
    # =========================================================================

    async def list_products(self, *, lang: str = "sv") -> tuple[Any, bool]:
        """List all available statistical products."""
        url = f"{self._base_url}/structure?lang={lang}"
        return await self._cached_get("structure:products", url, use_meta_cache=True)

    async def get_structure(self, query: str, *, lang: str = "sv") -> tuple[Any, bool]:
        """Get structure (dimensions, measures) for a query.

        Args:
            query: Pipe-separated query, e.g. "t10016" or "t10016|itrfslut|ar"
            lang: Language code ("sv" or "en")
        """
        url = f"{self._base_url}/structure?query={query}&lang={lang}"
        cache_key = f"structure:{query}:{lang}"
        return await self._cached_get(cache_key, url, use_meta_cache=True)

    # =========================================================================
    # Data API — actual statistical observations
    # =========================================================================

    async def get_data(self, query: str, *, lang: str = "sv") -> tuple[Any, bool]:
        """Fetch statistical data for a query.

        Args:
            query: Pipe-separated query, e.g. "t10016|itrfslut|ar:2024"
            lang: Language code ("sv" or "en")

        Returns:
            Tuple of (response_data, cached_flag)
        """
        url = f"{self._base_url}/data?query={query}&lang={lang}"
        cache_key = f"data:{query}:{lang}"
        return await self._cached_get(cache_key, url)

    # =========================================================================
    # Convenience: Fordon (Vehicles)
    # =========================================================================

    async def get_vehicles_in_traffic(
        self,
        product: str = PRODUCT_PERSONBILAR,
        *,
        years: str = "senaste",
        breakdown: str = "",
    ) -> tuple[Any, bool]:
        """Get number of vehicles in traffic.

        Args:
            product: Product code (e.g. t10016 for passenger cars)
            years: Comma-separated years or "senaste" for latest
            breakdown: Optional dimension for breakdown (e.g. "drivm" for fuel type)
        """
        parts = [MEASURE_I_TRAFIK, f"{DIMENSION_AR}:{years}"]
        if breakdown:
            parts.append(breakdown)
        query = self.build_query(product, *parts)
        return await self.get_data(query)

    async def get_new_registrations(
        self,
        product: str = PRODUCT_PERSONBILAR,
        *,
        years: str = "senaste",
        breakdown: str = "",
    ) -> tuple[Any, bool]:
        """Get new vehicle registrations.

        Args:
            product: Product code (e.g. t10016 for passenger cars)
            years: Comma-separated years or "senaste" for latest
            breakdown: Optional dimension for breakdown
        """
        parts = [MEASURE_NYREGISTRERINGAR, f"{DIMENSION_AR}:{years}"]
        if breakdown:
            parts.append(breakdown)
        query = self.build_query(product, *parts)
        return await self.get_data(query)

    async def get_deregistrations(
        self,
        product: str = PRODUCT_PERSONBILAR,
        *,
        years: str = "senaste",
    ) -> tuple[Any, bool]:
        """Get vehicle deregistrations."""
        query = self.build_query(
            product, MEASURE_AVREGISTRERINGAR, f"{DIMENSION_AR}:{years}"
        )
        return await self.get_data(query)

    async def get_traffic_volume(
        self,
        *,
        years: str = "senaste",
    ) -> tuple[Any, bool]:
        """Get traffic volume (trafikarbete) in vehicle-kilometers."""
        query = self.build_query(
            PRODUCT_TRAFIKARBETE, "fordonkm", f"{DIMENSION_AR}:{years}"
        )
        return await self.get_data(query)

    # =========================================================================
    # Convenience: Körkort (Driving licenses)
    # =========================================================================

    async def get_driving_licenses(
        self,
        *,
        years: str = "senaste",
        breakdown: str = "",
    ) -> tuple[Any, bool]:
        """Get driving license statistics."""
        parts = [f"{DIMENSION_AR}:{years}"]
        if breakdown:
            parts.append(breakdown)
        query = self.build_query(PRODUCT_KORKORT, *parts)
        return await self.get_data(query)

    # =========================================================================
    # Convenience: Vägtrafikskador (Road traffic injuries)
    # =========================================================================

    async def get_traffic_injuries(
        self,
        *,
        years: str = "senaste",
    ) -> tuple[Any, bool]:
        """Get road traffic injury statistics."""
        query = self.build_query(PRODUCT_VAGTRAFIK_SKADOR, f"{DIMENSION_AR}:{years}")
        return await self.get_data(query)

    # =========================================================================
    # Convenience: Sjöfart (Maritime)
    # =========================================================================

    async def get_maritime_traffic(
        self,
        *,
        years: str = "senaste",
    ) -> tuple[Any, bool]:
        """Get maritime traffic statistics."""
        query = self.build_query(PRODUCT_SJOTRAFIK, f"{DIMENSION_AR}:{years}")
        return await self.get_data(query)

    # =========================================================================
    # Convenience: Luftfart (Aviation)
    # =========================================================================

    async def get_aviation_statistics(
        self,
        *,
        years: str = "senaste",
    ) -> tuple[Any, bool]:
        """Get aviation statistics."""
        query = self.build_query(PRODUCT_LUFTFART, f"{DIMENSION_AR}:{years}")
        return await self.get_data(query)

    # =========================================================================
    # Convenience: Järnväg (Railway)
    # =========================================================================

    async def get_railway_transport(
        self,
        *,
        years: str = "senaste",
    ) -> tuple[Any, bool]:
        """Get railway transport statistics."""
        query = self.build_query(PRODUCT_JARNVAG_TRANSPORT, f"{DIMENSION_AR}:{years}")
        return await self.get_data(query)

    async def get_railway_injuries(
        self,
        *,
        years: str = "senaste",
    ) -> tuple[Any, bool]:
        """Get railway accident/injury statistics."""
        query = self.build_query(PRODUCT_BANTRAFIK_SKADOR, f"{DIMENSION_AR}:{years}")
        return await self.get_data(query)

    # =========================================================================
    # Convenience: Kollektivtrafik (Public transport)
    # =========================================================================

    async def get_public_transport(
        self,
        *,
        years: str = "senaste",
    ) -> tuple[Any, bool]:
        """Get regional public transport statistics."""
        query = self.build_query(
            PRODUCT_REGIONAL_LINJETRAFIK, f"{DIMENSION_AR}:{years}"
        )
        return await self.get_data(query)
