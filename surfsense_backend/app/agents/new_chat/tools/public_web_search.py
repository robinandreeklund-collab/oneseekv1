import json
import logging

from langchain_core.tools import tool

from app.config import config

logger = logging.getLogger(__name__)


def _format_results(results: list[dict]) -> str:
    if not results:
        return "No results found."
    formatted = []
    for result in results:
        title = result.get("title") or "Untitled Result"
        url = result.get("url") or ""
        snippet = result.get("content") or result.get("snippet") or ""
        formatted.append(
            json.dumps(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                }
            )
        )
    return "\n".join(formatted)


def create_public_web_search_tool():
    """
    Factory for the public web search tool.

    Uses globally configured API keys (not user-specific).
    """

    @tool
    async def search_web(query: str, max_results: int = 5) -> str:
        """
        Search the public web using globally configured providers.

        Use this tool for real-time web search when the user needs up-to-date
        information. This tool is available to anonymous public chat sessions.

        Args:
            query: The web search query.
            max_results: Maximum number of results to return (capped).

        Returns:
            A JSON-lines string with results containing title, url, and snippet.
        """
        max_results = max(1, min(max_results, config.PUBLIC_WEB_SEARCH_MAX_RESULTS))

        if config.PUBLIC_TAVILY_API_KEY:
            try:
                from tavily import TavilyClient

                client = TavilyClient(api_key=config.PUBLIC_TAVILY_API_KEY)
                response = client.search(
                    query=query,
                    max_results=max_results,
                    search_depth="advanced",
                )
                results = response.get("results", []) if isinstance(response, dict) else []
                return _format_results(results)
            except Exception as exc:
                logger.error("Public Tavily search failed: %s", exc)
                return f"Public web search failed: {exc!s}"

        return (
            "Public web search is not configured. "
            "Set PUBLIC_TAVILY_API_KEY to enable this tool."
        )

    return search_web
