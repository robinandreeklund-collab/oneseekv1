from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.tools import tool

from app.agents.new_chat.sandbox_runtime import (
    SandboxExecutionError,
    run_sandbox_command,
)


def create_sandbox_execute_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
):
    @tool
    async def sandbox_execute(
        description: str,
        command: str,
        timeout_seconds: int | None = None,
    ) -> str:
        """Execute a shell command in an isolated sandbox workspace.

        Args:
            description: Briefly describe why this command is needed.
            command: The shell command to execute.
            timeout_seconds: Optional timeout override (seconds, capped).
        """
        _ = str(description or "").strip()
        try:
            result = await asyncio.to_thread(
                run_sandbox_command,
                command=str(command or ""),
                thread_id=thread_id,
                runtime_hitl=runtime_hitl,
                timeout_seconds=timeout_seconds,
            )
            payload = {
                "mode": result.mode,
                "workspace_path": result.workspace_path,
                "container_name": result.container_name,
                "output": result.output,
                "exit_code": result.exit_code,
                "truncated": bool(result.truncated),
            }
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
            }
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_execute
