"""SCB LLM-driven tools — Hybrid approach for precision.

Three tools that let the LLM *see* and *reason about* SCB's variable
structure instead of relying on heuristic-based selection:

1. scb_search_and_inspect — Search tables + inspect variables
2. scb_validate_selection — Dry-run validation with fuzzy suggestions
3. scb_fetch_validated   — Execute a validated selection

Design rationale:
- The old approach hid variables from the LLM → wrong tables, wrong data
- These tools expose the variable structure so the LLM can build correct
  selections based on understanding, not heuristics
- Precision over speed: 3-5 LLM tool calls instead of 1, but correct data
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from app.services.scb_regions import (
    find_region_fuzzy,
    format_region_for_llm,
    normalize_diacritik,
    resolve_region_codes,
)
from app.services.scb_service import ScbService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Variable / value translation (inspired by SCB-MCP)
# ---------------------------------------------------------------------------

# Common English/Swedish → SCB API variable code mappings
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

# Common value aliases for gender
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

# Maximum values to show per variable in inspect output
_MAX_VALUES_TO_SHOW = 25


# ---------------------------------------------------------------------------
# Tool 1: scb_search_and_inspect
# ---------------------------------------------------------------------------


def create_scb_search_and_inspect_tool(scb_service: ScbService | None = None):
    """Create the search + inspect tool."""
    service = scb_service or ScbService()

    @tool("scb_search_and_inspect")
    async def scb_search_and_inspect(
        query: str,
        base_path: str = "",
        table_id: str = "",
    ) -> str:
        """Search SCB tables and inspect their variable structure.

        Use this to find the right table for a statistics question. Returns
        candidate tables with their variables, value codes, and labels so
        you can build a precise selection.

        Args:
            query: The user's question or search terms (Swedish gives better results).
            base_path: Optional SCB domain path to scope search (e.g. "BE/" for population).
            table_id: If provided, skip search and inspect this specific table directly.

        Returns:
            JSON with candidate tables and their variable structures.
        """
        query = (query or "").strip()
        if not query and not table_id:
            return json.dumps({"error": "Provide a query or table_id."})

        try:
            if table_id:
                # Direct inspection of a known table
                metadata = await service.get_table_metadata(table_id.strip())
                if not metadata or not metadata.get("variables"):
                    return json.dumps({
                        "error": f"Table '{table_id}' not found or has no variables.",
                        "suggestions": [
                            "Try searching with scb_search_and_inspect(query='...')",
                            "Check if the table ID is correct",
                        ],
                    })
                return json.dumps(
                    _format_table_inspection(table_id, table_id, metadata),
                    ensure_ascii=False,
                )

            # Search for tables
            tables = await service.search_tables(query, limit=20)

            # Also try v1 tree if base_path provided
            if base_path:
                from app.agents.new_chat.scb_tool_definitions import SCB_TOOL_DEFINITIONS
                scoring_hint = ""
                for defn in SCB_TOOL_DEFINITIONS:
                    if defn.base_path == base_path:
                        scoring_hint = " ".join([defn.name, *defn.keywords])
                        break

                best_table, candidates = await service.find_best_table_candidates(
                    base_path,
                    query,
                    scoring_hint=scoring_hint,
                    max_tables=40,
                    metadata_limit=5,
                )
                # Merge with search results
                seen = {t.id for t in tables}
                if best_table and best_table.id not in seen:
                    tables.insert(0, best_table)
                for c in candidates:
                    if c.id not in seen:
                        tables.append(c)
                        seen.add(c.id)

            if not tables:
                return json.dumps({
                    "error": f"No tables found for query '{query}'.",
                    "suggestions": [
                        "Try Swedish search terms (e.g. 'befolkning' not 'population')",
                        "Try broader terms",
                        "Check SCB domain paths: BE/ AM/ BO/ NR/ PR/ etc.",
                    ],
                })

            # Inspect top 3 candidates (fetch metadata in parallel)
            import asyncio
            top_tables = tables[:5]

            async def _safe_meta(t):
                try:
                    return await service.get_table_metadata(t.path)
                except Exception:
                    return {}

            metadatas = await asyncio.gather(*(_safe_meta(t) for t in top_tables))

            inspections = []
            for table, metadata in zip(top_tables, metadatas, strict=False):
                if metadata and metadata.get("variables"):
                    inspections.append(
                        _format_table_inspection(table.id, table.title, metadata)
                    )

            if not inspections:
                return json.dumps({
                    "tables_found": len(tables),
                    "error": "Found tables but could not fetch metadata.",
                    "table_ids": [t.id for t in tables[:10]],
                    "suggestions": [
                        "Try inspecting a specific table: scb_search_and_inspect(table_id='...')"
                    ],
                })

            return json.dumps({
                "query": query,
                "tables_inspected": len(inspections),
                "total_tables_found": len(tables),
                "tables": inspections,
                "next_step": (
                    "Choose the best table, then use scb_validate_selection to "
                    "build and validate your selection before fetching data."
                ),
            }, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_search_and_inspect failed: %s", exc)
            return json.dumps({"error": f"Search failed: {exc!s}"})

    return scb_search_and_inspect


def _format_table_inspection(
    table_id: str,
    title: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Format table metadata into an LLM-friendly structure."""
    variables = metadata.get("variables") or []
    formatted_vars = []

    for var in variables:
        code = str(var.get("code") or "")
        label = str(var.get("text") or code)
        values = [str(v) for v in (var.get("values") or []) if v is not None]
        value_texts = [
            str(v) for v in (var.get("valueTexts") or []) if v is not None
        ]

        # Detect variable type for labeling
        from app.services.scb_service import (
            _is_age_variable,
            _is_gender_variable,
            _is_region_variable,
            _is_time_variable,
        )

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

        # Build value samples
        total_values = len(values)
        sample_values = []
        show_count = min(total_values, _MAX_VALUES_TO_SHOW)

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
            "values": sample_values,
        }

        if total_values > _MAX_VALUES_TO_SHOW:
            var_info["note"] = (
                f"Showing {show_count} of {total_values} values. "
                "Use specific codes in your selection."
            )

        # Add helpful hints per type
        if var_type == "time" and values:
            var_info["hint"] = f"Latest: {values[-1]}, Earliest: {values[0]}"
        elif var_type == "region" and total_values > 20:
            var_info["hint"] = (
                "Use scb_validate_selection to resolve region names to codes. "
                "00=Riket (whole Sweden)."
            )
        elif var_type == "gender":
            var_info["hint"] = "Common: 1=män, 2=kvinnor, TOT/totalt=alla"
        elif var_type == "measure":
            var_info["hint"] = "REQUIRED: Choose which measure to query."

        formatted_vars.append(var_info)

    return {
        "table_id": table_id,
        "title": title,
        "variables": formatted_vars,
        "selection_rules": {
            "all_variables_required": True,
            "note": (
                "SCB requires ALL variables to have at least one value selected. "
                "Use 'TOT' or 'totalt' for dimensions you don't want to split by."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Tool 2: scb_validate_selection
# ---------------------------------------------------------------------------


def create_scb_validate_selection_tool(scb_service: ScbService | None = None):
    """Create the dry-run validation tool."""
    service = scb_service or ScbService()

    @tool("scb_validate_selection")
    async def scb_validate_selection(
        table_id: str,
        selection: dict[str, list[str]],
    ) -> str:
        """Validate a selection against a table's metadata WITHOUT fetching data.

        Checks that all variables are covered, all value codes exist, and
        estimates the result size. Returns errors with suggestions if invalid.

        Args:
            table_id: The SCB table ID (e.g. "TAB1234" or "BE0101N2").
            selection: Dict mapping variable code to list of value codes.
                Example: {"Region": ["0180"], "Tid": ["2023"], "Kon": ["1", "2"]}

        Returns:
            JSON with validation result: "valid" with cell count, or "invalid"
            with specific errors and suggestions.
        """
        table_id = (table_id or "").strip()
        if not table_id:
            return json.dumps({"error": "table_id is required."})
        if not selection or not isinstance(selection, dict):
            return json.dumps({
                "error": "selection must be a dict of variable_code -> [value_codes].",
                "example": {"Region": ["00"], "Tid": ["2023"], "ContentsCode": ["BE0101N1"]},
            })

        try:
            metadata = await service.get_table_metadata(table_id)
        except Exception as exc:
            return json.dumps({"error": f"Failed to fetch metadata: {exc!s}"})

        if not metadata or not metadata.get("variables"):
            return json.dumps({
                "error": f"Table '{table_id}' not found or has no variables.",
            })

        variables = metadata.get("variables") or []
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []
        resolved_selection: dict[str, list[str]] = {}
        total_cells = 1

        # Build lookup for actual variable codes
        var_by_code: dict[str, dict[str, Any]] = {}
        var_by_normalized: dict[str, dict[str, Any]] = {}
        for var in variables:
            code = str(var.get("code") or "")
            var_by_code[code] = var
            var_by_normalized[normalize_diacritik(code)] = var
            # Also index by label
            label = str(var.get("text") or "")
            if label:
                var_by_normalized[normalize_diacritik(label)] = var

        # Index alias translations
        for alias, real_code in _VARIABLE_ALIASES.items():
            if real_code in var_by_code and alias not in var_by_normalized:
                var_by_normalized[normalize_diacritik(alias)] = var_by_code[real_code]

        # Check each provided selection variable
        used_vars: set[str] = set()

        for sel_code, sel_values in selection.items():
            # Resolve variable name
            var_info = var_by_code.get(sel_code)
            if not var_info:
                # Try normalized / alias lookup
                norm_code = normalize_diacritik(sel_code)
                var_info = var_by_normalized.get(norm_code)

            if not var_info:
                # Find closest match for suggestion
                suggestions = _find_closest_variables(
                    sel_code, [str(v.get("code", "")) for v in variables]
                )
                errors.append({
                    "variable": sel_code,
                    "error": f"Variable '{sel_code}' not found in table.",
                    "available_variables": [
                        f"{v.get('code')}: {v.get('text')}" for v in variables
                    ],
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

                # Direct match
                if val_str in valid_set:
                    resolved_values.append(val_str)
                    continue

                # Try gender alias
                gender_alias = _GENDER_ALIASES.get(val_str.lower())
                if gender_alias and gender_alias in valid_set:
                    resolved_values.append(gender_alias)
                    warnings.append(f"Resolved '{val_str}' → '{gender_alias}'")
                    continue

                # Try region resolution
                from app.services.scb_service import _is_region_variable
                if _is_region_variable(actual_code, str(var_info.get("text", ""))):
                    region_codes = resolve_region_codes(
                        val_str, valid_values, value_texts,
                    )
                    if region_codes:
                        resolved_values.extend(region_codes)
                        names = [value_text_map.get(c, c) for c in region_codes]
                        warnings.append(
                            f"Resolved region '{val_str}' → {region_codes} ({', '.join(names)})"
                        )
                        continue

                # Try fuzzy value text matching
                fuzzy_matches = _fuzzy_match_values(
                    val_str, valid_values, value_texts
                )
                if fuzzy_matches:
                    resolved_values.extend(fuzzy_matches)
                    names = [value_text_map.get(c, c) for c in fuzzy_matches]
                    warnings.append(
                        f"Fuzzy-matched '{val_str}' → {fuzzy_matches} ({', '.join(names)})"
                    )
                    continue

                # No match — suggest closest
                closest = _find_closest_values(val_str, valid_values, value_texts)
                errors.append({
                    "variable": actual_code,
                    "value": val_str,
                    "error": f"Value '{val_str}' not found in variable '{actual_code}'.",
                    "suggestions": closest,
                })

            if resolved_values:
                resolved_selection[actual_code] = list(dict.fromkeys(resolved_values))
                total_cells *= len(resolved_selection[actual_code])

        # Check for missing required variables
        all_var_codes = {str(v.get("code", "")) for v in variables}
        missing = all_var_codes - used_vars
        if missing:
            for miss_code in sorted(missing):
                var_info = var_by_code.get(miss_code, {})
                values = [str(v) for v in (var_info.get("values") or [])]
                value_texts = [str(v) for v in (var_info.get("valueTexts") or [])]

                # Suggest sensible defaults
                from app.services.scb_service import (
                    _is_time_variable,
                    _is_region_variable,
                    _is_gender_variable,
                    _is_age_variable,
                    _pick_preferred_value,
                )

                label = str(var_info.get("text", miss_code))
                suggestion = ""
                if _is_time_variable(miss_code, label):
                    default = values[-5:] if values else []
                    suggestion = f"Suggested: latest values {default}"
                elif _is_region_variable(miss_code, label):
                    default = _pick_preferred_value(values, value_texts, ["riket", "sverige"])
                    suggestion = f"Suggested: {default} (Riket = whole Sweden)"
                elif _is_gender_variable(miss_code, label):
                    default = _pick_preferred_value(values, value_texts, ["tot", "total"])
                    suggestion = f"Suggested: {default} (totalt)"
                elif _is_age_variable(miss_code, label):
                    default = _pick_preferred_value(values, value_texts, ["tot", "total"])
                    suggestion = f"Suggested: {default} (totalt)"
                else:
                    default = _pick_preferred_value(values, value_texts, ["tot", "total", "alla"])
                    if not default and values:
                        default = values[:1]
                    suggestion = f"Suggested: {default}"

                errors.append({
                    "variable": miss_code,
                    "label": label,
                    "error": "Missing from selection — SCB requires ALL variables.",
                    "suggestion": suggestion,
                    "sample_values": [
                        f"{v}={t}" for v, t in
                        list(zip(values[:10], value_texts[:10], strict=False))
                    ],
                })

        if errors:
            return json.dumps({
                "status": "invalid",
                "errors": errors,
                "warnings": warnings,
                "resolved_so_far": resolved_selection,
                "hint": "Fix the errors and try again. All variables must be included.",
            }, ensure_ascii=False)

        # All valid!
        max_cells = service.max_cells
        needs_batching = total_cells > max_cells

        return json.dumps({
            "status": "valid",
            "table_id": table_id,
            "selection": resolved_selection,
            "estimated_cells": total_cells,
            "needs_batching": needs_batching,
            "warnings": warnings,
            "next_step": (
                f"Selection is valid ({total_cells} cells). "
                "Use scb_fetch_validated to fetch the data."
            ),
        }, ensure_ascii=False)

    return scb_validate_selection


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
        # Exact normalized match
        if query_norm == text_norm or query_norm == normalize_diacritik(val):
            matches.append(val)
        # Word-boundary match for multi-word queries
        elif f" {query_norm} " in f" {text_norm} ":
            matches.append(val)

    return matches


# ---------------------------------------------------------------------------
# Tool 3: scb_fetch_validated
# ---------------------------------------------------------------------------


def create_scb_fetch_validated_tool(
    scb_service: ScbService | None = None,
    connector_service=None,
    search_space_id: int = 0,
    user_id: str | None = None,
    thread_id: int | None = None,
):
    """Create the validated data fetch tool."""
    service = scb_service or ScbService()

    @tool("scb_fetch_validated")
    async def scb_fetch_validated(
        table_id: str,
        selection: dict[str, list[str]],
    ) -> str:
        """Fetch data from SCB using a pre-validated selection.

        Use scb_validate_selection first to ensure your selection is correct.
        This tool executes the query and returns the data.

        Args:
            table_id: The SCB table ID.
            selection: Dict mapping variable code to list of value codes.
                Must include ALL variables for the table.

        Returns:
            JSON with the query results, metadata, and source information.
        """
        table_id = (table_id or "").strip()
        if not table_id:
            return json.dumps({"error": "table_id is required."})
        if not selection or not isinstance(selection, dict):
            return json.dumps({
                "error": "selection is required. Use scb_validate_selection first.",
            })

        try:
            # Build v2 payload directly from the selection
            payload = {
                "selection": [
                    {"variableCode": code, "valueCodes": values}
                    for code, values in selection.items()
                    if values
                ],
            }

            # Check if we need batching
            from math import prod
            cell_count = prod(len(v) for v in selection.values()) if selection else 0

            if cell_count > service.max_cells:
                # Use the existing batching infrastructure
                metadata = await service.get_table_metadata(table_id)
                if metadata:
                    # Convert selection dict to internal format
                    internal_selections = []
                    variables = metadata.get("variables") or []
                    var_map = {str(v.get("code", "")): v for v in variables}

                    for code, values in selection.items():
                        var_info = var_map.get(code, {})
                        value_texts = [
                            str(v) for v in (var_info.get("valueTexts") or [])
                        ]
                        from app.services.scb_service import (
                            _is_time_variable,
                            _is_region_variable,
                        )
                        internal_selections.append({
                            "code": code,
                            "label": str(var_info.get("text", code)),
                            "values": values,
                            "value_texts": value_texts,
                            "is_time": _is_time_variable(
                                code, str(var_info.get("text", ""))
                            ),
                            "is_region": _is_region_variable(
                                code, str(var_info.get("text", ""))
                            ),
                        })

                    batches, warnings = service._split_selection_batches(
                        internal_selections,
                        max_cells=service.max_cells,
                        max_batches=6,
                    )

                    import asyncio
                    payloads = [
                        service._payload_from_selections(batch)
                        for batch in batches
                    ]
                    results = await asyncio.gather(
                        *(service.query_table(table_id, p) for p in payloads)
                    )

                    data_batches = [
                        {"batch": i + 1, "data": data}
                        for i, data in enumerate(results)
                    ]

                    response = {
                        "source": "SCB PxWeb",
                        "table_id": table_id,
                        "selection": {k: v for k, v in selection.items()},
                        "batches": len(data_batches),
                        "warnings": warnings,
                        "data": data_batches,
                    }

                    # Optional: ingest to knowledge base
                    if connector_service is not None:
                        await _ingest_result(
                            connector_service, service, table_id,
                            response, search_space_id, user_id, thread_id,
                        )

                    return json.dumps(response, ensure_ascii=False)

            # Simple single-batch fetch
            data = await service.query_table(table_id, payload)

            source_url = f"{service.base_url}tables/{table_id}"
            response = {
                "source": "SCB PxWeb",
                "table_id": table_id,
                "source_url": source_url,
                "selection": {k: v for k, v in selection.items()},
                "estimated_cells": cell_count,
                "data": data,
            }

            # Optional: ingest to knowledge base
            if connector_service is not None:
                await _ingest_result(
                    connector_service, service, table_id,
                    response, search_space_id, user_id, thread_id,
                )

            return json.dumps(response, ensure_ascii=False)

        except Exception as exc:
            logger.exception("scb_fetch_validated failed: %s", exc)
            return json.dumps({
                "error": f"Data fetch failed: {exc!s}",
                "suggestions": [
                    "Verify your selection with scb_validate_selection first",
                    "Try a smaller selection (fewer values per variable)",
                ],
            })

    return scb_fetch_validated


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
        from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
        document = await connector_service.ingest_tool_output(
            tool_name="scb_fetch_validated",
            tool_output=result,
            title=f"SCB: {table_id}",
            metadata={
                "source": "SCB",
                "scb_table_id": table_id,
                "scb_source_url": result.get("source_url", ""),
            },
            user_id=user_id,
            origin_search_space_id=search_space_id,
            thread_id=thread_id,
        )
    except Exception as exc:
        logger.warning("Failed to ingest SCB result: %s", exc)
