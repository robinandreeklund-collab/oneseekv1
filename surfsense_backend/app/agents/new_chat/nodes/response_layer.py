"""Response Layer nodes (Nivå 4) — presentation mode routing & formatting.

Two graph nodes work together:

``response_layer_router``
    LLM-driven node that analyses the synthesised answer and decides which
    of the four presentation modes fits best.  Its reasoning streams into
    the FadeLayer think-box because it is registered as an *internal*
    pipeline chain in ``stream_new_chat.py``.

``response_layer``
    Reads ``response_mode`` from state (set by the router) and, when a
    per-mode prompt is available, uses a second LLM call to reformat the
    answer accordingly.  Falls back to keyword heuristics if the router
    was skipped or failed.

Modes:

- ``kunskap``       – Factual knowledge answer, clean and direct.
- ``analys``        – Structured analytical answer with sections/headers.
- ``syntes``        – Multi-source synthesis that explicitly names sources.
- ``visualisering`` – Data-heavy answer formatted as a table or list.
"""

from __future__ import annotations

import json
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

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.DOTALL)


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


def _parse_router_response(raw: str) -> dict[str, str] | None:
    """Extract JSON from the router LLM response."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    match = _JSON_BLOCK_RE.search(cleaned)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        chosen = str(data.get("chosen_layer", "")).strip().lower()
        if chosen in _VALID_MODES:
            return {
                "chosen_layer": chosen,
                "reason": str(data.get("reason", "")),
                "data_characteristics": str(
                    data.get("data_characteristics", "")
                ),
            }
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return None


# ---------------------------------------------------------------------------
# Router node builder (separate LangGraph node → internal pipeline chain)
# ---------------------------------------------------------------------------

def build_response_layer_router_node(
    *,
    llm: Any = None,
    router_prompt: str = "",
    latest_user_query_fn: Callable[[list[Any] | None], str],
):
    """Return a ``response_layer_router`` graph node.

    This node analyses the synthesised answer and picks the best
    presentation mode.  Because it is a *separate* LangGraph node, its
    LLM call is emitted under the chain name ``response_layer_router``
    which is registered as INTERNAL in the streaming pipeline — the
    model's reasoning therefore appears in the FadeLayer think-box.

    Writes ``response_mode`` to state so the downstream
    ``response_layer`` node can format accordingly.
    """
    _prompt = (router_prompt or "").strip()

    async def response_layer_router_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        final_response = str(state.get("final_response") or "").strip()
        if not final_response or not _prompt or llm is None:
            return {}

        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        route_hint = str(state.get("route_hint") or "").strip().lower()
        sub_intents: list[str] = [
            str(s).strip()
            for s in (state.get("sub_intents") or [])
            if str(s).strip()
        ]
        execution_strategy = str(
            state.get("execution_strategy") or ""
        ).strip().lower()

        # Truncate to keep the router call fast
        truncated = final_response[:3000]
        if len(final_response) > 3000:
            truncated += "\n\n[...trunkerat...]"

        human_content = (
            f"Användarfråga: {latest_user_query}\n"
            f"Route: {route_hint}\n"
            f"Sub-intents: {', '.join(sub_intents) if sub_intents else 'inga'}\n"
            f"Exekveringsstrategi: {execution_strategy or 'standard'}\n\n"
            f"Data att analysera:\n{truncated}"
        )

        try:
            # Use astream so astream_events(v2) emits per-token events
            # that the streaming pipeline can route to reasoning-delta.
            # Pass config explicitly to ensure callbacks propagate to
            # the parent astream_events — without this the LLM events
            # are invisible to the streaming pipeline.
            chunks: list[str] = []
            stream_kwargs: dict[str, Any] = {"max_tokens": 512}
            if config is not None:
                stream_kwargs["config"] = config
            async for chunk in llm.astream(
                [
                    SystemMessage(content=_prompt),
                    HumanMessage(content=human_content),
                ],
                **stream_kwargs,
            ):
                content = getattr(chunk, "content", "")
                if content:
                    chunks.append(content)
            raw = "".join(chunks).strip()
            decision = _parse_router_response(raw)
            if decision:
                mode = decision["chosen_layer"]
                logger.info(
                    "response_layer_router: chosen=%s reason=%s",
                    mode,
                    decision.get("reason", ""),
                )
                return {"response_mode": mode}
        except Exception:
            logger.debug(
                "response_layer_router: LLM call failed",
                exc_info=True,
            )

        return {}

    return response_layer_router_node


# ---------------------------------------------------------------------------
# Formatting node builder
# ---------------------------------------------------------------------------

def build_response_layer_node(
    *,
    llm: Any = None,
    mode_prompts: dict[str, str] | None = None,
    latest_user_query_fn: Callable[[list[Any] | None], str],
):
    """Return a ``response_layer`` node.

    Reads ``response_mode`` from state (set by the upstream router node).
    If the mode is not yet set, falls back to keyword heuristics.

    When *mode_prompts* contains a non-empty prompt for the selected mode
    **and** an *llm* is provided, the node uses an LLM call to reformat
    the response according to the mode-specific prompt.  Otherwise the
    response passes through unchanged.
    """
    _mode_prompts = mode_prompts or {}

    async def _llm_format(
        prompt_template: str,
        response: str,
        query: str,
        run_config: RunnableConfig | None = None,
    ) -> str:
        """Use LLM to reformat *response* according to *prompt_template*.

        Uses ``astream`` so that LangGraph's ``astream_events(v2)`` emits
        per-token ``on_chat_model_stream`` events.  This lets the streaming
        pipeline route the formatted text to ``text-delta`` in real-time.

        Passing *run_config* is critical — without it the LLM's callback
        events are invisible to the parent ``astream_events`` and the
        streaming pipeline cannot route the formatted text to the frontend.
        """
        if llm is None:
            return response
        try:
            chunks: list[str] = []
            stream_kwargs: dict[str, Any] = {"max_tokens": 4096}
            if run_config is not None:
                stream_kwargs["config"] = run_config
            async for chunk in llm.astream(
                [
                    SystemMessage(content=prompt_template),
                    HumanMessage(
                        content=(
                            f"Användarfråga: {query}\n\n"
                            f"Svar att formatera:\n{response}"
                        )
                    ),
                ],
                **stream_kwargs,
            ):
                content = getattr(chunk, "content", "")
                if content:
                    chunks.append(content)
            result = "".join(chunks).strip()
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
        execution_strategy = str(
            state.get("execution_strategy") or ""
        ).strip().lower()

        # Read mode from state (set by router) or fall back to heuristic
        mode = str(state.get("response_mode") or "").strip().lower()
        if mode not in _VALID_MODES:
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
            formatted = await _llm_format(
                mode_prompt, final_response, latest_user_query,
                run_config=config,
            )
        else:
            formatted = final_response

        logger.info(
            "response_layer: mode=%s route=%s sub_intents=%d llm_format=%s",
            mode,
            route_hint,
            len(sub_intents),
            bool(mode_prompt and llm is not None),
        )

        # Always include the final text in the output so the streaming
        # pipeline's fallback mechanism (chain_end → fallback_assistant_text)
        # picks up the response_layer's text rather than the synthesizer's
        # raw output.  This is the safety net that prevents think-leakage
        # even when the LLM's streaming events don't propagate.
        updates: dict[str, Any] = {
            "response_mode": mode,
            "final_response": formatted,
        }
        messages = list(state.get("messages") or [])
        last_message = messages[-1] if messages else None
        if isinstance(last_message, AIMessage):
            existing = str(getattr(last_message, "content", "") or "").strip()
            if existing == formatted:
                return updates
        updates["messages"] = [AIMessage(content=formatted)]
        return updates

    return response_layer_node
