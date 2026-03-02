"""Synthesis text sanitizer for compare mode.

Strips raw JSON blobs that smaller LLMs leak into visible synthesis text.
Extracted from compare_executor.py (KQ-06) to keep modules focused.
"""

from __future__ import annotations

import re

# All JSON field names that smaller LLMs tend to dump as raw JSON outside
# of the intended ```spotlight-arena-data code fence.
# KQ-01: Frontend mirrors this list in lib/compare-constants.ts — keep in sync.
_LEAKED_JSON_FIELDS = (
    "search_queries", "search_results", "winner_answer", "winner_rationale",
    "reasoning", "thinking", "arena_analysis", "consensus", "disagreements",
    "unique_contributions", "reliability_notes", "score",
)

# Regex alternation for the field names above
_FIELD_ALT = "|".join(re.escape(f) for f in _LEAKED_JSON_FIELDS)

# Pre-compiled regex patterns (avoid re-compilation on every call)
_ARENA_DATA_BLOCK_RE = re.compile(
    r"```spotlight-arena-data\s*\n[\s\S]*?```\s*\n?",
)
_JSON_FENCED_BLOCK_RE = re.compile(
    r"```json\s*\n[\s\S]*?```\s*\n?",
)

# Pattern: a JSON object (possibly multi-line) whose first key is one of
# the known leaked fields.  Handles both compact `{ "key": ... }` and
# pretty-printed multi-line variants.
_NAKED_JSON_RE = re.compile(
    r'\{\s*"(?:' + _FIELD_ALT + r')"[\s\S]*?\}(?:\s*\})*',
)

# Pattern: a trailing JSON blob at the end of the text, starting with
# any of the known field names.  Catches cases where the JSON is appended
# after the markdown body without a blank-line separator.
_TRAILING_JSON_RE = re.compile(
    r'\n?\s*\{\s*"(?:' + _FIELD_ALT + r')"[\s\S]*$',
)


def sanitize_synthesis_text(text: str) -> str:
    """Remove raw JSON blobs that leak into the visible synthesis text.

    Some smaller LLMs dump structured analysis data (search_queries,
    search_results, winner_rationale, etc.) as raw JSON in the response
    instead of properly placing it inside ```spotlight-arena-data fences.

    This function applies multiple overlapping strategies to strip leaked
    JSON robustly — even when the JSON is multi-line or malformed.
    """
    if not text:
        return text

    # 1. Remove the ```spotlight-arena-data block (frontend extracts it separately)
    cleaned = _ARENA_DATA_BLOCK_RE.sub("", text)

    # 2. Remove any ```json ... ``` fenced blocks that contain leaked fields
    cleaned = _JSON_FENCED_BLOCK_RE.sub("", cleaned)

    # 3. Strip trailing JSON blob (greedy match to end of text)
    cleaned = _TRAILING_JSON_RE.sub("", cleaned)

    # 4. Strip inline / multi-line naked JSON blobs with known field names
    cleaned = _NAKED_JSON_RE.sub("", cleaned)

    # 5. Line-by-line pass: catch any remaining JSON fragments that the
    #    regex missed (e.g. brace-only lines, partial JSON).
    lines = cleaned.split("\n")
    result_lines: list[str] = []
    brace_depth = 0
    in_json_leak = False
    for line in lines:
        stripped_line = line.strip()

        # Detect start of a naked JSON blob: line starts with { and
        # EITHER contains a known field name OR is just a lone brace
        # (multi-line JSON where fields appear on subsequent lines).
        if not in_json_leak and stripped_line.startswith("{"):
            has_field = any(
                f'"{f}"' in stripped_line for f in _LEAKED_JSON_FIELDS
            )
            is_lone_brace = stripped_line == "{"
            if has_field or is_lone_brace:
                # Peek: count braces to track depth
                brace_depth = stripped_line.count("{") - stripped_line.count("}")
                if brace_depth > 0:
                    in_json_leak = True
                # Even if braces balance on one line, skip it if it has a field
                continue

        if in_json_leak:
            brace_depth += stripped_line.count("{") - stripped_line.count("}")
            if brace_depth <= 0:
                in_json_leak = False
            continue

        result_lines.append(line)

    return "\n".join(result_lines).strip()
