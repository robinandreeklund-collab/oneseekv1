from __future__ import annotations

import asyncio
import json
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.types import Checkpointer
from langgraph_bigtool.graph import END, StateGraph, ToolNode, RunnableCallable
from langgraph_bigtool.tools import InjectedState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.bigtool_store import _tokenize, _normalize_text
from app.agents.new_chat.bigtool_workers import WorkerConfig, create_bigtool_worker
from app.agents.new_chat.lazy_worker_pool import LazyWorkerPool
from app.agents.new_chat.response_compressor import compress_response
from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
from app.agents.new_chat.token_budget import TokenBudget
from app.agents.new_chat.statistics_prompts import build_statistics_system_prompt
from app.agents.new_chat.system_prompt import append_datetime_context
from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.external_models import (
    DEFAULT_EXTERNAL_SYSTEM_PROMPT,
    EXTERNAL_MODEL_SPECS,
    call_external_model,
)
from app.agents.new_chat.tools.reflect_on_progress import create_reflect_on_progress_tool
from app.agents.new_chat.tools.write_todos import create_write_todos_tool
from app.db import AgentComboCache
from app.services.cache_control import is_cache_disabled
from app.services.reranker_service import RerankerService


_AGENT_CACHE_TTL = timedelta(minutes=20)
_AGENT_COMBO_CACHE: dict[str, tuple[datetime, list[str]]] = {}
_AGENT_STOPWORDS = {
    "hur",
    "vad",
    "var",
    "när",
    "nar",
    "är",
    "ar",
    "och",
    "eller",
    "för",
    "for",
    "till",
    "fran",
    "från",
    "en",
    "ett",
    "i",
    "på",
    "pa",
    "av",
    "med",
    "som",
    "om",
    "den",
    "det",
    "de",
}
_EXTERNAL_MODEL_TOOL_NAMES = {spec.tool_name for spec in EXTERNAL_MODEL_SPECS}
_AGENT_EMBED_CACHE: dict[str, list[float]] = {}
AGENT_RERANK_CANDIDATES = 6
AGENT_EMBEDDING_WEIGHT = 4.0


@dataclass(frozen=True)
class AgentToolProfile:
    tool_id: str
    category: str
    description: str
    keywords: tuple[str, ...]


def _build_agent_tool_profiles() -> dict[str, list[AgentToolProfile]]:
    profiles: dict[str, list[AgentToolProfile]] = {
        "trafik": [],
        "statistics": [],
        "riksdagen": [],
        "bolag": [],
    }
    for definition in TRAFIKVERKET_TOOL_DEFINITIONS:
        profiles["trafik"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "trafik")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    for definition in SCB_TOOL_DEFINITIONS:
        profiles["statistics"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "base_path", "statistics")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    for definition in RIKSDAGEN_TOOL_DEFINITIONS:
        profiles["riksdagen"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "riksdagen")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    for definition in BOLAGSVERKET_TOOL_DEFINITIONS:
        profiles["bolag"].append(
            AgentToolProfile(
                tool_id=str(getattr(definition, "tool_id", "")),
                category=str(getattr(definition, "category", "bolag")),
                description=str(getattr(definition, "description", "")),
                keywords=tuple(str(item) for item in list(getattr(definition, "keywords", []))),
            )
        )
    return profiles


_AGENT_TOOL_PROFILES = _build_agent_tool_profiles()
_AGENT_TOOL_PROFILE_BY_ID: dict[str, AgentToolProfile] = {
    profile.tool_id: profile
    for profiles in _AGENT_TOOL_PROFILES.values()
    for profile in profiles
    if profile.tool_id
}

# Message pruning constants for progressive context management
MESSAGE_PRUNING_THRESHOLD = 20  # Start pruning when total messages exceed this
TOOL_MSG_THRESHOLD = 8  # Trigger aggressive pruning when tool messages exceed this
KEEP_TOOL_MSG_COUNT = 6  # Number of recent tool message exchanges to preserve
TOOL_CONTEXT_MAX_CHARS = 1200
TOOL_CONTEXT_MAX_ITEMS = 5
TOOL_CONTEXT_DROP_KEYS = {
    "raw",
    "data",
    "entries",
    "matching_entries",
    "results",
    "content",
    "chunks",
    "documents",
    "rows",
    "timeSeries",
    "origin_lookup",
    "destination_lookup",
    "timetable",
}

_TRAFFIC_INTENT_RE = re.compile(
    r"\b("
    r"trafikverket|trafikinfo|trafik|"
    r"olycka|storing|storning|störning|"
    r"koer|köer|ko|kö|"
    r"vagarbete|vägarbete|avstangning|avstängning|omledning|framkomlighet|"
    r"tag|tåg|jarnvag|järnväg|"
    r"kamera|kameror|"
    r"vaglag|väglag|hastighet|"
    r"e\d+|rv\s?\d+|riksvag|riksväg|vag\s?\d+|väg\s?\d+"
    r")\b",
    re.IGNORECASE,
)
_MAP_INTENT_RE = re.compile(
    r"\b(karta|kartbild|kartor|map|marker|markor|pin|"
    r"rutt|route|vagbeskrivning|vägbeskrivning)\b",
    re.IGNORECASE,
)


def _has_trafik_intent(text: str) -> bool:
    return bool(text and _TRAFFIC_INTENT_RE.search(text))


def _has_map_intent(text: str) -> bool:
    return bool(text and _MAP_INTENT_RE.search(text))


def _tokenize_focus_terms(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z0-9åäöÅÄÖ]{3,}", str(text or "").lower())
    return {token for token in tokens if token not in _AGENT_STOPWORDS}


def _score_tool_profile(profile: AgentToolProfile, query_norm: str, tokens: set[str]) -> int:
    score = 0
    if profile.tool_id and profile.tool_id.lower() in query_norm:
        score += 6
    category_norm = _normalize_text(profile.category)
    if category_norm and category_norm in query_norm:
        score += 4
    description_norm = _normalize_text(profile.description)
    for keyword in profile.keywords:
        keyword_norm = _normalize_text(keyword)
        if keyword_norm and keyword_norm in query_norm:
            score += 3
    for token in tokens:
        if token and description_norm and token in description_norm:
            score += 1
    return score


def _select_focused_tool_profiles(
    agent_name: str,
    task: str,
    *,
    limit: int = 4,
) -> list[AgentToolProfile]:
    profiles = list(_AGENT_TOOL_PROFILES.get(str(agent_name or "").strip().lower(), []))
    if not profiles:
        return []
    query_norm = _normalize_text(task)
    tokens = _tokenize_focus_terms(task)
    scored = [
        (profile, _score_tool_profile(profile, query_norm, tokens))
        for profile in profiles
    ]
    scored.sort(
        key=lambda item: (
            item[1],
            len(item[0].keywords),
            len(item[0].description),
        ),
        reverse=True,
    )
    selected = [profile for profile, score in scored if score > 0][: max(1, int(limit))]
    if selected:
        return selected
    return profiles[: max(1, int(limit))]


