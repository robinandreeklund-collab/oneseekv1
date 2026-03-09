"use client";

/** Överblick tab — Nyckeltal, Trenddiagram, Lifecycle, Eval-historik, Audit Trail */

import { useQuery } from "@tanstack/react-query";
import { useAtomValue } from "jotai";
import { CheckCircle2, Loader2, Search, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import type {
	ToolLifecycleListResponse,
	ToolLifecycleStatusResponse as ToolLifecycleStatus,
} from "@/contracts/types/admin-tool-lifecycle.types";
import type { ToolEvaluationStageHistoryResponse } from "@/contracts/types/admin-tool-settings.types";
import { adminToolLifecycleApiService } from "@/lib/apis/admin-tool-lifecycle-api.service";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";

// Helpers

function formatPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	return `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	const sign = value > 0 ? "+" : "";
	return `${sign}${(value * 100).toFixed(1)}%`;
}

// Trend bars sub-component

function HistoryTrendBars({
	points,
	valueKey,
	label,
}: {
	points: Array<Record<string, unknown>>;
	valueKey: string;
	label: string;
}) {
	if (points.length === 0) {
		return <p className="text-xs text-muted-foreground">Ingen historik.</p>;
	}
	return (
		<div className="space-y-1">
			<p className="text-xs text-muted-foreground">{label}</p>
			<div className="flex items-end gap-0.5 h-16 rounded border bg-muted/30 p-1.5">
				{points.map((point, index) => {
					const raw = point[valueKey];
					const numeric = typeof raw === "number" ? raw : 0;
					const normalized = Math.max(0.04, Math.min(1, numeric));
					const runAt = String(point.run_at ?? "");
					const evalName = String(point.eval_name ?? "");
					const title = `${evalName || "Eval"} • ${
						runAt ? new Date(runAt).toLocaleString("sv-SE") : "okand tid"
					} • ${formatPercent(numeric)}`;
					return (
						<div
							key={`${valueKey}-${index}-${runAt}`}
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

// Stage history section (compact)

function StageHistorySection({
	title,
	description,
	history,
	selectedCategory,
	onSelectCategory,
}: {
	title: string;
	description: string;
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

	useEffect(() => {
		if (effectiveCategory && effectiveCategory !== selectedCategory) {
			onSelectCategory(effectiveCategory);
		}
	}, [effectiveCategory, selectedCategory, onSelectCategory]);

	return (
		<div className="space-y-3">
			<div className="flex items-center gap-4 text-sm">
				<span className="text-muted-foreground">
					Senaste: {latest?.run_at ? new Date(latest.run_at).toLocaleString("sv-SE") : "-"}
				</span>
				<span className="text-muted-foreground">Rate: {formatPercent(latest?.success_rate)}</span>
				<span className="text-muted-foreground">Korningar: {history?.items?.length ?? 0}</span>
			</div>

			{categoryOptions.length > 0 && (
				<div className="flex items-center gap-2">
					<Label htmlFor={`${history?.stage ?? "stage"}-overview-cat`} className="text-xs">
						Kategori
					</Label>
					<select
						id={`${history?.stage ?? "stage"}-overview-cat`}
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
				<HistoryTrendBars
					points={selectedSeries.points ?? []}
					valueKey="success_rate"
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
								.map((item, index) => (
									<TableRow key={`${item.run_at}-${index}`}>
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

// Main component

export function OverviewTab() {
	const { data: currentUser } = useAtomValue(currentUserAtom);

	// Lifecycle state
	const [lifecycleData, setLifecycleData] = useState<ToolLifecycleListResponse | null>(null);
	const [lifecycleLoading, setLifecycleLoading] = useState(true);
	const [searchQuery, setSearchQuery] = useState("");
	const [statusFilter, setStatusFilter] = useState<"all" | "live" | "review" | "ready">("all");
	const [rollbackTool, setRollbackTool] = useState<ToolLifecycleStatus | null>(null);
	const [rollbackNotes, setRollbackNotes] = useState("");
	const [actionLoading, setActionLoading] = useState<string | null>(null);

	const [agentHistoryCategory, setAgentHistoryCategory] = useState("");
	const [toolHistoryCategory, setToolHistoryCategory] = useState("");
	const [apiInputHistoryCategory, setApiInputHistoryCategory] = useState("");
	const [statsTab, setStatsTab] = useState("agent");
	const [auditEntries] = useState<AuditTrailEntry[]>([]);

	const { data: toolSettings } = useQuery({
		queryKey: ["admin-tool-settings"],
		queryFn: () => adminToolSettingsApiService.getToolSettings(),
		enabled: !!currentUser,
	});

	const searchSpaceId = toolSettings?.search_space_id;

	const { data: agentEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "agent"],
		queryFn: () => adminToolSettingsApiService.getToolEvaluationHistory("agent", searchSpaceId),
		enabled: !!currentUser && typeof searchSpaceId === "number",
	});

	const { data: toolEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "tool"],
		queryFn: () => adminToolSettingsApiService.getToolEvaluationHistory("tool", searchSpaceId),
		enabled: !!currentUser && typeof searchSpaceId === "number",
	});

	const { data: apiInputEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "api_input"],
		queryFn: () => adminToolSettingsApiService.getToolEvaluationHistory("api_input", searchSpaceId),
		enabled: !!currentUser && typeof searchSpaceId === "number",
	});

	useEffect(() => {
		fetchLifecycleData();
	}, []);

	const fetchLifecycleData = async () => {
		try {
			setLifecycleLoading(true);
			const result = await adminToolLifecycleApiService.getToolLifecycleList();
			setLifecycleData(result);
		} catch (error) {
			toast.error("Kunde inte ladda lifecycle-data");
			console.error(error);
		} finally {
			setLifecycleLoading(false);
		}
	};

	const latestAgentRate =
		agentEvalHistory?.items && agentEvalHistory.items.length > 0
			? agentEvalHistory.items[agentEvalHistory.items.length - 1].success_rate
			: null;
	const latestToolRate =
		toolEvalHistory?.items && toolEvalHistory.items.length > 0
			? toolEvalHistory.items[toolEvalHistory.items.length - 1].success_rate
			: null;
	const latestApiInputRate =
		apiInputEvalHistory?.items && apiInputEvalHistory.items.length > 0
			? apiInputEvalHistory.items[apiInputEvalHistory.items.length - 1].success_rate
			: null;

	const prevAgentRate =
		agentEvalHistory?.items && agentEvalHistory.items.length > 1
			? agentEvalHistory.items[agentEvalHistory.items.length - 2].success_rate
			: null;
	const prevToolRate =
		toolEvalHistory?.items && toolEvalHistory.items.length > 1
			? toolEvalHistory.items[toolEvalHistory.items.length - 2].success_rate
			: null;
	const prevApiInputRate =
		apiInputEvalHistory?.items && apiInputEvalHistory.items.length > 1
			? apiInputEvalHistory.items[apiInputEvalHistory.items.length - 2].success_rate
			: null;

	const agentDelta =
		latestAgentRate != null && prevAgentRate != null ? latestAgentRate - prevAgentRate : null;
	const toolDelta =
		latestToolRate != null && prevToolRate != null ? latestToolRate - prevToolRate : null;
	const apiInputDelta =
		latestApiInputRate != null && prevApiInputRate != null
			? latestApiInputRate - prevApiInputRate
			: null;

	// Lifecycle rate from latest eval (for the 4th metric card)
	const latestEvalRate = toolSettings?.latest_evaluation?.success_rate ?? null;

	// Latest eval date for summary line
	const latestEvalDate = toolSettings?.latest_evaluation?.run_at
		? new Date(toolSettings.latest_evaluation.run_at).toLocaleString("sv-SE")
		: null;

	const toggleToolStatus = async (tool: ToolLifecycleStatus) => {
		const newStatus = tool.status === "live" ? "review" : "live";

		if (
			newStatus === "live" &&
			tool.success_rate !== null &&
			tool.success_rate < tool.required_success_rate
		) {
			toast.error(
				`Verktyget nar inte kraven (${(tool.success_rate * 100).toFixed(1)}% < ${(tool.required_success_rate * 100).toFixed(0)}%)`
			);
			return;
		}

		try {
			setActionLoading(tool.tool_id);
			await adminToolLifecycleApiService.updateToolStatus(tool.tool_id, {
				status: newStatus,
				notes: `Status andrad till ${newStatus}`,
			});
			toast.success(`${tool.tool_id} satt till ${newStatus}`);
			await fetchLifecycleData();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Kunde inte uppdatera status");
			console.error(error);
		} finally {
			setActionLoading(null);
		}
	};

	const performRollback = async () => {
		if (!rollbackTool || !rollbackNotes.trim()) {
			toast.error("Ange en anledning for rollback");
			return;
		}

		try {
			setActionLoading(rollbackTool.tool_id);
			await adminToolLifecycleApiService.rollbackTool(rollbackTool.tool_id, {
				notes: rollbackNotes,
			});
			toast.success(`Rollback genomford: ${rollbackTool.tool_id}`);
			setRollbackTool(null);
			setRollbackNotes("");
			await fetchLifecycleData();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Rollback misslyckades");
			console.error(error);
		} finally {
			setActionLoading(null);
		}
	};

	const bulkPromoteToLive = async () => {
		if (
			!confirm(
				`Befordra ALLA ${lifecycleData?.review_count || 0} review-verktyg till LIVE?\n\nDetta kringgår tröskelvärden och är avsett för initial migrering.`
			)
		) {
			return;
		}

		try {
			setLifecycleLoading(true);
			const result = await adminToolLifecycleApiService.bulkPromoteToLive();
			toast.success(
				(result as { message?: string })?.message || "Alla verktyg befordrade till LIVE"
			);
			await fetchLifecycleData();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Bulk-befordran misslyckades");
			console.error(error);
		} finally {
			setLifecycleLoading(false);
		}
	};

	const filteredTools = useMemo(() => {
		let tools = lifecycleData?.tools ?? [];

		// Text search filter
		if (searchQuery) {
			tools = tools.filter((tool) =>
				tool.tool_id.toLowerCase().includes(searchQuery.toLowerCase())
			);
		}

		// Status filter
		if (statusFilter === "live") {
			tools = tools.filter((tool) => tool.status === "live");
		} else if (statusFilter === "review") {
			tools = tools.filter((tool) => tool.status !== "live");
		} else if (statusFilter === "ready") {
			tools = tools.filter(
				(tool) =>
					tool.status !== "live" &&
					tool.success_rate !== null &&
					tool.success_rate >= tool.required_success_rate
			);
		}

		return tools;
	}, [lifecycleData?.tools, searchQuery, statusFilter]);

	const canToggle = (tool: ToolLifecycleStatus): boolean => {
		if (tool.status === "live") return true;
		if (tool.success_rate === null) return false;
		return tool.success_rate >= tool.required_success_rate;
	};

	const getTooltipText = (tool: ToolLifecycleStatus): string => {
		if (tool.status === "live") return "Satt till review";
		if (tool.success_rate === null) return "Ingen eval-data tillganglig";
		if (tool.success_rate < tool.required_success_rate) {
			return `Success rate for lag: ${(tool.success_rate * 100).toFixed(1)}% < ${(tool.required_success_rate * 100).toFixed(0)}%`;
		}
		return "Befordra till live";
	};

	// Action icon helper for lifecycle table
	const getActionIcon = (tool: ToolLifecycleStatus) => {
		if (tool.status === "live") return "rollback"; // show rollback icon
		if (tool.success_rate !== null && tool.success_rate >= tool.required_success_rate) {
			return "promote"; // ready to promote
		}
		return "blocked"; // under threshold
	};

	// ---- Render ----

	return (
		<div className="space-y-4">
			{/* 1. Nyckeltal */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base">Nyckeltal</CardTitle>
				</CardHeader>
				<CardContent className="space-y-3">
					<div className="grid gap-3 grid-cols-2 md:grid-cols-4">
						{/* Agentval */}
						<div className="rounded-lg border p-3 space-y-1">
							<p className="text-xs text-muted-foreground">Agentval</p>
							<p className="text-xl font-bold tabular-nums">{formatPercent(latestAgentRate)}</p>
							{agentDelta !== null && (
								<p className={`text-xs ${agentDelta >= 0 ? "text-emerald-600" : "text-red-500"}`}>
									{agentDelta >= 0 ? "\u25B2" : "\u25BC"} {formatSignedPercent(agentDelta)}
								</p>
							)}
						</div>
						{/* Toolval */}
						<div className="rounded-lg border p-3 space-y-1">
							<p className="text-xs text-muted-foreground">Toolval</p>
							<p className="text-xl font-bold tabular-nums">{formatPercent(latestToolRate)}</p>
							{toolDelta !== null && (
								<p className={`text-xs ${toolDelta >= 0 ? "text-emerald-600" : "text-red-500"}`}>
									{toolDelta >= 0 ? "\u25B2" : "\u25BC"} {formatSignedPercent(toolDelta)}
								</p>
							)}
						</div>
						{/* API Input */}
						<div className="rounded-lg border p-3 space-y-1">
							<p className="text-xs text-muted-foreground">API Input</p>
							<p className="text-xl font-bold tabular-nums">{formatPercent(latestApiInputRate)}</p>
							{apiInputDelta !== null && (
								<p
									className={`text-xs ${apiInputDelta >= 0 ? "text-emerald-600" : "text-red-500"}`}
								>
									{apiInputDelta >= 0 ? "\u25B2" : "\u25BC"} {formatSignedPercent(apiInputDelta)}
								</p>
							)}
						</div>
						{/* Lifecycle */}
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

					{/* Summary line */}
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
						<span>
							Fas: <span className="font-medium text-foreground">Shadow</span>
						</span>
					</div>
				</CardContent>
			</Card>

			{/* 2. Trenddiagram (30 dagar) -- 2x2 grid */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base">Trenddiagram (30 dagar)</CardTitle>
				</CardHeader>
				<CardContent>
					<div className="grid gap-3 grid-cols-1 md:grid-cols-2">
						<HistoryTrendBars
							points={agentEvalHistory?.items ?? []}
							valueKey="success_rate"
							label="Agentval"
						/>
						<HistoryTrendBars
							points={toolEvalHistory?.items ?? []}
							valueKey="success_rate"
							label="Toolval"
						/>
						<HistoryTrendBars
							points={apiInputEvalHistory?.items ?? []}
							valueKey="success_rate"
							label="API Input"
						/>
						<HistoryTrendBars
							points={
								// Combined/overall trend -- use agent as proxy if no combined data
								agentEvalHistory?.items ?? []
							}
							valueKey="success_rate"
							label="Overgripande"
						/>
					</div>
				</CardContent>
			</Card>

			{/* 3. Lifecycle-status */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base">Lifecycle-status</CardTitle>
				</CardHeader>
				<CardContent className="space-y-3">
					<div className="flex items-center gap-3 flex-wrap">
						<div className="flex items-center gap-2 flex-1 min-w-[200px]">
							<Search className="h-4 w-4 text-muted-foreground shrink-0" />
							<Input
								placeholder="Sok verktyg..."
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
						{lifecycleData && lifecycleData.review_count > 0 && (
							<Button
								onClick={bulkPromoteToLive}
								variant="outline"
								size="sm"
								className="gap-1 text-xs h-8"
								disabled={lifecycleLoading}
							>
								Promota alla redo
							</Button>
						)}
					</div>

					{lifecycleLoading ? (
						<div className="flex items-center justify-center h-24">
							<Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
						</div>
					) : (
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead className="text-xs">Verktyg</TableHead>
									<TableHead className="text-xs">Status</TableHead>
									<TableHead className="text-xs">Rate</TableHead>
									<TableHead className="text-xs">Troskel</TableHead>
									<TableHead className="text-xs text-right">Atgard</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{filteredTools.length === 0 ? (
									<TableRow>
										<TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
											{searchQuery ? "Inga verktyg hittades" : "Inga verktyg tillgangliga"}
										</TableCell>
									</TableRow>
								) : (
									filteredTools.map((tool) => {
										const action = getActionIcon(tool);
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
															<span className="text-xs text-muted-foreground px-1">&mdash;</span>
														)}
													</div>
												</TableCell>
											</TableRow>
										);
									})
								)}
							</TableBody>
						</Table>
					)}

					{/* Legend */}
					<div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground border-t pt-2">
						<span>
							<CheckCircle2 className="inline h-3 w-3 text-emerald-600" /> = Redo att promota
						</span>
						<span>
							<ShieldAlert className="inline h-3 w-3 text-red-600" /> = Emergency rollback
						</span>
						<span>&mdash; = Under troskel</span>
					</div>
				</CardContent>
			</Card>

			{/* 4. Eval-historik (tabbed detail) */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base">Eval-historik</CardTitle>
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
								title="Historik: Agentval"
								description="Utveckling over tid for agent_accuracy och success rate."
								history={agentEvalHistory}
								selectedCategory={agentHistoryCategory}
								onSelectCategory={setAgentHistoryCategory}
							/>
						</TabsContent>

						<TabsContent value="tool" className="mt-3">
							<StageHistorySection
								title="Historik: Toolval"
								description="Utveckling over tid for tool_accuracy och success rate."
								history={toolEvalHistory}
								selectedCategory={toolHistoryCategory}
								onSelectCategory={setToolHistoryCategory}
							/>
						</TabsContent>

						<TabsContent value="api_input" className="mt-3">
							<StageHistorySection
								title="Historik: API Input"
								description="Utveckling over tid for api_input och success rate."
								history={apiInputEvalHistory}
								selectedCategory={apiInputHistoryCategory}
								onSelectCategory={setApiInputHistoryCategory}
							/>
						</TabsContent>
					</Tabs>
				</CardContent>
			</Card>

			{/* 5. Audit Trail */}
			<AuditTrail entries={auditEntries} />

			{/* Emergency Rollback Dialog */}
			<AlertDialog
				open={rollbackTool !== null}
				onOpenChange={(open) => !open && setRollbackTool(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Emergency Rollback</AlertDialogTitle>
						<AlertDialogDescription>
							Satt tillbaka <span className="font-mono font-semibold">{rollbackTool?.tool_id}</span>{" "}
							till review-status. Detta tar omedelbart bort verktyget fran produktion.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<div className="py-4">
						<label className="text-sm font-medium mb-2 block">Anledning (kravs):</label>
						<Input
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
								"Bekrafta Rollback"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
