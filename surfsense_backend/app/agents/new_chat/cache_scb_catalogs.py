"""SCB Table Catalog Cache — pre-fetches table metadata for all domains.

At startup (or on first use), fetches table metadata for each SCB domain tool
so that the LLM can choose the correct table directly from the system prompt
instead of doing multi-step tool calls (search → inspect → codelist → ...).

Cached per tool_id:
- table_id, title
- ContentsCode labels (measures)
- Variable summaries (region count, time range, etc.)

TTL: 24 hours (configurable via SCB_CATALOG_TTL env var).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from cachetools import TTLCache

from app.agents.new_chat.scb_tool_definitions import (
    SCB_TOOL_DEFINITIONS,
    ScbToolDefinition,
)
from app.services.scb_regions import (
    find_region_fuzzy,
    format_region_for_llm,
    normalize_diacritik,
)
from app.services.scb_service import (
    ScbService,
    _is_age_variable,
    _is_gender_variable,
    _is_region_variable,
    _is_time_variable,
)

logger = logging.getLogger(__name__)

SCB_CATALOG_TTL = int(os.getenv("SCB_CATALOG_TTL", "86400"))  # 24h default

# ASCII→Swedish diacritics mapping for keywords that were stored without åäö.
# SCB v2 search requires proper Swedish characters to match.
_DIACRITICS_MAP: dict[str, str] = {
    "arbetsloshet": "arbetslöshet",
    "sysselsattning": "sysselsättning",
    "lon": "lön",
    "loner": "löner",
    "lonestruktur": "lönestruktur",
    "folkmangd": "folkmängd",
    "fodd": "född",
    "fodda": "födda",
    "dod": "död",
    "alder": "ålder",
    "kon": "kön",
    "foraldrar": "föräldrar",
    "naring": "näring",
    "utbildningsniva": "utbildningsnivå",
    "forandringar": "förändringar",
    "forandring": "förändring",
    "miljo": "miljö",
    "utslapp": "utsläpp",
    "energiforsorjning": "energiförsörjning",
    "utrikeshandel": "utrikeshandel",
    "lan": "län",
    "invanare": "invånare",
    "netto": "netto",
    "halsa": "hälsa",
    "sjukvard": "sjukvård",
    "aldreomsorgen": "äldreomsorgen",
    "bostader": "bostäder",
    "nybyggnation": "nybyggnation",
    "fritidshus": "fritidshus",
    "detaljhandel": "detaljhandel",
    "konsumentpris": "konsumentpris",
    "inflation": "inflation",
}


def _restore_diacritics(keyword: str) -> str:
    """Restore Swedish diacritics for an ASCII keyword."""
    return _DIACRITICS_MAP.get(keyword.lower(), keyword)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CachedVariable:
    """Compact summary of a table variable for the catalog prompt."""

    code: str
    label: str
    var_type: str  # "time" | "region" | "gender" | "age" | "measure" | "other"
    total_values: int
    summary: str  # e.g. "2005-2024 (20 perioder)" or "290 kommuner + 21 län"
    values_sample: list[dict[str, str]] = field(default_factory=list)
    eliminable: bool = False


@dataclass
class CachedTable:
    """Compact table entry for the catalog prompt."""

    table_id: str
    title: str
    path: str
    variables: list[CachedVariable] = field(default_factory=list)
    contents_labels: list[str] = field(default_factory=list)  # ContentsCode labels


@dataclass
class DomainCatalog:
    """All cached tables for a single SCB domain tool."""

    tool_id: str
    domain_name: str
    base_path: str
    tables: list[CachedTable] = field(default_factory=list)
    fetched_at: float = 0.0


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

# tool_id -> DomainCatalog
_catalog_cache: TTLCache[str, DomainCatalog] = TTLCache(
    maxsize=100, ttl=SCB_CATALOG_TTL
)
_cache_lock = asyncio.Lock()
_build_lock = asyncio.Lock()  # prevents concurrent builds


# ---------------------------------------------------------------------------
# Variable summarization
# ---------------------------------------------------------------------------


def _summarize_variable(var: dict[str, Any]) -> CachedVariable:
    """Create a compact variable summary from raw SCB metadata."""
    code = str(var.get("code") or "")
    label = str(var.get("text") or code)
    values = [str(v) for v in (var.get("values") or []) if v is not None]
    value_texts = [str(v) for v in (var.get("valueTexts") or []) if v is not None]
    total = len(values)
    eliminable = var.get("elimination", False)

    # Detect type
    var_type = "other"
    if _is_time_variable(code, label):
        var_type = "time"
    elif _is_region_variable(code, label):
        var_type = "region"
    elif _is_gender_variable(code, label):
        var_type = "gender"
    elif _is_age_variable(code, label):
        var_type = "age"
    elif code.lower() in ("contentscode", "contents"):
        var_type = "measure"

    # Build summary string
    summary = ""
    sample: list[dict[str, str]] = []

    if var_type == "time" and values:
        summary = f"{values[0]}\u2013{values[-1]} ({total} perioder)"
    elif var_type == "region":
        n_kommun = sum(1 for v in values if len(v) == 4 and v.isdigit())
        n_lan = sum(1 for v in values if len(v) == 2 and v.isdigit())
        parts = []
        if n_kommun:
            parts.append(f"{n_kommun} kommuner")
        if n_lan:
            parts.append(f"{n_lan} l\u00e4n")
        if "00" in values:
            parts.append("Riket")
        summary = " + ".join(parts) if parts else f"{total} regioner"
    elif var_type == "gender":
        labels = ", ".join(
            f"{v}={t}" for v, t in zip(values, value_texts, strict=False)
        )
        summary = labels or f"{total} v\u00e4rden"
    elif var_type == "age":
        if values:
            summary = f"{total} \u00e5ldersgrupper ({values[0]}\u2013{values[-1]})"
        else:
            summary = f"{total} \u00e5ldersgrupper"
    elif var_type == "measure":
        # Show ALL measure labels — this is the critical info
        for v, t in zip(values, value_texts, strict=False):
            sample.append({"code": v, "label": t})
        summary = f"{total} m\u00e5tt"
    else:
        if total <= 10:
            labels = ", ".join(
                f"{v}={t}" for v, t in zip(values, value_texts, strict=False)
            )
            summary = labels
        else:
            summary = f"{total} v\u00e4rden"

    return CachedVariable(
        code=code,
        label=label,
        var_type=var_type,
        total_values=total,
        summary=summary,
        values_sample=sample,
        eliminable=eliminable,
    )


# ---------------------------------------------------------------------------
# Table discovery and caching
# ---------------------------------------------------------------------------


async def _discover_tables_for_domain(
    service: ScbService,
    definition: ScbToolDefinition,
) -> list[CachedTable]:
    """Discover all tables under a domain and fetch their metadata."""
    from app.services.scb_service import ScbTable

    # Use both v2 search and v1 tree traversal for maximum coverage
    all_tables: list[ScbTable] = []
    seen_ids: set[str] = set()

    # v1 tree traversal (scoped to base_path) — generous limits for caching
    try:
        v1_tables = await service.collect_tables(
            definition.base_path,
            " ".join(definition.keywords),
            max_tables=200,
            max_nodes=300,
            max_children=20,
            max_depth=5,
            total_timeout=120.0,
        )
        for t in v1_tables:
            if t.id not in seen_ids:
                all_tables.append(t)
                seen_ids.add(t.id)
    except Exception as exc:
        logger.warning("v1 tree traversal failed for %s: %s", definition.base_path, exc)

    # v2 search with domain keywords
    # search_tables now builds v1-style paths from the v2 paths hierarchy,
    # so path.startswith(base_path) works for both broad ("BE/") and
    # sub-domain ("BE/BE0101/BE0101A/") definitions.
    if hasattr(service, "search_tables"):
        # Deduplicate keywords after diacritics restoration
        search_keywords: list[str] = []
        seen_kw: set[str] = set()
        for kw in definition.keywords[:5]:
            restored = _restore_diacritics(kw)
            if restored.lower() not in seen_kw:
                seen_kw.add(restored.lower())
                search_keywords.append(restored)
            # Also try the original if different
            if kw.lower() not in seen_kw:
                seen_kw.add(kw.lower())
                search_keywords.append(kw)
        for kw in search_keywords:
            try:
                v2_tables = await service.search_tables(kw, limit=50)
                for t in v2_tables:
                    if t.id not in seen_ids:
                        if t.path and t.path.startswith(definition.base_path):
                            all_tables.append(t)
                            seen_ids.add(t.id)
                        elif not t.path:
                            all_tables.append(t)
                            seen_ids.add(t.id)
            except Exception:
                pass

    logger.info(
        "Discovered %d tables for %s (%s)",
        len(all_tables),
        definition.tool_id,
        definition.base_path,
    )

    # Fetch metadata for all discovered tables (with concurrency limit)
    semaphore = asyncio.Semaphore(5)
    cached_tables: list[CachedTable] = []

    async def _fetch_meta(table: ScbTable) -> CachedTable | None:
        async with semaphore:
            try:
                # For v2, use table.id (e.g. "TAB4552") not table.path
                # (which is now a domain hierarchy like "BE/BE0101/...")
                meta_key = table.id if service._is_v2 else (table.path or table.id)
                metadata = await service.get_table_metadata(meta_key)
                if not metadata or not metadata.get("variables"):
                    return None

                variables = [
                    _summarize_variable(var) for var in metadata.get("variables", [])
                ]

                # Extract ContentsCode labels
                contents_labels: list[str] = []
                for var in metadata.get("variables", []):
                    code = str(var.get("code") or "").lower()
                    if code in ("contentscode", "contents"):
                        value_texts = [str(v) for v in (var.get("valueTexts") or [])]
                        contents_labels = value_texts

                return CachedTable(
                    table_id=table.id,
                    title=getattr(table, "title", table.id),
                    path=getattr(table, "path", table.id),
                    variables=variables,
                    contents_labels=contents_labels,
                )
            except Exception as exc:
                logger.debug("Failed to fetch metadata for %s: %s", table.id, exc)
                return None

    results = await asyncio.gather(
        *(_fetch_meta(t) for t in all_tables),
        return_exceptions=True,
    )

    for r in results:
        if isinstance(r, CachedTable):
            cached_tables.append(r)

    return cached_tables


async def build_domain_catalog(
    service: ScbService,
    definition: ScbToolDefinition,
) -> DomainCatalog:
    """Build and cache the catalog for a single domain."""
    tables = await _discover_tables_for_domain(service, definition)
    catalog = DomainCatalog(
        tool_id=definition.tool_id,
        domain_name=definition.name,
        base_path=definition.base_path,
        tables=tables,
        fetched_at=time.time(),
    )
    async with _cache_lock:
        _catalog_cache[definition.tool_id] = catalog
    return catalog


async def get_domain_catalog(
    definition: ScbToolDefinition,
    service: ScbService | None = None,
) -> DomainCatalog:
    """Get cached catalog, building it on first access."""
    async with _cache_lock:
        cached = _catalog_cache.get(definition.tool_id)
        if cached is not None:
            return cached

    # Build catalog (with lock to prevent concurrent builds for same domain)
    svc = service or ScbService()
    async with _build_lock:
        # Double-check after acquiring lock
        async with _cache_lock:
            cached = _catalog_cache.get(definition.tool_id)
            if cached is not None:
                return cached
        return await build_domain_catalog(svc, definition)


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def format_catalog_for_prompt(
    catalog: DomainCatalog,
    user_query: str = "",
) -> str:
    """Format a domain catalog as a compact text block for the system prompt.

    Includes ContentsCode labels and variable summaries so the LLM can
    pick the right table without extra tool calls.
    """
    if not catalog.tables:
        return f"Domän: {catalog.domain_name} ({catalog.base_path})\nInga tabeller hittades."

    lines: list[str] = []
    lines.append(f"## Tabellkatalog: {catalog.domain_name}")
    lines.append(f"Domänväg: {catalog.base_path}")
    lines.append(f"Antal tabeller: {len(catalog.tables)}")
    lines.append(
        "OBS: Använd TAB-koderna nedan (t.ex. TAB2910) som table_id i "
        "scb_validate/scb_fetch — INTE domänvägen."
    )
    lines.append("")

    for table in catalog.tables:
        lines.append(f"### {table.table_id}: {table.title}")

        # ContentsCode (measures) — the most critical info
        if table.contents_labels:
            measures = "; ".join(
                f"{sv['code']}={sv['label']}"
                for var in table.variables
                if var.var_type == "measure"
                for sv in var.values_sample
            )
            if measures:
                lines.append(f"  Mått: {measures}")
            else:
                lines.append(f"  Mått: {', '.join(table.contents_labels)}")

        # Variable summaries
        for var in table.variables:
            if var.var_type == "measure":
                continue  # Already shown above
            elim = " (kan utelämnas)" if var.eliminable else ""
            lines.append(f"  {var.code} ({var.label}): {var.summary}{elim}")

        lines.append("")

    return "\n".join(lines)


def resolve_regions_for_prompt(user_query: str) -> str:
    """Extract region references from the query and resolve to SCB codes.

    Returns a compact string like:
      Regionkoder: 1280=Malmö (kommun), 12=Skåne län (län)
    """
    # Extract potential region words from query
    words = user_query.lower().split()
    # Also try multi-word combinations (e.g. "Västra Götaland")
    bigrams = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]

    resolved: list[str] = []
    seen_codes: set[str] = set()

    for term in words + bigrams:
        # Skip very short or common words
        if len(term) < 3:
            continue
        norm = normalize_diacritik(term)
        if norm in {
            "per",
            "for",
            "och",
            "med",
            "den",
            "det",
            "hur",
            "vad",
            "som",
            "att",
            "till",
            "lan",
            "kommun",
            "region",
            "riket",
            "sverige",
        }:
            continue

        regions = find_region_fuzzy(term)
        for r in regions[:2]:  # Max 2 matches per term
            if r.code not in seen_codes:
                resolved.append(format_region_for_llm(r))
                seen_codes.add(r.code)

    if not resolved:
        return ""

    return "Regionkoder: " + ", ".join(resolved)


# ---------------------------------------------------------------------------
# Background pre-warm (optional)
# ---------------------------------------------------------------------------


async def prewarm_catalogs(
    service: ScbService | None = None,
    tool_ids: list[str] | None = None,
) -> dict[str, int]:
    """Pre-warm catalogs for specified tools (or all).

    Returns dict of tool_id -> number of tables cached.
    """
    svc = service or ScbService()
    targets = SCB_TOOL_DEFINITIONS
    if tool_ids:
        id_set = set(tool_ids)
        targets = [d for d in SCB_TOOL_DEFINITIONS if d.tool_id in id_set]

    results: dict[str, int] = {}
    for definition in targets:
        try:
            catalog = await build_domain_catalog(svc, definition)
            results[definition.tool_id] = len(catalog.tables)
            logger.info(
                "Pre-warmed %s: %d tables", definition.tool_id, len(catalog.tables)
            )
        except Exception as exc:
            logger.warning("Failed to pre-warm %s: %s", definition.tool_id, exc)
            results[definition.tool_id] = 0

    return results


# ---------------------------------------------------------------------------
# Table-ID resolution — auto-correct common LLM mistakes
# ---------------------------------------------------------------------------


def resolve_table_id(raw_table_id: str) -> str | None:
    """Try to resolve a wrong table_id to the correct one using cached catalogs.

    Common LLM mistakes:
    - Using a ContentsCode (e.g. ``BE0101N1``) instead of table_id (``TAB638``)
    - Using a path segment (e.g. ``BE0101A``) instead of table_id
    - Using the domain base_path (e.g. ``BE0101``)

    Returns the corrected table_id if found, or ``None`` if no match.
    """
    raw = (raw_table_id or "").strip()
    if not raw:
        return None

    raw_upper = raw.upper()
    raw_lower = raw.lower()

    # Walk all cached catalogs
    for catalog in _catalog_cache.values():
        if not isinstance(catalog, DomainCatalog):
            continue
        for table in catalog.tables:
            # Direct match — already correct
            if table.table_id.upper() == raw_upper:
                return table.table_id

            # Match by ContentsCode (e.g. "BE0101N1" → TAB638)
            for var in table.variables:
                if var.var_type == "measure":
                    for sample in var.values_sample:
                        code = str(sample.get("code") or "").strip()
                        if code and code.upper() == raw_upper:
                            return table.table_id

            # Match by path segment (e.g. "BE0101A" appearing in table.path)
            if raw_lower in table.path.lower():
                return table.table_id

        # Match by domain base_path (e.g. "BE0101" → first table in domain)
        base_clean = catalog.base_path.strip("/").replace("/", "")
        if raw_upper == base_clean.upper() or raw_lower == catalog.base_path.strip("/").lower():
            if catalog.tables:
                return catalog.tables[0].table_id

    return None
