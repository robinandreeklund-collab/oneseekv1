from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import Checkpointer
from langgraph_bigtool.graph import END, RunnableCallable, StateGraph, ToolNode
from langgraph_bigtool.tools import InjectedState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.bigtool_store import (
    build_global_tool_registry,
    build_tool_index,
    get_namespace_tool_ids_with_retrieval_hints,
    smart_retrieve_tools_with_breakdown,
)
from app.agents.new_chat.bigtool_workers import WorkerConfig
from app.agents.new_chat.compare_prompts import DEFAULT_COMPARE_ANALYSIS_PROMPT
from app.agents.new_chat.domain_fan_out import (
    execute_domain_fan_out,
    format_fan_out_context,
    is_fan_out_enabled,
)
from app.agents.new_chat.episodic_memory import (
    get_or_create_episodic_store,
    infer_ttl_seconds,
)
from app.agents.new_chat.hybrid_state import (
    build_speculative_candidates,
    build_trivial_response,
    classify_graph_complexity,
)
from app.agents.new_chat.marketplace_tools import MARKETPLACE_TOOL_DEFINITIONS
from app.agents.new_chat.nodes import (
    build_agent_resolver_node,
    build_critic_node,
    build_domain_planner_node,
    build_execution_hitl_gate_node,
    build_execution_router_node,
    build_executor_nodes,
    build_intent_resolver_node,
    build_multi_query_decomposer_node,
    build_planner_hitl_gate_node,
    build_planner_node,
    build_progressive_synthesizer_node,
    build_response_layer_node,
    build_response_layer_router_node,
    build_smart_critic_node,
    build_speculative_merge_node,
    build_speculative_node,
    build_synthesis_hitl_gate_node,
    build_synthesizer_node,
    build_tool_resolver_node,
)
from app.agents.new_chat.nodes.execution_router import get_execution_timeout_seconds
from app.agents.new_chat.prompt_registry import resolve_prompt
from app.agents.new_chat.response_compressor import compress_response
from app.agents.new_chat.retrieval_feedback import (
    get_global_retrieval_feedback_store,
    hydrate_global_retrieval_feedback_store,
)
from app.agents.new_chat.shared_worker_pool import get_or_create_shared_worker_pool
from app.agents.new_chat.structured_schemas import structured_output_enabled
from app.agents.new_chat.subagent_utils import SMALLTALK_INSTRUCTIONS
from app.agents.new_chat.supervisor_pipeline_prompts import (
    DEFAULT_RESPONSE_LAYER_ANALYS_PROMPT,
    DEFAULT_RESPONSE_LAYER_KUNSKAP_PROMPT,
    DEFAULT_RESPONSE_LAYER_ROUTER_PROMPT,
    DEFAULT_RESPONSE_LAYER_SYNTES_PROMPT,
    DEFAULT_RESPONSE_LAYER_VISUALISERING_PROMPT,
    DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
    DEFAULT_SUPERVISOR_DECOMPOSER_PROMPT,
    DEFAULT_SUPERVISOR_DOMAIN_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE,
    DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE,
    DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE,
    DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_MULTI_DOMAIN_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
    DEFAULT_SUPERVISOR_TOOL_RESOLVER_PROMPT,
)
from app.agents.new_chat.supervisor_runtime_prompts import (
    DEFAULT_SUPERVISOR_CODE_READ_FILE_ENFORCEMENT_MESSAGE,
    DEFAULT_SUPERVISOR_CODE_SANDBOX_ENFORCEMENT_MESSAGE,
    DEFAULT_SUPERVISOR_CRITIC_PROMPT,
    DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
    DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE,
    DEFAULT_SUPERVISOR_SUBAGENT_CONTEXT_TEMPLATE,
    DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
    DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
    DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE,
)
from app.agents.new_chat.system_prompt import (
    SURFSENSE_CORE_GLOBAL_PROMPT,
    append_datetime_context,
    inject_core_prompt,
)
from app.agents.new_chat.token_budget import TokenBudget
from app.agents.new_chat.tools.external_models import (
    DEFAULT_EXTERNAL_SYSTEM_PROMPT,
    EXTERNAL_MODEL_SPECS,
    call_external_model,
)
from app.agents.new_chat.tools.reflect_on_progress import (
    create_reflect_on_progress_tool,
)
from app.agents.new_chat.tools.smhi import SMHI_TOOL_DEFINITIONS
from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.write_todos import create_write_todos_tool
from app.db import UserMemory
from app.services.agent_metadata_service import get_effective_agent_metadata
from app.services.retrieval_feedback_persistence_service import (
    load_retrieval_feedback_snapshot,
    persist_retrieval_feedback_signal,
)
from app.services.tool_metadata_service import get_global_tool_metadata_overrides
from app.services.tool_retrieval_tuning_service import (
    get_global_tool_retrieval_tuning,
    normalize_tool_retrieval_tuning,
)

logger = logging.getLogger(__name__)


# Import from extracted modules
from app.agents.new_chat.supervisor_agent_retrieval import (
    _smart_retrieve_agents,
    _smart_retrieve_agents_with_breakdown,
)
from app.agents.new_chat.supervisor_cache import (
    _build_cache_key,
    _fetch_cached_combo_db,
    _get_cached_combo,
    _set_cached_combo,
    _store_cached_combo_db,
)
from app.agents.new_chat.supervisor_constants import (
    _ARTIFACT_DEFAULT_MAX_ENTRIES,
    _ARTIFACT_DEFAULT_OFFLOAD_THRESHOLD_CHARS,
    _ARTIFACT_DEFAULT_STORAGE_MODE,
    _ARTIFACT_INTERNAL_TOOL_NAMES,
    _ARTIFACT_OFFLOAD_PER_PASS_LIMIT,
    _COMPARE_FOLLOWUP_RE,
    _CONTEXT_COMPACTION_DEFAULT_STEP_KEEP,
    _CONTEXT_COMPACTION_DEFAULT_SUMMARY_MAX_CHARS,
    _CONTEXT_COMPACTION_DEFAULT_TRIGGER_RATIO,
    _CONTEXT_COMPACTION_MIN_MESSAGES,
    _EXPLICIT_FILE_READ_RE,
    _EXTERNAL_MODEL_TOOL_NAMES,
    _FILESYSTEM_NOT_FOUND_MARKERS,
    _LIVE_ROUTING_PHASE_ORDER,
    _LOOP_GUARD_MAX_CONSECUTIVE,
    _MARKETPLACE_PROVIDER_RE,
    _MAX_AGENT_HOPS_PER_TURN,
    _SANDBOX_ALIAS_TOOL_IDS,
    _SANDBOX_CODE_TOOL_IDS,
    _SPECIALIZED_AGENTS,
    _SUBAGENT_DEFAULT_CONTEXT_MAX_CHARS,
    _SUBAGENT_DEFAULT_MAX_CONCURRENCY,
    _SUBAGENT_DEFAULT_RESULT_MAX_CHARS,
    _SUBAGENT_MAX_HANDOFFS_IN_PROMPT,
    KEEP_TOOL_MSG_COUNT,
    MAX_TOTAL_STEPS,
    MESSAGE_PRUNING_THRESHOLD,
    TOOL_MSG_THRESHOLD,
    _live_phase_enabled,
    _normalize_live_routing_phase,
)
from app.agents.new_chat.supervisor_memory import (
    _persist_artifact_content,
    _render_cross_session_memory_context,
    _select_cross_session_memory_entries,
)
from app.agents.new_chat.supervisor_routing import (
    _focused_tool_ids_for_agent,
    _guess_agent_from_alias,
    _has_filesystem_intent,
    _has_map_intent,
    _has_marketplace_intent,
    _has_strict_trafik_intent,
    _has_trafik_intent,
    _has_weather_intent,
    _is_weather_tool_id,
    _normalize_route_hint_value,
    _route_allowed_agents,
    _route_default_agent,
)
from app.agents.new_chat.supervisor_state_utils import (
    _count_tools_since_last_user,
    _format_artifact_manifest_context,
    _format_compare_outputs_for_prompt,
    _format_cross_session_memory_context,
    _format_execution_strategy,
    _format_intent_context,
    _format_plan_context,
    _format_recent_calls,
    _format_resolved_tools_context,
    _format_rolling_context_summary_context,
    _format_route_hint,
    _format_selected_agents_context,
    _format_subagent_handoffs_context,
    _tool_call_name_index,
)
from app.agents.new_chat.supervisor_text_utils import (
    _coerce_confidence,
    _coerce_float_range,
    _coerce_int_range,
    _extract_first_json_object,
    _parse_hitl_confirmation,
    _render_hitl_message,
    _safe_json,
    _serialize_artifact_payload,
    _strip_critic_json,
    _truncate_for_prompt,
)
from app.agents.new_chat.supervisor_tools import (
    _build_scoped_prompt_for_agent,
    _build_tool_prompt_block,
    _fallback_tool_ids_for_tool,
    _format_prompt_template,
    _sanitize_selected_tool_ids_for_worker,
)
from app.agents.new_chat.supervisor_types import (
    AgentDefinition,
    SupervisorState,
)

_MAX_TOOL_CALLS_PER_TURN = int(os.environ.get("MAX_TOOL_CALLS", "8"))
_MAX_SUPERVISOR_TOOL_CALLS_PER_STEP = 1
# If the same direct tool (e.g. scb_befolkning, smhi_vaderprognoser_metfcst)
# is called this many times consecutively, force finalization.
_MAX_CONSECUTIVE_SAME_TOOL = 2
_MAX_REPLAN_ATTEMPTS = int(os.environ.get("MAX_REPLAN_ATTEMPTS", "3"))


_HITL_APPROVE_RE = re.compile(
    r"\b(ja|yes|ok|okej|kor|kör|go|fortsatt|fortsätt)\b", re.IGNORECASE
)
_HITL_REJECT_RE = re.compile(r"\b(nej|no|stopp|avbryt|stop|inte)\b", re.IGNORECASE)

# Import extracted helper functions (Sprint 2 refactor)
from app.agents.new_chat.supervisor_helpers import (  # noqa: E402
    _agent_call_entries_since_last_user,
    _best_actionable_entry,
    _build_agent_result_contract,
    _build_rolling_context_summary,
    _build_subagent_handoff_payload,
    _build_subagent_id,
    _coerce_supervisor_tool_calls,
    _contract_from_payload,
    _count_consecutive_loop_tools,
    _count_consecutive_same_direct_tool,
    _current_turn_key,
    _format_tools_for_llm_binding,
    _has_followup_plan_steps,
    _latest_actionable_ai_response,
    _latest_user_query,
    _projected_followup_plan_steps,
    _render_guard_message,
    _resolve_tool_message_name,
    _sanitize_messages,
    _should_finalize_from_contract,
    _summarize_tool_payload,
    _tool_names_from_messages,
    _all_tool_data_empty,
)


