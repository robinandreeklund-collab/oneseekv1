from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.new_chat.routing import Route
from app.services.reranker_service import RerankerService


def _normalize_text(value: str) -> str:
    lowered = (value or "").lower()
    cleaned = (
        lowered.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
    )
    return "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in cleaned).strip()


def _tokenize(value: str) -> list[str]:
    normalized = _normalize_text(value)
    return [token for token in normalized.split() if token]


def _safe_keywords(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = str(raw or "").strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _score_intent(
    *,
    query: str,
    query_norm: str,
    query_tokens: set[str],
    definition: dict[str, Any],
) -> dict[str, Any]:
    intent_id = str(definition.get("intent_id") or "").strip().lower()
    route = str(definition.get("route") or "").strip().lower()
    label = str(definition.get("label") or intent_id).strip()
    description = str(definition.get("description") or "").strip()
    keywords = _safe_keywords(definition.get("keywords"))
    priority = int(definition.get("priority") or 500)

    intent_norm = _normalize_text(intent_id)
    route_norm = _normalize_text(route)
    description_norm = _normalize_text(description)

    name_match_hits = 1 if intent_norm and intent_norm in query_norm else 0
    route_match_hits = 1 if route_norm and route_norm in query_norm else 0
    keyword_hits = 0
    for keyword in keywords:
        normalized_keyword = _normalize_text(keyword)
        if normalized_keyword and normalized_keyword in query_norm:
            keyword_hits += 1
    description_hits = 0
    for token in query_tokens:
        if token and token in description_norm:
            description_hits += 1

    priority_bonus = max(0.0, 3.0 - (float(priority) / 250.0))
    lexical_score = (
        (name_match_hits * 4.0)
        + (route_match_hits * 1.5)
        + (keyword_hits * 2.4)
        + (description_hits * 0.6)
        + priority_bonus
    )
    return {
        "intent_id": intent_id,
        "route": route,
        "label": label,
        "description": description,
        "keywords": keywords,
        "priority": priority,
        "name_match_hits": int(name_match_hits),
        "route_match_hits": int(route_match_hits),
        "keyword_hits": int(keyword_hits),
        "description_hits": int(description_hits),
        "priority_bonus": float(priority_bonus),
        "lexical_score": float(lexical_score),
    }


def _rerank_candidates(
    *,
    query: str,
    candidates: list[dict[str, Any]],
) -> dict[str, float]:
    if len(candidates) <= 1:
        return {}
    reranker = RerankerService.get_reranker_instance()
    if not reranker:
        return {}
    documents: list[dict[str, Any]] = []
    for item in candidates:
        intent_id = str(item.get("intent_id") or "")
        if not intent_id:
            continue
        label = str(item.get("label") or intent_id).strip()
        description = str(item.get("description") or "").strip()
        keywords = ", ".join(_safe_keywords(item.get("keywords")))
        content = (
            f"Intent: {intent_id}\n"
            f"Label: {label}\n"
            f"Description: {description}\n"
            f"Keywords: {keywords}\n"
        ).strip()
        documents.append(
            {
                "document_id": intent_id,
                "content": content,
                "score": float(item.get("lexical_score") or 0.0),
                "document": {
                    "id": intent_id,
                    "title": label or intent_id,
                    "document_type": "INTENT",
                },
            }
        )
    if not documents:
        return {}
    try:
        reranked = reranker.rerank_documents(query, documents)
    except Exception:
        return {}
    scores: dict[str, float] = {}
    for row in reranked:
        intent_id = str(row.get("document_id") or "").strip()
        if not intent_id:
            continue
        scores[intent_id] = float(row.get("score") or 0.0)
    return scores


def _clamp_confidence(value: float) -> float:
    return max(0.01, min(0.99, round(float(value), 3)))


def _compute_confidence(ordered: list[dict[str, Any]]) -> float:
    if not ordered:
        return 0.0
    top_score = float(ordered[0].get("score") or 0.0)
    second_score = float(ordered[1].get("score") or 0.0) if len(ordered) > 1 else 0.0
    if top_score <= 0.0:
        return 0.2
    margin = max(0.0, top_score - second_score)
    relative_margin = margin / max(1.0, abs(top_score))
    keyword_hits = int(ordered[0].get("keyword_hits") or 0)
    base = 0.45 + (relative_margin * 0.45) + min(0.12, keyword_hits * 0.03)
    return _clamp_confidence(base)


@dataclass(frozen=True)
class IntentRouteDecision:
    route: Route
    confidence: float
    source: str
    reason: str
    candidates: list[dict[str, Any]]


def resolve_route_from_intents(
    *,
    query: str,
    definitions: list[dict[str, Any]] | None,
) -> IntentRouteDecision | None:
    text = str(query or "").strip()
    if not text:
        return None
    candidates = [
        definition
        for definition in (definitions or [])
        if isinstance(definition, dict) and bool(definition.get("enabled", True))
    ]
    if not candidates:
        return None
    query_norm = _normalize_text(text)
    query_tokens = set(_tokenize(text))
    scored = [
        _score_intent(
            query=text,
            query_norm=query_norm,
            query_tokens=query_tokens,
            definition=definition,
        )
        for definition in candidates
    ]
    rerank_scores = _rerank_candidates(query=text, candidates=scored)
    for item in scored:
        rerank_score = rerank_scores.get(str(item.get("intent_id") or ""))
        item["rerank_score"] = rerank_score
        item["score"] = float(item.get("lexical_score") or 0.0) + (
            float(rerank_score) if rerank_score is not None else 0.0
        )
    scored.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            -int(item.get("priority") or 500),
        ),
        reverse=True,
    )
    top = scored[0] if scored else None
    if not top:
        return None
    route_value = str(top.get("route") or "").strip().lower()
    try:
        selected_route = Route(route_value)
    except Exception:
        return None
    confidence = _compute_confidence(scored)
    top_intent = str(top.get("intent_id") or selected_route.value)
    reason = f"intent_retrieval:{top_intent}"
    top_candidates: list[dict[str, Any]] = []
    for item in scored[:4]:
        top_candidates.append(
            {
                "intent_id": str(item.get("intent_id") or ""),
                "route": str(item.get("route") or ""),
                "score": round(float(item.get("score") or 0.0), 4),
                "lexical_score": round(float(item.get("lexical_score") or 0.0), 4),
                "rerank_score": (
                    round(float(item.get("rerank_score")), 4)
                    if item.get("rerank_score") is not None
                    else None
                ),
                "keyword_hits": int(item.get("keyword_hits") or 0),
            }
        )
    return IntentRouteDecision(
        route=selected_route,
        confidence=confidence,
        source="intent_retrieval",
        reason=reason,
        candidates=top_candidates,
    )
