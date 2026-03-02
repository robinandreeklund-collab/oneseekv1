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
import uuid
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.new_chat.compare_criterion_evaluator import evaluate_model_response
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
    research_synthesis_prompt: str | None = None,
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

    def _build_sandbox_hitl(subagent_id: str, scope: str = "subagent") -> dict[str, Any]:
        """Build per-domain/criterion runtime_hitl with sandbox scope."""
        hitl = dict(_runtime_hitl)
        hitl["sandbox_scope"] = scope
        hitl["sandbox_scope_id"] = subagent_id
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

    async def _acquire_criterion_pod(
        domain: str,
        criterion: str,
        parent_subagent_id: str,
        thread_id: str,
    ) -> tuple[str, Any]:
        """Acquire an isolated sandbox pod for a single criterion evaluator.

        Returns (pod_id, lease_or_None).  The pod_id is always generated
        even when sandbox is disabled so the frontend can display it.
        """
        pod_id = f"pod-crit-{domain}-{criterion}-{uuid.uuid4().hex[:6]}"
        if not _sandbox_active:
            return pod_id, None
        try:
            from app.agents.new_chat.sandbox_runtime import acquire_sandbox_lease

            scope_id = f"sa-criterion_{domain}_{criterion}_{uuid.uuid4().hex[:8]}"
            hitl = _build_sandbox_hitl(scope_id, scope="criterion")
            lease = await asyncio.to_thread(
                acquire_sandbox_lease,
                thread_id=thread_id,
                runtime_hitl=hitl,
            )
            logger.debug(
                "compare_executor[%s/%s]: criterion pod acquired "
                "(pod_id=%s, sandbox_id=%s, parent=%s)",
                domain, criterion, pod_id, lease.sandbox_id, parent_subagent_id,
            )
            return pod_id, lease
        except Exception as exc:
            logger.debug(
                "compare_executor[%s/%s]: criterion pod failed (non-critical): %s",
                domain, criterion, exc,
            )
            return pod_id, None

    async def _release_criterion_pod(
        domain: str,
        criterion: str,
        scope_id: str,
        thread_id: str,
    ) -> None:
        """Release criterion pod lease."""
        if not _sandbox_active:
            return
        try:
            from app.agents.new_chat.sandbox_runtime import release_sandbox_lease

            hitl = _build_sandbox_hitl(scope_id, scope="criterion")
            await asyncio.to_thread(
                release_sandbox_lease,
                thread_id=thread_id,
                runtime_hitl=hitl,
                reason="criterion-complete",
            )
        except Exception as exc:
            logger.debug(
                "compare_executor[%s/%s]: criterion pod release failed (non-critical): %s",
                domain, criterion, exc,
            )

    async def _run_external_model_domain(
        domain: str,
        plan_data: dict[str, Any],
        user_query: str,
        subagent_id: str,
        on_criterion_complete: Any | None = None,
        thread_id: str = "",
        config: Any = None,
        research_context: str | None = None,
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

        # Emit model_response_ready immediately so frontend can render
        # the card before criterion evaluation starts.
        tools = plan_data.get("tools", [])
        tool_name = tools[0] if tools else f"call_{domain}"
        tc_id = f"tc-{subagent_id}"
        try:
            from langchain_core.callbacks import adispatch_custom_event

            await adispatch_custom_event(
                "model_response_ready",
                {
                    "domain": domain,
                    "tool_call_id": tc_id,
                    "tool_name": tool_name,
                    "result": {**result, "latency_ms": latency_ms},
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception as exc:
            logger.debug(
                "compare_executor[%s]: model_response_ready dispatch failed: %s",
                domain, exc,
            )

        # Run 4 parallel criterion evaluations if model returned successfully
        criterion_scores: dict[str, int] = {}
        criterion_reasonings: dict[str, str] = {}
        criterion_pod_info: dict[str, Any] = {}
        if status == "complete" and response_text:
            # Notify frontend that criterion evaluation is starting for this domain
            try:
                from langchain_core.callbacks import adispatch_custom_event as _dispatch

                await _dispatch(
                    "criterion_evaluation_started",
                    {"domain": domain, "timestamp": time.time()},
                    config=config,
                )
            except Exception as exc:
                logger.debug(
                    "compare_executor[%s]: criterion_evaluation_started dispatch failed: %s",
                    domain, exc,
                )

            try:
                eval_result = await evaluate_model_response(
                    domain=domain,
                    model_response=response_text,
                    model_display_name=spec_data.get("display", domain),
                    user_query=user_query,
                    research_context=research_context,
                    llm=llm,
                    extract_json_fn=extract_first_json_object_fn,
                    timeout_seconds=30,
                    on_criterion_complete=on_criterion_complete,
                    prompt_overrides=criterion_prompt_overrides,
                    # Criterion evaluators are LLM API calls — they run
                    # inside the parent domain pod and do NOT need their
                    # own K8s pods.  Passing None skips pod creation.
                    acquire_criterion_pod_fn=None,
                    release_criterion_pod_fn=None,
                    parent_subagent_id=subagent_id,
                    thread_id=thread_id,
                )
                criterion_scores = eval_result.get("scores", {})
                criterion_reasonings = eval_result.get("reasonings", {})
                criterion_pod_info = eval_result.get("pod_info", {})
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
                "summary": (response_text[:300] if response_text else error_text[:200]),
                "findings": [],
                "used_tools": plan_data.get("tools", []),
                "criterion_scores": criterion_scores,
                "criterion_reasonings": criterion_reasonings,
                "criterion_pod_info": criterion_pod_info,
                **scope_info,
            },
            "raw_result": result,
            "micro_plan": [{"action": "call_model", "tool_id": plan_data.get("tools", [None])[0]}],
        }

    async def _run_research_domain(
        user_query: str,
        subagent_id: str,
        thread_id: str = "",
        config: Any = None,
        on_criterion_complete: Any = None,
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
                    synthesis_prompt=research_synthesis_prompt,
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

        # Emit model_response_ready so the research card appears immediately
        try:
            from langchain_core.callbacks import adispatch_custom_event

            await adispatch_custom_event(
                "model_response_ready",
                {
                    "domain": "research",
                    "tool_call_id": f"tc-{subagent_id}",
                    "tool_name": "call_oneseek",
                    "result": {**result, "latency_ms": latency_ms},
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception as exc:
            logger.debug(
                "compare_executor[research]: model_response_ready dispatch failed: %s",
                exc,
            )

        # Run 4 parallel criterion evaluations (same as external models)
        criterion_scores: dict[str, int] = {}
        criterion_reasonings: dict[str, str] = {}
        criterion_pod_info: dict[str, Any] = {}
        if status == "complete" and response_text:
            try:
                from langchain_core.callbacks import adispatch_custom_event as _dispatch

                await _dispatch(
                    "criterion_evaluation_started",
                    {"domain": "research", "timestamp": time.time()},
                    config=config,
                )
            except Exception as exc:
                logger.debug(
                    "compare_executor[research]: criterion_evaluation_started dispatch failed: %s",
                    exc,
                )

            try:
                eval_result = await evaluate_model_response(
                    domain="research",
                    model_response=response_text,
                    model_display_name="OneSeek Research",
                    user_query=user_query,
                    research_context=response_text,
                    llm=llm,
                    extract_json_fn=extract_first_json_object_fn,
                    timeout_seconds=30,
                    on_criterion_complete=on_criterion_complete,
                    prompt_overrides=criterion_prompt_overrides,
                    acquire_criterion_pod_fn=None,
                    release_criterion_pod_fn=None,
                    parent_subagent_id=subagent_id,
                    thread_id=thread_id,
                )
                criterion_scores = eval_result.get("scores", {})
                criterion_reasonings = eval_result.get("reasonings", {})
                criterion_pod_info = eval_result.get("pod_info", {})
                avg_score = eval_result.get("total", 200) / 4
                confidence = round(avg_score / 100, 2)
            except Exception as exc:
                logger.warning("compare_executor[research]: criterion eval failed: %s", exc)

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
                "summary": (response_text[:300] if response_text else error_text[:200]),
                "findings": [
                    f"{src.get('title', 'Webb-källa')} ({src.get('url', '')})"
                    for src in web_sources[:5]
                ],
                "used_tools": ["call_oneseek"],
                "criterion_scores": criterion_scores,
                "criterion_reasonings": criterion_reasonings,
                "criterion_pod_info": criterion_pod_info,
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
            domain: str,
            criterion: str,
            score: int,
            reasoning: str,
            *,
            pod_id: str = "",
            parent_pod_id: str = "",
            latency_ms: int = 0,
        ) -> None:
            event_data: dict[str, Any] = {
                "domain": domain,
                "criterion": criterion,
                "score": score,
                "reasoning": reasoning,
                "timestamp": time.time(),
            }
            if pod_id:
                event_data["pod_id"] = pod_id
            if parent_pod_id:
                event_data["parent_pod_id"] = parent_pod_id
            if latency_ms:
                event_data["latency_ms"] = latency_ms
            criterion_events.append(event_data)
            # Dispatch immediately — picked up by on_custom_event in SSE stream
            try:
                await adispatch_custom_event(
                    "criterion_complete", event_data, config=config,
                )
            except Exception as exc:
                logger.debug(
                    "compare_executor[%s/%s]: criterion_complete dispatch failed: %s",
                    domain, criterion, exc,
                )

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

        # Shared research context: research domain sets this when complete,
        # external model criterion evaluators can wait for it (BUG-03 fix).
        _research_done = asyncio.Event()
        _research_context_holder: dict[str, str | None] = {"text": None}
        _research_wait_timeout = 15  # seconds to wait for research before proceeding without it

        # Execute all domains in parallel
        semaphore = asyncio.Semaphore(10)

        async def _run_domain(domain: str, plan_data: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                subagent_id = domain_subagent_ids[domain]
                if domain == "research":
                    domain_result = await _run_research_domain(
                        user_query, subagent_id, thread_id=_thread_id,
                        config=config,
                        on_criterion_complete=_on_criterion_complete,
                    )
                    # Store research response for other domains' korrekthet eval
                    raw_res = domain_result.get("raw_result", {})
                    res_text = raw_res.get("response", "")
                    if res_text:
                        _research_context_holder["text"] = res_text
                    _research_done.set()
                else:
                    # Wait for research context before criterion eval (short timeout)
                    research_ctx: str | None = None
                    try:
                        await asyncio.wait_for(
                            _research_done.wait(),
                            timeout=_research_wait_timeout,
                        )
                        research_ctx = _research_context_holder["text"]
                    except TimeoutError:
                        logger.debug(
                            "compare_executor[%s]: research context not available "
                            "within %ds, proceeding without it",
                            domain, _research_wait_timeout,
                        )
                    domain_result = await _run_external_model_domain(
                        domain, plan_data, user_query, subagent_id,
                        on_criterion_complete=_on_criterion_complete,
                        thread_id=_thread_id,
                        config=config,
                        research_context=research_ctx,
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
                if handoff.get("criterion_pod_info"):
                    raw_with_scores["criterion_pod_info"] = handoff["criterion_pod_info"]
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
                except Exception as exc:
                    logger.debug(
                        "compare_executor[%s]: model_complete dispatch failed: %s",
                        domain, exc,
                    )

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
                "criterion_pod_info": handoff.get("criterion_pod_info", {}),
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
            if handoff.get("criterion_pod_info"):
                raw_with_scores["criterion_pod_info"] = handoff["criterion_pod_info"]
            if handoff.get("sandbox_scope_mode"):
                raw_with_scores["sandbox_scope"] = handoff["sandbox_scope_mode"]
                raw_with_scores["sandbox_scope_id"] = handoff.get("sandbox_scope_id", "")

            compare_outputs.append({
                "tool_name": tool_name,
                "tool_call_id": tc_id,
                "result": raw_with_scores,
                "timestamp": time.time(),
            })

            # Build ToolMessage for frontend rendering (includes scores).
            # OPT-08: json.dumps is required here — @assistant-ui/react's
            # makeAssistantToolUI expects content to be a JSON string that
            # it parses into the `result` prop.  Passing a dict directly
            # would change the serialization format and break frontend parsing.
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


# ─── KQ-06: Re-exports for backward compatibility ───────────────────
# The following were extracted into dedicated modules but are re-exported
# here so that existing imports (e.g. supervisor_agent.py) continue to work.

from app.agents.new_chat.compare_scoring import (  # noqa: E402, F401
    CRITERION_WEIGHTS,
    compute_weighted_score,
    rank_models_by_weighted_score,
)
from app.agents.new_chat.compare_synthesizer import (  # noqa: E402, F401
    build_compare_synthesizer_node,
)


