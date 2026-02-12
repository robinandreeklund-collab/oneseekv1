from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.new_chat.bigtool_store import ToolIndexEntry, smart_retrieve_tools

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


async def run_tool_evaluation(
    *,
    tests: list[dict[str, Any]],
    tool_index: list[ToolIndexEntry],
    llm,
    retrieval_limit: int = 5,
) -> dict[str, Any]:
    retrieval_limit = max(1, min(int(retrieval_limit or 5), 15))
    index_by_id = {entry.tool_id: entry for entry in tool_index}
    results: list[dict[str, Any]] = []

    category_checks: list[bool] = []
    tool_checks: list[bool] = []
    retrieval_checks: list[bool] = []

    for idx, test in enumerate(tests):
        test_id = str(test.get("id") or f"case-{idx + 1}")
        question = str(test.get("question") or "").strip()
        expected = test.get("expected") or {}
        if not isinstance(expected, dict):
            expected = {}
        expected_tool = expected.get("tool")
        expected_tool = str(expected_tool).strip() if expected_tool else None
        expected_category = expected.get("category")
        expected_category = (
            str(expected_category).strip() if expected_category else None
        )
        allowed_tools = _safe_string_list(test.get("allowed_tools"))
        if expected_tool and not allowed_tools:
            allowed_tools = [expected_tool]

        retrieved_ids = smart_retrieve_tools(
            question,
            tool_index=tool_index,
            primary_namespaces=[("tools",)],
            fallback_namespaces=[],
            limit=max(retrieval_limit, 8),
            trace_key=None,
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
        checks = [check for check in (passed_category, passed_tool) if check is not None]
        passed = all(checks) if checks else True
        retrieval_hit_expected_tool = (
            expected_tool in retrieved_ids[:retrieval_limit]
            if expected_tool is not None
            else None
        )

        if passed_category is not None:
            category_checks.append(bool(passed_category))
        if passed_tool is not None:
            tool_checks.append(bool(passed_tool))
        if retrieval_hit_expected_tool is not None:
            retrieval_checks.append(bool(retrieval_hit_expected_tool))

        results.append(
            {
                "test_id": test_id,
                "question": question,
                "expected_category": expected_category,
                "expected_tool": expected_tool,
                "allowed_tools": allowed_tools,
                "selected_category": selected_category,
                "selected_tool": selected_tool,
                "planning_analysis": planning.get("analysis") or "",
                "planning_steps": _safe_string_list(planning.get("plan_steps")),
                "retrieval_top_tools": retrieved_ids[:retrieval_limit],
                "retrieval_top_categories": [
                    index_by_id[tool_id].category
                    for tool_id in retrieved_ids[:retrieval_limit]
                    if tool_id in index_by_id
                ],
                "retrieval_hit_expected_tool": retrieval_hit_expected_tool,
                "passed_category": passed_category,
                "passed_tool": passed_tool,
                "passed": passed,
            }
        )

    total_tests = len(results)
    passed_count = sum(1 for item in results if item.get("passed"))
    metrics = {
        "total_tests": total_tests,
        "passed_tests": passed_count,
        "success_rate": (passed_count / total_tests) if total_tests else 0.0,
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
            llm=llm,
            current=current,
            failures=failures,
        )
        if llm_suggestion is not None:
            proposed, rationale = llm_suggestion
        else:
            proposed, rationale = _build_fallback_suggestion(
                current=current,
                questions=failure_data["questions"],
                failed_count=len(failure_data["questions"]),
            )
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
