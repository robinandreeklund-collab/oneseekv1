from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import tool

from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.blocket_tradera_service import BlocketTraderaService
from app.services.connector_service import ConnectorService


@dataclass(frozen=True)
class MarketplaceToolDefinition:
    tool_id: str
    name: str
    category: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    platforms: list[str]


MARKETPLACE_TOOL_DEFINITIONS: list[MarketplaceToolDefinition] = [
    MarketplaceToolDefinition(
        tool_id="marketplace_unified_search",
        name="Unified Marketplace Search",
        category="marketplace_search",
        description=(
            "Sök annonser på både Blocket och Tradera samtidigt. "
            "Använd för att få en bred översikt över marknaden."
        ),
        keywords=["sök", "köp", "sälj", "begagnat", "marknadsplats", "annons"],
        example_queries=[
            "Sök iPhone på marknadsplatser",
            "Vad kostar begagnade cyklar?",
            "Hitta bärbara datorer till salu",
        ],
        platforms=["blocket", "tradera"],
    ),
    MarketplaceToolDefinition(
        tool_id="marketplace_blocket_search",
        name="Blocket Search",
        category="marketplace_search",
        description="Sök annonser på Blocket. Bra för större föremål och lokala affärer.",
        keywords=["blocket", "sök", "köp", "sälj", "begagnat", "annons"],
        example_queries=[
            "Sök möbler på Blocket i Stockholm",
            "Hitta verktyg på Blocket",
            "Blocket annonser för elektronik",
        ],
        platforms=["blocket"],
    ),
    MarketplaceToolDefinition(
        tool_id="marketplace_blocket_cars",
        name="Blocket Bilar",
        category="marketplace_vehicles",
        description="Sök bilar på Blocket. Filtrera efter märke, modell, årsmodell och plats.",
        keywords=["bilar", "bil", "fordon", "volvo", "bmw", "toyota", "begagnad bil"],
        example_queries=[
            "Hitta Volvo V70 i Göteborg",
            "Begagnade bilar under 100000 kr",
            "BMW från 2018 eller senare",
        ],
        platforms=["blocket"],
    ),
    MarketplaceToolDefinition(
        tool_id="marketplace_blocket_boats",
        name="Blocket Båtar",
        category="marketplace_vehicles",
        description="Sök båtar på Blocket. Filtrera efter typ, plats och pris.",
        keywords=["båtar", "båt", "segelbåt", "motorbåt", "sjö"],
        example_queries=[
            "Hitta segelbåtar i Blekinge",
            "Motorbåtar under 200000 kr",
            "Båtar till salu vid västkusten",
        ],
        platforms=["blocket"],
    ),
    MarketplaceToolDefinition(
        tool_id="marketplace_blocket_mc",
        name="Blocket MC",
        category="marketplace_vehicles",
        description="Sök motorcyklar på Blocket. Filtrera efter märke, plats och pris.",
        keywords=["motorcykel", "mc", "moped", "cross", "harley", "yamaha", "honda"],
        example_queries=[
            "Hitta Yamaha motorcyklar",
            "MC under 50000 kr i Skåne",
            "Begagnade Harley Davidson",
        ],
        platforms=["blocket"],
    ),
    MarketplaceToolDefinition(
        tool_id="marketplace_tradera_search",
        name="Tradera Search",
        category="marketplace_search",
        description=(
            "Sök auktioner på Tradera. Bra för samlarobjekt, antikviteter och budgivning. "
            "OBS: Begränsat till 100 anrop per dygn."
        ),
        keywords=["tradera", "auktion", "budgivning", "samlarobjekt", "antikt"],
        example_queries=[
            "Hitta samlarfigurer på Tradera",
            "Auktioner för antikviteter",
            "Tradera annonser för klockor",
        ],
        platforms=["tradera"],
    ),
    MarketplaceToolDefinition(
        tool_id="marketplace_compare_prices",
        name="Jämför Priser",
        category="marketplace_compare",
        description="Jämför priser mellan Blocket och Tradera för samma typ av artikel.",
        keywords=["jämför", "prisjämförelse", "billigast", "pris", "compare"],
        example_queries=[
            "Jämför priser för iPhone 13 på marknadsplatser",
            "Vad är billigast - Blocket eller Tradera för cyklar?",
            "Prisjämförelse för Nintendo Switch",
        ],
        platforms=["blocket", "tradera"],
    ),
    MarketplaceToolDefinition(
        tool_id="marketplace_categories",
        name="Marketplace Kategorier",
        category="marketplace_reference",
        description="Lista tillgängliga kategorier på Blocket och Tradera.",
        keywords=["kategorier", "kategori", "ämnesområde", "avdelning"],
        example_queries=[
            "Vilka kategorier finns på Blocket?",
            "Lista Tradera kategorier",
            "Vilka typer av annonser kan jag söka efter?",
        ],
        platforms=["blocket", "tradera"],
    ),
    MarketplaceToolDefinition(
        tool_id="marketplace_regions",
        name="Marketplace Regioner",
        category="marketplace_reference",
        description="Lista tillgängliga regioner och platser för sökning.",
        keywords=["regioner", "platser", "orter", "län", "städer"],
        example_queries=[
            "Vilka regioner kan jag söka i?",
            "Lista alla orter på Blocket",
            "Vilka län täcks av marknadsplatserna?",
        ],
        platforms=["blocket", "tradera"],
    ),
]


