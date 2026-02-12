from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agents.new_chat.tools.trafikverket_types import (
    TrafikverketFilterKind,
    TrafikverketIntent,
    TrafikverketToolDefinition,
    TrafikverketToolInput,
)


ROAD_REGEX = re.compile(r"\b(?:E|EU)\s?(\d{1,3})\b", re.IGNORECASE)
RV_REGEX = re.compile(r"\b(?:RV|Riksv[aä]g)\s?(\d{1,3})\b", re.IGNORECASE)
LV_REGEX = re.compile(r"\b(?:LV|L[aä]nsv[aä]g)\s?(\d{1,4})\b", re.IGNORECASE)
CAMERA_ID_REGEX = re.compile(r"\b(?:kamera|camera)\s*#?\s*([0-9]{4,})\b", re.IGNORECASE)


INTENT_PATTERNS: list[tuple[TrafikverketIntent, list[str]]] = [
    (TrafikverketIntent.KAMERA_SNAPSHOT, [r"\bsnapshot\b", r"\blivebild\b", r"\bsenaste bild\b"]),
    (TrafikverketIntent.KAMERA_STATUS, [r"\bstatus\b", r"\bonline\b", r"\boffline\b", r"\bdrift\b"]),
    (TrafikverketIntent.KAMERA_LISTA, [r"\bkamera\b", r"\bkameror\b", r"\blivekamera\b"]),
    (TrafikverketIntent.TAG_INSTALD, [r"\binställd\b", r"\binställda\b", r"\binstalld\b"]),
    (TrafikverketIntent.TAG_FORSENING, [r"\bförsening\b", r"\bforsening\b", r"\bförsenad\b"]),
    (TrafikverketIntent.TAG_TIDTABELL, [r"\btidtabell\b", r"\bavgång\b", r"\bankomst\b"]),
    (TrafikverketIntent.TAG_STATIONER, [r"\bstationer\b", r"\bstationslista\b"]),
    (TrafikverketIntent.TRAFIK_OLYCKA, [r"\bolycka\b", r"\bkrock\b", r"\bincident\b"]),
    (TrafikverketIntent.TRAFIK_KOER, [r"\bkö\b", r"\bköer\b", r"\btrafikstockning\b"]),
    (TrafikverketIntent.TRAFIK_VAGARBETE, [r"\bvägarbete\b", r"\bvägarbeten\b", r"\bomledning\b"]),
    (TrafikverketIntent.TRAFIK_STORNING, [r"\bstörning\b", r"\bstörningar\b", r"\bhinder\b"]),
    (TrafikverketIntent.VAG_AVSTANGNING, [r"\bavstängning\b", r"\bavstängningar\b"]),
    (TrafikverketIntent.VAG_HASTIGHET, [r"\bhastighetsgräns\b", r"\bfartgräns\b"]),
    (TrafikverketIntent.VAG_UNDERHALL, [r"\bunderhåll\b", r"\bvägskick\b"]),
    (TrafikverketIntent.VAG_STATUS, [r"\btrafikläge\b", r"\bvägstatus\b", r"\bframkomlighet\b"]),
    (TrafikverketIntent.VADER_HALKA, [r"\bhalka\b", r"\bisrisk\b", r"\bväglag\b"]),
    (TrafikverketIntent.VADER_VIND, [r"\bvind\b", r"\bstorm\b", r"\bblåst\b"]),
    (TrafikverketIntent.VADER_TEMPERATUR, [r"\btemperatur\b", r"\bgrader\b", r"\bminusgrader\b"]),
    (TrafikverketIntent.VADER_STATIONER, [r"\bväderstation\b", r"\bmätstation\b"]),
    (TrafikverketIntent.PROGNOS_TRAFIK, [r"\btrafikprognos\b", r"\brestidsprognos\b"]),
    (TrafikverketIntent.PROGNOS_VAG, [r"\bvägprognos\b", r"\bplanerade arbeten\b"]),
    (TrafikverketIntent.PROGNOS_TAG, [r"\btågprognos\b", r"\btågposition\b"]),
]


