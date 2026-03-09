"""Tests for TrafikanalysService and Trafikanalys tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.trafikanalys_service import (
    TrafikanalysService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    return TrafikanalysService(
        base_url="https://api.trafa.se/api",
        timeout=5.0,
    )


def _mock_data_response(rows=None, name="Personbilar", product_code="T10016"):
    """Build a mock Trafikanalys data API response."""
    return {
        "Header": {
            "Column": [
                {"Name": "ar", "Value": "År", "Type": "D", "Unit": ""},
                {
                    "Name": "itrfslut",
                    "Value": "Antal i trafik",
                    "Type": "M",
                    "Unit": "st",
                },
            ],
            "Description": None,
        },
        "Rows": rows or [],
        "Errors": None,
        "Description": "",
        "Name": name,
        "OriginalName": product_code,
        "Notes": {},
        "NextPublishDate": "0001-01-01T00:00:00",
        "ActiveFrom": "2022-05-10T14:00:00",
        "ValidatedRequestType": "anonymous",
    }


def _mock_row(values: dict[str, str]) -> dict:
    """Build a mock row from a dict of column:value pairs."""
    return {
        "Cell": [
            {
                "Column": col,
                "Value": val,
                "FormattedValue": val,
                "IsMeasure": col.startswith("i")
                or col.startswith("ny")
                or col.startswith("av"),
                "Name": val,
                "NoteIds": [],
                "Description": None,
            }
            for col, val in values.items()
        ]
    }


def _mock_structure_response(products=None):
    """Build a mock structure API response."""
    return {
        "DataCount": 0,
        "StructureItems": products
        or [
            {
                "Id": 1,
                "Name": "t10016",
                "Label": "Personbilar",
                "Type": "P",
                "Selected": False,
            },
            {
                "Id": 2,
                "Name": "t10013",
                "Label": "Lastbilar",
                "Type": "P",
                "Selected": False,
            },
            {
                "Id": 3,
                "Name": "t10011",
                "Label": "Bussar",
                "Type": "P",
                "Selected": False,
            },
        ],
        "ValidatedRequestType": "anonymous",
    }


# ---------------------------------------------------------------------------
# Query builder tests
# ---------------------------------------------------------------------------


class TestQueryBuilder:
    def test_simple_product(self):
        result = TrafikanalysService.build_query("t10016")
        assert result == "t10016"

    def test_product_with_measure(self):
        result = TrafikanalysService.build_query("t10016", "itrfslut")
        assert result == "t10016|itrfslut"

    def test_product_with_measure_and_filter(self):
        result = TrafikanalysService.build_query("t10016", "itrfslut", "ar:2024")
        assert result == "t10016|itrfslut|ar:2024"

    def test_product_with_multiple_parts(self):
        result = TrafikanalysService.build_query(
            "t10016", "itrfslut", "ar:2023,2024", "drivm"
        )
        assert result == "t10016|itrfslut|ar:2023,2024|drivm"

    def test_empty_parts_filtered(self):
        result = TrafikanalysService.build_query("t10016", "itrfslut", "", "ar:2024")
        assert result == "t10016|itrfslut|ar:2024"


# ---------------------------------------------------------------------------
# Structure API tests
# ---------------------------------------------------------------------------


class TestStructureAPI:
    @pytest.mark.asyncio
    async def test_list_products(self, service):
        mock_data = _mock_structure_response()
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ):
            data, cached = await service.list_products()
            assert isinstance(data, dict)
            assert "StructureItems" in data
            assert cached is False

    @pytest.mark.asyncio
    async def test_list_products_cached(self, service):
        mock_data = _mock_structure_response()
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ):
            data1, cached1 = await service.list_products()
            data2, cached2 = await service.list_products()
            assert cached1 is False
            assert cached2 is True
            assert data1 == data2

    @pytest.mark.asyncio
    async def test_get_structure(self, service):
        mock_data = _mock_structure_response()
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ):
            data, cached = await service.get_structure("t10016")
            assert isinstance(data, dict)
            assert cached is False

    @pytest.mark.asyncio
    async def test_get_structure_with_language(self, service):
        mock_data = _mock_structure_response()
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_structure("t10016", lang="en")
            call_url = mock_get.call_args[0][0]
            assert "lang=en" in call_url


# ---------------------------------------------------------------------------
# Data API tests
# ---------------------------------------------------------------------------


class TestDataAPI:
    @pytest.mark.asyncio
    async def test_get_data(self, service):
        mock_data = _mock_data_response(
            rows=[_mock_row({"ar": "2024", "itrfslut": "4977791"})]
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ):
            data, cached = await service.get_data("t10016|itrfslut|ar:2024")
            assert data["Name"] == "Personbilar"
            assert len(data["Rows"]) == 1
            assert cached is False

    @pytest.mark.asyncio
    async def test_get_data_cached(self, service):
        mock_data = _mock_data_response(
            rows=[_mock_row({"ar": "2024", "itrfslut": "4977791"})]
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ):
            data1, cached1 = await service.get_data("t10016|itrfslut|ar:2024")
            data2, cached2 = await service.get_data("t10016|itrfslut|ar:2024")
            assert cached1 is False
            assert cached2 is True

    @pytest.mark.asyncio
    async def test_get_data_multiple_rows(self, service):
        mock_data = _mock_data_response(
            rows=[
                _mock_row({"ar": "2023", "drivm": "Bensin", "itrfslut": "2405521"}),
                _mock_row({"ar": "2023", "drivm": "Diesel", "itrfslut": "1607362"}),
                _mock_row({"ar": "2023", "drivm": "El", "itrfslut": "291678"}),
            ]
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ):
            data, cached = await service.get_data("t10016|itrfslut|ar:2023|drivm")
            assert len(data["Rows"]) == 3


# ---------------------------------------------------------------------------
# Convenience method tests
# ---------------------------------------------------------------------------


class TestConvenienceMethods:
    @pytest.mark.asyncio
    async def test_get_vehicles_in_traffic(self, service):
        mock_data = _mock_data_response(
            rows=[_mock_row({"ar": "2024", "itrfslut": "4977791"})]
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            data, cached = await service.get_vehicles_in_traffic(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t10016" in call_url
            assert "itrfslut" in call_url
            assert "ar:2024" in call_url

    @pytest.mark.asyncio
    async def test_get_vehicles_with_breakdown(self, service):
        mock_data = _mock_data_response(rows=[])
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_vehicles_in_traffic(years="2024", breakdown="drivm")
            call_url = mock_get.call_args[0][0]
            assert "drivm" in call_url

    @pytest.mark.asyncio
    async def test_get_new_registrations(self, service):
        mock_data = _mock_data_response(
            rows=[_mock_row({"ar": "2024", "nyregunder": "277338"})]
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            data, cached = await service.get_new_registrations(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "nyregunder" in call_url

    @pytest.mark.asyncio
    async def test_get_deregistrations(self, service):
        mock_data = _mock_data_response(rows=[])
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_deregistrations(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "avregunder" in call_url

    @pytest.mark.asyncio
    async def test_get_traffic_volume(self, service):
        mock_data = _mock_data_response(
            rows=[], name="Trafikarbete", product_code="T0401"
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_traffic_volume(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t0401" in call_url
            assert "fordonkm" in call_url

    @pytest.mark.asyncio
    async def test_get_driving_licenses(self, service):
        mock_data = _mock_data_response(rows=[], name="Körkort", product_code="T10012")
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_driving_licenses(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t10012" in call_url

    @pytest.mark.asyncio
    async def test_get_traffic_injuries(self, service):
        mock_data = _mock_data_response(
            rows=[], name="Vägtrafikskador", product_code="T1004"
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_traffic_injuries(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t1004" in call_url

    @pytest.mark.asyncio
    async def test_get_maritime_traffic(self, service):
        mock_data = _mock_data_response(rows=[], name="Sjötrafik", product_code="T0802")
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_maritime_traffic(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t0802" in call_url

    @pytest.mark.asyncio
    async def test_get_aviation_statistics(self, service):
        mock_data = _mock_data_response(rows=[], name="Luftfart", product_code="T0501")
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_aviation_statistics(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t0501" in call_url

    @pytest.mark.asyncio
    async def test_get_railway_transport(self, service):
        mock_data = _mock_data_response(
            rows=[], name="Järnvägtransporter", product_code="T0603"
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_railway_transport(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t0603" in call_url

    @pytest.mark.asyncio
    async def test_get_railway_injuries(self, service):
        mock_data = _mock_data_response(
            rows=[], name="Bantrafikskador", product_code="T0602"
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_railway_injuries(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t0602" in call_url

    @pytest.mark.asyncio
    async def test_get_public_transport(self, service):
        mock_data = _mock_data_response(
            rows=[], name="Regional linjetrafik", product_code="T1203"
        )
        with patch.object(
            service, "_get_json", new_callable=AsyncMock, return_value=mock_data
        ) as mock_get:
            await service.get_public_transport(years="2024")
            call_url = mock_get.call_args[0][0]
            assert "t1203" in call_url


# ---------------------------------------------------------------------------
# HTTP client lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_close(self, service):
        # Should not raise even when no client exists
        await service.close()

    def test_client_created_on_demand(self, service):
        client = service._get_client()
        assert client is not None
        assert not client.is_closed


# ---------------------------------------------------------------------------
# Tool definitions validation
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    def test_all_definitions_have_required_fields(self):
        from app.agents.new_chat.tools.trafikanalys import TRAFIKANALYS_TOOL_DEFINITIONS

        for defn in TRAFIKANALYS_TOOL_DEFINITIONS:
            assert defn.tool_id, "tool_id must not be empty"
            assert defn.name, "name must not be empty"
            assert defn.description, "description must not be empty"
            assert len(defn.keywords) >= 3, f"{defn.tool_id}: needs at least 3 keywords"
            assert len(defn.example_queries) >= 2, (
                f"{defn.tool_id}: needs at least 2 example queries"
            )
            assert defn.category, "category must not be empty"

    def test_unique_tool_ids(self):
        from app.agents.new_chat.tools.trafikanalys import TRAFIKANALYS_TOOL_DEFINITIONS

        ids = [d.tool_id for d in TRAFIKANALYS_TOOL_DEFINITIONS]
        assert len(ids) == len(set(ids)), "Duplicate tool IDs found"

    def test_tool_count(self):
        from app.agents.new_chat.tools.trafikanalys import TRAFIKANALYS_TOOL_DEFINITIONS

        assert len(TRAFIKANALYS_TOOL_DEFINITIONS) == 12

    def test_create_all_tools(self):
        from app.agents.new_chat.tools.trafikanalys import (
            TRAFIKANALYS_TOOL_DEFINITIONS,
            create_trafikanalys_tool,
        )

        for defn in TRAFIKANALYS_TOOL_DEFINITIONS:
            tool_instance = create_trafikanalys_tool(defn)
            assert tool_instance is not None
            assert tool_instance.name == defn.tool_id

    def test_all_tool_ids_prefixed(self):
        from app.agents.new_chat.tools.trafikanalys import TRAFIKANALYS_TOOL_DEFINITIONS

        for defn in TRAFIKANALYS_TOOL_DEFINITIONS:
            assert defn.tool_id.startswith("trafikanalys_"), (
                f"{defn.tool_id} must start with 'trafikanalys_'"
            )


# ---------------------------------------------------------------------------
# Response simplification tests
# ---------------------------------------------------------------------------


class TestResponseSimplification:
    def test_simplify_response(self):
        from app.agents.new_chat.tools.trafikanalys import _simplify_response

        raw = _mock_data_response(
            rows=[
                _mock_row({"ar": "2024", "itrfslut": "4977791"}),
                _mock_row({"ar": "2023", "itrfslut": "4900000"}),
            ]
        )
        result = _simplify_response(raw)
        assert result["product"] == "Personbilar"
        assert result["product_code"] == "T10016"
        assert result["row_count"] == 2
        assert len(result["rows"]) == 2
        assert result["rows"][0]["ar"] == "2024"
        assert result["rows"][0]["itrfslut"] == "4977791"

    def test_simplify_empty_response(self):
        from app.agents.new_chat.tools.trafikanalys import _simplify_response

        raw = _mock_data_response(rows=[])
        result = _simplify_response(raw)
        assert result["row_count"] == 0
        assert result["rows"] == []

    def test_simplify_non_dict(self):
        from app.agents.new_chat.tools.trafikanalys import _simplify_response

        result = _simplify_response("not a dict")
        assert "raw" in result

    def test_extract_rows(self):
        from app.agents.new_chat.tools.trafikanalys import _extract_rows

        data = _mock_data_response(
            rows=[
                _mock_row({"ar": "2024", "drivm": "El", "itrfslut": "291678"}),
            ]
        )
        rows = _extract_rows(data)
        assert len(rows) == 1
        assert rows[0]["drivm"] == "El"
        assert rows[0]["itrfslut"] == "291678"
