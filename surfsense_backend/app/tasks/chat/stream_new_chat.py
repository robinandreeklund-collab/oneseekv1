"""
Streaming task for the new SurfSense deep agent chat.

This module streams responses from the deep agent using the Vercel AI SDK
Data Stream Protocol (SSE format).

Supports loading LLM configurations from:
- YAML files (negative IDs for global configs)
- NewLLMConfig database table (positive IDs for user-created configs with prompt settings)
"""

import json
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.agents.new_chat.chat_deepagent import create_surfsense_deep_agent
from app.agents.new_chat.checkpointer import get_checkpointer
from app.agents.new_chat.llm_config import (
    AgentConfig,
    create_chat_litellm_from_agent_config,
    create_chat_litellm_from_config,
    load_agent_config,
    load_llm_config_from_yaml,
)
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
from app.agents.new_chat.compare_prompts import (
    COMPARE_SUPERVISOR_INSTRUCTIONS,
    DEFAULT_COMPARE_ANALYSIS_PROMPT,
    build_compare_synthesis_prompt,
)
from app.agents.new_chat.dispatcher import (
    DEFAULT_ROUTE_SYSTEM_PROMPT,
    dispatch_route,
)
from app.agents.new_chat.prompt_registry import resolve_prompt
from app.agents.new_chat.routing import Route, ROUTE_TOOL_SETS
from app.agents.new_chat.system_prompt import SURFSENSE_CITATION_INSTRUCTIONS
from app.agents.new_chat.supervisor_agent import create_supervisor_agent
from app.agents.new_chat.supervisor_prompts import (
    DEFAULT_SUPERVISOR_PROMPT,
    build_supervisor_prompt,
)
from app.agents.new_chat.statistics_prompts import (
    DEFAULT_STATISTICS_SYSTEM_PROMPT,
    build_statistics_system_prompt,
)
from app.agents.new_chat.subagent_utils import (
    SMALLTALK_INSTRUCTIONS,
    build_subagent_config,
)
from app.agents.new_chat.trafik_prompts import (
    DEFAULT_TRAFFIC_SYSTEM_PROMPT,
    build_trafik_prompt,
)
from app.agents.new_chat.tools.external_models import DEFAULT_EXTERNAL_SYSTEM_PROMPT
from app.agents.new_chat.tools.external_models import EXTERNAL_MODEL_SPECS
from app.agents.new_chat.tools.display_image import extract_domain, generate_image_id
from app.services.agent_prompt_service import get_global_prompt_overrides
from app.db import ChatTraceSession, Document, SurfsenseDocsDocument, async_session_maker
from app.schemas.new_chat import ChatAttachment
from app.services.chat_session_state_service import (
    clear_ai_responding,
    set_ai_responding,
)
from app.agents.new_chat.tools.user_memory import create_save_memory_tool
from app.services.connector_service import ConnectorService
from app.services.new_streaming_service import VercelStreamingService
from app.services.trace_service import TraceRecorder
from app.tasks.chat.stream_compare_chat import (
    extract_compare_query,
    is_compare_request,
)
from app.tasks.chat.context_formatters import (
    format_attachments_as_context,
    format_mentioned_documents_as_context,
    format_mentioned_surfsense_docs_as_context,
)
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
        re.compile(r"\bjag heter ([A-ZÅÄÖ][\wÅÄÖåäö\-]+(?:\s+[A-ZÅÄÖ][\wÅÄÖåäö\-]+)*)", re.IGNORECASE),
        "fact",
        "User's name is {value}",
    ),
    (
        re.compile(r"\bkalla mig ([A-ZÅÄÖ][\wÅÄÖåäö\-]+(?:\s+[A-ZÅÄÖ][\wÅÄÖåäö\-]+)*)", re.IGNORECASE),
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
        re.compile(r"\bjag (?:jobbar|arbetar) som ([A-Za-zÅÄÖåäö\s\-]{2,80})\b", re.IGNORECASE),
        "fact",
        "User works as {value}",
    ),
    (
        re.compile(r"\bjag (?:gillar|föredrar|tycker om) ([^.!?\n]{2,80})", re.IGNORECASE),
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
from app.utils.content_utils import bootstrap_history_from_db




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
                        node.get("Description")
                        or node.get("LocationDescriptor")
                        or ""
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
    tool_calls = getattr(message, "tool_calls", None) or getattr(message, "toolCalls", None)
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
        return _extract_assistant_text_from_event_output(getattr(output, "generations"))
    if hasattr(output, "message"):
        return _extract_assistant_text_from_event_output(getattr(output, "message"))
    if hasattr(output, "content"):
        return _extract_assistant_text_from_message(output)
    return ""


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
        router_prompt = resolve_prompt(
            prompt_overrides, "router.top_level", DEFAULT_ROUTE_SYSTEM_PROMPT
        )

        route = await dispatch_route(
            raw_user_query,
            llm,
            has_attachments=bool(attachments),
            has_mentions=bool(mentioned_document_ids or mentioned_surfsense_doc_ids),
            system_prompt_override=router_prompt,
        )
        if route == Route.COMPARE and compare_query:
            user_query = compare_query
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
        supervisor_prompt = resolve_prompt(
            prompt_overrides,
            "agent.supervisor.system",
            DEFAULT_SUPERVISOR_PROMPT,
        )
        supervisor_system_prompt = build_supervisor_prompt(
            supervisor_prompt,
            citation_instructions=citation_instructions_block,
        )
        if route == Route.COMPARE:
            supervisor_system_prompt = (
                supervisor_system_prompt + "\n\n" + COMPARE_SUPERVISOR_INSTRUCTIONS
            )

        knowledge_prompt = resolve_prompt(
            prompt_overrides,
            "agent.knowledge.system",
            resolve_prompt(
                prompt_overrides,
                "agent.worker.knowledge",
                DEFAULT_WORKER_KNOWLEDGE_PROMPT,
            ),
        )
        knowledge_worker_prompt = build_worker_prompt(
            knowledge_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        )
        action_prompt = resolve_prompt(
            prompt_overrides,
            "agent.action.system",
            resolve_prompt(
                prompt_overrides,
                "agent.worker.action",
                DEFAULT_WORKER_ACTION_PROMPT,
            ),
        )
        action_worker_prompt = build_worker_prompt(
            action_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        )
        media_prompt = resolve_prompt(
            prompt_overrides,
            "agent.media.system",
            action_prompt,
        )
        browser_prompt = resolve_prompt(
            prompt_overrides,
            "agent.browser.system",
            knowledge_prompt,
        )
        code_prompt = resolve_prompt(
            prompt_overrides,
            "agent.code.system",
            knowledge_prompt,
        )
        kartor_prompt = resolve_prompt(
            prompt_overrides,
            "agent.kartor.system",
            action_prompt,
        )
        statistics_prompt = resolve_prompt(
            prompt_overrides,
            "agent.statistics.system",
            DEFAULT_STATISTICS_SYSTEM_PROMPT,
        )
        statistics_worker_prompt = build_statistics_system_prompt(
            statistics_prompt,
            citation_instructions=citation_instructions_block,
        )
        synthesis_prompt = resolve_prompt(
            prompt_overrides,
            "agent.synthesis.system",
            statistics_prompt,
        )
        bolag_prompt = resolve_prompt(
            prompt_overrides,
            "agent.bolag.system",
            DEFAULT_BOLAG_SYSTEM_PROMPT,
        )
        bolag_worker_prompt = build_bolag_prompt(
            bolag_prompt,
            citation_instructions=citation_instructions_block,
        )
        trafik_prompt = resolve_prompt(
            prompt_overrides,
            "agent.trafik.system",
            DEFAULT_TRAFFIC_SYSTEM_PROMPT,
        )
        trafik_worker_prompt = build_trafik_prompt(
            trafik_prompt,
            citation_instructions=citation_instructions_block,
        )
        compare_analysis_prompt = resolve_prompt(
            prompt_overrides,
            "compare.analysis.system",
            DEFAULT_COMPARE_ANALYSIS_PROMPT,
        )
        compare_synthesis_prompt = build_compare_synthesis_prompt(
            compare_analysis_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        )
        compare_external_prompt = resolve_prompt(
            prompt_overrides,
            "compare.external.system",
            DEFAULT_EXTERNAL_SYSTEM_PROMPT,
        )

        if route == Route.SMALLTALK:
            smalltalk_prompt = resolve_prompt(
                prompt_overrides,
                "agent.smalltalk.system",
                SMALLTALK_INSTRUCTIONS,
            )
        else:
            worker_system_prompt = supervisor_system_prompt

        effective_agent_config = agent_config
        if route == Route.SMALLTALK and smalltalk_prompt:
            effective_agent_config = build_subagent_config(
                agent_config, smalltalk_prompt
            )

        if trace_recorder:
            route_span_id = f"route-{uuid.uuid4().hex[:8]}"
            route_meta = {
                "route": route.value,
                "citations_enabled": citations_enabled,
                "citation_instructions_enabled": citations_enabled,
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

        # Get the PostgreSQL checkpointer for persistent conversation memory
        checkpointer = await get_checkpointer()

        if route != Route.SMALLTALK:
            agent = await create_supervisor_agent(
                llm=llm,
                dependencies={
                    "search_space_id": search_space_id,
                    "db_session": session,
                    "connector_service": connector_service,
                    "firecrawl_api_key": firecrawl_api_key,
                    "user_id": user_id,
                    "thread_id": chat_id,
                },
                checkpointer=checkpointer,
                knowledge_prompt=knowledge_worker_prompt,
                action_prompt=action_worker_prompt,
                statistics_prompt=statistics_worker_prompt,
                synthesis_prompt=compare_synthesis_prompt or synthesis_prompt,
                compare_mode=route == Route.COMPARE,
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
                tool_prompt_overrides=prompt_overrides,
            )
        else:
            # Fallback to deep agent for smalltalk
            agent = await create_surfsense_deep_agent(
                llm=llm,
                search_space_id=search_space_id,
                db_session=session,
                connector_service=connector_service,
                checkpointer=checkpointer,
                user_id=user_id,  # Pass user ID for memory tools
                thread_id=chat_id,  # Pass chat ID for podcast association
                agent_config=effective_agent_config,  # Pass prompt configuration
                firecrawl_api_key=firecrawl_api_key,  # Pass Firecrawl API key if configured
                enabled_tools=ROUTE_TOOL_SETS.get(route, []),
                tool_names_for_prompt=[],
                force_citations_enabled=citations_enabled,
                citation_instructions=citation_instructions_block,
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
        if worker_system_prompt:
            langchain_messages.append(SystemMessage(content=worker_system_prompt))
        langchain_messages.append(HumanMessage(content=final_query))

        input_state = {
            # Lets not pass this message atm because we are using the checkpointer to manage the conversation history
            # We will use this to simulate group chat functionality in the future
            "messages": langchain_messages,
        }
        if route == Route.SMALLTALK:
            input_state["search_space_id"] = search_space_id
        else:
            input_state["route_hint"] = route.value

        # Configure LangGraph with thread_id for memory
        # If checkpoint_id is provided, fork from that checkpoint (for edit/reload)
        configurable = {"thread_id": str(chat_id)}
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

        route_step_id = next_thinking_step_id()
        route_items = [f"Route: {route.value}"]
        yield streaming_service.format_thinking_step(
            step_id=route_step_id,
            title=format_step_title("Routing request"),
            status="in_progress",
            items=route_items,
        )
        yield streaming_service.format_thinking_step(
            step_id=route_step_id,
            title=format_step_title("Routing request"),
            status="completed",
            items=route_items,
        )
        completed_step_ids.add(route_step_id)

        # Initial thinking step - analyzing the request
        analyze_step_id = next_thinking_step_id()
        last_active_step_id = analyze_step_id

        # Determine step title and action verb based on context
        if attachments and (mentioned_documents or mentioned_surfsense_docs):
            last_active_step_title = format_step_title("Analyzing your content")
            action_verb = "Reading"
        elif attachments:
            last_active_step_title = format_step_title("Reading your content")
            action_verb = "Reading"
        elif mentioned_documents or mentioned_surfsense_docs:
            last_active_step_title = format_step_title("Analyzing referenced content")
            action_verb = "Analyzing"
        else:
            last_active_step_title = format_step_title("Understanding your request")
            action_verb = "Processing"

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
                processing_parts.append(f"[{len(attachment_names)} files]")

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
                processing_parts.append(f"[{len(doc_names)} documents]")

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
                processing_parts.append(f"[{len(doc_names)} docs]")

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
                    match = re.search(r"\{\s*\"status\"\s*:", remaining)
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
            if not repeat_candidate:
                if text.lstrip().startswith(stripped_existing[:10]):
                    repeat_candidate = True
                else:
                    return text
            repeat_buffer += text
            if len(repeat_buffer) < 60:
                return ""
            if stripped_existing.startswith(repeat_buffer[:60].lstrip()):
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

            if trace_recorder:
                if event_type == "on_chain_start":
                    chain_name = event.get("name") or "chain"
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
                    trace_event = await trace_recorder.end_span(
                        span_id=run_id,
                        output_data=chain_output,
                        status="completed",
                    )
                    if trace_event:
                        yield trace_event
                    candidate_text = _extract_assistant_text_from_event_output(
                        chain_output
                    )
                    if candidate_text:
                        fallback_assistant_text = candidate_text
                elif event_type == "on_chain_error":
                    trace_event = await trace_recorder.end_span(
                        span_id=run_id,
                        output_data=event.get("data"),
                        status="error",
                    )
                    if trace_event:
                        yield trace_event
                elif event_type in ("on_chat_model_start", "on_llm_start"):
                    model_data = event.get("data", {})
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
                    if candidate_text:
                        fallback_assistant_text = candidate_text

            # Handle chat model stream events (text streaming)
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    content = chunk.content
                    if content and isinstance(content, str):
                        content = filter_critic_json(content)
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

                # Complete any previous step EXCEPT "Synthesizing response"
                # (we want to reuse the Synthesizing step after tools complete)
                if last_active_step_title != format_step_title("Synthesizing response"):
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
                        "Searching knowledge base"
                    )
                    last_active_step_items = [
                        f"Query: {query[:100]}{'...' if len(query) > 100 else ''}"
                    ]
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
                    last_active_step_title = format_step_title(
                        "Fetching link preview"
                    )
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
                    last_active_step_title = format_step_title("Analyzing the image")
                    last_active_step_items = [
                        f"Analyzing: {title[:50] if title else src[:50]}{'...' if len(title or src) > 50 else ''}"
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
                    last_active_step_title = format_step_title("Scraping webpage")
                    last_active_step_items = [
                        f"URL: {url[:80]}{'...' if len(url) > 80 else ''}"
                    ]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
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
                    last_active_step_title = format_step_title(
                        "Fetching weather (SMHI)"
                    )
                    last_active_step_items = [
                        f"Location: {location[:80]}{'...' if len(location) > 80 else ''}"
                    ]
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
                        origin = tool_input.get("origin") or tool_input.get("origin_id") or ""
                        destination = (
                            tool_input.get("destination") or tool_input.get("destination_id") or ""
                        )
                        time_value = tool_input.get("time") or ""
                    else:
                        origin = str(tool_input)
                    last_active_step_title = format_step_title(
                        "Planning route (Trafiklab)"
                    )
                    route_text = f"{origin} -> {destination}".strip()
                    last_active_step_items = [
                        f"Route: {route_text[:80]}{'...' if len(route_text) > 80 else ''}"
                    ]
                    if time_value:
                        last_active_step_items.append(
                            f"Time: {time_value[:40]}{'...' if len(time_value) > 40 else ''}"
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
                        "Searching Libris catalog"
                    )
                    item_label = (
                        f"Record: {record_id}" if record_id else f"Query: {query}"
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
                    last_active_step_title = format_step_title("Searching job ads")
                    details = f"{query} {location}".strip()
                    last_active_step_items = [
                        f"Search: {details[:100]}{'...' if len(details) > 100 else ''}"
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
                        last_active_step_title = format_step_title("Creating plan")
                        last_active_step_items = [f"Defining {todo_count} tasks..."]
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

                        last_active_step_title = format_step_title("Updating plan")
                        last_active_step_items = (
                            [
                                f"Progress: {completed_count}/{todo_count} completed",
                                f"In progress: {in_progress_count} tasks",
                            ]
                            if completed_count > 0
                            else [f"Working on {todo_count} tasks"]
                        )

                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "retrieve_agents":
                    query = tool_input.get("query") if isinstance(tool_input, dict) else tool_input
                    limit = tool_input.get("limit") if isinstance(tool_input, dict) else None
                    last_active_step_title = format_step_title("Selecting agents")
                    last_active_step_items = [
                        f"Query: {_summarize_text(query)}"
                    ]
                    if limit:
                        last_active_step_items.append(f"Limit: {limit}")
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
                        agent_name = tool_input.get("agent_name") or tool_input.get("agent") or ""
                        task = tool_input.get("task") or ""
                    else:
                        task = str(tool_input)
                    title_agent = agent_name or "worker"
                    last_active_step_title = format_step_title(
                        f"Delegating to {title_agent}"
                    )
                    last_active_step_items = []
                    if agent_name:
                        last_active_step_items.append(f"Agent: {agent_name}")
                    if task:
                        last_active_step_items.append(
                            f"Task: {_summarize_text(task)}"
                        )
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
                        items=last_active_step_items,
                    )
                elif tool_name == "retrieve_tools":
                    query = tool_input.get("query") if isinstance(tool_input, dict) else tool_input
                    last_active_step_title = format_step_title("Selecting tools")
                    last_active_step_items = [f"Query: {_summarize_text(query)}"]
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
                    last_active_step_title = format_step_title("Reflecting on progress")
                    last_active_step_items = [
                        _summarize_text(reflection)
                        if reflection
                        else "Reviewing findings, gaps, and next steps"
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
                    last_active_step_title = format_step_title("Generating podcast")
                    last_active_step_items = [
                        f"Title: {podcast_title}",
                        f"Content: {content_len:,} characters",
                        "Preparing audio generation...",
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
                        f"Using {tool_name.replace('_', ' ')}"
                    )
                    last_active_step_items = []
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=last_active_step_title,
                        status="in_progress",
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
                        tool_output.get("status") == "error"
                        or "error" in tool_output
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

                if tool_name in {"smhi_weather", "trafiklab_route"}:
                    try:
                        tool_title = None
                        tool_metadata: dict[str, object] = {}
                        if isinstance(tool_output, dict):
                            if tool_name == "smhi_weather":
                                location = tool_output.get("location", {}) or {}
                                location_name = (
                                    location.get("name")
                                    or location.get("display_name")
                                    or "location"
                                )
                                tool_title = f"SMHI weather: {location_name}"
                                tool_metadata = {
                                    "provider": "SMHI",
                                    "location": location,
                                    "source": tool_output.get("source", {}),
                                }
                            elif tool_name == "trafiklab_route":
                                origin = (tool_output.get("origin") or {}).get("name")
                                destination = (tool_output.get("destination") or {}).get("name")
                                if origin and destination:
                                    tool_title = f"Trafiklab route: {origin} → {destination}"
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
                    result_info = "Search completed"
                    if isinstance(tool_output, dict):
                        result_len = tool_output.get("result_length", 0)
                        if result_len > 0:
                            result_info = (
                                f"Found relevant information ({result_len} chars)"
                            )
                    # Include original query in completed items
                    completed_items = [*last_active_step_items, result_info]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Searching knowledge base"),
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
                    completed_items = (
                        todo_items if todo_items else ["Plan updated"]
                    )
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
                        [f"Agents: {', '.join(agent_names)}"]
                        if agent_names
                        else ["Agents selected"]
                    )
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Selecting agents"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "call_agent":
                    agent_name = ""
                    response = ""
                    critic = {}
                    if isinstance(tool_output, dict):
                        agent_name = tool_output.get("agent") or ""
                        response = tool_output.get("response") or ""
                        critic = tool_output.get("critic") or {}
                    completed_items = []
                    if agent_name:
                        completed_items.append(f"Agent: {agent_name}")
                    if response:
                        completed_items.append(f"Result: {_summarize_text(response)}")
                    if isinstance(critic, dict) and critic.get("reason"):
                        completed_items.append(
                            f"Critic: {_summarize_text(critic.get('reason'))}"
                        )
                    if not completed_items:
                        completed_items = ["Delegation completed"]
                    title = (
                        f"Delegated to {agent_name}"
                        if agent_name
                        else "Delegation completed"
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
                        [f"Tools: {', '.join(tool_ids)}"]
                        if tool_ids
                        else ["Tools selected"]
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
                        title=format_step_title("Selecting tools"),
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
                        else ["Reflection logged"]
                    )
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Reflecting on progress"),
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
                                f"Error: {tool_output.get('error', 'Failed to fetch')}",
                            ]
                        else:
                            completed_items = [
                                *last_active_step_items,
                                f"Title: {title[:60]}{'...' if len(title) > 60 else ''}",
                                f"Domain: {domain}" if domain else "Preview loaded",
                            ]
                    else:
                        completed_items = [*last_active_step_items, "Preview loaded"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Fetching link preview"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "display_image":
                    # Build completion items for image analysis
                    if isinstance(tool_output, dict):
                        title = tool_output.get("title", "")
                        alt = tool_output.get("alt", "Image")
                        display_name = title or alt
                        completed_items = [
                            *last_active_step_items,
                            f"Analyzed: {display_name[:50]}{'...' if len(display_name) > 50 else ''}",
                        ]
                    else:
                        completed_items = [*last_active_step_items, "Image analyzed"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Analyzing the image"),
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
                                f"Error: {tool_output.get('error', 'Failed to scrape')[:50]}",
                            ]
                        else:
                            completed_items = [
                                *last_active_step_items,
                                f"Title: {title[:50]}{'...' if len(title) > 50 else ''}",
                                f"Extracted: {word_count:,} words",
                            ]
                    else:
                        completed_items = [*last_active_step_items, "Content extracted"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Scraping webpage"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "smhi_weather":
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
                        if temperature is not None:
                            completed_items.append(f"Temperature: {temperature} C")
                    else:
                        completed_items = [*last_active_step_items, "Weather data retrieved"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Fetching weather (SMHI)"),
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
                                f"Route: {route_summary[:60]}{'...' if len(route_summary) > 60 else ''}"
                            )
                        completed_items.append(
                            f"Matches: {len(matches)}"
                        )
                    else:
                        completed_items = [*last_active_step_items, "Route results ready"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Planning route (Trafiklab)"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "libris_search":
                    if isinstance(tool_output, dict):
                        mode = tool_output.get("mode", "search")
                        if mode == "record":
                            record = tool_output.get("record", {}) or {}
                            title = record.get("title") or "Record"
                            completed_items = [*last_active_step_items, f"Record: {title}"]
                        else:
                            results = tool_output.get("results", []) or []
                            completed_items = [
                                *last_active_step_items,
                                f"Results: {len(results)}",
                            ]
                    else:
                        completed_items = [*last_active_step_items, "Libris results ready"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Searching Libris catalog"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name == "jobad_links_search":
                    if isinstance(tool_output, dict):
                        results = tool_output.get("results", []) or []
                        completed_items = [
                            *last_active_step_items,
                            f"Results: {len(results)}",
                        ]
                    else:
                        completed_items = [*last_active_step_items, "Job ads ready"]
                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Searching job ads"),
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
                            f"Title: {podcast_title}",
                            "Audio generation started",
                            "Processing in background...",
                        ]
                    elif podcast_status == "already_generating":
                        completed_items = [
                            f"Title: {podcast_title}",
                            "Podcast already in progress",
                            "Please wait for it to complete",
                        ]
                    elif podcast_status == "error":
                        error_msg = (
                            tool_output.get("error", "Unknown error")
                            if isinstance(tool_output, dict)
                            else "Unknown error"
                        )
                        completed_items = [
                            f"Title: {podcast_title}",
                            f"Error: {error_msg[:50]}",
                        ]
                    else:
                        completed_items = last_active_step_items

                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Generating podcast"),
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
                #                 f"Progress: {completed_count}/{todo_count} completed",
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
                #         completed_items = ["Plan updated"]
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
                        completed_items = ["No files found"]

                    yield streaming_service.format_thinking_step(
                        step_id=original_step_id,
                        title=format_step_title("Exploring files"),
                        status="completed",
                        items=completed_items,
                    )
                elif tool_name in ("write_todos", "reflect_on_progress"):
                    title = (
                        last_active_step_title
                        if last_active_step_title
                        else format_step_title(f"Using {tool_name.replace('_', ' ')}")
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
                        title=format_step_title(
                            f"Using {tool_name.replace('_', ' ')}"
                        ),
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
                            f"Podcast generated successfully: {tool_output.get('title', 'Podcast')}",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Unknown error")
                            if isinstance(tool_output, dict)
                            else "Unknown error"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Podcast generation failed: {error_msg}",
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
                            f"Link preview loaded: {title[:50]}{'...' if len(title) > 50 else ''}",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Failed to fetch")
                            if isinstance(tool_output, dict)
                            else "Failed to fetch"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Link preview failed: {error_msg}",
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
                            f"Image analyzed: {title[:40]}{'...' if len(title) > 40 else ''}",
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
                            f"Scraped: {title[:40]}{'...' if len(title) > 40 else ''} ({word_count:,} words)",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Failed to scrape")
                            if isinstance(tool_output, dict)
                            else "Failed to scrape"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Scrape failed: {error_msg}",
                            "error",
                        )
                elif tool_name == "smhi_weather":
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output if isinstance(tool_output, dict) else {"result": tool_output},
                    )
                    if isinstance(tool_output, dict) and tool_output.get("status") == "ok":
                        location = tool_output.get("location", {}) or {}
                        location_name = (
                            location.get("name")
                            or location.get("display_name")
                            or "location"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Weather data loaded for {location_name[:40]}",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Failed to fetch weather")
                            if isinstance(tool_output, dict)
                            else "Failed to fetch weather"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Weather lookup failed: {error_msg}",
                            "error",
                        )
                elif tool_name == "trafiklab_route":
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output if isinstance(tool_output, dict) else {"result": tool_output},
                    )
                    if isinstance(tool_output, dict) and tool_output.get("status") == "ok":
                        matches = tool_output.get("matching_entries", []) or []
                        yield streaming_service.format_terminal_info(
                            f"Trafiklab departures loaded ({len(matches)} matches)",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Failed to fetch departures")
                            if isinstance(tool_output, dict)
                            else "Failed to fetch departures"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Trafiklab route failed: {error_msg}",
                            "error",
                        )
                elif tool_name == "libris_search":
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output if isinstance(tool_output, dict) else {"result": tool_output},
                    )
                    if isinstance(tool_output, dict) and tool_output.get("status") == "ok":
                        results = tool_output.get("results", []) or []
                        yield streaming_service.format_terminal_info(
                            f"Libris results loaded ({len(results)} items)",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Libris search failed")
                            if isinstance(tool_output, dict)
                            else "Libris search failed"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Libris search failed: {error_msg}",
                            "error",
                        )
                elif tool_name == "jobad_links_search":
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output if isinstance(tool_output, dict) else {"result": tool_output},
                    )
                    if isinstance(tool_output, dict) and tool_output.get("status") == "ok":
                        results = tool_output.get("results", []) or []
                        yield streaming_service.format_terminal_info(
                            f"Job ads loaded ({len(results)} items)",
                            "success",
                        )
                    else:
                        error_msg = (
                            tool_output.get("error", "Job ad search failed")
                            if isinstance(tool_output, dict)
                            else "Job ad search failed"
                        )
                        yield streaming_service.format_terminal_info(
                            f"Job ad search failed: {error_msg}",
                            "error",
                        )
                elif tool_name == "search_knowledge_base":
                    # Don't stream the full output for search (can be very large), just acknowledge
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        {"status": "completed", "result_length": len(str(tool_output))},
                    )
                    yield streaming_service.format_terminal_info(
                        "Knowledge base search completed", "success"
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
                        f"Plan updated ({len(todo_items) or len(todos) if isinstance(todos, list) else 0} tasks)",
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
                            f"Plan updated ({todo_count} tasks)",
                            "success",
                        )
                    else:
                        yield streaming_service.format_terminal_info(
                            "Plan updated",
                            "success",
                        )
                else:
                    # Default handling for other tools
                    payload = {"status": "completed", "result_length": len(str(tool_output))}
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
                        f"Tool {tool_name} completed", "success"
                    )

            # Handle chain/agent end to close any open text blocks
            elif event_type in ("on_chain_end", "on_agent_end"):
                candidate_text = _extract_assistant_text_from_event_output(
                    event.get("data", {}).get("output")
                )
                if candidate_text:
                    fallback_assistant_text = candidate_text
                if current_text_id is not None:
                    yield streaming_service.format_text_end(current_text_id)
                    current_text_id = None

        # Ensure text block is closed
        if repeat_buffer and not suppress_repeat:
            if current_text_id is None:
                current_text_id = streaming_service.generate_text_id()
                yield streaming_service.format_text_start(current_text_id)
            yield streaming_service.format_text_delta(current_text_id, repeat_buffer)
            accumulated_text += repeat_buffer
            repeat_buffer = ""
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
