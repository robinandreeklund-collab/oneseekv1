from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_prompt_service import (
    get_global_prompt_overrides,
    upsert_global_prompt_overrides,
)

_AGENT_METADATA_OVERRIDE_PREFIX = "agent.metadata."

_DEFAULT_AGENT_METADATA: tuple[dict[str, Any], ...] = (
    {
        "agent_id": "åtgärd",
        "label": "Åtgärd",
        "description": "Realtime actions som vader, resor och verktygskorningar.",
        "keywords": [
            "vader",
            "vadret",
            "vader",
            "vadret",
            "smhi",
            "resa",
            "tag",
            "avgar",
            "tidtabell",
            "trafik",
            "rutt",
            "karta",
            "kartbild",
            "geoapify",
            "adress",
        ],
        "namespace": ["agents", "action"],
        "prompt_key": "action",
    },
    {
        "agent_id": "väder",
        "label": "Väder",
        "description": "SMHI-vaderprognoser och Trafikverkets vagvaderdata for svenska orter och vagar.",
        "keywords": [
            "smhi",
            "vader",
            "temperatur",
            "regn",
            "sno",
            "vind",
            "prognos",
            "halka",
            "isrisk",
            "vaglag",
        ],
        "namespace": ["agents", "weather"],
        "prompt_key": "action",
    },
    {
        "agent_id": "kartor",
        "label": "Kartor",
        "description": "Skapa statiska kartbilder och markorer.",
        "keywords": [
            "karta",
            "kartor",
            "kartbild",
            "map",
            "geoapify",
            "adress",
            "plats",
            "koordinat",
            "vagarbete",
            "vag",
            "rutt",
        ],
        "namespace": ["agents", "kartor"],
        "prompt_key": "kartor",
    },
    {
        "agent_id": "statistik",
        "label": "Statistik",
        "description": "SCB och officiell svensk statistik samt Kolada kommundata.",
        "keywords": [
            "statistik",
            "scb",
            "kolada",
            "skolverket statistik",
            "salsa",
            "nyckeltal",
            "kommun",
            "kommundata",
            "befolkning",
            "kpi",
            "aldreomsorg",
            "hemtjanst",
            "behorighet",
            "skattesats",
        ],
        "namespace": ["agents", "statistics"],
        "prompt_key": "statistics",
    },
    {
        "agent_id": "media",
        "label": "Media",
        "description": "Podcast, bild och media-generering.",
        "keywords": ["podcast", "podd", "media", "bild", "ljud"],
        "namespace": ["agents", "media"],
        "prompt_key": "media",
    },
    {
        "agent_id": "kunskap",
        "label": "Kunskap",
        "description": "SurfSense, Tavily och generell kunskap.",
        "keywords": [
            "kunskap",
            "surfsense",
            "tavily",
            "docs",
            "note",
            "skolverket",
            "laroplan",
            "kursplan",
            "amnesplan",
            "skolenhet",
            "komvux",
            "vuxenutbildning",
        ],
        "namespace": ["agents", "knowledge"],
        "prompt_key": "knowledge",
    },
    {
        "agent_id": "webb",
        "label": "Webb",
        "description": "Webbsokning och scraping.",
        "keywords": ["webb", "browser", "sok", "nyheter", "url"],
        "namespace": ["agents", "browser"],
        "prompt_key": "browser",
    },
    {
        "agent_id": "kod",
        "label": "Kod",
        "description": "Kalkyler och kodrelaterade uppgifter.",
        "keywords": [
            "kod",
            "berakna",
            "script",
            "python",
            "fil",
            "filer",
            "file",
            "filesystem",
            "filsystem",
            "skriv fil",
            "las fil",
            "create file",
            "read file",
            "write file",
            "sandbox",
            "docker",
            "bash",
            "terminal",
        ],
        "namespace": ["agents", "code"],
        "prompt_key": "code",
    },
    {
        "agent_id": "bolag",
        "label": "Bolag",
        "description": "Bolagsverket och foretagsdata (orgnr, agare, ekonomi).",
        "keywords": [
            "bolag",
            "bolagsverket",
            "foretag",
            "orgnr",
            "organisationsnummer",
            "styrelse",
            "firmatecknare",
            "arsredovisning",
            "f-skatt",
            "moms",
            "konkurs",
        ],
        "namespace": ["agents", "bolag"],
        "prompt_key": "bolag",
    },
    {
        "agent_id": "trafik",
        "label": "Trafik",
        "description": "Trafikverket realtidsdata (vag, tag, kameror).",
        "keywords": [
            "trafikverket",
            "trafik",
            "vag",
            "tag",
            "storning",
            "olycka",
            "ko",
            "kamera",
        ],
        "namespace": ["agents", "trafik"],
        "prompt_key": "trafik",
    },
    {
        "agent_id": "riksdagen",
        "label": "Riksdagen",
        "description": "Riksdagens oppna data: propositioner, motioner, voteringar, ledamoter.",
        "keywords": [
            "riksdag",
            "riksdagen",
            "proposition",
            "prop",
            "motion",
            "mot",
            "votering",
            "omrostning",
            "ledamot",
            "ledamoter",
            "betankande",
            "interpellation",
            "fraga",
            "anforande",
            "debatt",
            "kammare",
            "sou",
            "ds",
            "utskott",
            "parti",
        ],
        "namespace": ["agents", "riksdagen"],
        "prompt_key": "riksdagen",
    },
    {
        "agent_id": "marknad",
        "label": "Marknad",
        "description": "Sok och jamfor annonser pa Blocket och Tradera for begagnade varor.",
        "keywords": [
            "blocket",
            "tradera",
            "kop",
            "kopa",
            "salj",
            "salja",
            "begagnat",
            "annons",
            "annonser",
            "marknadsplats",
            "auktion",
            "bilar",
            "batar",
            "mc",
            "motorcykel",
            "pris",
            "prisjamforelse",
            "jamfor",
            "kategorier",
            "regioner",
            "sok",
            "hitta",
        ],
        "namespace": ["agents", "marketplace"],
        "prompt_key": "agent.marketplace.system",
    },
    {
        "agent_id": "syntes",
        "label": "Syntes",
        "description": "Syntes och jamforelser av flera kallor och modeller.",
        "keywords": ["synthesis", "syntes", "jamfor", "compare", "sammanfatta"],
        "namespace": ["agents", "synthesis"],
        "prompt_key": "synthesis",
    },
)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_optional_text(value: Any) -> str | None:
    text = _normalize_text(value)
    return text or None


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


