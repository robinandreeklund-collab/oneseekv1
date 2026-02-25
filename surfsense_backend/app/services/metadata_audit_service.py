from __future__ import annotations

import asyncio
import hashlib
import json
import re
from time import perf_counter
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.new_chat.bigtool_store import (
    METADATA_MAX_DESCRIPTION_CHARS,
    METADATA_MAX_EXAMPLE_QUERIES,
    METADATA_MAX_KEYWORDS,
    ToolIndexEntry,
    enforce_metadata_limits,
    get_tool_embedding_context_split_fields,
    get_tool_embedding_context_fields,
    get_vector_recall_top_k,
    normalize_retrieval_tuning,
    smart_retrieve_tools_with_breakdown,
)
from app.services.agent_metadata_service import normalize_agent_metadata_payload
from app.services.intent_definition_service import normalize_intent_definition_payload


_TOOL_AUDIT_STOPWORDS = {
    "och",
    "att",
    "det",
    "den",
    "som",
    "for",
    "med",
    "pa",
    "på",
    "i",
    "av",
    "till",
    "fran",
    "från",
    "för",
    "hur",
    "vad",
    "visa",
    "kan",
    "finns",
    "sverige",
}

_KUNSKAP_AGENTS = {
    "kunskap", "knowledge", "webb", "browser", "väder", "weather",
    "trafik", "statistik", "statistics", "bolag", "riksdagen",
    "marknad", "marketplace",
}
_SKAPANDE_AGENTS = {
    "media", "kartor", "kod", "code", "åtgärd", "action",
}
_JAMFORELSE_AGENTS = {"syntes", "synthesis", "statistik", "statistics", "kunskap", "knowledge"}
# Backward compat aliases
_ACTION_AGENTS = _SKAPANDE_AGENTS | _KUNSKAP_AGENTS
_KNOWLEDGE_AGENTS = _KUNSKAP_AGENTS
_STATISTICS_AGENTS = {"statistik", "statistics"}
_COMPARE_AGENTS = {"syntes", "synthesis"}
_MAX_INTENT_FAILURES_FOR_LLM = 20
_MAX_AGENT_FAILURES_FOR_LLM = 20
_PROBE_QUERY_LLM_TIMEOUT_SECONDS = 18.0
_METADATA_LAYER_LLM_TIMEOUT_SECONDS = 20.0
_TOOL_ID_LIKE_RE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b", re.IGNORECASE)
_PROBE_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_PROBE_TIME_CONTEXT_RE = re.compile(
    r"\b("
    r"idag|imorgon|ikväll|i\s+morgon|nu|just\s+nu|"
    r"denna\s+(vecka|månad|helg)|"
    r"nästa\s+(vecka|månad|helg|kvartal|år)|"
    r"förra\s+(veckan|månaden|året)|"
    r"kommande\s+(dygnet|veckan|månaden)|"
    r"senaste\s+\d+\s+(dagarna|veckorna|månaderna|åren)|"
    r"under\s+(vintern|våren|sommaren|hösten)|"
    r"q[1-4]\s*(19|20)\d{2}|"
    r"januari|februari|mars|april|maj|juni|juli|augusti|"
    r"september|oktober|november|december"
    r")\b",
    re.IGNORECASE,
)
_SWEDISH_REFERENCE_CITIES = (
    "Stockholm",
    "Göteborg",
    "Malmö",
    "Uppsala",
    "Västerås",
    "Örebro",
    "Linköping",
    "Helsingborg",
    "Jönköping",
    "Norrköping",
    "Lund",
    "Umeå",
    "Gävle",
    "Borås",
    "Eskilstuna",
    "Södertälje",
    "Karlstad",
    "Östersund",
    "Luleå",
    "Sundsvall",
    "Visby",
    "Halmstad",
    "Helsingborg",
    "Skellefteå",
    "Falun",
    "Trollhättan",
)
_GENERIC_QUERY_TERMS = {
    "hjälp",
    "hjälpa",
    "visa",
    "data",
    "information",
    "relevant",
    "relevanta",
    "liknande",
    "mått",
    "sak",
    "grej",
    "sverige",
    "svenska",
    "fråga",
    "frågor",
    "underlag",
}
_LOW_SIGNAL_QUERY_PATTERNS = (
    re.compile(r"\brelevanta data\b", re.IGNORECASE),
    re.compile(r"\blika?nande mått\b", re.IGNORECASE),
    re.compile(r"\bhjälp mig\b", re.IGNORECASE),
    re.compile(r"\bvisa data\b", re.IGNORECASE),
    re.compile(r"\bvisa information\b", re.IGNORECASE),
)
_SWEDISH_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(city) for city in _SWEDISH_REFERENCE_CITIES) + r")\b",
    re.IGNORECASE,
)
_SWEDISH_QUERY_STARTERS = (
    "hur",
    "vad",
    "vilken",
    "vilka",
    "kan",
    "jämför",
    "visa",
    "ge",
    "ta fram",
    "när",
    "varför",
)

_AGENT_NAMESPACE_MAP: dict[str, tuple[list[tuple[str, ...]], list[tuple[str, ...]]]] = {
    "knowledge": (
        [("tools", "knowledge")],
        [("tools", "action"), ("tools", "statistics"), ("tools", "general")],
    ),
    "kunskap": (
        [("tools", "knowledge")],
        [("tools", "action"), ("tools", "statistics"), ("tools", "general")],
    ),
    "action": (
        [("tools", "action")],
        [
            ("tools", "knowledge"),
            ("tools", "statistics"),
            ("tools", "kartor"),
            ("tools", "general"),
        ],
    ),
    "åtgärd": (
        [("tools", "action")],
        [
            ("tools", "knowledge"),
            ("tools", "statistics"),
            ("tools", "kartor"),
            ("tools", "general"),
        ],
    ),
    "weather": (
        [("tools", "weather")],
        [("tools", "action"), ("tools", "knowledge"), ("tools", "general")],
    ),
    "väder": (
        [("tools", "weather")],
        [("tools", "action"), ("tools", "knowledge"), ("tools", "general")],
    ),
    "kartor": (
        [("tools", "kartor")],
        [("tools", "action"), ("tools", "knowledge"), ("tools", "general")],
    ),
    "media": (
        [("tools", "action", "media")],
        [
            ("tools", "knowledge"),
            ("tools", "statistics"),
            ("tools", "kartor"),
            ("tools", "general"),
        ],
    ),
    "statistics": (
        [("tools", "statistics")],
        [("tools", "action"), ("tools", "knowledge"), ("tools", "general")],
    ),
    "statistik": (
        [("tools", "statistics")],
        [("tools", "action"), ("tools", "knowledge"), ("tools", "general")],
    ),
    "browser": (
        [("tools", "knowledge", "web")],
        [
            ("tools", "knowledge"),
            ("tools", "action"),
            ("tools", "statistics"),
            ("tools", "general"),
        ],
    ),
    "webb": (
        [("tools", "knowledge", "web")],
        [
            ("tools", "knowledge"),
            ("tools", "action"),
            ("tools", "statistics"),
            ("tools", "general"),
        ],
    ),
    "code": (
        [("tools", "code")],
        [
            ("tools", "general"),
            ("tools", "knowledge"),
            ("tools", "action"),
            ("tools", "statistics"),
        ],
    ),
    "kod": (
        [("tools", "code")],
        [
            ("tools", "general"),
            ("tools", "knowledge"),
            ("tools", "action"),
            ("tools", "statistics"),
        ],
    ),
    "bolag": (
        [("tools", "bolag")],
        [
            ("tools", "knowledge"),
            ("tools", "statistics"),
            ("tools", "action"),
            ("tools", "general"),
        ],
    ),
    "trafik": (
        [("tools", "trafik")],
        [("tools", "action"), ("tools", "knowledge"), ("tools", "general")],
    ),
    "riksdagen": (
        [("tools", "politik")],
        [("tools", "knowledge"), ("tools", "action"), ("tools", "general")],
    ),
    "marketplace": (
        [("tools", "marketplace")],
        [("tools", "knowledge"), ("tools", "general")],
    ),
    "marknad": (
        [("tools", "marketplace")],
        [("tools", "knowledge"), ("tools", "general")],
    ),
    "synthesis": (
        [("tools", "knowledge")],
        [("tools", "statistics"), ("tools", "action"), ("tools", "general")],
    ),
    "syntes": (
        [("tools", "knowledge")],
        [("tools", "statistics"), ("tools", "action"), ("tools", "general")],
    ),
}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


_SWEDISH_QUERY_DIACRITIC_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bgoteborg\b", "göteborg"),
    (r"\bmalmo\b", "malmö"),
    (r"\blulea\b", "luleå"),
    (r"\bostersund\b", "östersund"),
    (r"\bgavle\b", "gävle"),
    (r"\bvasteras\b", "västerås"),
    (r"\bjonkoping\b", "jönköping"),
    (r"\bnasta\b", "nästa"),
    (r"\bmanad\b", "månad"),
    (r"\bmanaden\b", "månaden"),
    (r"\bmanader\b", "månader"),
    (r"\bvader\b", "väder"),
    (r"\bhjalp\b", "hjälp"),
    (r"\bjamfor\b", "jämför"),
    (r"\bfraga\b", "fråga"),
    (r"\bfragor\b", "frågor"),
    (r"\banvanda\b", "använda"),
    (r"\banvander\b", "använder"),
    (r"\banvandning\b", "användning"),
    (r"\bfor\b", "för"),
    (r"\bfran\b", "från"),
    (r"\bnar\b", "när"),
    (r"\bratt\b", "rätt"),
)


