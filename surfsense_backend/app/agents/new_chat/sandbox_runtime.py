from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

SANDBOX_MODE_LOCAL = "local"
SANDBOX_MODE_DOCKER = "docker"
SANDBOX_MODE_PROVISIONER = "provisioner"
_DEFAULT_SANDBOX_MODE = SANDBOX_MODE_DOCKER
_ALLOWED_SANDBOX_MODES = {
    SANDBOX_MODE_LOCAL,
    SANDBOX_MODE_DOCKER,
    SANDBOX_MODE_PROVISIONER,
}

DEFAULT_SANDBOX_WORKSPACE_ROOT = "/tmp/oneseek-sandbox"
DEFAULT_SANDBOX_DOCKER_IMAGE = "python:3.12-slim"
DEFAULT_SANDBOX_CONTAINER_PREFIX = "oneseek-sandbox"
DEFAULT_SANDBOX_PROVISIONER_URL = "http://localhost:8002"
DEFAULT_SANDBOX_TIMEOUT_SECONDS = 30
DEFAULT_SANDBOX_MAX_OUTPUT_BYTES = 100_000
SANDBOX_VIRTUAL_WORKSPACE_PREFIX = "/workspace"

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
    provisioner_url: str = DEFAULT_SANDBOX_PROVISIONER_URL
    provisioner_api_key: str | None = None
    timeout_seconds: int = DEFAULT_SANDBOX_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_SANDBOX_MAX_OUTPUT_BYTES


def sandbox_config_from_runtime_flags(
    runtime_hitl: dict[str, Any] | None,
) -> SandboxRuntimeConfig:
    payload = dict(runtime_hitl or {})
    enabled = _coerce_bool(payload.get("sandbox_enabled"), default=False)
    requested_mode = str(payload.get("sandbox_mode") or _DEFAULT_SANDBOX_MODE).strip().lower()
    if requested_mode == "remote":
        requested_mode = SANDBOX_MODE_PROVISIONER
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
    provisioner_url = str(
        payload.get("sandbox_provisioner_url")
        or payload.get("sandbox_service_url")
        or DEFAULT_SANDBOX_PROVISIONER_URL
    ).strip() or DEFAULT_SANDBOX_PROVISIONER_URL
    provisioner_api_key = str(
        payload.get("sandbox_provisioner_api_key")
        or payload.get("sandbox_service_api_key")
        or ""
    ).strip() or None
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
        provisioner_url=provisioner_url,
        provisioner_api_key=provisioner_api_key,
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


