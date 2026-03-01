"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { AlertCircleIcon, ChevronDownIcon } from "lucide-react";
import { useContext, useState } from "react";
import { z } from "zod";
import { SpotlightArenaActiveContext } from "@/components/tool-ui/spotlight-arena";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

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

const MODEL_LOGOS: Record<string, { src: string; alt: string }> = {
	call_grok: { src: "/model-logos/grok.png", alt: "Grok" },
	call_gpt: { src: "/model-logos/chatgpt.png", alt: "ChatGPT" },
	call_claude: { src: "/model-logos/claude.png", alt: "Claude" },
	call_gemini: { src: "/model-logos/gemini.png", alt: "Gemini" },
	call_deepseek: { src: "/model-logos/deepseek.png", alt: "DeepSeek" },
	call_perplexity: { src: "/model-logos/perplexity.png", alt: "Perplexity" },
	call_qwen: { src: "/model-logos/qwen.png", alt: "Qwen" },
	call_oneseek: { src: "/model-logos/oneseek.png", alt: "Oneseek" },
};

function formatLatency(latencyMs?: number | null): string {
	if (typeof latencyMs !== "number" || Number.isNaN(latencyMs)) return "";
	if (latencyMs >= 1000) return `${(latencyMs / 1000).toFixed(1)}s`;
	return `${Math.round(latencyMs)}ms`;
}

function formatUsage(
	usage: ExternalModelResult["usage"] | null | undefined,
	estimate?: { totalTokens: number; isEstimated: boolean } | null
): string {
	if (usage) {
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
	}
	if (estimate?.totalTokens) {
		return `${estimate.isEstimated ? "~" : ""}${estimate.totalTokens} tokens`;
	}
	return "";
}

const ENERGY_WH_PER_1K_TOKENS = 0.2;
const CO2G_PER_1K_TOKENS = 0.1;

function formatEstimate(value: number, digits = 2): string {
	if (!Number.isFinite(value)) return "";
	if (value === 0) return "0";
	if (value < 0.01) return value.toFixed(3);
	if (value < 1) return value.toFixed(2);
	return value.toFixed(digits);
}

function estimateTokensFromText(text: string): number {
	if (!text) return 0;
	return Math.max(1, Math.round(text.length / 4));
}

function resolveTokenEstimate(
	usage: ExternalModelResult["usage"] | null | undefined,
	args: ExternalModelArgs,
	result?: ExternalModelResult | null
): { totalTokens: number; isEstimated: boolean } | null {
	if (usage && typeof usage.total_tokens === "number") {
		return { totalTokens: usage.total_tokens, isEstimated: false };
	}
	const promptTokens = estimateTokensFromText(args.query ?? "");
	const completionTokens = estimateTokensFromText(result?.response ?? "");
	const total = promptTokens + completionTokens;
	if (!total) return null;
	return { totalTokens: total, isEstimated: true };
}

function estimateImpact(
	tokenEstimate?: { totalTokens: number; isEstimated: boolean } | null
) {
	if (!tokenEstimate) return null;
	const totalTokens = tokenEstimate.totalTokens;

	const energyWh = (totalTokens / 1000) * ENERGY_WH_PER_1K_TOKENS;
	const co2g = (totalTokens / 1000) * CO2G_PER_1K_TOKENS;
	const ledMinutes = (energyWh / 10) * 60;
	const kwh = energyWh / 1000;

	const cleanMin = kwh * 10;
	const cleanMax = kwh * 50;
	const avgMin = kwh * 100;
	const avgMax = kwh * 300;
	const dirtyMin = kwh * 600;
	const dirtyMax = kwh * 900;

	return {
		totalTokens,
		isEstimated: tokenEstimate.isEstimated,
		energyWh,
		co2g,
		ledMinutes,
		co2Ranges: {
			clean: [cleanMin, cleanMax] as [number, number],
			avg: [avgMin, avgMax] as [number, number],
			dirty: [dirtyMin, dirtyMax] as [number, number],
		},
	};
}

function resolveSummary(result?: ExternalModelResult | null): string {
	if (!result) return "";
	if (result.summary) return result.summary;
	if (result.response) return result.response.slice(0, 220);
	return "";
}

