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
	retrieval_feedback_db_enabled: z.boolean().optional().default(false),
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
	weather_suite_mode: z.string().optional().default("mixed"),
	question_count: z.number().int().optional().default(12),
	difficulty_profile: z.string().optional().default("mixed"),
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

export const toolEvaluationStageHistoryCategoryItem = z.object({
	category_id: z.string(),
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
});

export const toolEvaluationStageHistoryItem = z.object({
	run_at: z.string(),
	stage: z.string(),
	eval_name: z.string().nullable().optional(),
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
	stage_metric_name: z.string().nullable().optional(),
	stage_metric_value: z.number().nullable().optional(),
	category_breakdown: z.array(toolEvaluationStageHistoryCategoryItem).default([]),
});

export const toolEvaluationStageCategorySeriesPoint = z.object({
	run_at: z.string(),
	eval_name: z.string().nullable().optional(),
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
	stage_metric_value: z.number().nullable().optional(),
});

export const toolEvaluationStageCategorySeries = z.object({
	category_id: z.string(),
	points: z.array(toolEvaluationStageCategorySeriesPoint).default([]),
});

export const toolEvaluationStageHistoryResponse = z.object({
	stage: z.string(),
	items: z.array(toolEvaluationStageHistoryItem).default([]),
	category_series: z.array(toolEvaluationStageCategorySeries).default([]),
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

export const agentMetadataItem = z.object({
	agent_id: z.string(),
	label: z.string(),
	description: z.string(),
	keywords: z.array(z.string()),
	prompt_key: z.string().nullable().optional(),
	namespace: z.array(z.string()).optional().default([]),
	has_override: z.boolean().optional().default(false),
});

export const agentMetadataUpdateItem = z.object({
	agent_id: z.string(),
	label: z.string(),
	description: z.string(),
	keywords: z.array(z.string()),
	prompt_key: z.string().nullable().optional(),
	namespace: z.array(z.string()).optional().default([]),
});

export const intentMetadataItem = z.object({
	intent_id: z.string(),
	label: z.string(),
	route: z.string(),
	description: z.string(),
	keywords: z.array(z.string()),
	priority: z.number().int().optional().default(500),
	enabled: z.boolean().optional().default(true),
	has_override: z.boolean().optional().default(false),
});

export const intentMetadataUpdateItem = z.object({
	intent_id: z.string(),
	label: z.string(),
	route: z.string(),
	description: z.string(),
	keywords: z.array(z.string()),
	priority: z.number().int().optional().default(500),
	enabled: z.boolean().optional().default(true),
});

export const metadataCatalogResponse = z.object({
	search_space_id: z.number(),
	metadata_version_hash: z.string(),
	tool_categories: z.array(toolCategoryResponse).default([]),
	agents: z.array(agentMetadataItem).default([]),
	intents: z.array(intentMetadataItem).default([]),
});

export const metadataCatalogUpdateRequest = z.object({
	tools: z.array(toolMetadataUpdateItem).optional().default([]),
	agents: z.array(agentMetadataUpdateItem).optional().default([]),
	intents: z.array(intentMetadataUpdateItem).optional().default([]),
});

export const metadataCatalogAuditConfusionPair = z.object({
	expected_label: z.string(),
	predicted_label: z.string(),
	count: z.number().int(),
});

export const metadataCatalogAuditPathConfusionPair = z.object({
	expected_path: z.string(),
	predicted_path: z.string(),
	count: z.number().int(),
});

export const metadataCatalogAuditLayerResult = z.object({
	expected_label: z.string().nullable().optional(),
	predicted_label: z.string().nullable().optional(),
	top1: z.string().nullable().optional(),
	top2: z.string().nullable().optional(),
	margin: z.number().nullable().optional(),
	score_breakdown: z.array(z.record(z.string(), z.unknown())).optional().default([]),
});

export const metadataCatalogAuditToolVectorDiagnostics = z.object({
	vector_top_k: z.number().int().optional().default(5),
	vector_selected_ids: z.array(z.string()).optional().default([]),
	predicted_tool_vector_selected: z.boolean().optional().default(false),
	predicted_tool_vector_rank: z.number().int().nullable().optional(),
	predicted_tool_vector_only: z.boolean().optional().default(false),
	predicted_tool_lexical_candidate: z.boolean().optional().default(false),
	expected_tool_vector_selected: z.boolean().optional().default(false),
	expected_tool_vector_rank: z.number().int().nullable().optional(),
	expected_tool_vector_only: z.boolean().optional().default(false),
	expected_tool_lexical_candidate: z.boolean().optional().default(false),
});

export const metadataCatalogAuditVectorRecallSummary = z.object({
	top_k: z.number().int().optional().default(5),
	probes_with_vector_candidates: z.number().int().optional().default(0),
	probes_with_top1_from_vector: z.number().int().optional().default(0),
	probes_with_top1_vector_only: z.number().int().optional().default(0),
	probes_with_expected_tool_in_vector_top_k: z.number().int().optional().default(0),
	probes_with_expected_tool_vector_only: z.number().int().optional().default(0),
	probes_with_correct_tool_and_vector_support: z.number().int().optional().default(0),
	share_probes_with_vector_candidates: z.number().optional().default(0),
	share_top1_from_vector: z.number().optional().default(0),
	share_expected_tool_in_vector_top_k: z.number().optional().default(0),
});

export const metadataCatalogAuditToolEmbeddingContext = z.object({
	enabled: z.boolean().optional().default(true),
	context_fields: z.array(z.string()).optional().default([]),
	description: z.string().nullable().optional(),
});

export const metadataCatalogAuditProbeItem = z.object({
	probe_id: z.string(),
	query: z.string(),
	source: z.string(),
	target_tool_id: z.string(),
	expected_path: z.string(),
	predicted_path: z.string(),
	intent: metadataCatalogAuditLayerResult,
	agent: metadataCatalogAuditLayerResult,
	tool: metadataCatalogAuditLayerResult,
	tool_vector_diagnostics: metadataCatalogAuditToolVectorDiagnostics.optional().default({
		vector_top_k: 5,
		vector_selected_ids: [],
		predicted_tool_vector_selected: false,
		predicted_tool_vector_rank: null,
		predicted_tool_vector_only: false,
		predicted_tool_lexical_candidate: false,
		expected_tool_vector_selected: false,
		expected_tool_vector_rank: null,
		expected_tool_vector_only: false,
		expected_tool_lexical_candidate: false,
	}),
});

export const metadataCatalogAuditSummary = z.object({
	total_probes: z.number().int().optional().default(0),
	intent_accuracy: z.number().optional().default(0),
	agent_accuracy: z.number().optional().default(0),
	tool_accuracy: z.number().optional().default(0),
	agent_accuracy_given_intent_correct: z.number().nullable().optional(),
	tool_accuracy_given_intent_agent_correct: z.number().nullable().optional(),
	intent_confusion_matrix: z.array(metadataCatalogAuditConfusionPair).optional().default([]),
	agent_confusion_matrix: z.array(metadataCatalogAuditConfusionPair).optional().default([]),
	tool_confusion_matrix: z.array(metadataCatalogAuditConfusionPair).optional().default([]),
	path_confusion_matrix: z.array(metadataCatalogAuditPathConfusionPair).optional().default([]),
	vector_recall_summary: metadataCatalogAuditVectorRecallSummary
		.optional()
		.default({
			top_k: 5,
			probes_with_vector_candidates: 0,
			probes_with_top1_from_vector: 0,
			probes_with_top1_vector_only: 0,
			probes_with_expected_tool_in_vector_top_k: 0,
			probes_with_expected_tool_vector_only: 0,
			probes_with_correct_tool_and_vector_support: 0,
			share_probes_with_vector_candidates: 0,
			share_top1_from_vector: 0,
			share_expected_tool_in_vector_top_k: 0,
		}),
	tool_embedding_context: metadataCatalogAuditToolEmbeddingContext
		.optional()
		.default({ enabled: true, context_fields: [], description: null }),
});

export const metadataCatalogAuditRunRequest = z.object({
	search_space_id: z.number().nullable().optional(),
	metadata_patch: z.array(toolMetadataUpdateItem).optional().default([]),
	intent_metadata_patch: z.array(intentMetadataUpdateItem).optional().default([]),
	agent_metadata_patch: z.array(agentMetadataUpdateItem).optional().default([]),
	tool_ids: z.array(z.string()).optional().default([]),
	tool_id_prefix: z.string().nullable().optional(),
	include_existing_examples: z.boolean().optional().default(true),
	include_llm_generated: z.boolean().optional().default(true),
	llm_queries_per_tool: z.number().int().optional().default(3),
	max_queries_per_tool: z.number().int().optional().default(6),
	hard_negatives_per_tool: z.number().int().optional().default(1),
	retrieval_limit: z.number().int().optional().default(5),
	max_tools: z.number().int().optional().default(25),
	probe_generation_parallelism: z.number().int().optional().default(1),
	probe_round: z.number().int().optional().default(1),
	exclude_probe_queries: z.array(z.string()).optional().default([]),
});

export const metadataCatalogAuditRunResponse = z.object({
	search_space_id: z.number(),
	metadata_version_hash: z.string(),
	retrieval_tuning: toolRetrievalTuning,
	probes: z.array(metadataCatalogAuditProbeItem).optional().default([]),
	summary: metadataCatalogAuditSummary,
	available_intent_ids: z.array(z.string()).optional().default([]),
	available_agent_ids: z.array(z.string()).optional().default([]),
	available_tool_ids: z.array(z.string()).optional().default([]),
});

export const metadataCatalogAuditAnnotationItem = z.object({
	probe_id: z.string(),
	query: z.string(),
	expected_intent_id: z.string().nullable().optional(),
	expected_agent_id: z.string().nullable().optional(),
	expected_tool_id: z.string().nullable().optional(),
	predicted_intent_id: z.string().nullable().optional(),
	predicted_agent_id: z.string().nullable().optional(),
	predicted_tool_id: z.string().nullable().optional(),
	intent_is_correct: z.boolean().optional().default(true),
	corrected_intent_id: z.string().nullable().optional(),
	agent_is_correct: z.boolean().optional().default(true),
	corrected_agent_id: z.string().nullable().optional(),
	tool_is_correct: z.boolean().optional().default(true),
	corrected_tool_id: z.string().nullable().optional(),
	intent_score_breakdown: z.array(z.record(z.string(), z.unknown())).optional().default([]),
	agent_score_breakdown: z.array(z.record(z.string(), z.unknown())).optional().default([]),
	tool_score_breakdown: z.array(z.record(z.string(), z.unknown())).optional().default([]),
	tool_vector_diagnostics: metadataCatalogAuditToolVectorDiagnostics.nullable().optional(),
});

export const metadataCatalogAuditSuggestionRequest = z.object({
	search_space_id: z.number().nullable().optional(),
	metadata_patch: z.array(toolMetadataUpdateItem).optional().default([]),
	intent_metadata_patch: z.array(intentMetadataUpdateItem).optional().default([]),
	agent_metadata_patch: z.array(agentMetadataUpdateItem).optional().default([]),
	annotations: z.array(metadataCatalogAuditAnnotationItem).optional().default([]),
	max_suggestions: z.number().int().optional().default(20),
	llm_parallelism: z.number().int().optional().default(1),
});

export const metadataCatalogAuditSuggestionResponse = z.object({
	tool_suggestions: z
		.array(
			z.object({
				tool_id: z.string(),
				failed_test_ids: z.array(z.string()).optional().default([]),
				rationale: z.string(),
				current_metadata: toolMetadataUpdateItem,
				proposed_metadata: toolMetadataUpdateItem,
			})
		)
		.optional()
		.default([]),
	intent_suggestions: z
		.array(
			z.object({
				intent_id: z.string(),
				failed_probe_ids: z.array(z.string()).optional().default([]),
				rationale: z.string(),
				current_metadata: intentMetadataUpdateItem,
				proposed_metadata: intentMetadataUpdateItem,
			})
		)
		.optional()
		.default([]),
	agent_suggestions: z
		.array(
			z.object({
				agent_id: z.string(),
				failed_probe_ids: z.array(z.string()).optional().default([]),
				rationale: z.string(),
				current_metadata: agentMetadataUpdateItem,
				proposed_metadata: agentMetadataUpdateItem,
			})
		)
		.optional()
		.default([]),
	total_annotations: z.number().int().optional().default(0),
	reviewed_intent_failures: z.number().int().optional().default(0),
	reviewed_agent_failures: z.number().int().optional().default(0),
	reviewed_tool_failures: z.number().int().optional().default(0),
	diagnostics: z
		.object({
			total_ms: z.number().optional().default(0),
			preparation_ms: z.number().optional().default(0),
			tool_stage_ms: z.number().optional().default(0),
			intent_stage_ms: z.number().optional().default(0),
			agent_stage_ms: z.number().optional().default(0),
			annotations_count: z.number().int().optional().default(0),
			annotations_payload_bytes: z.number().int().optional().default(0),
			tool_failure_candidates: z.number().int().optional().default(0),
			intent_failure_candidates: z.number().int().optional().default(0),
			agent_failure_candidates: z.number().int().optional().default(0),
			llm_parallelism: z.number().int().optional().default(1),
			max_suggestions: z.number().int().optional().default(20),
		})
		.optional()
		.default({
			total_ms: 0,
			preparation_ms: 0,
			tool_stage_ms: 0,
			intent_stage_ms: 0,
			agent_stage_ms: 0,
			annotations_count: 0,
			annotations_payload_bytes: 0,
			tool_failure_candidates: 0,
			intent_failure_candidates: 0,
			agent_failure_candidates: 0,
			llm_parallelism: 1,
			max_suggestions: 20,
		}),
});

export const toolEvaluationExpected = z.object({
	category: z.string().nullable().optional(),
	tool: z.string().nullable().optional(),
	agent: z.string().nullable().optional(),
	acceptable_agents: z.array(z.string()).optional().default([]),
	acceptable_tools: z.array(z.string()).optional().default([]),
	intent: z.string().nullable().optional(),
	route: z.string().nullable().optional(),
	sub_route: z.string().nullable().optional(),
	graph_complexity: z.string().nullable().optional(),
	execution_strategy: z.string().nullable().optional(),
	plan_requirements: z.array(z.string()).optional().default([]),
});

export const toolApiInputEvaluationExpected = z.object({
	category: z.string().nullable().optional(),
	tool: z.string().nullable().optional(),
	agent: z.string().nullable().optional(),
	acceptable_agents: z.array(z.string()).optional().default([]),
	acceptable_tools: z.array(z.string()).optional().default([]),
	intent: z.string().nullable().optional(),
	route: z.string().nullable().optional(),
	sub_route: z.string().nullable().optional(),
	graph_complexity: z.string().nullable().optional(),
	execution_strategy: z.string().nullable().optional(),
	plan_requirements: z.array(z.string()).optional().default([]),
	required_fields: z.array(z.string()).optional().default([]),
	field_values: z.record(z.string(), z.unknown()).optional().default({}),
	allow_clarification: z.boolean().nullable().optional(),
});

export const toolEvaluationTestCase = z.object({
	id: z.string(),
	question: z.string(),
	difficulty: z.string().nullable().optional(),
	expected: toolEvaluationExpected.nullable().optional(),
	allowed_tools: z.array(z.string()).optional().default([]),
});

export const toolApiInputEvaluationTestCase = z.object({
	id: z.string(),
	question: z.string(),
	difficulty: z.string().nullable().optional(),
	expected: toolApiInputEvaluationExpected.nullable().optional(),
	allowed_tools: z.array(z.string()).optional().default([]),
});

export const toolDifficultyBreakdownItem = z.object({
	difficulty: z.string(),
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
	gated_success_rate: z.number().nullable().optional(),
});

export const toolEvaluationRequest = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	search_space_id: z.number().nullable().optional(),
	retrieval_limit: z.number().int().optional().default(5),
	use_llm_supervisor_review: z.boolean().optional().default(true),
	tests: z.array(toolEvaluationTestCase),
	metadata_patch: z.array(toolMetadataUpdateItem).optional().default([]),
	retrieval_tuning_override: toolRetrievalTuning.nullable().optional(),
});

