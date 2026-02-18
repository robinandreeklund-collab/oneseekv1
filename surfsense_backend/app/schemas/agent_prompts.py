from pydantic import BaseModel, Field


class AgentPromptItem(BaseModel):
    key: str = Field(..., description="Prompt key identifier")
    label: str = Field(..., description="Human-readable label")
    description: str = Field(..., description="Description of where the prompt is used")
    node_group: str = Field(..., description="LangGraph node group (router/supervisor/subagent/compare/system/other)")
    node_group_label: str = Field(..., description="Display label for node_group")
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


class AgentPromptHistoryItem(BaseModel):
    key: str
    previous_prompt: str | None = None
    new_prompt: str | None = None
    updated_at: str
    updated_by_id: str | None = None


class AgentPromptHistoryResponse(BaseModel):
    items: list[AgentPromptHistoryItem]
