"""Tests for Select-Then-Route — Sprint 2."""

from app.nexus.config import Zone
from app.nexus.routing.select_then_route import SelectThenRoute


class TestZoneSelection:
    def setup_method(self):
        self.str = SelectThenRoute()

    def test_select_valid_zones(self):
        zones = self.str.select_zones([Zone.KUNSKAP, Zone.SKAPANDE])
        assert zones == [Zone.KUNSKAP, Zone.SKAPANDE]

    def test_select_zones_max(self):
        zones = self.str.select_zones(
            [Zone.KUNSKAP, Zone.SKAPANDE, Zone.JAMFORELSE],
            max_zones=2,
        )
        assert len(zones) == 2

    def test_select_zones_fallback(self):
        zones = self.str.select_zones([])
        assert Zone.KUNSKAP in zones
        assert Zone.SKAPANDE in zones

    def test_select_zones_invalid_filtered(self):
        zones = self.str.select_zones(["nonexistent"])
        assert Zone.KUNSKAP in zones  # fallback


class TestRetrieval:
    def setup_method(self):
        self.str = SelectThenRoute()
        self.tools = [
            {
                "tool_id": "smhi_weather",
                "zone": "kunskap",
                "score": 0.95,
                "namespace": "tools/weather",
            },
            {
                "tool_id": "scb_data",
                "zone": "kunskap",
                "score": 0.80,
                "namespace": "tools/statistik",
            },
            {
                "tool_id": "search_kb",
                "zone": "kunskap",
                "score": 0.70,
                "namespace": "tools/knowledge",
            },
            {
                "tool_id": "call_gpt",
                "zone": "jämförelse",
                "score": 0.50,
                "namespace": "tools/compare",
            },
        ]

    def test_retrieve_per_zone(self):
        candidates = self.str.retrieve_per_zone(
            "väder stockholm",
            ["kunskap"],
            self.tools,
        )
        assert len(candidates) == 3
        assert candidates[0].tool_id == "smhi_weather"

    def test_retrieve_multiple_zones(self):
        candidates = self.str.retrieve_per_zone(
            "väder stockholm",
            ["kunskap", "jämförelse"],
            self.tools,
        )
        assert len(candidates) == 4

    def test_retrieve_empty_zone(self):
        candidates = self.str.retrieve_per_zone(
            "test",
            ["skapande"],
            self.tools,
        )
        assert len(candidates) == 0


class TestMarginComputation:
    def setup_method(self):
        self.str = SelectThenRoute()

    def test_compute_margin_normal(self):
        from app.nexus.routing.select_then_route import RetrievalCandidate

        candidates = [
            RetrievalCandidate(tool_id="a", zone="z", raw_score=0.95),
            RetrievalCandidate(tool_id="b", zone="z", raw_score=0.70),
        ]
        top, second, margin = self.str.compute_margin(candidates)
        assert top == 0.95
        assert second == 0.70
        assert margin > 0

    def test_compute_margin_single(self):
        from app.nexus.routing.select_then_route import RetrievalCandidate

        candidates = [
            RetrievalCandidate(tool_id="a", zone="z", raw_score=0.95),
        ]
        top, second, _margin = self.str.compute_margin(candidates)
        assert top == 0.95
        assert second == 0.0

    def test_compute_margin_empty(self):
        top, _second, _margin = self.str.compute_margin([])
        assert top == 0.0


class TestFullPipeline:
    def test_run(self):
        str_pipeline = SelectThenRoute()
        tools = [
            {
                "tool_id": "smhi_weather",
                "zone": "kunskap",
                "score": 0.95,
                "namespace": "tools/weather",
            },
            {
                "tool_id": "scb_data",
                "zone": "kunskap",
                "score": 0.80,
                "namespace": "tools/statistik",
            },
            {
                "tool_id": "search_kb",
                "zone": "kunskap",
                "score": 0.70,
                "namespace": "tools/knowledge",
            },
        ]
        result = str_pipeline.run(
            "väder i stockholm",
            [Zone.KUNSKAP],
            tools,
        )
        assert len(result.zones_searched) >= 1
        assert result.top_score == 0.95
        assert len(result.candidates) >= 1
