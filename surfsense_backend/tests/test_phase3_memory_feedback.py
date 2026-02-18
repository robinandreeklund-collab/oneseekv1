from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import time


def _load_module(module_name: str, relative_path: str):
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


episodic_memory = _load_module(
    "episodic_memory_phase3_test_module",
    "app/agents/new_chat/episodic_memory.py",
)
retrieval_feedback = _load_module(
    "retrieval_feedback_phase3_test_module",
    "app/agents/new_chat/retrieval_feedback.py",
)


def test_episodic_memory_put_get_hit() -> None:
    store = episodic_memory.EpisodicMemoryStore(max_entries=10)
    store.put(
        tool_id="smhi_weather",
        query="vader i stockholm",
        value={"response": "soligt"},
        ttl_seconds=60,
    )
    cached = store.get(tool_id="smhi_weather", query="vader i stockholm")
    assert isinstance(cached, dict)
    assert cached.get("response") == "soligt"


def test_episodic_memory_expiry() -> None:
    store = episodic_memory.EpisodicMemoryStore(max_entries=10)
    store.put(
        tool_id="trafiklab_route",
        query="nar gar taget",
        value={"response": "10:30"},
        ttl_seconds=1,
    )
    time.sleep(1.05)
    cached = store.get(tool_id="trafiklab_route", query="nar gar taget")
    assert cached is None


def test_episodic_memory_lru_eviction() -> None:
    store = episodic_memory.EpisodicMemoryStore(max_entries=2)
    store.put(tool_id="a", query="q1", value={"v": 1}, ttl_seconds=30)
    store.put(tool_id="b", query="q2", value={"v": 2}, ttl_seconds=30)
    store.put(tool_id="c", query="q3", value={"v": 3}, ttl_seconds=30)
    assert store.get(tool_id="a", query="q1") is None
    assert store.get(tool_id="b", query="q2") is not None
    assert store.get(tool_id="c", query="q3") is not None


def test_infer_ttl_seconds_domain_specific() -> None:
    assert episodic_memory.infer_ttl_seconds(tool_id="smhi_weather", agent_name="weather") == 300
    assert episodic_memory.infer_ttl_seconds(tool_id="trafiklab_route", agent_name="trafik") == 120
    assert episodic_memory.infer_ttl_seconds(tool_id="scb_befolkning", agent_name="statistics") == 86400


def test_retrieval_feedback_boost_positive_and_negative() -> None:
    store = retrieval_feedback.RetrievalFeedbackStore(max_patterns=100)
    for _ in range(3):
        store.record(tool_id="smhi_weather", query="vader i malmo", success=True)
    store.record(tool_id="smhi_weather", query="vader i malmo", success=False)
    positive_boost = store.get_boost(tool_id="smhi_weather", query="vader i malmo")
    assert positive_boost > 0.0

    for _ in range(5):
        store.record(tool_id="smhi_weather", query="vader i malmo", success=False)
    negative_boost = store.get_boost(tool_id="smhi_weather", query="vader i malmo")
    assert negative_boost < 0.0


def test_retrieval_feedback_boost_bounds() -> None:
    store = retrieval_feedback.RetrievalFeedbackStore(max_patterns=100)
    for _ in range(100):
        store.record(tool_id="t", query="q", success=True)
    assert -2.0 <= store.get_boost(tool_id="t", query="q") <= 2.0
    for _ in range(400):
        store.record(tool_id="t", query="q", success=False)
    assert -2.0 <= store.get_boost(tool_id="t", query="q") <= 2.0


def test_retrieval_feedback_hydrate_rows_merges_counts() -> None:
    store = retrieval_feedback.RetrievalFeedbackStore(max_patterns=100)
    store.record(tool_id="smhi_weather", query="vader i malmo", success=True)
    query_hash = retrieval_feedback.query_pattern_hash("vader i malmo")
    applied = store.hydrate_rows(
        [
            {
                "tool_id": "smhi_weather",
                "query_pattern_hash": query_hash,
                "successes": 3,
                "failures": 1,
            }
        ]
    )
    assert applied == 1
    snapshot = store.snapshot()
    assert snapshot["count"] == 1
    row = snapshot["rows"][0]
    assert row["successes"] == 3
    assert row["failures"] == 1
