from __future__ import annotations

import asyncio
import ast
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
from app.agents.new_chat.prompt_registry import resolve_prompt
from app.agents.new_chat.response_compressor import compress_response
from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
from app.agents.new_chat.supervisor_runtime_prompts import (
    DEFAULT_SUPERVISOR_CRITIC_PROMPT,
    DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
    DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
    DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE,
)
from app.agents.new_chat.supervisor_pipeline_prompts import (
    DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
    DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
    DEFAULT_SUPERVISOR_PLANNER_PROMPT,
    DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
)
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
_LOOP_GUARD_TOOL_NAMES = {
    "retrieve_agents",
    "call_agents_parallel",
    "reflect_on_progress",
    "write_todos",
}
_LOOP_GUARD_MAX_CONSECUTIVE = 12
_MAX_AGENT_HOPS_PER_TURN = 3
_AGENT_NAME_ALIAS_MAP = {
    "weather": "weather",
    "weather_agent": "weather",
    "smhi": "weather",
    "smhi_agent": "weather",
    "traffic_information": "trafik",
    "traffic_info": "trafik",
    "traffic_agent": "trafik",
    "road_works_planner": "trafik",
    "roadworks_planner": "trafik",
    "road_work_planner": "trafik",
    "roadworks": "trafik",
    "municipality_agent": "statistics",
    "map_agent": "kartor",
    "maps_agent": "kartor",
    "statistic_agent": "statistics",
    "statistics_agent": "statistics",
    "parliament_agent": "riksdagen",
    "company_agent": "bolag",
    "code_agent": "code",
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
_TRAFFIC_STRICT_INTENT_RE = re.compile(
    r"\b("
    r"trafikverket|"
    r"olycka|storing|storning|störning|"
    r"koer|köer|ko|kö|"
    r"vagarbete|vägarbete|avstangning|avstängning|omledning|framkomlighet|"
    r"kamera|kameror|"
    r"vaglag|väglag|hastighet|"
    r"e\d+|rv\s?\d+|riksvag|riksväg|vag\s?\d+|väg\s?\d+"
    r")\b",
    re.IGNORECASE,
)
_TRAFFIC_INCIDENT_STRICT_RE = re.compile(
    r"\b("
    r"trafikverket|"
    r"olycka|storing|storning|störning|"
    r"koer|köer|ko|kö|"
    r"vagarbete|vägarbete|avstangning|avstängning|omledning|framkomlighet|"
    r"kamera|kameror|"
    r"tagforsening|tågförsening|forsening|försening|installd|inställd|"
    r"trafikinfo"
    r")\b",
    re.IGNORECASE,
)
_WEATHER_INTENT_RE = re.compile(
    r"\b("
    r"smhi|vader|väder|temperatur|regn|sno|snö|vind|vindhastighet|"
    r"halka|isrisk|vaglag|väglag|vagvader|vägväder|"
    r"nederbord|nederbörd|prognos|sol|moln|luftfuktighet"
    r")\b",
    re.IGNORECASE,
)
_MAP_INTENT_RE = re.compile(
    r"\b(karta|kartbild|kartor|map|marker|markor|pin|"
    r"rutt|route|vagbeskrivning|vägbeskrivning)\b",
    re.IGNORECASE,
)
_MISSING_SIGNAL_RE = re.compile(
    r"\b(saknar|behöver|behover|ange|specificera|uppge|oklart|otydligt)\b",
    re.IGNORECASE,
)
_UNAVAILABLE_RESPONSE_MARKERS = (
    "finns inte tillganglig",
    "finns inte tillgänglig",
    "publiceras inte",
    "inte tillganglig",
    "inte tillgänglig",
    "framtida ar",
    "framtida år",
    "har inte publicerats",
    "saknas for",
    "saknas för",
)
_ALTERNATIVE_RESPONSE_MARKERS = (
    "senaste tillgangliga",
    "senaste tillgängliga",
    "istallet",
    "istället",
    "vill du ha",
    "kan ge",
    "kan visa",
    "2023",
    "2024",
)
_BLOCKED_RESPONSE_MARKERS = (
    "jag kan inte",
    "jag kunde inte",
    "kan tyvarr inte",
    "kan tyvärr inte",
    "saknar tillgang",
    "saknar tillgång",
    "utan tillgang",
    "utan tillgång",
    "annan agent behovs",
    "annan agent behövs",
    "behover annan agent",
    "behöver annan agent",
)
_MISSING_FIELD_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("datum", ("datum", "period", "vecka", "manad", "månad", "ar", "år")),
    ("tid", ("tid", "klockslag", "timme", "avgangstid", "avgångstid")),
    ("plats", ("plats", "ort", "stad", "kommun", "adress", "koordinat")),
    ("stracka", ("stracka", "sträcka", "riktning", "vagnummer", "vägnummer")),
    ("id", ("id", "organisationsnummer", "personnummer", "beteckning")),
    ("kategori", ("kategori", "typ", "slag")),
)
_RESULT_STATUS_VALUES = {"success", "partial", "blocked", "error"}
_ROUTE_STRICT_AGENT_POLICIES: dict[str, set[str]] = {
    "statistics": {"statistics"},
    "compare": {"synthesis", "statistics", "knowledge"},
}


def _has_trafik_intent(text: str) -> bool:
    return bool(text and _TRAFFIC_INTENT_RE.search(text))


def _has_map_intent(text: str) -> bool:
    return bool(text and _MAP_INTENT_RE.search(text))


def _has_strict_trafik_intent(text: str) -> bool:
    if not text:
        return False
    if not _TRAFFIC_STRICT_INTENT_RE.search(text):
        return False
    if _has_weather_intent(text):
        # For mixed weather+road queries, only keep strict traffic lock when
        # clear incident/disruption intent exists.
        return bool(_TRAFFIC_INCIDENT_STRICT_RE.search(text))
    return True


def _has_weather_intent(text: str) -> bool:
    return bool(text and _WEATHER_INTENT_RE.search(text))


def _is_weather_tool_id(tool_id: str) -> bool:
    normalized = str(tool_id or "").strip().lower()
    if not normalized:
        return False
    if normalized == "smhi_weather":
        return True
    if normalized.startswith("trafikverket_vader_"):
        return True
    return False


def _normalize_route_hint_value(value: Any) -> str:
    return str(value or "").strip().lower()


def _route_allowed_agents(route_hint: str | None) -> set[str]:
    route = _normalize_route_hint_value(route_hint)
    return set(_ROUTE_STRICT_AGENT_POLICIES.get(route, set()))


def _route_default_agent(route_hint: str | None, allowed: set[str] | None = None) -> str:
    route = _normalize_route_hint_value(route_hint)
    defaults = {
        "action": "action",
        "knowledge": "knowledge",
        "statistics": "statistics",
        "compare": "synthesis",
        "trafik": "trafik",
    }
    preferred = defaults.get(route, "knowledge")
    if allowed:
        if preferred in allowed:
            return preferred
        for name in ("statistics", "synthesis", "knowledge", "action", "trafik"):
            if name in allowed:
                return name
    return preferred


