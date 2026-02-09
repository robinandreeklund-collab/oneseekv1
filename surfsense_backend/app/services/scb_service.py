from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, UTC
from math import prod
from typing import Any

import httpx

SCB_BASE_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/"
SCB_MAX_CELLS = 150_000

_DIACRITIC_MAP = str.maketrans(
    {
        "å": "a",
        "ä": "a",
        "ö": "o",
        "Å": "a",
        "Ä": "a",
        "Ö": "o",
    }
)


@dataclass(frozen=True)
class ScbTable:
    id: str
    path: str
    title: str
    updated: str | None = None
    breadcrumb: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScbQueryResult:
    table: ScbTable
    payload: dict[str, Any]
    data: dict[str, Any]
    selection_summary: list[str]
    warnings: list[str]


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower().translate(_DIACRITIC_MAP)
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_text(text)
    return [token for token in normalized.split() if token]


def _score_text(query_tokens: set[str], text: str) -> int:
    normalized = _normalize_text(text)
    if not normalized:
        return 0
    score = 0
    for token in query_tokens:
        if token and token in normalized:
            score += 1
    return score


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
        if normalized in query_norm:
            matches.append(value)
            continue
        tokens = set(normalized.split())
        if tokens and tokens.issubset(query_tokens):
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


class ScbService:
    def __init__(self, base_url: str = SCB_BASE_URL, timeout: float = 25.0) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self._node_cache: dict[str, list[dict[str, Any]]] = {}

    def _build_url(self, path: str, *, trailing: bool) -> str:
        cleaned = (path or "").lstrip("/")
        url = f"{self.base_url}{cleaned}"
        if trailing and not url.endswith("/"):
            url += "/"
        return url

    async def _get_json(self, url: str) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def _post_json(self, url: str, payload: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def list_nodes(self, path: str) -> list[dict[str, Any]]:
        url = self._build_url(path, trailing=True)
        if url in self._node_cache:
            return list(self._node_cache[url])
        data = await self._get_json(url)
        if not isinstance(data, list):
            return []
        self._node_cache[url] = data
        return list(data)

    async def get_table_metadata(self, table_path: str) -> dict[str, Any]:
        url = self._build_url(table_path, trailing=False)
        data = await self._get_json(url)
        if isinstance(data, dict):
            return data
        return {}

    async def query_table(self, table_path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._build_url(table_path, trailing=False)
        data = await self._post_json(url, payload)
        if isinstance(data, dict):
            return data
        return {"data": data}

    async def collect_tables(
        self,
        base_path: str,
        query: str,
        *,
        max_tables: int = 80,
        max_depth: int = 4,
        max_nodes: int = 140,
        max_children: int = 8,
    ) -> list[ScbTable]:
        query_tokens = set(_tokenize(query))
        queue: list[tuple[str, int, tuple[str, ...]]] = [
            (base_path.rstrip("/") + "/", 0, ())
        ]
        seen: set[str] = set()
        tables: list[ScbTable] = []

        while queue and len(tables) < max_tables and len(seen) < max_nodes:
            current_path, depth, breadcrumb = queue.pop(0)
            if current_path in seen:
                continue
            seen.add(current_path)

            try:
                items = await self.list_nodes(current_path)
            except httpx.HTTPError:
                continue

            children: list[tuple[int, str, int, tuple[str, ...]]] = []
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
                    children.append((score, next_path, depth + 1, next_breadcrumb))

            if children:
                children.sort(key=lambda item: item[0], reverse=True)
                if depth <= 1:
                    selected = children
                else:
                    selected = [child for child in children if child[0] > 0]
                    if len(selected) < max_children:
                        selected = children[:max_children]
                queue.extend(selected)

        return tables

    async def find_best_table(
        self,
        base_path: str,
        query: str,
        *,
        max_tables: int = 80,
        metadata_limit: int = 10,
    ) -> ScbTable | None:
        tables = await self.collect_tables(base_path, query, max_tables=max_tables)
        if not tables:
            return None
        query_tokens = set(_tokenize(query))
        query_norm = _normalize_text(query)
        requested_years = _extract_years(query)
        wants_region = _has_region_request(query_tokens, query_norm)
        wants_gender = _has_gender_request(query_tokens, query_norm)
        wants_age = _has_age_request(query_tokens, query_norm)

        def rank(table: ScbTable) -> tuple[int, float]:
            breadcrumb_text = " ".join(table.breadcrumb)
            score = _score_text(
                query_tokens, f"{table.title} {breadcrumb_text} {table.id}"
            )
            updated = _parse_iso(table.updated)
            return (score, updated.timestamp() if updated else 0.0)

        tables.sort(key=rank, reverse=True)
        top_candidates = tables[:metadata_limit]
        best_table = tables[0]
        best_score = rank(best_table)[0]

        for table in top_candidates:
            try:
                metadata = await self.get_table_metadata(table.path)
            except httpx.HTTPError:
                continue
            meta_score = _score_table_metadata(
                metadata=metadata,
                query_tokens=query_tokens,
                query_norm=query_norm,
                requested_years=requested_years,
                wants_region=wants_region,
                wants_gender=wants_gender,
                wants_age=wants_age,
            )
            total_score = rank(table)[0] + meta_score
            if total_score > best_score:
                best_score = total_score
                best_table = table

        return best_table

    def build_query_payload(
        self,
        metadata: dict[str, Any],
        query: str,
        *,
        max_cells: int = SCB_MAX_CELLS,
        max_values_per_variable: int = 6,
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        variables = metadata.get("variables") or []
        if not isinstance(variables, list):
            variables = []

        query_norm = _normalize_text(query)
        query_tokens = set(query_norm.split())
        years = _extract_years(query)

        selections: list[dict[str, Any]] = []
        summaries: list[str] = []
        warnings: list[str] = []

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
                selected = _match_values_by_text(values, value_texts, query_norm, query_tokens)
                explicit = bool(selected)
                if not selected:
                    selected = _pick_preferred_value(values, value_texts, ["riket", "sverige"])
            elif _is_gender_variable(code, label):
                if any(token.startswith("kvin") for token in query_tokens):
                    selected = _match_values_by_text(values, value_texts, "kvin", {"kvin"})
                elif any(token.startswith("man") or token.startswith("male") for token in query_tokens):
                    selected = _match_values_by_text(values, value_texts, "man", {"man"})
                if not selected:
                    selected = _pick_preferred_value(values, value_texts, ["tot", "total"])
                explicit = bool(selected)
            elif _is_age_variable(code, label):
                selected = _match_values_by_text(values, value_texts, query_norm, query_tokens)
                explicit = bool(selected)
                if not selected:
                    selected = _pick_preferred_value(values, value_texts, ["tot", "total"])
            else:
                selected = _match_values_by_text(values, value_texts, query_norm, query_tokens)
                explicit = bool(selected)
                if not selected:
                    selected = _pick_preferred_value(values, value_texts, ["tot", "total", "alla"])

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
                }
            )

        def cell_count() -> int:
            lengths = [max(len(sel["values"]), 1) for sel in selections]
            return prod(lengths) if lengths else 0

        total_cells = cell_count()
        if total_cells > max_cells:
            warnings.append(
                f"Estimated {total_cells} cells; trimming selection to stay under {max_cells}."
            )

            selections.sort(key=lambda item: len(item["values"]), reverse=True)
            for selection in selections:
                if total_cells <= max_cells:
                    break
                if selection["explicit"] and any(
                    len(other["values"]) > 1 and not other["explicit"]
                    for other in selections
                ):
                    continue
                if len(selection["values"]) > 1:
                    selection["values"] = selection["values"][:1]
                    total_cells = cell_count()

        if total_cells > max_cells:
            warnings.append(
                "Selection still exceeds cell limit; consider narrowing the query."
            )

        query_payload = {
            "query": [
                {
                    "code": sel["code"],
                    "selection": {"filter": "item", "values": sel["values"]},
                }
                for sel in selections
            ],
            "response": {"format": "json-stat2"},
        }

        for selection in selections:
            label = selection["label"]
            value_texts = selection["value_texts"]
            text_map = {val: text for val, text in zip(selection["values"], value_texts, strict=False)}
            display = [text_map.get(value, value) for value in selection["values"]]
            if display:
                summaries.append(f"{label}: {', '.join(display)}")

        return query_payload, summaries, warnings