function ModelLogo({ toolName, label }: { toolName: string; label: string }) {
	const [hasError, setHasError] = useState(false);
	const logo = MODEL_LOGOS[toolName];
	if (!logo || hasError) {
		const fallback = label.trim().slice(0, 1).toUpperCase() || "M";
		return (
			<div className="flex size-10 items-center justify-center rounded-lg border border-border/60 bg-muted text-xs font-semibold text-muted-foreground">
				{fallback}
			</div>
		);
	}
	return (
		<img
			src={logo.src}
			alt={`${logo.alt} logo`}
			className="size-10 rounded-lg border border-border/60 bg-white object-contain p-1"
			loading="lazy"
			onError={() => setHasError(true)}
		/>
	);
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
	toolName,
	args,
	result,
	status,
}: {
	label: string;
	toolName: string;
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
	const source = result.source || result.provider || "External model";
	const latency = formatLatency(result.latency_ms);
	const tokenEstimate = resolveTokenEstimate(result.usage, args, result);
	const usage = formatUsage(result.usage, tokenEstimate);
	const impact = estimateImpact(tokenEstimate);
	const rawResponse = result.response || "";
	const hasFullResponse = typeof rawResponse === "string" && rawResponse.trim().length > 0;
	const showExpand = hasFullResponse;
	const metadataRows = [
		{ label: "Model", value: result.model || displayName },
		{ label: "Provider", value: result.provider },
		{ label: "Model string", value: result.model_string },
		{ label: "API base", value: result.api_base },
		{ label: "Latency", value: latency },
		{ label: "Usage", value: usage },
	].filter((row) => row.value);

	return (
		<Card className="my-4 w-full">
			<CardContent className="p-3">
				<div className="flex items-center justify-between gap-4">
					<div className="flex items-center gap-3">
						<ModelLogo toolName={toolName} label={displayName} />
						<div>
							<div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
								<span className="text-xs text-muted-foreground">AI model</span>
								<Badge variant="secondary">{source}</Badge>
								{latency && <span>{latency}</span>}
							</div>
							<h3 className="mt-0.5 text-base font-semibold">{displayName}</h3>
						</div>
					</div>
					{usage && (
						<div className="text-right text-xs text-muted-foreground">
							<span>{usage}</span>
						</div>
					)}
				</div>

				{impact && (
					<div className="mt-2 flex flex-wrap gap-2">
						<Tooltip>
							<TooltipTrigger asChild>
								<Badge variant="secondary" className="text-[10px]">
									CO₂e {impact.isEstimated ? "≈" : ""}
									{formatEstimate(impact.co2g)} g
								</Badge>
							</TooltipTrigger>
							<TooltipContent>
								<p className="text-xs">
									Antagande: 0,1 g CO₂e per 1 000 tokens. Elmix: ren 10–50 g/kWh →{" "}
									{formatEstimate(impact.co2Ranges.clean[0])}–
									{formatEstimate(impact.co2Ranges.clean[1])} g · mix 100–300 g/kWh →{" "}
									{formatEstimate(impact.co2Ranges.avg[0])}–
									{formatEstimate(impact.co2Ranges.avg[1])} g · kol 600–900 g/kWh →{" "}
									{formatEstimate(impact.co2Ranges.dirty[0])}–
									{formatEstimate(impact.co2Ranges.dirty[1])} g
								</p>
							</TooltipContent>
						</Tooltip>
						<Tooltip>
							<TooltipTrigger asChild>
								<Badge variant="secondary" className="text-[10px]">
									Energi {impact.isEstimated ? "≈" : ""}
									{formatEstimate(impact.energyWh)} Wh
								</Badge>
							</TooltipTrigger>
							<TooltipContent>
								<p className="text-xs">
									Antagande: 0,2 Wh per 1 000 tokens (≈ 10 W LED i{" "}
									{formatEstimate(impact.ledMinutes)} min).
								</p>
							</TooltipContent>
						</Tooltip>
					</div>
				)}

				{showExpand && (
					<Collapsible open={open} onOpenChange={setOpen}>
						<CollapsibleTrigger asChild>
							<Button
								variant="ghost"
								size="sm"
								className="mt-2 w-full justify-center text-xs text-muted-foreground"
							>
								<span>{open ? "Hide full response" : "Show full response"}</span>
								<ChevronDownIcon
									className={`ml-2 size-4 transition-transform ${open ? "rotate-180" : ""}`}
								/>
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
									<div className="whitespace-pre-wrap text-sm text-foreground leading-relaxed">
										{rawResponse}
									</div>
								) : (
									<p className="text-xs text-muted-foreground">No response to display.</p>
								)}
							</div>
						</CollapsibleContent>
					</Collapsible>
				)}
			</CardContent>
		</Card>
	);
}

function createExternalModelToolUI(toolName: string, label: string) {
	return makeAssistantToolUI<ExternalModelArgs, ExternalModelResult>({
		toolName,
		render: function ExternalModelUI({ args, result, status }) {
			const isInArena = useContext(SpotlightArenaActiveContext);
			if (isInArena) return null;

			return (
				<ModelCard
					label={label}
					toolName={toolName}
					args={args}
					result={result}
					status={status}
				/>
			);
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
export const QwenToolUI = createExternalModelToolUI("call_qwen", "Qwen");
export const OneseekToolUI = createExternalModelToolUI("call_oneseek", "Oneseek");
