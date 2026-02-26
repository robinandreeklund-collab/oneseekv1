"use client";

import {
	type AppendMessage,
	AssistantRuntimeProvider,
	type ThreadMessageLike,
	useExternalStoreRuntime,
} from "@assistant-ui/react";
import { useQueryClient } from "@tanstack/react-query";
import { useAtomValue, useSetAtom } from "jotai";
import { Activity } from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import {
	clearTargetCommentIdAtom,
	currentThreadAtom,
	setTargetCommentIdAtom,
} from "@/atoms/chat/current-thread.atom";
import {
	type MentionedDocumentInfo,
	mentionedDocumentIdsAtom,
	mentionedDocumentsAtom,
	messageDocumentsMapAtom,
} from "@/atoms/chat/mentioned-documents.atom";
import {
	clearPlanOwnerRegistry,
	// extractWriteTodosFromContent,
	hydratePlanStateAtom,
} from "@/atoms/chat/plan-state.atom";
import { membersAtom } from "@/atoms/members/members-query.atoms";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import { Thread } from "@/components/assistant-ui/thread";
import type { ContextStatsEntry } from "@/components/assistant-ui/context-stats";
import {
	TracePanelContext,
	type TracePanelContextValue,
} from "@/components/assistant-ui/trace-context";
import { TraceSheet } from "@/components/assistant-ui/trace-sheet";
import { ChatHeader } from "@/components/new-chat/chat-header";
import type { TimelineEntry } from "@/components/assistant-ui/thinking-steps";
import type { ThinkingStep } from "@/components/tool-ui/deepagent-thinking";
import { DisplayImageToolUI } from "@/components/tool-ui/display-image";
import { DisplayImageGalleryToolUI } from "@/components/tool-ui/image-gallery";
import { GeoapifyStaticMapToolUI } from "@/components/tool-ui/geoapify-static-map";
import { GeneratePodcastToolUI } from "@/components/tool-ui/generate-podcast";
import { JobAdLinksToolUI } from "@/components/tool-ui/jobad-links";
import { LinkPreviewToolUI } from "@/components/tool-ui/link-preview";
import { LibrisSearchToolUI } from "@/components/tool-ui/libris-search";
import { ScrapeWebpageToolUI } from "@/components/tool-ui/scrape-webpage";
import { SmhiMetfcstToolUI, SmhiWeatherToolUI } from "@/components/tool-ui/smhi-weather";
import { TrafiklabRouteToolUI } from "@/components/tool-ui/trafiklab-route";
import { RecallMemoryToolUI, SaveMemoryToolUI } from "@/components/tool-ui/user-memory";
import {
	ClaudeToolUI,
	DeepSeekToolUI,
	GeminiToolUI,
	GptToolUI,
	GrokToolUI,
	PerplexityToolUI,
	QwenToolUI,
	OneseekToolUI,
} from "@/components/tool-ui/compare-model";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useChatSessionStateSync } from "@/hooks/use-chat-session-state";
import { useMessagesElectric } from "@/hooks/use-messages-electric";
import { useMediaQuery } from "@/hooks/use-media-query";
import type { TraceSpan } from "@/contracts/types/chat-trace.types";
import { chatTraceApiService } from "@/lib/apis/chat-trace-api.service";
import { documentsApiService } from "@/lib/apis/documents-api.service";
import { getBearerToken } from "@/lib/auth-utils";
import { createAttachmentAdapter, extractAttachmentContent } from "@/lib/chat/attachment-adapter";
import { convertToThreadMessage } from "@/lib/chat/message-utils";
import {
	isPodcastGenerating,
	looksLikePodcastRequest,
	setActivePodcastTaskId,
} from "@/lib/chat/podcast-state";
import {
	appendMessage,
	createThread,
	getRegenerateUrl,
	getThreadFull,
	getThreadMessages,
	updateThread,
	type ThreadRecord,
} from "@/lib/chat/thread-persistence";
import { cn } from "@/lib/utils";
import {
	trackChatCreated,
	trackChatError,
	trackChatMessageSent,
	trackChatResponseReceived,
} from "@/lib/posthog/events";

type RuntimeHitlPayload = Record<string, unknown>;

function parseRuntimeHitlPayload(raw: string | undefined): RuntimeHitlPayload | null {
	if (!raw || !raw.trim()) return null;
	try {
		const parsed = JSON.parse(raw);
		if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
			return parsed as RuntimeHitlPayload;
		}
		console.error(
			"[NewChatPage] Ignoring NEXT_PUBLIC_RUNTIME_HITL_JSON: expected a JSON object payload"
		);
		return null;
	} catch (error) {
		console.error("[NewChatPage] Failed to parse NEXT_PUBLIC_RUNTIME_HITL_JSON:", error);
		return null;
	}
}

const PLATFORM_RUNTIME_HITL = parseRuntimeHitlPayload(
	process.env.NEXT_PUBLIC_RUNTIME_HITL_JSON
);

/**
 * Extract thinking steps from message content
 */
function extractThinkingSteps(content: unknown): ThinkingStep[] {
	if (!Array.isArray(content)) return [];

	const thinkingPart = content.find(
		(part: unknown) =>
			typeof part === "object" &&
			part !== null &&
			"type" in part &&
			(part as { type: string }).type === "thinking-steps"
	) as { type: "thinking-steps"; steps: ThinkingStep[] } | undefined;

	return thinkingPart?.steps || [];
}

/**
 * Extract persisted reasoning text from message content.
 * Returns the reasoning string or empty string if not persisted.
 */
function extractReasoningText(content: unknown): string {
	if (!Array.isArray(content)) return "";

	const part = content.find(
		(p: unknown) =>
			typeof p === "object" &&
			p !== null &&
			"type" in p &&
			(p as { type: string }).type === "reasoning-text"
	) as { type: "reasoning-text"; text: string } | undefined;

	return part?.text || "";
}

/**
 * Zod schema for mentioned document info (for type-safe parsing)
 */
const MentionedDocumentInfoSchema = z.object({
	id: z.number(),
	title: z.string(),
	document_type: z.string(),
});

const MentionedDocumentsPartSchema = z.object({
	type: z.literal("mentioned-documents"),
	documents: z.array(MentionedDocumentInfoSchema),
});

/**
 * Extract mentioned documents from message content (type-safe with Zod)
 */
function extractMentionedDocuments(content: unknown): MentionedDocumentInfo[] {
	if (!Array.isArray(content)) return [];

	for (const part of content) {
		const result = MentionedDocumentsPartSchema.safeParse(part);
		if (result.success) {
			return result.data.documents;
		}
	}

	return [];
}

function buildChatTitle(rawQuery: string): string {
	const cleaned = rawQuery.replace(/\s+/g, " ").trim();
	if (!cleaned) return "";

	const withoutCommand = cleaned.replace(/^\/compare\s*:?\s*/i, "").trim();
	const firstLine = (withoutCommand.split("\n")[0] || "").trim();
	const sentence = (firstLine.split(/[.!?]/)[0] || "").trim();
	const candidate = sentence || firstLine || withoutCommand;
	const maxLength = 80;

	if (candidate.length <= maxLength) {
		return candidate;
	}

	return `${candidate.slice(0, maxLength).trimEnd()}...`;
}

const GREETING_REGEX =
	/^(hej|hejsan|hallå|tjena|tja|tjo|hi|hello|hey|yo|hola|bonjour|ciao|guten tag|god morgon|god kväll)\b/i;

function isLowSignalTitle(title: string | null | undefined, lastAutoTitle?: string | null): boolean {
	if (!title) return true;
	const normalized = title.trim().toLowerCase();
	if (!normalized) return true;
	if (normalized === "new chat" || normalized === "ny chatt" || normalized === "chat") return true;
	if (normalized.length <= 4) return true;
	if (GREETING_REGEX.test(normalized)) return true;
	if (lastAutoTitle && title.trim() === lastAutoTitle) return true;
	return false;
}

function isGreetingQuery(query: string): boolean {
	const cleaned = query.replace(/\s+/g, " ").trim();
	if (!cleaned) return false;
	return cleaned.length <= 12 && GREETING_REGEX.test(cleaned);
}

const formatContextNumber = (value?: number) => {
	if (typeof value !== "number" || Number.isNaN(value)) return "0";
	return value.toLocaleString("sv-SE");
};

const buildContextStatsStep = (stats: ContextStatsEntry): ThinkingStepData => {
	const totalTokens = stats.total_tokens ?? 0;
	const totalChars = stats.total_chars ?? 0;
	const baseTokens = stats.base_tokens ?? 0;
	const contextTokens = stats.context_tokens ?? 0;
	const toolTokens = stats.tool_tokens ?? 0;
	const deltaTokens = stats.delta_tokens ?? 0;
	const label = stats.label || stats.phase || "Uppdatering";

	const items: string[] = [];
	if (totalTokens || totalChars) {
		items.push(
			`Totalt: ${formatContextNumber(totalTokens)} tok · ${formatContextNumber(totalChars)} tecken`
		);
	}
	if (baseTokens || contextTokens || toolTokens) {
		items.push(
			`Bas: ${formatContextNumber(baseTokens)} tok · Kontext: ${formatContextNumber(
				contextTokens
			)} tok · Verktyg: ${formatContextNumber(toolTokens)} tok`
		);
	}
	if (deltaTokens > 0) {
		items.push(`Senaste: +${formatContextNumber(deltaTokens)} tok · ${label}`);
	}
	if (!items.length) {
		items.push(label);
	}

	return {
		id: "context-stats",
		title: "Kontextstatus",
		status: "in_progress",
		items,
	};
};

/**
 * Tools that should render custom UI in the chat.
 */
