"use client";

/**
 * Eval & Audit Panel — Panel 4
 *
 * Unified eval flow with batch/parallel execution support.
 * Three action cards: Audit, Eval, Auto-Loop — each runnable independently.
 * Batch mode: run multiple eval categories in parallel.
 */

import { useQuery } from "@tanstack/react-query";
import {
	AlertCircle,
	CheckCircle2,
	FlaskConical,
	Layers,
	Loader2,
	Play,
	RotateCcw,
	XCircle,
	Zap,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { EvalJobStatusCard } from "@/components/admin/shared/eval-job-status-card";
import { formatPercent, useToolCatalog } from "@/components/admin/tools/hooks/use-tool-catalog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EvalType = "tool_selection" | "api_input";
type GenerationMode = "category" | "provider" | "global_random";
type DifficultyProfile = "blandad" | "lätt" | "medel" | "svår";

interface BatchJob {
	id: string;
	categoryId: string;
	jobId: string | null;
	status: "pending" | "running" | "completed" | "failed";
	successRate: number | null;
	error: string | null;
}

// ---------------------------------------------------------------------------
// Audit section
// ---------------------------------------------------------------------------

function AuditSection({ searchSpaceId }: { searchSpaceId: number | undefined }) {
	const [isRunning, setIsRunning] = useState(false);
	const [maxTools, setMaxTools] = useState(50);
	const [retrievalLimit, setRetrievalLimit] = useState(10);
	const [includeDraft, setIncludeDraft] = useState(false);
	const [result, setResult] = useState<Record<string, unknown> | null>(null);

	const runAudit = useCallback(async () => {
		setIsRunning(true);
		try {
			const response = await adminToolSettingsApiService.runMetadataCatalogAudit({
				search_space_id: searchSpaceId,
				max_tools: maxTools,
				retrieval_limit: retrievalLimit,
				include_draft_metadata: includeDraft,
			});
			setResult(response as Record<string, unknown>);
			toast.success("Metadata-audit klar");
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Audit misslyckades");
		} finally {
			setIsRunning(false);
		}
	}, [searchSpaceId, maxTools, retrievalLimit, includeDraft]);

	const summary = result?.summary as Record<string, unknown> | undefined;

	return (
		<Card>
			<CardHeader className="pb-3">
				<div className="flex items-center gap-2">
					<Layers className="h-4 w-4" />
					<CardTitle className="text-base">Metadata Audit</CardTitle>
				</div>
				<CardDescription>
					3-lager-audit: intent-accuracy, agent-accuracy, tool-accuracy. Hittar kollisioner och
					förvirring i metadata.
				</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				<div className="grid gap-4 md:grid-cols-3">
					<div className="space-y-1">
						<Label className="text-xs">Max verktyg</Label>
						<Input
							type="number"
							min={10}
							max={200}
							value={maxTools}
							onChange={(e) => setMaxTools(Number.parseInt(e.target.value || "50", 10))}
							className="h-8"
						/>
					</div>
					<div className="space-y-1">
						<Label className="text-xs">Retrieval-limit</Label>
						<Input
							type="number"
							min={3}
							max={50}
							value={retrievalLimit}
							onChange={(e) => setRetrievalLimit(Number.parseInt(e.target.value || "10", 10))}
							className="h-8"
						/>
					</div>
					<div className="flex items-end gap-2 pb-1">
						<Switch checked={includeDraft} onCheckedChange={setIncludeDraft} />
						<Label className="text-xs">Inkludera utkast</Label>
					</div>
				</div>

				<Button onClick={runAudit} disabled={isRunning} className="gap-2">
					{isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
					Kör audit
				</Button>

				{summary && (
					<div className="space-y-3">
						<div className="grid gap-3 grid-cols-3">
							<div className="rounded border p-3 text-center">
								<p className="text-xs text-muted-foreground">Intent</p>
								<p className="text-xl font-bold tabular-nums">
									{formatPercent(summary.intent_accuracy as number)}
								</p>
							</div>
							<div className="rounded border p-3 text-center">
								<p className="text-xs text-muted-foreground">Agent</p>
								<p className="text-xl font-bold tabular-nums">
									{formatPercent(summary.agent_accuracy as number)}
								</p>
							</div>
							<div className="rounded border p-3 text-center">
								<p className="text-xs text-muted-foreground">Tool</p>
								<p className="text-xl font-bold tabular-nums">
									{formatPercent(summary.tool_accuracy as number)}
								</p>
							</div>
						</div>
						{summary.tool_confusion_matrix && (
							<div>
								<p className="text-xs font-medium text-muted-foreground mb-1">
									Kollisioner (top 5)
								</p>
								<div className="space-y-1">
									{(
										summary.tool_confusion_matrix as Array<{
											predicted: string;
											expected: string;
											count: number;
										}>
									)
										.slice(0, 5)
										.map((pair, i) => (
											<div
												key={`collision-${i}`}
												className="flex items-center justify-between text-xs border rounded px-2 py-1"
											>
												<span className="font-mono">
													{pair.predicted} ↔ {pair.expected}
												</span>
												<Badge variant="secondary" className="text-xs">
													{pair.count}x
												</Badge>
											</div>
										))}
								</div>
							</div>
						)}
					</div>
				)}
			</CardContent>
		</Card>
	);
}

// ---------------------------------------------------------------------------
// Eval section with batch/parallel
// ---------------------------------------------------------------------------

function EvalSection({ searchSpaceId }: { searchSpaceId: number | undefined }) {
	const [evalType, setEvalType] = useState<EvalType>("tool_selection");
	const [genMode, _setGenMode] = useState<GenerationMode>("category");
	const [categoryId, _setCategoryId] = useState("");
	const [questionCount, setQuestionCount] = useState(12);
	const [difficulty, setDifficulty] = useState<DifficultyProfile>("blandad");
	const [evalName, setEvalName] = useState("");
	const [testCasesJson, setTestCasesJson] = useState("");
	const [isGenerating, setIsGenerating] = useState(false);
	const [isRunning, setIsRunning] = useState(false);
	const [jobId, setJobId] = useState<string | null>(null);
	const [jobStatus, setJobStatus] = useState<Record<string, unknown> | null>(null);

	// Batch/parallel state
	const [batchEnabled, setBatchEnabled] = useState(false);
	const [batchCategories, setBatchCategories] = useState<string[]>([]);
	const [parallelCount, setParallelCount] = useState(3);
	const [batchJobs, setBatchJobs] = useState<BatchJob[]>([]);
	const [isBatchRunning, setIsBatchRunning] = useState(false);

	const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

	const { data: apiCategories } = useQuery({
		queryKey: ["admin-tool-api-categories", searchSpaceId],
		queryFn: () => adminToolSettingsApiService.getToolApiCategories(searchSpaceId),
		enabled: typeof searchSpaceId === "number",
	});

	const categories =
		(
			apiCategories as {
				providers?: Array<{ provider_key: string; categories?: Array<{ category_id: string }> }>;
			}
		)?.providers?.flatMap((p) => p.categories?.map((c) => c.category_id) ?? []) ?? [];

	// Cleanup on unmount
	useEffect(() => {
		return () => {
			if (pollRef.current) clearInterval(pollRef.current);
		};
	}, []);

	// Poll job status
	useEffect(() => {
		if (!jobId || !isRunning) return;

		const poll = async () => {
			try {
				let status: Record<string, unknown>;
				if (evalType === "tool_selection") {
					status = (await adminToolSettingsApiService.getToolEvaluationStatus(jobId)) as Record<
						string,
						unknown
					>;
				} else {
					status = (await adminToolSettingsApiService.getToolApiInputEvaluationStatus(
						jobId
					)) as Record<string, unknown>;
				}
				setJobStatus(status);

				if (status.status === "completed" || status.status === "failed") {
					setIsRunning(false);
					if (pollRef.current) clearInterval(pollRef.current);
					if (status.status === "completed") {
						toast.success(`Eval klar: ${formatPercent(status.success_rate as number)}`);
					} else {
						toast.error(`Eval misslyckades: ${status.error || "Okänt fel"}`);
					}
				}
			} catch {
				// Ignore poll errors
			}
		};

		pollRef.current = setInterval(poll, 3000);
		poll(); // Initial poll

		return () => {
			if (pollRef.current) clearInterval(pollRef.current);
		};
	}, [jobId, isRunning, evalType]);

	const generateTests = useCallback(async () => {
		setIsGenerating(true);
		try {
			const response = await adminToolSettingsApiService.generateEvalLibraryFile({
				mode: genMode,
				category_id: categoryId || undefined,
				question_count: questionCount,
				difficulty_profile: difficulty,
				search_space_id: searchSpaceId,
			});
			const generated = response as { test_cases?: unknown[] };
			if (generated.test_cases) {
				setTestCasesJson(JSON.stringify(generated.test_cases, null, 2));
				toast.success(`Genererade ${generated.test_cases.length} testfall`);
			}
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Generering misslyckades");
		} finally {
			setIsGenerating(false);
		}
	}, [genMode, categoryId, questionCount, difficulty, searchSpaceId]);

	const runEval = useCallback(async () => {
		setIsRunning(true);
		setJobStatus(null);
		try {
			let testCases: unknown[] | undefined;
			if (testCasesJson.trim()) {
				testCases = JSON.parse(testCasesJson);
			}

			let response: Record<string, unknown>;
			if (evalType === "tool_selection") {
				response = (await adminToolSettingsApiService.startToolEvaluation({
					test_cases: testCases,
					eval_name: evalName || undefined,
					search_space_id: searchSpaceId,
				})) as Record<string, unknown>;
			} else {
				response = (await adminToolSettingsApiService.startToolApiInputEvaluation({
					test_cases: testCases,
					eval_name: evalName || undefined,
					search_space_id: searchSpaceId,
				})) as Record<string, unknown>;
			}
			setJobId(response.job_id as string);
			toast.info("Eval startad — polling pågår...");
		} catch (error) {
			setIsRunning(false);
			toast.error(error instanceof Error ? error.message : "Eval-start misslyckades");
		}
	}, [testCasesJson, evalType, evalName, searchSpaceId]);

	// Batch/parallel execution
	const runBatch = useCallback(async () => {
		if (batchCategories.length === 0) {
			toast.error("Välj minst en kategori för batch-körning");
			return;
		}

		setIsBatchRunning(true);
		const jobs: BatchJob[] = batchCategories.map((catId, i) => ({
			id: `batch-${i}`,
			categoryId: catId,
			jobId: null,
			status: "pending",
			successRate: null,
			error: null,
		}));
		setBatchJobs(jobs);

		// Run in parallel batches
		const runOne = async (job: BatchJob): Promise<BatchJob> => {
			try {
				job.status = "running";
				setBatchJobs((prev) => prev.map((j) => (j.id === job.id ? { ...job } : j)));

				const response = (await adminToolSettingsApiService.startToolEvaluation({
					eval_name: `batch-${job.categoryId}`,
					category_id: job.categoryId,
					question_count: questionCount,
					difficulty_profile: difficulty,
					search_space_id: searchSpaceId,
				})) as Record<string, unknown>;

				job.jobId = response.job_id as string;

				// Poll until done
				let done = false;
				while (!done) {
					await new Promise((r) => setTimeout(r, 3000));
					const status = (await adminToolSettingsApiService.getToolEvaluationStatus(
						job.jobId as string
					)) as Record<string, unknown>;

					if (status.status === "completed") {
						job.status = "completed";
						job.successRate = status.success_rate as number;
						done = true;
					} else if (status.status === "failed") {
						job.status = "failed";
						job.error = (status.error as string) || "Okänt fel";
						done = true;
					}
				}
			} catch (error) {
				job.status = "failed";
				job.error = error instanceof Error ? error.message : "Okänt fel";
			}

			setBatchJobs((prev) => prev.map((j) => (j.id === job.id ? { ...job } : j)));
			return job;
		};

		// Process in parallel chunks
		const chunks: BatchJob[][] = [];
		for (let i = 0; i < jobs.length; i += parallelCount) {
			chunks.push(jobs.slice(i, i + parallelCount));
		}

		for (const chunk of chunks) {
			await Promise.all(chunk.map(runOne));
		}

		const completed = jobs.filter((j) => j.status === "completed").length;
		const failed = jobs.filter((j) => j.status === "failed").length;
		toast.success(`Batch klar: ${completed} lyckades, ${failed} misslyckades`);
		setIsBatchRunning(false);
	}, [batchCategories, parallelCount, questionCount, difficulty, searchSpaceId]);

	const toggleBatchCategory = (catId: string) => {
		setBatchCategories((prev) =>
			prev.includes(catId) ? prev.filter((c) => c !== catId) : [...prev, catId]
		);
	};

	return (
		<Card>
			<CardHeader className="pb-3">
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-2">
						<FlaskConical className="h-4 w-4" />
						<CardTitle className="text-base">Evaluering</CardTitle>
					</div>
					<div className="flex items-center gap-3">
						<div className="flex items-center gap-2">
							<Switch checked={batchEnabled} onCheckedChange={setBatchEnabled} />
							<Label className="text-xs">Batch/Parallell</Label>
						</div>
					</div>
				</div>
				<CardDescription>
					{batchEnabled
						? "Kör eval på flera kategorier parallellt. Välj kategorier och parallellitetsgrad."
						: "Generera testfall, kör eval, se resultat per fråga."}
				</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				{/* Eval type and generation config */}
				<div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
					<div className="space-y-1">
						<Label className="text-xs">Eval-typ</Label>
						<Select value={evalType} onValueChange={(v) => setEvalType(v as EvalType)}>
							<SelectTrigger className="h-8 text-xs">
								<SelectValue />
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="tool_selection">Verktygsval</SelectItem>
								<SelectItem value="api_input">API Input</SelectItem>
							</SelectContent>
						</Select>
					</div>
					<div className="space-y-1">
						<Label className="text-xs">Frågor</Label>
						<Input
							type="number"
							min={3}
							max={50}
							value={questionCount}
							onChange={(e) => setQuestionCount(Number.parseInt(e.target.value || "12", 10))}
							className="h-8"
						/>
					</div>
					<div className="space-y-1">
						<Label className="text-xs">Svårighet</Label>
						<Select value={difficulty} onValueChange={(v) => setDifficulty(v as DifficultyProfile)}>
							<SelectTrigger className="h-8 text-xs">
								<SelectValue />
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="blandad">Blandad</SelectItem>
								<SelectItem value="lätt">Lätt</SelectItem>
								<SelectItem value="medel">Medel</SelectItem>
								<SelectItem value="svår">Svår</SelectItem>
							</SelectContent>
						</Select>
					</div>
					<div className="space-y-1">
						<Label className="text-xs">Eval-namn</Label>
						<Input
							value={evalName}
							onChange={(e) => setEvalName(e.target.value)}
							placeholder="Valfritt namn"
							className="h-8 text-xs"
						/>
					</div>
				</div>

				{/* Batch mode */}
				{batchEnabled && (
					<>
						<Separator />
						<div className="space-y-3">
							<div className="flex items-center gap-4">
								<div className="flex items-center gap-2">
									<Zap className="h-4 w-4 text-amber-500" />
									<Label className="text-sm font-medium">Batch-inställningar</Label>
								</div>
								<div className="flex items-center gap-2">
									<Label className="text-xs">Parallella jobb:</Label>
									<Input
										type="number"
										min={1}
										max={10}
										value={parallelCount}
										onChange={(e) => setParallelCount(Number.parseInt(e.target.value || "3", 10))}
										className="h-7 w-16 text-xs"
									/>
								</div>
							</div>
							<p className="text-xs text-muted-foreground">
								Välj kategorier att köra eval på. De körs i parallella batchar om {parallelCount} åt
								gången.
							</p>
							<div className="flex flex-wrap gap-1.5">
								{categories.map((catId) => (
									<Badge
										key={catId}
										variant={batchCategories.includes(catId) ? "default" : "outline"}
										className="cursor-pointer text-xs"
										onClick={() => toggleBatchCategory(catId)}
									>
										{catId}
									</Badge>
								))}
								{categories.length === 0 && (
									<span className="text-xs text-muted-foreground">
										Inga kategorier tillgängliga
									</span>
								)}
							</div>
							{batchCategories.length > 0 && (
								<p className="text-xs text-muted-foreground">
									{batchCategories.length} kategorier valda
								</p>
							)}
							<Button
								onClick={runBatch}
								disabled={isBatchRunning || batchCategories.length === 0}
								className="gap-2"
							>
								{isBatchRunning ? (
									<Loader2 className="h-4 w-4 animate-spin" />
								) : (
									<Zap className="h-4 w-4" />
								)}
								Kör batch ({batchCategories.length} kategorier)
							</Button>

							{/* Batch results */}
							{batchJobs.length > 0 && (
								<div className="space-y-1 max-h-64 overflow-auto">
									{batchJobs.map((job) => (
										<div
											key={job.id}
											className="flex items-center justify-between rounded border px-3 py-2 text-xs"
										>
											<span className="font-mono">{job.categoryId}</span>
											<div className="flex items-center gap-2">
												{job.status === "pending" && <Badge variant="outline">Väntar</Badge>}
												{job.status === "running" && (
													<Badge variant="secondary" className="gap-1">
														<Loader2 className="h-3 w-3 animate-spin" />
														Kör
													</Badge>
												)}
												{job.status === "completed" && (
													<Badge variant="default" className="gap-1 bg-emerald-600">
														<CheckCircle2 className="h-3 w-3" />
														{formatPercent(job.successRate)}
													</Badge>
												)}
												{job.status === "failed" && (
													<Badge variant="destructive" className="gap-1">
														<XCircle className="h-3 w-3" />
														Fel
													</Badge>
												)}
											</div>
										</div>
									))}
								</div>
							)}
						</div>
					</>
				)}

				{/* Single eval mode */}
				{!batchEnabled && (
					<>
						<Separator />

						{/* Test case input */}
						<div className="space-y-2">
							<div className="flex items-center justify-between">
								<Label className="text-xs">Testfall (JSON)</Label>
								<Button
									onClick={generateTests}
									disabled={isGenerating}
									size="sm"
									variant="outline"
									className="gap-1 h-7 text-xs"
								>
									{isGenerating ? (
										<Loader2 className="h-3 w-3 animate-spin" />
									) : (
										<Play className="h-3 w-3" />
									)}
									Generera
								</Button>
							</div>
							<Textarea
								value={testCasesJson}
								onChange={(e) => setTestCasesJson(e.target.value)}
								placeholder='[{"question": "...", "expected": {"tool": "...", "agent": "..."}}]'
								rows={6}
								className="font-mono text-xs"
							/>
						</div>

						<Button onClick={runEval} disabled={isRunning} className="gap-2">
							{isRunning ? (
								<Loader2 className="h-4 w-4 animate-spin" />
							) : (
								<FlaskConical className="h-4 w-4" />
							)}
							Kör eval
						</Button>

						{/* Job status */}
						{jobId && jobStatus && (
							<EvalJobStatusCard
								title={`Eval: ${evalName || jobId}`}
								jobId={jobId}
								status={jobStatus.status as string}
								completedTests={jobStatus.completed_tests as number}
								totalTests={jobStatus.total_tests as number}
								error={jobStatus.error as string}
								caseStatuses={
									(jobStatus.case_statuses as Array<{
										test_id: string;
										status: string;
										question: string;
										passed?: boolean;
										error?: string;
										selected_route?: string;
										selected_sub_route?: string;
										selected_agent?: string;
										selected_tool?: string;
									}>) ?? []
								}
								onExportJson={() => {
									const blob = new Blob([JSON.stringify(jobStatus, null, 2)], {
										type: "application/json",
									});
									const url = URL.createObjectURL(blob);
									const a = document.createElement("a");
									a.href = url;
									a.download = `eval-${jobId}.json`;
									a.click();
									URL.revokeObjectURL(url);
								}}
								onExportYaml={() => {
									toast.info("YAML-export stöds i nästa version");
								}}
								exportDisabled={jobStatus.status !== "completed"}
							/>
						)}
					</>
				)}
			</CardContent>
		</Card>
	);
}

// ---------------------------------------------------------------------------
// Auto-loop section
// ---------------------------------------------------------------------------

function AutoLoopSection({ searchSpaceId }: { searchSpaceId: number | undefined }) {
	const [targetRate, setTargetRate] = useState(0.85);
	const [maxIterations, setMaxIterations] = useState(6);
	const [patience, setPatience] = useState(2);
	const [minDelta, setMinDelta] = useState(0.005);
	const [isRunning, setIsRunning] = useState(false);
	const [jobId, setJobId] = useState<string | null>(null);
	const [jobStatus, setJobStatus] = useState<Record<string, unknown> | null>(null);
	const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

	useEffect(() => {
		return () => {
			if (pollRef.current) clearInterval(pollRef.current);
		};
	}, []);

	useEffect(() => {
		if (!jobId || !isRunning) return;

		const poll = async () => {
			try {
				const status = (await adminToolSettingsApiService.getToolAutoLoopStatus(jobId)) as Record<
					string,
					unknown
				>;
				setJobStatus(status);

				if (status.status === "completed" || status.status === "failed") {
					setIsRunning(false);
					if (pollRef.current) clearInterval(pollRef.current);
					if (status.status === "completed") {
						toast.success("Auto-loop klar");
					}
				}
			} catch {
				// Ignore
			}
		};

		pollRef.current = setInterval(poll, 5000);
		poll();

		return () => {
			if (pollRef.current) clearInterval(pollRef.current);
		};
	}, [jobId, isRunning]);

	const start = useCallback(async () => {
		setIsRunning(true);
		setJobStatus(null);
		try {
			const response = (await adminToolSettingsApiService.startToolAutoLoop({
				target_success_rate: targetRate,
				max_iterations: maxIterations,
				patience,
				min_improvement_delta: minDelta,
				search_space_id: searchSpaceId,
			})) as Record<string, unknown>;
			setJobId(response.job_id as string);
			toast.info("Auto-loop startad");
		} catch (error) {
			setIsRunning(false);
			toast.error(error instanceof Error ? error.message : "Auto-loop misslyckades");
		}
	}, [targetRate, maxIterations, patience, minDelta, searchSpaceId]);

	const iterations = (jobStatus?.iterations as Array<Record<string, unknown>>) ?? [];

	return (
		<Card>
			<CardHeader className="pb-3">
				<div className="flex items-center gap-2">
					<RotateCcw className="h-4 w-4" />
					<CardTitle className="text-base">Auto-optimering</CardTitle>
				</div>
				<CardDescription>
					Iterativ loop: eval → suggestions → apply → re-eval. Stannar vid target rate eller
					patience-gräns.
				</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				<div className="grid gap-4 md:grid-cols-4">
					<div className="space-y-1">
						<Label className="text-xs">Target success rate</Label>
						<Input
							type="number"
							step={0.01}
							min={0.5}
							max={1}
							value={targetRate}
							onChange={(e) => setTargetRate(Number.parseFloat(e.target.value || "0.85"))}
							className="h-8"
						/>
					</div>
					<div className="space-y-1">
						<Label className="text-xs">Max iterationer</Label>
						<Input
							type="number"
							min={1}
							max={20}
							value={maxIterations}
							onChange={(e) => setMaxIterations(Number.parseInt(e.target.value || "6", 10))}
							className="h-8"
						/>
					</div>
					<div className="space-y-1">
						<Label className="text-xs">Patience</Label>
						<Input
							type="number"
							min={1}
							max={10}
							value={patience}
							onChange={(e) => setPatience(Number.parseInt(e.target.value || "2", 10))}
							className="h-8"
						/>
					</div>
					<div className="space-y-1">
						<Label className="text-xs">Min förbättring (δ)</Label>
						<Input
							type="number"
							step={0.001}
							min={0}
							max={0.1}
							value={minDelta}
							onChange={(e) => setMinDelta(Number.parseFloat(e.target.value || "0.005"))}
							className="h-8"
						/>
					</div>
				</div>

				<Button onClick={start} disabled={isRunning} className="gap-2">
					{isRunning ? (
						<Loader2 className="h-4 w-4 animate-spin" />
					) : (
						<RotateCcw className="h-4 w-4" />
					)}
					Starta auto-loop
				</Button>

				{/* Loop progress */}
				{jobStatus && (
					<div className="space-y-2">
						<div className="flex items-center gap-2">
							<Badge variant={jobStatus.status === "completed" ? "default" : "secondary"}>
								{jobStatus.status as string}
							</Badge>
							<span className="text-xs text-muted-foreground">{iterations.length} iterationer</span>
						</div>
						{iterations.length > 0 && (
							<div className="space-y-1 max-h-48 overflow-auto">
								{iterations.map((iter, i) => (
									<div
										key={`iter-${i}`}
										className="flex items-center justify-between rounded border px-3 py-1.5 text-xs"
									>
										<span>Iteration {i + 1}</span>
										<div className="flex items-center gap-2">
											<span className="tabular-nums">
												{formatPercent(iter.success_rate as number)}
											</span>
											{(iter.success_rate as number) >= targetRate ? (
												<CheckCircle2 className="h-3 w-3 text-emerald-600" />
											) : (
												<AlertCircle className="h-3 w-3 text-amber-600" />
											)}
										</div>
									</div>
								))}
							</div>
						)}
					</div>
				)}
			</CardContent>
		</Card>
	);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function EvalPanel() {
	const { searchSpaceId, isLoading } = useToolCatalog();

	if (isLoading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	return (
		<div className="space-y-6">
			<AuditSection searchSpaceId={searchSpaceId} />
			<EvalSection searchSpaceId={searchSpaceId} />
			<AutoLoopSection searchSpaceId={searchSpaceId} />
		</div>
	);
}
