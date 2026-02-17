from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

_FILESYSTEM_QUERY_RE = re.compile(
    r"(/workspace|/tmp|sandbox_|\\b(file|files|fil|filer|directory|katalog|mapp|read|write|l[aä]s|skriv)\\b)",
    re.IGNORECASE,
)
_NO_DATA_MARKERS = (
    "does not exist",
    "directory not found",
    "not found",
    "finns inte",
    "saknas",
    "kunde inte",
)
_GUARD_STYLE_MARKERS = (
    "planeringsloop",
    "loop guard",
    "skicka gärna frågan igen",
    "strikt enkel exekvering",
)


def _should_passthrough_synthesizer(
    *,
    state: dict[str, Any],
    latest_user_query: str,
    source_response: str,
) -> bool:
    final_agent_name = str(state.get("final_agent_name") or "").strip().lower()
    if final_agent_name == "supervisor":
        return True
    route_hint = str(state.get("route_hint") or "").strip().lower()
    if route_hint == "action" and _FILESYSTEM_QUERY_RE.search(str(latest_user_query or "")):
        return True
    lowered = str(source_response or "").strip().lower()
    if any(marker in lowered for marker in _NO_DATA_MARKERS):
        return True
    if any(marker in lowered for marker in _GUARD_STYLE_MARKERS):
        return True
    return False


def _candidate_conflicts_with_no_data(source_response: str, candidate: str) -> bool:
    source_lower = str(source_response or "").strip().lower()
    if not any(marker in source_lower for marker in _NO_DATA_MARKERS):
        return False
    candidate_lower = str(candidate or "").strip().lower()
    if not candidate_lower:
        return True
    return not any(marker in candidate_lower for marker in _NO_DATA_MARKERS)


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

        if _should_passthrough_synthesizer(
            state=state,
            latest_user_query=latest_user_query,
            source_response=source_response,
        ):
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
            if candidate and not _candidate_conflicts_with_no_data(source_response, candidate):
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
