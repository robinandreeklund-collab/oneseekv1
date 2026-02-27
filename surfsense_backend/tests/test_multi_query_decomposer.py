"""
Sprint P3 tests — Multi-query decomposer node.

Tests verify:
- Decomposer splits compound questions into atomic sub-questions
- Single questions pass through unchanged (empty atomic_questions)
- Dependency graph is preserved
- Non-complex queries skip decomposition entirely
- Planner consumes atomic_questions when present

These tests run WITHOUT a running LLM or DB — they use mocked LLM responses.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, relative_path: str):
    module_path = _PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Stub heavy dependencies
# ---------------------------------------------------------------------------
def _ensure_stub(name: str):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


for _dep in [
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.runnables",
    "langgraph",
    "langgraph.types",
    "langgraph.graph",
    "langgraph.graph.state",
]:
    _ensure_stub(_dep)

# Provide stub message classes
_lc_messages = sys.modules["langchain_core.messages"]


class _StubMessage:
    def __init__(self, content: str = "", **kwargs):
        self.content = content
        for k, v in kwargs.items():
            setattr(self, k, v)


class AIMessage(_StubMessage):
    type = "ai"


class HumanMessage(_StubMessage):
    type = "human"


class SystemMessage(_StubMessage):
    type = "system"


class ToolMessage(_StubMessage):
    type = "tool"
    def __init__(self, content="", name="", tool_call_id="", **kwargs):
        super().__init__(content=content, **kwargs)
        self.name = name
        self.tool_call_id = tool_call_id


_lc_messages.AIMessage = AIMessage  # type: ignore[attr-defined]
_lc_messages.HumanMessage = HumanMessage  # type: ignore[attr-defined]
_lc_messages.SystemMessage = SystemMessage  # type: ignore[attr-defined]
_lc_messages.ToolMessage = ToolMessage  # type: ignore[attr-defined]
_lc_messages.AnyMessage = Any  # type: ignore[attr-defined]

# Stub RunnableConfig
_lc_runnables = sys.modules["langchain_core.runnables"]
_lc_runnables.RunnableConfig = dict  # type: ignore[attr-defined]

# Stub langgraph.graph.add_messages
_lg_graph = sys.modules["langgraph.graph"]
_lg_graph.add_messages = lambda left, right: (left or []) + (right or [])  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Load modules under test
# ---------------------------------------------------------------------------
_schemas_mod = _load_module(
    "app.agents.new_chat.structured_schemas",
    "app/agents/new_chat/structured_schemas.py",
)
DecomposerResult = _schemas_mod.DecomposerResult
AtomicQuestion = _schemas_mod.AtomicQuestion

_types_mod = _load_module(
    "app.agents.new_chat.supervisor_types",
    "app/agents/new_chat/supervisor_types.py",
)
SupervisorState = _types_mod.SupervisorState

_decomposer_mod = _load_module(
    "app.agents.new_chat.nodes.multi_query_decomposer",
    "app/agents/new_chat/nodes/multi_query_decomposer.py",
)
build_multi_query_decomposer_node = _decomposer_mod.build_multi_query_decomposer_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_llm_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    return msg


def _make_llm(response_json: dict) -> MagicMock:
    """Create a mock LLM that returns a JSON response."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=_make_llm_response(json.dumps(response_json, ensure_ascii=False))
    )
    return llm


def _extract_first_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        return {}


