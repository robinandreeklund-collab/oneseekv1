"""Intent detection, routing, and agent aliasing functions for supervisor agent."""
from __future__ import annotations

import re
from typing import Any

from app.agents.new_chat.bigtool_store import _normalize_text
from app.agents.new_chat.supervisor_constants import (
    _AGENT_NAME_ALIAS_MAP,
    _AGENT_STOPWORDS,
    _AGENT_TOOL_PROFILES,
    _DYNAMIC_TOOL_QUERY_MARKERS,
    _FILESYSTEM_INTENT_RE,
    _MAP_INTENT_RE,
    _MARKETPLACE_INTENT_RE,
    _ROUTE_STRICT_AGENT_POLICIES,
    _TRAFFIC_INCIDENT_STRICT_RE,
    _TRAFFIC_INTENT_RE,
    _TRAFFIC_STRICT_INTENT_RE,
    _UNAVAILABLE_RESPONSE_MARKERS,
    _ALTERNATIVE_RESPONSE_MARKERS,
    _WEATHER_INTENT_RE,
    AgentToolProfile,
)


# Intent detection functions
def _has_trafik_intent(text: str) -> bool:
    return bool(text and _TRAFFIC_INTENT_RE.search(text))


def _has_map_intent(text: str) -> bool:
    return bool(text and _MAP_INTENT_RE.search(text))


def _has_marketplace_intent(text: str) -> bool:
    return bool(text and _MARKETPLACE_INTENT_RE.search(text))


def _has_filesystem_intent(text: str) -> bool:
    return bool(text and _FILESYSTEM_INTENT_RE.search(text))


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
    if normalized.startswith("smhi_"):
        return True
    if normalized.startswith("trafikverket_vader_"):
        return True
    return False


# Route functions
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
        "mixed": "knowledge",
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


# Text tokenization and scoring
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
    normalized_task = _normalize_text(task)
    normalized_agent_name = str(agent_name or "").strip().lower()
    if normalized_agent_name in {"knowledge", "statistics", "action"} and any(
        marker in normalized_task for marker in _DYNAMIC_TOOL_QUERY_MARKERS
    ):
        # Allow retrieve_tools to discover dynamic connector tools (for example MCP)
        # instead of locking the worker to static profile IDs.
        return []
    focused = _select_focused_tool_profiles(agent_name, task, limit=limit)
    return [profile.tool_id for profile in focused if profile.tool_id]


# Agent aliasing
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
        (("blocket", "tradera", "annons", "begagnat", "köp", "sälj", "marknadsplats"), "marketplace"),
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
