from __future__ import annotations

import json
from typing import Any

import httpx
from langchain_core.tools import tool

from app.agents.new_chat.riksdagen_agent import RiksdagenToolDefinition
from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.connector_service import ConnectorService
from app.services.riksdagen_service import (
    RIKSDAGEN_SOURCE,
    RIKSDAGEN_SOURCE_URL,
    RiksdagenService,
)

# =============================================================================
# DOKUMENT TOOLS (13 document sub-tools + 1 top-level + 1 status)
# =============================================================================

RIKSDAGEN_DOKUMENT_TOOL_DEFINITIONS: list[RiksdagenToolDefinition] = [
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument",
        name="Riksdag Dokument - Alla typer",
        description="Sök bland alla 70+ dokumenttyper från Riksdagen.",
        keywords=["dokument", "riksdag", "riksdagen", "söka", "sök"],
        example_queries=[
            "Dokument om försvar 2024",
            "Riksdagsdokument från Finansutskottet",
            "Dokument om klimat senaste året",
        ],
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_proposition",
        name="Riksdag Dokument - Proposition",
        description="Sök propositioner (regeringens förslag till riksdagen).",
        keywords=["proposition", "prop", "regeringen", "förslag"],
        example_queries=[
            "Propositioner om NATO 2024",
            "Senaste budgetpropositionen",
            "Proposition om skola 2023/24",
        ],
        doktyp="prop",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_motion",
        name="Riksdag Dokument - Motion",
        description="Sök motioner (ledamöternas förslag).",
        keywords=["motion", "mot", "förslag", "ledamot"],
        example_queries=[
            "Motioner om migration 2024",
            "Socialdemokraternas motioner om vård",
            "Motion från Anna Andersson",
        ],
        doktyp="mot",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_betankande",
        name="Riksdag Dokument - Betänkande",
        description="Sök betänkanden (utskottens beslutsförslag).",
        keywords=["betänkande", "bet", "utskott", "beslutsförslag"],
        example_queries=[
            "Finansutskottets betänkanden 2024",
            "Betänkande om budget",
            "Utskottsbetänkanden om försvar",
        ],
        doktyp="bet",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_interpellation",
        name="Riksdag Dokument - Interpellation",
        description="Sök interpellationer (frågor till ministrar som besvaras i kammaren).",
        keywords=["interpellation", "ip", "fråga", "minister"],
        example_queries=[
            "Interpellationer till statsministern 2024",
            "Frågor om skola till utbildningsministern",
            "Interpellation om klimat",
        ],
        doktyp="ip",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_fraga",
        name="Riksdag Dokument - Fråga",
        description="Sök skriftliga frågor (frågor som besvaras skriftligt).",
        keywords=["fråga", "fr", "frs", "skriftlig"],
        example_queries=[
            "Frågor till regeringen 2024",
            "Skriftliga frågor om migration",
            "Frågor från Moderaterna",
        ],
        doktyp="fr,frs",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_protokoll",
        name="Riksdag Dokument - Protokoll",
        description="Sök kammarprotokoll (från debatter och voteringar).",
        keywords=["protokoll", "prot", "kammarprotokoll", "debatt"],
        example_queries=[
            "Protokoll från budgetdebatten 2024",
            "Kammarprotokoll senaste veckan",
            "Protokoll om försvar",
        ],
        doktyp="prot",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_sou",
        name="Riksdag Dokument - SOU",
        description="Sök statens offentliga utredningar (SOU).",
        keywords=["sou", "utredning", "offentlig"],
        example_queries=[
            "SOU om migration senaste året",
            "Utredningar om klimat 2023",
            "SOU från 2024",
        ],
        doktyp="sou",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_ds",
        name="Riksdag Dokument - Ds",
        description="Sök departementsskrivelser (Ds).",
        keywords=["ds", "departement", "skrivelse"],
        example_queries=[
            "Ds om försvar 2024",
            "Departementsskrivelser senaste året",
            "Ds från Finansdepartementet",
        ],
        doktyp="ds",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_dir",
        name="Riksdag Dokument - Direktiv",
        description="Sök kommittédirektiv.",
        keywords=["direktiv", "dir", "kommitté"],
        example_queries=[
            "Direktiv för utredningar 2024",
            "Kommittédirektiv om klimat",
            "Direktiv senaste året",
        ],
        doktyp="dir",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_rskr",
        name="Riksdag Dokument - Riksdagsskrivelse",
        description="Sök riksdagsskrivelser (beslut till regeringen).",
        keywords=["riksdagsskrivelse", "rskr", "beslut"],
        example_queries=[
            "Riksdagsskrivelser 2024",
            "Beslut till regeringen om budget",
            "Rskr från senaste året",
        ],
        doktyp="rskr",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_eu",
        name="Riksdag Dokument - EU-dokument",
        description="Sök EU-dokument som behandlas i Riksdagen.",
        keywords=["eu", "kom", "europa", "europeiska"],
        example_queries=[
            "EU-dokument om migration 2024",
            "KOM-dokument senaste året",
            "EU-förslag i Riksdagen",
        ],
        doktyp="KOM",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokument_rir",
        name="Riksdag Dokument - RiR",
        description="Sök Riksrevisionens rapporter (RiR).",
        keywords=["rir", "riksrevisionen", "granskning", "rapport"],
        example_queries=[
            "Riksrevisionens rapporter 2024",
            "RiR om statsbudgeten",
            "Granskningar från Riksrevisionen",
        ],
        doktyp="rir",
        category="riksdagen_dokument",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_dokumentstatus",
        name="Riksdag Dokumentstatus",
        description="Hämta ärendehistorik och status för ett specifikt dokument.",
        keywords=["status", "ärendehistorik", "handläggning", "dokumentstatus"],
        example_queries=[
            "Status för proposition 2023/24:1",
            "Vad har hänt med motion M123?",
            "Ärendehistorik för betänkande 2024/25:FiU1",
        ],
        category="riksdagen_status",
    ),
]


