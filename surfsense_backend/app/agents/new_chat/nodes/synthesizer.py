from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..structured_schemas import (
    SynthesizerResult,
    pydantic_to_response_format,
    structured_output_enabled,
)
from ..supervisor_memory import (
    _format_artifact_contents_for_context,
    _load_recent_artifact_contents,
)

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
    "returnerade ingen data",
    "returnerade tom data",
    "data saknas",
    "ingen data",
)
_GUARD_STYLE_MARKERS = (
    "planeringsloop",
    "loop guard",
    "skicka gärna frågan igen",
    "strikt enkel exekvering",
)
# Markers that indicate an SCB fetch failure — the subagent may still
# produce plausible-sounding text, but no real data was retrieved.
_SCB_FETCH_FAILURE_MARKERS = (
    "kunde inte hamta",
    "kunde inte hämta",
    "fetch failed",
    "data fetch failed",
    "400 bad request",
    "scb_fetch misslyckades",
    "<tool_call>",  # LLM emitted XML tool call as text = format failure
    '"next_step"',  # scb_validate succeeded but scb_fetch was never called
)
# Regex to strip leaked <tool_call> XML blocks from responses.
_TEXT_TOOL_CALL_STRIP_RE = re.compile(
    r"<tool_call>.*?</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_SYNTH_PLACEHOLDER_RESPONSES = {
    "guardrail",
    "no-data",
    "not-found",
    "n/a",
    "none",
    "ok",
}


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
    if route_hint in {"skapande", "action"} and _FILESYSTEM_QUERY_RE.search(str(latest_user_query or "")):
        return True
    lowered = str(source_response or "").strip().lower()
    if any(marker in lowered for marker in _NO_DATA_MARKERS):
        return True
    if any(marker in lowered for marker in _GUARD_STYLE_MARKERS):
        return True
    if any(marker in lowered for marker in _SCB_FETCH_FAILURE_MARKERS):
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


def _candidate_is_degenerate(source_response: str, candidate: str) -> bool:
    candidate_text = str(candidate or "").strip()
    if not candidate_text:
        return True
    candidate_lower = candidate_text.lower()
    source_lower = str(source_response or "").strip().lower()

    # Never replace a meaningful source answer with generic placeholders.
    if candidate_lower in _SYNTH_PLACEHOLDER_RESPONSES and candidate_lower != source_lower:
        return True

    # Single-token rewrites are almost always regressions in synthesis.
    if (
        len(candidate_text.split()) <= 2
        and len(candidate_text) <= 24
        and len(str(source_response or "").strip()) > len(candidate_text)
    ):
        return True

    return False


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
        # Strip leaked <tool_call> XML blocks that the LLM emitted as text
        # instead of structured tool calls — never let raw XML reach the user.
        if "<tool_call>" in source_response:
            source_response = _TEXT_TOOL_CALL_STRIP_RE.sub("", source_response).strip()
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        graph_complexity = str(state.get("graph_complexity") or "").strip().lower()
        if graph_complexity == "simple":
            # Simple flows should avoid an extra synthesis rewrite call.
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
        if route_hint in {"jämförelse", "compare"} and compare_synthesizer_prompt_template:
            prompt_template = compare_synthesizer_prompt_template
        else:
            prompt_template = synthesizer_prompt_template
        
        prompt = append_datetime_context_fn(prompt_template)

        # Inject artifact contents so the synthesizer has access to full
        # tool data that was offloaded from context during artifact indexing.
        artifact_data_context = ""
        artifact_contents = _load_recent_artifact_contents(
            state.get("artifact_manifest"),
        )
        if artifact_contents:
            artifact_data_context = _format_artifact_contents_for_context(
                artifact_contents
            )

        synth_payload: dict[str, Any] = {
            "query": latest_user_query,
            "response": source_response,
            "resolved_intent": state.get("resolved_intent") or {},
        }
        if artifact_data_context:
            synth_payload["artifact_data"] = artifact_data_context
        synth_input = json.dumps(synth_payload, ensure_ascii=True)
        refined_response = source_response
        try:
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 800}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    SynthesizerResult, "synthesizer_result"
                )
            message = await llm.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=synth_input)],
                **_invoke_kwargs,
            )
            _raw_content = str(getattr(message, "content", "") or "")
            # P1 Extra: try Pydantic structured parse, fall back to regex
            try:
                _structured = SynthesizerResult.model_validate_json(_raw_content)
                candidate = _structured.response.strip()
            except Exception:
                parsed = extract_first_json_object_fn(_raw_content)
                candidate = str(parsed.get("response") or "").strip()
            if (
                candidate
                and not _candidate_conflicts_with_no_data(source_response, candidate)
                and not _candidate_is_degenerate(source_response, candidate)
            ):
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
