from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.store.memory import InMemoryStore
from langgraph.types import Checkpointer
from langgraph_bigtool import create_agent as create_bigtool_agent
from langgraph_bigtool.graph import ToolNode as BigtoolToolNode

from app.agents.new_chat.cache_scb_catalogs import (
    format_catalog_for_prompt,
    get_domain_catalog,
    resolve_regions_for_prompt,
)
# NOTE: NormalizingChatWrapper import is lazy (inside function) to break circular import:
# supervisor_constants → tools → registry → statistics_agent → nodes → critic
# → supervisor_memory → supervisor_constants
from app.agents.new_chat.scb_tool_definitions import (
    SCB_TOOL_DEFINITIONS,
    ScbToolDefinition,
    aretrieve_scb_tools,
    retrieve_scb_tools,
)
from app.agents.new_chat.tools.scb_llm_tools import (
    create_scb_fetch_tool,
    create_scb_validate_tool,
)
from app.services.connector_service import (
    ConnectorService,
)
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
# Tool building — NEW: cached catalog approach
# ---------------------------------------------------------------------------


def _build_tool_description(definition: ScbToolDefinition) -> str:
    examples = "\n".join(f"- {example}" for example in definition.example_queries)
    sections = [
        definition.description,
        (
            "CATALOG FLOW: This tool returns a pre-cached catalog of ALL tables "
            "in this domain with their ContentsCode (measures) and variable "
            "summaries. Choose the right table, then call scb_validate to "
            "validate your selection, and scb_fetch to get the data."
        ),
    ]
    if definition.table_codes:
        sections.append(f"Vanliga tabellkoder: {', '.join(definition.table_codes)}.")
    if definition.typical_filters:
        sections.append(f"Typiska filter: {', '.join(definition.typical_filters)}.")
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
    """Build a domain-scoped SCB tool using the cached catalog approach.

    Instead of real-time BFS + metadata fetching, each domain tool returns
    a pre-cached catalog of all tables with ContentsCode labels and variable
    summaries. The LLM picks the right table directly, then uses
    scb_validate + scb_fetch to complete the query.
    """
    service = scb_service or ScbService()
    description = _build_tool_description(definition)

    async def _scb_tool(
        question: str,
    ) -> str:
        query = (question or "").strip()
        if not query:
            return json.dumps(
                {"error": "Missing question for SCB query."}, ensure_ascii=False
            )

        try:
            # Get cached catalog (fetches on first use, then cached 24h)
            catalog = await get_domain_catalog(definition, service=service)

            if not catalog.tables:
                return json.dumps(
                    {
                        "error": f"No tables found in domain {definition.base_path}.",
                        "suggestions": [
                            "Try scb_search for unrestricted search",
                        ],
                    },
                    ensure_ascii=False,
                )

            # Format catalog for LLM consumption
            catalog_text = format_catalog_for_prompt(catalog, user_query=query)

            # Resolve region references in the query
            region_info = resolve_regions_for_prompt(query)

            # Build the response with catalog + region info + instructions
            result: dict[str, Any] = {
                "domain": definition.name,
                "base_path": definition.base_path,
                "query": query,
                "total_tables": len(catalog.tables),
                "catalog": catalog_text,
            }

            if region_info:
                result["region_codes"] = region_info

            result["instructions"] = (
                "STEG 1: Läs tabellkatalogen ovan. Välj den tabell vars "
                "ContentsCode (mått) bäst matchar frågan.\n"
                "STEG 2: Bygg en selection-dict med variabelkoder.\n"
                "STEG 3: Kör scb_validate(table_id='...', selection={...}) "
                "för att validera.\n"
                "STEG 4: Kör scb_fetch(table_id='...', selection={...}) "
                "för att hämta data som markdown.\n\n"
                "VIKTIGT: Du MÅSTE köra scb_validate INNAN scb_fetch.\n"
                "Saknade variabler auto-kompletteras.\n"
                "Använd TOP(n), FROM(x), RANGE(x,y) för tidsval."
            )

            return json.dumps(result, ensure_ascii=False)

        except Exception as exc:
            logger.exception(
                "%s failed for query '%s': %s",
                definition.tool_id,
                query,
                exc,
            )
            return json.dumps(
                {
                    "error": f"SCB catalog lookup failed: {exc!s}",
                    "suggestions": [
                        "Try scb_search for unrestricted search",
                    ],
                },
                ensure_ascii=False,
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_scb_tool)


