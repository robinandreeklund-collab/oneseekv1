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
    # ── Trafiklab route tool (assigned to tåg-agent) ──
    {
        "tool_id": "trafiklab_route",
        "agent_id": "trafik-tag",
        "label": "Resplanering",
        "description": "Planerar resa med kollektivtrafik via Trafiklab.",
        "keywords": ["resplanering", "trafiklab", "kollektivtrafik", "buss", "tåg"],
        "category": "trafik",
        "namespace": ["tools", "trafik", "tag"],
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

    # Simple agents: one import path → one agent_id
    simple_agent_tool_mapping = {
        "bolag": "app.agents.new_chat.tools.bolagsverket:BOLAGSVERKET_TOOL_DEFINITIONS",
        "marknad": "app.agents.new_chat.marketplace_tools:MARKETPLACE_TOOL_DEFINITIONS",
        "riksbank-ekonomi": "app.agents.new_chat.tools.riksbank:RIKSBANK_TOOL_DEFINITIONS",
        "elpris": "app.agents.new_chat.tools.elpris:ELPRIS_TOOL_DEFINITIONS",
        "trafikanalys-transport": "app.agents.new_chat.tools.trafikanalys:TRAFIKANALYS_TOOL_DEFINITIONS",
    }

    for agent_id, import_path in simple_agent_tool_mapping.items():
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

    # ── Riksdagen: split across 3 sub-agents by category ──
    riksdagen_agent_by_category = {
        "riksdagen_dokument": "riksdagen-dokument",
        "riksdagen_status": "riksdagen-dokument",
        "riksdagen_anforanden": "riksdagen-debatt",
        "riksdagen_voteringar": "riksdagen-debatt",
        "riksdagen_ledamoter": "riksdagen-ledamoter",
        "riksdagen_kalender": "riksdagen-ledamoter",
    }
    riksdagen_ns_by_agent = {
        "riksdagen-dokument": ["tools", "politik", "dokument"],
        "riksdagen-debatt": ["tools", "politik", "debatt"],
        "riksdagen-ledamoter": ["tools", "politik", "ledamoter"],
    }
    try:
        from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS

        for definition in RIKSDAGEN_TOOL_DEFINITIONS:
            tool_id = str(getattr(definition, "tool_id", ""))
            if not tool_id:
                continue
            category = str(getattr(definition, "category", ""))
            sub_agent = riksdagen_agent_by_category.get(category, "riksdagen-dokument")
            additional.append(
                {
                    "tool_id": tool_id,
                    "agent_id": sub_agent,
                    "label": str(getattr(definition, "name", tool_id)),
                    "description": str(getattr(definition, "description", "")),
                    "keywords": list(getattr(definition, "keywords", [])),
                    "category": category,
                    "namespace": list(
                        riksdagen_ns_by_agent.get(
                            sub_agent, ["tools", "politik", "dokument"]
                        )
                    ),
                    "enabled": True,
                    "priority": 100,
                }
            )
    except Exception:
        pass

    # ── SMHI: split across 3 sub-agents by category ──
    smhi_agent_by_category = {
        "smhi_vaderprognoser": "väder",
        "smhi_vaderanalyser": "väder",
        "smhi_vaderobservationer": "väder",
        "smhi_hydrologi": "väder-vatten",
        "smhi_oceanografi": "väder-vatten",
        "smhi_brandrisk": "väder-risk",
        "smhi_solstralning": "väder-risk",
    }
    smhi_ns_by_agent = {
        "väder": ["tools", "weather", "smhi"],
        "väder-vatten": ["tools", "weather", "hydro"],
        "väder-risk": ["tools", "weather", "risk"],
    }
    try:
        from app.agents.new_chat.tools.smhi import SMHI_TOOL_DEFINITIONS

        for definition in SMHI_TOOL_DEFINITIONS:
            tool_id = str(getattr(definition, "tool_id", ""))
            if not tool_id:
                continue
            category = str(getattr(definition, "category", ""))
            sub_agent = smhi_agent_by_category.get(category, "väder")
            additional.append(
                {
                    "tool_id": tool_id,
                    "agent_id": sub_agent,
                    "label": str(getattr(definition, "name", tool_id)),
                    "description": str(getattr(definition, "description", "")),
                    "keywords": list(getattr(definition, "keywords", [])),
                    "category": category,
                    "namespace": list(
                        smhi_ns_by_agent.get(sub_agent, ["tools", "weather", "smhi"])
                    ),
                    "enabled": True,
                    "priority": 100,
                }
            )
    except Exception:
        pass

    # ── Trafikverket: split across 3 sub-agents by category ──
    trafik_agent_by_category = {
        "trafikverket_tag": "trafik-tag",
        "trafikverket_trafikinfo": "trafik-vag",
        "trafikverket_vag": "trafik-vag",
        "trafikverket_kameror": "trafik-vag",
        "trafikverket_prognos": "trafik-vag",
        "trafikverket_vader": "trafik-vagvader",
    }
    trafik_ns_by_agent = {
        "trafik-tag": ["tools", "trafik", "tag"],
        "trafik-vag": ["tools", "trafik", "vag"],
        "trafik-vagvader": ["tools", "trafik", "vagvader"],
    }
    # Special case: tågprognos goes to trafik-tag, not trafik-vag
    trafik_tool_override = {
        "trafikverket_prognos_tag": "trafik-tag",
    }
    try:
        from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS

        for definition in TRAFIKVERKET_TOOL_DEFINITIONS:
            tool_id = str(getattr(definition, "tool_id", ""))
            if not tool_id:
                continue
            category = str(getattr(definition, "category", ""))
            sub_agent = trafik_tool_override.get(
                tool_id, trafik_agent_by_category.get(category, "trafik-vag")
            )
            additional.append(
                {
                    "tool_id": tool_id,
                    "agent_id": sub_agent,
                    "label": str(getattr(definition, "name", tool_id)),
                    "description": str(getattr(definition, "description", "")),
                    "keywords": list(getattr(definition, "keywords", [])),
                    "category": category,
                    "namespace": list(
                        trafik_ns_by_agent.get(sub_agent, ["tools", "trafik", "vag"])
                    ),
                    "enabled": True,
                    "priority": 100,
                }
            )
    except Exception:
        pass

    # ── SCB: split across statistik-* sub-agents by tool_id prefix ──
    scb_agent_by_prefix = {
        "scb_befolkning": "statistik-befolkning",
        "scb_arbetsmarknad": "statistik-arbetsmarknad",
        "scb_utbildning": "statistik-utbildning",
        "scb_halsa": "statistik-halsa",
        "scb_socialtjanst": "statistik-halsa",
        "scb_levnadsforhallanden": "statistik-halsa",
        "scb_miljo": "statistik-miljo",
        "scb_energi": "statistik-miljo",
        "scb_boende": "statistik-fastighet",
        "scb_naringsverksamhet": "statistik-naringsliv",
        "scb_naringsliv": "statistik-naringsliv",
        "scb_nationalrakenskaper": "statistik-ekonomi",
        "scb_priser": "statistik-ekonomi",
        "scb_finansmarknad": "statistik-ekonomi",
        "scb_offentlig": "statistik-ekonomi",
        "scb_hushall": "statistik-ekonomi",
        "scb_handel": "statistik-ekonomi",
        "scb_transporter": "statistik-samhalle",
        "scb_demokrati": "riksdagen-dokument",
        "scb_kultur": "statistik-samhalle",
        "scb_jordbruk": "statistik-samhalle",
        "scb_amnesovergripande": "statistik-samhalle",
    }
    scb_ns_by_agent = {
        "statistik-ekonomi": ["tools", "statistics", "scb", "ekonomi"],
        "statistik-befolkning": ["tools", "statistics", "scb", "befolkning"],
        "statistik-arbetsmarknad": ["tools", "statistics", "scb", "arbetsmarknad"],
        "statistik-utbildning": ["tools", "statistics", "scb", "utbildning"],
        "statistik-halsa": ["tools", "statistics", "scb", "halsa"],
        "statistik-miljo": ["tools", "statistics", "scb", "miljo"],
        "statistik-fastighet": ["tools", "statistics", "scb", "fastighet"],
        "statistik-naringsliv": ["tools", "statistics", "scb", "naringsliv"],
        "statistik-samhalle": ["tools", "statistics", "scb", "samhalle"],
        "riksdagen-dokument": ["tools", "politik", "dokument"],
    }
    try:
        from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS

        for definition in SCB_TOOL_DEFINITIONS:
            tool_id = str(getattr(definition, "tool_id", ""))
            if not tool_id:
                continue
            sub_agent = "statistik-samhalle"  # default fallback
            for prefix, agent in scb_agent_by_prefix.items():
                if tool_id.startswith(prefix):
                    sub_agent = agent
                    break
            additional.append(
                {
                    "tool_id": tool_id,
                    "agent_id": sub_agent,
                    "label": str(getattr(definition, "name", tool_id)),
                    "description": str(getattr(definition, "description", "")),
                    "keywords": list(getattr(definition, "keywords", [])),
                    "category": str(getattr(definition, "base_path", "statistik")),
                    "namespace": list(
                        scb_ns_by_agent.get(
                            sub_agent, ["tools", "statistics", "scb", "samhalle"]
                        )
                    ),
                    "enabled": True,
                    "priority": 100,
                }
            )
    except Exception:
        pass

    # ── Kolada: split across statistik-* sub-agents by tool_id prefix ──
    kolada_agent_by_prefix = {
        "kolada_aldreomsorg": "statistik-halsa",
        "kolada_lss": "statistik-halsa",
        "kolada_ifo": "statistik-halsa",
        "kolada_barn_unga": "statistik-halsa",
        "kolada_halsa": "statistik-halsa",
        "kolada_forskola": "statistik-utbildning",
        "kolada_grundskola": "statistik-utbildning",
        "kolada_gymnasieskola": "statistik-utbildning",
        "kolada_ekonomi": "statistik-ekonomi",
        "kolada_miljo": "statistik-miljo",
        "kolada_boende": "statistik-fastighet",
        "kolada_arbetsmarknad": "statistik-arbetsmarknad",
        "kolada_demokrati": "riksdagen-ledamoter",
        "kolada_kultur": "statistik-samhalle",
        "kolada_sammanfattning": "statistik-samhalle",
    }
    kolada_ns_by_agent = {
        "statistik-ekonomi": ["tools", "statistics", "kolada", "ekonomi"],
        "statistik-arbetsmarknad": ["tools", "statistics", "kolada", "arbetsmarknad"],
        "statistik-utbildning": ["tools", "statistics", "kolada", "utbildning"],
        "statistik-halsa": ["tools", "statistics", "kolada", "halsa"],
        "statistik-miljo": ["tools", "statistics", "kolada", "miljo"],
        "statistik-fastighet": ["tools", "statistics", "kolada", "fastighet"],
        "statistik-samhalle": ["tools", "statistics", "kolada", "samhalle"],
        "riksdagen-ledamoter": ["tools", "politik", "ledamoter"],
    }
    try:
        from app.agents.new_chat.kolada_tools import KOLADA_TOOL_DEFINITIONS

        for definition in KOLADA_TOOL_DEFINITIONS:
            tool_id = str(getattr(definition, "tool_id", ""))
            if not tool_id:
                continue
            sub_agent = "statistik-samhalle"  # default fallback
            for prefix, agent in kolada_agent_by_prefix.items():
                if tool_id.startswith(prefix):
                    sub_agent = agent
                    break
            additional.append(
                {
                    "tool_id": tool_id,
                    "agent_id": sub_agent,
                    "label": str(getattr(definition, "name", tool_id)),
                    "description": str(getattr(definition, "description", "")),
                    "keywords": list(getattr(definition, "keywords", [])),
                    "category": str(getattr(definition, "category", "kolada")),
                    "namespace": list(
                        kolada_ns_by_agent.get(
                            sub_agent, ["tools", "statistics", "kolada", "samhalle"]
                        )
                    ),
                    "enabled": True,
                    "priority": 100,
                }
            )
    except Exception:
        pass

    # ── Skolverket: split across skolverket-* sub-agents by tool_id ──
    skolverket_agent_by_tool: dict[str, str] = {
        # Kursplaner: ämnen, kurser, program, läroplaner
        "search_subjects": "skolverket-kursplaner",
        "get_subject_details": "skolverket-kursplaner",
        "get_subject_versions": "skolverket-kursplaner",
        "search_courses": "skolverket-kursplaner",
        "get_course_details": "skolverket-kursplaner",
        "get_course_versions": "skolverket-kursplaner",
        "search_programs": "skolverket-kursplaner",
        "get_program_details": "skolverket-kursplaner",
        "get_program_versions": "skolverket-kursplaner",
        "get_programs_v4": "skolverket-kursplaner",
        "search_curriculums": "skolverket-kursplaner",
        "get_curriculum_details": "skolverket-kursplaner",
        "get_curriculum_versions": "skolverket-kursplaner",
        # Skolenheter
        "search_school_units": "skolverket-skolenheter",
        "search_school_units_v4": "skolverket-skolenheter",
        "get_school_unit_details": "skolverket-skolenheter",
        "search_school_units_by_name": "skolverket-skolenheter",
        "get_school_units_by_status": "skolverket-skolenheter",
        "get_school_unit_education_events": "skolverket-skolenheter",
        "get_school_unit_documents": "skolverket-skolenheter",
        "get_school_unit_statistics": "skolverket-skolenheter",
        # Vuxenutbildning & utbildningstillfällen
        "search_adult_education": "skolverket-vuxenutbildning",
        "get_adult_education_details": "skolverket-vuxenutbildning",
        "filter_adult_education_by_distance": "skolverket-vuxenutbildning",
        "filter_adult_education_by_pace": "skolverket-vuxenutbildning",
        "count_adult_education_events": "skolverket-vuxenutbildning",
        "get_adult_education_areas_v4": "skolverket-vuxenutbildning",
        "search_education_events": "skolverket-vuxenutbildning",
        "count_education_events": "skolverket-vuxenutbildning",
        "get_geographical_areas_v4": "skolverket-vuxenutbildning",
        "get_education_areas": "skolverket-vuxenutbildning",
        "get_directions": "skolverket-vuxenutbildning",
        # Referensdata, statistik & system
        "get_school_types": "skolverket-referens",
        "get_school_types_v4": "skolverket-referens",
        "get_types_of_syllabus": "skolverket-referens",
        "get_subject_and_course_codes": "skolverket-referens",
        "get_study_path_codes": "skolverket-referens",
        "get_national_statistics": "skolverket-referens",
        "get_program_statistics": "skolverket-referens",
        "get_api_info": "skolverket-referens",
        "health_check": "skolverket-referens",
    }
    skolverket_ns_by_agent = {
        "skolverket-kursplaner": ["tools", "skolverket", "kursplaner"],
        "skolverket-skolenheter": ["tools", "skolverket", "skolenheter"],
        "skolverket-vuxenutbildning": ["tools", "skolverket", "vuxenutbildning"],
        "skolverket-referens": ["tools", "skolverket", "referens"],
    }
    try:
        from app.agents.new_chat.skolverket_tools import SKOLVERKET_TOOL_DEFINITIONS

        for definition in SKOLVERKET_TOOL_DEFINITIONS:
            tool_id = str(getattr(definition, "tool_id", ""))
            if not tool_id:
                continue
            sub_agent = skolverket_agent_by_tool.get(
                tool_id, "skolverket-referens"
            )
            additional.append(
                {
                    "tool_id": tool_id,
                    "agent_id": sub_agent,
                    "label": str(getattr(definition, "name", tool_id)),
                    "description": str(getattr(definition, "description", "")),
                    "keywords": list(getattr(definition, "keywords", [])),
                    "category": str(getattr(definition, "category", "skolverket")),
                    "namespace": list(
                        skolverket_ns_by_agent.get(
                            sub_agent, ["tools", "skolverket", "referens"]
                        )
                    ),
                    "enabled": True,
                    "priority": 100,
                }
            )
    except Exception:
        pass

    return additional
