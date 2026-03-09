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


_registry_route_defaults: dict[str, str] | None = None


def set_registry_route_defaults(defaults: dict[str, str]) -> None:
    """Install registry-built route defaults (called after registry load)."""
    global _registry_route_defaults
    _registry_route_defaults = defaults


def _route_default_agent(
    route_hint: str | None, allowed: set[str] | None = None
) -> str:
    route = _normalize_route_hint_value(route_hint)
    # Use registry-built defaults when available, otherwise fall back to
    # minimal static defaults for the 4 broad routes.
    defaults = _registry_route_defaults or {
        "skapande": "åtgärd",
        "jämförelse": "syntes",
        "konversation": "konversation",
        "action": "åtgärd",
        "compare": "syntes",
        "smalltalk": "konversation",
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


def _score_tool_profile(
    profile: AgentToolProfile, query_norm: str, tokens: set[str]
) -> int:
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


_registry_tool_profiles: dict[str, list[AgentToolProfile]] | None = None


def set_registry_tool_profiles(
    profiles: dict[str, list[AgentToolProfile]],
) -> None:
    """Install registry-built tool profiles (called after registry load)."""
    global _registry_tool_profiles
    _registry_tool_profiles = profiles


def _select_focused_tool_profiles(
    agent_name: str,
    task: str,
    *,
    limit: int = 4,
) -> list[AgentToolProfile]:
    tool_profiles = _registry_tool_profiles if _registry_tool_profiles is not None else _AGENT_TOOL_PROFILES
    profiles = list(tool_profiles.get(str(agent_name or "").strip().lower(), []))
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


def _focused_tool_ids_for_agent(
    agent_name: str, task: str, *, limit: int = 5
) -> list[str]:
    normalized_task = _normalize_text(task)
    normalized_agent_name = str(agent_name or "").strip().lower()
    # Check if this agent has tool profiles — if not, allow dynamic discovery
    tool_profiles = _registry_tool_profiles if _registry_tool_profiles is not None else _AGENT_TOOL_PROFILES
    has_profiles = bool(tool_profiles.get(normalized_agent_name))
    if not has_profiles and any(
        marker in normalized_task for marker in _DYNAMIC_TOOL_QUERY_MARKERS
    ):
        # Allow retrieve_tools to discover dynamic connector tools (for example MCP)
        # instead of locking the worker to static profile IDs.
        return []
    focused = _select_focused_tool_profiles(agent_name, task, limit=limit)
    return [profile.tool_id for profile in focused if profile.tool_id]


_registry_alias_map: dict[str, str] | None = None
_registry_token_rules: list[tuple[tuple[str, ...], str]] | None = None


def set_registry_alias_map(alias_map: dict[str, str]) -> None:
    """Install registry-built alias map (called after registry load)."""
    global _registry_alias_map
    _registry_alias_map = alias_map


def set_registry_token_rules(
    rules: list[tuple[tuple[str, ...], str]],
) -> None:
    """Install registry-built token rules (called after registry load)."""
    global _registry_token_rules
    _registry_token_rules = rules


# Agent aliasing
def _normalize_agent_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9åäö]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _guess_agent_from_alias(alias: str) -> str | None:
    normalized = _normalize_agent_identifier(alias)
    if not normalized:
        return None
    # Try registry-built alias map first, then static fallback
    alias_map = _registry_alias_map if _registry_alias_map is not None else _AGENT_NAME_ALIAS_MAP
    direct = alias_map.get(normalized)
    if direct:
        return direct
    # Try registry-built token rules first, then static fallback
    token_rules = _registry_token_rules if _registry_token_rules is not None else _STATIC_TOKEN_RULES
    for tokens, resolved in token_rules:
        if any(token in normalized for token in tokens):
            return resolved
    return None


# Static fallback token rules (used when no registry is loaded)
_STATIC_TOKEN_RULES: list[tuple[tuple[str, ...], str]] = [
    (("smhi", "weather", "vader", "temperatur", "regn", "sno", "vind"), "väder"),
    (("trafik", "traffic", "road", "vag"), "trafik-vag"),
    (("rail", "train", "tag"), "trafik-tag"),
    (("map", "kart", "geo"), "kartor"),
    (("stat", "scb", "data"), "statistik-ekonomi"),
    (("riks", "parliament", "politik"), "riksdagen-dokument"),
    (("bolag", "company", "business"), "bolag"),
    (("blocket", "tradera", "annons", "begagnat", "marknadsplats"), "marknad"),
    (("browser", "web", "scrape"), "webb"),
    (("media", "podcast", "image"), "media"),
    (("code", "python", "calc", "kod"), "kod"),
    (("synth", "compare", "samman", "syntes"), "syntes"),
    (("knowledge", "docs", "kunskap"), "kunskap"),
    (("action", "travel"), "åtgärd"),
]


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
                        agent_id = str(agent.get("agent_id") or "").strip().lower()
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
