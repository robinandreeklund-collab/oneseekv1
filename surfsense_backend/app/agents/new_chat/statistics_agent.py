from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
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
from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.connector_service import ConnectorService
from app.services.scb_service import SCB_BASE_URL, ScbService

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
    sections = [definition.description]
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
    service = scb_service or ScbService()
    description = _build_tool_description(definition)

    async def _scb_tool(
        question: str,
        max_tables: int = 80,
        max_cells: int = 150_000,
        max_batches: int = 6,
    ) -> str:  # KQ-4: explicit return type annotation
        query = (question or "").strip()
        if not query:
            return json.dumps(
                {"error": "Missing question for SCB query."}, ensure_ascii=True
            )

        try:
            # Build scoring hint from domain keywords and table codes.
            # Exclude typical_filters (tid, region, kon, alder) — they're too
            # generic and match almost every SCB table, drowning out relevance.
            scoring_hint = " ".join(
                [
                    definition.name,
                    *definition.keywords,
                    *definition.table_codes,
                ]
            ).strip()
            table, candidates = await service.find_best_table_candidates(
                definition.base_path,
                query,
                scoring_hint=scoring_hint,
                max_tables=max_tables,
            )
            if not table:
                return json.dumps(
                    {"error": "No matching SCB table found."}, ensure_ascii=True
                )
            metadata = await service.get_table_metadata(table.path)
            payloads, selection_summary, warnings, batch_summaries = (
                service.build_query_payloads(
                    metadata,
                    query,
                    max_cells=max_cells,
                    max_batches=max_batches,
                )
            )
            if not payloads:
                return json.dumps(
                    {"error": "No valid SCB query payloads could be built."},
                    ensure_ascii=True,
                )

            raw_results = await asyncio.gather(
                *(service.query_table(table.path, p) for p in payloads)
            )
            data_batches: list[dict[str, Any]] = []
            for index, (data, _payload) in enumerate(
                zip(raw_results, payloads, strict=False), start=1
            ):
                entry: dict[str, Any] = {"batch": index, "data": data}
                if index - 1 < len(batch_summaries):
                    entry["selection"] = batch_summaries[index - 1]
                data_batches.append(entry)
        except (httpx.HTTPError, UnicodeDecodeError, ValueError) as exc:
            return json.dumps(
                {"error": f"SCB request failed: {exc!s}"}, ensure_ascii=True
            )

        source_url = f"{service.base_url}{table.path.lstrip('/')}"
        tool_output = {
            "source": "SCB PxWeb",
            "table": {
                "id": table.id,
                "title": table.title,
                "path": table.path,
                "updated": table.updated,
                "source_url": source_url,
            },
            "selection": selection_summary,
            "query": payloads,
            "data": data_batches,
            "warnings": warnings,
        }
        if candidates:
            tool_output["candidates"] = [
                {
                    "id": candidate.id,
                    "title": candidate.title,
                    "path": candidate.path,
                    "updated": candidate.updated,
                }
                for candidate in candidates
            ]

        # Document storage is optional — Pipeline Explorer runs without
        # connector_service, so we skip ingestion when it's unavailable.
        formatted_docs = ""
        if connector_service is not None:
            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=tool_output,
                title=f"{definition.name}: {table.title}",
                metadata={
                    "source": "SCB",
                    "scb_base_path": definition.base_path,
                    "scb_table_path": table.path,
                    "scb_table_id": table.id,
                    "scb_table_title": table.title,
                    "scb_source_url": source_url,
                },
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )
            if document:
                serialized = connector_service.serialize_external_document(
                    document, score=1.0
                )
                formatted_docs = format_documents_for_context([serialized])

        response_payload = {
            "query": query,
            "table": tool_output["table"],
            "selection": selection_summary,
            "warnings": warnings,
            "results": formatted_docs,
            "batches": len(data_batches),
        }
        if candidates:
            response_payload["candidates"] = tool_output["candidates"]
        if not formatted_docs:
            response_payload["data"] = data_batches
        return json.dumps(response_payload, ensure_ascii=True)

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
