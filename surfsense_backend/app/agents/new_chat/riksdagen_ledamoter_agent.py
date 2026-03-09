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
# LEDAMÖTER & KALENDER TOOLS (6 total)
# =============================================================================

RIKSDAGEN_LEDAMOTER_TOOL_DEFINITIONS: list[RiksdagenToolDefinition] = [
    RiksdagenToolDefinition(
        tool_id="riksdag_ledamoter",
        name="Riksdag Ledamöter - Alla",
        description="Sök bland alla riksdagsledamöter.",
        keywords=["ledamot", "ledamöter", "riksdagsledamot", "politiker"],
        example_queries=[
            "Ledamöter från Socialdemokraterna",
            "Ledamöter i Stockholms län",
            "Sök ledamot Anders Andersson",
        ],
        category="riksdagen_ledamoter",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_ledamoter_parti",
        name="Riksdag Ledamöter - Parti",
        description="Sök ledamöter filtrerat på parti.",
        keywords=["parti", "socialdemokraterna", "moderaterna", "sverigedemokraterna"],
        example_queries=[
            "Socialdemokraternas ledamöter",
            "Moderater i Riksdagen",
            "SD:s riksdagsledamöter",
        ],
        category="riksdagen_ledamoter",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_ledamoter_valkrets",
        name="Riksdag Ledamöter - Valkrets",
        description="Sök ledamöter filtrerat på valkrets.",
        keywords=["valkrets", "län", "stockholms", "skåne", "västra"],
        example_queries=[
            "Ledamöter från Stockholms län",
            "Riksdagsledamöter i Skåne",
            "Ledamöter från Västra Götaland",
        ],
        category="riksdagen_ledamoter",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_kalender",
        name="Riksdag Kalender - Alla händelser",
        description="Sök i Riksdagens kalender: debatter, utskottsmöten, voteringar, frågestunder och andra aktiviteter.",
        keywords=["kalender", "schema", "möte", "sammanträde", "händelse", "agenda"],
        example_queries=[
            "Vad händer i Riksdagen nästa vecka?",
            "Kommande debatter i kammaren",
            "Utskottsmöten denna månad",
        ],
        category="riksdagen_kalender",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_kalender_kammare",
        name="Riksdag Kalender - Kammaren",
        description="Sök kammaraktiviteter: debatter, voteringar, frågestunder, interpellationsdebatter.",
        keywords=["kammare", "debatt", "votering", "frågestund", "plenum"],
        example_queries=[
            "Kommande voteringar i kammaren",
            "Planerade debatter denna vecka",
            "Frågestunder med statsministern",
        ],
        category="riksdagen_kalender",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_kalender_utskott",
        name="Riksdag Kalender - Utskott",
        description="Sök utskottsmöten och EU-nämndsmöten.",
        keywords=["utskott", "EU-nämnden", "sammanträde", "kommitté"],
        example_queries=[
            "Finansutskottets möten",
            "EU-nämndens sammanträden",
            "Försvarsutskottets agenda",
        ],
        category="riksdagen_kalender",
    ),
]


def _build_tool_description(definition: RiksdagenToolDefinition) -> str:
    """Build tool description with examples."""
    examples = "\n".join(f"- {example}" for example in definition.example_queries)
    sections = [definition.description]
    sections.append(f"Exempel:\n{examples}")
    return "\n\n".join(sections)