def _apply_case_pattern(source: str, replacement: str) -> str:
    if not source:
        return replacement
    if source.isupper():
        return replacement.upper()
    if source[0].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _swedishify_query_text(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    updated = text
    for pattern, replacement in _SWEDISH_QUERY_DIACRITIC_REPLACEMENTS:
        updated = re.sub(
            pattern,
            lambda match, repl=replacement: _apply_case_pattern(match.group(0), repl),
            updated,
            flags=re.IGNORECASE,
        )
    return updated


def _has_swedish_diacritics(value: str) -> bool:
    return bool(re.search(r"[åäöÅÄÖ]", str(value or "")))


def _tool_reference_markers(entry: ToolIndexEntry, neighbors: list[str]) -> set[str]:
    markers: set[str] = set()

    def _add(raw: Any) -> None:
        text = _normalize_text(raw).casefold()
        if len(text) < 3:
            return
        compact = " ".join(text.split())
        if compact:
            markers.add(compact)
        if "_" in compact:
            markers.add(compact.replace("_", " "))
            markers.add(compact.replace("_", "-"))

    _add(entry.tool_id)
    _add(entry.name)
    for neighbor in list(neighbors or []):
        _add(neighbor)
    return markers


def _contains_forbidden_tool_reference(query: str, *, forbidden_markers: set[str]) -> bool:
    normalized = _normalize_text(query).casefold()
    if not normalized:
        return False
    if _TOOL_ID_LIKE_RE.search(normalized):
        return True
    for marker in forbidden_markers:
        if marker and marker in normalized:
            return True
    return False


def _is_valid_probe_query(query: str, *, forbidden_markers: set[str]) -> bool:
    normalized = _swedishify_query_text(query)
    if not normalized:
        return False
    if len(normalized) < 12 or len(normalized) > 180:
        return False
    if len(_tokenize(normalized)) < 3:
        return False
    if any(pattern.search(normalized) for pattern in _LOW_SIGNAL_QUERY_PATTERNS):
        return False
    if not _has_swedish_diacritics(normalized):
        return False
    if _contains_forbidden_tool_reference(normalized, forbidden_markers=forbidden_markers):
        return False
    return True


def _has_city_reference(query: str) -> bool:
    return bool(_SWEDISH_CITY_RE.search(str(query or "")))


def _has_time_or_year_reference(query: str) -> bool:
    text = str(query or "")
    return bool(_PROBE_TIME_CONTEXT_RE.search(text) or _PROBE_YEAR_RE.search(text))


def _query_domain_terms(entry: ToolIndexEntry, *, limit: int = 80) -> set[str]:
    terms: set[str] = set()
    effective_limit = max(10, int(limit))

    def _extend(value: str) -> None:
        for token in _tokenize(value):
            if token in _GENERIC_QUERY_TERMS:
                continue
            terms.add(token)
            if len(terms) >= effective_limit:
                return

    for keyword in list(entry.keywords or [])[:METADATA_MAX_KEYWORDS]:
        _extend(str(keyword))
        if len(terms) >= effective_limit:
            break
    if len(terms) < effective_limit:
        _extend(entry.category or "")
    if len(terms) < effective_limit:
        _extend(entry.description or "")
    if len(terms) < effective_limit:
        _extend(entry.name or "")
    if len(terms) < effective_limit:
        _extend(getattr(entry, "main_identifier", "") or "")
    if len(terms) < effective_limit:
        _extend(getattr(entry, "core_activity", "") or "")
    if len(terms) < effective_limit:
        _extend(getattr(entry, "unique_scope", "") or "")
    if len(terms) < effective_limit:
        _extend(getattr(entry, "geographic_scope", "") or "")
    for sample in list(entry.example_queries or [])[:8]:
        if len(terms) >= effective_limit:
            break
        _extend(str(sample))
    for exclude_term in list(getattr(entry, "excludes", ()) or ()):
        if len(terms) >= effective_limit:
            break
        _extend(str(exclude_term))
    return terms


def _probe_query_quality_row(
    query: str,
    *,
    domain_terms: set[str],
) -> dict[str, Any]:
    normalized = _swedishify_query_text(query)
    tokens = _tokenize(normalized)
    token_set = set(tokens)
    domain_overlap = len(token_set & set(domain_terms))
    has_city = _has_city_reference(normalized)
    has_time = _has_time_or_year_reference(normalized)
    starts_naturally = normalized.casefold().startswith(_SWEDISH_QUERY_STARTERS)
    ends_question = normalized.endswith("?")
    low_signal = any(pattern.search(normalized) for pattern in _LOW_SIGNAL_QUERY_PATTERNS)
    score = 0.0
    score += min(4.0, float(domain_overlap)) * 2.2
    if has_city:
        score += 1.2
    if has_time:
        score += 1.2
    if starts_naturally or ends_question:
        score += 0.6
    token_count = len(tokens)
    if 5 <= token_count <= 16:
        score += 0.6
    elif token_count < 4 or token_count > 24:
        score -= 1.0
    if low_signal:
        score -= 2.5
    return {
        "query": normalized,
        "score": float(score),
        "has_city": has_city,
        "has_time": has_time,
        "domain_overlap": domain_overlap,
    }


def _select_high_quality_probe_queries(
    *,
    entry: ToolIndexEntry,
    candidates: list[str],
    query_count: int,
    forbidden_markers: set[str],
    avoid_keys: set[str] | None = None,
) -> list[str]:
    target_count = max(1, int(query_count))
    blocked = set(avoid_keys or set())
    domain_terms = _query_domain_terms(entry)
    scored: list[dict[str, Any]] = []
    seen: set[str] = set()

    for candidate in list(candidates or []):
        normalized = _swedishify_query_text(candidate)
        key = normalized.casefold()
        if (
            not normalized
            or key in seen
            or key in blocked
            or not _is_valid_probe_query(normalized, forbidden_markers=forbidden_markers)
        ):
            continue
        seen.add(key)
        scored.append(
            _probe_query_quality_row(
                normalized,
                domain_terms=domain_terms,
            )
        )

    if not scored:
        return []
    scored.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            int(item.get("domain_overlap") or 0),
            len(str(item.get("query") or "")),
        ),
        reverse=True,
    )
    city_target = 1 if target_count <= 2 else max(1, int(round(target_count * 0.6)))
    time_target = 1 if target_count <= 2 else max(1, int(round(target_count * 0.6)))
    selected: list[str] = []
    selected_keys: set[str] = set()
    city_count = 0
    time_count = 0

    def _take_row(
        *,
        require_city: bool | None = None,
        require_time: bool | None = None,
    ) -> bool:
        nonlocal city_count, time_count
        for row in scored:
            query = str(row.get("query") or "")
            key = query.casefold()
            if not query or key in selected_keys:
                continue
            has_city = bool(row.get("has_city"))
            has_time = bool(row.get("has_time"))
            if require_city is not None and has_city is not require_city:
                continue
            if require_time is not None and has_time is not require_time:
                continue
            selected.append(query)
            selected_keys.add(key)
            if has_city:
                city_count += 1
            if has_time:
                time_count += 1
            return True
        return False

    while len(selected) < target_count and city_count < city_target and time_count < time_target:
        if not _take_row(require_city=True, require_time=True):
            break
    while len(selected) < target_count and city_count < city_target:
        if not _take_row(require_city=True, require_time=None):
            break
    while len(selected) < target_count and time_count < time_target:
        if not _take_row(require_city=None, require_time=True):
            break
    while len(selected) < target_count:
        if not _take_row(require_city=None, require_time=None):
            break
    return selected[:target_count]


