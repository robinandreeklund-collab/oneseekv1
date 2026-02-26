"""Tests for Sprint P1 Extra — Structured Output (JSON Schema).

Covers:
- Pydantic schema validation
- pydantic_to_response_format helper
- IncrementalSchemaParser
- inject_core_prompt structured_output mode
- Env flag behaviour
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from app.agents.new_chat.structured_schemas import (
    AgentResolverResult,
    CriticResult,
    IntentResult,
    PlannerResult,
    PlanStep,
    ResponseLayerResult,
    ResponseLayerRouterResult,
    SynthesizerResult,
    pydantic_to_response_format,
    structured_output_enabled,
)
from app.agents.new_chat.incremental_json_parser import IncrementalSchemaParser
from app.agents.new_chat.system_prompt import (
    SURFSENSE_CORE_GLOBAL_PROMPT,
    SURFSENSE_CORE_GLOBAL_PROMPT_STRUCTURED,
    inject_core_prompt,
)


# ────────────────────────────────────────────────────────────────
# P1-Extra.1: Schema tests
# ────────────────────────────────────────────────────────────────


class TestIntentSchema:
    def test_valid_json_schema(self):
        """IntentResult.model_json_schema() produces valid JSON Schema."""
        schema = IntentResult.model_json_schema()
        assert schema["type"] == "object"
        assert "thinking" in schema["properties"]
        assert "intent_id" in schema["properties"]
        assert "route" in schema["properties"]

    def test_parse_valid(self):
        """IntentResult parses a valid LLM response."""
        data = {
            "thinking": "Jag analyserar...",
            "intent_id": "weather_forecast",
            "route": "kunskap",
            "sub_intents": [],
            "reason": "Väderfråga",
            "confidence": 0.92,
        }
        result = IntentResult.model_validate(data)
        assert result.intent_id == "weather_forecast"
        assert result.route == "kunskap"
        assert result.thinking == "Jag analyserar..."
        assert result.confidence == 0.92

    def test_parse_from_json_string(self):
        """IntentResult can be parsed from JSON string (model_validate_json)."""
        json_str = json.dumps({
            "thinking": "test",
            "intent_id": "test_id",
            "route": "konversation",
            "sub_intents": [],
            "reason": "test reason",
            "confidence": 0.5,
        })
        result = IntentResult.model_validate_json(json_str)
        assert result.intent_id == "test_id"

    def test_invalid_route_rejected(self):
        """IntentResult rejects invalid route values."""
        with pytest.raises(Exception):
            IntentResult(
                thinking="test",
                intent_id="x",
                route="invalid_route",
                reason="test",
                confidence=0.5,
            )

    def test_confidence_range(self):
        """IntentResult rejects confidence outside 0-1."""
        with pytest.raises(Exception):
            IntentResult(
                thinking="test",
                intent_id="x",
                route="kunskap",
                reason="test",
                confidence=1.5,
            )


class TestPlannerSchema:
    def test_valid_schema(self):
        schema = PlannerResult.model_json_schema()
        assert "steps" in schema["properties"]
        assert "thinking" in schema["properties"]

    def test_parse_with_steps(self):
        data = {
            "thinking": "Jag planerar...",
            "steps": [
                {"id": "step-1", "content": "Hämta väderdata"},
                {"id": "step-2", "content": "Sammanfatta"},
            ],
            "reason": "Enkel plan",
        }
        result = PlannerResult.model_validate(data)
        assert len(result.steps) == 2
        assert result.steps[0].id == "step-1"
        assert result.steps[0].status == "pending"
        assert result.steps[0].parallel is False

    def test_plan_step_defaults(self):
        step = PlanStep(id="s1", content="do something")
        assert step.status == "pending"
        assert step.parallel is False


class TestCriticSchema:
    def test_decision_enum(self):
        """CriticResult rejects invalid decision values."""
        with pytest.raises(Exception):
            CriticResult(
                thinking="test",
                decision="maybe",
                reason="test",
                confidence=0.5,
            )

    def test_valid_decisions(self):
        for decision in ["ok", "needs_more", "replan"]:
            result = CriticResult(
                thinking="test",
                decision=decision,
                reason="test",
                confidence=0.5,
            )
            assert result.decision == decision


class TestSynthesizerSchema:
    def test_response_field(self):
        result = SynthesizerResult(
            thinking="Jag sammanfogar...",
            response="Sammanfattat svar här.",
            reason="Test",
        )
        assert result.response == "Sammanfattat svar här."


class TestResponseLayerSchemas:
    def test_router_valid_layers(self):
        for layer in ["kunskap", "analys", "syntes", "visualisering"]:
            result = ResponseLayerRouterResult(
                thinking="test",
                chosen_layer=layer,
                reason="test",
            )
            assert result.chosen_layer == layer

    def test_router_invalid_layer(self):
        with pytest.raises(Exception):
            ResponseLayerRouterResult(
                thinking="test",
                chosen_layer="invalid",
                reason="test",
            )

    def test_response_layer_result(self):
        result = ResponseLayerResult(
            thinking="Jag formaterar...",
            response="# Svar\n\nHär är svaret.",
        )
        assert "Svar" in result.response


# ────────────────────────────────────────────────────────────────
# pydantic_to_response_format helper
# ────────────────────────────────────────────────────────────────


class TestResponseFormatHelper:
    def test_correct_structure(self):
        fmt = pydantic_to_response_format(IntentResult, "intent_result")
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["name"] == "intent_result"
        assert fmt["json_schema"]["strict"] is True
        assert "properties" in fmt["json_schema"]["schema"]

    def test_schema_contains_thinking(self):
        fmt = pydantic_to_response_format(CriticResult, "critic")
        props = fmt["json_schema"]["schema"]["properties"]
        assert "thinking" in props


# ────────────────────────────────────────────────────────────────
# thinking field is first in all schemas
# ────────────────────────────────────────────────────────────────


class TestThinkingFieldFirst:
    @pytest.mark.parametrize(
        "model",
        [
            IntentResult,
            AgentResolverResult,
            PlannerResult,
            CriticResult,
            SynthesizerResult,
            ResponseLayerRouterResult,
            ResponseLayerResult,
        ],
    )
    def test_thinking_is_first_field(self, model):
        """All schemas must have 'thinking' as the first field."""
        fields = list(model.model_fields.keys())
        assert fields[0] == "thinking", (
            f"{model.__name__}: first field is '{fields[0]}', expected 'thinking'"
        )


# ────────────────────────────────────────────────────────────────
# IncrementalSchemaParser
# ────────────────────────────────────────────────────────────────


class TestIncrementalSchemaParser:
    def test_thinking_extracted_progressively(self):
        """Parser extracts thinking delta across multiple feeds."""
        parser = IncrementalSchemaParser()

        d1, _ = parser.feed('{"thinking": "Jag ')
        # Partial string may omit trailing chars before closing quote
        assert "Jag" in d1

        d2, _ = parser.feed("analyserar ")
        assert "analyserar" in d2

        d3, _ = parser.feed('frågan", "intent_id": "test"}')
        assert "frågan" in d3

    def test_finalize_returns_complete_json(self):
        """finalize() returns the complete parsed JSON."""
        parser = IncrementalSchemaParser()
        parser.feed('{"thinking": "test", ')
        parser.feed('"decision": "ok", ')
        parser.feed('"reason": "bra", ')
        parser.feed('"confidence": 0.9}')

        result = parser.finalize()
        assert result["decision"] == "ok"
        assert result["confidence"] == 0.9

    def test_partial_json_no_crash(self):
        """Partial JSON doesn't crash the parser."""
        parser = IncrementalSchemaParser()
        d, partial = parser.feed('{"thinking": "hej')
        assert d == "hej"
        # Should not crash even with incomplete JSON

    def test_empty_buffer(self):
        parser = IncrementalSchemaParser()
        d, partial = parser.feed("")
        assert d == ""
        assert partial is None

    def test_response_delta_tracking(self):
        """feed_response() tracks response field deltas."""
        parser = IncrementalSchemaParser()
        parser.feed('{"thinking": "done", "response": "')

        d1, _ = parser.feed_response("Hej ")
        assert "Hej" in d1

        d2, _ = parser.feed_response("världen")
        assert "världen" in d2

    def test_feed_all_both_deltas(self):
        """feed_all() returns both thinking and response deltas."""
        parser = IncrementalSchemaParser()

        t1, r1, _ = parser.feed_all('{"thinking": "Jag ')
        assert "Jag" in t1
        assert r1 == ""

        t2, r2, _ = parser.feed_all('analyserar", "response": "Hej ')
        assert "analyserar" in t2
        assert "Hej" in r2

        t3, r3, _ = parser.feed_all('världen"}')
        # thinking is complete — no new delta
        assert t3 == ""
        assert "världen" in r3

    def test_feed_all_complete_json(self):
        """feed_all() handles a complete JSON in one chunk."""
        parser = IncrementalSchemaParser()
        t, r, partial = parser.feed_all(
            '{"thinking": "kort", "response": "svar"}'
        )
        assert t == "kort"
        assert r == "svar"
        assert partial is not None
        assert partial["thinking"] == "kort"
        assert partial["response"] == "svar"


