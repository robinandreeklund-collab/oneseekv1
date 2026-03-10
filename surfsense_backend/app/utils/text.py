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


# Swedish/English stop words that match almost anything via substring and
# add noise rather than signal when scoring table/branch names.
_STOP_TOKENS: frozenset[str] = frozenset({
    "i", "ar", "at", "av", "en", "et", "er", "de", "di",
    "hur", "ser", "vad", "och", "for", "med", "den", "det",
    "som", "att", "till", "per", "pa", "om", "ut", "in",
    "the", "is", "of", "and", "to", "a", "an",
})


def score_text(query_tokens: set[str], text: str) -> int:
    """Score how many query tokens appear in the given text.

    Supports bidirectional substring matching to handle Swedish compound
    words.  For example, query token "arbetsmarknadslaget" should match
    text containing "arbetsmarknad", and vice versa.

    Stop words (short function words) are excluded to avoid false matches.
    """
    normalized = normalize_text(text)
    if not normalized:
        return 0
    text_tokens = set(normalized.split())
    score = 0
    for token in query_tokens:
        if not token or token in _STOP_TOKENS:
            continue
        # Forward: query token appears in text (original behaviour)
        if token in normalized:
            score += 1
            continue
        # Reverse: a text token (≥4 chars) appears inside a long query
        # token.  Handles Swedish compound words where the query has
        # "arbetsmarknadslaget" but the text has "arbetsmarknad".
        if len(token) >= 6:
            for ttoken in text_tokens:
                if len(ttoken) >= 4 and ttoken not in _STOP_TOKENS and ttoken in token:
                    score += 1
                    break
    return score
