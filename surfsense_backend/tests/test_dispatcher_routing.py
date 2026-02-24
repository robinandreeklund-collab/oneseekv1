from __future__ import annotations

import asyncio
import importlib.util
from dataclasses import dataclass
from pathlib import Path
import sys
import types

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_APP_PACKAGE = types.ModuleType("app")
_APP_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app")]
sys.modules.setdefault("app", _APP_PACKAGE)

_AGENTS_PACKAGE = types.ModuleType("app.agents")
_AGENTS_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/agents")]
sys.modules.setdefault("app.agents", _AGENTS_PACKAGE)

_NEW_CHAT_PACKAGE = types.ModuleType("app.agents.new_chat")
_NEW_CHAT_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/agents/new_chat")]
sys.modules.setdefault("app.agents.new_chat", _NEW_CHAT_PACKAGE)

_SERVICES_PACKAGE = types.ModuleType("app.services")
_SERVICES_PACKAGE.__path__ = [str(_PROJECT_ROOT / "app/services")]
sys.modules.setdefault("app.services", _SERVICES_PACKAGE)

_FAKE_INTENT_ROUTER = types.ModuleType("app.agents.new_chat.intent_router")
_FAKE_INTENT_ROUTER.resolve_route_from_intents = lambda **_kwargs: None
sys.modules["app.agents.new_chat.intent_router"] = _FAKE_INTENT_ROUTER

_FAKE_INTENT_DEFINITION_SERVICE = types.ModuleType("app.services.intent_definition_service")
_FAKE_INTENT_DEFINITION_SERVICE.get_default_intent_definitions = lambda: {}
sys.modules["app.services.intent_definition_service"] = _FAKE_INTENT_DEFINITION_SERVICE

_spec = importlib.util.spec_from_file_location(
    "dispatcher_routing_test_module",
    _PROJECT_ROOT / "app/agents/new_chat/dispatcher.py",
)
if _spec is None or _spec.loader is None:
    raise RuntimeError("Could not load dispatcher module spec")
dispatcher = importlib.util.module_from_spec(_spec)
sys.modules["dispatcher_routing_test_module"] = dispatcher
_spec.loader.exec_module(dispatcher)


@dataclass(frozen=True)
class _Decision:
    route: object
    confidence: float
    source: str
    reason: str
    candidates: list[dict[str, object]]


def _fake_resolve_route_from_intents(*, query: str, definitions=None):
    text = str(query or "").strip().lower()
    if text.startswith("/compare"):
        return _Decision(
            route=dispatcher.Route.JAMFORELSE,
            confidence=0.95,
            source="intent_retrieval",
            reason="intent_retrieval:jämförelse",
            candidates=[{"intent_id": "jämförelse", "route": "jämförelse", "score": 9.5}],
        )
    if "trafik" in text or "väder" in text or "vader" in text:
        return _Decision(
            route=dispatcher.Route.KUNSKAP,
            confidence=0.93,
            source="intent_retrieval",
            reason="intent_retrieval:kunskap",
            candidates=[
                {"intent_id": "kunskap", "route": "kunskap", "score": 11.2},
            ],
        )
    return _Decision(
        route=dispatcher.Route.KUNSKAP,
        confidence=0.81,
        source="intent_retrieval",
        reason="intent_retrieval:kunskap",
        candidates=[{"intent_id": "kunskap", "route": "kunskap", "score": 8.0}],
    )


def test_rule_based_konversation_only_for_pure_greeting() -> None:
    route = dispatcher._infer_rule_based_route("Hej!")
    assert route == dispatcher.Route.KONVERSATION


def test_greeting_with_weather_query_is_not_forced_konversation() -> None:
    route = dispatcher._infer_rule_based_route("Hej, vad blir vädret i Stockholm i morgon?")
    assert route is None


def test_compare_command_rule_still_has_priority() -> None:
    route = dispatcher._infer_rule_based_route("/compare väder i Malmö")
    assert route == dispatcher.Route.JAMFORELSE


def test_compare_followup_allows_new_kunskap_query_route() -> None:
    original_resolver = dispatcher.resolve_route_from_intents
    dispatcher.resolve_route_from_intents = _fake_resolve_route_from_intents
    try:
        route, meta = asyncio.run(
            dispatcher.dispatch_route_with_trace(
                "Kan du kolla om det finns några trafikstörningar på E4 i Göteborg?",
                llm=None,
                conversation_history=[
                    {"role": "user", "content": "/compare openai och anthropic"},
                ],
                intent_definitions=[
                    {"intent_id": "kunskap", "route": "kunskap", "enabled": True},
                    {"intent_id": "skapande", "route": "skapande", "enabled": True},
                    {"intent_id": "jämförelse", "route": "jämförelse", "enabled": True},
                ],
            )
        )
    finally:
        dispatcher.resolve_route_from_intents = original_resolver

    assert route == dispatcher.Route.KUNSKAP
    assert meta.get("reason") != "followup_after_compare_routes_to_knowledge"


def test_backward_compat_old_route_values() -> None:
    """Old English route values should still resolve via _missing_."""
    assert dispatcher.Route("knowledge") == dispatcher.Route.KUNSKAP
    assert dispatcher.Route("action") == dispatcher.Route.SKAPANDE
    assert dispatcher.Route("smalltalk") == dispatcher.Route.KONVERSATION
    assert dispatcher.Route("compare") == dispatcher.Route.JAMFORELSE
    assert dispatcher.Route("statistics") == dispatcher.Route.KUNSKAP
