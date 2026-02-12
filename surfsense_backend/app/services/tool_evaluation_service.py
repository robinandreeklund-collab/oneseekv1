from __future__ import annotations

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
    normalize_retrieval_tuning,
    smart_retrieve_tools_with_breakdown,
)
from app.agents.new_chat.dispatcher import dispatch_route
from app.agents.new_chat.knowledge_router import KnowledgeRoute, dispatch_knowledge_route
from app.agents.new_chat.routing import Route

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
_EVAL_AGENT_CHOICES = (
    "statistics",
    "riksdagen",
    "trafik",
    "bolag",
    "kartor",
    "media",
    "browser",
    "knowledge",
    "action",
    "synthesis",
)

_EVAL_AGENT_DESCRIPTIONS: dict[str, str] = {
    "statistics": "SCB/statistics and official data in Sweden.",
    "riksdagen": "Swedish parliament and political documents.",
    "trafik": "Traffic, roads, routes, weather-related transport context.",
    "bolag": "Swedish company/organization registry context.",
    "kartor": "Geospatial/maps/geocoding context.",
    "media": "Podcast and media generation context.",
    "browser": "Web browsing, URL scraping, and page lookup tasks.",
    "knowledge": "Knowledge lookup in docs/internal/external sources.",
    "action": "General action/data tasks not covered by a specialist agent.",
    "synthesis": "Cross-source compare/synthesis tasks.",
}


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


def _normalize_route_value(value: Any) -> str | None:
    route = str(value or "").strip().lower()
    if route in {Route.KNOWLEDGE.value, Route.ACTION.value, Route.SMALLTALK.value, Route.STATISTICS.value, Route.COMPARE.value}:
        return route
    if route in {"statistik", "statistics"}:
        return Route.STATISTICS.value
    return None


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


def _normalize_agent_name(value: Any) -> str | None:
    agent = str(value or "").strip().lower()
    if not agent:
        return None
    aliases = {
        "statistik": "statistics",
        "stats": "statistics",
        "scb": "statistics",
        "riksdag": "riksdagen",
        "traffic": "trafik",
        "trafikverket": "trafik",
        "weather": "trafik",
        "maps": "kartor",
        "map": "kartor",
        "geo": "kartor",
        "geography": "kartor",
        "bolagsverket": "bolag",
        "companies": "bolag",
        "company": "bolag",
        "web": "browser",
        "docs": "knowledge",
        "internal": "knowledge",
        "external": "knowledge",
        "compare": "synthesis",
    }
    normalized = aliases.get(agent, agent)
    return normalized if normalized in _EVAL_AGENT_CHOICES else None


def _agent_for_route_hint(route_value: str | None, sub_route_value: str | None) -> str | None:
    route_norm = _normalize_route_value(route_value)
    sub_norm = _normalize_sub_route_value(sub_route_value)
    if route_norm == Route.STATISTICS.value:
        return "statistics"
    if route_norm == Route.COMPARE.value:
        return "synthesis"
    if route_norm == Route.KNOWLEDGE.value:
        return "knowledge"
    if route_norm == Route.ACTION.value:
        if sub_norm == ActionRoute.TRAVEL.value:
            return "trafik"
        if sub_norm == ActionRoute.WEB.value:
            return "browser"
        if sub_norm == ActionRoute.MEDIA.value:
            return "media"
        if sub_norm == ActionRoute.DATA.value:
            return "action"
        return "action"
    return None


def _agent_for_tool(
    tool_id: str | None,
    category: str | None = None,
    route_value: str | None = None,
    sub_route_value: str | None = None,
) -> str | None:
    tool = str(tool_id or "").strip().lower()
    cat = str(category or "").strip().lower()
    if tool.startswith("scb_") or cat in {"statistics", "scb_statistics"}:
        return "statistics"
    if tool.startswith("riksdag_") or cat.startswith("riksdag"):
        return "riksdagen"
    if tool.startswith("trafikverket_") or tool in {"trafiklab_route", "smhi_weather"}:
        return "trafik"
    if tool.startswith("bolagsverket_"):
        return "bolag"
    if tool.startswith("geoapify_"):
        return "kartor"
    if tool in {"generate_podcast", "display_image"}:
        return "media"
    if tool in {"search_web", "search_tavily", "scrape_webpage", "link_preview"}:
        return "browser"
    if tool in {"search_surfsense_docs", "search_knowledge_base"}:
        return "knowledge"
    return _agent_for_route_hint(route_value, sub_route_value)


