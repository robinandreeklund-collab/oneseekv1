"use client";

/**
 * Pipeline Explorer — Panel 1
 *
 * Write a query and see in real-time which Intent, Agent, and Tool(s) would be
 * selected, with a full scoring breakdown per dimension.
 */

import { useAtomValue } from "jotai";
import { ArrowRight, CheckCircle2, Loader2, Minus, Play, Search, XCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import { useToolCatalog } from "@/components/admin/tools/hooks/use-tool-catalog";
import { Badge } from "@/components/ui/badge";
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
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";

// ---------------------------------------------------------------------------
// Types for debug response
// ---------------------------------------------------------------------------

interface DebugScoringDimension {
	name_match: number;
	keyword: number;
	description_token: number;
	example_query: number;
	embedding: number;
	namespace_boost: number;
	total: number;
}

interface DebugToolCandidate {
	tool_id: string;
	score: number;
	auto_selected: boolean;
	scoring?: DebugScoringDimension;
	rank: number;
}

interface DebugAgentCandidate {
	agent_id: string;
	score: number;
	auto_selected: boolean;
	rank: number;
}

interface DebugIntentResult {
	intent_id: string;
	route: string;
	confidence: number;
	graph_complexity: string;
}

interface DebugRetrievalResult {
	intent: DebugIntentResult | null;
	agents: DebugAgentCandidate[];
	tools: DebugToolCandidate[];
	thresholds: {
		tool_auto_score: number;
		tool_auto_margin: number;
		agent_auto_score: number;
		agent_auto_margin: number;
	} | null;
	timing_ms: number;
	error?: string;
}

// ---------------------------------------------------------------------------
// Confidence meter
// ---------------------------------------------------------------------------

function ConfidenceMeter({ value, label }: { value: number; label: string }) {
	const pct = Math.round(value * 100);
	const color = pct >= 80 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-red-500";

	return (
		<div className="space-y-1">
			<div className="flex items-center justify-between text-xs">
				<span className="text-muted-foreground">{label}</span>
				<span className="font-mono tabular-nums">{pct}%</span>
			</div>
			<div className="h-2 rounded-full bg-muted overflow-hidden">
				<div
					className={`h-full rounded-full transition-all duration-500 ${color}`}
					style={{ width: `${pct}%` }}
				/>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Pipeline step card
// ---------------------------------------------------------------------------

function PipelineStep({
	step,
	label,
	value,
	confidence,
	detail,
	isActive,
}: {
	step: number;
	label: string;
	value: string | null;
	confidence: number | null;
	detail?: string;
	isActive: boolean;
}) {
	return (
		<div
			className={`rounded-lg border p-4 space-y-2 transition-colors ${
				isActive ? "border-primary bg-primary/5" : "border-muted"
			}`}
		>
			<div className="flex items-center gap-2">
				<span className="flex items-center justify-center h-6 w-6 rounded-full bg-primary text-primary-foreground text-xs font-bold">
					{step}
				</span>
				<span className="text-sm font-medium">{label}</span>
			</div>
			{value ? (
				<>
					<p className="font-mono text-sm font-semibold">{value}</p>
					{confidence != null && <ConfidenceMeter value={confidence} label="Konfidensgrad" />}
					{detail && <p className="text-xs text-muted-foreground">{detail}</p>}
				</>
			) : (
				<p className="text-xs text-muted-foreground italic">Väntar på körning...</p>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function PipelineExplorerPanel() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const { searchSpaceId } = useToolCatalog();

	const [query, setQuery] = useState("");
	const [isRunning, setIsRunning] = useState(false);
	const [result, setResult] = useState<DebugRetrievalResult | null>(null);
	const [history, setHistory] = useState<
		Array<{ query: string; result: DebugRetrievalResult; ts: number }>
	>([]);

	const runDebug = useCallback(async () => {
		if (!query.trim() || !currentUser) return;

		setIsRunning(true);
		setResult(null);

		try {
			const response = await adminToolSettingsApiService.debugRetrieval({
				query: query.trim(),
				search_space_id: searchSpaceId,
			});

			if (response) {
				setResult(response as DebugRetrievalResult);
				setHistory((prev) => [
					{ query: query.trim(), result: response as DebugRetrievalResult, ts: Date.now() },
					...prev.slice(0, 9),
				]);
			} else {
				toast.info(
					"Inget resultat returnerat. Kontrollera att backend-endpointen /admin/tool-settings/debug-retrieval är implementerad."
				);
			}
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Kunde inte köra pipeline-debug");
		} finally {
			setIsRunning(false);
		}
	}, [query, currentUser, searchSpaceId]);

	const topAgent = result?.agents?.[0] ?? null;

	return (
		<div className="space-y-6">
			{/* Query input */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle>Testa retrieval-pipelinen</CardTitle>
					<CardDescription>
						Skriv en fråga och se vilken intent, agent och tool(s) som väljs — med fullständig
						scoring-breakdown.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="flex gap-3">
						<div className="flex-1">
							<Input
								placeholder="T.ex. Hur är vädret i Göteborg imorgon?"
								value={query}
								onChange={(e) => setQuery(e.target.value)}
								onKeyDown={(e) => {
									if (e.key === "Enter" && !isRunning) {
										e.preventDefault();
										runDebug();
									}
								}}
								className="h-11 text-base"
							/>
						</div>
						<Button
							onClick={runDebug}
							disabled={isRunning || !query.trim()}
							className="gap-2 h-11 px-6"
						>
							{isRunning ? (
								<Loader2 className="h-4 w-4 animate-spin" />
							) : (
								<Play className="h-4 w-4" />
							)}
							Kör
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* Pipeline flow visualization */}
			{result && (
				<>
					{/* Intent & Agent steps — only shown when backend populates them */}
					{(result.intent != null || topAgent != null) && (
						<>
							<div className="grid gap-4 md:grid-cols-3">
								<PipelineStep
									step={1}
									label="Intent"
									value={result.intent?.intent_id ?? null}
									confidence={result.intent?.confidence ?? null}
									detail={
										result.intent
											? `Route: ${result.intent.route} · Complexity: ${result.intent.graph_complexity}`
											: undefined
									}
									isActive={result.intent != null}
								/>
								<div className="hidden md:flex items-center justify-center">
									<ArrowRight className="h-5 w-5 text-muted-foreground" />
								</div>
								<PipelineStep
									step={2}
									label="Agent"
									value={topAgent?.agent_id ?? null}
									confidence={topAgent?.score ?? null}
									detail={
										topAgent
											? `${result.agents.length} kandidater · ${topAgent.auto_selected ? "Auto-vald" : "LLM-rankad"}`
											: undefined
									}
									isActive={topAgent != null}
								/>
							</div>

							<div className="flex items-center justify-center">
								<ArrowRight className="h-5 w-5 text-muted-foreground rotate-90" />
							</div>
						</>
					)}

					{/* Tool scoring breakdown */}
					<Card>
						<CardHeader className="pb-3">
							<div className="flex items-center justify-between">
								<CardTitle>Verktygsval — scoring breakdown</CardTitle>
								{result.timing_ms > 0 && (
									<Badge variant="outline" className="text-xs">
										{result.timing_ms}ms
									</Badge>
								)}
							</div>
							{result.thresholds && (
								<CardDescription>
									Auto-select tröskel: score ≥{" "}
									{(result.thresholds.tool_auto_score * 100).toFixed(0)}%, margin ≥{" "}
									{(result.thresholds.tool_auto_margin * 100).toFixed(0)}%
								</CardDescription>
							)}
						</CardHeader>
						<CardContent>
							{result.tools.length > 0 ? (
								<div className="overflow-x-auto">
									<Table>
										<TableHeader>
											<TableRow>
												<TableHead className="w-8">#</TableHead>
												<TableHead>Verktyg</TableHead>
												<TableHead className="text-right">Namn</TableHead>
												<TableHead className="text-right">Nyckelord</TableHead>
												<TableHead className="text-right">Beskr.</TableHead>
												<TableHead className="text-right">Exempel</TableHead>
												<TableHead className="text-right">Embedding</TableHead>
												<TableHead className="text-right">Ns.Boost</TableHead>
												<TableHead className="text-right font-bold">Total</TableHead>
												<TableHead className="text-center">Vald</TableHead>
											</TableRow>
										</TableHeader>
										<TableBody>
											{result.tools.map((tool) => (
												<TableRow
													key={tool.tool_id}
													className={tool.auto_selected ? "bg-emerald-500/5" : ""}
												>
													<TableCell className="text-xs text-muted-foreground">
														{tool.rank}
													</TableCell>
													<TableCell className="font-mono text-xs font-medium">
														{tool.tool_id}
													</TableCell>
													<TableCell className="text-right text-xs tabular-nums">
														{tool.scoring?.name_match?.toFixed(2) ?? "-"}
													</TableCell>
													<TableCell className="text-right text-xs tabular-nums">
														{tool.scoring?.keyword?.toFixed(2) ?? "-"}
													</TableCell>
													<TableCell className="text-right text-xs tabular-nums">
														{tool.scoring?.description_token?.toFixed(2) ?? "-"}
													</TableCell>
													<TableCell className="text-right text-xs tabular-nums">
														{tool.scoring?.example_query?.toFixed(2) ?? "-"}
													</TableCell>
													<TableCell className="text-right text-xs tabular-nums">
														{tool.scoring?.embedding?.toFixed(2) ?? "-"}
													</TableCell>
													<TableCell className="text-right text-xs tabular-nums">
														{tool.scoring?.namespace_boost?.toFixed(2) ?? "-"}
													</TableCell>
													<TableCell className="text-right text-xs tabular-nums font-bold">
														{tool.score.toFixed(3)}
													</TableCell>
													<TableCell className="text-center">
														{tool.auto_selected ? (
															<CheckCircle2 className="h-4 w-4 text-emerald-600 mx-auto" />
														) : (
															<Minus className="h-4 w-4 text-muted-foreground mx-auto" />
														)}
													</TableCell>
												</TableRow>
											))}
										</TableBody>
									</Table>
								</div>
							) : (
								<p className="text-sm text-muted-foreground text-center py-6">
									Inga verktyg hittades för denna fråga.
								</p>
							)}
						</CardContent>
					</Card>
				</>
			)}

			{/* Error state */}
			{result?.error && (
				<Card className="border-destructive">
					<CardContent className="py-4">
						<div className="flex items-center gap-2 text-destructive">
							<XCircle className="h-4 w-4" />
							<p className="text-sm">{result.error}</p>
						</div>
					</CardContent>
				</Card>
			)}

			{/* Query history */}
			{history.length > 0 && !result && (
				<Card>
					<CardHeader className="pb-3">
						<CardTitle className="text-base">Senaste sökningar</CardTitle>
					</CardHeader>
					<CardContent>
						<div className="space-y-2">
							{history.map((item) => (
								<button
									type="button"
									key={`history-${item.ts}`}
									className="w-full text-left rounded border p-3 hover:bg-muted/50 transition-colors"
									onClick={() => {
										setQuery(item.query);
										setResult(item.result);
									}}
								>
									<p className="text-sm font-medium">{item.query}</p>
									<div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
										<span>Intent: {item.result.intent?.intent_id ?? "-"}</span>
										<span>Agent: {item.result.agents[0]?.agent_id ?? "-"}</span>
										<span>Tool: {item.result.tools[0]?.tool_id ?? "-"}</span>
										<span>{item.result.timing_ms}ms</span>
									</div>
								</button>
							))}
						</div>
					</CardContent>
				</Card>
			)}

			{/* Empty state */}
			{!result && history.length === 0 && (
				<Card>
					<CardContent className="py-12 text-center">
						<Search className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
						<p className="text-lg font-medium">Testa pipelinen</p>
						<p className="text-sm text-muted-foreground mt-1">
							Skriv en fråga ovan och tryck Kör för att se hela Intent → Agent → Tool-kedjan med
							scoring.
						</p>
					</CardContent>
				</Card>
			)}
		</div>
	);
}
