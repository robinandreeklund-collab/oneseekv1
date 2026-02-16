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


class ToolLatestEvaluationSummary(BaseModel):
    run_at: str
    eval_name: str | None = None
    total_tests: int
    passed_tests: int
    success_rate: float


class ToolSettingsResponse(BaseModel):
    categories: list[ToolCategoryResponse]
    retrieval_tuning: ToolRetrievalTuning
    latest_evaluation: ToolLatestEvaluationSummary | None = None
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
    agent: str | None = None
    acceptable_agents: list[str] = Field(default_factory=list)
    acceptable_tools: list[str] = Field(default_factory=list)
    intent: str | None = None
    route: str | None = None
    sub_route: str | None = None
    graph_complexity: str | None = None
    execution_strategy: str | None = None
    plan_requirements: list[str] = Field(default_factory=list)


class ToolApiInputEvaluationExpected(BaseModel):
    category: str | None = None
    tool: str | None = None
    agent: str | None = None
    acceptable_agents: list[str] = Field(default_factory=list)
    acceptable_tools: list[str] = Field(default_factory=list)
    intent: str | None = None
    route: str | None = None
    sub_route: str | None = None
    graph_complexity: str | None = None
    execution_strategy: str | None = None
    plan_requirements: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    field_values: dict[str, Any] = Field(default_factory=dict)
    allow_clarification: bool | None = None


class ToolEvaluationTestCase(BaseModel):
    id: str
    question: str
    difficulty: str | None = None
    expected: ToolEvaluationExpected | None = None
    allowed_tools: list[str] = Field(default_factory=list)


class ToolApiInputEvaluationTestCase(BaseModel):
    id: str
    question: str
    difficulty: str | None = None
    expected: ToolApiInputEvaluationExpected | None = None
    allowed_tools: list[str] = Field(default_factory=list)


class ToolEvaluationRequest(BaseModel):
    eval_name: str | None = None
    target_success_rate: float | None = None
    search_space_id: int | None = None
    retrieval_limit: int = 5
    use_llm_supervisor_review: bool = True
    tests: list[ToolEvaluationTestCase]
    metadata_patch: list[ToolMetadataUpdateItem] = Field(default_factory=list)
    retrieval_tuning_override: ToolRetrievalTuning | None = None


class ToolApiInputEvaluationRequest(BaseModel):
    eval_name: str | None = None
    target_success_rate: float | None = None
    search_space_id: int | None = None
    retrieval_limit: int = 5
    use_llm_supervisor_review: bool = True
    tests: list[ToolApiInputEvaluationTestCase]
    holdout_tests: list[ToolApiInputEvaluationTestCase] = Field(default_factory=list)
    metadata_patch: list[ToolMetadataUpdateItem] = Field(default_factory=list)
    retrieval_tuning_override: ToolRetrievalTuning | None = None


class ToolDifficultyBreakdownItem(BaseModel):
    difficulty: str
    total_tests: int
    passed_tests: int
    success_rate: float
    gated_success_rate: float | None = None


class ToolEvaluationMetrics(BaseModel):
    total_tests: int
    passed_tests: int
    success_rate: float
    gated_success_rate: float | None = None
    intent_accuracy: float | None = None
    route_accuracy: float | None = None
    sub_route_accuracy: float | None = None
    graph_complexity_accuracy: float | None = None
    execution_strategy_accuracy: float | None = None
    agent_accuracy: float | None = None
    plan_accuracy: float | None = None
    supervisor_review_score: float | None = None
    supervisor_review_pass_rate: float | None = None
    category_accuracy: float | None = None
    tool_accuracy: float | None = None
    retrieval_recall_at_k: float | None = None
    difficulty_breakdown: list[ToolDifficultyBreakdownItem] = Field(default_factory=list)


class ToolSupervisorReviewRubricItem(BaseModel):
    key: str
    label: str
    passed: bool
    weight: float = 1.0
    evidence: str | None = None


