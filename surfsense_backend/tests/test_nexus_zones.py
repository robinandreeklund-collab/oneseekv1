"""Tests for Zone Manager — Sprint 2 extensions."""

import numpy as np
import pytest

from app.nexus.config import Zone
from app.nexus.routing.zone_manager import ZoneManager


class TestZonePrefixEmbeddings:
    def setup_method(self):
        self.zm = ZoneManager()

    def test_embed_tool_with_zone_known_namespace(self):
        result = self.zm.embed_tool_with_zone("Väderprognos", "tools/weather/smhi")
        # tools/weather maps to "väder-och-klimat" → prefix [VÄDER]
        assert result.startswith("[VÄDER] ")
        assert "Väderprognos" in result

    def test_embed_tool_with_zone_unknown_namespace(self):
        result = self.zm.embed_tool_with_zone("Something", "tools/unknown")
        assert result == "Something"

    def test_embed_query_with_hint(self):
        result = self.zm.embed_query_with_hint("väder stockholm", [Zone.KUNSKAP])
        assert result.startswith("[KUNSK] ")

    def test_embed_query_no_hint(self):
        result = self.zm.embed_query_with_hint("väder stockholm", [])
        assert result == "väder stockholm"


class TestZoneCentroids:
    def setup_method(self):
        self.zm = ZoneManager()

    def test_set_and_get_centroid(self):
        centroid = [1.0, 0.0, 0.0]
        self.zm.set_centroid("kunskap", centroid)
        result = self.zm.get_centroid("kunskap")
        assert result is not None
        np.testing.assert_array_almost_equal(result, centroid)

    def test_get_centroid_not_set(self):
        result = self.zm.get_centroid("nonexistent")
        assert result is None

    def test_distance_to_centroid(self):
        self.zm.set_centroid("kunskap", [1.0, 0.0, 0.0])
        dist = self.zm.distance_to_centroid([1.0, 0.0, 0.0], "kunskap")
        assert dist == pytest.approx(0.0, abs=1e-6)

    def test_distance_to_centroid_nonzero(self):
        self.zm.set_centroid("kunskap", [1.0, 0.0, 0.0])
        dist = self.zm.distance_to_centroid([0.0, 1.0, 0.0], "kunskap")
        assert dist == pytest.approx(2**0.5, abs=1e-4)

    def test_distance_no_centroid(self):
        dist = self.zm.distance_to_centroid([1.0, 0.0], "nonexistent")
        assert dist == -1.0

    def test_compute_centroids_from_tools(self):
        tools = [
            {"zone": "kunskap", "embedding": [1.0, 0.0]},
            {"zone": "kunskap", "embedding": [3.0, 0.0]},
            {"zone": "myndigheter", "embedding": [0.0, 1.0]},
        ]
        centroids = self.zm.compute_centroids_from_tools(tools)
        assert "kunskap" in centroids
        np.testing.assert_array_almost_equal(centroids["kunskap"], [2.0, 0.0])
        np.testing.assert_array_almost_equal(centroids["myndigheter"], [0.0, 1.0])

    def test_nearest_zone(self):
        self.zm.set_centroid("kunskap", [1.0, 0.0])
        self.zm.set_centroid("myndigheter", [0.0, 1.0])
        result = self.zm.nearest_zone([0.9, 0.1])
        assert result is not None
        assert result[0] == "kunskap"

    def test_nearest_zone_no_centroids(self):
        result = self.zm.nearest_zone([1.0, 0.0])
        assert result is None
