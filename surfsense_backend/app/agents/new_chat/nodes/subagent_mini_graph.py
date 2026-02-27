"""P4.1: Subagent mini-graph — isolated per-domain execution via worker pool.

Each domain gets proper subagent isolation identical to call_agent:
  - Unique subagent_id  (sa-mini_{domain}-{hash})
  - Isolated checkpoint namespace
  - Sandbox scope per domain  (sandbox_scope_mode=subagent)
  - Proper handoff contract   (status, confidence, summary, findings, artifact_refs)

The subagent_spawner orchestrates parallel domain execution using the
same worker infrastructure as call_agent / call_agents_parallel.
Each worker can in turn call call_agent recursively (nested subagents).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

# Hard limits per mini-graph to prevent infinite loops.
_MAX_MINI_RETRIES = 2
_MAX_PARALLEL_SUBAGENTS = 6
_MAX_MINI_PLAN_STEPS = 3


# ─── Cache helper ────────────────────────────────────────────────────

def _cache_key(domain: str, query: str) -> str:
    """Generate a deterministic cache key for semantic tool caching (P4.3)."""
    raw = f"cache:{domain}:{query}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ─── Response extraction from worker result ──────────────────────────

def _extract_response_text(result: dict[str, Any] | Any) -> str:
    """Extract final response text from worker.ainvoke result.

    Follows the exact same pattern as call_agent in supervisor_agent.py:
    1. Take last message content
    2. Fallback to last ToolMessage content if empty
    """
    if not isinstance(result, dict):
        return ""
    messages_out = result.get("messages") or []
    if not messages_out:
        return ""
    response_text = str(getattr(messages_out[-1], "content", "") or "")
    if not response_text.strip():
        for msg in reversed(messages_out):
            if hasattr(msg, "type") and getattr(msg, "type", None) == "tool":
                tool_content = str(getattr(msg, "content", "") or "").strip()
                if tool_content and len(tool_content) > 10:
                    return tool_content
            elif isinstance(msg, dict) and str(msg.get("type") or "").strip().lower() == "tool":
                tool_content = str(msg.get("content") or "").strip()
                if tool_content and len(tool_content) > 10:
                    return tool_content
    return response_text


def _extract_used_tools(result: dict[str, Any] | Any) -> list[str]:
    """Extract tool names used by the worker from its output messages."""
    if not isinstance(result, dict):
        return []
    messages_out = result.get("messages") or []
    tool_names: list[str] = []
    seen: set[str] = set()
    for msg in messages_out:
        name = ""
        if hasattr(msg, "name") and hasattr(msg, "type"):
            if getattr(msg, "type", None) == "tool":
                name = str(getattr(msg, "name", "") or "").strip()
        elif isinstance(msg, dict) and str(msg.get("type") or "") == "tool":
            name = str(msg.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            tool_names.append(name)
    return tool_names


# ─── Subagent Spawner ────────────────────────────────────────────────

def build_subagent_spawner_node(
    *,
    llm: Any,
    # Prompt templates
    spawner_prompt_template: str,
    mini_planner_prompt_template: str,
    mini_critic_prompt_template: str,
    mini_synthesizer_prompt_template: str,
    adaptive_guard_prompt_template: str,
    # Shared utility callbacks
    latest_user_query_fn: Callable[[list[Any] | None], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
    # Worker infrastructure (same as call_agent uses)
    worker_pool: Any,  # LazyWorkerPool — .get(agent_name) returns worker or None
    # Isolation infrastructure callbacks
    build_subagent_id_fn: Callable[..., str],
    build_handoff_payload_fn: Callable[..., dict[str, Any]],
    # Runtime config (captured per request, same as call_agent closure)
    base_thread_id: str,
    parent_checkpoint_ns: str,
    subagent_isolation_enabled: bool,
    subagent_result_max_chars: int,
    execution_timeout_seconds: float,
):
    """Return an async node function for the subagent spawner.

    The spawner reads ``domain_plans`` from state (produced by
    ``domain_planner``), and for each domain:

    1. Creates a micro-plan via LLM  (mini_planner)
    2. Invokes the domain's worker with full isolation
       (subagent_id, checkpoint_ns, sandbox_scope)
    3. Evaluates the result via LLM  (mini_critic)
    4. Retries with adaptive thresholds if needed  (adaptive_guard)
    5. Builds a proper handoff contract identical to call_agent's

    Each worker can in turn call call_agent recursively, enabling
    nested subagent spawning.
    """

    async def _run_mini_planner(
        domain: str,
        plan_data: dict[str, Any],
        user_query: str,
    ) -> list[dict[str, Any]]:
        """LLM-driven micro-plan for a single domain."""
        tools = plan_data.get("tools") or []
        rationale = plan_data.get("rationale") or user_query
        system_msg = SystemMessage(content=mini_planner_prompt_template)
        human_msg = HumanMessage(
            content=(
                f"Domän: {domain}\n"
                f"Fråga: {user_query}\n"
                f"Uppgift: {rationale}\n"
                f"Tillgängliga verktyg: {', '.join(str(t) for t in tools)}"
            )
        )
        try:
            raw = await llm.ainvoke([system_msg, human_msg], max_tokens=400)
            raw_content = str(getattr(raw, "content", "") or "")
            parsed = extract_first_json_object_fn(raw_content)
            steps = parsed.get("steps", [])[:_MAX_MINI_PLAN_STEPS]
            logger.info(
                "mini_planner[%s]: %d steps planned",
                domain,
                len(steps),
            )
            return steps
        except Exception:
            logger.exception("mini_planner[%s]: failed, using fallback", domain)
            first_tool = str(tools[0]) if tools else "unknown"
            return [{"action": "query", "tool_id": first_tool}]

    async def _run_mini_critic(
        domain: str,
        response_text: str,
        used_tools: list[str],
        user_query: str,
    ) -> dict[str, Any]:
        """LLM-driven evaluation of domain worker result."""
        system_msg = SystemMessage(content=mini_critic_prompt_template)
        human_msg = HumanMessage(
            content=(
                f"Domän: {domain}\n"
                f"Fråga: {user_query}\n"
                f"Använda verktyg: {', '.join(used_tools)}\n"
                f"Svar:\n{response_text[:2000]}"
            )
        )
        try:
            raw = await llm.ainvoke([system_msg, human_msg], max_tokens=300)
            raw_content = str(getattr(raw, "content", "") or "")
            parsed = extract_first_json_object_fn(raw_content)
            return {
                "decision": parsed.get("decision", "ok"),
                "feedback": parsed.get("feedback", ""),
            }
        except Exception:
            logger.exception("mini_critic[%s]: failed, defaulting to ok", domain)
            return {"decision": "ok", "feedback": ""}

    def _run_adaptive_guard(retry_count: int) -> dict[str, Any]:
        """Check budget and adjust thresholds (P4.2a).

        Returns adaptive thresholds dict. If force_synthesis is True,
        the mini-graph should stop retrying.
        """
        force = retry_count >= _MAX_MINI_RETRIES
        confidence = max(0.3, 0.7 - (retry_count * 0.15))
        max_tools = max(1, 4 - retry_count)
        return {
            "force_synthesis": force,
            "adjusted_confidence_threshold": confidence,
            "adjusted_max_tools": max_tools,
            "steps_remaining": max(0, _MAX_MINI_RETRIES - retry_count),
        }

    async def _invoke_domain_worker(
        *,
        domain: str,
        agent_name: str,
        plan_steps: list[dict[str, Any]],
        tool_ids: list[str],
        user_query: str,
        subagent_id: str,
        turn_key: str,
        attempt: int,
        critic_feedback: str = "",
    ) -> dict[str, Any]:
        """Invoke a domain worker with full isolation.

        Uses the exact same pattern as call_agent in supervisor_agent.py:
        1. Get worker from pool
        2. Build isolated worker state (subagent_id, sandbox_scope)
        3. Build isolated checkpoint config
        4. worker.ainvoke() with timeout

        Returns the raw worker result dict.
        """
        worker = await worker_pool.get(agent_name)
        if worker is None:
            raise RuntimeError(
                f"Worker '{agent_name}' not available in worker pool"
            )

        # Format the task for the worker with the micro-plan
        plan_text = json.dumps(plan_steps, ensure_ascii=False, default=str)
        retry_hint = ""
        if attempt > 0 and critic_feedback:
            retry_hint = (
                f"\n\nDetta är retry #{attempt}. "
                f"Tidigare feedback: {critic_feedback}"
            )
        task_for_worker = (
            f"Domän: {domain}\n"
            f"Fråga: {user_query}\n"
            f"Mikroplan:\n{plan_text}"
            f"{retry_hint}"
        )

        # Build system prompt with spawner context
        system_content = (
            f"Du är en isolerad subagent för domänen '{domain}'.\n"
            f"subagent_id={subagent_id}\n"
            f"Följ mikroplanen och använd de tilldelade verktygen.\n"
            f"Svara med ett kompakt resultat."
        )
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=task_for_worker),
        ]

        # Build isolated worker state (same as _build_subagent_worker_state)
        worker_state: dict[str, Any] = {
            "messages": list(messages),
            "selected_tool_ids": list(tool_ids),
        }
        if subagent_isolation_enabled and subagent_id:
            worker_state["subagent_id"] = subagent_id
            worker_state["sandbox_scope_mode"] = "subagent"
            worker_state["sandbox_scope_id"] = subagent_id

        # Build isolated checkpoint config
        worker_thread_id = f"{base_thread_id}:mini_{domain}:{turn_key}"
        if subagent_isolation_enabled and subagent_id:
            worker_thread_id = f"{worker_thread_id}:{subagent_id}"
        worker_configurable: dict[str, Any] = {"thread_id": worker_thread_id}
        if parent_checkpoint_ns:
            if subagent_isolation_enabled and subagent_id:
                worker_configurable["checkpoint_ns"] = (
                    f"{parent_checkpoint_ns}:subagent:mini_{domain}:{subagent_id}"
                )
            else:
                worker_configurable["checkpoint_ns"] = (
                    f"{parent_checkpoint_ns}:worker:mini_{domain}"
                )
        config = {
            "configurable": worker_configurable,
            "recursion_limit": 12,
        }

        # Invoke worker with timeout (same as call_agent)
        result = await asyncio.wait_for(
            worker.ainvoke(worker_state, config=config),
            timeout=float(execution_timeout_seconds),
        )
        return result

    async def _run_single_domain(
        domain: str,
        plan_data: dict[str, Any],
        call_index: int,
        user_query: str,
        turn_key: str,
    ) -> dict[str, Any]:
        """Execute a complete mini-graph loop for one domain.

        1. mini_planner  → create micro-plan
        2. worker invoke → real tool execution with isolation
        3. mini_critic   → evaluate result
        4. adaptive_guard → decide retry
        5. Build handoff contract

        Returns a dict with domain, subagent_id, handoff, micro_plan.
        """
        agent_name = domain
        tool_ids = plan_data.get("tools") or [] if isinstance(plan_data, dict) else []

        # Generate unique subagent_id (same pattern as call_agent)
        subagent_id = build_subagent_id_fn(
            base_thread_id=base_thread_id,
            turn_key=turn_key,
            agent_name=f"mini_{domain}",
            call_index=call_index,
            task=user_query,
        )

        # Step 1: Mini-planner — LLM creates micro-plan
        plan_steps = await _run_mini_planner(domain, plan_data, user_query)

        # Step 2-4: Execute → Critic → Adaptive guard loop
        response_text = ""
        used_tools: list[str] = []
        error_text = ""
        critic_feedback = ""

        for attempt in range(_MAX_MINI_RETRIES + 1):
            try:
                result = await _invoke_domain_worker(
                    domain=domain,
                    agent_name=agent_name,
                    plan_steps=plan_steps,
                    tool_ids=tool_ids,
                    user_query=user_query,
                    subagent_id=subagent_id,
                    turn_key=turn_key,
                    attempt=attempt,
                    critic_feedback=critic_feedback,
                )
                response_text = _extract_response_text(result)
                used_tools = _extract_used_tools(result)
                error_text = ""
            except asyncio.TimeoutError:
                error_text = (
                    f"Worker '{agent_name}' timed out after "
                    f"{int(execution_timeout_seconds)}s"
                )
                logger.warning(
                    "mini_executor[%s]: %s (attempt %d)",
                    domain, error_text, attempt,
                )
                break
            except Exception as exc:
                error_text = str(exc)
                logger.exception(
                    "mini_executor[%s]: failed (attempt %d)", domain, attempt,
                )
                break

            # Mini-critic: evaluate the result
            critic_result = await _run_mini_critic(
                domain, response_text, used_tools, user_query,
            )
            logger.info(
                "mini_critic[%s]: decision=%s (attempt %d)",
                domain, critic_result["decision"], attempt,
            )

            if critic_result["decision"] == "ok":
                break

            if critic_result["decision"] == "fail":
                logger.warning(
                    "mini_critic[%s]: fail decision, stopping", domain,
                )
                break

            # Adaptive guard: check retry budget
            guard = _run_adaptive_guard(attempt + 1)
            if guard["force_synthesis"]:
                logger.warning(
                    "adaptive_guard[%s]: forcing synthesis after %d retries",
                    domain, attempt + 1,
                )
                break

            critic_feedback = critic_result.get("feedback", "")

        # Step 5: Build proper handoff contract (same as call_agent)
        handoff = build_handoff_payload_fn(
            subagent_id=subagent_id,
            agent_name=agent_name,
            response_text=response_text,
            result_contract=None,
            result_max_chars=subagent_result_max_chars,
            error_text=error_text,
        )

        return {
            "domain": domain,
            "subagent_id": subagent_id,
            "handoff": handoff,
            "micro_plan": plan_steps,
            "used_tools": used_tools,
        }

    async def subagent_spawner_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        """Spawn parallel mini-graphs per domain from domain_plans.

        Reads ``domain_plans`` (produced by domain_planner) and dispatches
        each domain to an isolated worker via the standard worker pool.
        """
        domain_plans = state.get("domain_plans") or {}
        if not domain_plans:
            logger.info("subagent_spawner: no domain_plans, skipping")
            return {
                "spawned_domains": [],
                "subagent_summaries": [],
                "subagent_handoffs": [],
                "micro_plans": {},
                "convergence_status": None,
                "adaptive_thresholds": None,
            }

        user_query = latest_user_query_fn(state.get("messages") or [])
        turn_key = str(state.get("active_turn_id") or state.get("turn_id") or "turn")

        # Limit concurrency
        semaphore = asyncio.Semaphore(_MAX_PARALLEL_SUBAGENTS)

        async def _run_with_semaphore(
            domain: str,
            plan_data: dict[str, Any],
            idx: int,
        ) -> dict[str, Any]:
            async with semaphore:
                return await _run_single_domain(
                    domain, plan_data, idx, user_query, turn_key,
                )

        # Execute all domains in parallel
        completed = await asyncio.gather(
            *[
                _run_with_semaphore(domain, plan_data, idx)
                for idx, (domain, plan_data) in enumerate(domain_plans.items())
            ],
            return_exceptions=True,
        )

        # Collect results
        spawned_domains: list[str] = []
        subagent_summaries: list[dict[str, Any]] = []
        handoff_updates: list[dict[str, Any]] = []
        micro_plans: dict[str, list[dict[str, Any]]] = {}

        for result in completed:
            if isinstance(result, Exception):
                logger.error("subagent_spawner: mini-graph failed: %s", result)
                continue
            domain_result: dict[str, Any] = result
            domain_name = domain_result["domain"]
            spawned_domains.append(domain_name)
            handoff = domain_result["handoff"]
            # subagent_summaries keeps backward compat for convergence_node
            subagent_summaries.append({
                "domain": domain_name,
                "subagent_id": domain_result["subagent_id"],
                "summary": handoff.get("summary", ""),
                "findings": handoff.get("findings", []),
                "status": handoff.get("status", "partial"),
                "confidence": handoff.get("confidence", 0.0),
                "used_tools": domain_result.get("used_tools", []),
            })
            handoff_updates.append(handoff)
            micro_plans[domain_name] = domain_result["micro_plan"]

        logger.info(
            "subagent_spawner: %d/%d domains completed",
            len(spawned_domains),
            len(domain_plans),
        )

        return {
            "spawned_domains": spawned_domains,
            "subagent_summaries": subagent_summaries,
            "subagent_handoffs": handoff_updates,
            "micro_plans": micro_plans,
            "total_steps": (state.get("total_steps") or 0) + 1,
        }

    return subagent_spawner_node
