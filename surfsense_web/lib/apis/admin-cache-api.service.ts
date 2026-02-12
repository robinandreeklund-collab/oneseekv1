import {
	type AdminCacheToggleRequest,
	adminCacheClearResponse,
	adminCacheStateResponse,
	adminCacheToggleRequest,
} from "@/contracts/types/admin-cache.types";
import { ValidationError } from "@/lib/error";
import { baseApiService } from "@/lib/apis/base-api.service";

class AdminCacheApiService {
	getCacheState = async () => {
		return baseApiService.get(`/api/v1/admin/cache`, adminCacheStateResponse);
	};

	updateCacheState = async (request: AdminCacheToggleRequest) => {
		const parsedRequest = adminCacheToggleRequest.safeParse(request);
		if (!parsedRequest.success) {
			const errorMessage = parsedRequest.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}
		return baseApiService.post(`/api/v1/admin/cache/disable`, adminCacheStateResponse, {
			body: parsedRequest.data,
		});
	};

	clearCaches = async () => {
		return baseApiService.post(`/api/v1/admin/cache/clear`, adminCacheClearResponse, {});
	};
}

export const adminCacheApiService = new AdminCacheApiService();
