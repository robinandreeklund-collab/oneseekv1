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
    BolagsverketToolDefinition(
        tool_id="bolagsverket_info_basic",
        name="Bolagsverket Info - Grunddata",
        description="Grunddata om företag (namn, orgnr, form, registreringsdatum).",
        keywords=["bolagsverket", "grunddata", "orgnr", "foretag", "företag"],
        example_queries=[
            "Grunddata för Spotify AB",
            "Hämta grundinfo för 556703-7485",
        ],
        base_path="/foretag/{orgnr}",
        category="bolagsverket_info",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_info_status",
        name="Bolagsverket Info - Status",
        description="Status för bolag (aktivt, vilande, avvecklat).",
        keywords=["status", "aktiv", "vilande", "avvecklad", "bolag"],
        example_queries=[
            "Är företaget 556123-4567 aktivt?",
            "Status för Klarna AB",
        ],
        base_path="/foretag/{orgnr}/status",
        category="bolagsverket_info",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_info_adress",
        name="Bolagsverket Info - Adress",
        description="Registrerad adress och kontaktuppgifter för bolag.",
        keywords=["adress", "kontakt", "postadress", "besoksadress", "bolag"],
        example_queries=[
            "Adress till 556123-4567",
            "Var är H&M Hennes & Mauritz AB registrerat?",
        ],
        base_path="/foretag/{orgnr}/adress",
        category="bolagsverket_info",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_sok_namn",
        name="Bolagsverket Sök - Namn",
        description="Sök företag på namn.",
        keywords=["sok", "sök", "namn", "foretag", "företag"],
        example_queries=[
            "Sök företag som heter \"Nordic AB\"",
            "Bolag med namn som innehåller \"Bygg\"",
        ],
        base_path="/foretag?namn=",
        category="bolagsverket_sok",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_sok_orgnr",
        name="Bolagsverket Sök - Orgnr",
        description="Sök företag på organisationsnummer.",
        keywords=["orgnr", "organisationsnummer", "sok", "sök"],
        example_queries=[
            "Sök orgnr 556123-4567",
            "Bolagsverket orgnr 556703-7485",
        ],
        base_path="/foretag?orgnr=",
        category="bolagsverket_sok",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_sok_bransch",
        name="Bolagsverket Sök - Bransch",
        description="Sök företag efter bransch/SNI-kod.",
        keywords=["bransch", "sni", "näringsgren", "sok", "sök"],
        example_queries=[
            "Sök företag inom SNI 62.01",
            "Bolag i IT-konsultbranschen",
        ],
        base_path="/foretag?sni=",
        category="bolagsverket_sok",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_sok_region",
        name="Bolagsverket Sök - Region",
        description="Sök företag efter län/region.",
        keywords=["region", "lan", "län", "skane", "skåne", "sok", "sök"],
        example_queries=[
            "Sök bolag i Skåne län",
            "Företag i Västra Götalands län",
        ],
        base_path="/foretag?lan=",
        category="bolagsverket_sok",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_sok_status",
        name="Bolagsverket Sök - Status",
        description="Sök företag efter status (aktivt, vilande, avvecklat).",
        keywords=["status", "aktiv", "vilande", "avvecklad", "sok", "sök"],
        example_queries=[
            "Sök vilande bolag i Stockholm",
            "Bolag med status avvecklad",
        ],
        base_path="/foretag?status=",
        category="bolagsverket_sok",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_ekonomi_bokslut",
        name="Bolagsverket Ekonomi - Bokslut",
        description="Bokslut per år för ett bolag.",
        keywords=["bokslut", "ekonomi", "arsbokslut", "årsresultat"],
        example_queries=[
            "Bokslut för 556703-7485 2023",
            "Senaste bokslut för IKEA AB",
        ],
        base_path="/foretag/{orgnr}/bokslut",
        category="bolagsverket_ekonomi",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_ekonomi_arsredovisning",
        name="Bolagsverket Ekonomi - Årsredovisning",
        description="Årsredovisningar per år.",
        keywords=["arsredovisning", "årsredovisning", "ekonomi", "rapport"],
        example_queries=[
            "Årsredovisning för 556123-4567 2022",
            "Hämta årsredovisning för Spotify AB",
        ],
        base_path="/foretag/{orgnr}/arsredovisning",
        category="bolagsverket_ekonomi",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_ekonomi_nyckeltal",
        name="Bolagsverket Ekonomi - Nyckeltal",
        description="Nyckeltal (t.ex. omsättning, resultat, soliditet).",
        keywords=["nyckeltal", "omsattning", "omsättning", "resultat", "soliditet"],
        example_queries=[
            "Nyckeltal för 556703-7485 2023",
            "Nyckeltal för Volvo AB",
        ],
        base_path="/foretag/{orgnr}/nyckeltal",
        category="bolagsverket_ekonomi",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_styrelse_ledning",
        name="Bolagsverket Styrelse - Styrelse",
        description="Styrelse och ledning (roller och personer).",
        keywords=["styrelse", "ledning", "styrelseledamot", "vd"],
        example_queries=[
            "Styrelse för 556123-4567",
            "Vilka sitter i styrelsen för Klarna?",
        ],
        base_path="/foretag/{orgnr}/styrelse",
        category="bolagsverket_styrelse",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_styrelse_agarstruktur",
        name="Bolagsverket Styrelse - Ägare",
        description="Ägare och ägarstruktur.",
        keywords=["agare", "ägare", "agarstruktur", "owner"],
        example_queries=[
            "Ägare till 556703-7485",
            "Vem äger bolaget X?",
        ],
        base_path="/foretag/{orgnr}/agare",
        category="bolagsverket_styrelse",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_styrelse_firmatecknare",
        name="Bolagsverket Styrelse - Firmatecknare",
        description="Firmatecknare och behöriga signatörer.",
        keywords=["firmatecknare", "signator", "behörig"],
        example_queries=[
            "Firmatecknare för 556123-4567",
            "Vem får skriva under för bolaget?",
        ],
        base_path="/foretag/{orgnr}/firmatecknare",
        category="bolagsverket_styrelse",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_registrering_fskatt",
        name="Bolagsverket Registrering - F-skatt",
        description="F-skattestatus för bolag.",
        keywords=["f-skatt", "fskatt", "skattestatus"],
        example_queries=[
            "Har bolaget 556703-7485 F-skatt?",
            "F-skattestatus för företag X",
        ],
        base_path="/foretag/{orgnr}/fskatt",
        category="bolagsverket_registrering",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_registrering_moms",
        name="Bolagsverket Registrering - Moms",
        description="Momsregistrering för bolag.",
        keywords=["moms", "momsregistrering", "vat"],
        example_queries=[
            "Momsstatus för 556123-4567",
            "Är bolaget momsregistrerat?",
        ],
        base_path="/foretag/{orgnr}/moms",
        category="bolagsverket_registrering",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_registrering_konkurs",
        name="Bolagsverket Registrering - Konkurs",
        description="Konkursstatus och eventuella konkursärenden.",
        keywords=["konkurs", "insolvens", "bankruptcy"],
        example_queries=[
            "Är 556123-4567 i konkurs?",
            "Konkursstatus för bolag X",
        ],
        base_path="/foretag/{orgnr}/konkurs",
        category="bolagsverket_registrering",
    ),
    BolagsverketToolDefinition(
        tool_id="bolagsverket_registrering_andringar",
        name="Bolagsverket Registrering - Ändringar",
        description="Ändringshistorik (registreringsändringar).",
        keywords=["andringar", "ändringar", "registrering", "historik"],
        example_queries=[
            "Ändringshistorik för 556703-7485",
            "Senaste ändringar i bolaget",
        ],
        base_path="/foretag/{orgnr}/andringar",
        category="bolagsverket_registrering",
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
    service = BolagsverketService(api_key=api_key)

    @tool("bolagsverket_info_basic", description=BOLAGSVERKET_TOOL_DEFINITIONS[0].description)
    async def bolagsverket_info_basic(orgnr: str) -> dict[str, Any]:
        breaker = get_breaker("bolagsverket")
        if not breaker.can_execute():
            return {
                "status": "error",
                "error": f"Service {breaker.name} temporarily unavailable (circuit open)",
                "query": {"orgnr": orgnr},
            }
        try:
            data, cached = await service.get_company_basic(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_info_basic",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[0].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_info_basic",
                title=f"Bolagsverket grunddata {orgnr}",
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

    @tool("bolagsverket_info_status", description=BOLAGSVERKET_TOOL_DEFINITIONS[1].description)
    async def bolagsverket_info_status(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.get_company_status(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_info_status",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[1].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_info_status",
                title=f"Bolagsverket status {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_info_adress", description=BOLAGSVERKET_TOOL_DEFINITIONS[2].description)
    async def bolagsverket_info_adress(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.get_company_address(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_info_adress",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[2].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_info_adress",
                title=f"Bolagsverket adress {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_sok_namn", description=BOLAGSVERKET_TOOL_DEFINITIONS[3].description)
    async def bolagsverket_sok_namn(name: str, limit: int = 5, offset: int = 0) -> dict[str, Any]:
        try:
            data, cached = await service.search_by_name(name, limit=limit, offset=offset)
            payload = _build_payload(
                tool_name="bolagsverket_sok_namn",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[3].base_path,
                query={"namn": name, "limit": limit, "offset": offset},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_sok_namn",
                title=f"Bolagsverket sök namn {name}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_sok_orgnr", description=BOLAGSVERKET_TOOL_DEFINITIONS[4].description)
    async def bolagsverket_sok_orgnr(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.search_by_orgnr(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_sok_orgnr",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[4].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_sok_orgnr",
                title=f"Bolagsverket sök orgnr {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_sok_bransch", description=BOLAGSVERKET_TOOL_DEFINITIONS[5].description)
    async def bolagsverket_sok_bransch(sni: str, limit: int = 5, offset: int = 0) -> dict[str, Any]:
        try:
            data, cached = await service.search_by_industry(sni, limit=limit, offset=offset)
            payload = _build_payload(
                tool_name="bolagsverket_sok_bransch",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[5].base_path,
                query={"sni": sni, "limit": limit, "offset": offset},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_sok_bransch",
                title=f"Bolagsverket sök bransch {sni}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_sok_region", description=BOLAGSVERKET_TOOL_DEFINITIONS[6].description)
    async def bolagsverket_sok_region(region: str, limit: int = 5, offset: int = 0) -> dict[str, Any]:
        try:
            data, cached = await service.search_by_region(region, limit=limit, offset=offset)
            payload = _build_payload(
                tool_name="bolagsverket_sok_region",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[6].base_path,
                query={"lan": region, "limit": limit, "offset": offset},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_sok_region",
                title=f"Bolagsverket sök region {region}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_sok_status", description=BOLAGSVERKET_TOOL_DEFINITIONS[7].description)
    async def bolagsverket_sok_status(status: str, limit: int = 5, offset: int = 0) -> dict[str, Any]:
        try:
            data, cached = await service.search_by_status(status, limit=limit, offset=offset)
            payload = _build_payload(
                tool_name="bolagsverket_sok_status",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[7].base_path,
                query={"status": status, "limit": limit, "offset": offset},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_sok_status",
                title=f"Bolagsverket sök status {status}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_ekonomi_bokslut", description=BOLAGSVERKET_TOOL_DEFINITIONS[8].description)
    async def bolagsverket_ekonomi_bokslut(orgnr: str, year: int | None = None) -> dict[str, Any]:
        try:
            data, cached = await service.get_financial_statements(orgnr, year=year)
            payload = _build_payload(
                tool_name="bolagsverket_ekonomi_bokslut",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[8].base_path,
                query={"orgnr": orgnr, "ar": year},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_ekonomi_bokslut",
                title=f"Bolagsverket bokslut {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_ekonomi_arsredovisning", description=BOLAGSVERKET_TOOL_DEFINITIONS[9].description)
    async def bolagsverket_ekonomi_arsredovisning(orgnr: str, year: int | None = None) -> dict[str, Any]:
        try:
            data, cached = await service.get_annual_reports(orgnr, year=year)
            payload = _build_payload(
                tool_name="bolagsverket_ekonomi_arsredovisning",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[9].base_path,
                query={"orgnr": orgnr, "ar": year},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_ekonomi_arsredovisning",
                title=f"Bolagsverket årsredovisning {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_ekonomi_nyckeltal", description=BOLAGSVERKET_TOOL_DEFINITIONS[10].description)
    async def bolagsverket_ekonomi_nyckeltal(orgnr: str, year: int | None = None) -> dict[str, Any]:
        try:
            data, cached = await service.get_key_ratios(orgnr, year=year)
            payload = _build_payload(
                tool_name="bolagsverket_ekonomi_nyckeltal",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[10].base_path,
                query={"orgnr": orgnr, "ar": year},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_ekonomi_nyckeltal",
                title=f"Bolagsverket nyckeltal {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_styrelse_ledning", description=BOLAGSVERKET_TOOL_DEFINITIONS[11].description)
    async def bolagsverket_styrelse_ledning(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.get_board(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_styrelse_ledning",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[11].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_styrelse_ledning",
                title=f"Bolagsverket styrelse {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_styrelse_agarstruktur", description=BOLAGSVERKET_TOOL_DEFINITIONS[12].description)
    async def bolagsverket_styrelse_agarstruktur(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.get_owners(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_styrelse_agarstruktur",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[12].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_styrelse_agarstruktur",
                title=f"Bolagsverket ägare {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_styrelse_firmatecknare", description=BOLAGSVERKET_TOOL_DEFINITIONS[13].description)
    async def bolagsverket_styrelse_firmatecknare(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.get_signatories(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_styrelse_firmatecknare",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[13].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_styrelse_firmatecknare",
                title=f"Bolagsverket firmatecknare {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_registrering_fskatt", description=BOLAGSVERKET_TOOL_DEFINITIONS[14].description)
    async def bolagsverket_registrering_fskatt(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.get_f_tax_status(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_registrering_fskatt",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[14].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_registrering_fskatt",
                title=f"Bolagsverket F-skatt {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_registrering_moms", description=BOLAGSVERKET_TOOL_DEFINITIONS[15].description)
    async def bolagsverket_registrering_moms(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.get_vat_status(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_registrering_moms",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[15].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_registrering_moms",
                title=f"Bolagsverket moms {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_registrering_konkurs", description=BOLAGSVERKET_TOOL_DEFINITIONS[16].description)
    async def bolagsverket_registrering_konkurs(orgnr: str) -> dict[str, Any]:
        try:
            data, cached = await service.get_bankruptcy_status(orgnr)
            payload = _build_payload(
                tool_name="bolagsverket_registrering_konkurs",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[16].base_path,
                query={"orgnr": orgnr},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_registrering_konkurs",
                title=f"Bolagsverket konkurs {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    @tool("bolagsverket_registrering_andringar", description=BOLAGSVERKET_TOOL_DEFINITIONS[17].description)
    async def bolagsverket_registrering_andringar(
        orgnr: str, from_date: str | None = None, to_date: str | None = None
    ) -> dict[str, Any]:
        try:
            data, cached = await service.get_change_history(
                orgnr, from_date=from_date, to_date=to_date
            )
            payload = _build_payload(
                tool_name="bolagsverket_registrering_andringar",
                base_path=BOLAGSVERKET_TOOL_DEFINITIONS[17].base_path,
                query={"orgnr": orgnr, "from": from_date, "to": to_date},
                data=data,
                cached=cached,
            )
            await _ingest_output(
                connector_service=connector_service,
                tool_name="bolagsverket_registrering_andringar",
                title=f"Bolagsverket ändringar {orgnr}",
                payload=payload,
                search_space_id=search_space_id,
                user_id=user_id,
                thread_id=thread_id,
            )
            return payload
        except Exception as exc:
            return {"status": "error", "error": _format_error(exc)}

    registry = {
        "bolagsverket_info_basic": bolagsverket_info_basic,
        "bolagsverket_info_status": bolagsverket_info_status,
        "bolagsverket_info_adress": bolagsverket_info_adress,
        "bolagsverket_sok_namn": bolagsverket_sok_namn,
        "bolagsverket_sok_orgnr": bolagsverket_sok_orgnr,
        "bolagsverket_sok_bransch": bolagsverket_sok_bransch,
        "bolagsverket_sok_region": bolagsverket_sok_region,
        "bolagsverket_sok_status": bolagsverket_sok_status,
        "bolagsverket_ekonomi_bokslut": bolagsverket_ekonomi_bokslut,
        "bolagsverket_ekonomi_arsredovisning": bolagsverket_ekonomi_arsredovisning,
        "bolagsverket_ekonomi_nyckeltal": bolagsverket_ekonomi_nyckeltal,
        "bolagsverket_styrelse_ledning": bolagsverket_styrelse_ledning,
        "bolagsverket_styrelse_agarstruktur": bolagsverket_styrelse_agarstruktur,
        "bolagsverket_styrelse_firmatecknare": bolagsverket_styrelse_firmatecknare,
        "bolagsverket_registrering_fskatt": bolagsverket_registrering_fskatt,
        "bolagsverket_registrering_moms": bolagsverket_registrering_moms,
        "bolagsverket_registrering_konkurs": bolagsverket_registrering_konkurs,
        "bolagsverket_registrering_andringar": bolagsverket_registrering_andringar,
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
