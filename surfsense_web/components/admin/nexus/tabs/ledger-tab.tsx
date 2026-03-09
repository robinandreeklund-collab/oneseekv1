"use client";

import { AlertCircle, BookOpen, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
	type MetricsTrend,
	nexusApiService,
	type PipelineMetricsSummary,
	type StageMetrics,
} from "@/lib/apis/nexus-api.service";

const STAGE_LABELS: Record<string, string> = {
	intent: "1. Intent Routing",
	route: "2. Route Selection",
	bigtool: "3. Bigtool Retrieval",
	rerank: "4. Reranker",
	e2e: "5. End-to-End",
};

const STAGE_COLORS: Record<string, string> = {
	intent: "#3b82f6",
	route: "#22c55e",
	bigtool: "#f59e0b",
	rerank: "#a855f7",
	e2e: "#ef4444",
};

function getStageColor(stage: string): string {
	return STAGE_COLORS[stage] ?? "#6b7280";
}

export function LedgerTab() {
	const [metrics, setMetrics] = useState<PipelineMetricsSummary | null>(null);
	const [trend, setTrend] = useState<MetricsTrend | null>(null);
	const [loading, setLoading] = useState(true);
	const [trendLoading, setTrendLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [selectedNamespace, setSelectedNamespace] = useState<string>("__all__");

	useEffect(() => {
		nexusApiService
			.getLedgerMetrics()
			.then(setMetrics)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));

		nexusApiService
			.getLedgerTrendTyped(30)
			.then(setTrend)
			.catch(() => setTrend(null))
			.finally(() => setTrendLoading(false));
	}, []);

	const stages = metrics?.stages || [];

	const namespaces = useMemo(() => {
		const ns = new Set<string>();
		for (const stage of stages) {
			if (stage.namespace) {
				ns.add(stage.namespace);
			}
		}
		return Array.from(ns).sort();
	}, [stages]);

	const filteredStages = useMemo(() => {
		if (selectedNamespace === "__all__") return stages;
		return stages.filter((s) => s.namespace === selectedNamespace);
	}, [stages, selectedNamespace]);

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground p-4">
				<Loader2 className="h-4 w-4 animate-spin" />
				Laddar pipeline-metriker...
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
			{/* Header */}
			<div>
				<h3 className="text-lg font-semibold flex items-center gap-2">
					<BookOpen className="h-5 w-5" />
					Eval Ledger — Pipeline-metriker
				</h3>
				<p className="text-sm text-muted-foreground">
					5-stegs pipeline: intent, route, bigtool, rerank, end-to-end
				</p>
			</div>

			{/* E2E Summary */}
			{metrics?.overall_e2e && (
				<div className="rounded-lg border bg-card p-4">
					<p className="text-sm text-muted-foreground">End-to-End Precision@1</p>
					<p className="text-3xl font-bold mt-1">
						{metrics.overall_e2e.precision_at_1 !== null
							? `${(metrics.overall_e2e.precision_at_1 * 100).toFixed(1)}%`
							: "—"}
					</p>
				</div>
			)}

			{/* 30-day Trend Chart */}
			<TrendChart trend={trend} loading={trendLoading} />

			{/* Namespace Filter */}
			{namespaces.length > 0 && (
				<div className="flex items-center gap-3">
					<label htmlFor="namespace-filter" className="text-sm font-medium text-muted-foreground">
						Filtrera namespace:
					</label>
					<select
						id="namespace-filter"
						value={selectedNamespace}
						onChange={(e) => setSelectedNamespace(e.target.value)}
						className="rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
					>
						<option value="__all__">Alla</option>
						{namespaces.map((ns) => (
							<option key={ns} value={ns}>
								{ns}
							</option>
						))}
					</select>
				</div>
			)}

			{/* Stage metrics */}
			{filteredStages.length === 0 ? (
				<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
					Inga pipeline-metriker tillgängliga ännu. Kör en eval-loop för att generera data.
				</div>
			) : (
				<div className="space-y-4">
					{filteredStages.map((stage) => (
						<StageCard key={`${stage.stage}-${stage.stage_name}`} stage={stage} />
					))}
				</div>
			)}
		</div>
	);
}

