"""SCB LLM-driven tools — 7-tool pipeline for precision data extraction.

Seven tools that let the LLM navigate, inspect, preview, validate, and
fetch data from SCB (Statistics Sweden) with full control:

Discovery:
1. scb_search        — Fulltext search across SCB tables
2. scb_browse        — Navigate the SCB topic tree step by step

Inspection:
3. scb_inspect       — Full metadata with defaults, hints, codelists
4. scb_codelist      — Fetch a codelist (counties, municipalities, etc.)

Data:
5. scb_preview       — Auto-limited preview (~20 rows)
6. scb_validate      — Dry-run validation with auto-complete
7. scb_fetch         — Fetch data → decoded markdown table
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.tools import tool

from app.agents.new_chat.tools.scb_schemas import (
    ScbBrowseInput,
    ScbCodelistInput,
    ScbFetchInput,
    ScbInspectInput,
    ScbPreviewInput,
    ScbSearchInput,
    ScbValidateInput,
)
from app.services.scb_regions import (
    normalize_diacritik,
    resolve_region_codes,
)
from app.services.scb_service import (
    ScbService,
    _is_age_variable,
    _is_gender_variable,
    _is_region_variable,
    _is_time_variable,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Variable / value translation
# ---------------------------------------------------------------------------

_VARIABLE_ALIASES: dict[str, str] = {
    "year": "Tid",
    "time": "Tid",
    "ar": "Tid",
    "år": "Tid",
    "tid": "Tid",
    "period": "Tid",
    "region": "Region",
    "lan": "Region",
    "län": "Region",
    "kommun": "Region",
    "sex": "Kon",
    "gender": "Kon",
    "kon": "Kon",
    "kön": "Kon",
    "age": "Alder",
    "alder": "Alder",
    "ålder": "Alder",
    "contents": "ContentsCode",
    "matt": "ContentsCode",
    "mått": "ContentsCode",
    "measure": "ContentsCode",
}

_GENDER_ALIASES: dict[str, str] = {
    "male": "1",
    "man": "1",
    "män": "1",
    "female": "2",
    "kvinna": "2",
    "kvinnor": "2",
    "total": "TOT",
    "totalt": "TOT",
    "alla": "TOT",
    "both": "TOT",
    "båda": "TOT",
}

_MAX_VALUES_TO_SHOW = 25


def _coerce_selection(
    selection: dict[str, Any],
) -> dict[str, list[str]]:
    """Coerce selection values to ``list[str]``.

    LLMs frequently pass scalar strings instead of single-element lists.
    This helper silently converts ``"0180"`` → ``["0180"]`` and
    ``"2015-2020"`` year-range strings → ``["2015", "2016", ..., "2020"]``
    so that downstream validation never fails on type alone.
    """
    coerced: dict[str, list[str]] = {}
    for key, val in selection.items():
        if isinstance(val, str):
            val = val.strip()
            # Detect year-range patterns like "2015-2020"
            m = re.match(r"^(\d{4})\s*[-\u2013]\s*(\d{4})$", val)
            if m:
                start, end = int(m.group(1)), int(m.group(2))
                if 1900 <= start <= end <= 2200 and (end - start) <= 100:
                    coerced[key] = [str(y) for y in range(start, end + 1)]
                    continue
            coerced[key] = [val]
        elif isinstance(val, list | tuple):
            # Also expand year-range strings inside lists
            expanded: list[str] = []
            for item in val:
                s = str(item).strip()
                m = re.match(r"^(\d{4})\s*[-\u2013]\s*(\d{4})$", s)
                if m:
                    start, end = int(m.group(1)), int(m.group(2))
                    if 1900 <= start <= end <= 2200 and (end - start) <= 100:
                        expanded.extend(str(y) for y in range(start, end + 1))
                        continue
                expanded.append(s)
            coerced[key] = expanded
        else:
            coerced[key] = [str(val)]
    return coerced


# v2 expression pattern — TOP(n), BOTTOM(n), FROM(x), TO(x), RANGE(x,y), *
_V2_EXPR_RE = re.compile(
    r"^(?:TOP|BOTTOM)\(\d+(?:\s*,\s*\d+)?\)$"
    r"|^(?:FROM|TO)\(.+\)$"
    r"|^RANGE\(.+,.+\)$"
    r"|^\*$"
    r"|^.+\*$"
    r"|^\*.+$"
    r"|^\?+$",
    re.IGNORECASE,
)


def _is_v2_expression(value: str) -> bool:
    """Check if a value is a v2 selection expression (TOP, FROM, etc.)."""
    return bool(_V2_EXPR_RE.match(value.strip()))


def _estimate_v2_expression_size(expr: str, total_values: int) -> int:
    """Estimate cell count for a v2 expression."""
    expr = expr.strip().upper()
    if expr == "*":
        return total_values
    m = re.match(r"(?:TOP|BOTTOM)\((\d+)", expr)
    if m:
        return min(int(m.group(1)), total_values)
    # FROM/TO/RANGE — estimate conservatively
    return min(total_values, 20)


# ---------------------------------------------------------------------------
# Tool 1: scb_search
# ---------------------------------------------------------------------------


def create_scb_search_tool(scb_service: ScbService | None = None):
    """Create the search tool."""
    service = scb_service or ScbService()

    @tool("scb_search", args_schema=ScbSearchInput)
    async def scb_search(
        query: str,
        max_results: int = 15,
        past_days: int | None = None,
    ) -> str:
        """Search SCB tables by keywords. Returns a compact list of matches.

        Use Swedish search terms for best results (e.g. "befolkning", "arbetslöshet").

        Args:
            query: Search terms in Swedish.
            max_results: Maximum number of results (default 15).
            past_days: Only show tables updated in the last N days.

        Returns:
            JSON with matching tables (id, title, period, subject).
            Use scb_inspect(table_id) on a result to see its full variable structure.
        """
        query = (query or "").strip()
        if not query:
            return json.dumps({"error": "Provide a search query."})

        try:
            tables = await service.search_tables(
                query, limit=max_results, past_days=past_days,
            )
            if not tables:
                return json.dumps({
                    "query": query,
                    "results": [],
                    "total_hits": 0,
                    "suggestions": [
                        "Try Swedish terms (e.g. 'befolkning' not 'population')",
                        "Try broader terms",
                        "Try scb_browse() to explore topics",
                    ],
                })

            results = []
            for t in tables[:max_results]:
                entry: dict[str, Any] = {
                    "id": t.id,
                    "title": t.title,
                }
                if t.updated:
                    entry["updated"] = t.updated
                if t.breadcrumb:
                    entry["subject"] = " > ".join(t.breadcrumb)
                results.append(entry)

            return json.dumps({
                "query": query,
                "results": results,
                "total_hits": len(tables),
                "next_step": "Use scb_inspect(table_id='...') to see full metadata.",
            }, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_search failed: %s", exc)
            return json.dumps({"error": f"Search failed: {exc!s}"})

    return scb_search


# ---------------------------------------------------------------------------
# Tool 2: scb_browse
# ---------------------------------------------------------------------------


def create_scb_browse_tool(scb_service: ScbService | None = None):
    """Create the tree navigation tool."""
    service = scb_service or ScbService()

    @tool("scb_browse", args_schema=ScbBrowseInput)
    async def scb_browse(
        path: str = "",
    ) -> str:
        """Navigate SCB's topic tree step by step.

        Use with empty path to see all top-level subjects, then drill down
        into interesting areas.

        Args:
            path: SCB path to browse. Empty string = top level.
                  Examples: "AM" (labour market), "BE/BE0101" (population stats).

        Returns:
            JSON with folder and table items at this level.
        """
        path = (path or "").strip().rstrip("/")
        browse_path = f"{path}/" if path else ""

        try:
            nodes = await service.list_nodes(browse_path)
            if not nodes:
                return json.dumps({
                    "path": path or "(top level)",
                    "items": [],
                    "note": "No items found at this path. Try a different path.",
                })

            items = []
            for node in nodes:
                node_id = str(node.get("id") or "").strip()
                node_type = str(node.get("type") or "").strip().lower()
                node_text = str(node.get("text") or node_id)

                entry: dict[str, Any] = {
                    "id": node_id,
                    "type": "table" if node_type == "t" else "folder",
                    "text": node_text,
                }
                if node.get("updated"):
                    entry["updated"] = node["updated"]
                items.append(entry)

            next_step = ""
            has_tables = any(i["type"] == "table" for i in items)
            has_folders = any(i["type"] == "folder" for i in items)
            if has_folders:
                folder_example = next(i["id"] for i in items if i["type"] == "folder")
                sub_path = f"{path}/{folder_example}" if path else folder_example
                next_step += f"Browse deeper: scb_browse(path='{sub_path}'). "
            if has_tables:
                table_example = next(i["id"] for i in items if i["type"] == "table")
                next_step += f"Inspect a table: scb_inspect(table_id='{table_example}')."

            return json.dumps({
                "path": path or "(top level)",
                "items": items,
                "folders": sum(1 for i in items if i["type"] == "folder"),
                "tables": sum(1 for i in items if i["type"] == "table"),
                "next_step": next_step,
            }, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_browse failed: %s", exc)
            return json.dumps({"error": f"Browse failed: {exc!s}"})

    return scb_browse


# ---------------------------------------------------------------------------
# Tool 3: scb_inspect
# ---------------------------------------------------------------------------


def create_scb_inspect_tool(scb_service: ScbService | None = None):
    """Create the metadata inspection tool."""
    service = scb_service or ScbService()

    @tool("scb_inspect", args_schema=ScbInspectInput)
    async def scb_inspect(
        table_id: str,
    ) -> str:
        """Inspect a SCB table's full metadata: variables, codes, defaults, codelists.

        This is the key step before fetching data. Shows everything you need to
        build a correct selection, including which variables can be omitted
        (auto-filled with defaults).

        Args:
            table_id: The SCB table ID (e.g. "TAB638", "BefolkningNy").

        Returns:
            JSON with complete variable structure, elimination info, default
            selection, usage examples, and hints.
        """
        table_id = (table_id or "").strip()
        if not table_id:
            return json.dumps({"error": "table_id is required."})

        try:
            # Fetch metadata and default selection in parallel
            metadata_task = service.get_table_metadata(table_id)
            default_sel_task = service.get_default_selection(table_id)
            metadata, default_selection = await asyncio.gather(
                metadata_task, default_sel_task
            )

            if not metadata or not metadata.get("variables"):
                return json.dumps({
                    "error": f"Table '{table_id}' not found or has no variables.",
                    "suggestions": ["Try scb_search(query='...') to find tables."],
                })

            variables = metadata.get("variables") or []
            formatted_vars = []

            for var in variables:
                code = str(var.get("code") or "")
                label = str(var.get("text") or code)
                values = [str(v) for v in (var.get("values") or []) if v is not None]
                value_texts = [
                    str(v) for v in (var.get("valueTexts") or []) if v is not None
                ]

                # Detect variable type
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

                total_values = len(values)

                # Build value samples (show strategic subset)
                sample_values = _build_sample_values(
                    values, value_texts, var_type, total_values
                )

                var_info: dict[str, Any] = {
                    "code": code,
                    "label": label,
                    "type": var_type,
                    "total_values": total_values,
                    "eliminable": var.get("elimination", False),
                    "values": sample_values,
                }

                # Default value
                elim_code = var.get("eliminationValueCode")
                if elim_code:
                    var_info["default_value"] = elim_code

                # Codelists
                codelists = var.get("codelists")
                if codelists:
                    var_info["codelists"] = [
                        f"{cl['id']} ({cl.get('label', '')})"
                        for cl in codelists
                    ]

                # ContentsCode enrichment (unit, ref_period)
                value_meta = var.get("valueMeta")
                if value_meta and var_type == "measure":
                    enriched_values = []
                    for sv in sample_values:
                        sv_code = sv.get("code", "")
                        meta = value_meta.get(sv_code, {})
                        if meta:
                            unit = meta.get("unit")
                            if isinstance(unit, dict):
                                sv["unit"] = unit.get("base", "")
                                sv["decimals"] = unit.get("decimals", 0)
                            elif unit:
                                sv["unit"] = str(unit)
                            if meta.get("refperiod"):
                                sv["ref_period"] = meta["refperiod"]
                            if meta.get("measuringType"):
                                sv["measuring_type"] = meta["measuringType"]
                        enriched_values.append(sv)
                    var_info["values"] = enriched_values

                # Hints and usage examples
                hint, usage = _build_hints_and_usage(
                    var_type, code, values, total_values, var_info.get("eliminable", False)
                )
                if hint:
                    var_info["hint"] = hint
                var_info["usage_examples"] = usage

                if total_values > _MAX_VALUES_TO_SHOW:
                    var_info["note"] = (
                        f"Showing {len(sample_values)} of {total_values} values."
                    )

                formatted_vars.append(var_info)

            result: dict[str, Any] = {
                "table_id": table_id,
                "title": metadata.get("title", table_id),
                "variables": formatted_vars,
            }

            # Top-level metadata
            if metadata.get("source"):
                result["source"] = metadata["source"]
            if metadata.get("updated"):
                result["updated"] = metadata["updated"]
            if metadata.get("officialStatistics") is not None:
                result["official_statistics"] = metadata["officialStatistics"]
            if metadata.get("note"):
                result["footnotes"] = metadata["note"]
            if metadata.get("contact"):
                result["contact"] = metadata["contact"]

            # Default selection
            if default_selection:
                result["default_selection"] = default_selection

            result["auto_complete_note"] = (
                "Variables marked eliminable=true can be OMITTED from your selection — "
                "they will be auto-filled with their default value."
            )
            result["next_step"] = (
                f"Build your selection and use scb_fetch(table_id='{table_id}', "
                "selection={...}). Omit eliminable variables to use defaults."
            )

            return json.dumps(result, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_inspect failed: %s", exc)
            return json.dumps({"error": f"Inspect failed: {exc!s}"})

    return scb_inspect


def _build_sample_values(
    values: list[str],
    value_texts: list[str],
    var_type: str,
    total_values: int,
) -> list[dict[str, str]]:
    """Build a strategic subset of values to show the LLM."""
    if total_values <= _MAX_VALUES_TO_SHOW:
        return [
            {"code": v, "label": t}
            for v, t in zip(values, value_texts, strict=False)
        ]

    # For large lists, show strategic samples
    samples: list[tuple[str, str]] = []

    if var_type == "time":
        # Show first 2 + last 5
        for i in range(min(2, total_values)):
            samples.append((values[i], value_texts[i] if i < len(value_texts) else values[i]))
        for i in range(max(0, total_values - 5), total_values):
            pair = (values[i], value_texts[i] if i < len(value_texts) else values[i])
            if pair not in samples:
                samples.append(pair)
    elif var_type == "region":
        # Show key regions: Riket, some counties, some cities
        key_codes = {"00", "01", "0180", "12", "1280", "14", "1480", "tot"}
        for v, t in zip(values, value_texts, strict=False):
            if v in key_codes:
                samples.append((v, t))
        # Fill up to _MAX_VALUES_TO_SHOW
        for v, t in zip(values, value_texts, strict=False):
            if len(samples) >= _MAX_VALUES_TO_SHOW:
                break
            if (v, t) not in samples:
                samples.append((v, t))
    else:
        # First _MAX_VALUES_TO_SHOW
        for i in range(min(_MAX_VALUES_TO_SHOW, total_values)):
            samples.append((
                values[i],
                value_texts[i] if i < len(value_texts) else values[i],
            ))

    return [{"code": v, "label": t} for v, t in samples]


def _build_hints_and_usage(
    var_type: str,
    code: str,
    values: list[str],
    total_values: int,
    eliminable: bool,
) -> tuple[str, dict[str, Any]]:
    """Build hints and usage examples for a variable."""
    hint = ""
    usage: dict[str, Any] = {}

    if var_type == "time" and values:
        hint = f"Range: {values[0]} - {values[-1]} ({total_values} periods)."
        hint += " Use TOP(n) for latest n, RANGE(from,to) for a span."
        usage = {
            "latest_5": {code: ["TOP(5)"]},
            "specific": {code: [values[-1]]},
            "range": {code: [f"RANGE({values[-3] if len(values) >= 3 else values[0]},{values[-1]})"]},
        }
    elif var_type == "region":
        hint = f"{total_values} regions. 00=Riket. Use codelist for counties/municipalities."
        usage = {
            "riket": {code: ["00"]},
            "specific": {code: ["0180"]},
            "all": {code: ["*"]},
        }
    elif var_type == "gender":
        hint = "1=män, 2=kvinnor. Omit to use default (total)."
        usage = {
            "both": {code: ["1", "2"]},
            "all": {code: ["*"]},
        }
    elif var_type == "measure":
        hint = "REQUIRED: Choose which measure to query."
        if values:
            usage = {"first_measure": {code: [values[0]]}}
    elif var_type == "age":
        hint = f"{total_values} age groups. Use 'tot' for total if available."
        usage = {"all": {code: ["*"]}}
    else:
        if eliminable:
            hint = f"Eliminable ({total_values} values). Can be omitted."
        usage = {"all": {code: ["*"]}}

    return hint, usage


# ---------------------------------------------------------------------------
# Tool 4: scb_codelist
# ---------------------------------------------------------------------------


def create_scb_codelist_tool(scb_service: ScbService | None = None):
    """Create the codelist lookup tool."""
    service = scb_service or ScbService()

    @tool("scb_codelist", args_schema=ScbCodelistInput)
    async def scb_codelist(
        codelist_id: str,
    ) -> str:
        """Fetch a SCB codelist (e.g. counties only, municipalities only).

        Use when scb_inspect shows available codelists for a variable.
        Codelists let you select pre-defined groups instead of listing all codes.

        Args:
            codelist_id: Codelist ID (e.g. "vs_RegionLän", "vs_RegionKommun07").

        Returns:
            JSON with all values in the codelist (code + label).
        """
        codelist_id = (codelist_id or "").strip()
        if not codelist_id:
            return json.dumps({"error": "codelist_id is required."})

        try:
            data = await service.get_codelist(codelist_id)
            if "error" in data:
                return json.dumps(data)

            # Format values
            values_list = data.get("values") or data.get("valueItems") or []
            formatted_values = []
            if isinstance(values_list, list):
                for item in values_list:
                    if isinstance(item, dict):
                        formatted_values.append({
                            "code": item.get("code", ""),
                            "label": item.get("label", item.get("valueText", "")),
                        })
                    elif isinstance(item, str):
                        formatted_values.append({"code": item, "label": item})

            return json.dumps({
                "id": data.get("id", codelist_id),
                "label": data.get("label", data.get("text", "")),
                "type": data.get("type", ""),
                "values": formatted_values,
                "total_values": len(formatted_values),
            }, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_codelist failed: %s", exc)
            return json.dumps({"error": f"Codelist fetch failed: {exc!s}"})

    return scb_codelist


# ---------------------------------------------------------------------------
# Tool 5: scb_preview
# ---------------------------------------------------------------------------


def create_scb_preview_tool(scb_service: ScbService | None = None):
    """Create the auto-limited preview tool."""
    service = scb_service or ScbService()

    @tool("scb_preview", args_schema=ScbPreviewInput)
    async def scb_preview(
        table_id: str,
        selection: dict[str, Any] | None = None,
    ) -> str:
        """Preview a SCB table with auto-limited data (~20 rows max).

        Use this to see what a table's data looks like before fetching the full
        dataset. Auto-limits: time → latest period, large dimensions → first 2 values.

        Args:
            table_id: The SCB table ID.
            selection: Optional partial selection. Unspecified variables are auto-limited.
                Values can be lists or strings (strings are auto-wrapped).

        Returns:
            JSON with a small markdown table preview and metadata.
        """
        table_id = (table_id or "").strip()
        if not table_id:
            return json.dumps({"error": "table_id is required."})

        # Auto-coerce string values to lists and expand year ranges
        if selection and isinstance(selection, dict):
            selection = _coerce_selection(selection)

        try:
            metadata = await service.get_table_metadata(table_id)
            if not metadata or not metadata.get("variables"):
                return json.dumps({
                    "error": f"Table '{table_id}' not found.",
                })

            variables = metadata.get("variables") or []
            preview_sel: dict[str, list[str]] = {}

            for var in variables:
                code = str(var.get("code") or "")
                values = [str(v) for v in (var.get("values") or []) if v is not None]
                label = str(var.get("text") or code)

                if selection and code in selection:
                    # Limit user-provided values
                    user_vals = selection[code]
                    limited = []
                    for uv in user_vals:
                        if _is_v2_expression(uv):
                            # Limit TOP/BOTTOM expressions
                            uv_upper = uv.strip().upper()
                            m = re.match(r"(TOP|BOTTOM)\((\d+)", uv_upper)
                            if m and int(m.group(2)) > 2:
                                limited.append(f"{m.group(1)}(2)")
                            else:
                                limited.append(uv)
                        else:
                            limited.append(uv)
                        if len(limited) >= 2:
                            break
                    preview_sel[code] = limited
                elif _is_time_variable(code, label):
                    preview_sel[code] = ["TOP(1)"]
                elif len(values) <= 3:
                    preview_sel[code] = values
                else:
                    # Use elimination default if available, else first 2
                    elim_code = var.get("eliminationValueCode")
                    if elim_code:
                        preview_sel[code] = [str(elim_code)]
                    else:
                        preview_sel[code] = values[:2]

            # Build and execute query
            payload = {
                "selection": [
                    {"variableCode": code, "valueCodes": vals}
                    for code, vals in preview_sel.items()
                    if vals
                ],
            }
            data = await service.query_table(table_id, payload)

            # Decode to markdown
            decoded = service.decode_jsonstat2_to_markdown(data, max_rows=30)

            return json.dumps({
                "table_id": table_id,
                "preview": True,
                "selection_used": preview_sel,
                **decoded,
                "note": (
                    "This is a LIMITED preview. Use scb_fetch() for full data. "
                    "Preview auto-limits: time=latest, large dims=first 2."
                ),
            }, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_preview failed: %s", exc)
            return json.dumps({"error": f"Preview failed: {exc!s}"})

    return scb_preview


# ---------------------------------------------------------------------------
# Tool 6: scb_validate
# ---------------------------------------------------------------------------


def create_scb_validate_tool(scb_service: ScbService | None = None):
    """Create the dry-run validation tool with auto-complete."""
    service = scb_service or ScbService()

    @tool("scb_validate", args_schema=ScbValidateInput)
    async def scb_validate(
        table_id: str,
        selection: dict[str, Any],
    ) -> str:
        """Validate a selection WITHOUT fetching data. Auto-completes missing variables.

        Unlike the old tool, you do NOT need to specify all variables.
        Missing eliminable variables are auto-filled with their defaults.
        Supports v2 expressions: TOP(n), FROM(x), RANGE(x,y), *.

        Args:
            table_id: The SCB table ID.
            selection: Dict mapping variable code to value codes.
                Values can be lists or strings (strings are auto-wrapped).
                Example: {"Region": ["0180"], "Tid": ["TOP(3)"], "ContentsCode": ["BE0101N1"]}

        Returns:
            JSON with validation result, auto-completed selection, and cell estimate.
        """
        table_id = (table_id or "").strip()
        if not table_id:
            return json.dumps({"error": "table_id is required."})
        if not selection or not isinstance(selection, dict):
            return json.dumps({
                "error": "selection must be a dict. Example: {\"Region\": [\"00\"], \"Tid\": [\"TOP(3)\"]}",
            })

        # Auto-coerce string values to lists and expand year ranges
        selection = _coerce_selection(selection)

        try:
            # Fetch metadata + default selection in parallel
            metadata_task = service.get_table_metadata(table_id)
            default_sel_task = service.get_default_selection(table_id)
            metadata, default_selection = await asyncio.gather(
                metadata_task, default_sel_task
            )

            if not metadata or not metadata.get("variables"):
                return json.dumps({
                    "error": f"Table '{table_id}' not found.",
                })

            variables = metadata.get("variables") or []
            errors: list[dict[str, Any]] = []
            warnings: list[str] = []
            resolved_selection: dict[str, list[str]] = {}

            # Build variable lookup
            var_by_code: dict[str, dict[str, Any]] = {}
            var_by_normalized: dict[str, dict[str, Any]] = {}
            for var in variables:
                vc = str(var.get("code") or "")
                var_by_code[vc] = var
                var_by_normalized[normalize_diacritik(vc)] = var
                vl = str(var.get("text") or "")
                if vl:
                    var_by_normalized[normalize_diacritik(vl)] = var

            for alias, real_code in _VARIABLE_ALIASES.items():
                if real_code in var_by_code and alias not in var_by_normalized:
                    var_by_normalized[normalize_diacritik(alias)] = var_by_code[real_code]

            # Validate provided selection
            used_vars: set[str] = set()

            for sel_code, sel_values in selection.items():
                var_info = var_by_code.get(sel_code)
                if not var_info:
                    norm_code = normalize_diacritik(sel_code)
                    var_info = var_by_normalized.get(norm_code)

                if not var_info:
                    suggestions = _find_closest_variables(
                        sel_code, [str(v.get("code", "")) for v in variables]
                    )
                    errors.append({
                        "variable": sel_code,
                        "error": f"Variable '{sel_code}' not found.",
                        "suggestions": suggestions,
                    })
                    continue

                actual_code = str(var_info.get("code") or "")
                used_vars.add(actual_code)
                valid_values = [str(v) for v in (var_info.get("values") or [])]
                valid_set = set(valid_values)
                value_texts = [str(v) for v in (var_info.get("valueTexts") or [])]
                value_text_map = dict(zip(valid_values, value_texts, strict=False))

                resolved_values: list[str] = []

                for val in (sel_values or []):
                    val_str = str(val).strip()

                    # v2 expressions pass through without validation
                    if _is_v2_expression(val_str):
                        resolved_values.append(val_str)
                        continue

                    if val_str in valid_set:
                        resolved_values.append(val_str)
                        continue

                    # Gender alias
                    gender_alias = _GENDER_ALIASES.get(val_str.lower())
                    if gender_alias and gender_alias in valid_set:
                        resolved_values.append(gender_alias)
                        warnings.append(f"'{val_str}' → '{gender_alias}'")
                        continue

                    # Region resolution
                    if _is_region_variable(actual_code, str(var_info.get("text", ""))):
                        region_codes = resolve_region_codes(
                            val_str, valid_values, value_texts,
                        )
                        if region_codes:
                            resolved_values.extend(region_codes)
                            names = [value_text_map.get(c, c) for c in region_codes]
                            warnings.append(
                                f"Region '{val_str}' → {region_codes} ({', '.join(names)})"
                            )
                            continue

                    # Fuzzy value matching
                    fuzzy_matches = _fuzzy_match_values(val_str, valid_values, value_texts)
                    if fuzzy_matches:
                        resolved_values.extend(fuzzy_matches)
                        names = [value_text_map.get(c, c) for c in fuzzy_matches]
                        warnings.append(f"'{val_str}' → {fuzzy_matches} ({', '.join(names)})")
                        continue

                    closest = _find_closest_values(val_str, valid_values, value_texts)
                    errors.append({
                        "variable": actual_code,
                        "value": val_str,
                        "error": f"Value '{val_str}' not found.",
                        "suggestions": closest,
                    })

                if resolved_values:
                    resolved_selection[actual_code] = list(dict.fromkeys(resolved_values))

            if errors:
                return json.dumps({
                    "status": "invalid",
                    "errors": errors,
                    "warnings": warnings,
                    "resolved_so_far": resolved_selection,
                }, ensure_ascii=False)

            # Auto-complete missing variables
            auto_completed, auto_log = service.auto_complete_selection(
                metadata, resolved_selection, default_selection
            )

            # Estimate cell count
            estimated_cells = 1
            for code, vals in auto_completed.items():
                var_info = var_by_code.get(code)
                total_vals = len(var_info.get("values", [])) if var_info else 1
                val_count = 0
                for v in vals:
                    if _is_v2_expression(v):
                        val_count += _estimate_v2_expression_size(v, total_vals)
                    else:
                        val_count += 1
                estimated_cells *= max(val_count, 1)

            return json.dumps({
                "status": "valid",
                "table_id": table_id,
                "selection": auto_completed,
                "auto_completed": auto_log,
                "estimated_cells": estimated_cells,
                "warnings": warnings,
                "next_step": (
                    f"Selection valid (~{estimated_cells} cells). "
                    f"Use scb_fetch(table_id='{table_id}', selection=...) to get data."
                ),
            }, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_validate failed: %s", exc)
            return json.dumps({"error": f"Validation failed: {exc!s}"})

    return scb_validate


# ---------------------------------------------------------------------------
# Tool 7: scb_fetch
# ---------------------------------------------------------------------------


def create_scb_fetch_tool(
    scb_service: ScbService | None = None,
    connector_service=None,
    search_space_id: int = 0,
    user_id: str | None = None,
    thread_id: int | None = None,
):
    """Create the data fetch tool with auto-complete and markdown decoding."""
    service = scb_service or ScbService()

    @tool("scb_fetch", args_schema=ScbFetchInput)
    async def scb_fetch(
        table_id: str,
        selection: dict[str, Any],
        codelist: dict[str, str] | None = None,
        max_rows: int = 100,
    ) -> str:
        """Fetch data from SCB and return as a readable markdown table.

        Auto-completes missing variables with elimination defaults.
        Supports v2 expressions: TOP(n), FROM(x), RANGE(x,y), *.
        Returns a formatted markdown table that you can present directly.

        Args:
            table_id: The SCB table ID (e.g. "TAB638").
            selection: Dict mapping variable codes to value codes.
                Values can be lists or strings (strings are auto-wrapped).
                Example: {"Region": ["0180","1480"], "Tid": ["TOP(3)"], "ContentsCode": ["BE0101N1"]}
                Missing eliminable variables are auto-filled.
            codelist: Optional dict mapping variable code to codelist ID.
                Example: {"Region": "vs_RegionLän"} to use only counties.
            max_rows: Maximum rows in the markdown table (default 100).

        Returns:
            JSON with data_table (markdown), metadata (unit, source), and selection used.
        """
        table_id = (table_id or "").strip()
        if not table_id:
            return json.dumps({"error": "table_id is required."})
        if not selection or not isinstance(selection, dict):
            return json.dumps({
                "error": "selection is required. Example: {\"ContentsCode\": [\"BE0101N1\"], \"Tid\": [\"TOP(3)\"]}",
            })

        # Auto-coerce string values to lists and expand year ranges
        selection = _coerce_selection(selection)

        try:
            # Step 1: Fetch metadata + default selection
            metadata_task = service.get_table_metadata(table_id)
            default_sel_task = service.get_default_selection(table_id)
            metadata, default_selection = await asyncio.gather(
                metadata_task, default_sel_task
            )

            if not metadata or not metadata.get("variables"):
                return json.dumps({
                    "error": f"Table '{table_id}' not found.",
                })

            # Step 2: Auto-complete missing variables
            completed_selection, auto_log = service.auto_complete_selection(
                metadata, selection, default_selection
            )

            # Step 3: Build v2 payload
            v2_selection: list[dict[str, Any]] = []
            for code, vals in completed_selection.items():
                entry: dict[str, Any] = {
                    "variableCode": code,
                    "valueCodes": vals,
                }
                # Apply codelist if specified
                if codelist and code in codelist:
                    entry["codelist"] = codelist[code]
                v2_selection.append(entry)

            payload = {"selection": v2_selection}

            # Step 4: Estimate cells and check limits
            variables = metadata.get("variables") or []
            var_by_code = {str(v.get("code", "")): v for v in variables}
            estimated_cells = 1
            for code, vals in completed_selection.items():
                var_info = var_by_code.get(code)
                total_vals = len(var_info.get("values", [])) if var_info else 1
                val_count = 0
                for v in vals:
                    if _is_v2_expression(v):
                        val_count += _estimate_v2_expression_size(v, total_vals)
                    else:
                        val_count += 1
                estimated_cells *= max(val_count, 1)

            if estimated_cells > 150_000:
                return json.dumps({
                    "error": f"Selection too large (~{estimated_cells:,} cells, max 150,000).",
                    "selection": completed_selection,
                    "suggestions": [
                        "Reduce time range: use TOP(5) instead of all years",
                        "Select specific regions instead of all",
                        "Use a codelist to limit regions (e.g. vs_RegionLän for counties)",
                        "Select fewer ContentsCode measures",
                    ],
                })

            # Step 5: Fetch data
            data = await service.query_table(table_id, payload)

            # Step 6: Decode JSON-stat2 to markdown
            decoded = service.decode_jsonstat2_to_markdown(data, max_rows=max_rows)

            # Build selection summary with labels
            selection_summary: dict[str, list[str]] = {}
            for code, vals in completed_selection.items():
                var_info = var_by_code.get(code, {})
                vt_map = dict(zip(
                    var_info.get("values") or [],
                    var_info.get("valueTexts") or [],
                    strict=False,
                ))
                labeled = []
                for v in vals:
                    if _is_v2_expression(v):
                        labeled.append(v)
                    else:
                        label = vt_map.get(v)
                        labeled.append(f"{v} ({label})" if label and label != v else v)
                selection_summary[code] = labeled

            result: dict[str, Any] = {
                "table_id": table_id,
                "title": metadata.get("title", table_id),
                "source": decoded.get("source", "SCB"),
                "updated": metadata.get("updated"),
                "selection_used": selection_summary,
                "data_table": decoded["data_table"],
                "row_count": decoded["row_count"],
                "truncated": decoded["truncated"],
            }

            if decoded.get("unit"):
                result["unit"] = decoded["unit"]
            if decoded.get("ref_period"):
                result["ref_period"] = decoded["ref_period"]
            if decoded.get("footnotes"):
                result["footnotes"] = decoded["footnotes"]
            if auto_log:
                result["auto_completed"] = auto_log
            result["warnings"] = []

            # Optional: ingest to knowledge base
            if connector_service is not None:
                await _ingest_result(
                    connector_service, service, table_id,
                    result, search_space_id, user_id, thread_id,
                )

            return json.dumps(result, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_fetch failed: %s", exc)
            return json.dumps({
                "error": f"Data fetch failed: {exc!s}",
                "suggestions": [
                    "Try scb_validate first to check your selection",
                    "Try scb_preview for a quick look",
                    "Reduce the selection size",
                ],
            })

    return scb_fetch


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _find_closest_variables(query: str, var_codes: list[str]) -> list[str]:
    """Find closest variable code matches."""
    query_norm = normalize_diacritik(query)
    scored = []
    for code in var_codes:
        code_norm = normalize_diacritik(code)
        if query_norm in code_norm or code_norm in query_norm:
            scored.append(code)
    return scored[:5] if scored else var_codes[:5]


def _find_closest_values(
    query: str,
    values: list[str],
    value_texts: list[str],
) -> list[str]:
    """Find closest value matches with 'did you mean?' suggestions."""
    query_norm = normalize_diacritik(query)
    suggestions: list[str] = []

    for val, text in zip(values, value_texts, strict=False):
        val_norm = normalize_diacritik(val)
        text_norm = normalize_diacritik(text)
        if (
            query_norm in val_norm
            or query_norm in text_norm
            or val_norm.startswith(query_norm)
            or text_norm.startswith(query_norm)
        ):
            suggestions.append(f"{val}={text}")

    return suggestions[:10] if suggestions else [
        f"{v}={t}" for v, t in list(zip(values[:10], value_texts[:10], strict=False))
    ]


def _fuzzy_match_values(
    query: str,
    values: list[str],
    value_texts: list[str],
) -> list[str]:
    """Fuzzy-match a value string against the valid values."""
    query_norm = normalize_diacritik(query)
    matches: list[str] = []

    for val, text in zip(values, value_texts, strict=False):
        text_norm = normalize_diacritik(text)
        if query_norm == text_norm or query_norm == normalize_diacritik(val) or f" {query_norm} " in f" {text_norm} ":
            matches.append(val)

    return matches


# Keep the old function name as an alias for backward compatibility
# (used by statistics_agent.py)
def _format_table_inspection(
    table_id: str,
    title: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Format table metadata into an LLM-friendly structure (legacy compat)."""
    variables = metadata.get("variables") or []
    formatted_vars = []

    for var in variables:
        code = str(var.get("code") or "")
        label = str(var.get("text") or code)
        values = [str(v) for v in (var.get("values") or []) if v is not None]
        value_texts = [
            str(v) for v in (var.get("valueTexts") or []) if v is not None
        ]

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

        total_values = len(values)
        show_count = min(total_values, _MAX_VALUES_TO_SHOW)
        sample_values = []
        for i in range(show_count):
            entry = {"code": values[i]}
            if i < len(value_texts):
                entry["label"] = value_texts[i]
            sample_values.append(entry)

        var_info: dict[str, Any] = {
            "code": code,
            "label": label,
            "type": var_type,
            "total_values": total_values,
            "eliminable": var.get("elimination", False),
            "values": sample_values,
        }

        if total_values > _MAX_VALUES_TO_SHOW:
            var_info["note"] = f"Showing {show_count} of {total_values} values."

        if var_type == "time" and values:
            var_info["hint"] = f"Latest: {values[-1]}, Earliest: {values[0]}. Use TOP(n) for latest n."
        elif var_type == "region" and total_values > 20:
            var_info["hint"] = "Use scb_validate to resolve region names. 00=Riket."
        elif var_type == "gender":
            var_info["hint"] = "1=män, 2=kvinnor. Omit to use default."
        elif var_type == "measure":
            var_info["hint"] = "REQUIRED: Choose which measure to query."

        formatted_vars.append(var_info)

    return {
        "table_id": table_id,
        "title": title,
        "variables": formatted_vars,
    }


async def _ingest_result(
    connector_service,
    scb_service: ScbService,
    table_id: str,
    result: dict[str, Any],
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Optionally ingest result into knowledge base."""
    try:
        await connector_service.ingest_tool_output(
            tool_name="scb_fetch",
            tool_output=result,
            title=f"SCB: {table_id}",
            metadata={
                "source": "SCB",
                "scb_table_id": table_id,
            },
            user_id=user_id,
            origin_search_space_id=search_space_id,
            thread_id=thread_id,
        )
    except Exception as exc:
        logger.warning("Failed to ingest SCB result: %s", exc)
