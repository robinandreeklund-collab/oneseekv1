"""
SurfSense New Chat Agent Module.

This module provides the SurfSense deep agent with configurable tools
for knowledge base search, podcast generation, and more.

Directory Structure:
- tools/: All agent tools (knowledge_base, podcast, link_preview, etc.)
- chat_deepagent.py: Main agent factory
- system_prompt.py: System prompts and instructions
- context.py: Context schema for the agent
- checkpointer.py: LangGraph checkpointer setup
- llm_config.py: LLM configuration utilities
- utils.py: Shared utilities
"""

from importlib import import_module
from typing import Any

__all__ = [
    # Tools registry
    "BUILTIN_TOOLS",
    # System prompt
    "SURFSENSE_CITATION_INSTRUCTIONS",
    "SURFSENSE_SYSTEM_PROMPT",
    # Context
    "SurfSenseContextSchema",
    "ToolDefinition",
    "build_surfsense_system_prompt",
    "build_tools",
    # LLM config
    "create_chat_litellm_from_config",
    # Tool factories
    "create_display_image_tool",
    "create_generate_podcast_tool",
    "create_link_preview_tool",
    "create_scrape_webpage_tool",
    "create_search_knowledge_base_tool",
    # Agent factory
    "create_surfsense_deep_agent",
    # Knowledge base utilities
    "format_documents_for_context",
    "get_all_tool_names",
    "get_default_enabled_tools",
    "get_tool_by_name",
    "load_llm_config_from_yaml",
    "search_knowledge_base_async",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # Agent factory
    "create_surfsense_deep_agent": (
        "app.agents.new_chat.chat_deepagent",
        "create_surfsense_deep_agent",
    ),
    # Context
    "SurfSenseContextSchema": (
        "app.agents.new_chat.context",
        "SurfSenseContextSchema",
    ),
    # LLM config
    "create_chat_litellm_from_config": (
        "app.agents.new_chat.llm_config",
        "create_chat_litellm_from_config",
    ),
    "load_llm_config_from_yaml": (
        "app.agents.new_chat.llm_config",
        "load_llm_config_from_yaml",
    ),
    # System prompt
    "SURFSENSE_CITATION_INSTRUCTIONS": (
        "app.agents.new_chat.system_prompt",
        "SURFSENSE_CITATION_INSTRUCTIONS",
    ),
    "SURFSENSE_SYSTEM_PROMPT": (
        "app.agents.new_chat.system_prompt",
        "SURFSENSE_SYSTEM_PROMPT",
    ),
    "build_surfsense_system_prompt": (
        "app.agents.new_chat.system_prompt",
        "build_surfsense_system_prompt",
    ),
    # Tools
    "BUILTIN_TOOLS": ("app.agents.new_chat.tools", "BUILTIN_TOOLS"),
    "ToolDefinition": ("app.agents.new_chat.tools", "ToolDefinition"),
    "build_tools": ("app.agents.new_chat.tools", "build_tools"),
    "create_display_image_tool": (
        "app.agents.new_chat.tools",
        "create_display_image_tool",
    ),
    "create_generate_podcast_tool": (
        "app.agents.new_chat.tools",
        "create_generate_podcast_tool",
    ),
    "create_link_preview_tool": (
        "app.agents.new_chat.tools",
        "create_link_preview_tool",
    ),
    "create_scrape_webpage_tool": (
        "app.agents.new_chat.tools",
        "create_scrape_webpage_tool",
    ),
    "create_search_knowledge_base_tool": (
        "app.agents.new_chat.tools",
        "create_search_knowledge_base_tool",
    ),
    "format_documents_for_context": (
        "app.agents.new_chat.tools",
        "format_documents_for_context",
    ),
    "get_all_tool_names": ("app.agents.new_chat.tools", "get_all_tool_names"),
    "get_default_enabled_tools": (
        "app.agents.new_chat.tools",
        "get_default_enabled_tools",
    ),
    "get_tool_by_name": ("app.agents.new_chat.tools", "get_tool_by_name"),
    "search_knowledge_base_async": (
        "app.agents.new_chat.tools",
        "search_knowledge_base_async",
    ),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
