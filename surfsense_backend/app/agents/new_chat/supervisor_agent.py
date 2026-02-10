from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.types import Checkpointer
from langgraph_bigtool.graph import END, StateGraph, ToolNode, RunnableCallable
from langgraph_bigtool.tools import InjectedState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.bigtool_store import _tokenize, _normalize_text
from app.agents.new_chat.bigtool_workers import WorkerConfig, create_bigtool_worker
from app.agents.new_chat.statistics_prompts import build_statistics_system_prompt
from app.agents.new_chat.tools.external_models import (
    DEFAULT_EXTERNAL_SYSTEM_PROMPT,
    EXTERNAL_MODEL_SPECS,
    call_external_model,
)
from app.agents.new_chat.tools.reflect_on_progress import create_reflect_on_progress_tool
from app.agents.new_chat.tools.write_todos import create_write_todos_tool
from app.db import AgentComboCache
from app.services.reranker_service import RerankerService


_AGENT_CACHE_TTL = timedelta(minutes=20)
_AGENT_COMBO_CACHE: dict[str, tuple[datetime, list[str]]] = {}
_AGENT_STOPWORDS = {
    "hur",
    "vad",
    "var",
    "när",
    "nar",
    "är",
    "ar",
    "och",
    "eller",
    "för",
    "for",
    "till",
    "fran",
    "från",
    "en",
    "ett",
    "i",
    "på",
    "pa",
    "av",
    "med",
    "som",
    "om",
    "den",
    "det",
    "de",
}
_EXTERNAL_MODEL_TOOL_NAMES = {spec.tool_name for spec in EXTERNAL_MODEL_SPECS}
_AGENT_EMBED_CACHE: dict[str, list[float]] = {}
AGENT_RERANK_CANDIDATES = 6
AGENT_EMBEDDING_WEIGHT = 4.0


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    keywords: list[str]
    namespace: tuple[str, ...]
    prompt_key: str


def _score_agent(definition: AgentDefinition, query_norm: str, tokens: set[str]) -> int:
    score = 0
    name_norm = _normalize_text(definition.name)
    desc_norm = _normalize_text(definition.description)
    if name_norm and name_norm in query_norm:
        score += 4
    for keyword in definition.keywords:
        if _normalize_text(keyword) in query_norm:
            score += 3
    for token in tokens:
        if token and token in desc_norm:
            score += 1
    return score


def _normalize_vector(vector: Any) -> list[float] | None:
    if vector is None:
        return None
    if isinstance(vector, list):
        return vector
    try:
        return [float(value) for value in vector]
    except Exception:
        return None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for a, b in zip(left, right):
        dot += a * b
        norm_left += a * a
        norm_right += b * b
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / ((norm_left**0.5) * (norm_right**0.5))


def _build_agent_rerank_text(definition: AgentDefinition) -> str:
    parts: list[str] = []
    if definition.name:
        parts.append(definition.name)
    if definition.description:
        parts.append(definition.description)
    if definition.keywords:
        parts.append("Keywords: " + ", ".join(definition.keywords))
    return "\n".join(part for part in parts if part)


def _get_agent_embedding(definition: AgentDefinition) -> list[float] | None:
    cached = _AGENT_EMBED_CACHE.get(definition.name)
    if cached is not None:
        return cached
    text = _build_agent_rerank_text(definition)
    if not text:
        return None
    try:
        from app.config import config

        embedding = config.embedding_model_instance.embed(text)
    except Exception:
        return None
    normalized = _normalize_vector(embedding)
    if normalized is None:
        return None
    _AGENT_EMBED_CACHE[definition.name] = normalized
    return normalized


