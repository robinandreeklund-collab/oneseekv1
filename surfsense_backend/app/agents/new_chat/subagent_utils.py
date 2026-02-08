from dataclasses import replace

from app.agents.new_chat.action_router import ActionRoute
from app.agents.new_chat.knowledge_router import KnowledgeRoute
from app.agents.new_chat.llm_config import AgentConfig
from app.agents.new_chat.system_prompt import get_default_system_instructions


def build_subagent_config(
    base_config: AgentConfig | None, extra_instructions: str | None
) -> AgentConfig | None:
    if base_config is None or not extra_instructions:
        return base_config
    base_instructions = (
        base_config.system_instructions
        if base_config.system_instructions
        else get_default_system_instructions()
    )
    combined = (
        f"{base_instructions}\n\n<routing_instructions>\n"
        f"{extra_instructions.strip()}\n</routing_instructions>"
    )
    return replace(
        base_config,
        system_instructions=combined,
        use_default_system_instructions=False,
    )


def knowledge_route_instructions(route: KnowledgeRoute) -> str:
    if route == KnowledgeRoute.DOCS:
        return (
            "The user question is about SurfSense itself. "
            "Use search_surfsense_docs to answer and cite docs."
        )
    if route == KnowledgeRoute.EXTERNAL:
        return (
            "The user needs external, real-time web information. "
            "Use search_knowledge_base with connectors_to_search=['TAVILY_API'] "
            "and top_k=3. Prefer concise, up-to-date sources."
        )
    return (
        "The user question should be answered from the user's internal knowledge base. "
        "Use search_knowledge_base and search broadly unless the user specifies a source."
    )


def knowledge_route_label(route: KnowledgeRoute) -> str:
    if route == KnowledgeRoute.DOCS:
        return "Docs"
    if route == KnowledgeRoute.EXTERNAL:
        return "External"
    return "KB"


def action_route_instructions(route: ActionRoute) -> str:
    if route == ActionRoute.MEDIA:
        return (
            "The user wants media output. Use generate_podcast to create audio. "
            "If you need source content, first call search_knowledge_base."
        )
    if route == ActionRoute.TRAVEL:
        return (
            "The user needs travel or weather info. Use smhi_weather for weather "
            "and trafiklab_route for public transport. Ask for missing details."
        )
    if route == ActionRoute.DATA:
        return (
            "The user is asking for structured data results. Use libris_search for books "
            "and jobad_links_search for job listings."
        )
    return (
        "The user needs web content handling. Use link_preview for URLs, "
        "scrape_webpage for content, and display_image for relevant images."
    )


def action_route_label(route: ActionRoute) -> str:
    if route == ActionRoute.MEDIA:
        return "Media"
    if route == ActionRoute.TRAVEL:
        return "Travel"
    if route == ActionRoute.DATA:
        return "Data"
    return "Web"
