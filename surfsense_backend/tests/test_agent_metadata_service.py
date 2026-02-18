from app.services.agent_metadata_service import (
    agent_metadata_payload_equal,
    get_default_agent_metadata,
    normalize_agent_metadata_payload,
)


def test_default_agent_metadata_contains_expected_agents():
    defaults = get_default_agent_metadata()
    assert "knowledge" in defaults
    assert "weather" in defaults
    assert defaults["knowledge"]["description"]
    assert isinstance(defaults["knowledge"]["keywords"], list)


def test_normalize_agent_metadata_uses_default_fields_when_missing():
    defaults = get_default_agent_metadata()
    knowledge_default = defaults["knowledge"]
    normalized = normalize_agent_metadata_payload(
        {"agent_id": "knowledge", "description": "Ny beskrivning"},
        agent_id="knowledge",
        default_payload=knowledge_default,
    )
    assert normalized["agent_id"] == "knowledge"
    assert normalized["description"] == "Ny beskrivning"
    assert normalized["label"] == knowledge_default["label"]
    assert normalized["keywords"] == knowledge_default["keywords"]
    assert normalized["prompt_key"] == knowledge_default["prompt_key"]


def test_agent_metadata_payload_equal_normalizes_keywords():
    left = {
        "agent_id": "weather",
        "label": "Weather",
        "description": "Test",
        "keywords": ["SMHI", "vader", "smhi"],
    }
    right = {
        "agent_id": "weather",
        "label": "Weather",
        "description": "Test",
        "keywords": ["SMHI", "vader"],
    }
    assert agent_metadata_payload_equal(left, right)
