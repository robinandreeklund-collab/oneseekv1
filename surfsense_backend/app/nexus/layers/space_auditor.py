"""Space Auditor — Layer 1: Embedding-space visualization & health.

Continuously measures how well-separated tools, intents, and agents are
in the vector space. Computes UMAP 2D projections, silhouette scores,
confusion pairs, and hubness detection.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ToolPoint:
    """A single tool's embedding point for space analysis."""

    tool_id: str
    namespace: str
    zone: str
    embedding: list[float]


@dataclass
class ConfusionPair:
    """Two tools that are dangerously close in embedding space."""

    tool_a: str
    tool_b: str
    similarity: float
    zone_a: str = ""
    zone_b: str = ""
    is_cross_zone: bool = False


@dataclass
class HubnessAlert:
    """A tool that appears too often as nearest neighbor."""

    tool_id: str
    zone: str
    times_as_nn: int
    expected_rate: float
    actual_rate: float


@dataclass
class UMAPPoint:
    """A 2D UMAP projection point."""

    tool_id: str
    x: float
    y: float
    zone: str
    cluster_label: int = -1


@dataclass
class SeparationReport:
    """Full space auditor report."""

    global_silhouette: float
    per_zone_silhouette: dict[str, float] = field(default_factory=dict)
    confusion_pairs: list[ConfusionPair] = field(default_factory=list)
    hubness_alerts: list[HubnessAlert] = field(default_factory=list)
    umap_points: list[UMAPPoint] = field(default_factory=list)
    total_tools: int = 0
    inter_zone_distances: dict[str, float] = field(default_factory=dict)


def _cosine_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity matrix."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    # Avoid division by zero
    norms = np.maximum(norms, 1e-10)
    normalized = embeddings / norms
    return normalized @ normalized.T


def _silhouette_score_simple(
    embeddings: np.ndarray,
    labels: list[str],
) -> float:
    """Compute silhouette score without sklearn dependency.

    For each point:
      a(i) = mean distance to same-cluster points
      b(i) = min mean distance to any other cluster
      s(i) = (b(i) - a(i)) / max(a(i), b(i))

    Returns mean s(i).
    """
    n = len(labels)
    if n < 2:
        return 0.0

    unique_labels = list(set(labels))
    if len(unique_labels) < 2:
        return 0.0

    # Compute pairwise distances (1 - cosine similarity)
    sim_matrix = _cosine_similarity_matrix(embeddings)
    dist_matrix = 1.0 - sim_matrix

    label_indices: dict[str, list[int]] = {}
    for i, label in enumerate(labels):
        label_indices.setdefault(label, []).append(i)

    scores: list[float] = []
    for i in range(n):
        my_label = labels[i]
        same_cluster = [j for j in label_indices[my_label] if j != i]

        if not same_cluster:
            scores.append(0.0)
            continue

        # a(i): mean distance to same-cluster points
        a_i = float(np.mean([dist_matrix[i, j] for j in same_cluster]))

        # b(i): min mean distance to any other cluster
        b_i = float("inf")
        for other_label in unique_labels:
            if other_label == my_label:
                continue
            other_indices = label_indices[other_label]
            if not other_indices:
                continue
            mean_dist = float(np.mean([dist_matrix[i, j] for j in other_indices]))
            b_i = min(b_i, mean_dist)

        if b_i == float("inf"):
            scores.append(0.0)
        else:
            denom = max(a_i, b_i)
            scores.append((b_i - a_i) / denom if denom > 0 else 0.0)

    return float(np.mean(scores))


