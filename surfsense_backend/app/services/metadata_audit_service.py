from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.new_chat.bigtool_store import (
    ToolIndexEntry,
    smart_retrieve_tools_with_breakdown,
)


_TOOL_AUDIT_STOPWORDS = {
    "och",
    "att",
    "det",
    "den",
    "som",
    "for",
    "med",
    "pa",
    "i",
    "av",
    "till",
    "fran",
    "hur",
    "vad",
    "visa",
    "kan",
    "finns",
    "sverige",
}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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
) -> list[str]:
    hints = list(entry.keywords[: max(2, query_count * 2)])
    if not hints:
        hints = _tokenize(entry.description)[: max(2, query_count * 2)]
    prompts: list[str] = []
    for hint in hints:
        prompts.append(f"Visa {hint} for Stockholm idag")
        if len(prompts) >= query_count:
            break
    if len(prompts) < query_count:
        prompts.append(f"Hjalp mig med {entry.name} for Sverige")
    if neighbors and len(prompts) < query_count:
        prompts.append(
            f"Nar ska jag anvanda {entry.name} i stallet for {neighbors[0]}?"
        )
    deduped: list[str] = []
    seen: set[str] = set()
    for prompt in prompts:
        normalized = prompt.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped[:query_count]


async def _generate_probe_queries_for_tool(
    *,
    llm: Any,
    entry: ToolIndexEntry,
    neighbors: list[str],
    query_count: int,
) -> list[str]:
    if llm is None:
        return _fallback_probe_queries(
            entry=entry,
            neighbors=neighbors,
            query_count=query_count,
        )
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0)
    except Exception:
        model = llm

    prompt = (
        "You generate Swedish probe queries for metadata audit.\n"
        "Goal: create user questions that should clearly map to one tool and help "
        "separate it from similar tools.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "queries": ["query 1", "query 2"]\n'
        "}\n"
        "Rules:\n"
        "- Swedish language.\n"
        "- No markdown.\n"
        "- Keep each query short and realistic.\n"
        "- Include at least one borderline/ambiguous query.\n"
    )
    payload = {
        "tool_id": entry.tool_id,
        "tool_name": entry.name,
        "description": entry.description,
        "keywords": entry.keywords,
        "example_queries": entry.example_queries[:8],
        "nearby_tools": neighbors,
        "query_count": max(1, int(query_count)),
    }
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
            ]
        )
        parsed = _extract_json_object(
            _response_content_to_text(getattr(response, "content", ""))
        )
        if not parsed:
            return _fallback_probe_queries(
                entry=entry,
                neighbors=neighbors,
                query_count=query_count,
            )
        generated = _safe_string_list(parsed.get("queries"))
        if not generated:
            return _fallback_probe_queries(
                entry=entry,
                neighbors=neighbors,
                query_count=query_count,
            )
        return generated[:query_count]
    except Exception:
        return _fallback_probe_queries(
            entry=entry,
            neighbors=neighbors,
            query_count=query_count,
        )


