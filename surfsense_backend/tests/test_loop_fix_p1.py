"""
Sprint P1 tests — Loop-fix, guard_finalized, total_steps, adaptive critic,
response layer ordering, and THINK_ON_TOOL_CALLS.

These tests verify the P1 changes WITHOUT requiring a running LLM or DB.
They use isolated module loading (same pattern as existing test suite).
"""
from __future__ import annotations

import asyncio
import importlib.util
import re
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
# Stub heavy dependencies so we can import node modules in isolation
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

# Provide AIMessage / HumanMessage / SystemMessage stubs
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


_lc_messages.AIMessage = AIMessage
_lc_messages.HumanMessage = HumanMessage
_lc_messages.SystemMessage = SystemMessage
_lc_messages.ToolMessage = ToolMessage

# RunnableConfig stub
_lc_runnables = sys.modules["langchain_core.runnables"]
_lc_runnables.RunnableConfig = dict


# ---------------------------------------------------------------------------
# Load the modules under test
# ---------------------------------------------------------------------------
critic_mod = _load_module(
    "critic_test_mod",
    "app/agents/new_chat/nodes/critic.py",
)
smart_critic_mod = _load_module(
    "smart_critic_test_mod",
    "app/agents/new_chat/nodes/smart_critic.py",
)
system_prompt_mod = _load_module(
    "system_prompt_test_mod",
    "app/agents/new_chat/system_prompt.py",
)

build_critic_node = critic_mod.build_critic_node
build_smart_critic_node = smart_critic_mod.build_smart_critic_node
inject_core_prompt = system_prompt_mod.inject_core_prompt
SURFSENSE_CORE_GLOBAL_PROMPT = system_prompt_mod.SURFSENSE_CORE_GLOBAL_PROMPT
SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK = system_prompt_mod.SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK


# ---------------------------------------------------------------------------
# Helpers to build a critic for testing
# ---------------------------------------------------------------------------
def _make_critic(max_replan=2, max_total_steps=12, llm_decision="ok"):
    """Create a critic_node that returns a canned LLM decision."""
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = MagicMock(
        content=f'{{"decision": "{llm_decision}"}}'
    )

    return build_critic_node(
        llm=mock_llm,
        critic_gate_prompt_template="Evaluate: {resolved_today} {resolved_time}",
        loop_guard_template="Loop guard: {preview}",
        default_loop_guard_message="Default fallback.",
        max_replan_attempts=max_replan,
        latest_user_query_fn=lambda msgs: "test query",
        append_datetime_context_fn=lambda p: p,
        extract_first_json_object_fn=lambda s: (
            {"decision": llm_decision}
            if llm_decision
            else {}
        ),
        render_guard_message_fn=lambda t, p: t or "Fallback text.",
        max_total_steps=max_total_steps,
    )


# ===================================================================
# P1.1: guard_finalized prevents critic from overriding
# ===================================================================
class TestGuardFinalized:
    def test_guard_finalized_prevents_critic_override(self):
        """When guard_finalized=True and final_response exists,
        critic must return 'ok' regardless of LLM opinion."""
        critic = _make_critic(llm_decision="needs_more")
        state = {
            "guard_finalized": True,
            "final_agent_response": "Guard produced this answer.",
            "final_response": "Guard produced this answer.",
            "replan_count": 0,
            "total_steps": 5,
            "critic_history": [],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
        }
        result = asyncio.run(critic(state))
        assert result["critic_decision"] == "ok"
        assert result["final_response"] == "Guard produced this answer."
        assert result["orchestration_phase"] == "finalize"

    def test_guard_finalized_false_allows_needs_more(self):
        """When guard_finalized is False, critic CAN return needs_more."""
        critic = _make_critic(llm_decision="needs_more")
        state = {
            "guard_finalized": False,
            "final_agent_response": "Some response.",
            "final_response": "Some response.",
            "replan_count": 0,
            "total_steps": 3,
            "critic_history": [],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
        }
        result = asyncio.run(critic(state))
        assert result["critic_decision"] == "needs_more"

    def test_guard_finalized_no_response_delegates(self):
        """If guard_finalized=True but final_response is empty,
        critic falls through to normal logic."""
        critic = _make_critic(llm_decision="ok")
        state = {
            "guard_finalized": True,
            "final_agent_response": "",
            "final_response": "",
            "replan_count": 0,
            "total_steps": 3,
            "critic_history": [],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
            "guard_parallel_preview": [],
        }
        result = asyncio.run(critic(state))
        # Should still produce a decision (needs_more since no response)
        assert result["critic_decision"] == "needs_more"


