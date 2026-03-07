"""Intent detection, routing, and agent aliasing functions for supervisor agent."""
from __future__ import annotations

import re
from typing import Any

from app.agents.new_chat.bigtool_store import _normalize_text
from app.agents.new_chat.supervisor_constants import (
    _AGENT_NAME_ALIAS_MAP,
    _AGENT_STOPWORDS,
    _AGENT_TOOL_PROFILES,
    _ALTERNATIVE_RESPONSE_MARKERS,
    _DYNAMIC_TOOL_QUERY_MARKERS,
    _FILESYSTEM_INTENT_RE,
    _MAP_INTENT_RE,
    _MARKETPLACE_INTENT_RE,
    _ROUTE_STRICT_AGENT_POLICIES,
    _TRAFFIC_INCIDENT_STRICT_RE,
    _TRAFFIC_INTENT_RE,
    _TRAFFIC_STRICT_INTENT_RE,
    _UNAVAILABLE_RESPONSE_MARKERS,
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
    # Minimal defaults for the 4 broad routes + backward compat aliases.
    # Domain-specific agent selection is handled by the registry-aware
    # ``resolve_default_agent_with_registry()`` — this function is only
    # the final fallback when no registry is available.
    defaults = {
        "skapande": "åtgärd",
        "jämförelse": "syntes",
        "konversation": "konversation",
        # Backward compat
        "action": "åtgärd",
        "compare": "syntes",
        "smalltalk": "konversation",
        # Domain-specific routes that already have a matching agent name
        "trafik": "trafik",
        "statistik": "statistik",
        "väder": "väder",
        "marknad": "marknad",
        "bolag": "bolag",
        "riksdagen": "riksdagen",
        "kartor": "kartor",
        "media": "media",
        "kod": "kod",
        "webb": "webb",
    }
    # If the route/domain itself is a valid agent name, use it directly
    preferred = defaults.get(route, route if route else "kunskap")
    if allowed:
        if preferred in allowed:
            return preferred
        for name in allowed:
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
    if normalized_agent_name in {"kunskap", "statistik", "åtgärd", "knowledge", "statistics", "action"} and any(
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
        (("smhi", "weather", "vader", "väder", "temperatur", "regn", "sno", "snö", "vind"), "väder"),
        (("trafik", "traffic", "road", "vag", "väg", "rail", "train"), "trafik"),
        (("map", "kart", "geo"), "kartor"),
        (("stat", "scb", "data"), "statistik"),
        (("riks", "parliament", "politik"), "riksdagen"),
        (("bolag", "company", "business", "org"), "bolag"),
        (("blocket", "tradera", "annons", "begagnat", "köp", "sälj", "marknadsplats"), "marknad"),
        (("browser", "web", "scrape", "search"), "webb"),
        (("media", "podcast", "image", "video"), "media"),
        (("code", "python", "calc", "kod"), "kod"),
        (("synth", "compare", "samman", "syntes"), "syntes"),
        (("knowledge", "docs", "internal", "external", "local", "kunskap"), "kunskap"),
        (("action", "travel", "åtgärd"), "åtgärd"),
    ]
    for tokens, resolved in token_rules:
        if any(token in normalized for token in tokens):
            return resolved
    return None


# ── Registry-aware agent + tool resolution ────────────────────────────

def resolve_default_agent_with_registry(
    route_hint: str | None,
    query: str,
    registry: Any | None,
) -> str:
    """Pick the best agent for a route, using registry if available.

    Falls back to the legacy ``_route_default_agent`` when no registry
    is provided or the domain has no agents.
    """
    if registry is not None:
        try:
            from app.agents.new_chat.routing import Route, route_to_domains
            from app.services.agent_resolver_service import (
                resolve_default_agent_for_domain,
            )

            route_value = _normalize_route_hint_value(route_hint)
            try:
                route_enum = Route(route_value)
            except (ValueError, KeyError):
                route_enum = None
            if route_enum is not None:
                domain_ids = route_to_domains(route_enum)
                for domain_id in domain_ids:
                    agent_id = resolve_default_agent_for_domain(
                        query=query,
                        domain_id=domain_id,
                        registry=registry,
                    )
                    if agent_id:
                        return agent_id
        except Exception:
            pass
    allowed = _route_allowed_agents(route_hint)
    return _route_default_agent(route_hint, allowed)


def resolve_allowed_agents_with_registry(
    route_hint: str | None,
    registry: Any | None,
) -> set[str]:
    """Return allowed agent IDs for a route, using registry if available.

    Falls back to ``_route_allowed_agents`` when no registry is available.
    """
    if registry is not None:
        try:
            from app.agents.new_chat.routing import Route, route_to_domains

            route_value = _normalize_route_hint_value(route_hint)
            try:
                route_enum = Route(route_value)
            except (ValueError, KeyError):
                route_enum = None
            if route_enum is not None:
                domain_ids = route_to_domains(route_enum)
                agent_ids: set[str] = set()
                for domain_id in domain_ids:
                    agents = list(
                        (registry.agents_by_domain or {}).get(domain_id) or []
                    )
                    for agent in agents:
                        agent_id = str(
                            agent.get("agent_id") or ""
                        ).strip().lower()
                        if agent_id and agent.get("enabled", True):
                            agent_ids.add(agent_id)
                if agent_ids:
                    return agent_ids
        except Exception:
            pass
    return _route_allowed_agents(route_hint)


def resolve_focused_tool_ids_with_registry(
    agent_id: str,
    query: str,
    registry: Any | None,
    *,
    limit: int = 5,
) -> list[str]:
    """Return focused tool IDs for an agent, using registry if available.

    Falls back to ``_focused_tool_ids_for_agent`` when no registry is
    available.
    """
    if registry is not None:
        try:
            from app.services.tool_resolver_service import (
                resolve_tool_ids_for_agent,
            )

            tool_ids = resolve_tool_ids_for_agent(
                query=query,
                agent_id=agent_id,
                registry=registry,
                top_k=limit,
            )
            if tool_ids:
                return tool_ids
        except Exception:
            pass
    return _focused_tool_ids_for_agent(agent_id, query, limit=limit)