export const toolApiInputEvaluationRequest = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	search_space_id: z.number().nullable().optional(),
	retrieval_limit: z.number().int().optional().default(5),
	use_llm_supervisor_review: z.boolean().optional().default(true),
	tests: z.array(toolApiInputEvaluationTestCase),
	holdout_tests: z.array(toolApiInputEvaluationTestCase).optional().default([]),
	metadata_patch: z.array(toolMetadataUpdateItem).optional().default([]),
	retrieval_tuning_override: toolRetrievalTuning.nullable().optional(),
});

export const toolEvaluationMetrics = z.object({
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
	gated_success_rate: z.number().nullable().optional(),
	intent_accuracy: z.number().nullable().optional(),
	route_accuracy: z.number().nullable().optional(),
	sub_route_accuracy: z.number().nullable().optional(),
	graph_complexity_accuracy: z.number().nullable().optional(),
	execution_strategy_accuracy: z.number().nullable().optional(),
	agent_accuracy: z.number().nullable().optional(),
	plan_accuracy: z.number().nullable().optional(),
	supervisor_review_score: z.number().nullable().optional(),
	supervisor_review_pass_rate: z.number().nullable().optional(),
	category_accuracy: z.number().nullable().optional(),
	tool_accuracy: z.number().nullable().optional(),
	retrieval_recall_at_k: z.number().nullable().optional(),
	difficulty_breakdown: z.array(toolDifficultyBreakdownItem).optional().default([]),
});

