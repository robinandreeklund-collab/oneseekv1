"""Schema Verifier — post-selection parameter validation.

Verifies that a selected tool's required parameters, geographic scope,
and temporal scope match what the query provides. This catches misroutes
where the tool match looks correct but the query lacks necessary context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolSchema:
    """Expected schema for a tool."""

    tool_id: str
    required_params: list[str] = field(default_factory=list)
    geographic_scope: str = ""  # e.g., "sweden", "global", "nordic"
    temporal_scope: str = ""  # e.g., "realtime", "historical", "forecast"
    min_entities: int = 0  # minimum required entities in query


@dataclass
class VerificationResult:
    """Result of schema verification."""

    verified: bool
    tool_id: str
    missing_params: list[str] = field(default_factory=list)
    scope_mismatch: str = ""
    confidence_penalty: float = 0.0


# Built-in tool schemas — extended as tools are added
TOOL_SCHEMAS: dict[str, ToolSchema] = {
    # Weather tools need location
    "smhi_weather": ToolSchema(
        tool_id="smhi_weather",
        required_params=["location"],
        geographic_scope="sweden",
        temporal_scope="forecast",
    ),
    "smhi_vaderprognoser_metfcst": ToolSchema(
        tool_id="smhi_vaderprognoser_metfcst",
        required_params=["location"],
        geographic_scope="sweden",
        temporal_scope="forecast",
    ),
    "smhi_vaderobservationer_metobs": ToolSchema(
        tool_id="smhi_vaderobservationer_metobs",
        required_params=["location"],
        geographic_scope="sweden",
        temporal_scope="historical",
    ),
    "smhi_brandrisk_fwif": ToolSchema(
        tool_id="smhi_brandrisk_fwif",
        geographic_scope="sweden",
        temporal_scope="forecast",
    ),
    # SCB tools need municipality or data category
    "scb_befolkning": ToolSchema(
        tool_id="scb_befolkning",
        geographic_scope="sweden",
    ),
    # Kolada tools need municipality
    "kolada_aldreomsorg": ToolSchema(
        tool_id="kolada_aldreomsorg",
        required_params=["municipality"],
        geographic_scope="sweden",
    ),
    # Riksdagen — no geographic requirement but temporal
    "riksdag_dokument": ToolSchema(
        tool_id="riksdag_dokument",
        geographic_scope="sweden",
    ),
    "riksdag_voteringar": ToolSchema(
        tool_id="riksdag_voteringar",
        geographic_scope="sweden",
    ),
    # External model calls — no constraints
    "call_gpt": ToolSchema(tool_id="call_gpt"),
    "call_claude": ToolSchema(tool_id="call_claude"),
    "call_grok": ToolSchema(tool_id="call_grok"),
    # Knowledge tools
    "search_knowledge_base": ToolSchema(tool_id="search_knowledge_base"),
    "search_tavily": ToolSchema(tool_id="search_tavily"),
    # Trafiklab
    "trafiklab_route": ToolSchema(
        tool_id="trafiklab_route",
        required_params=["origin", "destination"],
        geographic_scope="sweden",
    ),
}

# Geographic scope keywords
_SWEDEN_INDICATORS = frozenset({
    "sverige", "swedish", "svensk", "stockholm", "göteborg", "malmö",
    "kommun", "län", "region",
})

_GLOBAL_INDICATORS = frozenset({
    "global", "world", "international", "internationell",
})


class SchemaVerifier:
    """Verifies that a selected tool's schema matches the query context."""

    def __init__(self, schemas: dict[str, ToolSchema] | None = None):
        self.schemas = schemas or TOOL_SCHEMAS

    def verify(
        self,
        tool_id: str,
        *,
        query: str = "",
        entities_locations: list[str] | None = None,
        entities_times: list[str] | None = None,
        entities_organizations: list[str] | None = None,
    ) -> VerificationResult:
        """Verify that the query satisfies the tool's schema.

        Args:
            tool_id: The tool to verify against.
            query: The original query text.
            entities_locations: Extracted location entities.
            entities_times: Extracted time entities.
            entities_organizations: Extracted organization entities.

        Returns:
            VerificationResult with pass/fail and details.
        """
        schema = self.schemas.get(tool_id)
        if not schema:
            # No schema defined — pass by default
            return VerificationResult(verified=True, tool_id=tool_id)

        missing_params: list[str] = []
        penalty = 0.0
        scope_mismatch = ""

        locations = entities_locations or []
        times = entities_times or []

        # Check required parameters
        for param in schema.required_params:
            if (param in ("location", "municipality") and not locations) or (param in ("origin", "destination") and len(locations) < 2):
                missing_params.append(param)
                penalty += 0.10

        # Check geographic scope
        if schema.geographic_scope == "sweden":
            lower = query.lower()
            has_foreign = any(
                kw in lower
                for kw in ("utomlands", "utanför sverige", "europa", "usa", "medelhavet")
            )
            if has_foreign:
                scope_mismatch = "foreign_query_for_sweden_tool"
                penalty += 0.15

        # Check temporal scope
        if schema.temporal_scope == "forecast" and times:
            # If query mentions historical dates, penalize
            lower = query.lower()
            if any(kw in lower for kw in ("förra", "igår", "historisk", "1990", "1980")):
                scope_mismatch = scope_mismatch or "historical_query_for_forecast_tool"
                penalty += 0.10

        elif schema.temporal_scope == "historical" and times:
            lower = query.lower()
            if any(kw in lower for kw in ("imorgon", "nästa", "kommande")):
                scope_mismatch = scope_mismatch or "future_query_for_historical_tool"
                penalty += 0.10

        verified = not missing_params and not scope_mismatch
        return VerificationResult(
            verified=verified,
            tool_id=tool_id,
            missing_params=missing_params,
            scope_mismatch=scope_mismatch,
            confidence_penalty=penalty,
        )

    def verify_top_candidates(
        self,
        candidates: list[dict],
        *,
        query: str = "",
        entities_locations: list[str] | None = None,
        entities_times: list[str] | None = None,
        entities_organizations: list[str] | None = None,
    ) -> list[VerificationResult]:
        """Verify multiple candidates, returning results for each."""
        return [
            self.verify(
                c.get("tool_id", ""),
                query=query,
                entities_locations=entities_locations,
                entities_times=entities_times,
                entities_organizations=entities_organizations,
            )
            for c in candidates
        ]
