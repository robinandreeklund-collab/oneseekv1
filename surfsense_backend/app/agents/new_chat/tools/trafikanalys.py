"""Trafikanalys API tools — Swedish transport statistics.

Follows the same pattern as riksbank.py / elpris.py:
- ToolDefinition dataclass
- List of TRAFIKANALYS_TOOL_DEFINITIONS
- Factory function create_trafikanalys_tool()

Source: Trafikanalys (trafa.se)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.agents.new_chat.circuit_breaker import get_breaker
from app.services.trafikanalys_service import (
    DIMENSION_AR,
    PRODUCT_BUSSAR,
    PRODUCT_FORDON_PA_VAG,
    PRODUCT_JARNVAG_TRANSPORT,
    PRODUCT_KORKORT,
    PRODUCT_LASTBILAR,
    PRODUCT_LUFTFART,
    PRODUCT_MOTORCYKLAR,
    PRODUCT_PERSONBILAR,
    PRODUCT_REGIONAL_LINJETRAFIK,
    PRODUCT_SJOTRAFIK,
    PRODUCT_TRAFIKARBETE,
    PRODUCT_VAGTRAFIK_SKADOR,
    TRAFIKANALYS_SOURCE,
    TrafikanalysService,
)


@dataclass(frozen=True)
class TrafikanalysToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str
    base_path: str


TRAFIKANALYS_TOOL_DEFINITIONS: list[TrafikanalysToolDefinition] = [
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_fordon_personbilar",
        name="Trafikanalys Personbilar",
        description=(
            "Hämtar statistik om personbilar i Sverige från Trafikanalys: "
            "antal i trafik, nyregistreringar, avregistreringar, uppdelat på "
            "drivmedel, ägarkategori, årsmodell m.m."
        ),
        keywords=[
            "personbilar",
            "bilar",
            "fordon",
            "bilbestånd",
            "bilpark",
            "nyregistrering",
            "avregistrering",
            "drivmedel",
            "elbil",
            "dieselbil",
            "bensinbil",
            "laddhybrid",
            "trafikanalys",
        ],
        example_queries=[
            "Hur många personbilar finns i Sverige?",
            "Antal elbilar i trafik 2024",
            "Nyregistrerade bilar senaste året",
            "Fördelning av drivmedel för personbilar",
        ],
        category="trafikanalys_vagtrafik",
        base_path="/api/data?query=t10016",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_fordon_lastbilar",
        name="Trafikanalys Lastbilar",
        description=(
            "Hämtar statistik om lastbilar i Sverige från Trafikanalys: "
            "antal i trafik, nyregistreringar, avregistreringar."
        ),
        keywords=[
            "lastbilar",
            "lastbil",
            "truck",
            "tunga fordon",
            "godstransport",
            "lastbilsbestånd",
            "trafikanalys",
        ],
        example_queries=[
            "Hur många lastbilar finns i Sverige?",
            "Nyregistrerade lastbilar per år",
        ],
        category="trafikanalys_vagtrafik",
        base_path="/api/data?query=t10013",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_fordon_bussar",
        name="Trafikanalys Bussar",
        description=(
            "Hämtar statistik om bussar i Sverige från Trafikanalys: "
            "antal i trafik, nyregistreringar, avregistreringar."
        ),
        keywords=[
            "bussar",
            "buss",
            "kollektivtrafik",
            "busstrafik",
            "bussbestånd",
            "trafikanalys",
        ],
        example_queries=[
            "Hur många bussar finns i Sverige?",
            "Antal bussar i trafik per år",
        ],
        category="trafikanalys_vagtrafik",
        base_path="/api/data?query=t10011",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_fordon_motorcyklar",
        name="Trafikanalys Motorcyklar",
        description=(
            "Hämtar statistik om motorcyklar i Sverige från Trafikanalys: "
            "antal i trafik, nyregistreringar, avregistreringar."
        ),
        keywords=[
            "motorcyklar",
            "motorcykel",
            "mc",
            "tvåhjuling",
            "motorcykelbestånd",
            "trafikanalys",
        ],
        example_queries=[
            "Hur många motorcyklar finns i Sverige?",
            "Nyregistrerade motorcyklar per år",
        ],
        category="trafikanalys_vagtrafik",
        base_path="/api/data?query=t10014",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_fordon_oversikt",
        name="Trafikanalys Fordonsöversikt",
        description=(
            "Hämtar översiktsstatistik för alla fordonsslag i Sverige: "
            "personbilar, lastbilar, bussar, motorcyklar, mopeder, "
            "släpvagnar, traktorer och terrängskotrar."
        ),
        keywords=[
            "fordonsstatistik",
            "fordonsöversikt",
            "alla fordon",
            "fordonsbestånd",
            "fordonspark",
            "trafikanalys",
        ],
        example_queries=[
            "Hur många fordon finns i Sverige totalt?",
            "Översikt av fordonsbeståndet",
            "Alla fordonsslag i Sverige",
        ],
        category="trafikanalys_vagtrafik",
        base_path="/api/data?query=t10010",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_korkort",
        name="Trafikanalys Körkort",
        description=(
            "Hämtar körkortsstatistik från Trafikanalys: antal körkort "
            "per behörighetsklass, ålder och kön."
        ),
        keywords=[
            "körkort",
            "körkortsbehörighet",
            "behörighet",
            "AM",
            "A",
            "B",
            "C",
            "D",
            "CE",
            "körkortsinnehavare",
            "trafikanalys",
        ],
        example_queries=[
            "Hur många har körkort i Sverige?",
            "Körkortsstatistik per åldersgrupp",
        ],
        category="trafikanalys_vagtrafik",
        base_path="/api/data?query=t10012",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_trafikarbete",
        name="Trafikanalys Trafikarbete",
        description=(
            "Hämtar trafikarbete (fordonskilometer) på väg i Sverige "
            "från Trafikanalys, uppdelat per fordonsslag och vägtyp."
        ),
        keywords=[
            "trafikarbete",
            "fordonskilometer",
            "trafikvolym",
            "vägkilometer",
            "trafikflöde",
            "trafikmängd",
            "trafikanalys",
        ],
        example_queries=[
            "Hur många fordonskilometer körs i Sverige per år?",
            "Trafikarbete per fordonsslag",
        ],
        category="trafikanalys_vagtrafik",
        base_path="/api/data?query=t0401",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_vagtrafik_skador",
        name="Trafikanalys Vägtrafikskador",
        description=(
            "Hämtar statistik om vägtrafikolyckor och trafikskador "
            "i Sverige från Trafikanalys: döda, svårt skadade, "
            "lindrigt skadade per trafikantgrupp och år."
        ),
        keywords=[
            "trafikolyckor",
            "trafikskador",
            "trafikdöda",
            "olycksstatistik",
            "vägtrafikskador",
            "svårt skadade",
            "lindrigt skadade",
            "trafiksäkerhet",
            "trafikanalys",
        ],
        example_queries=[
            "Hur många trafikdöda per år i Sverige?",
            "Trafikolyckor senaste året",
            "Utveckling av trafikskador över tid",
        ],
        category="trafikanalys_vagtrafik",
        base_path="/api/data?query=t1004",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_sjotrafik",
        name="Trafikanalys Sjötrafik",
        description=(
            "Hämtar sjötrafikstatistik från Trafikanalys: "
            "godsmängder, passagerare och anlöp i svenska hamnar."
        ),
        keywords=[
            "sjötrafik",
            "sjöfart",
            "hamn",
            "hamnar",
            "gods",
            "passagerare",
            "fartyg",
            "maritim",
            "trafikanalys",
        ],
        example_queries=[
            "Sjötrafikstatistik i Sverige",
            "Godsmängder i svenska hamnar",
            "Passagerare via svenska hamnar per år",
        ],
        category="trafikanalys_sjofart",
        base_path="/api/data?query=t0802",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_luftfart",
        name="Trafikanalys Luftfart",
        description=(
            "Hämtar luftfartsstatistik från Trafikanalys: "
            "passagerare, flygningar och gods på svenska flygplatser."
        ),
        keywords=[
            "luftfart",
            "flyg",
            "flygplatser",
            "flygpassagerare",
            "flygningar",
            "flygtrafik",
            "aviation",
            "trafikanalys",
        ],
        example_queries=[
            "Flygpassagerare i Sverige per år",
            "Luftfartsstatistik senaste året",
            "Antal flygningar på svenska flygplatser",
        ],
        category="trafikanalys_luftfart",
        base_path="/api/data?query=t0501",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_jarnvag",
        name="Trafikanalys Järnväg",
        description=(
            "Hämtar järnvägsstatistik från Trafikanalys: "
            "persontransporter, godstransporter och olyckor på järnväg."
        ),
        keywords=[
            "järnväg",
            "tåg",
            "tågtrafik",
            "järnvägstransport",
            "persontåg",
            "godståg",
            "järnvägsolyckor",
            "trafikanalys",
        ],
        example_queries=[
            "Järnvägstransporter i Sverige per år",
            "Antal tågresenärer per år",
            "Bantrafik olycksstatistik",
        ],
        category="trafikanalys_jarnvag",
        base_path="/api/data?query=t0603",
    ),
    TrafikanalysToolDefinition(
        tool_id="trafikanalys_kollektivtrafik",
        name="Trafikanalys Kollektivtrafik",
        description=(
            "Hämtar kollektivtrafikstatistik från Trafikanalys: "
            "regional linjetrafik, färdtjänst, kommersiell linjetrafik."
        ),
        keywords=[
            "kollektivtrafik",
            "regional trafik",
            "linjetrafik",
            "färdtjänst",
            "riksfärdtjänst",
            "busstrafik",
            "trafikanalys",
        ],
        example_queries=[
            "Kollektivtrafikstatistik i Sverige",
            "Regional linjetrafik per år",
        ],
        category="trafikanalys_kollektivtrafik",
        base_path="/api/data?query=t1203",
    ),
]


def _build_payload(
    *,
    tool_name: str,
    base_path: str,
    query: dict[str, Any],
    data: Any,
    cached: bool,
) -> dict[str, Any]:
    return {
        "status": "success",
        "tool": tool_name,
        "source": TRAFIKANALYS_SOURCE,
        "base_path": base_path,
        "query": query,
        "cached": cached,
        "data": data,
    }


def _format_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message if message else type(exc).__name__


def _extract_rows(data: Any) -> list[dict[str, str]]:
    """Extract simplified rows from Trafikanalys data response."""
    rows = data.get("Rows", []) if isinstance(data, dict) else []
    result = []
    for row in rows:
        cells = row.get("Cell", [])
        record = {}
        for cell in cells:
            col = cell.get("Column", "")
            value = cell.get("Value", "")
            formatted = cell.get("FormattedValue", value)
            record[col] = formatted
        result.append(record)
    return result


def _simplify_response(data: Any) -> dict[str, Any]:
    """Simplify Trafikanalys response for LLM consumption."""
    if not isinstance(data, dict):
        return {"raw": data}

    columns = []
    for col in data.get("Header", {}).get("Column", []):
        columns.append(
            {
                "name": col.get("Name", ""),
                "label": col.get("Value", col.get("Name", "")),
                "type": col.get("Type", ""),
                "unit": col.get("Unit", ""),
            }
        )

    rows = _extract_rows(data)
    errors = data.get("Errors")

    result: dict[str, Any] = {
        "product": data.get("Name", ""),
        "product_code": data.get("OriginalName", ""),
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }
    if errors:
        result["errors"] = errors
    notes = data.get("Notes")
    if notes:
        result["notes"] = notes
    return result


def create_trafikanalys_tool(definition: TrafikanalysToolDefinition) -> BaseTool:
    """Factory that creates a LangChain tool for the given Trafikanalys definition."""

    service = TrafikanalysService()

    # ── Personbilar ──
    if definition.tool_id == "trafikanalys_fordon_personbilar":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_fordon_personbilar(
            measure: str = "itrfslut",
            years: str = "senaste",
            breakdown: str = "",
        ) -> dict[str, Any]:
            """Hämta personbilsstatistik.

            measure: Mått — itrfslut (i trafik), nyregunder (nyregistreringar),
                     avregunder (avregistreringar), avstslut (avställda).
            years: År att hämta, kommaseparerade (t.ex. "2023,2024") eller "senaste".
            breakdown: Valfri dimension för uppdelning (t.ex. "drivm" för drivmedel,
                       "agarkat" för ägarkategori).
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                parts = [measure, f"{DIMENSION_AR}:{years}"]
                if breakdown:
                    parts.append(breakdown)
                query = service.build_query(PRODUCT_PERSONBILAR, *parts)
                data, cached = await service.get_data(query)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={
                        "product": PRODUCT_PERSONBILAR,
                        "measure": measure,
                        "years": years,
                        "breakdown": breakdown,
                    },
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_fordon_personbilar  # type: ignore[return-value]

    # ── Lastbilar ──
    if definition.tool_id == "trafikanalys_fordon_lastbilar":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_fordon_lastbilar(
            measure: str = "itrfslut",
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta lastbilsstatistik.

            measure: itrfslut (i trafik), nyregunder, avregunder, avstslut.
            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                query = service.build_query(
                    PRODUCT_LASTBILAR, measure, f"{DIMENSION_AR}:{years}"
                )
                data, cached = await service.get_data(query)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={
                        "product": PRODUCT_LASTBILAR,
                        "measure": measure,
                        "years": years,
                    },
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_fordon_lastbilar  # type: ignore[return-value]

    # ── Bussar ──
    if definition.tool_id == "trafikanalys_fordon_bussar":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_fordon_bussar(
            measure: str = "itrfslut",
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta bussstatistik.

            measure: itrfslut (i trafik), nyregunder, avregunder, avstslut.
            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                query = service.build_query(
                    PRODUCT_BUSSAR, measure, f"{DIMENSION_AR}:{years}"
                )
                data, cached = await service.get_data(query)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={
                        "product": PRODUCT_BUSSAR,
                        "measure": measure,
                        "years": years,
                    },
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_fordon_bussar  # type: ignore[return-value]

    # ── Motorcyklar ──
    if definition.tool_id == "trafikanalys_fordon_motorcyklar":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_fordon_motorcyklar(
            measure: str = "itrfslut",
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta motorcykelstatistik.

            measure: itrfslut (i trafik), nyregunder, avregunder, avstslut.
            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                query = service.build_query(
                    PRODUCT_MOTORCYKLAR, measure, f"{DIMENSION_AR}:{years}"
                )
                data, cached = await service.get_data(query)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={
                        "product": PRODUCT_MOTORCYKLAR,
                        "measure": measure,
                        "years": years,
                    },
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_fordon_motorcyklar  # type: ignore[return-value]

    # ── Fordonsöversikt ──
    if definition.tool_id == "trafikanalys_fordon_oversikt":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_fordon_oversikt(
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta översiktsstatistik för alla fordonsslag.

            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                query = service.build_query(
                    PRODUCT_FORDON_PA_VAG, f"{DIMENSION_AR}:{years}"
                )
                data, cached = await service.get_data(query)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"product": PRODUCT_FORDON_PA_VAG, "years": years},
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_fordon_oversikt  # type: ignore[return-value]

    # ── Körkort ──
    if definition.tool_id == "trafikanalys_korkort":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_korkort(
            years: str = "senaste",
            breakdown: str = "",
        ) -> dict[str, Any]:
            """Hämta körkortsstatistik.

            years: År eller "senaste".
            breakdown: Valfri dimension (t.ex. "kon" för kön, "alder" för åldersgrupp).
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                data, cached = await service.get_driving_licenses(
                    years=years, breakdown=breakdown
                )
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={
                        "product": PRODUCT_KORKORT,
                        "years": years,
                        "breakdown": breakdown,
                    },
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_korkort  # type: ignore[return-value]

    # ── Trafikarbete ──
    if definition.tool_id == "trafikanalys_trafikarbete":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_trafikarbete(
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta trafikarbete (fordonskilometer) i Sverige.

            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                data, cached = await service.get_traffic_volume(years=years)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"product": PRODUCT_TRAFIKARBETE, "years": years},
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_trafikarbete  # type: ignore[return-value]

    # ── Vägtrafikskador ──
    if definition.tool_id == "trafikanalys_vagtrafik_skador":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_vagtrafik_skador(
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta trafikolycks- och skadestatistik.

            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                data, cached = await service.get_traffic_injuries(years=years)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"product": PRODUCT_VAGTRAFIK_SKADOR, "years": years},
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_vagtrafik_skador  # type: ignore[return-value]

    # ── Sjötrafik ──
    if definition.tool_id == "trafikanalys_sjotrafik":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_sjotrafik(
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta sjötrafikstatistik.

            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                data, cached = await service.get_maritime_traffic(years=years)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"product": PRODUCT_SJOTRAFIK, "years": years},
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_sjotrafik  # type: ignore[return-value]

    # ── Luftfart ──
    if definition.tool_id == "trafikanalys_luftfart":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_luftfart(
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta luftfartsstatistik.

            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                data, cached = await service.get_aviation_statistics(years=years)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"product": PRODUCT_LUFTFART, "years": years},
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_luftfart  # type: ignore[return-value]

    # ── Järnväg ──
    if definition.tool_id == "trafikanalys_jarnvag":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_jarnvag(
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta järnvägsstatistik (person- och godstransporter).

            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                data, cached = await service.get_railway_transport(years=years)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"product": PRODUCT_JARNVAG_TRANSPORT, "years": years},
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_jarnvag  # type: ignore[return-value]

    # ── Kollektivtrafik ──
    if definition.tool_id == "trafikanalys_kollektivtrafik":

        @tool(definition.tool_id, description=definition.description)
        async def trafikanalys_kollektivtrafik(
            years: str = "senaste",
        ) -> dict[str, Any]:
            """Hämta kollektivtrafikstatistik.

            years: År eller "senaste".
            """
            breaker = get_breaker("trafikanalys")
            if not breaker.can_execute():
                return {
                    "status": "error",
                    "error": "Trafikanalys service temporarily unavailable",
                }
            try:
                data, cached = await service.get_public_transport(years=years)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"product": PRODUCT_REGIONAL_LINJETRAFIK, "years": years},
                    data=_simplify_response(data),
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return trafikanalys_kollektivtrafik  # type: ignore[return-value]

    raise ValueError(f"Unknown Trafikanalys tool_id: {definition.tool_id}")
