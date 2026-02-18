from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import threading
from typing import Any


def _safe_scope_component(value: Any) -> str:
    return str(value or "").strip() or "anonymous"


def _normalize_task_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def _build_entry_key(tool_id: str, query: str) -> str:
    normalized_tool = str(tool_id or "").strip().lower()
    normalized_query = _normalize_task_query(query)
    material = f"{normalized_tool}|{normalized_query}".encode("utf-8")
    return f"{normalized_tool}:{hashlib.sha256(material).hexdigest()}"


def infer_ttl_seconds(*, tool_id: str, agent_name: str | None = None) -> int:
    normalized_tool = str(tool_id or "").strip().lower()
    normalized_agent = str(agent_name or "").strip().lower()
    token = f"{normalized_tool} {normalized_agent}"

    if any(marker in token for marker in ("smhi", "weather", "vader", "väder")):
        return 5 * 60
    if any(marker in token for marker in ("trafik", "route", "departure", "avgang", "avgång")):
        return 2 * 60
    if any(marker in token for marker in ("scb", "kolada", "statistics", "statistik")):
        return 24 * 60 * 60
    if any(marker in token for marker in ("bolag", "bolagsverket", "orgnr")):
        return 7 * 24 * 60 * 60
    if any(marker in token for marker in ("riksdag", "riksdagen", "politik")):
        return 60 * 60
    return 15 * 60


@dataclass
class EpisodicFact:
    value: dict[str, Any]
    expires_at: datetime
    created_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at


class EpisodicMemoryStore:
    def __init__(self, *, max_entries: int = 500):
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[str, EpisodicFact] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, *, tool_id: str, query: str) -> dict[str, Any] | None:
        key = _build_entry_key(tool_id, query)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.is_expired:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return dict(entry.value)

    def put(
        self,
        *,
        tool_id: str,
        query: str,
        value: dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        safe_ttl = max(1, int(ttl_seconds))
        now = datetime.now(UTC)
        key = _build_entry_key(tool_id, query)
        fact = EpisodicFact(
            value=dict(value or {}),
            created_at=now,
            expires_at=now + timedelta(seconds=safe_ttl),
        )
        with self._lock:
            self._entries[key] = fact
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate(self, *, tool_id: str | None = None) -> None:
        with self._lock:
            if not tool_id:
                self._entries.clear()
                return
            normalized = str(tool_id or "").strip().lower()
            if not normalized:
                self._entries.clear()
                return
            prefix = f"{normalized}:"
            keys_to_drop = [key for key in self._entries.keys() if key.startswith(prefix)]
            for key in keys_to_drop:
                self._entries.pop(key, None)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


_MAX_STORES = 100
_registry_lock = threading.RLock()
_store_registry: OrderedDict[str, EpisodicMemoryStore] = OrderedDict()


def _scope_key(*, search_space_id: Any, user_id: Any) -> str:
    return f"{_safe_scope_component(search_space_id)}::{_safe_scope_component(user_id)}"


def get_or_create_episodic_store(
    *,
    search_space_id: Any,
    user_id: Any,
    max_entries: int = 500,
) -> EpisodicMemoryStore:
    key = _scope_key(search_space_id=search_space_id, user_id=user_id)
    with _registry_lock:
        existing = _store_registry.get(key)
        if existing is not None:
            _store_registry.move_to_end(key)
            return existing
        store = EpisodicMemoryStore(max_entries=max_entries)
        _store_registry[key] = store
        _store_registry.move_to_end(key)
        while len(_store_registry) > _MAX_STORES:
            _store_registry.popitem(last=False)
        return store
