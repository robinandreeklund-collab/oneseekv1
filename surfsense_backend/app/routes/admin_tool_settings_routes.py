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
    GlobalToolEvaluationStageRun,
    GlobalToolEvaluationRun,
    GlobalToolMetadataOverrideHistory,
    SearchSpaceMembership,
    User,
    async_session_maker,
    get_async_session,
)
from app.schemas.admin_tool_settings import (
    ToolAutoLoopJobStatusResponse,
    ToolAutoLoopRequest,
    ToolAutoLoopResult,
    ToolAutoLoopStartResponse,
    ToolApiInputApplyPromptSuggestionsRequest,
    ToolApiInputApplyPromptSuggestionsResponse,
    ToolApiInputEvaluationJobStatusResponse,
    ToolApiInputEvaluationRequest,
    ToolApiInputEvaluationResponse,
    ToolApiInputEvaluationStartResponse,
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
    ToolEvaluationMetricDeltaItem,
    ToolEvaluationStageHistoryResponse,
    ToolEvaluationTestCase,
    ToolEvaluationRunComparison,
    ToolEvaluationRequest,
    ToolEvaluationResponse,
    ToolEvaluationStartResponse,
    ToolMetadataHistoryResponse,
    ToolMetadataItem,
    ToolMetadataUpdateItem,
    ToolRetrievalTuning,
    ToolRetrievalTuningResponse,
    ToolAutoLoopIterationSummary,
    ToolAutoLoopDraftPromptItem,
    ToolSettingsUpdateRequest,
    ToolSuggestionRequest,
    ToolSuggestionResponse,
    ToolSettingsResponse,
)
from app.agents.new_chat.prompt_registry import (
    PROMPT_DEFINITION_MAP,
    resolve_prompt,
)
from app.services.agent_prompt_service import (
    get_global_prompt_overrides,
    upsert_global_prompt_overrides,
)
from app.services.connector_service import ConnectorService
from app.services.llm_service import get_agent_llm
from app.services.tool_evaluation_service import (
    compute_metadata_version_hash,
    generate_tool_metadata_suggestions,
    run_tool_api_input_evaluation,
    run_tool_evaluation,
    suggest_agent_prompt_improvements_for_api_input,
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
_API_INPUT_EVAL_JOBS: dict[str, dict[str, Any]] = {}
_API_INPUT_EVAL_JOBS_LOCK = asyncio.Lock()
_MAX_API_INPUT_EVAL_JOBS = 100
_AUTO_LOOP_JOBS: dict[str, dict[str, Any]] = {}
_AUTO_LOOP_JOBS_LOCK = asyncio.Lock()
_MAX_AUTO_LOOP_JOBS = 60
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
_SWEDISH_CITIES = [
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
    "Sundsvall",
    "Luleå",
]
_SWEDISH_REGIONS = [
    "Stockholms län",
    "Västra Götalands län",
    "Skåne län",
    "Uppsala län",
    "Örebro län",
    "Östergötlands län",
    "Västerbottens län",
    "Norrbottens län",
]
_SWEDISH_ROADS = [
    "E4",
    "E6",
    "E18",
    "E20",
    "E22",
    "Riksväg 40",
    "Riksväg 50",
    "Riksväg 73",
    "Södra länken",
    "Norra länken",
]
_SWEDISH_POLITICS_TOPICS = [
    "arbetslöshet",
    "inflation",
    "bostadsbyggande",
    "kollektivtrafik",
    "sjukvård",
    "skola",
    "energi",
    "klimatpolitik",
]
_NON_SWEDISH_MARKERS = (
    "what",
    "how",
    "where",
    "when",
    "which",
    "show me",
    "give me",
    "tell me",
    "please",
    "could you",
    "can you",
)
_SWEDEN_CONTEXT_MARKERS = (
    "sverige",
    "svensk",
    "riksdag",
    "scb",
    "kommun",
    "län",
    "stad",
    "trafikverket",
    "smhi",
    "e4",
    "e6",
    "e18",
    "e20",
)
_SWEDISH_DIACRITIC_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bgoteborg\b", "Göteborg"),
    (r"\bmalmo\b", "Malmö"),
    (r"\bvasteras\b", "Västerås"),
    (r"\blinkoping\b", "Linköping"),
    (r"\bjonkoping\b", "Jönköping"),
    (r"\bnorrkoping\b", "Norrköping"),
    (r"\bumea\b", "Umeå"),
    (r"\bgavle\b", "Gävle"),
    (r"\bvader\b", "väder"),
    (r"\bvag(ar|en|s)?\b", r"väg\1"),
    (r"\blan(et|s)?\b", r"län\1"),
    (r"\bfraga(n|r|s)?\b", r"fråga\1"),
]
_DIFFICULTY_LABELS = ("lätt", "medel", "svår")


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _restore_swedish_diacritics(text: str) -> str:
    restored = str(text or "")
    for pattern, replacement in _SWEDISH_DIACRITIC_REPLACEMENTS:
        restored = re.sub(pattern, replacement, restored, flags=re.IGNORECASE)
    return restored


def _normalize_difficulty_label(value: Any) -> str | None:
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


