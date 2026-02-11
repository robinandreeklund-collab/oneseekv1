import { z } from "zod";

export const traceSpanSchema = z.object({
	id: z.string(),
	parent_id: z.string().nullable().optional(),
	name: z.string(),
	kind: z.string(),
	status: z.string(),
	sequence: z.number(),
	start_ts: z.string(),
	end_ts: z.string().nullable().optional(),
	duration_ms: z.number().nullable().optional(),
	input: z.any().optional().nullable(),
	output: z.any().optional().nullable(),
	meta: z.any().optional().nullable(),
});

export const traceSessionResponseSchema = z.object({
	session_id: z.string(),
	thread_id: z.number(),
	message_id: z.number().nullable().optional(),
	created_at: z.string(),
	ended_at: z.string().nullable().optional(),
	spans: z.array(traceSpanSchema),
});

export const traceSessionAttachRequestSchema = z.object({
	thread_id: z.number(),
	trace_session_id: z.string(),
	message_id: z.number(),
});

export type TraceSpan = z.infer<typeof traceSpanSchema>;
export type TraceSessionResponse = z.infer<typeof traceSessionResponseSchema>;
export type TraceSessionAttachRequest = z.infer<typeof traceSessionAttachRequestSchema>;
