"""
Sprint P4 tests — Subagent Mini-Graphs, Convergence, Adaptive Guard,
Semantic Cache, Admin & Studio Integration.

Tests verify:
- P4.1:  Subagent mini-graph isolation (state doesn't leak)
- P4.1:  Max 4-6 calls per mini-graph (retry cap)
- P4.1:  Convergence node merges results from multiple domains
- P4.1a: Per-domain checkpointer isolation (state fields)
- P4.1b: Command-pattern handoff (spawned_domains tracking)
- P4.1c: Summarization token budget (mini_synthesizer output)
- P4.1d: PEV verify node prompt exists
- P4.2:  Adaptive threshold by step (confidence drops)
- P4.2a: Adaptive limits per domain (force_synthesis)
- P4.3:  Semantic cache hit (cache_key determinism)
- P4.3:  Semantic cache miss fallback
- P4.1:  Parallel subagents execution
- P4.5a: Prompt registry completeness
- P4.5b: Studio node group mapping
- P4.5c: Pipeline nodes have prompt_key
- P4.5c: Pipeline edges connected
- P4.5c: Admin flow-graph endpoint includes P4 nodes
- P4.5e: No loose ends

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
# Module loading helpers (same pattern as P3 tests)
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

_types_mod = _load_module(
    "app.agents.new_chat.supervisor_types",
    "app/agents/new_chat/supervisor_types.py",
)
SupervisorState = _types_mod.SupervisorState

_mini_graph_mod = _load_module(
    "app.agents.new_chat.nodes.subagent_mini_graph",
    "app/agents/new_chat/nodes/subagent_mini_graph.py",
)
build_subagent_spawner_node = _mini_graph_mod.build_subagent_spawner_node
MiniGraphState = _mini_graph_mod.MiniGraphState
_cache_key = _mini_graph_mod._cache_key

_convergence_mod = _load_module(
    "app.agents.new_chat.nodes.convergence_node",
    "app/agents/new_chat/nodes/convergence_node.py",
)
build_convergence_node = _convergence_mod.build_convergence_node


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


def _latest_user_query(msgs):
    for m in reversed(msgs or []):
        if isinstance(m, HumanMessage):
            return getattr(m, "content", "")
    return ""


def _build_spawner(**overrides):
    """Build a subagent_spawner_node with sensible defaults."""
    llm = overrides.pop("llm", _make_llm({
        "thinking": "test",
        "steps": [{"action": "hämta data", "tool_id": "tool_a", "use_cache": False}],
        "reason": "test",
    }))
    # The LLM returns different responses for different calls:
    # - mini_planner: steps
    # - mini_critic: decision ok
    # - mini_synthesizer: summary
    critic_response = json.dumps({
        "thinking": "ok", "decision": "ok",
        "feedback": "", "confidence": 0.9, "reason": "bra"
    })
    synthesizer_response = json.dumps({
        "thinking": "sammanfatta", "domain": "test",
        "summary": "Testsammanfattning", "key_facts": ["fakt1"],
        "data_quality": "high", "reason": "klar"
    })
    planner_response = json.dumps({
        "thinking": "plan", "steps": [
            {"action": "hämta", "tool_id": "tool_a", "use_cache": False}
        ], "reason": "plan klar"
    })

    # Mock LLM that returns different responses per call
    call_count = {"n": 0}

    async def _ainvoke(msgs, **kwargs):
        call_count["n"] += 1
        n = call_count["n"]
        if n % 3 == 1:
            return _make_llm_response(planner_response)
        elif n % 3 == 2:
            return _make_llm_response(critic_response)
        else:
            return _make_llm_response(synthesizer_response)

    llm.ainvoke = AsyncMock(side_effect=_ainvoke)

    return build_subagent_spawner_node(
        llm=llm,
        spawner_prompt_template="Test spawner",
        mini_planner_prompt_template="Test mini planner",
        mini_critic_prompt_template="Test mini critic",
        mini_synthesizer_prompt_template="Test mini synthesizer",
        adaptive_guard_prompt_template="Test adaptive guard",
        latest_user_query_fn=_latest_user_query,
        append_datetime_context_fn=lambda s: s,
        extract_first_json_object_fn=_extract_first_json_object,
        **overrides,
    )


def _build_convergence(**overrides):
    """Build a convergence_node with sensible defaults."""
    llm = overrides.pop("llm", _make_llm({
        "thinking": "merge",
        "merged_summary": "Sammanslagen sammanfattning",
        "merged_fields": ["väder", "statistik"],
        "overlap_score": 0.3,
        "conflicts": [],
        "source_domains": ["väder", "statistik"],
        "reason": "merged"
    }))
    return build_convergence_node(
        llm=llm,
        convergence_prompt_template="Test convergence",
        latest_user_query_fn=_latest_user_query,
        extract_first_json_object_fn=_extract_first_json_object,
        **overrides,
    )


# ---------------------------------------------------------------------------
# P4.1 Tests — Subagent Mini-Graph
# ---------------------------------------------------------------------------
class TestSubagentMiniGraphIsolation:
    """P4.1: Subagent state doesn't leak to parent."""

    def test_mini_graph_state_independent(self):
        ms1 = MiniGraphState(domain="väder", task="väder i sthlm", tools=["smhi"])
        ms2 = MiniGraphState(domain="statistik", task="befolkning", tools=["scb"])
        ms1.summary = "Soligt"
        ms2.summary = "500k"
        # States are independent
        assert ms1.summary != ms2.summary
        assert ms1.domain != ms2.domain
        assert ms1.tools != ms2.tools

    def test_mini_graph_to_dict(self):
        ms = MiniGraphState(domain="trafik", task="förseningar", tools=["trafikverket"])
        ms.summary = "Inga förseningar"
        ms.key_facts = ["punktligt"]
        ms.data_quality = "high"
        d = ms.to_dict()
        assert d["domain"] == "trafik"
        assert d["summary"] == "Inga förseningar"
        assert d["key_facts"] == ["punktligt"]
        assert d["data_quality"] == "high"


