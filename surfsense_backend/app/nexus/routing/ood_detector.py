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

    # ------------------------------------------------------------------
    # UAEval4RAG — 6 OOD Query Categories
    # ------------------------------------------------------------------

    def classify_ood_category(
        self,
        query: str,
        *,
        entities_locations: list[str] | None = None,
        entities_times: list[str] | None = None,
        zone_candidates: list[str] | None = None,
        tool_count: int = 0,
    ) -> str:
        """Classify an OOD query into one of 6 UAEval4RAG categories.

        Categories:
            no_tool: No matching tool exists in the system
            geo_scope: Query is outside geographic scope (e.g. "weather in Paris")
            temporal_scope: Query is outside temporal scope (e.g. "1987")
            ambiguous: Multiple interpretations possible
            conflicting: Contradictory requirements in query
            underspecified: Missing necessary information
        """
        import re

        query_lower = query.lower()
        locations = entities_locations or []
        _times = entities_times or []  # reserved for future temporal analysis
        zones = zone_candidates or []

        # no_tool: No candidates found at all
        if tool_count == 0 and not zones:
            return "no_tool"

        # geo_scope: Foreign locations detected
        foreign_indicators = [
            "paris",
            "london",
            "berlin",
            "new york",
            "tokyo",
            "los angeles",
            "madrid",
            "rom",
            "amsterdam",
            "bangkok",
            "dubai",
            "sydney",
            "europa",
            "asien",
            "afrika",
            "usa",
            "kina",
            "japan",
            "indien",
            "utomlands",
            "internationell",
        ]
        for loc in locations:
            if loc.lower() in foreign_indicators:
                return "geo_scope"
        for word in foreign_indicators:
            if word in query_lower:
                return "geo_scope"

        # temporal_scope: Historical or far-future dates
        year_match = re.search(r"\b(1[89]\d{2}|20[0-1]\d)\b", query_lower)
        if year_match:
            year = int(year_match.group(1))
            if year < 2020:
                return "temporal_scope"
        historical_words = ["historisk", "förr", "1900-tal", "medeltid", "antiken"]
        if any(w in query_lower for w in historical_words):
            return "temporal_scope"

        # conflicting: Contradictory signals
        if len(zones) >= 2 and zones[0] != zones[1]:
            conflict_pairs = [
                ("jämför", "skapa"),
                ("sök", "generera"),
                ("statistik", "karta"),
                ("väder", "bolag"),
            ]
            for a, b in conflict_pairs:
                if a in query_lower and b in query_lower:
                    return "conflicting"

        # ambiguous: Multiple possible interpretations
        ambig_words = [
            "det",
            "den",
            "saker",
            "grejer",
            "information",
            "data",
            "hjälp",
            "visa",
        ]
        if len(query_lower.split()) <= 3 and any(
            w in query_lower.split() for w in ambig_words
        ):
            return "ambiguous"

        # underspecified: Too vague or missing key info
        if len(query_lower.split()) <= 2:
            return "underspecified"
        vague_patterns = ["hur gör man", "berätta om", "vad finns det"]
        if any(p in query_lower for p in vague_patterns):
            return "underspecified"

        return "no_tool"

    # ------------------------------------------------------------------
    # Dark Matter Clustering (DBSCAN when embeddings available)
    # ------------------------------------------------------------------

    def cluster_dark_matter(
        self,
        ood_queries: list[dict],
        *,
        embeddings: list[list[float]] | None = None,
    ) -> list[dict]:
        """Cluster OOD queries using DBSCAN on embeddings when available,
        falling back to keyword grouping otherwise.
        """
        if not ood_queries or len(ood_queries) < 3:
            return []

        if embeddings and len(embeddings) == len(ood_queries):
            return self._cluster_dbscan(ood_queries, embeddings)

        return self._cluster_keywords(ood_queries)

    def _cluster_dbscan(
        self,
        ood_queries: list[dict],
        embeddings: list[list[float]],
    ) -> list[dict]:
        """Cluster using DBSCAN on embedding vectors."""
        try:
            from sklearn.cluster import DBSCAN
        except ImportError:
            logger.info(
                "scikit-learn not installed, falling back to keyword clustering"
            )
            return self._cluster_keywords(ood_queries)

        arr = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        arr_norm = arr / norms

        clustering = DBSCAN(eps=0.3, min_samples=2, metric="cosine").fit(arr_norm)
        labels = clustering.labels_

        cluster_map: dict[int, list[dict]] = {}
        for i, label in enumerate(labels):
            if label == -1:
                continue
            cluster_map.setdefault(label, []).append(ood_queries[i])

        clusters: list[dict] = []
        for cluster_id, queries in sorted(
            cluster_map.items(), key=lambda x: len(x[1]), reverse=True
        ):
            sample_texts = [q.get("query_text", "") for q in queries[:5]]
            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "query_count": len(queries),
                    "sample_queries": sample_texts,
                    "suggested_tool": None,
                    "reviewed": False,
                }
            )
            if len(clusters) >= 20:
                break

        return clusters

    def _cluster_keywords(self, ood_queries: list[dict]) -> list[dict]:
        """Fallback clustering by shared keywords."""
        keyword_groups: dict[str, list[dict]] = {}
        for q in ood_queries:
            text = q.get("query_text", "").lower()
            tokens = set(text.split())
            for token in tokens:
                if len(token) > 3:
                    keyword_groups.setdefault(token, []).append(q)
                    break

        clusters: list[dict] = []
        cluster_id = 0
        seen_queries: set[str] = set()

        for _keyword, queries in sorted(
            keyword_groups.items(), key=lambda x: len(x[1]), reverse=True
        ):
            unique_queries = [
                q for q in queries if q.get("query_text", "") not in seen_queries
            ]
            if len(unique_queries) < 2:
                continue

            sample_texts = [q.get("query_text", "") for q in unique_queries[:5]]
            for text in sample_texts:
                seen_queries.add(text)

            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "query_count": len(unique_queries),
                    "sample_queries": sample_texts,
                    "suggested_tool": None,
                    "reviewed": False,
                }
            )
            cluster_id += 1

            if cluster_id >= 20:
                break

        return clusters
