from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any
from uuid import uuid4

from langchain_core.tools import tool

try:  # pragma: no cover - compatibility for isolated unit tests
    from langgraph_bigtool.tools import InjectedState
except Exception:  # pragma: no cover
    InjectedState = Any  # type: ignore[misc,assignment]

from app.agents.new_chat.sandbox_runtime import (
    SANDBOX_MODE_DOCKER,
    SANDBOX_MODE_PROVISIONER,
    SandboxExecutionError,
    build_sandbox_container_name,
    sandbox_list_directory,
    sandbox_config_from_runtime_flags,
    sandbox_read_text_file,
    sandbox_replace_text_file,
    sandbox_write_text_file,
)


async def _trace_start(
    *,
    trace_recorder: Any | None,
    parent_span_id: str | None,
    name: str,
    input_data: Any | None = None,
    meta: dict[str, Any] | None = None,
) -> str | None:
    if trace_recorder is None:
        return None
    span_id = f"{name.replace('.', '-')}-{uuid4().hex[:8]}"
    try:
        await trace_recorder.start_span(
            span_id=span_id,
            name=name,
            kind="tool",
            parent_id=parent_span_id,
            input_data=input_data,
            meta=meta or {},
        )
        return span_id
    except Exception:
        return None


async def _trace_end(
    *,
    trace_recorder: Any | None,
    span_id: str | None,
    output_data: Any | None = None,
    status: str = "completed",
) -> None:
    if trace_recorder is None or not span_id:
        return
    try:
        await trace_recorder.end_span(
            span_id=span_id,
            output_data=output_data,
            status=status,
        )
    except Exception:
        return


def _runtime_hitl_with_scope(
    *,
    runtime_hitl: dict[str, Any] | None,
    state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    merged = dict(runtime_hitl or {})
    injected = state if isinstance(state, dict) else {}
    scope_mode = str(
        injected.get("sandbox_scope_mode")
        or merged.get("sandbox_scope")
        or ""
    ).strip().lower()
    scope_id = str(
        injected.get("sandbox_scope_id")
        or injected.get("subagent_id")
        or merged.get("sandbox_scope_id")
        or ""
    ).strip()
    if scope_mode in {"thread", "subagent"}:
        merged["sandbox_scope"] = scope_mode
    elif scope_id:
        merged["sandbox_scope"] = "subagent"
    if scope_id:
        merged["sandbox_scope_id"] = scope_id
    return merged


def _sandbox_preview(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None,
) -> dict[str, Any]:
    config = sandbox_config_from_runtime_flags(runtime_hitl)
    preview: dict[str, Any] = {
        "sandbox_enabled": bool(config.enabled),
        "mode": config.mode,
        "state_store": config.state_store,
        "idle_timeout_seconds": int(config.idle_timeout_seconds),
        "scope": config.scope,
        "scope_id": config.scope_id,
    }
    if config.mode == SANDBOX_MODE_DOCKER:
        preview["container_name"] = build_sandbox_container_name(
            thread_id=thread_id,
            container_prefix=config.docker_container_prefix,
        )
    if config.mode == SANDBOX_MODE_PROVISIONER:
        preview["provisioner_url"] = str(config.provisioner_url or "").strip()
    return preview


def create_sandbox_ls_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
    trace_recorder: Any | None = None,
    trace_parent_span_id: str | None = None,
):
    @tool
    async def sandbox_ls(
        description: str,
        path: str = "/workspace",
        max_depth: int = 2,
        max_entries: int = 200,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """List files and directories inside the sandbox workspace.

        Args:
            description: Briefly describe why listing files is needed.
            path: Absolute sandbox path to list (defaults to /workspace).
            max_depth: Max recursive depth from the target directory.
            max_entries: Max number of entries to return.
        """
        _ = str(description or "").strip()
        scoped_runtime_hitl = _runtime_hitl_with_scope(
            runtime_hitl=runtime_hitl,
            state=state,
        )
        try:
            acquire_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.acquire",
                input_data={"thread_id": thread_id, "tool": "sandbox_ls"},
            )
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=acquire_span_id,
                output_data={"mode": _sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl).get("mode")},
            )
            execute_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.execute",
                input_data={"tool": "sandbox_ls", "path": path},
            )
            entries = await asyncio.to_thread(
                sandbox_list_directory,
                thread_id=thread_id,
                runtime_hitl=scoped_runtime_hitl,
                path=str(path or "/workspace"),
                max_depth=max_depth,
                max_entries=max_entries,
            )
            payload: dict[str, Any] = {
                "path": str(path or "/workspace"),
                "entries": entries,
                "count": len(entries),
                "max_depth": int(max_depth),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=execute_span_id,
                output_data={"count": len(entries)},
            )
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_ls


