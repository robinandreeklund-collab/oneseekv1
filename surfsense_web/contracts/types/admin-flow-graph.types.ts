import { z } from "zod";

// ── Pipeline (LangGraph execution flow) ──────────────────────────────

export const pipelineNode = z.object({
	id: z.string(),
	label: z.string(),
	stage: z.string(),
	description: z.string(),
});

export const pipelineEdge = z.object({
	source: z.string(),
	target: z.string(),
	type: z.string(),
	label: z.string().optional(),
});

export const pipelineStage = z.object({
	id: z.string(),
	label: z.string(),
	color: z.string(),
});

// ── Routing (intent → agent → tool) ─────────────────────────────────

export const flowIntentNode = z.object({
	id: z.string(),
	type: z.literal("intent"),
	intent_id: z.string(),
	label: z.string(),
	description: z.string(),
	route: z.string(),
	keywords: z.array(z.string()),
	priority: z.number(),
	enabled: z.boolean(),
});

export const flowAgentNode = z.object({
	id: z.string(),
	type: z.literal("agent"),
	agent_id: z.string(),
	label: z.string(),
	description: z.string(),
	keywords: z.array(z.string()),
	prompt_key: z.string(),
	namespace: z.array(z.string()),
	routes: z.array(z.string()).default([]),
});

export const flowToolNode = z.object({
	id: z.string(),
	type: z.literal("tool"),
	tool_id: z.string(),
	label: z.string(),
	agent_id: z.string(),
});

export const flowEdge = z.object({
	source: z.string(),
	target: z.string(),
});

export const flowGraphResponse = z.object({
	// Pipeline
	pipeline_nodes: z.array(pipelineNode),
	pipeline_edges: z.array(pipelineEdge),
	pipeline_stages: z.array(pipelineStage),
	// Routing
	intents: z.array(flowIntentNode),
	agents: z.array(flowAgentNode),
	tools: z.array(flowToolNode),
	intent_agent_edges: z.array(flowEdge),
	agent_tool_edges: z.array(flowEdge),
});

export type PipelineNode = z.infer<typeof pipelineNode>;
export type PipelineEdge = z.infer<typeof pipelineEdge>;
export type PipelineStage = z.infer<typeof pipelineStage>;
export type FlowIntentNode = z.infer<typeof flowIntentNode>;
export type FlowAgentNode = z.infer<typeof flowAgentNode>;
export type FlowToolNode = z.infer<typeof flowToolNode>;
export type FlowEdge = z.infer<typeof flowEdge>;
export type FlowGraphResponse = z.infer<typeof flowGraphResponse>;
