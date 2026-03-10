from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.store.memory import InMemoryStore
from langgraph.types import Checkpointer
from langgraph_bigtool import create_agent as create_bigtool_agent
from langgraph_bigtool.graph import ToolNode as BigtoolToolNode

from app.agents.new_chat.nodes.executor import NormalizingChatWrapper
from app.agents.new_chat.scb_tool_definitions import (
    SCB_TOOL_DEFINITIONS,
    ScbToolDefinition,
    aretrieve_scb_tools,
    retrieve_scb_tools,
)
from app.agents.new_chat.tools.scb_llm_tools import _format_table_inspection
from app.services.connector_service import ConnectorService  # noqa: F401 — used by callers
from app.services.scb_service import SCB_BASE_URL, ScbService

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (bigtool_store.py imports these)
__all__ = [
    "SCB_TOOL_DEFINITIONS",
    "ScbToolDefinition",
    "aretrieve_scb_tools",
    "build_scb_tool",
    "build_scb_tool_registry",
    "build_scb_tool_store",
    "create_statistics_agent",
    "retrieve_scb_tools",
]


# Tool definitions, scoring, and retrieval are in scb_tool_definitions.py (KQ-3).
# The old inline list (~800 lines) was extracted there — see that file for all 47 tools.


# ---------------------------------------------------------------------------
# Tool building
# ---------------------------------------------------------------------------


def _build_tool_description(definition: ScbToolDefinition) -> str:
    examples = "\n".join(f"- {example}" for example in definition.example_queries)
    sections = [
        definition.description,
        (
            "HYBRID FLOW: This tool searches tables and returns their variable "
            "structure so you can build a precise selection. After calling this, "
            "use scb_validate_selection to validate your selection, then "
            "scb_fetch_validated to fetch the data."
        ),
    ]
    if definition.table_codes:
        sections.append(f"Vanliga tabellkoder: {', '.join(definition.table_codes)}.")
    if definition.typical_filters:
        sections.append(
            f"Typiska filter: {', '.join(definition.typical_filters)}."
        )
    sections.append(f"Exempel:\n{examples}")
    return "\n\n".join(sections)


def _build_scb_tool(
    definition: ScbToolDefinition,
    *,
    scb_service: ScbService | None = None,
    connector_service: ConnectorService | None = None,
    search_space_id: int = 0,
    user_id: str | None = None,
    thread_id: int | None = None,
):
    """Build a domain-scoped SCB tool using the hybrid LLM flow.

    Instead of blindly fetching data via heuristic payloads, each domain tool
    now returns the table variable structure (inspection) so the LLM can
    reason about what to select. The LLM then uses scb_validate_selection
    and scb_fetch_validated to complete the query.

    This is the hybrid approach: domain tools provide scoped search + inspect,
    the 3 LLM tools handle validation and fetching.
    """
    service = scb_service or ScbService()
    description = _build_tool_description(definition)

    async def _scb_tool(
        question: str,
        max_tables: int = 80,
    ) -> str:
        query = (question or "").strip()
        if not query:
            return json.dumps(
                {"error": "Missing question for SCB query."}, ensure_ascii=False
            )

        try:
            # Build scoring hint from domain keywords and table codes.
            scoring_hint = " ".join(
                [
                    definition.name,
                    *definition.keywords,
                    *definition.table_codes,
                ]
            ).strip()

            # Search within the domain's base_path
            table, candidates = await service.find_best_table_candidates(
                definition.base_path,
                query,
                scoring_hint=scoring_hint,
                max_tables=max_tables,
                metadata_limit=5,
            )

            # Also try v2 full-text search for broader coverage
            try:
                search_tables = await service.search_tables(query, limit=10)
            except Exception:
                search_tables = []

            # Merge results — domain-scoped first, then search results
            all_tables = []
            seen_ids: set[str] = set()
            if table:
                all_tables.append(table)
                seen_ids.add(table.id)
            for c in candidates or []:
                if c.id not in seen_ids:
                    all_tables.append(c)
                    seen_ids.add(c.id)
            for t in search_tables:
                if t.id not in seen_ids:
                    all_tables.append(t)
                    seen_ids.add(t.id)

            if not all_tables:
                return json.dumps({
                    "error": f"No matching SCB table found for '{query}' "
                             f"in domain {definition.base_path}.",
                    "suggestions": [
                        "Try broader Swedish search terms",
                        "Try scb_search_and_inspect for unrestricted search",
                    ],
                }, ensure_ascii=False)

            # Inspect top candidates — fetch metadata in parallel
            top_tables = all_tables[:5]

            async def _safe_meta(t):
                try:
                    path = getattr(t, "path", None) or t.id
                    return await service.get_table_metadata(path)
                except Exception:
                    return {}

            metadatas = await asyncio.gather(
                *(_safe_meta(t) for t in top_tables)
            )

            inspections = []
            for tbl, metadata in zip(top_tables, metadatas, strict=False):
                if metadata and metadata.get("variables"):
                    inspections.append(
                        _format_table_inspection(
                            tbl.id,
                            getattr(tbl, "title", tbl.id),
                            metadata,
                        )
                    )

            if not inspections:
                return json.dumps({
                    "tables_found": len(all_tables),
                    "error": "Found tables but could not fetch metadata.",
                    "table_ids": [t.id for t in all_tables[:10]],
                    "suggestions": [
                        "Try inspecting a specific table: "
                        "scb_search_and_inspect(table_id='...')",
                    ],
                }, ensure_ascii=False)

            return json.dumps({
                "domain": definition.name,
                "base_path": definition.base_path,
                "query": query,
                "tables_inspected": len(inspections),
                "total_tables_found": len(all_tables),
                "tables": inspections,
                "next_step": (
                    "Choose the best table above. Build a selection dict "
                    "mapping each variable code to the value codes you want. "
                    "Then call scb_validate_selection(table_id='...', "
                    "selection={...}) to validate, and finally "
                    "scb_fetch_validated(table_id='...', selection={...}) "
                    "to fetch the data."
                ),
            }, ensure_ascii=False)

        except Exception as exc:
            logger.exception(
                "%s failed for query '%s': %s",
                definition.tool_id, query, exc,
            )
            return json.dumps({
                "error": f"SCB search failed: {exc!s}",
                "suggestions": [
                    "Try scb_search_and_inspect for unrestricted search",
                ],
            }, ensure_ascii=False)

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_scb_tool)


