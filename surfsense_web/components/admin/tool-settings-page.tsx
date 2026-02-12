"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { toast } from "sonner";
import { useAtomValue } from "jotai";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type {
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
	const [evalInputError, setEvalInputError] = useState<string | null>(null);
	const [isEvaluating, setIsEvaluating] = useState(false);
	const [retrievalLimit, setRetrievalLimit] = useState(5);
	const [includeDraftMetadata, setIncludeDraftMetadata] = useState(true);
	const [evaluationResult, setEvaluationResult] =
		useState<ToolEvaluationResponse | null>(null);
	const [selectedSuggestionIds, setSelectedSuggestionIds] = useState<Set<string>>(
		new Set()
	);
	const [isApplyingSuggestions, setIsApplyingSuggestions] = useState(false);
	const [isSavingSuggestions, setIsSavingSuggestions] = useState(false);

	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["admin-tool-settings"],
		queryFn: () => adminToolSettingsApiService.getToolSettings(),
		enabled: !!currentUser,
	});

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
						item.expected || item.expected_tool || item.expected_category
							? {
									tool: item.expected?.tool ?? item.expected_tool ?? null,
									category:
										item.expected?.category ?? item.expected_category ?? null,
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

	const handleRunEvaluation = async () => {
		const parsedInput = parseEvalInput();
		if (!parsedInput) return;
		setIsEvaluating(true);
		try {
			const response = await adminToolSettingsApiService.evaluateToolSettings({
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
			setEvaluationResult(response);
			setSelectedSuggestionIds(new Set());
			toast.success("Eval-run klar");
		} catch (err) {
			toast.error("Eval-run misslyckades");
		} finally {
			setIsEvaluating(false);
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

	const uploadEvalFile = async (event: ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		if (!file) return;
		const content = await file.text();
		setEvalInput(content);
		setEvalInputError(null);
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
							<CardTitle>Eval Input (JSON)</CardTitle>
							<CardDescription>
								Ladda upp ett eval-JSON med testfrågor och förväntade tool/category.
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
								<Button onClick={handleRunEvaluation} disabled={isEvaluating}>
									{isEvaluating ? "Kör eval..." : "Run Tool Evaluation"}
								</Button>
							</div>
							<Textarea
								placeholder='{"eval_name":"routing-smoke","tests":[{"id":"t1","question":"...","expected":{"tool":"...","category":"..."}}]}'
								value={evalInput}
								onChange={(e) => setEvalInput(e.target.value)}
								rows={12}
								className="font-mono text-xs"
							/>
							{evalInputError && (
								<Alert variant="destructive">
									<AlertCircle className="h-4 w-4" />
									<AlertDescription>{evalInputError}</AlertDescription>
								</Alert>
							)}
						</CardContent>
					</Card>

					{evaluationResult && (
						<>
							<Card>
								<CardHeader>
									<CardTitle>Eval Resultat</CardTitle>
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

							<Card>
								<CardHeader>
									<CardTitle>Retrieval-vikter i denna eval</CardTitle>
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
									<CardTitle>Resultat per test</CardTitle>
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
									<CardTitle>Metadata-förslag</CardTitle>
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
										<Button onClick={handleRunEvaluation} disabled={isEvaluating}>
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
															</div>
															<div className="rounded bg-muted/50 p-2">
																<p className="text-xs font-medium mb-1">Föreslagen</p>
																<p className="text-xs">
																	{suggestion.proposed_metadata.description}
																</p>
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
				</TabsContent>
			</Tabs>
		</div>
	);
}
