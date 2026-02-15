from __future__ import annotations

import asyncio
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, UTC
from time import monotonic
from typing import Any

import httpx

BLOCKET_BASE_URL = "https://api.blocket.se/search_bff/v2/content"
TRADERA_API_BASE = "https://api.tradera.com"


class SimpleCache:
    """Simple TTL-based in-memory cache."""

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired."""
        if key in self._cache:
            expires_at, value = self._cache[key]
            if monotonic() < expires_at:
                return value
            # Expired, remove
            del self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with TTL."""
        expires_at = monotonic() + self.ttl_seconds
        self._cache[key] = (expires_at, value)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()


class RateLimiter:
    """Rate limiter for API calls."""

    def __init__(self, max_requests_per_second: float):
        self.max_requests_per_second = max_requests_per_second
        self.min_interval = 1.0 / max_requests_per_second
        self.last_request_time: float = 0.0

    async def acquire(self) -> None:
        """Wait if necessary to respect rate limit."""
        now = monotonic()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_interval:
            wait_time = self.min_interval - time_since_last
            await asyncio.sleep(wait_time)
        self.last_request_time = monotonic()


class TraderaBudget:
    """Track and enforce Tradera API budget (100 calls per 24h)."""

    def __init__(self, max_calls: int = 100):
        self.max_calls = max_calls
        self.calls_made = 0
        self.reset_time = self._next_midnight_utc()

    def _next_midnight_utc(self) -> datetime:
        """Calculate next midnight UTC."""
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)

    def _check_and_reset(self) -> None:
        """Check if reset time has passed and reset if necessary."""
        now = datetime.now(UTC)
        if now >= self.reset_time:
            self.calls_made = 0
            self.reset_time = self._next_midnight_utc()

    def can_make_call(self) -> bool:
        """Check if we can make another API call."""
        self._check_and_reset()
        return self.calls_made < self.max_calls

    def record_call(self) -> None:
        """Record that an API call was made."""
        self._check_and_reset()
        self.calls_made += 1

    def get_remaining_calls(self) -> int:
        """Get number of remaining calls."""
        self._check_and_reset()
        return max(0, self.max_calls - self.calls_made)


