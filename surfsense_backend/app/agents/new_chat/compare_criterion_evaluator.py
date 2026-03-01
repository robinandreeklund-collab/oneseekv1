"""
Per-model criterion evaluator for compare mode.

Evaluates each model response on 4 dimensions via parallel LLM calls:
- relevans:    Does the answer address the core question?
- djup:        How detailed and nuanced is the response?
- klarhet:     How clear and well-structured is the response?
- korrekthet:  How factually correct is the response?

Concurrency is capped by _CRITERION_CONCURRENCY to avoid rate-limiting.
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

# Concurrency limit for criterion LLM calls.  A low limit avoids
# rate-limiting from the LLM provider which caused systematic
# score=50 fallbacks (korrekthet always, djup often).
_CRITERION_CONCURRENCY = asyncio.Semaphore(12)

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
    """Evaluate a single criterion for a single model response."""
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

    try:
        _invoke_kwargs: dict[str, Any] = {"max_tokens": 300}
        if structured_output_enabled():
            _invoke_kwargs["response_format"] = pydantic_to_response_format(
                CriterionEvalResult, f"criterion_{criterion}"
            )
        async with _CRITERION_CONCURRENCY:
            raw = await asyncio.wait_for(
                llm.ainvoke(messages, **_invoke_kwargs),
                timeout=timeout_seconds,
            )
        raw_text = str(getattr(raw, "content", "") or "")

        try:
            _structured = CriterionEvalResult.model_validate_json(raw_text)
            score = max(0, min(100, _structured.score))
            reasoning = _structured.reasoning
        except Exception:
            parsed = extract_json_fn(raw_text)
            score = int(parsed.get("score", 50))
            score = max(0, min(100, score))
            reasoning = str(parsed.get("reasoning", ""))

        if not reasoning:
            reasoning = f"Bedömningen returnerade poäng {score} utan motivering."

        return {"criterion": criterion, "score": score, "reasoning": reasoning}

    except TimeoutError:
        logger.warning("criterion_evaluator[%s/%s]: timeout", model_display_name, criterion)
        return {"criterion": criterion, "score": 50, "reasoning": "Timeout vid bedömning."}
    except Exception as exc:
        logger.warning("criterion_evaluator[%s/%s]: error: %s", model_display_name, criterion, exc)
        return {"criterion": criterion, "score": 50, "reasoning": f"Bedömningsfel: {exc}"}


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
    """Evaluate all 4 criteria for a model response via parallel LLM calls."""
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
