"""
Trafiklab realtime route tool for SurfSense agent.

Uses Trafiklab realtime APIs (stop lookup + timetables) to find departures
from an origin stop and optionally match them to a destination.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from app.agents.new_chat.circuit_breaker import get_breaker
from app.config import config

logger = logging.getLogger(__name__)

TRAFIKLAB_BASE_URL = "https://realtime-api.trafiklab.se/v1"


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _select_stop_group(stop_groups: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    if not stop_groups:
        return None
    query_norm = _normalize_text(query)
    exact = [g for g in stop_groups if _normalize_text(g.get("name", "")) == query_norm]
    if exact:
        return exact[0]
    prefix = [
        g
        for g in stop_groups
        if _normalize_text(g.get("name", "")).startswith(query_norm)
    ]
    if prefix:
        return prefix[0]
    contains = [
        g for g in stop_groups if query_norm in _normalize_text(g.get("name", ""))
    ]
    if contains:
        return contains[0]
    return stop_groups[0]


def _normalize_timetable_time(value: str) -> str:
    if not value:
        return value
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.strftime("%Y-%m-%dT%H:%M")
        return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return value


async def _fetch_stop_lookup(
    query: str, api_key: str, client: httpx.AsyncClient
) -> dict[str, Any]:
    url = f"{TRAFIKLAB_BASE_URL}/stops/name/{quote(query)}/"
    response = await client.get(url, params={"key": api_key})
    response.raise_for_status()
    return response.json()


async def _fetch_timetables(
    mode: str, area_id: str, api_key: str, client: httpx.AsyncClient, time: str | None
) -> dict[str, Any]:
    path = f"/{mode}/{area_id}"
    if time:
        path = f"{path}/{time}"
    url = f"{TRAFIKLAB_BASE_URL}{path}"
    response = await client.get(url, params={"key": api_key})
    response.raise_for_status()
    return response.json()


def _match_departure(
    entry: dict[str, Any],
    destination_names: list[str],
    destination_stop_ids: set[str],
    match_strategy: str,
) -> bool:
    route = entry.get("route") or {}
    dest = route.get("destination") or {}
    dest_id = str(dest.get("id") or "")
    if dest_id and dest_id in destination_stop_ids:
        return True

    dest_name = _normalize_text(str(dest.get("name") or ""))
    direction_name = _normalize_text(str(route.get("direction") or ""))

    for candidate in destination_names:
        candidate_norm = _normalize_text(candidate)
        if not candidate_norm:
            continue
        if match_strategy == "exact":
            if candidate_norm == dest_name or candidate_norm == direction_name:
                return True
        elif match_strategy == "starts_with":
            if dest_name.startswith(candidate_norm) or direction_name.startswith(
                candidate_norm
            ):
                return True
        else:
            if candidate_norm in dest_name or candidate_norm in direction_name:
                return True
    return False


def create_trafiklab_route_tool():
    """
    Factory for Trafiklab realtime route tool.
    """

    @tool
    async def trafiklab_route(
        origin: str | None = None,
        destination: str | None = None,
        origin_id: str | None = None,
        destination_id: str | None = None,
        time: str | None = None,
        mode: str = "departures",
        max_results: int | None = None,
        match_strategy: str = "contains",
        include_raw: bool = True,
    ) -> dict[str, Any]:
        """
        Find upcoming departures/arrivals using Trafiklab realtime APIs.

        This tool uses stop lookup + timetables to return a departure board
        from an origin stop. If a destination is provided, it filters the board
        to entries whose direction or destination matches the destination.

        Args:
            origin: Origin stop name (e.g., "Goteborg Centralstation").
            destination: Destination stop name (optional).
            origin_id: Optional origin stop area id (skip lookup).
            destination_id: Optional destination stop area id (skip lookup).
            time: Optional query time in YYYY-MM-DDTHH:MM format.
            mode: "departures" or "arrivals" (default: departures).
            max_results: Optional max number of entries to return.
            match_strategy: "contains", "starts_with", or "exact" matching.
            include_raw: Include raw API payloads (default: True).

        Returns:
            A dictionary with origin/destination info, matching departures,
            and optional raw payloads.
        """
        breaker = get_breaker("trafiklab")
        if not breaker.can_execute():
            return {
                "status": "error",
                "error": f"Service {breaker.name} temporarily unavailable (circuit open)",
            }
        
        api_key = config.TRAFIKLAB_API_KEY
        if not api_key:
            return {
                "status": "error",
                "error": "TRAFIKLAB_API_KEY is not configured.",
            }

        resolved_mode = mode if mode in {"departures", "arrivals"} else "departures"
        requested_time = _normalize_timetable_time(time) if time else None

        origin_lookup: dict[str, Any] | None = None
        destination_lookup: dict[str, Any] | None = None
        origin_stop_group: dict[str, Any] | None = None
        destination_stop_group: dict[str, Any] | None = None

        if not origin_id:
            if not origin:
                return {
                    "status": "error",
                    "error": "Provide origin or origin_id.",
                }

        async with httpx.AsyncClient(timeout=10.0) as client:
            if origin and not origin_id:
                try:
                    origin_lookup = await _fetch_stop_lookup(origin, api_key, client)
                except Exception as exc:
                    logger.error("Trafiklab stop lookup failed: %s", exc)
                    return {
                        "status": "error",
                        "error": f"Stop lookup failed: {exc!s}",
                        "origin": {"query": origin},
                    }
                stop_groups = origin_lookup.get("stop_groups") or []
                origin_stop_group = _select_stop_group(stop_groups, origin)
                if not origin_stop_group:
                    return {
                        "status": "error",
                        "error": "No matching origin stop found.",
                        "origin": {"query": origin},
                    }
                origin_id = str(origin_stop_group.get("id"))

            if destination and not destination_id:
                try:
                    destination_lookup = await _fetch_stop_lookup(
                        destination, api_key, client
                    )
                except Exception as exc:
                    logger.error("Trafiklab stop lookup failed: %s", exc)
                    return {
                        "status": "error",
                        "error": f"Destination lookup failed: {exc!s}",
                        "destination": {"query": destination},
                    }
                stop_groups = destination_lookup.get("stop_groups") or []
                destination_stop_group = _select_stop_group(stop_groups, destination)
                if destination_stop_group:
                    destination_id = str(destination_stop_group.get("id"))

            try:
                timetable = await _fetch_timetables(
                    resolved_mode,
                    str(origin_id),
                    api_key,
                    client,
                    requested_time,
                )
                breaker.record_success()
            except Exception as exc:
                breaker.record_failure()
                logger.error("Trafiklab timetable fetch failed: %s", exc)
                return {
                    "status": "error",
                    "error": f"Timetable request failed: {exc!s}",
                    "origin": {"id": origin_id, "name": origin},
                }

        entries = timetable.get(resolved_mode) or []
        if not isinstance(entries, list):
            entries = []

        destination_names: list[str] = []
        destination_stop_ids: set[str] = set()
        if destination:
            destination_names.append(destination)
        if destination_id and not destination_stop_group:
            destination_stop_ids.add(str(destination_id))
        if destination_stop_group:
            destination_names.append(destination_stop_group.get("name", ""))
            for stop in destination_stop_group.get("stops") or []:
                stop_id = stop.get("id")
                if stop_id:
                    destination_stop_ids.add(str(stop_id))
                stop_name = stop.get("name")
                if stop_name:
                    destination_names.append(stop_name)

        matching_entries: list[dict[str, Any]] = []
        if destination_names or destination_stop_ids:
            for entry in entries:
                if _match_departure(
                    entry, destination_names, destination_stop_ids, match_strategy
                ):
                    matching_entries.append(entry)

        if max_results is not None and max_results > 0:
            entries = entries[:max_results]
            matching_entries = matching_entries[:max_results]

        result: dict[str, Any] = {
            "status": "ok",
            "attribution": "Data from Trafiklab.se (CC-BY 4.0)",
            "board_type": resolved_mode,
            "requested_time": requested_time,
            "query_time": (timetable.get("query") or {}).get("queryTime"),
            "origin": {
                "id": origin_id,
                "name": origin,
                "stop_group": origin_stop_group,
            },
            "destination": {
                "id": destination_id,
                "name": destination,
                "stop_group": destination_stop_group,
            },
            "entries": entries,
            "matching_entries": matching_entries,
            "notes": [
                "This tool uses Trafiklab realtime timetables and stop lookup. It does not compute multi-leg routes.",
            ],
        }

        if include_raw:
            result["raw"] = {
                "origin_lookup": origin_lookup,
                "destination_lookup": destination_lookup,
                "timetable": timetable,
            }

        return result

    return trafiklab_route