class ToolEvaluationCaseResult(BaseModel):
    test_id: str
    question: str
    difficulty: str | None = None
    expected_intent: str | None = None
    expected_route: str | None = None
    expected_sub_route: str | None = None
    expected_graph_complexity: str | None = None
    expected_execution_strategy: str | None = None
    expected_agent: str | None = None
    expected_acceptable_agents: list[str] = Field(default_factory=list)
    expected_category: str | None = None
    expected_tool: str | None = None
    expected_acceptable_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    selected_route: str | None = None
    selected_sub_route: str | None = None
    selected_intent: str | None = None
    selected_graph_complexity: str | None = None
    selected_execution_strategy: str | None = None
    selected_agent: str | None = None
    agent_selection_analysis: str = ""
    selected_category: str | None = None
    selected_tool: str | None = None
    planning_analysis: str = ""
    planning_steps: list[str] = Field(default_factory=list)
    supervisor_trace: dict[str, Any] = Field(default_factory=dict)
    supervisor_review_score: float | None = None
    supervisor_review_passed: bool | None = None
    supervisor_review_rationale: str | None = None
    supervisor_review_issues: list[str] = Field(default_factory=list)
    supervisor_review_rubric: list[ToolSupervisorReviewRubricItem] = Field(
        default_factory=list
    )
    plan_requirement_checks: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_top_tools: list[str] = Field(default_factory=list)
    retrieval_top_categories: list[str] = Field(default_factory=list)
    retrieval_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_hit_expected_tool: bool | None = None
    consistency_warnings: list[str] = Field(default_factory=list)
    expected_normalized: bool = False
    passed_route: bool | None = None
    passed_sub_route: bool | None = None
    passed_graph_complexity: bool | None = None
    passed_execution_strategy: bool | None = None
    passed_intent: bool | None = None
    passed_agent: bool | None = None
    passed_plan: bool | None = None
    passed_category: bool | None = None
    passed_tool: bool | None = None
    passed_with_agent_gate: bool | None = None
    agent_gate_score: float | None = None
    passed: bool


class ToolApiInputFieldCheck(BaseModel):
    field: str
    expected: Any | None = None
    actual: Any | None = None
    passed: bool


class ToolApiInputEvaluationCaseResult(BaseModel):
    test_id: str
    question: str
    difficulty: str | None = None
    expected_intent: str | None = None
    expected_route: str | None = None
    expected_sub_route: str | None = None
    expected_graph_complexity: str | None = None
    expected_execution_strategy: str | None = None
    expected_agent: str | None = None
    expected_acceptable_agents: list[str] = Field(default_factory=list)
    expected_category: str | None = None
    expected_tool: str | None = None
    expected_acceptable_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    selected_route: str | None = None
    selected_sub_route: str | None = None
    selected_intent: str | None = None
    selected_graph_complexity: str | None = None
    selected_execution_strategy: str | None = None
    selected_agent: str | None = None
    agent_selection_analysis: str = ""
    selected_category: str | None = None
    selected_tool: str | None = None
    planning_analysis: str = ""
    planning_steps: list[str] = Field(default_factory=list)
    supervisor_trace: dict[str, Any] = Field(default_factory=dict)
    supervisor_review_score: float | None = None
    supervisor_review_passed: bool | None = None
    supervisor_review_rationale: str | None = None
    supervisor_review_issues: list[str] = Field(default_factory=list)
    supervisor_review_rubric: list[ToolSupervisorReviewRubricItem] = Field(
        default_factory=list
    )
    plan_requirement_checks: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_top_tools: list[str] = Field(default_factory=list)
    retrieval_top_categories: list[str] = Field(default_factory=list)
    retrieval_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    consistency_warnings: list[str] = Field(default_factory=list)
    expected_normalized: bool = False
    proposed_arguments: dict[str, Any] = Field(default_factory=dict)
    target_tool_for_validation: str | None = None
    schema_required_fields: list[str] = Field(default_factory=list)
    expected_required_fields: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    unexpected_fields: list[str] = Field(default_factory=list)
    field_checks: list[ToolApiInputFieldCheck] = Field(default_factory=list)
    schema_valid: bool | None = None
    schema_errors: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    passed_route: bool | None = None
    passed_sub_route: bool | None = None
    passed_graph_complexity: bool | None = None
    passed_execution_strategy: bool | None = None
    passed_intent: bool | None = None
    passed_agent: bool | None = None
    passed_plan: bool | None = None
    passed_category: bool | None = None
    passed_tool: bool | None = None
    passed_api_input: bool | None = None
    passed_with_agent_gate: bool | None = None
    agent_gate_score: float | None = None
    passed: bool


