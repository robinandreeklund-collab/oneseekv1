"use client";

/**
 * Panel 5 — Deploy & Ops
 *
 * Consolidates:
 * - Key metrics (agent/tool/api-input accuracy rates + deltas)
 * - 30-day trend bars
 * - Lifecycle management table with promote / rollback / bulk promote
 * - Routing phase indicator
 * - Audit trail history
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAtomValue } from "jotai";
import {
	Activity,
	CheckCircle2,
	Loader2,
	Rocket,
	RotateCcw,
	Search,
	ShieldAlert,
	TrendingDown,
	TrendingUp,
} from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import { AuditTrail, type AuditTrailEntry } from "@/components/admin/shared/audit-trail";
import { LifecycleBadge } from "@/components/admin/shared/lifecycle-badge";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { ToolLifecycleStatusResponse } from "@/contracts/types/admin-tool-lifecycle.types";
import type { ToolEvaluationStageHistoryResponse } from "@/contracts/types/admin-tool-settings.types";
import { adminToolLifecycleApiService } from "@/lib/apis/admin-tool-lifecycle-api.service";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";
import { formatPercent, formatSignedPercent } from "@/components/admin/tools/hooks/use-tool-catalog";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Compact metric card with rate, delta, and optional trend icon. */
function MetricCard({
	label,
	rate,
	delta,
}: {
	label: string;
	rate: number | null;
	delta: number | null;
}) {
	const DeltaIcon = delta != null && delta >= 0 ? TrendingUp : TrendingDown;
	return (
		<div className="rounded-lg border p-3 space-y-1">
			<p className="text-xs text-muted-foreground">{label}</p>
			<p className="text-xl font-bold tabular-nums">{formatPercent(rate)}</p>
			{delta !== null && (
				<p
					className={`text-xs flex items-center gap-0.5 ${delta >= 0 ? "text-emerald-600" : "text-red-500"}`}
				>
					<DeltaIcon className="h-3 w-3" />
					{formatSignedPercent(delta)}
				</p>
			)}
		</div>
	);
}

/** Trend bars — mini bar chart for eval history. */
function TrendBars({
	points,
	label,
}: {
	points: Array<{ run_at: string; eval_name?: string | null; success_rate: number }>;
	label: string;
}) {
	if (points.length === 0) {
		return <p className="text-xs text-muted-foreground">Ingen historik.</p>;
	}
	return (
		<div className="space-y-1">
			<p className="text-xs text-muted-foreground">{label}</p>
			<div className="flex items-end gap-0.5 h-16 rounded border bg-muted/30 p-1.5">
				{points.map((point) => {
					const normalized = Math.max(0.04, Math.min(1, point.success_rate));
					const title = `${point.eval_name || "Eval"} \u2022 ${
						point.run_at ? new Date(point.run_at).toLocaleString("sv-SE") : "ok\u00e4nd tid"
					} \u2022 ${formatPercent(point.success_rate)}`;
					return (
						<div
							key={`${label}-${point.run_at}-${point.eval_name ?? ""}`}
							className="flex-1 min-w-[4px] rounded-sm bg-primary/80 hover:bg-primary transition-colors"
							style={{ height: `${Math.round(normalized * 100)}%` }}
							title={title}
						/>
					);
				})}
			</div>
		</div>
	);
}

