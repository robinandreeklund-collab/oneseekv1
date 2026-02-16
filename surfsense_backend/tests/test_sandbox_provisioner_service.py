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


provisioner_module = _load_module(
    "sandbox_provisioner_service_test_module",
    "app/sandbox_provisioner/main.py",
)


def _make_settings() -> object:
    return provisioner_module.ProvisionerSettings(
        namespace="oneseek-sandbox",
        kubectl_binary="kubectl",
        kubectl_context=None,
        worker_image="python:3.12-slim",
        worker_container_name="sandbox",
        pod_prefix="oneseek-sb",
        workspace_dir="/workspace",
        startup_timeout_seconds=30,
        idle_timeout_seconds=60,
        cleanup_interval_seconds=60,
        max_timeout_seconds=600,
        max_output_bytes=100_000,
        service_api_key=None,
        pod_cpu_request=None,
        pod_memory_request=None,
        pod_cpu_limit=None,
        pod_memory_limit=None,
    )


def test_build_sandbox_pod_name_deterministic() -> None:
    name_a = provisioner_module.build_sandbox_pod_name(
        sandbox_id="thread-123",
        pod_prefix="OneSeek Sandbox##",
    )
    name_b = provisioner_module.build_sandbox_pod_name(
        sandbox_id="thread-123",
        pod_prefix="OneSeek Sandbox##",
    )
    assert name_a == name_b
    assert name_a.startswith("oneseek-sandbox")
    assert len(name_a) <= 63


def test_normalize_workspace_path_rejects_traversal() -> None:
    try:
        provisioner_module.normalize_workspace_path("/workspace/../etc/passwd")
        assert False, "Expected ProvisionerError for path traversal"
    except provisioner_module.ProvisionerError:
        pass


def test_ensure_pod_reuses_running_pod(monkeypatch) -> None:
    provisioner = provisioner_module.KubectlSandboxProvisioner(_make_settings())
    monkeypatch.setattr(
        provisioner,
        "_get_pod",
        lambda **kwargs: {
            "status": {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "True"}],
            }
        },
    )
    monkeypatch.setattr(provisioner, "_wait_for_pod_ready", lambda **kwargs: None)
    monkeypatch.setattr(provisioner, "_annotate_last_used", lambda **kwargs: None)
    monkeypatch.setattr(
        provisioner,
        "_create_pod",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("Should not create pod")),
    )

    pod_name, reused = provisioner._ensure_pod(
        thread_key="thread-123",
        sandbox_id="thread-123",
    )
    assert reused is True
    assert pod_name.startswith("oneseek-sb")


def test_cleanup_idle_pods_deletes_stale_entries(monkeypatch) -> None:
    provisioner = provisioner_module.KubectlSandboxProvisioner(_make_settings())
    now_ref = {"value": 10_000}
    monkeypatch.setattr(provisioner_module.time, "time", lambda: float(now_ref["value"]))
    deleted: list[str] = []
    monkeypatch.setattr(provisioner, "_delete_pod", lambda **kwargs: deleted.append(kwargs["pod_name"]))
    monkeypatch.setattr(
        provisioner,
        "_run_kubectl_json",
        lambda **kwargs: {
            "items": [
                {
                    "metadata": {
                        "name": "stale-pod",
                        "annotations": {
                            "oneseek.ai/last-used-ts": str(now_ref["value"] - 120),
                        },
                    }
                },
                {
                    "metadata": {
                        "name": "fresh-pod",
                        "annotations": {
                            "oneseek.ai/last-used-ts": str(now_ref["value"] - 10),
                        },
                    }
                },
            ]
        },
    )

    removed = provisioner.cleanup_idle_pods()
    assert removed == ["stale-pod"]
    assert deleted == ["stale-pod"]
