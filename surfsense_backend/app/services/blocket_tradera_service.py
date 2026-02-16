from __future__ import annotations

import asyncio
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, UTC
from time import monotonic
from typing import Any

import httpx

BLOCKET_API_BASE = os.getenv("BLOCKET_API_BASE_URL", "https://blocket-api.se").rstrip("/")
BLOCKET_SEARCH_URL = f"{BLOCKET_API_BASE}/v1/search"
BLOCKET_CAR_SEARCH_URL = f"{BLOCKET_API_BASE}/v1/search/car"
BLOCKET_BOAT_SEARCH_URL = f"{BLOCKET_API_BASE}/v1/search/boat"
BLOCKET_MC_SEARCH_URL = f"{BLOCKET_API_BASE}/v1/search/mc"
TRADERA_API_BASE = "https://api.tradera.com"

_BLOCKET_CATEGORY_ALIAS_MAP: dict[str, str] = {
    "affarsverksamhet": "AFFARSVERKSAMHET",
    "business": "AFFARSVERKSAMHET",
    "djur": "DJUR_OCH_TILLBEHOR",
    "djur och tillbehor": "DJUR_OCH_TILLBEHOR",
    "elektronik": "ELEKTRONIK_OCH_VITVAROR",
    "vitvaror": "ELEKTRONIK_OCH_VITVAROR",
    "fordonstillbehor": "FORDONSTILLBEHOR",
    "fritid": "FRITID_HOBBY_OCH_UNDERHALLNING",
    "hobby": "FRITID_HOBBY_OCH_UNDERHALLNING",
    "underhallning": "FRITID_HOBBY_OCH_UNDERHALLNING",
    "foraldrar och barn": "FORALDRAR_OCH_BARN",
    "barn": "FORALDRAR_OCH_BARN",
    "klader": "KLADER_KOSMETIKA_OCH_ACCESSOARER",
    "mode": "KLADER_KOSMETIKA_OCH_ACCESSOARER",
    "konst": "KONST_OCH_ANTIKT",
    "antik": "KONST_OCH_ANTIKT",
    "mobler": "MOBLER_OCH_INREDNING",
    "inredning": "MOBLER_OCH_INREDNING",
    "sport": "SPORT_OCH_FRITID",
    "tradgard": "TRADGARD_OCH_RENOVERING",
    "renovering": "TRADGARD_OCH_RENOVERING",
}
_BLOCKET_CAR_CATEGORY_ALIASES = {"bil", "bilar", "car", "cars", "fordon"}
_BLOCKET_BOAT_CATEGORY_ALIASES = {"bat", "batar", "boat", "boats"}
_BLOCKET_MC_CATEGORY_ALIASES = {"mc", "motorcykel", "motorcyklar", "moped", "mopeder"}
_BLOCKET_LOCATION_ALIAS_MAP: dict[str, str] = {
    "blekinge": "BLEKINGE",
    "dalarna": "DALARNA",
    "gotland": "GOTLAND",
    "gavleborg": "GAVLEBORG",
    "halland": "HALLAND",
    "jamtland": "JAMTLAND",
    "jonkoping": "JONKOPING",
    "kalmar": "KALMAR",
    "kronoberg": "KRONOBERG",
    "norrbotten": "NORRBOTTEN",
    "skane": "SKANE",
    "stockholm": "STOCKHOLM",
    "sodermanland": "SODERMANLAND",
    "uppsala": "UPPSALA",
    "varmland": "VARMLAND",
    "vasterbotten": "VASTERBOTTEN",
    "vasternorrland": "VASTERNORRLAND",
    "vastmanland": "VASTMANLAND",
    "vastra gotaland": "VASTRA_GOTALAND",
    "orebro": "OREBRO",
    "ostergotland": "OSTERGOTLAND",
    # Common city aliases mapped to county codes.
    "malmo": "SKANE",
    "lund": "SKANE",
    "helsingborg": "SKANE",
    "goteborg": "VASTRA_GOTALAND",
    "linkoping": "OSTERGOTLAND",
    "norrkoping": "OSTERGOTLAND",
    "umea": "VASTERBOTTEN",
    "gavle": "GAVLEBORG",
}


