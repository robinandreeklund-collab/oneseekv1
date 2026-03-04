"use client";

import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	Activity,
	AlertCircle,
	Beaker,
	BookOpen,
	Loader2,
	Orbit,
	Rocket,
	Sparkles,
	Trash2,
	Workflow,
} from "lucide-react";
import {
	nexusApiService,
	type NexusHealthResponse,
	type OverviewMetricsResponse,
	type RoutingEventResponse,
	type ECEReportResponse,
	type CalibrationParamsResponse,
	type LiveRoutingConfigResponse,
} from "@/lib/apis/nexus-api.service";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ThumbsUp, ThumbsDown, ExternalLink, Settings } from "lucide-react";
import Link from "next/link";
import { DarkMatterPanel } from "@/components/admin/nexus/shared/dark-matter-panel";
import { ZoneHealthCard } from "@/components/admin/nexus/shared/zone-health-card";
import { BandDistribution } from "@/components/admin/nexus/shared/band-distribution";
import { SpaceTab } from "@/components/admin/nexus/tabs/space-tab";
import { ForgeTab } from "@/components/admin/nexus/tabs/forge-tab";
import { LoopTab } from "@/components/admin/nexus/tabs/loop-tab";
import { LedgerTab } from "@/components/admin/nexus/tabs/ledger-tab";
import { DeployTab } from "@/components/admin/nexus/tabs/deploy-tab";
import { OptimizerTab } from "@/components/admin/nexus/tabs/optimizer-tab";
import { PipelineExplorerTab } from "@/components/admin/nexus/tabs/pipeline-explorer-tab";

function TabFallback() {
	return (
		<div className="flex items-center justify-center h-64">
			<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
		</div>
	);
}

function PlaceholderTab({ name }: { name: string }) {
	return (
		<div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
			<Beaker className="h-12 w-12 mb-4 opacity-50" />
			<p className="text-lg font-medium">{name}</p>
			<p className="text-sm">Byggs i kommande sprint</p>
		</div>
	);
}

