import {
	type AgentPromptsUpdateRequest,
	agentPromptsResponse,
	agentPromptsUpdateRequest,
} from "@/contracts/types/agent-prompts.types";
import { ValidationError } from "@/lib/error";
import { baseApiService } from "@/lib/apis/base-api.service";

class AdminPromptsApiService {
	getAgentPrompts = async (searchSpaceId: number) => {
		return baseApiService.get(
			`/api/v1/admin/search-spaces/${searchSpaceId}/agent-prompts`,
			agentPromptsResponse
		);
	};

	updateAgentPrompts = async (searchSpaceId: number, request: AgentPromptsUpdateRequest) => {
		const parsedRequest = agentPromptsUpdateRequest.safeParse(request);
		if (!parsedRequest.success) {
			const errorMessage = parsedRequest.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}

		return baseApiService.put(
			`/api/v1/admin/search-spaces/${searchSpaceId}/agent-prompts`,
			agentPromptsResponse,
			{
				body: parsedRequest.data,
			}
		);
	};
}

export const adminPromptsApiService = new AdminPromptsApiService();
