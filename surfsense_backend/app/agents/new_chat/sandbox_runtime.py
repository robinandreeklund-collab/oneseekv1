from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import subprocess
import threading
from typing import Any

SANDBOX_MODE_LOCAL = "local"
SANDBOX_MODE_DOCKER = "docker"
_DEFAULT_SANDBOX_MODE = SANDBOX_MODE_DOCKER
_ALLOWED_SANDBOX_MODES = {SANDBOX_MODE_LOCAL, SANDBOX_MODE_DOCKER}

DEFAULT_SANDBOX_WORKSPACE_ROOT = "/tmp/oneseek-sandbox"
DEFAULT_SANDBOX_DOCKER_IMAGE = "python:3.12-slim"
DEFAULT_SANDBOX_CONTAINER_PREFIX = "oneseek-sandbox"
DEFAULT_SANDBOX_TIMEOUT_SECONDS = 30
DEFAULT_SANDBOX_MAX_OUTPUT_BYTES = 100_000

_LONG_LIVED_PATTERNS = (
    re.compile(r"\bnpm\s+run\s+(dev|start)\b", re.IGNORECASE),
    re.compile(r"\bpnpm\s+run\s+(dev|start)\b", re.IGNORECASE),
    re.compile(r"\byarn\s+(dev|start)\b", re.IGNORECASE),
    re.compile(r"\btail\s+-f\b", re.IGNORECASE),
    re.compile(r"\bwatch\b", re.IGNORECASE),
)


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def _coerce_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _sanitize_segment(value: Any, *, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "")).strip("-")
    if not normalized:
        return fallback
    return normalized


def _safe_shell_output(*, stdout: str, stderr: str) -> str:
    parts: list[str] = []
    cleaned_stdout = str(stdout or "").strip()
    if cleaned_stdout:
        parts.append(cleaned_stdout)
    cleaned_stderr = str(stderr or "").strip()
    if cleaned_stderr:
        for line in cleaned_stderr.splitlines():
            line = str(line or "").strip()
            if not line:
                continue
            parts.append(f"[stderr] {line}")
    if not parts:
        return "<no output>"
    return "\n".join(parts)


def command_looks_long_lived(command: str) -> bool:
    normalized = str(command or "").strip()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _LONG_LIVED_PATTERNS)


def build_sandbox_container_name(
    *,
    thread_id: Any,
    container_prefix: str = DEFAULT_SANDBOX_CONTAINER_PREFIX,
) -> str:
    safe_prefix = _sanitize_segment(container_prefix, fallback="oneseek-sandbox").lower()
    seed = str(thread_id or "thread-default").strip() or "thread-default"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    combined = f"{safe_prefix}-{digest}".lower()
    return combined[:63]


@dataclass(frozen=True)
class SandboxRuntimeConfig:
    enabled: bool = False
    mode: str = _DEFAULT_SANDBOX_MODE
    workspace_root: str = DEFAULT_SANDBOX_WORKSPACE_ROOT
    docker_image: str = DEFAULT_SANDBOX_DOCKER_IMAGE
    docker_container_prefix: str = DEFAULT_SANDBOX_CONTAINER_PREFIX
    timeout_seconds: int = DEFAULT_SANDBOX_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_SANDBOX_MAX_OUTPUT_BYTES


def sandbox_config_from_runtime_flags(
    runtime_hitl: dict[str, Any] | None,
) -> SandboxRuntimeConfig:
    payload = dict(runtime_hitl or {})
    enabled = _coerce_bool(payload.get("sandbox_enabled"), default=False)
    requested_mode = str(payload.get("sandbox_mode") or _DEFAULT_SANDBOX_MODE).strip().lower()
    mode = requested_mode if requested_mode in _ALLOWED_SANDBOX_MODES else _DEFAULT_SANDBOX_MODE
    workspace_root = str(
        payload.get("sandbox_workspace_root") or DEFAULT_SANDBOX_WORKSPACE_ROOT
    ).strip() or DEFAULT_SANDBOX_WORKSPACE_ROOT
    docker_image = str(
        payload.get("sandbox_docker_image") or DEFAULT_SANDBOX_DOCKER_IMAGE
    ).strip() or DEFAULT_SANDBOX_DOCKER_IMAGE
    docker_container_prefix = str(
        payload.get("sandbox_container_prefix") or DEFAULT_SANDBOX_CONTAINER_PREFIX
    ).strip() or DEFAULT_SANDBOX_CONTAINER_PREFIX
    timeout_seconds = _coerce_int(
        payload.get("sandbox_timeout_seconds"),
        default=DEFAULT_SANDBOX_TIMEOUT_SECONDS,
        min_value=3,
        max_value=600,
    )
    max_output_bytes = _coerce_int(
        payload.get("sandbox_max_output_bytes"),
        default=DEFAULT_SANDBOX_MAX_OUTPUT_BYTES,
        min_value=1024,
        max_value=1_000_000,
    )
    return SandboxRuntimeConfig(
        enabled=enabled,
        mode=mode,
        workspace_root=workspace_root,
        docker_image=docker_image,
        docker_container_prefix=docker_container_prefix,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
    )


