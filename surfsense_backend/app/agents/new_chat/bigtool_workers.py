from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.types import Checkpointer
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph_bigtool import create_agent as create_bigtool_agent
from langgraph_bigtool.graph import ToolNode as BigtoolToolNode

from app.agents.new_chat.bigtool_store import (
    build_bigtool_store,
    build_global_tool_registry,
    build_tool_index,
    make_smart_retriever,
)
from app.services.tool_retrieval_tuning_service import (
    get_global_tool_retrieval_tuning,
)
from app.services.tool_metadata_service import get_global_tool_metadata_overrides


@dataclass(frozen=True)
class WorkerConfig:
    name: str
    primary_namespaces: list[tuple[str, ...]]
    fallback_namespaces: list[tuple[str, ...]]
    tool_limit: int = 3


class WorkerHandle:
    """Thin wrapper that exposes worker tool inventory for guardrails."""

    def __init__(self, *, graph: Any, available_tool_ids: tuple[str, ...]):
        self._graph = graph
        self.available_tool_ids = available_tool_ids

    async def ainvoke(self, *args, **kwargs):
        return await self._graph.ainvoke(*args, **kwargs)

    async def astream(self, *args, **kwargs):
        async for item in self._graph.astream(*args, **kwargs):
            yield item

    def __getattr__(self, item: str) -> Any:
        return getattr(self._graph, item)


async def create_bigtool_worker(
    *,
    llm,
    dependencies: dict[str, Any],
    checkpointer: Checkpointer | None,
    config: WorkerConfig,
):
    if not hasattr(BigtoolToolNode, "inject_tool_args") and hasattr(
        BigtoolToolNode, "_inject_tool_args"
    ):
        def _inject_tool_args_compat(self, tool_call, state, store):
            tool_call_id = None
            if isinstance(tool_call, dict):
                tool_call_id = tool_call.get("id")
            runtime = ToolRuntime(
                state,
                {},
                {},
                lambda _: None,
                tool_call_id,
                store,
            )
            return self._inject_tool_args(tool_call, runtime)

        BigtoolToolNode.inject_tool_args = _inject_tool_args_compat  # type: ignore[attr-defined]
    tool_registry = await build_global_tool_registry(
        dependencies=dependencies,
        include_mcp_tools=True,
    )
    metadata_overrides = await get_global_tool_metadata_overrides(
        dependencies["db_session"]
    )
    retrieval_tuning = await get_global_tool_retrieval_tuning(
        dependencies["db_session"]
    )
    tool_index = build_tool_index(
        tool_registry,
        metadata_overrides=metadata_overrides,
    )
    store = build_bigtool_store(tool_index)
    trace_key = str(dependencies.get("thread_id") or "")
    retrieve_tools, aretrieve_tools = make_smart_retriever(
        tool_index=tool_index,
        primary_namespaces=config.primary_namespaces,
        fallback_namespaces=config.fallback_namespaces,
        limit=config.tool_limit,
        trace_key=trace_key,
        retrieval_tuning=retrieval_tuning,
    )
    graph = create_bigtool_agent(
        llm,
        tool_registry,
        limit=config.tool_limit,
        retrieve_tools_function=retrieve_tools,
        retrieve_tools_coroutine=aretrieve_tools,
    )
    compiled = graph.compile(
        checkpointer=checkpointer,
        store=store,
        name=config.name,
    )
    available_tool_ids = tuple(sorted(str(tool_id) for tool_id in tool_registry.keys()))
    return WorkerHandle(
        graph=compiled,
        available_tool_ids=available_tool_ids,
    )
