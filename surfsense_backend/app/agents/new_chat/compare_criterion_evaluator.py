"""
Per-model criterion evaluator for compare mode.

Evaluates each model response on 4 dimensions via separate LLM calls:
- relevans:    Does the answer address the core question?
- djup:        How detailed and nuanced is the response?
- klarhet:     How clear and well-structured is the response?
- korrekthet:  How factually correct is the response?

Rate-limiting protection:
- Global semaphore (_GLOBAL_CRITERION_SEM) caps concurrent LLM calls
  across ALL domains.  With 8 domains × 4 criteria = 32 potential calls,
  the semaphore ensures at most _MAX_CONCURRENT run at once.
- Automatic retry with exponential backoff on failure.
- Detailed logging of LLM responses on parse failure (to diagnose
  why score=50 fallbacks occur).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .structured_schemas import (
    CriterionEvalResult,
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)

CRITERIA = ("relevans", "djup", "klarhet", "korrekthet")

# ── Global concurrency control ────────────────────────────────────
# This semaphore is shared across ALL domains and ALL criterion calls.
# 8 domains × 4 criteria = 32 total calls; we allow max 4 at once.
_MAX_CONCURRENT = 4
_GLOBAL_CRITERION_SEM = asyncio.Semaphore(_MAX_CONCURRENT)

# Retry config
_MAX_RETRIES = 2
_RETRY_DELAYS = (2.0, 5.0)  # seconds between retries

_CRITERION_PROMPTS: dict[str, str] = {
    "relevans": (
        "Du är en expert-bedömare som ENBART utvärderar RELEVANS.\n\n"
        "RELEVANS mäter: Besvarar svaret kärnfrågan? Är informationen on-topic?\n"
        "Fokusera ENBART på relevans.\n\n"
        "Regler:\n"
        "- Poäng 0-100 där 0=helt irrelevant, 100=perfekt besvarar hela frågan.\n\n"
        "INSTRUKTIONER FÖR OUTPUT:\n"
        "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
    "djup": (
        "Du är en expert-bedömare som ENBART utvärderar DJUP.\n\n"
        "DJUP mäter: Hur detaljerat och nyanserat är svaret?\n"
        "Fokusera ENBART på djup.\n\n"
        "Regler:\n"
        "- Poäng 0-100 där 0=helt ytligt, 100=exceptionellt djup analys.\n\n"
        "INSTRUKTIONER FÖR OUTPUT:\n"
        "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
    "klarhet": (
        "Du är en expert-bedömare som ENBART utvärderar KLARHET.\n\n"
        "KLARHET mäter: Hur tydligt och välstrukturerat är svaret?\n"
        "Fokusera ENBART på klarhet.\n\n"
        "Regler:\n"
        "- Poäng 0-100 där 0=helt obegripligt, 100=kristallklart.\n\n"
        "INSTRUKTIONER FÖR OUTPUT:\n"
        "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
    "korrekthet": (
        "Du är en expert-bedömare som ENBART utvärderar KORREKTHET.\n\n"
        "KORREKTHET mäter: Hur faktamässigt korrekt är svaret?\n"
        "Fokusera ENBART på korrekthet.\n\n"
        "Regler:\n"
        "- Poäng 0-100 där 0=helt felaktigt, 100=perfekt korrekt.\n\n"
        "INSTRUKTIONER FÖR OUTPUT:\n"
        "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
}


# ── Single criterion LLM call ────────────────────────────────────


async def _invoke_criterion_llm(
    *,
    criterion: str,
    model_response: str,
    user_query: str,
    model_display_name: str,
    research_context: str | None,
    llm: Any,
    extract_json_fn: Any,
    timeout_seconds: float,
    prompt_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make a single criterion LLM call behind the global semaphore.

    Raises on failure so the caller can retry.
    """
    if prompt_overrides and criterion in prompt_overrides:
        prompt = prompt_overrides[criterion]
    else:
        prompt = _CRITERION_PROMPTS.get(criterion, _CRITERION_PROMPTS["relevans"])

    user_content = (
        f"Användarfråga: {user_query}\n\n"
        f"Modell: {model_display_name}\n"
        f"Modellens svar:\n{model_response[:6000]}\n"
    )
    if research_context and criterion == "korrekthet":
        user_content += f"\nResearch-data (webbkällor):\n{research_context[:3000]}\n"

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]

    _invoke_kwargs: dict[str, Any] = {"max_tokens": 300}
    if structured_output_enabled():
        _invoke_kwargs["response_format"] = pydantic_to_response_format(
            CriterionEvalResult, f"criterion_{criterion}"
        )

    async with _GLOBAL_CRITERION_SEM:
        raw = await asyncio.wait_for(
            llm.ainvoke(messages, **_invoke_kwargs),
            timeout=timeout_seconds,
        )

    raw_text = str(getattr(raw, "content", "") or "")

    # Try structured Pydantic parse first
    try:
        _structured = CriterionEvalResult.model_validate_json(raw_text)
        score = max(0, min(100, _structured.score))
        reasoning = _structured.reasoning
        if not reasoning:
            reasoning = f"Bedömningen returnerade poäng {score} utan motivering."
        return {"criterion": criterion, "score": score, "reasoning": reasoning}
    except Exception:
        pass

    # Fallback: extract JSON from raw text
    parsed = extract_json_fn(raw_text)
    if not parsed:
        logger.warning(
            "criterion_evaluator[%s/%s]: LLM returned unparseable response "
            "(len=%d): %.500s",
            model_display_name, criterion, len(raw_text), raw_text,
        )
        raise ValueError(
            f"Unparseable LLM response for {criterion} "
            f"(len={len(raw_text)}): {raw_text[:200]}"
        )

    score_val = parsed.get("score")
    if score_val is None:
        logger.warning(
            "criterion_evaluator[%s/%s]: JSON had no 'score' key. "
            "parsed_keys=%s raw=%.300s",
            model_display_name, criterion, list(parsed.keys()), raw_text,
        )
        raise ValueError(
            f"No 'score' in parsed JSON for {criterion}: keys={list(parsed.keys())}"
        )

    score = max(0, min(100, int(score_val)))
    reasoning = str(parsed.get("reasoning", ""))
    if not reasoning:
        reasoning = f"Bedömningen returnerade poäng {score} utan motivering."

    return {"criterion": criterion, "score": score, "reasoning": reasoning}


