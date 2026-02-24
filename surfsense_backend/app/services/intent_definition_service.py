from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.agents.new_chat.routing import Route
from app.db import GlobalIntentDefinition, GlobalIntentDefinitionHistory


_ROUTE_VALUES = {route.value for route in Route}

# ── Backward-compat: accept old route values during normalization ─────
_COMPAT_ROUTE_MAP: dict[str, str] = {
    "knowledge": Route.KUNSKAP.value,
    "action": Route.SKAPANDE.value,
    "smalltalk": Route.KONVERSATION.value,
    "compare": Route.JAMFORELSE.value,
    "statistics": Route.KUNSKAP.value,  # merged into kunskap
}

_DEFAULT_INTENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "kunskap": {
        "intent_id": "kunskap",
        "route": Route.KUNSKAP.value,
        "label": "Kunskap",
        "description": (
            "Användaren vill ha information eller kunskap om något – "
            "oavsett källa (interna dokument, väder, trafik, statistik, "
            "bolagsinfo, marknadsplatser, riksdagen, webb)."
        ),
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
            "väder",
            "vädret",
            "vader",
            "vadret",
            "smhi",
            "temperatur",
            "regn",
            "prognos",
            "trafik",
            "trafiken",
            "trafikverket",
            "statistik",
            "scb",
            "befolkning",
            "kolada",
            "bolag",
            "bolagsverket",
            "riksdagen",
            "proposition",
            "blocket",
            "tradera",
            "marknadsplats",
            "annons",
            "begagnat",
            "webb",
            "länk",
            "nyheter",
            "kolla",
            "vad är",
            "hur mycket",
            "hur många",
        ],
        "priority": 200,
        "enabled": True,
    },
    "skapande": {
        "intent_id": "skapande",
        "route": Route.SKAPANDE.value,
        "label": "Skapande",
        "description": (
            "Användaren vill att systemet skapar eller genererar något – "
            "podcast, kartbilder, kod, filer."
        ),
        "keywords": [
            "skapa",
            "generera",
            "gör",
            "rita",
            "podcast",
            "bild",
            "karta",
            "kartbild",
            "kod",
            "script",
            "python",
            "sandbox",
            "fil",
            "skriv",
        ],
        "priority": 300,
        "enabled": True,
    },
    "jämförelse": {
        "intent_id": "jämförelse",
        "route": Route.JAMFORELSE.value,
        "label": "Jämförelse",
        "description": "Jämförelse-läge när användaren explicit efterfrågar compare.",
        "keywords": ["/compare", "compare", "jämför", "jamfor", "jämförelse"],
        "priority": 50,
        "enabled": True,
    },
    "konversation": {
        "intent_id": "konversation",
        "route": Route.KONVERSATION.value,
        "label": "Konversation",
        "description": "Hälsningar och enkel konversation utan verktyg.",
        "keywords": ["hej", "tjena", "hallå", "hur mår du", "konversation", "smalltalk"],
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


def _normalize_identity_field(value: Any, max_chars: int) -> str:
    text = _normalize_text(value)
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_dot = cut.rfind(".")
    if last_dot > max_chars * 0.6:
        return cut[: last_dot + 1]
    return cut.rstrip()


def _normalize_excludes(values: Any, max_items: int = 15) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(e).strip() for e in values if str(e).strip()][:max_items]


def normalize_intent_definition_payload(
    payload: Mapping[str, Any],
    *,
    intent_id: str | None = None,
) -> dict[str, Any]:
    resolved_intent_id = _normalize_text(intent_id or payload.get("intent_id")).lower()
    if not resolved_intent_id:
        resolved_intent_id = "custom"
    route_value = _normalize_text(payload.get("route")).lower()
    # Accept old English route names transparently
    route_value = _COMPAT_ROUTE_MAP.get(route_value, route_value)
    if route_value not in _ROUTE_VALUES:
        route_value = Route.KUNSKAP.value
    label = _normalize_optional_text(payload.get("label")) or resolved_intent_id.replace(
        "_", " "
    ).title()
    description = _normalize_optional_text(payload.get("description")) or ""
    keywords = _normalize_keywords(payload.get("keywords"))
    priority = _normalize_int(payload.get("priority"), default=500)
    enabled = bool(payload.get("enabled", True))
    main_identifier = _normalize_identity_field(payload.get("main_identifier", ""), 80)
    core_activity = _normalize_identity_field(payload.get("core_activity", ""), 120)
    unique_scope = _normalize_identity_field(payload.get("unique_scope", ""), 120)
    geographic_scope = _normalize_identity_field(payload.get("geographic_scope", ""), 80)
    excludes = _normalize_excludes(payload.get("excludes", []))
    return {
        "intent_id": resolved_intent_id,
        "route": route_value,
        "label": label,
        "description": description,
        "keywords": keywords,
        "priority": priority,
        "enabled": enabled,
        "main_identifier": main_identifier,
        "core_activity": core_activity,
        "unique_scope": unique_scope,
        "geographic_scope": geographic_scope,
        "excludes": excludes,
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
