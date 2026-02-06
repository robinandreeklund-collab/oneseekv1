"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { AlertCircleIcon, ExternalLinkIcon, MapPinIcon, BriefcaseIcon } from "lucide-react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

// ============================================================================
// Zod Schemas
// ============================================================================

const JobAdResultSchema = z
	.object({
		id: z.string().nullish(),
		headline: z.string().nullish(),
		employer: z.string().nullish(),
		location: z.string().nullish(),
		published: z.string().nullish(),
		application_url: z.string().nullish(),
		remote: z.boolean().nullish(),
		brief: z.string().nullish(),
		occupation_group: z.string().nullish(),
		occupation_field: z.string().nullish(),
		sources: z
			.array(
				z.object({
					label: z.string().nullish(),
					url: z.string().nullish(),
				})
			)
			.nullish(),
	})
	.partial();

const JobAdLinksArgsSchema = z
	.object({
		query: z.string().nullish(),
		location: z.string().nullish(),
		occupation: z.string().nullish(),
		industry: z.string().nullish(),
		remote: z.boolean().nullish(),
	})
	.partial();

const JobAdLinksResultSchema = z
	.object({
		status: z.string().nullish(),
		error: z.string().nullish(),
		query: z.string().nullish(),
		results: z.array(JobAdResultSchema).nullish(),
		total: z.number().nullish(),
		attribution: z.string().nullish(),
	})
	.partial()
	.passthrough();

type JobAdLinksArgs = z.infer<typeof JobAdLinksArgsSchema>;
type JobAdLinksResult = z.infer<typeof JobAdLinksResultSchema>;

// ============================================================================
// Helpers
// ============================================================================

function JobAdErrorState({ error }: { error: string }) {
	return (
		<div className="my-4 overflow-hidden rounded-xl border border-destructive/20 bg-destructive/5 p-4 max-w-2xl">
			<div className="flex items-center gap-4">
				<div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-destructive/10">
					<AlertCircleIcon className="size-6 text-destructive" />
				</div>
				<div className="flex-1 min-w-0">
					<p className="font-medium text-destructive text-sm">Failed to load job ads</p>
					<p className="text-muted-foreground text-xs mt-1">{error}</p>
				</div>
			</div>
		</div>
	);
}

function JobAdLoading() {
	return (
		<Card className="my-4 w-full max-w-2xl animate-pulse">
			<CardContent className="p-4">
				<div className="h-4 w-1/2 rounded bg-muted" />
				<div className="mt-3 h-3 w-3/4 rounded bg-muted" />
				<div className="mt-2 h-3 w-full rounded bg-muted" />
			</CardContent>
		</Card>
	);
}

function formatDate(value?: string | null): string {
	if (!value) return "";
	const dt = new Date(value);
	if (Number.isNaN(dt.getTime())) return value;
	return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(dt);
}

function truncate(text?: string | null, limit = 140): string {
	if (!text) return "";
	return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

// ============================================================================
// Tool UI
// ============================================================================

export const JobAdLinksToolUI = makeAssistantToolUI<JobAdLinksArgs, JobAdLinksResult>({
	toolName: "jobad_links_search",
	render: function JobAdLinksUI({ args, result, status }) {
		if (status.type === "running" || status.type === "requires-action") {
			return <JobAdLoading />;
		}

		if (status.type === "incomplete") {
			if (status.reason === "cancelled") {
				return (
					<div className="my-4 rounded-xl border border-muted p-4 text-muted-foreground max-w-2xl">
						<p className="line-through">Job ad search cancelled</p>
					</div>
				);
			}
			if (status.reason === "error") {
				return (
					<JobAdErrorState
						error={typeof status.error === "string" ? status.error : "An error occurred"}
					/>
				);
			}
		}

		if (!result) {
			return <JobAdLoading />;
		}

		if (result.error || result.status === "error") {
			return <JobAdErrorState error={result.error || "Job ad search failed"} />;
		}

		const results = result.results || [];
		return (
			<Card className="my-4 w-full max-w-2xl">
				<CardContent className="p-4">
					<div className="flex items-center justify-between">
						<div className="text-sm text-muted-foreground">Job ads</div>
						{typeof result.total === "number" && (
							<Badge variant="secondary">{result.total} ads</Badge>
						)}
					</div>
					{args.query && (
						<p className="mt-1 text-xs text-muted-foreground">
							Query: <span className="font-medium text-foreground">{args.query}</span>
						</p>
					)}
					<div className="mt-3 space-y-3">
						{results.length === 0 ? (
							<p className="text-sm text-muted-foreground">No job ads found.</p>
						) : (
							results.map((job) => (
								<div key={job.id || job.headline} className="rounded-lg border border-border/60 p-3">
									<div className="flex items-start justify-between gap-3">
										<div>
											<p className="font-semibold text-sm">{job.headline || "Untitled job"}</p>
											<div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
												{job.employer && (
													<span className="inline-flex items-center gap-1">
														<BriefcaseIcon className="size-3" />
														{job.employer}
													</span>
												)}
												{job.location && (
													<span className="inline-flex items-center gap-1">
														<MapPinIcon className="size-3" />
														{job.location}
													</span>
												)}
												{job.occupation_field && <span>{job.occupation_field}</span>}
											</div>
											{job.published && (
												<p className="mt-1 text-[10px] text-muted-foreground">
													Published: {formatDate(job.published)}
												</p>
											)}
											{job.brief && (
												<p className="mt-2 text-xs text-muted-foreground">
													{truncate(job.brief, 160)}
												</p>
											)}
										</div>
										{job.application_url && (
											<Button
												size="sm"
												variant="outline"
												onClick={() =>
													window.open(job.application_url || "", "_blank", "noopener,noreferrer")
												}
											>
												Apply
												<ExternalLinkIcon className="ml-2 size-3" />
											</Button>
										)}
									</div>
									<div className="mt-2 flex flex-wrap gap-2">
										{job.remote && <Badge variant="secondary">Remote</Badge>}
										{job.occupation_group && (
											<Badge variant="secondary">{job.occupation_group}</Badge>
										)}
										{job.sources?.slice(0, 2).map((source) => (
											<Badge key={source.label || source.url} variant="outline">
												{source.label || "Source"}
											</Badge>
										))}
									</div>
								</div>
							))
						)}
					</div>
					{result.attribution && (
						<Badge variant="secondary" className="mt-3 w-fit">
							{result.attribution}
						</Badge>
					)}
				</CardContent>
			</Card>
		);
	},
});

