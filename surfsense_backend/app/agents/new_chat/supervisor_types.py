"""Type definitions and reducer functions for supervisor agent."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


# Reducer functions for SupervisorState
def _replace(left: Any, right: Any) -> Any:
    return right


def _append_recent(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if right == []:
        return []
    merged = list(left or [])
    merged.extend(right or [])
    return merged[-3:]


def _append_compare_outputs(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    if right == []:
        return []
    merged: dict[str, dict[str, Any]] = {}
    for item in left or []:
        tool_call_id = str(item.get("tool_call_id") or "")
        # Fall back to a positional key so items without an explicit ID are
        # not silently dropped (e.g. timeout results, Tavily error responses).
        key = tool_call_id or f"__idx_{len(merged)}"
        merged[key] = item
    for item in right or []:
        tool_call_id = str(item.get("tool_call_id") or "")
        key = tool_call_id or f"__idx_{len(merged)}"
        merged[key] = item
    return list(merged.values())


def _append_subagent_handoffs(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if right == []:
        return []
    merged: dict[str, dict[str, Any]] = {}
    for item in left or []:
        if not isinstance(item, dict):
            continue
        subagent_id = str(item.get("subagent_id") or item.get("id") or "").strip()
        if not subagent_id:
            continue
        merged[subagent_id] = item
    for item in right or []:
        if not isinstance(item, dict):
            continue
        subagent_id = str(item.get("subagent_id") or item.get("id") or "").strip()
        if not subagent_id:
            continue
        merged[subagent_id] = item
    return list(merged.values())[-12:]


def _append_artifact_manifest(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if right == []:
        return []

    # Import here to avoid circular dependency
    from app.agents.new_chat.supervisor_constants import _ARTIFACT_DEFAULT_MAX_ENTRIES

    merged: dict[str, dict[str, Any]] = {}
    for item in left or []:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("id") or "").strip()
        source_id = str(item.get("source_id") or "").strip()
        key = artifact_id or source_id
        if not key:
            continue
        merged[key] = item
    for item in right or []:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("id") or "").strip()
        source_id = str(item.get("source_id") or "").strip()
        key = artifact_id or source_id
        if not key:
            continue
        merged[key] = item
    limit = max(8, int(_ARTIFACT_DEFAULT_MAX_ENTRIES))
    return list(merged.values())[-limit:]


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    keywords: list[str]
    namespace: tuple[str, ...]
    prompt_key: str


class SupervisorState(TypedDict, total=False):
    # Keep a typed message channel so LangGraph Studio enables Chat mode.
    messages: Annotated[list[AnyMessage], add_messages]
    turn_id: Annotated[str | None, _replace]
    active_turn_id: Annotated[str | None, _replace]
    resolved_intent: Annotated[dict[str, Any] | None, _replace]
    sub_intents: Annotated[list[str] | None, _replace]
    graph_complexity: Annotated[str | None, _replace]
    speculative_candidates: Annotated[list[dict[str, Any]], _replace]
    speculative_results: Annotated[dict[str, Any], _replace]
    execution_strategy: Annotated[str | None, _replace]
    worker_results: Annotated[list[dict[str, Any]], _replace]
    synthesis_drafts: Annotated[list[dict[str, Any]], _replace]
    retrieval_feedback: Annotated[dict[str, Any], _replace]
    live_routing_trace: Annotated[dict[str, Any], _replace]
    targeted_missing_info: Annotated[list[str], _replace]
    selected_agents: Annotated[list[dict[str, Any]], _replace]
    resolved_tools_by_agent: Annotated[dict[str, list[str]], _replace]
    query_embedding: Annotated[list[float] | None, _replace]
    active_plan: Annotated[list[dict[str, Any]], _replace]
    plan_step_index: Annotated[int | None, _replace]
    plan_complete: Annotated[bool, _replace]
    step_results: Annotated[list[dict[str, Any]], _replace]
    recent_agent_calls: Annotated[list[dict[str, Any]], _append_recent]
    route_hint: Annotated[str | None, _replace]
    worker_system_prompt: Annotated[str | None, _replace]
    compare_outputs: Annotated[list[dict[str, Any]], _append_compare_outputs]
    subagent_handoffs: Annotated[list[dict[str, Any]], _append_subagent_handoffs]
    artifact_manifest: Annotated[list[dict[str, Any]], _append_artifact_manifest]
    cross_session_memory_context: Annotated[str | None, _replace]
    rolling_context_summary: Annotated[str | None, _replace]
    final_agent_response: Annotated[str | None, _replace]
    final_response: Annotated[str | None, _replace]
    critic_decision: Annotated[str | None, _replace]
    awaiting_confirmation: Annotated[bool | None, _replace]
    pending_hitl_stage: Annotated[str | None, _replace]
    pending_hitl_payload: Annotated[dict[str, Any] | None, _replace]
    user_feedback: Annotated[dict[str, Any] | None, _replace]
    replan_count: Annotated[int | None, _replace]
    final_agent_name: Annotated[str | None, _replace]
    orchestration_phase: Annotated[str | None, _replace]
    agent_hops: Annotated[int | None, _replace]
    no_progress_runs: Annotated[int | None, _replace]
    guard_parallel_preview: Annotated[list[str], _replace]
    domain_fan_out_trace: Annotated[dict[str, Any] | None, _replace]
    domain_plans: Annotated[dict[str, Any] | None, _replace]
    response_mode: Annotated[str | None, _replace]
