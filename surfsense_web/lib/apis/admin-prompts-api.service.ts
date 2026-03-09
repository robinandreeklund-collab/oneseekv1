import {
	type AgentPromptsUpdateRequest,
	agentPromptHistoryResponse,
	agentPromptsResponse,
	agentPromptsUpdateRequest,
} from "@/contracts/types/agent-prompts.types";
import { baseApiService } from "@/lib/apis/base-api.service";
import { ValidationError } from "@/lib/error";

class AdminPromptsApiService {
	getAgentPrompts = async () => {
		return baseApiService.get(`/api/v1/admin/agent-prompts`, agentPromptsResponse);
	};

	updateAgentPrompts = async (request: AgentPromptsUpdateRequest) => {
		const parsedRequest = agentPromptsUpdateRequest.safeParse(request);
		if (!parsedRequest.success) {
			const errorMessage = parsedRequest.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}

		return baseApiService.put(`/api/v1/admin/agent-prompts`, agentPromptsResponse, {
			body: parsedRequest.data,
		});
	};

	getAgentPromptHistory = async (promptKey: string) => {
		return baseApiService.get(
			`/api/v1/admin/agent-prompts/${promptKey}/history`,
			agentPromptHistoryResponse
		);
	};
}

export const adminPromptsApiService = new AdminPromptsApiService();
