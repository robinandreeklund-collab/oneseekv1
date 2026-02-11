import {
	type TraceSessionAttachRequest,
	type TraceSessionResponse,
	traceSessionAttachRequestSchema,
	traceSessionResponseSchema,
} from "@/contracts/types/chat-trace.types";
import { ValidationError } from "@/lib/error";
import { baseApiService } from "./base-api.service";

class ChatTraceApiService {
	getTraceByMessage = async (
		threadId: number,
		messageId: number
	): Promise<TraceSessionResponse> => {
		return baseApiService.get(
			`/api/v1/threads/${threadId}/messages/${messageId}/traces`,
			traceSessionResponseSchema
		);
	};

	attachTraceSession = async (request: TraceSessionAttachRequest): Promise<void> => {
		const parsed = traceSessionAttachRequestSchema.safeParse(request);
		if (!parsed.success) {
			const errorMessage = parsed.error.issues.map((issue) => issue.message).join(", ");
			throw new ValidationError(`Invalid request: ${errorMessage}`);
		}

		await baseApiService.post(
			`/api/v1/threads/${parsed.data.thread_id}/trace-sessions/${parsed.data.trace_session_id}/attach`,
			undefined,
			{
				body: {
					message_id: parsed.data.message_id,
				},
			}
		);
	};
}

export const chatTraceApiService = new ChatTraceApiService();