def _focused_tool_ids_for_agent(agent_name: str, task: str, *, limit: int = 5) -> list[str]:
    focused = _select_focused_tool_profiles(agent_name, task, limit=limit)
    return [profile.tool_id for profile in focused if profile.tool_id]


def _build_scoped_prompt_for_agent(agent_name: str, task: str) -> str | None:
    focused = _select_focused_tool_profiles(agent_name, task, limit=3)
    if not focused:
        return None
    lines = [
        "[SCOPED TOOL PROMPT]",
        "Fokusera pa dessa mest relevanta verktyg/kategorier for uppgiften:",
    ]
    for profile in focused:
        keywords = ", ".join(profile.keywords[:4]) if profile.keywords else ""
        snippet = profile.description.strip()
        if len(snippet) > 140:
            snippet = snippet[:137].rstrip() + "..."
        lines.append(
            f"- {profile.tool_id} ({profile.category})"
            + (f": {snippet}" if snippet else "")
            + (f" [nyckelord: {keywords}]" if keywords else "")
        )
    lines.append(
        "Anvand i forsta hand ett av ovanstaende verktyg och hall argumenten strikt till valt verktygs schema."
    )
    return "\n".join(lines)


def _default_prompt_for_tool_id(tool_id: str) -> str | None:
    profile = _AGENT_TOOL_PROFILE_BY_ID.get(str(tool_id or "").strip())
    if not profile:
        return None
    keywords = ", ".join(profile.keywords[:8]) if profile.keywords else "-"
    description = profile.description.strip() or "-"
    return "\n".join(
        [
            f"[TOOL-SPECIFIC PROMPT: {profile.tool_id}]",
            f"Kategori: {profile.category}",
            f"Beskrivning: {description}",
            f"Nyckelord: {keywords}",
            "Anvand endast detta verktyg om uppgiften matchar dess doman.",
            "Matcha argument strikt mot verktygets schema och undvik overflodiga falt.",
            "Vid saknade kravfalt: stall en kort, exakt forfragan om komplettering.",
        ]
    )


def _tool_prompt_for_id(tool_id: str, tool_prompt_overrides: dict[str, str]) -> str | None:
    normalized_tool_id = str(tool_id or "").strip()
    if not normalized_tool_id:
        return None
    override_key = f"tool.{normalized_tool_id}.system"
    override = str(tool_prompt_overrides.get(override_key) or "").strip()
    if override:
        return override
    return _default_prompt_for_tool_id(normalized_tool_id)


def _build_tool_prompt_block(
    selected_tool_ids: list[str],
    tool_prompt_overrides: dict[str, str],
    *,
    max_tools: int = 2,
) -> str | None:
    blocks: list[str] = []
    seen: set[str] = set()
    for tool_id in selected_tool_ids:
        normalized_tool_id = str(tool_id or "").strip()
        if not normalized_tool_id or normalized_tool_id in seen:
            continue
        seen.add(normalized_tool_id)
        prompt_text = _tool_prompt_for_id(normalized_tool_id, tool_prompt_overrides)
        if prompt_text:
            blocks.append(prompt_text)
        if len(blocks) >= max(1, int(max_tools)):
            break
    if not blocks:
        return None
    return "\n\n".join(blocks)


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    keywords: list[str]
    namespace: tuple[str, ...]
    prompt_key: str


def _score_agent(definition: AgentDefinition, query_norm: str, tokens: set[str]) -> int:
    score = 0
    name_norm = _normalize_text(definition.name)
    desc_norm = _normalize_text(definition.description)
    if name_norm and name_norm in query_norm:
        score += 4
    for keyword in definition.keywords:
        if _normalize_text(keyword) in query_norm:
            score += 3
    for token in tokens:
        if token and token in desc_norm:
            score += 1
    return score


def _normalize_vector(vector: Any) -> list[float] | None:
    if vector is None:
        return None
    if isinstance(vector, list):
        return vector
    try:
        return [float(value) for value in vector]
    except Exception:
        return None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for a, b in zip(left, right):
        dot += a * b
        norm_left += a * a
        norm_right += b * b
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / ((norm_left**0.5) * (norm_right**0.5))


def _build_agent_rerank_text(definition: AgentDefinition) -> str:
    parts: list[str] = []
    if definition.name:
        parts.append(definition.name)
    if definition.description:
        parts.append(definition.description)
    if definition.keywords:
        parts.append("Keywords: " + ", ".join(definition.keywords))
    return "\n".join(part for part in parts if part)


def _get_agent_embedding(definition: AgentDefinition) -> list[float] | None:
    if not is_cache_disabled():
        cached = _AGENT_EMBED_CACHE.get(definition.name)
        if cached is not None:
            return cached
    text = _build_agent_rerank_text(definition)
    if not text:
        return None
    try:
        from app.config import config

        embedding = config.embedding_model_instance.embed(text)
    except Exception:
        return None
    normalized = _normalize_vector(embedding)
    if normalized is None:
        return None
    if not is_cache_disabled():
        _AGENT_EMBED_CACHE[definition.name] = normalized
    return normalized


def _rerank_agents(
    query: str,
    *,
    candidates: list[AgentDefinition],
    scores_by_name: dict[str, float],
) -> list[AgentDefinition]:
    if len(candidates) <= 1:
        return candidates
    reranker = RerankerService.get_reranker_instance()
    if not reranker:
        return candidates
    documents: list[dict[str, Any]] = []
    for agent in candidates:
        content = _build_agent_rerank_text(agent) or agent.name
        documents.append(
            {
                "document_id": agent.name,
                "content": content,
                "score": float(scores_by_name.get(agent.name, 0.0)),
                "document": {
                    "id": agent.name,
                    "title": agent.name,
                    "document_type": "AGENT",
                },
            }
        )
    reranked = reranker.rerank_documents(query, documents)
    if not reranked:
        return candidates
    reranked_names = [
        str(doc.get("document_id"))
        for doc in reranked
        if doc.get("document_id")
    ]
    by_name = {agent.name: agent for agent in candidates}
    ordered: list[AgentDefinition] = []
    seen: set[str] = set()
    for name in reranked_names:
        if name in by_name and name not in seen:
            ordered.append(by_name[name])
            seen.add(name)
    for agent in candidates:
        if agent.name not in seen:
            ordered.append(agent)
            seen.add(agent.name)
    return ordered


