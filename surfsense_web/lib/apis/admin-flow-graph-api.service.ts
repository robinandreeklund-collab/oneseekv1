import { flowGraphResponse } from "@/contracts/types/admin-flow-graph.types";
import { baseApiService } from "@/lib/apis/base-api.service";
import { z } from "zod";

const statusResponse = z.object({ status: z.string() });

export interface FlowToolEntry {
	tool_id: string;
	label: string;
}

class AdminFlowGraphApiService {
	getFlowGraph = async () => {
		return baseApiService.get(
			`/api/v1/admin/flow-graph`,
			flowGraphResponse
		);
	};

	updateAgentRoutes = async (agentId: string, routes: string[]) => {
		return baseApiService.patch(
			`/api/v1/admin/flow-graph/agent-routes`,
			statusResponse,
			{ body: { agent_id: agentId, routes } }
		);
	};

	updateAgentTools = async (agentId: string, flowTools: FlowToolEntry[]) => {
		return baseApiService.patch(
			`/api/v1/admin/flow-graph/agent-tools`,
			statusResponse,
			{ body: { agent_id: agentId, flow_tools: flowTools } }
		);
	};

	upsertIntent = async (intent: {
		intent_id: string;
		label?: string;
		route?: string;
		graph_route?: string;
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
		return baseApiService.put(
			`/api/v1/admin/flow-graph/intent`,
			statusResponse,
			{ body: intent }
		);
	};

	deleteIntent = async (intentId: string) => {
		return baseApiService.delete(
			`/api/v1/admin/flow-graph/intent`,
			statusResponse,
			{ body: { intent_id: intentId } }
		);
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
		return baseApiService.put(
			`/api/v1/admin/flow-graph/agent`,
			statusResponse,
			{ body: agent }
		);
	};

	deleteAgent = async (agentId: string) => {
		return baseApiService.delete(
			`/api/v1/admin/flow-graph/agent`,
			statusResponse,
			{ body: { agent_id: agentId } }
		);
	};
}

export const adminFlowGraphApiService = new AdminFlowGraphApiService();
