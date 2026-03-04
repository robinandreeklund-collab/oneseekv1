"""Tests for NEXUS Confidence Band Cascade."""

import pytest

from app.nexus.routing.confidence_bands import ConfidenceBandCascade


@pytest.fixture
def cascade():
    return ConfidenceBandCascade()


class TestBandClassification:
    def test_band_0_high_confidence_high_margin(self, cascade):
        result = cascade.classify(top_score=0.97, second_score=0.70)
        assert result.band == 0
        assert result.action == "direct"

    def test_band_1_high_confidence_moderate_margin(self, cascade):
        result = cascade.classify(top_score=0.85, second_score=0.72)
        assert result.band == 1
        assert result.action == "verify"

    def test_band_2_medium_confidence(self, cascade):
        result = cascade.classify(top_score=0.71, second_score=0.68)
        assert result.band == 2
        assert result.action == "top3_llm"

    def test_band_3_low_confidence(self, cascade):
        result = cascade.classify(top_score=0.52, second_score=0.48)
        assert result.band == 3
        assert result.action == "decompose"

    def test_band_4_very_low(self, cascade):
        result = cascade.classify(top_score=0.31, second_score=0.28)
        assert result.band == 4
        assert result.action == "ood"

    def test_band_0_requires_both_score_and_margin(self, cascade):
        # High score but low margin → not band 0
        result = cascade.classify(top_score=0.96, second_score=0.90)
        assert result.band != 0

    def test_zero_scores(self, cascade):
        result = cascade.classify(top_score=0.0, second_score=0.0)
        assert result.band == 4


class TestBandDistribution:
    def test_distribution_counts(self, cascade):
        classifications = [
            cascade.classify(0.97, 0.70),  # Band 0
            cascade.classify(0.97, 0.70),  # Band 0
            cascade.classify(0.85, 0.72),  # Band 1
            cascade.classify(0.52, 0.48),  # Band 3
            cascade.classify(0.31, 0.28),  # Band 4
        ]
        dist = cascade.get_band_distribution(classifications)
        assert dist[0] == 2
        assert dist[1] == 1
        assert dist[3] == 1
        assert dist[4] == 1

    def test_band0_rate(self, cascade):
        classifications = [
            cascade.classify(0.97, 0.70),  # Band 0
            cascade.classify(0.97, 0.70),  # Band 0
            cascade.classify(0.97, 0.70),  # Band 0
            cascade.classify(0.97, 0.70),  # Band 0
            cascade.classify(0.52, 0.48),  # Band 3
        ]
        rate = cascade.compute_band0_rate(classifications)
        assert rate == 0.8  # 4/5

    def test_band0_rate_empty(self, cascade):
        assert cascade.compute_band0_rate([]) == 0.0


class TestRawMarginOverride:
    """Platt scaling can compress calibrated margins to near-zero.

    When raw_margin is supplied, band checks should use that instead of
    the (compressed) calibrated margin.
    """

    def test_raw_margin_promotes_to_band_0(self, cascade):
        # Calibrated scores are close (margin 0.01) but raw margin is large
        result = cascade.classify(
            top_score=0.9909, second_score=0.9809, raw_margin=0.24
        )
        assert result.band == 0, f"Expected Band 0, got Band {result.band}"
        assert result.action == "direct"

    def test_raw_margin_promotes_to_band_1(self, cascade):
        # Calibrated margin < 0.10 but raw margin qualifies for Band 1
        result = cascade.classify(
            top_score=0.88, second_score=0.85, raw_margin=0.14
        )
        assert result.band == 1

    def test_raw_margin_none_uses_calibrated(self, cascade):
        # Without raw_margin, small calibrated gap → Band 2
        result = cascade.classify(top_score=0.96, second_score=0.90)
        assert result.band != 0  # margin 0.06 < 0.20


class TestCustomThresholds:
    def test_custom_band0_threshold(self):
        cascade = ConfidenceBandCascade(band_0_min_score=0.99)
        result = cascade.classify(top_score=0.97, second_score=0.70)
        assert result.band != 0  # 0.97 < 0.99

    def test_relaxed_thresholds(self):
        cascade = ConfidenceBandCascade(
            band_0_min_score=0.80,
            band_0_min_margin=0.10,
        )
        result = cascade.classify(top_score=0.82, second_score=0.70)
        assert result.band == 0
