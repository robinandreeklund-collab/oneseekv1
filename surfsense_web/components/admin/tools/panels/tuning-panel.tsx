"use client";

/**
 * Tuning Panel — Panel 3
 *
 * Visual sliders for retrieval scoring weights, auto-select thresholds,
 * Top-K parameters, and advanced adaptive settings.
 */

import { useQueryClient } from "@tanstack/react-query";
import { Info, Loader2, RotateCcw, Save } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useToolCatalog } from "@/components/admin/tools/hooks/use-tool-catalog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { ToolRetrievalTuning } from "@/contracts/types/admin-tool-settings.types";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";

// ---------------------------------------------------------------------------
// Labeled slider
// ---------------------------------------------------------------------------

function WeightSlider({
	label,
	tooltip,
	value,
	onChange,
	min = 0,
	max = 5,
	step = 0.1,
	unit = "",
}: {
	label: string;
	tooltip: string;
	value: number;
	onChange: (v: number) => void;
	min?: number;
	max?: number;
	step?: number;
	unit?: string;
}) {
	return (
		<div className="space-y-2">
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-1.5">
					<Label className="text-sm">{label}</Label>
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
							</TooltipTrigger>
							<TooltipContent side="right" className="max-w-xs">
								<p className="text-xs">{tooltip}</p>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>
				</div>
				<span className="font-mono text-sm tabular-nums w-16 text-right">
					{value.toFixed(step < 1 ? (step < 0.1 ? 2 : 1) : 0)}
					{unit}
				</span>
			</div>
			<Slider
				value={[value]}
				onValueChange={([v]) => onChange(v)}
				min={min}
				max={max}
				step={step}
				className="w-full"
			/>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Weight balance visualization
// ---------------------------------------------------------------------------

function WeightBar({
	weights,
}: {
	weights: Array<{ label: string; value: number; color: string }>;
}) {
	const total = weights.reduce((sum, w) => sum + Math.max(0, w.value), 0);
	if (total === 0) return null;

	return (
		<div className="space-y-2">
			<p className="text-xs text-muted-foreground font-medium">Viktbalans</p>
			<div className="flex h-4 rounded-full overflow-hidden bg-muted">
				{weights.map((w) => {
					const pct = (Math.max(0, w.value) / total) * 100;
					if (pct < 1) return null;
					return (
						<div
							key={w.label}
							className={`${w.color} transition-all duration-300`}
							style={{ width: `${pct}%` }}
							title={`${w.label}: ${pct.toFixed(1)}%`}
						/>
					);
				})}
			</div>
			<div className="flex flex-wrap gap-x-3 gap-y-1">
				{weights.map((w) => {
					const pct = total > 0 ? (Math.max(0, w.value) / total) * 100 : 0;
					return (
						<div key={w.label} className="flex items-center gap-1.5 text-xs">
							<div className={`h-2 w-2 rounded-full ${w.color}`} />
							<span className="text-muted-foreground">{w.label}</span>
							<span className="tabular-nums">{pct.toFixed(0)}%</span>
						</div>
					);
				})}
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function TuningPanel() {
	const queryClient = useQueryClient();
	const { retrievalTuning, refetch, isLoading } = useToolCatalog();

	const [draft, setDraft] = useState<ToolRetrievalTuning | null>(null);
	const [isSaving, setIsSaving] = useState(false);

	useEffect(() => {
		if (retrievalTuning && !draft) {
			setDraft({ ...retrievalTuning });
		}
	}, [retrievalTuning, draft]);

	const hasChanges = useMemo(() => {
		if (!draft || !retrievalTuning) return false;
		return JSON.stringify(draft) !== JSON.stringify(retrievalTuning);
	}, [draft, retrievalTuning]);

	const update = useCallback(
		<K extends keyof ToolRetrievalTuning>(key: K, value: ToolRetrievalTuning[K]) => {
			setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
		},
		[]
	);

	const save = useCallback(async () => {
		if (!draft) return;
		setIsSaving(true);
		try {
			await adminToolSettingsApiService.updateRetrievalTuning(draft);
			await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			await refetch();
			toast.success("Sparade retrieval-vikter");
		} catch {
			toast.error("Kunde inte spara retrieval-vikter");
		} finally {
			setIsSaving(false);
		}
	}, [draft, queryClient, refetch]);

	const reset = useCallback(() => {
		if (retrievalTuning) {
			setDraft({ ...retrievalTuning });
			toast.info("Vikter återställda till senast sparade.");
		}
	}, [retrievalTuning]);

	if (isLoading || !draft) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	const weightItems = [
		{ label: "Namn", value: draft.name_match_weight, color: "bg-blue-500" },
		{ label: "Nyckelord", value: draft.keyword_weight, color: "bg-emerald-500" },
		{ label: "Beskrivning", value: draft.description_token_weight, color: "bg-amber-500" },
		{ label: "Exempel", value: draft.example_query_weight, color: "bg-purple-500" },
		{ label: "Sem. Emb.", value: draft.semantic_embedding_weight ?? 0, color: "bg-pink-500" },
		{ label: "Str. Emb.", value: draft.structural_embedding_weight ?? 0, color: "bg-cyan-500" },
		{ label: "Ns. Boost", value: draft.namespace_boost, color: "bg-orange-500" },
	];

	return (
		<div className="space-y-6">
			{/* Scoring weights */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle>Scoring-vikter</CardTitle>
					<CardDescription>
						Styr hur mycket varje dimension påverkar verktygsval-scoring. Högre vikt = mer
						inflytande vid retrieval.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-6">
					<div className="grid gap-6 md:grid-cols-2">
						<div className="space-y-5">
							<WeightSlider
								label="Namnmatchning"
								tooltip="Vikt för exakt/delvis matchning av verktygsnamn mot frågan"
								value={draft.name_match_weight}
								onChange={(v) => update("name_match_weight", v)}
							/>
							<WeightSlider
								label="Nyckelord"
								tooltip="Vikt för nyckelordsmatchning (keyword overlap)"
								value={draft.keyword_weight}
								onChange={(v) => update("keyword_weight", v)}
							/>
							<WeightSlider
								label="Beskrivning"
								tooltip="Vikt för token-matchning i verktygsbeskrivningen"
								value={draft.description_token_weight}
								onChange={(v) => update("description_token_weight", v)}
							/>
							<WeightSlider
								label="Exempelfrågor"
								tooltip="Vikt för matchning mot konfigurerade exempelfrågor"
								value={draft.example_query_weight}
								onChange={(v) => update("example_query_weight", v)}
							/>
						</div>
						<div className="space-y-5">
							<WeightSlider
								label="Semantisk embedding"
								tooltip="Vikt för semantisk vektorlikhet (innehållsbaserad)"
								value={draft.semantic_embedding_weight ?? 0}
								onChange={(v) => update("semantic_embedding_weight", v)}
							/>
							<WeightSlider
								label="Strukturell embedding"
								tooltip="Vikt för strukturell vektorlikhet (schema/format)"
								value={draft.structural_embedding_weight ?? 0}
								onChange={(v) => update("structural_embedding_weight", v)}
							/>
							<WeightSlider
								label="Namespace boost"
								tooltip="Extra poäng om verktyget är i samma namespace-hierarki"
								value={draft.namespace_boost}
								onChange={(v) => update("namespace_boost", v)}
							/>
						</div>
					</div>

					<Separator />

					<WeightBar weights={weightItems} />
				</CardContent>
			</Card>

			{/* Auto-select thresholds */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle>Auto-select tröskelvärden</CardTitle>
					<CardDescription>
						Styr när verktyg/agenter väljs automatiskt utan LLM-rankering. Score-tröskel = minsta
						poäng, Margin = minimalt avstånd till näst bästa.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-5">
					<div className="grid gap-6 md:grid-cols-2">
						<div className="space-y-5">
							<p className="text-sm font-medium">Verktyg</p>
							<WeightSlider
								label="Score-tröskel"
								tooltip="Minsta score för att auto-välja verktyg (0.0-1.0)"
								value={draft.tool_auto_score_threshold ?? 0.6}
								onChange={(v) => update("tool_auto_score_threshold", v)}
								min={0}
								max={1}
								step={0.01}
							/>
							<WeightSlider
								label="Margin-tröskel"
								tooltip="Minsta avstånd till näst bästa verktyg"
								value={draft.tool_auto_margin_threshold ?? 0.25}
								onChange={(v) => update("tool_auto_margin_threshold", v)}
								min={0}
								max={1}
								step={0.01}
							/>
						</div>
						<div className="space-y-5">
							<p className="text-sm font-medium">Agent</p>
							<WeightSlider
								label="Score-tröskel"
								tooltip="Minsta score för att auto-välja agent"
								value={draft.agent_auto_score_threshold ?? 0.55}
								onChange={(v) => update("agent_auto_score_threshold", v)}
								min={0}
								max={1}
								step={0.01}
							/>
							<WeightSlider
								label="Margin-tröskel"
								tooltip="Minsta avstånd till näst bästa agent"
								value={draft.agent_auto_margin_threshold ?? 0.18}
								onChange={(v) => update("agent_auto_margin_threshold", v)}
								min={0}
								max={1}
								step={0.01}
							/>
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Top-K and reranking */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle>Top-K & Reranking</CardTitle>
					<CardDescription>
						Hur många kandidater som beaktas i varje steg av pipelinen.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-5">
					<div className="grid gap-6 md:grid-cols-3">
						<div className="space-y-2">
							<Label className="text-sm">Intent Top-K</Label>
							<Input
								type="number"
								min={2}
								max={8}
								value={draft.intent_candidate_top_k ?? 3}
								onChange={(e) =>
									update("intent_candidate_top_k", Number.parseInt(e.target.value || "3", 10))
								}
								className="h-9"
							/>
							<p className="text-xs text-muted-foreground">Antal intent-kandidater</p>
						</div>
						<div className="space-y-2">
							<Label className="text-sm">Agent Top-K</Label>
							<Input
								type="number"
								min={2}
								max={8}
								value={draft.agent_candidate_top_k ?? 3}
								onChange={(e) =>
									update("agent_candidate_top_k", Number.parseInt(e.target.value || "3", 10))
								}
								className="h-9"
							/>
							<p className="text-xs text-muted-foreground">Antal agent-kandidater</p>
						</div>
						<div className="space-y-2">
							<Label className="text-sm">Tool Top-K</Label>
							<Input
								type="number"
								min={2}
								max={10}
								value={draft.tool_candidate_top_k ?? 5}
								onChange={(e) =>
									update("tool_candidate_top_k", Number.parseInt(e.target.value || "5", 10))
								}
								className="h-9"
							/>
							<p className="text-xs text-muted-foreground">Antal verktygs-kandidater</p>
						</div>
					</div>
					<div className="space-y-2">
						<Label className="text-sm">Rerank-kandidater</Label>
						<Input
							type="number"
							min={1}
							max={100}
							value={draft.rerank_candidates}
							onChange={(e) =>
								update("rerank_candidates", Math.max(1, Number.parseInt(e.target.value || "1", 10)))
							}
							className="h-9 w-32"
						/>
						<p className="text-xs text-muted-foreground">
							Antal kandidater att skicka till reranker-modellen
						</p>
					</div>
				</CardContent>
			</Card>

			{/* Advanced / adaptive */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle>Avancerat</CardTitle>
					<CardDescription>Adaptiva trösklar, intent-vikter och feedback-databas.</CardDescription>
				</CardHeader>
				<CardContent className="space-y-5">
					<div className="grid gap-6 md:grid-cols-2">
						<WeightSlider
							label="Adaptive delta"
							tooltip="Hur mycket adaptiva trösklar justeras per feedback-signal"
							value={draft.adaptive_threshold_delta ?? 0.08}
							onChange={(v) => update("adaptive_threshold_delta", v)}
							max={0.5}
							step={0.01}
						/>
						<div className="space-y-2">
							<Label className="text-sm">Adaptive min samples</Label>
							<Input
								type="number"
								min={1}
								value={draft.adaptive_min_samples ?? 8}
								onChange={(e) =>
									update("adaptive_min_samples", Number.parseInt(e.target.value || "8", 10))
								}
								className="h-9 w-32"
							/>
							<p className="text-xs text-muted-foreground">
								Minsta antal samples innan adaptiv justering
							</p>
						</div>
						<WeightSlider
							label="Intent lexical vikt"
							tooltip="Vikt för lexikal matchning vid intent-retrieval"
							value={draft.intent_lexical_weight ?? 1}
							onChange={(v) => update("intent_lexical_weight", v)}
						/>
						<WeightSlider
							label="Intent semantic vikt"
							tooltip="Vikt för embedding-matchning vid intent-retrieval"
							value={draft.intent_embedding_weight ?? 1}
							onChange={(v) => update("intent_embedding_weight", v)}
						/>
					</div>

					<Separator />

					<div className="flex items-center gap-6">
						<div className="flex items-center gap-3">
							<Switch
								checked={draft.live_routing_enabled ?? false}
								onCheckedChange={(v) => update("live_routing_enabled", v)}
							/>
							<Label className="text-sm">Live routing aktiverat</Label>
						</div>
						<div className="space-y-1">
							<Label className="text-xs">Live-routing fas</Label>
							<Select
								value={draft.live_routing_phase ?? "shadow"}
								onValueChange={(v) =>
									update("live_routing_phase", v as ToolRetrievalTuning["live_routing_phase"])
								}
							>
								<SelectTrigger className="h-8 w-48 text-xs">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="shadow">Shadow</SelectItem>
									<SelectItem value="tool_gate">Tool gate</SelectItem>
									<SelectItem value="agent_auto">Agent auto</SelectItem>
									<SelectItem value="adaptive">Adaptive</SelectItem>
									<SelectItem value="intent_finetune">Intent finetune</SelectItem>
								</SelectContent>
							</Select>
						</div>
						<div className="flex items-center gap-3">
							<Switch
								checked={draft.retrieval_feedback_db_enabled ?? false}
								onCheckedChange={(v) => update("retrieval_feedback_db_enabled", v)}
							/>
							<Label className="text-sm">Feedback-databas aktiverad</Label>
						</div>
					</div>
					<p className="text-xs text-muted-foreground">
						Feedback-databas lagrar retrieval-signaler för adaptiva trösklar; aktiveras via togglen ovan.
					</p>
				</CardContent>
			</Card>

			{/* Save bar */}
			<div className="flex items-center gap-3 sticky bottom-4">
				<Button onClick={save} disabled={!hasChanges || isSaving} className="gap-2 shadow-lg">
					{isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
					{isSaving ? "Sparar vikter..." : "Spara vikter"}
				</Button>
				<Button variant="outline" onClick={reset} disabled={!hasChanges} className="gap-2">
					<RotateCcw className="h-4 w-4" />
					Återställ
				</Button>
				{hasChanges && (
					<Badge variant="outline" className="text-xs">
						Osparade ändringar
					</Badge>
				)}
			</div>
		</div>
	);
}
