"""Memory selection, artifact handling, and cross-session memory for supervisor agent."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Callable

from app.agents.new_chat.bigtool_store import _normalize_text, _tokenize
from app.agents.new_chat.sandbox_runtime import sandbox_write_text_file
from app.agents.new_chat.supervisor_constants import (
    _AGENT_STOPWORDS,
    _ARTIFACT_DEFAULT_STORAGE_MODE,
    _ARTIFACT_LOCAL_ROOT,
)
from app.agents.new_chat.supervisor_text_utils import (
    _safe_id_segment,
    _serialize_artifact_payload,
    _truncate_for_prompt,
)

logger = logging.getLogger(__name__)

# Type alias for sandbox read callback.
# Signature: (path: str) -> str
# Should be created by the supervisor closure binding thread_id and runtime_hitl.
SandboxReadFn = Callable[[str], str]

# Limits for artifact content injection into downstream nodes.
_ARTIFACT_READ_MAX_ITEMS = 3
_ARTIFACT_READ_MAX_CHARS_PER_ITEM = 4000
_ARTIFACT_READ_MAX_TOTAL_CHARS = 12000


def _artifact_runtime_hitl_thread_scope(
    runtime_hitl: dict[str, Any] | None, *, subagent_id: str | None = None
) -> dict[str, Any]:
    scoped = dict(runtime_hitl or {})
    if subagent_id:
        scoped["sandbox_scope"] = "subagent"
        scoped["sandbox_scope_id"] = subagent_id
        scoped.pop("subagent_scope_id", None)
    else:
        scoped["sandbox_scope"] = "thread"
        scoped.pop("sandbox_scope_id", None)
        scoped.pop("subagent_scope_id", None)
    return scoped


def _persist_artifact_content(
    *,
    artifact_id: str,
    content: str,
    thread_id: Any,
    turn_key: str,
    sandbox_enabled: bool,
    artifact_storage_mode: str,
    runtime_hitl_cfg: dict[str, Any],
    subagent_id: str | None = None,
) -> tuple[str, str, str]:
    artifact_uri = f"artifact://{artifact_id}"
    normalized_turn = _safe_id_segment(turn_key, fallback="turn")
    normalized_thread = _safe_id_segment(thread_id, fallback="thread")
    requested_mode = str(artifact_storage_mode or _ARTIFACT_DEFAULT_STORAGE_MODE).strip().lower()
    if requested_mode not in {"auto", "sandbox", "local"}:
        requested_mode = _ARTIFACT_DEFAULT_STORAGE_MODE
    effective_mode = requested_mode
    if requested_mode == "auto":
        sandbox_mode = str(runtime_hitl_cfg.get("sandbox_mode") or "").strip().lower()
        if sandbox_mode in {"provisioner", "remote"}:
            effective_mode = "sandbox"
        else:
            effective_mode = "sandbox"
    if effective_mode == "sandbox" and sandbox_enabled:
        artifact_path = f"/workspace/.artifacts/{normalized_turn}/{artifact_id}.json"
        try:
            written_path = sandbox_write_text_file(
                thread_id=thread_id,
                runtime_hitl=_artifact_runtime_hitl_thread_scope(
                    runtime_hitl_cfg, subagent_id=subagent_id
                ),
                path=artifact_path,
                content=content,
                append=False,
            )
            return artifact_uri, str(written_path or artifact_path), "sandbox"
        except Exception:
            pass

    local_root = Path(_ARTIFACT_LOCAL_ROOT).expanduser() / normalized_thread / normalized_turn
    local_root.mkdir(parents=True, exist_ok=True)
    local_path = local_root / f"{artifact_id}.json"
    local_path.write_text(str(content or ""), encoding="utf-8")
    return artifact_uri, str(local_path), "local"


def _read_artifact_content(
    entry: dict[str, Any],
    *,
    sandbox_read_fn: SandboxReadFn | None = None,
) -> str | None:
    """Read artifact content back from disk or sandbox.

    Tries local filesystem first.  If the file is not locally accessible and
    *sandbox_read_fn* is provided, falls back to reading via the sandbox
    runtime (for artifacts stored in remote containers).

    Returns the content string or ``None`` if it cannot be read.
    """
    artifact_path = str(entry.get("artifact_path") or "").strip()
    if not artifact_path:
        return None

    # 1. Try local filesystem (works for storage_backend="local" and
    #    for sandbox backends with mounted volumes).
    try:
        p = Path(artifact_path)
        if p.is_file():
            return p.read_text(encoding="utf-8")
    except Exception:
        pass

    # 2. Try sandbox read for remote-stored artifacts.
    storage_backend = str(entry.get("storage_backend") or "").strip().lower()
    if storage_backend == "sandbox" and sandbox_read_fn is not None:
        try:
            content = sandbox_read_fn(artifact_path)
            if content:
                return content
        except Exception:
            logger.debug(
                "sandbox read failed for artifact %s at %s",
                entry.get("id", "?"),
                artifact_path,
            )

    return None


def _load_recent_artifact_contents(
    manifest: list[dict[str, Any]] | None,
    *,
    max_items: int = _ARTIFACT_READ_MAX_ITEMS,
    max_chars_per_item: int = _ARTIFACT_READ_MAX_CHARS_PER_ITEM,
    max_total_chars: int = _ARTIFACT_READ_MAX_TOTAL_CHARS,
    sandbox_read_fn: SandboxReadFn | None = None,
) -> list[dict[str, str]]:
    """Load contents of the most recent artifacts from the manifest.

    Returns a list of ``{"tool": ..., "summary": ..., "content": ...}`` dicts
    for each artifact whose content could be read, newest first, subject to
    *max_items* / *max_total_chars* limits.

    If *sandbox_read_fn* is provided it will be used as a fallback for artifacts
    stored in a remote sandbox container (``storage_backend="sandbox"``).
    """
    if not manifest:
        return []
    loaded: list[dict[str, str]] = []
    total_chars = 0
    for entry in reversed(manifest):
        if not isinstance(entry, dict):
            continue
        content = _read_artifact_content(entry, sandbox_read_fn=sandbox_read_fn)
        if not content:
            continue
        # Truncate individual artifact content to limit
        if len(content) > max_chars_per_item:
            content = content[:max_chars_per_item] + "\n[...trunkerad]"
        if total_chars + len(content) > max_total_chars:
            # If adding this artifact would exceed the total limit, skip it
            if loaded:
                break
            # If this is the first artifact and already too large, truncate
            remaining = max_total_chars - total_chars
            content = content[:remaining] + "\n[...trunkerad]"
        loaded.append({
            "tool": str(entry.get("tool") or "").strip(),
            "summary": str(entry.get("summary") or "").strip(),
            "content": content,
        })
        total_chars += len(content)
        if len(loaded) >= max_items:
            break
    loaded.reverse()
    return loaded


def _format_artifact_contents_for_context(
    artifact_contents: list[dict[str, str]],
) -> str:
    """Format loaded artifact contents as a context block for LLM injection."""
    if not artifact_contents:
        return ""
    parts: list[str] = []
    for item in artifact_contents:
        tool = item.get("tool") or "tool"
        summary = item.get("summary") or ""
        content = item.get("content") or ""
        parts.append(
            f"<artifact tool=\"{tool}\" summary=\"{summary}\">\n{content}\n</artifact>"
        )
    return "<artifact_data>\n" + "\n".join(parts) + "\n</artifact_data>"


def _tokenize_for_memory_relevance(text: str) -> set[str]:
    tokens = _tokenize(_normalize_text(str(text or "")))
    return {
        token
        for token in tokens
        if len(token) >= 3 and token not in _AGENT_STOPWORDS
    }


def _select_cross_session_memory_entries(
    *,
    entries: list[dict[str, Any]],
    query: str,
    max_items: int,
) -> list[dict[str, Any]]:
    if not entries:
        return []
    query_tokens = _tokenize_for_memory_relevance(query)
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("memory_text") or "").strip()
        if not text:
            continue
        category = str(entry.get("category") or "fact").strip().lower()
        entry_tokens = _tokenize_for_memory_relevance(text)
        overlap = len(query_tokens.intersection(entry_tokens))
        score = overlap * 10 + max(0, len(entries) - index)
        if category in {"instruction", "preference"}:
            score += 2
        if overlap == 0 and category not in {"instruction", "preference"}:
            continue
        scored.append((score, index, entry))
    if not scored:
        return [item for item in entries[: max(1, min(max_items, 2))] if isinstance(item, dict)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _score, _index, entry in scored:
        key = str(entry.get("id") or "").strip() or hashlib.sha1(
            str(entry.get("memory_text") or "").encode("utf-8", errors="ignore")
        ).hexdigest()[:12]
        if key in seen:
            continue
        seen.add(key)
        selected.append(entry)
        if len(selected) >= max(1, int(max_items)):
            break
    return selected


def _render_cross_session_memory_context(
    *,
    entries: list[dict[str, Any]],
    max_chars: int,
) -> str:
    if not entries:
        return ""
    lines: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "fact").strip().lower()
        memory_text = _truncate_for_prompt(str(entry.get("memory_text") or "").strip(), 220)
        if not memory_text:
            continue
        lines.append(f"- [{category}] {memory_text}")
    if not lines:
        return ""
    rendered = "\n".join(lines)
    return _truncate_for_prompt(rendered, max_chars)
