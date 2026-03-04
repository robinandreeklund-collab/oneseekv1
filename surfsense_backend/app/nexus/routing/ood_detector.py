"""OOD Detection — Energy Score + KNN backup gate.

Detects out-of-distribution queries ("dark matter") that don't match
any known tool zone. Uses energy-based scoring as primary method
and KNN distance as backup for borderline cases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from app.nexus.config import (
    OOD_ENERGY_BORDERLINE_FACTOR,
    OOD_ENERGY_THRESHOLD,
    OOD_KNN_K,
    OOD_KNN_THRESHOLD,
)

logger = logging.getLogger(__name__)


@dataclass
class OODResult:
    """Result of OOD detection."""

    is_ood: bool
    method: str | None = None  # "energy" | "knn" | None
    energy_score: float = 0.0
    knn_distance: float | None = None
    nearest_zone: str | None = None


class DarkMatterDetector:
    """Energy-based OOD detection — no distributional assumptions.

    Lower energy = more in-distribution (known query type).
    Recommended in ACM CSUR 2025 as primary method for production.

    Dual-gate approach:
        1. Energy score (primary) — fast, threshold-based
        2. KNN distance (backup) — for borderline energy scores
    """

    def __init__(
        self,
        energy_threshold: float = OOD_ENERGY_THRESHOLD,
        knn_k: int = OOD_KNN_K,
        knn_threshold: float = OOD_KNN_THRESHOLD,
    ):
        self.energy_threshold = energy_threshold
        self.knn_k = knn_k
        self.knn_threshold = knn_threshold
        self._knn_index = None  # FAISS index, built lazily
        self._knn_embeddings: np.ndarray | None = None

    def build_knn_index(self, embeddings: list[list[float]]) -> None:
        """Build a FAISS KNN index from known query embeddings.

        Args:
            embeddings: List of embedding vectors from known-good queries.
        """
        try:
            import faiss
        except ImportError:
            logger.warning("faiss-cpu not installed. KNN backup gate disabled.")
            return

        arr = np.array(embeddings, dtype=np.float32)
        if arr.shape[0] == 0:
            logger.warning("No embeddings provided for KNN index.")
            return

        dim = arr.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(arr)
        self._knn_index = index
        self._knn_embeddings = arr
        logger.info("KNN index built with %d vectors, dim=%d", arr.shape[0], dim)

    def energy_score(self, route_logits: np.ndarray, temperature: float = 1.0) -> float:
        """Compute energy score from route logits.

        Lower score = well-known query type.
        Higher score (above threshold) = OOD.

        Args:
            route_logits: Raw scores from routing candidates.
            temperature: Temperature parameter (default 1.0).

        Returns:
            Energy score (negative; more negative = more in-distribution).
        """
        logits = np.array(route_logits, dtype=np.float64)
        if logits.size == 0:
            return 0.0
        # Clip to prevent overflow
        logits = np.clip(logits / temperature, -50, 50)
        return float(-temperature * np.log(np.sum(np.exp(logits))))

    def knn_score(self, query_embedding: np.ndarray) -> float | None:
        """Compute KNN distance — distance to k-th nearest training query.

        Args:
            query_embedding: Query embedding vector.

        Returns:
            Distance to k-th nearest neighbor, or None if index not built.
        """
        if self._knn_index is None:
            return None

        emb = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
        distances, _ = self._knn_index.search(emb, self.knn_k)
        # Return distance to k-th nearest (last in the sorted list)
        return float(distances[0][-1])

    def detect(
        self,
        route_logits: np.ndarray,
        query_embedding: np.ndarray | None = None,
        nearest_zone: str | None = None,
    ) -> OODResult:
        """Full OOD detection with dual-gate approach.

        Gate 1: Energy score (always runs)
        Gate 2: KNN distance (runs only if energy is borderline)

        Args:
            route_logits: Raw scores from routing candidates.
            query_embedding: Optional query embedding for KNN gate.
            nearest_zone: Optional name of the nearest zone.

        Returns:
            OODResult with detection outcome.
        """
        energy = self.energy_score(route_logits)

        # Gate 1: Clear OOD
        if energy > self.energy_threshold:
            return OODResult(
                is_ood=True,
                method="energy",
                energy_score=energy,
                nearest_zone=nearest_zone,
            )

        # Gate 2: Borderline — use KNN as backup
        borderline_threshold = self.energy_threshold * OOD_ENERGY_BORDERLINE_FACTOR
        if energy > borderline_threshold and query_embedding is not None:
            knn_dist = self.knn_score(query_embedding)
            if knn_dist is not None and knn_dist > self.knn_threshold:
                return OODResult(
                    is_ood=True,
                    method="knn",
                    energy_score=energy,
                    knn_distance=knn_dist,
                    nearest_zone=nearest_zone,
                )

        # In-distribution
        return OODResult(
            is_ood=False,
            energy_score=energy,
            nearest_zone=nearest_zone,
        )

    @property
    def has_knn_index(self) -> bool:
        return self._knn_index is not None
