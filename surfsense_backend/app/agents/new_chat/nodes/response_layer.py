"""Response Layer node (Nivå 4) — presentation mode selection.

This node is the last processing step before END.  It runs after
``synthesizer`` / ``progressive_synthesizer`` and determines *how* the
final answer should be presented:

- ``kunskap``       – Factual knowledge answer, clean and direct.
- ``analys``        – Structured analytical answer with sections/headers.
- ``syntes``        – Multi-source synthesis that explicitly names sources.
- ``visualisering`` – Data-heavy answer that should be formatted as a
                       table or structured list.

The node writes ``response_mode`` to state so the frontend and any
downstream logging/analytics can inspect the chosen mode.  When a
per-mode prompt template is available, it uses an LLM call to reformat
the final response according to the mode-specific rules.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristic mode selection (fast-path, no LLM call needed)
# ---------------------------------------------------------------------------

_ANALYS_ROUTE_HINTS = {"jämförelse", "compare", "skapande"}
_SYNTES_KEYWORDS = re.compile(
    r"\b(jämför|analysera|sammanfatta|berätta\s+om|samla|kombinera|"
    r"compare|analyse|analyze|summarize|synthesize)\b",
    re.IGNORECASE,
)
_VISUALISERING_KEYWORDS = re.compile(
    r"\b(tabell|lista|diagram|graf|chart|table|list|show\s+data|visa\s+data|"
    r"visualisera|statistik\s+för|siffror\s+för)\b",
    re.IGNORECASE,
)
_ANALYS_KEYWORDS = re.compile(
    r"\b(analys|varför|anledning|orsak|förklara|explain|reason|why|"
    r"vad\s+beror|hur\s+kommer\s+det\s+sig)\b",
    re.IGNORECASE,
)

_VALID_MODES = {"kunskap", "analys", "syntes", "visualisering"}


def _select_response_mode(
    *,
    route_hint: str,
    query: str,
    response: str,
    sub_intents: list[str],
    execution_strategy: str,
) -> str:
    """Choose presentation mode using lightweight heuristics.

    Priority order:
    1. visualisering  – query or response contains table/list signals
    2. analys         – compare/jämförelse route, or analytical keywords
    3. syntes         – multi-domain (mixed route / multiple sub_intents)
    4. kunskap        – default factual answer
    """
    route = route_hint.lower()

    if _VISUALISERING_KEYWORDS.search(query):
        return "visualisering"

    if route in _ANALYS_ROUTE_HINTS or _ANALYS_KEYWORDS.search(query):
        return "analys"

    # Multiple domains resolved → synthesis presentation
    if route == "mixed" or len(sub_intents) > 1 or execution_strategy == "parallel":
        return "syntes"

    return "kunskap"


# ---------------------------------------------------------------------------
# Node builder
# ---------------------------------------------------------------------------

def build_response_layer_node(
    *,
    llm: Any = None,
    mode_prompts: dict[str, str] | None = None,
    latest_user_query_fn: Callable[[list[Any] | None], str],
):
    """Return a response_layer node.

    The node classifies the final answer into one of the four presentation
    modes and records the decision as ``response_mode`` on state.

    When *mode_prompts* contains a non-empty prompt for the selected mode
    **and** an *llm* is provided, the node uses an LLM call to reformat
    the response according to the mode-specific prompt.  Otherwise the
    response passes through unchanged.
    """
    _mode_prompts = mode_prompts or {}

    async def _llm_format(prompt_template: str, response: str, query: str) -> str:
        """Use LLM to reformat *response* according to *prompt_template*."""
        if llm is None:
            return response
        try:
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt_template),
                    HumanMessage(
                        content=(
                            f"Användarfråga: {query}\n\n"
                            f"Svar att formatera:\n{response}"
                        )
                    ),
                ],
                max_tokens=4096,
            )
            result = str(getattr(message, "content", "") or "").strip()
            return result if result else response
        except Exception:
            logger.debug(
                "response_layer: LLM formatting failed, returning original",
                exc_info=True,
            )
            return response

    async def response_layer_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        final_response = str(state.get("final_response") or "").strip()
        if not final_response:
            return {"response_mode": "kunskap"}

        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        route_hint = str(state.get("route_hint") or "").strip().lower()
        sub_intents: list[str] = [
            str(s).strip()
            for s in (state.get("sub_intents") or [])
            if str(s).strip()
        ]
        execution_strategy = str(state.get("execution_strategy") or "").strip().lower()

        mode = _select_response_mode(
            route_hint=route_hint,
            query=latest_user_query,
            response=final_response,
            sub_intents=sub_intents,
            execution_strategy=execution_strategy,
        )

        # ── LLM-driven formatting if a per-mode prompt is available ──
        mode_prompt = _mode_prompts.get(mode, "").strip()
        if mode_prompt and llm is not None:
            formatted = await _llm_format(mode_prompt, final_response, latest_user_query)
        else:
            formatted = final_response

        logger.info(
            "response_layer: mode=%s route=%s sub_intents=%d llm_format=%s",
            mode,
            route_hint,
            len(sub_intents),
            bool(mode_prompt and llm is not None),
        )

        updates: dict[str, Any] = {"response_mode": mode}
        if formatted != final_response:
            messages = list(state.get("messages") or [])
            last_message = messages[-1] if messages else None
            if isinstance(last_message, AIMessage):
                if str(getattr(last_message, "content", "") or "").strip() == formatted:
                    updates["final_response"] = formatted
                    return updates
            updates["messages"] = [AIMessage(content=formatted)]
            updates["final_response"] = formatted

        return updates

    return response_layer_node
