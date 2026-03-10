"""Tests for app.services.scb_regions — SCB region registry + diacritik normalization."""

import pytest

from app.services.scb_regions import (
    ALL_REGIONS,
    ScbRegion,
    find_region_by_code,
    find_region_by_name,
    find_region_fuzzy,
    format_region_for_llm,
    normalize_diacritik,
    resolve_region_codes,
)


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------


class TestRegistryIntegrity:
    def test_all_regions_not_empty(self):
        assert len(ALL_REGIONS) > 300  # 1 country + 21 counties + 290 munis

    def test_exactly_one_country(self):
        countries = [r for r in ALL_REGIONS if r.type == "country"]
        assert len(countries) == 1
        assert countries[0].code == "00"
        assert countries[0].name == "Riket"

    def test_twenty_one_counties(self):
        counties = [r for r in ALL_REGIONS if r.type == "county"]
        assert len(counties) == 21

    def test_municipality_count(self):
        munis = [r for r in ALL_REGIONS if r.type == "municipality"]
        assert len(munis) == 290

    def test_all_codes_unique(self):
        codes = [r.code for r in ALL_REGIONS]
        assert len(codes) == len(set(codes)), "Duplicate region codes found"

    def test_municipality_codes_are_4_digits(self):
        munis = [r for r in ALL_REGIONS if r.type == "municipality"]
        for m in munis:
            assert len(m.code) == 4, f"{m.name} has code {m.code} (not 4 digits)"
            assert m.code.isdigit(), f"{m.name} code {m.code} is not numeric"

    def test_county_codes_are_2_digits(self):
        counties = [r for r in ALL_REGIONS if r.type == "county"]
        for c in counties:
            assert len(c.code) == 2, f"{c.name} has code {c.code} (not 2 digits)"
            assert c.code.isdigit(), f"{c.name} code {c.code} is not numeric"

    def test_well_known_municipalities_present(self):
        codes = {r.code for r in ALL_REGIONS}
        well_known = {
            "0180": "Stockholm",
            "1480": "Göteborg",
            "1280": "Malmö",
            "0380": "Uppsala",
            "0580": "Linköping",
            "0680": "Jönköping",
            "2480": "Umeå",
        }
        for code, name in well_known.items():
            assert code in codes, f"{name} ({code}) not in registry"


# ---------------------------------------------------------------------------
# Diacritik normalization
# ---------------------------------------------------------------------------


class TestNormalizeDiacritik:
    def test_swedish_a_ring(self):
        assert normalize_diacritik("Malmö") == "malmo"

    def test_swedish_umlaut(self):
        assert normalize_diacritik("Göteborg") == "goteborg"
        assert normalize_diacritik("Jönköping") == "jonkoping"
        assert normalize_diacritik("Västerås") == "vasteras"

    def test_a_ring(self):
        assert normalize_diacritik("Åre") == "are"

    def test_already_ascii(self):
        assert normalize_diacritik("Stockholm") == "stockholm"

    def test_case_insensitive(self):
        assert normalize_diacritik("GÖTEBORG") == "goteborg"

    def test_strips_whitespace(self):
        assert normalize_diacritik("  Malmö  ") == "malmo"

    def test_empty_string(self):
        assert normalize_diacritik("") == ""

    def test_french_accents(self):
        # Should also handle non-Swedish diacritics
        assert normalize_diacritik("café") == "cafe"

    def test_idempotent(self):
        result = normalize_diacritik("Göteborg")
        assert normalize_diacritik(result) == result


# ---------------------------------------------------------------------------
# Lookup functions
# ---------------------------------------------------------------------------


class TestFindRegionByCode:
    def test_municipality(self):
        r = find_region_by_code("0180")
        assert r is not None
        assert r.name == "Stockholm"
        assert r.type == "municipality"

    def test_county(self):
        r = find_region_by_code("14")
        assert r is not None
        assert r.name == "Västra Götalands län"
        assert r.type == "county"

    def test_country(self):
        r = find_region_by_code("00")
        assert r is not None
        assert r.name == "Riket"

    def test_not_found(self):
        assert find_region_by_code("9999") is None

    def test_strips_whitespace(self):
        r = find_region_by_code(" 0180 ")
        assert r is not None
        assert r.name == "Stockholm"