class SpaceAuditor:
    """Layer 1: Embedding-space health monitoring.

    Provides:
    - Separation matrix (silhouette scores per zone)
    - Confusion pair detection (tools that are too similar)
    - Hubness detection (tools that dominate NN results)
    - UMAP 2D projections for visualization
    """

    def __init__(
        self,
        confusion_threshold: float = 0.85,
        hubness_threshold: float = 0.08,
    ):
        self.confusion_threshold = confusion_threshold
        self.hubness_threshold = hubness_threshold

    def compute_separation_matrix(
        self, tools: list[ToolPoint]
    ) -> SeparationReport:
        """Compute full separation analysis.

        Args:
            tools: List of tool points with embeddings.

        Returns:
            SeparationReport with all metrics.
        """
        if len(tools) < 2:
            return SeparationReport(global_silhouette=0.0, total_tools=len(tools))

        embeddings = np.array([t.embedding for t in tools], dtype=np.float32)
        zones = [t.zone for t in tools]

        # Global silhouette
        global_sil = _silhouette_score_simple(embeddings, zones)

        # Per-zone silhouette (zone as label within global space)
        per_zone = self._per_zone_silhouette(embeddings, tools)

        # Confusion pairs
        confusion_pairs = self._find_confusion_pairs(embeddings, tools)

        # Hubness detection
        hubness_alerts = self._detect_hubness(embeddings, tools)

        # Inter-zone distances
        inter_zone = self._compute_inter_zone_distances(embeddings, tools)

        # UMAP projection (if umap-learn is available)
        umap_points = self._compute_umap(embeddings, tools)

        return SeparationReport(
            global_silhouette=global_sil,
            per_zone_silhouette=per_zone,
            confusion_pairs=confusion_pairs,
            hubness_alerts=hubness_alerts,
            umap_points=umap_points,
            total_tools=len(tools),
            inter_zone_distances=inter_zone,
        )

    def _per_zone_silhouette(
        self,
        embeddings: np.ndarray,
        tools: list[ToolPoint],
    ) -> dict[str, float]:
        """Compute silhouette score grouped by zone."""
        zones = list({t.zone for t in tools})
        result: dict[str, float] = {}

        for zone in zones:
            zone_mask = [i for i, t in enumerate(tools) if t.zone == zone]
            if len(zone_mask) < 2:
                result[zone] = 0.0
                continue

            zone_embeddings = embeddings[zone_mask]
            zone_namespaces = [tools[i].namespace for i in zone_mask]

            if len(set(zone_namespaces)) < 2:
                result[zone] = 1.0  # Single namespace = perfect separation
                continue

            result[zone] = _silhouette_score_simple(zone_embeddings, zone_namespaces)

        return result

    def _find_confusion_pairs(
        self,
        embeddings: np.ndarray,
        tools: list[ToolPoint],
    ) -> list[ConfusionPair]:
        """Find tool pairs that are dangerously similar."""
        sim_matrix = _cosine_similarity_matrix(embeddings)
        pairs: list[ConfusionPair] = []

        for i in range(len(tools)):
            for j in range(i + 1, len(tools)):
                sim = float(sim_matrix[i, j])
                if sim >= self.confusion_threshold and tools[i].namespace != tools[j].namespace:
                        pairs.append(
                            ConfusionPair(
                                tool_a=tools[i].tool_id,
                                tool_b=tools[j].tool_id,
                                similarity=sim,
                                zone_a=tools[i].zone,
                                zone_b=tools[j].zone,
                                is_cross_zone=tools[i].zone != tools[j].zone,
                            )
                        )

        # Sort by similarity descending
        pairs.sort(key=lambda p: p.similarity, reverse=True)
        return pairs[:20]  # Top 20 most confusing pairs

    def _detect_hubness(
        self,
        embeddings: np.ndarray,
        tools: list[ToolPoint],
    ) -> list[HubnessAlert]:
        """Detect tools that appear too often as nearest neighbor.

        A hub is a tool that is the nearest neighbor of many other tools,
        which indicates it's a "false positive magnet".
        """
        n = len(tools)
        if n < 3:
            return []

        sim_matrix = _cosine_similarity_matrix(embeddings)
        # Zero out self-similarity
        np.fill_diagonal(sim_matrix, -1.0)

        # Find nearest neighbor for each tool
        nn_indices = np.argmax(sim_matrix, axis=1)
        nn_counts = Counter(int(idx) for idx in nn_indices)

        expected_rate = 1.0 / n
        alerts: list[HubnessAlert] = []

        for idx, count in nn_counts.items():
            actual_rate = count / n
            if actual_rate > self.hubness_threshold:
                alerts.append(
                    HubnessAlert(
                        tool_id=tools[idx].tool_id,
                        zone=tools[idx].zone,
                        times_as_nn=count,
                        expected_rate=expected_rate,
                        actual_rate=actual_rate,
                    )
                )

        alerts.sort(key=lambda a: a.actual_rate, reverse=True)
        return alerts

    def _compute_inter_zone_distances(
        self,
        embeddings: np.ndarray,
        tools: list[ToolPoint],
    ) -> dict[str, float]:
        """Compute mean distances between zone centroids."""
        zones = list({t.zone for t in tools})
        centroids: dict[str, np.ndarray] = {}

        for zone in zones:
            zone_mask = [i for i, t in enumerate(tools) if t.zone == zone]
            if zone_mask:
                centroids[zone] = np.mean(embeddings[zone_mask], axis=0)

        distances: dict[str, float] = {}
        zone_list = sorted(centroids.keys())

        for i, z1 in enumerate(zone_list):
            for z2 in zone_list[i + 1:]:
                # Cosine distance
                c1 = centroids[z1]
                c2 = centroids[z2]
                sim = float(
                    np.dot(c1, c2)
                    / (np.linalg.norm(c1) * np.linalg.norm(c2) + 1e-10)
                )
                distances[f"{z1}↔{z2}"] = 1.0 - sim

        return distances

    def _compute_umap(
        self,
        embeddings: np.ndarray,
        tools: list[ToolPoint],
    ) -> list[UMAPPoint]:
        """Compute 2D UMAP projection.

        Falls back to PCA if umap-learn is not installed.
        """
        try:
            from umap import UMAP

            reducer = UMAP(n_components=2, random_state=42, n_neighbors=min(15, len(tools) - 1))
            coords = reducer.fit_transform(embeddings)
        except ImportError:
            logger.info("umap-learn not installed, falling back to PCA projection")
            coords = self._pca_2d(embeddings)

        points: list[UMAPPoint] = []
        for i, tool in enumerate(tools):
            points.append(
                UMAPPoint(
                    tool_id=tool.tool_id,
                    x=float(coords[i, 0]),
                    y=float(coords[i, 1]),
                    zone=tool.zone,
                )
            )
        return points

    @staticmethod
    def _pca_2d(embeddings: np.ndarray) -> np.ndarray:
        """Simple PCA to 2D as fallback for UMAP."""
        centered = embeddings - np.mean(embeddings, axis=0)
        # Use SVD for PCA
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        return centered @ vt[:2].T