def _build_riksdagen_ledamot_tool(
    definition: RiksdagenToolDefinition,
    *,
    riksdagen_service: RiksdagenService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Build a member search tool."""
    description = _build_tool_description(definition)

    async def _ledamot_tool(
        fnamn: str | None = None,
        enamn: str | None = None,
        parti: str | None = None,
        valkrets: str | None = None,
        antal: int = 20,
    ) -> str:
        """
        Search Riksdagen members.

        Args:
            fnamn: First name
            enamn: Last name
            parti: Party code (s, m, sd, c, v, kd, mp, l, -)
            valkrets: Electoral district
            antal: Max results (default 20)
        """
        try:
            ledamoter = await riksdagen_service.search_ledamoter(
                fnamn=fnamn,
                enamn=enamn,
                parti=parti,
                valkrets=valkrets,
                antal=min(antal, 100),
            )

            if not ledamoter:
                return json.dumps(
                    {
                        "results": [],
                        "count": 0,
                        "message": "Inga ledamöter hittades.",
                    },
                    ensure_ascii=False,
                )

            results = []
            for ledamot in ledamoter:
                results.append(
                    {
                        "intressent_id": ledamot.intressent_id,
                        "fornamn": ledamot.fornamn,
                        "efternamn": ledamot.efternamn,
                        "parti": ledamot.parti,
                        "valkrets": ledamot.valkrets,
                        "status": ledamot.status,
                        "bild_url": ledamot.bild_url,
                    }
                )

            tool_output = {
                "source": RIKSDAGEN_SOURCE,
                "source_url": RIKSDAGEN_SOURCE_URL,
                "parti": parti,
                "valkrets": valkrets,
                "results": results,
                "count": len(results),
            }

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=tool_output,
                title=f"{definition.name}: {parti or valkrets or 'Sökning'}",
                metadata={
                    "source": RIKSDAGEN_SOURCE,
                    "source_url": RIKSDAGEN_SOURCE_URL,
                    "parti": parti or "",
                    "valkrets": valkrets or "",
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
                "parti": parti,
                "valkrets": valkrets,
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
    )(_ledamot_tool)


# Mapping from calendar tool_id to the org parameter for the API
_KALENDER_ORG_MAP: dict[str, str | None] = {
    "riksdag_kalender": None,
    "riksdag_kalender_kammare": "kamm",
    "riksdag_kalender_utskott": None,  # utskott uses org=specific committee
}


def _build_riksdagen_kalender_tool(
    definition: RiksdagenToolDefinition,
    *,
    riksdagen_service: RiksdagenService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Build a calendar search tool."""
    description = _build_tool_description(definition)
    default_org = _KALENDER_ORG_MAP.get(definition.tool_id)

    async def _kalender_tool(
        from_datum: str | None = None,
        tom_datum: str | None = None,
        org: str | None = None,
        sok: str | None = None,
        antal: int = 30,
    ) -> str:
        """
        Search Riksdagen calendar events.

        Args:
            from_datum: From date (YYYY-MM-DD)
            tom_datum: To date (YYYY-MM-DD)
            org: Organisation/committee (e.g. "kamm", "FiU", "FöU", "AU", "SoU")
            sok: Search term
            antal: Max results (default 30)
        """
        effective_org = org or default_org

        try:
            entries = await riksdagen_service.search_kalender(
                from_datum=from_datum,
                tom_datum=tom_datum,
                org=effective_org,
                sok=sok,
                antal=min(antal, 100),
            )

            if not entries:
                return json.dumps(
                    {
                        "results": [],
                        "count": 0,
                        "message": "Inga kalenderhändelser hittades.",
                    },
                    ensure_ascii=False,
                )

            results = []
            for entry in entries:
                results.append(
                    {
                        "uid": entry.uid,
                        "summary": entry.summary,
                        "categories": entry.categories,
                        "location": entry.location,
                        "dtstart": entry.dtstart,
                        "dtend": entry.dtend,
                        "description": entry.description,
                        "rm": entry.rm,
                    }
                )

            tool_output = {
                "source": RIKSDAGEN_SOURCE,
                "source_url": RIKSDAGEN_SOURCE_URL,
                "from_datum": from_datum,
                "tom_datum": tom_datum,
                "org": effective_org,
                "results": results,
                "count": len(results),
            }

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=tool_output,
                title=f"{definition.name}: {sok or effective_org or 'Sökning'}",
                metadata={
                    "source": RIKSDAGEN_SOURCE,
                    "source_url": RIKSDAGEN_SOURCE_URL,
                    "org": effective_org or "",
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
                "org": effective_org,
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
    )(_kalender_tool)


def build_riksdagen_ledamoter_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    riksdagen_service: RiksdagenService | None = None,
) -> dict[str, Any]:
    """Build registry of all Riksdagen member & calendar tools."""
    service = riksdagen_service or RiksdagenService()
    registry: dict[str, Any] = {}

    for definition in RIKSDAGEN_LEDAMOTER_TOOL_DEFINITIONS:
        if definition.category == "riksdagen_kalender":
            builder = _build_riksdagen_kalender_tool
        else:
            builder = _build_riksdagen_ledamot_tool

        registry[definition.tool_id] = builder(
            definition,
            riksdagen_service=service,
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )

    return registry
