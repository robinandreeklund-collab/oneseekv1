"""LangGraph Studio entrypoint for local SurfSense supervisor debugging.

This module exposes a LangGraph factory that can be referenced from
`langgraph.json` so the full supervisor graph can be inspected in
LangGraph/LangSmith Dev Studio on a local machine.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import replace
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, ConfigDict, Field, create_model
from sqlalchemy.future import select

from app.agents.new_chat.bigtool_prompts import (
    DEFAULT_WORKER_ACTION_PROMPT,
    DEFAULT_WORKER_KNOWLEDGE_PROMPT,
    build_worker_prompt,
)
from app.agents.new_chat.bolag_prompts import (
    DEFAULT_BOLAG_SYSTEM_PROMPT,
    build_bolag_prompt,
)
from app.agents.new_chat.compare_prompts import (
    DEFAULT_COMPARE_ANALYSIS_PROMPT,
    build_compare_synthesis_prompt,
)
from app.agents.new_chat.complete_graph import build_complete_graph
from app.agents.new_chat.llm_config import (
    AgentConfig,
    create_chat_litellm_from_agent_config,
    load_agent_config,
)
from app.agents.new_chat.marketplace_prompts import (
    DEFAULT_MARKETPLACE_SYSTEM_PROMPT,
    build_marketplace_prompt,
)
from app.agents.new_chat.prompt_registry import get_prompt_definitions, resolve_prompt
from app.agents.new_chat.riksdagen_prompts import DEFAULT_RIKSDAGEN_SYSTEM_PROMPT
from app.agents.new_chat.statistics_prompts import (
    DEFAULT_STATISTICS_SYSTEM_PROMPT,
    build_statistics_system_prompt,
)
from app.agents.new_chat.supervisor_prompts import (
    DEFAULT_SUPERVISOR_PROMPT,
    build_supervisor_prompt,
)
from app.agents.new_chat.system_prompt import (
    SURFSENSE_CITATION_INSTRUCTIONS,
    SURFSENSE_SYSTEM_INSTRUCTIONS,
)
from app.agents.new_chat.trafik_prompts import (
    DEFAULT_TRAFFIC_SYSTEM_PROMPT,
    build_trafik_prompt,
)
from app.agents.new_chat.tools.external_models import DEFAULT_EXTERNAL_SYSTEM_PROMPT
from app.db import SearchSpace, SearchSourceConnectorType, async_session_maker
from app.services.agent_prompt_service import get_global_prompt_overrides
from app.services.connector_service import ConnectorService

_DEFAULT_RUNTIME_HITL: dict[str, Any] = {
    "enabled": True,
    "hybrid_mode": True,
    "speculative_enabled": True,
    "subagent_enabled": True,
    "subagent_isolation_enabled": True,
    "subagent_max_concurrency": 3,
    "subagent_context_max_chars": 1400,
    "subagent_result_max_chars": 1000,
    "subagent_sandbox_scope": "subagent",
    "artifact_offload_enabled": True,
    "artifact_offload_storage_mode": "auto",
    "artifact_offload_threshold_chars": 4000,
    "context_compaction_enabled": True,
    "context_compaction_trigger_ratio": 0.65,
    "cross_session_memory_enabled": True,
    "cross_session_memory_max_items": 6,
    "sandbox_enabled": False,
    "sandbox_mode": "provisioner",
    "sandbox_state_store": "file",
    "sandbox_idle_timeout_seconds": 900,
}

_GRAPH_CACHE: dict[str, Any] = {}
_BUILD_LOCK: asyncio.Lock | None = None
_BUILD_LOCK_LOOP_ID: int | None = None
_SESSION = None

_PROMPT_NODE_GROUP_TO_GRAPH_NODES: dict[str, list[str]] = {
    "router": ["resolve_intent"],
    "supervisor": [
        "resolve_intent",
        "agent_resolver",
        "planner",
        "tool_resolver",
        "critic",
        "synthesizer",
    ],
    "subagent": ["executor"],
    "compare": ["compare_fan_out", "compare_synthesizer"],
    "system": ["executor"],
    "other": ["executor"],
}
_GRAPH_RELEVANT_PROMPT_GROUPS = {"router", "supervisor", "subagent", "compare", "system"}
_PROMPT_KEY_FIELD_NAME_OVERRIDES: dict[str, str] = {
    "agent.supervisor.system": "prompt_supervisor_system",
    "agent.knowledge.system": "prompt_knowledge_system",
    "agent.action.system": "prompt_action_system",
    "agent.statistics.system": "prompt_statistics_system",
    "agent.bolag.system": "prompt_bolag_system",
    "agent.trafik.system": "prompt_trafik_system",
    "agent.riksdagen.system": "prompt_riksdagen_system",
    "agent.marketplace.system": "prompt_marketplace_system",
    "compare.analysis.system": "prompt_compare_analysis_system",
    "compare.external.system": "prompt_compare_external_system",
}
_PROMPT_KEY_ENV_NAME_OVERRIDES: dict[str, str] = {
    "agent.supervisor.system": "STUDIO_PROMPT_SUPERVISOR_SYSTEM",
    "agent.knowledge.system": "STUDIO_PROMPT_KNOWLEDGE_SYSTEM",
    "agent.action.system": "STUDIO_PROMPT_ACTION_SYSTEM",
    "agent.statistics.system": "STUDIO_PROMPT_STATISTICS_SYSTEM",
    "agent.bolag.system": "STUDIO_PROMPT_BOLAG_SYSTEM",
    "agent.trafik.system": "STUDIO_PROMPT_TRAFIK_SYSTEM",
    "agent.riksdagen.system": "STUDIO_PROMPT_RIKSDAGEN_SYSTEM",
    "agent.marketplace.system": "STUDIO_PROMPT_MARKETPLACE_SYSTEM",
    "compare.analysis.system": "STUDIO_PROMPT_COMPARE_ANALYSIS_SYSTEM",
    "compare.external.system": "STUDIO_PROMPT_COMPARE_EXTERNAL_SYSTEM",
}


class StudioGraphConfigurationBase(BaseModel):
    """Base configurable values exposed in LangGraph Studio."""

    model_config = ConfigDict(extra="allow")

    search_space_id: int = Field(default=1, description="Search space id")
    llm_config_id: int = Field(default=-1, description="LLM config id")
    compare_mode: bool = Field(default=False, description="Enable compare mode graph")
    thread_id: str | int = Field(
        default=900000001,
        description="Thread id used in Studio (int or UUID string).",
    )
    user_id: str | None = Field(default=None, description="Optional forced user id")
    checkpointer_mode: str = Field(default="memory", description="memory or postgres")
    checkpoint_ns: str | None = Field(default=None, description="Checkpoint namespace")
    recursion_limit: int = Field(
        default=120,
        description="Graph recursion limit for Studio runs (default 120).",
    )
    citation_instructions: bool | str | None = Field(
        default=False,
        description="true/false or explicit citation instruction block",
    )
    hybrid_mode: bool | None = Field(default=None, description="Override hybrid_mode")
    speculative_enabled: bool | None = Field(
        default=None,
        description="Override speculative_enabled",
    )
    runtime_hitl: dict[str, Any] | str | None = Field(
        default=None,
        description="Runtime HITL overrides (dict or JSON string)",
    )
    prompt_overrides_json: str | None = Field(
        default=None,
        description="JSON object with prompt-key -> prompt-text overrides.",
        json_schema_extra={
            "langgraph_nodes": ["executor"],
            "langgraph_type": "prompt",
        },
    )


def _sanitize_prompt_key_for_field(prompt_key: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(prompt_key or "").strip().lower())
    normalized = normalized.strip("_")
    return normalized or "prompt"


def _prompt_field_name_for_key(prompt_key: str, *, used_names: set[str]) -> str:
    requested = _PROMPT_KEY_FIELD_NAME_OVERRIDES.get(prompt_key)
    if requested:
        candidate = requested
    else:
        candidate = f"prompt_{_sanitize_prompt_key_for_field(prompt_key)}"
    if candidate not in used_names:
        return candidate
    # Resolve rare collisions from sanitized keys.
    index = 2
    base_candidate = candidate
    while f"{base_candidate}_{index}" in used_names:
        index += 1
    return f"{base_candidate}_{index}"


def _prompt_env_name_for_field(prompt_key: str, field_name: str) -> str:
    requested = _PROMPT_KEY_ENV_NAME_OVERRIDES.get(prompt_key)
    if requested:
        return requested
    return f"STUDIO_{field_name.upper()}"


def _build_studio_prompt_field_specs() -> tuple[dict[str, tuple[str, str]], dict[str, Any]]:
    config_fields: dict[str, tuple[str, str]] = {}
    model_fields: dict[str, Any] = {}
    used_field_names: set[str] = set()
    # Keep Studio/LangSmith prompt exposure aligned with the active OneSeek template.
    prompt_definitions = get_prompt_definitions(active_only=True)
    for definition in prompt_definitions:
        if definition.node_group not in _GRAPH_RELEVANT_PROMPT_GROUPS:
            continue
        prompt_key = str(definition.key).strip()
        if not prompt_key:
            continue
        field_name = _prompt_field_name_for_key(prompt_key, used_names=used_field_names)
        used_field_names.add(field_name)
        env_name = _prompt_env_name_for_field(prompt_key, field_name)
        config_fields[field_name] = (prompt_key, env_name)
        graph_nodes = _PROMPT_NODE_GROUP_TO_GRAPH_NODES.get(
            definition.node_group,
            ["executor"],
        )
        model_fields[field_name] = (
            str | None,
            Field(
                default=definition.default_prompt,
                description=f"{definition.label} ({prompt_key})",
                json_schema_extra={
                    "langgraph_type": "prompt",
                    "langgraph_nodes": graph_nodes,
                    "prompt_key": prompt_key,
                    "prompt_node_group": definition.node_group,
                },
            ),
        )
    return config_fields, model_fields


_STUDIO_PROMPT_CONFIG_FIELDS, _STUDIO_PROMPT_MODEL_FIELDS = _build_studio_prompt_field_specs()

StudioGraphConfiguration = create_model(
    "StudioGraphConfiguration",
    __base__=StudioGraphConfigurationBase,
    **_STUDIO_PROMPT_MODEL_FIELDS,
)


def _parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def _parse_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _parse_thread_id(value: Any, *, default: str | int) -> str | int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    normalized = str(value).strip()
    if not normalized:
        return default
    if re.fullmatch(r"-?\d+", normalized):
        try:
            return int(normalized)
        except Exception:
            return default
    return normalized


def _resolve_studio_recursion_limit(configurable: dict[str, Any]) -> int:
    configured_value = configurable.get("recursion_limit")
    configured_limit: int | None = None
    if configured_value is not None and str(configured_value).strip() != "":
        configured_limit = _parse_int(configured_value, default=120)

    env_value = os.getenv("STUDIO_RECURSION_LIMIT")
    env_limit: int | None = None
    if env_value is not None and str(env_value).strip() != "":
        env_limit = _parse_int(env_value, default=120)

    if configured_limit is None and env_limit is None:
        chosen_limit = 120
    elif configured_limit is None:
        chosen_limit = int(env_limit or 120)
    elif env_limit is None:
        chosen_limit = int(configured_limit)
    else:
        # In Studio, environment recursion limit acts as a safety floor so
        # stale UI-configured low values cannot silently cap complex runs.
        chosen_limit = max(int(configured_limit), int(env_limit))

    return max(25, min(2000, int(chosen_limit)))


def _first_value(
    configurable: dict[str, Any],
    key: str,
    *,
    env_name: str,
    default: Any,
) -> Any:
    if key in configurable:
        return configurable.get(key)
    env_value = os.getenv(env_name)
    if env_value is not None and str(env_value).strip() != "":
        return env_value
    return default


def _json_override(
    configurable: dict[str, Any],
    *,
    key: str,
    env_name: str,
) -> dict[str, Any]:
    raw = configurable.get(key)
    if raw is None:
        raw = os.getenv(env_name)
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except Exception:
        return {}
    if isinstance(parsed, dict):
        return dict(parsed)
    return {}


def _collect_studio_prompt_overrides(configurable: dict[str, Any]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    # Allow arbitrary prompt key overrides via JSON.
    json_payload = _json_override(
        configurable,
        key="prompt_overrides_json",
        env_name="STUDIO_PROMPT_OVERRIDES_JSON",
    )
    for prompt_key, prompt_text in json_payload.items():
        normalized_key = str(prompt_key or "").strip()
        normalized_text = str(prompt_text or "").strip()
        if normalized_key and normalized_text:
            overrides[normalized_key] = normalized_text

    # And provide direct Studio fields for the most common prompts.
    for field_name, (prompt_key, env_name) in _STUDIO_PROMPT_CONFIG_FIELDS.items():
        raw_value = _first_value(
            configurable,
            field_name,
            env_name=env_name,
            default=None,
        )
        if raw_value is None:
            continue
        normalized_text = str(raw_value).strip()
        if normalized_text:
            overrides[prompt_key] = normalized_text
    return overrides


async def _get_session():
    global _SESSION
    if _SESSION is None:
        _SESSION = async_session_maker()
    try:
        await _SESSION.rollback()
    except Exception:
        pass
    return _SESSION


def _get_build_lock() -> asyncio.Lock:
    """Return a loop-local build lock for async graph construction."""
    global _BUILD_LOCK, _BUILD_LOCK_LOOP_ID
    running_loop = asyncio.get_running_loop()
    running_loop_id = id(running_loop)
    if _BUILD_LOCK is None or _BUILD_LOCK_LOOP_ID != running_loop_id:
        _BUILD_LOCK = asyncio.Lock()
        _BUILD_LOCK_LOOP_ID = running_loop_id
    return _BUILD_LOCK


async def _resolve_user_id(
    *,
    session,
    search_space_id: int,
    configured_user_id: str | None,
) -> str | None:
    explicit = str(configured_user_id or "").strip()
    if explicit:
        return explicit
    try:
        result = await session.execute(
            select(SearchSpace).filter(SearchSpace.id == search_space_id).limit(1)
        )
        search_space = result.scalars().first()
    except Exception:
        search_space = None
    if search_space and getattr(search_space, "user_id", None):
        return str(search_space.user_id)
    return None


async def _resolve_firecrawl_key(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
) -> str | None:
    try:
        webcrawler_connector = await connector_service.get_connector_by_type(
            SearchSourceConnectorType.WEBCRAWLER_CONNECTOR,
            search_space_id,
        )
    except Exception:
        return None
    if webcrawler_connector and webcrawler_connector.config:
        return str(webcrawler_connector.config.get("FIRECRAWL_API_KEY") or "").strip() or None
    return None


async def _build_studio_graph(config: dict[str, Any] | None = None):
    config = config or {}
    configurable = (
        dict(config.get("configurable") or {})
        if isinstance(config, dict)
        else {}
    )
    search_space_id = _parse_int(
        _first_value(
            configurable,
            "search_space_id",
            env_name="STUDIO_SEARCH_SPACE_ID",
            default=1,
        ),
        default=1,
    )
    llm_config_id = _parse_int(
        _first_value(
            configurable,
            "llm_config_id",
            env_name="STUDIO_LLM_CONFIG_ID",
            default=-1,
        ),
        default=-1,
    )
    compare_mode = _parse_bool(
        _first_value(
            configurable,
            "compare_mode",
            env_name="STUDIO_COMPARE_MODE",
            default=False,
        ),
        default=False,
    )
    thread_id = _parse_thread_id(
        _first_value(
            configurable,
            "thread_id",
            env_name="STUDIO_THREAD_ID",
            default=900000001,
        ),
        default=900000001,
    )
    recursion_limit = _resolve_studio_recursion_limit(configurable)
    user_id = await _resolve_user_id(
        session=await _get_session(),
        search_space_id=search_space_id,
        configured_user_id=str(
            _first_value(
                configurable,
                "user_id",
                env_name="STUDIO_USER_ID",
                default="",
            )
            or ""
        ).strip(),
    )
    session = await _get_session()
    try:
        prompt_overrides = await get_global_prompt_overrides(session)
    except Exception:
        # Local Studio should stay usable even when DB access is unavailable
        # (e.g. Windows blocker detects a sync call inside the DB driver path).
        prompt_overrides = {}
    runtime_prompt_overrides = _collect_studio_prompt_overrides(configurable)
    if runtime_prompt_overrides:
        # Studio-configurable prompt overrides should always win over DB defaults.
        prompt_overrides = {**prompt_overrides, **runtime_prompt_overrides}

    agent_config = await load_agent_config(
        session=session,
        config_id=llm_config_id,
        search_space_id=search_space_id,
    )
    if not agent_config and llm_config_id >= 0:
        # Studio should stay usable even when DB-backed config lookup fails.
        # Fallback to YAML/global default profile for local debugging sessions.
        agent_config = await load_agent_config(
            session=session,
            config_id=-1,
            search_space_id=search_space_id,
        )
    if not agent_config:
        raise RuntimeError(
            "Could not load LLM config for Studio. "
            "Set STUDIO_LLM_CONFIG_ID (or configurable.llm_config_id) to a valid config, "
            "or ensure global YAML config id -1 exists."
        )
    llm = create_chat_litellm_from_agent_config(agent_config)
    if not llm:
        raise RuntimeError("Could not create LLM instance for LangGraph Studio.")

    default_system_prompt = resolve_prompt(
        prompt_overrides,
        "system.default.instructions",
        SURFSENSE_SYSTEM_INSTRUCTIONS,
    )
    has_custom_system_prompt = bool(str(agent_config.system_instructions or "").strip())
    if agent_config.use_default_system_instructions and not has_custom_system_prompt:
        agent_config = replace(
            agent_config,
            system_instructions=default_system_prompt,
            use_default_system_instructions=False,
        )

    citation_instructions_value = _first_value(
        configurable,
        "citation_instructions",
        env_name="STUDIO_CITATION_INSTRUCTIONS",
        default=False,
    )
    citation_prompt_default = resolve_prompt(
        prompt_overrides,
        "citation.instructions",
        SURFSENSE_CITATION_INSTRUCTIONS,
    )
    if isinstance(citation_instructions_value, bool):
        citation_instructions_block = (
            citation_prompt_default.strip() if citation_instructions_value else None
        )
    else:
        explicit_citation_instructions = str(citation_instructions_value or "").strip()
        citation_instructions_block = (
            explicit_citation_instructions if explicit_citation_instructions else None
        )
    citations_enabled = bool(citation_instructions_block)

    supervisor_prompt = resolve_prompt(
        prompt_overrides,
        "agent.supervisor.system",
        DEFAULT_SUPERVISOR_PROMPT,
    )
    supervisor_system_prompt = build_supervisor_prompt(
        supervisor_prompt,
        citation_instructions=citation_instructions_block,
    )

    knowledge_prompt = resolve_prompt(
        prompt_overrides,
        "agent.knowledge.system",
        resolve_prompt(
            prompt_overrides,
            "agent.worker.knowledge",
            DEFAULT_WORKER_KNOWLEDGE_PROMPT,
        ),
    )
    knowledge_worker_prompt = build_worker_prompt(
        knowledge_prompt,
        citations_enabled=citations_enabled,
        citation_instructions=citation_instructions_block,
    )
    action_prompt = resolve_prompt(
        prompt_overrides,
        "agent.action.system",
        resolve_prompt(
            prompt_overrides,
            "agent.worker.action",
            DEFAULT_WORKER_ACTION_PROMPT,
        ),
    )
    action_worker_prompt = build_worker_prompt(
        action_prompt,
        citations_enabled=citations_enabled,
        citation_instructions=citation_instructions_block,
    )
    media_prompt = resolve_prompt(
        prompt_overrides,
        "agent.media.system",
        action_prompt,
    )
    browser_prompt = resolve_prompt(
        prompt_overrides,
        "agent.browser.system",
        knowledge_prompt,
    )
    code_prompt = resolve_prompt(
        prompt_overrides,
        "agent.code.system",
        knowledge_prompt,
    )
    kartor_prompt = resolve_prompt(
        prompt_overrides,
        "agent.kartor.system",
        action_prompt,
    )
    statistics_prompt = resolve_prompt(
        prompt_overrides,
        "agent.statistics.system",
        DEFAULT_STATISTICS_SYSTEM_PROMPT,
    )
    statistics_worker_prompt = build_statistics_system_prompt(
        statistics_prompt,
        citation_instructions=citation_instructions_block,
    )
    synthesis_prompt = resolve_prompt(
        prompt_overrides,
        "agent.synthesis.system",
        statistics_prompt,
    )
    bolag_prompt = resolve_prompt(
        prompt_overrides,
        "agent.bolag.system",
        DEFAULT_BOLAG_SYSTEM_PROMPT,
    )
    bolag_worker_prompt = build_bolag_prompt(
        bolag_prompt,
        citation_instructions=citation_instructions_block,
    )
    trafik_prompt = resolve_prompt(
        prompt_overrides,
        "agent.trafik.system",
        DEFAULT_TRAFFIC_SYSTEM_PROMPT,
    )
    trafik_worker_prompt = build_trafik_prompt(
        trafik_prompt,
        citation_instructions=citation_instructions_block,
    )
    riksdagen_prompt = resolve_prompt(
        prompt_overrides,
        "agent.riksdagen.system",
        DEFAULT_RIKSDAGEN_SYSTEM_PROMPT,
    )
    riksdagen_worker_prompt = build_worker_prompt(
        riksdagen_prompt,
        citations_enabled=citations_enabled,
        citation_instructions=citation_instructions_block,
    )
    marketplace_prompt = resolve_prompt(
        prompt_overrides,
        "agent.marketplace.system",
        DEFAULT_MARKETPLACE_SYSTEM_PROMPT,
    )
    marketplace_worker_prompt = build_marketplace_prompt(
        marketplace_prompt,
        citation_instructions=citation_instructions_block,
    )
    compare_analysis_prompt = resolve_prompt(
        prompt_overrides,
        "compare.analysis.system",
        DEFAULT_COMPARE_ANALYSIS_PROMPT,
    )
    compare_synthesis_prompt = build_compare_synthesis_prompt(
        compare_analysis_prompt,
        citations_enabled=citations_enabled,
        citation_instructions=citation_instructions_block,
    )
    compare_external_prompt = resolve_prompt(
        prompt_overrides,
        "compare.external.system",
        DEFAULT_EXTERNAL_SYSTEM_PROMPT,
    )

    runtime_hitl = dict(_DEFAULT_RUNTIME_HITL)
    runtime_hitl.update(_json_override(configurable, key="runtime_hitl", env_name="STUDIO_RUNTIME_HITL_JSON"))
    runtime_hitl["hybrid_mode"] = _parse_bool(
        _first_value(
            configurable,
            "hybrid_mode",
            env_name="STUDIO_HYBRID_MODE",
            default=runtime_hitl.get("hybrid_mode", True),
        ),
        default=bool(runtime_hitl.get("hybrid_mode", True)),
    )
    runtime_hitl["speculative_enabled"] = _parse_bool(
        _first_value(
            configurable,
            "speculative_enabled",
            env_name="STUDIO_SPECULATIVE_ENABLED",
            default=runtime_hitl.get("speculative_enabled", True),
        ),
        default=bool(runtime_hitl.get("speculative_enabled", True)),
    )

    connector_service = ConnectorService(
        session,
        search_space_id=search_space_id,
        user_id=user_id,
    )
    firecrawl_api_key = await _resolve_firecrawl_key(
        connector_service=connector_service,
        search_space_id=search_space_id,
    )

    checkpointer_mode = str(
        _first_value(
            configurable,
            "checkpointer_mode",
            env_name="STUDIO_CHECKPOINTER_MODE",
            default="memory",
        )
        or "memory"
    ).strip().lower()
    checkpoint_ns = str(
        _first_value(
            configurable,
            "checkpoint_ns",
            env_name="STUDIO_CHECKPOINT_NS",
            default="",
        )
        or ""
    ).strip()
    if checkpointer_mode in {"postgres", "pg", "database"}:
        from app.agents.new_chat.checkpointer import (
            build_checkpoint_namespace,
            get_checkpointer,
            resolve_checkpoint_namespace_for_thread,
        )

        checkpointer = await get_checkpointer()
        preferred_checkpoint_ns = checkpoint_ns or build_checkpoint_namespace(
            user_id=user_id,
            flow="langgraph_studio",
        )
        checkpoint_ns = await resolve_checkpoint_namespace_for_thread(
            checkpointer=checkpointer,
            thread_id=thread_id,
            preferred_namespace=preferred_checkpoint_ns,
        )
    else:
        checkpointer = MemorySaver()
        if not checkpoint_ns:
            checkpoint_ns = "langgraph_studio_local"

    graph = await build_complete_graph(
        llm=llm,
        dependencies={
            "search_space_id": search_space_id,
            "db_session": session,
            "connector_service": connector_service,
            "firecrawl_api_key": firecrawl_api_key,
            "user_id": user_id,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "runtime_hitl": runtime_hitl,
            "trace_recorder": None,
            "trace_parent_span_id": None,
        },
        checkpointer=checkpointer,
        config_schema=StudioGraphConfiguration,
        knowledge_prompt=knowledge_worker_prompt,
        action_prompt=action_worker_prompt,
        statistics_prompt=statistics_worker_prompt,
        synthesis_prompt=compare_synthesis_prompt or synthesis_prompt,
        compare_mode=compare_mode,
        hybrid_mode=bool(runtime_hitl.get("hybrid_mode")),
        speculative_enabled=bool(runtime_hitl.get("speculative_enabled")),
        external_model_prompt=compare_external_prompt,
        bolag_prompt=bolag_worker_prompt,
        trafik_prompt=trafik_worker_prompt,
        media_prompt=build_worker_prompt(
            media_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        ),
        browser_prompt=build_worker_prompt(
            browser_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        ),
        code_prompt=build_worker_prompt(
            code_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        ),
        kartor_prompt=build_worker_prompt(
            kartor_prompt,
            citations_enabled=citations_enabled,
            citation_instructions=citation_instructions_block,
        ),
        riksdagen_prompt=riksdagen_worker_prompt,
        marketplace_prompt=marketplace_worker_prompt,
        tool_prompt_overrides=prompt_overrides,
    )
    return graph.with_config({"recursion_limit": recursion_limit})


async def make_studio_graph_async(config: dict[str, Any] | None = None):
    config = config or {}
    configurable = (
        dict(config.get("configurable") or {})
        if isinstance(config, dict)
        else {}
    )
    cache_key = json.dumps(
        {
            "search_space_id": configurable.get("search_space_id", os.getenv("STUDIO_SEARCH_SPACE_ID", 1)),
            "llm_config_id": configurable.get("llm_config_id", os.getenv("STUDIO_LLM_CONFIG_ID", -1)),
            "thread_id": configurable.get("thread_id", os.getenv("STUDIO_THREAD_ID", 900000001)),
            "recursion_limit": _resolve_studio_recursion_limit(configurable),
            "compare_mode": configurable.get("compare_mode", os.getenv("STUDIO_COMPARE_MODE", False)),
            "checkpointer_mode": configurable.get("checkpointer_mode", os.getenv("STUDIO_CHECKPOINTER_MODE", "memory")),
            "checkpoint_ns": configurable.get("checkpoint_ns", os.getenv("STUDIO_CHECKPOINT_NS", "")),
            "runtime_hitl": configurable.get("runtime_hitl", os.getenv("STUDIO_RUNTIME_HITL_JSON", "")),
            "prompt_overrides_json": configurable.get(
                "prompt_overrides_json", os.getenv("STUDIO_PROMPT_OVERRIDES_JSON", "")
            ),
            "prompt_field_overrides": {
                field_name: configurable.get(field_name, os.getenv(env_name, ""))
                for field_name, (_prompt_key, env_name) in _STUDIO_PROMPT_CONFIG_FIELDS.items()
            },
        },
        sort_keys=True,
        default=str,
    )
    if cache_key in _GRAPH_CACHE:
        return _GRAPH_CACHE[cache_key]
    async with _get_build_lock():
        if cache_key in _GRAPH_CACHE:
            return _GRAPH_CACHE[cache_key]
        graph = await _build_studio_graph(config)
        _GRAPH_CACHE[cache_key] = graph
        return graph


def make_studio_graph(config: dict[str, Any] | None = None):
    """LangGraph Studio factory.

    Return the coroutine so LangGraph API can await it on the active runtime loop.
    This avoids cross-loop resources when building and executing the graph.
    """
    return make_studio_graph_async(config)
