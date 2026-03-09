"use client";

/**
 * CalibrationTab — Flik 2: Kalibrering
 *
 * Fas-panel ÖVERST visar live routing-fas (Shadow → Tool gate → Agent auto → Adaptive → Intent finetune).
 *
 * Guidat 3-stegsflöde:
 *   Steg 1: Metadata Audit (egen audit-sektion med 3-layer accuracy + kollisionsrapport)
 *   Steg 2: Eval (generering + agentval eval + API input eval + resultat + diff-vy)
 *   Steg 3: Auto-optimering (auto-loop med holdout + lifecycle-promotion)
 */

import { AlertCircle, Loader2 } from "lucide-react";
import {
	type LiveRoutingPhaseValue,
	useCalibrationTab,
} from "@/components/admin/hooks/use-calibration-tab";
import {
	formatAutoLoopStopReason,
	formatPercent,
	formatSignedPercent,
} from "@/components/admin/hooks/use-eval-parsers";
import { ComparisonInsights as SharedComparisonInsights } from "@/components/admin/shared/comparison-insights";
import { DifficultyBreakdown as SharedDifficultyBreakdown } from "@/components/admin/shared/difficulty-breakdown";
import { EvalJobStatusCard } from "@/components/admin/shared/eval-job-status-card";
import { EvalPerTestCard } from "@/components/admin/shared/eval-per-test-card";
import { IntentSuggestionsCard } from "@/components/admin/shared/intent-suggestions-card";
import { LifecycleBadge } from "@/components/admin/shared/lifecycle-badge";
import { PromptSuggestionsCard } from "@/components/admin/shared/prompt-suggestions-card";
import { SuggestionDiffView } from "@/components/admin/shared/suggestion-diff-view";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CalibrationTab() {
	const ctx = useCalibrationTab();

	if (ctx.isLoading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	if (ctx.error) {
		return (
			<Alert variant="destructive">
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					Fel vid hämtning av verktygsdata. Kontrollera att du har administratörsbehörighet.
				</AlertDescription>
			</Alert>
		);
	}

	return (
		<div className="space-y-6">
			{/* ================================================================ */}
			{/* FAS-PANEL ÖVERST                                                */}
			{/* ================================================================ */}
			<Card>
				<CardHeader>
					<CardTitle>Fas-panel</CardTitle>
					<CardDescription>
						Live routing-fas, embedding-modell, kalibreringsdatum och antal verktyg.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="flex flex-wrap items-center gap-2">
						{(["shadow", "tool_gate", "agent_auto", "adaptive", "intent_finetune"] as const).map(
							(phase) => {
								const currentPhase =
									ctx.draftRetrievalTuning?.live_routing_phase ??
									ctx.data?.retrieval_tuning?.live_routing_phase ??
									"shadow";
								const isActive = phase === currentPhase;
								const labels: Record<string, string> = {
									shadow: "Shadow",
									tool_gate: "Tool gate",
									agent_auto: "Agent auto",
									adaptive: "Adaptive",
									intent_finetune: "Intent finetune",
								};
								return (
									<Badge
										key={phase}
										variant={isActive ? "default" : "outline"}
										className={isActive ? "bg-green-600 hover:bg-green-700" : ""}
									>
										{isActive ? "●" : "○"} {labels[phase]}
									</Badge>
								);
							}
						)}
					</div>
					<div className="flex flex-wrap items-center gap-3">
						<div className="flex items-center gap-2">
							<Label htmlFor="phase-select">Byt fas</Label>
							<select
								id="phase-select"
								className="h-9 rounded-md border bg-background px-3 text-sm"
								value={ctx.draftRetrievalTuning?.live_routing_phase ?? "shadow"}
								onChange={(e) => ctx.handleChangePhase(e.target.value as LiveRoutingPhaseValue)}
							>
								<option value="shadow">Shadow</option>
								<option value="tool_gate">Tool gate</option>
								<option value="agent_auto">Agent auto</option>
								<option value="adaptive">Adaptive</option>
								<option value="intent_finetune">Intent finetune</option>
							</select>
						</div>
					</div>
					<div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5 text-sm">
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Metadata version</p>
							<p className="font-medium font-mono text-xs">
								{ctx.data?.metadata_version_hash?.slice(0, 12) ?? "-"}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Antal verktyg</p>
							<p className="font-medium">
								{ctx.data?.categories?.reduce((sum, cat) => sum + cat.tools.length, 0) ?? 0}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Lifecycle</p>
							<p className="font-medium">
								{ctx.lifecycleData?.live_count ?? 0} Live / {ctx.lifecycleData?.review_count ?? 0}{" "}
								Review
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Embedding-modell</p>
							<p className="font-medium text-xs truncate">
								{(ctx.data as any)?.embedding_model ?? "okänd"}
							</p>
						</div>
						<div className="rounded border p-3">
							<p className="text-xs text-muted-foreground">Kalibrerad</p>
							<p className="font-medium text-xs">
								{(ctx.data as any)?.calibrated_at
									? new Date((ctx.data as any).calibrated_at).toLocaleString("sv-SE")
									: "-"}
							</p>
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Guided 3-step navigation */}
			<Card>
				<CardHeader>
					<CardTitle>Kalibreringsflöde</CardTitle>
					<CardDescription>Guidat 3-stegsflöde: audit, eval och auto-optimering.</CardDescription>
				</CardHeader>
				<CardContent>
					<Tabs
						value={ctx.calibrationStep}
						onValueChange={(v) => ctx.setCalibrationStep(v as "audit" | "eval" | "auto")}
					>
						<TabsList>
							<TabsTrigger value="audit">Steg 1: Metadata Audit</TabsTrigger>
							<TabsTrigger value="eval">Steg 2: Eval</TabsTrigger>
							<TabsTrigger value="auto">Steg 3: Auto-optimering</TabsTrigger>
						</TabsList>
					</Tabs>
				</CardContent>
			</Card>

			{/* ================================================================ */}
			{/* STEG 1: METADATA AUDIT                                          */}
			{/* ================================================================ */}
			{ctx.calibrationStep === "audit" && (
				<div className="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>Metadata Audit</CardTitle>
							<CardDescription>
								Kör en 3-layer audit (intent, agent, tool) med probe-frågor och analysera
								kollisioner.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="flex flex-wrap items-center gap-3">
								<div className="flex items-center gap-2">
									<Label htmlFor="audit-provider-filter">Provider</Label>
									<select
										id="audit-provider-filter"
										className="h-10 rounded-md border bg-background px-3 text-sm max-w-[200px]"
										value={ctx.auditProviderFilter}
										onChange={(e) => ctx.setAuditProviderFilter(e.target.value)}
									>
										<option value="all">Alla providers</option>
										{ctx.apiProviders.map((p) => (
											<option key={p.provider_key} value={p.provider_key}>
												{p.provider_name}
											</option>
										))}
									</select>
								</div>
								<div className="flex items-center gap-2">
									<Label htmlFor="audit-max-tools">Max verktyg</Label>
									<Input
										id="audit-max-tools"
										type="number"
										min={5}
										max={200}
										value={ctx.auditMaxTools}
										onChange={(e) =>
											ctx.setAuditMaxTools(Number.parseInt(e.target.value || "25", 10))
										}
										className="w-24"
									/>
								</div>
								<div className="flex items-center gap-2">
									<Label htmlFor="audit-retrieval-limit">Retrieval K</Label>
									<Input
										id="audit-retrieval-limit"
										type="number"
										min={1}
										max={15}
										value={ctx.auditRetrievalLimit}
										onChange={(e) =>
											ctx.setAuditRetrievalLimit(Number.parseInt(e.target.value || "5", 10))
										}
										className="w-24"
									/>
								</div>
								<div className="flex items-center gap-2">
									<Switch
										checked={ctx.includeDraftMetadata}
										onCheckedChange={ctx.setIncludeDraftMetadata}
									/>
									<span className="text-sm">Inkludera draft</span>
								</div>
								<Button onClick={ctx.handleRunAudit} disabled={ctx.isRunningAudit}>
									{ctx.isRunningAudit ? "Kör audit..." : "Kör audit"}
								</Button>
								<Button
									variant="outline"
									onClick={ctx.handleRunSeparation}
									disabled={ctx.isRunningSeparation || !ctx.auditResult}
								>
									{ctx.isRunningSeparation ? "Separerar..." : "Separera kollisioner"}
								</Button>
							</div>
						</CardContent>
					</Card>

					{ctx.auditResult && (
						<Card>
							<CardHeader>
								<CardTitle>Audit-resultat</CardTitle>
								<CardDescription>
									{ctx.auditResult.summary.total_probes} probes · metadata version{" "}
									{ctx.auditResult.metadata_version_hash.slice(0, 8)}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid gap-4 md:grid-cols-3">
									<div className="rounded border p-3 text-center">
										<p className="text-xs text-muted-foreground">Intent accuracy</p>
										<p className="text-2xl font-semibold">
											{(ctx.auditResult.summary.intent_accuracy * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3 text-center">
										<p className="text-xs text-muted-foreground">Agent accuracy</p>
										<p className="text-2xl font-semibold">
											{(ctx.auditResult.summary.agent_accuracy * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3 text-center">
										<p className="text-xs text-muted-foreground">Tool accuracy</p>
										<p className="text-2xl font-semibold">
											{(ctx.auditResult.summary.tool_accuracy * 100).toFixed(1)}%
										</p>
									</div>
								</div>
								<div className="grid gap-4 md:grid-cols-2">
									{ctx.auditResult.summary.agent_accuracy_given_intent_correct != null && (
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Agent | Intent korrekt</p>
											<p className="text-lg font-semibold">
												{(
													ctx.auditResult.summary.agent_accuracy_given_intent_correct * 100
												).toFixed(1)}
												%
											</p>
										</div>
									)}
									{ctx.auditResult.summary.tool_accuracy_given_intent_agent_correct != null && (
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Tool | Intent+Agent korrekt</p>
											<p className="text-lg font-semibold">
												{(
													ctx.auditResult.summary.tool_accuracy_given_intent_agent_correct * 100
												).toFixed(1)}
												%
											</p>
										</div>
									)}
								</div>
								{ctx.auditResult.summary.tool_confusion_matrix.length > 0 && (
									<div className="rounded border p-3 space-y-2">
										<p className="text-sm font-medium">
											Kollisionsrapport ({ctx.auditResult.summary.tool_confusion_matrix.length} par)
										</p>
										<div className="max-h-64 overflow-auto space-y-1">
											{ctx.auditResult.summary.tool_confusion_matrix
												.slice(0, 15)
												.map((pair, idx) => (
													<div
														key={`collision-${idx}`}
														className="flex items-center gap-2 text-xs rounded bg-muted/40 px-2 py-1"
													>
														<Badge variant="outline">{pair.expected_label}</Badge>
														<span className="text-muted-foreground">↔</span>
														<Badge variant="outline">{pair.predicted_label}</Badge>
														<span className="text-muted-foreground ml-auto">{pair.count} fel</span>
													</div>
												))}
										</div>
									</div>
								)}
								{ctx.auditResult.summary.vector_recall_summary && (
									<div className="grid gap-3 md:grid-cols-3 text-sm">
										<Badge variant="outline">
											Vektor-kandidater:{" "}
											{ctx.auditResult.summary.vector_recall_summary.probes_with_vector_candidates}
										</Badge>
										<Badge variant="outline">
											Top-1 från vektor:{" "}
											{ctx.auditResult.summary.vector_recall_summary.probes_with_top1_from_vector}
										</Badge>
										<Badge variant="outline">
											Förväntad i top-K:{" "}
											{
												ctx.auditResult.summary.vector_recall_summary
													.probes_with_expected_tool_in_vector_top_k
											}
										</Badge>
									</div>
								)}
								{ctx.auditResult.probes.length > 0 && (
									<details className="rounded border p-3">
										<summary className="text-sm font-medium cursor-pointer">
											Visa probe-detaljer ({ctx.auditResult.probes.length} probes)
										</summary>
										<div className="mt-3 max-h-96 overflow-auto space-y-2">
											{ctx.auditResult.probes.slice(0, 50).map((probe) => (
												<div key={probe.probe_id} className="rounded border p-2 text-xs space-y-1">
													<p className="font-medium">{probe.query}</p>
													<div className="flex flex-wrap gap-2">
														<Badge
															variant={
																probe.intent.predicted_label === probe.intent.expected_label
																	? "outline"
																	: "destructive"
															}
														>
															Intent: {probe.intent.expected_label ?? "-"} →{" "}
															{probe.intent.predicted_label ?? "-"}
														</Badge>
														<Badge
															variant={
																probe.agent.predicted_label === probe.agent.expected_label
																	? "outline"
																	: "destructive"
															}
														>
															Agent: {probe.agent.expected_label ?? "-"} →{" "}
															{probe.agent.predicted_label ?? "-"}
														</Badge>
														<Badge
															variant={
																probe.tool.predicted_label === probe.tool.expected_label
																	? "outline"
																	: "destructive"
															}
														>
															Tool: {probe.tool.expected_label ?? "-"} →{" "}
															{probe.tool.predicted_label ?? "-"}
														</Badge>
													</div>
												</div>
											))}
										</div>
									</details>
								)}
							</CardContent>
						</Card>
					)}

					{ctx.separationResult && (
						<Card>
							<CardHeader>
								<CardTitle>Separationsresultat</CardTitle>
								<CardDescription>Baseline → Final accuracy efter separation</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid gap-4 md:grid-cols-2">
									<div className="rounded border p-3 space-y-1">
										<p className="text-xs text-muted-foreground">Baseline</p>
										<p className="text-sm">
											Intent{" "}
											{(ctx.separationResult.baseline_summary.intent_accuracy * 100).toFixed(1)}% ·
											Agent{" "}
											{(ctx.separationResult.baseline_summary.agent_accuracy * 100).toFixed(1)}% ·
											Tool {(ctx.separationResult.baseline_summary.tool_accuracy * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3 space-y-1">
										<p className="text-xs text-muted-foreground">Slutresultat</p>
										<p className="text-sm">
											Intent {(ctx.separationResult.final_summary.intent_accuracy * 100).toFixed(1)}
											% · Agent{" "}
											{(ctx.separationResult.final_summary.agent_accuracy * 100).toFixed(1)}% · Tool{" "}
											{(ctx.separationResult.final_summary.tool_accuracy * 100).toFixed(1)}%
										</p>
									</div>
								</div>
								{ctx.separationResult.proposed_tool_metadata_patch.length > 0 && (
									<div className="rounded border p-3 space-y-2">
										<p className="text-sm font-medium">
											{ctx.separationResult.proposed_tool_metadata_patch.length} metadata-ändringar
											föreslagna
										</p>
										<Button onClick={ctx.handleApplySeparation}>
											Applicera separationsförslag
										</Button>
									</div>
								)}
							</CardContent>
						</Card>
					)}
				</div>
			)}

			{/* ================================================================ */}
			{/* STEG 2: EVAL                                                    */}
			{/* ================================================================ */}
			{ctx.calibrationStep === "eval" && (
				<div className="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>Flikar för eval-steg</CardTitle>
							<CardDescription>
								Dela upp arbetsflödet i separata steg för tydligare körning och analys.
							</CardDescription>
						</CardHeader>
						<CardContent>
							<Tabs
								value={ctx.evaluationStepTab}
								onValueChange={(value) =>
									ctx.setEvaluationStepTab(
										value as "all" | "guide" | "generation" | "agent_eval" | "api_input"
									)
								}
							>
								<TabsList className="flex flex-wrap">
									<TabsTrigger value="all">Alla steg</TabsTrigger>
									<TabsTrigger value="guide">Guide</TabsTrigger>
									<TabsTrigger value="generation">Generering</TabsTrigger>
									<TabsTrigger value="agent_eval">Agentval Eval</TabsTrigger>
									<TabsTrigger value="api_input">API Input Eval</TabsTrigger>
								</TabsList>
							</Tabs>
						</CardContent>
					</Card>

					{ctx.showGuideSections && (
						<Card>
							<CardHeader>
								<CardTitle>Steg 0: Guide och arbetssätt</CardTitle>
								<CardDescription>
									Följ stegen nedan i ordning för att trimma route, agentval, tool-val, API-input
									och prompts på ett säkert sätt (dry-run).
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4 text-sm">
								<div className="rounded border p-3 space-y-2">
									<p className="font-medium">Steg 1: Förbered test-upplägg</p>
									<ul className="list-disc pl-5 space-y-1 text-muted-foreground">
										<li>
											Börja med <span className="font-medium">Per kategori/API</span> för precision.
										</li>
										<li>
											Använd sedan <span className="font-medium">Global random mix</span> för
											regression.
										</li>
										<li>Rekommendation: 10-15 frågor per kategori och 25-40 frågor globalt.</li>
									</ul>
								</div>
								<div className="rounded border p-3 space-y-2">
									<p className="font-medium">Steg 2: Generera eller ladda eval-JSON</p>
									<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
										<li>Välj Läge, Eval-typ, Provider, Kategori och antal frågor.</li>
										<li>Klicka &quot;Generera + spara eval JSON&quot;.</li>
										<li>Klicka &quot;Ladda i eval-input&quot; på filen i listan.</li>
										<li>Alternativt: ladda upp egen fil eller klistra in i JSON-fältet.</li>
									</ol>
								</div>
								<div className="rounded border p-3 space-y-2">
									<p className="font-medium">Steg 3: Kör Agentval Eval</p>
									<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
										<li>
											Sätt <span className="font-medium">Retrieval K</span> (5 standard, 8-10 för
											svårare).
										</li>
										<li>
											Behåll &quot;Inkludera draft metadata&quot; aktiv för osparade ändringar.
										</li>
										<li>Klicka &quot;Run Tool Evaluation&quot;.</li>
										<li>Kontrollera Route, Sub-route, Agent, Plan och Tool accuracy.</li>
									</ol>
								</div>
								<div className="rounded border p-3 space-y-2">
									<p className="font-medium">Steg 4: Förbättra och kör om</p>
									<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
										<li>
											Använd &quot;Metadata-förslag&quot; för description, keywords och
											exempelfrågor.
										</li>
										<li>Använd &quot;Föreslagen tuning&quot; för retrieval-vikter.</li>
										<li>Använd &quot;Prompt-förslag&quot; för router/agent-prompts.</li>
										<li>Kör om tills resultatet stabiliseras.</li>
									</ol>
								</div>
								<div className="rounded border p-3 space-y-2">
									<p className="font-medium">Steg 5: Kör API Input Eval (utan API-anrop)</p>
									<ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
										<li>Välj suite med required_fields (och gärna field_values).</li>
										<li>Klicka &quot;Run API Input Eval (dry-run)&quot;.</li>
										<li>
											Kontrollera Schema validity, Required-field recall, Field-value accuracy.
										</li>
										<li>Spara &quot;Prompt-förslag&quot; och kör om tills stabilt.</li>
									</ol>
								</div>
								<div className="rounded border p-3 space-y-2">
									<p className="font-medium">Steg 6: Använd holdout (anti-overfitting)</p>
									<ul className="list-disc pl-5 space-y-1 text-muted-foreground">
										<li>Aktivera &quot;Använd holdout-suite&quot;.</li>
										<li>Klistra in separat holdout-JSON eller lägg holdout_tests i huvud-JSON.</li>
										<li>
											Optimera på huvudsuite, godkänn endast ändringar som även förbättrar holdout.
										</li>
									</ul>
								</div>
							</CardContent>
						</Card>
					)}

					{ctx.showGuideSections && (
						<Card>
							<CardHeader>
								<CardTitle>Stegöversikt</CardTitle>
								<CardDescription>
									Arbeta i denna ordning för ett tydligt och repeterbart eval-flöde.
								</CardDescription>
							</CardHeader>
							<CardContent className="flex flex-wrap items-center gap-2 text-xs">
								<Badge variant="secondary">Steg 1: Generera/Ladda frågor</Badge>
								<Badge variant="secondary">
									Steg 2: Agentval Eval (route + agent + tool + plan)
								</Badge>
								<Badge variant="secondary">Steg 3: API Input Eval</Badge>
								<Badge variant="secondary">Steg 4: Holdout + spara förbättringar</Badge>
							</CardContent>
						</Card>
					)}

					{ctx.showGenerationSections && (
						<Card>
							<CardHeader>
								<CardTitle>Steg 1: Generera/Ladda eval-frågor</CardTitle>
								<CardDescription>
									Skapa JSON i rätt format, spara i /eval/api och ladda direkt in i eval-run.
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-6">
									<div className="space-y-2">
										<Label htmlFor="cal-generation-mode">Läge</Label>
										<select
											id="cal-generation-mode"
											className="h-10 w-full rounded-md border bg-background px-3 text-sm"
											value={ctx.generationMode}
											onChange={(event) =>
												ctx.setGenerationMode(
													event.target.value === "global_random"
														? "global_random"
														: event.target.value === "provider"
															? "provider"
															: "category"
												)
											}
										>
											<option value="category">Per kategori/API</option>
											<option value="provider">Huvudkategori/provider</option>
											<option value="global_random">Random mix (global)</option>
										</select>
									</div>
									<div className="space-y-2">
										<Label htmlFor="cal-generation-eval-type">Eval-typ</Label>
										<select
											id="cal-generation-eval-type"
											className="h-10 w-full rounded-md border bg-background px-3 text-sm"
											value={ctx.generationEvalType}
											onChange={(event) =>
												ctx.setGenerationEvalType(
													event.target.value === "api_input" ? "api_input" : "tool_selection"
												)
											}
										>
											<option value="tool_selection">Tool selection</option>
											<option value="api_input">API input</option>
										</select>
									</div>
									<div className="space-y-2">
										<Label htmlFor="cal-generation-provider">Provider</Label>
										<select
											id="cal-generation-provider"
											className="h-10 w-full rounded-md border bg-background px-3 text-sm"
											value={ctx.generationProvider}
											onChange={(event) => ctx.setGenerationProvider(event.target.value)}
										>
											{ctx.generationMode === "global_random" && (
												<option value="all">Alla providers</option>
											)}
											{ctx.apiProviders.map((provider) => (
												<option key={provider.provider_key} value={provider.provider_key}>
													{provider.provider_name}
												</option>
											))}
										</select>
									</div>
									<div className="space-y-2">
										<Label htmlFor="cal-generation-question-count">Antal frågor</Label>
										<Input
											id="cal-generation-question-count"
											type="number"
											min={1}
											max={100}
											value={ctx.generationQuestionCount}
											onChange={(event) =>
												ctx.setGenerationQuestionCount(
													Number.parseInt(event.target.value || "12", 10)
												)
											}
										/>
									</div>
									<div className="space-y-2">
										<Label htmlFor="cal-generation-difficulty">Svårighetsgrad</Label>
										<select
											id="cal-generation-difficulty"
											className="h-10 w-full rounded-md border bg-background px-3 text-sm"
											value={ctx.generationDifficultyProfile}
											onChange={(event) =>
												ctx.setGenerationDifficultyProfile(
													event.target.value === "lätt"
														? "lätt"
														: event.target.value === "medel"
															? "medel"
															: event.target.value === "svår"
																? "svår"
																: "mixed"
												)
											}
										>
											<option value="mixed">Blandad</option>
											<option value="lätt">Lätt</option>
											<option value="medel">Medel</option>
											<option value="svår">Svår</option>
										</select>
									</div>
									<div className="space-y-2">
										<Label htmlFor="cal-generation-eval-name">Eval-namn</Label>
										<Input
											id="cal-generation-eval-name"
											placeholder="scb-prisindex-mars-2026"
											value={ctx.generationEvalName}
											onChange={(event) => ctx.setGenerationEvalName(event.target.value)}
										/>
									</div>
								</div>

								{ctx.generationMode === "category" && (
									<div className="space-y-2">
										<Label htmlFor="cal-generation-category">Kategori</Label>
										<select
											id="cal-generation-category"
											className="h-10 w-full rounded-md border bg-background px-3 text-sm"
											value={ctx.generationCategory}
											onChange={(event) => ctx.setGenerationCategory(event.target.value)}
										>
											{ctx.generationCategoryOptions.length === 0 && (
												<option value="">Inga kategorier hittades</option>
											)}
											{ctx.generationCategoryOptions.map((option) => (
												<option key={option.category_id} value={option.category_id}>
													{option.category_name} ({option.category_id})
												</option>
											))}
										</select>
									</div>
								)}

								<div className="flex flex-wrap items-center gap-2">
									<Button
										onClick={ctx.handleGenerateEvalLibraryFile}
										disabled={ctx.isGeneratingEvalFile}
									>
										{ctx.isGeneratingEvalFile ? "Genererar..." : "Generera + spara eval JSON"}
									</Button>
									{ctx.selectedLibraryPath && (
										<Badge variant="outline">Vald fil: {ctx.selectedLibraryPath}</Badge>
									)}
								</div>

								<div className="rounded border p-3 space-y-2">
									<div className="flex items-center justify-between gap-2">
										<p className="text-sm font-medium">Sparade eval-filer (/eval/api)</p>
										<Button variant="outline" size="sm" onClick={ctx.refreshEvalLibraryFiles}>
											Uppdatera lista
										</Button>
									</div>
									<div className="space-y-2">
										{(ctx.evalLibraryFiles?.items ?? []).length === 0 ? (
											<p className="text-xs text-muted-foreground">Inga sparade filer ännu.</p>
										) : (
											(ctx.evalLibraryFiles?.items ?? []).slice(0, 25).map((item) => (
												<div
													key={item.relative_path}
													className="flex flex-wrap items-center justify-between gap-2 rounded border p-2"
												>
													<div className="space-y-1">
														<p className="text-xs font-medium">{item.file_name}</p>
														<p className="text-xs text-muted-foreground">
															{item.relative_path} ·{" "}
															{new Date(item.created_at).toLocaleString("sv-SE")}
															{typeof item.test_count === "number"
																? ` · ${item.test_count} frågor`
																: ""}
														</p>
													</div>
													<div className="flex items-center gap-2">
														<Button
															variant={
																ctx.selectedLibraryPath === item.relative_path
																	? "default"
																	: "outline"
															}
															size="sm"
															onClick={() => ctx.loadEvalLibraryFile(item.relative_path)}
															disabled={ctx.isLoadingLibraryFile}
														>
															Ladda i eval-input
														</Button>
														<Button
															variant={
																ctx.selectedHoldoutLibraryPath === item.relative_path
																	? "default"
																	: "outline"
															}
															size="sm"
															onClick={() => ctx.loadEvalLibraryFileToHoldout(item.relative_path)}
															disabled={ctx.isLoadingLibraryFile}
														>
															Ladda i holdout
														</Button>
													</div>
												</div>
											))
										)}
									</div>
								</div>
							</CardContent>
						</Card>
					)}

					{/* Eval run controls */}
					{(ctx.showAgentSections || ctx.showApiSections) && (
						<Card>
							<CardHeader>
								<CardTitle>Steg 2: Kör Agentval Eval och API Input Eval</CardTitle>
								<CardDescription>Testa hela agentvalet och API-input i dry-run.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="flex flex-wrap items-center gap-3">
									<Input
										type="file"
										accept="application/json"
										onChange={ctx.uploadEvalFile}
										className="max-w-sm"
									/>
									<div className="flex items-center gap-2">
										<Label htmlFor="cal-retrieval-limit">Retrieval K</Label>
										<Input
											id="cal-retrieval-limit"
											type="number"
											value={ctx.retrievalLimit}
											onChange={(e) =>
												ctx.setRetrievalLimit(Number.parseInt(e.target.value || "5", 10))
											}
											className="w-24"
											min={1}
											max={15}
										/>
									</div>
									<div className="flex items-center gap-2">
										<Switch
											checked={ctx.includeDraftMetadata}
											onCheckedChange={ctx.setIncludeDraftMetadata}
										/>
										<span className="text-sm">Inkludera osparad draft</span>
									</div>
									<div className="flex items-center gap-2">
										<Switch
											checked={ctx.useLlmSupervisorReview}
											onCheckedChange={ctx.setUseLlmSupervisorReview}
										/>
										<span className="text-sm">LLM-granskning</span>
									</div>
									<Button
										onClick={ctx.handleRunEvaluation}
										disabled={ctx.isEvaluating || ctx.isEvalJobRunning}
									>
										{ctx.isEvaluating
											? "Startar agentval-eval..."
											: ctx.isEvalJobRunning
												? "Agentval-eval körs..."
												: "Run Agentval Eval"}
									</Button>
									<Button
										variant="outline"
										onClick={ctx.handleRunApiInputEvaluation}
										disabled={ctx.isApiInputEvaluating || ctx.isApiInputEvalJobRunning}
									>
										{ctx.isApiInputEvaluating
											? "Startar API input eval..."
											: ctx.isApiInputEvalJobRunning
												? "API input eval körs..."
												: "Run API Input Eval (dry-run)"}
									</Button>
								</div>
								<div className="rounded border p-3 space-y-3">
									<div className="flex items-center justify-between gap-2">
										<p className="text-sm font-medium">Eval JSON</p>
										<Button
											variant="outline"
											size="sm"
											onClick={() => ctx.setShowEvalJsonInput((prev) => !prev)}
										>
											{ctx.showEvalJsonInput ? "Minimera JSON-fält" : "Visa JSON-fält"}
										</Button>
									</div>
									{ctx.showEvalJsonInput ? (
										<Textarea
											placeholder='{"eval_name":"...","tests":[...]}'
											value={ctx.evalInput}
											onChange={(e) => ctx.setEvalInput(e.target.value)}
											rows={12}
											className="font-mono text-xs"
										/>
									) : (
										<p className="text-xs text-muted-foreground">JSON-fältet är minimerat.</p>
									)}
								</div>
								<div className="rounded border p-3 space-y-3">
									<div className="flex flex-wrap items-center justify-between gap-2">
										<div className="flex items-center gap-2">
											<Switch
												checked={ctx.useHoldoutSuite}
												onCheckedChange={ctx.setUseHoldoutSuite}
											/>
											<p className="text-sm font-medium">Använd holdout-suite</p>
										</div>
										<Button
											variant="outline"
											size="sm"
											onClick={() => ctx.setShowHoldoutJsonInput((prev) => !prev)}
										>
											{ctx.showHoldoutJsonInput ? "Minimera holdout-fält" : "Visa holdout-fält"}
										</Button>
									</div>
									<p className="text-xs text-muted-foreground">
										Holdout-suite används för anti-overfitting.
									</p>
									<div className="flex flex-wrap items-center gap-2">
										<Input
											type="file"
											accept="application/json"
											onChange={ctx.uploadHoldoutFile}
											className="max-w-sm"
										/>
										{ctx.selectedHoldoutLibraryPath && (
											<Badge variant="outline">Holdout-fil: {ctx.selectedHoldoutLibraryPath}</Badge>
										)}
									</div>
									{ctx.showHoldoutJsonInput ? (
										<Textarea
											placeholder='{"tests":[...]}'
											value={ctx.holdoutInput}
											onChange={(e) => ctx.setHoldoutInput(e.target.value)}
											rows={8}
											className="font-mono text-xs"
										/>
									) : (
										<p className="text-xs text-muted-foreground">Holdout-fältet är minimerat.</p>
									)}
								</div>
								{ctx.evalInputError && (
									<Alert variant="destructive">
										<AlertCircle className="h-4 w-4" />
										<AlertDescription>{ctx.evalInputError}</AlertDescription>
									</Alert>
								)}
							</CardContent>
						</Card>
					)}

					{ctx.showAgentSections && ctx.evalJobId && (
						<EvalJobStatusCard
							title="Steg 2A: Agentval-status per fråga"
							jobId={ctx.evalJobId}
							status={ctx.evalJobStatus?.status}
							completedTests={ctx.evalJobStatus?.completed_tests}
							totalTests={ctx.evalJobStatus?.total_tests}
							error={ctx.evalJobStatus?.error}
							caseStatuses={ctx.evalJobStatus?.case_statuses as any}
							onExportJson={() => ctx.handleExportEvalRun("tool_selection", "json")}
							onExportYaml={() => ctx.handleExportEvalRun("tool_selection", "yaml")}
							exportDisabled={!ctx.evalJobStatus}
						/>
					)}

					{ctx.showApiSections && ctx.apiInputEvalJobId && (
						<EvalJobStatusCard
							title="Steg 3A: API input-status per fråga"
							jobId={ctx.apiInputEvalJobId}
							status={ctx.apiInputEvalJobStatus?.status}
							completedTests={ctx.apiInputEvalJobStatus?.completed_tests}
							totalTests={ctx.apiInputEvalJobStatus?.total_tests}
							error={ctx.apiInputEvalJobStatus?.error}
							caseStatuses={ctx.apiInputEvalJobStatus?.case_statuses as any}
							onExportJson={() => ctx.handleExportEvalRun("api_input", "json")}
							onExportYaml={() => ctx.handleExportEvalRun("api_input", "yaml")}
							exportDisabled={!ctx.apiInputEvalJobStatus}
						/>
					)}

					{/* Agentval eval results */}
					{ctx.showAgentSections && ctx.evaluationResult && (
						<>
							<Card>
								<CardHeader>
									<CardTitle>Steg 2B: Agentval Eval Resultat</CardTitle>
									<CardDescription>
										Metadata version {ctx.evaluationResult.metadata_version_hash} · search space{" "}
										{ctx.evaluationResult.search_space_id}
									</CardDescription>
								</CardHeader>
								<CardContent className="grid gap-4 md:grid-cols-4">
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Success rate</p>
										<p className="text-2xl font-semibold">
											{(ctx.evaluationResult.metrics.success_rate * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Gated success</p>
										<p className="text-2xl font-semibold">
											{ctx.evaluationResult.metrics.gated_success_rate == null
												? "-"
												: `${(ctx.evaluationResult.metrics.gated_success_rate * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Intent accuracy</p>
										<p className="text-2xl font-semibold">
											{ctx.evaluationResult.metrics.intent_accuracy == null
												? "-"
												: `${(ctx.evaluationResult.metrics.intent_accuracy * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Route accuracy</p>
										<p className="text-2xl font-semibold">
											{ctx.evaluationResult.metrics.route_accuracy == null
												? "-"
												: `${(ctx.evaluationResult.metrics.route_accuracy * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Agent accuracy</p>
										<p className="text-2xl font-semibold">
											{ctx.evaluationResult.metrics.agent_accuracy == null
												? "-"
												: `${(ctx.evaluationResult.metrics.agent_accuracy * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Tool accuracy</p>
										<p className="text-2xl font-semibold">
											{ctx.evaluationResult.metrics.tool_accuracy == null
												? "-"
												: `${(ctx.evaluationResult.metrics.tool_accuracy * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Plan accuracy</p>
										<p className="text-2xl font-semibold">
											{ctx.evaluationResult.metrics.plan_accuracy == null
												? "-"
												: `${(ctx.evaluationResult.metrics.plan_accuracy * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Supervisor review</p>
										<p className="text-2xl font-semibold">
											{ctx.evaluationResult.metrics.supervisor_review_score == null
												? "-"
												: `${(ctx.evaluationResult.metrics.supervisor_review_score * 100).toFixed(1)}%`}
										</p>
									</div>
								</CardContent>
							</Card>

							<SharedDifficultyBreakdown
								title="Svårighetsgrad · Agentval Eval"
								items={ctx.evaluationResult.metrics.difficulty_breakdown ?? []}
							/>
							<SharedComparisonInsights
								title="Diff mot föregående Agent/Tool-run"
								comparison={ctx.evaluationResult.comparison}
							/>

							<Card>
								<CardHeader>
									<CardTitle>Steg 2C: Retrieval-vikter i denna eval</CardTitle>
								</CardHeader>
								<CardContent className="space-y-3">
									<div className="grid gap-2 md:grid-cols-3">
										<Badge variant="outline">
											name: {ctx.evaluationResult.retrieval_tuning.name_match_weight}
										</Badge>
										<Badge variant="outline">
											keyword: {ctx.evaluationResult.retrieval_tuning.keyword_weight}
										</Badge>
										<Badge variant="outline">
											desc: {ctx.evaluationResult.retrieval_tuning.description_token_weight}
										</Badge>
										<Badge variant="outline">
											example: {ctx.evaluationResult.retrieval_tuning.example_query_weight}
										</Badge>
										<Badge variant="outline">
											namespace: {ctx.evaluationResult.retrieval_tuning.namespace_boost}
										</Badge>
										<Badge variant="outline">
											embedding: {ctx.evaluationResult.retrieval_tuning.embedding_weight}
										</Badge>
										<Badge variant="outline">
											rerank: {ctx.evaluationResult.retrieval_tuning.rerank_candidates}
										</Badge>
									</div>
									{ctx.evaluationResult.retrieval_tuning_suggestion && (
										<div className="rounded border p-3 space-y-2">
											<p className="text-sm font-medium">Föreslagen tuning</p>
											<p className="text-xs text-muted-foreground">
												{ctx.evaluationResult.retrieval_tuning_suggestion.rationale}
											</p>
											<div className="flex gap-2">
												<Button
													variant="outline"
													onClick={ctx.applyWeightSuggestionToDraft}
													disabled={ctx.isSavingRetrievalTuning}
												>
													Applicera viktförslag i draft
												</Button>
												<Button
													onClick={ctx.saveWeightSuggestion}
													disabled={ctx.isSavingRetrievalTuning}
												>
													Spara viktförslag
												</Button>
											</div>
										</div>
									)}
								</CardContent>
							</Card>

							<EvalPerTestCard
								title="Steg 2D: Agentval-resultat per test"
								results={ctx.evaluationResult.results as any}
							/>

							<Card>
								<CardHeader>
									<CardTitle>Steg 2E: Metadata-förslag</CardTitle>
									<CardDescription>Acceptera förslag, spara och kör eval igen.</CardDescription>
								</CardHeader>
								<CardContent className="space-y-4">
									<div className="flex flex-wrap items-center gap-2">
										<Button variant="outline" onClick={ctx.regenerateSuggestions}>
											Regenerera förslag
										</Button>
										<Button
											onClick={ctx.applySelectedSuggestionsToDraft}
											disabled={!ctx.selectedSuggestionIds.size || ctx.isApplyingSuggestions}
										>
											Applicera valda i draft
										</Button>
										<Button
											onClick={ctx.saveSelectedSuggestions}
											disabled={!ctx.selectedSuggestionIds.size || ctx.isSavingSuggestions}
										>
											Spara valda förslag
										</Button>
										<Button
											onClick={ctx.handleRunEvaluation}
											disabled={ctx.isEvaluating || ctx.isEvalJobRunning}
										>
											Kör om eval
										</Button>
										<Badge variant="outline">{ctx.selectedSuggestions.length} valda</Badge>
									</div>
									{ctx.evaluationResult.suggestions.length === 0 ? (
										<p className="text-sm text-muted-foreground">
											Inga förbättringsförslag hittades.
										</p>
									) : (
										<SuggestionDiffView
											suggestions={ctx.suggestionDiffItems}
											selectedIds={ctx.selectedSuggestionIds}
											onToggle={ctx.toggleSuggestion}
											onToggleAll={ctx.toggleAllSuggestions}
										/>
									)}
								</CardContent>
							</Card>

							<PromptSuggestionsCard
								title="Steg 2F: Prompt-förslag från Agentval Eval"
								suggestions={ctx.evaluationResult.prompt_suggestions}
								selectedKeys={ctx.selectedToolPromptSuggestionKeys}
								onToggle={ctx.toggleToolPromptSuggestion}
								onSave={ctx.saveSelectedToolPromptSuggestions}
								isSaving={ctx.isSavingToolPromptSuggestions}
							/>

							<IntentSuggestionsCard
								title="Steg 2G: Intent-förslag"
								suggestions={ctx.evaluationResult.intent_suggestions}
							/>
						</>
					)}

					{/* API Input eval results */}
					{ctx.showApiSections && ctx.apiInputEvaluationResult && (
						<>
							<Card>
								<CardHeader>
									<CardTitle>Steg 3B: API Input Eval Resultat</CardTitle>
									<CardDescription>
										Metadata version {ctx.apiInputEvaluationResult.metadata_version_hash} · search
										space {ctx.apiInputEvaluationResult.search_space_id}
									</CardDescription>
								</CardHeader>
								<CardContent className="grid gap-4 md:grid-cols-5">
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Success rate</p>
										<p className="text-2xl font-semibold">
											{(ctx.apiInputEvaluationResult.metrics.success_rate * 100).toFixed(1)}%
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Schema validity</p>
										<p className="text-2xl font-semibold">
											{ctx.apiInputEvaluationResult.metrics.schema_validity_rate == null
												? "-"
												: `${(ctx.apiInputEvaluationResult.metrics.schema_validity_rate * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Required recall</p>
										<p className="text-2xl font-semibold">
											{ctx.apiInputEvaluationResult.metrics.required_field_recall == null
												? "-"
												: `${(ctx.apiInputEvaluationResult.metrics.required_field_recall * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Field-value accuracy</p>
										<p className="text-2xl font-semibold">
											{ctx.apiInputEvaluationResult.metrics.field_value_accuracy == null
												? "-"
												: `${(ctx.apiInputEvaluationResult.metrics.field_value_accuracy * 100).toFixed(1)}%`}
										</p>
									</div>
									<div className="rounded border p-3">
										<p className="text-xs text-muted-foreground">Clarification accuracy</p>
										<p className="text-2xl font-semibold">
											{ctx.apiInputEvaluationResult.metrics.clarification_accuracy == null
												? "-"
												: `${(ctx.apiInputEvaluationResult.metrics.clarification_accuracy * 100).toFixed(1)}%`}
										</p>
									</div>
								</CardContent>
							</Card>

							<SharedDifficultyBreakdown
								title="Svårighetsgrad · API Input Eval"
								items={ctx.apiInputEvaluationResult.metrics.difficulty_breakdown ?? []}
							/>
							<SharedComparisonInsights
								title="Diff mot föregående API Input-run"
								comparison={ctx.apiInputEvaluationResult.comparison}
							/>

							{ctx.apiInputEvaluationResult.holdout_metrics && (
								<Card>
									<CardHeader>
										<CardTitle>Steg 4: Holdout-suite</CardTitle>
										<CardDescription>Separat mätning för anti-overfitting.</CardDescription>
									</CardHeader>
									<CardContent className="grid gap-4 md:grid-cols-4">
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Holdout success</p>
											<p className="text-2xl font-semibold">
												{(ctx.apiInputEvaluationResult.holdout_metrics.success_rate * 100).toFixed(
													1
												)}
												%
											</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Schema validity</p>
											<p className="text-2xl font-semibold">
												{ctx.apiInputEvaluationResult.holdout_metrics.schema_validity_rate == null
													? "-"
													: `${(ctx.apiInputEvaluationResult.holdout_metrics.schema_validity_rate * 100).toFixed(1)}%`}
											</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Required recall</p>
											<p className="text-2xl font-semibold">
												{ctx.apiInputEvaluationResult.holdout_metrics.required_field_recall == null
													? "-"
													: `${(ctx.apiInputEvaluationResult.holdout_metrics.required_field_recall * 100).toFixed(1)}%`}
											</p>
										</div>
										<div className="rounded border p-3">
											<p className="text-xs text-muted-foreground">Holdout cases</p>
											<p className="text-2xl font-semibold">
												{ctx.apiInputEvaluationResult.holdout_metrics.passed_tests}/
												{ctx.apiInputEvaluationResult.holdout_metrics.total_tests}
											</p>
										</div>
									</CardContent>
								</Card>
							)}

							<EvalPerTestCard
								title="Steg 3C: API Input resultat per test"
								results={ctx.apiInputEvaluationResult.results as any}
								showApiInputFields
							/>

							<PromptSuggestionsCard
								title="Steg 3D: Prompt-förslag från API Input Eval"
								suggestions={ctx.apiInputEvaluationResult.prompt_suggestions}
								selectedKeys={ctx.selectedPromptSuggestionKeys}
								onToggle={ctx.togglePromptSuggestion}
								onSave={ctx.saveSelectedPromptSuggestions}
								isSaving={ctx.isSavingPromptSuggestions}
								extraActions={
									<Button
										variant="outline"
										onClick={ctx.handleRunApiInputEvaluation}
										disabled={ctx.isApiInputEvaluating || ctx.isApiInputEvalJobRunning}
									>
										Kör om API input eval
									</Button>
								}
							/>

							<IntentSuggestionsCard
								title="Steg 3E: Intent-förslag"
								suggestions={ctx.apiInputEvaluationResult.intent_suggestions}
							/>
						</>
					)}
				</div>
			)}

			{/* ================================================================ */}
			{/* STEG 3: AUTO-OPTIMERING                                         */}
			{/* ================================================================ */}
			{ctx.calibrationStep === "auto" && (
				<Card>
					<CardHeader>
						<CardTitle>Auto-optimering</CardTitle>
						<CardDescription>
							Loopa generering → eval → förslag → uppdatering tills önskad success rate nås.
						</CardDescription>
					</CardHeader>
					<CardContent className="space-y-4">
						<div className="grid gap-3 md:grid-cols-4">
							<div className="space-y-2">
								<Label htmlFor="cal-auto-target">Target success</Label>
								<Input
									id="cal-auto-target"
									type="number"
									min={0}
									max={1}
									step={0.01}
									value={ctx.autoTargetSuccessRate}
									onChange={(e) =>
										ctx.setAutoTargetSuccessRate(Number.parseFloat(e.target.value || "0.85"))
									}
								/>
							</div>
							<div className="space-y-2">
								<Label htmlFor="cal-auto-max">Max iterationer</Label>
								<Input
									id="cal-auto-max"
									type="number"
									min={1}
									max={30}
									value={ctx.autoMaxIterations}
									onChange={(e) =>
										ctx.setAutoMaxIterations(Number.parseInt(e.target.value || "6", 10))
									}
								/>
							</div>
							<div className="space-y-2">
								<Label htmlFor="cal-auto-patience">Patience</Label>
								<Input
									id="cal-auto-patience"
									type="number"
									min={1}
									max={12}
									value={ctx.autoPatience}
									onChange={(e) => ctx.setAutoPatience(Number.parseInt(e.target.value || "2", 10))}
								/>
							</div>
							<div className="space-y-2">
								<Label htmlFor="cal-auto-delta">Min förbättring</Label>
								<Input
									id="cal-auto-delta"
									type="number"
									min={0}
									max={0.25}
									step={0.001}
									value={ctx.autoMinImprovementDelta}
									onChange={(e) =>
										ctx.setAutoMinImprovementDelta(Number.parseFloat(e.target.value || "0.005"))
									}
								/>
							</div>
						</div>

						<div className="rounded border p-3 space-y-3">
							<div className="flex items-center gap-2">
								<Switch
									checked={ctx.autoUseHoldoutSuite}
									onCheckedChange={ctx.setAutoUseHoldoutSuite}
								/>
								<span className="text-sm font-medium">Inkludera auto-genererad holdout-suite</span>
							</div>
							<p className="text-xs text-muted-foreground">
								Auto-läget jämför train och holdout per iteration för att upptäcka överanpassning.
							</p>
							{ctx.autoUseHoldoutSuite && (
								<div className="grid gap-3 md:grid-cols-2">
									<div className="space-y-2">
										<Label htmlFor="cal-auto-holdout-count">Holdout antal frågor</Label>
										<Input
											id="cal-auto-holdout-count"
											type="number"
											min={1}
											max={100}
											value={ctx.autoHoldoutQuestionCount}
											onChange={(e) =>
												ctx.setAutoHoldoutQuestionCount(Number.parseInt(e.target.value || "8", 10))
											}
										/>
									</div>
									<div className="space-y-2">
										<Label htmlFor="cal-auto-holdout-diff">Holdout svårighetsprofil</Label>
										<select
											id="cal-auto-holdout-diff"
											className="h-10 w-full rounded-md border bg-background px-3 text-sm"
											value={ctx.autoHoldoutDifficultyProfile}
											onChange={(e) =>
												ctx.setAutoHoldoutDifficultyProfile(
													e.target.value === "lätt"
														? "lätt"
														: e.target.value === "medel"
															? "medel"
															: e.target.value === "svår"
																? "svår"
																: "mixed"
												)
											}
										>
											<option value="mixed">Blandad</option>
											<option value="lätt">Lätt</option>
											<option value="medel">Medel</option>
											<option value="svår">Svår</option>
										</select>
									</div>
								</div>
							)}
						</div>

						<div className="flex flex-wrap items-center gap-2">
							<Button
								onClick={ctx.handleStartAutoLoop}
								disabled={ctx.isStartingAutoLoop || ctx.isAutoLoopRunning}
							>
								{ctx.isStartingAutoLoop
									? "Startar auto-läge..."
									: ctx.isAutoLoopRunning
										? "Auto-läge körs..."
										: "Starta auto-läge"}
							</Button>
							{ctx.autoLoopJobId && (
								<Badge variant="outline">Jobb: {ctx.autoLoopJobId.slice(0, 8)}</Badge>
							)}
							{ctx.autoLoopJobStatus && (
								<Badge
									variant={
										ctx.autoLoopJobStatus.status === "failed"
											? "destructive"
											: ctx.autoLoopJobStatus.status === "completed"
												? "default"
												: "secondary"
									}
								>
									{ctx.autoLoopJobStatus.status}
								</Badge>
							)}
						</div>

						{ctx.autoLoopJobStatus && (
							<div className="rounded bg-muted/30 p-3 space-y-2">
								<div className="grid gap-2 md:grid-cols-4 text-xs">
									<p>
										Iteration: {ctx.autoLoopJobStatus.completed_iterations}/
										{ctx.autoLoopJobStatus.total_iterations}
									</p>
									<p>Bästa success: {formatPercent(ctx.autoLoopJobStatus.best_success_rate)}</p>
									<p>Utebliven förbättring: {ctx.autoLoopJobStatus.no_improvement_runs}</p>
									<p>{ctx.autoLoopJobStatus.message || "-"}</p>
								</div>
								{(ctx.autoLoopJobStatus.iterations ?? []).length > 0 && (
									<div className="space-y-1">
										{ctx.autoLoopJobStatus.iterations.slice(-6).map((item) => (
											<p
												key={`auto-iter-${item.iteration}`}
												className="text-xs text-muted-foreground"
											>
												Iter {item.iteration}: train {formatPercent(item.success_rate)}
												{typeof item.success_delta_vs_previous === "number"
													? ` (${formatSignedPercent(item.success_delta_vs_previous)})`
													: ""}
												{typeof item.holdout_success_rate === "number"
													? ` · holdout ${formatPercent(item.holdout_success_rate)}`
													: ""}
												{typeof item.combined_score === "number"
													? ` · kombinerad ${formatPercent(item.combined_score)}`
													: ""}
												{item.note ? ` · ${item.note}` : ""}
											</p>
										))}
									</div>
								)}
								{ctx.autoLoopJobStatus.status === "completed" && ctx.autoLoopJobStatus.result && (
									<div className="space-y-1">
										<p className="text-xs text-muted-foreground">
											Stop-orsak:{" "}
											{formatAutoLoopStopReason(ctx.autoLoopJobStatus.result.stop_reason)}
										</p>
										{ctx.autoLoopJobStatus.result.final_holdout_evaluation && (
											<p className="text-xs text-muted-foreground">
												Slutlig holdout success:{" "}
												{formatPercent(
													ctx.autoLoopJobStatus.result.final_holdout_evaluation.metrics.success_rate
												)}
											</p>
										)}
									</div>
								)}
								{ctx.autoLoopPromptDrafts.length > 0 && (
									<div className="flex flex-wrap items-center gap-2">
										<Badge variant="outline">
											{ctx.autoLoopPromptDrafts.length} promptutkast redo
										</Badge>
										<Button
											variant="outline"
											size="sm"
											onClick={ctx.saveAutoLoopPromptDraftSuggestions}
											disabled={ctx.isSavingAutoLoopPromptDrafts}
										>
											{ctx.isSavingAutoLoopPromptDrafts ? "Sparar..." : "Spara promptutkast"}
										</Button>
									</div>
								)}
							</div>
						)}
					</CardContent>
				</Card>
			)}

			{/* ================================================================ */}
			{/* LIFECYCLE PROMOTION                                             */}
			{/* ================================================================ */}
			{ctx.lifecycleData && ctx.lifecycleData.review_count > 0 && (
				<Card>
					<CardHeader>
						<CardTitle>Lifecycle-promotion</CardTitle>
						<CardDescription>
							Verktyg i Review som uppnått krävd success rate kan befordras till Live.
						</CardDescription>
					</CardHeader>
					<CardContent className="space-y-4">
						<div className="grid gap-3 md:grid-cols-3 text-sm">
							<div className="rounded border p-3">
								<p className="text-xs text-muted-foreground">Live</p>
								<p className="text-2xl font-semibold text-green-600">
									{ctx.lifecycleData.live_count}
								</p>
							</div>
							<div className="rounded border p-3">
								<p className="text-xs text-muted-foreground">Review</p>
								<p className="text-2xl font-semibold text-amber-600">
									{ctx.lifecycleData.review_count}
								</p>
							</div>
							<div className="rounded border p-3">
								<p className="text-xs text-muted-foreground">Totalt</p>
								<p className="text-2xl font-semibold">{ctx.lifecycleData.total_count}</p>
							</div>
						</div>
						<div className="max-h-64 overflow-auto space-y-1">
							{ctx.lifecycleData.tools
								.filter((t) => t.status === "review")
								.map((tool) => (
									<div
										key={`promo-${tool.tool_id}`}
										className="flex items-center justify-between gap-2 rounded border p-2 text-xs"
									>
										<span className="font-mono truncate max-w-[250px]">{tool.tool_id}</span>
										<LifecycleBadge
											status={tool.status as "live" | "review"}
											successRate={tool.success_rate}
											requiredSuccessRate={tool.required_success_rate}
										/>
									</div>
								))}
						</div>
						<Button onClick={ctx.handleBulkPromote} disabled={ctx.isPromoting}>
							{ctx.isPromoting ? "Befordrar..." : "Befordra kvalificerade till Live"}
						</Button>
					</CardContent>
				</Card>
			)}
		</div>
	);
}
