from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from typing import Any

import httpx

BOLAGSVERKET_BASE_URL = "https://api.bolagsverket.se/open-data/v2"
BOLAGSVERKET_SOURCE = "Bolagsverket Open Data API"
BOLAGSVERKET_DEFAULT_TIMEOUT = 20.0
BOLAGSVERKET_CACHE_TTL = 60 * 60 * 24  # 1 day
BOLAGSVERKET_MAX_RETRIES = 4


def _clean_orgnr(value: str) -> str:
    return re.sub(r"[^0-9]", "", value or "").strip()


def _build_cache_key(method: str, url: str, payload: Any) -> str:
    raw = json.dumps(
        {"method": method.upper(), "url": url, "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class BolagsverketService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = BOLAGSVERKET_BASE_URL,
        timeout: float = BOLAGSVERKET_DEFAULT_TIMEOUT,
        redis_url: str | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("BOLAGSVERKET_API_KEY") or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._redis_url = redis_url or os.getenv("REDIS_APP_URL") or ""
        self._redis_client = None

    def _get_redis(self):
        if not self._redis_url:
            return None
        if self._redis_client is not None:
            return self._redis_client
        try:
            import redis

            self._redis_client = redis.from_url(
                self._redis_url, decode_responses=True
            )
        except Exception:
            self._redis_client = None
        return self._redis_client

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        cache_ttl: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if not self.api_key:
            raise ValueError("Missing BOLAGSVERKET_API_KEY for Bolagsverket API.")

        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"X-Api-Key": self.api_key}
        payload = {"params": params or {}, "json": json_body or {}}
        cache_key = None
        cache_hit = False

        if method.upper() == "GET" and cache_ttl:
            cache_key = _build_cache_key(method, url, payload)
            client = self._get_redis()
            if client:
                cached = client.get(cache_key)
                if cached:
                    try:
                        return json.loads(cached), True
                    except json.JSONDecodeError:
                        pass

        last_error: str | None = None
        for attempt in range(BOLAGSVERKET_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        json=json_body,
                    )
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else (0.5 * (2**attempt))
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                data = response.json()
                if cache_key:
                    client = self._get_redis()
                    if client:
                        client.setex(cache_key, cache_ttl, json.dumps(data))
                        cache_hit = False
                return data, cache_hit
            except httpx.HTTPStatusError as exc:
                last_error = f"{exc.response.status_code}: {exc.response.text}"
            except (httpx.RequestError, ValueError) as exc:
                last_error = str(exc)
            await asyncio.sleep(0.5 * (2**attempt))

        raise RuntimeError(last_error or "Bolagsverket API request failed.")

    async def get_company_basic(self, orgnr: str) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_company_status(self, orgnr: str) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}/status", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_company_address(self, orgnr: str) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}/adress", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def search_by_name(
        self, name: str, *, limit: int = 5, offset: int = 0
    ) -> tuple[dict[str, Any], bool]:
        return await self._request_json(
            "GET",
            "foretag",
            params={"namn": name, "limit": limit, "offset": offset},
            cache_ttl=BOLAGSVERKET_CACHE_TTL,
        )

    async def search_by_orgnr(
        self, orgnr: str
    ) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET",
            "foretag",
            params={"orgnr": orgnr},
            cache_ttl=BOLAGSVERKET_CACHE_TTL,
        )

    async def search_by_industry(
        self, sni: str, *, limit: int = 5, offset: int = 0
    ) -> tuple[dict[str, Any], bool]:
        return await self._request_json(
            "GET",
            "foretag",
            params={"sni": sni, "limit": limit, "offset": offset},
            cache_ttl=BOLAGSVERKET_CACHE_TTL,
        )

    async def search_by_region(
        self, region: str, *, limit: int = 5, offset: int = 0
    ) -> tuple[dict[str, Any], bool]:
        return await self._request_json(
            "GET",
            "foretag",
            params={"lan": region, "limit": limit, "offset": offset},
            cache_ttl=BOLAGSVERKET_CACHE_TTL,
        )

    async def search_by_status(
        self, status: str, *, limit: int = 5, offset: int = 0
    ) -> tuple[dict[str, Any], bool]:
        return await self._request_json(
            "GET",
            "foretag",
            params={"status": status, "limit": limit, "offset": offset},
            cache_ttl=BOLAGSVERKET_CACHE_TTL,
        )

    async def get_financial_statements(
        self, orgnr: str, *, year: int | None = None
    ) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        params = {"ar": year} if year else None
        return await self._request_json(
            "GET", f"foretag/{orgnr}/bokslut", params=params, cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_annual_reports(
        self, orgnr: str, *, year: int | None = None
    ) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        params = {"ar": year} if year else None
        return await self._request_json(
            "GET",
            f"foretag/{orgnr}/arsredovisning",
            params=params,
            cache_ttl=BOLAGSVERKET_CACHE_TTL,
        )

    async def get_key_ratios(
        self, orgnr: str, *, year: int | None = None
    ) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        params = {"ar": year} if year else None
        return await self._request_json(
            "GET", f"foretag/{orgnr}/nyckeltal", params=params, cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_board(self, orgnr: str) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}/styrelse", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_owners(self, orgnr: str) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}/agare", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_signatories(self, orgnr: str) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}/firmatecknare", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_f_tax_status(self, orgnr: str) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}/fskatt", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_vat_status(self, orgnr: str) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}/moms", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_bankruptcy_status(
        self, orgnr: str
    ) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        return await self._request_json(
            "GET", f"foretag/{orgnr}/konkurs", cache_ttl=BOLAGSVERKET_CACHE_TTL
        )

    async def get_change_history(
        self,
        orgnr: str,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        orgnr = _clean_orgnr(orgnr)
        params: dict[str, Any] = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return await self._request_json(
            "GET",
            f"foretag/{orgnr}/andringar",
            params=params or None,
            cache_ttl=BOLAGSVERKET_CACHE_TTL,
        )
