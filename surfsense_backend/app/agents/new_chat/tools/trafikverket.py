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
    schema_version: str = "1.0"
    filter_field: str | None = None


TRAFIKVERKET_TOOL_DEFINITIONS: list[TrafikverketToolDefinition] = [
    TrafikverketToolDefinition(
        tool_id="trafikverket_trafikinfo_storningar",
        name="Trafikverket Trafikinfo - Störningar",
        description="Aktuella störningar i trafiken (väg och järnväg).",
        keywords=["störning", "trafikinfo", "trafikverket", "incident"],
        example_queries=[
            "Störningar på E4 idag",
            "Trafikstörningar i Stockholm",
        ],
        base_path="/data.json",
        category="trafikverket_trafikinfo",
        objecttype="Situation",
        filter_field="LocationDescriptor",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_trafikinfo_olyckor",
        name="Trafikverket Trafikinfo - Olyckor",
        description="Olyckor och incidenter i trafiken.",
        keywords=["olycka", "trafikinfo", "incident", "krock"],
        example_queries=[
            "Olyckor på E6",
            "Trafikolyckor i Skåne",
        ],
        base_path="/data.json",
        category="trafikverket_trafikinfo",
        objecttype="Situation",
        filter_field="LocationDescriptor",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_trafikinfo_koer",
        name="Trafikverket Trafikinfo - Köer",
        description="Köer och framkomlighetsproblem på vägar.",
        keywords=["kö", "koer", "trafikinfo", "framkomlighet"],
        example_queries=[
            "Var är det köer i Göteborg?",
            "Köinformation E18",
        ],
        base_path="/data.json",
        category="trafikverket_trafikinfo",
        objecttype="Situation",
        filter_field="LocationDescriptor",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_trafikinfo_vagarbeten",
        name="Trafikverket Trafikinfo - Vägarbeten",
        description="Planerade och pågående vägarbeten.",
        keywords=["vägarbete", "vagarbete", "arbete", "trafikinfo"],
        example_queries=[
            "Pågående vägarbeten i Skåne",
            "Vägarbeten E4",
        ],
        base_path="/data.json",
        category="trafikverket_trafikinfo",
        objecttype="Situation",
        filter_field="LocationDescriptor",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_tag_forseningar",
        name="Trafikverket Tåg - Förseningar",
        description="Tågförseningar per station eller sträcka.",
        keywords=["tåg", "försening", "forsening", "station"],
        example_queries=[
            "Tågförseningar Stockholm C",
            "Förseningar till Göteborg",
        ],
        base_path="/data.json",
        category="trafikverket_tag",
        objecttype="TrainAnnouncement",
        filter_field="AdvertisedLocationName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_tag_tidtabell",
        name="Trafikverket Tåg - Tidtabell",
        description="Tidtabell för tågavgångar/ankomster.",
        keywords=["tidtabell", "tåg", "avgång", "ankomst"],
        example_queries=[
            "Tidtabell Stockholm C idag",
            "Avgångar från Malmö C",
        ],
        base_path="/data.json",
        category="trafikverket_tag",
        objecttype="TrainAnnouncement",
        filter_field="AdvertisedLocationName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_tag_stationer",
        name="Trafikverket Tåg - Stationer",
        description="Stationer och hållplatser för tåg.",
        keywords=["station", "hållplats", "tågstation"],
        example_queries=[
            "Hitta stationer i Uppsala",
            "Stationer som börjar med 'Sundsvall'",
        ],
        base_path="/data.json",
        category="trafikverket_tag",
        objecttype="TrainStation",
        filter_field="AdvertisedLocationName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_tag_installda",
        name="Trafikverket Tåg - Inställda",
        description="Inställda tåg per station/linje.",
        keywords=["inställd", "installd", "tåg", "avgång"],
        example_queries=[
            "Inställda tåg i Göteborg",
            "Inställda avgångar Stockholm C",
        ],
        base_path="/data.json",
        category="trafikverket_tag",
        objecttype="TrainAnnouncement",
        filter_field="AdvertisedLocationName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vag_status",
        name="Trafikverket Väg - Status",
        description="Vägstatus för vägsträckor eller regioner.",
        keywords=["vägstatus", "vagstatus", "väg", "status"],
        example_queries=[
            "Vägstatus E4",
            "Vägstatus i Västra Götaland",
        ],
        base_path="/data.json",
        category="trafikverket_vag",
        objecttype="TrafficFlow",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vag_underhall",
        name="Trafikverket Väg - Underhåll",
        description="Underhållsinformation för vägar.",
        keywords=["underhåll", "underhall", "väg", "vag"],
        example_queries=[
            "Planerat underhåll på E18",
            "Underhållsarbeten i Skåne",
        ],
        base_path="/data.json",
        category="trafikverket_vag",
        objecttype="RoadMaintenance",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vag_hastighet",
        name="Trafikverket Väg - Hastighet",
        description="Aktuella hastighetsbegränsningar.",
        keywords=["hastighet", "fart", "begränsning"],
        example_queries=[
            "Hastighetsbegränsningar på E6",
            "Tillfälliga hastigheter i Stockholm",
        ],
        base_path="/data.json",
        category="trafikverket_vag",
        objecttype="TrafficFlow",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vag_avstangningar",
        name="Trafikverket Väg - Avstängningar",
        description="Vägavstängningar och omledningar.",
        keywords=["avstängning", "avstangning", "omledning", "väg"],
        example_queries=[
            "Vägavstängningar i Uppsala",
            "Avstängningar på E20",
        ],
        base_path="/data.json",
        category="trafikverket_vag",
        objecttype="RoadCondition",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vader_stationer",
        name="Trafikverket Väder - Stationer",
        description="Väderstationer kopplade till trafiknät.",
        keywords=["väderstation", "vaderstation", "station", "väder"],
        example_queries=[
            "Väderstationer i Norrbotten",
            "Stationer i närheten av E4",
        ],
        base_path="/data.json",
        category="trafikverket_vader",
        objecttype="WeatherStation",
        filter_field="CountyName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vader_halka",
        name="Trafikverket Väder - Halka",
        description="Halka och väglag kopplat till väder.",
        keywords=["halka", "väglag", "vader", "vaderlag"],
        example_queries=[
            "Halka i Västerbotten",
            "Väglag E45",
        ],
        base_path="/data.json",
        category="trafikverket_vader",
        objecttype="RoadCondition",
        filter_field="CountyName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vader_vind",
        name="Trafikverket Väder - Vind",
        description="Vindinformation för trafikleder.",
        keywords=["vind", "blåst", "storm", "vader"],
        example_queries=[
            "Vindvarning på Öresundsbron",
            "Vindstyrka i Skåne",
        ],
        base_path="/data.json",
        category="trafikverket_vader",
        objecttype="WeatherStation",
        filter_field="CountyName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_vader_temperatur",
        name="Trafikverket Väder - Temperatur",
        description="Temperaturer kopplat till väderstationer.",
        keywords=["temperatur", "kall", "varm", "vader"],
        example_queries=[
            "Temperatur på E4 idag",
            "Temperaturer i Dalarna",
        ],
        base_path="/data.json",
        category="trafikverket_vader",
        objecttype="WeatherStation",
        filter_field="CountyName",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_kameror_lista",
        name="Trafikverket Kameror - Lista",
        description="Lista trafikkameror per region/väg.",
        keywords=["kamera", "trafikkamera", "kameror", "snapshot"],
        example_queries=[
            "Visa trafikkameror i Stockholm",
            "Kameror längs E4",
        ],
        base_path="/data.json",
        category="trafikverket_kameror",
        objecttype="Camera",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_kameror_snapshot",
        name="Trafikverket Kameror - Snapshot",
        description="Hämta snapshot/aktuellt bildläge från kamera.",
        keywords=["kamera", "snapshot", "bild", "trafikkamera"],
        example_queries=[
            "Snapshot för kamera 12345",
            "Senaste bild från kamera E6-01",
        ],
        base_path="/data.json",
        category="trafikverket_kameror",
        objecttype="Camera",
        filter_field="CameraId",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_kameror_status",
        name="Trafikverket Kameror - Status",
        description="Status för en trafikkamera (online/offline).",
        keywords=["kamera", "status", "online", "offline"],
        example_queries=[
            "Status för kamera 12345",
            "Är kamera E4-10 online?",
        ],
        base_path="/data.json",
        category="trafikverket_kameror",
        objecttype="Camera",
        filter_field="CameraId",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_prognos_trafik",
        name="Trafikverket Prognos - Trafik",
        description="Trafikprognoser per region/väg.",
        keywords=["prognos", "trafik", "framtid", "belastning"],
        example_queries=[
            "Trafikprognos för E4 nästa vecka",
            "Prognos för trafik i Stockholm",
        ],
        base_path="/data.json",
        category="trafikverket_prognos",
        objecttype="TrafficFlow",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_prognos_vag",
        name="Trafikverket Prognos - Väg",
        description="Vägprognoser och planerade arbeten.",
        keywords=["prognos", "väg", "vag", "planering"],
        example_queries=[
            "Vägprognos E18",
            "Planerade arbeten kommande vecka",
        ],
        base_path="/data.json",
        category="trafikverket_prognos",
        objecttype="RoadCondition",
        filter_field="RoadNumber",
    ),
    TrafikverketToolDefinition(
        tool_id="trafikverket_prognos_tag",
        name="Trafikverket Prognos - Tåg",
        description="Tågprognoser och förväntade förseningar.",
        keywords=["prognos", "tåg", "forsening", "försening"],
        example_queries=[
            "Tågprognos Stockholm C",
            "Förväntade förseningar till Göteborg",
        ],
        base_path="/data.json",
        category="trafikverket_prognos",
        objecttype="TrainAnnouncement",
        filter_field="AdvertisedLocationName",
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
        schema_version: str,
        filter_field: str | None,
        filter_value: str | None,
        limit: int,
    ) -> dict[str, Any]:
        data, cached = await service.query(
            objecttype=objecttype,
            schema_version=schema_version,
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
        region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_trafikinfo_storningar",
                TRAFIKVERKET_TOOL_DEFINITIONS[0].base_path,
                {"region": region, "limit": limit},
                f"Trafikverket störningar {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[0].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[0].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[0].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_trafikinfo_olyckor", description=TRAFIKVERKET_TOOL_DEFINITIONS[1].description)
    async def trafikverket_trafikinfo_olyckor(
        region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_trafikinfo_olyckor",
                TRAFIKVERKET_TOOL_DEFINITIONS[1].base_path,
                {"region": region, "limit": limit},
                f"Trafikverket olyckor {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[1].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[1].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[1].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_trafikinfo_koer", description=TRAFIKVERKET_TOOL_DEFINITIONS[2].description)
    async def trafikverket_trafikinfo_koer(
        region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_trafikinfo_koer",
                TRAFIKVERKET_TOOL_DEFINITIONS[2].base_path,
                {"region": region, "limit": limit},
                f"Trafikverket köer {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[2].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[2].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[2].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_trafikinfo_vagarbeten", description=TRAFIKVERKET_TOOL_DEFINITIONS[3].description)
    async def trafikverket_trafikinfo_vagarbeten(
        region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_trafikinfo_vagarbeten",
                TRAFIKVERKET_TOOL_DEFINITIONS[3].base_path,
                {"region": region, "limit": limit},
                f"Trafikverket vägarbeten {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[3].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[3].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[3].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_tag_forseningar", description=TRAFIKVERKET_TOOL_DEFINITIONS[4].description)
    async def trafikverket_tag_forseningar(
        station: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_tag_forseningar",
                TRAFIKVERKET_TOOL_DEFINITIONS[4].base_path,
                {"station": station, "limit": limit},
                f"Trafikverket tågförseningar {station or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[4].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[4].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[4].filter_field,
                filter_value=station,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_tag_tidtabell", description=TRAFIKVERKET_TOOL_DEFINITIONS[5].description)
    async def trafikverket_tag_tidtabell(
        station: str, date: str | None = None
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_tag_tidtabell",
                TRAFIKVERKET_TOOL_DEFINITIONS[5].base_path,
                {"station": station, "date": date},
                f"Trafikverket tidtabell {station}",
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[5].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[5].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[5].filter_field,
                filter_value=station,
                limit=10,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_tag_stationer", description=TRAFIKVERKET_TOOL_DEFINITIONS[6].description)
    async def trafikverket_tag_stationer(
        query: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_tag_stationer",
                TRAFIKVERKET_TOOL_DEFINITIONS[6].base_path,
                {"query": query, "limit": limit},
                f"Trafikverket stationer {query or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[6].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[6].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[6].filter_field,
                filter_value=query,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_tag_installda", description=TRAFIKVERKET_TOOL_DEFINITIONS[7].description)
    async def trafikverket_tag_installda(
        station: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_tag_installda",
                TRAFIKVERKET_TOOL_DEFINITIONS[7].base_path,
                {"station": station, "limit": limit},
                f"Trafikverket inställda {station or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[7].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[7].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[7].filter_field,
                filter_value=station,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_vag_status", description=TRAFIKVERKET_TOOL_DEFINITIONS[8].description)
    async def trafikverket_vag_status(
        road: str | None = None, region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vag_status",
                TRAFIKVERKET_TOOL_DEFINITIONS[8].base_path,
                {"road": road, "region": region, "limit": limit},
                f"Trafikverket vägstatus {road or region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[8].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[8].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[8].filter_field,
                filter_value=road or region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_vag_underhall", description=TRAFIKVERKET_TOOL_DEFINITIONS[9].description)
    async def trafikverket_vag_underhall(
        road: str | None = None, region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vag_underhall",
                TRAFIKVERKET_TOOL_DEFINITIONS[9].base_path,
                {"road": road, "region": region, "limit": limit},
                f"Trafikverket underhåll {road or region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[9].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[9].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[9].filter_field,
                filter_value=road or region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_vag_hastighet", description=TRAFIKVERKET_TOOL_DEFINITIONS[10].description)
    async def trafikverket_vag_hastighet(
        road: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vag_hastighet",
                TRAFIKVERKET_TOOL_DEFINITIONS[10].base_path,
                {"road": road, "limit": limit},
                f"Trafikverket hastighet {road or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[10].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[10].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[10].filter_field,
                filter_value=road,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_vag_avstangningar", description=TRAFIKVERKET_TOOL_DEFINITIONS[11].description)
    async def trafikverket_vag_avstangningar(
        road: str | None = None, region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vag_avstangningar",
                TRAFIKVERKET_TOOL_DEFINITIONS[11].base_path,
                {"road": road, "region": region, "limit": limit},
                f"Trafikverket avstängningar {road or region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[11].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[11].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[11].filter_field,
                filter_value=road or region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_vader_stationer", description=TRAFIKVERKET_TOOL_DEFINITIONS[12].description)
    async def trafikverket_vader_stationer(
        region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vader_stationer",
                TRAFIKVERKET_TOOL_DEFINITIONS[12].base_path,
                {"region": region, "limit": limit},
                f"Trafikverket väderstationer {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[12].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[12].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[12].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_vader_halka", description=TRAFIKVERKET_TOOL_DEFINITIONS[13].description)
    async def trafikverket_vader_halka(
        region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vader_halka",
                TRAFIKVERKET_TOOL_DEFINITIONS[13].base_path,
                {"region": region, "limit": limit},
                f"Trafikverket halka {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[13].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[13].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[13].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_vader_vind", description=TRAFIKVERKET_TOOL_DEFINITIONS[14].description)
    async def trafikverket_vader_vind(
        region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vader_vind",
                TRAFIKVERKET_TOOL_DEFINITIONS[14].base_path,
                {"region": region, "limit": limit},
                f"Trafikverket vind {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[14].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[14].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[14].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_vader_temperatur", description=TRAFIKVERKET_TOOL_DEFINITIONS[15].description)
    async def trafikverket_vader_temperatur(
        region: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_vader_temperatur",
                TRAFIKVERKET_TOOL_DEFINITIONS[15].base_path,
                {"region": region, "limit": limit},
                f"Trafikverket temperatur {region or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[15].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[15].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[15].filter_field,
                filter_value=region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_kameror_lista", description=TRAFIKVERKET_TOOL_DEFINITIONS[16].description)
    async def trafikverket_kameror_lista(
        region: str | None = None, road: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_kameror_lista",
                TRAFIKVERKET_TOOL_DEFINITIONS[16].base_path,
                {"region": region, "road": road, "limit": limit},
                f"Trafikverket kameror {region or road or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[16].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[16].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[16].filter_field,
                filter_value=road or region,
                limit=limit,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_kameror_snapshot", description=TRAFIKVERKET_TOOL_DEFINITIONS[17].description)
    async def trafikverket_kameror_snapshot(kamera_id: str) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_kameror_snapshot",
                TRAFIKVERKET_TOOL_DEFINITIONS[17].base_path.format(kamera_id=kamera_id),
                {"kamera_id": kamera_id},
                f"Trafikverket snapshot {kamera_id}",
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[17].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[17].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[17].filter_field,
                filter_value=kamera_id,
                limit=1,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_kameror_status", description=TRAFIKVERKET_TOOL_DEFINITIONS[18].description)
    async def trafikverket_kameror_status(kamera_id: str) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_kameror_status",
                TRAFIKVERKET_TOOL_DEFINITIONS[18].base_path.format(kamera_id=kamera_id),
                {"kamera_id": kamera_id},
                f"Trafikverket kamera status {kamera_id}",
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[18].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[18].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[18].filter_field,
                filter_value=kamera_id,
                limit=1,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_prognos_trafik", description=TRAFIKVERKET_TOOL_DEFINITIONS[19].description)
    async def trafikverket_prognos_trafik(
        region: str | None = None, road: str | None = None
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_prognos_trafik",
                TRAFIKVERKET_TOOL_DEFINITIONS[19].base_path,
                {"region": region, "road": road},
                f"Trafikverket trafikprognos {region or road or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[19].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[19].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[19].filter_field,
                filter_value=road or region,
                limit=10,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_prognos_vag", description=TRAFIKVERKET_TOOL_DEFINITIONS[20].description)
    async def trafikverket_prognos_vag(
        region: str | None = None, road: str | None = None
    ) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_prognos_vag",
                TRAFIKVERKET_TOOL_DEFINITIONS[20].base_path,
                {"region": region, "road": road},
                f"Trafikverket vägprognos {region or road or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[20].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[20].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[20].filter_field,
                filter_value=road or region,
                limit=10,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @tool("trafikverket_prognos_tag", description=TRAFIKVERKET_TOOL_DEFINITIONS[21].description)
    async def trafikverket_prognos_tag(station: str | None = None) -> dict[str, Any]:
        try:
            return await _wrap(
                "trafikverket_prognos_tag",
                TRAFIKVERKET_TOOL_DEFINITIONS[21].base_path,
                {"station": station},
                f"Trafikverket tågprognos {station or ''}".strip(),
                objecttype=TRAFIKVERKET_TOOL_DEFINITIONS[21].objecttype,
                schema_version=TRAFIKVERKET_TOOL_DEFINITIONS[21].schema_version,
                filter_field=TRAFIKVERKET_TOOL_DEFINITIONS[21].filter_field,
                filter_value=station,
                limit=10,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

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