# ── Public API: single criterion with retry ──────────────────────


async def evaluate_criterion(
    *,
    criterion: str,
    model_response: str,
    user_query: str,
    model_display_name: str,
    research_context: str | None,
    llm: Any,
    extract_json_fn: Any,
    timeout_seconds: float = 90,
    prompt_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Evaluate a single criterion with automatic retry on failure."""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = await _invoke_criterion_llm(
                criterion=criterion,
                model_response=model_response,
                user_query=user_query,
                model_display_name=model_display_name,
                research_context=research_context,
                llm=llm,
                extract_json_fn=extract_json_fn,
                timeout_seconds=timeout_seconds,
                prompt_overrides=prompt_overrides,
            )
            if attempt > 0:
                logger.info(
                    "criterion_evaluator[%s/%s]: succeeded on retry %d",
                    model_display_name, criterion, attempt,
                )
            return result

        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else 5.0
                logger.warning(
                    "criterion_evaluator[%s/%s]: attempt %d/%d failed (%s), "
                    "retrying in %.1fs",
                    model_display_name, criterion, attempt + 1,
                    _MAX_RETRIES + 1, exc, delay,
                )
                await asyncio.sleep(delay)

    # All retries exhausted
    logger.error(
        "criterion_evaluator[%s/%s]: all %d attempts failed. Last error: %s",
        model_display_name, criterion, _MAX_RETRIES + 1, last_exc,
    )
    return {
        "criterion": criterion,
        "score": 50,
        "reasoning": f"Bedömningsfel efter {_MAX_RETRIES + 1} försök: {last_exc}",
    }


# ── Public API: all 4 criteria for one model ─────────────────────


async def evaluate_model_response(
    *,
    domain: str,
    model_response: str,
    model_display_name: str,
    user_query: str,
    research_context: str | None,
    llm: Any,
    extract_json_fn: Any,
    timeout_seconds: float = 60,
    on_criterion_complete: Any | None = None,
    prompt_overrides: dict[str, str] | None = None,
    acquire_criterion_pod_fn: Any | None = None,
    release_criterion_pod_fn: Any | None = None,
    parent_subagent_id: str = "",
    thread_id: str = "",
) -> dict[str, Any]:
    """Evaluate all 4 criteria for a model response.

    All 4 criteria are launched concurrently via asyncio.gather, but
    actual LLM calls are throttled by the global _GLOBAL_CRITERION_SEM
    (shared across all domains).  This means 8 domains × 4 criteria =
    32 tasks are created, but only _MAX_CONCURRENT LLM calls run at once.
    """
    start = time.monotonic()

    scores: dict[str, int] = {}
    reasonings: dict[str, str] = {}
    pod_info: dict[str, dict[str, Any]] = {}

    async def _eval_and_notify(criterion: str) -> dict[str, Any]:
        crit_start = time.monotonic()

        result = await evaluate_criterion(
            criterion=criterion,
            model_response=model_response,
            user_query=user_query,
            model_display_name=model_display_name,
            research_context=research_context,
            llm=llm,
            extract_json_fn=extract_json_fn,
            timeout_seconds=timeout_seconds,
            prompt_overrides=prompt_overrides,
        )

        crit_latency_ms = int((time.monotonic() - crit_start) * 1000)
        result["latency_ms"] = crit_latency_ms

        if on_criterion_complete:
            try:
                await on_criterion_complete(
                    domain,
                    criterion,
                    result["score"],
                    result["reasoning"],
                    pod_id="",
                    parent_pod_id=parent_subagent_id,
                    latency_ms=crit_latency_ms,
                )
            except Exception:
                pass
        return result

    results = await asyncio.gather(
        *[_eval_and_notify(c) for c in CRITERIA],
        return_exceptions=True,
    )

    for i, criterion in enumerate(CRITERIA):
        r = results[i]
        if isinstance(r, Exception):
            scores[criterion] = 50
            reasonings[criterion] = f"Bedömningsfel: {r}"
            logger.error(
                "criterion_evaluator[%s/%s]: gather returned exception: %s",
                domain, criterion, r,
            )
            if on_criterion_complete:
                try:
                    await on_criterion_complete(
                        domain, criterion, 50, reasonings[criterion],
                        pod_id="", parent_pod_id=parent_subagent_id, latency_ms=0,
                    )
                except Exception:
                    pass
        else:
            scores[criterion] = r["score"]
            reasonings[criterion] = r["reasoning"]

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "domain": domain,
        "scores": scores,
        "reasonings": reasonings,
        "pod_info": pod_info,
        "total": sum(scores.values()),
        "evaluated_at_ms": elapsed_ms,
    }
