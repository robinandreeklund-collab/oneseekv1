from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

SANDBOX_WORKSPACE_PREFIX = "/workspace"
_POD_LABEL_KEY = "app"
_POD_LABEL_VALUE = "oneseek-sandbox-worker"
_ANNOTATION_LAST_USED = "oneseek.ai/last-used-ts"
_ANNOTATION_CREATED_AT = "oneseek.ai/created-at"
_ANNOTATION_THREAD_KEY = "oneseek.ai/thread-key"
_ANNOTATION_SANDBOX_ID = "oneseek.ai/sandbox-id"

_LONG_LIVED_PATTERNS = (
    re.compile(r"\bnpm\s+run\s+(dev|start)\b", re.IGNORECASE),
    re.compile(r"\bpnpm\s+run\s+(dev|start)\b", re.IGNORECASE),
    re.compile(r"\byarn\s+(dev|start)\b", re.IGNORECASE),
    re.compile(r"\btail\s+-f\b", re.IGNORECASE),
    re.compile(r"\bwatch\b", re.IGNORECASE),
)

_LS_SCRIPT = r"""
import json
import os
import pathlib
import sys

payload = json.loads(sys.argv[1])
path = str(payload.get("path") or "/workspace")
max_depth = max(0, min(int(payload.get("max_depth", 2)), 6))
max_entries = max(1, min(int(payload.get("max_entries", 500)), 5000))
workspace = pathlib.Path("/workspace")
target = pathlib.Path(path).resolve()

if not str(target).startswith("/workspace"):
    print(json.dumps({"error": "Path escapes workspace."}, ensure_ascii=True))
    raise SystemExit(2)
if not target.exists():
    print(json.dumps({"error": "Directory not found."}, ensure_ascii=True))
    raise SystemExit(2)
if not target.is_dir():
    print(json.dumps({"error": "Path is not a directory."}, ensure_ascii=True))
    raise SystemExit(2)

root_depth = len(target.parts)
entries = []
for current_root, dirs, files in os.walk(target):
    current = pathlib.Path(current_root)
    depth = len(current.parts) - root_depth
    if depth > max_depth:
        dirs[:] = []
        continue
    dirs.sort()
    files.sort()
    rel_root = current.relative_to(workspace)
    display_root = "/workspace" if str(rel_root) == "." else f"/workspace/{rel_root.as_posix()}"
    for directory in dirs:
        entries.append(f"{display_root}/{directory}/")
        if len(entries) >= max_entries:
            print(json.dumps({"entries": entries}, ensure_ascii=True))
            raise SystemExit(0)
    for file_name in files:
        entries.append(f"{display_root}/{file_name}")
        if len(entries) >= max_entries:
            print(json.dumps({"entries": entries}, ensure_ascii=True))
            raise SystemExit(0)
    if depth >= max_depth:
        dirs[:] = []

print(json.dumps({"entries": entries}, ensure_ascii=True))
"""

_READ_FILE_SCRIPT = r"""
import json
import pathlib
import sys

payload = json.loads(sys.argv[1])
path = str(payload.get("path") or "")
start_line = payload.get("start_line")
end_line = payload.get("end_line")
max_lines = max(1, min(int(payload.get("max_lines", 400)), 4000))

target = pathlib.Path(path).resolve()
if not str(target).startswith("/workspace"):
    print(json.dumps({"error": "Path escapes workspace."}, ensure_ascii=True))
    raise SystemExit(2)
if not target.exists():
    print(json.dumps({"error": "File not found."}, ensure_ascii=True))
    raise SystemExit(2)
if not target.is_file():
    print(json.dumps({"error": "Path is not a file."}, ensure_ascii=True))
    raise SystemExit(2)

try:
    lines = target.read_text(encoding="utf-8").splitlines()
except UnicodeDecodeError:
    print(json.dumps({"error": "Failed to decode file as UTF-8."}, ensure_ascii=True))
    raise SystemExit(2)

if not lines:
    print(json.dumps({"content": "(empty)"}, ensure_ascii=True))
    raise SystemExit(0)

line_count = len(lines)
start = 1 if start_line is None else max(1, int(start_line))
if start > line_count:
    print(json.dumps({"error": f"start_line {start} exceeds file length ({line_count})."}, ensure_ascii=True))
    raise SystemExit(2)
if end_line is None:
    end = min(line_count, start + max_lines - 1)
else:
    end = min(line_count, int(end_line))
    if end < start:
        print(json.dumps({"error": "end_line cannot be less than start_line."}, ensure_ascii=True))
        raise SystemExit(2)
    if (end - start + 1) > max_lines:
        end = start + max_lines - 1

selected = lines[start - 1 : end]
formatted = [f"{idx}|{value}" for idx, value in enumerate(selected, start=start)]
print(json.dumps({"content": "\n".join(formatted)}, ensure_ascii=True))
"""

