"""
Libris XL search tool for SurfSense agent.

Searches the Libris XL API (Kungliga biblioteket) and optionally fetches a
single record. Returns a summarized view of results to keep payloads small.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

LIBRIS_BASE_URL = "https://libris.kb.se"
LIBRIS_FIND_URL = f"{LIBRIS_BASE_URL}/find.jsonld"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean_text(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    return value.strip()


def _extract_title(entry: dict[str, Any]) -> str | None:
    titles = _as_list(entry.get("hasTitle")) or _as_list(entry.get("title"))
    for title in titles:
        if not isinstance(title, dict):
            continue
        main = title.get("mainTitle") or title.get("prefLabel") or title.get("label")
        subtitle = title.get("subtitle")
        if main and subtitle:
            return f"{main} : {subtitle}"
        if main:
            return str(main)
    label = entry.get("label") or entry.get("prefLabel") or entry.get("name")
    return _clean_text(str(label)) if label else None


def _extract_authors(entry: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    instance = entry.get("instanceOf") if isinstance(entry.get("instanceOf"), dict) else {}
    contributions = _as_list(instance.get("contribution")) + _as_list(entry.get("contribution"))
    for contrib in contributions:
        if not isinstance(contrib, dict):
            continue
        agent = contrib.get("agent") or {}
        if isinstance(agent, dict):
            name = agent.get("label") or agent.get("name") or agent.get("prefLabel")
        else:
            name = agent
        if name and isinstance(name, str):
            authors.append(name)
    return list(dict.fromkeys([a for a in authors if a]))


def _extract_publication(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    instance = entry.get("instanceOf") if isinstance(entry.get("instanceOf"), dict) else {}
    publications = _as_list(entry.get("publication")) + _as_list(instance.get("publication"))
    year = None
    publisher = None
    for pub in publications:
        if not isinstance(pub, dict):
            continue
        if not year:
            year = pub.get("year") or pub.get("date")
        if not publisher:
            agent = pub.get("agent") if isinstance(pub.get("agent"), dict) else {}
            publisher = agent.get("label") or agent.get("name")
        if year or publisher:
            break
    return (_clean_text(str(year)) if year else None, _clean_text(str(publisher)) if publisher else None)


def _extract_isbn(entry: dict[str, Any]) -> str | None:
    instance = entry.get("instanceOf") if isinstance(entry.get("instanceOf"), dict) else {}
    identifiers = _as_list(entry.get("identifiedBy")) + _as_list(instance.get("identifiedBy"))
    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue
        types = _as_list(identifier.get("@type"))
        if any("ISBN" in str(t).upper() for t in types):
            value = identifier.get("value")
            if value:
                return str(value)
    return None


def _extract_subjects(entry: dict[str, Any]) -> list[str]:
    instance = entry.get("instanceOf") if isinstance(entry.get("instanceOf"), dict) else {}
    subjects = _as_list(instance.get("subject")) + _as_list(entry.get("subject"))
    labels: list[str] = []
    for subj in subjects:
        if not isinstance(subj, dict):
            continue
        label = subj.get("prefLabel") or subj.get("label") or subj.get("name")
        if label and isinstance(label, str):
            labels.append(label)
    return list(dict.fromkeys(labels))


def _extract_summary(entry: dict[str, Any]) -> str | None:
    instance = entry.get("instanceOf") if isinstance(entry.get("instanceOf"), dict) else {}
    summaries = _as_list(entry.get("summary")) + _as_list(instance.get("summary"))
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        label = summary.get("label") or summary.get("text")
        if label and isinstance(label, str):
            return label
    return None


def _extract_cover(entry: dict[str, Any]) -> str | None:
    media = _as_list(entry.get("associatedMedia"))
    if not media and isinstance(entry.get("instanceOf"), dict):
        media = _as_list(entry["instanceOf"].get("associatedMedia"))
    for item in media:
        if not isinstance(item, dict):
            continue
        uri = item.get("uri") or item.get("url")
        if isinstance(uri, list) and uri:
            return str(uri[0])
        if isinstance(uri, str):
            return uri
    return None


def _extract_availability(entry: dict[str, Any]) -> dict[str, Any] | None:
    reverse = entry.get("@reverse") if isinstance(entry.get("@reverse"), dict) else {}
    items = _as_list(reverse.get("itemOf"))
    held_by: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        held = item.get("heldBy")
        if isinstance(held, dict):
            name = held.get("name") or held.get("label")
        else:
            name = None
        if name and isinstance(name, str):
            held_by.append(name)
    if not held_by:
        return None
    return {"count": len(held_by), "libraries": held_by[:5]}


def _normalize_record_url(record_id: str) -> str:
    if record_id.startswith("http://") or record_id.startswith("https://"):
        return record_id
    if record_id.startswith("/"):
        return f"{LIBRIS_BASE_URL}{record_id}"
    if record_id.startswith("data/"):
        return f"{LIBRIS_BASE_URL}/{record_id}"
    return f"{LIBRIS_BASE_URL}/data/{record_id}"


def _extract_record_id(record_url: str) -> str:
    parsed = urlparse(record_url)
    return parsed.path.strip("/") or record_url


def _summarize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    title = _extract_title(entry)
    authors = _extract_authors(entry)
    year, publisher = _extract_publication(entry)
    summary = _extract_summary(entry)
    subjects = _extract_subjects(entry)
    isbn = _extract_isbn(entry)
    cover = _extract_cover(entry)
    availability = _extract_availability(entry)
    entry_id = entry.get("@id") or entry.get("id") or ""
    record_id = _extract_record_id(str(entry_id)) if entry_id else None
    return {
        "id": entry_id,
        "record_id": record_id,
        "title": title,
        "authors": authors,
        "year": year,
        "publisher": publisher,
        "isbn": isbn,
        "summary": summary,
        "subjects": subjects,
        "cover_image": cover,
        "availability": availability,
        "libris_url": f"{LIBRIS_BASE_URL}/{record_id}" if record_id else None,
    }


def create_libris_search_tool():
    """
    Factory for the Libris XL search tool.
    """

    @tool
    async def libris_search(
        query: str | None = None,
        record_id: str | None = None,
        limit: int = 5,
        offset: int = 0,
        include_raw: bool = False,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Search Libris XL or fetch a single record.

        Use this tool to search for books, articles, journals, and more in the
        Libris XL catalog. For advanced queries you can pass fielded syntax in
        the query (e.g., "tove (jansson|lindgren)").

        Args:
            query: Search query string (required unless record_id is provided).
            record_id: Optional Libris record id or URL to fetch a single record.
            limit: Max number of results to return (default: 5).
            offset: Offset for pagination (default: 0).
            include_raw: Include raw JSON-LD response (default: False).
            extra_params: Optional extra query params for advanced filters.

        Returns:
            Search results or record details with summarized fields.
        """
        headers = {"Accept": "application/ld+json"}

        if record_id:
            record_url = _normalize_record_url(record_id)
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(record_url, headers=headers)
                response.raise_for_status()
                payload = response.json()
            summary = _summarize_entry(payload if isinstance(payload, dict) else {})
            result = {
                "status": "ok",
                "mode": "record",
                "record": summary,
                "record_url": record_url,
            }
            if include_raw:
                result["raw"] = payload
            return result

        if not query:
            return {
                "status": "error",
                "error": "Provide a query or a record_id.",
            }

        params: dict[str, Any] = {"q": query, "_limit": max(1, min(limit, 20))}
        if offset > 0:
            params["_offset"] = offset
        if extra_params:
            params.update(extra_params)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(LIBRIS_FIND_URL, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        items = payload.get("items", []) if isinstance(payload, dict) else []
        results = [_summarize_entry(item) for item in items if isinstance(item, dict)]

        result = {
            "status": "ok",
            "mode": "search",
            "query": query,
            "limit": params.get("_limit"),
            "offset": params.get("_offset", 0),
            "total_items": payload.get("totalItems") if isinstance(payload, dict) else None,
            "results": results,
            "next": payload.get("next") if isinstance(payload, dict) else None,
        }
        if include_raw:
            result["raw"] = payload
        return result

    return libris_search
