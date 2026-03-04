"use client";

import { useEffect, useState } from "react";
import { AlertCircle, BookOpen, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
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

export function LedgerTab() {
	const [metrics, setMetrics] = useState<PipelineMetricsSummary | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		nexusApiService
			.getLedgerMetrics()
			.then(setMetrics)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	}, []);

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

	const stages = metrics?.stages || [];

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

			{/* Stage metrics */}
			{stages.length === 0 ? (
				<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
					Inga pipeline-metriker tillgängliga ännu. Kör en eval-loop för att generera data.
				</div>
			) : (
				<div className="space-y-4">
					{stages.map((stage) => (
						<StageCard key={`${stage.stage}-${stage.stage_name}`} stage={stage} />
					))}
				</div>
			)}
		</div>
	);
}

function StageCard({ stage }: { stage: StageMetrics }) {
	const label = STAGE_LABELS[stage.stage_name] || stage.stage_name;

	return (
		<div className="rounded-lg border bg-card p-4">
			<div className="flex items-center justify-between mb-3">
				<h4 className="font-semibold text-sm">{label}</h4>
				{stage.namespace && (
					<span className="text-xs text-muted-foreground font-mono">
						{stage.namespace}
					</span>
				)}
			</div>
			<div className="grid grid-cols-2 md:grid-cols-5 gap-4">
				<MetricValue label="P@1" value={stage.precision_at_1} />
				<MetricValue label="P@5" value={stage.precision_at_5} />
				<MetricValue label="MRR@10" value={stage.mrr_at_10} />
				<MetricValue label="nDCG@5" value={stage.ndcg_at_5} />
				{stage.reranker_delta !== null && (
					<MetricValue
						label="Reranker Delta"
						value={stage.reranker_delta}
						showSign
					/>
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
	const color = showSign
		? value > 0
			? "text-green-600"
			: value < 0
				? "text-red-600"
				: ""
		: "";

	return (
		<div>
			<p className="text-xs text-muted-foreground">{label}</p>
			<p className={`text-lg font-mono font-semibold ${color}`}>
				{prefix}{pct}%
			</p>
		</div>
	);
}
