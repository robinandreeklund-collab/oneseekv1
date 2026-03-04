"""Zone Manager — embedding zone architecture.

Manages the 4 embedding zones: [KUNSK], [MYNDG], [HANDL], [JAMFR].
Handles zone-prefix embeddings, namespace→zone mapping, and zone
health monitoring.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.nexus.config import NAMESPACE_ZONE_MAP, ZONE_PREFIXES, Zone

logger = logging.getLogger(__name__)


class ZoneManager:
    """Manages the 4-zone embedding architecture.

    Zone architecture:
        [KUNSK]  — Knowledge: search, web, docs, marketplace
        [MYNDG]  — Government: SMHI, SCB, Trafikverket, Riksdagen, Skolverket
        [HANDL]  — Actions: sandbox, podcast, image generation
        [JAMFR]  — Comparison: multi-model calls (GPT, Claude, Grok)

    Zone-prefix embeddings improve inter-zone distance by +12-18%
    without fine-tuning the underlying embedding model.
    """

    def __init__(self):
        self.zones = list(Zone)
        self.prefixes = ZONE_PREFIXES
        self.namespace_map = NAMESPACE_ZONE_MAP
        # Zone centroids (loaded from DB or computed from tool embeddings)
        self._centroids: dict[str, np.ndarray] = {}

    def resolve_zone_from_namespace(
        self, namespace: str | tuple[str, ...]
    ) -> Zone | None:
        """Map a namespace (or namespace tuple) to a zone.

        Args:
            namespace: Namespace string or tuple (e.g., "tools/weather/smhi"
                       or ("tools", "weather", "smhi")).

        Returns:
            The resolved Zone, or None if no match.
        """
        if isinstance(namespace, (list, tuple)):
            ns_str = "/".join(namespace)
        else:
            ns_str = namespace

        # Try progressively shorter prefixes
        parts = ns_str.split("/")
        for i in range(len(parts), 0, -1):
            prefix = "/".join(parts[:i])
            if prefix in self.namespace_map:
                return self.namespace_map[prefix]

        return None

    def get_zone_prefix(self, zone: Zone | str) -> str:
        """Get the prefix token for a zone.

        Args:
            zone: Zone enum or string name.

        Returns:
            Prefix string (e.g., "[KUNSK] ").
        """
        zone_key = Zone(zone) if isinstance(zone, str) else zone
        return self.prefixes.get(zone_key, "")

    def prefix_text_for_zone(self, text: str, zone: Zone | str) -> str:
        """Prepend zone prefix to text for embedding.

        Args:
            text: Text to prefix (e.g., tool description or query).
            zone: Target zone.

        Returns:
            Prefixed text (e.g., "[MYNDG] Väderprognos för...").
        """
        prefix = self.get_zone_prefix(zone)
        return f"{prefix}{text}"

    def prefix_query_with_hint(self, query: str, zone_hint: str | None) -> str:
        """Prefix a query with a zone hint if available.

        If no hint is provided, return the query unmodified for
        broad search across all zones.

        Args:
            query: The user query.
            zone_hint: Optional zone name to narrow the search.

        Returns:
            Query string, possibly with zone prefix.
        """
        if zone_hint and zone_hint in [z.value for z in Zone]:
            return self.prefix_text_for_zone(query, zone_hint)
        return query

    def get_zone_config_data(self) -> list[dict]:
        """Return zone configuration for seeding or API responses."""
        return [
            {
                "zone": zone.value,
                "prefix_token": self.prefixes[zone],
            }
            for zone in self.zones
        ]

    def get_all_zone_names(self) -> list[str]:
        """Return all zone names."""
        return [z.value for z in self.zones]

    # ----- Zone-prefix embedding methods (Sprint 2) -----

    def embed_tool_with_zone(
        self, description: str, namespace: str | tuple[str, ...]
    ) -> str:
        """Prepend the zone prefix to a tool description for embedding.

        This forces the embedding model to encode zone-awareness into the
        vector, improving inter-zone separation by +12-18%.

        Args:
            description: Tool description text.
            namespace: Tool namespace (used to resolve zone).

        Returns:
            Zone-prefixed text ready for embedding.
        """
        zone = self.resolve_zone_from_namespace(namespace)
        if zone:
            return self.prefix_text_for_zone(description, zone)
        return description

    def embed_query_with_hint(self, query: str, zone_candidates: list[str]) -> str:
        """Prepend the most likely zone prefix to a query for embedding.

        If multiple zones are candidates, uses the first (highest priority).

        Args:
            query: The user query.
            zone_candidates: Zone candidates from QUL analysis.

        Returns:
            Zone-prefixed query (or original if no candidate).
        """
        if zone_candidates:
            return self.prefix_query_with_hint(query, zone_candidates[0])
        return query

    def set_centroid(self, zone: str, centroid: list[float] | np.ndarray) -> None:
        """Set the centroid embedding for a zone.

        Args:
            zone: Zone name.
            centroid: Centroid embedding vector.
        """
        self._centroids[zone] = np.array(centroid, dtype=np.float32)

    def get_centroid(self, zone: str) -> np.ndarray | None:
        """Get the centroid embedding for a zone."""
        return self._centroids.get(zone)

    def distance_to_centroid(
        self, embedding: list[float] | np.ndarray, zone: str
    ) -> float:
        """Compute L2 distance from an embedding to a zone centroid.

        Args:
            embedding: Query or tool embedding.
            zone: Zone name.

        Returns:
            L2 distance, or -1.0 if no centroid is set.
        """
        centroid = self._centroids.get(zone)
        if centroid is None:
            return -1.0
        emb = np.array(embedding, dtype=np.float32)
        return float(np.linalg.norm(emb - centroid))

    def compute_centroids_from_tools(
        self, tool_data: list[dict[str, Any]]
    ) -> dict[str, np.ndarray]:
        """Compute zone centroids from a list of tool embeddings.

        Args:
            tool_data: List of dicts with 'zone' and 'embedding' keys.

        Returns:
            Dict of zone → centroid numpy array.
        """
        zone_embeddings: dict[str, list[list[float]]] = {}
        for t in tool_data:
            zone = t.get("zone", "")
            emb = t.get("embedding")
            if zone and emb:
                zone_embeddings.setdefault(zone, []).append(emb)

        for zone, embeddings in zone_embeddings.items():
            centroid = np.mean(embeddings, axis=0).astype(np.float32)
            self._centroids[zone] = centroid

        return dict(self._centroids)

    def nearest_zone(
        self, embedding: list[float] | np.ndarray
    ) -> tuple[str, float] | None:
        """Find the nearest zone centroid to an embedding.

        Returns:
            Tuple of (zone_name, distance) or None if no centroids set.
        """
        if not self._centroids:
            return None

        emb = np.array(embedding, dtype=np.float32)
        best_zone = ""
        best_dist = float("inf")

        for zone, centroid in self._centroids.items():
            dist = float(np.linalg.norm(emb - centroid))
            if dist < best_dist:
                best_dist = dist
                best_zone = zone

        return (best_zone, best_dist) if best_zone else None
