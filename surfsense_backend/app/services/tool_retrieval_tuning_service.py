from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import GlobalToolRetrievalTuning, GlobalToolRetrievalTuningHistory

DEFAULT_TOOL_RETRIEVAL_TUNING: dict[str, Any] = {
    "name_match_weight": 5.0,
    "keyword_weight": 3.0,
    "description_token_weight": 1.0,
    "example_query_weight": 2.0,
    "namespace_boost": 3.0,
    "embedding_weight": 4.0,
    "semantic_embedding_weight": 2.8,
    "structural_embedding_weight": 1.2,
    "rerank_candidates": 24,
    "retrieval_feedback_db_enabled": False,
    "live_routing_enabled": False,
    "live_routing_phase": "shadow",
    "intent_candidate_top_k": 3,
    "agent_candidate_top_k": 3,
    "tool_candidate_top_k": 5,
    "intent_lexical_weight": 1.0,
    "intent_embedding_weight": 1.0,
    "agent_auto_margin_threshold": 0.18,
    "agent_auto_score_threshold": 0.55,
    "tool_auto_margin_threshold": 0.25,
    "tool_auto_score_threshold": 0.60,
    "adaptive_threshold_delta": 0.08,
    "adaptive_min_samples": 8,
}

_LIVE_ROUTING_PHASES = {
    "shadow",
    "tool_gate",
    "agent_auto",
    "adaptive",
    "intent_finetune",
}

_TUNING_DEFAULT_KEY = "default"


def _as_float(value: Any, *, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _as_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def normalize_tool_retrieval_tuning(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload or {}
    legacy_embedding_weight = _as_float(
        source.get("embedding_weight"),
        default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["embedding_weight"]),
        min_value=0.0,
        max_value=25.0,
    )
    semantic_raw = source.get("semantic_embedding_weight")
    structural_raw = source.get("structural_embedding_weight")
    if semantic_raw is None and structural_raw is None:
        semantic_embedding_weight = legacy_embedding_weight * 0.7
        structural_embedding_weight = legacy_embedding_weight * 0.3
    else:
        semantic_embedding_weight = _as_float(
            semantic_raw,
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["semantic_embedding_weight"]),
            min_value=0.0,
            max_value=25.0,
        )
        structural_embedding_weight = _as_float(
            structural_raw,
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["structural_embedding_weight"]),
            min_value=0.0,
            max_value=25.0,
        )
        if source.get("embedding_weight") is not None:
            current_total = semantic_embedding_weight + structural_embedding_weight
            if current_total > 0:
                scale = legacy_embedding_weight / current_total
                semantic_embedding_weight *= scale
                structural_embedding_weight *= scale
            else:
                semantic_embedding_weight = legacy_embedding_weight * 0.7
                structural_embedding_weight = legacy_embedding_weight * 0.3
    combined_embedding_weight = max(
        0.0,
        min(25.0, semantic_embedding_weight + structural_embedding_weight),
    )
    phase_raw = str(source.get("live_routing_phase") or "").strip().lower()
    if phase_raw not in _LIVE_ROUTING_PHASES:
        phase_raw = str(DEFAULT_TOOL_RETRIEVAL_TUNING["live_routing_phase"])
    return {
        "name_match_weight": _as_float(
            source.get("name_match_weight"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["name_match_weight"]),
            min_value=0.0,
            max_value=25.0,
        ),
        "keyword_weight": _as_float(
            source.get("keyword_weight"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["keyword_weight"]),
            min_value=0.0,
            max_value=25.0,
        ),
        "description_token_weight": _as_float(
            source.get("description_token_weight"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["description_token_weight"]),
            min_value=0.0,
            max_value=10.0,
        ),
        "example_query_weight": _as_float(
            source.get("example_query_weight"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["example_query_weight"]),
            min_value=0.0,
            max_value=10.0,
        ),
        "namespace_boost": _as_float(
            source.get("namespace_boost"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["namespace_boost"]),
            min_value=0.0,
            max_value=10.0,
        ),
        "embedding_weight": combined_embedding_weight,
        "semantic_embedding_weight": semantic_embedding_weight,
        "structural_embedding_weight": structural_embedding_weight,
        "rerank_candidates": _as_int(
            source.get("rerank_candidates"),
            default=int(DEFAULT_TOOL_RETRIEVAL_TUNING["rerank_candidates"]),
            min_value=1,
            max_value=100,
        ),
        "retrieval_feedback_db_enabled": _as_bool(
            source.get("retrieval_feedback_db_enabled"),
            default=bool(DEFAULT_TOOL_RETRIEVAL_TUNING["retrieval_feedback_db_enabled"]),
        ),
        "live_routing_enabled": _as_bool(
            source.get("live_routing_enabled"),
            default=bool(DEFAULT_TOOL_RETRIEVAL_TUNING["live_routing_enabled"]),
        ),
        "live_routing_phase": phase_raw,
        "intent_candidate_top_k": _as_int(
            source.get("intent_candidate_top_k"),
            default=int(DEFAULT_TOOL_RETRIEVAL_TUNING["intent_candidate_top_k"]),
            min_value=2,
            max_value=8,
        ),
        "agent_candidate_top_k": _as_int(
            source.get("agent_candidate_top_k"),
            default=int(DEFAULT_TOOL_RETRIEVAL_TUNING["agent_candidate_top_k"]),
            min_value=2,
            max_value=8,
        ),
        "tool_candidate_top_k": _as_int(
            source.get("tool_candidate_top_k"),
            default=int(DEFAULT_TOOL_RETRIEVAL_TUNING["tool_candidate_top_k"]),
            min_value=2,
            max_value=10,
        ),
        "intent_lexical_weight": _as_float(
            source.get("intent_lexical_weight"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["intent_lexical_weight"]),
            min_value=0.0,
            max_value=5.0,
        ),
        "intent_embedding_weight": _as_float(
            source.get("intent_embedding_weight"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["intent_embedding_weight"]),
            min_value=0.0,
            max_value=5.0,
        ),
        "agent_auto_margin_threshold": _as_float(
            source.get("agent_auto_margin_threshold"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["agent_auto_margin_threshold"]),
            min_value=0.0,
            max_value=5.0,
        ),
        "agent_auto_score_threshold": _as_float(
            source.get("agent_auto_score_threshold"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["agent_auto_score_threshold"]),
            min_value=0.0,
            max_value=5.0,
        ),
        "tool_auto_margin_threshold": _as_float(
            source.get("tool_auto_margin_threshold"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["tool_auto_margin_threshold"]),
            min_value=0.0,
            max_value=5.0,
        ),
        "tool_auto_score_threshold": _as_float(
            source.get("tool_auto_score_threshold"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["tool_auto_score_threshold"]),
            min_value=0.0,
            max_value=5.0,
        ),
        "adaptive_threshold_delta": _as_float(
            source.get("adaptive_threshold_delta"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["adaptive_threshold_delta"]),
            min_value=0.0,
            max_value=1.0,
        ),
        "adaptive_min_samples": _as_int(
            source.get("adaptive_min_samples"),
            default=int(DEFAULT_TOOL_RETRIEVAL_TUNING["adaptive_min_samples"]),
            min_value=1,
            max_value=1000,
        ),
    }


