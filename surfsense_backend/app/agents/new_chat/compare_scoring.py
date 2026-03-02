"""Confidence-weighted scoring and ranking for compare mode.

Extracted from compare_executor.py (KQ-06) to keep modules focused.
"""

from __future__ import annotations

from typing import Any

# Weights: korrekthet (accuracy) is most important, then relevans, then
# djup and klarhet equally.  These can be tuned dynamically in the future.
CRITERION_WEIGHTS: dict[str, float] = {
    "korrekthet": 0.35,
    "relevans": 0.25,
    "djup": 0.20,
    "klarhet": 0.20,
}


def compute_weighted_score(scores: dict[str, int | float]) -> float:
    """Compute confidence-weighted final score from per-criterion scores.

    Returns a score 0-100 (weighted average).
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for criterion, weight in CRITERION_WEIGHTS.items():
        value = scores.get(criterion, 0)
        if isinstance(value, (int, float)):
            weighted_sum += weight * float(value)
            total_weight += weight
    if total_weight == 0.0:
        return 0.0
    return round(weighted_sum / total_weight, 1)


def rank_models_by_weighted_score(
    model_scores: dict[str, dict[str, int | float]],
) -> list[dict[str, Any]]:
    """Rank models by weighted score. Returns sorted list of dicts.

    Each entry: {"domain": "grok", "weighted_score": 82.5, "rank": 1,
                 "scores": {...}, "raw_total": 316}
    """
    ranked: list[dict[str, Any]] = []
    for domain, scores in model_scores.items():
        if domain == "research":
            continue  # Skip research agent from ranking
        if not isinstance(scores, dict):
            continue
        weighted = compute_weighted_score(scores)
        raw_total = sum(
            int(v) for v in scores.values() if isinstance(v, (int, float))
        )
        ranked.append({
            "domain": domain,
            "weighted_score": weighted,
            "raw_total": raw_total,
            "scores": scores,
        })
    ranked.sort(key=lambda x: x["weighted_score"], reverse=True)
    for i, entry in enumerate(ranked):
        entry["rank"] = i + 1
    return ranked
