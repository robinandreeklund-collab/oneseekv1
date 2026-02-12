import asyncio
import json
import logging
import random
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.bigtool_store import (
    build_global_tool_registry,
    build_tool_index,
    clear_tool_caches,
)
from app.db import (
    GlobalToolEvaluationRun,
    GlobalToolMetadataOverrideHistory,
    SearchSpaceMembership,
    User,
    async_session_maker,
    get_async_session,
)
from app.schemas.admin_tool_settings import (
    ToolApplySuggestionsRequest,
    ToolApplySuggestionsResponse,
    ToolApiCategoriesResponse,
    ToolCategoryResponse,
    ToolEvalLibraryFileResponse,
    ToolEvalLibraryGenerateRequest,
    ToolEvalLibraryGenerateResponse,
    ToolEvalLibraryListResponse,
    ToolEvaluationCaseStatus,
    ToolEvaluationJobStatusResponse,
    ToolEvaluationRequest,
    ToolEvaluationResponse,
    ToolEvaluationStartResponse,
    ToolMetadataHistoryResponse,
    ToolMetadataItem,
    ToolMetadataUpdateItem,
    ToolRetrievalTuning,
    ToolRetrievalTuningResponse,
    ToolSettingsUpdateRequest,
    ToolSuggestionRequest,
    ToolSuggestionResponse,
    ToolSettingsResponse,
)
from app.services.connector_service import ConnectorService
from app.services.llm_service import get_agent_llm
from app.services.tool_evaluation_service import (
    compute_metadata_version_hash,
    generate_tool_metadata_suggestions,
    run_tool_evaluation,
    suggest_retrieval_tuning,
)
from app.services.tool_metadata_service import (
    get_global_tool_metadata_overrides,
    merge_tool_metadata_overrides,
    normalize_tool_metadata_payload,
    tool_metadata_payload_equal,
    upsert_global_tool_metadata_overrides,
)
from app.services.tool_retrieval_tuning_service import (
    get_global_tool_retrieval_tuning,
    normalize_tool_retrieval_tuning,
    upsert_global_tool_retrieval_tuning,
)
from app.users import current_active_user
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
_EVAL_JOBS: dict[str, dict[str, Any]] = {}
_EVAL_JOBS_LOCK = asyncio.Lock()
_MAX_EVAL_JOBS = 100
_EVAL_LIBRARY_ROOT = Path(__file__).resolve().parents[3] / "eval" / "api"
_EVAL_INTERNAL_TOOL_IDS = {
    "write_todos",
    "reflect_on_progress",
    "retrieve_agents",
    "call_agent",
    "call_agents_parallel",
    "save_memory",
    "recall_memory",
}


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _require_admin(
    session: AsyncSession,
    user: User,
) -> list[int]:
    result = await session.execute(
        select(SearchSpaceMembership.search_space_id)
        .filter(
            SearchSpaceMembership.user_id == user.id,
            SearchSpaceMembership.is_owner.is_(True),
        )
    )
    owned_search_space_ids = [int(row[0]) for row in result.all() if row and row[0] is not None]
    if not owned_search_space_ids:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to manage tool settings",
        )
    return owned_search_space_ids


def _category_name(category_id: str) -> str:
    cleaned = (category_id or "general").replace("_", " ").replace("/", " / ")
    words = [word.capitalize() for word in cleaned.split()]
    return " ".join(words) or "General"


def _build_tool_api_categories_response() -> dict[str, Any]:
    providers: list[dict[str, Any]] = []
    try:
        from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS

        scb_items: list[dict[str, Any]] = []
        for definition in SCB_TOOL_DEFINITIONS:
            base_path = str(definition.base_path or "").strip()
            top_level = base_path.endswith("/") and base_path.count("/") == 1
            category_id = base_path.split("/", 1)[0] if base_path else definition.tool_id
            category_name = str(definition.name or "").replace("SCB ", "").strip()
            scb_items.append(
                {
                    "tool_id": definition.tool_id,
                    "tool_name": definition.name,
                    "category_id": category_id,
                    "category_name": category_name,
                    "level": "top_level" if top_level else "subcategory",
                    "description": definition.description,
                    "base_path": definition.base_path,
                }
            )
        scb_items.sort(key=lambda item: (item["level"] != "top_level", item["category_name"].lower()))
        providers.append(
            {
                "provider_key": "scb",
                "provider_name": "SCB",
                "categories": scb_items,
            }
        )
    except Exception:
        logger.exception("Failed to load SCB API categories")

    try:
        from app.agents.new_chat.riksdagen_agent import (
            RIKSDAGEN_TOOL_DEFINITIONS,
            RIKSDAGEN_TOP_LEVEL_TOOLS,
        )

        top_level_ids = {definition.tool_id for definition in RIKSDAGEN_TOP_LEVEL_TOOLS}
        riksdag_items: list[dict[str, Any]] = []
        for definition in RIKSDAGEN_TOOL_DEFINITIONS:
            level = "top_level" if definition.tool_id in top_level_ids else "subcategory"
            category_id = str(definition.category or "riksdagen").strip()
            riksdag_items.append(
                {
                    "tool_id": definition.tool_id,
                    "tool_name": definition.name,
                    "category_id": category_id,
                    "category_name": _category_name(category_id),
                    "level": level,
                    "description": definition.description,
                    "base_path": None,
                }
            )
        riksdag_items.sort(
            key=lambda item: (
                item["level"] != "top_level",
                item["category_name"].lower(),
                item["tool_name"].lower(),
            )
        )
        providers.append(
            {
                "provider_key": "riksdagen",
                "provider_name": "Riksdagen",
                "categories": riksdag_items,
            }
        )
    except Exception:
        logger.exception("Failed to load Riksdagen API categories")

    return {"providers": providers}