@dataclass
class SandboxCommandResult:
    mode: str
    workspace_path: str
    output: str
    exit_code: int
    truncated: bool = False
    container_name: str | None = None


class SandboxExecutionError(RuntimeError):
    pass


class _DockerSandboxPool:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def _is_running(self, container_name: str) -> bool:
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and result.stdout.strip().lower() == "true"

    def _start(
        self,
        *,
        container_name: str,
        workspace_path: Path,
        docker_image: str,
    ) -> None:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                container_name,
                "-w",
                "/workspace",
                "-v",
                f"{workspace_path}:/workspace",
                docker_image,
                "sh",
                "-c",
                "while true; do sleep 3600; done",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            output = _safe_shell_output(stdout=result.stdout, stderr=result.stderr)
            raise SandboxExecutionError(
                f"Failed to start docker sandbox '{container_name}': {output}"
            )

    def ensure(
        self,
        *,
        container_name: str,
        workspace_path: Path,
        docker_image: str,
    ) -> None:
        with self._lock:
            if self._is_running(container_name):
                return
            self._start(
                container_name=container_name,
                workspace_path=workspace_path,
                docker_image=docker_image,
            )


_DOCKER_POOL = _DockerSandboxPool()


def _run_subprocess(
    *,
    command: list[str],
    timeout_seconds: int,
    max_output_bytes: int,
    cwd: Path | None = None,
) -> tuple[str, int, bool]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=float(timeout_seconds),
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired:
        return (
            f"Error: command timed out after {int(timeout_seconds)}s.",
            124,
            False,
        )
    except FileNotFoundError as exc:
        return (
            f"Error: sandbox runtime binary not found ({exc}).",
            127,
            False,
        )
    output = _safe_shell_output(stdout=result.stdout, stderr=result.stderr)
    truncated = False
    if len(output) > max_output_bytes:
        output = output[:max_output_bytes] + "\n\n[Output truncated due to size limits.]"
        truncated = True
    return output, int(result.returncode), truncated


def _workspace_path(config: SandboxRuntimeConfig, thread_id: Any) -> Path:
    root = Path(str(config.workspace_root or DEFAULT_SANDBOX_WORKSPACE_ROOT)).expanduser()
    thread_segment = _sanitize_segment(thread_id, fallback="thread-default")
    path = (root / thread_segment).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_sandbox_command(
    *,
    command: str,
    thread_id: Any,
    runtime_hitl: dict[str, Any] | None,
    timeout_seconds: int | None = None,
) -> SandboxCommandResult:
    config = sandbox_config_from_runtime_flags(runtime_hitl)
    if not config.enabled:
        raise SandboxExecutionError(
            "Sandbox execution is disabled. Enable runtime_hitl.sandbox_enabled to use sandbox_execute."
        )

    normalized_command = str(command or "").strip()
    if not normalized_command:
        raise SandboxExecutionError("Command cannot be empty.")
    if command_looks_long_lived(normalized_command):
        raise SandboxExecutionError(
            "Refusing long-lived command in sandbox (dev/watch/tail). Use short-lived commands only."
        )

    effective_timeout = (
        _coerce_int(timeout_seconds, default=config.timeout_seconds, min_value=3, max_value=600)
        if timeout_seconds is not None
        else int(config.timeout_seconds)
    )
    workspace_path = _workspace_path(config, thread_id)
    max_output_bytes = int(config.max_output_bytes)

    if config.mode == SANDBOX_MODE_DOCKER:
        container_name = build_sandbox_container_name(
            thread_id=thread_id,
            container_prefix=config.docker_container_prefix,
        )
        _DOCKER_POOL.ensure(
            container_name=container_name,
            workspace_path=workspace_path,
            docker_image=config.docker_image,
        )
        output, exit_code, truncated = _run_subprocess(
            command=["docker", "exec", container_name, "sh", "-lc", normalized_command],
            timeout_seconds=effective_timeout,
            max_output_bytes=max_output_bytes,
        )
        return SandboxCommandResult(
            mode=SANDBOX_MODE_DOCKER,
            workspace_path=str(workspace_path),
            output=output,
            exit_code=exit_code,
            truncated=truncated,
            container_name=container_name,
        )

    output, exit_code, truncated = _run_subprocess(
        command=["bash", "-lc", normalized_command],
        timeout_seconds=effective_timeout,
        max_output_bytes=max_output_bytes,
        cwd=workspace_path,
    )
    return SandboxCommandResult(
        mode=SANDBOX_MODE_LOCAL,
        workspace_path=str(workspace_path),
        output=output,
        exit_code=exit_code,
        truncated=truncated,
        container_name=None,
    )
