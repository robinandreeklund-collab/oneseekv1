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

export const toolSettingsResponse = z.object({
	categories: z.array(toolCategoryResponse),
	metadata_version_hash: z.string(),
	search_space_id: z.number(),
});

export const toolSettingsUpdateRequest = z.object({
	tools: z.array(toolMetadataUpdateItem),
});

export const toolEvaluationExpected = z.object({
	category: z.string().nullable().optional(),
	tool: z.string().nullable().optional(),
});

export const toolEvaluationTestCase = z.object({
	id: z.string(),
	question: z.string(),
	expected: toolEvaluationExpected.nullable().optional(),
	allowed_tools: z.array(z.string()).optional().default([]),
});

export const toolEvaluationRequest = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	search_space_id: z.number().nullable().optional(),
	retrieval_limit: z.number().int().optional().default(5),
	tests: z.array(toolEvaluationTestCase),
	metadata_patch: z.array(toolMetadataUpdateItem).optional().default([]),
});

export const toolEvaluationMetrics = z.object({
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
	category_accuracy: z.number().nullable().optional(),
	tool_accuracy: z.number().nullable().optional(),
	retrieval_recall_at_k: z.number().nullable().optional(),
});

export const toolEvaluationCaseResult = z.object({
	test_id: z.string(),
	question: z.string(),
	expected_category: z.string().nullable().optional(),
	expected_tool: z.string().nullable().optional(),
	allowed_tools: z.array(z.string()).default([]),
	selected_category: z.string().nullable().optional(),
	selected_tool: z.string().nullable().optional(),
	planning_analysis: z.string().default(""),
	planning_steps: z.array(z.string()).default([]),
	retrieval_top_tools: z.array(z.string()).default([]),
	retrieval_top_categories: z.array(z.string()).default([]),
	retrieval_hit_expected_tool: z.boolean().nullable().optional(),
	passed_category: z.boolean().nullable().optional(),
	passed_tool: z.boolean().nullable().optional(),
	passed: z.boolean(),
});

export const toolMetadataSuggestion = z.object({
	tool_id: z.string(),
	failed_test_ids: z.array(z.string()).default([]),
	rationale: z.string(),
	current_metadata: toolMetadataUpdateItem,
	proposed_metadata: toolMetadataUpdateItem,
});

export const toolEvaluationResponse = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	metrics: toolEvaluationMetrics,
	results: z.array(toolEvaluationCaseResult),
	suggestions: z.array(toolMetadataSuggestion),
	metadata_version_hash: z.string(),
	search_space_id: z.number(),
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
export type ToolSettingsResponse = z.infer<typeof toolSettingsResponse>;
export type ToolSettingsUpdateRequest = z.infer<typeof toolSettingsUpdateRequest>;
export type ToolEvaluationExpected = z.infer<typeof toolEvaluationExpected>;
export type ToolEvaluationTestCase = z.infer<typeof toolEvaluationTestCase>;
export type ToolEvaluationRequest = z.infer<typeof toolEvaluationRequest>;
export type ToolEvaluationMetrics = z.infer<typeof toolEvaluationMetrics>;
export type ToolEvaluationCaseResult = z.infer<typeof toolEvaluationCaseResult>;
export type ToolMetadataSuggestion = z.infer<typeof toolMetadataSuggestion>;
export type ToolEvaluationResponse = z.infer<typeof toolEvaluationResponse>;
export type ToolSuggestionRequest = z.infer<typeof toolSuggestionRequest>;
export type ToolSuggestionResponse = z.infer<typeof toolSuggestionResponse>;
export type ToolApplySuggestionItem = z.infer<typeof toolApplySuggestionItem>;
export type ToolApplySuggestionsRequest = z.infer<typeof toolApplySuggestionsRequest>;
export type ToolApplySuggestionsResponse = z.infer<typeof toolApplySuggestionsResponse>;