def _slugify(value: str, fallback: str = "eval") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or fallback


def _provider_for_tool_id(tool_id: str) -> str:
    if tool_id.startswith("scb_"):
        return "scb"
    if tool_id.startswith("riksdag_"):
        return "riksdagen"
    return "other"


def _is_eval_candidate_entry(entry: Any) -> bool:
    tool_id = str(getattr(entry, "tool_id", "") or "")
    if not tool_id or tool_id in _EVAL_INTERNAL_TOOL_IDS:
        return False
    return True


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


def _normalize_generated_tests(
    *,
    tests: list[dict[str, Any]],
    selected_entries: list[Any],
    question_count: int,
    include_allowed_tools: bool,
) -> list[dict[str, Any]]:
    if not selected_entries:
        return []
    by_tool_id = {str(entry.tool_id): entry for entry in selected_entries}
    normalized: list[dict[str, Any]] = []
    for idx in range(question_count):
        source = tests[idx] if idx < len(tests) else {}
        if not isinstance(source, dict):
            source = {}
        fallback_entry = selected_entries[idx % len(selected_entries)]
        expected = source.get("expected") or {}
        if not isinstance(expected, dict):
            expected = {}
        expected_tool = str(
            expected.get("tool")
            or source.get("expected_tool")
            or getattr(fallback_entry, "tool_id", "")
        ).strip()
        if expected_tool not in by_tool_id:
            expected_tool = str(getattr(fallback_entry, "tool_id", "") or "")
        entry = by_tool_id.get(expected_tool, fallback_entry)
        expected_category = str(
            expected.get("category")
            or source.get("expected_category")
            or getattr(entry, "category", "")
        ).strip()
        question = str(source.get("question") or "").strip()
        if not question:
            examples = list(getattr(entry, "example_queries", []) or [])
            if examples:
                question = examples[idx % len(examples)]
            else:
                question = (
                    f"Vilket verktyg ska användas för: {getattr(entry, 'name', expected_tool)}?"
                )
        normalized.append(
            {
                "id": str(source.get("id") or f"case-{idx + 1}"),
                "question": question,
                "expected": {
                    "tool": expected_tool,
                    "category": expected_category or getattr(entry, "category", None),
                },
                "allowed_tools": [expected_tool] if include_allowed_tools else [],
            }
        )
    return normalized


def _build_fallback_generated_tests(
    *,
    selected_entries: list[Any],
    question_count: int,
    include_allowed_tools: bool,
) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    for idx in range(question_count):
        entry = selected_entries[idx % len(selected_entries)]
        examples = list(getattr(entry, "example_queries", []) or [])
        if examples:
            question = str(examples[idx % len(examples)]).strip()
        else:
            tool_name = str(getattr(entry, "name", getattr(entry, "tool_id", "verktyg")))
            description = str(getattr(entry, "description", "")).strip()
            if description:
                question = f"Hjälp mig med: {description[:120]}"
            else:
                question = f"När ska verktyget {tool_name} användas?"
        tool_id = str(getattr(entry, "tool_id", "")).strip()
        tests.append(
            {
                "id": f"case-{idx + 1}",
                "question": question,
                "expected": {
                    "tool": tool_id,
                    "category": str(getattr(entry, "category", "")).strip(),
                },
                "allowed_tools": [tool_id] if include_allowed_tools else [],
            }
        )
    return tests


def _build_eval_library_payload(
    *,
    eval_name: str | None,
    target_success_rate: float | None,
    tests: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "eval_name": eval_name,
        "target_success_rate": target_success_rate,
        "tests": tests,
    }


def _resolve_eval_library_file(relative_path: str) -> Path:
    root = _EVAL_LIBRARY_ROOT.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid eval library path")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Eval library file not found")
    if candidate.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Only JSON eval files are supported")
    return candidate


