from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..structured_schemas import (
    PlannerResult,
    pydantic_to_response_format,
    structured_output_enabled,
)


def build_planner_node(
    *,
    llm: Any,
    planner_prompt_template: str,
    multi_domain_planner_prompt_template: str | None = None,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
):
    async def planner_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        selected_agents = [
            item
            for item in (state.get("selected_agents") or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        if not latest_user_query:
            return {"orchestration_phase": "execute"}

        current_plan = state.get("active_plan") or []
        if current_plan and not state.get("plan_complete") and not state.get("critic_decision"):
            return {"orchestration_phase": "execute"}

        graph_complexity = str(state.get("graph_complexity") or "").strip().lower()
        if graph_complexity == "simple":
            fallback_agent = (
                str(selected_agents[0].get("name") or "").strip()
                if selected_agents
                else "agent"
            )
            return {
                "active_plan": [
                    {
                        "id": "step-1",
                        "content": f"Kör uppgiften med {fallback_agent} och sammanfatta resultatet",
                        "status": "pending",
                        "parallel": False,
                    }
                ],
                "plan_step_index": 0,
                "plan_complete": False,
                "orchestration_phase": "execute",
                "critic_decision": None,
            }

        # Select prompt: use multi-domain variant for mixed-route queries.
        intent_data = state.get("resolved_intent") or {}
        route_hint = str(
            intent_data.get("route") or state.get("route_hint") or ""
        ).strip().lower()
        sub_intents: list[str] = [
            str(s).strip()
            for s in (state.get("sub_intents") or [])
            if str(s).strip()
        ]
        # P3: atomic_questions from the multi_query_decomposer.
        atomic_questions: list[dict[str, Any]] = [
            q for q in (state.get("atomic_questions") or [])
            if isinstance(q, dict) and str(q.get("text") or "").strip()
        ]
        # Use multi-domain template if we have atomic questions with multiple
        # domains OR the legacy mixed-route path with sub_intents.
        is_mixed = route_hint == "mixed" and bool(sub_intents)
        has_decomposition = len(atomic_questions) >= 2
        chosen_template = (
            multi_domain_planner_prompt_template
            if (is_mixed or has_decomposition) and multi_domain_planner_prompt_template
            else planner_prompt_template
        )

        prompt = append_datetime_context_fn(chosen_template)
        planner_payload: dict[str, Any] = {
            "query": latest_user_query,
            "resolved_intent": state.get("resolved_intent") or {},
            "selected_agents": selected_agents,
            "current_plan": current_plan,
        }
        if atomic_questions:
            planner_payload["atomic_questions"] = atomic_questions
        planner_input = json.dumps(planner_payload, ensure_ascii=True)
        new_plan: list[dict[str, Any]] = []
        try:
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 500}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    PlannerResult, "planner_result"
                )
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=planner_input),
                ],
                **_invoke_kwargs,
            )
            _raw_content = str(getattr(message, "content", "") or "")
            # P1 Extra: try Pydantic structured parse, fall back to regex
            try:
                _structured = PlannerResult.model_validate_json(_raw_content)
                parsed = _structured.model_dump(exclude={"thinking"})
            except Exception:
                parsed = extract_first_json_object_fn(_raw_content)
            steps = parsed.get("steps")
            if isinstance(steps, list):
                for index, step in enumerate(steps[:4], start=1):
                    if isinstance(step, dict):
                        content = str(step.get("content") or "").strip()
                        if not content:
                            continue
                        step_id = str(step.get("id") or f"step-{index}").strip()
                        status = str(step.get("status") or "pending").strip().lower()
                        if status not in {"pending", "in_progress", "completed", "cancelled"}:
                            status = "pending"
                        parallel = bool(step.get("parallel", False))
                        new_plan.append(
                            {
                                "id": step_id,
                                "content": content,
                                "status": status,
                                "parallel": parallel,
                            }
                        )
        except Exception:
            pass

        if not new_plan:
            fallback_agent = (
                str(selected_agents[0].get("name") or "").strip()
                if selected_agents
                else "agent"
            )
            new_plan = [
                {
                    "id": "step-1",
                    "content": f"Delegara huvuduppgiften till {fallback_agent}",
                    "status": "pending",
                    "parallel": False,
                }
            ]
        return {
            "active_plan": new_plan,
            "plan_step_index": 0,
            "plan_complete": False,
            "orchestration_phase": "execute",
            "critic_decision": None,
        }

    return planner_node
