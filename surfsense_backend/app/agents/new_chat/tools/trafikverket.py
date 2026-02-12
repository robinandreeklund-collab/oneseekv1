from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.services.connector_service import ConnectorService
from app.services.trafikverket_service import (
    TRAFIKVERKET_SOURCE,
    TrafikverketService,
)


@dataclass(frozen=True)
class TrafikverketToolDefinition:
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    base_path: str
    category: str
    objecttype: str
    schema_version: str | None = "1.0"
    namespace: str | None = None
    filter_field: str | None = None


TRAFIKVERKET_TOOL_DEFINITIONS: list[TrafikverketToolDefinition] = [
    TrafikverketToolDefinition(
        tool_id="trafikverket_trafikinfo_storningar",
        name="Trafikverket Trafikinfo - Störningar",
        description="Allmänna störningar i väg- och järnvägstrafik (hinder, avbrott, incidenter).",
        keywords=[
            "störning",
            "störningar",
            "trafikstörning",
            "trafikinfo",
            "incident",
            "hinder",
            "avbrott",
            "signalproblem",
            "järnväg",
            "väg",
            "trafikverket",
        ],
        example_queries=[
            "Störningar på E4 vid Södertälje",
            "Trafikstörningar i Stockholm",
            "Störningar i tågtrafiken mellan Stockholm och Uppsala",
        ],
        base_path="/data.json",
        category="trafikverket_trafikinfo",
        objecttype="Situation",
        schema_version="1.6",
        namespace="road.trafficinfo.new",
        filter_field="Deviation.LocationDescriptor",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_trafikinfo_olyckor",
        name="Trafikverket Trafikinfo - Olyckor",
        description="Olyckor och incidenter i trafiken (väg).",
        keywords=[
            "olycka",
            "trafikolycka",
            "krock",
            "incident",
            "singelolycka",
            "väg",
            "trafikinfo",
            "trafikverket",
        ],
        example_queries=[
            "Olycka på E6 vid Kungsbacka",
            "Trafikolyckor i Skåne idag",
            "Olycka på riksväg 40",
        ],
        base_path="/data.json",
        category="trafikverket_trafikinfo",
        objecttype="Situation",
        schema_version="1.6",
        namespace="road.trafficinfo.new",
        filter_field="Deviation.LocationDescriptor",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_trafikinfo_koer",
        name="Trafikverket Trafikinfo - Köer",
        description="Köer och framkomlighetsproblem på vägar.",
        keywords=[
            "kö",
            "köer",
            "koer",
            "trafikstockning",
            "trängsel",
            "framkomlighet",
            "trafikläge",
            "trafikinfo",
        ],
        example_queries=[
            "Var är det köer i Göteborg just nu?",
            "Köer på E18 mot Stockholm",
            "Trafikstockning på Essingeleden",
        ],
        base_path="/data.json",
        category="trafikverket_trafikinfo",
        objecttype="Situation",
        schema_version="1.6",
        namespace="road.trafficinfo.new",
        filter_field="Deviation.LocationDescriptor",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_trafikinfo_vagarbeten",
        name="Trafikverket Trafikinfo - Vägarbeten",
        description="Planerade och pågående vägarbeten samt omledningar.",
        keywords=[
            "vägarbete",
            "vägarbeten",
            "vagarbete",
            "arbete",
            "roadwork",
            "omledning",
            "avstängning",
            "trafikinfo",
        ],
        example_queries=[
            "Vägarbeten på E4 mot Helsingborg",
            "Pågående vägarbeten i Skåne län",
            "Vägarbete på riksväg 50",
        ],
        base_path="/data.json",
        category="trafikverket_trafikinfo",
        objecttype="Situation",
        schema_version="1.6",
        namespace="road.trafficinfo.new",
        filter_field="Deviation.LocationDescriptor",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_tag_forseningar",
        name="Trafikverket Tåg - Förseningar",
        description="Tågförseningar per station eller sträcka.",
        keywords=[
            "tåg",
            "tågförsening",
            "försening",
            "forsening",
            "försenad",
            "järnväg",
            "station",
            "spår",
        ],
        example_queries=[
            "Tågförseningar Stockholm C just nu",
            "Försenade tåg mot Göteborg",
            "Förseningar på Västra stambanan",
        ],
        base_path="/data.json",
        category="trafikverket_tag",
        objecttype="TrainAnnouncement",
        schema_version="1.9",
        filter_field="AdvertisedLocationName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_tag_tidtabell",
        name="Trafikverket Tåg - Tidtabell",
        description="Tidtabell för tågavgångar och ankomster.",
        keywords=[
            "tidtabell",
            "avgång",
            "ankomst",
            "tåg",
            "perrong",
            "spår",
            "schedule",
        ],
        example_queries=[
            "Avgångar från Malmö C",
            "Ankomster till Göteborg C",
            "Tidtabell Uppsala C imorgon",
        ],
        base_path="/data.json",
        category="trafikverket_tag",
        objecttype="TrainAnnouncement",
        schema_version="1.9",
        filter_field="AdvertisedLocationName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_tag_stationer",
        name="Trafikverket Tåg - Stationer",
        description="Järnvägsstationer och hållplatser för tåg.",
        keywords=[
            "station",
            "stationer",
            "tågstation",
            "hållplats",
            "järnväg",
            "trafikverket",
        ],
        example_queries=[
            "Tågstationer i Uppsala län",
            "Stationer som börjar med 'Sundsvall'",
            "Lista stationer i Stockholm",
        ],
        base_path="/data.json",
        category="trafikverket_tag",
        objecttype="TrainStation",
        schema_version="1.5",
        namespace="rail.infrastructure",
        filter_field="AdvertisedLocationName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_tag_installda",
        name="Trafikverket Tåg - Inställda",
        description="Inställda tåg per station eller sträcka.",
        keywords=["inställd", "inställda", "installd", "tåg", "avgång", "ankomst"],
        example_queries=[
            "Inställda tåg i Göteborg",
            "Inställda avgångar Stockholm C",
            "Inställda tåg mot Malmö",
        ],
        base_path="/data.json",
        category="trafikverket_tag",
        objecttype="TrainAnnouncement",
        schema_version="1.9",
        filter_field="AdvertisedLocationName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vag_status",
        name="Trafikverket Väg - Status",
        description="Trafikflöde och vägstatus för vägsträckor eller regioner.",
        keywords=[
            "vägstatus",
            "vagstatus",
            "trafikläge",
            "trafikflöde",
            "framkomlighet",
            "väg",
            "status",
        ],
        example_queries=[
            "Trafikläge på E4 vid Stockholm",
            "Vägstatus i Västra Götaland",
            "Framkomlighet på Essingeleden",
        ],
        base_path="/data.json",
        category="trafikverket_vag",
        objecttype="TrafficFlow",
        schema_version="1.5",
        namespace="road.trafficinfo",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vag_underhall",
        name="Trafikverket Väg - Underhåll",
        description="Underhållsinformation och vägskick för vägar.",
        keywords=[
            "underhåll",
            "underhall",
            "vägskick",
            "beläggning",
            "väg",
            "reparation",
        ],
        example_queries=[
            "Planerat underhåll på E18",
            "Underhållsarbeten i Skåne",
            "Vägskick på riksväg 70",
        ],
        base_path="/data.json",
        category="trafikverket_vag",
        objecttype="RoadCondition",
        schema_version="1.3",
        namespace="road.trafficinfo",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vag_hastighet",
        name="Trafikverket Väg - Hastighet",
        description="Gällande hastighetsgränser (inklusive temporära).",
        keywords=[
            "hastighet",
            "hastighetsgräns",
            "fartgräns",
            "begränsning",
            "speed",
            "väg",
        ],
        example_queries=[
            "Hastighetsgräns på E6",
            "Tillfälliga hastigheter på E4",
            "Fartgräns i Stockholm innerstad",
        ],
        base_path="/data.json",
        category="trafikverket_vag",
        objecttype="Hastighetsgräns",
        schema_version="1.4",
        namespace="vägdata.nvdb_dk_o",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vag_avstangningar",
        name="Trafikverket Väg - Avstängningar",
        description="Vägavstängningar, avspärrningar och omledningar.",
        keywords=[
            "avstängning",
            "avstängningar",
            "avstangning",
            "omledning",
            "avspärrning",
            "väg",
            "trafik",
        ],
        example_queries=[
            "Avstängningar på E20",
            "Omledning vid väg 73",
            "Vägavstängning i Uppsala",
        ],
        base_path="/data.json",
        category="trafikverket_vag",
        objecttype="RoadCondition",
        schema_version="1.3",
        namespace="road.trafficinfo",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vader_stationer",
        name="Trafikverket Väder - Stationer",
        description="Väderstationer och mätpunkter kopplade till trafiknät.",
        keywords=[
            "väderstation",
            "vaderstation",
            "station",
            "mätpunkt",
            "väderdata",
            "väglag",
            "väder",
        ],
        example_queries=[
            "Väderstationer i Norrbotten",
            "Mätstationer längs E4",
            "Vägväderstationer i Skåne",
        ],
        base_path="/data.json",
        category="trafikverket_vader",
        objecttype="WeatherMeasurepoint",
        schema_version="2.1",
        namespace="road.weatherinfo",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vader_halka",
        name="Trafikverket Väder - Halka",
        description="Halka, isrisk och väglag kopplat till väder.",
        keywords=[
            "halka",
            "is",
            "isrisk",
            "väglag",
            "snö",
            "vader",
            "väder",
        ],
        example_queries=[
            "Risk för halka i Västerbotten",
            "Väglag på E45",
            "Halkvarning i Dalarna",
        ],
        base_path="/data.json",
        category="trafikverket_vader",
        objecttype="WeatherObservation",
        schema_version="2.1",
        namespace="road.weatherinfo",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vader_vind",
        name="Trafikverket Väder - Vind",
        description="Vindinformation och vindbyar för trafikleder.",
        keywords=["vind", "vindstyrka", "vindby", "blåst", "storm", "vader", "väder"],
        example_queries=[
            "Vind på Öresundsbron",
            "Vindstyrka vid Högakustenbron",
            "Blåst i Skåne",
        ],
        base_path="/data.json",
        category="trafikverket_vader",
        objecttype="WeatherObservation",
        schema_version="2.1",
        namespace="road.weatherinfo",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vader_temperatur",
        name="Trafikverket Väder - Temperatur",
        description="Temperaturer från väderstationer vid vägnätet.",
        keywords=["temperatur", "grader", "minus", "kall", "varm", "vader", "väder"],
        example_queries=[
            "Temperatur på E4 idag",
            "Temperaturer i Dalarna",
            "Minusgrader i Norrbotten",
        ],
        base_path="/data.json",
        category="trafikverket_vader",
        objecttype="WeatherObservation",
        schema_version="2.1",
        namespace="road.weatherinfo",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_kameror_lista",
        name="Trafikverket Kameror - Lista",
        description="Lista trafikkameror per region, plats eller väg.",
        keywords=[
            "kamera",
            "trafikkamera",
            "kameror",
            "livekamera",
            "bild",
            "snapshot",
            "väg",
        ],
        example_queries=[
            "Visa trafikkameror i Stockholm",
            "Kameror längs E4",
            "Lista kameror vid Essingeleden",
        ],
        base_path="/data.json",
        category="trafikverket_kameror",
        objecttype="Camera",
        schema_version="1.1",
        namespace="road.infrastructure",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_kameror_snapshot",
        name="Trafikverket Kameror - Snapshot",
        description="Hämta senaste bild/snapshot från en trafikkamera.",
        keywords=["kamera", "snapshot", "livebild", "senaste bild", "bild", "trafikkamera"],
        example_queries=[
            "Snapshot för kamera 12345",
            "Senaste bild från kamera E6-01",
            "Livebild kamera vid Slussen",
        ],
        base_path="/data.json",
        category="trafikverket_kameror",
        objecttype="Camera",
        schema_version="1.1",
        namespace="road.infrastructure",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_kameror_status",
        name="Trafikverket Kameror - Status",
        description="Status för trafikkamera (online/offline/drift).",
        keywords=["kamera", "status", "online", "offline", "drift", "tillgänglig"],
        example_queries=[
            "Status för kamera 12345",
            "Är kamera E4-10 online?",
            "Driftstatus trafikkamera vid E6",
        ],
        base_path="/data.json",
        category="trafikverket_kameror",
        objecttype="Camera",
        schema_version="1.1",
        namespace="road.infrastructure",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_prognos_trafik",
        name="Trafikverket Prognos - Trafik",
        description="Trafikprognoser per region/väg (belastning/restider).",
        keywords=["prognos", "trafik", "framtid", "belastning", "restid", "kö"],
        example_queries=[
            "Trafikprognos för E4 nästa vecka",
            "Prognos för trafik i Stockholm",
            "Restidsprognos på E6",
        ],
        base_path="/data.json",
        category="trafikverket_prognos",
        objecttype="TravelTimeRoute",
        schema_version="1.6",
        namespace="road.trafficinfo",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_prognos_vag",
        name="Trafikverket Prognos - Väg",
        description="Vägprognoser och planerade arbeten.",
        keywords=[
            "vägprognos",
            "prognos",
            "väg",
            "vag",
            "planerade arbeten",
            "planering",
        ],
        example_queries=[
            "Vägprognos E18",
            "Planerade arbeten kommande vecka",
            "Vägprojekt i Skåne län",
        ],
        base_path="/data.json",
        category="trafikverket_prognos",
        objecttype="TravelTimeRoute",
        schema_version="1.6",
        namespace="road.trafficinfo",
        filter_field=None,
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_prognos_tag",
        name="Trafikverket Prognos - Tåg",
        description="Tågprognoser och förväntade förseningar/positioner.",
        keywords=[
            "tågprognos",
            "prognos",
            "tåg",
            "försening",
            "forsening",
            "tågposition",
            "järnväg",
        ],
        example_queries=[
            "Tågprognos Stockholm C",
            "Förväntade förseningar till Göteborg",
            "Var är tåg 12345 nu?",
        ],
        base_path="/data.json",
        category="trafikverket_prognos",
        objecttype="TrainPosition",
        schema_version="1.1",
        namespace="järnväg.trafikinfo",
        filter_field=None,
    ),
]


