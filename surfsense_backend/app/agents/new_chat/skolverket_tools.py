from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.connector_service import ConnectorService
from app.services.skolverket_service import SkolverketApiError, SkolverketService


@dataclass(frozen=True)
class SkolverketToolDefinition:
    tool_id: str
    name: str
    category: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    input_schema: dict[str, Any]


def _schema(
    properties: dict[str, str],
    *,
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {key: {"type": value} for key, value in properties.items()},
        "required": list(required),
    }


def _def(
    tool_id: str,
    *,
    category: str,
    description: str,
    keywords: list[str],
    example: str,
    schema: dict[str, Any],
) -> SkolverketToolDefinition:
    return SkolverketToolDefinition(
        tool_id=tool_id,
        name=tool_id.replace("_", " ").title(),
        category=category,
        description=description,
        keywords=keywords,
        example_queries=[example],
        input_schema=schema,
    )


SKOLVERKET_TOOL_DEFINITIONS: list[SkolverketToolDefinition] = [
    # Syllabus API
    _def(
        "search_subjects",
        category="knowledge",
        description="Search syllabus subjects by school type and timespan.",
        keywords=["skolverket", "subject", "syllabus", "curriculum", "amne"],
        example="Search subjects for school type GY.",
        schema=_schema(
            {
                "schooltype": "string",
                "timespan": "string",
                "typeOfSyllabus": "string",
                "date": "string",
                "limit": "number",
            }
        ),
    ),
    _def(
        "get_subject_details",
        category="knowledge",
        description="Get full details for one subject code.",
        keywords=["subject", "details", "syllabus", "skolverket", "code"],
        example="Get details for subject code MAT.",
        schema=_schema({"code": "string", "version": "number", "date": "string"}, required=("code",)),
    ),
    _def(
        "get_subject_versions",
        category="knowledge",
        description="List all versions for one subject code.",
        keywords=["subject", "versions", "history", "skolverket"],
        example="List versions for subject MAT.",
        schema=_schema({"code": "string"}, required=("code",)),
    ),
    _def(
        "search_courses",
        category="knowledge",
        description="Search syllabus courses with optional filters.",
        keywords=["course", "kurs", "syllabus", "skolverket"],
        example="Search courses in GY for latest timespan.",
        schema=_schema(
            {
                "schooltype": "string",
                "timespan": "string",
                "date": "string",
                "subjectCode": "string",
                "limit": "number",
            }
        ),
    ),
    _def(
        "get_course_details",
        category="knowledge",
        description="Get full details for one course code.",
        keywords=["course", "details", "curriculum", "skolverket"],
        example="Get details for MATMAT01c.",
        schema=_schema({"code": "string", "version": "number", "date": "string"}, required=("code",)),
    ),
    _def(
        "get_course_versions",
        category="knowledge",
        description="List all versions for one course code.",
        keywords=["course", "versions", "history", "skolverket"],
        example="List versions for MATMAT01c.",
        schema=_schema({"code": "string"}, required=("code",)),
    ),
    _def(
        "search_programs",
        category="knowledge",
        description="Search programs and study paths.",
        keywords=["program", "study path", "gymnasium", "skolverket"],
        example="Search latest programs for school type GY.",
        schema=_schema(
            {
                "schooltype": "string",
                "timespan": "string",
                "date": "string",
                "typeOfStudyPath": "string",
                "limit": "number",
            }
        ),
    ),
    _def(
        "get_program_details",
        category="knowledge",
        description="Get full details for one program code.",
        keywords=["program", "details", "study path", "skolverket"],
        example="Get program details for NA.",
        schema=_schema({"code": "string", "version": "number", "date": "string"}, required=("code",)),
    ),
    _def(
        "get_program_versions",
        category="knowledge",
        description="List all versions for one program code.",
        keywords=["program", "versions", "history", "skolverket"],
        example="List versions for NA.",
        schema=_schema({"code": "string"}, required=("code",)),
    ),
    _def(
        "search_curriculums",
        category="knowledge",
        description="Search curriculums and policy docs.",
        keywords=["curriculum", "laroplan", "skolverket"],
        example="Search latest curriculums.",
        schema=_schema({"schooltype": "string", "timespan": "string", "date": "string"}),
    ),
    _def(
        "get_curriculum_details",
        category="knowledge",
        description="Get full details for one curriculum code.",
        keywords=["curriculum", "details", "laroplan", "skolverket"],
        example="Get curriculum details for GY2011.",
        schema=_schema({"code": "string", "version": "number", "date": "string"}, required=("code",)),
    ),
    _def(
        "get_curriculum_versions",
        category="knowledge",
        description="List all versions for one curriculum code.",
        keywords=["curriculum", "versions", "history", "skolverket"],
        example="List versions for GY2011.",
        schema=_schema({"code": "string"}, required=("code",)),
    ),
    _def(
        "get_school_types",
        category="knowledge",
        description="Get syllabus school types.",
        keywords=["school types", "skoltyper", "valuestore"],
        example="Get all school types.",
        schema=_schema({"includeExpired": "boolean"}),
    ),
    _def(
        "get_types_of_syllabus",
        category="knowledge",
        description="Get syllabus types.",
        keywords=["types", "syllabus", "curriculum"],
        example="Get types of syllabus.",
        schema=_schema({}),
    ),
    _def(
        "get_subject_and_course_codes",
        category="knowledge",
        description="Get all subject and course codes.",
        keywords=["subject code", "course code", "valuestore"],
        example="Get all course and subject codes.",
        schema=_schema({}),
    ),
    _def(
        "get_study_path_codes",
        category="knowledge",
        description="Get study path codes.",
        keywords=["study path", "program code", "valuestore"],
        example="Get study path codes for programs.",
        schema=_schema(
            {
                "schooltype": "string",
                "timespan": "string",
                "date": "string",
                "typeOfStudyPath": "string",
                "typeOfProgram": "string",
                "type": "string",
            }
        ),
    ),
    _def(
        "get_api_info",
        category="knowledge",
        description="Get syllabus API info metadata.",
        keywords=["api info", "syllabus", "skolverket"],
        example="Get API info.",
        schema=_schema({}),
    ),
    # School units API
    _def(
        "search_school_units",
        category="knowledge",
        description="Search school units in the school units register.",
        keywords=["school unit", "skolenhet", "register", "status"],
        example="Search active school units.",
        schema=_schema({"name": "string", "status": "string", "limit": "number"}),
    ),
    _def(
        "get_school_unit_details",
        category="knowledge",
        description="Get details for one school unit code.",
        keywords=["school unit", "details", "code", "skolenhet"],
        example="Get details for school unit code 69405762.",
        schema=_schema({"code": "string"}, required=("code",)),
    ),
    _def(
        "get_school_units_by_status",
        category="knowledge",
        description="List school units by status.",
        keywords=["school unit", "status", "active", "register"],
        example="List school units with status AKTIV.",
        schema=_schema({"status": "string", "limit": "number"}, required=("status",)),
    ),
    _def(
        "search_school_units_by_name",
        category="knowledge",
        description="Search school units by name.",
        keywords=["school unit", "name", "search", "skolenhet"],
        example="Search school units by name Uppsala.",
        schema=_schema({"name": "string", "limit": "number"}, required=("name",)),
    ),
    # Adult and planned education
    _def(
        "search_adult_education",
        category="knowledge",
        description="Search adult education events.",
        keywords=["adult education", "komvux", "sfi", "yh", "skolverket"],
        example="Search SFI in Uppsala.",
        schema=_schema(
            {
                "searchTerm": "string",
                "town": "string",
                "municipality": "string",
                "county": "string",
                "typeOfSchool": "string",
                "distance": "string",
                "paceOfStudy": "string",
                "semesterStartFrom": "string",
                "page": "number",
                "size": "number",
            }
        ),
    ),
    _def(
        "get_adult_education_details",
        category="knowledge",
        description="Get one adult education event by id.",
        keywords=["adult education", "details", "event id"],
        example="Get adult education details by id.",
        schema=_schema({"id": "string"}, required=("id",)),
    ),
    _def(
        "filter_adult_education_by_distance",
        category="knowledge",
        description="Filter adult education by distance/campus mode.",
        keywords=["adult education", "distance", "campus"],
        example="Filter adult education for distance=true.",
        schema=_schema({"distance": "boolean", "searchTerm": "string", "page": "number", "size": "number"}, required=("distance",)),
    ),
    _def(
        "filter_adult_education_by_pace",
        category="knowledge",
        description="Filter adult education by pace of study.",
        keywords=["adult education", "pace", "study pace"],
        example="Filter adult education with pace 50.",
        schema=_schema({"paceOfStudy": "string", "searchTerm": "string", "page": "number", "size": "number"}, required=("paceOfStudy",)),
    ),
    _def(
        "get_education_areas",
        category="knowledge",
        description="Get adult education support areas from v3.",
        keywords=["education areas", "support data", "adult"],
        example="Get education areas.",
        schema=_schema({}),
    ),
    _def(
        "get_directions",
        category="knowledge",
        description="Get directions/program support data from v3.",
        keywords=["directions", "support data", "programs"],
        example="Get directions.",
        schema=_schema({}),
    ),
    _def(
        "search_education_events",
        category="knowledge",
        description="Search education events in v4 with fallback client-side filtering.",
        keywords=["education events", "program", "school unit", "v4"],
        example="Search education events with searchTerm teknik.",
        schema=_schema(
            {
                "schoolUnitCode": "string",
                "typeOfSchool": "string",
                "municipality": "string",
                "county": "string",
                "distance": "boolean",
                "programCode": "string",
                "searchTerm": "string",
                "limit": "number",
                "page": "number",
                "size": "number",
                "maxPages": "number",
            }
        ),
    ),
    _def(
        "count_education_events",
        category="statistics",
        description="Count education events with fallback client-side filtering.",
        keywords=["count", "education events", "statistics"],
        example="Count education events for typeOfSchool gy.",
        schema=_schema(
            {
                "typeOfSchool": "string",
                "municipality": "string",
                "county": "string",
                "programCode": "string",
                "distance": "boolean",
                "searchTerm": "string",
                "schoolUnitCode": "string",
            }
        ),
    ),
    _def(
        "count_adult_education_events",
        category="statistics",
        description="Count adult education events using robust v3 fallback.",
        keywords=["count", "adult education", "statistics", "sfi"],
        example="Count adult education events for SFI.",
        schema=_schema(
            {
                "typeOfSchool": "string",
                "municipality": "string",
                "county": "string",
                "distance": "string",
                "searchTerm": "string",
                "town": "string",
                "paceOfStudy": "string",
            }
        ),
    ),
    _def(
        "get_adult_education_areas_v4",
        category="knowledge",
        description="Get v4 adult education areas.",
        keywords=["adult", "areas", "v4", "support"],
        example="Get adult education areas v4.",
        schema=_schema({}),
    ),
    _def(
        "search_school_units_v4",
        category="knowledge",
        description="Search school units in planned-educations v4.",
        keywords=["school units v4", "search", "planned education"],
        example="Search school units v4 by name Uppsala.",
        schema=_schema(
            {
                "name": "string",
                "municipality": "string",
                "county": "string",
                "typeOfSchool": "string",
                "status": "string",
                "principalOrganizer": "string",
                "limit": "number",
                "page": "number",
                "size": "number",
                "maxPages": "number",
            }
        ),
    ),
    _def(
        "get_school_unit_education_events",
        category="knowledge",
        description="Get education events for one school unit code.",
        keywords=["school unit", "education events", "program"],
        example="Get school unit education events for 69405762.",
        schema=_schema({"code": "string", "programCode": "string", "limit": "number"}, required=("code",)),
    ),
    _def(
        "get_school_types_v4",
        category="knowledge",
        description="Get v4 school types support data.",
        keywords=["school types", "v4", "support"],
        example="Get school types v4.",
        schema=_schema({}),
    ),
    _def(
        "get_geographical_areas_v4",
        category="knowledge",
        description="Get v4 geographical areas support data.",
        keywords=["geographical areas", "v4", "support"],
        example="Get geographical areas v4.",
        schema=_schema({}),
    ),
    _def(
        "get_programs_v4",
        category="knowledge",
        description="Get v4 programs support data.",
        keywords=["programs", "v4", "support"],
        example="Get programs v4.",
        schema=_schema({}),
    ),
    _def(
        "get_school_unit_documents",
        category="knowledge",
        description="Get school documents for one school unit code.",
        keywords=["documents", "school unit", "inspection"],
        example="Get documents for school unit 69405762.",
        schema=_schema({"code": "string", "typeOfSchooling": "string", "limit": "number"}, required=("code",)),
    ),
    _def(
        "get_school_unit_statistics",
        category="statistics",
        description="Get school unit statistics for one school type.",
        keywords=["statistics", "school unit", "national values"],
        example="Get school unit statistics for code 69405762 and schoolType gr.",
        schema=_schema({"code": "string", "schoolType": "string", "year": "string"}, required=("code", "schoolType")),
    ),
    _def(
        "get_national_statistics",
        category="statistics",
        description="Get national statistics by school type.",
        keywords=["national statistics", "school type", "skolverket"],
        example="Get national statistics for schoolType gr.",
        schema=_schema({"schoolType": "string", "year": "string", "programCode": "string"}, required=("schoolType",)),
    ),
    _def(
        "get_program_statistics",
        category="statistics",
        description="Get per-program statistics with fallback aggregation.",
        keywords=["program statistics", "gy", "gyan", "counts"],
        example="Get program statistics for schoolType gy.",
        schema=_schema({"schoolType": "string", "year": "string"}, required=("schoolType",)),
    ),
    _def(
        "health_check",
        category="general",
        description="Run a health check for syllabus, school units and planned APIs.",
        keywords=["health", "diagnostics", "status", "latency"],
        example="Run health_check with includeApiTests=true.",
        schema=_schema({"includeApiTests": "boolean"}),
    ),
]


