"""Default tool definition seed data.

Maps tools from the current ROUTE_TOOL_SETS and _AGENT_TOOL_PROFILES
to the new hierarchy. Tool definitions for specialized agents (SMHI,
Trafikverket, SCB, etc.) are loaded dynamically from their respective
TOOL_DEFINITIONS constants at seed time.
"""

from __future__ import annotations

from typing import Any

# ── Static tool definitions (non-specialized agents) ──────────────────

DEFAULT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    # ── Kunskap agent tools ──
    {
        "tool_id": "search_knowledge_base",
        "agent_id": "kunskap",
        "label": "Sök kunskapsbas",
        "description": "Söker i intern kunskapsbas och dokument.",
        "keywords": ["dokument", "kunskap", "sök", "intern"],
        "category": "knowledge",
        "namespace": ["tools", "knowledge", "kb"],
        "enabled": True,
        "priority": 100,
    },
    {
        "tool_id": "save_memory",
        "agent_id": "kunskap",
        "label": "Spara minne",
        "description": "Sparar information till minnet för framtida användning.",
        "keywords": ["minne", "spara", "kom ihåg"],
        "category": "memory",
        "namespace": ["tools", "knowledge", "memory"],
        "enabled": True,
        "priority": 200,
    },
    {
        "tool_id": "recall_memory",
        "agent_id": "kunskap",
        "label": "Hämta minne",
        "description": "Hämtar tidigare sparad information från minnet.",
        "keywords": ["minne", "hämta", "kom ihåg"],
        "category": "memory",
        "namespace": ["tools", "knowledge", "memory"],
        "enabled": True,
        "priority": 200,
    },
    # ── Webb agent tools ──
    {
        "tool_id": "public_web_search",
        "agent_id": "webb",
        "label": "Webbsökning",
        "description": "Söker på webben efter information.",
        "keywords": ["webb", "sök", "google", "internet"],
        "category": "web",
        "namespace": ["tools", "web", "search"],
        "enabled": True,
        "priority": 100,
    },
    {
        "tool_id": "tavily_search",
        "agent_id": "webb",
        "label": "Tavily Sökning",
        "description": "Avancerad webbsökning via Tavily API.",
        "keywords": ["tavily", "sök", "webb"],
        "category": "web",
        "namespace": ["tools", "web", "search"],
        "enabled": True,
        "priority": 150,
    },
    {
        "tool_id": "scrape_webpage",
        "agent_id": "webb",
        "label": "Skrapa webbsida",
        "description": "Hämtar och extraherar innehåll från en webbsida.",
        "keywords": ["scrape", "webbsida", "hämta", "url"],
        "category": "web",
        "namespace": ["tools", "web", "scrape"],
        "enabled": True,
        "priority": 150,
    },
    {
        "tool_id": "link_preview",
        "agent_id": "webb",
        "label": "Länkförhandsvisning",
        "description": "Visar förhandsvisning av en länk.",
        "keywords": ["länk", "preview", "förhandsvisning"],
        "category": "web",
        "namespace": ["tools", "web", "preview"],
        "enabled": True,
        "priority": 200,
    },
    {
        "tool_id": "libris_search",
        "agent_id": "webb",
        "label": "Libris Sökning",
        "description": "Söker i Libris (svenska bibliotekskatalogen).",
        "keywords": ["libris", "bibliotek", "bok", "sökning"],
        "category": "web",
        "namespace": ["tools", "web", "libris"],
        "enabled": True,
        "priority": 200,
    },
    {
        "tool_id": "jobad_links_search",
        "agent_id": "webb",
        "label": "Jobbannons-sökning",
        "description": "Söker efter jobbannonser.",
        "keywords": ["jobb", "annons", "lediga", "tjänster"],
        "category": "web",
        "namespace": ["tools", "web", "jobs"],
        "enabled": True,
        "priority": 200,
    },
    # ── Kod agent tools ──
    {
        "tool_id": "sandbox_execute",
        "agent_id": "kod",
        "label": "Kör kod",
        "description": "Exekverar Python-kod i sandboxmiljö.",
        "keywords": ["kör", "exekvera", "python", "sandbox"],
        "category": "code",
        "namespace": ["tools", "code", "sandbox"],
        "enabled": True,
        "priority": 100,
    },
    {
        "tool_id": "sandbox_write_file",
        "agent_id": "kod",
        "label": "Skriv fil",
        "description": "Skriver en fil i sandboxmiljön.",
        "keywords": ["skriv", "fil", "sandbox"],
        "category": "code",
        "namespace": ["tools", "code", "sandbox"],
        "enabled": True,
        "priority": 150,
    },
    {
        "tool_id": "sandbox_read_file",
        "agent_id": "kod",
        "label": "Läs fil",
        "description": "Läser en fil i sandboxmiljön.",
        "keywords": ["läs", "fil", "sandbox"],
        "category": "code",
        "namespace": ["tools", "code", "sandbox"],
        "enabled": True,
        "priority": 150,
    },
    {
        "tool_id": "sandbox_ls",
        "agent_id": "kod",
        "label": "Lista filer",
        "description": "Listar filer i sandboxmiljön.",
        "keywords": ["lista", "filer", "sandbox"],
        "category": "code",
        "namespace": ["tools", "code", "sandbox"],
        "enabled": True,
        "priority": 200,
    },
    {
        "tool_id": "sandbox_replace",
        "agent_id": "kod",
        "label": "Ersätt i fil",
        "description": "Ersätter text i en fil i sandboxmiljön.",
        "keywords": ["ersätt", "replace", "fil", "sandbox"],
        "category": "code",
        "namespace": ["tools", "code", "sandbox"],
        "enabled": True,
        "priority": 200,
    },
    {
        "tool_id": "sandbox_release",
        "agent_id": "kod",
        "label": "Frigör sandbox",
        "description": "Frigör sandboxresurser.",
        "keywords": ["frigör", "release", "sandbox"],
        "category": "code",
        "namespace": ["tools", "code", "sandbox"],
        "enabled": True,
        "priority": 300,
    },
    # ── Karta agent tools ──
    {
        "tool_id": "geoapify_static_map",
        "agent_id": "kartor",
        "label": "Statisk karta",
        "description": "Genererar en statisk kartbild med Geoapify.",
        "keywords": ["karta", "map", "geoapify", "bild"],
        "category": "map",
        "namespace": ["tools", "map", "geoapify"],
        "enabled": True,
        "priority": 100,
    },
    # ── Media agent tools ──
    {
        "tool_id": "generate_podcast",
        "agent_id": "media",
        "label": "Generera podcast",
        "description": "Genererar ett podcastavsnitt från text.",
        "keywords": ["podcast", "ljud", "generera"],
        "category": "media",
        "namespace": ["tools", "media", "podcast"],
        "enabled": True,
        "priority": 100,
    },
    {
        "tool_id": "display_image",
        "agent_id": "media",
        "label": "Visa bild",
        "description": "Visar en genererad bild.",
        "keywords": ["bild", "display", "visa"],
        "category": "media",
        "namespace": ["tools", "media", "image"],
        "enabled": True,
        "priority": 150,
    },
    # ── Trafiklab route tool ──
    {
        "tool_id": "trafiklab_route",
        "agent_id": "trafik",
        "label": "Resplanering",
        "description": "Planerar resa med kollektivtrafik via Trafiklab.",
        "keywords": ["resplanering", "trafiklab", "kollektivtrafik", "buss", "tåg"],
        "category": "trafik",
        "namespace": ["tools", "trafik", "trafiklab"],
        "enabled": True,
        "priority": 100,
    },
]


