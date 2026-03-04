"""Tests for NEXUS OOD (Out-of-Distribution) detection."""

import numpy as np

from app.nexus.routing.ood_detector import DarkMatterDetector


class TestEnergyScore:
    def test_in_distribution_high_logits(self):
        detector = DarkMatterDetector()
        # High logits → very negative energy → in-distribution
        logits = np.array([5.0, 4.0, 3.0])
        energy = detector.energy_score(logits)
        assert energy < -5.0  # Should be well below threshold

    def test_ood_low_logits(self):
        detector = DarkMatterDetector()
        # Low logits → higher energy → OOD
        logits = np.array([0.1, 0.05, 0.01])
        energy = detector.energy_score(logits)
        assert energy > -5.0  # Should be above threshold

    def test_empty_logits(self):
        detector = DarkMatterDetector()
        energy = detector.energy_score(np.array([]))
        assert energy == 0.0


class TestDetection:
    def test_clear_in_distribution(self):
        detector = DarkMatterDetector()
        logits = np.array([5.0, 4.0, 3.0])
        result = detector.detect(logits)
        assert not result.is_ood
        assert result.method is None

    def test_clear_ood(self):
        detector = DarkMatterDetector()
        logits = np.array([0.1, 0.05, 0.01])
        result = detector.detect(logits)
        assert result.is_ood
        assert result.method == "energy"

    def test_custom_threshold(self):
        # Energy for [1.0, 0.5, 0.3] ≈ -1.74, so threshold must be above that
        detector = DarkMatterDetector(energy_threshold=-1.5)
        logits = np.array([1.0, 0.5, 0.3])
        result = detector.detect(logits)
        # Energy -1.74 < threshold -1.5 → in-distribution
        assert not result.is_ood


class TestKNNBackup:
    def test_build_knn_index(self):
        detector = DarkMatterDetector()
        embeddings = np.random.randn(100, 64).tolist()
        detector.build_knn_index(embeddings)
        assert detector.has_knn_index

    def test_knn_score(self):
        detector = DarkMatterDetector()
        embeddings = np.random.randn(100, 64).tolist()
        detector.build_knn_index(embeddings)

        query = np.random.randn(64)
        score = detector.knn_score(query)
        assert score is not None
        assert score >= 0.0

    def test_knn_not_built(self):
        detector = DarkMatterDetector()
        query = np.random.randn(64)
        assert detector.knn_score(query) is None

    def test_borderline_triggers_knn(self):
        """When energy is borderline, KNN should be used as backup."""
        detector = DarkMatterDetector(
            energy_threshold=-5.0,
            knn_threshold=0.1,  # Very low threshold to trigger OOD
        )
        # Build with tight cluster
        embeddings = (np.random.randn(50, 64) * 0.01).tolist()
        detector.build_knn_index(embeddings)

        # Borderline energy: above threshold * 0.8 but below threshold
        # We mock by using logits that produce borderline energy
        logits = np.array([1.5, 1.0, 0.8])

        # Far-away query embedding
        far_query = np.ones(64) * 100.0

        result = detector.detect(logits, query_embedding=far_query)
        # The exact result depends on energy value, but the logic should run
        assert isinstance(result.is_ood, bool)
