from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.tools import tool

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


def _sandbox_preview(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None,
) -> dict[str, Any]:
    config = sandbox_config_from_runtime_flags(runtime_hitl)
    preview: dict[str, Any] = {
        "sandbox_enabled": bool(config.enabled),
        "mode": config.mode,
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
):
    @tool
    async def sandbox_ls(
        description: str,
        path: str = "/workspace",
        max_depth: int = 2,
        max_entries: int = 200,
    ) -> str:
        """List files and directories inside the sandbox workspace.

        Args:
            description: Briefly describe why listing files is needed.
            path: Absolute sandbox path to list (defaults to /workspace).
            max_depth: Max recursive depth from the target directory.
            max_entries: Max number of entries to return.
        """
        _ = str(description or "").strip()
        try:
            entries = await asyncio.to_thread(
                sandbox_list_directory,
                thread_id=thread_id,
                runtime_hitl=runtime_hitl,
                path=str(path or "/workspace"),
                max_depth=max_depth,
                max_entries=max_entries,
            )
            payload: dict[str, Any] = {
                "path": str(path or "/workspace"),
                "entries": entries,
                "count": len(entries),
                "max_depth": int(max_depth),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_ls


def create_sandbox_read_file_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
):
    @tool
    async def sandbox_read_file(
        description: str,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        max_lines: int = 400,
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
        try:
            content = await asyncio.to_thread(
                sandbox_read_text_file,
                thread_id=thread_id,
                runtime_hitl=runtime_hitl,
                path=str(path or ""),
                start_line=start_line,
                end_line=end_line,
                max_lines=max_lines,
            )
            payload: dict[str, Any] = {
                "path": str(path or ""),
                "content": content,
                "line_count": 0 if content == "(empty)" else len(content.splitlines()),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_read_file


def create_sandbox_write_file_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
):
    @tool
    async def sandbox_write_file(
        description: str,
        path: str,
        content: str,
        append: bool = False,
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
        try:
            written_path = await asyncio.to_thread(
                sandbox_write_text_file,
                thread_id=thread_id,
                runtime_hitl=runtime_hitl,
                path=str(path or ""),
                content=text,
                append=bool(append),
            )
            payload: dict[str, Any] = {
                "path": written_path,
                "written_chars": len(text),
                "written_bytes": len(text.encode("utf-8")),
                "append": bool(append),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_write_file


def create_sandbox_replace_tool(
    *,
    thread_id: int | None,
    runtime_hitl: dict[str, Any] | None = None,
):
    @tool
    async def sandbox_replace(
        description: str,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
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
        try:
            updated_path, replaced = await asyncio.to_thread(
                sandbox_replace_text_file,
                thread_id=thread_id,
                runtime_hitl=runtime_hitl,
                path=str(path or ""),
                old_text=str(old_text or ""),
                new_text=str(new_text or ""),
                replace_all=bool(replace_all),
            )
            payload: dict[str, Any] = {
                "path": updated_path,
                "replaced": int(replaced),
                "replace_all": bool(replace_all),
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        except SandboxExecutionError as exc:
            payload = {
                "error": str(exc),
                "error_type": "SandboxExecutionError",
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        except Exception as exc:
            payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                **_sandbox_preview(thread_id=thread_id, runtime_hitl=runtime_hitl),
            }
        return json.dumps(payload, ensure_ascii=True)

    return sandbox_replace
