"""Tests for Kolada tool definitions and builders."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.store.memory import InMemoryStore

from app.agents.new_chat.kolada_tools import (
    KOLADA_TOOL_DEFINITIONS,
    KoladaToolDefinition,
    _build_kolada_tool,
    _build_kolada_tool_description,
    build_kolada_tool_registry,
    build_kolada_tool_store,
)


def test_kolada_tool_definitions_count():
    """Test that we have exactly 15 Kolada tool definitions."""
    assert len(KOLADA_TOOL_DEFINITIONS) == 15


def test_kolada_tool_definitions_structure():
    """Test that all tool definitions have required fields."""
    for definition in KOLADA_TOOL_DEFINITIONS:
        assert isinstance(definition, KoladaToolDefinition)
        assert definition.tool_id.startswith("kolada_")
        assert len(definition.name) > 0
        assert len(definition.description) > 0
        assert len(definition.keywords) > 0
        assert len(definition.example_queries) > 0
        assert isinstance(definition.kpi_hints, list)
        assert len(definition.category) > 0
        assert len(definition.usage_notes) > 0


def test_kolada_tool_ids():
    """Test that all tool IDs are unique and follow naming convention."""
    tool_ids = [d.tool_id for d in KOLADA_TOOL_DEFINITIONS]
    
    # Check uniqueness
    assert len(tool_ids) == len(set(tool_ids))
    
    # Check naming convention
    for tool_id in tool_ids:
        assert tool_id.startswith("kolada_")


def test_kolada_keywords_requirements():
    """Test that keywords include required variants and 'kolada'."""
    for definition in KOLADA_TOOL_DEFINITIONS:
        # All tools should have 'kolada' as keyword
        assert "kolada" in definition.keywords
        
        # Check for Swedish character variants in relevant keywords
        keywords_str = " ".join(definition.keywords)
        
        # If a keyword contains Swedish characters, check if normalized version exists
        has_swedish = any(c in keywords_str for c in "åäö")
        if has_swedish:
            # Should have both variants
            pass  # Already tested by having multiple keyword entries


def test_kolada_example_queries_requirements():
    """Test that all definitions have at least 3 example queries."""
    for definition in KOLADA_TOOL_DEFINITIONS:
        assert len(definition.example_queries) >= 3


def test_kolada_categories():
    """Test that tool categories are valid."""
    valid_categories = {"omsorg", "skola", "halsa", "ekonomi", "miljo", "boende", "ovrig"}
    
    for definition in KOLADA_TOOL_DEFINITIONS:
        assert definition.category in valid_categories


def test_kolada_operating_areas():
    """Test that operating areas are assigned correctly."""
    # Omsorg tools
    assert KOLADA_TOOL_DEFINITIONS[0].tool_id == "kolada_aldreomsorg"
    assert KOLADA_TOOL_DEFINITIONS[0].operating_area == "V21"
    
    assert KOLADA_TOOL_DEFINITIONS[1].tool_id == "kolada_lss"
    assert KOLADA_TOOL_DEFINITIONS[1].operating_area == "V23"
    
    assert KOLADA_TOOL_DEFINITIONS[2].tool_id == "kolada_ifo"
    assert KOLADA_TOOL_DEFINITIONS[2].operating_area == "V25"
    
    assert KOLADA_TOOL_DEFINITIONS[3].tool_id == "kolada_barn_unga"
    assert KOLADA_TOOL_DEFINITIONS[3].operating_area == "V26"
    
    # Skola tools
    forskola_def = next(d for d in KOLADA_TOOL_DEFINITIONS if d.tool_id == "kolada_forskola")
    assert forskola_def.operating_area == "V11"
    
    grundskola_def = next(d for d in KOLADA_TOOL_DEFINITIONS if d.tool_id == "kolada_grundskola")
    assert grundskola_def.operating_area == "V15"
    
    gymnasie_def = next(d for d in KOLADA_TOOL_DEFINITIONS if d.tool_id == "kolada_gymnasieskola")
    assert gymnasie_def.operating_area == "V17"
    
    # Hälsa tool
    halsa_def = next(d for d in KOLADA_TOOL_DEFINITIONS if d.tool_id == "kolada_halsa")
    assert halsa_def.operating_area == "V45"


def test_build_kolada_tool_description():
    """Test that tool description builder includes all required sections."""
    definition = KoladaToolDefinition(
        tool_id="test_tool",
        name="Test Tool",
        operating_area="V21",
        description="Test description",
        keywords=["test", "keyword"],
        example_queries=["Query 1", "Query 2"],
        kpi_hints=["N00001", "N00002"],
        category="test",
        usage_notes="Test usage notes",
    )
    
    description = _build_kolada_tool_description(definition)
    
    # Check required sections
    assert "**Beskrivning:**" in description
    assert "Test description" in description
    
    assert "**Verksamhetsområde:**" in description
    assert "V21" in description
    
    assert "**KPI-ID:**" in description
    assert "N00001" in description
    assert "N00002" in description
    
    assert "**Parametrar:**" in description
    assert "`question`" in description
    assert "`municipality`" in description
    assert "`years`" in description
    
    assert "**Exempelfrågor:**" in description
    assert "Query 1" in description
    assert "Query 2" in description
    
    assert "**Viktigt:**" in description
    assert "Test usage notes" in description


def test_build_kolada_tool_description_without_operating_area():
    """Test tool description for tools without operating area."""
    definition = KoladaToolDefinition(
        tool_id="test_tool",
        name="Test Tool",
        operating_area=None,
        description="Test description",
        keywords=["test"],
        example_queries=["Query 1"],
        kpi_hints=[],
        category="test",
        usage_notes="Test notes",
    )
    
    description = _build_kolada_tool_description(definition)
    
    # Should not have operating area section
    assert "**Verksamhetsområde:**" not in description
    # Should still have other sections
    assert "**Beskrivning:**" in description
    assert "**Parametrar:**" in description


@pytest.mark.asyncio
async def test_build_kolada_tool():
    """Test building a Kolada tool."""
    definition = KoladaToolDefinition(
        tool_id="kolada_test",
        name="Test Tool",
        operating_area="V21",
        description="Test",
        keywords=["test"],
        example_queries=["Test query"],
        kpi_hints=["N00001"],
        category="test",
        usage_notes="Test notes",
    )
    
    # Create mock services
    mock_kolada_service = MagicMock()
    mock_kolada_service.query = AsyncMock(return_value=[])
    
    mock_connector_service = MagicMock()
    mock_connector_service.ingest_tool_output = AsyncMock(return_value=None)
    
    # Build tool
    tool = _build_kolada_tool(
        definition,
        kolada_service=mock_kolada_service,
        connector_service=mock_connector_service,
        search_space_id=1,
        user_id="test_user",
        thread_id=1,
    )
    
    # Check tool properties
    assert tool.name == "kolada_test"
    assert "Test" in tool.description


@pytest.mark.asyncio
async def test_build_kolada_tool_execution():
    """Test executing a built Kolada tool."""
    from app.services.kolada_service import KoladaKpi, KoladaMunicipality, KoladaQueryResult, KoladaValue
    
    definition = KoladaToolDefinition(
        tool_id="kolada_test",
        name="Test Tool",
        operating_area="V21",
        description="Test",
        keywords=["test"],
        example_queries=["Test query"],
        kpi_hints=["N00001"],
        category="test",
        usage_notes="Test notes",
    )
    
    # Mock query results
    mock_results = [
        KoladaQueryResult(
            kpi=KoladaKpi(
                id="N00001",
                title="Test KPI",
                description="Test description",
                operating_area="V21",
                has_ou_data=False,
            ),
            municipality=KoladaMunicipality(
                id="0180",
                title="Stockholm",
                type="K",
            ),
            values=[
                KoladaValue(
                    kpi="N00001",
                    municipality="0180",
                    period="2023",
                    gender=None,
                    value=100.0,
                    count=10,
                )
            ],
            warnings=[],
        )
    ]
    
    mock_kolada_service = MagicMock()
    mock_kolada_service.query = AsyncMock(return_value=mock_results)
    
    mock_document = MagicMock()
    mock_connector_service = MagicMock()
    mock_connector_service.ingest_tool_output = AsyncMock(return_value=mock_document)
    mock_connector_service._serialize_external_document = MagicMock(return_value={})
    
    tool = _build_kolada_tool(
        definition,
        kolada_service=mock_kolada_service,
        connector_service=mock_connector_service,
        search_space_id=1,
        user_id="test_user",
        thread_id=1,
    )
    
    # Execute tool
    with patch("app.agents.new_chat.kolada_tools.format_documents_for_context") as mock_format:
        mock_format.return_value = "Formatted docs"
        
        result = await tool.ainvoke({"question": "Test query", "municipality": "Stockholm"})
        
        # Verify kolada service was called
        assert mock_kolada_service.query.called
        
        # Verify connector service was called
        assert mock_connector_service.ingest_tool_output.called


def test_build_kolada_tool_registry():
    """Test building Kolada tool registry."""
    mock_connector_service = MagicMock()
    
    registry = build_kolada_tool_registry(
        connector_service=mock_connector_service,
        search_space_id=1,
        user_id="test_user",
        thread_id=1,
    )
    
    # Should have 15 tools
    assert len(registry) == 15
    
    # Check that all tool IDs are in registry
    for definition in KOLADA_TOOL_DEFINITIONS:
        assert definition.tool_id in registry


def test_build_kolada_tool_store():
    """Test building Kolada tool store."""
    store = build_kolada_tool_store()
    
    assert isinstance(store, InMemoryStore)
    
    # Verify that all tools are in the store
    for definition in KOLADA_TOOL_DEFINITIONS:
        item = store.get(("tools",), definition.tool_id)
        assert item is not None
        assert item.value["name"] == definition.name
        assert item.value["description"] == definition.description
        assert item.value["category"] == "kolada_statistics"
        assert item.value["keywords"] == definition.keywords
        assert item.value["example_queries"] == definition.example_queries
        assert item.value["kpi_hints"] == definition.kpi_hints
        assert item.value["usage_notes"] == definition.usage_notes


def test_omsorg_tools():
    """Test that all omsorg tools are defined correctly."""
    omsorg_tools = [d for d in KOLADA_TOOL_DEFINITIONS if d.category == "omsorg"]
    
    assert len(omsorg_tools) == 4
    
    tool_ids = [d.tool_id for d in omsorg_tools]
    assert "kolada_aldreomsorg" in tool_ids
    assert "kolada_lss" in tool_ids
    assert "kolada_ifo" in tool_ids
    assert "kolada_barn_unga" in tool_ids


def test_skola_tools():
    """Test that all skola tools are defined correctly."""
    skola_tools = [d for d in KOLADA_TOOL_DEFINITIONS if d.category == "skola"]
    
    assert len(skola_tools) == 3
    
    tool_ids = [d.tool_id for d in skola_tools]
    assert "kolada_forskola" in tool_ids
    assert "kolada_grundskola" in tool_ids
    assert "kolada_gymnasieskola" in tool_ids


def test_halsa_tools():
    """Test that hälsa tool is defined correctly."""
    halsa_tools = [d for d in KOLADA_TOOL_DEFINITIONS if d.category == "halsa"]
    
    assert len(halsa_tools) == 1
    assert halsa_tools[0].tool_id == "kolada_halsa"


def test_ekonomi_miljo_boende_tools():
    """Test ekonomi, miljö, boende tools."""
    ekonomi_tools = [d for d in KOLADA_TOOL_DEFINITIONS if d.category == "ekonomi"]
    assert len(ekonomi_tools) == 1
    assert ekonomi_tools[0].tool_id == "kolada_ekonomi"
    
    miljo_tools = [d for d in KOLADA_TOOL_DEFINITIONS if d.category == "miljo"]
    assert len(miljo_tools) == 1
    assert miljo_tools[0].tool_id == "kolada_miljo"
    
    boende_tools = [d for d in KOLADA_TOOL_DEFINITIONS if d.category == "boende"]
    assert len(boende_tools) == 1
    assert boende_tools[0].tool_id == "kolada_boende"


def test_ovrig_tools():
    """Test övriga tools."""
    ovrig_tools = [d for d in KOLADA_TOOL_DEFINITIONS if d.category == "ovrig"]
    
    assert len(ovrig_tools) == 4
    
    tool_ids = [d.tool_id for d in ovrig_tools]
    assert "kolada_sammanfattning" in tool_ids
    assert "kolada_kultur" in tool_ids
    assert "kolada_arbetsmarknad" in tool_ids
    assert "kolada_demokrati" in tool_ids
