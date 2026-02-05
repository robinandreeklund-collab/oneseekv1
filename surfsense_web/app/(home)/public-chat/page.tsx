"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type PublicMessage = {
	id: string;
	role: "user" | "assistant";
	content: string;
};

const BACKEND_URL = process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "http://localhost:8000";
const MAX_HISTORY_MESSAGES = 10;

export default function PublicChatPage() {
	const [messages, setMessages] = useState<PublicMessage[]>([]);
	const [input, setInput] = useState("");
	const [isStreaming, setIsStreaming] = useState(false);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);
	const abortRef = useRef<AbortController | null>(null);
	const bottomRef = useRef<HTMLDivElement | null>(null);

	const historyPayload = useMemo(
		() =>
			messages
				.filter((message) => message.content.trim().length > 0)
				.slice(-MAX_HISTORY_MESSAGES)
				.map((message) => ({
					role: message.role,
					content: message.content,
				})),
		[messages]
	);

	useEffect(() => {
		bottomRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [messages, isStreaming]);

	useEffect(() => {
		return () => {
			abortRef.current?.abort();
		};
	}, []);

	const handleSubmit = async (event: React.FormEvent) => {
		event.preventDefault();
		if (!input.trim() || isStreaming) {
			return;
		}

		setErrorMessage(null);
		const assistantId = `assistant-${Date.now()}`;
		const userMessage: PublicMessage = {
			id: `user-${Date.now()}`,
			role: "user",
			content: input.trim(),
		};

		setMessages((prev) => [
			...prev,
			userMessage,
			{ id: assistantId, role: "assistant", content: "" },
		]);
		setInput("");
		setIsStreaming(true);

		const controller = new AbortController();
		abortRef.current = controller;

		try {
			const response = await fetch(`${BACKEND_URL}/api/v1/public/global/chat`, {
				method: "POST",
				credentials: "include",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({
					user_query: userMessage.content,
					messages: historyPayload,
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

				for (const eventChunk of events) {
					const lines = eventChunk.split(/\r?\n/);
					for (const line of lines) {
						if (!line.startsWith("data: ")) continue;
						const data = line.slice(6).trim();
						if (!data || data === "[DONE]") continue;

						try {
							const parsed = JSON.parse(data);
							if (parsed.type === "text-delta" && typeof parsed.delta === "string") {
								setMessages((prev) =>
									prev.map((message) =>
										message.id === assistantId
											? { ...message, content: message.content + parsed.delta }
											: message
									)
								);
							}
							if (parsed.type === "error") {
								setErrorMessage(parsed.errorText || "Public chat failed.");
							}
						} catch {
							// Ignore malformed chunks.
						}
					}
				}
			}
		} catch (error) {
			if (!(error instanceof DOMException && error.name === "AbortError")) {
				setErrorMessage(error instanceof Error ? error.message : "Public chat failed.");
			}
		} finally {
			setIsStreaming(false);
			abortRef.current = null;
		}
	};

	return (
		<section className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 pb-16 pt-28">
			<header className="space-y-2 text-center">
				<h1 className="text-3xl font-semibold text-neutral-900 dark:text-white">
					Public Beta Chat
				</h1>
				<p className="text-sm text-neutral-500 dark:text-neutral-300">
					Try the global model without signing in. No personal data or saved chats are
					used.
				</p>
			</header>

			<div className="flex flex-1 flex-col gap-4 rounded-2xl border border-neutral-200 bg-white/80 p-6 shadow-sm backdrop-blur dark:border-neutral-800 dark:bg-neutral-950/80">
				<div className="flex flex-1 flex-col gap-4 overflow-y-auto">
					{messages.length === 0 && (
						<div className="rounded-xl border border-dashed border-neutral-200 bg-neutral-50 p-6 text-sm text-neutral-500 dark:border-neutral-800 dark:bg-neutral-900/40 dark:text-neutral-400">
							Type a question to start the chat.
						</div>
					)}
					{messages.map((message) => (
						<div
							key={message.id}
							className={`flex flex-col gap-2 rounded-xl px-4 py-3 text-sm ${
								message.role === "user"
									? "self-end bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
									: "self-start bg-neutral-100 text-neutral-900 dark:bg-neutral-900 dark:text-neutral-100"
							}`}
						>
							<span className="text-xs uppercase tracking-wide opacity-60">
								{message.role === "user" ? "You" : "SurfSense"}
							</span>
							<p className="whitespace-pre-wrap">
								{message.content || (isStreaming ? "..." : "")}
							</p>
						</div>
					))}
					<div ref={bottomRef} />
				</div>

				{errorMessage && (
					<div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
						{errorMessage}
					</div>
				)}

				<form onSubmit={handleSubmit} className="flex flex-col gap-3">
					<Textarea
						value={input}
						onChange={(event) => setInput(event.target.value)}
						placeholder="Type your question here..."
						className="min-h-[96px] resize-none"
						disabled={isStreaming}
					/>
					<div className="flex items-center justify-between gap-3">
						<Button type="submit" disabled={isStreaming || !input.trim()}>
							{isStreaming ? "Responding..." : "Send"}
						</Button>
						<p className="text-xs text-neutral-400">
							Rate limiting applies for anonymous access.
						</p>
					</div>
				</form>
			</div>
		</section>
	);
}
