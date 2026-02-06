"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { AlertCircleIcon, ChevronDownIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

// ============================================================================
// Zod Schemas
// ============================================================================

const ExternalModelArgsSchema = z
	.object({
		query: z.string().nullish(),
	})
	.partial();

const ExternalModelUsageSchema = z
	.object({
		prompt_tokens: z.number().nullish(),
		completion_tokens: z.number().nullish(),
		total_tokens: z.number().nullish(),
	})
	.partial();

const ExternalModelResultSchema = z
	.object({
		status: z.string().nullish(),
		error: z.string().nullish(),
		model_display_name: z.string().nullish(),
		provider: z.string().nullish(),
		model: z.string().nullish(),
		model_string: z.string().nullish(),
		api_base: z.string().nullish(),
		source: z.string().nullish(),
		latency_ms: z.number().nullish(),
		usage: ExternalModelUsageSchema.nullish(),
		summary: z.string().nullish(),
		response: z.string().nullish(),
		truncated: z.boolean().nullish(),
	})
	.partial()
	.passthrough();

type ExternalModelArgs = z.infer<typeof ExternalModelArgsSchema>;
type ExternalModelResult = z.infer<typeof ExternalModelResultSchema>;

// ============================================================================
// Helpers
// ============================================================================

function formatLatency(latencyMs?: number | null): string {
	if (typeof latencyMs !== "number" || Number.isNaN(latencyMs)) return "";
	if (latencyMs >= 1000) return `${(latencyMs / 1000).toFixed(1)}s`;
	return `${Math.round(latencyMs)}ms`;
}

function formatUsage(usage?: ExternalModelResult["usage"] | null): string {
	if (!usage) return "";
	const prompt = usage.prompt_tokens ?? undefined;
	const completion = usage.completion_tokens ?? undefined;
	const total = usage.total_tokens ?? undefined;
	if (typeof total === "number") {
		return `${total} tokens`;
	}
	if (typeof prompt === "number" || typeof completion === "number") {
		const parts = [
			typeof prompt === "number" ? `p${prompt}` : null,
			typeof completion === "number" ? `c${completion}` : null,
		].filter(Boolean);
		return parts.length ? `${parts.join(" / ")} tokens` : "";
	}
	return "";
}

function resolveSummary(result?: ExternalModelResult | null): string {
	if (!result) return "";
	if (result.summary) return result.summary;
	if (result.response) return result.response.slice(0, 220);
	return "";
}

function ModelErrorState({ label, error }: { label: string; error: string }) {
	return (
		<div className="my-4 overflow-hidden rounded-xl border border-destructive/20 bg-destructive/5 p-4 w-full">
			<div className="flex items-center gap-4">
				<div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-destructive/10">
					<AlertCircleIcon className="size-6 text-destructive" />
				</div>
				<div className="flex-1 min-w-0">
					<p className="font-medium text-destructive text-sm">{label} failed</p>
					<p className="text-muted-foreground text-xs mt-1">{error}</p>
				</div>
			</div>
		</div>
	);
}

function ModelLoading({ label }: { label: string }) {
	return (
		<Card className="my-4 w-full animate-pulse">
			<CardContent className="p-4">
				<div className="h-4 w-1/3 rounded bg-muted" />
				<div className="mt-3 h-8 w-2/3 rounded bg-muted" />
				<div className="mt-3 h-3 w-full rounded bg-muted" />
			</CardContent>
		</Card>
	);
}

