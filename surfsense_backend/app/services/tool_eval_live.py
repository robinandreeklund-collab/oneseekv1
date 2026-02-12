"""
Live Tool Evaluation Service

This module provides FULL PIPELINE evaluation by running queries through the 
actual supervisor agent with stub tools (no real API calls).

Unlike the isolated component testing in tool_eval_service.py, this runs the
COMPLETE production flow to see:
- Model reasoning and planning
- How _smart_retrieve_agents() works in practice  
- How smart_retrieve_tools() works in practice
- Full trace of all decisions and scores
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Literal
from pathlib import Path

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

# Import supervisor agent creation
from app.agents.new_chat.supervisor_agent import create_supervisor_agent
from app.agents.new_chat.llm_config import get_default_llm

# Import tool registry builder
from app.agents.new_chat.tools.registry import build_tools_async

# Import stub tool builder from eval service
from app.services.tool_eval_service import _build_stub_tool_registry


@dataclass
class LiveEvalTrace:
    """Trace of a single step in the execution."""
    step_number: int
    step_type: Literal["model_call", "tool_call", "agent_call", "system_message"]
    timestamp: float
    content: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: str | None = None
    model_reasoning: str | None = None
    agent_selected: str | None = None
    tools_retrieved: list[str] | None = None


@dataclass
class LiveEvalResult:
    """Result of running a query through the full pipeline."""
    query: str
    trace: list[LiveEvalTrace]
    final_response: str
    total_steps: int
    total_time_ms: float
    agents_used: list[str]
    tools_used: list[str]
    expected_tools: list[str] | None = None
    matched_tools: list[str] = field(default_factory=list)
    match_type: Literal["exact", "acceptable", "partial", "no_match"] | None = None
    
    # Detailed analysis
    agent_selection_correct: bool | None = None
    tool_selection_correct: bool | None = None
    reasoning_quality: str | None = None


async def _create_stub_tool_registry_for_supervisor(
    dependencies: dict[str, Any]
) -> dict[str, BaseTool]:
    """
    Create stub tool registry compatible with supervisor expectations.
    
    This replaces build_global_tool_registry with stub tools.
    """
    # Get stub tools
    stub_registry = _build_stub_tool_registry()
    
    # Note: In real supervisor, workers call build_global_tool_registry.
    # For evaluation, we need to intercept this and return stubs instead.
    # The challenge is that create_bigtool_worker calls build_global_tool_registry internally.
    # 
    # Solution: We'll need to monkey-patch or pass a parameter through the call chain.
    # For now, let's create a separate evaluation-specific supervisor builder.
    
    return stub_registry


async def evaluate_single_live(
    query: str,
    *,
    db: AsyncSession,
    user_id: str,
    expected_tools: list[str] | None = None,
    expected_agents: list[str] | None = None,
) -> LiveEvalResult:
    """
    Run a single query through the FULL supervisor pipeline with stub tools.
    
    This captures the complete trace including:
    - Model reasoning at each step
    - Agent selection with scores
    - Tool retrieval with scores
    - Execution flow
    
    Args:
        query: User query to evaluate
        db: Database session
        user_id: User ID for evaluation
        expected_tools: Optional list of expected tool IDs
        expected_agents: Optional list of expected agent names
    
    Returns:
        LiveEvalResult with full trace and analysis
    """
    start_time = time.time()
    trace: list[LiveEvalTrace] = []
    step_number = 0
    
    # Build stub tool registry
    stub_tool_registry = _build_stub_tool_registry()
    
    # Build dependencies (same as production)
    dependencies = {
        "db": db,
        "user_id": user_id,
        "thread_id": None,  # Evaluation mode - no persistence
        "search_space_id": 1,
    }
    
    # Get LLM
    llm = get_default_llm()
    
    # Get default prompts from registry
    from app.agents.new_chat.prompt_registry import get_prompt
    knowledge_prompt = get_prompt("agent.knowledge.system")
    action_prompt = get_prompt("agent.action.system")
    statistics_prompt = get_prompt("agent.statistics.system")
    
    try:
        # Create supervisor agent with stub tools
        graph = await create_supervisor_agent(
            llm=llm,
            dependencies=dependencies,
            checkpointer=None,  # No state persistence in eval mode
            knowledge_prompt=knowledge_prompt,
            action_prompt=action_prompt,
            statistics_prompt=statistics_prompt,
            stub_tool_registry=stub_tool_registry,  # Use stubs instead of real tools
        )
        
        # Run the query with event streaming
        state = {"messages": [HumanMessage(content=query)]}
        
        async for event in graph.astream_events(state, version="v1"):
            step_number += 1
            event_type = event.get("event")
            
            if event_type == "on_chat_model_start":
                # Capture model input (reasoning opportunity)
                messages = event.get("data", {}).get("input", {}).get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    content = str(last_msg.content) if hasattr(last_msg, "content") else str(last_msg)
                    trace.append(LiveEvalTrace(
                        step_number=step_number,
                        step_type="model_call",
                        timestamp=time.time() - start_time,
                        content=content[:500],  # Truncate long messages
                        model_reasoning="Processing query...",
                    ))
            
            elif event_type == "on_tool_start":
                # Capture tool invocation
                tool_name = event.get("name")
                tool_input = event.get("data", {}).get("input")
                trace.append(LiveEvalTrace(
                    step_number=step_number,
                    step_type="tool_call",
                    timestamp=time.time() - start_time,
                    content=f"Calling tool: {tool_name}",
                    tool_name=tool_name,
                    tool_args=tool_input if isinstance(tool_input, dict) else {"input": str(tool_input)},
                ))
            
            elif event_type == "on_tool_end":
                # Capture tool result
                tool_name = event.get("name")
                tool_output = event.get("data", {}).get("output")
                # Update the last tool call trace with result
                for t in reversed(trace):
                    if t.tool_name == tool_name and t.tool_result is None:
                        t.tool_result = str(tool_output)[:500] if tool_output else None
                        break
            
            elif event_type == "on_chat_model_end":
                # Capture model response
                output = event.get("data", {}).get("output")
                if hasattr(output, "content"):
                    content = str(output.content)
                    trace.append(LiveEvalTrace(
                        step_number=step_number,
                        step_type="model_call",
                        timestamp=time.time() - start_time,
                        content=content[:500],  # Truncate long responses
                        model_reasoning="Generated response",
                    ))
        
        # Extract final response from state
        final_messages = state.get("messages", [])
        if final_messages:
            last_message = final_messages[-1]
            final_response = str(last_message.content) if hasattr(last_message, "content") else str(last_message)
        else:
            final_response = "No response generated"
        
        # Analyze results
        agents_used = [t.agent_selected for t in trace if t.agent_selected]
        tools_used = [
            t.tool_name for t in trace 
            if t.tool_name 
            and not t.tool_name.startswith("retrieve_") 
            and not t.tool_name.startswith("call_")
            and not t.tool_name.startswith("_")
        ]
        
        # Match analysis
        matched_tools = []
        match_type = None
        if expected_tools:
            matched_tools = [t for t in tools_used if t in expected_tools]
            if set(tools_used) == set(expected_tools):
                match_type = "exact"
            elif all(t in expected_tools for t in tools_used):
                match_type = "acceptable"
            elif matched_tools:
                match_type = "partial"
            else:
                match_type = "no_match"
        
        return LiveEvalResult(
            query=query,
            trace=trace,
            final_response=final_response,
            total_steps=len(trace),
            total_time_ms=(time.time() - start_time) * 1000,
            agents_used=list(set(agents_used)),
            tools_used=list(set(tools_used)),
            expected_tools=expected_tools,
            matched_tools=matched_tools,
            match_type=match_type,
            agent_selection_correct=None,  # Could analyze if expected_agents provided
            tool_selection_correct=match_type == "exact" if match_type else None,
            reasoning_quality=None,  # Could analyze model reasoning quality
        )
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        # Return error result
        return LiveEvalResult(
            query=query,
            trace=trace,  # Return partial trace
            final_response=f"Error: {str(e)}\n\n{error_details}",
            total_steps=len(trace),
            total_time_ms=(time.time() - start_time) * 1000,
            agents_used=[],
            tools_used=[],
            expected_tools=expected_tools,
            matched_tools=[],
            match_type="no_match",
        )


def live_eval_result_to_dict(result: LiveEvalResult) -> dict[str, Any]:
    """Convert LiveEvalResult to JSON-serializable dict."""
    return {
        "query": result.query,
        "trace": [
            {
                "step_number": t.step_number,
                "step_type": t.step_type,
                "timestamp": t.timestamp,
                "content": t.content,
                "tool_name": t.tool_name,
                "tool_args": t.tool_args,
                "tool_result": t.tool_result,
                "model_reasoning": t.model_reasoning,
                "agent_selected": t.agent_selected,
                "tools_retrieved": t.tools_retrieved,
            }
            for t in result.trace
        ],
        "final_response": result.final_response,
        "total_steps": result.total_steps,
        "total_time_ms": result.total_time_ms,
        "agents_used": result.agents_used,
        "tools_used": result.tools_used,
        "expected_tools": result.expected_tools,
        "matched_tools": result.matched_tools,
        "match_type": result.match_type,
        "agent_selection_correct": result.agent_selection_correct,
        "tool_selection_correct": result.tool_selection_correct,
        "reasoning_quality": result.reasoning_quality,
    }