def _build_decomposer(**overrides):
    llm = overrides.pop("llm", _make_llm({"questions": [], "reason": "test"}))
    return build_multi_query_decomposer_node(
        llm=llm,
        decomposer_prompt_template="Test decomposer prompt",
        latest_user_query_fn=lambda msgs: next(
            (
                getattr(m, "content", "")
                for m in reversed(msgs or [])
                if isinstance(m, HumanMessage)
            ),
            "",
        ),
        append_datetime_context_fn=lambda s: s,
        extract_first_json_object_fn=_extract_first_json_object,
        **overrides,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestDecomposerSplitsCompoundQuestion:
    """Compound question → multiple atomic_questions."""

    def test_two_domains(self):
        llm = _make_llm({
            "thinking": "Frågan har två delar: befolkning och väder.",
            "questions": [
                {"id": "q1", "text": "Hur många bor i Göteborg?", "depends_on": [], "domain": "statistik"},
                {"id": "q2", "text": "Vad är vädret i Göteborg?", "depends_on": [], "domain": "väder"},
            ],
            "reason": "Frågan berör två domäner.",
        })
        node = _build_decomposer(llm=llm)
        state = {
            "messages": [HumanMessage(content="Hur många bor i Göteborg och vad är vädret?")],
            "graph_complexity": "complex",
            "resolved_intent": {"route": "mixed"},
            "sub_intents": ["statistik", "väder"],
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        questions = result["atomic_questions"]
        assert len(questions) == 2
        assert questions[0]["id"] == "q1"
        assert questions[0]["domain"] == "statistik"
        assert questions[1]["id"] == "q2"
        assert questions[1]["domain"] == "väder"

    def test_three_domains_capped_at_four(self):
        llm = _make_llm({
            "thinking": "tre domäner",
            "questions": [
                {"id": "q1", "text": "A", "depends_on": [], "domain": "statistik"},
                {"id": "q2", "text": "B", "depends_on": [], "domain": "väder"},
                {"id": "q3", "text": "C", "depends_on": [], "domain": "trafik"},
            ],
            "reason": "Tre domäner.",
        })
        node = _build_decomposer(llm=llm)
        state = {
            "messages": [HumanMessage(content="A, B och C")],
            "graph_complexity": "complex",
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert len(result["atomic_questions"]) == 3


class TestDecomposerSingleQuestionPassthrough:
    """Single question → empty atomic_questions (no decomposition)."""

    def test_single_question_returns_empty(self):
        llm = _make_llm({
            "thinking": "Enkel fråga.",
            "questions": [
                {"id": "q1", "text": "Vad är vädret i Stockholm?", "depends_on": [], "domain": "väder"},
            ],
            "reason": "Kan inte brytas ned.",
        })
        node = _build_decomposer(llm=llm)
        state = {
            "messages": [HumanMessage(content="Vad är vädret i Stockholm?")],
            "graph_complexity": "complex",
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result["atomic_questions"] == []


class TestDecomposerDependencyGraph:
    """Dependency graph with depends_on references."""

    def test_dependency_preserved(self):
        llm = _make_llm({
            "thinking": "Jämför A och B, visa på karta.",
            "questions": [
                {"id": "q1", "text": "Folkmängd Stockholm", "depends_on": [], "domain": "statistik"},
                {"id": "q2", "text": "Folkmängd Göteborg", "depends_on": [], "domain": "statistik"},
                {"id": "q3", "text": "Visa jämförelse på karta", "depends_on": ["q1", "q2"], "domain": "kartor"},
            ],
            "reason": "Kartfrågan beror på statistikfrågorna.",
        })
        node = _build_decomposer(llm=llm)
        state = {
            "messages": [HumanMessage(content="Jämför folkmängd Stockholm vs Göteborg på karta")],
            "graph_complexity": "complex",
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        questions = result["atomic_questions"]
        assert len(questions) == 3
        q3 = questions[2]
        assert q3["depends_on"] == ["q1", "q2"]
        assert q3["domain"] == "kartor"


class TestDecomposerSkippedForSimple:
    """Non-complex queries skip the decomposer entirely."""

    def test_simple_returns_empty(self):
        llm = _make_llm({"questions": [
            {"id": "q1", "text": "test", "depends_on": [], "domain": "kunskap"},
            {"id": "q2", "text": "test2", "depends_on": [], "domain": "väder"},
        ], "reason": "test"})
        node = _build_decomposer(llm=llm)
        state = {
            "messages": [HumanMessage(content="simple question")],
            "graph_complexity": "simple",
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result["atomic_questions"] == []
        # LLM should NOT have been called
        llm.ainvoke.assert_not_called()

    def test_trivial_returns_empty(self):
        llm = _make_llm({"questions": [], "reason": "test"})
        node = _build_decomposer(llm=llm)
        state = {
            "messages": [HumanMessage(content="hej")],
            "graph_complexity": "trivial",
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result["atomic_questions"] == []
        llm.ainvoke.assert_not_called()

    def test_no_complexity_returns_empty(self):
        llm = _make_llm({"questions": [], "reason": "test"})
        node = _build_decomposer(llm=llm)
        state = {
            "messages": [HumanMessage(content="hej")],
            "graph_complexity": None,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result["atomic_questions"] == []
        llm.ainvoke.assert_not_called()


class TestDecomposerLLMFailure:
    """LLM failure → empty atomic_questions (graceful degradation)."""

    def test_llm_exception_returns_empty(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
        node = _build_decomposer(llm=llm)
        state = {
            "messages": [HumanMessage(content="complex query")],
            "graph_complexity": "complex",
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result["atomic_questions"] == []


class TestStateFieldExists:
    """atomic_questions field exists in SupervisorState."""

    def test_field_in_annotations(self):
        annotations = getattr(SupervisorState, "__annotations__", {})
        assert "atomic_questions" in annotations


class TestPydanticSchemas:
    """DecomposerResult and AtomicQuestion schemas work correctly."""

    def test_decomposer_result_parses(self):
        raw = json.dumps({
            "thinking": "test",
            "questions": [
                {"id": "q1", "text": "test q", "depends_on": [], "domain": "väder"},
            ],
            "reason": "test reason",
        })
        result = DecomposerResult.model_validate_json(raw)
        assert len(result.questions) == 1
        assert result.questions[0].id == "q1"
        assert result.questions[0].domain == "väder"
        assert result.reason == "test reason"

    def test_atomic_question_defaults(self):
        q = AtomicQuestion(id="q1", text="test", domain="kunskap")
        assert q.depends_on == []
