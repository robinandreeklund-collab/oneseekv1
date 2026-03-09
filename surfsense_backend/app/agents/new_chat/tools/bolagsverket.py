from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.agents.new_chat.circuit_breaker import get_breaker
from app.services.bolagsverket_service import (
    BOLAGSVERKET_SOURCE,
    BolagsverketService,
)
from app.services.connector_service import ConnectorService


@dataclass(frozen=True)
class BolagsverketToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    base_path: str
    category: str


BOLAGSVERKET_TOOL_DEFINITIONS: list[BolagsverketToolDefinition] = [
    # ── Reduced from 18 to 6 tools to match gratis-API:t actual capabilities ──
    # See docs/API/Bolagsverket.md for full analysis.
    BolagsverketToolDefinition(
        tool_id="bolagsverket_sok_orgnr",
        name="Bolagsverket Sök - Organisationsnummer",
        description=(
            "Sök företag på organisationsnummer via Bolagsverket. "
            "Returnerar all tillgänglig grunddata: namn, juridisk form, "
            "adress, SNI-koder, styrelse, VD, F-skatt, moms, arbetsgivarstatus. "
            "OBS: Gratis-API:t stöder ENBART sökning på orgnr — inte namn."
        ),
        keywords=["orgnr", "organisationsnummer", "sok", "sök", "bolagsverket", "bolag", "företag"],
        example_queries=[
            "Sök orgnr 556123-4567",
            "Bolagsverket orgnr 556703-7485",
        ],
        base_path="/organisationer",
        category="bolagsverket_sok",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_info_grunddata",
        name="Bolagsverket Grunddata",
        description=(
            "Hämtar fullständig grunddata om ett företag: namn, juridisk form, "
            "registreringsdatum, adresser, SNI-koder, verksamhetsbeskrivning, "
            "aktiekapital, firmateckning, status. Kräver organisationsnummer."
        ),
        keywords=["bolagsverket", "grunddata", "foretag", "företag", "info", "företagsinfo"],
        example_queries=[
            "Grunddata för Spotify AB 556703-7485",
            "All information om bolaget 556123-4567",
        ],
        base_path="/organisationer",
        category="bolagsverket_info",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_funktionarer",
        name="Bolagsverket Funktionärer",
        description=(
            "Hämtar styrelse, VD och andra funktionärer för ett företag. "
            "Data extraheras från organisationssvaret. Kräver organisationsnummer."
        ),
        keywords=["styrelse", "ledning", "styrelseledamot", "vd", "funktionär", "firmatecknare"],
        example_queries=[
            "Styrelse för 556123-4567",
            "Vem är VD för bolaget?",
        ],
        base_path="/organisationer",
        category="bolagsverket_funktionarer",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_registrering",
        name="Bolagsverket Registreringsstatus",
        description=(
            "Hämtar registreringsstatus: F-skatt, momsregistrering, "
            "arbetsgivarstatus. Data extraheras från organisationssvaret. "
            "Kräver organisationsnummer."
        ),
        keywords=["f-skatt", "fskatt", "moms", "momsregistrering", "arbetsgivare", "registrering"],
        example_queries=[
            "Har bolaget 556703-7485 F-skatt?",
            "Momsstatus och arbetsgivarstatus för 556123-4567",
        ],
        base_path="/organisationer",
        category="bolagsverket_registrering",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_dokument_lista",
        name="Bolagsverket Dokumentlista",
        description=(
            "Listar tillgängliga dokument (årsredovisningar, bokslut m.m.) "
            "för ett företag. Returnerar dokumentreferenser — inte "
            "strukturerad finansdata. Kräver organisationsnummer."
        ),
        keywords=["dokument", "arsredovisning", "årsredovisning", "bokslut", "dokumentlista"],
        example_queries=[
            "Lista dokument för 556703-7485",
            "Årsredovisningar tillgängliga för Spotify",
        ],
        base_path="/dokumentlista",
        category="bolagsverket_dokument",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_dokument_hamta",
        name="Bolagsverket Hämta Dokument",
        description=(
            "Hämtar ett specifikt dokument (t.ex. årsredovisning) via dokument-ID. "
            "Dokument-ID fås från dokumentlistan."
        ),
        keywords=["dokument", "hamta", "hämta", "arsredovisning", "årsredovisning", "pdf"],
        example_queries=[
            "Hämta dokument med ID abc123",
            "Ladda ner årsredovisning från Bolagsverket",
        ],
        base_path="/dokument",
        category="bolagsverket_dokument",
    ),
]


def _build_payload(
    *,
    tool_name: str,
    base_path: str,
    query: dict[str, Any],
    data: dict[str, Any],
    cached: bool,
) -> dict[str, Any]:
    return {
        "status": "success",
        "tool": tool_name,
        "source": BOLAGSVERKET_SOURCE,
        "base_path": base_path,
        "query": query,
        "cached": cached,
        "data": data,
    }


def _format_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return type(exc).__name__