def tool_retrieval_tuning_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return normalize_tool_retrieval_tuning(left) == normalize_tool_retrieval_tuning(right)


async def get_global_tool_retrieval_tuning(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        select(GlobalToolRetrievalTuning).filter(
            GlobalToolRetrievalTuning.config_key == _TUNING_DEFAULT_KEY
        )
    )
    row = result.scalars().first()
    if not row or not isinstance(row.tuning_payload, dict):
        return normalize_tool_retrieval_tuning(DEFAULT_TOOL_RETRIEVAL_TUNING)
    return normalize_tool_retrieval_tuning(row.tuning_payload)


async def upsert_global_tool_retrieval_tuning(
    session: AsyncSession,
    tuning_payload: dict[str, Any],
    *,
    updated_by_id=None,
) -> dict[str, Any]:
    normalized_payload = normalize_tool_retrieval_tuning(tuning_payload)
    result = await session.execute(
        select(GlobalToolRetrievalTuning).filter(
            GlobalToolRetrievalTuning.config_key == _TUNING_DEFAULT_KEY
        )
    )
    existing = result.scalars().first()
    previous_payload = (
        normalize_tool_retrieval_tuning(existing.tuning_payload)
        if existing and isinstance(existing.tuning_payload, dict)
        else normalize_tool_retrieval_tuning(DEFAULT_TOOL_RETRIEVAL_TUNING)
    )

    if existing:
        existing.tuning_payload = normalized_payload
        if updated_by_id is not None:
            existing.updated_by_id = updated_by_id
    else:
        session.add(
            GlobalToolRetrievalTuning(
                config_key=_TUNING_DEFAULT_KEY,
                tuning_payload=normalized_payload,
                updated_by_id=updated_by_id,
            )
        )

    if previous_payload != normalized_payload:
        session.add(
            GlobalToolRetrievalTuningHistory(
                config_key=_TUNING_DEFAULT_KEY,
                previous_payload=previous_payload,
                new_payload=normalized_payload,
                updated_by_id=updated_by_id,
            )
        )

    return normalized_payload
