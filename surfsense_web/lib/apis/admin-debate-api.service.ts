import { z } from "zod";
import { baseApiService } from "@/lib/apis/base-api.service";

// ── Zod schemas ─────────────────────────────────────────────────────

const debateVoiceSettingsSchema = z.object({
	tts_provider: z.string().optional().default("cartesia"),
	api_key: z.string(),
	cartesia_api_key: z.string().optional().default(""),
	api_base: z.string(),
	model: z.string(),
	speed: z.number(),
	voice_map: z.record(z.string(), z.string()),
	language: z.string().optional().default("sv"),
	language_instructions: z.record(z.string(), z.string()).optional().default({}),
	max_tokens: z.number().optional().default(500),
	max_tokens_map: z.record(z.string(), z.number()).optional().default({}),
});

const debateVoiceSettingsResponseSchema = z.object({
	settings: debateVoiceSettingsSchema,
	stored: z.boolean(),
});

export type DebateVoiceSettings = z.infer<typeof debateVoiceSettingsSchema>;
export type DebateVoiceSettingsResponse = z.infer<typeof debateVoiceSettingsResponseSchema>;

// ── API service ─────────────────────────────────────────────────────

class AdminDebateApiService {
	getVoiceSettings = async (): Promise<DebateVoiceSettingsResponse> => {
		return baseApiService.get(
			"/api/v1/admin/debate/voice-settings",
			debateVoiceSettingsResponseSchema,
		);
	};

	updateVoiceSettings = async (
		settings: DebateVoiceSettings,
	): Promise<DebateVoiceSettingsResponse> => {
		return baseApiService.put(
			"/api/v1/admin/debate/voice-settings",
			debateVoiceSettingsResponseSchema,
			{ body: settings },
		);
	};
}

export const adminDebateApiService = new AdminDebateApiService();
