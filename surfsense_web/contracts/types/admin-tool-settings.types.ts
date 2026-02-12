import { z } from "zod";

export const toolMetadataItem = z.object({
	tool_id: z.string(),
	name: z.string(),
	description: z.string(),
	keywords: z.array(z.string()),
	example_queries: z.array(z.string()),
	category: z.string(),
	base_path: z.string().nullable().optional(),
	has_override: z.boolean().optional().default(false),
});

export const toolMetadataUpdateItem = z.object({
	tool_id: z.string(),
	name: z.string(),
	description: z.string(),
	keywords: z.array(z.string()),
	example_queries: z.array(z.string()),
	category: z.string(),
	base_path: z.string().nullable().optional(),
});

export const toolCategoryResponse = z.object({
	category_id: z.string(),
	category_name: z.string(),
	tools: z.array(toolMetadataItem),
});

export const toolRetrievalTuning = z.object({
	name_match_weight: z.number(),
	keyword_weight: z.number(),
	description_token_weight: z.number(),
	example_query_weight: z.number(),
	namespace_boost: z.number(),
	embedding_weight: z.number(),
	rerank_candidates: z.number().int(),
});

export const toolRetrievalTuningResponse = z.object({
	tuning: toolRetrievalTuning,
});

export const toolRetrievalTuningSuggestion = z.object({
	current_tuning: toolRetrievalTuning,
	proposed_tuning: toolRetrievalTuning,
	rationale: z.string(),
});

export const toolLatestEvaluationSummary = z.object({
	run_at: z.string(),
	eval_name: z.string().nullable().optional(),
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
});

export const toolApiCategoryItem = z.object({
	tool_id: z.string(),
	tool_name: z.string(),
	category_id: z.string(),
	category_name: z.string(),
	level: z.string(),
	description: z.string(),
	base_path: z.string().nullable().optional(),
});

export const toolApiCategoryProvider = z.object({
	provider_key: z.string(),
	provider_name: z.string(),
	categories: z.array(toolApiCategoryItem).default([]),
});

export const toolApiCategoriesResponse = z.object({
	providers: z.array(toolApiCategoryProvider).default([]),
});

export const toolEvalLibraryGenerateRequest = z.object({
	search_space_id: z.number().nullable().optional(),
	eval_type: z.string().optional().default("tool_selection"),
	mode: z.string().optional().default("category"),
	provider_key: z.string().nullable().optional(),
	category_id: z.string().nullable().optional(),
	question_count: z.number().int().optional().default(12),
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	include_allowed_tools: z.boolean().optional().default(true),
});

export const toolEvalLibraryFileItem = z.object({
	relative_path: z.string(),
	file_name: z.string(),
	provider_key: z.string().nullable().optional(),
	category_id: z.string().nullable().optional(),
	created_at: z.string(),
	size_bytes: z.number(),
	test_count: z.number().nullable().optional(),
});

export const toolEvalLibraryListResponse = z.object({
	items: z.array(toolEvalLibraryFileItem).default([]),
});

export const toolEvalLibraryFileResponse = z.object({
	relative_path: z.string(),
	content: z.string(),
	payload: z.record(z.string(), z.unknown()),
});

export const toolEvalLibraryGenerateResponse = z.object({
	relative_path: z.string(),
	file_name: z.string(),
	version: z.number().int(),
	created_at: z.string(),
	payload: z.record(z.string(), z.unknown()),
});

export const toolSettingsResponse = z.object({
	categories: z.array(toolCategoryResponse),
	retrieval_tuning: toolRetrievalTuning,
	latest_evaluation: toolLatestEvaluationSummary.nullable().optional(),
	metadata_version_hash: z.string(),
	search_space_id: z.number(),
});

export const toolSettingsUpdateRequest = z.object({
	tools: z.array(toolMetadataUpdateItem),
});

export const toolEvaluationExpected = z.object({
	category: z.string().nullable().optional(),
	tool: z.string().nullable().optional(),
	agent: z.string().nullable().optional(),
	route: z.string().nullable().optional(),
	sub_route: z.string().nullable().optional(),
	plan_requirements: z.array(z.string()).optional().default([]),
});

