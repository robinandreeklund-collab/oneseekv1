"""State formatting, message processing, and context building for supervisor agent."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.new_chat.supervisor_constants import (
    _ARTIFACT_CONTEXT_MAX_ITEMS,
    _CONTEXT_COMPACTION_DEFAULT_SUMMARY_MAX_CHARS,
    _SUBAGENT_MAX_HANDOFFS_IN_PROMPT,
)
from app.agents.new_chat.supervisor_text_utils import _truncate_for_prompt


def _count_tools_since_last_user(messages: list[Any]) -> int:
    count = 0
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage):
            count += 1
    return count


def _format_plan_context(state: dict[str, Any]) -> str | None:
    plan = state.get("active_plan") or []
    if not plan:
        return None
    status = "complete" if state.get("plan_complete") else "active"
    lines = []
    for item in plan:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        step_status = str(item.get("status") or "pending").lower()
        lines.append(f"- [{step_status}] {content}")
    if not lines:
        return None
    return f"<active_plan status=\"{status}\">\n" + "\n".join(lines) + "\n</active_plan>"


def _format_recent_calls(state: dict[str, Any]) -> str | None:
    recent_calls = state.get("recent_agent_calls") or []
    if not recent_calls:
        return None
    lines = []
    for call in recent_calls[-3:]:
        agent = call.get("agent")
        task = call.get("task")
        response = call.get("response") or ""
        if response and len(response) > 180:
            response = response[:177] + "..."
        lines.append(f"- {agent}: {task} → {response}")
    if not lines:
        return None
    return "<recent_agent_calls>\n" + "\n".join(lines) + "\n</recent_agent_calls>"


def _format_route_hint(state: dict[str, Any]) -> str | None:
    hint = state.get("route_hint")
    if not hint:
        return None
    return f"<route_hint>{hint}</route_hint>"


def _format_execution_strategy(state: dict[str, Any]) -> str | None:
    strategy = str(state.get("execution_strategy") or "").strip().lower()
    if not strategy:
        return None
    return f"<execution_strategy>{strategy}</execution_strategy>"


def _format_intent_context(state: dict[str, Any]) -> str | None:
    intent = state.get("resolved_intent")
    if not isinstance(intent, dict):
        return None
    intent_id = str(intent.get("intent_id") or "").strip()
    route = str(intent.get("route") or "").strip()
    reason = str(intent.get("reason") or "").strip()
    sub_intents_raw = intent.get("sub_intents")
    sub_intents: list[str] = []
    if isinstance(sub_intents_raw, list):
        sub_intents = [
            str(item).strip()
            for item in sub_intents_raw
            if str(item).strip()
        ][:4]
    if not sub_intents and isinstance(state.get("sub_intents"), list):
        sub_intents = [
            str(item).strip()
            for item in state.get("sub_intents")
            if str(item).strip()
        ][:4]
    if not (intent_id or route):
        return None
    lines = [f"intent_id={intent_id or 'unknown'}", f"route={route or 'unknown'}"]
    if sub_intents:
        lines.append("sub_intents=" + ",".join(sub_intents))
    if reason:
        lines.append(f"reason={_truncate_for_prompt(reason, 180)}")
    return "<resolved_intent>\n" + "\n".join(lines) + "\n</resolved_intent>"


def _format_selected_agents_context(state: dict[str, Any]) -> str | None:
    selected = state.get("selected_agents")
    if not isinstance(selected, list) or not selected:
        return None
    lines: list[str] = []
    for item in selected[:3]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        description = str(item.get("description") or "").strip()
        if description:
            lines.append(f"- {name}: {_truncate_for_prompt(description, 140)}")
        else:
            lines.append(f"- {name}")
    if not lines:
        return None
    return "<selected_agents>\n" + "\n".join(lines) + "\n</selected_agents>"


def _format_resolved_tools_context(state: dict[str, Any]) -> str | None:
    resolved = state.get("resolved_tools_by_agent")
    if not isinstance(resolved, dict) or not resolved:
        return None
    lines: list[str] = []
    for agent_name, tool_ids in list(resolved.items())[:3]:
        normalized_agent = str(agent_name or "").strip()
        if not normalized_agent:
            continue
        safe_tools = [
            str(tool_id).strip()
            for tool_id in (tool_ids if isinstance(tool_ids, list) else [])
            if str(tool_id).strip()
        ][:6]
        if not safe_tools:
            continue
        lines.append(f"- {normalized_agent}: {', '.join(safe_tools)}")
    if not lines:
        return None
    return "<resolved_tools>\n" + "\n".join(lines) + "\n</resolved_tools>"


def _format_subagent_handoffs_context(state: dict[str, Any]) -> str | None:
    handoffs = state.get("subagent_handoffs")
    if not isinstance(handoffs, list) or not handoffs:
        return None
    lines: list[str] = []
    for handoff in handoffs[-_SUBAGENT_MAX_HANDOFFS_IN_PROMPT:]:
        if not isinstance(handoff, dict):
            continue
        subagent_id = str(handoff.get("subagent_id") or "").strip()
        agent = str(handoff.get("agent") or "agent").strip() or "agent"
        summary = _truncate_for_prompt(str(handoff.get("summary") or "").strip(), 220)
        if not summary:
            continue
        artifact_refs_raw = handoff.get("artifact_refs")
        artifact_refs = (
            [
                str(item).strip()
                for item in artifact_refs_raw
                if str(item).strip()
            ][:3]
            if isinstance(artifact_refs_raw, list)
            else []
        )
        artifact_hint = f" artifacts={','.join(artifact_refs)}" if artifact_refs else ""
        prefix = f"- {agent}"
        if subagent_id:
            prefix += f" ({subagent_id})"
        lines.append(f"{prefix}: {summary}{artifact_hint}")
    if not lines:
        return None
    return "<subagent_handoffs>\n" + "\n".join(lines) + "\n</subagent_handoffs>"


def _format_artifact_manifest_context(state: dict[str, Any]) -> str | None:
    artifacts = state.get("artifact_manifest")
    if not isinstance(artifacts, list) or not artifacts:
        return None
    lines: list[str] = []
    for item in artifacts[-_ARTIFACT_CONTEXT_MAX_ITEMS:]:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("id") or "").strip()
        tool_name = str(item.get("tool") or "").strip() or "tool"
        summary = _truncate_for_prompt(str(item.get("summary") or "").strip(), 180)
        artifact_uri = str(item.get("artifact_uri") or "").strip()
        artifact_path = str(item.get("artifact_path") or "").strip()
        size_bytes = int(item.get("size_bytes") or 0)
        ref = artifact_uri or artifact_path
        if not ref:
            continue
        label = f"- {tool_name}"
        if artifact_id:
            label += f" ({artifact_id})"
        suffix: list[str] = [f"ref={ref}"]
        if size_bytes > 0:
            suffix.append(f"bytes={size_bytes}")
        if summary:
            suffix.append(f"summary={summary}")
        lines.append(f"{label}: " + "; ".join(suffix))
    if not lines:
        return None
    return "<artifact_manifest>\n" + "\n".join(lines) + "\n</artifact_manifest>"


def _format_cross_session_memory_context(state: dict[str, Any]) -> str | None:
    memory_context = _truncate_for_prompt(
        str(state.get("cross_session_memory_context") or "").strip(),
        1400,
    )
    if not memory_context:
        return None
    return "<cross_session_memory>\n" + memory_context + "\n</cross_session_memory>"


def _format_rolling_context_summary_context(state: dict[str, Any]) -> str | None:
    summary = _truncate_for_prompt(
        str(state.get("rolling_context_summary") or "").strip(),
        _CONTEXT_COMPACTION_DEFAULT_SUMMARY_MAX_CHARS,
    )
    if not summary:
        return None
    return "<rolling_context_summary>\n" + summary + "\n</rolling_context_summary>"


def _format_compare_outputs_for_prompt(compare_outputs: list[dict[str, Any]] | None) -> str:
    if not compare_outputs:
        return ""
    blocks: list[str] = []
    for output in compare_outputs:
        model_name = (
            output.get("model_display_name")
            or output.get("model")
            or output.get("tool_name")
            or "Model"
        )
        response = output.get("response") or ""
        if not isinstance(response, str):
            response = str(response)
        response = response.strip()
        if not response:
            continue
        citation_ids = output.get("citation_chunk_ids") or []
        if isinstance(citation_ids, str):
            citation_ids = [citation_ids]
        citation_hint = ", ".join([str(cid) for cid in citation_ids if cid])
        cite_note = (
            f" (citation_ids: {citation_hint})" if citation_hint else ""
        )
        blocks.append(f"MODEL_ANSWER ({model_name}){cite_note}:\n{response}")
    if not blocks:
        return ""
    return "<compare_outputs>\n" + "\n\n".join(blocks) + "\n</compare_outputs>"


def _tool_call_name_index(messages: list[Any] | None) -> dict[str, str]:
    index: dict[str, str] = {}
    for message in messages or []:
        if not isinstance(message, AIMessage):
            continue
        tool_calls = getattr(message, "tool_calls", None) or []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_call_id = str(tool_call.get("id") or "").strip()
            tool_name = str(tool_call.get("name") or "").strip()
            if tool_call_id and tool_name and tool_call_id not in index:
                index[tool_call_id] = tool_name
    return index