def _candidate_agents_for_route(
    route_value: str | None,
    sub_route_value: str | None,
) -> list[str]:
    route_norm = _normalize_route_value(route_value)
    sub_norm = _normalize_sub_route_value(sub_route_value)
    if route_norm == Route.STATISTICS.value:
        return ["statistics", "riksdagen", "knowledge"]
    if route_norm == Route.COMPARE.value:
        return ["synthesis", "statistics", "knowledge"]
    if route_norm == Route.KNOWLEDGE.value:
        return ["knowledge", "riksdagen", "statistics", "browser"]
    if route_norm == Route.ACTION.value:
        if sub_norm == ActionRoute.TRAVEL.value:
            return ["trafik", "action", "kartor"]
        if sub_norm == ActionRoute.WEB.value:
            return ["browser", "action", "knowledge"]
        if sub_norm == ActionRoute.MEDIA.value:
            return ["media", "action"]
        if sub_norm == ActionRoute.DATA.value:
            return ["action", "statistics", "riksdagen", "bolag", "kartor"]
        return ["action", "browser", "trafik", "media", "bolag", "kartor"]
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
    if any(token in text for token in ("trafik", "väg", "halka", "smhi", "rutt", "resa", "avgång")):
        return "trafik" if "trafik" in candidates else candidates[0]
    if any(token in text for token in ("bolag", "organisationsnummer", "företag")):
        return "bolag" if "bolag" in candidates else candidates[0]
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
        "analysis": "Agent planner fallback selected the closest route-compatible agent.",
    }
    if llm is None:
        return fallback_payload
    planner_prompt = (
        "You evaluate next-stage agent routing in dry-run mode.\n"
        "Given route context and allowed agent candidates, pick exactly one agent.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "selected_agent": "one of candidate names",\n'
        '  "analysis": "short explanation"\n'
        "}\n"
        "Do not include markdown."
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
) -> tuple[str | None, str | None]:
    overrides = prompt_overrides or {}
    selected_route = await dispatch_route(
        question,
        llm,
        has_attachments=False,
        has_mentions=False,
        system_prompt_override=overrides.get("router.top_level"),
    )
    route_value = (
        selected_route.value
        if hasattr(selected_route, "value")
        else _normalize_route_value(selected_route)
    )
    selected_sub_route: str | None = None
    if route_value == Route.ACTION.value:
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
    elif route_value == Route.KNOWLEDGE.value:
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
    return _normalize_route_value(route_value), _normalize_sub_route_value(selected_sub_route)


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
        passed = False
        if lowered.startswith("field:"):
            field_name = requirement.split(":", 1)[1].strip()
            proposed_arguments = context_payload.get("proposed_arguments")
            if isinstance(proposed_arguments, dict) and field_name:
                passed = field_name in proposed_arguments
        elif lowered in {"clarification", "ask_clarification"}:
            passed = bool(context_payload.get("needs_clarification"))
        elif lowered.startswith("tool:"):
            expected_tool = requirement.split(":", 1)[1].strip().casefold()
            selected_tool = str(context_payload.get("selected_tool") or "").casefold()
            passed = bool(expected_tool and selected_tool and expected_tool == selected_tool)
        elif lowered.startswith("route:"):
            expected_route = requirement.split(":", 1)[1].strip().casefold()
            selected_route = str(context_payload.get("selected_route") or "").casefold()
            passed = bool(
                expected_route and selected_route and expected_route == selected_route
            )
        elif lowered.startswith("agent:"):
            expected_agent = requirement.split(":", 1)[1].strip().casefold()
            selected_agent = str(context_payload.get("selected_agent") or "").casefold()
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
            "Planner fallback: no model available, selected highest retrieval candidate."
        ),
        "plan_steps": [
            "Inspect retrieved candidates from tool_retrieval.",
            f"Select {fallback_entry.tool_id} as best metadata match.",
            "Stop before tool execution (eval dry-run).",
        ],
    }
    if llm is None:
        return fallback_payload

    planner_prompt = (
        "You are evaluating tool routing in dry-run mode.\n"
        "Given a user question and retrieved tool candidates, choose the single best tool.\n"
        "Never invent tool ids. You must only pick from candidate tool_ids.\n"
        "Return strict JSON only with this schema:\n"
        "{\n"
        '  "selected_tool_id": "tool_id or null",\n'
        '  "selected_category": "category or null",\n'
        '  "analysis": "short explanation",\n'
        '  "plan_steps": ["step 1", "step 2"]\n'
        "}\n"
        "Do not include markdown."
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
        key = cleaned.casefold()
        if key in seen_examples:
            continue
        proposed_examples.append(cleaned)
        seen_examples.add(key)
        if len(proposed_examples) >= 12:
            break

    description = str(current.get("description") or "").strip()
    hint_terms = [token for token, _count in sorted_tokens[:3]]
    if hint_terms:
        hint_suffix = ", ".join(hint_terms)
        marker = f"Relevant for terms like: {hint_suffix}."
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
    }
    rationale = (
        f"Fallback suggestion based on {failed_count} failed test case(s): "
        "expanded keywords and example queries with recurring terms."
    )
    return proposed, rationale


