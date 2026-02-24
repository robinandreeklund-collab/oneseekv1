"""
Domain fan-out: parallel tool execution within bounded agent namespaces.

Instead of letting a bigtool worker call tools sequentially (1 per LLM turn,
max 3 turns), this module pre-executes relevant tools in parallel using
asyncio.gather() — the same pattern as compare_fan_out — and feeds the
collected results back as a single rich context block.

This is most valuable for namespace-bounded agents (väder, trafik, statistik)
where a single user question benefits from data across multiple API categories.

Example: "Hur är vädret i Göteborg?" →
  parallel: smhi_vaderprognoser_metfcst + smhi_vaderobservationer_metobs + smhi_vaderanalyser_mesan2g
  → worker receives pre-fetched data and synthesizes a richer answer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration: which tool categories to fan out per domain
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FanOutCategory:
    """A group of tools within a domain that serve a distinct data purpose."""

    name: str
    tool_ids: tuple[str, ...]
    priority: int = 0  # Lower = higher priority when selecting subset


@dataclass(frozen=True)
class DomainFanOutConfig:
    """Fan-out configuration for a single namespace-bounded agent."""

    enabled: bool = True
    max_parallel: int = 4
    timeout_seconds: float = 30.0
    categories: tuple[FanOutCategory, ...] = ()
    # When True, only fan out categories whose keywords match the query.
    # When False, always fan out all categories up to max_parallel.
    selective: bool = True


# --- SMHI / Weather ---

SMHI_CATEGORIES = (
    FanOutCategory(
        name="prognos",
        tool_ids=("smhi_vaderprognoser_metfcst",),
        priority=0,
    ),
    FanOutCategory(
        name="observation",
        tool_ids=("smhi_vaderobservationer_metobs",),
        priority=1,
    ),
    FanOutCategory(
        name="analys",
        tool_ids=("smhi_vaderanalyser_mesan2g",),
        priority=2,
    ),
    FanOutCategory(
        name="sno",
        tool_ids=("smhi_vaderprognoser_snow1g",),
        priority=3,
    ),
    FanOutCategory(
        name="hydrologi",
        tool_ids=("smhi_hydrologi_hydroobs",),
        priority=5,
    ),
    FanOutCategory(
        name="oceanografi",
        tool_ids=("smhi_oceanografi_ocobs",),
        priority=6,
    ),
    FanOutCategory(
        name="brandrisk",
        tool_ids=("smhi_brandrisk_fwif",),
        priority=7,
    ),
    FanOutCategory(
        name="solstralning",
        tool_ids=("smhi_solstralning_strang",),
        priority=8,
    ),
)

# Keyword sets that trigger each SMHI category beyond the default prognos.
_SMHI_CATEGORY_TRIGGERS: dict[str, set[str]] = {
    "prognos": set(),  # Always included as baseline
    "observation": {"observation", "mätning", "matning", "station", "senaste", "aktuell", "nu"},
    "analys": {"analys", "mesan", "grid", "moln", "molntäcke"},
    "sno": {"snö", "sno", "snödjup", "is", "frost", "vinterväder"},
    "hydrologi": {"vattenstånd", "vattenstand", "vattenföring", "hydrologi", "flod", "sjö", "mälaren", "vänern"},
    "oceanografi": {"hav", "havsnivå", "havsvatten", "våg", "våghöjd", "kust", "östersjön", "salthalt"},
    "brandrisk": {"brandrisk", "brand", "eld", "fwi", "skog", "torka"},
    "solstralning": {"sol", "solstrålning", "uv", "strålning", "solenergi", "par"},
}

# --- Trafikverket / Traffic ---

TRAFIKVERKET_CATEGORIES = (
    FanOutCategory(
        name="storningar",
        tool_ids=("trafikverket_trafikinfo_storningar",),
        priority=0,
    ),
    FanOutCategory(
        name="olyckor",
        tool_ids=("trafikverket_trafikinfo_olyckor",),
        priority=1,
    ),
    FanOutCategory(
        name="koer",
        tool_ids=("trafikverket_trafikinfo_koer",),
        priority=2,
    ),
    FanOutCategory(
        name="vagarbeten",
        tool_ids=("trafikverket_trafikinfo_vagarbeten",),
        priority=3,
    ),
    FanOutCategory(
        name="tag_forseningar",
        tool_ids=("trafikverket_tag_forseningar",),
        priority=4,
    ),
    FanOutCategory(
        name="tag_tidtabell",
        tool_ids=("trafikverket_tag_tidtabell",),
        priority=5,
    ),
    FanOutCategory(
        name="vag_status",
        tool_ids=("trafikverket_vag_status",),
        priority=6,
    ),
    FanOutCategory(
        name="vader_halka",
        tool_ids=("trafikverket_vader_halka",),
        priority=7,
    ),
    FanOutCategory(
        name="prognos_trafik",
        tool_ids=("trafikverket_prognos_trafik",),
        priority=8,
    ),
)

_TRAFIKVERKET_CATEGORY_TRIGGERS: dict[str, set[str]] = {
    "storningar": set(),  # Always included as baseline
    "olyckor": {"olycka", "olyckor", "krock", "incident", "singelolycka"},
    "koer": {"kö", "köer", "koer", "trängsel", "stockning", "trafikstockning"},
    "vagarbeten": {"vägarbete", "vagarbete", "vägarbeten", "omledning", "avstängning"},
    "tag_forseningar": {"tåg", "tag", "försening", "forsening", "försenad", "järnväg", "pendeltåg"},
    "tag_tidtabell": {"tidtabell", "avgång", "ankomst", "perrong", "tågtid"},
    "vag_status": {"vägstatus", "vagstatus", "trafikflöde", "framkomlighet"},
    "vader_halka": {"halka", "isrisk", "väglag", "vaglag", "snö", "is"},
    "prognos_trafik": {"prognos", "restid", "belastning"},
}

# --- SCB / Statistics ---
# SCB has 20+ broad categories — we fan out the most commonly co-queried ones.

SCB_CATEGORIES = (
    FanOutCategory(
        name="befolkning",
        tool_ids=("scb_befolkning",),
        priority=0,
    ),
    FanOutCategory(
        name="arbetsmarknad",
        tool_ids=("scb_arbetsmarknad",),
        priority=1,
    ),
    FanOutCategory(
        name="priser",
        tool_ids=("scb_priser_konsumtion",),
        priority=2,
    ),
    FanOutCategory(
        name="utbildning",
        tool_ids=("scb_utbildning",),
        priority=3,
    ),
    FanOutCategory(
        name="naringsliv",
        tool_ids=("scb_naringsverksamhet",),
        priority=4,
    ),
    FanOutCategory(
        name="miljo",
        tool_ids=("scb_miljo",),
        priority=5,
    ),
)

_SCB_CATEGORY_TRIGGERS: dict[str, set[str]] = {
    "befolkning": {"befolkning", "invånare", "folkmängd", "invandring", "utvandring", "födda", "döda"},
    "arbetsmarknad": {"arbetsmarknad", "arbetslöshet", "sysselsättning", "lön", "löner", "jobb"},
    "priser": {"pris", "priser", "inflation", "kpi", "konsument"},
    "utbildning": {"utbildning", "skola", "gymnasium", "högskola", "universitet"},
    "naringsliv": {"företag", "foretag", "näringsliv", "omsättning", "nyföretagande"},
    "miljo": {"miljö", "miljo", "utsläpp", "utslapp", "energi", "klimat"},
}


# ---------------------------------------------------------------------------
# Master configuration registry
# ---------------------------------------------------------------------------

DOMAIN_FAN_OUT_CONFIGS: dict[str, DomainFanOutConfig] = {
    "väder": DomainFanOutConfig(
        enabled=True,
        max_parallel=4,
        timeout_seconds=25.0,
        categories=SMHI_CATEGORIES,
        selective=True,
    ),
    "weather": DomainFanOutConfig(
        enabled=True,
        max_parallel=4,
        timeout_seconds=25.0,
        categories=SMHI_CATEGORIES,
        selective=True,
    ),
    "trafik": DomainFanOutConfig(
        enabled=True,
        max_parallel=4,
        timeout_seconds=25.0,
        categories=TRAFIKVERKET_CATEGORIES,
        selective=True,
    ),
    "statistik": DomainFanOutConfig(
        enabled=True,
        max_parallel=3,
        timeout_seconds=30.0,
        categories=SCB_CATEGORIES,
        selective=True,
    ),
    "statistics": DomainFanOutConfig(
        enabled=True,
        max_parallel=3,
        timeout_seconds=30.0,
        categories=SCB_CATEGORIES,
        selective=True,
    ),
}

_CATEGORY_TRIGGERS: dict[str, dict[str, set[str]]] = {
    "väder": _SMHI_CATEGORY_TRIGGERS,
    "weather": _SMHI_CATEGORY_TRIGGERS,
    "trafik": _TRAFIKVERKET_CATEGORY_TRIGGERS,
    "statistik": _SCB_CATEGORY_TRIGGERS,
    "statistics": _SCB_CATEGORY_TRIGGERS,
}


# ---------------------------------------------------------------------------
# Category selection logic
# ---------------------------------------------------------------------------

def select_categories(
    agent_name: str,
    query: str,
    *,
    config: DomainFanOutConfig | None = None,
) -> list[FanOutCategory]:
    """Select which categories to fan out based on query keywords.

    Always includes the baseline category (priority=0, no triggers).
    Adds additional categories when query contains matching trigger words.
    Caps at config.max_parallel.
    """
    if config is None:
        config = DOMAIN_FAN_OUT_CONFIGS.get(agent_name)
    if config is None or not config.enabled:
        return []

    triggers = _CATEGORY_TRIGGERS.get(agent_name, {})
    query_lower = query.lower()
    query_words = set(query_lower.split())

    selected: list[FanOutCategory] = []
    for cat in config.categories:
        cat_triggers = triggers.get(cat.name, set())
        if not cat_triggers:
            # No triggers = baseline category, always include
            selected.append(cat)
        elif config.selective:
            # Check if any trigger word appears in query
            if cat_triggers & query_words:
                selected.append(cat)
            elif any(trigger in query_lower for trigger in cat_triggers):
                selected.append(cat)
        else:
            # Non-selective: include all
            selected.append(cat)

    # Sort by priority and cap
    selected.sort(key=lambda c: c.priority)
    return selected[: config.max_parallel]


# ---------------------------------------------------------------------------
# Parallel execution engine
# ---------------------------------------------------------------------------

@dataclass
class FanOutResult:
    """Result from a single tool execution within the fan-out."""

    tool_id: str
    category: str
    status: str  # "success", "error", "timeout"
    content: str = ""
    error: str = ""
    elapsed_ms: float = 0.0


async def execute_domain_fan_out(
    *,
    agent_name: str,
    query: str,
    tool_registry: dict[str, BaseTool],
    tool_args: dict[str, Any] | None = None,
    config: DomainFanOutConfig | None = None,
) -> list[FanOutResult]:
    """Execute tools for selected categories in parallel.

    This is the core engine that mirrors compare_fan_out's asyncio.gather pattern
    but operates on domain-specific tools within a single agent's namespace.

    Args:
        agent_name: The bounded agent name (e.g., "väder", "trafik").
        query: The user's query to pass to each tool.
        tool_registry: Full tool registry (tool_name -> BaseTool).
        tool_args: Optional extra arguments to pass to each tool.
        config: Override config (defaults to DOMAIN_FAN_OUT_CONFIGS lookup).

    Returns:
        List of FanOutResult for each executed tool.
    """
    if config is None:
        config = DOMAIN_FAN_OUT_CONFIGS.get(agent_name)
    if config is None or not config.enabled:
        return []

    categories = select_categories(agent_name, query, config=config)
    if not categories:
        return []

    # Collect all tool_ids to call across selected categories
    tool_calls: list[tuple[str, str]] = []  # (tool_id, category_name)
    for cat in categories:
        for tool_id in cat.tool_ids:
            if tool_id in tool_registry:
                tool_calls.append((tool_id, cat.name))

    if not tool_calls:
        return []

    base_args = dict(tool_args or {})
    if "query" not in base_args:
        base_args["query"] = query

    async def _call_one(tool_id: str, category: str) -> FanOutResult:
        """Execute a single tool and return its result."""
        t0 = time.monotonic()
        tool = tool_registry.get(tool_id)
        if tool is None:
            return FanOutResult(
                tool_id=tool_id,
                category=category,
                status="error",
                error=f"Tool '{tool_id}' not found in registry",
                elapsed_ms=0.0,
            )
        try:
            result = await asyncio.wait_for(
                tool.ainvoke(base_args),
                timeout=config.timeout_seconds,
            )
            elapsed = (time.monotonic() - t0) * 1000
            content = str(result) if result is not None else ""
            return FanOutResult(
                tool_id=tool_id,
                category=category,
                status="success",
                content=content,
                elapsed_ms=elapsed,
            )
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - t0) * 1000
            return FanOutResult(
                tool_id=tool_id,
                category=category,
                status="timeout",
                error=f"Timed out after {config.timeout_seconds}s",
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return FanOutResult(
                tool_id=tool_id,
                category=category,
                status="error",
                error=str(exc),
                elapsed_ms=elapsed,
            )

    # The core parallel execution — same pattern as compare_fan_out
    results = await asyncio.gather(
        *[_call_one(tool_id, cat) for tool_id, cat in tool_calls],
        return_exceptions=False,
    )

    success_count = sum(1 for r in results if r.status == "success")
    logger.info(
        "domain-fan-out agent=%s categories=%d tools=%d success=%d elapsed_max=%.0fms",
        agent_name,
        len(categories),
        len(tool_calls),
        success_count,
        max((r.elapsed_ms for r in results), default=0),
    )

    return list(results)


# ---------------------------------------------------------------------------
# Context formatting: convert fan-out results into a prompt block
# ---------------------------------------------------------------------------

def format_fan_out_context(
    results: list[FanOutResult],
    *,
    max_chars_per_tool: int = 6000,
    max_total_chars: int = 20000,
) -> str:
    """Format fan-out results into a structured context block for the worker LLM.

    Successful results are included as data blocks. Errors are noted briefly.
    The output is designed to be prepended to the worker's system prompt so
    the LLM has pre-fetched data available for synthesis.
    """
    if not results:
        return ""

    blocks: list[str] = []
    total_chars = 0

    for r in results:
        if r.status == "success" and r.content:
            truncated = r.content[:max_chars_per_tool]
            block = (
                f"<domain_data tool=\"{r.tool_id}\" category=\"{r.category}\" "
                f"elapsed_ms=\"{r.elapsed_ms:.0f}\">\n"
                f"{truncated}\n"
                f"</domain_data>"
            )
            if total_chars + len(block) > max_total_chars:
                break
            blocks.append(block)
            total_chars += len(block)
        elif r.status in ("error", "timeout"):
            note = f"<!-- {r.tool_id}: {r.status} — {r.error[:120]} -->"
            blocks.append(note)

    if not blocks:
        return ""

    header = (
        "<domain_fan_out_results>\n"
        "Följande data hämtades parallellt från flera API:er. "
        "Använd denna information för att ge ett komplett svar.\n\n"
    )
    footer = "\n</domain_fan_out_results>"

    return header + "\n\n".join(blocks) + footer


# ---------------------------------------------------------------------------
# Public API: check if fan-out is available for an agent
# ---------------------------------------------------------------------------

def is_fan_out_enabled(agent_name: str) -> bool:
    """Check if domain fan-out is configured and enabled for an agent."""
    config = DOMAIN_FAN_OUT_CONFIGS.get(str(agent_name or "").strip().lower())
    return config is not None and config.enabled


def get_fan_out_tool_ids(agent_name: str) -> list[str]:
    """Return all tool IDs that could be used in fan-out for an agent."""
    config = DOMAIN_FAN_OUT_CONFIGS.get(str(agent_name or "").strip().lower())
    if config is None or not config.enabled:
        return []
    ids: list[str] = []
    for cat in config.categories:
        ids.extend(cat.tool_ids)
    return ids
