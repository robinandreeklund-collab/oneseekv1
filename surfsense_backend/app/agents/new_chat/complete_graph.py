"""Builder entrypoint for the modular supervisor graph.

This module provides a stable construction API used by chat streaming routes.
It decouples callers from supervisor internals so the graph can evolve without
touching endpoint/task wiring.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import Checkpointer

from app.agents.new_chat.supervisor_agent import create_supervisor_agent


async def build_complete_graph(
    *,
    llm,
    dependencies: dict[str, Any],
    checkpointer: Checkpointer | None,
    config_schema: type[Any] | None = None,
    knowledge_prompt: str,
    action_prompt: str,
    statistics_prompt: str,
    synthesis_prompt: str | None = None,
    compare_mode: bool = False,
    debate_mode: bool = False,
    voice_debate_mode: bool = False,
    hybrid_mode: bool = False,
    speculative_enabled: bool = False,
    external_model_prompt: str | None = None,
    bolag_prompt: str | None = None,
    trafik_prompt: str | None = None,
    media_prompt: str | None = None,
    browser_prompt: str | None = None,
    code_prompt: str | None = None,
    kartor_prompt: str | None = None,
    riksdagen_prompt: str | None = None,
    marketplace_prompt: str | None = None,
    tool_prompt_overrides: dict[str, str] | None = None,
    think_on_tool_calls: bool = True,
):
    """Build and compile the complete supervisor graph."""
    return await create_supervisor_agent(
        llm=llm,
        dependencies=dependencies,
        checkpointer=checkpointer,
        config_schema=config_schema,
        knowledge_prompt=knowledge_prompt,
        action_prompt=action_prompt,
        statistics_prompt=statistics_prompt,
        synthesis_prompt=synthesis_prompt,
        compare_mode=compare_mode,
        debate_mode=debate_mode,
        voice_debate_mode=voice_debate_mode,
        hybrid_mode=hybrid_mode,
        speculative_enabled=speculative_enabled,
        external_model_prompt=external_model_prompt,
        bolag_prompt=bolag_prompt,
        trafik_prompt=trafik_prompt,
        media_prompt=media_prompt,
        browser_prompt=browser_prompt,
        code_prompt=code_prompt,
        kartor_prompt=kartor_prompt,
        riksdagen_prompt=riksdagen_prompt,
        marketplace_prompt=marketplace_prompt,
        tool_prompt_overrides=tool_prompt_overrides,
        think_on_tool_calls=think_on_tool_calls,
    )
