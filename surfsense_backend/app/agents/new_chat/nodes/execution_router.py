from __future__ import annotations

import re
from typing import Any, Callable
from langchain_core.runnables import RunnableConfig

EXECUTION_STRATEGY_INLINE = "inline"
EXECUTION_STRATEGY_PARALLEL = "parallel"
EXECUTION_STRATEGY_SUBAGENT = "subagent"

INLINE_EXECUTION_TIMEOUT_SECONDS = 120
SUBAGENT_EXECUTION_TIMEOUT_SECONDS = 300

_BULK_SIGNAL_RE = re.compile(
    r"\b(alla|samtliga|hela\s+listan|bulk|for\s+alla|varje\s+kommun|alla\s+kommuner|alla\s+lan)\b",
    re.IGNORECASE,
)


def _selected_agent_names(state: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in state.get("selected_agents") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip().lower()
        else:
            name = str(item or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _plan_step_count(state: dict[str, Any]) -> int:
    plan = state.get("active_plan")
    if not isinstance(plan, list):
        return 0
    return len([item for item in plan if isinstance(item, dict)])


def _speculative_covers_all_tools(state: dict[str, Any]) -> bool:
    resolved = state.get("resolved_tools_by_agent")
    if not isinstance(resolved, dict) or not resolved:
        return False
    required: set[str] = set()
    for tool_ids in resolved.values():
        if not isinstance(tool_ids, list):
            continue
        for tool_id in tool_ids:
            normalized = str(tool_id or "").strip()
            if normalized:
                required.add(normalized)
    if not required:
        return False
    speculative_results = state.get("speculative_results")
    if not isinstance(speculative_results, dict):
        return False
    available = {
        str(tool_id or "").strip()
        for tool_id in speculative_results.keys()
        if str(tool_id or "").strip()
    }
    return required.issubset(available)


def classify_execution_strategy(
    *,
    state: dict[str, Any],
    latest_user_query: str,
    next_step_text: str,
    subagent_enabled: bool = True,
) -> tuple[str, str]:
    route_hint = str(state.get("route_hint") or "").strip().lower()
    if route_hint == "mixed":
        return EXECUTION_STRATEGY_PARALLEL, "mixed_route"
    selected_agents = _selected_agent_names(state)
    plan_steps = _plan_step_count(state)
    combined_text = " ".join(
        part for part in (str(latest_user_query or "").strip(), str(next_step_text or "").strip()) if part
    ).strip()

    if len(selected_agents) > 1:
        return (
            EXECUTION_STRATEGY_PARALLEL,
            f"multiple_agents:{','.join(selected_agents[:4])}",
        )
    if _BULK_SIGNAL_RE.search(combined_text):
        if not subagent_enabled:
            return EXECUTION_STRATEGY_INLINE, "subagent_disabled:bulk_signal_detected"
        return EXECUTION_STRATEGY_SUBAGENT, "bulk_signal_detected"
    if plan_steps > 3:
        if not subagent_enabled:
            return EXECUTION_STRATEGY_INLINE, f"subagent_disabled:plan_steps:{plan_steps}"
        return EXECUTION_STRATEGY_SUBAGENT, f"plan_steps:{plan_steps}"
    if _speculative_covers_all_tools(state):
        return EXECUTION_STRATEGY_INLINE, "speculative_cover_all"
    return EXECUTION_STRATEGY_INLINE, "default_inline"


def get_execution_timeout_seconds(strategy: str | None) -> int:
    normalized = str(strategy or "").strip().lower()
    if normalized == EXECUTION_STRATEGY_SUBAGENT:
        return SUBAGENT_EXECUTION_TIMEOUT_SECONDS
    return INLINE_EXECUTION_TIMEOUT_SECONDS


def build_execution_router_node(
    *,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    next_plan_step_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    subagent_enabled: bool = True,
):
    async def execution_router_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        step = next_plan_step_fn(state)
        next_step_text = (
            str(step.get("content") or "").strip()
            if isinstance(step, dict)
            else ""
        )
        strategy, reason = classify_execution_strategy(
            state=state,
            latest_user_query=latest_user_query,
            next_step_text=next_step_text,
            subagent_enabled=bool(subagent_enabled),
        )
        return {
            "execution_strategy": strategy,
            "orchestration_phase": "execute",
            "pending_hitl_payload": {
                "execution_strategy": strategy,
                "execution_reason": reason,
            },
        }

    return execution_router_node