def _provisioner_headers(config: SandboxRuntimeConfig) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    api_key = str(config.provisioner_api_key or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _post_to_provisioner(
    *,
    config: SandboxRuntimeConfig,
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    normalized_endpoint = str(endpoint or "").strip()
    if not normalized_endpoint.startswith("/"):
        normalized_endpoint = f"/{normalized_endpoint}"
    base_url = str(config.provisioner_url or "").strip().rstrip("/")
    if not base_url:
        raise SandboxExecutionError("sandbox_provisioner_url is required in provisioner mode.")
    url = f"{base_url}{normalized_endpoint}"
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib_request.Request(
        url=url,
        data=body,
        method="POST",
        headers=_provisioner_headers(config),
    )
    try:
        with urllib_request.urlopen(request, timeout=float(max(1, int(timeout_seconds)))) as response:
            raw_response = response.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as exc:
        details = ""
        if exc.fp is not None:
            try:
                details = str(exc.fp.read().decode("utf-8", errors="replace")).strip()
            except Exception:
                details = ""
        message = details or str(exc.reason or exc)
        raise SandboxExecutionError(
            f"Provisioner request failed ({exc.code}) for {normalized_endpoint}: {message}"
        ) from exc
    except urllib_error.URLError as exc:
        raise SandboxExecutionError(
            f"Provisioner request failed for {normalized_endpoint}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise SandboxExecutionError(
            f"Provisioner request timed out for {normalized_endpoint}."
        ) from exc
    except Exception as exc:
        raise SandboxExecutionError(
            f"Provisioner request failed for {normalized_endpoint}: {exc}"
        ) from exc

    if not raw_response.strip():
        return {}
    try:
        decoded = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise SandboxExecutionError(
            f"Provisioner returned invalid JSON for {normalized_endpoint}."
        ) from exc
    if not isinstance(decoded, dict):
        raise SandboxExecutionError(
            f"Provisioner response must be an object for {normalized_endpoint}."
        )
    return decoded


def _ensure_sandbox_enabled(config: SandboxRuntimeConfig) -> None:
    if not config.enabled:
        raise SandboxExecutionError(
            "Sandbox execution is disabled. Enable runtime_hitl.sandbox_enabled."
        )


def _coerce_remote_path(path: str) -> str:
    normalized_path = _coerce_path(path)
    if normalized_path == SANDBOX_VIRTUAL_WORKSPACE_PREFIX:
        return normalized_path
    if normalized_path.startswith(f"{SANDBOX_VIRTUAL_WORKSPACE_PREFIX}/"):
        relative = normalized_path[len(SANDBOX_VIRTUAL_WORKSPACE_PREFIX) :].lstrip("/")
    else:
        relative = normalized_path.lstrip("/")
    relative_path = Path(relative)
    if any(part in {"..", ""} for part in relative_path.parts):
        raise SandboxExecutionError(f"Path traversal is not allowed: {normalized_path}")
    if not relative:
        return SANDBOX_VIRTUAL_WORKSPACE_PREFIX
    return f"{SANDBOX_VIRTUAL_WORKSPACE_PREFIX}/{relative_path.as_posix()}"


def _coerce_remote_list(raw_entries: Any) -> list[str]:
    if not isinstance(raw_entries, list):
        return []
    entries: list[str] = []
    for value in raw_entries:
        text = str(value or "").strip()
        if text:
            entries.append(text)
    return entries


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


def _coerce_path(path: str) -> str:
    normalized_path = str(path or "").strip()
    if not normalized_path:
        raise SandboxExecutionError("Path cannot be empty.")
    if not normalized_path.startswith("/"):
        raise SandboxExecutionError("Path must be absolute and start with '/'.")
    return normalized_path


def _resolve_workspace_file_path(
    *,
    workspace_path: Path,
    path: str,
) -> tuple[Path, str]:
    normalized_path = _coerce_path(path)
    if normalized_path == SANDBOX_VIRTUAL_WORKSPACE_PREFIX:
        relative = ""
    elif normalized_path.startswith(f"{SANDBOX_VIRTUAL_WORKSPACE_PREFIX}/"):
        relative = normalized_path[len(SANDBOX_VIRTUAL_WORKSPACE_PREFIX) :].lstrip("/")
    else:
        # Treat other absolute paths as virtual paths under /workspace.
        relative = normalized_path.lstrip("/")

    relative_path = Path(relative)
    if any(part in {"..", ""} for part in relative_path.parts):
        raise SandboxExecutionError(f"Path traversal is not allowed: {normalized_path}")

    candidate = (workspace_path / relative_path).resolve()
    try:
        candidate.relative_to(workspace_path)
    except ValueError as exc:
        raise SandboxExecutionError(
            f"Path escapes sandbox workspace: {normalized_path}"
        ) from exc

    if relative:
        display_path = f"{SANDBOX_VIRTUAL_WORKSPACE_PREFIX}/{relative_path.as_posix()}"
    else:
        display_path = SANDBOX_VIRTUAL_WORKSPACE_PREFIX
    return candidate, display_path


def _prepare_workspace_and_path(
    *,
    thread_id: Any,
    runtime_hitl: dict[str, Any] | None,
    path: str,
) -> tuple[SandboxRuntimeConfig, Path, Path, str]:
    config = sandbox_config_from_runtime_flags(runtime_hitl)
    _ensure_sandbox_enabled(config)
    workspace_path = _workspace_path(config, thread_id)
    host_path, display_path = _resolve_workspace_file_path(
        workspace_path=workspace_path,
        path=path,
    )
    return config, workspace_path, host_path, display_path


def sandbox_list_directory(
    *,
    thread_id: Any,
    runtime_hitl: dict[str, Any] | None,
    path: str = SANDBOX_VIRTUAL_WORKSPACE_PREFIX,
    max_depth: int = 2,
    max_entries: int = 500,
) -> list[str]:
    config = sandbox_config_from_runtime_flags(runtime_hitl)
    _ensure_sandbox_enabled(config)
    normalized_path = _coerce_remote_path(path)
    safe_depth = max(0, min(int(max_depth), 6))
    safe_max_entries = max(1, min(int(max_entries), 5000))
    if config.mode == SANDBOX_MODE_PROVISIONER:
        response = _post_to_provisioner(
            config=config,
            endpoint="/v1/sandbox/ls",
            payload={
                "thread_id": str(thread_id or ""),
                "path": normalized_path,
                "max_depth": safe_depth,
                "max_entries": safe_max_entries,
            },
            timeout_seconds=max(5, min(120, int(config.timeout_seconds))),
        )
        return _coerce_remote_list(response.get("entries"))

    _config, workspace_path, host_path, _display_path = _prepare_workspace_and_path(
        thread_id=thread_id,
        runtime_hitl=runtime_hitl,
        path=normalized_path,
    )
    if not host_path.exists():
        raise SandboxExecutionError(f"Directory not found: {normalized_path}")
    if not host_path.is_dir():
        raise SandboxExecutionError(f"Path is not a directory: {normalized_path}")

    root_depth = len(host_path.parts)
    entries: list[str] = []
    for current_root, dirs, files in os.walk(host_path):
        current = Path(current_root)
        depth = len(current.parts) - root_depth
        if depth > safe_depth:
            dirs[:] = []
            continue
        dirs.sort()
        files.sort()
        try:
            relative_root = current.resolve().relative_to(workspace_path)
        except ValueError:
            continue
        if str(relative_root) == ".":
            display_root = SANDBOX_VIRTUAL_WORKSPACE_PREFIX
        else:
            display_root = f"{SANDBOX_VIRTUAL_WORKSPACE_PREFIX}/{relative_root.as_posix()}"
        for directory in dirs:
            entries.append(f"{display_root}/{directory}/")
            if len(entries) >= safe_max_entries:
                return entries
        for file_name in files:
            entries.append(f"{display_root}/{file_name}")
            if len(entries) >= safe_max_entries:
                return entries
        if depth >= safe_depth:
            dirs[:] = []
    return entries


def sandbox_read_text_file(
    *,
    thread_id: Any,
    runtime_hitl: dict[str, Any] | None,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    max_lines: int = 400,
) -> str:
    config = sandbox_config_from_runtime_flags(runtime_hitl)
    _ensure_sandbox_enabled(config)
    normalized_path = _coerce_remote_path(path)
    safe_max_lines = max(1, min(int(max_lines), 4000))
    safe_start = None if start_line is None else max(1, int(start_line))
    safe_end = None if end_line is None else int(end_line)
    if safe_end is not None and safe_start is not None and safe_end < safe_start:
        raise SandboxExecutionError("end_line cannot be less than start_line.")
    if config.mode == SANDBOX_MODE_PROVISIONER:
        response = _post_to_provisioner(
            config=config,
            endpoint="/v1/sandbox/read_file",
            payload={
                "thread_id": str(thread_id or ""),
                "path": normalized_path,
                "start_line": safe_start,
                "end_line": safe_end,
                "max_lines": safe_max_lines,
            },
            timeout_seconds=max(5, min(120, int(config.timeout_seconds))),
        )
        return str(response.get("content") or "(empty)")

    _config, _workspace_path, host_path, _display_path = _prepare_workspace_and_path(
        thread_id=thread_id,
        runtime_hitl=runtime_hitl,
        path=normalized_path,
    )
    if not host_path.exists():
        raise SandboxExecutionError(f"File not found: {normalized_path}")
    if not host_path.is_file():
        raise SandboxExecutionError(f"Path is not a file: {normalized_path}")

    try:
        with host_path.open("r", encoding="utf-8") as file_handle:
            lines = file_handle.readlines()
    except UnicodeDecodeError as exc:
        raise SandboxExecutionError(f"Failed to decode file as UTF-8: {normalized_path}") from exc

    if not lines:
        return "(empty)"

    line_count = len(lines)
    safe_start = 1 if safe_start is None else int(safe_start)
    if safe_start > line_count:
        raise SandboxExecutionError(
            f"start_line {safe_start} exceeds file length ({line_count})."
        )
    if safe_end is None:
        safe_end = min(line_count, safe_start + safe_max_lines - 1)
    else:
        safe_end = min(line_count, int(safe_end))
        if safe_end < safe_start:
            raise SandboxExecutionError("end_line cannot be less than start_line.")
        if (safe_end - safe_start + 1) > safe_max_lines:
            safe_end = safe_start + safe_max_lines - 1

    selected = lines[safe_start - 1 : safe_end]
    formatted: list[str] = []
    for index, line in enumerate(selected, start=safe_start):
        formatted.append(f"{index}|{line.rstrip()}")
    return "\n".join(formatted)


def sandbox_write_text_file(
    *,
    thread_id: Any,
    runtime_hitl: dict[str, Any] | None,
    path: str,
    content: str,
    append: bool = False,
) -> str:
    config = sandbox_config_from_runtime_flags(runtime_hitl)
    _ensure_sandbox_enabled(config)
    normalized_path = _coerce_remote_path(path)
    text = str(content or "")
    if config.mode == SANDBOX_MODE_PROVISIONER:
        response = _post_to_provisioner(
            config=config,
            endpoint="/v1/sandbox/write_file",
            payload={
                "thread_id": str(thread_id or ""),
                "path": normalized_path,
                "content": text,
                "append": bool(append),
            },
            timeout_seconds=max(5, min(120, int(config.timeout_seconds))),
        )
        response_path = str(response.get("path") or "").strip()
        return response_path or normalized_path

    _config, _workspace_path, host_path, display_path = _prepare_workspace_and_path(
        thread_id=thread_id,
        runtime_hitl=runtime_hitl,
        path=normalized_path,
    )
    host_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with host_path.open(mode, encoding="utf-8") as file_handle:
        file_handle.write(text)
    return display_path


def sandbox_replace_text_file(
    *,
    thread_id: Any,
    runtime_hitl: dict[str, Any] | None,
    path: str,
    old_text: str,
    new_text: str,
    replace_all: bool = False,
) -> tuple[str, int]:
    config = sandbox_config_from_runtime_flags(runtime_hitl)
    _ensure_sandbox_enabled(config)
    normalized_path = _coerce_remote_path(path)
    old_value = str(old_text or "")
    if not old_value:
        raise SandboxExecutionError("old_text cannot be empty.")
    new_value = str(new_text or "")
    if config.mode == SANDBOX_MODE_PROVISIONER:
        response = _post_to_provisioner(
            config=config,
            endpoint="/v1/sandbox/replace",
            payload={
                "thread_id": str(thread_id or ""),
                "path": normalized_path,
                "old_text": old_value,
                "new_text": new_value,
                "replace_all": bool(replace_all),
            },
            timeout_seconds=max(5, min(120, int(config.timeout_seconds))),
        )
        replaced_raw = response.get("replaced", 0)
        try:
            replaced_count = int(replaced_raw)
        except (TypeError, ValueError):
            replaced_count = 0
        response_path = str(response.get("path") or "").strip() or normalized_path
        return response_path, max(0, replaced_count)

    _config, _workspace_path, host_path, display_path = _prepare_workspace_and_path(
        thread_id=thread_id,
        runtime_hitl=runtime_hitl,
        path=normalized_path,
    )
    if not host_path.exists():
        raise SandboxExecutionError(f"File not found: {normalized_path}")
    if not host_path.is_file():
        raise SandboxExecutionError(f"Path is not a file: {normalized_path}")

    with host_path.open("r", encoding="utf-8") as file_handle:
        original_content = file_handle.read()

    occurrences = original_content.count(old_value)
    if occurrences <= 0:
        raise SandboxExecutionError("old_text not found in file.")
    if not replace_all and occurrences != 1:
        raise SandboxExecutionError(
            "old_text appears multiple times; set replace_all=true to replace all."
        )

    updated_content = (
        original_content.replace(old_value, new_value)
        if replace_all
        else original_content.replace(old_value, new_value, 1)
    )
    with host_path.open("w", encoding="utf-8") as file_handle:
        file_handle.write(updated_content)
    replaced = occurrences if replace_all else 1
    return display_path, replaced


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
    if config.mode == SANDBOX_MODE_PROVISIONER:
        response = _post_to_provisioner(
            config=config,
            endpoint="/v1/sandbox/execute",
            payload={
                "thread_id": str(thread_id or ""),
                "command": normalized_command,
                "timeout_seconds": int(effective_timeout),
                "max_output_bytes": int(config.max_output_bytes),
            },
            timeout_seconds=max(5, min(600, int(effective_timeout) + 5)),
        )
        output = str(response.get("output") or "<no output>")
        try:
            exit_code = int(response.get("exit_code", 1))
        except (TypeError, ValueError):
            exit_code = 1
        container_name_raw = str(response.get("container_name") or "").strip()
        workspace_path = str(
            response.get("workspace_path") or SANDBOX_VIRTUAL_WORKSPACE_PREFIX
        ).strip() or SANDBOX_VIRTUAL_WORKSPACE_PREFIX
        return SandboxCommandResult(
            mode=SANDBOX_MODE_PROVISIONER,
            workspace_path=workspace_path,
            output=output,
            exit_code=exit_code,
            truncated=bool(response.get("truncated", False)),
            container_name=container_name_raw or None,
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
