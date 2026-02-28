"""Compare Supervisor v2: Research agent worker.

The research worker executes web research via Tavily as an isolated
subagent within the compare mini-graph infrastructure (P4 pattern).

It follows the same execution pattern as other subagent workers:
1. Query decomposition (LLM-driven)
2. Parallel Tavily searches
3. Citation ingestion
4. Structured handoff result

This worker is invoked by the compare subagent spawner alongside
external model workers, giving the convergence node factual web
data to merge with model responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .structured_schemas import (
    ResearchDecomposeResult,
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)

# Hard limits
_MAX_RESEARCH_QUERIES = 3
_MAX_TAVILY_RESULTS_PER_QUERY = 3
_RESEARCH_TIMEOUT_SECONDS = 45


async def run_research_executor(
    *,
    query: str,
    llm: Any,
    tavily_search_fn: Any | None = None,
) -> dict[str, Any]:
    """Execute the research agent pipeline: decompose → search → structure.

    Args:
        query: The user's original question.
        llm: LLM instance for query decomposition.
        tavily_search_fn: Async callable that takes (query, max_results) and
            returns list of search result dicts.  If None, returns empty results.

    Returns:
        Structured research result dict compatible with P4 handoff contract.
    """
    start_time = time.monotonic()

    logger.info(
        "research_executor: starting (tavily_search_fn=%s, query=%r)",
        "SET" if tavily_search_fn is not None else "NONE",
        query[:80],
    )

    # Step 1: Decompose query into sub-queries
    sub_queries = await _decompose_query(query, llm)
    logger.info("research_executor: decomposed into %d sub-queries: %s", len(sub_queries), sub_queries)

    # Step 2: Parallel Tavily searches
    web_sources: list[dict[str, Any]] = []
    if tavily_search_fn is not None:
        search_tasks = [
            _safe_tavily_search(tavily_search_fn, sq)
            for sq in sub_queries
        ]
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.warning("research_executor: Tavily search failed: %s", r)
                continue
            web_sources.extend(r)

    logger.info("research_executor: collected %d raw web_sources", len(web_sources))

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_sources: list[dict[str, Any]] = []
    for src in web_sources:
        url = src.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_sources.append(src)

    # Step 3: LLM synthesis — analyse sources and formulate an answer
    synthesized = await _synthesize_research(query, unique_sources, llm)

    latency_ms = int((time.monotonic() - start_time) * 1000)

    return {
        "status": "success" if unique_sources else "partial",
        "source": "OneSeek Research",
        "model_display_name": "OneSeek Research",
        "provider": "oneseek",
        "queries_used": sub_queries,
        "web_sources": unique_sources[:12],
        "response": synthesized,
        "latency_ms": latency_ms,
    }


async def _decompose_query(query: str, llm: Any) -> list[str]:
    """LLM-driven query decomposition into 1-3 search queries."""
    system_msg = SystemMessage(
        content=(
            "Du är en sökfråge-decomposerare. "
            "Givet en användarfråga, generera 1-3 korta, specifika sökfrågor "
            "som täcker frågans kärnaspekter. Inkludera Sverige-bias om relevant.\n\n"
            "INSTRUKTIONER FÖR OUTPUT:\n"
            "- All intern resonering ska skrivas i \"thinking\"-fältet.\n"
            "- Använd INTE <think>-taggar.\n\n"
            "Returnera strikt JSON:\n"
            '{"thinking": "din resonering om hur frågan bäst delas upp", '
            '"queries": ["sökfråga 1", "sökfråga 2"]}'
        )
    )
    human_msg = HumanMessage(content=f"Fråga: {query}")

    try:
        _invoke_kwargs: dict[str, Any] = {"max_tokens": 300}
        if structured_output_enabled():
            _invoke_kwargs["response_format"] = pydantic_to_response_format(
                ResearchDecomposeResult, "research_decompose"
            )
        raw = await llm.ainvoke([system_msg, human_msg], **_invoke_kwargs)
        raw_content = str(getattr(raw, "content", "") or "")

        # Try structured Pydantic parse first, fall back to regex
        try:
            _structured = ResearchDecomposeResult.model_validate_json(raw_content)
            return [str(q) for q in _structured.queries[:_MAX_RESEARCH_QUERIES]]
        except Exception:
            pass

        import re

        json_match = re.search(r"\{[^{}]*\}", raw_content)
        if json_match:
            parsed = json.loads(json_match.group())
            queries = parsed.get("queries", [query])
            return [str(q) for q in queries[:_MAX_RESEARCH_QUERIES]]
    except Exception:
        logger.debug("research_decompose: LLM decomposition failed, using original query")

    return [query]


async def _safe_tavily_search(
    tavily_search_fn: Any,
    query: str,
) -> list[dict[str, Any]]:
    """Safely call Tavily with timeout."""
    try:
        results = await asyncio.wait_for(
            tavily_search_fn(query, _MAX_TAVILY_RESULTS_PER_QUERY),
            timeout=_RESEARCH_TIMEOUT_SECONDS,
        )
        return results if isinstance(results, list) else []
    except TimeoutError:
        logger.warning("research_executor: Tavily timed out for query: %s", query[:80])
        return []


_RESEARCH_SYNTHESIS_TIMEOUT = 30


async def _synthesize_research(
    query: str,
    sources: list[dict[str, Any]],
    llm: Any,
) -> str:
    """Use LLM to synthesize search results into a coherent answer."""
    if not sources:
        return f"Webbsökning för '{query}' gav inga resultat."

    # Build source context for the LLM
    source_lines: list[str] = []
    for i, src in enumerate(sources[:12], 1):
        title = src.get("title", "Okänd källa")
        url = src.get("url", "")
        snippet = src.get("content", src.get("snippet", ""))[:600]
        source_lines.append(f"[{i}] {title}\n    {url}\n    {snippet}")

    source_context = "\n\n".join(source_lines)

    system_msg = SystemMessage(
        content=(
            "Du är OneSeek Research — en forskningsagent som analyserar "
            "webbkällor och formulerar välgrundade svar.\n\n"
            "INSTRUKTIONER:\n"
            "- Läs igenom alla källor noggrant.\n"
            "- Formulera ett sammanhängande, informativt svar på användarens fråga.\n"
            "- Citera källor med [1], [2] osv. inline i texten.\n"
            "- Om källorna ger motstridiga uppgifter, notera det.\n"
            "- Svara på samma språk som frågan.\n"
            "- Avsluta med en kort källförteckning.\n"
            "- Var saklig och koncis men grundlig."
        )
    )
    human_msg = HumanMessage(
        content=(
            f"Fråga: {query}\n\n"
            f"Webbkällor ({len(sources)} st):\n\n{source_context}"
        )
    )

    try:
        raw = await asyncio.wait_for(
            llm.ainvoke(
                [system_msg, human_msg],
                **{"max_tokens": 1500},
            ),
            timeout=_RESEARCH_SYNTHESIS_TIMEOUT,
        )
        content = str(getattr(raw, "content", "") or "").strip()
        if content:
            return content
    except TimeoutError:
        logger.warning("research_executor: synthesis LLM timed out, falling back to source list")
    except Exception:
        logger.warning("research_executor: synthesis LLM failed, falling back to source list", exc_info=True)

    # Fallback: formatted source list (previous behaviour)
    return _format_research_response(query, sources)


def _format_research_response(
    query: str,
    sources: list[dict[str, Any]],
) -> str:
    """Format research results into a readable source list (fallback)."""
    if not sources:
        return f"Webbsökning för '{query}' gav inga resultat."

    lines = [f"Webbsökning ({len(sources)} källor):\n"]
    for i, src in enumerate(sources, 1):
        title = src.get("title", "Okänd källa")
        url = src.get("url", "")
        snippet = src.get("content", src.get("snippet", ""))[:400]
        lines.append(f"{i}. **{title}**")
        if url:
            lines.append(f"   {url}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")

    return "\n".join(lines)


def build_compare_external_model_worker(
    spec: Any,
    call_external_model_fn: Any,
) -> Any:
    """Build an async worker function for a single external model in compare mode.

    This wraps call_external_model to match the worker.ainvoke() interface
    expected by the subagent spawner.

    Args:
        spec: ExternalModelSpec with tool_name, display, model, etc.
        call_external_model_fn: The async function that calls the model.

    Returns:
        An async callable that takes (state, config) and returns a result dict.
    """

    class _ExternalModelWorker:
        """Minimal worker interface for compare external models."""

        def __init__(self, model_spec: Any, call_fn: Any):
            self._spec = model_spec
            self._call_fn = call_fn

        async def ainvoke(
            self,
            state: dict[str, Any],
            config: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Call the external model and return result as messages."""
            messages = state.get("messages", [])
            query = ""
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    query = str(msg.content)
                    break

            if not query:
                return {"messages": [AIMessage(content="No query provided")]}

            try:
                result = await self._call_fn(
                    spec=self._spec,
                    query=query,
                )
                result_json = json.dumps(result, ensure_ascii=False)
                tool_call_id = f"compare_{self._spec.tool_name}"
                return {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[{
                                "name": self._spec.tool_name,
                                "args": {"query": query},
                                "id": tool_call_id,
                                "type": "tool_call",
                            }],
                        ),
                        ToolMessage(
                            name=self._spec.tool_name,
                            content=result_json,
                            tool_call_id=tool_call_id,
                        ),
                    ],
                    "_compare_result": result,
                }
            except Exception as e:
                error_result = {
                    "status": "error",
                    "error": str(e),
                    "model_display_name": self._spec.display,
                }
                return {
                    "messages": [AIMessage(content=json.dumps(error_result))],
                    "_compare_result": error_result,
                }

    return _ExternalModelWorker(spec, call_external_model_fn)


class ResearchWorker:
    """Minimal worker interface for the research agent in compare mode."""

    def __init__(self, llm: Any, tavily_search_fn: Any | None = None):
        self._llm = llm
        self._tavily_search_fn = tavily_search_fn

    async def ainvoke(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute research and return result as messages."""
        messages = state.get("messages", [])
        query = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                query = str(msg.content)
                break

        if not query:
            return {"messages": [AIMessage(content="No query provided")]}

        result = await run_research_executor(
            query=query,
            llm=self._llm,
            tavily_search_fn=self._tavily_search_fn,
        )

        result_json = json.dumps(result, ensure_ascii=False)
        tool_call_id = "compare_call_oneseek"
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "call_oneseek",
                        "args": {"query": query},
                        "id": tool_call_id,
                        "type": "tool_call",
                    }],
                ),
                ToolMessage(
                    name="call_oneseek",
                    content=result_json,
                    tool_call_id=tool_call_id,
                ),
            ],
            "_compare_result": result,
        }
