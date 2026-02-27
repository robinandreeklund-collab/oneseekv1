import type { ThreadMessageLike } from "@assistant-ui/react";
import { z } from "zod";
import type { MessageRecord } from "./thread-persistence";

/**
 * Zod schema for persisted attachment info
 */
const PersistedAttachmentSchema = z.object({
	id: z.string(),
	name: z.string(),
	type: z.string(),
	contentType: z.string().optional(),
	imageDataUrl: z.string().optional(),
	extractedContent: z.string().optional(),
});

const AttachmentsPartSchema = z.object({
	type: z.literal("attachments"),
	items: z.array(PersistedAttachmentSchema),
});

type PersistedAttachment = z.infer<typeof PersistedAttachmentSchema>;

/**
 * Extract persisted attachments from message content (type-safe with Zod)
 */
function extractPersistedAttachments(content: unknown): PersistedAttachment[] {
	if (!Array.isArray(content)) return [];

	for (const part of content) {
		const result = AttachmentsPartSchema.safeParse(part);
		if (result.success) {
			return result.data.items;
		}
	}

	return [];
}

/**
 * Zod schema for persisted reasoning text (P1-Extra.6)
 */
const ReasoningTextPartSchema = z.object({
	type: z.literal("reasoning-text"),
	text: z.string(),
});

/**
 * Zod schema for a single structured field entry
 */
const StructuredFieldEntrySchema = z.object({
	node: z.string(),
	field: z.string(),
	value: z.unknown(),
});

/**
 * Zod schema for persisted structured fields (P1-Extra.6)
 */
const StructuredFieldsPartSchema = z.object({
	type: z.literal("structured-fields"),
	fields: z.record(z.string(), z.array(StructuredFieldEntrySchema)),
});

export type StructuredFieldEntry = z.infer<typeof StructuredFieldEntrySchema>;

/**
 * Extract persisted reasoning text from message content (type-safe with Zod)
 */
export function extractReasoningText(content: unknown): string {
	if (!Array.isArray(content)) return "";

	for (const part of content) {
		const result = ReasoningTextPartSchema.safeParse(part);
		if (result.success) {
			return result.data.text;
		}
	}

	return "";
}

/**
 * Extract persisted structured fields from message content (type-safe with Zod).
 * Returns Map<node, Array<{node, field, value}>> or null if not persisted.
 */
export function extractStructuredFields(
	content: unknown
): Map<string, StructuredFieldEntry[]> | null {
	if (!Array.isArray(content)) return null;

	for (const part of content) {
		const result = StructuredFieldsPartSchema.safeParse(part);
		if (result.success) {
			const map = new Map<string, StructuredFieldEntry[]>();
			for (const [node, entries] of Object.entries(result.data.fields)) {
				map.set(node, entries);
			}
			return map;
		}
	}

	return null;
}

// Strips <think>...</think> blocks (including their content) from text.
// Used to clean up messages that were persisted before the backend streaming
// filter was introduced, or as a safety net for any that slip through.
const THINK_BLOCK_RE = /<think>[\s\S]*?<\/think>/gi;
const THINK_TAG_RE = /<\/?think>/gi;

function stripThinkBlocks(text: string): string {
	return text.replace(THINK_BLOCK_RE, "").replace(THINK_TAG_RE, "").trim();
}

/**
 * Convert backend message to assistant-ui ThreadMessageLike format
 * Filters out 'thinking-steps' part as it's handled separately via messageThinkingSteps
 * Restores attachments for user messages from persisted data
 */
export function convertToThreadMessage(msg: MessageRecord): ThreadMessageLike {
	let content: ThreadMessageLike["content"];

	if (typeof msg.content === "string") {
		content = [{ type: "text", text: stripThinkBlocks(msg.content) }];
	} else if (Array.isArray(msg.content)) {
		// Filter out custom metadata parts - they're handled separately
		const filteredContent = msg.content
			.filter((part: unknown) => {
				if (typeof part !== "object" || part === null || !("type" in part)) return true;
				const partType = (part as { type: string }).type;
				// Filter out thinking-steps, reasoning-text, mentioned-documents, and attachments
				return (
					partType !== "thinking-steps" &&
					partType !== "reasoning-text" &&
					partType !== "mentioned-documents" &&
					partType !== "attachments" &&
					partType !== "compare-summary" &&
					partType !== "structured-fields"
				);
			})
			.map((part: unknown) => {
				// Strip <think> blocks from text parts
				if (
					typeof part === "object" &&
					part !== null &&
					"type" in part &&
					(part as { type: string }).type === "text" &&
					"text" in part &&
					typeof (part as { text: unknown }).text === "string"
				) {
					return { ...(part as object), text: stripThinkBlocks((part as { text: string }).text) };
				}
				return part;
			});
		content =
			filteredContent.length > 0
				? (filteredContent as ThreadMessageLike["content"])
				: [{ type: "text", text: "" }];
	} else {
		content = [{ type: "text", text: stripThinkBlocks(String(msg.content)) }];
	}

	// Restore attachments for user messages
	let attachments: ThreadMessageLike["attachments"];
	if (msg.role === "user") {
		const persistedAttachments = extractPersistedAttachments(msg.content);
		if (persistedAttachments.length > 0) {
			attachments = persistedAttachments.map((att) => ({
				id: att.id,
				name: att.name,
				type: att.type as "document" | "image" | "file",
				contentType: att.contentType || "application/octet-stream",
				status: { type: "complete" as const },
				content: [],
				// Custom fields for our ChatAttachment interface
				imageDataUrl: att.imageDataUrl,
				extractedContent: att.extractedContent,
			}));
		}
	}

	// Build metadata.custom for author display in shared chats
	const metadata = msg.author_id
		? {
				custom: {
					author: {
						displayName: msg.author_display_name ?? null,
						avatarUrl: msg.author_avatar_url ?? null,
					},
				},
			}
		: undefined;

	return {
		id: `msg-${msg.id}`,
		role: msg.role,
		content,
		createdAt: new Date(msg.created_at),
		attachments,
		metadata,
	};
}
