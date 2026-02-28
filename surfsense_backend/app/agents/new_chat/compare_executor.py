"""
Compare Supervisor v2: Unified P4 architecture for compare mode.

Replaces the legacy linear pipeline (fan_out → collect → tavily → synthesizer)
with the same P4 infrastructure used by normal mode: isolated subagent
mini-graphs, convergence node, mini-critic, adaptive guard, and proper
handoff contracts.

Each external model + the research agent runs as an isolated subagent
mini-graph through the shared subagent_spawner infrastructure.

Architecture:
    resolve_intent
        → compare_domain_planner  (deterministic — 8 domains always)
        -> compare_subagent_spawner  (P4 mini-graphs x 8 in parallel)
        → compare_convergence  (LLM-driven merge with overlap/conflict)
        → compare_synthesizer  (final synthesis from convergence data)
        → END
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import re
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.new_chat.compare_prompts import DEFAULT_COMPARE_ANALYSIS_PROMPT
from app.agents.new_chat.system_prompt import append_datetime_context
from app.agents.new_chat.tools.external_models import (
    EXTERNAL_MODEL_SPECS,
    call_external_model,
)

logger = logging.getLogger(__name__)


# ─── Compare Domain Planner ──────────────────────────────────────────


def build_compare_domain_planner_node(
    *,
    external_model_specs: list[Any] | None = None,
    include_research: bool = True,
):
    """Build the deterministic compare domain planner node.

    Generates domain_plans in the same format as normal mode's domain_planner,
    but with a fixed set of domains (one per external model + research).
    No LLM call needed — all 8 domains are always included.
    """
    specs = external_model_specs or list(EXTERNAL_MODEL_SPECS)

    async def compare_domain_planner_node(
        state: dict[str, Any],
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = state.get("messages", [])

        # Extract user query
        user_query = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_query = str(msg.content)
                break

        if not user_query:
            return {"domain_plans": {}}

        domain_plans: dict[str, dict[str, Any]] = {}

        # One domain per external model
        for spec in specs:
            domain_key = spec.tool_name.replace("call_", "")
            domain_plans[domain_key] = {
                "agent": f"compare_{domain_key}",
                "tools": [spec.tool_name],
                "rationale": f"Extern modell: {spec.display} ({spec.key})",
                "spec": {
                    "tool_name": spec.tool_name,
                    "display": spec.display,
                    "key": spec.key,
                    "config_id": spec.config_id,
                },
            }

        # Research domain
        if include_research:
            domain_plans["research"] = {
                "agent": "compare_research",
                "tools": ["call_oneseek"],
                "rationale": "Webb-research agent med Tavily-sökning",
            }

        logger.info(
            "compare_domain_planner: %d domains planned",
            len(domain_plans),
        )

        return {
            "domain_plans": domain_plans,
            "orchestration_phase": f"compare_domain_planner_{len(domain_plans)}",
        }

    return compare_domain_planner_node


# ─── Compare Subagent Spawner ────────────────────────────────────────
# This reuses the P4 subagent_spawner pattern but with specialized
# workers for external models and research.


def build_compare_subagent_spawner_node(
    *,
    llm: Any,
    compare_mini_critic_prompt: str,
    latest_user_query_fn: Any,
    extract_first_json_object_fn: Any,
    call_external_model_fn: Any | None = None,
    tavily_search_fn: Any | None = None,
    execution_timeout_seconds: float = 90,
    sandbox_enabled: bool = False,
    sandbox_isolation_enabled: bool = False,
    runtime_hitl_cfg: dict[str, Any] | None = None,
    criterion_prompt_overrides: dict[str, str] | None = None,
):
    """Build the compare-specific subagent spawner.

    Unlike normal mode's subagent_spawner which uses the worker pool,
    this spawner directly manages external model calls and research
    since they have simpler execution patterns (single API call each).

    Each domain gets:
    - Unique subagent_id
    - 4 parallel criterion evaluations (relevans, djup, klarhet, korrekthet)
    - Mini-critic evaluation
    - Adaptive retry (max 1 for external models)
    - Proper handoff contract
    - Sandbox scope isolation (when sandbox_enabled=True):
      Each domain receives sandbox_scope="subagent" and a unique
      sandbox_scope_id, enabling per-model isolated execution environments
      (Docker containers, K8s pods, or local workspaces).
      Note: sandbox_isolation_enabled is respected as an additional gate
      but sandbox_enabled alone is sufficient for lease acquisition.
    """
    _call_external = call_external_model_fn or call_external_model
    _max_retries_external = 1
    _max_retries_research = 2
    _runtime_hitl = dict(runtime_hitl_cfg or {})
    # Sandbox is active if sandbox_enabled=True.  The separate
    # compare_sandbox_isolation flag is an ADDITIONAL opt-in but
    # sandbox_enabled alone is enough to acquire leases.
    _sandbox_active = bool(sandbox_enabled)

    def _build_sandbox_hitl(subagent_id: str) -> dict[str, Any]:
        """Build per-domain runtime_hitl with sandbox scope set to subagent."""
        hitl = dict(_runtime_hitl)
        hitl["sandbox_scope"] = "subagent"
        hitl["sandbox_scope_id"] = subagent_id
        # Ensure sandbox_enabled is explicitly True in the hitl payload
        # so that sandbox_config_from_runtime_flags picks it up.
        hitl["sandbox_enabled"] = True
        return hitl

    async def _acquire_sandbox_for_domain(
        subagent_id: str,
        thread_id: str,
    ) -> Any:
        """Acquire a sandbox lease for a compare domain (K8s pod / Docker / local).

        Returns the lease object, or None if sandbox is disabled or fails.
        """
        if not _sandbox_active:
            return None
        try:
            from app.agents.new_chat.sandbox_runtime import acquire_sandbox_lease

            hitl = _build_sandbox_hitl(subagent_id)
            lease = await asyncio.to_thread(
                acquire_sandbox_lease,
                thread_id=thread_id,
                runtime_hitl=hitl,
            )
            logger.info(
                "compare_executor[%s]: sandbox lease acquired "
                "(mode=%s, scope=%s, sandbox_id=%s)",
                subagent_id,
                lease.mode,
                lease.scope,
                lease.sandbox_id,
            )
            return lease
        except Exception as exc:
            logger.warning(
                "compare_executor[%s]: sandbox lease failed: %s",
                subagent_id,
                exc,
            )
            return None

    async def _release_sandbox_for_domain(
        subagent_id: str,
        thread_id: str,
    ) -> None:
        """Release sandbox lease when domain completes."""
        if not _sandbox_active:
            return
        try:
            from app.agents.new_chat.sandbox_runtime import release_sandbox_lease

            hitl = _build_sandbox_hitl(subagent_id)
            await asyncio.to_thread(
                release_sandbox_lease,
                thread_id=thread_id,
                runtime_hitl=hitl,
                reason="compare-domain-complete",
            )
        except Exception as exc:
            logger.debug(
                "compare_executor[%s]: sandbox release failed (non-critical): %s",
                subagent_id,
                exc,
            )

    async def _run_external_model_domain(
        domain: str,
        plan_data: dict[str, Any],
        user_query: str,
        subagent_id: str,
        on_criterion_complete: Any | None = None,
        thread_id: str = "",
    ) -> dict[str, Any]:
        """Execute a single external model as a subagent."""
        spec_data = plan_data.get("spec", {})
        start_time = time.monotonic()
        result: dict[str, Any] = {}
        error_text = ""

        # Acquire sandbox lease (K8s pod / Docker container) for this domain
        lease = await _acquire_sandbox_for_domain(subagent_id, thread_id)

        for attempt in range(_max_retries_external + 1):
            try:
                # Create a minimal spec-like object
                from types import SimpleNamespace

                spec = SimpleNamespace(**spec_data)
                result = await asyncio.wait_for(
                    _call_external(spec=spec, query=user_query),
                    timeout=execution_timeout_seconds,
                )
                error_text = ""
                break
            except TimeoutError:
                error_text = f"Model '{domain}' timed out after {int(execution_timeout_seconds)}s"
                logger.warning(
                    "compare_executor[%s]: timeout (attempt %d)", domain, attempt
                )
            except Exception as exc:
                error_text = str(exc)
                logger.warning(
                    "compare_executor[%s]: error (attempt %d): %s",
                    domain,
                    attempt,
                    exc,
                )

        latency_ms = int((time.monotonic() - start_time) * 1000)

        if error_text:
            result = {
                "status": "error",
                "error": error_text,
                "model_display_name": spec_data.get("display", domain),
                "provider": spec_data.get("provider", ""),
                "latency_ms": latency_ms,
            }

        status = "complete" if result.get("status") == "success" else "error"
        response_text = result.get("response", "")
        confidence = 0.8 if status == "complete" else 0.0

        # Run 4 parallel criterion evaluations if model returned successfully
        criterion_scores: dict[str, int] = {}
        criterion_reasonings: dict[str, str] = {}
        if status == "complete" and response_text:
            try:
                from app.agents.new_chat.compare_criterion_evaluator import (
                    evaluate_model_response,
                )

                eval_result = await evaluate_model_response(
                    domain=domain,
                    model_response=response_text,
                    model_display_name=spec_data.get("display", domain),
                    user_query=user_query,
                    research_context=None,
                    llm=llm,
                    extract_json_fn=extract_first_json_object_fn,
                    timeout_seconds=90,
                    on_criterion_complete=on_criterion_complete,
                    prompt_overrides=criterion_prompt_overrides,
                )
                criterion_scores = eval_result.get("scores", {})
                criterion_reasonings = eval_result.get("reasonings", {})
                # Derive confidence from scores
                avg_score = eval_result.get("total", 200) / 4
                confidence = round(avg_score / 100, 2)
            except Exception as exc:
                logger.warning("compare_executor[%s]: criterion eval failed: %s", domain, exc)

        # Sandbox scope for this domain
        scope_info: dict[str, Any] = {}
        if _sandbox_active:
            scope_info = {
                "sandbox_scope_mode": "subagent",
                "sandbox_scope_id": subagent_id,
            }
            if lease:
                scope_info["sandbox_id"] = lease.sandbox_id
                scope_info["sandbox_mode"] = lease.mode

        # Release sandbox lease (non-blocking, fire-and-forget)
        await _release_sandbox_for_domain(subagent_id, thread_id)

        return {
            "domain": domain,
            "subagent_id": subagent_id,
            "handoff": {
                "subagent_id": subagent_id,
                "agent_name": f"compare_{domain}",
                "status": status,
                "confidence": confidence,
                "summary": (response_text[:500] if response_text else error_text[:200]),
                "findings": [],
                "used_tools": plan_data.get("tools", []),
                "criterion_scores": criterion_scores,
                "criterion_reasonings": criterion_reasonings,
                **scope_info,
            },
            "raw_result": result,
            "micro_plan": [{"action": "call_model", "tool_id": plan_data.get("tools", [None])[0]}],
        }

    async def _run_research_domain(
        user_query: str,
        subagent_id: str,
        thread_id: str = "",
    ) -> dict[str, Any]:
        """Execute the research agent as a subagent."""
        from app.agents.new_chat.compare_research_worker import run_research_executor

        lease = await _acquire_sandbox_for_domain(subagent_id, thread_id)
        start_time = time.monotonic()
        result: dict[str, Any] = {}
        error_text = ""

        try:
            result = await asyncio.wait_for(
                run_research_executor(
                    query=user_query,
                    llm=llm,
                    tavily_search_fn=tavily_search_fn,
                ),
                timeout=execution_timeout_seconds,
            )
        except TimeoutError:
            error_text = f"Research agent timed out after {int(execution_timeout_seconds)}s"
        except Exception as exc:
            error_text = str(exc)
            logger.exception("compare_executor[research]: failed")

        latency_ms = int((time.monotonic() - start_time) * 1000)

        if error_text:
            result = {
                "status": "error",
                "error": error_text,
                "source": "OneSeek Research",
                "model_display_name": "OneSeek Research",
                "latency_ms": latency_ms,
            }

        status = "complete" if result.get("status") in ("success", "partial") else "error"
        response_text = result.get("response", "")
        web_sources = result.get("web_sources", [])
        confidence = min(0.9, 0.3 + 0.1 * len(web_sources)) if status == "complete" else 0.0

        scope_info_r: dict[str, Any] = {}
        if _sandbox_active:
            scope_info_r = {
                "sandbox_scope_mode": "subagent",
                "sandbox_scope_id": subagent_id,
            }
            if lease:
                scope_info_r["sandbox_id"] = lease.sandbox_id
                scope_info_r["sandbox_mode"] = lease.mode

        await _release_sandbox_for_domain(subagent_id, thread_id)

        return {
            "domain": "research",
            "subagent_id": subagent_id,
            "handoff": {
                "subagent_id": subagent_id,
                "agent_name": "compare_research",
                "status": status,
                "confidence": confidence,
                "summary": (response_text[:500] if response_text else error_text[:200]),
                "findings": [
                    f"{src.get('title', 'Webb-källa')} ({src.get('url', '')})"
                    for src in web_sources[:5]
                ],
                "used_tools": ["call_oneseek"],
                **scope_info_r,
            },
            "raw_result": result,
            "micro_plan": [{"action": "web_research", "tool_id": "call_oneseek"}],
        }

    async def compare_subagent_spawner_node(
        state: dict[str, Any],
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Spawn parallel mini-graphs for all compare domains.

        Reads domain_plans and dispatches each domain to its specialized
        executor with proper isolation and handoff contracts.

        Each external model domain:
        1. Calls the external model API
        2. Runs 4 parallel criterion evaluators (relevans, djup, klarhet, korrekthet)
        3. Includes criterion scores in handoff + ToolMessage for frontend
        """
        domain_plans = state.get("domain_plans") or {}
        if not domain_plans:
            logger.info("compare_subagent_spawner: no domain_plans, skipping")
            return {
                "spawned_domains": [],
                "subagent_summaries": [],
                "micro_plans": {},
                "compare_outputs": [],
            }

        messages = state.get("messages", [])
        user_query = latest_user_query_fn(messages)

        # Extract thread_id from config for sandbox lease management
        _configurable = (
            config.get("configurable", {})
            if isinstance(config, dict)
            else getattr(config, "configurable", {}) or {}
        )
        _thread_id = str(_configurable.get("thread_id", "compare"))

        # Dispatch real-time events via LangGraph custom events so that
        # astream_events(v2) emits them immediately (not batched at node end).
        from langchain_core.callbacks import adispatch_custom_event

        # Also collect locally for state return (backward compat).
        criterion_events: list[dict[str, Any]] = []

        async def _on_criterion_complete(
            domain: str, criterion: str, score: int, reasoning: str
        ) -> None:
            event_data = {
                "domain": domain,
                "criterion": criterion,
                "score": score,
                "reasoning": reasoning,
                "timestamp": time.time(),
            }
            criterion_events.append(event_data)
            # Dispatch immediately — picked up by on_custom_event in SSE stream
            try:
                await adispatch_custom_event(
                    "criterion_complete", event_data, config=config,
                )
            except Exception:
                pass  # non-critical: fallback to batched emission

        # Generate subagent IDs with sandbox scope info
        domain_subagent_ids: dict[str, str] = {}
        for domain in domain_plans:
            domain_subagent_ids[domain] = f"sa-compare_{domain}-{uuid.uuid4().hex[:8]}"

        if _sandbox_active:
            logger.info(
                "compare_subagent_spawner: sandbox ENABLED "
                "(mode=%s, scope=subagent, %d domains)",
                _runtime_hitl.get("sandbox_mode", "docker"),
                len(domain_plans),
            )
        else:
            logger.debug(
                "compare_subagent_spawner: sandbox disabled "
                "(sandbox_enabled=%s)",
                sandbox_enabled,
            )

        # Build AI message with tool_calls for frontend model cards
        tool_calls = []
        for domain, plan_data in domain_plans.items():
            tools = plan_data.get("tools", [])
            tool_name = tools[0] if tools else f"call_{domain}"
            tool_call_id = f"tc-{domain_subagent_ids[domain]}"
            tool_calls.append({
                "name": tool_name,
                "args": {"query": user_query},
                "id": tool_call_id,
                "type": "tool_call",
            })

        ai_message = AIMessage(content="", tool_calls=tool_calls)

        # Collect per-model completion events for progressive SSE streaming.
        # Each event carries the full tool_result so the frontend can render
        # model cards as they arrive (not all at once after gather).
        model_complete_events: list[dict[str, Any]] = []

        # Execute all domains in parallel
        semaphore = asyncio.Semaphore(10)

        async def _run_domain(domain: str, plan_data: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                subagent_id = domain_subagent_ids[domain]
                if domain == "research":
                    domain_result = await _run_research_domain(
                        user_query, subagent_id, thread_id=_thread_id,
                    )
                else:
                    domain_result = await _run_external_model_domain(
                        domain, plan_data, user_query, subagent_id,
                        on_criterion_complete=_on_criterion_complete,
                        thread_id=_thread_id,
                    )

                # Fire model-complete event immediately (while other models still run)
                tools = plan_data.get("tools", [])
                tool_name = tools[0] if tools else f"call_{domain}"
                tc_id = f"tc-{domain_subagent_ids[domain]}"
                raw = domain_result.get("raw_result", {})
                handoff = domain_result.get("handoff", {})
                raw_with_scores = {**raw}
                if handoff.get("criterion_scores"):
                    raw_with_scores["criterion_scores"] = handoff["criterion_scores"]
                    raw_with_scores["criterion_reasonings"] = handoff.get("criterion_reasonings", {})
                if handoff.get("sandbox_scope_mode"):
                    raw_with_scores["sandbox_scope"] = handoff["sandbox_scope_mode"]
                    raw_with_scores["sandbox_scope_id"] = handoff.get("sandbox_scope_id", "")

                mc_event = {
                    "domain": domain,
                    "tool_call_id": tc_id,
                    "tool_name": tool_name,
                    "result": raw_with_scores,
                    "timestamp": time.time(),
                }
                model_complete_events.append(mc_event)
                # Dispatch immediately — frontend gets this model card in real-time
                try:
                    await adispatch_custom_event(
                        "model_complete", mc_event, config=config,
                    )
                except Exception:
                    pass  # non-critical: fallback to batched emission

                return domain_result

        completed = await asyncio.gather(
            *[_run_domain(d, p) for d, p in domain_plans.items()],
            return_exceptions=True,
        )

        # Collect results
        spawned_domains: list[str] = []
        subagent_summaries: list[dict[str, Any]] = []
        micro_plans: dict[str, list[dict[str, Any]]] = {}
        compare_outputs: list[dict[str, Any]] = []
        tool_messages: list[ToolMessage] = []

        for i, (domain, plan_data) in enumerate(domain_plans.items()):
            result = completed[i]
            if isinstance(result, Exception):
                logger.error("compare_subagent_spawner[%s]: failed: %s", domain, result)
                # Create error ToolMessage for frontend
                tools = plan_data.get("tools", [])
                tool_name = tools[0] if tools else f"call_{domain}"
                tc_id = f"tc-{domain_subagent_ids[domain]}"
                tool_messages.append(ToolMessage(
                    name=tool_name,
                    content=json.dumps({
                        "status": "error",
                        "error": str(result),
                        "model_display_name": plan_data.get("spec", {}).get("display", domain),
                    }, ensure_ascii=False),
                    tool_call_id=tc_id,
                ))
                continue

            domain_result: dict[str, Any] = result
            domain_name = domain_result["domain"]
            handoff = domain_result["handoff"]

            spawned_domains.append(domain_name)
            subagent_summaries.append({
                "domain": domain_name,
                "subagent_id": domain_result["subagent_id"],
                "summary": handoff.get("summary", ""),
                "findings": handoff.get("findings", []),
                "status": handoff.get("status", "partial"),
                "confidence": handoff.get("confidence", 0.0),
                "used_tools": handoff.get("used_tools", []),
                "criterion_scores": handoff.get("criterion_scores", {}),
                "criterion_reasonings": handoff.get("criterion_reasonings", {}),
            })
            micro_plans[domain_name] = domain_result.get("micro_plan", [])

            # Build compare_outputs for backward compat with frontend
            raw = domain_result.get("raw_result", {})
            tools = plan_data.get("tools", [])
            tool_name = tools[0] if tools else f"call_{domain}"
            tc_id = f"tc-{domain_subagent_ids[domain]}"

            # Inject criterion_scores and sandbox scope into raw result
            raw_with_scores = {**raw}
            if handoff.get("criterion_scores"):
                raw_with_scores["criterion_scores"] = handoff["criterion_scores"]
                raw_with_scores["criterion_reasonings"] = handoff.get("criterion_reasonings", {})
            if handoff.get("sandbox_scope_mode"):
                raw_with_scores["sandbox_scope"] = handoff["sandbox_scope_mode"]
                raw_with_scores["sandbox_scope_id"] = handoff.get("sandbox_scope_id", "")

            compare_outputs.append({
                "tool_name": tool_name,
                "tool_call_id": tc_id,
                "result": raw_with_scores,
                "timestamp": time.time(),
            })

            # Build ToolMessage for frontend rendering (includes scores)
            tool_messages.append(ToolMessage(
                name=tool_name,
                content=json.dumps(raw_with_scores, ensure_ascii=False),
                tool_call_id=tc_id,
            ))

        logger.info(
            "compare_subagent_spawner: %d/%d domains completed, %d criterion events",
            len(spawned_domains),
            len(domain_plans),
            len(criterion_events),
        )

        return {
            "messages": [ai_message, *tool_messages],
            "spawned_domains": spawned_domains,
            "subagent_summaries": subagent_summaries,
            "micro_plans": micro_plans,
            "compare_outputs": compare_outputs,
            "criterion_events": criterion_events,
            "model_complete_events": model_complete_events,
            "total_steps": (state.get("total_steps") or 0) + 1,
        }

    return compare_subagent_spawner_node


# ─── Confidence-Weighted Scoring ─────────────────────────────────────

# Weights: korrekthet (accuracy) is most important, then relevans, then
# djup and klarhet equally.  These can be tuned dynamically in the future.
CRITERION_WEIGHTS: dict[str, float] = {
    "korrekthet": 0.35,
    "relevans": 0.25,
    "djup": 0.20,
    "klarhet": 0.20,
}


def compute_weighted_score(scores: dict[str, int | float]) -> float:
    """Compute confidence-weighted final score from per-criterion scores.

    Returns a score 0-100 (weighted average).
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for criterion, weight in CRITERION_WEIGHTS.items():
        value = scores.get(criterion, 0)
        if isinstance(value, (int, float)):
            weighted_sum += weight * float(value)
            total_weight += weight
    if total_weight == 0.0:
        return 0.0
    return round(weighted_sum / total_weight, 1)


def rank_models_by_weighted_score(
    model_scores: dict[str, dict[str, int | float]],
) -> list[dict[str, Any]]:
    """Rank models by weighted score. Returns sorted list of dicts.

    Each entry: {"domain": "grok", "weighted_score": 82.5, "rank": 1,
                 "scores": {...}, "raw_total": 316}
    """
    ranked: list[dict[str, Any]] = []
    for domain, scores in model_scores.items():
        if domain == "research":
            continue  # Skip research agent from ranking
        if not isinstance(scores, dict):
            continue
        weighted = compute_weighted_score(scores)
        raw_total = sum(
            int(v) for v in scores.values() if isinstance(v, (int, float))
        )
        ranked.append({
            "domain": domain,
            "weighted_score": weighted,
            "raw_total": raw_total,
            "scores": scores,
        })
    ranked.sort(key=lambda x: x["weighted_score"], reverse=True)
    for i, entry in enumerate(ranked):
        entry["rank"] = i + 1
    return ranked


# ─── Compare Synthesis Context ───────────────────────────────────────


def _build_synthesis_from_convergence(
    user_query: str,
    convergence: dict[str, Any],
    summaries: list[dict[str, Any]],
) -> str:
    """Build synthesis context from convergence data + per-domain summaries."""
    blocks = [f"Användarfråga: {user_query}\n"]

    # Convergence overview
    overlap = convergence.get("overlap_score", 0.0)
    conflicts = convergence.get("conflicts", [])
    merged = convergence.get("merged_summary", "")
    if merged:
        blocks.append(f"CONVERGENCE SAMMANFATTNING (overlap: {overlap:.0%}):\n{merged}\n")
    if conflicts:
        blocks.append("KONFLIKTER:")
        for c in conflicts:
            blocks.append(f"  - {c}")
        blocks.append("")

    # Model scores: prefer criterion_scores from handoffs over convergence
    model_scores = convergence.get("model_scores", {})
    # Also collect scores from subagent summaries (criterion evaluator)
    for s in summaries:
        domain = s.get("domain", "unknown")
        cs = s.get("criterion_scores", {})
        if cs and domain not in model_scores:
            model_scores[domain] = cs
    if model_scores:
        blocks.append("PER-MODELL POÄNG (från kriterie-bedömning):")
        for domain, scores in model_scores.items():
            if isinstance(scores, dict):
                blocks.append(
                    f"  {domain}: relevans={scores.get('relevans', 0)}, "
                    f"djup={scores.get('djup', 0)}, "
                    f"klarhet={scores.get('klarhet', 0)}, "
                    f"korrekthet={scores.get('korrekthet', 0)}"
                )
        blocks.append("")

        # Confidence-weighted ranking — this is the DEFINITIVE ranking
        ranked = rank_models_by_weighted_score(model_scores)
        if ranked:
            blocks.append(
                "VIKTAD SLUTRANKING (confidence-weighted convergence):\n"
                "Vikter: korrekthet=35%, relevans=25%, djup=20%, klarhet=20%\n"
                "DENNA RANKING ÄR DEFINITIV — din winner_rationale MÅSTE matcha denna.\n"
            )
            for entry in ranked:
                blocks.append(
                    f"  #{entry['rank']} {entry['domain']}: "
                    f"viktat={entry['weighted_score']}/100, "
                    f"rå_total={entry['raw_total']}/400"
                )
            blocks.append("")

    # Agreements and disagreements
    agreements = convergence.get("agreements", [])
    if agreements:
        blocks.append("KONSENSUS:")
        for a in agreements:
            blocks.append(f"  - {a}")
        blocks.append("")

    disagreements = convergence.get("disagreements", [])
    if disagreements:
        blocks.append("MENINGSSKILJAKTIGHETER:")
        for d in disagreements:
            blocks.append(f"  - {d}")
        blocks.append("")

    unique_insights = convergence.get("unique_insights", {})
    if unique_insights:
        blocks.append("UNIKA INSIKTER:")
        for domain, insight in unique_insights.items():
            blocks.append(f"  - {domain}: {insight}")
        blocks.append("")

    comparative = convergence.get("comparative_summary", "")
    if comparative:
        blocks.append(f"JÄMFÖRANDE ANALYS:\n{comparative}\n")

    # Per-domain summaries
    for s in summaries:
        domain = s.get("domain", "unknown")
        status = s.get("status", "partial")
        confidence = s.get("confidence", 0.0)
        summary = s.get("summary", "")
        findings = s.get("findings", [])

        if domain == "research":
            label = "ONESEEK_RESEARCH (verifierad webb-data)"
        else:
            label = f"MODEL_ANSWER from {domain} (confidence: {confidence:.0%})"

        blocks.append(f"{label}:")
        if summary:
            blocks.append(summary)
        if findings:
            blocks.append("Källor:")
            for f in findings:
                blocks.append(f"  - {f}")
        blocks.append(f"[status: {status}]\n")

    return "\n".join(blocks)


def _build_synthesis_context(
    user_query: str,
    compare_outputs: list[dict[str, Any]],
) -> str:
    """Build context string from compare outputs for synthesis (legacy compat)."""
    blocks = [f"Användarfråga: {user_query}\n"]

    for output in compare_outputs:
        tool_name = output.get("tool_name", "unknown")
        result = output.get("result", {})

        if result.get("status") == "success":
            model_name = result.get("model_display_name", tool_name)
            response = result.get("response", "")
            provider = result.get("provider", "")
            blocks.append(
                f"MODEL_ANSWER from {model_name} ({provider}):\n{response}\n"
            )
        elif result.get("status") == "error":
            model_name = result.get("model_display_name", tool_name)
            error = result.get("error", "Unknown error")
            blocks.append(f"MODEL_ERROR from {model_name}: {error}\n")

    return "\n".join(blocks)


# ─── Synthesis Text Sanitizer ─────────────────────────────────────────

# All JSON field names that smaller LLMs tend to dump as raw JSON outside
# of the intended ```spotlight-arena-data code fence.
_LEAKED_JSON_FIELDS = (
    "search_queries", "search_results", "winner_answer", "winner_rationale",
    "reasoning", "thinking", "arena_analysis", "consensus", "disagreements",
    "unique_contributions", "reliability_notes", "score",
)

# Regex alternation for the field names above
_FIELD_ALT = "|".join(re.escape(f) for f in _LEAKED_JSON_FIELDS)

# Pattern: a JSON object (possibly multi-line) whose first key is one of
# the known leaked fields.  Handles both compact `{ "key": ... }` and
# pretty-printed multi-line variants.
_NAKED_JSON_RE = re.compile(
    r'\{\s*"(?:' + _FIELD_ALT + r')"[\s\S]*?\}(?:\s*\})*',
)

# Pattern: a trailing JSON blob at the end of the text, starting with
# any of the known field names.  Catches cases where the JSON is appended
# after the markdown body without a blank-line separator.
_TRAILING_JSON_RE = re.compile(
    r'\n?\s*\{\s*"(?:' + _FIELD_ALT + r')"[\s\S]*$',
)


def _sanitize_synthesis_text(text: str) -> str:
    """Remove raw JSON blobs that leak into the visible synthesis text.

    Some smaller LLMs dump structured analysis data (search_queries,
    search_results, winner_rationale, etc.) as raw JSON in the response
    instead of properly placing it inside ```spotlight-arena-data fences.

    This function applies multiple overlapping strategies to strip leaked
    JSON robustly — even when the JSON is multi-line or malformed.
    """
    if not text:
        return text

    # 1. Remove the ```spotlight-arena-data block (frontend extracts it separately)
    cleaned = re.sub(
        r"```spotlight-arena-data\s*\n[\s\S]*?```\s*\n?",
        "",
        text,
    )

    # 2. Remove any ```json ... ``` fenced blocks that contain leaked fields
    cleaned = re.sub(
        r"```json\s*\n[\s\S]*?```\s*\n?",
        "",
        cleaned,
    )

    # 3. Strip trailing JSON blob (greedy match to end of text)
    cleaned = _TRAILING_JSON_RE.sub("", cleaned)

    # 4. Strip inline / multi-line naked JSON blobs with known field names
    cleaned = _NAKED_JSON_RE.sub("", cleaned)

    # 5. Line-by-line pass: catch any remaining JSON fragments that the
    #    regex missed (e.g. brace-only lines, partial JSON).
    lines = cleaned.split("\n")
    result_lines: list[str] = []
    brace_depth = 0
    in_json_leak = False
    for line in lines:
        stripped_line = line.strip()

        # Detect start of a naked JSON blob: line starts with { and
        # EITHER contains a known field name OR is just a lone brace
        # (multi-line JSON where fields appear on subsequent lines).
        if not in_json_leak and stripped_line.startswith("{"):
            has_field = any(
                f'"{f}"' in stripped_line for f in _LEAKED_JSON_FIELDS
            )
            is_lone_brace = stripped_line == "{"
            if has_field or is_lone_brace:
                # Peek: count braces to track depth
                brace_depth = stripped_line.count("{") - stripped_line.count("}")
                if brace_depth > 0:
                    in_json_leak = True
                # Even if braces balance on one line, skip it if it has a field
                continue

        if in_json_leak:
            brace_depth += stripped_line.count("{") - stripped_line.count("}")
            if brace_depth <= 0:
                in_json_leak = False
            continue

        result_lines.append(line)

    return "\n".join(result_lines).strip()


# ─── Compare Synthesizer ─────────────────────────────────────────────


def build_compare_synthesizer_node(
    *,
    prompt_override: str | None = None,
):
    """Build the compare synthesizer node.

    Reads convergence_status and subagent_summaries from state (P4 pattern)
    and falls back to compare_outputs for backward compatibility.
    """

    async def compare_synthesizer(
        state: dict[str, Any],
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from app.agents.new_chat.llm_config import (
            create_chat_litellm_from_config,
            load_llm_config_from_yaml,
        )

        messages = state.get("messages", [])
        convergence = state.get("convergence_status") or {}
        subagent_summaries = state.get("subagent_summaries") or []
        compare_outputs = state.get("compare_outputs", [])

        # Extract user query
        user_query = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_query = str(msg.content)
                break

        # Build context: prefer convergence data, fall back to legacy
        if convergence and subagent_summaries:
            context = _build_synthesis_from_convergence(
                user_query, convergence, subagent_summaries
            )
        elif compare_outputs:
            context = _build_synthesis_context(user_query, compare_outputs)
        else:
            return {
                "final_response": "Inga modellsvar tillgängliga för syntes.",
                "orchestration_phase": "compare_synthesis_empty",
            }

        # Load synthesis LLM
        try:
            llm_config = load_llm_config_from_yaml(-1)
            llm = create_chat_litellm_from_config(llm_config)
        except Exception as e:
            return {
                "final_response": f"Error: Could not load synthesis LLM: {e}",
                "orchestration_phase": "compare_synthesis_error",
            }

        # Build prompt
        base_prompt = prompt_override if prompt_override else DEFAULT_COMPARE_ANALYSIS_PROMPT
        synthesis_prompt = append_datetime_context(base_prompt)

        synthesis_messages = [
            {"role": "system", "content": synthesis_prompt},
            {"role": "user", "content": context},
        ]

        try:
            from app.agents.new_chat.structured_schemas import (
                CompareSynthesisResult,
                pydantic_to_response_format,
                structured_output_enabled,
            )

            _invoke_kwargs: dict[str, Any] = {}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    CompareSynthesisResult, "compare_synthesis"
                )

            response = await llm.ainvoke(synthesis_messages, **_invoke_kwargs)
            raw_content = response.content if hasattr(response, "content") else str(response)

            # Parse structured JSON → extract response field
            synthesis_text = raw_content
            if structured_output_enabled():
                try:
                    _structured = CompareSynthesisResult.model_validate_json(raw_content)
                    synthesis_text = _structured.response
                except Exception:
                    # Fallback: try to extract JSON manually
                    try:
                        _obj = json.loads(raw_content)
                        synthesis_text = str(_obj.get("response", raw_content))
                    except (json.JSONDecodeError, ValueError):
                        pass

            # Extract arena analysis JSON before sanitizing (frontend also does this)
            _arena_match = re.search(
                r"```spotlight-arena-data\s*\n([\s\S]*?)```", synthesis_text,
            )
            _parsed_arena: dict[str, Any] | None = None
            if _arena_match:
                try:
                    _parsed_arena = json.loads(_arena_match.group(1))
                except Exception:
                    pass

            # Sanitize: remove raw JSON leakage from visible text
            synthesis_text = _sanitize_synthesis_text(synthesis_text)
            synthesis_message = AIMessage(content=synthesis_text)

            # Compute confidence-weighted ranking for arena data
            all_model_scores = convergence.get("model_scores", {})
            # Also collect scores from subagent summaries
            for s in subagent_summaries:
                domain = s.get("domain", "unknown")
                cs = s.get("criterion_scores", {})
                if cs and domain not in all_model_scores:
                    all_model_scores[domain] = cs
            weighted_ranking = rank_models_by_weighted_score(all_model_scores)

            # Build arena_data: merge backend scores with LLM-generated analysis
            arena_data: dict[str, Any] = {
                "model_scores": all_model_scores,
                "weighted_ranking": weighted_ranking,
                "criterion_weights": CRITERION_WEIGHTS,
                "agreements": convergence.get("agreements", []),
                "disagreements": convergence.get("disagreements", []),
                "unique_insights": convergence.get("unique_insights", {}),
                "comparative_summary": convergence.get("comparative_summary", ""),
                "overlap_score": convergence.get("overlap_score", 0.0),
                "conflicts": convergence.get("conflicts", []),
            }
            # Merge LLM-generated arena_analysis if extracted
            if _parsed_arena and isinstance(_parsed_arena, dict):
                aa = _parsed_arena.get("arena_analysis", _parsed_arena)
                if isinstance(aa, dict):
                    for key in ("consensus", "disagreements", "unique_contributions",
                                "winner_rationale", "reliability_notes"):
                        if key in aa and aa[key]:
                            arena_data[key] = aa[key]

            return {
                "messages": [synthesis_message],
                "final_response": synthesis_text,
                "orchestration_phase": "compare_synthesis_complete",
                "compare_arena_data": arena_data,
            }
        except Exception as e:
            error_msg = f"Error during synthesis: {e}"
            return {
                "messages": [AIMessage(content=error_msg)],
                "final_response": error_msg,
                "orchestration_phase": "compare_synthesis_error",
            }

    return compare_synthesizer


# ─── Legacy compat: keep old function signatures for imports ─────────
# These are no longer used in the graph but may be referenced in tests.


async def compare_fan_out(state: dict[str, Any]) -> dict[str, Any]:
    """Legacy: replaced by compare_domain_planner + compare_subagent_spawner."""
    logger.warning("compare_fan_out: legacy node called, use compare_domain_planner instead")
    return {}


async def compare_collect(state: dict[str, Any]) -> dict[str, Any]:
    """Legacy: replaced by convergence_node."""
    logger.warning("compare_collect: legacy node called, use convergence_node instead")
    return {"orchestration_phase": "compare_collect_legacy"}


async def compare_tavily(state: dict[str, Any]) -> dict[str, Any]:
    """Legacy: replaced by research subagent."""
    logger.warning("compare_tavily: legacy node called, use research subagent instead")
    return {"orchestration_phase": "compare_tavily_legacy"}


async def compare_synthesizer(
    state: dict[str, Any],
    prompt_override: str | None = None,
) -> dict[str, Any]:
    """Legacy: replaced by build_compare_synthesizer_node."""
    node = build_compare_synthesizer_node(prompt_override=prompt_override)
    return await node(state)
