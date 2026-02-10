from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

TRAFIKVERKET_BASE_URL = "https://api.trafikinfo.trafikverket.se/v3"
TRAFIKVERKET_SOURCE = "Trafikverket Open API"
TRAFIKVERKET_DEFAULT_TIMEOUT = 15.0
TRAFIKVERKET_CACHE_TTL = 60 * 5  # 5 minutes
TRAFIKVERKET_MAX_RETRIES = 4


def _build_cache_key(method: str, url: str, payload: Any) -> str:
    raw = json.dumps(
        {"method": method.upper(), "url": url, "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TrafikverketService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = TRAFIKVERKET_BASE_URL,
        timeout: float = TRAFIKVERKET_DEFAULT_TIMEOUT,
        redis_url: str | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("TRAFIKVERKET_API_KEY") or "").strip()
        if not self.api_key:
            base_dir = Path(__file__).resolve().parent.parent.parent
            load_dotenv(base_dir / ".env")
            self.api_key = (os.getenv("TRAFIKVERKET_API_KEY") or "").strip()
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
            raise ValueError("Missing TRAFIKVERKET_API_KEY for Trafikverket API.")

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
        for attempt in range(TRAFIKVERKET_MAX_RETRIES):
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

        raise RuntimeError(last_error or "Trafikverket API request failed.")

    async def fetch(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], bool]:
        return await self._request_json(
            "GET", path, params=params, cache_ttl=TRAFIKVERKET_CACHE_TTL
        )
