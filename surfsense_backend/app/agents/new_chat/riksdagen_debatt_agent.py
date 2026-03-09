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
# DEBATT & VOTERING TOOLS (5 total)
# =============================================================================

RIKSDAGEN_DEBATT_TOOL_DEFINITIONS: list[RiksdagenToolDefinition] = [
    RiksdagenToolDefinition(
        tool_id="riksdag_anforanden",
        name="Riksdag Anföranden - Alla",
        description="Sök bland alla anföranden i kammaren.",
        keywords=["anförande", "anföranden", "tal", "debatt", "kammare"],
        example_queries=[
            "Anföranden om försvar 2024",
            "Debatt om skola i Riksdagen",
            "Vad sa Socialdemokraterna om vård?",
        ],
        category="riksdagen_anforanden",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_anforanden_debatt",
        name="Riksdag Anföranden - Debatt",
        description="Sök anföranden från olika debatttyper (allmän debatt, budgetdebatt, utrikesdebatt, etc.).",
        keywords=["debatt", "allmän", "budget", "utrikes", "anförande"],
        example_queries=[
            "Debatt om försvar 2024",
            "Budgetdebatt i Riksdagen",
            "Utrikesdebatt om NATO",
        ],
        anftyp="kam-ad,kam-bu,kam-ud",
        category="riksdagen_anforanden",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_anforanden_fragestund",
        name="Riksdag Anföranden - Frågestund",
        description="Sök anföranden från frågestunder.",
        keywords=["frågestund", "statsråd", "fråga"],
        example_queries=[
            "Frågestund med statsministern 2024",
            "Frågor till ministrar",
            "Statsrådsfrågestunder",
        ],
        anftyp="kam-fs,kam-sf",
        category="riksdagen_anforanden",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_voteringar",
        name="Riksdag Voteringar - Alla",
        description="Sök bland alla omröstningar i Riksdagen.",
        keywords=["votering", "voteringar", "omröstning", "röstning"],
        example_queries=[
            "Voteringar om budgeten 2024",
            "Hur röstade partierna om migration?",
            "Omröstningar i Riksdagen senaste året",
        ],
        category="riksdagen_voteringar",
    ),
    RiksdagenToolDefinition(
        tool_id="riksdag_voteringar_resultat",
        name="Riksdag Voteringar - Detaljerat resultat",
        description="Sök voteringar med detaljerade röstresultat per parti och ledamot.",
        keywords=["resultat", "röstresultat", "detaljerat", "parti"],
        example_queries=[
            "Detaljerat röstresultat för budgetomröstningen",
            "Hur röstade varje parti om migration?",
            "Resultat av omröstning 2024/25:1",
        ],
        category="riksdagen_voteringar",
    ),
]


def _build_tool_description(definition: RiksdagenToolDefinition) -> str:
    """Build tool description with examples."""
    examples = "\n".join(f"- {example}" for example in definition.example_queries)
    sections = [definition.description]
    sections.append(f"Exempel:\n{examples}")
    return "\n\n".join(sections)


