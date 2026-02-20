from __future__ import annotations

import asyncio
import hashlib
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from time import perf_counter
from typing import Any, Awaitable, Callable

from app.agents.new_chat.bigtool_store import ToolIndexEntry, normalize_retrieval_tuning
from app.services.metadata_audit_service import (
    generate_agent_metadata_suggestions_from_annotations,
    generate_intent_metadata_suggestions_from_annotations,
    run_layered_metadata_audit,
)
from app.services.tool_evaluation_service import generate_tool_metadata_suggestions

_TOKEN_RE = re.compile(r"[a-z0-9åäö]{3,}", re.IGNORECASE)
_SWEDISH_STOPWORDS = {
    "och",
    "som",
    "med",
    "det",
    "den",
    "for",
    "för",
    "att",
    "hur",
    "vad",
    "kan",
    "ska",
    "fran",
    "från",
    "till",
    "hos",
    "pa",
    "på",
    "ett",
    "en",
    "när",
    "nar",
}
_EMBED_CACHE: dict[str, list[float]] = {}
_CONTRAST_MEMORY: dict[str, dict[tuple[str, str], str]] = {
    "intent": {},
    "agent": {},
    "tool": {},
}
_CONTRAST_MEMORY_DRIFT_EPS = 0.005
_CLUSTER_BALANCE_MAX_DROP = 0.015


@dataclass(frozen=True)
class _LayerConfig:
    enabled: bool = True
    min_probes: int = 5
    tier1_margin: float = -1.5
    tier2_margin: float = 0.5
    tier3_top1_threshold: float = 0.45
    local_delta: float = 0.02
    global_similarity_threshold: float = 0.85
    epsilon_noise: float = 0.02
    alignment_drop_max: float = 0.03
    score_alignment_weight: float = 0.5
    score_separation_weight: float = 0.5
    min_metric_delta: float = 0.0
    max_items: int = 24
    llm_enabled: bool = True


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_key(value: Any) -> str:
    return _normalize_text(value).lower()


def _safe_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = _normalize_text(raw)
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_bool(value: Any, default: bool = False) -> bool:
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


def _tokenize(value: str) -> list[str]:
    return [
        token.lower()
        for token in _TOKEN_RE.findall(value or "")
        if token and token.lower() not in _SWEDISH_STOPWORDS
    ]


