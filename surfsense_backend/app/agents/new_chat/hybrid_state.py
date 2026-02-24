from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

GRAPH_COMPLEXITY_TRIVIAL = "trivial"
GRAPH_COMPLEXITY_SIMPLE = "simple"
GRAPH_COMPLEXITY_COMPLEX = "complex"

_TRIVIAL_QUERY_RE = re.compile(
    r"^\s*(hej|hejsan|tja|tjena|hallo|god\s+morgon|god\s+kvall|hi|hello)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
_BULK_QUERY_RE = re.compile(
    r"\b(alla|samtliga|hela\s+listan|alla\s+kommuner|alla\s+lan|bulk)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WorkerResult:
    answer: str = ""
    structured_data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    completeness: str = "partial"
    missing_info: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    token_cost: int = 0
    duration_ms: int = 0
    strategy: str = "inline"


def _safe_confidence(value: Any, default: float = 0.5) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def _tokenize_query(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9åäö]{2,}", text.lower()) if token]


def looks_trivial_query(query: str) -> bool:
    text = str(query or "").strip()
    if not text:
        return False
    return bool(_TRIVIAL_QUERY_RE.match(text))


def classify_graph_complexity(
    *,
    resolved_intent: dict[str, Any] | None,
    user_query: str,
) -> str:
    intent = resolved_intent if isinstance(resolved_intent, dict) else {}
    route = str(intent.get("route") or "").strip().lower()
    confidence = _safe_confidence(intent.get("confidence"), 0.5)
    query_text = str(user_query or "").strip()
    query_tokens = _tokenize_query(query_text)

    if looks_trivial_query(query_text):
        return GRAPH_COMPLEXITY_TRIVIAL

    if route in {"konversation", "smalltalk"} and confidence >= 0.75:
        return GRAPH_COMPLEXITY_TRIVIAL

    if route in {"jämförelse", "compare"}:
        return GRAPH_COMPLEXITY_COMPLEX

    if _BULK_QUERY_RE.search(query_text):
        return GRAPH_COMPLEXITY_COMPLEX

    if confidence >= 0.72 and route in {"knowledge", "action", "weather", "trafik"}:
        if len(query_tokens) <= 18:
            return GRAPH_COMPLEXITY_SIMPLE

    return GRAPH_COMPLEXITY_COMPLEX


def build_trivial_response(user_query: str) -> str | None:
    query = str(user_query or "").strip()
    if not looks_trivial_query(query):
        return None
    return "Hej! Hur kan jag hjalpa dig idag?"


def build_speculative_candidates(
    *,
    resolved_intent: dict[str, Any] | None,
    user_query: str,
    route_to_tool_ids: dict[str, list[str]] | None,
    max_candidates: int = 3,
) -> list[dict[str, Any]]:
    route = str((resolved_intent or {}).get("route") or "").strip().lower()
    tool_ids = list((route_to_tool_ids or {}).get(route) or [])
    if not tool_ids:
        return []

    query_tokens = set(_tokenize_query(str(user_query or "")))
    ranked: list[tuple[str, float]] = []
    for tool_id in tool_ids:
        normalized_tool = str(tool_id or "").strip().lower()
        if not normalized_tool:
            continue
        tool_tokens = set(_tokenize_query(normalized_tool.replace("_", " ")))
        overlap = len(query_tokens.intersection(tool_tokens))
        base_probability = 0.55
        probability = min(0.95, base_probability + (0.12 * overlap))
        ranked.append((tool_id, probability))

    ranked.sort(key=lambda item: item[1], reverse=True)
    output: list[dict[str, Any]] = []
    for tool_id, probability in ranked[: max(1, int(max_candidates))]:
        output.append(
            {
                "tool_id": str(tool_id),
                "probability": round(float(probability), 2),
            }
        )
    return output