export const toolApiInputEvaluationExpected = z.object({
	category: z.string().nullable().optional(),
	tool: z.string().nullable().optional(),
	agent: z.string().nullable().optional(),
	route: z.string().nullable().optional(),
	sub_route: z.string().nullable().optional(),
	plan_requirements: z.array(z.string()).optional().default([]),
	required_fields: z.array(z.string()).optional().default([]),
	field_values: z.record(z.string(), z.unknown()).optional().default({}),
	allow_clarification: z.boolean().nullable().optional(),
});

export const toolEvaluationTestCase = z.object({
	id: z.string(),
	question: z.string(),
	expected: toolEvaluationExpected.nullable().optional(),
	allowed_tools: z.array(z.string()).optional().default([]),
});

export const toolApiInputEvaluationTestCase = z.object({
	id: z.string(),
	question: z.string(),
	expected: toolApiInputEvaluationExpected.nullable().optional(),
	allowed_tools: z.array(z.string()).optional().default([]),
});

export const toolEvaluationRequest = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	search_space_id: z.number().nullable().optional(),
	retrieval_limit: z.number().int().optional().default(5),
	tests: z.array(toolEvaluationTestCase),
	metadata_patch: z.array(toolMetadataUpdateItem).optional().default([]),
	retrieval_tuning_override: toolRetrievalTuning.nullable().optional(),
});

export const toolApiInputEvaluationRequest = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	search_space_id: z.number().nullable().optional(),
	retrieval_limit: z.number().int().optional().default(5),
	tests: z.array(toolApiInputEvaluationTestCase),
	holdout_tests: z.array(toolApiInputEvaluationTestCase).optional().default([]),
	metadata_patch: z.array(toolMetadataUpdateItem).optional().default([]),
	retrieval_tuning_override: toolRetrievalTuning.nullable().optional(),
});

export const toolEvaluationMetrics = z.object({
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
	route_accuracy: z.number().nullable().optional(),
	sub_route_accuracy: z.number().nullable().optional(),
	agent_accuracy: z.number().nullable().optional(),
	plan_accuracy: z.number().nullable().optional(),
	category_accuracy: z.number().nullable().optional(),
	tool_accuracy: z.number().nullable().optional(),
	retrieval_recall_at_k: z.number().nullable().optional(),
});

export const toolPlanRequirementCheck = z.object({
	requirement: z.string(),
	passed: z.boolean(),
});

export const toolEvaluationCaseResult = z.object({
	test_id: z.string(),
	question: z.string(),
	expected_route: z.string().nullable().optional(),
	expected_sub_route: z.string().nullable().optional(),
	expected_agent: z.string().nullable().optional(),
	expected_category: z.string().nullable().optional(),
	expected_tool: z.string().nullable().optional(),
	allowed_tools: z.array(z.string()).default([]),
	selected_route: z.string().nullable().optional(),
	selected_sub_route: z.string().nullable().optional(),
	selected_agent: z.string().nullable().optional(),
	selected_category: z.string().nullable().optional(),
	selected_tool: z.string().nullable().optional(),
	planning_analysis: z.string().default(""),
	planning_steps: z.array(z.string()).default([]),
	plan_requirement_checks: z.array(toolPlanRequirementCheck).default([]),
	retrieval_top_tools: z.array(z.string()).default([]),
	retrieval_top_categories: z.array(z.string()).default([]),
	retrieval_breakdown: z.array(z.record(z.string(), z.unknown())).default([]),
	retrieval_hit_expected_tool: z.boolean().nullable().optional(),
	passed_route: z.boolean().nullable().optional(),
	passed_sub_route: z.boolean().nullable().optional(),
	passed_agent: z.boolean().nullable().optional(),
	passed_plan: z.boolean().nullable().optional(),
	passed_category: z.boolean().nullable().optional(),
	passed_tool: z.boolean().nullable().optional(),
	passed: z.boolean(),
});

export const toolApiInputFieldCheck = z.object({
	field: z.string(),
	expected: z.unknown().nullable().optional(),
	actual: z.unknown().nullable().optional(),
	passed: z.boolean(),
});

