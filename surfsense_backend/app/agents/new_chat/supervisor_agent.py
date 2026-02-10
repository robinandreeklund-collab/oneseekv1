from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.types import Checkpointer
from langgraph_bigtool.graph import END, StateGraph, ToolNode, RunnableCallable
from langgraph_bigtool.tools import InjectedState

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
    recent_agents: list[str] | None = None,
    limit: int = 3,
) -> list[AgentDefinition]:
    query_norm = _normalize_text(query)
    tokens = set(_tokenize(query_norm))
    recent_agents = [agent for agent in (recent_agents or []) if agent]
    scored = [
        (definition, _score_agent(definition, query_norm, tokens))
        for definition in agent_definitions
    ]
    if recent_agents:
        for idx, (definition, score) in enumerate(scored):
            if definition.name in recent_agents:
                scored[idx] = (definition, score + 4)
    scored.sort(key=lambda item: item[1], reverse=True)
    return [definition for definition, _ in scored[:limit]]


def _replace(left: Any, right: Any) -> Any:
    return right if right is not None else left


def _append_recent(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged = list(left or [])
    merged.extend(right or [])
    return merged[-3:]


class SupervisorState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    active_plan: Annotated[list[dict[str, Any]], _replace]
    plan_complete: Annotated[bool, _replace]
    recent_agent_calls: Annotated[list[dict[str, Any]], _append_recent]
    route_hint: Annotated[str | None, _replace]


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
    ]

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

    llm_with_tools = llm.bind_tools(list(tool_registry.values()))
    tool_node = ToolNode(tool_registry.values())

    def call_model(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        messages = list(state.get("messages") or [])
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
        messages = list(state.get("messages") or [])
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
            if plan_update and last_call_payload:
                break

        if plan_update is not None:
            updates["active_plan"] = plan_update
        if plan_complete is not None:
            updates["plan_complete"] = plan_complete
        if recent_updates:
            updates["recent_agent_calls"] = recent_updates

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
