"use client";

import { useAssistantState } from "@assistant-ui/react";
import { AnimatePresence, motion } from "motion/react";
import {
	CheckCircle2Icon,
	ChevronDownIcon,
	ClockIcon,
	CoinsIcon,
	InfoIcon,
	LeafIcon,
	LoaderCircleIcon,
	ZapIcon,
} from "lucide-react";
import {
	type FC,
	createContext,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// ============================================================================
// Context — registered tool UIs check this to hide when arena is active
// ============================================================================

export const SpotlightArenaActiveContext = createContext(false);

// Live criterion scores context — SSE events push partial scores here before tool completion
export type LiveCriterionMap = Record<string, Partial<ModelScore>>;
export const LiveCriterionContext = createContext<LiveCriterionMap>({});

// Pod metadata per criterion from SSE events (domain → criterion → info)
export interface CriterionPodMeta {
	pod_id: string;
	parent_pod_id: string;
	latency_ms: number;
}
export type LiveCriterionPodMap = Record<string, Partial<Record<keyof ModelScore, CriterionPodMeta>>>;
export const LiveCriterionPodContext = createContext<LiveCriterionPodMap>({});

// ============================================================================
// Types
// ============================================================================

interface ModelScore {
	relevans: number;
	djup: number;
	klarhet: number;
	korrekthet: number;
}

type ModelReasonings = Partial<Record<keyof ModelScore, string>>;

interface ModelMeta {
	provider: string;
	model: string;
	modelString: string;
	source: string;
	latencyMs: number | null;
	tokens: {
		prompt: number | null;
		completion: number | null;
		total: number | null;
		isEstimated: boolean;
	};
	truncated: boolean;
}

interface RankedModel {
	toolName: string;
	displayName: string;
	domain: string;
	rank: number;
	scores: ModelScore;
	reasonings: ModelReasonings;
	criterionPodInfo: Partial<Record<keyof ModelScore, CriterionPodMeta>>;
	hasRealScores: boolean;
	totalScore: number;
	weightedScore: number;
	meta: ModelMeta;
	summary: string;
	fullResponse: string;
	status: "running" | "complete" | "error";
	errorMessage?: string;
}

interface ArenaAnalysis {
	consensus: string[];
	disagreements: {
		topic: string;
		sides: Record<string, string>;
		verdict: string;
	}[];
	unique_contributions: { model: string; insight: string }[];
	winner_rationale: string;
	reliability_notes: string;
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

/** Map tool_name → domain key used in convergence model_scores */
const TOOL_TO_DOMAIN: Record<string, string> = {
	call_grok: "grok",
	call_claude: "claude",
	call_gpt: "gpt",
	call_gemini: "gemini",
	call_deepseek: "deepseek",
	call_perplexity: "perplexity",
	call_qwen: "qwen",
	call_oneseek: "research",
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

const SCORE_KEYS: (keyof ModelScore)[] = [
	"relevans",
	"djup",
	"klarhet",
	"korrekthet",
];

const SCORE_COLORS: Record<keyof ModelScore, string> = {
	relevans: "bg-blue-500",
	djup: "bg-emerald-500",
	klarhet: "bg-amber-500",
	korrekthet: "bg-violet-500",
};

const SCORE_TEXT_COLORS: Record<keyof ModelScore, string> = {
	relevans: "text-blue-500",
	djup: "text-emerald-500",
	klarhet: "text-amber-500",
	korrekthet: "text-violet-500",
};

// CO2 / energy constants (same as compare-model.tsx)
const ENERGY_WH_PER_1K_TOKENS = 0.2;
const CO2G_PER_1K_TOKENS = 0.1;

// ============================================================================
// Helpers
// ============================================================================

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

function extractMeta(
	result: Record<string, unknown> | null,
	responseText: string,
	queryText: string,
): ModelMeta {
	if (!result) {
		return {
			provider: "",
			model: "",
			modelString: "",
			source: "",
			latencyMs: null,
			tokens: {
				prompt: null,
				completion: null,
				total: null,
				isEstimated: false,
			},
			truncated: false,
		};
	}

	const usage = result.usage as Record<string, unknown> | null | undefined;
	let prompt: number | null = null;
	let completion: number | null = null;
	let total: number | null = null;
	let isEstimated = false;

	if (usage) {
		if (typeof usage.prompt_tokens === "number") prompt = usage.prompt_tokens;
		if (typeof usage.completion_tokens === "number")
			completion = usage.completion_tokens;
		if (typeof usage.total_tokens === "number") total = usage.total_tokens;
	}

	if (total === null) {
		const estPrompt = Math.max(1, Math.round((queryText || "").length / 4));
		const estCompletion = Math.max(
			1,
			Math.round((responseText || "").length / 4),
		);
		total = estPrompt + estCompletion;
		prompt = estPrompt;
		completion = estCompletion;
		isEstimated = true;
	}

	return {
		provider: String(result.provider || ""),
		model: String(result.model || ""),
		modelString: String(result.model_string || ""),
		source: String(result.source || result.provider || ""),
		latencyMs:
			typeof result.latency_ms === "number" ? result.latency_ms : null,
		tokens: { prompt, completion, total, isEstimated },
		truncated: result.truncated === true,
	};
}

/** Confidence-weighted scoring matching backend weights */
const CRITERION_WEIGHTS: Record<keyof ModelScore, number> = {
	korrekthet: 0.35,
	relevans: 0.25,
	djup: 0.20,
	klarhet: 0.20,
};

function weightedScore(s: ModelScore): number {
	return Math.round(
		s.korrekthet * CRITERION_WEIGHTS.korrekthet +
		s.relevans * CRITERION_WEIGHTS.relevans +
		s.djup * CRITERION_WEIGHTS.djup +
		s.klarhet * CRITERION_WEIGHTS.klarhet
	);
}

function totalScore(s: ModelScore): number {
	return s.relevans + s.djup + s.klarhet + s.korrekthet;
}

function formatLatency(ms: number | null): string {
	if (ms === null) return "";
	if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
	return `${Math.round(ms)}ms`;
}

function formatTokens(meta: ModelMeta): string {
	const t = meta.tokens;
	if (t.total !== null) {
		return `${t.isEstimated ? "~" : ""}${t.total} tokens`;
	}
	return "";
}

function estimateCo2(meta: ModelMeta): { co2g: number; energyWh: number } | null {
	const total = meta.tokens.total;
	if (total === null || total === 0) return null;
	return {
		co2g: (total / 1000) * CO2G_PER_1K_TOKENS,
		energyWh: (total / 1000) * ENERGY_WH_PER_1K_TOKENS,
	};
}

function formatNum(n: number): string {
	if (n < 0.01) return n.toFixed(3);
	if (n < 1) return n.toFixed(2);
	return n.toFixed(1);
}

/** All JSON field names that smaller LLMs tend to dump as raw JSON */
const LEAKED_JSON_FIELDS = [
	"search_queries", "search_results", "winner_answer", "winner_rationale",
	"reasoning", "thinking", "arena_analysis", "consensus", "disagreements",
	"unique_contributions", "reliability_notes", "score",
] as const;

const FIELD_ALT = LEAKED_JSON_FIELDS.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");

/** Strip arena-data code blocks and leaked JSON from visible synthesis text */
function sanitizeSynthesisText(text: string): string {
	// 1. Remove ```spotlight-arena-data ... ``` blocks
	let cleaned = text.replace(/```spotlight-arena-data\s*\n[\s\S]*?```\s*\n?/g, "");
	// 2. Remove ```json ... ``` fenced blocks with leaked fields
	cleaned = cleaned.replace(/```json\s*\n[\s\S]*?```\s*\n?/g, "");
	// 3. Remove trailing JSON blob (greedy to end of text)
	cleaned = cleaned.replace(
		new RegExp(`\\n?\\s*\\{\\s*"(?:${FIELD_ALT})"[\\s\\S]*$`),
		"",
	);
	// 4. Remove inline/multi-line naked JSON blobs with known field names
	cleaned = cleaned.replace(
		new RegExp(`\\{\\s*"(?:${FIELD_ALT})"[\\s\\S]*?\\}(?:\\s*\\})*`, "g"),
		"",
	);
	return cleaned.trim();
}

/** Extract ```spotlight-arena-data JSON block from synthesis text */
function extractArenaAnalysis(
	textParts: string[],
): ArenaAnalysis | null {
	for (const text of textParts) {
		const match = text.match(
			/```spotlight-arena-data\s*\n([\s\S]*?)```/,
		);
		if (match?.[1]) {
			try {
				const parsed = JSON.parse(match[1]);
				return parsed.arena_analysis || null;
			} catch {
				// ignore parse errors
			}
		}
	}
	return null;
}

/** Extract convergence model_scores from arena-data or text */
function extractModelScores(
	textParts: string[],
): Record<string, ModelScore> | null {
	for (const text of textParts) {
		const match = text.match(
			/```spotlight-arena-data\s*\n([\s\S]*?)```/,
		);
		if (match?.[1]) {
			try {
				const parsed = JSON.parse(match[1]);
				if (parsed.model_scores) return parsed.model_scores;
			} catch {
				// ignore
			}
		}
	}
	return null;
}


// ============================================================================
// Sub-components
// ============================================================================

const ScoreBar: FC<{
	label: string;
	value: number;
	colorClass: string;
	rationale?: string;
	compact?: boolean;
	animate?: boolean;
	isEvaluating?: boolean;
	isComplete?: boolean;
}> = ({ label, value, colorClass, rationale, compact = false, animate = true, isEvaluating = false, isComplete = false }) => {
	const barRef = useRef<HTMLDivElement>(null);
	const [width, setWidth] = useState(animate ? 0 : value);

	useEffect(() => {
		if (!animate) {
			setWidth(value);
			return;
		}
		// Animate bar from 0 to value
		const timer = setTimeout(() => setWidth(value), 50);
		return () => clearTimeout(timer);
	}, [value, animate]);

	return (
		<div className={cn("flex items-center", compact ? "gap-1" : "gap-2")}>
			<span
				className={cn(
					"text-muted-foreground shrink-0 capitalize flex items-center",
					compact ? "text-[10px] w-16" : "text-xs w-20",
				)}
			>
				{label}
				{rationale && (
					<Tooltip>
						<TooltipTrigger asChild>
							<button
								type="button"
								className="ml-0.5 shrink-0 text-muted-foreground/60 hover:text-foreground transition-colors"
								aria-label={`Motivering för ${label}`}
							>
								<InfoIcon className={compact ? "size-2.5" : "size-3"} />
							</button>
						</TooltipTrigger>
						<TooltipContent side="top" className="max-w-xs pointer-events-auto">
							<p className="text-xs">{rationale}</p>
						</TooltipContent>
					</Tooltip>
				)}
			</span>
			<div
				className={cn(
					"flex-1 rounded-full bg-muted/50 overflow-hidden",
					compact ? "h-1.5" : "h-2",
				)}
			>
				<div
					ref={barRef}
					className={cn(
						"h-full rounded-full transition-all duration-1000 ease-out",
						colorClass,
					)}
					style={{ width: `${width}%` }}
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
			{/* Spinner while evaluating, checkmark when complete */}
			{isEvaluating && !isComplete && (
				<LoaderCircleIcon
					className={cn(
						"shrink-0 animate-spin text-muted-foreground/60",
						compact ? "size-2.5" : "size-3",
					)}
				/>
			)}
			{isComplete && (
				<CheckCircle2Icon
					className={cn(
						"shrink-0 text-emerald-500",
						compact ? "size-2.5" : "size-3",
					)}
				/>
			)}
		</div>
	);
};

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

const PhaseIndicator: FC<{ currentPhase: ArenaPhase }> = ({
	currentPhase,
}) => {
	const currentIdx = PHASE_LABELS.findIndex((p) => p.id === currentPhase);
	return (
		<div className="flex gap-1">
			{PHASE_LABELS.map(({ id, label }, idx) => (
				<div
					key={id}
					className={cn(
						"rounded-full px-2.5 py-0.5 text-[10px] font-medium transition-colors duration-500",
						idx === currentIdx
							? "bg-primary text-primary-foreground"
							: idx < currentIdx
								? "bg-primary/10 text-primary"
								: "bg-muted text-muted-foreground",
					)}
				>
					{label}
					{idx === currentIdx && (
						<span className="ml-1 inline-block size-1 rounded-full bg-current animate-pulse" />
					)}
				</div>
			))}
		</div>
	);
};

// ── Metadata badges ─────────────────────────────────────────────────────────

const MetaBadges: FC<{ meta: ModelMeta; compact?: boolean }> = ({
	meta,
	compact = false,
}) => {
	const latency = formatLatency(meta.latencyMs);
	const tokens = formatTokens(meta);
	const co2 = estimateCo2(meta);

	if (!latency && !tokens) return null;

	return (
		<div className={cn("flex flex-wrap gap-1.5", compact ? "mt-1" : "mt-2")}>
			{latency && (
				<Badge
					variant="secondary"
					className={cn("gap-1", compact ? "text-[9px] px-1.5 py-0" : "text-[10px]")}
				>
					<ClockIcon className="size-2.5" />
					{latency}
				</Badge>
			)}
			{tokens && (
				<Badge
					variant="secondary"
					className={cn("gap-1", compact ? "text-[9px] px-1.5 py-0" : "text-[10px]")}
				>
					<CoinsIcon className="size-2.5" />
					{tokens}
				</Badge>
			)}
			{co2 && (
				<Badge
					variant="secondary"
					className={cn("gap-1", compact ? "text-[9px] px-1.5 py-0" : "text-[10px]")}
				>
					<LeafIcon className="size-2.5" />
					CO₂ {meta.tokens.isEstimated ? "≈" : ""}
					{formatNum(co2.co2g)}g
				</Badge>
			)}
			{co2 && !compact && (
				<Badge
					variant="secondary"
					className="gap-1 text-[10px]"
				>
					<ZapIcon className="size-2.5" />
					{formatNum(co2.energyWh)} Wh
				</Badge>
			)}
		</div>
	);
};

// ── Pod debug panel (power-user toggle) ─────────────────────────────────────

const CRITERION_LABELS: Record<keyof ModelScore, string> = {
	relevans: "Relevans",
	djup: "Djup",
	klarhet: "Klarhet",
	korrekthet: "Korrekthet",
};

const PodDebugPanel: FC<{
	podInfo: Partial<Record<keyof ModelScore, CriterionPodMeta>>;
	compact?: boolean;
}> = ({ podInfo, compact = false }) => {
	const [open, setOpen] = useState(false);
	const entries = SCORE_KEYS.filter((k) => podInfo[k]);

	if (entries.length === 0) return null;

	return (
		<Collapsible open={open} onOpenChange={setOpen}>
			<CollapsibleTrigger asChild>
				<Button
					variant="ghost"
					size="sm"
					className={cn(
						"w-full justify-center text-muted-foreground/50 hover:text-muted-foreground",
						compact ? "mt-0.5 text-[9px] h-5" : "mt-1 text-[10px] h-6",
					)}
				>
					<span>{open ? "Dölj pod-info" : "Pod-info"}</span>
					<ChevronDownIcon
						className={cn(
							"ml-1 transition-transform duration-200",
							compact ? "size-2.5" : "size-3",
							open && "rotate-180",
						)}
					/>
				</Button>
			</CollapsibleTrigger>
			<CollapsibleContent>
				<div className="mt-1 rounded-md border border-border/40 bg-muted/20 p-2 space-y-1">
					{entries.map((key) => {
						const meta = podInfo[key];
						if (!meta) return null;
						const latencyStr = meta.latency_ms >= 1000
							? `${(meta.latency_ms / 1000).toFixed(1)}s`
							: `${meta.latency_ms}ms`;
						return (
							<div
								key={key}
								className="flex items-center justify-between text-[10px] text-muted-foreground font-mono"
							>
								<span>
									<CheckCircle2Icon className="inline size-2.5 text-emerald-500 mr-1" />
									{CRITERION_LABELS[key]} klar
								</span>
								<span className="tabular-nums">
									{meta.pod_id.replace("pod-crit-", "")} ({latencyStr})
								</span>
							</div>
						);
					})}
				</div>
			</CollapsibleContent>
		</Collapsible>
	);
};

// ── Expandable response view ────────────────────────────────────────────────

const ExpandableResponse: FC<{
	model: RankedModel;
	compact?: boolean;
}> = ({ model, compact = false }) => {
	const [open, setOpen] = useState(false);

	if (!model.fullResponse && !model.summary) return null;

	return (
		<Collapsible open={open} onOpenChange={setOpen}>
			<CollapsibleTrigger asChild>
				<Button
					variant="ghost"
					size="sm"
					className={cn(
						"w-full justify-center text-muted-foreground",
						compact ? "mt-1 text-[10px] h-6" : "mt-2 text-xs",
					)}
				>
					<span>{open ? "Dölj svar" : "Visa svar"}</span>
					<ChevronDownIcon
						className={cn(
							"ml-1 transition-transform duration-200",
							compact ? "size-3" : "size-4",
							open && "rotate-180",
						)}
					/>
				</Button>
			</CollapsibleTrigger>
			<CollapsibleContent>
				<div className="mt-2 rounded-lg border border-border/60 bg-background/60 p-3 space-y-2">
					{/* Metadata row */}
					{(model.meta.model || model.meta.provider) && (
						<div className="grid gap-1 text-[10px] text-muted-foreground">
							{model.meta.model && (
								<div className="flex justify-between">
									<span>Modell</span>
									<span className="text-foreground">{model.meta.model}</span>
								</div>
							)}
							{model.meta.provider && (
								<div className="flex justify-between">
									<span>Provider</span>
									<span className="text-foreground">{model.meta.provider}</span>
								</div>
							)}
							{model.meta.modelString && (
								<div className="flex justify-between">
									<span>Model string</span>
									<span className="text-foreground font-mono text-[9px]">
										{model.meta.modelString}
									</span>
								</div>
							)}
						</div>
					)}
					{/* Full response */}
					<div className="whitespace-pre-wrap text-sm text-foreground leading-relaxed max-h-96 overflow-y-auto">
						{model.fullResponse || model.summary}
					</div>
					{model.meta.truncated && (
						<p className="text-[10px] text-amber-600 dark:text-amber-400">
							Svaret trunkerades (max 12 000 tecken)
						</p>
					)}
				</div>
			</CollapsibleContent>
		</Collapsible>
	);
};

// ── Duel card (top-2 models) ────────────────────────────────────────────────

const DuelCard: FC<{ model: RankedModel; delay?: number }> = ({
	model,
	delay = 0,
}) => {
	const liveScores = useContext(LiveCriterionContext);
	const livePods = useContext(LiveCriterionPodContext);

	// Determine per-criterion evaluation state from live SSE data
	const domainLive = liveScores[model.domain];
	const domainPods = livePods[model.domain] || model.criterionPodInfo;
	// "Criteria finalized" = tool result has criterion_scores (model_complete arrived)
	// or all 4 live criterion scores have arrived.
	const hasFinalScoresFromResult = Object.keys(model.criterionPodInfo).length === 4
		|| (model.hasRealScores && !domainLive);
	const allLiveDone = domainLive
		? (domainLive.relevans != null && domainLive.djup != null && domainLive.klarhet != null && domainLive.korrekthet != null)
		: false;
	const criteriaFinalized = hasFinalScoresFromResult || allLiveDone;
	// Show spinners when model has a response but criteria aren't all done yet
	const isEvaluating = model.status === "complete" && !criteriaFinalized;

	if (model.status === "running") {
		return (
			<Card className="flex-1 animate-pulse">
				<CardContent className="p-4 space-y-3">
					<div className="flex items-center gap-2">
						<div className="size-10 rounded-lg bg-muted" />
						<div className="space-y-1.5 flex-1">
							<div className="h-4 w-1/3 rounded bg-muted" />
							<div className="h-3 w-1/4 rounded bg-muted" />
						</div>
					</div>
					<div className="h-2.5 w-full rounded bg-muted" />
					<div className="h-2.5 w-full rounded bg-muted" />
					<div className="h-2.5 w-3/4 rounded bg-muted" />
					<div className="h-2.5 w-full rounded bg-muted" />
				</CardContent>
			</Card>
		);
	}

	if (model.status === "error") {
		return (
			<motion.div
				initial={{ opacity: 0, y: 12 }}
				animate={{ opacity: 1, y: 0 }}
				transition={{ duration: 0.4, delay }}
				className="flex-1"
			>
				<Card className="h-full border-destructive/20 bg-destructive/5">
					<CardContent className="p-4">
						<div className="flex items-center gap-2 mb-2">
							<span className="text-lg font-bold text-muted-foreground">
								#{model.rank}
							</span>
							<ModelLogo toolName={model.toolName} />
							<span className="font-semibold text-sm">
								{model.displayName}
							</span>
						</div>
						<p className="text-xs text-destructive">
							{model.errorMessage || "Modellen svarade inte"}
						</p>
					</CardContent>
				</Card>
			</motion.div>
		);
	}

	return (
		<motion.div
			initial={{ opacity: 0, y: 16 }}
			animate={{ opacity: 1, y: 0 }}
			transition={{ duration: 0.5, delay }}
			className="flex-1"
		>
			<Card className="h-full">
				<CardContent className="p-4">
					{/* Header: rank + logo + name + source badge */}
					<div className="flex items-center gap-2 mb-1">
						<span className="text-lg font-bold text-primary">
							#{model.rank}
						</span>
						<ModelLogo toolName={model.toolName} />
						<div className="flex-1 min-w-0">
							<span className="font-semibold text-sm">
								{model.displayName}
							</span>
							{model.meta.source && (
								<Badge
									variant="secondary"
									className="ml-2 text-[9px] px-1.5 py-0"
								>
									{model.meta.source}
								</Badge>
							)}
						</div>
					</div>

					{/* Meta badges: latency, tokens, CO2 */}
					<MetaBadges meta={model.meta} />

					{/* Score bars */}
					<div className="space-y-2 mt-3">
						{SCORE_KEYS.map((key) => (
							<ScoreBar
								key={key}
								label={key}
								value={model.scores[key]}
								colorClass={SCORE_COLORS[key]}
								rationale={model.reasonings[key]}
								animate={model.hasRealScores}
								isEvaluating={isEvaluating}
								isComplete={domainLive?.[key] != null || criteriaFinalized}
							/>
						))}
					</div>

					{/* Evaluating status */}
					{isEvaluating && (
						<div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground">
							<LoaderCircleIcon className="size-3 animate-spin" />
							<span>
								Utvärderar{" "}
								{SCORE_KEYS.filter((k) => domainLive?.[k] == null).map((k) => k).join(", ") || "..."}
							</span>
						</div>
					)}

					{/* Weighted score + raw total */}
					{!isEvaluating && (
						<>
							<div className="mt-2 flex items-center justify-between text-xs">
								<span className="text-muted-foreground">Viktat</span>
								<span className="font-bold tabular-nums text-primary">
									{model.weightedScore}/100
								</span>
							</div>
							<div className="flex items-center justify-between text-[10px]">
								<span className="text-muted-foreground">Totalpoäng</span>
								<span className="tabular-nums text-muted-foreground">
									{model.totalScore}/400
								</span>
							</div>
						</>
					)}

					{/* Pod debug panel */}
					<PodDebugPanel podInfo={domainPods} />

					{/* Expandable full response */}
					<ExpandableResponse model={model} />
				</CardContent>
			</Card>
		</motion.div>
	);
};

// ── VS duel layout ──────────────────────────────────────────────────────────

const VsDuel: FC<{ first: RankedModel; second: RankedModel }> = ({
	first,
	second,
}) => (
	<div className="grid grid-cols-[1fr_auto_1fr] gap-3 items-stretch">
		<DuelCard model={first} delay={0.1} />
		<div className="flex items-center justify-center">
			<motion.div
				initial={{ scale: 0, opacity: 0 }}
				animate={{ scale: 1, opacity: 1 }}
				transition={{ duration: 0.4, delay: 0.3, type: "spring" }}
				className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-sm"
			>
				VS
			</motion.div>
		</div>
		<DuelCard model={second} delay={0.2} />
	</div>
);

// ── Runner-up card (rank 3+) ────────────────────────────────────────────────

const RunnerUpCard: FC<{
	model: RankedModel;
	delay?: number;
}> = ({ model, delay = 0 }) => {
	const liveScores = useContext(LiveCriterionContext);
	const livePods = useContext(LiveCriterionPodContext);

	const domainLive = liveScores[model.domain];
	const domainPods = livePods[model.domain] || model.criterionPodInfo;
	const hasFinalScoresFromResult2 = Object.keys(model.criterionPodInfo).length === 4
		|| (model.hasRealScores && !domainLive);
	const allLiveDone2 = domainLive
		? (domainLive.relevans != null && domainLive.djup != null && domainLive.klarhet != null && domainLive.korrekthet != null)
		: false;
	const criteriaFinalized2 = hasFinalScoresFromResult2 || allLiveDone2;
	const isEvaluating = model.status === "complete" && !criteriaFinalized2;

	if (model.status === "running") {
		return (
			<Card className="animate-pulse">
				<CardContent className="p-3 space-y-2">
					<div className="flex items-center gap-1.5">
						<div className="size-7 rounded-lg bg-muted" />
						<div className="h-3 w-1/2 rounded bg-muted" />
					</div>
					<div className="h-1.5 w-full rounded bg-muted" />
					<div className="h-1.5 w-full rounded bg-muted" />
				</CardContent>
			</Card>
		);
	}

	if (model.status === "error") {
		return (
			<motion.div
				initial={{ opacity: 0, scale: 0.95 }}
				animate={{ opacity: 1, scale: 1 }}
				transition={{ duration: 0.3, delay }}
			>
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
			</motion.div>
		);
	}

	return (
		<motion.div
			initial={{ opacity: 0, y: 12 }}
			animate={{ opacity: 1, y: 0 }}
			transition={{ duration: 0.4, delay }}
		>
			<Card>
				<CardContent className="p-3">
					<div className="flex items-center gap-1.5 mb-1">
						<span className="text-sm font-bold text-primary">
							#{model.rank}
						</span>
						<ModelLogo toolName={model.toolName} size="sm" />
						<span className="text-xs font-semibold">{model.displayName}</span>
						{model.meta.source && (
							<Badge
								variant="secondary"
								className="text-[8px] px-1 py-0 ml-auto"
							>
								{model.meta.source}
							</Badge>
						)}
					</div>
					<MetaBadges meta={model.meta} compact />
					<div className="space-y-1 mt-2">
						{SCORE_KEYS.map((key) => (
							<ScoreBar
								key={key}
								label={key}
								value={model.scores[key]}
								colorClass={SCORE_COLORS[key]}
								rationale={model.reasonings[key]}
								compact
								animate={model.hasRealScores}
								isEvaluating={isEvaluating}
								isComplete={domainLive?.[key] != null || criteriaFinalized2}
							/>
						))}
					</div>
					{isEvaluating ? (
						<div className="mt-1 flex items-center gap-1 text-[9px] text-muted-foreground">
							<LoaderCircleIcon className="size-2.5 animate-spin" />
							<span>Utvärderar...</span>
						</div>
					) : (
						<div className="mt-1.5 flex items-center justify-between text-[10px]">
							<span className="text-muted-foreground">Viktat</span>
							<span className="font-bold tabular-nums text-primary">
								{model.weightedScore}/100
							</span>
						</div>
					)}
					<PodDebugPanel podInfo={domainPods} compact />
					<ExpandableResponse model={model} compact />
				</CardContent>
			</Card>
		</motion.div>
	);
};

// ── Convergence summary ─────────────────────────────────────────────────────

const ConvergenceSummary: FC<{
	models: RankedModel[];
	analysis: ArenaAnalysis | null;
}> = ({ models, analysis }) => {
	const completed = models.filter((m) => m.status === "complete");
	if (completed.length < 2) return null;

	return (
		<motion.div
			initial={{ opacity: 0, y: 16 }}
			animate={{ opacity: 1, y: 0 }}
			transition={{ duration: 0.5, delay: 0.5 }}
		>
			<Card className="bg-muted/30 border-border/40">
				<CardContent className="p-4 space-y-3">
					<h4 className="text-sm font-semibold">Sammanfattande bedömning</h4>

					{analysis ? (
						<>
							{/* Winner rationale */}
							{analysis.winner_rationale && (
								<p className="text-xs text-foreground leading-relaxed">
									{analysis.winner_rationale}
								</p>
							)}

							{/* Consensus */}
							{analysis.consensus.length > 0 && (
								<div>
									<p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
										Konsensus
									</p>
									<ul className="space-y-0.5">
										{analysis.consensus.map((item, i) => (
											<li
												key={`c-${i}`}
												className="text-xs text-foreground leading-relaxed flex gap-1.5"
											>
												<span className="text-emerald-500 shrink-0">
													+
												</span>
												{item}
											</li>
										))}
									</ul>
								</div>
							)}

							{/* Disagreements */}
							{analysis.disagreements.length > 0 && (
								<div>
									<p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
										Meningsskiljaktigheter
									</p>
									<div className="space-y-2">
										{analysis.disagreements.map((d, i) => (
											<div
												key={`d-${i}`}
												className="rounded-lg border border-border/40 p-2 text-xs"
											>
												<p className="font-medium text-foreground mb-1">
													{d.topic}
												</p>
												<div className="space-y-0.5 text-muted-foreground">
													{Object.entries(d.sides).map(
														([models, stance]) => (
															<p key={models}>
																<strong className="text-foreground">
																	{models}
																</strong>
																: {stance}
															</p>
														),
													)}
												</div>
												{d.verdict && (
													<p className="mt-1 text-[10px] text-primary font-medium">
														Bedömning: {d.verdict}
													</p>
												)}
											</div>
										))}
									</div>
								</div>
							)}

							{/* Unique contributions */}
							{analysis.unique_contributions.length > 0 && (
								<div>
									<p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
										Unika bidrag
									</p>
									<div className="space-y-1">
										{analysis.unique_contributions.map((uc, i) => (
											<div
												key={`u-${i}`}
												className="flex gap-2 text-xs"
											>
												<strong className="text-foreground shrink-0">
													{uc.model}:
												</strong>
												<span className="text-muted-foreground">
													{uc.insight}
												</span>
											</div>
										))}
									</div>
								</div>
							)}

							{/* Reliability */}
							{analysis.reliability_notes && (
								<p className="text-[10px] text-muted-foreground italic border-t border-border/40 pt-2">
									{analysis.reliability_notes}
								</p>
							)}
						</>
					) : (
						/* Fallback when no structured analysis is available */
						<p className="text-xs text-muted-foreground leading-relaxed">
							<strong className="text-foreground">
								{completed[0].displayName}
							</strong>{" "}
							(viktat: {completed[0].weightedScore}/100) och{" "}
							<strong className="text-foreground">
								{completed[1].displayName}
							</strong>{" "}
							(viktat: {completed[1].weightedScore}/100){" "}
							toppar rankingen. Klicka{" "}
							<em>Visa svar</em> på varje modell för att se fullständiga svar
							och jämföra själv.
						</p>
					)}
				</CardContent>
			</Card>
		</motion.div>
	);
};

// ============================================================================
// Main layout component
// ============================================================================

export const SpotlightArenaLayout: FC = () => {
	const messageContent = useAssistantState(({ message }) => message?.content);
	const isStreaming = useAssistantState(
		({ thread, message }) => thread.isRunning && (message?.isLast ?? false),
	);

	// Live criterion scores from SSE events (partial, before tool completion)
	const liveCriterionScores = useContext(LiveCriterionContext);

	// Track previously seen completed count for stagger animation
	const prevCompletedRef = useRef(0);

	// Extract text parts to find arena analysis
	const textParts = useMemo(() => {
		if (!Array.isArray(messageContent)) return [];
		return messageContent
			.filter(
				(part: { type: string; text?: string }) =>
					part.type === "text" && typeof part.text === "string",
			)
			.map((part: { text: string }) => part.text);
	}, [messageContent]);

	// Sanitized text parts: strip arena-data blocks and leaked JSON
	// so they don't appear in the rendered markdown
	const cleanTextParts = useMemo(
		() => textParts.map(sanitizeSynthesisText).filter(Boolean),
		[textParts],
	);

	const arenaAnalysis = useMemo(
		() => extractArenaAnalysis(textParts),
		[textParts],
	);

	const externalModelScores = useMemo(
		() => extractModelScores(textParts),
		[textParts],
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
				args?: { query?: string };
				result?: unknown;
				status?: { type: string };
			}) => {
				const result = parseResult(part.result);
				const isRunning = part.status?.type === "running";
				const isError = !isRunning && (!result || result.status === "error");
				const responseText = String(result?.response || "");
				const queryText = String(part.args?.query || "");

				// Score priority:
				// 1. criterion_scores from tool result (final real LLM evaluation)
				// 2. live SSE criterion scores — partial OK, missing criteria show as 0
				// 3. model_scores from convergence (LLM merge evaluation)
				// 4. Heuristic fallback (only when no live data at all)
				const domain = TOOL_TO_DOMAIN[part.toolName] || part.toolName;
				const criterionScores = result?.criterion_scores as
					| ModelScore
					| undefined;
				const liveScores = liveCriterionScores[domain];
				const hasAnyLive = !!liveScores && Object.keys(liveScores).length > 0;
				// Merge partial live scores with 0 for missing criteria (progressive rendering)
				const partialLiveScores: ModelScore | undefined = hasAnyLive
					? {
						relevans: liveScores.relevans ?? 0,
						djup: liveScores.djup ?? 0,
						klarhet: liveScores.klarhet ?? 0,
						korrekthet: liveScores.korrekthet ?? 0,
					}
					: undefined;
				const convergenceScores = externalModelScores?.[domain] as
					| ModelScore
					| undefined;
				// When no real scores are available yet (evaluation pending), show zeros
				// instead of heuristic fallback – avoids fake scores that jump on update.
				const ZERO_SCORES: ModelScore = { relevans: 0, djup: 0, klarhet: 0, korrekthet: 0 };
				const scores =
					criterionScores ||
					partialLiveScores ||
					convergenceScores ||
					ZERO_SCORES;
				const hasReal = !!(criterionScores || hasAnyLive || convergenceScores);

				// Extract criterion reasonings (motivations for each score)
				const reasonings: ModelReasonings =
					(result?.criterion_reasonings as ModelReasonings) || {};

				// Extract per-criterion pod info from tool result
				const criterionPodInfo: Partial<Record<keyof ModelScore, CriterionPodMeta>> =
					(result?.criterion_pod_info as Partial<Record<keyof ModelScore, CriterionPodMeta>>) || {};

				return {
					toolName: part.toolName,
					displayName:
						(result?.model_display_name as string) ||
						MODEL_DISPLAY[part.toolName] ||
						part.toolName,
					domain,
					rank: 0,
					scores,
					reasonings,
					criterionPodInfo,
					hasRealScores: hasReal,
					totalScore: totalScore(scores),
					weightedScore: weightedScore(scores),
					meta: extractMeta(result, responseText, queryText),
					summary: String(result?.summary || ""),
					fullResponse: responseText,
					status: isRunning ? "running" : isError ? "error" : "complete",
					errorMessage:
						typeof result?.error === "string"
							? (result.error as string)
							: undefined,
				};
			},
		);

		// Sort: complete first, then by weighted score descending
		// Weighted score uses confidence-weighted convergence:
		// korrekthet=35%, relevans=25%, djup=20%, klarhet=20%
		parsed.sort((a, b) => {
			if (a.status === "complete" && b.status !== "complete") return -1;
			if (a.status !== "complete" && b.status === "complete") return 1;
			return b.weightedScore - a.weightedScore;
		});

		parsed.forEach((m, i) => {
			m.rank = i + 1;
		});

		return parsed;
	}, [messageContent, externalModelScores, liveCriterionScores]);

	// Track completed count for determining new arrivals
	const completedCount = rankedModels.filter(
		(m) => m.status === "complete",
	).length;
	useEffect(() => {
		prevCompletedRef.current = completedCount;
	}, [completedCount]);

	const phase: ArenaPhase = useMemo(() => {
		if (rankedModels.length === 0) return "fanout";
		const someRunning = rankedModels.some((m) => m.status === "running");
		if (someRunning) return "fanout";
		// All done, check if synthesis has arena analysis yet
		if (arenaAnalysis) return "rankar";
		if (isStreaming) return "analyserar";
		// Results in but no analysis yet → granskning
		return "granskning";
	}, [rankedModels, isStreaming, arenaAnalysis]);

	const top2 = rankedModels.slice(0, 2);
	const runnerUps = rankedModels.slice(2);

	if (rankedModels.length === 0) return null;

	return (
		<div className="space-y-4 px-2 mb-4">
			{/* Header */}
			<motion.div
				initial={{ opacity: 0, y: -8 }}
				animate={{ opacity: 1, y: 0 }}
				transition={{ duration: 0.4 }}
				className="flex flex-wrap items-center justify-between gap-2"
			>
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
			</motion.div>

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
					{runnerUps.map((model, i) => (
						<RunnerUpCard
							key={model.toolName}
							model={model}
							delay={0.3 + i * 0.08}
						/>
					))}
				</div>
			)}

			{/* Convergence summary */}
			{phase === "rankar" && (
				<ConvergenceSummary
					models={rankedModels}
					analysis={arenaAnalysis}
				/>
			)}
		</div>
	);
};