/** Stage history detail (tabbed) */
function StageHistorySection({
	history,
	selectedCategory,
	onSelectCategory,
}: {
	history: ToolEvaluationStageHistoryResponse | undefined;
	selectedCategory: string;
	onSelectCategory: (value: string) => void;
}) {
	const latest =
		history?.items && history.items.length > 0
			? history.items[history.items.length - 1]
			: undefined;
	const categoryOptions = history?.category_series?.map((series) => series.category_id) ?? [];
	const effectiveCategory =
		categoryOptions.includes(selectedCategory) && selectedCategory
			? selectedCategory
			: (categoryOptions[0] ?? "");
	const selectedSeries = history?.category_series?.find(
		(series) => series.category_id === effectiveCategory
	);

	// Sync parent state when the effective category differs (e.g. first render)
	// Using a layout-safe callback avoids the fragile useEffect + setState pattern.
	const prevEffective = useRef(effectiveCategory);
	if (prevEffective.current !== effectiveCategory) {
		prevEffective.current = effectiveCategory;
		if (effectiveCategory && effectiveCategory !== selectedCategory) {
			// Defer to avoid setState-during-render warning
			queueMicrotask(() => onSelectCategory(effectiveCategory));
		}
	}

	return (
		<div className="space-y-3">
			<div className="flex items-center gap-4 text-sm">
				<span className="text-muted-foreground">
					Senaste: {latest?.run_at ? new Date(latest.run_at).toLocaleString("sv-SE") : "-"}
				</span>
				<span className="text-muted-foreground">Rate: {formatPercent(latest?.success_rate)}</span>
				<span className="text-muted-foreground">K\u00f6rningar: {history?.items?.length ?? 0}</span>
			</div>

			{categoryOptions.length > 0 && (
				<div className="flex items-center gap-2">
					<label
						htmlFor={`${history?.stage ?? "stage"}-deploy-cat`}
						className="text-xs text-muted-foreground"
					>
						Kategori
					</label>
					<select
						id={`${history?.stage ?? "stage"}-deploy-cat`}
						className="h-8 rounded-md border bg-background px-2 text-xs"
						value={effectiveCategory}
						onChange={(event) => onSelectCategory(event.target.value)}
					>
						{categoryOptions.map((categoryId) => (
							<option key={categoryId} value={categoryId}>
								{categoryId}
							</option>
						))}
					</select>
				</div>
			)}

			{selectedSeries && (
				<TrendBars
					points={selectedSeries.points ?? []}
					label={effectiveCategory ? `Kategori: ${effectiveCategory}` : "Kategori-trend"}
				/>
			)}

			{(history?.items ?? []).length > 0 && (
				<div className="max-h-40 overflow-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead className="text-xs py-1">Tid</TableHead>
								<TableHead className="text-xs py-1">Eval</TableHead>
								<TableHead className="text-xs py-1">Rate</TableHead>
								<TableHead className="text-xs py-1">Tester</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{[...(history?.items ?? [])]
								.reverse()
								.slice(0, 20)
								.map((item) => (
									<TableRow key={`${item.run_at}-${item.eval_name ?? ""}-${item.stage}`}>
										<TableCell className="text-xs py-1">
											{new Date(item.run_at).toLocaleString("sv-SE")}
										</TableCell>
										<TableCell className="text-xs py-1 font-mono">
											{item.eval_name || "-"}
										</TableCell>
										<TableCell className="text-xs py-1 tabular-nums">
											{formatPercent(item.success_rate)}
										</TableCell>
										<TableCell className="text-xs py-1 tabular-nums">
											{item.passed_tests}/{item.total_tests}
										</TableCell>
									</TableRow>
								))}
						</TableBody>
					</Table>
				</div>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function DeployPanel() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const queryClient = useQueryClient();

	// State
	const [searchQuery, setSearchQuery] = useState("");
	const [statusFilter, setStatusFilter] = useState<"all" | "live" | "review" | "ready">("all");
	const [rollbackTool, setRollbackTool] = useState<ToolLifecycleStatusResponse | null>(null);
	const [rollbackNotes, setRollbackNotes] = useState("");
	const [actionLoading, setActionLoading] = useState<string | null>(null);
	const [bulkPromoteOpen, setBulkPromoteOpen] = useState(false);
	const [statsTab, setStatsTab] = useState("agent");
	const [agentHistoryCategory, setAgentHistoryCategory] = useState("");
	const [toolHistoryCategory, setToolHistoryCategory] = useState("");
	const [apiInputHistoryCategory, setApiInputHistoryCategory] = useState("");

	// Queries
	const { data: toolSettings } = useQuery({
		queryKey: ["admin-tool-settings"],
		queryFn: () => adminToolSettingsApiService.getToolSettings(),
		enabled: !!currentUser,
		staleTime: 30_000,
	});

	const searchSpaceId = toolSettings?.search_space_id;

	const {
		data: lifecycleData,
		isLoading: lifecycleLoading,
		refetch: refetchLifecycle,
	} = useQuery({
		queryKey: ["admin-tool-lifecycle"],
		queryFn: () => adminToolLifecycleApiService.getToolLifecycleList(),
		enabled: !!currentUser,
		staleTime: 30_000,
	});

	const { data: agentEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "agent"],
		queryFn: () => adminToolSettingsApiService.getToolEvaluationHistory("agent", searchSpaceId),
		enabled: !!currentUser && typeof searchSpaceId === "number",
		staleTime: 30_000,
	});

	const { data: toolEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "tool"],
		queryFn: () => adminToolSettingsApiService.getToolEvaluationHistory("tool", searchSpaceId),
		enabled: !!currentUser && typeof searchSpaceId === "number",
		staleTime: 30_000,
	});

	const { data: apiInputEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "api_input"],
		queryFn: () => adminToolSettingsApiService.getToolEvaluationHistory("api_input", searchSpaceId),
		enabled: !!currentUser && typeof searchSpaceId === "number",
		staleTime: 30_000,
	});

	// Derived: latest/prev rates and deltas
	const rateInfo = useMemo(() => {
		function extractRateDelta(history: ToolEvaluationStageHistoryResponse | undefined) {
			const items = history?.items ?? [];
			const latest = items.length > 0 ? items[items.length - 1].success_rate : null;
			const prev = items.length > 1 ? items[items.length - 2].success_rate : null;
			const delta = latest != null && prev != null ? latest - prev : null;
			return { rate: latest, delta };
		}
		return {
			agent: extractRateDelta(agentEvalHistory),
			tool: extractRateDelta(toolEvalHistory),
			apiInput: extractRateDelta(apiInputEvalHistory),
		};
	}, [agentEvalHistory, toolEvalHistory, apiInputEvalHistory]);

	const latestEvalDate = toolSettings?.latest_evaluation?.run_at
		? new Date(toolSettings.latest_evaluation.run_at).toLocaleString("sv-SE")
		: null;

	// Lifecycle helpers
	const refreshLifecycle = useCallback(async () => {
		await refetchLifecycle();
		queryClient.invalidateQueries({ queryKey: ["admin-tool-lifecycle"] });
	}, [refetchLifecycle, queryClient]);

	const canToggle = (tool: ToolLifecycleStatusResponse): boolean => {
		if (tool.status === "live") return true;
		if (tool.success_rate === null) return false;
		return tool.success_rate >= tool.required_success_rate;
	};

	const toggleToolStatus = async (tool: ToolLifecycleStatusResponse) => {
		if (!canToggle(tool)) {
			toast.error(
				`Verktyget n\u00e5r inte kraven (${tool.success_rate !== null ? `${(tool.success_rate * 100).toFixed(1)}%` : "N/A"} < ${(tool.required_success_rate * 100).toFixed(0)}%)`
			);
			return;
		}

		const newStatus = tool.status === "live" ? "review" : "live";
		try {
			setActionLoading(tool.tool_id);
			await adminToolLifecycleApiService.updateToolStatus(tool.tool_id, {
				status: newStatus,
				notes: `Status \u00e4ndrad till ${newStatus}`,
			});
			toast.success(`${tool.tool_id} satt till ${newStatus}`);
			await refreshLifecycle();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Kunde inte uppdatera status");
		} finally {
			setActionLoading(null);
		}
	};

	const performRollback = async () => {
		if (!rollbackTool || !rollbackNotes.trim()) {
			toast.error("Ange en anledning f\u00f6r rollback");
			return;
		}

		try {
			setActionLoading(rollbackTool.tool_id);
			await adminToolLifecycleApiService.rollbackTool(rollbackTool.tool_id, {
				notes: rollbackNotes,
			});
			toast.success(`Rollback genomf\u00f6rd: ${rollbackTool.tool_id}`);
			setRollbackTool(null);
			setRollbackNotes("");
			await refreshLifecycle();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Rollback misslyckades");
		} finally {
			setActionLoading(null);
		}
	};

	const bulkPromoteToLive = async () => {
		try {
			setActionLoading("__bulk__");
			const result = await adminToolLifecycleApiService.bulkPromoteToLive();
			toast.success(
				(result as { message?: string })?.message || "Alla verktyg befordrade till LIVE"
			);
			await refreshLifecycle();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Bulk-befordran misslyckades");
		} finally {
			setActionLoading(null);
			setBulkPromoteOpen(false);
		}
	};

	// Filter lifecycle tools
	const filteredTools = useMemo(() => {
		let tools = lifecycleData?.tools ?? [];

		if (searchQuery) {
			const q = searchQuery.toLowerCase();
			tools = tools.filter((t) => t.tool_id.toLowerCase().includes(q));
		}

		switch (statusFilter) {
			case "live":
				tools = tools.filter((t) => t.status === "live");
				break;
			case "review":
				tools = tools.filter((t) => t.status !== "live");
				break;
			case "ready":
				tools = tools.filter(
					(t) =>
						t.status !== "live" &&
						t.success_rate !== null &&
						t.success_rate >= t.required_success_rate
				);
				break;
		}

		return tools;
	}, [lifecycleData?.tools, searchQuery, statusFilter]);

	const getActionType = (tool: ToolLifecycleStatusResponse): "rollback" | "promote" | "blocked" => {
		if (tool.status === "live") return "rollback";
		if (tool.success_rate !== null && tool.success_rate >= tool.required_success_rate)
			return "promote";
		return "blocked";
	};

	// Derive audit entries from lifecycle data — each tool's most recent change
	const auditEntries = useMemo<AuditTrailEntry[]>(() => {
		if (!lifecycleData?.tools) return [];
		return lifecycleData.tools
			.filter((tool) => tool.changed_at)
			.map((tool, idx) => ({
				id: idx + 1,
				tool_id: tool.tool_id,
				old_status: null,
				new_status: tool.status,
				success_rate: tool.success_rate ?? null,
				trigger: "manual",
				reason: tool.notes ?? null,
				changed_by_email: tool.changed_by_id ?? null,
				created_at: tool.changed_at,
			}))
			.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
			.slice(0, 50);
	}, [lifecycleData?.tools]);

	// ---- Render ----

	return (
		<div className="space-y-4">
			{/* ---- 1. Key Metrics ---- */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base flex items-center gap-2">
						<Activity className="h-4 w-4" />
						Nyckeltal
					</CardTitle>
					<CardDescription>Senaste eval-resultat per steg i pipelinen.</CardDescription>
				</CardHeader>
				<CardContent className="space-y-3">
					<div className="grid gap-3 grid-cols-2 md:grid-cols-4">
						<MetricCard label="Agentval" rate={rateInfo.agent.rate} delta={rateInfo.agent.delta} />
						<MetricCard label="Toolval" rate={rateInfo.tool.rate} delta={rateInfo.tool.delta} />
						<MetricCard
							label="API Input"
							rate={rateInfo.apiInput.rate}
							delta={rateInfo.apiInput.delta}
						/>
						<div className="rounded-lg border p-3 space-y-1">
							<p className="text-xs text-muted-foreground">Lifecycle</p>
							<p className="text-xl font-bold tabular-nums">
								{lifecycleData ? `${lifecycleData.live_count}/${lifecycleData.total_count}` : "-"}
							</p>
							{lifecycleData && lifecycleData.review_count > 0 && (
								<p className="text-xs text-muted-foreground">
									{lifecycleData.review_count} under review
								</p>
							)}
							{lifecycleLoading && (
								<Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
							)}
						</div>
					</div>

					<div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground border-t pt-2">
						<span>
							Live:{" "}
							<span className="font-medium text-foreground">
								{lifecycleData?.live_count ?? "-"}
							</span>
						</span>
						<span>
							Review:{" "}
							<span className="font-medium text-foreground">
								{lifecycleData?.review_count ?? "-"}
							</span>
						</span>
						<span>
							Total:{" "}
							<span className="font-medium text-foreground">
								{lifecycleData?.total_count ?? "-"}
							</span>
						</span>
						<span>
							Senaste eval:{" "}
							<span className="font-medium text-foreground">{latestEvalDate ?? "-"}</span>
						</span>
					</div>
				</CardContent>
			</Card>

			{/* ---- 2. Trend Bars ---- */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base">Trenddiagram (30 dagar)</CardTitle>
				</CardHeader>
				<CardContent>
					<div className="grid gap-3 grid-cols-1 md:grid-cols-3">
						<TrendBars points={agentEvalHistory?.items ?? []} label="Agentval" />
						<TrendBars points={toolEvalHistory?.items ?? []} label="Toolval" />
						<TrendBars points={apiInputEvalHistory?.items ?? []} label="API Input" />
					</div>
				</CardContent>
			</Card>

			{/* ---- 3. Lifecycle Management ---- */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base flex items-center gap-2">
						<Rocket className="h-4 w-4" />
						Lifecycle-status
					</CardTitle>
					<CardDescription>
						Hantera verktygens status. Promota till live n\u00e4r kraven \u00e4r uppfyllda, eller
						utf\u00f6r rollback vid problem.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-3">
					{/* Filters & actions */}
					<div className="flex items-center gap-3 flex-wrap">
						<div className="flex items-center gap-2 flex-1 min-w-[200px]">
							<Search className="h-4 w-4 text-muted-foreground shrink-0" />
							<Input
								placeholder="S\u00f6k verktyg..."
								value={searchQuery}
								onChange={(e) => setSearchQuery(e.target.value)}
								className="h-8 text-sm"
							/>
						</div>
						<select
							className="h-8 rounded-md border bg-background px-2 text-xs"
							value={statusFilter}
							onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
						>
							<option value="all">Alla</option>
							<option value="live">Live</option>
							<option value="review">Review</option>
							<option value="ready">Redo att promota</option>
						</select>
						<Button
							variant="ghost"
							size="sm"
							className="h-8 gap-1 text-xs"
							onClick={() => refreshLifecycle()}
						>
							<RotateCcw className="h-3.5 w-3.5" />
							Uppdatera
						</Button>
						{lifecycleData && lifecycleData.review_count > 0 && (
							<Button
								onClick={() => setBulkPromoteOpen(true)}
								variant="outline"
								size="sm"
								className="gap-1 text-xs h-8"
								disabled={actionLoading !== null}
							>
								Promota alla redo
							</Button>
						)}
					</div>

					{/* Table */}
					{lifecycleLoading ? (
						<div className="flex items-center justify-center h-24">
							<Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
						</div>
					) : (
						<div className="max-h-[420px] overflow-auto">
							<Table>
								<TableHeader>
									<TableRow>
										<TableHead className="text-xs">Verktyg</TableHead>
										<TableHead className="text-xs">Status</TableHead>
										<TableHead className="text-xs">Rate</TableHead>
										<TableHead className="text-xs">Tr\u00f6skel</TableHead>
										<TableHead className="text-xs">Senast \u00e4ndrad</TableHead>
										<TableHead className="text-xs text-right">\u00c5tg\u00e4rd</TableHead>
									</TableRow>
								</TableHeader>
								<TableBody>
									{filteredTools.length === 0 ? (
										<TableRow>
											<TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
												{searchQuery ? "Inga verktyg hittades" : "Inga verktyg tillg\u00e4ngliga"}
											</TableCell>
										</TableRow>
									) : (
										filteredTools.map((tool) => {
											const action = getActionType(tool);
											return (
												<TableRow key={tool.tool_id}>
													<TableCell className="font-mono text-xs py-2">{tool.tool_id}</TableCell>
													<TableCell className="py-2">
														<LifecycleBadge
															status={tool.status === "live" ? "live" : "review"}
															successRate={tool.success_rate}
															requiredSuccessRate={tool.required_success_rate}
															compact
														/>
													</TableCell>
													<TableCell className="text-xs py-2 tabular-nums">
														{tool.success_rate !== null ? (
															<span
																className={
																	tool.success_rate >= tool.required_success_rate
																		? "text-emerald-600"
																		: "text-amber-600"
																}
															>
																{(tool.success_rate * 100).toFixed(1)}%
															</span>
														) : (
															<span className="text-muted-foreground">N/A</span>
														)}
													</TableCell>
													<TableCell className="text-xs py-2 tabular-nums">
														{(tool.required_success_rate * 100).toFixed(0)}%
													</TableCell>
													<TableCell className="text-xs py-2 text-muted-foreground">
														{new Date(tool.changed_at).toLocaleDateString("sv-SE")}
													</TableCell>
													<TableCell className="text-right py-2">
														<div className="flex items-center justify-end gap-1">
															{action === "rollback" && (
																<TooltipProvider>
																	<Tooltip>
																		<TooltipTrigger asChild>
																			<Button
																				variant="ghost"
																				size="sm"
																				className="h-7 w-7 p-0"
																				disabled={actionLoading === tool.tool_id}
																				onClick={() => setRollbackTool(tool)}
																			>
																				<ShieldAlert className="h-3.5 w-3.5 text-red-600" />
																			</Button>
																		</TooltipTrigger>
																		<TooltipContent>
																			<p>Emergency rollback</p>
																		</TooltipContent>
																	</Tooltip>
																</TooltipProvider>
															)}
															{action === "promote" && (
																<TooltipProvider>
																	<Tooltip>
																		<TooltipTrigger asChild>
																			<Button
																				variant="ghost"
																				size="sm"
																				className="h-7 w-7 p-0"
																				disabled={actionLoading === tool.tool_id}
																				onClick={() => toggleToolStatus(tool)}
																			>
																				{actionLoading === tool.tool_id ? (
																					<Loader2 className="h-3.5 w-3.5 animate-spin" />
																				) : (
																					<CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
																				)}
																			</Button>
																		</TooltipTrigger>
																		<TooltipContent>
																			<p>Befordra till live</p>
																		</TooltipContent>
																	</Tooltip>
																</TooltipProvider>
															)}
															{action === "blocked" && (
																<TooltipProvider>
																	<Tooltip>
																		<TooltipTrigger asChild>
																			<span className="text-xs text-muted-foreground px-1 cursor-default">
																				&mdash;
																			</span>
																		</TooltipTrigger>
																		<TooltipContent>
																			<p>
																				{tool.success_rate === null
																					? "Ingen eval-data"
																					: `Under tr\u00f6skel: ${(tool.success_rate * 100).toFixed(1)}% < ${(tool.required_success_rate * 100).toFixed(0)}%`}
																			</p>
																		</TooltipContent>
																	</Tooltip>
																</TooltipProvider>
															)}
														</div>
													</TableCell>
												</TableRow>
											);
										})
									)}
								</TableBody>
							</Table>
						</div>
					)}

					{/* Legend */}
					<div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground border-t pt-2">
						<span>
							<CheckCircle2 className="inline h-3 w-3 text-emerald-600" /> = Redo att promota
						</span>
						<span>
							<ShieldAlert className="inline h-3 w-3 text-red-600" /> = Emergency rollback
						</span>
						<span>&mdash; = Under tr\u00f6skel / saknar eval</span>
					</div>
				</CardContent>
			</Card>

			{/* ---- 4. Eval History (tabbed detail) ---- */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base">Eval-historik</CardTitle>
					<CardDescription>
						Detaljerad historik per pipeline-steg med kategori-filter.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Tabs value={statsTab} onValueChange={setStatsTab}>
						<TabsList className="h-8">
							<TabsTrigger value="agent" className="text-xs">
								Agentval
							</TabsTrigger>
							<TabsTrigger value="tool" className="text-xs">
								Toolval
							</TabsTrigger>
							<TabsTrigger value="api_input" className="text-xs">
								API Input
							</TabsTrigger>
						</TabsList>

						<TabsContent value="agent" className="mt-3">
							<StageHistorySection
								history={agentEvalHistory}
								selectedCategory={agentHistoryCategory}
								onSelectCategory={setAgentHistoryCategory}
							/>
						</TabsContent>

						<TabsContent value="tool" className="mt-3">
							<StageHistorySection
								history={toolEvalHistory}
								selectedCategory={toolHistoryCategory}
								onSelectCategory={setToolHistoryCategory}
							/>
						</TabsContent>

						<TabsContent value="api_input" className="mt-3">
							<StageHistorySection
								history={apiInputEvalHistory}
								selectedCategory={apiInputHistoryCategory}
								onSelectCategory={setApiInputHistoryCategory}
							/>
						</TabsContent>
					</Tabs>
				</CardContent>
			</Card>

			{/* ---- 5. Audit Trail ---- */}
			<AuditTrail entries={auditEntries} />

			{/* ---- Emergency Rollback Dialog ---- */}
			<AlertDialog
				open={rollbackTool !== null}
				onOpenChange={(open) => !open && setRollbackTool(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Emergency Rollback</AlertDialogTitle>
						<AlertDialogDescription>
							S\u00e4tt tillbaka{" "}
							<span className="font-mono font-semibold">{rollbackTool?.tool_id}</span> till
							review-status. Detta tar omedelbart bort verktyget fr\u00e5n produktion.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<div className="py-4">
						<label htmlFor="rollback-reason" className="text-sm font-medium mb-2 block">
							Anledning (kr\u00e4vs):
						</label>
						<Input
							id="rollback-reason"
							placeholder="T.ex. Verktyg orsakar fel i produktion"
							value={rollbackNotes}
							onChange={(e) => setRollbackNotes(e.target.value)}
						/>
					</div>
					<AlertDialogFooter>
						<AlertDialogCancel
							onClick={() => {
								setRollbackTool(null);
								setRollbackNotes("");
							}}
						>
							Avbryt
						</AlertDialogCancel>
						<AlertDialogAction
							onClick={performRollback}
							disabled={!rollbackNotes.trim() || actionLoading !== null}
							className="bg-red-600 hover:bg-red-700"
						>
							{actionLoading ? (
								<>
									<Loader2 className="h-4 w-4 animate-spin mr-2" />
									Rollback...
								</>
							) : (
								"Bekr\u00e4fta Rollback"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* ---- Bulk Promote Dialog ---- */}
			<AlertDialog open={bulkPromoteOpen} onOpenChange={setBulkPromoteOpen}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Bulk-befordran till LIVE</AlertDialogTitle>
						<AlertDialogDescription>
							Befordra ALLA {lifecycleData?.review_count ?? 0} review-verktyg till
							LIVE? Detta kringg\u00e5r tr\u00f6skelv\u00e4rden och \u00e4r avsett f\u00f6r initial
							migrering.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Avbryt</AlertDialogCancel>
						<AlertDialogAction
							onClick={bulkPromoteToLive}
							disabled={actionLoading !== null}
						>
							{actionLoading === "__bulk__" ? (
								<>
									<Loader2 className="h-4 w-4 animate-spin mr-2" />
									Befordrar...
								</>
							) : (
								"Bekr\u00e4fta"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
