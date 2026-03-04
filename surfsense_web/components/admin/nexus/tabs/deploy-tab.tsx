"use client";

import { useEffect, useState } from "react";
import {
	AlertCircle,
	ArrowRight,
	CheckCircle2,
	Loader2,
	Rocket,
	RotateCcw,
	Search,
	Shield,
	XCircle,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
	nexusApiService,
	type GateStatusResponse,
	type PlatformToolResponse,
} from "@/lib/apis/nexus-api.service";

const CATEGORY_LABELS: Record<string, string> = {
	smhi: "SMHI (Väder)",
	scb: "SCB (Statistik)",
	kolada: "Kolada (Nyckeltal)",
	riksdagen: "Riksdagen",
	trafikverket: "Trafikverket",
	bolagsverket: "Bolagsverket",
	marketplace: "Marknadsplats",
	skolverket: "Skolverket",
	builtin: "Inbyggda verktyg",
	geoapify: "Kartor (Geoapify)",
};

export function DeployTab() {
	const [toolId, setToolId] = useState("");
	const [gateStatus, setGateStatus] = useState<GateStatusResponse | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [actionMessage, setActionMessage] = useState<string | null>(null);

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
								<p className="text-lg font-mono font-bold">{gateStatus.tool_id}</p>
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
								<Button variant="outline" size="sm" onClick={handleRollback}>
									<RotateCcw className="h-4 w-4 mr-1" />
									Rollback
								</Button>
							</div>
						</div>
					</div>

					{/* Gates */}
					<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
						{gateStatus.gates.map((gate) => (
							<div key={gate.gate_number} className="rounded-lg border bg-card p-4">
								<div className="flex items-center gap-2 mb-2">
									{gate.passed ? (
										<CheckCircle2 className="h-5 w-5 text-green-600" />
									) : (
										<XCircle className="h-5 w-5 text-red-600" />
									)}
									<h4 className="font-semibold text-sm">
										Gate {gate.gate_number}: {gate.gate_name}
									</h4>
								</div>
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
							</div>
						))}
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
