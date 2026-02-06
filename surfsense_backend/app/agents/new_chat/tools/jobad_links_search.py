"""
Job ad links tool for SurfSense agent.

Fetches job ad links and metadata from Arbetsförmedlingen/Jobtech JobAd Links API.
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


def _extract_job_item(item: dict[str, Any]) -> dict[str, Any]:
    headline = item.get("headline") or item.get("title") or item.get("occupation")
    employer = None
    employer_obj = item.get("employer") or item.get("company")
    if isinstance(employer_obj, dict):
        employer = employer_obj.get("name") or employer_obj.get("label")
    if not employer and isinstance(employer_obj, str):
        employer = employer_obj

    workplace = item.get("workplace_address") or {}
    municipality = (
        workplace.get("municipality") if isinstance(workplace, dict) else None
    ) or item.get("municipality")
    region = (
        workplace.get("region") if isinstance(workplace, dict) else None
    ) or item.get("region")
    location = None
    if municipality and region:
        location = f"{municipality}, {region}"
    elif municipality:
        location = str(municipality)
    elif region:
        location = str(region)

    published = (
        item.get("publication_date")
        or item.get("published")
        or item.get("last_publication_date")
    )
    application = (
        item.get("application_url")
        or item.get("url")
        or (item.get("application_details") or {}).get("url")
        or (item.get("application_details") or {}).get("href")
    )
    remote_flag = item.get("remote") or (
        workplace.get("remote") if isinstance(workplace, dict) else None
    )

    return {
        "id": item.get("id") or item.get("ad_id") or item.get("job_id"),
        "headline": headline,
        "employer": employer,
        "location": location,
        "published": published,
        "application_url": application,
        "remote": bool(remote_flag) if remote_flag is not None else None,
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
        Search job ads via JobAd Links API.

        Args:
            query: Free text search query.
            location: Location filter (municipality/region).
            occupation: Occupation filter.
            industry: Industry/field filter.
            remote: Filter for remote jobs.
            published_after: ISO date filter for publication date.
            limit: Max number of results (default: 10).
            offset: Offset for pagination (default: 0).
            include_raw: Include raw API payload (default: False).
            extra_params: Optional additional query params supported by API.

        Returns:
            Structured job ad results with links and metadata.
        """
        base_url = config.JOBAD_LINKS_BASE_URL or "https://jobadlinks.api.jobtechdev.se"
        url = f"{base_url.rstrip('/')}/search"
        params: dict[str, Any] = {"limit": max(1, min(limit, 50))}
        if query:
            params["q"] = query
        if location:
            params["location"] = location
        if occupation:
            params["occupation"] = occupation
        if industry:
            params["industry"] = industry
        if remote is not None:
            params["remote"] = str(remote).lower()
        if published_after:
            params["published_after"] = published_after
        if offset > 0:
            params["offset"] = offset
        if extra_params:
            params.update(extra_params)

        headers = {"Accept": "application/json"}
        if config.JOBAD_LINKS_API_KEY:
            headers["X-API-KEY"] = config.JOBAD_LINKS_API_KEY

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        items = []
        if isinstance(payload, dict):
            items = (
                payload.get("hits")
                or payload.get("items")
                or payload.get("links")
                or payload.get("ads")
                or []
            )
        if not isinstance(items, list):
            items = []

        results = [_extract_job_item(item) for item in items if isinstance(item, dict)]

        result = {
            "status": "ok",
            "query": query,
            "results": [
                {k: v for k, v in r.items() if k != "raw"} for r in results
            ],
            "total": payload.get("total") if isinstance(payload, dict) else None,
            "attribution": "Data from Arbetsförmedlingen Jobtech",
        }
        if include_raw:
            result["raw"] = payload
            result["raw_items"] = results
        return result

    return jobad_links_search