INTENT_TOOL_MAP: dict[TrafikverketIntent, str] = {
    TrafikverketIntent.TRAFIK_STORNING: "trafikverket_trafikinfo_storningar",
    TrafikverketIntent.TRAFIK_OLYCKA: "trafikverket_trafikinfo_olyckor",
    TrafikverketIntent.TRAFIK_KOER: "trafikverket_trafikinfo_koer",
    TrafikverketIntent.TRAFIK_VAGARBETE: "trafikverket_trafikinfo_vagarbeten",
    TrafikverketIntent.TAG_FORSENING: "trafikverket_tag_forseningar",
    TrafikverketIntent.TAG_INSTALD: "trafikverket_tag_installda",
    TrafikverketIntent.TAG_TIDTABELL: "trafikverket_tag_tidtabell",
    TrafikverketIntent.TAG_STATIONER: "trafikverket_tag_stationer",
    TrafikverketIntent.VAG_STATUS: "trafikverket_vag_status",
    TrafikverketIntent.VAG_UNDERHALL: "trafikverket_vag_underhall",
    TrafikverketIntent.VAG_HASTIGHET: "trafikverket_vag_hastighet",
    TrafikverketIntent.VAG_AVSTANGNING: "trafikverket_vag_avstangningar",
    TrafikverketIntent.VADER_HALKA: "trafikverket_vader_halka",
    TrafikverketIntent.VADER_VIND: "trafikverket_vader_vind",
    TrafikverketIntent.VADER_TEMPERATUR: "trafikverket_vader_temperatur",
    TrafikverketIntent.VADER_STATIONER: "trafikverket_vader_stationer",
    TrafikverketIntent.KAMERA_LISTA: "trafikverket_kameror_lista",
    TrafikverketIntent.KAMERA_SNAPSHOT: "trafikverket_kameror_snapshot",
    TrafikverketIntent.KAMERA_STATUS: "trafikverket_kameror_status",
    TrafikverketIntent.PROGNOS_TRAFIK: "trafikverket_prognos_trafik",
    TrafikverketIntent.PROGNOS_VAG: "trafikverket_prognos_vag",
    TrafikverketIntent.PROGNOS_TAG: "trafikverket_prognos_tag",
}


