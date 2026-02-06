"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { AlertCircleIcon, BookOpenIcon, ExternalLinkIcon } from "lucide-react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

// ============================================================================
// Zod Schemas
// ============================================================================

const LibrisResultItemSchema = z
	.object({
		id: z.string().nullish(),
		record_id: z.string().nullish(),
		title: z.string().nullish(),
		authors: z.array(z.string()).nullish(),
		year: z.string().nullish(),
		publisher: z.string().nullish(),
		isbn: z.string().nullish(),
		summary: z.string().nullish(),
		subjects: z.array(z.string()).nullish(),
		cover_image: z.string().nullish(),
		availability: z
			.object({
				count: z.number().nullish(),
				libraries: z.array(z.string()).nullish(),
			})
			.nullish(),
		libris_url: z.string().nullish(),
	})
	.partial();

const LibrisSearchArgsSchema = z
	.object({
		query: z.string().nullish(),
		record_id: z.string().nullish(),
		limit: z.number().nullish(),
		offset: z.number().nullish(),
	})
	.partial();

const LibrisSearchResultSchema = z
	.object({
		status: z.string().nullish(),
		error: z.string().nullish(),
		mode: z.string().nullish(),
		query: z.string().nullish(),
		results: z.array(LibrisResultItemSchema).nullish(),
		record: LibrisResultItemSchema.nullish(),
		total_items: z.number().nullish(),
	})
	.partial()
	.passthrough();

type LibrisSearchArgs = z.infer<typeof LibrisSearchArgsSchema>;
type LibrisSearchResult = z.infer<typeof LibrisSearchResultSchema>;

// ============================================================================
// Helpers
// ============================================================================

function truncate(text: string | null | undefined, limit: number): string {
	if (!text) return "";
	return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function LibrisErrorState({ error }: { error: string }) {
	return (
		<div className="my-4 overflow-hidden rounded-xl border border-destructive/20 bg-destructive/5 p-4 w-full">
			<div className="flex items-center gap-4">
				<div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-destructive/10">
					<AlertCircleIcon className="size-6 text-destructive" />
				</div>
				<div className="flex-1 min-w-0">
					<p className="font-medium text-destructive text-sm">Failed to load Libris results</p>
					<p className="text-muted-foreground text-xs mt-1">{error}</p>
				</div>
			</div>
		</div>
	);
}

function LibrisLoading() {
	return (
		<Card className="my-4 w-full animate-pulse">
			<CardContent className="p-4">
				<div className="h-4 w-1/3 rounded bg-muted" />
				<div className="mt-3 h-3 w-3/4 rounded bg-muted" />
				<div className="mt-2 h-3 w-full rounded bg-muted" />
			</CardContent>
		</Card>
	);
}

function LibrisResultCard({ result }: { result: z.infer<typeof LibrisResultItemSchema> }) {
	const authors = result.authors?.slice(0, 3) || [];
	const subjects = result.subjects?.slice(0, 4) || [];
	return (
		<div className="rounded-lg border border-border/60 bg-background p-3">
			<div className="flex gap-3">
				{result.cover_image ? (
					<img
						src={result.cover_image}
						alt={result.title || "Cover"}
						className="h-20 w-14 rounded border border-border/60 object-cover"
						loading="lazy"
					/>
				) : (
					<div className="flex h-20 w-14 items-center justify-center rounded border border-border/60 bg-muted text-muted-foreground">
						<BookOpenIcon className="size-5" />
					</div>
				)}
				<div className="flex-1 min-w-0">
					<div className="flex items-start justify-between gap-2">
						<h4 className="font-semibold text-sm">{result.title || "Untitled"}</h4>
						{result.libris_url && (
							<Button
								variant="ghost"
								size="icon"
								onClick={() => window.open(result.libris_url || "", "_blank", "noopener,noreferrer")}
								aria-label="Open in Libris"
							>
								<ExternalLinkIcon className="size-4" />
							</Button>
						)}
					</div>
					{authors.length > 0 && (
						<p className="text-xs text-muted-foreground">
							{authors.join(", ")}
						</p>
					)}
					<div className="mt-1 text-xs text-muted-foreground">
						{result.year && <span>{result.year}</span>}
						{result.publisher && <span> · {result.publisher}</span>}
						{result.isbn && <span> · ISBN {result.isbn}</span>}
					</div>
					{result.summary && (
						<p className="mt-2 text-xs text-muted-foreground">
							{truncate(result.summary, 160)}
						</p>
					)}
					{subjects.length > 0 && (
						<div className="mt-2 flex flex-wrap gap-1">
							{subjects.map((subject) => (
								<Badge key={subject} variant="secondary" className="text-[10px]">
									{subject}
								</Badge>
							))}
						</div>
					)}
					{result.availability?.count && (
						<p className="mt-2 text-[10px] text-muted-foreground">
							Available at {result.availability.count} libraries
						</p>
					)}
				</div>
			</div>
		</div>
	);
}

// ============================================================================
// Tool UI
// ============================================================================

export const LibrisSearchToolUI = makeAssistantToolUI<LibrisSearchArgs, LibrisSearchResult>({
	toolName: "libris_search",
	render: function LibrisSearchUI({ args, result, status }) {
		if (status.type === "running" || status.type === "requires-action") {
			return <LibrisLoading />;
		}

		if (status.type === "incomplete") {
			if (status.reason === "cancelled") {
				return (
					<div className="my-4 rounded-xl border border-muted p-4 text-muted-foreground w-full">
						<p className="line-through">Libris search cancelled</p>
					</div>
				);
			}
			if (status.reason === "error") {
				return (
					<LibrisErrorState
						error={typeof status.error === "string" ? status.error : "An error occurred"}
					/>
				);
			}
		}

		if (!result) {
			return <LibrisLoading />;
		}

		if (result.error || result.status === "error") {
			return <LibrisErrorState error={result.error || "Libris search failed"} />;
		}

		const results = result.mode === "record" ? (result.record ? [result.record] : []) : result.results || [];
		return (
			<Card className="my-4 w-full">
				<CardContent className="p-4">
					<div className="flex items-center justify-between">
						<div className="text-sm text-muted-foreground">
							Libris XL {result.mode === "record" ? "record" : "search"}
						</div>
						{typeof result.total_items === "number" && (
							<Badge variant="secondary">{result.total_items} results</Badge>
						)}
					</div>
					{args.query && (
						<p className="mt-1 text-xs text-muted-foreground">
							Query: <span className="font-medium text-foreground">{args.query}</span>
						</p>
					)}
					<div className="mt-3 space-y-3">
						{results.length === 0 ? (
							<p className="text-sm text-muted-foreground">No results found.</p>
						) : (
							results.map((item) => <LibrisResultCard key={item.id || item.title} result={item} />)
						)}
					</div>
				</CardContent>
			</Card>
		);
	},
});