# ===================================================================
# P1.2: total_steps hard cap
# ===================================================================
class TestTotalSteps:
    def test_total_steps_max_forces_synthesis_with_response(self):
        """At total_steps >= max, critic returns ok even if LLM says needs_more."""
        critic = _make_critic(llm_decision="needs_more", max_total_steps=12)
        state = {
            "guard_finalized": False,
            "final_agent_response": "Accumulated answer.",
            "final_response": "Accumulated answer.",
            "replan_count": 0,
            "total_steps": 12,
            "critic_history": [],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
        }
        result = asyncio.run(critic(state))
        assert result["critic_decision"] == "ok"
        assert result["final_response"] == "Accumulated answer."

    def test_total_steps_max_forces_synthesis_no_response(self):
        """At total_steps >= max without response, critic produces fallback."""
        critic = _make_critic(llm_decision="needs_more", max_total_steps=12)
        state = {
            "guard_finalized": False,
            "final_agent_response": "",
            "final_response": "",
            "replan_count": 0,
            "total_steps": 15,
            "critic_history": [],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
            "guard_parallel_preview": [],
        }
        result = asyncio.run(critic(state))
        assert result["critic_decision"] == "ok"
        # Should have a fallback message
        assert result.get("final_response")

    def test_total_steps_below_max_normal_behavior(self):
        """Below max_total_steps, critic operates normally."""
        critic = _make_critic(llm_decision="needs_more", max_total_steps=12)
        state = {
            "guard_finalized": False,
            "final_agent_response": "Partial.",
            "final_response": "Partial.",
            "replan_count": 0,
            "total_steps": 5,
            "critic_history": [],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
        }
        result = asyncio.run(critic(state))
        assert result["critic_decision"] == "needs_more"


# ===================================================================
# P1.2: critic_history prevents identical decisions
# ===================================================================
class TestCriticHistory:
    def test_two_consecutive_needs_more_forces_ok(self):
        """After 2 recent needs_more in history, critic forces ok."""
        critic = _make_critic(llm_decision="needs_more")
        state = {
            "guard_finalized": False,
            "final_agent_response": "Some answer.",
            "final_response": "Some answer.",
            "replan_count": 0,
            "total_steps": 5,
            "critic_history": [
                {"decision": "needs_more", "reason": "test", "step": 3},
                {"decision": "needs_more", "reason": "test", "step": 4},
            ],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
        }
        result = asyncio.run(critic(state))
        assert result["critic_decision"] == "ok"

    def test_one_needs_more_allows_another(self):
        """Single needs_more in history allows another."""
        critic = _make_critic(llm_decision="needs_more")
        state = {
            "guard_finalized": False,
            "final_agent_response": "Some answer.",
            "final_response": "Some answer.",
            "replan_count": 0,
            "total_steps": 5,
            "critic_history": [
                {"decision": "needs_more", "reason": "test", "step": 4},
            ],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
        }
        result = asyncio.run(critic(state))
        assert result["critic_decision"] == "needs_more"

    def test_history_updated_on_every_decision(self):
        """critic_history grows with every critic call."""
        critic = _make_critic(llm_decision="ok")
        state = {
            "guard_finalized": False,
            "final_agent_response": "Answer.",
            "final_response": "Answer.",
            "replan_count": 0,
            "total_steps": 3,
            "critic_history": [],
            "messages": [HumanMessage(content="test")],
            "graph_complexity": "complex",
        }
        result = asyncio.run(critic(state))
        assert len(result.get("critic_history", [])) == 1
        assert result["critic_history"][0]["decision"] == "ok"


# ===================================================================
# P1.3: Response layer streaming-ordning
# (stream_new_chat.py has too many imports; verify via file content)
# ===================================================================
class TestResponseLayerStreaming:
    @pytest.fixture(autouse=True)
    def _read_stream_file(self):
        self._stream_content = (
            _PROJECT_ROOT / "app/tasks/chat/stream_new_chat.py"
        ).read_text()

    def test_synthesizer_in_internal_pipeline(self):
        """synthesizer must appear in _INTERNAL_PIPELINE_CHAIN_TOKENS."""
        # Find the internal tuple (greedy to capture multi-line with comments)
        m = re.search(
            r"_INTERNAL_PIPELINE_CHAIN_TOKENS\s*=\s*\((.+?)\n\)",
            self._stream_content,
            re.DOTALL,
        )
        assert m, "_INTERNAL_PIPELINE_CHAIN_TOKENS not found"
        block = m.group(1)
        assert '"synthesizer"' in block
        assert '"progressive_synthesizer"' in block

    def test_synthesizer_not_in_output_pipeline(self):
        """synthesizer must NOT appear in _OUTPUT_PIPELINE_CHAIN_TOKENS."""
        m = re.search(
            r"_OUTPUT_PIPELINE_CHAIN_TOKENS\s*=\s*\((.*?)\)",
            self._stream_content,
            re.DOTALL,
        )
        assert m, "_OUTPUT_PIPELINE_CHAIN_TOKENS not found"
        block = m.group(1)
        assert '"synthesizer"' not in block
        assert '"progressive_synthesizer"' not in block

    def test_response_layer_is_in_output_pipeline(self):
        """response_layer must be in output pipeline."""
        m = re.search(
            r"_OUTPUT_PIPELINE_CHAIN_TOKENS\s*=\s*\((.*?)\)",
            self._stream_content,
            re.DOTALL,
        )
        assert m
        assert '"response_layer"' in m.group(1)

    def test_executor_in_internal_pipeline(self):
        """executor must be classified as internal."""
        m = re.search(
            r"_INTERNAL_PIPELINE_CHAIN_TOKENS\s*=\s*\((.*?)\)",
            self._stream_content,
            re.DOTALL,
        )
        assert m
        assert '"executor"' in m.group(1)