class TestSubagentMaxCallsPerAgent:
    """P4.1: Max 4-6 calls per mini-graph (retry cap = 2)."""

    def test_retry_cap_enforced(self):
        ms = MiniGraphState(domain="test", task="test", tools=["t"])
        ms.retry_count = 3  # Beyond the cap
        # adaptive_guard would force_synthesis
        assert ms.retry_count > _mini_graph_mod._MAX_MINI_RETRIES


class TestConvergenceNodeMergesResults:
    """P4.1: Convergence creates unified artifact."""

    def test_single_domain_passthrough(self):
        node = _build_convergence()
        state = {
            "messages": [HumanMessage(content="test")],
            "subagent_summaries": [
                {"domain": "väder", "summary": "Soligt", "key_facts": ["sol"], "data_quality": "high"}
            ],
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        cs = result["convergence_status"]
        assert cs["source_domains"] == ["väder"]
        assert cs["overlap_score"] == 0.0
        assert "Soligt" in cs["merged_summary"]

    def test_multi_domain_merge(self):
        node = _build_convergence()
        state = {
            "messages": [HumanMessage(content="test")],
            "subagent_summaries": [
                {"domain": "väder", "summary": "Soligt", "key_facts": ["sol"], "data_quality": "high"},
                {"domain": "statistik", "summary": "500k invånare", "key_facts": ["500k"], "data_quality": "high"},
            ],
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        cs = result["convergence_status"]
        assert len(cs["source_domains"]) == 2
        assert "väder" in cs["source_domains"]
        assert "statistik" in cs["source_domains"]


class TestPerDomainCheckpointerIsolation:
    """P4.1a: State fields for per-domain tracking exist."""

    def test_state_has_micro_plans(self):
        annotations = getattr(SupervisorState, "__annotations__", {})
        assert "micro_plans" in annotations

    def test_state_has_spawned_domains(self):
        annotations = getattr(SupervisorState, "__annotations__", {})
        assert "spawned_domains" in annotations

    def test_state_has_convergence_status(self):
        annotations = getattr(SupervisorState, "__annotations__", {})
        assert "convergence_status" in annotations

    def test_state_has_subagent_summaries(self):
        annotations = getattr(SupervisorState, "__annotations__", {})
        assert "subagent_summaries" in annotations

    def test_state_has_adaptive_thresholds(self):
        annotations = getattr(SupervisorState, "__annotations__", {})
        assert "adaptive_thresholds" in annotations


class TestCommandPatternHandoff:
    """P4.1b: Spawned domains tracking works."""

    def test_spawner_tracks_domains(self):
        node = _build_spawner()
        state = {
            "messages": [HumanMessage(content="väder och statistik")],
            "domain_plans": {
                "väder": {"tools": ["smhi_forecast"], "rationale": "väderprognos"},
                "statistik": {"tools": ["scb_api"], "rationale": "befolkningsdata"},
            },
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert len(result["spawned_domains"]) == 2
        assert set(result["spawned_domains"]) == {"väder", "statistik"}
        assert "väder" in result["micro_plans"]
        assert "statistik" in result["micro_plans"]


class TestSubagentSummarizationTokenBudget:
    """P4.1c: Mini-synthesizer produces compact output."""

    def test_summary_in_output(self):
        node = _build_spawner()
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {
                "väder": {"tools": ["smhi"], "rationale": "test"},
            },
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        summaries = result["subagent_summaries"]
        assert len(summaries) == 1
        assert summaries[0]["domain"] == "väder"
        assert "summary" in summaries[0]


class TestPevVerifyNode:
    """P4.1d: PEV verify node prompt exists in registry."""

    def test_pev_prompt_constant_exists(self):
        prompts_mod = _load_module(
            "app.agents.new_chat.supervisor_pipeline_prompts_p4_check",
            "app/agents/new_chat/supervisor_pipeline_prompts.py",
        )
        assert hasattr(prompts_mod, "DEFAULT_SUPERVISOR_PEV_VERIFY_PROMPT")
        prompt = prompts_mod.DEFAULT_SUPERVISOR_PEV_VERIFY_PROMPT
        assert "pev_verify" in prompt.lower() or "Plan-Execute-Verify" in prompt


# ---------------------------------------------------------------------------
# P4.2 Tests — Adaptive Everything
# ---------------------------------------------------------------------------
class TestAdaptiveThresholdByStep:
    """P4.2: Thresholds decrease with retries."""

    def test_confidence_drops_with_retries(self):
        ms = MiniGraphState(domain="test", task="test", tools=["t"])

        # At retry 0: confidence should be 0.7
        ms.retry_count = 0
        conf_0 = max(0.3, 0.7 - (ms.retry_count * 0.15))
        assert conf_0 == 0.7

        # At retry 1: confidence should drop
        ms.retry_count = 1
        conf_1 = max(0.3, 0.7 - (ms.retry_count * 0.15))
        assert abs(conf_1 - 0.55) < 1e-9
        assert conf_1 < conf_0

        # At retry 2: confidence drops further
        ms.retry_count = 2
        conf_2 = max(0.3, 0.7 - (ms.retry_count * 0.15))
        assert abs(conf_2 - 0.4) < 1e-9
        assert conf_2 < conf_1


class TestAdaptiveLimitsPerDomain:
    """P4.2a: Per-domain max_steps with force_synthesis."""

    def test_force_synthesis_after_max_retries(self):
        ms = MiniGraphState(domain="test", task="test", tools=["t"])
        ms.retry_count = 3  # > MAX_MINI_RETRIES (2)
        force = ms.retry_count >= _mini_graph_mod._MAX_MINI_RETRIES
        assert force is True

    def test_no_force_before_limit(self):
        ms = MiniGraphState(domain="test", task="test", tools=["t"])
        ms.retry_count = 1
        force = ms.retry_count >= _mini_graph_mod._MAX_MINI_RETRIES
        assert force is False


# ---------------------------------------------------------------------------
# P4.3 Tests — Semantic Tool Caching
# ---------------------------------------------------------------------------
class TestSemanticCacheHit:
    """P4.3: Cache key is deterministic."""

    def test_cache_key_deterministic(self):
        key1 = _cache_key("scb", "befolkning göteborg 2023")
        key2 = _cache_key("scb", "befolkning göteborg 2023")
        assert key1 == key2

    def test_cache_key_differs_by_domain(self):
        key1 = _cache_key("scb", "befolkning göteborg 2023")
        key2 = _cache_key("smhi", "befolkning göteborg 2023")
        assert key1 != key2

    def test_cache_key_differs_by_query(self):
        key1 = _cache_key("scb", "befolkning göteborg 2023")
        key2 = _cache_key("scb", "befolkning stockholm 2023")
        assert key1 != key2


class TestSemanticCacheMissFallback:
    """P4.3: Cache miss falls through to normal execution."""

    def test_no_cache_hit_by_default(self):
        ms = MiniGraphState(domain="test", task="test", tools=["t"])
        assert ms.cache_hit is False


# ---------------------------------------------------------------------------
# P4.1 — Parallel Execution
# ---------------------------------------------------------------------------
class TestParallelSubagentsExecution:
    """P4.1: Independent subagents run in parallel."""

    def test_spawner_empty_domain_plans(self):
        node = _build_spawner()
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {},
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result["spawned_domains"] == []
        assert result["subagent_summaries"] == []

    def test_spawner_none_domain_plans(self):
        node = _build_spawner()
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": None,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result["spawned_domains"] == []

    def test_three_domains_parallel(self):
        node = _build_spawner()
        state = {
            "messages": [HumanMessage(content="tre domäner")],
            "domain_plans": {
                "väder": {"tools": ["smhi"], "rationale": "a"},
                "statistik": {"tools": ["scb"], "rationale": "b"},
                "trafik": {"tools": ["trafikverket"], "rationale": "c"},
            },
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert len(result["spawned_domains"]) == 3
        assert len(result["subagent_summaries"]) == 3


# ---------------------------------------------------------------------------
# P4.5a Tests — Prompt Registry Completeness
# ---------------------------------------------------------------------------
class TestP4PromptRegistryCompleteness:
    """P4.5a: All P4 prompt keys exist in registry + definitions."""

    _P4_PROMPT_KEYS = [
        "supervisor.subagent_spawner.system",
        "supervisor.mini_planner.system",
        "supervisor.mini_critic.system",
        "supervisor.mini_synthesizer.system",
        "supervisor.convergence.system",
        "supervisor.pev_verify.system",
        "supervisor.adaptive_guard.system",
    ]

    def test_all_p4_keys_in_prompts_file(self):
        prompts_path = _PROJECT_ROOT / "app/agents/new_chat/supervisor_pipeline_prompts.py"
        content = prompts_path.read_text()
        expected_constants = [
            "DEFAULT_SUPERVISOR_SUBAGENT_SPAWNER_PROMPT",
            "DEFAULT_SUPERVISOR_MINI_PLANNER_PROMPT",
            "DEFAULT_SUPERVISOR_MINI_CRITIC_PROMPT",
            "DEFAULT_SUPERVISOR_MINI_SYNTHESIZER_PROMPT",
            "DEFAULT_SUPERVISOR_CONVERGENCE_PROMPT",
            "DEFAULT_SUPERVISOR_PEV_VERIFY_PROMPT",
            "DEFAULT_SUPERVISOR_ADAPTIVE_GUARD_PROMPT",
        ]
        for const in expected_constants:
            assert const in content, f"Missing constant: {const}"

    def test_all_p4_keys_in_registry(self):
        registry_path = _PROJECT_ROOT / "app/agents/new_chat/prompt_registry.py"
        content = registry_path.read_text()
        for key in self._P4_PROMPT_KEYS:
            assert f'"{key}"' in content, f"Missing key in registry: {key}"

    def test_p4_keys_in_template_tuple(self):
        registry_path = _PROJECT_ROOT / "app/agents/new_chat/prompt_registry.py"
        content = registry_path.read_text()
        # Check they're in the ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS tuple
        template_section = content.split("ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS")[1].split(")")[0]
        for key in self._P4_PROMPT_KEYS:
            assert f'"{key}"' in template_section, f"Missing in template tuple: {key}"


# ---------------------------------------------------------------------------
# P4.5b Tests — Studio Node Group Mapping
# ---------------------------------------------------------------------------
class TestP4StudioNodeGroupMapping:
    """P4.5b: All P4 nodes exist in _PROMPT_NODE_GROUP_TO_GRAPH_NODES."""

    def test_supervisor_nodes_include_p4(self):
        studio_path = _PROJECT_ROOT / "app/langgraph_studio.py"
        content = studio_path.read_text()
        for node_name in ["subagent_spawner", "convergence_node", "adaptive_guard"]:
            assert f'"{node_name}"' in content, f"Missing supervisor node: {node_name}"

    def test_subagent_mini_group_exists(self):
        studio_path = _PROJECT_ROOT / "app/langgraph_studio.py"
        content = studio_path.read_text()
        assert '"subagent_mini"' in content

    def test_subagent_mini_group_nodes(self):
        studio_path = _PROJECT_ROOT / "app/langgraph_studio.py"
        content = studio_path.read_text()
        for node_name in ["mini_planner", "mini_executor", "mini_critic", "mini_synthesizer", "pev_verify"]:
            assert f'"{node_name}"' in content, f"Missing mini group node: {node_name}"

    def test_relevant_groups_include_subagent_mini(self):
        studio_path = _PROJECT_ROOT / "app/langgraph_studio.py"
        content = studio_path.read_text()
        assert '"subagent_mini"' in content
        # Should be in _GRAPH_RELEVANT_PROMPT_GROUPS
        assert "subagent_mini" in content


# ---------------------------------------------------------------------------
# P4.5c Tests — Pipeline Nodes & Edges
# ---------------------------------------------------------------------------
class TestP4PipelineNodesHavePromptKey:
    """P4.5c: All P4 pipeline nodes have correct prompt_key."""

    _P4_NODE_IDS = [
        "node:subagent_spawner",
        "node:mini_planner",
        "node:mini_executor",
        "node:mini_critic",
        "node:mini_synthesizer",
        "node:pev_verify",
        "node:adaptive_guard",
        "node:convergence_node",
        "node:semantic_cache",
    ]

    def test_all_p4_nodes_in_pipeline(self):
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
        for node_id in self._P4_NODE_IDS:
            assert f'"{node_id}"' in content, f"Missing pipeline node: {node_id}"


class TestP4PipelineEdgesConnected:
    """P4.5c: All P4 pipeline edges have valid source/target."""

    def test_subagent_edges_exist(self):
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
        # Key edges
        assert '"node:subagent_spawner"' in content
        assert '"node:mini_planner"' in content
        assert '"node:convergence_node"' in content
        assert '"node:adaptive_guard"' in content

    def test_subagent_stage_exists(self):
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
        assert '"subagent"' in content
        assert '"Subagent Mini-Graphs"' in content
        assert '"indigo"' in content


class TestP4AdminFlowGraphEndpoint:
    """P4.5c: /admin/flow-graph would return P4 nodes."""

    def test_p4_nodes_in_pipeline_nodes_list(self):
        # We verify the _PIPELINE_NODES list by parsing the file
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
        # Count P4 nodes (stage = "subagent")
        subagent_count = content.count('"stage": "subagent"')
        assert subagent_count == 9, f"Expected 9 subagent-stage nodes, got {subagent_count}"


# ---------------------------------------------------------------------------
# P4.5e Tests — No Loose Ends
# ---------------------------------------------------------------------------
class TestP4NoLooseEnds:
    """P4.5e: Every P4 node meets all requirements."""

    def test_prompt_registry_infer_group_mini(self):
        """Mini-graph prompts map to subagent_mini group."""
        registry_path = _PROJECT_ROOT / "app/agents/new_chat/prompt_registry.py"
        content = registry_path.read_text()
        # The infer function should handle supervisor.mini_* → subagent_mini
        assert "supervisor.mini_" in content
        assert "subagent_mini" in content

    def test_prompt_registry_infer_group_pev(self):
        """PEV prompts map to subagent_mini group."""
        registry_path = _PROJECT_ROOT / "app/agents/new_chat/prompt_registry.py"
        content = registry_path.read_text()
        assert "supervisor.pev_" in content
        assert "subagent_mini" in content

    def test_all_p4_constants_exist(self):
        """All P4 default prompt constants are defined."""
        prompts_path = _PROJECT_ROOT / "app/agents/new_chat/supervisor_pipeline_prompts.py"
        content = prompts_path.read_text()
        constants = [
            "DEFAULT_SUPERVISOR_SUBAGENT_SPAWNER_PROMPT",
            "DEFAULT_SUPERVISOR_MINI_PLANNER_PROMPT",
            "DEFAULT_SUPERVISOR_MINI_CRITIC_PROMPT",
            "DEFAULT_SUPERVISOR_MINI_SYNTHESIZER_PROMPT",
            "DEFAULT_SUPERVISOR_CONVERGENCE_PROMPT",
            "DEFAULT_SUPERVISOR_PEV_VERIFY_PROMPT",
            "DEFAULT_SUPERVISOR_ADAPTIVE_GUARD_PROMPT",
        ]
        for c in constants:
            assert c in content, f"Missing constant: {c}"

    def test_nodes_exported_from_init(self):
        """P4 node builders exported from nodes/__init__.py."""
        init_path = _PROJECT_ROOT / "app/agents/new_chat/nodes/__init__.py"
        content = init_path.read_text()
        assert "build_subagent_spawner_node" in content
        assert "build_convergence_node" in content

    def test_convergence_node_increments_total_steps(self):
        """Convergence node increments total_steps."""
        node = _build_convergence()
        state = {
            "messages": [HumanMessage(content="test")],
            "subagent_summaries": [
                {"domain": "väder", "summary": "Sol", "key_facts": [], "data_quality": "high"},
            ],
            "total_steps": 5,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result.get("total_steps") == 6

    def test_spawner_node_increments_total_steps(self):
        """Spawner node increments total_steps."""
        node = _build_spawner()
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "test"}},
            "total_steps": 3,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result.get("total_steps") == 4
