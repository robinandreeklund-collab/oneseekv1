from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agents.new_chat.token_budget import TokenBudget

logger = logging.getLogger(__name__)

# Matches <think>...</think> reasoning blocks emitted by models such as
# nvidia/nemotron-3-nano, Qwen3 (thinking mode), DeepSeek-R1, etc.
# We strip these from the *history* stored in agent state so accumulated
# thinking tokens never contaminate the context window sent to the LLM.
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from a string."""
    stripped = _THINK_TAG_RE.sub("", text)
    return stripped.strip()


def _normalize_message_content(value: Any) -> str:
    """Normalize message content to plain text for strict OpenAI templates."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text_parts: list[str] = []
        for part in value:
            if part is None:
                continue
            if isinstance(part, str):
                if part:
                    text_parts.append(part)
                continue
            if isinstance(part, dict):
                normalized = {k: v for k, v in part.items() if v is not None}
                part_text = ""
                if normalized.get("type") == "text" or "text" in normalized:
                    part_text = str(normalized.get("text") or "")
                elif "content" in normalized:
                    part_text = str(normalized.get("content") or "")
                elif "value" in normalized:
                    part_text = str(normalized.get("value") or "")
                elif normalized:
                    try:
                        part_text = json.dumps(normalized, ensure_ascii=False)
                    except Exception:
                        part_text = str(normalized)
                if part_text:
                    text_parts.append(part_text)
                continue
            text_parts.append(str(part))
        return "\n".join(part for part in text_parts if part).strip()
    return str(value)


def _sanitize_template_value(value: Any) -> Any:
    """Recursively sanitize values so strict templates don't receive null."""
    if value is None:
        return ""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if item is None:
                continue
            sanitized[str(key)] = _sanitize_template_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_template_value(item) for item in value if item is not None]
    return value


def _normalize_tool_call_dict(tool_call: Any, *, index: int) -> dict[str, Any] | None:
    """Ensure tool call payload has non-null id/name/args for strict templates."""
    if not isinstance(tool_call, dict):
        return None
    normalized = dict(tool_call)

    raw_name = normalized.get("name")
    if not raw_name and isinstance(normalized.get("function"), dict):
        raw_name = normalized["function"].get("name")
    name = str(raw_name or "").strip() or "tool_call"
    call_id = str(normalized.get("id") or normalized.get("tool_call_id") or "").strip()
    if not call_id:
        call_id = f"call_{index}"

    raw_args = normalized.get("args")
    if raw_args is None:
        args: dict[str, Any] = {}
    elif isinstance(raw_args, dict):
        args = raw_args
    elif isinstance(raw_args, str):
        payload = raw_args.strip()
        if not payload:
            args = {}
        else:
            try:
                parsed = json.loads(payload)
            except Exception:
                args = {"value": payload}
            else:
                args = parsed if isinstance(parsed, dict) else {"value": payload}
    else:
        args = {"value": str(raw_args)}

    normalized["id"] = call_id
    normalized["name"] = name
    normalized["args"] = _sanitize_template_value(args)
    if isinstance(normalized.get("function"), dict):
        function_payload = dict(normalized["function"])
        function_payload["name"] = name
        function_payload["arguments"] = json.dumps(normalized["args"], ensure_ascii=False)
        normalized["function"] = function_payload
    if normalized.get("type") is None:
        normalized["type"] = "tool_call"
    return _sanitize_template_value(normalized)


def _hoist_system_messages(messages: list[Any]) -> list[Any]:
    """
    Collapse all SystemMessages into a single one at position 0.

    LangGraph's add_messages reducer can produce mid-conversation SystemMessages
    when the same system prompt is re-injected on a retry or reload (e.g.
    [system, user, system, user]).  Strict Jinja templates (LM Studio / nemotron)
    fail with "Cannot apply filter 'string' to type: NullValue" in that case.

    Strategy: collect every SystemMessage, join their content, and place a single
    merged SystemMessage at the front while keeping all other messages in order.
    """
    system_parts: list[str] = []
    rest: list[Any] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            part = _normalize_message_content(getattr(msg, "content", ""))
            if part:
                system_parts.append(part)
        else:
            rest.append(msg)
    if not system_parts:
        return rest
    merged_content = "\n\n".join(system_parts)
    try:
        merged_system = messages[
            next(i for i, m in enumerate(messages) if isinstance(m, SystemMessage))
        ].model_copy(update={"content": merged_content})
    except Exception:
        merged_system = SystemMessage(content=merged_content)
    return [merged_system, *rest]