export const toolApiInputEvaluationCaseResult = z.object({
	test_id: z.string(),
	question: z.string(),
	expected_route: z.string().nullable().optional(),
	expected_sub_route: z.string().nullable().optional(),
	expected_agent: z.string().nullable().optional(),
	expected_category: z.string().nullable().optional(),
	expected_tool: z.string().nullable().optional(),
	allowed_tools: z.array(z.string()).default([]),
	selected_route: z.string().nullable().optional(),
	selected_sub_route: z.string().nullable().optional(),
	selected_agent: z.string().nullable().optional(),
	selected_category: z.string().nullable().optional(),
	selected_tool: z.string().nullable().optional(),
	planning_analysis: z.string().default(""),
	planning_steps: z.array(z.string()).default([]),
	plan_requirement_checks: z.array(toolPlanRequirementCheck).default([]),
	retrieval_top_tools: z.array(z.string()).default([]),
	retrieval_top_categories: z.array(z.string()).default([]),
	retrieval_breakdown: z.array(z.record(z.string(), z.unknown())).default([]),
	proposed_arguments: z.record(z.string(), z.unknown()).default({}),
	target_tool_for_validation: z.string().nullable().optional(),
	schema_required_fields: z.array(z.string()).default([]),
	expected_required_fields: z.array(z.string()).default([]),
	missing_required_fields: z.array(z.string()).default([]),
	unexpected_fields: z.array(z.string()).default([]),
	field_checks: z.array(toolApiInputFieldCheck).default([]),
	schema_valid: z.boolean().nullable().optional(),
	schema_errors: z.array(z.string()).default([]),
	needs_clarification: z.boolean().default(false),
	clarification_question: z.string().nullable().optional(),
	passed_route: z.boolean().nullable().optional(),
	passed_sub_route: z.boolean().nullable().optional(),
	passed_agent: z.boolean().nullable().optional(),
	passed_plan: z.boolean().nullable().optional(),
	passed_category: z.boolean().nullable().optional(),
	passed_tool: z.boolean().nullable().optional(),
	passed_api_input: z.boolean().nullable().optional(),
	passed: z.boolean(),
});

export const toolApiInputEvaluationMetrics = z.object({
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
	route_accuracy: z.number().nullable().optional(),
	sub_route_accuracy: z.number().nullable().optional(),
	agent_accuracy: z.number().nullable().optional(),
	plan_accuracy: z.number().nullable().optional(),
	category_accuracy: z.number().nullable().optional(),
	tool_accuracy: z.number().nullable().optional(),
	schema_validity_rate: z.number().nullable().optional(),
	required_field_recall: z.number().nullable().optional(),
	field_value_accuracy: z.number().nullable().optional(),
	clarification_accuracy: z.number().nullable().optional(),
});

export const toolMetadataSuggestion = z.object({
	tool_id: z.string(),
	failed_test_ids: z.array(z.string()).default([]),
	rationale: z.string(),
	current_metadata: toolMetadataUpdateItem,
	proposed_metadata: toolMetadataUpdateItem,
});

export const toolApiInputPromptSuggestion = z.object({
	prompt_key: z.string(),
	failed_test_ids: z.array(z.string()).default([]),
	related_tools: z.array(z.string()).default([]),
	rationale: z.string(),
	current_prompt: z.string(),
	proposed_prompt: z.string(),
});

export const toolEvaluationResponse = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	metrics: toolEvaluationMetrics,
	results: z.array(toolEvaluationCaseResult),
	suggestions: z.array(toolMetadataSuggestion),
	prompt_suggestions: z.array(toolApiInputPromptSuggestion).default([]),
	retrieval_tuning: toolRetrievalTuning,
	retrieval_tuning_suggestion: toolRetrievalTuningSuggestion.nullable().optional(),
	metadata_version_hash: z.string(),
	search_space_id: z.number(),
});

