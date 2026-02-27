"""P3: Multi-query decomposer node.

Runs AFTER intent resolution but BEFORE agent_resolver, ONLY for
``complex``-classified queries.  Decomposes compound user questions into
independent atomic sub-questions with an optional dependency graph so
downstream planner and executor can parallelise where possible.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..structured_schemas import (
    DecomposerResult,
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)


def build_multi_query_decomposer_node(
    *,
    llm: Any,
    decomposer_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
):
    """Return an async node function for the multi-query decomposer.

    The node reads ``graph_complexity`` from state and short-circuits for
    non-complex queries (returning an empty ``atomic_questions`` list so the
    planner falls back to its normal behaviour).
    """

    async def multi_query_decomposer_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        complexity = str(state.get("graph_complexity") or "").strip().lower()
        if complexity != "complex":
            # Simple/trivial queries skip decomposition entirely.
            return {"atomic_questions": []}

        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        if not latest_user_query:
            return {"atomic_questions": []}

        resolved_intent = state.get("resolved_intent") or {}
        sub_intents: list[str] = [
            str(s).strip()
            for s in (state.get("sub_intents") or [])
            if str(s).strip()
        ]

        prompt = append_datetime_context_fn(decomposer_prompt_template)
        decomposer_input = json.dumps(
            {
                "query": latest_user_query,
                "resolved_intent": resolved_intent,
                "sub_intents": sub_intents,
            },
            ensure_ascii=True,
        )

        atomic_questions: list[dict[str, Any]] = []
        try:
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 600}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    DecomposerResult, "decomposer_result"
                )
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=decomposer_input),
                ],
                **_invoke_kwargs,
            )
            _raw_content = str(getattr(message, "content", "") or "")
            # Try structured parse, fall back to regex extraction.
            try:
                _structured = DecomposerResult.model_validate_json(_raw_content)
                parsed = _structured.model_dump(exclude={"thinking"})
            except Exception:
                parsed = extract_first_json_object_fn(_raw_content)

            raw_questions = parsed.get("questions")
            if isinstance(raw_questions, list):
                seen_ids: set[str] = set()
                for idx, q in enumerate(raw_questions[:4], start=1):
                    if not isinstance(q, dict):
                        continue
                    text = str(q.get("text") or "").strip()
                    if not text:
                        continue
                    q_id = str(q.get("id") or f"q{idx}").strip()
                    if q_id in seen_ids:
                        q_id = f"q{idx}"
                    seen_ids.add(q_id)

                    depends_on_raw = q.get("depends_on")
                    depends_on: list[str] = []
                    if isinstance(depends_on_raw, list):
                        depends_on = [
                            str(d).strip()
                            for d in depends_on_raw
                            if str(d).strip()
                        ]
                    domain = str(q.get("domain") or "kunskap").strip().lower()
                    atomic_questions.append(
                        {
                            "id": q_id,
                            "text": text,
                            "depends_on": depends_on,
                            "domain": domain,
                        }
                    )
        except Exception as exc:
            logger.warning("multi_query_decomposer failed: %s", exc)

        # Single-question result is equivalent to no decomposition — clear it
        # so the planner doesn't treat it differently.
        if len(atomic_questions) <= 1:
            atomic_questions = []

        return {"atomic_questions": atomic_questions}

    return multi_query_decomposer_node
