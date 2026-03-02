"""
Per-model criterion evaluator for compare mode.

Evaluates each model response on 4 dimensions via separate LLM calls:
- relevans:    Does the answer address the core question?
- djup:        How detailed and nuanced is the response?
- klarhet:     How clear and well-structured is the response?
- korrekthet:  How factually correct is the response?

Concurrency strategy (OPT-02):
- PRIMARY: litellm.batch_completion() batches all 4 criteria for a model
  into a single call, bypassing the LangChain ChatLiteLLM wrapper.
  A batch-level semaphore (_MAX_BATCH_CONCURRENT) limits how many models
  are evaluated simultaneously.
- FALLBACK: Individual llm.ainvoke() calls behind a per-call semaphore
  (_MAX_CONCURRENT) for retries or when batch extraction fails.
- Automatic retry with exponential backoff on failure.
- Detailed logging of LLM responses on parse failure.
"""

from __future__ import annotations

import asyncio
import logging
import time
import weakref
from typing import Any

import litellm

from .structured_schemas import (
    CriterionEvalResult,
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)

CRITERIA = ("relevans", "djup", "klarhet", "korrekthet")

# ── Concurrency control ──────────────────────────────────────────
#
# Two-tier concurrency:
#
# 1. Batch semaphore: limits how many models are evaluated via
#    litellm.batch_completion() simultaneously.  Each batch = 4 LLM calls,
#    so 4 batches = up to 16 concurrent provider requests.
#
# 2. Individual semaphore: limits per-call concurrency for the fallback
#    path (individual evaluate_criterion() calls with retry).
#
# Lazy initialization per event loop: avoids RuntimeError when multiple
# event loops exist (Celery workers, pytest-asyncio, uvicorn reload).

_MAX_BATCH_CONCURRENT = 4  # max simultaneous batch evaluations
_MAX_CONCURRENT = 6  # max individual LLM calls (fallback path)

_loop_semaphores: weakref.WeakValueDictionary[int, asyncio.Semaphore] = (
    weakref.WeakValueDictionary()
)
_loop_batch_semaphores: weakref.WeakValueDictionary[int, asyncio.Semaphore] = (
    weakref.WeakValueDictionary()
)


def _get_criterion_sem() -> asyncio.Semaphore:
    """Return a per-event-loop individual-call semaphore, created lazily."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    sem = _loop_semaphores.get(loop_id)
    if sem is None:
        sem = asyncio.Semaphore(_MAX_CONCURRENT)
        _loop_semaphores[loop_id] = sem
    return sem


def _get_batch_sem() -> asyncio.Semaphore:
    """Return a per-event-loop batch semaphore, created lazily."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    sem = _loop_batch_semaphores.get(loop_id)
    if sem is None:
        sem = asyncio.Semaphore(_MAX_BATCH_CONCURRENT)
        _loop_batch_semaphores[loop_id] = sem
    return sem


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
        '- All intern resonering ska skrivas i "thinking"-fältet.\n'
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
        '- All intern resonering ska skrivas i "thinking"-fältet.\n'
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
        '- All intern resonering ska skrivas i "thinking"-fältet.\n'
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
        '- All intern resonering ska skrivas i "thinking"-fältet.\n'
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
}


# ── Helpers ──────────────────────────────────────────────────────


def _extract_litellm_params(llm: Any) -> dict[str, Any]:
    """Extract litellm-native params from a ChatLiteLLM instance.

    Allows batch_completion() to call the same provider/model without
    going through the LangChain wrapper.
    """
    params: dict[str, Any] = {}
    model = getattr(llm, "model", None) or getattr(llm, "model_name", "")
    if model:
        params["model"] = model
    api_key = getattr(llm, "api_key", None)
    if api_key:
        params["api_key"] = api_key
    api_base = getattr(llm, "api_base", None)
    if api_base:
        params["api_base"] = api_base
    return params


