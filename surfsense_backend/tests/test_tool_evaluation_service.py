import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys
import types
from typing import Any

from pydantic import BaseModel

@dataclass(frozen=True)
class ToolIndexEntry:
    tool_id: str
    namespace: tuple[str, ...]
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str
    embedding: list[float] | None = None
    base_path: str | None = None


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_NEW_CHAT_PACKAGE = types.ModuleType("app.agents.new_chat")
_NEW_CHAT_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/agents/new_chat")]
sys.modules.setdefault("app.agents.new_chat", _NEW_CHAT_PACKAGE)

_NODES_PACKAGE = types.ModuleType("app.agents.new_chat.nodes")
_NODES_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/agents/new_chat/nodes")]
sys.modules.setdefault("app.agents.new_chat.nodes", _NODES_PACKAGE)

_FAKE_BIGTOOL_STORE = types.ModuleType("app.agents.new_chat.bigtool_store")
_FAKE_BIGTOOL_STORE.ToolIndexEntry = ToolIndexEntry


def _normalize_retrieval_tuning_stub(payload: dict[str, Any] | None = None):
    base = {
        "name_match_weight": 5.0,
        "keyword_weight": 3.0,
        "description_token_weight": 1.0,
        "example_query_weight": 2.0,
        "namespace_boost": 3.0,
        "embedding_weight": 4.0,
        "rerank_candidates": 24,
        "retrieval_feedback_db_enabled": False,
    }
    if isinstance(payload, dict):
        base.update(payload)
    return types.SimpleNamespace(**base)


_FAKE_BIGTOOL_STORE.normalize_retrieval_tuning = _normalize_retrieval_tuning_stub
_FAKE_BIGTOOL_STORE.smart_retrieve_tools_with_breakdown = (
    lambda *_args, **_kwargs: ([], [])
)
sys.modules["app.agents.new_chat.bigtool_store"] = _FAKE_BIGTOOL_STORE

_FAKE_DISPATCHER = types.ModuleType("app.agents.new_chat.dispatcher")


async def _dispatch_route_with_trace_stub(*_args, **_kwargs):
    return "action", {"route": "action", "confidence": 0.8}


_FAKE_DISPATCHER.dispatch_route_with_trace = _dispatch_route_with_trace_stub
sys.modules["app.agents.new_chat.dispatcher"] = _FAKE_DISPATCHER

_FAKE_SKOLVERKET_TOOLS = types.ModuleType("app.agents.new_chat.skolverket_tools")
_FAKE_SKOLVERKET_TOOLS.SKOLVERKET_TOOL_DEFINITIONS = []
sys.modules["app.agents.new_chat.skolverket_tools"] = _FAKE_SKOLVERKET_TOOLS

from app.services.tool_evaluation_service import (
    _apply_prompt_architecture_guard,
    _compute_agent_gate_score,
    _enrich_metadata_suggestion_fields,
    _repair_expected_routing,
    compute_metadata_version_hash,
    generate_tool_metadata_suggestions,
    run_tool_api_input_evaluation,
    run_tool_evaluation,
    suggest_agent_metadata_improvements,
    suggest_agent_prompt_improvements_for_api_input,
    suggest_retrieval_tuning,
)


def _entry(
    tool_id: str,
    *,
    name: str,
    description: str,
    category: str,
    keywords: list[str] | None = None,
) -> ToolIndexEntry:
    return ToolIndexEntry(
        tool_id=tool_id,
        namespace=("tools", category),
        name=name,
        description=description,
        keywords=keywords or [],
        example_queries=[],
        category=category,
        embedding=None,
        base_path=None,
    )


def test_compute_metadata_version_hash_changes_with_metadata():
    first_index = [
        _entry(
            "weather_lookup",
            name="Weather lookup",
            description="Fetch weather forecast",
            category="weather",
            keywords=["weather"],
        )
    ]
    second_index = [
        _entry(
            "weather_lookup",
            name="Weather lookup",
            description="Fetch weather forecast for roads",
            category="weather",
            keywords=["weather"],
        )
    ]

    first_hash = compute_metadata_version_hash(first_index)
    second_hash = compute_metadata_version_hash(second_index)

    assert first_hash != second_hash


