"""Platt Scaling — sigmoid calibration for reranker scores.

Transforms raw cross-encoder scores into calibrated probabilities so that
a score of 0.83 means actual accuracy of 83%.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from app.nexus.config import PLATT_DEFAULT_A, PLATT_DEFAULT_B

logger = logging.getLogger(__name__)


@dataclass
class PlattParams:
    """Fitted Platt scaling parameters."""

    a: float = PLATT_DEFAULT_A
    b: float = PLATT_DEFAULT_B
    fitted: bool = False
    n_samples: int = 0


class PlattCalibratedReranker:
    """Platt scaling: transforms raw retrieval-scores to calibrated probs.

    Usage:
        scaler = PlattCalibratedReranker()
        scaler.fit(raw_scores=[0.9, 0.7, 0.3, ...], labels=[1, 1, 0, ...])
        calibrated = scaler.calibrate(0.85)  # → actual probability
    """

    def __init__(self, params: PlattParams | None = None):
        self.params = params or PlattParams()

    def fit(self, raw_scores: list[float], labels: list[int]) -> PlattParams:
        """Fit Platt sigmoid on (raw_score → correct/incorrect) pairs.

        Args:
            raw_scores: Raw reranker output scores.
            labels: 1 = correct tool selected, 0 = wrong tool.

        Returns:
            Fitted PlattParams.
        """
        scores_arr = np.array(raw_scores, dtype=np.float64)
        labels_arr = np.array(labels, dtype=np.float64)

        if len(scores_arr) < 10:
            logger.warning(
                "Platt fit requires at least 10 samples, got %d. Using defaults.",
                len(scores_arr),
            )
            return self.params

        def negative_log_likelihood(params: np.ndarray) -> float:
            a, b = params
            probs = 1.0 / (1.0 + np.exp(a * scores_arr + b))
            probs = np.clip(probs, 1e-7, 1.0 - 1e-7)
            return -float(
                np.mean(
                    labels_arr * np.log(probs)
                    + (1.0 - labels_arr) * np.log(1.0 - probs)
                )
            )

        result = minimize(
            negative_log_likelihood,
            x0=np.array([PLATT_DEFAULT_A, PLATT_DEFAULT_B]),
            method="L-BFGS-B",
        )

        self.params = PlattParams(
            a=float(result.x[0]),
            b=float(result.x[1]),
            fitted=True,
            n_samples=len(scores_arr),
        )

        logger.info(
            "Platt calibration fitted: A=%.4f, B=%.4f on %d samples",
            self.params.a,
            self.params.b,
            self.params.n_samples,
        )

        return self.params

    def calibrate(self, raw_score: float) -> float:
        """Transform a raw reranker score into a calibrated probability."""
        return float(
            1.0 / (1.0 + np.exp(self.params.a * raw_score + self.params.b))
        )

    def calibrate_batch(self, raw_scores: list[float]) -> list[float]:
        """Calibrate a batch of scores."""
        arr = np.array(raw_scores, dtype=np.float64)
        calibrated = 1.0 / (1.0 + np.exp(self.params.a * arr + self.params.b))
        return calibrated.tolist()

    @property
    def is_fitted(self) -> bool:
        return self.params.fitted