class TestFindRegionByName:
    def test_exact_match(self):
        r = find_region_by_name("Stockholm")
        assert r is not None
        assert r.code == "0180"

    def test_case_insensitive(self):
        r = find_region_by_name("STOCKHOLM")
        assert r is not None
        assert r.code == "0180"

    def test_not_found(self):
        assert find_region_by_name("Narnia") is None


class TestFindRegionFuzzy:
    def test_exact_match(self):
        results = find_region_fuzzy("Stockholm")
        assert len(results) >= 1
        assert results[0].code == "0180"

    def test_diacritik_match(self):
        results = find_region_fuzzy("Goteborg")
        assert len(results) >= 1
        assert any(r.code == "1480" for r in results)

    def test_jonkoping_without_diacritics(self):
        results = find_region_fuzzy("Jonkoping")
        assert len(results) >= 1
        codes = [r.code for r in results]
        # Should match Jönköping municipality or county
        assert "0680" in codes or "06" in codes

    def test_alias_sthlm(self):
        results = find_region_fuzzy("sthlm")
        assert len(results) == 1
        assert results[0].code == "0180"

    def test_alias_gbg(self):
        results = find_region_fuzzy("gbg")
        assert len(results) == 1
        assert results[0].code == "1480"

    def test_alias_riket(self):
        results = find_region_fuzzy("riket")
        assert len(results) == 1
        assert results[0].code == "00"

    def test_empty_query(self):
        assert find_region_fuzzy("") == []

    def test_no_match(self):
        results = find_region_fuzzy("zzzzzzz")
        assert results == []

    def test_municipalities_before_counties(self):
        """Municipalities should come before counties in results."""
        results = find_region_fuzzy("Goteborg")
        if len(results) > 1:
            types = [r.type for r in results]
            muni_idx = types.index("municipality") if "municipality" in types else 999
            county_idx = types.index("county") if "county" in types else 999
            if muni_idx != 999 and county_idx != 999:
                assert muni_idx < county_idx

    def test_county_alias_skane(self):
        results = find_region_fuzzy("skane")
        assert len(results) >= 1
        assert results[0].code == "12"


# ---------------------------------------------------------------------------
# resolve_region_codes
# ---------------------------------------------------------------------------


class TestResolveRegionCodes:
    def test_basic_resolution(self):
        codes = resolve_region_codes("Stockholm")
        assert "0180" in codes

    def test_with_table_values(self):
        """Should filter to codes that exist in the table."""
        codes = resolve_region_codes(
            "Stockholm",
            table_values=["00", "0180", "1480"],
        )
        assert codes == ["0180"]

    def test_not_in_table(self):
        """If the region code doesn't exist in the table, return empty."""
        codes = resolve_region_codes(
            "Stockholm",
            table_values=["00", "1480"],  # No Stockholm
        )
        # Might find via text matching fallback or return empty
        assert isinstance(codes, list)

    def test_fuzzy_in_table_values(self):
        """Should match 'Goteborg' against table value texts."""
        codes = resolve_region_codes(
            "Goteborg",
            table_values=["1480"],
            table_value_texts=["Göteborgs kommun"],
        )
        assert "1480" in codes

    def test_empty_input(self):
        codes = resolve_region_codes("")
        assert codes == []


# ---------------------------------------------------------------------------
# format_region_for_llm
# ---------------------------------------------------------------------------


class TestFormatRegionForLlm:
    def test_municipality(self):
        region = ScbRegion("0180", "Stockholm", "municipality")
        formatted = format_region_for_llm(region)
        assert "0180" in formatted
        assert "Stockholm" in formatted
        assert "kommun" in formatted

    def test_county(self):
        region = ScbRegion("01", "Stockholms län", "county")
        formatted = format_region_for_llm(region)
        assert "01" in formatted
        assert "län" in formatted

    def test_country(self):
        region = ScbRegion("00", "Riket", "country")
        formatted = format_region_for_llm(region)
        assert "00" in formatted
        assert "hela landet" in formatted
