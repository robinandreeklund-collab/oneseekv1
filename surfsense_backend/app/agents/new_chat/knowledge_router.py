import re
from enum import Enum
from typing import Iterable

from langchain_core.messages import HumanMessage, SystemMessage


class KnowledgeRoute(str, Enum):
    DOCS = "docs"
    INTERNAL = "internal"
    EXTERNAL = "external"


_DOCS_PATTERNS = [
    r"\bsurfsense\b",
    r"\bdokumentation\b",
    r"\bdocs\b",
    r"\binstall\b",
    r"\bconnector\b",
    r"\bintegration\b",
    r"\bkonfigurera\b",
    r"\bsetup\b",
    r"\bapi\b",
    r"\bskapa (en )?workspace\b",
]

_EXTERNAL_PATTERNS = [
    r"\bnews\b",
    r"\bsenaste\b",
    r"\bnyheter\b",
    r"\baktuellt\b",
    r"\binternet\b",
    r"\bwebben\b",
    r"\btavily\b",
    r"\bextern(a|t)?\b",
    r"\bpublic\b",
    r"\brealtid\b",
]

DEFAULT_KNOWLEDGE_ROUTE_PROMPT = (
    "You are a routing classifier for SurfSense knowledge search.\n"
    "Decide the best route for the user's question.\n"
    "Return ONLY one of: docs, internal, external.\n"
    "Use 'docs' for SurfSense application questions.\n"
    "Use 'internal' for questions about the user's knowledge base.\n"
    "Use 'external' for real-time web search needs."
)


def _matches_any(patterns: Iterable[str], text: str) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _normalize_route(value: str) -> KnowledgeRoute | None:
    if not value:
        return None
    lowered = value.strip().lower()
    for route in (KnowledgeRoute.DOCS, KnowledgeRoute.INTERNAL, KnowledgeRoute.EXTERNAL):
        if route.value in lowered:
            return route
    return None


async def dispatch_knowledge_route(
    user_query: str,
    llm,
    *,
    has_attachments: bool = False,
    has_mentions: bool = False,
    allow_external: bool = True,
    system_prompt_override: str | None = None,
) -> KnowledgeRoute:
    text = (user_query or "").strip()
    if not text:
        return KnowledgeRoute.INTERNAL

    if has_attachments or has_mentions:
        return KnowledgeRoute.INTERNAL

    if _matches_any(_DOCS_PATTERNS, text):
        return KnowledgeRoute.DOCS

    if allow_external and _matches_any(_EXTERNAL_PATTERNS, text):
        return KnowledgeRoute.EXTERNAL

    try:
        system_prompt = system_prompt_override or DEFAULT_KNOWLEDGE_ROUTE_PROMPT
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=text),
            ]
        )
        resolved = _normalize_route(str(getattr(response, "content", "") or ""))
        if resolved is not None:
            if not allow_external and resolved == KnowledgeRoute.EXTERNAL:
                return KnowledgeRoute.INTERNAL
            return resolved
    except Exception:
        return KnowledgeRoute.INTERNAL

    return KnowledgeRoute.INTERNAL