def _normalize_messages_for_provider_compat(messages: list[Any]) -> list[Any]:
    """
    Guardrail for strict OpenAI-compatible templates (e.g. LM Studio Jinja).
    Avoid NullValue in content/tool-call fields between turns.
    """
    # Collapse multiple SystemMessages into one at position 0 first so that the
    # per-message normalisation below never sees a mid-conversation system message.
    messages = _hoist_system_messages(messages)
    normalized_messages: list[Any] = []
    for idx, message in enumerate(messages):
        if isinstance(message, AIMessage):
            content = _strip_thinking_tags(
                _normalize_message_content(getattr(message, "content", ""))
            )
            raw_tool_calls = getattr(message, "tool_calls", None)
            tool_calls: list[dict[str, Any]] = []
            if isinstance(raw_tool_calls, list):
                for tool_idx, tool_call in enumerate(raw_tool_calls):
                    normalized_tool_call = _normalize_tool_call_dict(
                        tool_call,
                        index=tool_idx,
                    )
                    if normalized_tool_call:
                        tool_calls.append(normalized_tool_call)
            try:
                updated = {
                    "content": content,
                    "additional_kwargs": _sanitize_template_value(
                        dict(getattr(message, "additional_kwargs", {}) or {})
                    ),
                    "response_metadata": _sanitize_template_value(
                        dict(getattr(message, "response_metadata", {}) or {})
                    ),
                }
                if isinstance(raw_tool_calls, list):
                    updated["tool_calls"] = tool_calls
                normalized_messages.append(message.model_copy(update=updated))
            except Exception:
                normalized_messages.append(
                    AIMessage(
                        content=content,
                        tool_calls=tool_calls,
                        additional_kwargs=_sanitize_template_value(
                            dict(getattr(message, "additional_kwargs", {}) or {})
                        ),
                        response_metadata=_sanitize_template_value(
                            dict(getattr(message, "response_metadata", {}) or {})
                        ),
                        id=getattr(message, "id", None),
                    )
                )
            continue

        if isinstance(message, ToolMessage):
            content = _normalize_message_content(getattr(message, "content", ""))
            name = str(getattr(message, "name", "") or "").strip() or "tool"
            tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
            if not tool_call_id:
                tool_call_id = f"tool_call_{idx}"
            try:
                normalized_messages.append(
                    message.model_copy(
                        update={
                            "content": content,
                            "name": name,
                            "tool_call_id": tool_call_id,
                        }
                    )
                )
            except Exception:
                normalized_messages.append(
                    ToolMessage(
                        content=content,
                        name=name,
                        tool_call_id=tool_call_id,
                    )
                )
            continue

        if isinstance(message, HumanMessage):
            content = _normalize_message_content(getattr(message, "content", ""))
            try:
                normalized_messages.append(message.model_copy(update={"content": content}))
            except Exception:
                normalized_messages.append(HumanMessage(content=content))
            continue

        if isinstance(message, SystemMessage):
            content = _normalize_message_content(getattr(message, "content", ""))
            try:
                normalized_messages.append(message.model_copy(update={"content": content}))
            except Exception:
                normalized_messages.append(SystemMessage(content=content))
            continue

        normalized_messages.append(message)
    return normalized_messages


def _is_jinja_nullvalue_error(error: Exception) -> bool:
    text = str(error or "")
    lowered = text.lower()
    return (
        "error rendering prompt with jinja template" in lowered
        and "nullvalue" in lowered
    ) or (
        "cannot apply filter \"string\" to type: nullvalue" in lowered
    )