class BlocketTraderaService:
    """Service for interacting with Blocket and Tradera APIs."""

    def __init__(self):
        self.blocket_cache = SimpleCache(ttl_seconds=600)  # 10 minutes
        self.tradera_cache = SimpleCache(ttl_seconds=1800)  # 30 minutes
        self.blocket_rate_limiter = RateLimiter(max_requests_per_second=5.0)
        self.tradera_budget = TraderaBudget(max_calls=100)
        self.tradera_app_id = os.getenv("TRADERA_APP_ID", "5572")
        self.tradera_app_key = os.getenv("TRADERA_APP_KEY", "")

    async def blocket_search(
        self,
        query: str,
        category: str | None = None,
        location: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search Blocket for general items.

        Args:
            query: Search query
            category: Optional category filter
            location: Optional location filter
            min_price: Minimum price
            max_price: Maximum price
            limit: Max number of results (default 20)

        Returns:
            Normalized search results
        """
        cache_key = f"blocket:search:{query}:{category}:{location}:{min_price}:{max_price}:{limit}"
        cached = self.blocket_cache.get(cache_key)
        if cached:
            return cached

        await self.blocket_rate_limiter.acquire()

        params: dict[str, Any] = {"q": query, "limit": limit}
        if category:
            params["category"] = category
        if location:
            params["location"] = location
        if min_price is not None:
            params["price_from"] = min_price
        if max_price is not None:
            params["price_to"] = max_price

        async with httpx.AsyncClient() as client:
            response = await client.get(BLOCKET_BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()

        normalized = self._normalize_blocket_response(data)
        self.blocket_cache.set(cache_key, normalized)
        return normalized

    async def blocket_search_cars(
        self,
        query: str | None = None,
        make: str | None = None,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        location: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search Blocket for cars.

        Args:
            query: Search query
            make: Car make/brand
            model: Car model
            year_from: Minimum year
            year_to: Maximum year
            location: Location filter
            limit: Max results

        Returns:
            Normalized car search results
        """
        search_query = query or ""
        if make:
            search_query = f"{search_query} {make}".strip()
        if model:
            search_query = f"{search_query} {model}".strip()

        cache_key = f"blocket:cars:{search_query}:{year_from}:{year_to}:{location}:{limit}"
        cached = self.blocket_cache.get(cache_key)
        if cached:
            return cached

        await self.blocket_rate_limiter.acquire()

        params: dict[str, Any] = {"category": "bilar", "limit": limit}
        if search_query:
            params["q"] = search_query
        if year_from:
            params["year_from"] = year_from
        if year_to:
            params["year_to"] = year_to
        if location:
            params["location"] = location

        async with httpx.AsyncClient() as client:
            response = await client.get(BLOCKET_BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()

        normalized = self._normalize_blocket_response(data)
        self.blocket_cache.set(cache_key, normalized)
        return normalized

    async def blocket_search_boats(
        self,
        query: str | None = None,
        boat_type: str | None = None,
        location: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search Blocket for boats.

        Args:
            query: Search query
            boat_type: Type of boat
            location: Location filter
            min_price: Minimum price
            max_price: Maximum price
            limit: Max results

        Returns:
            Normalized boat search results
        """
        search_query = query or ""
        if boat_type:
            search_query = f"{search_query} {boat_type}".strip()

        cache_key = f"blocket:boats:{search_query}:{location}:{min_price}:{max_price}:{limit}"
        cached = self.blocket_cache.get(cache_key)
        if cached:
            return cached

        await self.blocket_rate_limiter.acquire()

        params: dict[str, Any] = {"category": "batar", "limit": limit}
        if search_query:
            params["q"] = search_query
        if location:
            params["location"] = location
        if min_price is not None:
            params["price_from"] = min_price
        if max_price is not None:
            params["price_to"] = max_price

        async with httpx.AsyncClient() as client:
            response = await client.get(BLOCKET_BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()

        normalized = self._normalize_blocket_response(data)
        self.blocket_cache.set(cache_key, normalized)
        return normalized

    async def blocket_search_mc(
        self,
        query: str | None = None,
        make: str | None = None,
        location: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search Blocket for motorcycles.

        Args:
            query: Search query
            make: Motorcycle make
            location: Location filter
            min_price: Minimum price
            max_price: Maximum price
            limit: Max results

        Returns:
            Normalized MC search results
        """
        search_query = query or ""
        if make:
            search_query = f"{search_query} {make}".strip()

        cache_key = f"blocket:mc:{search_query}:{location}:{min_price}:{max_price}:{limit}"
        cached = self.blocket_cache.get(cache_key)
        if cached:
            return cached

        await self.blocket_rate_limiter.acquire()

        params: dict[str, Any] = {"category": "mc", "limit": limit}
        if search_query:
            params["q"] = search_query
        if location:
            params["location"] = location
        if min_price is not None:
            params["price_from"] = min_price
        if max_price is not None:
            params["price_to"] = max_price

        async with httpx.AsyncClient() as client:
            response = await client.get(BLOCKET_BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()

        normalized = self._normalize_blocket_response(data)
        self.blocket_cache.set(cache_key, normalized)
        return normalized

    async def tradera_search(
        self,
        query: str,
        category_id: int | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search Tradera using their SOAP API.

        Args:
            query: Search query
            category_id: Optional category ID
            min_price: Minimum price
            max_price: Maximum price
            limit: Max results

        Returns:
            Parsed search results from XML
        """
        if not self.tradera_budget.can_make_call():
            return {
                "error": "Tradera API budget exceeded",
                "remaining_calls": 0,
                "reset_time": self.tradera_budget.reset_time.isoformat(),
            }

        cache_key = f"tradera:search:{query}:{category_id}:{min_price}:{max_price}:{limit}"
        cached = self.tradera_cache.get(cache_key)
        if cached:
            return cached

        # Build SOAP request
        soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <Search xmlns="http://api.tradera.com">
      <appId>{self.tradera_app_id}</appId>
      <appKey>{self.tradera_app_key}</appKey>
      <query>{query}</query>
      <maxResults>{limit}</maxResults>
    </Search>
  </soap:Body>
</soap:Envelope>"""

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "http://api.tradera.com/Search"}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TRADERA_API_BASE}/v3/searchservice.asmx", content=soap_body, headers=headers, timeout=30.0
            )
            response.raise_for_status()

        self.tradera_budget.record_call()
        parsed = self._parse_tradera_search_xml(response.text)
        self.tradera_cache.set(cache_key, parsed)
        return parsed

    def _normalize_blocket_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize Blocket API response to consistent format.

        Args:
            data: Raw API response

        Returns:
            Normalized data structure
        """
        items = []
        raw_items = data.get("data", [])

        for item in raw_items:
            normalized_item = {
                "id": item.get("id"),
                "title": item.get("subject"),
                "price": item.get("price", {}).get("value"),
                "currency": item.get("price", {}).get("currency", "SEK"),
                "location": item.get("location", {}).get("name"),
                "url": item.get("share_url"),
                "image": item.get("image", {}).get("url") if item.get("image") else None,
                "published": item.get("date"),
                "category": item.get("category"),
            }
            items.append(normalized_item)

        return {"source": "Blocket", "total": len(items), "items": items}

    def _parse_tradera_search_xml(self, xml_text: str) -> dict[str, Any]:
        """
        Parse Tradera SOAP XML response.

        Args:
            xml_text: XML response text

        Returns:
            Parsed results as dict
        """
        try:
            root = ET.fromstring(xml_text)
            # Define namespaces
            namespaces = {
                "soap": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns": "http://api.tradera.com",
            }

            # Navigate to search results
            body = root.find("soap:Body", namespaces)
            if body is None:
                return {"source": "Tradera", "error": "Invalid XML structure", "items": []}

            search_response = body.find("ns:SearchResponse", namespaces)
            if search_response is None:
                return {"source": "Tradera", "error": "No search response", "items": []}

            search_result = search_response.find("ns:SearchResult", namespaces)
            if search_result is None:
                return {"source": "Tradera", "items": []}

            items_node = search_result.find("ns:Items", namespaces)
            items = []

            if items_node is not None:
                for item_node in items_node.findall("ns:Item", namespaces):
                    item = {
                        "id": self._get_xml_text(item_node, "ns:Id", namespaces),
                        "title": self._get_xml_text(item_node, "ns:ShortDescription", namespaces),
                        "price": self._get_xml_text(item_node, "ns:NextBid", namespaces),
                        "currency": "SEK",
                        "url": self._get_xml_text(item_node, "ns:ItemUrl", namespaces),
                        "image": self._get_xml_text(item_node, "ns:ThumbnailLink", namespaces),
                        "end_date": self._get_xml_text(item_node, "ns:EndDate", namespaces),
                        "bid_count": self._get_xml_text(item_node, "ns:BidCount", namespaces),
                    }
                    items.append(item)

            return {
                "source": "Tradera",
                "total": len(items),
                "items": items,
                "remaining_budget": self.tradera_budget.get_remaining_calls(),
            }

        except ET.ParseError as e:
            return {"source": "Tradera", "error": f"XML parse error: {e!s}", "items": []}

    def _get_xml_text(self, node: ET.Element, path: str, namespaces: dict[str, str]) -> str | None:
        """Helper to safely extract text from XML node."""
        element = node.find(path, namespaces)
        return element.text if element is not None else None
