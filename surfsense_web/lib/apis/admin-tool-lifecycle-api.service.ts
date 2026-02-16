import {
	type ToolLifecycleUpdateRequest,
	type ToolLifecycleRollbackRequest,
	toolLifecycleListResponse,
	toolLifecycleStatusResponse,
	toolLifecycleUpdateRequest,
	toolLifecycleRollbackRequest,
} from "@/contracts/types/admin-tool-lifecycle.types";
import { ValidationError } from "@/lib/error";
import { baseApiService } from "@/lib/apis/base-api.service";

class AdminToolLifecycleApiService {
	getToolLifecycleList = async () => {
		return baseApiService.get(
			`/api/v1/admin/tool-lifecycle`,
			toolLifecycleListResponse
		);
	};

	updateToolStatus = async (toolId: string, request: ToolLifecycleUpdateRequest) => {
		const parsedRequest = toolLifecycleUpdateRequest.safeParse(request);
		if (!parsedRequest.success) {
			const errorMessage = parsedRequest.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}

		return baseApiService.put(
			`/api/v1/admin/tool-lifecycle/${encodeURIComponent(toolId)}`,
			toolLifecycleStatusResponse,
			{
				body: parsedRequest.data,
			}
		);
	};

	rollbackTool = async (toolId: string, request: ToolLifecycleRollbackRequest) => {
		const parsedRequest = toolLifecycleRollbackRequest.safeParse(request);
		if (!parsedRequest.success) {
			const errorMessage = parsedRequest.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}

		return baseApiService.post(
			`/api/v1/admin/tool-lifecycle/${encodeURIComponent(toolId)}/rollback`,
			toolLifecycleStatusResponse,
			{
				body: parsedRequest.data,
			}
		);
	};

	bulkPromoteToLive = async () => {
		return baseApiService.post(
			`/api/v1/admin/tool-lifecycle/bulk-promote`,
			null, // No response schema validation needed, returns simple message
			{}
		);
	};
}

export const adminToolLifecycleApiService = new AdminToolLifecycleApiService();
