from __future__ import annotations

import asyncio
from typing import Any

from app.agents.new_chat.hybrid_state import (
    GRAPH_COMPLEXITY_COMPLEX,
    GRAPH_COMPLEXITY_SIMPLE,
    GRAPH_COMPLEXITY_TRIVIAL,
    build_trivial_response,
    classify_graph_complexity,
)
from app.agents.new_chat.nodes.smart_critic import build_smart_critic_node


def test_classify_graph_complexity_trivial_greeting() -> None:
    result = classify_graph_complexity(
        resolved_intent={"route": "knowledge", "confidence": 0.9},
        user_query="Hej!",
    )
    assert result == GRAPH_COMPLEXITY_TRIVIAL


def test_classify_graph_complexity_simple_action_query() -> None:
    result = classify_graph_complexity(
        resolved_intent={"route": "action", "confidence": 0.84},
        user_query="Vad blir vadret i Uppsala i morgon?",
    )
    assert result == GRAPH_COMPLEXITY_SIMPLE


def test_classify_graph_complexity_statistics_forces_complex() -> None:
    result = classify_graph_complexity(
        resolved_intent={"route": "statistics", "confidence": 0.95},
        user_query="Visa statistik for arbetsloshet i alla lan",
    )
    assert result == GRAPH_COMPLEXITY_COMPLEX


def test_build_trivial_response_only_for_greetings() -> None:
    assert build_trivial_response("Hej!") is not None
    assert build_trivial_response("Hur ser trafiken ut?") is None


def test_smart_critic_mechanical_ok_path() -> None:
    fallback_called = {"value": False}

    async def fallback_critic(
        state: dict[str, Any],
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        fallback_called["value"] = True
        return {"critic_decision": "ok", "orchestration_phase": "finalize"}

    smart_critic = build_smart_critic_node(
        fallback_critic_node=fallback_critic,
        contract_from_payload_fn=lambda payload: dict(payload.get("result_contract") or {})
        if isinstance(payload, dict)
        else {},
        latest_user_query_fn=lambda messages: "test query",
        max_replan_attempts=2,
    )

    state = {
        "final_response": "Klar svarstext",
        "step_results": [
            {
                "result_contract": {
                    "status": "success",
                    "confidence": 0.91,
                    "missing_fields": [],
                }
            }
        ],
        "replan_count": 0,
    }

    result = asyncio.run(smart_critic(state))
    assert result.get("critic_decision") == "ok"
    assert result.get("orchestration_phase") == "finalize"
    assert fallback_called["value"] is False


def test_smart_critic_needs_more_with_targeted_missing_info() -> None:
    async def fallback_critic(
        state: dict[str, Any],
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        return {"critic_decision": "ok", "orchestration_phase": "finalize"}

    smart_critic = build_smart_critic_node(
        fallback_critic_node=fallback_critic,
        contract_from_payload_fn=lambda payload: dict(payload.get("result_contract") or {})
        if isinstance(payload, dict)
        else {},
        latest_user_query_fn=lambda messages: "test query",
        max_replan_attempts=3,
    )

    state = {
        "final_response": "",
        "step_results": [
            {
                "result_contract": {
                    "status": "partial",
                    "confidence": 0.62,
                    "missing_fields": ["departure_time", "destination"],
                }
            }
        ],
        "replan_count": 0,
    }

    result = asyncio.run(smart_critic(state))
    assert result.get("critic_decision") == "needs_more"
    assert result.get("orchestration_phase") == "resolve_tools"
    assert result.get("targeted_missing_info") == ["departure_time", "destination"]
