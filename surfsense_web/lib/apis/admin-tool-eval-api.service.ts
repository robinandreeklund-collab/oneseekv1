/**
 * Admin Tool Evaluation API Service
 * 
 * Provides methods to interact with the tool evaluation endpoints.
 */

import { baseApiService } from "@/lib/apis/base-api.service";
import {
	type SingleQueryRequest,
	type SingleQueryResponse,
	type EvalRunResponse,
	type InvalidateCacheResponse,
	singleQueryResponseSchema,
	evalRunResponseSchema,
	invalidateCacheResponseSchema,
} from "@/contracts/types/admin-tool-eval.types";

class AdminToolEvalApiService {
	/**
	 * Test a single query through the tool retrieval pipeline.
	 */
	async testSingleQuery(
		request: SingleQueryRequest
	): Promise<SingleQueryResponse> {
		return baseApiService.post(
			"/api/v1/admin/tool-eval/single",
			singleQueryResponseSchema,
			{
				body: request,
			}
		);
	}

	/**
	 * Upload and run a full evaluation suite.
	 */
	async runEvalSuite(file: File): Promise<EvalRunResponse> {
		const formData = new FormData();
		formData.append("file", file);

		// Use fetch directly for FormData (baseApiService doesn't handle FormData well)
		const response = await fetch("/api/v1/admin/tool-eval/run", {
			method: "POST",
			body: formData,
			credentials: "include",
		});

		if (!response.ok) {
			const error = await response.text();
			throw new Error(error || "Failed to run evaluation suite");
		}

		const data = await response.json();
		return evalRunResponseSchema.parse(data);
	}

	/**
	 * Clear the cached tool index.
	 */
	async invalidateCache(): Promise<InvalidateCacheResponse> {
		return baseApiService.post(
			"/api/v1/admin/tool-eval/invalidate-cache",
			invalidateCacheResponseSchema,
			{}
		);
	}
}

export const adminToolEvalApiService = new AdminToolEvalApiService();
