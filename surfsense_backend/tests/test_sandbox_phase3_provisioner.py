from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from urllib import error as urllib_error

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
    "sandbox_phase3_provisioner_test_module",
    "app/agents/new_chat/sandbox_runtime.py",
)


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _decode_request_payload(request) -> dict[str, object]:
    raw_body = request.data or b"{}"
    return json.loads(raw_body.decode("utf-8"))


def test_sandbox_config_supports_provisioner_mode() -> None:
    config = sandbox_runtime.sandbox_config_from_runtime_flags(
        {
            "sandbox_enabled": True,
            "sandbox_mode": "provisioner",
            "sandbox_provisioner_url": "http://sandbox.local:8002",
            "sandbox_provisioner_api_key": "secret-token",
        }
    )
    assert config.enabled is True
    assert config.mode == sandbox_runtime.SANDBOX_MODE_PROVISIONER
    assert config.provisioner_url == "http://sandbox.local:8002"
    assert config.provisioner_api_key == "secret-token"


def test_sandbox_config_supports_remote_alias() -> None:
    config = sandbox_runtime.sandbox_config_from_runtime_flags(
        {
            "sandbox_enabled": True,
            "sandbox_mode": "remote",
        }
    )
    assert config.mode == sandbox_runtime.SANDBOX_MODE_PROVISIONER


def test_run_sandbox_command_provisioner_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = _decode_request_payload(request)
        captured["headers"] = dict(request.headers)
        return _FakeHTTPResponse(
            {
                "output": "ok",
                "exit_code": 0,
                "truncated": False,
                "workspace_path": "/workspace/thread-123",
                "container_name": "sandbox-pod-123",
            }
        )

    monkeypatch.setattr(sandbox_runtime.urllib_request, "urlopen", _fake_urlopen)

    result = sandbox_runtime.run_sandbox_command(
        command="echo hi",
        thread_id="thread-123",
        runtime_hitl={
            "sandbox_enabled": True,
            "sandbox_mode": "provisioner",
            "sandbox_provisioner_url": "http://sandbox.local:8002",
            "sandbox_provisioner_api_key": "token-abc",
        },
    )

    assert result.mode == sandbox_runtime.SANDBOX_MODE_PROVISIONER
    assert result.exit_code == 0
    assert result.output == "ok"
    assert result.workspace_path == "/workspace/thread-123"
    assert result.container_name == "sandbox-pod-123"
    assert str(captured.get("url", "")).endswith("/v1/sandbox/execute")
    payload = captured.get("payload")
    assert isinstance(payload, dict)
    assert payload["command"] == "echo hi"
    headers = captured.get("headers")
    assert isinstance(headers, dict)
    assert headers.get("Authorization") == "Bearer token-abc"


def test_sandbox_filesystem_calls_provisioner_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def _fake_urlopen(request, timeout=0):
        _ = timeout
        url = str(request.full_url)
        payload = _decode_request_payload(request)
        calls.append((url, payload))
        if url.endswith("/v1/sandbox/acquire"):
            return _FakeHTTPResponse(
                {
                    "sandbox_id": "thread-456",
                    "workspace_path": "/workspace",
                    "pod_name": "sandbox-pod-456",
                }
            )
        if url.endswith("/v1/sandbox/ls"):
            return _FakeHTTPResponse({"entries": ["/workspace/src/", "/workspace/src/main.py"]})
        if url.endswith("/v1/sandbox/write_file"):
            return _FakeHTTPResponse({"path": "/workspace/src/main.py"})
        if url.endswith("/v1/sandbox/read_file"):
            return _FakeHTTPResponse({"content": "1|print('hello')"})
        if url.endswith("/v1/sandbox/replace"):
            return _FakeHTTPResponse({"path": "/workspace/src/main.py", "replaced": 1})
        raise AssertionError(f"Unexpected endpoint: {url}")

    monkeypatch.setattr(sandbox_runtime.urllib_request, "urlopen", _fake_urlopen)

    runtime_hitl = {
        "sandbox_enabled": True,
        "sandbox_mode": "provisioner",
        "sandbox_provisioner_url": "http://sandbox.local:8002",
    }

    entries = sandbox_runtime.sandbox_list_directory(
        thread_id="thread-456",
        runtime_hitl=runtime_hitl,
        path="/workspace",
    )
    assert entries == ["/workspace/src/", "/workspace/src/main.py"]

    write_path = sandbox_runtime.sandbox_write_text_file(
        thread_id="thread-456",
        runtime_hitl=runtime_hitl,
        path="/workspace/src/main.py",
        content="print('hello')\n",
    )
    assert write_path == "/workspace/src/main.py"

    content = sandbox_runtime.sandbox_read_text_file(
        thread_id="thread-456",
        runtime_hitl=runtime_hitl,
        path="/workspace/src/main.py",
    )
    assert content == "1|print('hello')"

    replace_path, replaced = sandbox_runtime.sandbox_replace_text_file(
        thread_id="thread-456",
        runtime_hitl=runtime_hitl,
        path="/workspace/src/main.py",
        old_text="hello",
        new_text="hej",
    )
    assert replace_path == "/workspace/src/main.py"
    assert replaced == 1

    called_urls = [url for url, _payload in calls]
    assert any(url.endswith("/v1/sandbox/acquire") for url in called_urls)
    assert any(url.endswith("/v1/sandbox/ls") for url in called_urls)
    assert any(url.endswith("/v1/sandbox/write_file") for url in called_urls)
    assert any(url.endswith("/v1/sandbox/read_file") for url in called_urls)
    assert any(url.endswith("/v1/sandbox/replace") for url in called_urls)


