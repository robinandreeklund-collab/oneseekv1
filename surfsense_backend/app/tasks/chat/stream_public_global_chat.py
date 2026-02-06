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

    thinking_step_counter = 0
    last_active_step_id: str | None = None
    last_active_step_title = ""
    last_active_step_items: list[str] = []
    completed_step_ids: set[str] = set()
    tool_step_meta: dict[str, dict[str, object]] = {}

    def next_thinking_step_id() -> str:
        nonlocal thinking_step_counter
        thinking_step_counter += 1
        return f"thinking-{thinking_step_counter}"

    def complete_current_step() -> str | None:
        nonlocal last_active_step_id, last_active_step_title, last_active_step_items
        if last_active_step_id and last_active_step_id not in completed_step_ids:
            completed_step_ids.add(last_active_step_id)
            return streaming_service.format_thinking_step(
                step_id=last_active_step_id,
                title=last_active_step_title,
                status="completed",
                items=last_active_step_items if last_active_step_items else None,
            )
        return None

    def truncate(text: str, limit: int = 80) -> str:
        return text[:limit] + ("..." if len(text) > limit else "")

    def extract_user_query(messages: list | None) -> str:
        if not messages:
            return ""
        last_msg = messages[-1]
        content = getattr(last_msg, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [str(part) for part in content if isinstance(part, str)]
            return " ".join(parts)
        return str(content) if content else ""

    user_query = extract_user_query(input_state.get("messages"))
    if user_query.strip():
        last_active_step_id = next_thinking_step_id()
        last_active_step_title = "Understanding your request"
        last_active_step_items = [f"Processing: {truncate(user_query.strip())}"]
        yield streaming_service.format_thinking_step(
            step_id=last_active_step_id,
            title=last_active_step_title,
            status="in_progress",
            items=last_active_step_items,
        )

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
                        completion_event = complete_current_step()
                        if completion_event:
                            yield completion_event
                        current_text_id = streaming_service.generate_text_id()
                        yield streaming_service.format_text_start(current_text_id)
                    yield streaming_service.format_text_delta(current_text_id, content)
            elif event_type == "on_tool_start":
                tool_name = event.get("name", "unknown_tool")
                run_id = event.get("run_id", "")
                tool_input = event.get("data", {}).get("input", {})
                if current_text_id is not None:
                    yield streaming_service.format_text_end(current_text_id)
                    current_text_id = None
                completion_event = complete_current_step()
                if completion_event:
                    yield completion_event

                tool_step_id = next_thinking_step_id()
                last_active_step_id = tool_step_id

                title = f"Running {tool_name}"
                items: list[str] = []
                if tool_name == "search_web":
                    query = (
                        tool_input.get("query", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)
                    )
                    title = "Searching the web"
                    items = [f"Query: {truncate(str(query), 100)}"]
                elif tool_name == "link_preview":
                    url = (
                        tool_input.get("url", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)
                    )
                    title = "Fetching link preview"
                    items = [f"URL: {truncate(str(url), 100)}"]
                elif tool_name == "scrape_webpage":
                    url = (
                        tool_input.get("url", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)
                    )
                    title = "Scraping webpage"
                    items = [f"URL: {truncate(str(url), 100)}"]
                elif tool_name == "display_image":
                    src = (
                        tool_input.get("src", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)
                    )
                    title = "Analyzing the image"
                    items = [f"Image: {truncate(str(src), 100)}"]
                elif tool_name == "smhi_weather":
                    location = ""
                    if isinstance(tool_input, dict):
                        location = tool_input.get("location") or ""
                        lat = tool_input.get("lat")
                        lon = tool_input.get("lon")
                        if not location and lat is not None and lon is not None:
                            location = f"{lat}, {lon}"
                    else:
                        location = str(tool_input)
                    title = "Fetching weather (SMHI)"
                    items = [f"Location: {truncate(str(location), 100)}"]
                elif tool_name == "trafiklab_route":
                    origin = ""
                    destination = ""
                    if isinstance(tool_input, dict):
                        origin = tool_input.get("origin") or tool_input.get("origin_id") or ""
                        destination = (
                            tool_input.get("destination") or tool_input.get("destination_id") or ""
                        )
                    else:
                        origin = str(tool_input)
                    title = "Planning route (Trafiklab)"
                    route_label = f"{origin} -> {destination}".strip()
                    items = [f"Route: {truncate(str(route_label), 100)}"]
                elif tool_name == "libris_search":
                    query = ""
                    record_id = ""
                    if isinstance(tool_input, dict):
                        query = tool_input.get("query") or ""
                        record_id = tool_input.get("record_id") or ""
                    else:
                        query = str(tool_input)
                    title = "Searching Libris catalog"
                    label = record_id or query
                    items = [f"Query: {truncate(str(label), 100)}"]
                elif tool_name == "jobad_links_search":
                    query = ""
                    location = ""
                    if isinstance(tool_input, dict):
                        query = tool_input.get("query") or ""
                        location = tool_input.get("location") or ""
                    else:
                        query = str(tool_input)
                    title = "Searching job ads"
                    label = f"{query} {location}".strip()
                    items = [f"Search: {truncate(str(label), 100)}"]

                last_active_step_title = title
                last_active_step_items = items
                tool_step_meta[run_id] = {
                    "id": tool_step_id,
                    "title": title,
                    "items": items,
                }
                yield streaming_service.format_thinking_step(
                    step_id=tool_step_id,
                    title=title,
                    status="in_progress",
                    items=items,
                )
            elif event_type == "on_tool_end":
                run_id = event.get("run_id", "")
                meta = tool_step_meta.get(run_id)
                if meta:
                    step_id = str(meta.get("id"))
                    completed_step_ids.add(step_id)
                    yield streaming_service.format_thinking_step(
                        step_id=step_id,
                        title=str(meta.get("title", "Tool complete")),
                        status="completed",
                        items=meta.get("items") or [],
                    )
    except Exception as exc:
        yield streaming_service.format_error(f"Public chat failed: {exc!s}")
    finally:
        if current_text_id is not None:
            yield streaming_service.format_text_end(current_text_id)
        completion_event = complete_current_step()
        if completion_event:
            yield completion_event
        yield streaming_service.format_finish()
        yield streaming_service.format_done()