def _dedupe_strings(values: list[str], *, max_items: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _normalize_text(value)
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if max_items is not None and len(output) >= max_items:
            break
    return output


def _normalize_vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        return [float(item) for item in value]
    except Exception:
        return None


def _mean_vector(vectors: list[list[float] | None]) -> list[float] | None:
    usable = [vector for vector in vectors if vector]
    if not usable:
        return None
    dim = len(usable[0])
    if dim <= 0:
        return None
    for vector in usable:
        if len(vector) != dim:
            return None
    sums = [0.0] * dim
    for vector in usable:
        for index, value in enumerate(vector):
            sums[index] += float(value)
    count = float(len(usable))
    return [value / count for value in sums]


def _cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / ((left_norm**0.5) * (right_norm**0.5))


def _embed_text(text: str) -> list[float] | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    cache_key = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    if cache_key in _EMBED_CACHE:
        return _EMBED_CACHE.get(cache_key)
    try:
        from app.config import config

        vector = _normalize_vector(config.embedding_model_instance.embed(normalized))
    except Exception:
        vector = None
    if vector is not None:
        _EMBED_CACHE[cache_key] = vector
    return vector


def _intent_text(payload: dict[str, Any]) -> str:
    return " ".join(
        [
            _normalize_text(payload.get("intent_id")),
            _normalize_text(payload.get("label")),
            _normalize_text(payload.get("route")),
            _normalize_text(payload.get("description")),
            " ".join(_safe_string_list(payload.get("keywords"))),
        ]
    ).strip()


def _agent_text(payload: dict[str, Any]) -> str:
    return " ".join(
        [
            _normalize_text(payload.get("agent_id")),
            _normalize_text(payload.get("label")),
            _normalize_text(payload.get("description")),
            " ".join(_safe_string_list(payload.get("keywords"))),
            " ".join(_safe_string_list(payload.get("namespace"))),
        ]
    ).strip()


def _tool_semantic_text(payload: dict[str, Any]) -> str:
    return " ".join(
        [
            _normalize_text(payload.get("tool_id")),
            _normalize_text(payload.get("name")),
            _normalize_text(payload.get("description")),
            " ".join(_safe_string_list(payload.get("keywords"))),
            " ".join(_safe_string_list(payload.get("example_queries"))),
        ]
    ).strip()


def _serialize_tool_entry(entry: ToolIndexEntry) -> dict[str, Any]:
    return {
        "tool_id": _normalize_text(getattr(entry, "tool_id", "")),
        "name": _normalize_text(getattr(entry, "name", "")),
        "description": _normalize_text(getattr(entry, "description", "")),
        "keywords": _safe_string_list(getattr(entry, "keywords", [])),
        "example_queries": _safe_string_list(getattr(entry, "example_queries", [])),
        "category": _normalize_text(getattr(entry, "category", "")),
        "base_path": _normalize_text(getattr(entry, "base_path", "")) or None,
    }


def _layer_metric(layer: str, summary: dict[str, Any]) -> float:
    if layer == "intent":
        return float(summary.get("intent_accuracy") or 0.0)
    if layer == "agent":
        conditional = summary.get("agent_accuracy_given_intent_correct")
        if isinstance(conditional, (float, int)):
            return float(conditional)
        return float(summary.get("agent_accuracy") or 0.0)
    conditional = summary.get("tool_accuracy_given_intent_agent_correct")
    if isinstance(conditional, (float, int)):
        return float(conditional)
    return float(summary.get("tool_accuracy") or 0.0)


def _copy_tool_patch_map(
    patch_map: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    next_map: dict[str, dict[str, Any]] = {}
    for tool_id, payload in patch_map.items():
        next_map[tool_id] = {
            "tool_id": _normalize_text(payload.get("tool_id")) or _normalize_text(tool_id),
            **payload,
            "keywords": _safe_string_list(payload.get("keywords")),
            "example_queries": _safe_string_list(payload.get("example_queries")),
        }
    return next_map


def _copy_simple_patch_map(
    patch_map: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    next_map: dict[str, dict[str, Any]] = {}
    for key, payload in patch_map.items():
        next_map[key] = {
            **payload,
            "keywords": _safe_string_list(payload.get("keywords")),
        }
        if isinstance(payload.get("namespace"), list):
            next_map[key]["namespace"] = _safe_string_list(payload.get("namespace"))
    return next_map


def _layer_result_from_probe(probe: dict[str, Any], layer: str) -> dict[str, Any]:
    payload = probe.get(layer) if isinstance(probe, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _build_anchor_probe_set(probes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for probe in probes:
        if not isinstance(probe, dict):
            continue
        tool_id = _normalize_text(probe.get("target_tool_id"))
        query = _normalize_text(probe.get("query"))
        if not tool_id or not query:
            continue
        key = (tool_id.lower(), query.lower())
        if key in seen:
            continue
        seen.add(key)
        output.append({"tool_id": tool_id, "query": query, "source": "anchor"})
    return output


def _tool_metadata_payload_with_id(payload: dict[str, Any], *, tool_id: str) -> dict[str, Any]:
    return {
        "tool_id": _normalize_text(payload.get("tool_id")) or _normalize_text(tool_id),
        "name": _normalize_text(payload.get("name")),
        "description": _normalize_text(payload.get("description")),
        "keywords": _safe_string_list(payload.get("keywords")),
        "example_queries": _safe_string_list(payload.get("example_queries")),
        "category": _normalize_text(payload.get("category")),
        "base_path": (
            _normalize_text(payload.get("base_path")) or None
            if payload.get("base_path") is not None
            else None
        ),
    }


def _intent_metadata_payload_with_id(
    payload: dict[str, Any], *, intent_id: str
) -> dict[str, Any]:
    return {
        "intent_id": _normalize_text(payload.get("intent_id")) or _normalize_text(intent_id),
        "label": _normalize_text(payload.get("label")),
        "route": _normalize_text(payload.get("route")) or "knowledge",
        "description": _normalize_text(payload.get("description")),
        "keywords": _safe_string_list(payload.get("keywords")),
        "priority": int(payload.get("priority") or 500),
        "enabled": bool(payload.get("enabled", True)),
    }


def _agent_metadata_payload_with_id(
    payload: dict[str, Any], *, agent_id: str
) -> dict[str, Any]:
    return {
        "agent_id": _normalize_text(payload.get("agent_id")) or _normalize_text(agent_id),
        "label": _normalize_text(payload.get("label")),
        "description": _normalize_text(payload.get("description")),
        "keywords": _safe_string_list(payload.get("keywords")),
        "prompt_key": _normalize_text(payload.get("prompt_key")) or None,
        "namespace": _safe_string_list(payload.get("namespace")),
    }


def _normalize_layer_config(raw: dict[str, Any] | None) -> _LayerConfig:
    payload = dict(raw or {})
    try:
        min_probes = max(1, min(int(payload.get("min_probes", 5)), 1000))
    except Exception:
        min_probes = 5
    try:
        max_items = max(1, min(int(payload.get("max_items", 24)), 200))
    except Exception:
        max_items = 24
    return _LayerConfig(
        enabled=bool(payload.get("enabled", True)),
        min_probes=min_probes,
        tier1_margin=float(payload.get("tier1_margin", -1.5)),
        tier2_margin=float(payload.get("tier2_margin", 0.5)),
        tier3_top1_threshold=float(payload.get("tier3_top1_threshold", 0.45)),
        local_delta=max(0.0, float(payload.get("local_delta", 0.02))),
        global_similarity_threshold=float(payload.get("global_similarity_threshold", 0.85)),
        epsilon_noise=max(0.0, float(payload.get("epsilon_noise", 0.02))),
        alignment_drop_max=max(0.0, float(payload.get("alignment_drop_max", 0.03))),
        score_alignment_weight=max(0.0, float(payload.get("score_alignment_weight", 0.5))),
        score_separation_weight=max(0.0, float(payload.get("score_separation_weight", 0.5))),
        min_metric_delta=float(payload.get("min_metric_delta", 0.0)),
        max_items=max_items,
        llm_enabled=bool(payload.get("llm_enabled", True)),
    )


def _tier_for_stats(
    *,
    top1_rate: float,
    avg_margin: float | None,
    cfg: _LayerConfig,
) -> str:
    if avg_margin is not None and avg_margin <= cfg.tier1_margin:
        return "tier1_critical"
    if top1_rate < 0.35:
        return "tier1_critical"
    if avg_margin is not None and avg_margin < cfg.tier2_margin:
        return "tier2_unstable"
    if top1_rate < cfg.tier3_top1_threshold:
        return "tier3_watch"
    return "stable"


def _severity_score(top1_rate: float, avg_margin: float | None) -> float:
    margin_component = 0.0
    if avg_margin is not None:
        margin_component = max(0.0, -avg_margin)
    return (1.0 - max(0.0, min(1.0, top1_rate))) * 10.0 + margin_component


def _aggregate_layer_stats(
    *,
    probes: list[dict[str, Any]],
    layer: str,
    cfg: _LayerConfig,
) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for probe in probes:
        if not isinstance(probe, dict):
            continue
        layer_payload = _layer_result_from_probe(probe, layer)
        expected = _normalized_key(layer_payload.get("expected_label"))
        predicted = _normalized_key(layer_payload.get("predicted_label"))
        query = _normalize_text(probe.get("query"))
        if not expected:
            continue
        bucket = stats.setdefault(
            expected,
            {
                "probes": 0,
                "top1_hits": 0,
                "margin_sum": 0.0,
                "margin_count": 0,
                "rank_sum": 0.0,
                "rank_count": 0,
                "queries": [],
                "failed_queries": [],
                "competitors": defaultdict(int),
            },
        )
        bucket["probes"] += 1
        if query:
            bucket["queries"].append(query)
        if expected == predicted:
            bucket["top1_hits"] += 1
        else:
            if query:
                bucket["failed_queries"].append(query)
            if predicted:
                bucket["competitors"][predicted] += 1
        margin = layer_payload.get("expected_margin_vs_best_other")
        if isinstance(margin, (float, int)):
            bucket["margin_sum"] += float(margin)
            bucket["margin_count"] += 1
        expected_rank = layer_payload.get("expected_rank")
        if isinstance(expected_rank, int) and expected_rank > 0:
            bucket["rank_sum"] += float(expected_rank)
            bucket["rank_count"] += 1
    normalized: dict[str, dict[str, Any]] = {}
    for item_id, bucket in stats.items():
        probes_count = int(bucket.get("probes") or 0)
        if probes_count < cfg.min_probes:
            continue
        top1_hits = int(bucket.get("top1_hits") or 0)
        top1_rate = (top1_hits / probes_count) if probes_count else 0.0
        avg_margin = (
            float(bucket.get("margin_sum") or 0.0) / int(bucket.get("margin_count") or 0)
            if int(bucket.get("margin_count") or 0) > 0
            else None
        )
        avg_rank = (
            float(bucket.get("rank_sum") or 0.0) / int(bucket.get("rank_count") or 0)
            if int(bucket.get("rank_count") or 0) > 0
            else None
        )
        competitors = dict(bucket.get("competitors") or {})
        primary_competitor = None
        if competitors:
            primary_competitor = sorted(
                competitors.items(),
                key=lambda item: item[1],
                reverse=True,
            )[0][0]
        tier = _tier_for_stats(top1_rate=top1_rate, avg_margin=avg_margin, cfg=cfg)
        normalized[item_id] = {
            "item_id": item_id,
            "probes": probes_count,
            "top1_rate": top1_rate,
            "avg_margin": avg_margin,
            "avg_rank": avg_rank,
            "queries": _dedupe_strings(list(bucket.get("queries") or []), max_items=120),
            "failed_queries": _dedupe_strings(
                list(bucket.get("failed_queries") or []), max_items=120
            ),
            "competitors": competitors,
            "primary_competitor": primary_competitor,
            "tier": tier,
            "severity": _severity_score(top1_rate, avg_margin),
        }
    return normalized


def _conflict_components(
    *,
    layer_stats: dict[str, dict[str, Any]],
) -> list[list[str]]:
    unstable_ids = {
        item_id
        for item_id, stats in layer_stats.items()
        if str(stats.get("tier")) != "stable"
    }
    if not unstable_ids:
        return []
    adjacency: dict[str, set[str]] = {item_id: set() for item_id in unstable_ids}
    for item_id, stats in layer_stats.items():
        if item_id not in unstable_ids:
            continue
        for competitor_id, count in dict(stats.get("competitors") or {}).items():
            if count <= 0 or competitor_id not in unstable_ids:
                continue
            adjacency[item_id].add(competitor_id)
            adjacency[competitor_id].add(item_id)
    visited: set[str] = set()
    components: list[list[str]] = []
    for item_id in unstable_ids:
        if item_id in visited:
            continue
        stack = [item_id]
        component: list[str] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    stack.append(neighbor)
        components.append(component)
    components.sort(
        key=lambda ids: (
            -len(ids),
            -sum(float(layer_stats.get(item_id, {}).get("severity") or 0.0) for item_id in ids),
        )
    )
    return components


def _pair_key(left: str, right: str) -> tuple[str, str]:
    a = _normalized_key(left)
    b = _normalized_key(right)
    if a <= b:
        return a, b
    return b, a


def _contrast_memory_text(
    *,
    layer: str,
    item_id: str,
    competitor_id: str,
    current: dict[str, Any],
    competitor: dict[str, Any] | None,
) -> str:
    item_terms = _safe_string_list(current.get("keywords"))[:4]
    competitor_terms = _safe_string_list((competitor or {}).get("keywords"))[:4]
    item_hint = ", ".join(item_terms) if item_terms else _normalize_text(current.get("description"))[:70]
    competitor_hint = (
        ", ".join(competitor_terms)
        if competitor_terms
        else _normalize_text((competitor or {}).get("description"))[:70]
    )
    return (
        f"{item_id} != {competitor_id} because {item_id} fokuserar på [{item_hint}] "
        f"medan {competitor_id} fokuserar på [{competitor_hint}]."
    )


def _contrast_hints_for_item(layer: str, item_id: str, *, limit: int = 3) -> list[str]:
    item_key = _normalized_key(item_id)
    hints: list[str] = []
    for (left, right), text in _CONTRAST_MEMORY.get(layer, {}).items():
        if item_key not in {left, right}:
            continue
        normalized = _normalize_text(text)
        if not normalized:
            continue
        hints.append(normalized)
        if len(hints) >= limit:
            break
    return hints


def _contrast_memory_rivals(layer: str, item_id: str) -> set[str]:
    item_key = _normalized_key(item_id)
    rivals: set[str] = set()
    for left, right in _CONTRAST_MEMORY.get(layer, {}).keys():
        if item_key == left and right:
            rivals.add(right)
        elif item_key == right and left:
            rivals.add(left)
    return rivals


def _rule_patch_candidate(
    *,
    layer: str,
    item_id: str,
    current: dict[str, Any],
    competitor_id: str | None,
    competitor_payload: dict[str, Any] | None,
    failed_queries: list[str],
    contrast_hints: list[str],
) -> dict[str, Any]:
    candidate = deepcopy(current)
    keywords = _safe_string_list(candidate.get("keywords"))
    existing_keyword_keys = {value.lower() for value in keywords}
    competitor_keywords = {
        value.lower() for value in _safe_string_list((competitor_payload or {}).get("keywords"))
    }
    token_counts: dict[str, int] = {}
    for query in failed_queries[:30]:
        for token in _tokenize(query):
            token_counts[token] = token_counts.get(token, 0) + 1
    top_tokens = [
        token
        for token, _count in sorted(
            token_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        if token not in competitor_keywords and token not in existing_keyword_keys
    ]
    for token in top_tokens[:2]:
        keywords.append(token)
        existing_keyword_keys.add(token)
    if len(keywords) > 6:
        removable_idx = None
        for index, keyword in enumerate(keywords):
            if keyword.lower() in competitor_keywords:
                removable_idx = index
                break
        if removable_idx is not None:
            keywords.pop(removable_idx)
    candidate["keywords"] = _dedupe_strings(keywords, max_items=25)

    description = _normalize_text(candidate.get("description"))
    if competitor_id:
        marker = f"Inte primärt för {competitor_id}."
        if marker.lower() not in description.lower():
            description = f"{description} {marker}".strip()
    for hint in contrast_hints[:2]:
        if hint.lower() not in description.lower():
            description = f"{description} {hint}".strip()
            break
    candidate["description"] = description

    if layer == "tool":
        examples = _safe_string_list(candidate.get("example_queries"))
        existing_example_keys = {value.lower() for value in examples}
        for query in failed_queries[:8]:
            normalized = _normalize_text(query)
            if not normalized or normalized.lower() in existing_example_keys:
                continue
            examples.append(normalized)
            existing_example_keys.add(normalized.lower())
            if len(examples) >= 12:
                break
        candidate["example_queries"] = examples
    return candidate


def _merge_candidates(
    *,
    layer: str,
    current: dict[str, Any],
    rule_candidate: dict[str, Any],
    llm_candidate: dict[str, Any],
) -> dict[str, Any]:
    merged = deepcopy(current)
    merged.update(llm_candidate)
    merged["description"] = _normalize_text(llm_candidate.get("description")) or _normalize_text(
        rule_candidate.get("description")
    )
    merged["keywords"] = _dedupe_strings(
        [
            *_safe_string_list(llm_candidate.get("keywords")),
            *_safe_string_list(rule_candidate.get("keywords")),
        ],
        max_items=25,
    )
    if layer == "tool":
        merged["example_queries"] = _dedupe_strings(
            [
                *_safe_string_list(llm_candidate.get("example_queries")),
                *_safe_string_list(rule_candidate.get("example_queries")),
            ],
            max_items=12,
        )
    return merged


def _metadata_equal(layer: str, left: dict[str, Any], right: dict[str, Any]) -> bool:
    if layer == "tool":
        return (
            _normalize_text(left.get("name")) == _normalize_text(right.get("name"))
            and _normalize_text(left.get("description"))
            == _normalize_text(right.get("description"))
            and _safe_string_list(left.get("keywords"))
            == _safe_string_list(right.get("keywords"))
            and _safe_string_list(left.get("example_queries"))
            == _safe_string_list(right.get("example_queries"))
            and _normalize_text(left.get("category")) == _normalize_text(right.get("category"))
        )
    if layer == "intent":
        return (
            _normalize_text(left.get("label")) == _normalize_text(right.get("label"))
            and _normalize_text(left.get("route")) == _normalize_text(right.get("route"))
            and _normalize_text(left.get("description"))
            == _normalize_text(right.get("description"))
            and _safe_string_list(left.get("keywords"))
            == _safe_string_list(right.get("keywords"))
            and int(left.get("priority") or 500) == int(right.get("priority") or 500)
            and bool(left.get("enabled", True)) == bool(right.get("enabled", True))
        )
    return (
        _normalize_text(left.get("label")) == _normalize_text(right.get("label"))
        and _normalize_text(left.get("description"))
        == _normalize_text(right.get("description"))
        and _safe_string_list(left.get("keywords"))
        == _safe_string_list(right.get("keywords"))
        and _safe_string_list(left.get("namespace"))
        == _safe_string_list(right.get("namespace"))
    )


def _intent_scope_ids(item_payload: dict[str, Any], intent_map: dict[str, dict[str, Any]]) -> list[str]:
    route = _normalized_key(item_payload.get("route"))
    same_route_ids = [
        intent_id
        for intent_id, payload in intent_map.items()
        if _normalized_key(payload.get("route")) == route
    ]
    if len(same_route_ids) >= 3:
        return same_route_ids
    return list(intent_map.keys())


def _tool_scope_ids(
    item_payload: dict[str, Any],
    tool_map: dict[str, dict[str, Any]],
) -> list[str]:
    category = _normalized_key(item_payload.get("category"))
    same_category = [
        tool_id
        for tool_id, payload in tool_map.items()
        if _normalized_key(payload.get("category")) == category
    ]
    if len(same_category) >= 3:
        return same_category
    return list(tool_map.keys())


def _fused_tool_similarity(
    *,
    left_sem: list[float] | None,
    left_struct: list[float] | None,
    right_sem: list[float] | None,
    right_struct: list[float] | None,
    semantic_weight: float,
    structural_weight: float,
) -> float:
    sem = _cosine_similarity(left_sem, right_sem)
    struct = _cosine_similarity(left_struct, right_struct)
    sem_w = max(0.0, semantic_weight)
    struct_w = max(0.0, structural_weight)
    total = sem_w + struct_w
    if total <= 0.0:
        return sem
    return ((sem * sem_w) + (struct * struct_w)) / total


def _similarity_matrix(
    *,
    layer: str,
    labels: list[str],
    intent_map: dict[str, dict[str, Any]],
    agent_map: dict[str, dict[str, Any]],
    tool_map: dict[str, dict[str, Any]],
    tool_struct_map: dict[str, list[float] | None],
    semantic_weight: float,
    structural_weight: float,
) -> list[list[float]]:
    matrix: list[list[float]] = []
    for left_id in labels:
        row: list[float] = []
        for right_id in labels:
            if layer == "intent":
                left_vec = _embed_text(_intent_text(intent_map.get(left_id, {})))
                right_vec = _embed_text(_intent_text(intent_map.get(right_id, {})))
                row.append(round(_cosine_similarity(left_vec, right_vec), 4))
            elif layer == "agent":
                left_vec = _embed_text(_agent_text(agent_map.get(left_id, {})))
                right_vec = _embed_text(_agent_text(agent_map.get(right_id, {})))
                row.append(round(_cosine_similarity(left_vec, right_vec), 4))
            else:
                left_sem = _embed_text(_tool_semantic_text(tool_map.get(left_id, {})))
                right_sem = _embed_text(_tool_semantic_text(tool_map.get(right_id, {})))
                left_struct = tool_struct_map.get(left_id)
                right_struct = tool_struct_map.get(right_id)
                row.append(
                    round(
                        _fused_tool_similarity(
                            left_sem=left_sem,
                            left_struct=left_struct,
                            right_sem=right_sem,
                            right_struct=right_struct,
                            semantic_weight=semantic_weight,
                            structural_weight=structural_weight,
                        ),
                        4,
                    )
                )
        matrix.append(row)
    return matrix


def _build_stage_matrices(
    *,
    layer: str,
    processed_item_ids: list[str],
    intent_map: dict[str, dict[str, Any]],
    agent_map: dict[str, dict[str, Any]],
    tool_map: dict[str, dict[str, Any]],
    tool_struct_map: dict[str, list[float] | None],
    semantic_weight: float,
    structural_weight: float,
) -> list[dict[str, Any]]:
    if not processed_item_ids:
        return []
    ids = _dedupe_strings(processed_item_ids, max_items=18)
    if layer != "tool":
        return [
            {
                "scope_id": "global",
                "labels": ids,
                "values": _similarity_matrix(
                    layer=layer,
                    labels=ids,
                    intent_map=intent_map,
                    agent_map=agent_map,
                    tool_map=tool_map,
                    tool_struct_map=tool_struct_map,
                    semantic_weight=semantic_weight,
                    structural_weight=structural_weight,
                ),
            }
        ]
    by_category: dict[str, list[str]] = defaultdict(list)
    for tool_id in ids:
        category = _normalized_key(tool_map.get(tool_id, {}).get("category")) or "okand"
        by_category[category].append(tool_id)
    matrices: list[dict[str, Any]] = []
    for category, labels in sorted(by_category.items(), key=lambda item: item[0]):
        matrices.append(
            {
                "scope_id": category,
                "labels": labels,
                "values": _similarity_matrix(
                    layer=layer,
                    labels=labels,
                    intent_map=intent_map,
                    agent_map=agent_map,
                    tool_map=tool_map,
                    tool_struct_map=tool_struct_map,
                    semantic_weight=semantic_weight,
                    structural_weight=structural_weight,
                ),
            }
        )
    return matrices


def _extract_tool_struct_map(
    tool_index: list[ToolIndexEntry],
) -> dict[str, list[float] | None]:
    return {
        _normalized_key(entry.tool_id): _normalize_vector(entry.structural_embedding)
        for entry in tool_index
    }


def _cluster_balance_score(
    *,
    layer: str,
    components: list[list[str]],
    intent_map: dict[str, dict[str, Any]],
    agent_map: dict[str, dict[str, Any]],
    tool_map: dict[str, dict[str, Any]],
    tool_struct_map: dict[str, list[float] | None],
    semantic_weight: float,
    structural_weight: float,
) -> float | None:
    if len(components) < 2:
        return None
    centroids: list[tuple[list[float] | None, list[float] | None]] = []
    for component in components:
        labels = [item_id for item_id in component if _normalized_key(item_id)]
        if not labels:
            continue
        if layer == "intent":
            semantic_centroid = _mean_vector(
                [_embed_text(_intent_text(intent_map.get(item_id, {}))) for item_id in labels]
            )
            centroids.append((semantic_centroid, None))
            continue
        if layer == "agent":
            semantic_centroid = _mean_vector(
                [_embed_text(_agent_text(agent_map.get(item_id, {}))) for item_id in labels]
            )
            centroids.append((semantic_centroid, None))
            continue
        semantic_centroid = _mean_vector(
            [_embed_text(_tool_semantic_text(tool_map.get(item_id, {}))) for item_id in labels]
        )
        structural_centroid = _mean_vector([tool_struct_map.get(item_id) for item_id in labels])
        centroids.append((semantic_centroid, structural_centroid))
    if len(centroids) < 2:
        return None
    distances: list[float] = []
    for left_index in range(len(centroids)):
        for right_index in range(left_index + 1, len(centroids)):
            left_sem, left_struct = centroids[left_index]
            right_sem, right_struct = centroids[right_index]
            if layer == "tool":
                similarity = _fused_tool_similarity(
                    left_sem=left_sem,
                    left_struct=left_struct,
                    right_sem=right_sem,
                    right_struct=right_struct,
                    semantic_weight=semantic_weight,
                    structural_weight=structural_weight,
                )
            else:
                similarity = _cosine_similarity(left_sem, right_sem)
            distances.append(1.0 - similarity)
    if not distances:
        return None
    return float(sum(distances) / len(distances))


def _compute_alignment_semantic(
    *,
    queries: list[str],
    embedding: list[float] | None,
) -> float:
    if not embedding:
        return 0.0
    scores: list[float] = []
    for query in queries[:32]:
        query_embedding = _embed_text(query)
        if not query_embedding:
            continue
        scores.append(_cosine_similarity(query_embedding, embedding))
    if not scores:
        return 0.0
    return float(sum(scores) / len(scores))


def _pick_primary_competitor_from_similarity(
    *,
    layer: str,
    item_id: str,
    scope_ids: list[str],
    intent_map: dict[str, dict[str, Any]],
    agent_map: dict[str, dict[str, Any]],
    tool_map: dict[str, dict[str, Any]],
    tool_struct_map: dict[str, list[float] | None],
    semantic_weight: float,
    structural_weight: float,
) -> str | None:
    candidates = [value for value in scope_ids if value != item_id]
    if not candidates:
        return None
    if layer == "intent":
        item_vec = _embed_text(_intent_text(intent_map.get(item_id, {})))
        best_score = -2.0
        best_id: str | None = None
        for candidate_id in candidates:
            candidate_vec = _embed_text(_intent_text(intent_map.get(candidate_id, {})))
            score = _cosine_similarity(item_vec, candidate_vec)
            if score > best_score:
                best_score = score
                best_id = candidate_id
        return best_id
    if layer == "agent":
        item_vec = _embed_text(_agent_text(agent_map.get(item_id, {})))
        best_score = -2.0
        best_id: str | None = None
        for candidate_id in candidates:
            candidate_vec = _embed_text(_agent_text(agent_map.get(candidate_id, {})))
            score = _cosine_similarity(item_vec, candidate_vec)
            if score > best_score:
                best_score = score
                best_id = candidate_id
        return best_id
    item_sem = _embed_text(_tool_semantic_text(tool_map.get(item_id, {})))
    item_struct = tool_struct_map.get(item_id)
    best_score = -2.0
    best_id = None
    for candidate_id in candidates:
        candidate_sem = _embed_text(_tool_semantic_text(tool_map.get(candidate_id, {})))
        candidate_struct = tool_struct_map.get(candidate_id)
        score = _fused_tool_similarity(
            left_sem=item_sem,
            left_struct=item_struct,
            right_sem=candidate_sem,
            right_struct=candidate_struct,
            semantic_weight=semantic_weight,
            structural_weight=structural_weight,
        )
        if score > best_score:
            best_score = score
            best_id = candidate_id
    return best_id


def _evaluate_candidate(
    *,
    layer: str,
    candidate: dict[str, Any],
    current: dict[str, Any],
    item_id: str,
    primary_competitor: str | None,
    scope_ids: list[str],
    query_alignment_source: list[str],
    cfg: _LayerConfig,
    intent_map: dict[str, dict[str, Any]],
    agent_map: dict[str, dict[str, Any]],
    tool_map: dict[str, dict[str, Any]],
    tool_struct_map: dict[str, list[float] | None],
    semantic_weight: float,
    structural_weight: float,
) -> dict[str, Any]:
    if layer == "intent":
        old_vec = _embed_text(_intent_text(current))
        new_vec = _embed_text(_intent_text(candidate))
        item_embedding_old = old_vec
        item_embedding_new = new_vec
    elif layer == "agent":
        old_vec = _embed_text(_agent_text(current))
        new_vec = _embed_text(_agent_text(candidate))
        item_embedding_old = old_vec
        item_embedding_new = new_vec
    else:
        old_sem = _embed_text(_tool_semantic_text(current))
        new_sem = _embed_text(_tool_semantic_text(candidate))
        old_struct = tool_struct_map.get(item_id)
        new_struct = old_struct
        item_embedding_old = old_sem
        item_embedding_new = new_sem

    other_ids = [value for value in scope_ids if value != item_id]
    nearest_old = -1.0
    nearest_new = -1.0
    similarity_to_primary_old: float | None = None
    similarity_to_primary_new: float | None = None
    similarity_old_by_other: dict[str, float] = {}
    similarity_new_by_other: dict[str, float] = {}

    for other_id in other_ids:
        if layer == "intent":
            other_vec = _embed_text(_intent_text(intent_map.get(other_id, {})))
            sim_old = _cosine_similarity(item_embedding_old, other_vec)
            sim_new = _cosine_similarity(item_embedding_new, other_vec)
        elif layer == "agent":
            other_vec = _embed_text(_agent_text(agent_map.get(other_id, {})))
            sim_old = _cosine_similarity(item_embedding_old, other_vec)
            sim_new = _cosine_similarity(item_embedding_new, other_vec)
        else:
            other_sem = _embed_text(_tool_semantic_text(tool_map.get(other_id, {})))
            other_struct = tool_struct_map.get(other_id)
            sim_old = _fused_tool_similarity(
                left_sem=item_embedding_old,
                left_struct=old_struct,
                right_sem=other_sem,
                right_struct=other_struct,
                semantic_weight=semantic_weight,
                structural_weight=structural_weight,
            )
            sim_new = _fused_tool_similarity(
                left_sem=item_embedding_new,
                left_struct=new_struct,
                right_sem=other_sem,
                right_struct=other_struct,
                semantic_weight=semantic_weight,
                structural_weight=structural_weight,
            )
        nearest_old = max(nearest_old, sim_old)
        nearest_new = max(nearest_new, sim_new)
        similarity_old_by_other[other_id] = float(sim_old)
        similarity_new_by_other[other_id] = float(sim_new)
        if other_id == primary_competitor:
            similarity_to_primary_old = sim_old
            similarity_to_primary_new = sim_new

    if nearest_old < -0.5:
        nearest_old = 0.0
    if nearest_new < -0.5:
        nearest_new = 0.0

    alignment_old = _compute_alignment_semantic(
        queries=query_alignment_source,
        embedding=item_embedding_old,
    )
    alignment_new = _compute_alignment_semantic(
        queries=query_alignment_source,
        embedding=item_embedding_new,
    )

    local_pass = True
    if primary_competitor and similarity_to_primary_old is not None and similarity_to_primary_new is not None:
        local_pass = similarity_to_primary_new <= (similarity_to_primary_old - cfg.local_delta)

    global_limit = min(
        nearest_old + cfg.epsilon_noise,
        cfg.global_similarity_threshold,
    )
    contrast_violations: list[str] = []
    for rival in sorted(_contrast_memory_rivals(layer, item_id)):
        if rival not in similarity_old_by_other or rival not in similarity_new_by_other:
            continue
        if similarity_new_by_other[rival] > (similarity_old_by_other[rival] + _CONTRAST_MEMORY_DRIFT_EPS):
            contrast_violations.append(
                f"{rival}: {similarity_old_by_other[rival]:.4f}->{similarity_new_by_other[rival]:.4f}"
            )
    contrast_pass = len(contrast_violations) == 0
    global_pass = (
        nearest_new <= global_limit
        and alignment_new >= (
        alignment_old - cfg.alignment_drop_max
        )
        and contrast_pass
    )

    alignment_weight = max(0.0, cfg.score_alignment_weight)
    separation_weight = max(0.0, cfg.score_separation_weight)
    if alignment_weight + separation_weight <= 0:
        alignment_weight = 0.5
        separation_weight = 0.5

    score = (
        (alignment_new * alignment_weight)
        + ((1.0 - nearest_new) * separation_weight)
    )
    margin_new = alignment_new - nearest_new
    margin_old = alignment_old - nearest_old
    return {
        "local_pass": bool(local_pass),
        "global_pass": bool(global_pass),
        "score": float(score),
        "margin_new": float(margin_new),
        "margin_old": float(margin_old),
        "alignment_old": float(alignment_old),
        "alignment_new": float(alignment_new),
        "nearest_old": float(nearest_old),
        "nearest_new": float(nearest_new),
        "similarity_to_primary_old": similarity_to_primary_old,
        "similarity_to_primary_new": similarity_to_primary_new,
        "contrast_pass": contrast_pass,
        "contrast_violations": contrast_violations,
    }


async def _build_llm_candidate_maps(
    *,
    layer: str,
    target_ids: list[str],
    probes: list[dict[str, Any]],
    llm: Any,
    llm_parallelism: int,
    intent_map: dict[str, dict[str, Any]],
    agent_map: dict[str, dict[str, Any]],
    tool_index: list[ToolIndexEntry],
    retrieval_tuning: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if llm is None or not target_ids:
        return {}
    target_set = {_normalized_key(item_id) for item_id in target_ids if _normalized_key(item_id)}
    if not target_set:
        return {}
    max_suggestions = max(1, min(len(target_set) * 2, 60))
    if layer == "intent":
        failures: list[dict[str, Any]] = []
        for probe in probes:
            payload = _layer_result_from_probe(probe, "intent")
            expected = _normalized_key(payload.get("expected_label"))
            predicted = _normalized_key(payload.get("predicted_label"))
            if not expected or expected not in target_set:
                continue
            if expected == predicted:
                continue
            failures.append(
                {
                    "probe_id": _normalize_text(probe.get("probe_id")),
                    "query": _normalize_text(probe.get("query")),
                    "expected_intent_id": expected,
                    "predicted_intent_id": predicted,
                    "score_breakdown": list(payload.get("score_breakdown") or []),
                }
            )
        suggestions = await generate_intent_metadata_suggestions_from_annotations(
            intent_definitions=list(intent_map.values()),
            intent_failures=failures,
            llm=llm,
            max_suggestions=max_suggestions,
            parallelism=max(1, min(int(llm_parallelism or 1), 32)),
        )
        return {
            _normalized_key(item.get("intent_id")): dict(item.get("proposed_metadata") or {})
            for item in suggestions
            if _normalized_key(item.get("intent_id"))
        }
    if layer == "agent":
        failures = []
        for probe in probes:
            payload = _layer_result_from_probe(probe, "agent")
            expected = _normalized_key(payload.get("expected_label"))
            predicted = _normalized_key(payload.get("predicted_label"))
            if not expected or expected not in target_set:
                continue
            if expected == predicted:
                continue
            failures.append(
                {
                    "probe_id": _normalize_text(probe.get("probe_id")),
                    "query": _normalize_text(probe.get("query")),
                    "expected_agent_id": expected,
                    "predicted_agent_id": predicted,
                    "score_breakdown": list(payload.get("score_breakdown") or []),
                }
            )
        suggestions = await generate_agent_metadata_suggestions_from_annotations(
            agent_metadata=list(agent_map.values()),
            agent_failures=failures,
            llm=llm,
            max_suggestions=max_suggestions,
            parallelism=max(1, min(int(llm_parallelism or 1), 32)),
        )
        return {
            _normalized_key(item.get("agent_id")): dict(item.get("proposed_metadata") or {})
            for item in suggestions
            if _normalized_key(item.get("agent_id"))
        }
    evaluation_results: list[dict[str, Any]] = []
    for probe in probes:
        payload = _layer_result_from_probe(probe, "tool")
        expected = _normalized_key(payload.get("expected_label"))
        predicted = _normalized_key(payload.get("predicted_label"))
        if not expected or expected not in target_set:
            continue
        if expected == predicted:
            continue
        evaluation_results.append(
            {
                "test_id": _normalize_text(probe.get("probe_id")),
                "question": _normalize_text(probe.get("query")),
                "expected_tool": expected,
                "selected_tool": predicted or None,
                "passed_tool": False,
                "passed": False,
                "retrieval_breakdown": list(payload.get("score_breakdown") or []),
                "tool_vector_diagnostics": dict(
                    probe.get("tool_vector_diagnostics") or {}
                ),
            }
        )
    suggestions = await generate_tool_metadata_suggestions(
        evaluation_results=evaluation_results,
        tool_index=tool_index,
        llm=llm,
        retrieval_tuning=retrieval_tuning,
        retrieval_context={
            "audit_mode": "metadata_catalog",
            "pipeline": "bottom_up_separation",
        },
        max_suggestions=max_suggestions,
        parallelism=max(1, min(int(llm_parallelism or 1), 32)),
    )
    return {
        _normalized_key(item.get("tool_id")): dict(item.get("proposed_metadata") or {})
        for item in suggestions
        if _normalized_key(item.get("tool_id"))
    }


def _apply_selected_candidate(
    *,
    layer: str,
    item_id: str,
    candidate: dict[str, Any],
    intent_map: dict[str, dict[str, Any]],
    agent_map: dict[str, dict[str, Any]],
    tool_map: dict[str, dict[str, Any]],
    intent_patch_map: dict[str, dict[str, Any]],
    agent_patch_map: dict[str, dict[str, Any]],
    tool_patch_map: dict[str, dict[str, Any]],
) -> None:
    if layer == "intent":
        intent_map[item_id] = dict(candidate)
        intent_patch_map[item_id] = dict(candidate)
        return
    if layer == "agent":
        agent_map[item_id] = dict(candidate)
        agent_patch_map[item_id] = dict(candidate)
        return
    tool_map[item_id] = dict(candidate)
    tool_patch_map[item_id] = dict(candidate)


def _upstream_ok(
    *,
    layer: str,
    before_summary: dict[str, Any],
    after_summary: dict[str, Any],
    epsilon: float = 0.01,
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if layer == "intent":
        return True, notes
    before_intent = float(before_summary.get("intent_accuracy") or 0.0)
    after_intent = float(after_summary.get("intent_accuracy") or 0.0)
    if after_intent < before_intent - epsilon:
        notes.append(
            f"Intent accuracy regressade ({before_intent:.3f} -> {after_intent:.3f})."
        )
        return False, notes
    if layer == "tool":
        before_agent_cond = before_summary.get("agent_accuracy_given_intent_correct")
        after_agent_cond = after_summary.get("agent_accuracy_given_intent_correct")
        if isinstance(before_agent_cond, (float, int)) and isinstance(
            after_agent_cond, (float, int)
        ):
            if float(after_agent_cond) < float(before_agent_cond) - epsilon:
                notes.append(
                    "Agent|Intent-regression över tröskel efter tool-stage."
                )
                return False, notes
    return True, notes


async def run_bottom_up_metadata_separation(
    *,
    rebuild_tool_index_fn: Callable[[dict[str, dict[str, Any]]], Awaitable[list[ToolIndexEntry]]],
    retrieval_tuning: dict[str, Any],
    expected_intent_by_tool: dict[str, str],
    expected_agent_by_tool: dict[str, str],
    intent_definitions: list[dict[str, Any]],
    agent_metadata: list[dict[str, Any]],
    tool_patch_map: dict[str, dict[str, Any]],
    intent_patch_map: dict[str, dict[str, Any]],
    agent_patch_map: dict[str, dict[str, Any]],
    tool_ids: list[str] | None = None,
    tool_id_prefix: str | None = None,
    retrieval_limit: int = 5,
    max_tools: int = 25,
    max_queries_per_tool: int = 6,
    hard_negatives_per_tool: int = 1,
    anchor_probe_set: list[dict[str, Any]] | None = None,
    include_llm_refinement: bool = True,
    llm: Any = None,
    llm_parallelism: int = 4,
    intent_layer_config: dict[str, Any] | None = None,
    agent_layer_config: dict[str, Any] | None = None,
    tool_layer_config: dict[str, Any] | None = None,
    stability_locked_tool_ids: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    total_started_at = perf_counter()
    normalized_tuning = normalize_retrieval_tuning(retrieval_tuning or {})
    semantic_weight = float(
        getattr(normalized_tuning, "semantic_embedding_weight", 1.0)
    )
    structural_weight = float(
        getattr(normalized_tuning, "structural_embedding_weight", 0.0)
    )
    intent_cfg = _normalize_layer_config(intent_layer_config)
    agent_cfg = _normalize_layer_config(agent_layer_config)
    tool_cfg = _normalize_layer_config(tool_layer_config)
    locked_tool_ids = {
        _normalized_key(item_id)
        for item_id in list(stability_locked_tool_ids or [])
        if _normalized_key(item_id)
    }
    current_tool_patch_map = _copy_tool_patch_map(tool_patch_map)
    current_intent_patch_map = _copy_simple_patch_map(intent_patch_map)
    current_agent_patch_map = _copy_simple_patch_map(agent_patch_map)
    current_intent_map: dict[str, dict[str, Any]] = {}
    for payload in intent_definitions:
        intent_id = _normalized_key(payload.get("intent_id"))
        if intent_id:
            current_intent_map[intent_id] = dict(payload)
    current_agent_map: dict[str, dict[str, Any]] = {}
    for payload in agent_metadata:
        agent_id = _normalized_key(payload.get("agent_id"))
        if agent_id:
            current_agent_map[agent_id] = dict(payload)

    baseline_started_at = perf_counter()
    current_tool_index = await rebuild_tool_index_fn(current_tool_patch_map)
    current_tool_map: dict[str, dict[str, Any]] = {
        _normalized_key(entry.tool_id): _serialize_tool_entry(entry)
        for entry in current_tool_index
        if _normalized_key(entry.tool_id)
    }
    baseline_anchor = list(anchor_probe_set or [])
    baseline_result = await run_layered_metadata_audit(
        tool_index=current_tool_index,
        llm=None,
        retrieval_tuning=retrieval_tuning,
        intent_definitions=list(current_intent_map.values()),
        agent_metadata=list(current_agent_map.values()),
        expected_intent_by_tool=expected_intent_by_tool,
        expected_agent_by_tool=expected_agent_by_tool,
        tool_ids=list(tool_ids or []),
        tool_id_prefix=tool_id_prefix,
        include_existing_examples=True,
        include_llm_generated=False,
        llm_queries_per_tool=1,
        max_queries_per_tool=max(1, min(int(max_queries_per_tool or 6), 20)),
        hard_negatives_per_tool=max(0, min(int(hard_negatives_per_tool or 1), 10)),
        retrieval_limit=max(2, min(int(retrieval_limit or 5), 20)),
        max_tools=max(1, min(int(max_tools or 25), 200)),
        probe_generation_parallelism=1,
        probe_round=1,
        exclude_probe_queries=[],
        anchor_probe_set=baseline_anchor,
    )
    if not baseline_anchor:
        baseline_anchor = _build_anchor_probe_set(list(baseline_result.get("probes") or []))
    baseline_audit_ms = (perf_counter() - baseline_started_at) * 1000
    current_audit = baseline_result
    stage_reports: list[dict[str, Any]] = []
    contrast_updates: list[dict[str, Any]] = []
    candidate_count_total = 0
    candidate_count_rule = 0
    candidate_count_llm = 0
    candidate_count_combined = 0
    candidate_count_selected = 0
    candidate_count_rejected = 0
    stage_total_started_at = perf_counter()

    async def _run_stage(layer: str, cfg: _LayerConfig) -> tuple[dict[str, Any], float]:
        nonlocal current_audit
        nonlocal current_tool_index
        nonlocal current_tool_map
        nonlocal candidate_count_total
        nonlocal candidate_count_rule
        nonlocal candidate_count_llm
        nonlocal candidate_count_combined
        nonlocal candidate_count_selected
        nonlocal candidate_count_rejected
        stage_started_at = perf_counter()
        before_summary = dict(current_audit.get("summary") or {})
        before_metric = _layer_metric(layer, before_summary)
        stage_report: dict[str, Any] = {
            "layer": layer,
            "enabled": bool(cfg.enabled),
            "locked": False,
            "skipped_reason": None,
            "before_metric": before_metric,
            "after_metric": before_metric,
            "delta_pp": 0.0,
            "before_total_accuracy": float(
                before_summary.get(f"{layer}_accuracy") or before_metric
            ),
            "after_total_accuracy": float(
                before_summary.get(f"{layer}_accuracy") or before_metric
            ),
            "applied_changes": 0,
            "evaluated_items": 0,
            "candidate_decisions": [],
            "similarity_matrices": [],
            "notes": [],
            "mini_audit_summary": None,
        }
        if not cfg.enabled:
            stage_report["locked"] = True
            stage_report["skipped_reason"] = "Layer avaktiverat i separation-konfig."
            return stage_report, (perf_counter() - stage_started_at) * 1000

        probes = list(current_audit.get("probes") or [])
        layer_stats = _aggregate_layer_stats(probes=probes, layer=layer, cfg=cfg)
        unstable = {
            item_id: stats
            for item_id, stats in layer_stats.items()
            if str(stats.get("tier")) != "stable"
        }
        if layer == "tool" and locked_tool_ids:
            locked_candidates = sorted(
                item_id for item_id in unstable.keys() if item_id in locked_tool_ids
            )
            if locked_candidates:
                for item_id in locked_candidates:
                    unstable.pop(item_id, None)
                stage_report["notes"].append(
                    "Stability-lock exkluderade tools från rewrite: "
                    + ", ".join(locked_candidates[:12])
                    + ("..." if len(locked_candidates) > 12 else "")
                )
        if not unstable:
            stage_report["locked"] = True
            stage_report["skipped_reason"] = "Inga instabila kandidater i lagret."
            stage_report["mini_audit_summary"] = before_summary
            return stage_report, (perf_counter() - stage_started_at) * 1000

        components = _conflict_components(layer_stats=layer_stats)
        baseline_cluster_balance = _cluster_balance_score(
            layer=layer,
            components=components,
            intent_map=current_intent_map,
            agent_map=current_agent_map,
            tool_map=current_tool_map,
            tool_struct_map=_extract_tool_struct_map(current_tool_index),
            semantic_weight=semantic_weight,
            structural_weight=structural_weight,
        )
        ordered_ids: list[str] = []
        for component in components:
            sorted_component = sorted(
                component,
                key=lambda item_id: float(unstable.get(item_id, {}).get("severity") or 0.0),
                reverse=True,
            )
            ordered_ids.extend(sorted_component)
        ordered_ids = _dedupe_strings(ordered_ids, max_items=cfg.max_items)
        stage_report["evaluated_items"] = len(ordered_ids)
        llm_map: dict[str, dict[str, Any]] = {}
        llm_enabled_for_stage = bool(include_llm_refinement and cfg.llm_enabled and llm is not None)
        if llm_enabled_for_stage:
            llm_map = await _build_llm_candidate_maps(
                layer=layer,
                target_ids=ordered_ids,
                probes=probes,
                llm=llm,
                llm_parallelism=llm_parallelism,
                intent_map=current_intent_map,
                agent_map=current_agent_map,
                tool_index=current_tool_index,
                retrieval_tuning=retrieval_tuning,
            )

        if layer == "tool":
            tool_struct_map = _extract_tool_struct_map(current_tool_index)
        else:
            tool_struct_map = _extract_tool_struct_map(current_tool_index)

        pre_stage_tool_patch = _copy_tool_patch_map(current_tool_patch_map)
        pre_stage_intent_patch = _copy_simple_patch_map(current_intent_patch_map)
        pre_stage_agent_patch = _copy_simple_patch_map(current_agent_patch_map)
        pre_stage_intent_map = deepcopy(current_intent_map)
        pre_stage_agent_map = deepcopy(current_agent_map)
        pre_stage_tool_map = deepcopy(current_tool_map)

        processed_ids: list[str] = []
        for item_id in ordered_ids:
            stats = unstable.get(item_id)
            if not stats:
                continue
            current_payload = (
                current_intent_map.get(item_id)
                if layer == "intent"
                else current_agent_map.get(item_id)
                if layer == "agent"
                else current_tool_map.get(item_id)
            )
            if not isinstance(current_payload, dict):
                continue
            scope_ids = (
                _intent_scope_ids(current_payload, current_intent_map)
                if layer == "intent"
                else list(current_agent_map.keys())
                if layer == "agent"
                else _tool_scope_ids(current_payload, current_tool_map)
            )
            primary_competitor = _normalized_key(stats.get("primary_competitor"))
            if not primary_competitor:
                primary_competitor = _pick_primary_competitor_from_similarity(
                    layer=layer,
                    item_id=item_id,
                    scope_ids=scope_ids,
                    intent_map=current_intent_map,
                    agent_map=current_agent_map,
                    tool_map=current_tool_map,
                    tool_struct_map=tool_struct_map,
                    semantic_weight=semantic_weight,
                    structural_weight=structural_weight,
                )
            competitor_payload = (
                current_intent_map.get(primary_competitor)
                if layer == "intent"
                else current_agent_map.get(primary_competitor)
                if layer == "agent"
                else current_tool_map.get(primary_competitor)
            )
            contrast_hints = _contrast_hints_for_item(layer, item_id)
            rule_candidate = _rule_patch_candidate(
                layer=layer,
                item_id=item_id,
                current=current_payload,
                competitor_id=primary_competitor,
                competitor_payload=competitor_payload if isinstance(competitor_payload, dict) else None,
                failed_queries=list(stats.get("failed_queries") or []),
                contrast_hints=contrast_hints,
            )
            candidate_entries: list[tuple[str, dict[str, Any]]] = []
            if not _metadata_equal(layer, current_payload, rule_candidate):
                candidate_entries.append(("rule", rule_candidate))
            llm_candidate = llm_map.get(item_id)
            if isinstance(llm_candidate, dict) and llm_candidate:
                llm_candidate = deepcopy(llm_candidate)
                if layer == "tool":
                    llm_candidate["tool_id"] = item_id
                    llm_candidate["category"] = _normalize_text(
                        current_payload.get("category")
                    ) or _normalize_text(llm_candidate.get("category"))
                    llm_candidate["base_path"] = current_payload.get("base_path")
                elif layer == "intent":
                    llm_candidate["intent_id"] = item_id
                    llm_candidate["priority"] = int(
                        llm_candidate.get("priority")
                        if llm_candidate.get("priority") is not None
                        else current_payload.get("priority") or 500
                    )
                    llm_candidate["enabled"] = bool(
                        llm_candidate.get("enabled")
                        if llm_candidate.get("enabled") is not None
                        else current_payload.get("enabled", True)
                    )
                else:
                    llm_candidate["agent_id"] = item_id
                    llm_candidate["prompt_key"] = (
                        _normalize_text(llm_candidate.get("prompt_key"))
                        or _normalize_text(current_payload.get("prompt_key"))
                        or None
                    )
                    llm_candidate["namespace"] = _safe_string_list(
                        llm_candidate.get("namespace")
                    ) or _safe_string_list(current_payload.get("namespace"))
                if not _metadata_equal(layer, current_payload, llm_candidate):
                    candidate_entries.append(("llm", llm_candidate))
                    merged_candidate = _merge_candidates(
                        layer=layer,
                        current=current_payload,
                        rule_candidate=rule_candidate,
                        llm_candidate=llm_candidate,
                    )
                    if not _metadata_equal(layer, current_payload, merged_candidate):
                        candidate_entries.append(("combined", merged_candidate))

            decision_payload: dict[str, Any] = {
                "item_id": item_id,
                "tier": str(stats.get("tier") or "watch"),
                "probes": int(stats.get("probes") or 0),
                "top1_rate": float(stats.get("top1_rate") or 0.0),
                "avg_margin": (
                    float(stats["avg_margin"])
                    if isinstance(stats.get("avg_margin"), (float, int))
                    else None
                ),
                "primary_competitor": primary_competitor or None,
                "selected_source": "none",
                "local_check_passed": False,
                "global_check_passed": False,
                "selected_score": None,
                "selected_margin": None,
                "selected_alignment": None,
                "selected_nearest_similarity": None,
                "selected_similarity_to_primary": None,
                "old_similarity_to_primary": None,
                "old_margin": None,
                "applied": False,
                "rejection_reasons": [],
            }
            processed_ids.append(item_id)
            if not candidate_entries:
                decision_payload["rejection_reasons"] = ["Ingen kandidat skilde sig från nuvarande metadata."]
                stage_report["candidate_decisions"].append(decision_payload)
                candidate_count_rejected += 1
                continue

            selected: tuple[str, dict[str, Any], dict[str, Any]] | None = None
            for source, candidate_payload in candidate_entries:
                candidate_count_total += 1
                if source == "rule":
                    candidate_count_rule += 1
                elif source == "llm":
                    candidate_count_llm += 1
                elif source == "combined":
                    candidate_count_combined += 1
                eval_payload = _evaluate_candidate(
                    layer=layer,
                    candidate=candidate_payload,
                    current=current_payload,
                    item_id=item_id,
                    primary_competitor=primary_competitor,
                    scope_ids=scope_ids,
                    query_alignment_source=list(stats.get("queries") or []),
                    cfg=cfg,
                    intent_map=current_intent_map,
                    agent_map=current_agent_map,
                    tool_map=current_tool_map,
                    tool_struct_map=tool_struct_map,
                    semantic_weight=semantic_weight,
                    structural_weight=structural_weight,
                )
                if not bool(eval_payload.get("local_pass")):
                    decision_payload["rejection_reasons"].append(
                        f"{source}: local-check failed"
                    )
                    continue
                if not bool(eval_payload.get("global_pass")):
                    contrast_violations = list(eval_payload.get("contrast_violations") or [])
                    if contrast_violations:
                        decision_payload["rejection_reasons"].append(
                            f"{source}: contrast-memory drift ({'; '.join(contrast_violations[:3])})"
                        )
                    else:
                        decision_payload["rejection_reasons"].append(
                            f"{source}: global-safety failed"
                        )
                    continue
                if selected is None:
                    selected = (source, candidate_payload, eval_payload)
                    continue
                _selected_source, _selected_payload, selected_eval = selected
                if float(eval_payload.get("margin_new") or -9.0) > float(
                    selected_eval.get("margin_new") or -9.0
                ):
                    selected = (source, candidate_payload, eval_payload)
                elif float(eval_payload.get("margin_new") or -9.0) == float(
                    selected_eval.get("margin_new") or -9.0
                ) and float(eval_payload.get("score") or -9.0) > float(
                    selected_eval.get("score") or -9.0
                ):
                    selected = (source, candidate_payload, eval_payload)

            if selected is None:
                stage_report["candidate_decisions"].append(decision_payload)
                candidate_count_rejected += 1
                continue

            selected_source, selected_candidate, selected_eval = selected
            decision_payload.update(
                {
                    "selected_source": selected_source,
                    "local_check_passed": bool(selected_eval.get("local_pass")),
                    "global_check_passed": bool(selected_eval.get("global_pass")),
                    "selected_score": float(selected_eval.get("score") or 0.0),
                    "selected_margin": float(selected_eval.get("margin_new") or 0.0),
                    "selected_alignment": float(selected_eval.get("alignment_new") or 0.0),
                    "selected_nearest_similarity": float(
                        selected_eval.get("nearest_new") or 0.0
                    ),
                    "selected_similarity_to_primary": selected_eval.get(
                        "similarity_to_primary_new"
                    ),
                    "old_similarity_to_primary": selected_eval.get(
                        "similarity_to_primary_old"
                    ),
                    "old_margin": float(selected_eval.get("margin_old") or 0.0),
                    "applied": True,
                }
            )
            _apply_selected_candidate(
                layer=layer,
                item_id=item_id,
                candidate=selected_candidate,
                intent_map=current_intent_map,
                agent_map=current_agent_map,
                tool_map=current_tool_map,
                intent_patch_map=current_intent_patch_map,
                agent_patch_map=current_agent_patch_map,
                tool_patch_map=current_tool_patch_map,
            )
            stage_report["candidate_decisions"].append(decision_payload)
            candidate_count_selected += 1
            stage_report["applied_changes"] += 1

            if primary_competitor:
                memory_key = _pair_key(item_id, primary_competitor)
                memory_text = _contrast_memory_text(
                    layer=layer,
                    item_id=item_id,
                    competitor_id=primary_competitor,
                    current=selected_candidate,
                    competitor=competitor_payload if isinstance(competitor_payload, dict) else None,
                )
                _CONTRAST_MEMORY.setdefault(layer, {})[memory_key] = memory_text
                contrast_updates.append(
                    {
                        "layer": layer,
                        "item_id": item_id,
                        "competitor_id": primary_competitor,
                        "memory_text": memory_text,
                        "updated": True,
                    }
                )

        stage_report["similarity_matrices"] = _build_stage_matrices(
            layer=layer,
            processed_item_ids=processed_ids,
            intent_map=current_intent_map,
            agent_map=current_agent_map,
            tool_map=current_tool_map,
            tool_struct_map=tool_struct_map,
            semantic_weight=semantic_weight,
            structural_weight=structural_weight,
        )

        if stage_report["applied_changes"] <= 0:
            stage_report["locked"] = True
            stage_report["mini_audit_summary"] = before_summary
            return stage_report, (perf_counter() - stage_started_at) * 1000

        current_tool_index = await rebuild_tool_index_fn(current_tool_patch_map)
        current_tool_map = {
            _normalized_key(entry.tool_id): _serialize_tool_entry(entry)
            for entry in current_tool_index
            if _normalized_key(entry.tool_id)
        }
        mini_audit = await run_layered_metadata_audit(
            tool_index=current_tool_index,
            llm=None,
            retrieval_tuning=retrieval_tuning,
            intent_definitions=list(current_intent_map.values()),
            agent_metadata=list(current_agent_map.values()),
            expected_intent_by_tool=expected_intent_by_tool,
            expected_agent_by_tool=expected_agent_by_tool,
            tool_ids=list(tool_ids or []),
            tool_id_prefix=tool_id_prefix,
            include_existing_examples=True,
            include_llm_generated=False,
            llm_queries_per_tool=1,
            max_queries_per_tool=max(1, min(int(max_queries_per_tool or 6), 20)),
            hard_negatives_per_tool=max(0, min(int(hard_negatives_per_tool or 1), 10)),
            retrieval_limit=max(2, min(int(retrieval_limit or 5), 20)),
            max_tools=max(1, min(int(max_tools or 25), 200)),
            probe_generation_parallelism=1,
            probe_round=1,
            exclude_probe_queries=[],
            anchor_probe_set=baseline_anchor,
        )
        after_summary = dict(mini_audit.get("summary") or {})
        after_metric = _layer_metric(layer, after_summary)
        delta = after_metric - before_metric
        after_tool_struct_map = _extract_tool_struct_map(current_tool_index)
        after_cluster_balance = _cluster_balance_score(
            layer=layer,
            components=components,
            intent_map=current_intent_map,
            agent_map=current_agent_map,
            tool_map=current_tool_map,
            tool_struct_map=after_tool_struct_map,
            semantic_weight=semantic_weight,
            structural_weight=structural_weight,
        )
        upstream_ok, upstream_notes = _upstream_ok(
            layer=layer,
            before_summary=before_summary,
            after_summary=after_summary,
        )
        metric_ok = delta >= float(cfg.min_metric_delta)
        if not metric_ok:
            stage_report["notes"].append(
                f"Metric-delta under tröskel ({delta * 100:.2f} pp < {cfg.min_metric_delta * 100:.2f} pp)."
            )
        cluster_balance_ok = True
        if baseline_cluster_balance is not None and after_cluster_balance is not None:
            allowed_drop = max(_CLUSTER_BALANCE_MAX_DROP, float(cfg.epsilon_noise))
            if after_cluster_balance < (baseline_cluster_balance - allowed_drop):
                cluster_balance_ok = False
                stage_report["notes"].append(
                    "Cluster-balance regressade: "
                    f"{baseline_cluster_balance:.4f} -> {after_cluster_balance:.4f} "
                    f"(max tillåten drop {allowed_drop:.4f})."
                )
            else:
                stage_report["notes"].append(
                    "Cluster-balance ok: "
                    f"{baseline_cluster_balance:.4f} -> {after_cluster_balance:.4f}."
                )
        stage_report["notes"].extend(upstream_notes)

        locked = bool(metric_ok and upstream_ok and cluster_balance_ok)
        stage_report["locked"] = locked
        stage_report["after_metric"] = after_metric
        stage_report["delta_pp"] = round(delta * 100, 2)
        stage_report["after_total_accuracy"] = float(
            after_summary.get(f"{layer}_accuracy") or after_metric
        )
        stage_report["mini_audit_summary"] = after_summary

        if locked:
            current_audit = mini_audit
            stage_report["notes"].append("Stage låst efter mini-audit.")
            return stage_report, (perf_counter() - stage_started_at) * 1000

        current_tool_patch_map.clear()
        current_tool_patch_map.update(pre_stage_tool_patch)
        current_intent_patch_map.clear()
        current_intent_patch_map.update(pre_stage_intent_patch)
        current_agent_patch_map.clear()
        current_agent_patch_map.update(pre_stage_agent_patch)
        current_intent_map.clear()
        current_intent_map.update(pre_stage_intent_map)
        current_agent_map.clear()
        current_agent_map.update(pre_stage_agent_map)
        current_tool_map = pre_stage_tool_map
        current_tool_index = await rebuild_tool_index_fn(current_tool_patch_map)
        current_audit = {
            **current_audit,
            "summary": before_summary,
        }
        stage_report["notes"].append("Stage rollbackad pga gate-fel.")
        stage_report["applied_changes"] = 0
        return stage_report, (perf_counter() - stage_started_at) * 1000

    intent_report, intent_ms = await _run_stage("intent", intent_cfg)
    stage_reports.append(intent_report)
    agent_report, agent_ms = await _run_stage("agent", agent_cfg)
    stage_reports.append(agent_report)
    tool_report, tool_ms = await _run_stage("tool", tool_cfg)
    stage_reports.append(tool_report)
    stage_total_ms = (perf_counter() - stage_total_started_at) * 1000

    final_started_at = perf_counter()
    current_tool_index = await rebuild_tool_index_fn(current_tool_patch_map)
    final_audit = await run_layered_metadata_audit(
        tool_index=current_tool_index,
        llm=None,
        retrieval_tuning=retrieval_tuning,
        intent_definitions=list(current_intent_map.values()),
        agent_metadata=list(current_agent_map.values()),
        expected_intent_by_tool=expected_intent_by_tool,
        expected_agent_by_tool=expected_agent_by_tool,
        tool_ids=list(tool_ids or []),
        tool_id_prefix=tool_id_prefix,
        include_existing_examples=True,
        include_llm_generated=False,
        llm_queries_per_tool=1,
        max_queries_per_tool=max(1, min(int(max_queries_per_tool or 6), 20)),
        hard_negatives_per_tool=max(0, min(int(hard_negatives_per_tool or 1), 10)),
        retrieval_limit=max(2, min(int(retrieval_limit or 5), 20)),
        max_tools=max(1, min(int(max_tools or 25), 200)),
        probe_generation_parallelism=1,
        probe_round=1,
        exclude_probe_queries=[],
        anchor_probe_set=baseline_anchor,
    )
    final_audit_ms = (perf_counter() - final_started_at) * 1000
    total_ms = (perf_counter() - total_started_at) * 1000
    contrast_memory_rows: list[dict[str, Any]] = []
    for layer, rows in _CONTRAST_MEMORY.items():
        for (left, right), text in rows.items():
            contrast_memory_rows.append(
                {
                    "layer": layer,
                    "item_id": left,
                    "competitor_id": right,
                    "memory_text": text,
                    "updated": False,
                }
            )
    contrast_memory_rows.extend(contrast_updates)
    deduped_contrast: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in contrast_memory_rows:
        key = (
            _normalized_key(item.get("layer")),
            _normalized_key(item.get("item_id")),
            _normalized_key(item.get("competitor_id")),
        )
        deduped_contrast[key] = item
    normalized_tool_patch_output: list[dict[str, Any]] = []
    for tool_id, payload in current_tool_patch_map.items():
        normalized_tool_patch_output.append(
            {
                "tool_id": _normalize_text(payload.get("tool_id")) or _normalize_text(tool_id),
                "name": _normalize_text(payload.get("name")),
                "description": _normalize_text(payload.get("description")),
                "keywords": _safe_string_list(payload.get("keywords")),
                "example_queries": _safe_string_list(payload.get("example_queries")),
                "category": _normalize_text(payload.get("category")),
                "base_path": (
                    _normalize_text(payload.get("base_path")) or None
                    if payload.get("base_path") is not None
                    else None
                ),
            }
        )
    normalized_intent_patch_output: list[dict[str, Any]] = []
    for intent_id, payload in current_intent_patch_map.items():
        normalized_intent_patch_output.append(
            {
                "intent_id": _normalize_text(payload.get("intent_id")) or _normalize_text(intent_id),
                "label": _normalize_text(payload.get("label")),
                "route": _normalize_text(payload.get("route")) or "knowledge",
                "description": _normalize_text(payload.get("description")),
                "keywords": _safe_string_list(payload.get("keywords")),
                "priority": int(payload.get("priority") or 500),
                "enabled": bool(payload.get("enabled", True)),
            }
        )
    normalized_agent_patch_output: list[dict[str, Any]] = []
    for agent_id, payload in current_agent_patch_map.items():
        normalized_agent_patch_output.append(
            {
                "agent_id": _normalize_text(payload.get("agent_id")) or _normalize_text(agent_id),
                "label": _normalize_text(payload.get("label")),
                "description": _normalize_text(payload.get("description")),
                "keywords": _safe_string_list(payload.get("keywords")),
                "prompt_key": _normalize_text(payload.get("prompt_key")) or None,
                "namespace": _safe_string_list(payload.get("namespace")),
            }
        )
    return {
        "baseline_summary": dict(baseline_result.get("summary") or {}),
        "final_summary": dict(final_audit.get("summary") or {}),
        "stage_reports": stage_reports,
        "proposed_tool_metadata_patch": normalized_tool_patch_output,
        "proposed_intent_metadata_patch": normalized_intent_patch_output,
        "proposed_agent_metadata_patch": normalized_agent_patch_output,
        "contrast_memory": list(deduped_contrast.values()),
        "diagnostics": {
            "total_ms": round(float(total_ms), 2),
            "baseline_audit_ms": round(float(baseline_audit_ms), 2),
            "final_audit_ms": round(float(final_audit_ms), 2),
            "stage_total_ms": round(float(stage_total_ms), 2),
            "stage_intent_ms": round(float(intent_ms), 2),
            "stage_agent_ms": round(float(agent_ms), 2),
            "stage_tool_ms": round(float(tool_ms), 2),
            "candidate_count_total": int(candidate_count_total),
            "candidate_count_rule": int(candidate_count_rule),
            "candidate_count_llm": int(candidate_count_llm),
            "candidate_count_combined": int(candidate_count_combined),
            "candidate_count_selected": int(candidate_count_selected),
            "candidate_count_rejected": int(candidate_count_rejected),
            "llm_refinement_enabled": bool(include_llm_refinement),
            "llm_parallelism": int(max(1, min(int(llm_parallelism or 1), 32))),
            "anchor_probe_count": int(len(baseline_anchor)),
        },
        "final_tool_index": current_tool_index,
    }


_LOCK_LAYER_SET = {"intent", "agent", "tool"}
_STABILITY_LAYER_SET = {"tool"}
_STABILITY_LOCK_LEVELS = {"soft", "hard"}
_DEFAULT_STABILITY_LOCK_CONFIG = {
    "min_rounds": 2,
    "rank_shift_tolerance": 0.0,
    "top1_lock_threshold": 0.95,
    "top1_hard_lock_threshold": 1.0,
    "topk_lock_threshold": 1.0,
    "margin_lock_threshold": 0.8,
    "min_total_probes": 100,
    "min_probes_per_tool": 5,
    "global_median_margin_threshold": 2.0,
    "max_negative_margins": 1,
    "global_rank_shift_tolerance": 0.0,
    "unlock_top1_drop_pp": 0.10,
    "unlock_margin_negative_rounds": 2,
    "history_size": 12,
}


def _lock_pair_key(layer: str, item_a: str, item_b: str) -> tuple[str, str, str]:
    left = _normalized_key(item_a)
    right = _normalized_key(item_b)
    if left <= right:
        return (_normalized_key(layer), left, right)
    return (_normalized_key(layer), right, left)


def _normalize_stability_config(payload: Any) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    min_rounds = max(
        2,
        min(
            6,
            _as_int(
                raw.get("min_rounds"),
                int(_DEFAULT_STABILITY_LOCK_CONFIG["min_rounds"]),
            ),
        ),
    )
    rank_shift_tolerance = max(
        0.0,
        min(
            5.0,
            _as_float(
                raw.get("rank_shift_tolerance"),
                float(_DEFAULT_STABILITY_LOCK_CONFIG["rank_shift_tolerance"]),
            ),
        ),
    )
    top1_lock_threshold = max(
        0.0,
        min(
            1.0,
            _as_float(
                raw.get("top1_lock_threshold"),
                float(_DEFAULT_STABILITY_LOCK_CONFIG["top1_lock_threshold"]),
            ),
        ),
    )
    top1_hard_lock_threshold = max(
        top1_lock_threshold,
        min(
            1.0,
            _as_float(
                raw.get("top1_hard_lock_threshold"),
                float(_DEFAULT_STABILITY_LOCK_CONFIG["top1_hard_lock_threshold"]),
            ),
        ),
    )
    topk_lock_threshold = max(
        0.0,
        min(
            1.0,
            _as_float(
                raw.get("topk_lock_threshold"),
                float(_DEFAULT_STABILITY_LOCK_CONFIG["topk_lock_threshold"]),
            ),
        ),
    )
    margin_lock_threshold = max(
        -2.0,
        min(
            10.0,
            _as_float(
                raw.get("margin_lock_threshold"),
                float(_DEFAULT_STABILITY_LOCK_CONFIG["margin_lock_threshold"]),
            ),
        ),
    )
    min_total_probes = max(
        1,
        min(
            10000,
            _as_int(
                raw.get("min_total_probes"),
                int(_DEFAULT_STABILITY_LOCK_CONFIG["min_total_probes"]),
            ),
        ),
    )
    min_probes_per_tool = max(
        1,
        min(
            1000,
            _as_int(
                raw.get("min_probes_per_tool"),
                int(_DEFAULT_STABILITY_LOCK_CONFIG["min_probes_per_tool"]),
            ),
        ),
    )
    global_median_margin_threshold = max(
        -10.0,
        min(
            25.0,
            _as_float(
                raw.get("global_median_margin_threshold"),
                float(_DEFAULT_STABILITY_LOCK_CONFIG["global_median_margin_threshold"]),
            ),
        ),
    )
    max_negative_margins = max(
        0,
        min(
            1000,
            _as_int(
                raw.get("max_negative_margins"),
                int(_DEFAULT_STABILITY_LOCK_CONFIG["max_negative_margins"]),
            ),
        ),
    )
    global_rank_shift_tolerance = max(
        0.0,
        min(
            5.0,
            _as_float(
                raw.get("global_rank_shift_tolerance"),
                float(_DEFAULT_STABILITY_LOCK_CONFIG["global_rank_shift_tolerance"]),
            ),
        ),
    )
    unlock_top1_drop_pp = max(
        0.0,
        min(
            1.0,
            _as_float(
                raw.get("unlock_top1_drop_pp"),
                float(_DEFAULT_STABILITY_LOCK_CONFIG["unlock_top1_drop_pp"]),
            ),
        ),
    )
    unlock_margin_negative_rounds = max(
        1,
        min(
            10,
            _as_int(
                raw.get("unlock_margin_negative_rounds"),
                int(_DEFAULT_STABILITY_LOCK_CONFIG["unlock_margin_negative_rounds"]),
            ),
        ),
    )
    history_size = max(
        3,
        min(
            50,
            _as_int(
                raw.get("history_size"),
                int(_DEFAULT_STABILITY_LOCK_CONFIG["history_size"]),
            ),
        ),
    )
    return {
        "min_rounds": min_rounds,
        "rank_shift_tolerance": rank_shift_tolerance,
        "top1_lock_threshold": top1_lock_threshold,
        "top1_hard_lock_threshold": top1_hard_lock_threshold,
        "topk_lock_threshold": topk_lock_threshold,
        "margin_lock_threshold": margin_lock_threshold,
        "min_total_probes": min_total_probes,
        "min_probes_per_tool": min_probes_per_tool,
        "global_median_margin_threshold": global_median_margin_threshold,
        "max_negative_margins": max_negative_margins,
        "global_rank_shift_tolerance": global_rank_shift_tolerance,
        "unlock_top1_drop_pp": unlock_top1_drop_pp,
        "unlock_margin_negative_rounds": unlock_margin_negative_rounds,
        "history_size": history_size,
    }


def _normalize_stability_history(
    payload: Any,
    *,
    history_size: int,
) -> dict[str, list[dict[str, Any]]]:
    raw = payload if isinstance(payload, dict) else {}
    normalized: dict[str, list[dict[str, Any]]] = {}
    for raw_item_id, raw_samples in raw.items():
        item_id = _normalized_key(raw_item_id)
        if not item_id:
            continue
        if not isinstance(raw_samples, list):
            continue
        samples: list[dict[str, Any]] = []
        for sample in raw_samples:
            if not isinstance(sample, dict):
                continue
            probes = max(0, _as_int(sample.get("probes"), 0))
            top1_rate = max(0.0, min(1.0, _as_float(sample.get("top1_rate"), 0.0)))
            topk_rate = max(0.0, min(1.0, _as_float(sample.get("topk_rate"), 0.0)))
            avg_margin_raw = sample.get("avg_margin")
            avg_margin = (
                float(avg_margin_raw)
                if isinstance(avg_margin_raw, (float, int))
                else None
            )
            avg_expected_rank_raw = sample.get("avg_expected_rank")
            avg_expected_rank = (
                float(avg_expected_rank_raw)
                if isinstance(avg_expected_rank_raw, (float, int))
                else None
            )
            captured_at = _normalize_text(sample.get("captured_at")) or None
            samples.append(
                {
                    "captured_at": captured_at,
                    "probes": probes,
                    "top1_rate": top1_rate,
                    "topk_rate": topk_rate,
                    "avg_margin": avg_margin,
                    "avg_expected_rank": avg_expected_rank,
                }
            )
        if not samples:
            continue
        normalized[item_id] = samples[-history_size:]
    return normalized


def _normalize_stability_item_locks(payload: Any) -> list[dict[str, Any]]:
    raw_items = payload if isinstance(payload, list) else []
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        layer = _normalized_key(raw_item.get("layer"))
        item_id = _normalized_key(raw_item.get("item_id"))
        if layer not in _STABILITY_LAYER_SET or not item_id:
            continue
        lock_level = _normalized_key(raw_item.get("lock_level"))
        if lock_level not in _STABILITY_LOCK_LEVELS:
            lock_level = "soft"
        top1_rate = max(0.0, min(1.0, _as_float(raw_item.get("top1_rate"), 0.0)))
        topk_rate = max(0.0, min(1.0, _as_float(raw_item.get("topk_rate"), 0.0)))
        avg_margin_raw = raw_item.get("avg_margin")
        avg_margin = (
            float(avg_margin_raw)
            if isinstance(avg_margin_raw, (float, int))
            else None
        )
        last_rank_shift_raw = raw_item.get("last_rank_shift")
        last_rank_shift = (
            float(last_rank_shift_raw)
            if isinstance(last_rank_shift_raw, (float, int))
            else None
        )
        baseline_top1_raw = raw_item.get("baseline_top1_rate")
        baseline_top1_rate = (
            max(0.0, min(1.0, float(baseline_top1_raw)))
            if isinstance(baseline_top1_raw, (float, int))
            else None
        )
        baseline_margin_raw = raw_item.get("baseline_margin")
        baseline_margin = (
            float(baseline_margin_raw)
            if isinstance(baseline_margin_raw, (float, int))
            else None
        )
        normalized_item = {
            "layer": layer,
            "item_id": item_id,
            "locked": _as_bool(raw_item.get("locked"), True),
            "lock_level": lock_level,
            "lock_reason": _normalize_text(raw_item.get("lock_reason")) or None,
            "unlock_trigger": _normalize_text(raw_item.get("unlock_trigger")) or None,
            "source": _normalize_text(raw_item.get("source")) or "auto",
            "top1_rate": top1_rate,
            "topk_rate": topk_rate,
            "avg_margin": avg_margin,
            "last_rank_shift": last_rank_shift,
            "baseline_top1_rate": baseline_top1_rate,
            "baseline_margin": baseline_margin,
            "negative_margin_rounds": max(
                0,
                _as_int(raw_item.get("negative_margin_rounds"), 0),
            ),
            "locked_at": _normalize_text(raw_item.get("locked_at")) or None,
            "updated_at": _normalize_text(raw_item.get("updated_at")) or None,
        }
        key = (layer, item_id)
        existing = deduped.get(key)
        if not existing:
            deduped[key] = normalized_item
            continue
        existing_locked = bool(existing.get("locked"))
        next_locked = bool(normalized_item.get("locked"))
        if next_locked and not existing_locked:
            deduped[key] = normalized_item
            continue
        if next_locked == existing_locked and (
            _normalize_text(normalized_item.get("updated_at"))
            > _normalize_text(existing.get("updated_at"))
        ):
            deduped[key] = normalized_item
    rows = list(deduped.values())
    rows.sort(key=lambda item: (item.get("layer") or "", item.get("item_id") or ""))
    return rows


def normalize_metadata_separation_lock_registry(payload: Any) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    stability_config = _normalize_stability_config(raw.get("stability_config"))
    raw_locks = raw.get("pair_locks")
    normalized_locks: list[dict[str, Any]] = []
    if isinstance(raw_locks, list):
        for item in raw_locks:
            if not isinstance(item, dict):
                continue
            layer = _normalized_key(item.get("layer"))
            item_a = _normalized_key(item.get("item_a"))
            item_b = _normalized_key(item.get("item_b"))
            if layer not in _LOCK_LAYER_SET or not item_a or not item_b or item_a == item_b:
                continue
            _, left, right = _lock_pair_key(layer, item_a, item_b)
            max_similarity = max(-1.0, min(1.0, _as_float(item.get("max_similarity"), 0.9)))
            normalized_locks.append(
                {
                    "layer": layer,
                    "item_a": left,
                    "item_b": right,
                    "max_similarity": float(max_similarity),
                    "source": _normalize_text(item.get("source")) or "bsss",
                    "updated_at": _normalize_text(item.get("updated_at")) or None,
                }
            )
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for lock in normalized_locks:
        key = _lock_pair_key(lock["layer"], lock["item_a"], lock["item_b"])
        existing = deduped.get(key)
        if not existing:
            deduped[key] = lock
            continue
        # Keep the strictest ceiling when duplicates exist.
        existing["max_similarity"] = float(
            min(_as_float(existing.get("max_similarity"), 1.0), _as_float(lock.get("max_similarity"), 1.0))
        )
        if lock.get("updated_at"):
            existing["updated_at"] = lock["updated_at"]
        if lock.get("source"):
            existing["source"] = lock["source"]
    normalized_stability_history = _normalize_stability_history(
        raw.get("stability_history"),
        history_size=int(stability_config.get("history_size") or 12),
    )
    normalized_stability_items = _normalize_stability_item_locks(
        raw.get("stability_item_locks")
    )
    return {
        "lock_mode_enabled": _as_bool(raw.get("lock_mode_enabled"), True),
        "updated_at": _normalize_text(raw.get("updated_at")) or None,
        "pair_locks": list(deduped.values()),
        "stability_lock_mode_enabled": _as_bool(
            raw.get("stability_lock_mode_enabled"),
            True,
        ),
        "stability_auto_lock_enabled": _as_bool(
            raw.get("stability_auto_lock_enabled"),
            True,
        ),
        "stability_config": stability_config,
        "stability_item_locks": normalized_stability_items,
        "stability_history": normalized_stability_history,
    }


def build_metadata_separation_pair_locks_from_stage_reports(
    *,
    stage_reports: list[dict[str, Any]],
    epsilon: float = 0.015,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for stage in stage_reports or []:
        if not isinstance(stage, dict):
            continue
        layer = _normalized_key(stage.get("layer"))
        if layer not in _LOCK_LAYER_SET:
            continue
        decisions = stage.get("candidate_decisions")
        if not isinstance(decisions, list):
            continue
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            if not bool(decision.get("applied")):
                continue
            item_id = _normalized_key(decision.get("item_id"))
            competitor_id = _normalized_key(decision.get("primary_competitor"))
            if not item_id or not competitor_id or item_id == competitor_id:
                continue
            similarity_raw = decision.get("selected_similarity_to_primary")
            if similarity_raw is None:
                similarity_raw = decision.get("selected_nearest_similarity")
            if similarity_raw is None:
                continue
            similarity = _as_float(similarity_raw, 0.0)
            ceiling = max(-1.0, min(0.999, similarity + float(epsilon)))
            _, left, right = _lock_pair_key(layer, item_id, competitor_id)
            output.append(
                {
                    "layer": layer,
                    "item_a": left,
                    "item_b": right,
                    "max_similarity": float(ceiling),
                    "source": "bsss",
                    "updated_at": now_iso,
                }
            )
    return output


def merge_metadata_separation_pair_locks(
    *,
    existing_locks: list[dict[str, Any]],
    new_locks: list[dict[str, Any]],
    max_items: int = 4000,
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in list(existing_locks or []) + list(new_locks or []):
        if not isinstance(raw, dict):
            continue
        layer = _normalized_key(raw.get("layer"))
        item_a = _normalized_key(raw.get("item_a"))
        item_b = _normalized_key(raw.get("item_b"))
        if layer not in _LOCK_LAYER_SET or not item_a or not item_b or item_a == item_b:
            continue
        key = _lock_pair_key(layer, item_a, item_b)
        existing = merged.get(key)
        lock_payload = {
            "layer": key[0],
            "item_a": key[1],
            "item_b": key[2],
            "max_similarity": float(max(-1.0, min(1.0, _as_float(raw.get("max_similarity"), 0.9)))),
            "source": _normalize_text(raw.get("source")) or "bsss",
            "updated_at": _normalize_text(raw.get("updated_at")) or None,
        }
        if not existing:
            merged[key] = lock_payload
            continue
        existing["max_similarity"] = float(
            min(_as_float(existing.get("max_similarity"), 1.0), _as_float(lock_payload.get("max_similarity"), 1.0))
        )
        if lock_payload.get("updated_at"):
            existing["updated_at"] = lock_payload.get("updated_at")
        if lock_payload.get("source"):
            existing["source"] = lock_payload.get("source")
    rows = list(merged.values())
    rows.sort(key=lambda item: (item.get("layer") or "", item.get("item_a") or "", item.get("item_b") or ""))
    if len(rows) > int(max_items):
        rows = rows[: int(max_items)]
    return rows


def _stability_latest_rank_shift(history_rows: list[dict[str, Any]]) -> float | None:
    if len(history_rows) < 2:
        return None
    left_rank = history_rows[-2].get("avg_expected_rank")
    right_rank = history_rows[-1].get("avg_expected_rank")
    if not isinstance(left_rank, (float, int)) or not isinstance(right_rank, (float, int)):
        return None
    return float(abs(float(right_rank) - float(left_rank)))


def _stability_unlock_trigger_text(cfg: dict[str, Any]) -> str:
    drop_pp = float(cfg.get("unlock_top1_drop_pp") or 0.10) * 100
    negative_rounds = int(cfg.get("unlock_margin_negative_rounds") or 2)
    return (
        f"Lås upp vid top1-drop >= {drop_pp:.1f} pp mot baseline "
        f"eller margin < 0 i {negative_rounds} rundor i rad."
    )


def _stability_lock_reason_text(
    *,
    min_rounds: int,
    rank_shift_tolerance: float,
    top1_lock_threshold: float,
    topk_lock_threshold: float,
    margin_lock_threshold: float,
    latest_top1: float,
    latest_topk: float,
    latest_margin: float | None,
    hard_lock: bool,
    robust_gate_snapshot: dict[str, Any] | None = None,
) -> str:
    margin_text = (
        f"{latest_margin:.2f}" if isinstance(latest_margin, (float, int)) else "n/a"
    )
    level_text = "Hårt lås" if hard_lock else "Stabilt lås"
    robust_suffix = ""
    if isinstance(robust_gate_snapshot, dict):
        robust_suffix = (
            " Robust gate: "
            f"total_probes {int(robust_gate_snapshot.get('total_probes') or 0)}, "
            f"min_probes/tool {int(robust_gate_snapshot.get('min_probes_per_tool') or 0)}, "
            f"median_margin {float(robust_gate_snapshot.get('median_margin') or 0.0):.2f}, "
            f"neg_margins {int(robust_gate_snapshot.get('negative_margins') or 0)}."
        )
    return (
        f"{level_text}: stabil i {min_rounds} rundor "
        f"(rank_shift <= {rank_shift_tolerance:.3f}, "
        f"top1 >= {top1_lock_threshold * 100:.1f}%, "
        f"topK >= {topk_lock_threshold * 100:.1f}%, "
        f"margin > {margin_lock_threshold:.2f}). "
        f"Senaste: top1 {latest_top1 * 100:.1f}%, topK {latest_topk * 100:.1f}%, "
        f"margin {margin_text}.{robust_suffix}"
    )


def update_stability_locks_from_tool_ranking(
    *,
    lock_registry: dict[str, Any],
    tool_ranking_rows: list[dict[str, Any]] | None,
    captured_at: str | None = None,
    force_auto_lock: bool | None = None,
) -> dict[str, Any]:
    normalized = normalize_metadata_separation_lock_registry(lock_registry)
    cfg = dict(normalized.get("stability_config") or {})
    history_size = max(3, min(50, _as_int(cfg.get("history_size"), 12)))
    min_rounds = max(2, min(6, _as_int(cfg.get("min_rounds"), 2)))
    rank_shift_tolerance = max(0.0, float(cfg.get("rank_shift_tolerance") or 0.0))
    top1_lock_threshold = max(0.0, min(1.0, float(cfg.get("top1_lock_threshold") or 0.95)))
    top1_hard_lock_threshold = max(
        top1_lock_threshold,
        min(1.0, float(cfg.get("top1_hard_lock_threshold") or 1.0)),
    )
    topk_lock_threshold = max(0.0, min(1.0, float(cfg.get("topk_lock_threshold") or 1.0)))
    margin_lock_threshold = float(cfg.get("margin_lock_threshold") or 0.8)
    min_total_probes = max(1, _as_int(cfg.get("min_total_probes"), 100))
    min_probes_per_tool = max(1, _as_int(cfg.get("min_probes_per_tool"), 5))
    global_median_margin_threshold = float(
        cfg.get("global_median_margin_threshold") or 2.0
    )
    max_negative_margins = max(0, _as_int(cfg.get("max_negative_margins"), 1))
    global_rank_shift_tolerance = max(
        0.0,
        float(cfg.get("global_rank_shift_tolerance") or 0.0),
    )
    unlock_top1_drop_pp = max(
        0.0,
        min(1.0, float(cfg.get("unlock_top1_drop_pp") or 0.10)),
    )
    unlock_margin_negative_rounds = max(
        1,
        min(10, _as_int(cfg.get("unlock_margin_negative_rounds"), 2)),
    )
    now_iso = captured_at or datetime.now(timezone.utc).isoformat()
    stability_mode_enabled = bool(normalized.get("stability_lock_mode_enabled", True))
    auto_lock_enabled = (
        bool(force_auto_lock)
        if force_auto_lock is not None
        else bool(normalized.get("stability_auto_lock_enabled", True))
    )
    ranking_rows = list(tool_ranking_rows or [])
    ranking_map: dict[str, dict[str, Any]] = {}
    for raw in ranking_rows:
        if not isinstance(raw, dict):
            continue
        tool_id = _normalized_key(raw.get("tool_id"))
        if not tool_id:
            continue
        ranking_map[tool_id] = {
            "probes": max(0, _as_int(raw.get("probes"), 0)),
            "top1_rate": max(0.0, min(1.0, _as_float(raw.get("top1_rate"), 0.0))),
            "topk_rate": max(0.0, min(1.0, _as_float(raw.get("topk_rate"), 0.0))),
            "avg_margin": (
                float(raw.get("avg_margin_vs_best_other"))
                if isinstance(raw.get("avg_margin_vs_best_other"), (float, int))
                else None
            ),
            "avg_expected_rank": (
                float(raw.get("avg_expected_rank"))
                if isinstance(raw.get("avg_expected_rank"), (float, int))
                else None
            ),
        }

    history_map = {
        _normalized_key(item_id): list(samples)
        for item_id, samples in dict(normalized.get("stability_history") or {}).items()
        if _normalized_key(item_id)
    }
    lock_map: dict[tuple[str, str], dict[str, Any]] = {}
    for lock_item in list(normalized.get("stability_item_locks") or []):
        if not isinstance(lock_item, dict):
            continue
        layer = _normalized_key(lock_item.get("layer"))
        item_id = _normalized_key(lock_item.get("item_id"))
        if not layer or not item_id:
            continue
        lock_map[(layer, item_id)] = dict(lock_item)

    observed_ids = set(history_map.keys()) | set(ranking_map.keys())
    observed_ids.update(
        item_id
        for (layer, item_id), row in lock_map.items()
        if layer == "tool" and bool(row.get("locked"))
    )
    newly_locked: list[str] = []
    newly_unlocked: list[str] = []
    tool_snapshot_map: dict[str, dict[str, Any]] = {}

    for tool_id in sorted(observed_ids):
        history_rows = list(history_map.get(tool_id) or [])
        ranking_row = ranking_map.get(tool_id)
        if ranking_row is not None:
            history_rows.append(
                {
                    "captured_at": now_iso,
                    "probes": int(ranking_row.get("probes") or 0),
                    "top1_rate": float(ranking_row.get("top1_rate") or 0.0),
                    "topk_rate": float(ranking_row.get("topk_rate") or 0.0),
                    "avg_margin": ranking_row.get("avg_margin"),
                    "avg_expected_rank": ranking_row.get("avg_expected_rank"),
                }
            )
        if not history_rows:
            continue
        history_rows = history_rows[-history_size:]
        history_map[tool_id] = history_rows
        latest = history_rows[-1]
        latest_top1 = max(0.0, min(1.0, _as_float(latest.get("top1_rate"), 0.0)))
        latest_topk = max(0.0, min(1.0, _as_float(latest.get("topk_rate"), 0.0)))
        latest_margin = (
            float(latest.get("avg_margin"))
            if isinstance(latest.get("avg_margin"), (float, int))
            else None
        )
        recent_window = history_rows[-min_rounds:]
        rank_shifts: list[float] = []
        for index in range(1, len(recent_window)):
            left_rank = recent_window[index - 1].get("avg_expected_rank")
            right_rank = recent_window[index].get("avg_expected_rank")
            if isinstance(left_rank, (float, int)) and isinstance(right_rank, (float, int)):
                rank_shifts.append(abs(float(right_rank) - float(left_rank)))
            else:
                rank_shifts.append(float("inf"))
        probes_window_ok = len(recent_window) >= min_rounds and all(
            _as_int(sample.get("probes"), 0) >= min_probes_per_tool for sample in recent_window
        )
        rank_shift_ok = (
            len(recent_window) >= min_rounds
            and bool(rank_shifts)
            and all(shift <= rank_shift_tolerance for shift in rank_shifts)
        )
        top1_ok = len(recent_window) >= min_rounds and all(
            _as_float(sample.get("top1_rate"), 0.0) >= top1_lock_threshold
            for sample in recent_window
        )
        topk_ok = len(recent_window) >= min_rounds and all(
            _as_float(sample.get("topk_rate"), 0.0) >= (topk_lock_threshold - 1e-6)
            for sample in recent_window
        )
        margin_ok = len(recent_window) >= min_rounds and all(
            isinstance(sample.get("avg_margin"), (float, int))
            and float(sample.get("avg_margin")) > margin_lock_threshold
            for sample in recent_window
        )
        stable_candidate = probes_window_ok and rank_shift_ok and top1_ok and topk_ok and margin_ok
        tool_snapshot_map[tool_id] = {
            "tool_id": tool_id,
            "history_rows": history_rows,
            "recent_window": recent_window,
            "latest_probes": _as_int(latest.get("probes"), 0),
            "latest_top1": latest_top1,
            "latest_topk": latest_topk,
            "latest_margin": latest_margin,
            "latest_rank_shift": _stability_latest_rank_shift(history_rows),
            "stable_candidate": stable_candidate,
            "ranking_row_present": ranking_row is not None,
        }

    monitored_tools = len(tool_snapshot_map)
    latest_samples = list(tool_snapshot_map.values())
    total_probes_current = int(sum(item.get("latest_probes") or 0 for item in latest_samples))
    min_probes_current = (
        int(min(item.get("latest_probes") or 0 for item in latest_samples))
        if latest_samples
        else 0
    )
    current_margins = [
        float(item["latest_margin"])
        for item in latest_samples
        if isinstance(item.get("latest_margin"), (float, int))
    ]
    median_margin_current = float(median(current_margins)) if current_margins else None
    negative_margin_count = int(
        sum(
            1
            for item in latest_samples
            if isinstance(item.get("latest_margin"), (float, int))
            and float(item.get("latest_margin")) < 0
        )
    )
    rank_shift_values = [
        float(item["latest_rank_shift"])
        for item in latest_samples
        if isinstance(item.get("latest_rank_shift"), (float, int))
    ]
    max_rank_shift_current = max(rank_shift_values) if rank_shift_values else None
    robust_rank_shift_ok = bool(rank_shift_values) and all(
        value <= global_rank_shift_tolerance for value in rank_shift_values
    )
    robust_gate_blockers: list[str] = []
    if total_probes_current < min_total_probes:
        robust_gate_blockers.append(
            f"total_probes {total_probes_current} < {min_total_probes}"
        )
    if min_probes_current < min_probes_per_tool:
        robust_gate_blockers.append(
            f"min_probes_per_tool {min_probes_current} < {min_probes_per_tool}"
        )
    if median_margin_current is None:
        robust_gate_blockers.append("median_margin saknas")
    elif median_margin_current <= global_median_margin_threshold:
        robust_gate_blockers.append(
            f"median_margin {median_margin_current:.2f} <= {global_median_margin_threshold:.2f}"
        )
    if negative_margin_count > max_negative_margins:
        robust_gate_blockers.append(
            f"negative_margins {negative_margin_count} > {max_negative_margins}"
        )
    if not robust_rank_shift_ok:
        if max_rank_shift_current is None:
            robust_gate_blockers.append("rank_shift saknas för 2 rundor")
        else:
            robust_gate_blockers.append(
                f"rank_shift {max_rank_shift_current:.4f} > {global_rank_shift_tolerance:.4f}"
            )
    robust_gate_snapshot = {
        "total_probes": total_probes_current,
        "min_probes_per_tool": min_probes_current,
        "median_margin": median_margin_current,
        "negative_margins": negative_margin_count,
        "max_rank_shift": max_rank_shift_current,
    }
    robust_gate_requirements = {
        "min_total_probes": min_total_probes,
        "min_probes_per_tool": min_probes_per_tool,
        "rank_shift_tolerance": global_rank_shift_tolerance,
        "min_median_margin": global_median_margin_threshold,
        "max_negative_margins": max_negative_margins,
    }
    robust_gate_ready = len(robust_gate_blockers) == 0

    for tool_id in sorted(tool_snapshot_map.keys()):
        snapshot = tool_snapshot_map.get(tool_id) or {}
        latest_top1 = max(0.0, min(1.0, _as_float(snapshot.get("latest_top1"), 0.0)))
        latest_topk = max(0.0, min(1.0, _as_float(snapshot.get("latest_topk"), 0.0)))
        latest_margin = (
            float(snapshot.get("latest_margin"))
            if isinstance(snapshot.get("latest_margin"), (float, int))
            else None
        )
        history_rows = list(snapshot.get("history_rows") or [])
        recent_window = list(snapshot.get("recent_window") or [])
        lock_key = ("tool", tool_id)
        current_lock = dict(lock_map.get(lock_key) or {})
        is_locked = bool(current_lock.get("locked"))

        if is_locked:
            negative_margin_rounds = int(current_lock.get("negative_margin_rounds") or 0)
            if bool(snapshot.get("ranking_row_present")):
                if isinstance(latest_margin, (float, int)) and latest_margin < 0:
                    negative_margin_rounds += 1
                else:
                    negative_margin_rounds = 0
            baseline_top1 = (
                float(current_lock.get("baseline_top1_rate"))
                if isinstance(current_lock.get("baseline_top1_rate"), (float, int))
                else None
            )
            top1_drop_triggered = (
                isinstance(baseline_top1, (float, int))
                and (baseline_top1 - latest_top1) >= unlock_top1_drop_pp
            )
            margin_drop_triggered = negative_margin_rounds >= unlock_margin_negative_rounds
            if top1_drop_triggered or margin_drop_triggered:
                lock_map.pop(lock_key, None)
                newly_unlocked.append(tool_id)
                continue
            current_lock["top1_rate"] = latest_top1
            current_lock["topk_rate"] = latest_topk
            current_lock["avg_margin"] = latest_margin
            current_lock["last_rank_shift"] = _stability_latest_rank_shift(history_rows)
            current_lock["negative_margin_rounds"] = negative_margin_rounds
            current_lock["updated_at"] = now_iso
            lock_map[lock_key] = current_lock
            continue

        should_auto_lock = bool(
            stability_mode_enabled
            and auto_lock_enabled
            and robust_gate_ready
            and bool(snapshot.get("stable_candidate"))
        )
        if not should_auto_lock:
            continue
        hard_lock = all(
            _as_float(sample.get("top1_rate"), 0.0) >= top1_hard_lock_threshold
            for sample in recent_window
        )
        lock_payload = {
            "layer": "tool",
            "item_id": tool_id,
            "locked": True,
            "lock_level": "hard" if hard_lock else "soft",
            "lock_reason": _stability_lock_reason_text(
                min_rounds=min_rounds,
                rank_shift_tolerance=rank_shift_tolerance,
                top1_lock_threshold=top1_lock_threshold,
                topk_lock_threshold=topk_lock_threshold,
                margin_lock_threshold=margin_lock_threshold,
                latest_top1=latest_top1,
                latest_topk=latest_topk,
                latest_margin=latest_margin,
                hard_lock=hard_lock,
                robust_gate_snapshot=robust_gate_snapshot,
            ),
            "unlock_trigger": _stability_unlock_trigger_text(cfg),
            "source": "auto",
            "top1_rate": latest_top1,
            "topk_rate": latest_topk,
            "avg_margin": latest_margin,
            "last_rank_shift": _stability_latest_rank_shift(history_rows),
            "baseline_top1_rate": latest_top1,
            "baseline_margin": latest_margin,
            "negative_margin_rounds": 0,
            "locked_at": now_iso,
            "updated_at": now_iso,
        }
        lock_map[lock_key] = lock_payload
        newly_locked.append(tool_id)

    normalized_locks = sorted(
        lock_map.values(),
        key=lambda item: (item.get("layer") or "", item.get("item_id") or ""),
    )
    updated_registry = normalize_metadata_separation_lock_registry(
        {
            **normalized,
            "updated_at": now_iso,
            "stability_history": history_map,
            "stability_item_locks": normalized_locks,
        }
    )
    locked_tool_ids = sorted(
        {
            _normalized_key(item.get("item_id"))
            for item in list(updated_registry.get("stability_item_locks") or [])
            if _normalized_key(item.get("layer")) == "tool" and bool(item.get("locked"))
        }
    )
    changed = bool(newly_locked or newly_unlocked or bool(ranking_rows))
    return {
        "lock_registry": updated_registry,
        "changed": changed,
        "newly_locked": newly_locked,
        "newly_unlocked": newly_unlocked,
        "locked_tool_ids": locked_tool_ids,
        "monitored_tools": monitored_tools,
        "robust_gate_ready": robust_gate_ready,
        "robust_gate_blockers": robust_gate_blockers,
        "robust_gate_snapshot": robust_gate_snapshot,
        "robust_gate_requirements": robust_gate_requirements,
    }


def summarize_stability_item_locks(
    lock_registry: dict[str, Any],
    *,
    layer: str = "tool",
    include_unlocked: bool = False,
) -> list[dict[str, Any]]:
    normalized = normalize_metadata_separation_lock_registry(lock_registry)
    target_layer = _normalized_key(layer)
    rows: list[dict[str, Any]] = []
    for item in list(normalized.get("stability_item_locks") or []):
        if not isinstance(item, dict):
            continue
        if _normalized_key(item.get("layer")) != target_layer:
            continue
        is_locked = bool(item.get("locked"))
        if not is_locked and not include_unlocked:
            continue
        rows.append(
            {
                "layer": target_layer,
                "item_id": _normalized_key(item.get("item_id")),
                "locked": is_locked,
                "lock_level": _normalized_key(item.get("lock_level")) or "soft",
                "lock_reason": _normalize_text(item.get("lock_reason")) or None,
                "unlock_trigger": _normalize_text(item.get("unlock_trigger")) or None,
                "top1_rate": (
                    float(item.get("top1_rate"))
                    if isinstance(item.get("top1_rate"), (float, int))
                    else None
                ),
                "topk_rate": (
                    float(item.get("topk_rate"))
                    if isinstance(item.get("topk_rate"), (float, int))
                    else None
                ),
                "avg_margin": (
                    float(item.get("avg_margin"))
                    if isinstance(item.get("avg_margin"), (float, int))
                    else None
                ),
                "last_rank_shift": (
                    float(item.get("last_rank_shift"))
                    if isinstance(item.get("last_rank_shift"), (float, int))
                    else None
                ),
                "negative_margin_rounds": max(
                    0, _as_int(item.get("negative_margin_rounds"), 0)
                ),
                "locked_at": _normalize_text(item.get("locked_at")) or None,
                "updated_at": _normalize_text(item.get("updated_at")) or None,
            }
        )
    rows.sort(key=lambda item: item.get("item_id") or "")
    return rows


def get_stability_locked_item_ids(
    lock_registry: dict[str, Any],
    *,
    layer: str = "tool",
    respect_lock_mode: bool = True,
) -> set[str]:
    normalized = normalize_metadata_separation_lock_registry(lock_registry)
    if respect_lock_mode and not bool(normalized.get("stability_lock_mode_enabled", True)):
        return set()
    target_layer = _normalized_key(layer)
    locked_ids: set[str] = set()
    for item in list(normalized.get("stability_item_locks") or []):
        if not isinstance(item, dict):
            continue
        if _normalized_key(item.get("layer")) != target_layer:
            continue
        if not bool(item.get("locked")):
            continue
        item_id = _normalized_key(item.get("item_id"))
        if item_id:
            locked_ids.add(item_id)
    return locked_ids


def unlock_stability_item_locks(
    *,
    lock_registry: dict[str, Any],
    layer: str = "tool",
    item_ids: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_metadata_separation_lock_registry(lock_registry)
    target_layer = _normalized_key(layer)
    requested_ids = {
        _normalized_key(item_id)
        for item_id in list(item_ids or [])
        if _normalized_key(item_id)
    }
    now_iso = datetime.now(timezone.utc).isoformat()
    unlocked_ids: list[str] = []
    kept_items: list[dict[str, Any]] = []
    for item in list(normalized.get("stability_item_locks") or []):
        if not isinstance(item, dict):
            continue
        item_layer = _normalized_key(item.get("layer"))
        item_id = _normalized_key(item.get("item_id"))
        should_unlock = bool(item_layer == target_layer and bool(item.get("locked")))
        if should_unlock and requested_ids:
            should_unlock = item_id in requested_ids
        if should_unlock:
            unlocked_ids.append(item_id)
            continue
        kept_items.append(item)
    updated_registry = normalize_metadata_separation_lock_registry(
        {
            **normalized,
            "updated_at": now_iso,
            "stability_item_locks": kept_items,
        }
    )
    return {
        "lock_registry": updated_registry,
        "changed": bool(unlocked_ids),
        "unlocked_item_ids": sorted({item_id for item_id in unlocked_ids if item_id}),
        "reason": _normalize_text(reason) or None,
    }


async def filter_metadata_suggestions_with_pair_locks(
    *,
    pair_locks: list[dict[str, Any]],
    current_tool_map: dict[str, dict[str, Any]],
    current_intent_map: dict[str, dict[str, Any]],
    current_agent_map: dict[str, dict[str, Any]],
    tool_struct_map: dict[str, list[float] | None] | None = None,
    tool_suggestions: list[dict[str, Any]] | None = None,
    intent_suggestions: list[dict[str, Any]] | None = None,
    agent_suggestions: list[dict[str, Any]] | None = None,
    semantic_weight: float = 1.0,
    structural_weight: float = 0.0,
) -> dict[str, Any]:
    normalized = normalize_metadata_separation_lock_registry({"pair_locks": pair_locks})
    locks = list(normalized.get("pair_locks") or [])
    if not locks:
        return {
            "tool_suggestions": list(tool_suggestions or []),
            "intent_suggestions": list(intent_suggestions or []),
            "agent_suggestions": list(agent_suggestions or []),
            "rejections": {"tool": [], "intent": [], "agent": []},
        }

    lock_index: dict[str, list[dict[str, Any]]] = {"tool": [], "intent": [], "agent": []}
    for lock in locks:
        layer = _normalized_key(lock.get("layer"))
        if layer in lock_index:
            lock_index[layer].append(lock)

    tool_work_map: dict[str, dict[str, Any]] = {}
    for tool_id, payload in (current_tool_map or {}).items():
        key = _normalized_key(tool_id)
        if not key or not isinstance(payload, dict):
            continue
        tool_work_map[key] = _tool_metadata_payload_with_id(payload, tool_id=key)
    intent_work_map: dict[str, dict[str, Any]] = {}
    for intent_id, payload in (current_intent_map or {}).items():
        key = _normalized_key(intent_id)
        if not key or not isinstance(payload, dict):
            continue
        intent_work_map[key] = _intent_metadata_payload_with_id(payload, intent_id=key)
    agent_work_map: dict[str, dict[str, Any]] = {}
    for agent_id, payload in (current_agent_map or {}).items():
        key = _normalized_key(agent_id)
        if not key or not isinstance(payload, dict):
            continue
        agent_work_map[key] = _agent_metadata_payload_with_id(payload, agent_id=key)

    struct_map = {
        _normalized_key(tool_id): (list(values) if isinstance(values, list) else None)
        for tool_id, values in (tool_struct_map or {}).items()
        if _normalized_key(tool_id)
    }

    async def _tool_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
        left_id = _normalized_key(left.get("tool_id"))
        right_id = _normalized_key(right.get("tool_id"))
        sem_left = _embed_text(_tool_semantic_text(left))
        sem_right = _embed_text(_tool_semantic_text(right))
        struct_left = struct_map.get(left_id)
        struct_right = struct_map.get(right_id)
        return _fused_tool_similarity(
            left_sem=sem_left,
            left_struct=struct_left,
            right_sem=sem_right,
            right_struct=struct_right,
            semantic_weight=semantic_weight,
            structural_weight=structural_weight,
        )

    async def _intent_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
        sem_left = _embed_text(_intent_text(left))
        sem_right = _embed_text(_intent_text(right))
        return _cosine_similarity(sem_left, sem_right)

    async def _agent_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
        sem_left = _embed_text(_agent_text(left))
        sem_right = _embed_text(_agent_text(right))
        return _cosine_similarity(sem_left, sem_right)

    async def _filter_layer(
        *,
        layer: str,
        suggestions: list[dict[str, Any]] | None,
        item_id_field: str,
        current_map: dict[str, dict[str, Any]],
        payload_builder,
        similarity_fn,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        layer_locks = lock_index.get(layer) or []
        for row in suggestions or []:
            if not isinstance(row, dict):
                continue
            item_id = _normalized_key(row.get(item_id_field))
            if not item_id:
                continue
            proposed_meta = row.get("proposed_metadata")
            if not isinstance(proposed_meta, dict):
                accepted.append(row)
                continue
            existing = dict(current_map.get(item_id) or {})
            merged_payload = {**existing, **proposed_meta, item_id_field: item_id}
            candidate = payload_builder(merged_payload, **{item_id_field: item_id})
            violation: dict[str, Any] | None = None
            for lock in layer_locks:
                lock_item_a = _normalized_key(lock.get("item_a"))
                lock_item_b = _normalized_key(lock.get("item_b"))
                if item_id not in {lock_item_a, lock_item_b}:
                    continue
                competitor_id = lock_item_b if item_id == lock_item_a else lock_item_a
                competitor = current_map.get(competitor_id)
                if not isinstance(competitor, dict):
                    continue
                similarity = await similarity_fn(candidate, competitor)
                max_similarity = _as_float(lock.get("max_similarity"), 1.0)
                if similarity > (max_similarity + 1e-6):
                    violation = {
                        "item_id": item_id,
                        "competitor_id": competitor_id,
                        "similarity": float(similarity),
                        "max_similarity": float(max_similarity),
                    }
                    break
            if violation:
                rejected.append(violation)
                continue
            current_map[item_id] = candidate
            accepted.append(row)
        return accepted, rejected

    filtered_intent, rejected_intent = await _filter_layer(
        layer="intent",
        suggestions=intent_suggestions,
        item_id_field="intent_id",
        current_map=intent_work_map,
        payload_builder=_intent_metadata_payload_with_id,
        similarity_fn=_intent_similarity,
    )
    filtered_agent, rejected_agent = await _filter_layer(
        layer="agent",
        suggestions=agent_suggestions,
        item_id_field="agent_id",
        current_map=agent_work_map,
        payload_builder=_agent_metadata_payload_with_id,
        similarity_fn=_agent_similarity,
    )
    filtered_tool, rejected_tool = await _filter_layer(
        layer="tool",
        suggestions=tool_suggestions,
        item_id_field="tool_id",
        current_map=tool_work_map,
        payload_builder=_tool_metadata_payload_with_id,
        similarity_fn=_tool_similarity,
    )

    return {
        "tool_suggestions": filtered_tool,
        "intent_suggestions": filtered_intent,
        "agent_suggestions": filtered_agent,
        "rejections": {
            "tool": rejected_tool,
            "intent": rejected_intent,
            "agent": rejected_agent,
        },
    }