export const toolApiInputEvaluationResponse = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	metrics: toolApiInputEvaluationMetrics,
	results: z.array(toolApiInputEvaluationCaseResult),
	holdout_metrics: toolApiInputEvaluationMetrics.nullable().optional(),
	holdout_results: z.array(toolApiInputEvaluationCaseResult).default([]),
	prompt_suggestions: z.array(toolApiInputPromptSuggestion).default([]),
	retrieval_tuning: toolRetrievalTuning,
	metadata_version_hash: z.string(),
	search_space_id: z.number(),
});

export const toolEvaluationStartResponse = z.object({
	job_id: z.string(),
	status: z.string(),
	total_tests: z.number(),
});

export const toolEvaluationCaseStatus = z.object({
	test_id: z.string(),
	question: z.string(),
	status: z.string(),
	selected_route: z.string().nullable().optional(),
	selected_sub_route: z.string().nullable().optional(),
	selected_agent: z.string().nullable().optional(),
	selected_tool: z.string().nullable().optional(),
	selected_category: z.string().nullable().optional(),
	passed: z.boolean().nullable().optional(),
	error: z.string().nullable().optional(),
});

export const toolEvaluationJobStatusResponse = z.object({
	job_id: z.string(),
	status: z.string(),
	total_tests: z.number(),
	completed_tests: z.number(),
	started_at: z.string().nullable().optional(),
	completed_at: z.string().nullable().optional(),
	updated_at: z.string(),
	case_statuses: z.array(toolEvaluationCaseStatus).default([]),
	result: toolEvaluationResponse.nullable().optional(),
	error: z.string().nullable().optional(),
});

export const toolApiInputEvaluationStartResponse = z.object({
	job_id: z.string(),
	status: z.string(),
	total_tests: z.number(),
});

export const toolApiInputEvaluationJobStatusResponse = z.object({
	job_id: z.string(),
	status: z.string(),
	total_tests: z.number(),
	completed_tests: z.number(),
	started_at: z.string().nullable().optional(),
	completed_at: z.string().nullable().optional(),
	updated_at: z.string(),
	case_statuses: z.array(toolEvaluationCaseStatus).default([]),
	result: toolApiInputEvaluationResponse.nullable().optional(),
	error: z.string().nullable().optional(),
});

export const toolApiInputApplyPromptSuggestionItem = z.object({
	prompt_key: z.string(),
	proposed_prompt: z.string(),
});

export const toolApiInputApplyPromptSuggestionsRequest = z.object({
	suggestions: z.array(toolApiInputApplyPromptSuggestionItem),
});

export const toolApiInputApplyPromptSuggestionsResponse = z.object({
	applied_prompt_keys: z.array(z.string()),
});

export const toolSuggestionRequest = z.object({
	search_space_id: z.number().nullable().optional(),
	metadata_patch: z.array(toolMetadataUpdateItem).optional().default([]),
	failed_cases: z.array(toolEvaluationCaseResult),
});

export const toolSuggestionResponse = z.object({
	suggestions: z.array(toolMetadataSuggestion),
});

export const toolApplySuggestionItem = z.object({
	tool_id: z.string(),
	proposed_metadata: toolMetadataUpdateItem,
});

export const toolApplySuggestionsRequest = z.object({
	suggestions: z.array(toolApplySuggestionItem),
});

export const toolApplySuggestionsResponse = z.object({
	applied_tool_ids: z.array(z.string()),
	settings: toolSettingsResponse,
});

export type ToolMetadataItem = z.infer<typeof toolMetadataItem>;
export type ToolMetadataUpdateItem = z.infer<typeof toolMetadataUpdateItem>;
export type ToolCategoryResponse = z.infer<typeof toolCategoryResponse>;
export type ToolRetrievalTuning = z.infer<typeof toolRetrievalTuning>;
export type ToolRetrievalTuningResponse = z.infer<typeof toolRetrievalTuningResponse>;
export type ToolRetrievalTuningSuggestion = z.infer<typeof toolRetrievalTuningSuggestion>;
export type ToolLatestEvaluationSummary = z.infer<typeof toolLatestEvaluationSummary>;
export type ToolApiCategoryItem = z.infer<typeof toolApiCategoryItem>;
export type ToolApiCategoryProvider = z.infer<typeof toolApiCategoryProvider>;
export type ToolApiCategoriesResponse = z.infer<typeof toolApiCategoriesResponse>;
export type ToolEvalLibraryGenerateRequest = z.infer<
	typeof toolEvalLibraryGenerateRequest
