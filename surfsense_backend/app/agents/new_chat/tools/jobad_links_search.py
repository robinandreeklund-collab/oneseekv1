"""
Job ad links tool for SurfSense agent.

    Fetches job ad links and metadata from Arbetsförmedlingen/Jobtech Links API.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.tools import tool

from app.config import config

logger = logging.getLogger(__name__)


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
        base_url = config.JOBAD_LINKS_BASE_URL or "https://links.api.jobtechdev.se"
        url = f"{base_url.rstrip('/')}/joblinks"
        params: dict[str, Any] = {"limit": max(1, min(limit, 50))}
        query_parts = []
        if query:
            query_parts.append(str(query))
        if location:
            query_parts.append(str(location))
        if occupation:
            query_parts.append(str(occupation))
        if industry:
            query_parts.append(str(industry))
        if remote is True:
            query_parts.append("remote")
        if query_parts:
            params["q"] = " ".join(query_parts)
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

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
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

        results = [_extract_job_item(item) for item in items if isinstance(item, dict)]

        if location:
            location_lower = str(location).lower()
            results = [
                r
                for r in results
                if (r.get("location") or "").lower().find(location_lower) >= 0
            ]
        if occupation:
            occupation_lower = str(occupation).lower()
            results = [
                r
                for r in results
                if occupation_lower
                in " ".join(
                    [
                        str(r.get("occupation_group") or ""),
                        str(r.get("occupation_field") or ""),
                        str(r.get("headline") or ""),
                        str(r.get("brief") or ""),
                    ]
                ).lower()
            ]
        if industry:
            industry_lower = str(industry).lower()
            results = [
                r
                for r in results
                if industry_lower in str(r.get("occupation_field") or "").lower()
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
                or "remote" in str(r.get("headline") or "").lower()
                or "remote" in str(r.get("brief") or "").lower()
            ]

        result = {
            "status": "ok",
            "query": query,
            "results": [{k: v for k, v in r.items() if k != "raw"} for r in results],
            "total": payload.get("total", {}).get("value")
            if isinstance(payload, dict)
            else None,
            "attribution": "Data from Arbetsförmedlingen Jobtech",
        }
        if include_raw:
            result["raw"] = payload
            result["raw_items"] = results
        return result

    return jobad_links_search