def _create_dynamic_input_model_from_schema(
    tool_name: str,
    input_schema: dict[str, Any],
) -> type[BaseModel]:
    properties = input_schema.get("properties", {})
    required_fields = set(input_schema.get("required", []))

    field_definitions: dict[str, Any] = {}
    for param_name, param_schema in properties.items():
        param_type = str(param_schema.get("type") or "string").strip().lower()
        description = str(param_schema.get("description") or "")
        if param_type == "number":
            py_type = float
        elif param_type == "integer":
            py_type = int
        elif param_type == "boolean":
            py_type = bool
        elif param_type == "array":
            py_type = list[Any]
        elif param_type == "object":
            py_type = dict[str, Any]
        else:
            py_type = str

        if param_name in required_fields:
            field_definitions[param_name] = (py_type, Field(..., description=description))
        else:
            field_definitions[param_name] = (py_type | None, Field(None, description=description))

    model_name = f"{tool_name.replace('-', '_').replace(' ', '_').title()}Input"
    return create_model(model_name, **field_definitions)


def _pick(arguments: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: arguments.get(key) for key in keys if arguments.get(key) is not None}


def _normalize_text(text: Any) -> str:
    value = str(text or "").strip().lower()
    return (
        value.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
        .strip()
    )


def _as_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _normalize_text(value)
    if text in {"true", "1", "yes", "ja"}:
        return True
    if text in {"false", "0", "no", "nej"}:
        return False
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_embedded_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    embedded = payload.get("_embedded")
    if not isinstance(embedded, dict):
        return []
    data = embedded.get(key)
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _safe_json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value)


