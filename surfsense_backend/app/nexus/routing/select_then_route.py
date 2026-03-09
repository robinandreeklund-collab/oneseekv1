"""Select-Then-Route (StR) — zone-aware retrieval pipeline.

Pattern: Zone selector → per-zone retrieval (top-5 per zone)
         → merge candidates → cross-encoder rerank on ~15 candidates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.nexus.routing.zone_manager import ZoneManager

logger = logging.getLogger(__name__)


@dataclass
class RetrievalCandidate:
    """A single tool candidate from retrieval."""

    tool_id: str
    zone: str
    raw_score: float
    namespace: str = ""
    description: str = ""


@dataclass
class StRResult:
    """Result of a Select-Then-Route pipeline run."""

    candidates: list[RetrievalCandidate] = field(default_factory=list)
    zones_searched: list[str] = field(default_factory=list)
    top_score: float = 0.0
    second_score: float = 0.0
    margin: float = 0.0


# Number of candidates to keep per zone before merging
PER_ZONE_TOP_K: int = 5

# Maximum total candidates to send to reranker
RERANK_MAX_CANDIDATES: int = 15


class SelectThenRoute:
    """Zone-aware retrieval: select zones first, then retrieve per-zone.

    This decouples zone selection (cheap) from tool retrieval (expensive),
    avoiding full cross-zone search on every query.
    """

    def __init__(self, zone_manager: ZoneManager | None = None):
        self.zone_manager = zone_manager or ZoneManager()

    def select_zones(
        self,
        zone_candidates: list[str],
        *,
        max_zones: int = 2,
    ) -> list[str]:
        """Select which zones to search based on QUL zone candidates.

        Args:
            zone_candidates: Zone names from QUL analysis.
            max_zones: Maximum number of zones to search.

        Returns:
            Selected zone names (at most max_zones).
        """
        # Accept any zone candidate (domain_ids or legacy zone names)
        valid_zones = list(zone_candidates) if zone_candidates else []
        if not valid_zones:
            # Fallback: use first two domain zones from config
            from app.nexus.config import get_all_zone_prefixes

            fallback_zones = list(get_all_zone_prefixes().keys())[:2]
            return fallback_zones if fallback_zones else ["kunskap", "skapande"]
        return valid_zones[:max_zones]

    def retrieve_per_zone(
        self,
        query: str,
        zones: list[str],
        tool_entries: list[dict],
        *,
        per_zone_k: int = PER_ZONE_TOP_K,
    ) -> list[RetrievalCandidate]:
        """Retrieve top-k candidates from each selected zone.

        This is a lightweight retrieval using pre-computed embeddings.
        In production, this would query PGVector per zone. Here we
        score against in-memory tool index entries.

        Args:
            query: The user query.
            zones: Zones to search.
            tool_entries: List of tool dicts with tool_id, namespace, zone, score.
            per_zone_k: Number of candidates per zone.

        Returns:
            Merged candidates across all zones, sorted by score.
        """
        candidates: list[RetrievalCandidate] = []

        for zone in zones:
            zone_tools = [t for t in tool_entries if t.get("zone") == zone]
            # Sort by score descending, take top-k
            zone_tools.sort(key=lambda t: t.get("score", 0.0), reverse=True)
            for t in zone_tools[:per_zone_k]:
                candidates.append(
                    RetrievalCandidate(
                        tool_id=t.get("tool_id", ""),
                        zone=zone,
                        raw_score=t.get("score", 0.0),
                        namespace=t.get("namespace", ""),
                        description=t.get("description", ""),
                    )
                )

        # Sort merged candidates by score
        candidates.sort(key=lambda c: c.raw_score, reverse=True)
        return candidates[:RERANK_MAX_CANDIDATES]

    def compute_margin(
        self, candidates: list[RetrievalCandidate]
    ) -> tuple[float, float, float]:
        """Compute top score, second score, and ABSOLUTE margin.

        The margin must be absolute (top - second) to match the band
        cascade thresholds (Band 0 requires margin >= 0.20, Band 1 >= 0.10).

        Returns:
            Tuple of (top_score, second_score, margin).
        """
        if not candidates:
            return 0.0, 0.0, 0.0
        top = candidates[0].raw_score
        second = candidates[1].raw_score if len(candidates) > 1 else 0.0
        margin = top - second
        return top, second, margin

    def run(
        self,
        query: str,
        zone_candidates: list[str],
        tool_entries: list[dict],
        *,
        max_zones: int = 2,
        per_zone_k: int = PER_ZONE_TOP_K,
        agent_namespaces: list[str] | None = None,
    ) -> StRResult:
        """Run the full Select-Then-Route pipeline.

        Args:
            query: User query.
            zone_candidates: Zone candidates from QUL.
            tool_entries: Tool entries with zone and score pre-computed.
            max_zones: Max zones to search.
            per_zone_k: Top-k per zone.
            agent_namespaces: If provided, only consider tools whose namespace
                starts with one of these prefixes.  This is the key integration
                point for the agent layer: Intent → Agent → Tool.

        Returns:
            StRResult with candidates, scores, and margin.
        """
        # Filter tools by agent namespaces when provided
        if agent_namespaces:
            filtered_entries = [
                t
                for t in tool_entries
                if any(t.get("namespace", "").startswith(ns) for ns in agent_namespaces)
            ]
            # Fall back to unfiltered if agent filter yields nothing
            if filtered_entries:
                tool_entries = filtered_entries

        zones = self.select_zones(zone_candidates, max_zones=max_zones)
        candidates = self.retrieve_per_zone(
            query,
            zones,
            tool_entries,
            per_zone_k=per_zone_k,
        )
        top, second, margin = self.compute_margin(candidates)

        return StRResult(
            candidates=candidates,
            zones_searched=zones,
            top_score=top,
            second_score=second,
            margin=margin,
        )