def test_run_tool_evaluation_without_llm_uses_retrieval(monkeypatch):
    tool_index = [
        _entry(
            "tool_alpha",
            name="Alpha",
            description="Handles alpha tasks",
            category="alpha",
            keywords=["alpha"],
        ),
        _entry(
            "tool_beta",
            name="Beta",
            description="Handles beta tasks",
            category="beta",
            keywords=["beta"],
        ),
    ]

    monkeypatch.setattr(
        "app.services.tool_evaluation_service.smart_retrieve_tools_with_breakdown",
        lambda *_args, **_kwargs: (["tool_beta", "tool_alpha"], []),
    )
    async def _fake_dispatch_route(*_args, **_kwargs):
        return "action", "data", "action_task", {"confidence": 0.88}

    async def _fake_plan_agent_choice(*_args, **_kwargs):
        return {
            "selected_agent": "action",
            "analysis": "Data-fraga ska ga till action-agenten.",
        }

    monkeypatch.setattr(
        "app.services.tool_evaluation_service._dispatch_route_from_start",
        _fake_dispatch_route,
    )
    monkeypatch.setattr(
        "app.services.tool_evaluation_service._plan_agent_choice",
        _fake_plan_agent_choice,
    )

    output = asyncio.run(
        run_tool_evaluation(
            tests=[
                {
                    "id": "t1",
                    "question": "Need beta data",
                    "expected": {"tool": "tool_beta", "category": "beta"},
                    "allowed_tools": [],
                }
            ],
            tool_index=tool_index,
            llm=None,
            retrieval_limit=3,
        )
    )

    assert output["results"][0]["selected_tool"] == "tool_beta"
    assert output["results"][0]["retrieval_top_tools"][0] == "tool_beta"
    assert output["results"][0]["passed_tool"] is True


def test_generate_tool_metadata_suggestions_fallback():
    tool_index = [
        _entry(
            "trafikverket_vader_halka",
            name="Halka",
            description="Road surface and slippery condition info.",
            category="trafikverket_vader",
            keywords=["halka", "väglag"],
        ),
        _entry(
            "trafikverket_vag_status",
            name="Vägstatus",
            description="Road status and flow.",
            category="trafikverket_vag",
            keywords=["vägstatus"],
        ),
    ]

    results = [
        {
            "test_id": "case-1",
            "question": "Finns risk för is och temperaturfall i natt på E4?",
            "expected_tool": "trafikverket_vader_halka",
            "selected_tool": "trafikverket_vag_status",
            "passed_tool": False,
            "passed": False,
        }
    ]

    suggestions = asyncio.run(
        generate_tool_metadata_suggestions(
            evaluation_results=results,
            tool_index=tool_index,
            llm=None,
        )
    )

    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion["tool_id"] == "trafikverket_vader_halka"
    assert suggestion["proposed_metadata"]["tool_id"] == "trafikverket_vader_halka"
    assert suggestion["proposed_metadata"]["description"]
    assert len(suggestion["proposed_metadata"]["keywords"]) >= 2


def test_suggest_retrieval_tuning_fallback():
    suggestion = asyncio.run(
        suggest_retrieval_tuning(
            evaluation_results=[
                {
                    "test_id": "t1",
                    "question": "fraga",
                    "passed": False,
                    "passed_tool": False,
                    "retrieval_hit_expected_tool": False,
                }
            ],
            current_tuning={
                "name_match_weight": 5.0,
                "keyword_weight": 3.0,
                "description_token_weight": 1.0,
                "example_query_weight": 2.0,
                "namespace_boost": 3.0,
                "embedding_weight": 4.0,
                "rerank_candidates": 24,
                "retrieval_feedback_db_enabled": False,
            },
            llm=None,
        )
    )

    assert suggestion is not None
    assert suggestion["proposed_tuning"]["embedding_weight"] >= 4.0


