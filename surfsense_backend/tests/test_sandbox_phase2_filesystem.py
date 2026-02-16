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
    "sandbox_phase2_filesystem_test_module",
    "app/agents/new_chat/sandbox_runtime.py",
)


def _runtime_flags(tmp_path: Path) -> dict[str, object]:
    return {
        "sandbox_enabled": True,
        "sandbox_mode": "local",
        "sandbox_workspace_root": str(tmp_path),
    }


def test_sandbox_filesystem_write_read_and_ls(tmp_path: Path) -> None:
    flags = _runtime_flags(tmp_path)
    thread_id = "thread-fs-1"
    written_path = sandbox_runtime.sandbox_write_text_file(
        thread_id=thread_id,
        runtime_hitl=flags,
        path="/workspace/src/example.py",
        content="line one\nline two\nline three\n",
    )
    assert written_path == "/workspace/src/example.py"

    content = sandbox_runtime.sandbox_read_text_file(
        thread_id=thread_id,
        runtime_hitl=flags,
        path="/workspace/src/example.py",
        start_line=2,
        end_line=3,
    )
    assert content == "2|line two\n3|line three"

    entries = sandbox_runtime.sandbox_list_directory(
        thread_id=thread_id,
        runtime_hitl=flags,
        path="/workspace",
        max_depth=3,
    )
    assert "/workspace/src/" in entries
    assert "/workspace/src/example.py" in entries


def test_sandbox_filesystem_replace_requires_replace_all(tmp_path: Path) -> None:
    flags = _runtime_flags(tmp_path)
    thread_id = "thread-fs-2"
    sandbox_runtime.sandbox_write_text_file(
        thread_id=thread_id,
        runtime_hitl=flags,
        path="/workspace/data.txt",
        content="hello world\nhello world\n",
    )

    with pytest.raises(sandbox_runtime.SandboxExecutionError):
        sandbox_runtime.sandbox_replace_text_file(
            thread_id=thread_id,
            runtime_hitl=flags,
            path="/workspace/data.txt",
            old_text="hello",
            new_text="hi",
            replace_all=False,
        )

    replaced_path, replaced_count = sandbox_runtime.sandbox_replace_text_file(
        thread_id=thread_id,
        runtime_hitl=flags,
        path="/workspace/data.txt",
        old_text="hello",
        new_text="hi",
        replace_all=True,
    )
    assert replaced_path == "/workspace/data.txt"
    assert replaced_count == 2

    content = sandbox_runtime.sandbox_read_text_file(
        thread_id=thread_id,
        runtime_hitl=flags,
        path="/workspace/data.txt",
    )
    assert "1|hi world" in content
    assert "2|hi world" in content


def test_sandbox_filesystem_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(sandbox_runtime.SandboxExecutionError):
        sandbox_runtime.sandbox_write_text_file(
            thread_id="thread-fs-3",
            runtime_hitl=_runtime_flags(tmp_path),
            path="/workspace/../outside.txt",
            content="unsafe",
        )


def test_sandbox_filesystem_requires_enabled_flag(tmp_path: Path) -> None:
    with pytest.raises(sandbox_runtime.SandboxExecutionError):
        sandbox_runtime.sandbox_list_directory(
            thread_id="thread-fs-4",
            runtime_hitl={
                "sandbox_enabled": False,
                "sandbox_mode": "local",
                "sandbox_workspace_root": str(tmp_path),
            },
            path="/workspace",
        )
