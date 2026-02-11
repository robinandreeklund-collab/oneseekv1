from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import httpx
from dotenv import load_dotenv

TRAFIKVERKET_BASE_URL = "https://api.trafikinfo.trafikverket.se/v2/data.json"
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

    async def _request_xml(
        self,
        *,
        xml_body: str,
        cache_ttl: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if not self.api_key:
            raise ValueError("Missing TRAFIKVERKET_API_KEY for Trafikverket API.")

        url = self.base_url
        headers = {
            "Content-Type": "application/xml",
            "Accept": "application/json",
        }
        payload = {"xml": xml_body}
        cache_key = None
        cache_hit = False

        if cache_ttl:
            cache_key = _build_cache_key("POST", url, payload)
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
                    response = await client.post(
                        url,
                        headers=headers,
                        content=xml_body.encode("utf-8"),
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

    async def query(
        self,
        *,
        objecttype: str,
        schema_version: str | None = None,
        filter_field: str | None = None,
        filter_value: str | None = None,
        limit: int = 10,
    ) -> tuple[dict[str, Any], bool]:
        if not self.api_key:
            raise ValueError("Missing TRAFIKVERKET_API_KEY for Trafikverket API.")
        filter_xml = ""
        if filter_field and filter_value:
            filter_xml = (
                f"<FILTER><LIKE name=\"{escape(filter_field)}\" "
                f"value=\"{escape(filter_value)}\" /></FILTER>"
            )

        def build_query(schema: str | None) -> str:
            schema_attr = (
                f" schemaversion=\"{escape(schema)}\"" if schema else ""
            )
            return (
                f"<REQUEST>"
                f"<LOGIN authenticationkey=\"{escape(self.api_key)}\" />"
                f"<QUERY objecttype=\"{escape(objecttype)}\"{schema_attr} "
                f"limit=\"{int(limit)}\">"
                f"{filter_xml}"
                f"</QUERY>"
                f"</REQUEST>"
            )

        try:
            return await self._request_xml(
                xml_body=build_query(schema_version),
                cache_ttl=TRAFIKVERKET_CACHE_TTL,
            )
        except RuntimeError as exc:
            if schema_version and "ResourceNotFound" in str(exc):
                return await self._request_xml(
                    xml_body=build_query(None),
                    cache_ttl=TRAFIKVERKET_CACHE_TTL,
                )
            raise
