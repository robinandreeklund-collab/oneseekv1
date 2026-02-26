from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..structured_schemas import (
    AgentResolverResult,
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)


def build_agent_resolver_node(
    *,
    llm: Any,
    agent_resolver_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    normalize_route_hint_fn: Callable[[Any], str],
    route_allowed_agents_fn: Callable[[str | None], set[str]],
    route_default_agent_fn: Callable[[str | None, set[str] | None], str],
    smart_retrieve_agents_fn: Callable[..., list[Any]],
    smart_retrieve_agents_with_scores_fn: Callable[..., list[dict[str, Any]]] | None = None,
    agent_definitions: list[Any],
    agent_by_name: dict[str, Any],
    agent_payload_fn: Callable[[Any], dict[str, Any]],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
    live_routing_config: dict[str, Any] | None = None,
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
        sub_intents: list[str] = [
            str(s).strip()
            for s in (state.get("sub_intents") or [])
            if str(s).strip()
        ]
        route_allowed = route_allowed_agents_fn(route_hint)
        default_for_route = route_default_agent_fn(route_hint, route_allowed)
        recent_calls = state.get("recent_agent_calls") or []
        recent_agents = [
            str(item.get("agent") or "").strip()
            for item in recent_calls[-3:]
            if isinstance(item, dict) and str(item.get("agent") or "").strip()
        ]
        live_cfg = dict(live_routing_config or {})
        live_enabled = bool(live_cfg.get("enabled", False))
        phase_index = int(live_cfg.get("phase_index") or 0)
        shortlist_k = max(2, min(int(live_cfg.get("agent_top_k") or 3), 8))

        # Fix B: Multi-domain retrieval — run retrieval per sub_intent and merge candidates
        if route_hint == "mixed" and sub_intents and smart_retrieve_agents_with_scores_fn is not None:
            merged_by_name: dict[str, dict[str, Any]] = {}
            for sub_route in sub_intents:
                sub_allowed = route_allowed_agents_fn(sub_route)
                sub_candidates = list(
                    smart_retrieve_agents_with_scores_fn(
                        latest_user_query,
                        agent_definitions=agent_definitions,
                        recent_agents=recent_agents,
                        limit=max(shortlist_k, 3),
                    )
                    or []
                )
                if sub_allowed:
                    sub_candidates = [
                        item
                        for item in sub_candidates
                        if isinstance(item, dict)
                        and getattr(item.get("definition"), "name", "") in sub_allowed
                    ]
                for item in sub_candidates:
                    if not isinstance(item, dict):
                        continue
                    name = getattr(item.get("definition"), "name", "")
                    if name and name not in merged_by_name:
                        merged_by_name[name] = item
            ranked_candidates: list[dict[str, Any]] = list(merged_by_name.values())
        else:
            ranked_candidates = []
            if smart_retrieve_agents_with_scores_fn is not None:
                ranked_candidates = list(
                    smart_retrieve_agents_with_scores_fn(
                        latest_user_query,
                        agent_definitions=agent_definitions,
                        recent_agents=recent_agents,
                        limit=max(shortlist_k, 3),
                    )
                    or []
                )
            if not ranked_candidates:
                selected = smart_retrieve_agents_fn(
                    latest_user_query,
                    agent_definitions=agent_definitions,
                    recent_agents=recent_agents,
                    limit=max(shortlist_k, 3),
                )
                ranked_candidates = [
                    {"definition": item, "score": float(max(0, len(selected) - idx))}
                    for idx, item in enumerate(selected)
                ]
        selected = [
            item.get("definition")
            for item in ranked_candidates
            if isinstance(item, dict) and item.get("definition") is not None
        ]
        if route_allowed:
            filtered = [agent for agent in selected if agent.name in route_allowed]
            if filtered:
                selected = filtered
                allowed_names = {agent.name for agent in filtered}
                ranked_candidates = [
                    item
                    for item in ranked_candidates
                    if isinstance(item, dict)
                    and getattr(item.get("definition"), "name", "") in allowed_names
                ]
            elif default_for_route in agent_by_name:
                selected = [agent_by_name[default_for_route]]
                ranked_candidates = [
                    item
                    for item in ranked_candidates
                    if isinstance(item, dict)
                    and getattr(item.get("definition"), "name", "") == default_for_route
                ]
        selected_payload = [agent_payload_fn(agent) for agent in selected]
        if not selected_payload and default_for_route in agent_by_name:
            selected_payload = [agent_payload_fn(agent_by_name[default_for_route])]
        selected_payload = selected_payload[: max(1, int(shortlist_k))]
        top1 = ranked_candidates[0] if ranked_candidates else None
        top2 = ranked_candidates[1] if len(ranked_candidates) > 1 else None
        top1_name = (
            getattr(top1.get("definition"), "name", "")
            if isinstance(top1, dict)
            else ""
        )
        top2_name = (
            getattr(top2.get("definition"), "name", "")
            if isinstance(top2, dict)
            else ""
        )
        top1_score = float(top1.get("score") or 0.0) if isinstance(top1, dict) else 0.0
        top2_score = float(top2.get("score") or 0.0) if isinstance(top2, dict) else 0.0
        margin = (top1_score - top2_score) if top1 and top2 else None

        graph_complexity = str(state.get("graph_complexity") or "").strip().lower()
        if graph_complexity == "simple" and selected_payload:
            # For simple turns, avoid an extra resolver LLM call.
            trace = dict(state.get("live_routing_trace") or {})
            trace["agent"] = {
                "mode": "simple_auto",
                "phase": str(live_cfg.get("phase") or "shadow"),
                "top1": top1_name,
                "top2": top2_name,
                "margin": margin,
                "shortlist_size": len(selected_payload),
                "selected": selected_payload[0].get("name") if selected_payload else None,
            }
            if live_enabled:
                logger.info(
                    "live-routing agent-selection phase=%s mode=%s top1=%s top2=%s margin=%s selected=%s",
                    live_cfg.get("phase"),
                    trace["agent"].get("mode"),
                    top1_name,
                    top2_name,
                    margin,
                    trace["agent"].get("selected"),
                )
            return {
                "selected_agents": selected_payload[:1],
                "live_routing_trace": trace,
                "orchestration_phase": "plan",
            }

        should_auto_select = bool(
            live_enabled
            and phase_index >= 2
            and selected_payload
            and margin is not None
            and margin >= float(live_cfg.get("agent_auto_margin_threshold") or 0.18)
            and top1_score >= float(live_cfg.get("agent_auto_score_threshold") or 0.55)
        )
        if should_auto_select:
            selected_payload = selected_payload[:1]
            trace = dict(state.get("live_routing_trace") or {})
            trace["agent"] = {
                "mode": "auto_select",
                "phase": str(live_cfg.get("phase") or "shadow"),
                "top1": top1_name,
                "top2": top2_name,
                "margin": margin,
                "shortlist_size": len(selected_payload),
                "selected": selected_payload[0].get("name") if selected_payload else None,
            }
            if live_enabled:
                logger.info(
                    "live-routing agent-selection phase=%s mode=%s top1=%s top2=%s margin=%s selected=%s",
                    live_cfg.get("phase"),
                    trace["agent"].get("mode"),
                    top1_name,
                    top2_name,
                    margin,
                    trace["agent"].get("selected"),
                )
            return {
                "selected_agents": selected_payload[:1],
                "live_routing_trace": trace,
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
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 300}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    AgentResolverResult, "agent_resolver_result"
                )
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=resolver_input),
                ],
                **_invoke_kwargs,
            )
            _raw_content = str(getattr(message, "content", "") or "")
            # P1 Extra: try Pydantic structured parse, fall back to regex
            try:
                _structured = AgentResolverResult.model_validate_json(_raw_content)
                parsed = _structured.model_dump(exclude={"thinking"})
            except Exception:
                parsed = extract_first_json_object_fn(_raw_content)
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
                    selected_payload = ordered[: max(1, int(shortlist_k))]
        except Exception:
            pass
        trace = dict(state.get("live_routing_trace") or {})
        trace["agent"] = {
            "mode": "llm",
            "phase": str(live_cfg.get("phase") or "shadow"),
            "top1": top1_name,
            "top2": top2_name,
            "margin": margin,
            "shortlist_size": len(selected_payload),
            "selected": selected_payload[0].get("name") if selected_payload else None,
        }
        if live_enabled:
            logger.info(
                "live-routing agent-selection phase=%s mode=%s top1=%s top2=%s margin=%s selected=%s",
                live_cfg.get("phase"),
                trace["agent"].get("mode"),
                top1_name,
                top2_name,
                margin,
                trace["agent"].get("selected"),
            )
        return {
            "selected_agents": selected_payload[: max(1, int(shortlist_k))],
            "live_routing_trace": trace,
            "orchestration_phase": "plan",
        }

    return resolve_agents_node
