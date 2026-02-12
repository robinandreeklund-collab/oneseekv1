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
	type LiveQueryRequest,
	type LiveQueryResponse,
	singleQueryResponseSchema,
	evalRunResponseSchema,
	invalidateCacheResponseSchema,
	liveQueryResponseSchema,
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

		// Use baseApiService.postFormData for proper backend proxying
		return baseApiService.postFormData(
			"/api/v1/admin/tool-eval/run",
			evalRunResponseSchema,
			{
				body: formData,
			}
		);
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

	/**
	 * Test a single query through the FULL supervisor pipeline with trace.
	 * Returns complete execution trace including model reasoning, agent selection, and tool retrieval.
	 */
	async testSingleQueryLive(
		request: LiveQueryRequest
	): Promise<LiveQueryResponse> {
		return baseApiService.post(
			"/api/v1/admin/tool-eval/single-live",
			liveQueryResponseSchema,
			{
				body: request,
			}
		);
	}
}

export const adminToolEvalApiService = new AdminToolEvalApiService();
