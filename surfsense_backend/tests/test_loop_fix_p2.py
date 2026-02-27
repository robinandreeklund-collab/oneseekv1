"""
Sprint P2 tests — Studio node mapping, env-driven configuration, executor
pipeline classification, and improved no-progress fingerprinting.

These tests verify the P2 changes WITHOUT requiring a running LLM or DB.
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Module loading helpers (same pattern as P1 tests)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_stub(name: str):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


# Stub heavy dependencies so we can import modules in isolation
for _dep in [
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.runnables",
    "langchain_core.runnables.base",
    "langchain_core.tools",
    "langchain_core.tools.base",
    "langchain_core.prompt_values",
    "langchain_core.messages.base",
    "langchain_core.utils",
    "langchain_core.utils.function_calling",
    "langgraph",
    "langgraph.types",
    "langgraph.graph",
    "langgraph.graph.state",
    "langgraph.checkpoint",
    "langgraph.checkpoint.memory",
    "langgraph.prebuilt",
    "langgraph.prebuilt.tool_node",
    "langgraph_bigtool",
    "langgraph_bigtool.graph",
    "pydantic",
    "sqlalchemy",
    "sqlalchemy.future",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
]:
    _ensure_stub(_dep)

# Provide minimal message stubs
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
_lc_messages.BaseMessage = _StubMessage

_lc_runnables = sys.modules["langchain_core.runnables"]
_lc_runnables.RunnableConfig = dict


# ===================================================================
# P2.1: Studio node mapping completeness
# ===================================================================
class TestStudioNodeMapping:
    """All supervisor graph nodes must appear in the Studio node mapping."""

    # Complete list of nodes from the supervisor graph builder
    # (see supervisor_agent.py graph_builder.add_node calls)
    EXPECTED_GRAPH_NODES = {
        "resolve_intent",
        "memory_context",
        "smalltalk",
        "agent_resolver",
        "planner",
        "planner_hitl_gate",
        "tool_resolver",
        "execution_router",
        "domain_planner",
        "execution_hitl_gate",
        "executor",
        "tools",
        "post_tools",
        "artifact_indexer",
        "context_compactor",
        "orchestration_guard",
        "critic",
        "synthesis_hitl",
        "progressive_synthesizer",
        "synthesizer",
        "response_layer_router",
        "response_layer",
    }

    def test_all_supervisor_nodes_mapped(self):
        """Every graph node should appear in at least one Studio node group."""
        # Read the file directly to avoid complex import chains
        studio_path = _PROJECT_ROOT / "app" / "langgraph_studio.py"
        source = studio_path.read_text()

        # Extract mapped nodes from source
        mapped_nodes: set[str] = set()
        for node in self.EXPECTED_GRAPH_NODES:
            if f'"{node}"' in source:
                mapped_nodes.add(node)

        # These are infrastructure nodes that don't need prompt mapping
        infra_nodes = {
            "tools",
            "post_tools",
            "planner_hitl_gate",
            "execution_hitl_gate",
            "synthesis_hitl",
        }
        required_nodes = self.EXPECTED_GRAPH_NODES - infra_nodes
        missing = required_nodes - mapped_nodes
        assert not missing, (
            f"Nodes missing from Studio mapping: {missing}"
        )


# ===================================================================
# P2.2: Recursion limit from env variable
# ===================================================================
class TestRecursionLimitFromEnv:
    """recursion_limit should be driven by LANGGRAPH_RECURSION_LIMIT env."""

    def test_stream_new_chat_reads_env(self):
        """stream_new_chat.py should reference LANGGRAPH_RECURSION_LIMIT."""
        stream_path = _PROJECT_ROOT / "app" / "tasks" / "chat" / "stream_new_chat.py"
        source = stream_path.read_text()
        assert "LANGGRAPH_RECURSION_LIMIT" in source, (
            "stream_new_chat.py should read recursion_limit from "
            "LANGGRAPH_RECURSION_LIMIT env variable"
        )

    def test_studio_reads_same_env(self):
        """langgraph_studio.py should use the same env variable."""
        studio_path = _PROJECT_ROOT / "app" / "langgraph_studio.py"
        source = studio_path.read_text()
        assert "LANGGRAPH_RECURSION_LIMIT" in source, (
            "langgraph_studio.py should read recursion_limit from "
            "LANGGRAPH_RECURSION_LIMIT env variable"
        )


# ===================================================================
# P2.3: Configurable loop guards from env
# ===================================================================
class TestConfigurableGuards:
    """Loop guard constants should be driven by env variables."""

    def test_max_total_steps_from_env(self):
        """MAX_TOTAL_STEPS should read from MAX_TOTAL_STEPS env."""
        constants_path = (
            _PROJECT_ROOT / "app" / "agents" / "new_chat"
            / "supervisor_constants.py"
        )
        source = constants_path.read_text()
        assert 'os.environ.get("MAX_TOTAL_STEPS"' in source, (
            "MAX_TOTAL_STEPS should read from env"
        )

    def test_max_replan_from_env(self):
        """_MAX_REPLAN_ATTEMPTS should read from MAX_REPLAN_ATTEMPTS env."""
        supervisor_path = (
            _PROJECT_ROOT / "app" / "agents" / "new_chat"
            / "supervisor_agent.py"
        )
        source = supervisor_path.read_text()
        assert 'os.environ.get("MAX_REPLAN_ATTEMPTS"' in source, (
            "_MAX_REPLAN_ATTEMPTS should read from env"
        )

    def test_max_agent_hops_from_env(self):
        """_MAX_AGENT_HOPS_PER_TURN should read from MAX_AGENT_HOPS env."""
        constants_path = (
            _PROJECT_ROOT / "app" / "agents" / "new_chat"
            / "supervisor_constants.py"
        )
        source = constants_path.read_text()
        assert 'os.environ.get("MAX_AGENT_HOPS"' in source, (
            "_MAX_AGENT_HOPS_PER_TURN should read from env"
        )

    def test_max_tool_calls_from_env(self):
        """_MAX_TOOL_CALLS_PER_TURN should read from MAX_TOOL_CALLS env."""
        supervisor_path = (
            _PROJECT_ROOT / "app" / "agents" / "new_chat"
            / "supervisor_agent.py"
        )
        source = supervisor_path.read_text()
        assert 'os.environ.get("MAX_TOOL_CALLS"' in source, (
            "_MAX_TOOL_CALLS_PER_TURN should read from env"
        )


# ===================================================================
# P2.4: Executor and all internal nodes in pipeline chain tokens
# ===================================================================
class TestInternalPipelineChainTokens:
    """All internal nodes should be classified as internal pipeline chains."""

    EXPECTED_INTERNAL_TOKENS = {
        "executor",
        "resolve_intent",
        "memory_context",
        "agent_resolver",
        "planner",
        "tool_resolver",
        "execution_router",
        "domain_planner",
        "orchestration_guard",
        "critic",
        "synthesizer",
        "progressive_synthesizer",
        "response_layer_router",
        "artifact_indexer",
        "context_compactor",
    }

    def test_all_internal_tokens_present(self):
        """All internal nodes should appear in _INTERNAL_PIPELINE_CHAIN_TOKENS."""
        stream_path = _PROJECT_ROOT / "app" / "tasks" / "chat" / "stream_new_chat.py"
        source = stream_path.read_text()
        missing = set()
        for token in self.EXPECTED_INTERNAL_TOKENS:
            if f'"{token}"' not in source:
                missing.add(token)
        assert not missing, (
            f"Tokens missing from _INTERNAL_PIPELINE_CHAIN_TOKENS: {missing}"
        )

    def test_response_layer_is_output(self):
        """response_layer should be in _OUTPUT_PIPELINE_CHAIN_TOKENS."""
        stream_path = _PROJECT_ROOT / "app" / "tasks" / "chat" / "stream_new_chat.py"
        source = stream_path.read_text()
        assert '"response_layer"' in source


# ===================================================================
# P2.5: Improved no-progress fingerprinting
# ===================================================================
class TestImprovedFingerprinting:
    """No-progress detection should use agent+route, not agent+task."""

    def test_fingerprint_based_on_route_hint(self):
        """Supervisor should fingerprint on agent+route_hint, not agent+task."""
        supervisor_path = (
            _PROJECT_ROOT / "app" / "agents" / "new_chat"
            / "supervisor_agent.py"
        )
        source = supervisor_path.read_text()
        # The old fingerprint was: f"{agent}|{task_fp}"
        # The new fingerprint should be: f"{agent}|{route_hint}"
        assert "route_hint" in source and "last_fp" in source, (
            "Fingerprinting should reference route_hint"
        )
        # Should NOT fingerprint on task_fp anymore for the no_progress check
        # Check that the agent+route_hint pattern is present
        assert 'f"{last_agent}|{route_hint}"' in source, (
            "no_progress fingerprint should use agent+route_hint pattern"
        )


# ===================================================================
# P2 Bonus: Specialized agents should not be remapped
# ===================================================================
class TestSpecializedAgentResolution:
    """Specialized agents in _SPECIALIZED_AGENTS must not be remapped."""

    def test_specialized_check_before_selected_agents_lock(self):
        """_SPECIALIZED_AGENTS return must come before selected_agents_lock return."""
        supervisor_path = (
            _PROJECT_ROOT / "app" / "agents" / "new_chat"
            / "supervisor_agent.py"
        )
        source = supervisor_path.read_text()
        # Find the _resolve_agent_name function
        fn_start = source.find("def _resolve_agent_name")
        assert fn_start > 0
        fn_source = source[fn_start:fn_start + 5000]
        # The actual return statement with _SPECIALIZED_AGENTS must come
        # BEFORE the return statement with "selected_agents_lock".
        # We look for the code patterns, not comments.
        spec_return = fn_source.find("if requested_raw in _SPECIALIZED_AGENTS:")
        lock_return = fn_source.find('return fallback, f"selected_agents_lock:')
        assert spec_return > 0, (
            "if requested_raw in _SPECIALIZED_AGENTS: not found"
        )
        assert lock_return > 0, (
            'return fallback, f"selected_agents_lock: not found'
        )
        assert spec_return < lock_return, (
            "_SPECIALIZED_AGENTS check must come BEFORE selected_agents_lock "
            "return in _resolve_agent_name to prevent remapping specialized agents"
        )
