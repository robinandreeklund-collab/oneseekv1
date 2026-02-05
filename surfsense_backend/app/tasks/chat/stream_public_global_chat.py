from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import BaseMessage

from app.services.new_streaming_service import VercelStreamingService


def _extract_chunk_text(chunk: Any) -> str:
    if hasattr(chunk, "content") and isinstance(chunk.content, str):
        return chunk.content
    message = getattr(chunk, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
    return ""


async def stream_public_global_chat(
    llm: Any,
    messages: list[BaseMessage],
    llm_kwargs: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    streaming_service = VercelStreamingService()
    text_id = streaming_service.generate_text_id()
    llm_kwargs = llm_kwargs or {}

    yield streaming_service.format_message_start()
    yield streaming_service.format_text_start(text_id)

    try:
        async for chunk in llm.astream(messages, **llm_kwargs):
            delta = _extract_chunk_text(chunk)
            if delta:
                yield streaming_service.format_text_delta(text_id, delta)
        yield streaming_service.format_text_end(text_id)
        yield streaming_service.format_finish()
    except Exception as exc:
        yield streaming_service.format_error(f"Public chat failed: {exc!s}")
    finally:
        yield streaming_service.format_done()