def _dedupe_queries(queries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for query, source in queries:
        cleaned = _normalize_text(query)
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
    capped = max(1, min(int(max_tools or 25), 200))
    return selected[:capped]


async def run_tool_metadata_audit(
    *,
    tool_index: list[ToolIndexEntry],
    llm: Any,
    retrieval_tuning: dict[str, Any] | None = None,
    tool_ids: list[str] | None = None,
    tool_id_prefix: str | None = None,
    include_existing_examples: bool = True,
    include_llm_generated: bool = True,
    llm_queries_per_tool: int = 3,
    max_queries_per_tool: int = 6,
    retrieval_limit: int = 5,
    max_tools: int = 25,
) -> dict[str, Any]:
    selected_entries = _select_audit_entries(
        tool_index=tool_index,
        tool_ids=list(tool_ids or []),
        tool_id_prefix=tool_id_prefix,
        max_tools=max_tools,
    )
    neighbors_by_tool = _nearest_neighbor_map(selected_entries, max_neighbors=3)
    probe_rows: list[dict[str, Any]] = []
    confusion_counts: dict[tuple[str, str], int] = {}

    internal_retrieval_limit = max(2, min(int(retrieval_limit or 5), 20))
    max_probe_queries = max(1, min(int(max_queries_per_tool or 6), 20))
    llm_query_count = max(1, min(int(llm_queries_per_tool or 3), 10))

    for entry in selected_entries:
        queries: list[tuple[str, str]] = []
        if include_existing_examples:
            queries.extend((query, "existing_example") for query in entry.example_queries[:max_probe_queries])
        if include_llm_generated:
            generated = await _generate_probe_queries_for_tool(
                llm=llm,
                entry=entry,
                neighbors=neighbors_by_tool.get(entry.tool_id, []),
                query_count=llm_query_count,
            )
            queries.extend((query, "llm_generated") for query in generated)
        queries = _dedupe_queries(queries)[:max_probe_queries]
        for query, source in queries:
            selected_tool_ids, retrieval_breakdown = smart_retrieve_tools_with_breakdown(
                query,
                tool_index=tool_index,
                primary_namespaces=[("tools",)],
                fallback_namespaces=[],
                limit=internal_retrieval_limit,
                tuning=retrieval_tuning,
            )
            predicted_tool_id = (
                str(selected_tool_ids[0]).strip()
                if selected_tool_ids
                else None
            )
            target_tool_id = entry.tool_id
            is_correct = predicted_tool_id == target_tool_id
            target_rank = None
            for idx, candidate_id in enumerate(selected_tool_ids):
                if str(candidate_id).strip() == target_tool_id:
                    target_rank = idx + 1
                    break
            top_score = (
                float(retrieval_breakdown[0].get("pre_rerank_score") or retrieval_breakdown[0].get("score") or 0.0)
                if retrieval_breakdown
                else None
            )
            second_score = (
                float(retrieval_breakdown[1].get("pre_rerank_score") or retrieval_breakdown[1].get("score") or 0.0)
                if len(retrieval_breakdown) > 1
                else None
            )
            confidence_margin = (
                (top_score - second_score)
                if top_score is not None and second_score is not None
                else None
            )
            if predicted_tool_id and predicted_tool_id != target_tool_id:
                key = (target_tool_id, predicted_tool_id)
                confusion_counts[key] = confusion_counts.get(key, 0) + 1
            probe_id = hashlib.sha256(
                f"{target_tool_id}|{source}|{query}".encode("utf-8")
            ).hexdigest()[:20]
            probe_rows.append(
                {
                    "probe_id": probe_id,
                    "query": query,
                    "source": source,
                    "target_tool_id": target_tool_id,
                    "predicted_tool_id": predicted_tool_id,
                    "predicted_tool_ids": [str(tool_id) for tool_id in selected_tool_ids],
                    "target_rank": target_rank,
                    "is_correct": is_correct,
                    "confidence_margin": confidence_margin,
                    "retrieval_breakdown": list(retrieval_breakdown[:internal_retrieval_limit]),
                }
            )

    total_probes = len(probe_rows)
    correct_top1 = sum(1 for row in probe_rows if row.get("is_correct"))
    top1_accuracy = (correct_top1 / total_probes) if total_probes else 0.0
    ambiguous_count = sum(
        1
        for row in probe_rows
        if row.get("confidence_margin") is not None and float(row.get("confidence_margin")) < 0.75
    )
    confusion_pairs = [
        {
            "expected_tool_id": expected_tool_id,
            "predicted_tool_id": predicted_tool_id,
            "count": count,
        }
        for (expected_tool_id, predicted_tool_id), count in sorted(
            confusion_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:30]
    ]
    return {
        "probes": probe_rows,
        "summary": {
            "total_probes": total_probes,
            "correct_top1": correct_top1,
            "incorrect_top1": max(0, total_probes - correct_top1),
            "top1_accuracy": top1_accuracy,
            "ambiguous_count": ambiguous_count,
            "confusion_pairs": confusion_pairs,
        },
    }


def build_suggestion_inputs_from_audit_annotations(
    *,
    annotations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    evaluation_results: list[dict[str, Any]] = []
    confusion_counts: dict[tuple[str, str], int] = {}
    reviewed_failures = 0

    for item in annotations:
        query = _normalize_text(item.get("query"))
        target_tool_id = _normalize_text(item.get("target_tool_id"))
        predicted_tool_id = _normalize_text(item.get("predicted_tool_id")) or None
        corrected_tool_id = _normalize_text(item.get("corrected_tool_id")) or None
        is_correct = bool(item.get("is_correct", True))
        expected_tool = corrected_tool_id or target_tool_id
        passed_tool = bool(is_correct)
        if not is_correct:
            reviewed_failures += 1
            if predicted_tool_id and expected_tool and predicted_tool_id != expected_tool:
                key = (expected_tool, predicted_tool_id)
                confusion_counts[key] = confusion_counts.get(key, 0) + 1
        evaluation_results.append(
            {
                "test_id": _normalize_text(item.get("probe_id")) or hashlib.sha256(
                    f"{expected_tool}|{query}".encode("utf-8")
                ).hexdigest()[:20],
                "question": query,
                "expected_tool": expected_tool,
                "selected_tool": predicted_tool_id,
                "passed_tool": passed_tool,
                "passed": passed_tool,
                "retrieval_breakdown": (
                    list(item.get("retrieval_breakdown"))
                    if isinstance(item.get("retrieval_breakdown"), list)
                    else []
                ),
            }
        )
    confusion_pairs = [
        {
            "expected_tool_id": expected_tool_id,
            "predicted_tool_id": predicted_tool_id,
            "count": count,
        }
        for (expected_tool_id, predicted_tool_id), count in sorted(
            confusion_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:30]
    ]
    return evaluation_results, confusion_pairs, reviewed_failures
