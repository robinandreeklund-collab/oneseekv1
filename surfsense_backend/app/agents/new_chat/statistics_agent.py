from __future__ import annotations

import json
from dataclasses import dataclass
import re
from typing import Any

import httpx
from langchain_core.tools import tool
from langgraph.store.memory import InMemoryStore
from langgraph.types import Checkpointer
from langgraph_bigtool import create_agent as create_bigtool_agent

from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.connector_service import ConnectorService
from app.services.scb_service import SCB_BASE_URL, ScbService


@dataclass(frozen=True)
class ScbToolDefinition:
    tool_id: str
    name: str
    base_path: str
    description: str
    keywords: list[str]
    example_queries: list[str]


SCB_TOOL_DEFINITIONS: list[ScbToolDefinition] = [
    ScbToolDefinition(
        tool_id="scb_befolkning",
        name="SCB Befolkning",
        base_path="BE/",
        description=(
            "Hamta befolkningsstatistik fran SCB. Omfattar folkmangd, flyttningar, "
            "fodelser, dodsfall, alder, kon och region."
        ),
        keywords=[
            "befolkning",
            "folkmangd",
            "flytt",
            "migration",
            "fodd",
            "dod",
            "alder",
            "kon",
        ],
        example_queries=[
            "Befolkning i Stockholm 2024",
            "Folkmangd Sverige 2015-2024",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_arbetsmarknad",
        name="SCB Arbetsmarknad",
        base_path="AM/",
        description=(
            "Hamta arbetsmarknadsstatistik fran SCB. Omfattar sysselsattning, "
            "arbetsloshet, arbetskraftsdeltagande och loner."
        ),
        keywords=[
            "arbetsmarknad",
            "arbetsloshet",
            "sysselsattning",
            "arbetstid",
            "lon",
        ],
        example_queries=[
            "Arbetsloshet Sverige senaste ar",
            "Sysselsattning kvinnor 2023",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_utbildning",
        name="SCB Utbildning och forskning",
        base_path="UF/",
        description=(
            "Hamta utbildnings- och forskningsstatistik fran SCB. "
            "Omfattar skolresultat, examen, hogskola och forskning."
        ),
        keywords=[
            "utbildning",
            "skola",
            "examen",
            "hogskola",
            "forskning",
        ],
        example_queries=[
            "Gymnasieexamen per lan 2022",
            "Hogskoleutbildning kvinnor 2021",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_nationalrakenskaper",
        name="SCB Nationalrakenskaper",
        base_path="NR/",
        description=(
            "Hamta nationalrakenskaper fran SCB. Omfattar BNP, tillvaxt, "
            "offentliga finanser och makroekonomi."
        ),
        keywords=[
            "bnp",
            "tillvaxt",
            "nationalrakenskaper",
            "ekonomi",
            "makro",
        ],
        example_queries=[
            "BNP Sverige 2010-2024",
            "Tillvaxt per ar",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_priser_konsumtion",
        name="SCB Priser och konsumtion",
        base_path="PR/",
        description=(
            "Hamta pris- och konsumtionsstatistik fran SCB. Omfattar KPI, inflation "
            "och konsumtionsindex."
        ),
        keywords=[
            "kpi",
            "inflation",
            "priser",
            "konsumtion",
        ],
        example_queries=[
            "KPI Sverige senaste 5 ar",
            "Inflation 2022",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_boende_byggande",
        name="SCB Boende och byggande",
        base_path="BO/",
        description=(
            "Hamta statistik om boende, byggande och bostader fran SCB. "
            "Omfattar bostadsbestand, nybyggnation och bygglov."
        ),
        keywords=[
            "boende",
            "bostad",
            "byggande",
            "bygglov",
            "bostadsbestand",
        ],
        example_queries=[
            "Nybyggnation bostader 2023",
            "Bostadsbestand Stockholm",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_naringsverksamhet",
        name="SCB Naringsverksamhet",
        base_path="NV/",
        description=(
            "Hamta statistik om naringsverksamhet och foretag fran SCB. "
            "Omfattar foretagsstruktur, branscher och omsattning."
        ),
        keywords=[
            "foretag",
            "naringsliv",
            "bransch",
            "omsattning",
            "foretagsstruktur",
        ],
        example_queries=[
            "Antal foretag per bransch 2023",
            "Omsattning i industrin",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_halsa_sjukvard",
        name="SCB Halsa och sjukvard",
        base_path="HS/",
        description=(
            "Hamta halso- och sjukvardsstatistik fran SCB. Omfattar patientstatistik, "
            "halsa och sjukvard."
        ),
        keywords=[
            "halsa",
            "sjukvard",
            "patient",
            "vard",
        ],
        example_queries=[
            "Patientstatistik per lan 2024",
            "Sjukhusvard Sverige",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_miljo",
        name="SCB Miljo",
        base_path="MI/",
        description=(
            "Hamta miljostatistik fran SCB. Omfattar utslapp, energi och miljopaverkan."
        ),
        keywords=[
            "miljo",
            "utslapp",
            "co2",
            "energi",
            "klimat",
        ],
        example_queries=[
            "CO2-utslapp Sverige 2020-2024",
            "Energianvandning per sektor",
        ],
    ),
    ScbToolDefinition(
        tool_id="scb_transporter",
        name="SCB Transporter och kommunikationer",
        base_path="TK/",
        description=(
            "Hamta statistik om transporter och kommunikationer fran SCB. "
            "Omfattar resor, trafik och gods."
        ),
        keywords=[
            "transport",
            "trafik",
            "resor",
            "gods",
            "kommunikation",
        ],
        example_queries=[
            "Resor med kollektivtrafik 2023",
            "Godstransporter Sverige",
        ],
    ),
]


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    cleaned = (
        lowered.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
    )
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def _score_tool(definition: ScbToolDefinition, query_norm: str, tokens: set[str]) -> int:
    score = 0
    name_norm = _normalize_text(definition.name)
    desc_norm = _normalize_text(definition.description)
    if name_norm and name_norm in query_norm:
        score += 5
    for keyword in definition.keywords:
        if _normalize_text(keyword) in query_norm:
            score += 3
    for token in tokens:
        if token and token in desc_norm:
            score += 1
    return score


def retrieve_scb_tools(query: str, limit: int = 2) -> list[str]:
    """Retrieve SCB tool IDs matching the query."""
    query_norm = _normalize_text(query)
    tokens = set(query_norm.split())
    scored = [
        (definition.tool_id, _score_tool(definition, query_norm, tokens))
        for definition in SCB_TOOL_DEFINITIONS
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    if scored and scored[0][1] == 0:
        return [definition.tool_id for definition in SCB_TOOL_DEFINITIONS[:limit]]
    return [tool_id for tool_id, _ in scored[:limit]]


async def aretrieve_scb_tools(query: str, limit: int = 2) -> list[str]:
    """Async wrapper for retrieving SCB tool IDs matching the query."""
    return retrieve_scb_tools(query, limit=limit)


def _build_tool_description(definition: ScbToolDefinition) -> str:
    examples = "\n".join(f"- {example}" for example in definition.example_queries)
    return f"{definition.description}\n\nExempel:\n{examples}"


def _build_scb_tool(
    definition: ScbToolDefinition,
    *,
    scb_service: ScbService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    description = _build_tool_description(definition)

    async def _scb_tool(
        question: str,
        max_tables: int = 40,
        max_cells: int = 150_000,
    ) -> str:
        query = (question or "").strip()
        if not query:
            return json.dumps(
                {"error": "Missing question for SCB query."}, ensure_ascii=True
            )

        try:
            table = await scb_service.find_best_table(
                definition.base_path, query, max_tables=max_tables
            )
            if not table:
                return json.dumps(
                    {"error": "No matching SCB table found."}, ensure_ascii=True
                )
            metadata = await scb_service.get_table_metadata(table.path)
            payload, selection_summary, warnings = scb_service.build_query_payload(
                metadata, query, max_cells=max_cells
            )
            data = await scb_service.query_table(table.path, payload)
        except httpx.HTTPError as exc:
            return json.dumps(
                {"error": f"SCB request failed: {exc!s}"}, ensure_ascii=True
            )

        source_url = f"{scb_service.base_url}{table.path.lstrip('/')}"
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
            "query": payload,
            "data": data,
            "warnings": warnings,
        }

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

        formatted_docs = ""
        if document:
            serialized = connector_service._serialize_external_document(
                document, score=1.0
            )
            formatted_docs = format_documents_for_context([serialized])

        response_payload = {
            "query": query,
            "table": tool_output["table"],
            "selection": selection_summary,
            "warnings": warnings,
            "results": formatted_docs,
        }
        if not formatted_docs:
            response_payload["data"] = data
        return json.dumps(response_payload, ensure_ascii=True)

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_scb_tool)


def build_scb_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
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
            },
        )
    return store


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
        llm,
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