def _save_eval_library_payload(
    *,
    payload: dict[str, Any],
    mode: str,
    provider_key: str | None,
    category_id: str | None,
    eval_name: str | None,
) -> tuple[str, str, int, str]:
    root = _EVAL_LIBRARY_ROOT
    root.mkdir(parents=True, exist_ok=True)

    provider_slug = _slugify(provider_key or ("global" if mode == "global_random" else "custom"))
    category_slug = _slugify(category_id or ("mixed" if mode == "global_random" else "general"))
    target_dir = root / provider_slug / category_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    base_name = _slugify(eval_name or f"{provider_slug}_{category_slug}", fallback="eval")
    date_part = datetime.now(UTC).strftime("%Y%m%d")
    version_pattern = re.compile(rf"^{re.escape(base_name)}_{date_part}_v(\d+)\.json$")
    versions: list[int] = []
    for item in target_dir.glob(f"{base_name}_{date_part}_v*.json"):
        match = version_pattern.match(item.name)
        if match:
            versions.append(int(match.group(1)))
    version = (max(versions) if versions else 0) + 1
    file_name = f"{base_name}_{date_part}_v{version}.json"
    file_path = target_dir / file_name
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    file_path.write_text(serialized, encoding="utf-8")
    relative_path = file_path.relative_to(root).as_posix()
    return relative_path, file_name, version, _utcnow_iso()


async def _generate_eval_tests(
    *,
    llm,
    selected_entries: list[Any],
    question_count: int,
    include_allowed_tools: bool,
) -> list[dict[str, Any]]:
    fallback_tests = _build_fallback_generated_tests(
        selected_entries=selected_entries,
        question_count=question_count,
        include_allowed_tools=include_allowed_tools,
    )
    if llm is None:
        return fallback_tests
    prompt = (
        "Generate evaluation tests for tool routing.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "tests": [\n'
        "    {\n"
        '      "id": "case-1",\n'
        '      "question": "string",\n'
        '      "expected": {"tool": "tool_id", "category": "category"},\n'
        '      "allowed_tools": ["tool_id"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Generate exactly the requested number of tests.\n"
        "- Use only provided tool_ids.\n"
        "- Cover different intents and at least one harder/confusable case.\n"
        "- Keep questions in Swedish.\n"
        "- Do not include markdown."
    )
    candidate_tools = [
        {
            "tool_id": str(entry.tool_id),
            "name": str(entry.name),
            "category": str(entry.category),
            "description": str(entry.description or ""),
            "keywords": list(entry.keywords or []),
            "example_queries": list(entry.example_queries or []),
        }
        for entry in selected_entries[:40]
    ]
    payload = {
        "question_count": question_count,
        "candidate_tools": candidate_tools,
    }
    model = llm
    try:
        if hasattr(llm, "bind"):
            model = llm.bind(temperature=0.2)
    except Exception:
        model = llm
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
            ]
        )
        raw_content = getattr(response, "content", "")
        if isinstance(raw_content, list):
            parts: list[str] = []
            for item in raw_content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            raw_text = "".join(parts)
        else:
            raw_text = str(raw_content or "")
        parsed = _extract_json_object(raw_text)
        generated_tests = parsed.get("tests") if isinstance(parsed, dict) else None
        if not isinstance(generated_tests, list):
            return fallback_tests
        normalized = _normalize_generated_tests(
            tests=[item for item in generated_tests if isinstance(item, dict)],
            selected_entries=selected_entries,
            question_count=question_count,
            include_allowed_tools=include_allowed_tools,
        )
        return normalized or fallback_tests
    except Exception:
        return fallback_tests


def _select_generation_entries(
    *,
    tool_index: list[Any],
    mode: str,
    provider_key: str | None,
    category_id: str | None,
    question_count: int,
) -> list[Any]:
    provider_filter = str(provider_key or "").strip().lower()
    category_filter = str(category_id or "").strip()
    candidates = [entry for entry in tool_index if _is_eval_candidate_entry(entry)]

    if provider_filter and provider_filter != "all":
        candidates = [
            entry
            for entry in candidates
            if _provider_for_tool_id(str(entry.tool_id)) == provider_filter
        ]

    if mode == "category":
        if not category_filter:
            raise HTTPException(
                status_code=400,
                detail="category_id is required when mode=category",
            )
        api_categories = _build_tool_api_categories_response().get("providers") or []
        selected_tool_ids: set[str] = set()
        for provider in api_categories:
            provider_id = str(provider.get("provider_key") or "").strip().lower()
            if provider_filter and provider_filter != "all" and provider_id != provider_filter:
                continue
            for item in provider.get("categories") or []:
                if str(item.get("category_id") or "").strip() == category_filter:
                    tool_id = str(item.get("tool_id") or "").strip()
                    if tool_id:
                        selected_tool_ids.add(tool_id)
        pool = [entry for entry in candidates if str(entry.tool_id) in selected_tool_ids]
        if not pool:
            pool = [
                entry
                for entry in candidates
                if str(getattr(entry, "category", "")).strip() == category_filter
            ]
        if not pool:
            raise HTTPException(
                status_code=404,
                detail="No tools found for selected API category",
            )
        return pool

    by_category: dict[str, list[Any]] = {}
    for entry in candidates:
        category = str(getattr(entry, "category", "") or "general").strip() or "general"
        by_category.setdefault(category, []).append(entry)
    categories = list(by_category.keys())
    random.shuffle(categories)
    selected: list[Any] = []
    for category in categories:
        bucket = list(by_category.get(category) or [])
        random.shuffle(bucket)
        if bucket:
            selected.append(bucket[0])
        if len(selected) >= question_count:
            break
    if len(selected) < question_count:
        remaining = [entry for entry in candidates if entry not in selected]
        random.shuffle(remaining)
        needed = question_count - len(selected)
        selected.extend(remaining[:needed])
    return selected or candidates


