"use client";

import { useEffect, useState, useCallback } from "react";
import {
	AlertCircle,
	Beaker,
	CheckCircle2,
	ChevronDown,
	ChevronUp,
	Clock,
	Loader2,
	Play,
	XCircle,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
	nexusApiService,
	type AutoLoopRunResponse,
	type LoopRunDetail,
	type PlatformToolResponse,
} from "@/lib/apis/nexus-api.service";

const CATEGORY_LABELS: Record<string, string> = {
	"": "Alla kategorier",
	smhi: "SMHI (Vader)",
	scb: "SCB (Statistik)",
	kolada: "Kolada (Nyckeltal)",
	riksdagen: "Riksdagen",
	trafikverket: "Trafikverket",
	bolagsverket: "Bolagsverket",
	marketplace: "Marknadsplats",
	skolverket: "Skolverket",
	builtin: "Inbyggda verktyg",
	geoapify: "Kartor (Geoapify)",
};

const BAND_LABELS = ["Band 0 (Exakt)", "Band 1 (Hog)", "Band 2 (Medel)", "Band 3 (Lag)"];

type FilterMode = "all" | "category" | "namespace" | "tool";

export function LoopTab() {
	const [runs, setRuns] = useState<AutoLoopRunResponse[]>([]);
	const [platformTools, setPlatformTools] = useState<PlatformToolResponse[]>([]);
	const [categories, setCategories] = useState<string[]>([]);
	const [filterMode, setFilterMode] = useState<FilterMode>("all");
	const [selectedCategory, setSelectedCategory] = useState<string>("");
	const [selectedNamespace, setSelectedNamespace] = useState<string>("");
	const [selectedToolId, setSelectedToolId] = useState<string>("");
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [starting, setStarting] = useState(false);
	const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
	const [runDetails, setRunDetails] = useState<Record<string, LoopRunDetail>>({});
	const [detailLoading, setDetailLoading] = useState<string | null>(null);
	const [approving, setApproving] = useState<string | null>(null);

	// Derive unique namespace prefixes from tools (first 2 segments)
	const namespaces = Array.from(
		new Set(
			platformTools
				.map((t) => {
					const parts = t.namespace.split("/");
					return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : t.namespace;
				})
				.filter(Boolean),
		),
	).sort();

	const loadRuns = () => {
		setLoading(true);
		nexusApiService
			.getLoopRuns()
			.then(setRuns)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	};

	const loadPlatformTools = () => {
		nexusApiService
			.getPlatformTools()
			.then((data) => {
				setPlatformTools(data.tools || []);
				setCategories(data.categories || []);
			})
			.catch(() => {
				/* non-critical */
			});
	};

	useEffect(() => {
		loadRuns();
		loadPlatformTools();
	}, []);

	const handleStart = () => {
		setStarting(true);
		let request: { category?: string; tool_ids?: string[]; namespace?: string } = {};
		if (filterMode === "category" && selectedCategory) {
			request = { category: selectedCategory };
		} else if (filterMode === "namespace" && selectedNamespace) {
			request = { namespace: selectedNamespace };
		} else if (filterMode === "tool" && selectedToolId) {
			request = { tool_ids: [selectedToolId] };
		}
		nexusApiService
			.startLoop(request)
			.then(() => {
				loadRuns();
			})
			.catch((err) => setError(err.message))
			.finally(() => setStarting(false));
	};

	const filterLabel = (() => {
		if (filterMode === "category" && selectedCategory) {
			return CATEGORY_LABELS[selectedCategory] || selectedCategory;
		}
		if (filterMode === "namespace" && selectedNamespace) {
			return selectedNamespace;
		}
		if (filterMode === "tool" && selectedToolId) {
			return selectedToolId;
		}
		return null;
	})();

	const handleToggleExpand = useCallback(
		(runId: string) => {
			if (expandedRunId === runId) {
				setExpandedRunId(null);
				return;
			}
			setExpandedRunId(runId);
			if (!runDetails[runId]) {
				setDetailLoading(runId);
				nexusApiService
					.getLoopRunDetail(runId)
					.then((detail) => {
						setRunDetails((prev) => ({ ...prev, [runId]: detail }));
					})
					.catch((err) => setError(err.message))
					.finally(() => setDetailLoading(null));
			}
		},
		[expandedRunId, runDetails],
	);

	const handleApprove = useCallback((runId: string) => {
		setApproving(runId);
		nexusApiService
			.approveLoopRun(runId)
			.then(() => {
				loadRuns();
				setRunDetails((prev) => {
					const detail = prev[runId];
					if (detail) {
						return { ...prev, [runId]: { ...detail, status: "approved" } };
					}
					return prev;
				});
			})
			.catch((err) => setError(err.message))
			.finally(() => setApproving(null));
	}, []);

	const totalHardNegatives = runs.reduce(
		(sum, r) => sum + (r.failures || 0),
		0,
	);

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground p-4">
				<Loader2 className="h-4 w-4 animate-spin" />
				Laddar loop-korningar...
			</div>
		);
	}

	if (error) {
		return (
			<Alert variant="destructive">
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		);
	}

	return (
		<div className="space-y-6">
			{/* Header + Category Filter + Start Button */}
			<div className="flex items-center justify-between">
				<div>
					<h3 className="text-lg font-semibold flex items-center gap-2">
						<Beaker className="h-5 w-5" />
						Auto Loop -- Sjalvforbattring
					</h3>
					<p className="text-sm text-muted-foreground">
						7-stegs pipeline: generera, eval, kluster, root cause, test, review, deploy
					</p>
				</div>
				<div className="flex items-center gap-2 flex-wrap">
					{/* Filter mode selector */}
					<select
						value={filterMode}
						onChange={(e) => setFilterMode(e.target.value as FilterMode)}
						className="rounded-md border bg-background px-3 py-2 text-sm"
					>
						<option value="all">Alla ({platformTools.length})</option>
						<option value="category">Kategori</option>
						<option value="namespace">Namespace</option>
						<option value="tool">Verktyg</option>
					</select>

					{/* Category selector */}
					{filterMode === "category" && (
						<select
							value={selectedCategory}
							onChange={(e) => setSelectedCategory(e.target.value)}
							className="rounded-md border bg-background px-3 py-2 text-sm"
						>
							<option value="">Valj kategori...</option>
							{categories
								.filter((c) => c !== "external_model")
								.map((cat) => (
									<option key={cat} value={cat}>
										{CATEGORY_LABELS[cat] || cat} (
										{platformTools.filter((t) => t.category === cat).length})
									</option>
								))}
						</select>
					)}

					{/* Namespace selector */}
					{filterMode === "namespace" && (
						<select
							value={selectedNamespace}
							onChange={(e) => setSelectedNamespace(e.target.value)}
							className="rounded-md border bg-background px-3 py-2 text-sm"
						>
							<option value="">Valj namespace...</option>
							{namespaces.map((ns) => (
								<option key={ns} value={ns}>
									{ns} (
									{platformTools.filter((t) => t.namespace.startsWith(ns)).length})
								</option>
							))}
						</select>
					)}

					{/* Tool selector */}
					{filterMode === "tool" && (
						<select
							value={selectedToolId}
							onChange={(e) => setSelectedToolId(e.target.value)}
							className="rounded-md border bg-background px-3 py-2 text-sm max-w-xs"
						>
							<option value="">Valj verktyg...</option>
							{platformTools
								.filter((t) => t.category !== "external_model")
								.sort((a, b) => a.tool_id.localeCompare(b.tool_id))
								.map((t) => (
									<option key={t.tool_id} value={t.tool_id}>
										{t.tool_id}
									</option>
								))}
						</select>
					)}

					<Button onClick={handleStart} disabled={starting}>
						{starting ? (
							<Loader2 className="h-4 w-4 animate-spin mr-2" />
						) : (
							<Play className="h-4 w-4 mr-2" />
						)}
						{starting
							? "Kor loop..."
							: filterLabel
								? `Kor loop for ${filterLabel}`
								: "Starta loop"}
					</Button>
				</div>
			</div>

			{/* Stats */}
			<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
				<StatCard label="Totalt korningar" value={String(runs.length)} />
				<StatCard
					label="Godkanda forslag"
					value={String(
						runs.reduce((sum, r) => sum + (r.approved_proposals || 0), 0),
					)}
				/>
				<StatCard
					label="Hard negatives"
					value={String(totalHardNegatives)}
				/>
				<StatCard
					label="Senaste status"
					value={runs.length > 0 ? runs[0].status : "--"}
				/>
			</div>

			{/* Run history */}
			{runs.length === 0 ? (
				<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
					Inga loop-korningar annu. Klicka &quot;Starta loop&quot; for att borja.
				</div>
			) : (
				<div className="rounded-lg border bg-card">
					<div className="p-4 border-b">
						<h4 className="font-semibold">Korningshistorik</h4>
					</div>
					<div className="divide-y">
						{runs.map((run) => {
							const isExpanded = expandedRunId === run.id;
							const detail = runDetails[run.id];
							const isLoadingDetail = detailLoading === run.id;

							return (
								<div key={run.id}>
									<div
										className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors"
										onClick={() => handleToggleExpand(run.id)}
									>
										<div className="flex items-center gap-3">
											<StatusIcon status={run.status} />
											<div>
												<p className="text-sm font-medium">
													Loop #{run.loop_number}
												</p>
												<p className="text-xs text-muted-foreground">
													{run.started_at
														? new Date(run.started_at).toLocaleString("sv-SE")
														: "Ej startad"}
												</p>
											</div>
										</div>
										<div className="flex items-center gap-4 text-sm">
											{run.total_tests !== null && (
												<span className="text-muted-foreground">
													{run.failures || 0}/{run.total_tests} fel
												</span>
											)}
											{run.approved_proposals !== null &&
												run.approved_proposals > 0 && (
													<span className="text-green-600 font-medium">
														{run.approved_proposals} godkanda
													</span>
												)}
											<StatusBadge status={run.status} />
											{isExpanded ? (
												<ChevronUp className="h-4 w-4 text-muted-foreground" />
											) : (
												<ChevronDown className="h-4 w-4 text-muted-foreground" />
											)}
										</div>
									</div>

									{/* Expanded detail section */}
									{isExpanded && (
										<div className="border-t bg-muted/30 p-4 space-y-4">
											{isLoadingDetail ? (
												<div className="flex items-center gap-2 text-muted-foreground">
													<Loader2 className="h-4 w-4 animate-spin" />
													Laddar detaljer...
												</div>
											) : detail ? (
												<>
													{/* Approve button */}
													<div className="flex items-center justify-between">
														<h5 className="text-sm font-semibold">
															Korningsdetaljer -- Loop #{detail.loop_number}
														</h5>
														<Button
															size="sm"
															onClick={(e) => {
																e.stopPropagation();
																handleApprove(run.id);
															}}
															disabled={
																run.status !== "review" ||
																approving === run.id
															}
														>
															{approving === run.id ? (
																<Loader2 className="h-4 w-4 animate-spin mr-2" />
															) : (
																<CheckCircle2 className="h-4 w-4 mr-2" />
															)}
															Godkann alla
														</Button>
													</div>

													<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
														{/* Proposals */}
														<Card>
															<CardHeader className="py-3 px-4">
																<CardTitle className="text-sm">
																	Forslag ({detail.proposals.length})
																</CardTitle>
															</CardHeader>
															<CardContent className="px-4 pb-4">
																{detail.proposals.length === 0 ? (
																	<p className="text-sm text-muted-foreground">
																		Inga forslag i denna korning.
																	</p>
																) : (
																	<div className="space-y-3">
																		{detail.proposals.map((proposal, idx) => (
																			<div
																				key={`${proposal.tool_id}-${proposal.field}-${idx}`}
																				className="rounded-md border bg-background p-3 text-sm space-y-1"
																			>
																				<p>
																					<span className="font-medium text-muted-foreground">
																						Tool:
																					</span>{" "}
																					{proposal.tool_id}
																				</p>
																				<p>
																					<span className="font-medium text-muted-foreground">
																						Falt:
																					</span>{" "}
																					{proposal.field}
																				</p>
																				<p>
																					<span className="font-medium text-muted-foreground">
																						Anledning:
																					</span>{" "}
																					{proposal.reason}
																				</p>
																			</div>
																		))}
																	</div>
																)}
															</CardContent>
														</Card>

														{/* Band distribution + Platform stats */}
														<div className="space-y-4">
															<Card>
																<CardHeader className="py-3 px-4">
																	<CardTitle className="text-sm">
																		Band-fordelning
																	</CardTitle>
																</CardHeader>
																<CardContent className="px-4 pb-4">
																	{detail.band_distribution.length === 0 ? (
																		<p className="text-sm text-muted-foreground">
																			Ingen data.
																		</p>
																	) : (
																		<div className="space-y-2">
																			{detail.band_distribution.map(
																				(count, bandIdx) => {
																					const total =
																						detail.band_distribution.reduce(
																							(a, b) => a + b,
																							0,
																						);
																					const pct =
																						total > 0
																							? Math.round(
																									(count / total) * 100,
																								)
																							: 0;
																					return (
																						<div
																							key={bandIdx}
																							className="flex items-center gap-3 text-sm"
																						>
																							<span className="w-28 text-muted-foreground">
																								{BAND_LABELS[bandIdx] ||
																									`Band ${bandIdx}`}
																							</span>
																							<div className="flex-1 h-4 bg-muted rounded overflow-hidden">
																								<div
																									className="h-full bg-primary rounded"
																									style={{
																										width: `${pct}%`,
																									}}
																								/>
																							</div>
																							<span className="w-16 text-right tabular-nums">
																								{count} ({pct}%)
																							</span>
																						</div>
																					);
																				},
																			)}
																		</div>
																	)}
																</CardContent>
															</Card>

															<Card>
																<CardHeader className="py-3 px-4">
																	<CardTitle className="text-sm">
																		Plattformsjamforelse
																	</CardTitle>
																</CardHeader>
																<CardContent className="px-4 pb-4">
																	<div className="grid grid-cols-2 gap-4 text-sm">
																		<div>
																			<p className="text-muted-foreground">
																				Jamforelser
																			</p>
																			<p className="text-lg font-bold">
																				{detail.platform_comparisons}
																			</p>
																		</div>
																		<div>
																			<p className="text-muted-foreground">
																				Overensstammelser
																			</p>
																			<p className="text-lg font-bold">
																				{detail.platform_agreements}
																			</p>
																		</div>
																		{detail.platform_comparisons > 0 && (
																			<div className="col-span-2">
																				<p className="text-muted-foreground">
																					Overensstammelsegrad
																				</p>
																				<p className="text-lg font-bold">
																					{Math.round(
																						(detail.platform_agreements /
																							detail.platform_comparisons) *
																							100,
																					)}
																					%
																				</p>
																			</div>
																		)}
																	</div>
																</CardContent>
															</Card>
														</div>
													</div>
												</>
											) : (
												<p className="text-sm text-muted-foreground">
													Kunde inte ladda detaljer.
												</p>
											)}
										</div>
									)}
								</div>
							);
						})}
					</div>
				</div>
			)}
		</div>
	);
}

