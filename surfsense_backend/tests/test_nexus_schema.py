"""Tests for Schema Verifier — Sprint 2."""

from app.nexus.routing.schema_verifier import SchemaVerifier


class TestSchemaVerification:
    def setup_method(self):
        self.sv = SchemaVerifier()

    def test_unknown_tool_passes(self):
        result = self.sv.verify("unknown_tool_xyz")
        assert result.verified is True
        assert result.confidence_penalty == 0.0

    def test_smhi_with_location(self):
        result = self.sv.verify(
            "smhi_weather",
            query="väder i stockholm",
            entities_locations=["Stockholm"],
        )
        assert result.verified is True

    def test_smhi_without_location(self):
        result = self.sv.verify(
            "smhi_weather",
            query="hur blir vädret?",
            entities_locations=[],
        )
        assert result.verified is False
        assert "location" in result.missing_params
        assert result.confidence_penalty > 0

    def test_foreign_query_for_sweden_tool(self):
        result = self.sv.verify(
            "smhi_weather",
            query="väder utomlands i europa",
            entities_locations=["Stockholm"],
        )
        assert result.scope_mismatch == "foreign_query_for_sweden_tool"
        assert result.confidence_penalty > 0

    def test_trafiklab_needs_two_locations(self):
        result = self.sv.verify(
            "trafiklab_route",
            query="resa stockholm",
            entities_locations=["Stockholm"],
        )
        assert result.verified is False
        assert (
            "origin" in result.missing_params or "destination" in result.missing_params
        )

    def test_trafiklab_with_two_locations(self):
        result = self.sv.verify(
            "trafiklab_route",
            query="resa stockholm till göteborg",
            entities_locations=["Stockholm", "Göteborg"],
        )
        assert result.verified is True

    def test_temporal_mismatch_historical_for_forecast(self):
        result = self.sv.verify(
            "smhi_vaderprognoser_metfcst",
            query="väder igår i stockholm",
            entities_locations=["Stockholm"],
            entities_times=["igår"],
        )
        assert result.confidence_penalty > 0

    def test_external_model_no_constraints(self):
        result = self.sv.verify(
            "call_gpt",
            query="explain quantum physics",
        )
        assert result.verified is True
        assert result.confidence_penalty == 0.0


class TestBatchVerification:
    def test_verify_top_candidates(self):
        sv = SchemaVerifier()
        candidates = [
            {"tool_id": "smhi_weather"},
            {"tool_id": "call_gpt"},
        ]
        results = sv.verify_top_candidates(
            candidates,
            query="väder stockholm",
            entities_locations=["Stockholm"],
        )
        assert len(results) == 2
        assert results[0].verified is True  # smhi with location
        assert results[1].verified is True  # gpt no constraints