def _compact_failures_for_llm(
    failures: list[dict[str, Any]],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in failures[: max(1, int(max_items))]:
        if not isinstance(item, dict):
            continue
        compacted.append(
            {
                "probe_id": _normalize_text(item.get("probe_id")),
                "query": _normalize_text(item.get("query")),
                "expected_intent_id": _normalize_text(item.get("expected_intent_id")).lower() or None,
                "predicted_intent_id": _normalize_text(item.get("predicted_intent_id")).lower() or None,
                "expected_agent_id": _normalize_text(item.get("expected_agent_id")).lower() or None,
                "predicted_agent_id": _normalize_text(item.get("predicted_agent_id")).lower() or None,
                "score_breakdown": list(item.get("score_breakdown") or [])[:4],
            }
        )
    return compacted


def _safe_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9åäöÅÄÖ]{3,}", str(text or "").lower())
    return [token for token in tokens if token not in _TOOL_AUDIT_STOPWORDS]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    payload = str(text or "").strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = payload.find("{")
    end = payload.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        parsed = json.loads(payload[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _response_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    chunks.append(text_value)
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    return str(content or "")


def _cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for a, b in zip(left, right):
        dot += a * b
        norm_left += a * a
        norm_right += b * b
    if norm_left <= 0.0 or norm_right <= 0.0:
        return 0.0
    return dot / ((norm_left**0.5) * (norm_right**0.5))


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _embed_text(text: str) -> list[float] | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    try:
        from app.config import config

        vector = config.embedding_model_instance.embed(normalized)
    except Exception:
        return None
    if isinstance(vector, list):
        try:
            return [float(value) for value in vector]
        except Exception:
            return None
    try:
        return [float(value) for value in vector]
    except Exception:
        return None


def _tool_similarity_score(left: ToolIndexEntry, right: ToolIndexEntry) -> float:
    left_keywords = {item.casefold() for item in left.keywords if item}
    right_keywords = {item.casefold() for item in right.keywords if item}
    keyword_similarity = _jaccard_similarity(left_keywords, right_keywords)
    left_desc_tokens = set(_tokenize(left.description))
    right_desc_tokens = set(_tokenize(right.description))
    description_similarity = _jaccard_similarity(left_desc_tokens, right_desc_tokens)
    left_example_tokens = set(_tokenize(" ".join(left.example_queries)))
    right_example_tokens = set(_tokenize(" ".join(right.example_queries)))
    example_similarity = _jaccard_similarity(left_example_tokens, right_example_tokens)
    embedding_similarity = _cosine_similarity(left.embedding, right.embedding)
    return (
        (keyword_similarity * 0.45)
        + (description_similarity * 0.25)
        + (example_similarity * 0.15)
        + (embedding_similarity * 0.15)
    )


def _nearest_neighbor_map(
    entries: list[ToolIndexEntry],
    *,
    max_neighbors: int = 3,
) -> dict[str, list[str]]:
    by_id = {entry.tool_id: entry for entry in entries}
    neighbors: dict[str, list[str]] = {}
    for entry in entries:
        scored: list[tuple[str, float]] = []
        for other in entries:
            if other.tool_id == entry.tool_id:
                continue
            similarity = _tool_similarity_score(entry, other)
            if similarity <= 0.0:
                continue
            scored.append((other.tool_id, similarity))
        scored.sort(key=lambda item: item[1], reverse=True)
        neighbors[entry.tool_id] = [
            tool_id
            for tool_id, _score in scored[: max(1, int(max_neighbors))]
            if tool_id in by_id
        ]
    return neighbors


def _fallback_probe_queries(
    *,
    entry: ToolIndexEntry,
    neighbors: list[str],
    query_count: int,
    hard_negatives_per_tool: int = 1,
    avoid_queries: list[str] | None = None,
    round_index: int = 1,
) -> list[str]:
    hard_negative_count = max(0, min(int(hard_negatives_per_tool or 0), 10))
    normalized_round = max(1, min(int(round_index or 1), 1000))
    forbidden_markers = _tool_reference_markers(entry, neighbors)
    domain_terms = list(_query_domain_terms(entry, limit=max(query_count * 8, 24)))
    if not domain_terms:
        domain_terms = _tokenize(entry.description)[: max(2, query_count * 4)]
    if not domain_terms:
        domain_terms = _tokenize(entry.name)[: max(2, query_count * 2)] or ["utveckling"]

    locations = list(_SWEDISH_REFERENCE_CITIES)
    time_windows = [
        "idag",
        "imorgon",
        "kommande veckan",
        "denna månad",
        "nästa månad",
        "det här året",
        "nästa år",
        "under sommaren",
        "under vintern",
        "de senaste 12 månaderna",
        "de senaste 3 åren",
    ]

    avoid_keys = {
        normalized.casefold()
        for query in list(avoid_queries or [])
        if (normalized := _swedishify_query_text(query))
    }
    candidates: list[str] = []
    seen: set[str] = set()
    rotation_seed = sum(ord(ch) for ch in str(entry.tool_id)) + normalized_round
    location_offset = rotation_seed % len(locations)
    time_offset = (rotation_seed * 3) % len(time_windows)
    year_base = 2021 + (normalized_round % 5)

    def _append(prompt: str) -> None:
        normalized = _swedishify_query_text(prompt)
        if not normalized:
            return
        key = normalized.casefold()
        if key in seen or key in avoid_keys:
            return
        seen.add(key)
        candidates.append(normalized)

    if neighbors and hard_negative_count > 0:
        for idx in range(max(hard_negative_count * 2, hard_negative_count)):
            location = locations[(location_offset + idx) % len(locations)]
            time_window = time_windows[(time_offset + idx) % len(time_windows)]
            term_a = domain_terms[idx % len(domain_terms)]
            term_b = domain_terms[(idx + 3) % len(domain_terms)] if domain_terms else term_a
            if idx % 2 == 0:
                _append(
                    f"När är {term_a} mer relevant än {term_b} i {location} {time_window}?"
                )
            else:
                _append(
                    f"Hur skiljer sig {term_a} och {term_b} i {location} {time_window}?"
                )

    candidate_limit = max(query_count * 8, 24)
    for idx in range(candidate_limit):
        term = domain_terms[idx % len(domain_terms)]
        alt_term = domain_terms[(idx + 5) % len(domain_terms)]
        location = locations[(location_offset + idx) % len(locations)]
        time_window = time_windows[(time_offset + idx) % len(time_windows)]
        year = year_base + (idx % 4)
        if idx % 4 == 0:
            _append(f"Hur har {term} utvecklats i {location} under {time_window}?")
        elif idx % 4 == 1:
            _append(f"Kan du visa {term} i {location} för år {year}?")
        elif idx % 4 == 2:
            _append(
                f"Vilka nivåer ser vi för {term} i {location} mellan {year - 1} och {year}?"
            )
        else:
            _append(
                f"Jämför {term} med {alt_term} i {location} {time_window}."
            )

    selected = _select_high_quality_probe_queries(
        entry=entry,
        candidates=candidates,
        query_count=query_count,
        forbidden_markers=forbidden_markers,
        avoid_keys=avoid_keys,
    )
    if selected:
        return selected[:query_count]

    if domain_terms:
        _append(f"Hur ser {domain_terms[0]} ut i {locations[location_offset]} under nästa år?")
        _append(
            f"Vilken utveckling har {domain_terms[0]} haft i {locations[(location_offset + 1) % len(locations)]} sedan {year_base}?"
        )

    return _select_high_quality_probe_queries(
        entry=entry,
        candidates=candidates,
        query_count=query_count,
        forbidden_markers=forbidden_markers,
        avoid_keys=avoid_keys,
    )


async def _generate_probe_queries_for_tool(
    *,
    llm: Any,
    entry: ToolIndexEntry,
    neighbors: list[str],
    query_count: int,
    hard_negatives_per_tool: int = 1,
    avoid_queries: list[str] | None = None,
    round_index: int = 1,
) -> list[str]:
    hard_negative_count = max(0, min(int(hard_negatives_per_tool or 0), 10))
    forbidden_markers = _tool_reference_markers(entry, neighbors)
    avoid_keys = {
        normalized.casefold()
        for query in list(avoid_queries or [])
        if (normalized := _swedishify_query_text(query))
    }
    if llm is None:
        return _fallback_probe_queries(
            entry=entry,
            neighbors=neighbors,
            query_count=query_count,
            hard_negatives_per_tool=hard_negative_count,
            avoid_queries=list(avoid_keys),
            round_index=round_index,
        )
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm

    prompt = (
        "You generate Swedish probe queries for retrieval-only metadata audit.\n"
        "Goal: create top-quality user questions that should map to one tool and expose overlap.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "queries": ["query 1", "query 2"]\n'
        "}\n"
        "Rules:\n"
        "- Swedish language.\n"
        "- Every query must be natural, fluent Swedish as a real user would write it.\n"
        "- Use correct Swedish spelling with diacritics (å, ä, ö); do not transliterate.\n"
        "- Do NOT write robotic, generic, or template-like wording.\n"
        "- Use realistic Swedish context: cities, municipalities, regions, seasons, dates, years.\n"
        "- At least 70% of queries should include a Swedish city/place and explicit time context.\n"
        "- Every query must include domain-specific wording grounded in keywords/description.\n"
        "- Prefer concrete requests with measurable scope (e.g. period, location, comparison).\n"
        "- Keep focus tight to the target category; avoid vague phrasing.\n"
        "- Strictly forbidden: tool_id, tool names, function names, endpoint names, internal identifiers.\n"
        "- Never include underscore identifiers like marketplace_regions, smhi_forecast, trafikverket_*.\n"
        "- No markdown.\n"
        "- Keep each query realistic and concise (roughly 6-16 words when possible).\n"
        "- Include borderline/ambiguous hard negatives when requested.\n"
        "- Do not repeat any query listed in avoid_queries.\n"
        "- Prioritize novel phrasings for the provided round_index.\n"
    )
    domain_terms = sorted(_query_domain_terms(entry))[:40]
    city_examples = list(_SWEDISH_REFERENCE_CITIES[:16])
    time_examples = [
        "idag",
        "imorgon",
        "denna månad",
        "nästa månad",
        "de senaste 12 månaderna",
        "under 2024",
        "Q1 2025",
        "under sommaren",
    ]
    tool_context: dict[str, Any] = {
        "name": entry.name,
        "category": entry.category,
        "description": entry.description,
        "keywords": entry.keywords,
        "example_queries": entry.example_queries[:8],
    }
    if getattr(entry, "main_identifier", ""):
        tool_context["main_identifier"] = entry.main_identifier
    if getattr(entry, "core_activity", ""):
        tool_context["core_activity"] = entry.core_activity
    if getattr(entry, "unique_scope", ""):
        tool_context["unique_scope"] = entry.unique_scope
    if getattr(entry, "geographic_scope", ""):
        tool_context["geographic_scope"] = entry.geographic_scope
    if getattr(entry, "excludes", ()):
        tool_context["excludes"] = list(entry.excludes)
    payload = {
        "tool_context": tool_context,
        "target_quality_profile": {
            "language": "naturlig svenska",
            "style": "konkret och verklighetsnära användarfråga",
            "must_use_context": ["svensk plats", "tid/år/period"],
            "must_reflect_category": True,
            "forbid_internal_identifiers": True,
        },
        "domain_terms": domain_terms,
        "city_examples": city_examples,
        "time_examples": time_examples,
        "description": entry.description,
        "keywords": entry.keywords,
        "neighbor_count": len(list(neighbors or [])),
        "query_count": max(1, int(query_count)),
        "hard_negatives_per_tool": hard_negative_count,
        "round_index": max(1, int(round_index or 1)),
        "avoid_queries": list(avoid_keys)[:80],
    }
    try:
        response = await asyncio.wait_for(
            model.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
                ]
            ),
            timeout=_PROBE_QUERY_LLM_TIMEOUT_SECONDS,
        )
        parsed = _extract_json_object(
            _response_content_to_text(getattr(response, "content", ""))
        )
        if not parsed:
            return _fallback_probe_queries(
                entry=entry,
                neighbors=neighbors,
                query_count=query_count,
                hard_negatives_per_tool=hard_negative_count,
                avoid_queries=list(avoid_keys),
                round_index=round_index,
            )
        generated_candidates = _safe_string_list(parsed.get("queries"))
        if not generated_candidates:
            return _fallback_probe_queries(
                entry=entry,
                neighbors=neighbors,
                query_count=query_count,
                hard_negatives_per_tool=hard_negative_count,
                avoid_queries=list(avoid_keys),
                round_index=round_index,
            )
        hard_negative_queries = (
            _fallback_probe_queries(
                entry=entry,
                neighbors=neighbors,
                query_count=min(hard_negative_count, max(1, int(query_count))),
                hard_negatives_per_tool=hard_negative_count,
                avoid_queries=[*list(avoid_keys), *generated_candidates],
                round_index=round_index,
            )
            if hard_negative_count > 0
            else []
        )
        merged = _select_high_quality_probe_queries(
            entry=entry,
            candidates=[*generated_candidates, *hard_negative_queries],
            query_count=query_count,
            forbidden_markers=forbidden_markers,
            avoid_keys=avoid_keys,
        )
        if len(merged) < query_count:
            refill_queries = _fallback_probe_queries(
                entry=entry,
                neighbors=neighbors,
                query_count=max(query_count * 2, query_count),
                hard_negatives_per_tool=hard_negative_count,
                avoid_queries=[*list(avoid_keys), *merged],
                round_index=round_index,
            )
            merged = _select_high_quality_probe_queries(
                entry=entry,
                candidates=[*merged, *refill_queries],
                query_count=query_count,
                forbidden_markers=forbidden_markers,
                avoid_keys=avoid_keys,
            )
        if merged:
            return merged[:query_count]
        return _fallback_probe_queries(
            entry=entry,
            neighbors=neighbors,
            query_count=query_count,
            hard_negatives_per_tool=hard_negative_count,
            avoid_queries=list(avoid_keys),
            round_index=round_index,
        )
    except Exception:
        return _fallback_probe_queries(
            entry=entry,
            neighbors=neighbors,
            query_count=query_count,
            hard_negatives_per_tool=hard_negative_count,
            avoid_queries=list(avoid_keys),
            round_index=round_index,
        )


