import { z } from "zod";

// Tool lifecycle status enum
export const toolLifecycleStatus = z.enum(["review", "live"]);
export type ToolLifecycleStatus = z.infer<typeof toolLifecycleStatus>;

// Tool lifecycle status response
export const toolLifecycleStatusResponse = z.object({
	tool_id: z.string(),
	status: z.string(),
	success_rate: z.number().nullable(),
	total_tests: z.number().nullable(),
	last_eval_at: z.string().nullable(),
	required_success_rate: z.number(),
	changed_by_id: z.string().nullable(),
	changed_at: z.string(),
	notes: z.string().nullable(),
	created_at: z.string(),
});
export type ToolLifecycleStatusResponse = z.infer<typeof toolLifecycleStatusResponse>;

// Tool lifecycle list response
export const toolLifecycleListResponse = z.object({
	tools: z.array(toolLifecycleStatusResponse),
	total_count: z.number(),
	live_count: z.number(),
	review_count: z.number(),
});
export type ToolLifecycleListResponse = z.infer<typeof toolLifecycleListResponse>;

// Tool lifecycle update request
export const toolLifecycleUpdateRequest = z.object({
	status: z.string().regex(/^(review|live)$/),
	notes: z.string().optional(),
});
export type ToolLifecycleUpdateRequest = z.infer<typeof toolLifecycleUpdateRequest>;

// Tool lifecycle rollback request
export const toolLifecycleRollbackRequest = z.object({
	notes: z.string().min(1, "Reason for rollback is required"),
});
export type ToolLifecycleRollbackRequest = z.infer<typeof toolLifecycleRollbackRequest>;
