"use client";

/**
 * Tool Catalog Panel — Panel 2
 *
 * Domain-grouped catalog with inline metadata editing,
 * lifecycle badges, and live change tracking.
 */

import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Loader2, Lock, Plus, RotateCcw, Save, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { LifecycleBadge } from "@/components/admin/shared/lifecycle-badge";
import {
	arraysEqual,
	type DomainGroup,
	formatPercent,
	type ToolWithLifecycle,
	useToolCatalog,
} from "@/components/admin/tools/hooks/use-tool-catalog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type {
	ToolMetadataItem,
	ToolMetadataUpdateItem,
} from "@/contracts/types/admin-tool-settings.types";
import {
	METADATA_MAX_DESCRIPTION_CHARS,
	METADATA_MAX_EXAMPLE_QUERY_CHARS,
	METADATA_MAX_KEYWORD_CHARS,
} from "@/contracts/types/admin-tool-settings.types";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type StatusFilter = "all" | "live" | "review";

function toUpdateItem(tool: ToolMetadataItem): ToolMetadataUpdateItem {
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

function isToolChanged(draft: ToolMetadataUpdateItem, original: ToolMetadataItem): boolean {
	const orig = toUpdateItem(original);
	return (
		draft.name !== orig.name ||
		draft.description !== orig.description ||
		draft.category !== orig.category ||
		draft.main_identifier !== orig.main_identifier ||
		draft.core_activity !== orig.core_activity ||
		draft.unique_scope !== orig.unique_scope ||
		draft.geographic_scope !== orig.geographic_scope ||
		!arraysEqual(draft.keywords, orig.keywords) ||
		!arraysEqual(draft.example_queries, orig.example_queries) ||
		!arraysEqual(draft.excludes ?? [], orig.excludes ?? [])
	);
}

// ---------------------------------------------------------------------------
// Inline tool editor
// ---------------------------------------------------------------------------

function ToolEditor({
	draft,
	hasChanges,
	isSaving,
	onUpdate,
	onSave,
	onReset,
}: {
	draft: ToolMetadataUpdateItem;
	hasChanges: boolean;
	isSaving: boolean;
	onUpdate: (updates: Partial<ToolMetadataUpdateItem>) => void;
	onSave: () => void;
	onReset: () => void;
}) {
	const [newKeyword, setNewKeyword] = useState("");
	const [newExample, setNewExample] = useState("");
	const [showExamples, setShowExamples] = useState(false);

	const addKeyword = () => {
		if (newKeyword.trim()) {
			onUpdate({ keywords: [...draft.keywords, newKeyword.trim()] });
			setNewKeyword("");
		}
	};

	const addExample = () => {
		if (newExample.trim()) {
			onUpdate({ example_queries: [...draft.example_queries, newExample.trim()] });
			setNewExample("");
		}
	};

	return (
		<div className="space-y-3 py-3">
			{/* Description */}
			<div className="space-y-1">
				<Label className="text-xs text-muted-foreground">Beskrivning</Label>
				<div className="relative">
					<Textarea
						value={draft.description}
						maxLength={METADATA_MAX_DESCRIPTION_CHARS}
						onChange={(e) => onUpdate({ description: e.target.value })}
						rows={2}
						className="text-sm pr-16"
					/>
					<span className="absolute right-2 bottom-1.5 text-[10px] text-muted-foreground">
						{draft.description.length}/{METADATA_MAX_DESCRIPTION_CHARS}
					</span>
				</div>
			</div>

			{/* Identity fields grid */}
			<div className="grid gap-3 md:grid-cols-2">
				<div className="space-y-1">
					<Label className="text-xs text-muted-foreground">Huvudidentifierare</Label>
					<Input
						value={draft.main_identifier}
						onChange={(e) => onUpdate({ main_identifier: e.target.value })}
						className="h-8 text-xs"
						placeholder="T.ex. SMHI Öppna Data"
					/>
				</div>
				<div className="space-y-1">
					<Label className="text-xs text-muted-foreground">Kärnaktivitet</Label>
					<Input
						value={draft.core_activity}
						onChange={(e) => onUpdate({ core_activity: e.target.value })}
						className="h-8 text-xs"
						placeholder="T.ex. Hämtar väderprognoser"
					/>
				</div>
				<div className="space-y-1">
					<Label className="text-xs text-muted-foreground">Unikt scope</Label>
					<Input
						value={draft.unique_scope}
						onChange={(e) => onUpdate({ unique_scope: e.target.value })}
						className="h-8 text-xs"
					/>
				</div>
				<div className="space-y-1">
					<Label className="text-xs text-muted-foreground">Geografiskt scope</Label>
					<Input
						value={draft.geographic_scope}
						onChange={(e) => onUpdate({ geographic_scope: e.target.value })}
						className="h-8 text-xs"
					/>
				</div>
			</div>

			{/* Keywords */}
			<div className="space-y-1">
				<Label className="text-xs text-muted-foreground">
					Nyckelord ({draft.keywords.length}/20)
				</Label>
				<div className="flex flex-wrap items-center gap-1.5">
					{draft.keywords.map((kw, kwIdx) => (
						<Badge
							key={`kw-${draft.tool_id}-${kwIdx}-${kw}`}
							variant="secondary"
							className="gap-0.5 text-xs py-0.5"
						>
							{kw}
							<button
								type="button"
								onClick={() => onUpdate({ keywords: draft.keywords.filter((_, idx) => idx !== kwIdx) })}
								className="ml-0.5 hover:text-destructive"
							>
								<X className="h-2.5 w-2.5" />
							</button>
						</Badge>
					))}
					<div className="inline-flex items-center gap-1">
						<Input
							placeholder="Nytt nyckelord..."
							value={newKeyword}
							maxLength={METADATA_MAX_KEYWORD_CHARS}
							onChange={(e) => setNewKeyword(e.target.value)}
							onKeyDown={(e) => {
								if (e.key === "Enter") {
									e.preventDefault();
									addKeyword();
								}
							}}
							className="h-7 w-32 text-xs"
						/>
						<Button onClick={addKeyword} size="sm" variant="ghost" className="h-7 w-7 p-0">
							<Plus className="h-3 w-3" />
						</Button>
					</div>
				</div>
			</div>

			{/* Example queries */}
			<div className="space-y-1">
				<div className="flex items-center gap-2">
					<Label className="text-xs text-muted-foreground">
						Exempelfrågor ({draft.example_queries.length}/10)
					</Label>
					<Button
						variant="ghost"
						size="sm"
						className="h-5 text-xs px-2"
						onClick={() => setShowExamples(!showExamples)}
					>
						{showExamples ? "Dölj" : "Visa/Redigera"}
					</Button>
				</div>
				{showExamples && (
					<div className="space-y-1.5 pl-1">
						{draft.example_queries.map((eq, eqIdx) => (
							<div key={`eq-${draft.tool_id}-${eqIdx}-${eq.slice(0, 30)}`} className="flex items-center gap-1">
								<span className="flex-1 text-xs bg-muted px-2 py-1 rounded truncate">{eq}</span>
								<Button
									onClick={() =>
										onUpdate({
											example_queries: draft.example_queries.filter((_, idx) => idx !== eqIdx),
										})
									}
									size="sm"
									variant="ghost"
									className="h-6 w-6 p-0"
								>
									<X className="h-3 w-3" />
								</Button>
							</div>
						))}
						<div className="flex gap-1">
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
								className="h-7 text-xs"
							/>
							<Button onClick={addExample} size="sm" variant="ghost" className="h-7 w-7 p-0">
								<Plus className="h-3 w-3" />
							</Button>
						</div>
					</div>
				)}
			</div>

			{/* Save/reset */}
			{hasChanges && (
				<div className="flex gap-2 pt-1">
					<Button onClick={onSave} size="sm" className="gap-1.5" disabled={isSaving}>
						{isSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
						Spara
					</Button>
					<Button
						onClick={onReset}
						variant="outline"
						size="sm"
						className="gap-1.5"
						disabled={isSaving}
					>
						<RotateCcw className="h-3 w-3" />
						Återställ
					</Button>
				</div>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Domain group
// ---------------------------------------------------------------------------

function DomainGroupCard({
	group,
	drafts,
	savingToolId,
	stabilityLockedIds,
	onToolUpdate,
	onToolSave,
	onToolReset,
	searchTerm,
	statusFilter,
}: {
	group: DomainGroup;
	drafts: Record<string, ToolMetadataUpdateItem>;
	savingToolId: string | null;
	stabilityLockedIds: Set<string>;
	onToolUpdate: (toolId: string, updates: Partial<ToolMetadataUpdateItem>) => void;
	onToolSave: (toolId: string) => void;
	onToolReset: (toolId: string) => void;
	searchTerm: string;
	statusFilter: StatusFilter;
}) {
	const [isOpen, setIsOpen] = useState(false);

	const filteredTools = useMemo(() => {
		return group.tools.filter((tool) => {
			const term = searchTerm.toLowerCase();
			if (term) {
				const draft = drafts[tool.tool_id];
				const matchesSearch =
					tool.tool_id.toLowerCase().includes(term) ||
					(draft?.name ?? tool.name).toLowerCase().includes(term) ||
					(draft?.description ?? tool.description).toLowerCase().includes(term);
				if (!matchesSearch) return false;
			}

			if (statusFilter === "live" && tool.lifecycle?.status !== "live") return false;
			if (statusFilter === "review" && tool.lifecycle?.status === "live") return false;

			return true;
		});
	}, [group.tools, drafts, searchTerm, statusFilter]);

	const changedCount = filteredTools.filter(
		(t) => drafts[t.tool_id] && isToolChanged(drafts[t.tool_id], t)
	).length;

	if (filteredTools.length === 0) return null;

	return (
		<Collapsible open={isOpen} onOpenChange={setIsOpen}>
			<CollapsibleTrigger asChild>
				<button
					type="button"
					className="w-full flex items-center gap-3 rounded-lg border p-3 hover:bg-muted/50 transition-colors text-left"
				>
					<ChevronRight
						className={`h-4 w-4 text-muted-foreground transition-transform ${isOpen ? "rotate-90" : ""}`}
					/>
					<span className="font-medium text-sm">{group.label}</span>
					<span className="text-xs text-muted-foreground">{filteredTools.length} verktyg</span>
					<div className="flex items-center gap-1.5 ml-auto">
						{group.avgSuccessRate != null && (
							<span className="text-xs tabular-nums text-muted-foreground">
								{formatPercent(group.avgSuccessRate)}
							</span>
						)}
						<Badge variant="outline" className="text-xs">
							{group.liveCount} live
						</Badge>
						{group.reviewCount > 0 && (
							<Badge variant="secondary" className="text-xs">
								{group.reviewCount} review
							</Badge>
						)}
						{changedCount > 0 && (
							<Badge variant="default" className="text-xs bg-amber-500">
								{changedCount} ändrad{changedCount > 1 ? "e" : ""}
							</Badge>
						)}
					</div>
				</button>
			</CollapsibleTrigger>
			<CollapsibleContent>
				<div className="space-y-1 pl-7 pr-1 pb-2">
					{filteredTools.map((tool) => {
						const draft = drafts[tool.tool_id] ?? toUpdateItem(tool);
						const hasChanges = drafts[tool.tool_id]
							? isToolChanged(drafts[tool.tool_id], tool)
							: false;
						const isLocked = stabilityLockedIds.has(tool.tool_id);

						return (
							<Collapsible key={tool.tool_id}>
								<CollapsibleTrigger asChild>
									<button
										type="button"
										className="w-full flex items-center gap-2 rounded border px-3 py-2 hover:bg-muted/30 transition-colors text-left text-sm"
									>
										<span className="font-mono text-xs flex-1 truncate">{tool.tool_id}</span>
										{tool.lifecycle && (
											<LifecycleBadge
												status={tool.lifecycle.status === "live" ? "live" : "review"}
												successRate={tool.lifecycle.success_rate}
												requiredSuccessRate={tool.lifecycle.required_success_rate}
												compact
											/>
										)}
										{isLocked && <Lock className="h-3 w-3 text-muted-foreground" />}
										{hasChanges && (
											<Badge variant="outline" className="text-[10px] h-4 px-1">
												ändrad
											</Badge>
										)}
									</button>
								</CollapsibleTrigger>
								<CollapsibleContent>
									<div className="ml-3 border-l-2 border-muted pl-3">
										<ToolEditor
											draft={draft}
											hasChanges={hasChanges}
											isSaving={savingToolId === tool.tool_id}
											onUpdate={(updates) => onToolUpdate(tool.tool_id, updates)}
											onSave={() => onToolSave(tool.tool_id)}
											onReset={() => onToolReset(tool.tool_id)}
										/>
									</div>
								</CollapsibleContent>
							</Collapsible>
						);
					})}
				</div>
			</CollapsibleContent>
		</Collapsible>
	);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ToolCatalogPanel() {
	const queryClient = useQueryClient();
	const { domainGroups, allTools, catalogData, searchSpaceId, isLoading, error, refetch } =
		useToolCatalog();

	const [searchTerm, setSearchTerm] = useState("");
	const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
	const [drafts, setDrafts] = useState<Record<string, ToolMetadataUpdateItem>>({});
	const [savingToolId, setSavingToolId] = useState<string | null>(null);
	const [isSavingAll, setIsSavingAll] = useState(false);

	// Initialize drafts from loaded data
	useEffect(() => {
		const nextDrafts: Record<string, ToolMetadataUpdateItem> = {};
		for (const tool of allTools) {
			nextDrafts[tool.tool_id] = toUpdateItem(tool);
		}
		setDrafts(nextDrafts);
	}, [allTools]);

	const stabilityLockedIds = useMemo(() => {
		const ids = new Set<string>();
		for (const item of catalogData?.stability_locks?.locked_items ?? []) {
			ids.add(item.item_id);
		}
		return ids;
	}, [catalogData?.stability_locks?.locked_items]);

	const originalByToolId = useMemo(() => {
		const map: Record<string, ToolMetadataItem> = {};
		for (const tool of allTools) {
			map[tool.tool_id] = tool;
		}
		return map;
	}, [allTools]);

	const changedToolIds = useMemo(() => {
		return Object.keys(drafts).filter((toolId) => {
			const original = originalByToolId[toolId];
			if (!original) return false;
			return isToolChanged(drafts[toolId], original);
		});
	}, [drafts, originalByToolId]);

	const onToolUpdate = useCallback((toolId: string, updates: Partial<ToolMetadataUpdateItem>) => {
		setDrafts((prev) => ({
			...prev,
			[toolId]: { ...prev[toolId], ...updates },
		}));
	}, []);

	const saveTools = useCallback(
		async (toolIds: string[]) => {
			if (!searchSpaceId) return;
			const tools = toolIds.map((id) => drafts[id]).filter(Boolean);
			if (!tools.length) return;
			await adminToolSettingsApiService.updateToolSettings({ tools }, searchSpaceId);
			await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			await refetch();
		},
		[searchSpaceId, drafts, queryClient, refetch]
	);

	const onToolSave = useCallback(
		async (toolId: string) => {
			setSavingToolId(toolId);
			try {
				await saveTools([toolId]);
				toast.success(`Sparade metadata för ${toolId}`);
			} catch {
				toast.error("Kunde inte spara verktygsmetadata");
			} finally {
				setSavingToolId(null);
			}
		},
		[saveTools]
	);

	const onToolReset = useCallback(
		(toolId: string) => {
			const original = originalByToolId[toolId];
			if (!original) return;
			setDrafts((prev) => ({ ...prev, [toolId]: toUpdateItem(original) }));
		},
		[originalByToolId]
	);

	const saveAllChanges = useCallback(async () => {
		if (!changedToolIds.length) return;
		setIsSavingAll(true);
		try {
			await saveTools(changedToolIds);
			toast.success(`Sparade ${changedToolIds.length} metadataändringar`);
		} catch {
			toast.error("Kunde inte spara alla metadataändringar");
		} finally {
			setIsSavingAll(false);
		}
	}, [changedToolIds, saveTools]);

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
					<p className="text-destructive">Kunde inte ladda verktyg: {String(error)}</p>
				</CardContent>
			</Card>
		);
	}

	return (
		<div className="space-y-4">
			{/* Search & filter bar */}
			<div className="flex flex-wrap items-center gap-3">
				<div className="flex items-center gap-2 flex-1 min-w-[200px]">
					<Search className="h-4 w-4 text-muted-foreground shrink-0" />
					<Input
						placeholder="Sök verktyg..."
						value={searchTerm}
						onChange={(e) => setSearchTerm(e.target.value)}
						className="h-9"
					/>
				</div>
				<select
					value={statusFilter}
					onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
					className="h-9 rounded-md border bg-background px-3 text-sm"
				>
					<option value="all">Alla</option>
					<option value="live">Live</option>
					<option value="review">Review</option>
				</select>
				<span className="text-sm text-muted-foreground">
					{allTools.length} verktyg i {domainGroups.length} domäner
				</span>
			</div>

			{/* Domain groups */}
			<div className="space-y-2">
				{domainGroups.map((group) => (
					<DomainGroupCard
						key={group.domain}
						group={group}
						drafts={drafts}
						savingToolId={savingToolId}
						stabilityLockedIds={stabilityLockedIds}
						onToolUpdate={onToolUpdate}
						onToolSave={onToolSave}
						onToolReset={onToolReset}
						searchTerm={searchTerm}
						statusFilter={statusFilter}
					/>
				))}
			</div>

			{/* Save all bar */}
			{changedToolIds.length > 0 && (
				<div className="sticky bottom-4 flex justify-center">
					<Button onClick={saveAllChanges} disabled={isSavingAll} className="gap-2 shadow-lg">
						{isSavingAll ? (
							<Loader2 className="h-4 w-4 animate-spin" />
						) : (
							<Save className="h-4 w-4" />
						)}
						{isSavingAll ? "Sparar..." : `Spara alla ändringar (${changedToolIds.length})`}
					</Button>
				</div>
			)}
		</div>
	);
}
