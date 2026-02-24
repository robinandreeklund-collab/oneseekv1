"""Domain Planner node — LLM-driven per-agent micro-planning.

This node runs after execution_router and before execution_hitl_gate.
For each selected domain agent it creates a lightweight sub-plan that
specifies which tools to prioritise and whether to run them in parallel
or sequentially.  The result is stored in ``domain_plans`` on state so
that downstream workers can respect the per-domain strategy.

For simple/trivial flows or when only one tool is resolved the node is
a near-passthrough to keep latency low.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


def build_domain_planner_node(
    *,
    llm: Any,
    domain_planner_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
):
    """Return a domain_planner node bound to the supplied helpers.

    The planner inspects each domain agent selected by agent_resolver /
    execution_router and produces a per-agent micro-plan:

    ``domain_plans`` structure::

        {
          "väder": {
            "mode": "parallel",          # "parallel" | "sequential"
            "tools": ["smhi_metfcst", "smhi_metobs"],
            "rationale": "..."
          },
          "statistik": {
            "mode": "sequential",
            "tools": ["scb_befolkning"],
            "rationale": "..."
          }
        }

    If the LLM call fails or returns invalid JSON the node falls back to
    returning an empty dict so execution continues unaffected.
    """

    async def domain_planner_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        # ── Fast-path: nothing to plan ─────────────────────────────────
        selected_agents: list[dict[str, Any]] = [
            item
            for item in (state.get("selected_agents") or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        resolved_tools: dict[str, list[str]] = dict(
            state.get("resolved_tools_by_agent") or {}
        )

        if not selected_agents:
            return {"domain_plans": {}}

        graph_complexity = str(state.get("graph_complexity") or "").strip().lower()
        if graph_complexity in {"trivial", "simple"} or len(selected_agents) <= 1:
            # For single-agent / simple flows build a minimal plan directly
            # without spending an LLM call.
            minimal: dict[str, Any] = {}
            for agent_entry in selected_agents:
                agent_name = str(agent_entry.get("name") or "").strip()
                if not agent_name:
                    continue
                tool_ids = [
                    str(t) for t in (resolved_tools.get(agent_name) or []) if str(t).strip()
                ]
                minimal[agent_name] = {
                    "mode": "parallel" if len(tool_ids) > 1 else "sequential",
                    "tools": tool_ids,
                    "rationale": "Enkel flöde — automatisk plan utan LLM-anrop.",
                }
            return {"domain_plans": minimal}

        # ── Full LLM planning ──────────────────────────────────────────
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        prompt = append_datetime_context_fn(domain_planner_prompt_template)

        planner_input = json.dumps(
            {
                "query": latest_user_query,
                "selected_agents": [
                    {
                        "name": str(a.get("name") or "").strip(),
                        "description": str(a.get("description") or "").strip(),
                        "available_tools": [
                            str(t)
                            for t in (
                                resolved_tools.get(str(a.get("name") or "").strip()) or []
                            )
                            if str(t).strip()
                        ],
                    }
                    for a in selected_agents
                    if str(a.get("name") or "").strip()
                ],
                "execution_strategy": str(state.get("execution_strategy") or "").strip(),
                "route_hint": str(state.get("route_hint") or "").strip(),
                "sub_intents": list(state.get("sub_intents") or []),
            },
            ensure_ascii=True,
        )

        domain_plans: dict[str, Any] = {}
        try:
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=planner_input),
                ],
                max_tokens=300,
            )
            parsed = extract_first_json_object_fn(
                str(getattr(message, "content", "") or "")
            )
            raw_plans = parsed.get("domain_plans")
            if isinstance(raw_plans, dict):
                for agent_name, plan in raw_plans.items():
                    if not isinstance(plan, dict):
                        continue
                    tools = [
                        str(t) for t in (plan.get("tools") or []) if str(t).strip()
                    ]
                    mode = str(plan.get("mode") or "parallel").strip().lower()
                    if mode not in {"parallel", "sequential"}:
                        mode = "parallel"
                    domain_plans[str(agent_name).strip()] = {
                        "mode": mode,
                        "tools": tools,
                        "rationale": str(plan.get("rationale") or "").strip(),
                    }
        except Exception:
            logger.debug("domain_planner: LLM call failed, using empty plans", exc_info=True)

        # Ensure every selected agent has at least a minimal plan entry.
        for agent_entry in selected_agents:
            agent_name = str(agent_entry.get("name") or "").strip()
            if not agent_name or agent_name in domain_plans:
                continue
            tool_ids = [
                str(t) for t in (resolved_tools.get(agent_name) or []) if str(t).strip()
            ]
            domain_plans[agent_name] = {
                "mode": "parallel" if len(tool_ids) > 1 else "sequential",
                "tools": tool_ids,
                "rationale": "Fallback — LLM-plan saknades för agent.",
            }

        logger.info(
            "domain_planner: planned %d agents: %s",
            len(domain_plans),
            list(domain_plans.keys()),
        )
        return {"domain_plans": domain_plans}

    return domain_planner_node