def get_default_tool_definitions() -> dict[str, dict[str, Any]]:
    """Return default tools as a dict keyed by tool_id.

    Includes both static definitions and dynamically-imported specialized
    agent tools (SMHI, Trafikverket, SCB, etc.).
    """
    result = {tool["tool_id"]: tool for tool in DEFAULT_TOOL_DEFINITIONS}
    # Merge in specialized agent tools so they appear in the registry
    for tool in build_tool_definitions_from_profiles():
        tool_id = tool.get("tool_id", "")
        if tool_id and tool_id not in result:
            result[tool_id] = tool
    return result


def build_tool_definitions_from_profiles() -> list[dict[str, Any]]:
    """Build additional tool definitions from specialized agent tool profiles.

    This imports the TOOL_DEFINITIONS from specialized agents (SMHI,
    Trafikverket, SCB, etc.) and converts them to the standard format.
    Should be called at seed time.
    """
    additional: list[dict[str, Any]] = []

    agent_tool_mapping = {
        "väder": "app.agents.new_chat.tools.smhi:SMHI_TOOL_DEFINITIONS",
        "trafik": "app.agents.new_chat.tools.trafikverket:TRAFIKVERKET_TOOL_DEFINITIONS",
        "statistik": "app.agents.new_chat.statistics_agent:SCB_TOOL_DEFINITIONS",
        "riksdagen": "app.agents.new_chat.riksdagen_agent:RIKSDAGEN_TOOL_DEFINITIONS",
        "bolag": "app.agents.new_chat.tools.bolagsverket:BOLAGSVERKET_TOOL_DEFINITIONS",
        "marknad": "app.agents.new_chat.marketplace_tools:MARKETPLACE_TOOL_DEFINITIONS",
    }

    for agent_id, import_path in agent_tool_mapping.items():
        try:
            module_path, attr_name = import_path.rsplit(":", 1)
            import importlib

            module = importlib.import_module(module_path)
            definitions = getattr(module, attr_name, [])
        except Exception:
            continue

        for definition in definitions:
            tool_id = str(getattr(definition, "tool_id", ""))
            if not tool_id:
                continue
            additional.append(
                {
                    "tool_id": tool_id,
                    "agent_id": agent_id,
                    "label": str(getattr(definition, "name", tool_id)),
                    "description": str(getattr(definition, "description", "")),
                    "keywords": list(getattr(definition, "keywords", [])),
                    "category": str(getattr(definition, "category", agent_id)),
                    "namespace": [
                        "tools",
                        agent_id,
                        tool_id.split("_")[0] if "_" in tool_id else agent_id,
                    ],
                    "enabled": True,
                    "priority": 100,
                }
            )

    return additional
