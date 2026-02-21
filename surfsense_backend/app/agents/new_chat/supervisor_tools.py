"""Tool selection, sanitization, and prompt building for supervisor agent."""
from __future__ import annotations

from typing import Any

from app.agents.new_chat.supervisor_constants import (
    _AGENT_TOOL_PROFILE_BY_ID,
)
from app.agents.new_chat.supervisor_routing import _select_focused_tool_profiles
from app.agents.new_chat.supervisor_runtime_prompts import (
    DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE,
    DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
)


def _worker_available_tool_ids(worker: Any) -> list[str]:
    raw_ids = getattr(worker, "available_tool_ids", None)
    if not isinstance(raw_ids, (list, tuple, set)):
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for tool_id in raw_ids:
        normalized = str(tool_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _normalize_tool_id_list(
    tool_ids: list[str] | tuple[str, ...] | set[str] | None,
    *,
    limit: int = 8,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for tool_id in list(tool_ids or []):
        normalized = str(tool_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
        if len(ordered) >= max(1, int(limit)):
            break
    return ordered


def _fallback_tool_ids_for_tool(tool_id: str) -> list[str]:
    normalized = str(tool_id or "").strip().lower()
    if normalized.startswith("smhi_") and normalized != "smhi_weather":
        return ["smhi_weather"]
    return []


def _sanitize_selected_tool_ids_for_worker(
    worker: Any,
    selected_tool_ids: list[str],
    *,
    fallback_tool_ids: list[str] | None = None,
    limit: int = 8,
) -> list[str]:
    normalized_selected = _normalize_tool_id_list(selected_tool_ids, limit=limit)
    available_ids = _worker_available_tool_ids(worker)
    if not available_ids:
        return normalized_selected

    available_set = set(available_ids)
    filtered = [tool_id for tool_id in normalized_selected if tool_id in available_set]
    if filtered:
        return filtered[: max(1, int(limit))]

    fallback_candidates = _normalize_tool_id_list(fallback_tool_ids, limit=limit)
    fallback_filtered = [
        tool_id for tool_id in fallback_candidates if tool_id in available_set
    ]
    if fallback_filtered:
        return fallback_filtered[: max(1, int(limit))]

    return []


def _format_prompt_template(
    template: str,
    variables: dict[str, Any],
) -> str | None:
    normalized_template = str(template or "").strip()
    if not normalized_template:
        return None
    try:
        rendered = normalized_template.format(**variables)
    except Exception:
        return None
    rendered_text = str(rendered or "").strip()
    return rendered_text or None


def _build_scoped_prompt_for_agent(
    agent_name: str,
    task: str,
    *,
    prompt_template: str = DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE,
) -> str | None:
    focused = _select_focused_tool_profiles(agent_name, task, limit=3)
    if not focused:
        return None
    tool_lines: list[str] = []
    for profile in focused:
        keywords = ", ".join(profile.keywords[:4]) if profile.keywords else ""
        snippet = profile.description.strip()
        if len(snippet) > 140:
            snippet = snippet[:137].rstrip() + "..."
        tool_lines.append(
            f"- {profile.tool_id} ({profile.category})"
            + (f": {snippet}" if snippet else "")
            + (f" [nyckelord: {keywords}]" if keywords else "")
        )
    rendered = _format_prompt_template(
        prompt_template,
        {
            "tool_lines": "\n".join(tool_lines),
            "agent_name": str(agent_name or "").strip(),
            "task": str(task or "").strip(),
        },
    )
    if rendered:
        return rendered
    return DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE.format(
        tool_lines="\n".join(tool_lines)
    )


def _default_prompt_for_tool_id(
    tool_id: str,
    *,
    prompt_template: str = DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
) -> str | None:
    profile = _AGENT_TOOL_PROFILE_BY_ID.get(str(tool_id or "").strip())
    if not profile:
        return None
    keywords = ", ".join(profile.keywords[:8]) if profile.keywords else "-"
    description = profile.description.strip() or "-"
    rendered = _format_prompt_template(
        prompt_template,
        {
            "tool_id": profile.tool_id,
            "category": profile.category,
            "description": description,
            "keywords": keywords,
        },
    )
    if rendered:
        return rendered
    return DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE.format(
        tool_id=profile.tool_id,
        category=profile.category,
        description=description,
        keywords=keywords,
    )


def _tool_prompt_for_id(
    tool_id: str,
    tool_prompt_overrides: dict[str, str],
    *,
    default_prompt_template: str = DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
) -> str | None:
    normalized_tool_id = str(tool_id or "").strip()
    if not normalized_tool_id:
        return None
    override_key = f"tool.{normalized_tool_id}.system"
    override = str(tool_prompt_overrides.get(override_key) or "").strip()
    if override:
        return override
    return _default_prompt_for_tool_id(
        normalized_tool_id,
        prompt_template=default_prompt_template,
    )


def _build_tool_prompt_block(
    selected_tool_ids: list[str],
    tool_prompt_overrides: dict[str, str],
    *,
    max_tools: int = 2,
    default_prompt_template: str = DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
) -> str | None:
    blocks: list[str] = []
    seen: set[str] = set()
    for tool_id in selected_tool_ids:
        normalized_tool_id = str(tool_id or "").strip()
        if not normalized_tool_id or normalized_tool_id in seen:
            continue
        seen.add(normalized_tool_id)
        prompt_text = _tool_prompt_for_id(
            normalized_tool_id,
            tool_prompt_overrides,
            default_prompt_template=default_prompt_template,
        )
        if prompt_text:
            blocks.append(prompt_text)
        if len(blocks) >= max(1, int(max_tools)):
            break
    if not blocks:
        return None
    return "\n\n".join(blocks)
