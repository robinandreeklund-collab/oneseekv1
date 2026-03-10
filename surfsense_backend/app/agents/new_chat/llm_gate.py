"""LLM Gate — pure LLM-based routing for intent / agent / tool selection.

When ``llm_gate_mode`` is enabled in the retrieval tuning configuration, these
helpers replace all embedding + reranker logic with direct LLM calls.

Uses the same structured output pattern (``response_format`` with Pydantic
JSON Schema strict mode) as the rest of the LangGraph graph to guarantee
consistent quality and reliable parsing via Nemotron / LM Studio.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .structured_schemas import (
    LlmGateAgentResult,
    LlmGateIntentResult,
    LlmGateToolResult,
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)

# Regex for extracting "chosen" from truncated/malformed JSON.
# Handles both string and integer values.
_CHOSEN_RE = re.compile(r'"chosen"\s*:\s*(?:"([^"]+)"|(\d+))')
_CHOSEN_LIST_RE = re.compile(r'"chosen"\s*:\s*\[([^\]]*)\]')
_REASONING_RE = re.compile(r'"reasoning"\s*:\s*"([^"]*)"')


def _extract_field_from_partial_json(
    raw: str,
    field: str = "chosen",
) -> str | int:
    """Extract a field value from potentially truncated JSON output.

    This handles the common case where the LLM's JSON output is cut off
    due to max_tokens but the target field was already fully written.
    Returns int for numeric chosen values, str otherwise.
    """
    if field == "chosen":
        m = _CHOSEN_RE.search(raw)
        if not m:
            return ""
        # Group 1 = string value, Group 2 = integer value
        if m.group(2) is not None:
            return int(m.group(2))
        return m.group(1).strip()
    if field == "reasoning":
        m = _REASONING_RE.search(raw)
        return m.group(1).strip() if m else ""
    return ""


def _extract_chosen_list_from_partial_json(raw: str) -> list[str]:
    """Extract a list-valued 'chosen' field from partial JSON."""
    m = _CHOSEN_LIST_RE.search(raw)
    if not m:
        return []
    inner = m.group(1)
    return [s.strip().strip('"').strip("'") for s in inner.split(",") if s.strip().strip('"').strip("'")]


def _format_candidate_list(
    items: list[tuple[str, str]],
    *,
    numbered: bool = False,
) -> str:
    """Format candidates as '- id — description'.

    When *numbered* is True, prefix each line with its 1-based index
    so the LLM can refer to candidates by number instead of spelling
    out the (potentially complex Swedish) ID.
    """
    if numbered:
        return "\n".join(
            f"- idx={i} {item_id} — {desc}"
            for i, (item_id, desc) in enumerate(items, start=1)
        )
    return "\n".join(f"- {item_id} — {desc}" for item_id, desc in items)


def _resolve_llm_choice(raw: str, sorted_keys: list[str]) -> str:
    """Resolve an LLM response to an actual ID from the candidate list.

    Handles exact, case-insensitive, substring, hyphen-normalized,
    and numeric (1-based index) fallback matching.
    """
    if not raw:
        return ""
    if raw in sorted_keys:
        return raw
    lower = raw.lower()
    for key in sorted_keys:
        if key.lower() == lower:
            return key
    for key in sorted_keys:
        if lower in key.lower() or key.lower() in lower:
            return key
    norm = lower.replace("-", "")
    for key in sorted_keys:
        if key.lower().replace("-", "") == norm:
            return key
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(sorted_keys):
            return sorted_keys[idx]
    except ValueError:
        pass
    return raw


async def llm_gate_select_intent(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    llm: Any = None,
) -> dict[str, Any]:
    """Select intent domain using a structured LLM call.

    When ``llm`` is provided, uses the same ``response_format`` +
    Pydantic dual-parsing pattern as the rest of the LangGraph graph.
    Falls back to ``nexus_llm_call`` with text parsing only when no
    ``llm`` is provided (backward compat).

    Returns ``{"chosen": domain_id, "reasoning": str, "candidates_shown": int}``.
    """
    sorted_ids = sorted(
        str(c.get("intent_id") or c.get("domain_id") or "").strip()
        for c in candidates
        if str(c.get("intent_id") or c.get("domain_id") or "").strip()
    )
    items: list[tuple[str, str]] = []
    for c in candidates:
        cid = str(c.get("intent_id") or c.get("domain_id") or "").strip()
        desc = str(c.get("description") or "").strip()
        if cid:
            items.append((cid, desc))

    # Build idx→domain_id mapping for resolving the numeric response
    _idx_to_id: dict[int, str] = {
        i: item_id for i, (item_id, _) in enumerate(items, start=1)
    }

    system_prompt = (
        "Du är en intent-router. Givet användarens fråga, välj EXAKT EN domän "
        "från listan som bäst matchar frågan.\n\n"
        "Resonera semantiskt — förstå vad användaren faktiskt menar, "
        "inte bara vilka ord som förekommer i frågan.\n\n"
        "Tänk ALLTID på svenska i din interna resonering.\n"
        "I din motivering: beskriv VARFÖR domänen passar, "
        "men nämn ALDRIG 'domänlistan', 'nyckelord', 'agentlistan' "
        "eller andra interna systembegrepp.\n\n"
        "Domäner:\n" + _format_candidate_list(items, numbered=True) + "\n\n"
        "VIKTIGT: Svara med domänens numeriska idx-värde (heltal), "
        "INTE textnamnet."
    )
    user_prompt = f"Fråga: {query}"

    chosen = ""
    reasoning = ""
    try:
        if llm is not None:
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 400}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    LlmGateIntentResult, "llm_gate_intent_result"
                )
            message = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
                **_invoke_kwargs,
            )
            _raw = str(getattr(message, "content", "") or "")
            _chosen_raw: int | str = ""
            try:
                _structured = LlmGateIntentResult.model_validate_json(_raw)
                _chosen_raw = _structured.chosen
                reasoning = _structured.reasoning
            except Exception:
                m = re.search(r"\{[\s\S]*\}", _raw)
                if m:
                    try:
                        parsed = json.loads(m.group())
                        _chosen_raw = parsed.get("chosen", "")
                        reasoning = str(parsed.get("reasoning") or "").strip()
                    except json.JSONDecodeError:
                        # Truncated JSON — extract fields via regex
                        _chosen_raw = _extract_field_from_partial_json(_raw, "chosen")
                        reasoning = _extract_field_from_partial_json(_raw, "reasoning")
                if not _chosen_raw and _chosen_raw != 0:
                    for line in _raw.strip().splitlines():
                        ls = line.strip()
                        if ls.upper().startswith("DOMÄN:") or ls.upper().startswith("DOMAIN:"):
                            _chosen_raw = ls.split(":", 1)[1].strip()
                        elif ls.upper().startswith("MOTIVERING:"):
                            reasoning = ls.split(":", 1)[1].strip()
            # Resolve numeric idx → domain_id string
            if isinstance(_chosen_raw, int) and _chosen_raw in _idx_to_id:
                chosen = _idx_to_id[_chosen_raw]
            elif isinstance(_chosen_raw, str):
                # Try parsing as int (e.g. "5")
                try:
                    _int_val = int(_chosen_raw)
                    chosen = _idx_to_id.get(_int_val, _chosen_raw)
                except ValueError:
                    chosen = _chosen_raw
            else:
                chosen = str(_chosen_raw)
        else:
            # Backward compat: no llm provided → use nexus_llm_call
            from app.nexus.llm import nexus_llm_call

            prompt = system_prompt + "\n\n" + user_prompt + (
                "\n\nSvara EXAKT i detta format (inget annat):\n"
                "MOTIVERING: <en mening som förklarar varför just denna domän matchar>\n"
                "IDX: <numeriskt index>\n"
            )
            response = await nexus_llm_call(prompt)
            for line in response.strip().splitlines():
                ls = line.strip()
                if ls.upper().startswith("IDX:"):
                    _idx_str = ls.split(":", 1)[1].strip()
                    try:
                        _idx_val = int(_idx_str)
                        if _idx_val in _idx_to_id:
                            chosen = _idx_to_id[_idx_val]
                    except ValueError:
                        chosen = _idx_str
                elif ls.upper().startswith("MOTIVERING:"):
                    reasoning = ls.split(":", 1)[1].strip()

        # Final fallback: if chosen is still empty or not in sorted_ids,
        # attempt fuzzy resolution
        if chosen not in sorted_ids:
            chosen = _resolve_llm_choice(chosen, sorted_ids)
    except Exception as exc:
        logger.warning("LLM gate intent step failed: %s", exc)
        chosen = sorted_ids[0] if sorted_ids else "kunskap"
        reasoning = f"LLM-anrop misslyckades: {exc}"

    return {
        "chosen": chosen,
        "reasoning": reasoning,
        "candidates_shown": len(items),
    }


async def llm_gate_select_agent(
    query: str,
    chosen_domain: str,
    candidates: list[dict[str, Any]],
    *,
    llm: Any = None,
) -> dict[str, Any]:
    """Select agent using a structured LLM call.

    ``candidates`` should be dicts with at least ``name`` and ``description``.
    Returns ``{"chosen": agent_name, "reasoning": str, "candidates_shown": int}``.
    """
    sorted_ids: list[str] = []
    items: list[tuple[str, str]] = []
    for c in candidates:
        name = str(c.get("name") or c.get("agent_id") or "").strip()
        desc = str(c.get("description") or c.get("label") or "").strip()
        if name:
            sorted_ids.append(name)
            items.append((name, desc))
    sorted_ids.sort()

    system_prompt = (
        "Du är en agent-router. Givet användarens fråga och den valda domänen, "
        "välj EXAKT EN agent från listan som bäst kan hantera frågan.\n\n"
        "Resonera semantiskt — förstå vad användaren faktiskt menar, "
        "inte bara vilka ord som förekommer i frågan.\n\n"
        "Tänk ALLTID på svenska i din interna resonering.\n"
        "I din motivering: beskriv VARFÖR agenten passar, "
        "men nämn ALDRIG 'agentlistan', 'domänlistan', 'nyckelord' "
        "eller andra interna systembegrepp.\n\n"
        f"Vald domän: {chosen_domain}\n\n"
        "Agenter:\n" + _format_candidate_list(items) + "\n\n"
        "VIKTIGT: Svara med det exakta agent-ID:t (t.ex. 'väder'), "
        "INTE ett nummer."
    )
    user_prompt = f"Fråga: {query}"

    chosen = ""
    reasoning = ""
    try:
        if llm is not None:
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 500}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    LlmGateAgentResult, "llm_gate_agent_result"
                )
            message = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
                **_invoke_kwargs,
            )
            _raw = str(getattr(message, "content", "") or "")
            try:
                _structured = LlmGateAgentResult.model_validate_json(_raw)
                chosen = _structured.chosen
                reasoning = _structured.reasoning
            except Exception:
                m = re.search(r"\{[\s\S]*\}", _raw)
                if m:
                    try:
                        parsed = json.loads(m.group())
                        chosen = str(parsed.get("chosen") or "").strip()
                        reasoning = str(parsed.get("reasoning") or "").strip()
                    except json.JSONDecodeError:
                        # Truncated JSON — extract fields via regex
                        chosen = _extract_field_from_partial_json(_raw, "chosen")
                        reasoning = _extract_field_from_partial_json(_raw, "reasoning")
                if not chosen:
                    for line in _raw.strip().splitlines():
                        ls = line.strip()
                        if ls.upper().startswith("AGENT:"):
                            chosen = ls.split(":", 1)[1].strip()
                        elif ls.upper().startswith("MOTIVERING:"):
                            reasoning = ls.split(":", 1)[1].strip()
        else:
            from app.nexus.llm import nexus_llm_call

            prompt = system_prompt + "\n\n" + user_prompt + (
                "\n\nSvara EXAKT i detta format (inget annat):\n"
                "MOTIVERING: <en mening som förklarar varför just denna agent passar bäst>\n"
                "AGENT: <agent_id>\n"
            )
            response = await nexus_llm_call(prompt)
            for line in response.strip().splitlines():
                ls = line.strip()
                if ls.upper().startswith("AGENT:"):
                    chosen = ls.split(":", 1)[1].strip()
                elif ls.upper().startswith("MOTIVERING:"):
                    reasoning = ls.split(":", 1)[1].strip()

        chosen = _resolve_llm_choice(chosen, sorted_ids)
    except Exception as exc:
        logger.warning("LLM gate agent step failed: %s", exc)
        chosen = sorted_ids[0] if sorted_ids else ""
        reasoning = f"LLM-anrop misslyckades: {exc}"

    return {
        "chosen": chosen,
        "reasoning": reasoning,
        "candidates_shown": len(items),
    }


async def llm_gate_select_tools(
    query: str,
    chosen_agent: str,
    candidates: list[dict[str, Any]],
    *,
    llm: Any = None,
) -> dict[str, Any]:
    """Select tool(s) using a structured LLM call.

    ``candidates`` should be dicts with at least ``tool_id`` and ``description``.
    The LLM may select 1-3 tools when multiple are needed to answer the query.
    Returns ``{"chosen": [tool_id, ...], "reasoning": str, "candidates_shown": int}``.
    """
    sorted_ids: list[str] = []
    items: list[tuple[str, str]] = []
    for c in candidates:
        tid = str(c.get("tool_id") or "").strip()
        desc = str(c.get("description") or "").strip()
        if tid:
            sorted_ids.append(tid)
            items.append((tid, desc))
    sorted_ids.sort()

    if not items:
        return {"chosen": [], "reasoning": "Inga verktyg hittades.", "candidates_shown": 0}

    system_prompt = (
        "Du är en verktygsväljare. Givet användarens fråga och den valda agenten, "
        "välj de verktyg (1-3 st) från listan som behövs för att besvara frågan.\n\n"
        "Resonera semantiskt — förstå vad användaren faktiskt menar, "
        "inte bara vilka ord som förekommer i frågan.\n\n"
        "Tänk ALLTID på svenska i din interna resonering.\n"
        "I din motivering: beskriv VARFÖR verktygen behövs, "
        "men nämn ALDRIG interna systembegrepp.\n\n"
        f"Vald agent: {chosen_agent}\n\n"
        "Verktyg:\n" + _format_candidate_list(items) + "\n\n"
        "VIKTIGT: Svara med de exakta verktygs-ID:na. "
        "Välj bara de verktyg som faktiskt behövs — ofta räcker 1, "
        "men välj 2-3 om frågan kräver data från flera verktyg."
    )
    user_prompt = f"Fråga: {query}"

    chosen_list: list[str] = []
    reasoning = ""
    try:
        if llm is not None:
            _invoke_kwargs: dict[str, Any] = {"max_tokens": 400}
            if structured_output_enabled():
                _invoke_kwargs["response_format"] = pydantic_to_response_format(
                    LlmGateToolResult, "llm_gate_tool_result"
                )
            message = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
                **_invoke_kwargs,
            )
            _raw = str(getattr(message, "content", "") or "")
            try:
                _structured = LlmGateToolResult.model_validate_json(_raw)
                chosen_list = list(_structured.chosen)
                reasoning = _structured.reasoning
            except Exception:
                m = re.search(r"\{[\s\S]*\}", _raw)
                if m:
                    try:
                        parsed = json.loads(m.group())
                        raw_chosen = parsed.get("chosen") or []
                        if isinstance(raw_chosen, list):
                            chosen_list = [str(t).strip() for t in raw_chosen if str(t).strip()]
                        elif isinstance(raw_chosen, str) and raw_chosen.strip():
                            chosen_list = [raw_chosen.strip()]
                        reasoning = str(parsed.get("reasoning") or "").strip()
                    except json.JSONDecodeError:
                        # Truncated JSON — extract list via regex
                        chosen_list = _extract_chosen_list_from_partial_json(_raw)
                        reasoning = _extract_field_from_partial_json(_raw, "reasoning")
                if not chosen_list:
                    for line in _raw.strip().splitlines():
                        ls = line.strip()
                        if ls.upper().startswith("VERKTYG:"):
                            chosen_list.append(ls.split(":", 1)[1].strip())
                        elif ls.upper().startswith("MOTIVERING:"):
                            reasoning = ls.split(":", 1)[1].strip()
        else:
            from app.nexus.llm import nexus_llm_call

            prompt = system_prompt + "\n\n" + user_prompt + (
                "\n\nSvara EXAKT i detta format (inget annat):\n"
                "MOTIVERING: <en mening som förklarar varför dessa verktyg behövs>\n"
                "VERKTYG: <tool_id_1>\n"
                "VERKTYG: <tool_id_2>  (om fler behövs)\n"
            )
            response = await nexus_llm_call(prompt)
            for line in response.strip().splitlines():
                ls = line.strip()
                if ls.upper().startswith("VERKTYG:"):
                    chosen_list.append(ls.split(":", 1)[1].strip())
                elif ls.upper().startswith("MOTIVERING:"):
                    reasoning = ls.split(":", 1)[1].strip()

        # Resolve each chosen tool against the candidate list
        resolved_list: list[str] = []
        for raw_tool in chosen_list[:3]:
            resolved = _resolve_llm_choice(raw_tool, sorted_ids)
            if resolved and resolved not in resolved_list:
                resolved_list.append(resolved)
        chosen_list = resolved_list
    except Exception as exc:
        logger.warning("LLM gate tool step failed: %s", exc)
        chosen_list = [sorted_ids[0]] if sorted_ids else []
        reasoning = f"LLM-anrop misslyckades: {exc}"

    return {
        "chosen": chosen_list,
        "reasoning": reasoning,
        "candidates_shown": len(items),
    }