def test_sandbox_provisioner_path_traversal_blocked() -> None:
    with pytest.raises(sandbox_runtime.SandboxExecutionError):
        sandbox_runtime.sandbox_list_directory(
            thread_id="thread-789",
            runtime_hitl={
                "sandbox_enabled": True,
                "sandbox_mode": "provisioner",
                "sandbox_provisioner_url": "http://sandbox.local:8002",
            },
            path="/workspace/../etc",
        )


def test_sandbox_provisioner_request_error_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(request, timeout=0):
        _ = request, timeout
        raise urllib_error.URLError("connection refused")

    monkeypatch.setattr(sandbox_runtime.urllib_request, "urlopen", _fake_urlopen)
    with pytest.raises(sandbox_runtime.SandboxExecutionError):
        sandbox_runtime.run_sandbox_command(
            command="echo hi",
            thread_id="thread-fail",
            runtime_hitl={
                "sandbox_enabled": True,
                "sandbox_mode": "provisioner",
                "sandbox_provisioner_url": "http://sandbox.local:8002",
            },
        )


def test_sandbox_provisioner_idle_timeout_triggers_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    now_ref = {"value": 1_000}

    monkeypatch.setattr(
        sandbox_runtime.time,
        "time",
        lambda: float(now_ref["value"]),
    )

    def _fake_urlopen(request, timeout=0):
        _ = timeout
        url = str(request.full_url)
        calls.append(url)
        if url.endswith("/v1/sandbox/acquire"):
            return _FakeHTTPResponse(
                {
                    "sandbox_id": "thread-idle",
                    "workspace_path": "/workspace/thread-idle",
                    "pod_name": "sandbox-pod-idle",
                }
            )
        if url.endswith("/v1/sandbox/release"):
            return _FakeHTTPResponse({"released": True})
        if url.endswith("/v1/sandbox/execute"):
            return _FakeHTTPResponse(
                {
                    "output": "ok",
                    "exit_code": 0,
                    "workspace_path": "/workspace/thread-idle",
                    "container_name": "sandbox-pod-idle",
                }
            )
        raise AssertionError(f"Unexpected endpoint: {url}")

    monkeypatch.setattr(sandbox_runtime.urllib_request, "urlopen", _fake_urlopen)

    runtime_hitl = {
        "sandbox_enabled": True,
        "sandbox_mode": "provisioner",
        "sandbox_provisioner_url": "http://sandbox.local:8002",
        "sandbox_idle_timeout_seconds": 5,
        "sandbox_state_store": "file",
        "sandbox_state_file_path": str(tmp_path / "sandbox_state.json"),
    }
    first = sandbox_runtime.run_sandbox_command(
        command="echo first",
        thread_id="thread-idle",
        runtime_hitl=runtime_hitl,
    )
    assert first.exit_code == 0
    now_ref["value"] = 1_010
    second = sandbox_runtime.run_sandbox_command(
        command="echo second",
        thread_id="thread-idle",
        runtime_hitl=runtime_hitl,
    )
    assert second.exit_code == 0
    assert any(url.endswith("/v1/sandbox/release") for url in calls)
