import {
	type ToolApplySuggestionsRequest,
	type ToolEvaluationRequest,
	type ToolSettingsUpdateRequest,
	type ToolSuggestionRequest,
	toolApplySuggestionsRequest,
	toolApplySuggestionsResponse,
	toolEvaluationRequest,
	toolEvaluationResponse,
	toolSettingsResponse,
	toolSettingsUpdateRequest,
	toolSuggestionRequest,
	toolSuggestionResponse,
} from "@/contracts/types/admin-tool-settings.types";
import { ValidationError } from "@/lib/error";
import { baseApiService } from "@/lib/apis/base-api.service";

class AdminToolSettingsApiService {
	async getToolSettings(searchSpaceId?: number) {
		const query = typeof searchSpaceId === "number" ? `?search_space_id=${searchSpaceId}` : "";
		return baseApiService.get(
			`/api/v1/admin/tool-settings${query}`,
			toolSettingsResponse
		);
	}

	async updateToolSettings(request: ToolSettingsUpdateRequest, searchSpaceId?: number) {
		const parsed = toolSettingsUpdateRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		const query = typeof searchSpaceId === "number" ? `?search_space_id=${searchSpaceId}` : "";
		return baseApiService.put(`/api/v1/admin/tool-settings${query}`, toolSettingsResponse, {
			body: parsed.data,
		});
	}

	async evaluateToolSettings(request: ToolEvaluationRequest) {
		const parsed = toolEvaluationRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post("/api/v1/admin/tool-settings/evaluate", toolEvaluationResponse, {
			body: parsed.data,
		});
	}

	async generateSuggestions(request: ToolSuggestionRequest) {
		const parsed = toolSuggestionRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post("/api/v1/admin/tool-settings/suggestions", toolSuggestionResponse, {
			body: parsed.data,
		});
	}

	async applySuggestions(request: ToolApplySuggestionsRequest, searchSpaceId?: number) {
		const parsed = toolApplySuggestionsRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		const query = typeof searchSpaceId === "number" ? `?search_space_id=${searchSpaceId}` : "";
		return baseApiService.post(
			`/api/v1/admin/tool-settings/apply-suggestions${query}`,
			toolApplySuggestionsResponse,
			{
				body: parsed.data,
			}
		);
	}
}

export const adminToolSettingsApiService = new AdminToolSettingsApiService();