async def _build_llm_suggestion(
    *,
    tool_id: str,
    llm,
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
        "You optimize tool metadata for retrieval.\n"
        "Given current metadata and failed eval cases, propose improved metadata.\n"
        "Keep category unless strongly justified.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "name": "string",\n'
        '  "description": "string",\n'
        '  "keywords": ["..."],\n'
        '  "example_queries": ["..."],\n'
        '  "category": "string",\n'
        '  "rationale": "string"\n'
        "}\n"
        "Do not include markdown."
    )
    payload = {
        "current_metadata": current,
        "failed_cases": failures,
    }
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
            ]
        )
        text = str(getattr(response, "content", "") or "")
        parsed = _extract_json_object(text)
        if not parsed:
            return None
        suggested = {
            "tool_id": tool_id,
            "name": str(parsed.get("name") or current.get("name") or "").strip(),
            "description": str(
                parsed.get("description") or current.get("description") or ""
            ).strip(),
            "keywords": _safe_string_list(parsed.get("keywords"))
            or list(current.get("keywords") or []),
            "example_queries": _safe_string_list(parsed.get("example_queries"))
            or list(current.get("example_queries") or []),
            "category": str(
                parsed.get("category") or current.get("category") or ""
            ).strip(),
            "base_path": current.get("base_path"),
        }
        rationale = str(parsed.get("rationale") or "").strip()
        if not rationale:
            rationale = "LLM suggested updates based on failed routing cases."
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

    current_examples = _safe_string_list(current.get("example_queries"))
    proposed_examples = _safe_string_list(merged.get("example_queries"))
    fallback_examples = _safe_string_list(fallback.get("example_queries"))
    if proposed_examples == current_examples and fallback_examples != current_examples:
        merged["example_queries"] = fallback_examples
        enriched = True
    else:
        merged["example_queries"] = proposed_examples

    if "tool_id" not in merged:
        merged["tool_id"] = str(current.get("tool_id") or "")
    return merged, enriched


