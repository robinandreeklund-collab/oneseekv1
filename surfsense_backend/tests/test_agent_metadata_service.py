import importlib.util

import pytest

if importlib.util.find_spec("sqlalchemy") is None:  # pragma: no cover - optional dependency
    pytestmark = pytest.mark.skip(reason="sqlalchemy is not installed")
else:
    from app.services.agent_metadata_service import (
        agent_metadata_payload_equal,
        get_default_agent_metadata,
        normalize_agent_metadata_payload,
    )


def test_default_agent_metadata_contains_expected_agents():
    defaults = get_default_agent_metadata()
    assert "kunskap" in defaults
    assert "väder" in defaults
    assert defaults["kunskap"]["description"]
    assert isinstance(defaults["kunskap"]["keywords"], list)


def test_normalize_agent_metadata_uses_default_fields_when_missing():
    defaults = get_default_agent_metadata()
    kunskap_default = defaults["kunskap"]
    normalized = normalize_agent_metadata_payload(
        {"agent_id": "kunskap", "description": "Ny beskrivning"},
        agent_id="kunskap",
        default_payload=kunskap_default,
    )
    assert normalized["agent_id"] == "kunskap"
    assert normalized["description"] == "Ny beskrivning"
    assert normalized["label"] == kunskap_default["label"]
    assert normalized["keywords"] == kunskap_default["keywords"]
    assert normalized["prompt_key"] == kunskap_default["prompt_key"]


def test_agent_metadata_payload_equal_normalizes_keywords():
    left = {
        "agent_id": "väder",
        "label": "Väder",
        "description": "Test",
        "keywords": ["SMHI", "vader", "smhi"],
    }
    right = {
        "agent_id": "väder",
        "label": "Väder",
        "description": "Test",
        "keywords": ["SMHI", "vader"],
    }
    assert agent_metadata_payload_equal(left, right)


def test_default_agent_metadata_contains_identity_fields():
    defaults = get_default_agent_metadata()
    for agent_id, payload in defaults.items():
        assert "main_identifier" in payload, f"{agent_id} missing main_identifier"
        assert "core_activity" in payload, f"{agent_id} missing core_activity"
        assert "unique_scope" in payload, f"{agent_id} missing unique_scope"
        assert "geographic_scope" in payload, f"{agent_id} missing geographic_scope"
        assert "excludes" in payload, f"{agent_id} missing excludes"
        assert isinstance(payload["excludes"], list), f"{agent_id} excludes not a list"


def test_normalize_agent_metadata_preserves_identity_fields():
    normalized = normalize_agent_metadata_payload(
        {
            "agent_id": "test",
            "label": "Test",
            "description": "Test agent",
            "keywords": ["test"],
            "main_identifier": "Testagent",
            "core_activity": "Testar saker",
            "unique_scope": "Enbart testning",
            "geographic_scope": "Sverige",
            "excludes": ["produktion", "drift"],
        },
        agent_id="test",
    )
    assert normalized["main_identifier"] == "Testagent"
    assert normalized["core_activity"] == "Testar saker"
    assert normalized["unique_scope"] == "Enbart testning"
    assert normalized["geographic_scope"] == "Sverige"
    assert normalized["excludes"] == ["produktion", "drift"]


def test_normalize_agent_metadata_identity_fields_fallback_to_defaults():
    defaults = get_default_agent_metadata()
    vader_default = defaults["väder"]
    normalized = normalize_agent_metadata_payload(
        {"agent_id": "väder", "description": "Ny beskrivning"},
        agent_id="väder",
        default_payload=vader_default,
    )
    assert normalized["main_identifier"] == vader_default["main_identifier"]
    assert normalized["core_activity"] == vader_default["core_activity"]
    assert normalized["excludes"] == vader_default["excludes"]
