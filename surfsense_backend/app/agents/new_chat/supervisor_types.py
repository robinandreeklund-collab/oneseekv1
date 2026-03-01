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
    # P1 loop-fix: guard_finalized prevents critic from overriding orchestration_guard.
    guard_finalized: Annotated[bool, _replace]
    # P1 loop-fix: total_steps counts all meaningful work nodes, hard cap at MAX_TOTAL_STEPS.
    total_steps: Annotated[int, _replace]
    # P1 loop-fix: critic_history tracks previous critic decisions for adaptive behavior.
    critic_history: Annotated[list[dict[str, Any]], _replace]
    # P3: atomic_questions produced by multi_query_decomposer for complex queries.
    # Each item: {"id": "q1", "text": "...", "depends_on": [], "domain": "väder"}
    atomic_questions: Annotated[list[dict[str, Any]], _replace]
    # P4: micro_plans per subagent domain.
    # Dict: subagent_id → [{"action": "...", "tool_id": "...", "use_cache": bool}, ...]
    micro_plans: Annotated[dict[str, list[dict[str, Any]]], _replace]
    # P4: convergence_status after merging parallel subagent results.
    # {"merged_fields": [...], "overlap_score": 0.92, "conflicts": [], "source_domains": [...]}
    convergence_status: Annotated[dict[str, Any] | None, _replace]
    # P4: spawned_domains tracks which domains have active mini-graphs.
    spawned_domains: Annotated[list[str], _replace]
    # P4: subagent_summaries collects mini_synthesizer outputs before convergence.
    # List of {"domain": "...", "summary": "...", "key_facts": [...], "data_quality": "..."}
    subagent_summaries: Annotated[list[dict[str, Any]], _replace]
    # P4: adaptive thresholds per domain from adaptive_guard.
    # {"force_synthesis": bool, "adjusted_confidence_threshold": float, ...}
    adaptive_thresholds: Annotated[dict[str, Any] | None, _replace]
    # Compare: criterion evaluation events for SSE streaming to frontend.
    criterion_events: Annotated[list[dict[str, Any]], _replace]
    # Compare: per-model completion events for progressive SSE streaming.
    model_complete_events: Annotated[list[dict[str, Any]], _replace]
    # Compare: structured arena data from synthesizer.
    compare_arena_data: Annotated[dict[str, Any] | None, _replace]
    # Debate: participant list from domain planner.
    debate_participants: Annotated[list[dict[str, Any]], _replace]
    # Debate: topic being debated.
    debate_topic: Annotated[str | None, _replace]
    # Debate: current round number (1-4).
    debate_current_round: Annotated[int | None, _replace]
    # Debate: all round responses keyed by round number → {model: response_text}.
    debate_round_responses: Annotated[dict[int, dict[str, str]], _replace]
    # Debate: collected votes from round 4.
    debate_votes: Annotated[list[dict[str, Any]], _replace]
    # Debate: accumulated word counts per participant.
    debate_word_counts: Annotated[dict[str, int], _replace]
    # Debate: execution status tracking.
    debate_status: Annotated[str | None, _replace]
    # Debate voice settings (API key, voice map, model — from admin or env).
    debate_voice_settings: Annotated[dict[str, Any] | None, _replace]
