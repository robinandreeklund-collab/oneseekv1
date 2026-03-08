"use client";

import { useState } from "react";
import {
	ArrowRight,
	ChevronDown,
	ChevronRight,
	Loader2,
	Play,
	Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
	nexusApiService,
	type RoutingDecision,
	type AgentCandidateResponse,
	type RoutingCandidate,
	type LlmGateResult,
} from "@/lib/apis/nexus-api.service";

const BAND_COLORS: Record<number, string> = {
	0: "bg-green-100 text-green-800 border-green-300",
	1: "bg-blue-100 text-blue-800 border-blue-300",
	2: "bg-amber-100 text-amber-800 border-amber-300",
	3: "bg-orange-100 text-orange-800 border-orange-300",
	4: "bg-red-100 text-red-800 border-red-300",
};

const COMPLEXITY_COLORS: Record<string, string> = {
	trivial: "bg-green-50 text-green-700",
	simple: "bg-blue-50 text-blue-700",
	complex: "bg-purple-50 text-purple-700",
};

export function PipelineExplorerTab() {
	const [query, setQuery] = useState("");
	const [result, setResult] = useState<RoutingDecision | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [history, setHistory] = useState<Array<{ query: string; result: RoutingDecision }>>([]);
	const [llmJudgeEnabled, setLlmJudgeEnabled] = useState(false);
	const [llmGateEnabled, setLlmGateEnabled] = useState(false);

	const handleRun = async () => {
		const q = query.trim();
		if (!q) return;
		setLoading(true);
		setError(null);
		try {
			const decision = await nexusApiService.routeQuery(q, {
				llm_judge: llmJudgeEnabled,
				llm_gate: llmGateEnabled,
			});
			setResult(decision);
			setHistory((prev) => [{ query: q, result: decision }, ...prev].slice(0, 10));
		} catch (err: unknown) {
			setError(err instanceof Error ? err.message : "Routing misslyckades");
		} finally {
			setLoading(false);
		}
	};

	const handleKeyDown = (e: React.KeyboardEvent) => {
		if (e.key === "Enter" && !loading) handleRun();
	};

	const loadFromHistory = (item: { query: string; result: RoutingDecision }) => {
		setQuery(item.query);
		setResult(item.result);
		setError(null);
	};

	return (
		<div className="space-y-6">
			{/* Query input */}
			<Card>
				<CardHeader>
					<CardTitle className="text-base flex items-center gap-2">
						<Zap className="h-4 w-4" />
						Testa en fråga genom NEXUS-pipelinen
					</CardTitle>
				</CardHeader>
				<CardContent>
					<div className="flex gap-2">
						<Input
							placeholder="T.ex. Hur är vädret i Göteborg?"
							value={query}
							onChange={(e) => setQuery(e.target.value)}
							onKeyDown={handleKeyDown}
							disabled={loading}
							className="flex-1"
						/>
						<label className="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0 cursor-pointer select-none">
							<input
								type="checkbox"
								checked={llmGateEnabled}
								onChange={(e) => {
									setLlmGateEnabled(e.target.checked);
									if (e.target.checked) setLlmJudgeEnabled(false);
								}}
								disabled={loading}
								className="rounded"
							/>
							LLM Gate
						</label>
						<label className="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0 cursor-pointer select-none">
							<input
								type="checkbox"
								checked={llmJudgeEnabled}
								onChange={(e) => setLlmJudgeEnabled(e.target.checked)}
								disabled={loading || llmGateEnabled}
								className="rounded"
							/>
							LLM Judge
						</label>
						<Button onClick={handleRun} disabled={loading || !query.trim()}>
							{loading ? (
								<Loader2 className="h-4 w-4 animate-spin mr-1.5" />
							) : (
								<Play className="h-4 w-4 mr-1.5" />
							)}
							Kör
						</Button>
					</div>
					{error && (
						<p className="text-sm text-red-600 mt-2">{error}</p>
					)}
				</CardContent>
			</Card>

			{/* Pipeline result */}
			{result && (
				<div className="space-y-4">
					{/* Flow summary bar */}
					<FlowSummary result={result} />

					{/* Pipeline stages */}
					<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
						<IntentStage result={result} />
						<AgentStage result={result} />
						<ToolStage result={result} />
						<VerdictStage result={result} />
					</div>
				</div>
			)}

			{/* History */}
			{history.length > 0 && (
				<Card>
					<CardHeader>
						<CardTitle className="text-base">Historik (senaste 10)</CardTitle>
					</CardHeader>
					<CardContent>
						<div className="space-y-1">
							{history.map((item, idx) => (
								<button
									key={`${item.query}-${idx}`}
									type="button"
									className="w-full text-left px-3 py-2 rounded hover:bg-muted transition-colors flex items-center justify-between text-sm"
									onClick={() => loadFromHistory(item)}
								>
									<span className="truncate mr-4">{item.query}</span>
									<div className="flex items-center gap-2 shrink-0">
										<Badge variant="outline" className="text-xs">
											{item.result.selected_agent ?? "—"}
										</Badge>
										<ArrowRight className="h-3 w-3 text-muted-foreground" />
										<Badge variant="outline" className="text-xs font-mono">
											{item.result.selected_tool
												? item.result.selected_tool.split("/").pop()
												: "—"}
										</Badge>
										<span
											className={`text-xs px-1.5 py-0.5 rounded font-medium ${BAND_COLORS[item.result.band] ?? ""}`}
										>
											B{item.result.band}
										</span>
									</div>
								</button>
							))}
						</div>
					</CardContent>
				</Card>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Flow summary — horizontal pipeline view
// ---------------------------------------------------------------------------

function FlowSummary({ result }: { result: RoutingDecision }) {
	const qa = result.query_analysis;
	const zone = result.resolved_zone ?? qa.zone_candidates[0] ?? "?";
	const agent = result.selected_agent ?? "—";
	const tool = result.selected_tool ? result.selected_tool.split("/").pop() : "—";

	return (
		<Card className="bg-muted/30">
			<CardContent className="pt-4 pb-4">
				<div className="flex items-center gap-2 flex-wrap justify-center text-sm">
					{/* Query */}
					<span className="font-medium max-w-[200px] truncate" title={qa.original_query}>
						"{qa.original_query.length > 30
							? `${qa.original_query.slice(0, 30)}…`
							: qa.original_query}"
					</span>
					<ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />

					{/* Intent / Zone */}
					<Badge variant="secondary" className="gap-1">
						<span className="text-muted-foreground">intent:</span>
						{zone}
					</Badge>
					<ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />

					{/* Agent */}
					<Badge className="bg-indigo-100 text-indigo-800 border-indigo-300 gap-1">
						<span className="text-indigo-500">agent:</span>
						{agent}
					</Badge>
					<ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />

					{/* Tool */}
					<Badge className="bg-emerald-100 text-emerald-800 border-emerald-300 gap-1 font-mono">
						<span className="text-emerald-500">tool:</span>
						{tool}
					</Badge>
					<ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />

					{/* Band */}
					<span
						className={`px-2 py-0.5 rounded text-xs font-bold ${BAND_COLORS[result.band] ?? ""}`}
					>
						Band {result.band} — {result.band_name}
					</span>

					{/* LLM Gate */}
					{result.llm_gate && (
						<>
							<ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
							<Badge className="bg-purple-100 text-purple-800 border-purple-300 gap-1 text-[10px]">
								LLM Gate
							</Badge>
						</>
					)}

					{/* LLM Judge */}
					{result.llm_judge && (
						<>
							<ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
							<Badge
								className={`gap-1 font-mono ${
									result.llm_judge.agreement
										? "bg-green-100 text-green-800 border-green-300"
										: "bg-amber-100 text-amber-800 border-amber-300"
								}`}
							>
								<span className="opacity-60">llm:</span>
								{result.llm_judge.chosen_tool
									? result.llm_judge.chosen_tool.split("/").pop()
									: "—"}
							</Badge>
						</>
					)}

					{/* Latency */}
					<span className="text-xs text-muted-foreground ml-2">
						{result.latency_ms.toFixed(0)} ms
					</span>
				</div>
			</CardContent>
		</Card>
	);
}

// ---------------------------------------------------------------------------
// Stage 1: Intent
// ---------------------------------------------------------------------------

function IntentStage({ result }: { result: RoutingDecision }) {
	const qa = result.query_analysis;
	const gate = result.llm_gate;

	return (
		<StageCard number={1} title={gate ? "Intent (LLM)" : "Intent (QUL)"} color="bg-blue-500">
			<div className="space-y-3 text-sm">
				<Row label="Normaliserad" value={qa.normalized_query} />
				<Row label="Komplexitet">
					<Badge className={COMPLEXITY_COLORS[qa.complexity] ?? ""}>{qa.complexity}</Badge>
				</Row>
				<Row label="Zon-kandidater">
					<div className="flex gap-1 flex-wrap">
						{qa.zone_candidates.map((z) => (
							<Badge key={z} variant="outline">{z}</Badge>
						))}
					</div>
				</Row>
				{qa.domain_hints.length > 0 && (
					<Row label="Domänledtrådar">
						<div className="flex gap-1 flex-wrap">
							{qa.domain_hints.map((h) => (
								<Badge key={h} variant="outline" className="text-xs">{h}</Badge>
							))}
						</div>
					</Row>
				)}
				<Row label="Multi-intent" value={qa.is_multi_intent ? "Ja" : "Nej"} />
				<Row label="OOD-risk" value={qa.ood_risk.toFixed(2)} />

				{gate?.intent_step && (
					<div className="rounded-md border border-blue-200 bg-blue-50/50 p-3 space-y-2">
						<div className="flex items-center justify-between">
							<span className="text-xs font-medium text-blue-600">LLM Gate — Intent</span>
							<Badge variant="outline" className="text-[10px] py-0">{gate.intent_step.candidates_shown} kandidater</Badge>
						</div>
						<Row label="Vald domän">
							<Badge className="bg-blue-100 text-blue-800 border-blue-300">{gate.intent_step.chosen}</Badge>
						</Row>
						{gate.intent_step.reasoning && (
							<Row label="Motivering">
								<span className="text-muted-foreground italic text-xs">{gate.intent_step.reasoning}</span>
							</Row>
						)}
					</div>
				)}

				{/* Entities */}
				<EntityList entities={qa.entities} />

				{/* Sub-queries */}
				{qa.sub_queries.length > 0 && (
					<Collapsible title={`Delfrågor (${qa.sub_queries.length})`}>
						<ul className="list-disc list-inside text-xs text-muted-foreground">
							{qa.sub_queries.map((sq, i) => (
								<li key={`sq-${i}`}>{sq}</li>
							))}
						</ul>
					</Collapsible>
				)}
			</div>
		</StageCard>
	);
}

// ---------------------------------------------------------------------------
// Stage 2: Agent
// ---------------------------------------------------------------------------

function AgentStage({ result }: { result: RoutingDecision }) {
	const ar = result.agent_resolution;
	const gate = result.llm_gate;

	return (
		<StageCard number={2} title={gate ? "Agent (LLM)" : "Agent"} color="bg-indigo-500">
			{ar ? (
				<div className="space-y-3 text-sm">
					<Row label="Vald agent">
						<div className="flex gap-1 flex-wrap">
							{ar.selected_agents.map((a) => (
								<Badge key={a} className="bg-indigo-100 text-indigo-800 border-indigo-300">
									{a}
								</Badge>
							))}
						</div>
					</Row>
					<Row label="Namespace-filter">
						<div className="flex gap-1 flex-wrap">
							{ar.tool_namespaces.length > 0
								? ar.tool_namespaces.map((ns) => (
										<Badge key={ns} variant="outline" className="font-mono text-xs">
											{ns}
										</Badge>
									))
								: <span className="text-muted-foreground">Alla</span>}
						</div>
					</Row>

					{gate?.agent_step && (
						<div className="rounded-md border border-indigo-200 bg-indigo-50/50 p-3 space-y-2">
							<div className="flex items-center justify-between">
								<span className="text-xs font-medium text-indigo-600">LLM Gate — Agent</span>
								<Badge variant="outline" className="text-[10px] py-0">{gate.agent_step.candidates_shown} kandidater</Badge>
							</div>
							<Row label="Vald agent">
								<Badge className="bg-indigo-100 text-indigo-800 border-indigo-300">{gate.agent_step.chosen}</Badge>
							</Row>
							{gate.agent_step.reasoning && (
								<Row label="Motivering">
									<span className="text-muted-foreground italic text-xs">{gate.agent_step.reasoning}</span>
								</Row>
							)}
						</div>
					)}

					{ar.candidates.length > 0 && (
						<Collapsible title={`Alla kandidater (${ar.candidates.length})`}>
							<div className="space-y-1">
								{ar.candidates.map((c) => (
									<AgentCandidateRow key={c.name} candidate={c} selected={ar.selected_agents.includes(c.name)} />
								))}
							</div>
						</Collapsible>
					)}
				</div>
			) : (
				<p className="text-sm text-muted-foreground">Ingen agent-upplösning</p>
			)}
		</StageCard>
	);
}

function AgentCandidateRow({ candidate, selected }: { candidate: AgentCandidateResponse; selected: boolean }) {
	return (
		<div
			className={`flex items-center justify-between rounded px-2 py-1 text-xs ${
				selected ? "bg-indigo-50 border border-indigo-200" : "bg-muted/50"
			}`}
		>
			<div className="flex items-center gap-2">
				<span className={`font-medium ${selected ? "text-indigo-700" : ""}`}>{candidate.name}</span>
				<span className="text-muted-foreground">({candidate.zone})</span>
			</div>
			<div className="flex items-center gap-2">
				{candidate.matched_keywords.length > 0 && (
					<span className="text-muted-foreground">
						nyckelord: {candidate.matched_keywords.join(", ")}
					</span>
				)}
				<span className="font-mono font-medium">{candidate.score.toFixed(2)}</span>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Stage 3: Tool
// ---------------------------------------------------------------------------

function ToolStage({ result }: { result: RoutingDecision }) {
	const top5 = result.candidates.slice(0, 5);
	const judge = result.llm_judge;
	const gate = result.llm_gate;

	return (
		<StageCard number={3} title={gate ? "Tool (LLM)" : "Tool (StR + Rerank)"} color="bg-emerald-500">
			<div className="space-y-3 text-sm">
				<Row label="NEXUS valde">
					<Badge className="bg-emerald-100 text-emerald-800 border-emerald-300 font-mono">
						{result.selected_tool ?? "—"}
					</Badge>
				</Row>

				{/* LLM Gate tool result */}
				{gate?.tool_step && (
					<div className="rounded-md border border-emerald-200 bg-emerald-50/50 p-3 space-y-2">
						<div className="flex items-center justify-between">
							<span className="text-xs font-medium text-emerald-600">LLM Gate — Tool</span>
							<Badge variant="outline" className="text-[10px] py-0">{gate.tool_step.candidates_shown} kandidater</Badge>
						</div>
						<Row label="Valt verktyg">
							<Badge className="bg-emerald-100 text-emerald-800 border-emerald-300 font-mono">{gate.tool_step.chosen}</Badge>
						</Row>
						{gate.tool_step.reasoning && (
							<Row label="Motivering">
								<span className="text-muted-foreground italic text-xs">{gate.tool_step.reasoning}</span>
							</Row>
						)}
					</div>
				)}

				{/* LLM Judge result */}
				{judge && (
					<div className="rounded-md border p-3 space-y-2">
						<div className="flex items-center justify-between">
							<span className="text-xs font-medium text-muted-foreground">LLM Judge</span>
							{judge.agreement ? (
								<Badge className="bg-green-100 text-green-700 border-green-300 text-[10px] py-0">
									Overens
								</Badge>
							) : (
								<Badge className="bg-amber-100 text-amber-700 border-amber-300 text-[10px] py-0">
									Oenig
								</Badge>
							)}
						</div>
						<Row label="LLM valde">
							<Badge
								className={`font-mono ${
									judge.agreement
										? "bg-emerald-100 text-emerald-800 border-emerald-300"
										: "bg-amber-100 text-amber-800 border-amber-300"
								}`}
							>
								{judge.chosen_tool ?? "—"}
							</Badge>
						</Row>
						{judge.nexus_rank_of_chosen > 0 && !judge.agreement && (
							<Row label="NEXUS-rank" value={`#${judge.nexus_rank_of_chosen}`} />
						)}
						{judge.reasoning && (
							<Row label="Motivering">
								<span className="text-muted-foreground italic">{judge.reasoning}</span>
							</Row>
						)}
					</div>
				)}

				{top5.length > 0 && (
					<div>
						<p className="text-xs text-muted-foreground mb-1">Topp-{top5.length} kandidater</p>
						<div className="space-y-1">
							{top5.map((c, i) => (
								<ToolCandidateRow
									key={c.tool_id}
									candidate={c}
									isSelected={i === 0}
									isLlmChoice={judge?.chosen_tool === c.tool_id}
								/>
							))}
						</div>
					</div>
				)}

				{result.candidates.length > 5 && (
					<Collapsible title={`Alla kandidater (${result.candidates.length})`}>
						<div className="space-y-1">
							{result.candidates.map((c, i) => (
								<ToolCandidateRow
									key={c.tool_id}
									candidate={c}
									isSelected={i === 0}
									isLlmChoice={judge?.chosen_tool === c.tool_id}
								/>
							))}
						</div>
					</Collapsible>
				)}
			</div>
		</StageCard>
	);
}

function ToolCandidateRow({
	candidate,
	isSelected,
	isLlmChoice,
}: {
	candidate: RoutingCandidate;
	isSelected: boolean;
	isLlmChoice?: boolean;
}) {
	return (
		<div
			className={`flex items-center justify-between rounded px-2 py-1 text-xs ${
				isSelected ? "bg-emerald-50 border border-emerald-200" : "bg-muted/50"
			}`}
		>
			<div className="flex items-center gap-2">
				<span className="text-muted-foreground w-5 text-right">#{candidate.rank}</span>
				<span className={`font-mono ${isSelected ? "font-medium text-emerald-700" : ""}`}>
					{candidate.tool_id}
				</span>
				<Badge variant="outline" className="text-[10px] py-0">{candidate.zone}</Badge>
				{isLlmChoice && !isSelected && (
					<Badge className="bg-amber-100 text-amber-700 border-amber-300 text-[10px] py-0">
						LLM
					</Badge>
				)}
				{isLlmChoice && isSelected && (
					<Badge className="bg-green-100 text-green-700 border-green-300 text-[10px] py-0">
						LLM
					</Badge>
				)}
			</div>
			<div className="flex items-center gap-3 font-mono">
				<span className="text-muted-foreground">raw: {candidate.raw_score.toFixed(3)}</span>
				<span className="font-medium">cal: {candidate.calibrated_score.toFixed(3)}</span>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Stage 4: Verdict
// ---------------------------------------------------------------------------

function VerdictStage({ result }: { result: RoutingDecision }) {
	return (
		<StageCard number={4} title="Beslut" color="bg-amber-500">
			<div className="space-y-3 text-sm">
				<Row label="Band">
					<span className={`px-2 py-0.5 rounded text-xs font-bold ${BAND_COLORS[result.band] ?? ""}`}>
						{result.band} — {result.band_name}
					</span>
				</Row>
				<Row label="Kalibrerad confidence" value={result.calibrated_confidence.toFixed(4)} />
				<Row label="Schema-verifierad" value={result.schema_verified ? "Ja" : "Nej"} />
				<Row label="Out-of-distribution">
					{result.is_ood ? (
						<Badge variant="destructive">OOD</Badge>
					) : (
						<span className="text-green-600 font-medium">Nej</span>
					)}
				</Row>
				<Row label="Latens" value={`${result.latency_ms.toFixed(0)} ms`} />
			</div>
		</StageCard>
	);
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function StageCard({
	number,
	title,
	color,
	children,
}: {
	number: number;
	title: string;
	color: string;
	children: React.ReactNode;
}) {
	return (
		<Card>
			<CardHeader className="pb-3">
				<CardTitle className="text-base flex items-center gap-2">
					<span
						className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold text-white ${color}`}
					>
						{number}
					</span>
					{title}
				</CardTitle>
			</CardHeader>
			<CardContent>{children}</CardContent>
		</Card>
	);
}

function Row({
	label,
	value,
	children,
}: {
	label: string;
	value?: string;
	children?: React.ReactNode;
}) {
	return (
		<div className="flex items-start gap-2">
			<span className="text-muted-foreground shrink-0 w-32">{label}</span>
			{children ?? <span>{value}</span>}
		</div>
	);
}

function EntityList({ entities }: { entities: { locations: string[]; times: string[]; organizations: string[]; topics: string[] } }) {
	const all = [
		...entities.locations.map((v) => ({ type: "plats", value: v })),
		...entities.times.map((v) => ({ type: "tid", value: v })),
		...entities.organizations.map((v) => ({ type: "org", value: v })),
		...entities.topics.map((v) => ({ type: "ämne", value: v })),
	];
	if (all.length === 0) return null;

	const typeColors: Record<string, string> = {
		plats: "bg-sky-50 text-sky-700 border-sky-200",
		tid: "bg-violet-50 text-violet-700 border-violet-200",
		org: "bg-rose-50 text-rose-700 border-rose-200",
		ämne: "bg-teal-50 text-teal-700 border-teal-200",
	};

	return (
		<Row label="Entiteter">
			<div className="flex gap-1 flex-wrap">
				{all.map((e) => (
					<Badge key={`${e.type}-${e.value}`} variant="outline" className={`text-xs ${typeColors[e.type] ?? ""}`}>
						{e.type}: {e.value}
					</Badge>
				))}
			</div>
		</Row>
	);
}

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
	const [open, setOpen] = useState(false);
	return (
		<div>
			<button
				type="button"
				className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
				onClick={() => setOpen(!open)}
			>
				{open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
				{title}
			</button>
			{open && <div className="mt-1 ml-4">{children}</div>}
		</div>
	);
}
