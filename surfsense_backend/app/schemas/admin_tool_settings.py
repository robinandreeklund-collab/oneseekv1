from typing import Any

from pydantic import BaseModel, Field


class ToolMetadataItem(BaseModel):
    tool_id: str
    name: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    category: str
    base_path: str | None = None
    has_override: bool = False


class ToolMetadataUpdateItem(BaseModel):
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


class ToolRetrievalTuning(BaseModel):
    name_match_weight: float = 5.0
    keyword_weight: float = 3.0
    description_token_weight: float = 1.0
    example_query_weight: float = 2.0
    namespace_boost: float = 3.0
    embedding_weight: float = 4.0
    rerank_candidates: int = 24


class ToolSettingsResponse(BaseModel):
    categories: list[ToolCategoryResponse]
    retrieval_tuning: ToolRetrievalTuning
    metadata_version_hash: str
    search_space_id: int


class ToolSettingsUpdateRequest(BaseModel):
    tools: list[ToolMetadataUpdateItem]


class ToolRetrievalTuningResponse(BaseModel):
    tuning: ToolRetrievalTuning


class ToolRetrievalTuningSuggestion(BaseModel):
    current_tuning: ToolRetrievalTuning
    proposed_tuning: ToolRetrievalTuning
    rationale: str


class ToolEvaluationExpected(BaseModel):
    category: str | None = None
    tool: str | None = None


class ToolEvaluationTestCase(BaseModel):
    id: str
    question: str
    expected: ToolEvaluationExpected | None = None
    allowed_tools: list[str] = Field(default_factory=list)


class ToolEvaluationRequest(BaseModel):
    eval_name: str | None = None
    target_success_rate: float | None = None
    search_space_id: int | None = None
    retrieval_limit: int = 5
    tests: list[ToolEvaluationTestCase]
    metadata_patch: list[ToolMetadataUpdateItem] = Field(default_factory=list)
    retrieval_tuning_override: ToolRetrievalTuning | None = None


class ToolEvaluationMetrics(BaseModel):
    total_tests: int
    passed_tests: int
    success_rate: float
    category_accuracy: float | None = None
    tool_accuracy: float | None = None
    retrieval_recall_at_k: float | None = None


class ToolEvaluationCaseResult(BaseModel):
    test_id: str
    question: str
    expected_category: str | None = None
    expected_tool: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    selected_category: str | None = None
    selected_tool: str | None = None
    planning_analysis: str = ""
    planning_steps: list[str] = Field(default_factory=list)
    retrieval_top_tools: list[str] = Field(default_factory=list)
    retrieval_top_categories: list[str] = Field(default_factory=list)
    retrieval_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_hit_expected_tool: bool | None = None
    passed_category: bool | None = None
    passed_tool: bool | None = None
    passed: bool


class ToolMetadataSuggestion(BaseModel):
    tool_id: str
    failed_test_ids: list[str] = Field(default_factory=list)
    rationale: str
    current_metadata: ToolMetadataUpdateItem
    proposed_metadata: ToolMetadataUpdateItem


class ToolEvaluationResponse(BaseModel):
    eval_name: str | None = None
    target_success_rate: float | None = None
    metrics: ToolEvaluationMetrics
    results: list[ToolEvaluationCaseResult]
    suggestions: list[ToolMetadataSuggestion]
    retrieval_tuning: ToolRetrievalTuning
    retrieval_tuning_suggestion: ToolRetrievalTuningSuggestion | None = None
    metadata_version_hash: str
    search_space_id: int


class ToolSuggestionRequest(BaseModel):
    search_space_id: int | None = None
    metadata_patch: list[ToolMetadataUpdateItem] = Field(default_factory=list)
    failed_cases: list[ToolEvaluationCaseResult] = Field(default_factory=list)


class ToolSuggestionResponse(BaseModel):
    suggestions: list[ToolMetadataSuggestion]


class ToolApplySuggestionItem(BaseModel):
    tool_id: str
    proposed_metadata: ToolMetadataUpdateItem


class ToolApplySuggestionsRequest(BaseModel):
    suggestions: list[ToolApplySuggestionItem]


class ToolApplySuggestionsResponse(BaseModel):
    applied_tool_ids: list[str]
    settings: ToolSettingsResponse


class ToolMetadataHistoryItem(BaseModel):
    tool_id: str
    previous_payload: dict[str, Any] | None = None
    new_payload: dict[str, Any] | None = None
    updated_at: str
    updated_by_id: str | None = None


class ToolMetadataHistoryResponse(BaseModel):
    items: list[ToolMetadataHistoryItem]
