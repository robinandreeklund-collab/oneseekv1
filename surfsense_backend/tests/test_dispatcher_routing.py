from __future__ import annotations

import importlib.util
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


def test_rule_based_smalltalk_only_for_pure_greeting() -> None:
    route = dispatcher._infer_rule_based_route("Hej!")
    assert route == dispatcher.Route.SMALLTALK


def test_greeting_with_weather_query_is_not_forced_smalltalk() -> None:
    route = dispatcher._infer_rule_based_route("Hej, vad blir vädret i Stockholm i morgon?")
    assert route is None


def test_compare_command_rule_still_has_priority() -> None:
    route = dispatcher._infer_rule_based_route("/compare väder i Malmö")
    assert route == dispatcher.Route.COMPARE