_WRITE_FILE_SCRIPT = r"""
import json
import pathlib
import sys

payload = json.loads(sys.argv[1])
path = str(payload.get("path") or "")
content = str(payload.get("content") or "")
append = bool(payload.get("append", False))
target = pathlib.Path(path).resolve()

if not str(target).startswith("/workspace"):
    print(json.dumps({"error": "Path escapes workspace."}, ensure_ascii=True))
    raise SystemExit(2)
target.parent.mkdir(parents=True, exist_ok=True)
mode = "a" if append else "w"
with target.open(mode, encoding="utf-8") as handle:
    handle.write(content)

rel = target.relative_to(pathlib.Path("/workspace"))
display_path = f"/workspace/{rel.as_posix()}" if str(rel) != "." else "/workspace"
print(json.dumps({"path": display_path}, ensure_ascii=True))
"""

_REPLACE_FILE_SCRIPT = r"""
import json
import pathlib
import sys

payload = json.loads(sys.argv[1])
path = str(payload.get("path") or "")
old_text = str(payload.get("old_text") or "")
new_text = str(payload.get("new_text") or "")
replace_all = bool(payload.get("replace_all", False))
target = pathlib.Path(path).resolve()

if not str(target).startswith("/workspace"):
    print(json.dumps({"error": "Path escapes workspace."}, ensure_ascii=True))
    raise SystemExit(2)
if not target.exists():
    print(json.dumps({"error": "File not found."}, ensure_ascii=True))
    raise SystemExit(2)
if not target.is_file():
    print(json.dumps({"error": "Path is not a file."}, ensure_ascii=True))
    raise SystemExit(2)
if not old_text:
    print(json.dumps({"error": "old_text cannot be empty."}, ensure_ascii=True))
    raise SystemExit(2)

content = target.read_text(encoding="utf-8")
occurrences = content.count(old_text)
if occurrences <= 0:
    print(json.dumps({"error": "old_text not found in file."}, ensure_ascii=True))
    raise SystemExit(2)
if not replace_all and occurrences != 1:
    print(json.dumps({"error": "old_text appears multiple times; set replace_all=true to replace all."}, ensure_ascii=True))
    raise SystemExit(2)

updated = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
target.write_text(updated, encoding="utf-8")
replaced = occurrences if replace_all else 1
rel = target.relative_to(pathlib.Path("/workspace"))
display_path = f"/workspace/{rel.as_posix()}" if str(rel) != "." else "/workspace"
print(json.dumps({"path": display_path, "replaced": int(replaced)}, ensure_ascii=True))
"""


def _coerce_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def _sanitize_k8s_segment(value: Any, *, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    if not normalized:
        normalized = fallback
    return normalized[:63].strip("-") or fallback


def _safe_shell_output(*, stdout: str, stderr: str) -> str:
    parts: list[str] = []
    cleaned_stdout = str(stdout or "").strip()
    if cleaned_stdout:
        parts.append(cleaned_stdout)
    cleaned_stderr = str(stderr or "").strip()
    if cleaned_stderr:
        for line in cleaned_stderr.splitlines():
            line = str(line or "").strip()
            if line:
                parts.append(f"[stderr] {line}")
    if not parts:
        return "<no output>"
    return "\n".join(parts)


def _truncate_text(text: str, *, max_bytes: int) -> tuple[str, bool]:
    safe_limit = max(1024, int(max_bytes))
    if len(text.encode("utf-8")) <= safe_limit:
        return text, False
    encoded = text.encode("utf-8")[:safe_limit]
    truncated = encoded.decode("utf-8", errors="ignore")
    return truncated + "\n\n[Output truncated due to size limits.]", True


def command_looks_long_lived(command: str) -> bool:
    normalized = str(command or "").strip()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _LONG_LIVED_PATTERNS)


def build_sandbox_pod_name(*, sandbox_id: str, pod_prefix: str) -> str:
    safe_prefix = _sanitize_k8s_segment(pod_prefix, fallback="oneseek-sb")
    safe_sandbox = _sanitize_k8s_segment(sandbox_id, fallback="sandbox")
    digest = hashlib.sha1(safe_sandbox.encode("utf-8")).hexdigest()[:10]
    name = f"{safe_prefix}-{safe_sandbox[:30]}-{digest}"
    return name[:63].strip("-")


