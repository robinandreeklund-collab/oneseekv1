import {
	type MetadataCatalogAuditRunRequest,
	type MetadataCatalogSeparationRequest,
	type MetadataCatalogSafeRenameSuggestionRequest,
	type MetadataCatalogAuditSuggestionRequest,
	type MetadataCatalogSafeRenameSuggestionResponse,
	type MetadataCatalogUpdateRequest,
	type ToolApplySuggestionsRequest,
	type ToolAutoLoopRequest,
	type ToolApiInputApplyPromptSuggestionsRequest,
	type ToolApiInputEvaluationRequest,
	type ToolEvalLibraryGenerateRequest,
	type ToolEvaluationRequest,
	type ToolRetrievalTuning,
	type ToolSettingsUpdateRequest,
	type ToolSuggestionRequest,
	metadataCatalogAuditRunRequest,
	metadataCatalogAuditRunResponse,
	metadataCatalogSeparationRequest,
	metadataCatalogSeparationResponse,
	metadataCatalogSafeRenameSuggestionRequest,
	metadataCatalogSafeRenameSuggestionResponse,
	metadataCatalogAuditSuggestionRequest,
	metadataCatalogAuditSuggestionResponse,
	metadataCatalogResponse,
	metadataCatalogUpdateRequest,
	toolAutoLoopJobStatusResponse,
	toolAutoLoopRequest,
	toolAutoLoopStartResponse,
	toolApiInputApplyPromptSuggestionsRequest,
	toolApiInputApplyPromptSuggestionsResponse,
	toolApiInputEvaluationJobStatusResponse,
	toolApiInputEvaluationRequest,
	toolApiInputEvaluationResponse,
	toolApiInputEvaluationStartResponse,
	toolApplySuggestionsRequest,
	toolApplySuggestionsResponse,
	toolApiCategoriesResponse,
	toolEvalLibraryFileResponse,
	toolEvalLibraryGenerateRequest,
	toolEvalLibraryGenerateResponse,
	toolEvalLibraryListResponse,
	toolEvaluationRequest,
	toolEvaluationResponse,
	toolEvaluationStageHistoryResponse,
	toolEvaluationJobStatusResponse,
	toolEvaluationStartResponse,
	toolRetrievalTuning,
	toolRetrievalTuningResponse,
	toolSettingsResponse,
	toolSettingsUpdateRequest,
	toolSuggestionRequest,
	toolSuggestionResponse,
} from "@/contracts/types/admin-tool-settings.types";
import { ValidationError } from "@/lib/error";
import { baseApiService } from "@/lib/apis/base-api.service";

class AdminToolSettingsApiService {
	async getToolApiCategories(searchSpaceId?: number) {
		const query =
			typeof searchSpaceId === "number" ? `?search_space_id=${searchSpaceId}` : "";
		return baseApiService.get(
			`/api/v1/admin/tool-settings/api-categories${query}`,
			toolApiCategoriesResponse
		);
	}

	async getToolEvaluationHistory(
		stage: "agent" | "tool" | "api_input",
		searchSpaceId?: number,
		limit = 80
	) {
		const params = new URLSearchParams();
		params.set("stage", stage);
		params.set("limit", String(limit));
		if (typeof searchSpaceId === "number") {
			params.set("search_space_id", String(searchSpaceId));
		}
		return baseApiService.get(
			`/api/v1/admin/tool-settings/eval-history?${params.toString()}`,
			toolEvaluationStageHistoryResponse
		);
	}

	async listEvalLibraryFiles(providerKey?: string, categoryId?: string) {
		const params = new URLSearchParams();
		if (providerKey) params.set("provider_key", providerKey);
		if (categoryId) params.set("category_id", categoryId);
		const query = params.toString() ? `?${params.toString()}` : "";
		return baseApiService.get(
			`/api/v1/admin/tool-settings/eval-library/files${query}`,
			toolEvalLibraryListResponse
		);
	}

	async readEvalLibraryFile(relativePath: string) {
		const query = `?relative_path=${encodeURIComponent(relativePath)}`;
		return baseApiService.get(
			`/api/v1/admin/tool-settings/eval-library/file${query}`,
			toolEvalLibraryFileResponse
		);
	}