def normalize_limit(value: int | None, *, default: int = 10) -> int:
    try:
        if value is None:
            return default
        return max(1, min(int(value), 50))
    except (TypeError, ValueError):
        return default


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def normalize_road_number(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    match = ROAD_REGEX.search(raw)
    if match:
        return f"E{match.group(1)}"
    match = RV_REGEX.search(raw)
    if match:
        return match.group(1)
    match = LV_REGEX.search(raw)
    if match:
        return match.group(1)
    if raw.upper().startswith("E") and raw[1:].isdigit():
        return raw.upper()
    if raw.isdigit():
        return raw
    return None


def normalize_station_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    return cleaned or None


def extract_camera_id(value: str | None) -> str | None:
    if not value:
        return None
    match = CAMERA_ID_REGEX.search(value)
    if match:
        return match.group(1)
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 4:
        return digits
    return None


def infer_intent(text: str | None) -> TrafikverketIntent:
    if not text:
        return TrafikverketIntent.UNKNOWN
    lowered = text.lower()
    for intent, patterns in INTENT_PATTERNS:
        if any(re.search(pattern, lowered) for pattern in patterns):
            return intent
    if ROAD_REGEX.search(lowered) or RV_REGEX.search(lowered) or LV_REGEX.search(lowered):
        return TrafikverketIntent.TRAFIK_STORNING
    if "tåg" in lowered or "tag" in lowered:
        return TrafikverketIntent.TAG_TIDTABELL
    return TrafikverketIntent.UNKNOWN


def intent_to_tool_id(intent: TrafikverketIntent) -> str | None:
    return INTENT_TOOL_MAP.get(intent)


def normalize_tool_input(
    definition: TrafikverketToolDefinition, raw: TrafikverketToolInput
) -> TrafikverketToolInput:
    filter_data = raw.get("filter")
    if not isinstance(filter_data, dict):
        filter_data = {}
    query = _coerce_str(raw.get("query")) or ""
    region = _coerce_str(raw.get("region")) or _coerce_str(filter_data.get("region"))
    road = _coerce_str(raw.get("road")) or _coerce_str(filter_data.get("road"))
    station = _coerce_str(raw.get("station")) or _coerce_str(filter_data.get("station"))
    kamera_id = _coerce_str(raw.get("kamera_id")) or _coerce_str(
        filter_data.get("kamera_id") or filter_data.get("camera_id")
    )
    from_location = _coerce_str(raw.get("from_location")) or _coerce_str(
        filter_data.get("from") or filter_data.get("from_location")
    )
    to_location = _coerce_str(raw.get("to_location")) or _coerce_str(
        filter_data.get("to") or filter_data.get("to_location")
    )

    if not query and (from_location or to_location):
        query = " ".join(part for part in (from_location, to_location) if part)
    if not query and road:
        query = road

    if not road:
        road = normalize_road_number(query) or normalize_road_number(region)
    else:
        road = normalize_road_number(road) or road
    if not station and definition.filter_kind == TrafikverketFilterKind.STATION:
        station = normalize_station_name(raw.get("station") or query or region)
    if not region and query:
        region = query
    if not kamera_id:
        kamera_id = extract_camera_id(query)

    time_window = raw.get("time_window_hours")
    if time_window is None:
        time_window = infer_time_window(query)

    return {
        "region": region,
        "road": road,
        "station": station,
        "kamera_id": kamera_id,
        "query": query or None,
        "limit": raw.get("limit"),
        "raw_filter": raw.get("raw_filter"),
        "time_window_hours": time_window,
        "intent": raw.get("intent"),
        "filter": filter_data if filter_data else None,
        "from_location": from_location,
        "to_location": to_location,
    }


def infer_filter_value(
    definition: TrafikverketToolDefinition,
    raw: TrafikverketToolInput,
) -> str | None:
    if raw.get("raw_filter"):
        return str(raw.get("raw_filter"))
    from_location = _coerce_str(raw.get("from_location"))
    to_location = _coerce_str(raw.get("to_location"))
    combined_location = " ".join(
        part for part in (from_location, to_location) if part
    )
    road_value = normalize_road_number(raw.get("road") or None)
    query_text = _coerce_str(raw.get("query"))
    if definition.filter_kind == TrafikverketFilterKind.ROAD:
        return road_value or normalize_road_number(query_text)
    if definition.filter_kind == TrafikverketFilterKind.STATION:
        return normalize_station_name(raw.get("station") or query_text or combined_location)
    if definition.filter_kind == TrafikverketFilterKind.CAMERA:
        return extract_camera_id(raw.get("kamera_id") or raw.get("query"))
    if definition.filter_kind == TrafikverketFilterKind.LOCATION:
        return (
            road_value
            or raw.get("region")
            or combined_location
            or query_text
        )
    if definition.filter_kind == TrafikverketFilterKind.FREE:
        return query_text or raw.get("region") or road_value or combined_location
    return None


def infer_time_window(text: str | None) -> int | None:
    if not text:
        return None
    lowered = text.lower()
    if "just nu" in lowered or "nu" in lowered:
        return 6
    if "idag" in lowered:
        return 24
    if "imorgon" in lowered or "nästa" in lowered:
        return 48
    return None


def filter_results_by_time(payload: dict[str, Any], hours: int | None) -> dict[str, Any]:
    if not hours:
        return payload
    try:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
    except Exception:
        return payload

    def parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return None

    response = payload.get("RESPONSE") or payload.get("response") or {}
    results = response.get("RESULT") if isinstance(response, dict) else None
    if not isinstance(results, list):
        return payload

    filtered_results: list[Any] = []
    for result in results:
        if not isinstance(result, dict):
            filtered_results.append(result)
            continue
        for key, items in list(result.items()):
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                if not isinstance(item, dict):
                    kept.append(item)
                    continue
                time_value = (
                    item.get("StartTime")
                    or item.get("ModifiedTime")
                    or item.get("LastModifiedTime")
                    or item.get("CreatedTime")
                )
                parsed = parse_dt(str(time_value)) if time_value else None
                if not parsed or parsed >= cutoff:
                    kept.append(item)
            result[key] = kept
        filtered_results.append(result)
    response["RESULT"] = filtered_results
    payload["RESPONSE"] = response
    return payload


def has_results(payload: dict[str, Any]) -> bool:
    response = payload.get("RESPONSE") or payload.get("response") or {}
    results = response.get("RESULT") if isinstance(response, dict) else None
    if not isinstance(results, list):
        return False
    for result in results:
        if not isinstance(result, dict):
            continue
        for value in result.values():
            if isinstance(value, list) and value:
                return True
    return False
