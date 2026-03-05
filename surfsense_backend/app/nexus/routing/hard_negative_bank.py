"""Hard Negative Bank — false-negative-aware mining.

Mines and stores hard negative pairs: tools that are semantically similar
but should NOT be confused. These pairs are critical for improving
reranker precision and training contrastive embeddings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Thresholds
POSITIVE_AWARE_THRESHOLD: float = 0.80
SEMI_HARD_MARGIN: float = 0.15


@dataclass
class HardNegativePair:
    """A hard negative pair between two tools."""

    anchor_tool: str
    negative_tool: str
    mining_method: str  # "confusion" | "adversarial" | "semi_hard" | "domain_overlap"
    similarity_score: float = 0.0
    is_false_negative: bool = False
    adversarial_query: str = ""
    confusion_frequency: float = 0.0


@dataclass
class MiningResult:
    """Result of a hard negative mining run."""

    total_pairs: int = 0
    new_pairs: int = 0
    updated_pairs: int = 0
    by_method: dict[str, int] = field(default_factory=dict)


class HardNegativeMiner:
    """Mines hard negative pairs for contrastive training.

    Methods:
    1. Confusion-based: from Space Auditor confusion pairs
    2. Adversarial: from Synth Forge adversarial test cases
    3. Semi-hard: pairs within margin of positive threshold
    4. Domain-overlap: tools with shared keywords but different outputs
    """

    def __init__(
        self,
        positive_threshold: float = POSITIVE_AWARE_THRESHOLD,
        semi_hard_margin: float = SEMI_HARD_MARGIN,
    ):
        self.positive_threshold = positive_threshold
        self.semi_hard_margin = semi_hard_margin
        self._bank: dict[tuple[str, str], HardNegativePair] = {}

    @property
    def pairs(self) -> list[HardNegativePair]:
        """All stored hard negative pairs."""
        return list(self._bank.values())

    def add_pair(self, pair: HardNegativePair) -> bool:
        """Add a hard negative pair. Returns True if new, False if updated."""
        key = (pair.anchor_tool, pair.negative_tool)
        is_new = key not in self._bank

        existing = self._bank.get(key)
        if existing and existing.similarity_score >= pair.similarity_score:
            return False  # Don't overwrite with lower-similarity pair

        self._bank[key] = pair
        return is_new

    def mine_from_confusion(self, confusion_pairs: list[dict]) -> MiningResult:
        """Mine hard negatives from Space Auditor confusion pairs.

        Args:
            confusion_pairs: List of dicts with tool_a, tool_b, similarity.

        Returns:
            MiningResult with counts.
        """
        result = MiningResult()

        for cp in confusion_pairs:
            similarity = cp.get("similarity", 0.0)
            if similarity < self.positive_threshold:
                continue

            pair = HardNegativePair(
                anchor_tool=cp.get("tool_a", ""),
                negative_tool=cp.get("tool_b", ""),
                mining_method="confusion",
                similarity_score=similarity,
                confusion_frequency=cp.get("frequency", 0.0),
            )

            is_new = self.add_pair(pair)
            result.total_pairs += 1
            if is_new:
                result.new_pairs += 1
            else:
                result.updated_pairs += 1

        result.by_method["confusion"] = result.total_pairs
        return result

    def mine_from_adversarial(self, adversarial_cases: list[dict]) -> MiningResult:
        """Mine hard negatives from Synth Forge adversarial cases.

        Adversarial cases are queries that should NOT route to a tool
        but look similar. Each creates a hard negative pair.

        Args:
            adversarial_cases: List of dicts with tool_id, expected_tool, question.
        """
        result = MiningResult()

        for case in adversarial_cases:
            tool_id = case.get("tool_id", "")
            expected = case.get("expected_tool")

            if not tool_id or expected == tool_id:
                continue

            pair = HardNegativePair(
                anchor_tool=tool_id,
                negative_tool=expected or "unknown",
                mining_method="adversarial",
                adversarial_query=case.get("question", ""),
            )

            is_new = self.add_pair(pair)
            result.total_pairs += 1
            if is_new:
                result.new_pairs += 1
            else:
                result.updated_pairs += 1

        result.by_method["adversarial"] = result.total_pairs
        return result

    def mine_semi_hard(self, tool_pairs_with_scores: list[dict]) -> MiningResult:
        """Mine semi-hard negatives: pairs within margin of positive threshold.

        Semi-hard negatives are the most useful for training because they're
        close to the decision boundary.

        Args:
            tool_pairs_with_scores: List of dicts with anchor, negative, score.
        """
        result = MiningResult()

        lower_bound = self.positive_threshold - self.semi_hard_margin
        upper_bound = self.positive_threshold

        for entry in tool_pairs_with_scores:
            score = entry.get("score", 0.0)
            if lower_bound <= score <= upper_bound:
                pair = HardNegativePair(
                    anchor_tool=entry.get("anchor", ""),
                    negative_tool=entry.get("negative", ""),
                    mining_method="semi_hard",
                    similarity_score=score,
                )
                is_new = self.add_pair(pair)
                result.total_pairs += 1
                if is_new:
                    result.new_pairs += 1
                else:
                    result.updated_pairs += 1

        result.by_method["semi_hard"] = result.total_pairs
        return result

    def mine_domain_overlap(self, tools_metadata: list[dict]) -> MiningResult:
        """Mine hard negatives from tools with overlapping keywords but different zones.

        Args:
            tools_metadata: List of dicts with tool_id, zone, keywords.
        """
        result = MiningResult()

        # Build keyword → tool_id mapping
        keyword_tools: dict[str, list[dict]] = {}
        for tool in tools_metadata:
            for kw in tool.get("keywords", []):
                kw_lower = kw.lower()
                keyword_tools.setdefault(kw_lower, []).append(tool)

        # Find tools that share keywords but belong to different zones
        seen: set[tuple[str, str]] = set()
        for _kw, sharing_tools in keyword_tools.items():
            if len(sharing_tools) < 2:
                continue
            for i, t1 in enumerate(sharing_tools):
                for t2 in sharing_tools[i + 1 :]:
                    if t1.get("zone") == t2.get("zone"):
                        continue

                    key = tuple(sorted([t1["tool_id"], t2["tool_id"]]))
                    if key in seen:
                        continue
                    seen.add(key)

                    pair = HardNegativePair(
                        anchor_tool=key[0],
                        negative_tool=key[1],
                        mining_method="domain_overlap",
                    )
                    is_new = self.add_pair(pair)
                    result.total_pairs += 1
                    if is_new:
                        result.new_pairs += 1
                    else:
                        result.updated_pairs += 1

        result.by_method["domain_overlap"] = result.total_pairs
        return result

    def get_pairs_for_tool(self, tool_id: str) -> list[HardNegativePair]:
        """Get all hard negative pairs where tool_id is the anchor."""
        return [p for p in self._bank.values() if p.anchor_tool == tool_id]

    def get_stats(self) -> dict[str, int]:
        """Return summary statistics."""
        by_method: dict[str, int] = {}
        for pair in self._bank.values():
            by_method[pair.mining_method] = by_method.get(pair.mining_method, 0) + 1
        return {
            "total_pairs": len(self._bank),
            **by_method,
        }