def _rerank_agents(
    query: str,
    *,
    candidates: list[AgentDefinition],
    scores_by_name: dict[str, float],
) -> list[AgentDefinition]:
    if len(candidates) <= 1:
        return candidates
    reranker = RerankerService.get_reranker_instance()
    if not reranker:
        return candidates
    documents: list[dict[str, Any]] = []
    for agent in candidates:
        content = _build_agent_rerank_text(agent) or agent.name
        documents.append(
            {
                "document_id": agent.name,
                "content": content,
                "score": float(scores_by_name.get(agent.name, 0.0)),
                "document": {
                    "id": agent.name,
                    "title": agent.name,
                    "document_type": "AGENT",
                },
            }
        )
    reranked = reranker.rerank_documents(query, documents)
    if not reranked:
        return candidates
    reranked_names = [
        str(doc.get("document_id"))
        for doc in reranked
        if doc.get("document_id")
    ]
    by_name = {agent.name: agent for agent in candidates}
    ordered: list[AgentDefinition] = []
    seen: set[str] = set()
    for name in reranked_names:
        if name in by_name and name not in seen:
            ordered.append(by_name[name])
            seen.add(name)
    for agent in candidates:
        if agent.name not in seen:
            ordered.append(agent)
            seen.add(agent.name)
    return ordered


def _smart_retrieve_agents(
    query: str,
    *,
    agent_definitions: list[AgentDefinition],
    recent_agents: list[str] | None = None,
    limit: int = 3,
) -> list[AgentDefinition]:
    query_norm = _normalize_text(query)
    tokens = set(_tokenize(query_norm))
    query_embedding: list[float] | None = None
    if query:
        try:
            from app.config import config

            query_embedding = _normalize_vector(
                config.embedding_model_instance.embed(query)
            )
        except Exception:
            query_embedding = None
    recent_agents = [agent for agent in (recent_agents or []) if agent]
    scored: list[tuple[AgentDefinition, float]] = []
    scores_by_name: dict[str, float] = {}
    for definition in agent_definitions:
        base_score = float(_score_agent(definition, query_norm, tokens))
        semantic_score = 0.0
        if query_embedding:
            agent_embedding = _get_agent_embedding(definition)
            if agent_embedding:
                semantic_score = _cosine_similarity(query_embedding, agent_embedding)
        total_score = base_score + (semantic_score * AGENT_EMBEDDING_WEIGHT)
        scored.append((definition, total_score))
        scores_by_name[definition.name] = total_score
    if recent_agents:
        for idx, (definition, score) in enumerate(scored):
            if definition.name in recent_agents:
                scored[idx] = (definition, score + 4)
                scores_by_name[definition.name] = score + 4
    scored.sort(key=lambda item: item[1], reverse=True)
    candidates = [definition for definition, _ in scored[:AGENT_RERANK_CANDIDATES]]
    reranked = _rerank_agents(
        query, candidates=candidates, scores_by_name=scores_by_name
    )
    return reranked[:limit]


def _build_cache_key(
    query: str,
    route_hint: str | None,
    recent_agents: list[str] | None,
) -> tuple[str, str]:
    tokens = [
        token
        for token in _tokenize(query)
        if token and token not in _AGENT_STOPWORDS
    ]
    token_slice = " ".join(tokens[:6])
    recent_slice = ",".join((recent_agents or [])[-2:])
    pattern = f"{route_hint or 'none'}|{recent_slice}|{token_slice}"
    key = hashlib.sha256(pattern.encode("utf-8")).hexdigest()
    return key, pattern


def _get_cached_combo(cache_key: str) -> list[str] | None:
    entry = _AGENT_COMBO_CACHE.get(cache_key)
    if not entry:
        return None
    expires_at, agents = entry
    if expires_at < datetime.now(UTC):
        _AGENT_COMBO_CACHE.pop(cache_key, None)
        return None
    return agents


def _set_cached_combo(cache_key: str, agents: list[str]) -> None:
    _AGENT_COMBO_CACHE[cache_key] = (datetime.now(UTC) + _AGENT_CACHE_TTL, agents)


async def _fetch_cached_combo_db(
    session: AsyncSession | None, cache_key: str
) -> list[str] | None:
    if session is None:
        return None
    result = await session.execute(
        select(AgentComboCache).where(AgentComboCache.cache_key == cache_key)
    )
    row = result.scalars().first()
    if not row:
        return None
    agents = row.agents if isinstance(row.agents, list) else []
    row.hit_count = int(row.hit_count or 0) + 1
    row.last_used_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return [str(agent) for agent in agents if agent]


