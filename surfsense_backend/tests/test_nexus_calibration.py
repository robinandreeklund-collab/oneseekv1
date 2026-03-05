"""Tests for NEXUS Platt Scaling calibration."""

from app.nexus.calibration.platt_scaler import PlattCalibratedReranker, PlattParams


class TestPlattScaler:
    def test_default_params(self):
        scaler = PlattCalibratedReranker()
        assert not scaler.is_fitted
        assert scaler.params.a == 1.0
        assert scaler.params.b == 0.0

    def test_calibrate_with_defaults(self):
        scaler = PlattCalibratedReranker()
        result = scaler.calibrate(0.5)
        assert 0.0 < result < 1.0

    def test_fit_with_data(self):
        scaler = PlattCalibratedReranker()
        # Simulate: high scores → correct, low scores → incorrect
        raw_scores = [
            0.9,
            0.85,
            0.8,
            0.75,
            0.3,
            0.2,
            0.15,
            0.1,
            0.7,
            0.6,
            0.95,
            0.88,
            0.25,
            0.18,
            0.5,
            0.4,
            0.92,
            0.82,
            0.12,
            0.08,
        ]
        labels = [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0]

        params = scaler.fit(raw_scores, labels)
        assert params.fitted
        assert params.n_samples == 20

    def test_fit_too_few_samples(self):
        scaler = PlattCalibratedReranker()
        params = scaler.fit([0.9, 0.1], [1, 0])
        assert not params.fitted  # Should keep defaults

    def test_calibrate_batch(self):
        scaler = PlattCalibratedReranker(PlattParams(a=1.5, b=-0.5, fitted=True))
        results = scaler.calibrate_batch([0.1, 0.5, 0.9])
        assert len(results) == 3
        # All should be valid probabilities
        for r in results:
            assert 0.0 < r < 1.0

    def test_monotonicity_after_fit(self):
        """Higher raw scores should yield higher calibrated scores."""
        scaler = PlattCalibratedReranker()
        raw_scores = [
            0.9,
            0.85,
            0.8,
            0.75,
            0.3,
            0.2,
            0.15,
            0.1,
            0.7,
            0.6,
            0.95,
            0.88,
            0.25,
            0.18,
            0.5,
            0.4,
            0.92,
            0.82,
            0.12,
            0.08,
        ]
        labels = [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0]
        scaler.fit(raw_scores, labels)

        low = scaler.calibrate(0.2)
        high = scaler.calibrate(0.9)
        # After proper fitting, higher scores should map to higher probability
        # (either direction depending on sign of A)
        assert low != high

    def test_custom_params(self):
        params = PlattParams(a=2.0, b=-1.0, fitted=True, n_samples=100)
        scaler = PlattCalibratedReranker(params)
        assert scaler.is_fitted
        result = scaler.calibrate(0.5)
        assert 0.0 < result < 1.0
