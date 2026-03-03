"use client";

/**
 * v3 Admin Tools Dashboard — 8-tab layout.
 *
 * New panels:
 *   Tab 1: Pipeline Explorer — Query → Intent → Agent → Tool debug
 *   Tab 2: Tuning & Vikter  — Visual sliders, thresholds, weight balance
 *   Tab 3: Deploy & Ops     — Lifecycle, rollback, audit trail
 *
 * Restored full-feature tabs:
 *   Tab 4: Kalibrering       — Phase panel, 3-step guided flow (audit, eval, auto-opt)
 *   Tab 5: Metadata           — Per-tool editing, retrieval weights, lock management
 *   Tab 6: Överblick          — Key metrics, trend charts, eval history, lifecycle table
 */

import {
	AlertCircle,
	BarChart3,
	BookOpen,
	FlaskConical,
	Loader2,
	Rocket,
	Search,
	SlidersHorizontal,
} from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { useToolCatalog } from "@/components/admin/tools/hooks/use-tool-catalog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const PipelineExplorerPanel = lazy(() =>
	import("@/components/admin/tools/panels/pipeline-explorer-panel").then((m) => ({
		default: m.PipelineExplorerPanel,
	}))
);
const TuningPanel = lazy(() =>
	import("@/components/admin/tools/panels/tuning-panel").then((m) => ({
		default: m.TuningPanel,
	}))
);
const DeployPanel = lazy(() =>
	import("@/components/admin/tools/panels/deploy-panel").then((m) => ({
		default: m.DeployPanel,
	}))
);
const CalibrationTab = lazy(() =>
	import("@/components/admin/tabs/calibration-tab").then((m) => ({
		default: m.CalibrationTab,
	}))
);
const MetadataTab = lazy(() =>
	import("@/components/admin/tabs/metadata-tab").then((m) => ({
		default: m.MetadataTab,
	}))
);
const OverviewTab = lazy(() =>
	import("@/components/admin/tabs/overview-tab").then((m) => ({
		default: m.OverviewTab,
	}))
);

function PanelFallback() {
	return (
		<div className="flex items-center justify-center h-64">
			<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
		</div>
	);
}

export function ToolAdminDashboard() {
	const [activePanel, setActivePanel] = useState("calibration");
	// Prefetch shared data at dashboard level so all lazy-loaded panels share the cache
	useToolCatalog();

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold tracking-tight">Verktygsadministration</h1>
				<p className="text-muted-foreground mt-1">
					Kalibrering, metadata, pipeline-debug, tuning, eval och deploy — allt på ett ställe.
				</p>
			</div>

			<Alert>
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					<strong>Kalibrering</strong> guidat 3-stegsflöde (audit, eval, auto-optimering).{" "}
					<strong>Metadata</strong> redigerar per-verktyg metadata och vikter.{" "}
					<strong>Överblick</strong> nyckeltal och lifecycle.{" "}
					<strong>Explorer</strong> testar pipelinen live.{" "}
					<strong>Tuning</strong> justerar scoring-vikter visuellt.{" "}
					<strong>Deploy</strong> hanterar lifecycle och rollback.
				</AlertDescription>
			</Alert>

			<Tabs value={activePanel} onValueChange={setActivePanel}>
				<TabsList className="flex w-full flex-wrap">
					<TabsTrigger value="calibration" className="gap-1.5">
						<FlaskConical className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Kalibrering</span>
						<span className="sm:hidden">Kalib.</span>
					</TabsTrigger>
					<TabsTrigger value="metadata" className="gap-1.5">
						<BookOpen className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Metadata</span>
						<span className="sm:hidden">Meta</span>
					</TabsTrigger>
					<TabsTrigger value="overview" className="gap-1.5">
						<BarChart3 className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Överblick</span>
						<span className="sm:hidden">Överbl.</span>
					</TabsTrigger>
					<TabsTrigger value="explorer" className="gap-1.5">
						<Search className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Pipeline Explorer</span>
						<span className="sm:hidden">Explorer</span>
					</TabsTrigger>
					<TabsTrigger value="tuning" className="gap-1.5">
						<SlidersHorizontal className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Tuning</span>
						<span className="sm:hidden">Tuning</span>
					</TabsTrigger>
					<TabsTrigger value="deploy" className="gap-1.5">
						<Rocket className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Deploy & Ops</span>
						<span className="sm:hidden">Deploy</span>
					</TabsTrigger>
				</TabsList>

				<TabsContent value="calibration" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<CalibrationTab />
					</Suspense>
				</TabsContent>

				<TabsContent value="metadata" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<MetadataTab />
					</Suspense>
				</TabsContent>

				<TabsContent value="overview" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<OverviewTab />
					</Suspense>
				</TabsContent>

				<TabsContent value="explorer" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<PipelineExplorerPanel />
					</Suspense>
				</TabsContent>

				<TabsContent value="tuning" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<TuningPanel />
					</Suspense>
				</TabsContent>

				<TabsContent value="deploy" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<DeployPanel />
					</Suspense>
				</TabsContent>
			</Tabs>
		</div>
	);
}
