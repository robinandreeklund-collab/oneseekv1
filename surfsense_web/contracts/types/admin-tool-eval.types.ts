/**
 * Type definitions and Zod schemas for Admin Tool Evaluation
 */

import { z } from "zod";

// Request schemas

export const singleQueryRequestSchema = z.object({
	query: z.string().min(1, "Query cannot be empty"),
	expected_tools: z.array(z.string()).optional().nullable(),
	limit: z.number().int().min(1).max(10).default(2),
	primary_namespaces: z.array(z.array(z.string())).optional().nullable(),
	fallback_namespaces: z.array(z.array(z.string())).optional().nullable(),
});

export type SingleQueryRequest = z.infer<typeof singleQueryRequestSchema>;

// Response schemas

export const scoringDetailSchema = z.object({
	tool_id: z.string(),
	name: z.string(),
	namespace: z.array(z.string()),
	base_score: z.number(),
	semantic_score: z.number(),
	total_score: z.number(),
	keywords_matched: z.array(z.string()),
	examples_matched: z.array(z.string()),
});

export type ScoringDetail = z.infer<typeof scoringDetailSchema>;

export const singleQueryResponseSchema = z.object({
	query: z.string(),
	selected_tools: z.array(z.string()),
	scoring_details: z.array(scoringDetailSchema),
	rerank_trace: z.array(z.record(z.any())).nullable().optional(),
	match_type: z.string().nullable().optional(),
	latency_ms: z.number(),
});

export type SingleQueryResponse = z.infer<typeof singleQueryResponseSchema>;

// Evaluation report schemas

export const categoryResultSchema = z.object({
	category_id: z.string(),
	category_name: z.string(),
	total_tests: z.number(),
	route_accuracy: z.number(),
	sub_route_accuracy: z.number(),
	agent_exact_rate: z.number(),
	agent_avg_overlap: z.number(),
	tool_exact_rate: z.number(),
	tool_acceptable_rate: z.number(),
	tool_partial_rate: z.number(),
	avg_composite_score: z.number(),
	avg_latency_ms: z.number(),
	failed_tests: z.array(z.any()), // Complex nested structure, use any for simplicity
});

export type CategoryResult = z.infer<typeof categoryResultSchema>;

export const evalRunResponseSchema = z.object({
	suite_name: z.string(),
	total_tests: z.number(),
	timestamp: z.string(),
	
	// Overall metrics
	overall_route_accuracy: z.number(),
	overall_sub_route_accuracy: z.number(),
	overall_agent_exact_rate: z.number(),
	overall_agent_avg_overlap: z.number(),
	overall_tool_exact_rate: z.number(),
	overall_tool_acceptable_rate: z.number(),
	overall_tool_partial_rate: z.number(),
	overall_avg_composite_score: z.number(),
	overall_avg_latency_ms: z.number(),
	
	// Detailed results
	category_results: z.array(categoryResultSchema),
	by_difficulty: z.record(z.record(z.number())),
	route_confusion_matrix: z.record(z.record(z.number())),
	failure_patterns: z.record(z.number()),
	recommendations: z.array(z.string()),
});

export type EvalRunResponse = z.infer<typeof evalRunResponseSchema>;

export const invalidateCacheResponseSchema = z.object({
	success: z.boolean(),
	message: z.string(),
});

export type InvalidateCacheResponse = z.infer<typeof invalidateCacheResponseSchema>;
