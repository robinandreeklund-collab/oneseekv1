"""Regression tests for synthesizer placeholder rewrites."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage

try:
    from app.agents.new_chat.nodes.synthesizer import build_synthesizer_node
except ModuleNotFoundError as exc:  # pragma: no cover - optional local deps
    pytest.skip(
        f"Skipping synthesizer regression tests because optional dependency is missing: {exc}",
        allow_module_level=True,
    )


class _DummyLLM:
    def __init__(self, content: str):
        self._content = content

    async def ainvoke(self, *_args, **_kwargs):
        class _Message:
            def __init__(self, content: str):
                self.content = content

        return _Message(self._content)


def _extract_first_json_object(payload: str) -> dict:
    return json.loads(payload)


def _latest_user_query(messages):
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return str(message.content or "")
    return ""


@pytest.mark.anyio
async def test_synthesizer_keeps_source_when_llm_returns_guardrail_placeholder():
    source = (
        "För att räkna antalet behöver jag först klargöra vad du menar med "
        "\"utbildningshändelser\"."
    )
    node = build_synthesizer_node(
        llm=_DummyLLM('{"response":"guardrail"}'),
        synthesizer_prompt_template="Synthesize answer",
        compare_synthesizer_prompt_template=None,
        latest_user_query_fn=_latest_user_query,
        append_datetime_context_fn=lambda text: text,
        extract_first_json_object_fn=_extract_first_json_object,
        strip_critic_json_fn=lambda text: text,
    )

    state = {
        "messages": [HumanMessage(content="Räkna antal utbildningshändelser i Jönköping 2024")],
        "final_response": source,
        "final_agent_response": source,
        "final_agent_name": "statistics",
        "graph_complexity": "complex",
        "route_hint": "statistics",
        "resolved_intent": {"intent_id": "statistics"},
    }

    result = await node(state)
    assert result["final_response"] == source
    assert result["final_agent_response"] == source


@pytest.mark.anyio
async def test_synthesizer_accepts_non_degenerate_candidate():
    source = "Rått svar."
    candidate = "Här är en bättre och tydligare sammanfattning av resultatet."
    node = build_synthesizer_node(
        llm=_DummyLLM(json.dumps({"response": candidate}, ensure_ascii=False)),
        synthesizer_prompt_template="Synthesize answer",
        compare_synthesizer_prompt_template=None,
        latest_user_query_fn=_latest_user_query,
        append_datetime_context_fn=lambda text: text,
        extract_first_json_object_fn=_extract_first_json_object,
        strip_critic_json_fn=lambda text: text,
    )

    state = {
        "messages": [HumanMessage(content="Testfråga")],
        "final_response": source,
        "final_agent_response": source,
        "final_agent_name": "statistics",
        "graph_complexity": "complex",
        "route_hint": "statistics",
        "resolved_intent": {"intent_id": "statistics"},
    }

    result = await node(state)
    assert result["final_response"] == candidate
