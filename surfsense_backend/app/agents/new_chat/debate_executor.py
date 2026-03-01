"""
Debate Supervisor v1: 4-round debate architecture with voting.

Implements a multi-round debate where 7-9 AI participants (6-8 external
models + OneSeek) engage in sequential discussion with chained context.

Architecture:
    resolve_intent
        → debate_domain_planner   (deterministic — all participants)
        → debate_round_executor   (4 rounds: intro → argument × 2 → voting)
        → debate_convergence      (vote aggregation + tiebreaker)
        → debate_synthesizer      (final analysis with podcast data)
        → END

Each round runs participants sequentially in random order with full
context chain — each participant sees all previous responses.
Round 4 (voting) runs in parallel with enforced JSON schema.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.new_chat.debate_prompts import (
    DEFAULT_DEBATE_ANALYSIS_PROMPT,
    DEBATE_ROUND1_INTRO_PROMPT,
    DEBATE_ROUND2_ARGUMENT_PROMPT,
    DEBATE_ROUND3_DEEPENING_PROMPT,
    DEBATE_ROUND4_VOTING_PROMPT,
    ONESEEK_DEBATE_ROUND1_PROMPT,
    ONESEEK_DEBATE_ROUND2_PROMPT,
    ONESEEK_DEBATE_ROUND3_PROMPT,
    ONESEEK_DEBATE_ROUND4_PROMPT,
    ONESEEK_DEBATE_SYSTEM_PROMPT,
)
from app.agents.new_chat.structured_schemas import (
    DebateConvergenceResult,
    DebateVoteResult,
    pydantic_to_response_format,
    structured_output_enabled,
)
from app.agents.new_chat.system_prompt import append_datetime_context
from app.agents.new_chat.tools.external_models import (
    EXTERNAL_MODEL_SPECS,
    call_external_model,
)

logger = logging.getLogger(__name__)

# ─── Round prompts by round number ───────────────────────────────────

ROUND_PROMPTS = {
    1: DEBATE_ROUND1_INTRO_PROMPT,
    2: DEBATE_ROUND2_ARGUMENT_PROMPT,
    3: DEBATE_ROUND3_DEEPENING_PROMPT,
    4: DEBATE_ROUND4_VOTING_PROMPT,
}

# OneSeek-specific per-round prompts (layered on top of system prompt)
ONESEEK_ROUND_PROMPTS = {
    1: ONESEEK_DEBATE_ROUND1_PROMPT,
    2: ONESEEK_DEBATE_ROUND2_PROMPT,
    3: ONESEEK_DEBATE_ROUND3_PROMPT,
    4: ONESEEK_DEBATE_ROUND4_PROMPT,
}

# Maximum token budget per participant response
MAX_RESPONSE_TOKENS = 800
# Voting timeout per model
VOTE_TIMEOUT_SECONDS = 60
# Regular response timeout
RESPONSE_TIMEOUT_SECONDS = 90


# ─── Vote Schema ─────────────────────────────────────────────────────

VOTE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "voted_for": {"type": "string"},
        "short_motivation": {"type": "string", "maxLength": 200},
        "three_bullets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
    },
    "required": ["voted_for", "short_motivation", "three_bullets"],
}


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from text, handling markdown code blocks."""
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting from code blocks
    patterns = [
        r"```(?:json)?\s*\n?(.*?)\n?```",
        r"\{[^{}]*\"voted_for\"[^{}]*\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1) if "```" in pattern else match.group(0))
            except (json.JSONDecodeError, ValueError):
                continue

    return None


def _count_words(text: str) -> int:
    """Count words in a text string."""
    return len(text.split())


def _filter_self_votes(votes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove votes where a participant voted for themselves."""
    return [v for v in votes if v.get("voter", "").lower() != v.get("voted_for", "").lower()]


def _resolve_winner(
    vote_counts: dict[str, int],
    word_counts: dict[str, int],
) -> tuple[str, bool]:
    """Resolve the winner, using word count as tiebreaker.

    Returns (winner_name, tiebreaker_used).
    """
    if not vote_counts:
        return ("", False)

    max_votes = max(vote_counts.values())
    tied = [m for m, v in vote_counts.items() if v == max_votes]

    if len(tied) == 1:
        return (tied[0], False)

    # Tiebreaker: highest total word count
    winner = max(tied, key=lambda m: word_counts.get(m, 0))
    return (winner, True)


# ═══════════════════════════════════════════════════════════════════════
# Node builders
# ═══════════════════════════════════════════════════════════════════════


def build_debate_domain_planner_node(
    *,
    external_model_specs: list[Any] | None = None,
    include_research: bool = True,
):
    """Build deterministic debate domain planner.

    Generates domain_plans with all debate participants.
    """
    specs = external_model_specs or list(EXTERNAL_MODEL_SPECS)

    async def debate_domain_planner_node(
        state: dict[str, Any],
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = state.get("messages", [])

        user_query = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_query = str(msg.content)
                break

        if not user_query:
            return {"domain_plans": {}}

        # Build participant list
        participants: list[dict[str, Any]] = []
        domain_plans: dict[str, dict[str, Any]] = {}

        for spec in specs:
            domain_key = spec.tool_name.replace("call_", "")
            participant = {
                "key": spec.key,
                "display": spec.display,
                "tool_name": spec.tool_name,
                "config_id": spec.config_id,
                "is_oneseek": False,
            }
            participants.append(participant)
            domain_plans[domain_key] = {
                "agent": f"debate_{domain_key}",
                "tools": [spec.tool_name],
                "rationale": f"Debattdeltagare: {spec.display}",
                "spec": {
                    "tool_name": spec.tool_name,
                    "display": spec.display,
                    "key": spec.key,
                    "config_id": spec.config_id,
                },
            }

        if include_research:
            participants.append({
                "key": "oneseek",
                "display": "OneSeek",
                "tool_name": "call_oneseek",
                "config_id": -1,
                "is_oneseek": True,
            })
            domain_plans["research"] = {
                "agent": "debate_oneseek",
                "tools": ["call_oneseek"],
                "rationale": "OneSeek: Svensk AI-agent med realtidsverktyg",
                "is_oneseek": True,
            }

        return {
            "domain_plans": domain_plans,
            "debate_participants": participants,
            "debate_topic": user_query,
            "debate_current_round": 0,
            "debate_round_responses": {},
            "debate_votes": [],
            "debate_word_counts": {},
            "debate_status": "planning",
            "orchestration_phase": f"debate_domain_planner_{len(participants)}",
        }

    return debate_domain_planner_node


def build_debate_round_executor_node(
    *,
    llm: Any,
    call_external_model_fn: Any | None = None,
    tavily_search_fn: Any | None = None,
    execution_timeout_seconds: float = RESPONSE_TIMEOUT_SECONDS,
    prompt_overrides: dict[str, str] | None = None,
):
    """Build the debate round executor.

    Runs all 4 rounds of the debate:
    - Rounds 1-3: Sequential per round, random order, chained context
    - Round 4: Parallel voting with JSON schema enforcement
    """
    _call_external = call_external_model_fn or call_external_model

    async def debate_round_executor_node(
        state: dict[str, Any],
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        participants = state.get("debate_participants", [])
        topic = state.get("debate_topic", "")
        domain_plans = state.get("domain_plans", {})

        if not participants or not topic:
            return {
                "debate_status": "error",
                "debate_round_responses": {},
            }

        all_round_responses: dict[int, dict[str, str]] = {}
        all_word_counts: dict[str, int] = {}
        all_votes: list[dict[str, Any]] = []

        # Emit debate_init
        try:
            from langchain_core.callbacks import adispatch_custom_event
            await adispatch_custom_event(
                "debate_init",
                {
                    "participants": [p["display"] for p in participants],
                    "topic": topic,
                    "total_rounds": 4,
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception:
            pass

        # ─── Rounds 1-3: Sequential with chained context ─────────
        for round_num in range(1, 4):
            round_order = list(participants)
            random.shuffle(round_order)
            round_prompt = ROUND_PROMPTS[round_num]
            round_responses: dict[str, str] = {}

            # Emit round_start
            try:
                await adispatch_custom_event(
                    "debate_round_start",
                    {
                        "round": round_num,
                        "type": ["introduction", "argument", "deepening"][round_num - 1],
                        "order": [p["display"] for p in round_order],
                        "timestamp": time.time(),
                    },
                    config=config,
                )
            except Exception:
                pass

            for position, participant in enumerate(round_order):
                model_key = participant["key"]
                model_display = participant["display"]
                is_oneseek = participant.get("is_oneseek", False)

                # Build context chain: topic + all previous rounds + current round so far
                context_parts = [f"Debattämne: {topic}\n"]

                for prev_round in range(1, round_num):
                    prev_responses = all_round_responses.get(prev_round, {})
                    if prev_responses:
                        context_parts.append(f"\n--- Runda {prev_round} ---")
                        for name, resp in prev_responses.items():
                            context_parts.append(f"[{name}]: {resp[:600]}")

                if round_responses:
                    context_parts.append(f"\n--- Runda {round_num} (hittills) ---")
                    for name, resp in round_responses.items():
                        context_parts.append(f"[{name}]: {resp[:600]}")

                full_context = "\n".join(context_parts)
                query_with_context = f"{round_prompt}\n\n{full_context}"

                # Emit participant_start
                try:
                    await adispatch_custom_event(
                        "debate_participant_start",
                        {
                            "model": model_display,
                            "model_key": model_key,
                            "round": round_num,
                            "position": position + 1,
                            "timestamp": time.time(),
                        },
                        config=config,
                    )
                except Exception:
                    pass

                # Call model
                start_time = time.monotonic()
                response_text = ""

                try:
                    if is_oneseek:
                        # Resolve OneSeek per-round prompt from overrides or defaults
                        _os_round_key = f"debate.oneseek.round.{round_num}"
                        _os_round_prompt = (
                            (prompt_overrides or {}).get(_os_round_key)
                            or ONESEEK_ROUND_PROMPTS.get(round_num, "")
                        )
                        _os_system = (
                            (prompt_overrides or {}).get("debate.oneseek.system")
                            or ONESEEK_DEBATE_SYSTEM_PROMPT
                        )
                        # OneSeek uses internal LLM + optional Tavily
                        response_text = await _run_oneseek_debate_turn(
                            llm=llm,
                            query=query_with_context,
                            tavily_search_fn=tavily_search_fn,
                            topic=topic,
                            round_num=round_num,
                            timeout=execution_timeout_seconds,
                            system_prompt=_os_system,
                            round_prompt=_os_round_prompt,
                        )
                    else:
                        # External model
                        spec_data = None
                        for dp in domain_plans.values():
                            if dp.get("spec", {}).get("key") == model_key:
                                spec_data = dp["spec"]
                                break

                        if spec_data:
                            from types import SimpleNamespace
                            spec = SimpleNamespace(**spec_data)
                            result = await asyncio.wait_for(
                                _call_external(
                                    spec=spec,
                                    query=query_with_context,
                                    system_prompt=round_prompt,
                                ),
                                timeout=execution_timeout_seconds,
                            )
                            response_text = result.get("response", "")
                except asyncio.TimeoutError:
                    response_text = f"[{model_display} timeout efter {execution_timeout_seconds}s]"
                    logger.warning("debate: %s timed out in round %d", model_display, round_num)
                except Exception as exc:
                    response_text = f"[{model_display} fel: {str(exc)[:100]}]"
                    logger.warning("debate: %s error in round %d: %s", model_display, round_num, exc)

                latency_ms = int((time.monotonic() - start_time) * 1000)
                word_count = _count_words(response_text)
                all_word_counts[model_display] = all_word_counts.get(model_display, 0) + word_count
                round_responses[model_display] = response_text

                # Emit participant_end
                try:
                    await adispatch_custom_event(
                        "debate_participant_end",
                        {
                            "model": model_display,
                            "model_key": model_key,
                            "round": round_num,
                            "position": position + 1,
                            "word_count": word_count,
                            "latency_ms": latency_ms,
                            "response_preview": response_text[:300],
                            "timestamp": time.time(),
                        },
                        config=config,
                    )
                except Exception:
                    pass

                # Also emit as tool result for frontend model cards
                try:
                    tool_call_id = f"tc-debate-{model_key}-r{round_num}"
                    tool_name = participant.get("tool_name", f"call_{model_key}")
                    await adispatch_custom_event(
                        "model_response_ready",
                        {
                            "domain": model_key,
                            "tool_call_id": tool_call_id,
                            "tool_name": tool_name,
                            "result": {
                                "status": "success",
                                "response": response_text,
                                "model_display_name": model_display,
                                "latency_ms": latency_ms,
                                "debate_round": round_num,
                                "debate_position": position + 1,
                                "word_count": word_count,
                            },
                            "timestamp": time.time(),
                        },
                        config=config,
                    )
                except Exception:
                    pass

            all_round_responses[round_num] = round_responses

            # Emit round_end
            try:
                await adispatch_custom_event(
                    "debate_round_end",
                    {
                        "round": round_num,
                        "participant_count": len(round_responses),
                        "timestamp": time.time(),
                    },
                    config=config,
                )
            except Exception:
                pass

        # ─── Round 4: Parallel Voting ─────────────────────────────
        round_num = 4
        voting_context_parts = [f"Debattämne: {topic}\n"]
        for rnd in range(1, 4):
            rnd_resp = all_round_responses.get(rnd, {})
            if rnd_resp:
                voting_context_parts.append(f"\n--- Runda {rnd} ---")
                for name, resp in rnd_resp.items():
                    voting_context_parts.append(f"[{name}]: {resp[:600]}")

        voting_context = "\n".join(voting_context_parts)
        voting_query = f"{DEBATE_ROUND4_VOTING_PROMPT}\n\n{voting_context}"

        participant_names = [p["display"] for p in participants]

        # Emit round_start for voting
        try:
            await adispatch_custom_event(
                "debate_round_start",
                {
                    "round": 4,
                    "type": "voting",
                    "order": "parallel",
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception:
            pass

        # Run all votes in parallel
        async def _cast_vote(participant: dict[str, Any]) -> dict[str, Any]:
            model_key = participant["key"]
            model_display = participant["display"]
            is_oneseek = participant.get("is_oneseek", False)

            vote_prompt = (
                f"{voting_query}\n\n"
                f"Du är {model_display}. Rösta INTE på dig själv.\n"
                f"Deltagare att rösta på: {', '.join(n for n in participant_names if n != model_display)}"
            )

            try:
                if is_oneseek:
                    _os_vote_prompt = (
                        (prompt_overrides or {}).get("debate.oneseek.round.4")
                        or ONESEEK_ROUND_PROMPTS.get(4, "")
                    )
                    raw = await asyncio.wait_for(
                        _call_oneseek_vote(llm, vote_prompt, system_hint=_os_vote_prompt),
                        timeout=VOTE_TIMEOUT_SECONDS,
                    )
                else:
                    spec_data = None
                    for dp in domain_plans.values():
                        if dp.get("spec", {}).get("key") == model_key:
                            spec_data = dp["spec"]
                            break

                    if spec_data:
                        from types import SimpleNamespace
                        spec = SimpleNamespace(**spec_data)
                        result = await asyncio.wait_for(
                            _call_external(
                                spec=spec,
                                query=vote_prompt,
                                system_prompt=DEBATE_ROUND4_VOTING_PROMPT,
                            ),
                            timeout=VOTE_TIMEOUT_SECONDS,
                        )
                        raw = result.get("response", "")
                    else:
                        raw = ""

                vote_obj = _extract_json_from_text(raw)
                if vote_obj and "voted_for" in vote_obj:
                    vote_obj["voter"] = model_display
                    vote_obj["voter_key"] = model_key
                    return vote_obj
                else:
                    logger.warning("debate: %s vote parsing failed: %s", model_display, raw[:200])
                    return {
                        "voter": model_display,
                        "voter_key": model_key,
                        "voted_for": "",
                        "short_motivation": "Vote parsing failed",
                        "three_bullets": ["•  —", "•  —", "•  —"],
                        "parse_error": True,
                    }

            except Exception as exc:
                logger.warning("debate: %s vote error: %s", model_display, exc)
                return {
                    "voter": model_display,
                    "voter_key": model_key,
                    "voted_for": "",
                    "short_motivation": f"Error: {str(exc)[:80]}",
                    "three_bullets": ["•  —", "•  —", "•  —"],
                    "error": True,
                }

        vote_tasks = [_cast_vote(p) for p in participants]
        vote_results = await asyncio.gather(*vote_tasks, return_exceptions=True)

        for vr in vote_results:
            if isinstance(vr, Exception):
                logger.warning("debate: vote exception: %s", vr)
                continue
            if isinstance(vr, dict):
                all_votes.append(vr)

                # Emit vote_result
                try:
                    await adispatch_custom_event(
                        "debate_vote_result",
                        {
                            "voter": vr.get("voter", ""),
                            "voted_for": vr.get("voted_for", ""),
                            "motivation": vr.get("short_motivation", ""),
                            "bullets": vr.get("three_bullets", []),
                            "timestamp": time.time(),
                        },
                        config=config,
                    )
                except Exception:
                    pass

        all_round_responses[4] = {
            v.get("voter", ""): json.dumps(v, ensure_ascii=False)
            for v in all_votes
            if isinstance(v, dict)
        }

        return {
            "debate_round_responses": all_round_responses,
            "debate_votes": all_votes,
            "debate_word_counts": all_word_counts,
            "debate_current_round": 4,
            "debate_status": "voting_complete",
        }

    return debate_round_executor_node


async def _run_oneseek_debate_turn(
    *,
    llm: Any,
    query: str,
    tavily_search_fn: Any | None = None,
    topic: str = "",
    round_num: int = 1,
    timeout: float = RESPONSE_TIMEOUT_SECONDS,
    system_prompt: str | None = None,
    round_prompt: str | None = None,
) -> str:
    """Run OneSeek's debate turn with optional Tavily search.

    Simplified P4 pattern: search → synthesize.
    Uses per-round prompt (from admin) layered on top of system prompt.
    """
    search_context = ""

    # Perform Tavily search if available (max 2 searches per turn)
    if tavily_search_fn and topic:
        try:
            search_results = await asyncio.wait_for(
                tavily_search_fn(topic, 3),
                timeout=15,
            )
            if search_results:
                parts = []
                for sr in search_results[:3]:
                    title = sr.get("title", "")
                    content = sr.get("content", "")[:300]
                    url = sr.get("url", "")
                    parts.append(f"- {title}: {content} [{url}]")
                search_context = "\n\nAktuella sökresultat (Tavily):\n" + "\n".join(parts)
        except Exception as exc:
            logger.warning("debate: OneSeek Tavily search failed: %s", exc)

    # Build system prompt: base system + per-round strategy
    base_system = system_prompt or ONESEEK_DEBATE_SYSTEM_PROMPT
    combined_system = append_datetime_context(base_system)
    if round_prompt:
        combined_system = combined_system + "\n\n" + round_prompt

    full_query = query + search_context

    try:
        response = await asyncio.wait_for(
            llm.ainvoke([
                {"role": "system", "content": combined_system},
                {"role": "user", "content": full_query},
            ]),
            timeout=timeout,
        )
        return response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.warning("debate: OneSeek LLM call failed: %s", exc)
        return f"[OneSeek: fel vid generering — {str(exc)[:80]}]"


async def _call_oneseek_vote(
    llm: Any,
    vote_prompt: str,
    system_hint: str = "",
) -> str:
    """OneSeek's vote using internal LLM with structured output."""
    try:
        _invoke_kwargs: dict[str, Any] = {}
        if structured_output_enabled():
            _invoke_kwargs["response_format"] = pydantic_to_response_format(
                DebateVoteResult, "debate_vote"
            )
        _sys = system_hint or "Du röstar i en AI-debatt. Svara med strukturerad JSON."
        response = await llm.ainvoke(
            [
                {"role": "system", "content": _sys},
                {"role": "user", "content": vote_prompt},
            ],
            **_invoke_kwargs,
        )
        raw = response.content if hasattr(response, "content") else str(response)
        # Try structured Pydantic parse first
        if structured_output_enabled():
            try:
                parsed = DebateVoteResult.model_validate_json(raw)
                return json.dumps({
                    "voted_for": parsed.voted_for,
                    "short_motivation": parsed.short_motivation,
                    "three_bullets": parsed.three_bullets,
                }, ensure_ascii=False)
            except Exception:
                pass
        return raw
    except Exception as exc:
        return json.dumps({
            "voted_for": "",
            "short_motivation": f"Error: {str(exc)[:80]}",
            "three_bullets": ["•  —", "•  —", "•  —"],
        })


def build_debate_convergence_node(
    *,
    llm: Any,
    convergence_prompt_template: str,
    latest_user_query_fn: Any,
    extract_first_json_object_fn: Any,
):
    """Build the debate convergence node.

    Aggregates votes, calculates winner, and produces convergence status.
    """

    async def debate_convergence_node(
        state: dict[str, Any],
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        votes = state.get("debate_votes", [])
        word_counts = state.get("debate_word_counts", {})
        round_responses = state.get("debate_round_responses", {})
        topic = state.get("debate_topic", "")

        # Filter self-votes
        filtered_votes = _filter_self_votes(votes)

        # Count votes
        vote_counts: dict[str, int] = {}
        for v in filtered_votes:
            voted_for = v.get("voted_for", "")
            if voted_for:
                vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1

        # Resolve winner
        winner, tiebreaker_used = _resolve_winner(vote_counts, word_counts)

        # Build context for LLM convergence
        context_parts = [f"Debattämne: {topic}\n"]
        context_parts.append(f"Röstresultat: {json.dumps(vote_counts, ensure_ascii=False)}")
        context_parts.append(f"Vinnare: {winner}")
        context_parts.append(f"Tiebreaker använd: {tiebreaker_used}")
        context_parts.append(f"Ordräkning: {json.dumps(word_counts, ensure_ascii=False)}")

        context_parts.append("\nRöster:")
        for v in filtered_votes:
            voter = v.get("voter", "?")
            voted_for = v.get("voted_for", "?")
            motivation = v.get("short_motivation", "")
            context_parts.append(f"  {voter} → {voted_for}: {motivation}")

        # Summary of all rounds
        for rnd in range(1, 4):
            rnd_resp = round_responses.get(rnd, {})
            if rnd_resp:
                context_parts.append(f"\n--- Runda {rnd} sammanfattning ---")
                for name, resp in rnd_resp.items():
                    context_parts.append(f"[{name}]: {resp[:400]}")

        context = "\n".join(context_parts)

        # LLM convergence analysis (with structured output)
        try:
            _invoke_kwargs: dict[str, Any] = {}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    DebateConvergenceResult, "debate_convergence"
                )
            response = await llm.ainvoke(
                [
                    {"role": "system", "content": convergence_prompt_template},
                    {"role": "user", "content": context},
                ],
                **_invoke_kwargs,
            )
            raw_content = response.content if hasattr(response, "content") else str(response)

            # Try structured Pydantic parse first
            if structured_output_enabled():
                try:
                    _structured = DebateConvergenceResult.model_validate_json(raw_content)
                    convergence_obj = _structured.model_dump(exclude={"thinking"})
                except Exception:
                    convergence_obj = extract_first_json_object_fn(raw_content)
            else:
                convergence_obj = extract_first_json_object_fn(raw_content)

            if not convergence_obj:
                convergence_obj = {
                    "merged_summary": raw_content,
                    "overlap_score": 0.5,
                    "conflicts": [],
                    "agreements": [],
                }
        except Exception as exc:
            logger.warning("debate_convergence: LLM error: %s", exc)
            convergence_obj = {
                "merged_summary": f"Convergence failed: {exc}",
                "overlap_score": 0.0,
            }

        # Add vote data to convergence
        convergence_obj["vote_results"] = vote_counts
        convergence_obj["winner"] = winner
        convergence_obj["tiebreaker_used"] = tiebreaker_used
        convergence_obj["word_counts"] = word_counts
        convergence_obj["filtered_votes"] = [
            {k: v for k, v in fv.items() if k not in ("error", "parse_error")}
            for fv in filtered_votes
        ]
        convergence_obj["total_votes_cast"] = len(filtered_votes)
        convergence_obj["self_votes_filtered"] = len(votes) - len(filtered_votes)

        # Emit debate_results
        try:
            from langchain_core.callbacks import adispatch_custom_event
            await adispatch_custom_event(
                "debate_results",
                {
                    "winner": winner,
                    "vote_counts": vote_counts,
                    "tiebreaker_used": tiebreaker_used,
                    "word_counts": word_counts,
                    "total_votes": len(filtered_votes),
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception:
            pass

        return {
            "convergence_status": convergence_obj,
            "debate_status": "convergence_complete",
            "orchestration_phase": "debate_convergence_complete",
        }

    return debate_convergence_node


def build_debate_synthesizer_node(
    *,
    prompt_override: str | None = None,
):
    """Build the debate synthesizer node.

    Produces final debate analysis with structured data for frontend rendering.
    """

    async def debate_synthesizer_node(
        state: dict[str, Any],
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        convergence = state.get("convergence_status") or {}
        round_responses = state.get("debate_round_responses", {})
        topic = state.get("debate_topic", "")
        participants = state.get("debate_participants", [])

        # Build comprehensive context for synthesis
        context_parts = [
            f"Debattämne: {topic}\n",
            f"Antal deltagare: {len(participants)}",
            f"Vinnare: {convergence.get('winner', 'N/A')}",
            f"Röstresultat: {json.dumps(convergence.get('vote_results', {}), ensure_ascii=False)}",
            f"Tiebreaker använd: {convergence.get('tiebreaker_used', False)}",
        ]

        if convergence.get("merged_summary"):
            context_parts.append(f"\nConvergence sammanfattning:\n{convergence['merged_summary']}")

        # All rounds
        for rnd in range(1, 5):
            rnd_resp = round_responses.get(rnd, {})
            if rnd_resp:
                rnd_label = ["Introduktion", "Argument", "Fördjupning", "Röstning"][rnd - 1]
                context_parts.append(f"\n═══ RUNDA {rnd}: {rnd_label} ═══")
                for name, resp in rnd_resp.items():
                    context_parts.append(f"\n[{name}]:\n{resp[:500]}")

        # Votes detail
        filtered_votes = convergence.get("filtered_votes", [])
        if filtered_votes:
            context_parts.append("\n═══ RÖSTDETALJER ═══")
            for v in filtered_votes:
                voter = v.get("voter", "?")
                voted_for = v.get("voted_for", "?")
                motivation = v.get("short_motivation", "")
                bullets = v.get("three_bullets", [])
                context_parts.append(f"{voter} → {voted_for}: {motivation}")
                for b in bullets:
                    context_parts.append(f"  {b}")

        context = "\n".join(context_parts)

        # Load synthesis LLM (reuse passed llm or load from config)
        base_prompt = prompt_override or DEFAULT_DEBATE_ANALYSIS_PROMPT
        synthesis_prompt = append_datetime_context(base_prompt)

        synthesis_messages = [
            {"role": "system", "content": synthesis_prompt},
            {"role": "user", "content": context},
        ]

        try:
            # Try to load synthesis LLM from config
            from app.agents.new_chat.llm_config import (
                create_chat_litellm_from_config,
                load_llm_config_from_yaml,
            )
            llm_config = load_llm_config_from_yaml(-1)
            synth_llm = create_chat_litellm_from_config(llm_config)
        except Exception:
            # Fallback: use whatever LLM is available in state
            synth_llm = None

        final_response = ""
        if synth_llm:
            try:
                response = await synth_llm.ainvoke(synthesis_messages)
                final_response = response.content if hasattr(response, "content") else str(response)
            except Exception as exc:
                logger.warning("debate_synthesizer: LLM error: %s", exc)
                final_response = f"Debate synthesis error: {exc}"
        else:
            # Fallback: build a basic summary without LLM
            final_response = _build_fallback_synthesis(convergence, round_responses, topic)

        # Emit as final message
        try:
            from langchain_core.callbacks import adispatch_custom_event
            await adispatch_custom_event(
                "debate_synthesis_complete",
                {
                    "winner": convergence.get("winner", ""),
                    "vote_counts": convergence.get("vote_results", {}),
                    "synthesis_length": len(final_response),
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception:
            pass

        return {
            "messages": [AIMessage(content=final_response)],
            "debate_status": "complete",
            "orchestration_phase": "debate_synthesis_complete",
        }

    return debate_synthesizer_node


def _build_fallback_synthesis(
    convergence: dict[str, Any],
    round_responses: dict[int, dict[str, str]],
    topic: str,
) -> str:
    """Build a basic synthesis without LLM as fallback."""
    winner = convergence.get("winner", "N/A")
    vote_results = convergence.get("vote_results", {})
    word_counts = convergence.get("word_counts", {})

    parts = [
        f"# Debattresultat: {topic}\n",
        f"## Vinnare: {winner}\n",
        "## Röstresultat\n",
    ]

    for model, votes in sorted(vote_results.items(), key=lambda x: -x[1]):
        parts.append(f"- **{model}**: {votes} röster ({word_counts.get(model, 0)} ord totalt)")

    parts.append(f"\n{convergence.get('merged_summary', '')}")

    return "\n".join(parts)
