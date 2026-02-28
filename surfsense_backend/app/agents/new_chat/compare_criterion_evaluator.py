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
# Without this, 7 models × 4 criteria = 28 simultaneous requests
# overwhelm local LLM servers (LM Studio, Ollama, etc.).
_CRITERION_CONCURRENCY = asyncio.Semaphore(6)

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

        return {
            "criterion": criterion,
            "score": score,
            "reasoning": reasoning,
        }
    except TimeoutError:
        logger.warning("criterion_evaluator[%s/%s]: timeout", model_display_name, criterion)
        return {"criterion": criterion, "score": 50, "reasoning": "Timeout vid bedömning."}
    except Exception as exc:
        logger.warning(
            "criterion_evaluator[%s/%s]: error: %s",
            model_display_name, criterion, exc,
        )
        return {"criterion": criterion, "score": 50, "reasoning": f"Bedömningsfel: {exc}"}


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
) -> dict[str, Any]:
    """Evaluate all 4 criteria for a model response in parallel.

    Args:
        on_criterion_complete: Optional async callback(domain, criterion, score, reasoning)
            called as each criterion completes (for SSE streaming).
        prompt_overrides: Optional dict mapping criterion name to custom prompt.

    Returns:
        {
            "domain": "grok",
            "scores": {"relevans": 85, "djup": 72, "klarhet": 91, "korrekthet": 68},
            "reasonings": {"relevans": "...", "djup": "...", ...},
            "total": 316,
            "evaluated_at_ms": 1234
        }
    """
    start = time.monotonic()

    async def _eval_and_notify(criterion: str) -> dict[str, Any]:
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
        if on_criterion_complete:
            try:
                await on_criterion_complete(
                    domain, criterion, result["score"], result["reasoning"]
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

    for i, criterion in enumerate(CRITERIA):
        r = results[i]
        if isinstance(r, Exception):
            scores[criterion] = 50
            reasonings[criterion] = f"Error: {r}"
        else:
            scores[criterion] = r["score"]
            reasonings[criterion] = r["reasoning"]

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "domain": domain,
        "scores": scores,
        "reasonings": reasonings,
        "total": sum(scores.values()),
        "evaluated_at_ms": elapsed_ms,
    }