def _dedupe_queries(queries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for query, source in queries:
        cleaned = _swedishify_query_text(query)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((cleaned, source))
    return deduped


def _select_audit_entries(
    *,
    tool_index: list[ToolIndexEntry],
    tool_ids: list[str],
    tool_id_prefix: str | None,
    max_tools: int,
) -> list[ToolIndexEntry]:
    selected = list(tool_index)
    normalized_ids = {str(tool_id).strip() for tool_id in tool_ids if str(tool_id).strip()}
    if normalized_ids:
        selected = [entry for entry in selected if entry.tool_id in normalized_ids]
    normalized_prefix = str(tool_id_prefix or "").strip().lower()
    if normalized_prefix:
        selected = [
            entry
            for entry in selected
            if str(entry.tool_id).strip().lower().startswith(normalized_prefix)
        ]
    selected.sort(key=lambda entry: str(entry.tool_id))
    capped = max(1, min(int(max_tools or 25), 250))
    return selected[:capped]


def _agent_route_bonus(agent_id: str, intent_id: str | None, namespace_boost: float) -> float:
    normalized_agent = str(agent_id or "").strip().lower()
    normalized_intent = str(intent_id or "").strip().lower()
    if not normalized_intent:
        return 0.0
    if normalized_intent in {"info_sokning", "kunskap", "knowledge"} and normalized_agent in _KUNSKAP_AGENTS:
        return namespace_boost
    if normalized_intent in {"generering", "skapande", "action"} and normalized_agent in _SKAPANDE_AGENTS:
        return namespace_boost
    if normalized_intent in {"jamfor_analys", "jämförelse", "compare"} and normalized_agent in _JAMFORELSE_AGENTS:
        return namespace_boost
    if normalized_intent in {"smalltalk", "konversation"} and normalized_agent in _KUNSKAP_AGENTS:
        return namespace_boost
    # Backward compat
    if normalized_intent == "statistics" and normalized_agent in _STATISTICS_AGENTS:
        return namespace_boost
    return 0.0


def _rank_metadata_candidates(
    *,
    query: str,
    candidates: list[dict[str, Any]],
    retrieval_tuning: dict[str, Any],
    intent_hint: str | None = None,
) -> list[dict[str, Any]]:
    tuning = normalize_retrieval_tuning(retrieval_tuning or {})
    query_norm = str(query or "").strip().lower()
    query_tokens = set(_tokenize(query_norm))
    query_embedding = _embed_text(query)

    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        label = _normalize_text(candidate.get("label"))
        candidate_id = _normalize_text(candidate.get("id"))
        description = _normalize_text(candidate.get("description"))
        keywords = _safe_string_list(candidate.get("keywords"))
        label_norm = label.lower()
        candidate_id_norm = candidate_id.lower()
        name_match_hits = 0
        if label_norm and label_norm in query_norm:
            name_match_hits += 1
        if candidate_id_norm and candidate_id_norm in query_norm:
            name_match_hits += 1
        keyword_hits = sum(
            1 for keyword in keywords if str(keyword).strip().lower() in query_norm
        )
        description_hits = sum(
            1 for token in query_tokens if token and token in description.lower()
        )
        lexical_score = (
            (name_match_hits * tuning.name_match_weight)
            + (keyword_hits * tuning.keyword_weight)
            + (description_hits * tuning.description_token_weight)
        )
        candidate_embedding = candidate.get("embedding")
        if not isinstance(candidate_embedding, list):
            candidate_embedding = _embed_text(
                f"{label}\n{description}\nKeywords: {', '.join(keywords)}"
            )
        embedding_raw = _cosine_similarity(query_embedding, candidate_embedding)
        embedding_weighted = embedding_raw * tuning.embedding_weight
        route_bonus = _agent_route_bonus(
            candidate_id,
            intent_hint,
            tuning.namespace_boost,
        )
        score = lexical_score + embedding_weighted + route_bonus
        ranked.append(
            {
                "label": candidate_id,
                "name": label,
                "score": float(score),
                "pre_score": float(score),
                "name_match_hits": int(name_match_hits),
                "keyword_hits": int(keyword_hits),
                "description_hits": int(description_hits),
                "lexical_score": float(lexical_score),
                "embedding_score_raw": float(embedding_raw),
                "embedding_score_weighted": float(embedding_weighted),
                "intent_route_bonus": float(route_bonus),
            }
        )
    ranked.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return ranked


def _layer_result(
    *,
    expected_label: str | None,
    ranked: list[dict[str, Any]],
) -> dict[str, Any]:
    top1 = str(ranked[0].get("label") or "").strip() if ranked else None
    top2 = str(ranked[1].get("label") or "").strip() if len(ranked) > 1 else None
    top1_score = float(ranked[0].get("pre_score") or ranked[0].get("score") or 0.0) if ranked else None
    top2_score = (
        float(ranked[1].get("pre_score") or ranked[1].get("score") or 0.0)
        if len(ranked) > 1
        else None
    )
    margin = (
        (top1_score - top2_score)
        if top1_score is not None and top2_score is not None
        else None
    )
    expected_rank: int | None = None
    expected_margin: float | None = None
    if expected_label:
        expected_score: float | None = None
        best_other_score: float | None = None
        for idx, item in enumerate(ranked):
            label = _normalize_text(item.get("label"))
            score = float(item.get("pre_score") or item.get("score") or 0.0)
            if label == expected_label and expected_rank is None:
                expected_rank = idx + 1
                expected_score = score
            elif best_other_score is None or score > best_other_score:
                best_other_score = score
        if expected_score is not None and best_other_score is not None:
            expected_margin = expected_score - best_other_score
    return {
        "expected_label": expected_label,
        "predicted_label": top1,
        "top1": top1,
        "top2": top2,
        "expected_rank": expected_rank,
        "expected_margin_vs_best_other": expected_margin,
        "margin": margin,
        "score_breakdown": ranked[:6],
    }


def _tool_layer_result(
    *,
    expected_label: str | None,
    ranked_ids: list[str],
    retrieval_breakdown: list[dict[str, Any]],
) -> dict[str, Any]:
    top1 = ranked_ids[0] if ranked_ids else None
    top2 = ranked_ids[1] if len(ranked_ids) > 1 else None
    score_by_id: dict[str, float] = {}
    rank_by_id: dict[str, int] = {}
    for item in retrieval_breakdown:
        tool_id = _normalize_text(item.get("tool_id"))
        if not tool_id:
            continue
        rank_value = _to_positive_int_or_none(item.get("rank"))
        if rank_value is None:
            rank_value = len(rank_by_id) + 1
        rank_by_id[tool_id] = rank_value
        score_by_id[tool_id] = float(
            item.get("pre_rerank_score") or item.get("score") or 0.0
        )
    margin = (
        score_by_id[top1] - score_by_id[top2]
        if top1 and top2 and top1 in score_by_id and top2 in score_by_id
        else None
    )
    expected_rank = rank_by_id.get(expected_label) if expected_label else None
    expected_margin: float | None = None
    if expected_label and expected_label in score_by_id:
        expected_score = score_by_id[expected_label]
        competitor_scores = [
            score
            for tool_id, score in score_by_id.items()
            if tool_id != expected_label
        ]
        if competitor_scores:
            expected_margin = expected_score - max(competitor_scores)
    return {
        "expected_label": expected_label,
        "predicted_label": top1,
        "top1": top1,
        "top2": top2,
        "expected_rank": expected_rank,
        "expected_margin_vs_best_other": expected_margin,
        "margin": margin,
        "score_breakdown": retrieval_breakdown[:8],
    }


def _to_positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _tool_vector_diagnostics(
    *,
    expected_label: str | None,
    predicted_label: str | None,
    retrieval_breakdown: list[dict[str, Any]],
) -> dict[str, Any]:
    vector_top_k = get_vector_recall_top_k()
    by_tool_id: dict[str, dict[str, Any]] = {}
    vector_selected: list[tuple[int, str]] = []

    for row in retrieval_breakdown:
        tool_id = _normalize_text(row.get("tool_id"))
        if not tool_id:
            continue
        vector_selected_flag = bool(row.get("vector_recall_selected", False))
        vector_rank = _to_positive_int_or_none(row.get("vector_recall_rank"))
        lexical_selected_flag = bool(row.get("lexical_candidate_selected", False))
        vector_only_flag = bool(row.get("vector_only_candidate", False))
        by_tool_id[tool_id] = {
            "vector_recall_selected": vector_selected_flag,
            "vector_recall_rank": vector_rank,
            "lexical_candidate_selected": lexical_selected_flag,
            "vector_only_candidate": vector_only_flag,
        }
        if vector_selected_flag:
            vector_selected.append(
                (
                    vector_rank if vector_rank is not None else 1_000_000,
                    tool_id,
                )
            )

    vector_selected.sort(key=lambda item: item[0])
    vector_selected_ids = [tool_id for _rank, tool_id in vector_selected]
    predicted = by_tool_id.get(_normalize_text(predicted_label))
    expected = by_tool_id.get(_normalize_text(expected_label))
    return {
        "vector_top_k": vector_top_k,
        "vector_selected_ids": vector_selected_ids[: max(1, int(vector_top_k))],
        "predicted_tool_vector_selected": bool(
            predicted and predicted.get("vector_recall_selected")
        ),
        "predicted_tool_vector_rank": (
            int(predicted.get("vector_recall_rank"))
            if predicted and predicted.get("vector_recall_rank") is not None
            else None
        ),
        "predicted_tool_vector_only": bool(
            predicted and predicted.get("vector_only_candidate")
        ),
        "predicted_tool_lexical_candidate": bool(
            predicted and predicted.get("lexical_candidate_selected")
        ),
        "expected_tool_vector_selected": bool(
            expected and expected.get("vector_recall_selected")
        ),
        "expected_tool_vector_rank": (
            int(expected.get("vector_recall_rank"))
            if expected and expected.get("vector_recall_rank") is not None
            else None
        ),
        "expected_tool_vector_only": bool(
            expected and expected.get("vector_only_candidate")
        ),
        "expected_tool_lexical_candidate": bool(
            expected and expected.get("lexical_candidate_selected")
        ),
    }


def _tool_namespaces_for_agent(
    agent_id: str | None,
) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
    normalized = str(agent_id or "").strip().lower()
    if normalized in _AGENT_NAMESPACE_MAP:
        return _AGENT_NAMESPACE_MAP[normalized]
    return [("tools", "action")], [("tools", "knowledge"), ("tools", "general")]


def _path_label(intent_id: str | None, agent_id: str | None, tool_id: str | None) -> str:
    return f"{intent_id or '-'}>{agent_id or '-'}>{tool_id or '-'}"


def _matrix_rows_from_counts(
    counts: dict[tuple[str, str], int],
    *,
    expected_key: str,
    predicted_key: str,
    limit: int = 60,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (expected, predicted), count in sorted(
        counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )[: max(1, int(limit))]:
        rows.append(
            {
                expected_key: expected,
                predicted_key: predicted,
                "count": count,
            }
        )
    return rows


def _normalize_parallelism(value: int | None, *, default: int = 1) -> int:
    try:
        parsed = int(value or default)
    except Exception:
        parsed = default
    return max(1, min(parsed, 32))


def _normalize_anchor_probe_set(
    anchor_probe_set: list[dict[str, Any]] | None,
) -> dict[str, list[tuple[str, str]]]:
    normalized: dict[str, list[tuple[str, str]]] = {}
    seen_by_tool: dict[str, set[str]] = {}
    for item in list(anchor_probe_set or []):
        if not isinstance(item, dict):
            continue
        tool_id = _normalize_text(item.get("tool_id"))
        query = _swedishify_query_text(item.get("query"))
        source = _normalize_text(item.get("source")) or "anchor"
        if not tool_id or not query:
            continue
        key = query.casefold()
        seen = seen_by_tool.setdefault(tool_id, set())
        if key in seen:
            continue
        seen.add(key)
        normalized.setdefault(tool_id, []).append((query, source))
    return normalized


async def run_layered_metadata_audit(
    *,
    tool_index: list[ToolIndexEntry],
    llm: Any,
    retrieval_tuning: dict[str, Any],
    intent_definitions: list[dict[str, Any]],
    agent_metadata: list[dict[str, Any]],
    expected_intent_by_tool: dict[str, str],
    expected_agent_by_tool: dict[str, str],
    tool_ids: list[str] | None = None,
    tool_id_prefix: str | None = None,
    include_existing_examples: bool = True,
    include_llm_generated: bool = True,
    llm_queries_per_tool: int = 3,
    max_queries_per_tool: int = 6,
    hard_negatives_per_tool: int = 1,
    retrieval_limit: int = 5,
    max_tools: int = 25,
    probe_generation_parallelism: int = 1,
    probe_round: int = 1,
    exclude_probe_queries: list[str] | None = None,
    anchor_probe_set: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    total_started_at = perf_counter()
    preparation_started_at = total_started_at
    selected_entries = _select_audit_entries(
        tool_index=tool_index,
        tool_ids=list(tool_ids or []),
        tool_id_prefix=tool_id_prefix,
        max_tools=max_tools,
    )
    neighbors_by_tool = _nearest_neighbor_map(selected_entries, max_neighbors=3)
    intent_candidates = [
        {
            "id": str(definition.get("intent_id") or "").strip(),
            "label": str(definition.get("label") or definition.get("intent_id") or "").strip(),
            "description": str(definition.get("description") or "").strip(),
            "keywords": list(definition.get("keywords") or []),
            "route": str(definition.get("route") or "").strip().lower(),
        }
        for definition in intent_definitions
        if str(definition.get("intent_id") or "").strip()
    ]
    agent_candidates = [
        {
            "id": str(payload.get("agent_id") or "").strip(),
            "label": str(payload.get("label") or payload.get("agent_id") or "").strip(),
            "description": str(payload.get("description") or "").strip(),
            "keywords": list(payload.get("keywords") or []),
            "prompt_key": payload.get("prompt_key"),
            "namespace": list(payload.get("namespace") or []),
        }
        for payload in agent_metadata
        if str(payload.get("agent_id") or "").strip()
    ]

    probes: list[dict[str, Any]] = []
    intent_confusions: dict[tuple[str, str], int] = {}
    agent_confusions: dict[tuple[str, str], int] = {}
    tool_confusions: dict[tuple[str, str], int] = {}
    path_confusions: dict[tuple[str, str], int] = {}
    intent_correct_count = 0
    agent_correct_count = 0
    tool_correct_count = 0
    agent_conditional_correct = 0
    agent_conditional_total = 0
    tool_conditional_correct = 0
    tool_conditional_total = 0
    vector_probes_with_candidates = 0
    vector_probes_with_top1_from_vector = 0
    vector_probes_with_top1_vector_only = 0
    vector_probes_with_expected_tool_in_top_k = 0
    vector_probes_with_expected_tool_vector_only = 0
    vector_probes_correct_tool_with_vector_support = 0
    query_candidates_total = 0
    existing_example_candidates = 0
    llm_generated_candidates = 0
    excluded_query_history_count = 0
    excluded_query_duplicate_count = 0
    round_refresh_queries = 0
    anchor_probe_candidates = 0
    final_queries_evaluated = 0
    intent_layer_ms = 0.0
    agent_layer_ms = 0.0
    tool_layer_ms = 0.0
    tool_ranking_top_k = max(2, int(get_vector_recall_top_k()))
    tool_ranking_stats: dict[str, dict[str, float | int]] = {}

    internal_retrieval_limit = max(2, min(int(retrieval_limit or 5), 20))
    max_probe_queries = max(1, min(int(max_queries_per_tool or 6), 20))
    llm_query_count = max(1, min(int(llm_queries_per_tool or 3), 12))
    hard_negative_count = max(0, min(int(hard_negatives_per_tool or 0), 10))
    normalized_probe_parallelism = _normalize_parallelism(probe_generation_parallelism)
    normalized_probe_round = max(1, min(int(probe_round or 1), 1000))
    excluded_query_keys = {
        normalized.casefold()
        for query in list(exclude_probe_queries or [])
        if (normalized := _swedishify_query_text(query))
    }
    normalized_anchor_probes = _normalize_anchor_probe_set(anchor_probe_set)
    selected_tool_ids = {entry.tool_id for entry in selected_entries}
    normalized_anchor_probes = {
        tool_id: queries
        for tool_id, queries in normalized_anchor_probes.items()
        if tool_id in selected_tool_ids and queries
    }
    anchor_probe_mode = bool(normalized_anchor_probes)
    probe_generation_started_at = perf_counter()
    generated_queries_by_tool: dict[str, list[str]] = {}
    if include_llm_generated and not anchor_probe_mode:
        async def _generate_for_entry(entry: ToolIndexEntry) -> tuple[str, list[str]]:
            forbidden_markers = _tool_reference_markers(
                entry,
                neighbors_by_tool.get(entry.tool_id, []),
            )
            seed_examples = [
                normalized
                for query in entry.example_queries[:max_probe_queries]
                if (normalized := _swedishify_query_text(query))
                and _is_valid_probe_query(
                    normalized,
                    forbidden_markers=forbidden_markers,
                )
            ]
            avoid_for_generation = [*list(excluded_query_keys)[:160], *seed_examples[:40]]
            generated = await _generate_probe_queries_for_tool(
                llm=llm,
                entry=entry,
                neighbors=neighbors_by_tool.get(entry.tool_id, []),
                query_count=llm_query_count,
                hard_negatives_per_tool=hard_negative_count,
                avoid_queries=avoid_for_generation,
                round_index=normalized_probe_round,
            )
            return entry.tool_id, list(generated)

        if normalized_probe_parallelism <= 1:
            for entry in selected_entries:
                tool_id, generated = await _generate_for_entry(entry)
                generated_queries_by_tool[tool_id] = generated
        else:
            semaphore = asyncio.Semaphore(normalized_probe_parallelism)

            async def _run_with_limit(entry: ToolIndexEntry) -> tuple[str, list[str]]:
                async with semaphore:
                    return await _generate_for_entry(entry)

            generated_results = await asyncio.gather(
                *[_run_with_limit(entry) for entry in selected_entries]
            )
            for tool_id, generated in generated_results:
                generated_queries_by_tool[tool_id] = list(generated)
    probe_generation_ms = (perf_counter() - probe_generation_started_at) * 1000
    preparation_ms = (probe_generation_started_at - preparation_started_at) * 1000
    evaluation_started_at = perf_counter()

    for entry in selected_entries:
        expected_tool_id = entry.tool_id
        forbidden_markers = _tool_reference_markers(
            entry,
            neighbors_by_tool.get(entry.tool_id, []),
        )
        expected_intent_id = _normalize_text(expected_intent_by_tool.get(expected_tool_id)).lower() or None
        expected_agent_id = _normalize_text(expected_agent_by_tool.get(expected_tool_id)).lower() or None
        queries: list[tuple[str, str]] = []
        if anchor_probe_mode:
            anchored_queries = [
                (query, source)
                for query, source in list(normalized_anchor_probes.get(entry.tool_id) or [])
                if _is_valid_probe_query(
                    query,
                    forbidden_markers=forbidden_markers,
                )
            ]
            queries.extend(anchored_queries)
            anchor_probe_candidates += len(anchored_queries)
            query_candidates_total += len(anchored_queries)
            if not anchored_queries and include_existing_examples:
                # Fallback if a selected tool lacks anchor probes.
                existing_queries = [
                    normalized
                    for query in entry.example_queries[:max_probe_queries]
                    if (normalized := _swedishify_query_text(query))
                    and _is_valid_probe_query(
                        normalized,
                        forbidden_markers=forbidden_markers,
                    )
                ]
                queries.extend(
                    (query, "anchor_existing_fallback")
                    for query in existing_queries
                )
                existing_example_candidates += len(existing_queries)
                query_candidates_total += len(existing_queries)
        else:
            if include_existing_examples:
                existing_queries = [
                    normalized
                    for query in entry.example_queries[:max_probe_queries]
                    if (normalized := _swedishify_query_text(query))
                    and _is_valid_probe_query(
                        normalized,
                        forbidden_markers=forbidden_markers,
                    )
                ]
                queries.extend(
                    (query, "existing_example")
                    for query in existing_queries
                )
                existing_example_candidates += len(existing_queries)
                query_candidates_total += len(existing_queries)
            if include_llm_generated:
                generated = list(generated_queries_by_tool.get(entry.tool_id) or [])
                queries.extend((query, "llm_generated") for query in generated)
                llm_generated_candidates += len(generated)
                query_candidates_total += len(generated)
        queries = _dedupe_queries(queries)
        if queries:
            query_source_by_key = {
                _swedishify_query_text(query).casefold(): source
                for query, source in queries
                if _swedishify_query_text(query)
            }
            ranked_queries = _select_high_quality_probe_queries(
                entry=entry,
                candidates=[query for query, _source in queries],
                query_count=len(queries),
                forbidden_markers=forbidden_markers,
                avoid_keys=None,
            )
            if ranked_queries:
                queries = [
                    (
                        query,
                        query_source_by_key.get(_swedishify_query_text(query).casefold(), "candidate"),
                    )
                    for query in ranked_queries
                ]

        filtered_queries: list[tuple[str, str]] = []
        seen_query_keys: set[str] = set()
        history_exclusion_enabled = not anchor_probe_mode
        for query, source in queries:
            normalized_query = _swedishify_query_text(query)
            key = normalized_query.casefold()
            if (
                not normalized_query
                or key in seen_query_keys
                or (history_exclusion_enabled and key in excluded_query_keys)
                or not _is_valid_probe_query(
                    normalized_query,
                    forbidden_markers=forbidden_markers,
                )
            ):
                if history_exclusion_enabled and key in excluded_query_keys:
                    excluded_query_history_count += 1
                elif key in seen_query_keys:
                    excluded_query_duplicate_count += 1
                continue
            seen_query_keys.add(key)
            filtered_queries.append((normalized_query, source))
            if len(filtered_queries) >= max_probe_queries:
                break

        if len(filtered_queries) < max_probe_queries and not anchor_probe_mode:
            fallback_queries = _fallback_probe_queries(
                entry=entry,
                neighbors=neighbors_by_tool.get(entry.tool_id, []),
                query_count=max_probe_queries * 3,
                hard_negatives_per_tool=hard_negative_count,
                avoid_queries=[*list(excluded_query_keys), *list(seen_query_keys)],
                round_index=normalized_probe_round,
            )
            for query in fallback_queries:
                normalized_query = _swedishify_query_text(query)
                key = normalized_query.casefold()
                if (
                    not normalized_query
                    or key in seen_query_keys
                    or key in excluded_query_keys
                    or not _is_valid_probe_query(
                        normalized_query,
                        forbidden_markers=forbidden_markers,
                    )
                ):
                    continue
                seen_query_keys.add(key)
                filtered_queries.append((normalized_query, "round_refresh"))
                round_refresh_queries += 1
                if len(filtered_queries) >= max_probe_queries:
                    break

        queries = filtered_queries[:max_probe_queries]
        final_queries_evaluated += len(queries)

        for query, source in queries:
            intent_started_at = perf_counter()
            intent_ranked = _rank_metadata_candidates(
                query=query,
                candidates=intent_candidates,
                retrieval_tuning=retrieval_tuning,
                intent_hint=None,
            )
            intent_layer = _layer_result(
                expected_label=expected_intent_id,
                ranked=intent_ranked,
            )
            intent_layer_ms += (perf_counter() - intent_started_at) * 1000
            predicted_intent_id = _normalize_text(intent_layer.get("predicted_label")).lower() or None

            agent_started_at = perf_counter()
            agent_ranked = _rank_metadata_candidates(
                query=query,
                candidates=agent_candidates,
                retrieval_tuning=retrieval_tuning,
                intent_hint=predicted_intent_id,
            )
            agent_layer = _layer_result(
                expected_label=expected_agent_id,
                ranked=agent_ranked,
            )
            agent_layer_ms += (perf_counter() - agent_started_at) * 1000
            predicted_agent_id = _normalize_text(agent_layer.get("predicted_label")).lower() or None

            tool_started_at = perf_counter()
            primary_namespaces, fallback_namespaces = _tool_namespaces_for_agent(
                predicted_agent_id
            )
            predicted_tool_ids, retrieval_breakdown = smart_retrieve_tools_with_breakdown(
                query,
                tool_index=tool_index,
                primary_namespaces=primary_namespaces,
                fallback_namespaces=fallback_namespaces,
                limit=internal_retrieval_limit,
                tuning=retrieval_tuning,
            )
            normalized_predicted_tool_ids = [
                _normalize_text(tool_id) for tool_id in predicted_tool_ids if _normalize_text(tool_id)
            ]
            tool_layer = _tool_layer_result(
                expected_label=expected_tool_id,
                ranked_ids=normalized_predicted_tool_ids,
                retrieval_breakdown=list(retrieval_breakdown),
            )
            predicted_tool_id = _normalize_text(tool_layer.get("predicted_label")) or None
            if expected_tool_id:
                stats = tool_ranking_stats.setdefault(
                    expected_tool_id,
                    {
                        "probes": 0,
                        "top1_hits": 0,
                        "topk_hits": 0,
                        "rank_sum": 0.0,
                        "rank_count": 0,
                        "margin_sum": 0.0,
                        "margin_count": 0,
                    },
                )
                stats["probes"] = int(stats["probes"]) + 1
                if predicted_tool_id == expected_tool_id:
                    stats["top1_hits"] = int(stats["top1_hits"]) + 1
                expected_rank = _to_positive_int_or_none(tool_layer.get("expected_rank"))
                if expected_rank is not None:
                    stats["rank_sum"] = float(stats["rank_sum"]) + float(expected_rank)
                    stats["rank_count"] = int(stats["rank_count"]) + 1
                    if expected_rank <= tool_ranking_top_k:
                        stats["topk_hits"] = int(stats["topk_hits"]) + 1
                expected_margin = tool_layer.get("expected_margin_vs_best_other")
                if isinstance(expected_margin, (float, int)):
                    stats["margin_sum"] = float(stats["margin_sum"]) + float(expected_margin)
                    stats["margin_count"] = int(stats["margin_count"]) + 1
            tool_vector_diagnostics = _tool_vector_diagnostics(
                expected_label=expected_tool_id,
                predicted_label=predicted_tool_id,
                retrieval_breakdown=list(retrieval_breakdown),
            )
            tool_layer_ms += (perf_counter() - tool_started_at) * 1000

            expected_path = _path_label(
                expected_intent_id,
                expected_agent_id,
                expected_tool_id,
            )
            predicted_path = _path_label(
                predicted_intent_id,
                predicted_agent_id,
                predicted_tool_id,
            )
            probe_id = hashlib.sha256(
                f"{expected_tool_id}|{source}|{query}".encode("utf-8")
            ).hexdigest()[:24]

            probes.append(
                {
                    "probe_id": probe_id,
                    "query": query,
                    "source": source,
                    "target_tool_id": expected_tool_id,
                    "expected_path": expected_path,
                    "predicted_path": predicted_path,
                    "intent": intent_layer,
                    "agent": agent_layer,
                    "tool": tool_layer,
                    "tool_vector_diagnostics": tool_vector_diagnostics,
                }
            )

            intent_correct = expected_intent_id is not None and predicted_intent_id == expected_intent_id
            agent_correct = expected_agent_id is not None and predicted_agent_id == expected_agent_id
            tool_correct = predicted_tool_id == expected_tool_id
            if intent_correct:
                intent_correct_count += 1
            if agent_correct:
                agent_correct_count += 1
            if tool_correct:
                tool_correct_count += 1
            if tool_vector_diagnostics.get("vector_selected_ids"):
                vector_probes_with_candidates += 1
            if bool(tool_vector_diagnostics.get("predicted_tool_vector_selected")):
                vector_probes_with_top1_from_vector += 1
            if bool(tool_vector_diagnostics.get("predicted_tool_vector_only")):
                vector_probes_with_top1_vector_only += 1
            if bool(tool_vector_diagnostics.get("expected_tool_vector_selected")):
                vector_probes_with_expected_tool_in_top_k += 1
            if bool(tool_vector_diagnostics.get("expected_tool_vector_only")):
                vector_probes_with_expected_tool_vector_only += 1
            if tool_correct and bool(
                tool_vector_diagnostics.get("predicted_tool_vector_selected")
            ):
                vector_probes_correct_tool_with_vector_support += 1
            if expected_intent_id:
                key = (expected_intent_id, predicted_intent_id or "-")
                intent_confusions[key] = intent_confusions.get(key, 0) + 1
            if expected_agent_id:
                key = (expected_agent_id, predicted_agent_id or "-")
                agent_confusions[key] = agent_confusions.get(key, 0) + 1
            key = (expected_tool_id, predicted_tool_id or "-")
            tool_confusions[key] = tool_confusions.get(key, 0) + 1
            path_key = (expected_path, predicted_path)
            path_confusions[path_key] = path_confusions.get(path_key, 0) + 1

            if intent_correct and expected_agent_id:
                agent_conditional_total += 1
                if agent_correct:
                    agent_conditional_correct += 1
            if intent_correct and agent_correct:
                tool_conditional_total += 1
                if tool_correct:
                    tool_conditional_correct += 1

    evaluation_ms = (perf_counter() - evaluation_started_at) * 1000
    summary_started_at = perf_counter()
    total = len(probes)
    tool_ranking_rows: list[dict[str, Any]] = []
    for tool_id, stats in sorted(tool_ranking_stats.items(), key=lambda item: item[0]):
        probes_for_tool = int(stats.get("probes") or 0)
        if probes_for_tool <= 0:
            continue
        top1_hits = int(stats.get("top1_hits") or 0)
        topk_hits = int(stats.get("topk_hits") or 0)
        rank_count = int(stats.get("rank_count") or 0)
        margin_count = int(stats.get("margin_count") or 0)
        avg_expected_rank = (
            float(stats.get("rank_sum") or 0.0) / rank_count
            if rank_count > 0
            else None
        )
        avg_margin = (
            float(stats.get("margin_sum") or 0.0) / margin_count
            if margin_count > 0
            else None
        )
        tool_ranking_rows.append(
            {
                "tool_id": tool_id,
                "probes": probes_for_tool,
                "top1_hits": top1_hits,
                "topk_hits": topk_hits,
                "top1_rate": (top1_hits / probes_for_tool) if probes_for_tool else 0.0,
                "topk_rate": (topk_hits / probes_for_tool) if probes_for_tool else 0.0,
                "avg_expected_rank": avg_expected_rank,
                "avg_margin_vs_best_other": avg_margin,
            }
        )
    normalized_retrieval_tuning = normalize_retrieval_tuning(retrieval_tuning or {})
    embedding_context_split = get_tool_embedding_context_split_fields()
    summary = {
        "total_probes": total,
        "intent_accuracy": (intent_correct_count / total) if total else 0.0,
        "agent_accuracy": (agent_correct_count / total) if total else 0.0,
        "tool_accuracy": (tool_correct_count / total) if total else 0.0,
        "agent_accuracy_given_intent_correct": (
            (agent_conditional_correct / agent_conditional_total)
            if agent_conditional_total
            else None
        ),
        "tool_accuracy_given_intent_agent_correct": (
            (tool_conditional_correct / tool_conditional_total)
            if tool_conditional_total
            else None
        ),
        "intent_confusion_matrix": _matrix_rows_from_counts(
            intent_confusions,
            expected_key="expected_label",
            predicted_key="predicted_label",
        ),
        "agent_confusion_matrix": _matrix_rows_from_counts(
            agent_confusions,
            expected_key="expected_label",
            predicted_key="predicted_label",
        ),
        "tool_confusion_matrix": _matrix_rows_from_counts(
            tool_confusions,
            expected_key="expected_label",
            predicted_key="predicted_label",
        ),
        "path_confusion_matrix": _matrix_rows_from_counts(
            path_confusions,
            expected_key="expected_path",
            predicted_key="predicted_path",
        ),
        "vector_recall_summary": {
            "top_k": get_vector_recall_top_k(),
            "probes_with_vector_candidates": vector_probes_with_candidates,
            "probes_with_top1_from_vector": vector_probes_with_top1_from_vector,
            "probes_with_top1_vector_only": vector_probes_with_top1_vector_only,
            "probes_with_expected_tool_in_vector_top_k": (
                vector_probes_with_expected_tool_in_top_k
            ),
            "probes_with_expected_tool_vector_only": (
                vector_probes_with_expected_tool_vector_only
            ),
            "probes_with_correct_tool_and_vector_support": (
                vector_probes_correct_tool_with_vector_support
            ),
            "share_probes_with_vector_candidates": (
                (vector_probes_with_candidates / total) if total else 0.0
            ),
            "share_top1_from_vector": (
                (vector_probes_with_top1_from_vector / total) if total else 0.0
            ),
            "share_expected_tool_in_vector_top_k": (
                (vector_probes_with_expected_tool_in_top_k / total) if total else 0.0
            ),
        },
        "tool_ranking_summary": {
            "top_k": int(tool_ranking_top_k),
            "tools": tool_ranking_rows,
        },
        "tool_embedding_context": {
            "enabled": True,
            "context_fields": get_tool_embedding_context_fields(),
            "semantic_fields": list(embedding_context_split.get("semantic") or []),
            "structural_fields": list(embedding_context_split.get("structural") or []),
            "semantic_weight": float(
                getattr(normalized_retrieval_tuning, "semantic_embedding_weight", 0.0)
            ),
            "structural_weight": float(
                getattr(normalized_retrieval_tuning, "structural_embedding_weight", 0.0)
            ),
            "description": (
                "Embeddings ar uppdelade i semantic (namn/beskrivning/keywords/exempel) "
                "och structural (schema/required/example input/output-hint) med viktad fusion."
            ),
        },
    }
    summary_build_ms = (perf_counter() - summary_started_at) * 1000
    total_ms = (perf_counter() - total_started_at) * 1000
    return {
        "probes": probes,
        "summary": summary,
        "diagnostics": {
            "total_ms": round(float(total_ms), 2),
            "preparation_ms": round(float(preparation_ms), 2),
            "probe_generation_ms": round(float(probe_generation_ms), 2),
            "evaluation_ms": round(float(evaluation_ms), 2),
            "intent_layer_ms": round(float(intent_layer_ms), 2),
            "agent_layer_ms": round(float(agent_layer_ms), 2),
            "tool_layer_ms": round(float(tool_layer_ms), 2),
            "summary_build_ms": round(float(summary_build_ms), 2),
            "selected_tools_count": len(selected_entries),
            "intent_candidate_count": len(intent_candidates),
            "agent_candidate_count": len(agent_candidates),
            "query_candidates_total": int(query_candidates_total),
            "existing_example_candidates": int(existing_example_candidates),
            "llm_generated_candidates": int(llm_generated_candidates),
            "round_refresh_queries": int(round_refresh_queries),
            "excluded_query_history_count": int(excluded_query_history_count),
            "excluded_query_duplicate_count": int(excluded_query_duplicate_count),
            "evaluated_queries": int(final_queries_evaluated),
            "excluded_query_pool_size": int(len(excluded_query_keys)),
            "probe_generation_parallelism": int(normalized_probe_parallelism),
            "probe_round": int(normalized_probe_round),
            "anchor_probe_mode": bool(anchor_probe_mode),
            "anchor_probe_candidates": int(anchor_probe_candidates),
            "anchor_probe_tools": int(len(normalized_anchor_probes)),
            "include_existing_examples": bool(include_existing_examples),
            "include_llm_generated": bool(
                include_llm_generated and not anchor_probe_mode
            ),
        },
        "available_intent_ids": sorted(
            {
                _normalize_text(item.get("id")).lower()
                for item in intent_candidates
                if _normalize_text(item.get("id"))
            }
        ),
        "available_agent_ids": sorted(
            {
                _normalize_text(item.get("id")).lower()
                for item in agent_candidates
                if _normalize_text(item.get("id"))
            }
        ),
        "available_tool_ids": sorted(
            {
                _normalize_text(entry.tool_id)
                for entry in selected_entries
                if _normalize_text(entry.tool_id)
            }
        ),
    }


def build_layered_suggestion_inputs_from_annotations(
    *,
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    tool_results: list[dict[str, Any]] = []
    intent_failures: list[dict[str, Any]] = []
    agent_failures: list[dict[str, Any]] = []
    reviewed_intent_failures = 0
    reviewed_agent_failures = 0
    reviewed_tool_failures = 0

    for item in annotations:
        probe_id = _normalize_text(item.get("probe_id")) or hashlib.sha256(
            f"{item.get('query')}|{item.get('expected_tool_id')}".encode("utf-8")
        ).hexdigest()[:24]
        query = _normalize_text(item.get("query"))
        expected_intent = _normalize_text(item.get("expected_intent_id")).lower() or None
        expected_agent = _normalize_text(item.get("expected_agent_id")).lower() or None
        expected_tool = _normalize_text(item.get("expected_tool_id")) or None
        predicted_intent = _normalize_text(item.get("predicted_intent_id")).lower() or None
        predicted_agent = _normalize_text(item.get("predicted_agent_id")).lower() or None
        predicted_tool = _normalize_text(item.get("predicted_tool_id")) or None
        intent_is_correct = bool(item.get("intent_is_correct", True))
        agent_is_correct = bool(item.get("agent_is_correct", True))
        tool_is_correct = bool(item.get("tool_is_correct", True))
        corrected_intent = _normalize_text(item.get("corrected_intent_id")).lower() or None
        corrected_agent = _normalize_text(item.get("corrected_agent_id")).lower() or None
        corrected_tool = _normalize_text(item.get("corrected_tool_id")) or None

        resolved_expected_intent = (
            (corrected_intent or expected_intent) if not intent_is_correct else expected_intent
        )
        resolved_expected_agent = (
            (corrected_agent or expected_agent) if not agent_is_correct else expected_agent
        )
        resolved_expected_tool = (
            (corrected_tool or expected_tool) if not tool_is_correct else expected_tool
        )

        if not intent_is_correct and resolved_expected_intent:
            reviewed_intent_failures += 1
            intent_failures.append(
                {
                    "probe_id": probe_id,
                    "query": query,
                    "expected_intent_id": resolved_expected_intent,
                    "predicted_intent_id": predicted_intent,
                    "score_breakdown": list(item.get("intent_score_breakdown") or []),
                }
            )
        if not agent_is_correct and resolved_expected_agent:
            reviewed_agent_failures += 1
            agent_failures.append(
                {
                    "probe_id": probe_id,
                    "query": query,
                    "expected_agent_id": resolved_expected_agent,
                    "predicted_agent_id": predicted_agent,
                    "score_breakdown": list(item.get("agent_score_breakdown") or []),
                }
            )
        if resolved_expected_tool:
            if not tool_is_correct:
                reviewed_tool_failures += 1
            tool_results.append(
                {
                    "test_id": probe_id,
                    "question": query,
                    "expected_tool": resolved_expected_tool,
                    "selected_tool": predicted_tool,
                    "passed_tool": bool(tool_is_correct),
                    "passed": bool(tool_is_correct),
                    "retrieval_breakdown": list(item.get("tool_score_breakdown") or []),
                    "tool_vector_diagnostics": dict(
                        item.get("tool_vector_diagnostics") or {}
                    ),
                }
            )
    return {
        "tool_results": tool_results,
        "intent_failures": intent_failures,
        "agent_failures": agent_failures,
        "reviewed_intent_failures": reviewed_intent_failures,
        "reviewed_agent_failures": reviewed_agent_failures,
        "reviewed_tool_failures": reviewed_tool_failures,
    }


def _intent_metadata_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_norm = normalize_intent_definition_payload(
        left,
        intent_id=left.get("intent_id"),
    )
    right_norm = normalize_intent_definition_payload(
        right,
        intent_id=right.get("intent_id"),
    )
    return left_norm == right_norm


def _agent_metadata_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_norm = normalize_agent_metadata_payload(
        left,
        agent_id=left.get("agent_id"),
    )
    right_norm = normalize_agent_metadata_payload(
        right,
        agent_id=right.get("agent_id"),
    )
    return left_norm == right_norm


def _fallback_intent_metadata_suggestion(
    *,
    current: dict[str, Any],
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    token_counts: dict[str, int] = {}
    wrong_intents: set[str] = set()
    for failure in failures:
        query = _normalize_text(failure.get("query"))
        for token in _tokenize(query):
            token_counts[token] = token_counts.get(token, 0) + 1
        wrong_intent = _normalize_text(failure.get("predicted_intent_id")).lower()
        if wrong_intent and wrong_intent != _normalize_text(current.get("intent_id")).lower():
            wrong_intents.add(wrong_intent)
    keywords = _safe_string_list(current.get("keywords"))
    seen = {keyword.casefold() for keyword in keywords}
    for token, _count in sorted(token_counts.items(), key=lambda item: item[1], reverse=True):
        if token.casefold() in seen:
            continue
        keywords.append(token)
        seen.add(token.casefold())
        if len(keywords) >= METADATA_MAX_KEYWORDS:
            break
    description = _normalize_text(current.get("description"))
    if wrong_intents:
        marker = f"Skilj tydligt mot intent: {', '.join(sorted(wrong_intents)[:4])}."
        if marker not in description:
            description = f"{description} {marker}".strip()
    proposed = {
        "intent_id": _normalize_text(current.get("intent_id")).lower(),
        "label": _normalize_text(current.get("label")) or _normalize_text(current.get("intent_id")).title(),
        "route": _normalize_text(current.get("route")).lower() or "knowledge",
        "description": description,
        "keywords": keywords,
        "priority": int(current.get("priority") or 500),
        "enabled": bool(current.get("enabled", True)),
    }
    proposed = enforce_metadata_limits(proposed)
    rationale = (
        "Metadataforslag baserat pa granskade intent-kollisioner: "
        "forstarkt nyckelord och tydligare avgransning mot forvaxlade intents."
    )
    return proposed, rationale


def _fallback_agent_metadata_suggestion(
    *,
    current: dict[str, Any],
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    token_counts: dict[str, int] = {}
    wrong_agents: set[str] = set()
    for failure in failures:
        query = _normalize_text(failure.get("query"))
        for token in _tokenize(query):
            token_counts[token] = token_counts.get(token, 0) + 1
        wrong_agent = _normalize_text(failure.get("predicted_agent_id")).lower()
        if wrong_agent and wrong_agent != _normalize_text(current.get("agent_id")).lower():
            wrong_agents.add(wrong_agent)
    keywords = _safe_string_list(current.get("keywords"))
    seen = {keyword.casefold() for keyword in keywords}
    for token, _count in sorted(token_counts.items(), key=lambda item: item[1], reverse=True):
        if token.casefold() in seen:
            continue
        keywords.append(token)
        seen.add(token.casefold())
        if len(keywords) >= METADATA_MAX_KEYWORDS:
            break
    description = _normalize_text(current.get("description"))
    if wrong_agents:
        marker = f"Skilj tydligt mot agenter: {', '.join(sorted(wrong_agents)[:4])}."
        if marker not in description:
            description = f"{description} {marker}".strip()
    proposed = {
        "agent_id": _normalize_text(current.get("agent_id")).lower(),
        "label": _normalize_text(current.get("label")) or _normalize_text(current.get("agent_id")).title(),
        "description": description,
        "keywords": keywords,
        "prompt_key": _normalize_text(current.get("prompt_key")) or None,
        "namespace": _safe_string_list(current.get("namespace")),
    }
    proposed = enforce_metadata_limits(proposed)
    rationale = (
        "Metadataforslag baserat pa granskade agent-kollisioner: "
        "forstarkt nyckelord och tydligare avgransning mot forvaxlade agenter."
    )
    return proposed, rationale


async def _build_llm_intent_metadata_suggestion(
    *,
    llm: Any,
    current: dict[str, Any],
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], str] | None:
    if llm is None:
        return None
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    prompt = (
        "Du optimerar intent-metadata for retrieval-only.\n"
        "Forbattra enbart metadatafalten (label, route, description, keywords, priority, enabled).\n"
        "Inga prompt-forslag och ingen analys av pipeline-steg.\n"
        "Returnera strikt JSON:\n"
        "{\n"
        '  "label": "string",\n'
        '  "route": "knowledge|action|statistics|compare|smalltalk",\n'
        '  "description": "string pa svenska",\n'
        '  "keywords": ["svenska termer"],\n'
        '  "priority": 100,\n'
        '  "enabled": true,\n'
        '  "rationale": "kort motivering pa svenska"\n'
        "}\n"
        f"Begränsningar: beskrivning max {METADATA_MAX_DESCRIPTION_CHARS} tecken, keywords max {METADATA_MAX_KEYWORDS} stycken.\n"
        "Ingen markdown."
    )
    payload = {
        "current_metadata": current,
        "reviewed_failures": _compact_failures_for_llm(
            failures,
            max_items=_MAX_INTENT_FAILURES_FOR_LLM,
        ),
    }
    try:
        response = await asyncio.wait_for(
            model.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
                ]
            ),
            timeout=_METADATA_LAYER_LLM_TIMEOUT_SECONDS,
        )
        parsed = _extract_json_object(
            _response_content_to_text(getattr(response, "content", ""))
        )
        if not parsed:
            return None
        proposed = {
            "intent_id": _normalize_text(current.get("intent_id")).lower(),
            "label": _normalize_text(parsed.get("label")) or _normalize_text(current.get("label")),
            "route": _normalize_text(parsed.get("route")).lower()
            or _normalize_text(current.get("route")).lower(),
            "description": _normalize_text(parsed.get("description")) or _normalize_text(current.get("description")),
            "keywords": _safe_string_list(parsed.get("keywords")) or _safe_string_list(current.get("keywords")),
            "priority": int(parsed.get("priority") or current.get("priority") or 500),
            "enabled": bool(parsed.get("enabled", current.get("enabled", True))),
        }
        rationale = _normalize_text(parsed.get("rationale")) or (
            "LLM-forslag for intent-metadata baserat pa granskade retrieval-fall."
        )
        return proposed, rationale
    except Exception:
        return None


async def _build_llm_agent_metadata_suggestion(
    *,
    llm: Any,
    current: dict[str, Any],
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], str] | None:
    if llm is None:
        return None
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    prompt = (
        "Du optimerar agent-metadata for retrieval-only.\n"
        "Forbattra enbart metadatafalten (label, description, keywords).\n"
        "Inga prompt-forslag och ingen analys av pipeline-steg.\n"
        "Returnera strikt JSON:\n"
        "{\n"
        '  "label": "string",\n'
        '  "description": "string pa svenska",\n'
        '  "keywords": ["svenska termer"],\n'
        '  "rationale": "kort motivering pa svenska"\n'
        "}\n"
        f"Begränsningar: beskrivning max {METADATA_MAX_DESCRIPTION_CHARS} tecken, keywords max {METADATA_MAX_KEYWORDS} stycken.\n"
        "Ingen markdown."
    )
    payload = {
        "current_metadata": current,
        "reviewed_failures": _compact_failures_for_llm(
            failures,
            max_items=_MAX_AGENT_FAILURES_FOR_LLM,
        ),
    }
    try:
        response = await asyncio.wait_for(
            model.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
                ]
            ),
            timeout=_METADATA_LAYER_LLM_TIMEOUT_SECONDS,
        )
        parsed = _extract_json_object(
            _response_content_to_text(getattr(response, "content", ""))
        )
        if not parsed:
            return None
        proposed = {
            "agent_id": _normalize_text(current.get("agent_id")).lower(),
            "label": _normalize_text(parsed.get("label")) or _normalize_text(current.get("label")),
            "description": _normalize_text(parsed.get("description")) or _normalize_text(current.get("description")),
            "keywords": _safe_string_list(parsed.get("keywords")) or _safe_string_list(current.get("keywords")),
            "prompt_key": _normalize_text(current.get("prompt_key")) or None,
            "namespace": _safe_string_list(current.get("namespace")),
        }
        rationale = _normalize_text(parsed.get("rationale")) or (
            "LLM-forslag for agent-metadata baserat pa granskade retrieval-fall."
        )
        return proposed, rationale
    except Exception:
        return None