function TrendChart({ trend, loading }: { trend: MetricsTrend | null; loading: boolean }) {
	if (loading) {
		return (
			<Card>
				<CardHeader>
					<CardTitle className="text-base">30-dagars trend</CardTitle>
				</CardHeader>
				<CardContent>
					<div className="flex items-center gap-2 text-muted-foreground">
						<Loader2 className="h-4 w-4 animate-spin" />
						Laddar trenddata...
					</div>
				</CardContent>
			</Card>
		);
	}

	const dataPoints = trend?.data_points ?? [];

	if (dataPoints.length === 0) {
		return (
			<Card>
				<CardHeader>
					<CardTitle className="text-base">30-dagars trend</CardTitle>
				</CardHeader>
				<CardContent>
					<p className="text-sm text-muted-foreground">Ingen trenddata tillgänglig</p>
				</CardContent>
			</Card>
		);
	}

	// Group by stage
	const grouped: Record<string, { date: string; value: number }[]> = {};
	for (const dp of dataPoints) {
		if (dp.date === null || dp.precision_at_1 === null) continue;
		const stage = dp.stage;
		if (!grouped[stage]) grouped[stage] = [];
		grouped[stage].push({ date: dp.date, value: dp.precision_at_1 });
	}

	// Sort each group by date
	for (const stage of Object.keys(grouped)) {
		grouped[stage].sort((a, b) => a.date.localeCompare(b.date));
	}

	const stageNames = Object.keys(grouped).sort();

	if (stageNames.length === 0) {
		return (
			<Card>
				<CardHeader>
					<CardTitle className="text-base">30-dagars trend</CardTitle>
				</CardHeader>
				<CardContent>
					<p className="text-sm text-muted-foreground">Ingen trenddata tillgänglig</p>
				</CardContent>
			</Card>
		);
	}

	// Compute SVG coordinates
	const svgWidth = 600;
	const svgHeight = 200;
	const padding = { top: 15, right: 15, bottom: 25, left: 40 };
	const chartWidth = svgWidth - padding.left - padding.right;
	const chartHeight = svgHeight - padding.top - padding.bottom;

	// Collect all dates and values for axis scaling
	const allDates = new Set<string>();
	let minVal = 1;
	let maxVal = 0;
	for (const points of Object.values(grouped)) {
		for (const p of points) {
			allDates.add(p.date);
			if (p.value < minVal) minVal = p.value;
			if (p.value > maxVal) maxVal = p.value;
		}
	}

	const sortedDates = Array.from(allDates).sort();
	const dateCount = sortedDates.length;

	// Add some margin to value range
	const valRange = maxVal - minVal || 0.1;
	const yMin = Math.max(0, minVal - valRange * 0.1);
	const yMax = Math.min(1, maxVal + valRange * 0.1);

	function xScale(dateStr: string): number {
		const idx = sortedDates.indexOf(dateStr);
		if (dateCount === 1) return padding.left + chartWidth / 2;
		return padding.left + (idx / (dateCount - 1)) * chartWidth;
	}

	function yScale(val: number): number {
		const ratio = (val - yMin) / (yMax - yMin || 1);
		return padding.top + chartHeight - ratio * chartHeight;
	}

	// Build polyline points strings per stage
	const polylines = stageNames.map((stage) => {
		const points = grouped[stage]
			.map((p) => `${xScale(p.date).toFixed(1)},${yScale(p.value).toFixed(1)}`)
			.join(" ");
		return { stage, points, color: getStageColor(stage) };
	});

	// Y-axis labels
	const yTicks = 5;
	const yLabels = Array.from({ length: yTicks + 1 }, (_, i) => {
		const val = yMin + (i / yTicks) * (yMax - yMin);
		return { val, y: yScale(val), label: `${(val * 100).toFixed(0)}%` };
	});

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">30-dagars trend</CardTitle>
			</CardHeader>
			<CardContent>
				<svg
					viewBox={`0 0 ${svgWidth} ${svgHeight}`}
					className="w-full"
					style={{ height: "200px" }}
					preserveAspectRatio="xMidYMid meet"
				>
					{/* Y-axis grid lines and labels */}
					{yLabels.map((tick) => (
						<g key={tick.val}>
							<line
								x1={padding.left}
								y1={tick.y}
								x2={svgWidth - padding.right}
								y2={tick.y}
								stroke="currentColor"
								strokeOpacity={0.1}
								strokeWidth={1}
							/>
							<text
								x={padding.left - 5}
								y={tick.y + 4}
								textAnchor="end"
								fontSize={10}
								fill="currentColor"
								fillOpacity={0.5}
							>
								{tick.label}
							</text>
						</g>
					))}

					{/* Polylines per stage */}
					{polylines.map((pl) => (
						<polyline
							key={pl.stage}
							points={pl.points}
							fill="none"
							stroke={pl.color}
							strokeWidth={2}
							strokeLinejoin="round"
							strokeLinecap="round"
						/>
					))}

					{/* Data point dots */}
					{polylines.map((pl) =>
						grouped[pl.stage].map((p) => (
							<circle
								key={`${pl.stage}-${p.date}`}
								cx={xScale(p.date)}
								cy={yScale(p.value)}
								r={3}
								fill={pl.color}
							/>
						))
					)}
				</svg>

				{/* Legend */}
				<div className="flex flex-wrap gap-4 mt-3">
					{polylines.map((pl) => (
						<div key={pl.stage} className="flex items-center gap-1.5 text-xs">
							<span
								className="inline-block h-2.5 w-2.5 rounded-full"
								style={{ backgroundColor: pl.color }}
							/>
							<span className="text-muted-foreground">{STAGE_LABELS[pl.stage] ?? pl.stage}</span>
						</div>
					))}
				</div>
			</CardContent>
		</Card>
	);
}

