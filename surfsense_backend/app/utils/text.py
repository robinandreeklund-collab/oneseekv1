"""Centralized text normalization and scoring utilities.

Used by SCB service, statistics agent, bigtool store, and other modules
that need consistent Swedish-aware text processing.
"""

from __future__ import annotations

import re

_DIACRITIC_MAP = str.maketrans(
    {
        "å": "a",
        "ä": "a",
        "ö": "o",
        "Å": "a",
        "Ä": "a",
        "Ö": "o",
    }
)


def normalize_text(text: str) -> str:
    """Lowercase, strip diacritics, and collapse non-alphanumeric chars."""
    lowered = (text or "").lower().translate(_DIACRITIC_MAP)
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def tokenize(text: str) -> list[str]:
    """Tokenize normalized text into non-empty tokens."""
    normalized = normalize_text(text)
    return [token for token in normalized.split() if token]


def score_text(query_tokens: set[str], text: str) -> int:
    """Score how many query tokens appear in the given text."""
    normalized = normalize_text(text)
    if not normalized:
        return 0
    score = 0
    for token in query_tokens:
        if token and token in normalized:
            score += 1
    return score
