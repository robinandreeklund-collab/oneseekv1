from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import GlobalToolMetadataOverride, GlobalToolMetadataOverrideHistory


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_optional_text(value: Any) -> str | None:
    text = _normalize_text(value)
    return text or None


def _normalize_text_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw)
        if not text:
            continue
        lowered = text.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(text)
    return deduped


def normalize_tool_metadata_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "name": _normalize_text(payload.get("name")),
        "description": _normalize_text(payload.get("description")),
        "keywords": _normalize_text_list(payload.get("keywords")),
        "example_queries": _normalize_text_list(payload.get("example_queries")),
        "category": _normalize_text(payload.get("category")),
        "base_path": _normalize_optional_text(payload.get("base_path")),
        "main_identifier": _normalize_text(payload.get("main_identifier")),
        "core_activity": _normalize_text(payload.get("core_activity")),
        "unique_scope": _normalize_text(payload.get("unique_scope")),
        "geographic_scope": _normalize_text(payload.get("geographic_scope")),
        "excludes": _normalize_text_list(payload.get("excludes")),
    }


def tool_metadata_payload_equal(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    return normalize_tool_metadata_payload(left) == normalize_tool_metadata_payload(right)


def merge_tool_metadata_overrides(
    base_overrides: Mapping[str, dict[str, Any]] | None,
    patch_overrides: Mapping[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    if base_overrides:
        merged.update({tool_id: dict(value) for tool_id, value in base_overrides.items()})
    if patch_overrides:
        for tool_id, payload in patch_overrides.items():
            merged[tool_id] = dict(payload)
    return merged


async def get_global_tool_metadata_overrides(
    session: AsyncSession,
) -> dict[str, dict[str, Any]]:
    result = await session.execute(select(GlobalToolMetadataOverride))
    overrides: dict[str, dict[str, Any]] = {}
    for row in result.scalars().all():
        payload = row.override_payload
        if isinstance(payload, dict):
            overrides[row.tool_id] = normalize_tool_metadata_payload(payload)
    return overrides


async def upsert_global_tool_metadata_overrides(
    session: AsyncSession,
    updates: Iterable[tuple[str, dict[str, Any] | None]],
    *,
    updated_by_id=None,
) -> None:
    for tool_id, payload in updates:
        normalized_tool_id = _normalize_text(tool_id)
        if not normalized_tool_id:
            continue
        normalized_payload = (
            normalize_tool_metadata_payload(payload) if payload is not None else None
        )
        result = await session.execute(
            select(GlobalToolMetadataOverride).filter(
                GlobalToolMetadataOverride.tool_id == normalized_tool_id,
            )
        )
        existing = result.scalars().first()
        previous_payload = (
            normalize_tool_metadata_payload(existing.override_payload)
            if existing and isinstance(existing.override_payload, dict)
            else None
        )

        if normalized_payload is None:
            if existing:
                await session.delete(existing)
        else:
            if existing:
                existing.override_payload = normalized_payload
                if updated_by_id is not None:
                    existing.updated_by_id = updated_by_id
            else:
                session.add(
                    GlobalToolMetadataOverride(
                        tool_id=normalized_tool_id,
                        override_payload=normalized_payload,
                        updated_by_id=updated_by_id,
                    )
                )

        if previous_payload != normalized_payload:
            session.add(
                GlobalToolMetadataOverrideHistory(
                    tool_id=normalized_tool_id,
                    previous_payload=previous_payload,
                    new_payload=normalized_payload,
                    updated_by_id=updated_by_id,
                )
            )
