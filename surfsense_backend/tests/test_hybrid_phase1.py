from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from typing import Any


def _load_module(module_name: str, relative_path: str):
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


hybrid_state = _load_module(
    "hybrid_state_test_module",
    "app/agents/new_chat/hybrid_state.py",
)
smart_critic_module = _load_module(
    "smart_critic_test_module",
    "app/agents/new_chat/nodes/smart_critic.py",
)


def test_classify_graph_complexity_trivial_greeting() -> None:
    result = hybrid_state.classify_graph_complexity(
        resolved_intent={"route": "knowledge", "confidence": 0.9},
        user_query="Hej!",
    )
    assert result == hybrid_state.GRAPH_COMPLEXITY_TRIVIAL


def test_classify_graph_complexity_simple_action_query() -> None:
    result = hybrid_state.classify_graph_complexity(
        resolved_intent={"route": "action", "confidence": 0.84},
        user_query="Vad blir vadret i Uppsala i morgon?",
    )
    assert result == hybrid_state.GRAPH_COMPLEXITY_SIMPLE


def test_classify_graph_complexity_statistics_forces_complex() -> None:
    # After execution_mode refactoring, statistics queries classify as
    # tool_required which maps to "simple" (single-agent pipeline).
    # Multi-source queries use GRAPH_COMPLEXITY_COMPLEX.
    result = hybrid_state.classify_graph_complexity(
        resolved_intent={"route": "statistics", "confidence": 0.95},
        user_query="Visa statistik for arbetsloshet i alla lan",
    )
    assert result == hybrid_state.GRAPH_COMPLEXITY_SIMPLE


def test_build_trivial_response_only_for_greetings() -> None:
    assert hybrid_state.build_trivial_response("Hej!") is not None
    assert hybrid_state.build_trivial_response("Hur ser trafiken ut?") is None


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

    smart_critic = smart_critic_module.build_smart_critic_node(
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

    smart_critic = smart_critic_module.build_smart_critic_node(
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


def test_smart_critic_finalizes_from_successful_step_when_final_missing() -> None:
    fallback_called = {"value": False}

    async def fallback_critic(
        state: dict[str, Any],
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        fallback_called["value"] = True
        return {"critic_decision": "needs_more", "orchestration_phase": "resolve_tools"}

    smart_critic = smart_critic_module.build_smart_critic_node(
        fallback_critic_node=fallback_critic,
        contract_from_payload_fn=lambda payload: dict(payload.get("result_contract") or {})
        if isinstance(payload, dict)
        else {},
        latest_user_query_fn=lambda messages: "test query",
        max_replan_attempts=2,
    )

    state = {
        "final_response": "",
        "step_results": [
            {
                "agent": "trafik",
                "response": "Det finns flera temporara hastighetsgranser pa E6.",
                "result_contract": {
                    "status": "success",
                    "confidence": 0.93,
                    "missing_fields": [],
                    "agent": "trafik",
                },
            }
        ],
        "replan_count": 0,
    }

    result = asyncio.run(smart_critic(state))
    assert result.get("critic_decision") == "ok"
    assert result.get("orchestration_phase") == "finalize"
    assert result.get("final_response") == "Det finns flera temporara hastighetsgranser pa E6."
    assert result.get("final_agent_response") == "Det finns flera temporara hastighetsgranser pa E6."
    assert result.get("final_agent_name") == "trafik"
    assert fallback_called["value"] is False
