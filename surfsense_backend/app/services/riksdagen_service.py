from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

RIKSDAGEN_BASE_URL = "https://data.riksdagen.se"
RIKSDAGEN_SOURCE = "Riksdagens öppna data"
RIKSDAGEN_SOURCE_URL = "https://data.riksdagen.se"
RIKSDAGEN_DEFAULT_TIMEOUT = 30.0

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
class RiksdagenDocument:
    """Represents a document from Riksdagen."""
    
    id: str
    doktyp: str
    rm: str
    beteckning: str
    titel: str
    datum: str | None = None
    organ: str | None = None
    dokumentnamn: str | None = None
    dokument_url_text: str | None = None
    dokument_url_html: str | None = None
    summary: str | None = None


@dataclass(frozen=True)
class RiksdagenVotering:
    """Represents a voting record from Riksdagen."""
    
    votering_id: str
    rm: str
    beteckning: str
    punkt: str
    datum: str | None = None
    rubrik: str | None = None
    utfall: str | None = None
    ja_antal: int | None = None
    nej_antal: int | None = None
    avstår_antal: int | None = None
    frånvarande_antal: int | None = None


@dataclass(frozen=True)
class RiksdagenLedamot:
    """Represents a member of parliament."""
    
    intressent_id: str
    fornamn: str
    efternamn: str
    parti: str | None = None
    valkrets: str | None = None
    status: str | None = None
    bild_url: str | None = None


@dataclass(frozen=True)
class RiksdagenAnforande:
    """Represents a speech/statement in parliament."""
    
    anforande_id: str
    dok_id: str
    rm: str
    anftyp: str
    datum: str | None = None
    talare: str | None = None
    parti: str | None = None
    anforandetext: str | None = None


def _normalize_text(text: str) -> str:
    """Normalize Swedish text for search matching."""
    lowered = (text or "").lower().translate(_DIACRITIC_MAP)
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _parse_document(item: dict[str, Any]) -> RiksdagenDocument | None:
    """Parse a document from API response."""
    try:
        dok_id = str(item.get("id") or item.get("dok_id") or "")
        if not dok_id:
            return None
        
        return RiksdagenDocument(
            id=dok_id,
            doktyp=str(item.get("doktyp") or ""),
            rm=str(item.get("rm") or ""),
            beteckning=str(item.get("beteckning") or ""),
            titel=str(item.get("titel") or item.get("title") or ""),
            datum=item.get("datum") or item.get("publicerad"),
            organ=item.get("organ"),
            dokumentnamn=item.get("dokumentnamn"),
            dokument_url_text=item.get("dokument_url_text"),
            dokument_url_html=item.get("dokument_url_html"),
            summary=item.get("summary") or item.get("notis"),
        )
    except Exception:
        return None


def _parse_votering(item: dict[str, Any]) -> RiksdagenVotering | None:
    """Parse a voting record from API response."""
    try:
        votering_id = str(item.get("votering_id") or item.get("id") or "")
        if not votering_id:
            return None
        
        return RiksdagenVotering(
            votering_id=votering_id,
            rm=str(item.get("rm") or ""),
            beteckning=str(item.get("beteckning") or ""),
            punkt=str(item.get("punkt") or ""),
            datum=item.get("datum"),
            rubrik=item.get("rubrik"),
            utfall=item.get("utfall"),
            ja_antal=item.get("ja_antal"),
            nej_antal=item.get("nej_antal"),
            avstår_antal=item.get("avstar_antal") or item.get("avstår_antal"),
            frånvarande_antal=item.get("franvarande_antal") or item.get("frånvarande_antal"),
        )
    except Exception:
        return None


def _parse_ledamot(item: dict[str, Any]) -> RiksdagenLedamot | None:
    """Parse a member of parliament from API response."""
    try:
        intressent_id = str(item.get("intressent_id") or item.get("id") or "")
        if not intressent_id:
            return None
        
        fornamn = str(item.get("fornamn") or item.get("förnamn") or "")
        efternamn = str(item.get("efternamn") or "")
        
        if not fornamn and not efternamn:
            return None
        
        return RiksdagenLedamot(
            intressent_id=intressent_id,
            fornamn=fornamn,
            efternamn=efternamn,
            parti=item.get("parti"),
            valkrets=item.get("valkrets"),
            status=item.get("status"),
            bild_url=item.get("bild_url") or item.get("bild_url_80") or item.get("bild_url_192"),
        )
    except Exception:
        return None