async def create_supervisor_agent(
    *,
    llm,
    dependencies: dict[str, Any],
    checkpointer: Checkpointer | None,
    config_schema: type[Any] | None = None,
    knowledge_prompt: str,
    action_prompt: str,
    statistics_prompt: str,
    synthesis_prompt: str | None = None,
    compare_mode: bool = False,
    debate_mode: bool = False,
    voice_debate_mode: bool = False,
    hybrid_mode: bool = False,
    speculative_enabled: bool = False,
    external_model_prompt: str | None = None,
    bolag_prompt: str | None = None,
    trafik_prompt: str | None = None,
    media_prompt: str | None = None,
    browser_prompt: str | None = None,
    code_prompt: str | None = None,
    kartor_prompt: str | None = None,
    riksdagen_prompt: str | None = None,
    riksdagen_dokument_prompt: str | None = None,
    riksdagen_debatt_prompt: str | None = None,
    riksdagen_ledamoter_prompt: str | None = None,
    marketplace_prompt: str | None = None,
    tool_prompt_overrides: dict[str, str] | None = None,
    think_on_tool_calls: bool = True,
):
    prompt_overrides = dict(tool_prompt_overrides or {})
    tool_prompt_overrides = dict(prompt_overrides)

    # Resolve the global core prompt so it can be prepended to every pipeline
    # system prompt (but NOT to enforcement/guard/template messages).
    _raw_core = resolve_prompt(
        prompt_overrides,
        "system.core.global",
        SURFSENSE_CORE_GLOBAL_PROMPT,
    )
    _core = append_datetime_context(_raw_core.strip())
    _use_structured = structured_output_enabled()

    critic_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.critic.system",
            DEFAULT_SUPERVISOR_CRITIC_PROMPT,
        ),
    )
    loop_guard_template = resolve_prompt(
        prompt_overrides,
        "supervisor.loop_guard.message",
        DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
    )
    tool_limit_guard_template = resolve_prompt(
        prompt_overrides,
        "supervisor.tool_limit_guard.message",
        DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
    )
    trafik_enforcement_message = resolve_prompt(
        prompt_overrides,
        "supervisor.trafik.enforcement.message",
        DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE,
    )
    code_sandbox_enforcement_message = resolve_prompt(
        prompt_overrides,
        "supervisor.code.sandbox.enforcement.message",
        DEFAULT_SUPERVISOR_CODE_SANDBOX_ENFORCEMENT_MESSAGE,
    )
    code_read_file_enforcement_message = resolve_prompt(
        prompt_overrides,
        "supervisor.code.read_file.enforcement.message",
        DEFAULT_SUPERVISOR_CODE_READ_FILE_ENFORCEMENT_MESSAGE,
    )
    scoped_tool_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.scoped_tool_prompt.template",
        DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE,
    )
    tool_default_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.tool_default_prompt.template",
        DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
    )
    subagent_context_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.subagent.context.template",
        DEFAULT_SUPERVISOR_SUBAGENT_CONTEXT_TEMPLATE,
    )
    intent_resolver_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.intent_resolver.system",
            DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    decomposer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.decomposer.system",
            DEFAULT_SUPERVISOR_DECOMPOSER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    agent_resolver_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.agent_resolver.system",
            DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.planner.system",
            DEFAULT_SUPERVISOR_PLANNER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    multi_domain_planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.planner.multi_domain.system",
            DEFAULT_SUPERVISOR_MULTI_DOMAIN_PLANNER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    tool_resolver_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.tool_resolver.system",
            DEFAULT_SUPERVISOR_TOOL_RESOLVER_PROMPT,
        ),
    )
    critic_gate_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.critic_gate.system",
            DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
        ),
        structured_output=_use_structured,
    )
    domain_planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.domain_planner.system",
            DEFAULT_SUPERVISOR_DOMAIN_PLANNER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    response_layer_kunskap_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.kunskap",
            DEFAULT_RESPONSE_LAYER_KUNSKAP_PROMPT,
        ),
    )
    response_layer_analys_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.analys",
            DEFAULT_RESPONSE_LAYER_ANALYS_PROMPT,
        ),
    )
    response_layer_syntes_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.syntes",
            DEFAULT_RESPONSE_LAYER_SYNTES_PROMPT,
        ),
    )
    response_layer_visualisering_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.visualisering",
            DEFAULT_RESPONSE_LAYER_VISUALISERING_PROMPT,
        ),
    )
    response_layer_router_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.router",
            DEFAULT_RESPONSE_LAYER_ROUTER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    synthesizer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.synthesizer.system",
            DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    compare_synthesizer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "compare.analysis.system",
            DEFAULT_COMPARE_ANALYSIS_PROMPT,
        ),
    )
    # Compare Supervisor v2: P4-style prompts
    from app.agents.new_chat.compare_prompts import (
        DEFAULT_COMPARE_CONVERGENCE_PROMPT,
        DEFAULT_COMPARE_CRITERION_DJUP_PROMPT,
        DEFAULT_COMPARE_CRITERION_KLARHET_PROMPT,
        DEFAULT_COMPARE_CRITERION_KORREKTHET_PROMPT,
        DEFAULT_COMPARE_CRITERION_RELEVANS_PROMPT,
        DEFAULT_COMPARE_DOMAIN_PLANNER_PROMPT,
        DEFAULT_COMPARE_MINI_CRITIC_PROMPT,
        DEFAULT_COMPARE_MINI_PLANNER_PROMPT,
        DEFAULT_COMPARE_RESEARCH_PROMPT,
    )

    compare_domain_planner_prompt = resolve_prompt(
        prompt_overrides,
        "compare.domain_planner.system",
        DEFAULT_COMPARE_DOMAIN_PLANNER_PROMPT,
    )
    compare_mini_planner_prompt = resolve_prompt(
        prompt_overrides,
        "compare.mini_planner.system",
        DEFAULT_COMPARE_MINI_PLANNER_PROMPT,
    )
    compare_mini_critic_prompt = resolve_prompt(
        prompt_overrides,
        "compare.mini_critic.system",
        DEFAULT_COMPARE_MINI_CRITIC_PROMPT,
    )
    compare_convergence_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "compare.convergence.system",
            DEFAULT_COMPARE_CONVERGENCE_PROMPT,
        ),
    )
    # Per-criterion evaluator prompts (admin-editable)
    _criterion_prompt_overrides: dict[str, str] = {}
    for _crit, _default in [
        ("relevans", DEFAULT_COMPARE_CRITERION_RELEVANS_PROMPT),
        ("djup", DEFAULT_COMPARE_CRITERION_DJUP_PROMPT),
        ("klarhet", DEFAULT_COMPARE_CRITERION_KLARHET_PROMPT),
        ("korrekthet", DEFAULT_COMPARE_CRITERION_KORREKTHET_PROMPT),
    ]:
        _resolved = resolve_prompt(
            prompt_overrides,
            f"compare.criterion.{_crit}",
            _default,
        )
        if _resolved != _default:
            _criterion_prompt_overrides[_crit] = _resolved

    # Research synthesis prompt (admin-editable via compare.research.system)
    _research_synthesis_prompt_resolved = resolve_prompt(
        prompt_overrides,
        "compare.research.system",
        DEFAULT_COMPARE_RESEARCH_PROMPT,
    )
    _research_synthesis_prompt: str | None = (
        _research_synthesis_prompt_resolved
        if _research_synthesis_prompt_resolved != DEFAULT_COMPARE_RESEARCH_PROMPT
        else None
    )

    # ─── Debate mode prompts ─────────────────────────────────────────
    from app.agents.new_chat.debate_prompts import (
        DEFAULT_DEBATE_ANALYSIS_PROMPT,
        DEFAULT_DEBATE_CONVERGENCE_PROMPT,
        DEFAULT_DEBATE_MINI_CRITIC_PROMPT,
    )

    debate_synthesizer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "debate.analysis.system",
            DEFAULT_DEBATE_ANALYSIS_PROMPT,
        ),
    )
    debate_convergence_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "debate.convergence.system",
            DEFAULT_DEBATE_CONVERGENCE_PROMPT,
        ),
    )
    debate_mini_critic_prompt = resolve_prompt(
        prompt_overrides,
        "debate.mini_critic.system",
        DEFAULT_DEBATE_MINI_CRITIC_PROMPT,
    )

    hitl_planner_message_template = resolve_prompt(
        prompt_overrides,
        "supervisor.hitl.planner.message",
        DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE,
    )
    hitl_execution_message_template = resolve_prompt(
        prompt_overrides,
        "supervisor.hitl.execution.message",
        DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE,
    )
    hitl_synthesis_message_template = resolve_prompt(
        prompt_overrides,
        "supervisor.hitl.synthesis.message",
        DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE,
    )
    smalltalk_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "agent.smalltalk.system",
            SMALLTALK_INSTRUCTIONS,
        ),
        include_think_instructions=False,
    )
    # Prompt-key → prompt string lookup.  Falls back to knowledge_prompt
    # for unknown keys so new agents always get a usable prompt.
    _prompt_key_map: dict[str, str] = {
        "knowledge_prompt": knowledge_prompt,
        "action_prompt": action_prompt,
        "weather_prompt": action_prompt,
        "statistics_prompt": statistics_prompt,
        "synthesis_prompt": (
            synthesis_prompt or statistics_prompt or knowledge_prompt
        ),
        "bolag_prompt": bolag_prompt or knowledge_prompt,
        "trafik_prompt": trafik_prompt or action_prompt,
        "trafikanalys_prompt": (
            trafik_prompt or statistics_prompt or action_prompt
        ),
        "media_prompt": media_prompt or action_prompt,
        "browser_prompt": browser_prompt or knowledge_prompt,
        "code_prompt": code_prompt or knowledge_prompt,
        "kartor_prompt": kartor_prompt or action_prompt,
        "riksdagen_prompt": riksdagen_prompt or knowledge_prompt,
        "riksdagen_dokument_prompt": (
            riksdagen_dokument_prompt
            or riksdagen_prompt
            or knowledge_prompt
        ),
        "riksdagen_debatt_prompt": (
            riksdagen_debatt_prompt
            or riksdagen_prompt
            or knowledge_prompt
        ),
        "riksdagen_ledamoter_prompt": (
            riksdagen_ledamoter_prompt
            or riksdagen_prompt
            or knowledge_prompt
        ),
        "marketplace_prompt": marketplace_prompt or action_prompt,
        "elpris_prompt": statistics_prompt or action_prompt,
        "riksbank_prompt": statistics_prompt or knowledge_prompt,
        "skolverket_prompt": statistics_prompt or knowledge_prompt,
    }

    # Minimal static fallback — rebuilt dynamically from GraphRegistry
    # after it loads (see below after ``graph_registry = ...``).
    worker_configs: dict[str, WorkerConfig] = {
        "kunskap": WorkerConfig(
            name="kunskap-worker",
            primary_namespaces=[("tools", "knowledge")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "statistics"),
                ("tools", "general"),
            ],
        ),
    }
    worker_prompts: dict[str, str] = {"kunskap": knowledge_prompt}

    # NOTE: worker pool creation is deferred until after dynamic configs
    # are built from GraphRegistry (see below after registry install).

    agent_definitions = [
        AgentDefinition(
            name="åtgärd",
            description="Realtime-åtgärder som väder, resor och verktygskörningar",
            keywords=[
                "vader",
                "vadret",
                "väder",
                "vädret",
                "smhi",
                "resa",
                "tåg",
                "tag",
                "avgår",
                "tidtabell",
                "trafik",
                "rutt",
                "karta",
                "kartbild",
                "geoapify",
                "adress",
            ],
            namespace=("agents", "action"),
            prompt_key="action",
        ),
        AgentDefinition(
            name="väder",
            description="SMHI-väderprognoser och Trafikverkets vägväderdata för svenska orter och vägar",
            keywords=[
                "smhi",
                "vader",
                "väder",
                "vädret",
                "vadret",
                "temperatur",
                "regn",
                "snö",
                "sno",
                "vind",
                "prognos",
                "halka",
                "isrisk",
                "vaglag",
                "väglag",
                "trafikverket väder",
            ],
            namespace=("agents", "weather"),
            prompt_key="action",
        ),
        AgentDefinition(
            name="kartor",
            description="Skapa statiska kartbilder och markörer",
            keywords=[
                "karta",
                "kartor",
                "kartbild",
                "map",
                "geoapify",
                "adress",
                "plats",
                "koordinat",
                "vägarbete",
                "vag",
                "väg",
                "rutt",
            ],
            namespace=("agents", "kartor"),
            prompt_key="kartor",
        ),
        AgentDefinition(
            name="riksbank-ekonomi",
            description="Riksbankens räntor, valutakurser och makroprognoser — styrränta, STIBOR, SWESTR, SEK-kurser, inflationsprognos, BNP-prognos",
            keywords=[
                "riksbanken",
                "styrränta",
                "reporänta",
                "ränta",
                "valutakurs",
                "växelkurs",
                "sek",
                "swestr",
                "stibor",
                "dagslåneränta",
                "valuta",
                "inflationsprognos",
                "bnp-prognos",
            ],
            namespace=("agents", "riksbank", "ekonomi"),
            prompt_key="riksbank",
        ),
        AgentDefinition(
            name="elpris",
            description="Aktuella och historiska elpriser (spotpriser) per elområde i Sverige — SE1, SE2, SE3, SE4",
            keywords=[
                "elpris",
                "elpriser",
                "spotpris",
                "kwh",
                "elzon",
                "elområde",
                "se1",
                "se2",
                "se3",
                "se4",
                "elavtal",
                "timpris",
            ],
            namespace=("agents", "elpris", "energi"),
            prompt_key="elpris",
        ),
        AgentDefinition(
            name="statistik-ekonomi",
            description="Ekonomisk statistik — BNP, KPI, inflation, handel, finans",
            keywords=[
                "ekonomi",
                "bnp",
                "kpi",
                "inflation",
                "handel",
                "nationalräkenskaper",
                "priser",
                "skattesats",
                "offentlig ekonomi",
                "finansmarknad",
            ],
            namespace=("agents", "statistics", "ekonomi"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="statistik-befolkning",
            description="Befolkningsstatistik — folkmängd, demografi, migration",
            keywords=[
                "befolkning",
                "folkmängd",
                "invånare",
                "kommun",
                "demografi",
                "födda",
                "dödsfall",
                "invandring",
            ],
            namespace=("agents", "statistics", "befolkning"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="statistik-arbetsmarknad",
            description="Arbetsmarknadsstatistik — arbetslöshet, sysselsättning, löner",
            keywords=[
                "arbetsmarknad",
                "arbetslöshet",
                "sysselsättning",
                "lön",
                "löner",
                "lönestatistik",
                "lönestruktur",
            ],
            namespace=("agents", "statistics", "arbetsmarknad"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="statistik-utbildning",
            description="Utbildningsstatistik — skola, gymnasium, högskola, forskning",
            keywords=[
                "utbildning",
                "skola",
                "förskola",
                "grundskola",
                "gymnasium",
                "högskola",
                "forskning",
                "betyg",
                "behörighet",
                "pedagogtäthet",
            ],
            namespace=("agents", "statistics", "utbildning"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="statistik-halsa",
            description="Hälso- och omsorgsstatistik — sjukvård, äldreomsorg, LSS, IFO",
            keywords=[
                "hälsa",
                "sjukvård",
                "äldreomsorg",
                "hemtjänst",
                "lss",
                "ifo",
                "socialtjänst",
                "omsorg",
                "barn och unga",
                "kolada",
                "nyckeltal",
            ],
            namespace=("agents", "statistics", "halsa"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="statistik-miljo",
            description="Miljö- och energistatistik — utsläpp, energi, klimat",
            keywords=[
                "miljö",
                "energi",
                "utsläpp",
                "klimat",
                "avfall",
                "återvinning",
                "energianvändning",
            ],
            namespace=("agents", "statistics", "miljo"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="statistik-fastighet",
            description="Bostads- och fastighetsstatistik — bygglov, nybyggnation, bestånd",
            keywords=[
                "bostad",
                "bostäder",
                "bygglov",
                "nybyggnation",
                "bostadsbestånd",
                "hyra",
                "fastighet",
                "byggande",
            ],
            namespace=("agents", "statistics", "fastighet"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="statistik-naringsliv",
            description="Näringslivsstatistik — företag, omsättning, nyföretagande",
            keywords=[
                "näringsliv",
                "företag",
                "omsättning",
                "nyföretagande",
                "bransch",
                "näringsverksamhet",
            ],
            namespace=("agents", "statistics", "naringsliv"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="statistik-samhalle",
            description="Samhällsstatistik — transport, kultur, jordbruk",
            keywords=[
                "transport",
                "transporter",
                "kultur",
                "fritid",
                "jordbruk",
                "statistik",
                "nyckeltal",
                "scb",
                "samhälle",
            ],
            namespace=("agents", "statistics", "samhalle"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="skolverket-kursplaner",
            description="Skolverket kursplaner, ämnesplaner, program och läroplaner",
            keywords=[
                "ämne",
                "ämnesplan",
                "kursplan",
                "kurs",
                "program",
                "läroplan",
                "syllabus",
                "kunskapskrav",
                "centralt innehåll",
                "examensmål",
                "skolverket",
                "curriculum",
                "gymnasieprogram",
            ],
            namespace=("agents", "skolverket", "kursplaner"),
            prompt_key="skolverket",
        ),
        AgentDefinition(
            name="skolverket-skolenheter",
            description="Skolverket skolenheter — sökning, detaljer, dokument och status",
            keywords=[
                "skola",
                "skolenhet",
                "grundskola",
                "gymnasium",
                "friskola",
                "skolenhetsregister",
                "huvudman",
                "rektor",
                "skolverket",
            ],
            namespace=("agents", "skolverket", "skolenheter"),
            prompt_key="skolverket",
        ),
        AgentDefinition(
            name="skolverket-vuxenutbildning",
            description="Skolverket vuxenutbildning, komvux, YH, SFI, utbildningstillfällen",
            keywords=[
                "vuxenutbildning",
                "komvux",
                "yrkeshögskola",
                "yh",
                "sfi",
                "distansutbildning",
                "studietakt",
                "utbildningstillfälle",
                "skolverket",
            ],
            namespace=("agents", "skolverket", "vuxenutbildning"),
            prompt_key="skolverket",
        ),
        AgentDefinition(
            name="skolverket-referens",
            description="Skolverket referensdata, koder, skoltyper och utbildningsstatistik",
            keywords=[
                "skoltyp",
                "skolform",
                "ämneskod",
                "kurskod",
                "studieväg",
                "utbildningsstatistik",
                "programstatistik",
                "skolverket",
            ],
            namespace=("agents", "skolverket", "referens"),
            prompt_key="skolverket",
        ),
        AgentDefinition(
            name="media",
            description="Podcast, bild och media-generering",
            keywords=["podcast", "podd", "media", "bild", "ljud"],
            namespace=("agents", "media"),
            prompt_key="media",
        ),
        AgentDefinition(
            name="kunskap",
            description="SurfSense, Tavily och generell kunskap",
            keywords=[
                "kunskap",
                "surfsense",
                "tavily",
                "docs",
                "note",
                "skolverket",
                "laroplan",
                "läroplan",
                "kursplan",
                "ämnesplan",
                "amnesplan",
                "skolenhet",
                "komvux",
                "vuxenutbildning",
            ],
            namespace=("agents", "knowledge"),
            prompt_key="knowledge",
        ),
        AgentDefinition(
            name="webb",
            description="Webbsökning och scraping",
            keywords=["webb", "browser", "sok", "nyheter", "url"],
            namespace=("agents", "browser"),
            prompt_key="browser",
        ),
        AgentDefinition(
            name="kod",
            description="Kalkyler och kodrelaterade uppgifter",
            keywords=[
                "kod",
                "berakna",
                "script",
                "python",
                "fil",
                "filer",
                "file",
                "filesystem",
                "filsystem",
                "skriv fil",
                "läs fil",
                "las fil",
                "create file",
                "read file",
                "write file",
                "sandbox",
                "docker",
                "bash",
                "terminal",
            ],
            namespace=("agents", "code"),
            prompt_key="code",
        ),
        AgentDefinition(
            name="bolag",
            description="Bolagsverket och företagsdata (orgnr, ägare, ekonomi)",
            keywords=[
                "bolag",
                "bolagsverket",
                "foretag",
                "företag",
                "orgnr",
                "organisationsnummer",
                "styrelse",
                "firmatecknare",
                "arsredovisning",
                "årsredovisning",
                "f-skatt",
                "moms",
                "konkurs",
            ],
            namespace=("agents", "bolag"),
            prompt_key="bolag",
        ),
        AgentDefinition(
            name="trafik-tag",
            description="Tågtrafik – förseningar, tidtabeller, stationer, resplanering",
            keywords=[
                "tåg",
                "tag",
                "järnväg",
                "jarnvag",
                "tidtabell",
                "avgång",
                "ankomst",
                "station",
                "resplanering",
                "kollektivtrafik",
                "sj",
            ],
            namespace=("agents", "trafik", "tag"),
            prompt_key="trafik",
            routes=("trafik-och-transport",),
            main_identifier="TågtrafikAgent",
            core_activity="Hämtar realtidsinformation om tågtrafik och tidtabeller",
            unique_scope="Tågtrafik — förseningar, tidtabeller, stationer, resplanering",
            geographic_scope="Sverige",
            excludes=("väder", "statistik", "fordon"),
        ),
        AgentDefinition(
            name="trafik-vag",
            description="Vägtrafik – störningar, olyckor, köer, kameror, vägstatus",
            keywords=[
                "trafikverket",
                "trafik",
                "väg",
                "vag",
                "störning",
                "olycka",
                "kö",
                "ko",
                "kamera",
                "vägarbete",
                "hastighet",
            ],
            namespace=("agents", "trafik", "vag"),
            prompt_key="trafik",
            routes=("trafik-och-transport",),
            main_identifier="VägtrafikAgent",
            core_activity="Hämtar realtidsinformation om vägtrafik och störningar",
            unique_scope="Vägtrafik — störningar, olyckor, köer, kameror, vägarbeten",
            geographic_scope="Sverige",
            excludes=("väder", "statistik", "fordon", "tåg"),
        ),
        AgentDefinition(
            name="trafik-vagvader",
            description="Vägväder – halka, isrisk, vind, temperatur vid vägnätet",
            keywords=[
                "vägväder",
                "väglag",
                "halka",
                "isrisk",
                "vind",
                "temperatur",
                "väderstation",
                "bro",
            ],
            namespace=("agents", "trafik", "vagvader"),
            prompt_key="trafik",
            routes=("trafik-och-transport",),
            main_identifier="VägväderAgent",
            core_activity="Hämtar vägväderdata från Trafikverkets väderstationer",
            unique_scope="Vägväder — halka, isrisk, temperatur vid vägnätet",
            geographic_scope="Sverige",
            excludes=("statistik", "fordon", "tåg"),
        ),
        AgentDefinition(
            name="trafikanalys-transport",
            description="Svensk transportstatistik från Trafikanalys (trafa.se) — fordonsbestånd, nyregistreringar, avregistreringar, trafikarbete, vägtrafikskador, sjötrafik, luftfart, järnväg, kollektivtrafik och körkort. Statistik och siffror, inte realtidstrafik.",
            keywords=[
                "trafikanalys",
                "transportstatistik",
                "statistik",
                "fordon",
                "fordonsstatistik",
                "kollektivtrafik",
                "personbilar",
                "lastbilar",
                "bussar",
                "motorcyklar",
                "nyregistrering",
                "avregistrering",
                "trafikarbete",
                "fordonskilometer",
                "trafikskador",
                "trafikdöda",
                "trafikolyckor",
                "sjötrafik",
                "luftfart",
                "flyg",
                "järnväg",
                "tåg",
                "körkort",
                "drivmedel",
                "elbil",
                "bilbestånd",
                "fordonsbestånd",
                "trafa",
                "hur många bilar",
                "hur många fordon",
                "antal bilar",
                "antal fordon",
            ],
            namespace=("agents", "trafikanalys", "transport"),
            prompt_key="trafikanalys",
            routes=("trafik-och-transport",),
            main_identifier="TrafikanalysAgent",
            core_activity="Hämtar transportstatistik från Trafikanalys (trafa.se)",
            unique_scope="Svensk transportstatistik — fordon, trafik, olyckor, sjö, luft, järnväg, körkort",
            geographic_scope="Sverige",
            excludes=("väder", "realtid", "störning", "vägarbete"),
        ),
        AgentDefinition(
            name="riksdagen-dokument",
            description="Riksdagens dokument: propositioner, motioner, betänkanden, SOU, Ds, interpellationer, frågor",
            keywords=[
                "riksdag",
                "riksdagen",
                "proposition",
                "prop",
                "motion",
                "mot",
                "betänkande",
                "bet",
                "interpellation",
                "fråga",
                "sou",
                "ds",
                "direktiv",
                "utskott",
                "lagförslag",
                "riksdagsskrivelse",
            ],
            namespace=("agents", "riksdagen", "dokument"),
            prompt_key="riksdagen-dokument",
        ),
        AgentDefinition(
            name="riksdagen-debatt",
            description="Riksdagsdebatter, anföranden och voteringar: vad partierna säger och hur de röstar",
            keywords=[
                "debatt",
                "anförande",
                "tal",
                "votering",
                "omröstning",
                "röstning",
                "frågestund",
                "kammare",
                "röstresultat",
                "budgetdebatt",
            ],
            namespace=("agents", "riksdagen", "debatt"),
            prompt_key="riksdagen-debatt",
        ),
        AgentDefinition(
            name="riksdagen-ledamoter",
            description="Riksdagsledamöter per parti/valkrets och Riksdagens kalender med debatter och utskottsmöten",
            keywords=[
                "ledamot",
                "ledamöter",
                "riksdagsledamot",
                "parti",
                "valkrets",
                "kalender",
                "schema",
                "möte",
                "sammanträde",
                "agenda",
            ],
            namespace=("agents", "riksdagen", "ledamoter"),
            prompt_key="riksdagen-ledamoter",
        ),
        AgentDefinition(
            name="marknad",
            description="Sök och jämför annonser på Blocket och Tradera för begagnade varor, bilar, båtar, motorcyklar",
            keywords=[
                "blocket",
                "tradera",
                "köp",
                "köpa",
                "sälj",
                "sälja",
                "begagnat",
                "begagnad",
                "begagnade",
                "annons",
                "annonser",
                "marknadsplats",
                "marknadsplatser",
                "auktion",
                "auktioner",
                "bilar",
                "bil",
                "båtar",
                "båt",
                "mc",
                "motorcykel",
                "motorcyklar",
                "pris",
                "priser",
                "prisjämförelse",
                "jämför",
                "kategorier",
                "kategori",
                "regioner",
                "sök",
                "hitta",
                "finns",
            ],
            namespace=("agents", "marketplace"),
            prompt_key="agent.marketplace.system",
        ),
        AgentDefinition(
            name="syntes",
            description="Syntes och jämförelser av flera källor och modeller",
            keywords=["synthesis", "syntes", "jämför", "compare", "sammanfatta"],
            namespace=("agents", "synthesis"),
            prompt_key="synthesis",
        ),
    ]

    # ── GraphRegistry (Sprint 5: domain-scoped agent/tool resolution) ──
    graph_registry = dependencies.get("graph_registry")
    # Default to static set; overridden by registry-built set below
    specialized_agents: set[str] = _SPECIALIZED_AGENTS

    # ── Dynamic worker pool from GraphRegistry ─────────────────────────
    # Build one WorkerConfig per agent from the DB-backed registry.
    # Any agent added via the admin panel is immediately available.
    if graph_registry is not None and graph_registry.agent_index:
        _dyn_configs: dict[str, WorkerConfig] = {}
        _dyn_prompts: dict[str, str] = {}
        for _aid, _adata in graph_registry.agent_index.items():
            if not _adata.get("enabled", True):
                continue
            _raw_pri = _adata.get("primary_namespaces") or []
            _raw_fb = _adata.get("fallback_namespaces") or []
            _pri_ns = [
                tuple(ns) for ns in _raw_pri
                if isinstance(ns, (list, tuple)) and ns
            ]
            _fb_ns = [
                tuple(ns) for ns in _raw_fb
                if isinstance(ns, (list, tuple)) and ns
            ]
            if not _pri_ns and not _fb_ns:
                _fb_ns = [("tools", "knowledge"), ("tools", "general")]
            _wc = _adata.get("worker_config") or {}
            _dyn_configs[_aid] = WorkerConfig(
                name=f"{_aid}-worker",
                primary_namespaces=_pri_ns,
                fallback_namespaces=_fb_ns,
                tool_limit=int(_wc.get("tool_limit", 3)),
            )
            _pk = str(
                _adata.get("prompt_key") or "knowledge_prompt"
            ).strip()
            _dyn_prompts[_aid] = _prompt_key_map.get(
                _pk, knowledge_prompt
            )
        if _dyn_configs:
            worker_configs = _dyn_configs
            worker_prompts = _dyn_prompts

    # ── Install registry-aware dynamic structures ────────────────────
    # Rebuild hardcoded constants from the live registry so that agents/tools
    # added via admin panel are immediately available without code changes.
    if graph_registry is not None and graph_registry.agent_index:
        from app.agents.new_chat.supervisor_constants import (
            build_alias_map_from_registry,
            build_route_defaults_from_registry,
            build_specialized_agents_from_registry,
            build_token_rules_from_registry,
            build_tool_profiles_from_registry,
        )
        from app.agents.new_chat.supervisor_routing import (
            set_registry_alias_map,
            set_registry_route_defaults,
            set_registry_token_rules,
            set_registry_tool_profiles,
        )

        _dyn_specialized = build_specialized_agents_from_registry(graph_registry)
        _dyn_alias_map = build_alias_map_from_registry(graph_registry)
        _dyn_route_defaults = build_route_defaults_from_registry(graph_registry)
        _dyn_token_rules = build_token_rules_from_registry(graph_registry)
        _dyn_tool_profiles = build_tool_profiles_from_registry(graph_registry)

        # Override module-level specialized agents set for this graph instance
        specialized_agents = _dyn_specialized

        # Install into routing module globals
        set_registry_alias_map(_dyn_alias_map)
        set_registry_route_defaults(_dyn_route_defaults)
        set_registry_token_rules(_dyn_token_rules)
        if _dyn_tool_profiles:
            set_registry_tool_profiles(_dyn_tool_profiles)

    db_session = dependencies.get("db_session")
    if isinstance(db_session, AsyncSession):
        try:
            effective_agent_metadata = await get_effective_agent_metadata(db_session)
        except Exception:
            effective_agent_metadata = []
            logger.exception("Failed to load effective agent metadata overrides")
        if effective_agent_metadata:
            metadata_by_agent_id: dict[str, dict[str, Any]] = {}
            for payload in effective_agent_metadata:
                agent_id = str(payload.get("agent_id") or "").strip().lower()
                if agent_id:
                    metadata_by_agent_id[agent_id] = payload
            if metadata_by_agent_id:
                merged_agent_definitions: list[AgentDefinition] = []
                for definition in agent_definitions:
                    metadata = metadata_by_agent_id.get(definition.name)
                    if not metadata:
                        merged_agent_definitions.append(definition)
                        continue
                    _routes_raw = metadata.get("routes") or []
                    _routes = tuple(
                        str(r).strip()
                        for r in _routes_raw
                        if str(r).strip()
                    ) if isinstance(_routes_raw, list) else ()
                    _excludes_raw = metadata.get("excludes") or []
                    _excludes = tuple(
                        str(e).strip()
                        for e in _excludes_raw
                        if str(e).strip()
                    ) if isinstance(_excludes_raw, list) else ()
                    merged_agent_definitions.append(
                        AgentDefinition(
                            name=definition.name,
                            description=str(
                                metadata.get("description") or definition.description
                            ),
                            keywords=[
                                str(keyword)
                                for keyword in (
                                    metadata.get("keywords") or definition.keywords
                                )
                                if str(keyword).strip()
                            ],
                            namespace=definition.namespace,
                            prompt_key=definition.prompt_key,
                            routes=_routes or definition.routes,
                            main_identifier=str(
                                metadata.get("main_identifier") or definition.main_identifier
                            ),
                            core_activity=str(
                                metadata.get("core_activity") or definition.core_activity
                            ),
                            unique_scope=str(
                                metadata.get("unique_scope") or definition.unique_scope
                            ),
                            geographic_scope=str(
                                metadata.get("geographic_scope") or definition.geographic_scope
                            ),
                            excludes=_excludes or definition.excludes,
                        )
                    )
                agent_definitions = merged_agent_definitions
    agent_by_name = {definition.name: definition for definition in agent_definitions}

    # Create/get process-level shared worker pool AFTER dynamic configs are
    # built from GraphRegistry.  This ensures all DB-defined agents have a
    # WorkerConfig entry so LazyWorkerPool.get(agent_name) never returns None.
    # llm_gate_mode is set later (after live_routing_config is built), but
    # LazyWorkerPool initializes workers lazily, so we can patch it after.
    worker_pool = await get_or_create_shared_worker_pool(
        configs=worker_configs,
        llm=llm,
        dependencies=dependencies,
        checkpointer=checkpointer,
    )

    connector_service = dependencies.get("connector_service")
    search_space_id = dependencies.get("search_space_id")
    user_id = dependencies.get("user_id")
    thread_id = dependencies.get("thread_id")
    episodic_store = get_or_create_episodic_store(
        search_space_id=search_space_id,
        user_id=user_id,
        max_entries=500,
    )
    retrieval_feedback_store = get_global_retrieval_feedback_store()
    runtime_hitl_raw = dependencies.get("runtime_hitl")
    runtime_hitl_cfg = (
        dict(runtime_hitl_raw)
        if isinstance(runtime_hitl_raw, dict)
        else {"enabled": bool(runtime_hitl_raw)}
    )
    compare_external_prompt = external_model_prompt or DEFAULT_EXTERNAL_SYSTEM_PROMPT

    def _coerce_bool(value: Any, *, default: bool = False) -> bool:
        if value is None:
            return bool(default)
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
        return bool(default)

    persisted_tuning = normalize_tool_retrieval_tuning(None)
    retrieval_feedback_db_enabled = False
    if isinstance(db_session, AsyncSession):
        try:
            persisted_tuning = await get_global_tool_retrieval_tuning(db_session)
            retrieval_feedback_db_enabled = bool(
                persisted_tuning.get("retrieval_feedback_db_enabled")
            )
        except Exception:
            retrieval_feedback_db_enabled = False
            persisted_tuning = normalize_tool_retrieval_tuning(None)

    if isinstance(runtime_hitl_cfg, dict) and (
        "retrieval_feedback_db_enabled" in runtime_hitl_cfg
    ):
        retrieval_feedback_db_enabled = _coerce_bool(
            runtime_hitl_cfg.get("retrieval_feedback_db_enabled"),
            default=retrieval_feedback_db_enabled,
        )

    if retrieval_feedback_db_enabled and isinstance(db_session, AsyncSession):
        try:
            persisted_rows = await load_retrieval_feedback_snapshot(
                db_session,
                limit=5000,
            )
            hydrate_global_retrieval_feedback_store(persisted_rows)
        except Exception:
            # Retrieval ranking should continue even when persistence is unavailable.
            retrieval_feedback_db_enabled = False

    live_phase = _normalize_live_routing_phase(
        persisted_tuning.get("live_routing_phase")
    )
    live_routing_enabled = bool(persisted_tuning.get("live_routing_enabled"))
    if (
        isinstance(runtime_hitl_cfg, dict)
        and "live_routing_enabled" in runtime_hitl_cfg
    ):
        live_routing_enabled = _coerce_bool(
            runtime_hitl_cfg.get("live_routing_enabled"),
            default=live_routing_enabled,
        )
    if isinstance(runtime_hitl_cfg, dict) and "live_routing_phase" in runtime_hitl_cfg:
        live_phase = _normalize_live_routing_phase(
            runtime_hitl_cfg.get("live_routing_phase")
        )
    live_routing_config: dict[str, Any] = {
        "enabled": bool(live_routing_enabled),
        "phase": live_phase,
        "phase_index": int(_LIVE_ROUTING_PHASE_ORDER.get(live_phase, 0)),
        "intent_top_k": int(persisted_tuning.get("intent_candidate_top_k") or 3),
        "agent_top_k": int(persisted_tuning.get("agent_candidate_top_k") or 3),
        "tool_top_k": int(persisted_tuning.get("tool_candidate_top_k") or 5),
        "intent_lexical_weight": float(
            persisted_tuning.get("intent_lexical_weight") or 1.0
        ),
        "intent_embedding_weight": float(
            persisted_tuning.get("intent_embedding_weight") or 1.0
        ),
        "agent_auto_margin_threshold": float(
            persisted_tuning.get("agent_auto_margin_threshold") or 0.18
        ),
        "agent_auto_score_threshold": float(
            persisted_tuning.get("agent_auto_score_threshold") or 0.55
        ),
        "tool_auto_margin_threshold": float(
            persisted_tuning.get("tool_auto_margin_threshold") or 0.25
        ),
        "tool_auto_score_threshold": float(
            persisted_tuning.get("tool_auto_score_threshold") or 0.60
        ),
        "adaptive_threshold_delta": float(
            persisted_tuning.get("adaptive_threshold_delta") or 0.08
        ),
        "adaptive_min_samples": int(persisted_tuning.get("adaptive_min_samples") or 8),
        "llm_gate_mode": bool(persisted_tuning.get("llm_gate_mode", False)),
    }

    # Propagate llm_gate_mode to the worker pool so workers skip vector
    # retrieval and only use pre-resolved tools from the LLM gate pipeline.
    worker_pool._llm_gate_mode = bool(live_routing_config.get("llm_gate_mode", False))

    subagent_enabled = _coerce_bool(
        runtime_hitl_cfg.get("subagent_enabled"),
        default=True,
    )
    subagent_isolation_enabled = subagent_enabled and _coerce_bool(
        runtime_hitl_cfg.get("subagent_isolation_enabled"),
        default=False,
    )
    subagent_context_max_chars = _coerce_int_range(
        runtime_hitl_cfg.get("subagent_context_max_chars"),
        default=_SUBAGENT_DEFAULT_CONTEXT_MAX_CHARS,
        min_value=240,
        max_value=8_000,
    )
    subagent_result_max_chars = _coerce_int_range(
        runtime_hitl_cfg.get("subagent_result_max_chars"),
        default=_SUBAGENT_DEFAULT_RESULT_MAX_CHARS,
        min_value=180,
        max_value=4_000,
    )
    subagent_max_concurrency = _coerce_int_range(
        runtime_hitl_cfg.get("subagent_max_concurrency"),
        default=_SUBAGENT_DEFAULT_MAX_CONCURRENCY,
        min_value=1,
        max_value=8,
    )
    sandbox_enabled = _coerce_bool(
        runtime_hitl_cfg.get("sandbox_enabled"),
        default=False,
    )
    compare_sandbox_isolation = _coerce_bool(
        runtime_hitl_cfg.get("compare_sandbox_isolation"),
        default=False,
    )
    artifact_offload_enabled = _coerce_bool(
        runtime_hitl_cfg.get("artifact_offload_enabled"),
        default=False,
    )
    artifact_offload_threshold_chars = _coerce_int_range(
        runtime_hitl_cfg.get("artifact_offload_threshold_chars"),
        default=_ARTIFACT_DEFAULT_OFFLOAD_THRESHOLD_CHARS,
        min_value=800,
        max_value=200_000,
    )
    artifact_offload_max_entries = _coerce_int_range(
        runtime_hitl_cfg.get("artifact_offload_max_entries"),
        default=_ARTIFACT_DEFAULT_MAX_ENTRIES,
        min_value=8,
        max_value=120,
    )
    artifact_offload_storage_mode = (
        str(
            runtime_hitl_cfg.get("artifact_offload_storage_mode")
            or _ARTIFACT_DEFAULT_STORAGE_MODE
        )
        .strip()
        .lower()
    )
    if artifact_offload_storage_mode not in {"auto", "sandbox", "local"}:
        artifact_offload_storage_mode = _ARTIFACT_DEFAULT_STORAGE_MODE
    context_compaction_enabled = _coerce_bool(
        runtime_hitl_cfg.get("context_compaction_enabled"),
        default=True,
    )
    context_compaction_trigger_ratio = _coerce_float_range(
        runtime_hitl_cfg.get("context_compaction_trigger_ratio"),
        default=_CONTEXT_COMPACTION_DEFAULT_TRIGGER_RATIO,
        min_value=0.35,
        max_value=0.95,
    )
    context_compaction_summary_max_chars = _coerce_int_range(
        runtime_hitl_cfg.get("context_compaction_summary_max_chars"),
        default=_CONTEXT_COMPACTION_DEFAULT_SUMMARY_MAX_CHARS,
        min_value=320,
        max_value=8_000,
    )
    cross_session_memory_enabled = _coerce_bool(
        runtime_hitl_cfg.get("cross_session_memory_enabled"),
        default=True,
    )
    cross_session_memory_max_items = _coerce_int_range(
        runtime_hitl_cfg.get("cross_session_memory_max_items"),
        default=6,
        min_value=1,
        max_value=16,
    )
    cross_session_memory_max_chars = _coerce_int_range(
        runtime_hitl_cfg.get("cross_session_memory_max_chars"),
        default=1_000,
        min_value=220,
        max_value=4_000,
    )
    cross_session_memory_entries: list[dict[str, Any]] = []
    if (
        cross_session_memory_enabled
        and isinstance(db_session, AsyncSession)
        and user_id
    ):
        try:
            user_uuid = UUID(str(user_id))
            stmt = (
                select(UserMemory)
                .where(UserMemory.user_id == user_uuid)
                .order_by(UserMemory.updated_at.desc())
                .limit(max(4, int(cross_session_memory_max_items) * 3))
            )
            if search_space_id is not None:
                stmt = stmt.where(
                    (UserMemory.search_space_id == search_space_id)
                    | (UserMemory.search_space_id.is_(None))
                )
            rows = (await db_session.execute(stmt)).scalars().all()
            for row in rows:
                raw_category = getattr(row, "category", None)
                category = (
                    str(raw_category.value)
                    if hasattr(raw_category, "value")
                    else str(raw_category or "fact")
                )
                memory_text = str(getattr(row, "memory_text", "") or "").strip()
                if not memory_text:
                    continue
                cross_session_memory_entries.append(
                    {
                        "id": str(getattr(row, "id", "") or ""),
                        "category": category.lower(),
                        "memory_text": memory_text,
                        "updated_at": str(getattr(row, "updated_at", "") or ""),
                    }
                )
        except Exception:
            cross_session_memory_entries = []
    context_token_budget: TokenBudget | None = None
    context_budget_available_tokens = 0
    model_name_for_compaction = (
        getattr(llm, "model_name", None) or getattr(llm, "model", None) or ""
    )
    if model_name_for_compaction:
        try:
            context_token_budget = TokenBudget(
                model_name=str(model_name_for_compaction)
            )
            context_budget_available_tokens = max(
                1, int(context_token_budget.available_for_messages)
            )
        except Exception:
            context_token_budget = None
            context_budget_available_tokens = 0

    async def _record_retrieval_feedback(
        tool_id: str, query: str, success: bool
    ) -> None:
        normalized_tool_id = str(tool_id or "").strip()
        normalized_query = str(query or "").strip()
        retrieval_feedback_store.record(
            tool_id=normalized_tool_id,
            query=normalized_query,
            success=bool(success),
        )
        if not retrieval_feedback_db_enabled:
            return
        await persist_retrieval_feedback_signal(
            tool_id=normalized_tool_id,
            query=normalized_query,
            success=bool(success),
        )

    # ── Build per-agent tool ID lists from GraphRegistry (DB-backed) ──
    # Falls back to hardcoded lists if registry is unavailable.

    def _registry_tool_ids(agent_id: str) -> list[str]:
        """Return tool IDs for an agent from the graph registry."""
        if graph_registry is not None and graph_registry.tools_by_agent:
            tools = graph_registry.tools_by_agent.get(agent_id, [])
            return [str(t.get("tool_id", "")).strip() for t in tools if t.get("tool_id")]
        return []

    # Try registry first, fall back to hardcoded definitions
    weather_tool_ids = _registry_tool_ids("väder")
    if not weather_tool_ids:
        _HYDRO_PREFIXES = ("smhi_hydrologi_", "smhi_oceanografi_")
        _RISK_PREFIXES = ("smhi_brandrisk_", "smhi_solstralning_")
        weather_tool_ids = [
            d.tool_id for d in SMHI_TOOL_DEFINITIONS
            if not any(d.tool_id.startswith(p) for p in _HYDRO_PREFIXES + _RISK_PREFIXES)
        ]
        weather_tool_ids.extend(
            d.tool_id for d in TRAFIKVERKET_TOOL_DEFINITIONS
            if _is_weather_tool_id(d.tool_id)
        )
        weather_tool_ids = list(dict.fromkeys(weather_tool_ids))

    smhi_hydro_ids = _registry_tool_ids("väder-vatten")
    if not smhi_hydro_ids:
        smhi_hydro_ids = [
            d.tool_id for d in SMHI_TOOL_DEFINITIONS
            if d.tool_id.startswith(("smhi_hydrologi_", "smhi_oceanografi_"))
        ]

    smhi_risk_ids = _registry_tool_ids("väder-risk")
    if not smhi_risk_ids:
        smhi_risk_ids = [
            d.tool_id for d in SMHI_TOOL_DEFINITIONS
            if d.tool_id.startswith(("smhi_brandrisk_", "smhi_solstralning_"))
        ]

    weather_tool_id_set = set(weather_tool_ids)
    trafik_tool_ids = _registry_tool_ids("trafik-tag") + _registry_tool_ids("trafik-vag") + _registry_tool_ids("trafik-vagvader")
    if not trafik_tool_ids:
        trafik_tool_ids = [
            definition.tool_id
            for definition in TRAFIKVERKET_TOOL_DEFINITIONS
            if definition.tool_id not in weather_tool_id_set
        ]
    trafik_tool_ids = list(dict.fromkeys(trafik_tool_ids))
    live_tool_index = []
    _tool_registry_for_fan_out: dict[str, Any] = {}
    if isinstance(db_session, AsyncSession):
        try:
            global_tool_registry = await build_global_tool_registry(
                dependencies=dependencies,
                include_mcp_tools=True,
            )
            _tool_registry_for_fan_out = global_tool_registry
            metadata_overrides = await get_global_tool_metadata_overrides(db_session)
            live_tool_index = build_tool_index(
                global_tool_registry,
                metadata_overrides=metadata_overrides,
            )
        except Exception:
            live_tool_index = []

    def _adaptive_tool_margin_threshold(tool_id: str, base_threshold: float) -> float:
        if not _live_phase_enabled(live_routing_config, "adaptive"):
            return base_threshold
        rows = list(retrieval_feedback_store.snapshot().get("rows") or [])
        normalized_tool_id = str(tool_id or "").strip().lower()
        successes = 0
        failures = 0
        for row in rows:
            if str(row.get("tool_id") or "").strip().lower() != normalized_tool_id:
                continue
            try:
                successes += max(0, int(row.get("successes") or 0))
                failures += max(0, int(row.get("failures") or 0))
            except Exception:
                continue
        total = successes + failures
        min_samples = max(1, int(live_routing_config.get("adaptive_min_samples") or 8))
        if total < min_samples:
            return base_threshold
        quality = (successes - failures) / total
        delta = max(
            0.0,
            min(
                1.0, float(live_routing_config.get("adaptive_threshold_delta") or 0.08)
            ),
        )
        if quality <= 0.0:
            return min(5.0, base_threshold + delta)
        if quality >= 0.5:
            return max(0.0, base_threshold - delta)
        return base_threshold

    def _resolve_live_tool_selection_for_agent(
        agent_name: str,
        task: str,
        *,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback_ids = _focused_tool_ids_for_agent(agent_name, task, limit=6)
        if not _live_phase_enabled(live_routing_config, "shadow"):
            return {
                "selected_tool_ids": fallback_ids,
                "mode": "profile",
                "auto_selected": False,
            }
        if not live_tool_index:
            return {
                "selected_tool_ids": fallback_ids,
                "mode": "profile",
                "auto_selected": False,
            }
        worker_cfg = worker_configs.get(str(agent_name or "").strip().lower())
        if worker_cfg is None:
            return {
                "selected_tool_ids": fallback_ids,
                "mode": "profile",
                "auto_selected": False,
            }
        tool_top_k = max(2, min(int(live_routing_config.get("tool_top_k") or 5), 10))
        ranked_ids, retrieval_breakdown = smart_retrieve_tools_with_breakdown(
            task,
            tool_index=live_tool_index,
            primary_namespaces=worker_cfg.primary_namespaces,
            fallback_namespaces=worker_cfg.fallback_namespaces,
            limit=max(2, tool_top_k),
            tuning=persisted_tuning,
        )
        candidate_ids = [
            str(tool_id).strip() for tool_id in ranked_ids if str(tool_id).strip()
        ][:tool_top_k]
        top1 = candidate_ids[0] if candidate_ids else None
        top2 = candidate_ids[1] if len(candidate_ids) > 1 else None
        score_by_id: dict[str, float] = {}
        for row in list(retrieval_breakdown or []):
            tool_id = str(row.get("tool_id") or "").strip()
            if not tool_id:
                continue
            score_by_id[tool_id] = float(
                row.get("pre_rerank_score") or row.get("score") or 0.0
            )
        top1_score = score_by_id.get(top1 or "", 0.0)
        top2_score = score_by_id.get(top2 or "", 0.0)
        margin = (top1_score - top2_score) if top1 and top2 else None
        base_threshold = float(
            live_routing_config.get("tool_auto_margin_threshold") or 0.25
        )
        dynamic_threshold = (
            _adaptive_tool_margin_threshold(top1 or "", base_threshold)
            if top1
            else base_threshold
        )
        auto_score_threshold = float(
            live_routing_config.get("tool_auto_score_threshold") or 0.60
        )
        apply_gate = _live_phase_enabled(live_routing_config, "tool_gate")
        should_auto = bool(
            apply_gate
            and top1
            and margin is not None
            and margin >= dynamic_threshold
            and top1_score >= auto_score_threshold
        )
        if apply_gate and candidate_ids:
            selected_tool_ids = [top1] if should_auto and top1 else candidate_ids
            mode = "auto_select" if should_auto else "candidate_shortlist"
        else:
            selected_tool_ids = fallback_ids
            mode = (
                "shadow"
                if _live_phase_enabled(live_routing_config, "shadow")
                else "profile"
            )
        return {
            "selected_tool_ids": selected_tool_ids,
            "mode": mode,
            "auto_selected": bool(should_auto),
            "top1": top1,
            "top2": top2,
            "top1_score": float(top1_score),
            "top2_score": float(top2_score),
            "margin": margin,
            "threshold": float(dynamic_threshold),
            "candidate_ids": candidate_ids,
            "phase": str(live_routing_config.get("phase") or "shadow"),
        }

    def _hitl_enabled(stage: str) -> bool:
        if not bool(runtime_hitl_cfg.get("enabled", True)):
            return False
        normalized_stage = str(stage or "").strip().lower()
        if not normalized_stage:
            return False
        if isinstance(runtime_hitl_raw, bool):
            return bool(runtime_hitl_raw)
        aliases = {
            normalized_stage,
            f"confirm_{normalized_stage}",
            f"hitl_{normalized_stage}",
        }
        return any(bool(runtime_hitl_cfg.get(alias)) for alias in aliases)

    # Build route_to_intent_id dynamically from registry domains so that
    # domain-specific intent_ids (väder-och-klimat, trafik-och-transport …)
    # are visible to the intent resolver, not only the 4 broad routes.
    route_to_intent_id: dict[str, str] = {}
    if graph_registry is not None:
        for domain in graph_registry.domains:
            domain_id = str(domain.get("domain_id") or "").strip().lower()
            if domain_id and domain.get("enabled", True):
                fallback_route = (
                    str(domain.get("fallback_route") or domain_id).strip().lower()
                )
                route_to_intent_id[domain_id] = domain_id
                # Also register by fallback_route if not already taken by a more
                # specific domain.
                if fallback_route and fallback_route not in route_to_intent_id:
                    route_to_intent_id[fallback_route] = domain_id
    # Ensure the 4 broad route values always exist as keys (backward compat)
    broad_route_defaults = {
        "kunskap": "kunskap",
        "skapande": "skapande",
        "jämförelse": "jämförelse",
        "konversation": "konversation",
        "knowledge": "kunskap",
        "action": "skapande",
        "statistics": "kunskap",
        "compare": "jämförelse",
        "smalltalk": "konversation",
        "mixed": "mixed",
    }
    for key, value in broad_route_defaults.items():
        if key not in route_to_intent_id:
            route_to_intent_id[key] = value
    route_to_speculative_tool_ids: dict[str, list[str]] = {
        "kunskap": ["search_knowledge_base", "search_surfsense_docs", "search_tavily"],
        "åtgärd": list(dict.fromkeys(weather_tool_ids[:2] + trafik_tool_ids[:2])),
        "väder": weather_tool_ids[:6],
        "trafik-tag": trafik_tool_ids[:6],
        "trafik-vag": trafik_tool_ids[:6],
        "trafik-vagvader": trafik_tool_ids[:6],
        "statistik-ekonomi": _registry_tool_ids("statistik-ekonomi")[:6] or [
            "scb_nationalrakenskaper", "scb_priser_kpi", "scb_priser_inflation",
            "scb_handel", "scb_finansmarknad", "kolada_ekonomi",
        ],
        "statistik-befolkning": _registry_tool_ids("statistik-befolkning")[:6] or [
            "scb_befolkning", "scb_befolkning_folkmangd", "scb_befolkning_forandringar",
            "scb_befolkning_fodda", "scb_befolkning_dodsfall", "scb_befolkning_invandring",
        ],
        "statistik-arbetsmarknad": _registry_tool_ids("statistik-arbetsmarknad")[:6] or [
            "scb_arbetsmarknad", "scb_arbetsmarknad_arbetsloshet",
            "scb_arbetsmarknad_sysselsattning", "scb_arbetsmarknad_lon",
            "scb_arbetsmarknad_lonestruktur", "kolada_arbetsmarknad",
        ],
        "statistik-utbildning": _registry_tool_ids("statistik-utbildning")[:6] or [
            "scb_utbildning", "scb_utbildning_gymnasie", "scb_utbildning_hogskola",
            "kolada_forskola", "kolada_grundskola", "kolada_gymnasieskola",
        ],
        "statistik-halsa": _registry_tool_ids("statistik-halsa")[:6] or [
            "scb_halsa_sjukvard", "kolada_halsa", "kolada_aldreomsorg",
            "kolada_lss", "kolada_ifo", "kolada_barn_unga",
        ],
        "statistik-miljo": _registry_tool_ids("statistik-miljo")[:5] or [
            "scb_miljo", "scb_miljo_utslapp", "scb_miljo_energi",
            "scb_energi", "kolada_miljo",
        ],
        "statistik-fastighet": _registry_tool_ids("statistik-fastighet")[:5] or [
            "scb_boende_byggande", "scb_boende_bygglov", "scb_boende_nybyggnation",
            "scb_boende_bestand", "kolada_boende",
        ],
        "statistik-naringsliv": _registry_tool_ids("statistik-naringsliv")[:4] or [
            "scb_naringsverksamhet", "scb_naringsliv_foretag",
            "scb_naringsliv_omsattning", "scb_naringsliv_nyforetagande",
        ],
        "statistik-samhalle": _registry_tool_ids("statistik-samhalle")[:6] or [
            "scb_transporter", "scb_kultur", "scb_jordbruk",
            "scb_amnesovergripande", "kolada_kultur", "kolada_sammanfattning",
        ],
        "marknad": [
            str(definition.tool_id).strip()
            for definition in MARKETPLACE_TOOL_DEFINITIONS[:6]
            if str(definition.tool_id).strip()
        ],
    }

    def _agent_name_for_speculative_tool_id(
        tool_id: str,
        *,
        state: dict[str, Any] | None,
    ) -> str:
        normalized_tool_id = str(tool_id or "").strip().lower()
        if not normalized_tool_id:
            state_route = str(
                ((state or {}).get("resolved_intent") or {}).get("route")
                or (state or {}).get("route_hint")
                or ""
            ).strip()
            allowed = _route_allowed_agents(state_route)
            return _route_default_agent(state_route, allowed)

        # Registry-aware lookup: find which agent owns this tool
        if graph_registry is not None and graph_registry.tool_index:
            tool_entry = graph_registry.tool_index.get(normalized_tool_id)
            if tool_entry:
                agent_id = str(tool_entry.get("agent_id") or "").strip().lower()
                if agent_id and agent_id in agent_by_name:
                    return agent_id

        # Fallback: prefix-based heuristic for tools not yet in registry
        if normalized_tool_id in {
            str(item).strip().lower() for item in smhi_hydro_ids
        }:
            return "väder-vatten"
        if normalized_tool_id in {
            str(item).strip().lower() for item in smhi_risk_ids
        }:
            return "väder-risk"
        if normalized_tool_id in {
            str(item).strip().lower() for item in weather_tool_ids
        }:
            return "väder"
        if normalized_tool_id in {
            str(item).strip().lower() for item in trafik_tool_ids
        }:
            return "trafik"
        if normalized_tool_id.startswith(("scb_", "kolada_", "skolverket_")):
            # Fallback: resolve via bigtool_store namespace when registry
            # is unavailable.  The namespace function already encodes the
            # correct agent sub-category.
            from app.agents.new_chat.bigtool_store import (
                _namespace_for_kolada_tool,
                _namespace_for_scb_tool,
            )

            _ns_to_agent: dict[str, str] = {
                "befolkning": "statistik-befolkning",
                "arbetsmarknad": "statistik-arbetsmarknad",
                "utbildning": "statistik-utbildning",
                "halsa": "statistik-halsa",
                "miljo": "statistik-miljo",
                "fastighet": "statistik-fastighet",
                "naringsliv": "statistik-naringsliv",
                "ekonomi": "statistik-ekonomi",
                "samhalle": "statistik-samhalle",
                "demokrati": "riksdagen-dokument",
            }
            if normalized_tool_id.startswith("scb_"):
                ns = _namespace_for_scb_tool(normalized_tool_id)
            elif normalized_tool_id.startswith("kolada_"):
                ns = _namespace_for_kolada_tool(normalized_tool_id)
            else:
                ns = ()
            # namespace is e.g. ("tools", "statistics", "scb", "ekonomi")
            sub_key = ns[-1] if len(ns) >= 4 else ""
            return _ns_to_agent.get(sub_key, "statistik-ekonomi")
        if normalized_tool_id.startswith("riksdag_"):
            return "riksdagen"
        if normalized_tool_id.startswith("bolagsverket_"):
            return "bolag"
        if normalized_tool_id.startswith("marketplace_"):
            return "marknad"
        if normalized_tool_id.startswith("geoapify_"):
            return "kartor"
        if normalized_tool_id in {"generate_podcast", "display_image"}:
            return "media"
        if normalized_tool_id in {
            "search_knowledge_base",
            "search_surfsense_docs",
            "search_tavily",
            "recall_memory",
        }:
            return "kunskap"
        state_route = str(
            ((state or {}).get("resolved_intent") or {}).get("route")
            or (state or {}).get("route_hint")
            or ""
        ).strip()
        allowed = _route_allowed_agents(state_route)
        return _route_default_agent(state_route, allowed)

    async def _run_speculative_candidate(
        *,
        tool_id: str,
        candidate: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        latest_user_query = _latest_user_query(state.get("messages") or [])
        if not latest_user_query:
            return {
                "status": "failed",
                "reason": "empty_query",
                "tool_id": tool_id,
            }
        probability = _coerce_confidence(candidate.get("probability"), 0.5)
        selected_agent_name = _agent_name_for_speculative_tool_id(
            tool_id,
            state=state,
        )
        worker = await worker_pool.get(selected_agent_name)
        if worker is None:
            return {
                "status": "failed",
                "reason": "worker_unavailable",
                "tool_id": tool_id,
                "agent": selected_agent_name,
            }
        selected_tool_ids_for_worker = _sanitize_selected_tool_ids_for_worker(
            worker,
            [tool_id],
            fallback_tool_ids=_fallback_tool_ids_for_tool(tool_id),
            limit=1,
        )
        if not selected_tool_ids_for_worker:
            return {
                "status": "failed",
                "reason": "tool_unavailable",
                "tool_id": tool_id,
                "agent": selected_agent_name,
                "probability": probability,
            }

        cached_payload = episodic_store.get(tool_id=tool_id, query=latest_user_query)
        if isinstance(cached_payload, dict):
            cached_response = _strip_critic_json(
                str(cached_payload.get("response") or "").strip()
            )
            if cached_response:
                cached_used_tools_raw = cached_payload.get("used_tools")
                cached_used_tools = (
                    [
                        str(item).strip()
                        for item in cached_used_tools_raw
                        if str(item).strip()
                    ][:6]
                    if isinstance(cached_used_tools_raw, list)
                    else [tool_id]
                )
                cached_contract = cached_payload.get("result_contract")
                if not isinstance(cached_contract, dict):
                    cached_contract = _build_agent_result_contract(
                        agent_name=selected_agent_name,
                        task=latest_user_query,
                        response_text=cached_response,
                        used_tools=cached_used_tools,
                        final_requested=False,
                    )
                return {
                    "status": "cached",
                    "reason": "episodic_memory_hit",
                    "tool_id": tool_id,
                    "agent": selected_agent_name,
                    "response": cached_response,
                    "used_tools": cached_used_tools,
                    "result_contract": cached_contract,
                    "probability": probability,
                    "duration_ms": 0,
                    "from_episodic_cache": True,
                }

        prompt = worker_prompts.get(selected_agent_name, "")
        scoped_prompt = _build_scoped_prompt_for_agent(
            selected_agent_name,
            latest_user_query,
            prompt_template=scoped_tool_prompt_template,
        )
        if scoped_prompt:
            prompt = (
                f"{prompt.rstrip()}\n\n{scoped_prompt}".strip()
                if prompt
                else scoped_prompt
            )
        tool_prompt_block = _build_tool_prompt_block(
            [tool_id],
            tool_prompt_overrides,
            max_tools=1,
            default_prompt_template=tool_default_prompt_template,
        )
        if tool_prompt_block:
            prompt = (
                f"{prompt.rstrip()}\n\n{tool_prompt_block}".strip()
                if prompt
                else tool_prompt_block
            )
        worker_messages: list[Any] = []
        if prompt:
            worker_messages.append(SystemMessage(content=prompt))
        worker_messages.append(HumanMessage(content=latest_user_query))
        worker_state = {
            "messages": worker_messages,
            "selected_tool_ids": selected_tool_ids_for_worker,
        }
        turn_key = _current_turn_key(state)
        base_thread_id = str(dependencies.get("thread_id") or "thread")
        worker_checkpoint_ns = str(dependencies.get("checkpoint_ns") or "").strip()
        worker_configurable = {
            "thread_id": (
                f"{base_thread_id}:{selected_agent_name}:speculative:{turn_key}:{tool_id[:24]}"
            )
        }
        if worker_checkpoint_ns:
            worker_configurable["checkpoint_ns"] = (
                f"{worker_checkpoint_ns}:worker:{selected_agent_name}"
            )
        worker_config = {"configurable": worker_configurable, "recursion_limit": 40}
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                worker.ainvoke(worker_state, config=worker_config),
                timeout=10.0,
            )
        except TimeoutError:
            return {
                "status": "failed",
                "reason": "timeout",
                "tool_id": tool_id,
                "agent": selected_agent_name,
                "probability": probability,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "reason": f"exception:{type(exc).__name__}",
                "tool_id": tool_id,
                "agent": selected_agent_name,
                "probability": probability,
            }
        duration_ms = int((time.monotonic() - started) * 1000)
        response_text = ""
        messages_out: list[Any] = []
        if isinstance(result, dict):
            messages_out = result.get("messages") or []
            if messages_out:
                response_text = str(getattr(messages_out[-1], "content", "") or "")
        if not response_text:
            response_text = str(result)
        response_text = _strip_critic_json(response_text)
        used_tool_names = _tool_names_from_messages(messages_out) or [tool_id]
        result_contract = _build_agent_result_contract(
            agent_name=selected_agent_name,
            task=latest_user_query,
            response_text=response_text,
            used_tools=used_tool_names,
            final_requested=False,
        )
        # Guard: downgrade if all data tools returned empty data
        if (
            _all_tool_data_empty(messages_out)
            and str(result_contract.get("status") or "") == "success"
        ):
            result_contract.update(
                {
                    "status": "partial",
                    "actionable": False,
                    "retry_recommended": True,
                    "confidence": min(
                        float(result_contract.get("confidence") or 0.35),
                        0.35,
                    ),
                    "reason": (
                        "Alla verktyg returnerade tom data. "
                        "Svaret kan inte verifieras."
                    ),
                }
            )
        status = str(result_contract.get("status") or "").strip().lower()
        speculative_status = status if status in {"success", "partial"} else "failed"
        if speculative_status in {"success", "partial"} and response_text:
            episodic_store.put(
                tool_id=tool_id,
                query=latest_user_query,
                value={
                    "response": response_text,
                    "used_tools": used_tool_names,
                    "result_contract": result_contract,
                    "agent": selected_agent_name,
                },
                ttl_seconds=infer_ttl_seconds(
                    tool_id=tool_id,
                    agent_name=selected_agent_name,
                ),
            )
        return {
            "status": speculative_status,
            "reason": str(result_contract.get("reason") or ""),
            "tool_id": tool_id,
            "agent": selected_agent_name,
            "response": response_text,
            "used_tools": used_tool_names,
            "result_contract": result_contract,
            "probability": probability,
            "duration_ms": duration_ms,
            "from_episodic_cache": False,
        }

    def _intent_from_route(route_value: str | None) -> dict[str, Any]:
        normalized = _normalize_route_hint_value(route_value)
        intent_id = route_to_intent_id.get(normalized, normalized or "kunskap")
        return {
            "intent_id": intent_id,
            "route": normalized or intent_id,
            "reason": "Fallback baserad pa route_hint.",
            "confidence": 0.5,
        }

    def _route_default_agent_for_intent(
        route_value: str | None,
        latest_user_query: str = "",
    ) -> str:
        normalized = _normalize_route_hint_value(route_value)
        if normalized in {"skapande", "action", "kunskap", "knowledge"}:
            if sandbox_enabled and _has_filesystem_intent(latest_user_query):
                return "kod"
            if _has_weather_intent(latest_user_query):
                return "väder"
            if _has_strict_trafik_intent(latest_user_query):
                return "trafik"
            if _has_map_intent(latest_user_query):
                return "kartor"
            if _has_marketplace_intent(latest_user_query):
                return "marknad"
        allowed = _route_allowed_agents(normalized)
        return _route_default_agent(normalized, allowed)

    def _coerce_resolved_intent_for_query(
        resolved_intent_payload: dict[str, Any],
        latest_user_query: str,
        route_hint: str | None = None,
    ) -> dict[str, Any]:
        resolved = (
            dict(resolved_intent_payload)
            if isinstance(resolved_intent_payload, dict)
            else {}
        )
        query = str(latest_user_query or "").strip()
        if not query:
            return resolved
        normalized_route = _normalize_route_hint_value(
            resolved.get("route") or route_hint
        )
        if normalized_route in {"jämförelse", "compare", "mixed"}:
            return resolved

        # Dynamic domain→agent route override from GraphRegistry.
        # When intent resolution identifies a specialized domain, the
        # fallback_route is "kunskap" for legacy compat.  We override
        # the route to the first agent in that domain so the agent
        # resolver picks the correct specialist agent.
        intent_id = str(resolved.get("intent_id") or "").strip().lower()
        if (
            intent_id
            and normalized_route in {"kunskap", "knowledge"}
            and graph_registry is not None
            and graph_registry.agents_by_domain
        ):
            domain_agents = graph_registry.agents_by_domain.get(intent_id) or []
            if domain_agents:
                # Use the first enabled agent in the domain as the route
                first_agent = next(
                    (
                        str(a.get("agent_id") or "").strip()
                        for a in domain_agents
                        if a.get("enabled", True)
                        and str(a.get("agent_id") or "").strip()
                    ),
                    "",
                )
                if first_agent:
                    resolved["route"] = first_agent

        if sandbox_enabled and _has_filesystem_intent(query):
            override_route = "skapande"
            override_reason = "Heuristisk override: filsystem/sandbox-fraga ska routas till skapande/code."
            if (
                normalized_route != override_route
                or not str(resolved.get("intent_id") or "").strip()
            ):
                resolved["intent_id"] = route_to_intent_id.get(
                    override_route, override_route
                )
                resolved["route"] = override_route
                resolved["reason"] = override_reason
                resolved["confidence"] = max(
                    _coerce_confidence(resolved.get("confidence"), 0.5),
                    0.9,
                )
        return resolved

    def _classify_graph_complexity(
        resolved_intent_payload: dict[str, Any],
        latest_user_query: str,
    ) -> str:
        if not hybrid_mode:
            return "complex"
        return classify_graph_complexity(
            resolved_intent=resolved_intent_payload,
            user_query=latest_user_query,
        )

    def _build_speculative_candidates_for_intent(
        resolved_intent_payload: dict[str, Any],
        latest_user_query: str,
    ) -> list[dict[str, Any]]:
        if not (hybrid_mode and speculative_enabled):
            return []
        return build_speculative_candidates(
            resolved_intent=resolved_intent_payload,
            user_query=latest_user_query,
            route_to_tool_ids=route_to_speculative_tool_ids,
            max_candidates=3,
        )

    def _build_trivial_response_for_intent(latest_user_query: str) -> str | None:
        if not hybrid_mode:
            return None
        return build_trivial_response(latest_user_query)

    def _agent_payload(definition: AgentDefinition) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": definition.name,
            "description": definition.description,
            "keywords": list(definition.keywords or []),
        }
        if definition.main_identifier:
            payload["main_identifier"] = definition.main_identifier
        if definition.core_activity:
            payload["core_activity"] = definition.core_activity
        if definition.unique_scope:
            payload["unique_scope"] = definition.unique_scope
        if definition.excludes:
            payload["excludes"] = list(definition.excludes)
        return payload

    def _next_plan_step(state: dict[str, Any]) -> dict[str, Any] | None:
        plan_items = state.get("active_plan") or []
        if not isinstance(plan_items, list) or not plan_items:
            return None
        try:
            step_index = int(state.get("plan_step_index") or 0)
        except (TypeError, ValueError):
            step_index = 0
        step_index = max(0, step_index)
        if step_index < len(plan_items) and isinstance(plan_items[step_index], dict):
            return plan_items[step_index]
        for item in plan_items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip().lower()
            if status in {"pending", "in_progress"}:
                return item
        return plan_items[0] if isinstance(plan_items[0], dict) else None

    def _plan_preview_text(state: dict[str, Any], *, max_steps: int = 4) -> str:
        plan_items = state.get("active_plan") or []
        if not isinstance(plan_items, list) or not plan_items:
            return "- Ingen plan tillganglig."
        lines: list[str] = []
        for item in plan_items[: max(1, int(max_steps))]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            status = str(item.get("status") or "pending").strip().lower()
            lines.append(f"- [{status}] {content}")
        return "\n".join(lines) if lines else "- Ingen plan tillganglig."

    def _resolve_agent_name(
        requested_name: str,
        *,
        task: str,
        state: dict[str, Any] | None = None,
    ) -> tuple[str | None, str | None]:
        requested_raw = str(requested_name or "").strip().lower()
        if not requested_raw:
            return None, "empty_name"
        route_hint = _normalize_route_hint_value((state or {}).get("route_hint"))
        route_allowed = _route_allowed_agents(route_hint)
        default_for_route = _route_default_agent(route_hint, route_allowed)
        strict_trafik_task = _has_strict_trafik_intent(task)
        weather_task = _has_weather_intent(task)
        marketplace_task = _has_marketplace_intent(task)
        filesystem_task = _has_filesystem_intent(task)
        explicit_marketplace_provider = bool(
            task and _MARKETPLACE_PROVIDER_RE.search(str(task))
        )
        selected_agent_names: list[str] = []
        if state:
            for item in state.get("selected_agents") or []:
                if isinstance(item, dict):
                    candidate = str(item.get("name") or "").strip().lower()
                else:
                    candidate = str(item or "").strip().lower()
                if (
                    candidate
                    and candidate in agent_by_name
                    and candidate not in selected_agent_names
                ):
                    selected_agent_names.append(candidate)
        selected_agent_set = set(selected_agent_names)

        def _selected_fallback(preferred: str | None = None) -> str | None:
            if preferred and preferred in selected_agent_set:
                return preferred
            if selected_agent_names:
                return selected_agent_names[0]
            if preferred and preferred in agent_by_name:
                return preferred
            return None

        # Soft preference for weather-capable agents on weather tasks
        if (
            route_hint in {"kunskap", "skapande", "action", "knowledge"}
            and weather_task
            and not strict_trafik_task
        ):
            if requested_raw in agent_by_name and requested_raw != "väder":
                # Check if requested agent has SMHI tools via its WorkerConfig
                requested_worker = worker_configs.get(requested_raw)
                has_weather_tools = False
                if requested_worker:
                    all_namespaces = list(requested_worker.primary_namespaces or [])
                    all_namespaces.extend(requested_worker.fallback_namespaces or [])
                    has_weather_tools = any(
                        ("weather" in ns or "smhi" in str(ns).lower())
                        for ns in all_namespaces
                    )
                if not has_weather_tools:
                    return "väder", f"weather_soft_lock:{requested_raw}->väder"
        if (
            route_hint in {"kunskap", "skapande", "action", "knowledge"}
            and strict_trafik_task
        ):
            allowed_for_strict = {"trafik", "kartor", "åtgärd"}
            if (
                requested_raw in agent_by_name
                and requested_raw not in allowed_for_strict
            ):
                return "trafik", f"strict_trafik_lock:{requested_raw}->trafik"
        # For explicit marketplace tasks, keep execution on marketplace to avoid
        # drifting into browser/web-search aliases mid-plan.
        if (
            route_hint in {"kunskap", "skapande", "action", "knowledge"}
            and marketplace_task
            and not weather_task
            and not strict_trafik_task
            and (explicit_marketplace_provider or "marknad" in selected_agent_set)
            and "marknad" in agent_by_name
            and requested_raw != "marknad"
        ):
            return "marknad", f"marketplace_lock:{requested_raw}->marknad"
        # For filesystem operations in sandbox mode, always execute through code agent.
        if (
            sandbox_enabled
            and filesystem_task
            and "kod" in agent_by_name
            and requested_raw != "kod"
        ):
            return "kod", f"filesystem_hard_lock:{requested_raw}->kod"
        # SCALABLE FIX: If requested agent is a specialized agent with dedicated tools,
        # respect that choice and DON'T override with route_policy.
        # This scales to 100s of APIs without needing regex patterns.
        if requested_raw in agent_by_name:
            # Specialized agents (statistik, marknad, etc.) must NEVER be
            # remapped by selected_agents_lock — they own domain-specific
            # tools that other agents cannot substitute.
            if requested_raw in specialized_agents:
                return requested_raw, None
            if selected_agent_set and requested_raw not in selected_agent_set:
                fallback = _selected_fallback(
                    "marknad" if marketplace_task else default_for_route
                )
                if fallback and fallback in agent_by_name:
                    return fallback, f"selected_agents_lock:{requested_raw}->{fallback}"
            if route_allowed and requested_raw not in route_allowed:
                if default_for_route in agent_by_name:
                    return (
                        default_for_route,
                        f"route_policy:{requested_raw}->{default_for_route}",
                    )
            return requested_raw, None

        alias_guess = _guess_agent_from_alias(requested_raw)
        if alias_guess and alias_guess in agent_by_name:
            if selected_agent_set and alias_guess not in selected_agent_set:
                fallback = _selected_fallback(
                    "marknad" if marketplace_task else default_for_route
                )
                if fallback and fallback in agent_by_name:
                    return (
                        fallback,
                        f"selected_agents_lock_alias:{requested_raw}->{fallback}",
                    )
            if route_allowed and alias_guess not in route_allowed:
                if default_for_route in agent_by_name:
                    return (
                        default_for_route,
                        f"route_policy_alias:{requested_raw}->{default_for_route}",
                    )
            return alias_guess, f"alias:{requested_raw}->{alias_guess}"

        recent_agents: list[str] = []
        route_hint = None
        if state:
            route_hint = _normalize_route_hint_value(state.get("route_hint"))
            recent_calls = state.get("recent_agent_calls") or []
            recent_agents = [
                str(call.get("agent") or "").strip()
                for call in recent_calls
                if isinstance(call, dict) and str(call.get("agent") or "").strip()
            ]
        route_allowed = _route_allowed_agents(route_hint)
        default_for_route = _route_default_agent(route_hint, route_allowed)
        retrieval_query = (
            f"{task}\n"
            f"Agent hint from planner: {requested_raw}\n"
            "Resolve to one existing internal agent id."
        )
        retrieved = _smart_retrieve_agents(
            retrieval_query,
            agent_definitions=agent_definitions,
            recent_agents=recent_agents,
            limit=3,
        )
        if route_allowed:
            retrieved = [agent for agent in retrieved if agent.name in route_allowed]
        if selected_agent_set:
            retrieved = [
                agent for agent in retrieved if agent.name in selected_agent_set
            ]
        if route_hint:
            preferred = {
                "kunskap": ["kunskap", "webb"],
                "skapande": ["åtgärd", "media"],
                "jämförelse": ["syntes", "kunskap", "statistik-ekonomi"],
                # Backward compat
                "action": ["åtgärd", "media"],
                "knowledge": ["kunskap", "webb"],
                "statistics": ["statistik-ekonomi"],
                "compare": ["syntes", "kunskap", "statistik-ekonomi"],
            }.get(str(route_hint), [])
            if marketplace_task and "marknad" not in preferred:
                preferred.insert(0, "marknad")
            if str(route_hint) in {"skapande", "action"}:
                if sandbox_enabled and filesystem_task:
                    preferred = ["kod", "åtgärd"]
                if marketplace_task and "marknad" not in preferred:
                    preferred.insert(0, "marknad")
                if _has_map_intent(task) and "kartor" not in preferred:
                    preferred.insert(0, "kartor")
                if (
                    _has_trafik_intent(task)
                    and not weather_task
                    and "trafik" not in preferred
                ):
                    preferred.insert(0, "trafik")
            if route_allowed:
                preferred = [name for name in preferred if name in route_allowed]
            if selected_agent_set:
                preferred = [name for name in preferred if name in selected_agent_set]
            for preferred_name in preferred:
                if any(agent.name == preferred_name for agent in retrieved):
                    return (
                        preferred_name,
                        f"route_pref:{requested_raw}->{preferred_name}",
                    )
        if retrieved:
            return retrieved[0].name, f"retrieval:{requested_raw}->{retrieved[0].name}"
        if selected_agent_names:
            fallback = _selected_fallback(
                "marknad" if marketplace_task else default_for_route
            )
            if fallback and fallback in agent_by_name:
                return fallback, f"selected_agents_fallback:{requested_raw}->{fallback}"
        if route_allowed and default_for_route in agent_by_name:
            return (
                default_for_route,
                f"route_default:{requested_raw}->{default_for_route}",
            )
        return None, f"unresolved:{requested_raw}"

    def _build_compare_external_tool(spec):
        async def _compare_tool(query: str) -> dict[str, Any]:
            result = await call_external_model(
                spec=spec,
                query=query,
                system_prompt=compare_external_prompt,
            )
            if connector_service:
                try:
                    document = await connector_service.ingest_tool_output(
                        tool_name=spec.tool_name,
                        tool_output=result,
                        metadata={
                            "provider": result.get("provider"),
                            "model": result.get("model"),
                            "model_display_name": result.get("model_display_name"),
                            "source": result.get("source"),
                        },
                        user_id=user_id,
                        origin_search_space_id=search_space_id,
                        thread_id=thread_id,
                    )
                    if document and getattr(document, "chunks", None):
                        result["document_id"] = document.id
                        result["citation_chunk_ids"] = [
                            str(chunk.id) for chunk in document.chunks
                        ]
                except Exception as exc:
                    print(f"[compare] Failed to ingest {spec.tool_name}: {exc!s}")
            return result

        return tool(
            spec.tool_name,
            description=f"Call external model {spec.display} for compare mode.",
        )(_compare_tool)

    @tool
    async def retrieve_agents(
        query: str,
        limit: int = 1,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Retrieve relevant agents for the task.

        Use this only when selected agent context is missing or stale.
        If `selected_agents` is already populated for the current plan, continue with
        call_agent/call_agents_parallel instead of retrieving again.

        IMPORTANT: Reuse agent names exactly as returned in `agents[].name`.
        Allowed internal ids include: åtgärd, väder, kartor, statistik, media, kunskap,
        webb, kod, bolag, trafik, riksdagen, marknad, syntes.
        """
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 1
        limit = max(1, min(limit, 2))

        recent_agents = []
        context_query = query
        route_hint = None
        cache_key = None
        cache_pattern = None
        policy_query = query
        if state:
            recent_calls = state.get("recent_agent_calls") or []
            recent_agents = [
                str(call.get("agent")) for call in recent_calls if call.get("agent")
            ]
            route_hint = _normalize_route_hint_value(state.get("route_hint"))
            latest_user_query = _latest_user_query(state.get("messages") or [])
            if latest_user_query:
                policy_query = latest_user_query
            context_parts = []
            for call in recent_calls[-3:]:
                response = str(call.get("response") or "")
                if len(response) > 120:
                    response = response[:117] + "..."
                context_parts.append(
                    f"{call.get('agent')}: {call.get('task')} {response}"
                )
            if context_parts:
                context_query = f"{query} {' '.join(context_parts)}"

        has_trafik_intent = _has_trafik_intent(policy_query)
        has_strict_trafik_intent = _has_strict_trafik_intent(policy_query)
        has_map_intent = _has_map_intent(policy_query)
        has_weather_intent = _has_weather_intent(policy_query)
        has_marketplace_intent = _has_marketplace_intent(policy_query)
        has_filesystem_intent = _has_filesystem_intent(policy_query)
        route_allowed = _route_allowed_agents(route_hint)
        default_for_route = _route_default_agent(route_hint, route_allowed)
        # Weather limit removed: should be controlled by graph_complexity like other routes
        if route_hint and (
            str(route_hint).startswith("statistik") or route_hint == "statistics"
        ):  # Statistics agents chosen by agent_resolver, not route
            limit = 1

        # Extract sub_intents from state for multi-domain cache key
        sub_intents = state.get("sub_intents") if state else None
        cache_key, cache_pattern = _build_cache_key(
            query, route_hint, recent_agents, sub_intents
        )
        cached_agents = _get_cached_combo(cache_key)
        if cached_agents is None:
            cached_agents = await _fetch_cached_combo_db(db_session, cache_key)
            if cached_agents:
                _set_cached_combo(cache_key, cached_agents)
        if (
            cached_agents
            and route_hint in {"kunskap", "skapande", "action", "knowledge"}
            and has_strict_trafik_intent
        ):
            # Avoid stale non-traffic combos on hard traffic queries.
            cached_agents = None
        if cached_agents and has_trafik_intent and "trafik" not in cached_agents:
            cached_agents = None
        if cached_agents and has_marketplace_intent and "marknad" not in cached_agents:
            cached_agents = None

        if cached_agents:
            selected = [
                agent_by_name[name] for name in cached_agents if name in agent_by_name
            ]
        else:
            selected = _smart_retrieve_agents(
                context_query,
                agent_definitions=agent_definitions,
                recent_agents=recent_agents,
                limit=limit,
            )
            if route_hint:
                preferred = {
                    "kunskap": ["kunskap", "webb"],
                    "skapande": ["åtgärd", "media"],
                    "jämförelse": ["syntes", "kunskap", "statistik-ekonomi"],
                    # Backward compat
                    "action": ["åtgärd", "media"],
                    "knowledge": ["kunskap", "webb"],
                    "statistics": ["statistik-ekonomi"],
                    "compare": ["syntes", "kunskap", "statistik-ekonomi"],
                    "trafik": ["trafik", "åtgärd"],
                }.get(str(route_hint), [])
                if has_marketplace_intent and "marknad" not in preferred:
                    preferred.insert(0, "marknad")
                if str(route_hint) in {"skapande", "action", "kunskap", "knowledge"}:
                    if sandbox_enabled and has_filesystem_intent:
                        preferred = ["kod", "åtgärd"]
                    if has_marketplace_intent and "marknad" not in preferred:
                        preferred.insert(0, "marknad")
                    # Keep route_hint as advisory only unless action intent is explicit.
                    if not (
                        has_map_intent
                        or has_trafik_intent
                        or (sandbox_enabled and has_filesystem_intent)
                    ):
                        preferred = []
                        if has_marketplace_intent:
                            preferred = ["marknad"]
                    if has_map_intent and "kartor" not in preferred:
                        preferred.insert(0, "kartor")
                    if (
                        has_trafik_intent
                        and not has_weather_intent
                        and "trafik" not in preferred
                    ):
                        preferred.insert(0, "trafik")
                if preferred:
                    for preferred_name in reversed(preferred):
                        agent = agent_by_name.get(preferred_name)
                        if not agent:
                            continue
                        if agent in selected:
                            selected = [item for item in selected if item != agent]
                        selected.insert(0, agent)
                    selected = selected[:limit]

            if (
                has_trafik_intent
                and not has_weather_intent
                and route_hint
                in {"kunskap", "skapande", "action", "knowledge", "trafik"}
            ):
                trafik_agent = agent_by_name.get("trafik")
                if trafik_agent and trafik_agent not in selected:
                    selected.insert(0, trafik_agent)
                    selected = selected[:limit]
            if (
                route_hint in {"kunskap", "skapande", "action", "knowledge"}
                and sandbox_enabled
                and has_filesystem_intent
            ):
                code_agent = agent_by_name.get("kod")
                if code_agent:
                    if code_agent in selected:
                        selected = [agent for agent in selected if agent != code_agent]
                    selected.insert(0, code_agent)
                    selected = selected[:limit]

            if route_allowed:
                filtered = [agent for agent in selected if agent.name in route_allowed]
                if filtered:
                    selected = filtered
                elif default_for_route in agent_by_name:
                    selected = [agent_by_name[default_for_route]]

            selected_names = [agent.name for agent in selected]
            if cache_key and cache_pattern:
                await _store_cached_combo_db(
                    db_session,
                    cache_key=cache_key,
                    route_hint=route_hint,
                    pattern=cache_pattern,
                    recent_agents=recent_agents,
                    agents=selected_names,
                )

        if route_allowed:
            filtered = [agent for agent in selected if agent.name in route_allowed]
            if filtered:
                selected = filtered
            elif default_for_route in agent_by_name:
                selected = [agent_by_name[default_for_route]]

        selected = selected[:limit]
        if (
            route_hint in {"kunskap", "skapande", "action", "knowledge"}
            and has_marketplace_intent
            and not has_weather_intent
            and not has_strict_trafik_intent
        ):
            marketplace_order = ["marknad"]
            marketplace_selected = [
                agent_by_name[name]
                for name in marketplace_order
                if name in agent_by_name
            ]
            selected = (
                marketplace_selected[:limit] if marketplace_selected else selected
            )
        # Weather order removed: selection should be based on retrieval and LLM classification
        if (
            route_hint in {"kunskap", "skapande", "action", "knowledge"}
            and has_strict_trafik_intent
        ):
            strict_order = ["trafik"]
            if has_map_intent:
                strict_order.append("kartor")
            strict_order.append("åtgärd")
            strict_selected = [
                agent_by_name[name] for name in strict_order if name in agent_by_name
            ]
            selected = strict_selected[:limit] if strict_selected else selected
        payload = [
            {"name": agent.name, "description": agent.description} for agent in selected
        ]
        return json.dumps(
            {
                "agents": payload,
                "valid_agent_ids": [agent.name for agent in agent_definitions],
            },
            ensure_ascii=True,
        )

    def _prepare_task_for_synthesis(task: str, state: dict[str, Any] | None) -> str:
        """Add compare_outputs context for synthesis agent if applicable."""
        if not state:
            return task
        normalized_task = str(task or "").strip()
        if not normalized_task:
            return task

        def _build_recent_compare_context() -> str:
            if not _COMPARE_FOLLOWUP_RE.search(normalized_task):
                return ""
            candidates: list[dict[str, str]] = []
            for entry in reversed(list(state.get("recent_agent_calls") or [])):
                if not isinstance(entry, dict):
                    continue
                response = _strip_critic_json(str(entry.get("response") or "").strip())
                if not response:
                    continue
                agent_name = str(entry.get("agent") or "").strip() or "agent"
                task_text = str(entry.get("task") or "").strip()
                candidates.append(
                    {
                        "agent": agent_name,
                        "task": task_text,
                        "response": _truncate_for_prompt(response, 420),
                    }
                )
                if len(candidates) >= 2:
                    break
            if len(candidates) < 2:
                return ""
            candidates.reverse()
            lines = ["<recent_agent_results>"]
            for idx, item in enumerate(candidates, start=1):
                lines.append(f"Resultat {idx} ({item['agent']}): {item['response']}")
                if item["task"]:
                    lines.append(f"Uppgift {idx}: {item['task']}")
            lines.append(
                "Om användaren skriver 'dessa två' eller liknande: jämför just dessa två resultat först, "
                "innan du hämtar ny data."
            )
            lines.append("</recent_agent_results>")
            return "\n".join(lines)

        compare_context = _format_compare_outputs_for_prompt(
            state.get("compare_outputs") or []
        )
        if compare_context and "<compare_outputs>" not in normalized_task:
            normalized_task = f"{normalized_task}\n\n{compare_context}"
        recent_compare_context = _build_recent_compare_context()
        if recent_compare_context and "<recent_agent_results>" not in normalized_task:
            normalized_task = f"{normalized_task}\n\n{recent_compare_context}"
        return normalized_task

    def _collect_speculative_response(
        *,
        selected_tool_ids: list[str],
        state: dict[str, Any] | None,
    ) -> tuple[str, list[str], list[dict[str, Any]]]:
        if not selected_tool_ids:
            return "", [], []
        injected_state = state or {}
        speculative_results = injected_state.get("speculative_results")
        if not isinstance(speculative_results, dict):
            return "", [], []

        accepted_statuses = {"success", "partial", "cached", "ok"}
        used_tools: list[str] = []
        raw_responses: list[str] = []
        payloads: list[dict[str, Any]] = []
        for tool_id in selected_tool_ids:
            payload = speculative_results.get(str(tool_id).strip())
            if not isinstance(payload, dict):
                return "", [], []
            status = str(payload.get("status") or "").strip().lower()
            if status not in accepted_statuses:
                return "", [], []
            response_text = _strip_critic_json(
                str(payload.get("response") or "").strip()
            )
            if response_text:
                raw_responses.append(response_text)
            used_tools.append(str(tool_id).strip())
            payloads.append(payload)

        if not raw_responses:
            return "", [], []
        deduped: list[str] = []
        seen: set[str] = set()
        for response in raw_responses:
            normalized = response.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(response)
        return "\n\n".join(deduped).strip(), used_tools, payloads

    def _subagent_isolation_active(execution_strategy: str) -> bool:
        if not subagent_enabled:
            return False
        normalized = str(execution_strategy or "").strip().lower()
        # Allow isolation for both "subagent" and "parallel" (multi-agent runs)
        if normalized not in {"subagent", "parallel"}:
            return False
        return bool(subagent_isolation_enabled)

    def _build_subagent_task(
        *,
        task: str,
        state: dict[str, Any],
        subagent_id: str,
        agent_name: str,
    ) -> str:
        if not str(task or "").strip():
            return ""
        latest_query = _truncate_for_prompt(
            _latest_user_query((state or {}).get("messages") or []),
            max(120, int(subagent_context_max_chars // 2)),
        )
        route_hint = _normalize_route_hint_value(
            ((state or {}).get("resolved_intent") or {}).get("route")
            or (state or {}).get("route_hint")
        )
        focused_tools = (
            ((state or {}).get("resolved_tools_by_agent") or {}).get(agent_name)
            if isinstance((state or {}).get("resolved_tools_by_agent"), dict)
            else []
        )
        focused_tools_text = ", ".join(
            str(item).strip()
            for item in (focused_tools if isinstance(focused_tools, list) else [])
            if str(item).strip()
        )
        task_body = _truncate_for_prompt(
            str(task or "").strip(), int(subagent_context_max_chars)
        )
        context_lines = [f"subagent_id={subagent_id}"]
        if route_hint:
            context_lines.append(f"route_hint={route_hint}")
        if latest_query:
            context_lines.append(f"parent_query={latest_query}")
        if focused_tools_text:
            context_lines.append(f"preferred_tools={focused_tools_text}")
        context_block = "\n".join(context_lines)
        rendered = _format_prompt_template(
            subagent_context_prompt_template,
            {
                "subagent_context_lines": context_block,
                "subagent_id": subagent_id,
                "route_hint": route_hint,
                "parent_query": latest_query,
                "preferred_tools": focused_tools_text,
                "task": task_body,
            },
        )
        if rendered:
            return rendered
        return DEFAULT_SUPERVISOR_SUBAGENT_CONTEXT_TEMPLATE.format(
            subagent_context_lines=context_block,
            task=task_body,
        ).strip()

    def _build_subagent_worker_state(
        *,
        base_messages: list[Any],
        selected_tool_ids: list[str],
        isolated: bool,
        subagent_id: str | None,
    ) -> dict[str, Any]:
        state_payload: dict[str, Any] = {
            "messages": list(base_messages),
            "selected_tool_ids": selected_tool_ids,
        }
        if isolated and subagent_id:
            state_payload["subagent_id"] = subagent_id
            state_payload["sandbox_scope_mode"] = "subagent"
            state_payload["sandbox_scope_id"] = subagent_id
        return state_payload

    def _is_filesystem_task(agent_name: str, task: str) -> bool:
        return str(agent_name or "").strip().lower() in {
            "kod",
            "code",
        } and _has_filesystem_intent(task)

    def _is_filesystem_sandbox_task(agent_name: str, task: str) -> bool:
        return bool(sandbox_enabled) and _is_filesystem_task(agent_name, task)

    def _requires_explicit_file_read(task: str) -> bool:
        task_text = str(task or "").strip()
        if not task_text:
            return False
        if not _EXPLICIT_FILE_READ_RE.search(task_text):
            return False
        if _has_filesystem_intent(task_text):
            return True
        return "/workspace/" in task_text or "/tmp/" in task_text

    def _prioritize_sandbox_code_tools(
        tool_ids: list[str],
        *,
        agent_name: str,
        task: str,
        limit: int = 8,
    ) -> list[str]:
        merged = list(tool_ids or [])
        if _is_filesystem_sandbox_task(agent_name, task):
            merged = list(_SANDBOX_CODE_TOOL_IDS) + merged
        ordered: list[str] = []
        seen: set[str] = set()
        for tool_id in merged:
            normalized = str(tool_id or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
            if len(ordered) >= max(1, int(limit)):
                break
        return ordered

    def _uses_sandbox_tool(tool_names: list[str] | None) -> bool:
        return any(
            (
                str(name or "").strip().lower().startswith("sandbox_")
                or str(name or "").strip().lower() in _SANDBOX_ALIAS_TOOL_IDS
            )
            for name in (tool_names or [])
        )

    def _looks_filesystem_not_found_response(text: str) -> bool:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return False
        return any(marker in lowered for marker in _FILESYSTEM_NOT_FOUND_MARKERS)

    def _collect_subagent_artifacts_from_messages(
        *,
        messages_out: list[Any],
        injected_state: dict[str, Any],
        force_sandbox_for_auto: bool = False,
        subagent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not artifact_offload_enabled:
            return []
        if not isinstance(messages_out, list) or not messages_out:
            return []

        normalized_messages: list[ToolMessage] = []
        for message in messages_out:
            if isinstance(message, ToolMessage):
                normalized_messages.append(message)
                continue
            if (
                isinstance(message, dict)
                and str(message.get("type") or "").strip().lower() == "tool"
            ):
                normalized_messages.append(
                    ToolMessage(
                        content=message.get("content") or "",
                        name=message.get("name"),
                        tool_call_id=message.get("tool_call_id"),
                    )
                )
        if not normalized_messages:
            return []

        storage_mode = artifact_offload_storage_mode
        if force_sandbox_for_auto and storage_mode == "auto":
            storage_mode = "sandbox"

        turn_key = _current_turn_key(injected_state)
        current_turn_id = str(
            injected_state.get("active_turn_id") or injected_state.get("turn_id") or ""
        ).strip()
        tool_call_index = _tool_call_name_index(normalized_messages)
        seen_source_ids: set[str] = set()
        seen_digests: set[str] = set()
        new_entries: list[dict[str, Any]] = []

        for message in reversed(normalized_messages):
            tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            normalized_tool_name = str(tool_name or "").strip().lower()
            if (
                not normalized_tool_name
                or normalized_tool_name in _ARTIFACT_INTERNAL_TOOL_NAMES
            ):
                continue
            payload = _safe_json(getattr(message, "content", ""))
            if not payload:
                continue
            serialized_payload = _serialize_artifact_payload(payload)
            if len(serialized_payload) < int(artifact_offload_threshold_chars):
                continue
            content_sha1 = hashlib.sha1(
                serialized_payload.encode("utf-8", errors="ignore")
            ).hexdigest()
            source_id = str(getattr(message, "tool_call_id", "") or "").strip()
            if not source_id:
                source_id = f"{normalized_tool_name}:{content_sha1[:14]}"
            if source_id in seen_source_ids or content_sha1 in seen_digests:
                continue

            artifact_seed = "|".join(
                [
                    str(thread_id or "thread"),
                    current_turn_id or turn_key or "turn",
                    source_id,
                    content_sha1[:16],
                ]
            )
            artifact_id = (
                "art-"
                + hashlib.sha1(
                    artifact_seed.encode("utf-8", errors="ignore")
                ).hexdigest()[:16]
            )
            artifact_uri, artifact_path, storage_backend = _persist_artifact_content(
                artifact_id=artifact_id,
                content=serialized_payload,
                thread_id=thread_id,
                turn_key=turn_key,
                sandbox_enabled=bool(sandbox_enabled),
                artifact_storage_mode=storage_mode,
                runtime_hitl_cfg=runtime_hitl_cfg,
                subagent_id=subagent_id,
            )
            summary = _summarize_tool_payload(normalized_tool_name, payload)
            new_entries.append(
                {
                    "id": artifact_id,
                    "artifact_uri": artifact_uri,
                    "artifact_path": artifact_path,
                    "storage_backend": storage_backend,
                    "tool": normalized_tool_name,
                    "source_id": source_id,
                    "turn_id": current_turn_id or None,
                    "summary": _truncate_for_prompt(summary, 220),
                    "size_bytes": len(serialized_payload.encode("utf-8")),
                    "content_sha1": content_sha1,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            seen_source_ids.add(source_id)
            seen_digests.add(content_sha1)
            if len(new_entries) >= _ARTIFACT_OFFLOAD_PER_PASS_LIMIT:
                break
        return new_entries

    @tool
    async def call_agent(
        agent_name: str,
        task: str,
        final: bool = False,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Call a specialized agent with a task."""
        injected_state = state or {}
        latest_turn_query = _latest_user_query(injected_state.get("messages") or [])
        requested_name = (agent_name or "").strip().lower()
        resolved_name, resolution_reason = _resolve_agent_name(
            requested_name,
            task=task,
            state=injected_state,
        )
        name = resolved_name or requested_name
        current_turn_id = str(
            injected_state.get("active_turn_id") or injected_state.get("turn_id") or ""
        ).strip()
        execution_strategy = (
            str(injected_state.get("execution_strategy") or "").strip().lower()
        )
        subagent_isolated = _subagent_isolation_active(execution_strategy)
        turn_key = _current_turn_key(injected_state)
        base_thread_id = str(dependencies.get("thread_id") or "thread")
        subagent_id = (
            _build_subagent_id(
                base_thread_id=base_thread_id,
                turn_key=turn_key,
                agent_name=name,
                call_index=0,
                task=task,
            )
            if subagent_isolated
            else None
        )
        execution_timeout_seconds = get_execution_timeout_seconds(execution_strategy)
        filesystem_task = _is_filesystem_task(name, task)
        if filesystem_task and not sandbox_enabled:
            error_message = (
                "Sandbox is disabled for this runtime. Enable "
                "runtime_hitl.sandbox_enabled=true and set sandbox_mode "
                "to provisioner or docker."
            )
            result_contract = _build_agent_result_contract(
                agent_name=name,
                task=task,
                response_text="",
                error_text=error_message,
                used_tools=[],
                final_requested=bool(final),
            )
            return json.dumps(
                {
                    "agent": name,
                    "requested_agent": requested_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "error": error_message,
                    "error_type": "SandboxDisabledError",
                    "result_contract": result_contract,
                    "final": bool(final),
                    "turn_id": current_turn_id,
                    "execution_strategy": execution_strategy or "inline",
                    "subagent_isolated": bool(subagent_isolated),
                    "subagent_id": subagent_id,
                    "subagent_handoff": (
                        _build_subagent_handoff_payload(
                            subagent_id=str(subagent_id or ""),
                            agent_name=name,
                            response_text="",
                            result_contract=result_contract,
                            result_max_chars=subagent_result_max_chars,
                            error_text=error_message,
                        )
                        if subagent_isolated and subagent_id
                        else None
                    ),
                },
                ensure_ascii=True,
            )
        worker = await worker_pool.get(name)
        if not worker:
            error_message = f"Agent '{agent_name}' not available."
            return json.dumps(
                {
                    "agent": name,
                    "requested_agent": requested_name,
                    "agent_resolution": resolution_reason,
                    "error": error_message,
                    "result_contract": _build_agent_result_contract(
                        agent_name=name,
                        task=task,
                        response_text="",
                        error_text=error_message,
                        used_tools=[],
                        final_requested=bool(final),
                    ),
                    "turn_id": current_turn_id,
                    "execution_strategy": execution_strategy or "inline",
                    "subagent_isolated": bool(subagent_isolated),
                    "subagent_id": subagent_id,
                    "subagent_handoff": (
                        _build_subagent_handoff_payload(
                            subagent_id=str(subagent_id or ""),
                            agent_name=name,
                            response_text="",
                            result_contract=_build_agent_result_contract(
                                agent_name=name,
                                task=task,
                                response_text="",
                                error_text=error_message,
                                used_tools=[],
                                final_requested=bool(final),
                            ),
                            result_max_chars=subagent_result_max_chars,
                            error_text=error_message,
                        )
                        if subagent_isolated and subagent_id
                        else None
                    ),
                },
                ensure_ascii=True,
            )
        if name in {"syntes", "synthesis"} and injected_state:
            task = _prepare_task_for_synthesis(task, injected_state)
        task_for_worker = task
        if subagent_isolated and subagent_id:
            task_for_worker = _build_subagent_task(
                task=task,
                state=injected_state,
                subagent_id=subagent_id,
                agent_name=name,
            )
        resolved_tools_map = injected_state.get("resolved_tools_by_agent")
        selected_tool_ids: list[str] = []
        tool_selection_meta: dict[str, Any] = {}
        if isinstance(resolved_tools_map, dict):
            candidate_tools = resolved_tools_map.get(name) or resolved_tools_map.get(
                requested_name
            )
            if isinstance(candidate_tools, list):
                selected_tool_ids = [
                    str(tool_id).strip()
                    for tool_id in candidate_tools
                    if str(tool_id).strip()
                ][:8]
        if not selected_tool_ids:
            tool_selection_meta = _resolve_live_tool_selection_for_agent(
                name,
                task,
                state=injected_state,
            )
            selected_tool_ids = [
                str(tool_id).strip()
                for tool_id in list(tool_selection_meta.get("selected_tool_ids") or [])
                if str(tool_id).strip()
            ][:8]
        live_tool_gate_active = _live_phase_enabled(live_routing_config, "tool_gate")
        if name in {"väder", "weather"}:
            if live_tool_gate_active:
                selected_tool_ids = [
                    tool_id
                    for tool_id in selected_tool_ids
                    if tool_id in weather_tool_ids
                ]
                if not selected_tool_ids:
                    selected_tool_ids = list(weather_tool_ids)
            else:
                selected_tool_ids = list(weather_tool_ids)
        elif name == "väder-vatten":
            selected_tool_ids = list(smhi_hydro_ids)
        elif name == "väder-risk":
            selected_tool_ids = list(smhi_risk_ids)
        if name.startswith("trafik-"):
            selected_tool_ids = [
                tool_id for tool_id in selected_tool_ids if tool_id in trafik_tool_ids
            ]
            if not selected_tool_ids:
                selected_tool_ids = list(trafik_tool_ids)
        # Statistik agents always need scb_validate + scb_fetch for the
        # catalog → validate → fetch pipeline (bigtool agent internal tools).
        if name.startswith("statistik"):
            for pid in ("scb_validate", "scb_fetch"):
                if pid not in selected_tool_ids:
                    selected_tool_ids.append(pid)
        selected_tool_ids = _prioritize_sandbox_code_tools(
            selected_tool_ids,
            agent_name=name,
            task=task,
            limit=8,
        )
        fallback_tool_ids: list[str] = []
        if name in {"väder", "weather"}:
            fallback_tool_ids = list(weather_tool_ids)
        elif name == "väder-vatten":
            fallback_tool_ids = list(smhi_hydro_ids)
        elif name == "väder-risk":
            fallback_tool_ids = list(smhi_risk_ids)
        elif name.startswith("trafik-"):
            fallback_tool_ids = list(trafik_tool_ids)
        selected_tool_ids = _sanitize_selected_tool_ids_for_worker(
            worker,
            selected_tool_ids,
            fallback_tool_ids=fallback_tool_ids,
            limit=8,
        )
        if _live_phase_enabled(live_routing_config, "shadow"):
            logger.info(
                "live-routing tool-selection phase=%s agent=%s mode=%s top1=%s top2=%s margin=%s selected=%s",
                live_routing_config.get("phase"),
                name,
                str(tool_selection_meta.get("mode") or "resolved"),
                str(tool_selection_meta.get("top1") or ""),
                str(tool_selection_meta.get("top2") or ""),
                tool_selection_meta.get("margin"),
                ",".join(selected_tool_ids[:5]),
            )
        filesystem_sandbox_task = _is_filesystem_sandbox_task(name, task)
        explicit_file_read_requested = filesystem_sandbox_task and (
            _requires_explicit_file_read(task)
            or _requires_explicit_file_read(latest_turn_query)
        )
        speculative_response, speculative_tools, speculative_payloads = (
            ("", [], [])
            if filesystem_sandbox_task
            else _collect_speculative_response(
                selected_tool_ids=selected_tool_ids,
                state=injected_state,
            )
        )
        if speculative_response:
            result_contract = _build_agent_result_contract(
                agent_name=name,
                task=task,
                response_text=speculative_response,
                used_tools=speculative_tools,
                final_requested=bool(final),
            )
            output_response = speculative_response
            if not final:
                output_response = compress_response(output_response, agent_name=name)
            if subagent_isolated:
                output_response = _truncate_for_prompt(
                    output_response,
                    subagent_result_max_chars,
                )
            subagent_handoff = (
                _build_subagent_handoff_payload(
                    subagent_id=str(subagent_id or ""),
                    agent_name=name,
                    response_text=speculative_response,
                    result_contract=result_contract,
                    result_max_chars=subagent_result_max_chars,
                )
                if subagent_isolated and subagent_id
                else None
            )
            return json.dumps(
                {
                    "agent": name,
                    "requested_agent": requested_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "response": output_response,
                    "used_tools": speculative_tools,
                    "result_contract": result_contract,
                    "critic": {
                        "status": "cached",
                        "reason": "speculative_reuse_hit",
                        "sources": len(speculative_payloads),
                    },
                    "final": bool(final),
                    "turn_id": current_turn_id,
                    "execution_strategy": execution_strategy or "inline",
                    "from_speculative_cache": True,
                    "subagent_isolated": bool(subagent_isolated),
                    "subagent_id": subagent_id,
                    "subagent_handoff": subagent_handoff,
                },
                ensure_ascii=True,
            )
        memory_scope_id = (
            str(selected_tool_ids[0]).strip()
            if selected_tool_ids
            else f"agent:{name or 'unknown'}"
        )
        cached_payload = (
            None
            if filesystem_sandbox_task
            else episodic_store.get(
                tool_id=memory_scope_id,
                query=task,
            )
        )
        if isinstance(cached_payload, dict):
            cached_response = _strip_critic_json(
                str(cached_payload.get("response") or "").strip()
            )
            if cached_response:
                cached_used_tools_raw = cached_payload.get("used_tools")
                cached_used_tools = (
                    [
                        str(item).strip()
                        for item in cached_used_tools_raw
                        if str(item).strip()
                    ][:8]
                    if isinstance(cached_used_tools_raw, list)
                    else []
                )
                cached_contract = cached_payload.get("result_contract")
                if not isinstance(cached_contract, dict):
                    cached_contract = _build_agent_result_contract(
                        agent_name=name,
                        task=task,
                        response_text=cached_response,
                        used_tools=cached_used_tools,
                        final_requested=bool(final),
                    )
                output_response = cached_response
                if not final:
                    output_response = compress_response(
                        output_response, agent_name=name
                    )
                if subagent_isolated:
                    output_response = _truncate_for_prompt(
                        output_response,
                        subagent_result_max_chars,
                    )
                subagent_handoff = (
                    _build_subagent_handoff_payload(
                        subagent_id=str(subagent_id or ""),
                        agent_name=name,
                        response_text=cached_response,
                        result_contract=cached_contract,
                        result_max_chars=subagent_result_max_chars,
                    )
                    if subagent_isolated and subagent_id
                    else None
                )
                return json.dumps(
                    {
                        "agent": name,
                        "requested_agent": requested_name,
                        "agent_resolution": resolution_reason,
                        "task": task,
                        "response": output_response,
                        "used_tools": cached_used_tools,
                        "result_contract": cached_contract,
                        "critic": {
                            "status": "cached",
                            "reason": "episodic_memory_hit",
                        },
                        "final": bool(final),
                        "turn_id": current_turn_id,
                        "execution_strategy": execution_strategy or "inline",
                        "from_speculative_cache": False,
                        "from_episodic_cache": True,
                        "subagent_isolated": bool(subagent_isolated),
                        "subagent_id": subagent_id,
                        "subagent_handoff": subagent_handoff,
                    },
                    ensure_ascii=True,
                )
        prompt = worker_prompts.get(name, "")
        scoped_prompt = _build_scoped_prompt_for_agent(
            name,
            task,
            prompt_template=scoped_tool_prompt_template,
        )
        if scoped_prompt:
            prompt = (
                f"{prompt.rstrip()}\n\n{scoped_prompt}".strip()
                if prompt
                else scoped_prompt
            )
        tool_prompt_block = _build_tool_prompt_block(
            selected_tool_ids,
            tool_prompt_overrides,
            max_tools=2,
            default_prompt_template=tool_default_prompt_template,
        )
        if tool_prompt_block:
            prompt = (
                f"{prompt.rstrip()}\n\n{tool_prompt_block}".strip()
                if prompt
                else tool_prompt_block
            )
        # --- Domain fan-out: pre-fetch data in parallel ---
        fan_out_context = ""
        if is_fan_out_enabled(name) and not filesystem_sandbox_task:
            try:
                fan_out_results = await execute_domain_fan_out(
                    agent_name=name,
                    query=task,
                    tool_registry=_tool_registry_for_fan_out,
                )
                fan_out_context = format_fan_out_context(fan_out_results)
            except Exception as fan_out_exc:
                logger.warning(
                    "domain-fan-out failed for agent=%s: %s",
                    name,
                    fan_out_exc,
                )
        if fan_out_context:
            prompt = (
                f"{prompt.rstrip()}\n\n{fan_out_context}".strip()
                if prompt
                else fan_out_context
            )
        messages = []
        if prompt:
            messages.append(SystemMessage(content=prompt))
        messages.append(HumanMessage(content=task_for_worker))
        worker_state = _build_subagent_worker_state(
            base_messages=messages,
            selected_tool_ids=selected_tool_ids,
            isolated=subagent_isolated,
            subagent_id=subagent_id,
        )
        worker_checkpoint_ns = str(dependencies.get("checkpoint_ns") or "").strip()
        worker_thread_id = f"{base_thread_id}:{name}:{turn_key}"
        if subagent_isolated and subagent_id:
            worker_thread_id = f"{worker_thread_id}:{subagent_id}"
        worker_configurable = {"thread_id": worker_thread_id}
        if worker_checkpoint_ns:
            if subagent_isolated and subagent_id:
                worker_configurable["checkpoint_ns"] = (
                    f"{worker_checkpoint_ns}:subagent:{name}:{subagent_id}"
                )
            else:
                worker_configurable["checkpoint_ns"] = (
                    f"{worker_checkpoint_ns}:worker:{name}"
                )
        config = {
            "configurable": worker_configurable,
            "recursion_limit": 12,
        }
        try:
            result = await asyncio.wait_for(
                worker.ainvoke(worker_state, config=config),
                timeout=float(execution_timeout_seconds),
            )
        except TimeoutError:
            error_message = (
                f"Agent '{name}' timed out after {int(execution_timeout_seconds)}s."
            )
            return json.dumps(
                {
                    "agent": name,
                    "requested_agent": requested_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "error": error_message,
                    "error_type": "TimeoutError",
                    "result_contract": _build_agent_result_contract(
                        agent_name=name,
                        task=task,
                        response_text="",
                        error_text=error_message,
                        used_tools=[],
                        final_requested=bool(final),
                    ),
                    "final": bool(final),
                    "turn_id": current_turn_id,
                    "execution_strategy": execution_strategy or "inline",
                    "subagent_isolated": bool(subagent_isolated),
                    "subagent_id": subagent_id,
                    "subagent_handoff": (
                        _build_subagent_handoff_payload(
                            subagent_id=str(subagent_id or ""),
                            agent_name=name,
                            response_text="",
                            result_contract=_build_agent_result_contract(
                                agent_name=name,
                                task=task,
                                response_text="",
                                error_text=error_message,
                                used_tools=[],
                                final_requested=bool(final),
                            ),
                            result_max_chars=subagent_result_max_chars,
                            error_text=error_message,
                        )
                        if subagent_isolated and subagent_id
                        else None
                    ),
                },
                ensure_ascii=True,
            )
        except Exception as exc:
            error_message = str(exc)
            return json.dumps(
                {
                    "agent": name,
                    "requested_agent": requested_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "error": error_message,
                    "error_type": type(exc).__name__,
                    "result_contract": _build_agent_result_contract(
                        agent_name=name,
                        task=task,
                        response_text="",
                        error_text=error_message,
                        used_tools=[],
                        final_requested=bool(final),
                    ),
                    "final": bool(final),
                    "turn_id": current_turn_id,
                    "execution_strategy": execution_strategy or "inline",
                    "subagent_isolated": bool(subagent_isolated),
                    "subagent_id": subagent_id,
                    "subagent_handoff": (
                        _build_subagent_handoff_payload(
                            subagent_id=str(subagent_id or ""),
                            agent_name=name,
                            response_text="",
                            result_contract=_build_agent_result_contract(
                                agent_name=name,
                                task=task,
                                response_text="",
                                error_text=error_message,
                                used_tools=[],
                                final_requested=bool(final),
                            ),
                            result_max_chars=subagent_result_max_chars,
                            error_text=error_message,
                        )
                        if subagent_isolated and subagent_id
                        else None
                    ),
                },
                ensure_ascii=True,
            )
        response_text = ""
        messages_out: list[Any] = []
        if isinstance(result, dict):
            messages_out = result.get("messages") or []
            if messages_out:
                response_text = str(getattr(messages_out[-1], "content", "") or "")
            # Fallback: if the bigtool worker returned empty text but there
            # are ToolMessages with real data, extract the last ToolMessage
            # content so we don't lose the tool results entirely.
            if not response_text.strip():
                for msg in reversed(messages_out):
                    if isinstance(msg, ToolMessage):
                        tool_content = str(getattr(msg, "content", "") or "").strip()
                        if tool_content and len(tool_content) > 10:
                            response_text = tool_content
                            break
            initial_tool_names = _tool_names_from_messages(messages_out)
            enforcement_message: str | None = None
            if name.startswith("trafik-"):
                used_trafik_tool = any(
                    tool_name.startswith("trafikverket_")
                    or tool_name.startswith("trafiklab_")
                    for tool_name in initial_tool_names
                )
                if not used_trafik_tool:
                    enforcement_message = trafik_enforcement_message
            elif filesystem_sandbox_task and not _uses_sandbox_tool(initial_tool_names):
                enforcement_message = code_sandbox_enforcement_message
            elif (
                filesystem_sandbox_task
                and explicit_file_read_requested
                and "sandbox_read_file" not in initial_tool_names
            ):
                enforcement_message = (
                    f"{code_sandbox_enforcement_message}\n\n"
                    f"{code_read_file_enforcement_message}"
                )
            if enforcement_message:
                enforced_prompt = (
                    f"{prompt.rstrip()}\n\n{enforcement_message}".strip()
                    if prompt
                    else enforcement_message
                )
                enforced_messages = [
                    SystemMessage(content=enforced_prompt),
                    HumanMessage(content=task_for_worker),
                ]
                retry_state = _build_subagent_worker_state(
                    base_messages=enforced_messages,
                    selected_tool_ids=selected_tool_ids,
                    isolated=subagent_isolated,
                    subagent_id=subagent_id,
                )
                try:
                    result = await asyncio.wait_for(
                        worker.ainvoke(retry_state, config=config),
                        timeout=float(execution_timeout_seconds),
                    )
                except TimeoutError:
                    error_message = (
                        f"Agent '{name}' retry timed out after "
                        f"{int(execution_timeout_seconds)}s."
                    )
                    return json.dumps(
                        {
                            "agent": name,
                            "requested_agent": requested_name,
                            "agent_resolution": resolution_reason,
                            "task": task,
                            "error": error_message,
                            "error_type": "TimeoutError",
                            "result_contract": _build_agent_result_contract(
                                agent_name=name,
                                task=task,
                                response_text="",
                                error_text=error_message,
                                used_tools=[],
                                final_requested=bool(final),
                            ),
                            "final": bool(final),
                            "turn_id": current_turn_id,
                            "execution_strategy": execution_strategy or "inline",
                            "subagent_isolated": bool(subagent_isolated),
                            "subagent_id": subagent_id,
                            "subagent_handoff": (
                                _build_subagent_handoff_payload(
                                    subagent_id=str(subagent_id or ""),
                                    agent_name=name,
                                    response_text="",
                                    result_contract=_build_agent_result_contract(
                                        agent_name=name,
                                        task=task,
                                        response_text="",
                                        error_text=error_message,
                                        used_tools=[],
                                        final_requested=bool(final),
                                    ),
                                    result_max_chars=subagent_result_max_chars,
                                    error_text=error_message,
                                )
                                if subagent_isolated and subagent_id
                                else None
                            ),
                        },
                        ensure_ascii=True,
                    )
                if isinstance(result, dict):
                    messages_out = result.get("messages") or []
                    if messages_out:
                        response_text = str(
                            getattr(messages_out[-1], "content", "") or ""
                        )
        if not response_text:
            response_text = str(result)
        # Strip leaked <tool_call> XML text — the LLM emitted tool calls as
        # text instead of structured tool_calls.  Never propagate raw XML.
        if "<tool_call>" in response_text:
            response_text = re.sub(
                r"<tool_call>.*?</tool_call>",
                "",
                response_text,
                flags=re.DOTALL | re.IGNORECASE,
            ).strip()
        used_tool_names = _tool_names_from_messages(messages_out)
        explicit_file_read_required = bool(explicit_file_read_requested)
        used_explicit_read_tool = "sandbox_read_file" in used_tool_names
        if (
            explicit_file_read_required
            and not used_explicit_read_tool
            and _looks_filesystem_not_found_response(response_text)
            and _uses_sandbox_tool(used_tool_names)
        ):
            # Reading may be impossible when the target path genuinely does not exist.
            explicit_file_read_required = False
        subagent_artifacts = _collect_subagent_artifacts_from_messages(
            messages_out=messages_out,
            injected_state=injected_state,
            force_sandbox_for_auto=(filesystem_sandbox_task or subagent_isolated),
            subagent_id=subagent_id,
        )
        if filesystem_sandbox_task and not _uses_sandbox_tool(used_tool_names):
            response_text = (
                "Kunde inte verifiera filsystemsandringen eftersom inga sandbox-verktyg anropades. "
                "Forsok igen med sandbox_write_file/sandbox_read_file aktiverade."
            )
        elif explicit_file_read_required and not used_explicit_read_tool:
            response_text = (
                "Uppgiften kraver explicit fillasning men sandbox_read_file anropades inte. "
                "Forsok igen och las filen innan slutsvaret."
            )

        critic_prompt = append_datetime_context(critic_prompt_template)
        critic_input = f"Uppgift: {task}\nSvar: {response_text}"
        try:
            critic_msg = await llm.ainvoke(
                [
                    SystemMessage(content=str(critic_prompt or "")),
                    HumanMessage(content=str(critic_input or "")),
                ]
            )
            critic_text = str(getattr(critic_msg, "content", "") or "").strip()
            critic_payload = _safe_json(critic_text)
            if not critic_payload:
                critic_payload = {"status": "ok", "reason": critic_text}
        except Exception as exc:  # pragma: no cover - defensive fallback
            critic_payload = {
                "status": "unavailable",
                "reason": f"critic_unavailable:{type(exc).__name__}",
            }

        response_text = _strip_critic_json(response_text)
        result_contract = _build_agent_result_contract(
            agent_name=name,
            task=task,
            response_text=response_text,
            used_tools=used_tool_names,
            final_requested=bool(final),
        )
        if filesystem_sandbox_task and not _uses_sandbox_tool(used_tool_names):
            result_contract.update(
                {
                    "status": "partial",
                    "actionable": False,
                    "retry_recommended": True,
                    "confidence": min(
                        float(result_contract.get("confidence") or 0.45),
                        0.45,
                    ),
                    "reason": (
                        "Filsystemsuppgift maste verifieras med sandbox-verktyg "
                        "(sandbox_write_file/sandbox_read_file)."
                    ),
                }
            )
        elif explicit_file_read_required and not used_explicit_read_tool:
            result_contract.update(
                {
                    "status": "partial",
                    "actionable": False,
                    "retry_recommended": True,
                    "confidence": min(
                        float(result_contract.get("confidence") or 0.45),
                        0.45,
                    ),
                    "reason": (
                        "Uppgiften kraver explicit fillasning med sandbox_read_file "
                        "innan svaret kan godkannas."
                    ),
                }
            )
        # Guard: if every data-bearing tool returned empty data ({}/[]),
        # the worker LLM has nothing to ground its answer on — downgrade
        # the contract to prevent hallucinated numbers from being finalized.
        if (
            not filesystem_sandbox_task
            and _all_tool_data_empty(messages_out)
            and str(result_contract.get("status") or "") == "success"
        ):
            result_contract.update(
                {
                    "status": "partial",
                    "actionable": False,
                    "retry_recommended": True,
                    "confidence": min(
                        float(result_contract.get("confidence") or 0.35),
                        0.35,
                    ),
                    "reason": (
                        "Alla verktyg returnerade tom data. "
                        "Svaret kan inte verifieras och bor inte finaliseras."
                    ),
                }
            )
            logger.warning(
                "LLM gate guard: all tool data empty for agent=%s tools=%s — "
                "downgrading contract to partial",
                name,
                ",".join(used_tool_names[:4]),
            )
        if _live_phase_enabled(live_routing_config, "shadow"):
            logger.info(
                "live-routing tool-outcome phase=%s agent=%s mode=%s predicted_top1=%s margin=%s worker_top1=%s used_count=%s",
                live_routing_config.get("phase"),
                name,
                str(tool_selection_meta.get("mode") or "resolved"),
                str(tool_selection_meta.get("top1") or ""),
                tool_selection_meta.get("margin"),
                (used_tool_names[0] if used_tool_names else ""),
                len(used_tool_names),
            )
        if (
            not filesystem_sandbox_task
            and str(result_contract.get("status") or "").strip().lower()
            in {
                "success",
                "partial",
            }
            and str(response_text).strip()
        ):
            episodic_store.put(
                tool_id=memory_scope_id,
                query=task,
                value={
                    "response": response_text,
                    "used_tools": used_tool_names,
                    "result_contract": result_contract,
                    "agent": name,
                },
                ttl_seconds=infer_ttl_seconds(
                    tool_id=memory_scope_id,
                    agent_name=name,
                ),
            )

        if subagent_artifacts:
            artifact_refs: list[str] = []
            for item in subagent_artifacts:
                if not isinstance(item, dict):
                    continue
                artifact_uri = str(item.get("artifact_uri") or "").strip()
                artifact_path = str(item.get("artifact_path") or "").strip()
                if artifact_uri:
                    artifact_refs.append(artifact_uri)
                if artifact_path.startswith("/workspace/"):
                    artifact_refs.append(artifact_path)
            deduped_refs: list[str] = []
            seen_refs: set[str] = set()
            for ref in artifact_refs:
                if not ref or ref in seen_refs:
                    continue
                seen_refs.add(ref)
                deduped_refs.append(ref)
                if len(deduped_refs) >= 4:
                    break
            if deduped_refs:
                reference_text = ", ".join(deduped_refs)
                response_text = (
                    f"{str(response_text or '').rstrip()}\n\n"
                    f"[artifact_offload] Full tool output saved: {reference_text}"
                ).strip()

        raw_response_text = response_text
        subagent_handoff = (
            _build_subagent_handoff_payload(
                subagent_id=str(subagent_id or ""),
                agent_name=name,
                response_text=raw_response_text,
                result_contract=result_contract,
                result_max_chars=subagent_result_max_chars,
            )
            if subagent_isolated and subagent_id
            else None
        )
        # Compress response for context efficiency when not final
        if not final:
            response_text = compress_response(response_text, agent_name=name)
        if subagent_isolated:
            response_text = _truncate_for_prompt(
                response_text, subagent_result_max_chars
            )

        return json.dumps(
            {
                "agent": name,
                "requested_agent": requested_name,
                "agent_resolution": resolution_reason,
                "task": task,
                "response": response_text,
                "used_tools": used_tool_names,
                "result_contract": result_contract,
                "critic": critic_payload,
                "final": bool(final),
                "turn_id": current_turn_id,
                "execution_strategy": execution_strategy or "inline",
                "from_speculative_cache": False,
                "from_episodic_cache": False,
                "subagent_isolated": bool(subagent_isolated),
                "subagent_id": subagent_id,
                "subagent_handoff": subagent_handoff,
                "artifacts": subagent_artifacts,
            },
            ensure_ascii=True,
        )

    @tool
    async def call_agents_parallel(
        calls: list[dict],
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Call multiple agents in parallel. Each call dict has 'agent' and 'task' keys.
        Use when tasks are independent and don't depend on each other's results.

        IMPORTANT: Use exact internal agent ids from retrieve_agents()."""
        injected_state = state or {}
        current_turn_id = str(
            injected_state.get("active_turn_id") or injected_state.get("turn_id") or ""
        ).strip()
        requested_strategy = (
            str(injected_state.get("execution_strategy") or "").strip().lower()
        )
        allow_parallel = (
            compare_mode
            or requested_strategy == "parallel"
            or (requested_strategy == "subagent" and subagent_enabled)
        )
        subagent_isolation_for_parallel = _subagent_isolation_active(requested_strategy)
        serialized_mode = not allow_parallel
        execution_timeout_seconds = get_execution_timeout_seconds(requested_strategy)
        dropped_calls = 0
        if serialized_mode and isinstance(calls, list) and len(calls) > 1:
            dropped_calls = len(calls) - 1
            calls = calls[:1]

        async def _run_one(call_spec: dict, *, call_index: int) -> dict:
            requested_agent_name = (call_spec.get("agent") or "").strip().lower()
            task = call_spec.get("task") or ""
            resolved_agent_name, resolution_reason = _resolve_agent_name(
                requested_agent_name,
                task=task,
                state=injected_state,
            )
            agent_name = resolved_agent_name or requested_agent_name
            turn_key = _current_turn_key(injected_state)
            base_thread_id = str(dependencies.get("thread_id") or "thread")
            subagent_id = (
                _build_subagent_id(
                    base_thread_id=base_thread_id,
                    turn_key=turn_key,
                    agent_name=agent_name,
                    call_index=call_index,
                    task=task,
                )
                if subagent_isolation_for_parallel
                else None
            )
            filesystem_task = _is_filesystem_task(agent_name, task)
            if filesystem_task and not sandbox_enabled:
                error_message = (
                    "Sandbox is disabled for this runtime. Enable "
                    "runtime_hitl.sandbox_enabled=true and set sandbox_mode "
                    "to provisioner or docker."
                )
                result_contract = _build_agent_result_contract(
                    agent_name=agent_name,
                    task=task,
                    response_text="",
                    error_text=error_message,
                    used_tools=[],
                    final_requested=False,
                )
                return {
                    "agent": agent_name,
                    "requested_agent": requested_agent_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "error": error_message,
                    "error_type": "SandboxDisabledError",
                    "result_contract": result_contract,
                    "turn_id": current_turn_id,
                    "execution_strategy": requested_strategy or "inline",
                    "subagent_isolated": bool(subagent_isolation_for_parallel),
                    "subagent_id": subagent_id,
                    "subagent_handoff": (
                        _build_subagent_handoff_payload(
                            subagent_id=str(subagent_id or ""),
                            agent_name=agent_name,
                            response_text="",
                            result_contract=result_contract,
                            result_max_chars=subagent_result_max_chars,
                            error_text=error_message,
                        )
                        if subagent_isolation_for_parallel and subagent_id
                        else None
                    ),
                }
            worker = await worker_pool.get(agent_name)
            if not worker:
                error_message = f"Agent '{agent_name}' not available."
                result_contract = _build_agent_result_contract(
                    agent_name=agent_name,
                    task=task,
                    response_text="",
                    error_text=error_message,
                    used_tools=[],
                    final_requested=False,
                )
                return {
                    "agent": agent_name,
                    "requested_agent": requested_agent_name,
                    "agent_resolution": resolution_reason,
                    "error": error_message,
                    "result_contract": result_contract,
                    "turn_id": current_turn_id,
                    "subagent_isolated": bool(subagent_isolation_for_parallel),
                    "subagent_id": subagent_id,
                    "subagent_handoff": (
                        _build_subagent_handoff_payload(
                            subagent_id=str(subagent_id or ""),
                            agent_name=agent_name,
                            response_text="",
                            result_contract=result_contract,
                            result_max_chars=subagent_result_max_chars,
                            error_text=error_message,
                        )
                        if subagent_isolation_for_parallel and subagent_id
                        else None
                    ),
                }
            try:
                # Reuse same worker invocation logic as call_agent
                if agent_name in {"syntes", "synthesis"} and injected_state:
                    task = _prepare_task_for_synthesis(task, injected_state)
                task_for_worker = task
                if subagent_isolation_for_parallel and subagent_id:
                    task_for_worker = _build_subagent_task(
                        task=task,
                        state=injected_state,
                        subagent_id=subagent_id,
                        agent_name=agent_name,
                    )
                resolved_tools_map = injected_state.get("resolved_tools_by_agent")
                selected_tool_ids: list[str] = []
                tool_selection_meta: dict[str, Any] = {}
                if isinstance(resolved_tools_map, dict):
                    candidate_tools = resolved_tools_map.get(
                        agent_name
                    ) or resolved_tools_map.get(requested_agent_name)
                    if isinstance(candidate_tools, list):
                        selected_tool_ids = [
                            str(tool_id).strip()
                            for tool_id in candidate_tools
                            if str(tool_id).strip()
                        ][:8]
                if not selected_tool_ids:
                    tool_selection_meta = _resolve_live_tool_selection_for_agent(
                        agent_name,
                        task,
                        state=injected_state,
                    )
                    selected_tool_ids = [
                        str(tool_id).strip()
                        for tool_id in list(
                            tool_selection_meta.get("selected_tool_ids") or []
                        )
                        if str(tool_id).strip()
                    ][:8]
                if not selected_tool_ids:
                    selected_tool_ids = _focused_tool_ids_for_agent(
                        agent_name,
                        task,
                        limit=6,
                    )
                live_tool_gate_active = _live_phase_enabled(
                    live_routing_config, "tool_gate"
                )
                if agent_name in {"väder", "weather"}:
                    if live_tool_gate_active:
                        selected_tool_ids = [
                            tool_id
                            for tool_id in selected_tool_ids
                            if tool_id in weather_tool_ids
                        ]
                        if not selected_tool_ids:
                            selected_tool_ids = list(weather_tool_ids)
                    else:
                        selected_tool_ids = list(weather_tool_ids)
                elif agent_name == "väder-vatten":
                    selected_tool_ids = list(smhi_hydro_ids)
                elif agent_name == "väder-risk":
                    selected_tool_ids = list(smhi_risk_ids)
                if agent_name.startswith("trafik-"):
                    selected_tool_ids = [
                        tool_id
                        for tool_id in selected_tool_ids
                        if tool_id in trafik_tool_ids
                    ]
                    if not selected_tool_ids:
                        selected_tool_ids = list(trafik_tool_ids)
                selected_tool_ids = _prioritize_sandbox_code_tools(
                    selected_tool_ids,
                    agent_name=agent_name,
                    task=task,
                    limit=8,
                )
                fallback_tool_ids: list[str] = []
                if agent_name in {"väder", "weather"}:
                    fallback_tool_ids = list(weather_tool_ids)
                elif agent_name == "väder-vatten":
                    fallback_tool_ids = list(smhi_hydro_ids)
                elif agent_name == "väder-risk":
                    fallback_tool_ids = list(smhi_risk_ids)
                elif agent_name.startswith("trafik-"):
                    fallback_tool_ids = list(trafik_tool_ids)
                selected_tool_ids = _sanitize_selected_tool_ids_for_worker(
                    worker,
                    selected_tool_ids,
                    fallback_tool_ids=fallback_tool_ids,
                    limit=8,
                )
                if _live_phase_enabled(live_routing_config, "shadow"):
                    logger.info(
                        "live-routing tool-selection phase=%s agent=%s mode=%s top1=%s top2=%s margin=%s selected=%s",
                        live_routing_config.get("phase"),
                        agent_name,
                        str(tool_selection_meta.get("mode") or "resolved"),
                        str(tool_selection_meta.get("top1") or ""),
                        str(tool_selection_meta.get("top2") or ""),
                        tool_selection_meta.get("margin"),
                        ",".join(selected_tool_ids[:5]),
                    )
                filesystem_sandbox_task = _is_filesystem_sandbox_task(agent_name, task)
                (
                    speculative_response,
                    speculative_tools,
                    speculative_payloads,
                ) = (
                    ("", [], [])
                    if filesystem_sandbox_task
                    else _collect_speculative_response(
                        selected_tool_ids=selected_tool_ids,
                        state=injected_state,
                    )
                )
                if speculative_response:
                    result_contract = _build_agent_result_contract(
                        agent_name=agent_name,
                        task=task,
                        response_text=speculative_response,
                        used_tools=speculative_tools,
                        final_requested=False,
                    )
                    response_value = speculative_response
                    if subagent_isolation_for_parallel:
                        response_value = _truncate_for_prompt(
                            response_value,
                            subagent_result_max_chars,
                        )
                    return {
                        "agent": agent_name,
                        "requested_agent": requested_agent_name,
                        "agent_resolution": resolution_reason,
                        "task": task,
                        "response": response_value,
                        "used_tools": speculative_tools,
                        "result_contract": result_contract,
                        "turn_id": current_turn_id,
                        "execution_strategy": requested_strategy or "inline",
                        "from_speculative_cache": True,
                        "speculative_source_count": len(speculative_payloads),
                        "subagent_isolated": bool(subagent_isolation_for_parallel),
                        "subagent_id": subagent_id,
                        "subagent_handoff": (
                            _build_subagent_handoff_payload(
                                subagent_id=str(subagent_id or ""),
                                agent_name=agent_name,
                                response_text=speculative_response,
                                result_contract=result_contract,
                                result_max_chars=subagent_result_max_chars,
                            )
                            if subagent_isolation_for_parallel and subagent_id
                            else None
                        ),
                    }
                memory_scope_id = (
                    str(selected_tool_ids[0]).strip()
                    if selected_tool_ids
                    else f"agent:{agent_name or 'unknown'}"
                )
                cached_payload = (
                    None
                    if filesystem_sandbox_task
                    else episodic_store.get(
                        tool_id=memory_scope_id,
                        query=task,
                    )
                )
                if isinstance(cached_payload, dict):
                    cached_response = _strip_critic_json(
                        str(cached_payload.get("response") or "").strip()
                    )
                    if cached_response:
                        cached_used_tools_raw = cached_payload.get("used_tools")
                        cached_used_tools = (
                            [
                                str(item).strip()
                                for item in cached_used_tools_raw
                                if str(item).strip()
                            ][:8]
                            if isinstance(cached_used_tools_raw, list)
                            else []
                        )
                        cached_contract = cached_payload.get("result_contract")
                        if not isinstance(cached_contract, dict):
                            cached_contract = _build_agent_result_contract(
                                agent_name=agent_name,
                                task=task,
                                response_text=cached_response,
                                used_tools=cached_used_tools,
                                final_requested=False,
                            )
                        return {
                            "agent": agent_name,
                            "requested_agent": requested_agent_name,
                            "agent_resolution": resolution_reason,
                            "task": task,
                            "response": (
                                _truncate_for_prompt(
                                    cached_response,
                                    subagent_result_max_chars,
                                )
                                if subagent_isolation_for_parallel
                                else cached_response
                            ),
                            "used_tools": cached_used_tools,
                            "result_contract": cached_contract,
                            "turn_id": current_turn_id,
                            "execution_strategy": requested_strategy or "inline",
                            "from_speculative_cache": False,
                            "from_episodic_cache": True,
                            "subagent_isolated": bool(subagent_isolation_for_parallel),
                            "subagent_id": subagent_id,
                            "subagent_handoff": (
                                _build_subagent_handoff_payload(
                                    subagent_id=str(subagent_id or ""),
                                    agent_name=agent_name,
                                    response_text=cached_response,
                                    result_contract=cached_contract,
                                    result_max_chars=subagent_result_max_chars,
                                )
                                if subagent_isolation_for_parallel and subagent_id
                                else None
                            ),
                        }
                prompt = worker_prompts.get(agent_name, "")
                scoped_prompt = _build_scoped_prompt_for_agent(
                    agent_name,
                    task,
                    prompt_template=scoped_tool_prompt_template,
                )
                if scoped_prompt:
                    prompt = (
                        f"{prompt.rstrip()}\n\n{scoped_prompt}".strip()
                        if prompt
                        else scoped_prompt
                    )
                tool_prompt_block = _build_tool_prompt_block(
                    selected_tool_ids,
                    tool_prompt_overrides,
                    max_tools=2,
                    default_prompt_template=tool_default_prompt_template,
                )
                if tool_prompt_block:
                    prompt = (
                        f"{prompt.rstrip()}\n\n{tool_prompt_block}".strip()
                        if prompt
                        else tool_prompt_block
                    )
                # --- Domain fan-out: pre-fetch data in parallel ---
                fan_out_context = ""
                if is_fan_out_enabled(agent_name) and not filesystem_sandbox_task:
                    try:
                        fan_out_results = await execute_domain_fan_out(
                            agent_name=agent_name,
                            query=task,
                            tool_registry=_tool_registry_for_fan_out,
                        )
                        fan_out_context = format_fan_out_context(fan_out_results)
                    except Exception as fan_out_exc:
                        logger.warning(
                            "domain-fan-out failed for agent=%s: %s",
                            agent_name,
                            fan_out_exc,
                        )
                if fan_out_context:
                    prompt = (
                        f"{prompt.rstrip()}\n\n{fan_out_context}".strip()
                        if prompt
                        else fan_out_context
                    )
                messages = []
                if prompt:
                    messages.append(SystemMessage(content=prompt))
                messages.append(HumanMessage(content=task_for_worker))
                worker_state = _build_subagent_worker_state(
                    base_messages=messages,
                    selected_tool_ids=selected_tool_ids,
                    isolated=subagent_isolation_for_parallel,
                    subagent_id=subagent_id,
                )
                worker_checkpoint_ns = str(
                    dependencies.get("checkpoint_ns") or ""
                ).strip()
                worker_thread_id = f"{base_thread_id}:{agent_name}:{turn_key}"
                if subagent_isolation_for_parallel and subagent_id:
                    worker_thread_id = f"{worker_thread_id}:{subagent_id}"
                worker_configurable = {"thread_id": worker_thread_id}
                if worker_checkpoint_ns:
                    if subagent_isolation_for_parallel and subagent_id:
                        worker_configurable["checkpoint_ns"] = (
                            f"{worker_checkpoint_ns}:subagent:{agent_name}:{subagent_id}"
                        )
                    else:
                        worker_configurable["checkpoint_ns"] = (
                            f"{worker_checkpoint_ns}:worker:{agent_name}"
                        )
                config = {
                    "configurable": worker_configurable,
                    "recursion_limit": 12,
                }
                try:
                    result = await asyncio.wait_for(
                        worker.ainvoke(worker_state, config=config),
                        timeout=float(execution_timeout_seconds),
                    )
                except TimeoutError:
                    error_message = (
                        f"Agent '{agent_name}' timed out after "
                        f"{int(execution_timeout_seconds)}s."
                    )
                    result_contract = _build_agent_result_contract(
                        agent_name=agent_name,
                        task=task,
                        response_text="",
                        error_text=error_message,
                        used_tools=[],
                        final_requested=False,
                    )
                    return {
                        "agent": agent_name,
                        "requested_agent": requested_agent_name,
                        "agent_resolution": resolution_reason,
                        "task": task,
                        "error": error_message,
                        "error_type": "TimeoutError",
                        "result_contract": result_contract,
                        "turn_id": current_turn_id,
                        "execution_strategy": requested_strategy or "inline",
                        "subagent_isolated": bool(subagent_isolation_for_parallel),
                        "subagent_id": subagent_id,
                        "subagent_handoff": (
                            _build_subagent_handoff_payload(
                                subagent_id=str(subagent_id or ""),
                                agent_name=agent_name,
                                response_text="",
                                result_contract=result_contract,
                                result_max_chars=subagent_result_max_chars,
                                error_text=error_message,
                            )
                            if subagent_isolation_for_parallel and subagent_id
                            else None
                        ),
                    }
                response_text = ""
                messages_out: list[Any] = []
                if isinstance(result, dict):
                    messages_out = result.get("messages") or []
                    if messages_out:
                        last_msg = messages_out[-1]
                        response_text = str(getattr(last_msg, "content", "") or "")
                if not response_text:
                    response_text = str(result)
                response_text = _strip_critic_json(response_text)
                used_tool_names = _tool_names_from_messages(messages_out)
                if filesystem_sandbox_task and not _uses_sandbox_tool(used_tool_names):
                    response_text = (
                        "Kunde inte verifiera filsystemsandringen eftersom inga sandbox-verktyg anropades. "
                        "Forsok igen med sandbox_write_file/sandbox_read_file aktiverade."
                    )
                result_contract = _build_agent_result_contract(
                    agent_name=agent_name,
                    task=task,
                    response_text=response_text,
                    used_tools=used_tool_names,
                    final_requested=False,
                )
                if filesystem_sandbox_task and not _uses_sandbox_tool(used_tool_names):
                    result_contract.update(
                        {
                            "status": "partial",
                            "actionable": False,
                            "retry_recommended": True,
                            "confidence": min(
                                float(result_contract.get("confidence") or 0.45),
                                0.45,
                            ),
                            "reason": (
                                "Filsystemsuppgift maste verifieras med sandbox-verktyg "
                                "(sandbox_write_file/sandbox_read_file)."
                            ),
                        }
                    )
                if _live_phase_enabled(live_routing_config, "shadow"):
                    logger.info(
                        "live-routing tool-outcome phase=%s agent=%s mode=%s predicted_top1=%s margin=%s worker_top1=%s used_count=%s",
                        live_routing_config.get("phase"),
                        agent_name,
                        str(tool_selection_meta.get("mode") or "resolved"),
                        str(tool_selection_meta.get("top1") or ""),
                        tool_selection_meta.get("margin"),
                        (used_tool_names[0] if used_tool_names else ""),
                        len(used_tool_names),
                    )
                if (
                    not filesystem_sandbox_task
                    and str(result_contract.get("status") or "").strip().lower()
                    in {
                        "success",
                        "partial",
                    }
                    and str(response_text).strip()
                ):
                    episodic_store.put(
                        tool_id=memory_scope_id,
                        query=task,
                        value={
                            "response": response_text,
                            "used_tools": used_tool_names,
                            "result_contract": result_contract,
                            "agent": agent_name,
                        },
                        ttl_seconds=infer_ttl_seconds(
                            tool_id=memory_scope_id,
                            agent_name=agent_name,
                        ),
                    )
                subagent_artifacts: list[dict[str, Any]] = []
                if subagent_isolation_for_parallel:
                    subagent_artifacts = _collect_subagent_artifacts_from_messages(
                        messages_out=messages_out,
                        injected_state=injected_state,
                        force_sandbox_for_auto=True,
                        subagent_id=subagent_id,
                    )
                subagent_handoff = (
                    _build_subagent_handoff_payload(
                        subagent_id=str(subagent_id or ""),
                        agent_name=agent_name,
                        response_text=response_text,
                        result_contract=result_contract,
                        result_max_chars=subagent_result_max_chars,
                    )
                    if subagent_isolation_for_parallel and subagent_id
                    else None
                )
                response_value = response_text
                if subagent_isolation_for_parallel:
                    response_value = _truncate_for_prompt(
                        response_text,
                        subagent_result_max_chars,
                    )
                return {
                    "agent": agent_name,
                    "requested_agent": requested_agent_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "response": response_value,
                    "used_tools": used_tool_names,
                    "result_contract": result_contract,
                    "turn_id": current_turn_id,
                    "execution_strategy": requested_strategy or "inline",
                    "from_speculative_cache": False,
                    "from_episodic_cache": False,
                    "subagent_isolated": bool(subagent_isolation_for_parallel),
                    "subagent_id": subagent_id,
                    "subagent_handoff": subagent_handoff,
                    "artifacts": subagent_artifacts,
                }
            except Exception as exc:
                error_message = str(exc)
                result_contract = _build_agent_result_contract(
                    agent_name=agent_name,
                    task=task,
                    response_text="",
                    error_text=error_message,
                    used_tools=[],
                    final_requested=False,
                )
                return {
                    "agent": agent_name,
                    "requested_agent": requested_agent_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "error": error_message,
                    "error_type": type(exc).__name__,
                    "result_contract": result_contract,
                    "turn_id": current_turn_id,
                    "execution_strategy": requested_strategy or "inline",
                    "subagent_isolated": bool(subagent_isolation_for_parallel),
                    "subagent_id": subagent_id,
                    "subagent_handoff": (
                        _build_subagent_handoff_payload(
                            subagent_id=str(subagent_id or ""),
                            agent_name=agent_name,
                            response_text="",
                            result_contract=result_contract,
                            result_max_chars=subagent_result_max_chars,
                            error_text=error_message,
                        )
                        if subagent_isolation_for_parallel and subagent_id
                        else None
                    ),
                }

        parallel_semaphore = asyncio.Semaphore(max(1, int(subagent_max_concurrency)))

        async def _run_with_guard(call_spec: dict, *, call_index: int) -> dict:
            if serialized_mode:
                return await _run_one(call_spec, call_index=call_index)
            async with parallel_semaphore:
                return await _run_one(call_spec, call_index=call_index)

        results = await asyncio.gather(
            *[
                _run_with_guard(call_spec, call_index=index)
                for index, call_spec in enumerate(calls)
            ],
            return_exceptions=True,
        )

        processed = []
        for r in results:
            if isinstance(r, Exception):
                processed.append({"error": str(r)})
            else:
                processed.append(r)

        return json.dumps(
            {
                "results": processed,
                "serialized_mode": serialized_mode,
                "dropped_calls": dropped_calls,
                "execution_strategy": requested_strategy or "inline",
                "subagent_enabled": bool(subagent_enabled),
                "subagent_isolation_enabled": bool(subagent_isolation_for_parallel),
                "subagent_max_concurrency": int(subagent_max_concurrency),
            },
            ensure_ascii=True,
        )

    tool_registry = {
        "retrieve_agents": retrieve_agents,
        "call_agent": call_agent,
        "call_agents_parallel": call_agents_parallel,
        "write_todos": create_write_todos_tool(),
        "reflect_on_progress": create_reflect_on_progress_tool(),
    }
    if compare_mode:
        for spec in EXTERNAL_MODEL_SPECS:
            tool_registry[spec.tool_name] = _build_compare_external_tool(spec)

    llm_with_tools = llm.bind_tools(
        _format_tools_for_llm_binding(list(tool_registry.values()))
    )
    tool_node = ToolNode(tool_registry.values())

    # Build domain-based candidates for the intent resolver when registry
    # is available.  This gives the LLM richer metadata (description,
    # keywords, label) for each candidate domain instead of just route→id.
    _registry_intent_candidates: list[dict[str, Any]] | None = None
    if graph_registry is not None:
        try:
            from app.services.intent_definition_service import (
                domains_to_intent_definitions,
            )

            _registry_intent_candidates = domains_to_intent_definitions(
                graph_registry.domains
            )
        except Exception:
            logger.debug("Failed to build registry intent candidates", exc_info=True)

    resolve_intent_node = build_intent_resolver_node(
        llm=llm,
        route_to_intent_id=route_to_intent_id,
        intent_resolver_prompt_template=intent_resolver_prompt_template,
        latest_user_query_fn=_latest_user_query,
        parse_hitl_confirmation_fn=_parse_hitl_confirmation,
        normalize_route_hint_fn=_normalize_route_hint_value,
        intent_from_route_fn=_intent_from_route,
        append_datetime_context_fn=append_datetime_context,
        extract_first_json_object_fn=_extract_first_json_object,
        coerce_confidence_fn=_coerce_confidence,
        classify_graph_complexity_fn=_classify_graph_complexity,
        build_speculative_candidates_fn=_build_speculative_candidates_for_intent,
        build_trivial_response_fn=_build_trivial_response_for_intent,
        route_default_agent_fn=_route_default_agent_for_intent,
        coerce_resolved_intent_fn=_coerce_resolved_intent_for_query,
        live_routing_config=live_routing_config,
        registry_candidates=_registry_intent_candidates,
    )

    decomposer_node = build_multi_query_decomposer_node(
        llm=llm,
        decomposer_prompt_template=decomposer_prompt_template,
        latest_user_query_fn=_latest_user_query,
        append_datetime_context_fn=append_datetime_context,
        extract_first_json_object_fn=_extract_first_json_object,
    )

    resolve_agents_node = build_agent_resolver_node(
        llm=llm,
        agent_resolver_prompt_template=agent_resolver_prompt_template,
        latest_user_query_fn=_latest_user_query,
        normalize_route_hint_fn=_normalize_route_hint_value,
        route_allowed_agents_fn=_route_allowed_agents,
        route_default_agent_fn=_route_default_agent,
        smart_retrieve_agents_fn=_smart_retrieve_agents,
        smart_retrieve_agents_with_scores_fn=_smart_retrieve_agents_with_breakdown,
        agent_definitions=agent_definitions,
        agent_by_name=agent_by_name,
        agent_payload_fn=_agent_payload,
        append_datetime_context_fn=append_datetime_context,
        extract_first_json_object_fn=_extract_first_json_object,
        live_routing_config=live_routing_config,
    )

    planner_node = build_planner_node(
        llm=llm,
        planner_prompt_template=planner_prompt_template,
        multi_domain_planner_prompt_template=multi_domain_planner_prompt_template,
        latest_user_query_fn=_latest_user_query,
        append_datetime_context_fn=append_datetime_context,
        extract_first_json_object_fn=_extract_first_json_object,
    )

    planner_hitl_gate_node = build_planner_hitl_gate_node(
        hitl_enabled_fn=_hitl_enabled,
        plan_preview_text_fn=_plan_preview_text,
        render_hitl_message_fn=_render_hitl_message,
        hitl_planner_message_template=hitl_planner_message_template,
    )

    # Capture live_tool_index + persisted_tuning for namespace exposure closure
    _ns_tool_index = live_tool_index
    _ns_tuning = persisted_tuning

    def _llm_gate_tool_candidates_for_agent(agent_name: str) -> list[dict[str, Any]]:
        """Return all tools in an agent's namespace as dicts for LLM gate selection.

        Resolution order:
        1. graph_registry.tools_by_agent (DB-driven, authoritative)
        2. AGENT_NAMESPACE_MAP + tool_index namespace matching (hardcoded fallback)
        3. Empty list (never return ALL tools for unknown agents)
        """
        from app.agents.new_chat.bigtool_store import AGENT_NAMESPACE_MAP, _match_namespace

        _agent_key = str(agent_name or "").strip().lower()

        # Path 1: DB-driven registry (authoritative)
        if graph_registry is not None:
            registry_tools = graph_registry.tools_by_agent.get(_agent_key) or []
            if registry_tools:
                return [
                    {
                        "tool_id": str(t.get("tool_id") or "").strip(),
                        "name": str(t.get("name") or t.get("tool_id") or "").strip(),
                        "description": str(t.get("description") or "").strip(),
                        "keywords": list(t.get("keywords") or []),
                    }
                    for t in registry_tools
                    if str(t.get("tool_id") or "").strip()
                ]

        # Path 2: Hardcoded namespace map
        prefixes = AGENT_NAMESPACE_MAP.get(_agent_key, [])
        if not prefixes:
            # No namespace mapping AND no registry entry — return empty
            # rather than exposing ALL tools (which causes wrong tool selection).
            logger.warning(
                "LLM gate: no tool candidates for agent %r (not in registry or namespace map)",
                _agent_key,
            )
            return []
        results: list[dict[str, Any]] = []
        for entry in _ns_tool_index:
            for prefix in prefixes:
                if _match_namespace(entry.namespace, prefix):
                    results.append({
                        "tool_id": entry.tool_id,
                        "name": entry.name,
                        "description": entry.description,
                        "keywords": list(entry.keywords or []),
                    })
                    break
        return results

    tool_resolver_node = build_tool_resolver_node(
        tool_resolver_prompt_template=tool_resolver_prompt_template,
        latest_user_query_fn=_latest_user_query,
        next_plan_step_fn=_next_plan_step,
        resolve_tool_selection_for_agent_fn=_resolve_live_tool_selection_for_agent,
        focused_tool_ids_for_agent_fn=(
            lambda agent_name, task: _prioritize_sandbox_code_tools(
                _focused_tool_ids_for_agent(agent_name, task, limit=6),
                agent_name=agent_name,
                task=task,
                limit=8,
            )
        ),
        weather_tool_ids=weather_tool_ids,
        trafik_tool_ids=trafik_tool_ids,
        namespace_tool_ids_fn=(
            (
                lambda agent_name, query: get_namespace_tool_ids_with_retrieval_hints(
                    agent_name,
                    query,
                    tool_index=_ns_tool_index,
                    tuning=_ns_tuning,
                )
            )
            if _ns_tool_index
            else None
        ),
        llm_gate_tool_candidates_fn=(
            _llm_gate_tool_candidates_for_agent if _ns_tool_index else None
        ),
        live_routing_config=live_routing_config,
        llm=llm,
    )
    execution_router_node = build_execution_router_node(
        latest_user_query_fn=_latest_user_query,
        next_plan_step_fn=_next_plan_step,
        subagent_enabled=subagent_enabled,
    )
    speculative_node = build_speculative_node(
        run_speculative_candidate_fn=_run_speculative_candidate,
        max_candidates=3,
    )
    speculative_merge_node = build_speculative_merge_node()

    execution_hitl_gate_node = build_execution_hitl_gate_node(
        hitl_enabled_fn=_hitl_enabled,
        next_plan_step_fn=_next_plan_step,
        render_hitl_message_fn=_render_hitl_message,
        hitl_execution_message_template=hitl_execution_message_template,
    )

    critic_node = build_critic_node(
        llm=llm,
        critic_gate_prompt_template=critic_gate_prompt_template,
        loop_guard_template=loop_guard_template,
        default_loop_guard_message=DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
        max_replan_attempts=_MAX_REPLAN_ATTEMPTS,
        latest_user_query_fn=_latest_user_query,
        append_datetime_context_fn=append_datetime_context,
        extract_first_json_object_fn=_extract_first_json_object,
        render_guard_message_fn=_render_guard_message,
        max_total_steps=MAX_TOTAL_STEPS,
    )
    smart_critic_node = build_smart_critic_node(
        fallback_critic_node=critic_node,
        contract_from_payload_fn=_contract_from_payload,
        latest_user_query_fn=_latest_user_query,
        max_replan_attempts=_MAX_REPLAN_ATTEMPTS,
        min_mechanical_confidence=0.7,
        record_retrieval_feedback_fn=_record_retrieval_feedback,
    )

    synthesis_hitl_gate_node = build_synthesis_hitl_gate_node(
        hitl_enabled_fn=_hitl_enabled,
        truncate_for_prompt_fn=_truncate_for_prompt,
        render_hitl_message_fn=_render_hitl_message,
        hitl_synthesis_message_template=hitl_synthesis_message_template,
    )

    synthesizer_node = build_synthesizer_node(
        llm=llm,
        synthesizer_prompt_template=synthesizer_prompt_template,
        compare_synthesizer_prompt_template=compare_synthesizer_prompt_template,
        latest_user_query_fn=_latest_user_query,
        append_datetime_context_fn=append_datetime_context,
        extract_first_json_object_fn=_extract_first_json_object,
        strip_critic_json_fn=_strip_critic_json,
    )
    progressive_synthesizer_node = build_progressive_synthesizer_node(
        truncate_for_prompt_fn=_truncate_for_prompt,
    )

    domain_planner_node = build_domain_planner_node(
        llm=llm,
        domain_planner_prompt_template=domain_planner_prompt_template,
        latest_user_query_fn=_latest_user_query,
        append_datetime_context_fn=append_datetime_context,
        extract_first_json_object_fn=_extract_first_json_object,
    )

    response_layer_router_node = build_response_layer_router_node(
        llm=llm,
        router_prompt=response_layer_router_prompt,
        latest_user_query_fn=_latest_user_query,
    )

    response_layer_node = build_response_layer_node(
        llm=llm,
        mode_prompts={
            "kunskap": response_layer_kunskap_prompt,
            "analys": response_layer_analys_prompt,
            "syntes": response_layer_syntes_prompt,
            "visualisering": response_layer_visualisering_prompt,
        },
        latest_user_query_fn=_latest_user_query,
    )

    call_model, acall_model = build_executor_nodes(
        llm=llm,
        llm_with_tools=llm_with_tools,
        compare_mode=compare_mode,
        strip_critic_json_fn=_strip_critic_json,
        sanitize_messages_fn=_sanitize_messages,
        format_plan_context_fn=_format_plan_context,
        format_recent_calls_fn=_format_recent_calls,
        format_route_hint_fn=_format_route_hint,
        format_execution_strategy_fn=_format_execution_strategy,
        format_intent_context_fn=_format_intent_context,
        format_selected_agents_context_fn=_format_selected_agents_context,
        format_resolved_tools_context_fn=_format_resolved_tools_context,
        format_subagent_handoffs_context_fn=_format_subagent_handoffs_context,
        format_artifact_manifest_context_fn=_format_artifact_manifest_context,
        format_cross_session_memory_context_fn=_format_cross_session_memory_context,
        format_rolling_context_summary_context_fn=_format_rolling_context_summary_context,
        coerce_supervisor_tool_calls_fn=_coerce_supervisor_tool_calls,
        think_on_tool_calls=think_on_tool_calls,
        use_structured_output=_use_structured,
    )

    async def memory_context_node(
        state: SupervisorState,
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        if not cross_session_memory_enabled:
            return {"cross_session_memory_context": None}
        if not cross_session_memory_entries:
            return {"cross_session_memory_context": None}
        latest_user_query = _latest_user_query(state.get("messages") or [])
        selected_entries = _select_cross_session_memory_entries(
            entries=cross_session_memory_entries,
            query=latest_user_query,
            max_items=int(cross_session_memory_max_items),
        )
        rendered = _render_cross_session_memory_context(
            entries=selected_entries,
            max_chars=int(cross_session_memory_max_chars),
        )
        if not rendered:
            return {"cross_session_memory_context": None}
        return {"cross_session_memory_context": rendered}

    async def smalltalk_node(
        state: SupervisorState,
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        latest_user_query = _latest_user_query(state.get("messages") or [])
        if not latest_user_query:
            fallback = "Hej! Hur kan jag hjälpa dig idag?"
            return {
                "messages": [AIMessage(content=fallback)],
                "final_agent_response": fallback,
                "final_response": fallback,
                "final_agent_name": "smalltalk",
                "critic_decision": "ok",
                "plan_complete": True,
                "orchestration_phase": "finalize",
            }

        prompt = append_datetime_context(str(smalltalk_prompt_template or "").strip())
        if not prompt:
            prompt = append_datetime_context(SMALLTALK_INSTRUCTIONS)
        response_text = ""
        try:
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=latest_user_query),
                ],
                max_tokens=180,
            )
            raw_content = str(getattr(message, "content", "") or "")
            # Strip any <think>…</think> that the model may produce despite
            # instructions — smalltalk must never expose internal reasoning.
            response_text = re.sub(r"<think>[\s\S]*?</think>", "", raw_content).strip()
            # Also strip bare opening <think> with no closing tag (truncated)
            response_text = re.sub(r"<think>[\s\S]*$", "", response_text).strip()
            response_text = _strip_critic_json(response_text).strip()
        except Exception:
            response_text = ""
        if not response_text:
            response_text = "Hej! Jag är OneSeek. Hur kan jag hjälpa dig idag?"
        return {
            "messages": [AIMessage(content=response_text)],
            "final_agent_response": response_text,
            "final_response": response_text,
            "final_agent_name": "smalltalk",
            "critic_decision": "ok",
            "plan_complete": True,
            "orchestration_phase": "finalize",
        }

    async def post_tools(
        state: SupervisorState,
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        updates: dict[str, Any] = {}
        recent_updates: list[dict[str, Any]] = []
        compare_updates: list[dict[str, Any]] = []
        subagent_handoff_updates: list[dict[str, Any]] = []
        artifact_updates: list[dict[str, Any]] = []
        parallel_preview: list[str] = []
        plan_update: list[dict[str, Any]] | None = None
        plan_complete: bool | None = None
        last_call_payload: dict[str, Any] | None = None
        route_hint = _normalize_route_hint_value(state.get("route_hint"))
        latest_user_query = _latest_user_query(state.get("messages") or [])
        messages = list(state.get("messages") or [])
        existing_steps = [
            item for item in (state.get("step_results") or []) if isinstance(item, dict)
        ]
        tool_call_index = _tool_call_name_index(messages)

        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                break
            if not isinstance(message, ToolMessage):
                continue
            tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            if not tool_name:
                continue
            payload = _safe_json(message.content)
            if tool_name == "write_todos":
                todos = payload.get("todos") or []
                if todos:
                    plan_update = todos
                    completed = [
                        str(todo.get("status") or "").lower()
                        for todo in todos
                        if isinstance(todo, dict)
                    ]
                    if completed:
                        plan_complete = all(
                            status in ("completed", "cancelled") for status in completed
                        )
                if "plan_complete" in payload:
                    plan_complete = bool(payload.get("plan_complete"))
            elif tool_name == "call_agent":
                last_call_payload = payload
                if payload:
                    payload_contract = _contract_from_payload(payload)
                    recent_updates.append(
                        {
                            "agent": payload.get("agent"),
                            "task": payload.get("task"),
                            "response": payload.get("response"),
                            "result_contract": payload_contract,
                        }
                    )
                    handoff = payload.get("subagent_handoff")
                    if isinstance(handoff, dict):
                        subagent_handoff_updates.append(handoff)
                    payload_artifacts = payload.get("artifacts")
                    if isinstance(payload_artifacts, list):
                        artifact_updates.extend(
                            item for item in payload_artifacts if isinstance(item, dict)
                        )
                    pending_followup_steps = _projected_followup_plan_steps(
                        state=state,
                        active_plan=plan_update,
                        plan_complete=plan_complete,
                        completed_steps_count=len(existing_steps) + len(recent_updates),
                    )
                    if payload.get("final") and payload.get("response"):
                        cleaned_response = _strip_critic_json(
                            str(payload.get("response") or "").strip()
                        )
                        if (
                            _should_finalize_from_contract(
                                contract=payload_contract,
                                response_text=cleaned_response,
                                route_hint=route_hint,
                                agent_name=str(payload.get("agent") or ""),
                                latest_user_query=latest_user_query,
                                agent_hops=int(state.get("agent_hops") or 0),
                            )
                            and not pending_followup_steps
                        ):
                            updates["final_agent_response"] = cleaned_response
                            updates["final_response"] = cleaned_response
                            updates["final_agent_name"] = payload.get("agent")
                            updates["orchestration_phase"] = "finalize"
                    elif payload.get("response"):
                        cleaned_response = _strip_critic_json(
                            str(payload.get("response") or "").strip()
                        )
                        selected_agent = str(payload.get("agent") or "").strip().lower()
                        if (
                            _should_finalize_from_contract(
                                contract=payload_contract,
                                response_text=cleaned_response,
                                route_hint=route_hint,
                                agent_name=selected_agent,
                                latest_user_query=latest_user_query,
                                agent_hops=int(state.get("agent_hops") or 0),
                            )
                            and not pending_followup_steps
                        ):
                            updates["final_agent_response"] = cleaned_response
                            updates["final_response"] = cleaned_response
                            updates["final_agent_name"] = payload.get("agent")
                            updates["orchestration_phase"] = "finalize"
            elif tool_name == "call_agents_parallel":
                parallel_results = payload.get("results")
                if isinstance(parallel_results, list):
                    for item in parallel_results:
                        if not isinstance(item, dict):
                            continue
                        agent_name = str(item.get("agent") or "").strip()
                        task_text = str(item.get("task") or "").strip()
                        response_text = _strip_critic_json(
                            str(item.get("response") or "").strip()
                        )
                        error_text = str(item.get("error") or "").strip()
                        compact_response = response_text or error_text
                        if compact_response:
                            recent_updates.append(
                                {
                                    "agent": agent_name or "agent",
                                    "task": task_text,
                                    "response": compact_response,
                                    "result_contract": _contract_from_payload(item),
                                }
                            )
                        if response_text and len(parallel_preview) < 3:
                            label = agent_name or "agent"
                            parallel_preview.append(
                                f"- {label}: {_truncate_for_prompt(response_text, 220)}"
                            )
                        handoff = item.get("subagent_handoff")
                        if isinstance(handoff, dict):
                            subagent_handoff_updates.append(handoff)
                        item_artifacts = item.get("artifacts")
                        if isinstance(item_artifacts, list):
                            artifact_updates.extend(
                                entry
                                for entry in item_artifacts
                                if isinstance(entry, dict)
                            )
            elif tool_name in _EXTERNAL_MODEL_TOOL_NAMES:
                if payload and payload.get("status") == "success":
                    compare_updates.append(
                        {
                            "tool_call_id": getattr(message, "tool_call_id", None),
                            "tool_name": tool_name,
                            "model_display_name": payload.get("model_display_name"),
                            "model": payload.get("model"),
                            "response": payload.get("response"),
                            "summary": payload.get("summary"),
                            "citation_chunk_ids": payload.get("citation_chunk_ids"),
                        }
                    )
            if plan_update and last_call_payload:
                break

        if plan_update is not None:
            updates["active_plan"] = plan_update
        if plan_complete is not None:
            updates["plan_complete"] = plan_complete
        if recent_updates:
            updates["recent_agent_calls"] = recent_updates
            merged_steps = (existing_steps + recent_updates)[-12:]
            updates["step_results"] = merged_steps
            updates["plan_step_index"] = min(
                len(merged_steps),
                len(state.get("active_plan") or []),
            )
        if compare_updates:
            updates["compare_outputs"] = compare_updates
        if subagent_handoff_updates:
            updates["subagent_handoffs"] = subagent_handoff_updates
        if artifact_updates:
            updates["artifact_manifest"] = artifact_updates
        updates["guard_parallel_preview"] = parallel_preview[:3]
        return updates

    async def artifact_indexer(
        state: SupervisorState,
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        if not artifact_offload_enabled:
            return {}
        messages = list(state.get("messages") or [])
        if not messages:
            return {}
        turn_key = _current_turn_key(state)
        tool_call_index = _tool_call_name_index(messages)
        existing_manifest = [
            item
            for item in (state.get("artifact_manifest") or [])
            if isinstance(item, dict)
        ]
        existing_source_ids = {
            str(item.get("source_id") or "").strip()
            for item in existing_manifest
            if str(item.get("source_id") or "").strip()
        }
        existing_digests = {
            str(item.get("content_sha1") or "").strip()
            for item in existing_manifest
            if str(item.get("content_sha1") or "").strip()
        }
        current_turn_id = str(
            state.get("active_turn_id") or state.get("turn_id") or ""
        ).strip()
        new_entries: list[dict[str, Any]] = []

        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                break
            if not isinstance(message, ToolMessage):
                continue
            tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            normalized_tool_name = str(tool_name or "").strip().lower()
            if (
                not normalized_tool_name
                or normalized_tool_name in _ARTIFACT_INTERNAL_TOOL_NAMES
            ):
                continue
            payload = _safe_json(getattr(message, "content", ""))
            if not payload:
                continue
            serialized_payload = _serialize_artifact_payload(payload)
            if len(serialized_payload) < int(artifact_offload_threshold_chars):
                continue
            content_sha1 = hashlib.sha1(
                serialized_payload.encode("utf-8", errors="ignore")
            ).hexdigest()
            source_id = str(getattr(message, "tool_call_id", "") or "").strip()
            if not source_id:
                source_id = f"{normalized_tool_name}:{content_sha1[:14]}"
            if source_id in existing_source_ids or content_sha1 in existing_digests:
                continue

            artifact_seed = "|".join(
                [
                    str(thread_id or "thread"),
                    current_turn_id or "turn",
                    source_id,
                    content_sha1[:16],
                ]
            )
            artifact_id = (
                "art-"
                + hashlib.sha1(
                    artifact_seed.encode("utf-8", errors="ignore")
                ).hexdigest()[:16]
            )
            artifact_uri, artifact_path, storage_backend = _persist_artifact_content(
                artifact_id=artifact_id,
                content=serialized_payload,
                thread_id=thread_id,
                turn_key=turn_key,
                sandbox_enabled=bool(sandbox_enabled),
                artifact_storage_mode=artifact_offload_storage_mode,
                runtime_hitl_cfg=runtime_hitl_cfg,
            )
            summary = _summarize_tool_payload(normalized_tool_name, payload)
            entry = {
                "id": artifact_id,
                "artifact_uri": artifact_uri,
                "artifact_path": artifact_path,
                "storage_backend": storage_backend,
                "tool": normalized_tool_name,
                "source_id": source_id,
                "turn_id": current_turn_id or None,
                "summary": _truncate_for_prompt(summary, 220),
                "size_bytes": len(serialized_payload.encode("utf-8")),
                "content_sha1": content_sha1,
                "created_at": datetime.now(UTC).isoformat(),
            }
            new_entries.append(entry)
            existing_source_ids.add(source_id)
            existing_digests.add(content_sha1)
            per_pass_limit = min(
                max(1, int(artifact_offload_max_entries)),
                _ARTIFACT_OFFLOAD_PER_PASS_LIMIT,
            )
            if len(new_entries) >= per_pass_limit:
                break

        if not new_entries:
            return {}
        return {
            "artifact_manifest": new_entries,
        }

    async def context_compactor(
        state: SupervisorState,
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        if not context_compaction_enabled:
            return {}
        messages = list(state.get("messages") or [])
        if len(messages) < _CONTEXT_COMPACTION_MIN_MESSAGES:
            return {}
        if not (
            state.get("step_results")
            or state.get("artifact_manifest")
            or state.get("subagent_handoffs")
        ):
            return {}

        usage_ratio = 0.0
        if context_token_budget is not None and context_budget_available_tokens > 0:
            try:
                used_tokens = context_token_budget.estimate_messages_tokens(messages)
                usage_ratio = float(used_tokens) / float(
                    context_budget_available_tokens
                )
            except Exception:
                usage_ratio = 0.0
        else:
            # Conservative fallback when model context metadata is unavailable.
            approx_chars = sum(
                len(str(getattr(message, "content", "") or "")) for message in messages
            )
            usage_ratio = min(1.0, float(max(0, approx_chars)) / 24_000.0)
        if (
            usage_ratio < float(context_compaction_trigger_ratio)
            and len(messages) < MESSAGE_PRUNING_THRESHOLD
        ):
            return {}

        summary = _build_rolling_context_summary(
            latest_user_query=_latest_user_query(messages),
            active_plan=[
                item
                for item in (state.get("active_plan") or [])
                if isinstance(item, dict)
            ],
            step_results=[
                item
                for item in (state.get("step_results") or [])
                if isinstance(item, dict)
            ],
            subagent_handoffs=[
                item
                for item in (state.get("subagent_handoffs") or [])
                if isinstance(item, dict)
            ],
            artifact_manifest=[
                item
                for item in (state.get("artifact_manifest") or [])
                if isinstance(item, dict)
            ],
            targeted_missing_info=[
                str(item).strip()
                for item in (state.get("targeted_missing_info") or [])
                if str(item).strip()
            ],
            max_chars=int(context_compaction_summary_max_chars),
        )
        if not summary:
            return {}

        updates: dict[str, Any] = {
            "rolling_context_summary": summary,
        }
        compacted_steps = [
            item for item in (state.get("step_results") or []) if isinstance(item, dict)
        ]
        if len(compacted_steps) > _CONTEXT_COMPACTION_DEFAULT_STEP_KEEP:
            updates["step_results"] = compacted_steps[
                -_CONTEXT_COMPACTION_DEFAULT_STEP_KEEP:
            ]
        compacted_handoffs = [
            item
            for item in (state.get("subagent_handoffs") or [])
            if isinstance(item, dict)
        ]
        if len(compacted_handoffs) > _SUBAGENT_MAX_HANDOFFS_IN_PROMPT:
            updates["subagent_handoffs"] = compacted_handoffs[
                -_SUBAGENT_MAX_HANDOFFS_IN_PROMPT:
            ]
        compacted_artifacts = [
            item
            for item in (state.get("artifact_manifest") or [])
            if isinstance(item, dict)
        ]
        if len(compacted_artifacts) > int(artifact_offload_max_entries):
            updates["artifact_manifest"] = compacted_artifacts[
                -int(artifact_offload_max_entries) :
            ]
        return updates

    async def orchestration_guard(
        state: SupervisorState,
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        updates: dict[str, Any] = {}
        # P1: increment total_steps for every pass through orchestration_guard.
        updates["total_steps"] = int(state.get("total_steps") or 0) + 1
        route_hint = str(state.get("route_hint") or "").strip().lower()
        latest_user_query = _latest_user_query(state.get("messages") or [])
        parallel_preview = list(state.get("guard_parallel_preview") or [])[:3]
        current_turn_id = str(
            state.get("active_turn_id") or state.get("turn_id") or ""
        ).strip()
        call_entries = _agent_call_entries_since_last_user(
            state.get("messages") or [],
            turn_id=current_turn_id or None,
        )
        if not parallel_preview and call_entries:
            for item in reversed(call_entries):
                response_text = _strip_critic_json(
                    str(item.get("response") or "").strip()
                )
                if not response_text:
                    continue
                agent_name = str(item.get("agent") or "agent").strip() or "agent"
                parallel_preview.append(
                    f"- {agent_name}: {_truncate_for_prompt(response_text, 220)}"
                )
                if len(parallel_preview) >= 3:
                    break
        messages = list(state.get("messages") or [])
        tool_call_index = _tool_call_name_index(messages)
        last_call_payload: dict[str, Any] | None = None
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                break
            if not isinstance(message, ToolMessage):
                continue
            tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            if tool_name != "call_agent":
                continue
            payload = _safe_json(getattr(message, "content", ""))
            if payload:
                last_call_payload = payload
                break

        agent_hops = len(call_entries)
        updates["agent_hops"] = agent_hops
        updates["orchestration_phase"] = (
            "validate_agent_output" if agent_hops > 0 else "select_agent"
        )
        pending_followup_steps = _has_followup_plan_steps(state)

        no_progress_runs = int(state.get("no_progress_runs") or 0)
        if call_entries:
            last_entry = call_entries[-1]
            last_agent = str(last_entry.get("agent") or "").strip().lower()
            # P2.5: Fingerprint based on agent_name + route_hint instead of
            # agent_name + task_text.  Minimal task variations (e.g.
            # "invånare Göteborg 2023" vs "befolkning Göteborg 2023") no
            # longer reset the counter — same agent + same route = no progress.
            last_fp = f"{last_agent}|{route_hint}" if last_agent else ""
            if last_fp:
                fp_count = 0
                for entry in call_entries:
                    agent = str(entry.get("agent") or "").strip().lower()
                    if f"{agent}|{route_hint}" == last_fp:
                        fp_count += 1
                no_progress_runs = no_progress_runs + 1 if fp_count >= 2 else 0
            else:
                no_progress_runs = 0
        else:
            no_progress_runs = 0
        updates["no_progress_runs"] = no_progress_runs

        if (
            "final_agent_response" not in updates
            and call_entries
            and route_hint not in {"jämförelse", "compare"}
            and not pending_followup_steps
        ):
            last_entry = call_entries[-1]
            last_response = _strip_critic_json(
                str(last_entry.get("response") or "").strip()
            )
            last_contract = _contract_from_payload(last_entry)
            if _should_finalize_from_contract(
                contract=last_contract,
                response_text=last_response,
                route_hint=route_hint,
                agent_name=str(last_entry.get("agent") or ""),
                latest_user_query=latest_user_query,
                agent_hops=agent_hops,
            ):
                updates["final_agent_response"] = last_response
                updates["final_response"] = last_response
                updates["final_agent_name"] = (
                    str(last_entry.get("agent") or "").strip() or "agent"
                )
                updates["orchestration_phase"] = "finalize"
                updates["guard_finalized"] = True

        if (
            "final_agent_response" not in updates
            and route_hint not in {"jämförelse", "compare"}
            and not pending_followup_steps
        ):
            ai_fallback = _latest_actionable_ai_response(
                messages,
                latest_user_query=latest_user_query,
            )
            if ai_fallback:
                updates["final_agent_response"] = ai_fallback
                updates["final_response"] = ai_fallback
                updates["final_agent_name"] = "assistant"
                updates["orchestration_phase"] = "finalize"
                updates["guard_finalized"] = True

        if "final_agent_response" not in updates and no_progress_runs >= 2:
            best = _best_actionable_entry(call_entries)
            if best:
                updates["final_agent_response"] = best[0]
                updates["final_response"] = best[0]
                updates["final_agent_name"] = best[1]
                updates["orchestration_phase"] = "finalize"
                updates["guard_finalized"] = True
            else:
                rendered = _render_guard_message(loop_guard_template, parallel_preview)
                if not rendered:
                    rendered = _render_guard_message(
                        DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
                        parallel_preview,
                    )
                updates["final_agent_response"] = rendered
                updates["final_response"] = rendered
                updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
                updates["orchestration_phase"] = "finalize"
                updates["guard_finalized"] = True

        if last_call_payload:
            last_contract = _contract_from_payload(last_call_payload)
            if (
                bool(last_contract.get("retry_recommended"))
                and "final_agent_response" not in updates
            ):
                updates["plan_complete"] = False

        # Guard: detect repeated calls to the same direct tool (e.g. scb_befolkning
        # or smhi_vaderprognoser_metfcst called 2+ times in a row without progress).
        if "final_agent_response" not in updates:
            same_tool_count, same_tool_name = _count_consecutive_same_direct_tool(
                state.get("messages") or []
            )
            if same_tool_count >= _MAX_CONSECUTIVE_SAME_TOOL:
                # Try to use the last tool result as the final response
                last_tool_response = ""
                for message in reversed(messages):
                    if isinstance(message, HumanMessage):
                        break
                    if isinstance(message, ToolMessage):
                        content = str(getattr(message, "content", "") or "")
                        parsed = _safe_json(content)
                        if isinstance(parsed, dict):
                            last_tool_response = _strip_critic_json(
                                str(
                                    parsed.get("summary")
                                    or parsed.get("response")
                                    or content
                                )
                            ).strip()
                        else:
                            last_tool_response = _strip_critic_json(content).strip()
                        break
                if last_tool_response:
                    updates["final_agent_response"] = last_tool_response
                    updates["final_response"] = last_tool_response
                    updates["final_agent_name"] = same_tool_name or "agent"
                else:
                    rendered = _render_guard_message(
                        loop_guard_template, parallel_preview
                    )
                    if not rendered:
                        rendered = _render_guard_message(
                            DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE, parallel_preview
                        )
                    updates["final_agent_response"] = rendered
                    updates["final_response"] = rendered
                    updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
                updates["orchestration_phase"] = "finalize"
                updates["guard_finalized"] = True

        # Fallback safety: avoid endless supervisor loops on repeated retrieval/delegation tools.
        if "final_agent_response" not in updates:
            loop_count = _count_consecutive_loop_tools(
                state.get("messages") or [],
                turn_id=current_turn_id or None,
            )
            if loop_count >= _LOOP_GUARD_MAX_CONSECUTIVE:
                rendered = _render_guard_message(loop_guard_template, parallel_preview)
                if not rendered:
                    rendered = _render_guard_message(
                        DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
                        parallel_preview,
                    )
                updates["final_agent_response"] = rendered
                updates["final_response"] = rendered
                updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
                updates["orchestration_phase"] = "finalize"
                updates["guard_finalized"] = True

        if (
            "final_agent_response" not in updates
            and agent_hops >= _MAX_AGENT_HOPS_PER_TURN
        ):
            best = _best_actionable_entry(call_entries)
            if best:
                updates["final_agent_response"] = best[0]
                updates["final_response"] = best[0]
                updates["final_agent_name"] = best[1]
            else:
                rendered = _render_guard_message(
                    tool_limit_guard_template,
                    parallel_preview[:3],
                )
                if not rendered:
                    rendered = _render_guard_message(
                        DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
                        parallel_preview[:3],
                    )
                updates["final_agent_response"] = rendered
                updates["final_response"] = rendered
                updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
            updates["orchestration_phase"] = "finalize"
            updates["guard_finalized"] = True

        # Hard guardrail: stop runaway tool loops within a single user turn.
        if "final_agent_response" not in updates:
            tool_calls_this_turn = _count_tools_since_last_user(
                state.get("messages") or []
            )
            if tool_calls_this_turn >= _MAX_TOOL_CALLS_PER_TURN:
                rendered = _render_guard_message(
                    tool_limit_guard_template,
                    parallel_preview[:3],
                )
                if not rendered:
                    rendered = _render_guard_message(
                        DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
                        parallel_preview[:3],
                    )
                updates["final_agent_response"] = rendered
                updates["final_response"] = rendered
                updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
                updates["orchestration_phase"] = "finalize"
                updates["guard_finalized"] = True

        # Progressive message pruning when messages get long
        if len(messages) > MESSAGE_PRUNING_THRESHOLD:
            tool_msgs = [
                i for i, m in enumerate(messages) if isinstance(m, ToolMessage)
            ]
            if len(tool_msgs) > TOOL_MSG_THRESHOLD:
                keep_from = tool_msgs[-KEEP_TOOL_MSG_COUNT]
                keep_start = max(0, keep_from - 1)
                dropped_count = keep_start
                if dropped_count > 0:
                    pruned = messages[keep_start:]
                    rolling_summary = str(
                        state.get("rolling_context_summary") or ""
                    ).strip()
                    summary_content = (
                        "<rolling_context_summary>\n"
                        + _truncate_for_prompt(
                            rolling_summary,
                            int(context_compaction_summary_max_chars),
                        )
                        + "\n</rolling_context_summary>"
                        if rolling_summary
                        else f"[{dropped_count} earlier messages (including tool calls) condensed. Recent context retained.]"
                    )
                    summary_msg = SystemMessage(content=summary_content)
                    leading_system = [
                        m for m in messages[:keep_start] if isinstance(m, SystemMessage)
                    ]
                    updates["messages"] = leading_system + [summary_msg] + pruned

        updates["guard_parallel_preview"] = []
        return updates

    def route_after_intent(state: SupervisorState, *, store=None):
        if bool(state.get("awaiting_confirmation")):
            stage = str(state.get("pending_hitl_stage") or "").strip().lower()
            if stage == "planner":
                return "planner_hitl_gate"
            if stage == "execution":
                return "execution_hitl_gate"
            if stage == "synthesis":
                return "synthesis_hitl"
            # Unknown/stale HITL stage — pause safely rather than proceeding
            # without user approval.
            return END
        resolved_intent = state.get("resolved_intent") or {}
        resolved_route = _normalize_route_hint_value(
            (
                resolved_intent.get("route")
                if isinstance(resolved_intent, dict)
                else None
            )
            or state.get("route_hint")
        )
        if resolved_route in {"konversation", "smalltalk"}:
            return "smalltalk"
        phase = str(state.get("orchestration_phase") or "").strip().lower()
        has_final = bool(
            str(
                state.get("final_response") or state.get("final_agent_response") or ""
            ).strip()
        )
        if phase == "finalize" and has_final:
            return "synthesis_hitl"
        if phase in {"resolve_tools", "execute"}:
            return "tool_resolver"
        if phase in {"plan"}:
            return "planner"
        if hybrid_mode and not compare_mode:
            complexity = str(state.get("graph_complexity") or "").strip().lower()
            if complexity == "simple":
                return "tool_resolver"
            if complexity == "trivial":
                if has_final:
                    return "synthesis_hitl"
                return "agent_resolver"
            # P3: complex queries go through multi_query_decomposer first.
            if complexity == "complex":
                return "multi_query_decomposer"
            return "agent_resolver"
        return "agent_resolver"

    def planner_hitl_should_continue(state: SupervisorState, *, store=None):
        awaiting = bool(state.get("awaiting_confirmation"))
        stage = str(state.get("pending_hitl_stage") or "").strip().lower()
        if awaiting and stage == "planner":
            return END
        return "tool_resolver"

    def execution_hitl_should_continue(state: SupervisorState, *, store=None):
        awaiting = bool(state.get("awaiting_confirmation"))
        stage = str(state.get("pending_hitl_stage") or "").strip().lower()
        if awaiting and stage == "execution":
            return END
        return "executor"

    def executor_should_continue(state: SupervisorState, *, store=None):
        messages = state.get("messages") or []
        if not messages:
            return "critic"
        last_message = messages[-1]
        if not (
            isinstance(last_message, AIMessage)
            and getattr(last_message, "tool_calls", None)
        ):
            return "critic"

        # --- Loop guard: detect repeated calls to the same direct tool ---
        # Count how many consecutive ToolMessage results come from the same
        # tool name.  If the executor keeps requesting the same tool, force
        # exit to critic instead of executing the tool again.
        tool_call_index = _tool_call_name_index(messages)
        consecutive = 0
        last_tool_name = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                break
            if not isinstance(msg, ToolMessage):
                continue
            name = _resolve_tool_message_name(msg, tool_call_index=tool_call_index)
            if not name or name in {
                "call_agent",
                "retrieve_agents",
                "reflect_on_progress",
                "write_todos",
            }:
                break
            if not last_tool_name:
                last_tool_name = name
            if name == last_tool_name:
                consecutive += 1
            else:
                break
        if consecutive >= _MAX_CONSECUTIVE_SAME_TOOL:
            # Force to critic — the same tool has been called enough times.
            return "critic"

        return "tools"

    def critic_should_continue(state: SupervisorState, *, store=None):
        decision = str(state.get("critic_decision") or "").strip().lower()
        final_response = str(
            state.get("final_response") or state.get("final_agent_response") or ""
        ).strip()
        replan_count = int(state.get("replan_count") or 0)
        total_steps = int(state.get("total_steps") or 0)
        # P1: guard_finalized or total_steps cap → always exit to synthesis.
        if state.get("guard_finalized") or total_steps >= MAX_TOTAL_STEPS:
            return "synthesis_hitl"
        if final_response and decision in {"ok", "pass", "finalize"}:
            return "synthesis_hitl"
        if decision == "replan" and replan_count < _MAX_REPLAN_ATTEMPTS:
            return "planner"
        if decision == "needs_more" and replan_count < _MAX_REPLAN_ATTEMPTS:
            return "tool_resolver"
        if final_response:
            return "synthesis_hitl"
        # Replan budget exhausted and guard-message may have produced an empty
        # final_response — always exit towards synthesis rather than looping
        # back to planner, which would create an unbounded replan cycle.
        return "synthesis_hitl"

    def synthesis_hitl_should_continue(state: SupervisorState, *, store=None):
        awaiting = bool(state.get("awaiting_confirmation"))
        stage = str(state.get("pending_hitl_stage") or "").strip().lower()
        if awaiting and stage == "synthesis":
            return END
        if hybrid_mode and not compare_mode:
            # Skip the progressive synthesizer for simple/trivial queries —
            # they produce short responses that don't benefit from incremental
            # streaming synthesis but do pay its latency cost.
            complexity = str(state.get("graph_complexity") or "").strip().lower()
            if complexity not in {"simple", "trivial"}:
                return "progressive_synthesizer"
        return "synthesizer"

    if config_schema is not None:
        try:
            graph_builder = StateGraph(SupervisorState, config_schema=config_schema)
        except TypeError:
            graph_builder = StateGraph(SupervisorState)
    else:
        graph_builder = StateGraph(SupervisorState)
    graph_builder.add_node(
        "resolve_intent", RunnableCallable(None, resolve_intent_node)
    )

    # Conditional graph structure based on compare_mode
    if compare_mode:
        # Compare Supervisor v2: unified P4 architecture
        # Same infrastructure as normal mode: subagent mini-graphs,
        # convergence node, proper handoff contracts.
        from app.agents.new_chat.compare_executor import (
            build_compare_domain_planner_node,
            build_compare_subagent_spawner_node,
            build_compare_synthesizer_node,
        )
        from app.agents.new_chat.nodes.convergence_node import (
            build_convergence_node,
        )

        # Build compare domain planner (deterministic — 8 domains always)
        compare_domain_planner_node = build_compare_domain_planner_node(
            external_model_specs=list(EXTERNAL_MODEL_SPECS),
            include_research=True,
        )

        # Build tavily_search_fn for compare research agent.
        # Pre-fetch the API key NOW (while the DB session is fresh) and
        # cache it in the closure.  This avoids expired-session errors
        # when the function is called minutes later from the research worker.
        #
        # Resolution order:
        # 1. Per-search-space connector (TAVILY_API in DB)
        # 2. Global PUBLIC_TAVILY_API_KEY environment variable
        _compare_tavily_search_fn = None
        _tavily_api_key: str | None = None
        if connector_service and search_space_id is not None:
            try:
                from app.db import SearchSourceConnectorType

                tavily_connector = await connector_service.get_connector_by_type(
                    SearchSourceConnectorType.TAVILY_API, search_space_id
                )
                if tavily_connector:
                    _tavily_api_key = tavily_connector.config.get("TAVILY_API_KEY")
            except Exception as exc:
                logger.warning(
                    "compare mode: failed to fetch Tavily API key from DB: %s", exc
                )

        # Fallback: use global PUBLIC_TAVILY_API_KEY from environment
        if not _tavily_api_key:
            from app.config import Config as _AppConfig

            _tavily_api_key = getattr(_AppConfig, "PUBLIC_TAVILY_API_KEY", None)
            if _tavily_api_key:
                logger.info(
                    "compare mode: using PUBLIC_TAVILY_API_KEY from env "
                    "(no per-space connector found)"
                )

        if _tavily_api_key:
            _cached_key = _tavily_api_key  # capture in closure

            async def _compare_tavily_search_fn(
                query: str, max_results: int
            ) -> list[dict[str, Any]]:
                """Call Tavily API directly with pre-fetched API key."""
                logger.info(
                    "compare_tavily_search_fn: searching query=%r, max_results=%d",
                    query[:80],
                    max_results,
                )
                try:
                    from tavily import TavilyClient

                    client = TavilyClient(api_key=_cached_key)
                    response = await asyncio.to_thread(
                        client.search,
                        query=query,
                        max_results=max_results,
                        search_depth="basic",
                        include_answer=True,
                        include_raw_content=False,
                        include_images=False,
                    )

                    results: list[dict[str, Any]] = []
                    for item in response.get("results", []):
                        results.append(
                            {
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "content": item.get("content", "")[:500],
                            }
                        )

                    # Include Tavily's own answer if available
                    tavily_answer = response.get("answer", "")
                    if tavily_answer and not results:
                        results.append(
                            {
                                "url": "",
                                "title": "Tavily AI Answer",
                                "content": str(tavily_answer)[:500],
                            }
                        )

                    logger.info(
                        "compare_tavily_search_fn: got %d results for query=%r",
                        len(results),
                        query[:80],
                    )
                    return results

                except Exception as exc:
                    logger.warning(
                        "compare_tavily_search_fn: error: %s",
                        exc,
                        exc_info=True,
                    )
                    return []

            logger.info(
                "compare mode: tavily_search_fn CREATED with pre-fetched API key",
            )
        else:
            logger.warning(
                "compare mode: tavily_search_fn is None! "
                "(connector_service=%s, search_space_id=%s, key_found=%s) "
                "— research agent will NOT perform web searches",
                connector_service,
                search_space_id,
                bool(_tavily_api_key),
            )

        # Build compare subagent spawner (P4 pattern with specialized workers)
        # Compare mode uses sandbox with Redis state store to avoid the
        # file-based lock contention that occurs with 8 parallel domains.
        _compare_hitl = dict(runtime_hitl_cfg or {})
        _compare_hitl["sandbox_state_store"] = "redis"
        # Ensure Redis URL is available for sandbox state store.
        # sandbox_runtime checks: sandbox_state_redis_url → redis_url → REDIS_URL env.
        # Fall back to CELERY_BROKER_URL / REDIS_APP_URL if REDIS_URL is not set.
        if not _compare_hitl.get("sandbox_state_redis_url") and not _compare_hitl.get(
            "redis_url"
        ):
            import os as _os

            _redis_url = (
                _os.getenv("REDIS_URL")
                or _os.getenv("REDIS_APP_URL")
                or _os.getenv("CELERY_BROKER_URL")
            )
            if _redis_url:
                _compare_hitl["redis_url"] = _redis_url
        compare_spawner_node = build_compare_subagent_spawner_node(
            llm=llm,
            compare_mini_critic_prompt=compare_mini_critic_prompt,
            latest_user_query_fn=_latest_user_query,
            extract_first_json_object_fn=_extract_first_json_object,
            tavily_search_fn=_compare_tavily_search_fn,
            execution_timeout_seconds=90,
            sandbox_enabled=True,
            sandbox_isolation_enabled=True,
            runtime_hitl_cfg=_compare_hitl,
            criterion_prompt_overrides=_criterion_prompt_overrides or None,
            research_synthesis_prompt=_research_synthesis_prompt,
        )

        # Build compare convergence node (reuses P4 convergence)
        compare_convergence_node_fn = build_convergence_node(
            llm=llm,
            convergence_prompt_template=compare_convergence_prompt,
            latest_user_query_fn=_latest_user_query,
            extract_first_json_object_fn=_extract_first_json_object,
        )

        # Build compare synthesizer
        compare_synth_node = build_compare_synthesizer_node(
            prompt_override=compare_synthesizer_prompt_template,
        )

        # Add nodes
        graph_builder.add_node(
            "compare_domain_planner",
            RunnableCallable(None, compare_domain_planner_node),
        )
        graph_builder.add_node(
            "compare_subagent_spawner", RunnableCallable(None, compare_spawner_node)
        )
        graph_builder.add_node(
            "compare_convergence", RunnableCallable(None, compare_convergence_node_fn)
        )
        graph_builder.add_node(
            "compare_synthesizer", RunnableCallable(None, compare_synth_node)
        )

        # Graph routing: resolve_intent → domain_planner → spawner → convergence → synthesizer → END
        graph_builder.set_entry_point("resolve_intent")
        graph_builder.add_edge("resolve_intent", "compare_domain_planner")
        graph_builder.add_edge("compare_domain_planner", "compare_subagent_spawner")
        graph_builder.add_edge("compare_subagent_spawner", "compare_convergence")
        graph_builder.add_edge("compare_convergence", "compare_synthesizer")
        graph_builder.add_edge("compare_synthesizer", END)
    elif debate_mode:
        # ─── Debate Supervisor v1: 4-round debate architecture ────────
        from app.agents.new_chat.debate_executor import (
            build_debate_convergence_node,
            build_debate_domain_planner_node,
            build_debate_round_executor_node,
            build_debate_synthesizer_node,
        )

        # Build debate domain planner (deterministic — all participants)
        debate_domain_planner_node = build_debate_domain_planner_node(
            external_model_specs=list(EXTERNAL_MODEL_SPECS),
            include_research=True,
        )

        # Build Tavily search function for OneSeek (reuse compare pattern)
        _debate_tavily_search_fn = None
        _debate_tavily_key: str | None = None
        if connector_service and search_space_id is not None:
            try:
                from app.db import SearchSourceConnectorType

                tavily_connector = await connector_service.get_connector_by_type(
                    SearchSourceConnectorType.TAVILY_API, search_space_id
                )
                if tavily_connector:
                    _debate_tavily_key = tavily_connector.config.get("TAVILY_API_KEY")
            except Exception as exc:
                logger.warning("debate mode: failed to fetch Tavily API key: %s", exc)

        if not _debate_tavily_key:
            from app.config import Config as _AppConfig

            _debate_tavily_key = getattr(_AppConfig, "PUBLIC_TAVILY_API_KEY", None)

        if _debate_tavily_key:
            _cached_debate_key = _debate_tavily_key

            async def _debate_tavily_search_fn(
                query: str, max_results: int
            ) -> list[dict[str, Any]]:
                """Call Tavily API for debate mode OneSeek research."""
                try:
                    from tavily import TavilyClient

                    client = TavilyClient(api_key=_cached_debate_key)
                    response = await asyncio.to_thread(
                        client.search,
                        query=query,
                        max_results=max_results,
                        search_depth="basic",
                        include_answer=True,
                        include_raw_content=False,
                        include_images=False,
                    )

                    results: list[dict[str, Any]] = []
                    for item in response.get("results", []):
                        results.append(
                            {
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "content": item.get("content", "")[:500],
                            }
                        )
                    return results
                except Exception as exc:
                    logger.warning("debate_tavily_search_fn: error: %s", exc)
                    return []

        # Build debate round executor (runs all 4 rounds)
        debate_round_executor_node = build_debate_round_executor_node(
            llm=llm,
            tavily_search_fn=_debate_tavily_search_fn,
            execution_timeout_seconds=90,
            prompt_overrides=prompt_overrides,
            voice_mode=voice_debate_mode,
        )

        # Build debate convergence node
        debate_convergence_node_fn = build_debate_convergence_node(
            llm=llm,
            convergence_prompt_template=debate_convergence_prompt,
            latest_user_query_fn=_latest_user_query,
            extract_first_json_object_fn=_extract_first_json_object,
        )

        # Build debate synthesizer
        debate_synth_node = build_debate_synthesizer_node(
            prompt_override=debate_synthesizer_prompt_template,
        )

        # Add nodes
        graph_builder.add_node(
            "debate_domain_planner", RunnableCallable(None, debate_domain_planner_node)
        )
        graph_builder.add_node(
            "debate_round_executor", RunnableCallable(None, debate_round_executor_node)
        )
        graph_builder.add_node(
            "debate_convergence", RunnableCallable(None, debate_convergence_node_fn)
        )
        graph_builder.add_node(
            "debate_synthesizer", RunnableCallable(None, debate_synth_node)
        )

        # Graph routing: resolve_intent → planner → rounds → convergence → synthesizer → END
        graph_builder.set_entry_point("resolve_intent")
        graph_builder.add_edge("resolve_intent", "debate_domain_planner")
        graph_builder.add_edge("debate_domain_planner", "debate_round_executor")
        graph_builder.add_edge("debate_round_executor", "debate_convergence")
        graph_builder.add_edge("debate_convergence", "debate_synthesizer")
        graph_builder.add_edge("debate_synthesizer", END)
    else:
        # Normal mode: use standard supervisor pipeline
        if hybrid_mode and not compare_mode and speculative_enabled:
            graph_builder.add_node(
                "speculative", RunnableCallable(None, speculative_node)
            )
        graph_builder.add_node(
            "memory_context", RunnableCallable(None, memory_context_node)
        )
        graph_builder.add_node("smalltalk", RunnableCallable(None, smalltalk_node))
        # P3: multi_query_decomposer for complex queries (hybrid_mode only)
        if hybrid_mode and not compare_mode:
            graph_builder.add_node(
                "multi_query_decomposer",
                RunnableCallable(None, decomposer_node),
            )
        graph_builder.add_node(
            "agent_resolver", RunnableCallable(None, resolve_agents_node)
        )
        graph_builder.add_node("planner", RunnableCallable(None, planner_node))
        graph_builder.add_node(
            "planner_hitl_gate",
            RunnableCallable(None, planner_hitl_gate_node),
        )
        graph_builder.add_node(
            "tool_resolver", RunnableCallable(None, tool_resolver_node)
        )
        if hybrid_mode and not compare_mode and speculative_enabled:
            graph_builder.add_node(
                "speculative_merge",
                RunnableCallable(None, speculative_merge_node),
            )
        if hybrid_mode and not compare_mode:
            graph_builder.add_node(
                "execution_router",
                RunnableCallable(None, execution_router_node),
            )
        graph_builder.add_node(
            "execution_hitl_gate",
            RunnableCallable(None, execution_hitl_gate_node),
        )
        graph_builder.add_node("executor", RunnableCallable(call_model, acall_model))
        graph_builder.add_node("tools", tool_node)
        graph_builder.add_node("post_tools", RunnableCallable(None, post_tools))
        graph_builder.add_node(
            "artifact_indexer",
            RunnableCallable(None, artifact_indexer),
        )
        graph_builder.add_node(
            "context_compactor",
            RunnableCallable(None, context_compactor),
        )
        graph_builder.add_node(
            "orchestration_guard",
            RunnableCallable(None, orchestration_guard),
        )
        selected_critic_node = (
            smart_critic_node if hybrid_mode and not compare_mode else critic_node
        )
        graph_builder.add_node("critic", RunnableCallable(None, selected_critic_node))
        graph_builder.add_node(
            "synthesis_hitl",
            RunnableCallable(None, synthesis_hitl_gate_node),
        )
        if hybrid_mode and not compare_mode:
            graph_builder.add_node(
                "progressive_synthesizer",
                RunnableCallable(None, progressive_synthesizer_node),
            )
        graph_builder.add_node("synthesizer", RunnableCallable(None, synthesizer_node))
        graph_builder.add_node(
            "domain_planner", RunnableCallable(None, domain_planner_node)
        )
        graph_builder.add_node(
            "response_layer_router", RunnableCallable(None, response_layer_router_node)
        )
        graph_builder.add_node(
            "response_layer", RunnableCallable(None, response_layer_node)
        )
        graph_builder.set_entry_point("resolve_intent")
        resolve_intent_paths = [
            "smalltalk",
            "agent_resolver",
            "planner",
            "planner_hitl_gate",
            "tool_resolver",
            "execution_hitl_gate",
            "synthesis_hitl",
            END,
        ]
        if hybrid_mode and not compare_mode:
            resolve_intent_paths.append("multi_query_decomposer")
        if hybrid_mode and not compare_mode and speculative_enabled:
            resolve_intent_paths.append("speculative")
        graph_builder.add_edge("resolve_intent", "memory_context")
        graph_builder.add_conditional_edges(
            "memory_context",
            route_after_intent,
            path_map=resolve_intent_paths,
        )
        graph_builder.add_edge("smalltalk", END)
        if hybrid_mode and not compare_mode:
            # P3: decomposer feeds into speculative (if enabled) or agent_resolver.
            if speculative_enabled:
                graph_builder.add_edge("multi_query_decomposer", "speculative")
            else:
                graph_builder.add_edge("multi_query_decomposer", "agent_resolver")
        if hybrid_mode and not compare_mode and speculative_enabled:
            graph_builder.add_edge("speculative", "agent_resolver")
        graph_builder.add_edge("agent_resolver", "planner")
        graph_builder.add_edge("planner", "planner_hitl_gate")
        graph_builder.add_conditional_edges(
            "planner_hitl_gate",
            planner_hitl_should_continue,
            path_map=["tool_resolver", END],
        )
        if hybrid_mode and not compare_mode and speculative_enabled:
            graph_builder.add_edge("tool_resolver", "speculative_merge")
            graph_builder.add_edge("speculative_merge", "execution_router")
            graph_builder.add_edge("execution_router", "domain_planner")
        elif hybrid_mode and not compare_mode:
            graph_builder.add_edge("tool_resolver", "execution_router")
            graph_builder.add_edge("execution_router", "domain_planner")
        else:
            graph_builder.add_edge("tool_resolver", "domain_planner")
        graph_builder.add_edge("domain_planner", "execution_hitl_gate")
        graph_builder.add_conditional_edges(
            "execution_hitl_gate",
            execution_hitl_should_continue,
            path_map=["executor", END],
        )
        graph_builder.add_conditional_edges(
            "executor",
            executor_should_continue,
            path_map=["tools", "critic"],
        )
        graph_builder.add_edge("tools", "post_tools")
        graph_builder.add_edge("post_tools", "artifact_indexer")
        graph_builder.add_edge("artifact_indexer", "context_compactor")
        graph_builder.add_edge("context_compactor", "orchestration_guard")
        graph_builder.add_edge("orchestration_guard", "critic")
        graph_builder.add_conditional_edges(
            "critic",
            critic_should_continue,
            path_map=["synthesis_hitl", "tool_resolver", "planner"],
        )
        graph_builder.add_conditional_edges(
            "synthesis_hitl",
            synthesis_hitl_should_continue,
            path_map=[
                *(
                    ["progressive_synthesizer"]
                    if hybrid_mode and not compare_mode
                    else []
                ),
                "synthesizer",
                END,
            ],
        )
        if hybrid_mode and not compare_mode:
            graph_builder.add_edge("progressive_synthesizer", "synthesizer")
        graph_builder.add_edge("synthesizer", "response_layer_router")
        graph_builder.add_edge("response_layer_router", "response_layer")
        graph_builder.add_edge("response_layer", END)

    return graph_builder.compile(checkpointer=checkpointer, name="supervisor-agent")