def _smart_retrieve_agents(
    query: str,
    *,
    agent_definitions: list[AgentDefinition],
    recent_agents: list[str] | None = None,
    limit: int = 3,
) -> list[AgentDefinition]:
    query_norm = _normalize_text(query)
    tokens = set(_tokenize(query_norm))
    query_embedding: list[float] | None = None
    if query:
        try:
            from app.config import config

            query_embedding = _normalize_vector(
                config.embedding_model_instance.embed(query)
            )
        except Exception:
            query_embedding = None
    recent_agents = [agent for agent in (recent_agents or []) if agent]
    scored: list[tuple[AgentDefinition, float]] = []
    scores_by_name: dict[str, float] = {}
    for definition in agent_definitions:
        base_score = float(_score_agent(definition, query_norm, tokens))
        semantic_score = 0.0
        if query_embedding:
            agent_embedding = _get_agent_embedding(definition)
            if agent_embedding:
                semantic_score = _cosine_similarity(query_embedding, agent_embedding)
        total_score = base_score + (semantic_score * AGENT_EMBEDDING_WEIGHT)
        scored.append((definition, total_score))
        scores_by_name[definition.name] = total_score
    if recent_agents:
        for idx, (definition, score) in enumerate(scored):
            if definition.name in recent_agents:
                scored[idx] = (definition, score + 4)
                scores_by_name[definition.name] = score + 4
    scored.sort(key=lambda item: item[1], reverse=True)
    candidates = [definition for definition, _ in scored[:AGENT_RERANK_CANDIDATES]]
    reranked = _rerank_agents(
        query, candidates=candidates, scores_by_name=scores_by_name
    )
    return reranked[:limit]


def _build_cache_key(
    query: str,
    route_hint: str | None,
    recent_agents: list[str] | None,
) -> tuple[str, str]:
    tokens = [
        token
        for token in _tokenize(query)
        if token and token not in _AGENT_STOPWORDS
    ]
    token_slice = " ".join(tokens[:6])
    recent_slice = ",".join((recent_agents or [])[-2:])
    pattern = f"{route_hint or 'none'}|{recent_slice}|{token_slice}"
    key = hashlib.sha256(pattern.encode("utf-8")).hexdigest()
    return key, pattern


def _get_cached_combo(cache_key: str) -> list[str] | None:
    if is_cache_disabled():
        return None
    entry = _AGENT_COMBO_CACHE.get(cache_key)
    if not entry:
        return None
    expires_at, agents = entry
    if expires_at < datetime.now(UTC):
        _AGENT_COMBO_CACHE.pop(cache_key, None)
        return None
    return agents


def _set_cached_combo(cache_key: str, agents: list[str]) -> None:
    if is_cache_disabled():
        return
    _AGENT_COMBO_CACHE[cache_key] = (datetime.now(UTC) + _AGENT_CACHE_TTL, agents)


def clear_agent_combo_cache() -> None:
    _AGENT_COMBO_CACHE.clear()
    _AGENT_EMBED_CACHE.clear()


async def _fetch_cached_combo_db(
    session: AsyncSession | None, cache_key: str
) -> list[str] | None:
    if is_cache_disabled():
        return None
    if session is None:
        return None
    result = await session.execute(
        select(AgentComboCache).where(AgentComboCache.cache_key == cache_key)
    )
    row = result.scalars().first()
    if not row:
        return None
    agents = row.agents if isinstance(row.agents, list) else []
    row.hit_count = int(row.hit_count or 0) + 1
    row.last_used_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return [str(agent) for agent in agents if agent]


async def _store_cached_combo_db(
    session: AsyncSession | None,
    *,
    cache_key: str,
    route_hint: str | None,
    pattern: str,
    recent_agents: list[str],
    agents: list[str],
) -> None:
    if is_cache_disabled():
        return
    if session is None:
        return
    result = await session.execute(
        select(AgentComboCache).where(AgentComboCache.cache_key == cache_key)
    )
    row = result.scalars().first()
    if row:
        row.agents = agents
        row.recent_agents = recent_agents
        row.route_hint = route_hint
        row.pattern = pattern
        row.updated_at = datetime.now(UTC)
        row.last_used_at = datetime.now(UTC)
    else:
        row = AgentComboCache(
            cache_key=cache_key,
            route_hint=route_hint,
            pattern=pattern,
            recent_agents=recent_agents,
            agents=agents,
            hit_count=0,
            last_used_at=datetime.now(UTC),
        )
        session.add(row)
    await session.commit()


def _replace(left: Any, right: Any) -> Any:
    return right if right is not None else left


