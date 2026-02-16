from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig


def build_synthesizer_node(
    *,
    llm: Any,
    synthesizer_prompt_template: str,
    compare_synthesizer_prompt_template: str | None = None,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
    strip_critic_json_fn: Callable[[str], str],
):
    async def synthesizer_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        source_response = str(
            state.get("final_response") or state.get("final_agent_response") or ""
        ).strip()
        if not source_response:
            return {}
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        
        # Use compare-specific prompt if in compare mode
        route_hint = str(state.get("route_hint") or "").strip().lower()
        if route_hint == "compare" and compare_synthesizer_prompt_template:
            prompt_template = compare_synthesizer_prompt_template
        else:
            prompt_template = synthesizer_prompt_template
        
        prompt = append_datetime_context_fn(prompt_template)
        synth_input = json.dumps(
            {
                "query": latest_user_query,
                "response": source_response,
                "resolved_intent": state.get("resolved_intent") or {},
            },
            ensure_ascii=True,
        )
        refined_response = source_response
        try:
            message = await llm.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=synth_input)]
            )
            parsed = extract_first_json_object_fn(str(getattr(message, "content", "") or ""))
            candidate = str(parsed.get("response") or "").strip()
            if candidate:
                refined_response = strip_critic_json_fn(candidate)
        except Exception:
            refined_response = source_response

        messages = list(state.get("messages") or [])
        last_message = messages[-1] if messages else None
        if isinstance(last_message, AIMessage):
            if str(getattr(last_message, "content", "") or "").strip() == refined_response:
                return {
                    "final_response": refined_response,
                    "final_agent_response": refined_response,
                    "plan_complete": True,
                    "awaiting_confirmation": False,
                    "pending_hitl_stage": None,
                    "pending_hitl_payload": None,
                }
        return {
            "messages": [AIMessage(content=refined_response)],
            "final_response": refined_response,
            "final_agent_response": refined_response,
            "plan_complete": True,
            "awaiting_confirmation": False,
            "pending_hitl_stage": None,
            "pending_hitl_payload": None,
        }

    return synthesizer_node
