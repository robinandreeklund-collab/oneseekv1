from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from math import prod
from typing import Any
from urllib.parse import quote as url_quote

import httpx
from cachetools import TTLCache

from app.utils.text import (
    normalize_text as _normalize_text,
    score_text as _score_text,
    tokenize as _tokenize,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults — overridable via Config or env vars
# ---------------------------------------------------------------------------

SCB_BASE_URL_V2 = os.getenv(
    "SCB_BASE_URL",
    "https://statistikdatabasen.scb.se/api/v2/",
)
SCB_BASE_URL_V1 = os.getenv(
    "SCB_BASE_URL_V1",
    "https://api.scb.se/OV0104/v1/doris/sv/ssd/",
)
SCB_API_VERSION = os.getenv("SCB_API_VERSION", "v2")

# Default to v2
SCB_BASE_URL = SCB_BASE_URL_V2 if SCB_API_VERSION == "v2" else SCB_BASE_URL_V1

SCB_MAX_CELLS = int(os.getenv("SCB_MAX_CELLS", "150000"))
SCB_DEFAULT_TIMEOUT = float(os.getenv("SCB_TIMEOUT", "25.0"))
SCB_CACHE_TTL = int(os.getenv("SCB_CACHE_TTL", "3600"))  # 1 hour default

# v2 output formats
SCB_OUTPUT_FORMATS = frozenset({
    "json-stat2", "csv", "xlsx", "parquet", "html", "px", "json-px",
})

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScbTable:
    id: str
    path: str
    title: str
    updated: str | None = None
    breadcrumb: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Helper functions (public — re-exported for tests)
# ---------------------------------------------------------------------------


def _parse_iso(updated: str | None) -> datetime | None:
    if not updated:
        return None
    try:
        return datetime.fromisoformat(updated.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _extract_years(text: str) -> list[str]:
    years = re.findall(r"\b(?:19|20)\d{2}\b", text or "")
    return list(dict.fromkeys(years))


def _is_time_variable(code: str, label: str) -> bool:
    normalized_code = _normalize_text(code)
    normalized_label = _normalize_text(label)
    return any(
        marker in normalized_code or marker in normalized_label
        for marker in ("tid", "time", "ar", "year", "manad", "kvartal")
    )


def _is_region_variable(code: str, label: str) -> bool:
    normalized_code = _normalize_text(code)
    normalized_label = _normalize_text(label)
    return any(
        marker in normalized_code or marker in normalized_label
        for marker in ("region", "lan", "kommun", "lans", "county")
    )


def _is_gender_variable(code: str, label: str) -> bool:
    normalized_code = _normalize_text(code)
    normalized_label = _normalize_text(label)
    return any(marker in normalized_code or marker in normalized_label for marker in ("kon", "sex", "gender"))


def _is_age_variable(code: str, label: str) -> bool:
    normalized_code = _normalize_text(code)
    normalized_label = _normalize_text(label)
    return any(marker in normalized_code or marker in normalized_label for marker in ("alder", "age"))


def _has_region_request(query_tokens: set[str], query_norm: str) -> bool:
    markers = {
        "lan",
        "lans",
        "län",
        "kommun",
        "region",
        "stockholm",
        "goteborg",
        "göteborg",
        "malmo",
        "malmö",
        "skane",
        "skåne",
        "uppsala",
        "västra",
        "vastra",
        "gotaland",
        "götaland",
        "riket",
        "sverige",
    }
    return any(token in markers for token in query_tokens) or " per " in query_norm


def _has_gender_request(query_tokens: set[str], query_norm: str) -> bool:
    markers = {"kvinna", "kvinnor", "man", "män", "kon", "kön", "gender"}
    return any(token in markers for token in query_tokens) or "kvin" in query_norm


def _has_age_request(query_tokens: set[str], query_norm: str) -> bool:
    markers = {"alder", "ålder", "age", "aldersgrupp", "åldersgrupp"}
    return any(token in markers for token in query_tokens) or "alder" in query_norm


def _score_table_metadata(
    *,
    metadata: dict[str, Any],
    query_tokens: set[str],
    query_norm: str,
    requested_years: list[str],
    wants_region: bool,
    wants_gender: bool,
    wants_age: bool,
) -> int:
    score = 0
    variables = metadata.get("variables") or []
    if not isinstance(variables, list):
        return score

    has_time = False
    for var in variables:
        code = str(var.get("code") or "")
        label = str(var.get("text") or code)
        values = [str(v) for v in (var.get("values") or []) if v is not None]
        value_texts = [
            str(v) for v in (var.get("valueTexts") or []) if v is not None
        ]

        score += min(3, _score_text(query_tokens, f"{code} {label}"))

        if _is_time_variable(code, label):
            has_time = True
            if requested_years and values:
                matches = 0
                for year in requested_years:
                    if any(value.startswith(year) for value in values):
                        matches += 1
                if matches:
                    score += 3 * matches
                else:
                    score -= 4

        if wants_region and _is_region_variable(code, label):
            score += 4
        if wants_gender and _is_gender_variable(code, label):
            score += 3
        if wants_age and _is_age_variable(code, label):
            score += 2

        if value_texts and len(value_texts) <= 200:
            for text in value_texts:
                if _score_text(query_tokens, text) > 0:
                    score += 2
                    break

    if requested_years and not has_time:
        score -= 4

    return score


def _match_values_by_text(
    values: list[str],
    value_texts: list[str],
    query_norm: str,
    query_tokens: set[str],
) -> list[str]:
    matches: list[str] = []
    for value, text in zip(values, value_texts, strict=False):
        normalized = _normalize_text(text)
        if not normalized:
            continue
        # Use word-boundary check to avoid false positives (BUG-3 fix)
        norm_tokens = set(normalized.split())
        if norm_tokens and norm_tokens.issubset(query_tokens):
            matches.append(value)
            continue
        # Fallback: check if normalized text appears as whole words in query
        if f" {normalized} " in f" {query_norm} ":
            matches.append(value)
    return matches


def _pick_preferred_value(values: list[str], value_texts: list[str], preferred: list[str]) -> list[str]:
    preferred_norm = [_normalize_text(p) for p in preferred]
    for value, text in zip(values, value_texts, strict=False):
        normalized = _normalize_text(text)
        if not normalized:
            continue
        for pref in preferred_norm:
            if pref and pref in normalized:
                return [value]
    return [values[0]] if values else []


# ---------------------------------------------------------------------------
# ScbService — v2-first with v1 fallback
# ---------------------------------------------------------------------------


class ScbService:
    """Client for SCB Statistikdatabasen (PxWebApi v2 / PxWeb v1).

    Changes from v1-only implementation:
    - Persistent httpx.AsyncClient with connection pooling (OPT-1)
    - asyncio.Lock on caches to prevent race conditions (BUG-1)
    - v2 table search via GET /tables?query= (OPT-3)
    - v2 metadata via GET /tables/{id}/metadata
    - v2 data via POST /tables/{id}/data with selection[] format
    - Total timeout on collect_tables (BUG-4)
    - URL encoding for path components (BUG-6)
    """

    def __init__(
        self,
        base_url: str = SCB_BASE_URL,
        timeout: float = SCB_DEFAULT_TIMEOUT,
        max_cells: int = SCB_MAX_CELLS,
        cache_ttl: int = SCB_CACHE_TTL,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.max_cells = max_cells
        self._is_v2 = "/api/v2" in self.base_url
        self._client: httpx.AsyncClient | None = None
        # TTL caches with lock (OPT-4 + BUG-1 fix)
        self._cache_lock = asyncio.Lock()
        self._node_cache: TTLCache[str, list[dict[str, Any]]] = TTLCache(
            maxsize=1000, ttl=cache_ttl,
        )
        self._metadata_cache: TTLCache[str, dict[str, Any]] = TTLCache(
            maxsize=500, ttl=cache_ttl,
        )
        self._codelist_cache: TTLCache[str, dict[str, Any]] = TTLCache(
            maxsize=200, ttl=cache_ttl,
        )

        from app.services.cache_control import register_service_cache

        register_service_cache(self._node_cache)
        register_service_cache(self._metadata_cache)
        register_service_cache(self._codelist_cache)

    # -- Lifecycle -----------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create a persistent HTTP client (OPT-1)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # -- Low-level HTTP ------------------------------------------------------

    def _encode_path(self, path: str) -> str:
        """URL-encode path components to handle Swedish characters (BUG-6)."""
        parts = (path or "").split("/")
        return "/".join(url_quote(part, safe="") for part in parts)

    def _build_url(self, path: str, *, trailing: bool) -> str:
        cleaned = (path or "").lstrip("/")
        encoded = self._encode_path(cleaned)
        url = f"{self.base_url}{encoded}"
        if trailing and not url.endswith("/"):
            url += "/"
        return url

    async def _get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        client = self._get_client()
        response = await client.get(url, params=params)
        response.raise_for_status()
        return self._decode_json_response(response)

    async def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        client = self._get_client()
        response = await client.post(url, json=payload, params=params)
        response.raise_for_status()
        return self._decode_json_response(response)

    @staticmethod
    def _decode_json_response(response: httpx.Response) -> Any:
        """Decode JSON from an httpx response, handling encoding mismatches.

        Some SCB endpoints declare charset=utf-8 but return Latin-1 bytes
        (e.g. Swedish characters å/ä/ö encoded as single bytes).  This
        method falls back to Latin-1 decoding when UTF-8 fails.
        """
        try:
            return response.json()
        except UnicodeDecodeError:
            raw = response.content
            for encoding in ("latin-1", "cp1252"):
                try:
                    text = raw.decode(encoding)
                    return json.loads(text)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
            # Last resort: replace bad bytes
            text = raw.decode("utf-8", errors="replace")
            return json.loads(text)

    # -- v2 Table Search (OPT-3) --------------------------------------------

    async def search_tables(
        self,
        query: str,
        *,
        limit: int = 80,
        lang: str = "sv",
        past_days: int | None = None,
    ) -> list[ScbTable]:
        """Search tables via v2 GET /tables endpoint.

        Replaces the slow tree-traversal approach with a single API call.
        """
        if not self._is_v2:
            return []

        url = f"{self.base_url}tables"
        params: dict[str, Any] = {
            "query": query,
            "pageSize": min(limit, 100),
            "lang": lang,
        }
        if past_days is not None:
            params["pastDays"] = past_days

        try:
            data = await self._get_json(url, params=params)
        except httpx.HTTPError as exc:
            logger.warning("v2 table search failed: %s", exc)
            return []

        tables: list[ScbTable] = []
        items = data if isinstance(data, list) else data.get("tables", data.get("data", []))
        if not isinstance(items, list):
            return []

        for item in items[:limit]:
            table_id = str(item.get("id") or "").strip()
            if not table_id:
                continue
            tables.append(
                ScbTable(
                    id=table_id,
                    path=table_id,
                    title=str(item.get("label") or item.get("text") or table_id),
                    updated=item.get("updated"),
                )
            )
        return tables

    # -- v1 Tree Navigation (fallback) --------------------------------------

    async def list_nodes(self, path: str) -> list[dict[str, Any]]:
        url = self._build_url(path, trailing=True)
        async with self._cache_lock:
            if url in self._node_cache:
                return list(self._node_cache[url])
        data = await self._get_json(url)
        if not isinstance(data, list):
            return []
        async with self._cache_lock:
            self._node_cache[url] = data
        return list(data)

    async def collect_tables(
        self,
        base_path: str,
        query: str,
        *,
        max_tables: int = 80,
        max_depth: int = 4,
        max_nodes: int = 140,
        max_children: int = 8,
        total_timeout: float = 60.0,
        max_concurrent: int = 5,
    ) -> list[ScbTable]:
        """Priority-BFS through v1 tree, with parallel node fetching (OPT-2).

        Uses a semaphore-bounded parallel fetch for each BFS level, and
        prioritises high-scoring branches (BUG-2 fix: depth-first for scored
        branches avoids broad nodes consuming the whole node budget).
        """
        query_tokens = set(_tokenize(query))
        semaphore = asyncio.Semaphore(max_concurrent)

        # Priority queue: (negative_score, depth, path, breadcrumb)
        # Using negative score so lower = better when sorted ascending
        queue: list[tuple[int, int, str, tuple[str, ...]]] = [
            (0, 0, base_path.rstrip("/") + "/", ())
        ]
        seen: set[str] = set()
        tables: list[ScbTable] = []
        deadline = asyncio.get_event_loop().time() + total_timeout

        async def _fetch_bounded(path: str) -> list[dict[str, Any]]:
            async with semaphore:
                return await self.list_nodes(path)

        while queue and len(tables) < max_tables and len(seen) < max_nodes:
            # BUG-4 fix: total timeout
            if asyncio.get_event_loop().time() > deadline:
                logger.warning("collect_tables timed out after %.0fs", total_timeout)
                break

            # BUG-2 fix: sort queue by priority (highest score first)
            queue.sort(key=lambda item: (item[0], item[1]))

            # OPT-2: Batch-fetch up to max_concurrent paths at same priority level
            batch_paths: list[tuple[int, int, str, tuple[str, ...]]] = []
            while queue and len(batch_paths) < max_concurrent:
                entry = queue.pop(0)
                _neg_score, depth, path, breadcrumb = entry
                if path in seen:
                    continue
                seen.add(path)
                batch_paths.append(entry)

            if not batch_paths:
                continue

            # Parallel fetch for this batch
            fetch_tasks = [_fetch_bounded(entry[2]) for entry in batch_paths]
            try:
                results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            except Exception:
                continue

            for (_neg_score, depth, current_path, breadcrumb), items in zip(
                batch_paths, results, strict=False
            ):
                if isinstance(items, Exception):
                    continue
                if not isinstance(items, list):
                    continue

                children: list[tuple[int, int, str, tuple[str, ...]]] = []
                for item in items:
                    item_id = str(item.get("id") or "").strip()
                    if not item_id:
                        continue
                    item_type = str(item.get("type") or "").strip().lower()
                    item_text = str(item.get("text") or item_id)
                    if item_type == "t":
                        table_path = f"{current_path}{item_id}"
                        tables.append(
                            ScbTable(
                                id=item_id,
                                path=table_path,
                                title=item_text,
                                updated=item.get("updated"),
                                breadcrumb=breadcrumb,
                            )
                        )
                        if len(tables) >= max_tables:
                            break
                    elif item_type == "l" and depth < max_depth:
                        score = _score_text(query_tokens, f"{item_id} {item_text}")
                        next_path = f"{current_path}{item_id}/"
                        next_breadcrumb = (*breadcrumb, item_text)
                        children.append((-score, depth + 1, next_path, next_breadcrumb))

                if children:
                    children.sort(key=lambda item: (item[0], item[1]))
                    if depth <= 1:
                        selected = children
                    else:
                        selected = [child for child in children if child[0] < 0]
                        if len(selected) < max_children:
                            selected = children[:max_children]
                    queue.extend(selected)

        return tables

    # -- Metadata -----------------------------------------------------------

    async def get_table_metadata(self, table_path: str) -> dict[str, Any]:
        """Fetch table metadata. Uses v2 /tables/{id}/metadata or v1 GET."""
        if self._is_v2:
            return await self._get_table_metadata_v2(table_path)
        return await self._get_table_metadata_v1(table_path)

    async def _get_table_metadata_v2(self, table_id: str) -> dict[str, Any]:
        """Fetch metadata via v2 /tables/{id}/metadata."""
        cache_key = f"v2:{table_id}"
        async with self._cache_lock:
            if cache_key in self._metadata_cache:
                return dict(self._metadata_cache[cache_key])

        clean_id = table_id.strip("/")
        url = f"{self.base_url}tables/{url_quote(clean_id, safe='')}/metadata"
        try:
            data = await self._get_json(url, params={"lang": "sv"})
        except httpx.HTTPError:
            return {}

        if not isinstance(data, dict):
            return {}

        # Normalize v2 metadata to match the internal format expected by
        # _build_selections and _score_table_metadata.
        metadata = self._normalize_v2_metadata(data)
        async with self._cache_lock:
            self._metadata_cache[cache_key] = metadata
        return metadata

    async def _get_table_metadata_v1(self, table_path: str) -> dict[str, Any]:
        url = self._build_url(table_path, trailing=False)
        async with self._cache_lock:
            if url in self._metadata_cache:
                return dict(self._metadata_cache[url])
        data = await self._get_json(url)
        if isinstance(data, dict):
            async with self._cache_lock:
                self._metadata_cache[url] = data
            return data
        return {}

    @staticmethod
    def _normalize_v2_metadata(data: dict[str, Any]) -> dict[str, Any]:
        """Convert v2 metadata format to the internal v1-compatible format.

        The v2 /metadata endpoint returns JSON-stat2 format with:
        - ``id``: list of dimension names (e.g. ["Region", "Tid", ...])
        - ``dimension``: dict mapping each name to an object with ``label``
          and ``category`` (which has ``index`` and ``label`` sub-dicts).

        This method also handles older PxWeb-style responses that use a
        ``variables`` list with ``code``/``label``/``values`` entries.
        """
        # --- JSON-stat2 format (v2 /metadata endpoint) ---
        dim_ids = data.get("id")
        dimensions = data.get("dimension")
        if isinstance(dim_ids, list) and isinstance(dimensions, dict):
            normalized_vars: list[dict[str, Any]] = []
            for dim_id in dim_ids:
                dim = dimensions.get(dim_id)
                if not isinstance(dim, dict):
                    continue
                label = str(dim.get("label") or dim_id)
                category = dim.get("category") or {}
                index_map = category.get("index") or {}
                label_map = category.get("label") or {}

                # Sort value codes by their positional index
                if isinstance(index_map, dict):
                    sorted_codes = sorted(
                        index_map.keys(), key=lambda k: index_map[k]
                    )
                else:
                    sorted_codes = list(index_map)

                values = [str(c) for c in sorted_codes]
                value_texts = [
                    str(label_map.get(c, c)) for c in sorted_codes
                ]

                normalized_vars.append({
                    "code": str(dim_id),
                    "text": label,
                    "values": values,
                    "valueTexts": value_texts,
                })
            return {"variables": normalized_vars}

        # --- PxWeb-style format (variables list) ---
        variables = data.get("variables") or []
        if not isinstance(variables, list):
            return data

        # Check if already in v1-compatible format
        if variables and "valueTexts" in variables[0]:
            return data

        normalized_vars = []
        for var in variables:
            code = str(var.get("code") or "")
            text = str(var.get("label") or var.get("text") or code)
            raw_values = var.get("values") or []

            values: list[str] = []
            value_texts: list[str] = []

            if raw_values and isinstance(raw_values[0], dict):
                # v2 format: values is list of {code, label}
                for val_obj in raw_values:
                    values.append(str(val_obj.get("code") or ""))
                    value_texts.append(str(val_obj.get("label") or ""))
            elif raw_values and isinstance(raw_values[0], str):
                # Already string format (v1 or hybrid)
                values = [str(v) for v in raw_values]
                value_texts = [str(v) for v in (var.get("valueTexts") or raw_values)]
            else:
                values = [str(v) for v in raw_values]
                value_texts = list(values)

            normalized_vars.append({
                "code": code,
                "text": text,
                "values": values,
                "valueTexts": value_texts,
            })

        return {"variables": normalized_vars}

    # -- Table Discovery ----------------------------------------------------

    async def find_best_table_candidates(
        self,
        base_path: str,
        query: str,
        *,
        scoring_hint: str = "",
        max_tables: int = 80,
        metadata_limit: int = 10,
        candidate_limit: int = 5,
    ) -> tuple[ScbTable | None, list[ScbTable]]:
        """Find the best matching SCB table for a query.

        Uses a two-pronged approach:
        1. v2 API text search (broad, all subject areas) with the *raw* query
        2. v1 tree traversal scoped to ``base_path`` (domain-specific)

        Results are merged, deduplicated, and scored using both the raw query
        tokens and optional ``scoring_hint`` tokens (domain keywords / table
        codes) that boost relevance without polluting the API search.
        """
        # --- Collect tables from both sources in parallel -------------------
        v2_tables: list[ScbTable] = []
        v1_tables: list[ScbTable] = []

        if self._is_v2:
            # v2: send only the raw user question — avoid enrichment noise
            v2_coro = self.search_tables(query, limit=max_tables)
            # Also run v1 tree traversal scoped to the domain for diversity
            v1_coro = self.collect_tables(
                base_path, query, max_tables=max(20, max_tables // 2),
            )
            v2_tables, v1_tables = await asyncio.gather(v2_coro, v1_coro)
        else:
            v1_tables = await self.collect_tables(
                base_path, query, max_tables=max_tables,
            )

        # Merge and deduplicate (prefer v1 entries — they have breadcrumbs)
        seen_ids: set[str] = set()
        tables: list[ScbTable] = []
        for table in [*v1_tables, *v2_tables]:
            if table.id not in seen_ids:
                seen_ids.add(table.id)
                tables.append(table)

        if not tables:
            return None, []

        # --- Build scoring tokens ------------------------------------------
        # Raw query tokens are the primary signal; scoring_hint tokens give
        # a secondary boost so that domain-specific tables rank higher.
        query_tokens = set(_tokenize(query))
        hint_tokens = set(_tokenize(scoring_hint)) - query_tokens if scoring_hint else set()
        combined_tokens = query_tokens | hint_tokens

        query_norm = _normalize_text(query)
        requested_years = _extract_years(query)
        wants_region = _has_region_request(query_tokens, query_norm)
        wants_gender = _has_gender_request(query_tokens, query_norm)
        wants_age = _has_age_request(query_tokens, query_norm)

        def rank(table: ScbTable) -> tuple[int, float]:
            breadcrumb_text = " ".join(table.breadcrumb)
            full_text = f"{table.title} {breadcrumb_text} {table.id}"
            # Primary: raw query match; secondary: hint match (weighted lower)
            raw_score = _score_text(query_tokens, full_text)
            hint_score = _score_text(hint_tokens, full_text) if hint_tokens else 0
            score = raw_score * 2 + hint_score
            updated = _parse_iso(table.updated)
            return (score, updated.timestamp() if updated else 0.0)

        tables.sort(key=rank, reverse=True)
        top_candidates = tables[:metadata_limit]

        async def _fetch_metadata_safe(table: ScbTable) -> dict[str, Any]:
            try:
                return await self.get_table_metadata(table.path)
            except httpx.HTTPError:
                return {}

        metadatas = await asyncio.gather(
            *(_fetch_metadata_safe(t) for t in top_candidates)
        )

        scored: list[tuple[ScbTable, float]] = []
        for table, metadata in zip(top_candidates, metadatas, strict=False):
            base_score = rank(table)[0]
            meta_score = _score_table_metadata(
                metadata=metadata,
                query_tokens=combined_tokens,
                query_norm=query_norm,
                requested_years=requested_years,
                wants_region=wants_region,
                wants_gender=wants_gender,
                wants_age=wants_age,
            )
            scored.append((table, float(base_score + meta_score)))

        if not scored:
            return None, []

        scored.sort(key=lambda item: item[1], reverse=True)
        best_table = scored[0][0]
        candidates = [item[0] for item in scored[1 : candidate_limit + 1]]
        return best_table, candidates

    async def find_best_table(
        self,
        base_path: str,
        query: str,
        *,
        max_tables: int = 80,
        metadata_limit: int = 10,
    ) -> ScbTable | None:
        best_table, _ = await self.find_best_table_candidates(
            base_path,
            query,
            max_tables=max_tables,
            metadata_limit=metadata_limit,
        )
        return best_table

    # -- Codelist Integration (#16) -----------------------------------------

    async def get_codelist(self, codelist_id: str, *, lang: str = "sv") -> dict[str, Any]:
        """Fetch a codelist via v2 GET /codelists/{id}.

        Codelists provide centralised value mappings (e.g. region codes →
        names) that can be reused across multiple tables.  Only available
        on v2.
        """
        if not self._is_v2:
            return {}

        cache_key = f"cl:{codelist_id}:{lang}"
        async with self._cache_lock:
            if cache_key in self._codelist_cache:
                return dict(self._codelist_cache[cache_key])

        url = f"{self.base_url}codelists/{url_quote(codelist_id, safe='')}"
        try:
            data = await self._get_json(url, params={"lang": lang})
        except httpx.HTTPError as exc:
            logger.warning("codelist fetch failed for %s: %s", codelist_id, exc)
            return {}

        if not isinstance(data, dict):
            return {}

        async with self._cache_lock:
            self._codelist_cache[cache_key] = data
        return data

    # -- Data Retrieval -----------------------------------------------------

    async def query_table(
        self,
        table_path: str,
        payload: dict[str, Any],
        *,
        output_format: str = "json-stat2",
    ) -> dict[str, Any]:
        """Execute a data query. Uses v2 or v1 format automatically.

        Args:
            table_path: Table ID (v2) or path (v1).
            payload: Query payload in v1 or v2 format.
            output_format: Response format — 'json-stat2' (default), 'csv',
                'xlsx', 'parquet', 'html', 'px', 'json-px'.  Non-json formats
                only supported on v2.
        """
        if self._is_v2:
            return await self._query_table_v2(table_path, payload, output_format=output_format)
        return await self._query_table_v1(table_path, payload)

    async def _query_table_v2(
        self,
        table_id: str,
        payload: dict[str, Any],
        *,
        output_format: str = "json-stat2",
    ) -> dict[str, Any]:
        clean_id = table_id.strip("/")
        url = f"{self.base_url}tables/{url_quote(clean_id, safe='')}/data"

        # Convert v1 payload format to v2 if needed
        v2_payload = self._convert_payload_to_v2(payload)

        # Remove outputFormat from body — v2 API requires it as a query param
        v2_payload.pop("outputFormat", None)

        query_params: dict[str, str] = {"lang": "sv"}
        if output_format and output_format in SCB_OUTPUT_FORMATS:
            query_params["outputFormat"] = output_format

        data = await self._post_json(url, v2_payload, params=query_params)
        if isinstance(data, dict):
            return data
        return {"data": data}

    async def _query_table_v1(self, table_path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._build_url(table_path, trailing=False)
        data = await self._post_json(url, payload)
        if isinstance(data, dict):
            return data
        return {"data": data}

    @staticmethod
    def _convert_payload_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
        """Convert v1 query[] format to v2 selection[] format."""
        # If already in v2 format, return as-is
        if "selection" in payload:
            return payload

        v1_query = payload.get("query") or []
        selection: list[dict[str, Any]] = []
        for item in v1_query:
            code = item.get("code", "")
            values = item.get("selection", {}).get("values", [])
            selection.append({
                "variableCode": code,
                "valueCodes": values,
            })

        v2_payload: dict[str, Any] = {"selection": selection}
        output_format = (payload.get("response") or {}).get("format", "json-stat2")
        v2_payload["outputFormat"] = output_format
        return v2_payload

    # -- Query Building -----------------------------------------------------

    def build_query_payloads(
        self,
        metadata: dict[str, Any],
        query: str,
        *,
        max_cells: int | None = None,
        max_values_per_variable: int = 6,
        max_batches: int = 8,
    ) -> tuple[list[dict[str, Any]], list[str], list[str], list[list[str]]]:
        effective_max_cells = max_cells if max_cells is not None else self.max_cells
        selections, summary = self._build_selections(
            metadata,
            query,
            max_values_per_variable=max_values_per_variable,
        )
        if not selections:
            return [], [], ["No selectable variables found in SCB metadata."], []

        batches, warnings = self._split_selection_batches(
            selections,
            max_cells=effective_max_cells,
            max_batches=max_batches,
        )
        if len(batches) > 1:
            warnings.append(
                f"Split into {len(batches)} requests to stay under {effective_max_cells} cells."
            )

        payloads = [self._payload_from_selections(batch) for batch in batches]
        batch_summaries = [self._format_selection_summary(batch) for batch in batches]
        return payloads, summary, warnings, batch_summaries

    def build_query_payload(
        self,
        metadata: dict[str, Any],
        query: str,
        *,
        max_cells: int | None = None,
        max_values_per_variable: int = 6,
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        effective_max_cells = max_cells if max_cells is not None else self.max_cells
        payloads, summary, warnings, _ = self.build_query_payloads(
            metadata,
            query,
            max_cells=effective_max_cells,
            max_values_per_variable=max_values_per_variable,
            max_batches=1,
        )
        if not payloads:
            return {}, summary, warnings
        return payloads[0], summary, warnings

    def _build_selections(
        self,
        metadata: dict[str, Any],
        query: str,
        *,
        max_values_per_variable: int = 6,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        variables = metadata.get("variables") or []
        if not isinstance(variables, list):
            variables = []

        query_norm = _normalize_text(query)
        query_tokens = set(query_norm.split())
        years = _extract_years(query)

        selections: list[dict[str, Any]] = []

        for var in variables:
            code = str(var.get("code") or "")
            label = str(var.get("text") or code)
            values = [str(v) for v in (var.get("values") or []) if v is not None]
            value_texts = [
                str(v) for v in (var.get("valueTexts") or []) if v is not None
            ]

            explicit = False
            selected: list[str] = []

            if not values:
                continue

            if _is_time_variable(code, label):
                if years:
                    for year in years:
                        for value in values:
                            if value.startswith(year):
                                selected.append(value)
                    selected = list(dict.fromkeys(selected))
                    explicit = bool(selected)
                if not selected:
                    selected = values[-max_values_per_variable:]
            elif _is_region_variable(code, label):
                selected = _match_values_by_text(
                    values, value_texts, query_norm, query_tokens
                )
                explicit = bool(selected)
                if not selected:
                    selected = _pick_preferred_value(
                        values, value_texts, ["riket", "sverige"]
                    )
            elif _is_gender_variable(code, label):
                if any(token.startswith("kvin") for token in query_tokens):
                    selected = _match_values_by_text(values, value_texts, "kvin", {"kvin"})
                elif any(token.startswith("man") or token.startswith("male") for token in query_tokens):
                    selected = _match_values_by_text(values, value_texts, "man", {"man"})
                if not selected:
                    selected = _pick_preferred_value(values, value_texts, ["tot", "total"])
                explicit = bool(selected)
            elif _is_age_variable(code, label):
                selected = _match_values_by_text(
                    values, value_texts, query_norm, query_tokens
                )
                explicit = bool(selected)
                if not selected:
                    selected = _pick_preferred_value(values, value_texts, ["tot", "total"])
            else:
                selected = _match_values_by_text(
                    values, value_texts, query_norm, query_tokens
                )
                explicit = bool(selected)
                if not selected:
                    selected = _pick_preferred_value(
                        values, value_texts, ["tot", "total", "alla"]
                    )

            if not selected:
                selected = values[:1]

            if len(selected) > max_values_per_variable:
                selected = selected[:max_values_per_variable]

            selections.append(
                {
                    "code": code,
                    "label": label,
                    "values": selected,
                    "value_texts": value_texts,
                    "explicit": explicit,
                    "is_time": _is_time_variable(code, label),
                    "is_region": _is_region_variable(code, label),
                }
            )

        return selections, self._format_selection_summary(selections)

    def _format_selection_summary(self, selections: list[dict[str, Any]]) -> list[str]:
        summaries: list[str] = []
        for selection in selections:
            label = selection.get("label", "")
            value_texts = selection.get("value_texts") or []
            text_map = dict(zip(selection.get("values") or [], value_texts, strict=False))
            display = [text_map.get(value, value) for value in selection.get("values") or []]
            if display and label:
                summaries.append(f"{label}: {', '.join(display)}")
        return summaries

    def _payload_from_selections(
        self, selections: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if self._is_v2:
            return self._payload_from_selections_v2(selections)
        return self._payload_from_selections_v1(selections)

    @staticmethod
    def _payload_from_selections_v1(
        selections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "query": [
                {
                    "code": sel["code"],
                    "selection": {"filter": "item", "values": sel["values"]},
                }
                for sel in selections
                if sel.get("values")
            ],
            "response": {"format": "json-stat2"},
        }

    @staticmethod
    def _payload_from_selections_v2(
        selections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "selection": [
                {
                    "variableCode": sel["code"],
                    "valueCodes": sel["values"],
                }
                for sel in selections
                if sel.get("values")
            ],
        }

    def _selection_cell_count(self, selections: list[dict[str, Any]]) -> int:
        """Count total cells as product of all value-list lengths.

        Returns 0 if any variable has zero values (BUG-5 fix).
        """
        lengths = [len(sel.get("values") or []) for sel in selections]
        if not lengths or any(n == 0 for n in lengths):
            return 0
        return prod(lengths)

    def _choose_split_index(
        self, selections: list[dict[str, Any]]
    ) -> int | None:
        candidates = [
            idx
            for idx, sel in enumerate(selections)
            if len(sel.get("values") or []) > 1
        ]
        if not candidates:
            return None
        time_candidates = [idx for idx in candidates if selections[idx].get("is_time")]
        if time_candidates:
            return time_candidates[0]
        region_candidates = [
            idx for idx in candidates if selections[idx].get("is_region")
        ]
        if region_candidates:
            return region_candidates[0]
        return max(candidates, key=lambda idx: len(selections[idx].get("values") or []))

    def _split_selection_batches(
        self,
        selections: list[dict[str, Any]],
        *,
        max_cells: int,
        max_batches: int,
    ) -> tuple[list[list[dict[str, Any]]], list[str]]:
        warnings: list[str] = []
        batches: list[list[dict[str, Any]]] = []
        pending: list[list[dict[str, Any]]] = [selections]

        while pending:
            current = pending.pop(0)
            total_cells = self._selection_cell_count(current)
            if total_cells <= max_cells:
                batches.append(current)
                if len(batches) >= max_batches:
                    break
                continue

            split_idx = self._choose_split_index(current)
            if split_idx is None:
                warnings.append(
                    "Selection exceeds cell limit; please narrow the query."
                )
                batches.append(current)
                break

            values = list(current[split_idx].get("values") or [])
            if len(values) <= 1:
                warnings.append(
                    "Selection exceeds cell limit; please narrow the query."
                )
                batches.append(current)
                break

            other_prod = 1
            for idx, sel in enumerate(current):
                if idx == split_idx:
                    continue
                other_prod *= max(len(sel.get("values") or []), 1)
            max_chunk = max(1, max_cells // max(other_prod, 1))
            if max_chunk >= len(values):
                max_chunk = max(1, len(values) // 2)

            chunks = [
                values[i : i + max_chunk] for i in range(0, len(values), max_chunk)
            ]
            for chunk in chunks:
                next_sel = [dict(sel) for sel in current]
                next_sel[split_idx] = {**current[split_idx], "values": chunk}
                pending.append(next_sel)
                if len(batches) + len(pending) > max_batches:
                    break
            if len(batches) + len(pending) > max_batches:
                break

        if pending and len(batches) >= max_batches:
            warnings.append(
                f"Too many batches requested; returning first {max_batches} batches."
            )
        return batches[:max_batches], warnings
