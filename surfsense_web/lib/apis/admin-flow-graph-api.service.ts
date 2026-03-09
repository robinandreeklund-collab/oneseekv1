import { z } from "zod";
import { flowGraphResponse } from "@/contracts/types/admin-flow-graph.types";
import { baseApiService } from "@/lib/apis/base-api.service";

const statusResponse = z.object({ status: z.string() });

export interface FlowToolEntry {
	tool_id: string;
	label: string;
}

class AdminFlowGraphApiService {
	getFlowGraph = async () => {
		return baseApiService.get(`/api/v1/admin/flow-graph`, flowGraphResponse);
	};

	updateAgentRoutes = async (agentId: string, routes: string[]) => {
		return baseApiService.patch(`/api/v1/admin/flow-graph/agent-routes`, statusResponse, {
			body: { agent_id: agentId, routes },
		});
	};

	updateAgentTools = async (agentId: string, flowTools: FlowToolEntry[]) => {
		return baseApiService.patch(`/api/v1/admin/flow-graph/agent-tools`, statusResponse, {
			body: { agent_id: agentId, flow_tools: flowTools },
		});
	};

	upsertIntent = async (intent: {
		intent_id: string;
		label?: string;
		route?: string;
		description?: string;
		keywords?: string[];
		priority?: number;
		enabled?: boolean;
		main_identifier?: string;
		core_activity?: string;
		unique_scope?: string;
		geographic_scope?: string;
		excludes?: string[];
	}) => {
		return baseApiService.put(`/api/v1/admin/flow-graph/intent`, statusResponse, { body: intent });
	};

	deleteIntent = async (intentId: string) => {
		return baseApiService.delete(`/api/v1/admin/flow-graph/intent`, statusResponse, {
			body: { intent_id: intentId },
		});
	};

	upsertAgent = async (agent: {
		agent_id: string;
		label?: string;
		description?: string;
		keywords?: string[];
		prompt_key?: string;
		namespace?: string[];
		routes?: string[];
		flow_tools?: FlowToolEntry[];
		main_identifier?: string;
		core_activity?: string;
		unique_scope?: string;
		geographic_scope?: string;
		excludes?: string[];
	}) => {
		return baseApiService.put(`/api/v1/admin/flow-graph/agent`, statusResponse, { body: agent });
	};

	deleteAgent = async (agentId: string) => {
		return baseApiService.delete(`/api/v1/admin/flow-graph/agent`, statusResponse, {
			body: { agent_id: agentId },
		});
	};

	resetAgentToSeed = async (agentId: string) => {
		return baseApiService.post(
			`/api/v1/admin/flow-graph/agent/reset-to-seed`,
			z.object({
				status: z.string(),
				agent_id: z.string().optional(),
				had_override: z.boolean().optional(),
				seed_default: z.boolean().optional(),
				reset_count: z.number().optional(),
				agents: z.array(z.string()).optional(),
			}),
			{ body: { agent_id: agentId } }
		);
	};
}

export const adminFlowGraphApiService = new AdminFlowGraphApiService();
