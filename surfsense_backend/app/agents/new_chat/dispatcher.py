import re
from typing import Any, Iterable

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.new_chat.intent_router import resolve_route_from_intents
from app.agents.new_chat.routing import Route
from app.agents.new_chat.system_prompt import append_datetime_context
from app.services.intent_definition_service import get_default_intent_definitions

_GREETING_REGEX = re.compile(
    r"^(hi|hello|hey|hej|tjena|hallå|yo|god( morgon| kväll| eftermiddag))\b",
    re.IGNORECASE,
)
_COMPARE_COMMAND_RE = re.compile(r"^/compare\b", re.IGNORECASE)
_FOLLOWUP_CONTEXT_RE = re.compile(
    r"\b(också|ocksa|även|aven|samma|där|dar|dit|den|det|dom|dem|denna|denne|kolla|fortsätt|fortsatt)\b",
    re.IGNORECASE,
)

DEFAULT_ROUTE_SYSTEM_PROMPT = (
    "You are a route tie-breaker for SurfSense.\n"
    "A retrieval system already selected candidate routes.\n"
    "Pick the best route using current message plus short history.\n"
    "Return ONLY one route id from the provided candidates.\n"
    "Never invent route ids."
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
    if _COMPARE_COMMAND_RE.match(value):
        return Route.COMPARE
    if _GREETING_REGEX.match(value) and len(value) <= 20:
        return Route.SMALLTALK
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


def _first_non_compare_route(candidates: list[dict[str, Any]] | None) -> Route | None:
    for item in candidates or []:
        route = _normalize_route(str(item.get("route") or ""))
        if route and route not in {Route.COMPARE, Route.SMALLTALK}:
            return route
    return None


async def dispatch_route(
    user_query: str,
    llm,
    *,
    has_attachments: bool = False,
    has_mentions: bool = False,
    system_prompt_override: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    intent_definitions: list[dict[str, Any]] | None = None,
) -> Route:
    route, _meta = await dispatch_route_with_trace(
        user_query,
        llm,
        has_attachments=has_attachments,
        has_mentions=has_mentions,
        system_prompt_override=system_prompt_override,
        conversation_history=conversation_history,
        intent_definitions=intent_definitions,
    )
    return route


async def dispatch_route_with_trace(
    user_query: str,
    llm,
    *,
    has_attachments: bool = False,
    has_mentions: bool = False,
    system_prompt_override: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    intent_definitions: list[dict[str, Any]] | None = None,
) -> tuple[Route, dict[str, Any]]:
    text = (user_query or "").strip()
    if not text:
        return Route.SMALLTALK, {
            "source": "empty_message",
            "confidence": 1.0,
            "reason": "empty_input_defaults_to_smalltalk",
            "candidates": [],
        }

    explicit_route = _infer_rule_based_route(text)
    if explicit_route:
        return explicit_route, {
            "source": "rule",
            "confidence": 0.99,
            "reason": f"rule_match:{explicit_route.value}",
            "candidates": [],
        }

    if has_attachments or has_mentions:
        return Route.KNOWLEDGE, {
            "source": "attachment_or_mention",
            "confidence": 0.98,
            "reason": "attachments_or_mentions_force_knowledge",
            "candidates": [],
        }

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
        and previous_route not in {Route.SMALLTALK}
    ):
        # Special handling for compare followups
        if previous_route == Route.COMPARE:
            return Route.KNOWLEDGE, {
                "source": "compare_followup",
                "confidence": 0.92,
                "reason": "followup_after_compare_routes_to_knowledge",
                "candidates": [],
            }
        # Global continuity rule: preserve prior route for context-dependent follow-ups.
        return previous_route, {
            "source": "followup_continuity",
            "confidence": 0.94,
            "reason": f"followup_preserve:{previous_route.value}",
            "candidates": [],
        }

    normalized_intents = [
        item
        for item in (intent_definitions or list(get_default_intent_definitions().values()))
        if isinstance(item, dict) and bool(item.get("enabled", True))
    ]
    if not previous_route and previous_user_text:
        previous_decision = resolve_route_from_intents(
            query=previous_user_text,
            definitions=normalized_intents,
        )
        if previous_decision and previous_decision.route not in {Route.SMALLTALK}:
            previous_route = previous_decision.route

    explicit_compare = bool(_COMPARE_COMMAND_RE.match(text))

    def remap_non_explicit_compare(
        route: Route,
        *,
        candidates: list[dict[str, Any]] | None = None,
    ) -> Route:
        if route != Route.COMPARE or explicit_compare:
            return route
        if previous_route and previous_route not in {Route.SMALLTALK}:
            # Allow compare followups to preserve compare context
            if previous_route == Route.COMPARE:
                return Route.KNOWLEDGE
            return previous_route
        candidate_route = _first_non_compare_route(candidates)
        if candidate_route:
            return candidate_route
        return Route.KNOWLEDGE

    retrieval_decision = resolve_route_from_intents(
        query=text,
        definitions=normalized_intents,
    )
    if retrieval_decision and retrieval_decision.confidence >= 0.62:
        selected_route = remap_non_explicit_compare(
            retrieval_decision.route,
            candidates=retrieval_decision.candidates,
        )
        if selected_route != retrieval_decision.route:
            return selected_route, {
                "source": "compare_guard",
                "confidence": max(0.5, retrieval_decision.confidence - 0.1),
                "reason": "compare_requires_explicit_/compare_command",
                "candidates": retrieval_decision.candidates,
            }
        return retrieval_decision.route, {
            "source": retrieval_decision.source,
            "confidence": retrieval_decision.confidence,
            "reason": retrieval_decision.reason,
            "candidates": retrieval_decision.candidates,
        }

    try:
        system_prompt = append_datetime_context(
            system_prompt_override or DEFAULT_ROUTE_SYSTEM_PROMPT
        )
        routing_payload: dict[str, Any] = {
            "current_message": text,
            "history": [],
            "candidates": retrieval_decision.candidates if retrieval_decision else [],
            "candidate_routes": sorted(
                {
                    str(item.get("route") or "").strip()
                    for item in (retrieval_decision.candidates if retrieval_decision else [])
                    if str(item.get("route") or "").strip()
                }
            ),
        }
        if safe_history:
            history_lines: list[str] = []
            for item in safe_history:
                role = item.get("role") or "unknown"
                content = re.sub(r"\s+", " ", item.get("content") or "").strip()
                if not content:
                    continue
                history_lines.append(f"{role}: {content[:220]}")
            routing_payload["history"] = history_lines[-6:]
        if retrieval_decision:
            routing_payload["retrieval_route"] = retrieval_decision.route.value
            routing_payload["retrieval_confidence"] = retrieval_decision.confidence
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=str(routing_payload)),
            ]
        )
        llm_route = _normalize_route(str(getattr(response, "content", "") or ""))
        if llm_route:
            guarded_llm_route = remap_non_explicit_compare(
                llm_route,
                candidates=retrieval_decision.candidates if retrieval_decision else [],
            )
            if guarded_llm_route != llm_route:
                return guarded_llm_route, {
                    "source": "compare_guard_llm",
                    "confidence": 0.76,
                    "reason": "llm_compare_blocked_without_/compare_command",
                    "candidates": retrieval_decision.candidates
                    if retrieval_decision
                    else [],
                }
            if (
                is_followup
                and previous_route
                and previous_route not in {Route.SMALLTALK}
                and guarded_llm_route in {Route.KNOWLEDGE, Route.ACTION}
            ):
                # Special handling for compare followups
                if previous_route == Route.COMPARE:
                    return Route.KNOWLEDGE, {
                        "source": "followup_override_compare",
                        "confidence": 0.85,
                        "reason": "followup_after_compare_routes_to_knowledge",
                        "candidates": retrieval_decision.candidates
                        if retrieval_decision
                        else [],
                    }
                return previous_route, {
                    "source": "followup_override",
                    "confidence": 0.85,
                    "reason": f"preserve_previous_route:{previous_route.value}",
                    "candidates": retrieval_decision.candidates
                    if retrieval_decision
                    else [],
                }
            return guarded_llm_route, {
                "source": "llm_tiebreak",
                "confidence": retrieval_decision.confidence
                if retrieval_decision
                else 0.55,
                "reason": f"llm_selected:{guarded_llm_route.value}",
                "candidates": retrieval_decision.candidates if retrieval_decision else [],
            }
        if retrieval_decision:
            fallback_route = remap_non_explicit_compare(
                retrieval_decision.route,
                candidates=retrieval_decision.candidates,
            )
            if fallback_route != retrieval_decision.route:
                return fallback_route, {
                    "source": "compare_guard_fallback",
                    "confidence": max(0.45, retrieval_decision.confidence - 0.15),
                    "reason": "fallback_compare_blocked_without_/compare_command",
                    "candidates": retrieval_decision.candidates,
                }
            return retrieval_decision.route, {
                "source": "intent_retrieval_fallback",
                "confidence": retrieval_decision.confidence,
                "reason": retrieval_decision.reason,
                "candidates": retrieval_decision.candidates,
            }
        fallback_route = previous_route or Route.KNOWLEDGE
        return fallback_route, {
            "source": "fallback",
            "confidence": 0.4 if previous_route else 0.35,
            "reason": "fallback_without_valid_llm_route",
            "candidates": [],
        }
    except Exception:
        if retrieval_decision:
            fallback_route = remap_non_explicit_compare(
                retrieval_decision.route,
                candidates=retrieval_decision.candidates,
            )
            if fallback_route != retrieval_decision.route:
                return fallback_route, {
                    "source": "compare_guard_exception_fallback",
                    "confidence": max(0.4, retrieval_decision.confidence - 0.2),
                    "reason": "exception_compare_blocked_without_/compare_command",
                    "candidates": retrieval_decision.candidates,
                }
            return retrieval_decision.route, {
                "source": "intent_retrieval_exception_fallback",
                "confidence": retrieval_decision.confidence,
                "reason": retrieval_decision.reason,
                "candidates": retrieval_decision.candidates,
            }
        fallback_route = previous_route or Route.KNOWLEDGE
        return fallback_route, {
            "source": "exception_fallback",
            "confidence": 0.33,
            "reason": "dispatcher_exception",
            "candidates": [],
        }
