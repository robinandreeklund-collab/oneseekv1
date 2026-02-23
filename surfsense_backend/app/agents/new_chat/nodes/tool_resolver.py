from __future__ import annotations

from typing import Any, Callable
from langchain_core.runnables import RunnableConfig


def build_tool_resolver_node(
    *,
    tool_resolver_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    next_plan_step_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    focused_tool_ids_for_agent_fn: Callable[[str, str], list[str]],
    resolve_tool_selection_for_agent_fn: Callable[..., dict[str, Any]] | None = None,
    weather_tool_ids: list[str],
    trafik_tool_ids: list[str],
    namespace_tool_ids_fn: Callable[[str, str], tuple[list[str], dict[str, Any]] | None] | None = None,
):
    async def tool_resolver_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        selected_agents_raw = state.get("selected_agents") or []
        selected_agent_names = [
            str(item.get("name") or "").strip().lower()
            for item in selected_agents_raw
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        if not selected_agent_names:
            fallback_agent = str(state.get("final_agent_name") or "").strip().lower()
            if fallback_agent:
                selected_agent_names = [fallback_agent]
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        step = next_plan_step_fn(state)
        step_text = str(step.get("content") or "").strip() if isinstance(step, dict) else ""
        targeted_missing_info_raw = state.get("targeted_missing_info")
        targeted_missing_info = (
            [
                str(item).strip()
                for item in targeted_missing_info_raw
                if str(item).strip()
            ][:6]
            if isinstance(targeted_missing_info_raw, list)
            else []
        )
        resolver_query = " ".join(
            value for value in [latest_user_query, step_text] if str(value).strip()
        ).strip()
        if targeted_missing_info:
            resolver_query = (
                f"{resolver_query} Saknad information: {', '.join(targeted_missing_info)}"
            ).strip()
        if not resolver_query:
            resolver_query = latest_user_query or step_text

        resolved: dict[str, list[str]] = {}
        tool_trace: dict[str, Any] = {}
        for agent_name in selected_agent_names[:3]:
            # --- Namespace-aware full exposure ---
            # For bounded agents (trafik, weather, etc.) try to expose all
            # namespace tools with retrieval scores as hints instead of
            # relying solely on retrieval to filter.
            namespace_result: tuple[list[str], dict[str, Any]] | None = None
            if namespace_tool_ids_fn is not None:
                try:
                    namespace_result = namespace_tool_ids_fn(agent_name, resolver_query)
                except Exception:
                    namespace_result = None

            resolution_payload: dict[str, Any] = {}
            if resolve_tool_selection_for_agent_fn is not None:
                try:
                    resolution_payload = dict(
                        resolve_tool_selection_for_agent_fn(
                            agent_name,
                            resolver_query,
                            state=state,
                        )
                        or {}
                    )
                except Exception:
                    resolution_payload = {}
            focused_ids = [
                str(tool_id).strip()
                for tool_id in list(resolution_payload.get("selected_tool_ids") or [])
                if str(tool_id).strip()
            ]
            if not focused_ids:
                if namespace_result is not None:
                    # Use full namespace exposure — all tools visible to LLM.
                    ns_ids, ns_hints = namespace_result
                    focused_ids = list(ns_ids)
                    resolution_payload["namespace_hints"] = ns_hints
                    resolution_payload["mode"] = resolution_payload.get("mode") or "namespace_full"
                else:
                    focused_ids = focused_tool_ids_for_agent_fn(agent_name, resolver_query)
            live_gate_mode = str(resolution_payload.get("mode") or "").strip().lower() in {
                "auto_select",
                "candidate_shortlist",
            }
            if agent_name == "weather":
                if live_gate_mode:
                    focused_ids = [tool_id for tool_id in focused_ids if tool_id in weather_tool_ids]
                    if not focused_ids:
                        focused_ids = list(weather_tool_ids)
                elif namespace_result is None:
                    # Legacy fallback when namespace exposure is not available
                    focused_ids = list(weather_tool_ids)
            elif agent_name == "trafik" and namespace_result is None:
                # Legacy fallback when namespace exposure is not available
                focused_ids = [tool_id for tool_id in focused_ids if tool_id in trafik_tool_ids]
                if not focused_ids:
                    focused_ids = list(trafik_tool_ids)
            deduped_ids: list[str] = []
            seen_ids: set[str] = set()
            for tool_id in focused_ids:
                normalized = str(tool_id or "").strip()
                if not normalized or normalized in seen_ids:
                    continue
                seen_ids.add(normalized)
                deduped_ids.append(normalized)
            if deduped_ids:
                resolved[agent_name] = deduped_ids
            tool_trace[agent_name] = {
                "mode": str(resolution_payload.get("mode") or "profile"),
                "top1": resolution_payload.get("top1"),
                "top2": resolution_payload.get("top2"),
                "margin": resolution_payload.get("margin"),
                "auto_selected": bool(resolution_payload.get("auto_selected", False)),
                "selected": deduped_ids,
                "namespace_full_exposure": namespace_result is not None,
                "namespace_hints": resolution_payload.get("namespace_hints"),
            }

        if not resolved:
            resolved = dict(state.get("resolved_tools_by_agent") or {})
        trace = dict(state.get("live_routing_trace") or {})
        trace["tool"] = tool_trace
        return {
            "resolved_tools_by_agent": resolved,
            "live_routing_trace": trace,
            "orchestration_phase": "execute",
            "targeted_missing_info": [],
            "pending_hitl_payload": {
                "tool_resolver_prompt": tool_resolver_prompt_template.strip()[:240],
                "resolved_agent_count": len(resolved),
                "targeted_missing_info": targeted_missing_info,
            },
        }

    return tool_resolver_node
