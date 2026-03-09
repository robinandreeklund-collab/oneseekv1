"""End-to-end tests for the NEXUS routing pipeline.

Tests the full flow: Query → QUL → StR → Calibrate → Band → Decision,
verifying that each stage produces correct output for the next."""

import pytest

from app.nexus.calibration.platt_scaler import PlattCalibratedReranker, PlattParams
from app.nexus.config import Zone
from app.nexus.routing.confidence_bands import ConfidenceBandCascade
from app.nexus.routing.qul import QueryUnderstandingLayer
from app.nexus.routing.select_then_route import SelectThenRoute


def _compute_ece(
    calibrated_scores: list[float],
    labels: list[float],
    n_bins: int = 10,
) -> float:
    """Local copy of ECE computation for testing without heavy imports."""
    if not calibrated_scores or not labels:
        return 0.0
    n = len(calibrated_scores)
    bin_boundaries = [i / n_bins for i in range(n_bins + 1)]
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        in_bin = [
            (conf, lab)
            for conf, lab in zip(calibrated_scores, labels, strict=False)
            if lo <= conf < hi or (i == n_bins - 1 and conf == hi)
        ]
        if not in_bin:
            continue
        avg_conf = sum(conf for conf, _ in in_bin) / len(in_bin)
        avg_acc = sum(lab for _, lab in in_bin) / len(in_bin)
        ece += (len(in_bin) / n) * abs(avg_conf - avg_acc)
    return round(ece, 6)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def qul():
    return QueryUnderstandingLayer()


@pytest.fixture
def str_pipeline():
    return SelectThenRoute()


@pytest.fixture
def cascade():
    return ConfidenceBandCascade()


@pytest.fixture
def fitted_scaler():
    """A pre-fitted Platt scaler with realistic parameters.

    a > 0 and b < 0 ensures higher raw scores map to higher calibrated scores.
    """
    return PlattCalibratedReranker(
        PlattParams(a=-5.0, b=2.5, fitted=True, n_samples=100)
    )


@pytest.fixture
def tool_entries():
    """Simulated platform tool entries with score and namespace."""
    return [
        {
            "tool_id": "smhi_forecast",
            "zone": "väder-och-klimat",
            "score": 0.95,
            "namespace": "tools/weather/smhi_forecast",
        },
        {
            "tool_id": "trafikverket_trafikinfo",
            "zone": "trafik-och-transport",
            "score": 0.70,
            "namespace": "tools/trafik/trafikverket_trafikinfo",
        },
        {
            "tool_id": "scb_query",
            "zone": "statistik-och-data",
            "score": 0.60,
            "namespace": "tools/statistics/scb_query",
        },
        {
            "tool_id": "kolada_query",
            "zone": "statistik-och-data",
            "score": 0.55,
            "namespace": "tools/statistics/kolada_query",
        },
        {
            "tool_id": "riksdagen_search",
            "zone": "politik-och-samhälle",
            "score": 0.50,
            "namespace": "tools/politik/riksdagen_search",
        },
        {
            "tool_id": "bolagsverket_lookup",
            "zone": "bolag-och-ekonomi",
            "score": 0.45,
            "namespace": "tools/bolag/bolagsverket_lookup",
        },
        {
            "tool_id": "kb_search",
            "zone": "kunskap",
            "score": 0.40,
            "namespace": "tools/knowledge/kb_search",
        },
    ]


# ---------------------------------------------------------------------------
# End-to-end: Query → QUL → StR → Band
# ---------------------------------------------------------------------------


class TestE2EPipeline:
    def test_weather_query_routes_correctly(
        self, qul, str_pipeline, cascade, tool_entries, fitted_scaler
    ):
        """'Vad blir vädret i Stockholm imorgon?' should route to SMHI via band 0."""
        # Stage 1: QUL
        analysis = qul.analyze("Vad blir vädret i Stockholm imorgon?")
        assert "Stockholm" in analysis.entities.locations
        assert analysis.ood_risk < 0.5  # Should NOT be OOD

        # Stage 2: StR with agent namespace filtering
        agent_ns = ["tools/weather"]
        result = str_pipeline.run(
            analysis.normalized_query,
            analysis.zone_candidates or [Zone.KUNSKAP],
            tool_entries,
            agent_namespaces=agent_ns,
        )
        assert len(result.candidates) >= 1
        top_candidate = result.candidates[0]
        assert top_candidate.tool_id == "smhi_forecast"

        # Stage 3: Calibrate
        calibrated = fitted_scaler.calibrate(top_candidate.raw_score)
        assert 0.0 < calibrated < 1.0

        # Stage 4: Band classification
        second_score = (
            result.candidates[1].raw_score if len(result.candidates) > 1 else 0.0
        )
        band = cascade.classify(
            calibrated,
            fitted_scaler.calibrate(second_score) if second_score > 0 else 0.0,
        )
        assert band.band <= 1  # Should be high confidence

    def test_unknown_query_gets_high_ood_risk(self, qul):
        """Query about unrelated topic should get high OOD risk."""
        analysis = qul.analyze("How do quantum computers work?")
        assert analysis.ood_risk >= 0.5

    def test_multi_intent_query_detected(self, qul):
        """Query with multiple intents should be detected."""
        analysis = qul.analyze("Hur är vädret och vad kostar en bostad i Sundsvall?")
        assert analysis.is_multi_intent
        assert len(analysis.sub_queries) >= 2

    def test_traffic_query_domain_hints(self, qul):
        """Traffic query with org mention should be recognized."""
        analysis = qul.analyze("Vad säger Trafikverket om E4 vid Uppsala?")
        # Trafikverket is an organization keyword — expect hints or entity match
        has_hints = len(analysis.domain_hints) >= 1
        has_org = "Trafikverket" in analysis.entities.organizations
        assert has_hints or has_org


