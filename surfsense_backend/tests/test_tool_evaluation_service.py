import asyncio

from app.agents.new_chat.bigtool_store import ToolIndexEntry
from app.services.tool_evaluation_service import (
    compute_metadata_version_hash,
    generate_tool_metadata_suggestions,
    run_tool_evaluation,
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
