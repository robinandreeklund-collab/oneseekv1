"""Admin endpoint that returns the complete intent -> agent -> tool flow graph."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import (
    SearchSpaceMembership,
    User,
    get_async_session,
)
from app.services.intent_definition_service import get_effective_intent_definitions
from app.services.agent_metadata_service import get_effective_agent_metadata
from app.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Intent → Route → Agent policy mapping ──────────────────────────────
_ROUTE_AGENT_POLICIES: dict[str, list[str]] = {
    "kunskap": [
        "knowledge", "browser", "weather", "trafik", "statistics",
        "bolag", "riksdagen", "marketplace",
    ],
    "skapande": ["media", "kartor", "code"],
    "jämförelse": ["synthesis", "statistics", "knowledge"],
    "konversation": [],
}

# ── Agent → Tool mapping (hardcoded tool IDs per agent namespace) ──────
_AGENT_TOOL_MAP: dict[str, list[dict[str, str]]] = {
    "knowledge": [
        {"tool_id": "search_surfsense_docs", "label": "SurfSense Docs"},
        {"tool_id": "save_memory", "label": "Save Memory"},
        {"tool_id": "recall_memory", "label": "Recall Memory"},
        {"tool_id": "tavily_search", "label": "Tavily Search"},
    ],
    "browser": [
        {"tool_id": "scrape_webpage", "label": "Scrape Webpage"},
        {"tool_id": "link_preview", "label": "Link Preview"},
        {"tool_id": "public_web_search", "label": "Web Search"},
    ],
    "weather": [
        {"tool_id": "smhi_weather", "label": "SMHI Prognos"},
        {"tool_id": "smhi_vaderprognoser_metfcst", "label": "SMHI MetFcst"},
        {"tool_id": "smhi_vaderprognoser_snow1g", "label": "SMHI Snö"},
        {"tool_id": "smhi_vaderanalyser_mesan2g", "label": "SMHI MESAN"},
        {"tool_id": "smhi_vaderobservationer_metobs", "label": "SMHI MetObs"},
        {"tool_id": "smhi_hydrologi_hydroobs", "label": "SMHI HydroObs"},
        {"tool_id": "smhi_hydrologi_pthbv", "label": "SMHI PTHBV"},
        {"tool_id": "smhi_oceanografi_ocobs", "label": "SMHI Oceanografi"},
        {"tool_id": "smhi_brandrisk_fwif", "label": "SMHI Brandrisk FWIF"},
        {"tool_id": "smhi_brandrisk_fwia", "label": "SMHI Brandrisk FWIA"},
    ],
    "trafik": [
        {"tool_id": "trafikverket_situation", "label": "Trafikläge"},
        {"tool_id": "trafikverket_road_condition", "label": "Väglag"},
        {"tool_id": "trafikverket_camera", "label": "Kameror"},
        {"tool_id": "trafikverket_ferry", "label": "Färjor"},
        {"tool_id": "trafikverket_railway", "label": "Järnväg"},
        {"tool_id": "trafiklab_route", "label": "Resplanerare"},
    ],
    "kartor": [
        {"tool_id": "geoapify_static_map", "label": "Statisk Karta"},
    ],
    "marketplace": [
        {"tool_id": "marketplace_unified_search", "label": "Unified Search"},
        {"tool_id": "marketplace_blocket_search", "label": "Blocket Sök"},
        {"tool_id": "marketplace_blocket_cars", "label": "Blocket Bilar"},
        {"tool_id": "marketplace_blocket_boats", "label": "Blocket Båtar"},
        {"tool_id": "marketplace_blocket_mc", "label": "Blocket MC"},
        {"tool_id": "marketplace_tradera_search", "label": "Tradera Sök"},
        {"tool_id": "marketplace_compare_prices", "label": "Prisjämförelse"},
    ],
    "statistics": [
        {"tool_id": "scb_befolkning", "label": "SCB Befolkning"},
        {"tool_id": "scb_arbetsmarknad", "label": "SCB Arbetsmarknad"},
        {"tool_id": "scb_boende_byggande", "label": "SCB Boende"},
        {"tool_id": "scb_priser_konsumtion", "label": "SCB Priser"},
        {"tool_id": "scb_utbildning", "label": "SCB Utbildning"},
        {"tool_id": "kolada_municipality", "label": "Kolada Kommun"},
    ],
    "media": [
        {"tool_id": "generate_podcast", "label": "Podcast"},
        {"tool_id": "display_image", "label": "Visa Bild"},
    ],
    "code": [
        {"tool_id": "sandbox_execute", "label": "Sandbox Execute"},
        {"tool_id": "sandbox_write_file", "label": "Sandbox Write"},
        {"tool_id": "sandbox_read_file", "label": "Sandbox Read"},
        {"tool_id": "sandbox_ls", "label": "Sandbox LS"},
        {"tool_id": "sandbox_replace", "label": "Sandbox Replace"},
        {"tool_id": "sandbox_release", "label": "Sandbox Release"},
    ],
    "bolag": [
        {"tool_id": "bolagsverket_info_basic", "label": "Företagsinfo"},
        {"tool_id": "bolagsverket_info_status", "label": "Företagsstatus"},
        {"tool_id": "bolagsverket_sok_namn", "label": "Sök Namn"},
        {"tool_id": "bolagsverket_sok_orgnr", "label": "Sök Orgnr"},
        {"tool_id": "bolagsverket_ekonomi_bokslut", "label": "Bokslut"},
    ],
    "riksdagen": [
        {"tool_id": "riksdagen_dokument_sok", "label": "Dokument Sök"},
        {"tool_id": "riksdagen_votering", "label": "Voteringar"},
        {"tool_id": "riksdagen_ledamot", "label": "Ledamöter"},
    ],
    "action": [
        {"tool_id": "search_knowledge_base", "label": "Knowledge Base"},
        {"tool_id": "link_preview", "label": "Link Preview"},
        {"tool_id": "scrape_webpage", "label": "Scrape Webpage"},
    ],
    "synthesis": [
        {"tool_id": "external_model_compare", "label": "Model Compare"},
    ],
}


async def _require_admin(
    session: AsyncSession,
    user: User,
) -> None:
    result = await session.execute(
        select(SearchSpaceMembership)
        .filter(
            SearchSpaceMembership.user_id == user.id,
            SearchSpaceMembership.is_owner.is_(True),
        )
        .limit(1)
    )
    if result.scalars().first() is None:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access flow graph",
        )


@router.get("/flow-graph")
async def get_flow_graph(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """Return the complete intent -> agent -> tool graph for admin visualization."""
    await _require_admin(session, user)

    intents = await get_effective_intent_definitions(session)
    agents = await get_effective_agent_metadata(session)
    agent_map = {a["agent_id"]: a for a in agents}

    intent_nodes: list[dict[str, Any]] = []
    agent_nodes: list[dict[str, Any]] = []
    tool_nodes: list[dict[str, Any]] = []
    intent_agent_edges: list[dict[str, str]] = []
    agent_tool_edges: list[dict[str, str]] = []
    seen_agents: set[str] = set()
    seen_tools: set[str] = set()

    for intent in intents:
        intent_id = intent.get("intent_id", "")
        route = intent.get("route", "")
        intent_nodes.append({
            "id": f"intent:{intent_id}",
            "type": "intent",
            "intent_id": intent_id,
            "label": intent.get("label", intent_id),
            "description": intent.get("description", ""),
            "route": route,
            "keywords": intent.get("keywords", []),
            "priority": intent.get("priority", 500),
            "enabled": intent.get("enabled", True),
        })

        # Build edges to agents based on route policy
        agent_ids = _ROUTE_AGENT_POLICIES.get(route, [])
        for agent_id in agent_ids:
            intent_agent_edges.append({
                "source": f"intent:{intent_id}",
                "target": f"agent:{agent_id}",
            })
            if agent_id not in seen_agents:
                seen_agents.add(agent_id)
                meta = agent_map.get(agent_id, {})
                agent_nodes.append({
                    "id": f"agent:{agent_id}",
                    "type": "agent",
                    "agent_id": agent_id,
                    "label": meta.get("label", agent_id),
                    "description": meta.get("description", ""),
                    "keywords": meta.get("keywords", []),
                    "prompt_key": meta.get("prompt_key", ""),
                    "namespace": meta.get("namespace", []),
                })

    # Add any remaining agents not yet covered by routes
    for agent in agents:
        agent_id = agent["agent_id"]
        if agent_id not in seen_agents:
            seen_agents.add(agent_id)
            agent_nodes.append({
                "id": f"agent:{agent_id}",
                "type": "agent",
                "agent_id": agent_id,
                "label": agent.get("label", agent_id),
                "description": agent.get("description", ""),
                "keywords": agent.get("keywords", []),
                "prompt_key": agent.get("prompt_key", ""),
                "namespace": agent.get("namespace", []),
            })

    # Build tool nodes and agent → tool edges
    for agent_id in seen_agents:
        tools = _AGENT_TOOL_MAP.get(agent_id, [])
        for tool in tools:
            tool_id = tool["tool_id"]
            if tool_id not in seen_tools:
                seen_tools.add(tool_id)
                tool_nodes.append({
                    "id": f"tool:{tool_id}",
                    "type": "tool",
                    "tool_id": tool_id,
                    "label": tool.get("label", tool_id),
                    "agent_id": agent_id,
                })
            agent_tool_edges.append({
                "source": f"agent:{agent_id}",
                "target": f"tool:{tool_id}",
            })

    return {
        "intents": intent_nodes,
        "agents": agent_nodes,
        "tools": tool_nodes,
        "intent_agent_edges": intent_agent_edges,
        "agent_tool_edges": agent_tool_edges,
    }
