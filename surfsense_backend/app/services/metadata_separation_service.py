from __future__ import annotations

import asyncio
import hashlib
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
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
    global_pass = nearest_new <= global_limit and alignment_new >= (
        alignment_old - cfg.alignment_drop_max
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
        if not unstable:
            stage_report["locked"] = True
            stage_report["skipped_reason"] = "Inga instabila kandidater i lagret."
            stage_report["mini_audit_summary"] = before_summary
            return stage_report, (perf_counter() - stage_started_at) * 1000

        components = _conflict_components(layer_stats=layer_stats)
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
        stage_report["notes"].extend(upstream_notes)

        locked = bool(metric_ok and upstream_ok)
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
    return {
        "baseline_summary": dict(baseline_result.get("summary") or {}),
        "final_summary": dict(final_audit.get("summary") or {}),
        "stage_reports": stage_reports,
        "proposed_tool_metadata_patch": list(current_tool_patch_map.values()),
        "proposed_intent_metadata_patch": list(current_intent_patch_map.values()),
        "proposed_agent_metadata_patch": list(current_agent_patch_map.values()),
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
