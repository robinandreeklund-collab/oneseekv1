"""Tests for NEXUS Synth Forge — Layer 2: LLM-generated test questions."""

from __future__ import annotations

import asyncio
import json
import uuid

from app.nexus.layers.synth_forge import (
    ForgeRunResult,
    GeneratedCase,
    SynthForge,
)


def _run(coro):
    """Run async coroutine in sync test."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TOOL = {
    "tool_id": "smhi_weather",
    "name": "SMHI Väderprognos",
    "description": "Hämtar väderdata från SMHI",
    "namespace": "tools/kunskap/smhi_weather",
    "keywords": ["väder", "prognos", "temperatur"],
    "excludes": ["klimat"],
    "geographic_scope": "Sverige",
}


def _make_llm_response(cases: list[dict]) -> str:
    return json.dumps(cases, ensure_ascii=False)


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_basic_prompt(self):
        forge = SynthForge()
        prompt = forge.build_prompt(SAMPLE_TOOL)
        assert "SMHI Väderprognos" in prompt
        assert "väder" in prompt
        assert "EASY" in prompt
        assert "ADVERSARIAL" in prompt

    def test_empty_metadata(self):
        forge = SynthForge()
        prompt = forge.build_prompt({})
        assert "EASY" in prompt

    def test_custom_questions_per_difficulty(self):
        forge = SynthForge(questions_per_difficulty=8)
        prompt = forge.build_prompt(SAMPLE_TOOL)
        assert "8" in prompt


# ---------------------------------------------------------------------------
# parse_llm_response
# ---------------------------------------------------------------------------


class TestParseLLMResponse:
    def test_valid_json(self):
        forge = SynthForge()
        cases_data = [
            {
                "difficulty": "easy",
                "question": "Vad är vädret?",
                "expected_tool": "smhi_weather",
                "expected_reason": "Direkt",
            },
            {
                "difficulty": "hard",
                "question": "Jämför väder",
                "expected_tool": "smhi_weather",
                "expected_reason": "Disambiguation",
            },
        ]
        cases = forge.parse_llm_response(
            json.dumps(cases_data), "smhi_weather", "tools/kunskap/smhi_weather"
        )
        assert len(cases) == 2
        assert cases[0].difficulty == "easy"
        assert cases[0].tool_id == "smhi_weather"

    def test_markdown_code_block(self):
        forge = SynthForge()
        raw = '```json\n[{"difficulty": "easy", "question": "Test?", "expected_tool": "t1", "expected_reason": "r"}]\n```'
        cases = forge.parse_llm_response(raw, "t1", "ns")
        assert len(cases) == 1
        assert cases[0].question == "Test?"

    def test_invalid_json(self):
        forge = SynthForge()
        cases = forge.parse_llm_response("not json at all", "t1", "ns")
        assert cases == []

    def test_unknown_difficulty_filtered(self):
        forge = SynthForge()
        cases_data = [
            {"difficulty": "unknown", "question": "Q?", "expected_tool": "t1"},
            {"difficulty": "easy", "question": "Q2?", "expected_tool": "t1"},
        ]
        cases = forge.parse_llm_response(json.dumps(cases_data), "t1", "ns")
        assert len(cases) == 1
        assert cases[0].difficulty == "easy"

    def test_single_object_wrapped(self):
        forge = SynthForge()
        raw = json.dumps(
            {"difficulty": "medium", "question": "Q?", "expected_tool": "t1"}
        )
        cases = forge.parse_llm_response(raw, "t1", "ns")
        assert len(cases) == 1


# ---------------------------------------------------------------------------
# verify_roundtrip
# ---------------------------------------------------------------------------


class TestVerifyRoundtrip:
    def test_verified_when_in_top_k(self):
        forge = SynthForge(roundtrip_top_k=3)
        case = GeneratedCase(
            tool_id="t1",
            namespace="ns",
            question="Q?",
            difficulty="easy",
            expected_tool="t1",
        )
        assert forge.verify_roundtrip(case, lambda q: ["t1", "t2", "t3"])

    def test_not_verified_when_not_in_top_k(self):
        forge = SynthForge(roundtrip_top_k=2)
        case = GeneratedCase(
            tool_id="t1",
            namespace="ns",
            question="Q?",
            difficulty="easy",
            expected_tool="t1",
        )
        assert not forge.verify_roundtrip(case, lambda q: ["t2", "t3", "t1"])

    def test_no_retrieve_fn(self):
        forge = SynthForge()
        case = GeneratedCase(
            tool_id="t1",
            namespace="ns",
            question="Q?",
            difficulty="easy",
            expected_tool="t1",
        )
        assert not forge.verify_roundtrip(case, None)

    def test_adversarial_no_expected(self):
        forge = SynthForge()
        case = GeneratedCase(
            tool_id="t1",
            namespace="ns",
            question="Q?",
            difficulty="adversarial",
            expected_tool=None,
        )
        assert not forge.verify_roundtrip(case, lambda q: ["t1"])


# ---------------------------------------------------------------------------
# generate_for_tool (async)
# ---------------------------------------------------------------------------


class TestGenerateForTool:
    def test_no_llm_returns_empty(self):
        forge = SynthForge()
        cases = _run(forge.generate_for_tool(SAMPLE_TOOL, llm_call=None))
        assert cases == []

    def test_with_llm(self):
        async def mock_llm(prompt):
            return json.dumps(
                [
                    {
                        "difficulty": "easy",
                        "question": "Vad är vädret?",
                        "expected_tool": "smhi_weather",
                    },
                ]
            )

        forge = SynthForge()
        cases = _run(forge.generate_for_tool(SAMPLE_TOOL, llm_call=mock_llm))
        assert len(cases) == 1
        assert cases[0].tool_id == "smhi_weather"


# ---------------------------------------------------------------------------
# run (full pipeline)
# ---------------------------------------------------------------------------


class TestForgeRun:
    def test_run_no_llm(self):
        forge = SynthForge()
        result = _run(forge.run([SAMPLE_TOOL]))
        assert isinstance(result, ForgeRunResult)
        assert result.total_generated == 0

    def test_run_with_llm_and_roundtrip(self):
        async def mock_llm(prompt):
            return json.dumps(
                [
                    {
                        "difficulty": "easy",
                        "question": "Vad?",
                        "expected_tool": "smhi_weather",
                    },
                    {
                        "difficulty": "hard",
                        "question": "Jämför?",
                        "expected_tool": "smhi_weather",
                    },
                ]
            )

        def mock_retrieve(q):
            return ["smhi_weather", "scb_data"]

        forge = SynthForge()
        result = _run(
            forge.run(
                [SAMPLE_TOOL],
                llm_call=mock_llm,
                retrieve_fn=mock_retrieve,
            )
        )
        assert result.total_generated == 2
        assert result.total_verified == 2
        assert result.by_difficulty.get("easy") == 1
        assert result.by_difficulty.get("hard") == 1

    def test_run_with_tool_id_filter(self):
        async def mock_llm(prompt):
            return json.dumps(
                [
                    {"difficulty": "easy", "question": "Q?", "expected_tool": "other"},
                ]
            )

        forge = SynthForge()
        result = _run(
            forge.run(
                [SAMPLE_TOOL, {"tool_id": "other", "name": "Other"}],
                llm_call=mock_llm,
                tool_ids=["other"],
            )
        )
        # Only "other" should be generated for
        assert result.total_generated == 1


# ---------------------------------------------------------------------------
# ForgeRunResult / GeneratedCase dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_generated_case_defaults(self):
        case = GeneratedCase(
            tool_id="t", namespace="n", question="Q?", difficulty="easy"
        )
        assert case.roundtrip_verified is False
        assert case.quality_score is None

    def test_forge_run_result_defaults(self):
        result = ForgeRunResult(run_id=uuid.uuid4())
        assert result.total_generated == 0
        assert result.cases == []
