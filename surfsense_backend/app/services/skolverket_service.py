from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

SKOLVERKET_SYLLABUS_BASE_URL = "https://api.skolverket.se/syllabus"
SKOLVERKET_SCHOOL_UNITS_BASE_URL = "https://api.skolverket.se/skolenhetsregistret"
SKOLVERKET_PLANNED_EDUCATION_BASE_URL = "https://api.skolverket.se/planned-educations"

SKOLVERKET_V3_ACCEPT = "application/vnd.skolverket.plannededucations.api.v3.hal+json"
SKOLVERKET_V4_ACCEPT = "application/vnd.skolverket.plannededucations.api.v4.hal+json"


@dataclass(frozen=True)
class SkolverketApiError(Exception):
    message: str
    status_code: int | None = None
    path: str | None = None
    payload: Any | None = None

    def __str__(self) -> str:
        details = self.message
        if self.status_code is not None:
            details = f"{details} (status={self.status_code})"
        if self.path:
            details = f"{details} [{self.path}]"
        return details


def _normalize_text(value: str) -> str:
    lowered = str(value or "").lower()
    return (
        lowered.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
        .strip()
    )


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value)


class SkolverketService:
    """Native HTTP wrapper for Skolverket public APIs.

    This service mirrors the MCP wrapper's intent, but talks directly to the
    upstream APIs so we do not need an external MCP server process.
    """

    def __init__(
        self,
        *,
        syllabus_base_url: str = SKOLVERKET_SYLLABUS_BASE_URL,
        school_units_base_url: str = SKOLVERKET_SCHOOL_UNITS_BASE_URL,
        planned_education_base_url: str = SKOLVERKET_PLANNED_EDUCATION_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 0.75,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.syllabus_base_url = syllabus_base_url.rstrip("/")
        self.school_units_base_url = school_units_base_url.rstrip("/")
        self.planned_education_base_url = planned_education_base_url.rstrip("/")
        self.timeout = max(5.0, float(timeout))
        self.max_retries = max(1, int(max_retries))
        self.retry_delay_seconds = max(0.1, float(retry_delay_seconds))
        self.cache_ttl_seconds = max(1, int(cache_ttl_seconds))
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cache_get(self, key: str) -> Any | None:
        cached = self._cache.get(key)
        if not cached:
            return None
        expires_at, value = cached
        if time.time() >= expires_at:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        ttl = max(1, int(ttl_seconds or self.cache_ttl_seconds))
        self._cache[key] = (time.time() + ttl, value)

    async def _request_json(
        self,
        *,
        base_url: str,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = f"{base_url}{path}"
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        clean_headers = {"Accept": "application/json"}
        if headers:
            clean_headers.update(headers)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(
                        url,
                        params=clean_params or None,
                        headers=clean_headers,
                    )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay_seconds * (2**attempt))
                    continue
                if response.status_code >= 400:
                    message = self._extract_error_message(response)
                    raise SkolverketApiError(
                        message=message,
                        status_code=response.status_code,
                        path=path,
                        payload=self._safe_json(response),
                    )
                return self._safe_json(response)
            except (httpx.HTTPError, SkolverketApiError) as exc:
                last_error = exc
                if isinstance(exc, SkolverketApiError):
                    if exc.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay_seconds * (2**attempt))
                        continue
                    raise
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay_seconds * (2**attempt))
                    continue
        if isinstance(last_error, SkolverketApiError):
            raise last_error
        raise SkolverketApiError(
            message=f"Request failed: {last_error!s}" if last_error else "Request failed",
            path=path,
        )

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        payload = SkolverketService._safe_json(response)
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("detail") or payload.get("title")
            body = payload.get("body")
            if message and body is not None:
                return f"Skolverket API error: {response.status_code} - {message} - {body}"
            if message:
                return f"Skolverket API error: {response.status_code} - {message}"
            return f"Skolverket API error: {response.status_code} - {_stringify(payload)[:700]}"
        return f"Skolverket API error: {response.status_code} - {_stringify(payload)[:700]}"

    @staticmethod
    def _unwrap_planned_payload(payload: Any, *, path: str) -> Any:
        if isinstance(payload, dict) and "status" in payload and "body" in payload:
            status = str(payload.get("status") or "").upper()
            if status and status != "OK":
                raise SkolverketApiError(
                    message=str(payload.get("message") or "Skolverket planned-educations error"),
                    path=path,
                    payload=payload,
                )
            return payload.get("body")
        return payload

    async def syllabus_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return await self._request_json(
            base_url=self.syllabus_base_url,
            path=path,
            params=params,
            headers={"Accept": "application/json"},
        )

    async def school_units_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return await self._request_json(
            base_url=self.school_units_base_url,
            path=path,
            params=params,
            headers={"Accept": "application/json"},
        )

    async def planned_v3_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        payload = await self._request_json(
            base_url=self.planned_education_base_url,
            path=path,
            params=params,
            headers={"Accept": SKOLVERKET_V3_ACCEPT},
        )
        return self._unwrap_planned_payload(payload, path=path)

    async def planned_v4_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        payload = await self._request_json(
            base_url=self.planned_education_base_url,
            path=path,
            params=params,
            headers={"Accept": SKOLVERKET_V4_ACCEPT},
        )
        return self._unwrap_planned_payload(payload, path=path)

    async def get_all_school_units(self) -> list[dict[str, Any]]:
        cache_key = "school_units_v2_all"
        cached = self._cache_get(cache_key)
        if isinstance(cached, list):
            return cached
        payload = await self.school_units_get("/v2/school-units")
        units = []
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                attrs = data.get("attributes")
                if isinstance(attrs, list):
                    units = [item for item in attrs if isinstance(item, dict)]
        self._cache_set(cache_key, units, ttl_seconds=300)
        return units

    async def get_school_unit_by_code(self, code: str) -> dict[str, Any] | None:
        clean_code = str(code or "").strip()
        if not clean_code:
            return None
        cache_key = f"school_unit_v2_{clean_code}"
        cached = self._cache_get(cache_key)
        if isinstance(cached, dict):
            return cached
        try:
            payload = await self.school_units_get(f"/v2/school-units/{clean_code}")
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, dict):
                    attrs = data.get("attributes")
                    if isinstance(attrs, dict):
                        self._cache_set(cache_key, attrs, ttl_seconds=300)
                        return attrs
        except SkolverketApiError:
            pass
        units = await self.get_all_school_units()
        for unit in units:
            if str(unit.get("schoolUnitCode") or "").strip() == clean_code:
                self._cache_set(cache_key, unit, ttl_seconds=300)
                return unit
        return None

    async def iter_planned_v4_pages(
        self,
        path: str,
        *,
        base_params: dict[str, Any] | None = None,
        max_pages: int = 5,
        page_param: str = "page",
        size_param: str = "size",
        size: int = 200,
    ) -> list[Any]:
        pages: list[Any] = []
        max_pages = max(1, min(int(max_pages), 20))
        for page in range(max_pages):
            params = dict(base_params or {})
            params[page_param] = page
            params[size_param] = size
            body = await self.planned_v4_get(path, params=params)
            pages.append(body)
            page_info = body.get("page") if isinstance(body, dict) else None
            if not isinstance(page_info, dict):
                break
            total_pages = page_info.get("totalPages")
            if isinstance(total_pages, int) and page >= total_pages - 1:
                break
        return pages

    @staticmethod
    def matches_text(candidate: Any, query: str) -> bool:
        query_norm = _normalize_text(query)
        if not query_norm:
            return True
        text = _normalize_text(_stringify(candidate))
        return query_norm in text

