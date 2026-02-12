from pydantic import BaseModel


class ToolMetadataItem(BaseModel):
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str
    base_path: str | None = None


class ToolCategoryResponse(BaseModel):
    category_id: str
    category_name: str
    tools: list[ToolMetadataItem]


class ToolSettingsResponse(BaseModel):
    categories: list[ToolCategoryResponse]
