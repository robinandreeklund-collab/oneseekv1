from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig


def build_intent_resolver_node(
    *,
    llm: Any,
    route_to_intent_id: dict[str, str],
    intent_resolver_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    parse_hitl_confirmation_fn: Callable[[str], str | None],
    normalize_route_hint_fn: Callable[[Any], str],
    intent_from_route_fn: Callable[[str | None], dict[str, Any]],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
    coerce_confidence_fn: Callable[[Any, float], float],
    classify_graph_complexity_fn: Callable[[dict[str, Any], str], str],
    build_speculative_candidates_fn: Callable[[dict[str, Any], str], list[dict[str, Any]]],
    build_trivial_response_fn: Callable[[str], str | None],
    route_default_agent_fn: Callable[..., str],
):
    async def resolve_intent_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        latest_user_query = latest_user_query_fn(state.get("messages") or [])

        if new_user_turn and bool(state.get("awaiting_confirmation")):
            pending_stage = str(state.get("pending_hitl_stage") or "").strip().lower()
            decision = parse_hitl_confirmation_fn(latest_user_query)
            if decision is None:
                return {
                    "messages": [
                        AIMessage(
                            content="Svara med ja eller nej sa jag vet hur jag ska fortsatta."
                        )
                    ],
                    "awaiting_confirmation": True,
                    "pending_hitl_stage": pending_stage or None,
                    "active_turn_id": incoming_turn_id or active_turn_id or None,
                    "orchestration_phase": "awaiting_confirmation",
                }
            updates: dict[str, Any] = {
                "awaiting_confirmation": False,
                "pending_hitl_stage": None,
                "pending_hitl_payload": None,
                "user_feedback": {
                    "stage": pending_stage or None,
                    "decision": decision,
                    "message": latest_user_query,
                },
            }
            if incoming_turn_id:
                updates["active_turn_id"] = incoming_turn_id
            if decision == "approve":
                if pending_stage == "planner":
                    updates["orchestration_phase"] = "resolve_tools"
                elif pending_stage == "execution":
                    updates["orchestration_phase"] = "execute"
                elif pending_stage == "synthesis":
                    updates["orchestration_phase"] = "finalize"
                return updates
            # reject
            updates["replan_count"] = int(state.get("replan_count") or 0) + 1
            if pending_stage == "synthesis":
                updates["final_response"] = None
                updates["final_agent_response"] = None
            updates["critic_decision"] = "replan"
            updates["orchestration_phase"] = "plan"
            return updates

        if not new_user_turn and state.get("resolved_intent"):
            return {}

        route_hint = normalize_route_hint_fn(state.get("route_hint"))
        candidates: list[dict[str, Any]] = []
        for route_name, intent_id in route_to_intent_id.items():
            candidates.append({"intent_id": intent_id, "route": route_name})
        if route_hint:
            candidates.sort(key=lambda item: 0 if item.get("route") == route_hint else 1)
        candidate_ids = {
            str(item.get("intent_id") or "").strip()
            for item in candidates
            if str(item.get("intent_id") or "").strip()
        }

        resolved = intent_from_route_fn(route_hint)
        if latest_user_query:
            prompt = append_datetime_context_fn(intent_resolver_prompt_template)
            resolver_input = json.dumps(
                {
                    "query": latest_user_query,
                    "route_hint": route_hint,
                    "intent_candidates": candidates,
                },
                ensure_ascii=True,
            )
            try:
                message = await llm.ainvoke(
                    [
                        SystemMessage(content=prompt),
                        HumanMessage(content=resolver_input),
                    ]
                )
                parsed = extract_first_json_object_fn(
                    str(getattr(message, "content", "") or "")
                )
                selected_intent = str(parsed.get("intent_id") or "").strip()
                selected_route = normalize_route_hint_fn(parsed.get("route"))
                if selected_intent and selected_intent in candidate_ids:
                    resolved = {
                        "intent_id": selected_intent,
                        "route": selected_route
                        or next(
                            (
                                str(item.get("route") or "")
                                for item in candidates
                                if str(item.get("intent_id") or "").strip()
                                == selected_intent
                            ),
                            route_hint or "knowledge",
                        ),
                        "reason": str(parsed.get("reason") or "").strip()
                        or "LLM intent_resolver valde intent.",
                        "confidence": coerce_confidence_fn(
                            parsed.get("confidence"), 0.5
                        ),
                    }
            except Exception:
                pass

        graph_complexity = str(
            classify_graph_complexity_fn(resolved, latest_user_query)
        ).strip().lower()
        if graph_complexity not in {"trivial", "simple", "complex"}:
            graph_complexity = "complex"
        speculative_candidates = build_speculative_candidates_fn(
            resolved,
            latest_user_query,
        )
        if not isinstance(speculative_candidates, list):
            speculative_candidates = []
        speculative_candidates = [
            item for item in speculative_candidates[:3] if isinstance(item, dict)
        ]

        selected_agents_for_simple: list[dict[str, Any]] = []
        if graph_complexity == "simple":
            try:
                default_agent_name = route_default_agent_fn(
                    resolved.get("route"),
                    latest_user_query,
                )
            except TypeError:
                default_agent_name = route_default_agent_fn(resolved.get("route"))
            if default_agent_name:
                selected_agents_for_simple = [
                    {
                        "name": str(default_agent_name),
                        "description": "Preselected from hybrid intent complexity.",
                    }
                ]

        trivial_response = (
            build_trivial_response_fn(latest_user_query)
            if graph_complexity == "trivial"
            else None
        )

        updates: dict[str, Any] = {
            "resolved_intent": resolved,
            "graph_complexity": graph_complexity,
            "speculative_candidates": speculative_candidates,
            "speculative_results": {},
            "execution_strategy": None,
            "worker_results": [],
            "synthesis_drafts": [],
            "retrieval_feedback": {},
            "targeted_missing_info": [],
            "orchestration_phase": "select_agent",
        }
        if new_user_turn:
            updates["active_plan"] = []
            updates["plan_step_index"] = 0
            updates["plan_complete"] = False
            updates["step_results"] = []
            updates["recent_agent_calls"] = []
            updates["compare_outputs"] = []
            updates["selected_agents"] = []
            updates["resolved_tools_by_agent"] = {}
            updates["final_agent_response"] = None
            updates["final_response"] = None
            updates["critic_decision"] = None
            updates["awaiting_confirmation"] = False
            updates["pending_hitl_stage"] = None
            updates["pending_hitl_payload"] = None
            updates["user_feedback"] = None
            updates["replan_count"] = 0
            updates["agent_hops"] = 0
            updates["no_progress_runs"] = 0
            updates["guard_parallel_preview"] = []
            updates["graph_complexity"] = graph_complexity
            updates["speculative_candidates"] = speculative_candidates
            updates["speculative_results"] = {}
            updates["execution_strategy"] = None
            updates["worker_results"] = []
            updates["synthesis_drafts"] = []
            updates["retrieval_feedback"] = {}
            updates["targeted_missing_info"] = []
            if incoming_turn_id:
                updates["active_turn_id"] = incoming_turn_id
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id

        if selected_agents_for_simple:
            updates["selected_agents"] = selected_agents_for_simple

        if trivial_response:
            updates["final_agent_response"] = trivial_response
            updates["final_response"] = trivial_response
            updates["final_agent_name"] = "supervisor"
            updates["orchestration_phase"] = "finalize"
        return updates

    return resolve_intent_node
