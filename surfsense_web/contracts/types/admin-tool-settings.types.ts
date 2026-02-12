import { z } from "zod";

export const toolMetadataItem = z.object({
	tool_id: z.string(),
	name: z.string(),
	description: z.string(),
	keywords: z.array(z.string()),
	example_queries: z.array(z.string()),
	category: z.string(),
	base_path: z.string().nullable().optional(),
});

export const toolCategoryResponse = z.object({
	category_id: z.string(),
	category_name: z.string(),
	tools: z.array(toolMetadataItem),
});

export const toolSettingsResponse = z.object({
	categories: z.array(toolCategoryResponse),
});

export type ToolMetadataItem = z.infer<typeof toolMetadataItem>;
export type ToolCategoryResponse = z.infer<typeof toolCategoryResponse>;
export type ToolSettingsResponse = z.infer<typeof toolSettingsResponse>;
