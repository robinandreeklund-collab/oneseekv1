export interface ToolMetadataItem {
	tool_id: string;
	name: string;
	description: string;
	keywords: string[];
	example_queries: string[];
	category: string;
	base_path?: string | null;
}

export interface ToolCategoryResponse {
	category_id: string;
	category_name: string;
	tools: ToolMetadataItem[];
}

export interface ToolSettingsResponse {
	categories: ToolCategoryResponse[];
}