export function NexusDashboard() {
	const [activeTab, setActiveTab] = useState("explorer");
	const [health, setHealth] = useState<NexusHealthResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [resetting, setResetting] = useState(false);
	const [resetResult, setResetResult] = useState<string | null>(null);

	useEffect(() => {
		nexusApiService
			.getHealth()
			.then(setHealth)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	}, []);

	const handleReset = useCallback(() => {
		if (!window.confirm("Nollställ ALL NEXUS-data? Routing-händelser, testfall, loop-körningar, snapshots — allt raderas.")) {
			return;
		}
		setResetting(true);
		setResetResult(null);
		nexusApiService
			.resetAll()
			.then((res) => {
				const total = Object.values(res.deleted).reduce((a, b) => a + b, 0);
				setResetResult(`Raderade ${total} rader. Ladda om sidan.`);
			})
			.catch((err) => setResetResult(`Fel: ${err.message}`))
			.finally(() => setResetting(false));
	}, []);

	return (
		<div className="space-y-6">
			{/* Header */}
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-3xl font-bold tracking-tight">NEXUS</h1>
					<p className="text-muted-foreground mt-1">
						Retrieval Intelligence Platform — Intent → Agent → Tool precision routing,
						självförbättrande eval och embedding-rymd-hälsa
					</p>
				</div>
				<div className="flex items-center gap-2">
					{resetResult && (
						<span className="text-xs text-muted-foreground">{resetResult}</span>
					)}
					<Button
						variant="outline"
						size="sm"
						onClick={handleReset}
						disabled={resetting}
						className="text-destructive hover:text-destructive"
					>
						{resetting ? (
							<Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
						) : (
							<Trash2 className="h-3.5 w-3.5 mr-1.5" />
						)}
						Nollställ NEXUS
					</Button>
				</div>
			</div>

			{/* Health Summary */}
			{loading ? (
				<div className="flex items-center gap-2 text-muted-foreground">
					<Loader2 className="h-4 w-4 animate-spin" />
					Laddar systemstatus...
				</div>
			) : error ? (
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertDescription>
						Kunde inte ansluta till NEXUS backend: {error}
					</AlertDescription>
				</Alert>
			) : health ? (
				<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
					<StatusCard
						label="Status"
						value={health.status === "ok" ? "Aktiv" : "Fel"}
						color={health.status === "ok" ? "green" : "red"}
					/>
					<StatusCard
						label="Zoner konfigurerade"
						value={String(health.zones_configured)}
					/>
					<StatusCard
						label="Routing-händelser"
						value={String(health.total_routing_events)}
					/>
					<StatusCard
						label="Syntetiska testfall"
						value={String(health.total_synthetic_cases)}
					/>
				</div>
			) : null}

			{/* Tabs */}
			<Tabs value={activeTab} onValueChange={setActiveTab}>
				<TabsList>
					<TabsTrigger value="explorer" className="gap-1.5">
						<Workflow className="h-3.5 w-3.5" />
						Pipeline Explorer
					</TabsTrigger>
					<TabsTrigger value="overview" className="gap-1.5">
						<Activity className="h-3.5 w-3.5" />
						Översikt
					</TabsTrigger>
					<TabsTrigger value="space" className="gap-1.5">
						<Orbit className="h-3.5 w-3.5" />
						Rymd
					</TabsTrigger>
					<TabsTrigger value="forge" className="gap-1.5">
						<Sparkles className="h-3.5 w-3.5" />
						Forge
					</TabsTrigger>
					<TabsTrigger value="loop" className="gap-1.5">
						<Beaker className="h-3.5 w-3.5" />
						Loop
					</TabsTrigger>
					<TabsTrigger value="ledger" className="gap-1.5">
						<BookOpen className="h-3.5 w-3.5" />
						Ledger
					</TabsTrigger>
					<TabsTrigger value="deploy" className="gap-1.5">
						<Rocket className="h-3.5 w-3.5" />
						Deploy
					</TabsTrigger>
					<TabsTrigger value="optimizer" className="gap-1.5">
						<Sparkles className="h-3.5 w-3.5" />
						Optimizer
					</TabsTrigger>
				</TabsList>

				<TabsContent value="explorer" className="mt-6">
					<PipelineExplorerTab />
				</TabsContent>

				<TabsContent value="overview" className="mt-6">
					<OverviewTab />
				</TabsContent>

				<TabsContent value="space" className="mt-6">
					<SpaceTab />
				</TabsContent>

				<TabsContent value="forge" className="mt-6">
					<ForgeTab />
				</TabsContent>

				<TabsContent value="loop" className="mt-6">
					<LoopTab />
				</TabsContent>

				<TabsContent value="ledger" className="mt-6">
					<LedgerTab />
				</TabsContent>

				<TabsContent value="deploy" className="mt-6">
					<DeployTab />
				</TabsContent>

				<TabsContent value="optimizer" className="mt-6">
					<OptimizerTab />
				</TabsContent>
			</Tabs>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Overview Tab — shows zones + band distribution
// ---------------------------------------------------------------------------

function OverviewTab() {
	const [metrics, setMetrics] = useState<OverviewMetricsResponse | null>(null);
	const [metricsLoading, setMetricsLoading] = useState(true);

	useEffect(() => {
		nexusApiService
			.getOverviewMetrics()
			.then(setMetrics)
			.catch(() => {})
			.finally(() => setMetricsLoading(false));
	}, []);

	const pct = (v: number | null | undefined) =>
		v != null ? `${(v * 100).toFixed(1)}%` : "—";
	const num = (v: number | null | undefined, decimals = 4) =>
		v != null ? v.toFixed(decimals) : "—";
	const pctColor = (v: number | null | undefined, good: number, invert = false) => {
		if (v == null) return undefined;
		return invert ? (v <= good ? "green" : "red") : (v >= good ? "green" : "red");
	};

	return (
		<div className="space-y-6">
			{metricsLoading ? (
				<div className="flex items-center gap-2 text-muted-foreground">
					<Loader2 className="h-4 w-4 animate-spin" />
					Laddar metriker...
				</div>
			) : metrics ? (
				<>
					{/* SECTION 1: Routing Health */}
					<Card>
						<CardHeader>
							<CardTitle className="text-base">Routing Health</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="grid grid-cols-2 md:grid-cols-4 gap-4">
								<StatusCard
									label="Band-0 Throughput"
									value={pct(metrics.band0_rate)}
									color={pctColor(metrics.band0_rate, 0.8)}
								/>
								<StatusCard
									label="Multi-intent detect"
									value={pct(metrics.multi_intent_rate)}
								/>
								<StatusCard
									label="Schema match rate"
									value={pct(metrics.schema_match_rate)}
									color={pctColor(metrics.schema_match_rate, 0.9)}
								/>
								<StatusCard
									label="OOD rate (dark matter)"
									value={pct(metrics.ood_rate)}
									color={pctColor(metrics.ood_rate, 0.03, true)}
								/>
							</div>
						</CardContent>
					</Card>

					{/* SECTION 2: Calibration */}
					<Card>
						<CardHeader>
							<CardTitle className="text-base">Calibration</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="grid grid-cols-2 md:grid-cols-3 gap-4">
								<StatusCard
									label="Global ECE"
									value={num(metrics.ece_global)}
									color={pctColor(metrics.ece_global, 0.05, true)}
								/>
								<StatusCard
									label="Platt-kalibrerad"
									value={metrics.platt_calibrated ? "Ja" : "Nej"}
									color={metrics.platt_calibrated ? "green" : "red"}
								/>
								<StatusCard
									label="Routing-händelser"
									value={String(metrics.total_events)}
								/>
							</div>
						</CardContent>
					</Card>

					{/* SECTION 3: Retrieval Quality */}
					<Card>
						<CardHeader>
							<CardTitle className="text-base">Retrieval Quality</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="grid grid-cols-2 md:grid-cols-4 gap-4">
								<StatusCard
									label="Namespace Purity"
									value={pct(metrics.namespace_purity)}
									color={pctColor(metrics.namespace_purity, 0.88)}
								/>
								<StatusCard
									label="Hard negatives"
									value={String(metrics.total_hard_negatives)}
								/>
								<StatusCard
									label="Reranker Delta"
									value={metrics.reranker_delta != null ? `+${(metrics.reranker_delta * 100).toFixed(1)}pp` : "—"}
									color={metrics.reranker_delta != null && metrics.reranker_delta > 0.12 ? "green" : undefined}
								/>
								<StatusCard
									label="Verktyg indexerade"
									value={String(metrics.total_tools)}
								/>
							</div>
						</CardContent>
					</Card>

					{/* SECTION 4: Embedding Health */}
					<Card>
						<CardHeader>
							<CardTitle className="text-base">Embedding Health</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="grid grid-cols-2 md:grid-cols-4 gap-4">
								<StatusCard
									label="Silhouette (global)"
									value={num(metrics.silhouette_global, 3)}
									color={pctColor(metrics.silhouette_global, 0.55)}
								/>
								<StatusCard
									label="Inter-zone distance"
									value={num(metrics.inter_zone_distance, 3)}
									color={pctColor(metrics.inter_zone_distance, 0.55)}
								/>
								<StatusCard
									label="Hubness rate"
									value={pct(metrics.hubness_rate)}
									color={pctColor(metrics.hubness_rate, 0.05, true)}
								/>
								<StatusCard
									label="False negative rate"
									value="—"
								/>
							</div>
						</CardContent>
					</Card>
				</>
			) : null}

			<LiveRoutingPanel />
			<ZoneHealthCard />
			<BandDistribution />
			<RoutingEventsPanel />
			<CalibrationPanel />
			<DarkMatterPanel />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Live Routing Panel — shows current phase + key retrieval weights (read-only)
// ---------------------------------------------------------------------------

const PHASE_LABELS: Record<string, string> = {
	shadow: "Shadow",
	tool_gate: "Tool gate",
	agent_auto: "Agent auto",
	adaptive: "Adaptive",
	intent_finetune: "Intent finetune",
};

const DEFAULT_TUNING = {
	live_routing_enabled: false,
	live_routing_phase: "shadow",
	name_match_weight: 5.0,
	keyword_weight: 3.0,
	description_token_weight: 1.0,
	example_query_weight: 2.0,
	namespace_boost: 3.0,
	embedding_weight: 4.0,
	semantic_embedding_weight: 2.8,
	structural_embedding_weight: 1.2,
	rerank_candidates: 24,
	tool_auto_score_threshold: 0.6,
	tool_auto_margin_threshold: 0.25,
	agent_auto_score_threshold: 0.55,
	agent_auto_margin_threshold: 0.18,
	intent_candidate_top_k: 3,
	agent_candidate_top_k: 3,
	tool_candidate_top_k: 5,
} as LiveRoutingConfigResponse["current_config"];

function LiveRoutingPanel() {
	const [config, setConfig] = useState<LiveRoutingConfigResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [usingDefaults, setUsingDefaults] = useState(false);

	useEffect(() => {
		nexusApiService
			.getLiveRoutingConfig()
			.then(setConfig)
			.catch(() => {
				setConfig({ phases: PHASE_LABELS as unknown as Record<string, number>, current_config: DEFAULT_TUNING });
				setUsingDefaults(true);
			})
			.finally(() => setLoading(false));
	}, []);

	const cfg = config?.current_config ?? DEFAULT_TUNING;
	const currentPhase = cfg.live_routing_phase ?? "shadow";

	return (
		<Card>
			<CardHeader className="flex flex-row items-center justify-between">
				<div className="flex items-center gap-2">
					<Settings className="h-4 w-4 text-muted-foreground" />
					<CardTitle>Fas & Retrieval-vikter</CardTitle>
					{usingDefaults && (
						<span className="text-xs text-muted-foreground bg-muted rounded px-1.5 py-0.5">defaults</span>
					)}
				</div>
				<Link
					href="/admin/tools"
					className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
				>
					Redigera i Verktyg
					<ExternalLink className="h-3 w-3" />
				</Link>
			</CardHeader>
			<CardContent>
				{loading ? (
					<div className="flex items-center gap-2 text-muted-foreground">
						<Loader2 className="h-4 w-4 animate-spin" />
						Laddar routing-konfiguration...
					</div>
				) : (
					<div className="space-y-4">
						{/* Phase badges */}
						<div>
							<p className="text-xs text-muted-foreground mb-2">Live routing-fas</p>
							<div className="flex flex-wrap items-center gap-2">
								{Object.keys(config?.phases ?? PHASE_LABELS).map((phase) => {
									const isActive = phase === currentPhase;
									return (
										<span
											key={phase}
											className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium ${
												isActive
													? "bg-green-600 text-white"
													: "bg-muted text-muted-foreground"
											}`}
										>
											{isActive ? "●" : "○"} {PHASE_LABELS[phase] ?? phase}
										</span>
									);
								})}
							</div>
						</div>

						{/* Key weights grid */}
						<div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
							<WeightCell label="Name match" value={cfg.name_match_weight} />
							<WeightCell label="Keyword" value={cfg.keyword_weight} />
							<WeightCell label="Semantic emb." value={cfg.semantic_embedding_weight} />
							<WeightCell label="Structural emb." value={cfg.structural_embedding_weight} />
							<WeightCell label="Namespace boost" value={cfg.namespace_boost} />
							<WeightCell label="Rerank candidates" value={cfg.rerank_candidates} />
						</div>

						{/* Thresholds */}
						<div className="grid grid-cols-2 md:grid-cols-4 gap-2">
							<WeightCell label="Tool score thr." value={cfg.tool_auto_score_threshold} />
							<WeightCell label="Tool margin thr." value={cfg.tool_auto_margin_threshold} />
							<WeightCell label="Agent score thr." value={cfg.agent_auto_score_threshold} />
							<WeightCell label="Agent margin thr." value={cfg.agent_auto_margin_threshold} />
						</div>

						{/* Summary line */}
						<div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground pt-1 border-t">
							<span>
								Live routing:{" "}
								<span className={cfg.live_routing_enabled ? "text-green-600 font-medium" : "text-red-500 font-medium"}>
									{cfg.live_routing_enabled ? "Aktiverad" : "Inaktiverad"}
								</span>
							</span>
							<span>Top-K: intent={cfg.intent_candidate_top_k}, agent={cfg.agent_candidate_top_k}, tool={cfg.tool_candidate_top_k}</span>
						</div>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

function WeightCell({ label, value }: { label: string; value: number | undefined }) {
	return (
		<div className="rounded border px-3 py-2">
			<p className="text-xs text-muted-foreground truncate">{label}</p>
			<p className="text-sm font-mono font-medium">{value ?? "—"}</p>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Routing Events Panel — last 20 routing events with feedback
// ---------------------------------------------------------------------------

const BAND_COLORS: Record<number, string> = {
	0: "text-green-600 bg-green-50",
	1: "text-blue-600 bg-blue-50",
	2: "text-amber-600 bg-amber-50",
	3: "text-orange-600 bg-orange-50",
	4: "text-red-600 bg-red-50",
};

function RoutingEventsPanel() {
	const [events, setEvents] = useState<RoutingEventResponse[]>([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		nexusApiService
			.getRoutingEvents(20)
			.then(setEvents)
			.catch(() => {})
			.finally(() => setLoading(false));
	}, []);

	const handleFeedback = (eventId: string, value: number) => {
		nexusApiService.logFeedback(eventId, { explicit: value }).catch(() => {});
	};

	return (
		<Card>
			<CardHeader>
				<CardTitle>Senaste routing-händelser</CardTitle>
			</CardHeader>
			<CardContent>
				{loading ? (
					<div className="flex items-center gap-2 text-muted-foreground">
						<Loader2 className="h-4 w-4 animate-spin" />
						Laddar händelser...
					</div>
				) : events.length === 0 ? (
					<p className="text-sm text-muted-foreground">
						Inga routing-händelser registrerade ännu.
					</p>
				) : (
					<div className="overflow-x-auto">
						<table className="w-full text-sm">
							<thead>
								<tr className="border-b text-left text-muted-foreground">
									<th className="pb-2 pr-4">Fråga</th>
									<th className="pb-2 pr-4">Band</th>
									<th className="pb-2 pr-4">Zon</th>
									<th className="pb-2 pr-4">Agent</th>
									<th className="pb-2 pr-4">Verktyg</th>
									<th className="pb-2 pr-4">Confidence</th>
									<th className="pb-2 pr-4">OOD</th>
									<th className="pb-2 pr-4">Tid</th>
									<th className="pb-2" />
								</tr>
							</thead>
							<tbody>
								{events.map((evt) => (
									<tr key={evt.id} className="border-b last:border-0">
										<td className="py-2 pr-4 max-w-[300px] truncate" title={evt.query_text ?? ""}>
											{evt.query_text
												? evt.query_text.length > 60
													? `${evt.query_text.slice(0, 60)}…`
													: evt.query_text
												: "—"}
										</td>
										<td className="py-2 pr-4">
											<span
												className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${BAND_COLORS[evt.band] ?? ""}`}
											>
												{evt.band}
											</span>
										</td>
										<td className="py-2 pr-4">{evt.resolved_zone ?? "—"}</td>
										<td className="py-2 pr-4">
											{evt.selected_agent ? (
												<span className="inline-flex items-center rounded bg-indigo-50 text-indigo-700 px-1.5 py-0.5 text-xs font-medium">
													{evt.selected_agent}
												</span>
											) : "—"}
										</td>
										<td className="py-2 pr-4">{evt.selected_tool ?? "—"}</td>
										<td className="py-2 pr-4">
											{evt.calibrated_confidence != null
												? evt.calibrated_confidence.toFixed(3)
												: "—"}
										</td>
										<td className="py-2 pr-4">
											{evt.is_ood ? (
												<span className="text-red-600 font-medium">Ja</span>
											) : (
												"Nej"
											)}
										</td>
										<td className="py-2 pr-4 whitespace-nowrap">
											{new Date(evt.routed_at).toLocaleString("sv-SE")}
										</td>
										<td className="py-2">
											<div className="flex items-center gap-1">
												<button
													type="button"
													className="p-1 rounded hover:bg-green-100 transition-colors"
													onClick={() => handleFeedback(evt.id, 1)}
													title="Bra routing"
												>
													<ThumbsUp className="h-3.5 w-3.5 text-muted-foreground hover:text-green-600" />
												</button>
												<button
													type="button"
													className="p-1 rounded hover:bg-red-100 transition-colors"
													onClick={() => handleFeedback(evt.id, -1)}
													title="Dålig routing"
												>
													<ThumbsDown className="h-3.5 w-3.5 text-muted-foreground hover:text-red-600" />
												</button>
											</div>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

// ---------------------------------------------------------------------------
// Calibration Panel — ECE per zone + Platt fitting
// ---------------------------------------------------------------------------

function CalibrationPanel() {
	const [ece, setEce] = useState<ECEReportResponse | null>(null);
	const [params, setParams] = useState<CalibrationParamsResponse[]>([]);
	const [loading, setLoading] = useState(true);
	const [fitting, setFitting] = useState(false);

	const fetchData = () => {
		setLoading(true);
		Promise.all([
			nexusApiService.getCalibrationECE(),
			nexusApiService.getCalibrationParams(),
		])
			.then(([eceData, paramsData]) => {
				setEce(eceData);
				setParams(paramsData);
			})
			.catch(() => {})
			.finally(() => setLoading(false));
	};

	useEffect(() => {
		fetchData();
	}, []);

	const handleFit = () => {
		setFitting(true);
		nexusApiService
			.fitCalibration()
			.then(() => fetchData())
			.catch(() => {})
			.finally(() => setFitting(false));
	};

	return (
		<Card>
			<CardHeader className="flex flex-row items-center justify-between">
				<CardTitle>Kalibrering</CardTitle>
				<Button
					variant="outline"
					size="sm"
					onClick={handleFit}
					disabled={fitting}
				>
					{fitting ? (
						<>
							<Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
							Kalibrerar...
						</>
					) : (
						"Kalibrera Platt"
					)}
				</Button>
			</CardHeader>
			<CardContent>
				{loading ? (
					<div className="flex items-center gap-2 text-muted-foreground">
						<Loader2 className="h-4 w-4 animate-spin" />
						Laddar kalibreringsdata...
					</div>
				) : (
					<div className="space-y-4">
						{/* Global ECE */}
						<div>
							<p className="text-sm text-muted-foreground">Global ECE</p>
							<p className="text-2xl font-bold">
								{ece?.global_ece != null ? ece.global_ece.toFixed(4) : "—"}
							</p>
						</div>

						{/* Per-zone ECE */}
						{ece && Object.keys(ece.per_zone).length > 0 && (
							<div>
								<p className="text-sm font-medium mb-2">ECE per zon</p>
								<div className="grid grid-cols-2 md:grid-cols-4 gap-2">
									{Object.entries(ece.per_zone).map(([zone, value]) => (
										<div
											key={zone}
											className="rounded border px-3 py-2"
										>
											<p className="text-xs text-muted-foreground">{zone}</p>
											<p className="text-sm font-mono font-medium">
												{value.toFixed(4)}
											</p>
										</div>
									))}
								</div>
							</div>
						)}

						{/* Platt params */}
						{params.length > 0 && (
							<div>
								<p className="text-sm font-medium mb-2">Platt-parametrar</p>
								<div className="grid grid-cols-1 md:grid-cols-2 gap-2">
									{params.map((p) => (
										<div
											key={p.id}
											className="rounded border px-3 py-2 text-sm"
										>
											<div className="flex items-center justify-between">
												<span className="font-medium">{p.zone}</span>
												{p.is_active && (
													<span className="text-xs text-green-600 bg-green-50 rounded px-1.5 py-0.5">
														Aktiv
													</span>
												)}
											</div>
											<div className="mt-1 text-muted-foreground text-xs space-y-0.5">
												<p>A: {p.param_a != null ? p.param_a.toFixed(4) : "—"} · B: {p.param_b != null ? p.param_b.toFixed(4) : "—"}</p>
												<p>ECE: {p.ece_score != null ? p.ece_score.toFixed(4) : "—"} · Samples: {p.fitted_on_samples ?? "—"}</p>
												<p>Metod: {p.calibration_method} · Fittad: {new Date(p.fitted_at).toLocaleString("sv-SE")}</p>
											</div>
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
// Status Card
// ---------------------------------------------------------------------------

function StatusCard({
	label,
	value,
	color,
}: {
	label: string;
	value: string;
	color?: string;
}) {
	return (
		<div className="rounded-lg border bg-card p-4">
			<p className="text-sm text-muted-foreground">{label}</p>
			<p
				className={`text-2xl font-bold mt-1 ${
					color === "green"
						? "text-green-600"
						: color === "red"
							? "text-red-600"
							: ""
				}`}
			>
				{value}
			</p>
		</div>
	);
}