class ToolApiInputEvaluationMetrics(BaseModel):
    total_tests: int
    passed_tests: int
    success_rate: float
    gated_success_rate: float | None = None
    intent_accuracy: float | None = None
    route_accuracy: float | None = None
    sub_route_accuracy: float | None = None
    graph_complexity_accuracy: float | None = None
    execution_strategy_accuracy: float | None = None
    agent_accuracy: float | None = None
    plan_accuracy: float | None = None
    supervisor_review_score: float | None = None
    supervisor_review_pass_rate: float | None = None
    category_accuracy: float | None = None
    tool_accuracy: float | None = None
    schema_validity_rate: float | None = None
    required_field_recall: float | None = None
    field_value_accuracy: float | None = None
    clarification_accuracy: float | None = None
    difficulty_breakdown: list[ToolDifficultyBreakdownItem] = Field(default_factory=list)


class ToolMetadataSuggestion(BaseModel):
    tool_id: str
    failed_test_ids: list[str] = Field(default_factory=list)
    rationale: str
    current_metadata: ToolMetadataUpdateItem
    proposed_metadata: ToolMetadataUpdateItem


class ToolPromptSuggestion(BaseModel):
    prompt_key: str
    failed_test_ids: list[str] = Field(default_factory=list)
    related_tools: list[str] = Field(default_factory=list)
    rationale: str
    current_prompt: str
    proposed_prompt: str


class ToolIntentDefinitionSuggestion(BaseModel):
    intent_id: str
    failed_test_ids: list[str] = Field(default_factory=list)
    rationale: str
    current_definition: dict[str, Any] = Field(default_factory=dict)
    proposed_definition: dict[str, Any] = Field(default_factory=dict)
    prompt_key: str | None = None
    current_prompt: str | None = None
    proposed_prompt: str | None = None


class ToolEvaluationMetricDeltaItem(BaseModel):
    metric: str
    previous: float | None = None
    current: float | None = None
    delta: float | None = None


class ToolEvaluationRunComparison(BaseModel):
    stage: str
    stage_metric_name: str | None = None
    trend: str
    previous_run_at: str | None = None
    previous_eval_name: str | None = None
    previous_success_rate: float | None = None
    current_success_rate: float
    success_rate_delta: float | None = None
    previous_stage_metric: float | None = None
    current_stage_metric: float | None = None
    stage_metric_delta: float | None = None
    previous_gated_success_rate: float | None = None
    current_gated_success_rate: float | None = None
    gated_success_rate_delta: float | None = None
    metric_deltas: list[ToolEvaluationMetricDeltaItem] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)


class ToolEvaluationResponse(BaseModel):
    eval_name: str | None = None
    target_success_rate: float | None = None
    metrics: ToolEvaluationMetrics
    results: list[ToolEvaluationCaseResult]
    suggestions: list[ToolMetadataSuggestion]
    prompt_suggestions: list[ToolPromptSuggestion] = Field(default_factory=list)
    intent_suggestions: list[ToolIntentDefinitionSuggestion] = Field(default_factory=list)
    retrieval_tuning: ToolRetrievalTuning
    retrieval_tuning_suggestion: ToolRetrievalTuningSuggestion | None = None
    consistency_summary: dict[str, int] = Field(default_factory=dict)
    comparison: ToolEvaluationRunComparison | None = None
    metadata_version_hash: str
    search_space_id: int