def _list_eval_library_files(
    *,
    provider_key: str | None = None,
    category_id: str | None = None,
) -> list[dict[str, Any]]:
    root = _EVAL_LIBRARY_ROOT
    if not root.exists():
        return []
    provider_filter = _slugify(provider_key, fallback="").strip("_") if provider_key else ""
    category_filter = _slugify(category_id, fallback="").strip("_") if category_id else ""
    items: list[dict[str, Any]] = []
    for path in root.rglob("*.json"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        parts = rel.split("/")
        provider = parts[0] if len(parts) >= 2 else None
        category = parts[1] if len(parts) >= 3 else None
        if provider_filter and provider != provider_filter:
            continue
        if category_filter and category != category_filter:
            continue
        test_count: int | None = None
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict) and isinstance(parsed.get("tests"), list):
                test_count = len(parsed["tests"])
        except Exception:
            test_count = None
        stat = path.stat()
        created_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        items.append(
            {
                "relative_path": rel,
                "file_name": path.name,
                "provider_key": provider,
                "category_id": category,
                "created_at": created_at,
                "size_bytes": int(stat.st_size),
                "test_count": test_count,
            }
        )
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items


async def _prune_eval_jobs() -> None:
    if len(_EVAL_JOBS) <= _MAX_EVAL_JOBS:
        return
    finished = [
        (job_id, payload)
        for job_id, payload in _EVAL_JOBS.items()
        if payload.get("status") in {"completed", "failed"}
    ]
    finished.sort(key=lambda item: str(item[1].get("updated_at") or ""))
    overflow = len(_EVAL_JOBS) - _MAX_EVAL_JOBS
    for job_id, _payload in finished[: max(0, overflow)]:
        _EVAL_JOBS.pop(job_id, None)


async def _update_eval_job(job_id: str, **updates: Any) -> None:
    async with _EVAL_JOBS_LOCK:
        job = _EVAL_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = _utcnow_iso()


def _serialize_eval_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "total_tests": int(job.get("total_tests", 0)),
        "completed_tests": int(job.get("completed_tests", 0)),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "updated_at": job.get("updated_at") or _utcnow_iso(),
        "case_statuses": job.get("case_statuses") or [],
        "result": job.get("result"),
        "error": job.get("error"),
    }


def _build_eval_summary_payload(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    total_tests = int(metrics.get("total_tests") or 0)
    passed_tests = int(metrics.get("passed_tests") or 0)
    success_rate = float(metrics.get("success_rate") or 0.0)
    return {
        "run_at": _utcnow_iso(),
        "eval_name": result.get("eval_name"),
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "success_rate": success_rate,
    }


async def _record_latest_eval_summary(
    session: AsyncSession,
    *,
    search_space_id: int,
    result: dict[str, Any],
    updated_by_id: Any | None = None,
) -> None:
    summary = _build_eval_summary_payload(result)
    row = GlobalToolEvaluationRun(
        search_space_id=search_space_id,
        eval_name=summary.get("eval_name"),
        total_tests=int(summary.get("total_tests") or 0),
        passed_tests=int(summary.get("passed_tests") or 0),
        success_rate=float(summary.get("success_rate") or 0.0),
        updated_by_id=updated_by_id,
    )
    try:
        session.add(row)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("Failed to persist latest tool evaluation summary")


async def _get_latest_eval_summary(
    session: AsyncSession,
    *,
    search_space_id: int,
) -> dict[str, Any] | None:
    result = await session.execute(
        select(GlobalToolEvaluationRun)
        .filter(GlobalToolEvaluationRun.search_space_id == search_space_id)
        .order_by(GlobalToolEvaluationRun.created_at.desc())
        .limit(1)
    )
    latest = result.scalars().first()
    if latest is None:
        return None
    return {
        "run_at": latest.created_at.isoformat(),
        "eval_name": latest.eval_name,
        "total_tests": int(latest.total_tests or 0),
        "passed_tests": int(latest.passed_tests or 0),
        "success_rate": float(latest.success_rate or 0.0),
    }


def _metadata_payload_from_item(item: ToolMetadataUpdateItem) -> dict[str, Any]:
    return normalize_tool_metadata_payload(
        {
            "name": item.name,
            "description": item.description,
            "keywords": item.keywords,
            "example_queries": item.example_queries,
            "category": item.category,
            "base_path": item.base_path,
        }
    )


def _metadata_payload_from_entry(entry) -> dict[str, Any]:
    return normalize_tool_metadata_payload(
        {
            "name": entry.name,
            "description": entry.description,
            "keywords": list(entry.keywords),
            "example_queries": list(entry.example_queries),
            "category": entry.category,
            "base_path": entry.base_path,
        }
    )


def _tool_item_from_entry(entry, *, has_override: bool) -> ToolMetadataItem:
    return ToolMetadataItem(
        tool_id=entry.tool_id,
        name=entry.name,
        description=entry.description,
        keywords=list(entry.keywords),
        example_queries=list(entry.example_queries),
        category=entry.category,
        base_path=entry.base_path,
        has_override=has_override,
    )


def _group_tool_index_by_category(
    tool_index: list[Any],
    *,
    persisted_overrides: dict[str, dict[str, Any]],
) -> list[ToolCategoryResponse]:
    grouped: dict[str, list[ToolMetadataItem]] = {}
    for entry in tool_index:
        category_id = entry.category or "general"
        grouped.setdefault(category_id, []).append(
            _tool_item_from_entry(
                entry,
                has_override=entry.tool_id in persisted_overrides,
            )
        )
    categories: list[ToolCategoryResponse] = []
    for category_id in sorted(grouped.keys()):
        tools = sorted(grouped[category_id], key=lambda tool: tool.name.lower())
        categories.append(
            ToolCategoryResponse(
                category_id=category_id,
                category_name=_category_name(category_id),
                tools=tools,
            )
        )
    return categories


def _patch_map_from_updates(
    updates: list[ToolMetadataUpdateItem],
) -> dict[str, dict[str, Any]]:
    patch_map: dict[str, dict[str, Any]] = {}
    for item in updates:
        patch_map[item.tool_id] = _metadata_payload_from_item(item)
    return patch_map


async def _resolve_search_space_id(
    session: AsyncSession,
    user: User,
    *,
    requested_search_space_id: int | None,
) -> tuple[list[int], int]:
    owned_search_space_ids = await _require_admin(session, user)
    if requested_search_space_id is not None:
        if requested_search_space_id not in owned_search_space_ids:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to use this search space for admin eval",
            )
        return owned_search_space_ids, requested_search_space_id
    return owned_search_space_ids, owned_search_space_ids[0]


