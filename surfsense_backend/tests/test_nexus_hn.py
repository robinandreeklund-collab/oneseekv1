"""Tests for NEXUS Hard Negative Bank — false-negative-aware mining."""

from __future__ import annotations

from app.nexus.routing.hard_negative_bank import (
    POSITIVE_AWARE_THRESHOLD,
    SEMI_HARD_MARGIN,
    HardNegativeMiner,
    HardNegativePair,
)

# ---------------------------------------------------------------------------
# HardNegativePair dataclass
# ---------------------------------------------------------------------------


class TestHardNegativePair:
    def test_defaults(self):
        pair = HardNegativePair(
            anchor_tool="a", negative_tool="b", mining_method="confusion"
        )
        assert pair.similarity_score == 0.0
        assert pair.is_false_negative is False
        assert pair.adversarial_query == ""


# ---------------------------------------------------------------------------
# add_pair
# ---------------------------------------------------------------------------


class TestAddPair:
    def test_new_pair(self):
        miner = HardNegativeMiner()
        pair = HardNegativePair(
            anchor_tool="a",
            negative_tool="b",
            mining_method="confusion",
            similarity_score=0.9,
        )
        assert miner.add_pair(pair) is True
        assert len(miner.pairs) == 1

    def test_update_higher_score(self):
        miner = HardNegativeMiner()
        p1 = HardNegativePair(
            anchor_tool="a",
            negative_tool="b",
            mining_method="confusion",
            similarity_score=0.8,
        )
        p2 = HardNegativePair(
            anchor_tool="a",
            negative_tool="b",
            mining_method="confusion",
            similarity_score=0.95,
        )
        miner.add_pair(p1)
        assert miner.add_pair(p2) is False  # Not new, but updated
        assert miner.pairs[0].similarity_score == 0.95

    def test_no_downgrade(self):
        miner = HardNegativeMiner()
        p1 = HardNegativePair(
            anchor_tool="a",
            negative_tool="b",
            mining_method="confusion",
            similarity_score=0.95,
        )
        p2 = HardNegativePair(
            anchor_tool="a",
            negative_tool="b",
            mining_method="confusion",
            similarity_score=0.8,
        )
        miner.add_pair(p1)
        miner.add_pair(p2)
        assert miner.pairs[0].similarity_score == 0.95  # Not downgraded


# ---------------------------------------------------------------------------
# mine_from_confusion
# ---------------------------------------------------------------------------


class TestMineFromConfusion:
    def test_basic_mining(self):
        miner = HardNegativeMiner()
        pairs = [
            {"tool_a": "smhi", "tool_b": "yr", "similarity": 0.92},
            {"tool_a": "scb", "tool_b": "kolada", "similarity": 0.85},
        ]
        result = miner.mine_from_confusion(pairs)
        assert result.total_pairs == 2
        assert result.new_pairs == 2

    def test_below_threshold_filtered(self):
        miner = HardNegativeMiner()
        pairs = [
            {"tool_a": "a", "tool_b": "b", "similarity": 0.50},
            {"tool_a": "c", "tool_b": "d", "similarity": 0.90},
        ]
        result = miner.mine_from_confusion(pairs)
        assert result.total_pairs == 1  # Only the one >= 0.80

    def test_empty_input(self):
        miner = HardNegativeMiner()
        result = miner.mine_from_confusion([])
        assert result.total_pairs == 0


# ---------------------------------------------------------------------------
# mine_from_adversarial
# ---------------------------------------------------------------------------


class TestMineFromAdversarial:
    def test_basic_adversarial(self):
        miner = HardNegativeMiner()
        cases = [
            {"tool_id": "smhi", "expected_tool": "yr", "question": "Vad blir vädret?"},
        ]
        result = miner.mine_from_adversarial(cases)
        assert result.total_pairs == 1
        assert miner.pairs[0].mining_method == "adversarial"
        assert miner.pairs[0].adversarial_query == "Vad blir vädret?"

    def test_same_tool_skipped(self):
        miner = HardNegativeMiner()
        cases = [
            {"tool_id": "smhi", "expected_tool": "smhi", "question": "Q?"},
        ]
        result = miner.mine_from_adversarial(cases)
        assert result.total_pairs == 0

    def test_no_tool_id_skipped(self):
        miner = HardNegativeMiner()
        cases = [{"expected_tool": "yr", "question": "Q?"}]
        result = miner.mine_from_adversarial(cases)
        assert result.total_pairs == 0


# ---------------------------------------------------------------------------
# mine_semi_hard
# ---------------------------------------------------------------------------