# ────────────────────────────────────────────────────────────────
# Env flag
# ────────────────────────────────────────────────────────────────


class TestStructuredOutputEnvFlag:
    def test_default_enabled(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STRUCTURED_OUTPUT_ENABLED", None)
            assert structured_output_enabled() is True

    def test_explicit_true(self):
        with patch.dict(os.environ, {"STRUCTURED_OUTPUT_ENABLED": "true"}):
            assert structured_output_enabled() is True

    def test_explicit_false(self):
        with patch.dict(os.environ, {"STRUCTURED_OUTPUT_ENABLED": "false"}):
            assert structured_output_enabled() is False

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"STRUCTURED_OUTPUT_ENABLED": "FALSE"}):
            assert structured_output_enabled() is False


# ────────────────────────────────────────────────────────────────
# Prompt structured mode
# ────────────────────────────────────────────────────────────────


class TestPromptStructuredMode:
    def test_structured_output_uses_structured_prompt(self):
        """inject_core_prompt(structured_output=True) uses the structured prompt."""
        result = inject_core_prompt(
            SURFSENSE_CORE_GLOBAL_PROMPT,
            "target prompt",
            structured_output=True,
        )
        # Should use the structured prompt with JSON thinking instructions
        assert '"thinking"' in result
        assert "target prompt" in result
        # Should NOT contain the original <think> instruction block
        assert "MÅSTE ske inuti <think>" not in result

    def test_structured_output_false_uses_original(self):
        """inject_core_prompt(structured_output=False) uses the original prompt."""
        result = inject_core_prompt(
            SURFSENSE_CORE_GLOBAL_PROMPT,
            "target prompt",
            structured_output=False,
        )
        assert "<think>" in result

    def test_structured_prompt_constant_exists(self):
        """SURFSENSE_CORE_GLOBAL_PROMPT_STRUCTURED has the right content."""
        assert '"thinking"' in SURFSENSE_CORE_GLOBAL_PROMPT_STRUCTURED
        # Should instruct to NOT use <think> tags (mentions them in negation)
        assert "INTE" in SURFSENSE_CORE_GLOBAL_PROMPT_STRUCTURED
        # Should NOT contain the old-style positive <think> instruction
        assert "MÅSTE ske inuti <think>" not in SURFSENSE_CORE_GLOBAL_PROMPT_STRUCTURED
