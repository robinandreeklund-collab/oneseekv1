from __future__ import annotations

from typing import Any, Callable
from langchain_core.runnables import RunnableConfig


def _safe_confidence(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def _collect_recent_responses(state: dict[str, Any], *, limit: int = 3) -> list[str]:
    step_results = state.get("step_results") or []
    responses: list[str] = []
    for item in reversed(step_results):
        if not isinstance(item, dict):
            continue
        response = str(item.get("response") or "").strip()
        if not response:
            continue
        responses.append(response)
        if len(responses) >= max(1, int(limit)):
            break
    responses.reverse()
    return responses


def _average_contract_confidence(state: dict[str, Any], *, limit: int = 3) -> float:
    step_results = state.get("step_results") or []
    confidences: list[float] = []
    for item in reversed(step_results):
        if not isinstance(item, dict):
            continue
        contract = item.get("result_contract")
        if not isinstance(contract, dict):
            continue
        confidences.append(_safe_confidence(contract.get("confidence"), 0.0))
        if len(confidences) >= max(1, int(limit)):
            break
    if not confidences:
        return 0.0
    return sum(confidences) / len(confidences)


def build_progressive_synthesizer_node(
    *,
    truncate_for_prompt_fn: Callable[[str, int], str],
):
    async def progressive_synthesizer_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        final_response = str(
            state.get("final_response") or state.get("final_agent_response") or ""
        ).strip()
        if not final_response:
            return {}

        recent_responses = _collect_recent_responses(state, limit=3)
        avg_confidence = _average_contract_confidence(state, limit=3)

        if len(recent_responses) <= 1 and avg_confidence >= 0.9:
            return {
                "synthesis_drafts": [],
                "pending_hitl_payload": {
                    "progressive_synthesis": "skipped_high_confidence_single_result"
                },
            }

        draft_source = "\n\n".join(recent_responses) if recent_responses else final_response
        draft_text = truncate_for_prompt_fn(draft_source, 1200)
        if not draft_text:
            draft_text = truncate_for_prompt_fn(final_response, 1200)
        if not draft_text:
            return {"synthesis_drafts": []}

        draft_payload = {
            "draft": draft_text,
            "confidence": 0.6,
            "version": 0,
        }
        return {
            "synthesis_drafts": [draft_payload],
            "pending_hitl_payload": {
                "progressive_synthesis": "draft_generated",
                "draft_length": len(draft_text),
            },
        }

    return progressive_synthesizer_node
