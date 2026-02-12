import { toolSettingsResponse } from "@/contracts/types/admin-tool-settings.types";
import { baseApiService } from "@/lib/apis/base-api.service";

class AdminToolSettingsApiService {
	async getToolSettings() {
		return baseApiService.get(
			"/api/v1/admin/tool-settings",
			toolSettingsResponse
		);
	}
}

export const adminToolSettingsApiService = new AdminToolSettingsApiService();
