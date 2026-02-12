from __future__ import annotations


_CACHE_DISABLED = False


def is_cache_disabled() -> bool:
    return _CACHE_DISABLED


def set_cache_disabled(value: bool) -> None:
    global _CACHE_DISABLED
    _CACHE_DISABLED = bool(value)