async def _ingest_output(
    *,
    connector_service: ConnectorService | None,
    tool_name: str,
    title: str,
    payload: dict[str, Any],
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
) -> None:
    if not connector_service:
        return
    await connector_service.ingest_tool_output(
        tool_name=tool_name,
        tool_output=payload,
        title=title,
        metadata={
            "source": BOLAGSVERKET_SOURCE,
            "base_path": payload.get("base_path"),
            "query": payload.get("query"),
        },
        user_id=user_id,
        origin_search_space_id=search_space_id,
        thread_id=thread_id,
    )


def build_bolagsverket_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    api_key: str | None = None,
) -> dict[str, BaseTool]:
    """Build registry of 6 Bolagsverket tools matching gratis-API capabilities."""
    service = BolagsverketService(api_key=api_key)

    async def _safe_call(tool_name, title, query, coro, base_path="/organisationer"):
        """Common error handling + ingestion wrapper."""
        breaker = get_breaker("bolagsverket")
        if not breaker.can_execute():
            return {
                "status": "error",
                "error": f"Service {breaker.name} temporarily unavailable (circuit open)",
                "query": query,
            }
        try:
            data, cached = await coro
            payload = _build_payload(
                tool_name=tool_name,
                base_path=base_path,
                query=query,
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name=tool_name,
                title=title,
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            breaker.record_success()
            return payload
        except Exception as exc:
            breaker.record_failure()
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_sok_orgnr", description=BOLAGSVERKET_TOOL_DEFINITIONS[0].description)
    async def bolagsverket_sok_orgnr(orgnr: str) -> dict[str, Any]:
        """Sök företag på organisationsnummer."""
        return await _safe_call(
            "bolagsverket_sok_orgnr",
            f"Bolagsverket sök orgnr {orgnr}",
            {"orgnr": orgnr},
            service.search_by_orgnr(orgnr),
        )

    @tool("bolagsverket_info_grunddata", description=BOLAGSVERKET_TOOL_DEFINITIONS[1].description)
    async def bolagsverket_info_grunddata(orgnr: str) -> dict[str, Any]:
        """Hämta fullständig grunddata om ett företag."""
        return await _safe_call(
            "bolagsverket_info_grunddata",
            f"Bolagsverket grunddata {orgnr}",
            {"orgnr": orgnr},
            service.get_organisationer(orgnr=orgnr),
        )

    @tool("bolagsverket_funktionarer", description=BOLAGSVERKET_TOOL_DEFINITIONS[2].description)
    async def bolagsverket_funktionarer(orgnr: str) -> dict[str, Any]:
        """Hämta styrelse, VD och funktionärer."""
        return await _safe_call(
            "bolagsverket_funktionarer",
            f"Bolagsverket funktionärer {orgnr}",
            {"orgnr": orgnr},
            service.get_organisationer(orgnr=orgnr),
        )

    @tool("bolagsverket_registrering", description=BOLAGSVERKET_TOOL_DEFINITIONS[3].description)
    async def bolagsverket_registrering(orgnr: str) -> dict[str, Any]:
        """Hämta registreringsstatus (F-skatt, moms, arbetsgivare)."""
        return await _safe_call(
            "bolagsverket_registrering",
            f"Bolagsverket registrering {orgnr}",
            {"orgnr": orgnr},
            service.get_organisationer(orgnr=orgnr),
        )

    @tool("bolagsverket_dokument_lista", description=BOLAGSVERKET_TOOL_DEFINITIONS[4].description)
    async def bolagsverket_dokument_lista(orgnr: str) -> dict[str, Any]:
        """Lista tillgängliga dokument för ett företag."""
        return await _safe_call(
            "bolagsverket_dokument_lista",
            f"Bolagsverket dokumentlista {orgnr}",
            {"orgnr": orgnr},
            service.get_dokumentlista(orgnr=orgnr),
            base_path="/dokumentlista",
        )

    @tool("bolagsverket_dokument_hamta", description=BOLAGSVERKET_TOOL_DEFINITIONS[5].description)
    async def bolagsverket_dokument_hamta(dokument_id: str) -> dict[str, Any]:
        """Hämta ett specifikt dokument via dokument-ID."""
        return await _safe_call(
            "bolagsverket_dokument_hamta",
            f"Bolagsverket dokument {dokument_id}",
            {"dokument_id": dokument_id},
            service.get_dokument(dokument_id),
            base_path="/dokument",
        )

    registry = {
        "bolagsverket_sok_orgnr": bolagsverket_sok_orgnr,
        "bolagsverket_info_grunddata": bolagsverket_info_grunddata,
        "bolagsverket_funktionarer": bolagsverket_funktionarer,
        "bolagsverket_registrering": bolagsverket_registrering,
        "bolagsverket_dokument_lista": bolagsverket_dokument_lista,
        "bolagsverket_dokument_hamta": bolagsverket_dokument_hamta,
    }
    return registry


def create_bolagsverket_tool(
    definition: BolagsverketToolDefinition,
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    api_key: str | None = None,
) -> BaseTool:
    registry = build_bolagsverket_tool_registry(
        connector_service=connector_service,
        search_space_id=search_space_id,
        user_id=user_id,
        thread_id=thread_id,
        api_key=api_key,
    )
    return registry[definition.tool_id]
