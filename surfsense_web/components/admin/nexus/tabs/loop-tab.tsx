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
	ThumbsUp,
	ThumbsDown,
	XCircle,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
	nexusApiService,
	type AutoLoopRunResponse,
	type LoopRunDetail,
	type LoopProposal,
	type LoopStreamEvent,
	type PlatformToolResponse,
} from "@/lib/apis/nexus-api.service";
import { ConcurrencyControl } from "@/components/admin/nexus/shared/concurrency-control";
import { useCategoryLabels } from "@/components/admin/nexus/shared/use-category-labels";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";

const BAND_LABELS = ["Band 0 (Exakt)", "Band 1 (Hog)", "Band 2 (Medel)", "Band 3 (Lag)"];

type FilterMode = "all" | "category" | "namespace" | "tool";

const BAND_COLORS: Record<number, string> = {
	0: "bg-green-100 text-green-700",
	1: "bg-blue-100 text-blue-700",
	2: "bg-amber-100 text-amber-700",
	3: "bg-orange-100 text-orange-700",
	4: "bg-red-100 text-red-700",
};

// ---------------------------------------------------------------------------
// ProposalCard — enriched proposal with diff + failed queries
// ---------------------------------------------------------------------------

function ProposalCard({
	proposal,
	showActions,
}: {
	proposal: LoopProposal;
	showActions: boolean;
}) {
	const [expanded, setExpanded] = useState(false);
	const hasDiff = proposal.current_value || proposal.proposed_value;
	const hasQueries = proposal.failed_queries && proposal.failed_queries.length > 0;

	return (
		<div className="rounded-md border bg-background text-sm">
			{/* Header */}
			<button
				type="button"
				className="w-full p-3 text-left flex items-start justify-between gap-2"
				onClick={() => setExpanded(!expanded)}
			>
				<div className="space-y-1 flex-1 min-w-0">
					<div className="flex items-center gap-2 flex-wrap">
						<span className="font-mono font-medium text-xs">
							{proposal.tool_id}
						</span>
						<Badge variant="outline" className="text-xs py-0">
							{proposal.field}
						</Badge>
						{proposal.embedding_delta !== 0 && (
							<span
								className={`text-xs font-mono px-1.5 py-0.5 rounded ${
									proposal.embedding_delta > 0
										? "bg-green-100 text-green-700"
										: "bg-red-100 text-red-700"
								}`}
							>
								{proposal.embedding_delta > 0 ? "+" : ""}
								{(proposal.embedding_delta * 100).toFixed(1)}pp
							</span>
						)}
						{hasQueries && (
							<span className="text-xs text-muted-foreground">
								{proposal.failed_queries.length} felaktiga fragor
							</span>
						)}
					</div>
					<p className="text-muted-foreground text-xs truncate">
						{proposal.reason}
					</p>
				</div>
				<div className="flex items-center gap-1 shrink-0">
					{showActions && (
						<>
							<button
								type="button"
								className="p-1 rounded hover:bg-green-100 transition-colors"
								title="Godkann forslag"
								onClick={(e) => e.stopPropagation()}
							>
								<ThumbsUp className="h-3.5 w-3.5 text-muted-foreground hover:text-green-600" />
							</button>
							<button
								type="button"
								className="p-1 rounded hover:bg-red-100 transition-colors"
								title="Avvisa forslag"
								onClick={(e) => e.stopPropagation()}
							>
								<ThumbsDown className="h-3.5 w-3.5 text-muted-foreground hover:text-red-600" />
							</button>
						</>
					)}
					{expanded ? (
						<ChevronUp className="h-4 w-4 text-muted-foreground" />
					) : (
						<ChevronDown className="h-4 w-4 text-muted-foreground" />
					)}
				</div>
			</button>

			{/* Expanded content */}
			{expanded && (
				<div className="border-t px-3 pb-3 space-y-3">
					{/* Diff view */}
					{hasDiff && (
						<div className="pt-3 space-y-1.5">
							<p className="text-xs font-medium text-muted-foreground">
								Metadata-diff ({proposal.field})
							</p>
							<div className="grid grid-cols-2 gap-2">
								{proposal.current_value && (
									<div className="rounded border border-red-200 bg-red-50 p-2 text-xs dark:border-red-900 dark:bg-red-950">
										<p className="text-red-600 dark:text-red-400 font-medium mb-0.5">
											Nuvarande
										</p>
										<p className="break-words whitespace-pre-wrap">
											{proposal.current_value}
										</p>
									</div>
								)}
								{proposal.proposed_value && (
									<div className="rounded border border-green-200 bg-green-50 p-2 text-xs dark:border-green-900 dark:bg-green-950">
										<p className="text-green-600 dark:text-green-400 font-medium mb-0.5">
											Foreslagen
										</p>
										<p className="break-words whitespace-pre-wrap">
											{proposal.proposed_value}
										</p>
									</div>
								)}
							</div>
						</div>
					)}

					{/* Failed queries table */}
					{hasQueries && (
						<div className="pt-2 space-y-1.5">
							<p className="text-xs font-medium text-muted-foreground">
								Felaktiga fragor ({proposal.failed_queries.length})
							</p>
							<div className="overflow-x-auto">
								<table className="w-full text-xs">
									<thead>
										<tr className="border-b text-left text-muted-foreground">
											<th className="pb-1.5 pr-2">Fraga</th>
											<th className="pb-1.5 pr-2">Forvantad</th>
											<th className="pb-1.5 pr-2">Fick</th>
											<th className="pb-1.5 pr-2">LLM valde</th>
											<th className="pb-1.5 pr-2">Intent/Zon</th>
											<th className="pb-1.5 pr-2">Agent</th>
											<th className="pb-1.5 pr-2">Band</th>
											<th className="pb-1.5">Conf</th>
										</tr>
									</thead>
									<tbody>
										{proposal.failed_queries.map((fq, fqIdx) => (
											<tr
												key={`fq-${fqIdx}`}
												className="border-b last:border-0"
											>
												<td
													className="py-1.5 pr-2 max-w-[200px] truncate"
													title={fq.query}
												>
													{fq.query}
												</td>
												<td className="py-1.5 pr-2 font-mono text-green-700">
													{fq.expected_tool}
												</td>
												<td className="py-1.5 pr-2 font-mono text-red-600">
													{fq.got_tool}
												</td>
												<td
													className="py-1.5 pr-2 font-mono"
													title={fq.llm_judge_reasoning || ""}
												>
													{fq.llm_judge_tool ? (
														<span
															className={
																fq.llm_judge_tool === fq.expected_tool
																	? "text-green-700"
																	: "text-amber-600"
															}
														>
															{fq.llm_judge_tool}
														</span>
													) : (
														"—"
													)}
												</td>
												<td className="py-1.5 pr-2">
													{fq.resolved_zone || "—"}
												</td>
												<td className="py-1.5 pr-2">
													{fq.selected_agent ? (
														<span className="inline-flex items-center rounded bg-indigo-50 text-indigo-700 px-1 py-0.5">
															{fq.selected_agent}
														</span>
													) : (
														"—"
													)}
												</td>
												<td className="py-1.5 pr-2">
													<span
														className={`inline-flex items-center rounded px-1 py-0.5 font-medium ${BAND_COLORS[fq.band] ?? ""}`}
													>
														{fq.band}
													</span>
												</td>
												<td className="py-1.5 tabular-nums">
													{fq.confidence?.toFixed(3) ?? "—"}
												</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
						</div>
					)}
				</div>
			)}
		</div>
	);
}

export function LoopTab() {
	const CATEGORY_LABELS = useCategoryLabels();
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

	// New: configurable parameters + live progress
	const [maxIterations, setMaxIterations] = useState(1);
	const [batchSize, setBatchSize] = useState(200);
	const [llmJudgeEnabled, setLlmJudgeEnabled] = useState(false);
	const [streamEvents, setStreamEvents] = useState<LoopStreamEvent[]>([]);
	const [liveProgress, setLiveProgress] = useState<LoopStreamEvent | null>(null);

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
		setStreamEvents([]);
		setLiveProgress(null);
		setError(null);

		let request: {
			category?: string;
			tool_ids?: string[];
			namespace?: string;
			batch_size?: number;
			max_iterations?: number;
			run_llm_judge?: boolean;
		} = {};
		if (filterMode === "category" && selectedCategory) {
			request = { category: selectedCategory };
		} else if (filterMode === "namespace" && selectedNamespace) {
			request = { namespace: selectedNamespace };
		} else if (filterMode === "tool" && selectedToolId) {
			request = { tool_ids: [selectedToolId] };
		}
		request.batch_size = batchSize;
		request.max_iterations = maxIterations;
		request.run_llm_judge = llmJudgeEnabled;

		nexusApiService
			.startLoopStream(request, (event) => {
				setStreamEvents((prev) => [...prev, event]);
				setLiveProgress(event);
				if (event.type === "error") {
					setError(event.message || "Okant fel under loop-korning");
				}
			})
			.then(() => {
				loadRuns();
			})
			.catch((err) => setError(err.message))
			.finally(() => {
				setStarting(false);
			});
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

			{/* Loop parameters */}
			<Card>
				<CardContent className="pt-4 pb-4 space-y-4">
					<div className="grid grid-cols-1 md:grid-cols-2 gap-6">
						<div className="space-y-2">
							<div className="flex items-center justify-between">
								<Label className="text-sm">Max iterationer</Label>
								<span className="text-sm font-mono font-medium tabular-nums">
									{maxIterations}
								</span>
							</div>
							<Slider
								min={1}
								max={10}
								step={1}
								value={[maxIterations]}
								onValueChange={([v]) => setMaxIterations(v)}
								disabled={starting}
							/>
							<p className="text-xs text-muted-foreground">
								Stoppar tidigare om alla testfall klaras. Max 10 iterationer.
							</p>
						</div>
						<div className="space-y-2">
							<div className="flex items-center justify-between">
								<Label className="text-sm">Batch-storlek</Label>
								<span className="text-sm font-mono font-medium tabular-nums">
									{batchSize}
								</span>
							</div>
							<Slider
								min={10}
								max={2000}
								step={10}
								value={[batchSize]}
								onValueChange={([v]) => setBatchSize(v)}
								disabled={starting}
							/>
							<p className="text-xs text-muted-foreground">
								Antal testfall per batch. Hogre = snabbare men mer minne.
							</p>
						</div>

						<div className="pt-2">
							<label className="flex items-center gap-2 cursor-pointer">
								<input
									type="checkbox"
									checked={llmJudgeEnabled}
									onChange={(e) => setLlmJudgeEnabled(e.target.checked)}
									disabled={starting}
									className="rounded"
								/>
								<span className="text-sm font-medium">LLM Judge</span>
								<span className="text-xs text-muted-foreground">
									LLM valjer verktyg fran hela agentens namespace (langsammare)
								</span>
							</label>
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Live progress panel */}
			{starting && liveProgress && (
				<Card className="border-blue-200 dark:border-blue-800">
					<CardContent className="pt-4 pb-4 space-y-3">
						<div className="flex items-center gap-2">
							<Loader2 className="h-4 w-4 animate-spin text-blue-600" />
							<span className="text-sm font-medium">
								{liveProgress.detail || "Kor loop..."}
							</span>
						</div>
						{liveProgress.total_cases != null && liveProgress.cases_processed != null && (
							<div className="space-y-1">
								<div className="flex justify-between text-xs text-muted-foreground">
									<span>
										{liveProgress.cases_processed}/{liveProgress.total_cases} fall
									</span>
									<span>
										Batch {liveProgress.batch || 0}/{liveProgress.total_batches || 0}
									</span>
								</div>
								<Progress
									value={
										liveProgress.total_cases > 0
											? (liveProgress.cases_processed / liveProgress.total_cases) * 100
											: 0
									}
								/>
							</div>
						)}
						{liveProgress.iteration != null && liveProgress.total_iterations != null && (
							<div className="flex items-center gap-3 text-xs text-muted-foreground">
								<span>
									Iteration {liveProgress.iteration}/{liveProgress.total_iterations}
								</span>
								{liveProgress.failures != null && liveProgress.total_tests != null && (
									<span>
										{liveProgress.failures}/{liveProgress.total_tests} fel
									</span>
								)}
								{liveProgress.precision_at_1 != null && (
									<span>
										P@1: {(liveProgress.precision_at_1 * 100).toFixed(1)}%
									</span>
								)}
								{liveProgress.intent_accuracy != null && (
									<span>
										Intent: {(liveProgress.intent_accuracy * 100).toFixed(1)}%
									</span>
								)}
								{liveProgress.agent_accuracy != null && (
									<span>
										Agent: {(liveProgress.agent_accuracy * 100).toFixed(1)}%
									</span>
								)}
								{liveProgress.llm_judge_agreement_rate != null && (
									<span>
										LLM-agree: {Math.round(liveProgress.llm_judge_agreement_rate * 100)}%
									</span>
								)}
							</div>
						)}
						{/* Event log */}
						{streamEvents.length > 1 && (
							<div className="max-h-32 overflow-y-auto rounded border bg-muted/50 p-2 text-xs font-mono space-y-0.5">
								{streamEvents.map((evt, idx) => (
									<div key={`evt-${idx}`} className="text-muted-foreground">
										<span className="text-blue-600">[{evt.step || evt.type}]</span>{" "}
										{evt.detail || evt.message || ""}
									</div>
								))}
							</div>
						)}
					</CardContent>
				</Card>
			)}

			{/* Concurrency control */}
			<ConcurrencyControl />

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
										{run.total_cases_available != null &&
											run.total_cases_available > 0 &&
											` (av ${run.total_cases_available})`}
												</span>
											)}
											{run.iterations_completed != null &&
												run.iterations_completed > 1 && (
													<span className="text-blue-600 text-xs">
														{run.iterations_completed} iterationer
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
													{/* Header with embedding delta + approve all */}
													<div className="flex items-center justify-between">
														<div className="flex items-center gap-4">
															<h5 className="text-sm font-semibold">
																Loop #{detail.loop_number}
																{detail.total_cases_available != null && (
																	<span className="text-xs font-normal text-muted-foreground ml-2">
																		({detail.total_tests}/{detail.total_cases_available} testfall utvärderade)
																	</span>
																)}
															</h5>
															{detail.embedding_delta != null && (
																<span
																	className={`text-xs font-mono px-2 py-0.5 rounded ${
																		detail.embedding_delta > 0
																			? "bg-green-100 text-green-700"
																			: detail.embedding_delta < 0
																				? "bg-red-100 text-red-700"
																				: "bg-muted text-muted-foreground"
																	}`}
																>
																	Embedding delta:{" "}
																	{detail.embedding_delta > 0 ? "+" : ""}
																	{(detail.embedding_delta * 100).toFixed(2)}pp
																</span>
															)}
														</div>
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
														{/* Enriched Proposals */}
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
																	<div className="space-y-4">
																		{detail.proposals.map((proposal, idx) => (
																			<ProposalCard
																				key={`${proposal.tool_id}-${proposal.field}-${idx}`}
																				proposal={proposal}
																				showActions={run.status === "review"}
																			/>
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

															{/* LLM Judge — dual-sided comparison */}
															{detail.llm_judge && (
																<Card>
																	<CardHeader className="py-3 px-4">
																		<CardTitle className="text-sm">
																			LLM Judge vs NEXUS
																		</CardTitle>
																	</CardHeader>
																	<CardContent className="px-4 pb-4 space-y-3">
																		{/* Accuracy head-to-head */}
																		<div className="grid grid-cols-2 gap-4 text-sm">
																			<div className="rounded border p-3">
																				<p className="text-xs text-muted-foreground mb-1">
																					NEXUS korrekt
																				</p>
																				<p className="text-2xl font-bold">
																					{Math.round(detail.llm_judge.nexus_accuracy * 100)}%
																				</p>
																				<p className="text-xs text-muted-foreground">
																					{detail.llm_judge.both_correct + detail.llm_judge.nexus_only_correct}/{detail.llm_judge.total}
																				</p>
																			</div>
																			<div className="rounded border p-3">
																				<p className="text-xs text-muted-foreground mb-1">
																					LLM korrekt
																				</p>
																				<p className="text-2xl font-bold">
																					{Math.round(detail.llm_judge.llm_accuracy * 100)}%
																				</p>
																				<p className="text-xs text-muted-foreground">
																					{detail.llm_judge.both_correct + detail.llm_judge.llm_only_correct}/{detail.llm_judge.total}
																				</p>
																			</div>
																		</div>

																		{/* Quadrant breakdown */}
																		<div className="space-y-1.5">
																			<p className="text-xs font-medium text-muted-foreground">
																				Korsmatris ({detail.llm_judge.total} testfall)
																			</p>
																			<div className="grid grid-cols-2 gap-1.5 text-xs">
																				<div className="rounded bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-900 p-2 text-center">
																					<p className="font-bold text-green-700 dark:text-green-400 text-lg">
																						{detail.llm_judge.both_correct}
																					</p>
																					<p className="text-green-600 dark:text-green-500">Bada ratt</p>
																				</div>
																				<div className="rounded bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-900 p-2 text-center">
																					<p className="font-bold text-blue-700 dark:text-blue-400 text-lg">
																						{detail.llm_judge.nexus_only_correct}
																					</p>
																					<p className="text-blue-600 dark:text-blue-500">Bara NEXUS ratt</p>
																				</div>
																				<div className="rounded bg-purple-50 dark:bg-purple-950 border border-purple-200 dark:border-purple-900 p-2 text-center">
																					<p className="font-bold text-purple-700 dark:text-purple-400 text-lg">
																						{detail.llm_judge.llm_only_correct}
																					</p>
																					<p className="text-purple-600 dark:text-purple-500">Bara LLM ratt</p>
																				</div>
																				<div className="rounded bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-900 p-2 text-center">
																					<p className="font-bold text-red-700 dark:text-red-400 text-lg">
																						{detail.llm_judge.both_wrong}
																					</p>
																					<p className="text-red-600 dark:text-red-500">Bada fel</p>
																				</div>
																			</div>
																		</div>

																		{/* Agreement rate */}
																		<div className="flex items-center justify-between text-xs text-muted-foreground border-t pt-2">
																			<span>Overensstammelse</span>
																			<span className="font-mono font-medium">
																				{detail.llm_judge.agreements}/{detail.llm_judge.total} ({Math.round(detail.llm_judge.agreement_rate * 100)}%)
																			</span>
																		</div>

																		{/* Disagreements table */}
																		{detail.llm_judge.disagreements.length > 0 && (
																			<div className="space-y-1.5">
																				<p className="text-xs font-medium text-muted-foreground">
																					Oenigheter ({detail.llm_judge.disagreements.length})
																				</p>
																				<div className="max-h-48 overflow-y-auto">
																					<table className="w-full text-xs">
																						<thead>
																							<tr className="border-b text-left text-muted-foreground">
																								<th className="pb-1 pr-2">Fraga</th>
																								<th className="pb-1 pr-2">NEXUS</th>
																								<th className="pb-1 pr-2">LLM</th>
																								<th className="pb-1 pr-2">Forvantad</th>
																								<th className="pb-1 pr-2">Vinnare</th>
																								<th className="pb-1">Motivering</th>
																							</tr>
																						</thead>
																						<tbody>
																							{detail.llm_judge.disagreements.map((d, idx) => (
																								<tr key={`disagree-${idx}`} className="border-b last:border-0">
																									<td className="py-1 pr-2 max-w-[140px] truncate" title={d.query}>
																										{d.query}
																									</td>
																									<td className={`py-1 pr-2 font-mono ${d.winner === "nexus" ? "text-green-700 font-medium" : "text-muted-foreground"}`}>
																										{d.nexus_tool}
																									</td>
																									<td className={`py-1 pr-2 font-mono ${d.winner === "llm" ? "text-green-700 font-medium" : "text-muted-foreground"}`}>
																										{d.llm_tool}
																									</td>
																									<td className="py-1 pr-2 font-mono text-muted-foreground">
																										{d.expected_tool}
																									</td>
																									<td className="py-1 pr-2">
																										{d.winner === "nexus" && (
																											<span className="text-blue-600 font-medium">NEXUS</span>
																										)}
																										{d.winner === "llm" && (
																											<span className="text-purple-600 font-medium">LLM</span>
																										)}
																										{d.winner === "neither" && (
																											<span className="text-red-500">Ingen</span>
																										)}
																										{d.winner === "tie" && (
																											<span className="text-muted-foreground">—</span>
																										)}
																									</td>
																									<td className="py-1 max-w-[180px] truncate text-muted-foreground" title={d.reasoning}>
																										{d.reasoning}
																									</td>
																								</tr>
																							))}
																						</tbody>
																					</table>
																				</div>
																			</div>
																		)}
																	</CardContent>
																</Card>
															)}

															{/* Iteration details */}
															{detail.iterations &&
																detail.iterations.length > 0 && (
																	<Card>
																		<CardHeader className="py-3 px-4">
																			<CardTitle className="text-sm">
																				Iterationer ({detail.iterations.length})
																			</CardTitle>
																		</CardHeader>
																		<CardContent className="px-4 pb-4">
																			<div className="space-y-2">
																				{detail.iterations.map((iter) => (
																					<div
																						key={iter.iteration}
																						className="flex items-center justify-between text-sm rounded-md border bg-background p-2"
																					>
																						<span className="font-medium">
																							Iteration {iter.iteration}
																						</span>
																						<div className="flex items-center gap-3 text-xs text-muted-foreground">
																							<span>
																								{iter.failures}/{iter.total_tests} fel
																							</span>
																							<span>
																								P@1: {(iter.precision_at_1 * 100).toFixed(1)}%
																							</span>
																							<span>
																								MRR: {(iter.mrr * 100).toFixed(1)}%
																							</span>
																							{iter.intent_accuracy != null && (
																								<span className="text-indigo-600">
																									Intent: {(iter.intent_accuracy * 100).toFixed(1)}%
																								</span>
																							)}
																							{iter.agent_accuracy != null && (
																								<span className="text-violet-600">
																									Agent: {(iter.agent_accuracy * 100).toFixed(1)}%
																								</span>
																							)}
																							{iter.llm_judge_agreement_rate != null && (
																								<span>
																									LLM-agree: {Math.round(iter.llm_judge_agreement_rate * 100)}%
																								</span>
																							)}
																						</div>
																					</div>
																				))}
																			</div>
																		</CardContent>
																	</Card>
																)}
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
