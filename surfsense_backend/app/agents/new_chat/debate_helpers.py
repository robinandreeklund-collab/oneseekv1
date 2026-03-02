"""Pure helper functions for debate mode.

Extracted from debate_executor.py (KQ-01/KQ-04) so they can be:
- Imported by tests without heavy langchain dependencies
- Reused across debate_executor, oneseek_debate_subagent, etc.
- Tested in isolation
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from text, handling markdown code blocks.

    Uses a balanced-brace approach as final fallback to handle nested
    structures (e.g. ``three_bullets`` arrays) that simple regex misses (BUG-03).
    """
    # 1. Direct parse
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Code block extraction
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Balanced-brace extraction — finds the first complete JSON object
    start = text.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except (json.JSONDecodeError, ValueError):
                    break

    return None


def count_words(text: str) -> int:
    """Count words in a text string."""
    return len(text.split())


def filter_self_votes(votes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove votes where a participant voted for themselves."""
    return [
        v
        for v in votes
        if v.get("voter", "").lower() != v.get("voted_for", "").lower()
    ]


def resolve_winner(
    vote_counts: dict[str, int],
    word_counts: dict[str, int],
) -> tuple[str, bool]:
    """Resolve the winner, using word count as tiebreaker.

    Returns (winner_name, tiebreaker_used).
    """
    if not vote_counts:
        return ("", False)

    max_votes = max(vote_counts.values())
    tied = [m for m, v in vote_counts.items() if v == max_votes]

    if len(tied) == 1:
        return (tied[0], False)

    # Tiebreaker: highest total word count
    winner = max(tied, key=lambda m: word_counts.get(m, 0))
    return (winner, True)


def build_round_context(
    topic: str,
    all_round_responses: dict[int, dict[str, str]],
    current_round_responses: dict[str, str],
    round_num: int,
    *,
    truncate_chars: int = 1200,
) -> str:
    """Build the chained context string for a participant.

    Includes all previous rounds and the current round's responses so far.
    Uses configurable truncation (BUG-04: increased from 600 to 1200).
    """
    context_parts = [f"Debattämne: {topic}\n"]
    for prev_round in range(1, round_num):
        prev_responses = all_round_responses.get(prev_round, {})
        if prev_responses:
            context_parts.append(f"\n--- Runda {prev_round} ---")
            for name, resp in prev_responses.items():
                context_parts.append(f"[{name}]: {resp[:truncate_chars]}")
    if current_round_responses:
        context_parts.append(f"\n--- Runda {round_num} (hittills) ---")
        for name, resp in current_round_responses.items():
            context_parts.append(f"[{name}]: {resp[:truncate_chars]}")
    return "\n".join(context_parts)


def build_fallback_synthesis(
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
        parts.append(
            f"- **{model}**: {votes} röster ({word_counts.get(model, 0)} ord totalt)"
        )

    parts.append(f"\n{convergence.get('merged_summary', '')}")

    return "\n".join(parts)


def resolve_language_instructions(
    voice_settings: dict[str, Any],
    participant_display: str,
) -> str:
    """Extract per-model language/accent instructions from voice settings (KQ-03).

    Consolidates duplicated logic from debate_voice.py into a single function.
    """
    lang_instructions = voice_settings.get("language_instructions") or {}
    if isinstance(lang_instructions, str):
        return lang_instructions.strip()
    return (
        lang_instructions.get(participant_display, "").strip()
        or lang_instructions.get("__default__", "").strip()
    )