def normalize_workspace_path(path: str) -> str:
    normalized_path = str(path or "").strip()
    if not normalized_path:
        raise ProvisionerError("Path cannot be empty.")
    if not normalized_path.startswith("/"):
        raise ProvisionerError("Path must be absolute and start with '/'.")
    if normalized_path == SANDBOX_WORKSPACE_PREFIX:
        return normalized_path
    if normalized_path.startswith(f"{SANDBOX_WORKSPACE_PREFIX}/"):
        relative = normalized_path[len(SANDBOX_WORKSPACE_PREFIX) :].lstrip("/")
    else:
        relative = normalized_path.lstrip("/")
    relative_path = Path(relative)
    if any(part in {"..", ""} for part in relative_path.parts):
        raise ProvisionerError(f"Path traversal is not allowed: {normalized_path}")
    return f"{SANDBOX_WORKSPACE_PREFIX}/{relative_path.as_posix()}"


def _now_ts() -> int:
    return int(time.time())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ProvisionerSettings:
    namespace: str
    kubectl_binary: str
    kubectl_context: str | None
    worker_image: str
    worker_container_name: str
    pod_prefix: str
    workspace_dir: str
    startup_timeout_seconds: int
    idle_timeout_seconds: int
    cleanup_interval_seconds: int
    max_timeout_seconds: int
    max_output_bytes: int
    service_api_key: str | None
    pod_cpu_request: str | None
    pod_memory_request: str | None
    pod_cpu_limit: str | None
    pod_memory_limit: str | None


def load_settings_from_env() -> ProvisionerSettings:
    return ProvisionerSettings(
        namespace=str(os.getenv("PROVISIONER_NAMESPACE") or "oneseek-sandbox").strip(),
        kubectl_binary=str(os.getenv("PROVISIONER_KUBECTL_BINARY") or "kubectl").strip(),
        kubectl_context=str(os.getenv("PROVISIONER_KUBECTL_CONTEXT") or "").strip() or None,
        worker_image=str(
            os.getenv("PROVISIONER_SANDBOX_IMAGE") or "python:3.12-slim"
        ).strip(),
        worker_container_name=str(
            os.getenv("PROVISIONER_WORKER_CONTAINER_NAME") or "sandbox"
        ).strip(),
        pod_prefix=str(os.getenv("PROVISIONER_POD_PREFIX") or "oneseek-sb").strip(),
        workspace_dir=str(
            os.getenv("PROVISIONER_WORKSPACE_DIR") or SANDBOX_WORKSPACE_PREFIX
        ).strip(),
        startup_timeout_seconds=_coerce_int(
            os.getenv("PROVISIONER_STARTUP_TIMEOUT_SECONDS"),
            default=120,
            min_value=10,
            max_value=900,
        ),
        idle_timeout_seconds=_coerce_int(
            os.getenv("PROVISIONER_IDLE_TIMEOUT_SECONDS"),
            default=15 * 60,
            min_value=30,
            max_value=86_400,
        ),
        cleanup_interval_seconds=_coerce_int(
            os.getenv("PROVISIONER_CLEANUP_INTERVAL_SECONDS"),
            default=60,
            min_value=10,
            max_value=3600,
        ),
        max_timeout_seconds=_coerce_int(
            os.getenv("PROVISIONER_MAX_TIMEOUT_SECONDS"),
            default=600,
            min_value=30,
            max_value=3600,
        ),
        max_output_bytes=_coerce_int(
            os.getenv("PROVISIONER_MAX_OUTPUT_BYTES"),
            default=1_000_000,
            min_value=1024,
            max_value=2_000_000,
        ),
        service_api_key=str(os.getenv("PROVISIONER_API_KEY") or "").strip() or None,
        pod_cpu_request=str(os.getenv("PROVISIONER_POD_CPU_REQUEST") or "").strip() or None,
        pod_memory_request=str(os.getenv("PROVISIONER_POD_MEMORY_REQUEST") or "").strip()
        or None,
        pod_cpu_limit=str(os.getenv("PROVISIONER_POD_CPU_LIMIT") or "").strip() or None,
        pod_memory_limit=str(os.getenv("PROVISIONER_POD_MEMORY_LIMIT") or "").strip() or None,
    )


class ProvisionerError(RuntimeError):
    pass


class AcquireRequest(BaseModel):
    thread_id: str | None = None
    thread_key: str | None = None
    sandbox_id: str | None = None


class ReleaseRequest(BaseModel):
    thread_id: str | None = None
    thread_key: str | None = None
    sandbox_id: str | None = None
    reason: str = "manual-release"