def _build_template_safe_retry_messages(messages: list[Any]) -> list[Any]:
    """
    Retry payload for strict templates:
    - collapse ToolMessage blocks into one HumanMessage observation
    - strip assistant tool_calls metadata from historical assistant messages
    """
    retried: list[Any] = []
    pending_tool_lines: list[str] = []

    def _flush_tool_lines() -> None:
        if not pending_tool_lines:
            return
        retried.append(
            HumanMessage(
                content=(
                    "<tool_results>\n"
                    + "\n".join(pending_tool_lines)
                    + "\n</tool_results>"
                )
            )
        )
        pending_tool_lines.clear()

    for idx, message in enumerate(messages):
        if isinstance(message, ToolMessage):
            tool_name = str(getattr(message, "name", "") or "").strip() or "tool"
            tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
            content = _normalize_message_content(getattr(message, "content", ""))
            label = f"{tool_name}" + (f"#{tool_call_id}" if tool_call_id else "")
            line = f"- {label}: {content or '(empty)'}"
            pending_tool_lines.append(line)
            continue

        _flush_tool_lines()
        if isinstance(message, AIMessage):
            try:
                retried.append(
                    message.model_copy(
                        update={
                            "content": _strip_thinking_tags(
                                _normalize_message_content(
                                    getattr(message, "content", "")
                                )
                            ),
                            "tool_calls": [],
                        }
                    )
                )
            except Exception:
                retried.append(
                    AIMessage(
                        content=_strip_thinking_tags(
                            _normalize_message_content(
                                getattr(message, "content", "")
                            )
                        ),
                        additional_kwargs=dict(
                            getattr(message, "additional_kwargs", {}) or {}
                        ),
                        response_metadata=dict(
                            getattr(message, "response_metadata", {}) or {}
                        ),
                        id=getattr(message, "id", None),
                    )
                )
            continue

        if isinstance(message, HumanMessage):
            retried.append(
                HumanMessage(
                    content=_normalize_message_content(getattr(message, "content", ""))
                )
            )
            continue

        if isinstance(message, SystemMessage):
            retried.append(
                SystemMessage(
                    content=_normalize_message_content(getattr(message, "content", ""))
                )
            )
            continue

        retried.append(message)

    _flush_tool_lines()
    return retried


def _build_executor_updates_for_new_user_turn(
    *,
    incoming_turn_id: str,
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "resolved_intent": None,
        "graph_complexity": None,
        "speculative_candidates": [],
        "speculative_results": {},
        "execution_strategy": None,
        "worker_results": [],
        "synthesis_drafts": [],
        "retrieval_feedback": {},
        "targeted_missing_info": [],
        "selected_agents": [],
        "resolved_tools_by_agent": {},
        "query_embedding": None,
        "active_plan": [],
        "plan_step_index": 0,
        "plan_complete": False,
        "step_results": [],
        "recent_agent_calls": [],
        "compare_outputs": [],
        "subagent_handoffs": [],
        "cross_session_memory_context": None,
        "rolling_context_summary": None,
        "final_agent_response": None,
        "final_response": None,
        "critic_decision": None,
        "awaiting_confirmation": False,
        "pending_hitl_stage": None,
        "pending_hitl_payload": None,
        "user_feedback": None,
        "replan_count": 0,
        "orchestration_phase": "select_agent",
        "agent_hops": 0,
        "no_progress_runs": 0,
        "guard_parallel_preview": [],
    }
    if incoming_turn_id:
        updates["active_turn_id"] = incoming_turn_id
    return updates


