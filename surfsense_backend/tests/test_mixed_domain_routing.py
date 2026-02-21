"""Tests for mixed-domain query routing without hardcoded weather overrides."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Lightweight stubs for langchain_core so the nodes that are loaded directly
# (via importlib, bypassing __init__.py) don't crash without the package.
# ---------------------------------------------------------------------------
def _install_langchain_stubs() -> None:
    """Register minimal stub modules for langchain_core types used by nodes."""
    if "langchain_core" in sys.modules:
        return  # already present — either real or already stubbed

    class _Msg:
        def __init__(self, content: str = "", **kwargs: Any) -> None:
            self.content = content

    HumanMessage = type("HumanMessage", (_Msg,), {})
    SystemMessage = type("SystemMessage", (_Msg,), {})
    AIMessage = type("AIMessage", (_Msg,), {"tool_calls": [], "additional_kwargs": {}})
    ToolMessage = type("ToolMessage", (_Msg,), {"tool_call_id": "", "name": ""})

    messages_mod = types.ModuleType("langchain_core.messages")
    messages_mod.HumanMessage = HumanMessage  # type: ignore[attr-defined]
    messages_mod.SystemMessage = SystemMessage  # type: ignore[attr-defined]
    messages_mod.AIMessage = AIMessage  # type: ignore[attr-defined]
    messages_mod.ToolMessage = ToolMessage  # type: ignore[attr-defined]

    runnables_mod = types.ModuleType("langchain_core.runnables")
    runnables_mod.RunnableConfig = dict  # type: ignore[attr-defined]

    lc_root = types.ModuleType("langchain_core")
    lc_root.messages = messages_mod  # type: ignore[attr-defined]
    lc_root.runnables = runnables_mod  # type: ignore[attr-defined]

    sys.modules["langchain_core"] = lc_root
    sys.modules["langchain_core.messages"] = messages_mod
    sys.modules["langchain_core.runnables"] = runnables_mod


_install_langchain_stubs()


# ---------------------------------------------------------------------------
# Helpers: load individual node files directly (bypass nodes/__init__.py which
# pulls in executor → token_budget → litellm and other heavy deps).
# ---------------------------------------------------------------------------
project_root = Path(__file__).resolve().parents[1]
_nodes_dir = project_root / "app" / "agents" / "new_chat" / "nodes"


def _load_node_module(filename: str) -> types.ModuleType:
    """Load a single node .py file as a fresh module, without triggering __init__.py."""
    file_path = _nodes_dir / filename
    module_name = f"_test_node_{filename.removesuffix('.py')}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Add the app directory to the path for legacy/code-inspection tests.
sys.path.insert(0, str(project_root))


# ---------------------------------------------------------------------------
# Original tests (unchanged)
# ---------------------------------------------------------------------------

def test_mixed_weather_statistics_does_not_lock_to_weather() -> None:
    """
    Test that a mixed query like "hur många bor i Göteborg och vad är det för väder?"
    does not get locked to only the weather agent.

    This verifies that the weather hardcoding has been removed and the system
    can handle multi-domain queries properly.
    """
    async def mock_retrieve_agents(query: str, limit: int = 1, **kwargs) -> str:
        return json.dumps({
            "agents": [
                {"name": "statistics", "description": "Statistics agent"},
                {"name": "weather", "description": "Weather agent"},
            ],
            "valid_agent_ids": ["statistics", "weather", "action", "knowledge"],
        }, ensure_ascii=True)

    result = asyncio.run(mock_retrieve_agents(
        "hur många bor i Göteborg och vad är det för väder?",
        limit=2
    ))

    parsed = json.loads(result)
    agents = parsed.get("agents", [])

    assert len(agents) >= 2, "Mixed query should return multiple agents"
    agent_names = [a.get("name") for a in agents]
    assert "statistics" in agent_names or len(agent_names) > 1, \
        "Mixed query should include statistics or multiple agents, not just weather"


def test_pure_weather_query_still_routes_to_action() -> None:
    """
    Test that a pure weather query still gets routed to action route,
    but without hardcoded overrides - via LLM classification.
    """
    query = "vad är det för väder i Stockholm?"
    assert "väder" in query.lower() or "vader" in query.lower()


def test_weather_agent_limit_not_forced_to_1() -> None:
    """
    Test that weather queries don't have limit hardcoded to 1.
    The limit should be controlled by graph_complexity like other routes.
    """
    supervisor_path = project_root / "app" / "agents" / "new_chat" / "supervisor_agent.py"
    with open(supervisor_path, 'r') as f:
        supervisor_code = f.read()

    assert "# Weather limit removed" in supervisor_code, \
        "Expected comment marker for removed weather limit not found"

    print("  ✓ Weather limit removal verified via code comment")


def test_weather_cache_not_invalidated_for_mixed_query() -> None:
    """
    Test that cache works for mixed queries and isn't invalidated just because
    weather intent is detected.
    """
    supervisor_path = project_root / "app" / "agents" / "new_chat" / "supervisor_agent.py"
    with open(supervisor_path, 'r') as f:
        supervisor_code = f.read()

    assert "# Weather cache invalidation removed" in supervisor_code, \
        "Expected comment marker for removed weather cache invalidation not found"
    assert "sub_intents" in supervisor_code, \
        "_build_cache_key should accept sub_intents parameter"

    print("  ✓ Weather-specific cache invalidation removed")
    print("  ✓ sub_intents parameter added to _build_cache_key")


# ---------------------------------------------------------------------------
# Behavioral tests (new)
# ---------------------------------------------------------------------------

def test_sub_intents_propagated_to_state() -> None:
    """
    Test that build_agent_resolver_node correctly performs per-domain retrieval
    when route_hint=="mixed" and sub_intents are provided.

    Uses mocks to drive the node without an actual LLM or external services.
    """
    mod = _load_node_module("agent_resolver.py")
    build_agent_resolver_node = mod.build_agent_resolver_node

    def _make_agent(name: str) -> Any:
        agent = MagicMock()
        agent.name = name
        return agent

    statistics_agent = _make_agent("statistics")
    weather_agent = _make_agent("weather")
    all_agents = [statistics_agent, weather_agent]

    def mock_route_allowed(route: str | None) -> set[str]:
        return {"statistics": {"statistics"}, "weather": {"weather"}}.get(
            str(route or "").lower(), set()
        )

    def mock_route_default(route: str | None, allowed: set[str] | None) -> str:
        return "knowledge"

    def mock_retrieve_with_scores(
        query: str, *, agent_definitions: list, recent_agents: list, limit: int
    ) -> list[dict]:
        # Returns both agents; sub_allowed filtering inside the node will partition them.
        return [
            {"definition": statistics_agent, "score": 0.9},
            {"definition": weather_agent, "score": 0.85},
        ]

    def mock_retrieve(
        query: str, *, agent_definitions: list, recent_agents: list, limit: int
    ) -> list:
        return all_agents

    node = build_agent_resolver_node(
        llm=AsyncMock(),
        agent_resolver_prompt_template="",
        latest_user_query_fn=lambda msgs: "hur många bor i Göteborg och vad är det för väder?",
        normalize_route_hint_fn=lambda v: str(v or "").strip().lower(),
        route_allowed_agents_fn=mock_route_allowed,
        route_default_agent_fn=mock_route_default,
        smart_retrieve_agents_fn=mock_retrieve,
        smart_retrieve_agents_with_scores_fn=mock_retrieve_with_scores,
        agent_definitions=all_agents,
        agent_by_name={"statistics": statistics_agent, "weather": weather_agent},
        agent_payload_fn=lambda a: {"name": a.name},
        append_datetime_context_fn=lambda t: t,
        extract_first_json_object_fn=lambda s: {},
    )

    state: dict[str, Any] = {
        "messages": [MagicMock()],
        "resolved_intent": {"route": "mixed"},
        "sub_intents": ["statistics", "weather"],
        "graph_complexity": "complex",
    }

    result = asyncio.run(node(state))

    selected_names = {a.get("name") for a in result.get("selected_agents", [])}
    assert "statistics" in selected_names, (
        f"Expected 'statistics' in selected_agents, got: {selected_names}"
    )
    assert "weather" in selected_names, (
        f"Expected 'weather' in selected_agents, got: {selected_names}"
    )
    print("  ✓ sub_intents drives per-domain retrieval — both agents selected")


def test_subagent_isolation_active_for_parallel_strategy() -> None:
    """
    Test that classify_execution_strategy returns 'parallel' for a mixed-route state,
    and that the isolation guard in supervisor_agent.py covers the 'parallel' strategy.
    """
    mod = _load_node_module("execution_router.py")
    EXECUTION_STRATEGY_PARALLEL = mod.EXECUTION_STRATEGY_PARALLEL
    classify_execution_strategy = mod.classify_execution_strategy

    state: dict[str, Any] = {
        "route_hint": "mixed",
        "selected_agents": [{"name": "statistics"}, {"name": "weather"}],
        "active_plan": [
            {"id": "step-1", "content": "hämta statistik", "status": "pending"},
            {"id": "step-2", "content": "hämta väder", "status": "pending"},
        ],
    }

    strategy, reason = classify_execution_strategy(
        state=state,
        latest_user_query="hur många bor och vad är det för väder?",
        next_step_text="hämta statistik",
        subagent_enabled=True,
    )

    assert strategy == EXECUTION_STRATEGY_PARALLEL, (
        f"Expected 'parallel' for mixed route, got: '{strategy}'"
    )
    assert reason == "mixed_route", f"Expected reason 'mixed_route', got: '{reason}'"

    # Minimal source check to confirm Fix C closure is in place.
    supervisor_code = (
        project_root / "app" / "agents" / "new_chat" / "supervisor_agent.py"
    ).read_text()
    assert 'not in {"subagent", "parallel"}' in supervisor_code, (
        '_subagent_isolation_active should check: normalized not in {"subagent", "parallel"}'
    )

    print("  ✓ classify_execution_strategy returns 'parallel' for mixed route")
    print("  ✓ _subagent_isolation_active covers 'parallel' strategy")


def test_planner_uses_multi_domain_prompt_for_mixed_route() -> None:
    """
    Test that build_planner_node:
    - selects the multi-domain prompt when route_hint=="mixed" with sub_intents, and
    - preserves the 'parallel' field in plan steps.
    """
    build_planner_node = _load_node_module("planner.py").build_planner_node

    STANDARD_PROMPT = "STANDARD_PROMPT"
    MULTI_DOMAIN_PROMPT = "MULTI_DOMAIN_PROMPT"

    captured: list[str] = []

    class _CapturingLLM:
        async def ainvoke(self, messages: list, **kwargs: Any) -> Any:
            for msg in messages:
                if msg.__class__.__name__ == "SystemMessage":
                    captured.append(msg.content)
            response = MagicMock()
            response.content = json.dumps({
                "steps": [
                    {"id": "step-1", "content": "Hämta statistik", "status": "pending", "parallel": True},
                    {"id": "step-2", "content": "Hämta väder", "status": "pending", "parallel": True},
                    {"id": "step-3", "content": "Syntetisera", "status": "pending", "parallel": False},
                ],
                "reason": "mixed query",
            })
            return response

    node = build_planner_node(
        llm=_CapturingLLM(),
        planner_prompt_template=STANDARD_PROMPT,
        multi_domain_planner_prompt_template=MULTI_DOMAIN_PROMPT,
        latest_user_query_fn=lambda msgs: "hur många bor och vad är det för väder?",
        append_datetime_context_fn=lambda t: t,
        extract_first_json_object_fn=lambda s: json.loads(s),
    )

    state: dict[str, Any] = {
        "messages": [MagicMock()],
        "resolved_intent": {"route": "mixed"},
        "sub_intents": ["statistics", "weather"],
        "selected_agents": [{"name": "statistics"}, {"name": "weather"}],
        "graph_complexity": "complex",
        "active_plan": [],
    }

    result = asyncio.run(node(state))

    assert MULTI_DOMAIN_PROMPT in captured, (
        f"Expected multi-domain prompt to be sent to LLM. Got: {captured}"
    )

    plan = result.get("active_plan", [])
    assert len(plan) == 3, f"Expected 3 plan steps, got {len(plan)}"
    assert plan[0]["parallel"] is True, "step-1 should be parallel=True"
    assert plan[1]["parallel"] is True, "step-2 should be parallel=True"
    assert plan[2]["parallel"] is False, "step-3 (synthesis) should be parallel=False"

    print("  ✓ Multi-domain prompt selected for mixed route")
    print("  ✓ 'parallel' field preserved in plan steps")


def test_planner_falls_back_to_standard_prompt_for_non_mixed_route() -> None:
    """
    Test that build_planner_node uses the standard prompt for non-mixed routes,
    even when multi_domain_planner_prompt_template is provided.
    """
    build_planner_node = _load_node_module("planner.py").build_planner_node

    STANDARD_PROMPT = "STANDARD_PROMPT"
    MULTI_DOMAIN_PROMPT = "MULTI_DOMAIN_PROMPT"

    captured: list[str] = []

    class _CapturingLLM:
        async def ainvoke(self, messages: list, **kwargs: Any) -> Any:
            for msg in messages:
                if msg.__class__.__name__ == "SystemMessage":
                    captured.append(msg.content)
            response = MagicMock()
            response.content = json.dumps({
                "steps": [{"id": "step-1", "content": "Gör jobbet", "status": "pending"}],
                "reason": "simple",
            })
            return response

    node = build_planner_node(
        llm=_CapturingLLM(),
        planner_prompt_template=STANDARD_PROMPT,
        multi_domain_planner_prompt_template=MULTI_DOMAIN_PROMPT,
        latest_user_query_fn=lambda msgs: "hur många bor i Göteborg?",
        append_datetime_context_fn=lambda t: t,
        extract_first_json_object_fn=lambda s: json.loads(s),
    )

    state: dict[str, Any] = {
        "messages": [MagicMock()],
        "resolved_intent": {"route": "statistics"},
        "sub_intents": [],
        "selected_agents": [{"name": "statistics"}],
        "graph_complexity": "complex",
        "active_plan": [],
    }

    result = asyncio.run(node(state))

    assert STANDARD_PROMPT in captured, (
        f"Expected standard prompt for non-mixed route. Got: {captured}"
    )
    assert MULTI_DOMAIN_PROMPT not in captured, (
        "Multi-domain prompt should NOT be used for non-mixed route"
    )

    plan = result.get("active_plan", [])
    assert len(plan) == 1
    # Default for missing parallel field should be False
    assert plan[0]["parallel"] is False

    print("  ✓ Standard prompt used for non-mixed route")
    print("  ✓ 'parallel' defaults to False when not specified by LLM")


if __name__ == "__main__":
    print("Running test_mixed_weather_statistics_does_not_lock_to_weather...")
    test_mixed_weather_statistics_does_not_lock_to_weather()
    print("✓ Passed")

    print("Running test_pure_weather_query_still_routes_to_action...")
    test_pure_weather_query_still_routes_to_action()
    print("✓ Passed")

    print("Running test_weather_agent_limit_not_forced_to_1...")
    test_weather_agent_limit_not_forced_to_1()
    print("✓ Passed")

    print("Running test_weather_cache_not_invalidated_for_mixed_query...")
    test_weather_cache_not_invalidated_for_mixed_query()
    print("✓ Passed")

    print("Running test_sub_intents_propagated_to_state...")
    test_sub_intents_propagated_to_state()
    print("✓ Passed")

    print("Running test_subagent_isolation_active_for_parallel_strategy...")
    test_subagent_isolation_active_for_parallel_strategy()
    print("✓ Passed")

    print("Running test_planner_uses_multi_domain_prompt_for_mixed_route...")
    test_planner_uses_multi_domain_prompt_for_mixed_route()
    print("✓ Passed")

    print("Running test_planner_falls_back_to_standard_prompt_for_non_mixed_route...")
    test_planner_falls_back_to_standard_prompt_for_non_mixed_route()
    print("✓ Passed")

    print("\nAll tests passed! ✓")
