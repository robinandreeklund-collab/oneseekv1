from __future__ import annotations

import asyncio
from collections import Counter
import json
import re
from hashlib import sha256
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from app.agents.new_chat.action_router import ActionRoute, dispatch_action_route
from app.agents.new_chat.bigtool_store import (
    ToolIndexEntry,
    get_tool_embedding_context_fields,
    get_vector_recall_top_k,
    normalize_retrieval_tuning,
    smart_retrieve_tools_with_breakdown,
)
from app.agents.new_chat.dispatcher import dispatch_route_with_trace
from app.agents.new_chat.hybrid_state import (
    GRAPH_COMPLEXITY_COMPLEX,
    GRAPH_COMPLEXITY_SIMPLE,
    GRAPH_COMPLEXITY_TRIVIAL,
    classify_graph_complexity,
)
from app.agents.new_chat.knowledge_router import KnowledgeRoute, dispatch_knowledge_route
from app.agents.new_chat.nodes.execution_router import (
    EXECUTION_STRATEGY_INLINE,
    EXECUTION_STRATEGY_PARALLEL,
    EXECUTION_STRATEGY_SUBAGENT,
    classify_execution_strategy,
)
from app.agents.new_chat.routing import Route
from app.agents.new_chat.skolverket_tools import SKOLVERKET_TOOL_DEFINITIONS

_SUGGESTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "att",
    "av",
    "be",
    "de",
    "den",
    "det",
    "do",
    "en",
    "ett",
    "for",
    "fran",
    "för",
    "from",
    "har",
    "hur",
    "i",
    "in",
    "is",
    "kan",
    "med",
    "och",
    "om",
    "on",
    "som",
    "the",
    "this",
    "to",
    "vad",
    "vilka",
}
_ENGLISH_SIGNAL_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "should",
    "return",
    "tool",
    "route",
    "prompt",
    "improvement",
    "based",
    "failed",
    "cases",
    "weights",
}
_SWEDISH_SIGNAL_WORDS = {
    "och",
    "för",
    "från",
    "ska",
    "verktyg",
    "fråga",
    "frågor",
    "rutt",
    "väg",
    "svenska",
    "förslag",
    "prompt",
    "utvärdering",
}
_EVAL_AGENT_CHOICES = (
    "statistik",
    "riksdagen",
    "väder",
    "trafik",
    "bolag",
    "marknad",
    "kartor",
    "media",
    "webb",
    "kunskap",
    "åtgärd",
    "syntes",
)

_EVAL_AGENT_DESCRIPTIONS: dict[str, str] = {
    "statistik": "SCB/statistik och officiell data i Sverige.",
    "riksdagen": "Riksdagens öppna data och politiska dokument.",
    "väder": "SMHI-väderprognoser och väderkontext för svenska orter.",
    "trafik": "Trafik, vägar, incidenter, järnväg och transport.",
    "bolag": "Bolagsverket och företagsregister.",
    "marknad": "Blocket/Tradera marknadsplatssökning och prisjämförelse.",
    "kartor": "Geospatial/kartor/geokodning.",
    "media": "Podcast och media-generering.",
    "webb": "Webbsökning, URL-scraping och siduppslag.",
    "kunskap": "Kunskapssökning i docs/interna/externa källor.",
    "åtgärd": "Generella åtgärder som inte täcks av specialistagenter.",
    "syntes": "Jämförelse och syntes från flera källor och modeller.",
}
_DIFFICULTY_ORDER = ("lätt", "medel", "svår")
_GRAPH_COMPLEXITY_VALUES = {
    GRAPH_COMPLEXITY_TRIVIAL,
    GRAPH_COMPLEXITY_SIMPLE,
    GRAPH_COMPLEXITY_COMPLEX,
}
_EXECUTION_STRATEGY_VALUES = {
    EXECUTION_STRATEGY_INLINE,
    EXECUTION_STRATEGY_PARALLEL,
    EXECUTION_STRATEGY_SUBAGENT,
}
_SKOLVERKET_TOOL_CATEGORY_BY_ID: dict[str, str] = {
    str(definition.tool_id).strip().lower(): str(definition.category or "").strip().lower()
    for definition in SKOLVERKET_TOOL_DEFINITIONS
    if str(definition.tool_id or "").strip()
}
_SKOLVERKET_TOOL_IDS = set(_SKOLVERKET_TOOL_CATEGORY_BY_ID.keys())
_MAX_TOOL_FAILURES_FOR_LLM = 18
_TOOL_METADATA_LLM_TIMEOUT_SECONDS = 20.0
_TOOL_ID_LIKE_RE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b", re.IGNORECASE)


