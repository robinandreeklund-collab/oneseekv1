from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig


def build_critic_node(
    *,
    llm: Any,
    critic_gate_prompt_template: str,
    loop_guard_template: str,
    default_loop_guard_message: str,
    max_replan_attempts: int,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
    render_guard_message_fn: Callable[[str, list[str]], str],
):
    async def critic_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        final_response = str(
            state.get("final_agent_response") or state.get("final_response") or ""
        ).strip()
        if not final_response:
            replan_count = int(state.get("replan_count") or 0)
            if replan_count >= max_replan_attempts:
                fallback = render_guard_message_fn(
                    loop_guard_template,
                    list(state.get("guard_parallel_preview") or [])[:3],
                )
                if not fallback:
                    fallback = render_guard_message_fn(
                        default_loop_guard_message,
                        list(state.get("guard_parallel_preview") or [])[:3],
                    )
                return {
                    "critic_decision": "ok",
                    "final_response": fallback,
                    "final_agent_response": fallback,
                    "final_agent_name": "supervisor",
                    "orchestration_phase": "finalize",
                }
            return {
                "critic_decision": "needs_more",
                "replan_count": replan_count + 1,
                "orchestration_phase": "select_agent",
            }

        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        prompt = append_datetime_context_fn(critic_gate_prompt_template)
        critic_input = json.dumps(
            {
                "query": latest_user_query,
                "resolved_intent": state.get("resolved_intent") or {},
                "active_plan": state.get("active_plan") or [],
                "final_agent_name": state.get("final_agent_name"),
                "final_response": final_response,
            },
            ensure_ascii=True,
        )
        decision = "ok"
        try:
            message = await llm.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=critic_input)]
            )
            parsed = extract_first_json_object_fn(str(getattr(message, "content", "") or ""))
            parsed_decision = str(parsed.get("decision") or "").strip().lower()
            if parsed_decision in {"ok", "needs_more", "replan"}:
                decision = parsed_decision
        except Exception:
            decision = "ok"

        replan_count = int(state.get("replan_count") or 0)
        if decision == "replan" and replan_count < max_replan_attempts:
            return {
                "critic_decision": "replan",
                "final_agent_response": None,
                "final_response": None,
                "replan_count": replan_count + 1,
                "orchestration_phase": "plan",
            }
        if decision == "needs_more" and replan_count < max_replan_attempts:
            return {
                "critic_decision": "needs_more",
                "final_agent_response": None,
                "final_response": None,
                "replan_count": replan_count + 1,
                "orchestration_phase": "select_agent",
            }
        return {
            "critic_decision": "ok",
            "final_response": final_response,
            "orchestration_phase": "finalize",
        }

    return critic_node