# Public alias for the tool factory (used by tools/registry.py)
build_scb_tool = _build_scb_tool


# # ---------------------------------------------------------------------------
# # OLD: Tool building — real-time BFS + metadata fetching (commented out)
# # ---------------------------------------------------------------------------
# # Kept for rollback if the cached catalog approach doesn't work.
#
# def _build_tool_description_OLD(definition: ScbToolDefinition) -> str:
#     examples = "\n".join(f"- {example}" for example in definition.example_queries)
#     sections = [
#         definition.description,
#         (
#             "HYBRID FLOW: This tool searches tables and returns their variable "
#             "structure so you can build a precise selection. After calling this, "
#             "use scb_validate to validate your selection, then "
#             "scb_fetch to fetch the data as a readable markdown table."
#         ),
#     ]
#     if definition.table_codes:
#         sections.append(f"Vanliga tabellkoder: {', '.join(definition.table_codes)}.")
#     if definition.typical_filters:
#         sections.append(
#             f"Typiska filter: {', '.join(definition.typical_filters)}."
#         )
#     sections.append(f"Exempel:\n{examples}")
#     return "\n\n".join(sections)
#
#
# def _build_scb_tool_OLD(
#     definition: ScbToolDefinition,
#     *,
#     scb_service: ScbService | None = None,
#     connector_service: ConnectorService | None = None,
#     search_space_id: int = 0,
#     user_id: str | None = None,
#     thread_id: int | None = None,
# ):
#     """Build a domain-scoped SCB tool using the hybrid LLM flow.
#
#     Instead of blindly fetching data via heuristic payloads, each domain tool
#     now returns the table variable structure (inspection) so the LLM can
#     reason about what to select. The LLM then uses scb_validate
#     and scb_fetch to complete the query with auto-complete and markdown output.
#
#     This is the hybrid approach: domain tools provide scoped search + inspect,
#     the 7 LLM tools handle validation, preview, and fetching.
#     """
#     from app.agents.new_chat.tools.scb_llm_tools import _format_table_inspection
#
#     service = scb_service or ScbService()
#     description = _build_tool_description_OLD(definition)
#
#     async def _scb_tool(
#         question: str,
#         max_tables: int = 80,
#     ) -> str:
#         query = (question or "").strip()
#         if not query:
#             return json.dumps(
#                 {"error": "Missing question for SCB query."}, ensure_ascii=False
#             )
#
#         try:
#             # Build scoring hint from domain keywords and table codes.
#             scoring_hint = " ".join(
#                 [
#                     definition.name,
#                     *definition.keywords,
#                     *definition.table_codes,
#                 ]
#             ).strip()
#
#             # Search within the domain's base_path
#             table, candidates = await service.find_best_table_candidates(
#                 definition.base_path,
#                 query,
#                 scoring_hint=scoring_hint,
#                 max_tables=max_tables,
#                 metadata_limit=15,
#                 candidate_limit=8,
#             )
#
#             # Also try v2 full-text search for broader coverage
#             try:
#                 search_tables = await service.search_tables(query, limit=10)
#             except Exception:
#                 search_tables = []
#
#             # Merge results — domain-scoped first, then search results
#             all_tables = []
#             seen_ids: set[str] = set()
#             if table:
#                 all_tables.append(table)
#                 seen_ids.add(table.id)
#             for c in candidates or []:
#                 if c.id not in seen_ids:
#                     all_tables.append(c)
#                     seen_ids.add(c.id)
#             for t in search_tables:
#                 if t.id not in seen_ids:
#                     all_tables.append(t)
#                     seen_ids.add(t.id)
#
#             if not all_tables:
#                 return json.dumps({
#                     "error": f"No matching SCB table found for '{query}' "
#                              f"in domain {definition.base_path}.",
#                     "suggestions": [
#                         "Try broader Swedish search terms",
#                         "Try scb_search for unrestricted search",
#                     ],
#                 }, ensure_ascii=False)
#
#             # Inspect top candidates — fetch metadata in parallel
#             top_tables = all_tables[:5]
#
#             async def _safe_meta(t):
#                 try:
#                     path = getattr(t, "path", None) or t.id
#                     return await service.get_table_metadata(path)
#                 except Exception:
#                     return {}
#
#             metadatas = await asyncio.gather(
#                 *(_safe_meta(t) for t in top_tables)
#             )
#
#             inspections = []
#             for tbl, metadata in zip(top_tables, metadatas, strict=False):
#                 if metadata and metadata.get("variables"):
#                     inspections.append(
#                         _format_table_inspection(
#                             tbl.id,
#                             getattr(tbl, "title", tbl.id),
#                             metadata,
#                         )
#                     )
#
#             if not inspections:
#                 return json.dumps({
#                     "tables_found": len(all_tables),
#                     "error": "Found tables but could not fetch metadata.",
#                     "table_ids": [t.id for t in all_tables[:10]],
#                     "suggestions": [
#                         "Try inspecting a specific table: "
#                         "scb_inspect(table_id='...')",
#                     ],
#                 }, ensure_ascii=False)
#
#             return json.dumps({
#                 "domain": definition.name,
#                 "base_path": definition.base_path,
#                 "query": query,
#                 "tables_inspected": len(inspections),
#                 "total_tables_found": len(all_tables),
#                 "tables": inspections,
#                 "next_step": (
#                     "Choose the best table above. Build a selection dict "
#                     "mapping each variable code to the value codes you want. "
#                     "Then call scb_fetch(table_id='...', "
#                     "selection={...}) to fetch data as a markdown table. "
#                     "Missing variables are auto-completed. "
#                     "Use TOP(n), FROM(x), RANGE(x,y) for time selections."
#                 ),
#             }, ensure_ascii=False)
#
#         except Exception as exc:
#             logger.exception(
#                 "%s failed for query '%s': %s",
#                 definition.tool_id, query, exc,
#             )
#             return json.dumps({
#                 "error": f"SCB search failed: {exc!s}",
#                 "suggestions": [
#                     "Try scb_search for unrestricted search",
#                 ],
#             }, ensure_ascii=False)
#
#     return tool(
#         definition.tool_id,
#         description=description,
#         parse_docstring=False,
#     )(_scb_tool)


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
    # Always include scb_validate and scb_fetch so the bigtool LLM can
    # complete the catalog → validate → fetch pipeline.
    registry["scb_validate"] = create_scb_validate_tool(scb_service=service)
    registry["scb_fetch"] = create_scb_fetch_tool(
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
    # Add validate + fetch to store so bigtool can use them
    store.put(
        ("tools",),
        "scb_validate",
        {
            "name": "SCB Validate",
            "description": (
                "Validate a selection without fetching data. Auto-completes "
                "missing variables. Use BEFORE scb_fetch."
            ),
            "category": "scb_pipeline",
            "keywords": ["validate", "selection", "check"],
        },
    )
    store.put(
        ("tools",),
        "scb_fetch",
        {
            "name": "SCB Fetch",
            "description": (
                "Fetch data from SCB as a readable markdown table. "
                "Auto-completes missing variables. Use AFTER scb_validate."
            ),
            "category": "scb_pipeline",
            "keywords": ["fetch", "data", "table", "markdown"],
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

    # Wrap retrieve functions to always include scb_validate + scb_fetch
    # so the bigtool LLM can complete: catalog → validate → fetch
    pipeline_tools = ["scb_validate", "scb_fetch"]

    def _retrieve_with_pipeline(query: str, limit: int = 2) -> list[str]:
        domain_tools = retrieve_scb_tools(query, limit=limit)
        return domain_tools + pipeline_tools

    async def _aretrieve_with_pipeline(query: str, limit: int = 2) -> list[str]:
        domain_tools = await aretrieve_scb_tools(query, limit=limit)
        return domain_tools + pipeline_tools

    from app.agents.new_chat.nodes.executor import NormalizingChatWrapper

    graph = create_bigtool_agent(
        NormalizingChatWrapper(llm),
        tool_registry,
        limit=4,  # 2 domain tools + validate + fetch
        retrieve_tools_function=_retrieve_with_pipeline,
        retrieve_tools_coroutine=_aretrieve_with_pipeline,
    )
    return graph.compile(
        checkpointer=checkpointer,
        store=store,
        name="statistics-agent",
    )