function StageCard({ stage }: { stage: StageMetrics }) {
	const label = STAGE_LABELS[stage.stage_name] || stage.stage_name;

	return (
		<div className="rounded-lg border bg-card p-4">
			<div className="flex items-center justify-between mb-3">
				<h4 className="font-semibold text-sm">{label}</h4>
				{stage.namespace && (
					<span className="text-xs text-muted-foreground font-mono">{stage.namespace}</span>
				)}
			</div>
			<div className="grid grid-cols-2 md:grid-cols-5 gap-4">
				<MetricValue label="P@1" value={stage.precision_at_1} />
				<MetricValue label="P@5" value={stage.precision_at_5} />
				<MetricValue label="MRR@10" value={stage.mrr_at_10} />
				<MetricValue label="nDCG@5" value={stage.ndcg_at_5} />
				{stage.reranker_delta !== null && (
					<MetricValue label="Reranker Delta" value={stage.reranker_delta} showSign />
				)}
			</div>
		</div>
	);
}

function MetricValue({
	label,
	value,
	showSign = false,
}: {
	label: string;
	value: number | null | undefined;
	showSign?: boolean;
}) {
	if (value === null || value === undefined) {
		return (
			<div>
				<p className="text-xs text-muted-foreground">{label}</p>
				<p className="text-lg font-mono text-muted-foreground">—</p>
			</div>
		);
	}

	const pct = (value * 100).toFixed(1);
	const prefix = showSign && value > 0 ? "+" : "";
	const color = showSign ? (value > 0 ? "text-green-600" : value < 0 ? "text-red-600" : "") : "";

	return (
		<div>
			<p className="text-xs text-muted-foreground">{label}</p>
			<p className={`text-lg font-mono font-semibold ${color}`}>
				{prefix}
				{pct}%
			</p>
		</div>
	);
}