class TestMineSemiHard:
    def test_within_margin(self):
        miner = HardNegativeMiner()
        pairs = [
            {"anchor": "a", "negative": "b", "score": 0.70},  # Within [0.65, 0.80]
            {"anchor": "c", "negative": "d", "score": 0.50},  # Below margin
        ]
        result = miner.mine_semi_hard(pairs)
        assert result.total_pairs == 1

    def test_custom_thresholds(self):
        miner = HardNegativeMiner(positive_threshold=0.90, semi_hard_margin=0.10)
        pairs = [
            {"anchor": "a", "negative": "b", "score": 0.85},  # [0.80, 0.90]
        ]
        result = miner.mine_semi_hard(pairs)
        assert result.total_pairs == 1

    def test_exact_boundary(self):
        miner = HardNegativeMiner()
        pairs = [
            {"anchor": "a", "negative": "b", "score": POSITIVE_AWARE_THRESHOLD},
            {
                "anchor": "c",
                "negative": "d",
                "score": POSITIVE_AWARE_THRESHOLD - SEMI_HARD_MARGIN,
            },
        ]
        result = miner.mine_semi_hard(pairs)
        assert result.total_pairs == 2  # Both on boundary included


# ---------------------------------------------------------------------------
# mine_domain_overlap
# ---------------------------------------------------------------------------


class TestMineDomainOverlap:
    def test_shared_keywords_different_zones(self):
        miner = HardNegativeMiner()
        tools = [
            {"tool_id": "smhi", "zone": "kunskap", "keywords": ["väder", "temperatur"]},
            {"tool_id": "yr", "zone": "handling", "keywords": ["väder", "prognos"]},
        ]
        result = miner.mine_domain_overlap(tools)
        assert result.total_pairs == 1
        assert miner.pairs[0].mining_method == "domain_overlap"

    def test_same_zone_skipped(self):
        miner = HardNegativeMiner()
        tools = [
            {"tool_id": "a", "zone": "kunskap", "keywords": ["data"]},
            {"tool_id": "b", "zone": "kunskap", "keywords": ["data"]},
        ]
        result = miner.mine_domain_overlap(tools)
        assert result.total_pairs == 0

    def test_no_shared_keywords(self):
        miner = HardNegativeMiner()
        tools = [
            {"tool_id": "a", "zone": "kunskap", "keywords": ["väder"]},
            {"tool_id": "b", "zone": "handling", "keywords": ["ekonomi"]},
        ]
        result = miner.mine_domain_overlap(tools)
        assert result.total_pairs == 0

    def test_no_duplicates(self):
        miner = HardNegativeMiner()
        tools = [
            {"tool_id": "a", "zone": "kunskap", "keywords": ["data", "statistik"]},
            {"tool_id": "b", "zone": "handling", "keywords": ["data", "statistik"]},
        ]
        result = miner.mine_domain_overlap(tools)
        assert result.total_pairs == 1  # Only counted once despite 2 shared keywords


# ---------------------------------------------------------------------------
# get_pairs_for_tool / get_stats
# ---------------------------------------------------------------------------


class TestUtilityMethods:
    def test_get_pairs_for_tool(self):
        miner = HardNegativeMiner()
        miner.add_pair(
            HardNegativePair(
                anchor_tool="a",
                negative_tool="b",
                mining_method="confusion",
                similarity_score=0.9,
            )
        )
        miner.add_pair(
            HardNegativePair(
                anchor_tool="a",
                negative_tool="c",
                mining_method="semi_hard",
                similarity_score=0.7,
            )
        )
        miner.add_pair(
            HardNegativePair(
                anchor_tool="b",
                negative_tool="c",
                mining_method="confusion",
                similarity_score=0.85,
            )
        )
        assert len(miner.get_pairs_for_tool("a")) == 2
        assert len(miner.get_pairs_for_tool("b")) == 1
        assert len(miner.get_pairs_for_tool("x")) == 0

    def test_get_stats(self):
        miner = HardNegativeMiner()
        miner.add_pair(
            HardNegativePair(
                anchor_tool="a",
                negative_tool="b",
                mining_method="confusion",
                similarity_score=0.9,
            )
        )
        miner.add_pair(
            HardNegativePair(
                anchor_tool="c",
                negative_tool="d",
                mining_method="adversarial",
                similarity_score=0.8,
            )
        )
        stats = miner.get_stats()
        assert stats["total_pairs"] == 2
        assert stats["confusion"] == 1
        assert stats["adversarial"] == 1
