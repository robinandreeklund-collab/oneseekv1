"use client";

import { Badge } from "@/components/ui/badge";
import type { ToolEvaluationRunComparison } from "@/contracts/types/admin-tool-settings.types";

function formatPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	return `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	const sign = value > 0 ? "+" : "";
	return `${sign}${(value * 100).toFixed(1)}%`;
}

interface ComparisonInsightsProps {
	title: string;
	comparison: ToolEvaluationRunComparison | null | undefined;
}

export function ComparisonInsights({ title, comparison }: ComparisonInsightsProps) {
	if (!comparison) return null;
	const trend = comparison.trend;
	const trendVariant =
		trend === "degraded" ? "destructive" : trend === "improved" ? "default" : "outline";
	const trendLabel =
		trend === "degraded"
			? "Sämre än föregående"
			: trend === "improved"
				? "Bättre än föregående"
				: trend === "unchanged"
					? "Oförändrat"
					: "Första jämförelse";
	const metricDeltas = (comparison.metric_deltas ?? [])
		.filter((item) => typeof item.delta === "number")
		.sort((left, right) => (left.delta ?? 0) - (right.delta ?? 0))
		.slice(0, 4);
	return (
		<div className="rounded border p-3 space-y-2">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<p className="text-sm font-medium">{title}</p>
				<Badge variant={trendVariant}>{trendLabel}</Badge>
			</div>
			<p className="text-xs text-muted-foreground">
				Nu: {formatPercent(comparison.current_success_rate)} · Föregående:{" "}
				{formatPercent(comparison.previous_success_rate)} · Delta:{" "}
				{formatSignedPercent(comparison.success_rate_delta)}
			</p>
			{comparison.previous_run_at && (
				<p className="text-xs text-muted-foreground">
					Jämfört med: {new Date(comparison.previous_run_at).toLocaleString("sv-SE")}
					{comparison.previous_eval_name ? ` (${comparison.previous_eval_name})` : ""}
				</p>
			)}
			{metricDeltas.length > 0 && (
				<div className="flex flex-wrap gap-2">
					{metricDeltas.map((item) => (
						<Badge
							key={`${title}-${item.metric}`}
							variant={(item.delta ?? 0) < 0 ? "destructive" : "outline"}
						>
							{item.metric}: {formatSignedPercent(item.delta)}
						</Badge>
					))}
				</div>
			)}
			{(comparison.guidance ?? []).length > 0 && (
				<ul className="list-disc pl-5 text-xs text-muted-foreground space-y-1">
					{comparison.guidance.map((line, index) => (
						<li key={`${title}-guide-${index}`}>{line}</li>
					))}
				</ul>
			)}
		</div>
	);
}
