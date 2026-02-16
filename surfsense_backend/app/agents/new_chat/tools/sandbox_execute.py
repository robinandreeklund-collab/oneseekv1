from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.tools import tool

from app.agents.new_chat.sandbox_runtime import (
    SANDBOX_MODE_PROVISIONER,
    SandboxExecutionError,
    run_sandbox_command,
    sandbox_config_from_runtime_flags,
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
            preview_config = sandbox_config_from_runtime_flags(runtime_hitl)
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
                "sandbox_enabled": bool(preview_config.enabled),
            }
            if preview_config.mode == SANDBOX_MODE_PROVISIONER:
                payload["provisioner_url"] = str(preview_config.provisioner_url or "").strip()
        except SandboxExecutionError as exc:
            preview_config = sandbox_config_from_runtime_flags(runtime_hitl)
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                "sandbox_enabled": bool(preview_config.enabled),
                "mode": preview_config.mode,
            }
            if preview_config.mode == SANDBOX_MODE_PROVISIONER:
                payload["provisioner_url"] = str(preview_config.provisioner_url or "").strip()
        except Exception as exc:
            preview_config = sandbox_config_from_runtime_flags(runtime_hitl)
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "sandbox_enabled": bool(preview_config.enabled),
                "mode": preview_config.mode,
            }
            if preview_config.mode == SANDBOX_MODE_PROVISIONER:
                payload["provisioner_url"] = str(preview_config.provisioner_url or "").strip()
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_execute
