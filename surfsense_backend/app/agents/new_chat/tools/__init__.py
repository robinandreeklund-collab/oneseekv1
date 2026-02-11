"""
Tools module for SurfSense deep agent.

This module contains all the tools available to the SurfSense agent.
To add a new tool, see the documentation in registry.py.

Available tools:
- search_knowledge_base: Search the user's personal knowledge base
- search_surfsense_docs: Search Surfsense documentation for usage help
- generate_podcast: Generate audio podcasts from content
- link_preview: Fetch rich previews for URLs
- display_image: Display images in chat
- geoapify_static_map: Generate static map images via Geoapify
- scrape_webpage: Extract content from webpages
- smhi_weather: Fetch weather data from SMHI
- trafiklab_route: Find departures using Trafiklab realtime APIs
- libris_search: Search the Libris XL catalog
- jobad_links_search: Search job ads via Arbetsformedlingen
- search_web: Search the public web with global API keys
- save_memory: Store facts/preferences about the user
- recall_memory: Retrieve relevant user memories
- reflect_on_progress: Log a brief reflection on progress
"""

# Registry exports
# Tool factory exports (for direct use)
from .display_image import create_display_image_tool
from .geoapify_maps import create_geoapify_static_map_tool
from .external_models import EXTERNAL_MODEL_SPECS, create_external_model_tool
from .jobad_links_search import create_jobad_links_search_tool
from .knowledge_base import (
    CONNECTOR_DESCRIPTIONS,
    create_search_knowledge_base_tool,
    format_documents_for_context,
    search_knowledge_base_async,
)
from .link_preview import create_link_preview_tool
from .libris_search import create_libris_search_tool
from .podcast import create_generate_podcast_tool
from .public_web_search import create_public_web_search_tool
from .reflect_on_progress import create_reflect_on_progress_tool
from .registry import (
    BUILTIN_TOOLS,
    ToolDefinition,
    build_tools,
    get_all_tool_names,
    get_default_enabled_tools,
    get_tool_by_name,
)
from .scrape_webpage import create_scrape_webpage_tool
from .search_surfsense_docs import create_search_surfsense_docs_tool
from .smhi_weather import create_smhi_weather_tool
from .trafiklab_route import create_trafiklab_route_tool
from .user_memory import create_recall_memory_tool, create_save_memory_tool

__all__ = [
    # Registry
    "BUILTIN_TOOLS",
    # Knowledge base utilities
    "CONNECTOR_DESCRIPTIONS",
    "ToolDefinition",
    "build_tools",
    # Tool factories
    "create_display_image_tool",
    "create_geoapify_static_map_tool",
    "create_external_model_tool",
    "create_geoapify_static_map_tool",
    "create_generate_podcast_tool",
    "create_jobad_links_search_tool",
    "create_link_preview_tool",
    "create_libris_search_tool",
    "create_public_web_search_tool",
    "create_reflect_on_progress_tool",
    "create_recall_memory_tool",
    "create_save_memory_tool",
    "create_scrape_webpage_tool",
    "create_search_knowledge_base_tool",
    "create_search_surfsense_docs_tool",
    "create_smhi_weather_tool",
    "create_trafiklab_route_tool",
    "EXTERNAL_MODEL_SPECS",
    "format_documents_for_context",
    "get_all_tool_names",
    "get_default_enabled_tools",
    "get_tool_by_name",
    "search_knowledge_base_async",
]
