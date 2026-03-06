"""Agent Resolver — selects candidate agents after intent/zone resolution.

Given a zone (domain/intent) and a query, scores and ranks agents using
keyword matching and domain hint overlap.  No LLM calls — pure heuristic
(<2 ms).

Flow position:  QUL (intent/zone) → **AgentResolver** → StR (tool retrieval)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.nexus.config import (
    AGENT_BY_NAME,
    AGENTS_BY_ZONE,
    DOMAIN_HINTS,
    NexusAgent,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentCandidate:
    """A scored agent candidate."""

    agent: NexusAgent
    score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class AgentResolutionResult:
    """Result of agent resolution for a single query."""

    candidates: list[AgentCandidate] = field(default_factory=list)
    selected_agents: list[str] = field(default_factory=list)
    zone: str = ""

    @property
    def top_agent(self) -> str | None:
        return self.selected_agents[0] if self.selected_agents else None

    def get_tool_namespaces(
        self, agent_by_name: dict[str, NexusAgent] | None = None
    ) -> list[str]:
        """Collect all primary_namespaces from selected agents.

        Args:
            agent_by_name: Dynamic agent lookup (from DB). Falls back to static config.
        """
        _agent_by_name = agent_by_name if agent_by_name is not None else AGENT_BY_NAME
        ns: list[str] = []
        for name in self.selected_agents:
            agent = _agent_by_name.get(name)
            if agent:
                ns.extend(agent.primary_namespaces)
        return ns

    @property
    def tool_namespaces(self) -> list[str]:
        """Collect all primary_namespaces from selected agents (static fallback)."""
        return self.get_tool_namespaces()


class AgentResolver:
    """Selects candidate agents based on zone + query keyword matching.

    Scoring strategy (per agent):
      +1.0  base score if zone matches
      +0.3  per keyword match in query
      +0.5  bonus if agent name matches a category hint from QUL
      +0.2  bonus for organization entity match (e.g. "SMHI" → väder)
    """

    def resolve(
        self,
        query: str,
        zone_candidates: list[str],
        *,
        domain_hints: list[str] | None = None,
        organizations: list[str] | None = None,
        max_agents: int = 3,
        agent_by_name: dict[str, NexusAgent] | None = None,
        agents_by_zone: dict[str, list[NexusAgent]] | None = None,
    ) -> AgentResolutionResult:
        """Score and select agents for the query.

        Args:
            query: Normalized user query.
            zone_candidates: Zones (domain_ids) identified by QUL.
            domain_hints: Domain keywords from QUL (zones + category hints).
            organizations: Organization entities from QUL.
            max_agents: Maximum number of agents to select.
            agent_by_name: Dynamic agent lookup (from DB). Falls back to static config.
            agents_by_zone: Dynamic zone-agent lookup (from DB). Falls back to static config.

        Returns:
            AgentResolutionResult with ranked candidates and selected agents.
        """
        # Use provided dynamic lookups, or fall back to static config
        _agents_by_zone = agents_by_zone if agents_by_zone is not None else AGENTS_BY_ZONE

        lower_query = query.lower()
        scored: list[AgentCandidate] = []

        # Build valid zone set from available domain hints + agents_by_zone keys
        zone_values = set(DOMAIN_HINTS.keys())
        zone_values.update(_agents_by_zone.keys())

        # Separate zone names from category hints in domain_hints
        category_hints = set()
        if domain_hints:
            category_hints = {h for h in domain_hints if h not in zone_values}

        # Collect agents from candidate zones (using string keys)
        candidate_agents: list[NexusAgent] = []
        for zone_name in zone_candidates:
            candidate_agents.extend(_agents_by_zone.get(zone_name, []))

        # Deduplicate
        seen_names: set[str] = set()
        unique_agents: list[NexusAgent] = []
        for a in candidate_agents:
            if a.name not in seen_names:
                seen_names.add(a.name)
                unique_agents.append(a)

        # Score each agent
        for agent in unique_agents:
            score = 1.0  # Base score for zone match
            matched_kw: list[str] = []

            # Category hint bonus — strongly boosts the right agent
            if agent.name in category_hints:
                score += 1.5
                matched_kw.append(f"category:{agent.name}")

            # Keyword matching
            for kw in agent.keywords:
                if re.search(rf"\b{re.escape(kw)}\b", lower_query):
                    score += 0.3
                    matched_kw.append(kw)

            # Organization entity bonus
            if organizations:
                org_lower = [o.lower() for o in organizations]
                for kw in agent.keywords:
                    if kw.lower() in org_lower:
                        score += 0.2

            scored.append(
                AgentCandidate(
                    agent=agent,
                    score=score,
                    matched_keywords=matched_kw,
                    reason=f"zone={agent.zone}, kw_matches={len(matched_kw)}",
                )
            )

        # Sort by score descending
        scored.sort(key=lambda c: c.score, reverse=True)

        # Select top agents (those above threshold or top max_agents)
        # Threshold: must have at least 1 keyword match (score > 1.0)
        # unless only 1 candidate
        selected: list[str] = []
        for c in scored[:max_agents]:
            if c.score > 1.0 or len(scored) <= max_agents:
                selected.append(c.agent.name)

        # Always select at least 1 if we have candidates
        if not selected and scored:
            selected = [scored[0].agent.name]

        primary_zone = zone_candidates[0] if zone_candidates else ""

        return AgentResolutionResult(
            candidates=scored,
            selected_agents=selected,
            zone=primary_zone,
        )
