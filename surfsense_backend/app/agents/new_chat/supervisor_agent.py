from __future__ import annotations

import asyncio
import ast
import json
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Annotated, TypedDict
from uuid import UUID

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.types import Checkpointer
from langgraph_bigtool.graph import END, StateGraph, ToolNode, RunnableCallable
from langgraph_bigtool.tools import InjectedState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.bigtool_store import (
    _tokenize,
    _normalize_text,
    build_global_tool_registry,
    build_tool_index,
    smart_retrieve_tools_with_breakdown,
)
from app.agents.new_chat.bigtool_workers import WorkerConfig
from app.agents.new_chat.nodes import (
    build_agent_resolver_node,
    build_critic_node,
    build_domain_planner_node,
    build_execution_router_node,
    build_executor_nodes,
    build_execution_hitl_gate_node,
    build_intent_resolver_node,
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
from app.agents.new_chat.hybrid_state import (
    build_speculative_candidates,
    build_trivial_response,
    classify_graph_complexity,
)
from app.agents.new_chat.episodic_memory import (
    get_or_create_episodic_store,
    infer_ttl_seconds,
)
from app.agents.new_chat.retrieval_feedback import (
    get_global_retrieval_feedback_store,
    hydrate_global_retrieval_feedback_store,
)
from app.agents.new_chat.sandbox_runtime import sandbox_write_text_file
from app.agents.new_chat.shared_worker_pool import get_or_create_shared_worker_pool
from app.agents.new_chat.prompt_registry import resolve_prompt
from app.agents.new_chat.system_prompt import (
    SURFSENSE_CORE_GLOBAL_PROMPT,
    append_datetime_context,
    inject_core_prompt,
)
from app.agents.new_chat.response_compressor import compress_response
from app.agents.new_chat.subagent_utils import SMALLTALK_INSTRUCTIONS
from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
from app.agents.new_chat.marketplace_tools import MARKETPLACE_TOOL_DEFINITIONS
from app.agents.new_chat.marketplace_prompts import DEFAULT_MARKETPLACE_SYSTEM_PROMPT
from app.agents.new_chat.compare_prompts import DEFAULT_COMPARE_ANALYSIS_PROMPT
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
from app.agents.new_chat.supervisor_pipeline_prompts import (
    DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
    DEFAULT_SUPERVISOR_DOMAIN_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE,
    DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE,
    DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE,
    DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_MULTI_DOMAIN_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
    DEFAULT_SUPERVISOR_TOOL_RESOLVER_PROMPT,
    DEFAULT_RESPONSE_LAYER_ANALYS_PROMPT,
    DEFAULT_RESPONSE_LAYER_KUNSKAP_PROMPT,
    DEFAULT_RESPONSE_LAYER_ROUTER_PROMPT,
    DEFAULT_RESPONSE_LAYER_SYNTES_PROMPT,
    DEFAULT_RESPONSE_LAYER_VISUALISERING_PROMPT,
)
from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
from app.agents.new_chat.statistics_prompts import build_statistics_system_prompt
from app.agents.new_chat.system_prompt import append_datetime_context
from app.agents.new_chat.token_budget import TokenBudget
from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.smhi import SMHI_TOOL_DEFINITIONS
from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.domain_fan_out import (
    execute_domain_fan_out,
    format_fan_out_context,
    is_fan_out_enabled,
)
from app.agents.new_chat.tools.external_models import (
    DEFAULT_EXTERNAL_SYSTEM_PROMPT,
    EXTERNAL_MODEL_SPECS,
    call_external_model,
)
from app.agents.new_chat.tools.reflect_on_progress import create_reflect_on_progress_tool
from app.agents.new_chat.tools.write_todos import create_write_todos_tool
from app.db import AgentComboCache, UserMemory
from app.services.cache_control import is_cache_disabled
from app.services.reranker_service import RerankerService
from app.services.retrieval_feedback_persistence_service import (
    load_retrieval_feedback_snapshot,
    persist_retrieval_feedback_signal,
)
from app.services.agent_metadata_service import get_effective_agent_metadata
from app.services.tool_retrieval_tuning_service import (
    get_global_tool_retrieval_tuning,
    normalize_tool_retrieval_tuning,
)
from app.services.tool_metadata_service import get_global_tool_metadata_overrides


logger = logging.getLogger(__name__)


# Import from extracted modules
from app.agents.new_chat.supervisor_constants import (
    _AGENT_CACHE_TTL,
    _AGENT_COMBO_CACHE,
    _AGENT_EMBED_CACHE,
    _AGENT_NAME_ALIAS_MAP,
    _AGENT_STOPWORDS,
    _AGENT_TOOL_PROFILE_BY_ID,
    _AGENT_TOOL_PROFILES,
    _ARTIFACT_CONTEXT_MAX_ITEMS,
    _ARTIFACT_DEFAULT_MAX_ENTRIES,
    _ARTIFACT_DEFAULT_OFFLOAD_THRESHOLD_CHARS,
    _ARTIFACT_DEFAULT_STORAGE_MODE,
    _ARTIFACT_INTERNAL_TOOL_NAMES,
    _ARTIFACT_LOCAL_ROOT,
    _ARTIFACT_OFFLOAD_PER_PASS_LIMIT,
    _BLOCKED_RESPONSE_MARKERS,
    _COMPARE_FOLLOWUP_RE,
    _CONTEXT_COMPACTION_DEFAULT_STEP_KEEP,
    _CONTEXT_COMPACTION_DEFAULT_SUMMARY_MAX_CHARS,
    _CONTEXT_COMPACTION_DEFAULT_TRIGGER_RATIO,
    _CONTEXT_COMPACTION_MIN_MESSAGES,
    _DYNAMIC_TOOL_QUERY_MARKERS,
    _EXPLICIT_FILE_READ_RE,
    _EXTERNAL_MODEL_TOOL_NAMES,
    _FILESYSTEM_INTENT_RE,
    _FILESYSTEM_NOT_FOUND_MARKERS,
    _LIVE_ROUTING_PHASE_ORDER,
    _LOOP_GUARD_MAX_CONSECUTIVE,
    _LOOP_GUARD_TOOL_NAMES,
    _MAP_INTENT_RE,
    _MARKETPLACE_INTENT_RE,
    _MARKETPLACE_PROVIDER_RE,
    _MAX_AGENT_HOPS_PER_TURN,
    _MISSING_FIELD_HINTS,
    _MISSING_SIGNAL_RE,
    _RESULT_STATUS_VALUES,
    _ROUTE_STRICT_AGENT_POLICIES,
    _SANDBOX_ALIAS_TOOL_IDS,
    _SANDBOX_CODE_TOOL_IDS,
    _SPECIALIZED_AGENTS,
    _SUBAGENT_ARTIFACT_RE,
    _SUBAGENT_DEFAULT_CONTEXT_MAX_CHARS,
    _SUBAGENT_DEFAULT_MAX_CONCURRENCY,
    _SUBAGENT_DEFAULT_RESULT_MAX_CHARS,
    _SUBAGENT_MAX_HANDOFFS_IN_PROMPT,
    _TRAFFIC_INCIDENT_STRICT_RE,
    _TRAFFIC_INTENT_RE,
    _TRAFFIC_STRICT_INTENT_RE,
    _UNAVAILABLE_RESPONSE_MARKERS,
    _WEATHER_INTENT_RE,
    _live_phase_enabled,
    _normalize_live_routing_phase,
    AGENT_EMBEDDING_WEIGHT,
    AGENT_RERANK_CANDIDATES,
    AgentToolProfile,
    KEEP_TOOL_MSG_COUNT,
    MESSAGE_PRUNING_THRESHOLD,
    TOOL_CONTEXT_DROP_KEYS,
    TOOL_CONTEXT_MAX_CHARS,
    TOOL_CONTEXT_MAX_ITEMS,
    TOOL_MSG_THRESHOLD,
    MAX_TOTAL_STEPS,
)
from app.agents.new_chat.supervisor_types import (
    AgentDefinition,
    SupervisorState,
    _append_artifact_manifest,
    _append_compare_outputs,
    _append_recent,
    _append_subagent_handoffs,
    _replace,
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
    _looks_complete_unavailability_answer,
    _normalize_agent_identifier,
    _normalize_route_hint_value,
    _route_allowed_agents,
    _route_default_agent,
    _score_tool_profile,
    _select_focused_tool_profiles,
    _tokenize_focus_terms,
)
from app.agents.new_chat.supervisor_text_utils import (
    _coerce_confidence,
    _coerce_float_range,
    _coerce_int_range,
    _dedupe_repeated_lines,
    _extract_first_json_object,
    _normalize_citation_spacing,
    _normalize_line_for_dedupe,
    _parse_hitl_confirmation,
    _remove_inline_critic_payloads,
    _render_hitl_message,
    _safe_id_segment,
    _safe_json,
    _serialize_artifact_payload,
    _strip_critic_json,
    _truncate_for_prompt,
)
from app.agents.new_chat.supervisor_cache import (
    _build_cache_key,
    _fetch_cached_combo_db,
    _get_cached_combo,
    _set_cached_combo,
    _store_cached_combo_db,
    clear_agent_combo_cache,
)
from app.agents.new_chat.supervisor_agent_retrieval import (
    _build_agent_rerank_text,
    _cosine_similarity,
    _get_agent_embedding,
    _normalize_vector,
    _rerank_agents,
    _score_agent,
    _smart_retrieve_agents,
    _smart_retrieve_agents_with_breakdown,
)
from app.agents.new_chat.supervisor_tools import (
    _build_scoped_prompt_for_agent,
    _build_tool_prompt_block,
    _default_prompt_for_tool_id,
    _fallback_tool_ids_for_tool,
    _format_prompt_template,
    _normalize_tool_id_list,
    _sanitize_selected_tool_ids_for_worker,
    _tool_prompt_for_id,
    _worker_available_tool_ids,
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
from app.agents.new_chat.supervisor_memory import (
    _artifact_runtime_hitl_thread_scope,
    _persist_artifact_content,
    _render_cross_session_memory_context,
    _select_cross_session_memory_entries,
    _tokenize_for_memory_relevance,
)














_MAX_TOOL_CALLS_PER_TURN = 12
_MAX_SUPERVISOR_TOOL_CALLS_PER_STEP = 1
_MAX_REPLAN_ATTEMPTS = 2



_HITL_APPROVE_RE = re.compile(r"\b(ja|yes|ok|okej|kor|kör|go|fortsatt|fortsätt)\b", re.IGNORECASE)
_HITL_REJECT_RE = re.compile(r"\b(nej|no|stopp|avbryt|stop|inte)\b", re.IGNORECASE)








def _infer_tool_name_from_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    if "agent" in payload and "task" in payload and "result_contract" in payload:
        return "call_agent"
    if isinstance(payload.get("results"), list):
        return "call_agents_parallel"
    if "todos" in payload:
        return "write_todos"
    if "reflection" in payload:
        return "reflect_on_progress"
    return ""


def _resolve_tool_message_name(
    message: ToolMessage,
    *,
    tool_call_index: dict[str, str] | None = None,
) -> str:
    explicit_name = str(getattr(message, "name", "") or "").strip()
    if explicit_name:
        return explicit_name
    tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
    if tool_call_id and tool_call_index:
        indexed_name = str(tool_call_index.get(tool_call_id) or "").strip()
        if indexed_name:
            return indexed_name
    payload_name = _infer_tool_name_from_payload(_safe_json(getattr(message, "content", "")))
    return payload_name


def _tool_call_priority(
    tool_name: str,
    *,
    orchestration_phase: str,
    agent_hops: int,
    execution_strategy: str = "",
    state: dict[str, Any] | None = None,
) -> int:
    normalized_tool = str(tool_name or "").strip()
    phase = str(orchestration_phase or "").strip().lower()
    strategy = str(execution_strategy or "").strip().lower()
    selected_agents_present = bool(_selected_agent_names_from_state(state))
    pending_plan_steps = _has_followup_plan_steps(state)
    if strategy in {"parallel", "subagent"}:
        preferred = {
            "call_agents_parallel": 0,
            "call_agent": 1,
            "retrieve_agents": 2,
            "write_todos": 3,
            "reflect_on_progress": 4,
        }
        if normalized_tool in _EXTERNAL_MODEL_TOOL_NAMES:
            return 5
        return preferred.get(normalized_tool, 99)
    prefer_retrieval = (
        phase == "select_agent" and not selected_agents_present and agent_hops <= 0
    ) or (
        phase in {"execute", "resolve_tools", "validate_agent_output"}
        and not selected_agents_present
        and not pending_plan_steps
        and agent_hops <= 0
    )
    if prefer_retrieval:
        ordering = {
            "retrieve_agents": 0,
            "call_agent": 1,
            "call_agents_parallel": 2,
            "write_todos": 3,
            "reflect_on_progress": 4,
        }
    else:
        ordering = {
            "call_agent": 0,
            "call_agents_parallel": 1,
            "retrieve_agents": 2,
            "write_todos": 3,
            "reflect_on_progress": 4,
        }
    if normalized_tool in _EXTERNAL_MODEL_TOOL_NAMES:
        return 5
    return ordering.get(normalized_tool, 99)


def _has_followup_plan_steps(state: dict[str, Any] | None) -> bool:
    if not isinstance(state, dict):
        return False
    if bool(state.get("plan_complete")):
        return False
    plan_items = state.get("active_plan") or []
    if not isinstance(plan_items, list) or not plan_items:
        return False
    try:
        step_index = int(state.get("plan_step_index") or 0)
    except (TypeError, ValueError):
        step_index = 0
    step_index = max(0, step_index)
    for idx, item in enumerate(plan_items):
        if idx < step_index:
            continue
        if not isinstance(item, dict):
            return True
        status = str(item.get("status") or "").strip().lower()
        if status not in {"completed", "cancelled", "done"}:
            return True
    if step_index < len(plan_items):
        # Defensive fallback when plan statuses are missing or stale.
        return True
    return False


def _projected_followup_plan_steps(
    *,
    state: dict[str, Any],
    active_plan: list[dict[str, Any]] | None,
    plan_complete: bool | None,
    completed_steps_count: int,
) -> bool:
    projected_plan = (
        [item for item in (active_plan or []) if isinstance(item, dict)]
        if isinstance(active_plan, list)
        else [item for item in (state.get("active_plan") or []) if isinstance(item, dict)]
    )
    projected_complete = (
        bool(plan_complete)
        if plan_complete is not None
        else bool(state.get("plan_complete"))
    )
    projected_step_index = min(
        max(0, int(completed_steps_count)),
        len(projected_plan),
    )
    return _has_followup_plan_steps(
        {
            "active_plan": projected_plan,
            "plan_complete": projected_complete,
            "plan_step_index": projected_step_index,
        }
    )


def _selected_agent_names_from_state(state: dict[str, Any] | None) -> list[str]:
    if not isinstance(state, dict):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for item in state.get("selected_agents") or []:
        if isinstance(item, dict):
            normalized = str(item.get("name") or "").strip().lower()
        else:
            normalized = str(item or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(normalized)
    return names


def _next_plan_step_text(state: dict[str, Any] | None) -> str:
    if not isinstance(state, dict):
        return ""
    plan_items = state.get("active_plan") or []
    if not isinstance(plan_items, list) or not plan_items:
        return ""
    try:
        step_index = int(state.get("plan_step_index") or 0)
    except (TypeError, ValueError):
        step_index = 0
    step_index = max(0, step_index)
    for idx, item in enumerate(plan_items):
        if idx < step_index:
            continue
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        status = str(item.get("status") or "pending").strip().lower()
        if not content:
            continue
        if status in {"completed", "cancelled", "done"}:
            continue
        return content
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if content:
            return content
    return ""


def _coerce_redundant_retrieve_call(
    tool_calls: list[dict[str, Any]],
    *,
    orchestration_phase: str,
    state: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(state, dict):
        return tool_calls, False
    phase = str(orchestration_phase or "").strip().lower()
    if phase not in {"execute", "resolve_tools", "validate_agent_output"}:
        return tool_calls, False
    if len(tool_calls) != 1:
        return tool_calls, False
    only_call = tool_calls[0]
    if str(only_call.get("name") or "").strip() != "retrieve_agents":
        return tool_calls, False
    if str(_normalize_route_hint_value(state.get("route_hint")) or "") in {"jämförelse", "compare"}:
        return tool_calls, False
    selected_agents = _selected_agent_names_from_state(state)
    if len(selected_agents) != 1:
        return tool_calls, False
    has_pending_plan_steps = _has_followup_plan_steps(state)
    graph_complexity = str(state.get("graph_complexity") or "").strip().lower()
    simple_single_agent_turn = graph_complexity == "simple"
    if not has_pending_plan_steps and not simple_single_agent_turn:
        return tool_calls, False
    call_args = only_call.get("args")
    retrieve_query = (
        str(call_args.get("query") or "").strip()
        if isinstance(call_args, dict)
        else ""
    )
    task_text = _latest_user_query(state.get("messages") or [])
    if not task_text:
        task_text = _next_plan_step_text(state)
    if not task_text:
        task_text = retrieve_query
    if not task_text:
        return tool_calls, False
    coerced_call = dict(only_call)
    coerced_call["name"] = "call_agent"
    coerced_call["args"] = {
        "agent_name": selected_agents[0],
        "task": task_text,
        "final": False,
    }
    return [coerced_call], True


def _coerce_supervisor_tool_calls(
    message: Any,
    *,
    orchestration_phase: str,
    agent_hops: int,
    execution_strategy: str,
    allow_multiple: bool,
    state: dict[str, Any] | None = None,
) -> Any:
    if allow_multiple or not isinstance(message, AIMessage):
        return message
    tool_calls = [
        tool_call
        for tool_call in (getattr(message, "tool_calls", None) or [])
        if isinstance(tool_call, dict)
    ]
    coerce_final = _has_followup_plan_steps(state)
    changed = False
    if coerce_final and tool_calls:
        coerced_tool_calls: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            if str(tool_call.get("name") or "").strip() != "call_agent":
                coerced_tool_calls.append(tool_call)
                continue
            raw_args = tool_call.get("args")
            if not isinstance(raw_args, dict) or not bool(raw_args.get("final")):
                coerced_tool_calls.append(tool_call)
                continue
            coerced_args = dict(raw_args)
            coerced_args["final"] = False
            coerced_call = dict(tool_call)
            coerced_call["args"] = coerced_args
            coerced_tool_calls.append(coerced_call)
            changed = True
        if changed:
            tool_calls = coerced_tool_calls
    tool_calls, retrieve_changed = _coerce_redundant_retrieve_call(
        tool_calls,
        orchestration_phase=orchestration_phase,
        state=state,
    )
    changed = changed or retrieve_changed
    if len(tool_calls) <= _MAX_SUPERVISOR_TOOL_CALLS_PER_STEP:
        if not changed:
            return message
        try:
            return message.model_copy(update={"tool_calls": tool_calls})
        except Exception:
            return AIMessage(
                content=str(getattr(message, "content", "") or ""),
                tool_calls=tool_calls,
                additional_kwargs=dict(getattr(message, "additional_kwargs", {}) or {}),
                response_metadata=dict(getattr(message, "response_metadata", {}) or {}),
                id=getattr(message, "id", None),
            )
    ranked = sorted(
        enumerate(tool_calls),
        key=lambda item: (
            _tool_call_priority(
                str(item[1].get("name") or ""),
                orchestration_phase=orchestration_phase,
                agent_hops=agent_hops,
                execution_strategy=execution_strategy,
                state=state,
            ),
            item[0],
        ),
    )
    chosen_call = ranked[0][1]
    try:
        return message.model_copy(update={"tool_calls": [chosen_call]})
    except Exception:
        return AIMessage(
            content=str(getattr(message, "content", "") or ""),
            tool_calls=[chosen_call],
            additional_kwargs=dict(getattr(message, "additional_kwargs", {}) or {}),
            response_metadata=dict(getattr(message, "response_metadata", {}) or {}),
            id=getattr(message, "id", None),
        )


def _sanitize_openai_tool_schema(value: Any) -> Any:
    """
    Remove null defaults/variants from tool schemas for strict Jinja templates.
    LM Studio templates can fail on `default: null` or explicit `type: null`.

    ``description`` fields are preserved with an empty string rather than
    dropped — the nemotron-3-nano Jinja template accesses
    ``tool.function.description | string`` unconditionally.  A missing key
    resolves to NullValue in LM Studio's Jinja engine, crashing the template.
    """
    # Keys that model templates access unconditionally.  Dropping them causes
    # "Cannot apply filter 'string' to type: NullValue" in LM Studio.
    _KEEP_AS_EMPTY_STRING = {"description"}

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if item is None:
                if key in _KEEP_AS_EMPTY_STRING:
                    sanitized[key] = ""
                continue
            if key == "default" and item is None:
                continue
            if key in {"anyOf", "oneOf", "allOf"} and isinstance(item, list):
                variants: list[Any] = []
                for variant in item:
                    cleaned_variant = _sanitize_openai_tool_schema(variant)
                    if (
                        isinstance(cleaned_variant, dict)
                        and str(cleaned_variant.get("type") or "").strip().lower()
                        == "null"
                    ):
                        continue
                    variants.append(cleaned_variant)
                if variants:
                    sanitized[key] = variants
                continue
            sanitized[key] = _sanitize_openai_tool_schema(item)

        properties = sanitized.get("properties")
        required = sanitized.get("required")
        required_set = {
            str(field).strip()
            for field in (required if isinstance(required, list) else [])
            if str(field).strip()
        }
        if isinstance(properties, dict):
            cleaned_properties: dict[str, Any] = {}
            for prop_name, prop_schema in properties.items():
                normalized_name = str(prop_name or "").strip()
                # Injected runtime state must never be exposed in the model-facing schema.
                if normalized_name == "state":
                    continue
                cleaned_schema = _sanitize_openai_tool_schema(prop_schema)
                if isinstance(cleaned_schema, dict):
                    if (
                        "default" not in cleaned_schema
                        and normalized_name not in required_set
                    ):
                        inferred_default = _infer_non_null_tool_default(cleaned_schema)
                        if inferred_default is not None:
                            cleaned_schema["default"] = inferred_default
                cleaned_properties[normalized_name] = cleaned_schema
            sanitized["properties"] = cleaned_properties
            properties = cleaned_properties

        if isinstance(required, list) and isinstance(properties, dict):
            kept_required = [
                str(field).strip()
                for field in required
                if isinstance(field, str) and str(field).strip() in properties
            ]
            if kept_required:
                sanitized["required"] = kept_required
            else:
                sanitized.pop("required", None)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_openai_tool_schema(item) for item in value]
    return value


def _infer_non_null_tool_default(schema: dict[str, Any]) -> Any:
    type_name = str(schema.get("type") or "").strip().lower()
    if type_name == "boolean":
        return False
    if type_name == "string":
        return ""
    if type_name == "integer":
        return 0
    if type_name == "number":
        return 0
    if type_name == "array":
        return []
    if type_name == "object":
        return {}

    for union_key in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(union_key)
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            inferred = _infer_non_null_tool_default(variant)
            if inferred is not None:
                return inferred
    return None


def _format_tools_for_llm_binding(tools: list[Any]) -> list[dict[str, Any]]:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    formatted: list[dict[str, Any]] = []
    for tool_def in tools:
        try:
            raw = tool_def if isinstance(tool_def, dict) else convert_to_openai_tool(tool_def)
        except Exception:
            logger.debug("Failed to convert tool for llm binding", exc_info=True)
            continue
        cleaned = _sanitize_openai_tool_schema(raw)
        if isinstance(cleaned, dict):
            # Guarantee that function.description always exists — strict Jinja
            # templates (nemotron-3-nano) access it without null guards.
            func = cleaned.get("function")
            if isinstance(func, dict) and "description" not in func:
                func["description"] = ""
            formatted.append(cleaned)
    return formatted



def _render_guard_message(template: str, preview_lines: list[str]) -> str:
    preview_block = ""
    if preview_lines:
        preview_block = "Detta ar de senaste delresultaten:\n" + "\n".join(
            [str(item) for item in preview_lines[:3] if str(item).strip()]
        )
    try:
        rendered = str(template or "").format(recent_preview=preview_block)
    except Exception:
        rendered = str(template or "")
    rendered = rendered.strip()
    if preview_block and "{recent_preview}" not in str(template or ""):
        if preview_block not in rendered:
            rendered = (rendered + "\n" + preview_block).strip()
    return rendered


def _current_turn_key(state: dict[str, Any] | None) -> str:
    if not state:
        return "turn"
    active_turn_id = str(state.get("active_turn_id") or state.get("turn_id") or "").strip()
    if active_turn_id:
        digest = hashlib.sha1(active_turn_id.encode("utf-8")).hexdigest()
        return f"t{digest[:12]}"
    messages = state.get("messages") or []
    latest_human: HumanMessage | None = None
    human_count = 0
    for message in messages:
        if isinstance(message, HumanMessage):
            human_count += 1
            latest_human = message
    if latest_human is not None:
        message_id = str(getattr(latest_human, "id", "") or "").strip()
        content = str(getattr(latest_human, "content", "") or "").strip()
        seed = message_id or content or f"human:{human_count}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
        return f"h{human_count}:{digest[:12]}"
    return "turn"


def _latest_user_query(messages: list[Any] | None) -> str:
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return str(getattr(message, "content", "") or "").strip()
    return ""


def _tool_names_from_messages(messages: list[Any] | None) -> list[str]:
    names: list[str] = []
    tool_call_index = _tool_call_name_index(messages)
    for message in messages or []:
        if not isinstance(message, ToolMessage):
            continue
        name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if name and name not in names:
            names.append(name)
    return names


def _infer_missing_fields(response_text: str) -> list[str]:
    text = str(response_text or "").strip().lower()
    if not text or not _MISSING_SIGNAL_RE.search(text):
        return []
    missing: list[str] = []
    for field_name, hints in _MISSING_FIELD_HINTS:
        if any(hint in text for hint in hints):
            missing.append(field_name)
    return missing[:6]


def _looks_blocked_agent_response(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _BLOCKED_RESPONSE_MARKERS)


def _normalize_result_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in _RESULT_STATUS_VALUES:
        return status
    return "partial"


def _compute_contract_confidence(
    *,
    status: str,
    response_text: str,
    actionable: bool,
    missing_fields: list[str],
    used_tool_count: int,
    final_requested: bool,
) -> float:
    base = 0.45
    if status == "success":
        base = 0.78
    elif status == "blocked":
        base = 0.24
    elif status == "error":
        base = 0.08

    if actionable:
        base += 0.08
    if used_tool_count > 0:
        base += 0.05
    if used_tool_count >= 2:
        base += 0.03

    response_len = len(str(response_text or "").strip())
    if response_len >= 200:
        base += 0.05
    elif response_len < 40:
        base -= 0.10

    if missing_fields:
        base -= min(0.24, 0.08 * len(missing_fields))
    if final_requested and status == "success":
        base += 0.03

    base = max(0.01, min(0.99, base))
    return round(float(base), 2)


def _build_agent_result_contract(
    *,
    agent_name: str,
    task: str,
    response_text: str,
    error_text: str = "",
    used_tools: list[str] | None = None,
    final_requested: bool = False,
) -> dict[str, Any]:
    cleaned_response = _strip_critic_json(str(response_text or "").strip())
    error_value = str(error_text or "").strip()
    used_tool_names = [str(item).strip() for item in (used_tools or []) if str(item).strip()]
    missing_fields = _infer_missing_fields(cleaned_response)
    actionable = _looks_actionable_agent_answer(cleaned_response)
    blocked = _looks_blocked_agent_response(cleaned_response)
    complete_unavailable = _looks_complete_unavailability_answer(cleaned_response)

    if error_value:
        status = "error"
    elif not cleaned_response:
        status = "partial"
    elif complete_unavailable:
        status = "success"
        actionable = True
    elif blocked and not actionable:
        status = "blocked"
    elif missing_fields and not actionable:
        status = "partial"
    elif actionable:
        status = "success"
    else:
        status = "partial"

    confidence = _compute_contract_confidence(
        status=status,
        response_text=cleaned_response,
        actionable=actionable,
        missing_fields=missing_fields,
        used_tool_count=len(used_tool_names),
        final_requested=bool(final_requested),
    )
    retry_recommended = status in {"partial", "blocked", "error"}
    if status == "success" and confidence < 0.55:
        retry_recommended = True

    if status == "error":
        reason = (
            f"Agentfel: {error_value[:140]}"
            if error_value
            else "Agentkorningen misslyckades."
        )
    elif status == "blocked":
        reason = "Svar saknar tillrackligt underlag eller kraver annan agent."
    elif status == "partial":
        if missing_fields:
            reason = "Saknade falt: " + ", ".join(missing_fields[:4])
        else:
            reason = "Svar finns men bedoms inte komplett nog for finalisering."
    else:
        reason = "Svar bedoms tillrackligt komplett for finalisering."

    return {
        "status": status,
        "confidence": confidence,
        "actionable": bool(actionable),
        "missing_fields": missing_fields,
        "retry_recommended": bool(retry_recommended),
        "used_tools": used_tool_names[:6],
        "reason": reason,
        "agent": str(agent_name or "").strip(),
        "task_hash": hashlib.sha1(str(task or "").encode("utf-8")).hexdigest()[:12],
    }


def _contract_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    raw_contract = source.get("result_contract")
    if isinstance(raw_contract, dict):
        normalized_status = _normalize_result_status(raw_contract.get("status"))
        try:
            confidence = float(raw_contract.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = round(max(0.0, min(1.0, confidence)), 2)
        missing_fields_raw = raw_contract.get("missing_fields")
        missing_fields = (
            [
                str(item).strip()
                for item in missing_fields_raw
                if str(item).strip()
            ][:6]
            if isinstance(missing_fields_raw, list)
            else []
        )
        used_tools_raw = raw_contract.get("used_tools")
        used_tools = (
            [str(item).strip() for item in used_tools_raw if str(item).strip()][:6]
            if isinstance(used_tools_raw, list)
            else []
        )
        reason = str(raw_contract.get("reason") or "").strip()
        if not reason:
            reason = "Resultatkontrakt utan forklaring."
        if confidence <= 0.0 and (
            str(source.get("response") or "").strip() or str(source.get("error") or "").strip()
        ):
            fallback = _build_agent_result_contract(
                agent_name=str(source.get("agent") or ""),
                task=str(source.get("task") or ""),
                response_text=str(source.get("response") or ""),
                error_text=str(source.get("error") or ""),
                used_tools=used_tools,
                final_requested=bool(source.get("final")),
            )
            confidence = float(fallback.get("confidence") or confidence)
            if normalized_status == "partial":
                normalized_status = _normalize_result_status(fallback.get("status"))
            if not missing_fields:
                missing_fields = list(fallback.get("missing_fields") or [])
            if not reason:
                reason = str(fallback.get("reason") or "").strip()
        return {
            "status": normalized_status,
            "confidence": confidence,
            "actionable": bool(raw_contract.get("actionable")),
            "missing_fields": missing_fields,
            "retry_recommended": bool(raw_contract.get("retry_recommended")),
            "used_tools": used_tools,
            "reason": reason,
            "agent": str(raw_contract.get("agent") or source.get("agent") or "").strip(),
            "task_hash": str(raw_contract.get("task_hash") or "").strip(),
        }

    fallback_tools = source.get("used_tools")
    fallback_tool_list = (
        [str(item).strip() for item in fallback_tools if str(item).strip()]
        if isinstance(fallback_tools, list)
        else []
    )
    return _build_agent_result_contract(
        agent_name=str(source.get("agent") or ""),
        task=str(source.get("task") or ""),
        response_text=str(source.get("response") or ""),
        error_text=str(source.get("error") or ""),
        used_tools=fallback_tool_list,
        final_requested=bool(source.get("final")),
    )


def _should_finalize_from_contract(
    *,
    contract: dict[str, Any],
    response_text: str,
    route_hint: str,
    agent_name: str,
    latest_user_query: str,
    agent_hops: int,
) -> bool:
    response = _strip_critic_json(str(response_text or "").strip())
    if not response:
        return False
    if str(route_hint or "").strip().lower() in {"jämförelse", "compare"}:
        return False

    status = _normalize_result_status(contract.get("status"))
    actionable = bool(contract.get("actionable"))
    try:
        confidence = float(contract.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    missing_fields = contract.get("missing_fields")
    missing_count = len(missing_fields) if isinstance(missing_fields, list) else 0

    if status == "success" and actionable and confidence >= 0.55 and missing_count <= 1:
        return True

    normalized_agent = str(agent_name or "").strip().lower()
    if (
        str(route_hint or "").strip().lower() in {"action", "skapande"}
        and normalized_agent == "trafik"
        and _has_strict_trafik_intent(latest_user_query)
        and actionable
        and status in {"success", "partial"}
        and confidence >= 0.45
        and missing_count <= 1
    ):
        return True

    if (
        agent_hops >= 2
        and actionable
        and status in {"success", "partial"}
        and confidence >= 0.60
        and missing_count == 0
    ):
        return True
    return False


def _normalize_task_for_fingerprint(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    value = re.sub(r"[^a-z0-9åäö\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180]


def _agent_call_entries_since_last_user(
    messages: list[Any] | None,
    *,
    turn_id: str | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    expected_turn_id = str(turn_id or "").strip()
    tool_call_index = _tool_call_name_index(messages)
    for message in messages or []:
        if isinstance(message, HumanMessage):
            entries = []
            continue
        if not isinstance(message, ToolMessage):
            continue
        resolved_name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if resolved_name != "call_agent":
            continue
        payload = _safe_json(getattr(message, "content", ""))
        if not isinstance(payload, dict):
            continue
        payload_turn_id = str(payload.get("turn_id") or "").strip()
        if expected_turn_id and payload_turn_id != expected_turn_id:
            continue
        entries.append(payload)
    return entries


def _looks_actionable_agent_answer(text: str) -> bool:
    value = str(text or "").strip()
    if len(value) < 32:
        return False
    lowered = value.lower()
    rejection_markers = (
        "jag kan inte",
        "jag kunde inte",
        "kan tyvarr inte",
        "kan tyvärr inte",
        "jag saknar",
        "jag behover",
        "jag behöver",
        "behover mer information",
        "behöver mer information",
        "inte möjligt",
        "not available",
        "cannot answer",
        "specificera",
        "ange mer",
    )
    if "inga " in lowered and (
        "hittades" in lowered
        or "fanns" in lowered
        or "rapporterades" in lowered
    ):
        return True
    return not any(marker in lowered for marker in rejection_markers)


def _query_requests_capability_overview(query: str) -> bool:
    lowered = str(query or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "vad kan du",
        "vad kan ni",
        "what can you do",
        "what are your capabilities",
        "vilka verktyg har du",
        "vad hjälper du med",
        "vad kan oneseek",
    )
    return any(marker in lowered for marker in markers)


def _is_generic_capability_answer(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "jag kan hjälpa dig med olika uppgifter",
        "här är några exempel på vad jag kan göra",
        "vill du ha hjälp med något specifikt",
        "i can help you with different tasks",
        "here are some examples of what i can do",
    )
    return any(marker in lowered for marker in markers)


def _latest_actionable_ai_response(
    messages: list[Any],
    *,
    latest_user_query: str,
) -> str | None:
    allow_capability_response = _query_requests_capability_overview(latest_user_query)
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, AIMessage):
            continue
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            continue
        response = _strip_critic_json(str(getattr(message, "content", "") or "").strip())
        if not response:
            continue
        lowered = response.lower()
        if "jag fastnade i en planeringsloop" in lowered:
            continue
        if _is_generic_capability_answer(response) and not allow_capability_response:
            continue
        if _looks_actionable_agent_answer(response) or allow_capability_response:
            return response
    return None


def _best_actionable_entry(entries: list[dict[str, Any]]) -> tuple[str, str] | None:
    best: tuple[tuple[int, int, float, int], tuple[str, str]] | None = None
    status_rank = {"success": 3, "partial": 2, "blocked": 1, "error": 0}
    for entry in entries:
        response = _strip_critic_json(str(entry.get("response") or "").strip())
        if not response:
            continue
        contract = _contract_from_payload(entry)
        status = _normalize_result_status(contract.get("status"))
        actionable = bool(contract.get("actionable")) or _looks_actionable_agent_answer(
            response
        )
        try:
            confidence = float(contract.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        score = (
            1 if actionable else 0,
            status_rank.get(status, 0),
            confidence,
            len(response),
        )
        agent_name = str(entry.get("agent") or "").strip() or "agent"
        if best is None or score > best[0]:
            best = (score, (response, agent_name))
    if best:
        return best[1]
    return None


def _build_subagent_id(
    *,
    base_thread_id: str,
    turn_key: str,
    agent_name: str,
    call_index: int,
    task: str,
) -> str:
    seed = "|".join(
        [
            str(base_thread_id or "").strip() or "thread",
            str(turn_key or "").strip() or "turn",
            str(agent_name or "").strip().lower() or "agent",
            str(max(0, int(call_index))),
            hashlib.sha1(str(task or "").encode("utf-8")).hexdigest()[:10],
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]
    agent_slug = _normalize_agent_identifier(agent_name) or "agent"
    return f"sa-{agent_slug[:18]}-{digest}"


def _extract_subagent_artifact_refs(text: str, *, limit: int = 4) -> list[str]:
    if not text:
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for match in _SUBAGENT_ARTIFACT_RE.findall(str(text or "")):
        normalized = str(match or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        refs.append(normalized)
        if len(refs) >= max(1, int(limit)):
            break
    return refs


def _build_subagent_handoff_payload(
    *,
    subagent_id: str,
    agent_name: str,
    response_text: str,
    result_contract: dict[str, Any] | None,
    result_max_chars: int,
    error_text: str = "",
) -> dict[str, Any]:
    contract = result_contract if isinstance(result_contract, dict) else {}
    response = _strip_critic_json(str(response_text or "").strip())
    summary = _truncate_for_prompt(response, max(180, int(result_max_chars)))
    findings: list[str] = []
    for line in response.splitlines():
        cleaned = str(line or "").strip(" -*")
        if not cleaned:
            continue
        findings.append(_truncate_for_prompt(cleaned, 180))
        if len(findings) >= 4:
            break
    if not findings and summary:
        findings = [_truncate_for_prompt(summary, 180)]
    status = _normalize_result_status(contract.get("status"))
    try:
        confidence = float(contract.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "subagent_id": str(subagent_id or "").strip(),
        "agent": str(agent_name or "").strip(),
        "status": status,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "summary": summary,
        "findings": findings,
        "artifact_refs": _extract_subagent_artifact_refs(response),
        "error": _truncate_for_prompt(str(error_text or "").strip(), 240),
    }



def _summarize_parallel_results(results: Any) -> str:
    if not isinstance(results, list) or not results:
        return "results=0"
    success_count = 0
    error_count = 0
    snippets: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        response = str(item.get("response") or "").strip()
        error = str(item.get("error") or "").strip()
        if error:
            error_count += 1
        elif response:
            success_count += 1
    for item in results[:TOOL_CONTEXT_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "agent").strip() or "agent"
        response = _strip_critic_json(str(item.get("response") or "").strip())
        error = str(item.get("error") or "").strip()
        if response:
            snippets.append(f"{agent}: {_truncate_for_prompt(response, 140)}")
        elif error:
            snippets.append(f"{agent}: error {_truncate_for_prompt(error, 100)}")
        else:
            snippets.append(f"{agent}: completed")
    summary = f"results={len(results)}; success={success_count}; errors={error_count}"
    if snippets:
        summary += "; outputs=" + " | ".join(snippets)
    return _truncate_for_prompt(summary)


def _build_rolling_context_summary(
    *,
    latest_user_query: str,
    active_plan: list[dict[str, Any]] | None,
    step_results: list[dict[str, Any]] | None,
    subagent_handoffs: list[dict[str, Any]] | None,
    artifact_manifest: list[dict[str, Any]] | None,
    targeted_missing_info: list[str] | None,
    max_chars: int,
) -> str:
    lines: list[str] = []
    user_query = str(latest_user_query or "").strip()
    if user_query:
        lines.append(f"User goal: {_truncate_for_prompt(user_query, 260)}")

    plan_items = [item for item in (active_plan or []) if isinstance(item, dict)]
    if plan_items:
        pending = [
            str(item.get("content") or "").strip()
            for item in plan_items
            if str(item.get("status") or "").strip().lower() in {"pending", "in_progress"}
            and str(item.get("content") or "").strip()
        ][:3]
        completed_count = sum(
            1
            for item in plan_items
            if str(item.get("status") or "").strip().lower() == "completed"
        )
        lines.append(
            f"Plan status: completed={completed_count}/{len(plan_items)}"
        )
        if pending:
            lines.append("Next steps: " + " | ".join(pending))

    compact_steps: list[str] = []
    for item in (step_results or [])[-_CONTEXT_COMPACTION_DEFAULT_STEP_KEEP:]:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "agent").strip() or "agent"
        task = _truncate_for_prompt(str(item.get("task") or "").strip(), 100)
        response = _truncate_for_prompt(
            _strip_critic_json(str(item.get("response") or "").strip()),
            180,
        )
        contract = item.get("result_contract")
        status = (
            _normalize_result_status(contract.get("status"))
            if isinstance(contract, dict)
            else "partial"
        )
        if response:
            compact_steps.append(f"- {agent} [{status}] {task} -> {response}")
    if compact_steps:
        lines.append("Recent execution:")
        lines.extend(compact_steps[:6])

    handoff_lines: list[str] = []
    for handoff in (subagent_handoffs or [])[-4:]:
        if not isinstance(handoff, dict):
            continue
        agent = str(handoff.get("agent") or "agent").strip() or "agent"
        summary = _truncate_for_prompt(str(handoff.get("summary") or "").strip(), 160)
        refs = handoff.get("artifact_refs")
        ref_text = ""
        if isinstance(refs, list):
            normalized = [str(item).strip() for item in refs if str(item).strip()][:2]
            if normalized:
                ref_text = f" refs={','.join(normalized)}"
        if summary:
            handoff_lines.append(f"- {agent}: {summary}{ref_text}")
    if handoff_lines:
        lines.append("Subagent handoffs:")
        lines.extend(handoff_lines)

    artifact_lines: list[str] = []
    for item in (artifact_manifest or [])[-4:]:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("artifact_uri") or item.get("artifact_path") or "").strip()
        if not ref:
            continue
        summary = _truncate_for_prompt(str(item.get("summary") or "").strip(), 140)
        if summary:
            artifact_lines.append(f"- {ref}: {summary}")
        else:
            artifact_lines.append(f"- {ref}")
    if artifact_lines:
        lines.append("Artifacts:")
        lines.extend(artifact_lines)

    missing = [str(item).strip() for item in (targeted_missing_info or []) if str(item).strip()]
    if missing:
        lines.append("Open gaps: " + " | ".join(missing[:4]))

    rendered = "\n".join(lines).strip()
    return _truncate_for_prompt(rendered, max(320, int(max_chars)))


def _count_consecutive_loop_tools(messages: list[Any], *, turn_id: str | None = None) -> int:
    count = 0
    expected_turn_id = str(turn_id or "").strip()
    tool_call_index = _tool_call_name_index(messages)
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, ToolMessage):
            continue
        name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if name == "call_agent":
            payload = _safe_json(getattr(message, "content", ""))
            payload_turn_id = (
                str(payload.get("turn_id") or "").strip()
                if isinstance(payload, dict)
                else ""
            )
            if expected_turn_id and payload_turn_id != expected_turn_id:
                break
            if isinstance(payload, dict) and str(payload.get("error") or "").strip():
                count += 1
                continue
            contract = _contract_from_payload(payload if isinstance(payload, dict) else {})
            status = _normalize_result_status(contract.get("status"))
            actionable = bool(contract.get("actionable"))
            try:
                confidence = float(contract.get("confidence"))
            except (TypeError, ValueError):
                confidence = 0.0
            if status == "success" and actionable and confidence >= 0.55:
                break
            if bool(contract.get("retry_recommended")) or status in {
                "partial",
                "blocked",
                "error",
            }:
                count += 1
                continue
            break
        if name in _LOOP_GUARD_TOOL_NAMES:
            count += 1
            continue
        break
    return count


def _summarize_tool_payload(tool_name: str, payload: dict[str, Any]) -> str:
    name = (tool_name or "tool").strip() or "tool"
    status = str(payload.get("status") or "completed").lower()
    parts: list[str] = [f"{name}: {status}"]

    if status == "error" or "error" in payload:
        error_text = _truncate_for_prompt(str(payload.get("error") or "Unknown error"), 300)
        return _truncate_for_prompt(f"{name}: error - {error_text}")

    if name == "write_todos":
        todos = payload.get("todos") or []
        if isinstance(todos, list):
            completed = sum(
                1
                for item in todos
                if isinstance(item, dict) and str(item.get("status") or "").lower() == "completed"
            )
            in_progress = sum(
                1
                for item in todos
                if isinstance(item, dict) and str(item.get("status") or "").lower() == "in_progress"
            )
            parts.append(f"todos={len(todos)}")
            parts.append(f"completed={completed}")
            parts.append(f"in_progress={in_progress}")
            task_names = [
                str(item.get("content") or "").strip()
                for item in todos
                if isinstance(item, dict) and str(item.get("content") or "").strip()
            ][:TOOL_CONTEXT_MAX_ITEMS]
            if task_names:
                parts.append("tasks=" + " | ".join(task_names))
            return _truncate_for_prompt("; ".join(parts))

    if name == "trafiklab_route":
        origin = payload.get("origin") or {}
        destination = payload.get("destination") or {}
        origin_name = ""
        destination_name = ""
        if isinstance(origin, dict):
            origin_name = str(
                ((origin.get("stop_group") or {}) if isinstance(origin.get("stop_group"), dict) else {}).get("name")
                or origin.get("name")
                or ""
            ).strip()
        if isinstance(destination, dict):
            destination_name = str(
                (
                    ((destination.get("stop_group") or {}) if isinstance(destination.get("stop_group"), dict) else {}).get("name")
                    or destination.get("name")
                    or ""
                )
            ).strip()
        route_label = " -> ".join([label for label in (origin_name, destination_name) if label]).strip()
        if route_label:
            parts.append(f"route={route_label}")
        matches = payload.get("matching_entries")
        entries = payload.get("entries")
        if isinstance(matches, list):
            parts.append(f"matching_entries={len(matches)}")
        if isinstance(entries, list):
            parts.append(f"entries={len(entries)}")
        return _truncate_for_prompt("; ".join(parts))

    if name.startswith("smhi_"):
        location = payload.get("location") or {}
        location_name = ""
        if isinstance(location, dict):
            location_name = str(location.get("name") or location.get("display_name") or "").strip()
        if location_name:
            parts.append(f"location={location_name}")
        current = payload.get("current") or {}
        summary = current.get("summary") if isinstance(current, dict) else {}
        if isinstance(summary, dict):
            temperature = summary.get("temperature_c")
            if temperature is not None:
                parts.append(f"temperature_c={temperature}")
            wind = summary.get("wind_speed_mps")
            if wind is None:
                wind = summary.get("wind_speed_m_s")
            if wind is not None:
                parts.append(f"wind_mps={wind}")
        return _truncate_for_prompt("; ".join(parts))

    if name == "call_agents_parallel":
        return _truncate_for_prompt(
            f"{name}: {status}; {_summarize_parallel_results(payload.get('results'))}"
        )

    for key, value in payload.items():
        if key in {"status", "error"}:
            continue
        if key in TOOL_CONTEXT_DROP_KEYS:
            if isinstance(value, list):
                parts.append(f"{key}_count={len(value)}")
            elif isinstance(value, dict):
                parts.append(f"{key}_keys={len(value)}")
            elif value is not None:
                parts.append(f"{key}=present")
            continue
        if isinstance(value, (str, int, float, bool)):
            parts.append(f"{key}={_truncate_for_prompt(str(value), 180)}")
            continue
        if isinstance(value, list):
            parts.append(f"{key}_count={len(value)}")
            continue
        if isinstance(value, dict):
            parts.append(f"{key}_keys={len(value)}")
            continue
        if value is not None:
            parts.append(f"{key}=present")

    return _truncate_for_prompt("; ".join(parts))


def _sanitize_messages(messages: list[Any]) -> list[Any]:
    sanitized: list[Any] = []
    tool_call_index = _tool_call_name_index(messages)
    for message in messages:
        if isinstance(message, ToolMessage):
            resolved_tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            payload = _safe_json(message.content)
            if payload:
                response = payload.get("response")
                if isinstance(response, str):
                    agent = payload.get("agent") or resolved_tool_name or "agent"
                    response = _strip_critic_json(response)
                    contract = _contract_from_payload(payload)
                    status = _normalize_result_status(contract.get("status"))
                    try:
                        confidence = float(contract.get("confidence"))
                    except (TypeError, ValueError):
                        confidence = 0.0
                    status_prefix = ""
                    if status != "success" or confidence < 0.7:
                        status_prefix = f"[{status} {confidence:.2f}] "
                    content = (
                        _truncate_for_prompt(f"{agent}: {status_prefix}{response}")
                        if response
                        else f"{agent}: completed"
                    )
                    sanitized.append(
                        ToolMessage(
                            content=content,
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                if payload.get("status") and payload.get("reason"):
                    tool_name = resolved_tool_name or "tool"
                    sanitized.append(
                        ToolMessage(
                            content=_truncate_for_prompt(f"{tool_name}: completed"),
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                summarized = _summarize_tool_payload(
                    resolved_tool_name or "tool",
                    payload,
                )
                sanitized.append(
                    ToolMessage(
                        content=summarized,
                        name=resolved_tool_name or message.name,
                        tool_call_id=getattr(message, "tool_call_id", None),
                    )
                )
                continue
            if isinstance(message.content, str) and "{\"status\"" in message.content:
                trimmed = message.content.split("{\"status\"", 1)[0].rstrip()
                if trimmed:
                    sanitized.append(
                        ToolMessage(
                            content=_truncate_for_prompt(trimmed),
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                else:
                    sanitized.append(
                        ToolMessage(
                            content=f"{resolved_tool_name or 'tool'}: completed",
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                continue
            if isinstance(message.content, str):
                trimmed = _strip_critic_json(message.content)
                if not trimmed:
                    trimmed = f"{resolved_tool_name or 'tool'}: completed"
                sanitized.append(
                    ToolMessage(
                        content=_truncate_for_prompt(trimmed),
                        name=resolved_tool_name or message.name,
                        tool_call_id=getattr(message, "tool_call_id", None),
                    )
                )
                continue
        sanitized.append(message)
    return sanitized


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
    )
    agent_resolver_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.agent_resolver.system",
            DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
        ),
    )
    planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.planner.system",
            DEFAULT_SUPERVISOR_PLANNER_PROMPT,
        ),
    )
    multi_domain_planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.planner.multi_domain.system",
            DEFAULT_SUPERVISOR_MULTI_DOMAIN_PLANNER_PROMPT,
        ),
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
    )
    domain_planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.domain_planner.system",
            DEFAULT_SUPERVISOR_DOMAIN_PLANNER_PROMPT,
        ),
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
    )
    synthesizer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.synthesizer.system",
            DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
        ),
    )
    compare_synthesizer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "compare.analysis.system",
            DEFAULT_COMPARE_ANALYSIS_PROMPT,
        ),
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
    )
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
        "åtgärd": WorkerConfig(
            name="åtgärd-worker",
            primary_namespaces=[("tools", "action")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "statistics"),
                ("tools", "kartor"),
                ("tools", "general"),
            ],
        ),
        "väder": WorkerConfig(
            name="väder-worker",
            primary_namespaces=[("tools", "weather")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "kartor": WorkerConfig(
            name="kartor-worker",
            primary_namespaces=[("tools", "kartor")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "media": WorkerConfig(
            name="media-worker",
            primary_namespaces=[("tools", "action", "media")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "statistics"),
                ("tools", "kartor"),
                ("tools", "general"),
            ],
        ),
        "statistik": WorkerConfig(
            name="statistik-worker",
            primary_namespaces=[("tools", "statistics")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "webb": WorkerConfig(
            name="webb-worker",
            primary_namespaces=[("tools", "knowledge", "web")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "action"),
                ("tools", "statistics"),
                ("tools", "general"),
            ],
        ),
        "kod": WorkerConfig(
            name="kod-worker",
            primary_namespaces=[("tools", "code")],
            fallback_namespaces=[
                ("tools", "general"),
                ("tools", "knowledge"),
                ("tools", "action"),
                ("tools", "statistics"),
            ],
        ),
        "bolag": WorkerConfig(
            name="bolag-worker",
            primary_namespaces=[("tools", "bolag")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "statistics"),
                ("tools", "action"),
                ("tools", "general"),
            ],
        ),
        "trafik": WorkerConfig(
            name="trafik-worker",
            primary_namespaces=[("tools", "trafik")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "riksdagen": WorkerConfig(
            name="riksdagen-worker",
            primary_namespaces=[("tools", "politik")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "action"),
                ("tools", "general"),
            ],
        ),
        "marknad": WorkerConfig(
            name="marknad-worker",
            primary_namespaces=[("tools", "marketplace")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "syntes": WorkerConfig(
            name="syntes-worker",
            primary_namespaces=[("tools", "knowledge")],
            fallback_namespaces=[
                ("tools", "statistics"),
                ("tools", "action"),
                ("tools", "general"),
            ],
        ),
    }

    worker_prompts: dict[str, str] = {
        "kunskap": knowledge_prompt,
        "åtgärd": action_prompt,
        "väder": action_prompt,
        "kartor": action_prompt,
        "media": media_prompt or action_prompt,
        "statistik": statistics_prompt,
        "webb": browser_prompt or knowledge_prompt,
        "kod": code_prompt or knowledge_prompt,
        "bolag": bolag_prompt or knowledge_prompt,
        "trafik": trafik_prompt or action_prompt,
        "kartor": kartor_prompt or action_prompt,
        "riksdagen": riksdagen_prompt or knowledge_prompt,
        "marknad": marketplace_prompt or action_prompt,
        "syntes": synthesis_prompt or statistics_prompt or knowledge_prompt,
    }

    # Create/get process-level shared worker pool for this runtime signature.
    worker_pool = await get_or_create_shared_worker_pool(
        configs=worker_configs,
        llm=llm,
        dependencies=dependencies,
        checkpointer=checkpointer,
    )

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
            name="statistik",
            description="SCB och officiell svensk statistik samt Kolada kommundata",
            keywords=[
                "statistik",
                "scb",
                "kolada",
                "skolverket statistik",
                "salsa",
                "nyckeltal",
                "kommun",
                "kommundata",
                "befolkning",
                "kpi",
                "aldreomsorg",
                "äldreomsorg",
                "hemtjanst",
                "hemtjänst",
                "behorighet",
                "behörighet",
                "skattesats",
            ],
            namespace=("agents", "statistics"),
            prompt_key="statistics",
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
            name="trafik",
            description="Trafikverket realtidsdata (väg, tåg, kameror)",
            keywords=[
                "trafikverket",
                "trafik",
                "väg",
                "vag",
                "tåg",
                "tag",
                "störning",
                "olycka",
                "kö",
                "ko",
                "kamera",
            ],
            namespace=("agents", "trafik"),
            prompt_key="trafik",
        ),
        AgentDefinition(
            name="riksdagen",
            description="Riksdagens öppna data: propositioner, motioner, voteringar, ledamöter",
            keywords=[
                "riksdag",
                "riksdagen",
                "proposition",
                "prop",
                "motion",
                "mot",
                "votering",
                "omröstning",
                "ledamot",
                "ledamöter",
                "betänkande",
                "bet",
                "interpellation",
                "fråga",
                "anförande",
                "debatt",
                "kammare",
                "sou",
                "ds",
                "utskott",
                "parti",
            ],
            namespace=("agents", "riksdagen"),
            prompt_key="riksdagen",
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
                        )
                    )
                agent_definitions = merged_agent_definitions
    agent_by_name = {definition.name: definition for definition in agent_definitions}
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

    live_phase = _normalize_live_routing_phase(persisted_tuning.get("live_routing_phase"))
    live_routing_enabled = bool(persisted_tuning.get("live_routing_enabled"))
    if isinstance(runtime_hitl_cfg, dict) and "live_routing_enabled" in runtime_hitl_cfg:
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
    }

    subagent_enabled = _coerce_bool(
        runtime_hitl_cfg.get("subagent_enabled"),
        default=True,
    )
    subagent_isolation_enabled = (
        subagent_enabled
        and _coerce_bool(
            runtime_hitl_cfg.get("subagent_isolation_enabled"),
            default=False,
        )
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
    artifact_offload_storage_mode = str(
        runtime_hitl_cfg.get("artifact_offload_storage_mode")
        or _ARTIFACT_DEFAULT_STORAGE_MODE
    ).strip().lower()
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
    if cross_session_memory_enabled and isinstance(db_session, AsyncSession) and user_id:
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
            context_token_budget = TokenBudget(model_name=str(model_name_for_compaction))
            context_budget_available_tokens = max(
                1, int(context_token_budget.available_for_messages)
            )
        except Exception:
            context_token_budget = None
            context_budget_available_tokens = 0

    async def _record_retrieval_feedback(tool_id: str, query: str, success: bool) -> None:
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

    weather_tool_ids = [definition.tool_id for definition in SMHI_TOOL_DEFINITIONS]
    weather_tool_ids.extend(
        definition.tool_id
        for definition in TRAFIKVERKET_TOOL_DEFINITIONS
        if _is_weather_tool_id(definition.tool_id)
    )
    weather_tool_ids = list(dict.fromkeys(weather_tool_ids))
    weather_tool_id_set = set(weather_tool_ids)
    trafik_tool_ids = [
        definition.tool_id
        for definition in TRAFIKVERKET_TOOL_DEFINITIONS
        if definition.tool_id not in weather_tool_id_set
    ]
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
            min(1.0, float(live_routing_config.get("adaptive_threshold_delta") or 0.08)),
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
            str(tool_id).strip()
            for tool_id in ranked_ids
            if str(tool_id).strip()
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
        base_threshold = float(live_routing_config.get("tool_auto_margin_threshold") or 0.25)
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
            mode = "shadow" if _live_phase_enabled(live_routing_config, "shadow") else "profile"
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

    route_to_intent_id = {
        "kunskap": "kunskap",
        "skapande": "skapande",
        "jämförelse": "jämförelse",
        "konversation": "konversation",
        # Backward compat
        "knowledge": "kunskap",
        "action": "skapande",
        "statistics": "kunskap",
        "compare": "jämförelse",
        "smalltalk": "konversation",
        "mixed": "mixed",
    }
    route_to_speculative_tool_ids: dict[str, list[str]] = {
        "kunskap": ["search_knowledge_base", "search_surfsense_docs", "search_tavily"],
        "åtgärd": list(dict.fromkeys((weather_tool_ids[:2] + trafik_tool_ids[:2]))),
        "väder": weather_tool_ids[:6],
        "trafik": trafik_tool_ids[:6],
        "statistik": [
            str(definition.tool_id).strip()
            for definition in SCB_TOOL_DEFINITIONS[:6]
            if str(definition.tool_id).strip()
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
            return "kunskap"
        if normalized_tool_id in {str(item).strip().lower() for item in weather_tool_ids}:
            return "väder"
        if normalized_tool_id in {str(item).strip().lower() for item in trafik_tool_ids}:
            return "trafik"
        if normalized_tool_id.startswith(("scb_", "kolada_", "skolverket_")):
            return "statistik"
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
        except asyncio.TimeoutError:
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
        status = str(result_contract.get("status") or "").strip().lower()
        speculative_status = (
            status if status in {"success", "partial"} else "failed"
        )
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
        intent_id = route_to_intent_id.get(normalized, "kunskap")
        return {
            "intent_id": intent_id,
            "route": normalized or "kunskap",
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

        override_route: str | None = None
        override_reason = ""
        # Weather, traffic, filesystem, marketplace, map overrides
        # (agent-level routing picks the right specialist agent)
        if _has_weather_intent(query):
            override_route = "kunskap"
            override_reason = (
                "Heuristisk override: vaderfraga ska routas till kunskap/vader."
            )
        elif _has_strict_trafik_intent(query):
            override_route = "kunskap"
            override_reason = (
                "Heuristisk override: trafikfraga ska routas till kunskap/trafik."
            )
        elif sandbox_enabled and _has_filesystem_intent(query):
            override_route = "skapande"
            override_reason = (
                "Heuristisk override: filsystem/sandbox-fraga ska routas till skapande/code."
            )
        elif _has_marketplace_intent(query):
            override_route = "kunskap"
            override_reason = (
                "Heuristisk override: marknadsplatsfraga ska routas till kunskap/marketplace."
            )
        elif _has_map_intent(query):
            override_route = "skapande"
            override_reason = (
                "Heuristisk override: kart/rutt-fraga ska routas till skapande."
            )
        if not override_route:
            return resolved
        if normalized_route == override_route and str(
            resolved.get("intent_id") or ""
        ).strip():
            return resolved

        resolved["intent_id"] = route_to_intent_id.get(override_route, override_route)
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
        return {
            "name": definition.name,
            "description": definition.description,
            "keywords": list(definition.keywords or []),
        }

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
                if candidate and candidate in agent_by_name and candidate not in selected_agent_names:
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
        if route_hint in {"kunskap", "skapande", "action", "knowledge"} and weather_task and not strict_trafik_task:
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
        if route_hint in {"kunskap", "skapande", "action", "knowledge"} and strict_trafik_task:
            allowed_for_strict = {"trafik", "kartor", "åtgärd"}
            if requested_raw in agent_by_name and requested_raw not in allowed_for_strict:
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
            if selected_agent_set and requested_raw not in selected_agent_set:
                fallback = _selected_fallback(
                    "marknad" if marketplace_task else default_for_route
                )
                if fallback and fallback in agent_by_name:
                    return fallback, f"selected_agents_lock:{requested_raw}->{fallback}"
            if requested_raw in _SPECIALIZED_AGENTS:
                return requested_raw, None
            if route_allowed and requested_raw not in route_allowed:
                if default_for_route in agent_by_name:
                    return default_for_route, f"route_policy:{requested_raw}->{default_for_route}"
            return requested_raw, None

        alias_guess = _guess_agent_from_alias(requested_raw)
        if alias_guess and alias_guess in agent_by_name:
            if selected_agent_set and alias_guess not in selected_agent_set:
                fallback = _selected_fallback(
                    "marknad" if marketplace_task else default_for_route
                )
                if fallback and fallback in agent_by_name:
                    return fallback, f"selected_agents_lock_alias:{requested_raw}->{fallback}"
            if route_allowed and alias_guess not in route_allowed:
                if default_for_route in agent_by_name:
                    return default_for_route, f"route_policy_alias:{requested_raw}->{default_for_route}"
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
            retrieved = [agent for agent in retrieved if agent.name in selected_agent_set]
        if route_hint:
            preferred = {
                "kunskap": ["kunskap", "webb"],
                "skapande": ["åtgärd", "media"],
                "jämförelse": ["syntes", "kunskap", "statistik"],
                # Backward compat
                "action": ["åtgärd", "media"],
                "knowledge": ["kunskap", "webb"],
                "statistics": ["statistik"],
                "compare": ["syntes", "kunskap", "statistik"],
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
                if _has_trafik_intent(task) and not weather_task and "trafik" not in preferred:
                    preferred.insert(0, "trafik")
            if route_allowed:
                preferred = [name for name in preferred if name in route_allowed]
            if selected_agent_set:
                preferred = [name for name in preferred if name in selected_agent_set]
            for preferred_name in preferred:
                if any(agent.name == preferred_name for agent in retrieved):
                    return preferred_name, f"route_pref:{requested_raw}->{preferred_name}"
        if retrieved:
            return retrieved[0].name, f"retrieval:{requested_raw}->{retrieved[0].name}"
        if selected_agent_names:
            fallback = _selected_fallback(
                "marknad" if marketplace_task else default_for_route
            )
            if fallback and fallback in agent_by_name:
                return fallback, f"selected_agents_fallback:{requested_raw}->{fallback}"
        if route_allowed and default_for_route in agent_by_name:
            return default_for_route, f"route_default:{requested_raw}->{default_for_route}"
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
                    print(
                        f"[compare] Failed to ingest {spec.tool_name}: {exc!s}"
                    )
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
                str(call.get("agent"))
                for call in recent_calls
                if call.get("agent")
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
        if route_hint in {"statistik", "statistics"}:  # Statistics agents chosen by agent_resolver, not route
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
        if (
            cached_agents
            and has_marketplace_intent
            and "marknad" not in cached_agents
        ):
            cached_agents = None

        if cached_agents:
            selected = [
                agent_by_name[name]
                for name in cached_agents
                if name in agent_by_name
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
                    "jämförelse": ["syntes", "kunskap", "statistik"],
                    # Backward compat
                    "action": ["åtgärd", "media"],
                    "knowledge": ["kunskap", "webb"],
                    "statistics": ["statistik"],
                    "compare": ["syntes", "kunskap", "statistik"],
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
                and route_hint in {"kunskap", "skapande", "action", "knowledge", "trafik"}
            ):
                trafik_agent = agent_by_name.get("trafik")
                if trafik_agent and trafik_agent not in selected:
                    selected.insert(0, trafik_agent)
                    selected = selected[:limit]
            if route_hint in {"kunskap", "skapande", "action", "knowledge"} and sandbox_enabled and has_filesystem_intent:
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
                agent_by_name[name] for name in marketplace_order if name in agent_by_name
            ]
            selected = marketplace_selected[:limit] if marketplace_selected else selected
        # Weather order removed: selection should be based on retrieval and LLM classification
        if route_hint in {"kunskap", "skapande", "action", "knowledge"} and has_strict_trafik_intent:
            strict_order = ["trafik"]
            if has_map_intent:
                strict_order.append("kartor")
            strict_order.append("åtgärd")
            strict_selected = [
                agent_by_name[name] for name in strict_order if name in agent_by_name
            ]
            selected = strict_selected[:limit] if strict_selected else selected
        payload = [
            {"name": agent.name, "description": agent.description}
            for agent in selected
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
            response_text = _strip_critic_json(str(payload.get("response") or "").strip())
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
        task_body = _truncate_for_prompt(str(task or "").strip(), int(subagent_context_max_chars))
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
        return (
            str(agent_name or "").strip().lower() in {"kod", "code"}
            and _has_filesystem_intent(task)
        )

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
            if isinstance(message, dict) and str(message.get("type") or "").strip().lower() == "tool":
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
            if not normalized_tool_name or normalized_tool_name in _ARTIFACT_INTERNAL_TOOL_NAMES:
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
            artifact_id = "art-" + hashlib.sha1(
                artifact_seed.encode("utf-8", errors="ignore")
            ).hexdigest()[:16]
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
        execution_strategy = str(injected_state.get("execution_strategy") or "").strip().lower()
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
                    tool_id for tool_id in selected_tool_ids if tool_id in weather_tool_ids
                ]
                if not selected_tool_ids:
                    selected_tool_ids = list(weather_tool_ids)
            else:
                selected_tool_ids = list(weather_tool_ids)
        if name == "trafik":
            selected_tool_ids = [
                tool_id for tool_id in selected_tool_ids if tool_id in trafik_tool_ids
            ]
            if not selected_tool_ids:
                selected_tool_ids = list(trafik_tool_ids)
        selected_tool_ids = _prioritize_sandbox_code_tools(
            selected_tool_ids,
            agent_name=name,
            task=task,
            limit=8,
        )
        fallback_tool_ids: list[str] = []
        if name in {"väder", "weather"}:
            fallback_tool_ids = list(weather_tool_ids)
        elif name == "trafik":
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
        explicit_file_read_requested = (
            filesystem_sandbox_task
            and (
                _requires_explicit_file_read(task)
                or _requires_explicit_file_read(latest_turn_query)
            )
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
            prompt = f"{prompt.rstrip()}\n\n{scoped_prompt}".strip() if prompt else scoped_prompt
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
                worker_configurable["checkpoint_ns"] = f"{worker_checkpoint_ns}:worker:{name}"
        config = {
            "configurable": worker_configurable,
            "recursion_limit": 60,
        }
        try:
            result = await asyncio.wait_for(
                worker.ainvoke(worker_state, config=config),
                timeout=float(execution_timeout_seconds),
            )
        except asyncio.TimeoutError:
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
            initial_tool_names = _tool_names_from_messages(messages_out)
            enforcement_message: str | None = None
            if name == "trafik":
                used_trafik_tool = any(
                    tool_name.startswith("trafikverket_")
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
                except asyncio.TimeoutError:
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
                [SystemMessage(content=str(critic_prompt or "")), HumanMessage(content=str(critic_input or ""))]
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
            and str(result_contract.get("status") or "").strip().lower() in {
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
            response_text = _truncate_for_prompt(response_text, subagent_result_max_chars)

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
        requested_strategy = str(injected_state.get("execution_strategy") or "").strip().lower()
        allow_parallel = compare_mode or requested_strategy == "parallel" or (
            requested_strategy == "subagent" and subagent_enabled
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
                    candidate_tools = resolved_tools_map.get(agent_name) or resolved_tools_map.get(
                        requested_agent_name
                    )
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
                        for tool_id in list(tool_selection_meta.get("selected_tool_ids") or [])
                        if str(tool_id).strip()
                    ][:8]
                if not selected_tool_ids:
                    selected_tool_ids = _focused_tool_ids_for_agent(
                        agent_name,
                        task,
                        limit=6,
                    )
                live_tool_gate_active = _live_phase_enabled(live_routing_config, "tool_gate")
                if agent_name in {"väder", "weather"}:
                    if live_tool_gate_active:
                        selected_tool_ids = [
                            tool_id for tool_id in selected_tool_ids if tool_id in weather_tool_ids
                        ]
                        if not selected_tool_ids:
                            selected_tool_ids = list(weather_tool_ids)
                    else:
                        selected_tool_ids = list(weather_tool_ids)
                if agent_name == "trafik":
                    selected_tool_ids = [
                        tool_id for tool_id in selected_tool_ids if tool_id in trafik_tool_ids
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
                elif agent_name == "trafik":
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
                filesystem_sandbox_task = _is_filesystem_sandbox_task(
                    agent_name, task
                )
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
                worker_checkpoint_ns = str(dependencies.get("checkpoint_ns") or "").strip()
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
                    "recursion_limit": 60,
                }
                try:
                    result = await asyncio.wait_for(
                        worker.ainvoke(worker_state, config=config),
                        timeout=float(execution_timeout_seconds),
                    )
                except asyncio.TimeoutError:
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
                    and str(result_contract.get("status") or "").strip().lower() in {
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
            fallback = "Hej! Hur kan jag hjalpa dig idag?"
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
            response_text = _strip_critic_json(
                str(getattr(message, "content", "") or "")
            ).strip()
        except Exception:
            response_text = ""
        if not response_text:
            response_text = "Hej! Jag ar OneSeek. Hur kan jag hjalpa dig idag?"
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
                            item
                            for item in payload_artifacts
                            if isinstance(item, dict)
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
                        if _should_finalize_from_contract(
                            contract=payload_contract,
                            response_text=cleaned_response,
                            route_hint=route_hint,
                            agent_name=str(payload.get("agent") or ""),
                            latest_user_query=latest_user_query,
                            agent_hops=int(state.get("agent_hops") or 0),
                        ) and not pending_followup_steps:
                            updates["final_agent_response"] = cleaned_response
                            updates["final_response"] = cleaned_response
                            updates["final_agent_name"] = payload.get("agent")
                            updates["orchestration_phase"] = "finalize"
                    elif payload.get("response"):
                        cleaned_response = _strip_critic_json(
                            str(payload.get("response") or "").strip()
                        )
                        selected_agent = str(payload.get("agent") or "").strip().lower()
                        if _should_finalize_from_contract(
                            contract=payload_contract,
                            response_text=cleaned_response,
                            route_hint=route_hint,
                            agent_name=selected_agent,
                            latest_user_query=latest_user_query,
                            agent_hops=int(state.get("agent_hops") or 0),
                        ) and not pending_followup_steps:
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
            if not normalized_tool_name or normalized_tool_name in _ARTIFACT_INTERNAL_TOOL_NAMES:
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
            artifact_id = "art-" + hashlib.sha1(
                artifact_seed.encode("utf-8", errors="ignore")
            ).hexdigest()[:16]
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
                usage_ratio = float(used_tokens) / float(context_budget_available_tokens)
            except Exception:
                usage_ratio = 0.0
        else:
            # Conservative fallback when model context metadata is unavailable.
            approx_chars = sum(
                len(str(getattr(message, "content", "") or ""))
                for message in messages
            )
            usage_ratio = min(1.0, float(max(0, approx_chars)) / 24_000.0)
        if usage_ratio < float(context_compaction_trigger_ratio) and len(messages) < MESSAGE_PRUNING_THRESHOLD:
            return {}

        summary = _build_rolling_context_summary(
            latest_user_query=_latest_user_query(messages),
            active_plan=[
                item for item in (state.get("active_plan") or []) if isinstance(item, dict)
            ],
            step_results=[
                item for item in (state.get("step_results") or []) if isinstance(item, dict)
            ],
            subagent_handoffs=[
                item for item in (state.get("subagent_handoffs") or []) if isinstance(item, dict)
            ],
            artifact_manifest=[
                item for item in (state.get("artifact_manifest") or []) if isinstance(item, dict)
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
            updates["step_results"] = compacted_steps[-_CONTEXT_COMPACTION_DEFAULT_STEP_KEEP:]
        compacted_handoffs = [
            item for item in (state.get("subagent_handoffs") or []) if isinstance(item, dict)
        ]
        if len(compacted_handoffs) > _SUBAGENT_MAX_HANDOFFS_IN_PROMPT:
            updates["subagent_handoffs"] = compacted_handoffs[-_SUBAGENT_MAX_HANDOFFS_IN_PROMPT:]
        compacted_artifacts = [
            item for item in (state.get("artifact_manifest") or []) if isinstance(item, dict)
        ]
        if len(compacted_artifacts) > int(artifact_offload_max_entries):
            updates["artifact_manifest"] = compacted_artifacts[-int(artifact_offload_max_entries):]
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
                response_text = _strip_critic_json(str(item.get("response") or "").strip())
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
            last_task = _normalize_task_for_fingerprint(
                str(last_entry.get("task") or "")
            )
            last_fp = f"{last_agent}|{last_task}" if (last_agent or last_task) else ""
            if last_fp:
                fp_count = 0
                for entry in call_entries:
                    agent = str(entry.get("agent") or "").strip().lower()
                    task_fp = _normalize_task_for_fingerprint(
                        str(entry.get("task") or "")
                    )
                    if f"{agent}|{task_fp}" == last_fp:
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

        if (
            "final_agent_response" not in updates
            and no_progress_runs >= 2
        ):
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

        if "final_agent_response" not in updates and agent_hops >= _MAX_AGENT_HOPS_PER_TURN:
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
            tool_msgs = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage)]
            if len(tool_msgs) > TOOL_MSG_THRESHOLD:
                keep_from = tool_msgs[-KEEP_TOOL_MSG_COUNT]
                keep_start = max(0, keep_from - 1)
                dropped_count = keep_start
                if dropped_count > 0:
                    pruned = messages[keep_start:]
                    rolling_summary = str(state.get("rolling_context_summary") or "").strip()
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
                    summary_msg = SystemMessage(
                        content=summary_content
                    )
                    leading_system = [m for m in messages[:keep_start] if isinstance(m, SystemMessage)]
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
            (resolved_intent.get("route") if isinstance(resolved_intent, dict) else None)
            or state.get("route_hint")
        )
        if resolved_route in {"konversation", "smalltalk"}:
            return "smalltalk"
        phase = str(state.get("orchestration_phase") or "").strip().lower()
        has_final = bool(
            str(state.get("final_response") or state.get("final_agent_response") or "").strip()
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
            if complexity == "complex" and speculative_enabled:
                return "speculative"
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
        if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
            return "tools"
        return "critic"

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
    graph_builder.add_node("resolve_intent", RunnableCallable(None, resolve_intent_node))
    
    # Conditional graph structure based on compare_mode
    if compare_mode:
        # Compare mode: use deterministic compare subgraph
        from functools import partial
        from app.agents.new_chat.compare_executor import (
            compare_fan_out,
            compare_collect,
            compare_tavily,
            compare_synthesizer,
        )
        
        # Create compare_synthesizer with resolved prompt override
        compare_synthesizer_with_prompt = partial(
            compare_synthesizer,
            prompt_override=compare_synthesizer_prompt_template
        )
        
        graph_builder.add_node("compare_fan_out", RunnableCallable(None, compare_fan_out))
        graph_builder.add_node("compare_collect", RunnableCallable(None, compare_collect))
        graph_builder.add_node("compare_tavily", RunnableCallable(None, compare_tavily))
        graph_builder.add_node("compare_synthesizer", RunnableCallable(None, compare_synthesizer_with_prompt))
        
        # Direct routing: resolve_intent -> compare_fan_out -> ... -> END
        graph_builder.set_entry_point("resolve_intent")
        graph_builder.add_edge("resolve_intent", "compare_fan_out")
        graph_builder.add_edge("compare_fan_out", "compare_collect")
        graph_builder.add_edge("compare_collect", "compare_tavily")
        graph_builder.add_edge("compare_tavily", "compare_synthesizer")
        graph_builder.add_edge("compare_synthesizer", END)
    else:
        # Normal mode: use standard supervisor pipeline
        if hybrid_mode and not compare_mode and speculative_enabled:
            graph_builder.add_node("speculative", RunnableCallable(None, speculative_node))
        graph_builder.add_node("memory_context", RunnableCallable(None, memory_context_node))
        graph_builder.add_node("smalltalk", RunnableCallable(None, smalltalk_node))
        graph_builder.add_node("agent_resolver", RunnableCallable(None, resolve_agents_node))
        graph_builder.add_node("planner", RunnableCallable(None, planner_node))
        graph_builder.add_node(
            "planner_hitl_gate",
            RunnableCallable(None, planner_hitl_gate_node),
        )
        graph_builder.add_node("tool_resolver", RunnableCallable(None, tool_resolver_node))
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
        graph_builder.add_node("domain_planner", RunnableCallable(None, domain_planner_node))
        graph_builder.add_node("response_layer_router", RunnableCallable(None, response_layer_router_node))
        graph_builder.add_node("response_layer", RunnableCallable(None, response_layer_node))
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
        if hybrid_mode and not compare_mode and speculative_enabled:
            resolve_intent_paths.append("speculative")
        graph_builder.add_edge("resolve_intent", "memory_context")
        graph_builder.add_conditional_edges(
            "memory_context",
            route_after_intent,
            path_map=resolve_intent_paths,
        )
        graph_builder.add_edge("smalltalk", END)
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
