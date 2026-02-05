"""
Utilities for working with message content.

Message content in new_chat_messages can be stored in various formats:
- String: Simple text content
- List: Array of content parts [{"type": "text", "text": "..."}, {"type": "tool-call", ...}]
- Dict: Single content object

These utilities help extract and transform content for different use cases.
"""

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def format_compare_summary_for_memory(summary: object) -> str:
    """Format stored compare summary for LLM memory."""
    if not isinstance(summary, dict):
        return ""

    lines: list[str] = ["[Compare Summary]"]
    query = summary.get("query")
    if isinstance(query, str) and query:
        lines.append(f"Query: {query}")

    providers = summary.get("providers")
    if isinstance(providers, dict):
        for key, value in providers.items():
            if not isinstance(value, dict):
                continue
            status = value.get("status")
            label = str(key).strip().title()
            if status == "error":
                error_msg = value.get("error") or "Error"
                lines.append(f"{label}: Error: {error_msg}")
            else:
                answer = value.get("answer") or ""
                if answer:
                    lines.append(f"{label}: {answer}")

    final_answer = summary.get("final_answer")
    if isinstance(final_answer, str) and final_answer:
        lines.append(f"Final: {final_answer}")

    return "\n".join(lines)


def extract_text_content(content: str | dict | list) -> str:
    """Extract plain text content from various message formats."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        # Handle dict with 'text' key
        if "text" in content:
            return content["text"]
        return str(content)
    if isinstance(content, list):
        # Handle list of parts (e.g., [{"type": "text", "text": "..."}])
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif isinstance(part, dict) and part.get("type") == "compare-summary":
                summary = part.get("summary") if isinstance(part, dict) else None
                summary_text = format_compare_summary_for_memory(summary)
                if summary_text:
                    texts.append(summary_text)
            elif isinstance(part, str):
                texts.append(part)
        return "\n".join(texts) if texts else ""
    return ""


async def bootstrap_history_from_db(
    session: AsyncSession,
    thread_id: int,
) -> list[HumanMessage | AIMessage]:
    """
    Load message history from database and convert to LangChain format.

    Used for cloned chats where the LangGraph checkpointer has no state,
    but we have messages in the database that should be used as context.

    Args:
        session: Database session
        thread_id: The chat thread ID

    Returns:
        List of LangChain messages (HumanMessage/AIMessage)
    """
    from app.db import NewChatMessage

    result = await session.execute(
        select(NewChatMessage)
        .filter(NewChatMessage.thread_id == thread_id)
        .order_by(NewChatMessage.created_at)
    )
    db_messages = result.scalars().all()

    langchain_messages: list[HumanMessage | AIMessage] = []

    for msg in db_messages:
        text_content = extract_text_content(msg.content)
        if not text_content:
            continue
        if msg.role == "user":
            langchain_messages.append(HumanMessage(content=text_content))
        elif msg.role == "assistant":
            langchain_messages.append(AIMessage(content=text_content))

    return langchain_messages
