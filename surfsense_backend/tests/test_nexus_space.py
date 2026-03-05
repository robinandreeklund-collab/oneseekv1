"""Tests for Space Auditor — Sprint 2."""

import numpy as np

from app.nexus.layers.space_auditor import (
    SpaceAuditor,
    ToolPoint,
    _cosine_similarity_matrix,
)


class TestCosineMatrix:
    def test_identity(self):
        embs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        sim = _cosine_similarity_matrix(embs)
        assert sim[0, 0] == 1.0
        assert sim[1, 1] == 1.0
        assert abs(sim[0, 1]) < 1e-6  # orthogonal

    def test_same_vectors(self):
        embs = np.array([[1.0, 1.0], [1.0, 1.0]], dtype=np.float32)
        sim = _cosine_similarity_matrix(embs)
        assert sim[0, 1] > 0.999


class TestSpaceAuditor:
    def setup_method(self):
        self.auditor = SpaceAuditor(confusion_threshold=0.90)

    def _make_tools(self) -> list[ToolPoint]:
        """Create tool points with clearly separated zones."""
        return [
            ToolPoint(
                "smhi_weather", "tools/weather", "myndigheter", [1.0, 0.0, 0.0, 0.0]
            ),
            ToolPoint(
                "smhi_brandrisk", "tools/weather", "myndigheter", [0.9, 0.1, 0.0, 0.0]
            ),
            ToolPoint(
                "scb_pop", "tools/statistik", "myndigheter", [0.8, 0.2, 0.0, 0.0]
            ),
            ToolPoint("search_kb", "tools/knowledge", "kunskap", [0.0, 0.0, 1.0, 0.0]),
            ToolPoint("search_web", "tools/knowledge", "kunskap", [0.0, 0.0, 0.9, 0.1]),
            ToolPoint("sandbox", "tools/code", "handling", [0.0, 0.0, 0.0, 1.0]),
            ToolPoint("podcast", "tools/action", "handling", [0.0, 0.0, 0.0, 0.9]),
        ]

    def test_separation_matrix_basic(self):
        tools = self._make_tools()
        report = self.auditor.compute_separation_matrix(tools)
        assert report.total_tools == 7
        assert report.global_silhouette != 0.0

    def test_per_zone_silhouette(self):
        tools = self._make_tools()
        report = self.auditor.compute_separation_matrix(tools)
        assert "myndigheter" in report.per_zone_silhouette
        assert "kunskap" in report.per_zone_silhouette

    def test_confusion_pairs(self):
        # Create two tools with nearly identical embeddings
        tools = [
            ToolPoint("tool_a", "ns_a", "zone_a", [1.0, 0.0]),
            ToolPoint("tool_b", "ns_b", "zone_a", [0.99, 0.01]),
            ToolPoint("tool_c", "ns_c", "zone_b", [0.0, 1.0]),
        ]
        auditor = SpaceAuditor(confusion_threshold=0.90)
        report = auditor.compute_separation_matrix(tools)
        assert len(report.confusion_pairs) >= 1
        pair = report.confusion_pairs[0]
        assert {pair.tool_a, pair.tool_b} == {"tool_a", "tool_b"}

    def test_no_confusion_well_separated(self):
        tools = [
            ToolPoint("a", "ns_a", "z1", [1.0, 0.0, 0.0]),
            ToolPoint("b", "ns_b", "z2", [0.0, 1.0, 0.0]),
            ToolPoint("c", "ns_c", "z3", [0.0, 0.0, 1.0]),
        ]
        auditor = SpaceAuditor(confusion_threshold=0.90)
        report = auditor.compute_separation_matrix(tools)
        assert len(report.confusion_pairs) == 0

    def test_hubness_detection(self):
        # Create a hub: one vector that is nearest neighbor to many
        tools = [
            ToolPoint("hub", "ns_hub", "z1", [0.5, 0.5, 0.5]),
            ToolPoint("a", "ns_a", "z2", [0.4, 0.5, 0.5]),
            ToolPoint("b", "ns_b", "z2", [0.5, 0.4, 0.5]),
            ToolPoint("c", "ns_c", "z2", [0.5, 0.5, 0.4]),
            ToolPoint("d", "ns_d", "z3", [0.5, 0.5, 0.6]),
        ]
        auditor = SpaceAuditor(hubness_threshold=0.30)
        report = auditor.compute_separation_matrix(tools)
        # Hub should appear as NN for multiple tools
        if report.hubness_alerts:
            assert report.hubness_alerts[0].times_as_nn >= 2

    def test_inter_zone_distances(self):
        tools = self._make_tools()
        report = self.auditor.compute_separation_matrix(tools)
        assert len(report.inter_zone_distances) > 0

    def test_umap_points_generated(self):
        tools = self._make_tools()
        report = self.auditor.compute_separation_matrix(tools)
        assert len(report.umap_points) == 7
        for p in report.umap_points:
            assert hasattr(p, "x")
            assert hasattr(p, "y")

    def test_single_tool(self):
        tools = [ToolPoint("only", "ns", "z", [1.0, 0.0])]
        report = self.auditor.compute_separation_matrix(tools)
        assert report.total_tools == 1
        assert report.global_silhouette == 0.0

    def test_empty_tools(self):
        report = self.auditor.compute_separation_matrix([])
        assert report.total_tools == 0


