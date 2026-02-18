from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig


def build_agent_resolver_node(
    *,
    llm: Any,
    agent_resolver_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    normalize_route_hint_fn: Callable[[Any], str],
    route_allowed_agents_fn: Callable[[str | None], set[str]],
    route_default_agent_fn: Callable[[str | None, set[str] | None], str],
    smart_retrieve_agents_fn: Callable[..., list[Any]],
    agent_definitions: list[Any],
    agent_by_name: dict[str, Any],
    agent_payload_fn: Callable[[Any], dict[str, Any]],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
):
    async def resolve_agents_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        feedback = state.get("user_feedback")
        if isinstance(feedback, dict):
            feedback_decision = str(feedback.get("decision") or "").strip().lower()
            feedback_stage = str(feedback.get("stage") or "").strip().lower()
            if (
                feedback_decision == "approve"
                and feedback_stage in {"planner", "execution", "synthesis"}
                and state.get("selected_agents")
            ):
                return {"orchestration_phase": "plan"}
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        if not latest_user_query:
            return {}
        intent_data = state.get("resolved_intent") or {}
        route_hint = normalize_route_hint_fn(
            intent_data.get("route") or state.get("route_hint")
        )
        route_allowed = route_allowed_agents_fn(route_hint)
        default_for_route = route_default_agent_fn(route_hint, route_allowed)
        recent_calls = state.get("recent_agent_calls") or []
        recent_agents = [
            str(item.get("agent") or "").strip()
            for item in recent_calls[-3:]
            if isinstance(item, dict) and str(item.get("agent") or "").strip()
        ]
        selected = smart_retrieve_agents_fn(
            latest_user_query,
            agent_definitions=agent_definitions,
            recent_agents=recent_agents,
            limit=3,
        )
        if route_allowed:
            filtered = [agent for agent in selected if agent.name in route_allowed]
            if filtered:
                selected = filtered
            elif default_for_route in agent_by_name:
                selected = [agent_by_name[default_for_route]]
        selected_payload = [agent_payload_fn(agent) for agent in selected]
        if not selected_payload and default_for_route in agent_by_name:
            selected_payload = [agent_payload_fn(agent_by_name[default_for_route])]

        graph_complexity = str(state.get("graph_complexity") or "").strip().lower()
        if graph_complexity == "simple" and selected_payload:
            # For simple turns, avoid an extra resolver LLM call.
            return {
                "selected_agents": selected_payload[:1],
                "orchestration_phase": "plan",
            }

        prompt = append_datetime_context_fn(agent_resolver_prompt_template)
        resolver_input = json.dumps(
            {
                "query": latest_user_query,
                "resolved_intent": intent_data if isinstance(intent_data, dict) else {},
                "agent_candidates": selected_payload,
            },
            ensure_ascii=True,
        )
        try:
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=resolver_input),
                ],
                max_tokens=180,
            )
            parsed = extract_first_json_object_fn(str(getattr(message, "content", "") or ""))
            requested = parsed.get("selected_agents")
            if isinstance(requested, list) and requested:
                by_name = {
                    str(item.get("name") or "").strip(): item
                    for item in selected_payload
                    if isinstance(item, dict)
                }
                ordered: list[dict[str, Any]] = []
                for name in requested:
                    normalized = str(name or "").strip()
                    if normalized and normalized in by_name:
                        ordered.append(by_name[normalized])
                if ordered:
                    selected_payload = ordered[:3]
        except Exception:
            pass
        return {
            "selected_agents": selected_payload[:3],
            "orchestration_phase": "plan",
        }

    return resolve_agents_node
