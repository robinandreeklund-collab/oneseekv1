from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any
from uuid import uuid4

from langchain_core.tools import tool
from langgraph_bigtool.tools import InjectedState

from app.agents.new_chat.sandbox_runtime import (
    SANDBOX_MODE_PROVISIONER,
    SandboxExecutionError,
    run_sandbox_command,
    sandbox_config_from_runtime_flags,
)


async def _trace_start(
    *,
    trace_recorder: Any | None,
    parent_span_id: str | None,
    name: str,
    kind: str,
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
            kind=kind,
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
    meta: dict[str, Any] | None = None,
) -> None:
    if trace_recorder is None or not span_id:
        return
    try:
        await trace_recorder.end_span(
            span_id=span_id,
            output_data=output_data,
            status=status,
            meta=meta or {},
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


def create_sandbox_execute_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
    trace_recorder: Any | None = None,
    trace_parent_span_id: str | None = None,
):
    @tool
    async def sandbox_execute(
        description: str,
        command: str,
        timeout_seconds: int | None = None,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Execute a shell command in an isolated sandbox workspace.

        Args:
            description: Briefly describe why this command is needed.
            command: The shell command to execute.
            timeout_seconds: Optional timeout override (seconds, capped).
        """
        _ = str(description or "").strip()
        scoped_runtime_hitl = _runtime_hitl_with_scope(
            runtime_hitl=runtime_hitl,
            state=state,
        )
        try:
            preview_config = sandbox_config_from_runtime_flags(scoped_runtime_hitl)
            acquire_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.acquire",
                kind="tool",
                input_data={
                    "thread_id": thread_id,
                    "mode": preview_config.mode,
                },
                meta={
                    "sandbox_enabled": bool(preview_config.enabled),
                    "mode": preview_config.mode,
                },
            )
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=acquire_span_id,
                output_data={
                    "thread_id": thread_id,
                    "mode": preview_config.mode,
                },
            )

            execute_span_id = await _trace_start(
                trace_recorder=trace_recorder,
                parent_span_id=trace_parent_span_id,
                name="sandbox.execute",
                kind="tool",
                input_data={
                    "thread_id": thread_id,
                    "command": str(command or ""),
                    "timeout_seconds": timeout_seconds,
                },
                meta={
                    "mode": preview_config.mode,
                },
            )
            result = await asyncio.to_thread(
                run_sandbox_command,
                command=str(command or ""),
                thread_id=thread_id,
                runtime_hitl=scoped_runtime_hitl,
                timeout_seconds=timeout_seconds,
            )
            payload = {
                "mode": result.mode,
                "workspace_path": result.workspace_path,
                "container_name": result.container_name,
                "sandbox_id": result.sandbox_id,
                "lease_id": result.lease_id,
                "reused": bool(result.reused),
                "state_backend": result.state_backend,
                "state_store": preview_config.state_store,
                "idle_timeout_seconds": int(preview_config.idle_timeout_seconds),
                "scope": result.scope,
                "scope_id": result.scope_id,
                "idle_releases": result.idle_releases or [],
                "output": result.output,
                "exit_code": result.exit_code,
                "truncated": bool(result.truncated),
                "sandbox_enabled": bool(preview_config.enabled),
            }
            if preview_config.mode == SANDBOX_MODE_PROVISIONER:
                payload["provisioner_url"] = str(preview_config.provisioner_url or "").strip()
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=execute_span_id,
                output_data={
                    "exit_code": result.exit_code,
                    "reused": bool(result.reused),
                    "state_backend": result.state_backend,
                    "lease_id": result.lease_id,
                },
                meta={
                    "mode": result.mode,
                    "sandbox_id": result.sandbox_id,
                    "container_name": result.container_name,
                },
            )
            if result.idle_releases:
                release_span_id = await _trace_start(
                    trace_recorder=trace_recorder,
                    parent_span_id=trace_parent_span_id,
                    name="sandbox.release",
                    kind="tool",
                    input_data={
                        "reason": "idle-timeout-cleanup",
                    },
                    meta={
                        "released_count": len(result.idle_releases),
                    },
                )
                await _trace_end(
                    trace_recorder=trace_recorder,
                    span_id=release_span_id,
                    output_data={
                        "released_threads": list(result.idle_releases),
                    },
                )
        except SandboxExecutionError as exc:
            preview_config = sandbox_config_from_runtime_flags(scoped_runtime_hitl)
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                "sandbox_enabled": bool(preview_config.enabled),
                "mode": preview_config.mode,
                "state_store": preview_config.state_store,
                "idle_timeout_seconds": int(preview_config.idle_timeout_seconds),
                "scope": preview_config.scope,
                "scope_id": preview_config.scope_id,
            }
            if preview_config.mode == SANDBOX_MODE_PROVISIONER:
                payload["provisioner_url"] = str(preview_config.provisioner_url or "").strip()
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        except Exception as exc:
            preview_config = sandbox_config_from_runtime_flags(scoped_runtime_hitl)
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "sandbox_enabled": bool(preview_config.enabled),
                "mode": preview_config.mode,
                "state_store": preview_config.state_store,
                "idle_timeout_seconds": int(preview_config.idle_timeout_seconds),
                "scope": preview_config.scope,
                "scope_id": preview_config.scope_id,
            }
            if preview_config.mode == SANDBOX_MODE_PROVISIONER:
                payload["provisioner_url"] = str(preview_config.provisioner_url or "").strip()
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=locals().get("execute_span_id"),
                output_data=payload,
                status="failed",
            )
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_execute
