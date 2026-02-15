"""
Deterministic compare execution nodes for the supervisor graph.

These nodes orchestrate parallel external model calls, collect results,
optionally enrich with web search, and synthesize the final comparison response.

Unlike the non-deterministic LLM-based approach, these nodes guarantee
that ALL configured external models are called in parallel without relying
on the LLM to make tool calling decisions.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.new_chat.compare_prompts import DEFAULT_COMPARE_ANALYSIS_PROMPT
from app.agents.new_chat.system_prompt import append_datetime_context
from app.agents.new_chat.tools.external_models import (
    EXTERNAL_MODEL_SPECS,
    call_external_model,
)


async def compare_fan_out(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compare fan-out node: Call ALL external models in parallel.
    
    This node:
    1. Extracts user query from messages
    2. Calls ALL configured external models in parallel using asyncio.gather
    3. Ingests each result via connector_service for citations
    4. Emits proper AIMessage with tool_calls and ToolMessage responses
       to ensure frontend model cards render correctly
    
    Returns state updates with new messages appended.
    """
    messages = state.get("messages", [])
    
    # Extract user query from last HumanMessage
    user_query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_query = msg.content
            break
    
    if not user_query:
        # Shouldn't happen, but safeguard
        return {}
    
    # Create AIMessage with tool_calls for ALL external models
    # This ensures the UI renders model cards for each
    tool_calls = []
    for spec in EXTERNAL_MODEL_SPECS:
        tool_call_id = str(uuid.uuid4())
        tool_calls.append({
            "name": spec.tool_name,
            "args": {"query": user_query},
            "id": tool_call_id,
            "type": "tool_call",
        })
    
    ai_message = AIMessage(
        content="",  # Empty content, just tool calls
        tool_calls=tool_calls,
    )
    
    # Call all external models in parallel
    async def call_one_model(spec, tool_call_id: str) -> tuple[str, str, dict[str, Any]]:
        """Call a single external model and return (tool_name, tool_call_id, result)"""
        try:
            result = await call_external_model(
                spec=spec,
                query=user_query,
            )
            return spec.tool_name, tool_call_id, result
        except Exception as e:
            return spec.tool_name, tool_call_id, {
                "status": "error",
                "error": str(e),
                "model_display_name": spec.display,
            }
    
    # Execute all calls in parallel
    tasks = [
        call_one_model(spec, tc["id"])
        for spec, tc in zip(EXTERNAL_MODEL_SPECS, tool_calls, strict=True)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    
    # Note: Tool output ingestion for citations is handled by the supervisor's
    # post_tools node, which has access to the full dependency context
    # (db_session, connector_service, user_id, etc.)
    
    # Create ToolMessage for each result
    tool_messages = []
    for tool_name, tool_call_id, result in results:
        tool_messages.append(
            ToolMessage(
                name=tool_name,
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=tool_call_id,
            )
        )
    
    # Store results in compare_outputs for synthesis
    compare_updates = []
    for tool_name, _, result in results:
        compare_updates.append({
            "tool_name": tool_name,
            "result": result,
            "timestamp": time.time(),
        })
    
    return {
        "messages": [ai_message] + tool_messages,
        "compare_outputs": compare_updates,
    }


async def compare_collect(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compare collect node: Validate completeness of model results.
    
    Checks how many models succeeded/failed and could add metadata
    about result quality for the synthesizer.
    
    For now, this is a simple pass-through that could be extended
    with quality checks, timeout handling, etc.
    """
    compare_outputs = state.get("compare_outputs", [])
    
    success_count = sum(
        1 for output in compare_outputs
        if output.get("result", {}).get("status") == "success"
    )
    
    total_count = len(compare_outputs)
    
    # Could add a message or state update about completeness
    # For now, just pass through
    return {
        "orchestration_phase": f"compare_collect_complete_{success_count}/{total_count}",
    }


async def compare_tavily(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compare Tavily node: Optional web enrichment with Swedish sources.
    
    This node can be extended to:
    1. Detect if web search would be valuable
    2. Call Tavily with Swedish language preference
    3. Ingest Tavily results for citations
    4. Add web context to compare_outputs
    
    For now, this is a placeholder that can be enhanced later.
    """
    # TODO: Implement Tavily web enrichment
    # For MVP, we'll skip this and go straight to synthesis
    return {
        "orchestration_phase": "compare_tavily_complete",
    }


def _build_synthesis_context(
    user_query: str,
    compare_outputs: list[dict[str, Any]],
) -> str:
    """Build context string from compare outputs for synthesis."""
    blocks = []
    
    blocks.append(f"Användarfråga: {user_query}\n")
    
    for output in compare_outputs:
        tool_name = output.get("tool_name", "unknown")
        result = output.get("result", {})
        
        if result.get("status") == "success":
            model_name = result.get("model_display_name", tool_name)
            response = result.get("response", "")
            provider = result.get("provider", "")
            
            blocks.append(
                f"MODEL_ANSWER from {model_name} ({provider}):\n{response}\n"
            )
        elif result.get("status") == "error":
            model_name = result.get("model_display_name", tool_name)
            error = result.get("error", "Unknown error")
            blocks.append(f"MODEL_ERROR from {model_name}: {error}\n")
    
    return "\n".join(blocks)


async def compare_synthesizer(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compare synthesizer node: Create final synthesis response.
    
    Takes all compare_outputs from state and produces the final
    synthesis response using the LLM with DEFAULT_COMPARE_ANALYSIS_PROMPT.
    
    This node:
    1. Builds context from all model responses
    2. Uses synthesis LLM to create optimized answer
    3. Handles citations properly
    4. Returns final response in state
    """
    from app.agents.new_chat.llm_config import create_chat_litellm_from_config
    
    messages = state.get("messages", [])
    compare_outputs = state.get("compare_outputs", [])
    
    # Extract user query
    user_query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_query = msg.content
            break
    
    # Build synthesis context
    context = _build_synthesis_context(user_query, compare_outputs)
    
    # Get synthesis LLM config
    # For now, use the default LLM from global config
    # TODO: Make this configurable
    try:
        from app.agents.new_chat.llm_config import load_llm_config_from_yaml
        
        # Use config -1 (Sonnet) for synthesis
        llm_config = load_llm_config_from_yaml(-1)
        llm = create_chat_litellm_from_config(llm_config)
    except Exception as e:
        # Fallback: can't synthesize without LLM
        return {
            "final_response": f"Error: Could not load synthesis LLM: {e}",
            "orchestration_phase": "compare_synthesis_error",
        }
    
    # Build synthesis prompt
    synthesis_prompt = append_datetime_context(DEFAULT_COMPARE_ANALYSIS_PROMPT)
    
    # Create synthesis messages
    synthesis_messages = [
        {"role": "system", "content": synthesis_prompt},
        {"role": "user", "content": context},
    ]
    
    try:
        # Call synthesis LLM
        response = await llm.ainvoke(synthesis_messages)
        synthesis_text = response.content if hasattr(response, "content") else str(response)
        
        # Add synthesis result as AIMessage so streaming can extract it
        synthesis_message = AIMessage(content=synthesis_text)
        
        return {
            "messages": [synthesis_message],
            "final_response": synthesis_text,
            "orchestration_phase": "compare_synthesis_complete",
        }
    except Exception as e:
        error_msg = f"Error during synthesis: {e}"
        error_message = AIMessage(content=error_msg)
        return {
            "messages": [error_message],
            "final_response": error_msg,
            "orchestration_phase": "compare_synthesis_error",
        }
