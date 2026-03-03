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
import type { ToolLifecycleStatusResponse } from "@/contracts/types/admin-tool-lifecycle.types";
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
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { Separator } from "@/components/ui/separator";
import { Save, RotateCcw, Plus, X, Loader2, Lock, ShieldCheck } from "lucide-react";
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

type StatusFilter = "all" | "live" | "review";

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
	const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
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

	const { data: lifecycleData } = useQuery({
		queryKey: ["admin-tool-lifecycle"],
		queryFn: () => adminToolLifecycleApiService.getToolLifecycleList(),
		enabled: !!currentUser,
	});

	const { data: catalogData } = useQuery({
		queryKey: ["admin-metadata-catalog", data?.search_space_id],
		queryFn: () =>
			adminToolSettingsApiService.getMetadataCatalog(data?.search_space_id),
		enabled: !!currentUser && typeof data?.search_space_id === "number",
	});

	// ---- Lifecycle lookup map -----------------------------------------------
	const lifecycleByToolId = useMemo(() => {
		const map: Record<string, ToolLifecycleStatusResponse> = {};
		if (lifecycleData?.tools) {
			for (const tool of lifecycleData.tools) {
				map[tool.tool_id] = tool;
			}
		}
		return map;
	}, [lifecycleData?.tools]);

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
				const matchesSearch =
					draft.name.toLowerCase().includes(term) ||
					draft.description.toLowerCase().includes(term) ||
					draft.tool_id.toLowerCase().includes(term);

				if (!matchesSearch) return false;

				// Apply lifecycle status filter
				if (statusFilter !== "all") {
					const lifecycle = lifecycleByToolId[tool.tool_id];
					const toolStatus = lifecycle?.status ?? "review";
					if (toolStatus !== statusFilter) return false;
				}

				return true;
			}),
		}))
		.filter((category) => category.tools.length > 0);

	const totalTools = filteredCategories.reduce(
		(acc, cat) => acc + cat.tools.length,
		0
	);

	// ---- Lock management derived data ---------------------------------------
	const stabilityLockCount = catalogData?.stability_locks?.locked_count ?? 0;
	const stabilityLockedItems = catalogData?.stability_locks?.locked_items ?? [];

	// Count unique tool confusion pairs from the audit data as separation lock proxy
	const separationPairCount = useMemo(() => {
		if (!catalogData?.stability_locks?.locked_items) return 0;
		// Count items that have a non-null lock_reason containing "separation" or "collision"
		return stabilityLockedItems.filter(
			(item) =>
				item.lock_reason != null &&
				(item.lock_reason.toLowerCase().includes("separation") ||
					item.lock_reason.toLowerCase().includes("collision"))
		).length;
	}, [catalogData?.stability_locks?.locked_items, stabilityLockedItems]);

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
			{/* Globala retrieval-vikter */}
			<Card>
				<CardHeader>
					<CardTitle>Globala retrieval-vikter</CardTitle>
					<CardDescription>
						Styr hur tool_retrieval viktar namn, keywords, embeddings och rerank.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					{draftRetrievalTuning ? (
						<>
							{/* Auto-select thresholds + Top-K */}
							<div className="rounded-lg border p-3 space-y-3">
								<p className="text-sm font-medium">Auto-select trösklar och Top-K</p>
								<div className="grid gap-3 md:grid-cols-3 lg:grid-cols-4">
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
								<div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
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
										: "Spara vikter"}
								</Button>
								<Button
									variant="outline"
									onClick={() => {
										if (data?.retrieval_tuning) {
											setDraftRetrievalTuning({ ...data.retrieval_tuning });
											toast.info("Vikter återställda till senast sparade.");
										}
									}}
									disabled={!retrievalTuningChanged}
								>
									<RotateCcw className="h-4 w-4 mr-1" />
									Återställ
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

			{/* Search bar + filters + save-all */}
			<div className="flex flex-wrap items-center gap-4">
				<Input
					placeholder="Sök verktyg..."
					value={searchTerm}
					onChange={(e) => setSearchTerm(e.target.value)}
					className="max-w-md"
				/>
				<select
					value={statusFilter}
					onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
					className="flex h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
				>
					<option value="all">Alla</option>
					<option value="live">Live</option>
					<option value="review">Review</option>
				</select>
				<div className="text-sm text-muted-foreground">
					{totalTools} verktyg i {filteredCategories.length} kategorier
				</div>
				{lifecycleData && (
					<div className="flex items-center gap-2 text-xs text-muted-foreground">
						<Badge variant="default" className="bg-green-600 hover:bg-green-700 text-xs">
							{lifecycleData.live_count} Live
						</Badge>
						<Badge variant="secondary" className="text-xs">
							{lifecycleData.review_count} Review
						</Badge>
					</div>
				)}
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
											const lifecycle = lifecycleByToolId[tool.tool_id];
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
																{lifecycle && (
																	<LifecycleBadge
																		status={
																			lifecycle.status === "live"
																				? "live"
																				: "review"
																		}
																		successRate={lifecycle.success_rate}
																		requiredSuccessRate={
																			lifecycle.required_success_rate
																		}
																	/>
																)}
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

			{/* Lock management section */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Lock className="h-5 w-5" />
						Lås-hantering
					</CardTitle>
					<CardDescription>
						Översikt av stabilitets- och separationslås. Lås skyddar verktygsmetadata
						från oavsiktliga ändringar under pågående optimering.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="grid gap-4 md:grid-cols-2">
						{/* Stability locks */}
						<div className="rounded-lg border p-4 space-y-3">
							<div className="flex items-center gap-2">
								<ShieldCheck className="h-4 w-4 text-muted-foreground" />
								<p className="text-sm font-medium">Stabilitets-lås</p>
							</div>
							<div className="flex items-baseline gap-2">
								<span className="text-3xl font-bold tabular-nums">
									{stabilityLockCount}
								</span>
								<span className="text-sm text-muted-foreground">
									verktyg låsta
								</span>
							</div>
							{stabilityLockedItems.length > 0 && (
								<div className="max-h-32 overflow-auto space-y-1">
									{stabilityLockedItems.slice(0, 5).map((item) => (
										<div
											key={`stab-lock-${item.item_id}`}
											className="flex items-center gap-2 text-xs text-muted-foreground"
										>
											<Lock className="h-3 w-3 shrink-0" />
											<span className="truncate font-mono">
												{item.item_id}
											</span>
											{item.lock_level && (
												<Badge variant="outline" className="text-[10px] shrink-0">
													{item.lock_level}
												</Badge>
											)}
										</div>
									))}
									{stabilityLockedItems.length > 5 && (
										<p className="text-xs text-muted-foreground">
											... och {stabilityLockedItems.length - 5} till
										</p>
									)}
								</div>
							)}
							<Button variant="outline" size="sm" className="w-full" disabled>
								Hantera →
							</Button>
						</div>

						{/* Separation locks */}
						<div className="rounded-lg border p-4 space-y-3">
							<div className="flex items-center gap-2">
								<Lock className="h-4 w-4 text-muted-foreground" />
								<p className="text-sm font-medium">Separations-lås</p>
							</div>
							<div className="flex items-baseline gap-2">
								<span className="text-3xl font-bold tabular-nums">
									{separationPairCount}
								</span>
								<span className="text-sm text-muted-foreground">
									kollisionspar
								</span>
							</div>
							<p className="text-xs text-muted-foreground">
								Antal verktyg med separations- eller kollisionslås som förhindrar
								samtidiga metadataändringar på konkurrerande verktyg.
							</p>
							<Button variant="outline" size="sm" className="w-full" disabled>
								Hantera →
							</Button>
						</div>
					</div>

					{catalogData?.stability_locks && (
						<div className="mt-4 flex items-center gap-3 text-xs text-muted-foreground">
							<Badge
								variant={
									catalogData.stability_locks.lock_mode_enabled
										? "default"
										: "outline"
								}
								className="text-xs"
							>
								Lås-läge:{" "}
								{catalogData.stability_locks.lock_mode_enabled
									? "Aktivt"
									: "Av"}
							</Badge>
							<Badge
								variant={
									catalogData.stability_locks.auto_lock_enabled
										? "default"
										: "outline"
								}
								className="text-xs"
							>
								Auto-lås:{" "}
								{catalogData.stability_locks.auto_lock_enabled
									? "Aktivt"
									: "Av"}
							</Badge>
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}
