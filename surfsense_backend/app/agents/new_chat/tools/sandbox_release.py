from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from langchain_core.tools import tool

from app.agents.new_chat.sandbox_runtime import (
    SANDBOX_MODE_PROVISIONER,
    release_sandbox_lease,
    sandbox_config_from_runtime_flags,
)


async def _trace_start(
    *,
    trace_recorder: Any | None,
    parent_span_id: str | None,
    input_data: Any | None = None,
) -> str | None:
    if trace_recorder is None:
        return None
    span_id = f"sandbox-release-{uuid4().hex[:8]}"
    try:
        await trace_recorder.start_span(
            span_id=span_id,
            name="sandbox.release",
            kind="tool",
            parent_id=parent_span_id,
            input_data=input_data,
            meta={},
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


def create_sandbox_release_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
    trace_recorder: Any | None = None,
    trace_parent_span_id: str | None = None,
):
    @tool
    async def sandbox_release(
        description: str,
        reason: str = "manual-release",
    ) -> str:
        """Release and cleanup the sandbox lease for the current thread."""
        _ = str(description or "").strip()
        span_id = await _trace_start(
            trace_recorder=trace_recorder,
            parent_span_id=trace_parent_span_id,
            input_data={
                "thread_id": thread_id,
                "reason": str(reason or "manual-release"),
            },
        )
        try:
            config = sandbox_config_from_runtime_flags(runtime_hitl)
            released = await asyncio.to_thread(
                release_sandbox_lease,
                thread_id=thread_id,
                runtime_hitl=runtime_hitl,
                reason=str(reason or "manual-release"),
            )
            payload: dict[str, Any] = {
                "released": bool(released),
                "thread_id": thread_id,
                "mode": config.mode,
                "sandbox_enabled": bool(config.enabled),
            }
            if config.mode == SANDBOX_MODE_PROVISIONER:
                payload["provisioner_url"] = str(config.provisioner_url or "").strip()
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=span_id,
                output_data=payload,
            )
        except Exception as exc:
            payload = {
                "released": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
            await _trace_end(
                trace_recorder=trace_recorder,
                span_id=span_id,
                output_data=payload,
                status="failed",
            )
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_release
