import asyncio

from app.services.blocket_tradera_service import (
    BLOCKET_SEARCH_URL,
    BlocketTraderaService,
)


def test_resolve_locations_param_maps_county_aliases():
    service = BlocketTraderaService()

    skane, unresolved_skane = service._resolve_locations_param("Skåne län")
    vastra, unresolved_vastra = service._resolve_locations_param(
        "Västra Götalands län"
    )

    assert skane == ["SKANE"]
    assert unresolved_skane is None
    assert vastra == ["VASTRA_GOTALAND"]
    assert unresolved_vastra is None


def test_normalize_blocket_response_supports_docs_payload_and_limit():
    service = BlocketTraderaService()
    payload = {
        "docs": [
            {
                "id": "20880926",
                "heading": "Nimbus 22 Nova",
                "location": "Nyhamnsläge",
                "canonical_url": "https://www.blocket.se/mobility/item/20880926",
                "price": {"amount": 185000, "currency_code": "SEK"},
                "image": {"url": "https://images.blocketcdn.se/item.jpg"},
                "timestamp": 1771174624000,
                "type": "boat",
                "year": 1992,
                "make": "Nimbus",
                "model": "22 Nova",
            },
            {
                "id": "20861983",
                "heading": "Accantus 78",
                "location": "Limhamn",
                "canonical_url": "https://www.blocket.se/mobility/item/20861983",
                "price": {"amount": 27700, "currency_code": "SEK"},
                "timestamp": 1771120658000,
                "type": "boat",
            },
        ],
        "metadata": {"result_size": {"match_count": 350}},
    }

    normalized = service._normalize_blocket_response(payload, limit=1)

    assert normalized["source"] == "Blocket"
    assert normalized["total"] == 350
    assert len(normalized["items"]) == 1
    first_item = normalized["items"][0]
    assert first_item["title"] == "Nimbus 22 Nova"
    assert first_item["price"] == 185000
    assert first_item["location"] == "Nyhamnsläge"
    assert first_item["url"] == "https://www.blocket.se/mobility/item/20880926"
    assert first_item["type"] == "boat"


def test_normalize_blocket_response_supports_legacy_payload_shape():
    service = BlocketTraderaService()
    payload = {
        "data": [
            {
                "id": "legacy-1",
                "subject": "Legacy item",
                "price": {"value": 1200, "currency": "SEK"},
                "location": {"name": "Stockholm"},
                "share_url": "https://legacy.example/item/legacy-1",
                "image": {"url": "https://legacy.example/item/legacy-1.jpg"},
                "date": "2026-02-16T09:00:00Z",
                "category": "legacy",
            }
        ]
    }

    normalized = service._normalize_blocket_response(payload)
    item = normalized["items"][0]

    assert normalized["source"] == "Blocket"
    assert normalized["total"] == 1
    assert item["id"] == "legacy-1"
    assert item["title"] == "Legacy item"
    assert item["price"] == 1200
    assert item["currency"] == "SEK"
    assert item["location"] == "Stockholm"
    assert item["url"] == "https://legacy.example/item/legacy-1"
    assert item["image"] == "https://legacy.example/item/legacy-1.jpg"


def test_blocket_search_routes_vehicle_category_alias_to_car_endpoint(monkeypatch):
    service = BlocketTraderaService()
    captured: dict[str, object] = {}

    async def _fake_cars(**kwargs):
        captured.update(kwargs)
        return {"source": "Blocket", "total": 1, "items": [{"id": "car-1"}]}

    monkeypatch.setattr(service, "blocket_search_cars", _fake_cars)

    result = asyncio.run(
        service.blocket_search(
            "Volvo V70",
            category="bilar",
            location="Skåne län",
            limit=7,
        )
    )

    assert result["total"] == 1
    assert captured["query"] == "Volvo V70"
    assert captured["location"] == "Skåne län"
    assert captured["limit"] == 7


def test_blocket_search_falls_back_to_query_text_for_unknown_location(monkeypatch):
    service = BlocketTraderaService()
    captured: dict[str, object] = {}

    async def _fake_get(endpoint: str, *, params: dict):
        captured["endpoint"] = endpoint
        captured["params"] = params
        return {"docs": [], "metadata": {"result_size": {"match_count": 0}}}

    monkeypatch.setattr(service, "_blocket_get", _fake_get)

    result = asyncio.run(
        service.blocket_search(
            "kajak",
            location="Sundbyberg centrum",
            limit=5,
        )
    )

    assert result["total"] == 0
    assert captured["endpoint"] == BLOCKET_SEARCH_URL
    params = captured["params"]
    assert isinstance(params, dict)
    assert "locations" not in params
    assert params["query"] == "kajak Sundbyberg centrum"
