"""
Streaming task for SurfSense compare mode.

Compare mode runs the same query across multiple external LLMs in parallel,
streams thinking steps for each call, then synthesizes an optimized answer
using a local LLM and Tavily.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.agents.new_chat.chat_deepagent import create_surfsense_deep_agent
from app.agents.new_chat.llm_config import (
    create_chat_litellm_from_agent_config,
    load_agent_config,
    load_llm_config_from_yaml,
)
from app.agents.new_chat.tools.external_models import (
    EXTERNAL_MODEL_SPECS,
    call_external_model,
    describe_external_model_config,
)
from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.db import Document, NewChatThread, SurfsenseDocsDocument
from app.schemas.new_chat import ChatAttachment
from app.services.connector_service import ConnectorService
from app.services.new_streaming_service import VercelStreamingService
from app.tasks.chat.context_formatters import (
    format_attachments_as_context,
    format_mentioned_documents_as_context,
    format_mentioned_surfsense_docs_as_context,
)

COMPARE_PREFIX = "/compare"
COMPARE_TIMEOUT_SECONDS = 90
COMPARE_RAW_ANSWER_CHARS = 12000
MAX_TAVILY_RESULTS = 6
COMPARE_SUMMARY_ANSWER_CHARS = 600
COMPARE_SUMMARY_FINAL_CHARS = 700

LOCAL_ANALYSIS_SYSTEM_PROMPT = (
    "Du är Oneseek Compare Analyzer. Din roll är att syntetisera ett högkvalitativt "
    "svar från en användarfråga, flera verktygssvar från externa modeller och "
    "Tavily-webbsnuttar.\n\n"
    "**Indatastruktur**:\n"
    "- Användarfråga: Den ursprungliga frågan.\n"
    "- Verktygssvar: Utdata från externa modeller (märkta som MODEL_ANSWER med "
    "modellnamn).\n"
    "- Tavily-snuttar: Webbkällor i <sources>-sektionen med <chunk id='...'>-taggar.\n\n"
    "**Kärnuppgifter**:\n"
    "1. Utvärdera korrekthet: Korskontrollera fakta mellan alla källor.\n"
    "2. Lös konflikter: Om källor säger olika, prioritera Tavily för faktapåståenden, "
    "därefter det mest aktuella. Nämn osäkerheter och förklara varför "
    "(t.ex. \"Källa A hävdar X, men Tavily indikerar Y p.g.a. nya uppdateringar\").\n"
    "3. Fyll luckor: Använd egen allmän kunskap vid behov, men var tydlig med att "
    "det är allmän kunskap.\n"
    "4. Skapa ett optimerat svar: Skriv ett sammanhängande, korrekt och välstrukturerat "
    "svar. Attributera fakta till modeller (t.ex. \"Enligt Modell X...\"). "
    "För Tavily och modellutdata: citera inline med [citation:chunk_id]. "
    "Nämn modellnamn i löptext och använd [citation:chunk_id] för det som kommer "
    "från modellen. Undvik numrerade hakparenteser som [1] och skriv ingen separat "
    "referenslista.\n\n"
    "**Svarsriktlinjer**:\n"
    "- Svara på samma språk som användaren.\n"
    "- Håll huvudsvaret kort, faktabaserat, tydligt och engagerande.\n"
    "- Om info är osäker eller konfliktfylld: säg det och förklara varför.\n"
    "- Prioritera tillförlitliga, aktuella källor (Tavily > färskhet > modellkonsensus "
    "> intern kunskap).\n\n"
    "**Uppföljningsfrågor (viktigt format)**:\n"
    "Efter huvudsvaret ska du alltid lämna 2–4 riktade uppföljningsfrågor, "
    "men de får INTE synas i den synliga texten. "
    "Lägg dem i en HTML-kommentar exakt så här:\n"
    "<!-- possible_next_steps:\n"
    "- Fråga 1\n"
    "- Fråga 2\n"
    "-->\n"
    "Skriv ingen rubrik som \"Possible next steps\" i den synliga texten.\n\n"
    "Exempel på bra uppföljningsfrågor:\n"
    "- Vill du att jag gör en punkt-för-punkt-jämförelse av de viktigaste påståendena "
    "från Modell X vs Modell Y?\n"
    "- Ska jag extrahera och rangordna alla faktapåståenden där modellerna inte "
    "är överens?\n"
    "- Vill du ha en metaanalys av styrkor/svagheter för varje modell i ämnet?\n"
    "- Vill du att jag analyserar språklig bias, osäkerhetsmarkörer och "
    "sannolikhetsnivåer i svaren?\n"
    "- Ska jag granska källkritik, tidsaspekter eller metodskillnader mellan modellerna?\n"
    "- Vill du ha en sammanfattning av konsensus vs kontrovers?\n\n"
    "Hitta inte på information. Var saklig och transparent."
)

COMPARE_CITATION_INSTRUCTIONS = ""





def is_compare_request(user_query: str) -> bool:
    """Check if the user query activates compare mode."""
    return user_query.strip().lower().startswith(COMPARE_PREFIX)


def extract_compare_query(user_query: str) -> str:
    """Strip the /compare prefix and return the actual query."""
    trimmed = user_query.strip()
    if not trimmed.lower().startswith(COMPARE_PREFIX):
        return ""
    remainder = trimmed[len(COMPARE_PREFIX) :].strip()
    if remainder.startswith(":"):
        remainder = remainder[1:].strip()
    return remainder


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _build_compare_summary(
    query: str,
    provider_summaries: dict[str, dict[str, str]],
    final_answer: str,
) -> dict:
    return {
        "query": query,
        "providers": provider_summaries,
        "final_answer": _truncate_text(final_answer, COMPARE_SUMMARY_FINAL_CHARS)
        if final_answer
        else "",
    }


def _build_model_answer_documents(
    provider_results: dict[str, dict],
    specs: list[dict[str, str]] | None = None,
) -> list[dict]:
    documents: list[dict] = []
    if specs is None:
        specs = [{"key": spec.key, "display": spec.display} for spec in EXTERNAL_MODEL_SPECS]
    for spec in specs:
        provider_key = spec["key"]
        result = provider_results.get(provider_key)
        if not result:
            continue
        answer_text = result.get("response") or ""
        if not isinstance(answer_text, str):
            answer_text = str(answer_text)
        answer_text = _truncate_text(answer_text, COMPARE_SUMMARY_ANSWER_CHARS)
        if not answer_text:
            continue
        documents.append(
            {
                "document": {
                    "id": f"model-{provider_key}",
                    "title": f"{spec['display']} response",
                    "document_type": "MODEL_ANSWER",
                    "metadata": {
                        "source": "MODEL_ANSWER",
                        "provider": spec["display"],
                    },
                },
                "chunks": [
                    {
                        "chunk_id": spec["display"],
                        "content": answer_text,
                    }
                ],
                "source": "MODEL_ANSWER",
            }
        )
    return documents


def _collect_chunk_ids(documents: list[dict]) -> set[str]:
    chunk_ids: set[str] = set()
    for doc in documents:
        chunks = doc.get("chunks") if isinstance(doc, dict) else None
        if not isinstance(chunks, list):
            continue
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_id = chunk.get("chunk_id") or chunk.get("id")
            if chunk_id is None:
                continue
            chunk_ids.add(str(chunk_id))
    return chunk_ids


def _normalize_citations(text: str, valid_chunk_ids: set[str]) -> str:
    if not text or not valid_chunk_ids:
        return text

    def replace_match(match: re.Match) -> str:
        token = match.group(1).strip()
        if not token:
            return match.group(0)
        parts = [p.strip() for p in token.split(",") if p.strip()]
        if not parts:
            return match.group(0)
        if all(part in valid_chunk_ids for part in parts):
            return ", ".join([f"[citation:{part}]" for part in parts])
        return match.group(0)

    pattern = re.compile(r"\[(?!citation:)([^\]]+)\]")
    return pattern.sub(replace_match, text)


def _filter_invalid_citations(text: str, valid_chunk_ids: set[str]) -> str:
    if not text:
        return text

    pattern = re.compile(r"\[citation:([^\]]+)\]")

    def replace_match(match: re.Match) -> str:
        token = match.group(1).strip()
        if not token:
            return ""
        parts = [p.strip() for p in token.split(",") if p.strip()]
        valid_parts = [p for p in parts if p in valid_chunk_ids]
        if not valid_parts:
            return ""
        return ", ".join([f"[citation:{part}]" for part in valid_parts])

    return pattern.sub(replace_match, text)


async def _ingest_compare_outputs(
    connector_service: ConnectorService,
    provider_results: dict[str, dict],
    *,
    user_id: str | None,
    search_space_id: int,
    chat_id: int,
) -> list[dict]:
    documents: list[dict] = []
    for provider_key, result in provider_results.items():
        if not isinstance(result, dict):
            continue
        if result.get("status") != "success":
            continue
        response = result.get("response") or ""
        if not response:
            continue
        tool_payload = {
            "provider_key": provider_key,
            "provider": result.get("provider"),
            "model": result.get("model"),
            "model_display_name": result.get("model_display_name"),
            "response": response,
            "latency_ms": result.get("latency_ms"),
            "source": result.get("source"),
            "truncated": result.get("truncated"),
        }
        display_name = result.get("model_display_name") or provider_key
        title = f"Compare: {display_name} response"
        document = await connector_service.ingest_tool_output(
            tool_name="compare_model",
            tool_output=tool_payload,
            title=title,
            metadata={
                "compare_mode": True,
                "provider_key": provider_key,
                "provider": result.get("provider"),
                "model": result.get("model"),
                "model_display_name": result.get("model_display_name"),
                "source": "MODEL_ANSWER",
                "document_type": "MODEL_ANSWER",
            },
            user_id=user_id,
            origin_search_space_id=search_space_id,
            thread_id=chat_id,
        )
        if document:
            documents.append(
                connector_service._serialize_external_document(document, score=1.0)
            )
    return documents


async def _build_query_with_context(
    user_query: str,
    session: AsyncSession,
    search_space_id: int,
    attachments: list[ChatAttachment] | None,
    mentioned_document_ids: list[int] | None,
    mentioned_surfsense_doc_ids: list[int] | None,
) -> str:
    mentioned_documents: list[Document] = []
    if mentioned_document_ids:
        result = await session.execute(
            select(Document)
            .options(selectinload(Document.chunks))
            .filter(
                Document.id.in_(mentioned_document_ids),
                Document.search_space_id == search_space_id,
            )
        )
        mentioned_documents = list(result.scalars().all())

    mentioned_surfsense_docs: list[SurfsenseDocsDocument] = []
    if mentioned_surfsense_doc_ids:
        result = await session.execute(
            select(SurfsenseDocsDocument)
            .options(selectinload(SurfsenseDocsDocument.chunks))
            .filter(SurfsenseDocsDocument.id.in_(mentioned_surfsense_doc_ids))
        )
        mentioned_surfsense_docs = list(result.scalars().all())

    context_parts: list[str] = []
    if attachments:
        context_parts.append(format_attachments_as_context(attachments))
    if mentioned_documents:
        context_parts.append(format_mentioned_documents_as_context(mentioned_documents))
    if mentioned_surfsense_docs:
        context_parts.append(
            format_mentioned_surfsense_docs_as_context(mentioned_surfsense_docs)
        )

    if context_parts:
        context = "\n\n".join(context_parts)
        return f"{context}\n\n<user_query>{user_query}</user_query>"

    return user_query


async def stream_compare_chat(
    user_query: str,
    search_space_id: int,
    chat_id: int,
    session: AsyncSession,
    user_id: str | None = None,
    llm_config_id: int = -1,
    attachments: list[ChatAttachment] | None = None,
    mentioned_document_ids: list[int] | None = None,
    mentioned_surfsense_doc_ids: list[int] | None = None,
) -> AsyncGenerator[str, None]:
    streaming_service = VercelStreamingService()

    compare_query = extract_compare_query(user_query)
    if not compare_query:
        yield streaming_service.format_error(
            "Compare mode requires a question after /compare."
        )
        yield streaming_service.format_finish()
        yield streaming_service.format_done()
        return

    try:
        try:
            thread_result = await session.execute(
                select(NewChatThread).filter(NewChatThread.id == chat_id)
            )
            thread = thread_result.scalars().first()
            if thread and not thread.needs_history_bootstrap:
                thread.needs_history_bootstrap = True
                await session.commit()
        except Exception as exc:
            print(f"[compare] Failed to mark history bootstrap: {exc!s}")

        query_with_context = await _build_query_with_context(
            user_query=compare_query,
            session=session,
            search_space_id=search_space_id,
            attachments=attachments,
            mentioned_document_ids=mentioned_document_ids,
            mentioned_surfsense_doc_ids=mentioned_surfsense_doc_ids,
        )

        connector_service = ConnectorService(
            session, search_space_id=search_space_id, user_id=user_id
        )

        yield streaming_service.format_message_start()
        yield streaming_service.format_start_step()

        short_query = _truncate_text(compare_query, 80)

        provider_steps: dict[str, dict[str, str | list[str] | None]] = {}
        provider_errors: dict[str, str] = {}
        provider_summaries: dict[str, dict[str, str]] = {}
        provider_configs: dict[str, dict] = {}
        provider_tool_call_ids: dict[str, str] = {}
        provider_results: dict[str, dict] = {}
        spec_by_key = {spec.key: spec for spec in EXTERNAL_MODEL_SPECS}

        for spec in EXTERNAL_MODEL_SPECS:
            config = load_llm_config_from_yaml(spec.config_id)
            metadata = describe_external_model_config(config) if config else {}
            api_key_value = str(config.get("api_key") or "").strip() if config else ""

            if not config:
                provider_errors[spec.key] = (
                    f"Missing global config id {spec.config_id}"
                )
            elif not api_key_value:
                provider_errors[spec.key] = "Missing API key"
            else:
                provider_configs[spec.key] = config

            step_id = f"compare-{spec.key}-{uuid.uuid4().hex[:8]}"
            items: list[str] = []
            model_name = metadata.get("model_name") or ""
            provider_label = metadata.get("provider") or ""
            model_string = metadata.get("model_string") or ""
            api_base_value = metadata.get("api_base") or ""
            key_format = metadata.get("key_format") or ""
            if model_name:
                items.append(f"Model: {model_name}")
            if provider_label:
                items.append(f"Provider: {provider_label}")
            if api_base_value:
                items.append(f"API base: {api_base_value}")
            if api_key_value and key_format:
                items.append(f"Key format: {key_format}")
            if model_string:
                items.append(f"Model string: {model_string}")
            items.append(f"Tool: {spec.tool_name}")
            items.append(f"Query: {short_query}")

            provider_steps[spec.key] = {
                "id": step_id,
                "title": f"Asking {spec.display}",
                "items": items,
            }

            yield streaming_service.format_thinking_step(
                step_id=step_id,
                title=f"Asking {spec.display}",
                status="in_progress",
                items=items,
            )

            tool_call_id = streaming_service.generate_tool_call_id()
            provider_tool_call_ids[spec.key] = tool_call_id
            yield streaming_service.format_tool_input_start(
                tool_call_id, spec.tool_name
            )
            yield streaming_service.format_tool_input_available(
                tool_call_id,
                spec.tool_name,
                {"query": compare_query},
            )

            if spec.key in provider_errors:
                error_msg = provider_errors[spec.key]
                completed_items = [
                    *items,
                    f"Error: {_truncate_text(error_msg, 120)}",
                ]
                yield streaming_service.format_thinking_step(
                    step_id=step_id,
                    title=f"Asking {spec.display}",
                    status="completed",
                    items=completed_items,
                )
                error_result = {
                    "status": "error",
                    "error": error_msg,
                    "model_display_name": spec.display,
                    "provider": provider_label,
                    "model": model_name,
                    "model_string": model_string,
                    "api_base": api_base_value,
                    "source": metadata.get("source") or "",
                }
                yield streaming_service.format_tool_output_available(
                    tool_call_id, error_result
                )
                provider_summaries[spec.display] = {
                    "status": "error",
                    "error": _truncate_text(error_msg, 200),
                }

        answers: dict[str, str] = {}
        results_queue: asyncio.Queue[
            tuple[str, dict | None, Exception | None, float]
        ] = asyncio.Queue()
        tasks: list[asyncio.Task] = []

        async def run_call(spec_key: str, spec, config: dict) -> None:
            start_time = time.monotonic()
            try:
                result = await call_external_model(
                    spec=spec,
                    query=query_with_context,
                    timeout_seconds=COMPARE_TIMEOUT_SECONDS,
                    config=config,
                )
                await results_queue.put(
                    (spec_key, result, None, time.monotonic() - start_time)
                )
            except Exception as exc:
                await results_queue.put(
                    (spec_key, None, exc, time.monotonic() - start_time)
                )

        for spec in EXTERNAL_MODEL_SPECS:
            if spec.key not in provider_configs:
                continue
            tasks.append(
                asyncio.create_task(
                    run_call(spec.key, spec, provider_configs[spec.key])
                )
            )

        try:
            for _ in range(len(tasks)):
                provider_key, result, error, elapsed = await results_queue.get()
                spec = spec_by_key.get(provider_key)
                if spec is None:
                    continue
                step_info = provider_steps.get(provider_key, {})
                step_id = str(step_info.get("id"))
                title = str(step_info.get("title"))
                base_items = list(step_info.get("items") or [])
                tool_call_id = provider_tool_call_ids.get(provider_key, "")

                result_payload: dict[str, Any] = {}
                if error is None and isinstance(result, dict):
                    result_payload = result
                elif error is not None:
                    result_payload = {
                        "status": "error",
                        "error": str(error),
                        "model_display_name": spec.display,
                    }

                if tool_call_id:
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        result_payload
                        if result_payload
                        else {"status": "error", "error": "Empty response"},
                    )

                if result_payload.get("status") == "success":
                    response_text = result_payload.get("response") or ""
                    if not isinstance(response_text, str):
                        response_text = str(response_text)
                    if response_text:
                        answers[provider_key] = response_text
                        provider_results[provider_key] = result_payload
                        provider_summaries[spec.display] = {
                            "status": "success",
                            "answer": _truncate_text(
                                result_payload.get("summary") or response_text,
                                COMPARE_SUMMARY_ANSWER_CHARS,
                            ),
                        }
                        completed_items = [
                            *base_items,
                            f"Response length: {len(response_text)} chars",
                            f"Elapsed: {elapsed:.1f}s",
                        ]
                    else:
                        error_msg = "Empty response"
                        completed_items = [
                            *base_items,
                            f"Error: {_truncate_text(error_msg, 120)}",
                        ]
                        provider_summaries[spec.display] = {
                            "status": "error",
                            "error": _truncate_text(error_msg, 200),
                        }
                else:
                    error_msg = result_payload.get("error") or "Empty response"
                    completed_items = [
                        *base_items,
                        f"Error: {_truncate_text(error_msg, 120)}",
                    ]
                    provider_summaries[spec.display] = {
                        "status": "error",
                        "error": _truncate_text(str(error_msg), 200),
                    }

                yield streaming_service.format_thinking_step(
                    step_id=step_id,
                    title=title,
                    status="completed",
                    items=completed_items,
                )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        tavily_step_id = f"compare-tavily-{uuid.uuid4().hex[:8]}"
        yield streaming_service.format_thinking_step(
            step_id=tavily_step_id,
            title="Fetching latest sources",
            status="in_progress",
            items=[f"Query: {short_query}"],
        )

        _, tavily_documents = await connector_service.search_tavily(
            user_query=compare_query,
            search_space_id=search_space_id,
            top_k=MAX_TAVILY_RESULTS,
            user_id=user_id,
        )
        tavily_count = len(tavily_documents)
        yield streaming_service.format_thinking_step(
            step_id=tavily_step_id,
            title="Fetching latest sources",
            status="completed",
            items=[f"Tavily results: {tavily_count}"],
        )

        agent_config = await load_agent_config(
            session=session,
            config_id=llm_config_id,
            search_space_id=search_space_id,
        )
        if not agent_config:
            yield streaming_service.format_error("Failed to load local LLM configuration.")
            yield streaming_service.format_finish_step()
            yield streaming_service.format_finish()
            yield streaming_service.format_done()
            return

        local_llm = create_chat_litellm_from_agent_config(agent_config)
        if not local_llm:
            yield streaming_service.format_error("Failed to create local LLM instance.")
            yield streaming_service.format_finish_step()
            yield streaming_service.format_finish()
            yield streaming_service.format_done()
            return

        from app.db import SearchSourceConnectorType

        firecrawl_api_key = None
        webcrawler_connector = await connector_service.get_connector_by_type(
            SearchSourceConnectorType.WEBCRAWLER_CONNECTOR, search_space_id
        )
        if webcrawler_connector and webcrawler_connector.config:
            firecrawl_api_key = webcrawler_connector.config.get("FIRECRAWL_API_KEY")

        oneseek_checkpointer = MemorySaver()
        oneseek_agent = await create_surfsense_deep_agent(
            llm=local_llm,
            search_space_id=search_space_id,
            db_session=session,
            connector_service=connector_service,
            checkpointer=oneseek_checkpointer,
            user_id=user_id,
            thread_id=chat_id,
            agent_config=agent_config,
            firecrawl_api_key=firecrawl_api_key,
        )

        local_step_id = f"compare-oneseek-{uuid.uuid4().hex[:8]}"
        local_tool_call_id = streaming_service.generate_tool_call_id()
        local_model_name = str(agent_config.model_name or "")
        local_provider = str(agent_config.provider or "")
        local_api_base = str(agent_config.api_base or "")
        local_model_string = str(getattr(local_llm, "model", "") or "")
        local_items = [
            item
            for item in [
                f"Model: {local_model_name}" if local_model_name else None,
                f"Provider: {local_provider}" if local_provider else None,
                f"API base: {local_api_base}" if local_api_base else None,
                f"Model string: {local_model_string}" if local_model_string else None,
                "Tool: call_oneseek",
                f"Query: {short_query}",
            ]
            if item
        ]
        provider_steps["oneseek"] = {
            "id": local_step_id,
            "title": "Asking Oneseek",
            "items": local_items,
        }
        provider_tool_call_ids["oneseek"] = local_tool_call_id

        yield streaming_service.format_thinking_step(
            step_id=local_step_id,
            title="Asking Oneseek",
            status="in_progress",
            items=local_items,
        )
        yield streaming_service.format_tool_input_start(
            local_tool_call_id, "call_oneseek"
        )
        yield streaming_service.format_tool_input_available(
            local_tool_call_id, "call_oneseek", {"query": compare_query}
        )

        oneseek_start = time.monotonic()
        oneseek_error: str | None = None
        oneseek_text = ""
        oneseek_tool_steps: dict[str, str] = {}
        oneseek_tool_calls: dict[str, str] = {}

        input_state = {
            "messages": [HumanMessage(content=query_with_context)],
            "search_space_id": search_space_id,
        }
        config = {
            "configurable": {"thread_id": f"{chat_id}-compare-oneseek"},
            "recursion_limit": 80,
        }

        try:
            async for event in oneseek_agent.astream_events(
                input_state, config=config, version="v2"
            ):
                event_type = event.get("event", "")
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        content = chunk.content
                        if content and isinstance(content, str):
                            oneseek_text += content
                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown_tool")
                    run_id = event.get("run_id", "")
                    tool_input = event.get("data", {}).get("input", {})

                    tool_step_id = f"compare-oneseek-tool-{uuid.uuid4().hex[:8]}"
                    oneseek_tool_steps[run_id] = tool_step_id
                    tool_title = f"Using {tool_name.replace('_', ' ')}"
                    tool_items: list[str] = []
                    if isinstance(tool_input, dict):
                        for key in (
                            "query",
                            "location",
                            "url",
                            "origin",
                            "destination",
                            "record_id",
                            "podcast_title",
                        ):
                            if tool_input.get(key):
                                tool_items.append(
                                    f"{key.replace('_', ' ').title()}: {tool_input.get(key)}"
                                )
                                break
                    if not tool_items:
                        tool_items = [f"Tool: {tool_name}"]
                    yield streaming_service.format_thinking_step(
                        step_id=tool_step_id,
                        title=tool_title,
                        status="in_progress",
                        items=tool_items,
                    )

                    tool_call_id = (
                        f"call_{run_id[:32]}"
                        if run_id
                        else streaming_service.generate_tool_call_id()
                    )
                    oneseek_tool_calls[run_id] = tool_call_id
                    yield streaming_service.format_tool_input_start(
                        tool_call_id, tool_name
                    )
                    yield streaming_service.format_tool_input_available(
                        tool_call_id,
                        tool_name,
                        tool_input if isinstance(tool_input, dict) else {"input": tool_input},
                    )
                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown_tool")
                    run_id = event.get("run_id", "")
                    raw_output = event.get("data", {}).get("output")
                    tool_output = raw_output
                    if hasattr(raw_output, "content"):
                        content = raw_output.content
                        if isinstance(content, str):
                            try:
                                tool_output = json.loads(content)
                            except Exception:
                                tool_output = {"result": content}
                        else:
                            tool_output = content
                    elif isinstance(raw_output, str):
                        try:
                            tool_output = json.loads(raw_output)
                        except Exception:
                            tool_output = {"result": raw_output}
                    elif raw_output is None:
                        tool_output = {"result": "No output"}

                    tool_call_id = oneseek_tool_calls.get(run_id) or (
                        f"call_{run_id[:32]}"
                        if run_id
                        else streaming_service.generate_tool_call_id()
                    )
                    yield streaming_service.format_tool_output_available(
                        tool_call_id,
                        tool_output if isinstance(tool_output, dict) else {"result": tool_output},
                    )

                    tool_step_id = oneseek_tool_steps.get(run_id)
                    if tool_step_id:
                        yield streaming_service.format_thinking_step(
                            step_id=tool_step_id,
                            title=f"Using {tool_name.replace('_', ' ')}",
                            status="completed",
                            items=[f"Completed: {tool_name.replace('_', ' ')}"],
                        )
        except Exception as exc:
            oneseek_error = str(exc)

        oneseek_elapsed = time.monotonic() - oneseek_start
        if oneseek_error or not oneseek_text.strip():
            error_msg = oneseek_error or "Empty response"
            provider_summaries["Oneseek"] = {
                "status": "error",
                "error": _truncate_text(error_msg, 200),
            }
            yield streaming_service.format_tool_output_available(
                local_tool_call_id,
                {
                    "status": "error",
                    "error": error_msg,
                    "model_display_name": "Oneseek",
                    "provider": local_provider,
                    "model": local_model_name,
                    "model_string": local_model_string,
                    "api_base": local_api_base,
                    "source": "Oneseek",
                    "latency_ms": int(oneseek_elapsed * 1000),
                },
            )
            completed_items = [
                *local_items,
                f"Error: {_truncate_text(error_msg, 120)}",
            ]
        else:
            oneseek_text = oneseek_text.strip()
            was_truncated = len(oneseek_text) > COMPARE_RAW_ANSWER_CHARS
            oneseek_text = _truncate_text(oneseek_text, COMPARE_RAW_ANSWER_CHARS)
            answers["oneseek"] = oneseek_text
            provider_results["oneseek"] = {
                "status": "success",
                "model_display_name": "Oneseek",
                "provider": local_provider,
                "model": local_model_name,
                "model_string": local_model_string,
                "api_base": local_api_base,
                "source": "Oneseek",
                "latency_ms": int(oneseek_elapsed * 1000),
                "usage": None,
                "summary": _truncate_text(oneseek_text, COMPARE_SUMMARY_ANSWER_CHARS),
                "response": oneseek_text,
                "truncated": was_truncated,
            }
            provider_summaries["Oneseek"] = {
                "status": "success",
                "answer": _truncate_text(oneseek_text, COMPARE_SUMMARY_ANSWER_CHARS),
            }
            yield streaming_service.format_tool_output_available(
                local_tool_call_id, provider_results["oneseek"]
            )
            completed_items = [
                *local_items,
                f"Response length: {len(oneseek_text)} chars",
                f"Elapsed: {oneseek_elapsed:.1f}s",
            ]

        yield streaming_service.format_thinking_step(
            step_id=local_step_id,
            title="Asking Oneseek",
            status="completed",
            items=completed_items,
        )

        model_output_documents: list[dict] = []
        try:
            model_output_documents = await _ingest_compare_outputs(
                connector_service,
                provider_results,
                user_id=user_id,
                search_space_id=search_space_id,
                chat_id=chat_id,
            )
        except Exception as exc:
            print(f"[compare] Failed to ingest model outputs: {exc!s}")

        _, tavily_documents = await connector_service.search_tavily(
            user_query=compare_query,
            search_space_id=search_space_id,
            top_k=MAX_TAVILY_RESULTS,
            user_id=user_id,
        )

        if not answers:
            yield streaming_service.format_error(
                "Compare mode failed: no model answers were retrieved."
            )
            yield streaming_service.format_finish_step()
            yield streaming_service.format_finish()
            yield streaming_service.format_done()
            return

        analysis_step_id = f"compare-analysis-{uuid.uuid4().hex[:8]}"
        total_models = len(EXTERNAL_MODEL_SPECS) + 1
        analysis_items = [f"Responses received: {len(answers)}/{total_models}"]

        yield streaming_service.format_thinking_step(
            step_id=analysis_step_id,
            title="Analyzing and validating responses",
            status="in_progress",
            items=analysis_items,
        )

        if tavily_documents:
            analysis_items.append(f"Tavily results: {len(tavily_documents)}")
        else:
            analysis_items.append("Tavily results: 0")

        compare_specs = [
            *[
                {"key": spec.key, "display": spec.display, "tool": spec.tool_name}
                for spec in EXTERNAL_MODEL_SPECS
            ],
            {"key": "oneseek", "display": "Oneseek", "tool": "call_oneseek"},
        ]

        answers_block = "\n".join(
            [
                (
                    f"<answer model='{spec['display']}' tool='{spec['tool']}' "
                    f"provider='{result.get('provider', '')}' "
                    f"model_name='{result.get('model', '')}' "
                    f"latency_ms='{result.get('latency_ms', '')}' "
                    f"source='{result.get('source', '')}'>\n"
                    f"{result.get('response', '')}\n</answer>"
                )
                for spec in compare_specs
                if (result := provider_results.get(spec["key"]))
            ]
        )

        model_answer_documents = (
            model_output_documents
            if model_output_documents
            else _build_model_answer_documents(
                provider_results,
                specs=[
                    {"key": spec["key"], "display": spec["display"]}
                    for spec in compare_specs
                ],
            )
        )
        source_documents = [*model_answer_documents, *tavily_documents]
        sources_context = (
            format_documents_for_context(source_documents)
            if source_documents
            else ""
        )
        valid_chunk_ids = _collect_chunk_ids(source_documents)

        prompt_parts = [
            f"<user_query>\n{query_with_context}\n</user_query>",
            "<external_answers>",
            answers_block,
            "</external_answers>",
            "<sources>",
            sources_context or "None",
            "</sources>",
        ]

        analysis_prompt = "\n".join(prompt_parts)

        try:
            local_response = await local_llm.ainvoke(
                [
                    SystemMessage(
                        content=f"{LOCAL_ANALYSIS_SYSTEM_PROMPT}\n\n{COMPARE_CITATION_INSTRUCTIONS}"
                    ),
                    HumanMessage(content=analysis_prompt),
                ]
            )
            final_answer = str(getattr(local_response, "content", "") or "").strip()
        except Exception as exc:
            analysis_items.append(
                f"Error: {_truncate_text(str(exc), 120)}"
            )
            yield streaming_service.format_thinking_step(
                step_id=analysis_step_id,
                title="Analyzing and validating responses",
                status="completed",
                items=analysis_items,
            )
            yield streaming_service.format_error(
                "Failed to generate the final answer."
            )
            yield streaming_service.format_finish_step()
            yield streaming_service.format_finish()
            yield streaming_service.format_done()
            return
        if not final_answer:
            final_answer = "I could not generate a response."
        else:
            final_answer = _normalize_citations(final_answer, valid_chunk_ids)
            final_answer = _filter_invalid_citations(final_answer, valid_chunk_ids)

        try:
            await connector_service.ingest_tool_output(
                tool_name="compare_summary",
                tool_output={
                    "query": compare_query,
                    "final_answer": final_answer,
                    "providers": provider_summaries,
                },
                title="Compare: synthesized answer",
                metadata={"compare_mode": True, "type": "summary"},
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=chat_id,
            )
        except Exception as exc:
            print(f"[compare] Failed to ingest summary: {exc!s}")

        analysis_items.append(f"Final answer length: {len(final_answer)} chars")
        yield streaming_service.format_thinking_step(
            step_id=analysis_step_id,
            title="Analyzing and validating responses",
            status="completed",
            items=analysis_items,
        )

        compare_summary = _build_compare_summary(
            query=compare_query,
            provider_summaries=provider_summaries,
            final_answer=final_answer,
        )
        yield streaming_service.format_data("compare-summary", compare_summary)

        text_id = streaming_service.generate_text_id()
        yield streaming_service.format_text_start(text_id)
        for part in streaming_service.stream_text(text_id, final_answer, chunk_size=24):
            yield part
        yield streaming_service.format_text_end(text_id)

        yield streaming_service.format_finish_step()
        yield streaming_service.format_finish()
        yield streaming_service.format_done()

    except Exception as exc:
        yield streaming_service.format_error(f"Error during compare mode: {exc!s}")
        yield streaming_service.format_finish_step()
        yield streaming_service.format_finish()
        yield streaming_service.format_done()