def _build_payload(
    *,
    tool_name: str,
    base_path: str,
    query: dict[str, Any],
    data: dict[str, Any],
    cached: bool,
) -> dict[str, Any]:
    return {
        "status": "success",
        "tool": tool_name,
        "source": TRAFIKVERKET_SOURCE,
        "base_path": base_path,
        "query": query,
        "cached": cached,
        "data": data,
    }


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _extract_filter_value(query: dict[str, Any]) -> str | None:
    filter_data = query.get("filter")
    if isinstance(query.get("region"), dict) and not isinstance(filter_data, dict):
        filter_data = query.get("region")
    if not isinstance(filter_data, dict):
        filter_data = {}

    from_location = _coerce_str(
        filter_data.get("from")
        or filter_data.get("from_location")
        or query.get("from")
        or query.get("from_location")
    )
    to_location = _coerce_str(
        filter_data.get("to")
        or filter_data.get("to_location")
        or query.get("to")
        or query.get("to_location")
    )
    road = _coerce_str(filter_data.get("road") or query.get("road"))
    region = _coerce_str(filter_data.get("region") or query.get("region"))
    station = _coerce_str(filter_data.get("station") or query.get("station"))
    kamera_id = _coerce_str(
        filter_data.get("kamera_id")
        or filter_data.get("camera_id")
        or query.get("kamera_id")
    )
    query_text = _coerce_str(filter_data.get("query") or query.get("query"))

    for candidate in (road, region, station, kamera_id, query_text):
        if candidate:
            return candidate
    if from_location or to_location:
        return " ".join(part for part in (from_location, to_location) if part)
    return None


