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
_FOLLOWUP_CONTEXT_RE = re.compile(
    r"\b(också|ocksa|även|aven|samma|där|dar|dit|den|det|dom|dem|denna|denne|kolla|fortsätt|fortsatt)\b",
    re.IGNORECASE,
)

DEFAULT_ROUTE_SYSTEM_PROMPT = (
    "You are a routing classifier for SurfSense.\n"
    "Decide the best route for the user's message.\n"
    "Return ONLY one of: knowledge, action, smalltalk, statistics, compare.\n"
    "Use 'knowledge' for anything that needs searching user data, docs, or memory.\n"
    "Use 'action' for tool execution (scrape, link preview, podcast, weather, routes).\n"
    "Use 'statistics' for SCB/statistics questions and official data requests.\n"
    "Use 'compare' only when the user explicitly starts with /compare.\n"
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
    for route in (
        Route.KNOWLEDGE,
        Route.ACTION,
        Route.SMALLTALK,
        Route.STATISTICS,
        Route.COMPARE,
    ):
        if route.value in lowered:
            return route
    if "statistik" in lowered:
        return Route.STATISTICS
    if "compare" in lowered:
        return Route.COMPARE
    return None


def _infer_rule_based_route(text: str) -> Route | None:
    value = (text or "").strip()
    if not value:
        return None
    if value.lower().startswith("/compare"):
        return Route.COMPARE
    if _GREETING_REGEX.match(value) and len(value) <= 20:
        return Route.SMALLTALK
    if _URL_REGEX.search(value) or _matches_any(_ACTION_PATTERNS, value):
        return Route.ACTION
    if _matches_any(_STATISTICS_PATTERNS, value):
        return Route.STATISTICS
    if _matches_any(_KNOWLEDGE_PATTERNS, value):
        return Route.KNOWLEDGE
    return None


def _looks_context_dependent_followup(text: str) -> bool:
    value = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not value:
        return False
    if len(value) <= 90 and _FOLLOWUP_CONTEXT_RE.search(value):
        return True
    if len(value) <= 70 and value.startswith(("kan du ", "kan ni ", "och ", "hur ", "vad ")):
        return True
    return False


async def dispatch_route(
    user_query: str,
    llm,
    *,
    has_attachments: bool = False,
    has_mentions: bool = False,
    system_prompt_override: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> Route:
    text = (user_query or "").strip()
    if not text:
        return Route.SMALLTALK

    explicit_route = _infer_rule_based_route(text)
    if explicit_route:
        return explicit_route

    if has_attachments or has_mentions:
        return Route.KNOWLEDGE

    safe_history = [
        {
            "role": str(item.get("role") or "").strip().lower(),
            "content": str(item.get("content") or "").strip(),
        }
        for item in (conversation_history or [])
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]
    safe_history = safe_history[-8:]
    previous_user_text = ""
    for item in reversed(safe_history):
        if item.get("role") == "user":
            previous_user_text = item.get("content") or ""
            if previous_user_text:
                break
    previous_route = _infer_rule_based_route(previous_user_text)
    is_followup = _looks_context_dependent_followup(text)
    if (
        is_followup
        and previous_route
        and previous_route not in {Route.SMALLTALK, Route.COMPARE}
    ):
        # Global continuity rule: preserve prior route for context-dependent follow-ups.
        return previous_route

    try:
        system_prompt = append_datetime_context(
            system_prompt_override or DEFAULT_ROUTE_SYSTEM_PROMPT
        )
        routing_input = text
        if safe_history:
            history_lines = []
            for item in safe_history:
                role = item.get("role") or "unknown"
                content = re.sub(r"\s+", " ", item.get("content") or "").strip()
                if not content:
                    continue
                history_lines.append(f"{role}: {content[:220]}")
            if history_lines:
                routing_input = (
                    f"<current_message>\n{text}\n</current_message>\n"
                    "<recent_conversation>\n"
                    + "\n".join(history_lines[-6:])
                    + "\n</recent_conversation>\n"
                    "Use recent conversation to interpret follow-up references."
                )
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=routing_input)]
        )
        llm_route = _normalize_route(str(getattr(response, "content", "") or ""))
        if llm_route:
            if (
                is_followup
                and previous_route
                and previous_route not in {Route.SMALLTALK, Route.COMPARE}
                and llm_route in {Route.KNOWLEDGE, Route.ACTION}
            ):
                return previous_route
            return llm_route
        return previous_route or Route.KNOWLEDGE
    except Exception:
        return previous_route or Route.KNOWLEDGE