def build_executor_nodes(
    *,
    llm: Any,
    llm_with_tools: Any,
    compare_mode: bool,
    strip_critic_json_fn: Callable[[str], str],
    sanitize_messages_fn: Callable[[list[Any]], list[Any]],
    format_plan_context_fn: Callable[[dict[str, Any]], str | None],
    format_recent_calls_fn: Callable[[dict[str, Any]], str | None],
    format_route_hint_fn: Callable[[dict[str, Any]], str | None],
    format_execution_strategy_fn: Callable[[dict[str, Any]], str | None],
    format_intent_context_fn: Callable[[dict[str, Any]], str | None],
    format_selected_agents_context_fn: Callable[[dict[str, Any]], str | None],
    format_resolved_tools_context_fn: Callable[[dict[str, Any]], str | None],
    format_subagent_handoffs_context_fn: Callable[[dict[str, Any]], str | None],
    format_artifact_manifest_context_fn: Callable[[dict[str, Any]], str | None],
    format_cross_session_memory_context_fn: Callable[[dict[str, Any]], str | None],
    format_rolling_context_summary_context_fn: Callable[[dict[str, Any]], str | None],
    coerce_supervisor_tool_calls_fn: Callable[..., Any],
):
    def _build_context_messages(
        *,
        state: dict[str, Any],
        new_user_turn: bool,
    ) -> list[Any]:
        messages = sanitize_messages_fn(list(state.get("messages") or []))
        plan_context = None if new_user_turn else format_plan_context_fn(state)
        recent_context = None if new_user_turn else format_recent_calls_fn(state)
        route_context = format_route_hint_fn(state)
        execution_strategy_context = (
            None if new_user_turn else format_execution_strategy_fn(state)
        )
        intent_context = None if new_user_turn else format_intent_context_fn(state)
        selected_agents_context = (
            None if new_user_turn else format_selected_agents_context_fn(state)
        )
        resolved_tools_context = (
            None if new_user_turn else format_resolved_tools_context_fn(state)
        )
        subagent_handoffs_context = (
            None if new_user_turn else format_subagent_handoffs_context_fn(state)
        )
        artifact_manifest_context = (
            None if new_user_turn else format_artifact_manifest_context_fn(state)
        )
        cross_session_memory_context = (
            None if new_user_turn else format_cross_session_memory_context_fn(state)
        )
        rolling_context_summary = (
            None if new_user_turn else format_rolling_context_summary_context_fn(state)
        )
        system_bits = [
            item
            for item in (
                plan_context,
                recent_context,
                route_context,
                execution_strategy_context,
                intent_context,
                selected_agents_context,
                resolved_tools_context,
                subagent_handoffs_context,
                artifact_manifest_context,
                cross_session_memory_context,
                rolling_context_summary,
            )
            if item
        ]
        if system_bits:
            extra = "\n".join(system_bits)
            if messages and isinstance(messages[0], SystemMessage):
                # Merge context bits into the existing leading system message to
                # avoid a second SystemMessage appearing mid-conversation, which
                # breaks strict Jinja templates (e.g. LM Studio / nemotron-3-nano).
                existing = _normalize_message_content(
                    getattr(messages[0], "content", "")
                )
                merged = (existing + "\n\n" + extra).strip() if existing else extra
                try:
                    messages = [
                        messages[0].model_copy(update={"content": merged})
                    ] + messages[1:]
                except Exception:
                    messages = [SystemMessage(content=merged)] + messages[1:]
            else:
                messages = [SystemMessage(content=extra)] + messages
        model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None) or ""
        if model_name:
            budget = TokenBudget(model_name=str(model_name))
            messages = budget.fit_messages(messages)
        return messages

    def call_model(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        final_response = state.get("final_agent_response") or state.get("final_response")
        messages_state = state.get("messages") or []
        last_message = messages_state[-1] if messages_state else None
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        if final_response and isinstance(last_message, ToolMessage) and not new_user_turn:
            return {"messages": [AIMessage(content=strip_critic_json_fn(str(final_response)))]}
        if not incoming_turn_id and final_response and isinstance(last_message, HumanMessage):
            # Legacy fallback when turn_id is missing.
            new_user_turn = True

        def _latest_user_text(messages: list[Any]) -> str:
            for message in reversed(messages or []):
                if isinstance(message, HumanMessage):
                    return _normalize_message_content(getattr(message, "content", ""))
                if (
                    isinstance(message, dict)
                    and str(message.get("type") or "").strip().lower()
                    in {"human", "user"}
                ):
                    return _normalize_message_content(message.get("content"))
            return ""

        def _has_tool_since_last_human(messages: list[Any]) -> bool:
            for message in reversed(messages or []):
                if isinstance(message, HumanMessage):
                    return False
                if isinstance(message, ToolMessage):
                    return True
            return False

        route_hint = str(state.get("route_hint") or "").strip().lower()
        resolved_intent = state.get("resolved_intent")
        sub_intents: list[str] = []
        if isinstance(resolved_intent, dict):
            raw_subs = resolved_intent.get("sub_intents")
            if isinstance(raw_subs, list):
                sub_intents = [
                    str(item).strip()
                    for item in raw_subs
                    if str(item).strip()
                ][:4]
        if not sub_intents and isinstance(state.get("sub_intents"), list):
            sub_intents = [
                str(item).strip()
                for item in state.get("sub_intents")
                if str(item).strip()
            ][:4]
        selected_agents: list[str] = []
        seen_agents: set[str] = set()
        for item in state.get("selected_agents") or []:
            name = ""
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip().lower()
            else:
                name = str(item or "").strip().lower()
            if not name or name in seen_agents:
                continue
            seen_agents.add(name)
            selected_agents.append(name)

        if (
            route_hint == "mixed"
            and len(selected_agents) >= 2
            and not _has_tool_since_last_human(messages_state)
        ):
            latest_user_query = _latest_user_text(messages_state)
            calls: list[dict[str, Any]] = []
            for idx, agent_name in enumerate(selected_agents[:3]):
                focus = ""
                if idx < len(sub_intents):
                    focus = sub_intents[idx]
                elif sub_intents:
                    focus = sub_intents[-1]
                focus_line = f"Fokus: {focus}".strip() if focus else ""
                task_parts = [
                    part.strip()
                    for part in [latest_user_query, focus_line]
                    if str(part or "").strip()
                ]
                task_text = "\n".join(task_parts).strip()
                if not task_text:
                    task_text = "Hantera deluppgiften for denna domain."
                calls.append(
                    {
                        "agent": agent_name,
                        "task": task_text,
                    }
                )
            if calls:
                tool_call = {
                    "id": "auto_mixed_parallel",
                    "name": "call_agents_parallel",
                    "args": {"calls": calls},
                }
                auto_response = AIMessage(content="", tool_calls=[tool_call])
                updates = {"messages": [auto_response], "execution_strategy": "parallel"}
                if new_user_turn:
                    updates.update(
                        _build_executor_updates_for_new_user_turn(
                            incoming_turn_id=incoming_turn_id,
                        )
                    )
                elif incoming_turn_id and not active_turn_id:
                    updates["active_turn_id"] = incoming_turn_id
                if final_response and new_user_turn:
                    updates["final_agent_response"] = None
                    updates["final_response"] = None
                return updates

        messages = _build_context_messages(state=state, new_user_turn=new_user_turn)
        messages = _normalize_messages_for_provider_compat(messages)
        try:
            response = llm_with_tools.invoke(messages)
        except Exception as exc:
            if not _is_jinja_nullvalue_error(exc):
                raise
            retry_messages = _build_template_safe_retry_messages(messages)
            logger.warning(
                "Template NullValue in sync invoke; retrying with tool-result compaction"
            )
            try:
                response = llm_with_tools.invoke(retry_messages)
            except Exception as retry_exc:
                if not _is_jinja_nullvalue_error(retry_exc):
                    raise
                logger.warning(
                    "Template NullValue persisted after compaction; retrying without tools"
                )
                response = llm.invoke(retry_messages)
        response = coerce_supervisor_tool_calls_fn(
            response,
            orchestration_phase=str(state.get("orchestration_phase") or ""),
            agent_hops=int(state.get("agent_hops") or 0),
            execution_strategy=str(state.get("execution_strategy") or ""),
            allow_multiple=bool(compare_mode),
            state=state,
        )
        updates: dict[str, Any] = {"messages": [response]}
        if new_user_turn:
            updates.update(
                _build_executor_updates_for_new_user_turn(
                    incoming_turn_id=incoming_turn_id,
                )
            )
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id
        if final_response and new_user_turn:
            updates["final_agent_response"] = None
            updates["final_response"] = None
        return updates

    async def acall_model(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        final_response = state.get("final_agent_response") or state.get("final_response")
        messages_state = state.get("messages") or []
        last_message = messages_state[-1] if messages_state else None
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        if final_response and isinstance(last_message, ToolMessage) and not new_user_turn:
            return {"messages": [AIMessage(content=strip_critic_json_fn(str(final_response)))]}
        if not incoming_turn_id and final_response and isinstance(last_message, HumanMessage):
            new_user_turn = True

        messages = _build_context_messages(state=state, new_user_turn=new_user_turn)
        messages = _normalize_messages_for_provider_compat(messages)
        try:
            response = await llm_with_tools.ainvoke(messages)
        except Exception as exc:
            if not _is_jinja_nullvalue_error(exc):
                raise
            retry_messages = _build_template_safe_retry_messages(messages)
            logger.warning(
                "Template NullValue in async invoke; retrying with tool-result compaction"
            )
            try:
                response = await llm_with_tools.ainvoke(retry_messages)
            except Exception as retry_exc:
                if not _is_jinja_nullvalue_error(retry_exc):
                    raise
                logger.warning(
                    "Template NullValue persisted after compaction; retrying without tools"
                )
                response = await llm.ainvoke(retry_messages)
        response = coerce_supervisor_tool_calls_fn(
            response,
            orchestration_phase=str(state.get("orchestration_phase") or ""),
            agent_hops=int(state.get("agent_hops") or 0),
            execution_strategy=str(state.get("execution_strategy") or ""),
            allow_multiple=bool(compare_mode),
            state=state,
        )
        updates: dict[str, Any] = {"messages": [response]}
        if new_user_turn:
            updates.update(
                _build_executor_updates_for_new_user_turn(
                    incoming_turn_id=incoming_turn_id,
                )
            )
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id
        if final_response and new_user_turn:
            updates["final_agent_response"] = None
            updates["final_response"] = None
        return updates

    return call_model, acall_model
