"""
Job ad links tool for SurfSense agent.

    Fetches job ad links and metadata from Arbetsförmedlingen/Jobtech Links API.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any

import httpx
from langchain_core.tools import tool

from app.config import config

logger = logging.getLogger(__name__)

DEFAULT_JOBAD_BASE_URL = "https://links.api.jobtechdev.se"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _first_text(value[0])
    return None


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _extract_location(item: dict[str, Any]) -> str | None:
    addresses = _as_list(item.get("workplace_addresses"))
    for address in addresses:
        if not isinstance(address, dict):
            continue
        municipality = address.get("municipality")
        region = address.get("region")
        city = address.get("city") or address.get("town")
        if municipality and region:
            return f"{municipality}, {region}"
        if city and region:
            return f"{city}, {region}"
        if municipality:
            return str(municipality)
        if city:
            return str(city)
    return None


def _extract_job_item(item: dict[str, Any]) -> dict[str, Any]:
    headline = item.get("headline") or item.get("title") or item.get("occupation")
    employer = None
    employer_obj = item.get("employer") or item.get("company")
    if isinstance(employer_obj, dict):
        employer = employer_obj.get("name") or employer_obj.get("label")
    if not employer and isinstance(employer_obj, str):
        employer = employer_obj

    location = _extract_location(item)

    published = (
        item.get("publication_date")
        or item.get("published")
        or item.get("last_publication_date")
    )
    source_links = _as_list(item.get("source_links"))
    application = None
    sources: list[dict[str, Any]] = []
    for link in source_links:
        if not isinstance(link, dict):
            continue
        label = link.get("label")
        url = link.get("url") or link.get("href")
        if not application and url:
            application = url
        sources.append({"label": label, "url": url})
    remote_flag = item.get("remote")

    return {
        "id": item.get("id") or item.get("ad_id") or item.get("job_id"),
        "headline": headline,
        "employer": employer,
        "location": location,
        "published": published,
        "application_url": application,
        "remote": bool(remote_flag) if remote_flag is not None else None,
        "brief": item.get("brief"),
        "occupation_group": (item.get("occupation_group") or {}).get("label"),
        "occupation_field": (item.get("occupation_field") or {}).get("label"),
        "sources": sources,
        "raw": item,
    }


def create_jobad_links_search_tool():
    """
    Factory for the JobAd Links search tool.
    """

    @tool
    async def jobad_links_search(
        query: str | None = None,
        location: str | None = None,
        occupation: str | None = None,
        industry: str | None = None,
        remote: bool | None = None,
        published_after: str | None = None,
        limit: int = 10,
        offset: int = 0,
        include_raw: bool = False,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Search job ads via Jobtech Links API.

        Args:
            query: Free text search query.
            location: Location filter (municipality/region) - best effort.
            occupation: Occupation filter - best effort.
            industry: Industry/field filter - best effort.
            remote: Filter for remote jobs (best effort).
            published_after: ISO date filter for publication date (best effort).
            limit: Max number of results (default: 10).
            offset: Offset for pagination (default: 0).
            include_raw: Include raw API payload (default: False).
            extra_params: Optional additional query params supported by API.

        Returns:
            Structured job ad results with links and metadata from Jobtech Links.
        """
        base_url = config.JOBAD_LINKS_BASE_URL or DEFAULT_JOBAD_BASE_URL
        url = f"{base_url.rstrip('/')}/joblinks"
        params: dict[str, Any] = {"limit": max(1, min(limit, 100))}
        query_text = str(query) if query else ""
        if not query_text:
            query_text = " ".join(
                part
                for part in [
                    str(occupation) if occupation else "",
                    str(industry) if industry else "",
                    str(location) if location else "",
                ]
                if part
            ).strip()
        if query_text:
            params["q"] = query_text
        else:
            return {
                "status": "error",
                "error": "Provide a query or filters to search job ads.",
            }
        if offset > 0:
            params["offset"] = offset
        if extra_params:
            params.update(extra_params)

        headers = {"Accept": "application/json"}
        if config.JOBAD_LINKS_API_KEY:
            headers["api-key"] = config.JOBAD_LINKS_API_KEY

        payload = None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            if base_url != DEFAULT_JOBAD_BASE_URL:
                logger.warning(
                    "JobAd Links base URL failed, retrying with default: %s", exc
                )
                try:
                    fallback_url = f"{DEFAULT_JOBAD_BASE_URL}/joblinks"
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        response = await client.get(
                            fallback_url, params=params, headers=headers
                        )
                        response.raise_for_status()
                        payload = response.json()
                except Exception as fallback_exc:
                    logger.error("JobAd Links request failed: %s", fallback_exc)
                    return {
                        "status": "error",
                        "error": f"JobAd Links request failed: {fallback_exc!s}",
                        "query": query,
                    }
            else:
                logger.error("JobAd Links request failed: %s", exc)
                return {
                    "status": "error",
                    "error": f"JobAd Links request failed: {exc!s}",
                    "query": query,
                }

        items: list[Any] = []
        if isinstance(payload, dict):
            items = payload.get("hits") or []
        if not isinstance(items, list):
            items = []

        raw_results = [_extract_job_item(item) for item in items if isinstance(item, dict)]
        results = raw_results

        filters_applied = any([location, occupation, industry, published_after, remote])
        if location:
            location_norm = _normalize_text(str(location))
            results = [
                r
                for r in results
                if location_norm
                in _normalize_text(str(r.get("location") or ""))
            ]
        if occupation:
            occupation_norm = _normalize_text(str(occupation))
            results = [
                r
                for r in results
                if occupation_norm
                in _normalize_text(
                    " ".join(
                        [
                            str(r.get("occupation_group") or ""),
                            str(r.get("occupation_field") or ""),
                            str(r.get("headline") or ""),
                            str(r.get("brief") or ""),
                        ]
                    )
                )
            ]
        if industry:
            industry_norm = _normalize_text(str(industry))
            results = [
                r
                for r in results
                if industry_norm
                in _normalize_text(str(r.get("occupation_field") or ""))
            ]
        if published_after:
            try:
                published_cutoff = published_after.split("T")[0]
                results = [
                    r
                    for r in results
                    if r.get("published")
                    and str(r.get("published")).split("T")[0] >= published_cutoff
                ]
            except Exception:
                pass
        if remote is True:
            results = [
                r
                for r in results
                if r.get("remote") is True
                or "remote" in _normalize_text(str(r.get("headline") or ""))
                or "remote" in _normalize_text(str(r.get("brief") or ""))
            ]

        filter_warning = None
        if filters_applied and not results and raw_results:
            results = raw_results
            filter_warning = (
                "Filters returned no results; showing unfiltered results."
            )

        result = {
            "status": "ok",
            "query": query,
            "results": [{k: v for k, v in r.items() if k != "raw"} for r in results],
            "total": payload.get("total", {}).get("value")
            if isinstance(payload, dict)
            else None,
            "attribution": "Data from Arbetsförmedlingen Jobtech",
        }
        if filter_warning:
            result["filter_warning"] = filter_warning
        if include_raw:
            result["raw"] = payload
            result["raw_items"] = raw_results
        return result

    return jobad_links_search
