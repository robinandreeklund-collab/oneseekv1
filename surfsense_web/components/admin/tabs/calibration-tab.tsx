"use client";

/**
 * CalibrationTab — Flik 2: Kalibrering
 *
 * Fas-panel ÖVERST visar live routing-fas (Shadow → Tool gate → Agent auto → Adaptive → Intent finetune).
 *
 * Guidat 3-stegsflöde:
 *   Steg 1: Metadata Audit (egen audit-sektion med 3-layer accuracy + kollisionsrapport)
 *   Steg 2: Eval (generering + agentval eval + API input eval + resultat + diff-vy)
 *   Steg 3: Auto-optimering (auto-loop med holdout + lifecycle-promotion)
 *
 * Extracted from tool-settings-page.tsx (5283 lines — DEPRECATED)
 */

import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAtomValue } from "jotai";
import { stringify as stringifyYaml } from "yaml";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type {
	MetadataCatalogAuditRunResponse,
	MetadataCatalogSeparationResponse,
	ToolAutoLoopDraftPromptItem,
	ToolApiInputEvaluationJobStatusResponse,
	ToolApiInputEvaluationResponse,
	ToolApiInputEvaluationTestCase,
	ToolEvaluationJobStatusResponse,
	ToolEvaluationRunComparison,
	ToolEvaluationResponse,
	ToolEvaluationTestCase,
	ToolMetadataItem,
	ToolMetadataUpdateItem,
	ToolRetrievalTuning,
} from "@/contracts/types/admin-tool-settings.types";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";
import { adminToolLifecycleApiService } from "@/lib/apis/admin-tool-lifecycle-api.service";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { AlertCircle, Download, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { LifecycleBadge } from "@/components/admin/shared/lifecycle-badge";
import { SuggestionDiffView, type SuggestionDiffItem } from "@/components/admin/shared/suggestion-diff-view";

// ---------------------------------------------------------------------------
// Helper types
// ---------------------------------------------------------------------------

type EvalExportFormat = "json" | "yaml";
type LiveRoutingPhase =
	| "shadow"
	| "tool_gate"
	| "agent_auto"
	| "adaptive"
	| "intent_finetune";
type NumericRetrievalTuningField = {
	[K in keyof ToolRetrievalTuning]: ToolRetrievalTuning[K] extends number ? K : never;
}[keyof ToolRetrievalTuning];
type ExportableEvalJobStatus =
	| ToolEvaluationJobStatusResponse
	| ToolApiInputEvaluationJobStatusResponse;

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

function downloadTextFile(content: string, fileName: string, mimeType: string) {
	const blob = new Blob([content], { type: mimeType });
	const blobUrl = URL.createObjectURL(blob);
	const anchor = document.createElement("a");
	anchor.href = blobUrl;
	anchor.download = fileName;
	document.body.appendChild(anchor);
	anchor.click();
	anchor.remove();
	URL.revokeObjectURL(blobUrl);
}

function buildEvalExportFileName(
	evalKind: "tool_selection" | "api_input",
	jobId: string,
	format: EvalExportFormat
) {
	const normalizedJob = String(jobId || "unknown")
		.replace(/[^a-zA-Z0-9_-]+/g, "")
		.slice(0, 14);
	const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
	const prefix = evalKind === "api_input" ? "api-input-eval-run" : "tool-eval-run";
	return `${prefix}-${normalizedJob || "unknown"}-${timestamp}.${format}`;
}

function toUpdateItem(tool: ToolMetadataItem | ToolMetadataUpdateItem): ToolMetadataUpdateItem {
	return {
		tool_id: tool.tool_id,
		name: tool.name,
		description: tool.description,
		keywords: [...tool.keywords],
		example_queries: [...tool.example_queries],
		category: tool.category,
		base_path: tool.base_path ?? null,
		main_identifier: tool.main_identifier ?? "",
		core_activity: tool.core_activity ?? "",
		unique_scope: tool.unique_scope ?? "",
		geographic_scope: tool.geographic_scope ?? "",
		excludes: [...(tool.excludes ?? [])],
	};
}

function isEqualTool(left: ToolMetadataUpdateItem, right: ToolMetadataUpdateItem) {
	return JSON.stringify(left) === JSON.stringify(right);
}

function isEqualTuning(left: ToolRetrievalTuning, right: ToolRetrievalTuning) {
	return JSON.stringify(left) === JSON.stringify(right);
}

function formatPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	return `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	const sign = value > 0 ? "+" : "";
	return `${sign}${(value * 100).toFixed(1)}%`;
}

function formatDifficultyLabel(value: string | null | undefined) {
	const normalized = String(value ?? "").trim().toLowerCase();
	if (!normalized) return "Okänd";
	if (normalized === "lätt" || normalized === "latt" || normalized === "easy") return "Lätt";
	if (normalized === "medel" || normalized === "medium") return "Medel";
	if (normalized === "svår" || normalized === "svar" || normalized === "hard") return "Svår";
	return value ?? "Okänd";
}

function formatAutoLoopStopReason(reason: string | null | undefined) {
	const normalized = String(reason ?? "").trim().toLowerCase();
	if (!normalized) return "Okänd stop-orsak";
	if (normalized === "target_reached") return "Målnivå uppnådd";
	if (normalized === "no_improvement") return "Avbruten p.g.a. utebliven förbättring";
	if (normalized === "max_iterations_reached") return "Max antal iterationer uppnåddes";
	return reason ?? "Okänd stop-orsak";
}

function buildFailureReasons(result: Record<string, unknown>): string[] {
	const reasons: string[] = [];
	if (result.passed_intent === false) reasons.push("Intent mismatch");
	if (result.passed_route === false) reasons.push("Route mismatch");
	if (result.passed_sub_route === false) reasons.push("Sub-route mismatch");
	if (result.passed_agent === false) reasons.push("Agent mismatch");
	if (result.passed_plan === false) reasons.push("Plankrav ej uppfyllda");
	if (result.passed_tool === false) reasons.push("Tool mismatch");
	if (result.passed_api_input === false) reasons.push("API-input mismatch");
	if (result.supervisor_review_passed === false)
		reasons.push("Supervisor-spår behöver förbättras");
	return reasons;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DifficultyBreakdown({
	title,
	items,
}: {
	title: string;
	items: Array<{
		difficulty: string;
		total_tests: number;
		passed_tests: number;
		success_rate: number;
		gated_success_rate?: number | null;
	}>;
}) {
	if (!items.length) return null;
	return (
		<div className="rounded border p-3 space-y-2">
			<p className="text-sm font-medium">{title}</p>
			<div className="flex flex-wrap gap-2">
				{items.map((item) => (
					<Badge key={`${title}-${item.difficulty}`} variant="outline">
						{formatDifficultyLabel(item.difficulty)}: {item.passed_tests}/{item.total_tests} (
						{(item.success_rate * 100).toFixed(1)}%)
						{item.gated_success_rate == null
							? ""
							: ` · gated ${(item.gated_success_rate * 100).toFixed(1)}%`}
					</Badge>
				))}
			</div>
		</div>
	);
}

function ComparisonInsights({
	title,
	comparison,
}: {
	title: string;
	comparison: ToolEvaluationRunComparison | null | undefined;
}) {
	if (!comparison) return null;
	const trend = comparison.trend;
	const trendVariant =
		trend === "degraded" ? "destructive" : trend === "improved" ? "default" : "outline";
	const trendLabel =
		trend === "degraded"
			? "Sämre än föregående"
			: trend === "improved"
				? "Bättre än föregående"
				: trend === "unchanged"
					? "Oförändrat"
					: "Första jämförelse";
	const metricDeltas = (comparison.metric_deltas ?? [])
		.filter((item) => typeof item.delta === "number")
		.sort((left, right) => (left.delta ?? 0) - (right.delta ?? 0))
		.slice(0, 4);
	return (
		<div className="rounded border p-3 space-y-2">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<p className="text-sm font-medium">{title}</p>
				<Badge variant={trendVariant}>{trendLabel}</Badge>
			</div>
			<p className="text-xs text-muted-foreground">
				Nu: {formatPercent(comparison.current_success_rate)} · Föregående:{" "}
				{formatPercent(comparison.previous_success_rate)} · Delta:{" "}
				{formatSignedPercent(comparison.success_rate_delta)}
			</p>
			{comparison.previous_run_at && (
				<p className="text-xs text-muted-foreground">
					Jämfört med: {new Date(comparison.previous_run_at).toLocaleString("sv-SE")}
					{comparison.previous_eval_name ? ` (${comparison.previous_eval_name})` : ""}
				</p>
			)}
			{metricDeltas.length > 0 && (
				<div className="flex flex-wrap gap-2">
					{metricDeltas.map((item) => (
						<Badge
							key={`${title}-${item.metric}`}
							variant={(item.delta ?? 0) < 0 ? "destructive" : "outline"}
						>
							{item.metric}: {formatSignedPercent(item.delta)}
						</Badge>
					))}
				</div>
			)}
			{(comparison.guidance ?? []).length > 0 && (
				<ul className="list-disc pl-5 text-xs text-muted-foreground space-y-1">
					{comparison.guidance.map((line, index) => (
						<li key={`${title}-guide-${index}`}>{line}</li>
					))}
				</ul>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CalibrationTab() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const queryClient = useQueryClient();

	// --- Calibration step ---
	const [calibrationStep, setCalibrationStep] = useState<
		"audit" | "eval" | "auto"
	>("audit");

	// --- Draft metadata (needed for metadataPatch in eval) ---
	const [draftTools, setDraftTools] = useState<Record<string, ToolMetadataUpdateItem>>({});
	const [draftRetrievalTuning, setDraftRetrievalTuning] =
		useState<ToolRetrievalTuning | null>(null);

	// --- Eval state ---
	const [evalInput, setEvalInput] = useState("");
	const [showEvalJsonInput, setShowEvalJsonInput] = useState(false);
	const [useHoldoutSuite, setUseHoldoutSuite] = useState(false);
	const [holdoutInput, setHoldoutInput] = useState("");
	const [showHoldoutJsonInput, setShowHoldoutJsonInput] = useState(false);
	const [evalInputError, setEvalInputError] = useState<string | null>(null);
	const [generationMode, setGenerationMode] = useState<
		"category" | "provider" | "global_random"
	>("category");
	const [evaluationStepTab, setEvaluationStepTab] = useState<
		"all" | "guide" | "generation" | "agent_eval" | "api_input"
	>("all");
	const [generationEvalType, setGenerationEvalType] = useState<
		"tool_selection" | "api_input"
	>("tool_selection");
	const [generationProvider, setGenerationProvider] = useState("scb");
	const [generationCategory, setGenerationCategory] = useState("");
	const [generationQuestionCount, setGenerationQuestionCount] = useState(12);
	const [generationDifficultyProfile, setGenerationDifficultyProfile] = useState<
		"mixed" | "lätt" | "medel" | "svår"
	>("mixed");
	const [generationEvalName, setGenerationEvalName] = useState("");
	const [isGeneratingEvalFile, setIsGeneratingEvalFile] = useState(false);

	// --- Auto-loop state ---
	const [autoTargetSuccessRate, setAutoTargetSuccessRate] = useState(0.85);
	const [autoMaxIterations, setAutoMaxIterations] = useState(6);
	const [autoPatience, setAutoPatience] = useState(2);
	const [autoMinImprovementDelta, setAutoMinImprovementDelta] = useState(0.005);
	const [autoUseHoldoutSuite, setAutoUseHoldoutSuite] = useState(false);
	const [autoHoldoutQuestionCount, setAutoHoldoutQuestionCount] = useState(8);
	const [autoHoldoutDifficultyProfile, setAutoHoldoutDifficultyProfile] = useState<
		"mixed" | "lätt" | "medel" | "svår"
	>("mixed");
	const [isStartingAutoLoop, setIsStartingAutoLoop] = useState(false);
	const [autoLoopJobId, setAutoLoopJobId] = useState<string | null>(null);
	const [lastAutoLoopNotice, setLastAutoLoopNotice] = useState<string | null>(null);
	const [autoLoopPromptDrafts, setAutoLoopPromptDrafts] = useState<
		ToolAutoLoopDraftPromptItem[]
	>([]);
	const [isSavingAutoLoopPromptDrafts, setIsSavingAutoLoopPromptDrafts] = useState(false);

	// --- Eval library ---
	const [selectedLibraryPath, setSelectedLibraryPath] = useState("");
	const [selectedHoldoutLibraryPath, setSelectedHoldoutLibraryPath] = useState("");
	const [isLoadingLibraryFile, setIsLoadingLibraryFile] = useState(false);

	// --- Eval jobs ---
	const [isEvaluating, setIsEvaluating] = useState(false);
	const [isApiInputEvaluating, setIsApiInputEvaluating] = useState(false);
	const [retrievalLimit, setRetrievalLimit] = useState(5);
	const [useLlmSupervisorReview, setUseLlmSupervisorReview] = useState(true);
	const [includeDraftMetadata, setIncludeDraftMetadata] = useState(true);
	const [evaluationResult, setEvaluationResult] =
		useState<ToolEvaluationResponse | null>(null);
	const [apiInputEvaluationResult, setApiInputEvaluationResult] =
		useState<ToolApiInputEvaluationResponse | null>(null);
	const [evalJobId, setEvalJobId] = useState<string | null>(null);
	const [apiInputEvalJobId, setApiInputEvalJobId] = useState<string | null>(null);
	const [lastEvalJobNotice, setLastEvalJobNotice] = useState<string | null>(null);
	const [lastApiInputEvalJobNotice, setLastApiInputEvalJobNotice] = useState<string | null>(
		null
	);

	// --- Suggestion state ---
	const [selectedSuggestionIds, setSelectedSuggestionIds] = useState<Set<string>>(
		new Set()
	);
	const [selectedPromptSuggestionKeys, setSelectedPromptSuggestionKeys] = useState<
		Set<string>
	>(new Set());
	const [selectedToolPromptSuggestionKeys, setSelectedToolPromptSuggestionKeys] = useState<
		Set<string>
	>(new Set());
	const [isApplyingSuggestions, setIsApplyingSuggestions] = useState(false);
	const [isSavingSuggestions, setIsSavingSuggestions] = useState(false);
	const [isSavingPromptSuggestions, setIsSavingPromptSuggestions] = useState(false);
	const [isSavingToolPromptSuggestions, setIsSavingToolPromptSuggestions] =
		useState(false);
	const [isSavingRetrievalTuning, setIsSavingRetrievalTuning] = useState(false);

	// --- Audit state (Steg 1 — egen audit, ingen MetadataCatalogTab-wrapping) ---
	const [isRunningAudit, setIsRunningAudit] = useState(false);
	const [auditResult, setAuditResult] = useState<MetadataCatalogAuditRunResponse | null>(null);
	const [isRunningSeparation, setIsRunningSeparation] = useState(false);
	const [separationResult, setSeparationResult] = useState<MetadataCatalogSeparationResponse | null>(null);
	const [auditMaxTools, setAuditMaxTools] = useState(25);
	const [auditRetrievalLimit, setAuditRetrievalLimit] = useState(5);

	// --- Lifecycle promotion state ---
	const [isPromoting, setIsPromoting] = useState(false);

	// ---------------------------------------------------------------------------
	// Queries
	// ---------------------------------------------------------------------------

	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["admin-tool-settings"],
		queryFn: () => adminToolSettingsApiService.getToolSettings(),
		enabled: !!currentUser,
	});

	const { data: apiCategories } = useQuery({
		queryKey: ["admin-tool-api-categories", data?.search_space_id],
		queryFn: () =>
			adminToolSettingsApiService.getToolApiCategories(data?.search_space_id),
		enabled: !!currentUser && typeof data?.search_space_id === "number",
	});

	const { data: evalLibraryFiles } = useQuery({
		queryKey: ["admin-tool-eval-library-files"],
		queryFn: () => adminToolSettingsApiService.listEvalLibraryFiles(),
		enabled: !!currentUser,
	});

	const { data: evalJobStatus } = useQuery({
		queryKey: ["admin-tool-evaluation-job", evalJobId],
		queryFn: () => adminToolSettingsApiService.getToolEvaluationStatus(evalJobId as string),
		enabled: !!evalJobId,
		refetchInterval: (query) => {
			const status = query.state.data?.status;
			if (!status) return 1200;
			return status === "pending" || status === "running" ? 1200 : false;
		},
	});

	const { data: apiInputEvalJobStatus } = useQuery({
		queryKey: ["admin-tool-api-input-evaluation-job", apiInputEvalJobId],
		queryFn: () =>
			adminToolSettingsApiService.getToolApiInputEvaluationStatus(
				apiInputEvalJobId as string
			),
		enabled: !!apiInputEvalJobId,
		refetchInterval: (query) => {
			const status = query.state.data?.status;
			if (!status) return 1200;
			return status === "pending" || status === "running" ? 1200 : false;
		},
	});

	const { data: autoLoopJobStatus } = useQuery({
		queryKey: ["admin-tool-auto-loop-job", autoLoopJobId],
		queryFn: () => adminToolSettingsApiService.getToolAutoLoopStatus(autoLoopJobId as string),
		enabled: !!autoLoopJobId,
		refetchInterval: (query) => {
			const status = query.state.data?.status;
			if (!status) return 1400;
			return status === "pending" || status === "running" ? 1400 : false;
		},
	});

	const { data: lifecycleData, refetch: refetchLifecycle } = useQuery({
		queryKey: ["admin-tool-lifecycle"],
		queryFn: () => adminToolLifecycleApiService.getToolLifecycleList(),
		enabled: !!currentUser,
	});

	// ---------------------------------------------------------------------------
	// Memos
	// ---------------------------------------------------------------------------

	const apiProviders = useMemo(() => apiCategories?.providers ?? [], [apiCategories?.providers]);

	const generationCategoryOptions = useMemo(() => {
		const provider = apiProviders.find(
			(item) => item.provider_key === generationProvider
		);
		const deduped = new Map<string, { category_id: string; category_name: string }>();
		for (const item of provider?.categories ?? []) {
			if (!deduped.has(item.category_id)) {
				deduped.set(item.category_id, {
					category_id: item.category_id,
					category_name: item.category_name,
				});
			}
		}
		return Array.from(deduped.values()).sort((left, right) =>
			left.category_name.localeCompare(right.category_name, "sv")
		);
	}, [apiProviders, generationProvider]);

	const originalTools = useMemo(() => {
		const byId: Record<string, ToolMetadataItem> = {};
		for (const category of data?.categories ?? []) {
			for (const tool of category.tools) {
				byId[tool.tool_id] = tool;
			}
		}
		return byId;
	}, [data?.categories, data?.retrieval_tuning]);

	const changedToolIds = useMemo(() => {
		return Object.keys(draftTools).filter((toolId) => {
			const original = originalTools[toolId];
			if (!original) return false;
			return !isEqualTool(draftTools[toolId], toUpdateItem(original));
		});
	}, [draftTools, originalTools]);

	const metadataPatch = useMemo(() => {
		return changedToolIds.map((toolId) => draftTools[toolId]);
	}, [changedToolIds, draftTools]);

	const isEvalJobRunning =
		!!evalJobId &&
		(!evalJobStatus ||
			evalJobStatus.status === "pending" ||
			evalJobStatus.status === "running");

	const isApiInputEvalJobRunning =
		!!apiInputEvalJobId &&
		(!apiInputEvalJobStatus ||
			apiInputEvalJobStatus.status === "pending" ||
			apiInputEvalJobStatus.status === "running");

	const isAutoLoopRunning =
		!!autoLoopJobId &&
		(!autoLoopJobStatus ||
			autoLoopJobStatus.status === "pending" ||
			autoLoopJobStatus.status === "running");

	const showGuideSections = evaluationStepTab === "all" || evaluationStepTab === "guide";
	const showGenerationSections =
		evaluationStepTab === "all" || evaluationStepTab === "generation";
	const showAgentSections =
		evaluationStepTab === "all" || evaluationStepTab === "agent_eval";
	const showApiSections = evaluationStepTab === "all" || evaluationStepTab === "api_input";

	const selectedSuggestions = useMemo(
		() =>
			evaluationResult?.suggestions.filter((suggestion) =>
				selectedSuggestionIds.has(suggestion.tool_id)
			) ?? [],
		[evaluationResult?.suggestions, selectedSuggestionIds]
	);

	const suggestionDiffItems: SuggestionDiffItem[] = useMemo(() => {
		if (!evaluationResult?.suggestions) return [];
		return evaluationResult.suggestions.map((suggestion) => {
			const fields: SuggestionDiffItem["fields"] = [];
			if (suggestion.current_metadata.description !== suggestion.proposed_metadata.description) {
				fields.push({
					field: "description",
					oldValue: suggestion.current_metadata.description,
					newValue: suggestion.proposed_metadata.description,
				});
			}
			const currentKw = new Set(suggestion.current_metadata.keywords);
			const proposedKw = new Set(suggestion.proposed_metadata.keywords);
			const addedKw = suggestion.proposed_metadata.keywords.filter((k) => !currentKw.has(k));
			const removedKw = suggestion.current_metadata.keywords.filter((k) => !proposedKw.has(k));
			if (addedKw.length || removedKw.length) {
				fields.push({ field: "keywords", added: addedKw, removed: removedKw });
			}
			const currentEx = new Set(suggestion.current_metadata.example_queries ?? []);
			const proposedEx = new Set(suggestion.proposed_metadata.example_queries ?? []);
			const addedEx = (suggestion.proposed_metadata.example_queries ?? []).filter((q) => !currentEx.has(q));
			const removedEx = (suggestion.current_metadata.example_queries ?? []).filter((q) => !proposedEx.has(q));
			if (addedEx.length || removedEx.length) {
				fields.push({ field: "example_queries", added: addedEx, removed: removedEx });
			}
			return {
				toolId: suggestion.tool_id,
				toolName: suggestion.tool_id,
				fields,
				validationStatus: "ok" as const,
			};
		});
	}, [evaluationResult?.suggestions]);

	const selectedPromptSuggestions = useMemo(
		() =>
			apiInputEvaluationResult?.prompt_suggestions.filter((suggestion) =>
				selectedPromptSuggestionKeys.has(suggestion.prompt_key)
			) ?? [],
		[apiInputEvaluationResult?.prompt_suggestions, selectedPromptSuggestionKeys]
	);

	const selectedToolPromptSuggestions = useMemo(
		() =>
			evaluationResult?.prompt_suggestions.filter((suggestion) =>
				selectedToolPromptSuggestionKeys.has(suggestion.prompt_key)
			) ?? [],
		[evaluationResult?.prompt_suggestions, selectedToolPromptSuggestionKeys]
	);

	// ---------------------------------------------------------------------------
	// Effects
	// ---------------------------------------------------------------------------

	useEffect(() => {
		if (!data?.categories) return;
		const nextDrafts: Record<string, ToolMetadataUpdateItem> = {};
		for (const category of data.categories) {
			for (const tool of category.tools) {
				nextDrafts[tool.tool_id] = toUpdateItem(tool);
			}
		}
		setDraftTools(nextDrafts);
		if (data.retrieval_tuning) {
			setDraftRetrievalTuning(data.retrieval_tuning);
		}
	}, [data?.categories]);

	useEffect(() => {
		if (!apiProviders.length) return;
		if (generationMode === "global_random" && generationProvider === "all") return;
		const hasCurrent = apiProviders.some(
			(provider) => provider.provider_key === generationProvider
		);
		if (!hasCurrent) {
			setGenerationProvider(apiProviders[0].provider_key);
		}
	}, [apiProviders, generationProvider, generationMode]);

	useEffect(() => {
		if (generationMode !== "category") return;
		if (!generationCategoryOptions.length) {
			if (generationCategory) setGenerationCategory("");
			return;
		}
		const exists = generationCategoryOptions.some(
			(option) => option.category_id === generationCategory
		);
		if (!exists) {
			setGenerationCategory(generationCategoryOptions[0].category_id);
		}
	}, [generationMode, generationCategoryOptions, generationCategory]);

	useEffect(() => {
		if (!evalJobStatus || !evalJobId) return;
		if (evalJobStatus.status === "completed" && evalJobStatus.result) {
			setEvaluationResult(evalJobStatus.result);
			setSelectedSuggestionIds(new Set());
			setSelectedToolPromptSuggestionKeys(new Set());
			void queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			void queryClient.invalidateQueries({ queryKey: ["admin-tool-eval-history"] });
			const noticeKey = `${evalJobId}:completed`;
			if (lastEvalJobNotice !== noticeKey) {
				toast.success("Eval-run klar");
				setLastEvalJobNotice(noticeKey);
			}
		}
		if (evalJobStatus.status === "failed") {
			const noticeKey = `${evalJobId}:failed`;
			if (lastEvalJobNotice !== noticeKey) {
				toast.error(evalJobStatus.error || "Eval-run misslyckades");
				setLastEvalJobNotice(noticeKey);
			}
		}
	}, [evalJobStatus, evalJobId, lastEvalJobNotice, queryClient]);

	useEffect(() => {
		if (!apiInputEvalJobStatus || !apiInputEvalJobId) return;
		if (apiInputEvalJobStatus.status === "completed" && apiInputEvalJobStatus.result) {
			setApiInputEvaluationResult(apiInputEvalJobStatus.result);
			setSelectedPromptSuggestionKeys(new Set());
			void queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			void queryClient.invalidateQueries({ queryKey: ["admin-tool-eval-history"] });
			const noticeKey = `${apiInputEvalJobId}:completed`;
			if (lastApiInputEvalJobNotice !== noticeKey) {
				toast.success("API input eval-run klar");
				setLastApiInputEvalJobNotice(noticeKey);
			}
		}
		if (apiInputEvalJobStatus.status === "failed") {
			const noticeKey = `${apiInputEvalJobId}:failed`;
			if (lastApiInputEvalJobNotice !== noticeKey) {
				toast.error(apiInputEvalJobStatus.error || "API input eval-run misslyckades");
				setLastApiInputEvalJobNotice(noticeKey);
			}
		}
	}, [apiInputEvalJobStatus, apiInputEvalJobId, lastApiInputEvalJobNotice, queryClient]);

	useEffect(() => {
		if (!autoLoopJobStatus || !autoLoopJobId) return;
		if (autoLoopJobStatus.status === "completed" && autoLoopJobStatus.result) {
			const result = autoLoopJobStatus.result;
			setEvaluationResult(result.final_evaluation);
			setSelectedSuggestionIds(new Set());
			setSelectedToolPromptSuggestionKeys(new Set());
			setAutoLoopPromptDrafts(result.draft_changes.prompt_patch ?? []);
			if (result.draft_changes.metadata_patch.length > 0) {
				setDraftTools((prev) => {
					const next = { ...prev };
					for (const item of result.draft_changes.metadata_patch) {
						next[item.tool_id] = { ...item };
					}
					return next;
				});
			}
			if (result.draft_changes.retrieval_tuning_override) {
				setDraftRetrievalTuning(result.draft_changes.retrieval_tuning_override);
			}
			void queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			void queryClient.invalidateQueries({ queryKey: ["admin-tool-eval-history"] });
			const noticeKey = `${autoLoopJobId}:completed`;
			if (lastAutoLoopNotice !== noticeKey) {
				toast.success("Auto-läge klart. Utkast har lagts i draft.");
				setLastAutoLoopNotice(noticeKey);
			}
		}
		if (autoLoopJobStatus.status === "failed") {
			const noticeKey = `${autoLoopJobId}:failed`;
			if (lastAutoLoopNotice !== noticeKey) {
				toast.error(autoLoopJobStatus.error || "Auto-läge misslyckades");
				setLastAutoLoopNotice(noticeKey);
			}
		}
	}, [autoLoopJobStatus, autoLoopJobId, lastAutoLoopNotice, queryClient]);

	// ---------------------------------------------------------------------------
	// Handlers
	// ---------------------------------------------------------------------------

	const handleExportEvalRun = (
		kind: "tool_selection" | "api_input",
		format: EvalExportFormat
	) => {
		const isApiInput = kind === "api_input";
		const jobId = isApiInput ? apiInputEvalJobId : evalJobId;
		const jobStatus: ExportableEvalJobStatus | undefined = isApiInput
			? apiInputEvalJobStatus
			: evalJobStatus;
		const resultPayload = isApiInput
			? (apiInputEvalJobStatus?.result ?? apiInputEvaluationResult)
			: (evalJobStatus?.result ?? evaluationResult);
		if (!jobId || !jobStatus) {
			toast.error("Ingen eval-körning att exportera ännu.");
			return;
		}
		const exportPayload = {
			export_version: 1,
			exported_at: new Date().toISOString(),
			source: "admin/calibration-tab",
			eval_type: kind,
			search_space_id: data?.search_space_id ?? null,
			job: {
				job_id: jobId,
				status: jobStatus.status,
				total_tests: jobStatus.total_tests,
				completed_tests: jobStatus.completed_tests,
				started_at: jobStatus.started_at ?? null,
				completed_at: jobStatus.completed_at ?? null,
				updated_at: jobStatus.updated_at,
				error: jobStatus.error ?? null,
				case_statuses: jobStatus.case_statuses ?? [],
			},
			result: resultPayload ?? null,
		};
		const fileName = buildEvalExportFileName(kind, jobId, format);
		try {
			if (format === "json") {
				downloadTextFile(
					`${JSON.stringify(exportPayload, null, 2)}\n`,
					fileName,
					"application/json"
				);
			} else {
				downloadTextFile(stringifyYaml(exportPayload), fileName, "application/yaml");
			}
			toast.success(`Exporterade eval-körning som ${format.toUpperCase()}`);
		} catch (_error) {
			toast.error("Kunde inte exportera eval-körningen");
		}
	};

	const handleGenerateEvalLibraryFile = async () => {
		if (!data?.search_space_id) return;
		if (generationMode === "category" && !generationCategory) {
			toast.error("Välj en kategori innan du genererar.");
			return;
		}
		if (generationMode === "provider" && (!generationProvider || generationProvider === "all")) {
			toast.error("Välj en specifik provider för huvudkategori-läge.");
			return;
		}
		const normalizedQuestionCount = Number.isFinite(generationQuestionCount)
			? generationQuestionCount
			: 12;
		setIsGeneratingEvalFile(true);
		try {
			const response = await adminToolSettingsApiService.generateEvalLibraryFile({
				search_space_id: data.search_space_id,
				eval_type: generationEvalType,
				mode: generationMode,
				provider_key: generationMode === "global_random" && generationProvider === "all"
					? null
					: generationProvider,
				category_id: generationMode === "category" ? generationCategory : null,
				weather_suite_mode: "mixed",
				question_count: Math.max(1, Math.min(100, Math.round(normalizedQuestionCount))),
				difficulty_profile: generationDifficultyProfile,
				eval_name: generationEvalName.trim() || null,
				include_allowed_tools: true,
			});
			setEvalInput(JSON.stringify(response.payload, null, 2));
			setEvalInputError(null);
			setShowEvalJsonInput(true);
			setSelectedLibraryPath(response.relative_path);
			await queryClient.invalidateQueries({
				queryKey: ["admin-tool-eval-library-files"],
			});
			const generatedTests = Array.isArray(response.payload.tests)
				? response.payload.tests.length
				: 0;
			toast.success(
				`Genererade ${generatedTests} frågor och sparade ${response.file_name}`
			);
		} catch (error) {
			toast.error("Kunde inte generera eval-fil");
		} finally {
			setIsGeneratingEvalFile(false);
		}
	};

	const handleStartAutoLoop = async () => {
		if (!data?.search_space_id) return;
		if (generationEvalType !== "tool_selection") {
			toast.error("Auto-läge stöder just nu endast Tool selection.");
			return;
		}
		if (generationMode === "category" && !generationCategory) {
			toast.error("Välj en kategori innan auto-läge startas.");
			return;
		}
		if (generationMode === "provider" && (!generationProvider || generationProvider === "all")) {
			toast.error("Välj en specifik provider för huvudkategori-läge.");
			return;
		}
		const normalizedQuestionCount = Number.isFinite(generationQuestionCount)
			? generationQuestionCount
			: 12;
		const normalizedTarget = Number.isFinite(autoTargetSuccessRate)
			? Math.max(0, Math.min(1, autoTargetSuccessRate))
			: 0.85;
		const normalizedIterations = Math.max(1, Math.min(30, Math.round(autoMaxIterations)));
		const normalizedPatience = Math.max(1, Math.min(12, Math.round(autoPatience)));
		const normalizedDelta = Number.isFinite(autoMinImprovementDelta)
			? Math.max(0, Math.min(0.25, autoMinImprovementDelta))
			: 0.005;
		const normalizedHoldoutCount = Number.isFinite(autoHoldoutQuestionCount)
			? Math.max(1, Math.min(100, Math.round(autoHoldoutQuestionCount)))
			: 8;
		setIsStartingAutoLoop(true);
		try {
			const started = await adminToolSettingsApiService.startToolAutoLoop({
				search_space_id: data.search_space_id,
				generation: {
					eval_type: "tool_selection",
					mode: generationMode,
					provider_key:
						generationMode === "global_random" && generationProvider === "all"
							? null
							: generationProvider,
					category_id: generationMode === "category" ? generationCategory : null,
					weather_suite_mode: "mixed",
					question_count: Math.max(1, Math.min(100, Math.round(normalizedQuestionCount))),
					difficulty_profile: generationDifficultyProfile,
					eval_name: generationEvalName.trim() || null,
					include_allowed_tools: true,
				},
				use_holdout_suite: autoUseHoldoutSuite,
				holdout_question_count: normalizedHoldoutCount,
				holdout_difficulty_profile: autoUseHoldoutSuite
					? autoHoldoutDifficultyProfile
					: null,
				target_success_rate: normalizedTarget,
				max_iterations: normalizedIterations,
				patience: normalizedPatience,
				min_improvement_delta: normalizedDelta,
				retrieval_limit: retrievalLimit,
				use_llm_supervisor_review: useLlmSupervisorReview,
				include_metadata_suggestions: true,
				include_prompt_suggestions: true,
				include_retrieval_tuning_suggestions: true,
			});
			setAutoLoopJobId(started.job_id);
			setLastAutoLoopNotice(null);
			setAutoLoopPromptDrafts([]);
			toast.info(
				`Auto-läge startat (${started.total_iterations} iterationer, target ${(started.target_success_rate * 100).toFixed(1)}%${
					autoUseHoldoutSuite ? `, holdout ${normalizedHoldoutCount}` : ""
				})`
			);
		} catch (_error) {
			toast.error("Kunde inte starta auto-läge");
		} finally {
			setIsStartingAutoLoop(false);
		}
	};

	const loadEvalLibraryFile = async (relativePath: string) => {
		setIsLoadingLibraryFile(true);
		try {
			const response = await adminToolSettingsApiService.readEvalLibraryFile(relativePath);
			setEvalInput(response.content);
			setEvalInputError(null);
			setShowEvalJsonInput(true);
			setSelectedLibraryPath(relativePath);
			toast.success(`Laddade ${response.relative_path}`);
		} catch (error) {
			toast.error("Kunde inte ladda eval-fil");
		} finally {
			setIsLoadingLibraryFile(false);
		}
	};

	const loadEvalLibraryFileToHoldout = async (relativePath: string) => {
		setIsLoadingLibraryFile(true);
		try {
			const response = await adminToolSettingsApiService.readEvalLibraryFile(relativePath);
			setHoldoutInput(response.content);
			setEvalInputError(null);
			setUseHoldoutSuite(true);
			setShowHoldoutJsonInput(true);
			setSelectedHoldoutLibraryPath(relativePath);
			toast.success(`Laddade ${response.relative_path} i holdout`);
		} catch (_error) {
			toast.error("Kunde inte ladda holdout-fil");
		} finally {
			setIsLoadingLibraryFile(false);
		}
	};

	const parseEvalInput = (): {
		eval_name?: string;
		target_success_rate?: number;
		tests: ToolEvaluationTestCase[];
	} | null => {
		setEvalInputError(null);
		const trimmed = evalInput.trim();
		if (!trimmed) {
			setEvalInputError("Klistra in eval-JSON innan du kör.");
			return null;
		}
		try {
			const parsed = JSON.parse(trimmed);
			const envelope = Array.isArray(parsed) ? { tests: parsed } : parsed;
			if (!envelope || !Array.isArray(envelope.tests)) {
				setEvalInputError("JSON måste innehålla en tests-array.");
				return null;
			}
			const tests: ToolEvaluationTestCase[] = envelope.tests.map(
				(item: any, index: number) => ({
					id: String(item.id ?? `case-${index + 1}`),
					question: String(item.question ?? ""),
					difficulty:
						typeof item.difficulty === "string" ? item.difficulty : undefined,
					expected:
						item.expected ||
						item.expected_tool ||
						item.expected_category ||
						item.expected_agent ||
						item.expected_route ||
						item.expected_sub_route ||
						item.plan_requirements
							? {
									tool: item.expected?.tool ?? item.expected_tool ?? null,
									category:
										item.expected?.category ?? item.expected_category ?? null,
									agent: item.expected?.agent ?? item.expected_agent ?? null,
									route: item.expected?.route ?? item.expected_route ?? null,
									sub_route:
										item.expected?.sub_route ?? item.expected_sub_route ?? null,
									plan_requirements: Array.isArray(
										item.expected?.plan_requirements ?? item.plan_requirements
									)
										? (
												item.expected?.plan_requirements ?? item.plan_requirements
											).map((value: unknown) => String(value))
										: [],
								}
							: undefined,
					allowed_tools: Array.isArray(item.allowed_tools)
						? item.allowed_tools.map((value: unknown) => String(value))
						: [],
				})
			);
			const invalidCase = tests.find((test) => !test.question.trim());
			if (invalidCase) {
				setEvalInputError(`Test ${invalidCase.id} saknar question.`);
				return null;
			}
			return {
				eval_name:
					typeof envelope.eval_name === "string" ? envelope.eval_name : undefined,
				target_success_rate:
					typeof envelope.target_success_rate === "number"
						? envelope.target_success_rate
						: undefined,
				tests,
			};
		} catch (error) {
			setEvalInputError("Ogiltig JSON. Kontrollera formatet och försök igen.");
			return null;
		}
	};

	const parseApiInputCaseList = (items: any[]): ToolApiInputEvaluationTestCase[] => {
		return items.map((item: any, index: number) => ({
			id: String(item.id ?? `case-${index + 1}`),
			question: String(item.question ?? ""),
			difficulty: typeof item.difficulty === "string" ? item.difficulty : undefined,
			expected:
				item.expected ||
				item.expected_tool ||
				item.expected_category ||
				item.expected_agent ||
				item.expected_route ||
				item.expected_sub_route ||
				item.plan_requirements ||
				item.required_fields ||
				item.field_values ||
				typeof item.allow_clarification === "boolean"
					? {
							tool: item.expected?.tool ?? item.expected_tool ?? null,
							category: item.expected?.category ?? item.expected_category ?? null,
							agent: item.expected?.agent ?? item.expected_agent ?? null,
							route: item.expected?.route ?? item.expected_route ?? null,
							sub_route: item.expected?.sub_route ?? item.expected_sub_route ?? null,
							plan_requirements: Array.isArray(
								item.expected?.plan_requirements ?? item.plan_requirements
							)
								? (
										item.expected?.plan_requirements ?? item.plan_requirements
									).map((value: unknown) => String(value))
								: [],
							required_fields: Array.isArray(
								item.expected?.required_fields ?? item.required_fields
							)
								? (item.expected?.required_fields ?? item.required_fields).map(
										(value: unknown) => String(value)
									)
								: [],
							field_values:
								typeof (item.expected?.field_values ?? item.field_values) ===
									"object" &&
								(item.expected?.field_values ?? item.field_values) !== null
									? (item.expected?.field_values ?? item.field_values)
									: {},
							allow_clarification:
								typeof (item.expected?.allow_clarification ??
									item.allow_clarification) === "boolean"
									? (item.expected?.allow_clarification ?? item.allow_clarification)
									: undefined,
						}
					: undefined,
			allowed_tools: Array.isArray(item.allowed_tools)
				? item.allowed_tools.map((value: unknown) => String(value))
				: [],
		})) as ToolApiInputEvaluationTestCase[];
	};

	const parseApiInputEvalInput = (): {
		eval_name?: string;
		target_success_rate?: number;
		tests: ToolApiInputEvaluationTestCase[];
		holdout_tests: ToolApiInputEvaluationTestCase[];
	} | null => {
		setEvalInputError(null);
		const trimmed = evalInput.trim();
		if (!trimmed) {
			setEvalInputError("Klistra in eval-JSON innan du kör.");
			return null;
		}
		try {
			const parsed = JSON.parse(trimmed);
			const envelope = Array.isArray(parsed) ? { tests: parsed } : parsed;
			if (!envelope || !Array.isArray(envelope.tests)) {
				setEvalInputError("JSON måste innehålla en tests-array.");
				return null;
			}
			const tests = parseApiInputCaseList(envelope.tests);
			const invalidCase = tests.find((test) => !test.question.trim());
			if (invalidCase) {
				setEvalInputError(`Test ${invalidCase.id} saknar question.`);
				return null;
			}
			let holdoutTestsRaw: any[] = [];
			if (useHoldoutSuite) {
				holdoutTestsRaw = Array.isArray(envelope.holdout_tests)
					? envelope.holdout_tests
					: [];
				const holdoutTrimmed = holdoutInput.trim();
				if (holdoutTrimmed) {
					let parsedHoldout: any;
					try {
						parsedHoldout = JSON.parse(holdoutTrimmed);
					} catch (_error) {
						setEvalInputError("Ogiltig holdout-JSON. Kontrollera formatet.");
						return null;
					}
					const extractedHoldoutTests = Array.isArray(parsedHoldout)
						? parsedHoldout
						: Array.isArray(parsedHoldout?.tests)
							? parsedHoldout.tests
							: Array.isArray(parsedHoldout?.holdout_tests)
								? parsedHoldout.holdout_tests
								: null;
					if (!extractedHoldoutTests) {
						setEvalInputError(
							"Holdout-JSON måste innehålla en tests-array (eller holdout_tests)."
						);
						return null;
					}
					holdoutTestsRaw = extractedHoldoutTests;
				}
			}
			const holdoutTests = parseApiInputCaseList(holdoutTestsRaw);
			const invalidHoldoutCase = holdoutTests.find((test) => !test.question.trim());
			if (invalidHoldoutCase) {
				setEvalInputError(`Holdout test ${invalidHoldoutCase.id} saknar question.`);
				return null;
			}
			if (useHoldoutSuite && holdoutTests.length === 0) {
				setEvalInputError(
					"Aktiverad holdout-suite men inga holdout tests hittades. Lägg till holdout-JSON eller holdout_tests i huvud-JSON."
				);
				return null;
			}
			return {
				eval_name:
					typeof envelope.eval_name === "string" ? envelope.eval_name : undefined,
				target_success_rate:
					typeof envelope.target_success_rate === "number"
						? envelope.target_success_rate
						: undefined,
				tests,
				holdout_tests: holdoutTests,
			};
		} catch (_error) {
			setEvalInputError("Ogiltig JSON. Kontrollera formatet och försök igen.");
			return null;
		}
	};

	const handleRunEvaluation = async () => {
		const parsedInput = parseEvalInput();
		if (!parsedInput) return;
		setIsEvaluating(true);
		try {
			const started = await adminToolSettingsApiService.startToolEvaluation({
				eval_name: parsedInput.eval_name,
				target_success_rate: parsedInput.target_success_rate,
				search_space_id: data?.search_space_id,
				retrieval_limit: retrievalLimit,
				use_llm_supervisor_review: useLlmSupervisorReview,
				tests: parsedInput.tests,
				metadata_patch: includeDraftMetadata ? metadataPatch : [],
				retrieval_tuning_override:
					includeDraftMetadata && draftRetrievalTuning
						? draftRetrievalTuning
						: undefined,
			});
			setEvalJobId(started.job_id);
			setLastEvalJobNotice(null);
			setEvaluationResult(null);
			setSelectedSuggestionIds(new Set());
			setSelectedToolPromptSuggestionKeys(new Set());
			toast.info(`Eval-run startad (${started.total_tests} frågor)`);
		} catch (err) {
			toast.error("Eval-run misslyckades");
		} finally {
			setIsEvaluating(false);
		}
	};

	const handleRunApiInputEvaluation = async () => {
		const parsedInput = parseApiInputEvalInput();
		if (!parsedInput) return;
		setIsApiInputEvaluating(true);
		try {
			const started = await adminToolSettingsApiService.startToolApiInputEvaluation({
				eval_name: parsedInput.eval_name,
				target_success_rate: parsedInput.target_success_rate,
				search_space_id: data?.search_space_id,
				retrieval_limit: retrievalLimit,
				use_llm_supervisor_review: useLlmSupervisorReview,
				tests: parsedInput.tests,
				holdout_tests: parsedInput.holdout_tests,
				metadata_patch: includeDraftMetadata ? metadataPatch : [],
				retrieval_tuning_override:
					includeDraftMetadata && draftRetrievalTuning
						? draftRetrievalTuning
						: undefined,
			});
			setApiInputEvalJobId(started.job_id);
			setLastApiInputEvalJobNotice(null);
			setApiInputEvaluationResult(null);
			setSelectedPromptSuggestionKeys(new Set());
			toast.info(
				`API input eval-run startad (${started.total_tests} frågor${
					parsedInput.holdout_tests.length > 0
						? ` + holdout ${parsedInput.holdout_tests.length}`
						: ""
				})`
			);
		} catch (_err) {
			toast.error("API input eval-run misslyckades");
		} finally {
			setIsApiInputEvaluating(false);
		}
	};

	const toggleSuggestion = (toolId: string) => {
		setSelectedSuggestionIds((prev) => {
			const next = new Set(prev);
			if (next.has(toolId)) next.delete(toolId);
			else next.add(toolId);
			return next;
		});
	};

	const togglePromptSuggestion = (promptKey: string) => {
		setSelectedPromptSuggestionKeys((prev) => {
			const next = new Set(prev);
			if (next.has(promptKey)) next.delete(promptKey);
			else next.add(promptKey);
			return next;
		});
	};

	const toggleToolPromptSuggestion = (promptKey: string) => {
		setSelectedToolPromptSuggestionKeys((prev) => {
			const next = new Set(prev);
			if (next.has(promptKey)) next.delete(promptKey);
			else next.add(promptKey);
			return next;
		});
	};

	const applySelectedSuggestionsToDraft = async () => {
		if (!evaluationResult) return;
		setIsApplyingSuggestions(true);
		try {
			const selected = evaluationResult.suggestions.filter((suggestion) =>
				selectedSuggestionIds.has(suggestion.tool_id)
			);
			if (!selected.length) {
				toast.info("Välj minst ett förslag att applicera");
				return;
			}
			setDraftTools((prev) => {
				const next = { ...prev };
				for (const suggestion of selected) {
					next[suggestion.tool_id] = { ...suggestion.proposed_metadata };
				}
				return next;
			});
			toast.success(`Applicerade ${selected.length} förslag i draft`);
		} finally {
			setIsApplyingSuggestions(false);
		}
	};

	const saveSelectedSuggestions = async () => {
		if (!evaluationResult || !data?.search_space_id) return;
		const selected = evaluationResult.suggestions.filter((suggestion) =>
			selectedSuggestionIds.has(suggestion.tool_id)
		);
		if (!selected.length) {
			toast.info("Välj minst ett förslag att spara");
			return;
		}
		setIsSavingSuggestions(true);
		try {
			await adminToolSettingsApiService.applySuggestions(
				{
					suggestions: selected.map((suggestion) => ({
						tool_id: suggestion.tool_id,
						proposed_metadata: suggestion.proposed_metadata,
					})),
				},
				data.search_space_id
			);
			await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			await refetch();
			toast.success(`Sparade ${selected.length} metadataförslag`);
		} catch (error) {
			toast.error("Kunde inte spara valda förslag");
		} finally {
			setIsSavingSuggestions(false);
		}
	};

	const regenerateSuggestions = async () => {
		if (!evaluationResult) return;
		try {
			const response = await adminToolSettingsApiService.generateSuggestions({
				search_space_id: data?.search_space_id,
				metadata_patch: includeDraftMetadata ? metadataPatch : [],
				failed_cases: evaluationResult.results.filter((result) => !result.passed),
			});
			setEvaluationResult((prev) =>
				prev ? { ...prev, suggestions: response.suggestions } : prev
			);
			setSelectedSuggestionIds(new Set());
			toast.success("Förslag uppdaterade");
		} catch (error) {
			toast.error("Kunde inte generera förslag");
		}
	};

	const applyWeightSuggestionToDraft = () => {
		const suggestion = evaluationResult?.retrieval_tuning_suggestion;
		if (!suggestion) {
			toast.info("Inget viktförslag att applicera.");
			return;
		}
		setDraftRetrievalTuning(suggestion.proposed_tuning);
		toast.success("Applicerade viktförslag i draft");
	};

	const saveWeightSuggestion = async () => {
		const suggestion = evaluationResult?.retrieval_tuning_suggestion;
		if (!suggestion) {
			toast.info("Inget viktförslag att spara.");
			return;
		}
		setIsSavingRetrievalTuning(true);
		try {
			await adminToolSettingsApiService.updateRetrievalTuning(
				suggestion.proposed_tuning
			);
			await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			await refetch();
			setDraftRetrievalTuning(suggestion.proposed_tuning);
			toast.success("Sparade föreslagna retrieval-vikter");
		} catch (error) {
			toast.error("Kunde inte spara viktförslaget");
		} finally {
			setIsSavingRetrievalTuning(false);
		}
	};

	const saveSelectedPromptSuggestions = async () => {
		if (!apiInputEvaluationResult) return;
		const selected = apiInputEvaluationResult.prompt_suggestions.filter((suggestion) =>
			selectedPromptSuggestionKeys.has(suggestion.prompt_key)
		);
		if (!selected.length) {
			toast.info("Välj minst ett promptförslag att spara");
			return;
		}
		setIsSavingPromptSuggestions(true);
		try {
			await adminToolSettingsApiService.applyApiInputPromptSuggestions({
				suggestions: selected.map((suggestion) => ({
					prompt_key: suggestion.prompt_key,
					proposed_prompt: suggestion.proposed_prompt,
				})),
			});
			setSelectedPromptSuggestionKeys(new Set());
			toast.success(`Sparade ${selected.length} promptförslag`);
		} catch (_error) {
			toast.error("Kunde inte spara valda promptförslag");
		} finally {
			setIsSavingPromptSuggestions(false);
		}
	};

	const saveSelectedToolPromptSuggestions = async () => {
		if (!evaluationResult) return;
		const selected = evaluationResult.prompt_suggestions.filter((suggestion) =>
			selectedToolPromptSuggestionKeys.has(suggestion.prompt_key)
		);
		if (!selected.length) {
			toast.info("Välj minst ett promptförslag att spara");
			return;
		}
		setIsSavingToolPromptSuggestions(true);
		try {
			await adminToolSettingsApiService.applyApiInputPromptSuggestions({
				suggestions: selected.map((suggestion) => ({
					prompt_key: suggestion.prompt_key,
					proposed_prompt: suggestion.proposed_prompt,
				})),
			});
			setSelectedToolPromptSuggestionKeys(new Set());
			toast.success(`Sparade ${selected.length} promptförslag`);
		} catch (_error) {
			toast.error("Kunde inte spara valda promptförslag");
		} finally {
			setIsSavingToolPromptSuggestions(false);
		}
	};

	const uploadEvalFile = async (event: ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		if (!file) return;
		const content = await file.text();
		setEvalInput(content);
		setEvalInputError(null);
		setSelectedLibraryPath("");
	};

	const uploadHoldoutFile = async (event: ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		if (!file) return;
		const content = await file.text();
		setHoldoutInput(content);
		setEvalInputError(null);
		setUseHoldoutSuite(true);
		setShowHoldoutJsonInput(true);
		setSelectedHoldoutLibraryPath("");
	};

	const saveAutoLoopPromptDraftSuggestions = async () => {
		if (!autoLoopPromptDrafts.length) {
			toast.info("Inga promptutkast från auto-läge att spara.");
			return;
		}
		setIsSavingAutoLoopPromptDrafts(true);
		try {
			await adminToolSettingsApiService.applyApiInputPromptSuggestions({
				suggestions: autoLoopPromptDrafts.map((item) => ({
					prompt_key: item.prompt_key,
					proposed_prompt: item.proposed_prompt,
				})),
			});
			toast.success(`Sparade ${autoLoopPromptDrafts.length} promptutkast`);
		} catch (_error) {
			toast.error("Kunde inte spara promptutkast från auto-läge");
		} finally {
			setIsSavingAutoLoopPromptDrafts(false);
		}
	};

	// ---------------------------------------------------------------------------
	// Audit handlers (Steg 1 — egen audit)
	// ---------------------------------------------------------------------------

	const handleRunAudit = async () => {
		setIsRunningAudit(true);
		try {
			const result = await adminToolSettingsApiService.runMetadataCatalogAudit({
				search_space_id: data?.search_space_id,
				metadata_patch: includeDraftMetadata ? metadataPatch : [],
				max_tools: auditMaxTools,
				retrieval_limit: auditRetrievalLimit,
			});
			setAuditResult(result);
			toast.success(
				`Audit klar: Intent ${(result.summary.intent_accuracy * 100).toFixed(1)}% · Agent ${(result.summary.agent_accuracy * 100).toFixed(1)}% · Tool ${(result.summary.tool_accuracy * 100).toFixed(1)}%`
			);
		} catch (_error) {
			toast.error("Audit misslyckades");
		} finally {
			setIsRunningAudit(false);
		}
	};

	const handleRunSeparation = async () => {
		setIsRunningSeparation(true);
		try {
			const result = await adminToolSettingsApiService.runMetadataCatalogSeparation({
				search_space_id: data?.search_space_id,
				metadata_patch: includeDraftMetadata ? metadataPatch : [],
				max_tools: auditMaxTools,
				retrieval_limit: auditRetrievalLimit,
			});
			setSeparationResult(result);
			toast.success("Separation klar");
		} catch (_error) {
			toast.error("Separation misslyckades");
		} finally {
			setIsRunningSeparation(false);
		}
	};

	const handleBulkPromote = async () => {
		setIsPromoting(true);
		try {
			await adminToolLifecycleApiService.bulkPromoteToLive();
			await refetchLifecycle();
			toast.success("Kvalificerade verktyg befordrade till Live");
		} catch (_error) {
			toast.error("Kunde inte befordra verktyg");
		} finally {
			setIsPromoting(false);
		}
	};

	// ---------------------------------------------------------------------------
	// Render
	// ---------------------------------------------------------------------------

	if (isLoading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	if (error) {
		return (
			<Alert variant="destructive">
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					Fel vid hämtning av verktygsdata. Kontrollera att du har
					administratörsbehörighet.
				</AlertDescription>
			</Alert>
		);
	}

	return (
		<div className="space-y-6">
			{/* ================================================================ */}
			{/* FAS-PANEL ÖVERST                                                */}
			{/* ================================================================ */}
			<Card>
				<CardHeader>
					<CardTitle>Fas-panel</CardTitle>
					<CardDescription>
						Live routing-fas, embedding-modell och antal verktyg.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="flex flex-wrap items-center gap-2">
						{(["shadow", "tool_gate", "agent_auto", "adaptive", "intent_finetune"] as const).map(
							(phase) => {
								const currentPhase = draftRetrievalTuning?.live_routing_phase ?? data?.retrieval_tuning?.live_routing_phase ?? "shadow";
								const isActive = phase === currentPhase;
								const labels: Record<string, string> = {
									shadow: "Shadow",
									tool_gate: "Tool gate",
									agent_auto: "Agent auto",
									adaptive: "Adaptive",
									intent_finetune: "Intent finetune",
								};
								return (
									<Badge
										key={phase}
										variant={isActive ? "default" : "outline"}
										className={isActive ? "bg-green-600 hover:bg-green-700" : ""}
									>
										{isActive ? "●" : "○"} {labels[phase]}
									</Badge>
								);
							}
						)}
					</div>
					<div className="grid gap-3 md:grid-cols-3 text-sm">
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Metadata version</p>
							<p className="font-medium font-mono text-xs">{data?.metadata_version_hash?.slice(0, 12) ?? "-"}</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Antal verktyg</p>
							<p className="font-medium">
								{data?.categories?.reduce((sum, cat) => sum + cat.tools.length, 0) ?? 0}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Lifecycle</p>
							<p className="font-medium">
								{lifecycleData?.live_count ?? 0} Live / {lifecycleData?.review_count ?? 0} Review
							</p>
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Guided 3-step navigation */}
			<Card>
				<CardHeader>
					<CardTitle>Kalibreringsflöde</CardTitle>
					<CardDescription>
						Guidat 3-stegsflöde: audit, eval och auto-optimering.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Tabs
						value={calibrationStep}
						onValueChange={(v) =>
							setCalibrationStep(v as "audit" | "eval" | "auto")
						}
					>
						<TabsList>
							<TabsTrigger value="audit">Steg 1: Metadata Audit</TabsTrigger>
							<TabsTrigger value="eval">Steg 2: Eval</TabsTrigger>
							<TabsTrigger value="auto">Steg 3: Auto-optimering</TabsTrigger>
						</TabsList>
					</Tabs>
				</CardContent>
			</Card>

			{/* ================================================================ */}
			{/* STEG 1: METADATA AUDIT (egen audit — inte MetadataCatalogTab)    */}
			{/* ================================================================ */}
			{calibrationStep === "audit" && (
				<div className="space-y-6">
					{/* Audit controls */}
					<Card>
						<CardHeader>
							<CardTitle>Metadata Audit</CardTitle>
							<CardDescription>
								Kör en 3-layer audit (intent, agent, tool) med probe-frågor
								och analysera kollisioner.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="flex flex-wrap items-center gap-3">
								<div className="flex items-center gap-2">
									<Label htmlFor="audit-max-tools">Max verktyg</Label>
									<Input
										id="audit-max-tools"
										type="number"
										min={5}
										max={200}
										value={auditMaxTools}
										onChange={(e) =>
											setAuditMaxTools(Number.parseInt(e.target.value || "25", 10))
										}
										className="w-24"
									/>
								</div>
								<div className="flex items-center gap-2">
									<Label htmlFor="audit-retrieval-limit">Retrieval K</Label>
									<Input
										id="audit-retrieval-limit"
										type="number"
										min={1}
										max={15}
										value={auditRetrievalLimit}
										onChange={(e) =>
											setAuditRetrievalLimit(Number.parseInt(e.target.value || "5", 10))
										}
										className="w-24"
									/>
								</div>
								<div className="flex items-center gap-2">
									<Switch checked={includeDraftMetadata} onCheckedChange={setIncludeDraftMetadata} />
									<span className="text-sm">Inkludera draft</span>
								</div>
								<Button onClick={handleRunAudit} disabled={isRunningAudit}>
									{isRunningAudit ? "Kör audit..." : "Kör audit"}
								</Button>
								<Button variant="outline" onClick={handleRunSeparation} disabled={isRunningSeparation || !auditResult}>
									{isRunningSeparation ? "Separerar..." : "Separera kollisioner"}
								</Button>
							</div>
						</CardContent>
					</Card>

					{/* Audit results — 3-layer accuracy */}
					{auditResult && (
						<Card>
							<CardHeader>
								<CardTitle>Audit-resultat</CardTitle>
								<CardDescription>
									{auditResult.summary.total_probes} probes ·
									metadata version {auditResult.metadata_version_hash.slice(0, 8)}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid gap-4 md:grid-cols-3">
									<div className="rounded border p-3 text-center">
										<p className="text-xs text-muted-foreground">Intent accuracy</p>
										<p className="text-2xl font-semibold">
											{(auditResult.summary.intent_accuracy * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3 text-center">
										<p className="text-xs text-muted-foreground">Agent accuracy</p>
										<p className="text-2xl font-semibold">
											{(auditResult.summary.agent_accuracy * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3 text-center">
										<p className="text-xs text-muted-foreground">Tool accuracy</p>
										<p className="text-2xl font-semibold">
											{(auditResult.summary.tool_accuracy * 100).toFixed(1)}%
										</p>
									</div>
								</div>

								{/* Conditional accuracy */}
								<div className="grid gap-4 md:grid-cols-2">
									{auditResult.summary.agent_accuracy_given_intent_correct != null && (
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Agent | Intent korrekt</p>
											<p className="text-lg font-semibold">
												{(auditResult.summary.agent_accuracy_given_intent_correct * 100).toFixed(1)}%
											</p>
										</div>
									)}
									{auditResult.summary.tool_accuracy_given_intent_agent_correct != null && (
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Tool | Intent+Agent korrekt</p>
											<p className="text-lg font-semibold">
												{(auditResult.summary.tool_accuracy_given_intent_agent_correct * 100).toFixed(1)}%
											</p>
										</div>
									)}
								</div>

								{/* Collision report (confusion matrices) */}
								{auditResult.summary.tool_confusion_matrix.length > 0 && (
									<div className="rounded border p-3 space-y-2">
										<p className="text-sm font-medium">
											Kollisionsrapport ({auditResult.summary.tool_confusion_matrix.length} par)
										</p>
										<div className="max-h-64 overflow-auto space-y-1">
											{auditResult.summary.tool_confusion_matrix.slice(0, 15).map((pair, idx) => (
												<div key={`collision-${idx}`} className="flex items-center gap-2 text-xs rounded bg-muted/40 px-2 py-1">
													<Badge variant="outline">{pair.expected_label}</Badge>
													<span className="text-muted-foreground">↔</span>
													<Badge variant="outline">{pair.predicted_label}</Badge>
													<span className="text-muted-foreground ml-auto">
														{pair.count} fel
													</span>
												</div>
											))}
										</div>
									</div>
								)}

								{/* Vector recall summary */}
								{auditResult.summary.vector_recall_summary && (
									<div className="grid gap-3 md:grid-cols-3 text-sm">
										<Badge variant="outline">
											Vektor-kandidater: {auditResult.summary.vector_recall_summary.probes_with_vector_candidates}
										</Badge>
										<Badge variant="outline">
											Top-1 från vektor: {auditResult.summary.vector_recall_summary.probes_with_top1_from_vector}
										</Badge>
										<Badge variant="outline">
											Förväntad i top-K: {auditResult.summary.vector_recall_summary.probes_with_expected_tool_in_vector_top_k}
										</Badge>
									</div>
								)}

								{/* Probe details (collapsed by default) */}
								{auditResult.probes.length > 0 && (
									<details className="rounded border p-3">
										<summary className="text-sm font-medium cursor-pointer">
											Visa probe-detaljer ({auditResult.probes.length} probes)
										</summary>
										<div className="mt-3 max-h-96 overflow-auto space-y-2">
											{auditResult.probes.slice(0, 50).map((probe) => (
												<div
													key={probe.probe_id}
													className="rounded border p-2 text-xs space-y-1"
												>
													<p className="font-medium">{probe.query}</p>
													<div className="flex flex-wrap gap-2">
														<Badge variant={probe.intent.predicted_label === probe.intent.expected_label ? "outline" : "destructive"}>
															Intent: {probe.intent.expected_label ?? "-"} → {probe.intent.predicted_label ?? "-"}
														</Badge>
														<Badge variant={probe.agent.predicted_label === probe.agent.expected_label ? "outline" : "destructive"}>
															Agent: {probe.agent.expected_label ?? "-"} → {probe.agent.predicted_label ?? "-"}
														</Badge>
														<Badge variant={probe.tool.predicted_label === probe.tool.expected_label ? "outline" : "destructive"}>
															Tool: {probe.tool.expected_label ?? "-"} → {probe.tool.predicted_label ?? "-"}
														</Badge>
													</div>
												</div>
											))}
										</div>
									</details>
								)}
							</CardContent>
						</Card>
					)}

					{/* Separation results */}
					{separationResult && (
						<Card>
							<CardHeader>
								<CardTitle>Separationsresultat</CardTitle>
								<CardDescription>
									Baseline → Final accuracy efter separation
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid gap-4 md:grid-cols-2">
									<div className="rounded border p-3 space-y-1">
										<p className="text-xs text-muted-foreground">Baseline</p>
										<p className="text-sm">
											Intent {(separationResult.baseline_summary.intent_accuracy * 100).toFixed(1)}% ·
											Agent {(separationResult.baseline_summary.agent_accuracy * 100).toFixed(1)}% ·
											Tool {(separationResult.baseline_summary.tool_accuracy * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3 space-y-1">
										<p className="text-xs text-muted-foreground">Slutresultat</p>
										<p className="text-sm">
											Intent {(separationResult.final_summary.intent_accuracy * 100).toFixed(1)}% ·
											Agent {(separationResult.final_summary.agent_accuracy * 100).toFixed(1)}% ·
											Tool {(separationResult.final_summary.tool_accuracy * 100).toFixed(1)}%
										</p>
									</div>
								</div>
								{separationResult.proposed_tool_metadata_patch.length > 0 && (
									<div className="rounded border p-3 space-y-2">
										<p className="text-sm font-medium">
											{separationResult.proposed_tool_metadata_patch.length} metadata-ändringar föreslagna
										</p>
										<Button
											onClick={async () => {
												try {
													await adminToolSettingsApiService.updateMetadataCatalog({
														tool_updates: separationResult.proposed_tool_metadata_patch,
													});
													await refetch();
													toast.success("Separationsförslag applicerade");
												} catch (_error) {
													toast.error("Kunde inte applicera separationsförslag");
												}
											}}
										>
											Applicera separationsförslag
										</Button>
									</div>
								)}
							</CardContent>
						</Card>
					)}
				</div>
			)}

			{/* ================================================================ */}
			{/* STEG 2: EVAL                                                    */}
			{/* ================================================================ */}
			{calibrationStep === "eval" && (
				<div className="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>Flikar för eval-steg</CardTitle>
							<CardDescription>
								Dela upp arbetsflödet i separata steg för tydligare körning och analys.
							</CardDescription>
						</CardHeader>
						<CardContent>
							<Tabs
								value={evaluationStepTab}
								onValueChange={(value) =>
									setEvaluationStepTab(
										value as "all" | "guide" | "generation" | "agent_eval" | "api_input"
									)
								}
							>
								<TabsList className="flex flex-wrap">
									<TabsTrigger value="all">Alla steg</TabsTrigger>
									<TabsTrigger value="guide">Guide</TabsTrigger>
									<TabsTrigger value="generation">Generering</TabsTrigger>
									<TabsTrigger value="agent_eval">Agentval Eval</TabsTrigger>
									<TabsTrigger value="api_input">API Input Eval</TabsTrigger>
								</TabsList>
							</Tabs>
						</CardContent>
					</Card>

					{showGuideSections && (
					<Card>
						<CardHeader>
							<CardTitle>Steg 0: Guide och arbetssätt</CardTitle>
							<CardDescription>
								Följ stegen nedan i ordning för att trimma route, agentval, tool-val,
								API-input och prompts på ett säkert sätt (dry-run).
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4 text-sm">
							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 1: Förbered test-upplägg</p>
								<ul className="list-disc pl-5 space-y-1 text-muted-foreground">
									<li>Börja med <span className="font-medium">Per kategori/API</span> för precision.</li>
									<li>Använd sedan <span className="font-medium">Global random mix</span> för regression.</li>
									<li>Rekommendation: 10-15 frågor per kategori och 25-40 frågor globalt.</li>
								</ul>
							</div>
							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 2: Generera eller ladda eval-JSON</p>
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>Välj Läge, Eval-typ, Provider, Kategori och antal frågor.</li>
									<li>Klicka &quot;Generera + spara eval JSON&quot;.</li>
									<li>Klicka &quot;Ladda i eval-input&quot; på filen i listan.</li>
									<li>Alternativt: ladda upp egen fil eller klistra in i JSON-fältet.</li>
								</ol>
							</div>
							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 3: Kör Agentval Eval</p>
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>Sätt <span className="font-medium">Retrieval K</span> (5 standard, 8-10 för svårare).</li>
									<li>Behåll &quot;Inkludera draft metadata&quot; aktiv för osparade ändringar.</li>
									<li>Klicka &quot;Run Tool Evaluation&quot;.</li>
									<li>Kontrollera Route, Sub-route, Agent, Plan och Tool accuracy.</li>
								</ol>
							</div>
							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 4: Förbättra och kör om</p>
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>Använd &quot;Metadata-förslag&quot; för description, keywords och exempelfrågor.</li>
									<li>Använd &quot;Föreslagen tuning&quot; för retrieval-vikter.</li>
									<li>Använd &quot;Prompt-förslag&quot; för router/agent-prompts.</li>
									<li>Kör om tills resultatet stabiliseras.</li>
								</ol>
							</div>
							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 5: Kör API Input Eval (utan API-anrop)</p>
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>Välj suite med required_fields (och gärna field_values).</li>
									<li>Klicka &quot;Run API Input Eval (dry-run)&quot;.</li>
									<li>Kontrollera Schema validity, Required-field recall, Field-value accuracy.</li>
									<li>Spara &quot;Prompt-förslag&quot; och kör om tills stabilt.</li>
								</ol>
							</div>
							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 6: Använd holdout (anti-overfitting)</p>
								<ul className="list-disc pl-5 space-y-1 text-muted-foreground">
									<li>Aktivera &quot;Använd holdout-suite&quot;.</li>
									<li>Klistra in separat holdout-JSON eller lägg holdout_tests i huvud-JSON.</li>
									<li>Optimera på huvudsuite, godkänn endast ändringar som även förbättrar holdout.</li>
								</ul>
							</div>
						</CardContent>
					</Card>
					)}

					{showGuideSections && (
					<Card>
						<CardHeader>
							<CardTitle>Stegöversikt</CardTitle>
							<CardDescription>
								Arbeta i denna ordning för ett tydligt och repeterbart eval-flöde.
							</CardDescription>
						</CardHeader>
						<CardContent className="flex flex-wrap items-center gap-2 text-xs">
							<Badge variant="secondary">Steg 1: Generera/Ladda frågor</Badge>
							<Badge variant="secondary">Steg 2: Agentval Eval (route + agent + tool + plan)</Badge>
							<Badge variant="secondary">Steg 3: API Input Eval</Badge>
							<Badge variant="secondary">Steg 4: Holdout + spara förbättringar</Badge>
						</CardContent>
					</Card>
					)}

					{showGenerationSections && (
					<Card>
						<CardHeader>
							<CardTitle>Steg 1: Generera/Ladda eval-frågor</CardTitle>
							<CardDescription>
								Skapa JSON i rätt format, spara i /eval/api och ladda direkt in i eval-run.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-6">
								<div className="space-y-2">
									<Label htmlFor="cal-generation-mode">Läge</Label>
									<select
										id="cal-generation-mode"
										className="h-10 w-full rounded-md border bg-background px-3 text-sm"
										value={generationMode}
										onChange={(event) =>
											setGenerationMode(
												event.target.value === "global_random"
													? "global_random"
													: event.target.value === "provider"
														? "provider"
														: "category"
											)
										}
									>
										<option value="category">Per kategori/API</option>
										<option value="provider">Huvudkategori/provider</option>
										<option value="global_random">Random mix (global)</option>
									</select>
								</div>
								<div className="space-y-2">
									<Label htmlFor="cal-generation-eval-type">Eval-typ</Label>
									<select
										id="cal-generation-eval-type"
										className="h-10 w-full rounded-md border bg-background px-3 text-sm"
										value={generationEvalType}
										onChange={(event) =>
											setGenerationEvalType(
												event.target.value === "api_input" ? "api_input" : "tool_selection"
											)
										}
									>
										<option value="tool_selection">Tool selection</option>
										<option value="api_input">API input</option>
									</select>
								</div>
								<div className="space-y-2">
									<Label htmlFor="cal-generation-provider">Provider</Label>
									<select
										id="cal-generation-provider"
										className="h-10 w-full rounded-md border bg-background px-3 text-sm"
										value={generationProvider}
										onChange={(event) => setGenerationProvider(event.target.value)}
									>
										{generationMode === "global_random" && (
											<option value="all">Alla providers</option>
										)}
										{apiProviders.map((provider) => (
											<option key={provider.provider_key} value={provider.provider_key}>
												{provider.provider_name}
											</option>
										))}
									</select>
								</div>
								<div className="space-y-2">
									<Label htmlFor="cal-generation-question-count">Antal frågor</Label>
									<Input
										id="cal-generation-question-count"
										type="number"
										min={1}
										max={100}
										value={generationQuestionCount}
										onChange={(event) =>
											setGenerationQuestionCount(
												Number.parseInt(event.target.value || "12", 10)
											)
										}
									/>
								</div>
								<div className="space-y-2">
									<Label htmlFor="cal-generation-difficulty">Svårighetsgrad</Label>
									<select
										id="cal-generation-difficulty"
										className="h-10 w-full rounded-md border bg-background px-3 text-sm"
										value={generationDifficultyProfile}
										onChange={(event) =>
											setGenerationDifficultyProfile(
												event.target.value === "lätt"
													? "lätt"
													: event.target.value === "medel"
														? "medel"
														: event.target.value === "svår"
															? "svår"
															: "mixed"
											)
										}
									>
										<option value="mixed">Blandad</option>
										<option value="lätt">Lätt</option>
										<option value="medel">Medel</option>
										<option value="svår">Svår</option>
									</select>
								</div>
								<div className="space-y-2">
									<Label htmlFor="cal-generation-eval-name">Eval-namn</Label>
									<Input
										id="cal-generation-eval-name"
										placeholder="scb-prisindex-mars-2026"
										value={generationEvalName}
										onChange={(event) => setGenerationEvalName(event.target.value)}
									/>
								</div>
							</div>

							{generationMode === "category" && (
								<div className="space-y-2">
									<Label htmlFor="cal-generation-category">Kategori</Label>
									<select
										id="cal-generation-category"
										className="h-10 w-full rounded-md border bg-background px-3 text-sm"
										value={generationCategory}
										onChange={(event) => setGenerationCategory(event.target.value)}
									>
										{generationCategoryOptions.length === 0 && (
											<option value="">Inga kategorier hittades</option>
										)}
										{generationCategoryOptions.map((option) => (
											<option key={option.category_id} value={option.category_id}>
												{option.category_name} ({option.category_id})
											</option>
										))}
									</select>
								</div>
							)}

							<div className="flex flex-wrap items-center gap-2">
								<Button
									onClick={handleGenerateEvalLibraryFile}
									disabled={isGeneratingEvalFile}
								>
									{isGeneratingEvalFile ? "Genererar..." : "Generera + spara eval JSON"}
								</Button>
								{selectedLibraryPath && (
									<Badge variant="outline">Vald fil: {selectedLibraryPath}</Badge>
								)}
							</div>

							{/* Eval library files */}
							<div className="rounded border p-3 space-y-2">
								<div className="flex items-center justify-between gap-2">
									<p className="text-sm font-medium">Sparade eval-filer (/eval/api)</p>
									<Button
										variant="outline"
										size="sm"
										onClick={() =>
											queryClient.invalidateQueries({
												queryKey: ["admin-tool-eval-library-files"],
											})
										}
									>
										Uppdatera lista
									</Button>
								</div>
								<div className="space-y-2">
									{(evalLibraryFiles?.items ?? []).length === 0 ? (
										<p className="text-xs text-muted-foreground">Inga sparade filer ännu.</p>
									) : (
										(evalLibraryFiles?.items ?? []).slice(0, 25).map((item) => (
											<div
												key={item.relative_path}
												className="flex flex-wrap items-center justify-between gap-2 rounded border p-2"
											>
												<div className="space-y-1">
													<p className="text-xs font-medium">{item.file_name}</p>
													<p className="text-xs text-muted-foreground">
														{item.relative_path} ·{" "}
														{new Date(item.created_at).toLocaleString("sv-SE")}
														{typeof item.test_count === "number"
															? ` · ${item.test_count} frågor`
															: ""}
													</p>
												</div>
												<div className="flex items-center gap-2">
													<Button
														variant={selectedLibraryPath === item.relative_path ? "default" : "outline"}
														size="sm"
														onClick={() => loadEvalLibraryFile(item.relative_path)}
														disabled={isLoadingLibraryFile}
													>
														Ladda i eval-input
													</Button>
													<Button
														variant={selectedHoldoutLibraryPath === item.relative_path ? "default" : "outline"}
														size="sm"
														onClick={() => loadEvalLibraryFileToHoldout(item.relative_path)}
														disabled={isLoadingLibraryFile}
													>
														Ladda i holdout
													</Button>
												</div>
											</div>
										))
									)}
								</div>
							</div>
						</CardContent>
					</Card>
					)}

					{/* Eval run controls */}
					{(showAgentSections || showApiSections) && (
					<Card>
						<CardHeader>
							<CardTitle>Steg 2: Kör Agentval Eval och API Input Eval</CardTitle>
							<CardDescription>
								Testa hela agentvalet och API-input i dry-run.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="flex flex-wrap items-center gap-3">
								<Input type="file" accept="application/json" onChange={uploadEvalFile} className="max-w-sm" />
								<div className="flex items-center gap-2">
									<Label htmlFor="cal-retrieval-limit">Retrieval K</Label>
									<Input
										id="cal-retrieval-limit"
										type="number"
										value={retrievalLimit}
										onChange={(e) => setRetrievalLimit(Number.parseInt(e.target.value || "5", 10))}
										className="w-24"
										min={1}
										max={15}
									/>
								</div>
								<div className="flex items-center gap-2">
									<Switch checked={includeDraftMetadata} onCheckedChange={setIncludeDraftMetadata} />
									<span className="text-sm">Inkludera osparad draft</span>
								</div>
								<div className="flex items-center gap-2">
									<Switch checked={useLlmSupervisorReview} onCheckedChange={setUseLlmSupervisorReview} />
									<span className="text-sm">LLM-granskning</span>
								</div>
								<Button onClick={handleRunEvaluation} disabled={isEvaluating || isEvalJobRunning}>
									{isEvaluating
										? "Startar agentval-eval..."
										: isEvalJobRunning
											? "Agentval-eval körs..."
											: "Run Agentval Eval"}
								</Button>
								<Button
									variant="outline"
									onClick={handleRunApiInputEvaluation}
									disabled={isApiInputEvaluating || isApiInputEvalJobRunning}
								>
									{isApiInputEvaluating
										? "Startar API input eval..."
										: isApiInputEvalJobRunning
											? "API input eval körs..."
											: "Run API Input Eval (dry-run)"}
								</Button>
							</div>
							<div className="rounded border p-3 space-y-3">
								<div className="flex items-center justify-between gap-2">
									<p className="text-sm font-medium">Eval JSON</p>
									<Button
										variant="outline"
										size="sm"
										onClick={() => setShowEvalJsonInput((prev) => !prev)}
									>
										{showEvalJsonInput ? "Minimera JSON-fält" : "Visa JSON-fält"}
									</Button>
								</div>
								{showEvalJsonInput ? (
									<Textarea
										placeholder='{"eval_name":"...","tests":[...]}'
										value={evalInput}
										onChange={(e) => setEvalInput(e.target.value)}
										rows={12}
										className="font-mono text-xs"
									/>
								) : (
									<p className="text-xs text-muted-foreground">JSON-fältet är minimerat.</p>
								)}
							</div>
							<div className="rounded border p-3 space-y-3">
								<div className="flex flex-wrap items-center justify-between gap-2">
									<div className="flex items-center gap-2">
										<Switch checked={useHoldoutSuite} onCheckedChange={setUseHoldoutSuite} />
										<p className="text-sm font-medium">Använd holdout-suite</p>
									</div>
									<Button
										variant="outline"
										size="sm"
										onClick={() => setShowHoldoutJsonInput((prev) => !prev)}
									>
										{showHoldoutJsonInput ? "Minimera holdout-fält" : "Visa holdout-fält"}
									</Button>
								</div>
								<p className="text-xs text-muted-foreground">
									Holdout-suite används för anti-overfitting.
								</p>
								<div className="flex flex-wrap items-center gap-2">
									<Input type="file" accept="application/json" onChange={uploadHoldoutFile} className="max-w-sm" />
									{selectedHoldoutLibraryPath && (
										<Badge variant="outline">Holdout-fil: {selectedHoldoutLibraryPath}</Badge>
									)}
								</div>
								{showHoldoutJsonInput ? (
									<Textarea
										placeholder='{"tests":[...]}'
										value={holdoutInput}
										onChange={(e) => setHoldoutInput(e.target.value)}
										rows={8}
										className="font-mono text-xs"
									/>
								) : (
									<p className="text-xs text-muted-foreground">Holdout-fältet är minimerat.</p>
								)}
							</div>
							{evalInputError && (
								<Alert variant="destructive">
									<AlertCircle className="h-4 w-4" />
									<AlertDescription>{evalInputError}</AlertDescription>
								</Alert>
							)}
						</CardContent>
					</Card>
					)}

					{/* Agentval job status */}
					{showAgentSections && evalJobId && (
						<Card>
							<CardHeader>
								<CardTitle>Steg 2A: Agentval-status per fråga</CardTitle>
								<CardDescription>
									Jobb {evalJobId} · status {evalJobStatus?.status ?? "pending"}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-3">
								<div className="flex flex-wrap items-center justify-between gap-2 text-sm">
									<div className="flex flex-wrap items-center gap-2">
										<Badge
											variant={
												evalJobStatus?.status === "failed"
													? "destructive"
													: evalJobStatus?.status === "completed"
														? "default"
														: "secondary"
											}
										>
											{evalJobStatus?.status ?? "pending"}
										</Badge>
										<span>
											{evalJobStatus?.completed_tests ?? 0}/{evalJobStatus?.total_tests ?? 0} frågor
										</span>
									</div>
									<div className="flex items-center gap-2">
										<Button variant="outline" size="sm" onClick={() => handleExportEvalRun("tool_selection", "json")} disabled={!evalJobStatus}>
											<Download className="h-4 w-4 mr-1" />Export JSON
										</Button>
										<Button variant="outline" size="sm" onClick={() => handleExportEvalRun("tool_selection", "yaml")} disabled={!evalJobStatus}>
											<Download className="h-4 w-4 mr-1" />Export YAML
										</Button>
									</div>
								</div>
								{evalJobStatus?.error && (
									<Alert variant="destructive">
										<AlertCircle className="h-4 w-4" />
										<AlertDescription>{evalJobStatus.error}</AlertDescription>
									</Alert>
								)}
								<div className="space-y-2">
									{(evalJobStatus?.case_statuses ?? []).map((caseStatus) => (
										<div key={caseStatus.test_id} className="rounded border p-2 text-xs space-y-1">
											<div className="flex items-center justify-between gap-2">
												<p className="font-medium">{caseStatus.test_id}</p>
												<Badge variant={caseStatus.status === "failed" ? "destructive" : caseStatus.status === "completed" ? "default" : caseStatus.status === "running" ? "secondary" : "outline"}>
													{caseStatus.status}
												</Badge>
											</div>
											<p className="text-muted-foreground">{caseStatus.question}</p>
											{caseStatus.selected_route && (
												<p className="text-muted-foreground">Route: {caseStatus.selected_route}{caseStatus.selected_sub_route ? ` / ${caseStatus.selected_sub_route}` : ""}</p>
											)}
											{caseStatus.selected_agent && <p className="text-muted-foreground">Vald agent: {caseStatus.selected_agent}</p>}
											{caseStatus.selected_tool && <p className="text-muted-foreground">Valt verktyg: {caseStatus.selected_tool}</p>}
											{caseStatus.expected_normalized && <Badge variant="secondary">Expected normaliserad</Badge>}
											{caseStatus.consistency_warnings?.length > 0 && (
												<p className="text-amber-400">Konsistensvarning: {caseStatus.consistency_warnings.join(" · ")}</p>
											)}
											{typeof caseStatus.passed === "boolean" && (
												<p className="text-muted-foreground">Resultat: {caseStatus.passed ? "Rätt" : "Fel"}</p>
											)}
											{caseStatus.error && <p className="text-red-500">{caseStatus.error}</p>}
										</div>
									))}
								</div>
							</CardContent>
						</Card>
					)}

					{/* API Input job status */}
					{showApiSections && apiInputEvalJobId && (
						<Card>
							<CardHeader>
								<CardTitle>Steg 3A: API input-status per fråga</CardTitle>
								<CardDescription>
									Jobb {apiInputEvalJobId} · status {apiInputEvalJobStatus?.status ?? "pending"}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-3">
								<div className="flex flex-wrap items-center justify-between gap-2 text-sm">
									<div className="flex flex-wrap items-center gap-2">
										<Badge variant={apiInputEvalJobStatus?.status === "failed" ? "destructive" : apiInputEvalJobStatus?.status === "completed" ? "default" : "secondary"}>
											{apiInputEvalJobStatus?.status ?? "pending"}
										</Badge>
										<span>{apiInputEvalJobStatus?.completed_tests ?? 0}/{apiInputEvalJobStatus?.total_tests ?? 0} frågor</span>
									</div>
									<div className="flex items-center gap-2">
										<Button variant="outline" size="sm" onClick={() => handleExportEvalRun("api_input", "json")} disabled={!apiInputEvalJobStatus}>
											<Download className="h-4 w-4 mr-1" />Export JSON
										</Button>
										<Button variant="outline" size="sm" onClick={() => handleExportEvalRun("api_input", "yaml")} disabled={!apiInputEvalJobStatus}>
											<Download className="h-4 w-4 mr-1" />Export YAML
										</Button>
									</div>
								</div>
								{apiInputEvalJobStatus?.error && (
									<Alert variant="destructive">
										<AlertCircle className="h-4 w-4" />
										<AlertDescription>{apiInputEvalJobStatus.error}</AlertDescription>
									</Alert>
								)}
								<div className="space-y-2">
									{(apiInputEvalJobStatus?.case_statuses ?? []).map((caseStatus) => (
										<div key={`api-input-${caseStatus.test_id}`} className="rounded border p-2 text-xs space-y-1">
											<div className="flex items-center justify-between gap-2">
												<p className="font-medium">{caseStatus.test_id}</p>
												<Badge variant={caseStatus.status === "failed" ? "destructive" : caseStatus.status === "completed" ? "default" : caseStatus.status === "running" ? "secondary" : "outline"}>
													{caseStatus.status}
												</Badge>
											</div>
											<p className="text-muted-foreground">{caseStatus.question}</p>
											{caseStatus.selected_route && <p className="text-muted-foreground">Route: {caseStatus.selected_route}{caseStatus.selected_sub_route ? ` / ${caseStatus.selected_sub_route}` : ""}</p>}
											{caseStatus.selected_agent && <p className="text-muted-foreground">Vald agent: {caseStatus.selected_agent}</p>}
											{caseStatus.selected_tool && <p className="text-muted-foreground">Valt verktyg: {caseStatus.selected_tool}</p>}
											{typeof caseStatus.passed === "boolean" && <p className="text-muted-foreground">Resultat: {caseStatus.passed ? "Rätt" : "Fel"}</p>}
											{caseStatus.error && <p className="text-red-500">{caseStatus.error}</p>}
										</div>
									))}
								</div>
							</CardContent>
						</Card>
					)}

					{/* Agentval eval results */}
					{showAgentSections && evaluationResult && (
						<>
							<Card>
								<CardHeader>
									<CardTitle>Steg 2B: Agentval Eval Resultat</CardTitle>
									<CardDescription>
										Metadata version {evaluationResult.metadata_version_hash} · search space {evaluationResult.search_space_id}
									</CardDescription>
								</CardHeader>
								<CardContent className="grid gap-4 md:grid-cols-4">
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Success rate</p>
										<p className="text-2xl font-semibold">{(evaluationResult.metrics.success_rate * 100).toFixed(1)}%</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Gated success</p>
										<p className="text-2xl font-semibold">{evaluationResult.metrics.gated_success_rate == null ? "-" : `${(evaluationResult.metrics.gated_success_rate * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Intent accuracy</p>
										<p className="text-2xl font-semibold">{evaluationResult.metrics.intent_accuracy == null ? "-" : `${(evaluationResult.metrics.intent_accuracy * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Route accuracy</p>
										<p className="text-2xl font-semibold">{evaluationResult.metrics.route_accuracy == null ? "-" : `${(evaluationResult.metrics.route_accuracy * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Agent accuracy</p>
										<p className="text-2xl font-semibold">{evaluationResult.metrics.agent_accuracy == null ? "-" : `${(evaluationResult.metrics.agent_accuracy * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Tool accuracy</p>
										<p className="text-2xl font-semibold">{evaluationResult.metrics.tool_accuracy == null ? "-" : `${(evaluationResult.metrics.tool_accuracy * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Plan accuracy</p>
										<p className="text-2xl font-semibold">{evaluationResult.metrics.plan_accuracy == null ? "-" : `${(evaluationResult.metrics.plan_accuracy * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Supervisor review</p>
										<p className="text-2xl font-semibold">{evaluationResult.metrics.supervisor_review_score == null ? "-" : `${(evaluationResult.metrics.supervisor_review_score * 100).toFixed(1)}%`}</p>
									</div>
								</CardContent>
							</Card>

							<DifficultyBreakdown title="Svårighetsgrad · Agentval Eval" items={evaluationResult.metrics.difficulty_breakdown ?? []} />
							<ComparisonInsights title="Diff mot föregående Agent/Tool-run" comparison={evaluationResult.comparison} />

							{/* Retrieval tuning in this eval */}
							<Card>
								<CardHeader><CardTitle>Steg 2C: Retrieval-vikter i denna eval</CardTitle></CardHeader>
								<CardContent className="space-y-3">
									<div className="grid gap-2 md:grid-cols-3">
										<Badge variant="outline">name: {evaluationResult.retrieval_tuning.name_match_weight}</Badge>
										<Badge variant="outline">keyword: {evaluationResult.retrieval_tuning.keyword_weight}</Badge>
										<Badge variant="outline">desc: {evaluationResult.retrieval_tuning.description_token_weight}</Badge>
										<Badge variant="outline">example: {evaluationResult.retrieval_tuning.example_query_weight}</Badge>
										<Badge variant="outline">namespace: {evaluationResult.retrieval_tuning.namespace_boost}</Badge>
										<Badge variant="outline">embedding: {evaluationResult.retrieval_tuning.embedding_weight}</Badge>
										<Badge variant="outline">rerank: {evaluationResult.retrieval_tuning.rerank_candidates}</Badge>
									</div>
									{evaluationResult.retrieval_tuning_suggestion && (
										<div className="rounded border p-3 space-y-2">
											<p className="text-sm font-medium">Föreslagen tuning</p>
											<p className="text-xs text-muted-foreground">{evaluationResult.retrieval_tuning_suggestion.rationale}</p>
											<div className="flex gap-2">
												<Button variant="outline" onClick={applyWeightSuggestionToDraft} disabled={isSavingRetrievalTuning}>
													Applicera viktförslag i draft
												</Button>
												<Button onClick={saveWeightSuggestion} disabled={isSavingRetrievalTuning}>
													Spara viktförslag
												</Button>
											</div>
										</div>
									)}
								</CardContent>
							</Card>

							{/* Per-test results */}
							<Card>
								<CardHeader><CardTitle>Steg 2D: Agentval-resultat per test</CardTitle></CardHeader>
								<CardContent className="space-y-3">
									{evaluationResult.results.map((result) => {
										const failureReasons = buildFailureReasons(result as unknown as Record<string, unknown>);
										return (
											<div key={result.test_id} className="rounded border p-3 space-y-2">
												<div className="flex items-center justify-between gap-2">
													<div className="flex items-center gap-2">
														<Badge variant="outline">{result.test_id}</Badge>
														{result.difficulty && <Badge variant="secondary">{formatDifficultyLabel(result.difficulty)}</Badge>}
														<Badge variant={result.passed ? "default" : "destructive"}>{result.passed ? "PASS" : "FAIL"}</Badge>
													</div>
													<div className="text-xs text-muted-foreground">
														{result.expected_tool || "-"} → {result.selected_tool || "-"}
													</div>
												</div>
												<p className="text-sm">{result.question}</p>
												<div className="flex flex-wrap gap-2">
													{result.passed_intent != null && <Badge variant={result.passed_intent ? "outline" : "destructive"}>intent {result.passed_intent ? "OK" : "MISS"}</Badge>}
													{result.passed_route != null && <Badge variant={result.passed_route ? "outline" : "destructive"}>route {result.passed_route ? "OK" : "MISS"}</Badge>}
													{result.passed_agent != null && <Badge variant={result.passed_agent ? "outline" : "destructive"}>agent {result.passed_agent ? "OK" : "MISS"}</Badge>}
													{result.passed_tool != null && <Badge variant={result.passed_tool ? "outline" : "destructive"}>tool {result.passed_tool ? "OK" : "MISS"}</Badge>}
												</div>
												{!result.passed && failureReasons.length > 0 && (
													<p className="text-xs text-red-400">Fail-orsak: {failureReasons.join(" · ")}</p>
												)}
												{result.supervisor_review_rationale && (
													<p className="text-xs text-muted-foreground">Supervisor: {result.supervisor_review_rationale}</p>
												)}
												<p className="text-xs text-muted-foreground">
													Retrieval: {result.retrieval_top_tools.join(", ") || "-"}
												</p>
											</div>
										);
									})}
								</CardContent>
							</Card>

							{/* Metadata suggestions */}
							<Card>
								<CardHeader>
									<CardTitle>Steg 2E: Metadata-förslag</CardTitle>
									<CardDescription>Acceptera förslag, spara och kör eval igen.</CardDescription>
								</CardHeader>
								<CardContent className="space-y-4">
									<div className="flex flex-wrap items-center gap-2">
										<Button variant="outline" onClick={regenerateSuggestions}>Regenerera förslag</Button>
										<Button onClick={applySelectedSuggestionsToDraft} disabled={!selectedSuggestionIds.size || isApplyingSuggestions}>Applicera valda i draft</Button>
										<Button onClick={saveSelectedSuggestions} disabled={!selectedSuggestionIds.size || isSavingSuggestions}>Spara valda förslag</Button>
										<Button onClick={handleRunEvaluation} disabled={isEvaluating || isEvalJobRunning}>Kör om eval</Button>
										<Badge variant="outline">{selectedSuggestions.length} valda</Badge>
									</div>
									{evaluationResult.suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">Inga förbättringsförslag hittades.</p>
									) : (
										<SuggestionDiffView
											suggestions={suggestionDiffItems}
											selectedIds={selectedSuggestionIds}
											onToggle={toggleSuggestion}
											onToggleAll={(selected) => {
												if (selected) {
													setSelectedSuggestionIds(
														new Set(evaluationResult.suggestions.map((s) => s.tool_id))
													);
												} else {
													setSelectedSuggestionIds(new Set());
												}
											}}
										/>
									)}
								</CardContent>
							</Card>

							{/* Tool prompt suggestions */}
							<Card>
								<CardHeader>
									<CardTitle>Steg 2F: Prompt-förslag från Agentval Eval</CardTitle>
								</CardHeader>
								<CardContent className="space-y-4">
									<div className="flex items-center gap-2">
										<Button onClick={saveSelectedToolPromptSuggestions} disabled={!selectedToolPromptSuggestionKeys.size || isSavingToolPromptSuggestions}>
											Spara valda promptförslag
										</Button>
										<Badge variant="outline">{selectedToolPromptSuggestions.length} valda</Badge>
									</div>
									{evaluationResult.prompt_suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">Inga promptförslag för denna run.</p>
									) : (
										<div className="space-y-3">
											{evaluationResult.prompt_suggestions.map((suggestion) => {
												const isSelected = selectedToolPromptSuggestionKeys.has(suggestion.prompt_key);
												return (
													<div key={`tool-prompt-${suggestion.prompt_key}`} className="rounded border p-3 space-y-2">
														<div className="flex items-center gap-2">
															<input type="checkbox" checked={isSelected} onChange={() => toggleToolPromptSuggestion(suggestion.prompt_key)} />
															<Badge variant="secondary">{suggestion.prompt_key}</Badge>
															<Badge variant="outline">{suggestion.failed_test_ids.length} fail-case(s)</Badge>
														</div>
														<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
														<div className="grid gap-3 md:grid-cols-2">
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Nuvarande</p>
																<pre className="text-[11px] whitespace-pre-wrap break-words">{suggestion.current_prompt}</pre>
															</div>
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Föreslagen</p>
																<pre className="text-[11px] whitespace-pre-wrap break-words">{suggestion.proposed_prompt}</pre>
															</div>
														</div>
													</div>
												);
											})}
										</div>
									)}
								</CardContent>
							</Card>

							{/* Intent suggestions */}
							<Card>
								<CardHeader><CardTitle>Steg 2G: Intent-förslag</CardTitle></CardHeader>
								<CardContent className="space-y-3">
									{evaluationResult.intent_suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">Inga intent-förslag för denna run.</p>
									) : (
										evaluationResult.intent_suggestions.map((suggestion) => (
											<div key={`intent-${suggestion.intent_id}`} className="rounded border p-3 space-y-2">
												<div className="flex items-center gap-2">
													<Badge variant="secondary">{suggestion.intent_id}</Badge>
													<Badge variant="outline">{suggestion.failed_test_ids.length} fail-case(s)</Badge>
												</div>
												<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
												<div className="grid gap-3 md:grid-cols-2">
													<div className="rounded bg-muted/50 p-2">
														<p className="text-xs font-medium mb-1">Nuvarande</p>
														<pre className="text-[11px] whitespace-pre-wrap break-words">{JSON.stringify(suggestion.current_definition, null, 2)}</pre>
													</div>
													<div className="rounded bg-muted/50 p-2">
														<p className="text-xs font-medium mb-1">Föreslagen</p>
														<pre className="text-[11px] whitespace-pre-wrap break-words">{JSON.stringify(suggestion.proposed_definition, null, 2)}</pre>
													</div>
												</div>
											</div>
										))
									)}
								</CardContent>
							</Card>
						</>
					)}

					{/* API Input eval results */}
					{showApiSections && apiInputEvaluationResult && (
						<>
							<Card>
								<CardHeader>
									<CardTitle>Steg 3B: API Input Eval Resultat</CardTitle>
									<CardDescription>
										Metadata version {apiInputEvaluationResult.metadata_version_hash} · search space {apiInputEvaluationResult.search_space_id}
									</CardDescription>
								</CardHeader>
								<CardContent className="grid gap-4 md:grid-cols-5">
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Success rate</p>
										<p className="text-2xl font-semibold">{(apiInputEvaluationResult.metrics.success_rate * 100).toFixed(1)}%</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Schema validity</p>
										<p className="text-2xl font-semibold">{apiInputEvaluationResult.metrics.schema_validity_rate == null ? "-" : `${(apiInputEvaluationResult.metrics.schema_validity_rate * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Required recall</p>
										<p className="text-2xl font-semibold">{apiInputEvaluationResult.metrics.required_field_recall == null ? "-" : `${(apiInputEvaluationResult.metrics.required_field_recall * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Field-value accuracy</p>
										<p className="text-2xl font-semibold">{apiInputEvaluationResult.metrics.field_value_accuracy == null ? "-" : `${(apiInputEvaluationResult.metrics.field_value_accuracy * 100).toFixed(1)}%`}</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Clarification accuracy</p>
										<p className="text-2xl font-semibold">{apiInputEvaluationResult.metrics.clarification_accuracy == null ? "-" : `${(apiInputEvaluationResult.metrics.clarification_accuracy * 100).toFixed(1)}%`}</p>
									</div>
								</CardContent>
							</Card>

							<DifficultyBreakdown title="Svårighetsgrad · API Input Eval" items={apiInputEvaluationResult.metrics.difficulty_breakdown ?? []} />
							<ComparisonInsights title="Diff mot föregående API Input-run" comparison={apiInputEvaluationResult.comparison} />

							{/* Holdout metrics */}
							{apiInputEvaluationResult.holdout_metrics && (
								<Card>
									<CardHeader>
										<CardTitle>Steg 4: Holdout-suite</CardTitle>
										<CardDescription>Separat mätning för anti-overfitting.</CardDescription>
									</CardHeader>
									<CardContent className="grid gap-4 md:grid-cols-4">
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Holdout success</p>
											<p className="text-2xl font-semibold">{(apiInputEvaluationResult.holdout_metrics.success_rate * 100).toFixed(1)}%</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Schema validity</p>
											<p className="text-2xl font-semibold">{apiInputEvaluationResult.holdout_metrics.schema_validity_rate == null ? "-" : `${(apiInputEvaluationResult.holdout_metrics.schema_validity_rate * 100).toFixed(1)}%`}</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Required recall</p>
											<p className="text-2xl font-semibold">{apiInputEvaluationResult.holdout_metrics.required_field_recall == null ? "-" : `${(apiInputEvaluationResult.holdout_metrics.required_field_recall * 100).toFixed(1)}%`}</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Holdout cases</p>
											<p className="text-2xl font-semibold">{apiInputEvaluationResult.holdout_metrics.passed_tests}/{apiInputEvaluationResult.holdout_metrics.total_tests}</p>
										</div>
									</CardContent>
								</Card>
							)}

							{/* API Input results per test */}
							<Card>
								<CardHeader><CardTitle>Steg 3C: API Input resultat per test</CardTitle></CardHeader>
								<CardContent className="space-y-3">
									{apiInputEvaluationResult.results.map((result) => {
										const failureReasons = buildFailureReasons(result as unknown as Record<string, unknown>);
										return (
											<div key={`api-result-${result.test_id}`} className="rounded border p-3 space-y-2">
												<div className="flex items-center justify-between gap-2">
													<div className="flex items-center gap-2">
														<Badge variant="outline">{result.test_id}</Badge>
														{result.difficulty && <Badge variant="secondary">{formatDifficultyLabel(result.difficulty)}</Badge>}
														<Badge variant={result.passed ? "default" : "destructive"}>{result.passed ? "PASS" : "FAIL"}</Badge>
													</div>
													<div className="text-xs text-muted-foreground">
														{result.expected_tool || "-"} → {result.selected_tool || "-"}
													</div>
												</div>
												<p className="text-sm">{result.question}</p>
												<div className="flex flex-wrap gap-2">
													{result.passed_intent != null && <Badge variant={result.passed_intent ? "outline" : "destructive"}>intent {result.passed_intent ? "OK" : "MISS"}</Badge>}
													{result.passed_route != null && <Badge variant={result.passed_route ? "outline" : "destructive"}>route {result.passed_route ? "OK" : "MISS"}</Badge>}
													{result.passed_agent != null && <Badge variant={result.passed_agent ? "outline" : "destructive"}>agent {result.passed_agent ? "OK" : "MISS"}</Badge>}
													{result.passed_tool != null && <Badge variant={result.passed_tool ? "outline" : "destructive"}>tool {result.passed_tool ? "OK" : "MISS"}</Badge>}
													{result.passed_api_input != null && <Badge variant={result.passed_api_input ? "outline" : "destructive"}>api-input {result.passed_api_input ? "OK" : "MISS"}</Badge>}
												</div>
												{!result.passed && failureReasons.length > 0 && (
													<p className="text-xs text-red-400">Fail-orsak: {failureReasons.join(" · ")}</p>
												)}
												<div className="grid gap-3 md:grid-cols-2">
													<div className="rounded bg-muted/40 p-2 space-y-1">
														<p className="text-xs font-medium">Proposed arguments</p>
														<pre className="text-[11px] whitespace-pre-wrap break-all text-muted-foreground">
															{JSON.stringify(result.proposed_arguments ?? {}, null, 2)}
														</pre>
													</div>
													<div className="rounded bg-muted/40 p-2 space-y-1">
														<p className="text-xs font-medium">Validering</p>
														<p className="text-[11px] text-muted-foreground">
															Schema-valid: {result.schema_valid == null ? "-" : result.schema_valid ? "Ja" : "Nej"}
														</p>
														<p className="text-[11px] text-muted-foreground">
															Missing required: {result.missing_required_fields.join(", ") || "-"}
														</p>
														<p className="text-[11px] text-muted-foreground">
															Unexpected: {result.unexpected_fields.join(", ") || "-"}
														</p>
													</div>
												</div>
											</div>
										);
									})}
								</CardContent>
							</Card>

							{/* API Input prompt suggestions */}
							<Card>
								<CardHeader>
									<CardTitle>Steg 3D: Prompt-förslag från API Input Eval</CardTitle>
								</CardHeader>
								<CardContent className="space-y-4">
									<div className="flex flex-wrap items-center gap-2">
										<Button onClick={saveSelectedPromptSuggestions} disabled={!selectedPromptSuggestionKeys.size || isSavingPromptSuggestions}>
											Spara valda promptförslag
										</Button>
										<Button variant="outline" onClick={handleRunApiInputEvaluation} disabled={isApiInputEvaluating || isApiInputEvalJobRunning}>
											Kör om API input eval
										</Button>
										<Badge variant="outline">{selectedPromptSuggestions.length} valda</Badge>
									</div>
									{apiInputEvaluationResult.prompt_suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">Inga promptförslag.</p>
									) : (
										<div className="space-y-3">
											{apiInputEvaluationResult.prompt_suggestions.map((suggestion) => {
												const isSelected = selectedPromptSuggestionKeys.has(suggestion.prompt_key);
												return (
													<div key={`prompt-${suggestion.prompt_key}`} className="rounded border p-3 space-y-2">
														<div className="flex items-center gap-2">
															<input type="checkbox" checked={isSelected} onChange={() => togglePromptSuggestion(suggestion.prompt_key)} />
															<Badge variant="secondary">{suggestion.prompt_key}</Badge>
															<Badge variant="outline">{suggestion.failed_test_ids.length} fail-case(s)</Badge>
														</div>
														<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
														<div className="grid gap-3 md:grid-cols-2">
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Nuvarande</p>
																<pre className="text-[11px] whitespace-pre-wrap break-words max-h-48 overflow-y-auto">{suggestion.current_prompt}</pre>
															</div>
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Föreslagen</p>
																<pre className="text-[11px] whitespace-pre-wrap break-words max-h-48 overflow-y-auto">{suggestion.proposed_prompt}</pre>
															</div>
														</div>
													</div>
												);
											})}
										</div>
									)}
								</CardContent>
							</Card>

							{/* API Input intent suggestions */}
							<Card>
								<CardHeader><CardTitle>Steg 3E: Intent-förslag</CardTitle></CardHeader>
								<CardContent className="space-y-3">
									{apiInputEvaluationResult.intent_suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">Inga intent-förslag.</p>
									) : (
										apiInputEvaluationResult.intent_suggestions.map((suggestion) => (
											<div key={`api-intent-${suggestion.intent_id}`} className="rounded border p-3 space-y-2">
												<div className="flex items-center gap-2">
													<Badge variant="secondary">{suggestion.intent_id}</Badge>
													<Badge variant="outline">{suggestion.failed_test_ids.length} fail-case(s)</Badge>
												</div>
												<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
												<div className="grid gap-3 md:grid-cols-2">
													<div className="rounded bg-muted/50 p-2">
														<p className="text-xs font-medium mb-1">Nuvarande</p>
														<pre className="text-[11px] whitespace-pre-wrap break-words">{JSON.stringify(suggestion.current_definition, null, 2)}</pre>
													</div>
													<div className="rounded bg-muted/50 p-2">
														<p className="text-xs font-medium mb-1">Föreslagen</p>
														<pre className="text-[11px] whitespace-pre-wrap break-words">{JSON.stringify(suggestion.proposed_definition, null, 2)}</pre>
													</div>
												</div>
											</div>
										))
									)}
								</CardContent>
							</Card>
						</>
					)}
				</div>
			)}

			{/* ================================================================ */}
			{/* STEG 3: AUTO-OPTIMERING                                         */}
			{/* ================================================================ */}
			{calibrationStep === "auto" && (
				<Card>
					<CardHeader>
						<CardTitle>Auto-optimering</CardTitle>
						<CardDescription>
							Loopa generering → eval → förslag → uppdatering tills önskad success rate nås.
						</CardDescription>
					</CardHeader>
					<CardContent className="space-y-4">
						<div className="grid gap-3 md:grid-cols-4">
							<div className="space-y-2">
								<Label htmlFor="cal-auto-target">Target success</Label>
								<Input id="cal-auto-target" type="number" min={0} max={1} step={0.01} value={autoTargetSuccessRate} onChange={(e) => setAutoTargetSuccessRate(Number.parseFloat(e.target.value || "0.85"))} />
							</div>
							<div className="space-y-2">
								<Label htmlFor="cal-auto-max">Max iterationer</Label>
								<Input id="cal-auto-max" type="number" min={1} max={30} value={autoMaxIterations} onChange={(e) => setAutoMaxIterations(Number.parseInt(e.target.value || "6", 10))} />
							</div>
							<div className="space-y-2">
								<Label htmlFor="cal-auto-patience">Patience</Label>
								<Input id="cal-auto-patience" type="number" min={1} max={12} value={autoPatience} onChange={(e) => setAutoPatience(Number.parseInt(e.target.value || "2", 10))} />
							</div>
							<div className="space-y-2">
								<Label htmlFor="cal-auto-delta">Min förbättring</Label>
								<Input id="cal-auto-delta" type="number" min={0} max={0.25} step={0.001} value={autoMinImprovementDelta} onChange={(e) => setAutoMinImprovementDelta(Number.parseFloat(e.target.value || "0.005"))} />
							</div>
						</div>

						<div className="rounded border p-3 space-y-3">
							<div className="flex items-center gap-2">
								<Switch checked={autoUseHoldoutSuite} onCheckedChange={setAutoUseHoldoutSuite} />
								<span className="text-sm font-medium">Inkludera auto-genererad holdout-suite</span>
							</div>
							<p className="text-xs text-muted-foreground">
								Auto-läget jämför train och holdout per iteration för att upptäcka överanpassning.
							</p>
							{autoUseHoldoutSuite && (
								<div className="grid gap-3 md:grid-cols-2">
									<div className="space-y-2">
										<Label htmlFor="cal-auto-holdout-count">Holdout antal frågor</Label>
										<Input id="cal-auto-holdout-count" type="number" min={1} max={100} value={autoHoldoutQuestionCount} onChange={(e) => setAutoHoldoutQuestionCount(Number.parseInt(e.target.value || "8", 10))} />
									</div>
									<div className="space-y-2">
										<Label htmlFor="cal-auto-holdout-diff">Holdout svårighetsprofil</Label>
										<select
											id="cal-auto-holdout-diff"
											className="h-10 w-full rounded-md border bg-background px-3 text-sm"
											value={autoHoldoutDifficultyProfile}
											onChange={(e) => setAutoHoldoutDifficultyProfile(e.target.value === "lätt" ? "lätt" : e.target.value === "medel" ? "medel" : e.target.value === "svår" ? "svår" : "mixed")}
										>
											<option value="mixed">Blandad</option>
											<option value="lätt">Lätt</option>
											<option value="medel">Medel</option>
											<option value="svår">Svår</option>
										</select>
									</div>
								</div>
							)}
						</div>

						<div className="flex flex-wrap items-center gap-2">
							<Button onClick={handleStartAutoLoop} disabled={isStartingAutoLoop || isAutoLoopRunning}>
								{isStartingAutoLoop ? "Startar auto-läge..." : isAutoLoopRunning ? "Auto-läge körs..." : "Starta auto-läge"}
							</Button>
							{autoLoopJobId && <Badge variant="outline">Jobb: {autoLoopJobId.slice(0, 8)}</Badge>}
							{autoLoopJobStatus && (
								<Badge variant={autoLoopJobStatus.status === "failed" ? "destructive" : autoLoopJobStatus.status === "completed" ? "default" : "secondary"}>
									{autoLoopJobStatus.status}
								</Badge>
							)}
						</div>

						{autoLoopJobStatus && (
							<div className="rounded bg-muted/30 p-3 space-y-2">
								<div className="grid gap-2 md:grid-cols-4 text-xs">
									<p>Iteration: {autoLoopJobStatus.completed_iterations}/{autoLoopJobStatus.total_iterations}</p>
									<p>Bästa success: {formatPercent(autoLoopJobStatus.best_success_rate)}</p>
									<p>Utebliven förbättring: {autoLoopJobStatus.no_improvement_runs}</p>
									<p>{autoLoopJobStatus.message || "-"}</p>
								</div>
								{(autoLoopJobStatus.iterations ?? []).length > 0 && (
									<div className="space-y-1">
										{autoLoopJobStatus.iterations.slice(-6).map((item) => (
											<p key={`auto-iter-${item.iteration}`} className="text-xs text-muted-foreground">
												Iter {item.iteration}: train {formatPercent(item.success_rate)}
												{typeof item.success_delta_vs_previous === "number" ? ` (${formatSignedPercent(item.success_delta_vs_previous)})` : ""}
												{typeof item.holdout_success_rate === "number" ? ` · holdout ${formatPercent(item.holdout_success_rate)}` : ""}
												{typeof item.combined_score === "number" ? ` · kombinerad ${formatPercent(item.combined_score)}` : ""}
												{item.note ? ` · ${item.note}` : ""}
											</p>
										))}
									</div>
								)}
								{autoLoopJobStatus.status === "completed" && autoLoopJobStatus.result && (
									<div className="space-y-1">
										<p className="text-xs text-muted-foreground">
											Stop-orsak: {formatAutoLoopStopReason(autoLoopJobStatus.result.stop_reason)}
										</p>
										{autoLoopJobStatus.result.final_holdout_evaluation && (
											<p className="text-xs text-muted-foreground">
												Slutlig holdout success: {formatPercent(autoLoopJobStatus.result.final_holdout_evaluation.metrics.success_rate)}
											</p>
										)}
									</div>
								)}
								{autoLoopPromptDrafts.length > 0 && (
									<div className="flex flex-wrap items-center gap-2">
										<Badge variant="outline">{autoLoopPromptDrafts.length} promptutkast redo</Badge>
										<Button variant="outline" size="sm" onClick={saveAutoLoopPromptDraftSuggestions} disabled={isSavingAutoLoopPromptDrafts}>
											{isSavingAutoLoopPromptDrafts ? "Sparar..." : "Spara promptutkast"}
										</Button>
									</div>
								)}
							</div>
						)}
					</CardContent>
				</Card>
			)}

			{/* ================================================================ */}
			{/* LIFECYCLE PROMOTION (visas alltid)                              */}
			{/* ================================================================ */}
			{lifecycleData && lifecycleData.review_count > 0 && (
				<Card>
					<CardHeader>
						<CardTitle>Lifecycle-promotion</CardTitle>
						<CardDescription>
							Verktyg i Review som uppnått krävd success rate kan befordras till Live.
						</CardDescription>
					</CardHeader>
					<CardContent className="space-y-4">
						<div className="grid gap-3 md:grid-cols-3 text-sm">
							<div className="rounded border p-3">
								<p className="text-xs text-muted-foreground">Live</p>
								<p className="text-2xl font-semibold text-green-600">{lifecycleData.live_count}</p>
							</div>
							<div className="rounded border p-3">
								<p className="text-xs text-muted-foreground">Review</p>
								<p className="text-2xl font-semibold text-amber-600">{lifecycleData.review_count}</p>
							</div>
							<div className="rounded border p-3">
								<p className="text-xs text-muted-foreground">Totalt</p>
								<p className="text-2xl font-semibold">{lifecycleData.total_count}</p>
							</div>
						</div>
						<div className="max-h-64 overflow-auto space-y-1">
							{lifecycleData.tools
								.filter((t) => t.status === "review")
								.map((tool) => (
									<div key={`promo-${tool.tool_id}`} className="flex items-center justify-between gap-2 rounded border p-2 text-xs">
										<span className="font-mono truncate max-w-[250px]">{tool.tool_id}</span>
										<LifecycleBadge
											status={tool.status as "live" | "review"}
											successRate={tool.success_rate}
											requiredSuccessRate={tool.required_success_rate}
										/>
									</div>
								))}
						</div>
						<Button onClick={handleBulkPromote} disabled={isPromoting}>
							{isPromoting ? "Befordrar..." : "Befordra kvalificerade till Live"}
						</Button>
					</CardContent>
				</Card>
			)}
		</div>
	);
}
