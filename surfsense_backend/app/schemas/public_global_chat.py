from typing import Literal

from pydantic import BaseModel, Field


class PublicGlobalChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class PublicGlobalChatRequest(BaseModel):
    user_query: str = Field(min_length=1, max_length=4000)
    messages: list[PublicGlobalChatMessage] | None = None
    llm_config_id: int | None = None
    citation_instructions: str | None = None