def _looks_complete_unavailability_answer(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if len(lowered) < 80:
        return False
    has_unavailable = any(marker in lowered for marker in _UNAVAILABLE_RESPONSE_MARKERS)
    has_alternative = any(marker in lowered for marker in _ALTERNATIVE_RESPONSE_MARKERS)
    return has_unavailable and has_alternative


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
    lines.append(
        "Om inget av dessa verktyg passar uppgiften: kor retrieve_tools igen med forfinad intent innan fortsattning."
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
            "Om uppgiften byter amne eller inte matchar domanen: gor ny retrieve_tools innan nasta verktygsval.",
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
    return right


def _append_recent(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if right == []:
        return []
    merged = list(left or [])
    merged.extend(right or [])
    return merged[-3:]


def _append_compare_outputs(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    if right == []:
        return []
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
    turn_id: Annotated[str | None, _replace]
    active_turn_id: Annotated[str | None, _replace]
    resolved_intent: Annotated[dict[str, Any] | None, _replace]
    selected_agents: Annotated[list[dict[str, Any]], _replace]
    query_embedding: Annotated[list[float] | None, _replace]
    active_plan: Annotated[list[dict[str, Any]], _replace]
    plan_step_index: Annotated[int | None, _replace]
    plan_complete: Annotated[bool, _replace]
    step_results: Annotated[list[dict[str, Any]], _replace]
    recent_agent_calls: Annotated[list[dict[str, Any]], _append_recent]
    route_hint: Annotated[str | None, _replace]
    compare_outputs: Annotated[list[dict[str, Any]], _append_compare_outputs]
    final_agent_response: Annotated[str | None, _replace]
    final_response: Annotated[str | None, _replace]
    critic_decision: Annotated[str | None, _replace]
    awaiting_confirmation: Annotated[bool | None, _replace]
    user_feedback: Annotated[dict[str, Any] | None, _replace]
    replan_count: Annotated[int | None, _replace]
    final_agent_name: Annotated[str | None, _replace]
    orchestration_phase: Annotated[str | None, _replace]
    agent_hops: Annotated[int | None, _replace]
    no_progress_runs: Annotated[int | None, _replace]
    guard_parallel_preview: Annotated[list[str], _replace]


_MAX_TOOL_CALLS_PER_TURN = 12
_MAX_SUPERVISOR_TOOL_CALLS_PER_STEP = 1
_MAX_REPLAN_ATTEMPTS = 2


def _count_tools_since_last_user(messages: list[Any]) -> int:
    count = 0
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage):
            count += 1
    return count


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


def _format_intent_context(state: dict[str, Any]) -> str | None:
    intent = state.get("resolved_intent")
    if not isinstance(intent, dict):
        return None
    intent_id = str(intent.get("intent_id") or "").strip()
    route = str(intent.get("route") or "").strip()
    reason = str(intent.get("reason") or "").strip()
    if not (intent_id or route):
        return None
    lines = [f"intent_id={intent_id or 'unknown'}", f"route={route or 'unknown'}"]
    if reason:
        lines.append(f"reason={_truncate_for_prompt(reason, 180)}")
    return "<resolved_intent>\n" + "\n".join(lines) + "\n</resolved_intent>"


def _format_selected_agents_context(state: dict[str, Any]) -> str | None:
    selected = state.get("selected_agents")
    if not isinstance(selected, list) or not selected:
        return None
    lines: list[str] = []
    for item in selected[:3]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        description = str(item.get("description") or "").strip()
        if description:
            lines.append(f"- {name}: {_truncate_for_prompt(description, 140)}")
        else:
            lines.append(f"- {name}")
    if not lines:
        return None
    return "<selected_agents>\n" + "\n".join(lines) + "\n</selected_agents>"




def _safe_json(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return {}


def _extract_first_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    if not value:
        return {}
    direct = _safe_json(value)
    if direct:
        return direct
    start = value.find("{")
    if start < 0:
        return {}
    segment = value[start:]
    try:
        decoded, _ = _CRITIC_JSON_DECODER.raw_decode(segment)
        if isinstance(decoded, dict):
            return decoded
    except Exception:
        pass
    for end in range(start + 1, min(len(value), start + 4000)):
        if value[end : end + 1] != "}":
            continue
        candidate = value[start : end + 1]
        parsed = _safe_json(candidate)
        if parsed:
            return parsed
        try:
            literal = ast.literal_eval(candidate)
            if isinstance(literal, dict):
                return literal
        except Exception:
            continue
    return {}


def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(0.0, min(1.0, parsed)), 2)


def _tool_call_name_index(messages: list[Any] | None) -> dict[str, str]:
    index: dict[str, str] = {}
    for message in messages or []:
        if not isinstance(message, AIMessage):
            continue
        tool_calls = getattr(message, "tool_calls", None) or []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_call_id = str(tool_call.get("id") or "").strip()
            tool_name = str(tool_call.get("name") or "").strip()
            if tool_call_id and tool_name and tool_call_id not in index:
                index[tool_call_id] = tool_name
    return index


def _infer_tool_name_from_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    if "agent" in payload and "task" in payload and "result_contract" in payload:
        return "call_agent"
    if isinstance(payload.get("results"), list):
        return "call_agents_parallel"
    if "todos" in payload:
        return "write_todos"
    if "reflection" in payload:
        return "reflect_on_progress"
    return ""


def _resolve_tool_message_name(
    message: ToolMessage,
    *,
    tool_call_index: dict[str, str] | None = None,
) -> str:
    explicit_name = str(getattr(message, "name", "") or "").strip()
    if explicit_name:
        return explicit_name
    tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
    if tool_call_id and tool_call_index:
        indexed_name = str(tool_call_index.get(tool_call_id) or "").strip()
        if indexed_name:
            return indexed_name
    payload_name = _infer_tool_name_from_payload(_safe_json(getattr(message, "content", "")))
    return payload_name


def _tool_call_priority(
    tool_name: str,
    *,
    orchestration_phase: str,
    agent_hops: int,
) -> int:
    normalized_tool = str(tool_name or "").strip()
    phase = str(orchestration_phase or "").strip().lower()
    if phase == "select_agent" or agent_hops <= 0:
        ordering = {
            "retrieve_agents": 0,
            "call_agent": 1,
            "call_agents_parallel": 2,
            "write_todos": 3,
            "reflect_on_progress": 4,
        }
    else:
        ordering = {
            "call_agent": 0,
            "call_agents_parallel": 1,
            "retrieve_agents": 2,
            "write_todos": 3,
            "reflect_on_progress": 4,
        }
    if normalized_tool in _EXTERNAL_MODEL_TOOL_NAMES:
        return 5
    return ordering.get(normalized_tool, 99)


def _coerce_supervisor_tool_calls(
    message: Any,
    *,
    orchestration_phase: str,
    agent_hops: int,
    allow_multiple: bool,
) -> Any:
    if allow_multiple or not isinstance(message, AIMessage):
        return message
    tool_calls = [
        tool_call
        for tool_call in (getattr(message, "tool_calls", None) or [])
        if isinstance(tool_call, dict)
    ]
    if len(tool_calls) <= _MAX_SUPERVISOR_TOOL_CALLS_PER_STEP:
        return message
    ranked = sorted(
        enumerate(tool_calls),
        key=lambda item: (
            _tool_call_priority(
                str(item[1].get("name") or ""),
                orchestration_phase=orchestration_phase,
                agent_hops=agent_hops,
            ),
            item[0],
        ),
    )
    chosen_call = ranked[0][1]
    try:
        return message.model_copy(update={"tool_calls": [chosen_call]})
    except Exception:
        return AIMessage(
            content=str(getattr(message, "content", "") or ""),
            tool_calls=[chosen_call],
            additional_kwargs=dict(getattr(message, "additional_kwargs", {}) or {}),
            response_metadata=dict(getattr(message, "response_metadata", {}) or {}),
            id=getattr(message, "id", None),
        )


_CRITIC_SNIPPET_RE = re.compile(
    r"\{\s*[\"']status[\"']\s*:\s*[\"'](?:ok|needs_more)[\"'][\s\S]*?[\"']reason[\"']\s*:\s*[\"'][\s\S]*?[\"']\s*\}",
    re.IGNORECASE,
)
_CRITIC_JSON_DECODER = json.JSONDecoder()
_LINE_BULLET_PREFIX_RE = re.compile(r"^[-*•]+\s*")
_CITATION_TOKEN_RE = re.compile(r"\[citation:[^\]]+\]", re.IGNORECASE)
_CITATION_SPACING_RE = re.compile(r"\[citation:\s*([^\]]+?)\s*\]", re.IGNORECASE)


def _remove_inline_critic_payloads(text: str) -> tuple[str, bool]:
    if not text:
        return text, False
    parts: list[str] = []
    idx = 0
    removed = False
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            parts.append(text[idx:])
            break
        parts.append(text[idx:start])
        segment = text[start:]
        try:
            decoded, consumed = _CRITIC_JSON_DECODER.raw_decode(segment)
        except ValueError:
            decoded = None
            consumed = 0
            for end in range(start + 1, min(len(text), start + 2400)):
                if text[end : end + 1] != "}":
                    continue
                candidate = text[start : end + 1]
                try:
                    parsed = ast.literal_eval(candidate)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    decoded = parsed
                    consumed = len(candidate)
                    break
            if decoded is None:
                parts.append(text[start : start + 1])
                idx = start + 1
                continue
        status = (
            str(decoded.get("status") or "").strip().lower()
            if isinstance(decoded, dict)
            else ""
        )
        if isinstance(decoded, dict) and status in {"ok", "needs_more"} and "reason" in decoded:
            removed = True
            idx = start + consumed
            continue
        parts.append(text[start : start + consumed])
        idx = start + consumed
    return "".join(parts), removed


def _normalize_line_for_dedupe(line: str) -> str:
    value = str(line or "").strip()
    value = _LINE_BULLET_PREFIX_RE.sub("", value)
    value = _CITATION_TOKEN_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-").lower()
    return value


def _dedupe_repeated_lines(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 4:
        return text.strip()
    seen: set[str] = set()
    deduped: list[str] = []
    duplicates = 0
    for line in lines:
        normalized = _normalize_line_for_dedupe(line)
        if normalized and len(normalized) >= 24:
            if normalized in seen:
                duplicates += 1
                continue
            seen.add(normalized)
        deduped.append(line)
    result = "\n".join(deduped).strip()
    if duplicates > 0:
        result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _normalize_citation_spacing(text: str) -> str:
    if not text:
        return text
    return _CITATION_SPACING_RE.sub(
        lambda match: f"[citation:{str(match.group(1) or '').strip()}]",
        text,
    )


def _strip_critic_json(text: str) -> str:
    if not text:
        return text
    cleaned = _CRITIC_SNIPPET_RE.sub("", text)
    cleaned, removed_inline = _remove_inline_critic_payloads(cleaned)
    if cleaned != text or removed_inline:
        cleaned = _dedupe_repeated_lines(cleaned)
    cleaned = _normalize_citation_spacing(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.rstrip()


def _render_guard_message(template: str, preview_lines: list[str]) -> str:
    preview_block = ""
    if preview_lines:
        preview_block = "Detta ar de senaste delresultaten:\n" + "\n".join(
            [str(item) for item in preview_lines[:3] if str(item).strip()]
        )
    try:
        rendered = str(template or "").format(recent_preview=preview_block)
    except Exception:
        rendered = str(template or "")
    rendered = rendered.strip()
    if preview_block and "{recent_preview}" not in str(template or ""):
        if preview_block not in rendered:
            rendered = (rendered + "\n" + preview_block).strip()
    return rendered


def _current_turn_key(state: dict[str, Any] | None) -> str:
    if not state:
        return "turn"
    active_turn_id = str(state.get("active_turn_id") or state.get("turn_id") or "").strip()
    if active_turn_id:
        digest = hashlib.sha1(active_turn_id.encode("utf-8")).hexdigest()
        return f"t{digest[:12]}"
    messages = state.get("messages") or []
    latest_human: HumanMessage | None = None
    human_count = 0
    for message in messages:
        if isinstance(message, HumanMessage):
            human_count += 1
            latest_human = message
    if latest_human is not None:
        message_id = str(getattr(latest_human, "id", "") or "").strip()
        content = str(getattr(latest_human, "content", "") or "").strip()
        seed = message_id or content or f"human:{human_count}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
        return f"h{human_count}:{digest[:12]}"
    return "turn"


def _latest_user_query(messages: list[Any] | None) -> str:
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return str(getattr(message, "content", "") or "").strip()
    return ""


def _tool_names_from_messages(messages: list[Any] | None) -> list[str]:
    names: list[str] = []
    tool_call_index = _tool_call_name_index(messages)
    for message in messages or []:
        if not isinstance(message, ToolMessage):
            continue
        name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if name and name not in names:
            names.append(name)
    return names


def _infer_missing_fields(response_text: str) -> list[str]:
    text = str(response_text or "").strip().lower()
    if not text or not _MISSING_SIGNAL_RE.search(text):
        return []
    missing: list[str] = []
    for field_name, hints in _MISSING_FIELD_HINTS:
        if any(hint in text for hint in hints):
            missing.append(field_name)
    return missing[:6]


def _looks_blocked_agent_response(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _BLOCKED_RESPONSE_MARKERS)


def _normalize_result_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in _RESULT_STATUS_VALUES:
        return status
    return "partial"


def _compute_contract_confidence(
    *,
    status: str,
    response_text: str,
    actionable: bool,
    missing_fields: list[str],
    used_tool_count: int,
    final_requested: bool,
) -> float:
    base = 0.45
    if status == "success":
        base = 0.78
    elif status == "blocked":
        base = 0.24
    elif status == "error":
        base = 0.08

    if actionable:
        base += 0.08
    if used_tool_count > 0:
        base += 0.05
    if used_tool_count >= 2:
        base += 0.03

    response_len = len(str(response_text or "").strip())
    if response_len >= 200:
        base += 0.05
    elif response_len < 40:
        base -= 0.10

    if missing_fields:
        base -= min(0.24, 0.08 * len(missing_fields))
    if final_requested and status == "success":
        base += 0.03

    base = max(0.01, min(0.99, base))
    return round(float(base), 2)


def _build_agent_result_contract(
    *,
    agent_name: str,
    task: str,
    response_text: str,
    error_text: str = "",
    used_tools: list[str] | None = None,
    final_requested: bool = False,
) -> dict[str, Any]:
    cleaned_response = _strip_critic_json(str(response_text or "").strip())
    error_value = str(error_text or "").strip()
    used_tool_names = [str(item).strip() for item in (used_tools or []) if str(item).strip()]
    missing_fields = _infer_missing_fields(cleaned_response)
    actionable = _looks_actionable_agent_answer(cleaned_response)
    blocked = _looks_blocked_agent_response(cleaned_response)
    complete_unavailable = _looks_complete_unavailability_answer(cleaned_response)

    if error_value:
        status = "error"
    elif not cleaned_response:
        status = "partial"
    elif complete_unavailable:
        status = "success"
        actionable = True
    elif blocked and not actionable:
        status = "blocked"
    elif missing_fields and not actionable:
        status = "partial"
    elif actionable:
        status = "success"
    else:
        status = "partial"

    confidence = _compute_contract_confidence(
        status=status,
        response_text=cleaned_response,
        actionable=actionable,
        missing_fields=missing_fields,
        used_tool_count=len(used_tool_names),
        final_requested=bool(final_requested),
    )
    retry_recommended = status in {"partial", "blocked", "error"}
    if status == "success" and confidence < 0.55:
        retry_recommended = True

    if status == "error":
        reason = (
            f"Agentfel: {error_value[:140]}"
            if error_value
            else "Agentkorningen misslyckades."
        )
    elif status == "blocked":
        reason = "Svar saknar tillrackligt underlag eller kraver annan agent."
    elif status == "partial":
        if missing_fields:
            reason = "Saknade falt: " + ", ".join(missing_fields[:4])
        else:
            reason = "Svar finns men bedoms inte komplett nog for finalisering."
    else:
        reason = "Svar bedoms tillrackligt komplett for finalisering."

    return {
        "status": status,
        "confidence": confidence,
        "actionable": bool(actionable),
        "missing_fields": missing_fields,
        "retry_recommended": bool(retry_recommended),
        "used_tools": used_tool_names[:6],
        "reason": reason,
        "agent": str(agent_name or "").strip(),
        "task_hash": hashlib.sha1(str(task or "").encode("utf-8")).hexdigest()[:12],
    }


def _contract_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    raw_contract = source.get("result_contract")
    if isinstance(raw_contract, dict):
        normalized_status = _normalize_result_status(raw_contract.get("status"))
        try:
            confidence = float(raw_contract.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = round(max(0.0, min(1.0, confidence)), 2)
        missing_fields_raw = raw_contract.get("missing_fields")
        missing_fields = (
            [
                str(item).strip()
                for item in missing_fields_raw
                if str(item).strip()
            ][:6]
            if isinstance(missing_fields_raw, list)
            else []
        )
        used_tools_raw = raw_contract.get("used_tools")
        used_tools = (
            [str(item).strip() for item in used_tools_raw if str(item).strip()][:6]
            if isinstance(used_tools_raw, list)
            else []
        )
        reason = str(raw_contract.get("reason") or "").strip()
        if not reason:
            reason = "Resultatkontrakt utan forklaring."
        if confidence <= 0.0 and (
            str(source.get("response") or "").strip() or str(source.get("error") or "").strip()
        ):
            fallback = _build_agent_result_contract(
                agent_name=str(source.get("agent") or ""),
                task=str(source.get("task") or ""),
                response_text=str(source.get("response") or ""),
                error_text=str(source.get("error") or ""),
                used_tools=used_tools,
                final_requested=bool(source.get("final")),
            )
            confidence = float(fallback.get("confidence") or confidence)
            if normalized_status == "partial":
                normalized_status = _normalize_result_status(fallback.get("status"))
            if not missing_fields:
                missing_fields = list(fallback.get("missing_fields") or [])
            if not reason:
                reason = str(fallback.get("reason") or "").strip()
        return {
            "status": normalized_status,
            "confidence": confidence,
            "actionable": bool(raw_contract.get("actionable")),
            "missing_fields": missing_fields,
            "retry_recommended": bool(raw_contract.get("retry_recommended")),
            "used_tools": used_tools,
            "reason": reason,
            "agent": str(raw_contract.get("agent") or source.get("agent") or "").strip(),
            "task_hash": str(raw_contract.get("task_hash") or "").strip(),
        }

    fallback_tools = source.get("used_tools")
    fallback_tool_list = (
        [str(item).strip() for item in fallback_tools if str(item).strip()]
        if isinstance(fallback_tools, list)
        else []
    )
    return _build_agent_result_contract(
        agent_name=str(source.get("agent") or ""),
        task=str(source.get("task") or ""),
        response_text=str(source.get("response") or ""),
        error_text=str(source.get("error") or ""),
        used_tools=fallback_tool_list,
        final_requested=bool(source.get("final")),
    )


def _should_finalize_from_contract(
    *,
    contract: dict[str, Any],
    response_text: str,
    route_hint: str,
    agent_name: str,
    latest_user_query: str,
    agent_hops: int,
) -> bool:
    response = _strip_critic_json(str(response_text or "").strip())
    if not response:
        return False
    if str(route_hint or "").strip().lower() == "compare":
        return False

    status = _normalize_result_status(contract.get("status"))
    actionable = bool(contract.get("actionable"))
    try:
        confidence = float(contract.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    missing_fields = contract.get("missing_fields")
    missing_count = len(missing_fields) if isinstance(missing_fields, list) else 0

    if status == "success" and actionable and confidence >= 0.55 and missing_count <= 1:
        return True

    normalized_agent = str(agent_name or "").strip().lower()
    if (
        str(route_hint or "").strip().lower() == "action"
        and normalized_agent == "trafik"
        and _has_strict_trafik_intent(latest_user_query)
        and actionable
        and status in {"success", "partial"}
        and confidence >= 0.45
        and missing_count <= 1
    ):
        return True

    if (
        agent_hops >= 2
        and actionable
        and status in {"success", "partial"}
        and confidence >= 0.60
        and missing_count == 0
    ):
        return True
    return False


def _normalize_task_for_fingerprint(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    value = re.sub(r"[^a-z0-9åäö\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180]


def _agent_call_entries_since_last_user(
    messages: list[Any] | None,
    *,
    turn_id: str | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    expected_turn_id = str(turn_id or "").strip()
    tool_call_index = _tool_call_name_index(messages)
    for message in messages or []:
        if isinstance(message, HumanMessage):
            entries = []
            continue
        if not isinstance(message, ToolMessage):
            continue
        resolved_name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if resolved_name != "call_agent":
            continue
        payload = _safe_json(getattr(message, "content", ""))
        if not isinstance(payload, dict):
            continue
        payload_turn_id = str(payload.get("turn_id") or "").strip()
        if expected_turn_id and payload_turn_id != expected_turn_id:
            continue
        entries.append(payload)
    return entries


def _looks_actionable_agent_answer(text: str) -> bool:
    value = str(text or "").strip()
    if len(value) < 32:
        return False
    lowered = value.lower()
    rejection_markers = (
        "jag kan inte",
        "jag kunde inte",
        "kan tyvarr inte",
        "kan tyvärr inte",
        "jag saknar",
        "jag behover",
        "jag behöver",
        "behover mer information",
        "behöver mer information",
        "inte möjligt",
        "not available",
        "cannot answer",
        "specificera",
        "ange mer",
    )
    if "inga " in lowered and (
        "hittades" in lowered
        or "fanns" in lowered
        or "rapporterades" in lowered
    ):
        return True
    return not any(marker in lowered for marker in rejection_markers)


def _best_actionable_entry(entries: list[dict[str, Any]]) -> tuple[str, str] | None:
    best: tuple[tuple[int, int, float, int], tuple[str, str]] | None = None
    status_rank = {"success": 3, "partial": 2, "blocked": 1, "error": 0}
    for entry in entries:
        response = _strip_critic_json(str(entry.get("response") or "").strip())
        if not response:
            continue
        contract = _contract_from_payload(entry)
        status = _normalize_result_status(contract.get("status"))
        actionable = bool(contract.get("actionable")) or _looks_actionable_agent_answer(
            response
        )
        try:
            confidence = float(contract.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        score = (
            1 if actionable else 0,
            status_rank.get(status, 0),
            confidence,
            len(response),
        )
        agent_name = str(entry.get("agent") or "").strip() or "agent"
        if best is None or score > best[0]:
            best = (score, (response, agent_name))
    if best:
        return best[1]
    return None


def _truncate_for_prompt(text: str, max_chars: int = TOOL_CONTEXT_MAX_CHARS) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _normalize_agent_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9åäö]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _guess_agent_from_alias(alias: str) -> str | None:
    normalized = _normalize_agent_identifier(alias)
    if not normalized:
        return None
    direct = _AGENT_NAME_ALIAS_MAP.get(normalized)
    if direct:
        return direct
    token_rules: list[tuple[tuple[str, ...], str]] = [
        (("smhi", "weather", "vader", "väder", "temperatur", "regn", "sno", "snö", "vind"), "weather"),
        (("trafik", "traffic", "road", "vag", "väg", "rail", "train"), "trafik"),
        (("map", "kart", "geo"), "kartor"),
        (("stat", "scb", "data"), "statistics"),
        (("riks", "parliament", "politik"), "riksdagen"),
        (("bolag", "company", "business", "org"), "bolag"),
        (("browser", "web", "scrape", "search"), "browser"),
        (("media", "podcast", "image", "video"), "media"),
        (("code", "python", "calc"), "code"),
        (("synth", "compare", "samman"), "synthesis"),
        (("knowledge", "docs", "internal", "external", "local"), "knowledge"),
        (("action", "travel"), "action"),
    ]
    for tokens, resolved in token_rules:
        if any(token in normalized for token in tokens):
            return resolved
    return None


def _summarize_parallel_results(results: Any) -> str:
    if not isinstance(results, list) or not results:
        return "results=0"
    success_count = 0
    error_count = 0
    snippets: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        response = str(item.get("response") or "").strip()
        error = str(item.get("error") or "").strip()
        if error:
            error_count += 1
        elif response:
            success_count += 1
    for item in results[:TOOL_CONTEXT_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "agent").strip() or "agent"
        response = _strip_critic_json(str(item.get("response") or "").strip())
        error = str(item.get("error") or "").strip()
        if response:
            snippets.append(f"{agent}: {_truncate_for_prompt(response, 140)}")
        elif error:
            snippets.append(f"{agent}: error {_truncate_for_prompt(error, 100)}")
        else:
            snippets.append(f"{agent}: completed")
    summary = f"results={len(results)}; success={success_count}; errors={error_count}"
    if snippets:
        summary += "; outputs=" + " | ".join(snippets)
    return _truncate_for_prompt(summary)


def _count_consecutive_loop_tools(messages: list[Any], *, turn_id: str | None = None) -> int:
    count = 0
    expected_turn_id = str(turn_id or "").strip()
    tool_call_index = _tool_call_name_index(messages)
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, ToolMessage):
            continue
        name = _resolve_tool_message_name(
            message,
            tool_call_index=tool_call_index,
        )
        if name == "call_agent":
            payload = _safe_json(getattr(message, "content", ""))
            payload_turn_id = (
                str(payload.get("turn_id") or "").strip()
                if isinstance(payload, dict)
                else ""
            )
            if expected_turn_id and payload_turn_id != expected_turn_id:
                break
            if isinstance(payload, dict) and str(payload.get("error") or "").strip():
                count += 1
                continue
            contract = _contract_from_payload(payload if isinstance(payload, dict) else {})
            status = _normalize_result_status(contract.get("status"))
            actionable = bool(contract.get("actionable"))
            try:
                confidence = float(contract.get("confidence"))
            except (TypeError, ValueError):
                confidence = 0.0
            if status == "success" and actionable and confidence >= 0.55:
                break
            if bool(contract.get("retry_recommended")) or status in {
                "partial",
                "blocked",
                "error",
            }:
                count += 1
                continue
            break
        if name in _LOOP_GUARD_TOOL_NAMES:
            count += 1
            continue
        break
    return count


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

    if name == "call_agents_parallel":
        return _truncate_for_prompt(
            f"{name}: {status}; {_summarize_parallel_results(payload.get('results'))}"
        )

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
    tool_call_index = _tool_call_name_index(messages)
    for message in messages:
        if isinstance(message, ToolMessage):
            resolved_tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            payload = _safe_json(message.content)
            if payload:
                response = payload.get("response")
                if isinstance(response, str):
                    agent = payload.get("agent") or resolved_tool_name or "agent"
                    response = _strip_critic_json(response)
                    contract = _contract_from_payload(payload)
                    status = _normalize_result_status(contract.get("status"))
                    try:
                        confidence = float(contract.get("confidence"))
                    except (TypeError, ValueError):
                        confidence = 0.0
                    status_prefix = ""
                    if status != "success" or confidence < 0.7:
                        status_prefix = f"[{status} {confidence:.2f}] "
                    content = (
                        _truncate_for_prompt(f"{agent}: {status_prefix}{response}")
                        if response
                        else f"{agent}: completed"
                    )
                    sanitized.append(
                        ToolMessage(
                            content=content,
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                if payload.get("status") and payload.get("reason"):
                    tool_name = resolved_tool_name or "tool"
                    sanitized.append(
                        ToolMessage(
                            content=_truncate_for_prompt(f"{tool_name}: completed"),
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                    continue
                summarized = _summarize_tool_payload(
                    resolved_tool_name or "tool",
                    payload,
                )
                sanitized.append(
                    ToolMessage(
                        content=summarized,
                        name=resolved_tool_name or message.name,
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
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                else:
                    sanitized.append(
                        ToolMessage(
                            content=f"{resolved_tool_name or 'tool'}: completed",
                            name=resolved_tool_name or message.name,
                            tool_call_id=getattr(message, "tool_call_id", None),
                        )
                    )
                continue
            if isinstance(message.content, str):
                trimmed = _strip_critic_json(message.content)
                if not trimmed:
                    trimmed = f"{resolved_tool_name or 'tool'}: completed"
                sanitized.append(
                    ToolMessage(
                        content=_truncate_for_prompt(trimmed),
                        name=resolved_tool_name or message.name,
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
    prompt_overrides = dict(tool_prompt_overrides or {})
    tool_prompt_overrides = dict(prompt_overrides)
    critic_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.critic.system",
        DEFAULT_SUPERVISOR_CRITIC_PROMPT,
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
    intent_resolver_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.intent_resolver.system",
        DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT,
    )
    agent_resolver_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.agent_resolver.system",
        DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT,
    )
    planner_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.planner.system",
        DEFAULT_SUPERVISOR_PLANNER_PROMPT,
    )
    critic_gate_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.critic_gate.system",
        DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT,
    )
    synthesizer_prompt_template = resolve_prompt(
        prompt_overrides,
        "supervisor.synthesizer.system",
        DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT,
    )
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
        "weather": WorkerConfig(
            name="weather-worker",
            primary_namespaces=[("tools", "weather")],
            fallback_namespaces=[
                ("tools", "action"),
                ("tools", "knowledge"),
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
        "weather": action_prompt,
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
            name="weather",
            description="SMHI-vaderprognoser och Trafikverkets vagvaderdata for svenska orter och vagar",
            keywords=[
                "smhi",
                "vader",
                "väder",
                "temperatur",
                "regn",
                "snö",
                "sno",
                "vind",
                "prognos",
                "halka",
                "isrisk",
                "vaglag",
                "väglag",
                "trafikverket väder",
            ],
            namespace=("agents", "weather"),
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
            description="Trafikverket realtidsdata (väg, tåg, kameror)",
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
    weather_tool_ids = ["smhi_weather"]
    weather_tool_ids.extend(
        definition.tool_id
        for definition in TRAFIKVERKET_TOOL_DEFINITIONS
        if _is_weather_tool_id(definition.tool_id)
    )
    weather_tool_ids = list(dict.fromkeys(weather_tool_ids))
    weather_tool_id_set = set(weather_tool_ids)
    trafik_tool_ids = [
        definition.tool_id
        for definition in TRAFIKVERKET_TOOL_DEFINITIONS
        if definition.tool_id not in weather_tool_id_set
    ]
    compare_external_prompt = external_model_prompt or DEFAULT_EXTERNAL_SYSTEM_PROMPT
    route_to_intent_id = {
        "knowledge": "knowledge",
        "action": "action",
        "statistics": "statistics",
        "compare": "compare",
        "smalltalk": "smalltalk",
    }

    def _intent_from_route(route_value: str | None) -> dict[str, Any]:
        normalized = _normalize_route_hint_value(route_value)
        intent_id = route_to_intent_id.get(normalized, "knowledge")
        return {
            "intent_id": intent_id,
            "route": normalized or "knowledge",
            "reason": "Fallback baserad pa route_hint.",
            "confidence": 0.5,
        }

    def _agent_payload(definition: AgentDefinition) -> dict[str, Any]:
        return {
            "name": definition.name,
            "description": definition.description,
            "keywords": list(definition.keywords or []),
        }

    def _resolve_agent_name(
        requested_name: str,
        *,
        task: str,
        state: dict[str, Any] | None = None,
    ) -> tuple[str | None, str | None]:
        requested_raw = str(requested_name or "").strip().lower()
        if not requested_raw:
            return None, "empty_name"
        route_hint = _normalize_route_hint_value((state or {}).get("route_hint"))
        route_allowed = _route_allowed_agents(route_hint)
        default_for_route = _route_default_agent(route_hint, route_allowed)
        strict_trafik_task = _has_strict_trafik_intent(task)
        weather_task = _has_weather_intent(task)
        if route_hint == "action" and weather_task and not strict_trafik_task:
            if requested_raw in agent_by_name and requested_raw != "weather":
                return "weather", f"weather_lock:{requested_raw}->weather"
        if route_hint == "action" and strict_trafik_task:
            allowed_for_strict = {"trafik", "kartor", "action"}
            if requested_raw in agent_by_name and requested_raw not in allowed_for_strict:
                return "trafik", f"strict_trafik_lock:{requested_raw}->trafik"
        if requested_raw in agent_by_name:
            if route_allowed and requested_raw not in route_allowed:
                if default_for_route in agent_by_name:
                    return default_for_route, f"route_policy:{requested_raw}->{default_for_route}"
            return requested_raw, None

        alias_guess = _guess_agent_from_alias(requested_raw)
        if alias_guess and alias_guess in agent_by_name:
            if route_allowed and alias_guess not in route_allowed:
                if default_for_route in agent_by_name:
                    return default_for_route, f"route_policy_alias:{requested_raw}->{default_for_route}"
            return alias_guess, f"alias:{requested_raw}->{alias_guess}"

        recent_agents: list[str] = []
        route_hint = None
        if state:
            route_hint = _normalize_route_hint_value(state.get("route_hint"))
            recent_calls = state.get("recent_agent_calls") or []
            recent_agents = [
                str(call.get("agent") or "").strip()
                for call in recent_calls
                if isinstance(call, dict) and str(call.get("agent") or "").strip()
            ]
        route_allowed = _route_allowed_agents(route_hint)
        default_for_route = _route_default_agent(route_hint, route_allowed)
        retrieval_query = (
            f"{task}\n"
            f"Agent hint from planner: {requested_raw}\n"
            "Resolve to one existing internal agent id."
        )
        retrieved = _smart_retrieve_agents(
            retrieval_query,
            agent_definitions=agent_definitions,
            recent_agents=recent_agents,
            limit=3,
        )
        if route_allowed:
            retrieved = [agent for agent in retrieved if agent.name in route_allowed]
        if route_hint:
            preferred = {
                "action": ["action", "media"],
                "knowledge": ["knowledge", "browser"],
                "statistics": ["statistics"],
                "compare": ["synthesis", "knowledge", "statistics"],
            }.get(str(route_hint), [])
            if str(route_hint) == "action":
                if weather_task and not strict_trafik_task:
                    preferred = ["weather", "action"]
                if _has_map_intent(task) and "kartor" not in preferred:
                    preferred.insert(0, "kartor")
                if _has_trafik_intent(task) and not weather_task and "trafik" not in preferred:
                    preferred.insert(0, "trafik")
            if route_allowed:
                preferred = [name for name in preferred if name in route_allowed]
            for preferred_name in preferred:
                if any(agent.name == preferred_name for agent in retrieved):
                    return preferred_name, f"route_pref:{requested_raw}->{preferred_name}"
        if retrieved:
            return retrieved[0].name, f"retrieval:{requested_raw}->{retrieved[0].name}"
        if route_allowed and default_for_route in agent_by_name:
            return default_for_route, f"route_default:{requested_raw}->{default_for_route}"
        return None, f"unresolved:{requested_raw}"

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
        limit: int = 1,
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Retrieve relevant agents for the task.

        IMPORTANT: Reuse agent names exactly as returned in `agents[].name`.
        Allowed internal ids include: action, weather, kartor, statistics, media, knowledge,
        browser, code, bolag, trafik, riksdagen, synthesis.
        """
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 1
        limit = max(1, min(limit, 2))

        recent_agents = []
        context_query = query
        route_hint = None
        cache_key = None
        cache_pattern = None
        policy_query = query
        if state:
            recent_calls = state.get("recent_agent_calls") or []
            recent_agents = [
                str(call.get("agent"))
                for call in recent_calls
                if call.get("agent")
            ]
            route_hint = _normalize_route_hint_value(state.get("route_hint"))
            latest_user_query = _latest_user_query(state.get("messages") or [])
            if latest_user_query:
                policy_query = latest_user_query
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

        has_trafik_intent = _has_trafik_intent(policy_query)
        has_strict_trafik_intent = _has_strict_trafik_intent(policy_query)
        has_map_intent = _has_map_intent(policy_query)
        has_weather_intent = _has_weather_intent(policy_query)
        route_allowed = _route_allowed_agents(route_hint)
        default_for_route = _route_default_agent(route_hint, route_allowed)
        if route_hint == "action" and has_weather_intent and not has_strict_trafik_intent:
            limit = 1
        if route_hint == "statistics":
            limit = 1

        cache_key, cache_pattern = _build_cache_key(
            query, route_hint, recent_agents
        )
        cached_agents = _get_cached_combo(cache_key)
        if cached_agents is None:
            cached_agents = await _fetch_cached_combo_db(db_session, cache_key)
            if cached_agents:
                _set_cached_combo(cache_key, cached_agents)
        if (
            cached_agents
            and route_hint == "action"
            and has_strict_trafik_intent
        ):
            # Avoid stale non-traffic combos on hard traffic queries.
            cached_agents = None
        if cached_agents and has_trafik_intent and "trafik" not in cached_agents:
            cached_agents = None
        if (
            cached_agents
            and route_hint == "action"
            and has_weather_intent
            and not has_strict_trafik_intent
            and "weather" not in cached_agents
        ):
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
                    if has_weather_intent and not has_strict_trafik_intent:
                        preferred = ["weather", "action"]
                    # Keep route_hint as advisory only unless action intent is explicit.
                    if not (has_map_intent or has_trafik_intent):
                        preferred = []
                    if has_weather_intent and not has_strict_trafik_intent:
                        preferred = ["weather", "action"]
                    if has_map_intent and "kartor" not in preferred:
                        preferred.insert(0, "kartor")
                    if (
                        has_trafik_intent
                        and not has_weather_intent
                        and "trafik" not in preferred
                    ):
                        preferred.insert(0, "trafik")
                if preferred:
                    for preferred_name in reversed(preferred):
                        agent = agent_by_name.get(preferred_name)
                        if not agent:
                            continue
                        if agent in selected:
                            selected = [item for item in selected if item != agent]
                        selected.insert(0, agent)
                    selected = selected[:limit]

            if (
                has_trafik_intent
                and not has_weather_intent
                and route_hint in {"action", "trafik"}
            ):
                trafik_agent = agent_by_name.get("trafik")
                if trafik_agent and trafik_agent not in selected:
                    selected.insert(0, trafik_agent)
                    selected = selected[:limit]

            if route_allowed:
                filtered = [agent for agent in selected if agent.name in route_allowed]
                if filtered:
                    selected = filtered
                elif default_for_route in agent_by_name:
                    selected = [agent_by_name[default_for_route]]

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

        if route_allowed:
            filtered = [agent for agent in selected if agent.name in route_allowed]
            if filtered:
                selected = filtered
            elif default_for_route in agent_by_name:
                selected = [agent_by_name[default_for_route]]

        selected = selected[:limit]
        if (
            route_hint == "action"
            and has_weather_intent
            and not has_strict_trafik_intent
        ):
            weather_order = ["weather", "action"]
            weather_selected = [
                agent_by_name[name] for name in weather_order if name in agent_by_name
            ]
            selected = weather_selected[:limit] if weather_selected else selected
        if route_hint == "action" and has_strict_trafik_intent:
            strict_order = ["trafik"]
            if has_map_intent:
                strict_order.append("kartor")
            strict_order.append("action")
            strict_selected = [
                agent_by_name[name] for name in strict_order if name in agent_by_name
            ]
            selected = strict_selected[:limit] if strict_selected else selected
        payload = [
            {"name": agent.name, "description": agent.description}
            for agent in selected
        ]
        return json.dumps(
            {
                "agents": payload,
                "valid_agent_ids": [agent.name for agent in agent_definitions],
            },
            ensure_ascii=True,
        )

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
        injected_state = state or {}
        requested_name = (agent_name or "").strip().lower()
        resolved_name, resolution_reason = _resolve_agent_name(
            requested_name,
            task=task,
            state=injected_state,
        )
        name = resolved_name or requested_name
        current_turn_id = str(
            injected_state.get("active_turn_id") or injected_state.get("turn_id") or ""
        ).strip()
        worker = await worker_pool.get(name)
        if not worker:
            error_message = f"Agent '{agent_name}' not available."
            return json.dumps(
                {
                    "agent": name,
                    "requested_agent": requested_name,
                    "agent_resolution": resolution_reason,
                    "error": error_message,
                    "result_contract": _build_agent_result_contract(
                        agent_name=name,
                        task=task,
                        response_text="",
                        error_text=error_message,
                        used_tools=[],
                        final_requested=bool(final),
                    ),
                    "turn_id": current_turn_id,
                },
                ensure_ascii=True,
            )
        if name == "synthesis" and injected_state:
            task = _prepare_task_for_synthesis(task, injected_state)
        turn_key = _current_turn_key(injected_state)
        base_thread_id = str(dependencies.get("thread_id") or "thread")
        selected_tool_ids: list[str] = _focused_tool_ids_for_agent(name, task, limit=6)
        if name == "weather":
            selected_tool_ids = list(weather_tool_ids)
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
        worker_state = {"messages": messages, "selected_tool_ids": selected_tool_ids}
        config = {
            "configurable": {"thread_id": f"{base_thread_id}:{name}:{turn_key}"},
            "recursion_limit": 60,
        }
        result = await worker.ainvoke(worker_state, config=config)
        response_text = ""
        messages_out: list[Any] = []
        if isinstance(result, dict):
            messages_out = result.get("messages") or []
            if messages_out:
                response_text = str(getattr(messages_out[-1], "content", "") or "")
            if name == "trafik":
                initial_tool_names = _tool_names_from_messages(messages_out)
                used_trafik_tool = any(
                    tool_name.startswith("trafikverket_")
                    for tool_name in initial_tool_names
                )
                if not used_trafik_tool:
                    enforced_prompt = (
                        f"{prompt.rstrip()}\n\n{trafik_enforcement_message}".strip()
                        if prompt
                        else trafik_enforcement_message
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
        used_tool_names = _tool_names_from_messages(messages_out)

        critic_prompt = append_datetime_context(critic_prompt_template)
        critic_input = f"Uppgift: {task}\nSvar: {response_text}"
        try:
            critic_msg = await llm.ainvoke(
                [SystemMessage(content=critic_prompt), HumanMessage(content=critic_input)]
            )
            critic_text = str(getattr(critic_msg, "content", "") or "").strip()
            critic_payload = _safe_json(critic_text)
            if not critic_payload:
                critic_payload = {"status": "ok", "reason": critic_text}
        except Exception as exc:  # pragma: no cover - defensive fallback
            critic_payload = {
                "status": "unavailable",
                "reason": f"critic_unavailable:{type(exc).__name__}",
            }

        response_text = _strip_critic_json(response_text)
        result_contract = _build_agent_result_contract(
            agent_name=name,
            task=task,
            response_text=response_text,
            used_tools=used_tool_names,
            final_requested=bool(final),
        )

        # Compress response for context efficiency when not final
        if not final:
            response_text = compress_response(response_text, agent_name=name)

        return json.dumps(
            {
                "agent": name,
                "requested_agent": requested_name,
                "agent_resolution": resolution_reason,
                "task": task,
                "response": response_text,
                "used_tools": used_tool_names,
                "result_contract": result_contract,
                "critic": critic_payload,
                "final": bool(final),
                "turn_id": current_turn_id,
            },
            ensure_ascii=True,
        )

    @tool
    async def call_agents_parallel(
        calls: list[dict],
        state: Annotated[dict[str, Any], InjectedState] | None = None,
    ) -> str:
        """Call multiple agents in parallel. Each call dict has 'agent' and 'task' keys.
        Use when tasks are independent and don't depend on each other's results.

        IMPORTANT: Use exact internal agent ids from retrieve_agents()."""
        injected_state = state or {}
        current_turn_id = str(
            injected_state.get("active_turn_id") or injected_state.get("turn_id") or ""
        ).strip()
        serialized_mode = not compare_mode
        dropped_calls = 0
        if serialized_mode and isinstance(calls, list) and len(calls) > 1:
            dropped_calls = len(calls) - 1
            calls = calls[:1]
        
        async def _run_one(call_spec: dict) -> dict:
            requested_agent_name = (call_spec.get("agent") or "").strip().lower()
            task = call_spec.get("task") or ""
            resolved_agent_name, resolution_reason = _resolve_agent_name(
                requested_agent_name,
                task=task,
                state=injected_state,
            )
            agent_name = resolved_agent_name or requested_agent_name
            worker = await worker_pool.get(agent_name)
            if not worker:
                error_message = f"Agent '{agent_name}' not available."
                return {
                    "agent": agent_name,
                    "requested_agent": requested_agent_name,
                    "agent_resolution": resolution_reason,
                    "error": error_message,
                    "result_contract": _build_agent_result_contract(
                        agent_name=agent_name,
                        task=task,
                        response_text="",
                        error_text=error_message,
                        used_tools=[],
                        final_requested=False,
                    ),
                    "turn_id": current_turn_id,
                }
            try:
                # Reuse same worker invocation logic as call_agent
                if agent_name == "synthesis" and injected_state:
                    task = _prepare_task_for_synthesis(task, injected_state)
                turn_key = _current_turn_key(injected_state)
                base_thread_id = str(dependencies.get("thread_id") or "thread")
                selected_tool_ids = _focused_tool_ids_for_agent(agent_name, task, limit=6)
                if agent_name == "weather":
                    selected_tool_ids = list(weather_tool_ids)
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
                    "configurable": {
                        "thread_id": f"{base_thread_id}:{agent_name}:{turn_key}"
                    },
                    "recursion_limit": 60,
                }
                result = await worker.ainvoke(worker_state, config=config)
                response_text = ""
                messages_out: list[Any] = []
                if isinstance(result, dict):
                    messages_out = result.get("messages") or []
                    if messages_out:
                        last_msg = messages_out[-1]
                        response_text = str(getattr(last_msg, "content", "") or "")
                if not response_text:
                    response_text = str(result)
                response_text = _strip_critic_json(response_text)
                used_tool_names = _tool_names_from_messages(messages_out)
                result_contract = _build_agent_result_contract(
                    agent_name=agent_name,
                    task=task,
                    response_text=response_text,
                    used_tools=used_tool_names,
                    final_requested=False,
                )
                return {
                    "agent": agent_name,
                    "requested_agent": requested_agent_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "response": response_text,
                    "used_tools": used_tool_names,
                    "result_contract": result_contract,
                    "turn_id": current_turn_id,
                }
            except Exception as exc:
                error_message = str(exc)
                return {
                    "agent": agent_name,
                    "requested_agent": requested_agent_name,
                    "agent_resolution": resolution_reason,
                    "task": task,
                    "error": error_message,
                    "error_type": type(exc).__name__,
                    "result_contract": _build_agent_result_contract(
                        agent_name=agent_name,
                        task=task,
                        response_text="",
                        error_text=error_message,
                        used_tools=[],
                        final_requested=False,
                    ),
                    "turn_id": current_turn_id,
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
        
        return json.dumps(
            {
                "results": processed,
                "serialized_mode": serialized_mode,
                "dropped_calls": dropped_calls,
            },
            ensure_ascii=True,
        )

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

    async def resolve_intent_node(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        if not new_user_turn and state.get("resolved_intent"):
            return {}

        latest_user_query = _latest_user_query(state.get("messages") or [])
        route_hint = _normalize_route_hint_value(state.get("route_hint"))
        candidates: list[dict[str, Any]] = []
        for route_name, intent_id in route_to_intent_id.items():
            candidates.append({"intent_id": intent_id, "route": route_name})
        if route_hint:
            candidates.sort(key=lambda item: 0 if item.get("route") == route_hint else 1)
        candidate_ids = {
            str(item.get("intent_id") or "").strip()
            for item in candidates
            if str(item.get("intent_id") or "").strip()
        }

        resolved = _intent_from_route(route_hint)
        if latest_user_query:
            prompt = append_datetime_context(intent_resolver_prompt_template)
            resolver_input = json.dumps(
                {
                    "query": latest_user_query,
                    "route_hint": route_hint,
                    "intent_candidates": candidates,
                },
                ensure_ascii=True,
            )
            try:
                message = await llm.ainvoke(
                    [
                        SystemMessage(content=prompt),
                        HumanMessage(content=resolver_input),
                    ]
                )
                parsed = _extract_first_json_object(
                    str(getattr(message, "content", "") or "")
                )
                selected_intent = str(parsed.get("intent_id") or "").strip()
                selected_route = _normalize_route_hint_value(parsed.get("route"))
                if selected_intent and selected_intent in candidate_ids:
                    resolved = {
                        "intent_id": selected_intent,
                        "route": selected_route
                        or next(
                            (
                                str(item.get("route") or "")
                                for item in candidates
                                if str(item.get("intent_id") or "").strip()
                                == selected_intent
                            ),
                            route_hint or "knowledge",
                        ),
                        "reason": str(parsed.get("reason") or "").strip()
                        or "LLM intent_resolver valde intent.",
                        "confidence": _coerce_confidence(parsed.get("confidence"), 0.5),
                    }
            except Exception:
                pass

        updates: SupervisorState = {
            "resolved_intent": resolved,
            "orchestration_phase": "select_agent",
        }
        if new_user_turn:
            updates["active_plan"] = []
            updates["plan_step_index"] = 0
            updates["plan_complete"] = False
            updates["step_results"] = []
            updates["recent_agent_calls"] = []
            updates["compare_outputs"] = []
            updates["selected_agents"] = []
            updates["final_agent_response"] = None
            updates["final_response"] = None
            updates["critic_decision"] = None
            updates["awaiting_confirmation"] = False
            updates["user_feedback"] = None
            updates["replan_count"] = 0
            updates["agent_hops"] = 0
            updates["no_progress_runs"] = 0
            updates["guard_parallel_preview"] = []
            if incoming_turn_id:
                updates["active_turn_id"] = incoming_turn_id
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id
        return updates

    async def resolve_agents_node(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        latest_user_query = _latest_user_query(state.get("messages") or [])
        if not latest_user_query:
            return {}
        intent_data = state.get("resolved_intent") or {}
        route_hint = _normalize_route_hint_value(
            intent_data.get("route") or state.get("route_hint")
        )
        route_allowed = _route_allowed_agents(route_hint)
        default_for_route = _route_default_agent(route_hint, route_allowed)
        recent_calls = state.get("recent_agent_calls") or []
        recent_agents = [
            str(item.get("agent") or "").strip()
            for item in recent_calls[-3:]
            if isinstance(item, dict) and str(item.get("agent") or "").strip()
        ]
        selected = _smart_retrieve_agents(
            latest_user_query,
            agent_definitions=agent_definitions,
            recent_agents=recent_agents,
            limit=3,
        )
        if route_allowed:
            filtered = [agent for agent in selected if agent.name in route_allowed]
            if filtered:
                selected = filtered
            elif default_for_route in agent_by_name:
                selected = [agent_by_name[default_for_route]]
        selected_payload = [_agent_payload(agent) for agent in selected]
        if not selected_payload and default_for_route in agent_by_name:
            selected_payload = [_agent_payload(agent_by_name[default_for_route])]

        prompt = append_datetime_context(agent_resolver_prompt_template)
        resolver_input = json.dumps(
            {
                "query": latest_user_query,
                "resolved_intent": intent_data if isinstance(intent_data, dict) else {},
                "agent_candidates": selected_payload,
            },
            ensure_ascii=True,
        )
        try:
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=resolver_input),
                ]
            )
            parsed = _extract_first_json_object(str(getattr(message, "content", "") or ""))
            requested = parsed.get("selected_agents")
            if isinstance(requested, list) and requested:
                by_name = {
                    str(item.get("name") or "").strip(): item
                    for item in selected_payload
                    if isinstance(item, dict)
                }
                ordered: list[dict[str, Any]] = []
                for name in requested:
                    normalized = str(name or "").strip()
                    if normalized and normalized in by_name:
                        ordered.append(by_name[normalized])
                if ordered:
                    selected_payload = ordered[:3]
        except Exception:
            pass
        return {
            "selected_agents": selected_payload[:3],
            "orchestration_phase": "plan",
        }

    async def planner_node(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        latest_user_query = _latest_user_query(state.get("messages") or [])
        selected_agents = [
            item
            for item in (state.get("selected_agents") or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        if not latest_user_query:
            return {"orchestration_phase": "execute"}

        current_plan = state.get("active_plan") or []
        if current_plan and not state.get("plan_complete") and not state.get("critic_decision"):
            return {"orchestration_phase": "execute"}

        prompt = append_datetime_context(planner_prompt_template)
        planner_input = json.dumps(
            {
                "query": latest_user_query,
                "resolved_intent": state.get("resolved_intent") or {},
                "selected_agents": selected_agents,
                "current_plan": current_plan,
            },
            ensure_ascii=True,
        )
        new_plan: list[dict[str, Any]] = []
        try:
            message = await llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=planner_input),
                ]
            )
            parsed = _extract_first_json_object(str(getattr(message, "content", "") or ""))
            steps = parsed.get("steps")
            if isinstance(steps, list):
                for index, step in enumerate(steps[:4], start=1):
                    if isinstance(step, dict):
                        content = str(step.get("content") or "").strip()
                        if not content:
                            continue
                        step_id = str(step.get("id") or f"step-{index}").strip()
                        status = str(step.get("status") or "pending").strip().lower()
                        if status not in {"pending", "in_progress", "completed", "cancelled"}:
                            status = "pending"
                        new_plan.append(
                            {
                                "id": step_id,
                                "content": content,
                                "status": status,
                            }
                        )
        except Exception:
            pass

        if not new_plan:
            fallback_agent = (
                str(selected_agents[0].get("name") or "").strip()
                if selected_agents
                else "agent"
            )
            new_plan = [
                {
                    "id": "step-1",
                    "content": f"Delegara huvuduppgiften till {fallback_agent}",
                    "status": "pending",
                }
            ]
        return {
            "active_plan": new_plan,
            "plan_step_index": 0,
            "plan_complete": False,
            "orchestration_phase": "execute",
            "critic_decision": None,
        }

    async def critic_node(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        final_response = str(
            state.get("final_agent_response") or state.get("final_response") or ""
        ).strip()
        if not final_response:
            replan_count = int(state.get("replan_count") or 0)
            if replan_count >= _MAX_REPLAN_ATTEMPTS:
                fallback = _render_guard_message(
                    loop_guard_template,
                    list(state.get("guard_parallel_preview") or [])[:3],
                )
                if not fallback:
                    fallback = _render_guard_message(
                        DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
                        list(state.get("guard_parallel_preview") or [])[:3],
                    )
                return {
                    "critic_decision": "ok",
                    "final_response": fallback,
                    "final_agent_response": fallback,
                    "final_agent_name": "supervisor",
                    "orchestration_phase": "finalize",
                }
            return {
                "critic_decision": "needs_more",
                "replan_count": replan_count + 1,
                "orchestration_phase": "select_agent",
            }

        latest_user_query = _latest_user_query(state.get("messages") or [])
        prompt = append_datetime_context(critic_gate_prompt_template)
        critic_input = json.dumps(
            {
                "query": latest_user_query,
                "resolved_intent": state.get("resolved_intent") or {},
                "active_plan": state.get("active_plan") or [],
                "final_agent_name": state.get("final_agent_name"),
                "final_response": final_response,
            },
            ensure_ascii=True,
        )
        decision = "ok"
        try:
            message = await llm.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=critic_input)]
            )
            parsed = _extract_first_json_object(str(getattr(message, "content", "") or ""))
            parsed_decision = str(parsed.get("decision") or "").strip().lower()
            if parsed_decision in {"ok", "needs_more"}:
                decision = parsed_decision
        except Exception:
            decision = "ok"

        replan_count = int(state.get("replan_count") or 0)
        if decision == "needs_more" and replan_count < _MAX_REPLAN_ATTEMPTS:
            return {
                "critic_decision": "needs_more",
                "final_agent_response": None,
                "final_response": None,
                "replan_count": replan_count + 1,
                "orchestration_phase": "select_agent",
            }
        return {
            "critic_decision": "ok",
            "final_response": final_response,
            "orchestration_phase": "finalize",
        }

    async def synthesizer_node(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        source_response = str(
            state.get("final_response") or state.get("final_agent_response") or ""
        ).strip()
        if not source_response:
            return {}
        latest_user_query = _latest_user_query(state.get("messages") or [])
        prompt = append_datetime_context(synthesizer_prompt_template)
        synth_input = json.dumps(
            {
                "query": latest_user_query,
                "response": source_response,
                "resolved_intent": state.get("resolved_intent") or {},
            },
            ensure_ascii=True,
        )
        refined_response = source_response
        try:
            message = await llm.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=synth_input)]
            )
            parsed = _extract_first_json_object(str(getattr(message, "content", "") or ""))
            candidate = str(parsed.get("response") or "").strip()
            if candidate:
                refined_response = _strip_critic_json(candidate)
        except Exception:
            refined_response = source_response

        messages = list(state.get("messages") or [])
        last_message = messages[-1] if messages else None
        if isinstance(last_message, AIMessage):
            if str(getattr(last_message, "content", "") or "").strip() == refined_response:
                return {
                    "final_response": refined_response,
                    "final_agent_response": refined_response,
                    "plan_complete": True,
                }
        return {
            "messages": [AIMessage(content=refined_response)],
            "final_response": refined_response,
            "final_agent_response": refined_response,
            "plan_complete": True,
        }

    def call_model(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        final_response = state.get("final_agent_response") or state.get("final_response")
        messages_state = state.get("messages") or []
        last_message = messages_state[-1] if messages_state else None
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        if (
            final_response
            and isinstance(last_message, ToolMessage)
            and not new_user_turn
        ):
            return {"messages": [AIMessage(content=_strip_critic_json(str(final_response)))]}
        if not incoming_turn_id and final_response and isinstance(last_message, HumanMessage):
            # Legacy fallback when turn_id is missing.
            new_user_turn = True
        messages = _sanitize_messages(list(state.get("messages") or []))
        plan_context = None if new_user_turn else _format_plan_context(state)
        recent_context = None if new_user_turn else _format_recent_calls(state)
        route_context = _format_route_hint(state)
        intent_context = None if new_user_turn else _format_intent_context(state)
        selected_agents_context = (
            None if new_user_turn else _format_selected_agents_context(state)
        )
        system_bits = [
            item
            for item in (
                plan_context,
                recent_context,
                route_context,
                intent_context,
                selected_agents_context,
            )
            if item
        ]
        if system_bits:
            messages = [SystemMessage(content="\n".join(system_bits))] + messages
        
        # Apply token budget
        model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None) or ""
        if model_name:
            budget = TokenBudget(model_name=str(model_name))
            messages = budget.fit_messages(messages)
        
        response = llm_with_tools.invoke(messages)
        response = _coerce_supervisor_tool_calls(
            response,
            orchestration_phase=str(state.get("orchestration_phase") or ""),
            agent_hops=int(state.get("agent_hops") or 0),
            allow_multiple=bool(compare_mode),
        )
        updates: SupervisorState = {"messages": [response]}
        if new_user_turn:
            # Start each user turn with fresh planner memory to avoid stale plan leakage.
            updates["resolved_intent"] = None
            updates["selected_agents"] = []
            updates["query_embedding"] = None
            updates["active_plan"] = []
            updates["plan_step_index"] = 0
            updates["plan_complete"] = False
            updates["step_results"] = []
            updates["recent_agent_calls"] = []
            updates["compare_outputs"] = []
            updates["final_agent_response"] = None
            updates["final_response"] = None
            updates["critic_decision"] = None
            updates["awaiting_confirmation"] = False
            updates["user_feedback"] = None
            updates["replan_count"] = 0
            updates["orchestration_phase"] = "select_agent"
            updates["agent_hops"] = 0
            updates["no_progress_runs"] = 0
            updates["guard_parallel_preview"] = []
            if incoming_turn_id:
                updates["active_turn_id"] = incoming_turn_id
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id
        if final_response and new_user_turn:
            updates["final_agent_response"] = None
            updates["final_response"] = None
        return updates

    async def acall_model(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        final_response = state.get("final_agent_response") or state.get("final_response")
        messages_state = state.get("messages") or []
        last_message = messages_state[-1] if messages_state else None
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        if (
            final_response
            and isinstance(last_message, ToolMessage)
            and not new_user_turn
        ):
            return {"messages": [AIMessage(content=_strip_critic_json(str(final_response)))]}
        if not incoming_turn_id and final_response and isinstance(last_message, HumanMessage):
            new_user_turn = True
        messages = _sanitize_messages(list(state.get("messages") or []))
        plan_context = None if new_user_turn else _format_plan_context(state)
        recent_context = None if new_user_turn else _format_recent_calls(state)
        route_context = _format_route_hint(state)
        intent_context = None if new_user_turn else _format_intent_context(state)
        selected_agents_context = (
            None if new_user_turn else _format_selected_agents_context(state)
        )
        system_bits = [
            item
            for item in (
                plan_context,
                recent_context,
                route_context,
                intent_context,
                selected_agents_context,
            )
            if item
        ]
        if system_bits:
            messages = [SystemMessage(content="\n".join(system_bits))] + messages
        
        # Apply token budget
        model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None) or ""
        if model_name:
            budget = TokenBudget(model_name=str(model_name))
            messages = budget.fit_messages(messages)
        
        response = await llm_with_tools.ainvoke(messages)
        response = _coerce_supervisor_tool_calls(
            response,
            orchestration_phase=str(state.get("orchestration_phase") or ""),
            agent_hops=int(state.get("agent_hops") or 0),
            allow_multiple=bool(compare_mode),
        )
        updates: SupervisorState = {"messages": [response]}
        if new_user_turn:
            # Start each user turn with fresh planner memory to avoid stale plan leakage.
            updates["resolved_intent"] = None
            updates["selected_agents"] = []
            updates["query_embedding"] = None
            updates["active_plan"] = []
            updates["plan_step_index"] = 0
            updates["plan_complete"] = False
            updates["step_results"] = []
            updates["recent_agent_calls"] = []
            updates["compare_outputs"] = []
            updates["final_agent_response"] = None
            updates["final_response"] = None
            updates["critic_decision"] = None
            updates["awaiting_confirmation"] = False
            updates["user_feedback"] = None
            updates["replan_count"] = 0
            updates["orchestration_phase"] = "select_agent"
            updates["agent_hops"] = 0
            updates["no_progress_runs"] = 0
            updates["guard_parallel_preview"] = []
            if incoming_turn_id:
                updates["active_turn_id"] = incoming_turn_id
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id
        if final_response and new_user_turn:
            updates["final_agent_response"] = None
            updates["final_response"] = None
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
        parallel_preview: list[str] = []
        plan_update: list[dict[str, Any]] | None = None
        plan_complete: bool | None = None
        last_call_payload: dict[str, Any] | None = None
        route_hint = _normalize_route_hint_value(state.get("route_hint"))
        latest_user_query = _latest_user_query(state.get("messages") or [])
        messages = list(state.get("messages") or [])
        tool_call_index = _tool_call_name_index(messages)

        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                break
            if not isinstance(message, ToolMessage):
                continue
            tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            if not tool_name:
                continue
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
                    payload_contract = _contract_from_payload(payload)
                    recent_updates.append(
                        {
                            "agent": payload.get("agent"),
                            "task": payload.get("task"),
                            "response": payload.get("response"),
                            "result_contract": payload_contract,
                        }
                    )
                    if payload.get("final") and payload.get("response"):
                        cleaned_response = _strip_critic_json(
                            str(payload.get("response") or "").strip()
                        )
                        if _should_finalize_from_contract(
                            contract=payload_contract,
                            response_text=cleaned_response,
                            route_hint=route_hint,
                            agent_name=str(payload.get("agent") or ""),
                            latest_user_query=latest_user_query,
                            agent_hops=int(state.get("agent_hops") or 0),
                        ):
                            updates["final_agent_response"] = cleaned_response
                            updates["final_response"] = cleaned_response
                            updates["final_agent_name"] = payload.get("agent")
                            updates["orchestration_phase"] = "finalize"
                    elif payload.get("response"):
                        cleaned_response = _strip_critic_json(
                            str(payload.get("response") or "").strip()
                        )
                        selected_agent = str(payload.get("agent") or "").strip().lower()
                        if _should_finalize_from_contract(
                            contract=payload_contract,
                            response_text=cleaned_response,
                            route_hint=route_hint,
                            agent_name=selected_agent,
                            latest_user_query=latest_user_query,
                            agent_hops=int(state.get("agent_hops") or 0),
                        ):
                            updates["final_agent_response"] = cleaned_response
                            updates["final_response"] = cleaned_response
                            updates["final_agent_name"] = payload.get("agent")
                            updates["orchestration_phase"] = "finalize"
            elif tool_name == "call_agents_parallel":
                parallel_results = payload.get("results")
                if isinstance(parallel_results, list):
                    for item in parallel_results:
                        if not isinstance(item, dict):
                            continue
                        agent_name = str(item.get("agent") or "").strip()
                        task_text = str(item.get("task") or "").strip()
                        response_text = _strip_critic_json(
                            str(item.get("response") or "").strip()
                        )
                        error_text = str(item.get("error") or "").strip()
                        compact_response = response_text or error_text
                        if compact_response:
                            recent_updates.append(
                                {
                                    "agent": agent_name or "agent",
                                    "task": task_text,
                                    "response": compact_response,
                                    "result_contract": _contract_from_payload(item),
                                }
                            )
                        if response_text and len(parallel_preview) < 3:
                            label = agent_name or "agent"
                            parallel_preview.append(
                                f"- {label}: {_truncate_for_prompt(response_text, 220)}"
                            )
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
            existing_steps = [
                item
                for item in (state.get("step_results") or [])
                if isinstance(item, dict)
            ]
            merged_steps = (existing_steps + recent_updates)[-12:]
            updates["step_results"] = merged_steps
            updates["plan_step_index"] = min(
                len(merged_steps),
                len(state.get("active_plan") or []),
            )
        if compare_updates:
            updates["compare_outputs"] = compare_updates
        updates["guard_parallel_preview"] = parallel_preview[:3]
        return updates

    async def orchestration_guard(
        state: SupervisorState,
        config: dict | None = None,
        *,
        store=None,
        **kwargs,
    ) -> SupervisorState:
        updates: dict[str, Any] = {}
        route_hint = str(state.get("route_hint") or "").strip().lower()
        latest_user_query = _latest_user_query(state.get("messages") or [])
        parallel_preview = list(state.get("guard_parallel_preview") or [])[:3]
        current_turn_id = str(
            state.get("active_turn_id") or state.get("turn_id") or ""
        ).strip()
        call_entries = _agent_call_entries_since_last_user(
            state.get("messages") or [],
            turn_id=current_turn_id or None,
        )
        if not parallel_preview and call_entries:
            for item in reversed(call_entries):
                response_text = _strip_critic_json(str(item.get("response") or "").strip())
                if not response_text:
                    continue
                agent_name = str(item.get("agent") or "agent").strip() or "agent"
                parallel_preview.append(
                    f"- {agent_name}: {_truncate_for_prompt(response_text, 220)}"
                )
                if len(parallel_preview) >= 3:
                    break
        messages = list(state.get("messages") or [])
        tool_call_index = _tool_call_name_index(messages)
        last_call_payload: dict[str, Any] | None = None
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                break
            if not isinstance(message, ToolMessage):
                continue
            tool_name = _resolve_tool_message_name(
                message,
                tool_call_index=tool_call_index,
            )
            if tool_name != "call_agent":
                continue
            payload = _safe_json(getattr(message, "content", ""))
            if payload:
                last_call_payload = payload
                break

        agent_hops = len(call_entries)
        updates["agent_hops"] = agent_hops
        updates["orchestration_phase"] = (
            "validate_agent_output" if agent_hops > 0 else "select_agent"
        )

        no_progress_runs = int(state.get("no_progress_runs") or 0)
        if call_entries:
            last_entry = call_entries[-1]
            last_agent = str(last_entry.get("agent") or "").strip().lower()
            last_task = _normalize_task_for_fingerprint(
                str(last_entry.get("task") or "")
            )
            last_fp = f"{last_agent}|{last_task}" if (last_agent or last_task) else ""
            if last_fp:
                fp_count = 0
                for entry in call_entries:
                    agent = str(entry.get("agent") or "").strip().lower()
                    task_fp = _normalize_task_for_fingerprint(
                        str(entry.get("task") or "")
                    )
                    if f"{agent}|{task_fp}" == last_fp:
                        fp_count += 1
                no_progress_runs = no_progress_runs + 1 if fp_count >= 2 else 0
            else:
                no_progress_runs = 0
        else:
            no_progress_runs = 0
        updates["no_progress_runs"] = no_progress_runs

        if "final_agent_response" not in updates and call_entries and route_hint != "compare":
            last_entry = call_entries[-1]
            last_response = _strip_critic_json(
                str(last_entry.get("response") or "").strip()
            )
            last_contract = _contract_from_payload(last_entry)
            if _should_finalize_from_contract(
                contract=last_contract,
                response_text=last_response,
                route_hint=route_hint,
                agent_name=str(last_entry.get("agent") or ""),
                latest_user_query=latest_user_query,
                agent_hops=agent_hops,
            ):
                updates["final_agent_response"] = last_response
                updates["final_response"] = last_response
                updates["final_agent_name"] = (
                    str(last_entry.get("agent") or "").strip() or "agent"
                )
                updates["orchestration_phase"] = "finalize"

        if (
            "final_agent_response" not in updates
            and no_progress_runs >= 2
        ):
            best = _best_actionable_entry(call_entries)
            if best:
                updates["final_agent_response"] = best[0]
                updates["final_response"] = best[0]
                updates["final_agent_name"] = best[1]
                updates["orchestration_phase"] = "finalize"
            else:
                rendered = _render_guard_message(loop_guard_template, parallel_preview)
                if not rendered:
                    rendered = _render_guard_message(
                        DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
                        parallel_preview,
                    )
                updates["final_agent_response"] = rendered
                updates["final_response"] = rendered
                updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
                updates["orchestration_phase"] = "finalize"

        if last_call_payload:
            last_contract = _contract_from_payload(last_call_payload)
            if (
                bool(last_contract.get("retry_recommended"))
                and "final_agent_response" not in updates
            ):
                updates["plan_complete"] = False

        # Fallback safety: avoid endless supervisor loops on repeated retrieval/delegation tools.
        if "final_agent_response" not in updates:
            loop_count = _count_consecutive_loop_tools(
                state.get("messages") or [],
                turn_id=current_turn_id or None,
            )
            if loop_count >= _LOOP_GUARD_MAX_CONSECUTIVE:
                rendered = _render_guard_message(loop_guard_template, parallel_preview)
                if not rendered:
                    rendered = _render_guard_message(
                        DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE,
                        parallel_preview,
                    )
                updates["final_agent_response"] = rendered
                updates["final_response"] = rendered
                updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
                updates["orchestration_phase"] = "finalize"

        if "final_agent_response" not in updates and agent_hops >= _MAX_AGENT_HOPS_PER_TURN:
            best = _best_actionable_entry(call_entries)
            if best:
                updates["final_agent_response"] = best[0]
                updates["final_response"] = best[0]
                updates["final_agent_name"] = best[1]
            else:
                rendered = _render_guard_message(
                    tool_limit_guard_template,
                    parallel_preview[:3],
                )
                if not rendered:
                    rendered = _render_guard_message(
                        DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
                        parallel_preview[:3],
                    )
                updates["final_agent_response"] = rendered
                updates["final_response"] = rendered
                updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
            updates["orchestration_phase"] = "finalize"

        # Hard guardrail: stop runaway tool loops within a single user turn.
        if "final_agent_response" not in updates:
            tool_calls_this_turn = _count_tools_since_last_user(
                state.get("messages") or []
            )
            if tool_calls_this_turn >= _MAX_TOOL_CALLS_PER_TURN:
                rendered = _render_guard_message(
                    tool_limit_guard_template,
                    parallel_preview[:3],
                )
                if not rendered:
                    rendered = _render_guard_message(
                        DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE,
                        parallel_preview[:3],
                    )
                updates["final_agent_response"] = rendered
                updates["final_response"] = rendered
                updates["final_agent_name"] = "supervisor"
                updates["plan_complete"] = True
                updates["orchestration_phase"] = "finalize"

        # Progressive message pruning when messages get long
        if len(messages) > MESSAGE_PRUNING_THRESHOLD:
            tool_msgs = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage)]
            if len(tool_msgs) > TOOL_MSG_THRESHOLD:
                keep_from = tool_msgs[-KEEP_TOOL_MSG_COUNT]
                keep_start = max(0, keep_from - 1)
                dropped_count = keep_start
                if dropped_count > 0:
                    pruned = messages[keep_start:]
                    summary_msg = SystemMessage(
                        content=f"[{dropped_count} earlier messages (including tool calls) condensed. Recent context retained.]"
                    )
                    leading_system = [m for m in messages[:keep_start] if isinstance(m, SystemMessage)]
                    updates["messages"] = leading_system + [summary_msg] + pruned

        updates["guard_parallel_preview"] = []
        return updates

    def should_continue(state: SupervisorState, *, store=None):
        messages = state.get("messages") or []
        if not messages:
            return "critic"
        last_message = messages[-1]
        if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
            return "tools"
        return "critic"

    def critic_should_continue(state: SupervisorState, *, store=None):
        decision = str(state.get("critic_decision") or "").strip().lower()
        final_response = str(
            state.get("final_response") or state.get("final_agent_response") or ""
        ).strip()
        replan_count = int(state.get("replan_count") or 0)
        if final_response and decision in {"ok", "pass", "finalize"}:
            return "synthesizer"
        if decision == "needs_more" and replan_count < _MAX_REPLAN_ATTEMPTS:
            return "agent_resolver"
        if final_response:
            return "synthesizer"
        return "agent_resolver"

    graph_builder = StateGraph(SupervisorState)
    graph_builder.add_node("resolve_intent", RunnableCallable(None, resolve_intent_node))
    graph_builder.add_node("agent_resolver", RunnableCallable(None, resolve_agents_node))
    graph_builder.add_node("planner", RunnableCallable(None, planner_node))
    graph_builder.add_node("agent", RunnableCallable(call_model, acall_model))
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("post_tools", RunnableCallable(None, post_tools))
    graph_builder.add_node(
        "orchestration_guard",
        RunnableCallable(None, orchestration_guard),
    )
    graph_builder.add_node("critic", RunnableCallable(None, critic_node))
    graph_builder.add_node("synthesizer", RunnableCallable(None, synthesizer_node))
    graph_builder.set_entry_point("resolve_intent")
    graph_builder.add_edge("resolve_intent", "agent_resolver")
    graph_builder.add_edge("agent_resolver", "planner")
    graph_builder.add_edge("planner", "agent")
    graph_builder.add_conditional_edges("agent", should_continue, path_map=["tools", "critic"])
    graph_builder.add_edge("tools", "post_tools")
    graph_builder.add_edge("post_tools", "orchestration_guard")
    graph_builder.add_edge("orchestration_guard", "critic")
    graph_builder.add_conditional_edges(
        "critic",
        critic_should_continue,
        path_map=["synthesizer", "agent_resolver"],
    )
    graph_builder.add_edge("synthesizer", END)

    return graph_builder.compile(checkpointer=checkpointer, name="supervisor-agent")
