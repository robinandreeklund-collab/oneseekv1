"""Riksbank API tools — interest rates, exchange rates, SWESTR, forecasts.

Follows the same pattern as bolagsverket.py / smhi.py:
- ToolDefinition dataclass
- List of RIKSBANK_TOOL_DEFINITIONS
- Factory function create_riksbank_tool()

Source: Sveriges Riksbank
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.agents.new_chat.circuit_breaker import get_breaker
from app.services.riksbank_service import (
    GROUP_EXCHANGE_RATES_SEK,
    GROUP_KEY_RATES,
    GROUP_STIBOR,
    RIKSBANK_SOURCE,
    SERIES_POLICY_RATE,
    RiksbankService,
)


@dataclass(frozen=True)
class RiksbankToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str
    base_path: str


RIKSBANK_TOOL_DEFINITIONS: list[RiksbankToolDefinition] = [
    RiksbankToolDefinition(
        tool_id="riksbank_ranta_styrranta",
        name="Riksbanken Styrränta",
        description=(
            "Hämtar aktuell styrränta (reporänta) och historik från Riksbanken. "
            "Inkluderar även in- och utlåningsränta samt referensränta."
        ),
        keywords=[
            "styrränta", "reporänta", "ränta", "riksbanken", "penningpolitik",
            "inlåningsränta", "utlåningsränta", "referensränta",
        ],
        example_queries=[
            "Vad är styrräntan just nu?",
            "Hur har reporäntan förändrats senaste året?",
            "Riksbankens räntehistorik sedan 2020",
        ],
        category="riksbank_rantor",
        base_path="/swea/v1/Observations",
    ),
    RiksbankToolDefinition(
        tool_id="riksbank_ranta_marknadsrantor",
        name="Riksbanken Marknadsräntor",
        description=(
            "Hämtar marknadsräntor från Riksbanken: statsobligationsräntor, "
            "STIBOR (alla löptider), statsskuldväxlar och bostadsräntor."
        ),
        keywords=[
            "stibor", "statsobligation", "obligation", "marknadsränta",
            "statsskuldväxel", "bostadsränta", "ränta", "obligationsränta",
        ],
        example_queries=[
            "Aktuell STIBOR-ränta",
            "Statsobligationsräntor 10 år",
            "Marknadsräntor Sverige",
        ],
        category="riksbank_rantor",
        base_path="/swea/v1/Observations/Latest/ByGroup",
    ),
    RiksbankToolDefinition(
        tool_id="riksbank_valuta_kurser",
        name="Riksbanken Valutakurser",
        description=(
            "Hämtar valutakurser (SEK mot andra valutor) från Riksbanken. "
            "Alla större valutor: EUR, USD, GBP, NOK, DKK, CHF, JPY m.fl."
        ),
        keywords=[
            "valutakurs", "växelkurs", "sek", "euro", "dollar", "pund",
            "nok", "dkk", "valuta", "forex",
        ],
        example_queries=[
            "Vad kostar en euro i svenska kronor?",
            "Dollarkursen idag",
            "SEK mot EUR senaste veckan",
        ],
        category="riksbank_valuta",
        base_path="/swea/v1/Observations/Latest/ByGroup/130",
    ),
    RiksbankToolDefinition(
        tool_id="riksbank_valuta_korsrantor",
        name="Riksbanken Korsräntor",
        description=(
            "Beräknar korsvalutakurser mellan valfria valutor via Riksbankens "
            "CrossRates-endpoint. Exempelvis EUR/USD, GBP/NOK."
        ),
        keywords=[
            "korskurs", "cross rate", "eur/usd", "valutaväxling",
            "valutapar", "korsvaluta",
        ],
        example_queries=[
            "Vad är EUR/USD-kursen idag?",
            "Korskurs mellan GBP och NOK",
        ],
        category="riksbank_valuta",
        base_path="/swea/v1/CrossRates",
    ),
    RiksbankToolDefinition(
        tool_id="riksbank_swestr",
        name="Riksbanken SWESTR",
        description=(
            "Hämtar SWESTR — Sveriges referensränta för dagslån. "
            "Inkluderar ränta, volym, antal transaktioner och agenter, "
            "percentiler (12.5/87.5)."
        ),
        keywords=[
            "swestr", "dagslåneränta", "referensränta", "overnight",
            "transaktionsränta", "interbankränta",
        ],
        example_queries=[
            "Aktuell SWESTR-ränta",
            "SWESTR historik senaste månaden",
        ],
        category="riksbank_swestr",
        base_path="/swestr/v1",
    ),
    RiksbankToolDefinition(
        tool_id="riksbank_prognos_inflation",
        name="Riksbanken Inflationsprognos",
        description=(
            "Riksbankens prognoser för KPI och KPIF (inflation). "
            "Inkluderar prognoser och utfall från 2020."
        ),
        keywords=[
            "inflationsprognos", "kpi", "kpif", "inflation", "prisstabilitet",
            "riksbanken prognos",
        ],
        example_queries=[
            "Riksbankens inflationsprognos",
            "KPI-prognos från Riksbanken",
        ],
        category="riksbank_prognos",
        base_path="/forecasts/v1/forecasts",
    ),
    RiksbankToolDefinition(
        tool_id="riksbank_prognos_bnp",
        name="Riksbanken BNP-prognos",
        description=(
            "Riksbankens BNP-prognoser och utfall. "
            "Inkluderar prognoser för ekonomisk tillväxt."
        ),
        keywords=[
            "bnp-prognos", "bnp", "tillväxtprognos", "ekonomisk tillväxt",
            "riksbanken prognos",
        ],
        example_queries=[
            "Riksbankens BNP-prognos",
            "Ekonomisk tillväxtprognos Sverige",
        ],
        category="riksbank_prognos",
        base_path="/forecasts/v1/forecasts",
    ),
    RiksbankToolDefinition(
        tool_id="riksbank_prognos_ovrigt",
        name="Riksbanken Makroprognoser",
        description=(
            "Övriga makroekonomiska prognoser från Riksbanken: "
            "arbetslöshet, reporänteprognos, växelkursprognos m.m."
        ),
        keywords=[
            "makroprognos", "arbetslöshetsprognos", "ränteprognos",
            "riksbanken prognos", "makroekonomi",
        ],
        example_queries=[
            "Riksbankens arbetslöshetsprognos",
            "Ränteprognos från Riksbanken",
            "Makroprognoser Sverige",
        ],
        category="riksbank_prognos",
        base_path="/forecasts/v1/forecasts",
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
        "source": RIKSBANK_SOURCE,
        "base_path": base_path,
        "query": query,
        "cached": cached,
        "data": data,
    }


def _format_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message if message else type(exc).__name__


def create_riksbank_tool(definition: RiksbankToolDefinition) -> BaseTool:
    """Factory that creates a LangChain tool for the given Riksbank definition."""

    service = RiksbankService()

    if definition.tool_id == "riksbank_ranta_styrranta":

        @tool(definition.tool_id, description=definition.description)
        async def riksbank_ranta_styrranta(
            from_date: str = "",
            to_date: str = "",
        ) -> dict[str, Any]:
            """Hämta styrräntan. Utan datum: aktuell ränta. Med datum: historik."""
            breaker = get_breaker("riksbank")
            if not breaker.can_execute():
                return {"status": "error", "error": "Riksbank service temporarily unavailable"}
            try:
                if from_date and to_date:
                    data, cached = await service.get_observations(
                        SERIES_POLICY_RATE, from_date, to_date
                    )
                else:
                    data, cached = await service.get_policy_rate()
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"series": SERIES_POLICY_RATE, "from": from_date, "to": to_date},
                    data=data,
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return riksbank_ranta_styrranta  # type: ignore[return-value]

    if definition.tool_id == "riksbank_ranta_marknadsrantor":

        @tool(definition.tool_id, description=definition.description)
        async def riksbank_ranta_marknadsrantor(
            group_id: str = "",
        ) -> dict[str, Any]:
            """Hämta marknadsräntor per grupp. Grupper: 2 (styrräntor), 3 (STIBOR), etc."""
            breaker = get_breaker("riksbank")
            if not breaker.can_execute():
                return {"status": "error", "error": "Riksbank service temporarily unavailable"}
            try:
                gid = group_id.strip() if group_id else GROUP_STIBOR
                data, cached = await service.get_latest_by_group(gid)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"group_id": gid},
                    data=data,
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return riksbank_ranta_marknadsrantor  # type: ignore[return-value]

    if definition.tool_id == "riksbank_valuta_kurser":

        @tool(definition.tool_id, description=definition.description)
        async def riksbank_valuta_kurser(
            series_id: str = "",
            from_date: str = "",
            to_date: str = "",
        ) -> dict[str, Any]:
            """Hämta valutakurser. Utan series_id: alla SEK-kurser. Med datum: historik."""
            breaker = get_breaker("riksbank")
            if not breaker.can_execute():
                return {"status": "error", "error": "Riksbank service temporarily unavailable"}
            try:
                if series_id and from_date and to_date:
                    data, cached = await service.get_observations(series_id, from_date, to_date)
                elif series_id:
                    data, cached = await service.get_latest_observation(series_id)
                else:
                    data, cached = await service.get_latest_by_group(GROUP_EXCHANGE_RATES_SEK)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"series_id": series_id, "from": from_date, "to": to_date},
                    data=data,
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return riksbank_valuta_kurser  # type: ignore[return-value]

    if definition.tool_id == "riksbank_valuta_korsrantor":

        @tool(definition.tool_id, description=definition.description)
        async def riksbank_valuta_korsrantor(
            series1: str = "SEKEURPMI",
            series2: str = "SEKUSDPMI",
            date: str = "",
        ) -> dict[str, Any]:
            """Beräkna korskurs mellan två valutor. Standard: EUR/USD."""
            breaker = get_breaker("riksbank")
            if not breaker.can_execute():
                return {"status": "error", "error": "Riksbank service temporarily unavailable"}
            try:
                if not date:
                    date = datetime.now().strftime("%Y-%m-%d")
                data, cached = await service.get_cross_rates(series1, series2, date)
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"series1": series1, "series2": series2, "date": date},
                    data=data,
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return riksbank_valuta_korsrantor  # type: ignore[return-value]

    if definition.tool_id == "riksbank_swestr":

        @tool(definition.tool_id, description=definition.description)
        async def riksbank_swestr(
            from_date: str = "",
            to_date: str = "",
        ) -> dict[str, Any]:
            """Hämta SWESTR-räntan. Utan datum: senaste. Med datum: historik."""
            breaker = get_breaker("riksbank")
            if not breaker.can_execute():
                return {"status": "error", "error": "Riksbank service temporarily unavailable"}
            try:
                if from_date:
                    data, cached = await service.get_swestr_observations(from_date, to_date or None)
                else:
                    data, cached = await service.get_swestr_latest()
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"from": from_date, "to": to_date},
                    data=data,
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return riksbank_swestr  # type: ignore[return-value]

    if definition.tool_id == "riksbank_prognos_inflation":

        @tool(definition.tool_id, description=definition.description)
        async def riksbank_prognos_inflation() -> dict[str, Any]:
            """Hämta Riksbankens inflationsprognoser (KPI, KPIF)."""
            breaker = get_breaker("riksbank")
            if not breaker.can_execute():
                return {"status": "error", "error": "Riksbank service temporarily unavailable"}
            try:
                data, cached = await service.get_forecasts(indicator="KPIF")
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"indicator": "KPIF"},
                    data=data,
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return riksbank_prognos_inflation  # type: ignore[return-value]

    if definition.tool_id == "riksbank_prognos_bnp":

        @tool(definition.tool_id, description=definition.description)
        async def riksbank_prognos_bnp() -> dict[str, Any]:
            """Hämta Riksbankens BNP-prognoser."""
            breaker = get_breaker("riksbank")
            if not breaker.can_execute():
                return {"status": "error", "error": "Riksbank service temporarily unavailable"}
            try:
                data, cached = await service.get_forecasts(indicator="GDP")
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"indicator": "GDP"},
                    data=data,
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return riksbank_prognos_bnp  # type: ignore[return-value]

    if definition.tool_id == "riksbank_prognos_ovrigt":

        @tool(definition.tool_id, description=definition.description)
        async def riksbank_prognos_ovrigt(indicator: str = "") -> dict[str, Any]:
            """Hämta makroprognoser. Valfri indicator (tom = alla)."""
            breaker = get_breaker("riksbank")
            if not breaker.can_execute():
                return {"status": "error", "error": "Riksbank service temporarily unavailable"}
            try:
                data, cached = await service.get_forecasts(
                    indicator=indicator if indicator else None
                )
                breaker.record_success()
                return _build_payload(
                    tool_name=definition.tool_id,
                    base_path=definition.base_path,
                    query={"indicator": indicator},
                    data=data,
                    cached=cached,
                )
            except Exception as exc:
                breaker.record_failure()
                return {"status": "error", "error": _format_error(exc)}

        return riksbank_prognos_ovrigt  # type: ignore[return-value]

    raise ValueError(f"Unknown Riksbank tool_id: {definition.tool_id}")
