from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage


def _load_module(module_name: str, relative_path: str):
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


intent_module = _load_module(
    "intent_resolver_test_module",
    "app/agents/new_chat/nodes/intent.py",
)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self._response_payload = response_payload
        self.called = False

    async def ainvoke(self, _messages: list[Any], max_tokens: int | None = None):
        self.called = True
        return _FakeMessage(json.dumps(self._response_payload, ensure_ascii=True))


def _extract_first_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def test_intent_resolver_applies_weather_override_for_simple_turn() -> None:
    llm = _FakeLLM(
        {
            "intent_id": "knowledge",
            "route": "knowledge",
            "reason": "fallback",
            "confidence": 0.61,
        }
    )

    def _coerce_intent(
        resolved: dict[str, Any],
        latest_user_query: str,
        route_hint: str | None,
    ) -> dict[str, Any]:
        if "vader" in latest_user_query.lower():
            return {
                "intent_id": "action",
                "route": "action",
                "reason": "weather override",
                "confidence": 0.95,
            }
        return resolved

    resolver = intent_module.build_intent_resolver_node(
        llm=llm,
        route_to_intent_id={
            "knowledge": "knowledge",
            "action": "action",
            "statistics": "statistics",
            "compare": "compare",
            "smalltalk": "smalltalk",
        },
        intent_resolver_prompt_template="prompt",
        latest_user_query_fn=lambda _messages: "kan du kolla vader i hjo?",
        parse_hitl_confirmation_fn=lambda _query: None,
        normalize_route_hint_fn=lambda value: str(value or "").strip().lower(),
        intent_from_route_fn=lambda route: {
            "intent_id": str(route or "knowledge"),
            "route": str(route or "knowledge"),
            "reason": "fallback",
            "confidence": 0.4,
        },
        append_datetime_context_fn=lambda prompt: prompt,
        extract_first_json_object_fn=_extract_first_json_object,
        coerce_confidence_fn=_coerce_confidence,
        classify_execution_mode_fn=lambda _intent, _query: "tool_required",
        build_speculative_candidates_fn=lambda _intent, _query: [],
        build_trivial_response_fn=lambda _query: None,
        route_default_agent_fn=lambda route, _query="": (
            "weather" if str(route or "").strip().lower() == "action" else "knowledge"
        ),
        coerce_resolved_intent_fn=_coerce_intent,
    )

    result = asyncio.run(resolver({"messages": []}))
    assert result.get("resolved_intent", {}).get("route") == "action"
    assert result.get("route_hint") == "action"
    selected_agents = result.get("selected_agents") or []
    assert selected_agents and selected_agents[0].get("name") == "weather"
    assert llm.called is True


def test_intent_resolver_propagates_route_hint_without_llm_roundtrip() -> None:
    llm = _FakeLLM(
        {
            "intent_id": "knowledge",
            "route": "knowledge",
            "reason": "unused",
            "confidence": 0.5,
        }
    )

    resolver = intent_module.build_intent_resolver_node(
        llm=llm,
        route_to_intent_id={
            "knowledge": "knowledge",
            "action": "action",
            "statistics": "statistics",
            "compare": "compare",
            "smalltalk": "smalltalk",
        },
        intent_resolver_prompt_template="prompt",
        latest_user_query_fn=lambda _messages: "visa statistik for goteborg",
        parse_hitl_confirmation_fn=lambda _query: None,
        normalize_route_hint_fn=lambda value: str(value or "").strip().lower(),
        intent_from_route_fn=lambda route: {
            "intent_id": str(route or "knowledge"),
            "route": str(route or "knowledge"),
            "reason": "fallback",
            "confidence": 0.5,
        },
        append_datetime_context_fn=lambda prompt: prompt,
        extract_first_json_object_fn=_extract_first_json_object,
        coerce_confidence_fn=_coerce_confidence,
        classify_execution_mode_fn=lambda _intent, _query: "tool_required",
        build_speculative_candidates_fn=lambda _intent, _query: [],
        build_trivial_response_fn=lambda _query: None,
        route_default_agent_fn=lambda route, _query="": str(route or "knowledge"),
        coerce_resolved_intent_fn=None,
    )

    result = asyncio.run(
        resolver(
            {
                "messages": [],
                "route_hint": "statistics",
            }
        )
    )
    assert result.get("resolved_intent", {}).get("route") == "statistics"
    assert result.get("route_hint") == "statistics"
    assert llm.called is False


def test_intent_resolver_reclassifies_when_turn_id_missing_but_new_human_message() -> None:
    llm = _FakeLLM(
        {
            "intent_id": "smalltalk",
            "route": "smalltalk",
            "reason": "stale",
            "confidence": 0.85,
        }
    )

    def _coerce_intent(
        resolved: dict[str, Any],
        latest_user_query: str,
        route_hint: str | None,
    ) -> dict[str, Any]:
        if "vader" in latest_user_query.lower():
            return {
                "intent_id": "action",
                "route": "action",
                "reason": "weather override",
                "confidence": 0.95,
            }
        return resolved

    resolver = intent_module.build_intent_resolver_node(
        llm=llm,
        route_to_intent_id={
            "knowledge": "knowledge",
            "action": "action",
            "statistics": "statistics",
            "compare": "compare",
            "smalltalk": "smalltalk",
        },
        intent_resolver_prompt_template="prompt",
        latest_user_query_fn=lambda messages: str(
            getattr((messages or [])[-1], "content", "") or ""
        ).strip(),
        parse_hitl_confirmation_fn=lambda _query: None,
        normalize_route_hint_fn=lambda value: str(value or "").strip().lower(),
        intent_from_route_fn=lambda route: {
            "intent_id": str(route or "knowledge"),
            "route": str(route or "knowledge"),
            "reason": "fallback",
            "confidence": 0.5,
        },
        append_datetime_context_fn=lambda prompt: prompt,
        extract_first_json_object_fn=_extract_first_json_object,
        coerce_confidence_fn=_coerce_confidence,
        classify_execution_mode_fn=lambda _intent, _query: "tool_required",
        build_speculative_candidates_fn=lambda _intent, _query: [],
        build_trivial_response_fn=lambda _query: None,
        route_default_agent_fn=lambda route, _query="": (
            "weather" if str(route or "").strip().lower() == "action" else "knowledge"
        ),
        coerce_resolved_intent_fn=_coerce_intent,
    )

    state = {
        "messages": [
            HumanMessage(content="hej"),
            AIMessage(content="Hej!"),
            HumanMessage(content="kan du kolla vader i hjo?"),
        ],
        "resolved_intent": {
            "intent_id": "smalltalk",
            "route": "smalltalk",
            "reason": "stale smalltalk",
            "confidence": 0.95,
        },
        "graph_complexity": "trivial",
        "orchestration_phase": "finalize",
    }

    result = asyncio.run(resolver(state))
    assert result.get("resolved_intent", {}).get("route") == "action"
    assert result.get("route_hint") == "action"
    assert str(result.get("active_turn_id") or "").startswith("implicit_turn:")
    assert llm.called is True

