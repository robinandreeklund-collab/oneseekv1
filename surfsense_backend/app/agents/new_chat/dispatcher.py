import re
from typing import Iterable

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.new_chat.routing import Route
from app.agents.new_chat.system_prompt import append_datetime_context

_GREETING_REGEX = re.compile(
    r"^(hi|hello|hey|hej|tjena|hallå|yo|god( morgon| kväll| eftermiddag))\b",
    re.IGNORECASE,
)
_URL_REGEX = re.compile(r"https?://", re.IGNORECASE)

_ACTION_PATTERNS = [
    r"\bpodcast\b",
    r"\bpodd(ar|en)?\b",
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
    r"\bnyheter\b",
    r"\bsenaste nyheterna\b",
    r"\baktuella händelser\b",
]

_STATISTICS_PATTERNS = [
    r"\bscb\b",
    r"\bstatistik\b",
    r"\bstatistiska centralbyr",
    r"\bpxweb\b",
    r"\bfolkmangd\b",
    r"\bfolkmängd\b",
    r"\bbefolkning\b",
    r"\barbetsloshet\b",
    r"\barbetslöshet\b",
    r"\bsysselsattning\b",
    r"\bsysselsättning\b",
    r"\bskog\b",
    r"\bbnp\b",
    r"\bkpi\b",
    r"\binflation\b",
    r"\bbygglov\b",
    r"\bbostad\b",
    r"\bmiljo\b",
    r"\bmiljö\b",
]

DEFAULT_ROUTE_SYSTEM_PROMPT = (
    "You are a routing classifier for SurfSense.\n"
    "Decide the best route for the user's message.\n"
    "Return ONLY one of: knowledge, action, smalltalk, statistics.\n"
    "Use 'knowledge' for anything that needs searching user data, docs, or memory.\n"
    "Use 'action' for tool execution (scrape, link preview, podcast, weather, routes).\n"
    "Use 'statistics' for SCB/statistics questions and official data requests.\n"
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
    for route in (Route.KNOWLEDGE, Route.ACTION, Route.SMALLTALK, Route.STATISTICS):
        if route.value in lowered:
            return route
    if "statistik" in lowered:
        return Route.STATISTICS
    return None


async def dispatch_route(
    user_query: str,
    llm,
    *,
    has_attachments: bool = False,
    has_mentions: bool = False,
    system_prompt_override: str | None = None,
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

    if _matches_any(_STATISTICS_PATTERNS, text):
        return Route.STATISTICS

    if _matches_any(_KNOWLEDGE_PATTERNS, text):
        return Route.KNOWLEDGE

    try:
        system_prompt = append_datetime_context(
            system_prompt_override or DEFAULT_ROUTE_SYSTEM_PROMPT
        )
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=text)]
        )
        return _normalize_route(str(getattr(response, "content", "") or "")) or Route.KNOWLEDGE
    except Exception:
        return Route.KNOWLEDGE