def _append_recent(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged = list(left or [])
    merged.extend(right or [])
    return merged[-3:]


def _append_compare_outputs(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in left or []:
        tool_call_id = str(item.get("tool_call_id") or "")
        if tool_call_id:
            merged[tool_call_id] = item
    for item in right or []:
        tool_call_id = str(item.get("tool_call_id") or "")
        if tool_call_id:
            merged[tool_call_id] = item
    return list(merged.values())


def _format_compare_outputs_for_prompt(compare_outputs: list[dict[str, Any]] | None) -> str:
    if not compare_outputs:
        return ""
    blocks: list[str] = []
    for output in compare_outputs:
        model_name = (
            output.get("model_display_name")
            or output.get("model")
            or output.get("tool_name")
            or "Model"
        )
        response = output.get("response") or ""
        if not isinstance(response, str):
            response = str(response)
        response = response.strip()
        if not response:
            continue
        citation_ids = output.get("citation_chunk_ids") or []
        if isinstance(citation_ids, str):
            citation_ids = [citation_ids]
        citation_hint = ", ".join([str(cid) for cid in citation_ids if cid])
        cite_note = (
            f" (citation_ids: {citation_hint})" if citation_hint else ""
        )
        blocks.append(f"MODEL_ANSWER ({model_name}){cite_note}:\n{response}")
    if not blocks:
        return ""
    return "<compare_outputs>\n" + "\n\n".join(blocks) + "\n</compare_outputs>"


class SupervisorState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    active_plan: Annotated[list[dict[str, Any]], _replace]
    plan_complete: Annotated[bool, _replace]
    recent_agent_calls: Annotated[list[dict[str, Any]], _append_recent]
    route_hint: Annotated[str | None, _replace]
    compare_outputs: Annotated[list[dict[str, Any]], _append_compare_outputs]
    final_agent_response: Annotated[str | None, _replace]
    final_agent_name: Annotated[str | None, _replace]


def _format_plan_context(state: dict[str, Any]) -> str | None:
    plan = state.get("active_plan") or []
    if not plan:
        return None
    status = "complete" if state.get("plan_complete") else "active"
    lines = []
    for item in plan:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        step_status = str(item.get("status") or "pending").lower()
        lines.append(f"- [{step_status}] {content}")
    if not lines:
        return None
    return f"<active_plan status=\"{status}\">\n" + "\n".join(lines) + "\n</active_plan>"


def _format_recent_calls(state: dict[str, Any]) -> str | None:
    recent_calls = state.get("recent_agent_calls") or []
    if not recent_calls:
        return None
    lines = []
    for call in recent_calls[-3:]:
        agent = call.get("agent")
        task = call.get("task")
        response = call.get("response") or ""
        if response and len(response) > 180:
            response = response[:177] + "..."
        lines.append(f"- {agent}: {task} → {response}")
    if not lines:
        return None
    return "<recent_agent_calls>\n" + "\n".join(lines) + "\n</recent_agent_calls>"


def _format_route_hint(state: dict[str, Any]) -> str | None:
    hint = state.get("route_hint")
    if not hint:
        return None
    return f"<route_hint>{hint}</route_hint>"




def _safe_json(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return {}


_CRITIC_SNIPPET_RE = re.compile(
    r"\{\s*\"status\"\s*:\s*\"(?:ok|needs_more)\"[^}]*\}", re.DOTALL
)


def _strip_critic_json(text: str) -> str:
    if not text:
        return text
    cleaned = _CRITIC_SNIPPET_RE.sub("", text)
    return cleaned.rstrip()


def _truncate_for_prompt(text: str, max_chars: int = TOOL_CONTEXT_MAX_CHARS) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _summarize_tool_payload(tool_name: str, payload: dict[str, Any]) -> str:
    name = (tool_name or "tool").strip() or "tool"
    status = str(payload.get("status") or "completed").lower()
    parts: list[str] = [f"{name}: {status}"]

    if status == "error" or "error" in payload:
        error_text = _truncate_for_prompt(str(payload.get("error") or "Unknown error"), 300)
        return _truncate_for_prompt(f"{name}: error - {error_text}")

    if name == "write_todos":
        todos = payload.get("todos") or []
        if isinstance(todos, list):
            completed = sum(
                1
                for item in todos
                if isinstance(item, dict) and str(item.get("status") or "").lower() == "completed"
            )
            in_progress = sum(
                1
                for item in todos
                if isinstance(item, dict) and str(item.get("status") or "").lower() == "in_progress"
            )
            parts.append(f"todos={len(todos)}")
            parts.append(f"completed={completed}")
            parts.append(f"in_progress={in_progress}")
            task_names = [
                str(item.get("content") or "").strip()
                for item in todos
                if isinstance(item, dict) and str(item.get("content") or "").strip()
            ][:TOOL_CONTEXT_MAX_ITEMS]
            if task_names:
                parts.append("tasks=" + " | ".join(task_names))
            return _truncate_for_prompt("; ".join(parts))

    if name == "trafiklab_route":
        origin = payload.get("origin") or {}
        destination = payload.get("destination") or {}
        origin_name = ""
        destination_name = ""
        if isinstance(origin, dict):
            origin_name = str(
                ((origin.get("stop_group") or {}) if isinstance(origin.get("stop_group"), dict) else {}).get("name")
                or origin.get("name")
                or ""
            ).strip()
        if isinstance(destination, dict):
            destination_name = str(
                (
                    ((destination.get("stop_group") or {}) if isinstance(destination.get("stop_group"), dict) else {}).get("name")
                    or destination.get("name")
                    or ""
                )
            ).strip()
        route_label = " -> ".join([label for label in (origin_name, destination_name) if label]).strip()
        if route_label:
            parts.append(f"route={route_label}")
        matches = payload.get("matching_entries")
        entries = payload.get("entries")
        if isinstance(matches, list):
            parts.append(f"matching_entries={len(matches)}")
        if isinstance(entries, list):
            parts.append(f"entries={len(entries)}")
        return _truncate_for_prompt("; ".join(parts))

    if name == "smhi_weather":
        location = payload.get("location") or {}
        location_name = ""
        if isinstance(location, dict):
            location_name = str(location.get("name") or location.get("display_name") or "").strip()
        if location_name:
            parts.append(f"location={location_name}")
        current = payload.get("current") or {}
        summary = current.get("summary") if isinstance(current, dict) else {}
        if isinstance(summary, dict):
            temperature = summary.get("temperature_c")
            if temperature is not None:
                parts.append(f"temperature_c={temperature}")
            wind = summary.get("wind_speed_mps")
            if wind is not None:
                parts.append(f"wind_mps={wind}")
        return _truncate_for_prompt("; ".join(parts))

    for key, value in payload.items():
        if key in {"status", "error"}:
            continue
        if key in TOOL_CONTEXT_DROP_KEYS:
            if isinstance(value, list):
                parts.append(f"{key}_count={len(value)}")
            elif isinstance(value, dict):
                parts.append(f"{key}_keys={len(value)}")
            elif value is not None:
                parts.append(f"{key}=present")
            continue
        if isinstance(value, (str, int, float, bool)):
            parts.append(f"{key}={_truncate_for_prompt(str(value), 180)}")
            continue
        if isinstance(value, list):
            parts.append(f"{key}_count={len(value)}")
            continue
        if isinstance(value, dict):
            parts.append(f"{key}_keys={len(value)}")
            continue
        if value is not None:
            parts.append(f"{key}=present")

    return _truncate_for_prompt("; ".join(parts))


def _sanitize_messages(messages: list[Any]) -> list[Any]:
    sanitized: list[Any] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            payload = _safe_json(message.content)
            if payload:
                response = payload.get("response")
                if isinstance(response, str):
                    agent = payload.get("agent") or message.name or "agent"
                    response = _strip_critic_json(response)
                    content = (
                        _truncate_for_prompt(f"{agent}: {response}")
                        if response
                        else f"{agent}: completed"
                    )
                    sanitized.append(
                        ToolMessage(
                            content=content,
                            name=message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                if payload.get("status") and payload.get("reason"):
                    tool_name = message.name or "tool"
                    sanitized.append(
                        ToolMessage(
                            content=_truncate_for_prompt(f"{tool_name}: completed"),
                            name=message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                summarized = _summarize_tool_payload(message.name or "tool", payload)
                sanitized.append(
                    ToolMessage(
                        content=summarized,
                        name=message.name,
                        tool_call_id=getattr(message, "tool_call_id", None),
                    )
                )
                continue
            if isinstance(message.content, str) and "{\"status\"" in message.content:
                trimmed = message.content.split("{\"status\"", 1)[0].rstrip()
                if trimmed:
                    sanitized.append(
                        ToolMessage(
                            content=_truncate_for_prompt(trimmed),
                            name=message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                else:
                    sanitized.append(
                        ToolMessage(
                            content=f"{message.name or 'tool'}: completed",
                            name=message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                continue
            if isinstance(message.content, str):
                trimmed = _strip_critic_json(message.content)
                if not trimmed:
                    trimmed = f"{message.name or 'tool'}: completed"
                sanitized.append(
                    ToolMessage(
                        content=_truncate_for_prompt(trimmed),
                        name=message.name,
                        tool_call_id=getattr(message, "tool_call_id", None),
                    )
                )
                continue
        sanitized.append(message)
    return sanitized


async def create_supervisor_agent(
    *,
    llm,
    dependencies: dict[str, Any],
    checkpointer: Checkpointer | None,
    knowledge_prompt: str,
    action_prompt: str,
    statistics_prompt: str,
    synthesis_prompt: str | None = None,
    compare_mode: bool = False,
    external_model_prompt: str | None = None,
    bolag_prompt: str | None = None,
    trafik_prompt: str | None = None,
    media_prompt: str | None = None,
    browser_prompt: str | None = None,
    code_prompt: str | None = None,
    kartor_prompt: str | None = None,
    riksdagen_prompt: str | None = None,
    tool_prompt_overrides: dict[str, str] | None = None,
):
    tool_prompt_overrides = dict(tool_prompt_overrides or {})
    worker_configs: dict[str, WorkerConfig] = {
        "knowledge": WorkerConfig(
            name="knowledge-worker",
            primary_namespaces=[("tools", "knowledge")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "statistics"),
                ("tools", "general"),
            ],
        ),
        "action": WorkerConfig(
            name="action-worker",
            primary_namespaces=[("tools", "action")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "statistics"),
                ("tools", "kartor"),
                ("tools", "general"),
            ],
        ),
        "kartor": WorkerConfig(
            name="kartor-worker",
            primary_namespaces=[("tools", "kartor")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "media": WorkerConfig(
            name="media-worker",
            primary_namespaces=[("tools", "action", "media")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "statistics"),
                ("tools", "kartor"),
                ("tools", "general"),
            ],
        ),
        "statistics": WorkerConfig(
            name="statistics-worker",
            primary_namespaces=[("tools", "statistics")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "browser": WorkerConfig(
            name="browser-worker",
            primary_namespaces=[("tools", "knowledge", "web")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "action"),
                ("tools", "statistics"),
                ("tools", "general"),
            ],
        ),
        "code": WorkerConfig(
            name="code-worker",
            primary_namespaces=[("tools", "general")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "action"),
                ("tools", "statistics"),
            ],
        ),
        "bolag": WorkerConfig(
            name="bolag-worker",
            primary_namespaces=[("tools", "bolag")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "statistics"),
                ("tools", "action"),
                ("tools", "general"),
            ],
        ),
        "trafik": WorkerConfig(
            name="trafik-worker",
            primary_namespaces=[("tools", "trafik")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
                ("tools", "general"),
            ],
        ),
        "riksdagen": WorkerConfig(
            name="riksdagen-worker",
            primary_namespaces=[("tools", "politik")],
            fallback_namespaces=[
                ("tools", "knowledge"),
                ("tools", "action"),
                ("tools", "general"),
            ],
        ),
        "synthesis": WorkerConfig(
            name="synthesis-worker",
            primary_namespaces=[("tools", "knowledge")],
            fallback_namespaces=[
                ("tools", "statistics"),
                ("tools", "action"),
                ("tools", "general"),
            ],
        ),
    }

    worker_prompts: dict[str, str] = {
        "knowledge": knowledge_prompt,
        "action": action_prompt,
        "kartor": action_prompt,
        "media": media_prompt or action_prompt,
        "statistics": statistics_prompt,
        "browser": browser_prompt or knowledge_prompt,
        "code": code_prompt or knowledge_prompt,
        "bolag": bolag_prompt or knowledge_prompt,
        "trafik": trafik_prompt or action_prompt,
        "kartor": kartor_prompt or action_prompt,
        "riksdagen": riksdagen_prompt or knowledge_prompt,
        "synthesis": synthesis_prompt or statistics_prompt or knowledge_prompt,
    }

    # Create lazy worker pool for on-demand initialization
    worker_pool = LazyWorkerPool(
        configs=worker_configs,
        llm=llm,
        dependencies=dependencies,
        checkpointer=checkpointer,
    )

    agent_definitions = [
        AgentDefinition(
            name="action",
            description="Realtime actions som vader, resor och verktygskorningar",
            keywords=[
                "vader",
                "vadret",
                "väder",
                "vädret",
                "smhi",
                "resa",
                "tåg",
                "tag",
                "avgår",
                "tidtabell",
                "trafik",
                "rutt",
                "karta",
                "kartbild",
                "geoapify",
                "adress",
            ],
            namespace=("agents", "action"),
            prompt_key="action",
        ),
        AgentDefinition(
            name="kartor",
            description="Skapa statiska kartbilder och markörer",
            keywords=[
                "karta",
                "kartor",
                "kartbild",
                "map",
                "geoapify",
                "adress",
                "plats",
                "koordinat",
                "vägarbete",
                "vag",
                "väg",
                "rutt",
            ],
            namespace=("agents", "kartor"),
            prompt_key="kartor",
        ),
        AgentDefinition(
            name="statistics",
            description="SCB och officiell svensk statistik",
            keywords=["statistik", "scb", "kolada", "befolkning", "kpi"],
            namespace=("agents", "statistics"),
            prompt_key="statistics",
        ),
        AgentDefinition(
            name="media",
            description="Podcast, bild och media-generering",
            keywords=["podcast", "podd", "media", "bild", "ljud"],
            namespace=("agents", "media"),
            prompt_key="media",
        ),
        AgentDefinition(
            name="knowledge",
            description="SurfSense, Tavily och generell kunskap",
            keywords=["kunskap", "surfsense", "tavily", "docs", "note"],
            namespace=("agents", "knowledge"),
            prompt_key="knowledge",
        ),
        AgentDefinition(
            name="browser",
            description="Webbsokning och scraping",
            keywords=["webb", "browser", "sok", "nyheter", "url"],
            namespace=("agents", "browser"),
            prompt_key="browser",
        ),
        AgentDefinition(
            name="code",
            description="Kalkyler och kodrelaterade uppgifter",
            keywords=["kod", "berakna", "script", "python"],
            namespace=("agents", "code"),
            prompt_key="code",
        ),
        AgentDefinition(
            name="bolag",
            description="Bolagsverket och företagsdata (orgnr, ägare, ekonomi)",
            keywords=[
                "bolag",
                "bolagsverket",
                "foretag",
                "företag",
                "orgnr",
                "organisationsnummer",
                "styrelse",
                "firmatecknare",
                "arsredovisning",
                "årsredovisning",
                "f-skatt",
                "moms",
                "konkurs",
            ],
            namespace=("agents", "bolag"),
            prompt_key="bolag",
        ),
        AgentDefinition(
            name="trafik",
            description="Trafikverket realtidsdata (väg, tåg, kameror, väder)",
            keywords=[
                "trafikverket",
                "trafik",
                "väg",
                "vag",
                "tåg",
                "tag",
                "störning",
                "olycka",
                "kö",
                "ko",
                "kamera",
                "väder",
                "vader",
            ],
            namespace=("agents", "trafik"),
            prompt_key="trafik",
        ),
        AgentDefinition(
            name="riksdagen",
            description="Riksdagens öppna data: propositioner, motioner, voteringar, ledamöter",
            keywords=[
                "riksdag",
                "riksdagen",
                "proposition",
                "prop",
                "motion",
                "mot",
                "votering",
                "omröstning",
                "ledamot",
                "ledamöter",
                "betänkande",
                "bet",
                "interpellation",
                "fråga",
                "anförande",
                "debatt",
                "kammare",
                "sou",
                "ds",
                "utskott",
                "parti",
            ],
            namespace=("agents", "riksdagen"),
            prompt_key="riksdagen",
        ),
        AgentDefinition(
            name="synthesis",
            description="Syntes och jämförelser av flera källor och modeller",
            keywords=["synthesis", "syntes", "jämför", "compare", "sammanfatta"],
            namespace=("agents", "synthesis"),
            prompt_key="synthesis",
        ),
    ]

    agent_by_name = {definition.name: definition for definition in agent_definitions}
    db_session = dependencies.get("db_session")
    connector_service = dependencies.get("connector_service")
    search_space_id = dependencies.get("search_space_id")
    user_id = dependencies.get("user_id")
    thread_id = dependencies.get("thread_id")
    trafik_tool_ids = [definition.tool_id for definition in TRAFIKVERKET_TOOL_DEFINITIONS]
    compare_external_prompt = external_model_prompt or DEFAULT_EXTERNAL_SYSTEM_PROMPT

    def _build_compare_external_tool(spec):
        async def _compare_tool(query: str) -> dict[str, Any]:
            result = await call_external_model(
                spec=spec,
                query=query,
                system_prompt=compare_external_prompt,
            )
            if connector_service:
                try:
                    document = await connector_service.ingest_tool_output(
                        tool_name=spec.tool_name,
                        tool_output=result,
                        metadata={
                            "provider": result.get("provider"),
                            "model": result.get("model"),
                            "model_display_name": result.get("model_display_name"),
                            "source": result.get("source"),
                        },
                        user_id=user_id,
                        origin_search_space_id=search_space_id,
                        thread_id=thread_id,
                    )
                    if document and getattr(document, "chunks", None):
                        result["document_id"] = document.id
                        result["citation_chunk_ids"] = [
                            str(chunk.id) for chunk in document.chunks
                        ]
                except Exception as exc:
                    print(
                        f"[compare] Failed to ingest {spec.tool_name}: {exc!s}"
                    )
            return result

        return tool(
            spec.tool_name,
            description=f"Call external model {spec.display} for compare mode.",
        )(_compare_tool)

    @tool
    async def retrieve_agents(
        query: str,
        limit: int = 3,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Retrieve relevant agents for the task."""
        recent_agents = []
        context_query = query
        route_hint = None
        cache_key = None
        cache_pattern = None
        if state:
            recent_calls = state.get("recent_agent_calls") or []
            recent_agents = [
                str(call.get("agent"))
                for call in recent_calls
                if call.get("agent")
            ]
            route_hint = state.get("route_hint")
            context_parts = []
            for call in recent_calls[-3:]:
                response = str(call.get("response") or "")
                if len(response) > 120:
                    response = response[:117] + "..."
                context_parts.append(
                    f"{call.get('agent')}: {call.get('task')} {response}"
                )
            if context_parts:
                context_query = f"{query} {' '.join(context_parts)}"

        has_trafik_intent = _has_trafik_intent(context_query)
        has_map_intent = _has_map_intent(context_query)

        cache_key, cache_pattern = _build_cache_key(
            query, route_hint, recent_agents
        )
        cached_agents = _get_cached_combo(cache_key)
        if cached_agents is None:
            cached_agents = await _fetch_cached_combo_db(db_session, cache_key)
            if cached_agents:
                _set_cached_combo(cache_key, cached_agents)
        if cached_agents and has_trafik_intent and "trafik" not in cached_agents:
            cached_agents = None

        if cached_agents:
            selected = [
                agent_by_name[name]
                for name in cached_agents
                if name in agent_by_name
            ]
        else:
            selected = _smart_retrieve_agents(
                context_query,
                agent_definitions=agent_definitions,
                recent_agents=recent_agents,
                limit=limit,
            )
            if route_hint:
                preferred = {
                    "action": ["action", "media"],
                    "knowledge": ["knowledge", "browser"],
                    "statistics": ["statistics"],
                    "compare": ["synthesis", "knowledge", "statistics"],
                    "trafik": ["trafik", "action"],
                }.get(str(route_hint), [])
                if str(route_hint) == "action":
                    if has_map_intent and "kartor" not in preferred:
                        preferred.insert(0, "kartor")
                    if has_trafik_intent and "trafik" not in preferred:
                        preferred.insert(0, "trafik")
                if preferred:
                    preferred_defs = [
                        agent
                        for agent in agent_definitions
                        if agent.name in preferred
                    ]
                    for agent in reversed(preferred_defs):
                        if agent not in selected:
                            selected.insert(0, agent)
                    selected = selected[:limit]

            if has_trafik_intent:
                trafik_agent = agent_by_name.get("trafik")
                if trafik_agent and trafik_agent not in selected:
                    selected.insert(0, trafik_agent)
                    selected = selected[:limit]

            selected_names = [agent.name for agent in selected]
            if cache_key and cache_pattern:
                await _store_cached_combo_db(
                    db_session,
                    cache_key=cache_key,
                    route_hint=route_hint,
                    pattern=cache_pattern,
                    recent_agents=recent_agents,
                    agents=selected_names,
                )

        selected = selected[:limit]
        payload = [
            {"name": agent.name, "description": agent.description}
            for agent in selected
        ]
        return json.dumps({"agents": payload}, ensure_ascii=True)

    def _prepare_task_for_synthesis(task: str, state: dict[str, Any] | None) -> str:
        """Add compare_outputs context for synthesis agent if applicable."""
        if not state:
            return task
        compare_context = _format_compare_outputs_for_prompt(
            state.get("compare_outputs") or []
        )
        if compare_context and "<compare_outputs>" not in task:
            return f"{task}\n\n{compare_context}"
        return task

    @tool
    async def call_agent(
        agent_name: str,
        task: str,
        final: bool = False,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Call a specialized agent with a task."""
        name = (agent_name or "").strip().lower()
        worker = await worker_pool.get(name)
        if not worker:
            return json.dumps(
                {"error": f"Agent '{agent_name}' not available."}, ensure_ascii=True
            )
        if name == "synthesis" and state:
            task = _prepare_task_for_synthesis(task, state)
        selected_tool_ids: list[str] = _focused_tool_ids_for_agent(name, task, limit=6)
        if name == "trafik":
            selected_tool_ids = [
                tool_id for tool_id in selected_tool_ids if tool_id in trafik_tool_ids
            ]
            if not selected_tool_ids:
                selected_tool_ids = list(trafik_tool_ids)
        prompt = worker_prompts.get(name, "")
        scoped_prompt = _build_scoped_prompt_for_agent(name, task)
        if scoped_prompt:
            prompt = f"{prompt.rstrip()}\n\n{scoped_prompt}".strip() if prompt else scoped_prompt
        tool_prompt_block = _build_tool_prompt_block(
            selected_tool_ids,
            tool_prompt_overrides,
            max_tools=2,
        )
        if tool_prompt_block:
            prompt = (
                f"{prompt.rstrip()}\n\n{tool_prompt_block}".strip()
                if prompt
                else tool_prompt_block
            )
        messages = []
        if prompt:
            messages.append(SystemMessage(content=prompt))
        messages.append(HumanMessage(content=task))
        state = {"messages": messages, "selected_tool_ids": selected_tool_ids}
        config = {
            "configurable": {"thread_id": f"{dependencies['thread_id']}:{name}"},
            "recursion_limit": 60,
        }
        result = await worker.ainvoke(state, config=config)
        response_text = ""
        if isinstance(result, dict):
            messages_out = result.get("messages") or []
            if messages_out:
                response_text = str(getattr(messages_out[-1], "content", "") or "")
            if name == "trafik":
                used_trafik_tool = any(
                    isinstance(message, ToolMessage)
                    and getattr(message, "name", "").startswith("trafikverket_")
                    for message in messages_out
                )
                if not used_trafik_tool:
                    enforced_prompt = (
                        f"{prompt}\n\n"
                        "Du måste använda retrieve_tools och sedan minst ett "
                        "trafikverket_* verktyg innan du svarar."
                    )
                    enforced_messages = [SystemMessage(content=enforced_prompt), HumanMessage(content=task)]
                    retry_state = {
                        "messages": enforced_messages,
                        "selected_tool_ids": selected_tool_ids,
                    }
                    result = await worker.ainvoke(retry_state, config=config)
                    if isinstance(result, dict):
                        messages_out = result.get("messages") or []
                        if messages_out:
                            response_text = str(
                                getattr(messages_out[-1], "content", "") or ""
                            )
        if not response_text:
            response_text = str(result)

        critic_prompt = append_datetime_context(
            "Du ar en kritisk granskare. Bedom om svaret ar komplett och korrekt. "
            "Svara kort i JSON med {\"status\": \"ok\"|\"needs_more\", \"reason\": \"...\"}."
        )
        critic_input = f"Uppgift: {task}\nSvar: {response_text}"
        critic_msg = await llm.ainvoke(
            [SystemMessage(content=critic_prompt), HumanMessage(content=critic_input)]
        )
        critic_text = str(getattr(critic_msg, "content", "") or "").strip()
        critic_payload = _safe_json(critic_text)
        if not critic_payload:
            critic_payload = {"status": "ok", "reason": critic_text}

        response_text = _strip_critic_json(response_text)

        # Compress response for context efficiency when not final
        if not final:
            response_text = compress_response(response_text, agent_name=name)

        return json.dumps(
            {
                "agent": name,
                "task": task,
                "response": response_text,
                "critic": critic_payload,
                "final": bool(final),
            },
            ensure_ascii=True,
        )

    @tool
    async def call_agents_parallel(
        calls: list[dict],
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Call multiple agents in parallel. Each call dict has 'agent' and 'task' keys.
        Use when tasks are independent and don't depend on each other's results."""
        
        async def _run_one(call_spec: dict) -> dict:
            agent_name = (call_spec.get("agent") or "").strip().lower()
            task = call_spec.get("task") or ""
            worker = await worker_pool.get(agent_name)
            if not worker:
                return {"agent": agent_name, "error": f"Agent '{agent_name}' not available."}
            try:
                # Reuse same worker invocation logic as call_agent
                if agent_name == "synthesis" and state:
                    task = _prepare_task_for_synthesis(task, state)
                selected_tool_ids = _focused_tool_ids_for_agent(agent_name, task, limit=6)
                if agent_name == "trafik":
                    selected_tool_ids = [
                        tool_id for tool_id in selected_tool_ids if tool_id in trafik_tool_ids
                    ]
                    if not selected_tool_ids:
                        selected_tool_ids = list(trafik_tool_ids)
                prompt = worker_prompts.get(agent_name, "")
                scoped_prompt = _build_scoped_prompt_for_agent(agent_name, task)
                if scoped_prompt:
                    prompt = (
                        f"{prompt.rstrip()}\n\n{scoped_prompt}".strip()
                        if prompt
                        else scoped_prompt
                    )
                tool_prompt_block = _build_tool_prompt_block(
                    selected_tool_ids,
                    tool_prompt_overrides,
                    max_tools=2,
                )
                if tool_prompt_block:
                    prompt = (
                        f"{prompt.rstrip()}\n\n{tool_prompt_block}".strip()
                        if prompt
                        else tool_prompt_block
                    )
                messages = []
                if prompt:
                    messages.append(SystemMessage(content=prompt))
                messages.append(HumanMessage(content=task))
                worker_state = {"messages": messages, "selected_tool_ids": selected_tool_ids}
                config = {
                    "configurable": {"thread_id": f"{dependencies['thread_id']}:{agent_name}"},
                    "recursion_limit": 60,
                }
                result = await worker.ainvoke(worker_state, config=config)
                response_text = ""
                if isinstance(result, dict):
                    messages_out = result.get("messages") or []
                    if messages_out:
                        last_msg = messages_out[-1]
                        response_text = str(getattr(last_msg, "content", "") or "")
                return {"agent": agent_name, "task": task, "response": response_text}
            except Exception as exc:
                return {
                    "agent": agent_name,
                    "task": task,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
        
        results = await asyncio.gather(
            *[_run_one(c) for c in calls],
            return_exceptions=True,
        )
        
        processed = []
        for r in results:
            if isinstance(r, Exception):
                processed.append({"error": str(r)})
            else:
                processed.append(r)
        
        return json.dumps({"results": processed}, ensure_ascii=True)

    tool_registry = {
        "retrieve_agents": retrieve_agents,
        "call_agent": call_agent,
        "call_agents_parallel": call_agents_parallel,
        "write_todos": create_write_todos_tool(),
        "reflect_on_progress": create_reflect_on_progress_tool(),
    }
    if compare_mode:
        for spec in EXTERNAL_MODEL_SPECS:
            tool_registry[spec.tool_name] = _build_compare_external_tool(spec)

    llm_with_tools = llm.bind_tools(list(tool_registry.values()))
    tool_node = ToolNode(tool_registry.values())

    def call_model(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        final_response = state.get("final_agent_response")
        messages_state = state.get("messages") or []
        last_message = messages_state[-1] if messages_state else None
        if final_response and isinstance(last_message, ToolMessage):
            return {"messages": [AIMessage(content=final_response)]}
        messages = _sanitize_messages(list(state.get("messages") or []))
        plan_context = _format_plan_context(state)
        recent_context = _format_recent_calls(state)
        route_context = _format_route_hint(state)
        system_bits = [
            item for item in (plan_context, recent_context, route_context) if item
        ]
        if system_bits:
            messages = [SystemMessage(content="\n".join(system_bits))] + messages
        
        # Apply token budget
        model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None) or ""
        if model_name:
            budget = TokenBudget(model_name=str(model_name))
            messages = budget.fit_messages(messages)
        
        response = llm_with_tools.invoke(messages)
        updates: SupervisorState = {"messages": [response]}
        if final_response and isinstance(last_message, HumanMessage):
            updates["final_agent_response"] = None
            updates["final_agent_name"] = None
        return updates

    async def acall_model(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        final_response = state.get("final_agent_response")
        messages_state = state.get("messages") or []
        last_message = messages_state[-1] if messages_state else None
        if final_response and isinstance(last_message, ToolMessage):
            return {"messages": [AIMessage(content=final_response)]}
        messages = _sanitize_messages(list(state.get("messages") or []))
        plan_context = _format_plan_context(state)
        recent_context = _format_recent_calls(state)
        route_context = _format_route_hint(state)
        system_bits = [
            item for item in (plan_context, recent_context, route_context) if item
        ]
        if system_bits:
            messages = [SystemMessage(content="\n".join(system_bits))] + messages
        
        # Apply token budget
        model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None) or ""
        if model_name:
            budget = TokenBudget(model_name=str(model_name))
            messages = budget.fit_messages(messages)
        
        response = await llm_with_tools.ainvoke(messages)
        updates: SupervisorState = {"messages": [response]}
        if final_response and isinstance(last_message, HumanMessage):
            updates["final_agent_response"] = None
            updates["final_agent_name"] = None
        return updates

    async def post_tools(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        updates: dict[str, Any] = {}
        recent_updates: list[dict[str, Any]] = []
        compare_updates: list[dict[str, Any]] = []
        plan_update: list[dict[str, Any]] | None = None
        plan_complete: bool | None = None
        last_call_payload: dict[str, Any] | None = None

        for message in reversed(state.get("messages") or []):
            if not isinstance(message, ToolMessage):
                continue
            tool_name = message.name or ""
            payload = _safe_json(message.content)
            if tool_name == "write_todos":
                todos = payload.get("todos") or []
                if todos:
                    plan_update = todos
                    completed = [
                        str(todo.get("status") or "").lower()
                        for todo in todos
                        if isinstance(todo, dict)
                    ]
                    if completed:
                        plan_complete = all(
                            status in ("completed", "cancelled") for status in completed
                        )
                if "plan_complete" in payload:
                    plan_complete = bool(payload.get("plan_complete"))
            elif tool_name == "call_agent":
                last_call_payload = payload
                if payload:
                    recent_updates.append(
                        {
                            "agent": payload.get("agent"),
                            "task": payload.get("task"),
                            "response": payload.get("response"),
                        }
                    )
                    if payload.get("final") and payload.get("response"):
                        critic_payload = payload.get("critic") or {}
                        if not (
                            isinstance(critic_payload, dict)
                            and critic_payload.get("status") == "needs_more"
                        ):
                            updates["final_agent_response"] = payload.get("response")
                            updates["final_agent_name"] = payload.get("agent")
            elif tool_name in _EXTERNAL_MODEL_TOOL_NAMES:
                if payload and payload.get("status") == "success":
                    compare_updates.append(
                        {
                            "tool_call_id": getattr(message, "tool_call_id", None),
                            "tool_name": tool_name,
                            "model_display_name": payload.get("model_display_name"),
                            "model": payload.get("model"),
                            "response": payload.get("response"),
                            "summary": payload.get("summary"),
                            "citation_chunk_ids": payload.get("citation_chunk_ids"),
                        }
                    )
            if plan_update and last_call_payload:
                break

        if plan_update is not None:
            updates["active_plan"] = plan_update
        if plan_complete is not None:
            updates["plan_complete"] = plan_complete
        if recent_updates:
            updates["recent_agent_calls"] = recent_updates
        if compare_updates:
            updates["compare_outputs"] = compare_updates

        if last_call_payload:
            critic_payload = last_call_payload.get("critic") or {}
            if isinstance(critic_payload, dict):
                if critic_payload.get("status") == "needs_more":
                    updates["plan_complete"] = False

        # Progressive message pruning when messages get long
        messages = state.get("messages") or []
        if len(messages) > MESSAGE_PRUNING_THRESHOLD:
            # Count ToolMessages
            tool_msgs = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage)]
            if len(tool_msgs) > TOOL_MSG_THRESHOLD:
                # Keep only the last KEEP_TOOL_MSG_COUNT tool messages and their context
                keep_from = tool_msgs[-KEEP_TOOL_MSG_COUNT]
                # Find the AI message that triggered the first kept tool message
                keep_start = max(0, keep_from - 1)
                
                # Summarize what we're dropping
                dropped_count = keep_start
                if dropped_count > 0:
                    pruned = messages[keep_start:]
                    summary_msg = SystemMessage(
                        content=f"[{dropped_count} earlier messages (including tool calls) condensed. Recent context retained.]"
                    )
                    # Preserve any leading system messages
                    leading_system = [m for m in messages[:keep_start] if isinstance(m, SystemMessage)]
                    updates["messages"] = leading_system + [summary_msg] + pruned

        return updates

    def should_continue(state: SupervisorState, *, store=None):
        messages = state.get("messages") or []
        if not messages:
            return END
        last_message = messages[-1]
        if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    graph_builder = StateGraph(SupervisorState)
    graph_builder.add_node("agent", RunnableCallable(call_model, acall_model))
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("post_tools", RunnableCallable(None, post_tools))
    graph_builder.set_entry_point("agent")
    graph_builder.add_conditional_edges("agent", should_continue, path_map=["tools", END])
    graph_builder.add_edge("tools", "post_tools")
    graph_builder.add_edge("post_tools", "agent")

    return graph_builder.compile(checkpointer=checkpointer, name="supervisor-agent")