def test_suggest_retrieval_tuning_when_all_passed_returns_no_change():
    suggestion = asyncio.run(
        suggest_retrieval_tuning(
            evaluation_results=[
                {
                    "test_id": "t1",
                    "question": "fraga",
                    "passed": True,
                    "passed_tool": True,
                    "retrieval_hit_expected_tool": True,
                }
            ],
            current_tuning={
                "name_match_weight": 5.0,
                "keyword_weight": 3.0,
                "description_token_weight": 1.0,
                "example_query_weight": 2.0,
                "namespace_boost": 3.0,
                "embedding_weight": 4.0,
                "rerank_candidates": 24,
                "retrieval_feedback_db_enabled": False,
            },
            llm=None,
        )
    )

    assert suggestion is not None
    assert suggestion["proposed_tuning"] == suggestion["current_tuning"]


def test_enrich_metadata_suggestion_fields_uses_fallback_for_all_core_fields():
    current = {
        "tool_id": "tool_weather",
        "name": "Weather",
        "description": "Current weather conditions.",
        "keywords": ["weather", "forecast"],
        "example_queries": ["Vad blir vädret i dag?"],
        "category": "weather",
        "base_path": None,
    }
    llm_proposed = {
        "tool_id": "tool_weather",
        "name": "Weather",
        "description": "Current weather conditions.",
        "keywords": ["weather", "forecast"],
        "example_queries": ["Vad blir vädret i dag?"],
        "category": "weather",
        "base_path": None,
    }
    fallback = {
        "tool_id": "tool_weather",
        "name": "Weather",
        "description": "Current weather conditions. Relevant for terms like: halka, snö, is.",
        "keywords": ["weather", "forecast", "halka", "snö"],
        "example_queries": [
            "Vad blir vädret i dag?",
            "Finns risk för halka i natt?",
        ],
        "category": "weather",
        "base_path": None,
    }

    merged, enriched = _enrich_metadata_suggestion_fields(
        current=current,
        proposed=llm_proposed,
        fallback=fallback,
    )

    assert enriched is True
    assert merged["description"] == fallback["description"]
    assert merged["keywords"] == fallback["keywords"]
    assert merged["example_queries"] == fallback["example_queries"]


class _FakeApiArgs(BaseModel):
    city: str
    date: str


class _FakeTool:
    args_schema = _FakeApiArgs


def test_run_tool_api_input_evaluation_detects_missing_required_fields(monkeypatch):
    tool_index = [
        _entry(
            "tool_weather",
            name="Weather Tool",
            description="Fetch weather by city/date",
            category="weather",
            keywords=["weather"],
        ),
    ]
    tool_registry = {"tool_weather": _FakeTool()}
    monkeypatch.setattr(
        "app.services.tool_evaluation_service.smart_retrieve_tools_with_breakdown",
        lambda *_args, **_kwargs: (["tool_weather"], []),
    )
    output = asyncio.run(
        run_tool_api_input_evaluation(
            tests=[
                {
                    "id": "api-1",
                    "question": "Vad blir vädret i Stockholm i morgon?",
                    "difficulty": "svår",
                    "expected": {
                        "tool": "tool_weather",
                        "category": "weather",
                        "required_fields": ["city", "date"],
                    },
                    "allowed_tools": ["tool_weather"],
                }
            ],
            tool_index=tool_index,
            tool_registry=tool_registry,
            llm=None,
            retrieval_limit=5,
        )
    )
    assert output["metrics"]["total_tests"] == 1
    assert output["results"][0]["missing_required_fields"] == ["city", "date"]
    assert output["results"][0]["difficulty"] == "svår"
    assert output["results"][0]["passed_api_input"] is False
    assert output["metrics"]["difficulty_breakdown"] == [
        {
            "difficulty": "svår",
            "total_tests": 1,
            "passed_tests": 0,
            "success_rate": 0.0,
            "gated_success_rate": 1.0 / 3.0,
        }
    ]


