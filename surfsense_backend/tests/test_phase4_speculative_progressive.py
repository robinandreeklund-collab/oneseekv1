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


speculative = _load_module(
    "speculative_phase4_test_module",
    "app/agents/new_chat/nodes/speculative.py",
)
progressive = _load_module(
    "progressive_synthesizer_phase4_test_module",
    "app/agents/new_chat/nodes/progressive_synthesizer.py",
)


def test_speculative_node_executes_candidates_and_counts_successes() -> None:
    async def _runner(*, tool_id: str, candidate: dict, state: dict) -> dict:
        _ = candidate, state
        return {"status": "success", "tool_id": tool_id, "response": f"ok:{tool_id}"}

    node = speculative.build_speculative_node(
        run_speculative_candidate_fn=_runner,
        max_candidates=3,
    )
    result = asyncio.run(
        node(
            {
                "speculative_candidates": [
                    {"tool_id": "smhi_weather", "probability": 0.9},
                    {"tool_id": "trafiklab_route", "probability": 0.8},
                    {"tool_id": "smhi_weather", "probability": 0.1},
                ]
            }
        )
    )
    speculative_results = result.get("speculative_results") or {}
    assert set(speculative_results.keys()) == {"smhi_weather", "trafiklab_route"}
    payload = result.get("pending_hitl_payload") or {}
    assert payload.get("speculative_executed") == 2
    assert payload.get("speculative_successes") == 2


def test_speculative_merge_forces_inline_when_all_planned_tools_are_covered() -> None:
    node = speculative.build_speculative_merge_node()
    result = asyncio.run(
        node(
            {
                "resolved_tools_by_agent": {
                    "weather": ["smhi_weather"],
                    "trafik": ["trafiklab_route"],
                },
                "speculative_results": {
                    "smhi_weather": {"status": "success"},
                    "trafiklab_route": {"status": "partial"},
                    "unused_tool": {"status": "success"},
                },
            }
        )
    )
    assert result.get("execution_strategy") == "inline"
    payload = result.get("pending_hitl_payload") or {}
    assert sorted(payload.get("speculative_reused_tools") or []) == [
        "smhi_weather",
        "trafiklab_route",
    ]
    assert payload.get("speculative_remaining_tools") == []
    assert payload.get("speculative_discarded_tools") == ["unused_tool"]


def test_progressive_synthesizer_generates_draft_for_multi_result_response() -> None:
    node = progressive.build_progressive_synthesizer_node(
        truncate_for_prompt_fn=lambda text, limit: text[:limit],
    )
    result = asyncio.run(
        node(
            {
                "final_response": "Detta ar slutsvaret.",
                "step_results": [
                    {
                        "response": "Delresultat ett",
                        "result_contract": {"confidence": 0.5},
                    },
                    {
                        "response": "Delresultat tva",
                        "result_contract": {"confidence": 0.6},
                    },
                ],
            }
        )
    )
    drafts = result.get("synthesis_drafts")
    assert isinstance(drafts, list)
    assert len(drafts) == 1
    assert "Delresultat ett" in drafts[0].get("draft", "")
    assert drafts[0].get("confidence") == 0.6


def test_progressive_synthesizer_skips_for_high_confidence_single_result() -> None:
    node = progressive.build_progressive_synthesizer_node(
        truncate_for_prompt_fn=lambda text, limit: text[:limit],
    )
    result = asyncio.run(
        node(
            {
                "final_response": "Klar.",
                "step_results": [
                    {
                        "response": "Klar.",
                        "result_contract": {"confidence": 0.95},
                    }
                ],
            }
        )
    )
    assert result.get("synthesis_drafts") == []