# Public alias for the tool factory (used by tools/registry.py)
build_scb_tool = _build_scb_tool


# ---------------------------------------------------------------------------
# Registry and store
# ---------------------------------------------------------------------------


def build_scb_tool_registry(
    *,
    connector_service: ConnectorService | None = None,
    search_space_id: int = 0,
    user_id: str | None = None,
    thread_id: int | None = None,
    scb_service: ScbService | None = None,
) -> dict[str, Any]:
    service = scb_service or ScbService()
    registry: dict[str, Any] = {}
    for definition in SCB_TOOL_DEFINITIONS:
        registry[definition.tool_id] = _build_scb_tool(
            definition,
            scb_service=service,
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )
    return registry


def build_scb_tool_store() -> InMemoryStore:
    store = InMemoryStore()
    for definition in SCB_TOOL_DEFINITIONS:
        store.put(
            ("tools",),
            definition.tool_id,
            {
                "name": definition.name,
                "description": definition.description,
                "category": "scb_statistics",
                "base_path": definition.base_path,
                "keywords": definition.keywords,
                "example_queries": definition.example_queries,
                "table_codes": definition.table_codes,
                "typical_filters": definition.typical_filters,
            },
        )
    return store


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_statistics_agent(
    *,
    llm,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    checkpointer: Checkpointer | None,
    scb_base_url: str | None = None,
):
    if not hasattr(BigtoolToolNode, "inject_tool_args") and hasattr(
        BigtoolToolNode, "_inject_tool_args"
    ):
        def _inject_tool_args_compat(self, tool_call, state, store):
            tool_call_id = None
            if isinstance(tool_call, dict):
                tool_call_id = tool_call.get("id")
            runtime = ToolRuntime(
                state,
                {},
                {},
                lambda _: None,
                tool_call_id,
                store,
            )
            return self._inject_tool_args(tool_call, runtime)

        BigtoolToolNode.inject_tool_args = _inject_tool_args_compat  # type: ignore[attr-defined]
    scb_service = ScbService(base_url=scb_base_url or SCB_BASE_URL)
    tool_registry = build_scb_tool_registry(
        connector_service=connector_service,
        search_space_id=search_space_id,
        user_id=user_id,
        thread_id=thread_id,
        scb_service=scb_service,
    )
    store = build_scb_tool_store()
    graph = create_bigtool_agent(
        NormalizingChatWrapper(llm),
        tool_registry,
        limit=2,
        retrieve_tools_function=retrieve_scb_tools,
        retrieve_tools_coroutine=aretrieve_scb_tools,
    )
    return graph.compile(
        checkpointer=checkpointer,
        store=store,
        name="statistics-agent",
    )
