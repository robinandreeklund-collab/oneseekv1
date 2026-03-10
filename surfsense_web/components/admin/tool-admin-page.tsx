"use client";

/**
 * v2 Admin Tools — Unified 3-tab dashboard.
 *
 * Tab 1: Metadata      — tool metadata editing + retrieval tuning + lock management
 * Tab 2: Kalibrering   — metadata audit, eval workflow, auto-loop, suggestions
 * Tab 3: Överblick     — key metrics, trends, lifecycle table, audit trail
 *
 * Replaces:
 * - tool-settings-page.tsx (5283 lines — DEPRECATED)
 * - metadata-catalog-tab.tsx (4221 lines — delegated via CalibrationTab)
 * - tool-lifecycle-page.tsx (427 lines — merged into OverviewTab)
 */

import { AlertCircle, Loader2 } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const MetadataTab = lazy(() =>
	import("@/components/admin/tabs/metadata-tab").then((m) => ({
		default: m.MetadataTab,
	}))
);
const CalibrationTab = lazy(() =>
	import("@/components/admin/tabs/calibration-tab").then((m) => ({
		default: m.CalibrationTab,
	}))
);
const OverviewTab = lazy(() =>
	import("@/components/admin/tabs/overview-tab").then((m) => ({
		default: m.OverviewTab,
	}))
);

function TabFallback() {
	return (
		<div className="flex items-center justify-center h-64">
			<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
		</div>
	);
}

export function ToolAdminPage() {
	const [activeTab, setActiveTab] = useState("metadata");

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold tracking-tight">Verktygsadministration</h1>
				<p className="text-muted-foreground mt-1">
					Metadata, kalibrering och lifecycle för alla verktyg.
				</p>
			</div>

			<Alert>
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					<strong>Metadata</strong> styr verklig tool_retrieval. <strong>Kalibrering</strong> kör
					audit, eval och optimering i dry-run. <strong>Överblick</strong> visar status, trender och
					lifecycle.
				</AlertDescription>
			</Alert>

			<Tabs value={activeTab} onValueChange={setActiveTab}>
				<TabsList>
					<TabsTrigger value="metadata">Metadata</TabsTrigger>
					<TabsTrigger value="calibration">Kalibrering</TabsTrigger>
					<TabsTrigger value="overview">Överblick &amp; Lifecycle</TabsTrigger>
				</TabsList>

				<TabsContent value="metadata" className="mt-6">
					<Suspense fallback={<TabFallback />}>
						<MetadataTab />
					</Suspense>
				</TabsContent>

				<TabsContent value="calibration" className="mt-6">
					<Suspense fallback={<TabFallback />}>
						<CalibrationTab />
					</Suspense>
				</TabsContent>

				<TabsContent value="overview" className="mt-6">
					<Suspense fallback={<TabFallback />}>
						<OverviewTab />
					</Suspense>
				</TabsContent>
			</Tabs>
		</div>
	);
}
