"""Tests for NEXUS QUL — Query Understanding Layer."""

import pytest

from app.nexus.routing.qul import QueryUnderstandingLayer


@pytest.fixture
def qul():
    return QueryUnderstandingLayer()


class TestSwedishNormalization:
    def test_abbreviation_expansion(self, qul):
        result = qul.analyze("Vad säger SMHI om vädret?")
        assert "Sveriges meteorologiska" in result.normalized_query

    def test_city_abbreviation(self, qul):
        result = qul.analyze("Bostadspriser i sthlm")
        assert "Stockholm" in result.normalized_query

    def test_slang_normalization(self, qul):
        result = qul.analyze("Vad kostar en tvårumma i gbg?")
        assert "tvårumslägenhet" in result.normalized_query
        assert "Göteborg" in result.normalized_query

    def test_no_modification_of_unknown_words(self, qul):
        result = qul.analyze("Berätta om artificiell intelligens")
        assert result.normalized_query == "Berätta om artificiell intelligens"


class TestEntityExtraction:
    def test_location_from_gazetteer(self, qul):
        result = qul.analyze("Väder i Uppsala imorgon")
        assert "Uppsala" in result.entities.locations

    def test_multiple_locations(self, qul):
        result = qul.analyze("Jämför bostadspriser Stockholm och Malmö")
        assert "Stockholm" in result.entities.locations
        assert "Malmö" in result.entities.locations

    def test_time_extraction(self, qul):
        result = qul.analyze("Väderprognos för imorgon")
        assert any("imorgon" in t for t in result.entities.times)

    def test_organization_extraction(self, qul):
        result = qul.analyze("Vad säger Trafikverket om E4?")
        assert "Trafikverket" in result.entities.organizations


class TestMultiIntentDetection:
    def test_single_intent(self, qul):
        result = qul.analyze("Vad blir vädret imorgon?")
        assert not result.is_multi_intent
        assert len(result.sub_queries) == 1

    def test_multi_intent_with_och(self, qul):
        result = qul.analyze("Hur är vädret och vad kostar en bostad i Sundsvall?")
        assert result.is_multi_intent
        assert len(result.sub_queries) >= 2

    def test_multi_intent_with_question_marks(self, qul):
        result = qul.analyze("Vad är vädret? Hur ser trafikläget ut?")
        assert result.is_multi_intent
        assert len(result.sub_queries) == 2

    def test_intent_margin_gate(self, qul):
        assert qul.should_decompose(top_score=0.5, second_score=0.45)
        assert not qul.should_decompose(top_score=0.9, second_score=0.3)


class TestDomainHints:
    def test_weather_hints(self, qul):
        result = qul.analyze("Väder i Stockholm")
        assert (
            "väder-och-klimat" in result.domain_hints or "väder" in result.domain_hints
        )

    def test_search_hints(self, qul):
        result = qul.analyze("Sök information om klimatförändringar")
        # "klimat" is a keyword for väder-och-klimat or kunskap
        assert len(result.domain_hints) >= 1

    def test_compare_hints_jamforelse(self, qul):
        result = qul.analyze("Jämför vad GPT och Claude tycker om AI")
        assert "jämförelse" in result.domain_hints

    def test_action_hints_skapande(self, qul):
        result = qul.analyze("Generera en podcast om teknik")
        assert "skapande" in result.domain_hints


class TestZoneResolution:
    def test_location_resolves_to_zone(self, qul):
        result = qul.analyze("Statistik om Umeå")
        # With fine-grained domains, statistik maps to specific domain zones
        assert len(result.zone_candidates) >= 1

    def test_fallback_to_broad_zones(self, qul):
        result = qul.analyze("hej")
        # Trivial greeting routes to konversation zone
        assert len(result.zone_candidates) >= 1


class TestComplexityClassification:
    def test_trivial(self, qul):
        result = qul.analyze("hej")
        assert result.complexity == "trivial"

    def test_simple(self, qul):
        result = qul.analyze("Väder i Stockholm imorgon")
        assert result.complexity == "simple"

    def test_compound(self, qul):
        result = qul.analyze("Hur är vädret och vad kostar bostäder?")
        assert result.complexity == "compound"
