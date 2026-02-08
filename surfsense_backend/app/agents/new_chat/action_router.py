import re
from enum import Enum
from typing import Iterable

from langchain_core.messages import HumanMessage, SystemMessage


class ActionRoute(str, Enum):
    WEB = "web"
    MEDIA = "media"
    TRAVEL = "travel"
    DATA = "data"


_URL_REGEX = re.compile(r"https?://", re.IGNORECASE)

_WEB_PATTERNS = [
    r"\blink\b",
    r"\bweb\b",
    r"\bwebpage\b",
    r"\barticle\b",
    r"\bblog\b",
    r"\bskr?ap(a|e)\b",
    r"\bsammanfatta .*https?://",
    r"\bread .*https?://",
    r"\burl\b",
    r"\bbild\b",
    r"\bimage\b",
]

_MEDIA_PATTERNS = [
    r"\bpodcast\b",
    r"\baudio\b",
    r"\bljud\b",
    r"\bvoice\b",
]

_TRAVEL_PATTERNS = [
    r"\bväder\b",
    r"\bweather\b",
    r"\bsmhi\b",
    r"\btrafiklab\b",
    r"\bresa\b",
    r"\brutt\b",
    r"\broute\b",
    r"\bavgång\b",
    r"\bdeparture\b",
]

_DATA_PATTERNS = [
    r"\blibris\b",
    r"\bjob(ad|b)?\b",
    r"\bjobb\b",
    r"\blediga jobb\b",
    r"\barbetsförmedlingen\b",
    r"\bjobtech\b",
]

DEFAULT_ACTION_ROUTE_PROMPT = (
    "You are a routing classifier for SurfSense action tools.\n"
    "Return ONLY one of: web, media, travel, data.\n"
    "Use 'web' for link previews, scraping, and URL-based tasks.\n"
    "Use 'media' for podcast/audio generation.\n"
    "Use 'travel' for weather and public transport routes.\n"
    "Use 'data' for Libris and job search tools."
)


def _matches_any(patterns: Iterable[str], text: str) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _normalize_route(value: str) -> ActionRoute | None:
    if not value:
        return None
    lowered = value.strip().lower()
    for route in (ActionRoute.WEB, ActionRoute.MEDIA, ActionRoute.TRAVEL, ActionRoute.DATA):
        if route.value in lowered:
            return route
    return None


async def dispatch_action_route(
    user_query: str,
    llm,
    *,
    system_prompt_override: str | None = None,
) -> ActionRoute:
    text = (user_query or "").strip()
    if not text:
        return ActionRoute.WEB

    if _URL_REGEX.search(text) or _matches_any(_WEB_PATTERNS, text):
        return ActionRoute.WEB

    if _matches_any(_MEDIA_PATTERNS, text):
        return ActionRoute.MEDIA

    if _matches_any(_TRAVEL_PATTERNS, text):
        return ActionRoute.TRAVEL

    if _matches_any(_DATA_PATTERNS, text):
        return ActionRoute.DATA

    try:
        system_prompt = system_prompt_override or DEFAULT_ACTION_ROUTE_PROMPT
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=text)]
        )
        return _normalize_route(str(getattr(response, "content", "") or "")) or ActionRoute.WEB
    except Exception:
        return ActionRoute.WEB
