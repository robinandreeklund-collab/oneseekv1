"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, Orbit } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	nexusApiService,
	type SpaceHealthReport,
	type SpaceSnapshot,
	type HubnessReport,
} from "@/lib/apis/nexus-api.service";
import { ConfusionMatrix } from "@/components/admin/nexus/shared/confusion-matrix";

export function SpaceTab() {
	const [health, setHealth] = useState<SpaceHealthReport | null>(null);
	const [snapshot, setSnapshot] = useState<SpaceSnapshot | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		Promise.all([
			nexusApiService.getSpaceHealth(),
			nexusApiService.getSpaceSnapshot(),
		])
			.then(([h, s]) => {
				setHealth(h);
				setSnapshot(s);
			})
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	}, []);

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground p-8">
				<Loader2 className="h-5 w-5 animate-spin" />
				Analyserar embedding-rymd...
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
			{/* Health Summary */}
			{health && (
				<div className="grid grid-cols-1 md:grid-cols-5 gap-4">
					<MetricCard
						label="Separation Score"
						value={health.global_silhouette}
						target={0.60}
						format="score"
					/>
					<MetricCard
						label="Cluster Purity"
						value={health.cluster_purity}
						target={0.85}
						format="score"
					/>
					<MetricCard
						label="Confusion Risk"
						value={health.confusion_risk}
						target={0.20}
						format="score"
						invert
					/>
					<MetricCard
						label="Totala verktyg"
						value={health.total_tools}
						format="count"
					/>
					<MetricCard
						label="Confusion-par"
						value={health.top_confusion_pairs.length}
						format="count"
						invert
					/>
				</div>
			)}

			{/* UMAP Visualization */}
			{snapshot && snapshot.points.length > 0 && (
				<div className="rounded-lg border bg-card p-4">
					<h3 className="font-semibold mb-4">UMAP 2D — Verktygsrymd</h3>
					<UMAPCanvas points={snapshot.points} />
				</div>
			)}

			{/* Hubness Alerts */}
			{health && health.hubness_alerts.length > 0 && (
				<HubnessPanel alerts={health.hubness_alerts} />
			)}

			{/* Confusion Matrix */}
			<ConfusionMatrix />
		</div>
	);
}

// ---------------------------------------------------------------------------
// UMAP Canvas — renders tool points as colored dots
// ---------------------------------------------------------------------------

/** Generate a deterministic HSL color from any string. */
function zoneColor(zone: string): string {
	let hash = 0;
	for (let i = 0; i < zone.length; i++) {
		hash = zone.charCodeAt(i) + ((hash << 5) - hash);
	}
	const hue = ((hash % 360) + 360) % 360;
	return `hsl(${hue}, 65%, 55%)`;
}

function UMAPCanvas({
	points,
}: {
	points: Array<{ tool_id: string; x: number; y: number; zone: string; cluster: number }>;
}) {
	// Build zone colors dynamically — deterministic from zone name
	const uniqueZones = Array.from(new Set(points.map((p) => p.zone)));
	const ZONE_COLORS: Record<string, string> = {};
	for (const z of uniqueZones) {
		ZONE_COLORS[z] = zoneColor(z);
	}

	// Only show zones that actually appear in data
	const usedZones = new Set(points.map((p) => p.zone));
	const activeZoneColors = Object.fromEntries(
		Object.entries(ZONE_COLORS).filter(([zone]) => usedZones.has(zone)),
	);

	// Normalize coordinates to 0-1
	const xs = points.map((p) => p.x);
	const ys = points.map((p) => p.y);
	const minX = Math.min(...xs);
	const maxX = Math.max(...xs);
	const minY = Math.min(...ys);
	const maxY = Math.max(...ys);
	const rangeX = maxX - minX || 1;
	const rangeY = maxY - minY || 1;

	return (
		<div className="relative w-full h-[400px] bg-muted/30 rounded overflow-hidden">
			{points.map((p) => {
				const x = ((p.x - minX) / rangeX) * 90 + 5;
				const y = ((p.y - minY) / rangeY) * 90 + 5;
				const color = ZONE_COLORS[p.zone] || "#6b7280";

				return (
					<div
						key={p.tool_id}
						className="absolute w-3 h-3 rounded-full -translate-x-1/2 -translate-y-1/2 cursor-pointer hover:ring-2 hover:ring-white"
						style={{
							left: `${x}%`,
							top: `${y}%`,
							backgroundColor: color,
						}}
						title={`${p.tool_id} (${p.zone})`}
					/>
				);
			})}
			{/* Legend */}
			<div className="absolute bottom-2 right-2 flex flex-wrap gap-2 text-xs bg-background/80 rounded px-2 py-1 max-w-[60%]">
				{Object.entries(activeZoneColors).map(([zone, color]) => (
					<span key={zone} className="flex items-center gap-1">
						<span
							className="w-2 h-2 rounded-full inline-block flex-shrink-0"
							style={{ backgroundColor: color }}
						/>
						{zone}
					</span>
				))}
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Metric Card
// ---------------------------------------------------------------------------

function MetricCard({
	label,
	value,
	target,
	format,
	invert,
}: {
	label: string;
	value: number | null;
	target?: number;
	format: "score" | "count";
	invert?: boolean;
}) {
	const display =
		value === null ? "—" : format === "score" ? (value * 100).toFixed(1) + "%" : String(value);

	const isGood = target
		? invert
			? (value ?? 0) <= target
			: (value ?? 0) >= target
		: true;

	return (
		<div className="rounded-lg border bg-card p-4">
			<p className="text-sm text-muted-foreground">{label}</p>
			<p className={`text-2xl font-bold mt-1 ${isGood ? "text-green-600" : "text-orange-600"}`}>
				{display}
			</p>
			{target && format === "score" && (
				<p className="text-xs text-muted-foreground mt-1">
					Mål: {(target * 100).toFixed(0)}%
				</p>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Hubness Panel
// ---------------------------------------------------------------------------

function HubnessPanel({ alerts }: { alerts: HubnessReport[] }) {
	return (
		<div className="rounded-lg border bg-card">
			<div className="p-4 border-b">
				<h3 className="font-semibold">Hubness-varningar</h3>
				<p className="text-sm text-muted-foreground">
					Verktyg som dyker upp som nearest-neighbor oproportionerligt ofta
				</p>
			</div>
			<div className="divide-y">
				{alerts.map((a) => (
					<div key={a.tool_id} className="flex items-center justify-between p-4">
						<span className="font-mono text-sm">{a.tool_id}</span>
						<div className="flex items-center gap-4 text-sm">
							<span className="text-muted-foreground">
								{a.times_as_nearest_neighbor}x NN
							</span>
							<span className="text-orange-600 font-mono">
								{(a.hubness_score * 100).toFixed(1)}%
							</span>
						</div>
					</div>
				))}
			</div>
		</div>
	);
}
