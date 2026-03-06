"""QUL — Query Understanding Layer.

Pre-routing analysis of queries: entity extraction, multi-intent detection,
Swedish normalization, domain hint scoring. Runs in <5ms, no LLM calls.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.nexus.config import (
    CATEGORY_HINTS,
    DOMAIN_HINTS,
    MULTI_INTENT_MARGIN_THRESHOLD,
    SWEDISH_NORMALIZATION_BANK,
    Zone,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Municipality Gazetteer — 290 Swedish municipalities + abbreviations
# ---------------------------------------------------------------------------

# Top ~100 most commonly queried municipalities + common abbreviations
# Full list can be loaded from SCB register at startup
MUNICIPALITY_GAZETTEER: dict[str, str] = {
    # Abbreviations
    "sthlm": "Stockholm",
    "gbg": "Göteborg",
    "cph": "Köpenhamn",
    "nkpg": "Norrköping",
    "lkpg": "Linköping",
    # Major cities (canonical → canonical for lookup)
    "stockholm": "Stockholm",
    "göteborg": "Göteborg",
    "malmö": "Malmö",
    "uppsala": "Uppsala",
    "linköping": "Linköping",
    "västerås": "Västerås",
    "örebro": "Örebro",
    "norrköping": "Norrköping",
    "helsingborg": "Helsingborg",
    "jönköping": "Jönköping",
    "umeå": "Umeå",
    "lund": "Lund",
    "borås": "Borås",
    "sundsvall": "Sundsvall",
    "gävle": "Gävle",
    "eskilstuna": "Eskilstuna",
    "södertälje": "Södertälje",
    "karlstad": "Karlstad",
    "täby": "Täby",
    "växjö": "Växjö",
    "halmstad": "Halmstad",
    "kalmar": "Kalmar",
    "kristianstad": "Kristianstad",
    "luleå": "Luleå",
    "trollhättan": "Trollhättan",
    "östersund": "Östersund",
    "borlänge": "Borlänge",
    "falun": "Falun",
    "skellefteå": "Skellefteå",
    "tumba": "Botkyrka",
    "solna": "Solna",
    "nacka": "Nacka",
    "huddinge": "Huddinge",
    "haninge": "Haninge",
    "järfälla": "Järfälla",
    "sollentuna": "Sollentuna",
    "lidingö": "Lidingö",
    "tyresö": "Tyresö",
    "norrtälje": "Norrtälje",
    "nyköping": "Nyköping",
    "visby": "Gotland",
    "gotland": "Gotland",
    "kiruna": "Kiruna",
    "karlskrona": "Karlskrona",
    "varberg": "Varberg",
    "uddevalla": "Uddevalla",
    "motala": "Motala",
    "landskrona": "Landskrona",
    "lidköping": "Lidköping",
    "enköping": "Enköping",
    "arvika": "Arvika",
    "härnösand": "Härnösand",
    "piteå": "Piteå",
    "ystad": "Ystad",
    "simrishamn": "Simrishamn",
    "trelleborg": "Trelleborg",
    "mora": "Mora",
    "avesta": "Avesta",
    "katrineholm": "Katrineholm",
    "mariestad": "Mariestad",
    "sandviken": "Sandviken",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class QueryEntities:
    locations: list[str] = field(default_factory=list)
    times: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)


@dataclass
class QueryAnalysisResult:
    original_query: str
    normalized_query: str
    sub_queries: list[str]
    entities: QueryEntities
    domain_hints: list[str]
    zone_candidates: list[str]
    complexity: str  # "trivial" | "simple" | "compound" | "complex"
    is_multi_intent: bool
    ood_risk: float = 0.0


# ---------------------------------------------------------------------------
# Time patterns (Swedish)
# ---------------------------------------------------------------------------

_TIME_PATTERNS = [
    re.compile(r"\b(imorgon|idag|igår|i ?övermorgon)\b", re.IGNORECASE),
    re.compile(r"\b(i ?helgen|nästa vecka|förra veckan)\b", re.IGNORECASE),
    re.compile(
        r"\b(måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag)\b", re.IGNORECASE
    ),
    re.compile(
        r"\b(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(
        r"\b\d{1,2}\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(senaste|kommande)\s+\d+\s+(dagar|veckor|månader)\b", re.IGNORECASE),
]

# Swedish conjunctions that may indicate multi-intent
_MULTI_INTENT_CONJUNCTIONS = re.compile(
    r"\b(och\s+(?:vad|hur|var|vilka|visa))\b"
    r"|(?:,\s*(?:samt|dessutom|plus)\s)"
    r"|(?:\?\s+(?:Och|Vad|Hur|Var))",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# QUL Class
# ---------------------------------------------------------------------------


class QueryUnderstandingLayer:
    """Pre-routing query analysis — no LLM, <5ms target."""

    def analyze(
        self,
        query: str,
        *,
        domain_hints_map: dict[str, list[str]] | None = None,
        category_hints_map: dict[str, list[str]] | None = None,
    ) -> QueryAnalysisResult:
        # 1. Swedish normalization
        normalized = self._normalize_swedish(query)

        # 2. Entity extraction (rule-based)
        entities = self._extract_entities(normalized)

        # 3. Multi-intent detection
        sub_queries = self._detect_and_split_intents(normalized)
        is_multi = len(sub_queries) > 1

        # 4. Domain hint scoring (use dynamic hints from DB if provided)
        domain_hints = self._score_domain_hints(
            normalized, entities,
            domain_hints_map=domain_hints_map,
            category_hints_map=category_hints_map,
        )

        # 5. Zone candidate scoring
        zone_candidates = self._resolve_zones(
            domain_hints, entities,
            domain_hints_map=domain_hints_map,
        )

        # 6. Complexity classification
        complexity = self._classify_complexity(normalized, is_multi, entities)

        return QueryAnalysisResult(
            original_query=query,
            normalized_query=normalized,
            sub_queries=sub_queries,
            entities=entities,
            domain_hints=domain_hints,
            zone_candidates=zone_candidates,
            complexity=complexity,
            is_multi_intent=is_multi,
        )

    def should_decompose(self, top_score: float, second_score: float) -> bool:
        """Intent Margin Gate — trigger decomposition if margin is narrow."""
        if top_score == 0:
            return True
        margin = (top_score - second_score) / max(1.0, top_score)
        return margin < MULTI_INTENT_MARGIN_THRESHOLD

    # ----- Internal methods -----

    def _normalize_swedish(self, query: str) -> str:
        """Expand abbreviations and normalize Swedish text."""
        normalized = query.strip()
        lower = normalized.lower()

        for abbrev, expansion in SWEDISH_NORMALIZATION_BANK.items():
            # Only replace if it's a whole word match
            pattern = rf"\b{re.escape(abbrev)}\b"
            if re.search(pattern, lower):
                normalized = re.sub(pattern, expansion, normalized, flags=re.IGNORECASE)
                lower = normalized.lower()

        return normalized

    def _extract_entities(self, query: str) -> QueryEntities:
        """Rule-based entity extraction: locations, times, organizations."""
        entities = QueryEntities()
        lower = query.lower()

        # Location extraction via gazetteer
        for key, canonical in MUNICIPALITY_GAZETTEER.items():
            if (
                re.search(rf"\b{re.escape(key)}\b", lower)
                and canonical not in entities.locations
            ):
                entities.locations.append(canonical)

        # Time extraction via patterns
        for pattern in _TIME_PATTERNS:
            matches = pattern.findall(query)
            for m in matches:
                time_str = m if isinstance(m, str) else m[0]
                if time_str not in entities.times:
                    entities.times.append(time_str)

        # Organization extraction (known Swedish authorities)
        org_patterns = {
            "smhi": "SMHI",
            "scb": "SCB",
            "trafikverket": "Trafikverket",
            "riksdagen": "Riksdagen",
            "skolverket": "Skolverket",
            "kolada": "Kolada",
            "bolagsverket": "Bolagsverket",
            "skatteverket": "Skatteverket",
            "försäkringskassan": "Försäkringskassan",
            "arbetsförmedlingen": "Arbetsförmedlingen",
        }
        for pattern, name in org_patterns.items():
            if pattern in lower:
                entities.organizations.append(name)

        return entities

    def _detect_and_split_intents(self, query: str) -> list[str]:
        """Detect multi-intent queries and split them."""
        # Check for multi-intent conjunctions
        if _MULTI_INTENT_CONJUNCTIONS.search(query):
            # Split on "och" when followed by a question word
            parts = re.split(
                r"\s+och\s+(?=(?:vad|hur|var|vilka|visa)\b)", query, flags=re.IGNORECASE
            )
            if len(parts) > 1:
                return [p.strip() for p in parts if p.strip()]

        # Check for multiple question marks
        questions = [q.strip() for q in query.split("?") if q.strip()]
        if len(questions) > 1:
            return questions

        return [query]

    def _score_domain_hints(
        self,
        query: str,
        entities: QueryEntities,
        *,
        domain_hints_map: dict[str, list[str]] | None = None,
        category_hints_map: dict[str, list[str]] | None = None,
    ) -> list[str]:
        """Score which domain zones AND categories are relevant.

        Returns a list where the first entries are zone names (e.g. "kunskap")
        followed by category hints (e.g. "väder", "statistik").  The category
        hints let the AgentResolver boost the specific agent instead of
        treating all agents in the zone equally.

        Args:
            domain_hints_map: Dynamic zone→keywords map from DB. Falls back to static config.
            category_hints_map: Dynamic agent→keywords map from DB. Falls back to static config.
        """
        _domain_hints = domain_hints_map if domain_hints_map is not None else DOMAIN_HINTS
        _category_hints = category_hints_map if category_hints_map is not None else CATEGORY_HINTS

        lower = query.lower()
        hints: list[str] = []

        # Zone-level hints (word-boundary matching to avoid partial hits)
        for zone, keywords in _domain_hints.items():
            for kw in keywords:
                # Multi-word keywords use substring, single words use \b
                if " " in kw:
                    matched = kw in lower
                else:
                    matched = bool(re.search(rf"\b{re.escape(kw)}\b", lower))
                if matched:
                    if zone not in hints:
                        hints.append(zone)
                    break

        # Category-level hints (agent-granular, same word-boundary logic)
        for category, keywords in _category_hints.items():
            for kw in keywords:
                if " " in kw:
                    matched = kw in lower
                else:
                    matched = bool(re.search(rf"\b{re.escape(kw)}\b", lower))
                if matched:
                    if category not in hints:
                        hints.append(category)
                    break

        return hints

    def _resolve_zones(
        self,
        domain_hints: list[str],
        entities: QueryEntities,
        *,
        domain_hints_map: dict[str, list[str]] | None = None,
    ) -> list[str]:
        """Determine candidate zones from domain hints and entities.

        Valid zones are derived from the domain_hints_map keys (which may
        include fine-grained domain IDs like "väder-och-klimat") plus the
        legacy Zone enum values.
        """
        # Build valid zone set from the hints map keys + legacy Zone enum
        valid_zones = {z.value for z in Zone}
        if domain_hints_map:
            valid_zones.update(domain_hints_map.keys())
        else:
            # Fall back to static DOMAIN_HINTS keys
            valid_zones.update(DOMAIN_HINTS.keys())

        zones: list[str] = [h for h in domain_hints if h in valid_zones]

        # If no hints at all, return the first few available domain zones
        # (NOT hardcoded to old legacy zones)
        if not zones:
            all_domain_keys = list(
                (domain_hints_map or DOMAIN_HINTS).keys()
            )
            # Use first domain as general fallback
            zones = all_domain_keys[:1] if all_domain_keys else [Zone.KUNSKAP.value]

        return zones

    def _classify_complexity(
        self, query: str, is_multi: bool, entities: QueryEntities
    ) -> str:
        """Classify query complexity: trivial / simple / compound / complex."""
        word_count = len(query.split())

        if is_multi:
            return "compound"
        if word_count <= 3 and not entities.locations and not entities.organizations:
            return "trivial"
        if word_count <= 8:
            return "simple"
        return "complex"