export const toolPlanRequirementCheck = z.object({
	requirement: z.string(),
	passed: z.boolean(),
});

export const toolSupervisorReviewRubricItem = z.object({
	key: z.string(),
	label: z.string(),
	passed: z.boolean(),
	weight: z.number().optional().default(1),
	evidence: z.string().nullable().optional(),
});

export const toolEvaluationCaseResult = z.object({
	test_id: z.string(),
	question: z.string(),
	difficulty: z.string().nullable().optional(),
	expected_intent: z.string().nullable().optional(),
	expected_route: z.string().nullable().optional(),
	expected_sub_route: z.string().nullable().optional(),
	expected_graph_complexity: z.string().nullable().optional(),
	expected_execution_strategy: z.string().nullable().optional(),
	expected_agent: z.string().nullable().optional(),
	expected_acceptable_agents: z.array(z.string()).default([]),
	expected_category: z.string().nullable().optional(),
	expected_tool: z.string().nullable().optional(),
	expected_acceptable_tools: z.array(z.string()).default([]),
	allowed_tools: z.array(z.string()).default([]),
	selected_route: z.string().nullable().optional(),
	selected_sub_route: z.string().nullable().optional(),
	selected_intent: z.string().nullable().optional(),
	selected_graph_complexity: z.string().nullable().optional(),
	selected_execution_strategy: z.string().nullable().optional(),
	selected_agent: z.string().nullable().optional(),
	agent_selection_analysis: z.string().default(""),
	selected_category: z.string().nullable().optional(),
	selected_tool: z.string().nullable().optional(),
	planning_analysis: z.string().default(""),
	planning_steps: z.array(z.string()).default([]),
	supervisor_trace: z.record(z.string(), z.unknown()).default({}),
	supervisor_review_score: z.number().nullable().optional(),
	supervisor_review_passed: z.boolean().nullable().optional(),
	supervisor_review_rationale: z.string().nullable().optional(),
	supervisor_review_issues: z.array(z.string()).default([]),
	supervisor_review_rubric: z.array(toolSupervisorReviewRubricItem).default([]),
	plan_requirement_checks: z.array(toolPlanRequirementCheck).default([]),
	retrieval_top_tools: z.array(z.string()).default([]),
	retrieval_top_categories: z.array(z.string()).default([]),
	retrieval_breakdown: z.array(z.record(z.string(), z.unknown())).default([]),
	retrieval_hit_expected_tool: z.boolean().nullable().optional(),
	consistency_warnings: z.array(z.string()).default([]),
	expected_normalized: z.boolean().optional().default(false),
	passed_intent: z.boolean().nullable().optional(),
	passed_route: z.boolean().nullable().optional(),
	passed_sub_route: z.boolean().nullable().optional(),
	passed_graph_complexity: z.boolean().nullable().optional(),
	passed_execution_strategy: z.boolean().nullable().optional(),
	passed_agent: z.boolean().nullable().optional(),
	passed_plan: z.boolean().nullable().optional(),
	passed_category: z.boolean().nullable().optional(),
	passed_tool: z.boolean().nullable().optional(),
	passed_with_agent_gate: z.boolean().nullable().optional(),
	agent_gate_score: z.number().nullable().optional(),
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
	difficulty: z.string().nullable().optional(),
	expected_intent: z.string().nullable().optional(),
	expected_route: z.string().nullable().optional(),
	expected_sub_route: z.string().nullable().optional(),
	expected_graph_complexity: z.string().nullable().optional(),
	expected_execution_strategy: z.string().nullable().optional(),
	expected_agent: z.string().nullable().optional(),
	expected_acceptable_agents: z.array(z.string()).default([]),
	expected_category: z.string().nullable().optional(),
	expected_tool: z.string().nullable().optional(),
	expected_acceptable_tools: z.array(z.string()).default([]),
	allowed_tools: z.array(z.string()).default([]),
	selected_route: z.string().nullable().optional(),
	selected_sub_route: z.string().nullable().optional(),
	selected_intent: z.string().nullable().optional(),
	selected_graph_complexity: z.string().nullable().optional(),
	selected_execution_strategy: z.string().nullable().optional(),
	selected_agent: z.string().nullable().optional(),
	agent_selection_analysis: z.string().default(""),
	selected_category: z.string().nullable().optional(),
	selected_tool: z.string().nullable().optional(),
	planning_analysis: z.string().default(""),
	planning_steps: z.array(z.string()).default([]),
	supervisor_trace: z.record(z.string(), z.unknown()).default({}),
	supervisor_review_score: z.number().nullable().optional(),
	supervisor_review_passed: z.boolean().nullable().optional(),
	supervisor_review_rationale: z.string().nullable().optional(),
	supervisor_review_issues: z.array(z.string()).default([]),
	supervisor_review_rubric: z.array(toolSupervisorReviewRubricItem).default([]),
	plan_requirement_checks: z.array(toolPlanRequirementCheck).default([]),
	retrieval_top_tools: z.array(z.string()).default([]),
	retrieval_top_categories: z.array(z.string()).default([]),
	retrieval_breakdown: z.array(z.record(z.string(), z.unknown())).default([]),
	consistency_warnings: z.array(z.string()).default([]),
	expected_normalized: z.boolean().optional().default(false),
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
	passed_intent: z.boolean().nullable().optional(),
	passed_route: z.boolean().nullable().optional(),
	passed_sub_route: z.boolean().nullable().optional(),
	passed_graph_complexity: z.boolean().nullable().optional(),
	passed_execution_strategy: z.boolean().nullable().optional(),
	passed_agent: z.boolean().nullable().optional(),
	passed_plan: z.boolean().nullable().optional(),
	passed_category: z.boolean().nullable().optional(),
	passed_tool: z.boolean().nullable().optional(),
	passed_api_input: z.boolean().nullable().optional(),
	passed_with_agent_gate: z.boolean().nullable().optional(),
	agent_gate_score: z.number().nullable().optional(),
	passed: z.boolean(),
});