def test_suggest_agent_prompt_improvements_for_api_input_fallback():
    suggestions = asyncio.run(
        suggest_agent_prompt_improvements_for_api_input(
            evaluation_results=[
                {
                    "test_id": "case-1",
                    "question": "Hur många fordonspassager i Malmö i går?",
                    "expected_tool": "trafikverket_vag_status",
                    "selected_tool": "trafikverket_vag_status",
                    "selected_category": "trafikverket_vag",
                    "missing_required_fields": ["region", "date"],
                    "schema_errors": ["Missing required fields"],
                    "passed_api_input": False,
                    "passed": False,
                }
            ],
            current_prompts={
                "tool.trafikverket_vag_status.system": (
                    "Du planerar input till trafikverket_vag_status."
                ),
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "tool.trafikverket_vag_status.system"
    assert "API INPUT EVAL-FÖRBÄTTRING" in suggestions[0]["proposed_prompt"]


def test_run_tool_evaluation_includes_route_agent_and_plan_metrics(monkeypatch):
    tool_index = [
        _entry(
            "tool_weather",
            name="Weather Tool",
            description="Fetch weather by city/date",
            category="weather",
            keywords=["weather"],
        ),
    ]
    monkeypatch.setattr(
        "app.services.tool_evaluation_service.smart_retrieve_tools_with_breakdown",
        lambda *_args, **_kwargs: (["tool_weather"], []),
    )

    async def _fake_dispatch_route(*_args, **_kwargs):
        return "action", "travel", "knowledge_lookup", {"confidence": 0.9}

    async def _fake_plan_tool_choice(*_args, **_kwargs):
        return {
            "selected_tool_id": "tool_weather",
            "selected_category": "weather",
            "analysis": "Plan starts with route:action and selects tool_weather.",
            "plan_steps": ["Use tool_weather for weather lookup."],
        }

    async def _fake_plan_agent_choice(*_args, **_kwargs):
        return {
            "selected_agent": "weather",
            "analysis": "Travel/weather should go to weather agent.",
        }

    monkeypatch.setattr(
        "app.services.tool_evaluation_service._dispatch_route_from_start",
        _fake_dispatch_route,
    )
    monkeypatch.setattr(
        "app.services.tool_evaluation_service._plan_agent_choice",
        _fake_plan_agent_choice,
    )
    monkeypatch.setattr(
        "app.services.tool_evaluation_service._plan_tool_choice",
        _fake_plan_tool_choice,
    )

    output = asyncio.run(
        run_tool_evaluation(
            tests=[
                {
                    "id": "r1",
                    "question": "Vad blir vädret i Malmö i morgon?",
                    "difficulty": "medel",
                    "expected": {
                        "tool": "tool_weather",
                        "category": "weather",
                        "route": "action",
                        "sub_route": "travel",
                        "agent": "weather",
                        "plan_requirements": [
                            "route:action",
                            "agent:weather",
                            "tool:tool_weather",
                        ],
                    },
                    "allowed_tools": ["tool_weather"],
                }
            ],
            tool_index=tool_index,
            llm=None,
            retrieval_limit=5,
        )
    )

    assert output["metrics"]["route_accuracy"] == 1.0
    assert output["metrics"]["sub_route_accuracy"] == 1.0
    assert output["metrics"]["agent_accuracy"] == 1.0
    assert output["metrics"]["plan_accuracy"] == 1.0
    assert output["metrics"]["gated_success_rate"] == 1.0
    assert output["results"][0]["passed_route"] is True
    assert output["results"][0]["passed_sub_route"] is True
    assert output["results"][0]["passed_agent"] is True
    assert output["results"][0]["selected_agent"] == "weather"
    assert (
        output["results"][0]["agent_selection_analysis"]
        == "Travel/weather should go to weather agent."
    )
    assert output["results"][0]["passed_plan"] is True
    assert output["results"][0]["agent_gate_score"] == 1.0
    assert output["results"][0]["passed_with_agent_gate"] is True
    assert output["metrics"]["supervisor_review_score"] is not None
    assert output["metrics"]["supervisor_review_pass_rate"] == 1.0
    assert output["results"][0]["supervisor_review_passed"] is True
    assert output["results"][0]["supervisor_trace"]["selected"]["agent"] == "weather"
    assert output["results"][0]["difficulty"] == "medel"
    breakdown = output["metrics"]["difficulty_breakdown"]
    assert isinstance(breakdown, list)
    assert len(breakdown) == 1
    assert breakdown[0]["difficulty"] == "medel"
    assert breakdown[0]["total_tests"] == 1
    assert breakdown[0]["gated_success_rate"] == 1.0


def test_run_tool_evaluation_includes_hybrid_execution_metrics(monkeypatch):
    tool_index = [
        _entry(
            "tool_statistics",
            name="Statistics Tool",
            description="Fetch municipality statistics",
            category="statistics",
            keywords=["kommun", "statistik"],
        ),
    ]
    monkeypatch.setattr(
        "app.services.tool_evaluation_service.smart_retrieve_tools_with_breakdown",
        lambda *_args, **_kwargs: (["tool_statistics"], []),
    )

    async def _fake_dispatch_route(*_args, **_kwargs):
        return "statistics", None, "statistics_query", {"confidence": 0.94}

    async def _fake_plan_tool_choice(*_args, **_kwargs):
        return {
            "selected_tool_id": "tool_statistics",
            "selected_category": "statistics",
            "analysis": "Plan starts with route:statistics and selects tool_statistics.",
            "plan_steps": ["Sammanstall data for alla kommuner."],
        }

    async def _fake_plan_agent_choice(*_args, **_kwargs):
        return {
            "selected_agent": "statistics",
            "analysis": "Statistics route should use statistics agent.",
        }

    monkeypatch.setattr(
        "app.services.tool_evaluation_service._dispatch_route_from_start",
        _fake_dispatch_route,
    )
    monkeypatch.setattr(
        "app.services.tool_evaluation_service._plan_agent_choice",
        _fake_plan_agent_choice,
    )
    monkeypatch.setattr(
        "app.services.tool_evaluation_service._plan_tool_choice",
        _fake_plan_tool_choice,
    )

    output = asyncio.run(
        run_tool_evaluation(
            tests=[
                {
                    "id": "h1",
                    "question": "Hamta statistik for alla kommuner i Sverige.",
                    "expected": {
                        "tool": "tool_statistics",
                        "category": "statistics",
                        "route": "statistics",
                        "agent": "statistics",
                        "graph_complexity": "complex",
                        "execution_strategy": "subagent",
                    },
                    "allowed_tools": ["tool_statistics"],
                }
            ],
            tool_index=tool_index,
            llm=None,
            retrieval_limit=5,
        )
    )

    assert output["metrics"]["graph_complexity_accuracy"] == 1.0
    assert output["metrics"]["execution_strategy_accuracy"] == 1.0
    assert output["results"][0]["selected_graph_complexity"] == "complex"
    assert output["results"][0]["selected_execution_strategy"] == "subagent"
    assert output["results"][0]["passed_graph_complexity"] is True
    assert output["results"][0]["passed_execution_strategy"] is True
    assert (
        output["results"][0]["supervisor_trace"]["selected"]["execution_strategy"]
        == "subagent"
    )


def test_run_tool_api_input_evaluation_includes_hybrid_execution_metrics(monkeypatch):
    class _StatsArgs(BaseModel):
        region: str

    class _StatsTool:
        args_schema = _StatsArgs

    tool_index = [
        _entry(
            "tool_statistics",
            name="Statistics Tool",
            description="Fetch municipality statistics",
            category="statistics",
            keywords=["kommun", "statistik"],
        ),
    ]
    tool_registry = {"tool_statistics": _StatsTool()}

    monkeypatch.setattr(
        "app.services.tool_evaluation_service.smart_retrieve_tools_with_breakdown",
        lambda *_args, **_kwargs: (["tool_statistics"], []),
    )

    async def _fake_dispatch_route(*_args, **_kwargs):
        return "statistics", None, "statistics_query", {"confidence": 0.95}

    async def _fake_plan_agent_choice(*_args, **_kwargs):
        return {
            "selected_agent": "statistics",
            "analysis": "Statistics route should use statistics agent.",
        }

    async def _fake_plan_tool_api_input(*_args, **_kwargs):
        return {
            "selected_tool_id": "tool_statistics",
            "selected_category": "statistics",
            "analysis": "Plan starts with route:statistics and prepares API input.",
            "plan_steps": ["Sammanstall data for alla kommuner."],
            "proposed_arguments": {"region": "alla kommuner"},
            "needs_clarification": False,
            "clarification_question": None,
        }

    monkeypatch.setattr(
        "app.services.tool_evaluation_service._dispatch_route_from_start",
        _fake_dispatch_route,
    )
    monkeypatch.setattr(
        "app.services.tool_evaluation_service._plan_agent_choice",
        _fake_plan_agent_choice,
    )
    monkeypatch.setattr(
        "app.services.tool_evaluation_service._plan_tool_api_input",
        _fake_plan_tool_api_input,
    )

    output = asyncio.run(
        run_tool_api_input_evaluation(
            tests=[
                {
                    "id": "h-api-1",
                    "question": "Hamta statistik for alla kommuner i Sverige.",
                    "expected": {
                        "tool": "tool_statistics",
                        "category": "statistics",
                        "route": "statistics",
                        "agent": "statistics",
                        "required_fields": ["region"],
                        "graph_complexity": "complex",
                        "execution_strategy": "subagent",
                    },
                    "allowed_tools": ["tool_statistics"],
                }
            ],
            tool_index=tool_index,
            tool_registry=tool_registry,
            llm=None,
            retrieval_limit=5,
        )
    )

    assert output["metrics"]["graph_complexity_accuracy"] == 1.0
    assert output["metrics"]["execution_strategy_accuracy"] == 1.0
    assert output["results"][0]["selected_graph_complexity"] == "complex"
    assert output["results"][0]["selected_execution_strategy"] == "subagent"
    assert output["results"][0]["passed_graph_complexity"] is True
    assert output["results"][0]["passed_execution_strategy"] is True


def test_suggest_agent_prompt_improvements_includes_router_prompt():
    suggestions = asyncio.run(
        suggest_agent_prompt_improvements_for_api_input(
            evaluation_results=[
                {
                    "test_id": "case-route-1",
                    "question": "Hur många invånare har Malmö?",
                    "expected_route": "statistics",
                    "selected_route": "knowledge",
                    "passed_route": False,
                    "passed": False,
                }
            ],
            current_prompts={
                "supervisor.intent_resolver.system": "Route incoming user messages.",
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "supervisor.intent_resolver.system"
    assert "API INPUT EVAL-FÖRBÄTTRING" in suggestions[0]["proposed_prompt"]


def test_suggest_agent_prompt_improvements_includes_agent_prompt():
    suggestions = asyncio.run(
        suggest_agent_prompt_improvements_for_api_input(
            evaluation_results=[
                {
                    "test_id": "case-agent-1",
                    "question": "Vad är vädret i Malmö i helgen?",
                    "expected_agent": "trafik",
                    "selected_agent": "action",
                    "passed_agent": False,
                    "passed": False,
                }
            ],
            current_prompts={
                "supervisor.agent_resolver.system": "Du väljer agent.",
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "supervisor.agent_resolver.system"
    assert "API INPUT EVAL-FÖRBÄTTRING" in suggestions[0]["proposed_prompt"]


def test_suggest_agent_prompt_improvements_includes_supervisor_prompt_on_review_fail():
    suggestions = asyncio.run(
        suggest_agent_prompt_improvements_for_api_input(
            evaluation_results=[
                {
                    "test_id": "case-supervisor-1",
                    "question": "Hur är läget på E4 vid Gävle i kväll?",
                    "passed": True,
                    "passed_route": True,
                    "passed_sub_route": True,
                    "passed_agent": True,
                    "passed_plan": True,
                    "passed_tool": True,
                    "supervisor_review_passed": False,
                    "supervisor_review_issues": [
                        "Saknar regel för ny retrieval vid ämnesbyte"
                    ],
                }
            ],
            current_prompts={
                "supervisor.planner.system": "Du planerar nästa steg.",
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "supervisor.planner.system"
    assert "retrieve_tools" in suggestions[0]["proposed_prompt"]


def test_suggest_agent_prompt_improvements_api_tool_only_prefers_input_prompt():
    suggestions = asyncio.run(
        suggest_agent_prompt_improvements_for_api_input(
            evaluation_results=[
                {
                    "test_id": "case-api-input-1",
                    "question": "Hur många fordon passerade E4 i går?",
                    "expected_tool": "trafikverket_vag_status",
                    "selected_tool": "trafikverket_vag_status",
                    "selected_category": "trafikverket_vag",
                    "missing_required_fields": ["road", "date"],
                    "passed_api_input": False,
                    "passed": False,
                }
            ],
            current_prompts={
                "tool.trafikverket_vag_status.input": "Du extraherar API-input.",
                "tool.trafikverket_vag_status.system": "Du planerar tool-val.",
            },
            llm=None,
            suggestion_scope="api_tool_only",
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "tool.trafikverket_vag_status.input"


def test_suggest_agent_metadata_improvements_fallback():
    suggestions = asyncio.run(
        suggest_agent_metadata_improvements(
            evaluation_results=[
                {
                    "test_id": "agent-meta-1",
                    "question": "Vad blir vädret i Hjo i morgon?",
                    "expected_agent": "weather",
                    "selected_agent": "action",
                    "expected_route": "action",
                    "expected_intent": "action",
                    "passed_agent": False,
                    "passed": False,
                }
            ],
            current_prompts={
                "agent.action.system": "Du är actionagent.",
                "supervisor.agent_resolver.system": "Välj agent baserat på retrieve_agents.",
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion["agent_id"] == "weather"
    assert suggestion["prompt_key"] in {
        "agent.action.system",
        "supervisor.agent_resolver.system",
    }
    assert suggestion["proposed_metadata"]["keywords"]
    assert suggestion["proposed_metadata"]["example_questions"]


def test_prompt_architecture_guard_rejects_static_supervisor_agent_list():
    prompt = (
        "Tillgängliga agenter:\n"
        "- action: väder\n"
        "- statistics: SCB\n"
        "- knowledge: docs\n"
        "- trafik: väg\n"
    )
    guarded, violations, severe = _apply_prompt_architecture_guard(
        prompt_key="agent.supervisor.system",
        prompt_text=prompt,
    )
    assert severe is True
    assert guarded.startswith(prompt.strip())
    assert "retrieve_agents" in guarded
    assert any("statisk agentlista" in violation.casefold() for violation in violations)


def test_prompt_architecture_guard_adds_retrieval_rules_for_agent_prompt():
    guarded, violations, severe = _apply_prompt_architecture_guard(
        prompt_key="agent.trafik.system",
        prompt_text="Du är trafikagent.",
    )
    assert severe is False
    assert "retrieve_tools" in guarded
    assert any("retrieve_tools" in violation for violation in violations)


def test_compute_agent_gate_score_skips_downstream_when_upstream_fails():
    score, passed = _compute_agent_gate_score(
        upstream_checks=[False, True, True, True],
        downstream_checks=[False, False],
    )
    assert score == 0.75
    assert passed is False

    score_ok, passed_ok = _compute_agent_gate_score(
        upstream_checks=[True, True, True, True],
        downstream_checks=[True, True],
    )
    assert score_ok == 1.0
    assert passed_ok is True


def test_repair_expected_routing_fixes_mislabeled_sub_route_for_tool():
    route, sub_route = _repair_expected_routing(
        expected_route="action",
        expected_sub_route="external",
        expected_tool="trafikverket_vag_status",
        expected_category="trafikverket_vag",
    )
    assert route == "action"
    assert sub_route == "travel"


def test_repair_expected_routing_fixes_wrong_action_sub_route_for_tool():
    route, sub_route = _repair_expected_routing(
        expected_route="action",
        expected_sub_route="web",
        expected_tool="trafikverket_trafikinfo_vagarbeten",
        expected_category="trafikverket_trafikinfo",
    )
    assert route == "action"
    assert sub_route == "travel"


def test_repair_expected_routing_handles_new_smhi_prefix_tool():
    route, sub_route = _repair_expected_routing(
        expected_route="knowledge",
        expected_sub_route="internal",
        expected_tool="smhi_forecast_hourly",
        expected_category="weather",
    )
    assert route == "action"
    assert sub_route == "travel"
