from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


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


sandbox_runtime = _load_module(
    "sandbox_phase3_robustness_test_module",
    "app/agents/new_chat/sandbox_runtime.py",
)


def test_sandbox_reuse_persists_across_module_reload(tmp_path: Path) -> None:
    runtime_hitl = {
        "sandbox_enabled": True,
        "sandbox_mode": "local",
        "sandbox_workspace_root": str(tmp_path / "ws"),
        "sandbox_state_store": "file",
        "sandbox_state_file_path": str(tmp_path / "state.json"),
    }
    first = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('hello')\"",
        thread_id="thread-reuse",
        runtime_hitl=runtime_hitl,
    )
    assert first.exit_code == 0
    assert first.reused is False
    assert first.lease_id

    reloaded = _load_module(
        "sandbox_phase3_robustness_test_module_reloaded",
        "app/agents/new_chat/sandbox_runtime.py",
    )
    second = reloaded.run_sandbox_command(
        command="python3 -c \"print('hello')\"",
        thread_id="thread-reuse",
        runtime_hitl=runtime_hitl,
    )
    assert second.exit_code == 0
    assert second.reused is True
    assert second.lease_id == first.lease_id


def test_sandbox_idle_timeout_rotates_lease(tmp_path: Path, monkeypatch) -> None:
    runtime_hitl = {
        "sandbox_enabled": True,
        "sandbox_mode": "local",
        "sandbox_workspace_root": str(tmp_path / "ws"),
        "sandbox_state_store": "file",
        "sandbox_state_file_path": str(tmp_path / "state.json"),
        "sandbox_idle_timeout_seconds": 10,
    }
    now_ref = {"value": 1_000}

    monkeypatch.setattr(
        sandbox_runtime.time,
        "time",
        lambda: float(now_ref["value"]),
    )

    first = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('one')\"",
        thread_id="thread-timeout",
        runtime_hitl=runtime_hitl,
    )
    assert first.reused is False
    assert first.lease_id
    assert first.idle_releases == []

    now_ref["value"] = 1_020
    second = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('two')\"",
        thread_id="thread-timeout",
        runtime_hitl=runtime_hitl,
    )
    assert second.reused is False
    assert second.lease_id
    assert second.lease_id != first.lease_id
    assert second.idle_releases


def test_sandbox_release_cleans_current_thread_lease(tmp_path: Path) -> None:
    runtime_hitl = {
        "sandbox_enabled": True,
        "sandbox_mode": "local",
        "sandbox_workspace_root": str(tmp_path / "ws"),
        "sandbox_state_store": "file",
        "sandbox_state_file_path": str(tmp_path / "state.json"),
    }
    first = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('alpha')\"",
        thread_id="thread-release",
        runtime_hitl=runtime_hitl,
    )
    assert first.lease_id
    assert sandbox_runtime.release_sandbox_lease(
        thread_id="thread-release",
        runtime_hitl=runtime_hitl,
        reason="unit-test",
    )
    second = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('beta')\"",
        thread_id="thread-release",
        runtime_hitl=runtime_hitl,
    )
    assert second.reused is False
    assert second.lease_id
    assert second.lease_id != first.lease_id


def test_sandbox_auto_state_store_falls_back_to_file(tmp_path: Path) -> None:
    result = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('ok')\"",
        thread_id="thread-auto-fallback",
        runtime_hitl={
            "sandbox_enabled": True,
            "sandbox_mode": "local",
            "sandbox_workspace_root": str(tmp_path / "ws"),
            "sandbox_state_store": "auto",
            "sandbox_state_redis_url": "redis://127.0.0.1:1/0",
        },
    )
    assert result.exit_code == 0
    assert result.state_backend == "file"


def test_sandbox_subagent_scope_isolates_leases(tmp_path: Path) -> None:
    common = {
        "sandbox_enabled": True,
        "sandbox_mode": "local",
        "sandbox_workspace_root": str(tmp_path / "ws"),
        "sandbox_state_store": "file",
        "sandbox_state_file_path": str(tmp_path / "state.json"),
        "sandbox_scope": "subagent",
    }
    alpha_first = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('alpha-1')\"",
        thread_id="thread-scope",
        runtime_hitl={**common, "sandbox_scope_id": "sa-alpha"},
    )
    beta_first = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('beta-1')\"",
        thread_id="thread-scope",
        runtime_hitl={**common, "sandbox_scope_id": "sa-beta"},
    )
    alpha_second = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('alpha-2')\"",
        thread_id="thread-scope",
        runtime_hitl={**common, "sandbox_scope_id": "sa-alpha"},
    )

    assert alpha_first.scope == "subagent"
    assert alpha_first.scope_id == "sa-alpha"
    assert beta_first.scope_id == "sa-beta"
    assert beta_first.lease_id != alpha_first.lease_id
    assert alpha_second.scope_id == "sa-alpha"
    assert alpha_second.reused is True
    assert alpha_second.lease_id == alpha_first.lease_id


def test_sandbox_release_subagent_scope_is_targeted(tmp_path: Path) -> None:
    common = {
        "sandbox_enabled": True,
        "sandbox_mode": "local",
        "sandbox_workspace_root": str(tmp_path / "ws"),
        "sandbox_state_store": "file",
        "sandbox_state_file_path": str(tmp_path / "state.json"),
        "sandbox_scope": "subagent",
    }
    alpha_first = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('alpha')\"",
        thread_id="thread-scope-release",
        runtime_hitl={**common, "sandbox_scope_id": "sa-alpha"},
    )
    beta_first = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('beta')\"",
        thread_id="thread-scope-release",
        runtime_hitl={**common, "sandbox_scope_id": "sa-beta"},
    )
    assert sandbox_runtime.release_sandbox_lease(
        thread_id="thread-scope-release",
        runtime_hitl={**common, "sandbox_scope_id": "sa-alpha"},
        reason="unit-test-release-alpha",
    )
    beta_second = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('beta-2')\"",
        thread_id="thread-scope-release",
        runtime_hitl={**common, "sandbox_scope_id": "sa-beta"},
    )
    alpha_second = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print('alpha-2')\"",
        thread_id="thread-scope-release",
        runtime_hitl={**common, "sandbox_scope_id": "sa-alpha"},
    )

    assert beta_second.reused is True
    assert beta_second.lease_id == beta_first.lease_id
    assert alpha_second.reused is False
    assert alpha_second.lease_id != alpha_first.lease_id
