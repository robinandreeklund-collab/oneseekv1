"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { toast } from "sonner";
import { useAtomValue } from "jotai";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type {
	ToolApiInputEvaluationResponse,
	ToolApiInputEvaluationTestCase,
	ToolEvaluationResponse,
	ToolEvaluationTestCase,
	ToolMetadataItem,
	ToolMetadataUpdateItem,
	ToolRetrievalTuning,
} from "@/contracts/types/admin-tool-settings.types";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";
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
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { Separator } from "@/components/ui/separator";
import { AlertCircle, Save, RotateCcw, Plus, X, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";

function toUpdateItem(tool: ToolMetadataItem | ToolMetadataUpdateItem): ToolMetadataUpdateItem {
	return {
		tool_id: tool.tool_id,
		name: tool.name,
		description: tool.description,
		keywords: [...tool.keywords],
		example_queries: [...tool.example_queries],
		category: tool.category,
		base_path: tool.base_path ?? null,
	};
}

function isEqualTool(left: ToolMetadataUpdateItem, right: ToolMetadataUpdateItem) {
	return JSON.stringify(left) === JSON.stringify(right);
}

function isEqualTuning(left: ToolRetrievalTuning, right: ToolRetrievalTuning) {
	return JSON.stringify(left) === JSON.stringify(right);
}

function ToolEditor({
	tool,
	original,
	onChange,
	onSave,
	onReset,
	isSaving,
}: {
	tool: ToolMetadataUpdateItem;
	original: ToolMetadataItem;
	onChange: (toolId: string, updates: Partial<ToolMetadataUpdateItem>) => void;
	onSave: (toolId: string) => Promise<void>;
	onReset: (toolId: string) => void;
	isSaving: boolean;
}) {
	const [newKeyword, setNewKeyword] = useState("");
	const [newExample, setNewExample] = useState("");

	const hasChanges = !isEqualTool(tool, toUpdateItem(original));

	const addKeyword = () => {
		if (newKeyword.trim()) {
			onChange(tool.tool_id, {
				keywords: [...tool.keywords, newKeyword.trim()],
			});
			setNewKeyword("");
		}
	};

	const removeKeyword = (index: number) => {
		onChange(tool.tool_id, {
			keywords: tool.keywords.filter((_, i) => i !== index),
		});
	}

	const addExample = () => {
		if (newExample.trim()) {
			onChange(tool.tool_id, {
				example_queries: [...tool.example_queries, newExample.trim()],
			});
			setNewExample("");
		}
	};

	const removeExample = (index: number) => {
		onChange(tool.tool_id, {
			example_queries: tool.example_queries.filter((_, i) => i !== index),
		});
	}

	return (
		<div className="space-y-4">
			<div className="space-y-2">
				<Label htmlFor={`name-${tool.tool_id}`}>Namn</Label>
				<Input
					id={`name-${tool.tool_id}`}
					value={tool.name}
					onChange={(e) =>
						onChange(tool.tool_id, {
							name: e.target.value,
						})
					}
				/>
			</div>

			<div className="space-y-2">
				<Label htmlFor={`desc-${tool.tool_id}`}>Beskrivning</Label>
				<Textarea
					id={`desc-${tool.tool_id}`}
					value={tool.description}
					onChange={(e) =>
						onChange(tool.tool_id, {
							description: e.target.value,
						})
					}
					rows={3}
				/>
			</div>

			<div className="space-y-2">
				<Label>Keywords</Label>
				<div className="flex flex-wrap gap-2 mb-2">
					{tool.keywords.map((keyword, index) => (
						<Badge key={index} variant="secondary" className="gap-1">
							{keyword}
							<button
								onClick={() => removeKeyword(index)}
								className="ml-1 hover:text-destructive"
							>
								<X className="h-3 w-3" />
							</button>
						</Badge>
					))}
				</div>
				<div className="flex gap-2">
					<Input
						placeholder="Nytt keyword..."
						value={newKeyword}
						onChange={(e) => setNewKeyword(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter") {
								e.preventDefault();
								addKeyword();
							}
						}}
					/>
					<Button onClick={addKeyword} size="sm" variant="outline">
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			</div>

			<div className="space-y-2">
				<Label>Exempelfrågor</Label>
				<div className="space-y-2 mb-2">
					{tool.example_queries.map((example, index) => (
						<div key={index} className="flex items-center gap-2">
							<div className="flex-1 text-sm bg-muted p-2 rounded">
								{example}
							</div>
							<Button
								onClick={() => removeExample(index)}
								size="sm"
								variant="ghost"
							>
								<X className="h-4 w-4" />
							</Button>
						</div>
					))}
				</div>
				<div className="flex gap-2">
					<Input
						placeholder="Ny exempelfråga..."
						value={newExample}
						onChange={(e) => setNewExample(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter") {
								e.preventDefault();
								addExample();
							}
						}}
					/>
					<Button onClick={addExample} size="sm" variant="outline">
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{hasChanges && (
				<div className="flex gap-2 pt-4">
					<Button
						onClick={() => onSave(tool.tool_id)}
						className="gap-2"
						disabled={isSaving}
					>
						<Save className="h-4 w-4" />
						Spara ändringar
					</Button>
					<Button
						onClick={() => onReset(tool.tool_id)}
						variant="outline"
						className="gap-2"
						disabled={isSaving}
					>
						<RotateCcw className="h-4 w-4" />
						Återställ
					</Button>
				</div>
			)}
		</div>
	);
}

