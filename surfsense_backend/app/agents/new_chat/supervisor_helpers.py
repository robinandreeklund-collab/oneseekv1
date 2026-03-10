"""Pure utility functions extracted from supervisor_agent.py.

Contains tool-call analysis, plan tracking, agent result contracts,
message sanitization, loop detection, and context summarization helpers.

All functions are stateless and do not depend on closure variables
from ``create_supervisor_agent()``.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from app.agents.new_chat.supervisor_constants import (
    _BLOCKED_RESPONSE_MARKERS,
    _CONTEXT_COMPACTION_DEFAULT_STEP_KEEP,
    _EXTERNAL_MODEL_TOOL_NAMES,
    _LOOP_GUARD_TOOL_NAMES,
    _MISSING_FIELD_HINTS,
    _MISSING_SIGNAL_RE,
    _RESULT_STATUS_VALUES,
    _SUBAGENT_ARTIFACT_RE,
    TOOL_CONTEXT_DROP_KEYS,
    TOOL_CONTEXT_MAX_ITEMS,
)
from app.agents.new_chat.supervisor_routing import (
    _has_strict_trafik_intent,
    _looks_complete_unavailability_answer,
    _normalize_agent_identifier,
    _normalize_route_hint_value,
)
from app.agents.new_chat.supervisor_state_utils import _tool_call_name_index
from app.agents.new_chat.supervisor_text_utils import (
    _safe_json,
    _strip_critic_json,
    _truncate_for_prompt,
)

logger = logging.getLogger(__name__)


# ── Tool-call analysis & prioritization ──────────────────────────────


def _infer_tool_name_from_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    if "agent" in payload and "task" in payload and "result_contract" in payload:
        return "call_agent"
    if isinstance(payload.get("results"), list):
        return "call_agents_parallel"
    if "todos" in payload:
        return "write_todos"
    if "reflection" in payload:
        return "reflect_on_progress"
    return ""


def _resolve_tool_message_name(
    message: ToolMessage,
    *,
    tool_call_index: dict[str, str] | None = None,
) -> str:
    explicit_name = str(getattr(message, "name", "") or "").strip()
    if explicit_name:
        return explicit_name
    tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
    if tool_call_id and tool_call_index:
        indexed_name = str(tool_call_index.get(tool_call_id) or "").strip()
        if indexed_name:
            return indexed_name
    payload_name = _infer_tool_name_from_payload(
        _safe_json(getattr(message, "content", ""))
    )
    return payload_name


def _tool_call_priority(
    tool_name: str,
    *,
    orchestration_phase: str,
    agent_hops: int,
    execution_strategy: str = "",
    state: dict[str, Any] | None = None,
) -> int:
    normalized_tool = str(tool_name or "").strip()
    phase = str(orchestration_phase or "").strip().lower()
    strategy = str(execution_strategy or "").strip().lower()
    selected_agents_present = bool(_selected_agent_names_from_state(state))
    pending_plan_steps = _has_followup_plan_steps(state)
    if strategy in {"parallel", "subagent"}:
        preferred = {
            "call_agents_parallel": 0,
            "call_agent": 1,
            "retrieve_agents": 2,
            "write_todos": 3,
            "reflect_on_progress": 4,
        }
        if normalized_tool in _EXTERNAL_MODEL_TOOL_NAMES:
            return 5
        return preferred.get(normalized_tool, 99)
    prefer_retrieval = (
        phase == "select_agent" and not selected_agents_present and agent_hops <= 0
    ) or (
        phase in {"execute", "resolve_tools", "validate_agent_output"}
        and not selected_agents_present
        and not pending_plan_steps
        and agent_hops <= 0
    )
    if prefer_retrieval:
        ordering = {
            "retrieve_agents": 0,
            "call_agent": 1,
            "call_agents_parallel": 2,
            "write_todos": 3,
            "reflect_on_progress": 4,
        }
    else:
        ordering = {
            "call_agent": 0,
            "call_agents_parallel": 1,
            "retrieve_agents": 2,
            "write_todos": 3,
            "reflect_on_progress": 4,
        }
    if normalized_tool in _EXTERNAL_MODEL_TOOL_NAMES:
        return 5
    return ordering.get(normalized_tool, 99)


# ── Plan & followup tracking ─────────────────────────────────────────


def _has_followup_plan_steps(state: dict[str, Any] | None) -> bool:
    if not isinstance(state, dict):
        return False
    if bool(state.get("plan_complete")):
        return False
    plan_items = state.get("active_plan") or []
    if not isinstance(plan_items, list) or not plan_items:
        return False
    try:
        step_index = int(state.get("plan_step_index") or 0)
    except (TypeError, ValueError):
        step_index = 0
    step_index = max(0, step_index)
    for idx, item in enumerate(plan_items):
        if idx < step_index:
            continue
        if not isinstance(item, dict):
            return True
        status = str(item.get("status") or "").strip().lower()
        if status not in {"completed", "cancelled", "done"}:
            return True
    if step_index < len(plan_items):
        # Defensive fallback when plan statuses are missing or stale.
        return True
    return False


def _projected_followup_plan_steps(
    *,
    state: dict[str, Any],
    active_plan: list[dict[str, Any]] | None,
    plan_complete: bool | None,
    completed_steps_count: int,
) -> bool:
    projected_plan = (
        [item for item in (active_plan or []) if isinstance(item, dict)]
        if isinstance(active_plan, list)
        else [
            item for item in (state.get("active_plan") or []) if isinstance(item, dict)
        ]
    )
    projected_complete = (
        bool(plan_complete)
        if plan_complete is not None
        else bool(state.get("plan_complete"))
    )
    projected_step_index = min(
        max(0, int(completed_steps_count)),
        len(projected_plan),
    )
    return _has_followup_plan_steps(
        {
            "active_plan": projected_plan,
            "plan_complete": projected_complete,
            "plan_step_index": projected_step_index,
        }
    )


# ── State extraction ─────────────────────────────────────────────────


def _selected_agent_names_from_state(state: dict[str, Any] | None) -> list[str]:
    if not isinstance(state, dict):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for item in state.get("selected_agents") or []:
        if isinstance(item, dict):
            normalized = str(item.get("name") or "").strip().lower()
        else:
            normalized = str(item or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(normalized)
    return names


def _next_plan_step_text(state: dict[str, Any] | None) -> str:
    if not isinstance(state, dict):
        return ""
    plan_items = state.get("active_plan") or []
    if not isinstance(plan_items, list) or not plan_items:
        return ""
    try:
        step_index = int(state.get("plan_step_index") or 0)
    except (TypeError, ValueError):
        step_index = 0
    step_index = max(0, step_index)
    for idx, item in enumerate(plan_items):
        if idx < step_index:
            continue
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        status = str(item.get("status") or "pending").strip().lower()
        if not content:
            continue
        if status in {"completed", "cancelled", "done"}:
            continue
        return content
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if content:
            return content
    return ""


def _latest_user_query(messages: list[Any] | None) -> str:
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return str(getattr(message, "content", "") or "").strip()
    return ""


def _tool_names_from_messages(messages: list[Any] | None) -> list[str]:
    names: list[str] = []
    tool_call_index = _tool_call_name_index(messages)
    for message in messages or []:
        if not isinstance(message, ToolMessage):
            continue
        name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if name and name not in names:
            names.append(name)
    return names


def _all_tool_data_empty(messages: list[Any] | None) -> bool:
    """Return True when every ToolMessage with JSON content had empty ``data``.

    This catches the scenario where external APIs (SCB, Riksbank, etc.)
    return ``{"status": "success", "data": {}}`` — the call itself succeeded
    but no actual data was found.  When *all* tool outputs are data-empty
    the worker LLM has nothing to ground its answer on, so the contract
    should NOT be marked as ``success``/``actionable``.

    Returns False (safe default) when there are no tool messages or when at
    least one tool returned non-empty data.
    """
    import json as _json

    data_tool_count = 0
    empty_count = 0
    for msg in messages or []:
        if not isinstance(msg, ToolMessage):
            continue
        raw = str(getattr(msg, "content", "") or "").strip()
        if not raw or raw.startswith("[") or len(raw) < 10:
            continue
        # Skip meta-tools (retrieve_tools, reflect_on_progress, etc.)
        tool_name = str(getattr(msg, "name", "") or "").strip().lower()
        if tool_name in {
            "retrieve_tools",
            "retrieve_tools_noop",
            "reflect_on_progress",
            "call_agent",
            "call_agents_parallel",
        }:
            continue
        try:
            parsed = _json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        # Only check data-bearing tool results (must have "data" key)
        if "data" not in parsed:
            continue
        data_tool_count += 1
        data_field = parsed["data"]
        if isinstance(data_field, dict) and not data_field:
            empty_count += 1
        elif isinstance(data_field, list) and not data_field:
            empty_count += 1
    return data_tool_count > 0 and empty_count == data_tool_count


# ── Tool-call coercion ────────────────────────────────────────────────

# Kept at module level so supervisor_agent.py can reference them.
_MAX_SUPERVISOR_TOOL_CALLS_PER_STEP = 1


def _coerce_redundant_retrieve_call(
    tool_calls: list[dict[str, Any]],
    *,
    orchestration_phase: str,
    state: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(state, dict):
        return tool_calls, False
    phase = str(orchestration_phase or "").strip().lower()
    if phase not in {"execute", "resolve_tools", "validate_agent_output"}:
        return tool_calls, False
    if len(tool_calls) != 1:
        return tool_calls, False
    only_call = tool_calls[0]
    if str(only_call.get("name") or "").strip() != "retrieve_agents":
        return tool_calls, False
    if str(_normalize_route_hint_value(state.get("route_hint")) or "") in {
        "jämförelse",
        "compare",
    }:
        return tool_calls, False
    selected_agents = _selected_agent_names_from_state(state)
    if len(selected_agents) != 1:
        return tool_calls, False
    has_pending_plan_steps = _has_followup_plan_steps(state)
    graph_complexity = str(state.get("graph_complexity") or "").strip().lower()
    simple_single_agent_turn = graph_complexity == "simple"
    if not has_pending_plan_steps and not simple_single_agent_turn:
        return tool_calls, False
    call_args = only_call.get("args")
    retrieve_query = (
        str(call_args.get("query") or "").strip() if isinstance(call_args, dict) else ""
    )
    task_text = _latest_user_query(state.get("messages") or [])
    if not task_text:
        task_text = _next_plan_step_text(state)
    if not task_text:
        task_text = retrieve_query
    if not task_text:
        return tool_calls, False
    coerced_call = dict(only_call)
    coerced_call["name"] = "call_agent"
    coerced_call["args"] = {
        "agent_name": selected_agents[0],
        "task": task_text,
        "final": False,
    }
    return [coerced_call], True


def _coerce_supervisor_tool_calls(
    message: Any,
    *,
    orchestration_phase: str,
    agent_hops: int,
    execution_strategy: str,
    allow_multiple: bool,
    state: dict[str, Any] | None = None,
) -> Any:
    if allow_multiple or not isinstance(message, AIMessage):
        return message
    tool_calls = [
        tool_call
        for tool_call in (getattr(message, "tool_calls", None) or [])
        if isinstance(tool_call, dict)
    ]
    coerce_final = _has_followup_plan_steps(state)
    changed = False
    if coerce_final and tool_calls:
        coerced_tool_calls: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            if str(tool_call.get("name") or "").strip() != "call_agent":
                coerced_tool_calls.append(tool_call)
                continue
            raw_args = tool_call.get("args")
            if not isinstance(raw_args, dict) or not bool(raw_args.get("final")):
                coerced_tool_calls.append(tool_call)
                continue
            coerced_args = dict(raw_args)
            coerced_args["final"] = False
            coerced_call = dict(tool_call)
            coerced_call["args"] = coerced_args
            coerced_tool_calls.append(coerced_call)
            changed = True
        if changed:
            tool_calls = coerced_tool_calls
    tool_calls, retrieve_changed = _coerce_redundant_retrieve_call(
        tool_calls,
        orchestration_phase=orchestration_phase,
        state=state,
    )
    changed = changed or retrieve_changed
    if len(tool_calls) <= _MAX_SUPERVISOR_TOOL_CALLS_PER_STEP:
        if not changed:
            return message
        try:
            return message.model_copy(update={"tool_calls": tool_calls})
        except Exception:
            return AIMessage(
                content=str(getattr(message, "content", "") or ""),
                tool_calls=tool_calls,
                additional_kwargs=dict(getattr(message, "additional_kwargs", {}) or {}),
                response_metadata=dict(getattr(message, "response_metadata", {}) or {}),
                id=getattr(message, "id", None),
            )
    ranked = sorted(
        enumerate(tool_calls),
        key=lambda item: (
            _tool_call_priority(
                str(item[1].get("name") or ""),
                orchestration_phase=orchestration_phase,
                agent_hops=agent_hops,
                execution_strategy=execution_strategy,
                state=state,
            ),
            item[0],
        ),
    )
    chosen_call = ranked[0][1]
    try:
        return message.model_copy(update={"tool_calls": [chosen_call]})
    except Exception:
        return AIMessage(
            content=str(getattr(message, "content", "") or ""),
            tool_calls=[chosen_call],
            additional_kwargs=dict(getattr(message, "additional_kwargs", {}) or {}),
            response_metadata=dict(getattr(message, "response_metadata", {}) or {}),
            id=getattr(message, "id", None),
        )


# ── Tool schema sanitization ─────────────────────────────────────────


def _sanitize_openai_tool_schema(value: Any) -> Any:
    """
    Remove null defaults/variants from tool schemas for strict Jinja templates.
    LM Studio templates can fail on `default: null` or explicit `type: null`.

    ``description`` fields are preserved with an empty string rather than
    dropped -- the nemotron-3-nano Jinja template accesses
    ``tool.function.description | string`` unconditionally.  A missing key
    resolves to NullValue in LM Studio's Jinja engine, crashing the template.
    """
    _KEEP_AS_EMPTY_STRING = {"description"}

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if item is None:
                if key in _KEEP_AS_EMPTY_STRING:
                    sanitized[key] = ""
                continue
            if key == "default" and item is None:
                continue
            if key in {"anyOf", "oneOf", "allOf"} and isinstance(item, list):
                variants: list[Any] = []
                for variant in item:
                    cleaned_variant = _sanitize_openai_tool_schema(variant)
                    if (
                        isinstance(cleaned_variant, dict)
                        and str(cleaned_variant.get("type") or "").strip().lower()
                        == "null"
                    ):
                        continue
                    variants.append(cleaned_variant)
                if variants:
                    sanitized[key] = variants
                continue
            sanitized[key] = _sanitize_openai_tool_schema(item)

        properties = sanitized.get("properties")
        required = sanitized.get("required")
        required_set = {
            str(field).strip()
            for field in (required if isinstance(required, list) else [])
            if str(field).strip()
        }
        if isinstance(properties, dict):
            cleaned_properties: dict[str, Any] = {}
            for prop_name, prop_schema in properties.items():
                normalized_name = str(prop_name or "").strip()
                # Injected state must not be in the model-facing schema.
                if normalized_name == "state":
                    continue
                cleaned_schema = _sanitize_openai_tool_schema(prop_schema)
                if isinstance(cleaned_schema, dict):
                    if (
                        "default" not in cleaned_schema
                        and normalized_name not in required_set
                    ):
                        inferred_default = _infer_non_null_tool_default(cleaned_schema)
                        if inferred_default is not None:
                            cleaned_schema["default"] = inferred_default
                cleaned_properties[normalized_name] = cleaned_schema
            sanitized["properties"] = cleaned_properties
            properties = cleaned_properties

        if isinstance(required, list) and isinstance(properties, dict):
            kept_required = [
                str(field).strip()
                for field in required
                if isinstance(field, str) and str(field).strip() in properties
            ]
            if kept_required:
                sanitized["required"] = kept_required
            else:
                sanitized.pop("required", None)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_openai_tool_schema(item) for item in value]
    return value


def _infer_non_null_tool_default(schema: dict[str, Any]) -> Any:
    type_name = str(schema.get("type") or "").strip().lower()
    if type_name == "boolean":
        return False
    if type_name == "string":
        return ""
    if type_name == "integer":
        return 0
    if type_name == "number":
        return 0
    if type_name == "array":
        return []
    if type_name == "object":
        return {}

    for union_key in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(union_key)
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            inferred = _infer_non_null_tool_default(variant)
            if inferred is not None:
                return inferred
    return None


def _format_tools_for_llm_binding(tools: list[Any]) -> list[dict[str, Any]]:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    formatted: list[dict[str, Any]] = []
    for tool_def in tools:
        try:
            raw = (
                tool_def
                if isinstance(tool_def, dict)
                else convert_to_openai_tool(tool_def)
            )
        except Exception:
            logger.debug("Failed to convert tool for llm binding", exc_info=True)
            continue
        cleaned = _sanitize_openai_tool_schema(raw)
        if isinstance(cleaned, dict):
            # Guarantee that function.description always exists -- strict Jinja
            # templates (nemotron-3-nano) access it without null guards.
            func = cleaned.get("function")
            if isinstance(func, dict) and "description" not in func:
                func["description"] = ""
            formatted.append(cleaned)
    return formatted


# ── Guard & response analysis ─────────────────────────────────────────


def _render_guard_message(template: str, preview_lines: list[str]) -> str:
    preview_block = ""
    if preview_lines:
        preview_block = "Detta ar de senaste delresultaten:\n" + "\n".join(
            [str(item) for item in preview_lines[:3] if str(item).strip()]
        )
    try:
        rendered = str(template or "").format(recent_preview=preview_block)
    except Exception:
        rendered = str(template or "")
    rendered = rendered.strip()
    if preview_block and "{recent_preview}" not in str(template or ""):
        if preview_block not in rendered:
            rendered = (rendered + "\n" + preview_block).strip()
    return rendered


def _current_turn_key(state: dict[str, Any] | None) -> str:
    if not state:
        return "turn"
    active_turn_id = str(
        state.get("active_turn_id") or state.get("turn_id") or ""
    ).strip()
    if active_turn_id:
        digest = hashlib.sha1(active_turn_id.encode("utf-8")).hexdigest()
        return f"t{digest[:12]}"
    messages = state.get("messages") or []
    latest_human: HumanMessage | None = None
    human_count = 0
    for message in messages:
        if isinstance(message, HumanMessage):
            human_count += 1
            latest_human = message
    if latest_human is not None:
        message_id = str(getattr(latest_human, "id", "") or "").strip()
        content = str(getattr(latest_human, "content", "") or "").strip()
        seed = message_id or content or f"human:{human_count}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
        return f"h{human_count}:{digest[:12]}"
    return "turn"


def _infer_missing_fields(response_text: str) -> list[str]:
    text = str(response_text or "").strip().lower()
    if not text or not _MISSING_SIGNAL_RE.search(text):
        return []
    missing: list[str] = []
    for field_name, hints in _MISSING_FIELD_HINTS:
        if any(hint in text for hint in hints):
            missing.append(field_name)
    return missing[:6]


def _looks_blocked_agent_response(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _BLOCKED_RESPONSE_MARKERS)


def _normalize_result_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in _RESULT_STATUS_VALUES:
        return status
    return "partial"


# ── Agent result contracts ────────────────────────────────────────────


def _compute_contract_confidence(
    *,
    status: str,
    response_text: str,
    actionable: bool,
    missing_fields: list[str],
    used_tool_count: int,
    final_requested: bool,
) -> float:
    base = 0.45
    if status == "success":
        base = 0.78
    elif status == "blocked":
        base = 0.24
    elif status == "error":
        base = 0.08

    if actionable:
        base += 0.08
    if used_tool_count > 0:
        base += 0.05
    if used_tool_count >= 2:
        base += 0.03

    response_len = len(str(response_text or "").strip())
    if response_len >= 200:
        base += 0.05
    elif response_len < 40:
        base -= 0.10

    if missing_fields:
        base -= min(0.24, 0.08 * len(missing_fields))
    if final_requested and status == "success":
        base += 0.03

    base = max(0.01, min(0.99, base))
    return round(float(base), 2)


def _build_agent_result_contract(
    *,
    agent_name: str,
    task: str,
    response_text: str,
    error_text: str = "",
    used_tools: list[str] | None = None,
    final_requested: bool = False,
) -> dict[str, Any]:
    cleaned_response = _strip_critic_json(str(response_text or "").strip())
    error_value = str(error_text or "").strip()
    used_tool_names = [
        str(item).strip() for item in (used_tools or []) if str(item).strip()
    ]
    missing_fields = _infer_missing_fields(cleaned_response)
    actionable = _looks_actionable_agent_answer(cleaned_response)
    blocked = _looks_blocked_agent_response(cleaned_response)
    complete_unavailable = _looks_complete_unavailability_answer(cleaned_response)

    if error_value:
        status = "error"
    elif not cleaned_response:
        status = "partial"
    elif complete_unavailable:
        status = "success"
        actionable = True
    elif blocked and not actionable:
        status = "blocked"
    elif missing_fields and not actionable:
        status = "partial"
    elif actionable:
        status = "success"
    else:
        status = "partial"

    confidence = _compute_contract_confidence(
        status=status,
        response_text=cleaned_response,
        actionable=actionable,
        missing_fields=missing_fields,
        used_tool_count=len(used_tool_names),
        final_requested=bool(final_requested),
    )
    retry_recommended = status in {"partial", "blocked", "error"}
    if status == "success" and confidence < 0.55:
        retry_recommended = True

    if status == "error":
        reason = (
            f"Agentfel: {error_value[:140]}"
            if error_value
            else "Agentkorningen misslyckades."
        )
    elif status == "blocked":
        reason = "Svar saknar tillrackligt underlag eller kraver annan agent."
    elif status == "partial":
        if missing_fields:
            reason = "Saknade falt: " + ", ".join(missing_fields[:4])
        else:
            reason = "Svar finns men bedoms inte komplett nog for finalisering."
    else:
        reason = "Svar bedoms tillrackligt komplett for finalisering."

    return {
        "status": status,
        "confidence": confidence,
        "actionable": bool(actionable),
        "missing_fields": missing_fields,
        "retry_recommended": bool(retry_recommended),
        "used_tools": used_tool_names[:6],
        "reason": reason,
        "agent": str(agent_name or "").strip(),
        "task_hash": hashlib.sha1(str(task or "").encode("utf-8")).hexdigest()[:12],
    }


def _contract_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    raw_contract = source.get("result_contract")
    if isinstance(raw_contract, dict):
        normalized_status = _normalize_result_status(raw_contract.get("status"))
        try:
            confidence = float(raw_contract.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = round(max(0.0, min(1.0, confidence)), 2)
        missing_fields_raw = raw_contract.get("missing_fields")
        missing_fields = (
            [str(item).strip() for item in missing_fields_raw if str(item).strip()][:6]
            if isinstance(missing_fields_raw, list)
            else []
        )
        used_tools_raw = raw_contract.get("used_tools")
        used_tools = (
            [str(item).strip() for item in used_tools_raw if str(item).strip()][:6]
            if isinstance(used_tools_raw, list)
            else []
        )
        reason = str(raw_contract.get("reason") or "").strip()
        if not reason:
            reason = "Resultatkontrakt utan forklaring."
        if confidence <= 0.0 and (
            str(source.get("response") or "").strip()
            or str(source.get("error") or "").strip()
        ):
            fallback = _build_agent_result_contract(
                agent_name=str(source.get("agent") or ""),
                task=str(source.get("task") or ""),
                response_text=str(source.get("response") or ""),
                error_text=str(source.get("error") or ""),
                used_tools=used_tools,
                final_requested=bool(source.get("final")),
            )
            confidence = float(fallback.get("confidence") or confidence)
            if normalized_status == "partial":
                normalized_status = _normalize_result_status(fallback.get("status"))
            if not missing_fields:
                missing_fields = list(fallback.get("missing_fields") or [])
            if not reason:
                reason = str(fallback.get("reason") or "").strip()
        return {
            "status": normalized_status,
            "confidence": confidence,
            "actionable": bool(raw_contract.get("actionable")),
            "missing_fields": missing_fields,
            "retry_recommended": bool(raw_contract.get("retry_recommended")),
            "used_tools": used_tools,
            "reason": reason,
            "agent": str(
                raw_contract.get("agent") or source.get("agent") or ""
            ).strip(),
            "task_hash": str(raw_contract.get("task_hash") or "").strip(),
        }

    fallback_tools = source.get("used_tools")
    fallback_tool_list = (
        [str(item).strip() for item in fallback_tools if str(item).strip()]
        if isinstance(fallback_tools, list)
        else []
    )
    return _build_agent_result_contract(
        agent_name=str(source.get("agent") or ""),
        task=str(source.get("task") or ""),
        response_text=str(source.get("response") or ""),
        error_text=str(source.get("error") or ""),
        used_tools=fallback_tool_list,
        final_requested=bool(source.get("final")),
    )


def _should_finalize_from_contract(
    *,
    contract: dict[str, Any],
    response_text: str,
    route_hint: str,
    agent_name: str,
    latest_user_query: str,
    agent_hops: int,
) -> bool:
    response = _strip_critic_json(str(response_text or "").strip())
    if not response:
        return False
    if str(route_hint or "").strip().lower() in {"jämförelse", "compare"}:
        return False

    status = _normalize_result_status(contract.get("status"))
    actionable = bool(contract.get("actionable"))
    try:
        confidence = float(contract.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    missing_fields = contract.get("missing_fields")
    missing_count = len(missing_fields) if isinstance(missing_fields, list) else 0

    if status == "success" and actionable and confidence >= 0.55 and missing_count <= 1:
        return True

    normalized_agent = str(agent_name or "").strip().lower()
    if (
        str(route_hint or "").strip().lower() in {"action", "skapande"}
        and normalized_agent.startswith("trafik-")
        and _has_strict_trafik_intent(latest_user_query)
        and actionable
        and status in {"success", "partial"}
        and confidence >= 0.45
        and missing_count <= 1
    ):
        return True

    if (
        agent_hops >= 2
        and actionable
        and status in {"success", "partial"}
        and confidence >= 0.60
        and missing_count == 0
    ):
        return True
    return False


# ── Agent call tracking & analysis ────────────────────────────────────


def _normalize_task_for_fingerprint(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    value = re.sub(r"[^a-z0-9åäö\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180]


def _agent_call_entries_since_last_user(
    messages: list[Any] | None,
    *,
    turn_id: str | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    expected_turn_id = str(turn_id or "").strip()
    tool_call_index = _tool_call_name_index(messages)
    for message in messages or []:
        if isinstance(message, HumanMessage):
            entries = []
            continue
        if not isinstance(message, ToolMessage):
            continue
        resolved_name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if resolved_name != "call_agent":
            continue
        payload = _safe_json(getattr(message, "content", ""))
        if not isinstance(payload, dict):
            continue
        payload_turn_id = str(payload.get("turn_id") or "").strip()
        if expected_turn_id and payload_turn_id != expected_turn_id:
            continue
        entries.append(payload)
    return entries


def _looks_actionable_agent_answer(text: str) -> bool:
    value = str(text or "").strip()
    if len(value) < 32:
        return False
    lowered = value.lower()
    rejection_markers = (
        "jag kan inte",
        "jag kunde inte",
        "kan tyvarr inte",
        "kan tyvärr inte",
        "jag saknar",
        "jag behover",
        "jag behöver",
        "behover mer information",
        "behöver mer information",
        "inte möjligt",
        "not available",
        "cannot answer",
        "specificera",
        "ange mer",
    )
    if "inga " in lowered and (
        "hittades" in lowered or "fanns" in lowered or "rapporterades" in lowered
    ):
        return True
    return not any(marker in lowered for marker in rejection_markers)


def _query_requests_capability_overview(query: str) -> bool:
    lowered = str(query or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "vad kan du",
        "vad kan ni",
        "what can you do",
        "what are your capabilities",
        "vilka verktyg har du",
        "vad hjälper du med",
        "vad kan oneseek",
    )
    return any(marker in lowered for marker in markers)


def _is_generic_capability_answer(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "jag kan hjälpa dig med olika uppgifter",
        "här är några exempel på vad jag kan göra",
        "vill du ha hjälp med något specifikt",
        "i can help you with different tasks",
        "here are some examples of what i can do",
    )
    return any(marker in lowered for marker in markers)


def _latest_actionable_ai_response(
    messages: list[Any],
    *,
    latest_user_query: str,
) -> str | None:
    allow_capability_response = _query_requests_capability_overview(latest_user_query)
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, AIMessage):
            continue
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            continue
        response = _strip_critic_json(
            str(getattr(message, "content", "") or "").strip()
        )
        if not response:
            continue
        lowered = response.lower()
        if "jag fastnade i en planeringsloop" in lowered:
            continue
        if _is_generic_capability_answer(response) and not allow_capability_response:
            continue
        if _looks_actionable_agent_answer(response) or allow_capability_response:
            return response
    return None


# ── Agent result ranking ──────────────────────────────────────────────


def _best_actionable_entry(entries: list[dict[str, Any]]) -> tuple[str, str] | None:
    best: tuple[tuple[int, int, float, int], tuple[str, str]] | None = None
    status_rank = {"success": 3, "partial": 2, "blocked": 1, "error": 0}
    for entry in entries:
        response = _strip_critic_json(str(entry.get("response") or "").strip())
        if not response:
            continue
        contract = _contract_from_payload(entry)
        status = _normalize_result_status(contract.get("status"))
        actionable = bool(contract.get("actionable")) or _looks_actionable_agent_answer(
            response
        )
        try:
            confidence = float(contract.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        score = (
            1 if actionable else 0,
            status_rank.get(status, 0),
            confidence,
            len(response),
        )
        agent_name = str(entry.get("agent") or "").strip() or "agent"
        if best is None or score > best[0]:
            best = (score, (response, agent_name))
    if best:
        return best[1]
    return None


# ── Subagent orchestration ────────────────────────────────────────────


def _build_subagent_id(
    *,
    base_thread_id: str,
    turn_key: str,
    agent_name: str,
    call_index: int,
    task: str,
) -> str:
    seed = "|".join(
        [
            str(base_thread_id or "").strip() or "thread",
            str(turn_key or "").strip() or "turn",
            str(agent_name or "").strip().lower() or "agent",
            str(max(0, int(call_index))),
            hashlib.sha1(str(task or "").encode("utf-8")).hexdigest()[:10],
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]
    agent_slug = _normalize_agent_identifier(agent_name) or "agent"
    return f"sa-{agent_slug[:18]}-{digest}"


def _extract_subagent_artifact_refs(text: str, *, limit: int = 4) -> list[str]:
    if not text:
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for match in _SUBAGENT_ARTIFACT_RE.findall(str(text or "")):
        normalized = str(match or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        refs.append(normalized)
        if len(refs) >= max(1, int(limit)):
            break
    return refs


def _build_subagent_handoff_payload(
    *,
    subagent_id: str,
    agent_name: str,
    response_text: str,
    result_contract: dict[str, Any] | None,
    result_max_chars: int,
    error_text: str = "",
) -> dict[str, Any]:
    contract = result_contract if isinstance(result_contract, dict) else {}
    response = _strip_critic_json(str(response_text or "").strip())
    summary = _truncate_for_prompt(response, max(180, int(result_max_chars)))
    findings: list[str] = []
    for line in response.splitlines():
        cleaned = str(line or "").strip(" -*")
        if not cleaned:
            continue
        findings.append(_truncate_for_prompt(cleaned, 180))
        if len(findings) >= 4:
            break
    if not findings and summary:
        findings = [_truncate_for_prompt(summary, 180)]
    status = _normalize_result_status(contract.get("status"))
    try:
        confidence = float(contract.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "subagent_id": str(subagent_id or "").strip(),
        "agent": str(agent_name or "").strip(),
        "status": status,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "summary": summary,
        "findings": findings,
        "artifact_refs": _extract_subagent_artifact_refs(response),
        "error": _truncate_for_prompt(str(error_text or "").strip(), 240),
    }


# ── Result aggregation & summarization ────────────────────────────────


def _summarize_parallel_results(results: Any) -> str:
    if not isinstance(results, list) or not results:
        return "results=0"
    success_count = 0
    error_count = 0
    snippets: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        response = str(item.get("response") or "").strip()
        error = str(item.get("error") or "").strip()
        if error:
            error_count += 1
        elif response:
            success_count += 1
    for item in results[:TOOL_CONTEXT_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "agent").strip() or "agent"
        response = _strip_critic_json(str(item.get("response") or "").strip())
        error = str(item.get("error") or "").strip()
        if response:
            snippets.append(f"{agent}: {_truncate_for_prompt(response, 140)}")
        elif error:
            snippets.append(f"{agent}: error {_truncate_for_prompt(error, 100)}")
        else:
            snippets.append(f"{agent}: completed")
    summary = f"results={len(results)}; success={success_count}; errors={error_count}"
    if snippets:
        summary += "; outputs=" + " | ".join(snippets)
    return _truncate_for_prompt(summary)


def _build_rolling_context_summary(
    *,
    latest_user_query: str,
    active_plan: list[dict[str, Any]] | None,
    step_results: list[dict[str, Any]] | None,
    subagent_handoffs: list[dict[str, Any]] | None,
    artifact_manifest: list[dict[str, Any]] | None,
    targeted_missing_info: list[str] | None,
    max_chars: int,
) -> str:
    lines: list[str] = []
    user_query = str(latest_user_query or "").strip()
    if user_query:
        lines.append(f"User goal: {_truncate_for_prompt(user_query, 260)}")

    plan_items = [item for item in (active_plan or []) if isinstance(item, dict)]
    if plan_items:
        pending = [
            str(item.get("content") or "").strip()
            for item in plan_items
            if str(item.get("status") or "").strip().lower()
            in {"pending", "in_progress"}
            and str(item.get("content") or "").strip()
        ][:3]
        completed_count = sum(
            1
            for item in plan_items
            if str(item.get("status") or "").strip().lower() == "completed"
        )
        lines.append(f"Plan status: completed={completed_count}/{len(plan_items)}")
        if pending:
            lines.append("Next steps: " + " | ".join(pending))

    compact_steps: list[str] = []
    for item in (step_results or [])[-_CONTEXT_COMPACTION_DEFAULT_STEP_KEEP:]:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "agent").strip() or "agent"
        task = _truncate_for_prompt(str(item.get("task") or "").strip(), 100)
        response = _truncate_for_prompt(
            _strip_critic_json(str(item.get("response") or "").strip()),
            180,
        )
        contract = item.get("result_contract")
        status = (
            _normalize_result_status(contract.get("status"))
            if isinstance(contract, dict)
            else "partial"
        )
        if response:
            compact_steps.append(f"- {agent} [{status}] {task} -> {response}")
    if compact_steps:
        lines.append("Recent execution:")
        lines.extend(compact_steps[:6])

    handoff_lines: list[str] = []
    for handoff in (subagent_handoffs or [])[-4:]:
        if not isinstance(handoff, dict):
            continue
        agent = str(handoff.get("agent") or "agent").strip() or "agent"
        summary = _truncate_for_prompt(str(handoff.get("summary") or "").strip(), 160)
        refs = handoff.get("artifact_refs")
        ref_text = ""
        if isinstance(refs, list):
            normalized = [str(item).strip() for item in refs if str(item).strip()][:2]
            if normalized:
                ref_text = f" refs={','.join(normalized)}"
        if summary:
            handoff_lines.append(f"- {agent}: {summary}{ref_text}")
    if handoff_lines:
        lines.append("Subagent handoffs:")
        lines.extend(handoff_lines)

    artifact_lines: list[str] = []
    for item in (artifact_manifest or [])[-4:]:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("artifact_uri") or item.get("artifact_path") or "").strip()
        if not ref:
            continue
        summary = _truncate_for_prompt(str(item.get("summary") or "").strip(), 140)
        if summary:
            artifact_lines.append(f"- {ref}: {summary}")
        else:
            artifact_lines.append(f"- {ref}")
    if artifact_lines:
        lines.append("Artifacts:")
        lines.extend(artifact_lines)

    missing = [
        str(item).strip() for item in (targeted_missing_info or []) if str(item).strip()
    ]
    if missing:
        lines.append("Open gaps: " + " | ".join(missing[:4]))

    rendered = "\n".join(lines).strip()
    return _truncate_for_prompt(rendered, max(320, int(max_chars)))


# ── Loop detection & tool counting ────────────────────────────────────


def _count_consecutive_loop_tools(
    messages: list[Any], *, turn_id: str | None = None
) -> int:
    count = 0
    expected_turn_id = str(turn_id or "").strip()
    tool_call_index = _tool_call_name_index(messages)
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, ToolMessage):
            continue
        name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if name == "call_agent":
            payload = _safe_json(getattr(message, "content", ""))
            payload_turn_id = (
                str(payload.get("turn_id") or "").strip()
                if isinstance(payload, dict)
                else ""
            )
            if expected_turn_id and payload_turn_id != expected_turn_id:
                break
            if isinstance(payload, dict) and str(payload.get("error") or "").strip():
                count += 1
                continue
            contract = _contract_from_payload(
                payload if isinstance(payload, dict) else {}
            )
            status = _normalize_result_status(contract.get("status"))
            actionable = bool(contract.get("actionable"))
            try:
                confidence = float(contract.get("confidence"))
            except (TypeError, ValueError):
                confidence = 0.0
            if status == "success" and actionable and confidence >= 0.55:
                break
            if bool(contract.get("retry_recommended")) or status in {
                "partial",
                "blocked",
                "error",
            }:
                count += 1
                continue
            break
        if name in _LOOP_GUARD_TOOL_NAMES:
            count += 1
            continue
        break
    return count


def _count_consecutive_same_direct_tool(messages: list[Any]) -> tuple[int, str]:
    """Count consecutive calls to the same *direct* tool since the last HumanMessage.

    Returns (count, tool_name).  For example if the last 3 ToolMessage results
    are all from ``scb_befolkning``, returns ``(3, "scb_befolkning")``.

    Only counts non-agent tools (i.e. not ``call_agent``, ``retrieve_agents``,
    ``reflect_on_progress``, ``write_todos``).  These have their own guards.
    """
    skip = {"call_agent", "retrieve_agents", "reflect_on_progress", "write_todos"}
    tool_call_index = _tool_call_name_index(messages)
    last_name: str = ""
    count = 0
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, ToolMessage):
            continue
        name = _resolve_tool_message_name(message, tool_call_index=tool_call_index)
        if name in skip:
            # Agent-level calls are guarded separately.
            break
        if not last_name:
            last_name = name
        if name == last_name:
            count += 1
        else:
            break
    return count, last_name


# ── Tool payload summarization ────────────────────────────────────────


def _summarize_tool_payload(tool_name: str, payload: dict[str, Any]) -> str:
    name = (tool_name or "tool").strip() or "tool"
    status = str(payload.get("status") or "completed").lower()
    parts: list[str] = [f"{name}: {status}"]

    if status == "error" or "error" in payload:
        error_text = _truncate_for_prompt(
            str(payload.get("error") or "Unknown error"), 300
        )
        return _truncate_for_prompt(f"{name}: error - {error_text}")

    if name == "write_todos":
        todos = payload.get("todos") or []
        if isinstance(todos, list):
            completed = sum(
                1
                for item in todos
                if isinstance(item, dict)
                and str(item.get("status") or "").lower() == "completed"
            )
            in_progress = sum(
                1
                for item in todos
                if isinstance(item, dict)
                and str(item.get("status") or "").lower() == "in_progress"
            )
            parts.append(f"todos={len(todos)}")
            parts.append(f"completed={completed}")
            parts.append(f"in_progress={in_progress}")
            task_names = [
                str(item.get("content") or "").strip()
                for item in todos
                if isinstance(item, dict) and str(item.get("content") or "").strip()
            ][:TOOL_CONTEXT_MAX_ITEMS]
            if task_names:
                parts.append("tasks=" + " | ".join(task_names))
            return _truncate_for_prompt("; ".join(parts))

    if name == "trafiklab_route":
        origin = payload.get("origin") or {}
        destination = payload.get("destination") or {}
        origin_name = ""
        destination_name = ""
        if isinstance(origin, dict):
            origin_name = str(
                (
                    (origin.get("stop_group") or {})
                    if isinstance(origin.get("stop_group"), dict)
                    else {}
                ).get("name")
                or origin.get("name")
                or ""
            ).strip()
        if isinstance(destination, dict):
            destination_name = str(
                (
                    (
                        (destination.get("stop_group") or {})
                        if isinstance(destination.get("stop_group"), dict)
                        else {}
                    ).get("name")
                    or destination.get("name")
                    or ""
                )
            ).strip()
        route_label = " -> ".join(
            [label for label in (origin_name, destination_name) if label]
        ).strip()
        if route_label:
            parts.append(f"route={route_label}")
        matches = payload.get("matching_entries")
        entries = payload.get("entries")
        if isinstance(matches, list):
            parts.append(f"matching_entries={len(matches)}")
        if isinstance(entries, list):
            parts.append(f"entries={len(entries)}")
        return _truncate_for_prompt("; ".join(parts))

    if name.startswith("smhi_"):
        location = payload.get("location") or {}
        location_name = ""
        if isinstance(location, dict):
            location_name = str(
                location.get("name") or location.get("display_name") or ""
            ).strip()
        if location_name:
            parts.append(f"location={location_name}")
        current = payload.get("current") or {}
        summary = current.get("summary") if isinstance(current, dict) else {}
        if isinstance(summary, dict):
            temperature = summary.get("temperature_c")
            if temperature is not None:
                parts.append(f"temperature_c={temperature}")
            wind = summary.get("wind_speed_mps")
            if wind is None:
                wind = summary.get("wind_speed_m_s")
            if wind is not None:
                parts.append(f"wind_mps={wind}")
        return _truncate_for_prompt("; ".join(parts))

    if name == "call_agents_parallel":
        return _truncate_for_prompt(
            f"{name}: {status}; {_summarize_parallel_results(payload.get('results'))}"
        )

    for key, value in payload.items():
        if key in {"status", "error"}:
            continue
        if key in TOOL_CONTEXT_DROP_KEYS:
            if isinstance(value, list):
                parts.append(f"{key}_count={len(value)}")
            elif isinstance(value, dict):
                parts.append(f"{key}_keys={len(value)}")
            elif value is not None:
                parts.append(f"{key}=present")
            continue
        if isinstance(value, (str, int, float, bool)):
            parts.append(f"{key}={_truncate_for_prompt(str(value), 180)}")
            continue
        if isinstance(value, list):
            parts.append(f"{key}_count={len(value)}")
            continue
        if isinstance(value, dict):
            parts.append(f"{key}_keys={len(value)}")
            continue
        if value is not None:
            parts.append(f"{key}=present")

    return _truncate_for_prompt("; ".join(parts))


# ── Message sanitization ──────────────────────────────────────────────


def _sanitize_messages(messages: list[Any]) -> list[Any]:
    sanitized: list[Any] = []
    tool_call_index = _tool_call_name_index(messages)
    for message in messages:
        if isinstance(message, ToolMessage):
            resolved_tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            payload = _safe_json(message.content)
            if payload:
                response = payload.get("response")
                if isinstance(response, str):
                    agent = payload.get("agent") or resolved_tool_name or "agent"
                    response = _strip_critic_json(response)
                    contract = _contract_from_payload(payload)
                    status = _normalize_result_status(contract.get("status"))
                    try:
                        confidence = float(contract.get("confidence"))
                    except (TypeError, ValueError):
                        confidence = 0.0
                    status_prefix = ""
                    if status != "success" or confidence < 0.7:
                        status_prefix = f"[{status} {confidence:.2f}] "
                    content = (
                        _truncate_for_prompt(f"{agent}: {status_prefix}{response}")
                        if response
                        else f"{agent}: completed"
                    )
                    sanitized.append(
                        ToolMessage(
                            content=content,
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                if payload.get("status") and payload.get("reason"):
                    tool_name = resolved_tool_name or "tool"
                    sanitized.append(
                        ToolMessage(
                            content=_truncate_for_prompt(f"{tool_name}: completed"),
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                summarized = _summarize_tool_payload(
                    resolved_tool_name or "tool",
                    payload,
                )
                sanitized.append(
                    ToolMessage(
                        content=summarized,
                        name=resolved_tool_name or message.name,
                        tool_call_id=getattr(message, "tool_call_id", None),
                    )
                )
                continue
            if isinstance(message.content, str) and '{"status"' in message.content:
                trimmed = message.content.split('{"status"', 1)[0].rstrip()
                if trimmed:
                    sanitized.append(
                        ToolMessage(
                            content=_truncate_for_prompt(trimmed),
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                else:
                    sanitized.append(
                        ToolMessage(
                            content=f"{resolved_tool_name or 'tool'}: completed",
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                continue
            if isinstance(message.content, str):
                trimmed = _strip_critic_json(message.content)
                if not trimmed:
                    trimmed = f"{resolved_tool_name or 'tool'}: completed"
                sanitized.append(
                    ToolMessage(
                        content=_truncate_for_prompt(trimmed),
                        name=resolved_tool_name or message.name,
                        tool_call_id=getattr(message, "tool_call_id", None),
                    )
                )
                continue
        sanitized.append(message)
    return sanitized
