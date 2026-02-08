from pydantic import BaseModel, Field


class AgentPromptItem(BaseModel):
    key: str = Field(..., description="Prompt key identifier")
    label: str = Field(..., description="Human-readable label")
    description: str = Field(..., description="Description of where the prompt is used")
    default_prompt: str = Field(..., description="Default prompt text")
    override_prompt: str | None = Field(
        None, description="Override prompt text if configured"
    )


class AgentPromptsResponse(BaseModel):
    items: list[AgentPromptItem]


class AgentPromptUpdateItem(BaseModel):
    key: str
    override_prompt: str | None = None


class AgentPromptsUpdateRequest(BaseModel):
    items: list[AgentPromptUpdateItem]
