"""Tests for Kolada integration in bigtool_store.py."""

import pytest

from app.agents.new_chat.bigtool_store import (
    TOOL_KEYWORDS,
    _namespace_for_kolada_tool,
    namespace_for_tool,
)
from app.agents.new_chat.kolada_tools import KOLADA_TOOL_DEFINITIONS


def test_namespace_for_kolada_tool_omsorg():
    """Test namespace mapping for omsorg category tools."""
    assert _namespace_for_kolada_tool("kolada_aldreomsorg") == (
        "tools",
        "statistics",
        "kolada",
        "omsorg",
    )
    assert _namespace_for_kolada_tool("kolada_lss") == (
        "tools",
        "statistics",
        "kolada",
        "omsorg",
    )
    assert _namespace_for_kolada_tool("kolada_ifo") == (
        "tools",
        "statistics",
        "kolada",
        "omsorg",
    )
    assert _namespace_for_kolada_tool("kolada_barn_unga") == (
        "tools",
        "statistics",
        "kolada",
        "omsorg",
    )


def test_namespace_for_kolada_tool_skola():
    """Test namespace mapping for skola category tools."""
    assert _namespace_for_kolada_tool("kolada_forskola") == (
        "tools",
        "statistics",
        "kolada",
        "skola",
    )
    assert _namespace_for_kolada_tool("kolada_grundskola") == (
        "tools",
        "statistics",
        "kolada",
        "skola",
    )
    assert _namespace_for_kolada_tool("kolada_gymnasieskola") == (
        "tools",
        "statistics",
        "kolada",
        "skola",
    )


def test_namespace_for_kolada_tool_halsa():
    """Test namespace mapping for hälsa category tool."""
    assert _namespace_for_kolada_tool("kolada_halsa") == (
        "tools",
        "statistics",
        "kolada",
        "halsa",
    )


def test_namespace_for_kolada_tool_ekonomi():
    """Test namespace mapping for ekonomi category tool."""
    assert _namespace_for_kolada_tool("kolada_ekonomi") == (
        "tools",
        "statistics",
        "kolada",
        "ekonomi",
    )


def test_namespace_for_kolada_tool_miljo():
    """Test namespace mapping for miljö category tool."""
    assert _namespace_for_kolada_tool("kolada_miljo") == (
        "tools",
        "statistics",
        "kolada",
        "miljo",
    )


def test_namespace_for_kolada_tool_boende():
    """Test namespace mapping for boende category tool."""
    assert _namespace_for_kolada_tool("kolada_boende") == (
        "tools",
        "statistics",
        "kolada",
        "boende",
    )


def test_namespace_for_kolada_tool_ovrig():
    """Test namespace mapping for övrig category tools."""
    assert _namespace_for_kolada_tool("kolada_sammanfattning") == (
        "tools",
        "statistics",
        "kolada",
        "sammanfattning",
    )
    assert _namespace_for_kolada_tool("kolada_kultur") == (
        "tools",
        "statistics",
        "kolada",
        "kultur",
    )
    assert _namespace_for_kolada_tool("kolada_arbetsmarknad") == (
        "tools",
        "statistics",
        "kolada",
        "arbetsmarknad",
    )
    assert _namespace_for_kolada_tool("kolada_demokrati") == (
        "tools",
        "statistics",
        "kolada",
        "demokrati",
    )


def test_namespace_for_tool_with_kolada_prefix():
    """Test that namespace_for_tool correctly routes kolada_ prefixed tools."""
    # Test a few examples
    assert namespace_for_tool("kolada_aldreomsorg") == (
        "tools",
        "statistics",
        "kolada",
        "omsorg",
    )
    assert namespace_for_tool("kolada_forskola") == (
        "tools",
        "statistics",
        "kolada",
        "skola",
    )
    assert namespace_for_tool("kolada_ekonomi") == (
        "tools",
        "statistics",
        "kolada",
        "ekonomi",
    )


def test_namespace_for_tool_kolada_vs_scb():
    """Test that kolada and scb tools have different namespaces."""
    # Kolada tools should be under kolada namespace
    kolada_ns = namespace_for_tool("kolada_aldreomsorg")
    assert kolada_ns[2] == "kolada"
    
    # SCB tools should be under scb namespace
    scb_ns = namespace_for_tool("scb_befolkning")
    assert scb_ns[2] == "scb"
    
    # Both should be under statistics
    assert kolada_ns[1] == "statistics"
    assert scb_ns[1] == "statistics"


def test_tool_keywords_all_kolada_tools():
    """Test that all 15 Kolada tools have keywords defined."""
    kolada_tool_ids = [d.tool_id for d in KOLADA_TOOL_DEFINITIONS]
    
    for tool_id in kolada_tool_ids:
        assert tool_id in TOOL_KEYWORDS, f"{tool_id} missing from TOOL_KEYWORDS"
        keywords = TOOL_KEYWORDS[tool_id]
        assert isinstance(keywords, list)
        assert len(keywords) > 0


