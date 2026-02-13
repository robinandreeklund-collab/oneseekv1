import { z } from "zod";

export const agentPromptKeyEnum = z.enum([
	"router.top_level",
	"router.knowledge",
	"router.action",
	"agent.knowledge.docs",
	"agent.knowledge.internal",
	"agent.knowledge.external",
	"agent.action.web",
	"agent.action.media",
	"agent.action.travel",
	"agent.action.data",
	"agent.smalltalk.system",
	"agent.supervisor.system",
	"agent.worker.knowledge",
	"agent.worker.action",
	"agent.knowledge.system",
	"agent.action.system",
	"agent.media.system",
	"agent.browser.system",
	"agent.code.system",
	"agent.kartor.system",
	"agent.synthesis.system",
	"agent.statistics.system",
	"agent.bolag.system",
	"agent.trafik.system",
	"agent.riksdagen.system",
	"compare.analysis.system",
	"compare.external.system",
	"citation.instructions",
]);

export const agentPromptItem = z.object({
	key: agentPromptKeyEnum,
	label: z.string(),
	description: z.string(),
	default_prompt: z.string(),
	override_prompt: z.string().nullable().optional(),
});

export const agentPromptsResponse = z.object({
	items: z.array(agentPromptItem),
});

export const agentPromptUpdateItem = z.object({
	key: agentPromptKeyEnum,
	override_prompt: z.string().nullable().optional(),
});

export const agentPromptsUpdateRequest = z.object({
	items: z.array(agentPromptUpdateItem),
});

export const agentPromptHistoryItem = z.object({
	key: agentPromptKeyEnum,
	previous_prompt: z.string().nullable().optional(),
	new_prompt: z.string().nullable().optional(),
	updated_at: z.string(),
	updated_by_id: z.string().nullable().optional(),
});

export const agentPromptHistoryResponse = z.object({
	items: z.array(agentPromptHistoryItem),
});

export type AgentPromptItem = z.infer<typeof agentPromptItem>;
export type AgentPromptsResponse = z.infer<typeof agentPromptsResponse>;
export type AgentPromptUpdateItem = z.infer<typeof agentPromptUpdateItem>;
export type AgentPromptsUpdateRequest = z.infer<typeof agentPromptsUpdateRequest>;
export type AgentPromptHistoryItem = z.infer<typeof agentPromptHistoryItem>;
export type AgentPromptHistoryResponse = z.infer<typeof agentPromptHistoryResponse>;
