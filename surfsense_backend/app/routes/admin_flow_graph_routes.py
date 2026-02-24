"""Admin endpoint that returns the LangGraph pipeline graph and routing data."""

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


# ─── LangGraph pipeline: nodes & edges ───────────────────────────────
# Mirrors the StateGraph built in supervisor_agent.py.

_PIPELINE_NODES: list[dict[str, Any]] = [
    # ── Entry ──
    {
        "id": "node:resolve_intent",
        "label": "Resolve Intent",
        "stage": "entry",
        "description": "Klassificerar frågan → route (kunskap/skapande/jämförelse/konversation) + confidence.",
    },
    {
        "id": "node:memory_context",
        "label": "Memory Context",
        "stage": "entry",
        "description": "Laddar minneskontext och samtalshistorik.",
    },
    # ── Fast paths ──
    {
        "id": "node:smalltalk",
        "label": "Smalltalk",
        "stage": "fast_path",
        "description": "Snabb hälsningssvar (konversation-route). → END",
    },
    # ── Speculative ──
    {
        "id": "node:speculative",
        "label": "Speculative",
        "stage": "speculative",
        "description": "Förberäknar troliga verktyg parallellt (hybrid-läge, komplex fråga).",
    },
    # ── Planning ──
    {
        "id": "node:agent_resolver",
        "label": "Agent Resolver",
        "stage": "planning",
        "description": "Hämtar och väljer agenter via vektor-retrieval + LLM-rankning.",
    },
    {
        "id": "node:planner",
        "label": "Planner",
        "stage": "planning",
        "description": "Skapar exekverbar plan (max 4 steg) baserat på valda agenter.",
    },
    {
        "id": "node:planner_hitl_gate",
        "label": "Planner HITL",
        "stage": "planning",
        "description": "Human-in-the-loop: pausar för användarens godkännande av planen.",
    },
    # ── Tool resolution ──
    {
        "id": "node:tool_resolver",
        "label": "Tool Resolver",
        "stage": "tool_resolution",
        "description": "Matchar plansteg → verktyg via vektor-retrieval.",
    },
    {
        "id": "node:speculative_merge",
        "label": "Speculative Merge",
        "stage": "tool_resolution",
        "description": "Mergar spekulativa verktygskandidater med resolver-resultat.",
    },
    {
        "id": "node:execution_router",
        "label": "Execution Router",
        "stage": "tool_resolution",
        "description": "Bestämmer exekverings-strategi (inline/subagent/parallel).",
    },
    # ── Execution ──
    {
        "id": "node:execution_hitl_gate",
        "label": "Execution HITL",
        "stage": "execution",
        "description": "Human-in-the-loop: pausar för godkännande innan verktygsanrop.",
    },
    {
        "id": "node:executor",
        "label": "Executor (LLM)",
        "stage": "execution",
        "description": "LLM-anrop som genererar svar eller tool_calls.",
    },
    {
        "id": "node:tools",
        "label": "Tools",
        "stage": "execution",
        "description": "Kör verktygsanrop (SMHI, SCB, Trafikverket, sandbox, etc.).",
    },
    {
        "id": "node:post_tools",
        "label": "Post-Tools",
        "stage": "execution",
        "description": "Efterbehandling av verktygsresultat.",
    },
    # ── Post-processing ──
    {
        "id": "node:artifact_indexer",
        "label": "Artifact Indexer",
        "stage": "post_processing",
        "description": "Indexerar artefakter (filer, data) för framtida referens.",
    },
    {
        "id": "node:context_compactor",
        "label": "Context Compactor",
        "stage": "post_processing",
        "description": "Komprimerar kontext för att hålla sig inom token-budget.",
    },
    {
        "id": "node:orchestration_guard",
        "label": "Orchestration Guard",
        "stage": "post_processing",
        "description": "Loop-guard och verktygs-limit-guard mot oändliga loopar.",
    },
    # ── Evaluation ──
    {
        "id": "node:critic",
        "label": "Critic",
        "stage": "evaluation",
        "description": "Bedömer om svaret är tillräckligt (ok/needs_more/replan).",
    },
    # ── Synthesis ──
    {
        "id": "node:synthesis_hitl",
        "label": "Synthesis HITL",
        "stage": "synthesis",
        "description": "Human-in-the-loop: pausar för godkännande innan leverans.",
    },
    {
        "id": "node:progressive_synthesizer",
        "label": "Progressive Synthesizer",
        "stage": "synthesis",
        "description": "Inkrementell streaming-syntes för komplexa svar.",
    },
    {
        "id": "node:synthesizer",
        "label": "Synthesizer",
        "stage": "synthesis",
        "description": "Slutgiltig förfining och formatering av svaret. → END",
    },
]

