from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys


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


execution_router = _load_module(
    "execution_router_phase2_test_module",
    "app/agents/new_chat/nodes/execution_router.py",
)


def test_classify_execution_strategy_parallel_for_multiple_agents() -> None:
    strategy, reason = execution_router.classify_execution_strategy(
        state={"selected_agents": [{"name": "weather"}, {"name": "trafik"}]},
        latest_user_query="Jamfor vader och trafik",
        next_step_text="",
    )
    assert strategy == execution_router.EXECUTION_STRATEGY_PARALLEL
    assert "multiple_agents" in reason


def test_classify_execution_strategy_subagent_for_bulk_signal() -> None:
    strategy, reason = execution_router.classify_execution_strategy(
        state={"selected_agents": [{"name": "statistics"}]},
        latest_user_query="Hamta statistik for alla kommuner",
        next_step_text="",
    )
    assert strategy == execution_router.EXECUTION_STRATEGY_SUBAGENT
    assert reason == "bulk_signal_detected"


def test_classify_execution_strategy_subagent_for_long_plan() -> None:
    strategy, reason = execution_router.classify_execution_strategy(
        state={
            "selected_agents": [{"name": "statistics"}],
            "active_plan": [
                {"id": "1"},
                {"id": "2"},
                {"id": "3"},
                {"id": "4"},
            ],
        },
        latest_user_query="Komplicerad statistik",
        next_step_text="",
    )
    assert strategy == execution_router.EXECUTION_STRATEGY_SUBAGENT
    assert reason == "plan_steps:4"


def test_classify_execution_strategy_inline_for_speculative_cover() -> None:
    strategy, reason = execution_router.classify_execution_strategy(
        state={
            "selected_agents": [{"name": "weather"}],
            "resolved_tools_by_agent": {"weather": ["smhi_weather"]},
            "speculative_results": {"smhi_weather": {"status": "success"}},
        },
        latest_user_query="Vader i Uppsala",
        next_step_text="",
    )
    assert strategy == execution_router.EXECUTION_STRATEGY_INLINE
    assert reason == "speculative_cover_all"


def test_get_execution_timeout_seconds_by_strategy() -> None:
    assert execution_router.get_execution_timeout_seconds("inline") == 120
    assert execution_router.get_execution_timeout_seconds("parallel") == 120
    assert execution_router.get_execution_timeout_seconds("subagent") == 300


def test_execution_router_node_returns_strategy_payload() -> None:
    node = execution_router.build_execution_router_node(
        latest_user_query_fn=lambda messages: "Hamta statistik for alla kommuner",
        next_plan_step_fn=lambda state: {"content": "Sammanstall data"},
    )

    result = asyncio.run(
        node(
            {
                "selected_agents": [{"name": "statistics"}],
                "active_plan": [{"id": "1"}],
            }
        )
    )
    assert result.get("execution_strategy") == execution_router.EXECUTION_STRATEGY_SUBAGENT
    payload = result.get("pending_hitl_payload") or {}
    assert payload.get("execution_strategy") == execution_router.EXECUTION_STRATEGY_SUBAGENT
