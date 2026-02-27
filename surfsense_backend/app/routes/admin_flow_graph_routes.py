"""Admin endpoint that returns the LangGraph pipeline graph and routing data."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import (
    SearchSpaceMembership,
    User,
    get_async_session,
)
from app.services.agent_metadata_service import (
    get_effective_agent_metadata,
    upsert_global_agent_metadata_overrides,
)
from app.services.intent_definition_service import (
    get_effective_intent_definitions,
    upsert_global_intent_definition_overrides,
)
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
        "prompt_key": "supervisor.intent_resolver.system",
    },
    {
        "id": "node:memory_context",
        "label": "Memory Context",
        "stage": "entry",
        "description": "Laddar minneskontext och samtalshistorik.",
        "prompt_key": None,
    },
    # ── Fast paths ──
    {
        "id": "node:smalltalk",
        "label": "Smalltalk",
        "stage": "fast_path",
        "description": "Snabb hälsningssvar (konversation-route). → END",
        "prompt_key": "agent.smalltalk.system",
    },
    # ── Multi-query decomposition ──
    {
        "id": "node:multi_query_decomposer",
        "label": "Multi-Query Decomposer",
        "stage": "entry",
        "description": "Bryter ned komplexa frågor till atomära delfrågor med beroendegraf (P3). Skippas för enkla/triviala frågor.",
        "prompt_key": "supervisor.decomposer.system",
    },
    # ── Speculative ──
    {
        "id": "node:speculative",
        "label": "Speculative",
        "stage": "speculative",
        "description": "Förberäknar troliga verktyg parallellt (hybrid-läge, komplex fråga).",
        "prompt_key": None,
    },
    # ── Planning ──
    {
        "id": "node:agent_resolver",
        "label": "Agent Resolver",
        "stage": "planning",
        "description": "Hämtar och väljer agenter via vektor-retrieval + LLM-rankning.",
        "prompt_key": "supervisor.agent_resolver.system",
    },
    {
        "id": "node:planner",
        "label": "Planner",
        "stage": "planning",
        "description": "Skapar exekverbar plan (max 4 steg) baserat på valda agenter.",
        "prompt_key": "supervisor.planner.system",
    },
    {
        "id": "node:planner_hitl_gate",
        "label": "Planner HITL",
        "stage": "planning",
        "description": "Human-in-the-loop: pausar för användarens godkännande av planen.",
        "prompt_key": "supervisor.hitl.planner.message",
    },
    # ── Tool resolution ──
    {
        "id": "node:tool_resolver",
        "label": "Tool Resolver",
        "stage": "tool_resolution",
        "description": "Matchar plansteg → verktyg via vektor-retrieval.",
        "prompt_key": "supervisor.tool_resolver.system",
    },
    {
        "id": "node:speculative_merge",
        "label": "Speculative Merge",
        "stage": "tool_resolution",
        "description": "Mergar spekulativa verktygskandidater med resolver-resultat.",
        "prompt_key": None,
    },
    {
        "id": "node:execution_router",
        "label": "Execution Router",
        "stage": "tool_resolution",
        "description": "Bestämmer exekverings-strategi (inline/subagent/parallel) per gren.",
        "prompt_key": None,
    },
    {
        "id": "node:domain_planner",
        "label": "Domain Planner",
        "stage": "tool_resolution",
        "description": "LLM-driven mikro-plan per domänagent: vilka sub-verktyg och om de körs parallellt eller sekventiellt (Nivå 2 agentplan).",
        "prompt_key": "supervisor.domain_planner.system",
    },
    # ── Execution ──
    {
        "id": "node:execution_hitl_gate",
        "label": "Execution HITL",
        "stage": "execution",
        "description": "Human-in-the-loop: pausar för godkännande innan verktygsanrop.",
        "prompt_key": "supervisor.hitl.execution.message",
    },
    {
        "id": "node:executor",
        "label": "Executor (LLM)",
        "stage": "execution",
        "description": "LLM-anrop som genererar svar eller tool_calls.",
        "prompt_key": "agent.supervisor.system",
    },
    {
        "id": "node:tools",
        "label": "Tools",
        "stage": "execution",
        "description": "Kör verktygsanrop (SMHI, SCB, Trafikverket, sandbox, etc.).",
        "prompt_key": None,
    },
    {
        "id": "node:post_tools",
        "label": "Post-Tools",
        "stage": "execution",
        "description": "Efterbehandling av verktygsresultat.",
        "prompt_key": None,
    },
    # ── Post-processing ──
    {
        "id": "node:artifact_indexer",
        "label": "Artifact Indexer",
        "stage": "post_processing",
        "description": "Indexerar artefakter (filer, data) för framtida referens.",
        "prompt_key": None,
    },
    {
        "id": "node:context_compactor",
        "label": "Context Compactor",
        "stage": "post_processing",
        "description": "Komprimerar kontext för att hålla sig inom token-budget.",
        "prompt_key": None,
    },
    {
        "id": "node:orchestration_guard",
        "label": "Orchestration Guard",
        "stage": "post_processing",
        "description": "Loop-guard och verktygs-limit-guard mot oändliga loopar.",
        "prompt_key": "supervisor.loop_guard.message",
    },
    # ── P4: Subagent Mini-Graphs ──
    {
        "id": "node:subagent_spawner",
        "label": "Subagent Spawner",
        "stage": "subagent",
        "description": "Startar isolerade mini-grafer per domänagent med egen checkpointer (P4.1).",
        "prompt_key": "supervisor.subagent_spawner.system",
    },
    {
        "id": "node:mini_planner",
        "label": "Mini Planner",
        "stage": "subagent",
        "description": "Skapar kompakt mikro-plan per domän inuti subagent mini-graf (P4.1).",
        "prompt_key": "supervisor.mini_planner.system",
    },
    {
        "id": "node:mini_executor",
        "label": "Mini Executor",
        "stage": "subagent",
        "description": "Kör verktygsanrop inuti subagent mini-graf (P4.1).",
        "prompt_key": None,
    },
    {
        "id": "node:mini_critic",
        "label": "Mini Critic",
        "stage": "subagent",
        "description": "Bedömer domänresultat inuti subagent mini-graf: ok/retry/fail (P4.1).",
        "prompt_key": "supervisor.mini_critic.system",
    },
    {
        "id": "node:mini_synthesizer",
        "label": "Mini Synthesizer",
        "stage": "subagent",
        "description": "Sammanfattar domänresultat till kompakt artefakt inuti subagent mini-graf (P4.1).",
        "prompt_key": "supervisor.mini_synthesizer.system",
    },
    {
        "id": "node:pev_verify",
        "label": "PEV Verify",
        "stage": "subagent",
        "description": "Plan-Execute-Verify: verifierar att exekvering matchar plan (P4.1d, valfritt).",
        "prompt_key": "supervisor.pev_verify.system",
    },
    {
        "id": "node:adaptive_guard",
        "label": "Adaptive Guard",
        "stage": "subagent",
        "description": "Dynamisk budget- och tröskeljustering per subagent via ProgressTracker (P4.2a).",
        "prompt_key": "supervisor.adaptive_guard.system",
    },
    {
        "id": "node:convergence_node",
        "label": "Convergence",
        "stage": "subagent",
        "description": "Slår ihop resultat från parallella subagent mini-grafer till unified artefakt (P4.1).",
        "prompt_key": "supervisor.convergence.system",
    },
    {
        "id": "node:semantic_cache",
        "label": "Semantic Cache",
        "stage": "subagent",
        "description": "Redis/LangGraph Store cache per domän — cache hit skippar verktygsanrop (P4.3).",
        "prompt_key": None,
    },
    # ── Compare mode ──
    # ── Compare Supervisor v2 (unified P4 architecture) ──
    {
        "id": "node:compare_domain_planner",
        "label": "Compare Domain Planner",
        "stage": "compare",
        "description": "Deterministisk domänplanering — genererar domain_plans för 7 externa modeller + 1 research-agent.",
        "prompt_key": "compare.domain_planner.system",
    },
    {
        "id": "node:compare_subagent_spawner",
        "label": "Compare Subagent Spawner",
        "stage": "compare",
        "description": "Startar isolerade subagent mini-grafer per domän (P4-mönster). Varje modell och research-agenten körs parallellt med handoff contracts.",
        "prompt_key": "compare.mini_planner.system",
    },
    {
        "id": "node:compare_mini_critic",
        "label": "Compare Mini Critic",
        "stage": "compare",
        "description": "Per-modell critic som utvärderar svarskvalitet. Retry med adaptive guard vid behov.",
        "prompt_key": "compare.mini_critic.system",
    },
    {
        "id": "node:compare_convergence",
        "label": "Compare Convergence",
        "stage": "compare",
        "description": "LLM-driven merge av alla domänresultat. Identifierar overlap, konflikter, och skapar unified artefakt. Research-agenten prioriteras.",
        "prompt_key": "compare.convergence.system",
    },
    {
        "id": "node:compare_synthesizer",
        "label": "Compare Synthesizer",
        "stage": "compare",
        "description": "Slutgiltig syntes från convergence-data + per-domän handoffs. Producerar strukturerat jämförelse-svar. → END",
        "prompt_key": "compare.analysis.system",
    },
    # ── Evaluation ──
    {
        "id": "node:critic",
        "label": "Critic",
        "stage": "evaluation",
        "description": "Bedömer om svaret är tillräckligt (ok/needs_more/replan).",
        "prompt_key": "supervisor.critic.system",
    },
    # ── Synthesis ──
    {
        "id": "node:synthesis_hitl",
        "label": "Synthesis HITL",
        "stage": "synthesis",
        "description": "Human-in-the-loop: pausar för godkännande innan leverans.",
        "prompt_key": "supervisor.hitl.synthesis.message",
    },
    {
        "id": "node:progressive_synthesizer",
        "label": "Progressive Synthesizer",
        "stage": "synthesis",
        "description": "Inkrementell streaming-syntes för komplexa svar.",
        "prompt_key": "supervisor.synthesizer.system",
    },
    {
        "id": "node:synthesizer",
        "label": "Synthesizer",
        "stage": "synthesis",
        "description": "Slutgiltig förfining och formatering av svaret.",
        "prompt_key": "supervisor.synthesizer.system",
    },
    {
        "id": "node:response_layer_router",
        "label": "RL Router",
        "stage": "synthesis",
        "description": "LLM-driven analys av data → väljer presentationsläge (Kunskap/Analys/Syntes/Visualisering). Reasoning visas i think-boxen.",
        "prompt_key": "supervisor.response_layer.router",
    },
    {
        "id": "node:response_layer",
        "label": "Response Layer",
        "stage": "synthesis",
        "description": "Nivå 4: formaterar svaret enligt valt presentationsläge.",
        "prompt_key": None,
    },
    # ── Response Layer per-mode nodes (editable prompts) ──
    {
        "id": "node:response_layer_kunskap",
        "label": "RL: Kunskap",
        "stage": "synthesis",
        "description": "Formateringsregler för kunskap-läge — direkt, faktabaserat svar.",
        "prompt_key": "supervisor.response_layer.kunskap",
    },
    {
        "id": "node:response_layer_analys",
        "label": "RL: Analys",
        "stage": "synthesis",
        "description": "Formateringsregler för analys-läge — strukturerat svar med sektioner och motivering.",
        "prompt_key": "supervisor.response_layer.analys",
    },
    {
        "id": "node:response_layer_syntes",
        "label": "RL: Syntes",
        "stage": "synthesis",
        "description": "Formateringsregler för syntes-läge — fler-källors syntes som namnger ursprung.",
        "prompt_key": "supervisor.response_layer.syntes",
    },
    {
        "id": "node:response_layer_visualisering",
        "label": "RL: Visualisering",
        "stage": "synthesis",
        "description": "Formateringsregler för visualisering-läge — data som tabell eller strukturerad lista. → END",
        "prompt_key": "supervisor.response_layer.visualisering",
    },
]

_PIPELINE_EDGES: list[dict[str, Any]] = [
    # ── Main flow ──
    {"source": "node:resolve_intent", "target": "node:memory_context", "type": "normal"},
    # ── Conditional from memory_context (route_after_intent) ──
    {"source": "node:memory_context", "target": "node:smalltalk", "type": "conditional", "label": "konversation"},
    {"source": "node:memory_context", "target": "node:multi_query_decomposer", "type": "conditional", "label": "komplex"},
    {"source": "node:memory_context", "target": "node:agent_resolver", "type": "conditional", "label": "default"},
    {"source": "node:memory_context", "target": "node:tool_resolver", "type": "conditional", "label": "enkel"},
    {"source": "node:memory_context", "target": "node:synthesis_hitl", "type": "conditional", "label": "finalize"},
    # ── Multi-query decomposer → speculative ──
    {"source": "node:multi_query_decomposer", "target": "node:speculative", "type": "normal"},
    # ── Speculative → planning ──
    {"source": "node:speculative", "target": "node:agent_resolver", "type": "normal"},
    # ── Planning flow ──
    {"source": "node:agent_resolver", "target": "node:planner", "type": "normal"},
    {"source": "node:planner", "target": "node:planner_hitl_gate", "type": "normal"},
    {"source": "node:planner_hitl_gate", "target": "node:tool_resolver", "type": "conditional", "label": "godkänd"},
    # ── Tool resolution → domain planner → execution ──
    {"source": "node:tool_resolver", "target": "node:speculative_merge", "type": "normal"},
    {"source": "node:speculative_merge", "target": "node:execution_router", "type": "normal"},
    {"source": "node:execution_router", "target": "node:domain_planner", "type": "normal"},
    {"source": "node:domain_planner", "target": "node:execution_hitl_gate", "type": "normal"},
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
    # ── P4: Subagent Mini-Graph edges ──
    {"source": "node:domain_planner", "target": "node:subagent_spawner", "type": "conditional", "label": "P4 subagent"},
    {"source": "node:subagent_spawner", "target": "node:mini_planner", "type": "normal"},
    {"source": "node:mini_planner", "target": "node:semantic_cache", "type": "normal"},
    {"source": "node:semantic_cache", "target": "node:mini_synthesizer", "type": "conditional", "label": "cache hit"},
    {"source": "node:semantic_cache", "target": "node:mini_executor", "type": "conditional", "label": "cache miss"},
    {"source": "node:mini_executor", "target": "node:mini_critic", "type": "normal"},
    {"source": "node:mini_critic", "target": "node:adaptive_guard", "type": "normal"},
    {"source": "node:adaptive_guard", "target": "node:mini_synthesizer", "type": "conditional", "label": "ok / budget slut"},
    {"source": "node:adaptive_guard", "target": "node:mini_executor", "type": "conditional", "label": "retry"},
    {"source": "node:mini_critic", "target": "node:pev_verify", "type": "conditional", "label": "PEV aktivt"},
    {"source": "node:pev_verify", "target": "node:mini_synthesizer", "type": "conditional", "label": "verified"},
    {"source": "node:pev_verify", "target": "node:mini_executor", "type": "conditional", "label": "deviation"},
    {"source": "node:mini_synthesizer", "target": "node:convergence_node", "type": "normal"},
    {"source": "node:convergence_node", "target": "node:critic", "type": "normal"},
    # ── Compare Supervisor v2 edges ──
    {"source": "node:resolve_intent", "target": "node:compare_domain_planner", "type": "conditional", "label": "jämförelse"},
    {"source": "node:compare_domain_planner", "target": "node:compare_subagent_spawner", "type": "normal"},
    {"source": "node:compare_subagent_spawner", "target": "node:compare_mini_critic", "type": "normal"},
    {"source": "node:compare_mini_critic", "target": "node:compare_subagent_spawner", "type": "conditional", "label": "retry"},
    {"source": "node:compare_mini_critic", "target": "node:compare_convergence", "type": "conditional", "label": "ok"},
    {"source": "node:compare_subagent_spawner", "target": "node:compare_convergence", "type": "normal"},
    {"source": "node:compare_convergence", "target": "node:compare_synthesizer", "type": "normal"},
    # ── Critic decisions ──
    {"source": "node:critic", "target": "node:synthesis_hitl", "type": "conditional", "label": "ok"},
    {"source": "node:critic", "target": "node:tool_resolver", "type": "conditional", "label": "needs_more"},
    {"source": "node:critic", "target": "node:planner", "type": "conditional", "label": "replan"},
    # ── Synthesis → response layer ──
    {"source": "node:synthesis_hitl", "target": "node:progressive_synthesizer", "type": "conditional", "label": "komplex"},
    {"source": "node:synthesis_hitl", "target": "node:synthesizer", "type": "conditional", "label": "enkel"},
    {"source": "node:progressive_synthesizer", "target": "node:synthesizer", "type": "normal"},
    {"source": "node:synthesizer", "target": "node:response_layer_router", "type": "normal"},
    {"source": "node:response_layer_router", "target": "node:response_layer", "type": "normal"},
    # ── Response Layer → per-mode nodes (conditional) ──
    {"source": "node:response_layer", "target": "node:response_layer_kunskap", "type": "conditional", "label": "kunskap"},
    {"source": "node:response_layer", "target": "node:response_layer_analys", "type": "conditional", "label": "analys"},
    {"source": "node:response_layer", "target": "node:response_layer_syntes", "type": "conditional", "label": "syntes"},
    {"source": "node:response_layer", "target": "node:response_layer_visualisering", "type": "conditional", "label": "visualisering"},
]

# Stage metadata for frontend grouping and coloring
_PIPELINE_STAGES: list[dict[str, str]] = [
    {"id": "entry", "label": "Ingång", "color": "violet"},
    {"id": "fast_path", "label": "Snabbsvar", "color": "amber"},
    {"id": "speculative", "label": "Spekulativ", "color": "slate"},
    {"id": "planning", "label": "Planering", "color": "blue"},
    {"id": "tool_resolution", "label": "Verktygsval / Domänplan", "color": "cyan"},
    {"id": "subagent", "label": "Subagent Mini-Graphs", "color": "indigo"},
    {"id": "compare", "label": "Jämförelse", "color": "purple"},
    {"id": "execution", "label": "Exekvering", "color": "emerald"},
    {"id": "post_processing", "label": "Efterbehandling", "color": "slate"},
    {"id": "evaluation", "label": "Utvärdering", "color": "orange"},
    {"id": "synthesis", "label": "Syntes / Response Layer", "color": "rose"},
]


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
    """Return the LangGraph pipeline graph and intent → agent → tool routing data.

    All routing data (intents, agents, tools, edges) is built dynamically from
    DB-backed services — nothing is hardcoded.
    """
    await _require_admin(session, user)

    # ── Read from DB ──
    intents = await get_effective_intent_definitions(session)
    agents = await get_effective_agent_metadata(session)

    # ── Build intent nodes ──
    intent_nodes: list[dict[str, Any]] = []
    for intent in intents:
        intent_id = intent.get("intent_id", "")
        intent_nodes.append({
            "id": f"intent:{intent_id}",
            "type": "intent",
            "intent_id": intent_id,
            "label": intent.get("label", intent_id),
            "description": intent.get("description", ""),
            "route": intent.get("route", ""),
            "keywords": intent.get("keywords", []),
            "priority": intent.get("priority", 500),
            "enabled": intent.get("enabled", True),
            "main_identifier": intent.get("main_identifier", ""),
            "core_activity": intent.get("core_activity", ""),
            "unique_scope": intent.get("unique_scope", ""),
            "geographic_scope": intent.get("geographic_scope", ""),
            "excludes": intent.get("excludes", []),
        })
    intent_ids = {intent.get("intent_id", "") for intent in intents}

    # ── Build agent nodes & intent→agent edges from agent.routes ──
    agent_nodes: list[dict[str, Any]] = []
    intent_agent_edges: list[dict[str, str]] = []
    for agent in agents:
        agent_id = agent.get("agent_id", "")
        agent_nodes.append({
            "id": f"agent:{agent_id}",
            "type": "agent",
            "agent_id": agent_id,
            "label": agent.get("label", agent_id),
            "description": agent.get("description", ""),
            "keywords": agent.get("keywords", []),
            "prompt_key": agent.get("prompt_key", ""),
            "namespace": agent.get("namespace", []),
            "routes": agent.get("routes", []),
            "main_identifier": agent.get("main_identifier", ""),
            "core_activity": agent.get("core_activity", ""),
            "unique_scope": agent.get("unique_scope", ""),
            "geographic_scope": agent.get("geographic_scope", ""),
            "excludes": agent.get("excludes", []),
        })
        for route_id in agent.get("routes", []):
            if route_id in intent_ids:
                intent_agent_edges.append({
                    "source": f"intent:{route_id}",
                    "target": f"agent:{agent_id}",
                })

    # ── Build tool nodes & agent→tool edges from agent.flow_tools ──
    tool_nodes: list[dict[str, Any]] = []
    agent_tool_edges: list[dict[str, str]] = []
    seen_tools: set[str] = set()
    for agent in agents:
        agent_id = agent.get("agent_id", "")
        for tool_entry in agent.get("flow_tools", []):
            tool_id = tool_entry.get("tool_id", "")
            if not tool_id:
                continue
            if tool_id not in seen_tools:
                seen_tools.add(tool_id)
                tool_nodes.append({
                    "id": f"tool:{tool_id}",
                    "type": "tool",
                    "tool_id": tool_id,
                    "label": tool_entry.get("label", tool_id),
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


# ── Save endpoints ────────────────────────────────────────────────────


class FlowToolEntry(BaseModel):
    tool_id: str
    label: str


class UpdateAgentRoutesRequest(BaseModel):
    agent_id: str
    routes: list[str]


class UpdateAgentToolsRequest(BaseModel):
    agent_id: str
    flow_tools: list[FlowToolEntry]


class UpdateIntentRequest(BaseModel):
    intent_id: str
    label: str | None = None
    route: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    priority: int | None = None
    enabled: bool | None = None
    main_identifier: str | None = None
    core_activity: str | None = None
    unique_scope: str | None = None
    geographic_scope: str | None = None
    excludes: list[str] | None = None


class UpsertAgentRequest(BaseModel):
    agent_id: str
    label: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    prompt_key: str | None = None
    namespace: list[str] | None = None
    routes: list[str] | None = None
    flow_tools: list[FlowToolEntry] | None = None
    main_identifier: str | None = None
    core_activity: str | None = None
    unique_scope: str | None = None
    geographic_scope: str | None = None
    excludes: list[str] | None = None


class DeleteAgentRequest(BaseModel):
    agent_id: str


class DeleteIntentRequest(BaseModel):
    intent_id: str


@router.put("/flow-graph/agent")
async def upsert_agent(
    request: UpsertAgentRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, str]:
    """Create or update an agent definition."""
    await _require_admin(session, user)
    payload: dict[str, Any] = {}
    if request.label is not None:
        payload["label"] = request.label
    if request.description is not None:
        payload["description"] = request.description
    if request.keywords is not None:
        payload["keywords"] = request.keywords
    if request.prompt_key is not None:
        payload["prompt_key"] = request.prompt_key
    if request.namespace is not None:
        payload["namespace"] = request.namespace
    if request.routes is not None:
        payload["routes"] = request.routes
    if request.flow_tools is not None:
        payload["flow_tools"] = [t.model_dump() for t in request.flow_tools]
    if request.main_identifier is not None:
        payload["main_identifier"] = request.main_identifier
    if request.core_activity is not None:
        payload["core_activity"] = request.core_activity
    if request.unique_scope is not None:
        payload["unique_scope"] = request.unique_scope
    if request.geographic_scope is not None:
        payload["geographic_scope"] = request.geographic_scope
    if request.excludes is not None:
        payload["excludes"] = request.excludes
    await upsert_global_agent_metadata_overrides(
        session,
        [(request.agent_id, payload)],
        updated_by_id=str(user.id),
    )
    await session.commit()
    return {"status": "ok"}


@router.delete("/flow-graph/agent")
async def delete_agent(
    request: DeleteAgentRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, str]:
    """Delete an agent definition override (reverts to default if exists)."""
    await _require_admin(session, user)
    await upsert_global_agent_metadata_overrides(
        session,
        [(request.agent_id, None)],
        updated_by_id=str(user.id),
    )
    await session.commit()
    return {"status": "ok"}


@router.patch("/flow-graph/agent-routes")
async def update_agent_routes(
    request: UpdateAgentRoutesRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, str]:
    """Update which routes/intents an agent is assigned to."""
    await _require_admin(session, user)
    await upsert_global_agent_metadata_overrides(
        session,
        [(request.agent_id, {"routes": request.routes})],
        updated_by_id=str(user.id),
    )
    await session.commit()
    return {"status": "ok"}


@router.patch("/flow-graph/agent-tools")
async def update_agent_tools(
    request: UpdateAgentToolsRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, str]:
    """Update which tools belong to an agent in the flow graph."""
    await _require_admin(session, user)
    await upsert_global_agent_metadata_overrides(
        session,
        [(
            request.agent_id,
            {"flow_tools": [t.model_dump() for t in request.flow_tools]},
        )],
        updated_by_id=str(user.id),
    )
    await session.commit()
    return {"status": "ok"}


@router.put("/flow-graph/intent")
async def upsert_intent(
    request: UpdateIntentRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, str]:
    """Create or update an intent definition."""
    await _require_admin(session, user)
    payload: dict[str, Any] = {}
    if request.label is not None:
        payload["label"] = request.label
    if request.route is not None:
        payload["route"] = request.route
    if request.description is not None:
        payload["description"] = request.description
    if request.keywords is not None:
        payload["keywords"] = request.keywords
    if request.priority is not None:
        payload["priority"] = request.priority
    if request.enabled is not None:
        payload["enabled"] = request.enabled
    if request.main_identifier is not None:
        payload["main_identifier"] = request.main_identifier
    if request.core_activity is not None:
        payload["core_activity"] = request.core_activity
    if request.unique_scope is not None:
        payload["unique_scope"] = request.unique_scope
    if request.geographic_scope is not None:
        payload["geographic_scope"] = request.geographic_scope
    if request.excludes is not None:
        payload["excludes"] = request.excludes
    await upsert_global_intent_definition_overrides(
        session,
        [(request.intent_id, payload)],
        updated_by_id=str(user.id),
    )
    await session.commit()
    return {"status": "ok"}


@router.delete("/flow-graph/intent")
async def delete_intent(
    request: DeleteIntentRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, str]:
    """Delete an intent definition override (reverts to default if exists)."""
    await _require_admin(session, user)
    await upsert_global_intent_definition_overrides(
        session,
        [(request.intent_id, None)],
        updated_by_id=str(user.id),
    )
    await session.commit()
    return {"status": "ok"}