function StatCard({ label, value }: { label: string; value: string }) {
	return (
		<div className="rounded-lg border bg-card p-4">
			<p className="text-sm text-muted-foreground">{label}</p>
			<p className="text-2xl font-bold mt-1">{value}</p>
		</div>
	);
}

function StatusIcon({ status }: { status: string }) {
	switch (status) {
		case "approved":
		case "deployed":
			return <CheckCircle2 className="h-5 w-5 text-green-600" />;
		case "rejected":
		case "failed":
			return <XCircle className="h-5 w-5 text-red-600" />;
		case "running":
		case "analyzing":
		case "proposing":
			return <Loader2 className="h-5 w-5 text-blue-600 animate-spin" />;
		default:
			return <Clock className="h-5 w-5 text-muted-foreground" />;
	}
}

function StatusBadge({ status }: { status: string }) {
	const colors: Record<string, string> = {
		pending: "bg-gray-100 text-gray-700",
		running: "bg-blue-100 text-blue-700",
		analyzing: "bg-blue-100 text-blue-700",
		proposing: "bg-purple-100 text-purple-700",
		review: "bg-yellow-100 text-yellow-700",
		approved: "bg-green-100 text-green-700",
		rejected: "bg-red-100 text-red-700",
		deployed: "bg-green-100 text-green-700",
		failed: "bg-red-100 text-red-700",
	};
	const color = colors[status] || "bg-gray-100 text-gray-700";

	return (
		<span className={`text-xs px-2 py-0.5 rounded ${color}`}>{status}</span>
	);
}