class ToolApiInputEvaluationResponse(BaseModel):
    eval_name: str | None = None
    target_success_rate: float | None = None
    metrics: ToolApiInputEvaluationMetrics
    results: list[ToolApiInputEvaluationCaseResult]
    holdout_metrics: ToolApiInputEvaluationMetrics | None = None
    holdout_results: list[ToolApiInputEvaluationCaseResult] = Field(default_factory=list)
    prompt_suggestions: list[ToolPromptSuggestion] = Field(default_factory=list)
    intent_suggestions: list[ToolIntentDefinitionSuggestion] = Field(default_factory=list)
    retrieval_tuning: ToolRetrievalTuning
    consistency_summary: dict[str, int] = Field(default_factory=dict)
    comparison: ToolEvaluationRunComparison | None = None
    metadata_version_hash: str
    search_space_id: int


class ToolEvaluationStartResponse(BaseModel):
    job_id: str
    status: str
    total_tests: int


class ToolEvaluationCaseStatus(BaseModel):
    test_id: str
    question: str
    status: str
    selected_route: str | None = None
    selected_sub_route: str | None = None
    selected_agent: str | None = None
    selected_tool: str | None = None
    selected_category: str | None = None
    consistency_warnings: list[str] = Field(default_factory=list)
    expected_normalized: bool | None = None
    passed: bool | None = None
    error: str | None = None


class ToolEvaluationJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_tests: int
    completed_tests: int
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str
    case_statuses: list[ToolEvaluationCaseStatus] = Field(default_factory=list)
    result: ToolEvaluationResponse | None = None
    error: str | None = None


class ToolApiInputEvaluationStartResponse(BaseModel):
    job_id: str
    status: str
    total_tests: int


class ToolApiInputEvaluationJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_tests: int
    completed_tests: int
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str
    case_statuses: list[ToolEvaluationCaseStatus] = Field(default_factory=list)
    result: ToolApiInputEvaluationResponse | None = None
    error: str | None = None


class ToolAutoLoopGenerationConfig(BaseModel):
    eval_type: str = "tool_selection"
    mode: str = "category"
    provider_key: str | None = None
    category_id: str | None = None
    weather_suite_mode: str = "mixed"
    question_count: int = 12
    difficulty_profile: str = "mixed"
    eval_name: str | None = None
    include_allowed_tools: bool = True


class ToolAutoLoopRequest(BaseModel):
    search_space_id: int | None = None
    generation: ToolAutoLoopGenerationConfig
    use_holdout_suite: bool = False
    holdout_question_count: int = 8
    holdout_difficulty_profile: str | None = None
    target_success_rate: float = 0.85
    max_iterations: int = 6
    patience: int = 2
    min_improvement_delta: float = 0.005
    retrieval_limit: int = 5
    use_llm_supervisor_review: bool = True
    include_metadata_suggestions: bool = True
    include_prompt_suggestions: bool = True
    include_retrieval_tuning_suggestions: bool = True


class ToolAutoLoopDraftPromptItem(BaseModel):
    prompt_key: str
    proposed_prompt: str
    rationale: str | None = None
    related_tools: list[str] = Field(default_factory=list)


class ToolAutoLoopDraftBundle(BaseModel):
    metadata_patch: list[ToolMetadataUpdateItem] = Field(default_factory=list)
    prompt_patch: list[ToolAutoLoopDraftPromptItem] = Field(default_factory=list)
    retrieval_tuning_override: ToolRetrievalTuning | None = None


class ToolAutoLoopIterationSummary(BaseModel):
    iteration: int
    success_rate: float
    gated_success_rate: float | None = None
    passed_tests: int
    total_tests: int
    success_delta_vs_previous: float | None = None
    holdout_success_rate: float | None = None
    holdout_passed_tests: int | None = None
    holdout_total_tests: int | None = None
    holdout_delta_vs_previous: float | None = None
    combined_score: float | None = None
    combined_delta_vs_previous: float | None = None
    metadata_changes_applied: int = 0
    prompt_changes_applied: int = 0
    retrieval_tuning_changed: bool = False
    note: str | None = None