def _match_text(candidate: Any, query: str) -> bool:
    query_norm = _normalize_text(query)
    if not query_norm:
        return True
    candidate_norm = _normalize_text(_safe_json_text(candidate))
    return query_norm in candidate_norm


def _filter_school_units_v4(
    units: list[dict[str, Any]],
    arguments: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    municipality = _as_str(arguments.get("municipality"))
    county = _as_str(arguments.get("county"))
    type_of_school = _as_str(arguments.get("typeOfSchool"))
    status = _as_str(arguments.get("status"))
    principal = _as_str(arguments.get("principalOrganizer"))

    warnings: list[str] = []
    filtered: list[dict[str, Any]] = []
    for unit in units:
        if municipality and not _match_text(
            f"{unit.get('postCodeDistrict', '')} {unit.get('name', '')}",
            municipality,
        ):
            continue
        if county and not _match_text(unit, county):
            continue
        if type_of_school:
            school_types = unit.get("typeOfSchooling")
            if isinstance(school_types, list):
                combined = " ".join(
                    f"{item.get('code', '')} {item.get('displayName', '')}"
                    for item in school_types
                    if isinstance(item, dict)
                )
                if not _match_text(combined, type_of_school):
                    continue
            elif not _match_text(unit, type_of_school):
                continue
        if status:
            status_value = unit.get("status")
            if status_value is None:
                warnings.append("status filter used, but status is not consistently exposed in this endpoint.")
            elif not _match_text(status_value, status):
                continue
        if principal and not _match_text(unit, principal):
            continue
        filtered.append(unit)
    return filtered, list(dict.fromkeys(warnings))


def _filter_education_events(
    events: list[dict[str, Any]],
    arguments: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    school_unit_code = _as_str(arguments.get("schoolUnitCode"))
    type_of_school = _as_str(arguments.get("typeOfSchool"))
    municipality = _as_str(arguments.get("municipality"))
    county = _as_str(arguments.get("county"))
    program_code = _as_str(arguments.get("programCode"))
    distance = _as_bool(arguments.get("distance"))
    search_term = _as_str(arguments.get("searchTerm"))

    warnings: list[str] = []
    filtered: list[dict[str, Any]] = []

    for event in events:
        if school_unit_code and str(event.get("schoolUnitCode") or "") != school_unit_code:
            continue
        if type_of_school:
            school_type = event.get("typeOfSchooling") or {}
            combined = ""
            if isinstance(school_type, dict):
                combined = f"{school_type.get('code', '')} {school_type.get('displayName', '')}"
            if not _match_text(combined, type_of_school):
                continue
        if municipality and not _match_text(event.get("visitingAddressCity") or "", municipality):
            continue
        if county:
            # v4 education-events currently does not expose county in stable fields.
            if not _match_text(event, county):
                continue
        if program_code:
            study_path = str(event.get("studyPathCode") or "")
            if not (study_path == program_code or study_path.startswith(program_code)):
                continue
        if search_term and not _match_text(event, search_term):
            continue
        if distance is not None:
            warnings.append("distance filter is not exposed in v4 education-events; filter cannot be enforced exactly.")
        filtered.append(event)
    return filtered, list(dict.fromkeys(warnings))


async def _fetch_v4_education_events(
    service: SkolverketService,
    arguments: dict[str, Any],
    *,
    include_filters: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    page_size = _as_int(arguments.get("size"), 200, min_value=1, max_value=200)
    max_pages = _as_int(arguments.get("maxPages"), 6, min_value=1, max_value=20)
    name_param = _as_str(arguments.get("searchTerm")) or _as_str(arguments.get("name"))

    base_params: dict[str, Any] = {}
    if name_param:
        base_params["name"] = name_param

    pages = await service.iter_planned_v4_pages(
        "/v4/education-events",
        base_params=base_params,
        max_pages=max_pages,
        size=page_size,
    )
    events: list[dict[str, Any]] = []
    page_info: dict[str, Any] = {}
    for body in pages:
        if isinstance(body, dict):
            page_info = body.get("page") if isinstance(body.get("page"), dict) else page_info
            events.extend(_get_embedded_list(body, "educationEvents"))

    warnings: list[str] = []
    if include_filters:
        events, filter_warnings = _filter_education_events(events, arguments)
        warnings.extend(filter_warnings)
    if len(pages) >= max_pages:
        warnings.append("Result set truncated to maxPages while collecting v4 education-events.")
    return events, page_info, list(dict.fromkeys(warnings))


def _normalize_school_type(value: Any) -> str:
    normalized = _normalize_text(value)
    aliases = {
        "forskoleklass": "fsk",
        "grundskola": "gr",
        "grundsarskola": "gran",
        "gymnasium": "gy",
        "gymnasiesarskola": "gyan",
    }
    return aliases.get(normalized, normalized)


async def _execute_tool(
    definition: SkolverketToolDefinition,
    arguments: dict[str, Any],
    *,
    service: SkolverketService,
) -> dict[str, Any]:
    tool_id = definition.tool_id

    if tool_id == "search_subjects":
        params = _pick(arguments, ("schooltype", "timespan", "typeOfSyllabus", "date"))
        data = await service.syllabus_get("/v1/subjects", params=params or None)
        subjects = [item for item in (data.get("subjects") or []) if isinstance(item, dict)]
        limit = _as_int(arguments.get("limit"), 50, min_value=1, max_value=200)
        subjects = subjects[:limit]
        return {
            "totalElements": data.get("totalElements", len(subjects)),
            "returned": len(subjects),
            "subjects": subjects,
        }

    if tool_id == "get_subject_details":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        version = arguments.get("version")
        date = _as_str(arguments.get("date"))
        if version is not None:
            path = f"/v1/subjects/{code}/versions/{version}"
        else:
            path = f"/v1/subjects/{code}"
        params = {"date": date} if date else None
        return await service.syllabus_get(path, params=params)

    if tool_id == "get_subject_versions":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        return await service.syllabus_get(f"/v1/subjects/{code}/versions")

    if tool_id == "search_courses":
        params = _pick(arguments, ("schooltype", "timespan", "date", "subjectCode"))
        data = await service.syllabus_get("/v1/courses", params=params or None)
        courses = [item for item in (data.get("courses") or []) if isinstance(item, dict)]
        limit = _as_int(arguments.get("limit"), 50, min_value=1, max_value=200)
        courses = courses[:limit]
        return {
            "totalElements": data.get("totalElements", len(courses)),
            "returned": len(courses),
            "courses": courses,
        }

    if tool_id == "get_course_details":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        version = arguments.get("version")
        date = _as_str(arguments.get("date"))
        path = f"/v1/courses/{code}/versions/{version}" if version is not None else f"/v1/courses/{code}"
        params = {"date": date} if date else None
        return await service.syllabus_get(path, params=params)

    if tool_id == "get_course_versions":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        return await service.syllabus_get(f"/v1/courses/{code}/versions")

    if tool_id == "search_programs":
        params = _pick(arguments, ("schooltype", "timespan", "date", "typeOfStudyPath"))
        data = await service.syllabus_get("/v1/programs", params=params or None)
        programs = [item for item in (data.get("programs") or []) if isinstance(item, dict)]
        limit = _as_int(arguments.get("limit"), 100, min_value=1, max_value=200)
        programs = programs[:limit]
        return {
            "totalElements": data.get("totalElements", len(programs)),
            "returned": len(programs),
            "programs": programs,
        }

    if tool_id == "get_program_details":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        version = arguments.get("version")
        date = _as_str(arguments.get("date"))
        path = f"/v1/programs/{code}/versions/{version}" if version is not None else f"/v1/programs/{code}"
        params = {"date": date} if date else None
        return await service.syllabus_get(path, params=params)

    if tool_id == "get_program_versions":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        return await service.syllabus_get(f"/v1/programs/{code}/versions")

    if tool_id == "search_curriculums":
        params = _pick(arguments, ("schooltype", "timespan", "date"))
        data = await service.syllabus_get("/v1/curriculums", params=params or None)
        curriculums = [item for item in (data.get("curriculums") or []) if isinstance(item, dict)]
        return {
            "totalElements": data.get("totalElements", len(curriculums)),
            "curriculums": curriculums,
        }

    if tool_id == "get_curriculum_details":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        version = arguments.get("version")
        date = _as_str(arguments.get("date"))
        path = f"/v1/curriculums/{code}/versions/{version}" if version is not None else f"/v1/curriculums/{code}"
        params = {"date": date} if date else None
        return await service.syllabus_get(path, params=params)

    if tool_id == "get_curriculum_versions":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        return await service.syllabus_get(f"/v1/curriculums/{code}/versions")

    if tool_id == "get_school_types":
        include_expired = bool(arguments.get("includeExpired"))
        active = await service.syllabus_get("/v1/valuestore/schooltypes")
        active_types = active.get("schoolTypes") if isinstance(active, dict) else active
        active_types = active_types if isinstance(active_types, list) else []
        expired_types: list[Any] = []
        if include_expired:
            expired = await service.syllabus_get("/v1/valuestore/schooltypes/expired")
            payload = expired.get("schoolTypes") if isinstance(expired, dict) else expired
            expired_types = payload if isinstance(payload, list) else []
        return {
            "activeSchoolTypes": active_types,
            "expiredSchoolTypes": expired_types if include_expired else None,
            "total": len(active_types) + len(expired_types),
        }

    if tool_id == "get_types_of_syllabus":
        data = await service.syllabus_get("/v1/valuestore/typeofsyllabus")
        values = data.get("typesOfSyllabus") if isinstance(data, dict) else data
        values = values if isinstance(values, list) else []
        return {"typesOfSyllabus": values, "total": len(values)}

    if tool_id == "get_subject_and_course_codes":
        data = await service.syllabus_get("/v1/valuestore/subjectandcoursecodes")
        values = data.get("codes") if isinstance(data, dict) else data
        values = values if isinstance(values, list) else []
        return {"codes": values, "total": len(values)}

    if tool_id == "get_study_path_codes":
        params = _pick(arguments, ("schooltype", "timespan", "date", "typeOfStudyPath", "typeOfProgram"))
        type_hint = _as_str(arguments.get("type"))
        if type_hint and "typeOfStudyPath" not in params:
            params["typeOfStudyPath"] = type_hint
        data = await service.syllabus_get("/v1/valuestore/studypathcodes", params=params or None)
        values = data.get("codes") if isinstance(data, dict) else data
        values = values if isinstance(values, list) else []
        return {
            "studyPathCodes": values,
            "total": len(values),
            "filters": params,
        }

    if tool_id == "get_api_info":
        return await service.syllabus_get("/v1/api-info")

    if tool_id == "search_school_units":
        units = await service.get_all_school_units()
        name = _as_str(arguments.get("name"))
        status = _as_str(arguments.get("status"))
        if name:
            units = [unit for unit in units if _match_text(unit.get("name", ""), name)]
        if status:
            status_norm = _normalize_text(status)
            units = [unit for unit in units if _normalize_text(unit.get("status", "")) == status_norm]
        limit = _as_int(arguments.get("limit"), 50, min_value=1, max_value=500)
        return {
            "totalFound": len(units),
            "showing": min(limit, len(units)),
            "schoolUnits": units[:limit],
        }

    if tool_id == "get_school_unit_details":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        unit = await service.get_school_unit_by_code(code)
        if not unit:
            return {"status": "not_found", "code": code}
        return unit

    if tool_id == "get_school_units_by_status":
        status = _as_str(arguments.get("status"))
        if not status:
            raise ValueError("status is required")
        units = await service.get_all_school_units()
        status_norm = _normalize_text(status)
        filtered = [unit for unit in units if _normalize_text(unit.get("status", "")) == status_norm]
        limit = _as_int(arguments.get("limit"), 50, min_value=1, max_value=500)
        return {
            "status": status,
            "totalFound": len(filtered),
            "showing": min(limit, len(filtered)),
            "schoolUnits": filtered[:limit],
        }

    if tool_id == "search_school_units_by_name":
        name = _as_str(arguments.get("name"))
        if not name:
            raise ValueError("name is required")
        units = await service.get_all_school_units()
        filtered = [unit for unit in units if _match_text(unit.get("name", ""), name)]
        limit = _as_int(arguments.get("limit"), 50, min_value=1, max_value=500)
        return {
            "searchTerm": name,
            "totalFound": len(filtered),
            "showing": min(limit, len(filtered)),
            "schoolUnits": filtered[:limit],
        }

    if tool_id == "search_adult_education":
        params = _pick(
            arguments,
            (
                "searchTerm",
                "town",
                "municipality",
                "county",
                "typeOfSchool",
                "distance",
                "paceOfStudy",
                "semesterStartFrom",
                "page",
                "size",
            ),
        )
        if "distance" in params:
            parsed_distance = _as_bool(params.get("distance"))
            if parsed_distance is not None:
                params["distance"] = "true" if parsed_distance else "false"
        if "paceOfStudy" in params:
            pace = _as_str(params.get("paceOfStudy"))
            params["paceOfStudy"] = pace
        if "size" in params:
            params["size"] = _as_int(params.get("size"), 20, min_value=1, max_value=100)
        body = await service.planned_v3_get("/v3/adult-education-events", params=params or None)
        events = _get_embedded_list(body, "listedAdultEducationEvents")
        page = body.get("page") if isinstance(body, dict) and isinstance(body.get("page"), dict) else {}
        return {
            "totalResults": page.get("totalElements", len(events)),
            "currentPage": page.get("number", 0),
            "totalPages": page.get("totalPages", 1),
            "showing": len(events),
            "educationEvents": events,
        }

    if tool_id == "get_adult_education_details":
        event_id = _as_str(arguments.get("id"))
        if not event_id:
            raise ValueError("id is required")
        return await service.planned_v3_get(f"/v3/adult-education-events/{event_id}")

    if tool_id == "filter_adult_education_by_distance":
        distance = _as_bool(arguments.get("distance"))
        if distance is None:
            raise ValueError("distance must be true/false")
        nested_args = {
            "distance": "true" if distance else "false",
            "searchTerm": _as_str(arguments.get("searchTerm")),
            "page": arguments.get("page"),
            "size": arguments.get("size"),
        }
        result = await _execute_tool(
            next(item for item in SKOLVERKET_TOOL_DEFINITIONS if item.tool_id == "search_adult_education"),
            nested_args,
            service=service,
        )
        result["filter"] = "distance=true" if distance else "distance=false"
        return result

    if tool_id == "filter_adult_education_by_pace":
        pace = _as_str(arguments.get("paceOfStudy"))
        if not pace:
            raise ValueError("paceOfStudy is required")
        nested_args = {
            "paceOfStudy": pace,
            "searchTerm": _as_str(arguments.get("searchTerm")),
            "page": arguments.get("page"),
            "size": arguments.get("size"),
        }
        result = await _execute_tool(
            next(item for item in SKOLVERKET_TOOL_DEFINITIONS if item.tool_id == "search_adult_education"),
            nested_args,
            service=service,
        )
        result["paceFilter"] = pace
        return result

    if tool_id == "get_education_areas":
        return await service.planned_v3_get("/v3/support/geographical-areas")

    if tool_id == "get_directions":
        return await service.planned_v3_get("/v3/support/programs")

    if tool_id == "search_education_events":
        events, page_info, warnings = await _fetch_v4_education_events(service, arguments)
        limit = _as_int(arguments.get("limit"), 50, min_value=1, max_value=500)
        selected = events[:limit]
        result = {
            "totalResults": len(events),
            "showing": len(selected),
            "educationEvents": selected,
            "page": page_info or None,
        }
        if warnings:
            result["warnings"] = warnings
        return result

    if tool_id == "count_education_events":
        filter_keys = ("typeOfSchool", "municipality", "county", "programCode", "distance", "searchTerm", "schoolUnitCode")
        has_filters = any(arguments.get(key) is not None for key in filter_keys)
        if not has_filters:
            try:
                payload = await service.planned_v4_get("/v4/education-events/count")
                if isinstance(payload, int):
                    return {"count": payload, "source": "v4_count_endpoint"}
                if isinstance(payload, dict):
                    count = payload.get("count") or payload.get("totalElements") or payload.get("value")
                    return {"count": count, "source": "v4_count_endpoint", "payload": payload}
            except SkolverketApiError:
                pass
        events, _, warnings = await _fetch_v4_education_events(service, arguments)
        response: dict[str, Any] = {
            "count": len(events),
            "source": "fallback_v4_search_filter",
        }
        if warnings:
            response["warnings"] = warnings
        return response

    if tool_id == "count_adult_education_events":
        params = _pick(
            arguments,
            ("typeOfSchool", "municipality", "county", "distance", "searchTerm", "town", "paceOfStudy"),
        )
        if "distance" in params:
            parsed_distance = _as_bool(params.get("distance"))
            if parsed_distance is not None:
                params["distance"] = "true" if parsed_distance else "false"
        params["page"] = 0
        params["size"] = 1
        body = await service.planned_v3_get("/v3/adult-education-events", params=params)
        page = body.get("page") if isinstance(body, dict) and isinstance(body.get("page"), dict) else {}
        total = page.get("totalElements")
        if total is None:
            events = _get_embedded_list(body, "listedAdultEducationEvents")
            total = len(events)
        return {"count": total, "source": "v3_adult_education_search"}

    if tool_id == "get_adult_education_areas_v4":
        return await service.planned_v4_get("/v4/adult-education-events/areas")

    if tool_id == "search_school_units_v4":
        page_size = _as_int(arguments.get("size"), 200, min_value=1, max_value=200)
        max_pages = _as_int(arguments.get("maxPages"), 6, min_value=1, max_value=20)
        base_params: dict[str, Any] = {}
        name = _as_str(arguments.get("name"))
        if name:
            base_params["name"] = name
        pages = await service.iter_planned_v4_pages(
            "/v4/school-units",
            base_params=base_params,
            max_pages=max_pages,
            size=page_size,
        )
        units: list[dict[str, Any]] = []
        page_info: dict[str, Any] = {}
        for body in pages:
            if isinstance(body, dict):
                page_info = body.get("page") if isinstance(body.get("page"), dict) else page_info
                units.extend(_get_embedded_list(body, "listedSchoolUnits"))
        units, warnings = _filter_school_units_v4(units, arguments)
        limit = _as_int(arguments.get("limit"), 50, min_value=1, max_value=500)
        response: dict[str, Any] = {
            "totalResults": len(units),
            "showing": min(limit, len(units)),
            "schoolUnits": units[:limit],
            "page": page_info or None,
        }
        if len(pages) >= max_pages:
            warnings.append("Result set truncated to maxPages while collecting school units.")
        if warnings:
            response["warnings"] = list(dict.fromkeys(warnings))
        return response

    if tool_id == "get_school_unit_education_events":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        body = await service.planned_v4_get(f"/v4/school-units/{code}/education-events")
        events = _get_embedded_list(body, "educationEvents")
        warnings: list[str] = []
        if not events:
            fallback_args = {
                "schoolUnitCode": code,
                "programCode": arguments.get("programCode"),
                "limit": arguments.get("limit") or 100,
                "maxPages": arguments.get("maxPages") or 8,
            }
            fallback_events, _, fallback_warnings = await _fetch_v4_education_events(service, fallback_args)
            events = fallback_events
            warnings.append("Primary school-unit endpoint returned empty body; fallback used global education-events search.")
            warnings.extend(fallback_warnings)
        program_code = _as_str(arguments.get("programCode"))
        if program_code:
            events = [
                event
                for event in events
                if str(event.get("studyPathCode") or "").startswith(program_code)
                or str(event.get("studyPathCode") or "") == program_code
            ]
        limit = _as_int(arguments.get("limit"), 50, min_value=1, max_value=500)
        response = {
            "schoolUnitCode": code,
            "totalResults": len(events),
            "showing": min(limit, len(events)),
            "educationEvents": events[:limit],
        }
        if warnings:
            response["warnings"] = list(dict.fromkeys(warnings))
        return response

    if tool_id == "get_school_types_v4":
        return await service.planned_v4_get("/v4/support/school-types")

    if tool_id == "get_geographical_areas_v4":
        return await service.planned_v4_get("/v4/support/geographical-areas")

    if tool_id == "get_programs_v4":
        return await service.planned_v4_get("/v4/support/programs")

    if tool_id == "get_school_unit_documents":
        code = _as_str(arguments.get("code"))
        if not code:
            raise ValueError("code is required")
        body = await service.planned_v4_get(f"/v4/school-units/{code}/documents")
        groups = body if isinstance(body, list) else []
        flattened: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_code = str(group.get("typeOfSchoolingCode") or "")
            documents = group.get("documents")
            if not isinstance(documents, list):
                continue
            for document in documents:
                if not isinstance(document, dict):
                    continue
                enriched = dict(document)
                enriched["typeOfSchoolingCode"] = group_code
                flattened.append(enriched)
        school_type_filter = _as_str(arguments.get("typeOfSchooling")) or _as_str(arguments.get("schoolType"))
        if school_type_filter:
            school_type_norm = _normalize_text(school_type_filter)
            flattened = [
                item
                for item in flattened
                if _normalize_text(item.get("typeOfSchoolingCode")) == school_type_norm
            ]
        limit = _as_int(arguments.get("limit"), 100, min_value=1, max_value=500)
        return {
            "schoolUnitCode": code,
            "totalResults": len(flattened),
            "showing": min(limit, len(flattened)),
            "documents": flattened[:limit],
        }

    if tool_id == "get_school_unit_statistics":
        code = _as_str(arguments.get("code"))
        school_type = _normalize_school_type(arguments.get("schoolType"))
        if not code or not school_type:
            raise ValueError("code and schoolType are required")
        if school_type not in {"fsk", "gr", "gran", "gy", "gyan"}:
            return {
                "status": "invalid_school_type",
                "message": f"Unsupported schoolType: {school_type}",
                "supported": ["fsk", "gr", "gran", "gy", "gyan"],
            }
        params = _pick(arguments, ("year",))
        try:
            statistics = await service.planned_v4_get(
                f"/v4/school-units/{code}/statistics/{school_type}",
                params=params or None,
            )
            return {
                "schoolUnitCode": code,
                "schoolType": school_type,
                "statistics": statistics,
            }
        except SkolverketApiError as exc:
            if exc.status_code == 404:
                return {
                    "status": "unavailable",
                    "schoolUnitCode": code,
                    "schoolType": school_type,
                    "message": "No statistics available for this schoolType and school unit in current API.",
                    "api_error": str(exc),
                }
            raise

    if tool_id == "get_national_statistics":
        school_type = _normalize_school_type(arguments.get("schoolType"))
        if school_type not in {"fsk", "gr", "gran", "gy", "gyan"}:
            return {
                "status": "invalid_school_type",
                "message": f"Unsupported schoolType: {school_type}",
                "supported": ["fsk", "gr", "gran", "gy", "gyan"],
            }
        params = _pick(arguments, ("year", "programCode"))
        try:
            payload = await service.planned_v4_get(
                f"/v4/statistics/national-values/{school_type}",
                params=params or None,
            )
            return {"schoolType": school_type, "nationalStatistics": payload}
        except SkolverketApiError as exc:
            if exc.status_code == 404 and school_type == "gy":
                fallback_payload = await service.planned_v4_get(
                    "/v4/statistics/national-values/gyan",
                    params=params or None,
                )
                return {
                    "schoolType": school_type,
                    "nationalStatistics": fallback_payload,
                    "warning": "national-values/gy is unavailable; fallback to gyan was used.",
                }
            if exc.status_code == 404:
                return {
                    "status": "unavailable",
                    "schoolType": school_type,
                    "message": "No national statistics available for this schoolType in current API.",
                    "api_error": str(exc),
                }
            raise

    if tool_id == "get_program_statistics":
        school_type = _normalize_school_type(arguments.get("schoolType"))
        if school_type not in {"gy", "gyan"}:
            return {
                "status": "invalid_school_type",
                "message": f"Unsupported schoolType: {school_type}",
                "supported": ["gy", "gyan"],
            }
        params = _pick(arguments, ("year",))
        try:
            payload = await service.planned_v4_get(
                f"/v4/statistics/per-program/{school_type}",
                params=params or None,
            )
            return {"schoolType": school_type, "programStatistics": payload}
        except SkolverketApiError as exc:
            if exc.status_code != 404:
                raise
            # Current upstream API does not expose per-program stats for gy/gyan.
            # Fallback: derive lightweight counts from education-events.
            derived_events, _, warnings = await _fetch_v4_education_events(
                service,
                {"maxPages": 10, "size": 200},
                include_filters=False,
            )
            filtered_events = [
                event
                for event in derived_events
                if _normalize_text((event.get("typeOfSchooling") or {}).get("code")) == school_type
            ]
            counts: dict[str, int] = {}
            for event in filtered_events:
                study_path_code = str(event.get("studyPathCode") or "").strip()
                if not study_path_code:
                    continue
                prefix = study_path_code[:2]
                counts[prefix] = counts.get(prefix, 0) + 1
            top_programs = sorted(
                [{"programCodePrefix": key, "count": value} for key, value in counts.items()],
                key=lambda item: item["count"],
                reverse=True,
            )[:30]
            response: dict[str, Any] = {
                "status": "fallback_derived",
                "schoolType": school_type,
                "message": "per-program endpoint is unavailable; response is derived from education-events sample.",
                "programStatistics": {
                    "sampleEventCount": len(filtered_events),
                    "programCodePrefixCounts": top_programs,
                },
            }
            if warnings:
                response["warnings"] = warnings
            return response

    if tool_id == "health_check":
        include_api_tests = bool(arguments.get("includeApiTests", True))
        checks: list[dict[str, Any]] = []

        async def _run_check(service_name: str, coroutine):
            started = time.perf_counter()
            try:
                await coroutine
                latency = int((time.perf_counter() - started) * 1000)
                checks.append(
                    {
                        "service": service_name,
                        "status": "healthy" if latency < 2000 else "degraded",
                        "latencyMs": latency,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - explicit payload response
                checks.append(
                    {
                        "service": service_name,
                        "status": "unhealthy",
                        "error": str(exc),
                    }
                )

        if include_api_tests:
            await _run_check("Syllabus API", service.syllabus_get("/v1/api-info"))
            await _run_check(
                "School Units API",
                service.school_units_get("/v2/school-units/69405762"),
            )
            await _run_check(
                "Planned Education API",
                service.planned_v3_get("/v3/support/geographical-areas"),
            )

        unhealthy = sum(1 for check in checks if check.get("status") == "unhealthy")
        degraded = sum(1 for check in checks if check.get("status") == "degraded")
        overall = "healthy"
        if unhealthy > 0:
            overall = "unhealthy"
        elif degraded > 0:
            overall = "degraded"
        return {
            "overall": overall,
            "includeApiTests": include_api_tests,
            "services": checks,
        }

    raise ValueError(f"Unsupported Skolverket tool: {tool_id}")


def _build_tool_description(definition: SkolverketToolDefinition) -> str:
    examples = "\n".join(f"- {example}" for example in definition.example_queries[:3])
    return "\n\n".join(
        [
            definition.description,
            f"Category: {definition.category}",
            f"Keywords: {', '.join(definition.keywords[:12])}",
            f"Examples:\n{examples}",
        ]
    )


def _build_skolverket_tool(
    definition: SkolverketToolDefinition,
    *,
    skolverket_service: SkolverketService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
) -> StructuredTool:
    input_model = _create_dynamic_input_model_from_schema(
        definition.tool_id,
        definition.input_schema,
    )
    description = _build_tool_description(definition)

    async def _run(**kwargs) -> str:
        try:
            data = await _execute_tool(
                definition,
                kwargs,
                service=skolverket_service,
            )
        except SkolverketApiError as exc:
            return json.dumps({"error": str(exc), "tool": definition.tool_id}, ensure_ascii=True)
        except Exception as exc:  # noqa: BLE001 - return structured tool error payload
            return json.dumps({"error": str(exc), "tool": definition.tool_id}, ensure_ascii=True)

        tool_output = {
            "source": "Skolverket Open APIs",
            "tool": definition.tool_id,
            "category": definition.category,
            "query": kwargs,
            "data": data,
        }

        formatted_docs = ""
        try:
            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=tool_output,
                title=f"Skolverket: {definition.name}",
                metadata={
                    "source": "Skolverket",
                    "skolverket_tool": definition.tool_id,
                    "skolverket_category": definition.category,
                },
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )
            if document:
                serialized = connector_service._serialize_external_document(document, score=1.0)
                formatted_docs = format_documents_for_context([serialized])
        except Exception:
            # Do not fail the tool call if ingestion/citation persistence fails.
            formatted_docs = ""

        response_payload: dict[str, Any] = {
            "source": "Skolverket",
            "tool": definition.tool_id,
            "category": definition.category,
            "data": data,
        }
        if formatted_docs:
            response_payload["results"] = formatted_docs
        return json.dumps(response_payload, ensure_ascii=True)

    return StructuredTool(
        name=definition.tool_id,
        description=description,
        coroutine=_run,
        args_schema=input_model,
    )


def build_skolverket_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    skolverket_service: SkolverketService | None = None,
) -> dict[str, StructuredTool]:
    service = skolverket_service or SkolverketService()
    registry: dict[str, StructuredTool] = {}
    for definition in SKOLVERKET_TOOL_DEFINITIONS:
        registry[definition.tool_id] = _build_skolverket_tool(
            definition,
            skolverket_service=service,
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )
    return registry

