"""DATS — Distance-Aware Temperature Scaling per zone.

Per-zone temperature calibration that adjusts confidence based on
how far a query is from the zone centroid. Queries near the centroid
get sharper (lower temperature) scaling; queries at the periphery
get flatter (higher temperature) scaling.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ZoneTemperature:
    """Temperature parameters for a single zone."""

    zone: str
    base_temperature: float = 1.0
    distance_weight: float = 0.5
    min_temperature: float = 0.5
    max_temperature: float = 3.0
    fitted: bool = False


@dataclass
class DATSResult:
    """Result of DATS calibration."""

    original_score: float
    calibrated_score: float
    temperature: float
    distance_to_centroid: float
    zone: str


class ZonalTemperatureScaler:
    """Distance-Aware Temperature Scaling.

    For each zone, maintains a temperature that varies with the query's
    distance to the zone centroid:

        T(d) = base_T + weight * d
        p_calibrated = softmax(logit / T(d))

    Where d is the L2 distance from query embedding to zone centroid.
    """

    def __init__(self):
        self._zone_temps: dict[str, ZoneTemperature] = {}

    def set_zone_temperature(self, zone: str, params: ZoneTemperature) -> None:
        """Set or update temperature parameters for a zone."""
        self._zone_temps[zone] = params

    def get_zone_temperature(self, zone: str) -> ZoneTemperature:
        """Get temperature parameters for a zone (default if not set)."""
        return self._zone_temps.get(zone, ZoneTemperature(zone=zone))

    def compute_temperature(self, zone: str, distance_to_centroid: float) -> float:
        """Compute effective temperature for a query at given distance.

        Args:
            zone: The embedding zone.
            distance_to_centroid: L2 distance from query to zone centroid.

        Returns:
            Effective temperature (clamped to [min_temp, max_temp]).
        """
        params = self.get_zone_temperature(zone)
        raw_temp = (
            params.base_temperature + params.distance_weight * distance_to_centroid
        )
        return max(params.min_temperature, min(params.max_temperature, raw_temp))

    def calibrate(
        self,
        score: float,
        zone: str,
        distance_to_centroid: float,
    ) -> DATSResult:
        """Apply distance-aware temperature scaling to a score.

        Args:
            score: Raw reranker score (typically 0-1 from cross-encoder).
            zone: The embedding zone.
            distance_to_centroid: L2 distance from query to zone centroid.

        Returns:
            DATSResult with calibrated score and metadata.
        """
        temperature = self.compute_temperature(zone, distance_to_centroid)

        # Apply temperature scaling via sigmoid
        # Convert score to logit, scale by temperature, convert back
        if score <= 0.0:
            calibrated = 0.0
        elif score >= 1.0:
            calibrated = 1.0
        else:
            logit = math.log(score / (1.0 - score))
            scaled_logit = logit / temperature
            calibrated = 1.0 / (1.0 + math.exp(-scaled_logit))

        return DATSResult(
            original_score=score,
            calibrated_score=calibrated,
            temperature=temperature,
            distance_to_centroid=distance_to_centroid,
            zone=zone,
        )

    def calibrate_batch(
        self,
        scores: list[float],
        zone: str,
        distance_to_centroid: float,
    ) -> list[DATSResult]:
        """Calibrate a batch of scores for the same zone/distance."""
        return [self.calibrate(s, zone, distance_to_centroid) for s in scores]

    def fit_from_data(
        self,
        zone: str,
        scores: list[float],
        labels: list[int],
        distances: list[float],
    ) -> ZoneTemperature:
        """Fit temperature parameters from labeled data.

        Simple grid search over base_temperature and distance_weight
        to minimize calibration error.

        Args:
            zone: Zone to fit.
            scores: Predicted scores.
            labels: Binary ground truth (0/1).
            distances: Distance to centroid for each sample.

        Returns:
            Fitted ZoneTemperature parameters.
        """
        if len(scores) < 10:
            logger.warning(
                "Too few samples (%d) to fit DATS for zone %s", len(scores), zone
            )
            return self.get_zone_temperature(zone)

        best_params = ZoneTemperature(zone=zone)
        best_error = float("inf")

        for base_t in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
            for d_weight in [0.0, 0.2, 0.5, 0.8, 1.0]:
                params = ZoneTemperature(
                    zone=zone,
                    base_temperature=base_t,
                    distance_weight=d_weight,
                    fitted=True,
                )
                self._zone_temps[zone] = params

                # Compute ECE-like error
                error = 0.0
                for s, label, dist in zip(scores, labels, distances, strict=False):
                    result = self.calibrate(s, zone, dist)
                    error += (result.calibrated_score - label) ** 2
                error /= len(scores)

                if error < best_error:
                    best_error = error
                    best_params = params

        self._zone_temps[zone] = best_params
        logger.info(
            "DATS fit for %s: base_T=%.2f, d_weight=%.2f, MSE=%.4f",
            zone,
            best_params.base_temperature,
            best_params.distance_weight,
            best_error,
        )
        return best_params