async def _build_tool_index_for_search_space(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
    metadata_patch: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    connector_service = ConnectorService(
        session,
        search_space_id=search_space_id,
        user_id=str(user.id),
    )
    dependencies = {
        "search_space_id": search_space_id,
        "db_session": session,
        "connector_service": connector_service,
        "user_id": str(user.id),
        "thread_id": 0,
    }
    tool_registry = await build_global_tool_registry(
        dependencies=dependencies,
        include_mcp_tools=False,
    )
    persisted_overrides = await get_global_tool_metadata_overrides(session)
    effective_overrides = merge_tool_metadata_overrides(
        persisted_overrides,
        metadata_patch,
    )
    tool_index = build_tool_index(
        tool_registry,
        metadata_overrides=effective_overrides,
    )
    return tool_index, persisted_overrides, effective_overrides


async def _build_tool_settings_response(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
) -> ToolSettingsResponse:
    tool_index, persisted_overrides, _effective_overrides = (
        await _build_tool_index_for_search_space(
            session,
            user,
            search_space_id=search_space_id,
            metadata_patch=None,
        )
    )
    categories = _group_tool_index_by_category(
        tool_index,
        persisted_overrides=persisted_overrides,
    )
    retrieval_tuning = await get_global_tool_retrieval_tuning(session)
    latest_evaluation = await _get_latest_eval_summary(
        session,
        search_space_id=search_space_id,
    )
    return ToolSettingsResponse(
        categories=categories,
        retrieval_tuning=ToolRetrievalTuning(**retrieval_tuning),
        latest_evaluation=latest_evaluation,
        metadata_version_hash=compute_metadata_version_hash(tool_index),
        search_space_id=search_space_id,
    )


async def _execute_tool_evaluation(
    session: AsyncSession,
    user: User,
    *,
    payload: ToolEvaluationRequest,
    resolved_search_space_id: int,
    progress_callback=None,
) -> dict[str, Any]:
    patch_map = _patch_map_from_updates(payload.metadata_patch)
    tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_index_for_search_space(
            session,
            user,
            search_space_id=resolved_search_space_id,
            metadata_patch=patch_map,
        )
    )
    persisted_tuning = await get_global_tool_retrieval_tuning(session)
    effective_tuning = (
        normalize_tool_retrieval_tuning(payload.retrieval_tuning_override.model_dump())
        if payload.retrieval_tuning_override
        else persisted_tuning
    )
    llm = await get_agent_llm(session, resolved_search_space_id)
    evaluation = await run_tool_evaluation(
        tests=[
            {
                "id": test.id,
                "question": test.question,
                "expected": {
                    "tool": test.expected.tool if test.expected else None,
                    "category": test.expected.category if test.expected else None,
                },
                "allowed_tools": list(test.allowed_tools),
            }
            for test in payload.tests
        ],
        tool_index=tool_index,
        llm=llm,
        retrieval_limit=payload.retrieval_limit,
        retrieval_tuning=effective_tuning,
        progress_callback=progress_callback,
    )
    suggestions = await generate_tool_metadata_suggestions(
        evaluation_results=evaluation["results"],
        tool_index=tool_index,
        llm=llm,
    )
    retrieval_tuning_suggestion = await suggest_retrieval_tuning(
        evaluation_results=evaluation["results"],
        current_tuning=effective_tuning,
        llm=llm,
    )
    return {
        "eval_name": payload.eval_name,
        "target_success_rate": payload.target_success_rate,
        "metrics": evaluation["metrics"],
        "results": evaluation["results"],
        "suggestions": suggestions,
        "retrieval_tuning": effective_tuning,
        "retrieval_tuning_suggestion": retrieval_tuning_suggestion,
        "metadata_version_hash": compute_metadata_version_hash(tool_index),
        "search_space_id": resolved_search_space_id,
    }


