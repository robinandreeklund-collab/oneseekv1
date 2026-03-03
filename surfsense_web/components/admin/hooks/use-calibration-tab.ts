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
	ToolEvaluationResponse,
	ToolEvaluationTestCase,
	ToolMetadataItem,
	ToolMetadataUpdateItem,
	ToolRetrievalTuning,
} from "@/contracts/types/admin-tool-settings.types";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";
import { adminToolLifecycleApiService } from "@/lib/apis/admin-tool-lifecycle-api.service";
import type { SuggestionDiffItem } from "@/components/admin/shared/suggestion-diff-view";
import {
	downloadTextFile,
	buildEvalExportFileName,
	parseEvalTestCases,
	parseApiInputEvalInput as parseApiInputEvalInputUtil,
} from "@/components/admin/hooks/use-eval-parsers";

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
type ExportableEvalJobStatus =
	| ToolEvaluationJobStatusResponse
	| ToolApiInputEvaluationJobStatusResponse;

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useCalibrationTab() {
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

	// --- Audit state (Steg 1) ---
	const [isRunningAudit, setIsRunningAudit] = useState(false);
	const [auditResult, setAuditResult] = useState<MetadataCatalogAuditRunResponse | null>(null);
	const [isRunningSeparation, setIsRunningSeparation] = useState(false);
	const [separationResult, setSeparationResult] = useState<MetadataCatalogSeparationResponse | null>(null);
	const [auditMaxTools, setAuditMaxTools] = useState(25);
	const [auditRetrievalLimit, setAuditRetrievalLimit] = useState(5);
	const [auditProviderFilter, setAuditProviderFilter] = useState<string>("all");

	// --- Lifecycle promotion state ---
	const [isPromoting, setIsPromoting] = useState(false);

	// -----------------------------------------------------------------------
	// Queries
	// -----------------------------------------------------------------------

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

	// -----------------------------------------------------------------------
	// Memos
	// -----------------------------------------------------------------------

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

	// -----------------------------------------------------------------------
	// Effects
	// -----------------------------------------------------------------------

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

	// -----------------------------------------------------------------------
	// Handlers
	// -----------------------------------------------------------------------

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
		} catch (_error) {
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
		} catch (_error) {
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

	const parseEvalInput = () => {
		setEvalInputError(null);
		const result = parseEvalTestCases(evalInput);
		if (!result.ok) { setEvalInputError(result.error); return null; }
		return result;
	};

	const parseApiInputEvalInput = () => {
		setEvalInputError(null);
		const result = parseApiInputEvalInputUtil(evalInput, holdoutInput, useHoldoutSuite);
		if (!result.ok) { setEvalInputError(result.error); return null; }
		return result;
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
		} catch (_err) {
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

	const toggleAllSuggestions = (selected: boolean) => {
		if (selected) {
			setSelectedSuggestionIds(
				new Set(evaluationResult?.suggestions.map((s) => s.tool_id) ?? [])
			);
		} else {
			setSelectedSuggestionIds(new Set());
		}
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
		} catch (_error) {
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
		} catch (_error) {
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
		} catch (_error) {
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

	// --- Audit handlers (Steg 1) ---

	const handleRunAudit = async () => {
		setIsRunningAudit(true);
		try {
			const result = await adminToolSettingsApiService.runMetadataCatalogAudit({
				search_space_id: data?.search_space_id,
				metadata_patch: includeDraftMetadata ? metadataPatch : [],
				max_tools: auditMaxTools,
				retrieval_limit: auditRetrievalLimit,
				...(auditProviderFilter !== "all" ? { provider_filter: auditProviderFilter } : {}),
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
				...(auditProviderFilter !== "all" ? { provider_filter: auditProviderFilter } : {}),
			});
			setSeparationResult(result);
			toast.success("Separation klar");
		} catch (_error) {
			toast.error("Separation misslyckades");
		} finally {
			setIsRunningSeparation(false);
		}
	};

	const handleApplySeparation = async () => {
		if (!separationResult) return;
		try {
			await adminToolSettingsApiService.updateMetadataCatalog({
				tool_updates: separationResult.proposed_tool_metadata_patch,
			});
			await refetch();
			toast.success("Separationsförslag applicerade");
		} catch (_error) {
			toast.error("Kunde inte applicera separationsförslag");
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

	const handleChangePhase = async (newPhase: LiveRoutingPhase) => {
		if (!draftRetrievalTuning) return;
		const updated = { ...draftRetrievalTuning, live_routing_phase: newPhase };
		try {
			await adminToolSettingsApiService.updateRetrievalTuning(updated);
			setDraftRetrievalTuning(updated);
			await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			toast.success(`Fas ändrad till ${newPhase}`);
		} catch (_error) {
			toast.error("Kunde inte byta fas");
		}
	};

	const refreshEvalLibraryFiles = () => {
		void queryClient.invalidateQueries({ queryKey: ["admin-tool-eval-library-files"] });
	};

	// -----------------------------------------------------------------------
	// Return
	// -----------------------------------------------------------------------

	return {
		// Data & loading
		data, isLoading, error,
		lifecycleData, apiProviders, evalLibraryFiles,
		evalJobStatus, apiInputEvalJobStatus, autoLoopJobStatus,

		// Step navigation
		calibrationStep, setCalibrationStep,
		evaluationStepTab, setEvaluationStepTab,
		showGuideSections, showGenerationSections, showAgentSections, showApiSections,

		// Fas-panel
		draftRetrievalTuning, handleChangePhase,

		// Audit (Steg 1)
		auditProviderFilter, setAuditProviderFilter,
		auditMaxTools, setAuditMaxTools,
		auditRetrievalLimit, setAuditRetrievalLimit,
		includeDraftMetadata, setIncludeDraftMetadata,
		isRunningAudit, handleRunAudit,
		isRunningSeparation, handleRunSeparation,
		auditResult, separationResult, handleApplySeparation,

		// Generation
		generationMode, setGenerationMode,
		generationEvalType, setGenerationEvalType,
		generationProvider, setGenerationProvider,
		generationQuestionCount, setGenerationQuestionCount,
		generationDifficultyProfile, setGenerationDifficultyProfile,
		generationEvalName, setGenerationEvalName,
		generationCategory, setGenerationCategory,
		generationCategoryOptions,
		isGeneratingEvalFile, handleGenerateEvalLibraryFile,
		selectedLibraryPath, selectedHoldoutLibraryPath,
		isLoadingLibraryFile, loadEvalLibraryFile, loadEvalLibraryFileToHoldout,
		refreshEvalLibraryFiles,

		// Eval input
		evalInput, setEvalInput,
		showEvalJsonInput, setShowEvalJsonInput,
		useHoldoutSuite, setUseHoldoutSuite,
		showHoldoutJsonInput, setShowHoldoutJsonInput,
		holdoutInput, setHoldoutInput,
		uploadEvalFile, uploadHoldoutFile,
		evalInputError,
		retrievalLimit, setRetrievalLimit,
		useLlmSupervisorReview, setUseLlmSupervisorReview,

		// Eval jobs
		isEvaluating, handleRunEvaluation,
		isApiInputEvaluating, handleRunApiInputEvaluation,
		isEvalJobRunning, isApiInputEvalJobRunning,
		evalJobId, apiInputEvalJobId,
		handleExportEvalRun,

		// Results
		evaluationResult, apiInputEvaluationResult,

		// Suggestions
		selectedSuggestionIds, suggestionDiffItems,
		toggleSuggestion, toggleAllSuggestions,
		selectedSuggestions,
		regenerateSuggestions,
		applySelectedSuggestionsToDraft, isApplyingSuggestions,
		saveSelectedSuggestions, isSavingSuggestions,

		selectedToolPromptSuggestionKeys,
		toggleToolPromptSuggestion,
		saveSelectedToolPromptSuggestions, isSavingToolPromptSuggestions,

		selectedPromptSuggestionKeys,
		togglePromptSuggestion,
		saveSelectedPromptSuggestions, isSavingPromptSuggestions,

		applyWeightSuggestionToDraft, saveWeightSuggestion, isSavingRetrievalTuning,

		// Auto-loop
		autoTargetSuccessRate, setAutoTargetSuccessRate,
		autoMaxIterations, setAutoMaxIterations,
		autoPatience, setAutoPatience,
		autoMinImprovementDelta, setAutoMinImprovementDelta,
		autoUseHoldoutSuite, setAutoUseHoldoutSuite,
		autoHoldoutQuestionCount, setAutoHoldoutQuestionCount,
		autoHoldoutDifficultyProfile, setAutoHoldoutDifficultyProfile,
		isStartingAutoLoop, handleStartAutoLoop,
		isAutoLoopRunning, autoLoopJobId,
		autoLoopPromptDrafts, isSavingAutoLoopPromptDrafts,
		saveAutoLoopPromptDraftSuggestions,

		// Lifecycle
		isPromoting, handleBulkPromote,
	};
}

export type LiveRoutingPhaseValue = LiveRoutingPhase;
