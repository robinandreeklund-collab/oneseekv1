"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAtomValue } from "jotai";
import { Loader2, Lock, Plus, RotateCcw, Save, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import { LifecycleBadge } from "@/components/admin/shared/lifecycle-badge";
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { ToolLifecycleStatusResponse } from "@/contracts/types/admin-tool-lifecycle.types";
import type {
	ToolMetadataItem,
	ToolMetadataUpdateItem,
	ToolRetrievalTuning,
} from "@/contracts/types/admin-tool-settings.types";
import {
	METADATA_MAX_DESCRIPTION_CHARS,
	METADATA_MAX_EXAMPLE_QUERY_CHARS,
	METADATA_MAX_KEYWORD_CHARS,
	METADATA_MAX_NAME_CHARS,
} from "@/contracts/types/admin-tool-settings.types";
import { adminToolLifecycleApiService } from "@/lib/apis/admin-tool-lifecycle-api.service";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LiveRoutingPhase = "shadow" | "tool_gate" | "agent_auto" | "adaptive" | "intent_finetune";

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
// Compact inline field helper
// ---------------------------------------------------------------------------

function InlineField({ label, children }: { label: string; children: React.ReactNode }) {
	return (
		<div className="flex items-center gap-2">
			<Label className="w-20 shrink-0 text-xs text-muted-foreground">{label}</Label>
			{children}
		</div>
	);
}

// ---------------------------------------------------------------------------
// ToolEditor sub-component (compact)
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
	const [showExamples, setShowExamples] = useState(false);

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
		<div className="space-y-2 py-2 px-1">
			<div className="flex items-center gap-2">
				<Label className="w-24 shrink-0 text-xs">Beskrivning:</Label>
				<div className="flex-1 relative">
					<Textarea
						id={`desc-${tool.tool_id}`}
						value={tool.description}
						maxLength={METADATA_MAX_DESCRIPTION_CHARS}
						onChange={(e) => onChange(tool.tool_id, { description: e.target.value })}
						rows={2}
						className="text-xs pr-14"
					/>
					<span className="absolute right-2 bottom-1 text-[10px] text-muted-foreground">
						({tool.description.length}/{METADATA_MAX_DESCRIPTION_CHARS})
					</span>
				</div>
			</div>

			<div className="flex items-start gap-2">
				<Label className="w-24 shrink-0 text-xs pt-1.5">Nyckelord:</Label>
				<div className="flex-1">
					<div className="flex flex-wrap items-center gap-1 mb-1">
						{tool.keywords.map((keyword, index) => (
							<Badge
								key={`kw-${tool.tool_id}-${index}`}
								variant="secondary"
								className="gap-0.5 text-xs py-0 h-5"
							>
								{keyword}
								<button
									onClick={() => removeKeyword(index)}
									className="ml-0.5 hover:text-destructive"
								>
									<X className="h-2.5 w-2.5" />
								</button>
							</Badge>
						))}
						<div className="inline-flex items-center gap-1">
							<Input
								placeholder="+"
								value={newKeyword}
								maxLength={METADATA_MAX_KEYWORD_CHARS}
								onChange={(e) => setNewKeyword(e.target.value)}
								onKeyDown={(e) => {
									if (e.key === "Enter") {
										e.preventDefault();
										addKeyword();
									}
								}}
								className="h-5 w-24 text-xs px-1"
							/>
							<Button onClick={addKeyword} size="sm" variant="ghost" className="h-5 w-5 p-0">
								<Plus className="h-3 w-3" />
							</Button>
						</div>
						<span className="text-[10px] text-muted-foreground">({tool.keywords.length}/20)</span>
					</div>
				</div>
			</div>

			<div className="flex items-center gap-2">
				<Label className="w-24 shrink-0 text-xs">Exempelfr&#229;gor:</Label>
				<span className="text-xs text-muted-foreground">{tool.example_queries.length}/10 st</span>
				<Button
					variant="ghost"
					size="sm"
					className="h-5 text-xs px-2"
					onClick={() => setShowExamples(!showExamples)}
				>
					{showExamples ? "D\u00f6lj" : "Visa/Redigera"}
				</Button>
			</div>

			{showExamples && (
				<div className="ml-26 space-y-1 pl-[6.5rem]">
					{tool.example_queries.map((example, index) => (
						<div key={`eq-${tool.tool_id}-${index}`} className="flex items-center gap-1">
							<span className="flex-1 text-xs bg-muted px-2 py-0.5 rounded truncate">
								{example}
							</span>
							<Button
								onClick={() => removeExample(index)}
								size="sm"
								variant="ghost"
								className="h-5 w-5 p-0"
							>
								<X className="h-3 w-3" />
							</Button>
						</div>
					))}
					<div className="flex gap-1">
						<Input
							placeholder="Ny exempelfr&#229;ga..."
							value={newExample}
							maxLength={METADATA_MAX_EXAMPLE_QUERY_CHARS}
							onChange={(e) => setNewExample(e.target.value)}
							onKeyDown={(e) => {
								if (e.key === "Enter") {
									e.preventDefault();
									addExample();
								}
							}}
							className="h-6 text-xs"
						/>
						<Button onClick={addExample} size="sm" variant="ghost" className="h-6 w-6 p-0">
							<Plus className="h-3 w-3" />
						</Button>
					</div>
				</div>
			)}

			<div className="flex items-center gap-4">
				<div className="flex items-center gap-2">
					<Label className="w-24 shrink-0 text-xs">Excludes:</Label>
					<span className="text-xs text-muted-foreground">
						{(tool.excludes ?? []).length}/15 st
					</span>
				</div>
				{tool.geographic_scope && (
					<span className="text-xs text-muted-foreground">Scope: {tool.geographic_scope}</span>
				)}
			</div>

			{hasChanges && (
				<div className="flex gap-2 pt-1">
					<Button
						onClick={() => onSave(tool.tool_id)}
						size="sm"
						className="gap-1 h-7 text-xs"
						disabled={isSaving}
					>
						<Save className="h-3 w-3" />
						Spara
					</Button>
					<Button
						onClick={() => onReset(tool.tool_id)}
						variant="outline"
						size="sm"
						className="gap-1 h-7 text-xs"
						disabled={isSaving}
					>
						<RotateCcw className="h-3 w-3" />
						&#197;terst&#228;ll
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

	const [searchTerm, setSearchTerm] = useState("");
	const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
	const [draftTools, setDraftTools] = useState<Record<string, ToolMetadataUpdateItem>>({});
	const [draftRetrievalTuning, setDraftRetrievalTuning] = useState<ToolRetrievalTuning | null>(
		null
	);
	const [savingToolId, setSavingToolId] = useState<string | null>(null);
	const [isSavingAll, setIsSavingAll] = useState(false);
	const [isSavingRetrievalTuning, setIsSavingRetrievalTuning] = useState(false);

	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["admin-tool-settings"],
		queryFn: () => adminToolSettingsApiService.getToolSettings(),
		enabled: !!currentUser,
	});

	const { data: apiCategories } = useQuery({
		queryKey: ["admin-tool-api-categories", data?.search_space_id],
		queryFn: () => adminToolSettingsApiService.getToolApiCategories(data?.search_space_id),
		enabled: !!currentUser && typeof data?.search_space_id === "number",
	});

	const { data: lifecycleData } = useQuery({
		queryKey: ["admin-tool-lifecycle"],
		queryFn: () => adminToolLifecycleApiService.getToolLifecycleList(),
		enabled: !!currentUser,
	});

	const { data: catalogData } = useQuery({
		queryKey: ["admin-metadata-catalog", data?.search_space_id],
		queryFn: () => adminToolSettingsApiService.getMetadataCatalog(data?.search_space_id),
		enabled: !!currentUser && typeof data?.search_space_id === "number",
	});

	const lifecycleByToolId = useMemo(() => {
		const map: Record<string, ToolLifecycleStatusResponse> = {};
		if (lifecycleData?.tools) {
			for (const tool of lifecycleData.tools) {
				map[tool.tool_id] = tool;
			}
		}
		return map;
	}, [lifecycleData?.tools]);

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

				if (statusFilter !== "all") {
					const lifecycle = lifecycleByToolId[tool.tool_id];
					const toolStatus = lifecycle?.status ?? "review";
					if (toolStatus !== statusFilter) return false;
				}

				return true;
			}),
		}))
		.filter((category) => category.tools.length > 0);

	const totalTools = filteredCategories.reduce((acc, cat) => acc + cat.tools.length, 0);

	const stabilityLockCount = catalogData?.stability_locks?.locked_count ?? 0;
	const stabilityLockedItems = catalogData?.stability_locks?.locked_items ?? [];

	const separationPairCount = useMemo(() => {
		if (!catalogData?.stability_locks?.locked_items) return 0;
		return stabilityLockedItems.filter(
			(item) =>
				item.lock_reason != null &&
				(item.lock_reason.toLowerCase().includes("separation") ||
					item.lock_reason.toLowerCase().includes("collision"))
		).length;
	}, [catalogData?.stability_locks?.locked_items, stabilityLockedItems]);

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

	const updateRetrievalTuningField = (key: NumericRetrievalTuningField, value: number) => {
		setDraftRetrievalTuning((prev) => {
			const current = prev ?? data?.retrieval_tuning;
			if (!current) return prev;
			if (key === "embedding_weight") {
				const nextEmbeddingWeight = Math.max(0, Number(value));
				const semanticCurrent = Math.max(0, Number(current.semantic_embedding_weight ?? 0));
				const structuralCurrent = Math.max(0, Number(current.structural_embedding_weight ?? 0));
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
				[key]: key === "rerank_candidates" ? Math.max(1, Math.round(value)) : Number(value),
				...(key === "semantic_embedding_weight" || key === "structural_embedding_weight"
					? {
							embedding_weight:
								(key === "semantic_embedding_weight"
									? Math.max(0, Number(value))
									: Math.max(0, Number(current.semantic_embedding_weight ?? 0))) +
								(key === "structural_embedding_weight"
									? Math.max(0, Number(value))
									: Math.max(0, Number(current.structural_embedding_weight ?? 0))),
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
		await adminToolSettingsApiService.updateToolSettings({ tools }, data.search_space_id);
		await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
		await refetch();
	};

	const saveSingleTool = async (toolId: string) => {
		setSavingToolId(toolId);
		try {
			await saveTools([toolId]);
			toast.success(`Sparade metadata f\u00f6r ${toolId}`);
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
			toast.success(`Sparade ${changedToolIds.length} metadata\u00e4ndringar`);
		} catch (_err) {
			toast.error("Kunde inte spara alla metadata\u00e4ndringar");
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
					<p className="text-destructive">Kunde inte ladda tool settings: {String(error)}</p>
				</CardContent>
			</Card>
		);
	}

	return (
		<div className="space-y-6">
			{/* ── Globala retrieval-vikter ─────────────────────────────── */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle>Globala retrieval-vikter</CardTitle>
				</CardHeader>
				<CardContent className="space-y-4">
					{draftRetrievalTuning ? (
						<>
							<div className="grid gap-6 md:grid-cols-2">
								{/* LEFT: Scoring-vikter */}
								<div className="rounded-lg border p-3 space-y-2">
									<p className="text-sm font-medium mb-2">Scoring-vikter</p>
									<InlineField label="namn:">
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
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="keyword:">
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
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="desc:">
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
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="example:">
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
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="sem.emb:">
										<Input
											type="number"
											step="0.1"
											value={draftRetrievalTuning.semantic_embedding_weight ?? 0}
											onChange={(e) =>
												updateRetrievalTuningField(
													"semantic_embedding_weight",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="str.emb:">
										<Input
											type="number"
											step="0.1"
											value={draftRetrievalTuning.structural_embedding_weight ?? 0}
											onChange={(e) =>
												updateRetrievalTuningField(
													"structural_embedding_weight",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="ns.boost:">
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
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
								</div>

								{/* RIGHT: Auto-select */}
								<div className="rounded-lg border p-3 space-y-2">
									<p className="text-sm font-medium mb-2">Auto-select</p>
									<InlineField label="tool score:">
										<Input
											type="number"
											step="0.01"
											value={draftRetrievalTuning.tool_auto_score_threshold ?? 0.6}
											onChange={(e) =>
												updateRetrievalTuningField(
													"tool_auto_score_threshold",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="tool margin:">
										<Input
											type="number"
											step="0.01"
											value={draftRetrievalTuning.tool_auto_margin_threshold ?? 0.25}
											onChange={(e) =>
												updateRetrievalTuningField(
													"tool_auto_margin_threshold",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="agent score:">
										<Input
											type="number"
											step="0.01"
											value={draftRetrievalTuning.agent_auto_score_threshold ?? 0.55}
											onChange={(e) =>
												updateRetrievalTuningField(
													"agent_auto_score_threshold",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 w-20 text-xs"
										/>
									</InlineField>
									<InlineField label="agent marg.:">
										<Input
											type="number"
											step="0.01"
											value={draftRetrievalTuning.agent_auto_margin_threshold ?? 0.18}
											onChange={(e) =>
												updateRetrievalTuningField(
													"agent_auto_margin_threshold",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 w-20 text-xs"
										/>
									</InlineField>

									<Separator className="my-2" />

									<InlineField label="Rerank:">
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
											className="h-7 w-20 text-xs"
										/>
									</InlineField>

									<div className="flex items-center gap-2">
										<Label className="w-20 shrink-0 text-xs text-muted-foreground">Top-K:</Label>
										<div className="flex items-center gap-2 text-xs">
											<span className="text-muted-foreground">I</span>
											<Input
												type="number"
												step="1"
												min={2}
												max={8}
												value={draftRetrievalTuning.intent_candidate_top_k ?? 3}
												onChange={(e) =>
													updateRetrievalTuningField(
														"intent_candidate_top_k",
														Number.parseInt(e.target.value || "3", 10)
													)
												}
												className="h-7 w-14 text-xs"
											/>
											<span className="text-muted-foreground">A</span>
											<Input
												type="number"
												step="1"
												min={2}
												max={8}
												value={draftRetrievalTuning.agent_candidate_top_k ?? 3}
												onChange={(e) =>
													updateRetrievalTuningField(
														"agent_candidate_top_k",
														Number.parseInt(e.target.value || "3", 10)
													)
												}
												className="h-7 w-14 text-xs"
											/>
											<span className="text-muted-foreground">T</span>
											<Input
												type="number"
												step="1"
												min={2}
												max={10}
												value={draftRetrievalTuning.tool_candidate_top_k ?? 5}
												onChange={(e) =>
													updateRetrievalTuningField(
														"tool_candidate_top_k",
														Number.parseInt(e.target.value || "5", 10)
													)
												}
												className="h-7 w-14 text-xs"
											/>
										</div>
									</div>
								</div>
							</div>

							{/* Avancerat (collapsible) */}
							<details className="text-sm">
								<summary className="cursor-pointer text-xs text-muted-foreground font-medium hover:text-foreground">
									Avancerat
								</summary>
								<div className="mt-2 rounded-lg border p-3 grid gap-3 md:grid-cols-3 lg:grid-cols-5">
									<div className="space-y-1">
										<Label className="text-xs">Adaptive delta</Label>
										<Input
											type="number"
											step="0.01"
											value={draftRetrievalTuning.adaptive_threshold_delta ?? 0.08}
											onChange={(e) =>
												updateRetrievalTuningField(
													"adaptive_threshold_delta",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 text-xs"
										/>
									</div>
									<div className="space-y-1">
										<Label className="text-xs">Adaptive min samples</Label>
										<Input
											type="number"
											step="1"
											min={1}
											value={draftRetrievalTuning.adaptive_min_samples ?? 8}
											onChange={(e) =>
												updateRetrievalTuningField(
													"adaptive_min_samples",
													Number.parseInt(e.target.value || "8", 10)
												)
											}
											className="h-7 text-xs"
										/>
									</div>
									<div className="space-y-1">
										<Label className="text-xs">Intent lexical vikt</Label>
										<Input
											type="number"
											step="0.1"
											value={draftRetrievalTuning.intent_lexical_weight ?? 1}
											onChange={(e) =>
												updateRetrievalTuningField(
													"intent_lexical_weight",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 text-xs"
										/>
									</div>
									<div className="space-y-1">
										<Label className="text-xs">Intent semantic vikt</Label>
										<Input
											type="number"
											step="0.1"
											value={draftRetrievalTuning.intent_embedding_weight ?? 1}
											onChange={(e) =>
												updateRetrievalTuningField(
													"intent_embedding_weight",
													Number.parseFloat(e.target.value || "0")
												)
											}
											className="h-7 text-xs"
										/>
									</div>
									<div className="space-y-1">
										<Label className="text-xs">Embedding weight</Label>
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
											className="h-7 text-xs"
										/>
									</div>
								</div>
							</details>

							<div className="flex items-center gap-2">
								<Button
									onClick={saveRetrievalTuning}
									size="sm"
									disabled={!retrievalTuningChanged || isSavingRetrievalTuning}
									className="gap-1 h-8"
								>
									<Save className="h-3.5 w-3.5" />
									{isSavingRetrievalTuning ? "Sparar vikter..." : "Spara vikter"}
								</Button>
								<Button
									variant="outline"
									size="sm"
									className="gap-1 h-8"
									onClick={() => {
										if (data?.retrieval_tuning) {
											setDraftRetrievalTuning({ ...data.retrieval_tuning });
											toast.info("Vikter \u00e5terst\u00e4llda till senast sparade.");
										}
									}}
									disabled={!retrievalTuningChanged}
								>
									<RotateCcw className="h-3.5 w-3.5" />
									&#197;terst&#228;ll till standard
								</Button>
							</div>
						</>
					) : (
						<p className="text-sm text-muted-foreground">Kunde inte l&#228;sa retrieval-vikter.</p>
					)}
				</CardContent>
			</Card>

			{/* ── Per-verktyg metadata ────────────────────────────────── */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle>Per-verktyg metadata</CardTitle>
				</CardHeader>
				<CardContent className="space-y-3">
					<div className="flex flex-wrap items-center gap-3">
						<div className="flex items-center gap-2">
							<Label className="text-xs text-muted-foreground shrink-0">S&#246;k:</Label>
							<Input
								placeholder="S&#246;k verktyg..."
								value={searchTerm}
								onChange={(e) => setSearchTerm(e.target.value)}
								className="h-8 w-48 text-xs"
							/>
						</div>
						<div className="flex items-center gap-2">
							<Label className="text-xs text-muted-foreground shrink-0">Filter:</Label>
							<select
								value={statusFilter}
								onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
								className="flex h-8 rounded-md border border-input bg-background px-2 py-1 text-xs"
							>
								<option value="all">Alla</option>
								<option value="live">Live</option>
								<option value="review">Review</option>
							</select>
						</div>
						<span className="text-xs text-muted-foreground">{totalTools} verktyg</span>
					</div>

					<Accordion type="single" collapsible className="space-y-1">
						{filteredCategories.flatMap((category) =>
							category.tools.map((tool) => {
								const draft = draftTools[tool.tool_id] ?? toUpdateItem(tool);
								const changed = changedToolSet.has(tool.tool_id);
								const lifecycle = lifecycleByToolId[tool.tool_id];
								const isLocked = stabilityLockedItems.some((item) => item.item_id === tool.tool_id);
								return (
									<AccordionItem
										key={tool.tool_id}
										value={tool.tool_id}
										className="border rounded-md px-3"
									>
										<AccordionTrigger className="hover:no-underline py-2">
											<div className="flex items-center gap-2 text-sm">
												<span className="font-mono text-xs">{draft.tool_id}</span>
												<span className="text-muted-foreground">&#8212;</span>
												{lifecycle && (
													<LifecycleBadge
														status={lifecycle.status === "live" ? "live" : "review"}
														successRate={lifecycle.success_rate}
														requiredSuccessRate={lifecycle.required_success_rate}
														compact
													/>
												)}
												{lifecycle?.success_rate != null && (
													<span className="text-xs tabular-nums text-muted-foreground">
														{formatPercent(lifecycle.success_rate)}
													</span>
												)}
												{isLocked && <Lock className="h-3 w-3 text-muted-foreground" />}
												{changed && (
													<Badge variant="outline" className="text-[10px] h-4 px-1">
														&#228;ndrad
													</Badge>
												)}
											</div>
										</AccordionTrigger>
										<AccordionContent>
											<ToolEditor
												tool={draft}
												original={tool}
												onChange={onToolChange}
												onSave={saveSingleTool}
												onReset={resetTool}
												isSaving={savingToolId === tool.tool_id}
											/>
										</AccordionContent>
									</AccordionItem>
								);
							})
						)}
					</Accordion>

					{filteredCategories.length === 0 && (
						<p className="text-sm text-muted-foreground text-center py-6">
							Inga verktyg matchade s&#246;kningen &quot;{searchTerm}&quot;
						</p>
					)}

					{changedToolIds.length > 0 && (
						<div className="pt-2">
							<Button onClick={saveAllChanges} disabled={isSavingAll} size="sm" className="gap-1">
								<Save className="h-3.5 w-3.5" />
								{isSavingAll ? "Sparar..." : `Spara alla \u00e4ndringar (${changedToolIds.length})`}
							</Button>
						</div>
					)}
				</CardContent>
			</Card>

			{/* ── L\u00e5s-hantering ──────────────────────────────────────── */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="flex items-center gap-2">
						<Lock className="h-4 w-4" />
						L&#229;s-hantering
					</CardTitle>
				</CardHeader>
				<CardContent className="space-y-2">
					<div className="flex items-center justify-between rounded-md border px-3 py-2">
						<div className="flex items-center gap-2 text-sm">
							<Lock className="h-3.5 w-3.5 text-muted-foreground" />
							<span>Stabilitets-l&#229;s:</span>
							<span className="font-medium tabular-nums">{stabilityLockCount} verktyg</span>
						</div>
						<Button variant="ghost" size="sm" className="h-7 text-xs" disabled>
							Hantera &#8594;
						</Button>
					</div>
					<div className="flex items-center justify-between rounded-md border px-3 py-2">
						<div className="flex items-center gap-2 text-sm">
							<ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
							<span>Separations-l&#229;s:</span>
							<span className="font-medium tabular-nums">{separationPairCount} par</span>
						</div>
						<Button variant="ghost" size="sm" className="h-7 text-xs" disabled>
							Hantera &#8594;
						</Button>
					</div>
				</CardContent>
			</Card>
		</div>
	);
}