function ModelCard({
	label,
	args,
	result,
	status,
}: {
	label: string;
	args: ExternalModelArgs;
	result: ExternalModelResult | undefined;
	status: { type: string; reason?: string; error?: unknown };
}) {
	const [open, setOpen] = useState(false);

	if (status.type === "running" || status.type === "requires-action") {
		return <ModelLoading label={label} />;
	}

	if (status.type === "incomplete") {
		if (status.reason === "cancelled") {
			return (
				<div className="my-4 rounded-xl border border-muted p-4 text-muted-foreground w-full">
					<p className="line-through">{label} call cancelled</p>
				</div>
			);
		}
		if (status.reason === "error") {
			return (
				<ModelErrorState
					label={label}
					error={typeof status.error === "string" ? status.error : "An error occurred"}
				/>
			);
		}
	}

	if (!result) {
		return <ModelLoading label={label} />;
	}

	if (result.error || result.status === "error") {
		return <ModelErrorState label={label} error={result.error || "Model call failed"} />;
	}

	const displayName = result.model_display_name || label;
	const summary = resolveSummary(result);
	const source = result.source || result.provider || "External model";
	const latency = formatLatency(result.latency_ms);
	const usage = formatUsage(result.usage);
	const queryText = args.query;
	const rawResponse = result.response || "";
	const metadataRows = useMemo(
		() =>
			[
				{ label: "Model", value: result.model || displayName },
				{ label: "Provider", value: result.provider },
				{ label: "Model string", value: result.model_string },
				{ label: "API base", value: result.api_base },
				{ label: "Latency", value: latency },
				{ label: "Usage", value: usage },
			].filter((row) => row.value),
		[displayName, latency, result.api_base, result.model, result.model_string, result.provider, usage]
	);

	return (
		<Card className="my-4 w-full">
			<CardContent className="p-4">
				<div className="flex items-start justify-between gap-4">
					<div>
						<div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
							<Badge variant="secondary">{source}</Badge>
							{latency && <span>{latency}</span>}
						</div>
						<h3 className="mt-1 text-lg font-semibold">{displayName}</h3>
						{queryText && (
							<p className="mt-1 text-xs text-muted-foreground">
								Query: <span className="font-medium text-foreground">{queryText}</span>
							</p>
						)}
					</div>
					{usage && (
						<div className="text-right text-xs text-muted-foreground">
							<span>{usage}</span>
						</div>
					)}
				</div>

				{summary && (
					<p className="mt-3 text-sm text-foreground whitespace-pre-wrap">{summary}</p>
				)}

				{result.truncated && (
					<p className="mt-2 text-xs text-amber-600">
						Response truncated in UI card.
					</p>
				)}

				<Collapsible open={open} onOpenChange={setOpen}>
					<CollapsibleTrigger asChild>
						<Button
							variant="ghost"
							size="sm"
							className="mt-3 w-full justify-center text-xs text-muted-foreground"
						>
							<span>{open ? "Hide full response" : "Show full response"}</span>
							<ChevronDownIcon className={`ml-2 size-4 transition-transform ${open ? "rotate-180" : ""}`} />
						</Button>
					</CollapsibleTrigger>
					<CollapsibleContent>
						<div className="mt-3 rounded-lg border border-border/60 bg-background/60 p-3 space-y-3">
							{metadataRows.length > 0 && (
								<div className="grid gap-2 text-xs text-muted-foreground">
									{metadataRows.map((row) => (
										<div key={row.label} className="flex items-center justify-between gap-2">
											<span>{row.label}</span>
											<span className="text-foreground">{row.value}</span>
										</div>
									))}
								</div>
							)}
							{rawResponse ? (
								<pre className="whitespace-pre-wrap text-xs text-foreground">{rawResponse}</pre>
							) : (
								<p className="text-xs text-muted-foreground">No response content.</p>
							)}
						</div>
					</CollapsibleContent>
				</Collapsible>
			</CardContent>
		</Card>
	);
}

function createExternalModelToolUI(toolName: string, label: string) {
	return makeAssistantToolUI<ExternalModelArgs, ExternalModelResult>({
		toolName,
		render: function ExternalModelUI({ args, result, status }) {
			return <ModelCard label={label} args={args} result={result} status={status} />;
		},
	});
}

export const GrokToolUI = createExternalModelToolUI("call_grok", "Grok");
export const ClaudeToolUI = createExternalModelToolUI("call_claude", "Claude");
export const GptToolUI = createExternalModelToolUI("call_gpt", "ChatGPT");
export const GeminiToolUI = createExternalModelToolUI("call_gemini", "Gemini");
export const DeepSeekToolUI = createExternalModelToolUI("call_deepseek", "DeepSeek");
export const PerplexityToolUI = createExternalModelToolUI(
	"call_perplexity",
	"Perplexity"
);
