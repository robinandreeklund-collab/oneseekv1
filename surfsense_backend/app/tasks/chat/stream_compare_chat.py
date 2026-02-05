"""
Streaming task for SurfSense compare mode.

Compare mode runs the same query across multiple external LLMs in parallel,
streams thinking steps for each call, then synthesizes an optimized answer
using a local LLM and Tavily.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.agents.new_chat.llm_config import (
    PROVIDER_MAP,
    create_chat_litellm_from_agent_config,
    create_chat_litellm_from_config,
    load_agent_config,
    load_llm_config_from_yaml,
)
import litellm
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
MAX_EXTERNAL_ANSWER_CHARS = 8000
MAX_TAVILY_RESULTS = 6
COMPARE_SUMMARY_ANSWER_CHARS = 600
COMPARE_SUMMARY_FINAL_CHARS = 700

COMPARE_MODELS = [
    {"key": "grok", "display": "Grok", "config_id": -20},
    {"key": "deepseek", "display": "DeepSeek", "config_id": -21},
    {"key": "gemini", "display": "Gemini", "config_id": -22},
    {"key": "chatgpt", "display": "ChatGPT", "config_id": -23},
]

EXTERNAL_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question clearly and concisely."
)

LOCAL_ANALYSIS_SYSTEM_PROMPT = (
    "You are SurfSense Compare Analyzer. You will receive the user query, multiple "
    "draft answers from external models, and Tavily web snippets. Your task is to "
    "evaluate correctness, resolve conflicts, fill gaps, and produce a high-quality "
    "optimized response. Use your own knowledge where appropriate. If information "
    "is uncertain or conflicting, mention the uncertainty. Respond in the same "
    "language as the user. Do not mention model names or that you compared multiple "
    "models unless the user explicitly asks."
)

COMPARE_CITATION_INSTRUCTIONS = (
    "When using information from the <sources> section, include citations in the "
    "format [citation:chunk_id] using chunk ids from <chunk id='...'> tags. "
    "MODEL_ANSWER documents represent other model outputs; only cite them when "
    "explicitly referencing those outputs. Prefer Tavily sources for factual claims."
)


def _describe_key_format(api_key: str) -> str:
    key = api_key.strip()
    if key.startswith("xai-"):
        return "xAI"
    if key.startswith("AIza"):
        return "Google AI Studio"
    if key.startswith("sk-or-"):
        return "OpenRouter"
    if key.startswith("sk-ant-"):
        return "Anthropic"
    if key.startswith("sk-"):
        return "OpenAI-like"
    return "Unknown"


def _apply_provider_env(provider: str, api_key: str) -> None:
    provider_key = provider.strip().upper()
    if not api_key:
        return
    if provider_key == "XAI":
        os.environ.setdefault("XAI_API_KEY", api_key)
    elif provider_key == "DEEPSEEK":
        os.environ.setdefault("DEEPSEEK_API_KEY", api_key)
    elif provider_key == "GOOGLE":
        os.environ.setdefault("GEMINI_API_KEY", api_key)
        os.environ.setdefault("GOOGLE_API_KEY", api_key)
    elif provider_key == "OPENROUTER":
        os.environ.setdefault("OPENROUTER_API_KEY", api_key)
    elif provider_key == "OPENAI":
        os.environ.setdefault("OPENAI_API_KEY", api_key)


def _build_model_string(config: dict) -> str:
    if config.get("custom_provider"):
        return f"{config['custom_provider']}/{config['model_name']}"
    provider = str(config.get("provider") or "").upper()
    provider_prefix = PROVIDER_MAP.get(provider, provider.lower())
    return f"{provider_prefix}/{config['model_name']}"


async def _call_external_llm_with_litellm(
    config: dict,
    query: str,
    timeout_seconds: int,
) -> str:
    model_string = _build_model_string(config)
    api_key = str(config.get("api_key") or "").strip()
    api_base = str(config.get("api_base") or "").strip()
    litellm_params = config.get("litellm_params") or {}

    async def _run():
        response = await litellm.acompletion(
            model=model_string,
            messages=[
                {"role": "system", "content": EXTERNAL_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            api_key=api_key,
            api_base=api_base or None,
            **litellm_params,
        )
        message = response.choices[0].message
        if hasattr(message, "content"):
            return str(message.content or "").strip()
        return str(message.get("content", "")).strip()

    return await asyncio.wait_for(_run(), timeout=timeout_seconds)


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


def _build_model_answer_documents(answers: dict[str, str]) -> list[dict]:
    documents: list[dict] = []
    for provider in COMPARE_MODELS:
        provider_key = provider["key"]
        if provider_key not in answers:
            continue
        answer_text = _truncate_text(
            answers[provider_key], COMPARE_SUMMARY_ANSWER_CHARS
        )
        if not answer_text:
            continue
        documents.append(
            {
                "document": {
                    "id": f"model-{provider_key}",
                    "title": f"{provider['display']} response",
                    "document_type": "MODEL_ANSWER",
                    "metadata": {
                        "source": "MODEL_ANSWER",
                        "provider": provider["display"],
                    },
                },
                "chunks": [
                    {
                        "chunk_id": f"model-{provider_key}-1",
                        "content": answer_text,
                    }
                ],
                "source": "MODEL_ANSWER",
            }
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


async def _call_external_llm(
    llm,
    query: str,
    timeout_seconds: int,
) -> str:
    response = await asyncio.wait_for(
        llm.ainvoke(
            [
                SystemMessage(content=EXTERNAL_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ]
        ),
        timeout=timeout_seconds,
    )
    content = getattr(response, "content", None)
    if content is None:
        return ""
    return str(content).strip()


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

        connector_service = ConnectorService(session, search_space_id=search_space_id)

        yield streaming_service.format_message_start()
        yield streaming_service.format_start_step()

        short_query = _truncate_text(compare_query, 80)

        provider_steps: dict[str, dict[str, str | list[str] | None]] = {}
        provider_errors: dict[str, str] = {}
        provider_summaries: dict[str, dict[str, str]] = {}
        provider_llms: dict[str, object] = {}
        provider_model_strings: dict[str, str] = {}
        provider_configs: dict[str, dict] = {}
        provider_labels: dict[str, str] = {}

        for provider in COMPARE_MODELS:
            config = load_llm_config_from_yaml(provider["config_id"])
            display = provider["display"]
            model_name = ""
            if not config:
                provider_errors[provider["key"]] = (
                    f"Missing global config id {provider['config_id']}"
                )
            else:
                model_name = str(config.get("model_name") or "")
                api_key = str(config.get("api_key") or "").strip()
                if not api_key:
                    provider_errors[provider["key"]] = "Missing API key"
                else:
                    provider_label = str(config.get("provider") or "").strip()
                    if provider_label:
                        _apply_provider_env(provider_label, api_key)
                        provider_labels[provider["key"]] = provider_label
                    provider_configs[provider["key"]] = config
                    llm = create_chat_litellm_from_config(config)
                    if llm is None:
                        provider_errors[provider["key"]] = "Failed to initialize model"
                    else:
                        provider_llms[provider["key"]] = llm
                        model_string = str(getattr(llm, "model", "") or "").strip()
                        if model_string:
                            provider_model_strings[provider["key"]] = model_string

            step_id = f"compare-{provider['key']}-{uuid.uuid4().hex[:8]}"
            items: list[str] = []
            if model_name:
                items.append(f"Model: {model_name}")
            if config:
                provider_label = provider_labels.get(provider["key"], "").strip()
                if provider_label:
                    items.append(f"Provider: {provider_label}")
                api_base_value = config.get("api_base")
                if api_base_value:
                    items.append(f"API base: {api_base_value}")
                api_key_value = str(config.get("api_key") or "").strip()
                if api_key_value:
                    items.append(f"Key format: {_describe_key_format(api_key_value)}")
                model_string = provider_model_strings.get(provider["key"], "")
                if model_string:
                    items.append(f"Model string: {model_string}")
            items.append(f"Query: {short_query}")
            provider_steps[provider["key"]] = {
                "id": step_id,
                "title": f"Asking {display}",
                "items": items,
            }

            yield streaming_service.format_thinking_step(
                step_id=step_id,
                title=f"Asking {display}",
                status="in_progress",
                items=items,
            )

            if provider["key"] not in provider_llms:
                error_msg = provider_errors.get(provider["key"], "Unavailable")
                completed_items = [
                    *items,
                    f"Error: {_truncate_text(error_msg, 120)}",
                ]
                yield streaming_service.format_thinking_step(
                    step_id=step_id,
                    title=f"Asking {display}",
                    status="completed",
                    items=completed_items,
                )
                provider_summaries[provider["key"]] = {
                    "status": "error",
                    "error": _truncate_text(error_msg, 200),
                }

        answers: dict[str, str] = {}
        results_queue: asyncio.Queue[
            tuple[str, str | None, Exception | None, float]
        ] = asyncio.Queue()
        tasks: list[asyncio.Task] = []

        async def run_call(provider_key: str, llm) -> None:
            start_time = time.monotonic()
            try:
                provider_label = provider_labels.get(provider_key, "").upper()
                if provider_label == "DEEPSEEK" and provider_key in provider_configs:
                    result = await _call_external_llm_with_litellm(
                        provider_configs[provider_key],
                        query_with_context,
                        COMPARE_TIMEOUT_SECONDS,
                    )
                else:
                    result = await _call_external_llm(
                        llm, query_with_context, COMPARE_TIMEOUT_SECONDS
                    )
                await results_queue.put(
                    (provider_key, result, None, time.monotonic() - start_time)
                )
            except Exception as exc:
                await results_queue.put(
                    (provider_key, None, exc, time.monotonic() - start_time)
                )

        for provider_key, llm in provider_llms.items():
            tasks.append(asyncio.create_task(run_call(provider_key, llm)))

        try:
            for _ in range(len(tasks)):
                provider_key, result, error, elapsed = await results_queue.get()
                step_info = provider_steps.get(provider_key, {})
                step_id = str(step_info.get("id"))
                title = str(step_info.get("title"))
                base_items = list(step_info.get("items") or [])

                if error is None and result:
                    result = result.strip()
                    if not result:
                        error = RuntimeError("Empty response")
                    else:
                        answers[provider_key] = _truncate_text(
                            result, MAX_EXTERNAL_ANSWER_CHARS
                        )
                        provider_summaries[provider_key] = {
                            "status": "success",
                            "answer": _truncate_text(
                                result, COMPARE_SUMMARY_ANSWER_CHARS
                            ),
                        }
                        completed_items = [
                            *base_items,
                            f"Response length: {len(result)} chars",
                            f"Elapsed: {elapsed:.1f}s",
                        ]
                if error is not None or not result:
                    error_msg = str(error) if error else "Empty response"
                    completed_items = [
                        *base_items,
                        f"Error: {_truncate_text(error_msg, 120)}",
                    ]
                    provider_summaries[provider_key] = {
                        "status": "error",
                        "error": _truncate_text(error_msg, 200),
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

        if not answers:
            yield streaming_service.format_error(
                "Compare mode failed: no external answers were retrieved."
            )
            yield streaming_service.format_finish_step()
            yield streaming_service.format_finish()
            yield streaming_service.format_done()
            return

        analysis_step_id = f"compare-analysis-{uuid.uuid4().hex[:8]}"
        analysis_items = [
            f"Responses received: {len(answers)}/{len(COMPARE_MODELS)}"
        ]

        yield streaming_service.format_thinking_step(
            step_id=analysis_step_id,
            title="Analyzing and validating responses",
            status="in_progress",
            items=analysis_items,
        )

        _, tavily_documents = await connector_service.search_tavily(
            user_query=compare_query,
            search_space_id=search_space_id,
            top_k=MAX_TAVILY_RESULTS,
        )
        if tavily_documents:
            analysis_items.append(f"Tavily results: {len(tavily_documents)}")
        else:
            analysis_items.append("Tavily results: 0")

        agent_config = await load_agent_config(
            session=session,
            config_id=llm_config_id,
            search_space_id=search_space_id,
        )
        if not agent_config:
            analysis_items.append("Error: Failed to load local LLM configuration")
            yield streaming_service.format_thinking_step(
                step_id=analysis_step_id,
                title="Analyzing and validating responses",
                status="completed",
                items=analysis_items,
            )
            yield streaming_service.format_error("Failed to load local LLM configuration.")
            yield streaming_service.format_finish_step()
            yield streaming_service.format_finish()
            yield streaming_service.format_done()
            return

        local_llm = create_chat_litellm_from_agent_config(agent_config)
        if not local_llm:
            analysis_items.append("Error: Failed to create local LLM instance")
            yield streaming_service.format_thinking_step(
                step_id=analysis_step_id,
                title="Analyzing and validating responses",
                status="completed",
                items=analysis_items,
            )
            yield streaming_service.format_error("Failed to create local LLM instance.")
            yield streaming_service.format_finish_step()
            yield streaming_service.format_finish()
            yield streaming_service.format_done()
            return

        answers_block = "\n".join(
            [
                f"<answer provider='{provider['key']}'>\n{answers[provider['key']]}\n</answer>"
                for provider in COMPARE_MODELS
                if provider["key"] in answers
            ]
        )

        model_answer_documents = _build_model_answer_documents(answers)
        source_documents = [*model_answer_documents, *tavily_documents]
        sources_context = (
            format_documents_for_context(source_documents)
            if source_documents
            else ""
        )

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
