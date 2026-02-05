from collections.abc import AsyncGenerator

from app.services.new_streaming_service import VercelStreamingService


async def stream_public_global_chat(
    agent,
    input_state: dict,
    stream_config: dict | None = None,
) -> AsyncGenerator[str, None]:
    streaming_service = VercelStreamingService()
    current_text_id: str | None = None
    stream_config = stream_config or {}

    yield streaming_service.format_message_start()

    try:
        async for event in agent.astream_events(
            input_state, config=stream_config, version="v2"
        ):
            event_type = event.get("event", "")
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                content = getattr(chunk, "content", None) if chunk else None
                if content and isinstance(content, str):
                    if current_text_id is None:
                        current_text_id = streaming_service.generate_text_id()
                        yield streaming_service.format_text_start(current_text_id)
                    yield streaming_service.format_text_delta(current_text_id, content)
            elif event_type == "on_tool_start":
                if current_text_id is not None:
                    yield streaming_service.format_text_end(current_text_id)
                    current_text_id = None
    except Exception as exc:
        yield streaming_service.format_error(f"Public chat failed: {exc!s}")
    finally:
        if current_text_id is not None:
            yield streaming_service.format_text_end(current_text_id)
        yield streaming_service.format_finish()
        yield streaming_service.format_done()
