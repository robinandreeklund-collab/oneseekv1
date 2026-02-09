import json
from typing import Any

from langchain_core.tools import tool

from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.connector_service import ConnectorService


def _ensure_sweden_bias(query: str) -> str:
    cleaned = (query or "").strip()
    if not cleaned:
        return cleaned
    if "site:" in cleaned:
        return cleaned
    return f"{cleaned} site:.se"


def create_tavily_search_tool(
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
):
    """
    Live Tavily search using the configured connector for the search space.
    Persists results to Search History as documents for citations.
    """

    @tool
    async def search_tavily(query: str, top_k: int = 3) -> str:
        """
        Search the web using the Tavily connector configured for this search space.

        Args:
            query: The search query
            top_k: Maximum number of results (default 3)
        Returns:
            Formatted document context with chunk IDs for citations.
        """
        resolved_query = _ensure_sweden_bias(query)
        sources_info, documents = await connector_service.search_tavily(
            user_query=resolved_query,
            search_space_id=search_space_id,
            top_k=top_k,
            user_id=user_id,
        )
        formatted = format_documents_for_context(documents)
        answer = ""
        if isinstance(sources_info, dict) and sources_info.get("answer"):
            answer = str(sources_info.get("answer")).strip()
        payload: dict[str, Any] = {
            "query": resolved_query,
            "answer": answer,
            "results": formatted,
        }
        return json.dumps(payload, ensure_ascii=True)

    return search_tavily
