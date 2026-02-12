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
    "rerank_candidates": 24,
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


def normalize_tool_retrieval_tuning(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload or {}
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
        "embedding_weight": _as_float(
            source.get("embedding_weight"),
            default=float(DEFAULT_TOOL_RETRIEVAL_TUNING["embedding_weight"]),
            min_value=0.0,
            max_value=25.0,
        ),
        "rerank_candidates": _as_int(
            source.get("rerank_candidates"),
            default=int(DEFAULT_TOOL_RETRIEVAL_TUNING["rerank_candidates"]),
            min_value=1,
            max_value=100,
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
