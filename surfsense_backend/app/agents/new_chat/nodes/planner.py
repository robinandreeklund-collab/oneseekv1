from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig


def build_planner_node(
    *,
    llm: Any,
    planner_prompt_template: str,
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
                    }
                ],
                "plan_step_index": 0,
                "plan_complete": False,
                "orchestration_phase": "execute",
                "critic_decision": None,
            }

        prompt = append_datetime_context_fn(planner_prompt_template)
        planner_input = json.dumps(
            {
                "query": latest_user_query,
                "resolved_intent": state.get("resolved_intent") or {},
                "selected_agents": selected_agents,
                "current_plan": current_plan,
            },
            ensure_ascii=True,
        )
        new_plan: list[dict[str, Any]] = []
        try:
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=planner_input),
                ],
                max_tokens=220,
            )
            parsed = extract_first_json_object_fn(str(getattr(message, "content", "") or ""))
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
                        new_plan.append(
                            {
                                "id": step_id,
                                "content": content,
                                "status": status,
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
