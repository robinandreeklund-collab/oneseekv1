"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	AlertCircle,
	Check,
	ChevronDown,
	ChevronRight,
	Layers,
	Loader2,
	Sparkles,
	X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
	nexusApiService,
	type ToolSuggestionResponse,
	type OptimizerResultResponse,
	type IntentLayerItemSuggestion,
	type IntentLayerResultResponse,
	type PlatformToolResponse,
} from "@/lib/apis/nexus-api.service";
import { useCategoryLabels } from "@/components/admin/nexus/shared/use-category-labels";

type FilterMode = "namespace" | "category" | "intent-layer";

// ---------------------------------------------------------------------------
// Shared diff view component
// ---------------------------------------------------------------------------

function DiffValue({
	label,
	current,
	suggested,
}: {
	label: string;
	current: unknown;
	suggested: unknown;
}) {
	const fmt = (v: unknown): string => {
		if (Array.isArray(v)) return v.join(", ");
		if (v == null) return "—";
		return String(v);
	};

	const currentStr = fmt(current);
	const suggestedStr = fmt(suggested);
	const changed = currentStr !== suggestedStr;

	if (!changed) return null;

	return (
		<div className="space-y-1">
			<p className="text-xs font-medium text-muted-foreground">{label}</p>
			<div className="grid grid-cols-2 gap-2 text-sm">
				<div className="rounded border border-red-200 bg-red-50 p-2 dark:border-red-900 dark:bg-red-950">
					<p className="text-xs text-red-600 dark:text-red-400 mb-0.5">Nuvarande</p>
					<p className="break-words">{currentStr || "—"}</p>
				</div>
				<div className="rounded border border-green-200 bg-green-50 p-2 dark:border-green-900 dark:bg-green-950">
					<p className="text-xs text-green-600 dark:text-green-400 mb-0.5">Föreslaget</p>
					<p className="break-words">{suggestedStr || "—"}</p>
				</div>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Tool Suggestion Card (namespace/category mode)
// ---------------------------------------------------------------------------

function SuggestionCard({
	suggestion,
	approved,
	onApprove,
	onReject,
}: {
	suggestion: ToolSuggestionResponse;
	approved: boolean | null;
	onApprove: () => void;
	onReject: () => void;
}) {
	const [expanded, setExpanded] = useState(false);

	return (
		<div
			className={`rounded-lg border p-4 ${
				approved === true
					? "border-green-300 bg-green-50/50 dark:border-green-800 dark:bg-green-950/30"
					: approved === false
						? "border-red-300 bg-red-50/50 dark:border-red-800 dark:bg-red-950/30 opacity-60"
						: "border-border"
			}`}
		>
			{/* Header */}
			<div className="flex items-center justify-between">
				<button
					type="button"
					className="flex items-center gap-2 text-left flex-1"
					onClick={() => setExpanded(!expanded)}
				>
					{expanded ? (
						<ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
					) : (
						<ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
					)}
					<div>
						<p className="font-medium text-sm">{suggestion.tool_id}</p>
						<div className="flex flex-wrap gap-1 mt-0.5">
							{suggestion.fields_changed.map((f) => (
								<Badge key={f} variant="secondary" className="text-xs py-0">
									{f}
								</Badge>
							))}
						</div>
					</div>
				</button>

				<div className="flex items-center gap-1.5 shrink-0">
					<Button
						variant={approved === true ? "default" : "outline"}
						size="sm"
						onClick={onApprove}
						className="h-7 px-2"
					>
						<Check className="h-3.5 w-3.5 mr-1" />
						Godkänn
					</Button>
					<Button
						variant={approved === false ? "destructive" : "outline"}
						size="sm"
						onClick={onReject}
						className="h-7 px-2"
					>
						<X className="h-3.5 w-3.5 mr-1" />
						Avvisa
					</Button>
				</div>
			</div>

			{/* Reasoning */}
			{suggestion.reasoning && (
				<p className="text-xs text-muted-foreground mt-2 italic">
					{suggestion.reasoning}
				</p>
			)}

			{/* Expanded diff view */}
			{expanded && (
				<div className="mt-4 space-y-3 border-t pt-3">
					<DiffValue
						label="Description"
						current={suggestion.current.description}
						suggested={suggestion.suggested.description}
					/>
					<DiffValue
						label="Keywords"
						current={suggestion.current.keywords}
						suggested={suggestion.suggested.keywords}
					/>
					<DiffValue
						label="Example Queries"
						current={suggestion.current.example_queries}
						suggested={suggestion.suggested.example_queries}
					/>
					<DiffValue
						label="Excludes"
						current={suggestion.current.excludes}
						suggested={suggestion.suggested.excludes}
					/>
					<DiffValue
						label="Geographic Scope"
						current={suggestion.current.geographic_scope}
						suggested={suggestion.suggested.geographic_scope}
					/>
				</div>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Intent Layer Suggestion Card (domain/agent)
// ---------------------------------------------------------------------------

function IntentLayerSuggestionCard({
	suggestion,
	approved,
	onApprove,
	onReject,
}: {
	suggestion: IntentLayerItemSuggestion;
	approved: boolean | null;
	onApprove: () => void;
	onReject: () => void;
}) {
	const [expanded, setExpanded] = useState(false);
	const typeLabel = suggestion.item_type === "domain" ? "Domän" : "Agent";

	return (
		<div
			className={`rounded-lg border p-4 ${
				approved === true
					? "border-green-300 bg-green-50/50 dark:border-green-800 dark:bg-green-950/30"
					: approved === false
						? "border-red-300 bg-red-50/50 dark:border-red-800 dark:bg-red-950/30 opacity-60"
						: "border-border"
			}`}
		>
			<div className="flex items-center justify-between">
				<button
					type="button"
					className="flex items-center gap-2 text-left flex-1"
					onClick={() => setExpanded(!expanded)}
				>
					{expanded ? (
						<ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
					) : (
						<ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
					)}
					<div>
						<div className="flex items-center gap-2">
							<Badge
								variant={suggestion.item_type === "domain" ? "default" : "secondary"}
								className="text-xs py-0"
							>
								{typeLabel}
							</Badge>
							<p className="font-medium text-sm">{suggestion.item_id}</p>
						</div>
						<div className="flex flex-wrap gap-1 mt-0.5">
							{suggestion.fields_changed.map((f) => (
								<Badge key={f} variant="outline" className="text-xs py-0">
									{f}
								</Badge>
							))}
						</div>
					</div>
				</button>

				<div className="flex items-center gap-1.5 shrink-0">
					<Button
						variant={approved === true ? "default" : "outline"}
						size="sm"
						onClick={onApprove}
						className="h-7 px-2"
					>
						<Check className="h-3.5 w-3.5 mr-1" />
						Godkänn
					</Button>
					<Button
						variant={approved === false ? "destructive" : "outline"}
						size="sm"
						onClick={onReject}
						className="h-7 px-2"
					>
						<X className="h-3.5 w-3.5 mr-1" />
						Avvisa
					</Button>
				</div>
			</div>

			{suggestion.reasoning && (
				<p className="text-xs text-muted-foreground mt-2 italic">
					{suggestion.reasoning}
				</p>
			)}

			{expanded && (
				<div className="mt-4 space-y-3 border-t pt-3">
					<DiffValue
						label="Description"
						current={suggestion.current.description}
						suggested={suggestion.suggested.description}
					/>
					<DiffValue
						label="Keywords"
						current={suggestion.current.keywords}
						suggested={suggestion.suggested.keywords}
					/>
					<DiffValue
						label="Excludes"
						current={suggestion.current.excludes}
						suggested={suggestion.suggested.excludes}
					/>
					<DiffValue
						label="Main Identifier"
						current={suggestion.current.main_identifier}
						suggested={suggestion.suggested.main_identifier}
					/>
					<DiffValue
						label="Core Activity"
						current={suggestion.current.core_activity}
						suggested={suggestion.suggested.core_activity}
					/>
					<DiffValue
						label="Unique Scope"
						current={suggestion.current.unique_scope}
						suggested={suggestion.suggested.unique_scope}
					/>
				</div>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// OptimizerTab — main component
// ---------------------------------------------------------------------------

export function OptimizerTab() {
	const CATEGORY_LABELS = useCategoryLabels();
	const [platformTools, setPlatformTools] = useState<PlatformToolResponse[]>([]);
	const [categories, setCategories] = useState<string[]>([]);
	const [filterMode, setFilterMode] = useState<FilterMode>("namespace");
	const [selectedNamespace, setSelectedNamespace] = useState<string>("");
	const [selectedCategory, setSelectedCategory] = useState<string>("");
	const [loading, setLoading] = useState(true);
	const [generating, setGenerating] = useState(false);
	const [applying, setApplying] = useState(false);

	// Tool optimizer state
	const [result, setResult] = useState<OptimizerResultResponse | null>(null);

	// Intent layer optimizer state
	const [intentResult, setIntentResult] = useState<IntentLayerResultResponse | null>(null);

	// Shared approval state (keyed by tool_id or item_id)
	const [approvalMap, setApprovalMap] = useState<Record<string, boolean | null>>({});
	const [applyResult, setApplyResult] = useState<string | null>(null);

	// Derive unique namespace prefixes from tools
	const namespaces = Array.from(
		new Set(
			platformTools
				.map((t) => {
					const parts = t.namespace.split("/");
					return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : t.namespace;
				})
				.filter(Boolean),
		),
	).sort();

	// Load platform tools + categories on mount
	useEffect(() => {
		setLoading(true);
		Promise.all([
			nexusApiService.getPlatformTools(),
			nexusApiService.getOptimizerCategories(),
		])
			.then(([toolsRes, catRes]) => {
				setPlatformTools(toolsRes.tools);
				setCategories(catRes.categories);
			})
			.catch(() => {})
			.finally(() => setLoading(false));
	}, []);

	// Count tools for selected filter
	const selectedToolCount = (() => {
		if (filterMode === "namespace" && selectedNamespace) {
			return platformTools.filter((t) => t.namespace.startsWith(selectedNamespace)).length;
		}
		if (filterMode === "category" && selectedCategory) {
			return platformTools.filter((t) => t.category === selectedCategory).length;
		}
		return 0;
	})();

	const canGenerate =
		filterMode === "intent-layer" ||
		(filterMode === "namespace" && !!selectedNamespace) ||
		(filterMode === "category" && !!selectedCategory);

	// Reset results when switching modes
	const switchMode = (mode: FilterMode) => {
		setFilterMode(mode);
		setResult(null);
		setIntentResult(null);
		setApprovalMap({});
		setApplyResult(null);
	};

	const handleGenerate = useCallback(async () => {
		if (!canGenerate) return;
		setGenerating(true);
		setResult(null);
		setIntentResult(null);
		setApprovalMap({});
		setApplyResult(null);

		if (filterMode === "intent-layer") {
			// Intent layer optimization
			try {
				const res = await nexusApiService.intentLayerGenerate({});
				setIntentResult(res);
				const map: Record<string, boolean | null> = {};
				for (const s of res.suggestions) {
					map[`${s.item_type}:${s.item_id}`] = null;
				}
				setApprovalMap(map);
			} catch (err) {
				setIntentResult({
					total_domains: 0,
					total_agents: 0,
					suggestions: [],
					model_used: "",
					error: err instanceof Error ? err.message : "Unknown error",
				});
			} finally {
				setGenerating(false);
			}
			return;
		}

		// Tool optimization (namespace/category)
		const request: { category?: string; namespace?: string } = {};
		if (filterMode === "namespace" && selectedNamespace) {
			request.namespace = selectedNamespace;
		} else if (filterMode === "category" && selectedCategory) {
			request.category = selectedCategory;
		}

		try {
			const res = await nexusApiService.optimizerGenerate(request);
			setResult(res);
			const map: Record<string, boolean | null> = {};
			for (const s of res.suggestions) {
				map[s.tool_id] = null;
			}
			setApprovalMap(map);
		} catch (err) {
			setResult({
				category: selectedNamespace || selectedCategory,
				total_tools: 0,
				suggestions: [],
				model_used: "",
				error: err instanceof Error ? err.message : "Unknown error",
			});
		} finally {
			setGenerating(false);
		}
	}, [canGenerate, filterMode, selectedNamespace, selectedCategory]);

	const handleApprove = (key: string) => {
		setApprovalMap((prev) => ({
			...prev,
			[key]: prev[key] === true ? null : true,
		}));
	};

	const handleReject = (key: string) => {
		setApprovalMap((prev) => ({
			...prev,
			[key]: prev[key] === false ? null : false,
		}));
	};

	const handleApproveAll = () => {
		if (filterMode === "intent-layer" && intentResult) {
			const map: Record<string, boolean | null> = {};
			for (const s of intentResult.suggestions) {
				map[`${s.item_type}:${s.item_id}`] = true;
			}
			setApprovalMap(map);
		} else if (result) {
			const map: Record<string, boolean | null> = {};
			for (const s of result.suggestions) {
				map[s.tool_id] = true;
			}
			setApprovalMap(map);
		}
	};

	const handleApply = useCallback(async () => {
		setApplying(true);
		setApplyResult(null);

		if (filterMode === "intent-layer" && intentResult) {
			// Intent layer apply
			const approved = intentResult.suggestions
				.filter((s) => approvalMap[`${s.item_type}:${s.item_id}`] === true)
				.map((s) => ({
					item_id: s.item_id,
					item_type: s.item_type,
					...s.suggested,
				}));

			if (approved.length === 0) {
				setApplyResult("Inga godkända förslag att tillämpa.");
				setApplying(false);
				return;
			}

			try {
				const res = await nexusApiService.intentLayerApply(approved);
				setApplyResult(
					`Tillämpat ${res.applied_domains} domäner och ${res.applied_agents} agenter.${res.skipped > 0 ? ` ${res.skipped} hoppade över.` : ""} NEXUS använder nu de uppdaterade definitionerna.`,
				);
			} catch (err) {
				setApplyResult(`Fel: ${err instanceof Error ? err.message : "Unknown error"}`);
			} finally {
				setApplying(false);
			}
			return;
		}

		// Tool apply
		if (!result) {
			setApplying(false);
			return;
		}

		const approved = result.suggestions
			.filter((s) => approvalMap[s.tool_id] === true)
			.map((s) => ({
				tool_id: s.tool_id,
				...s.suggested,
			}));

		if (approved.length === 0) {
			setApplyResult("Inga godkända förslag att tillämpa.");
			setApplying(false);
			return;
		}

		try {
			const res = await nexusApiService.optimizerApply(approved);
			setApplyResult(
				`Tillämpat ${res.applied} verktyg. ${res.skipped > 0 ? `${res.skipped} hoppade över.` : ""} NEXUS använder nu de nya metadata-overrides.`,
			);
		} catch (err) {
			setApplyResult(`Fel: ${err instanceof Error ? err.message : "Unknown error"}`);
		} finally {
			setApplying(false);
		}
	}, [filterMode, result, intentResult, approvalMap]);

	const approvedCount = Object.values(approvalMap).filter((v) => v === true).length;
	const rejectedCount = Object.values(approvalMap).filter((v) => v === false).length;
	const pendingCount = Object.values(approvalMap).filter((v) => v === null).length;

	// Active result (either tool or intent layer)
	const activeModelUsed =
		filterMode === "intent-layer" ? intentResult?.model_used : result?.model_used;
	const activeError =
		filterMode === "intent-layer" ? intentResult?.error : result?.error;
	const activeSuggestionCount =
		filterMode === "intent-layer"
			? (intentResult?.suggestions.length ?? 0)
			: (result?.suggestions.length ?? 0);
	const activeTotalCount =
		filterMode === "intent-layer"
			? (intentResult?.total_domains ?? 0) + (intentResult?.total_agents ?? 0)
			: (result?.total_tools ?? 0);
	const hasResult = filterMode === "intent-layer" ? !!intentResult : !!result;

	return (
		<div className="space-y-6">
			{/* Description */}
			<Alert>
				<Sparkles className="h-4 w-4" />
				<AlertDescription>
					Använd AI (Claude Sonnet) för att optimera metadata. Välj
					namespace/kategori för verktyg, eller &quot;Intent-lager&quot; för att
					optimera alla domäner och agenter samtidigt. LLM:en maximerar
					embedding-separation. Godkända förslag sparas som DB-overrides.
				</AlertDescription>
			</Alert>

			{/* Filter + Generate */}
			<Card>
				<CardHeader>
					<CardTitle className="text-base">Generera förslag</CardTitle>
				</CardHeader>
				<CardContent>
					<div className="space-y-4">
						{/* Filter mode toggle */}
						<div className="flex items-center gap-2">
							<Button
								variant={filterMode === "namespace" ? "default" : "outline"}
								size="sm"
								onClick={() => switchMode("namespace")}
							>
								Namespace
							</Button>
							<Button
								variant={filterMode === "category" ? "default" : "outline"}
								size="sm"
								onClick={() => switchMode("category")}
							>
								Kategori
							</Button>
							<Button
								variant={filterMode === "intent-layer" ? "default" : "outline"}
								size="sm"
								onClick={() => switchMode("intent-layer")}
							>
								<Layers className="h-3.5 w-3.5 mr-1.5" />
								Intent-lager
							</Button>
						</div>

						<div className="flex items-end gap-3">
							<div className="flex-1 max-w-sm">
								{filterMode === "intent-layer" ? (
									<p className="text-sm text-muted-foreground py-2">
										Optimerar hela intent-lagret: alla 17 domäner och 13 agenter
										skickas till LLM för batch-optimering av keywords,
										descriptions och excludes.
									</p>
								) : loading ? (
									<div className="flex items-center gap-2 text-muted-foreground h-9">
										<Loader2 className="h-4 w-4 animate-spin" />
										Laddar verktyg...
									</div>
								) : filterMode === "namespace" ? (
									<>
										<label className="text-sm text-muted-foreground mb-1.5 block">
											Namespace
										</label>
										<Select
											value={selectedNamespace}
											onValueChange={setSelectedNamespace}
										>
											<SelectTrigger>
												<SelectValue placeholder="Välj namespace..." />
											</SelectTrigger>
											<SelectContent>
												{namespaces.map((ns) => {
													const count = platformTools.filter((t) =>
														t.namespace.startsWith(ns),
													).length;
													return (
														<SelectItem key={ns} value={ns}>
															{ns} ({count} verktyg)
														</SelectItem>
													);
												})}
											</SelectContent>
										</Select>
									</>
								) : (
									<>
										<label className="text-sm text-muted-foreground mb-1.5 block">
											Kategori
										</label>
										<Select
											value={selectedCategory}
											onValueChange={setSelectedCategory}
										>
											<SelectTrigger>
												<SelectValue placeholder="Välj kategori..." />
											</SelectTrigger>
											<SelectContent>
												{categories.map((cat) => {
													const count = platformTools.filter(
														(t) => t.category === cat,
													).length;
													return (
														<SelectItem key={cat} value={cat}>
															{CATEGORY_LABELS[cat] || cat} ({count} verktyg)
														</SelectItem>
													);
												})}
											</SelectContent>
										</Select>
									</>
								)}
							</div>

							<Button
								onClick={handleGenerate}
								disabled={!canGenerate || generating}
							>
								{generating ? (
									<>
										<Loader2 className="h-4 w-4 animate-spin mr-2" />
										Genererar...
									</>
								) : filterMode === "intent-layer" ? (
									<>
										<Layers className="h-4 w-4 mr-2" />
										Optimera Intent-lager
									</>
								) : (
									<>
										<Sparkles className="h-4 w-4 mr-2" />
										Generera{selectedToolCount > 0 ? ` (${selectedToolCount} verktyg)` : ""}
									</>
								)}
							</Button>
						</div>

						{activeModelUsed && (
							<p className="text-xs text-muted-foreground">
								Modell: {activeModelUsed}
							</p>
						)}
					</div>
				</CardContent>
			</Card>

			{/* Error */}
			{activeError && (
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertDescription>{activeError}</AlertDescription>
				</Alert>
			)}

			{/* Results */}
			{hasResult && activeSuggestionCount > 0 && (
				<Card>
					<CardHeader className="flex flex-row items-center justify-between">
						<div>
							<CardTitle className="text-base">
								Förslag ({activeSuggestionCount} av {activeTotalCount}{" "}
								{filterMode === "intent-layer" ? "objekt" : "verktyg"})
							</CardTitle>
							<p className="text-xs text-muted-foreground mt-1">
								{approvedCount} godkända · {rejectedCount} avvisade · {pendingCount}{" "}
								väntande
							</p>
						</div>
						<div className="flex items-center gap-2">
							<Button variant="outline" size="sm" onClick={handleApproveAll}>
								Godkänn alla
							</Button>
							<Button
								size="sm"
								onClick={handleApply}
								disabled={applying || approvedCount === 0}
							>
								{applying ? (
									<>
										<Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
										Tillämpar...
									</>
								) : (
									<>
										<Check className="h-3.5 w-3.5 mr-1.5" />
										Tillämpa {approvedCount > 0 ? `(${approvedCount})` : ""}
									</>
								)}
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						{applyResult && (
							<Alert className="mb-4">
								<AlertDescription>{applyResult}</AlertDescription>
							</Alert>
						)}

						<div className="space-y-3">
							{filterMode === "intent-layer" && intentResult
								? intentResult.suggestions.map((s) => {
										const key = `${s.item_type}:${s.item_id}`;
										return (
											<IntentLayerSuggestionCard
												key={key}
												suggestion={s}
												approved={approvalMap[key] ?? null}
												onApprove={() => handleApprove(key)}
												onReject={() => handleReject(key)}
											/>
										);
									})
								: result?.suggestions.map((s) => (
										<SuggestionCard
											key={s.tool_id}
											suggestion={s}
											approved={approvalMap[s.tool_id] ?? null}
											onApprove={() => handleApprove(s.tool_id)}
											onReject={() => handleReject(s.tool_id)}
										/>
									))}
						</div>
					</CardContent>
				</Card>
			)}

			{/* No suggestions */}
			{hasResult && activeSuggestionCount === 0 && !activeError && (
				<Card>
					<CardContent className="pt-6">
						<p className="text-sm text-muted-foreground text-center">
							Inga förändringar föreslogs — metadata är redan bra optimerad.
						</p>
					</CardContent>
				</Card>
			)}
		</div>
	);
}