def compute_metadata_version_hash(tool_index: list[ToolIndexEntry]) -> str:
    material = [
        {
            "tool_id": entry.tool_id,
            "name": entry.name,
            "description": entry.description,
            "keywords": list(entry.keywords),
            "example_queries": list(entry.example_queries),
            "category": entry.category,
            "base_path": entry.base_path,
        }
        for entry in sorted(tool_index, key=lambda item: item.tool_id)
    ]
    encoded = json.dumps(material, ensure_ascii=True, sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = stripped[start : end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _response_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content or "")


def _safe_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


def _tool_reference_markers_for_suggestions(
    *,
    tool_id: str | None,
    tool_name: str | None,
) -> set[str]:
    markers: set[str] = set()

    def _add(raw: Any) -> None:
        value = str(raw or "").strip().casefold()
        if len(value) < 3:
            return
        compact = " ".join(value.split())
        if compact:
            markers.add(compact)
        if "_" in compact:
            markers.add(compact.replace("_", " "))
            markers.add(compact.replace("_", "-"))

    _add(tool_id)
    _add(tool_name)
    return markers


def _contains_forbidden_tool_reference(
    value: str,
    *,
    forbidden_markers: set[str],
) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return False
    if _TOOL_ID_LIKE_RE.search(text):
        return True
    for marker in forbidden_markers:
        if marker and marker in text:
            return True
    return False


def _sanitize_example_queries_no_tool_refs(
    values: list[str],
    *,
    forbidden_markers: set[str],
) -> list[str]:
    sanitized: list[str] = []
    seen: set[str] = set()
    for raw in list(values or []):
        text = str(raw or "").strip()
        if not text:
            continue
        if _contains_forbidden_tool_reference(text, forbidden_markers=forbidden_markers):
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        sanitized.append(text)
    return sanitized


def _normalize_difficulty_value(value: Any) -> str | None:
    lowered = str(value or "").strip().casefold()
    if not lowered:
        return None
    mapping = {
        "lätt": "lätt",
        "latt": "lätt",
        "easy": "lätt",
        "medel": "medel",
        "medium": "medel",
        "normal": "medel",
        "svår": "svår",
        "svar": "svår",
        "hard": "svår",
    }
    return mapping.get(lowered)


def _update_difficulty_bucket(
    *,
    difficulty_buckets: dict[str, dict[str, Any]],
    difficulty: str | None,
    passed: bool,
    gated_score: float | None,
) -> None:
    if not difficulty:
        return
    bucket = difficulty_buckets.setdefault(
        difficulty,
        {"total_tests": 0, "passed_tests": 0, "gated_scores": []},
    )
    bucket["total_tests"] = int(bucket.get("total_tests") or 0) + 1
    if passed:
        bucket["passed_tests"] = int(bucket.get("passed_tests") or 0) + 1
    if gated_score is not None:
        bucket_scores = bucket.get("gated_scores")
        if not isinstance(bucket_scores, list):
            bucket_scores = []
            bucket["gated_scores"] = bucket_scores
        bucket_scores.append(float(gated_score))


def _build_difficulty_breakdown(
    difficulty_buckets: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    order_map = {name: idx for idx, name in enumerate(_DIFFICULTY_ORDER)}
    rows: list[dict[str, Any]] = []
    for difficulty, bucket in sorted(
        difficulty_buckets.items(),
        key=lambda pair: (order_map.get(pair[0], 999), pair[0]),
    ):
        total_tests = int(bucket.get("total_tests") or 0)
        passed_tests = int(bucket.get("passed_tests") or 0)
        gated_scores = bucket.get("gated_scores") if isinstance(bucket.get("gated_scores"), list) else []
        rows.append(
            {
                "difficulty": difficulty,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "success_rate": (passed_tests / total_tests) if total_tests else 0.0,
                "gated_success_rate": (
                    sum(float(score) for score in gated_scores) / len(gated_scores)
                    if gated_scores
                    else None
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Per-namespace confusion matrix
# ---------------------------------------------------------------------------

def build_namespace_confusion_matrix(
    evaluation_results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build a confusion matrix grouped by namespace prefix.

    Returns a dict keyed by namespace prefix (e.g. "trafikverket_trafikinfo"),
    each containing:
        - ``matrix``: dict[expected_tool, dict[predicted_tool, count]]
        - ``tools``: sorted list of tool IDs in this namespace
        - ``accuracy``: per-tool accuracy dict
        - ``total``: total test cases in this namespace
        - ``correct``: correct predictions
    """
    # Collect (expected, predicted) pairs and infer namespace from tool_id.
    pairs: list[tuple[str, str, str]] = []  # (namespace_prefix, expected, predicted)
    for result in evaluation_results:
        expected = str(result.get("expected_tool") or "").strip()
        predicted = str(result.get("selected_tool") or "").strip()
        if not expected:
            continue
        # Derive namespace prefix from tool_id: e.g. "trafikverket_trafikinfo_koer" → "trafikverket_trafikinfo"
        parts = expected.split("_")
        if len(parts) >= 3:
            ns_prefix = "_".join(parts[:2])
        elif len(parts) == 2:
            ns_prefix = parts[0]
        else:
            ns_prefix = expected
        pairs.append((ns_prefix, expected, predicted or "(none)"))

    # Group by namespace prefix.
    from collections import defaultdict
    ns_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ns_prefix, expected, predicted in pairs:
        ns_groups[ns_prefix].append((expected, predicted))

    # Only build matrices for namespaces with ≥2 distinct expected tools
    # (single-tool namespaces cannot have intra-namespace confusion).
    matrices: dict[str, dict[str, Any]] = {}
    for ns_prefix, group_pairs in sorted(ns_groups.items()):
        distinct_expected = {e for e, _ in group_pairs}
        if len(distinct_expected) < 2:
            continue
        all_tools = sorted({t for pair in group_pairs for t in pair})
        matrix: dict[str, dict[str, int]] = {
            tool: {t: 0 for t in all_tools} for tool in distinct_expected
        }
        for expected, predicted in group_pairs:
            if predicted in matrix.get(expected, {}):
                matrix[expected][predicted] += 1
            else:
                matrix.setdefault(expected, {})[predicted] = (
                    matrix.get(expected, {}).get(predicted, 0) + 1
                )
        total = len(group_pairs)
        correct = sum(1 for e, p in group_pairs if e == p)
        per_tool_accuracy: dict[str, float] = {}
        for tool in distinct_expected:
            tool_total = sum(matrix.get(tool, {}).values())
            tool_correct = matrix.get(tool, {}).get(tool, 0)
            per_tool_accuracy[tool] = (
                (tool_correct / tool_total) if tool_total > 0 else 0.0
            )
        matrices[ns_prefix] = {
            "matrix": matrix,
            "tools": all_tools,
            "accuracy": per_tool_accuracy,
            "total": total,
            "correct": correct,
            "overall_accuracy": (correct / total) if total > 0 else 0.0,
        }
    return matrices


# ---------------------------------------------------------------------------
# Contrastive probe generation
# ---------------------------------------------------------------------------

def generate_contrastive_probes(
    tool_index: list[ToolIndexEntry],
    *,
    max_probes_per_pair: int = 2,
    max_total: int = 200,
) -> list[dict[str, Any]]:
    """Generate contrastive test probes for tool pairs that share a namespace.

    For every pair of tools (A, B) that belong to the same namespace cluster
    (based on the first two segments of tool_id), generates probe entries that
    include an ``expected_tool`` and a ``hard_negative`` — the most likely
    wrong tool.

    Each probe uses the example_queries of tool A with hard_negative = tool B
    and vice versa, which tests the system's ability to discriminate between
    close neighbours.

    Returns a list of eval-compatible test case dicts::

        {
            "id": "contrastive-{tool_a}-vs-{tool_b}-{idx}",
            "question": str,
            "difficulty": "svår",
            "expected": {
                "tool": tool_a_id,
            },
            "hard_negative": tool_b_id,
            "discriminating_signal": str,
            "allowed_tools": [tool_a_id, tool_b_id],
        }
    """
    from collections import defaultdict

    # Group tools by namespace prefix (first 2 segments of tool_id).
    ns_groups: dict[str, list[ToolIndexEntry]] = defaultdict(list)
    for entry in tool_index:
        parts = entry.tool_id.split("_")
        if len(parts) >= 3:
            prefix = "_".join(parts[:2])
        elif len(parts) == 2:
            prefix = parts[0]
        else:
            continue
        ns_groups[prefix].append(entry)

    probes: list[dict[str, Any]] = []
    for _ns_prefix, entries in sorted(ns_groups.items()):
        if len(entries) < 2:
            continue
        for i, entry_a in enumerate(entries):
            for entry_b in entries[i + 1 :]:
                # Generate probes from A's examples testing against B
                a_examples = list(entry_a.example_queries or [])[:max_probes_per_pair]
                b_examples = list(entry_b.example_queries or [])[:max_probes_per_pair]
                a_unique_kw = set(entry_a.keywords or []) - set(entry_b.keywords or [])
                b_unique_kw = set(entry_b.keywords or []) - set(entry_a.keywords or [])
                signal = (
                    f"{entry_a.tool_id} keywords: {', '.join(list(a_unique_kw)[:4])} "
                    f"vs {entry_b.tool_id} keywords: {', '.join(list(b_unique_kw)[:4])}"
                )
                for idx, question in enumerate(a_examples):
                    probes.append(
                        {
                            "id": f"contrastive-{entry_a.tool_id}-vs-{entry_b.tool_id}-{idx}",
                            "question": question,
                            "difficulty": "svår",
                            "expected": {"tool": entry_a.tool_id},
                            "hard_negative": entry_b.tool_id,
                            "discriminating_signal": signal,
                            "allowed_tools": [entry_a.tool_id, entry_b.tool_id],
                        }
                    )
                    if len(probes) >= max_total:
                        return probes
                for idx, question in enumerate(b_examples):
                    probes.append(
                        {
                            "id": f"contrastive-{entry_b.tool_id}-vs-{entry_a.tool_id}-{idx}",
                            "question": question,
                            "difficulty": "svår",
                            "expected": {"tool": entry_b.tool_id},
                            "hard_negative": entry_a.tool_id,
                            "discriminating_signal": signal,
                            "allowed_tools": [entry_a.tool_id, entry_b.tool_id],
                        }
                    )
                    if len(probes) >= max_total:
                        return probes
    return probes


def _looks_english_text(text: str) -> bool:
    tokens = re.findall(r"[a-zA-ZåäöÅÄÖ]{3,}", str(text or "").lower())
    if not tokens:
        return False
    english_hits = sum(1 for token in tokens if token in _ENGLISH_SIGNAL_WORDS)
    swedish_hits = sum(
        1 for token in tokens if token in _SWEDISH_SIGNAL_WORDS or any(ch in token for ch in "åäö")
    )
    return english_hits >= 2 and english_hits > swedish_hits


def _prefer_swedish_text(text: str, fallback: str) -> str:
    candidate = str(text or "").strip()
    fallback_text = str(fallback or "").strip()
    if not candidate:
        return fallback_text
    if _looks_english_text(candidate) and fallback_text:
        return fallback_text
    return candidate


def _has_retrieval_refresh_rule(text: str) -> bool:
    lowered = str(text or "").casefold()
    if not lowered:
        return False
    return any(
        token in lowered
        for token in (
            "retrieve_agents() igen",
            "retrieve_tools() igen",
            "kör retrieve_agents() igen",
            "kör retrieve_tools igen",
            "gor ny retrieve_agents",
            "gör ny retrieve_agents",
            "gor ny retrieve_tools",
            "gör ny retrieve_tools",
            "ny retrieval",
            "frågan byter ämne",
            "fragan byter amne",
            "frågan byter riktning",
            "fragan byter riktning",
            "inte matchar",
            "inte kan lösa",
            "inte kan losa",
        )
    )


def _apply_prompt_architecture_guard(
    *,
    prompt_key: str,
    prompt_text: str,
) -> tuple[str, list[str], bool]:
    cleaned = str(prompt_text or "").strip()
    if not cleaned:
        return cleaned, ["Tom prompt saknar innehåll."], True

    violations: list[str] = []
    severe = False
    lowered = cleaned.casefold()

    def _append_once(line: str) -> None:
        nonlocal cleaned, lowered
        if line.casefold() in lowered:
            return
        cleaned = f"{cleaned.rstrip()}\n{line}"
        lowered = cleaned.casefold()

    if prompt_key == "agent.supervisor.system":
        bullet_count = len(re.findall(r"(?m)^\s*[-*]\s+", cleaned))
        if "tillgängliga agenter" in lowered and bullet_count >= 4:
            violations.append(
                "Förslag innehåller statisk agentlista i supervisor-prompt."
            )
            severe = True
        if "retrieve_agents" not in lowered:
            violations.append(
                "Förslag saknar retrieve_agents() för dynamiskt agentval."
            )
            _append_once(
                "- Hämta kandidat-agenter dynamiskt via retrieve_agents() och välj därifrån."
            )
        if not _has_retrieval_refresh_rule(cleaned):
            violations.append(
                "Förslag saknar regel för ny retrieve_agents() vid mismatch/ämnesbyte."
            )
            _append_once(
                "- Om vald agent inte kan lösa uppgiften eller frågan byter riktning/ämne: kör retrieve_agents() igen innan nästa delegering."
            )
    elif prompt_key.startswith("agent.") or prompt_key.startswith("tool."):
        if "retrieve_tools" not in lowered:
            violations.append(
                "Förslag saknar retrieve_tools() för dynamiskt verktygsval."
            )
            _append_once(
                "- Använd retrieve_tools för dynamiskt verktygsval i aktuell kontext."
            )
        if not _has_retrieval_refresh_rule(cleaned):
            violations.append(
                "Förslag saknar regel för ny retrieve_tools() vid mismatch/ämnesbyte."
            )
            _append_once(
                "- Om tillgängliga verktyg inte kan lösa uppgiften eller frågan byter ämne: kör retrieve_tools igen med omformulerad intent."
            )

    return cleaned, violations, severe


def _normalize_route_value(value: Any) -> str | None:
    route = str(value or "").strip().lower()
    if route in {Route.KUNSKAP.value, Route.SKAPANDE.value, Route.KONVERSATION.value, Route.JAMFORELSE.value}:
        return route
    # Backward compat: map old English names to new Swedish values
    _COMPAT: dict[str, str] = {
        "knowledge": Route.KUNSKAP.value,
        "action": Route.SKAPANDE.value,
        "smalltalk": Route.KONVERSATION.value,
        "compare": Route.JAMFORELSE.value,
        "statistics": Route.KUNSKAP.value,
        "statistik": Route.KUNSKAP.value,
    }
    return _COMPAT.get(route)


def _normalize_sub_route_value(value: Any) -> str | None:
    sub_route = str(value or "").strip().lower()
    if sub_route in {
        ActionRoute.WEB.value,
        ActionRoute.MEDIA.value,
        ActionRoute.TRAVEL.value,
        ActionRoute.DATA.value,
        KnowledgeRoute.DOCS.value,
        KnowledgeRoute.INTERNAL.value,
        KnowledgeRoute.EXTERNAL.value,
    }:
        return sub_route
    return None


def _normalize_graph_complexity(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in _GRAPH_COMPLEXITY_VALUES:
        return normalized
    return None


def _normalize_execution_strategy(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in _EXECUTION_STRATEGY_VALUES:
        return normalized
    return None


def _infer_graph_complexity_for_eval(
    *,
    question: str,
    selected_route: str | None,
    selected_intent: str | None,
    route_decision: dict[str, Any] | None,
) -> str:
    confidence = None
    if isinstance(route_decision, dict):
        raw_confidence = route_decision.get("confidence")
        if isinstance(raw_confidence, (int, float)):
            confidence = float(raw_confidence)
    resolved_intent = {
        "intent_id": _normalize_intent_id(selected_intent),
        "route": _normalize_route_value(selected_route),
        "confidence": confidence if confidence is not None else 0.75,
    }
    return _normalize_graph_complexity(
        classify_graph_complexity(
            resolved_intent=resolved_intent,
            user_query=question,
        )
    ) or GRAPH_COMPLEXITY_COMPLEX


def _infer_execution_strategy_for_eval(
    *,
    question: str,
    selected_agent: str | None,
    selected_tool: str | None,
    planning_steps: list[str],
) -> str:
    active_plan = [
        {"id": str(index + 1), "content": step}
        for index, step in enumerate(_safe_string_list(planning_steps))
    ]
    eval_state: dict[str, Any] = {
        "selected_agents": [{"name": selected_agent}] if selected_agent else [],
        "active_plan": active_plan,
    }
    if selected_agent and selected_tool:
        eval_state["resolved_tools_by_agent"] = {selected_agent: [selected_tool]}
    next_step_text = active_plan[0]["content"] if active_plan else ""
    strategy, _reason = classify_execution_strategy(
        state=eval_state,
        latest_user_query=question,
        next_step_text=next_step_text,
    )
    return _normalize_execution_strategy(strategy) or EXECUTION_STRATEGY_INLINE


def _normalize_token_for_match(value: Any) -> str:
    token = str(value or "").strip().casefold()
    token = re.sub(r"[^a-z0-9åäö]+", "_", token)
    return re.sub(r"_+", "_", token).strip("_")


def _normalize_category_name(value: Any) -> str | None:
    normalized = _normalize_token_for_match(value)
    return normalized or None


def _normalize_agent_name(value: Any) -> str | None:
    agent = str(value or "").strip().lower()
    if not agent:
        return None
    normalized_token = _normalize_token_for_match(agent)
    aliases = {
        # Swedish → canonical
        "statistik": "statistik",
        "stats": "statistik",
        "scb": "statistik",
        "statistics": "statistik",
        "riksdag": "riksdagen",
        "traffic": "trafik",
        "trafikverket": "trafik",
        "weather": "väder",
        "smhi": "väder",
        "vader": "väder",
        "maps": "kartor",
        "map": "kartor",
        "geo": "kartor",
        "geography": "kartor",
        "bolagsverket": "bolag",
        "companies": "bolag",
        "company": "bolag",
        "web": "webb",
        "browser": "webb",
        "docs": "kunskap",
        "internal": "kunskap",
        "external": "kunskap",
        "knowledge": "kunskap",
        "compare": "syntes",
        "synthesis": "syntes",
        "marketplace": "marknad",
        "marknadsplats": "marknad",
        "marknadsplatser": "marknad",
        "blocket": "marknad",
        "tradera": "marknad",
        "marketplace_agent": "marknad",
        "marketplace_worker": "marknad",
        "marketplace_search": "marknad",
        "marketplace_compare": "marknad",
        "marketplace_reference": "marknad",
        "marketplace_vehicles": "marknad",
        "code": "kod",
        "action": "åtgärd",
    }
    normalized = aliases.get(agent, aliases.get(normalized_token, normalized_token))
    if normalized.startswith("marketplace_"):
        normalized = "marknad"
    return normalized if normalized in _EVAL_AGENT_CHOICES else None


def _is_weather_domain_tool(tool_id: str | None, category: str | None = None) -> bool:
    tool = str(tool_id or "").strip().lower()
    cat = str(category or "").strip().lower()
    if tool.startswith("smhi_"):
        return True
    if tool.startswith("trafikverket_vader_"):
        return True
    if cat in {"weather", "trafikverket_vader"} or cat.startswith("smhi_"):
        return True
    return False


def _agent_for_route_hint(route_value: str | None, sub_route_value: str | None) -> str | None:
    route_norm = _normalize_route_value(route_value)
    sub_norm = _normalize_sub_route_value(sub_route_value)
    if route_norm == Route.KUNSKAP.value:
        return "statistik"
    if route_norm == Route.JAMFORELSE.value:
        return "syntes"
    if route_norm == Route.KUNSKAP.value:
        return "kunskap"
    if route_norm == Route.SKAPANDE.value:
        if sub_norm == ActionRoute.TRAVEL.value:
            return "trafik"
        if sub_norm == ActionRoute.WEB.value:
            return "webb"
        if sub_norm == ActionRoute.MEDIA.value:
            return "media"
        if sub_norm == ActionRoute.DATA.value:
            return "åtgärd"
        return "åtgärd"
    return None


def _agent_for_tool(
    tool_id: str | None,
    category: str | None = None,
    route_value: str | None = None,
    sub_route_value: str | None = None,
) -> str | None:
    tool = str(tool_id or "").strip().lower()
    cat = str(category or "").strip().lower()
    if tool in _SKOLVERKET_TOOL_IDS:
        skolverket_category = _SKOLVERKET_TOOL_CATEGORY_BY_ID.get(tool, cat)
        if skolverket_category == "statistics":
            return "statistik"
        return "kunskap"
    if tool.startswith("scb_") or cat in {"statistics", "scb_statistics"}:
        return "statistik"
    if tool.startswith("riksdag_") or cat.startswith("riksdag"):
        return "riksdagen"
    if _is_weather_domain_tool(tool, cat):
        return "väder"
    if tool.startswith("trafikverket_") or tool == "trafiklab_route":
        return "trafik"
    if tool.startswith("bolagsverket_"):
        return "bolag"
    if tool.startswith("geoapify_"):
        return "kartor"
    if tool.startswith("marketplace_") or cat.startswith("marketplace"):
        return "marknad"
    if tool in {"generate_podcast", "display_image"}:
        return "media"
    if tool in {"search_web", "search_tavily", "scrape_webpage", "link_preview"}:
        return "webb"
    if tool in {"search_surfsense_docs", "search_knowledge_base"}:
        return "kunskap"
    return _agent_for_route_hint(route_value, sub_route_value)


def _dedupe_strings(values: list[str] | None) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        lowered = cleaned.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(cleaned)
    return deduped


def _normalize_expected_agent_candidates(
    *,
    expected_agent: str | None,
    expected_payload: dict[str, Any],
) -> list[str]:
    configured = _safe_string_list(expected_payload.get("acceptable_agents"))
    normalized_configured = [
        _normalize_agent_name(agent_name)
        for agent_name in configured
        if _normalize_agent_name(agent_name)
    ]
    baseline = [expected_agent] if expected_agent else []
    return _dedupe_strings(
        [*(baseline or []), *[agent for agent in normalized_configured if agent]]
    )


def _coerce_weather_agent_choice(
    *,
    selected_agent: str | None,
    selected_tool: str | None,
    selected_category: str | None,
    route_value: str | None,
    sub_route_value: str | None,
) -> tuple[str | None, bool]:
    normalized_selected_agent = _normalize_agent_name(selected_agent)
    tool_id = str(selected_tool or "").strip().lower()
    category = str(selected_category or "").strip().lower()
    route_norm = _normalize_route_value(route_value)
    sub_route_norm = _normalize_sub_route_value(sub_route_value)
    is_weather_tool = _is_weather_domain_tool(tool_id, category)
    if not is_weather_tool:
        return normalized_selected_agent, False
    if route_norm == Route.SKAPANDE.value and sub_route_norm in {
        ActionRoute.TRAVEL.value,
        None,
    }:
        if normalized_selected_agent != "weather":
            return "weather", True
    if not normalized_selected_agent:
        return "weather", True
    return normalized_selected_agent, False


def _route_sub_route_for_tool(
    tool_id: str | None,
    category: str | None = None,
) -> tuple[str | None, str | None]:
    tool = str(tool_id or "").strip().lower()
    cat = str(category or "").strip().lower()
    if tool in _SKOLVERKET_TOOL_IDS:
        skolverket_category = _SKOLVERKET_TOOL_CATEGORY_BY_ID.get(tool, cat)
        if skolverket_category == "statistics":
            return Route.KUNSKAP.value, None
        return Route.KUNSKAP.value, KnowledgeRoute.EXTERNAL.value
    if tool.startswith("scb_") or cat in {"statistics", "scb_statistics"}:
        return Route.KUNSKAP.value, None
    if tool == "trafiklab_route" or _is_weather_domain_tool(tool, cat):
        return Route.SKAPANDE.value, ActionRoute.TRAVEL.value
    if tool.startswith("trafikverket_"):
        return Route.SKAPANDE.value, ActionRoute.TRAVEL.value
    if tool in {"scrape_webpage", "link_preview", "search_web", "search_tavily"}:
        return Route.SKAPANDE.value, ActionRoute.WEB.value
    if tool in {"generate_podcast", "display_image"}:
        return Route.SKAPANDE.value, ActionRoute.MEDIA.value
    if tool in {"libris_search", "jobad_links_search"}:
        return Route.SKAPANDE.value, ActionRoute.DATA.value
    if tool.startswith("marketplace_") or cat.startswith("marketplace"):
        return Route.SKAPANDE.value, ActionRoute.DATA.value
    if tool.startswith("bolagsverket_") or tool.startswith("riksdag_"):
        return Route.SKAPANDE.value, ActionRoute.DATA.value
    if tool in {"search_surfsense_docs", "search_knowledge_base"}:
        return Route.KUNSKAP.value, KnowledgeRoute.INTERNAL.value
    return Route.SKAPANDE.value, ActionRoute.DATA.value


def _repair_expected_routing(
    *,
    expected_route: str | None,
    expected_sub_route: str | None,
    expected_tool: str | None,
    expected_category: str | None,
) -> tuple[str | None, str | None]:
    route = _normalize_route_value(expected_route)
    sub_route = _normalize_sub_route_value(expected_sub_route)
    if not expected_tool:
        return route, sub_route

    inferred_route, inferred_sub_route = _route_sub_route_for_tool(
        expected_tool,
        expected_category,
    )
    if route is None and inferred_route is not None:
        route = inferred_route

    if route == Route.SKAPANDE.value:
        if inferred_route == Route.SKAPANDE.value and inferred_sub_route:
            # If expected tool implies an action sub-route, trust that mapping
            # over mislabeled sub-routes in eval payloads (e.g. web vs travel).
            sub_route = inferred_sub_route
    elif route == Route.KUNSKAP.value:
        if inferred_route == Route.KUNSKAP.value and inferred_sub_route:
            sub_route = inferred_sub_route
    elif route == Route.KUNSKAP.value:
        sub_route = None

    if inferred_route and route and route != inferred_route:
        route = inferred_route
        sub_route = inferred_sub_route

    return route, sub_route


def _candidate_agents_for_route(
    route_value: str | None,
    sub_route_value: str | None,
) -> list[str]:
    route_norm = _normalize_route_value(route_value)
    sub_norm = _normalize_sub_route_value(sub_route_value)
    if route_norm == Route.KUNSKAP.value:
        return ["statistics", "riksdagen", "knowledge"]
    if route_norm == Route.JAMFORELSE.value:
        return ["synthesis", "statistics", "knowledge"]
    if route_norm == Route.KUNSKAP.value:
        return ["knowledge", "riksdagen", "statistics", "browser"]
    if route_norm == Route.SKAPANDE.value:
        if sub_norm == ActionRoute.TRAVEL.value:
            return ["weather", "trafik", "action", "kartor"]
        if sub_norm == ActionRoute.WEB.value:
            return ["browser", "action", "knowledge"]
        if sub_norm == ActionRoute.MEDIA.value:
            return ["media", "action"]
        if sub_norm == ActionRoute.DATA.value:
            return ["marketplace", "action", "statistics", "riksdagen", "bolag", "kartor"]
        return ["marketplace", "action", "browser", "weather", "trafik", "media", "bolag", "kartor"]
    return ["knowledge", "action"]


def _heuristic_agent_choice(
    question: str,
    route_value: str | None,
    sub_route_value: str | None,
    candidates: list[str],
) -> str | None:
    text = str(question or "").casefold()
    if any(token in text for token in ("riksdag", "interpellation", "motion", "utskott")):
        return "riksdagen" if "riksdagen" in candidates else candidates[0]
    if any(token in text for token in ("scb", "statistik", "inflation", "arbetslös", "befolkning")):
        return "statistics" if "statistics" in candidates else candidates[0]
    if any(
        token in text
        for token in (
            "smhi",
            "väder",
            "vader",
            "temperatur",
            "regn",
            "snö",
            "sno",
            "vind",
            "halka",
            "isrisk",
            "väglag",
            "vaglag",
            "vägväder",
            "vagvader",
        )
    ):
        return "weather" if "weather" in candidates else candidates[0]
    if any(token in text for token in ("trafik", "väg", "rutt", "resa", "avgång")):
        return "trafik" if "trafik" in candidates else candidates[0]
    if any(token in text for token in ("bolag", "organisationsnummer", "företag")):
        return "bolag" if "bolag" in candidates else candidates[0]
    if any(
        token in text
        for token in (
            "blocket",
            "tradera",
            "marknadsplats",
            "begagnat",
            "begagnad",
            "annons",
            "auktion",
            "prisjämförelse",
            "prisjamforelse",
            "motorcykel",
            "båtar",
            "batar",
            "bilar",
        )
    ):
        return "marketplace" if "marketplace" in candidates else candidates[0]
    if any(token in text for token in ("karta", "koordinat", "lat", "lon", "adress")):
        return "kartor" if "kartor" in candidates else candidates[0]
    if any(token in text for token in ("podcast", "podd", "bild", "image")):
        return "media" if "media" in candidates else candidates[0]
    if "http://" in text or "https://" in text or "webb" in text or "url" in text:
        return "browser" if "browser" in candidates else candidates[0]
    inferred = _agent_for_route_hint(route_value, sub_route_value)
    if inferred and inferred in candidates:
        return inferred
    return candidates[0] if candidates else None


async def _plan_agent_choice(
    *,
    question: str,
    route_value: str | None,
    sub_route_value: str | None,
    llm,
) -> dict[str, Any]:
    candidates = _candidate_agents_for_route(route_value, sub_route_value)
    fallback_agent = _heuristic_agent_choice(
        question,
        route_value=route_value,
        sub_route_value=sub_route_value,
        candidates=candidates,
    )
    fallback_payload = {
        "selected_agent": fallback_agent,
        "analysis": "Fallback-planeraren valde närmaste route-kompatibla agent.",
    }
    if llm is None:
        return fallback_payload
    planner_prompt = (
        "Du utvärderar nästa agentval i dry-run-läge.\n"
        "Givet route-kontekst och tillåtna kandidater ska du välja exakt en agent.\n"
        "All text ska vara på svenska.\n"
        "Returnera strikt JSON:\n"
        "{\n"
        '  "selected_agent": "one of candidate names",\n'
        '  "analysis": "kort förklaring på svenska"\n'
        "}\n"
        "Ingen markdown."
    )
    payload = {
        "question": question,
        "route": route_value,
        "sub_route": sub_route_value,
        "candidates": [
            {"name": name, "description": _EVAL_AGENT_DESCRIPTIONS.get(name, "")}
            for name in candidates
        ],
    }
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=planner_prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
            ]
        )
        parsed = _extract_json_object(_response_content_to_text(getattr(response, "content", "")))
        selected_agent = _normalize_agent_name(
            parsed.get("selected_agent") if isinstance(parsed, dict) else None
        )
        if selected_agent not in candidates:
            selected_agent = fallback_agent
        analysis = (
            str(parsed.get("analysis") or "").strip()
            if isinstance(parsed, dict)
            else ""
        )
        if not analysis:
            analysis = fallback_payload["analysis"]
        return {"selected_agent": selected_agent, "analysis": analysis}
    except Exception:
        return fallback_payload


async def _dispatch_route_from_start(
    *,
    question: str,
    llm,
    prompt_overrides: dict[str, str] | None = None,
    intent_definitions: list[dict[str, Any]] | None = None,
) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
    def _fallback_intent_id(route_value: str | None) -> str | None:
        mapping = {
            Route.KUNSKAP.value: "knowledge",
            Route.SKAPANDE.value: "action",
            Route.KUNSKAP.value: "statistics",
            Route.JAMFORELSE.value: "compare",
            Route.KONVERSATION.value: "smalltalk",
        }
        return mapping.get(_normalize_route_value(route_value))

    def _extract_intent_id(route_decision: dict[str, Any], route_value: str | None) -> str | None:
        normalized_route = _normalize_route_value(route_value)
        if isinstance(route_decision, dict):
            explicit_intent = _normalize_intent_id(
                route_decision.get("selected_intent")
                or route_decision.get("intent_id")
                or route_decision.get("intent")
            )
            if explicit_intent:
                return explicit_intent

            reason = str(route_decision.get("reason") or "").strip()
            if reason and ":" in reason:
                prefix, _, value = reason.partition(":")
                if prefix.strip().lower().startswith("intent") and value.strip():
                    return value.strip().lower()

            candidates = route_decision.get("candidates")
            if isinstance(candidates, list):
                normalized_candidates = [
                    candidate
                    for candidate in candidates
                    if isinstance(candidate, dict)
                ]
                if normalized_candidates and normalized_route:
                    route_matched = [
                        candidate
                        for candidate in normalized_candidates
                        if _normalize_route_value(candidate.get("route")) == normalized_route
                    ]
                    if route_matched:
                        route_matched.sort(
                            key=lambda candidate: float(candidate.get("score") or 0.0),
                            reverse=True,
                        )
                        matched_intent = _normalize_intent_id(
                            route_matched[0].get("intent_id")
                        )
                        if matched_intent:
                            return matched_intent
                for candidate in normalized_candidates:
                    intent_id = _normalize_intent_id(candidate.get("intent_id"))
                    if intent_id:
                        return intent_id
        return _fallback_intent_id(route_value)

    overrides = prompt_overrides or {}
    selected_route, route_decision = await dispatch_route_with_trace(
        question,
        llm,
        has_attachments=False,
        has_mentions=False,
        system_prompt_override=overrides.get("router.top_level"),
        intent_definitions=intent_definitions,
    )
    route_value = (
        selected_route.value
        if hasattr(selected_route, "value")
        else _normalize_route_value(selected_route)
    )
    selected_sub_route: str | None = None
    if route_value == Route.SKAPANDE.value:
        action_route = await dispatch_action_route(
            question,
            llm,
            system_prompt_override=overrides.get("router.action"),
        )
        selected_sub_route = (
            action_route.value
            if hasattr(action_route, "value")
            else _normalize_sub_route_value(action_route)
        )
    elif route_value == Route.KUNSKAP.value:
        knowledge_route = await dispatch_knowledge_route(
            question,
            llm,
            has_attachments=False,
            has_mentions=False,
            allow_external=True,
            system_prompt_override=overrides.get("router.knowledge"),
        )
        selected_sub_route = (
            knowledge_route.value
            if hasattr(knowledge_route, "value")
            else _normalize_sub_route_value(knowledge_route)
        )
    normalized_route = _normalize_route_value(route_value)
    normalized_sub_route = _normalize_sub_route_value(selected_sub_route)
    selected_intent = _extract_intent_id(route_decision, normalized_route)
    return normalized_route, normalized_sub_route, selected_intent, (
        route_decision if isinstance(route_decision, dict) else {}
    )


def _normalize_intent_id(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def _infer_expected_intent_id(
    *,
    expected: dict[str, Any],
    expected_route: str | None,
    intent_definitions: list[dict[str, Any]] | None = None,
) -> str | None:
    explicit = _normalize_intent_id(expected.get("intent") if isinstance(expected, dict) else None)
    if explicit:
        return explicit
    normalized_route = _normalize_route_value(expected_route)
    if not normalized_route:
        return None
    candidates = [
        item
        for item in (intent_definitions or [])
        if isinstance(item, dict)
        and _normalize_route_value(item.get("route")) == normalized_route
        and bool(item.get("enabled", True))
    ]
    if candidates:
        candidates.sort(
            key=lambda item: (
                int(item.get("priority") or 500),
                str(item.get("intent_id") or ""),
            )
        )
        resolved = _normalize_intent_id(candidates[0].get("intent_id"))
        if resolved:
            return resolved
    fallback = {
        Route.KUNSKAP.value: "knowledge",
        Route.SKAPANDE.value: "action",
        Route.KUNSKAP.value: "statistics",
        Route.JAMFORELSE.value: "compare",
        Route.KONVERSATION.value: "smalltalk",
    }
    return fallback.get(normalized_route)


def _parse_plan_requirement(requirement: str) -> tuple[str | None, str | None]:
    value = str(requirement or "").strip()
    if not value:
        return None, None
    lowered = value.casefold()
    if lowered in {"clarification", "ask_clarification"}:
        return "clarification", ""
    patterns: list[tuple[str, re.Pattern[str]]] = [
        ("field", re.compile(r"^field[\s:_-]+(.+)$", re.IGNORECASE)),
        ("tool", re.compile(r"^tool[\s:_-]+(.+)$", re.IGNORECASE)),
        ("route", re.compile(r"^route[\s:_-]+(.+)$", re.IGNORECASE)),
        ("sub_route", re.compile(r"^sub(?:[\s_-]?route)?[\s:_-]+(.+)$", re.IGNORECASE)),
        ("agent", re.compile(r"^agent[\s:_-]+(.+)$", re.IGNORECASE)),
    ]
    for key, pattern in patterns:
        match = pattern.match(value)
        if match:
            extracted = str(match.group(1) or "").strip()
            return key, extracted
    return None, value


def _route_requirement_matches(
    expected_value: str,
    *,
    context_payload: dict[str, Any],
) -> bool:
    expected = str(expected_value or "").strip().casefold()
    if not expected:
        return False
    selected_route = _normalize_route_value(context_payload.get("selected_route"))
    selected_sub_route = _normalize_sub_route_value(context_payload.get("selected_sub_route"))
    selected_agent = _normalize_agent_name(context_payload.get("selected_agent"))
    selected_tool = str(context_payload.get("selected_tool") or "").strip().casefold()

    normalized_route = _normalize_route_value(expected)
    if normalized_route:
        return bool(selected_route and selected_route == normalized_route)

    if expected in {"travel", "weather"}:
        if not (
            selected_route == Route.SKAPANDE.value
            and selected_sub_route == ActionRoute.TRAVEL.value
        ):
            return False
        if expected == "weather":
            return (
                selected_agent == "weather"
                or selected_tool.startswith("smhi_")
                or selected_tool.startswith("trafikverket_vader_")
            )
        return True

    if expected in {
        ActionRoute.WEB.value,
        ActionRoute.MEDIA.value,
        ActionRoute.DATA.value,
    }:
        return bool(
            selected_route == Route.SKAPANDE.value and selected_sub_route == expected
        )

    if expected in {
        KnowledgeRoute.DOCS.value,
        KnowledgeRoute.INTERNAL.value,
        KnowledgeRoute.EXTERNAL.value,
    }:
        return bool(
            selected_route == Route.KUNSKAP.value
            and selected_sub_route == expected
        )

    if expected.startswith("action/") or expected.startswith("action:"):
        trailing = (
            expected.split("/", 1)[1]
            if "/" in expected
            else expected.split(":", 1)[1]
        ).strip().casefold()
        if trailing == "weather":
            trailing = ActionRoute.TRAVEL.value
        return bool(
            selected_route == Route.SKAPANDE.value and selected_sub_route == trailing
        )

    if expected.startswith("knowledge/") or expected.startswith("knowledge:"):
        trailing = (
            expected.split("/", 1)[1]
            if "/" in expected
            else expected.split(":", 1)[1]
        ).strip().casefold()
        return bool(
            selected_route == Route.KUNSKAP.value and selected_sub_route == trailing
        )

    return False


def _sub_route_requirement_matches(
    expected_value: str,
    *,
    context_payload: dict[str, Any],
) -> bool:
    expected = str(expected_value or "").strip().casefold()
    if not expected:
        return False
    if expected == "weather":
        expected = ActionRoute.TRAVEL.value
    normalized_expected = _normalize_sub_route_value(expected)
    selected_sub_route = _normalize_sub_route_value(context_payload.get("selected_sub_route"))
    return bool(
        normalized_expected and selected_sub_route and normalized_expected == selected_sub_route
    )


def _evaluate_plan_requirements(
    *,
    requirements: list[str],
    planning_analysis: str,
    planning_steps: list[str],
    context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], bool | None]:
    normalized_requirements = _safe_string_list(requirements)
    if not normalized_requirements:
        return [], None
    merged_text = " ".join(
        [planning_analysis or "", *[step for step in planning_steps if step]]
    ).casefold()
    context_payload = context or {}
    checks: list[dict[str, Any]] = []
    for requirement in normalized_requirements:
        lowered = requirement.casefold()
        req_kind, req_value = _parse_plan_requirement(requirement)
        passed = False
        if req_kind == "field":
            field_name = str(req_value or "").strip()
            proposed_arguments = context_payload.get("proposed_arguments")
            if isinstance(proposed_arguments, dict) and field_name:
                passed = field_name in proposed_arguments
        elif req_kind == "clarification":
            passed = bool(context_payload.get("needs_clarification"))
        elif req_kind == "tool":
            expected_tool = str(req_value or "").strip().casefold()
            selected_tool = str(context_payload.get("selected_tool") or "").casefold()
            passed = bool(expected_tool and selected_tool and expected_tool == selected_tool)
        elif req_kind == "route":
            passed = _route_requirement_matches(
                str(req_value or ""),
                context_payload=context_payload,
            )
        elif req_kind == "sub_route":
            passed = _sub_route_requirement_matches(
                str(req_value or ""),
                context_payload=context_payload,
            )
        elif req_kind == "agent":
            expected_agent = _normalize_agent_name(req_value)
            selected_agent = _normalize_agent_name(context_payload.get("selected_agent"))
            passed = bool(
                expected_agent and selected_agent and expected_agent == selected_agent
            )
        else:
            passed = lowered in merged_text
        checks.append(
            {
                "requirement": requirement,
                "passed": passed,
            }
        )
    return checks, all(check.get("passed") for check in checks)


def _build_supervisor_trace(
    *,
    question: str,
    expected_intent: str | None,
    expected_route: str | None,
    expected_sub_route: str | None,
    expected_agent: str | None,
    expected_tool: str | None,
    expected_graph_complexity: str | None,
    expected_execution_strategy: str | None,
    selected_intent: str | None,
    selected_route: str | None,
    selected_sub_route: str | None,
    selected_agent: str | None,
    selected_tool: str | None,
    selected_graph_complexity: str | None,
    selected_execution_strategy: str | None,
    agent_selection_analysis: str,
    planning_analysis: str,
    planning_steps: list[str],
    plan_requirement_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "question": str(question or "").strip(),
        "expected": {
            "intent": expected_intent,
            "route": expected_route,
            "sub_route": expected_sub_route,
            "agent": expected_agent,
            "tool": expected_tool,
            "graph_complexity": expected_graph_complexity,
            "execution_strategy": expected_execution_strategy,
        },
        "selected": {
            "intent": selected_intent,
            "route": selected_route,
            "sub_route": selected_sub_route,
            "agent": selected_agent,
            "tool": selected_tool,
            "graph_complexity": selected_graph_complexity,
            "execution_strategy": selected_execution_strategy,
        },
        "reasoning": {
            "agent_selection_analysis": str(agent_selection_analysis or "").strip(),
            "tool_planning_analysis": str(planning_analysis or "").strip(),
        },
        "plan_steps": _safe_string_list(planning_steps)[:10],
        "plan_requirement_checks": list(plan_requirement_checks or [])[:20],
    }


def _build_supervisor_review_rubric(
    *,
    supervisor_trace: dict[str, Any],
) -> list[dict[str, Any]]:
    trace = supervisor_trace if isinstance(supervisor_trace, dict) else {}
    expected = trace.get("expected") if isinstance(trace.get("expected"), dict) else {}
    selected = trace.get("selected") if isinstance(trace.get("selected"), dict) else {}
    reasoning = trace.get("reasoning") if isinstance(trace.get("reasoning"), dict) else {}
    plan_steps = _safe_string_list(trace.get("plan_steps"))
    plan_checks = trace.get("plan_requirement_checks")
    if not isinstance(plan_checks, list):
        plan_checks = []

    expected_route = str(expected.get("route") or "").strip()
    expected_intent = str(expected.get("intent") or "").strip()
    expected_sub_route = str(expected.get("sub_route") or "").strip()
    expected_agent = str(expected.get("agent") or "").strip()
    expected_tool = str(expected.get("tool") or "").strip()
    expected_graph_complexity = str(expected.get("graph_complexity") or "").strip()
    expected_execution_strategy = str(expected.get("execution_strategy") or "").strip()
    selected_route = str(selected.get("route") or "").strip()
    selected_intent = str(selected.get("intent") or "").strip()
    selected_sub_route = str(selected.get("sub_route") or "").strip()
    selected_agent = str(selected.get("agent") or "").strip()
    selected_tool = str(selected.get("tool") or "").strip()
    selected_graph_complexity = str(selected.get("graph_complexity") or "").strip()
    selected_execution_strategy = str(selected.get("execution_strategy") or "").strip()
    agent_analysis = str(reasoning.get("agent_selection_analysis") or "").strip()
    tool_analysis = str(reasoning.get("tool_planning_analysis") or "").strip()
    failed_requirements = [
        str(item.get("requirement") or "").strip()
        for item in plan_checks
        if isinstance(item, dict) and item.get("passed") is False
    ]

    rubric: list[dict[str, Any]] = []

    def _item(
        *,
        key: str,
        label: str,
        passed: bool,
        weight: float,
        evidence: str,
    ) -> None:
        rubric.append(
            {
                "key": key,
                "label": label,
                "passed": bool(passed),
                "weight": float(weight),
                "evidence": evidence,
            }
        )

    _item(
        key="intent_presence",
        label="Intent är satt",
        passed=bool(selected_intent),
        weight=0.8,
        evidence=selected_intent or "Saknas",
    )
    _item(
        key="intent_alignment",
        label="Intent matchar förväntad",
        passed=(selected_intent == expected_intent)
        if expected_intent
        else bool(selected_intent),
        weight=0.8,
        evidence=f"expected={expected_intent or '-'} selected={selected_intent or '-'}",
    )

    _item(
        key="route_presence",
        label="Route är satt",
        passed=bool(selected_route),
        weight=1.0,
        evidence=selected_route or "Saknas",
    )
    _item(
        key="route_alignment",
        label="Route matchar förväntad",
        passed=(selected_route == expected_route) if expected_route else bool(selected_route),
        weight=0.8,
        evidence=f"expected={expected_route or '-'} selected={selected_route or '-'}",
    )
    _item(
        key="sub_route_alignment",
        label="Sub-route matchar förväntad",
        passed=(
            (selected_sub_route == expected_sub_route)
            if expected_sub_route
            else bool(selected_sub_route) or bool(selected_route)
        ),
        weight=0.7,
        evidence=f"expected={expected_sub_route or '-'} selected={selected_sub_route or '-'}",
    )
    if expected_graph_complexity or selected_graph_complexity:
        _item(
            key="graph_complexity_alignment",
            label="Graph complexity matchar förväntad",
            passed=(
                (selected_graph_complexity == expected_graph_complexity)
                if expected_graph_complexity
                else bool(selected_graph_complexity)
            ),
            weight=0.6,
            evidence=(
                f"expected={expected_graph_complexity or '-'} "
                f"selected={selected_graph_complexity or '-'}"
            ),
        )
    if expected_execution_strategy or selected_execution_strategy:
        _item(
            key="execution_strategy_alignment",
            label="Execution-strategi matchar förväntad",
            passed=(
                (selected_execution_strategy == expected_execution_strategy)
                if expected_execution_strategy
                else bool(selected_execution_strategy)
            ),
            weight=0.6,
            evidence=(
                f"expected={expected_execution_strategy or '-'} "
                f"selected={selected_execution_strategy or '-'}"
            ),
        )
    _item(
        key="agent_presence",
        label="Agent är satt",
        passed=bool(selected_agent),
        weight=1.0,
        evidence=selected_agent or "Saknas",
    )
    _item(
        key="agent_alignment",
        label="Agent matchar förväntad",
        passed=(selected_agent == expected_agent) if expected_agent else bool(selected_agent),
        weight=0.8,
        evidence=f"expected={expected_agent or '-'} selected={selected_agent or '-'}",
    )
    _item(
        key="tool_presence",
        label="Tool är satt",
        passed=bool(selected_tool),
        weight=1.0,
        evidence=selected_tool or "Saknas",
    )
    _item(
        key="tool_alignment",
        label="Tool matchar förväntad",
        passed=(selected_tool == expected_tool) if expected_tool else bool(selected_tool),
        weight=0.8,
        evidence=f"expected={expected_tool or '-'} selected={selected_tool or '-'}",
    )
    _item(
        key="agent_reasoning_quality",
        label="Agentvals-analys finns",
        passed=bool(agent_analysis),
        weight=0.8,
        evidence=agent_analysis or "Saknas",
    )
    _item(
        key="tool_reasoning_quality",
        label="Tool-planeringsanalys finns",
        passed=bool(tool_analysis),
        weight=0.8,
        evidence=tool_analysis or "Saknas",
    )
    _item(
        key="plan_steps_quality",
        label="Plansteg finns",
        passed=bool(plan_steps),
        weight=0.8,
        evidence=f"{len(plan_steps)} steg",
    )
    _item(
        key="plan_requirements_alignment",
        label="Plan-krav är uppfyllda",
        passed=(len(failed_requirements) == 0),
        weight=0.9,
        evidence=(
            "Alla krav uppfyllda"
            if not failed_requirements
            else "Missar: " + ", ".join(failed_requirements[:6])
        ),
    )
    return rubric


def _score_supervisor_review_rubric(rubric: list[dict[str, Any]]) -> float:
    if not rubric:
        return 0.0
    total_weight = 0.0
    earned_weight = 0.0
    for item in rubric:
        if not isinstance(item, dict):
            continue
        raw_weight = item.get("weight", 1.0)
        weight = float(raw_weight) if isinstance(raw_weight, (int, float)) else 1.0
        weight = max(0.1, min(3.0, weight))
        total_weight += weight
        if bool(item.get("passed")):
            earned_weight += weight
    if total_weight <= 0:
        return 0.0
    return max(0.0, min(1.0, earned_weight / total_weight))


def _fallback_supervisor_trace_review(
    *,
    supervisor_trace: dict[str, Any],
) -> dict[str, Any]:
    rubric = _build_supervisor_review_rubric(supervisor_trace=supervisor_trace)
    score = _score_supervisor_review_rubric(rubric)
    passed = score >= 0.67
    issues = [
        str(item.get("label") or "").strip()
        for item in rubric
        if isinstance(item, dict) and item.get("passed") is False
    ][:8]
    rationale = (
        "Heuristisk granskning av supervisor-spår: "
        f"{'godkänd' if passed else 'otillräcklig'} struktur."
    )
    return {
        "score": score,
        "passed": passed,
        "rationale": rationale,
        "issues": issues,
        "rubric": rubric,
    }


async def _review_supervisor_trace(
    *,
    supervisor_trace: dict[str, Any],
    llm,
) -> dict[str, Any]:
    fallback = _fallback_supervisor_trace_review(
        supervisor_trace=supervisor_trace,
    )
    if llm is None:
        return fallback

    prompt = (
        "Du granskar ett supervisor-spår från eval dry-run.\n"
        "Bedöm struktur och resonemangskvalitet i kedjan route -> agent -> tool -> plan.\n"
        "Krav:\n"
        "- Identifiera om spåret är komplett och sammanhängande.\n"
        "- Markera om plansteg och val är otydliga eller motsägelsefulla.\n"
        "- Kontrollera att resonemanget stödjer retrieval-arkitekturen (dynamiskt val, ny retrieval vid mismatch/ämnesbyte).\n"
        "All text ska vara på svenska.\n"
        "Returnera strikt JSON:\n"
        "{\n"
        '  "score": number mellan 0 och 1,\n'
        '  "passed": boolean,\n'
        '  "rationale": "kort motivering på svenska",\n'
        '  "issues": ["kort punkt på svenska"]\n'
        "}\n"
        "Ingen markdown."
    )
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(
                    content=json.dumps(
                        {"supervisor_trace": supervisor_trace},
                        ensure_ascii=True,
                    )
                ),
            ]
        )
        parsed = _extract_json_object(
            _response_content_to_text(getattr(response, "content", ""))
        )
        if not parsed:
            return fallback
        raw_score = parsed.get("score")
        llm_score = (
            float(raw_score)
            if isinstance(raw_score, (int, float))
            else float(fallback["score"])
        )
        llm_score = max(0.0, min(1.0, llm_score))
        score = (llm_score * 0.6) + (float(fallback["score"]) * 0.4)
        score = max(0.0, min(1.0, score))
        passed = (
            bool(parsed.get("passed"))
            if isinstance(parsed.get("passed"), bool)
            else score >= 0.67
        )
        rationale = _prefer_swedish_text(
            str(parsed.get("rationale") or "").strip(),
            fallback["rationale"],
        )
        issues = []
        for item in [*list(fallback.get("issues") or []), *_safe_string_list(parsed.get("issues"))]:
            cleaned = str(item).strip()
            if cleaned and cleaned.casefold() not in {value.casefold() for value in issues}:
                issues.append(cleaned)
        return {
            "score": score,
            "passed": passed,
            "rationale": rationale,
            "issues": issues,
            "rubric": list(fallback.get("rubric") or []),
        }
    except Exception:
        return fallback


def _compute_agent_gate_score(
    *,
    upstream_checks: list[bool | None],
    downstream_checks: list[bool | None],
    downstream_weight: float = 0.35,
) -> tuple[float | None, bool | None]:
    valid_upstream = [check for check in upstream_checks if check is not None]
    valid_downstream = [check for check in downstream_checks if check is not None]
    if not valid_upstream and not valid_downstream:
        return None, None
    upstream_failed = any(check is False for check in valid_upstream)
    total_weight = 0.0
    earned_weight = 0.0

    for check in valid_upstream:
        total_weight += 1.0
        if check:
            earned_weight += 1.0

    # Agent gate: when upstream routing fails, do not penalize tool/API checks.
    if not upstream_failed:
        for check in valid_downstream:
            total_weight += downstream_weight
            if check:
                earned_weight += downstream_weight

    if total_weight <= 0:
        return None, None
    score = earned_weight / total_weight
    return score, bool(score >= 0.999)


def _serialize_tool(entry: ToolIndexEntry) -> dict[str, Any]:
    return {
        "tool_id": entry.tool_id,
        "name": entry.name,
        "category": entry.category,
        "description": entry.description,
        "keywords": list(entry.keywords),
        "example_queries": list(entry.example_queries),
        "main_identifier": entry.main_identifier or "",
        "core_activity": entry.core_activity or "",
        "unique_scope": entry.unique_scope or "",
        "geographic_scope": entry.geographic_scope or "",
        "excludes": list(entry.excludes) if entry.excludes else [],
    }


async def _plan_tool_choice(
    *,
    question: str,
    candidates: list[ToolIndexEntry],
    llm,
) -> dict[str, Any]:
    candidate_ids = [entry.tool_id for entry in candidates]
    if not candidates:
        return {
            "selected_tool_id": None,
            "selected_category": None,
            "analysis": "No candidates were retrieved for this query.",
            "plan_steps": [],
        }

    fallback_entry = candidates[0]
    fallback_payload = {
        "selected_tool_id": fallback_entry.tool_id,
        "selected_category": fallback_entry.category,
        "analysis": (
            "Fallback-planerare: ingen modell tillgänglig, valde högst rankad retrieval-kandidat."
        ),
        "plan_steps": [
            "Inspektera kandidater från tool_retrieval.",
            f"Välj {fallback_entry.tool_id} som bästa metadata-match.",
            "Stoppa innan faktisk tool-körning (eval dry-run).",
        ],
    }
    if llm is None:
        return fallback_payload

    planner_prompt = (
        "Du utvärderar tool-routing i dry-run-läge.\n"
        "Givet en användarfråga och retrieval-kandidater: välj exakt ett bästa verktyg.\n"
        "Uppfinn aldrig tool_id. Du får endast välja bland kandidaternas tool_id.\n"
        "All text ska vara på svenska.\n"
        "Returnera strikt JSON med detta schema:\n"
        "{\n"
        '  "selected_tool_id": "tool_id or null",\n'
        '  "selected_category": "category or null",\n'
        '  "analysis": "kort förklaring på svenska",\n'
        '  "plan_steps": ["step 1", "step 2"]\n'
        "}\n"
        "Ingen markdown."
    )
    question_payload = {
        "question": question,
        "candidates": [_serialize_tool(entry) for entry in candidates[:8]],
    }
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=planner_prompt),
                HumanMessage(content=json.dumps(question_payload, ensure_ascii=True)),
            ]
        )
        text = str(getattr(response, "content", "") or "")
        parsed = _extract_json_object(text) or {}
        selected_tool_id = parsed.get("selected_tool_id")
        if selected_tool_id is not None:
            selected_tool_id = str(selected_tool_id).strip() or None
        if selected_tool_id not in candidate_ids:
            selected_tool_id = fallback_entry.tool_id
        selected_entry = next(
            (entry for entry in candidates if entry.tool_id == selected_tool_id),
            fallback_entry,
        )
        analysis = str(parsed.get("analysis") or "").strip()
        if not analysis:
            analysis = fallback_payload["analysis"]
        plan_steps = _safe_string_list(parsed.get("plan_steps"))
        if not plan_steps:
            plan_steps = fallback_payload["plan_steps"]
        return {
            "selected_tool_id": selected_tool_id,
            "selected_category": selected_entry.category,
            "analysis": analysis,
            "plan_steps": plan_steps,
        }
    except Exception:
        return fallback_payload


def _tokenize_for_suggestions(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9åäöÅÄÖ]{3,}", text.lower())
    return [token for token in tokens if token not in _SUGGESTION_STOPWORDS]


def _build_fallback_suggestion(
    *,
    tool_id: str,
    current: dict[str, Any],
    questions: list[str],
    failed_count: int,
) -> tuple[dict[str, Any], str]:
    forbidden_markers = _tool_reference_markers_for_suggestions(
        tool_id=tool_id,
        tool_name=str(current.get("name") or ""),
    )
    token_counts: dict[str, int] = {}
    for question in questions:
        for token in _tokenize_for_suggestions(question):
            token_counts[token] = token_counts.get(token, 0) + 1
    sorted_tokens = sorted(
        token_counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    existing_keywords = [str(keyword) for keyword in current.get("keywords") or []]
    existing_keyword_set = {keyword.casefold() for keyword in existing_keywords}
    proposed_keywords = list(existing_keywords)
    for token, _count in sorted_tokens:
        if token.casefold() in existing_keyword_set:
            continue
        proposed_keywords.append(token)
        existing_keyword_set.add(token.casefold())
        if len(proposed_keywords) >= 25:
            break

    proposed_examples = list(current.get("example_queries") or [])
    seen_examples = {str(example).casefold() for example in proposed_examples}
    for question in questions:
        cleaned = question.strip()
        if not cleaned:
            continue
        if _contains_forbidden_tool_reference(
            cleaned,
            forbidden_markers=forbidden_markers,
        ):
            continue
        key = cleaned.casefold()
        if key in seen_examples:
            continue
        proposed_examples.append(cleaned)
        seen_examples.add(key)
        if len(proposed_examples) >= 12:
            break
    proposed_examples = _sanitize_example_queries_no_tool_refs(
        proposed_examples,
        forbidden_markers=forbidden_markers,
    )

    description = str(current.get("description") or "").strip()
    hint_terms = [token for token, _count in sorted_tokens[:3]]
    if hint_terms:
        hint_suffix = ", ".join(hint_terms)
        marker = f"Relevant för termer som: {hint_suffix}."
        if marker not in description:
            description = f"{description} {marker}".strip()

    proposed = {
        "tool_id": tool_id,
        "name": str(current.get("name") or "").strip(),
        "description": description,
        "keywords": proposed_keywords,
        "example_queries": proposed_examples,
        "category": str(current.get("category") or "").strip(),
        "base_path": current.get("base_path"),
        "main_identifier": str(current.get("main_identifier") or "").strip(),
        "core_activity": str(current.get("core_activity") or "").strip(),
        "unique_scope": str(current.get("unique_scope") or "").strip(),
        "geographic_scope": str(current.get("geographic_scope") or "").strip(),
        "excludes": _safe_string_list(current.get("excludes")),
    }
    rationale = (
        f"Fallback-förslag baserat på {failed_count} misslyckade testfall: "
        "utökade nyckelord och exempelfrågor med återkommande termer."
    )
    return proposed, rationale


async def _build_llm_suggestion(
    *,
    tool_id: str,
    llm,
    current: dict[str, Any],
    failures: list[dict[str, Any]],
    retrieval_tuning: dict[str, Any] | None = None,
    retrieval_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str] | None:
    if llm is None:
        return None
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    forbidden_markers = _tool_reference_markers_for_suggestions(
        tool_id=tool_id,
        tool_name=str(current.get("name") or ""),
    )

    prompt = (
        "Du optimerar verktygsmetadata för retrieval.\n"
        "Givet nuvarande metadata och misslyckade eval-fall ska du föreslå förbättrad metadata.\n"
        "Använd retrieval-vikter och score-breakdown från fallen när du prioriterar ändringar.\n"
        "Om vector recall och embedding-context finns i underlaget ska de vägas in i motiveringen.\n"
        "Behåll kategori om det inte finns starka skäl att ändra.\n"
        "ALL text måste vara på svenska.\n"
        "Exempelfrågor måste vara naturlig svenska och skrivna som riktiga användarfrågor.\n"
        "Strikt förbud: tool_id, toolnamn, funktionsnamn, endpoint- eller interna identifierare i exempelfrågor.\n"
        "Använd aldrig snake_case eller identifierare med underscore i exempelfrågor.\n"
        "Fälten main_identifier, core_activity, unique_scope, geographic_scope och excludes är "
        "separata identitetsfält som används för embedding-separation och retrieval-precision.\n"
        "- main_identifier: Vad verktyget fundamentalt är/representerar.\n"
        "- core_activity: Vad verktyget gör / dess huvudsakliga funktion.\n"
        "- unique_scope: Vad som unikt avgränsar detta verktyg från liknande.\n"
        "- geographic_scope: Geografiskt omfång (t.ex. kommun, Sverige, Norden).\n"
        "- excludes: Lista med domänbegrepp som verktyget INTE hanterar (separationsstöd).\n"
        "Returnera strikt JSON:\n"
        "{\n"
        '  "name": "string",\n'
        '  "description": "string på svenska",\n'
        '  "keywords": ["svenska termer"],\n'
        '  "example_queries": ["svenska frågor"],\n'
        '  "category": "string",\n'
        '  "main_identifier": "string på svenska",\n'
        '  "core_activity": "string på svenska",\n'
        '  "unique_scope": "string på svenska",\n'
        '  "geographic_scope": "string på svenska",\n'
        '  "excludes": ["svenska termer"],\n'
        '  "rationale": "kort motivering på svenska"\n'
        "}\n"
        "Ingen markdown."
    )
    trimmed_failures: list[dict[str, Any]] = []
    for item in failures[:_MAX_TOOL_FAILURES_FOR_LLM]:
        if not isinstance(item, dict):
            continue
        trimmed_failures.append(
            {
                "question": str(item.get("question") or "").strip(),
                "selected_wrong_tool": str(item.get("selected_wrong_tool") or "").strip() or None,
                "retrieval_breakdown": list(item.get("retrieval_breakdown") or [])[:3],
                "tool_vector_diagnostics": dict(item.get("tool_vector_diagnostics") or {}),
            }
        )

    payload = {
        "current_metadata": current,
        "failed_cases": trimmed_failures,
        "retrieval_tuning": retrieval_tuning or {},
        "retrieval_context": retrieval_context or {},
    }
    try:
        failure_questions = [
            str(item.get("question") or "").strip()
            for item in failures
            if isinstance(item, dict) and str(item.get("question") or "").strip()
        ]
        fallback_proposed, fallback_rationale = _build_fallback_suggestion(
            tool_id=tool_id,
            current=current,
            questions=failure_questions,
            failed_count=len(failure_questions),
        )
        response = await asyncio.wait_for(
            model.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
                ]
            ),
            timeout=_TOOL_METADATA_LLM_TIMEOUT_SECONDS,
        )
        text = str(getattr(response, "content", "") or "")
        parsed = _extract_json_object(text)
        if not parsed:
            return None
        parsed_examples = _sanitize_example_queries_no_tool_refs(
            [
                value
                for value in _safe_string_list(parsed.get("example_queries"))
                if not _looks_english_text(value)
            ],
            forbidden_markers=forbidden_markers,
        )
        fallback_examples = _sanitize_example_queries_no_tool_refs(
            list(fallback_proposed.get("example_queries") or []),
            forbidden_markers=forbidden_markers,
        )
        current_examples = _sanitize_example_queries_no_tool_refs(
            list(current.get("example_queries") or []),
            forbidden_markers=forbidden_markers,
        )
        suggested = {
            "tool_id": tool_id,
            "name": str(parsed.get("name") or current.get("name") or "").strip(),
            "description": _prefer_swedish_text(
                str(parsed.get("description") or current.get("description") or "").strip(),
                str(fallback_proposed.get("description") or current.get("description") or ""),
            ),
            "keywords": _safe_string_list(parsed.get("keywords"))
            or list(current.get("keywords") or []),
            "example_queries": parsed_examples or fallback_examples or current_examples,
            "category": str(
                parsed.get("category") or current.get("category") or ""
            ).strip(),
            "base_path": current.get("base_path"),
            "main_identifier": str(
                parsed.get("main_identifier") or current.get("main_identifier") or ""
            ).strip(),
            "core_activity": str(
                parsed.get("core_activity") or current.get("core_activity") or ""
            ).strip(),
            "unique_scope": str(
                parsed.get("unique_scope") or current.get("unique_scope") or ""
            ).strip(),
            "geographic_scope": str(
                parsed.get("geographic_scope") or current.get("geographic_scope") or ""
            ).strip(),
            "excludes": _safe_string_list(parsed.get("excludes"))
            or _safe_string_list(current.get("excludes")),
        }
        rationale = _prefer_swedish_text(
            str(parsed.get("rationale") or "").strip(),
            fallback_rationale
            or "LLM-förslag för metadata baserat på misslyckade eval-fall.",
        )
        if not rationale:
            rationale = "LLM-förslag för metadata baserat på misslyckade eval-fall."
        return suggested, rationale
    except Exception:
        return None


def _metadata_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_payload = {
        "name": str(left.get("name") or "").strip(),
        "description": str(left.get("description") or "").strip(),
        "keywords": _safe_string_list(left.get("keywords")),
        "example_queries": _safe_string_list(left.get("example_queries")),
        "category": str(left.get("category") or "").strip(),
        "base_path": (str(left.get("base_path")).strip() if left.get("base_path") else None),
        "main_identifier": str(left.get("main_identifier") or "").strip(),
        "core_activity": str(left.get("core_activity") or "").strip(),
        "unique_scope": str(left.get("unique_scope") or "").strip(),
        "geographic_scope": str(left.get("geographic_scope") or "").strip(),
        "excludes": _safe_string_list(left.get("excludes")),
    }
    right_payload = {
        "name": str(right.get("name") or "").strip(),
        "description": str(right.get("description") or "").strip(),
        "keywords": _safe_string_list(right.get("keywords")),
        "example_queries": _safe_string_list(right.get("example_queries")),
        "category": str(right.get("category") or "").strip(),
        "base_path": (
            str(right.get("base_path")).strip() if right.get("base_path") else None
        ),
        "main_identifier": str(right.get("main_identifier") or "").strip(),
        "core_activity": str(right.get("core_activity") or "").strip(),
        "unique_scope": str(right.get("unique_scope") or "").strip(),
        "geographic_scope": str(right.get("geographic_scope") or "").strip(),
        "excludes": _safe_string_list(right.get("excludes")),
    }
    return left_payload == right_payload


def _enrich_metadata_suggestion_fields(
    *,
    current: dict[str, Any],
    proposed: dict[str, Any],
    fallback: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    merged = dict(proposed)
    enriched = False
    forbidden_markers = _tool_reference_markers_for_suggestions(
        tool_id=str(current.get("tool_id") or merged.get("tool_id") or ""),
        tool_name=str(current.get("name") or merged.get("name") or ""),
    )

    current_description = str(current.get("description") or "").strip()
    proposed_description = str(merged.get("description") or "").strip()
    fallback_description = str(fallback.get("description") or "").strip()
    if (
        proposed_description == current_description
        and fallback_description
        and fallback_description != current_description
    ):
        merged["description"] = fallback_description
        enriched = True

    current_keywords = _safe_string_list(current.get("keywords"))
    proposed_keywords = _safe_string_list(merged.get("keywords"))
    fallback_keywords = _safe_string_list(fallback.get("keywords"))
    if proposed_keywords == current_keywords and fallback_keywords != current_keywords:
        merged["keywords"] = fallback_keywords
        enriched = True
    else:
        merged["keywords"] = proposed_keywords

    current_examples = _sanitize_example_queries_no_tool_refs(
        _safe_string_list(current.get("example_queries")),
        forbidden_markers=forbidden_markers,
    )
    proposed_examples = _sanitize_example_queries_no_tool_refs(
        _safe_string_list(merged.get("example_queries")),
        forbidden_markers=forbidden_markers,
    )
    fallback_examples = _sanitize_example_queries_no_tool_refs(
        _safe_string_list(fallback.get("example_queries")),
        forbidden_markers=forbidden_markers,
    )
    if proposed_examples == current_examples and fallback_examples != current_examples:
        merged["example_queries"] = fallback_examples
        enriched = True
    else:
        merged["example_queries"] = proposed_examples

    # Propagate identity fields from proposed or fallback
    for field in ("main_identifier", "core_activity", "unique_scope", "geographic_scope"):
        current_val = str(current.get(field) or "").strip()
        proposed_val = str(merged.get(field) or "").strip()
        fallback_val = str(fallback.get(field) or "").strip()
        if proposed_val == current_val and fallback_val and fallback_val != current_val:
            merged[field] = fallback_val
            enriched = True
        elif proposed_val:
            merged[field] = proposed_val

    current_excludes = _safe_string_list(current.get("excludes"))
    proposed_excludes = _safe_string_list(merged.get("excludes"))
    fallback_excludes = _safe_string_list(fallback.get("excludes"))
    if proposed_excludes == current_excludes and fallback_excludes != current_excludes:
        merged["excludes"] = fallback_excludes
        enriched = True
    elif proposed_excludes:
        merged["excludes"] = proposed_excludes

    if "tool_id" not in merged:
        merged["tool_id"] = str(current.get("tool_id") or "")
    return merged, enriched


async def run_tool_evaluation(
    *,
    tests: list[dict[str, Any]],
    tool_index: list[ToolIndexEntry],
    llm,
    retrieval_limit: int = 5,
    use_llm_supervisor_review: bool = True,
    retrieval_tuning: dict[str, Any] | None = None,
    prompt_overrides: dict[str, str] | None = None,
    intent_definitions: list[dict[str, Any]] | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    retrieval_limit = max(1, min(int(retrieval_limit or 5), 15))
    normalized_tuning = normalize_retrieval_tuning(retrieval_tuning)
    index_by_id = {entry.tool_id: entry for entry in tool_index}
    results: list[dict[str, Any]] = []

    intent_checks: list[bool] = []
    route_checks: list[bool] = []
    sub_route_checks: list[bool] = []
    graph_complexity_checks: list[bool] = []
    execution_strategy_checks: list[bool] = []
    agent_checks: list[bool] = []
    gated_scores: list[float] = []
    plan_checks: list[bool] = []
    supervisor_review_scores: list[float] = []
    supervisor_review_pass_checks: list[bool] = []
    category_checks: list[bool] = []
    tool_checks: list[bool] = []
    retrieval_checks: list[bool] = []
    difficulty_buckets: dict[str, dict[str, Any]] = {}

    for idx, test in enumerate(tests):
        test_id = str(test.get("id") or f"case-{idx + 1}")
        question = str(test.get("question") or "").strip()
        difficulty = _normalize_difficulty_value(test.get("difficulty"))
        consistency_warnings = _safe_string_list(test.get("consistency_warnings"))
        expected_normalized = bool(test.get("expected_normalized"))
        if progress_callback is not None:
            event = {
                "type": "test_started",
                "test_id": test_id,
                "index": idx,
                "question": question,
                "consistency_warnings": consistency_warnings,
                "expected_normalized": expected_normalized,
            }
            maybe_result = progress_callback(event)
            if hasattr(maybe_result, "__await__"):
                await maybe_result
        expected = test.get("expected") or {}
        if not isinstance(expected, dict):
            expected = {}
        expected_route = _normalize_route_value(expected.get("route"))
        expected_sub_route = _normalize_sub_route_value(expected.get("sub_route"))
        plan_requirements = _safe_string_list(expected.get("plan_requirements"))
        expected_tool = expected.get("tool")
        expected_tool = str(expected_tool).strip() if expected_tool else None
        expected_category = expected.get("category")
        expected_category = (
            str(expected_category).strip() if expected_category else None
        )
        expected_route, expected_sub_route = _repair_expected_routing(
            expected_route=expected_route,
            expected_sub_route=expected_sub_route,
            expected_tool=expected_tool,
            expected_category=expected_category,
        )
        expected_intent = _infer_expected_intent_id(
            expected=expected,
            expected_route=expected_route,
            intent_definitions=intent_definitions,
        )
        expected_agent = _normalize_agent_name(expected.get("agent"))
        if expected_agent is None:
            expected_agent = _agent_for_tool(
                expected_tool,
                expected_category,
                expected_route,
                expected_sub_route,
            )
        expected_acceptable_agents = _normalize_expected_agent_candidates(
            expected_agent=expected_agent,
            expected_payload=expected,
        )
        expected_acceptable_tools = _dedupe_strings(
            [
                expected_tool or "",
                *_safe_string_list(expected.get("acceptable_tools")),
            ]
        )
        expected_graph_complexity = _normalize_graph_complexity(
            expected.get("graph_complexity")
        )
        expected_execution_strategy = _normalize_execution_strategy(
            expected.get("execution_strategy")
        )
        allowed_tools = _safe_string_list(test.get("allowed_tools"))
        if expected_acceptable_tools:
            allowed_tools = _dedupe_strings([*expected_acceptable_tools, *allowed_tools])
        if expected_tool and not allowed_tools:
            allowed_tools = [expected_tool]

        selected_route: str | None = None
        selected_sub_route: str | None = None
        selected_intent: str | None = None
        selected_agent: str | None = None
        selected_graph_complexity: str | None = None
        selected_execution_strategy: str | None = None
        passed_intent: bool | None = None
        passed_route: bool | None = None
        passed_sub_route: bool | None = None
        passed_graph_complexity: bool | None = None
        passed_execution_strategy: bool | None = None
        passed_agent: bool | None = None
        passed_plan: bool | None = None
        selected_agent_analysis = ""
        plan_requirement_checks: list[dict[str, Any]] = []
        supervisor_trace: dict[str, Any] = {}
        supervisor_review_score: float | None = None
        supervisor_review_passed: bool | None = None
        supervisor_review_rationale: str | None = None
        supervisor_review_issues: list[str] = []
        supervisor_review_rubric: list[dict[str, Any]] = []

        try:
            (
                selected_route,
                selected_sub_route,
                selected_intent,
                route_decision,
            ) = await _dispatch_route_from_start(
                question=question,
                llm=llm,
                prompt_overrides=prompt_overrides,
                intent_definitions=intent_definitions,
            )
            passed_intent = (
                _normalize_intent_id(selected_intent)
                == _normalize_intent_id(expected_intent)
                if expected_intent is not None
                else None
            )
            passed_route = (
                selected_route == expected_route if expected_route is not None else None
            )
            passed_sub_route = (
                selected_sub_route == expected_sub_route
                if expected_sub_route is not None
                else None
            )
            selected_graph_complexity = _infer_graph_complexity_for_eval(
                question=question,
                selected_route=selected_route,
                selected_intent=selected_intent,
                route_decision=route_decision,
            )
            passed_graph_complexity = (
                selected_graph_complexity == expected_graph_complexity
                if expected_graph_complexity is not None
                else None
            )
            selected_agent_plan = await _plan_agent_choice(
                question=question,
                route_value=selected_route,
                sub_route_value=selected_sub_route,
                llm=llm,
            )
            selected_agent = _normalize_agent_name(selected_agent_plan.get("selected_agent"))
            selected_agent_analysis = str(
                selected_agent_plan.get("analysis") or ""
            ).strip()
            passed_agent = (
                selected_agent in expected_acceptable_agents
                if expected_acceptable_agents
                else (selected_agent == expected_agent if expected_agent is not None else None)
            )
            retrieved_ids, retrieval_breakdown = smart_retrieve_tools_with_breakdown(
                question,
                tool_index=tool_index,
                primary_namespaces=[("tools",)],
                fallback_namespaces=[],
                limit=max(retrieval_limit, 8),
                trace_key=None,
                tuning=normalized_tuning,
            )
            retrieved_entries = [
                index_by_id[tool_id]
                for tool_id in retrieved_ids
                if tool_id in index_by_id
            ]
            planning = await _plan_tool_choice(
                question=question,
                candidates=retrieved_entries[:8],
                llm=llm,
            )
            selected_tool = planning.get("selected_tool_id")
            if selected_tool and selected_tool not in index_by_id:
                selected_tool = retrieved_ids[0] if retrieved_ids else None
            if not selected_tool:
                selected_tool = retrieved_ids[0] if retrieved_ids else None
            selected_entry = index_by_id.get(selected_tool) if selected_tool else None
            selected_category = (
                selected_entry.category
                if selected_entry
                else planning.get("selected_category")
            )
            if selected_agent is None:
                selected_agent = _agent_for_tool(
                    selected_tool,
                    selected_category,
                    selected_route,
                    selected_sub_route,
                )
            coerced_agent, coerced = _coerce_weather_agent_choice(
                selected_agent=selected_agent,
                selected_tool=selected_tool,
                selected_category=selected_category,
                route_value=selected_route,
                sub_route_value=selected_sub_route,
            )
            if coerced:
                selected_agent = coerced_agent
                if selected_agent_analysis:
                    selected_agent_analysis = (
                        f"{selected_agent_analysis} Agent justerad till weather baserat på väderverktyg."
                    )
                else:
                    selected_agent_analysis = (
                        "Agent justerad till weather baserat på valt väderverktyg."
                    )
            if expected_acceptable_agents:
                passed_agent = selected_agent in expected_acceptable_agents
            elif expected_agent is not None:
                passed_agent = selected_agent == expected_agent
            selected_execution_strategy = _infer_execution_strategy_for_eval(
                question=question,
                selected_agent=selected_agent,
                selected_tool=selected_tool,
                planning_steps=_safe_string_list(planning.get("plan_steps")),
            )
            passed_execution_strategy = (
                selected_execution_strategy == expected_execution_strategy
                if expected_execution_strategy is not None
                else None
            )
            plan_requirement_checks, passed_plan = _evaluate_plan_requirements(
                requirements=plan_requirements,
                planning_analysis=str(planning.get("analysis") or ""),
                planning_steps=_safe_string_list(planning.get("plan_steps")),
                context={
                    "selected_tool": selected_tool,
                    "selected_route": selected_route,
                    "selected_agent": selected_agent,
                    "proposed_arguments": {},
                    "needs_clarification": False,
                },
            )
            supervisor_trace = _build_supervisor_trace(
                question=question,
                expected_intent=expected_intent,
                expected_route=expected_route,
                expected_sub_route=expected_sub_route,
                expected_agent=expected_agent,
                expected_tool=expected_tool,
                expected_graph_complexity=expected_graph_complexity,
                expected_execution_strategy=expected_execution_strategy,
                selected_intent=selected_intent,
                selected_route=selected_route,
                selected_sub_route=selected_sub_route,
                selected_agent=selected_agent,
                selected_tool=selected_tool,
                selected_graph_complexity=selected_graph_complexity,
                selected_execution_strategy=selected_execution_strategy,
                agent_selection_analysis=selected_agent_analysis,
                planning_analysis=str(planning.get("analysis") or ""),
                planning_steps=_safe_string_list(planning.get("plan_steps")),
                plan_requirement_checks=plan_requirement_checks,
            )
            supervisor_review = await _review_supervisor_trace(
                supervisor_trace=supervisor_trace,
                llm=llm if use_llm_supervisor_review else None,
            )
            raw_supervisor_score = supervisor_review.get("score")
            supervisor_review_score = (
                float(raw_supervisor_score)
                if isinstance(raw_supervisor_score, (int, float))
                else None
            )
            if supervisor_review_score is not None:
                supervisor_review_score = max(0.0, min(1.0, supervisor_review_score))
                supervisor_review_scores.append(supervisor_review_score)
            supervisor_review_passed = (
                bool(supervisor_review.get("passed"))
                if isinstance(supervisor_review.get("passed"), bool)
                else None
            )
            if supervisor_review_passed is not None:
                supervisor_review_pass_checks.append(bool(supervisor_review_passed))
            supervisor_review_rationale = str(
                supervisor_review.get("rationale") or ""
            ).strip() or None
            supervisor_review_issues = _safe_string_list(
                supervisor_review.get("issues")
            )
            supervisor_review_rubric = list(supervisor_review.get("rubric") or [])
            selected_category_norm = _normalize_category_name(selected_category)
            expected_category_norm = _normalize_category_name(expected_category)
            passed_category = (
                selected_category_norm == expected_category_norm
                if expected_category is not None
                else None
            )
            passed_tool = (
                selected_tool in set(allowed_tools)
                if expected_tool is not None
                else None
            )
            checks = [
                check
                for check in (
                    passed_intent,
                    passed_route,
                    passed_sub_route,
                    passed_graph_complexity,
                    passed_execution_strategy,
                    passed_agent,
                    passed_plan,
                    passed_category,
                    passed_tool,
                )
                if check is not None
            ]
            passed = all(checks) if checks else True
            agent_gate_score, passed_with_agent_gate = _compute_agent_gate_score(
                upstream_checks=[
                    passed_route,
                    passed_sub_route,
                    passed_graph_complexity,
                    passed_execution_strategy,
                    passed_agent,
                    passed_plan,
                ],
                downstream_checks=[passed_category, passed_tool],
            )
            retrieval_hit_expected_tool = (
                expected_tool in retrieved_ids[:retrieval_limit]
                if expected_tool is not None
                else None
            )
            if agent_gate_score is not None:
                gated_scores.append(float(agent_gate_score))

            if passed_intent is not None:
                intent_checks.append(bool(passed_intent))
            if passed_route is not None:
                route_checks.append(bool(passed_route))
            if passed_sub_route is not None:
                sub_route_checks.append(bool(passed_sub_route))
            if passed_graph_complexity is not None:
                graph_complexity_checks.append(bool(passed_graph_complexity))
            if passed_execution_strategy is not None:
                execution_strategy_checks.append(bool(passed_execution_strategy))
            if passed_agent is not None:
                agent_checks.append(bool(passed_agent))
            if passed_plan is not None:
                plan_checks.append(bool(passed_plan))
            if passed_category is not None:
                category_checks.append(bool(passed_category))
            if passed_tool is not None:
                tool_checks.append(bool(passed_tool))
            if retrieval_hit_expected_tool is not None:
                retrieval_checks.append(bool(retrieval_hit_expected_tool))

            case_result = {
                "test_id": test_id,
                "question": question,
                "difficulty": difficulty,
                "expected_intent": expected_intent,
                "expected_route": expected_route,
                "expected_sub_route": expected_sub_route,
                "expected_graph_complexity": expected_graph_complexity,
                "expected_execution_strategy": expected_execution_strategy,
                "expected_agent": expected_agent,
                "expected_acceptable_agents": expected_acceptable_agents,
                "expected_category": expected_category,
                "expected_tool": expected_tool,
                "expected_acceptable_tools": expected_acceptable_tools,
                "allowed_tools": allowed_tools,
                "selected_route": selected_route,
                "selected_sub_route": selected_sub_route,
                "selected_intent": selected_intent,
                "selected_graph_complexity": selected_graph_complexity,
                "selected_execution_strategy": selected_execution_strategy,
                "selected_agent": selected_agent,
                "agent_selection_analysis": selected_agent_analysis,
                "selected_category": selected_category,
                "selected_tool": selected_tool,
                "planning_analysis": planning.get("analysis") or "",
                "planning_steps": _safe_string_list(planning.get("plan_steps")),
                "supervisor_trace": supervisor_trace,
                "supervisor_review_score": supervisor_review_score,
                "supervisor_review_passed": supervisor_review_passed,
                "supervisor_review_rationale": supervisor_review_rationale,
                "supervisor_review_issues": supervisor_review_issues,
                "supervisor_review_rubric": supervisor_review_rubric,
                "plan_requirement_checks": plan_requirement_checks,
                "retrieval_top_tools": retrieved_ids[:retrieval_limit],
                "retrieval_top_categories": [
                    index_by_id[tool_id].category
                    for tool_id in retrieved_ids[:retrieval_limit]
                    if tool_id in index_by_id
                ],
                "retrieval_breakdown": retrieval_breakdown[:retrieval_limit],
                "retrieval_hit_expected_tool": retrieval_hit_expected_tool,
                "consistency_warnings": consistency_warnings,
                "expected_normalized": expected_normalized,
                "passed_intent": passed_intent,
                "passed_route": passed_route,
                "passed_sub_route": passed_sub_route,
                "passed_graph_complexity": passed_graph_complexity,
                "passed_execution_strategy": passed_execution_strategy,
                "passed_agent": passed_agent,
                "passed_plan": passed_plan,
                "passed_category": passed_category,
                "passed_tool": passed_tool,
                "passed_with_agent_gate": passed_with_agent_gate,
                "agent_gate_score": agent_gate_score,
                "passed": passed,
            }
            _update_difficulty_bucket(
                difficulty_buckets=difficulty_buckets,
                difficulty=difficulty,
                passed=bool(passed),
                gated_score=agent_gate_score,
            )
            results.append(case_result)
            if progress_callback is not None:
                event = {
                    "type": "test_completed",
                    "test_id": test_id,
                    "index": idx,
                    "selected_intent": selected_intent,
                    "selected_route": selected_route,
                    "selected_sub_route": selected_sub_route,
                    "selected_graph_complexity": selected_graph_complexity,
                    "selected_execution_strategy": selected_execution_strategy,
                    "selected_agent": selected_agent,
                    "agent_selection_analysis": selected_agent_analysis,
                    "selected_tool": selected_tool,
                    "selected_category": selected_category,
                    "consistency_warnings": consistency_warnings,
                    "expected_normalized": expected_normalized,
                    "passed": passed,
                }
                maybe_result = progress_callback(event)
                if hasattr(maybe_result, "__await__"):
                    await maybe_result
        except Exception as exc:
            failed_supervisor_trace = _build_supervisor_trace(
                question=question,
                expected_intent=expected_intent,
                expected_route=expected_route,
                expected_sub_route=expected_sub_route,
                expected_agent=expected_agent,
                expected_tool=expected_tool,
                expected_graph_complexity=expected_graph_complexity,
                expected_execution_strategy=expected_execution_strategy,
                selected_intent=selected_intent,
                selected_route=selected_route,
                selected_sub_route=selected_sub_route,
                selected_agent=selected_agent,
                selected_tool=None,
                selected_graph_complexity=selected_graph_complexity,
                selected_execution_strategy=selected_execution_strategy,
                agent_selection_analysis=selected_agent_analysis,
                planning_analysis=f"Evaluation failed for this case: {exc}",
                planning_steps=[],
                plan_requirement_checks=[],
            )
            failed_supervisor_review = _fallback_supervisor_trace_review(
                supervisor_trace=failed_supervisor_trace
            )
            results.append(
                {
                    "test_id": test_id,
                    "question": question,
                    "difficulty": difficulty,
                    "expected_intent": expected_intent,
                    "expected_route": expected_route,
                    "expected_sub_route": expected_sub_route,
                    "expected_graph_complexity": expected_graph_complexity,
                    "expected_execution_strategy": expected_execution_strategy,
                    "expected_agent": expected_agent,
                    "expected_acceptable_agents": expected_acceptable_agents,
                    "expected_category": expected_category,
                    "expected_tool": expected_tool,
                    "expected_acceptable_tools": expected_acceptable_tools,
                    "allowed_tools": allowed_tools,
                    "selected_route": selected_route,
                    "selected_sub_route": selected_sub_route,
                    "selected_intent": selected_intent,
                    "selected_graph_complexity": selected_graph_complexity,
                    "selected_execution_strategy": selected_execution_strategy,
                    "selected_agent": selected_agent,
                    "agent_selection_analysis": selected_agent_analysis,
                    "selected_category": None,
                    "selected_tool": None,
                    "planning_analysis": f"Evaluation failed for this case: {exc}",
                    "planning_steps": [],
                    "supervisor_trace": failed_supervisor_trace,
                    "supervisor_review_score": 0.0,
                    "supervisor_review_passed": False,
                    "supervisor_review_rationale": "Supervisor-spåret kunde inte granskas eftersom eval-fallet avbröts av fel.",
                    "supervisor_review_issues": [str(exc)],
                    "supervisor_review_rubric": list(
                        failed_supervisor_review.get("rubric") or []
                    ),
                    "plan_requirement_checks": [],
                    "retrieval_top_tools": [],
                    "retrieval_top_categories": [],
                    "retrieval_breakdown": [],
                    "retrieval_hit_expected_tool": None,
                    "consistency_warnings": consistency_warnings,
                    "expected_normalized": expected_normalized,
                    "passed_intent": False if expected_intent is not None else None,
                    "passed_route": False if expected_route is not None else None,
                    "passed_sub_route": False if expected_sub_route is not None else None,
                    "passed_graph_complexity": (
                        False if expected_graph_complexity is not None else None
                    ),
                    "passed_execution_strategy": (
                        False if expected_execution_strategy is not None else None
                    ),
                    "passed_agent": False if expected_agent is not None else None,
                    "passed_plan": False if plan_requirements else None,
                    "passed_category": False if expected_category is not None else None,
                    "passed_tool": False if expected_tool is not None else None,
                    "passed_with_agent_gate": False,
                    "agent_gate_score": 0.0,
                    "passed": False,
                }
            )
            _update_difficulty_bucket(
                difficulty_buckets=difficulty_buckets,
                difficulty=difficulty,
                passed=False,
                gated_score=0.0,
            )
            gated_scores.append(0.0)
            supervisor_review_scores.append(0.0)
            supervisor_review_pass_checks.append(False)
            if expected_intent is not None:
                intent_checks.append(False)
            if expected_route is not None:
                route_checks.append(False)
            if expected_sub_route is not None:
                sub_route_checks.append(False)
            if expected_graph_complexity is not None:
                graph_complexity_checks.append(False)
            if expected_execution_strategy is not None:
                execution_strategy_checks.append(False)
            if expected_agent is not None:
                agent_checks.append(False)
            if plan_requirements:
                plan_checks.append(False)
            if expected_category is not None:
                category_checks.append(False)
            if expected_tool is not None:
                tool_checks.append(False)
                retrieval_checks.append(False)
            if progress_callback is not None:
                event = {
                    "type": "test_failed",
                    "test_id": test_id,
                    "index": idx,
                    "consistency_warnings": consistency_warnings,
                    "expected_normalized": expected_normalized,
                    "error": str(exc),
                }
                maybe_result = progress_callback(event)
                if hasattr(maybe_result, "__await__"):
                    await maybe_result

    total_tests = len(results)
    passed_count = sum(1 for item in results if item.get("passed"))
    metrics = {
        "total_tests": total_tests,
        "passed_tests": passed_count,
        "success_rate": (passed_count / total_tests) if total_tests else 0.0,
        "gated_success_rate": (
            sum(gated_scores) / len(gated_scores)
            if gated_scores
            else None
        ),
        "intent_accuracy": (
            sum(1 for check in intent_checks if check) / len(intent_checks)
            if intent_checks
            else None
        ),
        "route_accuracy": (
            sum(1 for check in route_checks if check) / len(route_checks)
            if route_checks
            else None
        ),
        "sub_route_accuracy": (
            sum(1 for check in sub_route_checks if check) / len(sub_route_checks)
            if sub_route_checks
            else None
        ),
        "graph_complexity_accuracy": (
            sum(1 for check in graph_complexity_checks if check)
            / len(graph_complexity_checks)
            if graph_complexity_checks
            else None
        ),
        "execution_strategy_accuracy": (
            sum(1 for check in execution_strategy_checks if check)
            / len(execution_strategy_checks)
            if execution_strategy_checks
            else None
        ),
        "agent_accuracy": (
            sum(1 for check in agent_checks if check) / len(agent_checks)
            if agent_checks
            else None
        ),
        "plan_accuracy": (
            sum(1 for check in plan_checks if check) / len(plan_checks)
            if plan_checks
            else None
        ),
        "supervisor_review_score": (
            sum(supervisor_review_scores) / len(supervisor_review_scores)
            if supervisor_review_scores
            else None
        ),
        "supervisor_review_pass_rate": (
            sum(1 for check in supervisor_review_pass_checks if check)
            / len(supervisor_review_pass_checks)
            if supervisor_review_pass_checks
            else None
        ),
        "category_accuracy": (
            sum(1 for check in category_checks if check) / len(category_checks)
            if category_checks
            else None
        ),
        "tool_accuracy": (
            sum(1 for check in tool_checks if check) / len(tool_checks)
            if tool_checks
            else None
        ),
        "retrieval_recall_at_k": (
            sum(1 for check in retrieval_checks if check) / len(retrieval_checks)
            if retrieval_checks
            else None
        ),
        "difficulty_breakdown": _build_difficulty_breakdown(difficulty_buckets),
        "namespace_confusion": build_namespace_confusion_matrix(results),
    }
    return {"metrics": metrics, "results": results}


async def generate_tool_metadata_suggestions(
    *,
    evaluation_results: list[dict[str, Any]],
    tool_index: list[ToolIndexEntry],
    llm=None,
    retrieval_tuning: dict[str, Any] | None = None,
    retrieval_context: dict[str, Any] | None = None,
    max_suggestions: int = 20,
    parallelism: int = 1,
) -> list[dict[str, Any]]:
    index_by_id = {entry.tool_id: entry for entry in tool_index}
    effective_retrieval_context = dict(retrieval_context or {})
    effective_retrieval_context.setdefault("vector_recall_top_k", get_vector_recall_top_k())
    effective_retrieval_context.setdefault(
        "tool_embedding_context_fields",
        get_tool_embedding_context_fields(),
    )
    grouped: dict[str, dict[str, Any]] = {}

    for result in evaluation_results:
        expected_tool = result.get("expected_tool")
        if not expected_tool or result.get("passed_tool") is True:
            continue
        if expected_tool not in index_by_id:
            continue
        bucket = grouped.setdefault(
            expected_tool,
            {"questions": [], "failed_test_ids": [], "wrong_tools": [], "failures": []},
        )
        question = str(result.get("question") or "").strip()
        if question:
            bucket["questions"].append(question)
        test_id = str(result.get("test_id") or "").strip()
        if test_id:
            bucket["failed_test_ids"].append(test_id)
        wrong_tool = str(result.get("selected_tool") or "").strip()
        if wrong_tool and wrong_tool != expected_tool:
            bucket["wrong_tools"].append(wrong_tool)
        retrieval_breakdown = (
            list(result.get("retrieval_breakdown"))
            if isinstance(result.get("retrieval_breakdown"), list)
            else []
        )
        tool_vector_diagnostics = (
            dict(result.get("tool_vector_diagnostics"))
            if isinstance(result.get("tool_vector_diagnostics"), dict)
            else {}
        )
        bucket["failures"].append(
            {
                "question": question,
                "selected_wrong_tool": wrong_tool if wrong_tool and wrong_tool != expected_tool else None,
                "retrieval_breakdown": retrieval_breakdown[:5],
                "tool_vector_diagnostics": tool_vector_diagnostics,
            }
        )

    normalized_max_suggestions = max(1, int(max_suggestions))
    try:
        normalized_parallelism = int(parallelism or 1)
    except Exception:
        normalized_parallelism = 1
    normalized_parallelism = max(1, min(normalized_parallelism, 32))
    grouped_items = list(grouped.items())

    async def _suggest_for_tool(
        tool_id: str,
        failure_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        entry = index_by_id[tool_id]
        current = _serialize_tool(entry)
        current["base_path"] = entry.base_path
        failures = list(failure_data.get("failures") or [])

        llm_suggestion = await _build_llm_suggestion(
            tool_id=tool_id,
            llm=llm,
            current=current,
            failures=failures,
            retrieval_tuning=retrieval_tuning,
            retrieval_context=effective_retrieval_context,
        )
        fallback_proposed, fallback_rationale = _build_fallback_suggestion(
            tool_id=tool_id,
            current=current,
            questions=failure_data["questions"],
            failed_count=len(failure_data["questions"]),
        )
        if llm_suggestion is not None:
            proposed, rationale = llm_suggestion
            proposed, enriched = _enrich_metadata_suggestion_fields(
                current=current,
                proposed=proposed,
                fallback=fallback_proposed,
            )
            if enriched:
                rationale = (
                    f"{rationale} Lade till fallback-förbättringar för beskrivning, "
                    "nyckelord och exempelfrågor från misslyckade fall."
                )
        else:
            proposed, rationale = fallback_proposed, fallback_rationale
        if _metadata_equal(current, proposed):
            return None
        return {
            "tool_id": tool_id,
            "failed_test_ids": list(failure_data["failed_test_ids"]),
            "rationale": rationale,
            "current_metadata": current,
            "proposed_metadata": proposed,
        }

    suggestions: list[dict[str, Any]] = []
    if normalized_parallelism <= 1:
        for tool_id, failure_data in grouped_items:
            suggestion = await _suggest_for_tool(tool_id, failure_data)
            if suggestion is None:
                continue
            suggestions.append(suggestion)
            if len(suggestions) >= normalized_max_suggestions:
                break
    else:
        semaphore = asyncio.Semaphore(normalized_parallelism)

        async def _run_with_limit(
            tool_id: str,
            failure_data: dict[str, Any],
        ) -> dict[str, Any] | None:
            async with semaphore:
                return await _suggest_for_tool(tool_id, failure_data)

        for start in range(0, len(grouped_items), normalized_parallelism):
            chunk = grouped_items[start : start + normalized_parallelism]
            chunk_results = await asyncio.gather(
                *[_run_with_limit(tool_id, failure_data) for tool_id, failure_data in chunk]
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


async def suggest_intent_definition_improvements(
    *,
    evaluation_results: list[dict[str, Any]],
    intent_definitions: list[dict[str, Any]] | None,
    current_prompts: dict[str, str],
    llm=None,
    max_suggestions: int = 8,
) -> list[dict[str, Any]]:
    definitions_by_id: dict[str, dict[str, Any]] = {}
    for definition in intent_definitions or []:
        if not isinstance(definition, dict):
            continue
        intent_id = _normalize_intent_id(definition.get("intent_id"))
        if not intent_id:
            continue
        definitions_by_id[intent_id] = {
            "intent_id": intent_id,
            "route": _normalize_route_value(definition.get("route")) or Route.KUNSKAP.value,
            "label": str(definition.get("label") or intent_id).strip(),
            "description": str(definition.get("description") or "").strip(),
            "keywords": _safe_string_list(definition.get("keywords")),
            "priority": int(definition.get("priority") or 500),
            "enabled": bool(definition.get("enabled", True)),
        }

    grouped: dict[str, dict[str, Any]] = {}
    for result in evaluation_results:
        if result.get("passed_intent") is not False:
            continue
        expected_intent = _normalize_intent_id(result.get("expected_intent"))
        if not expected_intent:
            continue
        bucket = grouped.setdefault(
            expected_intent,
            {
                "failed_test_ids": [],
                "questions": [],
                "selected_intents": [],
                "expected_route": _normalize_route_value(result.get("expected_route")),
            },
        )
        test_id = str(result.get("test_id") or "").strip()
        if test_id:
            bucket["failed_test_ids"].append(test_id)
        question = str(result.get("question") or "").strip()
        if question:
            bucket["questions"].append(question)
        selected_intent = _normalize_intent_id(result.get("selected_intent"))
        if selected_intent and selected_intent != expected_intent:
            bucket["selected_intents"].append(selected_intent)

    if not grouped:
        return []

    suggestions: list[dict[str, Any]] = []
    prompt_key = "supervisor.intent_resolver.system"
    current_prompt = str(current_prompts.get(prompt_key) or "").strip()
    for intent_id, bucket in grouped.items():
        if len(suggestions) >= max_suggestions:
            break
        current_definition = definitions_by_id.get(intent_id) or {
            "intent_id": intent_id,
            "route": str(bucket.get("expected_route") or Route.KUNSKAP.value),
            "label": intent_id.replace("_", " ").title(),
            "description": "",
            "keywords": [],
            "priority": 500,
            "enabled": True,
        }

        token_counts: dict[str, int] = {}
        for question in list(bucket.get("questions") or []):
            for token in _tokenize_for_suggestions(question):
                token_counts[token] = token_counts.get(token, 0) + 1
        sorted_tokens = [
            token for token, _count in sorted(token_counts.items(), key=lambda item: item[1], reverse=True)
        ]
        proposed_keywords = list(_safe_string_list(current_definition.get("keywords")))
        existing_set = {item.casefold() for item in proposed_keywords}
        for token in sorted_tokens:
            if token.casefold() in existing_set:
                continue
            proposed_keywords.append(token)
            existing_set.add(token.casefold())
            if len(proposed_keywords) >= 20:
                break
        proposed_description = str(current_definition.get("description") or "").strip()
        if sorted_tokens:
            hint = ", ".join(sorted_tokens[:3])
            marker = f"Vanliga fragetermer: {hint}."
            if marker not in proposed_description:
                proposed_description = f"{proposed_description} {marker}".strip()
        fallback_definition = {
            **current_definition,
            "keywords": proposed_keywords,
            "description": proposed_description,
        }
        fallback_rationale = (
            "Fallback-forslag for intent-metadata baserat pa misslyckade intent-fall: "
            "utokade nyckelord och tydligare beskrivning."
        )
        fallback_prompt = current_prompt
        if current_prompt and "intent" not in current_prompt.casefold():
            fallback_prompt = (
                f"{current_prompt.rstrip()}\n\n"
                "Kontrollera intent-match innan route finaliseras och valj alltid intent_id fran kandidaterna."
            ).strip()
        (
            fallback_prompt,
            fallback_architecture_violations,
            _fallback_architecture_severe,
        ) = _apply_prompt_architecture_guard(
            prompt_key=prompt_key,
            prompt_text=fallback_prompt or current_prompt,
        )
        if fallback_architecture_violations:
            fallback_rationale = (
                f"{fallback_rationale} Arkitektur-guard justerade prompt-forslaget: "
                + "; ".join(fallback_architecture_violations[:3])
                + "."
            )

        proposed_definition = dict(fallback_definition)
        proposed_prompt = fallback_prompt or current_prompt or None
        rationale = fallback_rationale

        if llm is not None:
            model = llm
            try:
                if hasattr(llm, "bind"):
                    model = llm.bind(temperature=0)
            except Exception:
                model = llm
            llm_prompt = (
                "Du optimerar intent-definitioner for route/eval i SurfSense.\n"
                "ALL text maste vara pa svenska.\n"
                "Forbattra intentets metadata sa intent-val blir mer korrekt.\n"
                "Om promptforbattring behovs, foresla en uppdaterad prompt for supervisor.intent_resolver.system.\n"
                "Returnera strikt JSON:\n"
                "{\n"
                '  "proposed_definition": {\n'
                '    "intent_id": "string",\n'
                '    "route": "knowledge|action|statistics|compare|smalltalk",\n'
                '    "label": "string",\n'
                '    "description": "string pa svenska",\n'
                '    "keywords": ["svenska nyckelord"],\n'
                '    "priority": 100,\n'
                '    "enabled": true\n'
                "  },\n"
                '  "proposed_prompt": "string eller tom",\n'
                '  "rationale": "kort motivering pa svenska"\n'
                "}\n"
                "Ingen markdown."
            )
            llm_payload = {
                "current_definition": current_definition,
                "failed_test_ids": list(bucket.get("failed_test_ids") or []),
                "failed_questions": list(bucket.get("questions") or [])[:20],
                "wrong_selected_intents": list(bucket.get("selected_intents") or [])[:10],
                "current_prompt": current_prompt,
            }
            try:
                response = await model.ainvoke(
                    [
                        SystemMessage(content=llm_prompt),
                        HumanMessage(content=json.dumps(llm_payload, ensure_ascii=True)),
                    ]
                )
                parsed = _extract_json_object(
                    _response_content_to_text(getattr(response, "content", ""))
                )
                if isinstance(parsed, dict):
                    candidate_definition = parsed.get("proposed_definition")
                    if isinstance(candidate_definition, dict):
                        candidate_intent_id = (
                            _normalize_intent_id(candidate_definition.get("intent_id"))
                            or intent_id
                        )
                        candidate_route = (
                            _normalize_route_value(candidate_definition.get("route"))
                            or str(current_definition.get("route") or Route.KUNSKAP.value)
                        )
                        proposed_definition = {
                            "intent_id": candidate_intent_id,
                            "route": candidate_route,
                            "label": str(
                                candidate_definition.get("label")
                                or current_definition.get("label")
                                or candidate_intent_id
                            ).strip(),
                            "description": _prefer_swedish_text(
                                str(
                                    candidate_definition.get("description")
                                    or current_definition.get("description")
                                    or ""
                                ).strip(),
                                str(fallback_definition.get("description") or ""),
                            ),
                            "keywords": _safe_string_list(candidate_definition.get("keywords"))
                            or list(fallback_definition.get("keywords") or []),
                            "priority": int(
                                candidate_definition.get("priority")
                                or current_definition.get("priority")
                                or 500
                            ),
                            "enabled": bool(
                                candidate_definition.get("enabled")
                                if "enabled" in candidate_definition
                                else current_definition.get("enabled", True)
                            ),
                        }
                    candidate_prompt = str(parsed.get("proposed_prompt") or "").strip()
                    if candidate_prompt:
                        (
                            candidate_prompt,
                            _candidate_violations,
                            candidate_severe,
                        ) = _apply_prompt_architecture_guard(
                            prompt_key=prompt_key,
                            prompt_text=candidate_prompt,
                        )
                        if not candidate_severe:
                            proposed_prompt = candidate_prompt
                    rationale = _prefer_swedish_text(
                        str(parsed.get("rationale") or "").strip(),
                        fallback_rationale,
                    )
            except Exception:
                pass

        suggestions.append(
            {
                "intent_id": intent_id,
                "failed_test_ids": list(bucket.get("failed_test_ids") or []),
                "rationale": rationale,
                "current_definition": current_definition,
                "proposed_definition": proposed_definition,
                "prompt_key": prompt_key,
                "current_prompt": current_prompt or None,
                "proposed_prompt": proposed_prompt,
            }
        )

    return suggestions


async def suggest_retrieval_tuning(
    *,
    evaluation_results: list[dict[str, Any]],
    current_tuning: dict[str, Any],
    llm=None,
) -> dict[str, Any] | None:
    normalized_current = normalize_retrieval_tuning(current_tuning)
    total = len(evaluation_results)
    if total == 0:
        return None
    failed = [result for result in evaluation_results if not result.get("passed")]
    if not failed:
        return {
            "current_tuning": normalized_current.__dict__,
            "proposed_tuning": normalized_current.__dict__,
            "rationale": (
                "Inga ändringar i retrieval-tuning rekommenderas från denna körning. "
                "Nuvarande vikter gav redan bra resultat."
            ),
        }

    retrieval_checks = [
        result.get("retrieval_hit_expected_tool")
        for result in evaluation_results
        if result.get("retrieval_hit_expected_tool") is not None
    ]
    retrieval_recall = (
        (sum(1 for value in retrieval_checks if value) / len(retrieval_checks))
        if retrieval_checks
        else None
    )
    tool_checks = [
        result.get("passed_tool")
        for result in evaluation_results
        if result.get("passed_tool") is not None
    ]
    tool_accuracy = (
        (sum(1 for value in tool_checks if value) / len(tool_checks))
        if tool_checks
        else None
    )

    fallback_proposed = dict(normalized_current.__dict__)
    if retrieval_recall is not None and retrieval_recall < 0.75:
        fallback_proposed["keyword_weight"] = min(
            25.0, fallback_proposed["keyword_weight"] + 0.8
        )
        fallback_proposed["semantic_embedding_weight"] = min(
            25.0, fallback_proposed.get("semantic_embedding_weight", 0.0) + 0.8
        )
        fallback_proposed["structural_embedding_weight"] = min(
            25.0, fallback_proposed.get("structural_embedding_weight", 0.0) + 0.2
        )
        fallback_proposed["rerank_candidates"] = min(
            100, fallback_proposed["rerank_candidates"] + 8
        )
    elif tool_accuracy is not None and tool_accuracy < 0.75:
        fallback_proposed["namespace_boost"] = min(
            10.0, fallback_proposed["namespace_boost"] + 0.4
        )
        fallback_proposed["example_query_weight"] = min(
            10.0, fallback_proposed["example_query_weight"] + 0.4
        )
        fallback_proposed["rerank_candidates"] = min(
            100, fallback_proposed["rerank_candidates"] + 4
        )
    else:
        fallback_proposed["description_token_weight"] = min(
            10.0, fallback_proposed["description_token_weight"] + 0.2
        )

    fallback_proposed = normalize_retrieval_tuning(fallback_proposed).__dict__
    fallback_rationale = (
        "Fallback-förslag för retrieval-tuning baserat på eval-metrics: justerade "
        "lexikala/semantiska vikter och rerank-fönster för bättre recall och tool-träff."
    )

    if llm is None:
        if fallback_proposed == normalized_current.__dict__:
            return None
        return {
            "current_tuning": normalized_current.__dict__,
            "proposed_tuning": fallback_proposed,
            "rationale": fallback_rationale,
        }

    payload = {
        "current_tuning": normalized_current.__dict__,
        "summary": {
            "total_cases": total,
            "failed_cases": len(failed),
            "retrieval_recall_at_k": retrieval_recall,
            "tool_accuracy": tool_accuracy,
        },
        "failed_cases": failed[:15],
    }
    prompt = (
        "Du optimerar retrieval-tuningvikter för tool-routingutvärdering.\n"
        "Givet nuvarande vikter och misslyckade fall ska du föreslå uppdaterade vikter.\n"
        "Skriv motiveringen på svenska.\n"
        "Returnera strikt JSON:\n"
        "{\n"
        '  "name_match_weight": number,\n'
        '  "keyword_weight": number,\n'
        '  "description_token_weight": number,\n'
        '  "example_query_weight": number,\n'
        '  "namespace_boost": number,\n'
        '  "embedding_weight": number,\n'
        '  "semantic_embedding_weight": number,\n'
        '  "structural_embedding_weight": number,\n'
        '  "live_routing_enabled": true,\n'
        '  "live_routing_phase": "shadow|tool_gate|agent_auto|adaptive|intent_finetune",\n'
        '  "intent_candidate_top_k": integer,\n'
        '  "agent_candidate_top_k": integer,\n'
        '  "tool_candidate_top_k": integer,\n'
        '  "intent_lexical_weight": number,\n'
        '  "intent_embedding_weight": number,\n'
        '  "agent_auto_margin_threshold": number,\n'
        '  "agent_auto_score_threshold": number,\n'
        '  "tool_auto_margin_threshold": number,\n'
        '  "tool_auto_score_threshold": number,\n'
        '  "adaptive_threshold_delta": number,\n'
        '  "adaptive_min_samples": integer,\n'
        '  "rerank_candidates": integer,\n'
        '  "rationale": "kort motivering på svenska"\n'
        "}\n"
        "Ingen markdown."
    )
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
            ]
        )
        parsed = _extract_json_object(str(getattr(response, "content", "") or ""))
        if not parsed:
            raise ValueError("No JSON tuning proposal returned")
        merged_payload = dict(normalized_current.__dict__)
        merged_payload.update(parsed)
        proposed = normalize_retrieval_tuning(merged_payload).__dict__
        if proposed == normalized_current.__dict__:
            return None
        rationale = _prefer_swedish_text(
            str(parsed.get("rationale") or "").strip(),
            "LLM-förslag för retrieval-tuning baserat på misslyckade eval-fall.",
        )
        return {
            "current_tuning": normalized_current.__dict__,
            "proposed_tuning": proposed,
            "rationale": rationale,
        }
    except Exception:
        if fallback_proposed == normalized_current.__dict__:
            return None
        return {
            "current_tuning": normalized_current.__dict__,
            "proposed_tuning": fallback_proposed,
            "rationale": fallback_rationale,
        }


def _tool_json_schema(tool: BaseTool | Any) -> dict[str, Any]:
    if tool is None:
        return {}
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None and hasattr(args_schema, "model_json_schema"):
        try:
            schema = args_schema.model_json_schema()
            if isinstance(schema, dict):
                return schema
        except Exception:
            pass
    get_input_schema = getattr(tool, "get_input_schema", None)
    if callable(get_input_schema):
        try:
            model = get_input_schema()
            if model is not None and hasattr(model, "model_json_schema"):
                schema = model.model_json_schema()
                if isinstance(schema, dict):
                    return schema
        except Exception:
            pass
    tool_args = getattr(tool, "args", None)
    if isinstance(tool_args, dict):
        return {
            "type": "object",
            "properties": tool_args,
            "required": [],
        }
    return {}


def _tool_required_fields(tool: BaseTool | Any) -> list[str]:
    schema = _tool_json_schema(tool)
    return _safe_string_list(schema.get("required"))


def _tool_property_fields(tool: BaseTool | Any) -> list[str]:
    schema = _tool_json_schema(tool)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    return _safe_string_list(list(properties.keys()))


def _coerce_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = _extract_json_object(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _normalize_field_list(values: Any) -> list[str]:
    items = _safe_string_list(values)
    seen: set[str] = set()
    normalized: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _value_matches_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_value_matches_expected(actual, item) for item in expected)
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(actual) == float(expected)
    expected_text = str(expected).strip().casefold()
    actual_text = str(actual).strip().casefold()
    if not expected_text:
        return not actual_text
    if actual_text == expected_text:
        return True
    return expected_text in actual_text or actual_text in expected_text


def _prompt_key_for_tool(tool_id: str | None, category: str | None = None) -> str:
    tool_id = str(tool_id or "").strip().lower()
    category = str(category or "").strip().lower()
    if tool_id:
        return f"tool.{tool_id}.system"
    if tool_id.startswith("scb_") or category in {"statistics", "scb_statistics"}:
        return "agent.statistics.system"
    if tool_id.startswith("riksdag_") or category.startswith("riksdag"):
        return "agent.riksdagen.system"
    if tool_id.startswith("trafikverket_"):
        return "agent.trafik.system"
    if tool_id.startswith("bolagsverket_"):
        return "agent.bolag.system"
    if tool_id.startswith("geoapify_"):
        return "agent.kartor.system"
    if tool_id.startswith("marketplace_"):
        return "agent.marketplace.system"
    if tool_id == "trafiklab_route" or tool_id.startswith("smhi_"):
        return "agent.action.travel"
    if tool_id in {"search_web", "search_tavily", "scrape_webpage", "link_preview"}:
        return "agent.action.web"
    if tool_id in {"libris_search", "jobad_links_search"}:
        return "agent.action.data"
    if tool_id in {"generate_podcast", "display_image"}:
        return "agent.action.media"
    return "agent.action.system"


def _prompt_key_for_agent(agent_name: str | None) -> str | None:
    normalized = _normalize_agent_name(agent_name)
    if not normalized:
        return None
    return "supervisor.agent_resolver.system"


def _prompt_key_for_sub_route(route_value: str | None) -> str | None:
    normalized = _normalize_route_value(route_value)
    if not normalized:
        return None
    return "supervisor.intent_resolver.system"


def _prompt_key_for_intent(intent_id: str | None) -> str | None:
    normalized = _normalize_intent_id(intent_id)
    if not normalized:
        return None
    return "supervisor.intent_resolver.system"


async def _plan_tool_api_input(
    *,
    question: str,
    candidates: list[ToolIndexEntry],
    tool_registry: dict[str, Any],
    llm,
) -> dict[str, Any]:
    candidate_ids = [entry.tool_id for entry in candidates]
    if not candidates:
        return {
            "selected_tool_id": None,
            "selected_category": None,
            "analysis": "No candidates were retrieved for this query.",
            "plan_steps": [],
            "proposed_arguments": {},
            "needs_clarification": True,
            "clarification_question": "Kan du specificera vad du vill att verktyget ska hamta?",
        }

    fallback_entry = candidates[0]
    fallback_payload = {
        "selected_tool_id": fallback_entry.tool_id,
        "selected_category": fallback_entry.category,
        "analysis": (
            "Fallback-planerare: valde högst rankad retrieval-kandidat och lämnade dry-run-argument tomma."
        ),
        "plan_steps": [
            "Inspektera kandidater från tool_retrieval.",
            f"Välj {fallback_entry.tool_id} som bästa metadata-match.",
            "Skissa tool-argument i dry-run utan att exekvera verktyget.",
        ],
        "proposed_arguments": {},
        "needs_clarification": False,
        "clarification_question": None,
    }
    if llm is None:
        return fallback_payload

    candidate_payload: list[dict[str, Any]] = []
    for entry in candidates[:8]:
        tool = tool_registry.get(entry.tool_id)
        required_fields = _tool_required_fields(tool)
        argument_fields = _tool_property_fields(tool)
        candidate_payload.append(
            {
                **_serialize_tool(entry),
                "required_fields": required_fields,
                "argument_fields": argument_fields,
            }
        )

    planner_prompt = (
        "Du utvärderar API-inputkvalitet i dry-run-läge.\n"
        "Välj bästa verktyget bland kandidater och skapa argument för tool-anropet.\n"
        "Exekvera inte verktyg. Uppfinn inte tool_id.\n"
        "Om obligatorisk information saknas, sätt needs_clarification=true.\n"
        "All text ska vara på svenska.\n"
        "Returnera strikt JSON:\n"
        "{\n"
        '  "selected_tool_id": "tool_id or null",\n'
        '  "selected_category": "category or null",\n'
        '  "analysis": "kort förklaring på svenska",\n'
        '  "plan_steps": ["step 1", "step 2"],\n'
        '  "proposed_arguments": {"field": "value"},\n'
        '  "needs_clarification": false,\n'
        '  "clarification_question": "question or null"\n'
        "}\n"
        "Ingen markdown."
    )
    question_payload = {
        "question": question,
        "candidates": candidate_payload,
    }
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=planner_prompt),
                HumanMessage(content=json.dumps(question_payload, ensure_ascii=True)),
            ]
        )
        text = _response_content_to_text(getattr(response, "content", ""))
        parsed = _extract_json_object(text) or {}
        selected_tool_id = parsed.get("selected_tool_id")
        if selected_tool_id is not None:
            selected_tool_id = str(selected_tool_id).strip() or None
        if selected_tool_id not in candidate_ids:
            selected_tool_id = fallback_entry.tool_id
        selected_entry = next(
            (entry for entry in candidates if entry.tool_id == selected_tool_id),
            fallback_entry,
        )
        analysis = str(parsed.get("analysis") or "").strip() or fallback_payload["analysis"]
        plan_steps = _safe_string_list(parsed.get("plan_steps")) or fallback_payload["plan_steps"]
        proposed_arguments = _coerce_arguments(parsed.get("proposed_arguments"))
        needs_clarification = bool(parsed.get("needs_clarification"))
        clarification_question = str(parsed.get("clarification_question") or "").strip() or None
        if needs_clarification and not clarification_question:
            clarification_question = (
                "Kan du komplettera de fält som saknas för att göra API-anropet korrekt?"
            )
        return {
            "selected_tool_id": selected_tool_id,
            "selected_category": selected_entry.category,
            "analysis": analysis,
            "plan_steps": plan_steps,
            "proposed_arguments": proposed_arguments,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
        }
    except Exception:
        return fallback_payload


async def run_tool_api_input_evaluation(
    *,
    tests: list[dict[str, Any]],
    tool_index: list[ToolIndexEntry],
    tool_registry: dict[str, Any],
    llm,
    retrieval_limit: int = 5,
    use_llm_supervisor_review: bool = True,
    retrieval_tuning: dict[str, Any] | None = None,
    prompt_overrides: dict[str, str] | None = None,
    intent_definitions: list[dict[str, Any]] | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    retrieval_limit = max(1, min(int(retrieval_limit or 5), 15))
    normalized_tuning = normalize_retrieval_tuning(retrieval_tuning)
    index_by_id = {entry.tool_id: entry for entry in tool_index}
    results: list[dict[str, Any]] = []

    intent_checks: list[bool] = []
    route_checks: list[bool] = []
    sub_route_checks: list[bool] = []
    graph_complexity_checks: list[bool] = []
    execution_strategy_checks: list[bool] = []
    agent_checks: list[bool] = []
    gated_scores: list[float] = []
    plan_checks: list[bool] = []
    supervisor_review_scores: list[float] = []
    supervisor_review_pass_checks: list[bool] = []
    category_checks: list[bool] = []
    tool_checks: list[bool] = []
    schema_checks: list[bool] = []
    required_field_recalls: list[float] = []
    field_value_checks: list[bool] = []
    clarification_checks: list[bool] = []
    difficulty_buckets: dict[str, dict[str, Any]] = {}

    for idx, test in enumerate(tests):
        test_id = str(test.get("id") or f"case-{idx + 1}")
        question = str(test.get("question") or "").strip()
        difficulty = _normalize_difficulty_value(test.get("difficulty"))
        consistency_warnings = _safe_string_list(test.get("consistency_warnings"))
        expected_normalized = bool(test.get("expected_normalized"))
        if progress_callback is not None:
            event = {
                "type": "test_started",
                "test_id": test_id,
                "index": idx,
                "question": question,
                "consistency_warnings": consistency_warnings,
                "expected_normalized": expected_normalized,
            }
            maybe_result = progress_callback(event)
            if hasattr(maybe_result, "__await__"):
                await maybe_result
        expected = test.get("expected") or {}
        if not isinstance(expected, dict):
            expected = {}
        expected_route = _normalize_route_value(expected.get("route"))
        expected_sub_route = _normalize_sub_route_value(expected.get("sub_route"))
        plan_requirements = _safe_string_list(expected.get("plan_requirements"))
        expected_tool = expected.get("tool")
        expected_tool = str(expected_tool).strip() if expected_tool else None
        expected_category = expected.get("category")
        expected_category = str(expected_category).strip() if expected_category else None
        expected_route, expected_sub_route = _repair_expected_routing(
            expected_route=expected_route,
            expected_sub_route=expected_sub_route,
            expected_tool=expected_tool,
            expected_category=expected_category,
        )
        expected_intent = _infer_expected_intent_id(
            expected=expected,
            expected_route=expected_route,
            intent_definitions=intent_definitions,
        )
        expected_agent = _normalize_agent_name(expected.get("agent"))
        if expected_agent is None:
            expected_agent = _agent_for_tool(
                expected_tool,
                expected_category,
                expected_route,
                expected_sub_route,
            )
        expected_acceptable_agents = _normalize_expected_agent_candidates(
            expected_agent=expected_agent,
            expected_payload=expected,
        )
        expected_acceptable_tools = _dedupe_strings(
            [
                expected_tool or "",
                *_safe_string_list(expected.get("acceptable_tools")),
            ]
        )
        expected_graph_complexity = _normalize_graph_complexity(
            expected.get("graph_complexity")
        )
        expected_execution_strategy = _normalize_execution_strategy(
            expected.get("execution_strategy")
        )
        expected_required_fields = _normalize_field_list(expected.get("required_fields"))
        expected_field_values = (
            expected.get("field_values") if isinstance(expected.get("field_values"), dict) else {}
        )
        allow_clarification_raw = expected.get("allow_clarification")
        allow_clarification = (
            bool(allow_clarification_raw)
            if isinstance(allow_clarification_raw, bool)
            else None
        )
        allowed_tools = _safe_string_list(test.get("allowed_tools"))
        if expected_acceptable_tools:
            allowed_tools = _dedupe_strings([*expected_acceptable_tools, *allowed_tools])
        if expected_tool and not allowed_tools:
            allowed_tools = [expected_tool]

        selected_route: str | None = None
        selected_sub_route: str | None = None
        selected_intent: str | None = None
        selected_agent: str | None = None
        selected_graph_complexity: str | None = None
        selected_execution_strategy: str | None = None
        passed_intent: bool | None = None
        passed_route: bool | None = None
        passed_sub_route: bool | None = None
        passed_graph_complexity: bool | None = None
        passed_execution_strategy: bool | None = None
        passed_agent: bool | None = None
        passed_plan: bool | None = None
        selected_agent_analysis = ""
        plan_requirement_checks: list[dict[str, Any]] = []
        supervisor_trace: dict[str, Any] = {}
        supervisor_review_score: float | None = None
        supervisor_review_passed: bool | None = None
        supervisor_review_rationale: str | None = None
        supervisor_review_issues: list[str] = []
        supervisor_review_rubric: list[dict[str, Any]] = []

        try:
            (
                selected_route,
                selected_sub_route,
                selected_intent,
                route_decision,
            ) = await _dispatch_route_from_start(
                question=question,
                llm=llm,
                prompt_overrides=prompt_overrides,
                intent_definitions=intent_definitions,
            )
            passed_intent = (
                _normalize_intent_id(selected_intent)
                == _normalize_intent_id(expected_intent)
                if expected_intent is not None
                else None
            )
            passed_route = (
                selected_route == expected_route if expected_route is not None else None
            )
            passed_sub_route = (
                selected_sub_route == expected_sub_route
                if expected_sub_route is not None
                else None
            )
            selected_graph_complexity = _infer_graph_complexity_for_eval(
                question=question,
                selected_route=selected_route,
                selected_intent=selected_intent,
                route_decision=route_decision,
            )
            passed_graph_complexity = (
                selected_graph_complexity == expected_graph_complexity
                if expected_graph_complexity is not None
                else None
            )
            selected_agent_plan = await _plan_agent_choice(
                question=question,
                route_value=selected_route,
                sub_route_value=selected_sub_route,
                llm=llm,
            )
            selected_agent = _normalize_agent_name(selected_agent_plan.get("selected_agent"))
            selected_agent_analysis = str(
                selected_agent_plan.get("analysis") or ""
            ).strip()
            passed_agent = (
                selected_agent in expected_acceptable_agents
                if expected_acceptable_agents
                else (selected_agent == expected_agent if expected_agent is not None else None)
            )
            retrieved_ids, retrieval_breakdown = smart_retrieve_tools_with_breakdown(
                question,
                tool_index=tool_index,
                primary_namespaces=[("tools",)],
                fallback_namespaces=[],
                limit=max(retrieval_limit, 8),
                trace_key=None,
                tuning=normalized_tuning,
            )
            retrieved_entries = [
                index_by_id[tool_id]
                for tool_id in retrieved_ids
                if tool_id in index_by_id
            ]
            planning = await _plan_tool_api_input(
                question=question,
                candidates=retrieved_entries[:8],
                tool_registry=tool_registry,
                llm=llm,
            )
            selected_tool = planning.get("selected_tool_id")
            if selected_tool and selected_tool not in index_by_id:
                selected_tool = retrieved_ids[0] if retrieved_ids else None
            if not selected_tool:
                selected_tool = retrieved_ids[0] if retrieved_ids else None
            selected_entry = index_by_id.get(selected_tool) if selected_tool else None
            selected_category = (
                selected_entry.category
                if selected_entry
                else planning.get("selected_category")
            )
            if selected_agent is None:
                selected_agent = _agent_for_tool(
                    selected_tool,
                    selected_category,
                    selected_route,
                    selected_sub_route,
                )
            coerced_agent, coerced = _coerce_weather_agent_choice(
                selected_agent=selected_agent,
                selected_tool=selected_tool,
                selected_category=selected_category,
                route_value=selected_route,
                sub_route_value=selected_sub_route,
            )
            if coerced:
                selected_agent = coerced_agent
                if selected_agent_analysis:
                    selected_agent_analysis = (
                        f"{selected_agent_analysis} Agent justerad till weather baserat på väderverktyg."
                    )
                else:
                    selected_agent_analysis = (
                        "Agent justerad till weather baserat på valt väderverktyg."
                    )
            if expected_acceptable_agents:
                passed_agent = selected_agent in expected_acceptable_agents
            elif expected_agent is not None:
                passed_agent = selected_agent == expected_agent
            selected_execution_strategy = _infer_execution_strategy_for_eval(
                question=question,
                selected_agent=selected_agent,
                selected_tool=selected_tool,
                planning_steps=_safe_string_list(planning.get("plan_steps")),
            )
            passed_execution_strategy = (
                selected_execution_strategy == expected_execution_strategy
                if expected_execution_strategy is not None
                else None
            )
            proposed_arguments = _coerce_arguments(planning.get("proposed_arguments"))
            needs_clarification = bool(planning.get("needs_clarification"))
            clarification_question = (
                str(planning.get("clarification_question") or "").strip() or None
            )
            plan_requirement_checks, passed_plan = _evaluate_plan_requirements(
                requirements=plan_requirements,
                planning_analysis=str(planning.get("analysis") or ""),
                planning_steps=_safe_string_list(planning.get("plan_steps")),
                context={
                    "selected_tool": selected_tool,
                    "selected_route": selected_route,
                    "selected_agent": selected_agent,
                    "proposed_arguments": proposed_arguments,
                    "needs_clarification": needs_clarification,
                },
            )
            supervisor_trace = _build_supervisor_trace(
                question=question,
                expected_intent=expected_intent,
                expected_route=expected_route,
                expected_sub_route=expected_sub_route,
                expected_agent=expected_agent,
                expected_tool=expected_tool,
                expected_graph_complexity=expected_graph_complexity,
                expected_execution_strategy=expected_execution_strategy,
                selected_intent=selected_intent,
                selected_route=selected_route,
                selected_sub_route=selected_sub_route,
                selected_agent=selected_agent,
                selected_tool=selected_tool,
                selected_graph_complexity=selected_graph_complexity,
                selected_execution_strategy=selected_execution_strategy,
                agent_selection_analysis=selected_agent_analysis,
                planning_analysis=str(planning.get("analysis") or ""),
                planning_steps=_safe_string_list(planning.get("plan_steps")),
                plan_requirement_checks=plan_requirement_checks,
            )
            supervisor_review = await _review_supervisor_trace(
                supervisor_trace=supervisor_trace,
                llm=llm if use_llm_supervisor_review else None,
            )
            raw_supervisor_score = supervisor_review.get("score")
            supervisor_review_score = (
                float(raw_supervisor_score)
                if isinstance(raw_supervisor_score, (int, float))
                else None
            )
            if supervisor_review_score is not None:
                supervisor_review_score = max(0.0, min(1.0, supervisor_review_score))
                supervisor_review_scores.append(supervisor_review_score)
            supervisor_review_passed = (
                bool(supervisor_review.get("passed"))
                if isinstance(supervisor_review.get("passed"), bool)
                else None
            )
            if supervisor_review_passed is not None:
                supervisor_review_pass_checks.append(bool(supervisor_review_passed))
            supervisor_review_rationale = str(
                supervisor_review.get("rationale") or ""
            ).strip() or None
            supervisor_review_issues = _safe_string_list(
                supervisor_review.get("issues")
            )
            supervisor_review_rubric = list(supervisor_review.get("rubric") or [])

            target_tool_for_validation = None
            if expected_tool and expected_tool in tool_registry:
                target_tool_for_validation = expected_tool
            elif selected_tool and selected_tool in tool_registry:
                target_tool_for_validation = selected_tool
            target_tool = tool_registry.get(target_tool_for_validation)
            schema_required_fields = _normalize_field_list(_tool_required_fields(target_tool))
            schema_properties = set(_tool_property_fields(target_tool))
            required_fields: list[str] = []
            for field in [*expected_required_fields, *schema_required_fields]:
                lowered = field.casefold()
                if lowered not in {item.casefold() for item in required_fields}:
                    required_fields.append(field)
            missing_required_fields = [
                field for field in required_fields if field not in proposed_arguments
            ]
            if required_fields:
                recall = (len(required_fields) - len(missing_required_fields)) / len(required_fields)
                required_field_recalls.append(recall)
            unexpected_fields = (
                [field for field in proposed_arguments if field not in schema_properties]
                if schema_properties
                else []
            )

            schema_valid: bool | None = None
            schema_errors: list[str] = []
            args_schema = getattr(target_tool, "args_schema", None) if target_tool else None
            if args_schema is not None and hasattr(args_schema, "model_validate"):
                try:
                    args_schema.model_validate(proposed_arguments)
                    schema_valid = True
                except Exception as exc:
                    schema_valid = False
                    schema_errors = [str(exc)]
            elif required_fields:
                schema_valid = len(missing_required_fields) == 0
                if schema_valid is False:
                    schema_errors = [
                        "Missing required fields for target tool input validation."
                    ]
            if schema_valid is not None:
                schema_checks.append(bool(schema_valid))

            field_checks: list[dict[str, Any]] = []
            for field_name, expected_value in expected_field_values.items():
                actual_value = proposed_arguments.get(field_name)
                passed_value_check = _value_matches_expected(actual_value, expected_value)
                field_checks.append(
                    {
                        "field": str(field_name),
                        "expected": expected_value,
                        "actual": actual_value,
                        "passed": passed_value_check,
                    }
                )
                field_value_checks.append(bool(passed_value_check))

            selected_category_norm = _normalize_category_name(selected_category)
            expected_category_norm = _normalize_category_name(expected_category)
            passed_category = (
                selected_category_norm == expected_category_norm
                if expected_category is not None
                else None
            )
            passed_tool = (
                selected_tool in set(allowed_tools)
                if expected_tool is not None
                else None
            )
            if passed_category is not None:
                category_checks.append(bool(passed_category))
            if passed_tool is not None:
                tool_checks.append(bool(passed_tool))
            if passed_intent is not None:
                intent_checks.append(bool(passed_intent))
            if passed_route is not None:
                route_checks.append(bool(passed_route))
            if passed_sub_route is not None:
                sub_route_checks.append(bool(passed_sub_route))
            if passed_graph_complexity is not None:
                graph_complexity_checks.append(bool(passed_graph_complexity))
            if passed_execution_strategy is not None:
                execution_strategy_checks.append(bool(passed_execution_strategy))
            if passed_agent is not None:
                agent_checks.append(bool(passed_agent))
            if passed_plan is not None:
                plan_checks.append(bool(passed_plan))

            clarification_ok: bool | None = None
            if allow_clarification is not None:
                clarification_ok = bool(needs_clarification) == bool(allow_clarification)
                clarification_checks.append(bool(clarification_ok))

            has_api_expectation = bool(
                target_tool_for_validation
                or expected_required_fields
                or expected_field_values
                or allow_clarification is not None
            )
            passed_api_input: bool | None
            if not has_api_expectation:
                passed_api_input = None
            elif allow_clarification is True and needs_clarification:
                passed_api_input = True
            else:
                api_checks: list[bool] = []
                if schema_valid is not None:
                    api_checks.append(bool(schema_valid))
                if required_fields:
                    api_checks.append(len(missing_required_fields) == 0)
                if field_checks:
                    api_checks.append(all(check["passed"] for check in field_checks))
                if clarification_ok is not None:
                    api_checks.append(bool(clarification_ok))
                passed_api_input = all(api_checks) if api_checks else True

            checks = [
                check
                for check in (
                    passed_intent,
                    passed_route,
                    passed_sub_route,
                    passed_graph_complexity,
                    passed_execution_strategy,
                    passed_agent,
                    passed_plan,
                    passed_category,
                    passed_tool,
                    passed_api_input,
                )
                if check is not None
            ]
            passed = all(checks) if checks else True
            agent_gate_score, passed_with_agent_gate = _compute_agent_gate_score(
                upstream_checks=[
                    passed_route,
                    passed_sub_route,
                    passed_graph_complexity,
                    passed_execution_strategy,
                    passed_agent,
                    passed_plan,
                ],
                downstream_checks=[passed_category, passed_tool, passed_api_input],
            )
            if agent_gate_score is not None:
                gated_scores.append(float(agent_gate_score))
            case_result = {
                "test_id": test_id,
                "question": question,
                "difficulty": difficulty,
                "expected_intent": expected_intent,
                "expected_route": expected_route,
                "expected_sub_route": expected_sub_route,
                "expected_graph_complexity": expected_graph_complexity,
                "expected_execution_strategy": expected_execution_strategy,
                "expected_agent": expected_agent,
                "expected_acceptable_agents": expected_acceptable_agents,
                "expected_category": expected_category,
                "expected_tool": expected_tool,
                "expected_acceptable_tools": expected_acceptable_tools,
                "allowed_tools": allowed_tools,
                "selected_route": selected_route,
                "selected_sub_route": selected_sub_route,
                "selected_intent": selected_intent,
                "selected_graph_complexity": selected_graph_complexity,
                "selected_execution_strategy": selected_execution_strategy,
                "selected_agent": selected_agent,
                "agent_selection_analysis": selected_agent_analysis,
                "selected_category": selected_category,
                "selected_tool": selected_tool,
                "planning_analysis": planning.get("analysis") or "",
                "planning_steps": _safe_string_list(planning.get("plan_steps")),
                "supervisor_trace": supervisor_trace,
                "supervisor_review_score": supervisor_review_score,
                "supervisor_review_passed": supervisor_review_passed,
                "supervisor_review_rationale": supervisor_review_rationale,
                "supervisor_review_issues": supervisor_review_issues,
                "supervisor_review_rubric": supervisor_review_rubric,
                "plan_requirement_checks": plan_requirement_checks,
                "retrieval_top_tools": retrieved_ids[:retrieval_limit],
                "retrieval_top_categories": [
                    index_by_id[tool_id].category
                    for tool_id in retrieved_ids[:retrieval_limit]
                    if tool_id in index_by_id
                ],
                "retrieval_breakdown": retrieval_breakdown[:retrieval_limit],
                "consistency_warnings": consistency_warnings,
                "expected_normalized": expected_normalized,
                "proposed_arguments": proposed_arguments,
                "target_tool_for_validation": target_tool_for_validation,
                "schema_required_fields": schema_required_fields,
                "expected_required_fields": expected_required_fields,
                "missing_required_fields": missing_required_fields,
                "unexpected_fields": unexpected_fields,
                "field_checks": field_checks,
                "schema_valid": schema_valid,
                "schema_errors": schema_errors,
                "needs_clarification": needs_clarification,
                "clarification_question": clarification_question,
                "passed_intent": passed_intent,
                "passed_route": passed_route,
                "passed_sub_route": passed_sub_route,
                "passed_graph_complexity": passed_graph_complexity,
                "passed_execution_strategy": passed_execution_strategy,
                "passed_agent": passed_agent,
                "passed_plan": passed_plan,
                "passed_category": passed_category,
                "passed_tool": passed_tool,
                "passed_api_input": passed_api_input,
                "passed_with_agent_gate": passed_with_agent_gate,
                "agent_gate_score": agent_gate_score,
                "passed": passed,
            }
            _update_difficulty_bucket(
                difficulty_buckets=difficulty_buckets,
                difficulty=difficulty,
                passed=bool(passed),
                gated_score=agent_gate_score,
            )
            results.append(case_result)
            if progress_callback is not None:
                event = {
                    "type": "test_completed",
                    "test_id": test_id,
                    "index": idx,
                    "selected_intent": selected_intent,
                    "selected_route": selected_route,
                    "selected_sub_route": selected_sub_route,
                    "selected_graph_complexity": selected_graph_complexity,
                    "selected_execution_strategy": selected_execution_strategy,
                    "selected_agent": selected_agent,
                    "agent_selection_analysis": selected_agent_analysis,
                    "selected_tool": selected_tool,
                    "selected_category": selected_category,
                    "consistency_warnings": consistency_warnings,
                    "expected_normalized": expected_normalized,
                    "passed": passed,
                }
                maybe_result = progress_callback(event)
                if hasattr(maybe_result, "__await__"):
                    await maybe_result
        except Exception as exc:
            failed_supervisor_trace = _build_supervisor_trace(
                question=question,
                expected_intent=expected_intent,
                expected_route=expected_route,
                expected_sub_route=expected_sub_route,
                expected_agent=expected_agent,
                expected_tool=expected_tool,
                expected_graph_complexity=expected_graph_complexity,
                expected_execution_strategy=expected_execution_strategy,
                selected_intent=selected_intent,
                selected_route=selected_route,
                selected_sub_route=selected_sub_route,
                selected_agent=selected_agent,
                selected_tool=None,
                selected_graph_complexity=selected_graph_complexity,
                selected_execution_strategy=selected_execution_strategy,
                agent_selection_analysis=selected_agent_analysis,
                planning_analysis=f"API input evaluation failed for this case: {exc}",
                planning_steps=[],
                plan_requirement_checks=[],
            )
            failed_supervisor_review = _fallback_supervisor_trace_review(
                supervisor_trace=failed_supervisor_trace
            )
            case_result = {
                "test_id": test_id,
                "question": question,
                "difficulty": difficulty,
                "expected_intent": expected_intent,
                "expected_route": expected_route,
                "expected_sub_route": expected_sub_route,
                "expected_graph_complexity": expected_graph_complexity,
                "expected_execution_strategy": expected_execution_strategy,
                "expected_agent": expected_agent,
                "expected_acceptable_agents": expected_acceptable_agents,
                "expected_category": expected_category,
                "expected_tool": expected_tool,
                "expected_acceptable_tools": expected_acceptable_tools,
                "allowed_tools": allowed_tools,
                "selected_route": selected_route,
                "selected_sub_route": selected_sub_route,
                "selected_intent": selected_intent,
                "selected_graph_complexity": selected_graph_complexity,
                "selected_execution_strategy": selected_execution_strategy,
                "selected_agent": selected_agent,
                "agent_selection_analysis": selected_agent_analysis,
                "selected_category": None,
                "selected_tool": None,
                "planning_analysis": f"API input evaluation failed for this case: {exc}",
                "planning_steps": [],
                "supervisor_trace": failed_supervisor_trace,
                "supervisor_review_score": 0.0,
                "supervisor_review_passed": False,
                "supervisor_review_rationale": "Supervisor-spåret kunde inte granskas eftersom eval-fallet avbröts av fel.",
                "supervisor_review_issues": [str(exc)],
                "supervisor_review_rubric": list(
                    failed_supervisor_review.get("rubric") or []
                ),
                "plan_requirement_checks": [],
                "retrieval_top_tools": [],
                "retrieval_top_categories": [],
                "retrieval_breakdown": [],
                "consistency_warnings": consistency_warnings,
                "expected_normalized": expected_normalized,
                "proposed_arguments": {},
                "target_tool_for_validation": expected_tool,
                "schema_required_fields": [],
                "expected_required_fields": expected_required_fields,
                "missing_required_fields": expected_required_fields,
                "unexpected_fields": [],
                "field_checks": [],
                "schema_valid": False,
                "schema_errors": [str(exc)],
                "needs_clarification": False,
                "clarification_question": None,
                "passed_intent": False if expected_intent is not None else None,
                "passed_route": False if expected_route is not None else None,
                "passed_sub_route": False if expected_sub_route is not None else None,
                "passed_graph_complexity": (
                    False if expected_graph_complexity is not None else None
                ),
                "passed_execution_strategy": (
                    False if expected_execution_strategy is not None else None
                ),
                "passed_agent": False if expected_agent is not None else None,
                "passed_plan": False if plan_requirements else None,
                "passed_category": False if expected_category is not None else None,
                "passed_tool": False if expected_tool is not None else None,
                "passed_api_input": False,
                "passed_with_agent_gate": False,
                "agent_gate_score": 0.0,
                "passed": False,
            }
            results.append(case_result)
            _update_difficulty_bucket(
                difficulty_buckets=difficulty_buckets,
                difficulty=difficulty,
                passed=False,
                gated_score=0.0,
            )
            gated_scores.append(0.0)
            supervisor_review_scores.append(0.0)
            supervisor_review_pass_checks.append(False)
            if expected_intent is not None:
                intent_checks.append(False)
            if expected_route is not None:
                route_checks.append(False)
            if expected_sub_route is not None:
                sub_route_checks.append(False)
            if expected_graph_complexity is not None:
                graph_complexity_checks.append(False)
            if expected_execution_strategy is not None:
                execution_strategy_checks.append(False)
            if expected_agent is not None:
                agent_checks.append(False)
            if plan_requirements:
                plan_checks.append(False)
            if expected_category is not None:
                category_checks.append(False)
            if expected_tool is not None:
                tool_checks.append(False)
            schema_checks.append(False)
            if expected_required_fields:
                required_field_recalls.append(0.0)
            if expected_field_values:
                for _key in expected_field_values.keys():
                    field_value_checks.append(False)
            if allow_clarification is not None:
                clarification_checks.append(False)
            if progress_callback is not None:
                event = {
                    "type": "test_failed",
                    "test_id": test_id,
                    "index": idx,
                    "consistency_warnings": consistency_warnings,
                    "expected_normalized": expected_normalized,
                    "error": str(exc),
                }
                maybe_result = progress_callback(event)
                if hasattr(maybe_result, "__await__"):
                    await maybe_result

    total_tests = len(results)
    passed_count = sum(1 for item in results if item.get("passed"))
    metrics = {
        "total_tests": total_tests,
        "passed_tests": passed_count,
        "success_rate": (passed_count / total_tests) if total_tests else 0.0,
        "gated_success_rate": (
            sum(gated_scores) / len(gated_scores)
            if gated_scores
            else None
        ),
        "intent_accuracy": (
            sum(1 for check in intent_checks if check) / len(intent_checks)
            if intent_checks
            else None
        ),
        "route_accuracy": (
            sum(1 for check in route_checks if check) / len(route_checks)
            if route_checks
            else None
        ),
        "sub_route_accuracy": (
            sum(1 for check in sub_route_checks if check) / len(sub_route_checks)
            if sub_route_checks
            else None
        ),
        "graph_complexity_accuracy": (
            sum(1 for check in graph_complexity_checks if check)
            / len(graph_complexity_checks)
            if graph_complexity_checks
            else None
        ),
        "execution_strategy_accuracy": (
            sum(1 for check in execution_strategy_checks if check)
            / len(execution_strategy_checks)
            if execution_strategy_checks
            else None
        ),
        "agent_accuracy": (
            sum(1 for check in agent_checks if check) / len(agent_checks)
            if agent_checks
            else None
        ),
        "plan_accuracy": (
            sum(1 for check in plan_checks if check) / len(plan_checks)
            if plan_checks
            else None
        ),
        "supervisor_review_score": (
            sum(supervisor_review_scores) / len(supervisor_review_scores)
            if supervisor_review_scores
            else None
        ),
        "supervisor_review_pass_rate": (
            sum(1 for check in supervisor_review_pass_checks if check)
            / len(supervisor_review_pass_checks)
            if supervisor_review_pass_checks
            else None
        ),
        "category_accuracy": (
            sum(1 for check in category_checks if check) / len(category_checks)
            if category_checks
            else None
        ),
        "tool_accuracy": (
            sum(1 for check in tool_checks if check) / len(tool_checks)
            if tool_checks
            else None
        ),
        "schema_validity_rate": (
            sum(1 for check in schema_checks if check) / len(schema_checks)
            if schema_checks
            else None
        ),
        "required_field_recall": (
            sum(required_field_recalls) / len(required_field_recalls)
            if required_field_recalls
            else None
        ),
        "field_value_accuracy": (
            sum(1 for check in field_value_checks if check) / len(field_value_checks)
            if field_value_checks
            else None
        ),
        "clarification_accuracy": (
            sum(1 for check in clarification_checks if check) / len(clarification_checks)
            if clarification_checks
            else None
        ),
        "difficulty_breakdown": _build_difficulty_breakdown(difficulty_buckets),
    }
    return {"metrics": metrics, "results": results}


def _build_fallback_prompt_suggestion(
    *,
    prompt_key: str,
    current_prompt: str,
    failures: list[dict[str, Any]],
    api_tool_only: bool = False,
) -> tuple[str, str]:
    missing_counter: Counter[str] = Counter()
    for failure in failures:
        for field_name in failure.get("missing_required_fields") or []:
            cleaned = str(field_name).strip()
            if cleaned:
                missing_counter[cleaned] += 1
    common_missing = [item for item, _count in missing_counter.most_common(8)]
    if api_tool_only:
        lines = [
            "- Fokusera strikt på API-input för detta verktyg: required_fields, format och datatyper.",
            "- Extrahera endast fält som finns i verktygets schema och använd exakta fältnamn.",
            "- Om obligatoriska fält saknas: ställ en kort förtydligande fråga innan anrop föreslås.",
            "- Undvik antaganden om datum/plats/id om de inte finns explicit i frågan.",
            "- Validera föreslagen payload mot schema innan verktygsanrop returneras.",
        ]
    elif prompt_key == "supervisor.intent_resolver.system":
        lines = [
            "- Välj intent_id utifrån semantisk intention, inte enbart enstaka nyckelord.",
            "- Vid kort uppföljning ska intent ärvas från föregående fråga om kontexten är oförändrad.",
            "- Returnera endast intent som finns i retrieve_intents-kandidaterna.",
            "- Vid osäkerhet: välj närmaste intent med tydlig motivering och hög precision.",
            "- Om intent inte matchar tillgängliga kandidater: be om förtydligande istället för gissning.",
        ]
    elif prompt_key == "supervisor.agent_resolver.system":
        lines = [
            "- Välj agenter strikt från retrieve_agents-kandidaterna för aktuell intent.",
            "- Prioritera 1 primär agent och undvik onödig multi-agent-planering.",
            "- Om vald agent saknar rätt verktygsdomän: kör retrieve_agents igen innan exekvering.",
            "- Följ domängränser strikt (ingen agent-drift till irrelevanta domäner).",
        ]
    elif prompt_key == "supervisor.planner.system":
        lines = [
            "- Skapa kort plan (max 4 steg) med tydlig koppling till intent och vald agent.",
            "- Undvik abstrakta steg; varje steg ska vara exekverbart och verifierbart.",
            "- Planen ska innehålla när retrieve_tools ska köras om kandidatverktyg inte matchar uppgiften.",
            "- Vid uppföljningsfrågor: återanvänd föregående metod och byt bara relevanta parametrar.",
        ]
    elif prompt_key == "supervisor.critic_gate.system":
        lines = [
            "- Returnera endast ok/needs_more/replan enligt kontraktet.",
            "- Välj ok när svaret uppfyller frågan och nödvändiga fält finns.",
            "- Välj needs_more endast när nästa steg realistiskt kan ge saknad information.",
            "- Välj replan vid tydlig domän- eller verktygsmismatch.",
        ]
    elif prompt_key == "supervisor.synthesizer.system":
        lines = [
            "- Sammanfatta enbart verifierade resultat från utförda steg.",
            "- Lägg inte till interna JSON-objekt eller kedje-resonemang i användarsvaret.",
            "- Behåll svaret kort, direkt och konsistent med användarens fråga.",
        ]
    elif prompt_key.startswith("router."):
        lines = [
            "- Returnera exakt en giltig route-etikett och undvik extra text.",
            "- Prioritera semantisk intention över nyckelordsöverlapp i gränsfall.",
            "- Om frågan tydligt gäller officiell statistik, prioritera statistics-route.",
            "- Om frågan gäller verktygsåtgärd, prioritera action-route över knowledge.",
        ]
        if prompt_key == "router.action":
            lines = [
                "- Returnera exakt en av: web, media, travel, data.",
                "- Använd travel för väder, avgångar, rutter och pendlingsfrågor.",
                "- Använd web för URL/länk/skrapning och sidinnehåll.",
                "- Använd data för jobb/Libris/dataset-frågor.",
            ]
        elif prompt_key == "router.knowledge":
            lines = [
                "- Returnera exakt en av: docs, internal, external.",
                "- Använd docs för SurfSense produkt-/how-to-frågor.",
                "- Använd internal för användardata/anteckningar/kalender/search space-innehåll.",
                "- Använd external endast för explicita realtids-/webbfrågor.",
            ]
    elif prompt_key == "agent.supervisor.system":
        lines = [
            "- Håll denna prompt minimal: koordinera endast route, agentanrop och slutsammanfattning.",
            "- Delegera domänresonemang och argumentdetaljer till specialiserade agent-/tool-prompts.",
            "- Lägg inte in långa verktygslistor eller endpointdetaljer i supervisorprompten.",
            "- Lista inte alla agenter statiskt; använd retrieve_agents för dynamiskt urval.",
            "- Använd retrieval-resultat för dynamiskt val av kandidater innan körning.",
            "- Om aktuell agent inte kan lösa uppgiften eller frågan byter riktning: kör retrieve_agents igen innan nästa delegering.",
        ]
    elif prompt_key == "supervisor.tool_resolver.system":
        lines = [
            "- Prioritera retrieval-förankrad tool-matchning per plansteg.",
            "- Begränsa antalet föreslagna verktyg per agent till de mest relevanta.",
            "- Undvik statiska endpoint-listor; använd retrieve_tools dynamiskt.",
            "- Om verktygskandidater inte matchar uppgiften: kör retrieve_tools igen med förfinad intent.",
            "- Håll output deterministisk och fokuserad på nästa exekverbara steg.",
        ]
    elif prompt_key.startswith("tool."):
        lines = [
            "- Fokusera endast på detta endpoint-verktyg och ignorera irrelevanta verktyg.",
            "- Mappa användarintention till detta verktygs schema med exakta fältnamn.",
            "- Om obligatoriska fält saknas: ställ en kort förtydligande fråga.",
            "- Lägg inte till argument som inte finns i verktygets schema.",
            "- Om uppgiften inte matchar verktygets domän: gör ny retrieve_tools innan nytt verktygsval.",
        ]
    elif prompt_key.startswith("agent."):
        lines = [
            "- Välj verktyg som matchar agentens domän innan argument genereras.",
            "- Avvisa verktyg utanför domänen om inte användarintentionen tydligt byter domän.",
            "- Håll planeringen kort: domänträff -> verktygsträff -> kompletta argument.",
            "- Undvik statisk endpoint-listning; använd retrieve_tools för dynamiskt urval.",
            "- Om domänkritiska fält saknas: ställ en fokuserad förtydligande fråga.",
            "- Om tillgängliga verktyg inte kan lösa uppgiften eller frågan byter ämne: kör retrieve_tools igen med omformulerad intent.",
        ]
    else:
        lines = [
            "- Validera argumentens fullständighet innan verktygsanrop föreslås.",
            "- Om obligatoriska argument saknas eller är tvetydiga: ställ en kort fråga först.",
            "- Använd exakta argumentnamn från målschemat och undvik okända fält.",
        ]
    if common_missing:
        lines.insert(
            0,
            f"- Prioritera att extrahera dessa ofta missade fält: {', '.join(common_missing)}.",
        )
    appendix = (
        "\n\n[API INPUT EVAL-FÖRBÄTTRING]\n"
        f"Prompt-nyckel: {prompt_key}\n"
        + "\n".join(lines)
    )
    proposed_prompt = current_prompt
    if appendix.strip() not in current_prompt:
        proposed_prompt = f"{current_prompt.rstrip()}{appendix}"
    rationale = (
        f"Fallback-förslag från {len(failures)} misslyckade eval-fall: "
        + (
            "skärper API-input-extraktion och validering."
            if api_tool_only
            else "skärper routing- och argumentval."
        )
    )
    return proposed_prompt, rationale


async def _build_llm_prompt_suggestion(
    *,
    prompt_key: str,
    current_prompt: str,
    failures: list[dict[str, Any]],
    llm,
    api_tool_only: bool = False,
) -> tuple[str, str] | None:
    if llm is None:
        return None
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    if api_tool_only:
        prompt = (
            "Du är en specialiserad evaluator för API-input.\n"
            "Du får endast förbättra verktygsspecifik prompt för bättre argumentextraktion.\n"
            "Fokusera på required_fields, fältformat, validering och korta förtydligande frågor.\n"
            "Föreslå INTE ändringar för router, supervisor eller generella agentprompter.\n"
            "All text ska vara på svenska.\n"
            "Returnera strikt JSON:\n"
            "{\n"
            '  "proposed_prompt": "fullständig reviderad prompt på svenska",\n'
            '  "rationale": "kort motivering på svenska"\n'
            "}\n"
            "Ingen markdown."
        )
    else:
        prompt = (
            "Du optimerar en routing-/agentprompt för bättre kvalitet i dry-run-evaluering.\n"
            "Behåll stil och syfte, men lägg till precisa instruktioner för route, planering och argumentextraktion.\n"
            "All text ska vara på svenska.\n"
            "Undvik statiska listor över alla agenter eller endpoints. Förlita dig på retrieve_agents/retrieve_tools.\n"
            "När valda agenter/verktyg inte räcker eller frågan byter riktning ska prompten instruera ny retrieval (retrieve_agents/retrieve_tools).\n"
            "Förslag får inte bryta arkitekturen: ingen statisk agentlista i supervisor, inga tunga endpoint-listor, och tydlig regel för ny retrieval vid mismatch/ämnesbyte.\n"
            "Om supervisor_trace finns i failed_cases ska du använda den för att förbättra kvaliteten i route -> agent -> tool -> plan.\n"
            "Returnera strikt JSON:\n"
            "{\n"
            '  "proposed_prompt": "fullständig reviderad prompt på svenska",\n'
            '  "rationale": "kort motivering på svenska"\n'
            "}\n"
            "Ingen markdown."
        )
    payload = {
        "prompt_key": prompt_key,
        "current_prompt": current_prompt,
        "failed_cases": failures[:20],
    }
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
            ]
        )
        text = _response_content_to_text(getattr(response, "content", ""))
        parsed = _extract_json_object(text)
        if not parsed:
            return None
        proposed_prompt = str(parsed.get("proposed_prompt") or "").strip()
        if not proposed_prompt:
            return None
        if _looks_english_text(proposed_prompt):
            return None
        proposed_prompt, architecture_violations, architecture_severe = (
            _apply_prompt_architecture_guard(
                prompt_key=prompt_key,
                prompt_text=proposed_prompt,
            )
        )
        if architecture_severe:
            return None
        rationale = str(parsed.get("rationale") or "").strip()
        if not rationale:
            rationale = "LLM-förslag för promptförbättring från API-input-fel."
        rationale = _prefer_swedish_text(
            rationale,
            "LLM-förslag för promptförbättring från API-input-fel.",
        )
        if architecture_violations:
            rationale = (
                f"{rationale} Arkitektur-guard tillämpad: "
                + "; ".join(architecture_violations[:3])
                + "."
            )
        return proposed_prompt, rationale
    except Exception:
        return None


async def suggest_agent_prompt_improvements_for_api_input(
    *,
    evaluation_results: list[dict[str, Any]],
    current_prompts: dict[str, str],
    llm=None,
    max_suggestions: int = 8,
    suggestion_scope: str = "full",
) -> list[dict[str, Any]]:
    normalized_scope = str(suggestion_scope or "full").strip().lower()
    api_tool_only = normalized_scope in {"api_tool_only", "api-tool-only", "tool_only"}

    def _append_failure(
        bucket_key: str,
        *,
        result: dict[str, Any],
        expected_tool: str | None,
        selected_tool: str | None,
    ) -> None:
        if bucket_key not in current_prompts:
            return
        bucket = buckets.setdefault(
            bucket_key,
            {
                "failed_test_ids": [],
                "related_tools": set(),
                "failures": [],
            },
        )
        test_id = str(result.get("test_id") or "").strip()
        if test_id:
            bucket["failed_test_ids"].append(test_id)
        for related_tool in (expected_tool, selected_tool):
            if related_tool:
                bucket["related_tools"].add(related_tool)
        bucket["failures"].append(
            {
                "test_id": test_id,
                "question": str(result.get("question") or "").strip(),
                "expected_route": result.get("expected_route"),
                "selected_route": result.get("selected_route"),
                "expected_intent": result.get("expected_intent"),
                "selected_intent": result.get("selected_intent"),
                "expected_sub_route": result.get("expected_sub_route"),
                "selected_sub_route": result.get("selected_sub_route"),
                "expected_agent": result.get("expected_agent"),
                "selected_agent": result.get("selected_agent"),
                "expected_tool": expected_tool,
                "selected_tool": selected_tool,
                "agent_selection_analysis": str(
                    result.get("agent_selection_analysis") or ""
                ).strip(),
                "planning_analysis": str(result.get("planning_analysis") or "").strip(),
                "planning_steps": list(result.get("planning_steps") or []),
                "supervisor_trace": (
                    result.get("supervisor_trace")
                    if isinstance(result.get("supervisor_trace"), dict)
                    else {}
                ),
                "supervisor_review_score": result.get("supervisor_review_score"),
                "supervisor_review_passed": result.get("supervisor_review_passed"),
                "supervisor_review_rationale": str(
                    result.get("supervisor_review_rationale") or ""
                ).strip(),
                "supervisor_review_issues": list(
                    result.get("supervisor_review_issues") or []
                ),
                "supervisor_review_rubric": list(
                    result.get("supervisor_review_rubric") or []
                ),
                "missing_required_fields": list(result.get("missing_required_fields") or []),
                "unexpected_fields": list(result.get("unexpected_fields") or []),
                "schema_errors": list(result.get("schema_errors") or []),
                "plan_requirement_checks": list(result.get("plan_requirement_checks") or []),
                "needs_clarification": bool(result.get("needs_clarification")),
                "clarification_question": result.get("clarification_question"),
            }
        )

    buckets: dict[str, dict[str, Any]] = {}
    for result in evaluation_results:
        passed = bool(result.get("passed"))
        passed_api_input = result.get("passed_api_input")
        passed_intent = result.get("passed_intent")
        passed_route = result.get("passed_route")
        passed_sub_route = result.get("passed_sub_route")
        passed_agent = result.get("passed_agent")
        passed_plan = result.get("passed_plan")
        passed_supervisor_review = result.get("supervisor_review_passed")
        has_api_input = "passed_api_input" in result
        failed_intent = passed_intent is False
        failed_route = passed_route is False
        failed_sub_route = passed_sub_route is False
        failed_agent = passed_agent is False
        failed_plan = passed_plan is False
        failed_supervisor_review = passed_supervisor_review is False
        failed_api_input = passed_api_input is False if has_api_input else False

        schema_valid = result.get("schema_valid")
        schema_failed = schema_valid is False
        missing_required_fields = list(result.get("missing_required_fields") or [])
        unexpected_fields = list(result.get("unexpected_fields") or [])
        schema_errors = list(result.get("schema_errors") or [])
        field_checks = list(result.get("field_checks") or [])
        field_check_failed = any(
            isinstance(check, dict) and check.get("passed") is False for check in field_checks
        )
        api_input_failure_signal = (
            failed_api_input
            or schema_failed
            or bool(missing_required_fields)
            or bool(unexpected_fields)
            or bool(schema_errors)
            or field_check_failed
        )
        if not (
            failed_intent
            or failed_route
            or failed_sub_route
            or failed_agent
            or failed_plan
            or failed_supervisor_review
            or failed_api_input
            or (api_tool_only and api_input_failure_signal)
            or not passed
        ):
            continue
        expected_tool = str(result.get("expected_tool") or "").strip() or None
        selected_tool = str(result.get("selected_tool") or "").strip() or None
        expected_agent = _normalize_agent_name(result.get("expected_agent"))
        selected_agent = _normalize_agent_name(result.get("selected_agent"))
        selected_category = str(result.get("selected_category") or "").strip() or None
        expected_category = str(result.get("expected_category") or "").strip() or None
        expected_route = _normalize_route_value(result.get("expected_route"))
        selected_route = _normalize_route_value(result.get("selected_route"))
        expected_intent = _normalize_intent_id(result.get("expected_intent"))
        selected_intent = _normalize_intent_id(result.get("selected_intent"))

        if api_tool_only:
            if not api_input_failure_signal:
                continue
            tool_id = expected_tool or selected_tool
            category = expected_category or selected_category
            prompt_key = _prompt_key_for_tool(tool_id, category)
            if not prompt_key.startswith("tool.") or prompt_key not in current_prompts:
                continue
            _append_failure(
                prompt_key,
                result=result,
                expected_tool=expected_tool,
                selected_tool=selected_tool,
            )
            continue

        if failed_route:
            _append_failure(
                "supervisor.intent_resolver.system",
                result=result,
                expected_tool=expected_tool,
                selected_tool=selected_tool,
            )
        if failed_intent:
            intent_prompt_key = _prompt_key_for_intent(expected_intent or selected_intent)
            if intent_prompt_key:
                _append_failure(
                    intent_prompt_key,
                    result=result,
                    expected_tool=expected_tool,
                    selected_tool=selected_tool,
                )
        if failed_sub_route:
            sub_route_prompt_key = _prompt_key_for_sub_route(expected_route or selected_route)
            if sub_route_prompt_key:
                _append_failure(
                    sub_route_prompt_key,
                    result=result,
                    expected_tool=expected_tool,
                    selected_tool=selected_tool,
                )

        if failed_agent:
            agent_prompt_key = _prompt_key_for_agent(expected_agent or selected_agent)
            if agent_prompt_key:
                _append_failure(
                    agent_prompt_key,
                    result=result,
                    expected_tool=expected_tool,
                    selected_tool=selected_tool,
                )

        if "supervisor.planner.system" in current_prompts and (
            failed_plan or failed_supervisor_review or not passed
        ):
            _append_failure(
                "supervisor.planner.system",
                result=result,
                expected_tool=expected_tool,
                selected_tool=selected_tool,
            )
        if (
            "supervisor.tool_resolver.system" in current_prompts
            and (failed_plan or failed_api_input or result.get("passed_tool") is False)
        ):
            _append_failure(
                "supervisor.tool_resolver.system",
                result=result,
                expected_tool=expected_tool,
                selected_tool=selected_tool,
            )

        tool_id = expected_tool or selected_tool
        category = expected_category or selected_category
        if (
            failed_plan
            or failed_api_input
            or expected_tool
            or selected_tool
            or expected_category
            or selected_category
        ):
            prompt_key = _prompt_key_for_tool(tool_id, category)
            if prompt_key not in current_prompts:
                fallback_agent_key = _prompt_key_for_agent(
                    _agent_for_tool(
                        tool_id,
                        category,
                        expected_route or selected_route,
                        _normalize_sub_route_value(
                            result.get("expected_sub_route")
                            or result.get("selected_sub_route")
                        ),
                    )
                )
                if fallback_agent_key and fallback_agent_key in current_prompts:
                    prompt_key = fallback_agent_key
            _append_failure(
                prompt_key,
                result=result,
                expected_tool=expected_tool,
                selected_tool=selected_tool,
            )

    suggestions: list[dict[str, Any]] = []
    for prompt_key, bucket in buckets.items():
        if len(suggestions) >= max_suggestions:
            break
        current_prompt = str(current_prompts.get(prompt_key) or "").strip()
        if not current_prompt:
            continue
        fallback_prompt, fallback_rationale = _build_fallback_prompt_suggestion(
            prompt_key=prompt_key,
            current_prompt=current_prompt,
            failures=bucket["failures"],
            api_tool_only=api_tool_only,
        )
        (
            fallback_prompt,
            fallback_architecture_violations,
            fallback_architecture_severe,
        ) = _apply_prompt_architecture_guard(
            prompt_key=prompt_key,
            prompt_text=fallback_prompt,
        )
        if fallback_architecture_severe:
            fallback_prompt = current_prompt
            fallback_rationale = (
                f"{fallback_rationale} Fallback-förslag stoppades av arkitektur-guard och "
                "ersattes med nuvarande prompt."
            )
        elif fallback_architecture_violations:
            fallback_rationale = (
                f"{fallback_rationale} Arkitektur-guard justerade fallback-förslaget: "
                + "; ".join(fallback_architecture_violations[:3])
                + "."
            )
        llm_result = await _build_llm_prompt_suggestion(
            prompt_key=prompt_key,
            current_prompt=current_prompt,
            failures=bucket["failures"],
            llm=llm,
            api_tool_only=api_tool_only,
        )
        if llm_result is None:
            proposed_prompt, rationale = fallback_prompt, fallback_rationale
        else:
            proposed_prompt, rationale = llm_result
            if proposed_prompt.strip() == current_prompt.strip():
                proposed_prompt = fallback_prompt
                rationale = (
                    f"{rationale} Lade till fallback-regler från API-input-fel."
                )
        (
            proposed_prompt,
            architecture_violations,
            architecture_severe,
        ) = _apply_prompt_architecture_guard(
            prompt_key=prompt_key,
            prompt_text=proposed_prompt,
        )
        if architecture_severe:
            proposed_prompt = fallback_prompt
            rationale = (
                f"{rationale} LLM-förslag bröt arkitekturregler och ersattes av fallback."
            )
        elif architecture_violations:
            rationale = (
                f"{rationale} Arkitektur-guard justerade förslaget: "
                + "; ".join(architecture_violations[:3])
                + "."
            )
        suggestions.append(
            {
                "prompt_key": prompt_key,
                "failed_test_ids": list(bucket["failed_test_ids"]),
                "related_tools": sorted(str(tool) for tool in bucket["related_tools"]),
                "rationale": rationale,
                "current_prompt": current_prompt,
                "proposed_prompt": proposed_prompt,
            }
        )
    return suggestions