async def _store_cached_combo_db(
    session: AsyncSession | None,
    *,
    cache_key: str,
    route_hint: str | None,
    pattern: str,
    recent_agents: list[str],
    agents: list[str],
) -> None:
    if session is None:
        return
    result = await session.execute(
        select(AgentComboCache).where(AgentComboCache.cache_key == cache_key)
    )
    row = result.scalars().first()
    if row:
        row.agents = agents
        row.recent_agents = recent_agents
        row.route_hint = route_hint
        row.pattern = pattern
        row.updated_at = datetime.now(UTC)
        row.last_used_at = datetime.now(UTC)
    else:
        row = AgentComboCache(
            cache_key=cache_key,
            route_hint=route_hint,
            pattern=pattern,
            recent_agents=recent_agents,
            agents=agents,
            hit_count=0,
            last_used_at=datetime.now(UTC),
        )
        session.add(row)
    await session.commit()


def _replace(left: Any, right: Any) -> Any:
    return right if right is not None else left


def _append_recent(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged = list(left or [])
    merged.extend(right or [])
    return merged[-3:]


def _append_compare_outputs(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in left or []:
        tool_call_id = str(item.get("tool_call_id") or "")
        if tool_call_id:
            merged[tool_call_id] = item
    for item in right or []:
        tool_call_id = str(item.get("tool_call_id") or "")
        if tool_call_id:
            merged[tool_call_id] = item
    return list(merged.values())


def _format_compare_outputs_for_prompt(compare_outputs: list[dict[str, Any]] | None) -> str:
    if not compare_outputs:
        return ""
    blocks: list[str] = []
    for output in compare_outputs:
        model_name = (
            output.get("model_display_name")
            or output.get("model")
            or output.get("tool_name")
            or "Model"
        )
        response = output.get("response") or ""
        if not isinstance(response, str):
            response = str(response)
        response = response.strip()
        if not response:
            continue
        citation_ids = output.get("citation_chunk_ids") or []
        if isinstance(citation_ids, str):
            citation_ids = [citation_ids]
        citation_hint = ", ".join([str(cid) for cid in citation_ids if cid])
        cite_note = (
            f" (citation_ids: {citation_hint})" if citation_hint else ""
        )
        blocks.append(f"MODEL_ANSWER ({model_name}){cite_note}:\n{response}")
    if not blocks:
        return ""
    return "<compare_outputs>\n" + "\n\n".join(blocks) + "\n</compare_outputs>"


class SupervisorState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    active_plan: Annotated[list[dict[str, Any]], _replace]
    plan_complete: Annotated[bool, _replace]
    recent_agent_calls: Annotated[list[dict[str, Any]], _append_recent]
    route_hint: Annotated[str | None, _replace]
    compare_outputs: Annotated[list[dict[str, Any]], _append_compare_outputs]


def _format_plan_context(state: dict[str, Any]) -> str | None:
    plan = state.get("active_plan") or []
    if not plan:
        return None
    status = "complete" if state.get("plan_complete") else "active"
    lines = []
    for item in plan:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        step_status = str(item.get("status") or "pending").lower()
        lines.append(f"- [{step_status}] {content}")
    if not lines:
        return None
    return f"<active_plan status=\"{status}\">\n" + "\n".join(lines) + "\n</active_plan>"


def _format_recent_calls(state: dict[str, Any]) -> str | None:
    recent_calls = state.get("recent_agent_calls") or []
    if not recent_calls:
        return None
    lines = []
    for call in recent_calls[-3:]:
        agent = call.get("agent")
        task = call.get("task")
        response = call.get("response") or ""
        if response and len(response) > 180:
            response = response[:177] + "..."
        lines.append(f"- {agent}: {task} → {response}")
    if not lines:
        return None
    return "<recent_agent_calls>\n" + "\n".join(lines) + "\n</recent_agent_calls>"


def _format_route_hint(state: dict[str, Any]) -> str | None:
    hint = state.get("route_hint")
    if not hint:
        return None
    return f"<route_hint>{hint}</route_hint>"




def _safe_json(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return {}


def _sanitize_messages(messages: list[Any]) -> list[Any]:
    sanitized: list[Any] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            payload = _safe_json(message.content)
            if payload:
                response = payload.get("response")
                if isinstance(response, str):
                    agent = payload.get("agent") or message.name or "agent"
                    content = f"{agent}: {response}" if response else f"{agent}: completed"
                    sanitized.append(
                        ToolMessage(
                            content=content,
                            name=message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                if payload.get("status") and payload.get("reason"):
                    tool_name = message.name or "tool"
                    sanitized.append(
                        ToolMessage(
                            content=f"{tool_name}: completed",
                            name=message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
            if isinstance(message.content, str) and "{\"status\"" in message.content:
                trimmed = message.content.split("{\"status\"", 1)[0].rstrip()
                if trimmed:
                    sanitized.append(
                        ToolMessage(
                            content=trimmed,
                            name=message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                else:
                    sanitized.append(
                        ToolMessage(
                            content=f"{message.name or 'tool'}: completed",
                            name=message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                continue
        sanitized.append(message)
    return sanitized


async def create_supervisor_agent(
    *,
    llm,
    dependencies: dict[str, Any],
    checkpointer: Checkpointer | None,
    knowledge_prompt: str,
    action_prompt: str,
    statistics_prompt: str,
    synthesis_prompt: str | None = None,
    compare_mode: bool = False,
    external_model_prompt: str | None = None,
):
    worker_configs: dict[str, WorkerConfig] = {
        "knowledge": WorkerConfig(
            name="knowledge-worker",
            primary_namespaces=[("tools", "knowledge")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "statistics"),
                ("tools", "general"),
            ],
        ),
        "action": WorkerConfig(
            name="action-worker",
            primary_namespaces=[("tools", "action")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "statistics"),
                ("tools", "general"),
            ],
        ),
        "media": WorkerConfig(
            name="media-worker",
            primary_namespaces=[("tools", "action", "media")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "statistics"),
                ("tools", "general"),
            ],
        ),
        "statistics": WorkerConfig(
            name="statistics-worker",
            primary_namespaces=[("tools", "statistics")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "browser": WorkerConfig(
            name="browser-worker",
            primary_namespaces=[("tools", "knowledge", "web")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "action"),
                ("tools", "statistics"),
                ("tools", "general"),
            ],
        ),
        "code": WorkerConfig(
            name="code-worker",
            primary_namespaces=[("tools", "general")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "action"),
                ("tools", "statistics"),
            ],
        ),
        "synthesis": WorkerConfig(
            name="synthesis-worker",
            primary_namespaces=[("tools", "knowledge")],
            fallback_namespaces=[
                ("tools", "statistics"),
                ("tools", "action"),
                ("tools", "general"),
            ],
        ),
    }

    worker_prompts: dict[str, str] = {
        "knowledge": knowledge_prompt,
        "action": action_prompt,
        "media": action_prompt,
        "statistics": statistics_prompt,
        "browser": knowledge_prompt,
        "code": knowledge_prompt,
        "synthesis": synthesis_prompt or statistics_prompt or knowledge_prompt,
    }

    workers = {}
    for name, config in worker_configs.items():
        workers[name] = await create_bigtool_worker(
            llm=llm,
            dependencies=dependencies,
            checkpointer=checkpointer,
            config=config,
        )

    agent_definitions = [
        AgentDefinition(
            name="action",
            description="Realtime actions som vader, resor och verktygskorningar",
            keywords=[
                "vader",
                "vadret",
                "väder",
                "vädret",
                "smhi",
                "resa",
                "tåg",
                "tag",
                "avgår",
                "tidtabell",
                "trafik",
                "rutt",
            ],
            namespace=("agents", "action"),
            prompt_key="action",
        ),
        AgentDefinition(
            name="statistics",
            description="SCB och officiell svensk statistik",
            keywords=["statistik", "scb", "kolada", "befolkning", "kpi"],
            namespace=("agents", "statistics"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="media",
            description="Podcast, bild och media-generering",
            keywords=["podcast", "podd", "media", "bild", "ljud"],
            namespace=("agents", "media"),
            prompt_key="media",
        ),
        AgentDefinition(
            name="knowledge",
            description="SurfSense, Tavily och generell kunskap",
            keywords=["kunskap", "surfsense", "tavily", "docs", "note"],
            namespace=("agents", "knowledge"),
            prompt_key="knowledge",
        ),
        AgentDefinition(
            name="browser",
            description="Webbsokning och scraping",
            keywords=["webb", "browser", "sok", "nyheter", "url"],
            namespace=("agents", "browser"),
            prompt_key="browser",
        ),
        AgentDefinition(
            name="code",
            description="Kalkyler och kodrelaterade uppgifter",
            keywords=["kod", "berakna", "script", "python"],
            namespace=("agents", "code"),
            prompt_key="code",
        ),
        AgentDefinition(
            name="synthesis",
            description="Syntes och jämförelser av flera källor och modeller",
            keywords=["synthesis", "syntes", "jämför", "compare", "sammanfatta"],
            namespace=("agents", "synthesis"),
            prompt_key="synthesis",
        ),
    ]

    agent_by_name = {definition.name: definition for definition in agent_definitions}
    db_session = dependencies.get("db_session")
    connector_service = dependencies.get("connector_service")
    search_space_id = dependencies.get("search_space_id")
    user_id = dependencies.get("user_id")
    thread_id = dependencies.get("thread_id")
    compare_external_prompt = external_model_prompt or DEFAULT_EXTERNAL_SYSTEM_PROMPT

    def _build_compare_external_tool(spec):
        async def _compare_tool(query: str) -> dict[str, Any]:
            result = await call_external_model(
                spec=spec,
                query=query,
                system_prompt=compare_external_prompt,
            )
            if connector_service:
                try:
                    document = await connector_service.ingest_tool_output(
                        tool_name=spec.tool_name,
                        tool_output=result,
                        metadata={
                            "provider": result.get("provider"),
                            "model": result.get("model"),
                            "model_display_name": result.get("model_display_name"),
                            "source": result.get("source"),
                        },
                        user_id=user_id,
                        origin_search_space_id=search_space_id,
                        thread_id=thread_id,
                    )
                    if document and getattr(document, "chunks", None):
                        result["document_id"] = document.id
                        result["citation_chunk_ids"] = [
                            str(chunk.id) for chunk in document.chunks
                        ]
                except Exception as exc:
                    print(
                        f"[compare] Failed to ingest {spec.tool_name}: {exc!s}"
                    )
            return result

        return tool(
            spec.tool_name,
            description=f"Call external model {spec.display} for compare mode.",
        )(_compare_tool)

    @tool
    async def retrieve_agents(
        query: str,
        limit: int = 3,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Retrieve relevant agents for the task."""
        recent_agents = []
        context_query = query
        route_hint = None
        cache_key = None
        cache_pattern = None
        if state:
            recent_calls = state.get("recent_agent_calls") or []
            recent_agents = [
                str(call.get("agent"))
                for call in recent_calls
                if call.get("agent")
            ]
            route_hint = state.get("route_hint")
            context_parts = []
            for call in recent_calls[-3:]:
                response = str(call.get("response") or "")
                if len(response) > 120:
                    response = response[:117] + "..."
                context_parts.append(
                    f"{call.get('agent')}: {call.get('task')} {response}"
                )
            if context_parts:
                context_query = f"{query} {' '.join(context_parts)}"

        cache_key, cache_pattern = _build_cache_key(
            query, route_hint, recent_agents
        )
        cached_agents = _get_cached_combo(cache_key)
        if cached_agents is None:
            cached_agents = await _fetch_cached_combo_db(db_session, cache_key)
            if cached_agents:
                _set_cached_combo(cache_key, cached_agents)

        if cached_agents:
            selected = [
                agent_by_name[name]
                for name in cached_agents
                if name in agent_by_name
            ]
        else:
            selected = _smart_retrieve_agents(
                context_query,
                agent_definitions=agent_definitions,
                recent_agents=recent_agents,
                limit=limit,
            )
            if route_hint:
                preferred = {
                    "action": ["action", "media"],
                    "knowledge": ["knowledge", "browser"],
                    "statistics": ["statistics"],
                    "compare": ["synthesis", "knowledge", "statistics"],
                }.get(str(route_hint), [])
                if preferred:
                    preferred_defs = [
                        agent
                        for agent in agent_definitions
                        if agent.name in preferred
                    ]
                    for agent in reversed(preferred_defs):
                        if agent not in selected:
                            selected.insert(0, agent)
                    selected = selected[:limit]

            selected_names = [agent.name for agent in selected]
            if cache_key and cache_pattern:
                await _store_cached_combo_db(
                    db_session,
                    cache_key=cache_key,
                    route_hint=route_hint,
                    pattern=cache_pattern,
                    recent_agents=recent_agents,
                    agents=selected_names,
                )

        selected = selected[:limit]
        payload = [
            {"name": agent.name, "description": agent.description}
            for agent in selected
        ]
        return json.dumps({"agents": payload}, ensure_ascii=True)

    @tool
    async def call_agent(
        agent_name: str,
        task: str,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Call a specialized agent with a task."""
        name = (agent_name or "").strip().lower()
        worker = workers.get(name)
        if not worker:
            return json.dumps(
                {"error": f"Agent '{agent_name}' not available."}, ensure_ascii=True
            )
        if name == "synthesis" and state:
            compare_context = _format_compare_outputs_for_prompt(
                state.get("compare_outputs") or []
            )
            if compare_context and "<compare_outputs>" not in task:
                task = f"{task}\n\n{compare_context}"
        prompt = worker_prompts.get(name, "")
        messages = []
        if prompt:
            messages.append(SystemMessage(content=prompt))
        messages.append(HumanMessage(content=task))
        state = {"messages": messages, "selected_tool_ids": []}
        config = {
            "configurable": {"thread_id": f"{dependencies['thread_id']}:{name}"},
            "recursion_limit": 60,
        }
        result = await worker.ainvoke(state, config=config)
        response_text = ""
        if isinstance(result, dict):
            messages_out = result.get("messages") or []
            if messages_out:
                response_text = str(getattr(messages_out[-1], "content", "") or "")
        if not response_text:
            response_text = str(result)

        critic_prompt = (
            "Du ar en kritisk granskare. Bedom om svaret ar komplett och korrekt. "
            "Svara kort i JSON med {\"status\": \"ok\"|\"needs_more\", \"reason\": \"...\"}."
        )
        critic_input = f"Uppgift: {task}\nSvar: {response_text}"
        critic_msg = await llm.ainvoke(
            [SystemMessage(content=critic_prompt), HumanMessage(content=critic_input)]
        )
        critic_text = str(getattr(critic_msg, "content", "") or "").strip()
        critic_payload = _safe_json(critic_text)
        if not critic_payload:
            critic_payload = {"status": "ok", "reason": critic_text}

        if response_text:
            response_text = response_text.split("{\"status\":", 1)[0].rstrip()

        return json.dumps(
            {
                "agent": name,
                "task": task,
                "response": response_text,
                "critic": critic_payload,
            },
            ensure_ascii=True,
        )

    tool_registry = {
        "retrieve_agents": retrieve_agents,
        "call_agent": call_agent,
        "write_todos": create_write_todos_tool(),
        "reflect_on_progress": create_reflect_on_progress_tool(),
    }
    if compare_mode:
        for spec in EXTERNAL_MODEL_SPECS:
            tool_registry[spec.tool_name] = _build_compare_external_tool(spec)

    llm_with_tools = llm.bind_tools(list(tool_registry.values()))
    tool_node = ToolNode(tool_registry.values())

    def call_model(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        messages = _sanitize_messages(list(state.get("messages") or []))
        plan_context = _format_plan_context(state)
        recent_context = _format_recent_calls(state)
        route_context = _format_route_hint(state)
        system_bits = [
            item for item in (plan_context, recent_context, route_context) if item
        ]
        if system_bits:
            messages = [SystemMessage(content="\n".join(system_bits))] + messages
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    async def acall_model(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        messages = _sanitize_messages(list(state.get("messages") or []))
        plan_context = _format_plan_context(state)
        recent_context = _format_recent_calls(state)
        route_context = _format_route_hint(state)
        system_bits = [
            item for item in (plan_context, recent_context, route_context) if item
        ]
        if system_bits:
            messages = [SystemMessage(content="\n".join(system_bits))] + messages
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    async def post_tools(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        updates: dict[str, Any] = {}
        recent_updates: list[dict[str, Any]] = []
        compare_updates: list[dict[str, Any]] = []
        plan_update: list[dict[str, Any]] | None = None
        plan_complete: bool | None = None
        last_call_payload: dict[str, Any] | None = None

        for message in reversed(state.get("messages") or []):
            if not isinstance(message, ToolMessage):
                continue
            tool_name = message.name or ""
            payload = _safe_json(message.content)
            if tool_name == "write_todos":
                todos = payload.get("todos") or []
                if todos:
                    plan_update = todos
                    completed = [
                        str(todo.get("status") or "").lower()
                        for todo in todos
                        if isinstance(todo, dict)
                    ]
                    if completed:
                        plan_complete = all(
                            status in ("completed", "cancelled") for status in completed
                        )
                if "plan_complete" in payload:
                    plan_complete = bool(payload.get("plan_complete"))
            elif tool_name == "call_agent":
                last_call_payload = payload
                if payload:
                    recent_updates.append(
                        {
                            "agent": payload.get("agent"),
                            "task": payload.get("task"),
                            "response": payload.get("response"),
                        }
                    )
            elif tool_name in _EXTERNAL_MODEL_TOOL_NAMES:
                if payload and payload.get("status") == "success":
                    compare_updates.append(
                        {
                            "tool_call_id": getattr(message, "tool_call_id", None),
                            "tool_name": tool_name,
                            "model_display_name": payload.get("model_display_name"),
                            "model": payload.get("model"),
                            "response": payload.get("response"),
                            "summary": payload.get("summary"),
                            "citation_chunk_ids": payload.get("citation_chunk_ids"),
                        }
                    )
            if plan_update and last_call_payload:
                break

        if plan_update is not None:
            updates["active_plan"] = plan_update
        if plan_complete is not None:
            updates["plan_complete"] = plan_complete
        if recent_updates:
            updates["recent_agent_calls"] = recent_updates
        if compare_updates:
            updates["compare_outputs"] = compare_updates

        if last_call_payload:
            critic_payload = last_call_payload.get("critic") or {}
            if isinstance(critic_payload, dict):
                if critic_payload.get("status") == "needs_more":
                    updates["plan_complete"] = False

        return updates

    def should_continue(state: SupervisorState, *, store=None):
        messages = state.get("messages") or []
        if not messages:
            return END
        last_message = messages[-1]
        if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    graph_builder = StateGraph(SupervisorState)
    graph_builder.add_node("agent", RunnableCallable(call_model, acall_model))
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("post_tools", RunnableCallable(None, post_tools))
    graph_builder.set_entry_point("agent")
    graph_builder.add_conditional_edges("agent", should_continue, path_map=["tools", END])
    graph_builder.add_edge("tools", "post_tools")
    graph_builder.add_edge("post_tools", "agent")

    return graph_builder.compile(checkpointer=checkpointer, name="supervisor-agent")