def _build_marketplace_tool(
    definition: MarketplaceToolDefinition,
    *,
    service: BlocketTraderaService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Build a marketplace tool based on definition."""

    description = f"{definition.name}: {definition.description}"

    if definition.tool_id == "marketplace_unified_search":

        async def _unified_search(
            query: str, location: str | None = None, min_price: int | None = None, max_price: int | None = None
        ) -> str:
            """Sök på både Blocket och Tradera samtidigt."""
            if not query.strip():
                return json.dumps({"error": "Tom sökfråga"}, ensure_ascii=True)

            # Search both platforms
            blocket_result = await service.blocket_search(query, location=location, min_price=min_price, max_price=max_price)
            tradera_result = await service.tradera_search(query, min_price=min_price, max_price=max_price)

            combined = {
                "query": query,
                "blocket": blocket_result,
                "tradera": tradera_result,
                "total_results": blocket_result.get("total", 0) + tradera_result.get("total", 0),
            }

            # Ingest for citations
            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=combined,
                title=f"Marknadssök: {query}",
                metadata={"source": "Blocket & Tradera", "query": query, "platforms": ["blocket", "tradera"]},
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service._serialize_external_document(document, score=1.0)
                formatted_docs = format_documents_for_context([serialized])

            response = {"query": query, "results": formatted_docs, "summary": combined}
            return json.dumps(response, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_unified_search)

    elif definition.tool_id == "marketplace_blocket_search":

        async def _blocket_search(
            query: str,
            category: str | None = None,
            location: str | None = None,
            min_price: int | None = None,
            max_price: int | None = None,
        ) -> str:
            """Sök annonser på Blocket."""
            if not query.strip():
                return json.dumps({"error": "Tom sökfråga"}, ensure_ascii=True)

            result = await service.blocket_search(query, category=category, location=location, min_price=min_price, max_price=max_price)

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=result,
                title=f"Blocket: {query}",
                metadata={"source": "Blocket", "query": query, "category": category, "location": location},
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service._serialize_external_document(document, score=1.0)
                formatted_docs = format_documents_for_context([serialized])

            response = {"query": query, "results": formatted_docs, "summary": result}
            return json.dumps(response, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_blocket_search)

    elif definition.tool_id == "marketplace_blocket_cars":

        async def _blocket_cars(
            query: str | None = None,
            make: str | None = None,
            model: str | None = None,
            year_from: int | None = None,
            year_to: int | None = None,
            location: str | None = None,
        ) -> str:
            """Sök bilar på Blocket."""
            result = await service.blocket_search_cars(
                query=query, make=make, model=model, year_from=year_from, year_to=year_to, location=location
            )

            search_desc = f"{make or ''} {model or ''} {query or ''}".strip() or "Bilar"

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=result,
                title=f"Blocket Bilar: {search_desc}",
                metadata={"source": "Blocket", "category": "bilar", "make": make, "model": model},
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service._serialize_external_document(document, score=1.0)
                formatted_docs = format_documents_for_context([serialized])

            response = {"search": search_desc, "results": formatted_docs, "summary": result}
            return json.dumps(response, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_blocket_cars)

    elif definition.tool_id == "marketplace_blocket_boats":

        async def _blocket_boats(
            query: str | None = None,
            boat_type: str | None = None,
            location: str | None = None,
            min_price: int | None = None,
            max_price: int | None = None,
        ) -> str:
            """Sök båtar på Blocket."""
            result = await service.blocket_search_boats(
                query=query, boat_type=boat_type, location=location, min_price=min_price, max_price=max_price
            )

            search_desc = f"{boat_type or ''} {query or ''}".strip() or "Båtar"

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=result,
                title=f"Blocket Båtar: {search_desc}",
                metadata={"source": "Blocket", "category": "båtar", "boat_type": boat_type},
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service._serialize_external_document(document, score=1.0)
                formatted_docs = format_documents_for_context([serialized])

            response = {"search": search_desc, "results": formatted_docs, "summary": result}
            return json.dumps(response, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_blocket_boats)

    elif definition.tool_id == "marketplace_blocket_mc":

        async def _blocket_mc(
            query: str | None = None,
            make: str | None = None,
            location: str | None = None,
            min_price: int | None = None,
            max_price: int | None = None,
        ) -> str:
            """Sök motorcyklar på Blocket."""
            result = await service.blocket_search_mc(query=query, make=make, location=location, min_price=min_price, max_price=max_price)

            search_desc = f"{make or ''} {query or ''}".strip() or "MC"

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=result,
                title=f"Blocket MC: {search_desc}",
                metadata={"source": "Blocket", "category": "mc", "make": make},
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service._serialize_external_document(document, score=1.0)
                formatted_docs = format_documents_for_context([serialized])

            response = {"search": search_desc, "results": formatted_docs, "summary": result}
            return json.dumps(response, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_blocket_mc)

    elif definition.tool_id == "marketplace_tradera_search":

        async def _tradera_search(
            query: str, category_id: int | None = None, min_price: int | None = None, max_price: int | None = None
        ) -> str:
            """Sök auktioner på Tradera. Begränsat till 100 anrop per dygn."""
            if not query.strip():
                return json.dumps({"error": "Tom sökfråga"}, ensure_ascii=True)

            result = await service.tradera_search(query, category_id=category_id, min_price=min_price, max_price=max_price)

            if "error" in result:
                return json.dumps(result, ensure_ascii=True)

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=result,
                title=f"Tradera: {query}",
                metadata={"source": "Tradera", "query": query, "remaining_budget": result.get("remaining_budget")},
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service._serialize_external_document(document, score=1.0)
                formatted_docs = format_documents_for_context([serialized])

            response = {"query": query, "results": formatted_docs, "summary": result}
            return json.dumps(response, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_tradera_search)

    elif definition.tool_id == "marketplace_compare_prices":

        async def _compare_prices(query: str, location: str | None = None) -> str:
            """Jämför priser mellan Blocket och Tradera."""
            if not query.strip():
                return json.dumps({"error": "Tom sökfråga"}, ensure_ascii=True)

            blocket_result = await service.blocket_search(query, location=location)
            tradera_result = await service.tradera_search(query)

            # Calculate price statistics
            blocket_prices = [item.get("price") for item in blocket_result.get("items", []) if item.get("price")]
            tradera_prices = [float(item.get("price")) for item in tradera_result.get("items", []) if item.get("price")]

            comparison = {
                "query": query,
                "blocket": {
                    "count": len(blocket_prices),
                    "avg_price": sum(blocket_prices) / len(blocket_prices) if blocket_prices else None,
                    "min_price": min(blocket_prices) if blocket_prices else None,
                    "max_price": max(blocket_prices) if blocket_prices else None,
                },
                "tradera": {
                    "count": len(tradera_prices),
                    "avg_price": sum(tradera_prices) / len(tradera_prices) if tradera_prices else None,
                    "min_price": min(tradera_prices) if tradera_prices else None,
                    "max_price": max(tradera_prices) if tradera_prices else None,
                },
            }

            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=comparison,
                title=f"Prisjämförelse: {query}",
                metadata={"source": "Blocket & Tradera", "query": query, "type": "price_comparison"},
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )

            formatted_docs = ""
            if document:
                serialized = connector_service._serialize_external_document(document, score=1.0)
                formatted_docs = format_documents_for_context([serialized])

            response = {"query": query, "results": formatted_docs, "comparison": comparison}
            return json.dumps(response, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_compare_prices)

    elif definition.tool_id == "marketplace_categories":

        async def _get_categories(platform: str = "both") -> str:
            """Lista tillgängliga kategorier."""
            categories = {
                "blocket": [
                    "bilar",
                    "batar",
                    "mc",
                    "fordon_ovriga",
                    "bostad",
                    "hem_tradgard",
                    "hem_hushall",
                    "elektronik",
                    "kläder_skor",
                    "fritid_hobby",
                    "sport_fritid",
                    "familj_barn",
                    "djur",
                    "byggnation",
                    "jobb",
                    "tjanster",
                ],
                "tradera": [
                    "antikviteter",
                    "bocker",
                    "datorer",
                    "elektronik",
                    "film",
                    "foto",
                    "hem_tradgard",
                    "kläder_mode",
                    "konst",
                    "musikinstrument",
                    "smycken",
                    "samlarföremål",
                    "sport",
                    "leksaker",
                ],
            }

            if platform.lower() == "blocket":
                result = {"platform": "Blocket", "categories": categories["blocket"]}
            elif platform.lower() == "tradera":
                result = {"platform": "Tradera", "categories": categories["tradera"]}
            else:
                result = {"blocket": categories["blocket"], "tradera": categories["tradera"]}

            return json.dumps(result, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_get_categories)

    elif definition.tool_id == "marketplace_regions":

        async def _get_regions() -> str:
            """Lista tillgängliga regioner."""
            regions = {
                "län": [
                    "Stockholm",
                    "Uppsala",
                    "Södermanland",
                    "Östergötland",
                    "Jönköping",
                    "Kronoberg",
                    "Kalmar",
                    "Gotland",
                    "Blekinge",
                    "Skåne",
                    "Halland",
                    "Västra Götaland",
                    "Värmland",
                    "Örebro",
                    "Västmanland",
                    "Dalarna",
                    "Gävleborg",
                    "Västernorrland",
                    "Jämtland",
                    "Västerbotten",
                    "Norrbotten",
                ],
                "större_städer": [
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
                ],
            }

            return json.dumps(regions, ensure_ascii=True)

        return tool(definition.tool_id, description=description, parse_docstring=False)(_get_regions)

    # Fallback
    async def _placeholder() -> str:
        return json.dumps({"error": f"Tool {definition.tool_id} not yet implemented"}, ensure_ascii=True)

    return tool(definition.tool_id, description=description, parse_docstring=False)(_placeholder)


def build_marketplace_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    marketplace_service: BlocketTraderaService | None = None,
) -> dict[str, Any]:
    """Build registry of marketplace tools."""
    service = marketplace_service or BlocketTraderaService()
    registry: dict[str, Any] = {}

    for definition in MARKETPLACE_TOOL_DEFINITIONS:
        registry[definition.tool_id] = _build_marketplace_tool(
            definition,
            service=service,
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )

    return registry
