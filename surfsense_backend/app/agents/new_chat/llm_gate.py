"""LLM Gate — pure LLM-based routing for intent / agent / tool selection.

When ``llm_gate_mode`` is enabled in the retrieval tuning configuration, these
helpers replace all embedding + reranker logic with direct LLM calls, mirroring
the approach used in the Nexus Pipeline Explorer.

Each function accepts a list of candidates (id + description) and a user query,
calls the global LLM via ``nexus_llm_call``, and returns the chosen id.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _format_candidate_list(items: list[tuple[str, str]]) -> str:
    """Format candidates as '- id — description' without numbering."""
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
) -> dict[str, Any]:
    """Select intent domain using a pure LLM call (no embeddings).

    Returns ``{"chosen": domain_id, "reasoning": str, "candidates_shown": int}``.
    """
    from app.nexus.llm import nexus_llm_call

    sorted_ids = sorted(
        str(c.get("intent_id") or c.get("domain_id") or "").strip()
        for c in candidates
        if str(c.get("intent_id") or c.get("domain_id") or "").strip()
    )
    items: list[tuple[str, str]] = []
    for c in candidates:
        cid = str(c.get("intent_id") or c.get("domain_id") or "").strip()
        desc = str(c.get("description") or "").strip()
        keywords = c.get("keywords") or []
        kw_str = ", ".join(str(k) for k in keywords[:6]) if keywords else ""
        label = f"{desc} (nyckelord: {kw_str})" if kw_str else desc
        if cid:
            items.append((cid, label))

    prompt = (
        "Du är en intent-router. Givet användarens fråga, välj EXAKT EN domän "
        "från listan som bäst matchar frågan.\n\n"
        f"Fråga: {query}\n\n"
        "Domäner:\n" + _format_candidate_list(items) + "\n\n"
        "VIKTIGT: Svara med det exakta domän-ID:t (t.ex. 'väder-och-klimat'), "
        "INTE ett nummer.\n\n"
        "Svara EXAKT i detta format (inget annat):\n"
        "MOTIVERING: <en mening som förklarar varför just denna domän matchar>\n"
        "DOMÄN: <domain_id>\n"
    )

    chosen = ""
    reasoning = ""
    try:
        response = await nexus_llm_call(prompt)
        for line in response.strip().splitlines():
            ls = line.strip()
            if ls.upper().startswith("DOMÄN:") or ls.upper().startswith("DOMAIN:"):
                chosen = ls.split(":", 1)[1].strip()
            elif ls.upper().startswith("MOTIVERING:"):
                reasoning = ls.split(":", 1)[1].strip()
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
) -> dict[str, Any]:
    """Select agent using a pure LLM call (no embeddings).

    ``candidates`` should be dicts with at least ``name`` and ``description``.
    Returns ``{"chosen": agent_name, "reasoning": str, "candidates_shown": int}``.
    """
    from app.nexus.llm import nexus_llm_call

    sorted_ids: list[str] = []
    items: list[tuple[str, str]] = []
    for c in candidates:
        name = str(c.get("name") or c.get("agent_id") or "").strip()
        desc = str(c.get("description") or c.get("label") or "").strip()
        keywords = c.get("keywords") or []
        kw_str = ", ".join(str(k) for k in keywords[:8]) if keywords else ""
        label = f"{desc} (nyckelord: {kw_str})" if kw_str else desc
        if name:
            sorted_ids.append(name)
            items.append((name, label))
    sorted_ids.sort()

    prompt = (
        "Du är en agent-router. Givet användarens fråga och den valda domänen, "
        "välj EXAKT EN agent från listan som bäst kan hantera frågan.\n\n"
        f"Fråga: {query}\n"
        f"Vald domän: {chosen_domain}\n\n"
        "Agenter:\n" + _format_candidate_list(items) + "\n\n"
        "VIKTIGT: Svara med det exakta agent-ID:t (t.ex. 'väder'), "
        "INTE ett nummer.\n\n"
        "Svara EXAKT i detta format (inget annat):\n"
        "MOTIVERING: <en mening som förklarar varför just denna agent passar bäst>\n"
        "AGENT: <agent_id>\n"
    )

    chosen = ""
    reasoning = ""
    try:
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
) -> dict[str, Any]:
    """Select tool(s) using a pure LLM call (no embeddings/reranker).

    ``candidates`` should be dicts with at least ``tool_id`` and ``description``.
    Returns ``{"chosen": [tool_id, ...], "reasoning": str, "candidates_shown": int}``.
    """
    from app.nexus.llm import nexus_llm_call

    sorted_ids: list[str] = []
    items: list[tuple[str, str]] = []
    for c in candidates:
        tid = str(c.get("tool_id") or "").strip()
        desc = str(c.get("description") or "").strip()
        keywords = c.get("keywords") or []
        kw_str = ", ".join(str(k) for k in keywords[:6]) if keywords else ""
        label = f"{desc} (nyckelord: {kw_str})" if kw_str else desc
        if tid:
            sorted_ids.append(tid)
            items.append((tid, label))
    sorted_ids.sort()

    if not items:
        return {"chosen": [], "reasoning": "Inga verktyg hittades.", "candidates_shown": 0}

    prompt = (
        "Du är en verktygsväljare. Givet användarens fråga och den valda agenten, "
        "välj EXAKT ETT verktyg från listan som bäst kan besvara frågan.\n\n"
        f"Fråga: {query}\n"
        f"Vald agent: {chosen_agent}\n\n"
        "Verktyg:\n" + _format_candidate_list(items) + "\n\n"
        "VIKTIGT: Svara med det exakta verktygs-ID:t (t.ex. 'smhi_temperatur'), "
        "INTE ett nummer.\n\n"
        "Svara EXAKT i detta format (inget annat):\n"
        "MOTIVERING: <en mening som förklarar varför just detta verktyg passar>\n"
        "VERKTYG: <tool_id>\n"
    )

    chosen = ""
    reasoning = ""
    try:
        response = await nexus_llm_call(prompt)
        for line in response.strip().splitlines():
            ls = line.strip()
            if ls.upper().startswith("VERKTYG:"):
                chosen = ls.split(":", 1)[1].strip()
            elif ls.upper().startswith("MOTIVERING:"):
                reasoning = ls.split(":", 1)[1].strip()
        if chosen:
            chosen = _resolve_llm_choice(chosen, sorted_ids)
    except Exception as exc:
        logger.warning("LLM gate tool step failed: %s", exc)
        chosen = sorted_ids[0] if sorted_ids else ""
        reasoning = f"LLM-anrop misslyckades: {exc}"

    return {
        "chosen": [chosen] if chosen else [],
        "reasoning": reasoning,
        "candidates_shown": len(items),
    }