export function ToolSettingsPage() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const queryClient = useQueryClient();
	const [searchTerm, setSearchTerm] = useState("");
	const [draftTools, setDraftTools] = useState<Record<string, ToolMetadataUpdateItem>>({});
	const [activeTab, setActiveTab] = useState("metadata");
	const [savingToolId, setSavingToolId] = useState<string | null>(null);
	const [isSavingAll, setIsSavingAll] = useState(false);
	const [draftRetrievalTuning, setDraftRetrievalTuning] =
		useState<ToolRetrievalTuning | null>(null);
	const [isSavingRetrievalTuning, setIsSavingRetrievalTuning] = useState(false);
	const [evalInput, setEvalInput] = useState("");
	const [showEvalJsonInput, setShowEvalJsonInput] = useState(false);
	const [useHoldoutSuite, setUseHoldoutSuite] = useState(false);
	const [holdoutInput, setHoldoutInput] = useState("");
	const [showHoldoutJsonInput, setShowHoldoutJsonInput] = useState(false);
	const [evalInputError, setEvalInputError] = useState<string | null>(null);
	const [generationMode, setGenerationMode] = useState<"category" | "global_random">(
		"category"
	);
	const [generationEvalType, setGenerationEvalType] = useState<
		"tool_selection" | "api_input"
	>("tool_selection");
	const [generationProvider, setGenerationProvider] = useState("scb");
	const [generationCategory, setGenerationCategory] = useState("");
	const [generationQuestionCount, setGenerationQuestionCount] = useState(12);
	const [generationEvalName, setGenerationEvalName] = useState("");
	const [isGeneratingEvalFile, setIsGeneratingEvalFile] = useState(false);
	const [selectedLibraryPath, setSelectedLibraryPath] = useState("");
	const [isLoadingLibraryFile, setIsLoadingLibraryFile] = useState(false);
	const [isEvaluating, setIsEvaluating] = useState(false);
	const [isApiInputEvaluating, setIsApiInputEvaluating] = useState(false);
	const [retrievalLimit, setRetrievalLimit] = useState(5);
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
		if (generationMode === "global_random" && generationProvider === "all") {
			return;
		}
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
			if (generationCategory) {
				setGenerationCategory("");
			}
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
	}, [evalJobStatus, evalJobId, lastEvalJobNotice]);

	useEffect(() => {
		if (!apiInputEvalJobStatus || !apiInputEvalJobId) return;
		if (apiInputEvalJobStatus.status === "completed" && apiInputEvalJobStatus.result) {
			setApiInputEvaluationResult(apiInputEvalJobStatus.result);
			setSelectedPromptSuggestionKeys(new Set());
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
	}, [apiInputEvalJobStatus, apiInputEvalJobId, lastApiInputEvalJobNotice]);

	const changedToolIds = useMemo(() => {
		return Object.keys(draftTools).filter((toolId) => {
			const original = originalTools[toolId];
			if (!original) return false;
			return !isEqualTool(draftTools[toolId], toUpdateItem(original));
		});
	}, [draftTools, originalTools]);

	const changedToolSet = useMemo(() => new Set(changedToolIds), [changedToolIds]);

	const metadataPatch = useMemo(() => {
		return changedToolIds.map((toolId) => draftTools[toolId]);
	}, [changedToolIds, draftTools]);

	const retrievalTuningChanged = useMemo(() => {
		if (!draftRetrievalTuning || !data?.retrieval_tuning) return false;
		return !isEqualTuning(draftRetrievalTuning, data.retrieval_tuning);
	}, [draftRetrievalTuning, data?.retrieval_tuning]);

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

	const onToolChange = (toolId: string, updates: Partial<ToolMetadataUpdateItem>) => {
		setDraftTools((prev) => ({
			...prev,
			[toolId]: {
				...prev[toolId],
				...updates,
			},
		}));
	};

	const updateRetrievalTuningField = (
		key: keyof ToolRetrievalTuning,
		value: number
	) => {
		setDraftRetrievalTuning((prev) => {
			const current = prev ?? data?.retrieval_tuning;
			if (!current) return prev;
			return {
				...current,
				[key]:
					key === "rerank_candidates"
						? Math.max(1, Math.round(value))
						: Number(value),
			};
		});
	};

	const resetTool = (toolId: string) => {
		const original = originalTools[toolId];
		if (!original) return;
		setDraftTools((prev) => ({
			...prev,
			[toolId]: toUpdateItem(original),
		}));
	};

	const saveTools = async (toolIds: string[]) => {
		if (!data?.search_space_id) return;
		const tools = toolIds.map((toolId) => draftTools[toolId]).filter(Boolean);
		if (!tools.length) return;
		await adminToolSettingsApiService.updateToolSettings(
			{ tools },
			data.search_space_id
		);
		await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
		await refetch();
	};

	const saveSingleTool = async (toolId: string) => {
		setSavingToolId(toolId);
		try {
			await saveTools([toolId]);
			toast.success(`Sparade metadata för ${toolId}`);
		} catch (err) {
			toast.error("Kunde inte spara verktygsmetadata");
		} finally {
			setSavingToolId(null);
		}
	};

	const saveAllChanges = async () => {
		if (!changedToolIds.length) return;
		setIsSavingAll(true);
		try {
			await saveTools(changedToolIds);
			toast.success(`Sparade ${changedToolIds.length} metadataändringar`);
		} catch (err) {
			toast.error("Kunde inte spara alla metadataändringar");
		} finally {
			setIsSavingAll(false);
		}
	};

	const saveRetrievalTuning = async () => {
		if (!draftRetrievalTuning) return;
		setIsSavingRetrievalTuning(true);
		try {
			await adminToolSettingsApiService.updateRetrievalTuning(draftRetrievalTuning);
			await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			await refetch();
			toast.success("Sparade retrieval-vikter");
		} catch (error) {
			toast.error("Kunde inte spara retrieval-vikter");
		} finally {
			setIsSavingRetrievalTuning(false);
		}
	};

	const handleGenerateEvalLibraryFile = async () => {
		if (!data?.search_space_id) return;
		if (generationMode === "category" && !generationCategory) {
			toast.error("Välj en kategori innan du genererar.");
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
				question_count: Math.max(1, Math.min(100, Math.round(normalizedQuestionCount))),
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
		}));
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

			let holdoutTestsRaw: any[] = Array.isArray(envelope.holdout_tests)
				? envelope.holdout_tests
				: [];
			if (useHoldoutSuite) {
				const holdoutTrimmed = holdoutInput.trim();
				if (holdoutTrimmed) {
					let parsedHoldout: any;
					try {
						parsedHoldout = JSON.parse(holdoutTrimmed);
					} catch (_error) {
						setEvalInputError("Ogiltig holdout-JSON. Kontrollera formatet.");
						return null;
					}
					const holdoutEnvelope = Array.isArray(parsedHoldout)
						? { tests: parsedHoldout }
						: parsedHoldout;
					if (!holdoutEnvelope || !Array.isArray(holdoutEnvelope.tests)) {
						setEvalInputError("Holdout-JSON måste innehålla en tests-array.");
						return null;
					}
					holdoutTestsRaw = holdoutEnvelope.tests;
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
			toast.info(`API input eval-run startad (${started.total_tests} frågor)`);
		} catch (_err) {
			toast.error("API input eval-run misslyckades");
		} finally {
			setIsApiInputEvaluating(false);
		}
	};

	const togglePromptSuggestion = (promptKey: string) => {
		setSelectedPromptSuggestionKeys((prev) => {
			const next = new Set(prev);
			if (next.has(promptKey)) {
				next.delete(promptKey);
			} else {
				next.add(promptKey);
			}
			return next;
		});
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

	const toggleToolPromptSuggestion = (promptKey: string) => {
		setSelectedToolPromptSuggestionKeys((prev) => {
			const next = new Set(prev);
			if (next.has(promptKey)) {
				next.delete(promptKey);
			} else {
				next.add(promptKey);
			}
			return next;
		});
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

	const toggleSuggestion = (toolId: string) => {
		setSelectedSuggestionIds((prev) => {
			const next = new Set(prev);
			if (next.has(toolId)) {
				next.delete(toolId);
			} else {
				next.add(toolId);
			}
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

	const selectedSuggestions = useMemo(
		() =>
			evaluationResult?.suggestions.filter((suggestion) =>
				selectedSuggestionIds.has(suggestion.tool_id)
			) ?? [],
		[evaluationResult?.suggestions, selectedSuggestionIds]
	);

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

	const uploadEvalFile = async (event: ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		if (!file) return;
		const content = await file.text();
		setEvalInput(content);
		setEvalInputError(null);
		setSelectedLibraryPath("");
	};

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

	const categories = data?.categories || [];

	const filteredCategories = categories
		.map((category) => ({
			...category,
			tools: category.tools.filter((tool) => {
				const draft = draftTools[tool.tool_id] ?? toUpdateItem(tool);
				const term = searchTerm.toLowerCase();
				return (
					draft.name.toLowerCase().includes(term) ||
					draft.description.toLowerCase().includes(term) ||
					draft.tool_id.toLowerCase().includes(term)
				);
			}),
		}))
		.filter((category) => category.tools.length > 0);

	const totalTools = filteredCategories.reduce(
		(acc, cat) => acc + cat.tools.length,
		0
	);

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold">Tool Settings</h1>
				<p className="text-muted-foreground mt-2">
						Hantera metadata och kör Tool Evaluation Loop i samma adminflöde.
				</p>
			</div>

			<Alert>
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					Metadata här styr verklig tool_retrieval. Evaluation kör planering och
					toolval i dry-run utan riktiga API-anrop.
				</AlertDescription>
			</Alert>

			<Tabs value={activeTab} onValueChange={setActiveTab}>
				<TabsList>
					<TabsTrigger value="metadata">Metadata</TabsTrigger>
					<TabsTrigger value="evaluation">Tool Evaluation</TabsTrigger>
				</TabsList>

				<TabsContent value="metadata" className="space-y-6 mt-6">
					<Card>
						<CardHeader>
							<CardTitle>Guide: Så använder du Metadata-fliken</CardTitle>
							<CardDescription>
								Denna flik styr produktionsbeteendet för tool retrieval. Spara här när
								du är nöjd med resultat från eval-fliken.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-3 text-sm">
							<div className="rounded border p-3">
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>
										Justera <span className="font-medium">Description</span>,{" "}
										<span className="font-medium">Keywords</span> och{" "}
										<span className="font-medium">Exempelfrågor</span> per verktyg.
									</li>
									<li>
										Ställ in <span className="font-medium">Retrieval Tuning</span> om
										tool-valen missar rätt kandidat.
									</li>
									<li>
										Spara ändringar i metadata-fliken (enskilt eller “Spara alla ändringar”).
									</li>
									<li>
										Gå till <span className="font-medium">Tool Evaluation</span> och kör
										nya tester.
									</li>
									<li>
										Kom tillbaka hit och spara bara de ändringar som förbättrar både
										huvudsuite och holdout.
									</li>
								</ol>
							</div>
							<p className="text-xs text-muted-foreground">
								Tips: “Senaste eval-körning” visar snabb status på hur senaste
								justeringar presterade.
							</p>
						</CardContent>
					</Card>

					{apiCategories?.providers?.length ? (
						<Card>
							<CardHeader>
								<CardTitle>API-kategorier (alla providers)</CardTitle>
								<CardDescription>
									Översikt av tillgängliga providers, API-kategorier och underkategorier för
									testdesign i Tool Evaluation.
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								{apiCategories.providers.map((provider) => {
									const topLevel = provider.categories.filter(
										(item) => item.level === "top_level"
									);
									const subcategories = provider.categories.filter(
										(item) => item.level !== "top_level"
									);
									return (
										<div key={provider.provider_key} className="rounded border p-3 space-y-3">
											<div className="flex flex-wrap items-center gap-2">
												<Badge variant="secondary">{provider.provider_name}</Badge>
												<Badge variant="outline">
													{topLevel.length} toppnivå
												</Badge>
												<Badge variant="outline">
													{subcategories.length} underkategorier
												</Badge>
											</div>
											<div className="grid gap-4 lg:grid-cols-2">
												<div className="space-y-2">
													<p className="text-sm font-medium">Toppnivå</p>
													<div className="max-h-72 overflow-auto rounded border p-2 space-y-1">
														{topLevel.map((item) => (
															<div
																key={`${provider.provider_key}-${item.tool_id}`}
																className="rounded bg-muted/40 px-2 py-1 text-xs"
															>
																<p className="font-medium">{item.category_name}</p>
																<p className="text-muted-foreground">
																	{item.tool_id}
																	{item.base_path ? ` · ${item.base_path}` : ""}
																</p>
															</div>
														))}
													</div>
												</div>
												<div className="space-y-2">
													<p className="text-sm font-medium">Underkategorier</p>
													<div className="max-h-72 overflow-auto rounded border p-2 space-y-1">
														{subcategories.map((item) => (
															<div
																key={`${provider.provider_key}-${item.tool_id}`}
																className="rounded bg-muted/40 px-2 py-1 text-xs"
															>
																<p className="font-medium">{item.tool_name}</p>
																<p className="text-muted-foreground">
																	{item.category_name} · {item.tool_id}
																	{item.base_path ? ` · ${item.base_path}` : ""}
																</p>
															</div>
														))}
													</div>
												</div>
											</div>
										</div>
									);
								})}
							</CardContent>
						</Card>
					) : null}

					{data?.latest_evaluation && (
						<Card>
							<CardHeader>
								<CardTitle>Senaste eval-körning</CardTitle>
								<CardDescription>
									Visar senaste genomförda Tool Evaluation för detta search space.
								</CardDescription>
							</CardHeader>
							<CardContent className="grid gap-3 md:grid-cols-4 text-sm">
								<div className="rounded border p-3">
									<p className="text-xs text-muted-foreground">Tidpunkt</p>
									<p className="font-medium">
										{new Date(data.latest_evaluation.run_at).toLocaleString("sv-SE")}
									</p>
								</div>
								<div className="rounded border p-3">
									<p className="text-xs text-muted-foreground">Antal frågor</p>
									<p className="font-medium">{data.latest_evaluation.total_tests}</p>
								</div>
								<div className="rounded border p-3">
									<p className="text-xs text-muted-foreground">Passerade</p>
									<p className="font-medium">{data.latest_evaluation.passed_tests}</p>
								</div>
								<div className="rounded border p-3">
									<p className="text-xs text-muted-foreground">Success rate</p>
									<p className="font-medium">
										{(data.latest_evaluation.success_rate * 100).toFixed(1)}%
									</p>
								</div>
								{data.latest_evaluation.eval_name && (
									<div className="rounded border p-3 md:col-span-4">
										<p className="text-xs text-muted-foreground">Eval-namn</p>
										<p className="font-medium">{data.latest_evaluation.eval_name}</p>
									</div>
								)}
							</CardContent>
						</Card>
					)}

					<Card>
						<CardHeader>
							<CardTitle>Retrieval Tuning</CardTitle>
							<CardDescription>
								Styr hur tool_retrieval viktar namn, keywords, embeddings och rerank.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							{draftRetrievalTuning ? (
								<>
									<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
										<div className="space-y-1">
											<Label>Name match</Label>
											<Input
												type="number"
												step="0.1"
												value={draftRetrievalTuning.name_match_weight}
												onChange={(e) =>
													updateRetrievalTuningField(
														"name_match_weight",
														Number.parseFloat(e.target.value || "0")
													)
												}
											/>
										</div>
										<div className="space-y-1">
											<Label>Keyword</Label>
											<Input
												type="number"
												step="0.1"
												value={draftRetrievalTuning.keyword_weight}
												onChange={(e) =>
													updateRetrievalTuningField(
														"keyword_weight",
														Number.parseFloat(e.target.value || "0")
													)
												}
											/>
										</div>
										<div className="space-y-1">
											<Label>Description token</Label>
											<Input
												type="number"
												step="0.1"
												value={draftRetrievalTuning.description_token_weight}
												onChange={(e) =>
													updateRetrievalTuningField(
														"description_token_weight",
														Number.parseFloat(e.target.value || "0")
													)
												}
											/>
										</div>
										<div className="space-y-1">
											<Label>Example query</Label>
											<Input
												type="number"
												step="0.1"
												value={draftRetrievalTuning.example_query_weight}
												onChange={(e) =>
													updateRetrievalTuningField(
														"example_query_weight",
														Number.parseFloat(e.target.value || "0")
													)
												}
											/>
										</div>
										<div className="space-y-1">
											<Label>Namespace boost</Label>
											<Input
												type="number"
												step="0.1"
												value={draftRetrievalTuning.namespace_boost}
												onChange={(e) =>
													updateRetrievalTuningField(
														"namespace_boost",
														Number.parseFloat(e.target.value || "0")
													)
												}
											/>
										</div>
										<div className="space-y-1">
											<Label>Embedding weight</Label>
											<Input
												type="number"
												step="0.1"
												value={draftRetrievalTuning.embedding_weight}
												onChange={(e) =>
													updateRetrievalTuningField(
														"embedding_weight",
														Number.parseFloat(e.target.value || "0")
													)
												}
											/>
										</div>
										<div className="space-y-1">
											<Label>Rerank candidates</Label>
											<Input
												type="number"
												step="1"
												min={1}
												max={100}
												value={draftRetrievalTuning.rerank_candidates}
												onChange={(e) =>
													updateRetrievalTuningField(
														"rerank_candidates",
														Number.parseInt(e.target.value || "1", 10)
													)
												}
											/>
										</div>
									</div>
									<div className="flex items-center gap-2">
										<Badge variant="outline">
											{retrievalTuningChanged
												? "Osparade viktändringar"
												: "Vikter i synk"}
										</Badge>
										<Button
											onClick={saveRetrievalTuning}
											disabled={!retrievalTuningChanged || isSavingRetrievalTuning}
										>
											{isSavingRetrievalTuning
												? "Sparar vikter..."
												: "Spara retrieval-vikter"}
										</Button>
									</div>
								</>
							) : (
								<p className="text-sm text-muted-foreground">
									Kunde inte läsa retrieval-vikter.
								</p>
							)}
						</CardContent>
					</Card>

					<div className="flex flex-wrap items-center gap-4">
						<Input
							placeholder="Sök verktyg..."
							value={searchTerm}
							onChange={(e) => setSearchTerm(e.target.value)}
							className="max-w-md"
						/>
						<div className="text-sm text-muted-foreground">
							{totalTools} verktyg i {filteredCategories.length} kategorier
						</div>
						<Badge variant="outline">
							{changedToolIds.length} osparade ändringar
						</Badge>
						<Button
							onClick={saveAllChanges}
							disabled={!changedToolIds.length || isSavingAll}
							className="gap-2"
						>
							<Save className="h-4 w-4" />
							{isSavingAll
								? "Sparar..."
								: `Spara alla ändringar (${changedToolIds.length})`}
						</Button>
					</div>

					<Accordion type="single" collapsible className="space-y-4">
						{filteredCategories.map((category) => (
							<Card key={category.category_id}>
								<AccordionItem value={category.category_id} className="border-0">
									<CardHeader>
										<AccordionTrigger className="hover:no-underline">
											<div className="flex items-center gap-3">
												<CardTitle>{category.category_name}</CardTitle>
												<Badge variant="outline">
													{category.tools.length} verktyg
												</Badge>
											</div>
										</AccordionTrigger>
									</CardHeader>
									<AccordionContent>
										<CardContent>
											<div className="space-y-6">
												{category.tools.map((tool, index) => {
													const draft = draftTools[tool.tool_id] ?? toUpdateItem(tool);
													const changed = changedToolSet.has(tool.tool_id);
													return (
														<div key={tool.tool_id}>
															{index > 0 && <Separator className="my-6" />}
															<div className="space-y-4">
																<div>
																	<div className="flex items-center gap-2 mb-1">
																		<h3 className="font-semibold">{draft.name}</h3>
																		<Badge
																			variant="secondary"
																			className="text-xs"
																		>
																			{draft.tool_id}
																		</Badge>
																		{(tool.has_override || changed) && (
																			<Badge
																				variant="outline"
																				className="text-xs"
																			>
																				override
																			</Badge>
																		)}
																	</div>
																	<p className="text-sm text-muted-foreground">
																		Kategori: {draft.category}
																	</p>
																</div>
																<ToolEditor
																	tool={draft}
																	original={tool}
																	onChange={onToolChange}
																	onSave={saveSingleTool}
																	onReset={resetTool}
																	isSaving={savingToolId === tool.tool_id}
																/>
															</div>
														</div>
													);
												})}
											</div>
										</CardContent>
									</AccordionContent>
								</AccordionItem>
							</Card>
						))}
					</Accordion>

					{filteredCategories.length === 0 && (
						<Card>
							<CardContent className="py-12 text-center">
								<p className="text-muted-foreground">
									Inga verktyg matchade sökningen &quot;{searchTerm}&quot;
								</p>
							</CardContent>
						</Card>
					)}
				</TabsContent>

				<TabsContent value="evaluation" className="space-y-6 mt-6">
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
									<li>
										Börja med <span className="font-medium">Per kategori/API</span> för
										precision.
									</li>
									<li>
										Använd sedan <span className="font-medium">Global random mix</span>{" "}
										för regression över flera kategorier.
									</li>
									<li>
										Rekommendation: 10-15 frågor per kategori och 25-40 frågor globalt.
									</li>
								</ul>
							</div>

							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 2: Generera eller ladda eval-JSON</p>
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>Välj Läge, Eval-typ, Provider, Kategori och antal frågor.</li>
									<li>Klicka “Generera + spara eval JSON”.</li>
									<li>
										Klicka “Ladda i eval-input” på filen i listan
										(<span className="font-medium">/eval/api</span>).
									</li>
									<li>
										Alternativt: ladda upp egen fil via “Ladda JSON-fil” eller klistra in i
										JSON-fältet.
									</li>
								</ol>
							</div>

							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">
									Steg 3: Kör Agentval Eval (route + sub-route + agent + tool + plan)
								</p>
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>
										Sätt <span className="font-medium">Retrieval K</span> (5 är standard,
										8-10 för svårare frågor).
									</li>
									<li>
										Behåll “Inkludera draft metadata” aktiv om du vill testa osparade
										ändringar.
									</li>
									<li>Klicka “Run Tool Evaluation”.</li>
									<li>
										Följ “Körstatus per fråga” och kontrollera:
										<span className="font-medium">
											{" "}
											Route accuracy, Sub-route accuracy, Agent accuracy, Plan
											accuracy, Tool accuracy
										</span>
										.
									</li>
								</ol>
							</div>

							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 4: Förbättra och kör om</p>
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>
										Använd “Metadata-förslag” för description, keywords och
										exempelfrågor.
									</li>
									<li>
										Använd “Föreslagen tuning” för retrieval-vikter och spara vid behov.
									</li>
									<li>
										Använd “Prompt-förslag från Tool Eval” för router/agent-prompts.
									</li>
									<li>Kör om samma suite och jämför del-metrics tills resultatet stabiliseras.</li>
								</ol>
							</div>

							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 5: Kör API Input Eval (utan API-anrop)</p>
								<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
									<li>
										Välj suite med <span className="font-medium">required_fields</span>{" "}
										(och gärna <span className="font-medium">field_values</span>).
									</li>
									<li>Klicka “Run API Input Eval (dry-run)”.</li>
									<li>
										Kontrollera: Schema validity, Required-field recall, Field-value
										accuracy, Clarification accuracy.
									</li>
									<li>
										Spara “Prompt-förslag från API Input Eval” och kör om tills stabilt.
									</li>
								</ol>
							</div>

							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Steg 6: Använd holdout (anti-overfitting)</p>
								<ul className="list-disc pl-5 space-y-1 text-muted-foreground">
									<li>Aktivera “Använd holdout-suite”.</li>
									<li>Klistra in separat holdout-JSON eller lägg holdout_tests i huvud-JSON.</li>
									<li>
										Optimera på huvudsuite, men godkänn endast ändringar som även förbättrar
										holdout.
									</li>
								</ul>
							</div>

							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Minsta JSON-format (Tool Eval)</p>
								<pre className="text-[11px] whitespace-pre-wrap break-words rounded bg-muted/40 p-2 text-muted-foreground">
{`{
  "tests": [
    {
      "id": "t1",
      "question": "Fråga...",
      "expected": {
        "route": "action",
        "sub_route": "travel",
        "agent": "trafik",
        "tool": "smhi_weather",
        "category": "weather",
        "plan_requirements": ["route:action", "agent:trafik", "tool:smhi_weather"]
      },
      "allowed_tools": ["smhi_weather"]
    }
  ]
}`}
								</pre>
							</div>

							<div className="rounded border p-3 space-y-2">
								<p className="font-medium">Minsta JSON-format (API Input Eval)</p>
								<pre className="text-[11px] whitespace-pre-wrap break-words rounded bg-muted/40 p-2 text-muted-foreground">
{`{
  "tests": [
    {
      "id": "a1",
      "question": "Fråga...",
      "expected": {
        "route": "action",
        "sub_route": "travel",
        "agent": "trafik",
        "tool": "smhi_weather",
        "category": "weather",
        "plan_requirements": ["route:action", "agent:trafik", "field:city"],
        "required_fields": ["city", "date"],
        "field_values": {"city": "Malmö"},
        "allow_clarification": false
      }
    }
  ]
}`}
								</pre>
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Stegöversikt</CardTitle>
							<CardDescription>
								Arbeta i denna ordning för ett tydligt och repeterbart eval-flöde.
							</CardDescription>
						</CardHeader>
						<CardContent className="flex flex-wrap items-center gap-2 text-xs">
							<Badge variant="secondary">Steg 1: Generera/Ladda frågor</Badge>
							<Badge variant="secondary">
								Steg 2: Agentval Eval (route + agent + tool + plan)
							</Badge>
							<Badge variant="secondary">Steg 3: API Input Eval</Badge>
							<Badge variant="secondary">Steg 4: Holdout + spara förbättringar</Badge>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Steg 1: Generera/Ladda eval-frågor</CardTitle>
							<CardDescription>
								Skapa JSON i rätt format, spara i /eval/api och ladda direkt in i
								eval-run. Frågor genereras på svenska och med Sverige-fokus
								(städer, vägar, politik, väder m.m.) utifrån vald tool-kategori.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
								<div className="space-y-2">
									<Label htmlFor="generation-mode">Läge</Label>
									<select
										id="generation-mode"
										className="h-10 w-full rounded-md border bg-background px-3 text-sm"
										value={generationMode}
										onChange={(event) =>
											setGenerationMode(
												event.target.value === "global_random"
													? "global_random"
													: "category"
											)
										}
									>
										<option value="category">Per kategori/API</option>
										<option value="global_random">
											Random mix från flera kategorier (global tuning)
										</option>
									</select>
								</div>
								<div className="space-y-2">
									<Label htmlFor="generation-eval-type">Eval-typ</Label>
									<select
										id="generation-eval-type"
										className="h-10 w-full rounded-md border bg-background px-3 text-sm"
										value={generationEvalType}
										onChange={(event) =>
											setGenerationEvalType(
												event.target.value === "api_input"
													? "api_input"
													: "tool_selection"
											)
										}
									>
										<option value="tool_selection">Tool selection</option>
										<option value="api_input">API input (required fields)</option>
									</select>
								</div>
								<div className="space-y-2">
									<Label htmlFor="generation-provider">Provider</Label>
									<select
										id="generation-provider"
										className="h-10 w-full rounded-md border bg-background px-3 text-sm"
										value={generationProvider}
										onChange={(event) => setGenerationProvider(event.target.value)}
									>
										{generationMode === "global_random" && (
											<option value="all">Alla providers</option>
										)}
										{apiProviders.map((provider) => (
											<option
												key={provider.provider_key}
												value={provider.provider_key}
											>
												{provider.provider_name}
											</option>
										))}
									</select>
								</div>
								<div className="space-y-2">
									<Label htmlFor="generation-question-count">Antal frågor</Label>
									<Input
										id="generation-question-count"
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
									<Label htmlFor="generation-eval-name">Eval-namn (valfritt)</Label>
									<Input
										id="generation-eval-name"
										placeholder="scb-prisindex-mars-2026"
										value={generationEvalName}
										onChange={(event) => setGenerationEvalName(event.target.value)}
									/>
								</div>
							</div>

							{generationMode === "category" && (
								<div className="space-y-2">
									<Label htmlFor="generation-category">Kategori</Label>
									<select
										id="generation-category"
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
										<p className="text-xs text-muted-foreground">
											Inga sparade filer ännu.
										</p>
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
												<Button
													variant={
														selectedLibraryPath === item.relative_path
															? "default"
															: "outline"
													}
													size="sm"
													onClick={() => loadEvalLibraryFile(item.relative_path)}
													disabled={isLoadingLibraryFile}
												>
													Ladda i eval-input
												</Button>
											</div>
										))
									)}
								</div>
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Steg 2: Kör Agentval Eval och API Input Eval</CardTitle>
							<CardDescription>
								Här testar du hela agentvalet från route/sub-route till agentval,
								tool-val och plan,
								samt API-input i dry-run.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="flex flex-wrap items-center gap-3">
								<Input
									type="file"
									accept="application/json"
									onChange={uploadEvalFile}
									className="max-w-sm"
								/>
								<div className="flex items-center gap-2">
									<Label htmlFor="retrieval-limit">Retrieval K</Label>
									<Input
										id="retrieval-limit"
										type="number"
										value={retrievalLimit}
										onChange={(e) =>
											setRetrievalLimit(Number.parseInt(e.target.value || "5", 10))
										}
										className="w-24"
										min={1}
										max={15}
									/>
								</div>
								<div className="flex items-center gap-2">
									<Switch
										checked={includeDraftMetadata}
										onCheckedChange={setIncludeDraftMetadata}
									/>
									<span className="text-sm">
										Inkludera osparad draft (metadata + retrieval-vikter)
									</span>
								</div>
								<Button
									onClick={handleRunEvaluation}
									disabled={isEvaluating || isEvalJobRunning}
								>
									{isEvaluating
										? "Startar agentval-eval..."
										: isEvalJobRunning
											? "Agentval-eval körs..."
											: "Run Agentval Eval (route + agent + tool + plan)"}
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
							<p className="text-xs text-muted-foreground">
								Retrieval K = antal top-kandidater som tas vidare från retrieval i
								eval-runen. 5 är bra standard; höj till 8-10 för breda/svåra frågor.
							</p>
							<p className="text-xs text-muted-foreground">
								Agentval Eval = starten av pipelinen: route/sub-route, valt agentsteg,
								valt verktyg och
								om planen uppfyller plan_requirements.
							</p>
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
										placeholder='{"eval_name":"routing-smoke","tests":[{"id":"t1","question":"...","expected":{"route":"action","sub_route":"travel","agent":"trafik","tool":"...","category":"...","plan_requirements":["route:action","agent:trafik","tool:..."]}}]}'
										value={evalInput}
										onChange={(e) => setEvalInput(e.target.value)}
										rows={12}
										className="font-mono text-xs"
									/>
								) : (
									<p className="text-xs text-muted-foreground">
										JSON-fältet är minimerat för bättre överblick. Klicka &quot;Visa
										JSON-fält&quot; för att redigera manuellt.
									</p>
								)}
							</div>
							<div className="rounded border p-3 space-y-3">
								<div className="flex flex-wrap items-center justify-between gap-2">
									<div className="flex items-center gap-2">
										<Switch
											checked={useHoldoutSuite}
											onCheckedChange={setUseHoldoutSuite}
										/>
										<p className="text-sm font-medium">Använd holdout-suite</p>
									</div>
									<Button
										variant="outline"
										size="sm"
										onClick={() => setShowHoldoutJsonInput((prev) => !prev)}
									>
										{showHoldoutJsonInput
											? "Minimera holdout-fält"
											: "Visa holdout-fält"}
									</Button>
								</div>
								<p className="text-xs text-muted-foreground">
									Holdout-suite används för anti-overfitting: promptförslag optimeras på
									huvudtesterna men kvaliteten mäts separat på holdout.
								</p>
								{showHoldoutJsonInput ? (
									<Textarea
										placeholder='{"tests":[{"id":"h1","question":"...","expected":{"route":"action","sub_route":"travel","agent":"trafik","tool":"...","category":"...","plan_requirements":["route:action","agent:trafik","field:city"],"required_fields":["city","date"]}}]}'
										value={holdoutInput}
										onChange={(e) => setHoldoutInput(e.target.value)}
										rows={8}
										className="font-mono text-xs"
									/>
								) : (
									<p className="text-xs text-muted-foreground">
										Holdout-fältet är minimerat. Du kan även lägga holdout_tests i
										huvud-JSON.
									</p>
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

					{evalJobId && (
						<Card>
							<CardHeader>
								<CardTitle>Steg 2A: Agentval-status per fråga</CardTitle>
								<CardDescription>
									Jobb {evalJobId} · status {evalJobStatus?.status ?? "pending"}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-3">
								<div className="flex flex-wrap items-center gap-2 text-sm">
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
										{evalJobStatus?.completed_tests ?? 0}/
										{evalJobStatus?.total_tests ?? 0} frågor färdiga
									</span>
								</div>
								{evalJobStatus?.error && (
									<Alert variant="destructive">
										<AlertCircle className="h-4 w-4" />
										<AlertDescription>{evalJobStatus.error}</AlertDescription>
									</Alert>
								)}
								<div className="space-y-2">
									{(evalJobStatus?.case_statuses ?? []).map((caseStatus) => (
										<div
											key={caseStatus.test_id}
											className="rounded border p-2 text-xs space-y-1"
										>
											<div className="flex items-center justify-between gap-2">
												<p className="font-medium">{caseStatus.test_id}</p>
												<Badge
													variant={
														caseStatus.status === "failed"
															? "destructive"
															: caseStatus.status === "completed"
																? "default"
																: caseStatus.status === "running"
																	? "secondary"
																	: "outline"
													}
												>
													{caseStatus.status}
												</Badge>
											</div>
											<p className="text-muted-foreground">{caseStatus.question}</p>
											{caseStatus.selected_route && (
												<p className="text-muted-foreground">
													Route: {caseStatus.selected_route}
													{caseStatus.selected_sub_route
														? ` / ${caseStatus.selected_sub_route}`
														: ""}
												</p>
											)}
											{caseStatus.selected_agent && (
												<p className="text-muted-foreground">
													Vald agent: {caseStatus.selected_agent}
												</p>
											)}
											{caseStatus.selected_tool && (
												<p className="text-muted-foreground">
													Valt verktyg: {caseStatus.selected_tool}
												</p>
											)}
											{typeof caseStatus.passed === "boolean" && (
												<p className="text-muted-foreground">
													Resultat: {caseStatus.passed ? "Rätt" : "Fel"}
												</p>
											)}
											{caseStatus.error && (
												<p className="text-red-500">{caseStatus.error}</p>
											)}
										</div>
									))}
								</div>
							</CardContent>
						</Card>
					)}

					{apiInputEvalJobId && (
						<Card>
							<CardHeader>
								<CardTitle>Steg 3A: API input-status per fråga</CardTitle>
								<CardDescription>
									Jobb {apiInputEvalJobId} · status{" "}
									{apiInputEvalJobStatus?.status ?? "pending"}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-3">
								<div className="flex flex-wrap items-center gap-2 text-sm">
									<Badge
										variant={
											apiInputEvalJobStatus?.status === "failed"
												? "destructive"
												: apiInputEvalJobStatus?.status === "completed"
													? "default"
													: "secondary"
										}
									>
										{apiInputEvalJobStatus?.status ?? "pending"}
									</Badge>
									<span>
										{apiInputEvalJobStatus?.completed_tests ?? 0}/
										{apiInputEvalJobStatus?.total_tests ?? 0} frågor färdiga
									</span>
								</div>
								{apiInputEvalJobStatus?.error && (
									<Alert variant="destructive">
										<AlertCircle className="h-4 w-4" />
										<AlertDescription>{apiInputEvalJobStatus.error}</AlertDescription>
									</Alert>
								)}
								<div className="space-y-2">
									{(apiInputEvalJobStatus?.case_statuses ?? []).map((caseStatus) => (
										<div
											key={`api-input-${caseStatus.test_id}`}
											className="rounded border p-2 text-xs space-y-1"
										>
											<div className="flex items-center justify-between gap-2">
												<p className="font-medium">{caseStatus.test_id}</p>
												<Badge
													variant={
														caseStatus.status === "failed"
															? "destructive"
															: caseStatus.status === "completed"
																? "default"
																: caseStatus.status === "running"
																	? "secondary"
																	: "outline"
													}
												>
													{caseStatus.status}
												</Badge>
											</div>
											<p className="text-muted-foreground">{caseStatus.question}</p>
											{caseStatus.selected_route && (
												<p className="text-muted-foreground">
													Route: {caseStatus.selected_route}
													{caseStatus.selected_sub_route
														? ` / ${caseStatus.selected_sub_route}`
														: ""}
												</p>
											)}
											{caseStatus.selected_agent && (
												<p className="text-muted-foreground">
													Vald agent: {caseStatus.selected_agent}
												</p>
											)}
											{caseStatus.selected_tool && (
												<p className="text-muted-foreground">
													Valt verktyg: {caseStatus.selected_tool}
												</p>
											)}
											{typeof caseStatus.passed === "boolean" && (
												<p className="text-muted-foreground">
													Resultat: {caseStatus.passed ? "Rätt" : "Fel"}
												</p>
											)}
											{caseStatus.error && (
												<p className="text-red-500">{caseStatus.error}</p>
											)}
										</div>
									))}
								</div>
							</CardContent>
						</Card>
					)}

					{evaluationResult && (
						<>
							<Card>
								<CardHeader>
									<CardTitle>
										Steg 2B: Agentval Eval Resultat (route + agent + tool + plan)
									</CardTitle>
									<CardDescription>
										Metadata version {evaluationResult.metadata_version_hash} ·
										search space {evaluationResult.search_space_id}
									</CardDescription>
								</CardHeader>
								<CardContent className="grid gap-4 md:grid-cols-4">
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Success rate</p>
										<p className="text-2xl font-semibold">
											{(evaluationResult.metrics.success_rate * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Route accuracy</p>
										<p className="text-2xl font-semibold">
											{evaluationResult.metrics.route_accuracy == null
												? "-"
												: `${(evaluationResult.metrics.route_accuracy * 100).toFixed(
														1
													)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Sub-route accuracy</p>
										<p className="text-2xl font-semibold">
											{evaluationResult.metrics.sub_route_accuracy == null
												? "-"
												: `${(
														evaluationResult.metrics.sub_route_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Agent accuracy</p>
										<p className="text-2xl font-semibold">
											{evaluationResult.metrics.agent_accuracy == null
												? "-"
												: `${(
														evaluationResult.metrics.agent_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Plan accuracy</p>
										<p className="text-2xl font-semibold">
											{evaluationResult.metrics.plan_accuracy == null
												? "-"
												: `${(evaluationResult.metrics.plan_accuracy * 100).toFixed(
														1
													)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Tool accuracy</p>
										<p className="text-2xl font-semibold">
											{evaluationResult.metrics.tool_accuracy == null
												? "-"
												: `${(evaluationResult.metrics.tool_accuracy * 100).toFixed(
														1
													)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Category accuracy</p>
										<p className="text-2xl font-semibold">
											{evaluationResult.metrics.category_accuracy == null
												? "-"
												: `${(
														evaluationResult.metrics.category_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Retrieval recall@K</p>
										<p className="text-2xl font-semibold">
											{evaluationResult.metrics.retrieval_recall_at_k == null
												? "-"
												: `${(
														evaluationResult.metrics.retrieval_recall_at_k * 100
													).toFixed(1)}%`}
										</p>
									</div>
								</CardContent>
							</Card>

							{apiInputEvaluationResult?.holdout_metrics && (
								<Card>
									<CardHeader>
										<CardTitle>Steg 4: Holdout-suite (anti-overfitting)</CardTitle>
										<CardDescription>
											Separat mätning på holdout för att verifiera att förbättringar
											generaliserar.
										</CardDescription>
									</CardHeader>
									<CardContent className="grid gap-4 md:grid-cols-4">
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Holdout success</p>
											<p className="text-2xl font-semibold">
												{(
													apiInputEvaluationResult.holdout_metrics.success_rate * 100
												).toFixed(1)}
												%
											</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Holdout schema</p>
											<p className="text-2xl font-semibold">
												{apiInputEvaluationResult.holdout_metrics.schema_validity_rate ==
												null
													? "-"
													: `${(
															apiInputEvaluationResult.holdout_metrics
																.schema_validity_rate * 100
														).toFixed(1)}%`}
											</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">
												Holdout required recall
											</p>
											<p className="text-2xl font-semibold">
												{apiInputEvaluationResult.holdout_metrics.required_field_recall ==
												null
													? "-"
													: `${(
															apiInputEvaluationResult.holdout_metrics
																.required_field_recall * 100
														).toFixed(1)}%`}
											</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Holdout cases</p>
											<p className="text-2xl font-semibold">
												{apiInputEvaluationResult.holdout_metrics.passed_tests}/
												{apiInputEvaluationResult.holdout_metrics.total_tests}
											</p>
										</div>
									</CardContent>
								</Card>
							)}

							<Card>
								<CardHeader>
									<CardTitle>Steg 2C: Retrieval-vikter i denna eval</CardTitle>
								</CardHeader>
								<CardContent className="space-y-3">
									<div className="grid gap-2 md:grid-cols-3">
										<Badge variant="outline">
											name: {evaluationResult.retrieval_tuning.name_match_weight}
										</Badge>
										<Badge variant="outline">
											keyword: {evaluationResult.retrieval_tuning.keyword_weight}
										</Badge>
										<Badge variant="outline">
											desc: {evaluationResult.retrieval_tuning.description_token_weight}
										</Badge>
										<Badge variant="outline">
											example: {evaluationResult.retrieval_tuning.example_query_weight}
										</Badge>
										<Badge variant="outline">
											namespace: {evaluationResult.retrieval_tuning.namespace_boost}
										</Badge>
										<Badge variant="outline">
											embedding: {evaluationResult.retrieval_tuning.embedding_weight}
										</Badge>
										<Badge variant="outline">
											rerank_candidates:{" "}
											{evaluationResult.retrieval_tuning.rerank_candidates}
										</Badge>
									</div>

									{evaluationResult.retrieval_tuning_suggestion && (
										<div className="rounded border p-3 space-y-2">
											<p className="text-sm font-medium">Föreslagen tuning</p>
											<p className="text-xs text-muted-foreground">
												{evaluationResult.retrieval_tuning_suggestion.rationale}
											</p>
											<div className="grid gap-2 md:grid-cols-3">
												<Badge variant="secondary">
													name:{" "}
													{
														evaluationResult.retrieval_tuning_suggestion.proposed_tuning
															.name_match_weight
													}
												</Badge>
												<Badge variant="secondary">
													keyword:{" "}
													{
														evaluationResult.retrieval_tuning_suggestion.proposed_tuning
															.keyword_weight
													}
												</Badge>
												<Badge variant="secondary">
													desc:{" "}
													{
														evaluationResult.retrieval_tuning_suggestion.proposed_tuning
															.description_token_weight
													}
												</Badge>
												<Badge variant="secondary">
													example:{" "}
													{
														evaluationResult.retrieval_tuning_suggestion.proposed_tuning
															.example_query_weight
													}
												</Badge>
												<Badge variant="secondary">
													namespace:{" "}
													{
														evaluationResult.retrieval_tuning_suggestion.proposed_tuning
															.namespace_boost
													}
												</Badge>
												<Badge variant="secondary">
													embedding:{" "}
													{
														evaluationResult.retrieval_tuning_suggestion.proposed_tuning
															.embedding_weight
													}
												</Badge>
												<Badge variant="secondary">
													rerank_candidates:{" "}
													{
														evaluationResult.retrieval_tuning_suggestion.proposed_tuning
															.rerank_candidates
													}
												</Badge>
											</div>
											<div className="flex gap-2">
												<Button
													variant="outline"
													onClick={applyWeightSuggestionToDraft}
													disabled={isSavingRetrievalTuning}
												>
													Applicera viktförslag i draft
												</Button>
												<Button
													onClick={saveWeightSuggestion}
													disabled={isSavingRetrievalTuning}
												>
													Spara viktförslag
												</Button>
											</div>
										</div>
									)}
								</CardContent>
							</Card>

							<Card>
								<CardHeader>
									<CardTitle>Steg 2D: Agentval-resultat per test</CardTitle>
								</CardHeader>
								<CardContent className="space-y-3">
									{evaluationResult.results.map((result) => (
										<div key={result.test_id} className="rounded border p-3 space-y-2">
											<div className="flex items-center justify-between gap-2">
												<div className="flex items-center gap-2">
													<Badge variant="outline">{result.test_id}</Badge>
													<Badge variant={result.passed ? "default" : "destructive"}>
														{result.passed ? "PASS" : "FAIL"}
													</Badge>
												</div>
												<div className="text-xs text-muted-foreground">
													Route: {result.expected_route || "-"}
													{result.expected_sub_route
														? ` / ${result.expected_sub_route}`
														: ""}{" "}
													→ {result.selected_route || "-"}
													{result.selected_sub_route
														? ` / ${result.selected_sub_route}`
														: ""}
												</div>
												<div className="text-xs text-muted-foreground">
													Agent: {result.expected_agent || "-"} →{" "}
													{result.selected_agent || "-"}
												</div>
												<div className="text-xs text-muted-foreground">
													Expected: {result.expected_category || "-"} /{" "}
													{result.expected_tool || "-"} · Selected:{" "}
													{result.selected_category || "-"} /{" "}
													{result.selected_tool || "-"}
												</div>
											</div>
											<p className="text-sm">{result.question}</p>
											{result.planning_analysis && (
												<p className="text-xs text-muted-foreground">
													Analys: {result.planning_analysis}
												</p>
											)}
											{result.plan_requirement_checks?.length > 0 && (
												<div className="flex flex-wrap gap-2">
													{result.plan_requirement_checks.map((check, idx) => (
														<Badge
															key={`${result.test_id}-plan-${idx}`}
															variant={check.passed ? "outline" : "destructive"}
														>
															{check.requirement}: {check.passed ? "OK" : "MISS"}
														</Badge>
													))}
												</div>
											)}
											<p className="text-xs text-muted-foreground">
												Retrieval: {result.retrieval_top_tools.join(", ") || "-"}
											</p>
											{result.retrieval_breakdown?.length > 0 && (
												<div className="rounded bg-muted/40 p-2 space-y-1">
													<p className="text-xs font-medium">Score breakdown</p>
													{result.retrieval_breakdown.slice(0, 5).map((entry) => (
														<div
															key={`${result.test_id}-${String(entry.tool_id)}`}
															className="text-[11px] text-muted-foreground"
														>
															{String(entry.rank)}. {String(entry.tool_id)} · lexical{" "}
															{Number(entry.lexical_score ?? 0).toFixed(2)} · embed{" "}
															{Number(entry.embedding_score_weighted ?? 0).toFixed(2)} ·
															ns {Number(entry.namespace_bonus ?? 0).toFixed(2)} · pre{" "}
															{Number(entry.pre_rerank_score ?? 0).toFixed(2)} · rerank{" "}
															{entry.rerank_score == null
																? "-"
																: Number(entry.rerank_score).toFixed(2)}
														</div>
													))}
												</div>
											)}
										</div>
									))}
								</CardContent>
							</Card>

							<Card>
								<CardHeader>
									<CardTitle>Steg 2E: Metadata-förslag</CardTitle>
									<CardDescription>
										Acceptera förslag, spara dem, och kör samma eval igen.
									</CardDescription>
								</CardHeader>
								<CardContent className="space-y-4">
									<div className="flex flex-wrap items-center gap-2">
										<Button variant="outline" onClick={regenerateSuggestions}>
											Regenerera förslag
										</Button>
										<Button
											onClick={applySelectedSuggestionsToDraft}
											disabled={
												!selectedSuggestionIds.size || isApplyingSuggestions
											}
										>
											Applicera valda i draft
										</Button>
										<Button
											onClick={saveSelectedSuggestions}
											disabled={!selectedSuggestionIds.size || isSavingSuggestions}
										>
											Spara valda förslag
										</Button>
										<Button
											onClick={handleRunEvaluation}
											disabled={isEvaluating || isEvalJobRunning}
										>
											Kör om eval
										</Button>
										<Badge variant="outline">
											{selectedSuggestions.length} valda
										</Badge>
									</div>

									{evaluationResult.suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">
											Inga förbättringsförslag hittades för denna run.
										</p>
									) : (
										<div className="space-y-3">
											{evaluationResult.suggestions.map((suggestion) => {
												const isSelected = selectedSuggestionIds.has(suggestion.tool_id);
												return (
													<div
														key={suggestion.tool_id}
														className="rounded border p-3 space-y-2"
													>
														<div className="flex items-center justify-between gap-2">
															<div className="flex items-center gap-2">
																<input
																	type="checkbox"
																	checked={isSelected}
																	onChange={() => toggleSuggestion(suggestion.tool_id)}
																/>
																<Badge variant="secondary">{suggestion.tool_id}</Badge>
																<Badge variant="outline">
																	{suggestion.failed_test_ids.length} fail-case(s)
																</Badge>
															</div>
														</div>
														<p className="text-xs text-muted-foreground">
															{suggestion.rationale}
														</p>
														<div className="grid gap-3 md:grid-cols-2">
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Nuvarande</p>
																<p className="text-xs">
																	{suggestion.current_metadata.description}
																</p>
																<p className="text-[11px] text-muted-foreground mt-2">
																	Keywords:{" "}
																	{suggestion.current_metadata.keywords.join(", ") || "-"}
																</p>
																<div className="mt-2">
																	<p className="text-[11px] text-muted-foreground mb-1">
																		Exempelfrågor
																	</p>
																	<ul className="list-disc pl-4 space-y-1">
																		{suggestion.current_metadata.example_queries
																			.slice(0, 3)
																			.map((example, idx) => (
																				<li key={`${suggestion.tool_id}-current-${idx}`} className="text-[11px]">
																					{example}
																				</li>
																			))}
																	</ul>
																</div>
															</div>
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Föreslagen</p>
																<p className="text-xs">
																	{suggestion.proposed_metadata.description}
																</p>
																<p className="text-[11px] text-muted-foreground mt-2">
																	Keywords:{" "}
																	{suggestion.proposed_metadata.keywords.join(", ") || "-"}
																</p>
																<div className="mt-2">
																	<p className="text-[11px] text-muted-foreground mb-1">
																		Exempelfrågor
																	</p>
																	<ul className="list-disc pl-4 space-y-1">
																		{suggestion.proposed_metadata.example_queries
																			.slice(0, 3)
																			.map((example, idx) => (
																				<li key={`${suggestion.tool_id}-proposed-${idx}`} className="text-[11px]">
																					{example}
																				</li>
																			))}
																	</ul>
																</div>
															</div>
														</div>
													</div>
												);
											})}
										</div>
									)}
								</CardContent>
							</Card>

							<Card>
								<CardHeader>
									<CardTitle>Steg 2F: Prompt-förslag från Agentval Eval</CardTitle>
									<CardDescription>
										Fixar route/sub-route, agentval och plan-kvalitet från starten av
										pipelinen.
									</CardDescription>
								</CardHeader>
								<CardContent className="space-y-4">
									<div className="flex items-center gap-2">
										<Button
											onClick={saveSelectedToolPromptSuggestions}
											disabled={
												!selectedToolPromptSuggestionKeys.size ||
												isSavingToolPromptSuggestions
											}
										>
											Spara valda promptförslag
										</Button>
										<Badge variant="outline">
											{selectedToolPromptSuggestions.length} valda
										</Badge>
									</div>

									{evaluationResult.prompt_suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">
											Inga promptförslag för denna run.
										</p>
									) : (
										<div className="space-y-3">
											{evaluationResult.prompt_suggestions.map((suggestion) => {
												const isSelected =
													selectedToolPromptSuggestionKeys.has(
														suggestion.prompt_key
													);
												return (
													<div
														key={`tool-prompt-${suggestion.prompt_key}`}
														className="rounded border p-3 space-y-2"
													>
														<div className="flex items-center justify-between gap-2">
															<div className="flex items-center gap-2">
																<input
																	type="checkbox"
																	checked={isSelected}
																	onChange={() =>
																		toggleToolPromptSuggestion(
																			suggestion.prompt_key
																		)
																	}
																/>
																<Badge variant="secondary">
																	{suggestion.prompt_key}
																</Badge>
																<Badge variant="outline">
																	{suggestion.failed_test_ids.length} fail-case(s)
																</Badge>
															</div>
														</div>
														<p className="text-xs text-muted-foreground">
															{suggestion.rationale}
														</p>
														<div className="grid gap-3 md:grid-cols-2">
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Nuvarande</p>
																<pre className="text-[11px] whitespace-pre-wrap break-words">
																	{suggestion.current_prompt}
																</pre>
															</div>
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Föreslagen</p>
																<pre className="text-[11px] whitespace-pre-wrap break-words">
																	{suggestion.proposed_prompt}
																</pre>
															</div>
														</div>
													</div>
												);
											})}
										</div>
									)}
								</CardContent>
							</Card>
						</>
					)}

					{apiInputEvaluationResult && (
						<>
							<Card>
								<CardHeader>
									<CardTitle>Steg 3B: API Input Eval Resultat</CardTitle>
									<CardDescription>
										Metadata version {apiInputEvaluationResult.metadata_version_hash} ·
										search space {apiInputEvaluationResult.search_space_id}
									</CardDescription>
								</CardHeader>
								<CardContent className="grid gap-4 md:grid-cols-5">
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Success rate</p>
										<p className="text-2xl font-semibold">
											{(apiInputEvaluationResult.metrics.success_rate * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Route accuracy</p>
										<p className="text-2xl font-semibold">
											{apiInputEvaluationResult.metrics.route_accuracy == null
												? "-"
												: `${(
														apiInputEvaluationResult.metrics.route_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Sub-route accuracy</p>
										<p className="text-2xl font-semibold">
											{apiInputEvaluationResult.metrics.sub_route_accuracy == null
												? "-"
												: `${(
														apiInputEvaluationResult.metrics.sub_route_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Agent accuracy</p>
										<p className="text-2xl font-semibold">
											{apiInputEvaluationResult.metrics.agent_accuracy == null
												? "-"
												: `${(
														apiInputEvaluationResult.metrics.agent_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Plan accuracy</p>
										<p className="text-2xl font-semibold">
											{apiInputEvaluationResult.metrics.plan_accuracy == null
												? "-"
												: `${(
														apiInputEvaluationResult.metrics.plan_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Schema validity</p>
										<p className="text-2xl font-semibold">
											{apiInputEvaluationResult.metrics.schema_validity_rate == null
												? "-"
												: `${(
														apiInputEvaluationResult.metrics.schema_validity_rate * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Required-field recall</p>
										<p className="text-2xl font-semibold">
											{apiInputEvaluationResult.metrics.required_field_recall == null
												? "-"
												: `${(
														apiInputEvaluationResult.metrics.required_field_recall * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Field-value accuracy</p>
										<p className="text-2xl font-semibold">
											{apiInputEvaluationResult.metrics.field_value_accuracy == null
												? "-"
												: `${(
														apiInputEvaluationResult.metrics.field_value_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Clarification accuracy</p>
										<p className="text-2xl font-semibold">
											{apiInputEvaluationResult.metrics.clarification_accuracy == null
												? "-"
												: `${(
														apiInputEvaluationResult.metrics.clarification_accuracy * 100
													).toFixed(1)}%`}
										</p>
									</div>
								</CardContent>
							</Card>

							<Card>
								<CardHeader>
									<CardTitle>Steg 3C: API Input resultat per test</CardTitle>
									<CardDescription>
										Dry-run: vi validerar modellens föreslagna tool-input utan riktiga
										API-anrop.
									</CardDescription>
								</CardHeader>
								<CardContent className="space-y-3">
									{apiInputEvaluationResult.results.map((result) => (
										<div
											key={`api-input-result-${result.test_id}`}
											className="rounded border p-3 space-y-2"
										>
											<div className="flex items-center justify-between gap-2">
												<div className="flex items-center gap-2">
													<Badge variant="outline">{result.test_id}</Badge>
													<Badge variant={result.passed ? "default" : "destructive"}>
														{result.passed ? "PASS" : "FAIL"}
													</Badge>
												</div>
												<div className="text-xs text-muted-foreground">
													Route: {result.expected_route || "-"}
													{result.expected_sub_route
														? ` / ${result.expected_sub_route}`
														: ""}{" "}
													→ {result.selected_route || "-"}
													{result.selected_sub_route
														? ` / ${result.selected_sub_route}`
														: ""}
												</div>
												<div className="text-xs text-muted-foreground">
													Agent: {result.expected_agent || "-"} →{" "}
													{result.selected_agent || "-"}
												</div>
												<div className="text-xs text-muted-foreground">
													Expected: {result.expected_category || "-"} /{" "}
													{result.expected_tool || "-"} · Selected:{" "}
													{result.selected_category || "-"} /{" "}
													{result.selected_tool || "-"}
												</div>
											</div>
											<p className="text-sm">{result.question}</p>
											{result.planning_analysis && (
												<p className="text-xs text-muted-foreground">
													Analys: {result.planning_analysis}
												</p>
											)}
											{result.plan_requirement_checks?.length > 0 && (
												<div className="flex flex-wrap gap-2">
													{result.plan_requirement_checks.map((check, idx) => (
														<Badge
															key={`${result.test_id}-api-plan-${idx}`}
															variant={check.passed ? "outline" : "destructive"}
														>
															{check.requirement}: {check.passed ? "OK" : "MISS"}
														</Badge>
													))}
												</div>
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
														Schema-valid:{" "}
														{result.schema_valid == null
															? "-"
															: result.schema_valid
																? "Ja"
																: "Nej"}
													</p>
													<p className="text-[11px] text-muted-foreground">
														Missing required:{" "}
														{result.missing_required_fields.join(", ") || "-"}
													</p>
													<p className="text-[11px] text-muted-foreground">
														Unexpected fields:{" "}
														{result.unexpected_fields.join(", ") || "-"}
													</p>
													<p className="text-[11px] text-muted-foreground">
														Klargörande:{" "}
														{result.needs_clarification
															? result.clarification_question || "Ja"
															: "Nej"}
													</p>
												</div>
											</div>
											{result.field_checks?.length > 0 && (
												<div className="rounded bg-muted/30 p-2 space-y-1">
													<p className="text-xs font-medium">Field checks</p>
													{result.field_checks.map((check, idx) => (
														<p
															key={`${result.test_id}-field-check-${idx}`}
															className="text-[11px] text-muted-foreground"
														>
															{check.field}: expected{" "}
															{JSON.stringify(check.expected)} · actual{" "}
															{JSON.stringify(check.actual)} ·{" "}
															{check.passed ? "PASS" : "FAIL"}
														</p>
													))}
												</div>
											)}
											{result.schema_errors?.length > 0 && (
												<div className="rounded bg-red-50 p-2 space-y-1">
													<p className="text-xs font-medium text-red-700">Schema errors</p>
													{result.schema_errors.map((error, idx) => (
														<p
															key={`${result.test_id}-schema-error-${idx}`}
															className="text-[11px] text-red-700"
														>
															{error}
														</p>
													))}
												</div>
											)}
										</div>
									))}
								</CardContent>
							</Card>

							<Card>
								<CardHeader>
									<CardTitle>Steg 3D: Prompt-förslag från API Input Eval</CardTitle>
									<CardDescription>
										Välj förslag att spara direkt till Agent Prompts och kör om eval.
									</CardDescription>
								</CardHeader>
								<CardContent className="space-y-4">
									<div className="flex flex-wrap items-center gap-2">
										<Button
											onClick={saveSelectedPromptSuggestions}
											disabled={
												!selectedPromptSuggestionKeys.size || isSavingPromptSuggestions
											}
										>
											Spara valda promptförslag
										</Button>
										<Button
											variant="outline"
											onClick={handleRunApiInputEvaluation}
											disabled={isApiInputEvaluating || isApiInputEvalJobRunning}
										>
											Kör om API input eval
										</Button>
										<Badge variant="outline">
											{selectedPromptSuggestions.length} valda
										</Badge>
									</div>

									{apiInputEvaluationResult.prompt_suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">
											Inga promptförslag hittades för denna run.
										</p>
									) : (
										<div className="space-y-3">
											{apiInputEvaluationResult.prompt_suggestions.map((suggestion) => {
												const isSelected = selectedPromptSuggestionKeys.has(
													suggestion.prompt_key
												);
												return (
													<div
														key={`prompt-suggestion-${suggestion.prompt_key}`}
														className="rounded border p-3 space-y-2"
													>
														<div className="flex items-center justify-between gap-2">
															<div className="flex items-center gap-2">
																<input
																	type="checkbox"
																	checked={isSelected}
																	onChange={() =>
																		togglePromptSuggestion(suggestion.prompt_key)
																	}
																/>
																<Badge variant="secondary">
																	{suggestion.prompt_key}
																</Badge>
																<Badge variant="outline">
																	{suggestion.failed_test_ids.length} fail-case(s)
																</Badge>
															</div>
														</div>
														<p className="text-xs text-muted-foreground">
															{suggestion.rationale}
														</p>
														<div className="grid gap-3 md:grid-cols-2">
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Nuvarande prompt</p>
																<pre className="text-[11px] whitespace-pre-wrap break-words text-muted-foreground max-h-48 overflow-y-auto">
																	{suggestion.current_prompt}
																</pre>
															</div>
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Föreslagen prompt</p>
																<pre className="text-[11px] whitespace-pre-wrap break-words text-muted-foreground max-h-48 overflow-y-auto">
																	{suggestion.proposed_prompt}
																</pre>
															</div>
														</div>
														{suggestion.related_tools.length > 0 && (
															<p className="text-[11px] text-muted-foreground">
																Relaterade verktyg: {suggestion.related_tools.join(", ")}
															</p>
														)}
													</div>
												);
											})}
										</div>
									)}
								</CardContent>
							</Card>
						</>
					)}
				</TabsContent>
			</Tabs>
		</div>
	);
}
