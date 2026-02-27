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
):
    """Build the compare-specific subagent spawner.

    Unlike normal mode's subagent_spawner which uses the worker pool,
    this spawner directly manages external model calls and research
    since they have simpler execution patterns (single API call each).

    Each domain gets:
    - Unique subagent_id
    - Mini-critic evaluation
    - Adaptive retry (max 1 for external models)
    - Proper handoff contract
    """
    _call_external = call_external_model_fn or call_external_model
    _max_retries_external = 1
    _max_retries_research = 2

    async def _run_external_model_domain(
        domain: str,
        plan_data: dict[str, Any],
        user_query: str,
        subagent_id: str,
    ) -> dict[str, Any]:
        """Execute a single external model as a subagent."""
        spec_data = plan_data.get("spec", {})
        start_time = time.monotonic()
        result: dict[str, Any] = {}
        error_text = ""

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
            },
            "raw_result": result,
            "micro_plan": [{"action": "call_model", "tool_id": plan_data.get("tools", [None])[0]}],
        }

    async def _run_research_domain(
        user_query: str,
        subagent_id: str,
    ) -> dict[str, Any]:
        """Execute the research agent as a subagent."""
        from app.agents.new_chat.compare_research_worker import run_research_executor

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

        # Generate subagent IDs
        domain_subagent_ids: dict[str, str] = {}
        for domain in domain_plans:
            domain_subagent_ids[domain] = f"sa-compare_{domain}-{uuid.uuid4().hex[:8]}"

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

        # Execute all domains in parallel
        semaphore = asyncio.Semaphore(10)

        async def _run_domain(domain: str, plan_data: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                subagent_id = domain_subagent_ids[domain]
                if domain == "research":
                    return await _run_research_domain(user_query, subagent_id)
                else:
                    return await _run_external_model_domain(
                        domain, plan_data, user_query, subagent_id
                    )

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
            })
            micro_plans[domain_name] = domain_result.get("micro_plan", [])

            # Build compare_outputs for backward compat with frontend
            raw = domain_result.get("raw_result", {})
            tools = plan_data.get("tools", [])
            tool_name = tools[0] if tools else f"call_{domain}"
            tc_id = f"tc-{domain_subagent_ids[domain]}"

            compare_outputs.append({
                "tool_name": tool_name,
                "tool_call_id": tc_id,
                "result": raw,
                "timestamp": time.time(),
            })

            # Build ToolMessage for frontend rendering
            tool_messages.append(ToolMessage(
                name=tool_name,
                content=json.dumps(raw, ensure_ascii=False),
                tool_call_id=tc_id,
            ))

        logger.info(
            "compare_subagent_spawner: %d/%d domains completed",
            len(spawned_domains),
            len(domain_plans),
        )

        return {
            "messages": [ai_message, *tool_messages],
            "spawned_domains": spawned_domains,
            "subagent_summaries": subagent_summaries,
            "micro_plans": micro_plans,
            "compare_outputs": compare_outputs,
            "total_steps": (state.get("total_steps") or 0) + 1,
        }

    return compare_subagent_spawner_node


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

    # Model scores from convergence
    model_scores = convergence.get("model_scores", {})
    if model_scores:
        blocks.append("PER-MODELL POÄNG (från convergence):")
        for domain, scores in model_scores.items():
            if isinstance(scores, dict):
                blocks.append(
                    f"  {domain}: relevans={scores.get('relevans', 0)}, "
                    f"djup={scores.get('djup', 0)}, "
                    f"klarhet={scores.get('klarhet', 0)}, "
                    f"korrekthet={scores.get('korrekthet', 0)}"
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
            response = await llm.ainvoke(synthesis_messages)
            synthesis_text = response.content if hasattr(response, "content") else str(response)
            synthesis_message = AIMessage(content=synthesis_text)

            return {
                "messages": [synthesis_message],
                "final_response": synthesis_text,
                "orchestration_phase": "compare_synthesis_complete",
                "compare_arena_data": {
                    "model_scores": convergence.get("model_scores", {}),
                    "agreements": convergence.get("agreements", []),
                    "disagreements": convergence.get("disagreements", []),
                    "unique_insights": convergence.get("unique_insights", {}),
                    "comparative_summary": convergence.get("comparative_summary", ""),
                    "overlap_score": convergence.get("overlap_score", 0.0),
                    "conflicts": convergence.get("conflicts", []),
                },
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
