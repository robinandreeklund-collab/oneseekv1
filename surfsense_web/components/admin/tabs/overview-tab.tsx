"use client";

/**
 * Överblick & Lifecycle tab — unified dashboard showing:
 *
 * 1. Key metrics cards (latest success rates per layer)
 * 2. Trend charts (agent, tool, api-input history)
 * 3. Lifecycle table with toggle, rollback, bulk promote
 * 4. Audit trail
 *
 * This replaces:
 * - /admin/lifecycle (standalone page)
 * - Stats: Agentval, Stats: Toolval, Stats: API Input (3 separate tabs)
 */

import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAtomValue } from "jotai";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import {
	Search,
	CheckCircle2,
	Clock,
	ShieldAlert,
	AlertCircle,
	Loader2,
	ToggleLeft,
	ToggleRight,
	TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
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
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { adminToolLifecycleApiService } from "@/lib/apis/admin-tool-lifecycle-api.service";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";
import type {
	ToolLifecycleStatusResponse as ToolLifecycleStatus,
	ToolLifecycleListResponse,
} from "@/contracts/types/admin-tool-lifecycle.types";
import type { ToolEvaluationStageHistoryResponse } from "@/contracts/types/admin-tool-settings.types";
import { LifecycleBadge } from "@/components/admin/shared/lifecycle-badge";
import { AuditTrail, type AuditTrailEntry } from "@/components/admin/shared/audit-trail";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	return `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	const sign = value > 0 ? "+" : "";
	return `${sign}${(value * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Trend bars sub-component
// ---------------------------------------------------------------------------

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
		return <p className="text-xs text-muted-foreground">Ingen historik \u00e4nnu.</p>;
	}
	return (
		<div className="space-y-2">
			<p className="text-xs text-muted-foreground">{label}</p>
			<div className="flex items-end gap-1 h-28 rounded border bg-muted/30 p-2">
				{points.map((point, index) => {
					const raw = point[valueKey];
					const numeric = typeof raw === "number" ? raw : 0;
					const normalized = Math.max(0.04, Math.min(1, numeric));
					const runAt = String(point.run_at ?? "");
					const evalName = String(point.eval_name ?? "");
					const title = `${evalName || "Eval"} \u2022 ${
						runAt ? new Date(runAt).toLocaleString("sv-SE") : "ok\u00e4nd tid"
					} \u2022 ${formatPercent(numeric)}`;
					return (
						<div
							key={`${valueKey}-${index}-${runAt}`}
							className="flex-1 min-w-[6px] rounded bg-primary/80 hover:bg-primary transition-colors"
							style={{ height: `${Math.round(normalized * 100)}%` }}
							title={title}
						/>
					);
				})}
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Stage history section (collapsed version of the old stats tabs)
// ---------------------------------------------------------------------------

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
	const categoryOptions =
		history?.category_series?.map((series) => series.category_id) ?? [];
	const effectiveCategory =
		categoryOptions.includes(selectedCategory) && selectedCategory
			? selectedCategory
			: categoryOptions[0] ?? "";
	const selectedSeries = history?.category_series?.find(
		(series) => series.category_id === effectiveCategory,
	);

	useEffect(() => {
		if (effectiveCategory && effectiveCategory !== selectedCategory) {
			onSelectCategory(effectiveCategory);
		}
	}, [effectiveCategory, selectedCategory, onSelectCategory]);

	return (
		<div className="space-y-4">
			<Card>
				<CardHeader>
					<CardTitle className="text-base">{title}</CardTitle>
					<CardDescription>{description}</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="grid gap-3 md:grid-cols-4">
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Senaste run</p>
							<p className="text-sm font-medium">
								{latest?.run_at
									? new Date(latest.run_at).toLocaleString("sv-SE")
									: "-"}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Success rate</p>
							<p className="text-sm font-medium">
								{formatPercent(latest?.success_rate)}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Stage-metric</p>
							<p className="text-sm font-medium">
								{latest?.stage_metric_name
									? `${latest.stage_metric_name}: ${formatPercent(latest.stage_metric_value ?? null)}`
									: "-"}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">K\u00f6rningar</p>
							<p className="text-sm font-medium">{history?.items?.length ?? 0}</p>
						</div>
					</div>

					<HistoryTrendBars
						points={history?.items ?? []}
						valueKey="success_rate"
						label="\u00d6vergripande success rate \u00f6ver tid"
					/>

					{categoryOptions.length > 0 && (
						<>
							<div className="space-y-2">
								<Label
									htmlFor={`${history?.stage ?? "stage"}-overview-cat`}
								>
									Kategori
								</Label>
								<select
									id={`${history?.stage ?? "stage"}-overview-cat`}
									className="h-10 w-full rounded-md border bg-background px-3 text-sm"
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
							<HistoryTrendBars
								points={selectedSeries?.points ?? []}
								valueKey="success_rate"
								label={
									effectiveCategory
										? `Kategori ${effectiveCategory}: success rate`
										: "Kategori-trend"
								}
							/>
						</>
					)}

					{(history?.items ?? []).length > 0 && (
						<div className="space-y-2">
							<p className="text-sm font-medium">Historiska k\u00f6rningar</p>
							<div className="max-h-48 overflow-auto space-y-1">
								{[...(history?.items ?? [])]
									.reverse()
									.slice(0, 20)
									.map((item, index) => (
										<div
											key={`${item.run_at}-${index}`}
											className="rounded border p-2 text-xs space-y-0.5"
										>
											<p className="font-medium">
												{item.eval_name || "Utan namn"} \u00b7{" "}
												{new Date(item.run_at).toLocaleString("sv-SE")}
											</p>
											<p className="text-muted-foreground">
												Success: {formatPercent(item.success_rate)} \u00b7{" "}
												Tester: {item.passed_tests}/{item.total_tests}
											</p>
										</div>
									))}
							</div>
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function OverviewTab() {
	const { data: currentUser } = useAtomValue(currentUserAtom);

	// Lifecycle state
	const [lifecycleData, setLifecycleData] =
		useState<ToolLifecycleListResponse | null>(null);
	const [lifecycleLoading, setLifecycleLoading] = useState(true);
	const [searchQuery, setSearchQuery] = useState("");
	const [rollbackTool, setRollbackTool] = useState<ToolLifecycleStatus | null>(
		null,
	);
	const [rollbackNotes, setRollbackNotes] = useState("");
	const [actionLoading, setActionLoading] = useState<string | null>(null);

	// Stats category selections
	const [agentHistoryCategory, setAgentHistoryCategory] = useState("");
	const [toolHistoryCategory, setToolHistoryCategory] = useState("");
	const [apiInputHistoryCategory, setApiInputHistoryCategory] = useState("");
	const [statsTab, setStatsTab] = useState("agent");

	// Audit trail (placeholder — will be populated when backend endpoint exists)
	const [auditEntries] = useState<AuditTrailEntry[]>([]);

	// ---- Queries ----

	const { data: toolSettings } = useQuery({
		queryKey: ["admin-tool-settings"],
		queryFn: () => adminToolSettingsApiService.getToolSettings(),
		enabled: !!currentUser,
	});

	const searchSpaceId = toolSettings?.search_space_id;

	const { data: agentEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "agent"],
		queryFn: () =>
			adminToolSettingsApiService.getToolEvaluationHistory(
				"agent",
				searchSpaceId,
			),
		enabled: !!currentUser && typeof searchSpaceId === "number",
	});

	const { data: toolEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "tool"],
		queryFn: () =>
			adminToolSettingsApiService.getToolEvaluationHistory(
				"tool",
				searchSpaceId,
			),
		enabled: !!currentUser && typeof searchSpaceId === "number",
	});

	const { data: apiInputEvalHistory } = useQuery({
		queryKey: ["admin-tool-eval-history", searchSpaceId, "api_input"],
		queryFn: () =>
			adminToolSettingsApiService.getToolEvaluationHistory(
				"api_input",
				searchSpaceId,
			),
		enabled: !!currentUser && typeof searchSpaceId === "number",
	});

	// ---- Lifecycle data ----

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

	// ---- Lifecycle helpers ----

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
			? apiInputEvalHistory.items[apiInputEvalHistory.items.length - 1]
					.success_rate
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
			? apiInputEvalHistory.items[apiInputEvalHistory.items.length - 2]
					.success_rate
			: null;

	const agentDelta =
		latestAgentRate != null && prevAgentRate != null
			? latestAgentRate - prevAgentRate
			: null;
	const toolDelta =
		latestToolRate != null && prevToolRate != null
			? latestToolRate - prevToolRate
			: null;
	const apiInputDelta =
		latestApiInputRate != null && prevApiInputRate != null
			? latestApiInputRate - prevApiInputRate
			: null;

	const toggleToolStatus = async (tool: ToolLifecycleStatus) => {
		const newStatus = tool.status === "live" ? "review" : "live";

		if (
			newStatus === "live" &&
			tool.success_rate !== null &&
			tool.success_rate < tool.required_success_rate
		) {
			toast.error(
				`Verktyget n\u00e5r inte kraven (${(tool.success_rate * 100).toFixed(1)}% < ${(tool.required_success_rate * 100).toFixed(0)}%)`,
			);
			return;
		}

		try {
			setActionLoading(tool.tool_id);
			await adminToolLifecycleApiService.updateToolStatus(tool.tool_id, {
				status: newStatus,
				notes: `Status \u00e4ndrad till ${newStatus}`,
			});
			toast.success(`${tool.tool_id} satt till ${newStatus}`);
			await fetchLifecycleData();
		} catch (error) {
			toast.error(
				error instanceof Error
					? error.message
					: "Kunde inte uppdatera status",
			);
			console.error(error);
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
			await fetchLifecycleData();
		} catch (error) {
			toast.error(
				error instanceof Error ? error.message : "Rollback misslyckades",
			);
			console.error(error);
		} finally {
			setActionLoading(null);
		}
	};

	const bulkPromoteToLive = async () => {
		if (
			!confirm(
				`Befordra ALLA ${lifecycleData?.review_count || 0} review-verktyg till LIVE?\n\nDetta kringg\u00e5r tr\u00f6skelv\u00e4rden och \u00e4r avsett f\u00f6r initial migrering.`,
			)
		) {
			return;
		}

		try {
			setLifecycleLoading(true);
			const result = await adminToolLifecycleApiService.bulkPromoteToLive();
			toast.success(
				(result as { message?: string })?.message ||
					"Alla verktyg befordrade till LIVE",
			);
			await fetchLifecycleData();
		} catch (error) {
			toast.error(
				error instanceof Error
					? error.message
					: "Bulk-befordran misslyckades",
			);
			console.error(error);
		} finally {
			setLifecycleLoading(false);
		}
	};

	const filteredTools = useMemo(
		() =>
			lifecycleData?.tools.filter((tool) =>
				tool.tool_id.toLowerCase().includes(searchQuery.toLowerCase()),
			) || [],
		[lifecycleData?.tools, searchQuery],
	);

	const canToggle = (tool: ToolLifecycleStatus): boolean => {
		if (tool.status === "live") return true;
		if (tool.success_rate === null) return false;
		return tool.success_rate >= tool.required_success_rate;
	};

	const getTooltipText = (tool: ToolLifecycleStatus): string => {
		if (tool.status === "live") return "S\u00e4tt till review";
		if (tool.success_rate === null) return "Ingen eval-data tillg\u00e4nglig";
		if (tool.success_rate < tool.required_success_rate) {
			return `Success rate f\u00f6r l\u00e5g: ${(tool.success_rate * 100).toFixed(1)}% < ${(tool.required_success_rate * 100).toFixed(0)}%`;
		}
		return "Befordra till live";
	};

	// ---- Render ----

	return (
		<div className="space-y-6">
			{/* Key Metric Cards */}
			<div className="grid gap-4 md:grid-cols-4">
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">Agentval</CardTitle>
						<TrendingUp className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div className="text-2xl font-bold">
							{formatPercent(latestAgentRate)}
						</div>
						{agentDelta !== null && (
							<p
								className={`text-xs ${agentDelta >= 0 ? "text-emerald-600" : "text-red-500"}`}
							>
								{formatSignedPercent(agentDelta)} vs f\u00f6reg\u00e5ende
							</p>
						)}
					</CardContent>
				</Card>

				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">Toolval</CardTitle>
						<TrendingUp className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div className="text-2xl font-bold">
							{formatPercent(latestToolRate)}
						</div>
						{toolDelta !== null && (
							<p
								className={`text-xs ${toolDelta >= 0 ? "text-emerald-600" : "text-red-500"}`}
							>
								{formatSignedPercent(toolDelta)} vs f\u00f6reg\u00e5ende
							</p>
						)}
					</CardContent>
				</Card>

				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">API Input</CardTitle>
						<TrendingUp className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div className="text-2xl font-bold">
							{formatPercent(latestApiInputRate)}
						</div>
						{apiInputDelta !== null && (
							<p
								className={`text-xs ${apiInputDelta >= 0 ? "text-emerald-600" : "text-red-500"}`}
							>
								{formatSignedPercent(apiInputDelta)} vs f\u00f6reg\u00e5ende
							</p>
						)}
					</CardContent>
				</Card>

				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">Lifecycle</CardTitle>
						{lifecycleLoading ? (
							<Loader2 className="h-4 w-4 animate-spin" />
						) : (
							<CheckCircle2 className="h-4 w-4 text-emerald-600" />
						)}
					</CardHeader>
					<CardContent>
						<div className="text-2xl font-bold">
							{lifecycleData
								? `${lifecycleData.live_count}/${lifecycleData.total_count}`
								: "-"}
						</div>
						<p className="text-xs text-muted-foreground">
							Live / Total
							{lifecycleData && lifecycleData.review_count > 0
								? ` \u00b7 ${lifecycleData.review_count} under review`
								: ""}
						</p>
					</CardContent>
				</Card>
			</div>

			{/* Latest eval info */}
			{toolSettings?.latest_evaluation && (
				<Card>
					<CardHeader>
						<CardTitle className="text-base">Senaste eval-k\u00f6rning</CardTitle>
					</CardHeader>
					<CardContent className="grid gap-3 md:grid-cols-4 text-sm">
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Tidpunkt</p>
							<p className="font-medium">
								{new Date(
									toolSettings.latest_evaluation.run_at,
								).toLocaleString("sv-SE")}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Antal fr\u00e5gor</p>
							<p className="font-medium">
								{toolSettings.latest_evaluation.total_tests}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Passerade</p>
							<p className="font-medium">
								{toolSettings.latest_evaluation.passed_tests}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Success rate</p>
							<p className="font-medium">
								{(
									toolSettings.latest_evaluation.success_rate * 100
								).toFixed(1)}
								%
							</p>
						</div>
					</CardContent>
				</Card>
			)}

			{/* Eval History Tabs — all 3 layers in one view */}
			<Card>
				<CardHeader>
					<CardTitle>Eval-historik</CardTitle>
					<CardDescription>
						Trender och historik per lager: agentval, toolval, API-input.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Tabs value={statsTab} onValueChange={setStatsTab}>
						<TabsList>
							<TabsTrigger value="agent">Agentval</TabsTrigger>
							<TabsTrigger value="tool">Toolval</TabsTrigger>
							<TabsTrigger value="api_input">API Input</TabsTrigger>
						</TabsList>

						<TabsContent value="agent">
							<StageHistorySection
								title="Historik: Agentval"
								description="Utveckling \u00f6ver tid f\u00f6r agent_accuracy och success rate, uppdelat per kategori."
								history={agentEvalHistory}
								selectedCategory={agentHistoryCategory}
								onSelectCategory={setAgentHistoryCategory}
							/>
						</TabsContent>

						<TabsContent value="tool">
							<StageHistorySection
								title="Historik: Toolval"
								description="Utveckling \u00f6ver tid f\u00f6r tool_accuracy och success rate, uppdelat per kategori."
								history={toolEvalHistory}
								selectedCategory={toolHistoryCategory}
								onSelectCategory={setToolHistoryCategory}
							/>
						</TabsContent>

						<TabsContent value="api_input">
							<StageHistorySection
								title="Historik: API Input"
								description="Utveckling \u00f6ver tid f\u00f6r api_input och success rate, uppdelat per kategori."
								history={apiInputEvalHistory}
								selectedCategory={apiInputHistoryCategory}
								onSelectCategory={setApiInputHistoryCategory}
							/>
						</TabsContent>
					</Tabs>
				</CardContent>
			</Card>

			{/* Lifecycle Table */}
			<Card>
				<CardHeader>
					<CardTitle>Lifecycle-status per verktyg</CardTitle>
					<CardDescription>
						Hantera review/live-status. Verktyg i review exkluderas fr\u00e5n produktion
						i faser med tool_gate eller h\u00f6gre.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="flex items-center justify-between gap-4">
						<div className="flex items-center gap-2 flex-1">
							<Search className="h-4 w-4 text-muted-foreground" />
							<Input
								placeholder="S\u00f6k tool ID..."
								value={searchQuery}
								onChange={(e) => setSearchQuery(e.target.value)}
								className="max-w-sm"
							/>
						</div>

						{lifecycleData && lifecycleData.review_count > 0 && (
							<Button
								onClick={bulkPromoteToLive}
								variant="outline"
								className="gap-2"
								disabled={lifecycleLoading}
							>
								<CheckCircle2 className="h-4 w-4" />
								Befordra alla till Live ({lifecycleData.review_count})
							</Button>
						)}
					</div>

					{lifecycleLoading ? (
						<div className="flex items-center justify-center h-32">
							<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
						</div>
					) : (
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Tool ID</TableHead>
									<TableHead>Status</TableHead>
									<TableHead>Success Rate</TableHead>
									<TableHead>Tr\u00f6skelv\u00e4rde</TableHead>
									<TableHead>Senaste eval</TableHead>
									<TableHead>\u00c4ndrad</TableHead>
									<TableHead className="text-right">
										\u00c5tg\u00e4rder
									</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{filteredTools.length === 0 ? (
									<TableRow>
										<TableCell
											colSpan={7}
											className="text-center text-muted-foreground"
										>
											{searchQuery
												? "Inga verktyg hittades"
												: "Inga verktyg tillg\u00e4ngliga"}
										</TableCell>
									</TableRow>
								) : (
									filteredTools.map((tool) => (
										<TableRow key={tool.tool_id}>
											<TableCell className="font-mono text-sm">
												{tool.tool_id}
											</TableCell>
											<TableCell>
												<LifecycleBadge
													status={
														tool.status === "live"
															? "live"
															: "review"
													}
													successRate={tool.success_rate}
													requiredSuccessRate={
														tool.required_success_rate
													}
													compact
												/>
											</TableCell>
											<TableCell>
												{tool.success_rate !== null ? (
													<div className="flex items-center gap-2">
														<span>
															{(
																tool.success_rate * 100
															).toFixed(1)}
															%
														</span>
														{tool.success_rate >=
														tool.required_success_rate ? (
															<CheckCircle2 className="h-4 w-4 text-emerald-600" />
														) : (
															<AlertCircle className="h-4 w-4 text-amber-600" />
														)}
													</div>
												) : (
													<span className="text-muted-foreground">
														N/A
													</span>
												)}
											</TableCell>
											<TableCell>
												\u2265
												{(
													tool.required_success_rate * 100
												).toFixed(0)}
												%
											</TableCell>
											<TableCell>
												{tool.last_eval_at ? (
													<span className="text-sm text-muted-foreground">
														{new Date(
															tool.last_eval_at,
														).toLocaleDateString("sv-SE")}
													</span>
												) : (
													<span className="text-muted-foreground">
														Aldrig
													</span>
												)}
											</TableCell>
											<TableCell>
												<span className="text-sm text-muted-foreground">
													{new Date(
														tool.changed_at,
													).toLocaleDateString("sv-SE")}
												</span>
											</TableCell>
											<TableCell className="text-right">
												<div className="flex items-center justify-end gap-2">
													<TooltipProvider>
														<Tooltip>
															<TooltipTrigger asChild>
																<Button
																	variant="ghost"
																	size="sm"
																	disabled={
																		!canToggle(
																			tool,
																		) ||
																		actionLoading ===
																			tool.tool_id
																	}
																	onClick={() =>
																		toggleToolStatus(
																			tool,
																		)
																	}
																>
																	{actionLoading ===
																	tool.tool_id ? (
																		<Loader2 className="h-4 w-4 animate-spin" />
																	) : tool.status ===
																		"live" ? (
																		<ToggleRight className="h-4 w-4" />
																	) : (
																		<ToggleLeft className="h-4 w-4" />
																	)}
																</Button>
															</TooltipTrigger>
															<TooltipContent>
																<p>
																	{getTooltipText(
																		tool,
																	)}
																</p>
															</TooltipContent>
														</Tooltip>
													</TooltipProvider>

													{tool.status === "live" && (
														<TooltipProvider>
															<Tooltip>
																<TooltipTrigger asChild>
																	<Button
																		variant="ghost"
																		size="sm"
																		disabled={
																			actionLoading ===
																			tool.tool_id
																		}
																		onClick={() =>
																			setRollbackTool(
																				tool,
																			)
																		}
																	>
																		<ShieldAlert className="h-4 w-4 text-red-600" />
																	</Button>
																</TooltipTrigger>
																<TooltipContent>
																	<p>
																		Emergency rollback
																	</p>
																</TooltipContent>
															</Tooltip>
														</TooltipProvider>
													)}
												</div>
											</TableCell>
										</TableRow>
									))
								)}
							</TableBody>
						</Table>
					)}
				</CardContent>
			</Card>

			{/* Audit Trail */}
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
							S\u00e4tt tillbaka{" "}
							<span className="font-mono font-semibold">
								{rollbackTool?.tool_id}
							</span>{" "}
							till review-status. Detta tar omedelbart bort verktyget fr\u00e5n
							produktion.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<div className="py-4">
						<label className="text-sm font-medium mb-2 block">
							Anledning (kr\u00e4vs):
						</label>
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
								"Bekr\u00e4fta Rollback"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
