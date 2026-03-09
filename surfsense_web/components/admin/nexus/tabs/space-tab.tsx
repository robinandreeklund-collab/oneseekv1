"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Filter, Loader2, Orbit, RefreshCw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
	nexusApiService,
	type SpaceHealthReport,
	type SpaceSnapshot,
	type SpaceSnapshotPoint,
	type HubnessReport,
} from "@/lib/apis/nexus-api.service";
import { ConfusionMatrix } from "@/components/admin/nexus/shared/confusion-matrix";

export function SpaceTab() {
	const [health, setHealth] = useState<SpaceHealthReport | null>(null);
	const [snapshot, setSnapshot] = useState<SpaceSnapshot | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [selectedNamespace, setSelectedNamespace] = useState<string>("all");
	const [selectedZone, setSelectedZone] = useState<string>("all");
	const [refreshing, setRefreshing] = useState(false);

	const loadData = useCallback(() => {
		setLoading(true);
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

	useEffect(() => {
		loadData();
	}, [loadData]);

	const handleRefresh = async () => {
		setRefreshing(true);
		try {
			await nexusApiService.refreshSpaceSnapshot();
			loadData();
		} catch (err: unknown) {
			setError(err instanceof Error ? err.message : "Refresh failed");
		} finally {
			setRefreshing(false);
		}
	};

	// Derive unique namespaces and zones from snapshot points
	const { namespaces, zones } = useMemo(() => {
		if (!snapshot) return { namespaces: [] as string[], zones: [] as string[] };
		const nsSet = new Set<string>();
		const zoneSet = new Set<string>();
		for (const p of snapshot.points) {
			if (p.namespace) {
				// Use first 2 segments as namespace prefix
				const parts = (p.namespace as string).split("/");
				nsSet.add(parts.length >= 2 ? `${parts[0]}/${parts[1]}` : p.namespace as string);
			}
			zoneSet.add(p.zone);
		}
		return {
			namespaces: Array.from(nsSet).sort(),
			zones: Array.from(zoneSet).sort(),
		};
	}, [snapshot]);

	// Filter points by selected namespace and zone
	const filteredPoints = useMemo(() => {
		if (!snapshot) return [];
		return snapshot.points.filter((p) => {
			if (selectedNamespace !== "all" && p.namespace) {
				const ns = p.namespace as string;
				if (!ns.startsWith(selectedNamespace)) return false;
			} else if (selectedNamespace !== "all") {
				return false;
			}
			if (selectedZone !== "all" && p.zone !== selectedZone) return false;
			return true;
		});
	}, [snapshot, selectedNamespace, selectedZone]);

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
			{/* Header with icon */}
			<div className="flex items-center justify-between">
				<div>
					<h3 className="text-lg font-semibold flex items-center gap-2">
						<Orbit className="h-5 w-5" />
						Embedding-rymd
					</h3>
					<p className="text-sm text-muted-foreground">
						UMAP-visualisering av verktygsemeddningar med zon-klustring
					</p>
				</div>
				<div className="flex items-center gap-2">
					{snapshot && (
						<Badge variant="outline" className="text-xs">
							{snapshot.points.length} verktyg totalt
						</Badge>
					)}
					<button
						type="button"
						onClick={handleRefresh}
						disabled={refreshing}
						className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-background hover:bg-muted disabled:opacity-50"
					>
						<RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
						{refreshing ? "Beräknar..." : "Uppdatera embeddings"}
					</button>
				</div>
			</div>

			{/* Health Summary */}
			{health && (
				<div className="grid grid-cols-2 md:grid-cols-5 gap-3">
					<MetricCard
						label="Separation"
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

			{/* UMAP Visualization with filters */}
			{snapshot && snapshot.points.length > 0 && (
				<Card>
					<CardHeader className="py-3 px-4">
						<div className="flex items-center justify-between flex-wrap gap-3">
							<CardTitle className="text-sm flex items-center gap-2">
								UMAP 2D — Verktygsrymd
								{(selectedNamespace !== "all" || selectedZone !== "all") && (
									<Badge variant="secondary" className="text-xs font-normal">
										{filteredPoints.length}/{snapshot.points.length} visas
									</Badge>
								)}
							</CardTitle>
							<div className="flex items-center gap-2">
								<Filter className="h-3.5 w-3.5 text-muted-foreground" />
								<select
									value={selectedNamespace}
									onChange={(e) => setSelectedNamespace(e.target.value)}
									className="rounded-md border bg-background px-2 py-1.5 text-xs"
								>
									<option value="all">Alla namespaces</option>
									{namespaces.map((ns) => (
										<option key={ns} value={ns}>
											{ns} ({snapshot.points.filter((p) => (p.namespace as string | undefined)?.startsWith(ns)).length})
										</option>
									))}
								</select>
								<select
									value={selectedZone}
									onChange={(e) => setSelectedZone(e.target.value)}
									className="rounded-md border bg-background px-2 py-1.5 text-xs"
								>
									<option value="all">Alla zoner</option>
									{zones.map((z) => (
										<option key={z} value={z}>
											{z} ({snapshot.points.filter((p) => p.zone === z).length})
										</option>
									))}
								</select>
							</div>
						</div>
					</CardHeader>
					<CardContent className="px-4 pb-4">
						<UMAPCanvas
							points={filteredPoints as SpaceSnapshotPoint[]}
							allPoints={snapshot.points as SpaceSnapshotPoint[]}
							isFiltered={selectedNamespace !== "all" || selectedZone !== "all"}
						/>
					</CardContent>
				</Card>
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
	allPoints,
	isFiltered,
}: {
	points: SpaceSnapshotPoint[];
	allPoints: SpaceSnapshotPoint[];
	isFiltered: boolean;
}) {
	const [hoveredTool, setHoveredTool] = useState<string | null>(null);

	// Build zone colors from ALL points (consistent colors regardless of filter)
	const ZONE_COLORS: Record<string, string> = {};
	for (const p of allPoints) {
		if (!ZONE_COLORS[p.zone]) {
			ZONE_COLORS[p.zone] = zoneColor(p.zone);
		}
	}

	// Unique zones in the visible points
	const visibleZones = Array.from(new Set(points.map((p) => p.zone))).sort();

	// Normalize coordinates based on filtered points for better spread
	const sourcePoints = points.length > 0 ? points : allPoints;
	const xs = sourcePoints.map((p) => p.x);
	const ys = sourcePoints.map((p) => p.y);
	const minX = Math.min(...xs);
	const maxX = Math.max(...xs);
	const minY = Math.min(...ys);
	const maxY = Math.max(...ys);
	const rangeX = maxX - minX || 1;
	const rangeY = maxY - minY || 1;

	// Ghost points (dimmed, for context when filtering)
	const ghostPoints = isFiltered
		? allPoints.filter((p) => !points.some((fp) => fp.tool_id === p.tool_id))
		: [];

	return (
		<div className="space-y-3">
			<div className="relative w-full h-[480px] bg-muted/20 rounded-lg overflow-hidden border">
				{/* Grid lines for reference */}
				<div className="absolute inset-0 pointer-events-none">
					<div className="absolute left-1/4 top-0 bottom-0 w-px bg-muted/40" />
					<div className="absolute left-1/2 top-0 bottom-0 w-px bg-muted/40" />
					<div className="absolute left-3/4 top-0 bottom-0 w-px bg-muted/40" />
					<div className="absolute top-1/4 left-0 right-0 h-px bg-muted/40" />
					<div className="absolute top-1/2 left-0 right-0 h-px bg-muted/40" />
					<div className="absolute top-3/4 left-0 right-0 h-px bg-muted/40" />
				</div>

				{/* Ghost points (context) */}
				{ghostPoints.map((p) => {
					const x = ((p.x - minX) / rangeX) * 88 + 6;
					const y = ((p.y - minY) / rangeY) * 88 + 6;
					return (
						<div
							key={`ghost-${p.tool_id}`}
							className="absolute w-2 h-2 rounded-full -translate-x-1/2 -translate-y-1/2 opacity-10"
							style={{
								left: `${x}%`,
								top: `${y}%`,
								backgroundColor: ZONE_COLORS[p.zone] || "#6b7280",
							}}
						/>
					);
				})}

				{/* Active points */}
				{points.map((p) => {
					const x = ((p.x - minX) / rangeX) * 88 + 6;
					const y = ((p.y - minY) / rangeY) * 88 + 6;
					const color = ZONE_COLORS[p.zone] || "#6b7280";
					const isHovered = hoveredTool === p.tool_id;

					return (
						<div
							key={p.tool_id}
							className={`absolute rounded-full -translate-x-1/2 -translate-y-1/2 cursor-pointer transition-all duration-150 ${
								isHovered
									? "w-5 h-5 ring-2 ring-white shadow-lg z-20"
									: "w-3 h-3 hover:w-4 hover:h-4 hover:ring-2 hover:ring-white/70 z-10"
							}`}
							style={{
								left: `${x}%`,
								top: `${y}%`,
								backgroundColor: color,
							}}
							onMouseEnter={() => setHoveredTool(p.tool_id)}
							onMouseLeave={() => setHoveredTool(null)}
						/>
					);
				})}

				{/* Hover tooltip */}
				{hoveredTool && (() => {
					const p = points.find((pt) => pt.tool_id === hoveredTool);
					if (!p) return null;
					const x = ((p.x - minX) / rangeX) * 88 + 6;
					const y = ((p.y - minY) / rangeY) * 88 + 6;
					return (
						<div
							className="absolute z-30 pointer-events-none bg-popover text-popover-foreground shadow-md rounded-md px-2.5 py-1.5 text-xs border"
							style={{
								left: `${x}%`,
								top: `${Math.max(y - 5, 2)}%`,
								transform: "translate(-50%, -100%)",
							}}
						>
							<p className="font-mono font-medium">{p.tool_id}</p>
							<p className="text-muted-foreground">
								{p.zone}{p.namespace ? ` — ${p.namespace}` : ""}
							</p>
						</div>
					);
				})()}
			</div>

			{/* Zone legend */}
			<div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
				{visibleZones.map((zone) => {
					const count = points.filter((p) => p.zone === zone).length;
					return (
						<span key={zone} className="flex items-center gap-1.5">
							<span
								className="w-2.5 h-2.5 rounded-full inline-block flex-shrink-0"
								style={{ backgroundColor: ZONE_COLORS[zone] }}
							/>
							<span className="text-muted-foreground">
								{zone} ({count})
							</span>
						</span>
					);
				})}
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
		<div className="rounded-lg border bg-card p-3">
			<p className="text-xs text-muted-foreground">{label}</p>
			<p className={`text-xl font-bold mt-0.5 ${isGood ? "text-green-600" : "text-orange-600"}`}>
				{display}
			</p>
			{target != null && format === "score" && (
				<p className="text-xs text-muted-foreground mt-0.5">
					Mal: {(target * 100).toFixed(0)}%
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
		<Card>
			<CardHeader className="py-3 px-4">
				<CardTitle className="text-sm">Hubness-varningar</CardTitle>
				<p className="text-xs text-muted-foreground">
					Verktyg som dyker upp som nearest-neighbor oproportionerligt ofta
				</p>
			</CardHeader>
			<CardContent className="px-4 pb-4">
				<div className="divide-y">
					{alerts.map((a) => (
						<div key={a.tool_id} className="flex items-center justify-between py-2.5">
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
			</CardContent>
		</Card>
	);
}