	async generateEvalLibraryFile(request: ToolEvalLibraryGenerateRequest) {
		const parsed = toolEvalLibraryGenerateRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/eval-library/generate",
			toolEvalLibraryGenerateResponse,
			{
				body: parsed.data,
			}
		);
	}

	async getToolSettings(searchSpaceId?: number) {
		const query = typeof searchSpaceId === "number" ? `?search_space_id=${searchSpaceId}` : "";
		return baseApiService.get(
			`/api/v1/admin/tool-settings${query}`,
			toolSettingsResponse
		);
	}

	async getMetadataCatalog(searchSpaceId?: number) {
		const query = typeof searchSpaceId === "number" ? `?search_space_id=${searchSpaceId}` : "";
		return baseApiService.get(
			`/api/v1/admin/tool-settings/metadata-catalog${query}`,
			metadataCatalogResponse
		);
	}

	async updateMetadataCatalog(request: MetadataCatalogUpdateRequest, searchSpaceId?: number) {
		const parsed = metadataCatalogUpdateRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		const query = typeof searchSpaceId === "number" ? `?search_space_id=${searchSpaceId}` : "";
		return baseApiService.put(
			`/api/v1/admin/tool-settings/metadata-catalog${query}`,
			metadataCatalogResponse,
			{
				body: parsed.data,
			}
		);
	}

	async suggestMetadataCatalogSafeRename(
		request: MetadataCatalogSafeRenameSuggestionRequest
	): Promise<MetadataCatalogSafeRenameSuggestionResponse> {
		const parsed = metadataCatalogSafeRenameSuggestionRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/metadata-catalog/safe-rename-suggestion",
			metadataCatalogSafeRenameSuggestionResponse,
			{
				body: parsed.data,
			}
		);
	}

	async runMetadataCatalogAudit(request: MetadataCatalogAuditRunRequest) {
		const parsed = metadataCatalogAuditRunRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/metadata-audit/run",
			metadataCatalogAuditRunResponse,
			{
				body: parsed.data,
			}
		);
	}

	async runMetadataCatalogSeparation(request: MetadataCatalogSeparationRequest) {
		const parsed = metadataCatalogSeparationRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/metadata-audit/separate-collisions",
			metadataCatalogSeparationResponse,
			{
				body: parsed.data,
			}
		);
	}

	async generateMetadataCatalogAuditSuggestions(request: MetadataCatalogAuditSuggestionRequest) {
		const parsed = metadataCatalogAuditSuggestionRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/metadata-audit/suggestions",
			metadataCatalogAuditSuggestionResponse,
			{
				body: parsed.data,
			}
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

	async getRetrievalTuning() {
		return baseApiService.get(
			"/api/v1/admin/tool-settings/retrieval-tuning",
			toolRetrievalTuningResponse
		);
	}

	async updateRetrievalTuning(tuning: ToolRetrievalTuning) {
		const parsed = toolRetrievalTuning.safeParse(tuning);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.put(
			"/api/v1/admin/tool-settings/retrieval-tuning",
			toolRetrievalTuningResponse,
			{
				body: parsed.data,
			}
		);
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

	async evaluateToolApiInput(request: ToolApiInputEvaluationRequest) {
		const parsed = toolApiInputEvaluationRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/evaluate-api-input",
			toolApiInputEvaluationResponse,
			{
				body: parsed.data,
			}
		);
	}

	async startToolApiInputEvaluation(request: ToolApiInputEvaluationRequest) {
		const parsed = toolApiInputEvaluationRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/evaluate-api-input/start",
			toolApiInputEvaluationStartResponse,
			{
				body: parsed.data,
			}
		);
	}

	async getToolApiInputEvaluationStatus(jobId: string) {
		return baseApiService.get(
			`/api/v1/admin/tool-settings/evaluate-api-input/${jobId}`,
			toolApiInputEvaluationJobStatusResponse
		);
	}

	async startToolAutoLoop(request: ToolAutoLoopRequest) {
		const parsed = toolAutoLoopRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/evaluate-auto-loop/start",
			toolAutoLoopStartResponse,
			{
				body: parsed.data,
			}
		);
	}

	async getToolAutoLoopStatus(jobId: string) {
		return baseApiService.get(
			`/api/v1/admin/tool-settings/evaluate-auto-loop/${jobId}`,
			toolAutoLoopJobStatusResponse
		);
	}

	async applyApiInputPromptSuggestions(
		request: ToolApiInputApplyPromptSuggestionsRequest
	) {
		const parsed = toolApiInputApplyPromptSuggestionsRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/evaluate-api-input/apply-prompt-suggestions",
			toolApiInputApplyPromptSuggestionsResponse,
			{
				body: parsed.data,
			}
		);
	}

	async startToolEvaluation(request: ToolEvaluationRequest) {
		const parsed = toolEvaluationRequest.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(
			"/api/v1/admin/tool-settings/evaluate/start",
			toolEvaluationStartResponse,
			{
				body: parsed.data,
			}
		);
	}

	async getToolEvaluationStatus(jobId: string) {
		return baseApiService.get(
			`/api/v1/admin/tool-settings/evaluate/${jobId}`,
			toolEvaluationJobStatusResponse
		);
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
