"""
Streaming task for the new SurfSense deep agent chat.

This module streams responses from the deep agent using the Vercel AI SDK
Data Stream Protocol (SSE format).

Supports loading LLM configurations from:
- YAML files (negative IDs for global configs)
- NewLLMConfig database table (positive IDs for user-created configs with prompt settings)
"""

import ast
import json
import re
import uuid
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.agents.new_chat.bigtool_prompts import (
    DEFAULT_WORKER_ACTION_PROMPT,
    DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    build_worker_prompt,
)
from app.agents.new_chat.bigtool_store import get_tool_rerank_trace
from app.agents.new_chat.bolag_prompts import (
    DEFAULT_BOLAG_SYSTEM_PROMPT,
    build_bolag_prompt,
)
from app.agents.new_chat.checkpointer import (
    build_checkpoint_namespace,
    get_checkpointer,
    resolve_checkpoint_namespace_for_thread,
)
from app.agents.new_chat.compare_prompts import (
    COMPARE_SUPERVISOR_INSTRUCTIONS,
    DEFAULT_COMPARE_ANALYSIS_PROMPT,
    build_compare_synthesis_prompt,
)
from app.agents.new_chat.complete_graph import build_complete_graph
from app.agents.new_chat.dispatcher import (
    DEFAULT_ROUTE_SYSTEM_PROMPT,
    dispatch_route_with_trace,
)
from app.agents.new_chat.llm_config import (
    AgentConfig,
    create_chat_litellm_from_agent_config,
    create_chat_litellm_from_config,
    load_agent_config,
    load_llm_config_from_yaml,
)
from app.agents.new_chat.marketplace_prompts import (
    DEFAULT_MARKETPLACE_SYSTEM_PROMPT,
    build_marketplace_prompt,
)
from app.agents.new_chat.prompt_registry import resolve_prompt
from app.agents.new_chat.riksdagen_prompts import DEFAULT_RIKSDAGEN_SYSTEM_PROMPT
from app.agents.new_chat.routing import Route
from app.agents.new_chat.statistics_prompts import (
    DEFAULT_STATISTICS_SYSTEM_PROMPT,
    build_statistics_system_prompt,
)
from app.agents.new_chat.subagent_utils import (
    SMALLTALK_INSTRUCTIONS,
)
from app.agents.new_chat.supervisor_prompts import (
    DEFAULT_SUPERVISOR_PROMPT,
    build_supervisor_prompt,
)
from app.agents.new_chat.system_prompt import (
    SURFSENSE_CITATION_INSTRUCTIONS,
    SURFSENSE_CORE_GLOBAL_PROMPT,
    SURFSENSE_SYSTEM_INSTRUCTIONS,
    append_datetime_context,
    inject_core_prompt,
)
from app.agents.new_chat.tools.display_image import extract_domain, generate_image_id
from app.agents.new_chat.tools.external_models import (
    DEFAULT_EXTERNAL_SYSTEM_PROMPT,
    EXTERNAL_MODEL_SPECS,
)
from app.agents.new_chat.tools.user_memory import create_save_memory_tool
from app.agents.new_chat.trafik_prompts import (
    DEFAULT_TRAFFIC_SYSTEM_PROMPT,
    build_trafik_prompt,
)
from app.db import (
    ChatTraceSession,
    Document,
    NewChatMessage,
    NewChatMessageRole,
    SurfsenseDocsDocument,
    async_session_maker,
)
from app.schemas.new_chat import ChatAttachment
from app.services.agent_prompt_service import get_global_prompt_overrides
from app.services.chat_session_state_service import (
    clear_ai_responding,
    set_ai_responding,
)
from app.services.connector_service import ConnectorService
from app.services.intent_definition_service import (
    get_default_intent_definitions,
    get_effective_intent_definitions,
)
from app.services.new_streaming_service import VercelStreamingService
from app.services.trace_service import TraceRecorder
from app.tasks.chat.context_formatters import (
    format_attachments_as_context,
    format_mentioned_documents_as_context,
    format_mentioned_surfsense_docs_as_context,
)
from app.tasks.chat.stream_compare_chat import (
    extract_compare_query,
    is_compare_request,
)
from app.utils.content_utils import bootstrap_history_from_db, extract_text_content
from app.utils.context_metrics import (
    estimate_tokens_from_text,
    serialize_context_payload,
)

AUTO_MEMORY_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"\bmy name is ([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+)*)", re.IGNORECASE),
        "fact",
        "User's name is {value}",
    ),
    (
        re.compile(r"\bcall me ([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+)*)", re.IGNORECASE),
        "fact",
        "User prefers to be called {value}",
    ),
    (
        re.compile(r"\bI am (\d{1,3}) years old\b", re.IGNORECASE),
        "fact",
        "User is {value} years old",
    ),
    (
        re.compile(r"\bI'm (\d{1,3}) years old\b", re.IGNORECASE),
        "fact",
        "User is {value} years old",
    ),
    (
        re.compile(r"\bI live in ([A-Za-zÅÄÖåäö\s\-]{2,60})\b", re.IGNORECASE),
        "fact",
        "User lives in {value}",
    ),
    (
        re.compile(r"\bI work as ([A-Za-zÅÄÖåäö\s\-]{2,80})\b", re.IGNORECASE),
        "fact",
        "User works as {value}",
    ),
    (
        re.compile(r"\bI(?:'m| am) a[n]? ([A-Za-zÅÄÖåäö\s\-]{2,80})\b", re.IGNORECASE),
        "fact",
        "User is a {value}",
    ),
    (
        re.compile(r"\bI (?:prefer|like|love) ([^.!?\n]{2,80})", re.IGNORECASE),
        "preference",
        "User prefers {value}",
    ),
    (
        re.compile(
            r"\bjag heter ([A-ZÅÄÖ][\wÅÄÖåäö\-]+(?:\s+[A-ZÅÄÖ][\wÅÄÖåäö\-]+)*)",
            re.IGNORECASE,
        ),
        "fact",
        "User's name is {value}",
    ),
    (
        re.compile(
            r"\bkalla mig ([A-ZÅÄÖ][\wÅÄÖåäö\-]+(?:\s+[A-ZÅÄÖ][\wÅÄÖåäö\-]+)*)",
            re.IGNORECASE,
        ),
        "fact",
        "User prefers to be called {value}",
    ),
    (
        re.compile(r"\bjag är (\d{1,3}) år\b", re.IGNORECASE),
        "fact",
        "User is {value} years old",
    ),
    (
        re.compile(r"\bjag bor i ([A-Za-zÅÄÖåäö\s\-]{2,60})\b", re.IGNORECASE),
        "fact",
        "User lives in {value}",
    ),
    (
        re.compile(
            r"\bjag (?:jobbar|arbetar) som ([A-Za-zÅÄÖåäö\s\-]{2,80})\b", re.IGNORECASE
        ),
        "fact",
        "User works as {value}",
    ),
    (
        re.compile(
            r"\bjag (?:gillar|föredrar|tycker om) ([^.!?\n]{2,80})", re.IGNORECASE
        ),
        "preference",
        "User prefers {value}",
    ),
]


def _normalize_memory_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    return cleaned.strip(" .,:;")


def extract_auto_memories(text: str) -> list[tuple[str, str]]:
    if not text:
        return []
    if len(text) > 400:
        return []

    memories: list[tuple[str, str]] = []
    for pattern, category, template in AUTO_MEMORY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        value = _normalize_memory_value(match.group(1))
        if not value:
            continue
        memories.append((template.format(value=value), category))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for content, category in memories:
        if content in seen:
            continue
        seen.add(content)
        unique.append((content, category))

    return unique[:3]


def _normalize_router_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


