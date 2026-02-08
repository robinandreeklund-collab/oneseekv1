from dataclasses import dataclass

from app.agents.new_chat.action_router import DEFAULT_ACTION_ROUTE_PROMPT
from app.agents.new_chat.compare_prompts import DEFAULT_COMPARE_ANALYSIS_PROMPT
from app.agents.new_chat.dispatcher import DEFAULT_ROUTE_SYSTEM_PROMPT
from app.agents.new_chat.knowledge_router import DEFAULT_KNOWLEDGE_ROUTE_PROMPT
from app.agents.new_chat.subagent_utils import (
    ACTION_DATA_INSTRUCTIONS,
    ACTION_MEDIA_INSTRUCTIONS,
    ACTION_TRAVEL_INSTRUCTIONS,
    ACTION_WEB_INSTRUCTIONS,
    KNOWLEDGE_DOCS_INSTRUCTIONS,
    KNOWLEDGE_EXTERNAL_INSTRUCTIONS,
    KNOWLEDGE_INTERNAL_INSTRUCTIONS,
    SMALLTALK_INSTRUCTIONS,
)
from app.agents.new_chat.tools.external_models import DEFAULT_EXTERNAL_SYSTEM_PROMPT


@dataclass(frozen=True)
class PromptDefinition:
    key: str
    label: str
    description: str
    default_prompt: str


PROMPT_DEFINITIONS: list[PromptDefinition] = [
    PromptDefinition(
        key="router.top_level",
        label="Top-level router prompt",
        description="Routes user requests into knowledge/action/smalltalk/compare.",
        default_prompt=DEFAULT_ROUTE_SYSTEM_PROMPT,
    ),
    PromptDefinition(
        key="router.knowledge",
        label="Knowledge router prompt",
        description="Routes knowledge requests to docs/internal/external.",
        default_prompt=DEFAULT_KNOWLEDGE_ROUTE_PROMPT,
    ),
    PromptDefinition(
        key="router.action",
        label="Action router prompt",
        description="Routes action requests to web/media/travel/data.",
        default_prompt=DEFAULT_ACTION_ROUTE_PROMPT,
    ),
    PromptDefinition(
        key="agent.knowledge.docs",
        label="Knowledge · Docs instructions",
        description="Sub-agent instructions for SurfSense docs.",
        default_prompt=KNOWLEDGE_DOCS_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="agent.knowledge.internal",
        label="Knowledge · Internal instructions",
        description="Sub-agent instructions for internal knowledge base.",
        default_prompt=KNOWLEDGE_INTERNAL_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="agent.knowledge.external",
        label="Knowledge · External instructions",
        description="Sub-agent instructions for external (Tavily) search.",
        default_prompt=KNOWLEDGE_EXTERNAL_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="agent.action.web",
        label="Action · Web instructions",
        description="Sub-agent instructions for web tasks (scrape/preview/image).",
        default_prompt=ACTION_WEB_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="agent.action.media",
        label="Action · Media instructions",
        description="Sub-agent instructions for podcast/audio tasks.",
        default_prompt=ACTION_MEDIA_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="agent.action.travel",
        label="Action · Travel instructions",
        description="Sub-agent instructions for weather/routes.",
        default_prompt=ACTION_TRAVEL_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="agent.action.data",
        label="Action · Data instructions",
        description="Sub-agent instructions for Libris/job search.",
        default_prompt=ACTION_DATA_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="agent.smalltalk.system",
        label="Smalltalk instructions",
        description="Instructions for casual chat without tools.",
        default_prompt=SMALLTALK_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="compare.analysis.system",
        label="Compare analysis prompt",
        description="System prompt for compare synthesis step.",
        default_prompt=DEFAULT_COMPARE_ANALYSIS_PROMPT,
    ),
    PromptDefinition(
        key="compare.external.system",
        label="Compare external model prompt",
        description="System prompt sent to external models in compare.",
        default_prompt=DEFAULT_EXTERNAL_SYSTEM_PROMPT,
    ),
]


PROMPT_DEFINITION_MAP = {definition.key: definition for definition in PROMPT_DEFINITIONS}


def get_prompt_definitions() -> list[PromptDefinition]:
    return list(PROMPT_DEFINITIONS)


def resolve_prompt(
    overrides: dict[str, str],
    key: str,
    default_prompt: str,
) -> str:
    override = overrides.get(key)
    if override is None:
        return default_prompt
    trimmed = override.strip()
    return trimmed if trimmed else default_prompt