class ExecuteRequest(BaseModel):
    thread_id: str | None = None
    thread_key: str | None = None
    sandbox_id: str | None = None
    command: str
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    max_output_bytes: int | None = Field(default=None, ge=1024, le=2_000_000)


class ListRequest(BaseModel):
    thread_id: str | None = None
    thread_key: str | None = None
    sandbox_id: str | None = None
    path: str = SANDBOX_WORKSPACE_PREFIX
    max_depth: int = Field(default=2, ge=0, le=10)
    max_entries: int = Field(default=500, ge=1, le=5000)


class ReadFileRequest(BaseModel):
    thread_id: str | None = None
    thread_key: str | None = None
    sandbox_id: str | None = None
    path: str
    start_line: int | None = None
    end_line: int | None = None
    max_lines: int = Field(default=400, ge=1, le=4000)


class WriteFileRequest(BaseModel):
    thread_id: str | None = None
    thread_key: str | None = None
    sandbox_id: str | None = None
    path: str
    content: str
    append: bool = False


class ReplaceRequest(BaseModel):
    thread_id: str | None = None
    thread_key: str | None = None
    sandbox_id: str | None = None
    path: str
    old_text: str
    new_text: str
    replace_all: bool = False


class KubectlSandboxProvisioner:
    def __init__(self, settings: ProvisionerSettings) -> None:
        self.settings = settings

    def _resolve_ids(
        self,
        *,
        thread_id: str | None,
        thread_key: str | None,
        sandbox_id: str | None,
    ) -> tuple[str, str, str]:
        resolved_thread_id = str(thread_id or thread_key or sandbox_id or "thread-default").strip()
        resolved_thread_key = _sanitize_k8s_segment(
            thread_key or resolved_thread_id,
            fallback="thread-default",
        )
        resolved_sandbox_id = _sanitize_k8s_segment(
            sandbox_id or resolved_thread_key,
            fallback=resolved_thread_key,
        )
        return resolved_thread_id, resolved_thread_key, resolved_sandbox_id

    def _kubectl_cmd(self, args: list[str]) -> list[str]:
        cmd = [self.settings.kubectl_binary]
        if self.settings.kubectl_context:
            cmd.extend(["--context", self.settings.kubectl_context])
        cmd.extend(args)
        return cmd

    def _run_cmd(
        self,
        *,
        args: list[str],
        timeout_seconds: int,
        input_text: str | None = None,
    ) -> tuple[str, str, int, bool]:
        cmd = self._kubectl_cmd(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=float(timeout_seconds),
                input=input_text,
            )
        except subprocess.TimeoutExpired:
            return "", "kubectl command timed out.", 124, True
        except FileNotFoundError as exc:
            raise ProvisionerError(f"Kubectl binary not found: {exc}") from exc
        return str(result.stdout or ""), str(result.stderr or ""), int(result.returncode), False

    def _run_kubectl_json(
        self,
        *,
        args: list[str],
        timeout_seconds: int,
        input_text: str | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
        stdout, stderr, exit_code, timed_out = self._run_cmd(
            args=args,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
        )
        if timed_out:
            raise ProvisionerError(_safe_shell_output(stdout=stdout, stderr=stderr))
        if exit_code != 0:
            error_text = _safe_shell_output(stdout=stdout, stderr=stderr)
            lowered = error_text.lower()
            if allow_not_found and (
                "notfound" in lowered or "not found" in lowered
            ):
                return None
            raise ProvisionerError(error_text)
        text = str(stdout or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProvisionerError(f"Invalid JSON from kubectl: {text}") from exc
        if not isinstance(parsed, dict):
            raise ProvisionerError("Expected kubectl JSON object response.")
        return parsed

    def _pod_manifest(self, *, pod_name: str, thread_key: str, sandbox_id: str) -> dict[str, Any]:
        resources: dict[str, Any] = {}
        requests: dict[str, str] = {}
        limits: dict[str, str] = {}
        if self.settings.pod_cpu_request:
            requests["cpu"] = self.settings.pod_cpu_request
        if self.settings.pod_memory_request:
            requests["memory"] = self.settings.pod_memory_request
        if self.settings.pod_cpu_limit:
            limits["cpu"] = self.settings.pod_cpu_limit
        if self.settings.pod_memory_limit:
            limits["memory"] = self.settings.pod_memory_limit
        if requests:
            resources["requests"] = requests
        if limits:
            resources["limits"] = limits

        container_spec: dict[str, Any] = {
            "name": self.settings.worker_container_name,
            "image": self.settings.worker_image,
            "command": ["sh", "-lc", "while true; do sleep 3600; done"],
            "workingDir": self.settings.workspace_dir,
            "volumeMounts": [
                {
                    "name": "workspace",
                    "mountPath": self.settings.workspace_dir,
                }
            ],
        }
        if resources:
            container_spec["resources"] = resources

        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": self.settings.namespace,
                "labels": {
                    _POD_LABEL_KEY: _POD_LABEL_VALUE,
                },
                "annotations": {
                    _ANNOTATION_CREATED_AT: _now_iso(),
                    _ANNOTATION_LAST_USED: str(_now_ts()),
                    _ANNOTATION_THREAD_KEY: thread_key,
                    _ANNOTATION_SANDBOX_ID: sandbox_id,
                },
            },
            "spec": {
                "restartPolicy": "Never",
                "containers": [container_spec],
                "volumes": [{"name": "workspace", "emptyDir": {}}],
            },
        }

    def _get_pod(self, *, pod_name: str) -> dict[str, Any] | None:
        return self._run_kubectl_json(
            args=["-n", self.settings.namespace, "get", "pod", pod_name, "-o", "json"],
            timeout_seconds=10,
            allow_not_found=True,
        )

    def _create_pod(self, *, pod_name: str, thread_key: str, sandbox_id: str) -> None:
        manifest = self._pod_manifest(
            pod_name=pod_name,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        stdout, stderr, exit_code, timed_out = self._run_cmd(
            args=["-n", self.settings.namespace, "apply", "-f", "-"],
            timeout_seconds=30,
            input_text=json.dumps(manifest, ensure_ascii=True),
        )
        if timed_out or exit_code != 0:
            raise ProvisionerError(_safe_shell_output(stdout=stdout, stderr=stderr))

    def _delete_pod(self, *, pod_name: str) -> None:
        stdout, stderr, exit_code, _timed_out = self._run_cmd(
            args=["-n", self.settings.namespace, "delete", "pod", pod_name, "--ignore-not-found=true"],
            timeout_seconds=30,
        )
        if exit_code != 0:
            raise ProvisionerError(_safe_shell_output(stdout=stdout, stderr=stderr))

    def _wait_for_pod_ready(self, *, pod_name: str) -> None:
        deadline = time.monotonic() + int(self.settings.startup_timeout_seconds)
        while True:
            pod = self._get_pod(pod_name=pod_name)
            if pod:
                status = pod.get("status", {}) if isinstance(pod, dict) else {}
                phase = str(status.get("phase") or "").strip()
                conditions = status.get("conditions") or []
                ready = any(
                    isinstance(condition, dict)
                    and str(condition.get("type") or "").lower() == "ready"
                    and str(condition.get("status") or "").lower() == "true"
                    for condition in conditions
                )
                if phase == "Running" and ready:
                    return
                if phase in {"Failed", "Succeeded"}:
                    raise ProvisionerError(f"Sandbox pod '{pod_name}' entered terminal phase '{phase}'.")
            if time.monotonic() >= deadline:
                raise ProvisionerError(f"Timed out waiting for sandbox pod '{pod_name}' to become ready.")
            time.sleep(1.5)

    def _annotate_last_used(self, *, pod_name: str, thread_key: str, sandbox_id: str) -> None:
        _, stderr, exit_code, _ = self._run_cmd(
            args=[
                "-n",
                self.settings.namespace,
                "annotate",
                "pod",
                pod_name,
                f"{_ANNOTATION_LAST_USED}={_now_ts()}",
                f"{_ANNOTATION_THREAD_KEY}={thread_key}",
                f"{_ANNOTATION_SANDBOX_ID}={sandbox_id}",
                "--overwrite",
            ],
            timeout_seconds=10,
        )
        if exit_code != 0 and "not found" not in stderr.lower():
            raise ProvisionerError(_safe_shell_output(stdout="", stderr=stderr))

    def _ensure_pod(
        self,
        *,
        thread_key: str,
        sandbox_id: str,
    ) -> tuple[str, bool]:
        pod_name = build_sandbox_pod_name(
            sandbox_id=sandbox_id,
            pod_prefix=self.settings.pod_prefix,
        )
        pod = self._get_pod(pod_name=pod_name)
        reused = False
        if pod:
            phase = str(((pod.get("status") or {}) if isinstance(pod, dict) else {}).get("phase") or "")
            if phase in {"Failed", "Succeeded"}:
                self._delete_pod(pod_name=pod_name)
                pod = None
            else:
                reused = True
        if not pod:
            self._create_pod(
                pod_name=pod_name,
                thread_key=thread_key,
                sandbox_id=sandbox_id,
            )
            reused = False
        self._wait_for_pod_ready(pod_name=pod_name)
        self._annotate_last_used(
            pod_name=pod_name,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        return pod_name, reused

    def acquire(
        self,
        *,
        thread_id: str | None,
        thread_key: str | None,
        sandbox_id: str | None,
    ) -> dict[str, Any]:
        resolved_thread_id, resolved_thread_key, resolved_sandbox_id = self._resolve_ids(
            thread_id=thread_id,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        pod_name, reused = self._ensure_pod(
            thread_key=resolved_thread_key,
            sandbox_id=resolved_sandbox_id,
        )
        return {
            "thread_id": resolved_thread_id,
            "thread_key": resolved_thread_key,
            "sandbox_id": resolved_sandbox_id,
            "pod_name": pod_name,
            "container_name": pod_name,
            "workspace_path": SANDBOX_WORKSPACE_PREFIX,
            "reused": bool(reused),
        }

    def release(
        self,
        *,
        thread_id: str | None,
        thread_key: str | None,
        sandbox_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        _resolved_thread_id, _resolved_thread_key, resolved_sandbox_id = self._resolve_ids(
            thread_id=thread_id,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        pod_name = build_sandbox_pod_name(
            sandbox_id=resolved_sandbox_id,
            pod_prefix=self.settings.pod_prefix,
        )
        pod_exists = self._get_pod(pod_name=pod_name) is not None
        if pod_exists:
            self._delete_pod(pod_name=pod_name)
        return {
            "released": bool(pod_exists),
            "pod_name": pod_name,
            "sandbox_id": resolved_sandbox_id,
            "reason": str(reason or "manual-release"),
        }

    def _exec_in_pod(
        self,
        *,
        pod_name: str,
        argv: list[str],
        timeout_seconds: int,
    ) -> tuple[str, str, int, bool]:
        return self._run_cmd(
            args=[
                "-n",
                self.settings.namespace,
                "exec",
                pod_name,
                "-c",
                self.settings.worker_container_name,
                "--",
                *argv,
            ],
            timeout_seconds=timeout_seconds,
        )

    def _exec_json_action(
        self,
        *,
        pod_name: str,
        script: str,
        payload: dict[str, Any],
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        stdout, stderr, exit_code, timed_out = self._exec_in_pod(
            pod_name=pod_name,
            argv=["python3", "-c", script, json.dumps(payload, ensure_ascii=True)],
            timeout_seconds=timeout_seconds,
        )
        if timed_out:
            raise ProvisionerError("Sandbox action timed out.")
        if exit_code != 0:
            combined = _safe_shell_output(stdout=stdout, stderr=stderr)
            try:
                parsed_error = json.loads(str(stdout or "").strip())
                if isinstance(parsed_error, dict) and parsed_error.get("error"):
                    raise ProvisionerError(str(parsed_error.get("error")))
            except json.JSONDecodeError:
                pass
            raise ProvisionerError(combined)
        text = str(stdout or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProvisionerError(f"Invalid JSON action response: {text}") from exc
        if not isinstance(parsed, dict):
            raise ProvisionerError("Action response must be a JSON object.")
        if parsed.get("error"):
            raise ProvisionerError(str(parsed["error"]))
        return parsed

    def execute(
        self,
        *,
        thread_id: str | None,
        thread_key: str | None,
        sandbox_id: str | None,
        command: str,
        timeout_seconds: int | None,
        max_output_bytes: int | None,
    ) -> dict[str, Any]:
        normalized_command = str(command or "").strip()
        if not normalized_command:
            raise ProvisionerError("Command cannot be empty.")
        if command_looks_long_lived(normalized_command):
            raise ProvisionerError("Refusing long-lived command in sandbox (dev/watch/tail).")

        lease = self.acquire(
            thread_id=thread_id,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        effective_timeout = (
            _coerce_int(
                timeout_seconds,
                default=30,
                min_value=3,
                max_value=self.settings.max_timeout_seconds,
            )
            if timeout_seconds is not None
            else 30
        )
        effective_max_output = (
            _coerce_int(
                max_output_bytes,
                default=self.settings.max_output_bytes,
                min_value=1024,
                max_value=self.settings.max_output_bytes,
            )
            if max_output_bytes is not None
            else int(self.settings.max_output_bytes)
        )
        stdout, stderr, exit_code, timed_out = self._exec_in_pod(
            pod_name=str(lease["pod_name"]),
            argv=["sh", "-lc", normalized_command],
            timeout_seconds=effective_timeout,
        )
        if timed_out:
            output, truncated = _truncate_text(
                f"Error: command timed out after {int(effective_timeout)}s.",
                max_bytes=effective_max_output,
            )
            exit_code = 124
        else:
            output, truncated = _truncate_text(
                _safe_shell_output(stdout=stdout, stderr=stderr),
                max_bytes=effective_max_output,
            )
        return {
            **lease,
            "output": output,
            "exit_code": int(exit_code),
            "truncated": bool(truncated),
        }

    def list_files(
        self,
        *,
        thread_id: str | None,
        thread_key: str | None,
        sandbox_id: str | None,
        path: str,
        max_depth: int,
        max_entries: int,
    ) -> dict[str, Any]:
        normalized_path = normalize_workspace_path(path)
        lease = self.acquire(
            thread_id=thread_id,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        payload = self._exec_json_action(
            pod_name=str(lease["pod_name"]),
            script=_LS_SCRIPT,
            payload={
                "path": normalized_path,
                "max_depth": int(max_depth),
                "max_entries": int(max_entries),
            },
        )
        return {
            **lease,
            "path": normalized_path,
            "entries": payload.get("entries") or [],
        }

    def read_file(
        self,
        *,
        thread_id: str | None,
        thread_key: str | None,
        sandbox_id: str | None,
        path: str,
        start_line: int | None,
        end_line: int | None,
        max_lines: int,
    ) -> dict[str, Any]:
        normalized_path = normalize_workspace_path(path)
        lease = self.acquire(
            thread_id=thread_id,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        payload = self._exec_json_action(
            pod_name=str(lease["pod_name"]),
            script=_READ_FILE_SCRIPT,
            payload={
                "path": normalized_path,
                "start_line": start_line,
                "end_line": end_line,
                "max_lines": int(max_lines),
            },
        )
        return {
            **lease,
            "path": normalized_path,
            "content": str(payload.get("content") or "(empty)"),
        }

    def write_file(
        self,
        *,
        thread_id: str | None,
        thread_key: str | None,
        sandbox_id: str | None,
        path: str,
        content: str,
        append: bool,
    ) -> dict[str, Any]:
        normalized_path = normalize_workspace_path(path)
        lease = self.acquire(
            thread_id=thread_id,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        payload = self._exec_json_action(
            pod_name=str(lease["pod_name"]),
            script=_WRITE_FILE_SCRIPT,
            payload={
                "path": normalized_path,
                "content": str(content or ""),
                "append": bool(append),
            },
        )
        return {
            **lease,
            "path": str(payload.get("path") or normalized_path),
        }

    def replace_file(
        self,
        *,
        thread_id: str | None,
        thread_key: str | None,
        sandbox_id: str | None,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool,
    ) -> dict[str, Any]:
        normalized_path = normalize_workspace_path(path)
        if not str(old_text or ""):
            raise ProvisionerError("old_text cannot be empty.")
        lease = self.acquire(
            thread_id=thread_id,
            thread_key=thread_key,
            sandbox_id=sandbox_id,
        )
        payload = self._exec_json_action(
            pod_name=str(lease["pod_name"]),
            script=_REPLACE_FILE_SCRIPT,
            payload={
                "path": normalized_path,
                "old_text": str(old_text or ""),
                "new_text": str(new_text or ""),
                "replace_all": bool(replace_all),
            },
        )
        replaced_raw = payload.get("replaced", 0)
        try:
            replaced = int(replaced_raw)
        except (TypeError, ValueError):
            replaced = 0
        return {
            **lease,
            "path": str(payload.get("path") or normalized_path),
            "replaced": max(0, replaced),
        }

    def cleanup_idle_pods(self) -> list[str]:
        payload = self._run_kubectl_json(
            args=[
                "-n",
                self.settings.namespace,
                "get",
                "pods",
                "-l",
                f"{_POD_LABEL_KEY}={_POD_LABEL_VALUE}",
                "-o",
                "json",
            ],
            timeout_seconds=20,
            allow_not_found=True,
        )
        if not payload:
            return []
        items = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return []
        now_ts = _now_ts()
        deleted: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") or {}
            if not isinstance(metadata, dict):
                continue
            pod_name = str(metadata.get("name") or "").strip()
            if not pod_name:
                continue
            annotations = metadata.get("annotations") or {}
            if not isinstance(annotations, dict):
                annotations = {}
            last_used_raw = annotations.get(_ANNOTATION_LAST_USED)
            try:
                last_used = int(last_used_raw) if last_used_raw is not None else 0
            except (TypeError, ValueError):
                last_used = 0
            if last_used <= 0:
                continue
            if (now_ts - last_used) <= int(self.settings.idle_timeout_seconds):
                continue
            self._delete_pod(pod_name=pod_name)
            deleted.append(pod_name)
        return deleted


settings = load_settings_from_env()
provisioner = KubectlSandboxProvisioner(settings)
app = FastAPI(
    title="OneSeek Sandbox Provisioner",
    version="0.1.0",
)
_cleanup_task: asyncio.Task[Any] | None = None


def _auth_guard(authorization: str | None = Header(default=None)) -> None:
    expected = str(settings.service_api_key or "").strip()
    if not expected:
        return
    provided = str(authorization or "").strip()
    if provided != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid provisioner API key.")


@app.on_event("startup")
async def _on_startup() -> None:
    global _cleanup_task
    interval = int(settings.cleanup_interval_seconds)
    if interval <= 0:
        _cleanup_task = None
        return

    async def _cleanup_loop() -> None:
        while True:
            try:
                await asyncio.to_thread(provisioner.cleanup_idle_pods)
            except Exception:
                # Best-effort cleanup loop
                pass
            await asyncio.sleep(float(interval))

    _cleanup_task = asyncio.create_task(_cleanup_loop())


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    global _cleanup_task
    if _cleanup_task is None:
        return
    _cleanup_task.cancel()
    try:
        await _cleanup_task
    except asyncio.CancelledError:
        pass
    _cleanup_task = None


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "sandbox-provisioner",
        "namespace": settings.namespace,
        "worker_image": settings.worker_image,
    }


@app.post("/v1/sandbox/acquire", dependencies=[Depends(_auth_guard)])
async def acquire_sandbox(request: AcquireRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            provisioner.acquire,
            thread_id=request.thread_id,
            thread_key=request.thread_key,
            sandbox_id=request.sandbox_id,
        )
    except ProvisionerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/sandbox/release", dependencies=[Depends(_auth_guard)])
async def release_sandbox(request: ReleaseRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            provisioner.release,
            thread_id=request.thread_id,
            thread_key=request.thread_key,
            sandbox_id=request.sandbox_id,
            reason=request.reason,
        )
    except ProvisionerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/sandbox/execute", dependencies=[Depends(_auth_guard)])
async def execute_sandbox_command(request: ExecuteRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            provisioner.execute,
            thread_id=request.thread_id,
            thread_key=request.thread_key,
            sandbox_id=request.sandbox_id,
            command=request.command,
            timeout_seconds=request.timeout_seconds,
            max_output_bytes=request.max_output_bytes,
        )
    except ProvisionerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/sandbox/ls", dependencies=[Depends(_auth_guard)])
async def sandbox_ls(request: ListRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            provisioner.list_files,
            thread_id=request.thread_id,
            thread_key=request.thread_key,
            sandbox_id=request.sandbox_id,
            path=request.path,
            max_depth=request.max_depth,
            max_entries=request.max_entries,
        )
    except ProvisionerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/sandbox/read_file", dependencies=[Depends(_auth_guard)])
async def sandbox_read_file(request: ReadFileRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            provisioner.read_file,
            thread_id=request.thread_id,
            thread_key=request.thread_key,
            sandbox_id=request.sandbox_id,
            path=request.path,
            start_line=request.start_line,
            end_line=request.end_line,
            max_lines=request.max_lines,
        )
    except ProvisionerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/sandbox/write_file", dependencies=[Depends(_auth_guard)])
async def sandbox_write_file(request: WriteFileRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            provisioner.write_file,
            thread_id=request.thread_id,
            thread_key=request.thread_key,
            sandbox_id=request.sandbox_id,
            path=request.path,
            content=request.content,
            append=request.append,
        )
    except ProvisionerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/sandbox/replace", dependencies=[Depends(_auth_guard)])
async def sandbox_replace(request: ReplaceRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            provisioner.replace_file,
            thread_id=request.thread_id,
            thread_key=request.thread_key,
            sandbox_id=request.sandbox_id,
            path=request.path,
            old_text=request.old_text,
            new_text=request.new_text,
            replace_all=request.replace_all,
        )
    except ProvisionerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/sandbox/cleanup_idle", dependencies=[Depends(_auth_guard)])
async def sandbox_cleanup_idle() -> dict[str, Any]:
    try:
        deleted = await asyncio.to_thread(provisioner.cleanup_idle_pods)
        return {
            "deleted": deleted,
            "count": len(deleted),
        }
    except ProvisionerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

