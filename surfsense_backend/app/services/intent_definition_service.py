from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.agents.new_chat.routing import Route
from app.db import GlobalIntentDefinition, GlobalIntentDefinitionHistory


_ROUTE_VALUES = {route.value for route in Route}
_DEFAULT_INTENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "knowledge": {
        "intent_id": "knowledge",
        "route": Route.KNOWLEDGE.value,
        "label": "Kunskap",
        "description": "Frågor som kräver sökning i kunskapskällor, dokument eller minne.",
        "keywords": [
            "dokument",
            "docs",
            "kunskap",
            "sök",
            "search",
            "notion",
            "slack",
            "github",
            "sammanfatta",
        ],
        "priority": 200,
        "enabled": True,
    },
    "action": {
        "intent_id": "action",
        "route": Route.ACTION.value,
        "label": "Action",
        "description": (
            "Realtidsuppgifter och verktygskörningar som väder, trafik, media, "
            "webb och marknadsplatser (Blocket/Tradera)."
        ),
        "keywords": [
            "väder",
            "smhi",
            "trafik",
            "resa",
            "rutt",
            "webb",
            "länk",
            "podcast",
            "bild",
            "verktyg",
            "blocket",
            "tradera",
            "marknadsplats",
            "annons",
            "begagnat",
            "auktion",
            "motorcykel",
            "mc",
            "bilar",
            "båtar",
            "prisjämförelse",
        ],
        "priority": 300,
        "enabled": True,
    },
    "statistics": {
        "intent_id": "statistics",
        "route": Route.STATISTICS.value,
        "label": "Statistik",
        "description": "SCB och officiell svensk statistik.",
        "keywords": [
            "statistik",
            "scb",
            "befolkning",
            "inflation",
            "arbetslöshet",
            "kpi",
            "kommun",
            "län",
        ],
        "priority": 100,
        "enabled": True,
    },
    "compare": {
        "intent_id": "compare",
        "route": Route.COMPARE.value,
        "label": "Compare",
        "description": "Jämförelse-läge när användaren explicit efterfrågar compare.",
        "keywords": ["/compare", "compare", "jämför", "jamfor"],
        "priority": 50,
        "enabled": True,
    },
    "smalltalk": {
        "intent_id": "smalltalk",
        "route": Route.SMALLTALK.value,
        "label": "Smalltalk",
        "description": "Hälsningar och enkel konversation utan verktyg.",
        "keywords": ["hej", "tjena", "hallå", "hur mår du", "smalltalk"],
        "priority": 400,
        "enabled": True,
    },
}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_optional_text(value: Any) -> str | None:
    text = _normalize_text(value)
    return text or None


def _normalize_int(value: Any, *, default: int = 500) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(10000, parsed))


def _normalize_keywords(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def normalize_intent_definition_payload(
    payload: Mapping[str, Any],
    *,
    intent_id: str | None = None,
) -> dict[str, Any]:
    resolved_intent_id = _normalize_text(intent_id or payload.get("intent_id")).lower()
    if not resolved_intent_id:
        resolved_intent_id = "custom"
    route_value = _normalize_text(payload.get("route")).lower()
    if route_value not in _ROUTE_VALUES:
        route_value = Route.KNOWLEDGE.value
    label = _normalize_optional_text(payload.get("label")) or resolved_intent_id.replace(
        "_", " "
    ).title()
    description = _normalize_optional_text(payload.get("description")) or ""
    keywords = _normalize_keywords(payload.get("keywords"))
    priority = _normalize_int(payload.get("priority"), default=500)
    enabled = bool(payload.get("enabled", True))
    return {
        "intent_id": resolved_intent_id,
        "route": route_value,
        "label": label,
        "description": description,
        "keywords": keywords,
        "priority": priority,
        "enabled": enabled,
    }


def get_default_intent_definitions() -> dict[str, dict[str, Any]]:
    return {
        intent_id: normalize_intent_definition_payload(payload, intent_id=intent_id)
        for intent_id, payload in _DEFAULT_INTENT_DEFINITIONS.items()
    }


async def get_global_intent_definition_overrides(
    session: AsyncSession,
) -> dict[str, dict[str, Any]]:
    result = await session.execute(select(GlobalIntentDefinition))
    overrides: dict[str, dict[str, Any]] = {}
    for row in result.scalars().all():
        payload = row.definition_payload if isinstance(row.definition_payload, dict) else {}
        normalized = normalize_intent_definition_payload(payload, intent_id=row.intent_id)
        overrides[row.intent_id] = normalized
    return overrides


async def get_effective_intent_definitions(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    defaults = get_default_intent_definitions()
    overrides = await get_global_intent_definition_overrides(session)
    merged = {**defaults}
    for intent_id, payload in overrides.items():
        merged[intent_id] = normalize_intent_definition_payload(payload, intent_id=intent_id)
    ordered = sorted(
        [payload for payload in merged.values() if payload.get("enabled", True)],
        key=lambda item: (int(item.get("priority") or 500), str(item.get("intent_id") or "")),
    )
    return ordered


async def upsert_global_intent_definition_overrides(
    session: AsyncSession,
    updates: Iterable[tuple[str, dict[str, Any] | None]],
    *,
    updated_by_id=None,
) -> None:
    for raw_intent_id, payload in updates:
        intent_id = _normalize_text(raw_intent_id).lower()
        if not intent_id:
            continue
        normalized_payload = (
            normalize_intent_definition_payload(payload, intent_id=intent_id)
            if payload is not None
            else None
        )
        result = await session.execute(
            select(GlobalIntentDefinition).filter(
                GlobalIntentDefinition.intent_id == intent_id,
            )
        )
        existing = result.scalars().first()
        previous_payload = (
            normalize_intent_definition_payload(
                existing.definition_payload,
                intent_id=intent_id,
            )
            if existing and isinstance(existing.definition_payload, dict)
            else None
        )
        if normalized_payload is None:
            if existing:
                await session.delete(existing)
        else:
            if existing:
                existing.definition_payload = normalized_payload
                if updated_by_id is not None:
                    existing.updated_by_id = updated_by_id
            else:
                session.add(
                    GlobalIntentDefinition(
                        intent_id=intent_id,
                        definition_payload=normalized_payload,
                        updated_by_id=updated_by_id,
                    )
                )
        if previous_payload != normalized_payload:
            session.add(
                GlobalIntentDefinitionHistory(
                    intent_id=intent_id,
                    previous_payload=previous_payload,
                    new_payload=normalized_payload,
                    updated_by_id=updated_by_id,
                )
            )
