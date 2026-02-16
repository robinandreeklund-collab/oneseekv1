from __future__ import annotations

from typing import Any, Callable


def build_tool_resolver_node(
    *,
    tool_resolver_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    next_plan_step_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    focused_tool_ids_for_agent_fn: Callable[[str, str], list[str]],
    weather_tool_ids: list[str],
    trafik_tool_ids: list[str],
):
    async def tool_resolver_node(
        state: dict[str, Any],
        config: dict | None = None,
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
        for agent_name in selected_agent_names[:3]:
            focused_ids = focused_tool_ids_for_agent_fn(agent_name, resolver_query)
            if agent_name == "weather":
                focused_ids = list(weather_tool_ids)
            elif agent_name == "trafik":
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

        if not resolved:
            resolved = dict(state.get("resolved_tools_by_agent") or {})
        return {
            "resolved_tools_by_agent": resolved,
            "orchestration_phase": "execute",
            "targeted_missing_info": [],
            "pending_hitl_payload": {
                "tool_resolver_prompt": tool_resolver_prompt_template.strip()[:240],
                "resolved_agent_count": len(resolved),
                "targeted_missing_info": targeted_missing_info,
            },
        }

    return tool_resolver_node
