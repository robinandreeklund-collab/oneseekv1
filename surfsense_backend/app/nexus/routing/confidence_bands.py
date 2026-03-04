"""Confidence Band Cascade — 5-band routing decision system.

Classifies routing decisions into bands based on calibrated confidence
scores and margin to runner-up, determining the appropriate routing
strategy for each query.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.nexus.config import BAND_THRESHOLDS


@dataclass
class BandClassification:
    """Result of band classification."""

    band: int  # 0-4
    band_name: str
    top_score: float
    margin: float
    action: str  # "direct" | "verify" | "top3_llm" | "decompose" | "ood"


# Band actions describe what the routing system should do
BAND_ACTIONS: dict[int, str] = {
    0: "direct",      # Direct route, no LLM needed
    1: "verify",      # Quick namespace verification, minimal LLM
    2: "top3_llm",    # Present top-3 candidates, LLM chooses
    3: "decompose",   # Decompose or reformulate the query
    4: "ood",         # OOD detection, generell fallback
}

BAND_NAMES: dict[int, str] = {
    0: "DIRECT",
    1: "VERIFY",
    2: "TOP-3 LLM",
    3: "DECOMPOSE",
    4: "OOD FALLBACK",
}


class ConfidenceBandCascade:
    """Classifies routing decisions into confidence bands.

    Band 0 [0.95-1.00]: Direct route, no LLM (target: >80% of queries)
    Band 1 [0.80-0.94]: Namespace verify, minimal LLM (~50ms)
    Band 2 [0.60-0.79]: Top-3 candidates, LLM chooses (~150ms)
    Band 3 [0.40-0.59]: Decompose or reformulate
    Band 4 [< 0.40]:   OOD detection → generell fallback
    """

    def __init__(
        self,
        band_0_min_score: float = BAND_THRESHOLDS.band_0_min_score,
        band_0_min_margin: float = BAND_THRESHOLDS.band_0_min_margin,
        band_1_min_score: float = BAND_THRESHOLDS.band_1_min_score,
        band_1_min_margin: float = BAND_THRESHOLDS.band_1_min_margin,
        band_2_min_score: float = BAND_THRESHOLDS.band_2_min_score,
        band_3_min_score: float = BAND_THRESHOLDS.band_3_min_score,
    ):
        self._b0_score = band_0_min_score
        self._b0_margin = band_0_min_margin
        self._b1_score = band_1_min_score
        self._b1_margin = band_1_min_margin
        self._b2_score = band_2_min_score
        self._b3_score = band_3_min_score

    def classify(
        self, top_score: float, second_score: float = 0.0
    ) -> BandClassification:
        """Classify a routing decision into a confidence band.

        Args:
            top_score: Calibrated score of the top-1 candidate.
            second_score: Calibrated score of the top-2 candidate.

        Returns:
            BandClassification with band number, name, and action.
        """
        margin = top_score - second_score

        # Band 0: Very high confidence with large margin
        if top_score >= self._b0_score and margin >= self._b0_margin:
            return BandClassification(
                band=0,
                band_name=BAND_NAMES[0],
                top_score=top_score,
                margin=margin,
                action=BAND_ACTIONS[0],
            )

        # Band 1: High confidence with reasonable margin
        if top_score >= self._b1_score and margin >= self._b1_margin:
            return BandClassification(
                band=1,
                band_name=BAND_NAMES[1],
                top_score=top_score,
                margin=margin,
                action=BAND_ACTIONS[1],
            )

        # Band 2: Medium confidence or tight race
        if top_score >= self._b2_score:
            return BandClassification(
                band=2,
                band_name=BAND_NAMES[2],
                top_score=top_score,
                margin=margin,
                action=BAND_ACTIONS[2],
            )

        # Band 3: Low confidence, might need decomposition
        if top_score >= self._b3_score:
            return BandClassification(
                band=3,
                band_name=BAND_NAMES[3],
                top_score=top_score,
                margin=margin,
                action=BAND_ACTIONS[3],
            )

        # Band 4: Very low — OOD
        return BandClassification(
            band=4,
            band_name=BAND_NAMES[4],
            top_score=top_score,
            margin=margin,
            action=BAND_ACTIONS[4],
        )

    def get_band_distribution(
        self, classifications: list[BandClassification]
    ) -> dict[int, int]:
        """Count the distribution of queries across bands."""
        dist: dict[int, int] = dict.fromkeys(range(5), 0)
        for c in classifications:
            dist[c.band] += 1
        return dist

    def compute_band0_rate(
        self, classifications: list[BandClassification]
    ) -> float:
        """Compute the Band-0 throughput rate (target: >80%)."""
        if not classifications:
            return 0.0
        band0_count = sum(1 for c in classifications if c.band == 0)
        return band0_count / len(classifications)
