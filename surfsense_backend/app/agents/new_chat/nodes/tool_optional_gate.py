"""Tool-Optional Gate node — confidence gate for tool-optional queries.

When execution_mode=tool_optional, this node asks the LLM to answer directly
without tools. If the LLM is confident (>= 0.85), the answer is delivered
immediately, saving 2-5 seconds of tool pipeline latency. If not confident,
the system falls back to the full tool_required pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.85


def build_tool_optional_gate_node(
    *,
    llm: Any,
    tool_optional_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
    coerce_confidence_fn: Callable[[Any, float], float],
):
    """Build the tool_optional_gate node.

    Returns a LangGraph node function that:
    - Attempts a direct LLM answer for tool-optional queries.
    - Sets orchestration_phase="finalize" if confident (fast path).
    - Sets execution_mode="tool_required" and orchestration_phase="select_agent"
      if not confident (fallback).
    """

    async def tool_optional_gate_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        if not latest_user_query:
            # No query — fallback to tool_required
            return {
                "execution_mode": "tool_required",
                "orchestration_phase": "select_agent",
            }

        prompt = append_datetime_context_fn(tool_optional_prompt_template)
        try:
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=latest_user_query),
                ],
                max_tokens=600,
            )
            parsed = extract_first_json_object_fn(
                str(getattr(message, "content", "") or "")
            )
            can_answer = bool(parsed.get("can_answer", False))
            confidence = coerce_confidence_fn(parsed.get("confidence"), 0.0)
            response_text = str(parsed.get("response") or "").strip()
        except Exception:
            logger.warning("tool_optional_gate: LLM call failed, falling back to tool_required")
            return {
                "execution_mode": "tool_required",
                "orchestration_phase": "select_agent",
            }

        if can_answer and confidence >= _CONFIDENCE_THRESHOLD and response_text:
            logger.info(
                "tool_optional_gate: confident answer (%.2f), delivering directly",
                confidence,
            )
            return {
                "final_agent_response": response_text,
                "final_response": response_text,
                "final_agent_name": "tool_optional_gate",
                "orchestration_phase": "finalize",
                "messages": [AIMessage(content=response_text)],
            }

        # Not confident enough — fall back to full pipeline
        logger.info(
            "tool_optional_gate: not confident enough (%.2f), falling back to tool_required",
            confidence,
        )
        return {
            "execution_mode": "tool_required",
            "orchestration_phase": "select_agent",
        }

    return tool_optional_gate_node