# ===================================================================
# P1.4: THINK_ON_TOOL_CALLS toggle
# ===================================================================
class TestThinkOnToolCalls:
    def test_inject_core_prompt_with_think(self):
        """Default inject_core_prompt includes think instructions."""
        result = inject_core_prompt(
            SURFSENSE_CORE_GLOBAL_PROMPT, "Agent prompt."
        )
        assert "<think>" in result
        assert "KRITISKT" in result

    def test_inject_core_prompt_without_think(self):
        """inject_core_prompt with include_think_instructions=False strips think."""
        result = inject_core_prompt(
            SURFSENSE_CORE_GLOBAL_PROMPT,
            "Agent prompt.",
            include_think_instructions=False,
        )
        assert "KRITISKT" not in result
        assert "<think>" not in result
        # But core_directives should still be there
        assert "core_directives" in result
        assert "Agent prompt." in result

    def test_no_think_prompt_has_no_think_instructions(self):
        """SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK should not mention <think>."""
        assert "<think>" not in SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK
        assert "KRITISKT" not in SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK
        # But should still have date placeholders
        assert "resolved_today" in SURFSENSE_CORE_GLOBAL_PROMPT_NO_THINK

    def test_think_filter_class_exists_in_stream(self):
        """_ThinkStreamFilter class must exist in stream_new_chat.py."""
        stream_content = (
            _PROJECT_ROOT / "app/tasks/chat/stream_new_chat.py"
        ).read_text()
        assert "class _ThinkStreamFilter" in stream_content
        # It should have an assume_think parameter
        assert "assume_think" in stream_content


# ===================================================================
# P1.2: smart_critic also respects guard_finalized
# ===================================================================
class TestSmartCriticGuardFinalized:
    def test_smart_critic_guard_finalized(self):
        """smart_critic respects guard_finalized=True."""
        # The fallback critic (should NOT be called if guard_finalized triggers)
        fallback = AsyncMock(return_value={"critic_decision": "needs_more"})

        smart_critic = build_smart_critic_node(
            fallback_critic_node=fallback,
            contract_from_payload_fn=lambda p: p or {},
            latest_user_query_fn=lambda msgs: "test",
            max_replan_attempts=2,
        )

        state = {
            "guard_finalized": True,
            "final_agent_response": "Guard response.",
            "final_response": "Guard response.",
            "replan_count": 0,
            "total_steps": 5,
            "critic_history": [],
            "messages": [HumanMessage(content="test")],
            "step_results": [],
        }
        result = asyncio.run(smart_critic(state))
        assert result["critic_decision"] == "ok"
        assert result["final_response"] == "Guard response."
        # Fallback should NOT have been called
        fallback.assert_not_called()


# ===================================================================
# P1: SupervisorState has new fields (verified via file content)
# ===================================================================
class TestStateFields:
    def test_supervisor_state_has_new_fields(self):
        """SupervisorState must include guard_finalized, total_steps, critic_history."""
        content = (
            _PROJECT_ROOT / "app/agents/new_chat/supervisor_types.py"
        ).read_text()
        assert "guard_finalized" in content
        assert "total_steps" in content
        assert "critic_history" in content

    def test_max_total_steps_constant_exists(self):
        """MAX_TOTAL_STEPS must be defined in supervisor_constants."""
        content = (
            _PROJECT_ROOT / "app/agents/new_chat/supervisor_constants.py"
        ).read_text()
        assert "MAX_TOTAL_STEPS" in content
        assert "MAX_TOTAL_STEPS = 12" in content
