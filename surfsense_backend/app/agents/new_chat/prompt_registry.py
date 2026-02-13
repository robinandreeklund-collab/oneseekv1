from dataclasses import dataclass

from app.agents.new_chat.action_router import DEFAULT_ACTION_ROUTE_PROMPT
from app.agents.new_chat.bolag_prompts import DEFAULT_BOLAG_SYSTEM_PROMPT
from app.agents.new_chat.bigtool_prompts import (
    DEFAULT_WORKER_ACTION_PROMPT,
    DEFAULT_WORKER_KNOWLEDGE_PROMPT,
)
from app.agents.new_chat.compare_prompts import DEFAULT_COMPARE_ANALYSIS_PROMPT
from app.agents.new_chat.dispatcher import DEFAULT_ROUTE_SYSTEM_PROMPT
from app.agents.new_chat.knowledge_router import DEFAULT_KNOWLEDGE_ROUTE_PROMPT
from app.agents.new_chat.riksdagen_prompts import DEFAULT_RIKSDAGEN_SYSTEM_PROMPT
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
from app.agents.new_chat.statistics_prompts import DEFAULT_STATISTICS_SYSTEM_PROMPT
from app.agents.new_chat.supervisor_prompts import DEFAULT_SUPERVISOR_PROMPT
from app.agents.new_chat.supervisor_runtime_prompts import (
    DEFAULT_SUPERVISOR_CRITIC_PROMPT,
    DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
    DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
    DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE,
)
from app.agents.new_chat.supervisor_pipeline_prompts import (
    DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
    DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE,
    DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE,
    DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE,
    DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
    DEFAULT_SUPERVISOR_TOOL_RESOLVER_PROMPT,
)
from app.agents.new_chat.system_prompt import SURFSENSE_CITATION_INSTRUCTIONS
from app.agents.new_chat.system_prompt import SURFSENSE_SYSTEM_INSTRUCTIONS
from app.agents.new_chat.trafik_prompts import DEFAULT_TRAFFIC_SYSTEM_PROMPT
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
        description="Routes user requests into knowledge/action/smalltalk/compare/statistics.",
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
        key="agent.supervisor.system",
        label="Supervisor prompt",
        description="System prompt for the supervisor agent.",
        default_prompt=DEFAULT_SUPERVISOR_PROMPT,
    ),
    PromptDefinition(
        key="supervisor.critic.system",
        label="Supervisor critic prompt",
        description="Prompt used by supervisor critic to validate delegated agent answers.",
        default_prompt=DEFAULT_SUPERVISOR_CRITIC_PROMPT,
    ),
    PromptDefinition(
        key="supervisor.loop_guard.message",
        label="Supervisor loop guard message",
        description=(
            "Fallback response when supervisor detects repeated planning loops. "
            "Use {recent_preview} placeholder to include latest partial results."
        ),
        default_prompt=DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
    ),
    PromptDefinition(
        key="supervisor.tool_limit_guard.message",
        label="Supervisor tool-limit guard message",
        description=(
            "Fallback response when too many tools are called in one user turn. "
            "Use {recent_preview} placeholder to include latest partial results."
        ),
        default_prompt=DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
    ),
    PromptDefinition(
        key="supervisor.trafik.enforcement.message",
        label="Supervisor Trafik enforcement prompt",
        description=(
            "Extra instruction injected when trafik agent must retry with proper trafikverket tool usage."
        ),
        default_prompt=DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE,
    ),
    PromptDefinition(
        key="supervisor.intent_resolver.system",
        label="Supervisor intent resolver prompt",
        description="Prompt for intent_resolver node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
    ),
    PromptDefinition(
        key="supervisor.agent_resolver.system",
        label="Supervisor agent resolver prompt",
        description="Prompt for agent_resolver node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
    ),
    PromptDefinition(
        key="supervisor.planner.system",
        label="Supervisor planner prompt",
        description="Prompt for planner node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_PLANNER_PROMPT,
    ),
    PromptDefinition(
        key="supervisor.tool_resolver.system",
        label="Supervisor tool resolver prompt",
        description="Prompt for tool_resolver node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_TOOL_RESOLVER_PROMPT,
    ),
    PromptDefinition(
        key="supervisor.critic_gate.system",
        label="Supervisor critic gate prompt",
        description="Prompt for critic node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
    ),
    PromptDefinition(
        key="supervisor.synthesizer.system",
        label="Supervisor synthesizer prompt",
        description="Prompt for synthesizer node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
    ),
    PromptDefinition(
        key="supervisor.hitl.planner.message",
        label="Supervisor HITL planner confirmation message",
        description="User-facing confirmation message before executing planner output.",
        default_prompt=DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE,
    ),
    PromptDefinition(
        key="supervisor.hitl.execution.message",
        label="Supervisor HITL execution confirmation message",
        description="User-facing confirmation message before running the next execution step.",
        default_prompt=DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE,
    ),
    PromptDefinition(
        key="supervisor.hitl.synthesis.message",
        label="Supervisor HITL synthesis confirmation message",
        description="User-facing confirmation message before delivering synthesized response.",
        default_prompt=DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE,
    ),
    PromptDefinition(
        key="agent.worker.knowledge",
        label="Worker · Knowledge prompt",
        description="System prompt for knowledge bigtool worker.",
        default_prompt=DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    ),
    PromptDefinition(
        key="agent.knowledge.system",
        label="Knowledge agent prompt",
        description="System prompt for the knowledge agent.",
        default_prompt=DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    ),
    PromptDefinition(
        key="agent.worker.action",
        label="Worker · Action prompt",
        description="System prompt for action bigtool worker.",
        default_prompt=DEFAULT_WORKER_ACTION_PROMPT,
    ),
    PromptDefinition(
        key="agent.action.system",
        label="Action agent prompt",
        description="System prompt for the action agent.",
        default_prompt=DEFAULT_WORKER_ACTION_PROMPT,
    ),
    PromptDefinition(
        key="agent.media.system",
        label="Media agent prompt",
        description="System prompt for the media agent.",
        default_prompt=DEFAULT_WORKER_ACTION_PROMPT,
    ),
    PromptDefinition(
        key="agent.browser.system",
        label="Browser agent prompt",
        description="System prompt for the browser agent.",
        default_prompt=DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    ),
    PromptDefinition(
        key="agent.code.system",
        label="Code agent prompt",
        description="System prompt for the code agent.",
        default_prompt=DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    ),
    PromptDefinition(
        key="agent.kartor.system",
        label="Kartor agent prompt",
        description="System prompt for the maps agent.",
        default_prompt=DEFAULT_WORKER_ACTION_PROMPT,
    ),
    PromptDefinition(
        key="agent.statistics.system",
        label="Statistics agent prompt",
        description="System prompt for the SCB statistics agent.",
        default_prompt=DEFAULT_STATISTICS_SYSTEM_PROMPT,
    ),
    PromptDefinition(
        key="agent.synthesis.system",
        label="Synthesis agent prompt",
        description="System prompt for the synthesis agent.",
        default_prompt=DEFAULT_STATISTICS_SYSTEM_PROMPT,
    ),
    PromptDefinition(
        key="agent.bolag.system",
        label="Bolag agent prompt",
        description="System prompt for Bolagsverket tools.",
        default_prompt=DEFAULT_BOLAG_SYSTEM_PROMPT,
    ),
    PromptDefinition(
        key="agent.trafik.system",
        label="Trafik agent prompt",
        description="System prompt for Trafikverket tools.",
        default_prompt=DEFAULT_TRAFFIC_SYSTEM_PROMPT,
    ),
    PromptDefinition(
        key="agent.riksdagen.system",
        label="Riksdagen agent prompt",
        description="System prompt for Riksdagen tools.",
        default_prompt=DEFAULT_RIKSDAGEN_SYSTEM_PROMPT,
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
    PromptDefinition(
        key="system.default.instructions",
        label="Core system prompt",
        description="Default system instructions from system_prompt.py.",
        default_prompt=SURFSENSE_SYSTEM_INSTRUCTIONS,
    ),
    PromptDefinition(
        key="citation.instructions",
        label="Citation instructions",
        description=(
            "Opt-in citation block injected only when citation_instructions is enabled in chat requests."
        ),
        default_prompt=SURFSENSE_CITATION_INSTRUCTIONS,
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