const TOOLS_WITH_UI = new Set([
	"generate_podcast",
	"link_preview",
	"display_image",
	"display_image_gallery",
	"geoapify_static_map",
	"scrape_webpage",
	"smhi_vaderprognoser_metfcst",
	"trafiklab_route",
	"libris_search",
	"jobad_links_search",
	"call_grok",
	"call_claude",
	"call_gpt",
	"call_gemini",
	"call_deepseek",
	"call_perplexity",
	"call_qwen",
	"call_oneseek",
	"sandbox_execute",
	"sandbox_ls",
	"sandbox_read_file",
	"sandbox_write_file",
	"sandbox_replace",
	"sandbox_release",
]);

/**
 * Type for thinking step data from the backend
 */
interface ThinkingStepData {
	id: string;
	title: string;
	status: "pending" | "in_progress" | "completed";
	items: string[];
}

type ContextStatsData = ContextStatsEntry;

export default function NewChatPage() {
	const params = useParams();
	const queryClient = useQueryClient();
	const [isInitializing, setIsInitializing] = useState(true);
	const [threadId, setThreadId] = useState<number | null>(null);
	const [currentThread, setCurrentThread] = useState<ThreadRecord | null>(null);
	const lastAutoTitleRef = useRef<string | null>(null);
	const [messages, setMessages] = useState<ThreadMessageLike[]>([]);
	const [isRunning, setIsRunning] = useState(false);
	// Store thinking steps per message ID - kept separate from content to avoid
	// "unsupported part type" errors from assistant-ui
	const [messageThinkingSteps, setMessageThinkingSteps] = useState<Map<string, ThinkingStep[]>>(
		new Map()
	);
	const [messageContextStats, setMessageContextStats] = useState<
		Map<string, ContextStatsEntry[]>
	>(new Map());
	const [messageReasoningMap, setMessageReasoningMap] = useState<Map<string, string>>(new Map());
	const [messageTimeline, setMessageTimeline] = useState<Map<string, TimelineEntry[]>>(new Map());
	const [messageTraceSessions, setMessageTraceSessions] = useState<Map<string, string>>(
		new Map()
	);
	const [traceSpansBySession, setTraceSpansBySession] = useState<Map<string, TraceSpan[]>>(
		new Map()
	);
	const [isTraceOpen, setIsTraceOpen] = useState(false);
	const [activeTraceMessageId, setActiveTraceMessageId] = useState<string | null>(null);
	const isLargeScreen = useMediaQuery("(min-width: 1024px)");
	const traceLayoutRef = useRef<HTMLDivElement | null>(null);
	const [traceMaxWidth, setTraceMaxWidth] = useState<number>(720);
	const abortControllerRef = useRef<AbortController | null>(null);

	// Get mentioned document IDs from the composer
	const mentionedDocumentIds = useAtomValue(mentionedDocumentIdsAtom);
	const mentionedDocuments = useAtomValue(mentionedDocumentsAtom);
	const setMentionedDocumentIds = useSetAtom(mentionedDocumentIdsAtom);
	const setMentionedDocuments = useSetAtom(mentionedDocumentsAtom);
	const setMessageDocumentsMap = useSetAtom(messageDocumentsMapAtom);
	const hydratePlanState = useSetAtom(hydratePlanStateAtom);
	const setCurrentThreadState = useSetAtom(currentThreadAtom);
	const setTargetCommentId = useSetAtom(setTargetCommentIdAtom);
	const clearTargetCommentId = useSetAtom(clearTargetCommentIdAtom);

	// Get current user for author info in shared chats
	const { data: currentUser } = useAtomValue(currentUserAtom);

	// Live collaboration: sync session state and messages via Electric SQL
	useChatSessionStateSync(threadId);
	const { data: membersData } = useAtomValue(membersAtom);

	const lastAssistantMessageId = useMemo(() => {
		for (let i = messages.length - 1; i >= 0; i -= 1) {
			const msg = messages[i];
			if (msg?.role === "assistant") return msg.id;
		}
		return null;
	}, [messages]);

	const openTraceForMessage = useCallback((messageId: string | null) => {
		if (!messageId) return;
		setActiveTraceMessageId(messageId);
		setIsTraceOpen(true);
	}, []);

	const activeTraceSessionId = useMemo(() => {
		if (!activeTraceMessageId) return null;
		return messageTraceSessions.get(activeTraceMessageId) ?? null;
	}, [activeTraceMessageId, messageTraceSessions]);

	const activeTraceSpans = useMemo(() => {
		if (!activeTraceSessionId) return [];
		return traceSpansBySession.get(activeTraceSessionId) ?? [];
	}, [activeTraceSessionId, traceSpansBySession]);

	const loadTraceForMessage = useCallback(
		async (messageId: string | null) => {
			if (!messageId || !threadId) return;
			if (messageTraceSessions.has(messageId)) return;
			const match = messageId.match(/^msg-(\d+)$/);
			if (!match) return;
			const messageNumericId = Number.parseInt(match[1], 10);
			if (!Number.isFinite(messageNumericId)) return;
			try {
				const trace = await chatTraceApiService.getTraceByMessage(
					threadId,
					messageNumericId
				);
				setMessageTraceSessions((prev) => {
					const next = new Map(prev);
					next.set(messageId, trace.session_id);
					return next;
				});
				setTraceSpansBySession((prev) => {
					const next = new Map(prev);
					next.set(trace.session_id, trace.spans);
					return next;
				});
			} catch (error) {
				console.warn("[trace] Failed to load trace", error);
			}
		},
		[threadId, messageTraceSessions]
	);

	useEffect(() => {
		if (isTraceOpen) {
			void loadTraceForMessage(activeTraceMessageId);
		}
	}, [activeTraceMessageId, isTraceOpen, loadTraceForMessage]);

	const handleElectricMessagesUpdate = useCallback(
		(
			electricMessages: {
				id: number;
				thread_id: number;
				role: string;
				content: unknown;
				author_id: string | null;
				created_at: string;
			}[]
		) => {
			if (isRunning) {
				return;
			}

			setMessages((prev) => {
				if (electricMessages.length < prev.length) {
					return prev;
				}

				return electricMessages.map((msg) => {
					const member = msg.author_id
						? membersData?.find((m) => m.user_id === msg.author_id)
						: null;

					// Preserve existing author info if member lookup fails (e.g., cloned chats)
					const existingMsg = prev.find((m) => m.id === `msg-${msg.id}`);
					const existingAuthor = existingMsg?.metadata?.custom?.author as
						| { displayName?: string | null; avatarUrl?: string | null }
						| undefined;

					return convertToThreadMessage({
						id: msg.id,
						thread_id: msg.thread_id,
						role: msg.role.toLowerCase() as "user" | "assistant" | "system",
						content: msg.content,
						author_id: msg.author_id,
						created_at: msg.created_at,
						author_display_name: member?.user_display_name ?? existingAuthor?.displayName ?? null,
						author_avatar_url: member?.user_avatar_url ?? existingAuthor?.avatarUrl ?? null,
					});
				});
			});
		},
		[isRunning, membersData]
	);

	useMessagesElectric(threadId, handleElectricMessagesUpdate);

	// Create the attachment adapter for file processing
	const rawSearchSpaceId = params.search_space_id;
	const isPublicChat = rawSearchSpaceId === "public";
	const attachmentAdapter = useMemo(
		() => (isPublicChat ? undefined : createAttachmentAdapter()),
		[isPublicChat]
	);

	// Extract search_space_id from URL params
	const searchSpaceId = useMemo(() => {
		if (isPublicChat) {
			return 0;
		}
		const id = params.search_space_id;
		const parsed = typeof id === "string" ? Number.parseInt(id, 10) : 0;
		return Number.isNaN(parsed) ? 0 : parsed;
	}, [params.search_space_id, isPublicChat]);

	const searchParams = useSearchParams();

	// Extract chat_id from URL params
	const urlChatId = useMemo(() => {
		const id = params.chat_id;
		let parsed = 0;
		if (Array.isArray(id) && id.length > 0) {
			parsed = Number.parseInt(id[0], 10);
		} else if (typeof id === "string") {
			parsed = Number.parseInt(id, 10);
		} else {
			const queryId = searchParams.get("chat_id");
			if (queryId) {
				parsed = Number.parseInt(queryId, 10);
			}
		}
		return Number.isNaN(parsed) ? 0 : parsed;
	}, [params.chat_id, searchParams]);

	// Initialize thread and load messages
	// For new chats (no urlChatId), we use lazy creation - thread is created on first message
	const initializeThread = useCallback(async () => {
		setIsInitializing(true);

		// Reset all state when switching between chats to prevent stale data
		setMessages([]);
		setThreadId(null);
		setCurrentThread(null);
		setMessageThinkingSteps(new Map());
		setMessageContextStats(new Map());
		setMessageTraceSessions(new Map());
		setTraceSpansBySession(new Map());
		setActiveTraceMessageId(null);
		setIsTraceOpen(false);
		setMentionedDocumentIds({
			surfsense_doc_ids: [],
			document_ids: [],
		});
		setMentionedDocuments([]);
		setMessageDocumentsMap({});
		clearPlanOwnerRegistry(); // Reset plan ownership for new chat

		try {
			if (isPublicChat) {
				setIsInitializing(false);
				return;
			}

			if (urlChatId > 0) {
				// Thread exists - load thread data and messages
				setThreadId(urlChatId);

				// Load thread data (for visibility info) and messages in parallel
				const [threadData, messagesResponse] = await Promise.all([
					getThreadFull(urlChatId),
					getThreadMessages(urlChatId),
				]);

				setCurrentThread(threadData);

				if (messagesResponse.messages && messagesResponse.messages.length > 0) {
					const loadedMessages = messagesResponse.messages.map(convertToThreadMessage);
					setMessages(loadedMessages);

					// Extract and restore thinking steps + reasoning from persisted messages
					const restoredThinkingSteps = new Map<string, ThinkingStep[]>();
					const restoredReasoningMap = new Map<string, string>();
					// Extract and restore mentioned documents from persisted messages
					const restoredDocsMap: Record<string, MentionedDocumentInfo[]> = {};

					for (const msg of messagesResponse.messages) {
						if (msg.role === "assistant") {
							const steps = extractThinkingSteps(msg.content);
							if (steps.length > 0) {
								restoredThinkingSteps.set(`msg-${msg.id}`, steps);
							}
							// P1 Extra: restore persisted reasoning text
							const reasoning = extractReasoningText(msg.content);
							if (reasoning) {
								restoredReasoningMap.set(`msg-${msg.id}`, reasoning);
							}
						}
						if (msg.role === "user") {
							const docs = extractMentionedDocuments(msg.content);
							if (docs.length > 0) {
								restoredDocsMap[`msg-${msg.id}`] = docs;
							}
						}
					}
					if (restoredThinkingSteps.size > 0 || restoredReasoningMap.size > 0) {
						if (restoredThinkingSteps.size > 0) {
							setMessageThinkingSteps(restoredThinkingSteps);
						}
						if (restoredReasoningMap.size > 0) {
							setMessageReasoningMap(restoredReasoningMap);
						}
						// Build timeline from restored thinking steps and reasoning text
						const restoredTimeline = new Map<string, TimelineEntry[]>();
						const allMsgIds = new Set([
							...restoredThinkingSteps.keys(),
							...restoredReasoningMap.keys(),
						]);
						for (const msgId of allMsgIds) {
							const entries: TimelineEntry[] = [];
							const reasoning = restoredReasoningMap.get(msgId);
							const steps = restoredThinkingSteps.get(msgId);
							// Add reasoning as a single block (original interleaving is lost,
							// but the full text is preserved for display)
							if (reasoning) {
								entries.push({ kind: "reasoning" as const, text: reasoning });
							}
							// Add step entries after reasoning
							if (steps) {
								for (const s of steps) {
									entries.push({ kind: "step" as const, stepId: s.id });
								}
							}
							if (entries.length > 0) {
								restoredTimeline.set(msgId, entries);
							}
						}
						setMessageTimeline(restoredTimeline);
					}
					if (Object.keys(restoredDocsMap).length > 0) {
						setMessageDocumentsMap(restoredDocsMap);
					}
				}
			}
			// For new chats (urlChatId === 0), don't create thread yet
			// Thread will be created lazily when user sends first message
			// This improves UX (instant load) and avoids orphan threads
		} catch (error) {
			console.error("[NewChatPage] Failed to initialize thread:", error);
			// Keep threadId as null - don't use Date.now() as it creates an invalid ID
			// that will cause 404 errors on subsequent API calls
			setThreadId(null);
			setCurrentThread(null);
			toast.error("Failed to load chat. Please try again.");
		} finally {
			setIsInitializing(false);
		}
	}, [
		isPublicChat,
		urlChatId,
		setMessageDocumentsMap,
		setMentionedDocumentIds,
		setMentionedDocuments,
		hydratePlanState,
	]);

	// Initialize on mount
	useEffect(() => {
		initializeThread();
	}, [initializeThread]);

	// Prefetch document titles for @ mention picker
	// Runs when user lands on page so data is ready when they type @
	useEffect(() => {
		if (!searchSpaceId) return;

		const prefetchParams = {
			search_space_id: searchSpaceId,
			page: 0,
			page_size: 20,
		};

		queryClient.prefetchQuery({
			queryKey: ["document-titles", prefetchParams],
			queryFn: () => documentsApiService.searchDocumentTitles({ queryParams: prefetchParams }),
			staleTime: 60 * 1000,
		});

		queryClient.prefetchQuery({
			queryKey: ["surfsense-docs-mention", "", false],
			queryFn: () =>
				documentsApiService.getSurfsenseDocs({
					queryParams: { page: 0, page_size: 20 },
				}),
			staleTime: 3 * 60 * 1000,
		});
	}, [searchSpaceId, queryClient]);

	// Handle scroll to comment from URL query params (e.g., from inbox item click)
	const targetCommentIdParam = searchParams.get("commentId");

	// Set target comment ID from URL param - the AssistantMessage and CommentItem
	// components will handle scrolling and highlighting once comments are loaded
	useEffect(() => {
		if (targetCommentIdParam && !isInitializing) {
			const commentId = Number.parseInt(targetCommentIdParam, 10);
			if (!Number.isNaN(commentId)) {
				setTargetCommentId(commentId);
			}
		}

		// Cleanup on unmount or when navigating away
		return () => clearTargetCommentId();
	}, [targetCommentIdParam, isInitializing, setTargetCommentId, clearTargetCommentId]);

	// Sync current thread state to atom
	useEffect(() => {
		setCurrentThreadState((prev) => ({
			...prev,
			id: currentThread?.id ?? null,
			visibility: currentThread?.visibility ?? null,
			hasComments: currentThread?.has_comments ?? false,
			addingCommentToMessageId: null,
		}));
	}, [currentThread, setCurrentThreadState]);

	// Cancel ongoing request
	const cancelRun = useCallback(async () => {
		if (abortControllerRef.current) {
			abortControllerRef.current.abort();
			abortControllerRef.current = null;
		}
		setIsRunning(false);
	}, []);

	// Handle new message from user
	const onNew = useCallback(
		async (message: AppendMessage) => {
			// Abort any previous streaming request to prevent race conditions
			// when user sends a second query while the first is still streaming
			if (abortControllerRef.current) {
				abortControllerRef.current.abort();
				abortControllerRef.current = null;
			}

			// Extract user query text from content parts
			let userQuery = "";
			for (const part of message.content) {
				if (part.type === "text") {
					userQuery += part.text;
				}
			}

			// Extract attachments from message
			// AppendMessage.attachments contains the processed attachment objects (from adapter.send())
			const messageAttachments: Array<Record<string, unknown>> = [];
			if (message.attachments && message.attachments.length > 0) {
				for (const att of message.attachments) {
					messageAttachments.push(att as unknown as Record<string, unknown>);
				}
			}

			if (!userQuery.trim() && messageAttachments.length === 0) return;

			if (isPublicChat) {
				if (!userQuery.trim()) return;

				const userMsgId = `msg-user-${Date.now()}`;
				const assistantMsgId = `msg-assistant-${Date.now()}`;
				const currentThinkingSteps = new Map<string, ThinkingStepData>();
				const currentTimeline: TimelineEntry[] = [];
				const timelineStepIds = new Set<string>();

				const userMessage: ThreadMessageLike = {
					id: userMsgId,
					role: "user",
					content: message.content,
					createdAt: new Date(),
					attachments: [],
				};

				setMessages((prev) => [
					...prev,
					userMessage,
					{
						id: assistantMsgId,
						role: "assistant",
						content: [{ type: "text", text: "" }],
						createdAt: new Date(),
					},
				]);

				setIsRunning(true);

				const backendUrl =
					process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "http://localhost:8000";

				// Build message history for context
				const messageHistory = messages
					.filter((m) => m.role === "user" || m.role === "assistant")
					.map((m) => {
						let text = "";
						for (const part of m.content) {
							if (typeof part === "object" && part.type === "text" && "text" in part) {
								text += part.text;
							}
						}
						return { role: m.role, content: text };
					})
					.filter((m) => m.content.length > 0);

				try {
					const controller = new AbortController();
					abortControllerRef.current = controller;

					const response = await fetch(`${backendUrl}/api/v1/public/global/chat`, {
						method: "POST",
						headers: {
							"Content-Type": "application/json",
						},
						credentials: "include",
						body: JSON.stringify({
							user_query: userQuery.trim(),
							messages: messageHistory,
						}),
						signal: controller.signal,
					});

					if (!response.ok) {
						throw new Error(`Backend error: ${response.status}`);
					}

					if (!response.body) {
						throw new Error("No response body");
					}

					const reader = response.body.getReader();
					const decoder = new TextDecoder();
					let buffer = "";

					while (true) {
						const { done, value } = await reader.read();
						if (done) break;

						buffer += decoder.decode(value, { stream: true });
						const events = buffer.split(/\r?\n\r?\n/);
						buffer = events.pop() || "";

						for (const event of events) {
							const lines = event.split(/\r?\n/);
							for (const line of lines) {
								if (!line.startsWith("data: ")) continue;
								const data = line.slice(6).trim();
								if (!data || data === "[DONE]") continue;

								try {
									const parsed = JSON.parse(data);
									if (parsed.type === "text-delta" && typeof parsed.delta === "string") {
										setMessages((prev) =>
											prev.map((msg) => {
												if (msg.id !== assistantMsgId) return msg;
												let existingText = "";
												if (Array.isArray(msg.content)) {
													for (const part of msg.content) {
														if (part.type === "text" && "text" in part) {
															existingText += part.text;
														}
													}
												}
												return {
													...msg,
													content: [{ type: "text", text: existingText + parsed.delta }],
												};
											})
										);
									}
									if (parsed.type === "data-thinking-step") {
										const stepData = parsed.data as ThinkingStepData;
										if (stepData?.id) {
											currentThinkingSteps.set(stepData.id, stepData);
											setMessageThinkingSteps((prev) => {
												const newMap = new Map(prev);
												newMap.set(assistantMsgId, Array.from(currentThinkingSteps.values()));
												return newMap;
											});
											if (!timelineStepIds.has(stepData.id)) {
												timelineStepIds.add(stepData.id);
												currentTimeline.push({ kind: "step", stepId: stepData.id });
												setMessageTimeline((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, [...currentTimeline]);
													return newMap;
												});
											}
										}
									}
									if (parsed.type === "error") {
										toast.error(parsed.errorText || "Public chat failed.");
									}
								} catch {
									// ignore malformed chunks
								}
							}
						}
					}
				} catch (error) {
					if (!(error instanceof DOMException && error.name === "AbortError")) {
						toast.error("Failed to get response. Please try again.");
					}
				} finally {
					setIsRunning(false);
					abortControllerRef.current = null;
				}

				return;
			}

			// Check if podcast is already generating
			if (isPodcastGenerating() && looksLikePodcastRequest(userQuery)) {
				toast.warning("A podcast is already being generated.");
				return;
			}

			const token = getBearerToken();
			if (!token) {
				toast.error("Not authenticated. Please log in again.");
				return;
			}

			// Lazy thread creation: create thread on first message if it doesn't exist
			let currentThreadId = threadId;
			let isNewThread = false;
			if (!currentThreadId) {
				try {
					const newThread = await createThread(searchSpaceId, "New Chat");
					currentThreadId = newThread.id;
					setThreadId(currentThreadId);
					// Set currentThread so ChatHeader can show share button immediately
					setCurrentThread(newThread);

					// Track chat creation
					trackChatCreated(searchSpaceId, currentThreadId);

					isNewThread = true;
					// Update URL silently using browser API (not router.replace) to avoid
					// interrupting the ongoing fetch/streaming with React navigation
					window.history.replaceState(
						null,
						"",
						`/dashboard/${searchSpaceId}/new-chat?chat_id=${currentThreadId}`
					);
				} catch (error) {
					console.error("[NewChatPage] Failed to create thread:", error);
					toast.error("Failed to start chat. Please try again.");
					return;
				}
			}

			const userMessageCount = messages.filter((msg) => msg.role === "user").length;
			const nextUserMessageCount = userMessageCount + 1;
			const currentTitle = currentThread?.title ?? "";
			const isLowSignal = isLowSignalTitle(currentTitle, lastAutoTitleRef.current);
			const candidateTitle = buildChatTitle(userQuery);
			const shouldAutoRename =
				!isPublicChat &&
				!!candidateTitle &&
				(!isGreetingQuery(userQuery) || isLowSignal) &&
				(isNewThread ||
					isLowSignal ||
					(lastAutoTitleRef.current && currentTitle.trim() === lastAutoTitleRef.current)) &&
				nextUserMessageCount <= 6;

			if (shouldAutoRename) {
				updateThread(currentThreadId, { title: candidateTitle })
					.then((updated) => {
						setCurrentThread(updated);
						lastAutoTitleRef.current = candidateTitle;
						queryClient.invalidateQueries({
							queryKey: ["threads", String(searchSpaceId)],
						});
						queryClient.invalidateQueries({
							queryKey: ["all-threads", String(searchSpaceId)],
						});
						queryClient.invalidateQueries({
							queryKey: ["search-threads", String(searchSpaceId)],
						});
						queryClient.invalidateQueries({
							queryKey: ["threads", "detail", currentThreadId],
						});
					})
					.catch((error) =>
						console.error("[NewChatPage] Failed to auto-rename thread:", error)
					);
			}

			// Add user message to state
			const userMsgId = `msg-user-${Date.now()}`;

			// Include author metadata for shared chats
			const authorMetadata =
				currentThread?.visibility === "SEARCH_SPACE" && currentUser
					? {
							custom: {
								author: {
									displayName: currentUser.display_name ?? null,
									avatarUrl: currentUser.avatar_url ?? null,
								},
							},
						}
					: undefined;

			const userMessage: ThreadMessageLike = {
				id: userMsgId,
				role: "user",
				content: message.content,
				createdAt: new Date(),
				attachments: message.attachments || [],
				metadata: authorMetadata,
			};
			setMessages((prev) => [...prev, userMessage]);

			// Track message sent
			trackChatMessageSent(searchSpaceId, currentThreadId, {
				hasAttachments: messageAttachments.length > 0,
				hasMentionedDocuments:
					mentionedDocumentIds.surfsense_doc_ids.length > 0 ||
					mentionedDocumentIds.document_ids.length > 0,
				messageLength: userQuery.length,
			});

			// Store mentioned documents with this message for display
			if (mentionedDocuments.length > 0) {
				const docsInfo: MentionedDocumentInfo[] = mentionedDocuments.map((doc) => ({
					id: doc.id,
					title: doc.title,
					document_type: doc.document_type,
				}));
				setMessageDocumentsMap((prev) => ({
					...prev,
					[userMsgId]: docsInfo,
				}));
			}

			// Persist user message with mentioned documents and attachments (don't await, fire and forget)
			const persistContent: unknown[] = [...message.content];

			// Add mentioned documents for persistence
			if (mentionedDocuments.length > 0) {
				persistContent.push({
					type: "mentioned-documents",
					documents: mentionedDocuments.map((doc) => ({
						id: doc.id,
						title: doc.title,
						document_type: doc.document_type,
					})),
				});
			}

			// Add attachments for persistence (so they survive page reload)
			if (message.attachments && message.attachments.length > 0) {
				persistContent.push({
					type: "attachments",
					items: message.attachments.map((att) => ({
						id: att.id,
						name: att.name,
						type: att.type,
						contentType: (att as { contentType?: string }).contentType,
						// Include imageDataUrl for images so they can be displayed after reload
						imageDataUrl: (att as { imageDataUrl?: string }).imageDataUrl,
						// Include extractedContent for context (already extracted, no re-processing needed)
						extractedContent: (att as { extractedContent?: string }).extractedContent,
					})),
				});
			}

			appendMessage(currentThreadId, {
				role: "user",
				content: persistContent,
			})
				.then(() => {
					if (isNewThread) {
						queryClient.invalidateQueries({ queryKey: ["threads", String(searchSpaceId)] });
					}
				})
				.catch((err) => console.error("Failed to persist user message:", err));

			// Start streaming response
			setIsRunning(true);
			const controller = new AbortController();
			abortControllerRef.current = controller;

			// Prepare assistant message
			const assistantMsgId = `msg-assistant-${Date.now()}`;
			const currentThinkingSteps = new Map<string, ThinkingStepData>();
			let currentReasoningText = "";
			const currentTimeline: TimelineEntry[] = [];
			const timelineStepIds = new Set<string>();
			let currentTraceSessionId: string | null = null;
			let compareSummary: unknown | null = null;

			// Ordered content parts to preserve inline tool call positions
			// Each part is either a text segment or a tool call
			type ContentPart =
				| { type: "text"; text: string }
				| {
						type: "tool-call";
						toolCallId: string;
						toolName: string;
						args: Record<string, unknown>;
						result?: unknown;
				  };
			const contentParts: ContentPart[] = [];

			// Track the current text segment index (for appending text deltas)
			let currentTextPartIndex = -1;

			// Map to track tool call indices for updating results
			const toolCallIndices = new Map<string, number>();

			// Helper to get or create the current text part for appending text.
			// Strips any <think>…</think> blocks that might slip through the
			// backend filter (e.g. when the server hasn't been restarted yet).
			const appendText = (delta: string) => {
				const cleaned = delta
					.replace(/<think>[\s\S]*?<\/think>/gi, "")
					.replace(/<\/?think>/gi, "");
				if (!cleaned) return;
				if (currentTextPartIndex >= 0 && contentParts[currentTextPartIndex]?.type === "text") {
					// Append to existing text part
					(contentParts[currentTextPartIndex] as { type: "text"; text: string }).text += cleaned;
				} else {
					// Create new text part
					contentParts.push({ type: "text", text: cleaned });
					currentTextPartIndex = contentParts.length - 1;
				}
			};

			// Helper to add a tool call (this "breaks" the current text segment)
			const addToolCall = (toolCallId: string, toolName: string, args: Record<string, unknown>) => {
				if (TOOLS_WITH_UI.has(toolName)) {
					contentParts.push({
						type: "tool-call",
						toolCallId,
						toolName,
						args,
					});
					toolCallIndices.set(toolCallId, contentParts.length - 1);
					// Reset text part index so next text creates a new segment
					currentTextPartIndex = -1;
				}
			};

			// Helper to update a tool call's args or result
			const updateToolCall = (
				toolCallId: string,
				update: { args?: Record<string, unknown>; result?: unknown }
			) => {
				const index = toolCallIndices.get(toolCallId);
				if (index !== undefined && contentParts[index]?.type === "tool-call") {
					const tc = contentParts[index] as ContentPart & { type: "tool-call" };
					if (update.args) tc.args = update.args;
					if (update.result !== undefined) tc.result = update.result;
				}
			};

			// Helper to build content for UI (without thinking-steps to avoid assistant-ui errors)
			const buildContentForUI = (): ThreadMessageLike["content"] => {
				// Filter to only include text parts with content and tool-calls with UI
				const filtered = contentParts.filter((part) => {
					if (part.type === "text") return part.text.length > 0;
					if (part.type === "tool-call") return TOOLS_WITH_UI.has(part.toolName);
					return false;
				});
				return filtered.length > 0
					? (filtered as ThreadMessageLike["content"])
					: [{ type: "text", text: "" }];
			};

			// Helper to build content for persistence (includes thinking-steps and reasoning for restoration)
			const buildContentForPersistence = (): unknown[] => {
				const parts: unknown[] = [];

				// Include thinking steps for persistence
				if (currentThinkingSteps.size > 0) {
					parts.push({
						type: "thinking-steps",
						steps: Array.from(currentThinkingSteps.values()),
					});
				}
				// P1 Extra: persist reasoning text so it survives page refresh
				if (currentReasoningText) {
					parts.push({
						type: "reasoning-text",
						text: currentReasoningText,
					});
				}
				if (compareSummary) {
					parts.push({ type: "compare-summary", summary: compareSummary });
				}

				// Add content parts (filtered)
				for (const part of contentParts) {
					if (part.type === "text" && part.text.length > 0) {
						parts.push(part);
					} else if (part.type === "tool-call" && TOOLS_WITH_UI.has(part.toolName)) {
						parts.push(part);
					}
				}

				return parts.length > 0 ? parts : [{ type: "text", text: "" }];
			};

			// Add placeholder assistant message
			setMessages((prev) => [
				...prev,
				{
					id: assistantMsgId,
					role: "assistant",
					content: [{ type: "text", text: "" }],
					createdAt: new Date(),
				},
			]);

			try {
				const backendUrl = process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "http://localhost:8000";

				// Build message history for context
				const messageHistory = messages
					.filter((m) => m.role === "user" || m.role === "assistant")
					.map((m) => {
						let text = "";
						for (const part of m.content) {
							if (typeof part === "object" && part.type === "text" && "text" in part) {
								text += part.text;
							}
						}
						return { role: m.role, content: text };
					})
					.filter((m) => m.content.length > 0);

				// Extract attachment content to send with the request
				const attachments = extractAttachmentContent(messageAttachments);

				// Get mentioned document IDs for context (separate fields for backend)
				const hasDocumentIds = mentionedDocumentIds.document_ids.length > 0;
				const hasSurfsenseDocIds = mentionedDocumentIds.surfsense_doc_ids.length > 0;

				// Clear mentioned documents after capturing them
				if (hasDocumentIds || hasSurfsenseDocIds) {
					setMentionedDocumentIds({
						surfsense_doc_ids: [],
						document_ids: [],
					});
					setMentionedDocuments([]);
				}

				const response = await fetch(`${backendUrl}/api/v1/new_chat`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						Authorization: `Bearer ${token}`,
					},
					body: JSON.stringify({
						chat_id: currentThreadId,
						user_query: userQuery.trim(),
						search_space_id: searchSpaceId,
						messages: messageHistory,
						attachments: attachments.length > 0 ? attachments : undefined,
						mentioned_document_ids: hasDocumentIds ? mentionedDocumentIds.document_ids : undefined,
						mentioned_surfsense_doc_ids: hasSurfsenseDocIds
							? mentionedDocumentIds.surfsense_doc_ids
							: undefined,
						runtime_hitl: PLATFORM_RUNTIME_HITL ?? undefined,
					}),
					signal: controller.signal,
				});

				if (!response.ok) {
					throw new Error(`Backend error: ${response.status}`);
				}

				if (!response.body) {
					throw new Error("No response body");
				}

				// Parse SSE stream
				const reader = response.body.getReader();
				const decoder = new TextDecoder();
				let buffer = "";

				try {
					while (true) {
						const { done, value } = await reader.read();
						if (done) break;

						buffer += decoder.decode(value, { stream: true });
						const events = buffer.split(/\r?\n\r?\n/);
						buffer = events.pop() || "";

						for (const event of events) {
							const lines = event.split(/\r?\n/);
							for (const line of lines) {
								if (!line.startsWith("data: ")) continue;
								const data = line.slice(6).trim();
								if (!data || data === "[DONE]") continue;

								try {
									const parsed = JSON.parse(data);

									switch (parsed.type) {
										case "text-delta":
											appendText(parsed.delta);
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;

										case "text-clear": {
											// Template-prefilled <think> detected: text streamed so
											// far was actually reasoning.  Discard text parts so the
											// retroactive reasoning-delta takes over.
											for (let i = contentParts.length - 1; i >= 0; i--) {
												if (contentParts[i].type === "text") {
													contentParts.splice(i, 1);
												}
											}
											currentTextPartIndex = -1;
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;
										}

										case "tool-input-start":
											// Add tool call inline - this breaks the current text segment
											addToolCall(parsed.toolCallId, parsed.toolName, {});
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;

										case "tool-input-available": {
											// Update existing tool call's args, or add if not exists
											if (toolCallIndices.has(parsed.toolCallId)) {
												updateToolCall(parsed.toolCallId, { args: parsed.input || {} });
											} else {
												addToolCall(parsed.toolCallId, parsed.toolName, parsed.input || {});
											}
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;
										}

										case "tool-output-available": {
											// Update the tool call with its result
											updateToolCall(parsed.toolCallId, { result: parsed.output });
											// Handle podcast-specific logic
											if (parsed.output?.status === "pending" && parsed.output?.podcast_id) {
												// Check if this is a podcast tool by looking at the content part
												const idx = toolCallIndices.get(parsed.toolCallId);
												if (idx !== undefined) {
													const part = contentParts[idx];
													if (part?.type === "tool-call" && part.toolName === "generate_podcast") {
														setActivePodcastTaskId(String(parsed.output.podcast_id));
													}
												}
											}
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;
										}

										case "data-thinking-step": {
											// Handle thinking step events for chain-of-thought display
											const stepData = parsed.data as ThinkingStepData;
											if (stepData?.id) {
												currentThinkingSteps.set(stepData.id, stepData);
												setMessageThinkingSteps((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, Array.from(currentThinkingSteps.values()));
													return newMap;
												});
												// Push step marker into timeline only on first occurrence
												// (subsequent events for same step are status updates)
												if (!timelineStepIds.has(stepData.id)) {
													timelineStepIds.add(stepData.id);
													currentTimeline.push({ kind: "step", stepId: stepData.id });
													setMessageTimeline((prev) => {
														const newMap = new Map(prev);
														newMap.set(assistantMsgId, [...currentTimeline]);
														return newMap;
													});
												}
											}
											break;
										}
										case "data-context-stats": {
											const stats = parsed.data as ContextStatsData;
											if (stats) {
												const step = buildContextStatsStep(stats);
												currentThinkingSteps.set(step.id, step);
												setMessageThinkingSteps((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, Array.from(currentThinkingSteps.values()));
													return newMap;
												});
												// Push context-stats step into timeline only on first occurrence
												if (!timelineStepIds.has(step.id)) {
													timelineStepIds.add(step.id);
													currentTimeline.push({ kind: "step", stepId: step.id });
													setMessageTimeline((prev) => {
														const newMap = new Map(prev);
														newMap.set(assistantMsgId, [...currentTimeline]);
														return newMap;
													});
												}
											}
											break;
										}
										case "data-trace-session": {
											const traceSessionId = parsed.data?.trace_session_id as
												| string
												| undefined;
											if (traceSessionId) {
												currentTraceSessionId = traceSessionId;
												setMessageTraceSessions((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, traceSessionId);
													return newMap;
												});
											}
											break;
										}
										case "data-trace-span": {
											const traceSessionId = parsed.data?.trace_session_id as
												| string
												| undefined;
											const spanEvent = parsed.data?.event as string | undefined;
											const span = parsed.data?.span as TraceSpan | undefined;
											if (traceSessionId && span) {
												setTraceSpansBySession((prev) => {
													const newMap = new Map(prev);
													const existing = newMap.get(traceSessionId) ?? [];
													const idx = existing.findIndex((s) => s.id === span.id);
													let next = existing;
													if (idx >= 0) {
														next = existing.map((s, i) => (i === idx ? { ...s, ...span } : s));
													} else {
														next = [...existing, span];
													}
													next.sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
													newMap.set(traceSessionId, next);
													return newMap;
												});
												if (
													spanEvent === "start" &&
													(!activeTraceMessageId || activeTraceMessageId === assistantMsgId)
												) {
													if (!activeTraceMessageId) {
														setActiveTraceMessageId(assistantMsgId);
													}
												}
											}
											break;
										}
										case "data-compare-summary": {
											compareSummary = parsed.data ?? null;
											break;
										}


										case "reasoning-delta": {
											if (parsed.delta) {
												currentReasoningText += parsed.delta;
												setMessageReasoningMap((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, currentReasoningText);
													return newMap;
												});
												// Extend last reasoning entry or start new chunk after a step
												const lastTlEntry = currentTimeline[currentTimeline.length - 1];
												if (lastTlEntry && lastTlEntry.kind === "reasoning") {
													lastTlEntry.text += parsed.delta;
												} else {
													currentTimeline.push({ kind: "reasoning", text: parsed.delta });
												}
												setMessageTimeline((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, [...currentTimeline]);
													return newMap;
												});
											}
											break;
										}

										case "error":
											throw new Error(parsed.errorText || "Server error");
	}
								} catch (e) {
									if (e instanceof SyntaxError) continue;
									throw e;
								}
							}
						}
					}
				} finally {
					reader.releaseLock();
				}

				// Persist assistant message (with thinking steps for restoration on refresh)
				const finalContent = buildContentForPersistence();
				if (contentParts.length > 0) {
					try {
						const savedMessage = await appendMessage(currentThreadId, {
							role: "assistant",
							content: finalContent,
						});

						// Update message ID from temporary to database ID so comments work immediately
						const newMsgId = `msg-${savedMessage.id}`;
						setMessages((prev) =>
							prev.map((m) => (m.id === assistantMsgId ? { ...m, id: newMsgId } : m))
						);

						// Also update thinking steps map with new ID
						setMessageThinkingSteps((prev) => {
							const steps = prev.get(assistantMsgId);
							if (steps) {
								const newMap = new Map(prev);
								newMap.delete(assistantMsgId);
								newMap.set(newMsgId, steps);
								return newMap;
							}
							return prev;
						});

						setMessageContextStats((prev) => {
							const stats = prev.get(assistantMsgId);
							if (stats) {
								const newMap = new Map(prev);
								newMap.delete(assistantMsgId);
								newMap.set(newMsgId, stats);
								return newMap;
							}
							return prev;
						});


						setMessageReasoningMap((prev) => {
							const reasoning = prev.get(assistantMsgId);
							if (reasoning) {
								const newMap = new Map(prev);
								newMap.delete(assistantMsgId);
								newMap.set(newMsgId, reasoning);
								return newMap;
							}
							return prev;
						});
						setMessageTimeline((prev) => {
							const tl = prev.get(assistantMsgId);
							if (tl) {
								const newMap = new Map(prev);
								newMap.delete(assistantMsgId);
								newMap.set(newMsgId, tl);
								return newMap;
							}
							return prev;
						});
						setMessageTraceSessions((prev) => {
							const traceSessionId = prev.get(assistantMsgId);
							if (!traceSessionId) return prev;
							const newMap = new Map(prev);
							newMap.delete(assistantMsgId);
							newMap.set(newMsgId, traceSessionId);
							return newMap;
						});

						setActiveTraceMessageId((prev) =>
							prev === assistantMsgId ? newMsgId : prev
						);

						if (currentTraceSessionId) {
							try {
								await chatTraceApiService.attachTraceSession({
									thread_id: threadId!,
									trace_session_id: currentTraceSessionId,
									message_id: savedMessage.id,
								});
							} catch (error) {
								console.warn("[trace] Failed to attach trace session", error);
							}
						}
					} catch (err) {
						console.error("Failed to persist assistant message:", err);
					}


					// Track successful response
					trackChatResponseReceived(searchSpaceId, currentThreadId);
				}
			} catch (error) {
				if (error instanceof Error && error.name === "AbortError") {
					// Request was cancelled by user - persist partial response if any content was received
					const hasContent = contentParts.some(
						(part) =>
							(part.type === "text" && part.text.length > 0) ||
							(part.type === "tool-call" && TOOLS_WITH_UI.has(part.toolName))
					);
					if (hasContent && currentThreadId) {
						const partialContent = buildContentForPersistence();
						try {
							const savedMessage = await appendMessage(currentThreadId, {
								role: "assistant",
								content: partialContent,
							});

							// Update message ID from temporary to database ID
							const newMsgId = `msg-${savedMessage.id}`;
							setMessages((prev) =>
								prev.map((m) => (m.id === assistantMsgId ? { ...m, id: newMsgId } : m))
							);
							setMessageThinkingSteps((prev) => {
								const steps = prev.get(assistantMsgId);
								if (steps) {
									const newMap = new Map(prev);
									newMap.delete(assistantMsgId);
									newMap.set(newMsgId, steps);
									return newMap;
								}
								return prev;
							});
							setMessageContextStats((prev) => {
								const stats = prev.get(assistantMsgId);
								if (stats) {
									const newMap = new Map(prev);
									newMap.delete(assistantMsgId);
									newMap.set(newMsgId, stats);
									return newMap;
								}
								return prev;
							});

							setMessageReasoningMap((prev) => {
								const reasoning = prev.get(assistantMsgId);
								if (reasoning) {
									const newMap = new Map(prev);
									newMap.delete(assistantMsgId);
									newMap.set(newMsgId, reasoning);
									return newMap;
								}
								return prev;
							});
							setMessageTimeline((prev) => {
								const tl = prev.get(assistantMsgId);
								if (tl) {
									const newMap = new Map(prev);
									newMap.delete(assistantMsgId);
									newMap.set(newMsgId, tl);
									return newMap;
								}
								return prev;
							});
							setMessageTraceSessions((prev) => {
								const traceSessionId = prev.get(assistantMsgId);
								if (!traceSessionId) return prev;
								const newMap = new Map(prev);
								newMap.delete(assistantMsgId);
								newMap.set(newMsgId, traceSessionId);
								return newMap;
							});
							setActiveTraceMessageId((prev) =>
								prev === assistantMsgId ? newMsgId : prev
							);
							if (currentTraceSessionId) {
								try {
									await chatTraceApiService.attachTraceSession({
										thread_id: currentThreadId,
										trace_session_id: currentTraceSessionId,
										message_id: savedMessage.id,
									});
								} catch (error) {
									console.warn("[trace] Failed to attach trace session", error);
								}
							}
						} catch (err) {
							console.error("Failed to persist partial assistant message:", err);
						}
					}
					return;
				}
				console.error("[NewChatPage] Chat error:", error);

				// Track chat error
				trackChatError(
					searchSpaceId,
					currentThreadId,
					error instanceof Error ? error.message : "Unknown error"
				);

				toast.error("Failed to get response. Please try again.");
				// Update assistant message with error
				setMessages((prev) =>
					prev.map((m) =>
						m.id === assistantMsgId
							? {
									...m,
									content: [
										{
											type: "text",
											text: "Sorry, there was an error. Please try again.",
										},
									],
								}
							: m
					)
				);
			} finally {
				setIsRunning(false);
				abortControllerRef.current = null;
				// Note: We no longer clear thinking steps - they persist with the message
			}
		},
		[
			threadId,
			searchSpaceId,
			messages,
			activeTraceMessageId,
			mentionedDocumentIds,
			mentionedDocuments,
			setMentionedDocumentIds,
			setMentionedDocuments,
			setMessageDocumentsMap,
			queryClient,
			currentThread,
			currentUser,
		]
	);

	// Convert message (pass through since already in correct format)
	const convertMessage = useCallback(
		(message: ThreadMessageLike): ThreadMessageLike => message,
		[]
	);

	/**
	 * Handle regeneration (edit or reload) by calling the regenerate endpoint
	 * and streaming the response. This rewinds the LangGraph checkpointer state.
	 *
	 * @param newUserQuery - The new user query (for edit). Pass null/undefined for reload.
	 */
	const handleRegenerate = useCallback(
		async (newUserQuery?: string | null) => {
			if (isPublicChat) {
				toast.info("Sign in to edit or regenerate responses.");
				return;
			}
			if (!threadId) {
				toast.error("Cannot regenerate: no active chat thread");
				return;
			}

			// Abort any previous streaming request
			if (abortControllerRef.current) {
				abortControllerRef.current.abort();
				abortControllerRef.current = null;
			}

			const token = getBearerToken();
			if (!token) {
				toast.error("Not authenticated. Please log in again.");
				return;
			}

			// Extract the original user query BEFORE removing messages (for reload mode)
			let userQueryToDisplay = newUserQuery;
			let originalUserMessageContent: ThreadMessageLike["content"] | null = null;
			let originalUserMessageAttachments: ThreadMessageLike["attachments"] | undefined;
			let originalUserMessageMetadata: ThreadMessageLike["metadata"] | undefined;

			if (!newUserQuery) {
				// Reload mode - find and preserve the last user message content
				const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");
				if (lastUserMessage) {
					originalUserMessageContent = lastUserMessage.content;
					originalUserMessageAttachments = lastUserMessage.attachments;
					originalUserMessageMetadata = lastUserMessage.metadata;
					// Extract text for the API request
					for (const part of lastUserMessage.content) {
						if (typeof part === "object" && part.type === "text" && "text" in part) {
							userQueryToDisplay = part.text;
							break;
						}
					}
				}
			}

			// Remove the last two messages (user + assistant) from the UI immediately
			// The backend will also delete them from the database
			setMessages((prev) => {
				if (prev.length >= 2) {
					return prev.slice(0, -2);
				}
				return prev;
			});

			// Clear thinking steps for the removed messages
			setMessageThinkingSteps((prev) => {
				const newMap = new Map(prev);
				// Remove thinking steps for the last two messages
				const lastTwoIds = messages
					.slice(-2)
					.map((m) => m.id)
					.filter((id): id is string => !!id);
				for (const id of lastTwoIds) {
					newMap.delete(id);
				}
				return newMap;
			});
			setMessageContextStats((prev) => {
				const newMap = new Map(prev);
				const lastTwoIds = messages
					.slice(-2)
					.map((m) => m.id)
					.filter((id): id is string => !!id);
				for (const id of lastTwoIds) {
					newMap.delete(id);
				}
				return newMap;
			});
			setMessageTraceSessions((prev) => {
				const newMap = new Map(prev);
				const lastTwoIds = messages
					.slice(-2)
					.map((m) => m.id)
					.filter((id): id is string => !!id);
				for (const id of lastTwoIds) {
					newMap.delete(id);
				}
				return newMap;
			});

			// Start streaming
			setIsRunning(true);
			const controller = new AbortController();
			abortControllerRef.current = controller;

			// Add placeholder user message if we have a new query (edit mode)
			const userMsgId = `msg-user-${Date.now()}`;
			const assistantMsgId = `msg-assistant-${Date.now()}`;
			const currentThinkingSteps = new Map<string, ThinkingStepData>();
			let currentReasoningText = "";
			const currentTimeline: TimelineEntry[] = [];
			const timelineStepIds = new Set<string>();
			let currentTraceSessionId: string | null = null;
			let compareSummary: unknown | null = null;

			// Content parts tracking (same as onNew)
			type ContentPart =
				| { type: "text"; text: string }
				| {
						type: "tool-call";
						toolCallId: string;
						toolName: string;
						args: Record<string, unknown>;
						result?: unknown;
				  };
			const contentParts: ContentPart[] = [];
			let currentTextPartIndex = -1;
			const toolCallIndices = new Map<string, number>();

			const appendText = (delta: string) => {
				const cleaned = delta
					.replace(/<think>[\s\S]*?<\/think>/gi, "")
					.replace(/<\/?think>/gi, "");
				if (!cleaned) return;
				if (currentTextPartIndex >= 0 && contentParts[currentTextPartIndex]?.type === "text") {
					(contentParts[currentTextPartIndex] as { type: "text"; text: string }).text += cleaned;
				} else {
					contentParts.push({ type: "text", text: cleaned });
					currentTextPartIndex = contentParts.length - 1;
				}
			};

			const addToolCall = (toolCallId: string, toolName: string, args: Record<string, unknown>) => {
				if (TOOLS_WITH_UI.has(toolName)) {
					contentParts.push({ type: "tool-call", toolCallId, toolName, args });
					toolCallIndices.set(toolCallId, contentParts.length - 1);
					currentTextPartIndex = -1;
				}
			};

			const updateToolCall = (
				toolCallId: string,
				update: { args?: Record<string, unknown>; result?: unknown }
			) => {
				const index = toolCallIndices.get(toolCallId);
				if (index !== undefined && contentParts[index]?.type === "tool-call") {
					const tc = contentParts[index] as ContentPart & { type: "tool-call" };
					if (update.args) tc.args = update.args;
					if (update.result !== undefined) tc.result = update.result;
				}
			};

			const buildContentForUI = (): ThreadMessageLike["content"] => {
				const filtered = contentParts.filter((part) => {
					if (part.type === "text") return part.text.length > 0;
					if (part.type === "tool-call") return TOOLS_WITH_UI.has(part.toolName);
					return false;
				});
				return filtered.length > 0
					? (filtered as ThreadMessageLike["content"])
					: [{ type: "text", text: "" }];
			};

			const buildContentForPersistence = (): unknown[] => {
				const parts: unknown[] = [];
				if (currentThinkingSteps.size > 0) {
					parts.push({
						type: "thinking-steps",
						steps: Array.from(currentThinkingSteps.values()),
					});
				}
				// P1 Extra: persist reasoning text so it survives page refresh
				if (currentReasoningText) {
					parts.push({
						type: "reasoning-text",
						text: currentReasoningText,
					});
				}
				if (compareSummary) {
					parts.push({ type: "compare-summary", summary: compareSummary });
				}
				for (const part of contentParts) {
					if (part.type === "text" && part.text.length > 0) {
						parts.push(part);
					} else if (part.type === "tool-call" && TOOLS_WITH_UI.has(part.toolName)) {
						parts.push(part);
					}
				}
				return parts.length > 0 ? parts : [{ type: "text", text: "" }];
			};

			// Add placeholder messages to UI
			// Always add back the user message (with new query for edit, or original content for reload)
			const userMessage: ThreadMessageLike = {
				id: userMsgId,
				role: "user",
				content: newUserQuery
					? [{ type: "text", text: newUserQuery }]
					: originalUserMessageContent || [{ type: "text", text: userQueryToDisplay || "" }],
				createdAt: new Date(),
				attachments: newUserQuery ? undefined : originalUserMessageAttachments,
				metadata: newUserQuery ? undefined : originalUserMessageMetadata,
			};
			setMessages((prev) => [...prev, userMessage]);

			// Add placeholder assistant message
			setMessages((prev) => [
				...prev,
				{
					id: assistantMsgId,
					role: "assistant",
					content: [{ type: "text", text: "" }],
					createdAt: new Date(),
				},
			]);

			try {
				const response = await fetch(getRegenerateUrl(threadId), {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						Authorization: `Bearer ${token}`,
					},
					body: JSON.stringify({
						search_space_id: searchSpaceId,
						user_query: newUserQuery || null,
						runtime_hitl: PLATFORM_RUNTIME_HITL ?? undefined,
					}),
					signal: controller.signal,
				});

				if (!response.ok) {
					throw new Error(`Backend error: ${response.status}`);
				}

				if (!response.body) {
					throw new Error("No response body");
				}

				// Parse SSE stream (same logic as onNew)
				const reader = response.body.getReader();
				const decoder = new TextDecoder();
				let buffer = "";

				try {
					while (true) {
						const { done, value } = await reader.read();
						if (done) break;

						buffer += decoder.decode(value, { stream: true });
						const events = buffer.split(/\r?\n\r?\n/);
						buffer = events.pop() || "";

						for (const event of events) {
							const lines = event.split(/\r?\n/);
							for (const line of lines) {
								if (!line.startsWith("data: ")) continue;
								const data = line.slice(6).trim();
								if (!data || data === "[DONE]") continue;

								try {
									const parsed = JSON.parse(data);

									switch (parsed.type) {
										case "text-delta":
											appendText(parsed.delta);
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;

										case "text-clear": {
											for (let i = contentParts.length - 1; i >= 0; i--) {
												if (contentParts[i].type === "text") {
													contentParts.splice(i, 1);
												}
											}
											currentTextPartIndex = -1;
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;
										}

										case "tool-input-start":
											addToolCall(parsed.toolCallId, parsed.toolName, {});
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;

										case "tool-input-available":
											if (toolCallIndices.has(parsed.toolCallId)) {
												updateToolCall(parsed.toolCallId, { args: parsed.input || {} });
											} else {
												addToolCall(parsed.toolCallId, parsed.toolName, parsed.input || {});
											}
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;

										case "tool-output-available":
											updateToolCall(parsed.toolCallId, { result: parsed.output });
											if (parsed.output?.status === "pending" && parsed.output?.podcast_id) {
												const idx = toolCallIndices.get(parsed.toolCallId);
												if (idx !== undefined) {
													const part = contentParts[idx];
													if (part?.type === "tool-call" && part.toolName === "generate_podcast") {
														setActivePodcastTaskId(String(parsed.output.podcast_id));
													}
												}
											}
											setMessages((prev) =>
												prev.map((m) =>
													m.id === assistantMsgId ? { ...m, content: buildContentForUI() } : m
												)
											);
											break;

										case "data-thinking-step": {
											const stepData = parsed.data as ThinkingStepData;
											if (stepData?.id) {
												currentThinkingSteps.set(stepData.id, stepData);
												setMessageThinkingSteps((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, Array.from(currentThinkingSteps.values()));
													return newMap;
												});
												// Push step marker into timeline only on first occurrence
												// (subsequent events for same step are status updates)
												if (!timelineStepIds.has(stepData.id)) {
													timelineStepIds.add(stepData.id);
													currentTimeline.push({ kind: "step", stepId: stepData.id });
													setMessageTimeline((prev) => {
														const newMap = new Map(prev);
														newMap.set(assistantMsgId, [...currentTimeline]);
														return newMap;
													});
												}
											}
											break;
										}
										case "data-context-stats": {
											const stats = parsed.data as ContextStatsData;
											if (stats) {
												const step = buildContextStatsStep(stats);
												currentThinkingSteps.set(step.id, step);
												setMessageThinkingSteps((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, Array.from(currentThinkingSteps.values()));
													return newMap;
												});
												// Push context-stats step into timeline only on first occurrence
												if (!timelineStepIds.has(step.id)) {
													timelineStepIds.add(step.id);
													currentTimeline.push({ kind: "step", stepId: step.id });
													setMessageTimeline((prev) => {
														const newMap = new Map(prev);
														newMap.set(assistantMsgId, [...currentTimeline]);
														return newMap;
													});
												}
											}
											break;
										}
										case "data-trace-session": {
											const traceSessionId = parsed.data?.trace_session_id as
												| string
												| undefined;
											if (traceSessionId) {
												currentTraceSessionId = traceSessionId;
												setMessageTraceSessions((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, traceSessionId);
													return newMap;
												});
											}
											break;
										}
										case "data-trace-span": {
											const traceSessionId = parsed.data?.trace_session_id as
												| string
												| undefined;
											const spanEvent = parsed.data?.event as string | undefined;
											const span = parsed.data?.span as TraceSpan | undefined;
											if (traceSessionId && span) {
												setTraceSpansBySession((prev) => {
													const newMap = new Map(prev);
													const existing = newMap.get(traceSessionId) ?? [];
													const idx = existing.findIndex((s) => s.id === span.id);
													let next = existing;
													if (idx >= 0) {
														next = existing.map((s, i) => (i === idx ? { ...s, ...span } : s));
													} else {
														next = [...existing, span];
													}
													next.sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
													newMap.set(traceSessionId, next);
													return newMap;
												});
												if (
													spanEvent === "start" &&
													(!activeTraceMessageId || activeTraceMessageId === assistantMsgId)
												) {
													if (!activeTraceMessageId) {
														setActiveTraceMessageId(assistantMsgId);
													}
												}
											}
											break;
										}
										case "data-compare-summary": {
											compareSummary = parsed.data ?? null;
											break;
										}


										case "reasoning-delta": {
											if (parsed.delta) {
												currentReasoningText += parsed.delta;
												setMessageReasoningMap((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, currentReasoningText);
													return newMap;
												});
												// Extend last reasoning entry or start new chunk after a step
												const lastTlEntry = currentTimeline[currentTimeline.length - 1];
												if (lastTlEntry && lastTlEntry.kind === "reasoning") {
													lastTlEntry.text += parsed.delta;
												} else {
													currentTimeline.push({ kind: "reasoning", text: parsed.delta });
												}
												setMessageTimeline((prev) => {
													const newMap = new Map(prev);
													newMap.set(assistantMsgId, [...currentTimeline]);
													return newMap;
												});
											}
											break;
										}

										case "error":
											throw new Error(parsed.errorText || "Server error");
	}
								} catch (e) {
									if (e instanceof SyntaxError) continue;
									throw e;
								}
							}
						}
					}
				} finally {
					reader.releaseLock();
				}

				// Persist messages after streaming completes
				const finalContent = buildContentForPersistence();
				if (contentParts.length > 0) {
					try {
						// Persist user message (for both edit and reload modes, since backend deleted it)
						const userContentToPersist = newUserQuery
							? [{ type: "text", text: newUserQuery }]
							: originalUserMessageContent || [{ type: "text", text: userQueryToDisplay || "" }];

						const savedUserMessage = await appendMessage(threadId, {
							role: "user",
							content: userContentToPersist,
						});

						// Update user message ID to database ID
						const newUserMsgId = `msg-${savedUserMessage.id}`;
						setMessages((prev) =>
							prev.map((m) => (m.id === userMsgId ? { ...m, id: newUserMsgId } : m))
						);

						// Persist assistant message
						const savedMessage = await appendMessage(threadId, {
							role: "assistant",
							content: finalContent,
						});

						// Update assistant message ID to database ID
						const newMsgId = `msg-${savedMessage.id}`;
						setMessages((prev) =>
							prev.map((m) => (m.id === assistantMsgId ? { ...m, id: newMsgId } : m))
						);

						setMessageThinkingSteps((prev) => {
							const steps = prev.get(assistantMsgId);
							if (steps) {
								const newMap = new Map(prev);
								newMap.delete(assistantMsgId);
								newMap.set(newMsgId, steps);
								return newMap;
							}
							return prev;
						});

					setMessageReasoningMap((prev) => {
						const reasoning = prev.get(assistantMsgId);
						if (reasoning) {
							const newMap = new Map(prev);
							newMap.delete(assistantMsgId);
							newMap.set(newMsgId, reasoning);
							return newMap;
						}
						return prev;
					});
					setMessageTimeline((prev) => {
						const tl = prev.get(assistantMsgId);
						if (tl) {
							const newMap = new Map(prev);
							newMap.delete(assistantMsgId);
							newMap.set(newMsgId, tl);
							return newMap;
						}
						return prev;
					});

					// Track successful response
						trackChatResponseReceived(searchSpaceId, threadId);
					} catch (err) {
						console.error("Failed to persist regenerated message:", err);
					}
				}
			} catch (error) {
				if (error instanceof Error && error.name === "AbortError") {
					return;
				}
				console.error("[NewChatPage] Regeneration error:", error);
				trackChatError(
					searchSpaceId,
					threadId,
					error instanceof Error ? error.message : "Unknown error"
				);
				toast.error("Failed to regenerate response. Please try again.");
				// Update assistant message with error
				setMessages((prev) =>
					prev.map((m) =>
						m.id === assistantMsgId
							? {
									...m,
									content: [{ type: "text", text: "Sorry, there was an error. Please try again." }],
								}
							: m
					)
				);
			} finally {
				setIsRunning(false);
				abortControllerRef.current = null;
			}
		},
		[
			isPublicChat,
			threadId,
			searchSpaceId,
			messages,
			activeTraceMessageId,
			setMessageThinkingSteps,
		]
	);

	// Handle editing a message - truncates history and regenerates with new query
	const onEdit = useCallback(
		async (message: AppendMessage) => {
			// Extract the new user query from the message content
			let newUserQuery = "";
			for (const part of message.content) {
				if (part.type === "text") {
					newUserQuery += part.text;
				}
			}

			if (!newUserQuery.trim()) {
				toast.error("Cannot edit with empty message");
				return;
			}

			// Call regenerate with the new query
			await handleRegenerate(newUserQuery.trim());
		},
		[handleRegenerate]
	);

	// Handle reloading/refreshing the last AI response
	const onReload = useCallback(async () => {
		// parentId is the ID of the message to reload from (the user message)
		// We call regenerate without a query to use the same query
		await handleRegenerate(null);
	}, [handleRegenerate]);

	// Create external store runtime with attachment support
	const runtime = useExternalStoreRuntime({
		messages,
		isRunning,
		onNew,
		onEdit,
		onReload,
		convertMessage,
		onCancel: cancelRun,
		adapters: attachmentAdapter ? { attachments: attachmentAdapter } : undefined,
	});

	const traceContextValue = useMemo<TracePanelContextValue>(
		() => ({
			messageTraceSessions,
			traceSpansBySession,
			activeMessageId: activeTraceMessageId,
			isOpen: isTraceOpen,
			openTraceForMessage: (messageId: string) => openTraceForMessage(messageId),
			setIsOpen: setIsTraceOpen,
		}),
		[
			messageTraceSessions,
			traceSpansBySession,
			activeTraceMessageId,
			isTraceOpen,
			openTraceForMessage,
		]
	);
	const isInlineTrace = isTraceOpen && isLargeScreen;

	useEffect(() => {
		const container = traceLayoutRef.current;
		if (!container) return;
		const chatWidthPx = 44 * 16; // matches --thread-max-width (44rem)
		const minTraceWidth = 420;
		const updateMaxWidth = () => {
			const totalWidth = container.clientWidth;
			const available = Math.max(0, totalWidth - chatWidthPx);
			const nextMax = Math.max(minTraceWidth, available);
			setTraceMaxWidth(nextMax);
		};
		updateMaxWidth();
		const observer = new ResizeObserver(updateMaxWidth);
		observer.observe(container);
		return () => observer.disconnect();
	}, [isInlineTrace]);

	// Show loading state only when loading an existing thread
	if (isInitializing) {
		return (
			<div className="flex h-[calc(100vh-64px)] flex-col bg-background px-4">
				<div className="mx-auto w-full max-w-[44rem] flex flex-1 flex-col gap-6 py-8">
					{/* User message */}
					<div className="flex justify-end">
						<Skeleton className="h-12 w-56 rounded-2xl" />
					</div>

					{/* Assistant message */}
					<div className="flex flex-col gap-2">
						<Skeleton className="h-4 w-full" />
						<Skeleton className="h-4 w-[85%]" />
						<Skeleton className="h-4 w-[70%]" />
					</div>

					{/* User message */}
					<div className="flex justify-end">
						<Skeleton className="h-12 w-40 rounded-2xl" />
					</div>

					{/* Assistant message */}
					<div className="flex flex-col gap-2">
						<Skeleton className="h-4 w-full" />
						<Skeleton className="h-4 w-[90%]" />
						<Skeleton className="h-4 w-[60%]" />
					</div>
				</div>

				{/* Input bar */}
				<div className="sticky bottom-0 pb-6 bg-background">
					<div className="mx-auto w-full max-w-[44rem]">
						<Skeleton className="h-24 w-full rounded-2xl" />
					</div>
				</div>
			</div>
		);
	}

	// Show error state only if we tried to load an existing thread but failed
	// For new chats (urlChatId === 0), threadId being null is expected (lazy creation)
	if (!threadId && urlChatId > 0) {
		return (
			<div className="flex h-[calc(100vh-64px)] flex-col items-center justify-center gap-4">
				<div className="text-destructive">Failed to load chat</div>
				<button
					type="button"
					onClick={() => {
						setIsInitializing(true);
						initializeThread();
					}}
					className="rounded-md bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
				>
					Try Again
				</button>
			</div>
		);
	}
	return (
		<AssistantRuntimeProvider runtime={runtime}>
			{!isPublicChat && <GeneratePodcastToolUI />}
			<LinkPreviewToolUI />
			<DisplayImageToolUI />
			<DisplayImageGalleryToolUI />
			<GeoapifyStaticMapToolUI />
			<ScrapeWebpageToolUI />
			<SmhiWeatherToolUI />
			<SmhiMetfcstToolUI />
			<TrafiklabRouteToolUI />
			<LibrisSearchToolUI />
			<JobAdLinksToolUI />
			<GrokToolUI />
			<ClaudeToolUI />
			<GptToolUI />
			<GeminiToolUI />
			<DeepSeekToolUI />
			<PerplexityToolUI />
			<QwenToolUI />
			<OneseekToolUI />
			{!isPublicChat && <SaveMemoryToolUI />}
			{!isPublicChat && <RecallMemoryToolUI />}
			<TracePanelContext.Provider value={traceContextValue}>
				<div
					ref={traceLayoutRef}
					className="flex h-[calc(100vh-64px)] overflow-hidden"
				>
					<div className="flex min-w-0 flex-1 flex-col">
						<Thread
							messageThinkingSteps={messageThinkingSteps}
							messageContextStats={messageContextStats}
							messageReasoningMap={messageReasoningMap}
							messageTimeline={messageTimeline}
							isPublicChat={isPublicChat}
							header={
								<div className="flex items-center justify-between gap-2">
									<ChatHeader searchSpaceId={searchSpaceId} isPublicChat={isPublicChat} />
									{!isPublicChat && (
										<Button
											variant="outline"
											size="sm"
											className="gap-2"
											disabled={!lastAssistantMessageId}
											onClick={() => openTraceForMessage(lastAssistantMessageId ?? null)}
										>
											<Activity
												className={cn("size-4", isTraceOpen ? "animate-pulse" : "")}
											/>
											Live-spårning
										</Button>
									)}
								</div>
							}
						/>
					</div>
					{isInlineTrace && (
						<TraceSheet
							open={isTraceOpen}
							onOpenChange={setIsTraceOpen}
							messageId={activeTraceMessageId}
							sessionId={activeTraceSessionId}
							spans={activeTraceSpans}
							variant="inline"
							dock="right"
							maxWidth={traceMaxWidth}
						/>
					)}
				</div>
				{!isInlineTrace && (
					<TraceSheet
						open={isTraceOpen}
						onOpenChange={setIsTraceOpen}
						messageId={activeTraceMessageId}
						sessionId={activeTraceSessionId}
						spans={activeTraceSpans}
						variant="overlay"
						dock="right"
					/>
				)}
			</TracePanelContext.Provider>
		</AssistantRuntimeProvider>
	);
}