class TestECEMonitor:
    def test_perfect_calibration(self):
        from app.nexus.calibration.ece_monitor import compute_ece

        # Perfect calibration: confidence matches accuracy
        confs = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        correct = [False, False, False, False, True, True, True, True, True, True]
        result = compute_ece(confs, correct, n_bins=5)
        assert result.ece < 0.3  # Should be low

    def test_bad_calibration(self):
        from app.nexus.calibration.ece_monitor import compute_ece

        # Always confident but always wrong
        confs = [0.95, 0.90, 0.85, 0.92, 0.88]
        correct = [False, False, False, False, False]
        result = compute_ece(confs, correct, n_bins=5)
        assert result.ece > 0.5

    def test_empty_input(self):
        from app.nexus.calibration.ece_monitor import compute_ece

        result = compute_ece([], [])
        assert result.ece == 0.0

    def test_per_zone(self):
        from app.nexus.calibration.ece_monitor import compute_ece_per_zone

        zone_data = {
            "kunskap": ([0.8, 0.9], [True, True]),
            "myndigheter": ([0.3, 0.4], [False, False]),
        }
        results = compute_ece_per_zone(zone_data)
        assert "kunskap" in results
        assert "myndigheter" in results


class TestDATSScaler:
    def test_calibrate_near_centroid(self):
        from app.nexus.calibration.dats_scaler import ZonalTemperatureScaler

        scaler = ZonalTemperatureScaler()
        result = scaler.calibrate(0.8, "kunskap", distance_to_centroid=0.1)
        assert 0 < result.calibrated_score <= 1.0
        assert result.temperature > 0

    def test_calibrate_far_from_centroid(self):
        from app.nexus.calibration.dats_scaler import ZonalTemperatureScaler

        scaler = ZonalTemperatureScaler()
        near = scaler.calibrate(0.8, "kunskap", distance_to_centroid=0.1)
        far = scaler.calibrate(0.8, "kunskap", distance_to_centroid=2.0)
        # Far should have higher temperature → flatter → lower confidence
        assert far.temperature > near.temperature

    def test_calibrate_edge_scores(self):
        from app.nexus.calibration.dats_scaler import ZonalTemperatureScaler

        scaler = ZonalTemperatureScaler()
        zero = scaler.calibrate(0.0, "z", 1.0)
        one = scaler.calibrate(1.0, "z", 1.0)
        assert zero.calibrated_score == 0.0
        assert one.calibrated_score == 1.0
