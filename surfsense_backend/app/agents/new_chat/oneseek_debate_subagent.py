"""
OneSeek Debate Subagent — P4 pattern for debate participation.

.. warning:: **EXPERIMENTAL / NOT YET INTEGRATED**

   This module is NOT used by the active debate pipeline.  The main flow in
   ``debate_executor.py`` calls ``_run_oneseek_debate_turn()`` (a simpler
   single-LLM path) instead of this subagent.  The module is kept for future
   integration once the P4 mini-agent pattern is validated end-to-end.
   See audit item **KQ-07** for background.

Implements the mini-planner → parallel mini-agents → mini-critic → synthesizer
pattern specifically for OneSeek's debate turns.

The subagent runs 6 parallel mini-agents:
1. Tavily Core Search
2. Fresh News
3. Counter-Evidence
4. Swedish Context
5. Fact Consolidation
6. Clarity Agent

Results are merged by the mini-critic and synthesized into a natural debate response.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.agents.new_chat.debate_prompts import ONESEEK_DEBATE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Max 4 Tavily calls across all mini-agents per debate turn
MAX_TAVILY_CALLS_PER_TURN = 4

# OPT-01: Shared semaphore to enforce Tavily call budget across mini-agents
_tavily_semaphore: asyncio.Semaphore | None = None


def _get_tavily_semaphore() -> asyncio.Semaphore:
    """Get or create the Tavily semaphore (OPT-01)."""
    global _tavily_semaphore
    if _tavily_semaphore is None:
        _tavily_semaphore = asyncio.Semaphore(MAX_TAVILY_CALLS_PER_TURN)
    return _tavily_semaphore


def reset_tavily_semaphore() -> None:
    """Reset semaphore between debate turns."""
    global _tavily_semaphore
    _tavily_semaphore = None


async def run_oneseek_debate_subagent(
    *,
    llm: Any,
    topic: str,
    round_context: str,
    round_num: int,
    tavily_search_fn: Any | None = None,
    timeout_seconds: float = 45.0,
) -> str:
    """Run the full P4 subagent pipeline for OneSeek's debate turn.

    Args:
        llm: The LLM instance for synthesis.
        topic: The debate topic.
        round_context: Full context chain from previous rounds.
        round_num: Current round number (1-4).
        tavily_search_fn: Optional Tavily search function.
        timeout_seconds: Timeout for the entire subagent pipeline.

    Returns:
        Synthesized debate response text.
    """
    start = time.monotonic()

    # ─── Phase 1: Mini-Planner (structured plan) ─────────────────
    _create_mini_plan(topic, round_num)  # plan logged but not used further

    # ─── Phase 2: Parallel Mini-Agents ───────────────────────────
    # OPT-01: Reset semaphore for each debate turn
    reset_tavily_semaphore()
    tavily_calls_remaining = MAX_TAVILY_CALLS_PER_TURN

    agent_tasks = {
        "tavily_core": _run_tavily_core(topic, tavily_search_fn, tavily_calls_remaining),
        "fresh_news": _run_fresh_news(topic, tavily_search_fn),
        "counter_evidence": _run_counter_evidence(round_context, llm),
        "swedish_context": _run_swedish_context(topic, tavily_search_fn),
        "fact_consolidation": _run_fact_consolidation(round_context, llm),
        "clarity": _run_clarity_agent(topic, round_context, llm),
    }

    # Run all mini-agents in parallel with overall timeout
    remaining_time = max(5.0, timeout_seconds - (time.monotonic() - start))
    try:
        results = await asyncio.wait_for(
            _gather_mini_agents(agent_tasks),
            timeout=remaining_time,
        )
    except TimeoutError:
        logger.warning("oneseek_debate_subagent: mini-agents timed out after %.1fs", remaining_time)
        results = {}

    # ─── Phase 3: Mini-Critic (quality check) ────────────────────
    # BUG-05: Removed unused llm/topic params
    critic_verdict = await _mini_critic(results)

    # ─── Phase 4: Final Synthesizer ──────────────────────────────
    response = await _synthesize_debate_response(
        llm=llm,
        topic=topic,
        round_context=round_context,
        round_num=round_num,
        mini_agent_results=results,
        critic_verdict=critic_verdict,
    )

    elapsed = time.monotonic() - start
    logger.info(
        "oneseek_debate_subagent: completed in %.1fs, %d agents returned data",
        elapsed,
        sum(1 for v in results.values() if v),
    )

    return response


def _create_mini_plan(topic: str, round_num: int) -> dict[str, Any]:
    """Create structured plan for the debate turn (no LLM, deterministic)."""
    plan = {
        "round": round_num,
        "strategy": "fact-based argumentation with source verification",
        "steps": [
            {"agent": "tavily_core", "purpose": "Search for core facts about topic"},
            {"agent": "fresh_news", "purpose": "Find latest news/developments"},
            {"agent": "counter_evidence", "purpose": "Identify potential counterarguments"},
            {"agent": "swedish_context", "purpose": "Find Swedish-specific data"},
            {"agent": "fact_consolidation", "purpose": "Verify and consolidate facts"},
            {"agent": "clarity", "purpose": "Ensure clear argumentation structure"},
        ],
        "max_tavily_calls": MAX_TAVILY_CALLS_PER_TURN,
    }
    return plan


async def _gather_mini_agents(tasks: dict[str, Any]) -> dict[str, str]:
    """Run all mini-agent coroutines in parallel and collect results."""
    results: dict[str, str] = {}
    gathered = await asyncio.gather(
        *[_wrap_agent(name, coro) for name, coro in tasks.items()],
        return_exceptions=True,
    )
    for item in gathered:
        if isinstance(item, tuple) and len(item) == 2:
            name, result = item
            results[name] = result
    return results


async def _wrap_agent(name: str, coro: Any) -> tuple[str, str]:
    """Wrap a mini-agent coroutine with error handling."""
    try:
        result = await coro
        return (name, str(result or ""))
    except Exception as exc:
        logger.warning("mini-agent %s failed: %s", name, exc)
        return (name, "")


# ─── Mini-Agent Implementations ──────────────────────────────────────


async def _run_tavily_core(
    topic: str,
    tavily_search_fn: Any | None,
    max_calls: int = 2,
) -> str:
    """Tavily Core Search — primary fact-finding."""
    if not tavily_search_fn:
        return ""

    # OPT-01: Acquire semaphore before Tavily call
    sem = _get_tavily_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=1.0)
    except TimeoutError:
        logger.debug("tavily_core: semaphore exhausted, skipping search")
        return ""

    try:
        results = await tavily_search_fn(topic, min(3, max_calls + 1))
        if not results:
            return ""

        parts = []
        for r in results[:3]:
            title = r.get("title", "")
            content = r.get("content", "")[:250]
            url = r.get("url", "")
            parts.append(f"[{title}] {content} ({url})")

        return "TAVILY CORE: " + " | ".join(parts)
    except Exception as exc:
        logger.warning("tavily_core: %s", exc)
        return ""


async def _run_fresh_news(
    topic: str,
    tavily_search_fn: Any | None,
) -> str:
    """Fresh News — find latest developments."""
    if not tavily_search_fn:
        return ""

    # OPT-01: Acquire semaphore before Tavily call
    sem = _get_tavily_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=1.0)
    except TimeoutError:
        logger.debug("fresh_news: semaphore exhausted, skipping search")
        return ""

    try:
        results = await tavily_search_fn(f"{topic} senaste nyheter 2026", 2)
        if not results:
            return ""

        parts = []
        for r in results[:2]:
            parts.append(f"[{r.get('title', '')}] {r.get('content', '')[:200]}")

        return "FRESH NEWS: " + " | ".join(parts)
    except Exception as exc:
        logger.warning("fresh_news: %s", exc)
        return ""


async def _run_counter_evidence(
    round_context: str,
    llm: Any,
) -> str:
    """Counter-Evidence — identify weaknesses in other arguments."""
    try:
        response = await llm.ainvoke([
            {
                "role": "system",
                "content": (
                    "Du identifierar svagheter och motargument i andras debattinlägg. "
                    "Svara kort med 2-3 punkter."
                ),
            },
            {
                "role": "user",
                "content": f"Identifiera svagheter i dessa argument:\n{round_context[:1500]}",
            },
        ])
        return "COUNTER: " + (response.content if hasattr(response, "content") else str(response))
    except Exception as exc:
        logger.warning("counter_evidence: %s", exc)
        return ""


async def _run_swedish_context(
    topic: str,
    tavily_search_fn: Any | None,
) -> str:
    """Swedish Context — find Sweden-specific data."""
    if not tavily_search_fn:
        return ""

    # OPT-01: Acquire semaphore before Tavily call
    sem = _get_tavily_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=1.0)
    except TimeoutError:
        logger.debug("swedish_context: semaphore exhausted, skipping search")
        return ""

    try:
        results = await tavily_search_fn(f"{topic} Sverige SCB Energimyndigheten", 2)
        if not results:
            return ""

        parts = []
        for r in results[:2]:
            parts.append(f"[{r.get('title', '')}] {r.get('content', '')[:200]}")

        return "SWEDISH CONTEXT: " + " | ".join(parts)
    except Exception as exc:
        logger.warning("swedish_context: %s", exc)
        return ""


async def _run_fact_consolidation(
    round_context: str,
    llm: Any,
) -> str:
    """Fact Consolidation — verify and organize facts from context."""
    try:
        response = await llm.ainvoke([
            {
                "role": "system",
                "content": (
                    "Du konsoliderar och verifierar fakta från en debatt. "
                    "Lista bekräftade fakta, osäkra påståenden och felaktigheter. "
                    "Svara kort."
                ),
            },
            {
                "role": "user",
                "content": f"Konsolidera fakta:\n{round_context[:1500]}",
            },
        ])
        return "FACTS: " + (response.content if hasattr(response, "content") else str(response))
    except Exception as exc:
        logger.warning("fact_consolidation: %s", exc)
        return ""


async def _run_clarity_agent(
    topic: str,
    round_context: str,
    llm: Any,
) -> str:
    """Clarity Agent — ensure clear argumentation structure."""
    try:
        response = await llm.ainvoke([
            {
                "role": "system",
                "content": (
                    "Du är expert på argumentationsstruktur. "
                    "Föreslå den tydligaste strukturen för ett debattinlägg om ämnet. "
                    "Svara med 3-4 punkter."
                ),
            },
            {
                "role": "user",
                "content": f"Ämne: {topic}\nKontext: {round_context[:800]}",
            },
        ])
        return "CLARITY: " + (response.content if hasattr(response, "content") else str(response))
    except Exception as exc:
        logger.warning("clarity: %s", exc)
        return ""


async def _mini_critic(
    results: dict[str, str],
) -> dict[str, Any]:
    """Mini-critic: evaluate quality of mini-agent results.

    BUG-05: Removed unused ``llm`` and ``topic`` parameters.
    This performs a quantitative check; for LLM-based quality evaluation,
    see DEFAULT_DEBATE_MINI_CRITIC_PROMPT (future enhancement).
    """
    filled = {k: v for k, v in results.items() if v}
    total = len(results)
    success = len(filled)

    verdict = {
        "decision": "ok" if success >= 3 else ("retry" if success >= 1 else "fail"),
        "agents_success": success,
        "agents_total": total,
        "confidence": min(1.0, success / max(total, 1)),
    }

    return verdict


async def _synthesize_debate_response(
    *,
    llm: Any,
    topic: str,
    round_context: str,
    round_num: int,
    mini_agent_results: dict[str, str],
    critic_verdict: dict[str, Any],
) -> str:
    """Synthesize final debate response from all mini-agent data."""
    # Build synthesis context
    data_parts = []
    for agent_name, result in mini_agent_results.items():
        if result:
            data_parts.append(f"[{agent_name}]: {result[:400]}")

    synthesis_data = "\n".join(data_parts) if data_parts else "Inga sökresultat tillgängliga."

    prompt = (
        f"Du är OneSeek i runda {round_num} av en AI-debatt.\n"
        f"Ämne: {topic}\n\n"
        f"Dina mini-agenter har samlat denna data:\n{synthesis_data}\n\n"
        f"Tidigare argument:\n{round_context[:1500]}\n\n"
        "Skriv ditt debattinlägg. Var faktabaserad, referera till sökresultat, "
        "och bygg vidare på eller utmana andra deltagares argument. "
        "Max 500 ord. Skriv naturligt som i en debatt."
    )

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": ONESEEK_DEBATE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])
        return response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.warning("debate synthesis failed: %s", exc)
        # Fallback: return consolidated facts
        if data_parts:
            return f"Baserat på aktuella sökresultat om {topic}:\n" + "\n".join(
                f"- {d}" for d in data_parts[:3]
            )
        return f"[OneSeek: syntesfel — {str(exc)[:80]}]"
