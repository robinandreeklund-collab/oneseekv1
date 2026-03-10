from __future__ import annotations

import weakref
from typing import Any

_CACHE_DISABLED = False

# Registry of TTLCache instances from services.
# We keep weak references so GC'd service instances don't linger.
_SERVICE_CACHES: list[weakref.ref[Any]] = []


def is_cache_disabled() -> bool:
    return _CACHE_DISABLED


def set_cache_disabled(value: bool) -> None:
    global _CACHE_DISABLED
    _CACHE_DISABLED = bool(value)


def register_service_cache(cache: Any) -> None:
    """Register a TTLCache (or any object with .clear()) for centralized flushing."""
    _SERVICE_CACHES.append(weakref.ref(cache))


def clear_all_service_caches() -> int:
    """Clear all registered service TTL caches. Returns number of caches flushed."""
    flushed = 0
    alive: list[weakref.ref[Any]] = []
    for ref in _SERVICE_CACHES:
        obj = ref()
        if obj is not None:
            try:
                obj.clear()
                flushed += 1
            except Exception:
                pass
            alive.append(ref)
    _SERVICE_CACHES[:] = alive
    return flushed