export const toolApiInputEvaluationMetrics = z.object({
	total_tests: z.number(),
	passed_tests: z.number(),
	success_rate: z.number(),
	gated_success_rate: z.number().nullable().optional(),
	intent_accuracy: z.number().nullable().optional(),
	route_accuracy: z.number().nullable().optional(),
	sub_route_accuracy: z.number().nullable().optional(),
	graph_complexity_accuracy: z.number().nullable().optional(),
	execution_strategy_accuracy: z.number().nullable().optional(),
	agent_accuracy: z.number().nullable().optional(),
	plan_accuracy: z.number().nullable().optional(),
	supervisor_review_score: z.number().nullable().optional(),
	supervisor_review_pass_rate: z.number().nullable().optional(),
	category_accuracy: z.number().nullable().optional(),
	tool_accuracy: z.number().nullable().optional(),
	schema_validity_rate: z.number().nullable().optional(),
	required_field_recall: z.number().nullable().optional(),
	field_value_accuracy: z.number().nullable().optional(),
	clarification_accuracy: z.number().nullable().optional(),
	difficulty_breakdown: z.array(toolDifficultyBreakdownItem).optional().default([]),
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

export const toolIntentDefinitionSuggestion = z.object({
	intent_id: z.string(),
	failed_test_ids: z.array(z.string()).default([]),
	rationale: z.string(),
	current_definition: z.record(z.string(), z.unknown()).default({}),
	proposed_definition: z.record(z.string(), z.unknown()).default({}),
	prompt_key: z.string().nullable().optional(),
	current_prompt: z.string().nullable().optional(),
	proposed_prompt: z.string().nullable().optional(),
});

export const toolEvaluationMetricDeltaItem = z.object({
	metric: z.string(),
	previous: z.number().nullable().optional(),
	current: z.number().nullable().optional(),
	delta: z.number().nullable().optional(),
});

export const toolEvaluationRunComparison = z.object({
	stage: z.string(),
	stage_metric_name: z.string().nullable().optional(),
	trend: z.string(),
	previous_run_at: z.string().nullable().optional(),
	previous_eval_name: z.string().nullable().optional(),
	previous_success_rate: z.number().nullable().optional(),
	current_success_rate: z.number(),
	success_rate_delta: z.number().nullable().optional(),
	previous_stage_metric: z.number().nullable().optional(),
	current_stage_metric: z.number().nullable().optional(),
	stage_metric_delta: z.number().nullable().optional(),
	previous_gated_success_rate: z.number().nullable().optional(),
	current_gated_success_rate: z.number().nullable().optional(),
	gated_success_rate_delta: z.number().nullable().optional(),
	metric_deltas: z.array(toolEvaluationMetricDeltaItem).default([]),
	guidance: z.array(z.string()).default([]),
});

export const toolEvaluationResponse = z.object({
	eval_name: z.string().nullable().optional(),
	target_success_rate: z.number().nullable().optional(),
	metrics: toolEvaluationMetrics,
	results: z.array(toolEvaluationCaseResult),
	suggestions: z.array(toolMetadataSuggestion),
	prompt_suggestions: z.array(toolApiInputPromptSuggestion).default([]),
	intent_suggestions: z.array(toolIntentDefinitionSuggestion).default([]),
	retrieval_tuning: toolRetrievalTuning,
	retrieval_tuning_suggestion: toolRetrievalTuningSuggestion.nullable().optional(),
	consistency_summary: z
		.object({
			total_tests: z.number().int().default(0),
			warned_tests: z.number().int().default(0),
			normalized_tests: z.number().int().default(0),
		})
		.default({ total_tests: 0, warned_tests: 0, normalized_tests: 0 }),
	comparison: toolEvaluationRunComparison.nullable().optional(),
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
	intent_suggestions: z.array(toolIntentDefinitionSuggestion).default([]),
	retrieval_tuning: toolRetrievalTuning,
	consistency_summary: z
		.object({
			total_tests: z.number().int().default(0),
			warned_tests: z.number().int().default(0),
			normalized_tests: z.number().int().default(0),
		})
		.default({ total_tests: 0, warned_tests: 0, normalized_tests: 0 }),
	comparison: toolEvaluationRunComparison.nullable().optional(),
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
	consistency_warnings: z.array(z.string()).default([]),
	expected_normalized: z.boolean().nullable().optional(),
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

export const toolAutoLoopGenerationConfig = z.object({
	eval_type: z.string().optional().default("tool_selection"),
	mode: z.string().optional().default("category"),
	provider_key: z.string().nullable().optional(),
	category_id: z.string().nullable().optional(),
	weather_suite_mode: z.string().optional().default("mixed"),
	question_count: z.number().int().optional().default(12),
	difficulty_profile: z.string().optional().default("mixed"),
	eval_name: z.string().nullable().optional(),
	include_allowed_tools: z.boolean().optional().default(true),
});

export const toolAutoLoopRequest = z.object({
	search_space_id: z.number().nullable().optional(),
	generation: toolAutoLoopGenerationConfig,
	use_holdout_suite: z.boolean().optional().default(false),
	holdout_question_count: z.number().int().optional().default(8),
	holdout_difficulty_profile: z.string().nullable().optional(),
	target_success_rate: z.number().optional().default(0.85),
	max_iterations: z.number().int().optional().default(6),
	patience: z.number().int().optional().default(2),
	min_improvement_delta: z.number().optional().default(0.005),
	retrieval_limit: z.number().int().optional().default(5),
	use_llm_supervisor_review: z.boolean().optional().default(true),
	include_metadata_suggestions: z.boolean().optional().default(true),
	include_prompt_suggestions: z.boolean().optional().default(true),
	include_retrieval_tuning_suggestions: z.boolean().optional().default(true),
});

export const toolAutoLoopStartResponse = z.object({
	job_id: z.string(),
	status: z.string(),
	total_iterations: z.number(),
	target_success_rate: z.number(),
});

export const toolAutoLoopDraftPromptItem = z.object({
	prompt_key: z.string(),
	proposed_prompt: z.string(),
	rationale: z.string().nullable().optional(),
	related_tools: z.array(z.string()).default([]),
});

export const toolAutoLoopDraftBundle = z.object({
	metadata_patch: z.array(toolMetadataUpdateItem).default([]),
	prompt_patch: z.array(toolAutoLoopDraftPromptItem).default([]),
	retrieval_tuning_override: toolRetrievalTuning.nullable().optional(),
});

export const toolAutoLoopIterationSummary = z.object({
	iteration: z.number(),
	success_rate: z.number(),
	gated_success_rate: z.number().nullable().optional(),
	passed_tests: z.number(),
	total_tests: z.number(),
	success_delta_vs_previous: z.number().nullable().optional(),
	holdout_success_rate: z.number().nullable().optional(),
	holdout_passed_tests: z.number().nullable().optional(),
	holdout_total_tests: z.number().nullable().optional(),
	holdout_delta_vs_previous: z.number().nullable().optional(),
	combined_score: z.number().nullable().optional(),
	combined_delta_vs_previous: z.number().nullable().optional(),
	metadata_changes_applied: z.number().optional().default(0),
	prompt_changes_applied: z.number().optional().default(0),
	retrieval_tuning_changed: z.boolean().optional().default(false),
	note: z.string().nullable().optional(),
});

export const toolAutoLoopResult = z.object({
	status: z.string(),
	stop_reason: z.string(),
	target_success_rate: z.number(),
	best_success_rate: z.number(),
	best_iteration: z.number(),
	no_improvement_runs: z.number(),
	generated_suite: z.record(z.string(), z.unknown()),
	generated_holdout_suite: z.record(z.string(), z.unknown()).nullable().optional(),
	iterations: z.array(toolAutoLoopIterationSummary).default([]),
	final_evaluation: toolEvaluationResponse,
	final_holdout_evaluation: toolEvaluationResponse.nullable().optional(),
	draft_changes: toolAutoLoopDraftBundle,
});

export const toolAutoLoopJobStatusResponse = z.object({
	job_id: z.string(),
	status: z.string(),
	total_iterations: z.number(),
	completed_iterations: z.number(),
	started_at: z.string().nullable().optional(),
	completed_at: z.string().nullable().optional(),
	updated_at: z.string(),
	current_iteration: z.number().optional().default(0),
	best_success_rate: z.number().nullable().optional(),
	no_improvement_runs: z.number().optional().default(0),
	message: z.string().nullable().optional(),
	iterations: z.array(toolAutoLoopIterationSummary).default([]),
	result: toolAutoLoopResult.nullable().optional(),
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
export type ToolDifficultyBreakdownItem = z.infer<typeof toolDifficultyBreakdownItem>;
export type ToolEvalLibraryGenerateRequest = z.infer<
	typeof toolEvalLibraryGenerateRequest
>;
export type ToolEvalLibraryFileItem = z.infer<typeof toolEvalLibraryFileItem>;
export type ToolEvalLibraryListResponse = z.infer<typeof toolEvalLibraryListResponse>;
export type ToolEvalLibraryFileResponse = z.infer<typeof toolEvalLibraryFileResponse>;
export type ToolEvalLibraryGenerateResponse = z.infer<
	typeof toolEvalLibraryGenerateResponse
>;
export type ToolEvaluationStageHistoryCategoryItem = z.infer<
	typeof toolEvaluationStageHistoryCategoryItem
>;
export type ToolEvaluationStageHistoryItem = z.infer<typeof toolEvaluationStageHistoryItem>;
export type ToolEvaluationStageCategorySeriesPoint = z.infer<
	typeof toolEvaluationStageCategorySeriesPoint
>;
export type ToolEvaluationStageCategorySeries = z.infer<
	typeof toolEvaluationStageCategorySeries
>;
export type ToolEvaluationStageHistoryResponse = z.infer<
	typeof toolEvaluationStageHistoryResponse
>;
export type ToolSettingsResponse = z.infer<typeof toolSettingsResponse>;
export type ToolSettingsUpdateRequest = z.infer<typeof toolSettingsUpdateRequest>;
export type AgentMetadataItem = z.infer<typeof agentMetadataItem>;
export type AgentMetadataUpdateItem = z.infer<typeof agentMetadataUpdateItem>;
export type IntentMetadataItem = z.infer<typeof intentMetadataItem>;
export type IntentMetadataUpdateItem = z.infer<typeof intentMetadataUpdateItem>;
export type MetadataCatalogResponse = z.infer<typeof metadataCatalogResponse>;
export type MetadataCatalogUpdateRequest = z.infer<typeof metadataCatalogUpdateRequest>;
export type MetadataCatalogAuditConfusionPair = z.infer<
	typeof metadataCatalogAuditConfusionPair
>;
export type MetadataCatalogAuditPathConfusionPair = z.infer<
	typeof metadataCatalogAuditPathConfusionPair
>;
export type MetadataCatalogAuditLayerResult = z.infer<
	typeof metadataCatalogAuditLayerResult
>;
export type MetadataCatalogAuditToolVectorDiagnostics = z.infer<
	typeof metadataCatalogAuditToolVectorDiagnostics
>;
export type MetadataCatalogAuditVectorRecallSummary = z.infer<
	typeof metadataCatalogAuditVectorRecallSummary
>;
export type MetadataCatalogAuditToolEmbeddingContext = z.infer<
	typeof metadataCatalogAuditToolEmbeddingContext
>;
export type MetadataCatalogAuditProbeItem = z.infer<typeof metadataCatalogAuditProbeItem>;
export type MetadataCatalogAuditSummary = z.infer<typeof metadataCatalogAuditSummary>;
export type MetadataCatalogAuditRunRequest = z.infer<typeof metadataCatalogAuditRunRequest>;
export type MetadataCatalogAuditRunResponse = z.infer<typeof metadataCatalogAuditRunResponse>;
export type MetadataCatalogAuditAnnotationItem = z.infer<
	typeof metadataCatalogAuditAnnotationItem
>;
export type MetadataCatalogAuditSuggestionRequest = z.infer<
	typeof metadataCatalogAuditSuggestionRequest
>;
export type MetadataCatalogAuditSuggestionResponse = z.infer<
	typeof metadataCatalogAuditSuggestionResponse
>;
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
export type ToolSupervisorReviewRubricItem = z.infer<
	typeof toolSupervisorReviewRubricItem
>;
export type ToolEvaluationCaseResult = z.infer<typeof toolEvaluationCaseResult>;
export type ToolApiInputFieldCheck = z.infer<typeof toolApiInputFieldCheck>;
export type ToolApiInputEvaluationCaseResult = z.infer<
	typeof toolApiInputEvaluationCaseResult
>;
export type ToolApiInputEvaluationMetrics = z.infer<
	typeof toolApiInputEvaluationMetrics
>;
export type ToolMetadataSuggestion = z.infer<typeof toolMetadataSuggestion>;
export type ToolIntentDefinitionSuggestion = z.infer<
	typeof toolIntentDefinitionSuggestion
>;
export type ToolEvaluationMetricDeltaItem = z.infer<typeof toolEvaluationMetricDeltaItem>;
export type ToolEvaluationRunComparison = z.infer<typeof toolEvaluationRunComparison>;
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
export type ToolAutoLoopGenerationConfig = z.infer<typeof toolAutoLoopGenerationConfig>;
export type ToolAutoLoopRequest = z.infer<typeof toolAutoLoopRequest>;
export type ToolAutoLoopStartResponse = z.infer<typeof toolAutoLoopStartResponse>;
export type ToolAutoLoopDraftPromptItem = z.infer<typeof toolAutoLoopDraftPromptItem>;
export type ToolAutoLoopDraftBundle = z.infer<typeof toolAutoLoopDraftBundle>;
export type ToolAutoLoopIterationSummary = z.infer<typeof toolAutoLoopIterationSummary>;
export type ToolAutoLoopResult = z.infer<typeof toolAutoLoopResult>;
export type ToolAutoLoopJobStatusResponse = z.infer<
	typeof toolAutoLoopJobStatusResponse
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
