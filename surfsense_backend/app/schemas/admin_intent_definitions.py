from typing import Any

from pydantic import BaseModel, Field


class IntentDefinitionItem(BaseModel):
    intent_id: str = Field(..., description="Stable intent identifier")
    route: str = Field(..., description="Top-level route selected for this intent")
    label: str = Field(..., description="Human-readable label")
    description: str = Field("", description="Intent description")
    keywords: list[str] = Field(default_factory=list, description="Routing keywords")
    priority: int = Field(500, description="Lower number means higher selection priority")
    enabled: bool = Field(True, description="Whether intent is active")
    has_override: bool = Field(False, description="True when DB override exists")


class IntentDefinitionsResponse(BaseModel):
    items: list[IntentDefinitionItem]


class IntentDefinitionUpdateItem(BaseModel):
    intent_id: str
    route: str | None = None
    label: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    priority: int | None = None
    enabled: bool | None = None
    clear_override: bool = False


class IntentDefinitionsUpdateRequest(BaseModel):
    items: list[IntentDefinitionUpdateItem]


class IntentDefinitionHistoryItem(BaseModel):
    intent_id: str
    previous_payload: dict[str, Any] | None = None
    new_payload: dict[str, Any] | None = None
    updated_at: str
    updated_by_id: str | None = None


class IntentDefinitionHistoryResponse(BaseModel):
    items: list[IntentDefinitionHistoryItem]
