from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.tools import tool

from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.connector_service import ConnectorService
from app.services.riksdagen_service import (
    RIKSDAGEN_SOURCE,
    RIKSDAGEN_SOURCE_URL,
    RiksdagenService,
)


@dataclass(frozen=True)
class RiksdagenToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    doktyp: str | None = None  # Document type filter for sub-tools
    anftyp: str | None = None  # Speech type filter for sub-tools
    category: str = "riksdagen"


# =============================================================================
# TOP-LEVEL TOOLS (5)
# =============================================================================

RIKSDAGEN_TOP_LEVEL_TOOLS: list[RiksdagenToolDefinition] = [
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


# =============================================================================
# DOKUMENT SUB-TOOLS (12)
# =============================================================================

RIKSDAGEN_DOKUMENT_SUBTOOLS: list[RiksdagenToolDefinition] = [
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
]


# =============================================================================
# ANFÖRANDE SUB-TOOLS (2)
# =============================================================================

RIKSDAGEN_ANFORANDE_SUBTOOLS: list[RiksdagenToolDefinition] = [
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
]


# =============================================================================
# LEDAMOT SUB-TOOLS (2)
# =============================================================================

RIKSDAGEN_LEDAMOT_SUBTOOLS: list[RiksdagenToolDefinition] = [
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
]


# =============================================================================
# VOTERING SUB-TOOLS (1)
# =============================================================================

RIKSDAGEN_VOTERING_SUBTOOLS: list[RiksdagenToolDefinition] = [
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


# Combine all tool definitions
RIKSDAGEN_TOOL_DEFINITIONS: list[RiksdagenToolDefinition] = (
    RIKSDAGEN_TOP_LEVEL_TOOLS
    + RIKSDAGEN_DOKUMENT_SUBTOOLS
    + RIKSDAGEN_ANFORANDE_SUBTOOLS
    + RIKSDAGEN_LEDAMOT_SUBTOOLS
    + RIKSDAGEN_VOTERING_SUBTOOLS
)


# =============================================================================
# TOOL BUILDERS
# =============================================================================


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
                ensure_ascii=False
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

            # Prepare results
            results = []
            for doc in documents:
                results.append({
                    "id": doc.id,
                    "doktyp": doc.doktyp,
                    "rm": doc.rm,
                    "beteckning": doc.beteckning,
                    "titel": doc.titel,
                    "datum": doc.datum,
                    "organ": doc.organ,
                    "dokument_url_html": doc.dokument_url_html,
                })

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

            # Ingest for citations
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
                serialized = connector_service._serialize_external_document(
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
                ensure_ascii=False
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_dokument_tool)


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
                results.append({
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
                })

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
                serialized = connector_service._serialize_external_document(
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
                ensure_ascii=False
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_votering_tool)


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
                results.append({
                    "intressent_id": ledamot.intressent_id,
                    "fornamn": ledamot.fornamn,
                    "efternamn": ledamot.efternamn,
                    "parti": ledamot.parti,
                    "valkrets": ledamot.valkrets,
                    "status": ledamot.status,
                    "bild_url": ledamot.bild_url,
                })

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
                serialized = connector_service._serialize_external_document(
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
                ensure_ascii=False
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_ledamot_tool)


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
                ensure_ascii=False
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
                results.append({
                    "anforande_id": anforande.anforande_id,
                    "dok_id": anforande.dok_id,
                    "rm": anforande.rm,
                    "anftyp": anforande.anftyp,
                    "datum": anforande.datum,
                    "talare": anforande.talare,
                    "parti": anforande.parti,
                    "anforandetext": anforande.anforandetext[:500] if anforande.anforandetext else None,
                })

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
                serialized = connector_service._serialize_external_document(
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
                ensure_ascii=False
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_anforande_tool)


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
                ensure_ascii=False
            )

        try:
            status = await riksdagen_service.get_dokumentstatus(
                dok_id=dok_id.strip()
            )

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
                serialized = connector_service._serialize_external_document(
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
                ensure_ascii=False
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_status_tool)


def build_riksdagen_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    riksdagen_service: RiksdagenService | None = None,
) -> dict[str, Any]:
    """Build registry of all Riksdagen tools."""
    service = riksdagen_service or RiksdagenService()
    registry: dict[str, Any] = {}
    
    for definition in RIKSDAGEN_TOOL_DEFINITIONS:
        # Determine which builder to use based on category
        if definition.category in ("riksdagen_dokument", "riksdagen"):
            builder = _build_riksdagen_dokument_tool
        elif definition.category == "riksdagen_voteringar":
            builder = _build_riksdagen_votering_tool
        elif definition.category == "riksdagen_ledamoter":
            builder = _build_riksdagen_ledamot_tool
        elif definition.category == "riksdagen_anforanden":
            builder = _build_riksdagen_anforande_tool
        elif definition.category == "riksdagen_status":
            builder = _build_riksdagen_status_tool
        else:
            # Default to document tool
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
