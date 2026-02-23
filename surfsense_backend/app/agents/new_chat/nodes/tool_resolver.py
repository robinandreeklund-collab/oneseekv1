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
        retrieval_hints: dict[str, list[str]] = {}
        tool_trace: dict[str, Any] = {}
        for agent_name in selected_agent_names[:3]:
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
                focused_ids = focused_tool_ids_for_agent_fn(agent_name, resolver_query)
            live_gate_mode = str(resolution_payload.get("mode") or "").strip().lower() in {
                "auto_select",
                "candidate_shortlist",
            }
            if agent_name == "weather":
                # Capture reranker's top suggestions as hints before namespace override
                ranked_weather = [tid for tid in focused_ids if tid in weather_tool_ids]
                if ranked_weather:
                    retrieval_hints[agent_name] = ranked_weather[:3]
                # Always expose full weather namespace so the LLM can choose
                if live_gate_mode:
                    focused_ids = [tool_id for tool_id in focused_ids if tool_id in weather_tool_ids]
                    if not focused_ids:
                        focused_ids = list(weather_tool_ids)
                else:
                    focused_ids = list(weather_tool_ids)
            elif agent_name == "trafik":
                # Capture reranker's top suggestions as hints before namespace override
                ranked_trafik = [tid for tid in focused_ids if tid in trafik_tool_ids]
                if ranked_trafik:
                    retrieval_hints[agent_name] = ranked_trafik[:3]
                # Always expose full trafik namespace so the LLM can choose
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
                if len(deduped_ids) >= 8:
                    break
            if deduped_ids:
                resolved[agent_name] = deduped_ids
            tool_trace[agent_name] = {
                "mode": str(resolution_payload.get("mode") or "profile"),
                "top1": resolution_payload.get("top1"),
                "top2": resolution_payload.get("top2"),
                "margin": resolution_payload.get("margin"),
                "auto_selected": bool(resolution_payload.get("auto_selected", False)),
                "selected": deduped_ids,
                "hints": retrieval_hints.get(agent_name, []),
            }

        if not resolved:
            resolved = dict(state.get("resolved_tools_by_agent") or {})
        trace = dict(state.get("live_routing_trace") or {})
        trace["tool"] = tool_trace
        return {
            "resolved_tools_by_agent": resolved,
            "retrieval_hints_by_agent": retrieval_hints,
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