def create_sandbox_read_file_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
    trace_recorder: Any | None = None,
    trace_parent_span_id: str | None = None,
):
    @tool
    async def sandbox_read_file(
        description: str,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        max_lines: int = 400,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Read a UTF-8 text file from the sandbox workspace.

        Args:
            description: Briefly describe why file reading is needed.
            path: Absolute sandbox file path (for example /workspace/main.py).
            start_line: Optional 1-indexed start line.
            end_line: Optional inclusive end line.
            max_lines: Safety cap for returned lines.
        """
        _ = str(description or "").strip()
        scoped_runtime_hitl = _runtime_hitl_with_scope(
            runtime_hitl=runtime_hitl,
            state=state,
        )
        try:
            acquire_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.acquire",
                input_data={"thread_id": thread_id, "tool": "sandbox_read_file"},
            )
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=acquire_span_id,
                output_data={"mode": _sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl).get("mode")},
            )
            execute_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.execute",
                input_data={"tool": "sandbox_read_file", "path": path},
            )
            content = await asyncio.to_thread(
                sandbox_read_text_file,
                thread_id=thread_id,
                runtime_hitl=scoped_runtime_hitl,
                path=str(path or ""),
                start_line=start_line,
                end_line=end_line,
                max_lines=max_lines,
            )
            payload: dict[str, Any] = {
                "path": str(path or ""),
                "content": content,
                "line_count": 0 if content == "(empty)" else len(content.splitlines()),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=execute_span_id,
                output_data={"line_count": payload["line_count"]},
            )
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_read_file


def create_sandbox_write_file_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
    trace_recorder: Any | None = None,
    trace_parent_span_id: str | None = None,
):
    @tool
    async def sandbox_write_file(
        description: str,
        path: str,
        content: str,
        append: bool = False,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Write text content to a sandbox file.

        Args:
            description: Briefly describe why file writing is needed.
            path: Absolute sandbox file path (for example /workspace/main.py).
            content: Text content to write.
            append: Append instead of overwrite when true.
        """
        _ = str(description or "").strip()
        text = str(content or "")
        scoped_runtime_hitl = _runtime_hitl_with_scope(
            runtime_hitl=runtime_hitl,
            state=state,
        )
        try:
            acquire_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.acquire",
                input_data={"thread_id": thread_id, "tool": "sandbox_write_file"},
            )
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=acquire_span_id,
                output_data={"mode": _sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl).get("mode")},
            )
            execute_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.execute",
                input_data={"tool": "sandbox_write_file", "path": path, "append": bool(append)},
            )
            written_path = await asyncio.to_thread(
                sandbox_write_text_file,
                thread_id=thread_id,
                runtime_hitl=scoped_runtime_hitl,
                path=str(path or ""),
                content=text,
                append=bool(append),
            )
            payload: dict[str, Any] = {
                "path": written_path,
                "written_chars": len(text),
                "written_bytes": len(text.encode("utf-8")),
                "append": bool(append),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=execute_span_id,
                output_data={"written_bytes": payload["written_bytes"]},
            )
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_write_file


def create_sandbox_replace_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
    trace_recorder: Any | None = None,
    trace_parent_span_id: str | None = None,
):
    @tool
    async def sandbox_replace(
        description: str,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Replace text inside a sandbox file.

        Args:
            description: Briefly describe why replacing text is needed.
            path: Absolute sandbox file path.
            old_text: Text to find.
            new_text: Replacement text.
            replace_all: Replace all occurrences (otherwise exactly one is expected).
        """
        _ = str(description or "").strip()
        scoped_runtime_hitl = _runtime_hitl_with_scope(
            runtime_hitl=runtime_hitl,
            state=state,
        )
        try:
            acquire_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.acquire",
                input_data={"thread_id": thread_id, "tool": "sandbox_replace"},
            )
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=acquire_span_id,
                output_data={"mode": _sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl).get("mode")},
            )
            execute_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.execute",
                input_data={
                    "tool": "sandbox_replace",
                    "path": path,
                    "replace_all": bool(replace_all),
                },
            )
            updated_path, replaced = await asyncio.to_thread(
                sandbox_replace_text_file,
                thread_id=thread_id,
                runtime_hitl=scoped_runtime_hitl,
                path=str(path or ""),
                old_text=str(old_text or ""),
                new_text=str(new_text or ""),
                replace_all=bool(replace_all),
            )
            payload: dict[str, Any] = {
                "path": updated_path,
                "replaced": int(replaced),
                "replace_all": bool(replace_all),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=execute_span_id,
                output_data={"replaced": int(replaced)},
            )
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_replace


def create_list_directory_alias_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
    trace_recorder: Any | None = None,
    trace_parent_span_id: str | None = None,
):
    @tool
    async def list_directory(
        path: str = "/workspace",
        recursive: bool = False,
        max_entries: int = 200,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Compatibility alias for listing sandbox directories."""
        scoped_runtime_hitl = _runtime_hitl_with_scope(
            runtime_hitl=runtime_hitl,
            state=state,
        )
        depth = 6 if bool(recursive) else 2
        safe_max_entries = max(1, min(1000, int(max_entries)))
        try:
            acquire_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.acquire",
                input_data={"thread_id": thread_id, "tool": "list_directory"},
            )
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=acquire_span_id,
                output_data={
                    "mode": _sandbox_preview(
                        thread_id=thread_id,
                        runtime_hitl=scoped_runtime_hitl,
                    ).get("mode")
                },
            )
            execute_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.execute",
                input_data={
                    "tool": "list_directory",
                    "path": path,
                    "recursive": bool(recursive),
                },
            )
            entries = await asyncio.to_thread(
                sandbox_list_directory,
                thread_id=thread_id,
                runtime_hitl=scoped_runtime_hitl,
                path=str(path or "/workspace"),
                max_depth=depth,
                max_entries=safe_max_entries,
            )
            payload: dict[str, Any] = {
                "path": str(path or "/workspace"),
                "recursive": bool(recursive),
                "entries": entries,
                "count": len(entries),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=execute_span_id,
                output_data={"count": len(entries)},
            )
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=scoped_runtime_hitl),
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        return json.dumps(payload, ensure_ascii=True)

    return list_directory
