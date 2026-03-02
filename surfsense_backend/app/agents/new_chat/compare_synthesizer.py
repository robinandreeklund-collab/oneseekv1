"""Compare synthesizer: context builders + synthesis node.

Builds the synthesis context from convergence/subagent data and runs
the final LLM synthesis call to produce the arena analysis.

Extracted from compare_executor.py (KQ-06) to keep modules focused.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.new_chat.compare_prompts import DEFAULT_COMPARE_ANALYSIS_PROMPT
from app.agents.new_chat.compare_sanitizer import sanitize_synthesis_text
from app.agents.new_chat.compare_scoring import (
    CRITERION_WEIGHTS,
    rank_models_by_weighted_score,
)
from app.agents.new_chat.system_prompt import append_datetime_context

logger = logging.getLogger(__name__)


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

    # Model scores: prefer handoff criterion_scores (actual isolated evaluator
    # scores) over convergence model_scores (LLM-generated merge scores).
    # This matches the frontend's score priority (BUG-05 fix).
    model_scores: dict[str, Any] = {}
    # First: collect actual criterion_scores from handoff summaries
    for s in summaries:
        domain = s.get("domain", "unknown")
        cs = s.get("criterion_scores", {})
        if cs:
            model_scores[domain] = cs
    # Fill in missing domains from convergence as fallback
    for domain, scores in convergence.get("model_scores", {}).items():
        if domain not in model_scores:
            model_scores[domain] = scores
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


# ─── Compare Synthesizer Node ────────────────────────────────────────


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
                import contextlib
                with contextlib.suppress(Exception):
                    _parsed_arena = json.loads(_arena_match.group(1))

            # Sanitize: remove raw JSON leakage from visible text
            synthesis_text = sanitize_synthesis_text(synthesis_text)
            synthesis_message = AIMessage(content=synthesis_text)

            # Compute confidence-weighted ranking for arena data.
            # Priority: handoff criterion_scores > convergence model_scores
            # (consistent with frontend and synthesis context — BUG-05 fix).
            all_model_scores: dict[str, Any] = {}
            all_model_reasonings: dict[str, dict[str, str]] = {}
            # First: collect actual criterion_scores from handoff summaries
            for s in subagent_summaries:
                domain = s.get("domain", "unknown")
                cs = s.get("criterion_scores", {})
                if cs:
                    all_model_scores[domain] = cs
                cr = s.get("criterion_reasonings", {})
                if cr:
                    all_model_reasonings[domain] = cr
            # Fill in missing domains from convergence as fallback
            for domain, scores in convergence.get("model_scores", {}).items():
                if domain not in all_model_scores:
                    all_model_scores[domain] = scores
            weighted_ranking = rank_models_by_weighted_score(all_model_scores)

            # Build arena_data: merge backend scores with LLM-generated analysis
            arena_data: dict[str, Any] = {
                "model_scores": all_model_scores,
                "model_reasonings": all_model_reasonings,
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
                        if aa.get(key):
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
