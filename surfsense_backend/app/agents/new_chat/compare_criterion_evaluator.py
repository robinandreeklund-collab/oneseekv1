"""
Per-criterion LLM evaluators for compare mode.

Each external model response is evaluated on 4 isolated dimensions:
- relevans:    Does the answer address the core question?
- djup:        How detailed and nuanced is the response?
- klarhet:     How clear and well-structured is the response?
- korrekthet:  How factually correct is the response?

Each evaluator runs as an independent LLM call to prevent
cross-contamination between scoring dimensions.
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

# Global semaphore to limit concurrent criterion LLM calls.
# 8 models × 4 criteria = 32 simultaneous requests — allow full parallelism
# so all criterion evaluations can run concurrently without serialization.
_CRITERION_CONCURRENCY = asyncio.Semaphore(32)

# ── Criterion-specific prompts ──────────────────────────────────────

_CRITERION_PROMPTS: dict[str, str] = {
    "relevans": (
        "Du är en expert-bedömare som ENBART utvärderar RELEVANS.\n\n"
        "RELEVANS mäter: Besvarar svaret kärnfrågan? Är informationen on-topic?\n"
        "Ignorerar modellen delar av frågan? Svarar den på rätt sak?\n\n"
        "Fokusera ENBART på relevans — bry dig inte om djup, klarhet eller korrekthet.\n\n"
        "Regler:\n"
        "- Poäng 0-100 där 0=helt irrelevant, 100=perfekt besvarar hela frågan.\n"
        "- 90+ = Besvarar frågan fullständigt, alla aspekter täcks.\n"
        "- 70-89 = Besvarar frågan, men missar vissa aspekter.\n"
        "- 50-69 = Delvis relevant, tangerar frågan men missar kärnan.\n"
        "- 30-49 = Svag relevans, mest off-topic.\n"
        "- 0-29 = Irrelevant eller besvarar fel fråga.\n\n"
        "INSTRUKTIONER FÖR OUTPUT:\n"
        "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
    "djup": (
        "Du är en expert-bedömare som ENBART utvärderar DJUP.\n\n"
        "DJUP mäter: Hur detaljerat och nyanserat är svaret?\n"
        "Inkluderar det kontext, bakgrund, nyanser, kantfall?\n"
        "Ger det ytlig eller djupgående analys?\n\n"
        "Fokusera ENBART på djup — bry dig inte om relevans, klarhet eller korrekthet.\n\n"
        "Regler:\n"
        "- Poäng 0-100 där 0=helt ytligt, 100=exceptionellt djup analys.\n"
        "- 90+ = Djupgående analys med nyanser, kontext, bakgrund och kantfall.\n"
        "- 70-89 = Bra djup med flera perspektiv, men saknar nyanser.\n"
        "- 50-69 = Medeldjupt, grundläggande fakta utan analys.\n"
        "- 30-49 = Ytligt, bara en eller två meningar.\n"
        "- 0-29 = Extremt ytligt, ingen substans.\n\n"
        "INSTRUKTIONER FÖR OUTPUT:\n"
        "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
    "klarhet": (
        "Du är en expert-bedömare som ENBART utvärderar KLARHET.\n\n"
        "KLARHET mäter: Hur tydligt och välstrukturerat är svaret?\n"
        "Är det lätt att förstå? Finns tydlig struktur (stycken, listor)?\n"
        "Undviker det onödig jargong? Flödar texten logiskt?\n\n"
        "Fokusera ENBART på klarhet — bry dig inte om relevans, djup eller korrekthet.\n\n"
        "Regler:\n"
        "- Poäng 0-100 där 0=helt obegripligt, 100=kristallklart.\n"
        "- 90+ = Perfekt strukturerat, varje mening bidrar, extremt tydligt.\n"
        "- 70-89 = Tydligt och välstrukturerat, lättläst.\n"
        "- 50-69 = Okej struktur, men kan vara rörig ibland.\n"
        "- 30-49 = Svår att följa, ostrukturerad.\n"
        "- 0-29 = Obegriplig, osammanhängande.\n\n"
        "INSTRUKTIONER FÖR OUTPUT:\n"
        "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
    "korrekthet": (
        "Du är en expert-bedömare som ENBART utvärderar KORREKTHET.\n\n"
        "KORREKTHET mäter: Hur faktamässigt korrekt är svaret?\n"
        "Stämmer siffror, datum, namn? Finns det felaktiga påståenden?\n"
        "Drar modellen ogrundade slutsatser?\n\n"
        "Fokusera ENBART på korrekthet — bry dig inte om relevans, djup eller klarhet.\n\n"
        "Du har tillgång till research-agentens webbdata (om tillgängligt).\n"
        "Jämför modellens påståenden med dessa fakta.\n\n"
        "Regler:\n"
        "- Poäng 0-100 där 0=helt felaktigt, 100=perfekt korrekt.\n"
        "- 90+ = Alla fakta stämmer, inga felaktiga påståenden.\n"
        "- 70-89 = Mestadels korrekt, smärre osäkerheter.\n"
        "- 50-69 = Blandat, vissa fakta stämmer men andra är osäkra.\n"
        "- 30-49 = Flera felaktigheter, opålitligt.\n"
        "- 0-29 = Helt felaktigt eller fabricerade fakta.\n\n"
        "INSTRUKTIONER FÖR OUTPUT:\n"
        "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
        "- Använd INTE <think>-taggar.\n\n"
        "Returnera strikt JSON:\n"
        '{"thinking": "din interna resonering", "score": 85, "reasoning": "En mening som motiverar poängen."}'
    ),
}


# ── Single criterion evaluator ──────────────────────────────────────


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
    """Evaluate a single criterion for a single model response.

    Args:
        prompt_overrides: Optional dict mapping criterion name to custom prompt.
            If provided and contains the criterion, that prompt is used instead
            of the hardcoded default.  This enables admin-editable prompts.

    Returns:
        {"criterion": "relevans", "score": 85, "reasoning": "..."}
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

    _max_attempts = 2

    for attempt in range(_max_attempts):
        try:
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 300}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    CriterionEvalResult, f"criterion_{criterion}"
                )
            # Limit concurrency to avoid overwhelming local LLM servers
            async with _CRITERION_CONCURRENCY:
                raw = await asyncio.wait_for(
                    llm.ainvoke(messages, **_invoke_kwargs),
                    timeout=timeout_seconds,
                )
            raw_text = str(getattr(raw, "content", "") or "")

            # Try structured Pydantic parse first, fall back to regex
            try:
                _structured = CriterionEvalResult.model_validate_json(raw_text)
                score = max(0, min(100, _structured.score))
                reasoning = _structured.reasoning
            except Exception:
                parsed = extract_json_fn(raw_text)
                score = int(parsed.get("score", 50))
                score = max(0, min(100, score))
                reasoning = str(parsed.get("reasoning", ""))

            # If both parsing paths failed to extract a real score/reasoning,
            # retry once before accepting the fallback.
            if not reasoning and score == 50 and attempt < _max_attempts - 1:
                logger.info(
                    "criterion_evaluator[%s/%s]: empty reasoning on attempt %d, retrying",
                    model_display_name, criterion, attempt + 1,
                )
                continue

            if not reasoning:
                reasoning = f"Bedömningen returnerade poäng {score} utan motivering."

            return {
                "criterion": criterion,
                "score": score,
                "reasoning": reasoning,
            }
        except TimeoutError:
            if attempt < _max_attempts - 1:
                logger.info(
                    "criterion_evaluator[%s/%s]: timeout on attempt %d, retrying",
                    model_display_name, criterion, attempt + 1,
                )
                continue
            logger.warning("criterion_evaluator[%s/%s]: timeout", model_display_name, criterion)
            return {"criterion": criterion, "score": 50, "reasoning": "Timeout vid bedömning."}
        except Exception as exc:
            if attempt < _max_attempts - 1:
                logger.info(
                    "criterion_evaluator[%s/%s]: error on attempt %d (%s), retrying",
                    model_display_name, criterion, attempt + 1, exc,
                )
                continue
            logger.warning(
                "criterion_evaluator[%s/%s]: error: %s",
                model_display_name, criterion, exc,
            )
            return {"criterion": criterion, "score": 50, "reasoning": f"Bedömningsfel: {exc}"}

    # Should not reach here, but safety fallback
    return {"criterion": criterion, "score": 50, "reasoning": "Bedömningen misslyckades efter flera försök."}