async def _apply_tool_metadata_updates(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
    updates: list[ToolMetadataUpdateItem],
) -> ToolSettingsResponse:
    connector_service = ConnectorService(
        session,
        search_space_id=search_space_id,
        user_id=str(user.id),
    )
    dependencies = {
        "search_space_id": search_space_id,
        "db_session": session,
        "connector_service": connector_service,
        "user_id": str(user.id),
        "thread_id": 0,
    }
    tool_registry = await build_global_tool_registry(
        dependencies=dependencies,
        include_mcp_tools=False,
    )
    default_tool_index = build_tool_index(tool_registry)
    defaults_by_tool = {entry.tool_id: _metadata_payload_from_entry(entry) for entry in default_tool_index}
    update_rows: list[tuple[str, dict[str, Any] | None]] = []
    for item in updates:
        if item.tool_id not in defaults_by_tool:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown tool_id in payload: {item.tool_id}",
            )
        normalized_payload = _metadata_payload_from_item(item)
        default_payload = defaults_by_tool[item.tool_id]
        override_payload = (
            None
            if tool_metadata_payload_equal(normalized_payload, default_payload)
            else normalized_payload
        )
        update_rows.append((item.tool_id, override_payload))
    try:
        await upsert_global_tool_metadata_overrides(
            session,
            update_rows,
            updated_by_id=user.id,
        )
        await session.commit()
        clear_tool_caches()
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to update tool metadata")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update tool metadata: {exc!s}",
        ) from exc
    return await _build_tool_settings_response(
        session,
        user,
        search_space_id=search_space_id,
    )


