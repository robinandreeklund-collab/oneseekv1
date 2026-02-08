import re
from typing import Iterable

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.new_chat.routing import Route

_GREETING_REGEX = re.compile(
    r"^(hi|hello|hey|hej|tjena|hallå|yo|god( morgon| kväll| eftermiddag))\b",
    re.IGNORECASE,
)
_URL_REGEX = re.compile(r"https?://", re.IGNORECASE)

_ACTION_PATTERNS = [
    r"\bpodcast\b",
    r"\bscrape\b",
    r"\bscrap(e|a) .*web\b",
    r"\bsammanfatta .*https?://",
    r"\bread (this|den här) .*https?://",
    r"\bweather\b",
    r"\bväder\b",
    r"\btrafiklab\b",
    r"\bsmhi\b",
    r"\broute\b",
    r"\bresa\b",
    r"\bimage\b",
    r"\bbild\b",
    r"\bvisa\b.*\bimage\b",
    r"\bvisa\b.*\bbild\b",
]

_KNOWLEDGE_PATTERNS = [
    r"\bsearch\b",
    r"\bfind\b",
    r"\blook up\b",
    r"\bmin(a)?\b.*\b(note|notes|anteckningar)\b",
    r"\bcalendar\b",
    r"\bmeeting\b",
    r"\bschedule\b",
    r"\bslack\b",
    r"\bnotion\b",
    r"\bobsidian\b",
    r"\bdrive\b",
    r"\bgithub\b",
    r"\bdocs\b",
    r"\bpolicy\b",
    r"\bremember\b",
    r"\bkom ihåg\b",
]

_ROUTE_SYSTEM_PROMPT = (
    "You are a routing classifier for SurfSense.\n"
    "Decide the best route for the user's message.\n"
    "Return ONLY one of: knowledge, action, smalltalk.\n"
    "Use 'knowledge' for anything that needs searching user data, docs, or memory.\n"
    "Use 'action' for tool execution (scrape, link preview, podcast, weather, routes).\n"
    "Use 'smalltalk' for greetings, chit-chat, or simple conversation without tools."
)


def _matches_any(patterns: Iterable[str], text: str) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _normalize_route(value: str) -> Route | None:
    if not value:
        return None
    lowered = value.strip().lower()
    for route in (Route.KNOWLEDGE, Route.ACTION, Route.SMALLTALK):
        if route.value in lowered:
            return route
    return None


async def dispatch_route(
    user_query: str,
    llm,
    *,
    has_attachments: bool = False,
    has_mentions: bool = False,
) -> Route:
    text = (user_query or "").strip()
    if not text:
        return Route.SMALLTALK

    if has_attachments or has_mentions:
        return Route.KNOWLEDGE

    if _GREETING_REGEX.match(text) and len(text) <= 20:
        return Route.SMALLTALK

    if _URL_REGEX.search(text) or _matches_any(_ACTION_PATTERNS, text):
        return Route.ACTION

    if _matches_any(_KNOWLEDGE_PATTERNS, text):
        return Route.KNOWLEDGE

    try:
        response = await llm.ainvoke(
            [SystemMessage(content=_ROUTE_SYSTEM_PROMPT), HumanMessage(content=text)]
        )
        return _normalize_route(str(getattr(response, "content", "") or "")) or Route.KNOWLEDGE
    except Exception:
        return Route.KNOWLEDGE
