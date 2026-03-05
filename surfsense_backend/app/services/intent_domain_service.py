"""CRUD service for intent domains (``intent_domains`` table).

Provides functions to read, create, update and delete domain definitions
that form the top level of the intent → agent → tool hierarchy.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import IntentDomain, IntentDomainHistory
from app.seeds.intent_domains import get_default_intent_domains

# ── Normalization helpers ─────────────────────────────────────────────


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def _normalize_text_list(values: Any) -> list[str]:
    return _normalize_keywords(values)


# ── Payload normalization ─────────────────────────────────────────────


def normalize_domain_payload(
    payload: Mapping[str, Any],
    *,
    domain_id: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize an intent domain payload."""
    resolved_id = _normalize_text(domain_id or payload.get("domain_id")).lower()
    if not resolved_id:
        resolved_id = "custom"
    return {
        "domain_id": resolved_id,
        "label": _normalize_text(payload.get("label"))
        or resolved_id.replace("-", " ").title(),
        "description": _normalize_text(payload.get("description")),
        "keywords": _normalize_keywords(payload.get("keywords")),
        "priority": _normalize_int(payload.get("priority"), default=500),
        "enabled": bool(payload.get("enabled", True)),
        "fallback_route": _normalize_text(payload.get("fallback_route")) or "kunskap",
        "citations_enabled": bool(payload.get("citations_enabled", True)),
        "main_identifier": _normalize_text(payload.get("main_identifier")),
        "core_activity": _normalize_text(payload.get("core_activity")),
        "unique_scope": _normalize_text(payload.get("unique_scope")),
        "geographic_scope": _normalize_text(payload.get("geographic_scope")),
        "excludes": _normalize_text_list(payload.get("excludes")),
        "complexity_override": _normalize_text(payload.get("complexity_override"))
        or None,
        "execution_strategy_hint": _normalize_text(
            payload.get("execution_strategy_hint")
        )
        or None,
    }


# ── Read operations ───────────────────────────────────────────────────


async def get_all_intent_domains(session: AsyncSession) -> list[dict[str, Any]]:
    """Return all intent domains from DB."""
    result = await session.execute(
        select(IntentDomain).order_by(IntentDomain.sort_order)
    )
    domains: list[dict[str, Any]] = []
    for row in result.scalars().all():
        payload = (
            row.definition_payload if isinstance(row.definition_payload, dict) else {}
        )
        normalized = normalize_domain_payload(payload, domain_id=row.domain_id)
        domains.append(normalized)
    return domains


async def get_intent_domain(
    session: AsyncSession, domain_id: str
) -> dict[str, Any] | None:
    """Return a single intent domain by ID."""
    result = await session.execute(
        select(IntentDomain).filter(IntentDomain.domain_id == domain_id)
    )
    row = result.scalars().first()
    if not row:
        return None
    payload = row.definition_payload if isinstance(row.definition_payload, dict) else {}
    return normalize_domain_payload(payload, domain_id=row.domain_id)


async def get_effective_intent_domains(session: AsyncSession) -> list[dict[str, Any]]:
    """Return merged default + DB domains, sorted by priority."""
    defaults = get_default_intent_domains()
    db_domains = await get_all_intent_domains(session)
    merged = {**defaults}
    for domain in db_domains:
        domain_id = domain.get("domain_id", "")
        if domain_id:
            merged[domain_id] = domain
    ordered = sorted(
        [d for d in merged.values() if d.get("enabled", True)],
        key=lambda item: (
            int(item.get("priority", 500)),
            str(item.get("domain_id", "")),
        ),
    )
    return ordered


# ── Write operations ──────────────────────────────────────────────────


async def upsert_intent_domain(
    session: AsyncSession,
    domain_id: str,
    payload: dict[str, Any],
    updated_by_id: Any = None,
) -> dict[str, Any]:
    """Create or update an intent domain. Returns the normalized payload."""
    normalized_id = _normalize_text(domain_id).lower()
    if not normalized_id:
        normalized_id = "custom"
    normalized = normalize_domain_payload(payload, domain_id=normalized_id)

    result = await session.execute(
        select(IntentDomain).filter(IntentDomain.domain_id == normalized_id)
    )
    existing = result.scalars().first()
    previous_payload = (
        normalize_domain_payload(existing.definition_payload, domain_id=normalized_id)
        if existing and isinstance(existing.definition_payload, dict)
        else None
    )

    if existing:
        existing.definition_payload = normalized
        existing.sort_order = normalized.get("priority", 500)
        if updated_by_id is not None:
            existing.updated_by_id = updated_by_id
    else:
        session.add(
            IntentDomain(
                domain_id=normalized_id,
                definition_payload=normalized,
                sort_order=normalized.get("priority", 500),
                updated_by_id=updated_by_id,
            )
        )

    if previous_payload != normalized:
        session.add(
            IntentDomainHistory(
                domain_id=normalized_id,
                previous_payload=previous_payload,
                new_payload=normalized,
                updated_by_id=updated_by_id,
            )
        )

    return normalized


async def delete_intent_domain(
    session: AsyncSession,
    domain_id: str,
    updated_by_id: Any = None,
) -> bool:
    """Delete an intent domain. Returns True if deleted."""
    result = await session.execute(
        select(IntentDomain).filter(IntentDomain.domain_id == domain_id)
    )
    existing = result.scalars().first()
    if not existing:
        return False

    previous_payload = (
        normalize_domain_payload(existing.definition_payload, domain_id=domain_id)
        if isinstance(existing.definition_payload, dict)
        else None
    )
    session.add(
        IntentDomainHistory(
            domain_id=domain_id,
            previous_payload=previous_payload,
            new_payload=None,
            updated_by_id=updated_by_id,
        )
    )
    await session.delete(existing)
    return True
