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


PLANNING_REFLECTION_INSTRUCTIONS = (
    "Before starting multi-step work, call write_todos to outline a short plan. "
    "Update the plan as you complete steps. After each major action or tool call, "
    "use reflect_on_progress to summarize findings, gaps, and the next step. "
    "Keep both concise to preserve context."
)

KNOWLEDGE_DOCS_INSTRUCTIONS = (
    "The user question is about SurfSense itself. "
    "Use search_surfsense_docs to answer and cite docs. "
    f"{PLANNING_REFLECTION_INSTRUCTIONS}"
)
KNOWLEDGE_INTERNAL_INSTRUCTIONS = (
    "The user question should be answered from the user's internal knowledge base. "
    "Use search_knowledge_base and search broadly unless the user specifies a source. "
    f"{PLANNING_REFLECTION_INSTRUCTIONS}"
)
KNOWLEDGE_EXTERNAL_INSTRUCTIONS = (
    "The user needs external, real-time web information. "
    "Use search_tavily with top_k=3 for live web results. "
    "Prefer concise, up-to-date sources. "
    f"{PLANNING_REFLECTION_INSTRUCTIONS}"
)


def knowledge_route_instructions(route: KnowledgeRoute) -> str:
    if route == KnowledgeRoute.DOCS:
        return KNOWLEDGE_DOCS_INSTRUCTIONS
    if route == KnowledgeRoute.EXTERNAL:
        return KNOWLEDGE_EXTERNAL_INSTRUCTIONS
    return KNOWLEDGE_INTERNAL_INSTRUCTIONS


def knowledge_route_label(route: KnowledgeRoute) -> str:
    if route == KnowledgeRoute.DOCS:
        return "Docs"
    if route == KnowledgeRoute.EXTERNAL:
        return "External"
    return "KB"


ACTION_WEB_INSTRUCTIONS = (
    "The user needs web content handling. Use link_preview for URLs, "
    "scrape_webpage for content, and display_image for relevant images. "
    f"{PLANNING_REFLECTION_INSTRUCTIONS}"
)
ACTION_MEDIA_INSTRUCTIONS = (
    "The user wants media output. Use generate_podcast to create audio. "
    "If you need source content, first call search_knowledge_base. "
    "If the user asks for a podcast, ALWAYS call generate_podcast and do not write a script. "
    f"{PLANNING_REFLECTION_INSTRUCTIONS}"
)
ACTION_TRAVEL_INSTRUCTIONS = (
    "The user needs travel or weather info. Use smhi_weather for weather "
    "and trafiklab_route for public transport. Ask for missing details. "
    f"{PLANNING_REFLECTION_INSTRUCTIONS}"
)
ACTION_DATA_INSTRUCTIONS = (
    "The user is asking for structured data results. Use libris_search for books "
    "and jobad_links_search for job listings. "
    f"{PLANNING_REFLECTION_INSTRUCTIONS}"
)


def action_route_instructions(route: ActionRoute) -> str:
    if route == ActionRoute.MEDIA:
        return ACTION_MEDIA_INSTRUCTIONS
    if route == ActionRoute.TRAVEL:
        return ACTION_TRAVEL_INSTRUCTIONS
    if route == ActionRoute.DATA:
        return ACTION_DATA_INSTRUCTIONS
    return ACTION_WEB_INSTRUCTIONS


SMALLTALK_INSTRUCTIONS = (
    "Keep responses friendly, concise, and conversational. "
    "Do not use tools. Avoid long explanations unless asked."
)


def action_route_label(route: ActionRoute) -> str:
    if route == ActionRoute.MEDIA:
        return "Media"
    if route == ActionRoute.TRAVEL:
        return "Travel"
    if route == ActionRoute.DATA:
        return "Data"
    return "Web"