def test_tool_keywords_include_kolada():
    """Test that all Kolada tools have 'kolada' as a keyword."""
    kolada_tool_ids = [d.tool_id for d in KOLADA_TOOL_DEFINITIONS]
    
    for tool_id in kolada_tool_ids:
        keywords = TOOL_KEYWORDS[tool_id]
        assert "kolada" in keywords, f"{tool_id} missing 'kolada' keyword"


def test_tool_keywords_swedish_variants():
    """Test that keywords include Swedish character variants."""
    # Test äldreomsorg has both å/ä/ö variants
    aldreomsorg_keywords = TOOL_KEYWORDS["kolada_aldreomsorg"]
    assert "aldreomsorg" in aldreomsorg_keywords
    assert "äldreomsorg" in aldreomsorg_keywords
    assert "aldrevard" in aldreomsorg_keywords or "äldrevård" in aldreomsorg_keywords
    
    # Test hemtjänst variants
    assert "hemtjanst" in aldreomsorg_keywords
    assert "hemtjänst" in aldreomsorg_keywords
    
    # Test förskola variants
    forskola_keywords = TOOL_KEYWORDS["kolada_forskola"]
    assert "forskola" in forskola_keywords
    assert "förskola" in forskola_keywords
    
    # Test gymnasieskola variants
    gymnasie_keywords = TOOL_KEYWORDS["kolada_gymnasieskola"]
    assert "genomstromning" in gymnasie_keywords
    assert "genomströmning" in gymnasie_keywords


def test_tool_keywords_category_specific():
    """Test that keywords match tool categories."""
    # Omsorg tools should have omsorg-related keywords
    aldreomsorg_keywords = TOOL_KEYWORDS["kolada_aldreomsorg"]
    assert any(k in ["aldreomsorg", "äldreomsorg", "hemtjanst", "hemtjänst"] for k in aldreomsorg_keywords)
    
    # Skola tools should have skola-related keywords
    grundskola_keywords = TOOL_KEYWORDS["kolada_grundskola"]
    assert any(k in ["grundskola", "skola", "elev", "betyg"] for k in grundskola_keywords)
    
    # Hälsa tool should have hälsa keywords
    halsa_keywords = TOOL_KEYWORDS["kolada_halsa"]
    assert any(k in ["halsa", "hälsa", "vard", "vård", "sjukvard", "sjukvård"] for k in halsa_keywords)


def test_kolada_tool_keywords_count():
    """Test that we have exactly 15 Kolada tools in TOOL_KEYWORDS."""
    kolada_keywords = {k: v for k, v in TOOL_KEYWORDS.items() if k.startswith("kolada_")}
    assert len(kolada_keywords) == 15


def test_kolada_keywords_no_duplicates():
    """Test that Kolada tool IDs don't have duplicate entries in TOOL_KEYWORDS."""
    kolada_tool_ids = [d.tool_id for d in KOLADA_TOOL_DEFINITIONS]
    keyword_tool_ids = [k for k in TOOL_KEYWORDS.keys() if k.startswith("kolada_")]
    
    # Should have same set of tool IDs
    assert set(kolada_tool_ids) == set(keyword_tool_ids)


def test_namespace_consistency():
    """Test that all Kolada tools get consistent namespace mapping."""
    for definition in KOLADA_TOOL_DEFINITIONS:
        namespace = _namespace_for_kolada_tool(definition.tool_id)
        
        # All should start with tools/statistics/kolada
        assert namespace[0] == "tools"
        assert namespace[1] == "statistics"
        assert namespace[2] == "kolada"
        
        # Should have 4 levels (including subcategory)
        assert len(namespace) == 4


def test_integration_with_scb_keywords():
    """Test that Kolada keywords don't conflict with SCB keywords."""
    scb_keywords = {k: v for k, v in TOOL_KEYWORDS.items() if k.startswith("scb_")}
    kolada_keywords = {k: v for k, v in TOOL_KEYWORDS.items() if k.startswith("kolada_")}
    
    # Should have no overlapping tool IDs
    assert len(set(scb_keywords.keys()) & set(kolada_keywords.keys())) == 0
    
    # But both should have 'statistik' as a potential keyword somewhere
    # (This is okay since they're different tools)


def test_all_categories_covered():
    """Test that all expected categories have tools."""
    categories = {d.category for d in KOLADA_TOOL_DEFINITIONS}
    
    expected_categories = {"omsorg", "skola", "halsa", "ekonomi", "miljo", "boende", "ovrig"}
    assert categories == expected_categories
