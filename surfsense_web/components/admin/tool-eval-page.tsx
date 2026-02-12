"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { adminToolEvalApiService } from "@/lib/apis/admin-tool-eval-api.service";
import type {
	SingleQueryRequest,
	SingleQueryResponse,
	EvalRunResponse,
	CategoryResult,
	ScoringDetail,
} from "@/contracts/types/admin-tool-eval.types";

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
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import {
	FlaskConical,
	Upload,
	Play,
	CheckCircle2,
	XCircle,
	AlertCircle,
	Clock,
	Loader2,
	RotateCcw,
	TrendingUp,
	Target,
} from "lucide-react";

export function ToolEvalPage() {
	const [singleQuery, setSingleQuery] = useState("");
	const [expectedTools, setExpectedTools] = useState("");
	const [singleResult, setSingleResult] = useState<SingleQueryResponse | null>(
		null
	);

	const [selectedFile, setSelectedFile] = useState<File | null>(null);
	const [evalReport, setEvalReport] = useState<EvalRunResponse | null>(null);

	const queryClient = useQueryClient();

	// Mutation for testing single query
	const testSingleMutation = useMutation({
		mutationFn: (request: SingleQueryRequest) =>
			adminToolEvalApiService.testSingleQuery(request),
		onSuccess: (data) => {
			setSingleResult(data);
			toast.success("Query testad framgångsrikt");
		},
		onError: (error: Error) => {
			toast.error(`Fel vid testning: ${error.message}`);
		},
	});

	// Mutation for running eval suite
	const runEvalMutation = useMutation({
		mutationFn: (file: File) => adminToolEvalApiService.runEvalSuite(file),
		onSuccess: (data) => {
			setEvalReport(data);
			toast.success("Utvärdering slutförd!");
		},
		onError: (error: Error) => {
			toast.error(`Fel vid utvärdering: ${error.message}`);
		},
	});

	// Mutation for invalidating cache
	const invalidateCacheMutation = useMutation({
		mutationFn: () => adminToolEvalApiService.invalidateCache(),
		onSuccess: () => {
			toast.success("Cache rensad");
		},
		onError: (error: Error) => {
			toast.error(`Fel vid cacherensning: ${error.message}`);
		},
	});

	const handleTestSingle = () => {
		if (!singleQuery.trim()) {
			toast.error("Ange en query");
			return;
		}

		const request: SingleQueryRequest = {
			query: singleQuery,
			expected_tools: expectedTools
				? expectedTools.split(",").map((t) => t.trim())
				: null,
			limit: 2,
		};

		testSingleMutation.mutate(request);
	};

	const handleRunEval = () => {
		if (!selectedFile) {
			toast.error("Välj en JSON-fil");
			return;
		}

		runEvalMutation.mutate(selectedFile);
	};

	const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		const file = e.target.files?.[0];
		if (file) {
			setSelectedFile(file);
		}
	};

	const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`;
	const formatMs = (value: number) => `${value.toFixed(0)}ms`;

	return (
		<div className="space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
						<FlaskConical className="h-8 w-8" />
						Tool Evaluation
					</h1>
					<p className="text-muted-foreground mt-1">
						Utvärdera och testa verktygsval utan riktiga API-anrop
					</p>
				</div>
				<Button
					variant="outline"
					size="sm"
					onClick={() => invalidateCacheMutation.mutate()}
					disabled={invalidateCacheMutation.isPending}
				>
					{invalidateCacheMutation.isPending ? (
						<Loader2 className="h-4 w-4 animate-spin" />
					) : (
						<RotateCcw className="h-4 w-4" />
					)}
					<span className="ml-2">Rensa Cache</span>
				</Button>
			</div>

			<Tabs defaultValue="single" className="space-y-4">
				<TabsList>
					<TabsTrigger value="single">Single Query Tester</TabsTrigger>
					<TabsTrigger value="suite">Suite Upload</TabsTrigger>
				</TabsList>

				{/* Single Query Tester */}
				<TabsContent value="single" className="space-y-4">
					<Card>
						<CardHeader>
							<CardTitle>Testa Enskild Query</CardTitle>
							<CardDescription>
								Testa hur systemet väljer verktyg för en specifik query
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="space-y-2">
								<Label htmlFor="single-query">Query</Label>
								<Input
									id="single-query"
									placeholder="Finns det några trafikstörningar på E4?"
									value={singleQuery}
									onChange={(e) => setSingleQuery(e.target.value)}
									onKeyDown={(e) => {
										if (e.key === "Enter") {
											handleTestSingle();
										}
									}}
								/>
							</div>

							<div className="space-y-2">
								<Label htmlFor="expected-tools">
									Förväntade Verktyg (valfritt, kommaseparerade)
								</Label>
								<Input
									id="expected-tools"
									placeholder="trafikverket_trafikinfo_storningar, trafikverket_trafikinfo_koer"
									value={expectedTools}
									onChange={(e) => setExpectedTools(e.target.value)}
								/>
							</div>

							<Button
								onClick={handleTestSingle}
								disabled={testSingleMutation.isPending}
								className="w-full"
							>
								{testSingleMutation.isPending ? (
									<>
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
										Testar...
									</>
								) : (
									<>
										<Play className="mr-2 h-4 w-4" />
										Testa
									</>
								)}
							</Button>
						</CardContent>
					</Card>

					{/* Single Query Results */}
					{singleResult && (
						<Card>
							<CardHeader>
								<CardTitle>Resultat</CardTitle>
								<CardDescription>
									Query: {singleResult.query}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								{/* Match Type Badge */}
								{singleResult.match_type && (
									<div className="flex items-center gap-2">
										<span className="text-sm font-medium">Match:</span>
										<Badge
											variant={
												singleResult.match_type === "exact_match"
													? "default"
													: singleResult.match_type === "partial_match"
													? "secondary"
													: "destructive"
											}
										>
											{singleResult.match_type}
										</Badge>
									</div>
								)}

								{/* Selected Tools */}
								<div className="space-y-2">
									<Label>Valda Verktyg</Label>
									<div className="flex flex-wrap gap-2">
										{singleResult.selected_tools.map((tool) => (
											<Badge key={tool} variant="outline">
												{tool}
											</Badge>
										))}
									</div>
								</div>

								{/* Latency */}
								<div className="flex items-center gap-2 text-sm text-muted-foreground">
									<Clock className="h-4 w-4" />
									<span>{formatMs(singleResult.latency_ms)}</span>
								</div>

								{/* Scoring Details */}
								<div className="space-y-2">
									<Label>Poängsättning</Label>
									<div className="rounded-md border">
										<Table>
											<TableHeader>
												<TableRow>
													<TableHead>Verktyg</TableHead>
													<TableHead>Base</TableHead>
													<TableHead>Semantic</TableHead>
													<TableHead>Total</TableHead>
													<TableHead>Nyckelord</TableHead>
												</TableRow>
											</TableHeader>
											<TableBody>
												{singleResult.scoring_details.map((detail) => (
													<TableRow key={detail.tool_id}>
														<TableCell className="font-medium">
															{detail.name}
														</TableCell>
														<TableCell>
															{detail.base_score.toFixed(1)}
														</TableCell>
														<TableCell>
															{detail.semantic_score.toFixed(2)}
														</TableCell>
														<TableCell className="font-semibold">
															{detail.total_score.toFixed(2)}
														</TableCell>
														<TableCell>
															<div className="flex flex-wrap gap-1">
																{detail.keywords_matched.map((kw) => (
																	<Badge
																		key={kw}
																		variant="secondary"
																		className="text-xs"
																	>
																		{kw}
																	</Badge>
																))}
															</div>
														</TableCell>
													</TableRow>
												))}
											</TableBody>
										</Table>
									</div>
								</div>
							</CardContent>
						</Card>
					)}
				</TabsContent>

				{/* Suite Upload */}
				<TabsContent value="suite" className="space-y-4">
					<Card>
						<CardHeader>
							<CardTitle>Ladda Upp Testsvit</CardTitle>
							<CardDescription>
								Ladda upp en JSON-fil med testsuite för fullständig utvärdering
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="space-y-2">
								<Label htmlFor="file-upload">Välj JSON-fil</Label>
								<Input
									id="file-upload"
									type="file"
									accept=".json"
									onChange={handleFileChange}
								/>
								{selectedFile && (
									<p className="text-sm text-muted-foreground">
										Vald fil: {selectedFile.name}
									</p>
								)}
							</div>

							<Button
								onClick={handleRunEval}
								disabled={runEvalMutation.isPending || !selectedFile}
								className="w-full"
							>
								{runEvalMutation.isPending ? (
									<>
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
										Kör utvärdering...
									</>
								) : (
									<>
										<Upload className="mr-2 h-4 w-4" />
										Kör Utvärdering
									</>
								)}
							</Button>
						</CardContent>
					</Card>

					{/* Evaluation Results */}
					{evalReport && (
						<div className="space-y-4">
							{/* Summary Cards */}
							<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
								<Card>
									<CardHeader className="pb-2">
										<CardTitle className="text-sm font-medium">
											Tool Exact Rate
										</CardTitle>
									</CardHeader>
									<CardContent>
										<div className="text-2xl font-bold">
											{formatPercent(evalReport.overall_tool_exact_rate)}
										</div>
										<p className="text-xs text-muted-foreground mt-1">
											{evalReport.total_tests} totala tester
										</p>
									</CardContent>
								</Card>

								<Card>
									<CardHeader className="pb-2">
										<CardTitle className="text-sm font-medium">
											Tool Acceptable Rate
										</CardTitle>
									</CardHeader>
									<CardContent>
										<div className="text-2xl font-bold">
											{formatPercent(evalReport.overall_tool_acceptable_rate)}
										</div>
										<p className="text-xs text-muted-foreground mt-1">
											Inkl. acceptabla verktyg
										</p>
									</CardContent>
								</Card>

								<Card>
									<CardHeader className="pb-2">
										<CardTitle className="text-sm font-medium">
											Composite Score
										</CardTitle>
									</CardHeader>
									<CardContent>
										<div className="text-2xl font-bold">
											{formatPercent(evalReport.overall_avg_composite_score)}
										</div>
										<p className="text-xs text-muted-foreground mt-1">
											Viktad poäng över alla lager
										</p>
									</CardContent>
								</Card>

								<Card>
									<CardHeader className="pb-2">
										<CardTitle className="text-sm font-medium">
											Avg Latency
										</CardTitle>
									</CardHeader>
									<CardContent>
										<div className="text-2xl font-bold">
											{formatMs(evalReport.overall_avg_latency_ms)}
										</div>
										<p className="text-xs text-muted-foreground mt-1">
											Per query
										</p>
									</CardContent>
								</Card>
							</div>

							{/* Recommendations */}
							{evalReport.recommendations.length > 0 && (
								<Alert>
									<TrendingUp className="h-4 w-4" />
									<AlertDescription>
										<div className="font-semibold mb-2">Rekommendationer:</div>
										<ul className="list-disc list-inside space-y-1">
											{evalReport.recommendations.map((rec, idx) => (
												<li key={idx} className="text-sm">
													{rec}
												</li>
											))}
										</ul>
									</AlertDescription>
								</Alert>
							)}

							{/* Category Results Table */}
							<Card>
								<CardHeader>
									<CardTitle>Resultat per Kategori</CardTitle>
								</CardHeader>
								<CardContent>
									<div className="rounded-md border">
										<Table>
											<TableHeader>
												<TableRow>
													<TableHead>Kategori</TableHead>
													<TableHead>Tester</TableHead>
													<TableHead>Route Acc</TableHead>
													<TableHead>Tool Exact</TableHead>
													<TableHead>Tool Accept</TableHead>
													<TableHead>Comp. Score</TableHead>
													<TableHead>Latency</TableHead>
												</TableRow>
											</TableHeader>
											<TableBody>
												{evalReport.category_results.map((cat) => (
													<TableRow key={cat.category_id}>
														<TableCell className="font-medium">
															{cat.category_name}
														</TableCell>
														<TableCell>{cat.total_tests}</TableCell>
														<TableCell>
															{formatPercent(cat.route_accuracy)}
														</TableCell>
														<TableCell>
															{formatPercent(cat.tool_exact_rate)}
														</TableCell>
														<TableCell>
															{formatPercent(cat.tool_acceptable_rate)}
														</TableCell>
														<TableCell>
															{formatPercent(cat.avg_composite_score)}
														</TableCell>
														<TableCell>
															{formatMs(cat.avg_latency_ms)}
														</TableCell>
													</TableRow>
												))}
											</TableBody>
										</Table>
									</div>
								</CardContent>
							</Card>

							{/* By-Difficulty Breakdown */}
							{Object.keys(evalReport.by_difficulty).length > 0 && (
								<Card>
									<CardHeader>
										<CardTitle>Resultat per Svårighetsgrad</CardTitle>
									</CardHeader>
									<CardContent>
										<div className="rounded-md border">
											<Table>
												<TableHeader>
													<TableRow>
														<TableHead>Svårighetsgrad</TableHead>
														<TableHead>Totalt</TableHead>
														<TableHead>Tool Exact</TableHead>
														<TableHead>Tool Accept</TableHead>
														<TableHead>Comp. Score</TableHead>
													</TableRow>
												</TableHeader>
												<TableBody>
													{Object.entries(evalReport.by_difficulty).map(
														([difficulty, stats]) => (
															<TableRow key={difficulty}>
																<TableCell className="font-medium capitalize">
																	{difficulty}
																</TableCell>
																<TableCell>{stats.total}</TableCell>
																<TableCell>
																	{formatPercent(stats.tool_exact_rate)}
																</TableCell>
																<TableCell>
																	{formatPercent(stats.tool_acceptable_rate)}
																</TableCell>
																<TableCell>
																	{formatPercent(stats.avg_composite_score)}
																</TableCell>
															</TableRow>
														)
													)}
												</TableBody>
											</Table>
										</div>
									</CardContent>
								</Card>
							)}

							{/* Route Confusion Matrix */}
							{Object.keys(evalReport.route_confusion_matrix).length > 0 && (
								<Card>
									<CardHeader>
										<CardTitle>Route Confusion Matrix</CardTitle>
										<CardDescription>
											Visar hur routes klassificeras (rad = förväntat, kolumn =
											predicerat)
										</CardDescription>
									</CardHeader>
									<CardContent>
										<div className="rounded-md border overflow-x-auto">
											<Table>
												<TableHeader>
													<TableRow>
														<TableHead>Expected / Predicted</TableHead>
														{/* Get all unique routes */}
														{Array.from(
															new Set(
																Object.values(
																	evalReport.route_confusion_matrix
																).flatMap((row) => Object.keys(row))
															)
														).map((route) => (
															<TableHead key={route}>{route}</TableHead>
														))}
													</TableRow>
												</TableHeader>
												<TableBody>
													{Object.entries(
														evalReport.route_confusion_matrix
													).map(([expected, predictions]) => (
														<TableRow key={expected}>
															<TableCell className="font-medium">
																{expected}
															</TableCell>
															{Array.from(
																new Set(
																	Object.values(
																		evalReport.route_confusion_matrix
																	).flatMap((row) => Object.keys(row))
																)
															).map((route) => (
																<TableCell key={route}>
																	{predictions[route] || 0}
																</TableCell>
															))}
														</TableRow>
													))}
												</TableBody>
											</Table>
										</div>
									</CardContent>
								</Card>
							)}

							{/* Failure Patterns */}
							{Object.keys(evalReport.failure_patterns).length > 0 && (
								<Card>
									<CardHeader>
										<CardTitle>Failure Patterns (by Tag)</CardTitle>
										<CardDescription>
											Vanligaste tags bland misslyckade tester
										</CardDescription>
									</CardHeader>
									<CardContent>
										<div className="flex flex-wrap gap-2">
											{Object.entries(evalReport.failure_patterns)
												.sort(([, a], [, b]) => b - a)
												.slice(0, 15)
												.map(([tag, count]) => (
													<Badge key={tag} variant="destructive">
														{tag} ({count})
													</Badge>
												))}
										</div>
									</CardContent>
								</Card>
							)}

							{/* Failed Tests Details */}
							{evalReport.category_results.some(
								(cat) => cat.failed_tests.length > 0
							) && (
								<Card>
									<CardHeader>
										<CardTitle>Misslyckade Tester</CardTitle>
										<CardDescription>
											Detaljer om queries som inte matchade förväntade verktyg
										</CardDescription>
									</CardHeader>
									<CardContent>
										<Accordion type="single" collapsible className="w-full">
											{evalReport.category_results
												.filter((cat) => cat.failed_tests.length > 0)
												.map((cat) => (
													<AccordionItem
														key={cat.category_id}
														value={cat.category_id}
													>
														<AccordionTrigger>
															{cat.category_name} ({cat.failed_tests.length}{" "}
															failures)
														</AccordionTrigger>
														<AccordionContent>
															<div className="space-y-4">
																{cat.failed_tests.slice(0, 10).map((test: any) => (
																	<div
																		key={test.test_case_id}
																		className="border rounded-lg p-4 space-y-2"
																	>
																		<div className="font-medium">
																			{test.query}
																		</div>
																		<div className="text-sm space-y-1">
																			<div>
																				<span className="text-muted-foreground">
																					Selected:
																				</span>{" "}
																				{test.selected_tools.join(", ") ||
																					"none"}
																			</div>
																			{test.failure_reasons.length > 0 && (
																				<div className="text-destructive text-xs">
																					{test.failure_reasons.join(" • ")}
																				</div>
																			)}
																		</div>
																	</div>
																))}
															</div>
														</AccordionContent>
													</AccordionItem>
												))}
										</Accordion>
									</CardContent>
								</Card>
							)}
						</div>
					)}
				</TabsContent>
			</Tabs>
		</div>
	);
}
