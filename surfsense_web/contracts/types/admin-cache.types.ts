import { z } from "zod";

export const adminCacheStateResponse = z.object({
	disabled: z.boolean(),
});

export const adminCacheToggleRequest = z.object({
	disabled: z.boolean(),
});

export const adminCacheClearResponse = z.object({
	cleared: z.record(z.string(), z.any()),
});

export type AdminCacheStateResponse = z.infer<typeof adminCacheStateResponse>;
export type AdminCacheToggleRequest = z.infer<typeof adminCacheToggleRequest>;
export type AdminCacheClearResponse = z.infer<typeof adminCacheClearResponse>;
