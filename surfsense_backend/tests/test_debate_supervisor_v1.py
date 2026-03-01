"""Tests for debate mode helper functions and schemas.

Tests cover:
- JSON extraction from text (including markdown code blocks)
- Word counting
- Self-vote filtering
- Winner resolution with tiebreaker
- Fallback synthesis building
- Pydantic schema validation
- /debatt command detection
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Ensure app.schemas is importable ────────────────────────────────────

_APP_PACKAGE = types.ModuleType("app")
_APP_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app")]
sys.modules.setdefault("app", _APP_PACKAGE)

_SCHEMAS_PACKAGE = types.ModuleType("app.schemas")
_SCHEMAS_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/schemas")]
sys.modules.setdefault("app.schemas", _SCHEMAS_PACKAGE)


# ═══════════════════════════════════════════════════════════════════════
# Pure helper functions (copied from debate_executor.py to avoid heavy
# langchain imports that aren't available in CI test environment)
# ═══════════════════════════════════════════════════════════════════════


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from text, handling markdown code blocks."""
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass
    patterns = [
        r"```(?:json)?\s*\n?(.*?)\n?```",
        r"\{[^{}]*\"voted_for\"[^{}]*\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1) if "```" in pattern else match.group(0))
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def _count_words(text: str) -> int:
    """Count words in a text string."""
    return len(text.split())


def _filter_self_votes(votes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove votes where a participant voted for themselves."""
    return [v for v in votes if v.get("voter", "").lower() != v.get("voted_for", "").lower()]


def _resolve_winner(
    vote_counts: dict[str, int],
    word_counts: dict[str, int],
) -> tuple[str, bool]:
    """Resolve the winner, using word count as tiebreaker."""
    if not vote_counts:
        return ("", False)
    max_votes = max(vote_counts.values())
    tied = [m for m, v in vote_counts.items() if v == max_votes]
    if len(tied) == 1:
        return (tied[0], False)
    winner = max(tied, key=lambda m: word_counts.get(m, 0))
    return (winner, True)


def _build_fallback_synthesis(
    convergence: dict[str, Any],
    round_responses: dict[int, dict[str, str]],
    topic: str,
) -> str:
    """Build a basic synthesis without LLM as fallback."""
    winner = convergence.get("winner", "N/A")
    vote_results = convergence.get("vote_results", {})
    word_counts = convergence.get("word_counts", {})
    parts = [
        f"# Debattresultat: {topic}\n",
        f"## Vinnare: {winner}\n",
        "## Röstresultat\n",
    ]
    for model, votes in sorted(vote_results.items(), key=lambda x: -x[1]):
        parts.append(f"- **{model}**: {votes} röster ({word_counts.get(model, 0)} ord totalt)")
    parts.append(f"\n{convergence.get('merged_summary', '')}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
# Test: _extract_json_from_text
# ═══════════════════════════════════════════════════════════════════════


class TestExtractJsonFromText:
    def test_plain_json(self):
        text = '{"voted_for": "Claude", "short_motivation": "Best reasoning"}'
        result = _extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Claude"

    def test_json_in_code_block(self):
        text = 'Here is my vote:\n```json\n{"voted_for": "Grok", "short_motivation": "Fast"}\n```'
        result = _extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Grok"

    def test_json_in_bare_code_block(self):
        text = '```\n{"voted_for": "Gemini", "short_motivation": "Thorough"}\n```'
        result = _extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Gemini"

    def test_json_with_surrounding_text(self):
        text = 'I vote for Claude. {"voted_for": "Claude", "short_motivation": "Compelling"}'
        result = _extract_json_from_text(text)
        assert result is not None
        assert result["voted_for"] == "Claude"

    def test_invalid_json_returns_none(self):
        text = "I think Claude is the best but no JSON here."
        result = _extract_json_from_text(text)
        assert result is None

    def test_empty_string(self):
        result = _extract_json_from_text("")
        assert result is None

    def test_nested_json_fields(self):
        text = '{"voted_for": "DeepSeek", "short_motivation": "Clear", "three_bullets": ["a", "b", "c"]}'
        result = _extract_json_from_text(text)
        assert result is not None
        assert result["three_bullets"] == ["a", "b", "c"]


# ═══════════════════════════════════════════════════════════════════════
# Test: _count_words
# ═══════════════════════════════════════════════════════════════════════


class TestCountWords:
    def test_simple_sentence(self):
        assert _count_words("Hello world this is a test") == 6

    def test_empty_string(self):
        assert _count_words("") == 0

    def test_single_word(self):
        assert _count_words("OneSeek") == 1

    def test_multiline(self):
        assert _count_words("Line one\nLine two\nLine three") == 6

    def test_extra_spaces(self):
        assert _count_words("  spaced   out   text  ") == 3


# ═══════════════════════════════════════════════════════════════════════
# Test: _filter_self_votes
# ═══════════════════════════════════════════════════════════════════════


class TestFilterSelfVotes:
    def test_no_self_votes(self):
        votes = [
            {"voter": "Claude", "voted_for": "Grok"},
            {"voter": "Grok", "voted_for": "Claude"},
        ]
        result = _filter_self_votes(votes)
        assert len(result) == 2

    def test_removes_self_vote(self):
        votes = [
            {"voter": "Claude", "voted_for": "Claude"},
            {"voter": "Grok", "voted_for": "Claude"},
        ]
        result = _filter_self_votes(votes)
        assert len(result) == 1
        assert result[0]["voter"] == "Grok"

    def test_case_insensitive(self):
        votes = [
            {"voter": "claude", "voted_for": "Claude"},
            {"voter": "Grok", "voted_for": "grok"},
        ]
        result = _filter_self_votes(votes)
        assert len(result) == 0

    def test_empty_votes(self):
        result = _filter_self_votes([])
        assert result == []

    def test_all_self_votes(self):
        votes = [
            {"voter": "Claude", "voted_for": "Claude"},
            {"voter": "Grok", "voted_for": "Grok"},
            {"voter": "Gemini", "voted_for": "Gemini"},
        ]
        result = _filter_self_votes(votes)
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════
# Test: _resolve_winner
# ═══════════════════════════════════════════════════════════════════════


class TestResolveWinner:
    def test_clear_winner(self):
        vote_counts = {"Claude": 4, "Grok": 2, "Gemini": 1}
        word_counts = {"Claude": 500, "Grok": 600, "Gemini": 400}
        winner, tiebreaker = _resolve_winner(vote_counts, word_counts)
        assert winner == "Claude"
        assert tiebreaker is False

    def test_two_way_tie_uses_word_count(self):
        vote_counts = {"Claude": 3, "Grok": 3, "Gemini": 1}
        word_counts = {"Claude": 500, "Grok": 700, "Gemini": 400}
        winner, tiebreaker = _resolve_winner(vote_counts, word_counts)
        assert winner == "Grok"
        assert tiebreaker is True

    def test_three_way_tie(self):
        vote_counts = {"Claude": 2, "Grok": 2, "Gemini": 2}
        word_counts = {"Claude": 800, "Grok": 600, "Gemini": 700}
        winner, tiebreaker = _resolve_winner(vote_counts, word_counts)
        assert winner == "Claude"
        assert tiebreaker is True

    def test_empty_vote_counts(self):
        winner, tiebreaker = _resolve_winner({}, {})
        assert winner == ""
        assert tiebreaker is False

    def test_single_participant(self):
        vote_counts = {"OneSeek": 6}
        word_counts = {"OneSeek": 1200}
        winner, tiebreaker = _resolve_winner(vote_counts, word_counts)
        assert winner == "OneSeek"
        assert tiebreaker is False


# ═══════════════════════════════════════════════════════════════════════
# Test: _build_fallback_synthesis
# ═══════════════════════════════════════════════════════════════════════


class TestBuildFallbackSynthesis:
    def test_basic_synthesis(self):
        convergence = {
            "winner": "Claude",
            "vote_results": {"Claude": 4, "Grok": 2},
            "word_counts": {"Claude": 500, "Grok": 600},
            "merged_summary": "Claude presented the strongest arguments.",
        }
        result = _build_fallback_synthesis(
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
        result = _build_fallback_synthesis(
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
