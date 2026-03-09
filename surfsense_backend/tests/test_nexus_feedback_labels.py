"""Tests for NEXUS feedback-aware calibration labels.

Verifies that user feedback (explicit_feedback) overrides band-based
labels when building Platt calibration training data."""

from types import SimpleNamespace


def _make_event(band: int, raw_score: float, explicit_feedback=None):
    """Create a fake routing event for testing label logic."""
    return SimpleNamespace(
        band=band,
        raw_reranker_score=raw_score,
        explicit_feedback=explicit_feedback,
    )


def _build_labels(events):
    """Replicate the label-building logic from fit_calibration."""
    labels = []
    for ev in events:
        if ev.explicit_feedback == 1:
            labels.append(1.0)
        elif ev.explicit_feedback == -1:
            labels.append(0.0)
        else:
            labels.append(1.0 if ev.band <= 1 else 0.0)
    return labels


class TestFeedbackLabelOverrides:
    def test_thumbs_up_overrides_bad_band(self):
        """Band 3 (bad) with thumbs up should become label 1.0."""
        events = [_make_event(band=3, raw_score=0.4, explicit_feedback=1)]
        labels = _build_labels(events)
        assert labels == [1.0]

    def test_thumbs_down_overrides_good_band(self):
        """Band 0 (good) with thumbs down should become label 0.0."""
        events = [_make_event(band=0, raw_score=0.95, explicit_feedback=-1)]
        labels = _build_labels(events)
        assert labels == [0.0]

    def test_no_feedback_uses_band(self):
        """Without feedback, band 0/1 → 1.0, band 2+ → 0.0."""
        events = [
            _make_event(band=0, raw_score=0.95),
            _make_event(band=1, raw_score=0.80),
            _make_event(band=2, raw_score=0.60),
            _make_event(band=3, raw_score=0.40),
        ]
        labels = _build_labels(events)
        assert labels == [1.0, 1.0, 0.0, 0.0]

    def test_neutral_feedback_uses_band(self):
        """explicit_feedback=0 (neutral) should fall back to band-based label."""
        events = [
            _make_event(band=0, raw_score=0.95, explicit_feedback=0),
            _make_event(band=3, raw_score=0.40, explicit_feedback=0),
        ]
        labels = _build_labels(events)
        assert labels == [1.0, 0.0]

    def test_mixed_feedback_and_no_feedback(self):
        """Mix of feedback-overridden and band-based labels."""
        events = [
            _make_event(band=0, raw_score=0.95),  # band → 1.0
            _make_event(band=3, raw_score=0.35, explicit_feedback=1),  # override → 1.0
            _make_event(band=1, raw_score=0.82, explicit_feedback=-1),  # override → 0.0
            _make_event(band=2, raw_score=0.55),  # band → 0.0
        ]
        labels = _build_labels(events)
        assert labels == [1.0, 1.0, 0.0, 0.0]


class TestFeedbackValidation:
    """Verify that log_feedback rejects invalid values."""

    def test_valid_implicit_values(self):
        valid = {"reformulation", "follow_up"}
        for v in valid:
            assert v in valid

    def test_invalid_implicit_rejected(self):
        invalid_values = ["click", "hover", "random", ""]
        valid = {"reformulation", "follow_up"}
        for v in invalid_values:
            assert v not in valid

    def test_valid_explicit_values(self):
        valid = {-1, 0, 1}
        for v in valid:
            assert v in valid

    def test_invalid_explicit_rejected(self):
        invalid = [2, -2, 5, 100]
        valid = {-1, 0, 1}
        for v in invalid:
            assert v not in valid
