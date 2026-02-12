from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CacheStateResponse(BaseModel):
    disabled: bool


class CacheToggleRequest(BaseModel):
    disabled: bool


class CacheClearResponse(BaseModel):
    cleared: dict[str, Any]