>;
export type ToolEvalLibraryFileItem = z.infer<typeof toolEvalLibraryFileItem>;
export type ToolEvalLibraryListResponse = z.infer<typeof toolEvalLibraryListResponse>;
export type ToolEvalLibraryFileResponse = z.infer<typeof toolEvalLibraryFileResponse>;
export type ToolEvalLibraryGenerateResponse = z.infer<
	typeof toolEvalLibraryGenerateResponse
>;
export type ToolSettingsResponse = z.infer<typeof toolSettingsResponse>;
export type ToolSettingsUpdateRequest = z.infer<typeof toolSettingsUpdateRequest>;
export type ToolEvaluationExpected = z.infer<typeof toolEvaluationExpected>;
export type ToolApiInputEvaluationExpected = z.infer<
	typeof toolApiInputEvaluationExpected
>;
export type ToolEvaluationTestCase = z.infer<typeof toolEvaluationTestCase>;
export type ToolApiInputEvaluationTestCase = z.infer<
	typeof toolApiInputEvaluationTestCase
>;
export type ToolEvaluationRequest = z.infer<typeof toolEvaluationRequest>;
export type ToolApiInputEvaluationRequest = z.infer<
	typeof toolApiInputEvaluationRequest
>;
export type ToolEvaluationMetrics = z.infer<typeof toolEvaluationMetrics>;
export type ToolPlanRequirementCheck = z.infer<typeof toolPlanRequirementCheck>;
export type ToolEvaluationCaseResult = z.infer<typeof toolEvaluationCaseResult>;
export type ToolApiInputFieldCheck = z.infer<typeof toolApiInputFieldCheck>;
export type ToolApiInputEvaluationCaseResult = z.infer<
	typeof toolApiInputEvaluationCaseResult
>;
export type ToolApiInputEvaluationMetrics = z.infer<
	typeof toolApiInputEvaluationMetrics
>;
export type ToolMetadataSuggestion = z.infer<typeof toolMetadataSuggestion>;
export type ToolEvaluationResponse = z.infer<typeof toolEvaluationResponse>;
export type ToolApiInputPromptSuggestion = z.infer<typeof toolApiInputPromptSuggestion>;
export type ToolApiInputEvaluationResponse = z.infer<
	typeof toolApiInputEvaluationResponse
>;
export type ToolEvaluationStartResponse = z.infer<typeof toolEvaluationStartResponse>;
export type ToolEvaluationCaseStatus = z.infer<typeof toolEvaluationCaseStatus>;
export type ToolEvaluationJobStatusResponse = z.infer<
	typeof toolEvaluationJobStatusResponse
>;
export type ToolApiInputEvaluationStartResponse = z.infer<
	typeof toolApiInputEvaluationStartResponse
>;
export type ToolApiInputEvaluationJobStatusResponse = z.infer<
	typeof toolApiInputEvaluationJobStatusResponse
>;
export type ToolApiInputApplyPromptSuggestionItem = z.infer<
	typeof toolApiInputApplyPromptSuggestionItem
>;
export type ToolApiInputApplyPromptSuggestionsRequest = z.infer<
	typeof toolApiInputApplyPromptSuggestionsRequest
>;
export type ToolApiInputApplyPromptSuggestionsResponse = z.infer<
	typeof toolApiInputApplyPromptSuggestionsResponse
>;
export type ToolSuggestionRequest = z.infer<typeof toolSuggestionRequest>;
export type ToolSuggestionResponse = z.infer<typeof toolSuggestionResponse>;
export type ToolApplySuggestionItem = z.infer<typeof toolApplySuggestionItem>;
export type ToolApplySuggestionsRequest = z.infer<typeof toolApplySuggestionsRequest>;
export type ToolApplySuggestionsResponse = z.infer<typeof toolApplySuggestionsResponse>;
