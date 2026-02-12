from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, TypedDict


class TrafikverketCategory(str, Enum):
    TRAFIKINFO = "trafikinfo"
    TAG = "tag"
    VAG = "vag"
    VADER = "vader"
    KAMEROR = "kameror"
    PROGNOS = "prognos"
    META = "meta"


class TrafikverketFilterKind(str, Enum):
    NONE = "none"
    LOCATION = "location"
    ROAD = "road"
    STATION = "station"
    CAMERA = "camera"
    FREE = "free"


class TrafikverketToolType(str, Enum):
    DATA = "data"
    AUTO = "auto"


class TrafikverketIntent(str, Enum):
    TRAFIK_STORNING = "trafik_storning"
    TRAFIK_OLYCKA = "trafik_olycka"
    TRAFIK_KOER = "trafik_koer"
    TRAFIK_VAGARBETE = "trafik_vagarbete"
    TAG_FORSENING = "tag_forsening"
    TAG_INSTALD = "tag_installd"
    TAG_TIDTABELL = "tag_tidtabell"
    TAG_STATIONER = "tag_stationer"
    VAG_STATUS = "vag_status"
    VAG_UNDERHALL = "vag_underhall"
    VAG_HASTIGHET = "vag_hastighet"
    VAG_AVSTANGNING = "vag_avstangning"
    VADER_HALKA = "vader_halka"
    VADER_VIND = "vader_vind"
    VADER_TEMPERATUR = "vader_temperatur"
    VADER_STATIONER = "vader_stationer"
    KAMERA_LISTA = "kamera_lista"
    KAMERA_SNAPSHOT = "kamera_snapshot"
    KAMERA_STATUS = "kamera_status"
    PROGNOS_TRAFIK = "prognos_trafik"
    PROGNOS_VAG = "prognos_vag"
    PROGNOS_TAG = "prognos_tag"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrafikverketToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    base_path: str
    category: TrafikverketCategory
    objecttype: str | None
    schema_version: str | None
    namespace: str | None
    filter_kind: TrafikverketFilterKind = TrafikverketFilterKind.NONE
    filter_fields: list[str] = field(default_factory=list)
    default_limit: int = 10
    tool_type: TrafikverketToolType = TrafikverketToolType.DATA
    requires_filter: bool = False
    fallback_tool_ids: list[str] = field(default_factory=list)


class TrafikverketToolInput(TypedDict, total=False):
    region: str | None
    road: str | None
    station: str | None
    kamera_id: str | None
    query: str | None
    limit: int | None
    raw_filter: str | None
    time_window_hours: int | None
    intent: str | None
    filter: dict[str, Any] | None
    from_location: str | None
    to_location: str | None


class TrafikverketToolResult(TypedDict, total=False):
    status: Literal["success", "error"]
    tool: str
    source: str
    base_path: str
    query: dict[str, Any]
    cached: bool
    data: dict[str, Any] | None
    error: str | None
    error_type: str | None
    resolved_filter_field: str | None
    resolved_filter_value: str | None
    resolved_intent: str | None