def _normalize_difficulty_profile(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    if lowered in {"blandad", "mix", "mixed", ""}:
        return "blandad"
    normalized = _normalize_difficulty_label(lowered)
    if normalized:
        return normalized
    return "blandad"


def _difficulty_for_index(index: int, profile: str) -> str:
    normalized = _normalize_difficulty_profile(profile)
    if normalized in _DIFFICULTY_LABELS:
        return normalized
    return _DIFFICULTY_LABELS[index % len(_DIFFICULTY_LABELS)]


def _difficulty_instructions_for_profile(profile: str) -> str:
    normalized = _normalize_difficulty_profile(profile)
    if normalized == "lätt":
        return (
            "- Alla frågor ska ha difficulty='lätt'.\n"
            "- Lätt: tydlig intent, ett verktyg är uppenbart, få villkor."
        )
    if normalized == "medel":
        return (
            "- Alla frågor ska ha difficulty='medel'.\n"
            "- Medel: 2-3 villkor (t.ex. plats + tid), men fortfarande tydlig intent."
        )
    if normalized == "svår":
        return (
            "- Alla frågor ska ha difficulty='svår'.\n"
            "- Svår: fler begränsningar, potentiellt förväxlingsbar fråga eller indirekt formulering."
        )
    return (
        "- Använd blandad svårighetsgrad och sätt difficulty per test till 'lätt', 'medel' eller 'svår'.\n"
        "- Försök få jämn fördelning mellan nivåerna."
    )


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
    normalized = str(category_id or "").strip().lower()
    aliases = {
        "weather": "Väder",
        "trafikverket_vader": "Väder",
    }
    if normalized in aliases:
        return aliases[normalized]
    cleaned = (category_id or "general").replace("_", " ").replace("/", " / ")
    words = [word.capitalize() for word in cleaned.split()]
    return " ".join(words) or "General"


def _build_tool_api_categories_response(
    *,
    tool_index: list[Any] | None = None,
) -> dict[str, Any]:
    providers_by_key: dict[str, dict[str, Any]] = {}
    seen_tool_ids: dict[str, set[str]] = {}

    def _ensure_provider(provider_key: str, provider_name: str | None = None) -> None:
        key = str(provider_key or "other").strip().lower() or "other"
        if key not in providers_by_key:
            providers_by_key[key] = {
                "provider_key": key,
                "provider_name": provider_name or _provider_display_name(key),
                "categories": [],
            }
        seen_tool_ids.setdefault(key, set())

    def _append_item(provider_key: str, item: dict[str, Any]) -> None:
        key = str(provider_key or "other").strip().lower() or "other"
        _ensure_provider(key)
        tool_id = str(item.get("tool_id") or "").strip()
        if not tool_id:
            return
        if tool_id in seen_tool_ids[key]:
            return
        seen_tool_ids[key].add(tool_id)
        providers_by_key[key]["categories"].append(item)

    try:
        from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS

        _ensure_provider("scb", "SCB")
        for definition in SCB_TOOL_DEFINITIONS:
            base_path = str(definition.base_path or "").strip()
            top_level = base_path.endswith("/") and base_path.count("/") == 1
            category_id = base_path.split("/", 1)[0] if base_path else definition.tool_id
            category_name = str(definition.name or "").replace("SCB ", "").strip()
            _append_item(
                "scb",
                {
                    "tool_id": definition.tool_id,
                    "tool_name": definition.name,
                    "category_id": category_id,
                    "category_name": category_name,
                    "level": "top_level" if top_level else "subcategory",
                    "description": definition.description,
                    "base_path": definition.base_path,
                },
            )
    except Exception:
        logger.exception("Failed to load SCB API categories")

    try:
        from app.agents.new_chat.riksdagen_agent import (
            RIKSDAGEN_TOOL_DEFINITIONS,
            RIKSDAGEN_TOP_LEVEL_TOOLS,
        )

        _ensure_provider("riksdagen", "Riksdagen")
        top_level_ids = {definition.tool_id for definition in RIKSDAGEN_TOP_LEVEL_TOOLS}
        for definition in RIKSDAGEN_TOOL_DEFINITIONS:
            level = "top_level" if definition.tool_id in top_level_ids else "subcategory"
            category_id = str(definition.category or "riksdagen").strip()
            _append_item(
                "riksdagen",
                {
                    "tool_id": definition.tool_id,
                    "tool_name": definition.name,
                    "category_id": category_id,
                    "category_name": _category_name(category_id),
                    "level": level,
                    "description": definition.description,
                    "base_path": None,
                },
            )
    except Exception:
        logger.exception("Failed to load Riksdagen API categories")

    for entry in tool_index or []:
        if not _is_eval_candidate_entry(entry):
            continue
        tool_id = str(getattr(entry, "tool_id", "") or "").strip()
        if not tool_id:
            continue
        provider_key = _provider_for_tool_id(tool_id)
        category_id = str(getattr(entry, "category", "") or provider_key).strip() or provider_key
        level = "top_level" if category_id == provider_key else "subcategory"
        _append_item(
            provider_key,
            {
                "tool_id": tool_id,
                "tool_name": str(getattr(entry, "name", "") or tool_id),
                "category_id": category_id,
                "category_name": _category_name(category_id),
                "level": level,
                "description": str(getattr(entry, "description", "") or ""),
                "base_path": getattr(entry, "base_path", None),
            },
        )

    providers: list[dict[str, Any]] = []
    for provider_key, provider in providers_by_key.items():
        categories = list(provider.get("categories") or [])
        categories.sort(
            key=lambda item: (
                str(item.get("level") or "") != "top_level",
                str(item.get("category_name") or "").lower(),
                str(item.get("tool_name") or "").lower(),
            )
        )
        providers.append(
            {
                "provider_key": provider_key,
                "provider_name": provider.get("provider_name")
                or _provider_display_name(provider_key),
                "categories": categories,
            }
        )
    providers.sort(key=lambda item: str(item.get("provider_name") or "").lower())
    return {"providers": providers}


def _slugify(value: str, fallback: str = "eval") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or fallback


def _provider_for_tool_id(tool_id: str) -> str:
    normalized = str(tool_id or "").strip().lower()
    if normalized.startswith("scb_"):
        return "scb"
    if normalized.startswith("riksdag_"):
        return "riksdagen"
    if normalized.startswith("trafikverket_"):
        return "trafikverket"
    if normalized.startswith("bolagsverket_"):
        return "bolagsverket"
    if normalized.startswith("geoapify_"):
        return "geoapify"
    if normalized.startswith("smhi_") or normalized == "smhi_weather":
        return "smhi"
    if normalized.startswith("trafiklab_") or normalized == "trafiklab_route":
        return "trafiklab"
    if normalized.startswith("libris_"):
        return "libris"
    if normalized.startswith("jobad_"):
        return "jobad"
    if normalized in {"search_web", "search_tavily", "scrape_webpage", "link_preview"}:
        return "web"
    if normalized in {"search_surfsense_docs", "search_knowledge_base"}:
        return "surfsense"
    if normalized in {"generate_podcast", "display_image"}:
        return "media"
    return "other"


def _is_weather_domain_tool(tool_id: str, category: str | None = None) -> bool:
    normalized_tool = str(tool_id or "").strip().lower()
    normalized_category = str(category or "").strip().lower()
    if normalized_tool == "smhi_weather":
        return True
    if normalized_tool.startswith("trafikverket_vader_"):
        return True
    if normalized_category in {"weather", "trafikverket_vader"}:
        return True
    return False


def _provider_display_name(provider_key: str) -> str:
    mapping = {
        "scb": "SCB",
        "riksdagen": "Riksdagen",
        "trafikverket": "Trafikverket",
        "bolagsverket": "Bolagsverket",
        "geoapify": "Geoapify",
        "smhi": "SMHI",
        "trafiklab": "Trafiklab",
        "libris": "Libris",
        "jobad": "JobAD",
        "web": "Web Tools",
        "surfsense": "SurfSense",
        "media": "Media Tools",
        "other": "Övriga",
    }
    key = str(provider_key or "").strip().lower()
    if key in mapping:
        return mapping[key]
    return _category_name(key)


def _infer_route_for_tool(tool_id: str, category: str | None = None) -> tuple[str, str | None]:
    normalized_tool = str(tool_id or "").strip().lower()
    normalized_category = str(category or "").strip().lower()
    if normalized_tool.startswith("scb_") or normalized_category in {"statistics", "scb_statistics"}:
        return "statistics", None
    if normalized_tool in {"trafiklab_route"} or _is_weather_domain_tool(
        normalized_tool,
        normalized_category,
    ):
        return "action", "travel"
    if normalized_tool.startswith("trafikverket_"):
        return "action", "travel"
    if normalized_tool in {"scrape_webpage", "link_preview", "search_web", "search_tavily"}:
        return "action", "web"
    if normalized_tool in {"generate_podcast", "display_image"}:
        return "action", "media"
    if normalized_tool in {"libris_search", "jobad_links_search"}:
        return "action", "data"
    if normalized_tool.startswith("bolagsverket_") or normalized_tool.startswith("riksdag_"):
        return "action", "data"
    if normalized_tool in {"search_surfsense_docs", "search_knowledge_base"}:
        return "knowledge", "internal"
    return "action", "data"


def _infer_agent_for_tool(
    tool_id: str,
    category: str | None = None,
    route: str | None = None,
    sub_route: str | None = None,
) -> str:
    normalized_tool = str(tool_id or "").strip().lower()
    normalized_category = str(category or "").strip().lower()
    normalized_route = str(route or "").strip().lower()
    normalized_sub_route = str(sub_route or "").strip().lower()
    if normalized_tool.startswith("scb_") or normalized_category in {"statistics", "scb_statistics"}:
        return "statistics"
    if normalized_tool.startswith("riksdag_") or normalized_category.startswith("riksdag"):
        return "riksdagen"
    if _is_weather_domain_tool(normalized_tool, normalized_category):
        return "weather"
    if normalized_tool.startswith("trafikverket_") or normalized_tool in {"trafiklab_route"}:
        return "trafik"
    if normalized_tool.startswith("bolagsverket_"):
        return "bolag"
    if normalized_tool.startswith("geoapify_"):
        return "kartor"
    if normalized_tool in {"generate_podcast", "display_image"}:
        return "media"
    if normalized_tool in {"search_web", "search_tavily", "scrape_webpage", "link_preview"}:
        return "browser"
    if normalized_tool in {"search_surfsense_docs", "search_knowledge_base"}:
        return "knowledge"
    if normalized_route == "statistics":
        return "statistics"
    if normalized_route == "compare":
        return "synthesis"
    if normalized_route == "knowledge":
        return "knowledge"
    if normalized_route == "action" and normalized_sub_route == "travel":
        return "trafik"
    if normalized_route == "action" and normalized_sub_route == "web":
        return "browser"
    if normalized_route == "action" and normalized_sub_route == "media":
        return "media"
    if normalized_route == "action":
        return "action"
    return "action"


def _pick_reference(values: list[str], index: int, offset: int = 0) -> str:
    if not values:
        return ""
    return str(values[(index + offset) % len(values)])


def _contains_sweden_context(text: str) -> bool:
    lowered = str(text or "").strip().casefold()
    if not lowered:
        return False
    if any(marker in lowered for marker in _SWEDEN_CONTEXT_MARKERS):
        return True
    if any(city.casefold() in lowered for city in _SWEDISH_CITIES):
        return True
    if any(road.casefold() in lowered for road in _SWEDISH_ROADS):
        return True
    return False


def _looks_non_swedish(text: str) -> bool:
    lowered = str(text or "").strip().casefold()
    return any(marker in lowered for marker in _NON_SWEDISH_MARKERS)


def _sweden_focus_hint_for_entry(entry: Any) -> str:
    tool_id = str(getattr(entry, "tool_id", "") or "").strip().lower()
    category = str(getattr(entry, "category", "") or "").strip().lower()
    route, sub_route = _infer_route_for_tool(tool_id, category)
    if tool_id.startswith("scb_") or route == "statistics":
        return (
            "Frågan ska handla om Sverige och använda svenska kommuner/län "
            "samt officiell statistik-kontext."
        )
    if tool_id.startswith("riksdag_"):
        return (
            "Frågan ska handla om svensk politik/riksdagen, till exempel "
            "motioner, interpellationer eller utskott."
        )
    if _is_weather_domain_tool(tool_id, category):
        return "Frågan ska gälla svenskt väder i svenska städer, gärna med vägkoppling."
    if sub_route == "travel" or "trafik" in tool_id or "trafik" in category:
        return (
            "Frågan ska använda giltiga svenska städer och vägar "
            "(t.ex. E4, E6, E18, E20)."
        )
    if tool_id.startswith("bolagsverket_"):
        return "Frågan ska gälla svenska företag och svensk bolagskontext."
    if sub_route == "web":
        return "Frågan ska gälla svensk information, svenska källor eller händelser i Sverige."
    return "Frågan ska vara på svenska och tydligt ha svensk/sverige-kontext."


def _build_swedish_question_for_entry(entry: Any, index: int) -> str:
    tool_id = str(getattr(entry, "tool_id", "") or "").strip().lower()
    category = str(getattr(entry, "category", "") or "").strip().lower()
    route, sub_route = _infer_route_for_tool(tool_id, category)
    city = _pick_reference(_SWEDISH_CITIES, index)
    city_alt = _pick_reference(_SWEDISH_CITIES, index, offset=4)
    region = _pick_reference(_SWEDISH_REGIONS, index)
    road = _pick_reference(_SWEDISH_ROADS, index)
    topic = _pick_reference(_SWEDISH_POLITICS_TOPICS, index)
    if tool_id.startswith("scb_") or route == "statistics":
        return (
            f"Hur har {topic} utvecklats i {city} kommun och {region} "
            "de senaste fem åren?"
        )
    if tool_id.startswith("riksdag_"):
        return (
            f"Vilka riksdagsdokument handlar om {topic} i Sverige "
            "under det senaste året?"
        )
    if sub_route == "travel" or "trafik" in tool_id or "trafik" in category:
        if _is_weather_domain_tool(tool_id, category) or "halka" in tool_id:
            return (
                f"Hur blir vädret i {city} i morgon och finns risk för halka på {road}?"
            )
        if "route" in tool_id:
            return (
                f"Vilken resa rekommenderas mellan {city} och {city_alt} i dag, "
                f"med fokus på trafikläget på {road}?"
            )
        return f"Hur ser trafikläget ut på {road} mellan {city} och {city_alt} just nu?"
    if _is_weather_domain_tool(tool_id, category):
        return f"Hur blir vädret i {city} i morgon enligt svenska prognoser?"
    if tool_id.startswith("bolagsverket_"):
        return (
            f"Kan du hämta information om ett svenskt företag med säte i {city}?"
        )
    if tool_id in {"libris_search"}:
        return f"Hitta svenska böcker om {topic} med koppling till {city}."
    if tool_id in {"jobad_links_search"}:
        return f"Vilka jobbannonser finns i {city} inom offentlig sektor i Sverige?"
    if tool_id in {"search_web", "search_tavily", "scrape_webpage", "link_preview"}:
        return f"Hitta aktuell information om {topic} i Sverige och sammanfatta kort."
    if tool_id in {"search_surfsense_docs", "search_knowledge_base"}:
        return f"Vad säger dokumentationen om {topic} för svenska användare i {city}?"
    description = str(getattr(entry, "description", "") or "").strip()
    if description:
        return f"Kan du hjälpa mig med svensk data om {description[:80]} i {city}?"
    return f"Vilket verktyg ska användas för en svensk fråga om {topic} i {city}?"


def _ensure_swedish_question_context(question: str, entry: Any, index: int) -> str:
    cleaned = _restore_swedish_diacritics(str(question or "").strip())
    if not cleaned:
        return _build_swedish_question_for_entry(entry, index)
    if _looks_non_swedish(cleaned) and not _contains_sweden_context(cleaned):
        return _build_swedish_question_for_entry(entry, index)
    if not _contains_sweden_context(cleaned):
        city = _pick_reference(_SWEDISH_CITIES, index)
        suffix = cleaned.rstrip("?.! ")
        return _restore_swedish_diacritics(f"{suffix} i {city}, Sverige?")
    return _restore_swedish_diacritics(cleaned)


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
    difficulty_profile: str,
) -> list[dict[str, Any]]:
    if not selected_entries:
        return []
    normalized_profile = _normalize_difficulty_profile(difficulty_profile)
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
        inferred_route, inferred_sub_route = _infer_route_for_tool(
            expected_tool,
            expected_category or str(getattr(entry, "category", "")).strip(),
        )
        expected_route = str(
            expected.get("route") or source.get("expected_route") or inferred_route
        ).strip()
        expected_sub_route = (
            str(expected.get("sub_route") or source.get("expected_sub_route") or inferred_sub_route or "").strip()
            or None
        )
        expected_agent = str(
            expected.get("agent")
            or source.get("expected_agent")
            or _infer_agent_for_tool(
                expected_tool,
                expected_category or str(getattr(entry, "category", "")).strip(),
                expected_route,
                expected_sub_route,
            )
        ).strip()
        source_plan_requirements = expected.get("plan_requirements") or source.get(
            "plan_requirements"
        )
        if isinstance(source_plan_requirements, list):
            plan_requirements = [
                str(item).strip() for item in source_plan_requirements if str(item).strip()
            ]
        else:
            plan_requirements = [
                f"route:{expected_route}",
                f"agent:{expected_agent}",
                f"tool:{expected_tool}",
            ]
        question = str(source.get("question") or "").strip()
        if not question:
            examples = list(getattr(entry, "example_queries", []) or [])
            if examples:
                question = examples[idx % len(examples)]
            else:
                question = (
                    f"Vilket verktyg ska användas för: {getattr(entry, 'name', expected_tool)}?"
                )
        question = _ensure_swedish_question_context(question, entry, idx)
        source_difficulty = _normalize_difficulty_label(source.get("difficulty"))
        difficulty = (
            normalized_profile
            if normalized_profile in _DIFFICULTY_LABELS
            else source_difficulty or _difficulty_for_index(idx, normalized_profile)
        )
        normalized.append(
            {
                "id": str(source.get("id") or f"case-{idx + 1}"),
                "question": question,
                "difficulty": difficulty,
                "expected": {
                    "tool": expected_tool,
                    "category": expected_category or getattr(entry, "category", None),
                    "route": expected_route,
                    "sub_route": expected_sub_route,
                    "agent": expected_agent,
                    "plan_requirements": plan_requirements,
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
    difficulty_profile: str,
) -> list[dict[str, Any]]:
    normalized_profile = _normalize_difficulty_profile(difficulty_profile)
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
        question = _ensure_swedish_question_context(question, entry, idx)
        tool_id = str(getattr(entry, "tool_id", "")).strip()
        route, sub_route = _infer_route_for_tool(
            tool_id,
            str(getattr(entry, "category", "")).strip(),
        )
        agent = _infer_agent_for_tool(
            tool_id,
            str(getattr(entry, "category", "")).strip(),
            route,
            sub_route,
        )
        tests.append(
            {
                "id": f"case-{idx + 1}",
                "question": question,
                "difficulty": _difficulty_for_index(idx, normalized_profile),
                "expected": {
                    "tool": tool_id,
                    "category": str(getattr(entry, "category", "")).strip(),
                    "route": route,
                    "sub_route": sub_route,
                    "agent": agent,
                    "plan_requirements": [
                        f"route:{route}",
                        f"agent:{agent}",
                        f"tool:{tool_id}",
                    ],
                },
                "allowed_tools": [tool_id] if include_allowed_tools else [],
            }
        )
    return tests


def _tool_schema_for_generation(tool: Any) -> dict[str, Any]:
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
    return {}


def _required_fields_for_generation(tool: Any) -> list[str]:
    schema = _tool_schema_for_generation(tool)
    values = schema.get("required")
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _property_schema_for_generation(tool: Any) -> dict[str, dict[str, Any]]:
    schema = _tool_schema_for_generation(tool)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key, value in properties.items():
        if isinstance(value, dict):
            result[str(key)] = value
    return result


def _sample_expected_field_value(
    *,
    field_name: str,
    field_schema: dict[str, Any],
    question: str,
    entry: Any,
    index: int,
) -> tuple[bool, Any]:
    lowered = field_name.lower()
    question_text = str(question or "").strip()
    city = _pick_reference(_SWEDISH_CITIES, index)
    city_alt = _pick_reference(_SWEDISH_CITIES, index, offset=5)
    region = _pick_reference(_SWEDISH_REGIONS, index)
    road = _pick_reference(_SWEDISH_ROADS, index)
    if lowered in {"question", "query", "text", "prompt"}:
        return True, question_text
    if "country" in lowered or lowered in {"land", "nation"}:
        return True, "Sverige"
    if "language" in lowered or lowered in {"lang", "sprak", "språk"}:
        return True, "sv"
    if "road" in lowered or "vag" in lowered or "väg" in lowered or "highway" in lowered:
        return True, road
    if "kommun" in lowered or "municipality" in lowered:
        return True, f"{city} kommun"
    if "city" in lowered or "stad" in lowered:
        return True, city
    if "region" in lowered or "lan" in lowered or "county" in lowered:
        return True, region
    if lowered in {"from", "origin", "from_city", "start", "start_location"}:
        return True, city
    if lowered in {"to", "destination", "to_city", "end", "end_location"}:
        return True, city_alt
    if "date" in lowered or "datum" in lowered:
        month = 1 + (index % 12)
        day = 1 + (index % 27)
        return True, f"2025-{month:02d}-{day:02d}"
    if "time" in lowered or lowered in {"tid", "departure_time", "arrival_time"}:
        hour = 6 + (index % 14)
        return True, f"{hour:02d}:00"
    if "table" in lowered and getattr(entry, "base_path", None):
        return True, str(getattr(entry, "base_path"))
    if "base_path" in lowered and getattr(entry, "base_path", None):
        return True, str(getattr(entry, "base_path"))
    field_type = str(field_schema.get("type") or "").strip().lower()
    if field_type == "boolean":
        return True, True
    if field_type == "integer":
        if "limit" in lowered or "max" in lowered:
            return True, 10
        return True, 1
    if field_type == "number":
        if "lat" in lowered:
            return True, 59.33
        if "lon" in lowered or "lng" in lowered:
            return True, 18.06
        return True, 1.0
    if field_type == "array":
        item_schema = field_schema.get("items")
        if isinstance(item_schema, dict):
            ok, value = _sample_expected_field_value(
                field_name=f"{field_name}_item",
                field_schema=item_schema,
                question=question,
                entry=entry,
                index=index,
            )
            if ok:
                return True, [value]
        return True, [question_text] if question_text else []
    enum_values = field_schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return True, enum_values[index % len(enum_values)]
    return False, None


def _enrich_api_input_generated_tests(
    *,
    tests: list[dict[str, Any]],
    selected_entries: list[Any],
    tool_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    by_tool_id = {str(entry.tool_id): entry for entry in selected_entries}
    enriched: list[dict[str, Any]] = []
    for index, test in enumerate(tests):
        expected = test.get("expected") if isinstance(test.get("expected"), dict) else {}
        expected_tool = str(expected.get("tool") or "").strip()
        entry = by_tool_id.get(expected_tool)
        if entry is None and selected_entries:
            entry = selected_entries[index % len(selected_entries)]
            expected_tool = str(getattr(entry, "tool_id", "") or "")
        tool = tool_registry.get(expected_tool) if expected_tool else None
        required_fields = _required_fields_for_generation(tool)
        properties = _property_schema_for_generation(tool)
        field_values: dict[str, Any] = {}
        for field_name in required_fields:
            field_schema = properties.get(field_name) or {}
            has_value, value = _sample_expected_field_value(
                field_name=field_name,
                field_schema=field_schema,
                question=str(test.get("question") or ""),
                entry=entry,
                index=index,
            )
            if has_value:
                field_values[field_name] = value
        route, sub_route = _infer_route_for_tool(
            expected_tool,
            str(getattr(entry, "category", "") if entry else ""),
        )
        agent = _infer_agent_for_tool(
            expected_tool,
            str(getattr(entry, "category", "") if entry else ""),
            route,
            sub_route,
        )
        plan_requirements: list[str] = [
            f"route:{route}",
            f"agent:{agent}",
            f"tool:{expected_tool}",
        ]
        for field_name in required_fields[:2]:
            plan_requirements.append(f"field:{field_name}")
        expected_payload = {
            "tool": expected_tool or expected.get("tool"),
            "category": expected.get("category")
            or (str(getattr(entry, "category", "")).strip() if entry else None),
            "route": route,
            "sub_route": sub_route,
            "agent": str(expected.get("agent") or agent).strip(),
            "plan_requirements": plan_requirements,
            "required_fields": required_fields,
            "field_values": field_values,
            "allow_clarification": False,
        }
        enriched.append(
            {
                "id": str(test.get("id") or f"case-{index + 1}"),
                "question": str(test.get("question") or ""),
                "difficulty": _normalize_difficulty_label(test.get("difficulty")),
                "expected": expected_payload,
                "allowed_tools": (
                    list(test.get("allowed_tools"))
                    if isinstance(test.get("allowed_tools"), list)
                    else []
                ),
            }
        )
    return enriched


def _build_eval_library_payload(
    *,
    eval_type: str | None = None,
    eval_name: str | None,
    target_success_rate: float | None,
    difficulty_profile: str | None,
    tests: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "eval_type": eval_type or "tool_selection",
        "eval_name": eval_name,
        "tests": tests,
    }
    if target_success_rate is not None:
        payload["target_success_rate"] = target_success_rate
    normalized_profile = _normalize_difficulty_profile(difficulty_profile)
    if normalized_profile:
        payload["difficulty_profile"] = normalized_profile
    return payload


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
    if mode == "global_random":
        category_fallback = "mixed"
    elif mode == "provider":
        category_fallback = "all_categories"
    else:
        category_fallback = "general"
    category_slug = _slugify(category_id or category_fallback)
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
    difficulty_profile: str,
) -> list[dict[str, Any]]:
    normalized_difficulty_profile = _normalize_difficulty_profile(difficulty_profile)
    fallback_tests = _build_fallback_generated_tests(
        selected_entries=selected_entries,
        question_count=question_count,
        include_allowed_tools=include_allowed_tools,
        difficulty_profile=normalized_difficulty_profile,
    )
    if llm is None:
        return fallback_tests
    prompt = (
        "Generate evaluation tests for tool routing.\n"
        "Context: The system is optimized for Swedish users and Swedish domains.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "tests": [\n'
        "    {\n"
        '      "id": "case-1",\n'
        '      "question": "string",\n'
        '      "difficulty": "lätt|medel|svår",\n'
        '      "expected": {\n'
        '        "tool": "tool_id",\n'
        '        "category": "category",\n'
        '        "route": "action|knowledge|statistics|smalltalk|compare",\n'
        '        "sub_route": "web|media|travel|data|docs|internal|external|null",\n'
        '        "agent": "trafik|statistics|riksdagen|bolag|kartor|media|browser|knowledge|action|synthesis",\n'
        '        "plan_requirements": ["route:action", "agent:trafik", "tool:tool_id"]\n'
        "      },\n"
        '      "allowed_tools": ["tool_id"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Generate exactly the requested number of tests.\n"
        "- Use only provided tool_ids.\n"
        "- Cover different intents and at least one harder/confusable case.\n"
        "- Questions must be in Swedish only.\n"
        "- Use proper Swedish characters (å, ä, ö), not ASCII transliterations.\n"
        "- Every question must be Sweden-specific and realistic for Sweden.\n"
        "- Use valid Swedish cities and rotate them across tests.\n"
        "- For traffic/travel/weather tools, use valid Swedish roads (e.g. E4, E6, E18, E20) and vary roads.\n"
        "- For politics/government tools, focus on Swedish politics and riksdag contexts.\n"
        "- For statistics tools, focus on Swedish municipalities/regions and official Swedish statistics context.\n"
        f"{_difficulty_instructions_for_profile(normalized_difficulty_profile)}\n"
        "- Never generate generic/global/non-Swedish examples.\n"
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
            "sweden_focus_hint": _sweden_focus_hint_for_entry(entry),
        }
        for entry in selected_entries[:40]
    ]
    payload = {
        "question_count": question_count,
        "difficulty_profile": normalized_difficulty_profile,
        "swedish_reference": {
            "cities": _SWEDISH_CITIES,
            "roads": _SWEDISH_ROADS,
            "regions": _SWEDISH_REGIONS,
            "politics_topics": _SWEDISH_POLITICS_TOPICS,
        },
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
            difficulty_profile=normalized_difficulty_profile,
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
    normalized_mode = str(mode or "category").strip().lower()
    if normalized_mode not in {"category", "global_random", "provider"}:
        normalized_mode = "category"
    provider_filter = str(provider_key or "").strip().lower()
    category_filter = str(category_id or "").strip()
    candidates = [entry for entry in tool_index if _is_eval_candidate_entry(entry)]

    if provider_filter and provider_filter != "all":
        candidates = [
            entry
            for entry in candidates
            if _provider_for_tool_id(str(entry.tool_id)) == provider_filter
        ]

    if normalized_mode == "provider":
        if not provider_filter or provider_filter == "all":
            raise HTTPException(
                status_code=400,
                detail="provider_key is required when mode=provider",
            )
        if not candidates:
            raise HTTPException(
                status_code=404,
                detail="No tools found for selected provider",
            )
        return candidates

    if normalized_mode == "category":
        if not category_filter:
            raise HTTPException(
                status_code=400,
                detail="category_id is required when mode=category",
            )
        api_categories = (
            _build_tool_api_categories_response(tool_index=candidates).get("providers")
            or []
        )
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


async def _prune_api_input_eval_jobs() -> None:
    if len(_API_INPUT_EVAL_JOBS) <= _MAX_API_INPUT_EVAL_JOBS:
        return
    finished = [
        (job_id, payload)
        for job_id, payload in _API_INPUT_EVAL_JOBS.items()
        if payload.get("status") in {"completed", "failed"}
    ]
    finished.sort(key=lambda item: str(item[1].get("updated_at") or ""))
    overflow = len(_API_INPUT_EVAL_JOBS) - _MAX_API_INPUT_EVAL_JOBS
    for job_id, _payload in finished[: max(0, overflow)]:
        _API_INPUT_EVAL_JOBS.pop(job_id, None)


async def _update_api_input_eval_job(job_id: str, **updates: Any) -> None:
    async with _API_INPUT_EVAL_JOBS_LOCK:
        job = _API_INPUT_EVAL_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = _utcnow_iso()


def _serialize_api_input_eval_job(job: dict[str, Any]) -> dict[str, Any]:
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


async def _prune_auto_loop_jobs() -> None:
    if len(_AUTO_LOOP_JOBS) <= _MAX_AUTO_LOOP_JOBS:
        return
    finished = [
        (job_id, payload)
        for job_id, payload in _AUTO_LOOP_JOBS.items()
        if payload.get("status") in {"completed", "failed"}
    ]
    finished.sort(key=lambda item: str(item[1].get("updated_at") or ""))
    overflow = len(_AUTO_LOOP_JOBS) - _MAX_AUTO_LOOP_JOBS
    for job_id, _payload in finished[: max(0, overflow)]:
        _AUTO_LOOP_JOBS.pop(job_id, None)


async def _update_auto_loop_job(job_id: str, **updates: Any) -> None:
    async with _AUTO_LOOP_JOBS_LOCK:
        job = _AUTO_LOOP_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = _utcnow_iso()


def _serialize_auto_loop_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "total_iterations": int(job.get("total_iterations", 0)),
        "completed_iterations": int(job.get("completed_iterations", 0)),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "updated_at": job.get("updated_at") or _utcnow_iso(),
        "current_iteration": int(job.get("current_iteration", 0)),
        "best_success_rate": _to_float(job.get("best_success_rate")),
        "no_improvement_runs": int(job.get("no_improvement_runs", 0)),
        "message": job.get("message"),
        "iterations": job.get("iterations") or [],
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


def _normalize_eval_stage(stage: str) -> str:
    normalized = str(stage or "").strip().lower()
    if normalized in {"agent", "agent_eval", "agent_selection"}:
        return "agent"
    if normalized in {"tool", "tool_eval", "tool_selection"}:
        return "tool"
    if normalized in {"api", "api_input", "api-input"}:
        return "api_input"
    raise HTTPException(status_code=400, detail=f"Unsupported eval stage: {stage}")


def _pass_field_for_stage(stage: str) -> str:
    normalized = _normalize_eval_stage(stage)
    if normalized == "agent":
        return "passed_agent"
    if normalized == "tool":
        return "passed_tool"
    return "passed_api_input"


def _stage_metric_name(stage: str) -> str:
    normalized = _normalize_eval_stage(stage)
    if normalized == "agent":
        return "agent_accuracy"
    if normalized == "tool":
        return "tool_accuracy"
    return "api_input_accuracy"


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def _comparison_metric_keys(stage: str) -> list[str]:
    normalized = _normalize_eval_stage(stage)
    shared = [
        "route_accuracy",
        "sub_route_accuracy",
        "agent_accuracy",
        "plan_accuracy",
        "supervisor_review_pass_rate",
        "supervisor_review_score",
        "category_accuracy",
        "tool_accuracy",
    ]
    if normalized == "tool":
        return shared + ["retrieval_recall_at_k"]
    if normalized == "api_input":
        return shared + [
            "schema_validity_rate",
            "required_field_recall",
            "field_value_accuracy",
            "clarification_accuracy",
        ]
    return shared


def _guidance_from_comparison(
    *,
    stage: str,
    success_delta: float | None,
    metric_deltas: list[dict[str, Any]],
    target_success_rate: float | None,
    current_success_rate: float,
) -> list[str]:
    guidance: list[str] = []
    degraded_metrics = [
        item["metric"]
        for item in metric_deltas
        if _to_float(item.get("delta")) is not None and float(item["delta"]) <= -0.02
    ]
    improved_metrics = [
        item["metric"]
        for item in metric_deltas
        if _to_float(item.get("delta")) is not None and float(item["delta"]) >= 0.02
    ]

    if success_delta is None:
        guidance.append(
            "Ingen tidigare jämförbar körning hittades för denna stage ännu. "
            "Kör samma suite igen efter en begränsad ändring för att få tydlig diff."
        )
    elif success_delta <= -0.005:
        guidance.append(
            "Resultatet blev sämre än föregående körning. Testa att backa senaste stora ändring "
            "och applicera mindre, isolerade ändringar per iteration."
        )
        if any(metric in degraded_metrics for metric in ["route_accuracy", "sub_route_accuracy"]):
            guidance.append(
                "Regression i route/sub-route: prioritera supervisor/router-prompt och kontrollera "
                "att route/sub-route-exempel matchar testernas formuleringar."
            )
        if "agent_accuracy" in degraded_metrics:
            guidance.append(
                "Regression i agentval: skärp regler i supervisor för när retrieve_agents ska köras "
                "om och när agent-id måste vara exakta."
            )
        if any(metric in degraded_metrics for metric in ["tool_accuracy", "retrieval_recall_at_k"]):
            guidance.append(
                "Regression i tool-träff: fokusera på metadata (description/keywords/example_queries) "
                "och retrieval-vikter innan fler promptändringar."
            )
        if stage == "api_input" and any(
            metric in degraded_metrics
            for metric in [
                "schema_validity_rate",
                "required_field_recall",
                "field_value_accuracy",
            ]
        ):
            guidance.append(
                "Regression i API-input: gör verktygsspecifika promptförtydliganden för required_fields, "
                "fältformat och validering innan anrop."
            )
    elif success_delta >= 0.005:
        guidance.append(
            "Resultatet förbättrades jämfört med föregående körning. Fortsätt med små ändringar "
            "och verifiera på holdout-suite för att undvika överanpassning."
        )
    else:
        guidance.append(
            "Resultatet är nära oförändrat jämfört med föregående körning. "
            "Byt strategi och fokusera på en dimension åt gången (route/agent/tool/API-input)."
        )

    if improved_metrics and success_delta is not None and success_delta > 0:
        guidance.append(
            "Förbättrade dimensioner: "
            + ", ".join(improved_metrics[:4])
            + ". Behåll dessa ändringar och iterera på kvarvarande svagheter."
        )
    if degraded_metrics and success_delta is not None and success_delta > -0.005:
        guidance.append(
            "Varning: vissa delmått sjönk trots liknande total success. "
            "Verifiera att inga regressionsrisker byggs in."
        )

    if (
        target_success_rate is not None
        and 0 <= target_success_rate <= 1
        and current_success_rate < target_success_rate
    ):
        guidance.append(
            f"Nuvarande success ({current_success_rate * 100:.1f}%) är under target "
            f"({target_success_rate * 100:.1f}%). Prioritera de mest regressiva metrikerna först."
        )
    return guidance


async def _build_stage_run_comparison(
    session: AsyncSession,
    *,
    search_space_id: int,
    stage: str,
    result: dict[str, Any],
    target_success_rate: float | None,
) -> dict[str, Any]:
    normalized_stage = _normalize_eval_stage(stage)
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    current_success_rate = _to_float(metrics.get("success_rate")) or 0.0
    stage_metric_name = _stage_metric_name(normalized_stage)
    current_stage_metric = _to_float(metrics.get(stage_metric_name))
    current_gated_success = _to_float(metrics.get("gated_success_rate"))
    if current_stage_metric is None:
        (
            _stage_total,
            _stage_passed,
            _stage_success_rate,
            _category_breakdown,
            derived_stage_metric,
        ) = _build_stage_breakdown(stage=normalized_stage, result=result)
        current_stage_metric = derived_stage_metric

    previous_row_result = await session.execute(
        select(GlobalToolEvaluationStageRun)
        .filter(
            GlobalToolEvaluationStageRun.search_space_id == search_space_id,
            GlobalToolEvaluationStageRun.stage == normalized_stage,
        )
        .order_by(GlobalToolEvaluationStageRun.created_at.desc())
        .limit(1)
    )
    previous_row = previous_row_result.scalars().first()
    previous_metadata = (
        previous_row.run_metadata
        if previous_row is not None and isinstance(previous_row.run_metadata, dict)
        else {}
    )

    metric_deltas: list[dict[str, Any]] = []
    for metric_key in _comparison_metric_keys(normalized_stage):
        previous_value = _to_float(previous_metadata.get(metric_key))
        current_value = _to_float(metrics.get(metric_key))
        metric_deltas.append(
            ToolEvaluationMetricDeltaItem(
                metric=metric_key,
                previous=previous_value,
                current=current_value,
                delta=_delta(current_value, previous_value),
            ).model_dump()
        )

    if previous_row is None:
        return ToolEvaluationRunComparison(
            stage=normalized_stage,
            stage_metric_name=stage_metric_name,
            trend="insufficient_data",
            previous_run_at=None,
            previous_eval_name=None,
            previous_success_rate=None,
            current_success_rate=current_success_rate,
            success_rate_delta=None,
            previous_stage_metric=None,
            current_stage_metric=current_stage_metric,
            stage_metric_delta=None,
            previous_gated_success_rate=None,
            current_gated_success_rate=current_gated_success,
            gated_success_rate_delta=None,
            metric_deltas=metric_deltas,
            guidance=_guidance_from_comparison(
                stage=normalized_stage,
                success_delta=None,
                metric_deltas=metric_deltas,
                target_success_rate=target_success_rate,
                current_success_rate=current_success_rate,
            ),
        ).model_dump()

    previous_success_rate = _to_float(previous_row.success_rate) or 0.0
    previous_stage_metric = _to_float(previous_row.metric_value)
    previous_gated_success = _to_float(previous_metadata.get("gated_success_rate"))
    success_delta = current_success_rate - previous_success_rate
    trend = "unchanged"
    if success_delta >= 0.005:
        trend = "improved"
    elif success_delta <= -0.005:
        trend = "degraded"

    return ToolEvaluationRunComparison(
        stage=normalized_stage,
        stage_metric_name=stage_metric_name,
        trend=trend,
        previous_run_at=(
            previous_row.created_at.isoformat() if previous_row.created_at else _utcnow_iso()
        ),
        previous_eval_name=previous_row.eval_name,
        previous_success_rate=previous_success_rate,
        current_success_rate=current_success_rate,
        success_rate_delta=success_delta,
        previous_stage_metric=previous_stage_metric,
        current_stage_metric=current_stage_metric,
        stage_metric_delta=_delta(current_stage_metric, previous_stage_metric),
        previous_gated_success_rate=previous_gated_success,
        current_gated_success_rate=current_gated_success,
        gated_success_rate_delta=_delta(current_gated_success, previous_gated_success),
        metric_deltas=metric_deltas,
        guidance=_guidance_from_comparison(
            stage=normalized_stage,
            success_delta=success_delta,
            metric_deltas=metric_deltas,
            target_success_rate=target_success_rate,
            current_success_rate=current_success_rate,
        ),
    ).model_dump()


def _build_stage_breakdown(
    *,
    stage: str,
    result: dict[str, Any],
) -> tuple[int, int, float, list[dict[str, Any]], float | None]:
    pass_field = _pass_field_for_stage(stage)
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    rows = result.get("results") if isinstance(result.get("results"), list) else []
    stage_total = 0
    stage_passed = 0
    grouped: dict[str, dict[str, int]] = {}

    for item in rows:
        if not isinstance(item, dict):
            continue
        passed_value = item.get(pass_field)
        if not isinstance(passed_value, bool):
            continue
        stage_total += 1
        if passed_value:
            stage_passed += 1
        category = (
            str(
                item.get("expected_category")
                or item.get("selected_category")
                or "okänd_kategori"
            )
            .strip()
            or "okänd_kategori"
        )
        bucket = grouped.setdefault(category, {"total": 0, "passed": 0})
        bucket["total"] += 1
        if passed_value:
            bucket["passed"] += 1

    category_breakdown: list[dict[str, Any]] = []
    for category, counts in sorted(grouped.items(), key=lambda pair: pair[0]):
        total = int(counts.get("total") or 0)
        passed = int(counts.get("passed") or 0)
        category_breakdown.append(
            {
                "category_id": category,
                "total_tests": total,
                "passed_tests": passed,
                "success_rate": (passed / total) if total else 0.0,
            }
        )

    if stage_total == 0:
        stage_total = int(metrics.get("total_tests") or 0)
        stage_passed = int(metrics.get("passed_tests") or 0)
    stage_success_rate = (stage_passed / stage_total) if stage_total else 0.0

    metric_name = _stage_metric_name(stage)
    metric_value = _to_float(metrics.get(metric_name))
    if metric_value is None:
        metric_value = stage_success_rate if stage_total else None
    return stage_total, stage_passed, stage_success_rate, category_breakdown, metric_value


async def _record_eval_stage_summaries(
    session: AsyncSession,
    *,
    search_space_id: int,
    result: dict[str, Any],
    stages: list[str],
    updated_by_id: Any | None = None,
) -> None:
    eval_name = str(result.get("eval_name") or "").strip() or None
    metrics_payload = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    run_metadata = {
        "gated_success_rate": _to_float(metrics_payload.get("gated_success_rate")),
    }
    for metric_key in _comparison_metric_keys("api_input"):
        run_metadata[metric_key] = _to_float(metrics_payload.get(metric_key))
    rows: list[GlobalToolEvaluationStageRun] = []
    for raw_stage in stages:
        stage = _normalize_eval_stage(raw_stage)
        total_tests, passed_tests, success_rate, category_breakdown, metric_value = (
            _build_stage_breakdown(stage=stage, result=result)
        )
        rows.append(
            GlobalToolEvaluationStageRun(
                search_space_id=search_space_id,
                stage=stage,
                eval_name=eval_name,
                metric_name=_stage_metric_name(stage),
                metric_value=metric_value,
                total_tests=total_tests,
                passed_tests=passed_tests,
                success_rate=success_rate,
                category_breakdown=category_breakdown,
                run_metadata=dict(run_metadata),
                updated_by_id=updated_by_id,
            )
        )
    if not rows:
        return
    try:
        for row in rows:
            session.add(row)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("Failed to persist eval stage history")


async def _get_eval_stage_history(
    session: AsyncSession,
    *,
    search_space_id: int,
    stage: str,
    limit: int = 80,
) -> dict[str, Any]:
    normalized_stage = _normalize_eval_stage(stage)
    normalized_limit = max(1, min(int(limit or 80), 300))
    result = await session.execute(
        select(GlobalToolEvaluationStageRun)
        .filter(
            GlobalToolEvaluationStageRun.search_space_id == search_space_id,
            GlobalToolEvaluationStageRun.stage == normalized_stage,
        )
        .order_by(GlobalToolEvaluationStageRun.created_at.desc())
        .limit(normalized_limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    items: list[dict[str, Any]] = []
    category_series: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        run_at = row.created_at.isoformat() if row.created_at else _utcnow_iso()
        category_breakdown = (
            row.category_breakdown if isinstance(row.category_breakdown, list) else []
        )
        items.append(
            {
                "run_at": run_at,
                "stage": normalized_stage,
                "eval_name": row.eval_name,
                "total_tests": int(row.total_tests or 0),
                "passed_tests": int(row.passed_tests or 0),
                "success_rate": float(row.success_rate or 0.0),
                "stage_metric_name": row.metric_name,
                "stage_metric_value": _to_float(row.metric_value),
                "category_breakdown": category_breakdown,
            }
        )
        for category_entry in category_breakdown:
            if not isinstance(category_entry, dict):
                continue
            category_id = str(category_entry.get("category_id") or "").strip()
            if not category_id:
                continue
            category_series.setdefault(category_id, []).append(
                {
                    "run_at": run_at,
                    "eval_name": row.eval_name,
                    "total_tests": int(category_entry.get("total_tests") or 0),
                    "passed_tests": int(category_entry.get("passed_tests") or 0),
                    "success_rate": float(category_entry.get("success_rate") or 0.0),
                    "stage_metric_value": _to_float(row.metric_value),
                }
            )
    return {
        "stage": normalized_stage,
        "items": items,
        "category_series": [
            {"category_id": category_id, "points": points}
            for category_id, points in sorted(category_series.items(), key=lambda pair: pair[0])
        ],
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


def _default_tool_system_prompt(entry: Any) -> str:
    tool_id = str(getattr(entry, "tool_id", "")).strip()
    name = str(getattr(entry, "name", "")).strip()
    category = str(getattr(entry, "category", "")).strip()
    description = str(getattr(entry, "description", "")).strip()
    keywords = [
        str(item).strip()
        for item in list(getattr(entry, "keywords", []) or [])
        if str(item).strip()
    ][:10]
    examples = [
        str(item).strip()
        for item in list(getattr(entry, "example_queries", []) or [])
        if str(item).strip()
    ][:6]
    return "\n".join(
        [
            f"Du är specialist för verktyget {tool_id}.",
            "Fokusera endast på detta verktyg och blanda inte in andra endpoint-kategorier.",
            f"Tool: {name or tool_id}",
            f"Kategori: {category or 'okänd'}",
            f"Beskrivning: {description or '-'}",
            f"Nyckelord: {', '.join(keywords) if keywords else '-'}",
            f"Exempelfrågor: {' | '.join(examples) if examples else '-'}",
            "Regler:",
            "- Använd exakt argumentnamn från valt verktygs schema.",
            "- Om viktiga fält saknas: ställ en kort förtydligande fråga.",
            "- Undvik antaganden om fält som inte explicit nämns i fråga eller schema.",
            "- Om frågan inte längre matchar verktygets domän: kör retrieve_tools igen innan du fortsätter.",
        ]
    )


def _build_current_eval_prompts(
    *,
    prompt_overrides: dict[str, str],
    tool_index: list[Any],
) -> dict[str, str]:
    current_prompts: dict[str, str] = {}
    for prompt_key, definition in PROMPT_DEFINITION_MAP.items():
        current_prompts[prompt_key] = resolve_prompt(
            prompt_overrides,
            prompt_key,
            definition.default_prompt,
        )
    for entry in tool_index:
        tool_id = str(getattr(entry, "tool_id", "")).strip()
        if not tool_id:
            continue
        tool_prompt_key = f"tool.{tool_id}.system"
        current_prompts[tool_prompt_key] = resolve_prompt(
            prompt_overrides,
            tool_prompt_key,
            _default_tool_system_prompt(entry),
        )
    return current_prompts


def _is_valid_prompt_key(prompt_key: str) -> bool:
    if prompt_key in PROMPT_DEFINITION_MAP:
        return True
    return bool(re.match(r"^tool\.[a-z0-9_-]+\.(system|input)$", prompt_key))


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


async def _build_tool_registry_and_index_for_search_space(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
    metadata_patch: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
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
    return tool_registry, tool_index, persisted_overrides, effective_overrides


async def _build_tool_index_for_search_space(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
    metadata_patch: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    _tool_registry, tool_index, persisted_overrides, effective_overrides = (
        await _build_tool_registry_and_index_for_search_space(
            session,
            user,
            search_space_id=search_space_id,
            metadata_patch=metadata_patch,
        )
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
    prompt_patch: dict[str, str] | None = None,
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
    prompt_overrides = await get_global_prompt_overrides(session)
    if prompt_patch:
        prompt_overrides = {**prompt_overrides, **prompt_patch}
    current_prompts = _build_current_eval_prompts(
        prompt_overrides=prompt_overrides,
        tool_index=tool_index,
    )
    evaluation = await run_tool_evaluation(
        tests=[
            {
                "id": test.id,
                "question": test.question,
                "difficulty": test.difficulty,
                "expected": {
                    "tool": test.expected.tool if test.expected else None,
                    "category": test.expected.category if test.expected else None,
                    "agent": test.expected.agent if test.expected else None,
                    "route": test.expected.route if test.expected else None,
                    "sub_route": test.expected.sub_route if test.expected else None,
                    "plan_requirements": (
                        list(test.expected.plan_requirements) if test.expected else []
                    ),
                },
                "allowed_tools": list(test.allowed_tools),
            }
            for test in payload.tests
        ],
        tool_index=tool_index,
        llm=llm,
        retrieval_limit=payload.retrieval_limit,
        use_llm_supervisor_review=payload.use_llm_supervisor_review,
        retrieval_tuning=effective_tuning,
        prompt_overrides=current_prompts,
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
    prompt_suggestions = await suggest_agent_prompt_improvements_for_api_input(
        evaluation_results=evaluation["results"],
        current_prompts=current_prompts,
        llm=llm,
        suggestion_scope="full",
    )
    return {
        "eval_name": payload.eval_name,
        "target_success_rate": payload.target_success_rate,
        "metrics": evaluation["metrics"],
        "results": evaluation["results"],
        "suggestions": suggestions,
        "prompt_suggestions": prompt_suggestions,
        "retrieval_tuning": effective_tuning,
        "retrieval_tuning_suggestion": retrieval_tuning_suggestion,
        "metadata_version_hash": compute_metadata_version_hash(tool_index),
        "search_space_id": resolved_search_space_id,
    }


async def _execute_api_input_evaluation(
    session: AsyncSession,
    user: User,
    *,
    payload: ToolApiInputEvaluationRequest,
    resolved_search_space_id: int,
    progress_callback=None,
) -> dict[str, Any]:
    def _serialize_api_input_tests(test_cases: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": test.id,
                "question": test.question,
                "difficulty": test.difficulty,
                "expected": {
                    "tool": test.expected.tool if test.expected else None,
                    "category": test.expected.category if test.expected else None,
                    "agent": test.expected.agent if test.expected else None,
                    "route": test.expected.route if test.expected else None,
                    "sub_route": test.expected.sub_route if test.expected else None,
                    "plan_requirements": (
                        list(test.expected.plan_requirements) if test.expected else []
                    ),
                    "required_fields": (
                        list(test.expected.required_fields) if test.expected else []
                    ),
                    "field_values": (
                        dict(test.expected.field_values) if test.expected else {}
                    ),
                    "allow_clarification": (
                        test.expected.allow_clarification if test.expected else None
                    ),
                },
                "allowed_tools": list(test.allowed_tools),
            }
            for test in test_cases
        ]

    patch_map = _patch_map_from_updates(payload.metadata_patch)
    tool_registry, tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_registry_and_index_for_search_space(
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
    overrides = await get_global_prompt_overrides(session)
    current_prompts = _build_current_eval_prompts(
        prompt_overrides=overrides,
        tool_index=tool_index,
    )
    evaluation = await run_tool_api_input_evaluation(
        tests=_serialize_api_input_tests(payload.tests),
        tool_index=tool_index,
        tool_registry=tool_registry,
        llm=llm,
        retrieval_limit=payload.retrieval_limit,
        use_llm_supervisor_review=payload.use_llm_supervisor_review,
        retrieval_tuning=effective_tuning,
        prompt_overrides=current_prompts,
        progress_callback=progress_callback,
    )
    holdout_evaluation: dict[str, Any] | None = None
    if payload.holdout_tests:
        holdout_evaluation = await run_tool_api_input_evaluation(
            tests=_serialize_api_input_tests(payload.holdout_tests),
            tool_index=tool_index,
            tool_registry=tool_registry,
            llm=llm,
            retrieval_limit=payload.retrieval_limit,
            use_llm_supervisor_review=payload.use_llm_supervisor_review,
            retrieval_tuning=effective_tuning,
            prompt_overrides=current_prompts,
            progress_callback=None,
        )
    prompt_suggestions = await suggest_agent_prompt_improvements_for_api_input(
        evaluation_results=evaluation["results"],
        current_prompts=current_prompts,
        llm=llm,
        suggestion_scope="api_tool_only",
    )
    return {
        "eval_name": payload.eval_name,
        "target_success_rate": payload.target_success_rate,
        "metrics": evaluation["metrics"],
        "results": evaluation["results"],
        "holdout_metrics": (
            holdout_evaluation["metrics"] if holdout_evaluation is not None else None
        ),
        "holdout_results": (
            holdout_evaluation["results"] if holdout_evaluation is not None else []
        ),
        "prompt_suggestions": prompt_suggestions,
        "retrieval_tuning": effective_tuning,
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
    search_space_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Return available API category lists for all providers in the selected search space."""
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=search_space_id,
    )
    tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_index_for_search_space(
            session,
            user,
            search_space_id=resolved_search_space_id,
            metadata_patch=None,
        )
    )
    return _build_tool_api_categories_response(tool_index=tool_index)


@router.get(
    "/tool-settings/eval-history",
    response_model=ToolEvaluationStageHistoryResponse,
)
async def get_tool_eval_stage_history(
    stage: str,
    limit: int = 80,
    search_space_id: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=search_space_id,
    )
    return await _get_eval_stage_history(
        session,
        search_space_id=resolved_search_space_id,
        stage=stage,
        limit=limit,
    )


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


def _normalize_generation_eval_type(value: str | None) -> str:
    normalized_eval_type = str(value or "tool_selection").strip().lower()
    if normalized_eval_type in {"api", "api_input_eval"}:
        normalized_eval_type = "api_input"
    if normalized_eval_type not in {"tool_selection", "api_input"}:
        raise HTTPException(
            status_code=400,
            detail="eval_type must be either 'tool_selection' or 'api_input'",
        )
    return normalized_eval_type


def _normalize_generation_mode(value: str | None) -> str:
    normalized_mode = str(value or "category").strip().lower()
    if normalized_mode in {"random", "global", "global_mix"}:
        normalized_mode = "global_random"
    if normalized_mode in {"provider_mix", "provider_wide"}:
        normalized_mode = "provider"
    if normalized_mode not in {"category", "global_random", "provider"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be one of: 'category', 'provider', 'global_random'",
        )
    return normalized_mode


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
    normalized_eval_type = _normalize_generation_eval_type(payload.eval_type)
    normalized_mode = _normalize_generation_mode(payload.mode)
    question_count = max(1, min(int(payload.question_count or 12), 100))
    normalized_difficulty_profile = _normalize_difficulty_profile(
        payload.difficulty_profile
    )
    tool_registry, tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_registry_and_index_for_search_space(
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
        difficulty_profile=normalized_difficulty_profile,
    )
    if normalized_eval_type == "api_input":
        tests = _enrich_api_input_generated_tests(
            tests=tests,
            selected_entries=selected_entries,
            tool_registry=tool_registry,
        )
    if not tests:
        raise HTTPException(status_code=500, detail="Could not generate eval tests")
    default_eval_name = (
        f"{payload.provider_key or 'global'}-{payload.category_id or normalized_mode}"
    )
    eval_name = str(payload.eval_name or default_eval_name)
    eval_payload = _build_eval_library_payload(
        eval_type=normalized_eval_type,
        eval_name=eval_name,
        target_success_rate=payload.target_success_rate,
        difficulty_profile=normalized_difficulty_profile,
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
    result["comparison"] = await _build_stage_run_comparison(
        session,
        search_space_id=resolved_search_space_id,
        stage="tool",
        result=result,
        target_success_rate=payload.target_success_rate,
    )
    await _record_latest_eval_summary(
        session,
        search_space_id=resolved_search_space_id,
        result=result,
        updated_by_id=user.id,
    )
    await _record_eval_stage_summaries(
        session,
        search_space_id=resolved_search_space_id,
        result=result,
        stages=["agent", "tool"],
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
                            case["selected_route"] = event.get("selected_route")
                            case["selected_sub_route"] = event.get("selected_sub_route")
                            case["selected_agent"] = event.get("selected_agent")
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
            result["comparison"] = await _build_stage_run_comparison(
                job_session,
                search_space_id=resolved_search_space_id,
                stage="tool",
                result=result,
                target_success_rate=payload.target_success_rate,
            )
            await _record_latest_eval_summary(
                job_session,
                search_space_id=resolved_search_space_id,
                result=result,
                updated_by_id=job_user.id,
            )
            await _record_eval_stage_summaries(
                job_session,
                search_space_id=resolved_search_space_id,
                result=result,
                stages=["agent", "tool"],
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


def _snapshot_metadata_state(
    state: dict[str, ToolMetadataUpdateItem],
) -> dict[str, ToolMetadataUpdateItem]:
    return {tool_id: item.model_copy(deep=True) for tool_id, item in state.items()}


def _snapshot_prompt_state(state: dict[str, str]) -> dict[str, str]:
    return dict(state)


def _snapshot_tuning_state(state: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(state) if isinstance(state, dict) else None


def _build_metadata_update_item(
    *,
    tool_id: str,
    proposed_payload: dict[str, Any],
    defaults_by_tool: dict[str, dict[str, Any]],
) -> ToolMetadataUpdateItem:
    fallback = defaults_by_tool.get(tool_id) or {}

    def _coerce_string_list(value: Any, fallback_key: str) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                return cleaned
        fallback_values = fallback.get(fallback_key)
        if isinstance(fallback_values, list):
            return [str(item).strip() for item in fallback_values if str(item).strip()]
        return []

    return ToolMetadataUpdateItem(
        tool_id=tool_id,
        name=(
            str(proposed_payload.get("name") or fallback.get("name") or tool_id).strip()
            or tool_id
        ),
        description=(
            str(proposed_payload.get("description") or fallback.get("description") or "").strip()
        ),
        keywords=_coerce_string_list(proposed_payload.get("keywords"), "keywords"),
        example_queries=_coerce_string_list(
            proposed_payload.get("example_queries"),
            "example_queries",
        ),
        category=(
            str(
                proposed_payload.get("category")
                or fallback.get("category")
                or "general"
            ).strip()
            or "general"
        ),
        base_path=(
            str(
                proposed_payload.get("base_path")
                if proposed_payload.get("base_path") is not None
                else (fallback.get("base_path") or "")
            ).strip()
            or None
        ),
    )


def _merge_auto_loop_metadata_suggestions(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_tool_ids: set[str] = set()
    for source in (primary, secondary):
        for suggestion in source:
            if not isinstance(suggestion, dict):
                continue
            tool_id = str(suggestion.get("tool_id") or "").strip()
            if not tool_id or tool_id in seen_tool_ids:
                continue
            seen_tool_ids.add(tool_id)
            merged.append(suggestion)
    return merged


def _merge_auto_loop_prompt_suggestions(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_prompt_keys: set[str] = set()
    for source in (primary, secondary):
        for suggestion in source:
            if not isinstance(suggestion, dict):
                continue
            prompt_key = str(suggestion.get("prompt_key") or "").strip()
            if not prompt_key or prompt_key in seen_prompt_keys:
                continue
            seen_prompt_keys.add(prompt_key)
            merged.append(suggestion)
    return merged


async def _generate_auto_loop_suite(
    session: AsyncSession,
    user: User,
    *,
    search_space_id: int,
    generation,
    use_holdout_suite: bool = False,
    holdout_question_count: int = 8,
    holdout_difficulty_profile: str | None = None,
) -> tuple[
    dict[str, Any],
    list[ToolEvaluationTestCase],
    dict[str, Any] | None,
    list[ToolEvaluationTestCase],
    list[Any],
]:
    def _normalize_auto_loop_tests(
        tests_raw: list[dict[str, Any]],
        *,
        id_prefix: str,
    ) -> list[ToolEvaluationTestCase]:
        normalized: list[ToolEvaluationTestCase] = []
        for index, item in enumerate(tests_raw):
            if not isinstance(item, dict):
                continue
            candidate = dict(item)
            candidate["id"] = str(candidate.get("id") or f"{id_prefix}-{index + 1}")
            try:
                parsed_case = ToolEvaluationTestCase(**candidate)
            except Exception:
                continue
            if not str(parsed_case.question).strip():
                continue
            normalized.append(parsed_case)
        return normalized

    normalized_eval_type = _normalize_generation_eval_type(generation.eval_type)
    if normalized_eval_type != "tool_selection":
        raise HTTPException(
            status_code=400,
            detail="Auto-läge stöder för närvarande endast eval_type='tool_selection'",
        )
    normalized_mode = _normalize_generation_mode(generation.mode)
    normalized_difficulty_profile = _normalize_difficulty_profile(
        generation.difficulty_profile
    )
    question_count = max(1, min(int(generation.question_count or 12), 100))
    _tool_registry, tool_index, _persisted_overrides, _effective_overrides = (
        await _build_tool_registry_and_index_for_search_space(
            session,
            user,
            search_space_id=search_space_id,
            metadata_patch=None,
        )
    )
    pool = _select_generation_entries(
        tool_index=tool_index,
        mode=normalized_mode,
        provider_key=generation.provider_key,
        category_id=generation.category_id,
        question_count=question_count,
    )
    if not pool:
        raise HTTPException(status_code=404, detail="No tools available for eval generation")
    random.shuffle(pool)
    selected_entries = pool[: max(question_count, min(len(pool), 30))]
    llm = await get_agent_llm(session, search_space_id)
    tests = await _generate_eval_tests(
        llm=llm,
        selected_entries=selected_entries,
        question_count=question_count,
        include_allowed_tools=bool(generation.include_allowed_tools),
        difficulty_profile=normalized_difficulty_profile,
    )
    if not tests:
        raise HTTPException(status_code=500, detail="Could not generate eval tests")
    default_eval_name = (
        f"{generation.provider_key or 'global'}-{generation.category_id or normalized_mode}"
    )
    eval_name = str(generation.eval_name or default_eval_name).strip() or default_eval_name
    suite_payload = _build_eval_library_payload(
        eval_type=normalized_eval_type,
        eval_name=eval_name,
        target_success_rate=None,
        difficulty_profile=normalized_difficulty_profile,
        tests=tests,
    )
    normalized_tests = _normalize_auto_loop_tests(tests, id_prefix="case")
    if not normalized_tests:
        raise HTTPException(status_code=500, detail="Generated tests could not be normalized")

    holdout_suite_payload: dict[str, Any] | None = None
    normalized_holdout_tests: list[ToolEvaluationTestCase] = []
    if use_holdout_suite:
        normalized_holdout_count = max(1, min(int(holdout_question_count or 8), 100))
        normalized_holdout_profile = _normalize_difficulty_profile(
            holdout_difficulty_profile or normalized_difficulty_profile
        )
        holdout_tests = await _generate_eval_tests(
            llm=llm,
            selected_entries=selected_entries,
            question_count=normalized_holdout_count,
            include_allowed_tools=bool(generation.include_allowed_tools),
            difficulty_profile=normalized_holdout_profile,
        )
        if not holdout_tests:
            raise HTTPException(status_code=500, detail="Could not generate holdout tests")
        holdout_suite_payload = _build_eval_library_payload(
            eval_type=normalized_eval_type,
            eval_name=f"{eval_name}-holdout",
            target_success_rate=None,
            difficulty_profile=normalized_holdout_profile,
            tests=holdout_tests,
        )
        normalized_holdout_tests = _normalize_auto_loop_tests(
            holdout_tests,
            id_prefix="holdout",
        )
        if not normalized_holdout_tests:
            raise HTTPException(
                status_code=500,
                detail="Generated holdout tests could not be normalized",
            )
    return (
        suite_payload,
        normalized_tests,
        holdout_suite_payload,
        normalized_holdout_tests,
        tool_index,
    )


async def _run_tool_auto_loop_job_background(
    *,
    job_id: str,
    payload_data: dict[str, Any],
    user_id: Any,
) -> None:
    await _update_auto_loop_job(
        job_id,
        status="running",
        started_at=_utcnow_iso(),
        error=None,
        message="Initierar auto-loop",
    )
    try:
        async with async_session_maker() as job_session:
            payload = ToolAutoLoopRequest(**payload_data)
            user_result = await job_session.execute(select(User).filter(User.id == user_id))
            job_user = user_result.scalars().first()
            if job_user is None:
                raise RuntimeError("Auto-loop user context could not be loaded")
            _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
                job_session,
                job_user,
                requested_search_space_id=payload.search_space_id,
            )

            (
                suite_payload,
                generated_tests,
                holdout_suite_payload,
                generated_holdout_tests,
                generation_tool_index,
            ) = (
                await _generate_auto_loop_suite(
                    job_session,
                    job_user,
                    search_space_id=resolved_search_space_id,
                    generation=payload.generation,
                    use_holdout_suite=bool(payload.use_holdout_suite),
                    holdout_question_count=payload.holdout_question_count,
                    holdout_difficulty_profile=payload.holdout_difficulty_profile,
                )
            )
            holdout_enabled = bool(generated_holdout_tests)
            await _update_auto_loop_job(
                job_id,
                message=(
                    f"Generated suite with {len(generated_tests)} frågor"
                    + (
                        f" + holdout {len(generated_holdout_tests)}"
                        if holdout_enabled
                        else ""
                    )
                ),
            )

            defaults_by_tool = {
                str(entry.tool_id): _metadata_payload_from_entry(entry)
                for entry in generation_tool_index
                if str(getattr(entry, "tool_id", "")).strip()
            }
            metadata_state: dict[str, ToolMetadataUpdateItem] = {}
            prompt_state: dict[str, str] = {}
            prompt_details: dict[str, dict[str, Any]] = {}
            retrieval_state = normalize_tool_retrieval_tuning(
                await get_global_tool_retrieval_tuning(job_session)
            )

            best_metadata_state = _snapshot_metadata_state(metadata_state)
            best_prompt_state = _snapshot_prompt_state(prompt_state)
            best_retrieval_state = _snapshot_tuning_state(retrieval_state)
            best_success_rate = -1.0
            best_combined_score = -1.0
            best_iteration = 0
            best_result: dict[str, Any] | None = None
            best_holdout_result: dict[str, Any] | None = None
            previous_success_rate: float | None = None
            previous_holdout_success_rate: float | None = None
            previous_combined_score: float | None = None
            no_improvement_runs = 0
            stop_reason = "max_iterations_reached"
            holdout_weight = 0.35

            target_success_rate = max(
                0.0,
                min(1.0, float(payload.target_success_rate or 0.85)),
            )
            max_iterations = max(1, min(int(payload.max_iterations or 6), 30))
            patience = max(1, min(int(payload.patience or 2), 12))
            min_improvement_delta = max(
                0.0, min(float(payload.min_improvement_delta or 0.005), 0.25)
            )

            iteration_summaries: list[dict[str, Any]] = []

            for iteration in range(1, max_iterations + 1):
                await _update_auto_loop_job(
                    job_id,
                    current_iteration=iteration,
                    message=f"Kör iteration {iteration}/{max_iterations}",
                )
                iteration_metadata_state = _snapshot_metadata_state(metadata_state)
                iteration_prompt_state = _snapshot_prompt_state(prompt_state)
                iteration_retrieval_state = _snapshot_tuning_state(retrieval_state)

                iteration_payload = ToolEvaluationRequest(
                    eval_name=f"{suite_payload.get('eval_name') or 'auto-loop'} · iter {iteration}",
                    target_success_rate=target_success_rate,
                    search_space_id=resolved_search_space_id,
                    retrieval_limit=max(1, min(int(payload.retrieval_limit or 5), 15)),
                    use_llm_supervisor_review=bool(payload.use_llm_supervisor_review),
                    tests=generated_tests,
                    metadata_patch=list(iteration_metadata_state.values()),
                    retrieval_tuning_override=(
                        ToolRetrievalTuning(**iteration_retrieval_state)
                        if isinstance(iteration_retrieval_state, dict)
                        else None
                    ),
                )
                result = await _execute_tool_evaluation(
                    job_session,
                    job_user,
                    payload=iteration_payload,
                    resolved_search_space_id=resolved_search_space_id,
                    prompt_patch=iteration_prompt_state,
                    progress_callback=None,
                )
                result["comparison"] = await _build_stage_run_comparison(
                    job_session,
                    search_space_id=resolved_search_space_id,
                    stage="tool",
                    result=result,
                    target_success_rate=target_success_rate,
                )
                await _record_latest_eval_summary(
                    job_session,
                    search_space_id=resolved_search_space_id,
                    result=result,
                    updated_by_id=job_user.id,
                )
                await _record_eval_stage_summaries(
                    job_session,
                    search_space_id=resolved_search_space_id,
                    result=result,
                    stages=["agent", "tool"],
                    updated_by_id=job_user.id,
                )

                metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
                success_rate = _to_float(metrics.get("success_rate")) or 0.0
                gated_success_rate = _to_float(metrics.get("gated_success_rate"))
                total_tests = int(metrics.get("total_tests") or len(generated_tests))
                passed_tests = int(metrics.get("passed_tests") or 0)
                success_delta_vs_previous = (
                    None
                    if previous_success_rate is None
                    else success_rate - previous_success_rate
                )
                previous_success_rate = success_rate
                holdout_result: dict[str, Any] | None = None
                holdout_success_rate: float | None = None
                holdout_passed_tests: int | None = None
                holdout_total_tests: int | None = None
                holdout_delta_vs_previous: float | None = None
                if holdout_enabled and generated_holdout_tests:
                    holdout_payload = ToolEvaluationRequest(
                        eval_name=(
                            f"{holdout_suite_payload.get('eval_name') or 'auto-loop-holdout'} "
                            f"· iter {iteration}"
                        ),
                        target_success_rate=target_success_rate,
                        search_space_id=resolved_search_space_id,
                        retrieval_limit=max(1, min(int(payload.retrieval_limit or 5), 15)),
                        use_llm_supervisor_review=bool(payload.use_llm_supervisor_review),
                        tests=generated_holdout_tests,
                        metadata_patch=list(iteration_metadata_state.values()),
                        retrieval_tuning_override=(
                            ToolRetrievalTuning(**iteration_retrieval_state)
                            if isinstance(iteration_retrieval_state, dict)
                            else None
                        ),
                    )
                    holdout_result = await _execute_tool_evaluation(
                        job_session,
                        job_user,
                        payload=holdout_payload,
                        resolved_search_space_id=resolved_search_space_id,
                        prompt_patch=iteration_prompt_state,
                        progress_callback=None,
                    )
                    holdout_metrics = (
                        holdout_result.get("metrics")
                        if isinstance(holdout_result.get("metrics"), dict)
                        else {}
                    )
                    holdout_success_rate = _to_float(holdout_metrics.get("success_rate")) or 0.0
                    holdout_total_tests = int(
                        holdout_metrics.get("total_tests") or len(generated_holdout_tests)
                    )
                    holdout_passed_tests = int(holdout_metrics.get("passed_tests") or 0)
                    holdout_delta_vs_previous = (
                        None
                        if previous_holdout_success_rate is None
                        else holdout_success_rate - previous_holdout_success_rate
                    )
                    previous_holdout_success_rate = holdout_success_rate

                combined_score = (
                    success_rate
                    if holdout_success_rate is None
                    else ((1 - holdout_weight) * success_rate) + (holdout_weight * holdout_success_rate)
                )
                combined_delta_vs_previous = (
                    None
                    if previous_combined_score is None
                    else combined_score - previous_combined_score
                )
                previous_combined_score = combined_score

                improved = best_result is None or (
                    combined_score >= best_combined_score + min_improvement_delta
                )
                if improved:
                    best_success_rate = success_rate
                    best_combined_score = combined_score
                    best_iteration = iteration
                    best_result = result
                    best_holdout_result = holdout_result
                    best_metadata_state = _snapshot_metadata_state(iteration_metadata_state)
                    best_prompt_state = _snapshot_prompt_state(iteration_prompt_state)
                    best_retrieval_state = _snapshot_tuning_state(iteration_retrieval_state)
                    no_improvement_runs = 0
                else:
                    no_improvement_runs += 1

                metadata_changes_applied = 0
                prompt_changes_applied = 0
                retrieval_tuning_changed = False
                note: str | None = None

                holdout_target_reached = (
                    holdout_success_rate is None
                    or holdout_success_rate >= target_success_rate
                )
                if success_rate >= target_success_rate and holdout_target_reached:
                    stop_reason = "target_reached"
                    if holdout_success_rate is None:
                        note = (
                            f"Målnivå uppnådd: {(success_rate * 100):.1f}% "
                            f"(target {(target_success_rate * 100):.1f}%)."
                        )
                    else:
                        note = (
                            f"Målnivå uppnådd: train {(success_rate * 100):.1f}% "
                            f"och holdout {(holdout_success_rate * 100):.1f}% "
                            f"(target {(target_success_rate * 100):.1f}%)."
                        )
                else:
                    metadata_state = _snapshot_metadata_state(iteration_metadata_state)
                    prompt_state = _snapshot_prompt_state(iteration_prompt_state)
                    retrieval_state = _snapshot_tuning_state(iteration_retrieval_state)
                    metadata_suggestions = list(result.get("suggestions") or [])
                    prompt_suggestions = list(result.get("prompt_suggestions") or [])
                    retrieval_tuning_suggestion = result.get("retrieval_tuning_suggestion")

                    if holdout_result is not None:
                        metadata_suggestions = _merge_auto_loop_metadata_suggestions(
                            list(holdout_result.get("suggestions") or []),
                            metadata_suggestions,
                        )
                        prompt_suggestions = _merge_auto_loop_prompt_suggestions(
                            list(holdout_result.get("prompt_suggestions") or []),
                            prompt_suggestions,
                        )
                        holdout_tuning_suggestion = holdout_result.get(
                            "retrieval_tuning_suggestion"
                        )
                        if isinstance(holdout_tuning_suggestion, dict):
                            retrieval_tuning_suggestion = holdout_tuning_suggestion
                        if (
                            success_rate >= target_success_rate
                            and holdout_success_rate is not None
                            and holdout_success_rate < target_success_rate
                        ):
                            note = (
                                "Train-suite nådde mål men holdout är lägre. "
                                "Auto-läget prioriterar nu holdout-baserade förslag för bättre generalisering."
                            )
                        elif (
                            success_delta_vs_previous is not None
                            and success_delta_vs_previous > 0
                            and holdout_delta_vs_previous is not None
                            and holdout_delta_vs_previous < -min_improvement_delta
                        ):
                            note = (
                                "Möjlig överanpassning: train förbättrades men holdout försämrades. "
                                "Prioriterar holdout-fel i nästa förslagsrunda."
                            )

                    if payload.include_metadata_suggestions:
                        for suggestion in metadata_suggestions:
                            if not isinstance(suggestion, dict):
                                continue
                            tool_id = str(suggestion.get("tool_id") or "").strip()
                            proposed_payload = suggestion.get("proposed_metadata")
                            if not tool_id or not isinstance(proposed_payload, dict):
                                continue
                            candidate = _build_metadata_update_item(
                                tool_id=tool_id,
                                proposed_payload=proposed_payload,
                                defaults_by_tool=defaults_by_tool,
                            )
                            current_item = metadata_state.get(tool_id)
                            if (
                                current_item is None
                                or current_item.model_dump() != candidate.model_dump()
                            ):
                                metadata_state[tool_id] = candidate
                                metadata_changes_applied += 1

                    if payload.include_prompt_suggestions:
                        for suggestion in prompt_suggestions:
                            if not isinstance(suggestion, dict):
                                continue
                            prompt_key = str(suggestion.get("prompt_key") or "").strip()
                            proposed_prompt = str(
                                suggestion.get("proposed_prompt") or ""
                            ).strip()
                            if not prompt_key or not proposed_prompt:
                                continue
                            if not _is_valid_prompt_key(prompt_key):
                                continue
                            if prompt_state.get(prompt_key) != proposed_prompt:
                                prompt_state[prompt_key] = proposed_prompt
                                prompt_changes_applied += 1
                            prompt_details[prompt_key] = {
                                "prompt_key": prompt_key,
                                "proposed_prompt": proposed_prompt,
                                "rationale": (
                                    str(suggestion.get("rationale") or "").strip()
                                    or "Auto-loop: samlat promptutkast från eval-körningar."
                                ),
                                "related_tools": [
                                    str(item).strip()
                                    for item in list(suggestion.get("related_tools") or [])
                                    if str(item).strip()
                                ],
                            }

                    if payload.include_retrieval_tuning_suggestions:
                        if isinstance(retrieval_tuning_suggestion, dict) and isinstance(
                            retrieval_tuning_suggestion.get("proposed_tuning"),
                            dict,
                        ):
                            proposed_tuning = normalize_tool_retrieval_tuning(
                                retrieval_tuning_suggestion["proposed_tuning"]
                            )
                            current_tuning = normalize_tool_retrieval_tuning(
                                retrieval_state
                                if isinstance(retrieval_state, dict)
                                else {}
                            )
                            if proposed_tuning != current_tuning:
                                retrieval_state = proposed_tuning
                                retrieval_tuning_changed = True

                    if (
                        not improved
                        and best_result is not None
                        and best_combined_score >= 0
                        and combined_score <= (best_combined_score - min_improvement_delta)
                    ):
                        metadata_state = _snapshot_metadata_state(best_metadata_state)
                        prompt_state = _snapshot_prompt_state(best_prompt_state)
                        retrieval_state = _snapshot_tuning_state(best_retrieval_state)
                        note = (
                            "Backoff aktiverad: återställde till bästa kända utkast innan nästa iteration."
                        )

                    if no_improvement_runs >= patience:
                        stop_reason = "no_improvement"
                        if note:
                            note = (
                                f"{note} Stoppar loopen efter {no_improvement_runs} "
                                "körningar utan tydlig förbättring."
                            )
                        else:
                            note = (
                                f"Stoppar loopen efter {no_improvement_runs} körningar "
                                "utan tydlig förbättring."
                            )

                iteration_summary = ToolAutoLoopIterationSummary(
                    iteration=iteration,
                    success_rate=success_rate,
                    gated_success_rate=gated_success_rate,
                    passed_tests=passed_tests,
                    total_tests=total_tests,
                    success_delta_vs_previous=success_delta_vs_previous,
                    holdout_success_rate=holdout_success_rate,
                    holdout_passed_tests=holdout_passed_tests,
                    holdout_total_tests=holdout_total_tests,
                    holdout_delta_vs_previous=holdout_delta_vs_previous,
                    combined_score=combined_score,
                    combined_delta_vs_previous=combined_delta_vs_previous,
                    metadata_changes_applied=metadata_changes_applied,
                    prompt_changes_applied=prompt_changes_applied,
                    retrieval_tuning_changed=retrieval_tuning_changed,
                    note=note,
                ).model_dump()
                iteration_summaries.append(iteration_summary)
                await _update_auto_loop_job(
                    job_id,
                    completed_iterations=iteration,
                    best_success_rate=best_success_rate if best_success_rate >= 0 else None,
                    no_improvement_runs=no_improvement_runs,
                    iterations=iteration_summaries,
                    message=note or f"Iteration {iteration} klar",
                )

                if stop_reason in {"target_reached", "no_improvement"}:
                    break

            if best_result is None:
                raise RuntimeError("Auto-loop completed without a valid evaluation result")

            ordered_metadata_patch = [
                best_metadata_state[tool_id].model_dump()
                for tool_id in sorted(best_metadata_state.keys())
            ]
            ordered_prompt_patch: list[dict[str, Any]] = []
            for prompt_key in sorted(best_prompt_state.keys()):
                detail = prompt_details.get(prompt_key) or {}
                ordered_prompt_patch.append(
                    ToolAutoLoopDraftPromptItem(
                        prompt_key=prompt_key,
                        proposed_prompt=best_prompt_state[prompt_key],
                        rationale=(
                            str(detail.get("rationale") or "").strip()
                            or "Auto-loop: samlat promptutkast."
                        ),
                        related_tools=[
                            str(item).strip()
                            for item in list(detail.get("related_tools") or [])
                            if str(item).strip()
                        ],
                    ).model_dump()
                )
            final_result = ToolAutoLoopResult(
                status="completed",
                stop_reason=stop_reason,
                target_success_rate=target_success_rate,
                best_success_rate=max(0.0, best_success_rate),
                best_iteration=best_iteration,
                no_improvement_runs=no_improvement_runs,
                generated_suite=suite_payload,
                generated_holdout_suite=holdout_suite_payload,
                iterations=iteration_summaries,
                final_evaluation=ToolEvaluationResponse(**best_result),
                final_holdout_evaluation=(
                    ToolEvaluationResponse(**best_holdout_result)
                    if isinstance(best_holdout_result, dict)
                    else None
                ),
                draft_changes={
                    "metadata_patch": ordered_metadata_patch,
                    "prompt_patch": ordered_prompt_patch,
                    "retrieval_tuning_override": (
                        ToolRetrievalTuning(**best_retrieval_state)
                        if isinstance(best_retrieval_state, dict)
                        else None
                    ),
                },
            ).model_dump()
            await _update_auto_loop_job(
                job_id,
                status="completed",
                completed_at=_utcnow_iso(),
                current_iteration=int(final_result.get("best_iteration") or 0),
                completed_iterations=len(iteration_summaries),
                message="Auto-loop slutförd",
                result=final_result,
            )
    except Exception as exc:
        logger.exception("Tool auto-loop job failed")
        await _update_auto_loop_job(
            job_id,
            status="failed",
            completed_at=_utcnow_iso(),
            error=str(exc),
            message="Auto-loop misslyckades",
        )


@router.post(
    "/tool-settings/evaluate-auto-loop/start",
    response_model=ToolAutoLoopStartResponse,
)
async def start_tool_auto_loop(
    payload: ToolAutoLoopRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    _owned_ids, resolved_search_space_id = await _resolve_search_space_id(
        session,
        user,
        requested_search_space_id=payload.search_space_id,
    )
    normalized_eval_type = _normalize_generation_eval_type(payload.generation.eval_type)
    if normalized_eval_type != "tool_selection":
        raise HTTPException(
            status_code=400,
            detail="Auto-läge stöder för närvarande endast eval_type='tool_selection'",
        )
    _normalize_generation_mode(payload.generation.mode)
    normalized_target = max(0.0, min(1.0, float(payload.target_success_rate or 0.85)))
    normalized_iterations = max(1, min(int(payload.max_iterations or 6), 30))
    normalized_patience = max(1, min(int(payload.patience or 2), 12))
    normalized_delta = max(0.0, min(float(payload.min_improvement_delta or 0.005), 0.25))
    normalized_use_holdout = bool(payload.use_holdout_suite)
    normalized_holdout_count = max(1, min(int(payload.holdout_question_count or 8), 100))
    normalized_holdout_profile = (
        _normalize_difficulty_profile(payload.holdout_difficulty_profile)
        if payload.holdout_difficulty_profile
        else None
    )
    normalized_payload = payload.model_copy(
        update={
            "search_space_id": resolved_search_space_id,
            "use_holdout_suite": normalized_use_holdout,
            "holdout_question_count": normalized_holdout_count,
            "holdout_difficulty_profile": normalized_holdout_profile,
            "target_success_rate": normalized_target,
            "max_iterations": normalized_iterations,
            "patience": normalized_patience,
            "min_improvement_delta": normalized_delta,
            "generation": payload.generation.model_copy(
                update={"eval_type": normalized_eval_type}
            ),
        }
    )
    job_id = uuid4().hex
    job_payload = {
        "job_id": job_id,
        "status": "pending",
        "total_iterations": normalized_iterations,
        "completed_iterations": 0,
        "started_at": None,
        "completed_at": None,
        "updated_at": _utcnow_iso(),
        "created_at": _utcnow_iso(),
        "current_iteration": 0,
        "best_success_rate": None,
        "no_improvement_runs": 0,
        "message": "Väntar på start",
        "iterations": [],
        "result": None,
        "error": None,
    }
    async with _AUTO_LOOP_JOBS_LOCK:
        _AUTO_LOOP_JOBS[job_id] = job_payload
        await _prune_auto_loop_jobs()
    asyncio.create_task(
        _run_tool_auto_loop_job_background(
            job_id=job_id,
            payload_data=normalized_payload.model_dump(),
            user_id=user.id,
        )
    )
    return {
        "job_id": job_id,
        "status": "pending",
        "total_iterations": normalized_iterations,
        "target_success_rate": normalized_target,
    }


@router.get(
    "/tool-settings/evaluate-auto-loop/{job_id}",
    response_model=ToolAutoLoopJobStatusResponse,
)
async def get_tool_auto_loop_status(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    async with _AUTO_LOOP_JOBS_LOCK:
        job = _AUTO_LOOP_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Auto-loop job not found")
        return _serialize_auto_loop_job(job)


@router.post(
    "/tool-settings/evaluate-api-input",
    response_model=ToolApiInputEvaluationResponse,
)
async def evaluate_tool_api_input(
    payload: ToolApiInputEvaluationRequest,
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
    result = await _execute_api_input_evaluation(
        session,
        user,
        payload=payload,
        resolved_search_space_id=resolved_search_space_id,
    )
    result["comparison"] = await _build_stage_run_comparison(
        session,
        search_space_id=resolved_search_space_id,
        stage="api_input",
        result=result,
        target_success_rate=payload.target_success_rate,
    )
    await _record_latest_eval_summary(
        session,
        search_space_id=resolved_search_space_id,
        result=result,
        updated_by_id=user.id,
    )
    await _record_eval_stage_summaries(
        session,
        search_space_id=resolved_search_space_id,
        result=result,
        stages=["api_input"],
        updated_by_id=user.id,
    )
    return result


async def _run_api_input_eval_job_background(
    *,
    job_id: str,
    payload_data: dict[str, Any],
    user_id: Any,
) -> None:
    await _update_api_input_eval_job(
        job_id,
        status="running",
        started_at=_utcnow_iso(),
        error=None,
    )
    try:
        async with async_session_maker() as job_session:
            payload = ToolApiInputEvaluationRequest(**payload_data)
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
                async with _API_INPUT_EVAL_JOBS_LOCK:
                    job = _API_INPUT_EVAL_JOBS.get(job_id)
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
                            case["selected_route"] = event.get("selected_route")
                            case["selected_sub_route"] = event.get("selected_sub_route")
                            case["selected_agent"] = event.get("selected_agent")
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

            result = await _execute_api_input_evaluation(
                job_session,
                job_user,
                payload=payload,
                resolved_search_space_id=resolved_search_space_id,
                progress_callback=_progress_callback,
            )
            result["comparison"] = await _build_stage_run_comparison(
                job_session,
                search_space_id=resolved_search_space_id,
                stage="api_input",
                result=result,
                target_success_rate=payload.target_success_rate,
            )
            await _record_latest_eval_summary(
                job_session,
                search_space_id=resolved_search_space_id,
                result=result,
                updated_by_id=job_user.id,
            )
            await _record_eval_stage_summaries(
                job_session,
                search_space_id=resolved_search_space_id,
                result=result,
                stages=["api_input"],
                updated_by_id=job_user.id,
            )
            await _update_api_input_eval_job(
                job_id,
                status="completed",
                completed_at=_utcnow_iso(),
                completed_tests=len(payload.tests),
                result=result,
            )
    except Exception as exc:
        logger.exception("Tool API input evaluation job failed")
        await _update_api_input_eval_job(
            job_id,
            status="failed",
            completed_at=_utcnow_iso(),
            error=str(exc),
        )


@router.post(
    "/tool-settings/evaluate-api-input/start",
    response_model=ToolApiInputEvaluationStartResponse,
)
async def start_tool_api_input_evaluation(
    payload: ToolApiInputEvaluationRequest,
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
    async with _API_INPUT_EVAL_JOBS_LOCK:
        _API_INPUT_EVAL_JOBS[job_id] = job_payload
        await _prune_api_input_eval_jobs()
    asyncio.create_task(
        _run_api_input_eval_job_background(
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
    "/tool-settings/evaluate-api-input/{job_id}",
    response_model=ToolApiInputEvaluationJobStatusResponse,
)
async def get_tool_api_input_evaluation_status(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    async with _API_INPUT_EVAL_JOBS_LOCK:
        job = _API_INPUT_EVAL_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Evaluation job not found")
        return _serialize_api_input_eval_job(job)


@router.post(
    "/tool-settings/evaluate-api-input/apply-prompt-suggestions",
    response_model=ToolApiInputApplyPromptSuggestionsResponse,
)
async def apply_api_input_prompt_suggestions(
    payload: ToolApiInputApplyPromptSuggestionsRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await _require_admin(session, user)
    if not payload.suggestions:
        raise HTTPException(status_code=400, detail="No prompt suggestions to apply")
    updates: list[tuple[str, str | None]] = []
    for suggestion in payload.suggestions:
        prompt_key = str(suggestion.prompt_key or "").strip()
        if not _is_valid_prompt_key(prompt_key):
            raise HTTPException(status_code=400, detail=f"Unknown prompt key: {prompt_key}")
        proposed_prompt = str(suggestion.proposed_prompt or "").strip()
        updates.append((prompt_key, proposed_prompt if proposed_prompt else None))
    try:
        await upsert_global_prompt_overrides(
            session,
            updates,
            updated_by_id=user.id,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to apply API input prompt suggestions")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply API input prompt suggestions: {exc!s}",
        ) from exc
    return {
        "applied_prompt_keys": [item[0] for item in updates],
    }


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