class ToolAutoLoopResult(BaseModel):
    status: str
    stop_reason: str
    target_success_rate: float
    best_success_rate: float
    best_iteration: int
    no_improvement_runs: int
    generated_suite: dict[str, Any]
    generated_holdout_suite: dict[str, Any] | None = None
    iterations: list[ToolAutoLoopIterationSummary] = Field(default_factory=list)
    final_evaluation: ToolEvaluationResponse
    final_holdout_evaluation: ToolEvaluationResponse | None = None
    draft_changes: ToolAutoLoopDraftBundle


class ToolAutoLoopStartResponse(BaseModel):
    job_id: str
    status: str
    total_iterations: int
    target_success_rate: float


class ToolAutoLoopJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_iterations: int
    completed_iterations: int
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str
    current_iteration: int = 0
    best_success_rate: float | None = None
    no_improvement_runs: int = 0
    message: str | None = None
    iterations: list[ToolAutoLoopIterationSummary] = Field(default_factory=list)
    result: ToolAutoLoopResult | None = None
    error: str | None = None


class ToolApiInputApplyPromptSuggestionItem(BaseModel):
    prompt_key: str
    proposed_prompt: str


class ToolApiInputApplyPromptSuggestionsRequest(BaseModel):
    suggestions: list[ToolApiInputApplyPromptSuggestionItem]


class ToolApiInputApplyPromptSuggestionsResponse(BaseModel):
    applied_prompt_keys: list[str]


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


class ToolApiCategoryItem(BaseModel):
    tool_id: str
    tool_name: str
    category_id: str
    category_name: str
    level: str
    description: str
    base_path: str | None = None


class ToolApiCategoryProvider(BaseModel):
    provider_key: str
    provider_name: str
    categories: list[ToolApiCategoryItem] = Field(default_factory=list)


class ToolApiCategoriesResponse(BaseModel):
    providers: list[ToolApiCategoryProvider] = Field(default_factory=list)


class ToolEvalLibraryGenerateRequest(BaseModel):
    search_space_id: int | None = None
    eval_type: str = "tool_selection"
    mode: str = "category"
    provider_key: str | None = None
    category_id: str | None = None
    weather_suite_mode: str = "mixed"
    question_count: int = 12
    difficulty_profile: str = "mixed"
    eval_name: str | None = None
    target_success_rate: float | None = None
    include_allowed_tools: bool = True


class ToolEvalLibraryFileItem(BaseModel):
    relative_path: str
    file_name: str
    provider_key: str | None = None
    category_id: str | None = None
    created_at: str
    size_bytes: int
    test_count: int | None = None


class ToolEvalLibraryListResponse(BaseModel):
    items: list[ToolEvalLibraryFileItem] = Field(default_factory=list)


class ToolEvalLibraryFileResponse(BaseModel):
    relative_path: str
    content: str
    payload: dict[str, Any]


class ToolEvalLibraryGenerateResponse(BaseModel):
    relative_path: str
    file_name: str
    version: int
    created_at: str
    payload: dict[str, Any]


class ToolEvaluationStageHistoryCategoryItem(BaseModel):
    category_id: str
    total_tests: int
    passed_tests: int
    success_rate: float


class ToolEvaluationStageHistoryItem(BaseModel):
    run_at: str
    stage: str
    eval_name: str | None = None
    total_tests: int
    passed_tests: int
    success_rate: float
    stage_metric_name: str | None = None
    stage_metric_value: float | None = None
    category_breakdown: list[ToolEvaluationStageHistoryCategoryItem] = Field(
        default_factory=list
    )


class ToolEvaluationStageCategorySeriesPoint(BaseModel):
    run_at: str
    eval_name: str | None = None
    total_tests: int
    passed_tests: int
    success_rate: float
    stage_metric_value: float | None = None


class ToolEvaluationStageCategorySeries(BaseModel):
    category_id: str
    points: list[ToolEvaluationStageCategorySeriesPoint] = Field(default_factory=list)


class ToolEvaluationStageHistoryResponse(BaseModel):
    stage: str
    items: list[ToolEvaluationStageHistoryItem] = Field(default_factory=list)
    category_series: list[ToolEvaluationStageCategorySeries] = Field(default_factory=list)