def _build_riksdagen_anforande_tool(
    definition: RiksdagenToolDefinition,
    *,
    riksdagen_service: RiksdagenService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Build a speech search tool."""
    description = _build_tool_description(definition)

    async def _anforande_tool(
        sokord: str,
        rm: str | None = None,
        from_datum: str | None = None,
        tom_datum: str | None = None,
        parti: str | None = None,
        antal: int = 20,
    ) -> str:
        """
        Search Riksdagen speeches.

        Args:
            sokord: Search term (required)
            rm: Parliamentary year
            from_datum: From date (YYYY-MM-DD)
            tom_datum: To date (YYYY-MM-DD)
            parti: Party code
            antal: Max results (default 20)
        """
        if not sokord or not sokord.strip():
            return json.dumps(
                {"error": "Parameter 'sokord' är obligatorisk."},
                ensure_ascii=False,
            )

        try:
            anforanden = await riksdagen_service.search_anforanden(
                sokord=sokord.strip(),
                anftyp=definition.anftyp,
                rm=rm,
                from_datum=from_datum,
                tom_datum=tom_datum,
                parti=parti,
                antal=min(antal, 100),
            )

            if not anforanden:
                return json.dumps(
                    {
                        "query": sokord,
                        "results": [],
                        "count": 0,
                        "message": "Inga anföranden hittades.",
                    },
                    ensure_ascii=False,
                )

            results = []
            for anforande in anforanden:
                results.append(
                    {
                        "anforande_id": anforande.anforande_id,
                        "dok_id": anforande.dok_id,
                        "rm": anforande.rm,
                        "anftyp": anforande.anftyp,
                        "datum": anforande.datum,
                        "talare": anforande.talare,
                        "parti": anforande.parti,
                        "anforandetext": anforande.anforandetext[:500]
                        if anforande.anforandetext
                        else None,
                    }
                )

            tool_output = {
                "source": RIKSDAGEN_SOURCE,
                "source_url": RIKSDAGEN_SOURCE_URL,
                "query": sokord,
                "anftyp": definition.anftyp or "alla",
                "rm": rm,
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
    )(_anforande_tool)


def _build_riksdagen_votering_tool(
    definition: RiksdagenToolDefinition,
    *,
    riksdagen_service: RiksdagenService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Build a voting search tool."""
    description = _build_tool_description(definition)

    async def _votering_tool(
        sokord: str | None = None,
        rm: str | None = None,
        bet: str | None = None,
        punkt: str | None = None,
        from_datum: str | None = None,
        tom_datum: str | None = None,
        parti: str | None = None,
        valkrets: str | None = None,
        antal: int = 20,
    ) -> str:
        """
        Search Riksdagen voting records.

        Args:
            sokord: Search term
            rm: Parliamentary year
            bet: Committee report number
            punkt: Vote item number
            from_datum: From date (YYYY-MM-DD)
            tom_datum: To date (YYYY-MM-DD)
            parti: Party code
            valkrets: Electoral district
            antal: Max results (default 20)
        """
        try:
            voteringar = await riksdagen_service.search_voteringar(
                sokord=sokord,
                rm=rm,
                bet=bet,
                punkt=punkt,
                from_datum=from_datum,
                tom_datum=tom_datum,
                parti=parti,
                valkrets=valkrets,
                antal=min(antal, 100),
            )

            if not voteringar:
                return json.dumps(
                    {
                        "query": sokord,
                        "results": [],
                        "count": 0,
                        "message": "Inga voteringar hittades.",
                    },
                    ensure_ascii=False,
                )

            results = []
            for votering in voteringar:
                results.append(
                    {
                        "votering_id": votering.votering_id,
                        "rm": votering.rm,
                        "beteckning": votering.beteckning,
                        "punkt": votering.punkt,
                        "datum": votering.datum,
                        "rubrik": votering.rubrik,
                        "utfall": votering.utfall,
                        "ja_antal": votering.ja_antal,
                        "nej_antal": votering.nej_antal,
                        "avstår_antal": votering.avstår_antal,
                        "frånvarande_antal": votering.frånvarande_antal,
                    }
                )

            tool_output = {
                "source": RIKSDAGEN_SOURCE,
                "source_url": RIKSDAGEN_SOURCE_URL,
                "query": sokord,
                "rm": rm,
                "parti": parti,
                "results": results,
                "count": len(results),
            }

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=tool_output,
                title=f"{definition.name}: {sokord or 'Sökning'}",
                metadata={
                    "source": RIKSDAGEN_SOURCE,
                    "source_url": RIKSDAGEN_SOURCE_URL,
                    "query": sokord or "",
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
    )(_votering_tool)


def build_riksdagen_debatt_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    riksdagen_service: RiksdagenService | None = None,
) -> dict[str, Any]:
    """Build registry of all Riksdagen debate & voting tools."""
    service = riksdagen_service or RiksdagenService()
    registry: dict[str, Any] = {}

    for definition in RIKSDAGEN_DEBATT_TOOL_DEFINITIONS:
        if definition.category == "riksdagen_voteringar":
            builder = _build_riksdagen_votering_tool
        else:
            builder = _build_riksdagen_anforande_tool

        registry[definition.tool_id] = builder(
            definition,
            riksdagen_service=service,
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )

    return registry