def _parse_anforande(item: dict[str, Any]) -> RiksdagenAnforande | None:
    """Parse a speech/statement from API response."""
    try:
        anforande_id = str(item.get("anforande_id") or item.get("id") or "")
        if not anforande_id:
            return None
        
        return RiksdagenAnforande(
            anforande_id=anforande_id,
            dok_id=str(item.get("dok_id") or ""),
            rm=str(item.get("rm") or ""),
            anftyp=str(item.get("anftyp") or ""),
            datum=item.get("datum"),
            talare=item.get("talare"),
            parti=item.get("parti"),
            anforandetext=item.get("anforandetext"),
        )
    except Exception:
        return None


class RiksdagenService:
    """Service for communicating with Riksdagen's open data API."""
    
    def __init__(
        self,
        base_url: str = RIKSDAGEN_BASE_URL,
        timeout: float = RIKSDAGEN_DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
    
    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Make GET request and return JSON response."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params or {})
            response.raise_for_status()
            return response.json()
    
    async def search_documents(
        self,
        *,
        sokord: str | None = None,
        doktyp: str | None = None,
        rm: str | None = None,
        from_datum: str | None = None,
        tom_datum: str | None = None,
        organ: str | None = None,
        parti: str | None = None,
        antal: int = 20,
    ) -> list[RiksdagenDocument]:
        """
        Search documents in Riksdagen.
        
        Args:
            sokord: Search term
            doktyp: Document type (prop, mot, bet, etc.)
            rm: Parliamentary year (e.g. "2023/24")
            from_datum: From date (YYYY-MM-DD)
            tom_datum: To date (YYYY-MM-DD)
            organ: Committee (e.g. "FiU", "FöU")
            parti: Party code (s, m, sd, c, v, kd, mp, l, -)
            antal: Maximum number of results (default 20, max 100)
        
        Returns:
            List of RiksdagenDocument objects
        """
        params: dict[str, Any] = {}
        
        if sokord:
            params["sok"] = sokord
        if doktyp:
            params["doktyp"] = doktyp
        if rm:
            params["rm"] = rm
        if from_datum:
            params["from"] = from_datum
        if tom_datum:
            params["tom"] = tom_datum
        if organ:
            params["org"] = organ
        if parti:
            params["parti"] = parti
        
        params["utformat"] = "json"
        params["p"] = min(max(antal, 1), 100)
        
        url = f"{self.base_url}/dokumentlista/"
        
        try:
            data = await self._get_json(url, params)
            
            # Handle different response structures
            if isinstance(data, dict):
                items = data.get("dokumentlista", {}).get("dokument", [])
            elif isinstance(data, list):
                items = data
            else:
                return []
            
            if not isinstance(items, list):
                items = [items] if items else []
            
            documents = []
            for item in items:
                doc = _parse_document(item)
                if doc:
                    documents.append(doc)
            
            return documents[:antal]
        
        except httpx.HTTPError:
            return []
    
    async def search_voteringar(
        self,
        *,
        sokord: str | None = None,
        rm: str | None = None,
        bet: str | None = None,
        punkt: str | None = None,
        from_datum: str | None = None,
        tom_datum: str | None = None,
        parti: str | None = None,
        valkrets: str | None = None,
        iid: str | None = None,
        antal: int = 20,
    ) -> list[RiksdagenVotering]:
        """
        Search voting records in Riksdagen.
        
        Args:
            sokord: Search term
            rm: Parliamentary year
            bet: Committee report number
            punkt: Vote item number
            from_datum: From date (YYYY-MM-DD)
            tom_datum: To date (YYYY-MM-DD)
            parti: Party code
            valkrets: Electoral district
            iid: Member ID
            antal: Maximum number of results
        
        Returns:
            List of RiksdagenVotering objects
        """
        params: dict[str, Any] = {}
        
        if sokord:
            params["sok"] = sokord
        if rm:
            params["rm"] = rm
        if bet:
            params["bet"] = bet
        if punkt:
            params["punkt"] = punkt
        if from_datum:
            params["from"] = from_datum
        if tom_datum:
            params["tom"] = tom_datum
        if parti:
            params["parti"] = parti
        if valkrets:
            params["valkrets"] = valkrets
        if iid:
            params["iid"] = iid
        
        params["utformat"] = "json"
        params["p"] = min(max(antal, 1), 100)
        
        url = f"{self.base_url}/voteringlista/"
        
        try:
            data = await self._get_json(url, params)
            
            if isinstance(data, dict):
                items = data.get("voteringlista", {}).get("votering", [])
            elif isinstance(data, list):
                items = data
            else:
                return []
            
            if not isinstance(items, list):
                items = [items] if items else []
            
            voteringar = []
            for item in items:
                votering = _parse_votering(item)
                if votering:
                    voteringar.append(votering)
            
            return voteringar[:antal]
        
        except httpx.HTTPError:
            return []
    
    async def search_ledamoter(
        self,
        *,
        fnamn: str | None = None,
        enamn: str | None = None,
        parti: str | None = None,
        valkrets: str | None = None,
        iid: str | None = None,
        rdlstatus: str = "samtida",
        antal: int = 20,
    ) -> list[RiksdagenLedamot]:
        """
        Search members of parliament.
        
        Args:
            fnamn: First name
            enamn: Last name
            parti: Party code
            valkrets: Electoral district
            iid: Member ID
            rdlstatus: Status (samtida=current, historisk=historical)
            antal: Maximum number of results
        
        Returns:
            List of RiksdagenLedamot objects
        """
        params: dict[str, Any] = {}
        
        if fnamn:
            params["fnamn"] = fnamn
        if enamn:
            params["enamn"] = enamn
        if parti:
            params["parti"] = parti
        if valkrets:
            params["valkrets"] = valkrets
        if iid:
            params["iid"] = iid
        
        params["rdlstatus"] = rdlstatus
        params["utformat"] = "json"
        params["p"] = min(max(antal, 1), 100)
        
        url = f"{self.base_url}/personlista/"
        
        try:
            data = await self._get_json(url, params)
            
            if isinstance(data, dict):
                items = data.get("personlista", {}).get("person", [])
            elif isinstance(data, list):
                items = data
            else:
                return []
            
            if not isinstance(items, list):
                items = [items] if items else []
            
            ledamoter = []
            for item in items:
                ledamot = _parse_ledamot(item)
                if ledamot:
                    ledamoter.append(ledamot)
            
            return ledamoter[:antal]
        
        except httpx.HTTPError:
            return []
    
    async def search_anforanden(
        self,
        *,
        sokord: str | None = None,
        anftyp: str | None = None,
        rm: str | None = None,
        from_datum: str | None = None,
        tom_datum: str | None = None,
        parti: str | None = None,
        iid: str | None = None,
        antal: int = 20,
    ) -> list[RiksdagenAnforande]:
        """
        Search speeches/statements in parliament.
        
        Args:
            sokord: Search term
            anftyp: Speech type (kam-ad, kam-bu, etc.)
            rm: Parliamentary year
            from_datum: From date (YYYY-MM-DD)
            tom_datum: To date (YYYY-MM-DD)
            parti: Party code
            iid: Member ID
            antal: Maximum number of results
        
        Returns:
            List of RiksdagenAnforande objects
        """
        params: dict[str, Any] = {}
        
        if sokord:
            params["sok"] = sokord
        if anftyp:
            params["anftyp"] = anftyp
        if rm:
            params["rm"] = rm
        if from_datum:
            params["from"] = from_datum
        if tom_datum:
            params["tom"] = tom_datum
        if parti:
            params["parti"] = parti
        if iid:
            params["iid"] = iid
        
        params["utformat"] = "json"
        params["p"] = min(max(antal, 1), 100)
        
        url = f"{self.base_url}/anforandelista/"
        
        try:
            data = await self._get_json(url, params)
            
            if isinstance(data, dict):
                items = data.get("anforandelista", {}).get("anforande", [])
            elif isinstance(data, list):
                items = data
            else:
                return []
            
            if not isinstance(items, list):
                items = [items] if items else []
            
            anforanden = []
            for item in items:
                anforande = _parse_anforande(item)
                if anforande:
                    anforanden.append(anforande)
            
            return anforanden[:antal]
        
        except httpx.HTTPError:
            return []
    
    async def get_dokumentstatus(
        self,
        *,
        dok_id: str,
    ) -> dict[str, Any]:
        """
        Get document status/history.
        
        Args:
            dok_id: Document ID
        
        Returns:
            Dictionary with document status information
        """
        params = {
            "utformat": "json",
        }
        
        url = f"{self.base_url}/dokumentstatus/{dok_id}"
        
        try:
            data = await self._get_json(url, params)
            return data if isinstance(data, dict) else {}
        except httpx.HTTPError:
            return {}
    
    async def list_organ(self) -> list[dict[str, Any]]:
        """
        List all committees (utskott).
        
        Returns:
            List of committee information
        """
        params = {
            "utformat": "json",
        }
        
        url = f"{self.base_url}/organ/"
        
        try:
            data = await self._get_json(url, params)
            
            if isinstance(data, dict):
                items = data.get("organlista", {}).get("organ", [])
            elif isinstance(data, list):
                items = data
            else:
                return []
            
            if not isinstance(items, list):
                items = [items] if items else []
            
            return items
        
        except httpx.HTTPError:
            return []