async def run_tool_evaluation(
    *,
    tests: list[dict[str, Any]],
    tool_index: list[ToolIndexEntry],
    llm,
    retrieval_limit: int = 5,
    retrieval_tuning: dict[str, Any] | None = None,
    prompt_overrides: dict[str, str] | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    retrieval_limit = max(1, min(int(retrieval_limit or 5), 15))
    normalized_tuning = normalize_retrieval_tuning(retrieval_tuning)
    index_by_id = {entry.tool_id: entry for entry in tool_index}
    results: list[dict[str, Any]] = []

    route_checks: list[bool] = []
    sub_route_checks: list[bool] = []
    agent_checks: list[bool] = []
    gated_scores: list[float] = []
    plan_checks: list[bool] = []
    category_checks: list[bool] = []
    tool_checks: list[bool] = []
    retrieval_checks: list[bool] = []

    for idx, test in enumerate(tests):
        test_id = str(test.get("id") or f"case-{idx + 1}")
        question = str(test.get("question") or "").strip()
        if progress_callback is not None:
            event = {
                "type": "test_started",
                "test_id": test_id,
                "index": idx,
                "question": question,
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
        expected_agent = _normalize_agent_name(expected.get("agent"))
        if expected_agent is None:
            expected_agent = _agent_for_tool(
                expected_tool,
                expected_category,
                expected_route,
                expected_sub_route,
            )
        allowed_tools = _safe_string_list(test.get("allowed_tools"))
        if expected_tool and not allowed_tools:
            allowed_tools = [expected_tool]

        selected_route: str | None = None
        selected_sub_route: str | None = None
        selected_agent: str | None = None
        passed_route: bool | None = None
        passed_sub_route: bool | None = None
        passed_agent: bool | None = None
        passed_plan: bool | None = None
        plan_requirement_checks: list[dict[str, Any]] = []

        try:
            selected_route, selected_sub_route = await _dispatch_route_from_start(
                question=question,
                llm=llm,
                prompt_overrides=prompt_overrides,
            )
            passed_route = (
                selected_route == expected_route if expected_route is not None else None
            )
            passed_sub_route = (
                selected_sub_route == expected_sub_route
                if expected_sub_route is not None
                else None
            )
            selected_agent_plan = await _plan_agent_choice(
                question=question,
                route_value=selected_route,
                sub_route_value=selected_sub_route,
                llm=llm,
            )
            selected_agent = _normalize_agent_name(selected_agent_plan.get("selected_agent"))
            passed_agent = (
                selected_agent == expected_agent if expected_agent is not None else None
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
                if expected_agent is not None:
                    passed_agent = selected_agent == expected_agent
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
            passed_category = (
                selected_category == expected_category
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
                    passed_route,
                    passed_sub_route,
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

            if passed_route is not None:
                route_checks.append(bool(passed_route))
            if passed_sub_route is not None:
                sub_route_checks.append(bool(passed_sub_route))
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
                "expected_route": expected_route,
                "expected_sub_route": expected_sub_route,
                "expected_agent": expected_agent,
                "expected_category": expected_category,
                "expected_tool": expected_tool,
                "allowed_tools": allowed_tools,
                "selected_route": selected_route,
                "selected_sub_route": selected_sub_route,
                "selected_agent": selected_agent,
                "selected_category": selected_category,
                "selected_tool": selected_tool,
                "planning_analysis": planning.get("analysis") or "",
                "planning_steps": _safe_string_list(planning.get("plan_steps")),
                "plan_requirement_checks": plan_requirement_checks,
                "retrieval_top_tools": retrieved_ids[:retrieval_limit],
                "retrieval_top_categories": [
                    index_by_id[tool_id].category
                    for tool_id in retrieved_ids[:retrieval_limit]
                    if tool_id in index_by_id
                ],
                "retrieval_breakdown": retrieval_breakdown[:retrieval_limit],
                "retrieval_hit_expected_tool": retrieval_hit_expected_tool,
                "passed_route": passed_route,
                "passed_sub_route": passed_sub_route,
                "passed_agent": passed_agent,
                "passed_plan": passed_plan,
                "passed_category": passed_category,
                "passed_tool": passed_tool,
                "passed_with_agent_gate": passed_with_agent_gate,
                "agent_gate_score": agent_gate_score,
                "passed": passed,
            }
            results.append(case_result)
            if progress_callback is not None:
                event = {
                    "type": "test_completed",
                    "test_id": test_id,
                    "index": idx,
                    "selected_route": selected_route,
                    "selected_sub_route": selected_sub_route,
                    "selected_agent": selected_agent,
                    "selected_tool": selected_tool,
                    "selected_category": selected_category,
                    "passed": passed,
                }
                maybe_result = progress_callback(event)
                if hasattr(maybe_result, "__await__"):
                    await maybe_result
        except Exception as exc:
            results.append(
                {
                    "test_id": test_id,
                    "question": question,
                    "expected_route": expected_route,
                    "expected_sub_route": expected_sub_route,
                    "expected_agent": expected_agent,
                    "expected_category": expected_category,
                    "expected_tool": expected_tool,
                    "allowed_tools": allowed_tools,
                    "selected_route": selected_route,
                    "selected_sub_route": selected_sub_route,
                    "selected_agent": selected_agent,
                    "selected_category": None,
                    "selected_tool": None,
                    "planning_analysis": f"Evaluation failed for this case: {exc}",
                    "planning_steps": [],
                    "plan_requirement_checks": [],
                    "retrieval_top_tools": [],
                    "retrieval_top_categories": [],
                    "retrieval_breakdown": [],
                    "retrieval_hit_expected_tool": None,
                    "passed_route": False if expected_route is not None else None,
                    "passed_sub_route": False if expected_sub_route is not None else None,
                    "passed_agent": False if expected_agent is not None else None,
                    "passed_plan": False if plan_requirements else None,
                    "passed_category": False if expected_category is not None else None,
                    "passed_tool": False if expected_tool is not None else None,
                    "passed_with_agent_gate": False,
                    "agent_gate_score": 0.0,
                    "passed": False,
                }
            )
            gated_scores.append(0.0)
            if expected_route is not None:
                route_checks.append(False)
            if expected_sub_route is not None:
                sub_route_checks.append(False)
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
    }
    return {"metrics": metrics, "results": results}


async def generate_tool_metadata_suggestions(
    *,
    evaluation_results: list[dict[str, Any]],
    tool_index: list[ToolIndexEntry],
    llm=None,
    max_suggestions: int = 20,
) -> list[dict[str, Any]]:
    index_by_id = {entry.tool_id: entry for entry in tool_index}
    grouped: dict[str, dict[str, Any]] = {}

    for result in evaluation_results:
        expected_tool = result.get("expected_tool")
        if not expected_tool or result.get("passed_tool") is True:
            continue
        if expected_tool not in index_by_id:
            continue
        bucket = grouped.setdefault(
            expected_tool,
            {"questions": [], "failed_test_ids": [], "wrong_tools": []},
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

    suggestions: list[dict[str, Any]] = []
    for tool_id, failure_data in grouped.items():
        if len(suggestions) >= max_suggestions:
            break
        entry = index_by_id[tool_id]
        current = _serialize_tool(entry)
        current["base_path"] = entry.base_path
        failures = [
            {
                "question": question,
                "selected_wrong_tool": failure_data["wrong_tools"][idx]
                if idx < len(failure_data["wrong_tools"])
                else None,
            }
            for idx, question in enumerate(failure_data["questions"])
        ]

        llm_suggestion = await _build_llm_suggestion(
            tool_id=tool_id,
            llm=llm,
            current=current,
            failures=failures,
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
                    f"{rationale} Added fallback improvements for description, "
                    "keywords, and example queries from failed cases."
                )
        else:
            proposed, rationale = fallback_proposed, fallback_rationale
        if _metadata_equal(current, proposed):
            continue
        suggestions.append(
            {
                "tool_id": tool_id,
                "failed_test_ids": list(failure_data["failed_test_ids"]),
                "rationale": rationale,
                "current_metadata": current,
                "proposed_metadata": proposed,
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
                "No tuning changes recommended from this run. Current retrieval "
                "weights already produced successful results."
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
        fallback_proposed["embedding_weight"] = min(
            25.0, fallback_proposed["embedding_weight"] + 1.0
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
        "Fallback tuning suggestion based on eval metrics: adjusted lexical/semantic "
        "weights and rerank candidate window to improve retrieval recall and tool hit rate."
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
        "You optimize retrieval tuning weights for tool routing evaluation.\n"
        "Given current weights and failed cases, propose updated weights.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "name_match_weight": number,\n'
        '  "keyword_weight": number,\n'
        '  "description_token_weight": number,\n'
        '  "example_query_weight": number,\n'
        '  "namespace_boost": number,\n'
        '  "embedding_weight": number,\n'
        '  "rerank_candidates": integer,\n'
        '  "rationale": "string"\n'
        "}\n"
        "Do not include markdown."
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
        proposed = normalize_retrieval_tuning(parsed).__dict__
        if proposed == normalized_current.__dict__:
            return None
        rationale = str(parsed.get("rationale") or "").strip() or (
            "LLM suggested retrieval tuning updates based on failed eval cases."
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
    if tool_id in {"trafiklab_route", "smhi_weather"}:
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
    mapping = {
        "statistics": "agent.statistics.system",
        "riksdagen": "agent.riksdagen.system",
        "trafik": "agent.trafik.system",
        "bolag": "agent.bolag.system",
        "kartor": "agent.kartor.system",
        "media": "agent.media.system",
        "browser": "agent.browser.system",
        "knowledge": "agent.knowledge.system",
        "action": "agent.action.system",
        "synthesis": "agent.synthesis.system",
    }
    return mapping.get(normalized) if normalized else None


def _prompt_key_for_sub_route(route_value: str | None) -> str | None:
    normalized = _normalize_route_value(route_value)
    if normalized == Route.ACTION.value:
        return "router.action"
    if normalized == Route.KNOWLEDGE.value:
        return "router.knowledge"
    return None


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
            "Planner fallback: selected highest retrieval candidate and kept dry-run arguments empty."
        ),
        "plan_steps": [
            "Inspect retrieved candidates from tool_retrieval.",
            f"Select {fallback_entry.tool_id} as best metadata match.",
            "Draft tool arguments in dry-run mode without executing the tool.",
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
        "You are evaluating API input quality in dry-run mode.\n"
        "Pick one best tool among candidates and draft the tool call arguments.\n"
        "Do not execute tools. Do not invent tool ids.\n"
        "If required information is missing, set needs_clarification=true.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "selected_tool_id": "tool_id or null",\n'
        '  "selected_category": "category or null",\n'
        '  "analysis": "short explanation",\n'
        '  "plan_steps": ["step 1", "step 2"],\n'
        '  "proposed_arguments": {"field": "value"},\n'
        '  "needs_clarification": false,\n'
        '  "clarification_question": "question or null"\n'
        "}\n"
        "Do not include markdown."
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
    retrieval_tuning: dict[str, Any] | None = None,
    prompt_overrides: dict[str, str] | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    retrieval_limit = max(1, min(int(retrieval_limit or 5), 15))
    normalized_tuning = normalize_retrieval_tuning(retrieval_tuning)
    index_by_id = {entry.tool_id: entry for entry in tool_index}
    results: list[dict[str, Any]] = []

    route_checks: list[bool] = []
    sub_route_checks: list[bool] = []
    agent_checks: list[bool] = []
    gated_scores: list[float] = []
    plan_checks: list[bool] = []
    category_checks: list[bool] = []
    tool_checks: list[bool] = []
    schema_checks: list[bool] = []
    required_field_recalls: list[float] = []
    field_value_checks: list[bool] = []
    clarification_checks: list[bool] = []

    for idx, test in enumerate(tests):
        test_id = str(test.get("id") or f"case-{idx + 1}")
        question = str(test.get("question") or "").strip()
        if progress_callback is not None:
            event = {
                "type": "test_started",
                "test_id": test_id,
                "index": idx,
                "question": question,
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
        expected_agent = _normalize_agent_name(expected.get("agent"))
        if expected_agent is None:
            expected_agent = _agent_for_tool(
                expected_tool,
                expected_category,
                expected_route,
                expected_sub_route,
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
        if expected_tool and not allowed_tools:
            allowed_tools = [expected_tool]

        selected_route: str | None = None
        selected_sub_route: str | None = None
        selected_agent: str | None = None
        passed_route: bool | None = None
        passed_sub_route: bool | None = None
        passed_agent: bool | None = None
        passed_plan: bool | None = None
        plan_requirement_checks: list[dict[str, Any]] = []

        try:
            selected_route, selected_sub_route = await _dispatch_route_from_start(
                question=question,
                llm=llm,
                prompt_overrides=prompt_overrides,
            )
            passed_route = (
                selected_route == expected_route if expected_route is not None else None
            )
            passed_sub_route = (
                selected_sub_route == expected_sub_route
                if expected_sub_route is not None
                else None
            )
            selected_agent_plan = await _plan_agent_choice(
                question=question,
                route_value=selected_route,
                sub_route_value=selected_sub_route,
                llm=llm,
            )
            selected_agent = _normalize_agent_name(selected_agent_plan.get("selected_agent"))
            passed_agent = (
                selected_agent == expected_agent if expected_agent is not None else None
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
                if expected_agent is not None:
                    passed_agent = selected_agent == expected_agent
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

            passed_category = (
                selected_category == expected_category
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
            if passed_route is not None:
                route_checks.append(bool(passed_route))
            if passed_sub_route is not None:
                sub_route_checks.append(bool(passed_sub_route))
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
                    passed_route,
                    passed_sub_route,
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
                "expected_route": expected_route,
                "expected_sub_route": expected_sub_route,
                "expected_agent": expected_agent,
                "expected_category": expected_category,
                "expected_tool": expected_tool,
                "allowed_tools": allowed_tools,
                "selected_route": selected_route,
                "selected_sub_route": selected_sub_route,
                "selected_agent": selected_agent,
                "selected_category": selected_category,
                "selected_tool": selected_tool,
                "planning_analysis": planning.get("analysis") or "",
                "planning_steps": _safe_string_list(planning.get("plan_steps")),
                "plan_requirement_checks": plan_requirement_checks,
                "retrieval_top_tools": retrieved_ids[:retrieval_limit],
                "retrieval_top_categories": [
                    index_by_id[tool_id].category
                    for tool_id in retrieved_ids[:retrieval_limit]
                    if tool_id in index_by_id
                ],
                "retrieval_breakdown": retrieval_breakdown[:retrieval_limit],
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
                "passed_route": passed_route,
                "passed_sub_route": passed_sub_route,
                "passed_agent": passed_agent,
                "passed_plan": passed_plan,
                "passed_category": passed_category,
                "passed_tool": passed_tool,
                "passed_api_input": passed_api_input,
                "passed_with_agent_gate": passed_with_agent_gate,
                "agent_gate_score": agent_gate_score,
                "passed": passed,
            }
            results.append(case_result)
            if progress_callback is not None:
                event = {
                    "type": "test_completed",
                    "test_id": test_id,
                    "index": idx,
                    "selected_route": selected_route,
                    "selected_sub_route": selected_sub_route,
                    "selected_agent": selected_agent,
                    "selected_tool": selected_tool,
                    "selected_category": selected_category,
                    "passed": passed,
                }
                maybe_result = progress_callback(event)
                if hasattr(maybe_result, "__await__"):
                    await maybe_result
        except Exception as exc:
            case_result = {
                "test_id": test_id,
                "question": question,
                "expected_route": expected_route,
                "expected_sub_route": expected_sub_route,
                "expected_agent": expected_agent,
                "expected_category": expected_category,
                "expected_tool": expected_tool,
                "allowed_tools": allowed_tools,
                "selected_route": selected_route,
                "selected_sub_route": selected_sub_route,
                "selected_agent": selected_agent,
                "selected_category": None,
                "selected_tool": None,
                "planning_analysis": f"API input evaluation failed for this case: {exc}",
                "planning_steps": [],
                "plan_requirement_checks": [],
                "retrieval_top_tools": [],
                "retrieval_top_categories": [],
                "retrieval_breakdown": [],
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
                "passed_route": False if expected_route is not None else None,
                "passed_sub_route": False if expected_sub_route is not None else None,
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
            gated_scores.append(0.0)
            if expected_route is not None:
                route_checks.append(False)
            if expected_sub_route is not None:
                sub_route_checks.append(False)
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
    }
    return {"metrics": metrics, "results": results}


def _build_fallback_prompt_suggestion(
    *,
    prompt_key: str,
    current_prompt: str,
    failures: list[dict[str, Any]],
) -> tuple[str, str]:
    missing_counter: Counter[str] = Counter()
    for failure in failures:
        for field_name in failure.get("missing_required_fields") or []:
            cleaned = str(field_name).strip()
            if cleaned:
                missing_counter[cleaned] += 1
    common_missing = [item for item, _count in missing_counter.most_common(8)]
    if prompt_key.startswith("router."):
        lines = [
            "- Return exactly one valid route label and avoid extra text.",
            "- Prioritize semantic intent over keyword overlap for borderline queries.",
            "- If the query clearly asks for official statistics, prefer statistics route.",
            "- If a query asks for execution/tool actions, prefer action route over knowledge.",
        ]
        if prompt_key == "router.action":
            lines = [
                "- Return exactly one of: web, media, travel, data.",
                "- Use travel for weather, departures, routes, and commute queries.",
                "- Use web for URL/link/scrape and page-content requests.",
                "- Use data for jobs/Libris/dataset lookups.",
            ]
        elif prompt_key == "router.knowledge":
            lines = [
                "- Return exactly one of: docs, internal, external.",
                "- Use docs for SurfSense product/how-to questions.",
                "- Use internal for user data/notes/calendar/search space content.",
                "- Use external only for explicit realtime/public-web requests.",
            ]
    elif prompt_key == "agent.supervisor.system":
        lines = [
            "- Keep this prompt minimal: only coordinate route, agent calls, and final synthesis.",
            "- Delegate domain reasoning and argument details to specialized agent/tool prompts.",
            "- Never include long tool catalogs or endpoint specifics in supervisor prompt.",
            "- Use retrieval results to pick candidate agents/tools dynamically before execution.",
        ]
    elif prompt_key.startswith("tool."):
        lines = [
            "- Focus only on this single tool endpoint and ignore unrelated tools.",
            "- Map user intent to this tool's schema using exact argument field names.",
            "- If required fields are missing, ask one concise clarification question.",
            "- Do not add arguments that are outside the selected tool schema.",
        ]
    elif prompt_key.startswith("agent."):
        lines = [
            "- Choose tools that match the selected agent domain before generating arguments.",
            "- Reject tools outside your domain unless user intent explicitly shifts domain.",
            "- Keep planning concise: domain fit -> tool fit -> argument completeness.",
            "- If domain-critical fields are missing, ask a focused clarification question.",
        ]
    else:
        lines = [
            "- Validate argument completeness before emitting a tool call.",
            "- If required arguments are missing or ambiguous, ask a concise clarification question first.",
            "- Use exact argument names from the target tool schema and avoid unsupported fields.",
        ]
    if common_missing:
        lines.insert(
            0,
            f"- Prioritize extracting these frequently missed fields: {', '.join(common_missing)}.",
        )
    appendix = (
        "\n\n[API INPUT EVAL IMPROVEMENT]\n"
        f"Prompt key: {prompt_key}\n"
        + "\n".join(lines)
    )
    proposed_prompt = current_prompt
    if appendix.strip() not in current_prompt:
        proposed_prompt = f"{current_prompt.rstrip()}{appendix}"
    rationale = (
        f"Fallback prompt improvement from {len(failures)} failed eval case(s): "
        "adds stricter routing/argument selection behavior."
    )
    return proposed_prompt, rationale


async def _build_llm_prompt_suggestion(
    *,
    prompt_key: str,
    current_prompt: str,
    failures: list[dict[str, Any]],
    llm,
) -> tuple[str, str] | None:
    if llm is None:
        return None
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm
    prompt = (
        "You optimize one routing/agent prompt to improve dry-run evaluation quality.\n"
        "Keep the current style and intent, but add precise instructions to improve route decisions, planning, and argument extraction.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "proposed_prompt": "full revised prompt text",\n'
        '  "rationale": "short rationale"\n'
        "}\n"
        "Do not include markdown."
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
        rationale = str(parsed.get("rationale") or "").strip()
        if not rationale:
            rationale = "LLM suggested prompt updates from API input failures."
        return proposed_prompt, rationale
    except Exception:
        return None


async def suggest_agent_prompt_improvements_for_api_input(
    *,
    evaluation_results: list[dict[str, Any]],
    current_prompts: dict[str, str],
    llm=None,
    max_suggestions: int = 8,
) -> list[dict[str, Any]]:
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
                "expected_sub_route": result.get("expected_sub_route"),
                "selected_sub_route": result.get("selected_sub_route"),
                "expected_agent": result.get("expected_agent"),
                "selected_agent": result.get("selected_agent"),
                "expected_tool": expected_tool,
                "selected_tool": selected_tool,
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
        passed_route = result.get("passed_route")
        passed_sub_route = result.get("passed_sub_route")
        passed_agent = result.get("passed_agent")
        passed_plan = result.get("passed_plan")
        has_api_input = "passed_api_input" in result
        failed_route = passed_route is False
        failed_sub_route = passed_sub_route is False
        failed_agent = passed_agent is False
        failed_plan = passed_plan is False
        failed_api_input = passed_api_input is False if has_api_input else False
        if not (
            failed_route
            or failed_sub_route
            or failed_agent
            or failed_plan
            or failed_api_input
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

        if failed_route:
            _append_failure(
                "router.top_level",
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

        if "agent.supervisor.system" in current_prompts:
            _append_failure(
                "agent.supervisor.system",
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
        )
        llm_result = await _build_llm_prompt_suggestion(
            prompt_key=prompt_key,
            current_prompt=current_prompt,
            failures=bucket["failures"],
            llm=llm,
        )
        if llm_result is None:
            proposed_prompt, rationale = fallback_prompt, fallback_rationale
        else:
            proposed_prompt, rationale = llm_result
            if proposed_prompt.strip() == current_prompt.strip():
                proposed_prompt = fallback_prompt
                rationale = (
                    f"{rationale} Added fallback constraints from API input failures."
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
