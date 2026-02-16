from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types


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


project_root = Path(__file__).resolve().parents[1]
app_pkg = types.ModuleType("app")
app_pkg.__path__ = [str(project_root / "app")]
agents_pkg = types.ModuleType("app.agents")
agents_pkg.__path__ = [str(project_root / "app" / "agents")]
new_chat_pkg = types.ModuleType("app.agents.new_chat")
new_chat_pkg.__path__ = [str(project_root / "app" / "agents" / "new_chat")]
sys.modules["app"] = app_pkg
sys.modules["app.agents"] = agents_pkg
sys.modules["app.agents.new_chat"] = new_chat_pkg

sandbox_runtime = _load_module(
    "app.agents.new_chat.sandbox_runtime",
    "app/agents/new_chat/sandbox_runtime.py",
)
sys.modules["app.agents.new_chat.sandbox_runtime"] = sandbox_runtime
sandbox_execute_module = _load_module(
    "sandbox_phase3_trace_execute_module",
    "app/agents/new_chat/tools/sandbox_execute.py",
)
sandbox_release_module = _load_module(
    "sandbox_phase3_trace_release_module",
    "app/agents/new_chat/tools/sandbox_release.py",
)


class _FakeTraceRecorder:
    def __init__(self) -> None:
        self.started: list[dict[str, str]] = []
        self.ended: list[dict[str, str]] = []

    async def start_span(self, **kwargs):
        self.started.append(
            {
                "name": str(kwargs.get("name") or ""),
                "span_id": str(kwargs.get("span_id") or ""),
            }
        )
        return None

    async def end_span(self, **kwargs):
        self.ended.append(
            {
                "status": str(kwargs.get("status") or ""),
                "span_id": str(kwargs.get("span_id") or ""),
            }
        )
        return None


def test_sandbox_execute_emits_acquire_execute_release_spans(monkeypatch, tmp_path: Path) -> None:
    fake_recorder = _FakeTraceRecorder()

    def _fake_run_sandbox_command(**kwargs):
        _ = kwargs
        return sandbox_runtime.SandboxCommandResult(
            mode=sandbox_runtime.SANDBOX_MODE_LOCAL,
            workspace_path=str(tmp_path / "ws"),
            output="ok",
            exit_code=0,
            truncated=False,
            container_name=None,
            sandbox_id="sandbox-123",
            lease_id="lease-123",
            reused=True,
            state_backend="file",
            idle_releases=["thread-old"],
        )

    monkeypatch.setattr(
        sandbox_execute_module,
        "run_sandbox_command",
        _fake_run_sandbox_command,
    )

    tool = sandbox_execute_module.create_sandbox_execute_tool(
        thread_id=123,
        runtime_hitl={
            "sandbox_enabled": True,
            "sandbox_mode": "local",
            "sandbox_workspace_root": str(tmp_path),
        },
        trace_recorder=fake_recorder,
        trace_parent_span_id="root-test",
    )
    raw_output = asyncio.run(
        tool.ainvoke(
            {
                "description": "run a quick test command",
                "command": "echo hi",
            }
        )
    )
    payload = json.loads(raw_output)
    assert payload.get("exit_code") == 0
    started_names = [item["name"] for item in fake_recorder.started]
    assert "sandbox.acquire" in started_names
    assert "sandbox.execute" in started_names
    assert "sandbox.release" in started_names


def test_sandbox_release_tool_emits_release_span(monkeypatch, tmp_path: Path) -> None:
    fake_recorder = _FakeTraceRecorder()

    monkeypatch.setattr(
        sandbox_release_module,
        "release_sandbox_lease",
        lambda **kwargs: True,
    )

    tool = sandbox_release_module.create_sandbox_release_tool(
        thread_id=777,
        runtime_hitl={
            "sandbox_enabled": True,
            "sandbox_mode": "provisioner",
            "sandbox_provisioner_url": "http://sandbox.local:8002",
            "sandbox_workspace_root": str(tmp_path),
        },
        trace_recorder=fake_recorder,
        trace_parent_span_id="root-test",
    )
    raw_output = asyncio.run(
        tool.ainvoke(
            {
                "description": "release test sandbox",
                "reason": "unit-test",
            }
        )
    )
    payload = json.loads(raw_output)
    assert payload.get("released") is True
    started_names = [item["name"] for item in fake_recorder.started]
    assert "sandbox.release" in started_names


def test_sandbox_execute_merges_subagent_scope_from_injected_state() -> None:
    merged = sandbox_execute_module._runtime_hitl_with_scope(
        runtime_hitl={"sandbox_enabled": True, "sandbox_mode": "local"},
        state={
            "sandbox_scope_mode": "subagent",
            "subagent_id": "sa-test-1",
        },
    )
    assert isinstance(merged, dict)
    assert merged.get("sandbox_scope") == "subagent"
    assert merged.get("sandbox_scope_id") == "sa-test-1"