async def _load_conversation_history_for_routing(
    session: AsyncSession,
    chat_id: int,
    current_user_query: str,
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    result = await session.execute(
        select(NewChatMessage)
        .filter(NewChatMessage.thread_id == chat_id)
        .order_by(NewChatMessage.created_at.desc())
        .limit(limit + 3)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    history: list[dict[str, str]] = []
    for row in rows:
        role = str(getattr(row.role, "value", row.role) or "").strip().lower()
        if role not in {
            NewChatMessageRole.USER.value,
            NewChatMessageRole.ASSISTANT.value,
        }:
            continue
        text = _normalize_router_text(extract_text_content(row.content))
        if not text:
            continue
        if role == NewChatMessageRole.ASSISTANT.value:
            text = _normalize_router_text(_clean_assistant_output_text(text))
        if not text:
            continue
        history.append({"role": role, "content": text[:420]})
    current_norm = _normalize_router_text(current_user_query).lower()
    if history and history[-1].get("role") == NewChatMessageRole.USER.value:
        trailing = _normalize_router_text(history[-1].get("content") or "").lower()
        if trailing == current_norm:
            history.pop()
    return history[-limit:]


_FOLLOWUP_CONFIRMATION_RE = re.compile(
    r"^(ja|nej|ok|okej|kör|go|yes|no|stopp?)\.?$",
    re.IGNORECASE,
)
_FOLLOWUP_MARKER_RE = re.compile(
    r"\b(och|också|även|då|samma|där|dit|här|dessa|båda|bada|de två)\b",
    re.IGNORECASE,
)
_FOLLOWUP_COMPARE_RE = re.compile(
    r"\b(jämför|jamfor|jämförelse|jamforelse|skillnad(?:en)?(?:\s+mellan)?)\b",
    re.IGNORECASE,
)


def _extract_previous_user_query_from_history(history: list[dict[str, str]]) -> str:
    for item in reversed(history or []):
        if str(item.get("role") or "").strip().lower() != NewChatMessageRole.USER.value:
            continue
        content = _normalize_router_text(item.get("content") or "")
        if content:
            return content
    return ""


def _looks_contextual_followup(query: str) -> bool:
    text = _normalize_router_text(query)
    if not text:
        return False
    lowered = text.lower().strip(" ?!.")
    if not lowered:
        return False
    if _FOLLOWUP_CONFIRMATION_RE.match(lowered):
        return False
    words = lowered.split()
    if len(words) > 9 or len(lowered) > 90:
        return False
    if lowered.startswith(("och ", "i ", "på ", "för ", "om ")):
        return True
    if lowered.endswith(" då") or lowered.endswith(" också"):
        return True
    if _FOLLOWUP_COMPARE_RE.search(lowered):
        return True
    return bool(_FOLLOWUP_MARKER_RE.search(lowered))


def _extract_previous_assistant_answers_from_history(
    history: list[dict[str, str]],
    *,
    limit: int = 2,
) -> list[str]:
    results: list[str] = []
    for item in reversed(history or []):
        role = str(item.get("role") or "").strip().lower()
        if role != NewChatMessageRole.ASSISTANT.value:
            continue
        content = _normalize_router_text(item.get("content") or "")
        if not content:
            continue
        results.append(content)
        if len(results) >= max(1, int(limit)):
            break
    results.reverse()
    return results


def _build_followup_context_block(
    raw_query: str,
    routing_history: list[dict[str, str]],
) -> str:
    current = _normalize_router_text(raw_query)
    if not _looks_contextual_followup(current):
        return ""
    previous = _extract_previous_user_query_from_history(routing_history)
    if not previous:
        return ""
    if previous.lower() == current.lower():
        return ""

    # Check if previous query was a compare request
    previous_was_compare = previous.strip().lower().startswith("/compare")

    context = (
        "<followup_context>\n"
        "Detta är en uppföljningsfråga. Tolka den med samma ämne, metod och verktygsnivå "
        "som föregående användarfråga om inget annat uttryckligen anges.\n"
        f"Föregående användarfråga: {previous}\n"
    )

    # Add special context for compare followups
    if previous_was_compare:
        context += (
            "\nFöregående fråga var en jämförelse (/compare) mellan flera AI-modeller. "
            "Modellernas svar finns tillgängliga som TOOL_OUTPUT-dokument i kunskapsbasen. "
            "Du kan söka efter dem med search_knowledge_base för att ge sammanhangsberoende svar "
            "baserade på jämförelsen.\n"
        )

    if _FOLLOWUP_COMPARE_RE.search(current.lower()):
        previous_answers = _extract_previous_assistant_answers_from_history(
            routing_history, limit=2
        )
        if previous_answers:
            for index, answer in enumerate(previous_answers, start=1):
                context += f"Föregående assistentsvar {index}: {answer[:420]}\n"
            context += (
                "Om användaren säger 'dessa två' eller liknande: utgå i första hand från de två "
                "senaste assistentsvaren ovan.\n"
            )
    context += "</followup_context>"
    return context


def extract_todos_from_deepagents(command_output) -> dict:
    """
    Extract todos from deepagents' TodoListMiddleware Command output.

    deepagents returns a Command object with:
    - Command.update['todos'] = [{'content': '...', 'status': '...'}]

    Returns the todos directly (no transformation needed - UI matches deepagents format).
    """
    todos_data = []
    if hasattr(command_output, "update"):
        # It's a Command object from deepagents
        update = command_output.update
        todos_data = update.get("todos", [])
    elif isinstance(command_output, dict):
        # Already a dict - check if it has todos directly or in update
        if "todos" in command_output:
            todos_data = command_output.get("todos", [])
        elif "update" in command_output and isinstance(command_output["update"], dict):
            todos_data = command_output["update"].get("todos", [])

    return {"todos": todos_data}


def format_todo_items(todos: list[dict] | None) -> list[str]:
    if not todos:
        return []
    items: list[str] = []
    for todo in todos:
        if not isinstance(todo, dict):
            continue
        content = str(todo.get("content") or "").strip()
        status = str(todo.get("status") or "").lower()
        if not content:
            continue
        marker = "[ ]"
        if status == "completed":
            marker = "[x]"
        elif status == "in_progress":
            marker = "[>]"
        elif status == "cancelled":
            marker = "[!]"
        items.append(f"{marker} {content}")
    return items


def _coerce_jsonable(value: object) -> object:
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


def _summarize_text(value: object, limit: int = 140) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _format_tool_input_items(
    tool_input: object, *, max_items: int = 6, max_value_len: int = 100
) -> list[str]:
    """Format a tool's input parameters as compact display items.

    Returns a list like:
        ["location: Stockholm", "days: 5", "units: metric"]

    Skips internal/large fields and limits value lengths.
    """
    if not isinstance(tool_input, dict) or not tool_input:
        if tool_input:
            text = str(tool_input).strip()
            if text:
                return [_summarize_text(text, max_value_len)]
        return []

    skip_keys = frozenset({
        "source_content", "content", "text", "body", "markdown",
        "html", "raw", "data", "payload", "context",
    })
    items: list[str] = []
    for key, value in tool_input.items():
        if len(items) >= max_items:
            remaining = len(tool_input) - len(items)
            if remaining > 0:
                items.append(f"(+{remaining} fler parametrar)")
            break
        if key.lower() in skip_keys and isinstance(value, str) and len(value) > 200:
                items.append(f"{key}: ({len(value):,} tecken)")
                continue
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            summary = json.dumps(value, ensure_ascii=False, default=str)
            items.append(f"{key}: {_summarize_text(summary, max_value_len)}")
        else:
            items.append(f"{key}: {_summarize_text(value, max_value_len)}")
    return items


def _build_image_payload(
    *,
    src: str,
    alt: str,
    title: str | None = None,
    description: str | None = None,
    href: str | None = None,
) -> dict[str, Any]:
    image_id = generate_image_id(src)
    if not src.startswith(("http://", "https://")):
        src = f"https://{src}"
    domain = extract_domain(src)
    ratio = "16:9"
    return {
        "id": image_id,
        "assetId": src,
        "src": src,
        "alt": alt,
        "title": title,
        "description": description,
        "href": href,
        "domain": domain,
        "ratio": ratio,
    }


def _collect_trafikverket_photos(payload: Any) -> list[dict[str, str]]:
    photos: list[dict[str, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if any(
                key in node
                for key in (
                    "PhotoUrlFullsize",
                    "PhotoUrl",
                    "PhotoUrlThumbnail",
                    "PhotoUrlSketch",
                )
            ):
                fullsize = (
                    node.get("PhotoUrlFullsize")
                    or node.get("PhotoUrl")
                    or node.get("PhotoUrlThumbnail")
                    or node.get("PhotoUrlSketch")
                )
                thumbnail = (
                    node.get("PhotoUrlThumbnail")
                    or node.get("PhotoUrl")
                    or node.get("PhotoUrlSketch")
                    or node.get("PhotoUrlFullsize")
                )
                if isinstance(thumbnail, str) and thumbnail:
                    title = str(
                        node.get("CameraId")
                        or node.get("Name")
                        or "Trafikverket kamera"
                    )
                    description = str(
                        node.get("Description") or node.get("LocationDescriptor") or ""
                    ).strip()
                    photos.append(
                        {
                            "src": thumbnail,
                            "fullsize": fullsize or thumbnail,
                            "title": title,
                            "description": description,
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return photos


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if isinstance(item, dict):
                text_value = item.get("text") or item.get("content")
                if isinstance(text_value, str):
                    chunks.append(text_value)
                continue
            text_attr = getattr(item, "text", None) or getattr(item, "content", None)
            if isinstance(text_attr, str):
                chunks.append(text_attr)
        return "".join(chunks)
    return str(content)


def _extract_assistant_text_from_message(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "").lower()
        if role in {"human", "user", "system", "tool"}:
            return ""
        tool_calls = message.get("tool_calls") or message.get("toolCalls")
        if tool_calls:
            return ""
        return _content_to_text(message.get("content")).strip()
    class_name = message.__class__.__name__.lower()
    if any(token in class_name for token in ("human", "system", "tool")):
        return ""
    tool_calls = getattr(message, "tool_calls", None) or getattr(
        message, "toolCalls", None
    )
    if tool_calls:
        return ""
    return _content_to_text(getattr(message, "content", "")).strip()


def _extract_assistant_text_from_event_output(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, dict):
        messages = output.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                text = _extract_assistant_text_from_message(message)
                if text:
                    return text
        generations = output.get("generations")
        if isinstance(generations, list):
            for generation in reversed(generations):
                text = _extract_assistant_text_from_event_output(generation)
                if text:
                    return text
        message = output.get("message")
        if message is not None:
            text = _extract_assistant_text_from_event_output(message)
            if text:
                return text
        if "content" in output:
            return _extract_assistant_text_from_message(output)
        return ""
    if isinstance(output, list):
        for item in reversed(output):
            text = _extract_assistant_text_from_event_output(item)
            if text:
                return text
        return ""
    if hasattr(output, "generations"):
        return _extract_assistant_text_from_event_output(output.generations)
    if hasattr(output, "message"):
        return _extract_assistant_text_from_event_output(output.message)
    if hasattr(output, "content"):
        return _extract_assistant_text_from_message(output)
    return ""


def _extract_and_stream_tool_calls(
    output: Any, streaming_service: Any, streamed_ids: set[str]
) -> list[str]:
    """
    Extract AIMessage with tool_calls and corresponding ToolMessages from chain output.
    Returns list of SSE events to stream to frontend.

    This is critical for compare mode where compare_fan_out creates:
    - AIMessage with tool_calls array (one per external model)
    - ToolMessage responses (one per model with results)

    Without this, frontend doesn't receive tool call events and can't render model cards.

    Args:
        output: Chain output dictionary containing messages
        streaming_service: Service for formatting SSE events
        streamed_ids: Set of tool_call_ids already streamed (prevents duplicates)
    """
    events = []

    if not isinstance(output, dict):
        return events

    messages = output.get("messages")
    if not isinstance(messages, list) or len(messages) == 0:
        return events

    # Find AIMessage with tool_calls and collect corresponding ToolMessages
    ai_message_with_tools = None
    tool_messages_by_id = {}

    for msg in messages:
        # Check for AIMessage with tool_calls
        if isinstance(msg, AIMessage) or (
            isinstance(msg, dict) and msg.get("type") == "ai"
        ):
            tool_calls = (
                getattr(msg, "tool_calls", None)
                if hasattr(msg, "tool_calls")
                else msg.get("tool_calls")
            )
            if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                ai_message_with_tools = (msg, tool_calls)

        # Collect ToolMessages
        if isinstance(msg, ToolMessage) or (
            isinstance(msg, dict) and msg.get("type") == "tool"
        ):
            tool_call_id = (
                getattr(msg, "tool_call_id", None)
                if hasattr(msg, "tool_call_id")
                else msg.get("tool_call_id")
            )
            if tool_call_id:
                tool_messages_by_id[tool_call_id] = msg

    # If we found tool calls and messages, stream them (but only if not already streamed)
    if ai_message_with_tools:
        _msg, tool_calls = ai_message_with_tools

        for tool_call in tool_calls:
            tool_call_id = (
                tool_call.get("id")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "id", None)
            )
            tool_name = (
                tool_call.get("name")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "name", None)
            )
            tool_args = (
                tool_call.get("args")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "args", {})
            )

            if not tool_call_id or not tool_name:
                continue

            # Skip if already streamed
            if tool_call_id in streamed_ids:
                continue

            # Mark as streamed
            streamed_ids.add(tool_call_id)

            # Stream tool input
            events.append(
                streaming_service.format_tool_input_start(tool_call_id, tool_name)
            )
            events.append(
                streaming_service.format_tool_input_available(
                    tool_call_id, tool_name, tool_args
                )
            )

            # Stream tool output if available
            tool_msg = tool_messages_by_id.get(tool_call_id)
            if tool_msg:
                content = (
                    getattr(tool_msg, "content", None)
                    if hasattr(tool_msg, "content")
                    else tool_msg.get("content")
                )
                if content:
                    # Try to parse as JSON
                    try:
                        output_data = (
                            json.loads(content) if isinstance(content, str) else content
                        )
                        events.append(
                            streaming_service.format_tool_output_available(
                                tool_call_id, output_data
                            )
                        )
                    except (json.JSONDecodeError, TypeError):
                        # If not JSON, send as-is
                        events.append(
                            streaming_service.format_tool_output_available(
                                tool_call_id, content
                            )
                        )

    return events


_CRITIC_JSON_SNIPPET_RE = re.compile(
    r"\{\s*[\"']status[\"']\s*:\s*[\"'](?:ok|needs_more|replan)[\"'][\s\S]*?[\"']reason[\"']\s*:\s*[\"'][\s\S]*?[\"']\s*\}",
    re.IGNORECASE,
)
_CITATION_MARKER_RE = re.compile(r"\[citation:[^\]]+\]", re.IGNORECASE)
_CITATION_SPACING_RE = re.compile(r"\[citation:\s*([^\]]+?)\s*\]", re.IGNORECASE)
_REPEAT_BULLET_PREFIX_RE = re.compile(r"^[-*•]+\s*")
_STREAM_JSON_DECODER = json.JSONDecoder()
_CRITIC_JSON_START_RE = re.compile(r"\{\s*[\"']status[\"']\s*:", re.IGNORECASE)
_PIPELINE_JSON_START_RE = re.compile(
    r"\{\s*[\"'](?:intent_id|graph_complexity|selected_agents|status|decision|steps|execution_strategy|speculative_candidates|speculative_reused_tools|synthesis_drafts|chosen_layer)\b",
    re.IGNORECASE,
)
_PIPELINE_JSON_PARTIAL_KEY_RE = re.compile(
    r"\{\s*[\"']?([a-zA-Z_]{0,32})\Z",
    re.IGNORECASE,
)
_PIPELINE_JSON_KEYS = (
    "intent_id",
    "graph_complexity",
    "selected_agents",
    "status",
    "decision",
    "steps",
    "execution_strategy",
    "execution_reason",
    "speculative_candidates",
    "speculative_reused_tools",
    "speculative_remaining_tools",
    "speculative_discarded_tools",
    "synthesis_drafts",
    "reason",
    "confidence",
)
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->", re.IGNORECASE)
_INTERNAL_PIPELINE_CHAIN_TOKENS = (
    "resolve_intent",
    "speculative",
    "speculative_merge",
    "agent_resolver",
    "planner",
    "tool_resolver",
    "execution_router",
    "executor",
    "worker",
    "domain_planner",
    "critic",
    "response_layer_router",
)

# Pipeline nodes whose model output IS the final user-facing response.
# These are intentionally NOT in _INTERNAL_PIPELINE_CHAIN_TOKENS so their
# text streams as text-delta (visible response) rather than being buffered.
_OUTPUT_PIPELINE_CHAIN_TOKENS = (
    "synthesizer",
    "progressive_synthesizer",
    "response_layer",
    "smalltalk",
    "compare_synthesizer",
)

# Generic intermediate chain names inserted by LangGraph/LangChain between
# the actual graph node and the model call.  When walking parent_ids to find
# the graph node that owns a model, these must be skipped so the real node
# name (e.g. "planner") is found instead of a meaningless wrapper.
_GENERIC_CHAIN_NAMES: frozenset[str] = frozenset({
    "runnablesequence",
    "runnablelambda",
    "runnableparallel",
    "runnablebranch",
    "runnablewithfallbacks",
    "runnablepassthrough",
    "chatmodel",
    "chatlitellm",
    "basechatmodel",
    "llm",
    "chatprompttemplate",
    "prompttemplate",
    "chain",
    # Infrastructure/gate nodes that don't own model calls and should be
    # skipped when walking the parent chain to find the real pipeline node.
    "memory_context",
    "planner_hitl_gate",
    "execution_hitl_gate",
    "synthesis_hitl",
    "post_tools",
    "artifact_indexer",
    "context_compactor",
    "orchestration_guard",
    "tools",
    # LangGraph model wrapper names (the acall_model / call_model functions
    # used by executor show up as chain names — skip them).
    "call_model",
    "acall_model",
    "callmodel",
    "acallmodel",
})

# Regex to strip <think>…</think> blocks and bare tags from pipeline text
# so that reasoning content doesn't leak into visible step items.
_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_THINK_TAG_RE = re.compile(r"</?think>", re.IGNORECASE)

# Regex to strip stray XML-like tags that models sometimes emit in their
# output (e.g. </final_planner>, </tool_call>, <tool_call>, etc.).
# These are NOT <think> tags — those are handled by _ThinkStreamFilter.
# This catches opening and closing tags with optional attributes.
_STRAY_XML_TAG_RE = re.compile(
    r"</?(?:final_planner|tool_call|tool_result|function_call|function_result"
    r"|assistant|system|user|output|response|answer|result|plan|execution"
    r"|synthesis|critique|reflection|observation|action|thought"
    r"|step|task|query|context|instruction|reasoning|analysis)(?:\s[^>]*)?>",
    re.IGNORECASE,
)

# Mapping from pipeline chain-name tokens to user-facing titles for the
# unified think-box.  Nodes not listed here fall back to a title derived
# from the chain name.
_PIPELINE_NODE_TITLES: dict[str, str] = {
    "resolve_intent": "Analyserar frågan",
    "agent_resolver": "Väljer agenter",
    "planner": "Bygger plan",
    "tool_resolver": "Väljer verktyg",
    "execution_router": "Planerar utförande",
    "executor": "Utför uppgift",
    "worker": "Kör agent",
    "domain_planner": "Planerar domänkörning",
    "critic": "Granskar resultat",
    "progressive_synthesizer": "Förbereder utkast",
    "synthesizer": "Sammanställer svar",
    "response_layer_router": "Väljer presentationsläge",
    "response_layer": "Formaterar svar",
    "speculative": "Spekulativ förkörning",
    "speculative_merge": "Sammanfogar spekulativa resultat",
    "smalltalk": "Svarar direkt",
    "compare_synthesizer": "Sammanställer jämförelse",
}


def _pipeline_node_title(chain_name: str) -> str:
    """Return a user-facing title for the pipeline node identified by *chain_name*."""
    normalized = str(chain_name or "").strip().lower()
    for token, title in _PIPELINE_NODE_TITLES.items():
        if token in normalized:
            return title
    # Fallback: capitalize the chain name
    return chain_name.replace("_", " ").capitalize() if chain_name else "Bearbetar"


def _strip_inline_critic_payloads(text: str) -> tuple[str, bool]:
    if not text:
        return text, False
    parts: list[str] = []
    idx = 0
    removed = False
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            parts.append(text[idx:])
            break
        parts.append(text[idx:start])
        segment = text[start:]
        try:
            decoded, consumed = _STREAM_JSON_DECODER.raw_decode(segment)
        except ValueError:
            decoded = None
            consumed = 0
            for end in range(start + 1, min(len(text), start + 2400)):
                if text[end : end + 1] != "}":
                    continue
                candidate = text[start : end + 1]
                try:
                    parsed = ast.literal_eval(candidate)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    decoded = parsed
                    consumed = len(candidate)
                    break
            if decoded is None:
                parts.append(text[start : start + 1])
                idx = start + 1
                continue
        status = (
            str(decoded.get("status") or "").strip().lower()
            if isinstance(decoded, dict)
            else ""
        )
        if (
            isinstance(decoded, dict)
            and status in {"ok", "needs_more", "replan"}
            and "reason" in decoded
        ):
            removed = True
            idx = start + consumed
            continue
        parts.append(text[start : start + consumed])
        idx = start + consumed
    return "".join(parts), removed


def _normalize_line_for_dedupe(line: str) -> str:
    value = str(line or "").strip()
    value = _REPEAT_BULLET_PREFIX_RE.sub("", value)
    value = _CITATION_MARKER_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-").lower()
    return value


def _clean_assistant_output_text(text: str) -> str:
    if not text:
        return ""
    # Strip <think>…</think> blocks and bare tags first
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = _CRITIC_JSON_SNIPPET_RE.sub("", cleaned)
    cleaned, removed_inline = _strip_inline_critic_payloads(cleaned)
    cleaned, removed_payloads = _strip_inline_pipeline_payloads(cleaned)
    cleaned = _HTML_COMMENT_RE.sub("", cleaned)
    cleaned = _CITATION_SPACING_RE.sub(
        lambda match: f"[citation:{str(match.group(1) or '').strip()}]",
        cleaned,
    )
    lines = cleaned.splitlines()
    if removed_inline or removed_payloads or len(lines) > 3:
        seen: set[str] = set()
        deduped: list[str] = []
        duplicate_count = 0
        for line in lines:
            normalized = _normalize_line_for_dedupe(line)
            if normalized and len(normalized) >= 24:
                if normalized in seen:
                    duplicate_count += 1
                    continue
                seen.add(normalized)
            deduped.append(line)
        if duplicate_count:
            cleaned = "\n".join(deduped)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_json_objects_from_text(
    text: str, *, max_objects: int = 6
) -> list[dict[str, Any]]:
    value = str(text or "").strip()
    if not value:
        return []
    objects: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(value) and len(objects) < max(1, int(max_objects)):
        start = value.find("{", cursor)
        if start < 0:
            break
        segment = value[start:]
        parsed_obj: dict[str, Any] | None = None
        consumed = 0
        try:
            decoded, consumed = _STREAM_JSON_DECODER.raw_decode(segment)
            if isinstance(decoded, dict):
                parsed_obj = decoded
        except Exception:
            parsed_obj = None
            consumed = 0
        if parsed_obj is None:
            matched = False
            for end in range(start + 1, min(len(value), start + 2800)):
                if value[end : end + 1] != "}":
                    continue
                candidate = value[start : end + 1]
                try:
                    decoded = json.loads(candidate)
                except Exception:
                    try:
                        decoded = ast.literal_eval(candidate)
                    except Exception:
                        continue
                if isinstance(decoded, dict):
                    parsed_obj = decoded
                    consumed = len(candidate)
                    matched = True
                    break
            if not matched:
                cursor = start + 1
                continue
        if parsed_obj is not None and consumed > 0:
            objects.append(parsed_obj)
            cursor = start + consumed
        else:
            cursor = start + 1
    return objects


def _pipeline_payload_kind(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    if "intent_id" in payload and ("reason" in payload or "confidence" in payload):
        return "intent"
    if isinstance(payload.get("selected_agents"), list):
        return "agent_resolver"
    if isinstance(payload.get("steps"), list) and (
        "reason" in payload
        or any(
            isinstance(step, dict)
            and ("content" in step or "status" in step or "id" in step)
            for step in payload.get("steps")[:4]
        )
    ):
        return "planner"
    status = str(payload.get("status") or "").strip().lower()
    decision = str(payload.get("decision") or "").strip().lower()
    if (
        status in {"ok", "needs_more", "replan"}
        and isinstance(payload.get("reason"), str)
    ) or (
        decision in {"ok", "needs_more", "replan"}
        and isinstance(payload.get("reason"), str)
    ):
        return "critic"
    execution_strategy = str(payload.get("execution_strategy") or "").strip().lower()
    if execution_strategy in {"inline", "parallel", "subagent"}:
        return "execution_router"
    if isinstance(payload.get("speculative_candidates"), list) or isinstance(
        payload.get("speculative_reused_tools"),
        list,
    ):
        return "speculative"
    if isinstance(payload.get("synthesis_drafts"), list):
        return "progressive_synthesizer"
    if "chosen_layer" in payload and isinstance(payload.get("chosen_layer"), str):
        return "response_layer_router"
    return None


def _normalize_synthesis_draft_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    draft_text = str(
        value.get("draft") or value.get("text") or value.get("content") or ""
    ).strip()
    if not draft_text:
        return None
    confidence_raw = value.get("confidence")
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.5
    version_raw = value.get("version")
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        version = 0
    return {
        "draft": draft_text,
        "confidence": max(0.0, min(1.0, confidence)),
        "version": max(0, version),
    }


def _extract_synthesis_drafts_from_event_output(output: Any) -> list[dict[str, Any]]:
    if output is None:
        return []
    if isinstance(output, dict):
        drafts = output.get("synthesis_drafts")
        if isinstance(drafts, list):
            normalized: list[dict[str, Any]] = []
            for item in drafts:
                payload = _normalize_synthesis_draft_payload(item)
                if payload:
                    normalized.append(payload)
            if normalized:
                return normalized
        for key in ("output", "message", "messages", "generations"):
            if key not in output:
                continue
            nested = _extract_synthesis_drafts_from_event_output(output.get(key))
            if nested:
                return nested
        return []
    if isinstance(output, list):
        for item in reversed(output):
            nested = _extract_synthesis_drafts_from_event_output(item)
            if nested:
                return nested
        return []
    if hasattr(output, "generations"):
        nested = _extract_synthesis_drafts_from_event_output(
            output.generations,
        )
        if nested:
            return nested
    if hasattr(output, "message"):
        nested = _extract_synthesis_drafts_from_event_output(
            output.message,
        )
        if nested:
            return nested
    if hasattr(output, "synthesis_drafts"):
        return _extract_synthesis_drafts_from_event_output(
            output.synthesis_drafts,
        )
    return []


def _decode_json_object_from_text(
    text: str, start: int, *, max_scan: int = 3200
) -> tuple[dict[str, Any] | None, int]:
    if start < 0 or start >= len(text):
        return None, 0
    segment = text[start:]
    try:
        decoded, consumed = _STREAM_JSON_DECODER.raw_decode(segment)
    except Exception:
        decoded = None
        consumed = 0
    if isinstance(decoded, dict) and consumed > 0:
        return decoded, int(consumed)
    for end in range(start + 1, min(len(text), start + max_scan)):
        if text[end : end + 1] != "}":
            continue
        candidate = text[start : end + 1]
        parsed = None
        try:
            parsed = json.loads(candidate)
        except Exception:
            try:
                parsed = ast.literal_eval(candidate)
            except Exception:
                parsed = None
        if isinstance(parsed, dict):
            return parsed, len(candidate)
    return None, 0


def _strip_inline_pipeline_payloads(
    text: str,
) -> tuple[str, list[dict[str, Any]]]:
    if not text:
        return text, []
    parts: list[str] = []
    captured: list[dict[str, Any]] = []
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            parts.append(text[idx:])
            break
        parts.append(text[idx:start])
        decoded, consumed = _decode_json_object_from_text(text, start)
        if decoded is None or consumed <= 0:
            parts.append(text[start : start + 1])
            idx = start + 1
            continue
        kind = _pipeline_payload_kind(decoded)
        if kind:
            captured.append(decoded)
            idx = start + consumed
            continue
        parts.append(text[start : start + consumed])
        idx = start + consumed
    return "".join(parts), captured


def _split_trailing_pipeline_prefix(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    start = text.rfind("{")
    if start < 0:
        return text, ""
    tail = text[start:]
    if "}" in tail:
        return text, ""
    if _PIPELINE_JSON_START_RE.match(tail):
        return text[:start], tail
    partial = _PIPELINE_JSON_PARTIAL_KEY_RE.match(tail)
    if partial and len(tail) <= 80:
        prefix = str(partial.group(1) or "").strip().lower()
        if (not prefix and tail.strip() == "{") or any(
            key.startswith(prefix) for key in _PIPELINE_JSON_KEYS
        ):
            return text[:start], tail
    return text, ""


def _is_internal_pipeline_chain_name(chain_name: str) -> bool:
    """Return True if *chain_name* belongs to an internal (non-output) pipeline node.

    Models under these nodes have their content buffered and routed to
    reasoning-delta, NOT to text-delta.
    """
    normalized = str(chain_name or "").strip().lower()
    if not normalized:
        return False
    return any(token in normalized for token in _INTERNAL_PIPELINE_CHAIN_TOKENS)


def _is_any_pipeline_chain_name(chain_name: str) -> bool:
    """Return True if *chain_name* belongs to ANY pipeline node (internal or output).

    Used for step labeling and chain-end text extraction where we want to
    recognise all known pipeline nodes, not just the buffered ones.
    """
    normalized = str(chain_name or "").strip().lower()
    if not normalized:
        return False
    return any(
        token in normalized
        for token in (*_INTERNAL_PIPELINE_CHAIN_TOKENS, *_OUTPUT_PIPELINE_CHAIN_TOKENS)
    )


def _coerce_runtime_flag(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


class _ThinkStreamFilter:
    """Stateful parser that splits streaming text at <think>…</think> boundaries.

    Models like nvidia/nemotron emit reasoning tokens as plain text wrapped in
    <think>…</think> tags.  This filter separates them so the streaming handler
    can route them to ``reasoning-delta`` SSE events instead of ``text-delta``.

    Tags may span multiple chunks (e.g. ``"<thi"`` + ``"nk>"``).  The filter
    buffers the trailing bytes that could be the start of the next tag and only
    emits them once the ambiguity is resolved.

    **Template-prefilled <think> support:**

    When *assume_think* is ``True`` (the default) the filter starts in think
    mode, which means all initial content is emitted as reasoning.  This
    handles models whose chat template pre-fills ``<think>`` in the assistant
    turn (e.g. Qwen3) so that reasoning content is streamed in real-time
    instead of being retroactively reclassified when ``</think>`` appears.

    If the model does NOT use ``<think>`` tags at all, the entire response
    will be classified as reasoning (the ``flush()`` method keeps it as
    reasoning).  In practice this is rare since the global core prompt
    instructs all models to use ``<think>`` blocks.

    When *assume_think* is ``False`` the filter uses the legacy behaviour:
    content is treated as text until ``<think>`` is explicitly seen, and
    template-prefilled detection is performed retroactively.

    Usage::

        f = _ThinkStreamFilter(assume_think=True)
        for chunk in model_stream:
            reasoning, text = f.feed(chunk)
            # stream reasoning -> reasoning-delta, text -> text-delta
        reasoning, text = f.flush()   # resolve any trailing buffer at end-of-stream
    """

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self, *, assume_think: bool = True) -> None:
        self._assume_think = assume_think
        self._in_think = assume_think
        self._buf = ""
        self._ever_opened = assume_think
        # Text returned as main text before late-close was detected.
        # The streaming handler must re-emit this as reasoning-delta.
        self._pre_close_text_parts: list[str] = []
        self._late_close_detected = False

    @property
    def in_think(self) -> bool:
        return self._in_think

    @property
    def late_close_detected(self) -> bool:
        """True if ``</think>`` was found before any ``<think>``.

        This indicates the model's chat template pre-filled the opening
        ``<think>`` tag, so text emitted before the detection was actually
        reasoning content.
        """
        return self._late_close_detected

    def drain_retroactive_reasoning(self) -> str:
        """Return and clear text that was wrongly emitted as main text.

        Call this once after :attr:`late_close_detected` becomes ``True``
        to get the accumulated text from previous :meth:`feed` calls that
        should have been reasoning.
        """
        if not self._pre_close_text_parts:
            return ""
        text = "".join(self._pre_close_text_parts)
        self._pre_close_text_parts.clear()
        return text

    @staticmethod
    def _longest_prefix_match(s: str, pattern: str) -> int:
        """Return the length of the longest suffix of *s* that is a prefix of *pattern*."""
        for length in range(min(len(pattern) - 1, len(s)), 0, -1):
            if s.endswith(pattern[:length]):
                return length
        return 0

    def feed(self, chunk: str) -> tuple[str, str]:
        """Process *chunk* and return ``(reasoning_text, main_text)``."""
        self._buf += chunk
        reasoning_parts: list[str] = []
        text_parts: list[str] = []

        while self._buf:
            if self._in_think:
                # Inside a think block - look for the closing tag.
                # Also strip any redundant <think> tag that might appear
                # when assume_think is active and the model also outputs
                # an explicit <think> tag.
                close_idx = self._buf.find(self._CLOSE)
                open_idx = self._buf.find(self._OPEN)

                # Strip redundant <think> if it appears before </think>
                if open_idx != -1 and (close_idx == -1 or open_idx < close_idx):
                    reasoning_parts.append(self._buf[:open_idx])
                    self._buf = self._buf[open_idx + len(self._OPEN) :]
                    continue

                if close_idx == -1:
                    partial = max(
                        self._longest_prefix_match(self._buf, self._CLOSE),
                        self._longest_prefix_match(self._buf, self._OPEN),
                    )
                    safe = self._buf[:-partial] if partial else self._buf
                    reasoning_parts.append(safe)
                    self._buf = self._buf[-partial:] if partial else ""
                    break
                else:
                    reasoning_parts.append(self._buf[:close_idx])
                    self._buf = self._buf[close_idx + len(self._CLOSE) :]
                    self._in_think = False
            else:
                # Outside a think block.
                if not self._ever_opened and not self._late_close_detected:
                    # Haven't seen any tag yet — look for both <think> and </think>
                    # to handle template-prefilled <think>.
                    open_idx = self._buf.find(self._OPEN)
                    close_idx = self._buf.find(self._CLOSE)

                    if open_idx != -1 and (close_idx == -1 or open_idx <= close_idx):
                        # Normal case: <think> found first.
                        self._ever_opened = True
                        text_parts.append(self._buf[:open_idx])
                        self._buf = self._buf[open_idx + len(self._OPEN) :]
                        self._in_think = True
                    elif close_idx != -1:
                        # </think> found before any <think> — template prefill.
                        self._late_close_detected = True
                        reasoning_parts.append(self._buf[:close_idx])
                        self._buf = self._buf[close_idx + len(self._CLOSE) :]
                        # _in_think stays False (we just exited the implicit block)
                    else:
                        # Neither tag found — check partial match for both tags.
                        partial = max(
                            self._longest_prefix_match(self._buf, self._OPEN),
                            self._longest_prefix_match(self._buf, self._CLOSE),
                        )
                        safe = self._buf[:-partial] if partial else self._buf
                        # Track text that might need retroactive reclassification.
                        self._pre_close_text_parts.append(safe)
                        text_parts.append(safe)
                        self._buf = self._buf[-partial:] if partial else ""
                        break
                else:
                    # Resolved state — only look for <think>.
                    idx = self._buf.find(self._OPEN)
                    if idx == -1:
                        partial = self._longest_prefix_match(self._buf, self._OPEN)
                        safe = self._buf[:-partial] if partial else self._buf
                        text_parts.append(safe)
                        self._buf = self._buf[-partial:] if partial else ""
                        break
                    else:
                        text_parts.append(self._buf[:idx])
                        self._buf = self._buf[idx + len(self._OPEN) :]
                        self._in_think = True
                        self._ever_opened = True

        return "".join(reasoning_parts), "".join(text_parts)

    def reset_think_mode(self) -> tuple[str, str]:
        """Flush buffer and re-enter think mode for a new model call.

        When multiple models stream through the same filter instance, each
        model should start in think mode (if *assume_think* is True) so that
        a previous model's ``</think>`` doesn't cause the next model's
        content to be classified as main text.

        Returns the same ``(reasoning, text)`` tuple as :meth:`flush` for
        any residual buffered content.
        """
        result = self.flush()
        if self._assume_think:
            self._in_think = True
            self._ever_opened = True
        # Clear late-close state so the next model starts fresh
        self._late_close_detected = False
        self._pre_close_text_parts.clear()
        return result

    def flush(self) -> tuple[str, str]:
        """Drain any remaining buffer at end-of-stream."""
        remaining, self._buf = self._buf, ""
        if not remaining:
            return "", ""
        if self._in_think:
            return remaining, ""
        # If we never resolved (no tags seen at all), check if there's
        # buffered speculative text that should just be flushed as text.
        return "", remaining


async def stream_new_chat(
    user_query: str,
    search_space_id: int,
    chat_id: int,
    session: AsyncSession,
    user_id: str | None = None,
    llm_config_id: int = -1,
    attachments: list[ChatAttachment] | None = None,
    mentioned_document_ids: list[int] | None = None,
    mentioned_surfsense_doc_ids: list[int] | None = None,
    checkpoint_id: str | None = None,
    needs_history_bootstrap: bool = False,
    citation_instructions: str | bool | None = None,
    runtime_hitl: dict[str, Any] | None = None,
    checkpoint_ns_override: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream chat responses from the new SurfSense deep agent.

    This uses the Vercel AI SDK Data Stream Protocol (SSE format) for streaming.
    The chat_id is used as LangGraph's thread_id for memory/checkpointing.

    Args:
        user_query: The user's query
        search_space_id: The search space ID
        chat_id: The chat ID (used as LangGraph thread_id for memory)
        session: The database session
        user_id: The current user's UUID string (for memory tools and session state)
        llm_config_id: The LLM configuration ID (default: -1 for first global config)
        attachments: Optional attachments with extracted content
        needs_history_bootstrap: If True, load message history from DB (for cloned chats)
        mentioned_document_ids: Optional list of document IDs mentioned with @ in the chat
        mentioned_surfsense_doc_ids: Optional list of SurfSense doc IDs mentioned with @ in the chat
        checkpoint_id: Optional checkpoint ID to rewind/fork from (for edit/reload operations)
        citation_instructions:
            - True: enable admin/default citation instructions.
            - False/None: disable citation instruction injection.
            - str: inject custom citation instructions.
        runtime_hitl:
            Optional runtime flags. Supports:
            - planner/execution/synthesis HITL checkpoints.
            - hybrid_mode (bool): enables hybrid supervisor routing.
            - speculative_enabled (bool): enables speculative execution paths.
            - subagent_enabled (bool): allows execution_strategy=subagent paths.
            - subagent_isolation_enabled (bool): enables strict subagent context isolation.
            - subagent_max_concurrency (int): max parallel subagent calls per step.
            - subagent_context_max_chars (int): max parent context chars injected to subagent.
            - subagent_result_max_chars (int): max compacted subagent result chars.
            - subagent_sandbox_scope (str): sandbox scope policy ("thread" or "subagent").
            - artifact_offload_enabled (bool): offload large tool payloads to artifacts.
            - artifact_offload_threshold_chars (int): offload threshold for payload size.
            - artifact_offload_max_entries (int): max artifact entries kept in state.
            - artifact_offload_storage_mode (str): "auto", "sandbox", or "local" artifact storage backend.
            - context_compaction_enabled (bool): enables semantic context compactor.
            - context_compaction_trigger_ratio (float): token-budget ratio that triggers compaction.
            - context_compaction_summary_max_chars (int): max chars in rolling summary.
            - cross_session_memory_enabled (bool): enables selective persistent memory injection.
            - cross_session_memory_max_items (int): max persistent memory items injected.
            - cross_session_memory_max_chars (int): max chars for injected memory context.
            - sandbox_enabled (bool): enables sandbox execution tools for code tasks.
            - sandbox_mode (str): sandbox runtime mode ("docker", "local", or "provisioner").
            - sandbox_provisioner_url (str): provisioner base URL when mode=provisioner.
            - sandbox_state_store (str): "file", "redis", or "auto" for lease/state storage.
            - sandbox_idle_timeout_seconds (int): idle timeout before sandbox lease cleanup.
        checkpoint_ns_override:
            Optional explicit checkpoint namespace. When provided, bypasses automatic
            namespace resolution and uses this value ("" means legacy namespace).

    Yields:
        str: SSE formatted response strings
    """
    streaming_service = VercelStreamingService()
    external_model_tool_names = {spec.tool_name for spec in EXTERNAL_MODEL_SPECS}
    raw_user_query = user_query
    compare_mode = is_compare_request(user_query)
    compare_query = extract_compare_query(user_query) if compare_mode else ""

    # Track the current text block for streaming (defined early for exception handling)
    current_text_id: str | None = None
    trace_recorder: TraceRecorder | None = None
    trace_db_session: AsyncSession | None = None

    try:
        # Mark AI as responding to this user for live collaboration
        if user_id:
            await set_ai_responding(session, chat_id, UUID(user_id))

        # Auto-save user memories from the raw query (best-effort)
        memory_query = compare_query or user_query
        if user_id and memory_query:
            try:
                auto_memories = extract_auto_memories(memory_query)
                if auto_memories:
                    save_memory = create_save_memory_tool(
                        user_id=user_id,
                        search_space_id=search_space_id,
                        db_session=session,
                    )
                    for content, category in auto_memories:
                        await save_memory(content=content, category=category)
            except Exception as exc:
                print(f"[auto-memory] Failed to save memories: {exc!s}")

        try:
            trace_db_session = async_session_maker()
            trace_session = ChatTraceSession(
                session_id=uuid.uuid4().hex,
                thread_id=chat_id,
                created_by_id=UUID(user_id) if user_id else None,
            )
            trace_db_session.add(trace_session)
            await trace_db_session.commit()
            await trace_db_session.refresh(trace_session)
            trace_recorder = TraceRecorder(
                db_session=trace_db_session,
                trace_session=trace_session,
                streaming_service=streaming_service,
                root_name="Chat Response",
                root_input={
                    "query": raw_user_query,
                    "attachments": [a.name for a in attachments or []],
                    "mentioned_document_ids": mentioned_document_ids or [],
                    "mentioned_surfsense_doc_ids": mentioned_surfsense_doc_ids or [],
                },
            )
            yield await trace_recorder.emit_session_start()
            root_event = await trace_recorder.start_root_span()
            if root_event:
                yield root_event
        except Exception as exc:
            if trace_db_session:
                await trace_db_session.rollback()
            trace_recorder = None
            print(f"[trace] Failed to initialize trace session: {exc!s}")
        # Load LLM config - supports both YAML (negative IDs) and database (positive IDs)
        agent_config: AgentConfig | None = None

        if llm_config_id >= 0:
            # Positive ID: Load from NewLLMConfig database table
            agent_config = await load_agent_config(
                session=session,
                config_id=llm_config_id,
                search_space_id=search_space_id,
            )
            if not agent_config:
                yield streaming_service.format_error(
                    f"Failed to load NewLLMConfig with id {llm_config_id}"
                )
                yield streaming_service.format_done()
                return

            # Create ChatLiteLLM from AgentConfig
            llm = create_chat_litellm_from_agent_config(agent_config)
        else:
            # Negative ID: Load from YAML (global configs)
            llm_config = load_llm_config_from_yaml(llm_config_id=llm_config_id)
            if not llm_config:
                yield streaming_service.format_error(
                    f"Failed to load LLM config with id {llm_config_id}"
                )
                yield streaming_service.format_done()
                return

            # Create ChatLiteLLM from YAML config dict
            llm = create_chat_litellm_from_config(llm_config)
            # Create AgentConfig from YAML for consistency (uses defaults for prompt settings)
            agent_config = AgentConfig.from_yaml_config(llm_config)

        if not llm:
            yield streaming_service.format_error("Failed to create LLM instance")
            yield streaming_service.format_done()
            return

        tokenizer_model = None
        if agent_config and agent_config.model_name:
            tokenizer_model = agent_config.model_name
        if not tokenizer_model:
            model_attr = getattr(llm, "model", None)
            if isinstance(model_attr, str) and model_attr.strip():
                tokenizer_model = model_attr.strip()
        if trace_recorder and tokenizer_model:
            trace_recorder.set_tokenizer_model(tokenizer_model)

        prompt_overrides = await get_global_prompt_overrides(session)

        # Resolve the global core prompt (Swedish thinking, date/time) and
        # resolve its date/time placeholders so it is ready to prepend.
        _raw_core_prompt = resolve_prompt(
            prompt_overrides,
            "system.core.global",
            SURFSENSE_CORE_GLOBAL_PROMPT,
        )
        core_global_prompt = append_datetime_context(_raw_core_prompt.strip())

        default_system_prompt = resolve_prompt(
            prompt_overrides,
            "system.default.instructions",
            SURFSENSE_SYSTEM_INSTRUCTIONS,
        )
        default_system_prompt = inject_core_prompt(
            core_global_prompt, default_system_prompt
        )
        if agent_config is not None:
            has_custom_system_prompt = bool(
                str(agent_config.system_instructions or "").strip()
            )
            if (
                agent_config.use_default_system_instructions
                and not has_custom_system_prompt
            ):
                # Keep default system prompt centrally editable from /admin/prompts.
                agent_config = replace(
                    agent_config,
                    system_instructions=default_system_prompt,
                    use_default_system_instructions=False,
                )
        router_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides, "router.top_level", DEFAULT_ROUTE_SYSTEM_PROMPT
            ),
        )
        try:
            routing_history = await _load_conversation_history_for_routing(
                session,
                chat_id,
                raw_user_query,
            )
        except Exception:
            routing_history = []
        followup_context_block = _build_followup_context_block(
            raw_user_query, routing_history
        )

        try:
            intent_definitions = await get_effective_intent_definitions(session)
        except Exception:
            intent_definitions = list(get_default_intent_definitions().values())

        route, route_decision = await dispatch_route_with_trace(
            raw_user_query,
            llm,
            has_attachments=bool(attachments),
            has_mentions=bool(mentioned_document_ids or mentioned_surfsense_doc_ids),
            system_prompt_override=router_prompt,
            conversation_history=routing_history,
            intent_definitions=intent_definitions,
        )

        # Sync compare_mode with route decision
        # Router can identify compare requests even without /compare prefix
        if route == Route.JAMFORELSE:
            compare_mode = True
            # Always extract compare query when route is COMPARE, even if initial detection failed
            if not compare_query:
                compare_query = extract_compare_query(raw_user_query)
            if compare_query:
                user_query = compare_query
            followup_context_block = ""

        worker_system_prompt: str | None = None
        supervisor_system_prompt: str | None = None
        smalltalk_prompt: str | None = None

        citation_prompt_default = resolve_prompt(
            prompt_overrides,
            "citation.instructions",
            SURFSENSE_CITATION_INSTRUCTIONS,
        )
        if isinstance(citation_instructions, bool):
            citation_instructions_block = (
                citation_prompt_default.strip() if citation_instructions else None
            )
        else:
            explicit_citation_instructions = str(citation_instructions or "").strip()
            citation_instructions_block = (
                explicit_citation_instructions
                if explicit_citation_instructions
                else None
            )
        citations_enabled = bool(citation_instructions_block)
        supervisor_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.supervisor.system",
                DEFAULT_SUPERVISOR_PROMPT,
            ),
        )
        supervisor_system_prompt = build_supervisor_prompt(
            supervisor_prompt,
            citation_instructions=citation_instructions_block,
        )
        if route == Route.JAMFORELSE:
            compare_supervisor_instructions = resolve_prompt(
                prompt_overrides,
                "compare.supervisor.instructions",
                COMPARE_SUPERVISOR_INSTRUCTIONS,
            )
            supervisor_system_prompt = (
                supervisor_system_prompt + "\n\n" + compare_supervisor_instructions
            )

        knowledge_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.knowledge.system",
                resolve_prompt(
                    prompt_overrides,
                    "agent.worker.knowledge",
                    DEFAULT_WORKER_KNOWLEDGE_PROMPT,
                ),
            ),
        )
        knowledge_worker_prompt = build_worker_prompt(
            knowledge_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        )
        action_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.action.system",
                resolve_prompt(
                    prompt_overrides,
                    "agent.worker.action",
                    DEFAULT_WORKER_ACTION_PROMPT,
                ),
            ),
        )
        action_worker_prompt = build_worker_prompt(
            action_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        )
        media_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.media.system",
                action_prompt,
            ),
        )
        browser_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.browser.system",
                knowledge_prompt,
            ),
        )
        code_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.code.system",
                knowledge_prompt,
            ),
        )
        kartor_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.kartor.system",
                action_prompt,
            ),
        )
        statistics_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.statistics.system",
                DEFAULT_STATISTICS_SYSTEM_PROMPT,
            ),
        )
        statistics_worker_prompt = build_statistics_system_prompt(
            statistics_prompt,
            citation_instructions=citation_instructions_block,
        )
        synthesis_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.synthesis.system",
                statistics_prompt,
            ),
        )
        bolag_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.bolag.system",
                DEFAULT_BOLAG_SYSTEM_PROMPT,
            ),
        )
        bolag_worker_prompt = build_bolag_prompt(
            bolag_prompt,
            citation_instructions=citation_instructions_block,
        )
        trafik_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.trafik.system",
                DEFAULT_TRAFFIC_SYSTEM_PROMPT,
            ),
        )
        trafik_worker_prompt = build_trafik_prompt(
            trafik_prompt,
            citation_instructions=citation_instructions_block,
        )
        riksdagen_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.riksdagen.system",
                DEFAULT_RIKSDAGEN_SYSTEM_PROMPT,
            ),
        )
        riksdagen_worker_prompt = build_worker_prompt(
            riksdagen_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        )
        marketplace_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "agent.marketplace.system",
                DEFAULT_MARKETPLACE_SYSTEM_PROMPT,
            ),
        )
        marketplace_worker_prompt = build_marketplace_prompt(
            marketplace_prompt,
            citation_instructions=citation_instructions_block,
        )
        compare_analysis_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "compare.analysis.system",
                DEFAULT_COMPARE_ANALYSIS_PROMPT,
            ),
        )
        compare_synthesis_prompt = build_compare_synthesis_prompt(
            compare_analysis_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        )
        compare_external_prompt = inject_core_prompt(
            core_global_prompt,
            resolve_prompt(
                prompt_overrides,
                "compare.external.system",
                DEFAULT_EXTERNAL_SYSTEM_PROMPT,
            ),
        )

        if route == Route.KONVERSATION:
            smalltalk_prompt = inject_core_prompt(
                core_global_prompt,
                resolve_prompt(
                    prompt_overrides,
                    "agent.smalltalk.system",
                    SMALLTALK_INSTRUCTIONS,
                ),
            )
        else:
            worker_system_prompt = supervisor_system_prompt

        runtime_flags = dict(runtime_hitl or {})
        hybrid_mode = _coerce_runtime_flag(
            runtime_flags.get("hybrid_mode"),
            default=False,
        )
        speculative_enabled = _coerce_runtime_flag(
            runtime_flags.get("speculative_enabled"),
            default=False,
        )
        sandbox_enabled = _coerce_runtime_flag(
            runtime_flags.get("sandbox_enabled"),
            default=False,
        )
        sandbox_mode = (
            str(runtime_flags.get("sandbox_mode") or "docker").strip().lower()
        )
        if sandbox_mode == "remote":
            sandbox_mode = "provisioner"
        sandbox_provisioner_url = str(
            runtime_flags.get("sandbox_provisioner_url")
            or runtime_flags.get("sandbox_service_url")
            or ""
        ).strip()
        sandbox_state_store = (
            str(runtime_flags.get("sandbox_state_store") or "file").strip().lower()
        )
        try:
            sandbox_idle_timeout_seconds = int(
                runtime_flags.get("sandbox_idle_timeout_seconds") or 15 * 60
            )
        except (TypeError, ValueError):
            sandbox_idle_timeout_seconds = 15 * 60
        think_enabled = _coerce_runtime_flag(
            runtime_flags.get("think_enabled"),
            default=True,
        )
        subagent_enabled = _coerce_runtime_flag(
            runtime_flags.get("subagent_enabled"),
            default=True,
        )
        subagent_isolation_enabled = subagent_enabled and _coerce_runtime_flag(
            runtime_flags.get("subagent_isolation_enabled"),
            default=False,
        )
        try:
            subagent_max_concurrency = int(
                runtime_flags.get("subagent_max_concurrency") or 3
            )
        except (TypeError, ValueError):
            subagent_max_concurrency = 3
        try:
            subagent_context_max_chars = int(
                runtime_flags.get("subagent_context_max_chars") or 1400
            )
        except (TypeError, ValueError):
            subagent_context_max_chars = 1400
        try:
            subagent_result_max_chars = int(
                runtime_flags.get("subagent_result_max_chars") or 1000
            )
        except (TypeError, ValueError):
            subagent_result_max_chars = 1000
        subagent_sandbox_scope = (
            str(
                runtime_flags.get("subagent_sandbox_scope")
                or runtime_flags.get("sandbox_scope")
                or "thread"
            )
            .strip()
            .lower()
        )
        artifact_offload_enabled = _coerce_runtime_flag(
            runtime_flags.get("artifact_offload_enabled"),
            default=False,
        )
        artifact_offload_storage_mode = (
            str(runtime_flags.get("artifact_offload_storage_mode") or "auto")
            .strip()
            .lower()
        )
        if artifact_offload_storage_mode not in {"auto", "sandbox", "local"}:
            artifact_offload_storage_mode = "auto"
        context_compaction_enabled = _coerce_runtime_flag(
            runtime_flags.get("context_compaction_enabled"),
            default=True,
        )
        try:
            context_compaction_trigger_ratio = float(
                runtime_flags.get("context_compaction_trigger_ratio") or 0.65
            )
        except (TypeError, ValueError):
            context_compaction_trigger_ratio = 0.65
        cross_session_memory_enabled = _coerce_runtime_flag(
            runtime_flags.get("cross_session_memory_enabled"),
            default=True,
        )
        try:
            cross_session_memory_max_items = int(
                runtime_flags.get("cross_session_memory_max_items") or 6
            )
        except (TypeError, ValueError):
            cross_session_memory_max_items = 6
        if not hybrid_mode:
            speculative_enabled = False

        if trace_recorder:
            route_span_id = f"route-{uuid.uuid4().hex[:8]}"
            route_meta = {
                "route": route.value,
                "route_source": str(route_decision.get("source") or ""),
                "route_confidence": route_decision.get("confidence"),
                "route_reason": str(route_decision.get("reason") or ""),
                "route_candidates": route_decision.get("candidates") or [],
                "citations_enabled": citations_enabled,
                "citation_instructions_enabled": citations_enabled,
                "runtime_hitl": runtime_hitl or {},
                "hybrid_mode": hybrid_mode,
                "speculative_enabled": speculative_enabled,
                "subagent_enabled": subagent_enabled,
                "subagent_isolation_enabled": subagent_isolation_enabled,
                "subagent_max_concurrency": subagent_max_concurrency,
                "subagent_context_max_chars": subagent_context_max_chars,
                "subagent_result_max_chars": subagent_result_max_chars,
                "subagent_sandbox_scope": subagent_sandbox_scope,
                "artifact_offload_enabled": artifact_offload_enabled,
                "artifact_offload_storage_mode": artifact_offload_storage_mode,
                "context_compaction_enabled": context_compaction_enabled,
                "context_compaction_trigger_ratio": context_compaction_trigger_ratio,
                "cross_session_memory_enabled": cross_session_memory_enabled,
                "cross_session_memory_max_items": cross_session_memory_max_items,
                "sandbox_enabled": sandbox_enabled,
                "sandbox_mode": sandbox_mode,
                "sandbox_provisioner_url": sandbox_provisioner_url,
                "sandbox_state_store": sandbox_state_store,
                "sandbox_idle_timeout_seconds": sandbox_idle_timeout_seconds,
            }
            route_start = await trace_recorder.start_span(
                span_id=route_span_id,
                name="Routing request",
                kind="middleware",
                parent_id=trace_recorder.root_span_id,
                input_data={"query": raw_user_query},
                meta=route_meta,
            )
            if route_start:
                yield route_start
            route_end = await trace_recorder.end_span(
                span_id=route_span_id,
                output_data=route_meta,
                status="completed",
            )
            if route_end:
                yield route_end

        checkpoint_ns = ""
        if route != Route.KONVERSATION:
            # Create connector service
            connector_service = ConnectorService(
                session, search_space_id=search_space_id, user_id=user_id
            )

            # Get Firecrawl API key from webcrawler connector if configured
            from app.db import SearchSourceConnectorType

            firecrawl_api_key = None
            webcrawler_connector = await connector_service.get_connector_by_type(
                SearchSourceConnectorType.WEBCRAWLER_CONNECTOR, search_space_id
            )
            if webcrawler_connector and webcrawler_connector.config:
                firecrawl_api_key = webcrawler_connector.config.get("FIRECRAWL_API_KEY")

            preferred_checkpoint_ns = build_checkpoint_namespace(
                user_id=user_id,
                flow="new_chat_v2",
            )

            # Get the PostgreSQL checkpointer for persistent conversation memory
            checkpointer = await get_checkpointer()
            if checkpoint_ns_override is not None:
                checkpoint_ns = str(checkpoint_ns_override).strip()
            else:
                checkpoint_ns = await resolve_checkpoint_namespace_for_thread(
                    checkpointer=checkpointer,
                    thread_id=chat_id,
                    preferred_namespace=preferred_checkpoint_ns,
                )

            print(
                "[DEBUG] Building graph with "
                f"compare_mode={compare_mode}, "
                f"hybrid_mode={hybrid_mode}, "
                f"speculative_enabled={speculative_enabled}, "
                f"subagent_enabled={subagent_enabled}, "
                f"subagent_isolation_enabled={subagent_isolation_enabled}, "
                f"subagent_max_concurrency={subagent_max_concurrency}, "
                f"subagent_sandbox_scope={subagent_sandbox_scope}, "
                f"artifact_offload_enabled={artifact_offload_enabled}, "
                f"artifact_offload_storage_mode={artifact_offload_storage_mode}, "
                f"context_compaction_enabled={context_compaction_enabled}, "
                f"context_compaction_trigger_ratio={context_compaction_trigger_ratio:.2f}, "
                f"cross_session_memory_enabled={cross_session_memory_enabled}, "
                f"cross_session_memory_max_items={cross_session_memory_max_items}, "
                f"sandbox_enabled={sandbox_enabled}, "
                f"sandbox_mode={sandbox_mode}, "
                f"sandbox_provisioner_url={sandbox_provisioner_url or '<none>'}, "
                f"sandbox_state_store={sandbox_state_store}, "
                f"sandbox_idle_timeout_seconds={sandbox_idle_timeout_seconds}"
            )
            agent = await build_complete_graph(
                llm=llm,
                dependencies={
                    "search_space_id": search_space_id,
                    "db_session": session,
                    "connector_service": connector_service,
                    "firecrawl_api_key": firecrawl_api_key,
                    "user_id": user_id,
                    "thread_id": chat_id,
                    "checkpoint_ns": checkpoint_ns,
                    "runtime_hitl": dict(runtime_hitl or {}),
                    "trace_recorder": trace_recorder,
                    "trace_parent_span_id": (
                        trace_recorder.root_span_id if trace_recorder else None
                    ),
                },
                checkpointer=checkpointer,
                knowledge_prompt=knowledge_worker_prompt,
                action_prompt=action_worker_prompt,
                statistics_prompt=statistics_worker_prompt,
                synthesis_prompt=compare_synthesis_prompt or synthesis_prompt,
                compare_mode=compare_mode,
                hybrid_mode=hybrid_mode,
                speculative_enabled=speculative_enabled,
                external_model_prompt=compare_external_prompt,
                bolag_prompt=bolag_worker_prompt,
                trafik_prompt=trafik_worker_prompt,
                media_prompt=build_worker_prompt(
                    media_prompt,
                    citations_enabled=citations_enabled,
                    citation_instructions=citation_instructions_block,
                ),
                browser_prompt=build_worker_prompt(
                    browser_prompt,
                    citations_enabled=citations_enabled,
                    citation_instructions=citation_instructions_block,
                ),
                code_prompt=build_worker_prompt(
                    code_prompt,
                    citations_enabled=citations_enabled,
                    citation_instructions=citation_instructions_block,
                ),
                kartor_prompt=build_worker_prompt(
                    kartor_prompt,
                    citations_enabled=citations_enabled,
                    citation_instructions=citation_instructions_block,
                ),
                riksdagen_prompt=riksdagen_worker_prompt,
                marketplace_prompt=marketplace_worker_prompt,
                tool_prompt_overrides=prompt_overrides,
            )
        else:
            smalltalk_system_prompt = append_datetime_context(
                str(smalltalk_prompt or SMALLTALK_INSTRUCTIONS).strip()
            )

            async def _run_smalltalk_fast_path(state: dict[str, Any]) -> dict[str, Any]:
                incoming = list(state.get("messages") or [])
                latest_query = ""
                for message in reversed(incoming):
                    if isinstance(message, HumanMessage):
                        latest_query = str(message.content or "").strip()
                        if latest_query:
                            break
                if not latest_query and incoming:
                    latest_query = str(
                        getattr(incoming[-1], "content", "") or ""
                    ).strip()
                if not latest_query:
                    latest_query = str(raw_user_query or "").strip()
                response = await llm.ainvoke(
                    [
                        SystemMessage(content=smalltalk_system_prompt),
                        HumanMessage(content=latest_query),
                    ]
                )
                if isinstance(response, AIMessage):
                    assistant_message = response
                else:
                    assistant_message = AIMessage(
                        content=str(getattr(response, "content", "") or response or "")
                    )
                return {"messages": [assistant_message]}

            agent = RunnableLambda(_run_smalltalk_fast_path).with_config(
                {"run_name": "SmalltalkFastPath"}
            )

        # Build input with message history
        langchain_messages = []

        # Bootstrap history for cloned chats (no LangGraph checkpoint exists yet)
        if needs_history_bootstrap:
            langchain_messages = await bootstrap_history_from_db(session, chat_id)

            # Clear the flag so we don't bootstrap again on next message
            from app.db import NewChatThread

            thread_result = await session.execute(
                select(NewChatThread).filter(NewChatThread.id == chat_id)
            )
            thread = thread_result.scalars().first()
            if thread:
                thread.needs_history_bootstrap = False
                await session.commit()

        # Fetch mentioned documents if any (with chunks for proper citations)
        mentioned_documents: list[Document] = []
        if mentioned_document_ids:
            from sqlalchemy.orm import selectinload as doc_selectinload

            result = await session.execute(
                select(Document)
                .options(doc_selectinload(Document.chunks))
                .filter(
                    Document.id.in_(mentioned_document_ids),
                    Document.search_space_id == search_space_id,
                )
            )
            mentioned_documents = list(result.scalars().all())

        # Fetch mentioned SurfSense docs if any
        mentioned_surfsense_docs: list[SurfsenseDocsDocument] = []
        if mentioned_surfsense_doc_ids:
            from sqlalchemy.orm import selectinload

            result = await session.execute(
                select(SurfsenseDocsDocument)
                .options(selectinload(SurfsenseDocsDocument.chunks))
                .filter(
                    SurfsenseDocsDocument.id.in_(mentioned_surfsense_doc_ids),
                )
            )
            mentioned_surfsense_docs = list(result.scalars().all())

        # Format the user query with context (attachments + mentioned documents + surfsense docs)
        final_query = user_query
        context_parts: list[str] = []
        attachments_context = ""
        mentioned_documents_context = ""
        mentioned_surfsense_context = ""
        followup_context = followup_context_block.strip()

        if followup_context:
            context_parts.append(followup_context)

        if attachments:
            attachments_context = format_attachments_as_context(attachments)
            if attachments_context:
                context_parts.append(attachments_context)

        if mentioned_documents:
            mentioned_documents_context = format_mentioned_documents_as_context(
                mentioned_documents
            )
            if mentioned_documents_context:
                context_parts.append(mentioned_documents_context)

        if mentioned_surfsense_docs:
            mentioned_surfsense_context = format_mentioned_surfsense_docs_as_context(
                mentioned_surfsense_docs
            )
            if mentioned_surfsense_context:
                context_parts.append(mentioned_surfsense_context)

        if context_parts:
            context = "\n\n".join(context_parts)
            final_query = f"{context}\n\n<user_query>{user_query}</user_query>"

        base_tokens = estimate_tokens_from_text(user_query, model=tokenizer_model)
        total_tokens = estimate_tokens_from_text(final_query, model=tokenizer_model)
        context_stats: dict[str, object] = {
            "base_chars": len(user_query),
            "base_tokens": base_tokens,
            "context_chars": max(0, len(final_query) - len(user_query)),
            "context_tokens": max(0, total_tokens - base_tokens),
            "tool_chars": 0,
            "tool_tokens": 0,
            "total_chars": len(final_query),
            "total_tokens": total_tokens,
            "breakdown": {
                "followup_context_chars": len(followup_context),
                "attachments_chars": len(attachments_context),
                "mentioned_docs_chars": len(mentioned_documents_context),
                "mentioned_surfsense_docs_chars": len(mentioned_surfsense_context),
            },
        }

        # if messages:
        #     # Convert frontend messages to LangChain format
        #     for msg in messages:
        #         if msg.role == "user":
        #             langchain_messages.append(HumanMessage(content=msg.content))
        #         elif msg.role == "assistant":
        #             langchain_messages.append(AIMessage(content=msg.content))
        # else:
        # Fallback: just use the current user query with attachment context
        langchain_messages.append(HumanMessage(content=final_query))
        request_turn_id = uuid.uuid4().hex

        input_state: dict = {
            # Lets not pass this message atm because we are using the checkpointer to manage the conversation history
            # We will use this to simulate group chat functionality in the future
            "messages": langchain_messages,
            "turn_id": request_turn_id,
        }
        # Store the worker system prompt as a dedicated state key so that the
        # executor can always inject it as the leading SystemMessage without
        # ever embedding it inside the `messages` list.  Putting a SystemMessage
        # into `messages` causes LangGraph's add_messages reducer to accumulate
        # one extra SystemMessage per turn, ultimately producing invalid
        # [system, user, system, user] sequences that crash strict Jinja
        # templates (LM Studio / nemotron "Cannot apply filter 'string' to type:
        # NullValue").
        if worker_system_prompt:
            input_state["worker_system_prompt"] = worker_system_prompt
        if route == Route.KONVERSATION:
            input_state["search_space_id"] = search_space_id
        else:
            input_state["route_hint"] = route.value

        # Configure LangGraph with thread_id for memory
        # If checkpoint_id is provided, fork from that checkpoint (for edit/reload)
        configurable = {"thread_id": str(chat_id)}
        if checkpoint_ns:
            configurable["checkpoint_ns"] = checkpoint_ns
        if checkpoint_id:
            configurable["checkpoint_id"] = checkpoint_id

        config = {
            "configurable": configurable,
            "recursion_limit": 80,  # Increase from default 25 to allow more tool iterations
        }

        # Start the message stream
        yield streaming_service.format_message_start()
        yield streaming_service.format_start_step()
        yield streaming_service.format_data(
            "context-stats",
            {
                "phase": "initial",
                "label": "Initial context",
                "delta_chars": context_stats.get("context_chars", 0),
                "delta_tokens": context_stats.get("context_tokens", 0),
                "total_chars": context_stats.get("total_chars", 0),
                "total_tokens": context_stats.get("total_tokens", 0),
                "base_chars": context_stats.get("base_chars", 0),
                "base_tokens": context_stats.get("base_tokens", 0),
                "context_chars": context_stats.get("context_chars", 0),
                "context_tokens": context_stats.get("context_tokens", 0),
                "tool_chars": context_stats.get("tool_chars", 0),
                "tool_tokens": context_stats.get("tool_tokens", 0),
                "breakdown": context_stats.get("breakdown", {}),
            },
        )

        # Reset text tracking for this stream
        accumulated_text = ""
        critic_buffer = ""
        suppress_critic = False
        repeat_buffer = ""
        suppress_repeat = False
        repeat_candidate = False

        # Track thinking steps for chain-of-thought display
        thinking_step_counter = 0
        # Map run_id -> step_id for tool calls so we can update them on completion
        tool_step_ids: dict[str, str] = {}
        tool_inputs: dict[str, dict[str, Any]] = {}
        write_todos_step_id: str | None = None
        # Track the last active step so we can mark it complete at the end
        last_active_step_id: str | None = None
        last_active_step_title: str = ""
        last_active_step_items: list[str] = []
        # Track which steps have been completed to avoid duplicate completions
        completed_step_ids: set[str] = set()
        # Track if we just finished a tool (text flows silently after tools)
        just_finished_tool: bool = False
        # Track write_todos calls to show "Creating plan" vs "Updating plan"
        write_todos_call_count: int = 0
        # Fallback text captured from non-streaming model/chain events
        fallback_assistant_text: str = ""
        chain_name_by_run_id: dict[str, str] = {}
        model_parent_chain_by_run_id: dict[str, str] = {}
        internal_model_buffers: dict[str, str] = {}
        emitted_pipeline_payload_signatures: set[str] = set()
        emitted_synthesis_draft_signatures: set[str] = set()
        streamed_tool_call_ids: set[str] = (
            set()
        )  # Track tool calls already streamed to prevent duplicates
        stream_pipeline_prefix_buffer: str = ""
        # Think-tag streaming state
        _think_filter = _ThinkStreamFilter(assume_think=think_enabled)
        active_reasoning_id: str | None = None
        _late_close_handled = False  # Guard for template-prefilled <think> handling

        # --- Node-by-node think-box state ---
        # Per-node ThinkStreamFilter instances keyed by model run_id.
        # When a pipeline node's LLM call streams tokens, we run them
        # through a dedicated filter to extract <think> reasoning per node.
        internal_node_think_filters: dict[str, _ThinkStreamFilter] = {}
        # Track which pipeline node last emitted reasoning so we can inject
        # transition headers (e.g. "--- Resolving intent ---") into the
        # global rolling reasoning stream.
        last_reasoning_pipeline_node: str = ""

        route_label = f"Supervisor/{route.value.capitalize()}"
        route_prefix = f"[{route_label}] "

        def format_step_title(title: str) -> str:
            if not title:
                return title
            if title.startswith(route_prefix):
                return title
            return f"{route_prefix}{title}"

        def next_thinking_step_id() -> str:
            nonlocal thinking_step_counter
            thinking_step_counter += 1
            return f"thinking-{thinking_step_counter}"

        def complete_current_step() -> str | None:
            """Complete the current active step and return the completion event, if any."""
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

        def emit_pipeline_steps_from_payloads(
            payloads: list[dict[str, Any]],
            *,
            source_chain: str | None = None,
        ) -> list[str]:
            events: list[str] = []
            for payload in payloads:
                kind = _pipeline_payload_kind(payload)
                if not kind:
                    continue
                signature = json.dumps(payload, ensure_ascii=True, sort_keys=True)
                if signature in emitted_pipeline_payload_signatures:
                    continue
                emitted_pipeline_payload_signatures.add(signature)

                completion_event = complete_current_step()
                if completion_event:
                    events.append(completion_event)

                step_id = next_thinking_step_id()
                title = format_step_title("Uppdaterar intern planerare")
                items: list[str] = []
                if kind == "intent":
                    title = format_step_title("Tolkar avsikt")
                    intent_id = str(payload.get("intent_id") or "").strip()
                    graph_complexity = str(
                        payload.get("graph_complexity") or ""
                    ).strip()
                    reason = str(payload.get("reason") or "").strip()
                    confidence = payload.get("confidence")
                    if intent_id:
                        items.append(f"Avsikt: {intent_id}")
                    if graph_complexity:
                        items.append(f"Komplexitet: {graph_complexity}")
                    if isinstance(confidence, (int, float)):
                        items.append(f"Konfidens: {float(confidence):.2f}")
                    if reason:
                        items.append(f"Orsak: {reason[:180]}")
                elif kind == "agent_resolver":
                    title = format_step_title("Väljer agenter")
                    selected_agents = payload.get("selected_agents")
                    if isinstance(selected_agents, list):
                        clean_agents = [
                            str(agent).strip()
                            for agent in selected_agents
                            if str(agent).strip()
                        ]
                        if clean_agents:
                            items.append(f"Agenter: {', '.join(clean_agents[:4])}")
                    reason = str(payload.get("reason") or "").strip()
                    if reason:
                        items.append(f"Orsak: {reason[:180]}")
                elif kind == "planner":
                    title = format_step_title("Bygger plan")
                    steps = payload.get("steps")
                    if isinstance(steps, list):
                        for step in steps[:4]:
                            if not isinstance(step, dict):
                                continue
                            content = str(step.get("content") or "").strip()
                            if content:
                                items.append(content[:180])
                    reason = str(payload.get("reason") or "").strip()
                    if reason:
                        items.append(f"Planmotiv: {reason[:180]}")
                elif kind == "critic":
                    title = format_step_title(
                        "Granskar resultat och nästa steg"
                    )
                    decision = str(payload.get("decision") or "").strip()
                    if not decision:
                        decision = str(payload.get("status") or "").strip()
                    reason = str(payload.get("reason") or "").strip()
                    if decision:
                        items.append(f"Beslut: {decision}")
                    if reason:
                        items.append(f"Orsak: {reason[:180]}")
                elif kind == "execution_router":
                    title = format_step_title("Planerar exekveringsstrategi")
                    strategy = str(payload.get("execution_strategy") or "").strip()
                    reason = str(
                        payload.get("execution_reason") or payload.get("reason") or ""
                    ).strip()
                    if strategy:
                        items.append(f"Strategi: {strategy}")
                    if reason:
                        items.append(f"Orsak: {reason[:180]}")
                elif kind == "speculative":
                    title = format_step_title("Kör spekulativa verktyg")
                    candidates = payload.get("speculative_candidates")
                    if isinstance(candidates, list):
                        candidate_ids = [
                            str((item or {}).get("tool_id") or "").strip()
                            for item in candidates
                            if isinstance(item, dict)
                        ]
                        candidate_ids = [item for item in candidate_ids if item]
                        if candidate_ids:
                            items.append(f"Kandidater: {', '.join(candidate_ids[:4])}")
                    reused = payload.get("speculative_reused_tools")
                    if isinstance(reused, list) and reused:
                        items.append(f"Återanvända: {len(reused)}")
                    remaining = payload.get("speculative_remaining_tools")
                    if isinstance(remaining, list) and remaining:
                        items.append(f"Kvar att köra: {len(remaining)}")
                elif kind == "response_layer_router":
                    title = format_step_title("Väljer presentationsläge")
                    chosen = str(payload.get("chosen_layer") or "").strip()
                    reason = str(payload.get("reason") or "").strip()
                    data_chars = str(
                        payload.get("data_characteristics") or ""
                    ).strip()
                    layer_labels = {
                        "kunskap": "Kunskap",
                        "analys": "Analys",
                        "syntes": "Syntes",
                        "visualisering": "Visualisering",
                    }
                    if chosen:
                        items.append(
                            f"Valt läge: {layer_labels.get(chosen, chosen)}"
                        )
                    if data_chars:
                        items.append(f"Data: {data_chars[:180]}")
                    if reason:
                        items.append(f"Motivering: {reason[:180]}")
                elif kind == "progressive_synthesizer":
                    title = format_step_title("Förbereder svarsutkast")
                    drafts = payload.get("synthesis_drafts")
                    if isinstance(drafts, list) and drafts:
                        first_draft = drafts[0] if isinstance(drafts[0], dict) else {}
                        confidence = first_draft.get("confidence")
                        draft_text = str(first_draft.get("draft") or "").strip()
                        if isinstance(confidence, (int, float)):
                            items.append(f"Utkastskonfidens: {float(confidence):.2f}")
                        if draft_text:
                            items.append(draft_text[:180])
                if source_chain and _is_any_pipeline_chain_name(source_chain):
                    items.insert(0, f"Nod: {source_chain}")
                events.append(
                    streaming_service.format_thinking_step(
                        step_id=step_id,
                        title=title,
                        status="in_progress",
                        items=items or None,
                    )
                )
                events.append(
                    streaming_service.format_thinking_step(
                        step_id=step_id,
                        title=title,
                        status="completed",
                        items=items or None,
                    )
                )
                completed_step_ids.add(step_id)
            return events

        def emit_pipeline_steps_from_text(
            text: str,
            *,
            source_chain: str | None = None,
        ) -> list[str]:
            # Strip <think>…</think> blocks and bare tags to prevent
            # reasoning content from leaking into visible step items.
            stripped = _THINK_BLOCK_RE.sub("", text) if text else text
            stripped = _THINK_TAG_RE.sub("", stripped) if stripped else stripped
            payloads = [
                payload
                for payload in _extract_json_objects_from_text(stripped, max_objects=6)
                if _pipeline_payload_kind(payload)
            ]
            return emit_pipeline_steps_from_payloads(
                payloads, source_chain=source_chain
            )

        def emit_synthesis_draft_events(output: Any) -> list[str]:
            events: list[str] = []
            for draft_payload in _extract_synthesis_drafts_from_event_output(output):
                signature = json.dumps(
                    draft_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                )
                if signature in emitted_synthesis_draft_signatures:
                    continue
                emitted_synthesis_draft_signatures.add(signature)
                events.append(
                    streaming_service.format_data("synthesis-draft", draft_payload)
                )
            return events

        route_step_id = next_thinking_step_id()
        route_items = [f"Rutt: {route.value}"]
        route_source = str(route_decision.get("source") or "").strip()
        route_confidence = route_decision.get("confidence")
        route_reason = str(route_decision.get("reason") or "").strip()
        if route_source:
            route_items.append(f"Källa: {route_source}")
        if isinstance(route_confidence, (int, float)):
            route_items.append(f"Konfidens: {float(route_confidence):.2f}")
        if route_reason:
            route_items.append(f"Orsak: {route_reason}")
        yield streaming_service.format_thinking_step(
            step_id=route_step_id,
            title=format_step_title("Dirigerar förfrågan"),
            status="in_progress",
            items=route_items,
        )
        yield streaming_service.format_thinking_step(
            step_id=route_step_id,
            title=format_step_title("Dirigerar förfrågan"),
            status="completed",
            items=route_items,
        )
        completed_step_ids.add(route_step_id)

        # Initial thinking step - analyzing the request
        analyze_step_id = next_thinking_step_id()
        last_active_step_id = analyze_step_id

        # Determine step title and action verb based on context
        if attachments and (mentioned_documents or mentioned_surfsense_docs):
            last_active_step_title = format_step_title("Analyserar ditt innehåll")
            action_verb = "Läser"
        elif attachments:
            last_active_step_title = format_step_title("Läser ditt innehåll")
            action_verb = "Läser"
        elif mentioned_documents or mentioned_surfsense_docs:
            last_active_step_title = format_step_title("Analyserar refererat innehåll")
            action_verb = "Analyserar"
        else:
            last_active_step_title = format_step_title("Analyserar din fråga")
            action_verb = "Bearbetar"

        # Build the message with inline context about attachments/documents
        processing_parts = []

        # Add the user query
        query_text = user_query[:80] + ("..." if len(user_query) > 80 else "")
        processing_parts.append(query_text)

        # Add file attachment names inline
        if attachments:
            attachment_names = []
            for attachment in attachments:
                name = attachment.name
                if len(name) > 30:
                    name = name[:27] + "..."
                attachment_names.append(name)
            if len(attachment_names) == 1:
                processing_parts.append(f"[{attachment_names[0]}]")
            else:
                processing_parts.append(f"[{len(attachment_names)} filer]")

        # Add mentioned document names inline
        if mentioned_documents:
            doc_names = []
            for doc in mentioned_documents:
                title = doc.title
                if len(title) > 30:
                    title = title[:27] + "..."
                doc_names.append(title)
            if len(doc_names) == 1:
                processing_parts.append(f"[{doc_names[0]}]")
            else:
                processing_parts.append(f"[{len(doc_names)} dokument]")

        # Add mentioned SurfSense docs inline
        if mentioned_surfsense_docs:
            doc_names = []
            for doc in mentioned_surfsense_docs:
                title = doc.title
                if len(title) > 30:
                    title = title[:27] + "..."
                doc_names.append(title)
            if len(doc_names) == 1:
                processing_parts.append(f"[{doc_names[0]}]")
            else:
                processing_parts.append(f"[{len(doc_names)} dokument]")

        last_active_step_items = [f"{action_verb}: {' '.join(processing_parts)}"]

        yield streaming_service.format_thinking_step(
            step_id=analyze_step_id,
            title=last_active_step_title,
            status="in_progress",
            items=last_active_step_items,
        )

        def trace_parent_id(event: dict) -> str | None:
            parents = event.get("parent_ids") or []
            if parents:
                return str(parents[-1])
            return None

        def filter_critic_json(text: str) -> str:
            nonlocal suppress_critic, critic_buffer
            if not text:
                return text
            output = ""
            remaining = text
            while remaining:
                if not suppress_critic:
                    match = _CRITIC_JSON_START_RE.search(remaining)
                    if not match:
                        output += remaining
                        break
                    output += remaining[: match.start()]
                    remaining = remaining[match.start() :]
                    suppress_critic = True
                    critic_buffer = ""
                if suppress_critic:
                    end_idx = remaining.find("}")
                    if end_idx == -1:
                        critic_buffer += remaining
                        remaining = ""
                    else:
                        remaining = remaining[end_idx + 1 :]
                        suppress_critic = False
                        critic_buffer = ""
            return output

        def filter_repeated_output(text: str) -> str:
            nonlocal repeat_buffer, suppress_repeat, repeat_candidate, accumulated_text
            if not text or suppress_repeat:
                return ""
            if len(accumulated_text) < 200:
                return text
            stripped_existing = accumulated_text.lstrip()
            if not stripped_existing:
                return text
            normalized_existing = _REPEAT_BULLET_PREFIX_RE.sub(
                "", stripped_existing
            ).lstrip()
            if not repeat_candidate:
                normalized_incoming = _REPEAT_BULLET_PREFIX_RE.sub("", text).lstrip()
                existing_probe = normalized_existing[:10]
                incoming_probe = normalized_incoming[:10]
                if (
                    existing_probe
                    and incoming_probe
                    and (
                        normalized_incoming.startswith(existing_probe)
                        or normalized_existing.startswith(incoming_probe)
                    )
                ):
                    repeat_candidate = True
                else:
                    return text
            repeat_buffer += text
            if len(repeat_buffer) < 60:
                return ""
            normalized_repeat = _REPEAT_BULLET_PREFIX_RE.sub(
                "", repeat_buffer[:60]
            ).lstrip()
            if normalized_repeat and normalized_existing.startswith(normalized_repeat):
                suppress_repeat = True
                repeat_buffer = ""
                return ""
            repeat_candidate = False
            output = repeat_buffer
            repeat_buffer = ""
            return output

        # Stream the agent response with thread config for memory
        async for event in agent.astream_events(
            input_state, config=config, version="v2"
        ):
            event_type = event.get("event", "")
            run_id = str(event.get("run_id") or "")
            trace_parent = trace_parent_id(event)
            if event_type == "on_chain_start" and run_id:
                chain_name_by_run_id.setdefault(
                    run_id, str(event.get("name") or "chain")
                )
            elif (
                event_type in ("on_chat_model_start", "on_llm_start")
                and run_id
                and run_id not in model_parent_chain_by_run_id
            ):
                parent_ids = [
                    str(value)
                    for value in (event.get("parent_ids") or [])
                    if str(value)
                ]
                # Walk ALL parents: track both the immediate non-generic
                # parent (for display/headers) and the pipeline ancestor
                # (for classification as internal vs output).
                immediate_parent = ""
                pipeline_parent = ""
                for parent_id in reversed(parent_ids):
                    candidate_chain_name = chain_name_by_run_id.get(parent_id)
                    if not candidate_chain_name:
                        continue
                    normalized = str(candidate_chain_name).strip().lower()
                    if normalized in _GENERIC_CHAIN_NAMES:
                        continue
                    cname = str(candidate_chain_name)
                    # Remember the closest non-generic chain
                    if not immediate_parent:
                        immediate_parent = cname
                    # If this ancestor is a known pipeline node, use it
                    if _is_internal_pipeline_chain_name(cname) or _is_any_pipeline_chain_name(cname):
                        pipeline_parent = cname
                        break

                # Use pipeline parent for classification, fall back to immediate
                parent_chain_name = pipeline_parent or immediate_parent

                # Build a display key that tracks transitions at the
                # agent level (not just pipeline node), so headers also
                # appear when switching between domain agents inside the
                # same executor loop.
                display_key = immediate_parent or parent_chain_name

                if _is_internal_pipeline_chain_name(parent_chain_name):
                    model_parent_chain_by_run_id[run_id] = parent_chain_name
                    internal_model_buffers.setdefault(run_id, "")
                    # Create per-node think filter so reasoning streams
                    # in real-time into the FadeLayer think-box.
                    internal_node_think_filters[run_id] = _ThinkStreamFilter(
                        assume_think=_think_filter._assume_think,
                    )
                    # Emit a node-transition header immediately so the
                    # frontend shows which pipeline phase is now active.
                    if display_key != last_reasoning_pipeline_node:
                        last_reasoning_pipeline_node = display_key
                        # If the immediate parent differs from the pipeline
                        # node, it's a domain agent — show its name.
                        if immediate_parent and immediate_parent != parent_chain_name:
                            node_title = _pipeline_node_title(parent_chain_name)
                            agent_label = immediate_parent.replace("_", " ").title()
                            header = f"\n--- {agent_label} ({node_title}) ---\n"
                        else:
                            node_title = _pipeline_node_title(parent_chain_name)
                            header = f"\n--- {node_title} ---\n"
                        if active_reasoning_id is None:
                            active_reasoning_id = (
                                streaming_service.generate_reasoning_id()
                            )
                            yield streaming_service.format_reasoning_start(
                                active_reasoning_id
                            )
                        yield streaming_service.format_reasoning_delta(
                            active_reasoning_id, header
                        )
                elif _is_any_pipeline_chain_name(parent_chain_name):
                    # Output pipeline node (synthesizer / response_layer):
                    # not registered as internal, but emit a header so the
                    # user sees which phase is producing the final response.
                    #
                    # When the response_layer output node starts AFTER the
                    # synthesizer has already streamed text, clear the
                    # existing text so the formatted version replaces it
                    # rather than being appended.
                    pcn_lower = str(parent_chain_name).strip().lower()
                    if (
                        "response_layer" in pcn_lower
                        and "response_layer_router" not in pcn_lower
                        and current_text_id is not None
                    ):
                        yield streaming_service.format_text_end(current_text_id)
                        current_text_id = None
                        yield streaming_service.format_text_clear()
                        accumulated_text = ""
                    if display_key != last_reasoning_pipeline_node:
                        last_reasoning_pipeline_node = display_key
                        node_title = _pipeline_node_title(parent_chain_name)
                        header = f"\n--- {node_title} ---\n"
                        if active_reasoning_id is None:
                            active_reasoning_id = (
                                streaming_service.generate_reasoning_id()
                            )
                            yield streaming_service.format_reasoning_start(
                                active_reasoning_id
                            )
                        yield streaming_service.format_reasoning_delta(
                            active_reasoning_id, header
                        )
                    if _think_filter._assume_think:
                        flush_r, flush_t = _think_filter.reset_think_mode()
                        if flush_r:
                            if active_reasoning_id is None:
                                active_reasoning_id = (
                                    streaming_service.generate_reasoning_id()
                                )
                                yield streaming_service.format_reasoning_start(
                                    active_reasoning_id
                                )
                            yield streaming_service.format_reasoning_delta(
                                active_reasoning_id, flush_r
                            )
                        # Flushed text from a PREVIOUS model goes to
                        # reasoning, NOT text-delta, to prevent leaks.
                        if flush_t:
                            if active_reasoning_id is None:
                                active_reasoning_id = (
                                    streaming_service.generate_reasoning_id()
                                )
                                yield streaming_service.format_reasoning_start(
                                    active_reasoning_id
                                )
                            yield streaming_service.format_reasoning_delta(
                                active_reasoning_id, flush_t
                            )
                        # The response_layer formatting LLM produces the
                        # final user-facing text.  reset_think_mode() puts
                        # the filter back in think mode, which would cause
                        # ALL its output to be classified as reasoning
                        # instead of text-delta.  Force out of think mode
                        # for response_layer so text streams correctly.
                        # (The synthesizer keeps assume_think behaviour
                        # for Qwen3-style models that pre-fill <think>.)
                        if (
                            "response_layer" in pcn_lower
                            and "response_layer_router" not in pcn_lower
                        ):
                            _think_filter._in_think = False
                else:
                    # Unknown / unclassified model: treat as INTERNAL to
                    # prevent any internal reasoning from leaking into the
                    # visible response.  Only output pipeline nodes
                    # (synthesizer, response_layer) should emit text-delta.
                    model_parent_chain_by_run_id[run_id] = parent_chain_name or "__unclassified__"
                    internal_model_buffers.setdefault(run_id, "")
                    internal_node_think_filters[run_id] = _ThinkStreamFilter(
                        assume_think=_think_filter._assume_think,
                    )
                    if _think_filter._assume_think:
                        flush_r, flush_t = _think_filter.reset_think_mode()
                        if flush_r or flush_t:
                            if active_reasoning_id is None:
                                active_reasoning_id = (
                                    streaming_service.generate_reasoning_id()
                                )
                                yield streaming_service.format_reasoning_start(
                                    active_reasoning_id
                                )
                            if flush_r:
                                yield streaming_service.format_reasoning_delta(
                                    active_reasoning_id, flush_r
                                )
                            if flush_t:
                                yield streaming_service.format_reasoning_delta(
                                    active_reasoning_id, flush_t
                                )

            if trace_recorder:
                if event_type == "on_chain_start":
                    chain_name = event.get("name") or "chain"
                    if run_id:
                        chain_name_by_run_id[run_id] = str(chain_name)

                    chain_input = event.get("data", {}).get("input")
                    chain_meta = {
                        "tags": event.get("tags") or [],
                        "metadata": event.get("metadata") or {},
                    }
                    trace_event = await trace_recorder.start_span(
                        span_id=run_id or f"chain-{uuid.uuid4().hex[:8]}",
                        name=str(chain_name),
                        kind="chain",
                        parent_id=trace_parent,
                        input_data=chain_input,
                        meta=chain_meta,
                    )
                    if trace_event:
                        yield trace_event
                elif event_type == "on_chain_end":
                    chain_output = event.get("data", {}).get("output")
                    for synthesis_event in emit_synthesis_draft_events(chain_output):
                        yield synthesis_event
                    trace_event = await trace_recorder.end_span(
                        span_id=run_id,
                        output_data=chain_output,
                        status="completed",
                    )
                    if trace_event:
                        yield trace_event

                    # Extract and stream tool calls from chain output — only
                    # needed for compare-mode chains where tool calls don't go
                    # through the normal on_tool_start/on_tool_end pipeline.
                    # Skipping non-compare chains prevents duplicate emission
                    # of tool results that are already handled by on_tool_end.
                    _chain_name_for_extract = chain_name_by_run_id.get(run_id, "")
                    if "compare" in str(_chain_name_for_extract).lower():
                        tool_call_events = _extract_and_stream_tool_calls(
                            chain_output, streaming_service, streamed_tool_call_ids
                        )
                        for tool_event in tool_call_events:
                            yield tool_event

                    candidate_text = _extract_assistant_text_from_event_output(
                        chain_output
                    )
                    chain_name = chain_name_by_run_id.get(run_id) or str(
                        event.get("name") or ""
                    )
                    if candidate_text:
                        source_chain = (
                            chain_name
                            if _is_any_pipeline_chain_name(chain_name)
                            else None
                        )
                        for step_event in emit_pipeline_steps_from_text(
                            candidate_text,
                            source_chain=source_chain,
                        ):
                            yield step_event
                        cleaned_candidate = _clean_assistant_output_text(candidate_text)
                        if cleaned_candidate:
                            fallback_assistant_text = cleaned_candidate
                elif event_type == "on_chain_error":
                    trace_event = await trace_recorder.end_span(
                        span_id=run_id,
                        output_data=event.get("data"),
                        status="error",
                    )
                    if trace_event:
                        yield trace_event
                    if run_id:
                        chain_name_by_run_id.pop(run_id, None)
                elif event_type in ("on_chat_model_start", "on_llm_start"):
                    model_data = event.get("data", {})
                    parent_chain_name = ""
                    parent_ids = [
                        str(value)
                        for value in (event.get("parent_ids") or [])
                        if str(value)
                    ]
                    # Walk ALL parents to find the nearest pipeline node.
                    for parent_id in reversed(parent_ids):
                        candidate_chain_name = chain_name_by_run_id.get(parent_id)
                        if not candidate_chain_name:
                            continue
                        normalized = str(candidate_chain_name).strip().lower()
                        if normalized in _GENERIC_CHAIN_NAMES:
                            continue
                        if not parent_chain_name:
                            parent_chain_name = str(candidate_chain_name)
                        if _is_internal_pipeline_chain_name(str(candidate_chain_name)):
                            parent_chain_name = str(candidate_chain_name)
                            break
                        if _is_any_pipeline_chain_name(str(candidate_chain_name)):
                            parent_chain_name = str(candidate_chain_name)
                            break
                    if run_id and run_id not in model_parent_chain_by_run_id:
                        # If the primary handler already classified this model,
                        # don't overwrite.  Otherwise, treat as internal unless
                        # it's an explicit output pipeline node.
                        is_output = (
                            _is_any_pipeline_chain_name(parent_chain_name)
                            and not _is_internal_pipeline_chain_name(parent_chain_name)
                        )
                        if not is_output:
                            model_parent_chain_by_run_id[run_id] = parent_chain_name or "__unclassified__"
                            internal_model_buffers.setdefault(run_id, "")
                            internal_node_think_filters[run_id] = _ThinkStreamFilter(
                                assume_think=_think_filter._assume_think,
                            )
                    model_input = (
                        model_data.get("input")
                        or model_data.get("messages")
                        or model_data.get("prompt")
                    )
                    model_name = event.get("name") or model_data.get("model") or "model"
                    model_meta = {
                        "model": model_data.get("model"),
                        "provider": model_data.get("provider"),
                        "tags": event.get("tags") or [],
                        "metadata": event.get("metadata") or {},
                    }
                    trace_event = await trace_recorder.start_span(
                        span_id=run_id or f"model-{uuid.uuid4().hex[:8]}",
                        name=str(model_name),
                        kind="model",
                        parent_id=trace_parent,
                        input_data=model_input,
                        meta=model_meta,
                    )
                    if trace_event:
                        yield trace_event
                elif event_type in ("on_chat_model_end", "on_llm_end"):
                    model_output = event.get("data", {}).get("output")
                    trace_event = await trace_recorder.end_span(
                        span_id=run_id,
                        output_data=model_output,
                        status="completed",
                    )
                    if trace_event:
                        yield trace_event
                    candidate_text = _extract_assistant_text_from_event_output(
                        model_output
                    )
                    internal_chain_name = model_parent_chain_by_run_id.pop(run_id, "")
                    internal_buffer = internal_model_buffers.pop(run_id, "")
                    # Flush per-node think filter and emit remaining reasoning
                    # into the global rolling think-box (reasoning-delta).
                    node_filter = internal_node_think_filters.pop(run_id, None)
                    if node_filter:
                        flush_reasoning, flush_node_text = node_filter.flush()
                        # Node text also goes to reasoning (never text-delta)
                        flush_reasoning = (flush_reasoning or "") + (flush_node_text or "")
                        if flush_reasoning:
                            # Inject node header if this is a new pipeline node
                            if internal_chain_name and internal_chain_name != last_reasoning_pipeline_node:
                                last_reasoning_pipeline_node = internal_chain_name
                                node_title = _pipeline_node_title(internal_chain_name)
                                header = f"\n--- {node_title} ---\n"
                                if active_reasoning_id is None:
                                    active_reasoning_id = streaming_service.generate_reasoning_id()
                                    yield streaming_service.format_reasoning_start(active_reasoning_id)
                                yield streaming_service.format_reasoning_delta(active_reasoning_id, header)
                            if active_reasoning_id is None:
                                active_reasoning_id = streaming_service.generate_reasoning_id()
                                yield streaming_service.format_reasoning_start(active_reasoning_id)
                            yield streaming_service.format_reasoning_delta(active_reasoning_id, flush_reasoning)
                    if internal_chain_name:
                        internal_text = internal_buffer or candidate_text
                        for step_event in emit_pipeline_steps_from_text(
                            internal_text,
                            source_chain=internal_chain_name,
                        ):
                            yield step_event
                    elif candidate_text:
                        for step_event in emit_pipeline_steps_from_text(candidate_text):
                            yield step_event
                        # Do NOT store as fallback text — this came from an
                        # unclassified model, not an output pipeline node.

            # Handle chat model stream events (text streaming)
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    # Handle native reasoning_content (DeepSeek-R1 / models with separate field)
                    native_reasoning: str | None = None
                    if hasattr(chunk, "additional_kwargs"):
                        native_reasoning = chunk.additional_kwargs.get(
                            "reasoning_content"
                        )
                    if native_reasoning and isinstance(native_reasoning, str):
                        if run_id and run_id in model_parent_chain_by_run_id:
                            # Pipeline node: emit as reasoning-delta in the
                            # global rolling think-box.
                            parent_chain = model_parent_chain_by_run_id.get(run_id, "")
                            if parent_chain != last_reasoning_pipeline_node:
                                last_reasoning_pipeline_node = parent_chain
                                node_title = _pipeline_node_title(parent_chain)
                                header = f"\n--- {node_title} ---\n"
                                if active_reasoning_id is None:
                                    active_reasoning_id = streaming_service.generate_reasoning_id()
                                    yield streaming_service.format_reasoning_start(active_reasoning_id)
                                yield streaming_service.format_reasoning_delta(active_reasoning_id, header)
                            if active_reasoning_id is None:
                                active_reasoning_id = streaming_service.generate_reasoning_id()
                                yield streaming_service.format_reasoning_start(active_reasoning_id)
                            yield streaming_service.format_reasoning_delta(
                                active_reasoning_id, native_reasoning
                            )
                        else:
                            # Executor node: emit as global reasoning-delta
                            if active_reasoning_id is None:
                                active_reasoning_id = (
                                    streaming_service.generate_reasoning_id()
                                )
                                yield streaming_service.format_reasoning_start(
                                    active_reasoning_id
                                )
                            yield streaming_service.format_reasoning_delta(
                                active_reasoning_id, native_reasoning
                            )

                    content = chunk.content
                    if content and isinstance(content, str):
                        if run_id and run_id in model_parent_chain_by_run_id:
                            internal_model_buffers[run_id] = (
                                internal_model_buffers.get(run_id, "") + content
                            )
                            if trace_recorder:
                                trace_update = await trace_recorder.append_span_output(
                                    span_id=run_id, output_delta=content
                                )
                                if trace_update:
                                    yield trace_update
                            # --- Node-by-node think-box: stream per-node reasoning
                            # into the global rolling think-box (reasoning-delta). ---
                            node_filter = internal_node_think_filters.get(run_id)
                            if node_filter:
                                node_reasoning, _node_text = node_filter.feed(content)
                                if node_reasoning:
                                    parent_chain = model_parent_chain_by_run_id.get(
                                        run_id, ""
                                    )
                                    # Inject node header when the pipeline node changes
                                    if parent_chain != last_reasoning_pipeline_node:
                                        last_reasoning_pipeline_node = parent_chain
                                        node_title = _pipeline_node_title(parent_chain)
                                        header = f"\n--- {node_title} ---\n"
                                        if active_reasoning_id is None:
                                            active_reasoning_id = streaming_service.generate_reasoning_id()
                                            yield streaming_service.format_reasoning_start(active_reasoning_id)
                                        yield streaming_service.format_reasoning_delta(
                                            active_reasoning_id, header
                                        )
                                    if active_reasoning_id is None:
                                        active_reasoning_id = streaming_service.generate_reasoning_id()
                                        yield streaming_service.format_reasoning_start(active_reasoning_id)
                                    yield streaming_service.format_reasoning_delta(
                                        active_reasoning_id, node_reasoning
                                    )
                            continue
                        # Split <think>…</think> tags into reasoning vs. main text
                        reasoning_chunk, content = _think_filter.feed(content)

                        # Handle template-prefilled <think> detection:
                        # When </think> appears before any <think>, text that was
                        # previously streamed as text-delta was actually reasoning.
                        if (
                            _think_filter.late_close_detected
                            and not _late_close_handled
                        ):
                            _late_close_handled = True
                            retro_text = _think_filter.drain_retroactive_reasoning()
                            if retro_text or reasoning_chunk:
                                if active_reasoning_id is None:
                                    active_reasoning_id = (
                                        streaming_service.generate_reasoning_id()
                                    )
                                    yield streaming_service.format_reasoning_start(
                                        active_reasoning_id
                                    )
                                if retro_text:
                                    yield streaming_service.format_reasoning_delta(
                                        active_reasoning_id, retro_text
                                    )
                                if reasoning_chunk:
                                    yield streaming_service.format_reasoning_delta(
                                        active_reasoning_id, reasoning_chunk
                                    )
                                yield streaming_service.format_reasoning_end(
                                    active_reasoning_id
                                )
                                active_reasoning_id = None
                                reasoning_chunk = ""  # already handled
                            if retro_text:
                                # Tell the frontend to discard text it already rendered
                                yield streaming_service.format_text_clear()
                                # Reset the text block so subsequent text starts fresh
                                if current_text_id is not None:
                                    yield streaming_service.format_text_end(
                                        current_text_id
                                    )
                                    current_text_id = None
                                accumulated_text = ""

                        elif reasoning_chunk:
                            if active_reasoning_id is None:
                                active_reasoning_id = (
                                    streaming_service.generate_reasoning_id()
                                )
                                yield streaming_service.format_reasoning_start(
                                    active_reasoning_id
                                )
                            yield streaming_service.format_reasoning_delta(
                                active_reasoning_id, reasoning_chunk
                            )
                        # Close reasoning block the moment main text starts arriving
                        if content and active_reasoning_id is not None:
                            yield streaming_service.format_reasoning_end(
                                active_reasoning_id
                            )
                            active_reasoning_id = None
                        if not content:
                            continue
                        content = filter_critic_json(content)
                        # Strip stray XML tags that models sometimes emit
                        # (e.g. </final_planner>, <tool_call>, etc.)
                        content = _STRAY_XML_TAG_RE.sub("", content)
                        if stream_pipeline_prefix_buffer:
                            content = stream_pipeline_prefix_buffer + content
                            stream_pipeline_prefix_buffer = ""
                        content, inline_pipeline_payloads = (
                            _strip_inline_pipeline_payloads(content)
                        )
                        if inline_pipeline_payloads:
                            for step_event in emit_pipeline_steps_from_payloads(
                                inline_pipeline_payloads
                            ):
                                yield step_event
                        content, stream_pipeline_prefix_buffer = (
                            _split_trailing_pipeline_prefix(content)
                        )
                        content = filter_repeated_output(content)
                        if not content:
                            continue
                        # Start a new text block if needed
                        if current_text_id is None:
                            # Complete any previous step
                            completion_event = complete_current_step()
                            if completion_event:
                                yield completion_event

                            if just_finished_tool:
                                # Clear the active step tracking - text flows without a dedicated step
                                last_active_step_id = None
                                last_active_step_title = ""
                                last_active_step_items = []
                                just_finished_tool = False

                            current_text_id = streaming_service.generate_text_id()
                            yield streaming_service.format_text_start(current_text_id)

                        # Stream the text delta
                        yield streaming_service.format_text_delta(
                            current_text_id, content
                        )
                        accumulated_text += content
                        if trace_recorder:
                            trace_update = await trace_recorder.append_span_output(
                                span_id=run_id, output_delta=content
                            )
                            if trace_update:
                                yield trace_update

            # Handle tool calls
            elif event_type == "on_tool_start":
                tool_name = event.get("name", "unknown_tool")
                run_id = event.get("run_id", "")
                tool_input = event.get("data", {}).get("input", {})
                if trace_recorder:
                    trace_event = await trace_recorder.start_span(
                        span_id=str(run_id) or f"tool-{uuid.uuid4().hex[:8]}",
                        name=str(tool_name),
                        kind="tool",
                        parent_id=trace_parent,
                        input_data=tool_input,
                        meta={"tool": tool_name},
                    )
                    if trace_event:
                        yield trace_event

                # End current text block if any
                if current_text_id is not None:
                    yield streaming_service.format_text_end(current_text_id)
                    current_text_id = None

                # End any active reasoning block
                if active_reasoning_id is not None:
                    yield streaming_service.format_reasoning_end(active_reasoning_id)
                    active_reasoning_id = None

                # Complete any previous step EXCEPT "Synthesizing response"
                # (we want to reuse the Synthesizing step after tools complete)
                if last_active_step_title != format_step_title("Sammanställer svar"):
                    completion_event = complete_current_step()
                    if completion_event:
                        yield completion_event

                # Reset the just_finished_tool flag since we're starting a new tool
                just_finished_tool = False

                # Create thinking step for the tool call and store it for later update
                tool_step_id = next_thinking_step_id()
                if tool_name == "write_todos":
                    if write_todos_step_id is None:
                        write_todos_step_id = tool_step_id
                    else:
                        tool_step_id = write_todos_step_id
                tool_step_ids[run_id] = tool_step_id
                last_active_step_id = tool_step_id
                if tool_name == "search_knowledge_base":
                    query = (
                        tool_input.get("query", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)
                    )
                    last_active_step_title = format_step_title(
                        "Söker i kunskapsbasen"
                    )
                    last_active_step_items = [
                        "API: search_knowledge_base",
                        f"Fråga: {query[:100]}{'...' if len(query) > 100 else ''}",
                    ]
                    # Show additional parameters (e.g. filters, limit)
                    if isinstance(tool_input, dict):
                        for k, v in tool_input.items():
                            if k != "query" and v is not None and v != "":
                                last_active_step_items.append(
                                    f"{k}: {_summarize_text(v, 80)}"
                                )
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "link_preview":
                    url = (
                        tool_input.get("url", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)
                    )
                    last_active_step_title = format_step_title("Hämtar länkförhandsgranskning")
                    last_active_step_items = [
                        f"URL: {url[:80]}{'...' if len(url) > 80 else ''}"
                    ]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "display_image":
                    src = (
                        tool_input.get("src", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)
                    )
                    title = (
                        tool_input.get("title", "")
                        if isinstance(tool_input, dict)
                        else ""
                    )
                    last_active_step_title = format_step_title("Analyserar bilden")
                    last_active_step_items = [
                        f"Analyserar: {title[:50] if title else src[:50]}{'...' if len(title or src) > 50 else ''}"
                    ]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "scrape_webpage":
                    url = (
                        tool_input.get("url", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)
                    )
                    last_active_step_title = format_step_title("Hämtar webbsida")
                    last_active_step_items = [
                        f"URL: {url[:80]}{'...' if len(url) > 80 else ''}"
                    ]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name.startswith("smhi_"):
                    location = ""
                    if isinstance(tool_input, dict):
                        location = tool_input.get("location") or ""
                        lat = tool_input.get("lat")
                        lon = tool_input.get("lon")
                        if not location and lat is not None and lon is not None:
                            location = f"{lat}, {lon}"
                    else:
                        location = str(tool_input)
                    last_active_step_title = format_step_title("Hämtar SMHI-data")
                    last_active_step_items = [
                        f"API: {tool_name}",
                        f"Plats: {location[:80]}{'...' if len(location) > 80 else ''}",
                    ]
                    # Show additional parameters the model passed
                    if isinstance(tool_input, dict):
                        for k, v in tool_input.items():
                            if k not in ("location", "lat", "lon") and v is not None and v != "":
                                last_active_step_items.append(
                                    f"{k}: {_summarize_text(v, 80)}"
                                )
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "trafiklab_route":
                    origin = ""
                    destination = ""
                    time_value = ""
                    if isinstance(tool_input, dict):
                        origin = (
                            tool_input.get("origin")
                            or tool_input.get("origin_id")
                            or ""
                        )
                        destination = (
                            tool_input.get("destination")
                            or tool_input.get("destination_id")
                            or ""
                        )
                        time_value = tool_input.get("time") or ""
                    else:
                        origin = str(tool_input)
                    last_active_step_title = format_step_title(
                        "Planerar resväg (Trafiklab)"
                    )
                    route_text = f"{origin} -> {destination}".strip()
                    last_active_step_items = [
                        "API: trafiklab_route",
                        f"Resväg: {route_text[:80]}{'...' if len(route_text) > 80 else ''}",
                    ]
                    if time_value:
                        last_active_step_items.append(
                            f"Tid: {time_value[:40]}{'...' if len(time_value) > 40 else ''}"
                        )
                    # Show additional parameters
                    if isinstance(tool_input, dict):
                        for k, v in tool_input.items():
                            if k not in ("origin", "origin_id", "destination", "destination_id", "time") and v is not None and v != "":
                                last_active_step_items.append(
                                    f"{k}: {_summarize_text(v, 80)}"
                                )
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "libris_search":
                    query = ""
                    record_id = ""
                    if isinstance(tool_input, dict):
                        query = tool_input.get("query") or ""
                        record_id = tool_input.get("record_id") or ""
                    else:
                        query = str(tool_input)
                    last_active_step_title = format_step_title(
                        "Söker i Libris-katalogen"
                    )
                    item_label = (
                        f"Post: {record_id}" if record_id else f"Fråga: {query}"
                    )
                    last_active_step_items = [
                        f"{item_label[:100]}{'...' if len(item_label) > 100 else ''}"
                    ]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "jobad_links_search":
                    query = ""
                    location = ""
                    if isinstance(tool_input, dict):
                        query = tool_input.get("query") or ""
                        location = tool_input.get("location") or ""
                    else:
                        query = str(tool_input)
                    last_active_step_title = format_step_title("Söker jobbannonser")
                    details = f"{query} {location}".strip()
                    last_active_step_items = [
                        f"Sökning: {details[:100]}{'...' if len(details) > 100 else ''}"
                    ]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "write_todos":
                    # Track write_todos calls for better messaging
                    write_todos_call_count += 1
                    todos = (
                        tool_input.get("todos", [])
                        if isinstance(tool_input, dict)
                        else []
                    )
                    todo_count = len(todos) if isinstance(todos, list) else 0

                    if write_todos_call_count == 1:
                        # First call - creating the plan
                        last_active_step_title = format_step_title("Skapar plan")
                        last_active_step_items = [f"Definierar {todo_count} uppgifter..."]
                    else:
                        # Subsequent calls - updating the plan
                        in_progress_count = (
                            sum(
                                1
                                for t in todos
                                if isinstance(t, dict)
                                and t.get("status") == "in_progress"
                            )
                            if isinstance(todos, list)
                            else 0
                        )
                        completed_count = (
                            sum(
                                1
                                for t in todos
                                if isinstance(t, dict)
                                and t.get("status") == "completed"
                            )
                            if isinstance(todos, list)
                            else 0
                        )

                        last_active_step_title = format_step_title("Uppdaterar plan")
                        last_active_step_items = (
                            [
                                f"Framsteg: {completed_count}/{todo_count} klara",
                                f"Pågår: {in_progress_count} uppgifter",
                            ]
                            if completed_count > 0
                            else [f"Arbetar med {todo_count} uppgifter"]
                        )

                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "retrieve_agents":
                    query = (
                        tool_input.get("query")
                        if isinstance(tool_input, dict)
                        else tool_input
                    )
                    limit = (
                        tool_input.get("limit")
                        if isinstance(tool_input, dict)
                        else None
                    )
                    last_active_step_title = format_step_title("Väljer agenter")
                    last_active_step_items = [f"Fråga: {_summarize_text(query)}"]
                    if limit:
                        last_active_step_items.append(f"Gräns: {limit}")
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "call_agent":
                    agent_name = ""
                    task = ""
                    if isinstance(tool_input, dict):
                        agent_name = (
                            tool_input.get("agent_name")
                            or tool_input.get("agent")
                            or ""
                        )
                        task = tool_input.get("task") or ""
                    else:
                        task = str(tool_input)
                    title_agent = agent_name or "worker"
                    last_active_step_title = format_step_title(
                        f"Delegerar till {title_agent}"
                    )
                    last_active_step_items = []
                    if agent_name:
                        last_active_step_items.append(f"Agent: {agent_name}")
                    if task:
                        last_active_step_items.append(f"Uppgift: {_summarize_text(task)}")
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "retrieve_tools":
                    query = (
                        tool_input.get("query")
                        if isinstance(tool_input, dict)
                        else tool_input
                    )
                    last_active_step_title = format_step_title("Väljer verktyg")
                    last_active_step_items = [f"Fråga: {_summarize_text(query)}"]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "reflect_on_progress":
                    reflection = (
                        tool_input.get("thoughts")
                        if isinstance(tool_input, dict)
                        else ""
                    )
                    last_active_step_title = format_step_title("Reflekterar över framsteg")
                    last_active_step_items = [
                        _summarize_text(reflection)
                        if reflection
                        else "Granskar resultat och nästa steg"
                    ]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "generate_podcast":
                    podcast_title = (
                        tool_input.get("podcast_title", "SurfSense Podcast")
                        if isinstance(tool_input, dict)
                        else "SurfSense Podcast"
                    )
                    # Get content length for context
                    content_len = len(
                        tool_input.get("source_content", "")
                        if isinstance(tool_input, dict)
                        else ""
                    )
                    last_active_step_title = format_step_title("Genererar podd")
                    last_active_step_items = [
                        f"Titel: {podcast_title}",
                        f"Innehåll: {content_len:,} tecken",
                        "Förbereder ljudgenerering...",
                    ]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                # elif tool_name == "ls":
                #     last_active_step_title = "Exploring files"
                #     last_active_step_items = []
                #     yield streaming_service.format_thinking_step(
                #         step_id=tool_step_id,
                #         title="Exploring files",
                #         status="in_progress",
                #         items=None,
                #     )
                else:
                    last_active_step_title = format_step_title(
                        f"Använder {tool_name.replace('_', ' ')}"
                    )
                    last_active_step_items = _format_tool_input_items(tool_input)
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items if last_active_step_items else None,
                    )

                # Stream tool info
                tool_call_id = (
                    f"call_{run_id[:32]}"
                    if run_id
                    else streaming_service.generate_tool_call_id()
                )
                yield streaming_service.format_tool_input_start(tool_call_id, tool_name)
                safe_tool_input = _coerce_jsonable(tool_input)
                if run_id:
                    tool_inputs[run_id] = (
                        safe_tool_input
                        if isinstance(safe_tool_input, dict)
                        else {"input": safe_tool_input}
                    )
                yield streaming_service.format_tool_input_available(
                    tool_call_id,
                    tool_name,
                    safe_tool_input
                    if isinstance(safe_tool_input, dict)
                    else {"input": safe_tool_input},
                )

            elif event_type == "on_tool_end":
                run_id = event.get("run_id", "")
                tool_name = event.get("name", "unknown_tool")
                raw_output = event.get("data", {}).get("output", "")

                # Handle deepagents' write_todos Command object specially
                if tool_name == "write_todos" and hasattr(raw_output, "update"):
                    # deepagents returns a Command object - extract todos directly
                    tool_output = extract_todos_from_deepagents(raw_output)
                elif hasattr(raw_output, "content"):
                    # It's a ToolMessage object - extract the content
                    content = raw_output.content
                    # If content is a string that looks like JSON, try to parse it
                    if isinstance(content, str):
                        try:
                            tool_output = json.loads(content)
                        except (json.JSONDecodeError, TypeError):
                            tool_output = {"result": content}
                    elif isinstance(content, dict):
                        tool_output = content
                    else:
                        tool_output = {"result": str(content)}
                elif isinstance(raw_output, dict):
                    tool_output = raw_output
                else:
                    tool_output = {
                        "result": str(raw_output) if raw_output else "completed"
                    }

                if trace_recorder:
                    status = "completed"
                    if isinstance(tool_output, dict) and (
                        tool_output.get("status") == "error" or "error" in tool_output
                    ):
                        status = "error"
                    trace_event = await trace_recorder.end_span(
                        span_id=str(run_id),
                        output_data=tool_output,
                        status=status,
                    )
                    if trace_event:
                        yield trace_event

                tool_call_id = f"call_{run_id[:32]}" if run_id else "call_unknown"

                tool_payload_text = serialize_context_payload(tool_output)
                if tool_payload_text:
                    delta_chars = len(tool_payload_text)
                    if delta_chars > 0:
                        delta_tokens = estimate_tokens_from_text(
                            tool_payload_text, model=tokenizer_model
                        )
                        context_stats["tool_chars"] = (
                            int(context_stats.get("tool_chars", 0)) + delta_chars
                        )
                        context_stats["tool_tokens"] = (
                            int(context_stats.get("tool_tokens", 0)) + delta_tokens
                        )
                        context_stats["total_chars"] = (
                            int(context_stats.get("total_chars", 0)) + delta_chars
                        )
                        context_stats["total_tokens"] = (
                            int(context_stats.get("total_tokens", 0)) + delta_tokens
                        )
                        yield streaming_service.format_data(
                            "context-stats",
                            {
                                "phase": "tool",
                                "label": f"Tool: {tool_name.replace('_', ' ')}",
                                "delta_chars": delta_chars,
                                "delta_tokens": delta_tokens,
                                "total_chars": context_stats.get("total_chars", 0),
                                "total_tokens": context_stats.get("total_tokens", 0),
                                "base_chars": context_stats.get("base_chars", 0),
                                "base_tokens": context_stats.get("base_tokens", 0),
                                "context_chars": context_stats.get("context_chars", 0),
                                "context_tokens": context_stats.get(
                                    "context_tokens", 0
                                ),
                                "tool_chars": context_stats.get("tool_chars", 0),
                                "tool_tokens": context_stats.get("tool_tokens", 0),
                            },
                        )

                if tool_name.startswith("smhi_") or tool_name == "trafiklab_route":
                    try:
                        tool_title = None
                        tool_metadata: dict[str, object] = {}
                        if isinstance(tool_output, dict):
                            if tool_name.startswith("smhi_"):
                                location = tool_output.get("location", {}) or {}
                                location_name = (
                                    location.get("name")
                                    or location.get("display_name")
                                    or "location"
                                )
                                category = str(
                                    tool_output.get("category") or ""
                                ).strip()
                                category_label = (
                                    category.replace("_", " ") if category else "data"
                                )
                                tool_title = f"SMHI {category_label}: {location_name}"
                                tool_metadata = {
                                    "provider": "SMHI",
                                    "tool_id": tool_name,
                                    "category": category,
                                    "location": location,
                                    "source": tool_output.get("source", {}),
                                }
                            elif tool_name == "trafiklab_route":
                                origin = (tool_output.get("origin") or {}).get("name")
                                destination = (
                                    tool_output.get("destination") or {}
                                ).get("name")
                                if origin and destination:
                                    tool_title = (
                                        f"Trafiklab route: {origin} → {destination}"
                                    )
                                tool_metadata = {
                                    "provider": "Trafiklab",
                                    "origin": tool_output.get("origin", {}),
                                    "destination": tool_output.get("destination", {}),
                                    "departures_count": len(
                                        tool_output.get("matching_entries")
                                        or tool_output.get("entries")
                                        or []
                                    ),
                                }
                        await connector_service.ingest_tool_output(
                            tool_name=tool_name,
                            tool_output=tool_output,
                            title=tool_title,
                            metadata=tool_metadata,
                            user_id=user_id,
                            origin_search_space_id=search_space_id,
                            thread_id=chat_id,
                        )
                    except Exception as exc:
                        print(f"[tool-output] Failed to ingest {tool_name}: {exc!s}")

                # Get the original tool step ID to update it (not create a new one)
                original_step_id = tool_step_ids.get(
                    run_id, f"thinking-unknown-{run_id[:8]}"
                )

                # Mark the tool thinking step as completed using the SAME step ID
                # Also add to completed set so we don't try to complete it again
                completed_step_ids.add(original_step_id)
                if tool_name == "search_knowledge_base":
                    # Get result count if available
                    result_info = "Sökning klar"
                    if isinstance(tool_output, dict):
                        result_len = tool_output.get("result_length", 0)
                        if result_len > 0:
                            result_info = (
                                f"Hittade relevant information ({result_len} tecken)"
                            )
                    # Include original query in completed items
                    completed_items = [*last_active_step_items, result_info]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Söker i kunskapsbasen"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "write_todos":
                    todos = (
                        tool_output.get("todos", [])
                        if isinstance(tool_output, dict)
                        else []
                    )
                    todo_items = format_todo_items(
                        todos if isinstance(todos, list) else []
                    )
                    completed_items = todo_items if todo_items else ["Plan uppdaterad"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Plan"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "retrieve_agents":
                    agents = []
                    if isinstance(tool_output, dict):
                        agents = tool_output.get("agents") or []
                    agent_names = [
                        agent.get("name")
                        for agent in agents
                        if isinstance(agent, dict) and agent.get("name")
                    ]
                    completed_items = (
                        [f"Agenter: {', '.join(agent_names)}"]
                        if agent_names
                        else ["Agenter valda"]
                    )
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Väljer agenter"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "call_agent":
                    agent_name = ""
                    response = ""
                    if isinstance(tool_output, dict):
                        agent_name = tool_output.get("agent") or ""
                        response = tool_output.get("response") or ""
                    completed_items = []
                    if agent_name:
                        completed_items.append(f"Agent: {agent_name}")
                    if response:
                        completed_items.append(f"Resultat: {_summarize_text(response)}")
                    if not completed_items:
                        completed_items = ["Delegering klar"]
                    title = (
                        f"Delegerade till {agent_name}"
                        if agent_name
                        else "Delegering klar"
                    )
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title(title),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "retrieve_tools":
                    tool_ids = []
                    if isinstance(tool_output, list):
                        tool_ids = [str(item) for item in tool_output]
                    elif isinstance(tool_output, dict):
                        tool_ids = tool_output.get("tools") or []
                    completed_items = (
                        [f"Verktyg: {', '.join(tool_ids)}"]
                        if tool_ids
                        else ["Verktyg valda"]
                    )
                    rerank_query = ""
                    tool_input = tool_inputs.get(run_id) if run_id else None
                    if isinstance(tool_input, dict):
                        rerank_query = str(tool_input.get("query") or "")
                    rerank_trace = get_tool_rerank_trace(
                        str(chat_id) if chat_id else None, query=rerank_query
                    )
                    if rerank_trace:
                        for entry in rerank_trace[:8]:
                            name = entry.get("name") or entry.get("tool_id")
                            score = entry.get("rerank_score")
                            if score is None:
                                score = entry.get("score")
                            if name and score is not None:
                                completed_items.append(
                                    f"{name}: rerank {float(score):.3f}"
                                )
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Väljer verktyg"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "reflect_on_progress":
                    reflection = ""
                    if isinstance(tool_output, dict):
                        reflection = tool_output.get("reflection") or ""
                    completed_items = (
                        [_summarize_text(reflection)]
                        if reflection
                        else ["Reflektion loggad"]
                    )
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Reflekterar över framsteg"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "link_preview":
                    # Build completion items based on link preview result
                    if isinstance(tool_output, dict):
                        title = tool_output.get("title", "Link")
                        domain = tool_output.get("domain", "")
                        has_error = "error" in tool_output
                        if has_error:
                            completed_items = [
                                *last_active_step_items,
                                f"Fel: {tool_output.get('error', 'Kunde inte hämta')}",
                            ]
                        else:
                            completed_items = [
                                *last_active_step_items,
                                f"Titel: {title[:60]}{'...' if len(title) > 60 else ''}",
                                f"Domän: {domain}" if domain else "Förhandsgranskning laddad",
                            ]
                    else:
                        completed_items = [*last_active_step_items, "Förhandsgranskning laddad"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Hämtar länkförhandsgranskning"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "display_image":
                    # Build completion items for image analysis
                    if isinstance(tool_output, dict):
                        title = tool_output.get("title", "")
                        alt = tool_output.get("alt", "Bild")
                        display_name = title or alt
                        completed_items = [
                            *last_active_step_items,
                            f"Analyserad: {display_name[:50]}{'...' if len(display_name) > 50 else ''}",
                        ]
                    else:
                        completed_items = [*last_active_step_items, "Bild analyserad"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Analyserar bilden"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "scrape_webpage":
                    # Build completion items for webpage scraping
                    if isinstance(tool_output, dict):
                        title = tool_output.get("title", "Webpage")
                        word_count = tool_output.get("word_count", 0)
                        has_error = "error" in tool_output
                        if has_error:
                            completed_items = [
                                *last_active_step_items,
                                f"Fel: {tool_output.get('error', 'Kunde inte hämta')[:50]}",
                            ]
                        else:
                            completed_items = [
                                *last_active_step_items,
                                f"Titel: {title[:50]}{'...' if len(title) > 50 else ''}",
                                f"Extraherat: {word_count:,} ord",
                            ]
                    else:
                        completed_items = [*last_active_step_items, "Innehåll extraherat"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Hämtar webbsida"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name.startswith("smhi_"):
                    if isinstance(tool_output, dict):
                        location = tool_output.get("location", {}) or {}
                        location_name = (
                            location.get("name")
                            or location.get("display_name")
                            or "location"
                        )
                        summary = (tool_output.get("current", {}) or {}).get(
                            "summary", {}
                        )
                        temperature = summary.get("temperature_c")
                        completed_items = [*last_active_step_items]
                        if location_name:
                            completed_items.append(
                                f"Plats: {location_name[:60]}{'...' if len(location_name) > 60 else ''}"
                            )
                        if temperature is not None:
                            completed_items.append(f"Temperatur: {temperature}\u00b0C")
                    else:
                        completed_items = [
                            *last_active_step_items,
                            "SMHI-data hämtad",
                        ]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Hämtar SMHI-data"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "trafiklab_route":
                    if isinstance(tool_output, dict):
                        origin_info = tool_output.get("origin", {}) or {}
                        destination_info = tool_output.get("destination", {}) or {}
                        origin = (
                            (origin_info.get("stop_group") or {}).get("name")
                            or origin_info.get("name")
                            or ""
                        )
                        destination = (
                            (destination_info.get("stop_group") or {}).get("name")
                            or destination_info.get("name")
                            or ""
                        )
                        matches = tool_output.get("matching_entries", []) or []
                        completed_items = [*last_active_step_items]
                        route_summary = f"{origin} -> {destination}".strip(" ->")
                        if route_summary:
                            completed_items.append(
                                f"Resväg: {route_summary[:60]}{'...' if len(route_summary) > 60 else ''}"
                            )
                        completed_items.append(f"Träffar: {len(matches)}")
                    else:
                        completed_items = [
                            *last_active_step_items,
                            "Reseresultat klara",
                        ]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Planerar resväg (Trafiklab)"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "libris_search":
                    if isinstance(tool_output, dict):
                        mode = tool_output.get("mode", "search")
                        if mode == "record":
                            record = tool_output.get("record", {}) or {}
                            title = record.get("title") or "Record"
                            completed_items = [
                                *last_active_step_items,
                                f"Post: {title}",
                            ]
                        else:
                            results = tool_output.get("results", []) or []
                            completed_items = [
                                *last_active_step_items,
                                f"Resultat: {len(results)}",
                            ]
                    else:
                        completed_items = [
                            *last_active_step_items,
                            "Libris-resultat klara",
                        ]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Söker i Libris-katalogen"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "jobad_links_search":
                    if isinstance(tool_output, dict):
                        results = tool_output.get("results", []) or []
                        completed_items = [
                            *last_active_step_items,
                            f"Resultat: {len(results)}",
                        ]
                    else:
                        completed_items = [*last_active_step_items, "Jobbannonser klara"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Söker jobbannonser"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "generate_podcast":
                    # Build detailed completion items based on podcast status
                    podcast_status = (
                        tool_output.get("status", "unknown")
                        if isinstance(tool_output, dict)
                        else "unknown"
                    )
                    podcast_title = (
                        tool_output.get("title", "Podcast")
                        if isinstance(tool_output, dict)
                        else "Podcast"
                    )

                    if podcast_status == "processing":
                        completed_items = [
                            f"Titel: {podcast_title}",
                            "Ljudgenerering startad",
                            "Bearbetar i bakgrunden...",
                        ]
                    elif podcast_status == "already_generating":
                        completed_items = [
                            f"Titel: {podcast_title}",
                            "Podd redan under generering",
                            "Vänta tills den är klar",
                        ]
                    elif podcast_status == "error":
                        error_msg = (
                            tool_output.get("error", "Okänt fel")
                            if isinstance(tool_output, dict)
                            else "Okänt fel"
                        )
                        completed_items = [
                            f"Titel: {podcast_title}",
                            f"Fel: {error_msg[:50]}",
                        ]
                    else:
                        completed_items = last_active_step_items

                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Genererar podd"),
                        status="completed",
                        items=completed_items,
                    )
                # elif tool_name == "write_todos":  # Disabled for now
                #     # Build completion items for planning/updating
                #     if isinstance(tool_output, dict):
                #         todos = tool_output.get("todos", [])
                #         todo_count = len(todos) if isinstance(todos, list) else 0
                #         completed_count = (
                #             sum(
                #                 1
                #                 for t in todos
                #                 if isinstance(t, dict)
                #                 and t.get("status") == "completed"
                #             )
                #             if isinstance(todos, list)
                #             else 0
                #         )
                #         in_progress_count = (
                #             sum(
                #                 1
                #                 for t in todos
                #                 if isinstance(t, dict)
                #                 and t.get("status") == "in_progress"
                #             )
                #             if isinstance(todos, list)
                #             else 0
                #         )

                #         # Use context-aware completion message
                #         if last_active_step_title == "Creating plan":
                #             completed_items = [f"Created {todo_count} tasks"]
                #         else:
                #             # Updating progress - show stats
                #             completed_items = [
                #                 f"Framsteg: {completed_count}/{todo_count} klara",
                #             ]
                #             if in_progress_count > 0:
                #                 # Find the currently in-progress task name
                #                 in_progress_task = next(
                #                     (
                #                         t.get("content", "")[:40]
                #                         for t in todos
                #                         if isinstance(t, dict)
                #                         and t.get("status") == "in_progress"
                #                     ),
                #                     None,
                #                 )
                #                 if in_progress_task:
                #                     completed_items.append(
                #                         f"Current: {in_progress_task}..."
                #                     )
                #     else:
                #         completed_items = ["Plan uppdaterad"]
                #     yield streaming_service.format_thinking_step(
                #         step_id=original_step_id,
                #         title=last_active_step_title,
                #         status="completed",
                #         items=completed_items,
                #     )
                elif tool_name == "ls":
                    # Build completion items showing file names found
                    if isinstance(tool_output, dict):
                        result = tool_output.get("result", "")
                    elif isinstance(tool_output, str):
                        result = tool_output
                    else:
                        result = str(tool_output) if tool_output else ""

                    # Parse file paths and extract just the file names
                    file_names = []
                    if result:
                        # The ls tool returns paths, extract just the file/folder names
                        for line in result.strip().split("\n"):
                            line = line.strip()
                            if line:
                                # Get just the filename from the path
                                name = line.rstrip("/").split("/")[-1]
                                if name and len(name) <= 40:
                                    file_names.append(name)
                                elif name:
                                    file_names.append(name[:37] + "...")

                    # Build display items - wrap file names in brackets for icon rendering
                    if file_names:
                        if len(file_names) <= 5:
                            # Wrap each file name in brackets for styled tile rendering
                            completed_items = [f"[{name}]" for name in file_names]
                        else:
                            # Show first few with brackets and count
                            completed_items = [f"[{name}]" for name in file_names[:4]]
                            completed_items.append(f"(+{len(file_names) - 4} more)")
                    else:
                        completed_items = ["Inga filer hittades"]

                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Utforskar filer"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name in ("write_todos", "reflect_on_progress"):
                    title = (
                        last_active_step_title
                        if last_active_step_title
                        else format_step_title(f"Använder {tool_name.replace('_', ' ')}")
                    )
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=title,
                        status="completed",
                        items=last_active_step_items,
                    )
                else:
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title(f"Använder {tool_name.replace('_', ' ')}"),
                        status="completed",
                        items=last_active_step_items,
                    )

                # Mark that we just finished a tool - "Synthesizing response" will be created
                # when text actually starts flowing (not immediately)
                just_finished_tool = True
                # Clear the active step since the tool is done
                last_active_step_id = None
                last_active_step_title = ""
                last_active_step_items = []

                # Handle different tool outputs
                if tool_name == "generate_podcast":
                    # Stream the full podcast result so frontend can render the audio player
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    # Send appropriate terminal message based on status
                    if (
                        isinstance(tool_output, dict)
                        and tool_output.get("status") == "success"
                    ):
                        yield streaming_service.format_terminal_info(
                            f"Podd genererad: {tool_output.get('title', 'Podd')}",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Okänt fel")
                            if isinstance(tool_output, dict)
                            else "Okänt fel"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Poddgenerering misslyckades: {error_msg}",
                            "error",
                        )
                elif tool_name == "link_preview":
                    # Stream the full link preview result so frontend can render the MediaCard
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    # Send appropriate terminal message
                    if isinstance(tool_output, dict) and "error" not in tool_output:
                        title = tool_output.get("title", "Link")
                        yield streaming_service.format_terminal_info(
                            f"Länkförhandsgranskning laddad: {title[:50]}{'...' if len(title) > 50 else ''}",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Kunde inte hämta")
                            if isinstance(tool_output, dict)
                            else "Kunde inte hämta"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Länkförhandsgranskning misslyckades: {error_msg}",
                            "error",
                        )
                elif tool_name == "display_image":
                    # Stream the full image result so frontend can render the Image component
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    # Send terminal message
                    if isinstance(tool_output, dict):
                        title = tool_output.get("title") or tool_output.get(
                            "alt", "Image"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Bild analyserad: {title[:40]}{'...' if len(title) > 40 else ''}",
                            "success",
                        )
                elif tool_name == "scrape_webpage":
                    # Stream the scrape result so frontend can render the Article component
                    # Note: We send metadata for display, but content goes to LLM for processing
                    if isinstance(tool_output, dict):
                        # Create a display-friendly output (without full content for the card)
                        display_output = {
                            k: v for k, v in tool_output.items() if k != "content"
                        }
                        # But keep a truncated content preview
                        if "content" in tool_output:
                            content = tool_output.get("content", "")
                            display_output["content_preview"] = (
                                content[:500] + "..." if len(content) > 500 else content
                            )
                        yield streaming_service.format_tool_output_available(
                            tool_call_id,
                            display_output,
                        )
                    else:
                        yield streaming_service.format_tool_output_available(
                            tool_call_id,
                            {"result": tool_output},
                        )
                    # Send terminal message
                    if isinstance(tool_output, dict) and "error" not in tool_output:
                        title = tool_output.get("title", "Webpage")
                        word_count = tool_output.get("word_count", 0)
                        yield streaming_service.format_terminal_info(
                            f"Hämtad: {title[:40]}{'...' if len(title) > 40 else ''} ({word_count:,} ord)",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Kunde inte hämta sida")
                            if isinstance(tool_output, dict)
                            else "Kunde inte hämta sida"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Hämtning misslyckades: {error_msg}",
                            "error",
                        )
                elif tool_name.startswith("smhi_"):
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    if (
                        isinstance(tool_output, dict)
                        and tool_output.get("status") == "ok"
                    ):
                        location = tool_output.get("location", {}) or {}
                        location_name = (
                            location.get("name")
                            or location.get("display_name")
                            or "location"
                        )
                        yield streaming_service.format_terminal_info(
                            f"SMHI-data laddad för {location_name[:40]}",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Kunde inte hämta SMHI-data")
                            if isinstance(tool_output, dict)
                            else "Kunde inte hämta SMHI-data"
                        )
                        yield streaming_service.format_terminal_info(
                            f"SMHI-hämtning misslyckades: {error_msg}",
                            "error",
                        )
                elif tool_name == "trafiklab_route":
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    if (
                        isinstance(tool_output, dict)
                        and tool_output.get("status") == "ok"
                    ):
                        matches = tool_output.get("matching_entries", []) or []
                        yield streaming_service.format_terminal_info(
                            f"Trafiklab-avgångar laddade ({len(matches)} träffar)",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Kunde inte hämta avgångar")
                            if isinstance(tool_output, dict)
                            else "Kunde inte hämta avgångar"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Trafiklab-rutt misslyckades: {error_msg}",
                            "error",
                        )
                elif tool_name == "libris_search":
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    if (
                        isinstance(tool_output, dict)
                        and tool_output.get("status") == "ok"
                    ):
                        results = tool_output.get("results", []) or []
                        yield streaming_service.format_terminal_info(
                            f"Libris-resultat laddade ({len(results)} poster)",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Libris-sökning misslyckades")
                            if isinstance(tool_output, dict)
                            else "Libris-sökning misslyckades"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Libris-sökning misslyckades: {error_msg}",
                            "error",
                        )
                elif tool_name == "jobad_links_search":
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    if (
                        isinstance(tool_output, dict)
                        and tool_output.get("status") == "ok"
                    ):
                        results = tool_output.get("results", []) or []
                        yield streaming_service.format_terminal_info(
                            f"Jobbannonser laddade ({len(results)} poster)",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Jobbsökning misslyckades")
                            if isinstance(tool_output, dict)
                            else "Jobbsökning misslyckades"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Jobbsökning misslyckades: {error_msg}",
                            "error",
                        )
                elif tool_name == "search_knowledge_base":
                    # Don't stream the full output for search (can be very large), just acknowledge
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        {"status": "completed", "result_length": len(str(tool_output))},
                    )
                    yield streaming_service.format_terminal_info(
                        "Sökning i kunskapsbasen klar", "success"
                    )
                elif tool_name == "write_todos":
                    todos = (
                        tool_output.get("todos", [])
                        if isinstance(tool_output, dict)
                        else []
                    )
                    todo_items = format_todo_items(
                        todos if isinstance(todos, list) else []
                    )
                    if todo_items:
                        last_active_step_items = todo_items
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    yield streaming_service.format_terminal_info(
                        f"Plan uppdaterad ({len(todo_items) or len(todos) if isinstance(todos, list) else 0} uppgifter)",
                        "success",
                    )
                elif tool_name == "write_todos":
                    # Stream the full write_todos result so frontend can render the Plan component
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output
                        if isinstance(tool_output, dict)
                        else {"result": tool_output},
                    )
                    # Send terminal message with plan info
                    if isinstance(tool_output, dict):
                        todos = tool_output.get("todos", [])
                        todo_count = len(todos) if isinstance(todos, list) else 0
                        yield streaming_service.format_terminal_info(
                            f"Plan uppdaterad ({todo_count} uppgifter)",
                            "success",
                        )
                    else:
                        yield streaming_service.format_terminal_info(
                            "Plan uppdaterad",
                            "success",
                        )
                else:
                    # Default handling for other tools
                    payload = {
                        "status": "completed",
                        "result_length": len(str(tool_output)),
                    }
                    if tool_name in external_model_tool_names:
                        payload = (
                            tool_output
                            if isinstance(tool_output, dict)
                            else {"result": tool_output}
                        )
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        payload,
                    )
                if tool_name in {
                    "trafikverket_kameror_snapshot",
                    "trafikverket_kameror_lista",
                }:
                    photos = _collect_trafikverket_photos(tool_output)
                    if photos:
                        photos = photos[:6]
                        if len(photos) > 1:
                            display_call_id = streaming_service.generate_tool_call_id()
                            gallery_args = {"images": []}
                            gallery_result = {"images": []}
                            for photo in photos:
                                image_args = {
                                    "src": photo["src"],
                                    "alt": "Trafikverket kamera",
                                    "title": photo.get("title"),
                                    "description": photo.get("description"),
                                    "href": photo.get("fullsize"),
                                }
                                image_result = _build_image_payload(**image_args)
                                gallery_args["images"].append(image_args)
                                gallery_result["images"].append(image_result)
                            yield streaming_service.format_tool_input_start(
                                display_call_id, "display_image_gallery"
                            )
                            yield streaming_service.format_tool_input_available(
                                display_call_id, "display_image_gallery", gallery_args
                            )
                            yield streaming_service.format_tool_output_available(
                                display_call_id, gallery_result
                            )
                        else:
                            photo = photos[0]
                            display_call_id = streaming_service.generate_tool_call_id()
                            image_args = {
                                "src": photo["src"],
                                "alt": "Trafikverket kamera",
                                "title": photo.get("title"),
                                "description": photo.get("description"),
                                "href": photo.get("fullsize"),
                            }
                            image_result = _build_image_payload(**image_args)
                            yield streaming_service.format_tool_input_start(
                                display_call_id, "display_image"
                            )
                            yield streaming_service.format_tool_input_available(
                                display_call_id, "display_image", image_args
                            )
                            yield streaming_service.format_tool_output_available(
                                display_call_id, image_result
                            )
                    yield streaming_service.format_terminal_info(
                        f"Verktyg {tool_name} klart", "success"
                    )

            # Handle chain/agent end to close any open text blocks
            elif event_type in ("on_chain_end", "on_agent_end"):
                chain_output = event.get("data", {}).get("output")
                for synthesis_event in emit_synthesis_draft_events(chain_output):
                    yield synthesis_event
                chain_name = chain_name_by_run_id.get(run_id) or str(
                    event.get("name") or ""
                )
                # ── response_layer_router structured step (fallback) ──
                # When the router node completes, emit a structured step
                # showing the chosen presentation mode.  This is a
                # fallback — if the LLM's streaming events propagated
                # correctly, the step may already have been emitted by
                # emit_pipeline_steps_from_text.  We guard against
                # duplicates via _pipeline_payload_kind-based signature
                # tracking (emitted_pipeline_payload_signatures).
                _cn_lower_ce = str(chain_name).strip().lower()
                if (
                    "response_layer_router" in _cn_lower_ce
                    and isinstance(chain_output, dict)
                ):
                    _chosen = str(
                        chain_output.get("response_mode") or ""
                    ).strip().lower()
                    if _chosen:
                        _rl_sig = f"response_layer_router::{_chosen}"
                        if _rl_sig not in emitted_pipeline_payload_signatures:
                            emitted_pipeline_payload_signatures.add(_rl_sig)
                            layer_labels = {
                                "kunskap": "Kunskap",
                                "analys": "Analys",
                                "syntes": "Syntes",
                                "visualisering": "Visualisering",
                            }
                            _rl_step_id = next_thinking_step_id()
                            _rl_title = format_step_title(
                                "Väljer presentationsläge"
                            )
                            _rl_items = [
                                "Nod: response_layer_router",
                                f"Valt läge: {layer_labels.get(_chosen, _chosen)}",
                            ]
                            completion_event = complete_current_step()
                            if completion_event:
                                yield completion_event
                            yield streaming_service.format_thinking_step(
                                step_id=_rl_step_id,
                                title=_rl_title,
                                status="in_progress",
                                items=_rl_items,
                            )
                            yield streaming_service.format_thinking_step(
                                step_id=_rl_step_id,
                                title=_rl_title,
                                status="completed",
                                items=_rl_items,
                            )
                            completed_step_ids.add(_rl_step_id)
                candidate_text = _extract_assistant_text_from_event_output(chain_output)
                if candidate_text:
                    source_chain = (
                        chain_name
                        if _is_any_pipeline_chain_name(chain_name)
                        else None
                    )
                    for step_event in emit_pipeline_steps_from_text(
                        candidate_text,
                        source_chain=source_chain,
                    ):
                        yield step_event
                    # Only store fallback text from OUTPUT pipeline nodes
                    # (synthesizer, response_layer, etc.). Internal nodes
                    # must NEVER become the visible response.
                    is_output_chain = (
                        _is_any_pipeline_chain_name(chain_name)
                        and not _is_internal_pipeline_chain_name(chain_name)
                    )
                    if is_output_chain:
                        cleaned_candidate = _clean_assistant_output_text(candidate_text)
                        if cleaned_candidate:
                            fallback_assistant_text = cleaned_candidate
                            # ── response_layer authoritative replacement ──
                            # The response_layer's chain_end carries the
                            # authoritative formatted text.  Emit it
                            # immediately, replacing any text that was
                            # previously streamed (from synthesizer or
                            # from the response_layer's own LLM).
                            # This is the safety net that guarantees the
                            # final visible response is ALWAYS the
                            # response_layer's output, regardless of
                            # whether the LLM's streaming events
                            # propagated correctly.
                            _cn_lower = str(chain_name).strip().lower()
                            if (
                                "response_layer" in _cn_lower
                                and "response_layer_router" not in _cn_lower
                            ):
                                # Skip replacement if the LLM's streaming
                                # events already produced the correct text
                                # (avoids a brief flicker from text-clear).
                                _stripped_acc = accumulated_text.strip()
                                _stripped_rl = cleaned_candidate.strip()
                                if _stripped_acc != _stripped_rl:
                                    if current_text_id is not None:
                                        yield streaming_service.format_text_end(
                                            current_text_id
                                        )
                                        current_text_id = None
                                    yield streaming_service.format_text_clear()
                                    current_text_id = (
                                        streaming_service.generate_text_id()
                                    )
                                    yield streaming_service.format_text_start(
                                        current_text_id
                                    )
                                    yield streaming_service.format_text_delta(
                                        current_text_id, cleaned_candidate
                                    )
                                    accumulated_text = cleaned_candidate
                if current_text_id is not None:
                    yield streaming_service.format_text_end(current_text_id)
                    current_text_id = None
                if event_type == "on_chain_end" and run_id:
                    chain_name_by_run_id.pop(run_id, None)

        # Flush think-filter buffer — EVERYTHING goes to reasoning to
        # prevent any leftover internal text from leaking as response.
        flush_reasoning, flush_text = _think_filter.flush()
        if flush_reasoning or flush_text:
            if active_reasoning_id is None:
                active_reasoning_id = streaming_service.generate_reasoning_id()
                yield streaming_service.format_reasoning_start(active_reasoning_id)
            if flush_reasoning:
                yield streaming_service.format_reasoning_delta(
                    active_reasoning_id, flush_reasoning
                )
            if flush_text:
                yield streaming_service.format_reasoning_delta(
                    active_reasoning_id, flush_text
                )
        if active_reasoning_id is not None:
            yield streaming_service.format_reasoning_end(active_reasoning_id)
            active_reasoning_id = None

        # Discard any leftover repeat buffer — it contains internal
        # pipeline text that should never reach the visible response.
        repeat_buffer = ""
        fallback_assistant_text = _clean_assistant_output_text(fallback_assistant_text)
        if not accumulated_text.strip() and fallback_assistant_text.strip():
            if current_text_id is None:
                completion_event = complete_current_step()
                if completion_event:
                    yield completion_event
                current_text_id = streaming_service.generate_text_id()
                yield streaming_service.format_text_start(current_text_id)
            yield streaming_service.format_text_delta(
                current_text_id, fallback_assistant_text
            )
            accumulated_text += fallback_assistant_text
        if current_text_id is not None:
            yield streaming_service.format_text_end(current_text_id)

        # Mark the last active thinking step as completed using the same title
        completion_event = complete_current_step()
        if completion_event:
            yield completion_event

        if trace_recorder:
            trace_end = await trace_recorder.end_span(
                span_id=trace_recorder.root_span_id,
                output_data={"status": "completed"},
                status="completed",
            )
            if trace_end:
                yield trace_end

        # Finish the step and message
        yield streaming_service.format_finish_step()
        yield streaming_service.format_finish()
        yield streaming_service.format_done()

    except Exception as e:
        # Handle any errors
        import traceback

        error_message = f"Error during chat: {e!s}"
        print(f"[stream_new_chat] {error_message}")
        print(f"[stream_new_chat] Exception type: {type(e).__name__}")
        print(f"[stream_new_chat] Traceback:\n{traceback.format_exc()}")

        # Close any open text block
        if current_text_id is not None:
            yield streaming_service.format_text_end(current_text_id)

        # Close any open reasoning block
        if active_reasoning_id is not None:
            yield streaming_service.format_reasoning_end(active_reasoning_id)
            active_reasoning_id = None

        if trace_recorder:
            trace_end = await trace_recorder.end_span(
                span_id=trace_recorder.root_span_id,
                output_data={"status": "error", "error": error_message},
                status="error",
            )
            if trace_end:
                yield trace_end

        yield streaming_service.format_error(error_message)
        yield streaming_service.format_finish_step()
        yield streaming_service.format_finish()
        yield streaming_service.format_done()

    finally:
        # Clear AI responding state for live collaboration
        await clear_ai_responding(session, chat_id)
        if trace_recorder:
            await trace_recorder.end_session()
        if trace_db_session:
            await trace_db_session.close()
