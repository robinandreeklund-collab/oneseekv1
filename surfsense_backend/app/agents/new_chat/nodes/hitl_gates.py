from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import AIMessage


def build_planner_hitl_gate_node(
    *,
    hitl_enabled_fn: Callable[[str], bool],
    plan_preview_text_fn: Callable[[dict[str, Any]], str],
    render_hitl_message_fn: Callable[..., str],
    hitl_planner_message_template: str,
):
    async def planner_hitl_gate_node(
        state: dict[str, Any],
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        if not hitl_enabled_fn("planner"):
            return {"orchestration_phase": "resolve_tools"}
        if bool(state.get("awaiting_confirmation")) and str(
            state.get("pending_hitl_stage") or ""
        ).strip().lower() == "planner":
            return {"orchestration_phase": "awaiting_confirmation"}
        feedback = state.get("user_feedback")
        if isinstance(feedback, dict):
            if (
                str(feedback.get("decision") or "").strip().lower() == "approve"
                and str(feedback.get("stage") or "").strip().lower() == "planner"
            ):
                return {"orchestration_phase": "resolve_tools", "user_feedback": None}
        plan_preview = plan_preview_text_fn(state)
        message = render_hitl_message_fn(
            hitl_planner_message_template,
            plan_preview=plan_preview,
        )
        return {
            "messages": [AIMessage(content=message)],
            "awaiting_confirmation": True,
            "pending_hitl_stage": "planner",
            "pending_hitl_payload": {"plan_preview": plan_preview},
            "orchestration_phase": "awaiting_confirmation",
        }

    return planner_hitl_gate_node


def build_execution_hitl_gate_node(
    *,
    hitl_enabled_fn: Callable[[str], bool],
    next_plan_step_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    render_hitl_message_fn: Callable[..., str],
    hitl_execution_message_template: str,
):
    async def execution_hitl_gate_node(
        state: dict[str, Any],
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        if not hitl_enabled_fn("execution"):
            return {"orchestration_phase": "execute"}
        if bool(state.get("awaiting_confirmation")) and str(
            state.get("pending_hitl_stage") or ""
        ).strip().lower() == "execution":
            return {"orchestration_phase": "awaiting_confirmation"}
        feedback = state.get("user_feedback")
        if isinstance(feedback, dict):
            if (
                str(feedback.get("decision") or "").strip().lower() == "approve"
                and str(feedback.get("stage") or "").strip().lower() == "execution"
            ):
                return {"orchestration_phase": "execute", "user_feedback": None}

        step = next_plan_step_fn(state)
        step_preview = (
            str(step.get("content") or "").strip()
            if isinstance(step, dict)
            else "Kora nasta steg i planen."
        )
        resolved_map = state.get("resolved_tools_by_agent") or {}
        tool_preview_parts: list[str] = []
        if isinstance(resolved_map, dict):
            for agent_name, tool_ids in list(resolved_map.items())[:2]:
                if not isinstance(tool_ids, list):
                    continue
                names = [str(item).strip() for item in tool_ids if str(item).strip()][:3]
                if names:
                    tool_preview_parts.append(f"{agent_name}: {', '.join(names)}")
        tool_preview = (
            " | ".join(tool_preview_parts) if tool_preview_parts else "Inga tydliga verktyg valda"
        )
        message = render_hitl_message_fn(
            hitl_execution_message_template,
            step_preview=step_preview,
            tool_preview=tool_preview,
        )
        return {
            "messages": [AIMessage(content=message)],
            "awaiting_confirmation": True,
            "pending_hitl_stage": "execution",
            "pending_hitl_payload": {
                "step_preview": step_preview,
                "tool_preview": tool_preview,
            },
            "orchestration_phase": "awaiting_confirmation",
        }

    return execution_hitl_gate_node


def build_synthesis_hitl_gate_node(
    *,
    hitl_enabled_fn: Callable[[str], bool],
    truncate_for_prompt_fn: Callable[[str, int], str],
    render_hitl_message_fn: Callable[..., str],
    hitl_synthesis_message_template: str,
):
    async def synthesis_hitl_gate_node(
        state: dict[str, Any],
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        if not hitl_enabled_fn("synthesis"):
            return {}
        if bool(state.get("awaiting_confirmation")) and str(
            state.get("pending_hitl_stage") or ""
        ).strip().lower() == "synthesis":
            return {"orchestration_phase": "awaiting_confirmation"}
        feedback = state.get("user_feedback")
        if isinstance(feedback, dict):
            feedback_decision = str(feedback.get("decision") or "").strip().lower()
            feedback_stage = str(feedback.get("stage") or "").strip().lower()
            if feedback_stage == "synthesis":
                if feedback_decision == "approve":
                    return {"user_feedback": None}
                if feedback_decision == "reject":
                    return {
                        "final_response": None,
                        "final_agent_response": None,
                        "critic_decision": "replan",
                        "orchestration_phase": "plan",
                        "user_feedback": None,
                    }
        response_preview = truncate_for_prompt_fn(
            str(state.get("final_response") or state.get("final_agent_response") or ""),
            280,
        )
        if not response_preview:
            return {}
        message = render_hitl_message_fn(
            hitl_synthesis_message_template,
            response_preview=response_preview,
        )
        return {
            "messages": [AIMessage(content=message)],
            "awaiting_confirmation": True,
            "pending_hitl_stage": "synthesis",
            "pending_hitl_payload": {"response_preview": response_preview},
            "orchestration_phase": "awaiting_confirmation",
        }

    return synthesis_hitl_gate_node
