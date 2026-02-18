"""Tools registry for SurfSense deep agent.

This module provides a registry pattern for managing tools in the SurfSense agent.
It makes it easy for OSS contributors to add new tools by:
1. Creating a tool factory function in a new file in this directory
2. Registering the tool in the BUILTIN_TOOLS list below

Example of adding a new tool:
------------------------------
1. Create your tool file (e.g., `tools/my_tool.py`):

    from langchain_core.tools import tool
    from sqlalchemy.ext.asyncio import AsyncSession

    def create_my_tool(search_space_id: int, db_session: AsyncSession):
        @tool
        async def my_tool(param: str) -> dict:
            '''My tool description.'''
            # Your implementation
            return {"result": "success"}
        return my_tool

2. Import and register in this file:

    from .my_tool import create_my_tool

    # Add to BUILTIN_TOOLS list:
    ToolDefinition(
        name="my_tool",
        description="Description of what your tool does",
        factory=lambda deps: create_my_tool(
            search_space_id=deps["search_space_id"],
            db_session=deps["db_session"],
        ),
        requires=["search_space_id", "db_session"],
    ),
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool

from .display_image import create_display_image_tool
from .geoapify_maps import create_geoapify_static_map_tool
from .bolagsverket import (
    BOLAGSVERKET_TOOL_DEFINITIONS,
    create_bolagsverket_tool,
)
from .trafikverket import (
    TRAFIKVERKET_TOOL_DEFINITIONS,
    create_trafikverket_tool,
)
from ..riksdagen_agent import (
    RIKSDAGEN_TOOL_DEFINITIONS,
    build_riksdagen_tool_registry,
)
from ..marketplace_tools import (
    MARKETPLACE_TOOL_DEFINITIONS,
    build_marketplace_tool_registry,
)
from ..skolverket_tools import (
    SKOLVERKET_TOOL_DEFINITIONS,
    build_skolverket_tool_registry,
)
from ..kolada_tools import (
    KOLADA_TOOL_DEFINITIONS,
    build_kolada_tool_registry,
)
from .external_models import EXTERNAL_MODEL_SPECS, create_external_model_tool
from .jobad_links_search import create_jobad_links_search_tool
from .knowledge_base import create_search_knowledge_base_tool
from .link_preview import create_link_preview_tool
from .libris_search import create_libris_search_tool
from .mcp_tool import load_mcp_tools
from .podcast import create_generate_podcast_tool
from .public_web_search import create_public_web_search_tool
from .reflect_on_progress import create_reflect_on_progress_tool
from .scrape_webpage import create_scrape_webpage_tool
from .search_surfsense_docs import create_search_surfsense_docs_tool
from .sandbox_execute import create_sandbox_execute_tool
from .sandbox_filesystem import (
    create_list_directory_alias_tool,
    create_sandbox_ls_tool,
    create_sandbox_read_file_tool,
    create_sandbox_replace_tool,
    create_sandbox_write_file_tool,
)
from .sandbox_release import create_sandbox_release_tool
from .smhi_weather import create_smhi_weather_tool
from .tavily_search import create_tavily_search_tool
from .trafiklab_route import create_trafiklab_route_tool
from .user_memory import create_recall_memory_tool, create_save_memory_tool
from .write_todos import create_write_todos_tool

# =============================================================================
# Tool Definition
# =============================================================================


@dataclass
class ToolDefinition:
    """Definition of a tool that can be added to the agent.

    Attributes:
        name: Unique identifier for the tool
        description: Human-readable description of what the tool does
        factory: Callable that creates the tool. Receives a dict of dependencies.
        requires: List of dependency names this tool needs (e.g., "search_space_id", "db_session")
        enabled_by_default: Whether the tool is enabled when no explicit config is provided

    """

    name: str
    description: str
    factory: Callable[[dict[str, Any]], BaseTool]
    requires: list[str] = field(default_factory=list)
    enabled_by_default: bool = True


# =============================================================================
# Built-in Tools Registry
# =============================================================================

# Registry of all built-in tools
# Contributors: Add your new tools here!
BUILTIN_TOOLS: list[ToolDefinition] = [
    # Core tool - searches the user's knowledge base
    # Now supports dynamic connector/document type discovery
    ToolDefinition(
        name="search_knowledge_base",
        description="Search the user's personal knowledge base for relevant information",
        factory=lambda deps: create_search_knowledge_base_tool(
            search_space_id=deps["search_space_id"],
            db_session=deps["db_session"],
            connector_service=deps["connector_service"],
            # Optional: dynamically discovered connectors/document types
            available_connectors=deps.get("available_connectors"),
            available_document_types=deps.get("available_document_types"),
        ),
        requires=["search_space_id", "db_session", "connector_service"],
        # Note: available_connectors and available_document_types are optional
    ),
    ToolDefinition(
        name="search_tavily",
        description="Search the public web via the Tavily connector (live)",
        factory=lambda deps: create_tavily_search_tool(
            connector_service=deps["connector_service"],
            search_space_id=deps["search_space_id"],
            user_id=deps.get("user_id"),
        ),
        requires=["connector_service", "search_space_id"],
    ),
    # Podcast generation tool
    ToolDefinition(
        name="generate_podcast",
        description="Generate an audio podcast from provided content",
        factory=lambda deps: create_generate_podcast_tool(
            search_space_id=deps["search_space_id"],
            db_session=deps["db_session"],
            thread_id=deps["thread_id"],
        ),
        requires=["search_space_id", "db_session", "thread_id"],
    ),
    # Link preview tool - fetches Open Graph metadata for URLs
    ToolDefinition(
        name="link_preview",
        description="Fetch metadata for a URL to display a rich preview card",
        factory=lambda deps: create_link_preview_tool(),
        requires=[],
    ),
    # Display image tool - shows images in the chat
    ToolDefinition(
        name="display_image",
        description="Display an image in the chat with metadata",
        factory=lambda deps: create_display_image_tool(),
        requires=[],
    ),
    ToolDefinition(
        name="geoapify_static_map",
        description="Generate a static map image with optional markers via Geoapify",
        factory=lambda deps: create_geoapify_static_map_tool(),
        requires=[],
    ),
    # Web scraping tool - extracts content from webpages
    ToolDefinition(
        name="scrape_webpage",
        description="Scrape and extract the main content from a webpage",
        factory=lambda deps: create_scrape_webpage_tool(
            firecrawl_api_key=deps.get("firecrawl_api_key"),
        ),
        requires=[],  # firecrawl_api_key is optional
    ),
    ToolDefinition(
        name="smhi_weather",
        description=(
            "Fetch weather data from SMHI using a place name or lat/lon coordinates"
        ),
        factory=lambda deps: create_smhi_weather_tool(),
        requires=[],
    ),
    ToolDefinition(
        name="trafiklab_route",
        description=(
            "Find public transport departures using Trafiklab realtime APIs and stop lookup"
        ),
        factory=lambda deps: create_trafiklab_route_tool(),
        requires=[],
    ),
    ToolDefinition(
        name="libris_search",
        description="Search the Libris XL catalog for books and media",
        factory=lambda deps: create_libris_search_tool(),
        requires=[],
    ),
    ToolDefinition(
        name="jobad_links_search",
        description="Search Swedish job ads via Arbetsformedlingen Jobtech Links API",
        factory=lambda deps: create_jobad_links_search_tool(),
        requires=[],
    ),
    ToolDefinition(
        name="search_web",
        description="Search the public web using globally configured providers",
        factory=lambda deps: create_public_web_search_tool(),
        requires=[],
        enabled_by_default=False,
    ),
    ToolDefinition(
        name="sandbox_execute",
        description="Execute shell commands inside a thread-isolated sandbox workspace",
        factory=lambda deps: create_sandbox_execute_tool(
            thread_id=deps.get("thread_id"),
            runtime_hitl=deps.get("runtime_hitl"),
            trace_recorder=deps.get("trace_recorder"),
            trace_parent_span_id=deps.get("trace_parent_span_id"),
        ),
        requires=[],
        enabled_by_default=False,
    ),
    ToolDefinition(
        name="sandbox_ls",
        description="List files and directories inside a thread-isolated sandbox workspace",
        factory=lambda deps: create_sandbox_ls_tool(
            thread_id=deps.get("thread_id"),
            runtime_hitl=deps.get("runtime_hitl"),
            trace_recorder=deps.get("trace_recorder"),
            trace_parent_span_id=deps.get("trace_parent_span_id"),
        ),
        requires=[],
        enabled_by_default=False,
    ),
    ToolDefinition(
        name="sandbox_read_file",
        description="Read UTF-8 text files from a thread-isolated sandbox workspace",
        factory=lambda deps: create_sandbox_read_file_tool(
            thread_id=deps.get("thread_id"),
            runtime_hitl=deps.get("runtime_hitl"),
            trace_recorder=deps.get("trace_recorder"),
            trace_parent_span_id=deps.get("trace_parent_span_id"),
        ),
        requires=[],
        enabled_by_default=False,
    ),
    ToolDefinition(
        name="sandbox_write_file",
        description="Write UTF-8 text files inside a thread-isolated sandbox workspace",
        factory=lambda deps: create_sandbox_write_file_tool(
            thread_id=deps.get("thread_id"),
            runtime_hitl=deps.get("runtime_hitl"),
            trace_recorder=deps.get("trace_recorder"),
            trace_parent_span_id=deps.get("trace_parent_span_id"),
        ),
        requires=[],
        enabled_by_default=False,
    ),
    ToolDefinition(
        name="sandbox_replace",
        description="Replace text within UTF-8 files in a thread-isolated sandbox workspace",
        factory=lambda deps: create_sandbox_replace_tool(
            thread_id=deps.get("thread_id"),
            runtime_hitl=deps.get("runtime_hitl"),
            trace_recorder=deps.get("trace_recorder"),
            trace_parent_span_id=deps.get("trace_parent_span_id"),
        ),
        requires=[],
        enabled_by_default=False,
    ),
    ToolDefinition(
        name="list_directory",
        description="Compatibility alias to list files in the sandbox workspace",
        factory=lambda deps: create_list_directory_alias_tool(
            thread_id=deps.get("thread_id"),
            runtime_hitl=deps.get("runtime_hitl"),
            trace_recorder=deps.get("trace_recorder"),
            trace_parent_span_id=deps.get("trace_parent_span_id"),
        ),
        requires=[],
        enabled_by_default=False,
    ),
    ToolDefinition(
        name="sandbox_release",
        description="Release and cleanup the current thread sandbox lease",
        factory=lambda deps: create_sandbox_release_tool(
            thread_id=deps.get("thread_id"),
            runtime_hitl=deps.get("runtime_hitl"),
            trace_recorder=deps.get("trace_recorder"),
            trace_parent_span_id=deps.get("trace_parent_span_id"),
        ),
        requires=[],
        enabled_by_default=False,
    ),
    # Note: write_todos is now provided by TodoListMiddleware from deepagents
    ToolDefinition(
        name="reflect_on_progress",
        description="Log a brief reflection on progress, gaps, and next steps",
        factory=lambda deps: create_reflect_on_progress_tool(),
        requires=[],
        enabled_by_default=False,
    ),
    ToolDefinition(
        name="write_todos",
        description="Create or update a short todo list for multi-step work",
        factory=lambda deps: create_write_todos_tool(),
        requires=[],
        enabled_by_default=False,
    ),
    # Surfsense documentation search tool
    ToolDefinition(
        name="search_surfsense_docs",
        description="Search Surfsense documentation for help with using the application",
        factory=lambda deps: create_search_surfsense_docs_tool(
            db_session=deps["db_session"],
        ),
        requires=["db_session"],
    ),
    # =========================================================================
    # USER MEMORY TOOLS - Claude-like memory feature
    # =========================================================================
    # Save memory tool - stores facts/preferences about the user
    ToolDefinition(
        name="save_memory",
        description="Save facts, preferences, or context about the user for personalized responses",
        factory=lambda deps: create_save_memory_tool(
            user_id=deps["user_id"],
            search_space_id=deps["search_space_id"],
            db_session=deps["db_session"],
        ),
        requires=["user_id", "search_space_id", "db_session"],
    ),
    # Recall memory tool - retrieves relevant user memories
    ToolDefinition(
        name="recall_memory",
        description="Recall user memories for personalized and contextual responses",
        factory=lambda deps: create_recall_memory_tool(
            user_id=deps["user_id"],
            search_space_id=deps["search_space_id"],
            db_session=deps["db_session"],
        ),
        requires=["user_id", "search_space_id", "db_session"],
    ),
    # =========================================================================
    # BOLAGSVERKET OPEN DATA TOOLS
    # =========================================================================
    *[
        ToolDefinition(
            name=definition.tool_id,
            description=definition.description,
            factory=lambda deps, definition=definition: create_bolagsverket_tool(
                definition,
                connector_service=deps["connector_service"],
                search_space_id=deps["search_space_id"],
                user_id=deps.get("user_id"),
                thread_id=deps.get("thread_id"),
            ),
            requires=["connector_service", "search_space_id"],
        )
        for definition in BOLAGSVERKET_TOOL_DEFINITIONS
    ],
    # =========================================================================
    # TRAFIKVERKET OPEN API TOOLS
    # =========================================================================
    *[
        ToolDefinition(
            name=definition.tool_id,
            description=definition.description,
            factory=lambda deps, definition=definition: create_trafikverket_tool(
                definition,
                connector_service=deps["connector_service"],
                search_space_id=deps["search_space_id"],
                user_id=deps.get("user_id"),
                thread_id=deps.get("thread_id"),
            ),
            requires=["connector_service", "search_space_id"],
        )
        for definition in TRAFIKVERKET_TOOL_DEFINITIONS
    ],
    # =========================================================================
    # EXTERNAL MODEL TOOLS (COMPARE FLOW)
    # =========================================================================
    *[
        ToolDefinition(
            name=spec.tool_name,
            description=(
                f"Call the external model {spec.display} using global config {spec.config_id}"
            ),
            factory=lambda deps, spec=spec: create_external_model_tool(spec),
            requires=[],
            enabled_by_default=False,
        )
        for spec in EXTERNAL_MODEL_SPECS
    ],
    # =========================================================================
    # ADD YOUR CUSTOM TOOLS BELOW
    # =========================================================================
    # Example:
    # ToolDefinition(
    #     name="my_custom_tool",
    #     description="What my tool does",
    #     factory=lambda deps: create_my_custom_tool(...),
    #     requires=["search_space_id"],
    # ),
]


# =============================================================================
# Registry Functions
# =============================================================================


def get_tool_by_name(name: str) -> ToolDefinition | None:
    """Get a tool definition by its name."""
    for tool_def in BUILTIN_TOOLS:
        if tool_def.name == name:
            return tool_def
    return None


def get_all_tool_names() -> list[str]:
    """Get names of all registered tools."""
    return [tool_def.name for tool_def in BUILTIN_TOOLS]


def get_default_enabled_tools() -> list[str]:
    """Get names of tools that are enabled by default."""
    default_tools = [tool_def.name for tool_def in BUILTIN_TOOLS if tool_def.enabled_by_default]
    # Add all specialized domain tools to default enabled tools
    riksdagen_tool_ids = [definition.tool_id for definition in RIKSDAGEN_TOOL_DEFINITIONS]
    marketplace_tool_ids = [definition.tool_id for definition in MARKETPLACE_TOOL_DEFINITIONS]
    skolverket_tool_ids = [definition.tool_id for definition in SKOLVERKET_TOOL_DEFINITIONS]
    kolada_tool_ids = [definition.tool_id for definition in KOLADA_TOOL_DEFINITIONS]
    return default_tools + riksdagen_tool_ids + marketplace_tool_ids + skolverket_tool_ids + kolada_tool_ids


def get_all_tool_names() -> list[str]:
    """
    Get all registered tool names across all categories.
    
    Returns:
        List of all tool IDs/names in the registry
    """
    builtin_tool_names = [tool_def.name for tool_def in BUILTIN_TOOLS]
    riksdagen_tool_ids = [definition.tool_id for definition in RIKSDAGEN_TOOL_DEFINITIONS]
    marketplace_tool_ids = [definition.tool_id for definition in MARKETPLACE_TOOL_DEFINITIONS]
    skolverket_tool_ids = [definition.tool_id for definition in SKOLVERKET_TOOL_DEFINITIONS]
    kolada_tool_ids = [definition.tool_id for definition in KOLADA_TOOL_DEFINITIONS]
    external_model_ids = [spec.tool_name for spec in EXTERNAL_MODEL_SPECS]
    
    return (
        builtin_tool_names
        + riksdagen_tool_ids
        + marketplace_tool_ids
        + skolverket_tool_ids
        + kolada_tool_ids
        + external_model_ids
    )


def build_tools(
    dependencies: dict[str, Any],
    enabled_tools: list[str] | None = None,
    disabled_tools: list[str] | None = None,
    additional_tools: list[BaseTool] | None = None,
) -> list[BaseTool]:
    """Build the list of tools for the agent.

    Args:
        dependencies: Dict containing all possible dependencies:
            - search_space_id: The search space ID
            - db_session: Database session
            - connector_service: Connector service instance
            - firecrawl_api_key: Optional Firecrawl API key
        enabled_tools: Explicit list of tool names to enable. If None, uses defaults.
        disabled_tools: List of tool names to disable (applied after enabled_tools).
        additional_tools: Extra tools to add (e.g., custom tools not in registry).

    Returns:
        List of configured tool instances ready for the agent.

    Example:
        # Use all default tools
        tools = build_tools(deps)

        # Use only specific tools
        tools = build_tools(deps, enabled_tools=["search_knowledge_base", "link_preview"])

        # Use defaults but disable podcast
        tools = build_tools(deps, disabled_tools=["generate_podcast"])

        # Add custom tools
        tools = build_tools(deps, additional_tools=[my_custom_tool])

    """
    # Determine which tools to enable
    if enabled_tools is not None:
        tool_names_to_use = set(enabled_tools)
    else:
        tool_names_to_use = set(get_default_enabled_tools())

    # Apply disabled list
    if disabled_tools:
        tool_names_to_use -= set(disabled_tools)

    # Build the tools
    tools: list[BaseTool] = []
    for tool_def in BUILTIN_TOOLS:
        if tool_def.name not in tool_names_to_use:
            continue

        # Check that all required dependencies are provided
        missing_deps = [dep for dep in tool_def.requires if dep not in dependencies]
        if missing_deps:
            msg = f"Tool '{tool_def.name}' requires dependencies: {missing_deps}"
            raise ValueError(
                msg,
            )

        # Create the tool
        tool = tool_def.factory(dependencies)
        tools.append(tool)

    # Add any additional custom tools
    if additional_tools:
        tools.extend(additional_tools)

    return tools


async def build_tools_async(
    dependencies: dict[str, Any],
    enabled_tools: list[str] | None = None,
    disabled_tools: list[str] | None = None,
    additional_tools: list[BaseTool] | None = None,
    include_mcp_tools: bool = True,
    respect_lifecycle: bool = True,
) -> list[BaseTool]:
    """Async version of build_tools that also loads MCP tools from database.

    Design Note:
    This function exists because MCP tools require database queries to load user configs,
    while built-in tools are created synchronously from static code.

    Alternative: We could make build_tools() itself async and always query the database,
    but that would force async everywhere even when only using built-in tools. The current
    design keeps the simple case (static tools only) synchronous while supporting dynamic
    database-loaded tools through this async wrapper.

    Args:
        dependencies: Dict containing all possible dependencies
        enabled_tools: Explicit list of tool names to enable. If None, uses defaults.
        disabled_tools: List of tool names to disable (applied after enabled_tools).
        additional_tools: Extra tools to add (e.g., custom tools not in registry).
        include_mcp_tools: Whether to load user's MCP tools from database.
        respect_lifecycle: If True, only load tools with 'live' status. If False, load all tools (for eval).

    Returns:
        List of configured tool instances ready for the agent, including MCP tools.

    """
    # Apply lifecycle filtering if enabled
    if respect_lifecycle and "db_session" in dependencies:
        try:
            from app.services.tool_lifecycle_service import get_live_tool_ids
            live_tool_ids = await get_live_tool_ids(dependencies["db_session"])
            
            if live_tool_ids:
                # Filter enabled_tools to only include live tools
                if enabled_tools is not None:
                    enabled_tools = [t for t in enabled_tools if t in live_tool_ids]
                else:
                    # Use default tools but filter to only live ones
                    default_tools = set(get_default_enabled_tools())
                    enabled_tools = [t for t in default_tools if t in live_tool_ids]
                
                logging.info(f"Lifecycle filtering enabled: {len(live_tool_ids)} live tools")
        except Exception as e:
            # Fallback: if lifecycle check fails, continue with original behavior
            logging.warning(f"Lifecycle filtering failed, using all tools: {e}")
    
    # Build standard tools
    tools = build_tools(dependencies, enabled_tools, disabled_tools, additional_tools)

    # Build Riksdagen tools if any are enabled
    if enabled_tools:
        riksdag_tools_to_build = [
            tool_id for tool_id in enabled_tools 
            if tool_id.startswith("riksdag_")
        ]
    else:
        # Check if any riksdag tools would be enabled by default
        riksdag_tools_to_build = [
            definition.tool_id for definition in RIKSDAGEN_TOOL_DEFINITIONS
        ]
    
    # Filter out disabled riksdag tools
    if disabled_tools:
        riksdag_tools_to_build = [
            tool_id for tool_id in riksdag_tools_to_build
            if tool_id not in disabled_tools
        ]
    
    # Build Riksdagen tools if any should be enabled
    if riksdag_tools_to_build and "connector_service" in dependencies and "search_space_id" in dependencies:
        try:
            riksdag_registry = build_riksdagen_tool_registry(
                connector_service=dependencies["connector_service"],
                search_space_id=dependencies["search_space_id"],
                user_id=dependencies.get("user_id"),
                thread_id=dependencies.get("thread_id"),
            )
            for tool_id in riksdag_tools_to_build:
                if tool_id in riksdag_registry:
                    tools.append(riksdag_registry[tool_id])
            logging.info(
                f"Registered {len(riksdag_tools_to_build)} Riksdagen tools: {riksdag_tools_to_build}",
            )
        except Exception as e:
            logging.exception(f"Failed to build Riksdagen tools: {e!s}")

    # Build Marketplace tools if any are enabled
    if enabled_tools:
        marketplace_tools_to_build = [
            tool_id for tool_id in enabled_tools 
            if tool_id.startswith("marketplace_")
        ]
    else:
        # Check if any marketplace tools would be enabled by default
        marketplace_tools_to_build = [
            definition.tool_id for definition in MARKETPLACE_TOOL_DEFINITIONS
        ]
    
    # Filter out disabled marketplace tools
    if disabled_tools:
        marketplace_tools_to_build = [
            tool_id for tool_id in marketplace_tools_to_build
            if tool_id not in disabled_tools
        ]
    
    # Build Marketplace tools if any should be enabled
    if marketplace_tools_to_build and "connector_service" in dependencies and "search_space_id" in dependencies:
        try:
            marketplace_registry = build_marketplace_tool_registry(
                connector_service=dependencies["connector_service"],
                search_space_id=dependencies["search_space_id"],
                user_id=dependencies.get("user_id"),
                thread_id=dependencies.get("thread_id"),
            )
            for tool_id in marketplace_tools_to_build:
                if tool_id in marketplace_registry:
                    tools.append(marketplace_registry[tool_id])
            logging.info(
                f"Registered {len(marketplace_tools_to_build)} Marketplace tools: {marketplace_tools_to_build}",
            )
        except Exception as e:
            logging.exception(f"Failed to build Marketplace tools: {e!s}")

    # Build Skolverket tools if requested
    if enabled_tools is not None:
        skolverket_tools_to_build = [
            tool_id
            for tool_id in enabled_tools
            if any(
                tool_id == definition.tool_id
                for definition in SKOLVERKET_TOOL_DEFINITIONS
            )
        ]
    else:
        # If no enabled_tools specified, build all Skolverket tools by default
        skolverket_tools_to_build = [
            definition.tool_id for definition in SKOLVERKET_TOOL_DEFINITIONS
        ]

    # Remove disabled tools
    if disabled_tools:
        skolverket_tools_to_build = [
            tool_id for tool_id in skolverket_tools_to_build if tool_id not in disabled_tools
        ]

    if skolverket_tools_to_build and "connector_service" in dependencies:
        try:
            skolverket_registry = build_skolverket_tool_registry(
                connector_service=dependencies["connector_service"],
                search_space_id=dependencies.get("search_space_id"),
                user_id=dependencies.get("user_id"),
                thread_id=dependencies.get("thread_id"),
            )

            # Add tools from registry
            for tool_id in skolverket_tools_to_build:
                if tool_id in skolverket_registry:
                    tools.append(skolverket_registry[tool_id])

            logging.info(
                f"Registered {len(skolverket_tools_to_build)} Skolverket tools: "
                f"{skolverket_tools_to_build}"
            )
        except Exception as e:
            logging.exception(f"Failed to build Skolverket tools: {e!s}")

    # Build Kolada tools if requested
    if enabled_tools is not None:
        kolada_tools_to_build = [
            tool_id
            for tool_id in enabled_tools
            if any(
                tool_id == definition.tool_id
                for definition in KOLADA_TOOL_DEFINITIONS
            )
        ]
    else:
        # If no enabled_tools specified, build all Kolada tools by default
        kolada_tools_to_build = [
            definition.tool_id for definition in KOLADA_TOOL_DEFINITIONS
        ]

    # Remove disabled tools
    if disabled_tools:
        kolada_tools_to_build = [
            tool_id for tool_id in kolada_tools_to_build if tool_id not in disabled_tools
        ]

    if kolada_tools_to_build and "connector_service" in dependencies:
        try:
            kolada_registry = build_kolada_tool_registry(
                connector_service=dependencies["connector_service"],
                search_space_id=dependencies.get("search_space_id"),
                user_id=dependencies.get("user_id"),
                thread_id=dependencies.get("thread_id"),
            )

            # Add tools from registry
            for tool_id in kolada_tools_to_build:
                if tool_id in kolada_registry:
                    tools.append(kolada_registry[tool_id])

            logging.info(
                f"Registered {len(kolada_tools_to_build)} Kolada tools: "
                f"{kolada_tools_to_build}"
            )
        except Exception as e:
            logging.exception(f"Failed to build Kolada tools: {e!s}")

    # Load MCP tools if requested and dependencies are available
    if (
        include_mcp_tools
        and "db_session" in dependencies
        and "search_space_id" in dependencies
    ):
        try:
            mcp_tools = await load_mcp_tools(
                dependencies["db_session"],
                dependencies["search_space_id"],
            )
            tools.extend(mcp_tools)
            logging.info(
                f"Registered {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}",
            )
        except Exception as e:
            # Log error but don't fail - just continue without MCP tools
            logging.exception(f"Failed to load MCP tools: {e!s}")

    # Log all tools being returned to agent
    logging.info(
        f"Total tools for agent: {len(tools)} - {[t.name for t in tools]}",
    )

    return tools
