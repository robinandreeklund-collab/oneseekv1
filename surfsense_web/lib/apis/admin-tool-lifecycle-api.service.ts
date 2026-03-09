import {
	type ToolLifecycleRollbackRequest,
	type ToolLifecycleUpdateRequest,
	toolLifecycleListResponse,
	toolLifecycleRollbackRequest,
	toolLifecycleStatusResponse,
	toolLifecycleUpdateRequest,
} from "@/contracts/types/admin-tool-lifecycle.types";
import { baseApiService } from "@/lib/apis/base-api.service";
import { ValidationError } from "@/lib/error";

class AdminToolLifecycleApiService {
	getToolLifecycleList = async () => {
		return baseApiService.get(`/api/v1/admin/tool-lifecycle`, toolLifecycleListResponse);
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
			undefined, // No response schema validation needed, returns simple message
			{}
		);
	};
}

export const adminToolLifecycleApiService = new AdminToolLifecycleApiService();