def _build_criterion_messages(
    criterion: str,
    model_response: str,
    user_query: str,
    model_display_name: str,
    research_context: str | None,
    prompt_overrides: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Build the message list for a single criterion evaluation."""
    prompt = (prompt_overrides or {}).get(criterion) or _CRITERION_PROMPTS.get(
        criterion, _CRITERION_PROMPTS["relevans"]
    )
    user_content = (
        f"Användarfråga: {user_query}\n\n"
        f"Modell: {model_display_name}\n"
        f"Modellens svar:\n{model_response[:6000]}\n"
    )
    if research_context and criterion == "korrekthet":
        user_content += f"\nResearch-data (webbkällor):\n{research_context[:3000]}\n"
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]


def _parse_criterion_raw(
    criterion: str,
    raw_text: str,
    model_display_name: str,
    extract_json_fn: Any,
) -> dict[str, Any]:
    """Parse a criterion LLM response into {criterion, score, reasoning}.

    Shared by both batch and individual evaluation paths.
    """
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
            "criterion_evaluator[%s/%s]: unparseable response (len=%d): %.500s",
            model_display_name,
            criterion,
            len(raw_text),
            raw_text,
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
            model_display_name,
            criterion,
            list(parsed.keys()),
            raw_text,
        )
        raise ValueError(
            f"No 'score' in parsed JSON for {criterion}: keys={list(parsed.keys())}"
        )

    score = max(0, min(100, int(score_val)))
    reasoning = str(parsed.get("reasoning", ""))
    if not reasoning:
        reasoning = f"Bedömningen returnerade poäng {score} utan motivering."

    return {"criterion": criterion, "score": score, "reasoning": reasoning}


# ── Batch criterion evaluation (OPT-02) ─────────────────────────


async def _batch_evaluate_criteria(
    *,
    criteria: tuple[str, ...],
    model_response: str,
    user_query: str,
    model_display_name: str,
    research_context: str | None,
    llm: Any,
    extract_json_fn: Any,
    timeout_seconds: float,
    prompt_overrides: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Batch all criterion calls using litellm.batch_completion().

    OPT-02: Uses LiteLLM's batch API to evaluate all criteria for one
    model in a single call.  Benefits over individual llm.ainvoke():
    - Bypasses the LangChain ChatLiteLLM wrapper (reduced per-call overhead)
    - Uses batch-level semaphore (per-model, not per-criterion)
    - LiteLLM's internal ThreadPoolExecutor manages parallelism efficiently
    - Estimated ~30-50% latency reduction under high concurrent load

    Returns list of parsed results.  Raises on total failure so caller
    can fall back to individual evaluate_criterion() calls.
    """
    litellm_params = _extract_litellm_params(llm)
    if "model" not in litellm_params:
        raise ValueError("Cannot extract model name from LLM instance for batch call")

    # Build message lists for all criteria
    all_messages: list[list[dict[str, str]]] = []
    criteria_order: list[str] = list(criteria)
    for criterion in criteria_order:
        all_messages.append(
            _build_criterion_messages(
                criterion,
                model_response,
                user_query,
                model_display_name,
                research_context,
                prompt_overrides,
            )
        )

    # Build batch kwargs
    batch_kwargs: dict[str, Any] = {
        **litellm_params,
        "messages": all_messages,
        "max_tokens": 300,
        "timeout": int(timeout_seconds),
        "max_workers": len(criteria_order),  # one thread per criterion
    }
    if structured_output_enabled():
        batch_kwargs["response_format"] = pydantic_to_response_format(
            CriterionEvalResult, "criterion_batch"
        )

    # Acquire batch semaphore and execute via litellm's batch API
    async with _get_batch_sem():
        responses = await asyncio.to_thread(litellm.batch_completion, **batch_kwargs)

    # Parse results
    parsed: list[dict[str, Any]] = []
    failed_criteria: list[tuple[str, Exception]] = []

    for i, criterion in enumerate(criteria_order):
        r = responses[i]
        if isinstance(r, Exception):
            logger.warning(
                "criterion_evaluator[%s/%s]: batch call failed: %s",
                model_display_name,
                criterion,
                r,
            )
            failed_criteria.append((criterion, r))
            continue
        try:
            raw_text = r.choices[0].message.content or ""
            result = _parse_criterion_raw(
                criterion, raw_text, model_display_name, extract_json_fn
            )
            parsed.append(result)
        except Exception as exc:
            logger.warning(
                "criterion_evaluator[%s/%s]: batch parse failed: %s",
                model_display_name,
                criterion,
                exc,
            )
            failed_criteria.append((criterion, exc))

    if failed_criteria and not parsed:
        # Total failure — raise so caller falls back entirely
        raise ValueError(
            f"All batch criterion calls failed for {model_display_name}: "
            + "; ".join(f"{c}: {e}" for c, e in failed_criteria)
        )

    # Retry failed criteria individually (with per-call semaphore + retry)
    for criterion, _exc in failed_criteria:
        logger.info(
            "criterion_evaluator[%s/%s]: retrying individually after batch failure",
            model_display_name,
            criterion,
        )
        fallback = await evaluate_criterion(
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
        parsed.append(fallback)

    return parsed


# ── Single criterion LLM call (fallback path) ───────────────────


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
    """Make a single criterion LLM call behind the individual semaphore.

    Uses the LangChain ChatLiteLLM wrapper (llm.ainvoke).
    Raises on failure so the caller can retry.
    """
    messages = _build_criterion_messages(
        criterion,
        model_response,
        user_query,
        model_display_name,
        research_context,
        prompt_overrides,
    )

    _invoke_kwargs: dict[str, Any] = {"max_tokens": 300}
    if structured_output_enabled():
        _invoke_kwargs["response_format"] = pydantic_to_response_format(
            CriterionEvalResult, f"criterion_{criterion}"
        )

    async with _get_criterion_sem():
        raw = await asyncio.wait_for(
            llm.ainvoke(messages, **_invoke_kwargs),
            timeout=timeout_seconds,
        )

    raw_text = str(getattr(raw, "content", "") or "")
    return _parse_criterion_raw(
        criterion, raw_text, model_display_name, extract_json_fn
    )


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
    timeout_seconds: float = 30,
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
                    model_display_name,
                    criterion,
                    attempt,
                )
            return result

        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else 5.0
                logger.warning(
                    "criterion_evaluator[%s/%s]: attempt %d/%d failed (%s), "
                    "retrying in %.1fs",
                    model_display_name,
                    criterion,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    # All retries exhausted
    logger.error(
        "criterion_evaluator[%s/%s]: all %d attempts failed. Last error: %s",
        model_display_name,
        criterion,
        _MAX_RETRIES + 1,
        last_exc,
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

    OPT-02: Tries litellm.batch_completion() first (batches all 4 criteria
    in a single call, bypassing the LangChain wrapper).  Falls back to
    individual llm.ainvoke() calls if batch fails.
    """
    start = time.monotonic()

    scores: dict[str, int] = {}
    reasonings: dict[str, str] = {}
    pod_info: dict[str, dict[str, Any]] = {}

    # ── OPT-02: Try batch evaluation first ───────────────────────
    batch_success = False
    try:
        batch_results = await _batch_evaluate_criteria(
            criteria=CRITERIA,
            model_response=model_response,
            user_query=user_query,
            model_display_name=model_display_name,
            research_context=research_context,
            llm=llm,
            extract_json_fn=extract_json_fn,
            timeout_seconds=timeout_seconds,
            prompt_overrides=prompt_overrides,
        )

        batch_latency_ms = int((time.monotonic() - start) * 1000)

        for result in batch_results:
            criterion = result["criterion"]
            scores[criterion] = result["score"]
            reasonings[criterion] = result["reasoning"]

            if on_criterion_complete:
                try:
                    await on_criterion_complete(
                        domain,
                        criterion,
                        result["score"],
                        result["reasoning"],
                        pod_id="",
                        parent_pod_id=parent_subagent_id,
                        latency_ms=batch_latency_ms,
                    )
                except Exception as exc:
                    logger.debug(
                        "criterion_evaluator[%s/%s]: "
                        "on_criterion_complete callback failed: %s",
                        model_display_name,
                        criterion,
                        exc,
                        exc_info=True,
                    )

        batch_success = True
        logger.info(
            "criterion_evaluator[%s]: batch evaluation completed in %dms",
            domain,
            batch_latency_ms,
        )
    except Exception as exc:
        logger.info(
            "criterion_evaluator[%s]: batch evaluation failed (%s), "
            "falling back to individual calls",
            domain,
            exc,
        )

    # ── Fallback: individual evaluation ──────────────────────────
    if not batch_success:

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
                except Exception as exc:
                    logger.debug(
                        "criterion_evaluator[%s/%s]: "
                        "on_criterion_complete callback failed: %s",
                        model_display_name,
                        criterion,
                        exc,
                        exc_info=True,
                    )
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
                    domain,
                    criterion,
                    r,
                )
                if on_criterion_complete:
                    try:
                        await on_criterion_complete(
                            domain,
                            criterion,
                            50,
                            reasonings[criterion],
                            pod_id="",
                            parent_pod_id=parent_subagent_id,
                            latency_ms=0,
                        )
                    except Exception as exc:
                        logger.debug(
                            "criterion_evaluator[%s/%s]: "
                            "on_criterion_complete callback failed: %s",
                            domain,
                            criterion,
                            exc,
                            exc_info=True,
                        )
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
