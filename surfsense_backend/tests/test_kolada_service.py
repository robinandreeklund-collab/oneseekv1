"""Tests for Kolada service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.kolada_service import (
    KoladaKpi,
    KoladaMunicipality,
    KoladaService,
    KoladaValue,
    _KNOWN_MUNICIPALITIES,
    _normalize,
    _score,
    _tokenize,
)


def test_normalize():
    """Test text normalization with diacritics."""
    assert _normalize("Äldreomsorg") == "aldreomsorg"
    assert _normalize("Göteborg") == "goteborg"
    assert _normalize("Malmö") == "malmo"
    assert _normalize("Test-string 123") == "test string 123"
    assert _normalize("") == ""
    assert _normalize("ÅÄÖ") == "aao"


def test_tokenize():
    """Test tokenization."""
    assert _tokenize("Äldreomsorg i Stockholm") == ["aldreomsorg", "i", "stockholm"]
    assert _tokenize("Test-string 123") == ["test", "string", "123"]
    assert _tokenize("") == []
    assert _tokenize("   multiple   spaces   ") == ["multiple", "spaces"]


def test_score():
    """Test scoring based on token matches."""
    tokens = {"aldreomsorg", "stockholm", "2023"}
    
    assert _score(tokens, "Äldreomsorg i Stockholm 2023") == 3
    assert _score(tokens, "Äldreomsorg") == 1
    assert _score(tokens, "Stockholm") == 1
    assert _score(tokens, "Ingen match") == 0
    assert _score(tokens, "") == 0
    assert _score(set(), "Some text") == 0


def test_known_municipalities():
    """Test that known municipalities dict has required entries."""
    assert len(_KNOWN_MUNICIPALITIES) >= 20
    
    # Test some common municipalities
    assert "stockholm" in _KNOWN_MUNICIPALITIES
    assert _KNOWN_MUNICIPALITIES["stockholm"] == "0180"
    
    assert "goteborg" in _KNOWN_MUNICIPALITIES
    assert _KNOWN_MUNICIPALITIES["goteborg"] == "1480"
    
    assert "malmo" in _KNOWN_MUNICIPALITIES
    assert _KNOWN_MUNICIPALITIES["malmo"] == "1280"
    
    # Test that variants exist
    assert "göteborg" in _KNOWN_MUNICIPALITIES
    assert "malmö" in _KNOWN_MUNICIPALITIES


def test_kolada_service_init():
    """Test KoladaService initialization."""
    service = KoladaService()
    
    assert service.base_url == "https://api.kolada.se/v3"
    assert service.timeout == 25.0
    assert service.max_retries == 3
    assert isinstance(service._kpi_cache, dict)
    assert isinstance(service._municipality_cache, dict)
    
    # Test custom initialization
    custom_service = KoladaService(
        base_url="https://custom.api.se/v3/",
        timeout=30.0,
        max_retries=5,
    )
    assert custom_service.base_url == "https://custom.api.se/v3"
    assert custom_service.timeout == 30.0
    assert custom_service.max_retries == 5


@pytest.mark.asyncio
async def test_search_kpis():
    """Test KPI search with mocked API response."""
    service = KoladaService()
    
    mock_response = {
        "values": [
            {
                "id": "N00945",
                "title": "Antal personer med hemtjänst",
                "description": "Antal personer 65 år och äldre med hemtjänst",
                "operating_area": "V21",
                "has_ou_data": True,
            },
            {
                "id": "N00946",
                "title": "Kostnad hemtjänst",
                "description": "Kostnad per brukare i hemtjänst",
                "operating_area": "V21",
                "has_ou_data": False,
            },
        ]
    }
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        
        kpis = await service.search_kpis("hemtjänst", operating_area="V21")
        
        assert len(kpis) == 2
        assert kpis[0].id == "N00945"
        assert kpis[0].title == "Antal personer med hemtjänst"
        assert kpis[0].operating_area == "V21"
        assert kpis[0].has_ou_data is True
        
        assert kpis[1].id == "N00946"
        assert kpis[1].operating_area == "V21"
        
        # Verify cache
        assert "N00945" in service._kpi_cache
        assert "N00946" in service._kpi_cache


@pytest.mark.asyncio
async def test_search_kpis_filter_by_operating_area():
    """Test KPI search filters by operating area."""
    service = KoladaService()
    
    mock_response = {
        "values": [
            {
                "id": "N00945",
                "title": "KPI 1",
                "description": "Test",
                "operating_area": "V21",
                "has_ou_data": False,
            },
            {
                "id": "N00946",
                "title": "KPI 2",
                "description": "Test",
                "operating_area": "V11",
                "has_ou_data": False,
            },
        ]
    }
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        
        kpis = await service.search_kpis("test", operating_area="V21")
        
        # Should filter to only V21
        assert len(kpis) == 1
        assert kpis[0].id == "N00945"


@pytest.mark.asyncio
async def test_get_kpi_with_cache():
    """Test get_kpi with cache hit and miss."""
    service = KoladaService()
    
    # Test cache miss
    mock_response = {
        "values": [
            {
                "id": "N00945",
                "title": "Test KPI",
                "description": "Test description",
                "operating_area": "V21",
                "has_ou_data": True,
            }
        ]
    }
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        
        kpi = await service.get_kpi("N00945")
        
        assert kpi is not None
        assert kpi.id == "N00945"
        assert kpi.title == "Test KPI"
        assert mock_get.call_count == 1
        
        # Test cache hit
        kpi2 = await service.get_kpi("N00945")
        
        assert kpi2 is not None
        assert kpi2.id == "N00945"
        # Should not call API again
        assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_get_kpi_not_found():
    """Test get_kpi with non-existent KPI."""
    service = KoladaService()
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        
        kpi = await service.get_kpi("INVALID")
        
        assert kpi is None


@pytest.mark.asyncio
async def test_resolve_municipality_by_name():
    """Test municipality resolution by name."""
    service = KoladaService()
    
    mock_response = {
        "values": [
            {
                "id": "0180",
                "title": "Stockholm",
                "type": "K",
            }
        ]
    }
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        
        municipality = await service.resolve_municipality("Stockholm")
        
        assert municipality is not None
        assert municipality.id == "0180"
        assert municipality.title == "Stockholm"
        assert municipality.type == "K"
        
        # Verify cache
        assert "0180" in service._municipality_cache


@pytest.mark.asyncio
async def test_resolve_municipality_by_id():
    """Test municipality resolution by ID."""
    service = KoladaService()
    
    mock_response = {
        "values": [
            {
                "id": "1480",
                "title": "Göteborg",
                "type": "K",
            }
        ]
    }
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        
        municipality = await service.resolve_municipality("1480")
        
        assert municipality is not None
        assert municipality.id == "1480"
        assert municipality.title == "Göteborg"


@pytest.mark.asyncio
async def test_resolve_municipality_not_found():
    """Test municipality resolution for unknown municipality."""
    service = KoladaService()
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        
        municipality = await service.resolve_municipality("INVALID")
        
        assert municipality is None


@pytest.mark.asyncio
async def test_get_values():
    """Test get_values for a KPI and municipality."""
    service = KoladaService()
    
    mock_response = {
        "values": [
            {
                "kpi": "N00945",
                "municipality": "0180",
                "values": [
                    {
                        "period": "2022",
                        "value": 15234.5,
                        "count": 100,
                        "gender": None,
                    },
                    {
                        "period": "2023",
                        "value": 15678.2,
                        "count": 105,
                        "gender": None,
                    },
                ],
            }
        ]
    }
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        
        values = await service.get_values("N00945", "0180", years=["2022", "2023"])
        
        assert len(values) == 2
        assert values[0].kpi == "N00945"
        assert values[0].municipality == "0180"
        assert values[0].period == "2022"
        assert values[0].value == 15234.5
        assert values[0].count == 100
        
        assert values[1].period == "2023"
        assert values[1].value == 15678.2


@pytest.mark.asyncio
async def test_get_values_multi():
    """Test get_values_multi for multiple KPIs."""
    service = KoladaService()
    
    mock_response_1 = {
        "values": [
            {
                "kpi": "N00945",
                "municipality": "0180",
                "values": [{"period": "2023", "value": 100.0, "count": 1, "gender": None}],
            }
        ]
    }
    
    mock_response_2 = {
        "values": [
            {
                "kpi": "N00946",
                "municipality": "0180",
                "values": [{"period": "2023", "value": 200.0, "count": 2, "gender": None}],
            }
        ]
    }
    
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [mock_response_1, mock_response_2]
        
        results = await service.get_values_multi(
            ["N00945", "N00946"], "0180", years=["2023"]
        )
        
        assert "N00945" in results
        assert "N00946" in results
        assert len(results["N00945"]) == 1
        assert len(results["N00946"]) == 1
        assert results["N00945"][0].value == 100.0
        assert results["N00946"][0].value == 200.0


@pytest.mark.asyncio
async def test_query():
    """Test high-level query method."""
    service = KoladaService()
    
    # Mock search_kpis
    mock_kpis = [
        KoladaKpi(
            id="N00945",
            title="Hemtjänst",
            description="Antal personer med hemtjänst",
            operating_area="V21",
            has_ou_data=True,
        )
    ]
    
    # Mock resolve_municipality
    mock_municipality = KoladaMunicipality(
        id="0180",
        title="Stockholm",
        type="K",
    )
    
    # Mock get_values
    mock_values = [
        KoladaValue(
            kpi="N00945",
            municipality="0180",
            period="2023",
            gender=None,
            value=15000.0,
            count=100,
        )
    ]
    
    with patch.object(service, "search_kpis", new_callable=AsyncMock) as mock_search:
        with patch.object(service, "resolve_municipality", new_callable=AsyncMock) as mock_resolve:
            with patch.object(service, "get_values", new_callable=AsyncMock) as mock_get_vals:
                mock_search.return_value = mock_kpis
                mock_resolve.return_value = mock_municipality
                mock_get_vals.return_value = mock_values
                
                results = await service.query(
                    "hemtjänst",
                    operating_area="V21",
                    municipality="Stockholm",
                    years=["2023"],
                    max_kpis=5,
                )
                
                assert len(results) == 1
                assert results[0].kpi.id == "N00945"
                assert results[0].municipality.id == "0180"
                assert len(results[0].values) == 1
                assert results[0].values[0].value == 15000.0


@pytest.mark.asyncio
async def test_query_no_kpis():
    """Test query with no matching KPIs."""
    service = KoladaService()
    
    with patch.object(service, "search_kpis", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        
        results = await service.query("invalid query")
        
        assert len(results) == 0


@pytest.mark.asyncio
async def test_query_municipality_not_found():
    """Test query with invalid municipality."""
    service = KoladaService()
    
    mock_kpis = [
        KoladaKpi(
            id="N00945",
            title="Test",
            description="Test",
            operating_area="V21",
            has_ou_data=False,
        )
    ]
    
    with patch.object(service, "search_kpis", new_callable=AsyncMock) as mock_search:
        with patch.object(service, "resolve_municipality", new_callable=AsyncMock) as mock_resolve:
            mock_search.return_value = mock_kpis
            mock_resolve.return_value = None
            
            results = await service.query("test", municipality="INVALID")
            
            assert len(results) == 1
            assert len(results[0].warnings) == 1
            assert "Kunde inte hitta kommun" in results[0].warnings[0]


@pytest.mark.asyncio
async def test_retry_on_429():
    """Test exponential backoff on HTTP 429 rate limiting."""
    service = KoladaService(max_retries=3)
    
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_request = MagicMock()
    
    call_count = 0
    
    async def mock_get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.HTTPStatusError(
                "Rate limited",
                request=mock_request,
                response=mock_response,
            )
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"values": []}
        success_response.raise_for_status = MagicMock()
        return success_response
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=mock_get_side_effect)
        mock_client_class.return_value = mock_client
        
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await service._get_json("/test")
            
            assert call_count == 3
            # Should have slept twice (2^0=1, 2^1=2)
            assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling for various HTTP errors."""
    service = KoladaService()
    
    # Test 404 Not Found
    with patch.object(service, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        
        kpis = await service.search_kpis("test")
        assert kpis == []
        
        kpi = await service.get_kpi("INVALID")
        assert kpi is None
        
        values = await service.get_values("INVALID", "0180")
        assert values == []
