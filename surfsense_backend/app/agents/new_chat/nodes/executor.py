from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.new_chat.token_budget import TokenBudget


def _build_executor_updates_for_new_user_turn(
    *,
    incoming_turn_id: str,
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "resolved_intent": None,
        "selected_agents": [],
        "resolved_tools_by_agent": {},
        "query_embedding": None,
        "active_plan": [],
        "plan_step_index": 0,
        "plan_complete": False,
        "step_results": [],
        "recent_agent_calls": [],
        "compare_outputs": [],
        "final_agent_response": None,
        "final_response": None,
        "critic_decision": None,
        "awaiting_confirmation": False,
        "pending_hitl_stage": None,
        "pending_hitl_payload": None,
        "user_feedback": None,
        "replan_count": 0,
        "orchestration_phase": "select_agent",
        "agent_hops": 0,
        "no_progress_runs": 0,
        "guard_parallel_preview": [],
    }
    if incoming_turn_id:
        updates["active_turn_id"] = incoming_turn_id
    return updates


def build_executor_nodes(
    *,
    llm: Any,
    llm_with_tools: Any,
    compare_mode: bool,
    strip_critic_json_fn: Callable[[str], str],
    sanitize_messages_fn: Callable[[list[Any]], list[Any]],
    format_plan_context_fn: Callable[[dict[str, Any]], str | None],
    format_recent_calls_fn: Callable[[dict[str, Any]], str | None],
    format_route_hint_fn: Callable[[dict[str, Any]], str | None],
    format_intent_context_fn: Callable[[dict[str, Any]], str | None],
    format_selected_agents_context_fn: Callable[[dict[str, Any]], str | None],
    format_resolved_tools_context_fn: Callable[[dict[str, Any]], str | None],
    coerce_supervisor_tool_calls_fn: Callable[..., Any],
):
    def _build_context_messages(
        *,
        state: dict[str, Any],
        new_user_turn: bool,
    ) -> list[Any]:
        messages = sanitize_messages_fn(list(state.get("messages") or []))
        plan_context = None if new_user_turn else format_plan_context_fn(state)
        recent_context = None if new_user_turn else format_recent_calls_fn(state)
        route_context = format_route_hint_fn(state)
        intent_context = None if new_user_turn else format_intent_context_fn(state)
        selected_agents_context = (
            None if new_user_turn else format_selected_agents_context_fn(state)
        )
        resolved_tools_context = (
            None if new_user_turn else format_resolved_tools_context_fn(state)
        )
        system_bits = [
            item
            for item in (
                plan_context,
                recent_context,
                route_context,
                intent_context,
                selected_agents_context,
                resolved_tools_context,
            )
            if item
        ]
        if system_bits:
            messages = [SystemMessage(content="\n".join(system_bits))] + messages
        model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None) or ""
        if model_name:
            budget = TokenBudget(model_name=str(model_name))
            messages = budget.fit_messages(messages)
        return messages

    def call_model(
        state: dict[str, Any],
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        final_response = state.get("final_agent_response") or state.get("final_response")
        messages_state = state.get("messages") or []
        last_message = messages_state[-1] if messages_state else None
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        if final_response and isinstance(last_message, ToolMessage) and not new_user_turn:
            return {"messages": [AIMessage(content=strip_critic_json_fn(str(final_response)))]}
        if not incoming_turn_id and final_response and isinstance(last_message, HumanMessage):
            # Legacy fallback when turn_id is missing.
            new_user_turn = True

        messages = _build_context_messages(state=state, new_user_turn=new_user_turn)
        response = llm_with_tools.invoke(messages)
        response = coerce_supervisor_tool_calls_fn(
            response,
            orchestration_phase=str(state.get("orchestration_phase") or ""),
            agent_hops=int(state.get("agent_hops") or 0),
            allow_multiple=bool(compare_mode),
        )
        updates: dict[str, Any] = {"messages": [response]}
        if new_user_turn:
            updates.update(
                _build_executor_updates_for_new_user_turn(
                    incoming_turn_id=incoming_turn_id,
                )
            )
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id
        if final_response and new_user_turn:
            updates["final_agent_response"] = None
            updates["final_response"] = None
        return updates

    async def acall_model(
        state: dict[str, Any],
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        final_response = state.get("final_agent_response") or state.get("final_response")
        messages_state = state.get("messages") or []
        last_message = messages_state[-1] if messages_state else None
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        if final_response and isinstance(last_message, ToolMessage) and not new_user_turn:
            return {"messages": [AIMessage(content=strip_critic_json_fn(str(final_response)))]}
        if not incoming_turn_id and final_response and isinstance(last_message, HumanMessage):
            new_user_turn = True

        messages = _build_context_messages(state=state, new_user_turn=new_user_turn)
        response = await llm_with_tools.ainvoke(messages)
        response = coerce_supervisor_tool_calls_fn(
            response,
            orchestration_phase=str(state.get("orchestration_phase") or ""),
            agent_hops=int(state.get("agent_hops") or 0),
            allow_multiple=bool(compare_mode),
        )
        updates: dict[str, Any] = {"messages": [response]}
        if new_user_turn:
            updates.update(
                _build_executor_updates_for_new_user_turn(
                    incoming_turn_id=incoming_turn_id,
                )
            )
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id
        if final_response and new_user_turn:
            updates["final_agent_response"] = None
            updates["final_response"] = None
        return updates

    return call_model, acall_model
