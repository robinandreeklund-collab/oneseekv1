"use client";

import { Suspense, lazy, useEffect, useState } from "react";
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
} from "lucide-react";
import {
	nexusApiService,
	type NexusHealthResponse,
	type OverviewMetricsResponse,
} from "@/lib/apis/nexus-api.service";
import { ZoneHealthCard } from "@/components/admin/nexus/shared/zone-health-card";
import { BandDistribution } from "@/components/admin/nexus/shared/band-distribution";
import { SpaceTab } from "@/components/admin/nexus/tabs/space-tab";
import { ForgeTab } from "@/components/admin/nexus/tabs/forge-tab";
import { LoopTab } from "@/components/admin/nexus/tabs/loop-tab";
import { LedgerTab } from "@/components/admin/nexus/tabs/ledger-tab";
import { DeployTab } from "@/components/admin/nexus/tabs/deploy-tab";

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
	const [activeTab, setActiveTab] = useState("overview");
	const [health, setHealth] = useState<NexusHealthResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		nexusApiService
			.getHealth()
			.then(setHealth)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	}, []);

	return (
		<div className="space-y-6">
			{/* Header */}
			<div>
				<h1 className="text-3xl font-bold tracking-tight">NEXUS</h1>
				<p className="text-muted-foreground mt-1">
					Retrieval Intelligence Platform — precisionrouting, självförbättrande
					eval och embedding-rymd-hälsa
				</p>
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
				</TabsList>

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

	return (
		<div className="space-y-6">
			{/* Key Performance Metrics */}
			{metricsLoading ? (
				<div className="flex items-center gap-2 text-muted-foreground">
					<Loader2 className="h-4 w-4 animate-spin" />
					Laddar metriker...
				</div>
			) : metrics ? (
				<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
					<StatusCard
						label="Band-0 Throughput"
						value={
							metrics.band0_rate != null
								? `${(metrics.band0_rate * 100).toFixed(1)}%`
								: "—"
						}
						color={
							metrics.band0_rate != null && metrics.band0_rate >= 0.8
								? "green"
								: undefined
						}
					/>
					<StatusCard
						label="ECE Global"
						value={
							metrics.ece_global != null
								? metrics.ece_global.toFixed(4)
								: "—"
						}
						color={
							metrics.ece_global != null && metrics.ece_global < 0.05
								? "green"
								: undefined
						}
					/>
					<StatusCard
						label="OOD Rate"
						value={
							metrics.ood_rate != null
								? `${(metrics.ood_rate * 100).toFixed(1)}%`
								: "—"
						}
						color={
							metrics.ood_rate != null && metrics.ood_rate < 0.03
								? "green"
								: metrics.ood_rate != null && metrics.ood_rate >= 0.03
									? "red"
									: undefined
						}
					/>
					<StatusCard
						label="Platt-kalibrerad"
						value={metrics.platt_calibrated ? "Ja" : "Nej"}
						color={metrics.platt_calibrated ? "green" : "red"}
					/>
				</div>
			) : null}

			{/* Additional counts */}
			{metrics ? (
				<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
					<StatusCard
						label="Totala routing-händelser"
						value={String(metrics.total_events)}
					/>
					<StatusCard
						label="Verktyg indexerade"
						value={String(metrics.total_tools)}
					/>
					<StatusCard
						label="Hard negatives"
						value={String(metrics.total_hard_negatives)}
					/>
				</div>
			) : null}

			<ZoneHealthCard />
			<BandDistribution />
		</div>
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
