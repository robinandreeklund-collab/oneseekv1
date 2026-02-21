"""Text utility functions for supervisor agent - JSON parsing, normalization, deduplication."""
from __future__ import annotations

import ast
import json
import re
from typing import Any

from app.agents.new_chat.supervisor_constants import TOOL_CONTEXT_MAX_CHARS


# Regex patterns for text processing
_HITL_APPROVE_RE = re.compile(r"\b(ja|yes|ok|okej|kor|kör|go|fortsatt|fortsätt)\b", re.IGNORECASE)
_HITL_REJECT_RE = re.compile(r"\b(nej|no|stopp|avbryt|stop|inte)\b", re.IGNORECASE)
_CRITIC_SNIPPET_RE = re.compile(
    r"\{\s*[\"']status[\"']\s*:\s*[\"'](?:ok|needs_more)[\"'][\s\S]*?[\"']reason[\"']\s*:\s*[\"'][\s\S]*?[\"']\s*\}",
    re.IGNORECASE,
)
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->", re.IGNORECASE)
_CRITIC_JSON_DECODER = json.JSONDecoder()
_LINE_BULLET_PREFIX_RE = re.compile(r"^[-*•]+\s*")
_CITATION_TOKEN_RE = re.compile(r"\[citation:[^\]]+\]", re.IGNORECASE)
_CITATION_SPACING_RE = re.compile(r"\[citation:\s*([^\]]+?)\s*\]", re.IGNORECASE)


# JSON parsing functions
def _safe_json(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return {}


def _extract_first_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    if not value:
        return {}
    direct = _safe_json(value)
    if direct:
        return direct
    start = value.find("{")
    if start < 0:
        return {}
    segment = value[start:]
    try:
        decoded, _ = _CRITIC_JSON_DECODER.raw_decode(segment)
        if isinstance(decoded, dict):
            return decoded
    except Exception:
        pass
    for end in range(start + 1, min(len(value), start + 4000)):
        if value[end : end + 1] != "}":
            continue
        candidate = value[start : end + 1]
        parsed = _safe_json(candidate)
        if parsed:
            return parsed
        try:
            literal = ast.literal_eval(candidate)
            if isinstance(literal, dict):
                return literal
        except Exception:
            continue
    return {}


# Text normalization and cleaning
def _normalize_line_for_dedupe(line: str) -> str:
    value = str(line or "").strip()
    value = _LINE_BULLET_PREFIX_RE.sub("", value)
    value = _CITATION_TOKEN_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-").lower()
    return value


def _dedupe_repeated_lines(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 4:
        return text.strip()
    seen: set[str] = set()
    deduped: list[str] = []
    duplicates = 0
    for line in lines:
        normalized = _normalize_line_for_dedupe(line)
        if normalized and len(normalized) >= 24:
            if normalized in seen:
                duplicates += 1
                continue
            seen.add(normalized)
        deduped.append(line)
    result = "\n".join(deduped).strip()
    if duplicates > 0:
        result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _normalize_citation_spacing(text: str) -> str:
    if not text:
        return text
    return _CITATION_SPACING_RE.sub(
        lambda match: f"[citation:{str(match.group(1) or '').strip()}]",
        text,
    )


def _remove_inline_critic_payloads(text: str) -> tuple[str, bool]:
    if not text:
        return text, False
    parts: list[str] = []
    idx = 0
    removed = False
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            parts.append(text[idx:])
            break
        parts.append(text[idx:start])
        segment = text[start:]
        try:
            decoded, consumed = _CRITIC_JSON_DECODER.raw_decode(segment)
        except ValueError:
            decoded = None
            consumed = 0
            for end in range(start + 1, min(len(text), start + 2400)):
                if text[end : end + 1] != "}":
                    continue
                candidate = text[start : end + 1]
                try:
                    parsed = ast.literal_eval(candidate)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    decoded = parsed
                    consumed = len(candidate)
                    break
            if decoded is None:
                parts.append(text[start : start + 1])
                idx = start + 1
                continue
        status = (
            str(decoded.get("status") or "").strip().lower()
            if isinstance(decoded, dict)
            else ""
        )
        if isinstance(decoded, dict) and status in {"ok", "needs_more"} and "reason" in decoded:
            removed = True
            idx = start + consumed
            continue
        parts.append(text[start : start + consumed])
        idx = start + consumed
    return "".join(parts), removed


def _strip_critic_json(text: str) -> str:
    if not text:
        return text
    cleaned = _CRITIC_SNIPPET_RE.sub("", text)
    cleaned, removed_inline = _remove_inline_critic_payloads(cleaned)
    if cleaned != text or removed_inline:
        cleaned = _dedupe_repeated_lines(cleaned)
    cleaned = _HTML_COMMENT_RE.sub("", cleaned)
    cleaned = _normalize_citation_spacing(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.rstrip()


def _truncate_for_prompt(text: str, max_chars: int = TOOL_CONTEXT_MAX_CHARS) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _safe_id_segment(value: Any, *, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "")).strip("-")
    return normalized or fallback


def _serialize_artifact_payload(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)
    except Exception:
        return str(payload)


# HITL (Human-in-the-loop) parsing
def _parse_hitl_confirmation(value: str) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if _HITL_REJECT_RE.search(text):
        return "reject"
    if _HITL_APPROVE_RE.search(text):
        return "approve"
    return None


def _render_hitl_message(template: str, **kwargs: Any) -> str:
    safe_kwargs = {key: str(value or "").strip() for key, value in kwargs.items()}
    try:
        rendered = str(template or "").format(**safe_kwargs)
    except Exception:
        rendered = str(template or "")
    return rendered.strip()


# Type coercion utilities
def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(0.0, min(1.0, parsed)), 2)


def _coerce_int_range(
    value: Any,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _coerce_float_range(
    value: Any,
    *,
    default: float,
    min_value: float,
    max_value: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))
