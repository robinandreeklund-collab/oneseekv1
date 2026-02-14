import asyncio

from pydantic import BaseModel

from app.agents.new_chat.bigtool_store import ToolIndexEntry
from app.services.tool_evaluation_service import (
    _apply_prompt_architecture_guard,
    _compute_agent_gate_score,
    _enrich_metadata_suggestion_fields,
    _repair_expected_routing,
    compute_metadata_version_hash,
    generate_tool_metadata_suggestions,
    run_tool_api_input_evaluation,
    run_tool_evaluation,
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

    assert output["metrics"]["passed_tests"] == 1
    assert output["results"][0]["selected_tool"] == "tool_beta"
    assert output["results"][0]["passed"] is True


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
            "gated_success_rate": 0.0,
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
                "agent.trafik.system": "Du är trafikagenten. Håll svaren korta.",
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "agent.trafik.system"
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
        return "action", "travel"

    async def _fake_plan_tool_choice(*_args, **_kwargs):
        return {
            "selected_tool_id": "tool_weather",
            "selected_category": "weather",
            "analysis": "Plan starts with route:action and selects tool_weather.",
            "plan_steps": ["Use tool_weather for weather lookup."],
        }

    async def _fake_plan_agent_choice(*_args, **_kwargs):
        return {
            "selected_agent": "trafik",
            "analysis": "Travel/weather should go to trafik agent.",
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
                        "agent": "trafik",
                        "plan_requirements": [
                            "route:action",
                            "agent:trafik",
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
    assert output["results"][0]["selected_agent"] == "trafik"
    assert (
        output["results"][0]["agent_selection_analysis"]
        == "Travel/weather should go to trafik agent."
    )
    assert output["results"][0]["passed_plan"] is True
    assert output["results"][0]["agent_gate_score"] == 1.0
    assert output["results"][0]["passed_with_agent_gate"] is True
    assert output["metrics"]["supervisor_review_score"] is not None
    assert output["metrics"]["supervisor_review_pass_rate"] == 1.0
    assert output["results"][0]["supervisor_review_passed"] is True
    assert output["results"][0]["supervisor_trace"]["selected"]["agent"] == "trafik"
    assert output["results"][0]["difficulty"] == "medel"
    assert output["metrics"]["difficulty_breakdown"] == [
        {
            "difficulty": "medel",
            "total_tests": 1,
            "passed_tests": 1,
            "success_rate": 1.0,
            "gated_success_rate": 1.0,
        }
    ]


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
                "router.top_level": "Route incoming user messages.",
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "router.top_level"
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
                "agent.trafik.system": "Du är trafikagenten.",
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "agent.trafik.system"
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
                "agent.supervisor.system": "Du är supervisor.",
            },
            llm=None,
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0]["prompt_key"] == "agent.supervisor.system"
    assert "retrieve_agents" in suggestions[0]["proposed_prompt"]


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
    assert guarded == prompt.strip()
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
