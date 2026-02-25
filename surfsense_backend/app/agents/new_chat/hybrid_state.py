from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from app.agents.new_chat.routing import ExecutionMode

# ── Backward-compat constants ────────────────────────────────────────
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

# ── General-knowledge patterns where LLM can likely answer directly ──
_GENERAL_KNOWLEDGE_RE = re.compile(
    r"\b(vad\s+(?:ar|betyder|innebar)|vem\s+(?:ar|var)|"
    r"forklara|beskriv|definiera|vad\s+heter|"
    r"hur\s+fungerar|what\s+is|who\s+is|explain|define)\b",
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


def _looks_general_knowledge(query: str) -> bool:
    """Check if the query is likely answerable by LLM alone (no tools)."""
    text = str(query or "").strip()
    if not text:
        return False
    return bool(_GENERAL_KNOWLEDGE_RE.search(text))


# ── Tool-signal keywords: queries that almost certainly need API data ──
_TOOL_SIGNAL_RE = re.compile(
    r"\b(vader|vadret|smhi|temperatur|regn|prognos|"
    r"trafik|trafiken|trafikverket|"
    r"statistik|scb|befolkning|kolada|"
    r"bolag|bolagsverket|"
    r"riksdagen|proposition|"
    r"blocket|tradera|annons|marknadsplats|"
    r"priser|kpi|inflation|"
    r"sokvag|resplan|pendeltag)\b",
    re.IGNORECASE,
)


def classify_execution_mode(
    *,
    resolved_intent: dict[str, Any] | None,
    user_query: str,
) -> str:
    """Classify the query into an ExecutionMode (Nivå 1 decision).

    This is the FIRST routing decision in the new architecture.
    Returns one of: tool_required, tool_optional, tool_forbidden, multi_source.
    """
    intent = resolved_intent if isinstance(resolved_intent, dict) else {}
    # If the intent_resolver already set execution_mode, trust it.
    llm_mode = str(intent.get("execution_mode") or "").strip().lower()
    if llm_mode in {m.value for m in ExecutionMode}:
        return llm_mode

    route = str(intent.get("route") or "").strip().lower()
    confidence = _safe_confidence(intent.get("confidence"), 0.5)
    query_text = str(user_query or "").strip()

    # 1. Trivial queries → tool_forbidden
    if looks_trivial_query(query_text):
        return ExecutionMode.TOOL_FORBIDDEN.value

    if route in {"konversation", "smalltalk"} and confidence >= 0.75:
        return ExecutionMode.TOOL_FORBIDDEN.value

    # 2. Compare / mixed → multi_source
    if route in {"jämförelse", "compare", "mixed"}:
        return ExecutionMode.MULTI_SOURCE.value

    sub_intents = intent.get("sub_intents")
    if isinstance(sub_intents, list) and len(sub_intents) > 1:
        return ExecutionMode.MULTI_SOURCE.value

    # 3. Explicit tool-signal keywords → tool_required
    if _TOOL_SIGNAL_RE.search(query_text):
        return ExecutionMode.TOOL_REQUIRED.value

    # 4. Bulk queries → tool_required
    if _BULK_QUERY_RE.search(query_text):
        return ExecutionMode.TOOL_REQUIRED.value

    # 5. High-confidence general knowledge → tool_optional
    if confidence >= 0.72 and _looks_general_knowledge(query_text):
        query_tokens = _tokenize_query(query_text)
        if len(query_tokens) <= 18 and not _TOOL_SIGNAL_RE.search(query_text):
            return ExecutionMode.TOOL_OPTIONAL.value

    # 6. Default: tool_required (better to have tools available)
    return ExecutionMode.TOOL_REQUIRED.value


def execution_mode_to_graph_complexity(execution_mode: str) -> str:
    """Map ExecutionMode to the old graph_complexity for backward compat."""
    mode = str(execution_mode or "").strip().lower()
    if mode == ExecutionMode.TOOL_FORBIDDEN.value:
        return GRAPH_COMPLEXITY_TRIVIAL
    if mode == ExecutionMode.TOOL_OPTIONAL.value:
        return GRAPH_COMPLEXITY_SIMPLE
    if mode == ExecutionMode.MULTI_SOURCE.value:
        return GRAPH_COMPLEXITY_COMPLEX
    # tool_required — most queries are single-agent; planner handles multi-step
    return GRAPH_COMPLEXITY_SIMPLE


# ── Backward-compat wrapper ──────────────────────────────────────────
def classify_graph_complexity(
    *,
    resolved_intent: dict[str, Any] | None,
    user_query: str,
) -> str:
    """Legacy wrapper: returns graph_complexity derived from execution_mode."""
    mode = classify_execution_mode(
        resolved_intent=resolved_intent,
        user_query=user_query,
    )
    return execution_mode_to_graph_complexity(mode)


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