_PIPELINE_EDGES: list[dict[str, Any]] = [
    # ── Main flow ──
    {"source": "node:resolve_intent", "target": "node:memory_context", "type": "normal"},
    # ── Conditional from memory_context (route_after_intent) ──
    {"source": "node:memory_context", "target": "node:smalltalk", "type": "conditional", "label": "konversation"},
    {"source": "node:memory_context", "target": "node:speculative", "type": "conditional", "label": "komplex"},
    {"source": "node:memory_context", "target": "node:agent_resolver", "type": "conditional", "label": "default"},
    {"source": "node:memory_context", "target": "node:tool_resolver", "type": "conditional", "label": "enkel"},
    {"source": "node:memory_context", "target": "node:synthesis_hitl", "type": "conditional", "label": "finalize"},
    # ── Speculative → planning ──
    {"source": "node:speculative", "target": "node:agent_resolver", "type": "normal"},
    # ── Planning flow ──
    {"source": "node:agent_resolver", "target": "node:planner", "type": "normal"},
    {"source": "node:planner", "target": "node:planner_hitl_gate", "type": "normal"},
    {"source": "node:planner_hitl_gate", "target": "node:tool_resolver", "type": "conditional", "label": "godkänd"},
    # ── Tool resolution → execution ──
    {"source": "node:tool_resolver", "target": "node:speculative_merge", "type": "normal"},
    {"source": "node:speculative_merge", "target": "node:execution_router", "type": "normal"},
    {"source": "node:execution_router", "target": "node:execution_hitl_gate", "type": "normal"},
    {"source": "node:execution_hitl_gate", "target": "node:executor", "type": "conditional", "label": "godkänd"},
    # ── Executor loop ──
    {"source": "node:executor", "target": "node:tools", "type": "conditional", "label": "tool_calls"},
    {"source": "node:executor", "target": "node:critic", "type": "conditional", "label": "svar klart"},
    # ── Tool processing chain ──
    {"source": "node:tools", "target": "node:post_tools", "type": "normal"},
    {"source": "node:post_tools", "target": "node:artifact_indexer", "type": "normal"},
    {"source": "node:artifact_indexer", "target": "node:context_compactor", "type": "normal"},
    {"source": "node:context_compactor", "target": "node:orchestration_guard", "type": "normal"},
    {"source": "node:orchestration_guard", "target": "node:critic", "type": "normal"},
    # ── Critic decisions ──
    {"source": "node:critic", "target": "node:synthesis_hitl", "type": "conditional", "label": "ok"},
    {"source": "node:critic", "target": "node:tool_resolver", "type": "conditional", "label": "needs_more"},
    {"source": "node:critic", "target": "node:planner", "type": "conditional", "label": "replan"},
    # ── Synthesis ──
    {"source": "node:synthesis_hitl", "target": "node:progressive_synthesizer", "type": "conditional", "label": "komplex"},
    {"source": "node:synthesis_hitl", "target": "node:synthesizer", "type": "conditional", "label": "enkel"},
    {"source": "node:progressive_synthesizer", "target": "node:synthesizer", "type": "normal"},
]

# Stage metadata for frontend grouping and coloring
_PIPELINE_STAGES: list[dict[str, str]] = [
    {"id": "entry", "label": "Ingång", "color": "violet"},
    {"id": "fast_path", "label": "Snabbsvar", "color": "amber"},
    {"id": "speculative", "label": "Spekulativ", "color": "slate"},
    {"id": "planning", "label": "Planering", "color": "blue"},
    {"id": "tool_resolution", "label": "Verktygsval", "color": "cyan"},
    {"id": "execution", "label": "Exekvering", "color": "emerald"},
    {"id": "post_processing", "label": "Efterbehandling", "color": "slate"},
    {"id": "evaluation", "label": "Utvärdering", "color": "orange"},
    {"id": "synthesis", "label": "Syntes", "color": "rose"},
]


# ── Intent → Route → Agent policy mapping ──────────────────────────────
_ROUTE_AGENT_POLICIES: dict[str, list[str]] = {
    "kunskap": [
        "kunskap", "webb", "väder", "trafik", "statistik",
        "bolag", "riksdagen", "marknad",
    ],
    "skapande": ["media", "kartor", "kod"],
    "jämförelse": ["syntes", "statistik", "kunskap"],
    "konversation": [],
}

# ── Agent → Tool mapping (hardcoded tool IDs per agent namespace) ──────
_AGENT_TOOL_MAP: dict[str, list[dict[str, str]]] = {
    "kunskap": [
        {"tool_id": "search_surfsense_docs", "label": "SurfSense Docs"},
        {"tool_id": "save_memory", "label": "Spara Minne"},
        {"tool_id": "recall_memory", "label": "Hämta Minne"},
        {"tool_id": "tavily_search", "label": "Tavily Sök"},
    ],
    "webb": [
        {"tool_id": "scrape_webpage", "label": "Scrape Webbsida"},
        {"tool_id": "link_preview", "label": "Länk Förhandsgranskning"},
        {"tool_id": "public_web_search", "label": "Webbsökning"},
    ],
    "väder": [
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
    "marknad": [
        {"tool_id": "marketplace_unified_search", "label": "Unified Search"},
        {"tool_id": "marketplace_blocket_search", "label": "Blocket Sök"},
        {"tool_id": "marketplace_blocket_cars", "label": "Blocket Bilar"},
        {"tool_id": "marketplace_blocket_boats", "label": "Blocket Båtar"},
        {"tool_id": "marketplace_blocket_mc", "label": "Blocket MC"},
        {"tool_id": "marketplace_tradera_search", "label": "Tradera Sök"},
        {"tool_id": "marketplace_compare_prices", "label": "Prisjämförelse"},
    ],
    "statistik": [
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
    "kod": [
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
    "åtgärd": [
        {"tool_id": "search_knowledge_base", "label": "Kunskapsbas"},
        {"tool_id": "link_preview", "label": "Länk Förhandsgranskning"},
        {"tool_id": "scrape_webpage", "label": "Scrape Webbsida"},
    ],
    "syntes": [
        {"tool_id": "external_model_compare", "label": "Modelljämförelse"},
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
    """Return the LangGraph pipeline graph and intent → agent → tool routing data."""
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
        # Pipeline (LangGraph execution flow)
        "pipeline_nodes": _PIPELINE_NODES,
        "pipeline_edges": _PIPELINE_EDGES,
        "pipeline_stages": _PIPELINE_STAGES,
        # Routing (intent → agent → tool)
        "intents": intent_nodes,
        "agents": agent_nodes,
        "tools": tool_nodes,
        "intent_agent_edges": intent_agent_edges,
        "agent_tool_edges": agent_tool_edges,
    }
