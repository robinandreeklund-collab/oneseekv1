"use client";

import { useState, useEffect } from "react";
import { 
	Search, 
	CheckCircle2, 
	Clock, 
	ShieldAlert,
	AlertCircle,
	Loader2,
	ToggleLeft,
	ToggleRight
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";
import { getBackendUrl } from "@/lib/config";

interface ToolLifecycleStatus {
	tool_id: string;
	status: "review" | "live";
	success_rate: number | null;
	total_tests: number | null;
	last_eval_at: string | null;
	required_success_rate: number;
	changed_by_id: string | null;
	changed_at: string;
	notes: string | null;
	created_at: string;
}

interface ToolLifecycleListResponse {
	tools: ToolLifecycleStatus[];
	total_count: number;
	live_count: number;
	review_count: number;
}

export function ToolLifecyclePage() {
	const [data, setData] = useState<ToolLifecycleListResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [searchQuery, setSearchQuery] = useState("");
	const [rollbackTool, setRollbackTool] = useState<ToolLifecycleStatus | null>(null);
	const [rollbackNotes, setRollbackNotes] = useState("");
	const [actionLoading, setActionLoading] = useState<string | null>(null);

	useEffect(() => {
		fetchLifecycleData();
	}, []);

	const fetchLifecycleData = async () => {
		try {
			setLoading(true);
			const response = await fetch(`${getBackendUrl()}/admin/tool-lifecycle`, {
				credentials: "include",
			});
			if (!response.ok) throw new Error("Failed to fetch lifecycle data");
			const result = await response.json();
			setData(result);
		} catch (error) {
			toast.error("Failed to load lifecycle data");
			console.error(error);
		} finally {
			setLoading(false);
		}
	};

	const toggleToolStatus = async (tool: ToolLifecycleStatus) => {
		const newStatus = tool.status === "live" ? "review" : "live";
		
		// Check if tool meets threshold for promotion to live
		if (
			newStatus === "live" &&
			tool.success_rate !== null &&
			tool.success_rate < tool.required_success_rate
		) {
			toast.error(
				`Tool does not meet required success rate (${(tool.success_rate * 100).toFixed(1)}% < ${(tool.required_success_rate * 100).toFixed(0)}%)`
			);
			return;
		}

		try {
			setActionLoading(tool.tool_id);
			const response = await fetch(
				`${getBackendUrl()}/admin/tool-lifecycle/${encodeURIComponent(tool.tool_id)}`,
				{
					method: "PUT",
					headers: { "Content-Type": "application/json" },
					credentials: "include",
					body: JSON.stringify({
						status: newStatus,
						notes: `Status changed to ${newStatus}`,
					}),
				}
			);

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || "Failed to update status");
			}

			toast.success(`Tool ${tool.tool_id} set to ${newStatus}`);
			await fetchLifecycleData();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to update status");
			console.error(error);
		} finally {
			setActionLoading(null);
		}
	};

	const performRollback = async () => {
		if (!rollbackTool || !rollbackNotes.trim()) {
			toast.error("Please provide a reason for the rollback");
			return;
		}

		try {
			setActionLoading(rollbackTool.tool_id);
			const response = await fetch(
				`${getBackendUrl()}/admin/tool-lifecycle/${encodeURIComponent(rollbackTool.tool_id)}/rollback`,
				{
					method: "POST",
					headers: { "Content-Type": "application/json" },
					credentials: "include",
					body: JSON.stringify({ notes: rollbackNotes }),
				}
			);

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || "Failed to rollback");
			}

			toast.success(`Emergency rollback completed for ${rollbackTool.tool_id}`);
			setRollbackTool(null);
			setRollbackNotes("");
			await fetchLifecycleData();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to rollback");
			console.error(error);
		} finally {
			setActionLoading(null);
		}
	};

	const filteredTools = data?.tools.filter((tool) =>
		tool.tool_id.toLowerCase().includes(searchQuery.toLowerCase())
	) || [];

	const canToggle = (tool: ToolLifecycleStatus): boolean => {
		// Can always toggle from live to review
		if (tool.status === "live") return true;
		
		// Can only toggle from review to live if meets threshold
		if (tool.success_rate === null) return false;
		return tool.success_rate >= tool.required_success_rate;
	};

	const getTooltipText = (tool: ToolLifecycleStatus): string => {
		if (tool.status === "live") return "Set to review status";
		if (tool.success_rate === null) return "No eval data available";
		if (tool.success_rate < tool.required_success_rate) {
			return `Success rate too low: ${(tool.success_rate * 100).toFixed(1)}% < ${(tool.required_success_rate * 100).toFixed(0)}%`;
		}
		return "Promote to live";
	};

	if (loading) {
		return (
			<div className="flex items-center justify-center h-64">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	if (!data) {
		return (
			<div className="flex items-center justify-center h-64 text-muted-foreground">
				Failed to load lifecycle data
			</div>
		);
	}

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold tracking-tight">Tool Lifecycle Management</h1>
				<p className="text-muted-foreground mt-2">
					Hantera lifecycle-status för tools - från review till live
				</p>
			</div>

			{/* Summary Cards */}
			<div className="grid gap-4 md:grid-cols-3">
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">Live Tools</CardTitle>
						<CheckCircle2 className="h-4 w-4 text-emerald-600" />
					</CardHeader>
					<CardContent>
						<div className="text-2xl font-bold">{data.live_count}</div>
						<p className="text-xs text-muted-foreground">
							Tillgängliga i produktion
						</p>
					</CardContent>
				</Card>

				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">Review Tools</CardTitle>
						<Clock className="h-4 w-4 text-amber-600" />
					</CardHeader>
					<CardContent>
						<div className="text-2xl font-bold">{data.review_count}</div>
						<p className="text-xs text-muted-foreground">
							Under evaluering
						</p>
					</CardContent>
				</Card>

				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">Total Tools</CardTitle>
						<ToggleLeft className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div className="text-2xl font-bold">{data.total_count}</div>
						<p className="text-xs text-muted-foreground">
							Alla registrerade tools
						</p>
					</CardContent>
				</Card>
			</div>

			{/* Search */}
			<div className="flex items-center gap-2">
				<Search className="h-4 w-4 text-muted-foreground" />
				<Input
					placeholder="Sök tool ID..."
					value={searchQuery}
					onChange={(e) => setSearchQuery(e.target.value)}
					className="max-w-sm"
				/>
			</div>

			{/* Tools Table */}
			<Card>
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Tool ID</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Success Rate</TableHead>
							<TableHead>Threshold</TableHead>
							<TableHead>Last Eval</TableHead>
							<TableHead>Changed</TableHead>
							<TableHead className="text-right">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{filteredTools.length === 0 ? (
							<TableRow>
								<TableCell colSpan={7} className="text-center text-muted-foreground">
									{searchQuery ? "No tools found" : "No tools available"}
								</TableCell>
							</TableRow>
						) : (
							filteredTools.map((tool) => (
								<TableRow key={tool.tool_id}>
									<TableCell className="font-mono text-sm">
										{tool.tool_id}
									</TableCell>
									<TableCell>
										<Badge
											variant={tool.status === "live" ? "default" : "secondary"}
											className={
												tool.status === "live"
													? "bg-emerald-600 hover:bg-emerald-700"
													: ""
											}
										>
											{tool.status}
										</Badge>
									</TableCell>
									<TableCell>
										{tool.success_rate !== null ? (
											<div className="flex items-center gap-2">
												<span>{(tool.success_rate * 100).toFixed(1)}%</span>
												{tool.success_rate >= tool.required_success_rate ? (
													<CheckCircle2 className="h-4 w-4 text-emerald-600" />
												) : (
													<AlertCircle className="h-4 w-4 text-amber-600" />
												)}
											</div>
										) : (
											<span className="text-muted-foreground">N/A</span>
										)}
									</TableCell>
									<TableCell>
										≥{(tool.required_success_rate * 100).toFixed(0)}%
									</TableCell>
									<TableCell>
										{tool.last_eval_at ? (
											<span className="text-sm text-muted-foreground">
												{new Date(tool.last_eval_at).toLocaleDateString("sv-SE")}
											</span>
										) : (
											<span className="text-muted-foreground">Never</span>
										)}
									</TableCell>
									<TableCell>
										<span className="text-sm text-muted-foreground">
											{new Date(tool.changed_at).toLocaleDateString("sv-SE")}
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
															disabled={!canToggle(tool) || actionLoading === tool.tool_id}
															onClick={() => toggleToolStatus(tool)}
														>
															{actionLoading === tool.tool_id ? (
																<Loader2 className="h-4 w-4 animate-spin" />
															) : tool.status === "live" ? (
																<ToggleRight className="h-4 w-4" />
															) : (
																<ToggleLeft className="h-4 w-4" />
															)}
														</Button>
													</TooltipTrigger>
													<TooltipContent>
														<p>{getTooltipText(tool)}</p>
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
																disabled={actionLoading === tool.tool_id}
																onClick={() => setRollbackTool(tool)}
															>
																<ShieldAlert className="h-4 w-4 text-red-600" />
															</Button>
														</TooltipTrigger>
														<TooltipContent>
															<p>Emergency rollback</p>
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
			</Card>

			{/* Emergency Rollback Dialog */}
			<AlertDialog open={rollbackTool !== null} onOpenChange={(open) => !open && setRollbackTool(null)}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Emergency Rollback</AlertDialogTitle>
						<AlertDialogDescription>
							Sätt tillbaka <span className="font-mono font-semibold">{rollbackTool?.tool_id}</span> till
							review-status. Detta kommer omedelbart ta bort verktyget från produktion.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<div className="py-4">
						<label className="text-sm font-medium mb-2 block">
							Anledning (krävs):
						</label>
						<Input
							placeholder="T.ex. Tool orsakar fel i produktion"
							value={rollbackNotes}
							onChange={(e) => setRollbackNotes(e.target.value)}
						/>
					</div>
					<AlertDialogFooter>
						<AlertDialogCancel onClick={() => {
							setRollbackTool(null);
							setRollbackNotes("");
						}}>
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
								"Bekräfta Rollback"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
