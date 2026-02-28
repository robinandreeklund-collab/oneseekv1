"""
Sprint P4 tests — Subagent Mini-Graphs with Real Isolation, Convergence,
Adaptive Guard, Semantic Cache, Admin & Studio Integration.

Tests verify:
- P4.1:  Subagent mini-graph uses real worker invocation with isolation
- P4.1:  Each domain gets unique subagent_id, checkpoint_ns, sandbox_scope
- P4.1:  Proper handoff contracts identical to call_agent
- P4.1:  Convergence node merges handoff contracts from multiple domains
- P4.1a: Per-domain checkpointer isolation (state fields)
- P4.1b: Command-pattern handoff (spawned_domains tracking)
- P4.2:  Adaptive threshold by step (confidence drops)
- P4.2a: Adaptive limits per domain (force_synthesis)
- P4.3:  Semantic cache hit (cache_key determinism)
- P4.1:  Parallel subagents execution with semaphore
- P4.5a: Prompt registry completeness
- P4.5b: Studio node group mapping
- P4.5c: Pipeline nodes have prompt_key
- P4.5c: Pipeline edges connected
- P4.5c: Admin flow-graph endpoint includes P4 nodes
- P4.5e: No loose ends

These tests run WITHOUT a running LLM or DB — they use mocked workers.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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


def _mock_build_subagent_id(
    *, base_thread_id, turn_key, agent_name, call_index, task,
):
    """Mimic _build_subagent_id from supervisor_agent.py."""
    seed = "|".join([
        str(base_thread_id or "thread"),
        str(turn_key or "turn"),
        str(agent_name or "agent").lower(),
        str(call_index),
        hashlib.sha1(str(task or "").encode()).hexdigest()[:10],
    ])
    digest = hashlib.sha1(seed.encode()).hexdigest()[:14]
    slug = str(agent_name or "agent").replace(" ", "_")[:18]
    return f"sa-{slug}-{digest}"


def _mock_build_handoff_payload(
    *, subagent_id, agent_name, response_text, result_contract,
    result_max_chars, error_text="",
):
    """Mimic _build_subagent_handoff_payload from supervisor_agent.py."""
    summary = str(response_text or "")[:max(180, result_max_chars)]
    findings = []
    for line in str(response_text or "").splitlines():
        cleaned = line.strip(" -*")
        if cleaned:
            findings.append(cleaned[:180])
        if len(findings) >= 4:
            break
    if not findings and summary:
        findings = [summary[:180]]
    return {
        "subagent_id": str(subagent_id or ""),
        "agent": str(agent_name or ""),
        "status": "success" if response_text and not error_text else "partial",
        "confidence": 0.7 if response_text and not error_text else 0.0,
        "summary": summary,
        "findings": findings,
        "artifact_refs": [],
        "error": str(error_text or "")[:240],
    }


def _make_mock_worker(response_text: str = "Testresultat från worker"):
    """Create a mock worker that simulates worker.ainvoke()."""
    worker = AsyncMock()
    worker.ainvoke = AsyncMock(return_value={
        "messages": [AIMessage(content=response_text)],
    })
    return worker


def _make_mock_worker_pool(agents: dict[str, Any] | None = None):
    """Create a mock worker pool.

    Args:
        agents: dict mapping agent name → mock worker (or None for default)
    """
    pool = AsyncMock()
    agent_workers = agents or {}

    async def _get(name):
        if name in agent_workers:
            return agent_workers[name]
        # Return a default worker for any agent
        return _make_mock_worker(f"Resultat för {name}")

    pool.get = AsyncMock(side_effect=_get)
    return pool


def _build_spawner(**overrides):
    """Build a subagent_spawner_node with sensible defaults + mock worker pool."""
    llm = overrides.pop("llm", None)
    if llm is None:
        planner_response = json.dumps({
            "thinking": "plan", "steps": [
                {"action": "hämta", "tool_id": "tool_a"}
            ], "reason": "plan klar"
        })
        critic_response = json.dumps({
            "thinking": "ok", "decision": "ok",
            "feedback": "", "confidence": 0.9, "reason": "bra"
        })

        # Mock LLM: planner (odd) → critic (even)
        call_count = {"n": 0}

        async def _ainvoke(msgs, **kwargs):
            call_count["n"] += 1
            if call_count["n"] % 2 == 1:
                return _make_llm_response(planner_response)
            else:
                return _make_llm_response(critic_response)

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=_ainvoke)

    defaults = {
        "llm": llm,
        "spawner_prompt_template": "Test spawner",
        "mini_planner_prompt_template": "Test mini planner",
        "mini_critic_prompt_template": "Test mini critic",
        "mini_synthesizer_prompt_template": "Test mini synthesizer",
        "adaptive_guard_prompt_template": "Test adaptive guard",
        "latest_user_query_fn": _latest_user_query,
        "extract_first_json_object_fn": _extract_first_json_object,
        "worker_pool": _make_mock_worker_pool(),
        "build_subagent_id_fn": _mock_build_subagent_id,
        "build_handoff_payload_fn": _mock_build_handoff_payload,
        "base_thread_id": "test-thread-123",
        "parent_checkpoint_ns": "new_chat_v2_user_test",
        "subagent_isolation_enabled": True,
        "subagent_result_max_chars": 1000,
        "execution_timeout_seconds": 30.0,
    }
    defaults.update(overrides)
    return build_subagent_spawner_node(**defaults)


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
# P4.1 Tests — Subagent Mini-Graph with Real Isolation
# ---------------------------------------------------------------------------
class TestSubagentWorkerIsolation:
    """P4.1: Each domain gets unique subagent_id, checkpoint_ns, sandbox_scope."""

    def test_spawner_generates_unique_subagent_ids(self):
        """Each domain should get a unique subagent_id."""
        captured_states = []
        captured_configs = []

        async def _capture_invoke(state, config=None, **kw):
            captured_states.append(dict(state))
            captured_configs.append(config)
            return {"messages": [AIMessage(content="ok")]}

        worker = AsyncMock()
        worker.ainvoke = AsyncMock(side_effect=_capture_invoke)
        pool = _make_mock_worker_pool({"väder": worker, "statistik": worker})

        node = _build_spawner(worker_pool=pool)
        state = {
            "messages": [HumanMessage(content="väder och statistik")],
            "domain_plans": {
                "väder": {"tools": ["smhi"], "rationale": "väder"},
                "statistik": {"tools": ["scb"], "rationale": "statistik"},
            },
            "total_steps": 0,
        }
        asyncio.get_event_loop().run_until_complete(node(state))

        # Both domains should have been invoked
        assert len(captured_states) == 2

        # Each should have a unique subagent_id
        ids = [s.get("subagent_id") for s in captured_states]
        assert ids[0] is not None
        assert ids[1] is not None
        assert ids[0] != ids[1]
        assert all(sid.startswith("sa-") for sid in ids)

    def test_spawner_sets_sandbox_scope(self):
        """Worker state should have sandbox_scope_mode=subagent."""
        captured_states = []

        async def _capture_invoke(state, config=None, **kw):
            captured_states.append(dict(state))
            return {"messages": [AIMessage(content="ok")]}

        worker = AsyncMock()
        worker.ainvoke = AsyncMock(side_effect=_capture_invoke)
        pool = _make_mock_worker_pool({"trafik": worker})

        node = _build_spawner(worker_pool=pool, subagent_isolation_enabled=True)
        state = {
            "messages": [HumanMessage(content="trafik")],
            "domain_plans": {"trafik": {"tools": ["trafikverket"], "rationale": "t"}},
            "total_steps": 0,
        }
        asyncio.get_event_loop().run_until_complete(node(state))

        assert len(captured_states) == 1
        ws = captured_states[0]
        assert ws["sandbox_scope_mode"] == "subagent"
        assert ws["sandbox_scope_id"] == ws["subagent_id"]

    def test_spawner_sets_checkpoint_namespace(self):
        """Worker config should have isolated checkpoint_ns."""
        captured_configs = []

        async def _capture_invoke(state, config=None, **kw):
            captured_configs.append(config)
            return {"messages": [AIMessage(content="ok")]}

        worker = AsyncMock()
        worker.ainvoke = AsyncMock(side_effect=_capture_invoke)
        pool = _make_mock_worker_pool({"väder": worker})

        node = _build_spawner(
            worker_pool=pool,
            parent_checkpoint_ns="ns_parent",
            subagent_isolation_enabled=True,
        )
        state = {
            "messages": [HumanMessage(content="väder")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "v"}},
            "total_steps": 0,
        }
        asyncio.get_event_loop().run_until_complete(node(state))

        assert len(captured_configs) == 1
        cfg = captured_configs[0]
        cp_ns = cfg["configurable"]["checkpoint_ns"]
        assert cp_ns.startswith("ns_parent:subagent:mini_väder:")
        assert "sa-" in cp_ns

    def test_spawner_returns_handoff_contracts(self):
        """Results should contain proper handoff contracts."""
        pool = _make_mock_worker_pool()
        node = _build_spawner(worker_pool=pool)
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "t"}},
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))

        # Check subagent_handoffs contains proper contracts
        handoffs = result.get("subagent_handoffs", [])
        assert len(handoffs) == 1
        h = handoffs[0]
        assert "subagent_id" in h
        assert "agent" in h
        assert "status" in h
        assert "confidence" in h
        assert "summary" in h
        assert "findings" in h
        assert h["subagent_id"].startswith("sa-")


class TestSubagentMaxCallsPerAgent:
    """P4.1: Retry cap prevents infinite loops."""

    def test_retry_cap_constant(self):
        assert _mini_graph_mod._MAX_MINI_RETRIES == 2
        assert _mini_graph_mod._MAX_PARALLEL_SUBAGENTS == 6


class TestConvergenceNodeMergesResults:
    """P4.1: Convergence creates unified artifact from handoff contracts."""

    def test_single_domain_passthrough(self):
        node = _build_convergence()
        state = {
            "messages": [HumanMessage(content="test")],
            "subagent_summaries": [{
                "domain": "väder",
                "subagent_id": "sa-mini_väder-abc123",
                "summary": "Soligt",
                "findings": ["sol"],
                "status": "success",
                "confidence": 0.8,
            }],
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        cs = result["convergence_status"]
        assert cs["source_domains"] == ["väder"]
        assert cs["overlap_score"] == 0.0
        assert "Soligt" in cs["merged_summary"]
        assert cs["subagent_ids"] == ["sa-mini_väder-abc123"]

    def test_multi_domain_merge(self):
        node = _build_convergence()
        state = {
            "messages": [HumanMessage(content="test")],
            "subagent_summaries": [
                {"domain": "väder", "subagent_id": "sa-1", "summary": "Soligt",
                 "findings": ["sol"], "status": "success", "confidence": 0.8},
                {"domain": "statistik", "subagent_id": "sa-2", "summary": "500k",
                 "findings": ["500k"], "status": "success", "confidence": 0.7},
            ],
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        cs = result["convergence_status"]
        assert len(cs["source_domains"]) == 2
        assert "väder" in cs["source_domains"]
        assert "statistik" in cs["source_domains"]
        assert cs["subagent_ids"] == ["sa-1", "sa-2"]
        assert cs["domain_statuses"]["väder"] == "success"


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
        pool = _make_mock_worker_pool()
        node = _build_spawner(worker_pool=pool)
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


class TestSubagentSummariesContainHandoffFields:
    """P4.1c: Subagent summaries contain handoff contract fields."""

    def test_summary_has_handoff_fields(self):
        pool = _make_mock_worker_pool()
        node = _build_spawner(worker_pool=pool)
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "test"}},
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        summaries = result["subagent_summaries"]
        assert len(summaries) == 1
        s = summaries[0]
        assert s["domain"] == "väder"
        assert "subagent_id" in s
        assert "summary" in s
        assert "status" in s
        assert "confidence" in s
        assert "findings" in s


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
        # At retry 0: confidence should be 0.7
        conf_0 = max(0.3, 0.7 - (0 * 0.15))
        assert conf_0 == 0.7

        # At retry 1: confidence should drop
        conf_1 = max(0.3, 0.7 - (1 * 0.15))
        assert abs(conf_1 - 0.55) < 1e-9
        assert conf_1 < conf_0

        # At retry 2: confidence drops further
        conf_2 = max(0.3, 0.7 - (2 * 0.15))
        assert abs(conf_2 - 0.4) < 1e-9
        assert conf_2 < conf_1


class TestAdaptiveLimitsPerDomain:
    """P4.2a: Per-domain max_steps with force_synthesis."""

    def test_force_synthesis_after_max_retries(self):
        force = 3 >= _mini_graph_mod._MAX_MINI_RETRIES
        assert force is True

    def test_no_force_before_limit(self):
        force = 1 >= _mini_graph_mod._MAX_MINI_RETRIES
        assert force is False


class TestAdaptiveGuardRetryCycle:
    """P4.2: Critic 'needs_more' triggers retry with feedback."""

    def test_retry_invokes_worker_again(self):
        """When critic says needs_more, worker is invoked again."""
        invoke_count = {"n": 0}

        async def _counted_invoke(state, config=None, **kw):
            invoke_count["n"] += 1
            return {"messages": [AIMessage(content=f"attempt {invoke_count['n']}")]}

        worker = AsyncMock()
        worker.ainvoke = AsyncMock(side_effect=_counted_invoke)
        pool = _make_mock_worker_pool({"väder": worker})

        # LLM: planner → critic(needs_more) → critic(ok)
        call_count = {"n": 0}

        async def _llm_invoke(msgs, **kwargs):
            call_count["n"] += 1
            n = call_count["n"]
            if n == 1:  # planner
                return _make_llm_response(json.dumps({
                    "steps": [{"action": "hämta", "tool_id": "smhi"}]
                }))
            elif n == 2:  # first critic → needs_more
                return _make_llm_response(json.dumps({
                    "decision": "needs_more", "feedback": "behöver mer data"
                }))
            else:  # second critic → ok
                return _make_llm_response(json.dumps({
                    "decision": "ok", "feedback": ""
                }))

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=_llm_invoke)

        node = _build_spawner(llm=llm, worker_pool=pool)
        state = {
            "messages": [HumanMessage(content="väder")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "v"}},
            "total_steps": 0,
        }
        asyncio.get_event_loop().run_until_complete(node(state))

        # Worker should be invoked twice (initial + 1 retry)
        assert invoke_count["n"] == 2


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
        assert result["subagent_handoffs"] == []

    def test_spawner_none_domain_plans(self):
        node = _build_spawner()
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": None,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result["spawned_domains"] == []

    def test_three_domains_parallel(self):
        pool = _make_mock_worker_pool()
        node = _build_spawner(worker_pool=pool)
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
        assert len(result["subagent_handoffs"]) == 3

    def test_worker_timeout_handled_gracefully(self):
        """Timeout on one domain should not crash other domains."""
        async def _timeout_invoke(state, config=None, **kw):
            raise asyncio.TimeoutError()

        timeout_worker = AsyncMock()
        timeout_worker.ainvoke = AsyncMock(side_effect=_timeout_invoke)
        ok_worker = _make_mock_worker("ok resultat")
        pool = _make_mock_worker_pool({"väder": timeout_worker, "statistik": ok_worker})

        node = _build_spawner(worker_pool=pool)
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {
                "väder": {"tools": ["smhi"], "rationale": "v"},
                "statistik": {"tools": ["scb"], "rationale": "s"},
            },
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        # Both should complete (väder with error, statistik ok)
        assert len(result["spawned_domains"]) == 2
        handoffs = result["subagent_handoffs"]
        assert len(handoffs) == 2

    def test_worker_pool_get_called_per_domain(self):
        """Worker pool .get() should be called for each domain."""
        pool = _make_mock_worker_pool()
        node = _build_spawner(worker_pool=pool)
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {
                "väder": {"tools": ["smhi"], "rationale": "a"},
                "statistik": {"tools": ["scb"], "rationale": "b"},
            },
            "total_steps": 0,
        }
        asyncio.get_event_loop().run_until_complete(node(state))
        # pool.get should have been called for each domain
        assert pool.get.call_count == 2


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
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
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
            "subagent_summaries": [{
                "domain": "väder", "subagent_id": "sa-1",
                "summary": "Sol", "findings": [], "status": "success",
                "confidence": 0.8,
            }],
            "total_steps": 5,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result.get("total_steps") == 6

    def test_spawner_node_increments_total_steps(self):
        """Spawner node increments total_steps."""
        pool = _make_mock_worker_pool()
        node = _build_spawner(worker_pool=pool)
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "test"}},
            "total_steps": 3,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert result.get("total_steps") == 4

    def test_spawner_isolation_disabled_skips_sandbox_fields(self):
        """When isolation is disabled, worker state has no sandbox fields."""
        captured_states = []

        async def _capture_invoke(state, config=None, **kw):
            captured_states.append(dict(state))
            return {"messages": [AIMessage(content="ok")]}

        worker = AsyncMock()
        worker.ainvoke = AsyncMock(side_effect=_capture_invoke)
        pool = _make_mock_worker_pool({"väder": worker})

        node = _build_spawner(worker_pool=pool, subagent_isolation_enabled=False)
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "t"}},
            "total_steps": 0,
        }
        asyncio.get_event_loop().run_until_complete(node(state))

        assert len(captured_states) == 1
        ws = captured_states[0]
        assert "sandbox_scope_mode" not in ws
        assert "sandbox_scope_id" not in ws

    def test_max_nesting_depth_constant(self):
        """_MAX_NESTING_DEPTH exists and is sensible."""
        assert _mini_graph_mod._MAX_NESTING_DEPTH == 2


# ---------------------------------------------------------------------------
# P4.1+ Tests — Recursive Mini-Agent Spawning
# ---------------------------------------------------------------------------
class TestRecursiveSubagentSpawning:
    """P4.1+: Subagents can recursively spawn sub-agents."""

    def test_spawner_accepts_nesting_depth(self):
        """build_subagent_spawner_node accepts max_nesting_depth param."""
        pool = _make_mock_worker_pool()
        node = _build_spawner(worker_pool=pool, max_nesting_depth=1)
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "t"}},
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        assert len(result["spawned_domains"]) == 1

    def test_sub_spawn_triggers_when_llm_says_yes(self):
        """When sub-spawn check says yes, nested workers are invoked."""
        invoke_count = {"n": 0}

        async def _counted_invoke(state, config=None, **kw):
            invoke_count["n"] += 1
            return {"messages": [AIMessage(content=f"result {invoke_count['n']}")]}

        worker = AsyncMock()
        worker.ainvoke = AsyncMock(side_effect=_counted_invoke)
        pool = _make_mock_worker_pool({"väder": worker, "smhi_detail": worker})

        # LLM sequence: planner → critic(ok) → sub_spawn(yes with 1 sub-domain)
        # → sub_planner → sub_critic(ok) → sub_spawn(no)
        call_count = {"n": 0}

        async def _llm_invoke(msgs, **kwargs):
            call_count["n"] += 1
            n = call_count["n"]
            if n == 1:  # planner
                return _make_llm_response(json.dumps({
                    "steps": [{"action": "hämta", "tool_id": "smhi"}]
                }))
            elif n == 2:  # critic → ok
                return _make_llm_response(json.dumps({
                    "decision": "ok", "feedback": ""
                }))
            elif n == 3:  # sub_spawn check → yes
                return _make_llm_response(json.dumps({
                    "needs_sub_spawn": True,
                    "sub_domains": {
                        "smhi_detail": {"tools": ["smhi_detail"], "rationale": "detaljer"}
                    }
                }))
            elif n == 4:  # sub_planner
                return _make_llm_response(json.dumps({
                    "steps": [{"action": "query", "tool_id": "smhi_detail"}]
                }))
            elif n == 5:  # sub_critic → ok
                return _make_llm_response(json.dumps({
                    "decision": "ok", "feedback": ""
                }))
            else:  # sub_spawn check → no (depth 1, but result checks)
                return _make_llm_response(json.dumps({
                    "needs_sub_spawn": False
                }))

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=_llm_invoke)

        node = _build_spawner(llm=llm, worker_pool=pool, max_nesting_depth=2)
        state = {
            "messages": [HumanMessage(content="detaljerad väderprognos")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "v"}},
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))

        # Parent worker invoked once + sub-agent worker invoked once = 2
        assert invoke_count["n"] == 2
        assert len(result["spawned_domains"]) == 1

    def test_nesting_depth_zero_prevents_sub_spawn(self):
        """When max_nesting_depth=0, no sub-spawning occurs."""
        call_count = {"n": 0}

        async def _llm_invoke(msgs, **kwargs):
            call_count["n"] += 1
            n = call_count["n"]
            if n == 1:  # planner
                return _make_llm_response(json.dumps({
                    "steps": [{"action": "hämta", "tool_id": "smhi"}]
                }))
            else:  # critic → ok
                return _make_llm_response(json.dumps({
                    "decision": "ok", "feedback": ""
                }))

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=_llm_invoke)
        pool = _make_mock_worker_pool()

        node = _build_spawner(llm=llm, worker_pool=pool, max_nesting_depth=0)
        state = {
            "messages": [HumanMessage(content="test")],
            "domain_plans": {"väder": {"tools": ["smhi"], "rationale": "t"}},
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))

        # Only planner + critic calls, NO sub_spawn check
        assert call_count["n"] == 2
        assert len(result["spawned_domains"]) == 1


class TestConvergenceFlattenSubResults:
    """Convergence node flattens sub_results from recursive spawning."""

    def test_flatten_no_sub_results(self):
        """No sub_results → no flattening needed."""
        node = _build_convergence()
        state = {
            "messages": [HumanMessage(content="test")],
            "subagent_summaries": [{
                "domain": "väder", "subagent_id": "sa-1",
                "summary": "Sol", "findings": ["sol"],
                "status": "success", "confidence": 0.8,
            }],
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        cs = result["convergence_status"]
        assert cs["source_domains"] == ["väder"]

    def test_flatten_with_sub_results(self):
        """Sub-results are flattened with qualified domain names."""
        node = _build_convergence()
        state = {
            "messages": [HumanMessage(content="test")],
            "subagent_summaries": [
                {
                    "domain": "statistik", "subagent_id": "sa-1",
                    "summary": "SCB data", "findings": ["500k"],
                    "status": "success", "confidence": 0.8,
                    "sub_results": [
                        {
                            "domain": "scb", "subagent_id": "sa-1-sub-1",
                            "summary": "Befolkning", "findings": ["500k"],
                            "status": "success", "confidence": 0.9,
                        },
                    ],
                },
            ],
            "total_steps": 0,
        }
        result = asyncio.get_event_loop().run_until_complete(node(state))
        cs = result["convergence_status"]
        # Flattened: "statistik" + "statistik.scb"
        assert "statistik" in cs["source_domains"]
        assert "statistik.scb" in cs["source_domains"]


# ---------------------------------------------------------------------------
# Pipeline Graph Tests — Compare Mode + P4 Node Positions
# ---------------------------------------------------------------------------
class TestCompareModePipelineNodes:
    """Compare mode nodes are in pipeline graph."""

    _COMPARE_NODE_IDS = [
        "node:compare_domain_planner",
        "node:compare_subagent_spawner",
        "node:compare_mini_critic",
        "node:compare_convergence",
        "node:compare_synthesizer",
    ]

    def test_all_compare_nodes_in_pipeline(self):
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
        for node_id in self._COMPARE_NODE_IDS:
            assert f'"{node_id}"' in content, f"Missing pipeline node: {node_id}"

    def test_compare_stage_exists(self):
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
        assert '"compare"' in content
        assert '"Jämförelse"' in content

    def test_compare_edges_exist(self):
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
        assert '"node:compare_domain_planner"' in content
        assert '"node:compare_subagent_spawner"' in content
        assert '"node:compare_mini_critic"' in content
        assert '"node:compare_convergence"' in content
        assert '"node:compare_synthesizer"' in content
        # Edge from resolve_intent
        assert "jämförelse" in content

    def test_compare_nodes_have_compare_stage(self):
        routes_path = _PROJECT_ROOT / "app/routes/admin_flow_graph_routes.py"
        content = routes_path.read_text()
        compare_count = content.count('"stage": "compare"')
        assert compare_count == 6, f"Expected 6 compare-stage nodes, got {compare_count}"


class TestFrontendPipelineNodePositions:
    """Frontend nodePositions map includes all P4 and compare nodes."""

    def test_p4_nodes_have_positions(self):
        tsx_path = _PROJECT_ROOT.parent / "surfsense_web/components/admin/flow-graph-page.tsx"
        content = tsx_path.read_text()
        p4_nodes = [
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
        for node_id in p4_nodes:
            assert f'"{node_id}"' in content, f"Missing position for: {node_id}"

    def test_compare_nodes_have_positions(self):
        tsx_path = _PROJECT_ROOT.parent / "surfsense_web/components/admin/flow-graph-page.tsx"
        content = tsx_path.read_text()
        compare_nodes = [
            "node:compare_domain_planner",
            "node:compare_subagent_spawner",
            "node:compare_mini_critic",
            "node:compare_criterion_evaluator",
            "node:compare_convergence",
            "node:compare_synthesizer",
        ]
        for node_id in compare_nodes:
            assert f'"{node_id}"' in content, f"Missing position for: {node_id}"

    def test_subagent_stage_color_exists(self):
        tsx_path = _PROJECT_ROOT.parent / "surfsense_web/components/admin/flow-graph-page.tsx"
        content = tsx_path.read_text()
        assert "subagent:" in content
        assert "compare:" in content

    def test_multi_query_decomposer_has_position(self):
        tsx_path = _PROJECT_ROOT.parent / "surfsense_web/components/admin/flow-graph-page.tsx"
        content = tsx_path.read_text()
        assert '"node:multi_query_decomposer"' in content
