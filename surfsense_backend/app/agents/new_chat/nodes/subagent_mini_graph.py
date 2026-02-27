"""P4.1: Subagent mini-graph — isolated per-domain LangGraph execution.

Each subagent gets its own mini-graph with:
  - mini_planner   → creates a compact micro-plan for the domain
  - mini_executor  → runs domain-scoped tools
  - mini_critic    → evaluates if the domain result is sufficient
  - mini_synthesizer → summarises results into a compact artifact

The subagent_spawner node orchestrates parallel execution of
independent domains, each with its own checkpointer scope so loops
in one domain cannot spill over into another.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..structured_schemas import (
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)

# Hard limits per mini-graph to prevent infinite loops.
_MAX_MINI_RETRIES = 2
_MAX_PARALLEL_SUBAGENTS = 6
_MAX_MINI_PLAN_STEPS = 3


# ─── Mini-graph internal state ──────────────────────────────────────

class MiniGraphState:
    """Lightweight container for a single domain mini-graph execution."""

    __slots__ = (
        "domain",
        "task",
        "tools",
        "plan_steps",
        "tool_results",
        "critic_decision",
        "critic_feedback",
        "retry_count",
        "summary",
        "key_facts",
        "data_quality",
        "cache_hit",
    )

    def __init__(self, *, domain: str, task: str, tools: list[str]):
        self.domain = domain
        self.task = task
        self.tools = tools
        self.plan_steps: list[dict[str, Any]] = []
        self.tool_results: list[dict[str, Any]] = []
        self.critic_decision: str = ""
        self.critic_feedback: str = ""
        self.retry_count: int = 0
        self.summary: str = ""
        self.key_facts: list[str] = []
        self.data_quality: str = "unknown"
        self.cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "summary": self.summary,
            "key_facts": self.key_facts,
            "data_quality": self.data_quality,
            "cache_hit": self.cache_hit,
        }


# ─── Cache helper ────────────────────────────────────────────────────

def _cache_key(domain: str, query: str) -> str:
    """Generate a deterministic cache key for semantic tool caching (P4.3)."""
    raw = f"cache:{domain}:{query}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ─── Subagent Spawner ────────────────────────────────────────────────

def build_subagent_spawner_node(
    *,
    llm: Any,
    spawner_prompt_template: str,
    mini_planner_prompt_template: str,
    mini_critic_prompt_template: str,
    mini_synthesizer_prompt_template: str,
    adaptive_guard_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
):
    """Return an async node function for the subagent spawner.

    The spawner reads ``domain_plans`` from state, creates
    ``MiniGraphState`` objects per domain, and runs them in parallel
    (up to ``_MAX_PARALLEL_SUBAGENTS``).

    Each mini-graph internally loops: plan → execute → critic → (retry | synthesize).
    """

    async def _run_mini_planner(
        mini_state: MiniGraphState,
        user_query: str,
    ) -> None:
        """LLM-driven micro-plan for a single domain."""
        system_msg = SystemMessage(content=mini_planner_prompt_template)
        human_msg = HumanMessage(
            content=(
                f"Domän: {mini_state.domain}\n"
                f"Fråga: {user_query}\n"
                f"Uppgift: {mini_state.task}\n"
                f"Tillgängliga verktyg: {', '.join(mini_state.tools)}"
            )
        )
        try:
            raw = await llm.ainvoke([system_msg, human_msg], max_tokens=400)
            raw_content = str(getattr(raw, "content", "") or "")
            parsed = extract_first_json_object_fn(raw_content)
            steps = parsed.get("steps", [])[:_MAX_MINI_PLAN_STEPS]
            mini_state.plan_steps = steps
            logger.info(
                "mini_planner[%s]: %d steps planned",
                mini_state.domain,
                len(steps),
            )
        except Exception:
            logger.exception("mini_planner[%s]: failed", mini_state.domain)
            mini_state.plan_steps = [
                {"action": "fallback", "tool_id": mini_state.tools[0] if mini_state.tools else "unknown", "use_cache": False}
            ]

    async def _run_mini_executor(
        mini_state: MiniGraphState,
    ) -> None:
        """Simulate tool execution for the domain.

        In the full implementation this will call actual tools via the
        existing executor infrastructure. For now we record the planned
        steps as pending results that downstream critic can evaluate.
        """
        results: list[dict[str, Any]] = []
        for step in mini_state.plan_steps:
            results.append({
                "tool_id": step.get("tool_id", "unknown"),
                "action": step.get("action", ""),
                "status": "executed",
                "use_cache": step.get("use_cache", False),
            })
        mini_state.tool_results = results
        logger.info(
            "mini_executor[%s]: %d tools executed",
            mini_state.domain,
            len(results),
        )

    async def _run_mini_critic(
        mini_state: MiniGraphState,
        user_query: str,
    ) -> None:
        """LLM-driven evaluation of domain results."""
        system_msg = SystemMessage(content=mini_critic_prompt_template)
        results_text = json.dumps(mini_state.tool_results, ensure_ascii=False, default=str)
        human_msg = HumanMessage(
            content=(
                f"Domän: {mini_state.domain}\n"
                f"Fråga: {user_query}\n"
                f"Verktygsresultat:\n{results_text}"
            )
        )
        try:
            raw = await llm.ainvoke([system_msg, human_msg], max_tokens=300)
            raw_content = str(getattr(raw, "content", "") or "")
            parsed = extract_first_json_object_fn(raw_content)
            mini_state.critic_decision = parsed.get("decision", "ok")
            mini_state.critic_feedback = parsed.get("feedback", "")
            logger.info(
                "mini_critic[%s]: decision=%s",
                mini_state.domain,
                mini_state.critic_decision,
            )
        except Exception:
            logger.exception("mini_critic[%s]: failed, defaulting to ok", mini_state.domain)
            mini_state.critic_decision = "ok"
            mini_state.critic_feedback = ""

    async def _run_mini_synthesizer(
        mini_state: MiniGraphState,
        user_query: str,
    ) -> None:
        """LLM-driven summarisation of domain results."""
        system_msg = SystemMessage(content=mini_synthesizer_prompt_template)
        results_text = json.dumps(mini_state.tool_results, ensure_ascii=False, default=str)
        human_msg = HumanMessage(
            content=(
                f"Domän: {mini_state.domain}\n"
                f"Fråga: {user_query}\n"
                f"Verktygsresultat:\n{results_text}"
            )
        )
        try:
            raw = await llm.ainvoke([system_msg, human_msg], max_tokens=600)
            raw_content = str(getattr(raw, "content", "") or "")
            parsed = extract_first_json_object_fn(raw_content)
            mini_state.summary = parsed.get("summary", "")
            mini_state.key_facts = parsed.get("key_facts", [])
            mini_state.data_quality = parsed.get("data_quality", "medium")
            logger.info(
                "mini_synthesizer[%s]: summary=%d chars",
                mini_state.domain,
                len(mini_state.summary),
            )
        except Exception:
            logger.exception("mini_synthesizer[%s]: failed", mini_state.domain)
            mini_state.summary = f"[Sammanfattning ej tillgänglig för {mini_state.domain}]"
            mini_state.data_quality = "low"

    async def _run_adaptive_guard(
        mini_state: MiniGraphState,
    ) -> dict[str, Any]:
        """Check budget and adjust thresholds (P4.2a).

        Returns adaptive thresholds dict. If force_synthesis is True,
        the mini-graph should skip retries.
        """
        force = mini_state.retry_count >= _MAX_MINI_RETRIES
        confidence = max(0.3, 0.7 - (mini_state.retry_count * 0.15))
        max_tools = max(1, 4 - mini_state.retry_count)
        return {
            "force_synthesis": force,
            "adjusted_confidence_threshold": confidence,
            "adjusted_max_tools": max_tools,
            "steps_remaining": max(0, _MAX_MINI_RETRIES - mini_state.retry_count),
        }

    async def _run_single_mini_graph(
        mini_state: MiniGraphState,
        user_query: str,
    ) -> MiniGraphState:
        """Execute the full mini-graph loop for one domain."""
        # Step 1: Plan
        await _run_mini_planner(mini_state, user_query)

        # Step 2-3: Execute → Critic loop (max _MAX_MINI_RETRIES)
        while True:
            await _run_mini_executor(mini_state)
            await _run_mini_critic(mini_state, user_query)

            if mini_state.critic_decision == "ok":
                break

            # Check adaptive guard
            guard = await _run_adaptive_guard(mini_state)
            if guard["force_synthesis"]:
                logger.warning(
                    "adaptive_guard[%s]: forcing synthesis after %d retries",
                    mini_state.domain,
                    mini_state.retry_count,
                )
                break

            mini_state.retry_count += 1

            if mini_state.critic_decision == "fail":
                logger.warning(
                    "mini_critic[%s]: fail decision, stopping",
                    mini_state.domain,
                )
                break

        # Step 4: Synthesize
        await _run_mini_synthesizer(mini_state, user_query)
        return mini_state

    async def subagent_spawner_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        """Spawn parallel mini-graphs per domain from domain_plans."""
        domain_plans = state.get("domain_plans") or {}
        if not domain_plans:
            logger.info("subagent_spawner: no domain_plans, skipping")
            return {
                "spawned_domains": [],
                "subagent_summaries": [],
                "micro_plans": {},
                "convergence_status": None,
                "adaptive_thresholds": None,
            }

        user_query = latest_user_query_fn(state.get("messages") or [])

        # Build MiniGraphState per domain
        mini_states: list[MiniGraphState] = []
        for domain_name, plan_data in domain_plans.items():
            if isinstance(plan_data, dict):
                tools = plan_data.get("tools", [])
                task = plan_data.get("rationale", user_query)
            else:
                tools = []
                task = user_query

            mini_states.append(MiniGraphState(
                domain=domain_name,
                task=task,
                tools=tools if isinstance(tools, list) else [],
            ))

        # Limit concurrency
        semaphore = asyncio.Semaphore(_MAX_PARALLEL_SUBAGENTS)

        async def _run_with_semaphore(ms: MiniGraphState) -> MiniGraphState:
            async with semaphore:
                return await _run_single_mini_graph(ms, user_query)

        # Execute all mini-graphs in parallel
        completed = await asyncio.gather(
            *[_run_with_semaphore(ms) for ms in mini_states],
            return_exceptions=True,
        )

        # Collect results
        summaries: list[dict[str, Any]] = []
        micro_plans: dict[str, list[dict[str, Any]]] = {}
        spawned_domains: list[str] = []

        for result in completed:
            if isinstance(result, Exception):
                logger.error("subagent_spawner: mini-graph failed: %s", result)
                continue
            ms: MiniGraphState = result
            spawned_domains.append(ms.domain)
            summaries.append(ms.to_dict())
            micro_plans[ms.domain] = ms.plan_steps

        logger.info(
            "subagent_spawner: %d/%d domains completed",
            len(spawned_domains),
            len(mini_states),
        )

        return {
            "spawned_domains": spawned_domains,
            "subagent_summaries": summaries,
            "micro_plans": micro_plans,
            "total_steps": (state.get("total_steps") or 0) + 1,
        }

    return subagent_spawner_node
