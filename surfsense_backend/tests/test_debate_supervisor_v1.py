"""Tests for debate mode helper functions and schemas.

Tests cover:
- JSON extraction from text (including markdown code blocks, nested JSON)
- Word counting
- Self-vote filtering
- Winner resolution with tiebreaker
- Fallback synthesis building
- Round context building (NEW)
- Language instructions resolution (NEW)
- Pydantic schema validation
- /debatt command detection

KQ-01: Now imports from debate_helpers.py instead of duplicating functions.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Ensure app packages are importable ──────────────────────────────

_APP_PACKAGE = types.ModuleType("app")
_APP_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app")]
sys.modules.setdefault("app", _APP_PACKAGE)

_SCHEMAS_PACKAGE = types.ModuleType("app.schemas")
_SCHEMAS_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/schemas")]
sys.modules.setdefault("app.schemas", _SCHEMAS_PACKAGE)

_AGENTS_PACKAGE = types.ModuleType("app.agents")
_AGENTS_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/agents")]
sys.modules.setdefault("app.agents", _AGENTS_PACKAGE)

_NEW_CHAT_PACKAGE = types.ModuleType("app.agents.new_chat")
_NEW_CHAT_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/agents/new_chat")]
sys.modules.setdefault("app.agents.new_chat", _NEW_CHAT_PACKAGE)


# ═══════════════════════════════════════════════════════════════════════
# KQ-01: Import from debate_helpers (no more duplication)
# ═══════════════════════════════════════════════════════════════════════

from app.agents.new_chat.debate_helpers import (
    build_fallback_synthesis,
    build_round_context,
    count_words,
    extract_json_from_text,
    filter_self_votes,
    resolve_language_instructions,
    resolve_winner,
)

# ═══════════════════════════════════════════════════════════════════════
# Test: extract_json_from_text
# ═══════════════════════════════════════════════════════════════════════


class TestExtractJsonFromText:
    def test_plain_json(self):
        text = '{"voted_for": "Claude", "short_motivation": "Best reasoning"}'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Claude"

    def test_json_in_code_block(self):
        text = 'Here is my vote:\n```json\n{"voted_for": "Grok", "short_motivation": "Fast"}\n```'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Grok"

    def test_json_in_bare_code_block(self):
        text = '```\n{"voted_for": "Gemini", "short_motivation": "Thorough"}\n```'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Gemini"

    def test_json_with_surrounding_text(self):
        text = 'I vote for Claude. {"voted_for": "Claude", "short_motivation": "Compelling"}'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Claude"

    def test_invalid_json_returns_none(self):
        text = "I think Claude is the best but no JSON here."
        result = extract_json_from_text(text)
        assert result is None

    def test_empty_string(self):
        result = extract_json_from_text("")
        assert result is None

    def test_nested_json_fields(self):
        text = '{"voted_for": "DeepSeek", "short_motivation": "Clear", "three_bullets": ["a", "b", "c"]}'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["three_bullets"] == ["a", "b", "c"]

    # BUG-03: Test that balanced-brace extraction handles nested structures
    def test_nested_json_with_surrounding_text(self):
        text = 'Jag röstar: {"voted_for": "Claude", "short_motivation": "Bra", "three_bullets": ["punkt 1", "punkt 2", "punkt 3"]} slut'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Claude"
        assert len(result["three_bullets"]) == 3

    def test_deeply_nested_json(self):
        text = 'Result: {"voted_for": "Grok", "meta": {"source": "test"}, "three_bullets": ["a", "b", "c"]}'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Grok"
        assert result["meta"]["source"] == "test"

    def test_json_with_escaped_quotes(self):
        text = r'{"voted_for": "Claude", "short_motivation": "Said \"best\" approach"}'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Claude"


# ═══════════════════════════════════════════════════════════════════════
# Test: count_words
# ═══════════════════════════════════════════════════════════════════════


class TestCountWords:
    def test_simple_sentence(self):
        assert count_words("Hello world this is a test") == 6

    def test_empty_string(self):
        assert count_words("") == 0

    def test_single_word(self):
        assert count_words("OneSeek") == 1

    def test_multiline(self):
        assert count_words("Line one\nLine two\nLine three") == 6

    def test_extra_spaces(self):
        assert count_words("  spaced   out   text  ") == 3


# ═══════════════════════════════════════════════════════════════════════
# Test: filter_self_votes
# ═══════════════════════════════════════════════════════════════════════


class TestFilterSelfVotes:
    def test_no_self_votes(self):
        votes = [
            {"voter": "Claude", "voted_for": "Grok"},
            {"voter": "Grok", "voted_for": "Claude"},
        ]
        result = filter_self_votes(votes)
        assert len(result) == 2

    def test_removes_self_vote(self):
        votes = [
            {"voter": "Claude", "voted_for": "Claude"},
            {"voter": "Grok", "voted_for": "Claude"},
        ]
        result = filter_self_votes(votes)
        assert len(result) == 1
        assert result[0]["voter"] == "Grok"

    def test_case_insensitive(self):
        votes = [
            {"voter": "claude", "voted_for": "Claude"},
            {"voter": "Grok", "voted_for": "grok"},
        ]
        result = filter_self_votes(votes)
        assert len(result) == 0

    def test_empty_votes(self):
        result = filter_self_votes([])
        assert result == []

    def test_all_self_votes(self):
        votes = [
            {"voter": "Claude", "voted_for": "Claude"},
            {"voter": "Grok", "voted_for": "Grok"},
            {"voter": "Gemini", "voted_for": "Gemini"},
        ]
        result = filter_self_votes(votes)
        assert len(result) == 0

    # BUG-01: Test that empty voted_for passes filter (but is handled elsewhere)
    def test_empty_voted_for_not_self_vote(self):
        votes = [
            {"voter": "Claude", "voted_for": ""},
            {"voter": "Grok", "voted_for": "Claude"},
        ]
        result = filter_self_votes(votes)
        assert len(result) == 2  # Empty voted_for is NOT a self-vote


# ═══════════════════════════════════════════════════════════════════════
# Test: resolve_winner
# ═══════════════════════════════════════════════════════════════════════


class TestResolveWinner:
    def test_clear_winner(self):
        vote_counts = {"Claude": 4, "Grok": 2, "Gemini": 1}
        word_counts = {"Claude": 500, "Grok": 600, "Gemini": 400}
        winner, tiebreaker = resolve_winner(vote_counts, word_counts)
        assert winner == "Claude"
        assert tiebreaker is False

    def test_two_way_tie_uses_word_count(self):
        vote_counts = {"Claude": 3, "Grok": 3, "Gemini": 1}
        word_counts = {"Claude": 500, "Grok": 700, "Gemini": 400}
        winner, tiebreaker = resolve_winner(vote_counts, word_counts)
        assert winner == "Grok"
        assert tiebreaker is True

    def test_three_way_tie(self):
        vote_counts = {"Claude": 2, "Grok": 2, "Gemini": 2}
        word_counts = {"Claude": 800, "Grok": 600, "Gemini": 700}
        winner, tiebreaker = resolve_winner(vote_counts, word_counts)
        assert winner == "Claude"
        assert tiebreaker is True

    def test_empty_vote_counts(self):
        winner, tiebreaker = resolve_winner({}, {})
        assert winner == ""
        assert tiebreaker is False

    def test_single_participant(self):
        vote_counts = {"OneSeek": 6}
        word_counts = {"OneSeek": 1200}
        winner, tiebreaker = resolve_winner(vote_counts, word_counts)
        assert winner == "OneSeek"
        assert tiebreaker is False


# ═══════════════════════════════════════════════════════════════════════
# Test: build_round_context (NEW — was untested)
# ═══════════════════════════════════════════════════════════════════════


class TestBuildRoundContext:
    def test_basic_context(self):
        result = build_round_context(
            topic="AI",
            all_round_responses={},
            current_round_responses={},
            round_num=1,
        )
        assert "Debattämne: AI" in result

    def test_includes_previous_rounds(self):
        result = build_round_context(
            topic="AI",
            all_round_responses={1: {"Claude": "Round 1 response"}},
            current_round_responses={},
            round_num=2,
        )
        assert "Runda 1" in result
        assert "Claude" in result
        assert "Round 1 response" in result

    def test_includes_current_round(self):
        result = build_round_context(
            topic="AI",
            all_round_responses={},
            current_round_responses={"Grok": "Current response"},
            round_num=1,
        )
        assert "Runda 1 (hittills)" in result
        assert "Grok" in result

    def test_truncation_default(self):
        long_response = "x" * 2000
        result = build_round_context(
            topic="AI",
            all_round_responses={1: {"Claude": long_response}},
            current_round_responses={},
            round_num=2,
        )
        # Default truncation is 1200
        assert len(long_response[:1200]) <= len(result)
        assert "x" * 1201 not in result

    def test_custom_truncation(self):
        long_response = "x" * 500
        result = build_round_context(
            topic="AI",
            all_round_responses={1: {"Claude": long_response}},
            current_round_responses={},
            round_num=2,
            truncate_chars=100,
        )
        assert "x" * 101 not in result


# ═══════════════════════════════════════════════════════════════════════
# Test: resolve_language_instructions (NEW — KQ-03)
# ═══════════════════════════════════════════════════════════════════════


class TestResolveLanguageInstructions:
    def test_string_instructions(self):
        settings = {"language_instructions": "Speak Swedish with clear pronunciation"}
        result = resolve_language_instructions(settings, "Claude")
        assert result == "Speak Swedish with clear pronunciation"

    def test_per_model_instructions(self):
        settings = {
            "language_instructions": {
                "Claude": "Use formal Swedish",
                "Grok": "Use casual Swedish",
                "__default__": "Speak Swedish",
            }
        }
        assert resolve_language_instructions(settings, "Claude") == "Use formal Swedish"
        assert resolve_language_instructions(settings, "Grok") == "Use casual Swedish"

    def test_default_fallback(self):
        settings = {
            "language_instructions": {
                "__default__": "Speak Swedish naturally",
            }
        }
        result = resolve_language_instructions(settings, "DeepSeek")
        assert result == "Speak Swedish naturally"

    def test_empty_settings(self):
        result = resolve_language_instructions({}, "Claude")
        assert result == ""

    def test_none_instructions(self):
        settings = {"language_instructions": None}
        result = resolve_language_instructions(settings, "Claude")
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════
# Test: build_fallback_synthesis
# ═══════════════════════════════════════════════════════════════════════


class TestBuildFallbackSynthesis:
    def test_basic_synthesis(self):
        convergence = {
            "winner": "Claude",
            "vote_results": {"Claude": 4, "Grok": 2},
            "word_counts": {"Claude": 500, "Grok": 600},
            "merged_summary": "Claude presented the strongest arguments.",
        }
        result = build_fallback_synthesis(
            convergence,
            round_responses={},
            topic="AI i samhället",
        )
        assert "AI i samhället" in result
        assert "Claude" in result
        assert "4 röster" in result
        assert "2 röster" in result
        assert "Claude presented the strongest arguments." in result

    def test_empty_convergence(self):
        result = build_fallback_synthesis(
            convergence={},
            round_responses={},
            topic="Test topic",
        )
        assert "Test topic" in result
        assert "N/A" in result


# ═══════════════════════════════════════════════════════════════════════
# Test: Pydantic schemas
# ═══════════════════════════════════════════════════════════════════════


_pydantic_available = importlib.util.find_spec("pydantic") is not None


@pytest.mark.skipif(not _pydantic_available, reason="pydantic not installed")
class TestDebateSchemas:
    def test_debate_vote_valid(self):
        from app.schemas.debate import DebateVote

        vote = DebateVote(
            voter="Claude",
            voter_key="claude",
            voted_for="Grok",
            short_motivation="Clear thinking",
            three_bullets=["Point 1", "Point 2", "Point 3"],
        )
        assert vote.voter == "Claude"
        assert vote.voted_for == "Grok"
        assert len(vote.three_bullets) == 3

    def test_debate_vote_requires_three_bullets(self):
        from app.schemas.debate import DebateVote

        with pytest.raises(Exception):
            DebateVote(
                voter="Claude",
                voted_for="Grok",
                short_motivation="Too short",
                three_bullets=["Only one"],
            )

    def test_debate_participant(self):
        from app.schemas.debate import DebateParticipant

        p = DebateParticipant(
            key="claude",
            display="Claude",
            tool_name="call_claude",
        )
        assert p.is_oneseek is False
        assert p.config_id == -1

    def test_debate_result(self):
        from app.schemas.debate import DebateResult

        r = DebateResult(topic="AI ethics")
        assert r.topic == "AI ethics"
        assert r.winner == ""
        assert r.tiebreaker_used is False
        assert r.rounds == []

    def test_debate_round_result(self):
        from app.schemas.debate import DebateRoundResult

        rr = DebateRoundResult(
            round_number=1,
            round_type="introduction",
        )
        assert rr.round_number == 1
        assert rr.responses == {}

    def test_debate_sse_event(self):
        from app.schemas.debate import DebateSSEEvent

        event = DebateSSEEvent(
            event_type="debate-init",
            data={"topic": "test", "participants": ["Claude", "Grok"]},
        )
        assert event.event_type == "debate-init"
        assert event.data["topic"] == "test"


# ═══════════════════════════════════════════════════════════════════════
# Test: /debatt command detection
# ═══════════════════════════════════════════════════════════════════════


class TestDebattCommandDetection:
    """Test the /debatt command detection logic."""

    DEBATE_PREFIX = "/debatt"

    def _is_debate_request(self, query: str) -> bool:
        return query.strip().lower().startswith(self.DEBATE_PREFIX)

    def _extract_debate_query(self, query: str) -> str:
        trimmed = query.strip()
        rest = trimmed[len(self.DEBATE_PREFIX):]
        return rest.lstrip(":").strip()

    def test_basic_debate_command(self):
        assert self._is_debate_request("/debatt Ska vi ha kärnkraft?")

    def test_debate_with_colon(self):
        assert self._is_debate_request("/debatt: Är AI farligt?")

    def test_not_debate(self):
        assert not self._is_debate_request("Vad tycker du om AI?")

    def test_compare_not_debate(self):
        assert not self._is_debate_request("/compare Vilken modell är bäst?")

    def test_extract_basic(self):
        assert self._extract_debate_query("/debatt Ska vi ha kärnkraft i Sverige?") == "Ska vi ha kärnkraft i Sverige?"

    def test_extract_with_colon(self):
        assert self._extract_debate_query("/debatt: Är AI farligt?") == "Är AI farligt?"

    def test_extract_empty(self):
        assert self._extract_debate_query("/debatt") == ""

    def test_case_insensitive(self):
        assert self._is_debate_request("/DEBATT test")
        assert self._is_debate_request("/Debatt test")
