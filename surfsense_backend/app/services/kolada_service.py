from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx

KOLADA_BASE_URL = "https://api.kolada.se/v3"

_DIACRITIC_MAP = str.maketrans(
    {
        "å": "a",
        "ä": "a",
        "ö": "o",
        "Å": "a",
        "Ä": "a",
        "Ö": "o",
    }
)


@dataclass(frozen=True)
class KoladaKpi:
    id: str
    title: str
    description: str
    operating_area: str
    has_ou_data: bool


@dataclass(frozen=True)
class KoladaMunicipality:
    id: str
    title: str
    type: str


@dataclass(frozen=True)
class KoladaValue:
    kpi: str
    municipality: str
    period: str
    gender: str | None
    value: float | None
    count: int | None


@dataclass(frozen=True)
class KoladaQueryResult:
    kpi: KoladaKpi
    municipality: KoladaMunicipality
    values: list[KoladaValue]
    warnings: list[str]


def _normalize(text: str) -> str:
    """Normalize text by removing diacritics and converting to lowercase."""
    lowered = (text or "").lower().translate(_DIACRITIC_MAP)
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _tokenize(text: str) -> list[str]:
    """Tokenize normalized text into words."""
    normalized = _normalize(text)
    return [token for token in normalized.split() if token]


def _score(query_tokens: set[str], text: str) -> int:
    """Score text based on query token matches."""
    normalized = _normalize(text)
    if not normalized:
        return 0
    score = 0
    for token in query_tokens:
        if token and token in normalized:
            score += 1
    return score


# Known municipalities for common lookups
_KNOWN_MUNICIPALITIES = {
    "stockholm": "0180",
    "goteborg": "1480",
    "göteborg": "1480",
    "malmo": "1280",
    "malmö": "1280",
    "uppsala": "0380",
    "vasteras": "1980",
    "västerås": "1980",
    "orebro": "1880",
    "örebro": "1880",
    "linkoping": "0580",
    "linköping": "0580",
    "helsingborg": "1283",
    "jonkoping": "0680",
    "jönköping": "0680",
    "norrkoping": "0581",
    "norrköping": "0581",
    "lund": "1281",
    "umea": "2480",
    "umeå": "2480",
    "gavle": "2180",
    "gävle": "2180",
    "boras": "1490",
    "borås": "1490",
    "eskilstuna": "0484",
    "sodertalje": "0181",
    "södertälje": "0181",
    "karlstad": "1780",
    "taby": "0160",
    "täby": "0160",
}


