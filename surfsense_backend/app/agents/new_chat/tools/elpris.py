"""Elpris API tools — Swedish electricity spot prices.

Follows the same pattern as riksbank.py / bolagsverket.py:
- ToolDefinition dataclass
- List of ELPRIS_TOOL_DEFINITIONS
- Factory function create_elpris_tool()

Source: elprisetjustnu.se
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.agents.new_chat.circuit_breaker import get_breaker
from app.services.elpris_service import (
    ELPRIS_SOURCE,
    VALID_ZONES,
    ZONE_NAMES,
    ElprisService,
)


@dataclass(frozen=True)
class ElprisToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str
    base_path: str


ELPRIS_TOOL_DEFINITIONS: list[ElprisToolDefinition] = [
    ElprisToolDefinition(
        tool_id="elpris_idag",
        name="Elpris Idag",
        description=(
            "Dagens elpriser (spotpriser) per elområde i Sverige. "
            "Priser per 15-minutersintervall i SEK/kWh och EUR/kWh. "
            "Zoner: SE1 (Luleå), SE2 (Sundsvall), SE3 (Stockholm), SE4 (Malmö)."
        ),
        keywords=[
            "elpris", "elpriser", "spotpris", "idag", "kwh",
            "el", "elräkning", "timpris", "aktuellt",
        ],
        example_queries=[
            "Vad kostar elen idag?",
            "Elpris Stockholm just nu",
            "Spotpris SE3 idag",
        ],
        category="elpris",
        base_path="/api/v1/prices",
    ),
    ElprisToolDefinition(
        tool_id="elpris_imorgon",
        name="Elpris Imorgon",
        description=(
            "Morgondagens elpriser per elområde. "
            "Tillgängliga efter ca 13:00 varje dag."
        ),
        keywords=[
            "elpris", "imorgon", "morgondagens", "spotpris",
            "el", "kommande", "nästa dag",
        ],
        example_queries=[
            "Elpris imorgon",
            "Vad kostar elen imorgon i Malmö?",
        ],
        category="elpris",
        base_path="/api/v1/prices",
    ),
    ElprisToolDefinition(
        tool_id="elpris_historik",
        name="Elpris Historik",
        description=(
            "Historiska elpriser för ett specifikt datum eller period (max 31 dagar). "
            "Data tillgänglig från 2022-11-01."
        ),
        keywords=[
            "elpris", "historik", "historiska", "förra veckan",
            "elstatistik", "prishistorik", "eldata",
        ],
        example_queries=[
            "Elpris förra veckan SE3",
            "Elpriser 2024-01-15 alla zoner",
            "Historiska spotpriser december 2024",
        ],
        category="elpris",
        base_path="/api/v1/prices",
    ),
    ElprisToolDefinition(
        tool_id="elpris_jamforelse",
        name="Elpris Zonjämförelse",
        description=(
            "Jämför elpriser mellan alla fyra svenska elzoner "
            "(SE1, SE2, SE3, SE4) för ett datum. "
            "Visar min/max/medelpris per zon."
        ),
        keywords=[
            "elpris", "jämförelse", "jämför", "elzon", "elområde",
            "se1", "se2", "se3", "se4", "zonpris",
        ],
        example_queries=[
            "Jämför elpriset mellan alla zoner idag",
            "Vilken elzon har lägst pris?",
            "Prisskillnad mellan SE1 och SE4",
        ],
        category="elpris",
        base_path="/api/v1/prices",
    ),
]


def _build_payload(
    *,
    tool_name: str,
    base_path: str,
    query: dict[str, Any],
    data: Any,
    cached: bool = False,
) -> dict[str, Any]:
    return {
        "status": "success",
        "tool": tool_name,
        "source": ELPRIS_SOURCE,
        "base_path": base_path,
        "query": query,
        "data": data,
        "cached": cached,
    }


def _format_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message if message else type(exc).__name__


def create_elpris_tool(definition: ElprisToolDefinition) -> BaseTool:
    """Factory that creates a LangChain tool for the given Elpris definition."""

    service = ElprisService()

    if definition.tool_id == "elpris_idag":

        @tool(definition.tool_id, description=definition.description)
        async def elpris_idag(zone: str = "SE3") -> dict[str, Any]:
            """Hämta dagens elpriser. Standard: SE3 (Stockholm)."""
            breaker = get_breaker("elpris")
            if not breaker.can_execute():
                return {"status": "error", "error": "Elpris service temporarily unavailable"}
            try:
                prices = await service.get_today_prices(zone)
                stats = service._aggregate(prices)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"zone": zone.upper(), "date": "idag"},
                    data={
                        "zone": zone.upper(),
                        "zone_name": ZONE_NAMES.get(zone.upper(), zone),
                        "prices": prices,
                        "summary": stats,
                    },
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return elpris_idag  # type: ignore[return-value]

    if definition.tool_id == "elpris_imorgon":

        @tool(definition.tool_id, description=definition.description)
        async def elpris_imorgon(zone: str = "SE3") -> dict[str, Any]:
            """Hämta morgondagens elpriser. Tillgängliga efter ca 13:00."""
            breaker = get_breaker("elpris")
            if not breaker.can_execute():
                return {"status": "error", "error": "Elpris service temporarily unavailable"}
            try:
                prices = await service.get_tomorrow_prices(zone)
                if not prices:
                    return {
                        "status": "info",
                        "message": "Morgondagens priser är inte tillgängliga ännu (publiceras efter 13:00).",
                        "query": {"zone": zone.upper()},
                    }
                stats = service._aggregate(prices)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"zone": zone.upper(), "date": "imorgon"},
                    data={
                        "zone": zone.upper(),
                        "zone_name": ZONE_NAMES.get(zone.upper(), zone),
                        "prices": prices,
                        "summary": stats,
                    },
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return elpris_imorgon  # type: ignore[return-value]

    if definition.tool_id == "elpris_historik":

        @tool(definition.tool_id, description=definition.description)
        async def elpris_historik(
            date: str = "",
            from_date: str = "",
            to_date: str = "",
            zone: str = "SE3",
        ) -> dict[str, Any]:
            """Historiska elpriser. Ange date för en dag, eller from_date+to_date för period."""
            breaker = get_breaker("elpris")
            if not breaker.can_execute():
                return {"status": "error", "error": "Elpris service temporarily unavailable"}
            try:
                if date:
                    prices = await service.get_prices(date, zone)
                    stats = service._aggregate(prices)
                    breaker.record_success()
                    return _build_payload(
                        tool_name=definition.tool_id,
                        base_path=definition.base_path,
                        query={"date": date, "zone": zone.upper()},
                        data={
                            "zone": zone.upper(),
                            "zone_name": ZONE_NAMES.get(zone.upper(), zone),
                            "prices": prices,
                            "summary": stats,
                        },
                    )
                elif from_date and to_date:
                    prices = await service.get_prices_range(from_date, to_date, zone)
                    stats = service._aggregate(prices)
                    breaker.record_success()
                    return _build_payload(
                        tool_name=definition.tool_id,
                        base_path=definition.base_path,
                        query={"from": from_date, "to": to_date, "zone": zone.upper()},
                        data={
                            "zone": zone.upper(),
                            "zone_name": ZONE_NAMES.get(zone.upper(), zone),
                            "prices": prices,
                            "summary": stats,
                        },
                    )
                else:
                    return {
                        "status": "error",
                        "error": "Ange antingen date eller from_date + to_date",
                    }
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return elpris_historik  # type: ignore[return-value]

    if definition.tool_id == "elpris_jamforelse":

        @tool(definition.tool_id, description=definition.description)
        async def elpris_jamforelse(date: str = "") -> dict[str, Any]:
            """Jämför elpriser mellan alla zoner. Utan datum: idag."""
            breaker = get_breaker("elpris")
            if not breaker.can_execute():
                return {"status": "error", "error": "Elpris service temporarily unavailable"}
            try:
                if not date:
                    date = datetime.now().strftime("%Y-%m-%d")
                data = await service.get_price_comparison(date)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"date": date},
                    data=data,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return elpris_jamforelse  # type: ignore[return-value]

    raise ValueError(f"Unknown Elpris tool_id: {definition.tool_id}")
