from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


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
    "sandbox_phase1_test_module",
    "app/agents/new_chat/sandbox_runtime.py",
)


def test_sandbox_config_defaults_disabled() -> None:
    config = sandbox_runtime.sandbox_config_from_runtime_flags(None)
    assert config.enabled is False
    assert config.mode == sandbox_runtime.SANDBOX_MODE_DOCKER


def test_sandbox_config_parses_flags() -> None:
    config = sandbox_runtime.sandbox_config_from_runtime_flags(
        {
            "sandbox_enabled": "true",
            "sandbox_mode": "local",
            "sandbox_workspace_root": "/tmp/sandbox-tests",
            "sandbox_timeout_seconds": "75",
            "sandbox_max_output_bytes": "2048",
            "sandbox_container_prefix": "custom-prefix",
            "sandbox_scope": "subagent",
            "sandbox_scope_id": "sa-123",
        }
    )
    assert config.enabled is True
    assert config.mode == sandbox_runtime.SANDBOX_MODE_LOCAL
    assert config.workspace_root == "/tmp/sandbox-tests"
    assert config.timeout_seconds == 75
    assert config.max_output_bytes == 2048
    assert config.docker_container_prefix == "custom-prefix"
    assert config.scope == "subagent"
    assert config.scope_id == "sa-123"


def test_build_sandbox_container_name_is_deterministic() -> None:
    name_a = sandbox_runtime.build_sandbox_container_name(
        thread_id="thread-123",
        container_prefix="OneSeek Sandbox##",
    )
    name_b = sandbox_runtime.build_sandbox_container_name(
        thread_id="thread-123",
        container_prefix="OneSeek Sandbox##",
    )
    assert name_a == name_b
    assert name_a.startswith("oneseek-sandbox-")
    assert len(name_a) <= 63


def test_command_looks_long_lived_detection() -> None:
    assert sandbox_runtime.command_looks_long_lived("npm run dev") is True
    assert sandbox_runtime.command_looks_long_lived("python3 -c \"print(1)\"") is False


def test_run_sandbox_command_local_mode(tmp_path: Path) -> None:
    result = sandbox_runtime.run_sandbox_command(
        command="python3 -c \"print(40+2)\"",
        thread_id="thread-local-1",
        runtime_hitl={
            "sandbox_enabled": True,
            "sandbox_mode": "local",
            "sandbox_workspace_root": str(tmp_path),
        },
    )
    assert result.mode == sandbox_runtime.SANDBOX_MODE_LOCAL
    assert result.exit_code == 0
    assert "42" in result.output
    assert Path(result.workspace_path).exists()


def test_run_sandbox_command_requires_flag(tmp_path: Path) -> None:
    with pytest.raises(sandbox_runtime.SandboxExecutionError):
        sandbox_runtime.run_sandbox_command(
            command="echo hi",
            thread_id="thread-local-2",
            runtime_hitl={
                "sandbox_enabled": False,
                "sandbox_mode": "local",
                "sandbox_workspace_root": str(tmp_path),
            },
        )


def test_run_sandbox_command_rejects_long_lived(tmp_path: Path) -> None:
    with pytest.raises(sandbox_runtime.SandboxExecutionError):
        sandbox_runtime.run_sandbox_command(
            command="npm run dev",
            thread_id="thread-local-3",
            runtime_hitl={
                "sandbox_enabled": True,
                "sandbox_mode": "local",
                "sandbox_workspace_root": str(tmp_path),
            },
        )