class KoladaService:
    """Service for interacting with Kolada API v3."""

    def __init__(
        self,
        base_url: str = KOLADA_BASE_URL,
        timeout: float = 25.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._kpi_cache: dict[str, KoladaKpi] = {}
        self._municipality_cache: dict[str, KoladaMunicipality] = {}

    async def _get_json(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """
        Make GET request with exponential backoff on HTTP 429.
        
        Args:
            endpoint: API endpoint (e.g., "/kpi")
            params: Query parameters
            
        Returns:
            JSON response data
            
        Raises:
            httpx.HTTPStatusError: On non-retryable errors
        """
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 429:
                        # Rate limited - exponential backoff
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            await asyncio.sleep(wait_time)
                            continue
                    
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue
                raise
        
        # If we get here, all retries exhausted
        raise httpx.HTTPStatusError(
            "Max retries exceeded",
            request=response.request,
            response=response,
        )

    async def search_kpis(
        self,
        query: str,
        operating_area: str | None = None,
        per_page: int = 50,
    ) -> list[KoladaKpi]:
        """
        Search for KPIs matching query.
        
        Args:
            query: Search query text
            operating_area: Filter by operating area code (e.g., "V21")
            per_page: Results per page (max 5000)
            
        Returns:
            List of matching KPIs
        """
        params = {"title": query, "per_page": str(per_page)}
        
        try:
            data = await self._get_json("/kpi", params=params)
            
            if not isinstance(data, dict) or "values" not in data:
                return []
            
            kpis = []
            for item in data["values"]:
                if not isinstance(item, dict):
                    continue
                
                kpi_id = str(item.get("id", ""))
                if not kpi_id:
                    continue
                
                # Filter by operating area if specified
                kpi_operating_area = str(item.get("operating_area", ""))
                if operating_area and kpi_operating_area != operating_area:
                    continue
                
                kpi = KoladaKpi(
                    id=kpi_id,
                    title=str(item.get("title", "")),
                    description=str(item.get("description", "")),
                    operating_area=kpi_operating_area,
                    has_ou_data=bool(item.get("has_ou_data", False)),
                )
                kpis.append(kpi)
                
                # Cache the KPI
                self._kpi_cache[kpi_id] = kpi
            
            return kpis
        except httpx.HTTPError:
            return []

    async def get_kpi(self, kpi_id: str) -> KoladaKpi | None:
        """
        Get KPI by ID with caching.
        
        Args:
            kpi_id: KPI identifier
            
        Returns:
            KPI object or None if not found
        """
        # Check cache first
        if kpi_id in self._kpi_cache:
            return self._kpi_cache[kpi_id]
        
        try:
            data = await self._get_json(f"/kpi/{kpi_id}")
            
            if not isinstance(data, dict) or "values" not in data:
                return None
            
            values = data["values"]
            if not values or not isinstance(values[0], dict):
                return None
            
            item = values[0]
            kpi = KoladaKpi(
                id=str(item.get("id", "")),
                title=str(item.get("title", "")),
                description=str(item.get("description", "")),
                operating_area=str(item.get("operating_area", "")),
                has_ou_data=bool(item.get("has_ou_data", False)),
            )
            
            # Cache the result
            self._kpi_cache[kpi_id] = kpi
            return kpi
        except httpx.HTTPError:
            return None

    async def resolve_municipality(self, name_or_id: str) -> KoladaMunicipality | None:
        """
        Resolve municipality by name or 4-digit code.
        
        Args:
            name_or_id: Municipality name or 4-digit code
            
        Returns:
            Municipality object or None if not found
        """
        # Normalize input
        normalized = _normalize(name_or_id)
        
        # Check if it's a known municipality name
        if normalized in _KNOWN_MUNICIPALITIES:
            muni_id = _KNOWN_MUNICIPALITIES[normalized]
            
            # Check cache
            if muni_id in self._municipality_cache:
                return self._municipality_cache[muni_id]
        else:
            # Assume it's an ID
            muni_id = name_or_id
        
        # Fetch from API
        try:
            data = await self._get_json(f"/municipality/{muni_id}")
            
            if not isinstance(data, dict) or "values" not in data:
                return None
            
            values = data["values"]
            if not values or not isinstance(values[0], dict):
                return None
            
            item = values[0]
            municipality = KoladaMunicipality(
                id=str(item.get("id", "")),
                title=str(item.get("title", "")),
                type=str(item.get("type", "")),
            )
            
            # Cache the result
            self._municipality_cache[municipality.id] = municipality
            return municipality
        except httpx.HTTPError:
            return None

    async def get_values(
        self,
        kpi_id: str,
        municipality_id: str,
        years: list[str] | None = None,
    ) -> list[KoladaValue]:
        """
        Get KPI values for a municipality.
        
        Args:
            kpi_id: KPI identifier
            municipality_id: Municipality 4-digit code
            years: List of years to filter (e.g., ["2020", "2021"])
            
        Returns:
            List of values
        """
        try:
            endpoint = f"/data/kpi/{kpi_id}/municipality/{municipality_id}"
            params = {}
            
            if years:
                # Filter by years using year parameter
                params["year"] = ",".join(years)
            
            data = await self._get_json(endpoint, params=params)
            
            if not isinstance(data, dict) or "values" not in data:
                return []
            
            values = []
            for item in data["values"]:
                if not isinstance(item, dict):
                    continue
                
                # Extract values array
                value_items = item.get("values", [])
                if not isinstance(value_items, list):
                    continue
                
                for val_item in value_items:
                    if not isinstance(val_item, dict):
                        continue
                    
                    value = KoladaValue(
                        kpi=str(item.get("kpi", "")),
                        municipality=str(item.get("municipality", "")),
                        period=str(val_item.get("period", "")),
                        gender=val_item.get("gender"),
                        value=val_item.get("value"),
                        count=val_item.get("count"),
                    )
                    values.append(value)
            
            return values
        except httpx.HTTPError:
            return []

    async def get_values_multi(
        self,
        kpi_ids: list[str],
        municipality_id: str,
        years: list[str] | None = None,
    ) -> dict[str, list[KoladaValue]]:
        """
        Get values for multiple KPIs.
        
        Args:
            kpi_ids: List of KPI identifiers
            municipality_id: Municipality 4-digit code
            years: List of years to filter
            
        Returns:
            Dictionary mapping KPI ID to list of values
        """
        # Fetch all KPIs in parallel
        tasks = [
            self.get_values(kpi_id, municipality_id, years)
            for kpi_id in kpi_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build result dictionary
        result: dict[str, list[KoladaValue]] = {}
        for kpi_id, values in zip(kpi_ids, results):
            if isinstance(values, list):
                result[kpi_id] = values
            else:
                result[kpi_id] = []
        
        return result

    async def query(
        self,
        question: str,
        operating_area: str | None = None,
        municipality: str | None = None,
        years: list[str] | None = None,
        max_kpis: int = 5,
    ) -> list[KoladaQueryResult]:
        """
        High-level convenience method to query Kolada data.
        
        Args:
            question: Natural language question
            operating_area: Filter by operating area (e.g., "V21")
            municipality: Municipality name or code
            years: Years to retrieve
            max_kpis: Maximum number of KPIs to return
            
        Returns:
            List of query results with data
        """
        # Search for relevant KPIs
        kpis = await self.search_kpis(question, operating_area=operating_area, per_page=max_kpis * 2)
        
        if not kpis:
            return []
        
        # Score and rank KPIs
        query_tokens = set(_tokenize(question))
        scored_kpis = []
        for kpi in kpis:
            score = _score(query_tokens, kpi.title) * 3 + _score(query_tokens, kpi.description)
            scored_kpis.append((score, kpi))
        
        scored_kpis.sort(key=lambda x: x[0], reverse=True)
        top_kpis = [kpi for _, kpi in scored_kpis[:max_kpis]]
        
        # Resolve municipality if provided
        resolved_muni = None
        if municipality:
            resolved_muni = await self.resolve_municipality(municipality)
            if not resolved_muni:
                # Return results without data if municipality not found
                return [
                    KoladaQueryResult(
                        kpi=kpi,
                        municipality=KoladaMunicipality(id="", title="", type=""),
                        values=[],
                        warnings=[f"Kunde inte hitta kommun: {municipality}"],
                    )
                    for kpi in top_kpis
                ]
        
        # Fetch values for each KPI
        results = []
        for kpi in top_kpis:
            values = []
            warnings = []
            
            if resolved_muni:
                try:
                    values = await self.get_values(kpi.id, resolved_muni.id, years=years)
                except Exception as e:
                    warnings.append(f"Fel vid hämtning av data: {str(e)}")
            
            results.append(
                KoladaQueryResult(
                    kpi=kpi,
                    municipality=resolved_muni or KoladaMunicipality(id="", title="", type=""),
                    values=values,
                    warnings=warnings,
                )
            )
        
        return results
