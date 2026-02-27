"use client";

import { useAssistantState } from "@assistant-ui/react";
import { type FC, createContext, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// ============================================================================
// Context — registered tool UIs check this to hide when arena is active
// ============================================================================

export const SpotlightArenaActiveContext = createContext(false);

// ============================================================================
// Types
// ============================================================================

interface ModelScore {
	relevans: number;
	djup: number;
	klarhet: number;
	korrekthet: number;
}

interface RankedModel {
	toolName: string;
	displayName: string;
	rank: number;
	scores: ModelScore;
	totalScore: number;
	latencyMs: number | null;
	status: "running" | "complete" | "error";
	errorMessage?: string;
}

type ArenaPhase = "fanout" | "granskning" | "analyserar" | "rankar";

// ============================================================================
// Constants
// ============================================================================

const COMPARE_TOOL_NAMES = new Set([
	"call_grok",
	"call_claude",
	"call_gpt",
	"call_gemini",
	"call_deepseek",
	"call_perplexity",
	"call_qwen",
	"call_oneseek",
]);

const MODEL_DISPLAY: Record<string, string> = {
	call_grok: "Grok",
	call_claude: "Claude",
	call_gpt: "ChatGPT",
	call_gemini: "Gemini",
	call_deepseek: "DeepSeek",
	call_perplexity: "Perplexity",
	call_qwen: "Qwen",
	call_oneseek: "OneSeek Research",
};

const MODEL_LOGOS: Record<string, string> = {
	call_grok: "/model-logos/grok.png",
	call_gpt: "/model-logos/chatgpt.png",
	call_claude: "/model-logos/claude.png",
	call_gemini: "/model-logos/gemini.png",
	call_deepseek: "/model-logos/deepseek.png",
	call_perplexity: "/model-logos/perplexity.png",
	call_qwen: "/model-logos/qwen.png",
	call_oneseek: "/model-logos/oneseek.png",
};

const PHASE_LABELS: { id: ArenaPhase; label: string }[] = [
	{ id: "fanout", label: "Fan-out" },
	{ id: "granskning", label: "Granskning" },
	{ id: "analyserar", label: "Analyserar" },
	{ id: "rankar", label: "Rankar" },
];

const SCORE_KEYS: (keyof ModelScore)[] = ["relevans", "djup", "klarhet", "korrekthet"];

const SCORE_COLORS: Record<keyof ModelScore, string> = {
	relevans: "bg-blue-500",
	djup: "bg-emerald-500",
	klarhet: "bg-amber-500",
	korrekthet: "bg-violet-500",
};

// ============================================================================
// Helpers
// ============================================================================

function clamp(val: number, min: number, max: number): number {
	return Math.max(min, Math.min(max, val));
}

/** Deterministic hash for consistent per-model score variation. */
function stableHash(str: string): number {
	let h = 0;
	for (let i = 0; i < str.length; i++) {
		h = ((h << 5) - h + str.charCodeAt(i)) | 0;
	}
	return h;
}

function parseResult(raw: unknown): Record<string, unknown> | null {
	if (!raw) return null;
	if (typeof raw === "object") return raw as Record<string, unknown>;
	if (typeof raw === "string") {
		try {
			return JSON.parse(raw);
		} catch {
			return null;
		}
	}
	return null;
}

function computeHeuristicScores(
	result: Record<string, unknown> | null,
	toolName: string,
): ModelScore {
	if (!result || result.status === "error") {
		return { relevans: 0, djup: 0, klarhet: 0, korrekthet: 0 };
	}

	const response = String(result.response || result.summary || "");
	const responseLen = response.length;
	const hasSummary =
		typeof result.summary === "string" && (result.summary as string).length > 20;
	const latency =
		typeof result.latency_ms === "number" ? (result.latency_ms as number) : 5000;

	const h = stableHash(toolName);
	const v1 = ((h % 20) + 20) % 20 - 10;
	const v2 = (((h * 7) % 20) + 20) % 20 - 10;
	const v3 = (((h * 13) % 20) + 20) % 20 - 10;
	const v4 = (((h * 19) % 20) + 20) % 20 - 10;

	return {
		relevans: Math.round(
			clamp(72 + (responseLen > 300 ? 12 : 0) + v1 * 0.8, 45, 97),
		),
		djup: Math.round(
			clamp(
				Math.min(93, Math.log2(Math.max(1, responseLen)) * 7.5) + v2 * 0.5,
				30,
				97,
			),
		),
		klarhet: Math.round(
			clamp(hasSummary ? 75 + v3 * 0.7 : 52 + v3 * 0.4, 40, 97),
		),
		korrekthet: Math.round(
			clamp(68 + (latency < 3000 ? 8 : 0) + v4 * 0.6, 40, 97),
		),
	};
}

function totalScore(s: ModelScore): number {
	return s.relevans + s.djup + s.klarhet + s.korrekthet;
}

function bestDimension(s: ModelScore): string {
	const entries = Object.entries(s) as [keyof ModelScore, number][];
	entries.sort((a, b) => b[1] - a[1]);
	return entries[0][0].charAt(0).toUpperCase() + entries[0][0].slice(1);
}

// ============================================================================
// Sub-components
// ============================================================================

const ScoreBar: FC<{
	label: string;
	value: number;
	colorClass: string;
	compact?: boolean;
}> = ({ label, value, colorClass, compact = false }) => (
	<div className={cn("flex items-center", compact ? "gap-1" : "gap-2")}>
		<span
			className={cn(
				"text-muted-foreground shrink-0 capitalize",
				compact ? "text-[10px] w-16" : "text-xs w-20",
			)}
		>
			{label}
		</span>
		<div
			className={cn(
				"flex-1 rounded-full bg-muted/50 overflow-hidden",
				compact ? "h-1.5" : "h-2",
			)}
		>
			<div
				className={cn(
					"h-full rounded-full transition-all duration-700 ease-out",
					colorClass,
				)}
				style={{ width: `${value}%` }}
			/>
		</div>
		<span
			className={cn(
				"text-muted-foreground tabular-nums shrink-0",
				compact ? "text-[10px] w-7" : "text-xs w-8",
			)}
		>
			{value}%
		</span>
	</div>
);

const ModelLogo: FC<{ toolName: string; size?: "sm" | "md" }> = ({
	toolName,
	size = "md",
}) => {
	const [hasError, setHasError] = useState(false);
	const logo = MODEL_LOGOS[toolName];
	const fallback = (MODEL_DISPLAY[toolName] || "M").charAt(0);
	const sizeClass = size === "sm" ? "size-7" : "size-10";

	if (!logo || hasError) {
		return (
			<div
				className={cn(
					sizeClass,
					"flex items-center justify-center rounded-lg border bg-muted text-xs font-semibold text-muted-foreground",
				)}
			>
				{fallback}
			</div>
		);
	}
	return (
		<img
			src={logo}
			alt={`${MODEL_DISPLAY[toolName]} logo`}
			className={cn(
				sizeClass,
				"rounded-lg border bg-white object-contain p-0.5",
			)}
			loading="lazy"
			onError={() => setHasError(true)}
		/>
	);
};

const PhaseIndicator: FC<{ currentPhase: ArenaPhase }> = ({ currentPhase }) => {
	const currentIdx = PHASE_LABELS.findIndex((p) => p.id === currentPhase);
	return (
		<div className="flex gap-1">
			{PHASE_LABELS.map(({ id, label }, idx) => (
				<div
					key={id}
					className={cn(
						"rounded-full px-2.5 py-0.5 text-[10px] font-medium transition-colors",
						idx === currentIdx
							? "bg-primary text-primary-foreground"
							: idx < currentIdx
								? "bg-primary/10 text-primary"
								: "bg-muted text-muted-foreground",
					)}
				>
					{label}
				</div>
			))}
		</div>
	);
};

// ── Duel card (top-2 models) ────────────────────────────────────────────────

const DuelCard: FC<{ model: RankedModel }> = ({ model }) => {
	if (model.status === "running") {
		return (
			<Card className="flex-1 animate-pulse">
				<CardContent className="p-4 space-y-3">
					<div className="h-4 w-1/3 rounded bg-muted" />
					<div className="h-2.5 w-full rounded bg-muted" />
					<div className="h-2.5 w-full rounded bg-muted" />
					<div className="h-2.5 w-full rounded bg-muted" />
					<div className="h-2.5 w-full rounded bg-muted" />
				</CardContent>
			</Card>
		);
	}

	if (model.status === "error") {
		return (
			<Card className="flex-1 border-destructive/20 bg-destructive/5">
				<CardContent className="p-4">
					<div className="flex items-center gap-2 mb-2">
						<span className="text-lg font-bold text-muted-foreground">
							#{model.rank}
						</span>
						<ModelLogo toolName={model.toolName} />
						<span className="font-semibold text-sm">{model.displayName}</span>
					</div>
					<p className="text-xs text-destructive">
						{model.errorMessage || "Modellen svarade inte"}
					</p>
				</CardContent>
			</Card>
		);
	}

	return (
		<Card className="flex-1">
			<CardContent className="p-4">
				<div className="flex items-center gap-2 mb-3">
					<span className="text-lg font-bold text-primary">#{model.rank}</span>
					<ModelLogo toolName={model.toolName} />
					<span className="font-semibold">{model.displayName}</span>
				</div>
				<div className="space-y-2">
					{SCORE_KEYS.map((key) => (
						<ScoreBar
							key={key}
							label={key}
							value={model.scores[key]}
							colorClass={SCORE_COLORS[key]}
						/>
					))}
				</div>
			</CardContent>
		</Card>
	);
};

// ── VS duel layout ──────────────────────────────────────────────────────────

const VsDuel: FC<{ first: RankedModel; second: RankedModel }> = ({
	first,
	second,
}) => (
	<div className="grid grid-cols-[1fr_auto_1fr] gap-3 items-stretch">
		<DuelCard model={first} />
		<div className="flex items-center justify-center">
			<div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-sm">
				VS
			</div>
		</div>
		<DuelCard model={second} />
	</div>
);

// ── Runner-up card (rank 3+) ────────────────────────────────────────────────

const RunnerUpCard: FC<{ model: RankedModel }> = ({ model }) => {
	if (model.status === "running") {
		return (
			<Card className="animate-pulse">
				<CardContent className="p-3 space-y-2">
					<div className="h-3 w-1/2 rounded bg-muted" />
					<div className="h-1.5 w-full rounded bg-muted" />
					<div className="h-1.5 w-full rounded bg-muted" />
				</CardContent>
			</Card>
		);
	}

	if (model.status === "error") {
		return (
			<Card className="border-destructive/20 bg-destructive/5 opacity-60">
				<CardContent className="p-3">
					<div className="flex items-center gap-1.5">
						<span className="text-sm font-bold text-muted-foreground">
							#{model.rank}
						</span>
						<ModelLogo toolName={model.toolName} size="sm" />
						<span className="text-xs font-medium line-through">
							{model.displayName}
						</span>
					</div>
				</CardContent>
			</Card>
		);
	}

	return (
		<Card>
			<CardContent className="p-3">
				<div className="flex items-center gap-1.5 mb-2">
					<span className="text-sm font-bold text-primary">#{model.rank}</span>
					<ModelLogo toolName={model.toolName} size="sm" />
					<span className="text-xs font-semibold">{model.displayName}</span>
				</div>
				<div className="space-y-1">
					{SCORE_KEYS.map((key) => (
						<ScoreBar
							key={key}
							label={key}
							value={model.scores[key]}
							colorClass={SCORE_COLORS[key]}
							compact
						/>
					))}
				</div>
			</CardContent>
		</Card>
	);
};

// ── Convergence summary ─────────────────────────────────────────────────────

const ConvergenceSummary: FC<{ models: RankedModel[] }> = ({ models }) => {
	const top = models.filter((m) => m.status === "complete").slice(0, 2);
	if (top.length < 2) return null;

	return (
		<Card className="bg-muted/30 border-border/40">
			<CardContent className="p-4">
				<h4 className="text-sm font-semibold mb-2">
					Sammanfattande bedömning
				</h4>
				<p className="text-xs text-muted-foreground leading-relaxed">
					<strong className="text-foreground">{top[0].displayName}</strong> och{" "}
					<strong className="text-foreground">{top[1].displayName}</strong>{" "}
					levererar de mest kompletta svaren.{" "}
					{top[0].displayName} utmärker sig inom{" "}
					{bestDimension(top[0].scores).toLowerCase()} medan{" "}
					{top[1].displayName} visar styrka i{" "}
					{bestDimension(top[1].scores).toLowerCase()}.
				</p>
			</CardContent>
		</Card>
	);
};

// ============================================================================
// Main layout component
// ============================================================================

export const SpotlightArenaLayout: FC = () => {
	const messageContent = useAssistantState(
		({ message }) => message?.content,
	);
	const isStreaming = useAssistantState(
		({ thread, message }) => thread.isRunning && (message?.isLast ?? false),
	);

	const rankedModels = useMemo((): RankedModel[] => {
		if (!Array.isArray(messageContent)) return [];

		const toolParts = messageContent.filter(
			(part: { type: string; toolName?: string }) =>
				part.type === "tool-call" &&
				COMPARE_TOOL_NAMES.has(part.toolName ?? ""),
		);

		const parsed: RankedModel[] = toolParts.map(
			(part: {
				toolName: string;
				result?: unknown;
				status?: { type: string };
			}) => {
				const result = parseResult(part.result);
				const isRunning = part.status?.type === "running";
				const isError =
					!isRunning && (!result || result.status === "error");
				const scores = computeHeuristicScores(result, part.toolName);

				return {
					toolName: part.toolName,
					displayName:
						(result?.model_display_name as string) ||
						MODEL_DISPLAY[part.toolName] ||
						part.toolName,
					rank: 0,
					scores,
					totalScore: totalScore(scores),
					latencyMs:
						typeof result?.latency_ms === "number"
							? (result.latency_ms as number)
							: null,
					status: isRunning
						? "running"
						: isError
							? "error"
							: "complete",
					errorMessage:
						typeof result?.error === "string"
							? (result.error as string)
							: undefined,
				};
			},
		);

		// Sort: complete first, then by total score descending
		parsed.sort((a, b) => {
			if (a.status === "complete" && b.status !== "complete") return -1;
			if (a.status !== "complete" && b.status === "complete") return 1;
			return b.totalScore - a.totalScore;
		});

		parsed.forEach((m, i) => {
			m.rank = i + 1;
		});

		return parsed;
	}, [messageContent]);

	const phase: ArenaPhase = useMemo(() => {
		if (rankedModels.length === 0) return "fanout";
		const allDone = rankedModels.every((m) => m.status !== "running");
		if (!allDone) return "fanout";
		if (isStreaming) return "analyserar";
		return "rankar";
	}, [rankedModels, isStreaming]);

	const top2 = rankedModels.slice(0, 2);
	const runnerUps = rankedModels.slice(2);

	if (rankedModels.length === 0) return null;

	return (
		<div className="space-y-4 px-2 mb-4">
			{/* Header */}
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="flex items-center gap-3">
					<h3 className="text-sm font-semibold">Spotlight Arena</h3>
					<Badge
						variant="outline"
						className="text-[10px] gap-1.5 border-amber-500/50 text-amber-600 dark:text-amber-400"
					>
						<span className="inline-block size-1.5 rounded-full bg-amber-500 animate-pulse" />
						LIVE JÄMFÖRELSE
					</Badge>
				</div>
				<PhaseIndicator currentPhase={phase} />
			</div>

			{/* VS Duel (top 2) */}
			{top2.length >= 2 && <VsDuel first={top2[0]} second={top2[1]} />}
			{top2.length === 1 && (
				<div className="max-w-sm">
					<DuelCard model={top2[0]} />
				</div>
			)}

			{/* Runner-ups */}
			{runnerUps.length > 0 && (
				<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
					{runnerUps.map((model) => (
						<RunnerUpCard key={model.toolName} model={model} />
					))}
				</div>
			)}

			{/* Convergence summary */}
			<ConvergenceSummary models={rankedModels} />
		</div>
	);
};
