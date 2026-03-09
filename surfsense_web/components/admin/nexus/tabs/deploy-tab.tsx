"use client";

import { useEffect, useState } from "react";
import {
	AlertCircle,
	ArrowRight,
	CheckCircle2,
	ChevronDown,
	ChevronUp,
	Loader2,
	Rocket,
	RotateCcw,
	Search,
	Shield,
	XCircle,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
	AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	nexusApiService,
	type GateStatusResponse,
	type PlatformToolResponse,
} from "@/lib/apis/nexus-api.service";
import { useCategoryLabels } from "@/components/admin/nexus/shared/use-category-labels";

const STAGE_LABELS: Record<string, string> = {
	review: "REVIEW",
	staging: "STAGING",
	live: "LIVE",
	rolled_back: "ROLLED BACK",
};

const STAGE_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
	review: "outline",
	staging: "secondary",
	live: "default",
	rolled_back: "destructive",
};

const GATE_REQUIREMENTS: Record<number, { requirement: string; thresholdExplanation: string; howToPass: string }> = {
	1: {
		requirement: "Separation-gate: Verktygets kod och konfiguration måste vara korrekt separerade från andra verktyg. Inga hårda beroenden till andra moduler.",
		thresholdExplanation: "Poängen mäter graden av kodmässig separation. Värden över tröskeln indikerar tillräcklig isolation.",
		howToPass: "Se till att verktyget har egen konfiguration, inga cirkulära beroenden, och att det kan laddas oberoende av andra verktyg.",
	},
	2: {
		requirement: "Eval-gate: Verktyget måste klara automatiserade utvärderingstester med tillräckligt högt resultat.",
		thresholdExplanation: "Poängen baseras på hur många eval-testfall verktyget klarar. Tröskeln anger minimikravet för godkänt.",
		howToPass: "Kör eval-sviten och åtgärda eventuella felaktiga svar. Kontrollera att verktygets output matchar förväntade resultat.",
	},
	3: {
		requirement: "LLM-judge-gate: En LLM-baserad bedömare utvärderar verktygets svar kvalitativt — relevans, korrekthet och användbarhet.",
		thresholdExplanation: "LLM-bedömaren ger ett kvalitetspoäng. Tröskeln anger den lägsta acceptabla kvalitetsnivån.",
		howToPass: "Förbättra verktygets prompter och svarsformat. Se till att svaren är tydliga, korrekta och relevanta för användarens fråga.",
	},
};

