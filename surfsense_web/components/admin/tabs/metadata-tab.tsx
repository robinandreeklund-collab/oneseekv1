"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useAtomValue } from "jotai";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type {
	ToolMetadataItem,
	ToolMetadataUpdateItem,
	ToolRetrievalTuning,
} from "@/contracts/types/admin-tool-settings.types";
import {
	METADATA_MAX_NAME_CHARS,
	METADATA_MAX_DESCRIPTION_CHARS,
	METADATA_MAX_KEYWORD_CHARS,
	METADATA_MAX_EXAMPLE_QUERY_CHARS,
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
import { Save, RotateCcw, Plus, X, Loader2 } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { LifecycleBadge } from "@/components/admin/shared/lifecycle-badge";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LiveRoutingPhase =
	| "shadow"
	| "tool_gate"
	| "agent_auto"
	| "adaptive"
	| "intent_finetune";

type NumericRetrievalTuningField = {
	[K in keyof ToolRetrievalTuning]: ToolRetrievalTuning[K] extends number ? K : never;
}[keyof ToolRetrievalTuning];

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

function isEqualTuning(left: ToolRetrievalTuning, right: ToolRetrievalTuning) {
	return JSON.stringify(left) === JSON.stringify(right);
}

function formatPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	return `${(value * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// ToolEditor sub-component
// ---------------------------------------------------------------------------

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
	};

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
	};

	return (
		<div className="space-y-4">
			<div className="space-y-2">
				<Label htmlFor={`name-${tool.tool_id}`}>Namn</Label>
				<Input
					id={`name-${tool.tool_id}`}
					value={tool.name}
					maxLength={METADATA_MAX_NAME_CHARS}
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
					maxLength={METADATA_MAX_DESCRIPTION_CHARS}
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
						<Badge key={`kw-${tool.tool_id}-${index}`} variant="secondary" className="gap-1">
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
						maxLength={METADATA_MAX_KEYWORD_CHARS}
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
						<div key={`eq-${tool.tool_id}-${index}`} className="flex items-center gap-2">
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
						maxLength={METADATA_MAX_EXAMPLE_QUERY_CHARS}
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

// ---------------------------------------------------------------------------
// MetadataTab component
// ---------------------------------------------------------------------------

export function MetadataTab() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const queryClient = useQueryClient();

	// ---- Local state -------------------------------------------------------
	const [searchTerm, setSearchTerm] = useState("");
	const [draftTools, setDraftTools] = useState<Record<string, ToolMetadataUpdateItem>>({});
	const [draftRetrievalTuning, setDraftRetrievalTuning] =
		useState<ToolRetrievalTuning | null>(null);
	const [savingToolId, setSavingToolId] = useState<string | null>(null);
	const [isSavingAll, setIsSavingAll] = useState(false);
	const [isSavingRetrievalTuning, setIsSavingRetrievalTuning] = useState(false);

	// ---- React Query hooks --------------------------------------------------
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

	// ---- Derived data -------------------------------------------------------
	const originalTools = useMemo(() => {
		const byId: Record<string, ToolMetadataItem> = {};
		for (const category of data?.categories ?? []) {
			for (const tool of category.tools) {
				byId[tool.tool_id] = tool;
			}
		}
		return byId;
	}, [data?.categories]);

	const changedToolIds = useMemo(() => {
		return Object.keys(draftTools).filter((toolId) => {
			const original = originalTools[toolId];
			if (!original) return false;
			return !isEqualTool(draftTools[toolId], toUpdateItem(original));
		});
	}, [draftTools, originalTools]);

	const changedToolSet = useMemo(() => new Set(changedToolIds), [changedToolIds]);

	const retrievalTuningChanged = useMemo(() => {
		if (!draftRetrievalTuning || !data?.retrieval_tuning) return false;
		return !isEqualTuning(draftRetrievalTuning, data.retrieval_tuning);
	}, [draftRetrievalTuning, data?.retrieval_tuning]);

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

	// ---- Effects ------------------------------------------------------------
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

	// ---- Handlers: retrieval tuning -----------------------------------------
	const updateRetrievalTuningField = (
		key: NumericRetrievalTuningField,
		value: number
	) => {
		setDraftRetrievalTuning((prev) => {
			const current = prev ?? data?.retrieval_tuning;
			if (!current) return prev;
			if (key === "embedding_weight") {
				const nextEmbeddingWeight = Math.max(0, Number(value));
				const semanticCurrent = Math.max(0, Number(current.semantic_embedding_weight ?? 0));
				const structuralCurrent = Math.max(
					0,
					Number(current.structural_embedding_weight ?? 0)
				);
				const currentTotal = semanticCurrent + structuralCurrent;
				const semanticNext =
					currentTotal > 0
						? (semanticCurrent / currentTotal) * nextEmbeddingWeight
						: nextEmbeddingWeight * 0.7;
				const structuralNext = Math.max(0, nextEmbeddingWeight - semanticNext);
				return {
					...current,
					embedding_weight: nextEmbeddingWeight,
					semantic_embedding_weight: semanticNext,
					structural_embedding_weight: structuralNext,
				};
			}
			return {
				...current,
				[key]:
					key === "rerank_candidates"
						? Math.max(1, Math.round(value))
						: Number(value),
				...(key === "semantic_embedding_weight" || key === "structural_embedding_weight"
					? {
							embedding_weight:
								(key === "semantic_embedding_weight"
									? Math.max(0, Number(value))
									: Math.max(
											0,
											Number(current.semantic_embedding_weight ?? 0)
										)) +
								(key === "structural_embedding_weight"
									? Math.max(0, Number(value))
									: Math.max(
											0,
											Number(current.structural_embedding_weight ?? 0)
										)),
						}
					: {}),
			};
		});
	};

	const updateRetrievalTuningToggle = (
		key: "live_routing_enabled" | "retrieval_feedback_db_enabled",
		value: boolean
	) => {
		setDraftRetrievalTuning((prev) => {
			const current = prev ?? data?.retrieval_tuning;
			if (!current) return prev;
			return {
				...current,
				[key]: Boolean(value),
			};
		});
	};

	const updateRetrievalPhase = (phase: LiveRoutingPhase) => {
		setDraftRetrievalTuning((prev) => {
			const current = prev ?? data?.retrieval_tuning;
			if (!current) return prev;
			return {
				...current,
				live_routing_phase: phase,
			};
		});
	};

	// ---- Handlers: tool edits -----------------------------------------------
	const onToolChange = (toolId: string, updates: Partial<ToolMetadataUpdateItem>) => {
		setDraftTools((prev) => ({
			...prev,
			[toolId]: {
				...prev[toolId],
				...updates,
			},
		}));
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
		} catch (_err) {
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
		} catch (_err) {
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
		} catch (_error) {
			toast.error("Kunde inte spara retrieval-vikter");
		} finally {
			setIsSavingRetrievalTuning(false);
		}
	};

	// ---- Loading / error states ---------------------------------------------
	if (isLoading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	if (error) {
		return (
			<Card>
				<CardContent className="py-12 text-center">
					<p className="text-destructive">
						Kunde inte ladda tool settings: {String(error)}
					</p>
				</CardContent>
			</Card>
		);
	}

	// ---- Render -------------------------------------------------------------
	return (
		<div className="space-y-6">
			{/* Guide card */}
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
								Spara ändringar i metadata-fliken (enskilt eller "Spara alla
								ändringar").
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
						Tips: "Senaste eval-körning" visar snabb status på hur senaste
						justeringar presterade.
					</p>
				</CardContent>
			</Card>

			{/* API categories overview */}
			{apiCategories?.providers?.length ? (
				<Card>
					<CardHeader>
						<CardTitle>API-kategorier (alla providers)</CardTitle>
						<CardDescription>
							Översikt av tillgängliga providers, API-kategorier och underkategorier
							för testdesign i Tool Evaluation.
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
								<div
									key={provider.provider_key}
									className="rounded border p-3 space-y-3"
								>
									<div className="flex flex-wrap items-center gap-2">
										<Badge variant="secondary">{provider.provider_name}</Badge>
										<Badge variant="outline">{topLevel.length} toppnivå</Badge>
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
														<p className="font-medium">
															{item.category_name}
														</p>
														<p className="text-muted-foreground">
															{item.tool_id}
															{item.base_path
																? ` · ${item.base_path}`
																: ""}
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
														<p className="font-medium">
															{item.tool_name}
														</p>
														<p className="text-muted-foreground">
															{item.category_name} · {item.tool_id}
															{item.base_path
																? ` · ${item.base_path}`
																: ""}
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

			{/* Latest eval summary */}
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

			{/* Retrieval Tuning card */}
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
							{/* Live routing rollout */}
							<div className="rounded-lg border p-3 space-y-3">
								<div className="flex flex-wrap items-center justify-between gap-3">
									<div>
										<p className="text-sm font-medium">Live routing rollout</p>
										<p className="text-xs text-muted-foreground">
											Aktivera fasstyrd utrullning (Shadow → Tool gate → Agent
											auto → Adaptive → Intent finjustering).
										</p>
									</div>
									<div className="flex items-center gap-2">
										<Badge
											variant={
												draftRetrievalTuning.live_routing_enabled
													? "default"
													: "outline"
											}
										>
											{draftRetrievalTuning.live_routing_enabled
												? "Aktiv"
												: "Av"}
										</Badge>
										<Switch
											checked={
												draftRetrievalTuning.live_routing_enabled ?? false
											}
											onCheckedChange={(checked) =>
												updateRetrievalTuningToggle(
													"live_routing_enabled",
													checked
												)
											}
										/>
									</div>
								</div>
								<div className="grid gap-3 md:grid-cols-3">
									<div className="space-y-1 md:col-span-2">
										<Label>Aktiv fas</Label>
										<select
											value={
												draftRetrievalTuning.live_routing_phase ?? "shadow"
											}
											onChange={(event) =>
												updateRetrievalPhase(
													event.target.value as LiveRoutingPhase
												)
											}
											className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
										>
											<option value="shadow">Fas 0 — Shadow mode</option>
											<option value="tool_gate">Fas 1 — Tool gate</option>
											<option value="agent_auto">
												Fas 1b — Agent auto-select
											</option>
											<option value="adaptive">
												Fas 2 — Adaptiva per-tool thresholds
											</option>
											<option value="intent_finetune">
												Fas 3 — Intent shortlist/vikter
											</option>
										</select>
									</div>
									<div className="space-y-1">
										<Label>Tool candidate top-K</Label>
										<Input
											type="number"
											step="1"
											min={2}
											max={10}
											value={
												draftRetrievalTuning.tool_candidate_top_k ?? 5
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"tool_candidate_top_k",
													Number.parseInt(e.target.value || "5", 10)
												)
											}
										/>
									</div>
								</div>
								{/* Auto-select thresholds grid */}
								<div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
									<div className="space-y-1">
										<Label>Intent top-K</Label>
										<Input
											type="number"
											step="1"
											min={2}
											max={8}
											value={
												draftRetrievalTuning.intent_candidate_top_k ?? 3
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"intent_candidate_top_k",
													Number.parseInt(e.target.value || "3", 10)
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Agent top-K</Label>
										<Input
											type="number"
											step="1"
											min={2}
											max={8}
											value={
												draftRetrievalTuning.agent_candidate_top_k ?? 3
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"agent_candidate_top_k",
													Number.parseInt(e.target.value || "3", 10)
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Agent margin</Label>
										<Input
											type="number"
											step="0.01"
											value={
												draftRetrievalTuning.agent_auto_margin_threshold ??
												0.18
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"agent_auto_margin_threshold",
													Number.parseFloat(e.target.value || "0")
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Agent top1 score</Label>
										<Input
											type="number"
											step="0.01"
											value={
												draftRetrievalTuning.agent_auto_score_threshold ??
												0.55
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"agent_auto_score_threshold",
													Number.parseFloat(e.target.value || "0")
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Tool margin</Label>
										<Input
											type="number"
											step="0.01"
											value={
												draftRetrievalTuning.tool_auto_margin_threshold ??
												0.25
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"tool_auto_margin_threshold",
													Number.parseFloat(e.target.value || "0")
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Tool top1 score</Label>
										<Input
											type="number"
											step="0.01"
											value={
												draftRetrievalTuning.tool_auto_score_threshold ??
												0.6
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"tool_auto_score_threshold",
													Number.parseFloat(e.target.value || "0")
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Adaptive delta</Label>
										<Input
											type="number"
											step="0.01"
											value={
												draftRetrievalTuning.adaptive_threshold_delta ??
												0.08
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"adaptive_threshold_delta",
													Number.parseFloat(e.target.value || "0")
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Adaptive min samples</Label>
										<Input
											type="number"
											step="1"
											min={1}
											value={
												draftRetrievalTuning.adaptive_min_samples ?? 8
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"adaptive_min_samples",
													Number.parseInt(e.target.value || "8", 10)
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Intent lexical vikt</Label>
										<Input
											type="number"
											step="0.1"
											value={
												draftRetrievalTuning.intent_lexical_weight ?? 1
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"intent_lexical_weight",
													Number.parseFloat(e.target.value || "0")
												)
											}
										/>
									</div>
									<div className="space-y-1">
										<Label>Intent semantic vikt</Label>
										<Input
											type="number"
											step="0.1"
											value={
												draftRetrievalTuning.intent_embedding_weight ?? 1
											}
											onChange={(e) =>
												updateRetrievalTuningField(
													"intent_embedding_weight",
													Number.parseFloat(e.target.value || "0")
												)
											}
										/>
									</div>
								</div>
							</div>

							{/* Scoring weights grid */}
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
									<Label>Semantic embedding</Label>
									<Input
										type="number"
										step="0.1"
										value={
											draftRetrievalTuning.semantic_embedding_weight ?? 0
										}
										onChange={(e) =>
											updateRetrievalTuningField(
												"semantic_embedding_weight",
												Number.parseFloat(e.target.value || "0")
											)
										}
									/>
								</div>
								<div className="space-y-1">
									<Label>Structural embedding</Label>
									<Input
										type="number"
										step="0.1"
										value={
											draftRetrievalTuning.structural_embedding_weight ?? 0
										}
										onChange={(e) =>
											updateRetrievalTuningField(
												"structural_embedding_weight",
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

							{/* Save retrieval tuning */}
							<div className="flex items-center gap-2">
								<Badge variant="outline">
									{retrievalTuningChanged
										? "Osparade viktändringar"
										: "Vikter i synk"}
								</Badge>
								<Button
									onClick={saveRetrievalTuning}
									disabled={
										!retrievalTuningChanged || isSavingRetrievalTuning
									}
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

			{/* Search bar + save-all */}
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

			{/* Per-tool accordion */}
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
											const draft =
												draftTools[tool.tool_id] ??
												toUpdateItem(tool);
											const changed = changedToolSet.has(tool.tool_id);
											return (
												<div key={tool.tool_id}>
													{index > 0 && (
														<Separator className="my-6" />
													)}
													<div className="space-y-4">
														<div>
															<div className="flex items-center gap-2 mb-1">
																<h3 className="font-semibold">
																	{draft.name}
																</h3>
																<Badge
																	variant="secondary"
																	className="text-xs"
																>
																	{draft.tool_id}
																</Badge>
																{(tool.has_override ||
																	changed) && (
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
															isSaving={
																savingToolId === tool.tool_id
															}
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

			{/* Empty state */}
			{filteredCategories.length === 0 && (
				<Card>
					<CardContent className="py-12 text-center">
						<p className="text-muted-foreground">
							Inga verktyg matchade sökningen &quot;{searchTerm}&quot;
						</p>
					</CardContent>
				</Card>
			)}
		</div>
	);
}
