"""Zone Manager — embedding zone architecture.

Manages the 4 embedding zones: [KUNSK], [MYNDG], [HANDL], [JAMFR].
Handles zone-prefix embeddings, namespace→zone mapping, and zone
health monitoring.
"""

from __future__ import annotations

import logging

from app.nexus.config import NAMESPACE_ZONE_MAP, ZONE_PREFIXES, Zone

logger = logging.getLogger(__name__)


class ZoneManager:
    """Manages the 4-zone embedding architecture.

    Zone architecture:
        [KUNSK]  — Knowledge: search, web, docs, marketplace
        [MYNDG]  — Government: SMHI, SCB, Trafikverket, Riksdagen, Skolverket
        [HANDL]  — Actions: sandbox, podcast, image generation
        [JAMFR]  — Comparison: multi-model calls (GPT, Claude, Grok)

    Zone-prefix embeddings improve inter-zone distance by +12-18%
    without fine-tuning the underlying embedding model.
    """

    def __init__(self):
        self.zones = list(Zone)
        self.prefixes = ZONE_PREFIXES
        self.namespace_map = NAMESPACE_ZONE_MAP

    def resolve_zone_from_namespace(self, namespace: str | tuple[str, ...]) -> Zone | None:
        """Map a namespace (or namespace tuple) to a zone.

        Args:
            namespace: Namespace string or tuple (e.g., "tools/weather/smhi"
                       or ("tools", "weather", "smhi")).

        Returns:
            The resolved Zone, or None if no match.
        """
        if isinstance(namespace, (list, tuple)):
            ns_str = "/".join(namespace)
        else:
            ns_str = namespace

        # Try progressively shorter prefixes
        parts = ns_str.split("/")
        for i in range(len(parts), 0, -1):
            prefix = "/".join(parts[:i])
            if prefix in self.namespace_map:
                return self.namespace_map[prefix]

        return None

    def get_zone_prefix(self, zone: Zone | str) -> str:
        """Get the prefix token for a zone.

        Args:
            zone: Zone enum or string name.

        Returns:
            Prefix string (e.g., "[KUNSK] ").
        """
        zone_key = Zone(zone) if isinstance(zone, str) else zone
        return self.prefixes.get(zone_key, "")

    def prefix_text_for_zone(self, text: str, zone: Zone | str) -> str:
        """Prepend zone prefix to text for embedding.

        Args:
            text: Text to prefix (e.g., tool description or query).
            zone: Target zone.

        Returns:
            Prefixed text (e.g., "[MYNDG] Väderprognos för...").
        """
        prefix = self.get_zone_prefix(zone)
        return f"{prefix}{text}"

    def prefix_query_with_hint(self, query: str, zone_hint: str | None) -> str:
        """Prefix a query with a zone hint if available.

        If no hint is provided, return the query unmodified for
        broad search across all zones.

        Args:
            query: The user query.
            zone_hint: Optional zone name to narrow the search.

        Returns:
            Query string, possibly with zone prefix.
        """
        if zone_hint and zone_hint in [z.value for z in Zone]:
            return self.prefix_text_for_zone(query, zone_hint)
        return query

    def get_zone_config_data(self) -> list[dict]:
        """Return zone configuration for seeding or API responses."""
        return [
            {
                "zone": zone.value,
                "prefix_token": self.prefixes[zone],
            }
            for zone in self.zones
        ]

    def get_all_zone_names(self) -> list[str]:
        """Return all zone names."""
        return [z.value for z in self.zones]
