from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.types import Checkpointer
from langgraph_bigtool import create_agent as create_bigtool_agent

from app.agents.new_chat.bigtool_store import _tokenize, _normalize_text
from app.agents.new_chat.bigtool_workers import WorkerConfig, create_bigtool_worker
from app.agents.new_chat.statistics_prompts import build_statistics_system_prompt
from app.agents.new_chat.tools.reflect_on_progress import create_reflect_on_progress_tool
from app.agents.new_chat.tools.write_todos import create_write_todos_tool


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


def _smart_retrieve_agents(
    query: str,
    *,
    agent_definitions: list[AgentDefinition],
    limit: int = 3,
) -> list[AgentDefinition]:
    query_norm = _normalize_text(query)
    tokens = set(_tokenize(query_norm))
    scored = [
        (definition, _score_agent(definition, query_norm, tokens))
        for definition in agent_definitions
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [definition for definition, _ in scored[:limit]]


async def create_supervisor_agent(
    *,
    llm,
    dependencies: dict[str, Any],
    checkpointer: Checkpointer | None,
    knowledge_prompt: str,
    action_prompt: str,
    statistics_prompt: str,
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
    }

    worker_prompts: dict[str, str] = {
        "knowledge": knowledge_prompt,
        "action": action_prompt,
        "media": action_prompt,
        "statistics": statistics_prompt,
        "browser": knowledge_prompt,
        "code": knowledge_prompt,
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
    ]

    @tool
    async def retrieve_agents(query: str, limit: int = 3) -> str:
        """Retrieve relevant agents for the task."""
        selected = _smart_retrieve_agents(
            query, agent_definitions=agent_definitions, limit=limit
        )
        payload = [
            {"name": agent.name, "description": agent.description}
            for agent in selected
        ]
        return json.dumps({"agents": payload}, ensure_ascii=True)

    @tool
    async def call_agent(agent_name: str, task: str) -> str:
        """Call a specialized agent with a task."""
        name = (agent_name or "").strip().lower()
        worker = workers.get(name)
        if not worker:
            return json.dumps(
                {"error": f"Agent '{agent_name}' not available."}, ensure_ascii=True
            )
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
        return json.dumps(
            {"agent": name, "response": response_text}, ensure_ascii=True
        )

    tool_registry = {
        "retrieve_agents": retrieve_agents,
        "call_agent": call_agent,
        "write_todos": create_write_todos_tool(),
        "reflect_on_progress": create_reflect_on_progress_tool(),
    }

    def retrieve_tools(query: str) -> list[str]:
        """Return supervisor tools to bind for this step."""
        return list(tool_registry.keys())

    async def aretrieve_tools(query: str) -> list[str]:
        """Async wrapper for supervisor tool binding."""
        return retrieve_tools(query)

    graph = create_bigtool_agent(
        llm,
        tool_registry,
        limit=3,
        retrieve_tools_function=retrieve_tools,
        retrieve_tools_coroutine=aretrieve_tools,
    )
    return graph.compile(
        checkpointer=checkpointer,
        name="supervisor-agent",
    )
