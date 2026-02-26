from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..structured_schemas import (
    CriticResult,
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)


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
    max_total_steps: int = 12,
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
        replan_count = int(state.get("replan_count") or 0)
        total_steps = int(state.get("total_steps") or 0)
        critic_history = list(state.get("critic_history") or [])

        # --- P1 guard_finalized: respect orchestration_guard decision ---
        if state.get("guard_finalized") and final_response:
            logger.info(
                "critic: guard_finalized=True, accepting response (total_steps=%d)",
                total_steps,
            )
            return {
                "critic_decision": "ok",
                "final_response": final_response,
                "orchestration_phase": "finalize",
                "critic_history": critic_history + [
                    {"decision": "ok", "reason": "guard_finalized", "step": total_steps}
                ],
            }

        # --- P1 total_steps hard cap: force to synthesis ---
        if total_steps >= max_total_steps:
            logger.info(
                "critic: total_steps=%d >= max=%d, forcing synthesis",
                total_steps,
                max_total_steps,
            )
            if not final_response:
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
                    "critic_history": critic_history + [
                        {"decision": "ok", "reason": "max_total_steps", "step": total_steps}
                    ],
                }
            return {
                "critic_decision": "ok",
                "final_response": final_response,
                "orchestration_phase": "finalize",
                "critic_history": critic_history + [
                    {"decision": "ok", "reason": "max_total_steps", "step": total_steps}
                ],
            }

        if not final_response:
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
                    "critic_history": critic_history + [
                        {"decision": "ok", "reason": "max_replan_no_response", "step": total_steps}
                    ],
                }
            return {
                "critic_decision": "needs_more",
                "replan_count": replan_count + 1,
                "orchestration_phase": "select_agent",
                "critic_history": critic_history + [
                    {"decision": "needs_more", "reason": "no_response", "step": total_steps}
                ],
            }

        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        graph_complexity = str(state.get("graph_complexity") or "").strip().lower()
        if graph_complexity == "simple":
            # Keep simple-path latency low by skipping an additional critic pass.
            return {
                "critic_decision": "ok",
                "final_response": final_response,
                "orchestration_phase": "finalize",
                "critic_history": critic_history + [
                    {"decision": "ok", "reason": "simple_passthrough", "step": total_steps}
                ],
            }

        # --- P1 adaptive threshold: check if critic has already made identical decisions ---
        recent_needs_more = sum(
            1 for h in critic_history[-3:]
            if h.get("decision") == "needs_more"
        )
        if recent_needs_more >= 2:
            # Critic has said needs_more twice recently — force accept to break loop.
            logger.info(
                "critic: %d consecutive needs_more in history, forcing ok",
                recent_needs_more,
            )
            return {
                "critic_decision": "ok",
                "final_response": final_response,
                "orchestration_phase": "finalize",
                "critic_history": critic_history + [
                    {"decision": "ok", "reason": "adaptive_break_loop", "step": total_steps}
                ],
            }

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
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 250}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    CriticResult, "critic_result"
                )
            message = await llm.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=critic_input)],
                **_invoke_kwargs,
            )
            _raw_content = str(getattr(message, "content", "") or "")
            # P1 Extra: try Pydantic structured parse, fall back to regex
            try:
                _structured = CriticResult.model_validate_json(_raw_content)
                parsed_decision = _structured.decision
            except Exception:
                parsed = extract_first_json_object_fn(_raw_content)
                parsed_decision = str(parsed.get("decision") or "").strip().lower()
            if parsed_decision in {"ok", "needs_more", "replan"}:
                decision = parsed_decision
        except Exception:
            decision = "ok"

        new_history_entry = {"decision": decision, "reason": "llm", "step": total_steps}

        if decision == "replan" and replan_count < max_replan_attempts:
            return {
                "critic_decision": "replan",
                "final_agent_response": None,
                "final_response": None,
                "replan_count": replan_count + 1,
                "orchestration_phase": "plan",
                "critic_history": critic_history + [new_history_entry],
            }
        if decision == "needs_more" and replan_count < max_replan_attempts:
            return {
                "critic_decision": "needs_more",
                "final_agent_response": None,
                "final_response": None,
                "replan_count": replan_count + 1,
                "orchestration_phase": "select_agent",
                "critic_history": critic_history + [new_history_entry],
            }
        return {
            "critic_decision": "ok",
            "final_response": final_response,
            "orchestration_phase": "finalize",
            "critic_history": critic_history + [new_history_entry],
        }

    return critic_node