def _normalize_query_token(value: str | None) -> str:
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", str(value))
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


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

    def _resolve_locations_param(self, location: str | None) -> tuple[list[str] | None, str | None]:
        normalized = _normalize_query_token(location)
        if not normalized:
            return None, None
        normalized = re.sub(r"\b(lan|lans)\b", "", normalized).strip()
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return None, None
        direct = _BLOCKET_LOCATION_ALIAS_MAP.get(normalized)
        if direct:
            return [direct], None
        for alias, code in _BLOCKET_LOCATION_ALIAS_MAP.items():
            if (
                normalized == alias
                or normalized.startswith(f"{alias} ")
                or normalized.endswith(f" {alias}")
                or f" {alias} " in f" {normalized} "
            ):
                return [code], None
        return None, str(location).strip()

    def _resolve_general_category(self, category: str | None) -> str | None:
        normalized = _normalize_query_token(category)
        if not normalized:
            return None
        return _BLOCKET_CATEGORY_ALIAS_MAP.get(normalized)

    @staticmethod
    def _append_query_part(query: str | None, part: str | None) -> str:
        left = str(query or "").strip()
        right = str(part or "").strip()
        if left and right:
            return f"{left} {right}".strip()
        return left or right

    async def _blocket_get(self, endpoint: str, *, params: dict[str, Any]) -> dict[str, Any]:
        await self.blocket_rate_limiter.acquire()
        async with httpx.AsyncClient() as client:
            response = await client.get(endpoint, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()

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

        normalized_category = _normalize_query_token(category)
        if normalized_category in _BLOCKET_CAR_CATEGORY_ALIASES:
            normalized = await self.blocket_search_cars(
                query=query,
                location=location,
                limit=limit,
            )
            self.blocket_cache.set(cache_key, normalized)
            return normalized
        if normalized_category in _BLOCKET_BOAT_CATEGORY_ALIASES:
            normalized = await self.blocket_search_boats(
                query=query,
                location=location,
                min_price=min_price,
                max_price=max_price,
                limit=limit,
            )
            self.blocket_cache.set(cache_key, normalized)
            return normalized
        if normalized_category in _BLOCKET_MC_CATEGORY_ALIASES:
            normalized = await self.blocket_search_mc(
                query=query,
                location=location,
                min_price=min_price,
                max_price=max_price,
                limit=limit,
            )
            self.blocket_cache.set(cache_key, normalized)
            return normalized

        params: dict[str, Any] = {"query": query, "page": 1}
        locations, unresolved_location = self._resolve_locations_param(location)
        if locations:
            params["locations"] = locations
        elif unresolved_location:
            params["query"] = self._append_query_part(params.get("query"), unresolved_location)
        mapped_category = self._resolve_general_category(category)
        if mapped_category:
            params["category"] = mapped_category
        if min_price is not None:
            params["price_from"] = min_price
        if max_price is not None:
            params["price_to"] = max_price

        data = await self._blocket_get(BLOCKET_SEARCH_URL, params=params)
        normalized = self._normalize_blocket_response(data, limit=limit)
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

        params: dict[str, Any] = {"page": 1}
        if search_query:
            params["query"] = search_query
        locations, unresolved_location = self._resolve_locations_param(location)
        if locations:
            params["locations"] = locations
        elif unresolved_location:
            params["query"] = self._append_query_part(params.get("query"), unresolved_location)
        if year_from:
            params["year_from"] = year_from
        if year_to:
            params["year_to"] = year_to

        data = await self._blocket_get(BLOCKET_CAR_SEARCH_URL, params=params)
        normalized = self._normalize_blocket_response(data, limit=limit)
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

        params: dict[str, Any] = {"page": 1}
        if search_query:
            params["query"] = search_query
        locations, unresolved_location = self._resolve_locations_param(location)
        if locations:
            params["locations"] = locations
        elif unresolved_location:
            params["query"] = self._append_query_part(params.get("query"), unresolved_location)
        if min_price is not None:
            params["price_from"] = min_price
        if max_price is not None:
            params["price_to"] = max_price

        data = await self._blocket_get(BLOCKET_BOAT_SEARCH_URL, params=params)
        normalized = self._normalize_blocket_response(data, limit=limit)
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

        params: dict[str, Any] = {"page": 1}
        if search_query:
            params["query"] = search_query
        locations, unresolved_location = self._resolve_locations_param(location)
        if locations:
            params["locations"] = locations
        elif unresolved_location:
            params["query"] = self._append_query_part(params.get("query"), unresolved_location)
        if min_price is not None:
            params["price_from"] = min_price
        if max_price is not None:
            params["price_to"] = max_price

        data = await self._blocket_get(BLOCKET_MC_SEARCH_URL, params=params)
        normalized = self._normalize_blocket_response(data, limit=limit)
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

    @staticmethod
    def _parse_blocket_price(raw_price: Any) -> tuple[int | float | None, str]:
        if isinstance(raw_price, dict):
            amount = raw_price.get("amount")
            if amount is None:
                amount = raw_price.get("value")
            currency = (
                raw_price.get("currency_code")
                or raw_price.get("currency")
                or "SEK"
            )
        else:
            amount = raw_price
            currency = "SEK"
        if isinstance(amount, str):
            normalized_amount = amount.replace(" ", "").replace(",", ".")
            try:
                amount = float(normalized_amount)
            except ValueError:
                amount = None
        if isinstance(amount, float) and amount.is_integer():
            amount = int(amount)
        if not isinstance(amount, (int, float)):
            amount = None
        return amount, str(currency or "SEK")

    @staticmethod
    def _timestamp_to_iso(value: Any) -> str | None:
        if not isinstance(value, (int, float)):
            return None
        try:
            epoch = float(value)
            if epoch > 10_000_000_000:
                epoch /= 1000.0
            return datetime.fromtimestamp(epoch, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _extract_blocket_total(data: dict[str, Any], *, fallback: int) -> int:
        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            result_size = metadata.get("result_size")
            if isinstance(result_size, dict):
                for key in ("match_count", "group_count"):
                    value = result_size.get(key)
                    if isinstance(value, int):
                        return value
            num_results = metadata.get("num_results")
            if isinstance(num_results, int):
                return num_results
        total = data.get("total")
        if isinstance(total, int):
            return total
        return fallback

    def _normalize_blocket_response(
        self,
        data: dict[str, Any],
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Normalize Blocket API response to consistent format.

        Supports both legacy Blocket payloads (`data`) and blocket-api.se payloads (`docs`).
        """
        raw_items = data.get("docs")
        if not isinstance(raw_items, list):
            raw_items = data.get("data", [])
        if not isinstance(raw_items, list):
            raw_items = []

        try:
            safe_limit = max(1, int(limit)) if limit is not None else None
        except (TypeError, ValueError):
            safe_limit = None

        normalized_items: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            price, currency = self._parse_blocket_price(item.get("price"))
            location_raw = item.get("location")
            if isinstance(location_raw, dict):
                location_name = (
                    location_raw.get("name")
                    or location_raw.get("postalName")
                    or location_raw.get("value")
                )
            else:
                location_name = location_raw
            image_raw = item.get("image")
            image_url = (
                image_raw.get("url")
                if isinstance(image_raw, dict)
                else None
            )
            if not image_url:
                image_urls = item.get("image_urls")
                if isinstance(image_urls, list) and image_urls:
                    image_url = image_urls[0]
            published = item.get("date") or self._timestamp_to_iso(item.get("timestamp"))
            normalized_items.append(
                {
                    "id": item.get("id") or item.get("ad_id"),
                    "title": item.get("heading") or item.get("subject"),
                    "price": price,
                    "currency": currency,
                    "location": location_name,
                    "url": item.get("canonical_url") or item.get("share_url"),
                    "image": image_url,
                    "published": published,
                    "category": item.get("category") or item.get("boat_class") or item.get("type"),
                    "year": item.get("year"),
                    "mileage": item.get("mileage"),
                    "make": item.get("make"),
                    "model": item.get("model"),
                    "dealer_segment": item.get("dealer_segment"),
                    "type": item.get("type"),
                }
            )

        if safe_limit is not None:
            items = normalized_items[:safe_limit]
        else:
            items = normalized_items
        total = self._extract_blocket_total(data, fallback=len(normalized_items))
        return {"source": "Blocket", "total": total, "items": items}

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
