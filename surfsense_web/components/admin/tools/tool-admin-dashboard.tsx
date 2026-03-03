"use client";

/**
 * v3 Admin Tools Dashboard — 5-panel layout.
 *
 * Panel 1: Pipeline Explorer — Query → Intent → Agent → Tool debug
 * Panel 2: Verktygskatalog  — Domain-grouped catalog with inline editing
 * Panel 3: Tuning & Vikter  — Visual sliders, thresholds, radar chart
 * Panel 4: Eval & Audit     — Eval with batch/parallel, audit, suggestions
 * Panel 5: Deploy & Ops     — Lifecycle, rollback, routing phase, audit trail
 */

import {
	AlertCircle,
	BookOpen,
	FlaskConical,
	Loader2,
	Rocket,
	Search,
	SlidersHorizontal,
} from "lucide-react";
import React, { lazy, Suspense, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const PipelineExplorerPanel = lazy(() =>
	import("@/components/admin/tools/panels/pipeline-explorer-panel").then((m) => ({
		default: m.PipelineExplorerPanel,
	}))
);
const ToolCatalogPanel = lazy(() =>
	import("@/components/admin/tools/panels/tool-catalog-panel").then((m) => ({
		default: m.ToolCatalogPanel,
	}))
);
const TuningPanel = lazy(() =>
	import("@/components/admin/tools/panels/tuning-panel").then((m) => ({
		default: m.TuningPanel,
	}))
);
const EvalPanel = lazy(() =>
	import("@/components/admin/tools/panels/eval-panel").then((m) => ({
		default: m.EvalPanel,
	}))
);
const DeployPanel = lazy(() =>
	import("@/components/admin/tools/panels/deploy-panel").then((m) => ({
		default: m.DeployPanel,
	}))
);

class EvalPanelErrorBoundary extends React.Component<
	{ children: React.ReactNode },
	{ hasError: boolean; message?: string; stack?: string }
> {
	constructor(props: { children: React.ReactNode }) {
		super(props);
		this.state = { hasError: false, message: undefined, stack: undefined };
	}

	static getDerivedStateFromError(error: Error) {
		return { hasError: true, message: error?.message, stack: error?.stack };
	}

	componentDidCatch(error: Error, info: React.ErrorInfo) {
		console.error("Eval & Audit panel crashed (dashboard boundary)", error, info);
	}

	render() {
		if (this.state.hasError) {
			return (
				<Alert className="flex flex-col gap-2">
					<div className="flex items-center gap-2">
						<AlertCircle className="h-4 w-4" />
						<span className="font-medium">Eval &amp; Audit kunde inte laddas</span>
					</div>
					<span className="text-sm text-muted-foreground">
						{this.state.message || "Okänt fel"}
					</span>
					{this.state.stack && (
						<pre className="text-xs whitespace-pre-wrap bg-muted/60 rounded p-2">{this.state.stack}</pre>
					)}
				</Alert>
			);
		}
		return this.props.children;
	}
}

function PanelFallback() {
	return (
		<div className="flex items-center justify-center h-64">
			<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
		</div>
	);
}

export function ToolAdminDashboard() {
	const [activePanel, setActivePanel] = useState("explorer");

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold tracking-tight">Verktygsadministration</h1>
				<p className="text-muted-foreground mt-1">
					Pipeline-debug, metadata, tuning, eval och deploy — allt på ett ställe.
				</p>
			</div>

			<Alert>
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					<strong>Explorer</strong> testar pipelinen live. <strong>Katalog</strong> redigerar
					metadata som styr retrieval. <strong>Tuning</strong> justerar scoring-vikter.{" "}
					<strong>Eval</strong> kör batch/parallell-tester. <strong>Deploy</strong> hanterar
					lifecycle och rollback.
				</AlertDescription>
			</Alert>

			<Tabs value={activePanel} onValueChange={setActivePanel}>
				<TabsList className="grid w-full grid-cols-5">
					<TabsTrigger value="explorer" className="gap-1.5">
						<Search className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Pipeline Explorer</span>
						<span className="sm:hidden">Explorer</span>
					</TabsTrigger>
					<TabsTrigger value="catalog" className="gap-1.5">
						<BookOpen className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Katalog</span>
						<span className="sm:hidden">Katalog</span>
					</TabsTrigger>
					<TabsTrigger value="tuning" className="gap-1.5">
						<SlidersHorizontal className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Tuning</span>
						<span className="sm:hidden">Tuning</span>
					</TabsTrigger>
					<TabsTrigger value="eval" className="gap-1.5">
						<FlaskConical className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Eval & Audit</span>
						<span className="sm:hidden">Eval</span>
					</TabsTrigger>
					<TabsTrigger value="deploy" className="gap-1.5">
						<Rocket className="h-3.5 w-3.5" />
						<span className="hidden sm:inline">Deploy & Ops</span>
						<span className="sm:hidden">Deploy</span>
					</TabsTrigger>
				</TabsList>

				<TabsContent value="explorer" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<PipelineExplorerPanel />
					</Suspense>
				</TabsContent>

				<TabsContent value="catalog" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<ToolCatalogPanel />
					</Suspense>
				</TabsContent>

				<TabsContent value="tuning" className="mt-6">
					<Suspense fallback={<PanelFallback />}>
						<TuningPanel />
					</Suspense>
				</TabsContent>

				<TabsContent value="eval" className="mt-6">
					<EvalPanelErrorBoundary>
						<Suspense fallback={<PanelFallback />}>
							<EvalPanel />
						</Suspense>
					</EvalPanelErrorBoundary>
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
