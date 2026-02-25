from dataclasses import dataclass

from app.agents.new_chat.bolag_prompts import DEFAULT_BOLAG_SYSTEM_PROMPT
from app.agents.new_chat.bigtool_prompts import (
    DEFAULT_WORKER_ACTION_PROMPT,
    DEFAULT_WORKER_KNOWLEDGE_PROMPT,
)
from app.agents.new_chat.compare_prompts import (
    COMPARE_SUPERVISOR_INSTRUCTIONS,
    DEFAULT_COMPARE_ANALYSIS_PROMPT,
)
from app.agents.new_chat.dispatcher import DEFAULT_ROUTE_SYSTEM_PROMPT
from app.agents.new_chat.riksdagen_prompts import DEFAULT_RIKSDAGEN_SYSTEM_PROMPT
from app.agents.new_chat.marketplace_prompts import DEFAULT_MARKETPLACE_SYSTEM_PROMPT
from app.agents.new_chat.statistics_prompts import DEFAULT_STATISTICS_SYSTEM_PROMPT
from app.agents.new_chat.subagent_utils import SMALLTALK_INSTRUCTIONS
from app.agents.new_chat.supervisor_prompts import DEFAULT_SUPERVISOR_PROMPT
from app.agents.new_chat.supervisor_runtime_prompts import (
    DEFAULT_SUPERVISOR_CODE_READ_FILE_ENFORCEMENT_MESSAGE,
    DEFAULT_SUPERVISOR_CODE_SANDBOX_ENFORCEMENT_MESSAGE,
    DEFAULT_SUPERVISOR_CRITIC_PROMPT,
    DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
    DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE,
    DEFAULT_SUPERVISOR_SUBAGENT_CONTEXT_TEMPLATE,
    DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
    DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
    DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE,
)
from app.agents.new_chat.supervisor_pipeline_prompts import (
    DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
    DEFAULT_SUPERVISOR_DOMAIN_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE,
    DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE,
    DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE,
    DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_MULTI_DOMAIN_PLANNER_PROMPT,
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
    active_in_admin: bool = True

    @property
    def node_group(self) -> str:
        group, _label = infer_prompt_node_group(self.key)
        return group

    @property
    def node_group_label(self) -> str:
        _group, label = infer_prompt_node_group(self.key)
        return label


def infer_prompt_node_group(key: str) -> tuple[str, str]:
    normalized_key = str(key or "").strip().lower()
    if normalized_key.startswith("router."):
        return ("router", "Router")
    if normalized_key.startswith("compare."):
        return ("compare", "Compare")
    if normalized_key == "agent.supervisor.system" or normalized_key.startswith(
        "supervisor."
    ):
        return ("supervisor", "Supervisor")
    if normalized_key.startswith("agent.") and normalized_key != "agent.supervisor.system":
        return ("subagent", "Subagent/Worker")
    if normalized_key.startswith("system.") or normalized_key.startswith("citation."):
        return ("system", "System")
    return ("other", "Övrigt")


ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS: tuple[str, ...] = (
    # Platform ingress
    "system.default.instructions",
    "citation.instructions",
    "router.top_level",
    "agent.smalltalk.system",
    # Supervisor orchestration
    "agent.supervisor.system",
    "compare.supervisor.instructions",
    "supervisor.intent_resolver.system",
    "supervisor.agent_resolver.system",
    "supervisor.planner.system",
    "supervisor.planner.multi_domain.system",
    "supervisor.tool_resolver.system",
    "supervisor.domain_planner.system",
    "supervisor.critic_gate.system",
    "supervisor.synthesizer.system",
    "supervisor.critic.system",
    "supervisor.loop_guard.message",
    "supervisor.tool_limit_guard.message",
    "supervisor.trafik.enforcement.message",
    "supervisor.code.sandbox.enforcement.message",
    "supervisor.code.read_file.enforcement.message",
    "supervisor.scoped_tool_prompt.template",
    "supervisor.tool_default_prompt.template",
    "supervisor.subagent.context.template",
    "supervisor.hitl.planner.message",
    "supervisor.hitl.execution.message",
    "supervisor.hitl.synthesis.message",
    # Worker prompts
    "agent.worker.knowledge",
    "agent.knowledge.system",
    "agent.worker.action",
    "agent.action.system",
    "agent.media.system",
    "agent.browser.system",
    "agent.code.system",
    "agent.kartor.system",
    "agent.statistics.system",
    "agent.synthesis.system",
    "agent.bolag.system",
    "agent.trafik.system",
    "agent.riksdagen.system",
    "agent.marketplace.system",
    # Compare execution
    "compare.analysis.system",
    "compare.external.system",
)


_PROMPT_DEFINITIONS_BY_KEY: dict[str, PromptDefinition] = {
    "system.default.instructions": PromptDefinition(
        key="system.default.instructions",
        label="Core system prompt",
        description="Default system instructions applied to chat runtime.",
        default_prompt=SURFSENSE_SYSTEM_INSTRUCTIONS,
    ),
    "citation.instructions": PromptDefinition(
        key="citation.instructions",
        label="Citation instructions",
        description=(
            "Optional citation instruction block injected when citations are enabled."
        ),
        default_prompt=SURFSENSE_CITATION_INSTRUCTIONS,
    ),
    "router.top_level": PromptDefinition(
        key="router.top_level",
        label="Top-level router prompt",
        description="Initial route dispatch prompt (kunskap/skapande/jämförelse/konversation).",
        default_prompt=DEFAULT_ROUTE_SYSTEM_PROMPT,
    ),
    "agent.smalltalk.system": PromptDefinition(
        key="agent.smalltalk.system",
        label="Smalltalk instructions",
        description="Prompt used by the smalltalk fast path.",
        default_prompt=SMALLTALK_INSTRUCTIONS,
    ),
    "agent.supervisor.system": PromptDefinition(
        key="agent.supervisor.system",
        label="Supervisor prompt",
        description="System prompt for the supervisor agent.",
        default_prompt=DEFAULT_SUPERVISOR_PROMPT,
    ),
    "compare.supervisor.instructions": PromptDefinition(
        key="compare.supervisor.instructions",
        label="Compare supervisor mode instructions",
        description="Instruction block appended when compare route is active.",
        default_prompt=COMPARE_SUPERVISOR_INSTRUCTIONS,
    ),
    "supervisor.intent_resolver.system": PromptDefinition(
        key="supervisor.intent_resolver.system",
        label="Supervisor intent resolver prompt",
        description="Prompt for intent_resolver node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
    ),
    "supervisor.agent_resolver.system": PromptDefinition(
        key="supervisor.agent_resolver.system",
        label="Supervisor agent resolver prompt",
        description="Prompt for agent_resolver node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
    ),
    "supervisor.planner.system": PromptDefinition(
        key="supervisor.planner.system",
        label="Supervisor planner prompt",
        description="Prompt for planner node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_PLANNER_PROMPT,
    ),
    "supervisor.planner.multi_domain.system": PromptDefinition(
        key="supervisor.planner.multi_domain.system",
        label="Supervisor multi-domain planner prompt",
        description="Prompt for planner node when route=mixed with multiple sub_intents.",
        default_prompt=DEFAULT_SUPERVISOR_MULTI_DOMAIN_PLANNER_PROMPT,
    ),
    "supervisor.tool_resolver.system": PromptDefinition(
        key="supervisor.tool_resolver.system",
        label="Supervisor tool resolver prompt",
        description="Prompt for tool_resolver node in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_TOOL_RESOLVER_PROMPT,
    ),
    "supervisor.domain_planner.system": PromptDefinition(
        key="supervisor.domain_planner.system",
        label="Supervisor domain planner prompt",
        description="Prompt for domain_planner node — skapar mikro-plan per domänagent med verktygsval och parallellitet.",
        default_prompt=DEFAULT_SUPERVISOR_DOMAIN_PLANNER_PROMPT,
    ),
    "supervisor.critic_gate.system": PromptDefinition(
        key="supervisor.critic_gate.system",
        label="Supervisor critic gate prompt",
        description="Prompt for critic node decisioning in supervisor pipeline.",
        default_prompt=DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
    ),
    "supervisor.synthesizer.system": PromptDefinition(
        key="supervisor.synthesizer.system",
        label="Supervisor synthesizer prompt",
        description="Prompt for final supervisor synthesis step.",
        default_prompt=DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
    ),
    "supervisor.critic.system": PromptDefinition(
        key="supervisor.critic.system",
        label="Supervisor critic prompt",
        description="Prompt used by delegated-agent output critic.",
        default_prompt=DEFAULT_SUPERVISOR_CRITIC_PROMPT,
    ),
    "supervisor.loop_guard.message": PromptDefinition(
        key="supervisor.loop_guard.message",
        label="Supervisor loop guard message",
        description=(
            "Fallback response when supervisor detects repeated planning loops. "
            "Supports {recent_preview}."
        ),
        default_prompt=DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
    ),
    "supervisor.tool_limit_guard.message": PromptDefinition(
        key="supervisor.tool_limit_guard.message",
        label="Supervisor tool-limit guard message",
        description=(
            "Fallback response when too many tool calls happen in one turn. "
            "Supports {recent_preview}."
        ),
        default_prompt=DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
    ),
    "supervisor.trafik.enforcement.message": PromptDefinition(
        key="supervisor.trafik.enforcement.message",
        label="Supervisor trafik enforcement prompt",
        description="Injected retry instruction for strict trafik tool usage.",
        default_prompt=DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE,
    ),
    "supervisor.code.sandbox.enforcement.message": PromptDefinition(
        key="supervisor.code.sandbox.enforcement.message",
        label="Supervisor code sandbox enforcement prompt",
        description="Injected retry instruction for mandatory sandbox usage.",
        default_prompt=DEFAULT_SUPERVISOR_CODE_SANDBOX_ENFORCEMENT_MESSAGE,
    ),
    "supervisor.code.read_file.enforcement.message": PromptDefinition(
        key="supervisor.code.read_file.enforcement.message",
        label="Supervisor code read-file enforcement prompt",
        description="Injected retry instruction when explicit file reads are required.",
        default_prompt=DEFAULT_SUPERVISOR_CODE_READ_FILE_ENFORCEMENT_MESSAGE,
    ),
    "supervisor.scoped_tool_prompt.template": PromptDefinition(
        key="supervisor.scoped_tool_prompt.template",
        label="Supervisor scoped tool prompt template",
        description=(
            "Template to focus a worker on top-ranked tools. "
            "Placeholders: {tool_lines}, {agent_name}, {task}."
        ),
        default_prompt=DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE,
    ),
    "supervisor.tool_default_prompt.template": PromptDefinition(
        key="supervisor.tool_default_prompt.template",
        label="Supervisor tool default prompt template",
        description=(
            "Fallback template when no tool.{tool_id}.system override exists. "
            "Placeholders: {tool_id}, {category}, {description}, {keywords}."
        ),
        default_prompt=DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
    ),
    "supervisor.subagent.context.template": PromptDefinition(
        key="supervisor.subagent.context.template",
        label="Supervisor subagent context template",
        description=(
            "Template wrapped around delegated subagent tasks in isolation mode. "
            "Placeholders: {subagent_context_lines}, {subagent_id}, {route_hint}, "
            "{parent_query}, {preferred_tools}, {task}."
        ),
        default_prompt=DEFAULT_SUPERVISOR_SUBAGENT_CONTEXT_TEMPLATE,
    ),
    "supervisor.hitl.planner.message": PromptDefinition(
        key="supervisor.hitl.planner.message",
        label="Supervisor HITL planner confirmation message",
        description="User-facing confirmation message before planner output runs.",
        default_prompt=DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE,
    ),
    "supervisor.hitl.execution.message": PromptDefinition(
        key="supervisor.hitl.execution.message",
        label="Supervisor HITL execution confirmation message",
        description="User-facing confirmation message before executing next step.",
        default_prompt=DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE,
    ),
    "supervisor.hitl.synthesis.message": PromptDefinition(
        key="supervisor.hitl.synthesis.message",
        label="Supervisor HITL synthesis confirmation message",
        description="User-facing confirmation message before final delivery.",
        default_prompt=DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE,
    ),
    "agent.worker.knowledge": PromptDefinition(
        key="agent.worker.knowledge",
        label="Worker · Knowledge prompt",
        description="Base worker prompt for knowledge-oriented workers.",
        default_prompt=DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    ),
    "agent.knowledge.system": PromptDefinition(
        key="agent.knowledge.system",
        label="Kunskap-agent prompt",
        description="System-prompt for kunskap-agenten (SurfSense, Tavily, generell kunskap).",
        default_prompt=DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    ),
    "agent.worker.action": PromptDefinition(
        key="agent.worker.action",
        label="Worker · Action prompt",
        description="Base worker prompt for action-oriented workers.",
        default_prompt=DEFAULT_WORKER_ACTION_PROMPT,
    ),
    "agent.action.system": PromptDefinition(
        key="agent.action.system",
        label="Åtgärd-agent prompt",
        description="System-prompt for åtgärd-agenten (realtime-åtgärder, catch-all).",
        default_prompt=DEFAULT_WORKER_ACTION_PROMPT,
    ),
    "agent.media.system": PromptDefinition(
        key="agent.media.system",
        label="Media-agent prompt",
        description="System-prompt for media-agenten (podcast, bilder).",
        default_prompt=DEFAULT_WORKER_ACTION_PROMPT,
    ),
    "agent.browser.system": PromptDefinition(
        key="agent.browser.system",
        label="Webb-agent prompt",
        description="System-prompt for webb-agenten (webbsökning, scraping).",
        default_prompt=DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    ),
    "agent.code.system": PromptDefinition(
        key="agent.code.system",
        label="Kod-agent prompt",
        description="System-prompt for kod-agenten (sandbox, kalkyler).",
        default_prompt=DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    ),
    "agent.kartor.system": PromptDefinition(
        key="agent.kartor.system",
        label="Kartor-agent prompt",
        description="System-prompt for kartor-agenten (Geoapify, statiska kartor).",
        default_prompt=DEFAULT_WORKER_ACTION_PROMPT,
    ),
    "agent.statistics.system": PromptDefinition(
        key="agent.statistics.system",
        label="Statistik-agent prompt",
        description="System-prompt for statistik-agenten (SCB, Kolada).",
        default_prompt=DEFAULT_STATISTICS_SYSTEM_PROMPT,
    ),
    "agent.synthesis.system": PromptDefinition(
        key="agent.synthesis.system",
        label="Syntes-agent prompt",
        description="System-prompt for syntes-agenten (jämförelser, sammanfattningar).",
        default_prompt=DEFAULT_STATISTICS_SYSTEM_PROMPT,
    ),
    "agent.bolag.system": PromptDefinition(
        key="agent.bolag.system",
        label="Bolag-agent prompt",
        description="System-prompt for bolag-agenten (Bolagsverket).",
        default_prompt=DEFAULT_BOLAG_SYSTEM_PROMPT,
    ),
    "agent.trafik.system": PromptDefinition(
        key="agent.trafik.system",
        label="Trafik-agent prompt",
        description="System-prompt for trafik-agenten (Trafikverket realtid).",
        default_prompt=DEFAULT_TRAFFIC_SYSTEM_PROMPT,
    ),
    "agent.riksdagen.system": PromptDefinition(
        key="agent.riksdagen.system",
        label="Riksdagen-agent prompt",
        description="System-prompt for riksdagen-agenten (propositioner, voteringar).",
        default_prompt=DEFAULT_RIKSDAGEN_SYSTEM_PROMPT,
    ),
    "agent.marketplace.system": PromptDefinition(
        key="agent.marketplace.system",
        label="Marknad-agent prompt",
        description="System-prompt for marknad-agenten (Blocket, Tradera).",
        default_prompt=DEFAULT_MARKETPLACE_SYSTEM_PROMPT,
    ),
    "compare.analysis.system": PromptDefinition(
        key="compare.analysis.system",
        label="Compare analysis prompt",
        description="System prompt for compare analysis/synthesis flow.",
        default_prompt=DEFAULT_COMPARE_ANALYSIS_PROMPT,
    ),
    "compare.external.system": PromptDefinition(
        key="compare.external.system",
        label="Compare external model prompt",
        description="System prompt sent to external compare models.",
        default_prompt=DEFAULT_EXTERNAL_SYSTEM_PROMPT,
    ),
}


_missing_template_keys = [
    key for key in ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS if key not in _PROMPT_DEFINITIONS_BY_KEY
]
if _missing_template_keys:
    raise RuntimeError(
        "Prompt template keys missing definitions: " + ", ".join(_missing_template_keys)
    )
_unexpected_prompt_keys = sorted(
    set(_PROMPT_DEFINITIONS_BY_KEY) - set(ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS)
)
if _unexpected_prompt_keys:
    raise RuntimeError(
        "Unexpected prompt definitions outside template: "
        + ", ".join(_unexpected_prompt_keys)
    )


PROMPT_DEFINITIONS: list[PromptDefinition] = [
    _PROMPT_DEFINITIONS_BY_KEY[key] for key in ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS
]


PROMPT_DEFINITION_MAP = {definition.key: definition for definition in PROMPT_DEFINITIONS}
ACTIVE_PROMPT_DEFINITION_MAP = {
    definition.key: definition
    for definition in PROMPT_DEFINITIONS
    if definition.active_in_admin
}


def get_prompt_definitions(*, active_only: bool = False) -> list[PromptDefinition]:
    if active_only:
        return [
            definition
            for definition in PROMPT_DEFINITIONS
            if definition.active_in_admin
        ]
    return list(PROMPT_DEFINITIONS)


def get_oneseek_langsmith_prompt_template() -> list[PromptDefinition]:
    """Canonical prompt template used by the current OneSeek LangGraph flow."""
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
