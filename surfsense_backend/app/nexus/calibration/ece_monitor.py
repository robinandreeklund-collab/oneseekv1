"""ECE Monitor — Expected Calibration Error tracking per zone.

Measures how well-calibrated confidence scores are: a confidence of 0.80
should mean the prediction is correct ~80% of the time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default number of bins for ECE computation
DEFAULT_N_BINS: int = 10


@dataclass
class ECEBin:
    """A single calibration bin."""

    bin_lower: float
    bin_upper: float
    avg_confidence: float = 0.0
    avg_accuracy: float = 0.0
    count: int = 0
    gap: float = 0.0  # |avg_confidence - avg_accuracy|


@dataclass
class ECEResult:
    """Result of ECE computation."""

    ece: float
    bins: list[ECEBin] = field(default_factory=list)
    total_samples: int = 0
    max_calibration_error: float = 0.0  # worst single bin gap
    underconfident_bins: int = 0  # bins where accuracy > confidence
    overconfident_bins: int = 0  # bins where confidence > accuracy


def compute_ece(
    confidences: list[float],
    correct: list[bool],
    *,
    n_bins: int = DEFAULT_N_BINS,
) -> ECEResult:
    """Compute Expected Calibration Error.

    ECE = sum_b (|B_b| / N) * |acc(B_b) - conf(B_b)|

    Where B_b is the set of predictions in bin b, acc is accuracy,
    and conf is average confidence.

    Args:
        confidences: Predicted confidence scores (0-1).
        correct: Whether each prediction was correct.
        n_bins: Number of equal-width bins.

    Returns:
        ECEResult with per-bin details.
    """
    if not confidences or len(confidences) != len(correct):
        return ECEResult(ece=0.0)

    n = len(confidences)
    bins: list[ECEBin] = []
    total_ece = 0.0
    max_gap = 0.0
    underconfident = 0
    overconfident = 0

    for i in range(n_bins):
        lower = i / n_bins
        upper = (i + 1) / n_bins

        # Collect samples in this bin
        bin_confs: list[float] = []
        bin_correct: list[bool] = []

        for conf, is_correct in zip(confidences, correct, strict=False):
            if lower <= conf < upper or (i == n_bins - 1 and conf == upper):
                bin_confs.append(conf)
                bin_correct.append(is_correct)

        if not bin_confs:
            bins.append(ECEBin(bin_lower=lower, bin_upper=upper))
            continue

        avg_conf = sum(bin_confs) / len(bin_confs)
        avg_acc = sum(1.0 for c in bin_correct if c) / len(bin_correct)
        gap = abs(avg_conf - avg_acc)
        weight = len(bin_confs) / n

        total_ece += weight * gap
        max_gap = max(max_gap, gap)

        if avg_acc > avg_conf:
            underconfident += 1
        elif avg_conf > avg_acc:
            overconfident += 1

        bins.append(
            ECEBin(
                bin_lower=lower,
                bin_upper=upper,
                avg_confidence=avg_conf,
                avg_accuracy=avg_acc,
                count=len(bin_confs),
                gap=gap,
            )
        )

    return ECEResult(
        ece=total_ece,
        bins=bins,
        total_samples=n,
        max_calibration_error=max_gap,
        underconfident_bins=underconfident,
        overconfident_bins=overconfident,
    )


def compute_ece_per_zone(
    zone_data: dict[str, tuple[list[float], list[bool]]],
    *,
    n_bins: int = DEFAULT_N_BINS,
) -> dict[str, ECEResult]:
    """Compute ECE separately for each zone.

    Args:
        zone_data: Dict mapping zone name → (confidences, correct).
        n_bins: Number of calibration bins.

    Returns:
        Dict mapping zone name → ECEResult.
    """
    results: dict[str, ECEResult] = {}
    for zone, (confs, correct) in zone_data.items():
        results[zone] = compute_ece(confs, correct, n_bins=n_bins)
    return results


def check_ece_targets(
    ece_by_zone: dict[str, ECEResult],
    *,
    target_band_01: float = 0.05,
    target_band_2: float = 0.10,
) -> dict[str, dict]:
    """Check whether ECE values meet targets.

    Args:
        ece_by_zone: ECE results per zone.
        target_band_01: Target ECE for bands 0-1.
        target_band_2: Target ECE for band 2.

    Returns:
        Dict with pass/fail status per zone.
    """
    status: dict[str, dict] = {}
    for zone, result in ece_by_zone.items():
        status[zone] = {
            "ece": result.ece,
            "meets_band_01_target": result.ece <= target_band_01,
            "meets_band_2_target": result.ece <= target_band_2,
            "max_gap": result.max_calibration_error,
            "total_samples": result.total_samples,
        }
    return status