async def generate_intent_metadata_suggestions_from_annotations(
    *,
    intent_definitions: list[dict[str, Any]],
    intent_failures: list[dict[str, Any]],
    llm: Any,
    max_suggestions: int = 20,
    parallelism: int = 1,
) -> list[dict[str, Any]]:
    definitions_by_id = {
        _normalize_text(item.get("intent_id")).lower(): normalize_intent_definition_payload(
            item,
            intent_id=item.get("intent_id"),
        )
        for item in intent_definitions
        if _normalize_text(item.get("intent_id"))
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for failure in intent_failures:
        expected_intent_id = _normalize_text(failure.get("expected_intent_id")).lower()
        if not expected_intent_id:
            continue
        grouped.setdefault(expected_intent_id, []).append(failure)
    normalized_max_suggestions = max(1, int(max_suggestions))
    normalized_parallelism = _normalize_parallelism(parallelism)
    candidate_items = list(grouped.items())

    async def _suggest_for_intent(
        intent_id: str,
        failures: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        current = definitions_by_id.get(intent_id) or normalize_intent_definition_payload(
            {"intent_id": intent_id},
            intent_id=intent_id,
        )
        fallback_proposed, fallback_rationale = _fallback_intent_metadata_suggestion(
            current=current,
            failures=failures,
        )
        llm_result = await _build_llm_intent_metadata_suggestion(
            llm=llm,
            current=current,
            failures=failures,
        )
        if llm_result is None:
            proposed = fallback_proposed
            rationale = fallback_rationale
        else:
            proposed, rationale = llm_result
        proposed = normalize_intent_definition_payload(
            proposed,
            intent_id=intent_id,
        )
        if _intent_metadata_equal(current, proposed):
            return None
        return {
            "intent_id": intent_id,
            "failed_probe_ids": [
                _normalize_text(item.get("probe_id"))
                for item in failures
                if _normalize_text(item.get("probe_id"))
            ],
            "rationale": rationale,
            "current_metadata": {
                "intent_id": intent_id,
                "label": current.get("label"),
                "route": current.get("route"),
                "description": current.get("description"),
                "keywords": list(current.get("keywords") or []),
                "priority": int(current.get("priority") or 500),
                "enabled": bool(current.get("enabled", True)),
            },
            "proposed_metadata": {
                "intent_id": intent_id,
                "label": proposed.get("label"),
                "route": proposed.get("route"),
                "description": proposed.get("description"),
                "keywords": list(proposed.get("keywords") or []),
                "priority": int(proposed.get("priority") or 500),
                "enabled": bool(proposed.get("enabled", True)),
            },
        }

    suggestions: list[dict[str, Any]] = []
    if normalized_parallelism <= 1:
        for intent_id, failures in candidate_items:
            suggestion = await _suggest_for_intent(intent_id, failures)
            if suggestion is None:
                continue
            suggestions.append(suggestion)
            if len(suggestions) >= normalized_max_suggestions:
                break
    else:
        semaphore = asyncio.Semaphore(normalized_parallelism)

        async def _run_with_limit(
            intent_id: str,
            failures: list[dict[str, Any]],
        ) -> dict[str, Any] | None:
            async with semaphore:
                return await _suggest_for_intent(intent_id, failures)

        for start in range(0, len(candidate_items), normalized_parallelism):
            chunk = candidate_items[start : start + normalized_parallelism]
            chunk_results = await asyncio.gather(
                *[_run_with_limit(intent_id, failures) for intent_id, failures in chunk]
            )
            for item in chunk_results:
                if item is None:
                    continue
                suggestions.append(item)
                if len(suggestions) >= normalized_max_suggestions:
                    break
            if len(suggestions) >= normalized_max_suggestions:
                break

    return suggestions[:normalized_max_suggestions]


async def generate_agent_metadata_suggestions_from_annotations(
    *,
    agent_metadata: list[dict[str, Any]],
    agent_failures: list[dict[str, Any]],
    llm: Any,
    max_suggestions: int = 20,
    parallelism: int = 1,
) -> list[dict[str, Any]]:
    metadata_by_id = {
        _normalize_text(item.get("agent_id")).lower(): normalize_agent_metadata_payload(
            item,
            agent_id=item.get("agent_id"),
        )
        for item in agent_metadata
        if _normalize_text(item.get("agent_id"))
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for failure in agent_failures:
        expected_agent_id = _normalize_text(failure.get("expected_agent_id")).lower()
        if not expected_agent_id:
            continue
        grouped.setdefault(expected_agent_id, []).append(failure)
    normalized_max_suggestions = max(1, int(max_suggestions))
    normalized_parallelism = _normalize_parallelism(parallelism)
    candidate_items = list(grouped.items())

    async def _suggest_for_agent(
        agent_id: str,
        failures: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        current = metadata_by_id.get(agent_id) or normalize_agent_metadata_payload(
            {"agent_id": agent_id},
            agent_id=agent_id,
        )
        fallback_proposed, fallback_rationale = _fallback_agent_metadata_suggestion(
            current=current,
            failures=failures,
        )
        llm_result = await _build_llm_agent_metadata_suggestion(
            llm=llm,
            current=current,
            failures=failures,
        )
        if llm_result is None:
            proposed = fallback_proposed
            rationale = fallback_rationale
        else:
            proposed, rationale = llm_result
        proposed = normalize_agent_metadata_payload(
            proposed,
            agent_id=agent_id,
        )
        if _agent_metadata_equal(current, proposed):
            return None
        return {
            "agent_id": agent_id,
            "failed_probe_ids": [
                _normalize_text(item.get("probe_id"))
                for item in failures
                if _normalize_text(item.get("probe_id"))
            ],
            "rationale": rationale,
            "current_metadata": {
                "agent_id": agent_id,
                "label": current.get("label"),
                "description": current.get("description"),
                "keywords": list(current.get("keywords") or []),
                "prompt_key": current.get("prompt_key"),
                "namespace": list(current.get("namespace") or []),
            },
            "proposed_metadata": {
                "agent_id": agent_id,
                "label": proposed.get("label"),
                "description": proposed.get("description"),
                "keywords": list(proposed.get("keywords") or []),
                "prompt_key": proposed.get("prompt_key"),
                "namespace": list(proposed.get("namespace") or []),
            },
        }

    suggestions: list[dict[str, Any]] = []
    if normalized_parallelism <= 1:
        for agent_id, failures in candidate_items:
            suggestion = await _suggest_for_agent(agent_id, failures)
            if suggestion is None:
                continue
            suggestions.append(suggestion)
            if len(suggestions) >= normalized_max_suggestions:
                break
    else:
        semaphore = asyncio.Semaphore(normalized_parallelism)

        async def _run_with_limit(
            agent_id: str,
            failures: list[dict[str, Any]],
        ) -> dict[str, Any] | None:
            async with semaphore:
                return await _suggest_for_agent(agent_id, failures)

        for start in range(0, len(candidate_items), normalized_parallelism):
            chunk = candidate_items[start : start + normalized_parallelism]
            chunk_results = await asyncio.gather(
                *[_run_with_limit(agent_id, failures) for agent_id, failures in chunk]
            )
            for item in chunk_results:
                if item is None:
                    continue
                suggestions.append(item)
                if len(suggestions) >= normalized_max_suggestions:
                    break
            if len(suggestions) >= normalized_max_suggestions:
                break

    return suggestions[:normalized_max_suggestions]