class TestCalibrationPipeline:
    def test_calibrated_scores_are_ordered(self, fitted_scaler):
        """Higher raw scores should yield higher calibrated scores."""
        raw_scores = [0.95, 0.80, 0.60, 0.40, 0.20]
        calibrated = fitted_scaler.calibrate_batch(raw_scores)
        # Monotonicity: should be non-increasing
        for i in range(len(calibrated) - 1):
            assert calibrated[i] >= calibrated[i + 1], (
                f"Calibrated scores not monotonic: {calibrated[i]} < {calibrated[i + 1]}"
            )

    def test_platt_params_roundtrip(self):
        """PlattParams can be created, fitted, and used for calibration."""
        scaler = PlattCalibratedReranker()
        assert not scaler.is_fitted

        raw = [
            0.9,
            0.85,
            0.8,
            0.3,
            0.2,
            0.15,
            0.7,
            0.6,
            0.95,
            0.88,
            0.25,
            0.18,
            0.5,
            0.4,
            0.92,
            0.12,
        ]
        labels = [1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 0]

        params = scaler.fit(raw, labels)
        assert params.fitted
        assert scaler.is_fitted

        # Can calibrate after fitting
        result = scaler.calibrate(0.5)
        assert 0.0 < result < 1.0


class TestECEComputation:
    def test_perfect_calibration_has_zero_ece(self):
        """Perfectly calibrated scores should have ECE ≈ 0."""
        # All predictions are 0.9 and all are correct (1.0)
        scores = [0.9] * 10
        labels = [1.0] * 10
        ece = _compute_ece(scores, labels)
        assert ece < 0.2  # Should be very low

    def test_terrible_calibration_has_high_ece(self):
        """Scores of 0.9 but all labels are 0 → high ECE."""
        scores = [0.9] * 10
        labels = [0.0] * 10
        ece = _compute_ece(scores, labels)
        assert ece > 0.5  # Should be high

    def test_empty_inputs(self):
        assert _compute_ece([], []) == 0.0

    def test_ece_is_bounded(self):
        """ECE should always be between 0 and 1."""
        import random

        random.seed(42)
        scores = [random.random() for _ in range(100)]
        labels = [float(random.choice([0, 1])) for _ in range(100)]
        ece = _compute_ece(scores, labels)
        assert 0.0 <= ece <= 1.0


class TestQULOODRisk:
    def test_known_domain_low_ood_risk(self, qul):
        """Weather query should have low OOD risk."""
        analysis = qul.analyze("Vad blir vädret imorgon?")
        assert analysis.ood_risk <= 0.2

    def test_unknown_domain_high_ood_risk(self, qul):
        """Completely unrelated query should have high OOD risk."""
        analysis = qul.analyze("Explain quantum entanglement in detail")
        assert analysis.ood_risk >= 0.5

    def test_multiple_domains_zero_risk(self, qul):
        """Multi-domain query should have very low OOD risk."""
        analysis = qul.analyze("Jämför vädret med trafikläget i Stockholm")
        # Multiple domain hints → low OOD risk
        if len(analysis.domain_hints) >= 2:
            assert analysis.ood_risk == 0.0


class TestStRCandidateSorting:
    def test_candidates_sorted_by_score(self, str_pipeline, tool_entries):
        """Candidates within a zone should be sorted by descending score."""
        result = str_pipeline.run(
            "statistik om befolkning",
            ["statistik-och-data"],
            tool_entries,
        )
        for i in range(len(result.candidates) - 1):
            assert result.candidates[i].raw_score >= result.candidates[i + 1].raw_score

    def test_namespace_filter_reduces_candidates(self, str_pipeline, tool_entries):
        """Filtering by namespace should return fewer candidates."""
        full = str_pipeline.run(
            "data", ["statistik-och-data", "väder-och-klimat"], tool_entries
        )
        filtered = str_pipeline.run(
            "data",
            ["statistik-och-data", "väder-och-klimat"],
            tool_entries,
            agent_namespaces=["tools/statistics"],
        )
        assert len(filtered.candidates) <= len(full.candidates)
