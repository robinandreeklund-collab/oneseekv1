import type { ToolSettingsResponse } from "@/contracts/types/admin-tool-settings.types";

class AdminToolSettingsApiService {
	async getToolSettings(): Promise<ToolSettingsResponse> {
		const response = await fetch("/api/admin/tool-settings", {
			method: "GET",
			headers: {
				"Content-Type": "application/json",
			},
			credentials: "include",
		});

		if (!response.ok) {
			throw new Error(`Failed to fetch tool settings: ${response.statusText}`);
		}

		return response.json();
	}
}

export const adminToolSettingsApiService = new AdminToolSettingsApiService();