def _normalize_namespace(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for raw in values:
        text = _normalize_text(raw)
        if text:
            normalized.append(text)
    return normalized


def normalize_agent_metadata_payload(
    payload: Mapping[str, Any],
    *,
    agent_id: str | None = None,
    default_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    default_payload = default_payload or {}
    resolved_agent_id = _normalize_text(agent_id or payload.get("agent_id")).lower()
    if not resolved_agent_id:
        resolved_agent_id = "custom"
    fallback_label = (
        _normalize_optional_text(default_payload.get("label"))
        or resolved_agent_id.replace("_", " ").title()
    )
    fallback_description = _normalize_optional_text(default_payload.get("description")) or ""
    fallback_keywords = _normalize_keywords(default_payload.get("keywords"))
    fallback_prompt_key = _normalize_optional_text(default_payload.get("prompt_key"))
    fallback_namespace = _normalize_namespace(default_payload.get("namespace"))
    label = _normalize_optional_text(payload.get("label")) or fallback_label
    description = _normalize_optional_text(payload.get("description")) or fallback_description
    keywords = _normalize_keywords(payload.get("keywords")) or fallback_keywords
    prompt_key = _normalize_optional_text(payload.get("prompt_key")) or fallback_prompt_key
    namespace = _normalize_namespace(payload.get("namespace")) or fallback_namespace
    return {
        "agent_id": resolved_agent_id,
        "label": label,
        "description": description,
        "keywords": keywords,
        "prompt_key": prompt_key,
        "namespace": namespace,
    }


def get_default_agent_metadata() -> dict[str, dict[str, Any]]:
    defaults: dict[str, dict[str, Any]] = {}
    for payload in _DEFAULT_AGENT_METADATA:
        normalized = normalize_agent_metadata_payload(
            payload,
            agent_id=payload.get("agent_id"),
            default_payload=payload,
        )
        defaults[normalized["agent_id"]] = normalized
    return defaults


def _serialize_override_payload(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)


def agent_metadata_payload_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_norm = normalize_agent_metadata_payload(left, agent_id=left.get("agent_id"))
    right_norm = normalize_agent_metadata_payload(right, agent_id=right.get("agent_id"))
    return left_norm == right_norm


async def get_global_agent_metadata_overrides(
    session: AsyncSession,
) -> dict[str, dict[str, Any]]:
    prompt_overrides = await get_global_prompt_overrides(session)
    overrides: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in prompt_overrides.items():
        key = str(raw_key or "").strip()
        if not key.startswith(_AGENT_METADATA_OVERRIDE_PREFIX):
            continue
        agent_id = (
            key[len(_AGENT_METADATA_OVERRIDE_PREFIX) :]
            .strip()
            .lower()
        )
        if not agent_id:
            continue
        payload: dict[str, Any] | None = None
        text_value = str(raw_value or "").strip()
        if text_value:
            try:
                parsed = json.loads(text_value)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {"agent_id": agent_id, "description": text_value}
        if payload is None:
            continue
        overrides[agent_id] = normalize_agent_metadata_payload(
            payload,
            agent_id=agent_id,
        )
    return overrides


async def get_effective_agent_metadata(session: AsyncSession) -> list[dict[str, Any]]:
    defaults = get_default_agent_metadata()
    overrides = await get_global_agent_metadata_overrides(session)
    merged: dict[str, dict[str, Any]] = {}
    for agent_id, default_payload in defaults.items():
        override_payload = overrides.get(agent_id)
        if override_payload is None:
            merged[agent_id] = default_payload
            continue
        merged[agent_id] = normalize_agent_metadata_payload(
            override_payload,
            agent_id=agent_id,
            default_payload=default_payload,
        )
    for agent_id, payload in overrides.items():
        if agent_id in merged:
            continue
        merged[agent_id] = normalize_agent_metadata_payload(
            payload,
            agent_id=agent_id,
        )
    ordered_ids = [
        payload["agent_id"]
        for payload in _DEFAULT_AGENT_METADATA
        if payload.get("agent_id")
    ]
    for agent_id in sorted(merged.keys()):
        if agent_id not in ordered_ids:
            ordered_ids.append(agent_id)
    return [merged[agent_id] for agent_id in ordered_ids if agent_id in merged]


async def upsert_global_agent_metadata_overrides(
    session: AsyncSession,
    updates: Iterable[tuple[str, Mapping[str, Any] | None]],
    *,
    updated_by_id=None,
) -> None:
    prompt_updates: list[tuple[str, str | None]] = []
    for raw_agent_id, payload in updates:
        agent_id = _normalize_text(raw_agent_id).lower()
        if not agent_id:
            continue
        key = f"{_AGENT_METADATA_OVERRIDE_PREFIX}{agent_id}"
        if payload is None:
            prompt_updates.append((key, None))
            continue
        normalized_payload = normalize_agent_metadata_payload(
            payload,
            agent_id=agent_id,
            default_payload=get_default_agent_metadata().get(agent_id),
        )
        prompt_updates.append((key, _serialize_override_payload(normalized_payload)))
    if not prompt_updates:
        return
    await upsert_global_prompt_overrides(
        session,
        prompt_updates,
        updated_by_id=updated_by_id,
    )