@router.get(
    "/tool-settings",
    response_model=ToolSettingsResponse,
)
async def get_tool_settings(
    search_space_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get effective tool metadata organized by category."""
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=search_space_id,
    )
    return await _build_tool_settings_response(
        session,
        user,
        search_space_id=resolved_search_space_id,
    )


@router.get(
    "/tool-settings/api-categories",
    response_model=ToolApiCategoriesResponse,
)
async def get_tool_api_categories(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Return available SCB and Riksdagen API category lists for admin UI."""
    await _require_admin(session, user)
    return _build_tool_api_categories_response()


@router.get(
    "/tool-settings/eval-library/files",
    response_model=ToolEvalLibraryListResponse,
)
async def list_eval_library_files(
    provider_key: str | None = None,
    category_id: str | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    return {
        "items": _list_eval_library_files(
            provider_key=provider_key,
            category_id=category_id,
        )
    }


@router.get(
    "/tool-settings/eval-library/file",
    response_model=ToolEvalLibraryFileResponse,
)
async def read_eval_library_file(
    relative_path: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    path = _resolve_eval_library_file(relative_path)
    content = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(content)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Eval library file is not valid JSON: {exc!s}",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="Eval library JSON must be an object")
    return {
        "relative_path": relative_path,
        "content": content,
        "payload": payload,
    }


@router.post(
    "/tool-settings/eval-library/generate",
    response_model=ToolEvalLibraryGenerateResponse,
)
async def generate_eval_library_file(
    payload: ToolEvalLibraryGenerateRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=payload.search_space_id,
    )
    normalized_mode = str(payload.mode or "category").strip().lower()
    if normalized_mode in {"random", "global", "global_mix"}:
        normalized_mode = "global_random"
    if normalized_mode not in {"category", "global_random"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be either 'category' or 'global_random'",
        )
    question_count = max(1, min(int(payload.question_count or 12), 100))
    tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_index_for_search_space(
            session,
            user,
            search_space_id=resolved_search_space_id,
            metadata_patch=None,
        )
    )
    pool = _select_generation_entries(
        tool_index=tool_index,
        mode=normalized_mode,
        provider_key=payload.provider_key,
        category_id=payload.category_id,
        question_count=question_count,
    )
    if not pool:
        raise HTTPException(status_code=404, detail="No tools available for eval generation")
    random.shuffle(pool)
    selected_entries = pool[: max(question_count, min(len(pool), 30))]
    llm = await get_agent_llm(session, resolved_search_space_id)
    tests = await _generate_eval_tests(
        llm=llm,
        selected_entries=selected_entries,
        question_count=question_count,
        include_allowed_tools=bool(payload.include_allowed_tools),
    )
    if not tests:
        raise HTTPException(status_code=500, detail="Could not generate eval tests")
    default_eval_name = (
        f"{payload.provider_key or 'global'}-{payload.category_id or normalized_mode}"
    )
    eval_name = str(payload.eval_name or default_eval_name)
    eval_payload = _build_eval_library_payload(
        eval_name=eval_name,
        target_success_rate=payload.target_success_rate,
        tests=tests,
    )
    relative_path, file_name, version, created_at = _save_eval_library_payload(
        payload=eval_payload,
        mode=normalized_mode,
        provider_key=payload.provider_key,
        category_id=payload.category_id,
        eval_name=eval_name,
    )
    return {
        "relative_path": relative_path,
        "file_name": file_name,
        "version": version,
        "created_at": created_at,
        "payload": eval_payload,
    }


@router.put(
    "/tool-settings",
    response_model=ToolSettingsResponse,
)
async def update_tool_settings(
    payload: ToolSettingsUpdateRequest,
    search_space_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Persist tool metadata overrides."""
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=search_space_id,
    )
    return await _apply_tool_metadata_updates(
        session,
        user,
        search_space_id=resolved_search_space_id,
        updates=payload.tools,
    )


@router.get(
    "/tool-settings/retrieval-tuning",
    response_model=ToolRetrievalTuningResponse,
)
async def get_tool_retrieval_tuning(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    tuning = await get_global_tool_retrieval_tuning(session)
    return {"tuning": tuning}


@router.put(
    "/tool-settings/retrieval-tuning",
    response_model=ToolRetrievalTuningResponse,
)
async def update_tool_retrieval_tuning(
    payload: ToolRetrievalTuning,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    normalized = normalize_tool_retrieval_tuning(payload.model_dump())
    try:
        await upsert_global_tool_retrieval_tuning(
            session,
            normalized,
            updated_by_id=user.id,
        )
        await session.commit()
        clear_tool_caches()
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to update retrieval tuning")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update retrieval tuning: {exc!s}",
        ) from exc
    return {"tuning": normalized}


@router.get(
    "/tool-settings/history/{tool_id}",
    response_model=ToolMetadataHistoryResponse,
)
async def get_tool_settings_history(
    tool_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    result = await session.execute(
        select(GlobalToolMetadataOverrideHistory)
        .filter(GlobalToolMetadataOverrideHistory.tool_id == tool_id)
        .order_by(GlobalToolMetadataOverrideHistory.created_at.desc())
        .limit(50)
    )
    items = []
    for row in result.scalars().all():
        items.append(
            {
                "tool_id": row.tool_id,
                "previous_payload": row.previous_payload,
                "new_payload": row.new_payload,
                "updated_at": row.created_at.isoformat(),
                "updated_by_id": str(row.updated_by_id) if row.updated_by_id else None,
            }
        )
    return {"items": items}


@router.post(
    "/tool-settings/evaluate",
    response_model=ToolEvaluationResponse,
)
async def evaluate_tool_settings(
    payload: ToolEvaluationRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    if not payload.tests:
        raise HTTPException(
            status_code=400,
            detail="Evaluation payload must include at least one test case",
        )
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=payload.search_space_id,
    )
    result = await _execute_tool_evaluation(
        session,
        user,
        payload=payload,
        resolved_search_space_id=resolved_search_space_id,
    )
    await _record_latest_eval_summary(
        session,
        search_space_id=resolved_search_space_id,
        result=result,
        updated_by_id=user.id,
    )
    return result


async def _run_eval_job_background(
    *,
    job_id: str,
    payload_data: dict[str, Any],
    user_id: Any,
) -> None:
    await _update_eval_job(
        job_id,
        status="running",
        started_at=_utcnow_iso(),
        error=None,
    )
    try:
        async with async_session_maker() as job_session:
            payload = ToolEvaluationRequest(**payload_data)
            user_result = await job_session.execute(select(User).filter(User.id == user_id))
            job_user = user_result.scalars().first()
            if job_user is None:
                raise RuntimeError("Evaluation user context could not be loaded")
            _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
                job_session,
                job_user,
                requested_search_space_id=payload.search_space_id,
            )

            async def _progress_callback(event: dict[str, Any]) -> None:
                test_id = str(event.get("test_id") or "")
                event_type = str(event.get("type") or "")
                async with _EVAL_JOBS_LOCK:
                    job = _EVAL_JOBS.get(job_id)
                    if not job:
                        return
                    case_statuses = job.get("case_statuses") or []
                    for case in case_statuses:
                        if case.get("test_id") != test_id:
                            continue
                        if event_type == "test_started":
                            case["status"] = "running"
                            case["error"] = None
                        elif event_type == "test_completed":
                            case["status"] = "completed"
                            case["selected_tool"] = event.get("selected_tool")
                            case["selected_category"] = event.get("selected_category")
                            case["passed"] = event.get("passed")
                        elif event_type == "test_failed":
                            case["status"] = "failed"
                            case["error"] = str(event.get("error") or "Unknown error")
                        break
                    job["completed_tests"] = sum(
                        1
                        for case in case_statuses
                        if case.get("status") in {"completed", "failed"}
                    )
                    job["updated_at"] = _utcnow_iso()

            result = await _execute_tool_evaluation(
                job_session,
                job_user,
                payload=payload,
                resolved_search_space_id=resolved_search_space_id,
                progress_callback=_progress_callback,
            )
            await _record_latest_eval_summary(
                job_session,
                search_space_id=resolved_search_space_id,
                result=result,
                updated_by_id=job_user.id,
            )
            await _update_eval_job(
                job_id,
                status="completed",
                completed_at=_utcnow_iso(),
                completed_tests=len(payload.tests),
                result=result,
            )
    except Exception as exc:
        logger.exception("Tool evaluation job failed")
        await _update_eval_job(
            job_id,
            status="failed",
            completed_at=_utcnow_iso(),
            error=str(exc),
        )


@router.post(
    "/tool-settings/evaluate/start",
    response_model=ToolEvaluationStartResponse,
)
async def start_tool_settings_evaluation(
    payload: ToolEvaluationRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    if not payload.tests:
        raise HTTPException(
            status_code=400,
            detail="Evaluation payload must include at least one test case",
        )
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=payload.search_space_id,
    )
    normalized_payload = payload.model_copy(
        update={"search_space_id": resolved_search_space_id}
    )
    case_statuses = [
        ToolEvaluationCaseStatus(
            test_id=test.id,
            question=test.question,
            status="pending",
        ).model_dump()
        for test in normalized_payload.tests
    ]
    job_id = uuid4().hex
    job_payload = {
        "job_id": job_id,
        "status": "pending",
        "total_tests": len(normalized_payload.tests),
        "completed_tests": 0,
        "started_at": None,
        "completed_at": None,
        "updated_at": _utcnow_iso(),
        "created_at": _utcnow_iso(),
        "case_statuses": case_statuses,
        "result": None,
        "error": None,
    }
    async with _EVAL_JOBS_LOCK:
        _EVAL_JOBS[job_id] = job_payload
        await _prune_eval_jobs()
    asyncio.create_task(
        _run_eval_job_background(
            job_id=job_id,
            payload_data=normalized_payload.model_dump(),
            user_id=user.id,
        )
    )
    return {
        "job_id": job_id,
        "status": "pending",
        "total_tests": len(normalized_payload.tests),
    }


@router.get(
    "/tool-settings/evaluate/{job_id}",
    response_model=ToolEvaluationJobStatusResponse,
)
async def get_tool_settings_evaluation_status(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    async with _EVAL_JOBS_LOCK:
        job = _EVAL_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Evaluation job not found")
        return _serialize_eval_job(job)


@router.post(
    "/tool-settings/suggestions",
    response_model=ToolSuggestionResponse,
)
async def generate_tool_suggestions(
    payload: ToolSuggestionRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=payload.search_space_id,
    )
    patch_map = _patch_map_from_updates(payload.metadata_patch)
    tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_index_for_search_space(
            session,
            user,
            search_space_id=resolved_search_space_id,
            metadata_patch=patch_map,
        )
    )
    llm = await get_agent_llm(session, resolved_search_space_id)
    failed_case_dicts = [
        {
            "test_id": case.test_id,
            "question": case.question,
            "expected_tool": case.expected_tool,
            "expected_category": case.expected_category,
            "selected_tool": case.selected_tool,
            "selected_category": case.selected_category,
            "passed_tool": case.passed_tool,
            "passed_category": case.passed_category,
            "passed": case.passed,
        }
        for case in payload.failed_cases
    ]
    suggestions = await generate_tool_metadata_suggestions(
        evaluation_results=failed_case_dicts,
        tool_index=tool_index,
        llm=llm,
    )
    return {"suggestions": suggestions}


@router.post(
    "/tool-settings/apply-suggestions",
    response_model=ToolApplySuggestionsResponse,
)
async def apply_tool_suggestions(
    payload: ToolApplySuggestionsRequest,
    search_space_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=search_space_id,
    )
    updates: list[ToolMetadataUpdateItem] = []
    for suggestion in payload.suggestions:
        if suggestion.proposed_metadata.tool_id != suggestion.tool_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Suggestion payload mismatch: proposed_metadata.tool_id must "
                    "match suggestion.tool_id"
                ),
            )
        updates.append(suggestion.proposed_metadata)
    settings = await _apply_tool_metadata_updates(
        session,
        user,
        search_space_id=resolved_search_space_id,
        updates=updates,
    )
    return {
        "applied_tool_ids": [update.tool_id for update in updates],
        "settings": settings,
    }
