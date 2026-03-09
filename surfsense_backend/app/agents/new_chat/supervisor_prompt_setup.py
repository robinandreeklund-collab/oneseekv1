"""Prompt resolution for the supervisor agent.

Extracts all prompt template resolution from ``create_supervisor_agent()``
into a single function that returns a dict of resolved prompt strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResolvedPrompts:
    """All resolved prompt templates for the supervisor pipeline."""

    core: str
    use_structured: bool

    # Runtime / enforcement prompts
    critic_prompt_template: str
    loop_guard_template: str
    tool_limit_guard_template: str
    trafik_enforcement_message: str
    code_sandbox_enforcement_message: str
    code_read_file_enforcement_message: str
    scoped_tool_prompt_template: str
    tool_default_prompt_template: str
    subagent_context_prompt_template: str

    # Pipeline node prompts
    intent_resolver_prompt_template: str
    decomposer_prompt_template: str
    agent_resolver_prompt_template: str
    planner_prompt_template: str
    multi_domain_planner_prompt_template: str
    tool_resolver_prompt_template: str
    critic_gate_prompt_template: str
    domain_planner_prompt_template: str
    synthesizer_prompt_template: str

    # Response layer prompts
    response_layer_kunskap_prompt: str
    response_layer_analys_prompt: str
    response_layer_syntes_prompt: str
    response_layer_visualisering_prompt: str
    response_layer_router_prompt: str

    # Compare mode prompts
    compare_synthesizer_prompt_template: str
    compare_domain_planner_prompt: str
    compare_mini_planner_prompt: str
    compare_mini_critic_prompt: str
    compare_convergence_prompt: str
    criterion_prompt_overrides: dict[str, str] = field(default_factory=dict)
    research_synthesis_prompt: str | None = None

    # Debate mode prompts
    debate_synthesizer_prompt_template: str = ""
    debate_convergence_prompt: str = ""
    debate_mini_critic_prompt: str = ""

    # HITL prompts
    hitl_planner_message_template: str = ""
    hitl_execution_message_template: str = ""
    hitl_synthesis_message_template: str = ""

    # Smalltalk
    smalltalk_prompt_template: str = ""


def resolve_all_prompts(
    *,
    tool_prompt_overrides: dict[str, str] | None = None,
) -> ResolvedPrompts:
    """Resolve all supervisor prompt templates.

    Returns a frozen ``ResolvedPrompts`` dataclass with every template
    needed by the supervisor pipeline.
    """
    from app.agents.new_chat.compare_prompts import (
        DEFAULT_COMPARE_ANALYSIS_PROMPT,
        DEFAULT_COMPARE_CONVERGENCE_PROMPT,
        DEFAULT_COMPARE_CRITERION_DJUP_PROMPT,
        DEFAULT_COMPARE_CRITERION_KLARHET_PROMPT,
        DEFAULT_COMPARE_CRITERION_KORREKTHET_PROMPT,
        DEFAULT_COMPARE_CRITERION_RELEVANS_PROMPT,
        DEFAULT_COMPARE_DOMAIN_PLANNER_PROMPT,
        DEFAULT_COMPARE_MINI_CRITIC_PROMPT,
        DEFAULT_COMPARE_MINI_PLANNER_PROMPT,
        DEFAULT_COMPARE_RESEARCH_PROMPT,
    )
    from app.agents.new_chat.debate_prompts import (
        DEFAULT_DEBATE_ANALYSIS_PROMPT,
        DEFAULT_DEBATE_CONVERGENCE_PROMPT,
        DEFAULT_DEBATE_MINI_CRITIC_PROMPT,
    )
    from app.agents.new_chat.prompt_registry import resolve_prompt
    from app.agents.new_chat.structured_schemas import structured_output_enabled
    from app.agents.new_chat.subagent_utils import SMALLTALK_INSTRUCTIONS
    from app.agents.new_chat.supervisor_pipeline_prompts import (
        DEFAULT_RESPONSE_LAYER_ANALYS_PROMPT,
        DEFAULT_RESPONSE_LAYER_KUNSKAP_PROMPT,
        DEFAULT_RESPONSE_LAYER_ROUTER_PROMPT,
        DEFAULT_RESPONSE_LAYER_SYNTES_PROMPT,
        DEFAULT_RESPONSE_LAYER_VISUALISERING_PROMPT,
        DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
        DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
        DEFAULT_SUPERVISOR_DECOMPOSER_PROMPT,
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
    from app.agents.new_chat.system_prompt import (
        SURFSENSE_CORE_GLOBAL_PROMPT,
        append_datetime_context,
        inject_core_prompt,
    )

    prompt_overrides = dict(tool_prompt_overrides or {})

    _raw_core = resolve_prompt(
        prompt_overrides,
        "system.core.global",
        SURFSENSE_CORE_GLOBAL_PROMPT,
    )
    _core = append_datetime_context(_raw_core.strip())
    _use_structured = structured_output_enabled()

    # -- Runtime / enforcement --
    critic_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.critic.system",
            DEFAULT_SUPERVISOR_CRITIC_PROMPT,
        ),
    )
    loop_guard_template = resolve_prompt(
        prompt_overrides,
        "supervisor.loop_guard.message",
        DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
    )
    tool_limit_guard_template = resolve_prompt(
        prompt_overrides,
        "supervisor.tool_limit_guard.message",
        DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
    )
    trafik_enforcement_message = resolve_prompt(
        prompt_overrides,
        "supervisor.trafik.enforcement.message",
        DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE,
    )
    code_sandbox_enforcement_message = resolve_prompt(
        prompt_overrides,
        "supervisor.code.sandbox.enforcement.message",
        DEFAULT_SUPERVISOR_CODE_SANDBOX_ENFORCEMENT_MESSAGE,
    )
    code_read_file_enforcement_message = resolve_prompt(
        prompt_overrides,
        "supervisor.code.read_file.enforcement.message",
        DEFAULT_SUPERVISOR_CODE_READ_FILE_ENFORCEMENT_MESSAGE,
    )
    scoped_tool_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.scoped_tool_prompt.template",
        DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE,
    )
    tool_default_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.tool_default_prompt.template",
        DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE,
    )
    subagent_context_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.subagent.context.template",
        DEFAULT_SUPERVISOR_SUBAGENT_CONTEXT_TEMPLATE,
    )

    # -- Pipeline node prompts --
    intent_resolver_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.intent_resolver.system",
            DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    decomposer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.decomposer.system",
            DEFAULT_SUPERVISOR_DECOMPOSER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    agent_resolver_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.agent_resolver.system",
            DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.planner.system",
            DEFAULT_SUPERVISOR_PLANNER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    multi_domain_planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.planner.multi_domain.system",
            DEFAULT_SUPERVISOR_MULTI_DOMAIN_PLANNER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    tool_resolver_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.tool_resolver.system",
            DEFAULT_SUPERVISOR_TOOL_RESOLVER_PROMPT,
        ),
    )
    critic_gate_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.critic_gate.system",
            DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
        ),
        structured_output=_use_structured,
    )
    domain_planner_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.domain_planner.system",
            DEFAULT_SUPERVISOR_DOMAIN_PLANNER_PROMPT,
        ),
        structured_output=_use_structured,
    )
    synthesizer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.synthesizer.system",
            DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
        ),
        structured_output=_use_structured,
    )

    # -- Response layer --
    response_layer_kunskap_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.kunskap",
            DEFAULT_RESPONSE_LAYER_KUNSKAP_PROMPT,
        ),
    )
    response_layer_analys_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.analys",
            DEFAULT_RESPONSE_LAYER_ANALYS_PROMPT,
        ),
    )
    response_layer_syntes_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.syntes",
            DEFAULT_RESPONSE_LAYER_SYNTES_PROMPT,
        ),
    )
    response_layer_visualisering_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.visualisering",
            DEFAULT_RESPONSE_LAYER_VISUALISERING_PROMPT,
        ),
    )
    response_layer_router_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "supervisor.response_layer.router",
            DEFAULT_RESPONSE_LAYER_ROUTER_PROMPT,
        ),
        structured_output=_use_structured,
    )

    # -- Compare mode --
    compare_synthesizer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "compare.analysis.system",
            DEFAULT_COMPARE_ANALYSIS_PROMPT,
        ),
    )
    compare_domain_planner_prompt = resolve_prompt(
        prompt_overrides,
        "compare.domain_planner.system",
        DEFAULT_COMPARE_DOMAIN_PLANNER_PROMPT,
    )
    compare_mini_planner_prompt = resolve_prompt(
        prompt_overrides,
        "compare.mini_planner.system",
        DEFAULT_COMPARE_MINI_PLANNER_PROMPT,
    )
    compare_mini_critic_prompt = resolve_prompt(
        prompt_overrides,
        "compare.mini_critic.system",
        DEFAULT_COMPARE_MINI_CRITIC_PROMPT,
    )
    compare_convergence_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "compare.convergence.system",
            DEFAULT_COMPARE_CONVERGENCE_PROMPT,
        ),
    )

    # Per-criterion evaluator prompts (admin-editable)
    criterion_prompt_overrides: dict[str, str] = {}
    for crit, default in [
        ("relevans", DEFAULT_COMPARE_CRITERION_RELEVANS_PROMPT),
        ("djup", DEFAULT_COMPARE_CRITERION_DJUP_PROMPT),
        ("klarhet", DEFAULT_COMPARE_CRITERION_KLARHET_PROMPT),
        ("korrekthet", DEFAULT_COMPARE_CRITERION_KORREKTHET_PROMPT),
    ]:
        resolved = resolve_prompt(
            prompt_overrides,
            f"compare.criterion.{crit}",
            default,
        )
        if resolved != default:
            criterion_prompt_overrides[crit] = resolved

    # Research synthesis prompt (admin-editable)
    _research_resolved = resolve_prompt(
        prompt_overrides,
        "compare.research.system",
        DEFAULT_COMPARE_RESEARCH_PROMPT,
    )
    research_synthesis_prompt: str | None = (
        _research_resolved
        if _research_resolved != DEFAULT_COMPARE_RESEARCH_PROMPT
        else None
    )

    # -- Debate mode --
    debate_synthesizer_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "debate.analysis.system",
            DEFAULT_DEBATE_ANALYSIS_PROMPT,
        ),
    )
    debate_convergence_prompt = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "debate.convergence.system",
            DEFAULT_DEBATE_CONVERGENCE_PROMPT,
        ),
    )
    debate_mini_critic_prompt = resolve_prompt(
        prompt_overrides,
        "debate.mini_critic.system",
        DEFAULT_DEBATE_MINI_CRITIC_PROMPT,
    )

    # -- HITL --
    hitl_planner_message_template = resolve_prompt(
        prompt_overrides,
        "supervisor.hitl.planner.message",
        DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE,
    )
    hitl_execution_message_template = resolve_prompt(
        prompt_overrides,
        "supervisor.hitl.execution.message",
        DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE,
    )
    hitl_synthesis_message_template = resolve_prompt(
        prompt_overrides,
        "supervisor.hitl.synthesis.message",
        DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE,
    )

    # -- Smalltalk --
    smalltalk_prompt_template = inject_core_prompt(
        _core,
        resolve_prompt(
            prompt_overrides,
            "agent.smalltalk.system",
            SMALLTALK_INSTRUCTIONS,
        ),
        include_think_instructions=False,
    )

    return ResolvedPrompts(
        core=_core,
        use_structured=_use_structured,
        critic_prompt_template=critic_prompt_template,
        loop_guard_template=loop_guard_template,
        tool_limit_guard_template=tool_limit_guard_template,
        trafik_enforcement_message=trafik_enforcement_message,
        code_sandbox_enforcement_message=code_sandbox_enforcement_message,
        code_read_file_enforcement_message=code_read_file_enforcement_message,
        scoped_tool_prompt_template=scoped_tool_prompt_template,
        tool_default_prompt_template=tool_default_prompt_template,
        subagent_context_prompt_template=subagent_context_prompt_template,
        intent_resolver_prompt_template=intent_resolver_prompt_template,
        decomposer_prompt_template=decomposer_prompt_template,
        agent_resolver_prompt_template=agent_resolver_prompt_template,
        planner_prompt_template=planner_prompt_template,
        multi_domain_planner_prompt_template=multi_domain_planner_prompt_template,
        tool_resolver_prompt_template=tool_resolver_prompt_template,
        critic_gate_prompt_template=critic_gate_prompt_template,
        domain_planner_prompt_template=domain_planner_prompt_template,
        synthesizer_prompt_template=synthesizer_prompt_template,
        response_layer_kunskap_prompt=response_layer_kunskap_prompt,
        response_layer_analys_prompt=response_layer_analys_prompt,
        response_layer_syntes_prompt=response_layer_syntes_prompt,
        response_layer_visualisering_prompt=response_layer_visualisering_prompt,
        response_layer_router_prompt=response_layer_router_prompt,
        compare_synthesizer_prompt_template=compare_synthesizer_prompt_template,
        compare_domain_planner_prompt=compare_domain_planner_prompt,
        compare_mini_planner_prompt=compare_mini_planner_prompt,
        compare_mini_critic_prompt=compare_mini_critic_prompt,
        compare_convergence_prompt=compare_convergence_prompt,
        criterion_prompt_overrides=criterion_prompt_overrides,
        research_synthesis_prompt=research_synthesis_prompt,
        debate_synthesizer_prompt_template=debate_synthesizer_prompt_template,
        debate_convergence_prompt=debate_convergence_prompt,
        debate_mini_critic_prompt=debate_mini_critic_prompt,
        hitl_planner_message_template=hitl_planner_message_template,
        hitl_execution_message_template=hitl_execution_message_template,
        hitl_synthesis_message_template=hitl_synthesis_message_template,
        smalltalk_prompt_template=smalltalk_prompt_template,
    )
