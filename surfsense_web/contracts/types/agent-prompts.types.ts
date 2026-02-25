import { z } from "zod";

export const knownAgentPromptKeys = [
	"system.default.instructions",
	"citation.instructions",
	"router.top_level",
	"agent.smalltalk.system",
	"agent.supervisor.system",
	"compare.supervisor.instructions",
	"supervisor.intent_resolver.system",
	"supervisor.agent_resolver.system",
	"supervisor.planner.system",
	"supervisor.tool_resolver.system",
	"supervisor.critic_gate.system",
	"supervisor.synthesizer.system",
	"supervisor.critic.system",
	"supervisor.loop_guard.message",
	"supervisor.tool_limit_guard.message",
	"supervisor.trafik.enforcement.message",
	"supervisor.code.sandbox.enforcement.message",
	"supervisor.code.read_file.enforcement.message",
	"supervisor.scoped_tool_prompt.template",
	"supervisor.tool_default_prompt.template",
	"supervisor.subagent.context.template",
	"supervisor.domain_planner.system",
	"supervisor.response_layer.kunskap",
	"supervisor.response_layer.analys",
	"supervisor.response_layer.syntes",
	"supervisor.response_layer.visualisering",
	"supervisor.hitl.planner.message",
	"supervisor.hitl.execution.message",
	"supervisor.hitl.synthesis.message",
	"agent.worker.knowledge",
	"agent.knowledge.system",
	"agent.worker.action",
	"agent.action.system",
	"agent.media.system",
	"agent.browser.system",
	"agent.code.system",
	"agent.kartor.system",
	"agent.statistics.system",
	"agent.synthesis.system",
	"agent.bolag.system",
	"agent.trafik.system",
	"agent.riksdagen.system",
	"agent.marketplace.system",
	"compare.analysis.system",
	"compare.external.system",
] as const;

/**
 * Keep known keys for editor UX, but allow unknown keys in API payloads/responses
 * so frontend doesn't break when backend adds prompt keys before web is redeployed.
 */
export const knownAgentPromptKeyEnum = z.enum(knownAgentPromptKeys);
export const agentPromptKeyEnum = z.string().min(1);

export const agentPromptItem = z.object({
	key: agentPromptKeyEnum,
	label: z.string(),
	description: z.string(),
	node_group: z.string(),
	node_group_label: z.string(),
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