# ── Parallel evaluation of all 4 criteria ───────────────────────────


async def evaluate_model_response(
    *,
    domain: str,
    model_response: str,
    model_display_name: str,
    user_query: str,
    research_context: str | None,
    llm: Any,
    extract_json_fn: Any,
    timeout_seconds: float = 30,
    on_criterion_complete: Any | None = None,
    prompt_overrides: dict[str, str] | None = None,
    acquire_criterion_pod_fn: Any | None = None,
    release_criterion_pod_fn: Any | None = None,
    parent_subagent_id: str = "",
    thread_id: str = "",
) -> dict[str, Any]:
    """Evaluate all 4 criteria for a model response in parallel.

    Args:
        on_criterion_complete: Optional async callback(domain, criterion, score,
            reasoning, *, pod_id, parent_pod_id, latency_ms) called as each
            criterion completes (for SSE streaming).
        prompt_overrides: Optional dict mapping criterion name to custom prompt.
        acquire_criterion_pod_fn: Optional async fn(domain, criterion, parent_id,
            thread_id) -> (pod_id, lease) for per-criterion sandbox isolation.
        release_criterion_pod_fn: Optional async fn(domain, criterion, scope_id,
            thread_id) for releasing criterion pods.
        parent_subagent_id: Parent domain subagent_id for pod lineage.
        thread_id: Thread ID for sandbox lease management.

    Returns:
        {
            "domain": "grok",
            "scores": {"relevans": 85, "djup": 72, "klarhet": 91, "korrekthet": 68},
            "reasonings": {"relevans": "...", "djup": "...", ...},
            "pod_info": {"relevans": {"pod_id": "...", ...}, ...},
            "total": 316,
            "evaluated_at_ms": 1234
        }
    """
    start = time.monotonic()

    async def _eval_and_notify(criterion: str) -> dict[str, Any]:
        crit_start = time.monotonic()
        pod_id = ""
        lease = None

        # Acquire isolated criterion pod
        if acquire_criterion_pod_fn:
            try:
                pod_id, lease = await acquire_criterion_pod_fn(
                    domain, criterion, parent_subagent_id, thread_id,
                )
            except Exception as exc:
                logger.debug("criterion pod acquire failed: %s", exc)

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

        # Release criterion pod
        if release_criterion_pod_fn and lease:
            scope_id = getattr(lease, "scope_id", "") or ""
            try:
                await release_criterion_pod_fn(
                    domain, criterion, scope_id, thread_id,
                )
            except Exception:
                pass

        # Store pod metadata in result
        result["pod_id"] = pod_id
        result["parent_pod_id"] = parent_subagent_id
        result["latency_ms"] = crit_latency_ms

        if on_criterion_complete:
            try:
                await on_criterion_complete(
                    domain,
                    criterion,
                    result["score"],
                    result["reasoning"],
                    pod_id=pod_id,
                    parent_pod_id=parent_subagent_id,
                    latency_ms=crit_latency_ms,
                )
            except Exception as exc:
                logger.debug("on_criterion_complete callback error: %s", exc)
        return result

    results = await asyncio.gather(
        *[_eval_and_notify(c) for c in CRITERIA],
        return_exceptions=True,
    )

    scores: dict[str, int] = {}
    reasonings: dict[str, str] = {}
    pod_info: dict[str, dict[str, Any]] = {}

    for i, criterion in enumerate(CRITERIA):
        r = results[i]
        if isinstance(r, Exception):
            scores[criterion] = 50
            reasonings[criterion] = f"Bedömningsfel: {r}"
            # Fire callback for failed criterion so frontend can finalize
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
            if r.get("pod_id"):
                pod_info[criterion] = {
                    "pod_id": r["pod_id"],
                    "parent_pod_id": r.get("parent_pod_id", ""),
                    "latency_ms": r.get("latency_ms", 0),
                }

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "domain": domain,
        "scores": scores,
        "reasonings": reasonings,
        "pod_info": pod_info,
        "total": sum(scores.values()),
        "evaluated_at_ms": elapsed_ms,
    }