async def _ingest_output(
    *,
    connector_service: ConnectorService | None,
    tool_name: str,
    title: str,
    payload: dict[str, Any],
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
) -> None:
    if not connector_service:
        return
    await connector_service.ingest_tool_output(
        tool_name=tool_name,
        tool_output=payload,
        title=title,
        metadata={
            "source": TRAFIKVERKET_SOURCE,
            "base_path": payload.get("base_path"),
            "query": payload.get("query"),
        },
        user_id=user_id,
        origin_search_space_id=search_space_id,
        thread_id=thread_id,
    )


def build_trafikverket_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    api_key: str | None = None,
) -> dict[str, BaseTool]:
    service = TrafikverketService(api_key=api_key)

    async def _wrap(
        tool_id: str,
        base_path: str,
        query: dict[str, Any],
        title: str,
        *,
        objecttype: str,
        schema_version: str | None,
        namespace: str | None,
        filter_field: str | None,
        filter_value: str | None,
        limit: int,
    ) -> dict[str, Any]:
        if filter_value is None:
            filter_value = _extract_filter_value(query)
        data, cached = await service.query(
            objecttype=objecttype,
            schema_version=schema_version,
            namespace=namespace,
            filter_field=filter_field,
            filter_value=filter_value,
            limit=limit,
        )
        payload = _build_payload(
            tool_name=tool_id,
            base_path=base_path,
            query=query,
            data=data,
            cached=cached,
        )
        await _ingest_output(
            connector_service=connector_service,
            tool_name=tool_id,
            title=title,
            payload=payload,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )
        return payload

    @tool("trafikverket_trafikinfo_storningar", description=TRAFIKVERKET_TOOL_DEFINITIONS[0].description)
    async def trafikverket_trafikinfo_storningar(
        region: str | None = None,
        road: str | None = None,
        from_location: str | None = None,
        to_location: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_trafikinfo_storningar",
                TRAFIKVERKET_TOOL_DEFINITIONS[0].base_path,
                {
                    "region": region,
                    "road": road,
                    "from_location": from_location,
                    "to_location": to_location,
                    "limit": limit,
                    "filter": filter,
                },
                f"Trafikverket störningar {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[0].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[0].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[0].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[0].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[0].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[0].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[0].namespace,
            }

    @tool("trafikverket_trafikinfo_olyckor", description=TRAFIKVERKET_TOOL_DEFINITIONS[1].description)
    async def trafikverket_trafikinfo_olyckor(
        region: str | None = None,
        road: str | None = None,
        from_location: str | None = None,
        to_location: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_trafikinfo_olyckor",
                TRAFIKVERKET_TOOL_DEFINITIONS[1].base_path,
                {
                    "region": region,
                    "road": road,
                    "from_location": from_location,
                    "to_location": to_location,
                    "limit": limit,
                    "filter": filter,
                },
                f"Trafikverket olyckor {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[1].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[1].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[1].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[1].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[1].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[1].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[1].namespace,
            }

    @tool("trafikverket_trafikinfo_koer", description=TRAFIKVERKET_TOOL_DEFINITIONS[2].description)
    async def trafikverket_trafikinfo_koer(
        region: str | None = None,
        road: str | None = None,
        from_location: str | None = None,
        to_location: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_trafikinfo_koer",
                TRAFIKVERKET_TOOL_DEFINITIONS[2].base_path,
                {
                    "region": region,
                    "road": road,
                    "from_location": from_location,
                    "to_location": to_location,
                    "limit": limit,
                    "filter": filter,
                },
                f"Trafikverket köer {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[2].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[2].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[2].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[2].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[2].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[2].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[2].namespace,
            }

    @tool("trafikverket_trafikinfo_vagarbeten", description=TRAFIKVERKET_TOOL_DEFINITIONS[3].description)
    async def trafikverket_trafikinfo_vagarbeten(
        region: str | None = None,
        road: str | None = None,
        from_location: str | None = None,
        to_location: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_trafikinfo_vagarbeten",
                TRAFIKVERKET_TOOL_DEFINITIONS[3].base_path,
                {
                    "region": region,
                    "road": road,
                    "from_location": from_location,
                    "to_location": to_location,
                    "limit": limit,
                    "filter": filter,
                },
                f"Trafikverket vägarbeten {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[3].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[3].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[3].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[3].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[3].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[3].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[3].namespace,
            }

    @tool("trafikverket_tag_forseningar", description=TRAFIKVERKET_TOOL_DEFINITIONS[4].description)
    async def trafikverket_tag_forseningar(
        station: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_tag_forseningar",
                TRAFIKVERKET_TOOL_DEFINITIONS[4].base_path,
                {"station": station, "limit": limit, "filter": filter},
                f"Trafikverket tågförseningar {station or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[4].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[4].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[4].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[4].filter_field,
                filter_value=station,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[4].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[4].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[4].namespace,
            }

    @tool("trafikverket_tag_tidtabell", description=TRAFIKVERKET_TOOL_DEFINITIONS[5].description)
    async def trafikverket_tag_tidtabell(
        station: str,
        date: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_tag_tidtabell",
                TRAFIKVERKET_TOOL_DEFINITIONS[5].base_path,
                {"station": station, "date": date, "filter": filter},
                f"Trafikverket tidtabell {station}",
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[5].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[5].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[5].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[5].filter_field,
                filter_value=station,
                limit=10,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[5].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[5].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[5].namespace,
            }

    @tool("trafikverket_tag_stationer", description=TRAFIKVERKET_TOOL_DEFINITIONS[6].description)
    async def trafikverket_tag_stationer(
        query: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_tag_stationer",
                TRAFIKVERKET_TOOL_DEFINITIONS[6].base_path,
                {"query": query, "limit": limit, "filter": filter},
                f"Trafikverket stationer {query or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[6].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[6].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[6].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[6].filter_field,
                filter_value=query,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[6].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[6].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[6].namespace,
            }

    @tool("trafikverket_tag_installda", description=TRAFIKVERKET_TOOL_DEFINITIONS[7].description)
    async def trafikverket_tag_installda(
        station: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_tag_installda",
                TRAFIKVERKET_TOOL_DEFINITIONS[7].base_path,
                {"station": station, "limit": limit, "filter": filter},
                f"Trafikverket inställda {station or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[7].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[7].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[7].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[7].filter_field,
                filter_value=station,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[7].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[7].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[7].namespace,
            }

    @tool("trafikverket_vag_status", description=TRAFIKVERKET_TOOL_DEFINITIONS[8].description)
    async def trafikverket_vag_status(
        road: str | None = None,
        region: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vag_status",
                TRAFIKVERKET_TOOL_DEFINITIONS[8].base_path,
                {"road": road, "region": region, "limit": limit, "filter": filter},
                f"Trafikverket vägstatus {road or region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[8].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[8].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[8].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[8].filter_field,
                filter_value=road or region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[8].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[8].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[8].namespace,
            }

    @tool("trafikverket_vag_underhall", description=TRAFIKVERKET_TOOL_DEFINITIONS[9].description)
    async def trafikverket_vag_underhall(
        road: str | None = None,
        region: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vag_underhall",
                TRAFIKVERKET_TOOL_DEFINITIONS[9].base_path,
                {"road": road, "region": region, "limit": limit, "filter": filter},
                f"Trafikverket underhåll {road or region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[9].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[9].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[9].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[9].filter_field,
                filter_value=road or region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[9].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[9].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[9].namespace,
            }

    @tool("trafikverket_vag_hastighet", description=TRAFIKVERKET_TOOL_DEFINITIONS[10].description)
    async def trafikverket_vag_hastighet(
        road: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vag_hastighet",
                TRAFIKVERKET_TOOL_DEFINITIONS[10].base_path,
                {"road": road, "limit": limit, "filter": filter},
                f"Trafikverket hastighet {road or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[10].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[10].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[10].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[10].filter_field,
                filter_value=road,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[10].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[10].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[10].namespace,
            }

    @tool("trafikverket_vag_avstangningar", description=TRAFIKVERKET_TOOL_DEFINITIONS[11].description)
    async def trafikverket_vag_avstangningar(
        road: str | None = None,
        region: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vag_avstangningar",
                TRAFIKVERKET_TOOL_DEFINITIONS[11].base_path,
                {"road": road, "region": region, "limit": limit, "filter": filter},
                f"Trafikverket avstängningar {road or region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[11].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[11].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[11].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[11].filter_field,
                filter_value=road or region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[11].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[11].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[11].namespace,
            }

    @tool("trafikverket_vader_stationer", description=TRAFIKVERKET_TOOL_DEFINITIONS[12].description)
    async def trafikverket_vader_stationer(
        region: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vader_stationer",
                TRAFIKVERKET_TOOL_DEFINITIONS[12].base_path,
                {"region": region, "limit": limit, "filter": filter},
                f"Trafikverket väderstationer {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[12].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[12].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[12].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[12].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[12].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[12].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[12].namespace,
            }

    @tool("trafikverket_vader_halka", description=TRAFIKVERKET_TOOL_DEFINITIONS[13].description)
    async def trafikverket_vader_halka(
        region: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vader_halka",
                TRAFIKVERKET_TOOL_DEFINITIONS[13].base_path,
                {"region": region, "limit": limit, "filter": filter},
                f"Trafikverket halka {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[13].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[13].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[13].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[13].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[13].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[13].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[13].namespace,
            }

    @tool("trafikverket_vader_vind", description=TRAFIKVERKET_TOOL_DEFINITIONS[14].description)
    async def trafikverket_vader_vind(
        region: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vader_vind",
                TRAFIKVERKET_TOOL_DEFINITIONS[14].base_path,
                {"region": region, "limit": limit, "filter": filter},
                f"Trafikverket vind {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[14].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[14].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[14].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[14].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[14].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[14].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[14].namespace,
            }

    @tool("trafikverket_vader_temperatur", description=TRAFIKVERKET_TOOL_DEFINITIONS[15].description)
    async def trafikverket_vader_temperatur(
        region: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vader_temperatur",
                TRAFIKVERKET_TOOL_DEFINITIONS[15].base_path,
                {"region": region, "limit": limit, "filter": filter},
                f"Trafikverket temperatur {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[15].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[15].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[15].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[15].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[15].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[15].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[15].namespace,
            }

    @tool("trafikverket_kameror_lista", description=TRAFIKVERKET_TOOL_DEFINITIONS[16].description)
    async def trafikverket_kameror_lista(
        region: str | None = None,
        road: str | None = None,
        limit: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_kameror_lista",
                TRAFIKVERKET_TOOL_DEFINITIONS[16].base_path,
                {"region": region, "road": road, "limit": limit, "filter": filter},
                f"Trafikverket kameror {region or road or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[16].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[16].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[16].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[16].filter_field,
                filter_value=road or region,
                limit=limit,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[16].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[16].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[16].namespace,
            }

    @tool("trafikverket_kameror_snapshot", description=TRAFIKVERKET_TOOL_DEFINITIONS[17].description)
    async def trafikverket_kameror_snapshot(
        kamera_id: str, filter: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_kameror_snapshot",
                TRAFIKVERKET_TOOL_DEFINITIONS[17].base_path.format(kamera_id=kamera_id),
                {"kamera_id": kamera_id, "filter": filter},
                f"Trafikverket snapshot {kamera_id}",
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[17].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[17].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[17].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[17].filter_field,
                filter_value=kamera_id,
                limit=1,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[17].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[17].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[17].namespace,
            }

    @tool("trafikverket_kameror_status", description=TRAFIKVERKET_TOOL_DEFINITIONS[18].description)
    async def trafikverket_kameror_status(
        kamera_id: str, filter: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_kameror_status",
                TRAFIKVERKET_TOOL_DEFINITIONS[18].base_path.format(kamera_id=kamera_id),
                {"kamera_id": kamera_id, "filter": filter},
                f"Trafikverket kamera status {kamera_id}",
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[18].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[18].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[18].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[18].filter_field,
                filter_value=kamera_id,
                limit=1,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[18].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[18].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[18].namespace,
            }

    @tool("trafikverket_prognos_trafik", description=TRAFIKVERKET_TOOL_DEFINITIONS[19].description)
    async def trafikverket_prognos_trafik(
        region: str | None = None,
        road: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_prognos_trafik",
                TRAFIKVERKET_TOOL_DEFINITIONS[19].base_path,
                {"region": region, "road": road, "filter": filter},
                f"Trafikverket trafikprognos {region or road or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[19].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[19].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[19].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[19].filter_field,
                filter_value=road or region,
                limit=10,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[19].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[19].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[19].namespace,
            }

    @tool("trafikverket_prognos_vag", description=TRAFIKVERKET_TOOL_DEFINITIONS[20].description)
    async def trafikverket_prognos_vag(
        region: str | None = None,
        road: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_prognos_vag",
                TRAFIKVERKET_TOOL_DEFINITIONS[20].base_path,
                {"region": region, "road": road, "filter": filter},
                f"Trafikverket vägprognos {region or road or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[20].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[20].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[20].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[20].filter_field,
                filter_value=road or region,
                limit=10,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[20].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[20].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[20].namespace,
            }

    @tool("trafikverket_prognos_tag", description=TRAFIKVERKET_TOOL_DEFINITIONS[21].description)
    async def trafikverket_prognos_tag(
        station: str | None = None, filter: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_prognos_tag",
                TRAFIKVERKET_TOOL_DEFINITIONS[21].base_path,
                {"station": station, "filter": filter},
                f"Trafikverket tågprognos {station or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[21].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[21].schema_version,
                namespace=TRAFIKVERKET_TOOL_DEFINITIONS[21].namespace,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[21].filter_field,
                filter_value=station,
                limit=10,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "objecttype": TRAFIKVERKET_TOOL_DEFINITIONS[21].objecttype,
                "schema_version": TRAFIKVERKET_TOOL_DEFINITIONS[21].schema_version,
                "namespace": TRAFIKVERKET_TOOL_DEFINITIONS[21].namespace,
            }

    registry = {
        "trafikverket_trafikinfo_storningar": trafikverket_trafikinfo_storningar,
        "trafikverket_trafikinfo_olyckor": trafikverket_trafikinfo_olyckor,
        "trafikverket_trafikinfo_koer": trafikverket_trafikinfo_koer,
        "trafikverket_trafikinfo_vagarbeten": trafikverket_trafikinfo_vagarbeten,
        "trafikverket_tag_forseningar": trafikverket_tag_forseningar,
        "trafikverket_tag_tidtabell": trafikverket_tag_tidtabell,
        "trafikverket_tag_stationer": trafikverket_tag_stationer,
        "trafikverket_tag_installda": trafikverket_tag_installda,
        "trafikverket_vag_status": trafikverket_vag_status,
        "trafikverket_vag_underhall": trafikverket_vag_underhall,
        "trafikverket_vag_hastighet": trafikverket_vag_hastighet,
        "trafikverket_vag_avstangningar": trafikverket_vag_avstangningar,
        "trafikverket_vader_stationer": trafikverket_vader_stationer,
        "trafikverket_vader_halka": trafikverket_vader_halka,
        "trafikverket_vader_vind": trafikverket_vader_vind,
        "trafikverket_vader_temperatur": trafikverket_vader_temperatur,
        "trafikverket_kameror_lista": trafikverket_kameror_lista,
        "trafikverket_kameror_snapshot": trafikverket_kameror_snapshot,
        "trafikverket_kameror_status": trafikverket_kameror_status,
        "trafikverket_prognos_trafik": trafikverket_prognos_trafik,
        "trafikverket_prognos_vag": trafikverket_prognos_vag,
        "trafikverket_prognos_tag": trafikverket_prognos_tag,
    }
    return registry


def create_trafikverket_tool(
    definition: TrafikverketToolDefinition,
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    api_key: str | None = None,
) -> BaseTool:
    registry = build_trafikverket_tool_registry(
        connector_service=connector_service,
        search_space_id=search_space_id,
        user_id=user_id,
        thread_id=thread_id,
        api_key=api_key,
    )
    return registry[definition.tool_id]