export function DeployTab() {
	const CATEGORY_LABELS = useCategoryLabels();
	const [toolId, setToolId] = useState("");
	const [gateStatus, setGateStatus] = useState<GateStatusResponse | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [actionMessage, setActionMessage] = useState<string | null>(null);
	const [expandedGates, setExpandedGates] = useState<Record<number, boolean>>({});

	// Platform tools for the tool picker
	const [platformTools, setPlatformTools] = useState<PlatformToolResponse[]>([]);
	const [categories, setCategories] = useState<string[]>([]);
	const [selectedCategory, setSelectedCategory] = useState<string>("");
	const [searchQuery, setSearchQuery] = useState("");
	const [toolsLoading, setToolsLoading] = useState(true);

	useEffect(() => {
		nexusApiService
			.getPlatformTools()
			.then((data) => {
				setPlatformTools(data.tools || []);
				setCategories(data.categories || []);
			})
			.catch(() => {
				/* non-critical */
			})
			.finally(() => setToolsLoading(false));
	}, []);

	const checkGates = (id?: string) => {
		const tid = (id || toolId).trim();
		if (!tid) return;
		setToolId(tid);
		setLoading(true);
		setError(null);
		setActionMessage(null);
		setExpandedGates({});
		nexusApiService
			.getDeployGates(tid)
			.then(setGateStatus)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	};

	const handlePromote = () => {
		if (!toolId.trim()) return;
		nexusApiService
			.promoteTool(toolId.trim())
			.then((result) => {
				setActionMessage(result.message);
				checkGates();
			})
			.catch((err) => setError(err.message));
	};

	const handleRollback = () => {
		if (!toolId.trim()) return;
		nexusApiService
			.rollbackTool(toolId.trim())
			.then((result) => {
				setActionMessage(result.message);
				checkGates();
			})
			.catch((err) => setError(err.message));
	};

	const toggleGateExpanded = (gateNumber: number) => {
		setExpandedGates((prev) => ({
			...prev,
			[gateNumber]: !prev[gateNumber],
		}));
	};

	// Get the current lifecycle stage from the selected tool
	const selectedTool = platformTools.find((t) => t.tool_id === toolId);
	const currentStage = selectedTool?.zone?.toLowerCase() || "";

	// Filter tools by category and search
	const filteredTools = platformTools.filter((t) => {
		if (t.category === "external_model") return false;
		if (selectedCategory && t.category !== selectedCategory) return false;
		if (searchQuery) {
			const q = searchQuery.toLowerCase();
			return (
				t.tool_id.toLowerCase().includes(q) ||
				t.name.toLowerCase().includes(q) ||
				t.description.toLowerCase().includes(q)
			);
		}
		return true;
	});

	return (
		<div className="space-y-6">
			{/* Header */}
			<div>
				<h3 className="text-lg font-semibold flex items-center gap-2">
					<Rocket className="h-5 w-5" />
					Deploy Control — Triple-gate Lifecycle
				</h3>
				<p className="text-sm text-muted-foreground">
					REVIEW → STAGING → LIVE med tre gates: separation, eval, LLM-judge
				</p>
			</div>

			{/* Tool Picker */}
			<div className="rounded-lg border bg-card p-4 space-y-3">
				<div className="flex items-center gap-3">
					<select
						value={selectedCategory}
						onChange={(e) => setSelectedCategory(e.target.value)}
						className="rounded-md border bg-background px-3 py-2 text-sm"
					>
						<option value="">
							Alla kategorier (
							{platformTools.filter((t) => t.category !== "external_model").length})
						</option>
						{categories
							.filter((c) => c !== "external_model")
							.map((cat) => (
								<option key={cat} value={cat}>
									{CATEGORY_LABELS[cat] || cat} (
									{platformTools.filter((t) => t.category === cat).length})
								</option>
							))}
					</select>
					<div className="relative flex-1">
						<Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
						<input
							type="text"
							value={searchQuery}
							onChange={(e) => setSearchQuery(e.target.value)}
							placeholder="Sök verktyg..."
							className="w-full pl-9 pr-3 py-2 rounded-md border bg-background text-sm"
						/>
					</div>
				</div>

				{/* Tool list */}
				{toolsLoading ? (
					<div className="flex items-center gap-2 text-muted-foreground p-2">
						<Loader2 className="h-4 w-4 animate-spin" />
						Laddar verktyg...
					</div>
				) : (
					<div className="max-h-64 overflow-y-auto border rounded divide-y">
						{filteredTools.slice(0, 50).map((tool) => (
							<button
								type="button"
								key={tool.tool_id}
								onClick={() => checkGates(tool.tool_id)}
								className={`w-full text-left px-3 py-2 hover:bg-muted/50 transition-colors ${
									toolId === tool.tool_id ? "bg-muted" : ""
								}`}
							>
								<div className="flex items-center justify-between">
									<div>
										<span className="font-mono text-sm">{tool.tool_id}</span>
										<span className="text-xs text-muted-foreground ml-2">
											{CATEGORY_LABELS[tool.category] || tool.category}
										</span>
									</div>
									<span className="text-xs text-muted-foreground">{tool.zone}</span>
								</div>
								{tool.description && (
									<p className="text-xs text-muted-foreground truncate mt-0.5">
										{tool.description.slice(0, 100)}
									</p>
								)}
							</button>
						))}
						{filteredTools.length === 0 && (
							<div className="p-4 text-center text-sm text-muted-foreground">
								Inga verktyg matchar filtret.
							</div>
						)}
						{filteredTools.length > 50 && (
							<div className="p-2 text-center text-xs text-muted-foreground">
								Visar 50 av {filteredTools.length} verktyg. Filtrera för att se fler.
							</div>
						)}
					</div>
				)}
			</div>

			{error && (
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			)}

			{actionMessage && (
				<Alert>
					<CheckCircle2 className="h-4 w-4" />
					<AlertDescription>{actionMessage}</AlertDescription>
				</Alert>
			)}

			{/* Gate Status */}
			{loading && (
				<div className="flex items-center gap-2 text-muted-foreground p-4">
					<Loader2 className="h-4 w-4 animate-spin" />
					Kontrollerar gates...
				</div>
			)}

			{gateStatus && !loading && (
				<div className="space-y-4">
					{/* Summary */}
					<div className="rounded-lg border bg-card p-4">
						<div className="flex items-center justify-between">
							<div>
								<p className="text-sm text-muted-foreground">Verktyg</p>
								<div className="flex items-center gap-3">
									<p className="text-lg font-mono font-bold">{gateStatus.tool_id}</p>
									{/* Current lifecycle stage badge */}
									{currentStage && (
										<Badge variant={STAGE_VARIANTS[currentStage] || "outline"}>
											<Shield className="h-3 w-3" />
											{STAGE_LABELS[currentStage] || currentStage.toUpperCase()}
										</Badge>
									)}
								</div>
							</div>
							<div className="flex items-center gap-3">
								<RecommendationBadge recommendation={gateStatus.recommendation} />
								<Button
									variant="outline"
									size="sm"
									onClick={handlePromote}
									disabled={!gateStatus.all_passed}
								>
									<ArrowRight className="h-4 w-4 mr-1" />
									Promote
								</Button>
								{/* Rollback with confirmation dialog */}
								<AlertDialog>
									<AlertDialogTrigger asChild>
										<Button variant="outline" size="sm">
											<RotateCcw className="h-4 w-4 mr-1" />
											Rollback
										</Button>
									</AlertDialogTrigger>
									<AlertDialogContent>
										<AlertDialogHeader>
											<AlertDialogTitle>Är du säker?</AlertDialogTitle>
											<AlertDialogDescription>
												Du håller på att rulla tillbaka verktyget{" "}
												<span className="font-mono font-semibold">{gateStatus.tool_id}</span>.
												Detta kommer att flytta verktyget till ROLLED BACK-stadiet och det
												kommer inte längre vara tillgängligt i sin nuvarande fas.
											</AlertDialogDescription>
										</AlertDialogHeader>
										<AlertDialogFooter>
											<AlertDialogCancel>Avbryt</AlertDialogCancel>
											<AlertDialogAction onClick={handleRollback}>
												Bekräfta rollback
											</AlertDialogAction>
										</AlertDialogFooter>
									</AlertDialogContent>
								</AlertDialog>
							</div>
						</div>
					</div>

					{/* Gates */}
					<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
						{gateStatus.gates.map((gate) => {
							const isExpanded = expandedGates[gate.gate_number] || false;
							const gateInfo = GATE_REQUIREMENTS[gate.gate_number];

							return (
								<div key={gate.gate_number} className="rounded-lg border bg-card p-4">
									<button
										type="button"
										onClick={() => toggleGateExpanded(gate.gate_number)}
										className="w-full text-left"
									>
										<div className="flex items-center justify-between mb-2">
											<div className="flex items-center gap-2">
												{gate.passed ? (
													<CheckCircle2 className="h-5 w-5 text-green-600" />
												) : (
													<XCircle className="h-5 w-5 text-red-600" />
												)}
												<h4 className="font-semibold text-sm">
													Gate {gate.gate_number}: {gate.gate_name}
												</h4>
											</div>
											{isExpanded ? (
												<ChevronUp className="h-4 w-4 text-muted-foreground" />
											) : (
												<ChevronDown className="h-4 w-4 text-muted-foreground" />
											)}
										</div>
									</button>
									{gate.score !== null && gate.score !== undefined && (
										<p className="text-2xl font-bold font-mono">
											{gate.score.toFixed(3)}
										</p>
									)}
									{gate.threshold !== null && gate.threshold !== undefined && (
										<p className="text-xs text-muted-foreground">
											Tröskel: {gate.threshold}
										</p>
									)}
									<p className="text-xs text-muted-foreground mt-1">{gate.details}</p>

									{/* Expandable gate details */}
									{isExpanded && gateInfo && (
										<div className="mt-3 pt-3 border-t space-y-2">
											<div>
												<p className="text-xs font-semibold text-foreground">Krav</p>
												<p className="text-xs text-muted-foreground">
													{gateInfo.requirement}
												</p>
											</div>
											<div>
												<p className="text-xs font-semibold text-foreground">
													Tröskelförklaring
												</p>
												<p className="text-xs text-muted-foreground">
													{gateInfo.thresholdExplanation}
												</p>
											</div>
											<div>
												<p className="text-xs font-semibold text-foreground">
													Vad krävs för att passera
												</p>
												<p className="text-xs text-muted-foreground">
													{gateInfo.howToPass}
												</p>
											</div>
										</div>
									)}
								</div>
							);
						})}
					</div>
				</div>
			)}
		</div>
	);
}

function RecommendationBadge({ recommendation }: { recommendation: string }) {
	const colors: Record<string, string> = {
		promote: "bg-green-100 text-green-700",
		review: "bg-yellow-100 text-yellow-700",
		fix_required: "bg-red-100 text-red-700",
	};
	const color = colors[recommendation] || "bg-gray-100 text-gray-700";

	return (
		<span className={`text-xs px-2 py-0.5 rounded font-medium ${color}`}>
			{recommendation}
		</span>
	);
}