def _build_tool_description(definition: RiksdagenToolDefinition) -> str:
    """Build tool description with examples."""
    examples = "\n".join(f"- {example}" for example in definition.example_queries)
    sections = [definition.description]
    sections.append(f"Exempel:\n{examples}")
    return "\n\n".join(sections)


def _build_riksdagen_dokument_tool(
    definition: RiksdagenToolDefinition,
    *,
    riksdagen_service: RiksdagenService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Build a document search tool."""
    description = _build_tool_description(definition)

    async def _dokument_tool(
        sokord: str,
        rm: str | None = None,
        from_datum: str | None = None,
        tom_datum: str | None = None,
        organ: str | None = None,
        parti: str | None = None,
        antal: int = 20,
    ) -> str:
        """
        Search Riksdagen documents.

        Args:
            sokord: Search term (required)
            rm: Parliamentary year (e.g. "2023/24")
            from_datum: From date (YYYY-MM-DD)
            tom_datum: To date (YYYY-MM-DD)
            organ: Committee (e.g. "FiU", "FöU", "SoU")
            parti: Party code (s, m, sd, c, v, kd, mp, l, -)
            antal: Max results (default 20, max 100)
        """
        if not sokord or not sokord.strip():
            return json.dumps(
                {"error": "Parameter 'sokord' är obligatorisk."},
                ensure_ascii=False,
            )

        try:
            documents = await riksdagen_service.search_documents(
                sokord=sokord.strip(),
                doktyp=definition.doktyp,
                rm=rm,
                from_datum=from_datum,
                tom_datum=tom_datum,
                organ=organ,
                parti=parti,
                antal=min(antal, 100),
            )

            if not documents:
                return json.dumps(
                    {
                        "query": sokord,
                        "results": [],
                        "count": 0,
                        "message": "Inga dokument hittades.",
                    },
                    ensure_ascii=False,
                )

            results = []
            for doc in documents:
                results.append(
                    {
                        "id": doc.id,
                        "doktyp": doc.doktyp,
                        "rm": doc.rm,
                        "beteckning": doc.beteckning,
                        "titel": doc.titel,
                        "datum": doc.datum,
                        "organ": doc.organ,
                        "dokument_url_html": doc.dokument_url_html,
                    }
                )

            tool_output = {
                "source": RIKSDAGEN_SOURCE,
                "source_url": RIKSDAGEN_SOURCE_URL,
                "query": sokord,
                "doktyp": definition.doktyp or "alla",
                "rm": rm,
                "organ": organ,
                "parti": parti,
                "results": results,
                "count": len(results),
            }

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=tool_output,
                title=f"{definition.name}: {sokord}",
                metadata={
                    "source": RIKSDAGEN_SOURCE,
                    "source_url": RIKSDAGEN_SOURCE_URL,
                    "query": sokord,
                    "doktyp": definition.doktyp or "alla",
                },
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service.serialize_external_document(
                    document, score=1.0
                )
                formatted_docs = format_documents_for_context([serialized])

            response_payload = {
                "query": sokord,
                "doktyp": definition.doktyp or "alla",
                "count": len(results),
                "results": formatted_docs if formatted_docs else results,
            }

            return json.dumps(response_payload, ensure_ascii=False)

        except httpx.HTTPError as exc:
            return json.dumps(
                {"error": f"Riksdagen API-fel: {exc!s}"},
                ensure_ascii=False,
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_dokument_tool)


def _build_riksdagen_status_tool(
    definition: RiksdagenToolDefinition,
    *,
    riksdagen_service: RiksdagenService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Build a document status tool."""
    description = _build_tool_description(definition)

    async def _status_tool(
        dok_id: str,
    ) -> str:
        """
        Get document status/history.

        Args:
            dok_id: Document ID (e.g. "H801123" for proposition 2023/24:123)
        """
        if not dok_id or not dok_id.strip():
            return json.dumps(
                {"error": "Parameter 'dok_id' är obligatorisk."},
                ensure_ascii=False,
            )

        try:
            status = await riksdagen_service.get_dokumentstatus(dok_id=dok_id.strip())

            if not status:
                return json.dumps(
                    {
                        "dok_id": dok_id,
                        "message": "Ingen status hittades.",
                    },
                    ensure_ascii=False,
                )

            tool_output = {
                "source": RIKSDAGEN_SOURCE,
                "source_url": RIKSDAGEN_SOURCE_URL,
                "dok_id": dok_id,
                "status": status,
            }

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=tool_output,
                title=f"{definition.name}: {dok_id}",
                metadata={
                    "source": RIKSDAGEN_SOURCE,
                    "source_url": RIKSDAGEN_SOURCE_URL,
                    "dok_id": dok_id,
                },
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service.serialize_external_document(
                    document, score=1.0
                )
                formatted_docs = format_documents_for_context([serialized])

            response_payload = {
                "dok_id": dok_id,
                "results": formatted_docs if formatted_docs else status,
            }

            return json.dumps(response_payload, ensure_ascii=False)

        except httpx.HTTPError as exc:
            return json.dumps(
                {"error": f"Riksdagen API-fel: {exc!s}"},
                ensure_ascii=False,
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_status_tool)


def build_riksdagen_dokument_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    riksdagen_service: RiksdagenService | None = None,
) -> dict[str, Any]:
    """Build registry of all Riksdagen document tools."""
    service = riksdagen_service or RiksdagenService()
    registry: dict[str, Any] = {}

    for definition in RIKSDAGEN_DOKUMENT_TOOL_DEFINITIONS:
        if definition.category == "riksdagen_status":
            builder = _build_riksdagen_status_tool
        else:
            builder = _build_riksdagen_dokument_tool

        registry[definition.tool_id] = builder(
            definition,
            riksdagen_service=service,
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )

    return registry
