"use client";

import { useEffect, useState } from "react";
import {
	AlertCircle,
	Beaker,
	CheckCircle2,
	Clock,
	Loader2,
	Play,
	XCircle,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
	nexusApiService,
	type AutoLoopRunResponse,
	type PlatformToolResponse,
} from "@/lib/apis/nexus-api.service";

const CATEGORY_LABELS: Record<string, string> = {
	"": "Alla kategorier",
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

export function LoopTab() {
	const [runs, setRuns] = useState<AutoLoopRunResponse[]>([]);
	const [platformTools, setPlatformTools] = useState<PlatformToolResponse[]>([]);
	const [categories, setCategories] = useState<string[]>([]);
	const [selectedCategory, setSelectedCategory] = useState<string>("");
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [starting, setStarting] = useState(false);

	const loadRuns = () => {
		setLoading(true);
		nexusApiService
			.getLoopRuns()
			.then(setRuns)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	};

	const loadPlatformTools = () => {
		nexusApiService
			.getPlatformTools()
			.then((data) => {
				setPlatformTools(data.tools || []);
				setCategories(data.categories || []);
			})
			.catch(() => {
				/* non-critical */
			});
	};

	useEffect(() => {
		loadRuns();
		loadPlatformTools();
	}, []);

	const handleStart = () => {
		setStarting(true);
		const request = selectedCategory ? { category: selectedCategory } : {};
		nexusApiService
			.startLoop(request)
			.then(() => {
				loadRuns();
			})
			.catch((err) => setError(err.message))
			.finally(() => setStarting(false));
	};

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground p-4">
				<Loader2 className="h-4 w-4 animate-spin" />
				Laddar loop-körningar...
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
			{/* Header + Category Filter + Start Button */}
			<div className="flex items-center justify-between">
				<div>
					<h3 className="text-lg font-semibold flex items-center gap-2">
						<Beaker className="h-5 w-5" />
						Auto Loop — Självförbättring
					</h3>
					<p className="text-sm text-muted-foreground">
						7-stegs pipeline: generera, eval, kluster, root cause, test, review, deploy
					</p>
				</div>
				<div className="flex items-center gap-3">
					<select
						value={selectedCategory}
						onChange={(e) => setSelectedCategory(e.target.value)}
						className="rounded-md border bg-background px-3 py-2 text-sm"
					>
						<option value="">Alla kategorier ({platformTools.length} verktyg)</option>
						{categories
							.filter((c) => c !== "external_model")
							.map((cat) => (
								<option key={cat} value={cat}>
									{CATEGORY_LABELS[cat] || cat} (
									{platformTools.filter((t) => t.category === cat).length})
								</option>
							))}
					</select>
					<Button onClick={handleStart} disabled={starting}>
						{starting ? (
							<Loader2 className="h-4 w-4 animate-spin mr-2" />
						) : (
							<Play className="h-4 w-4 mr-2" />
						)}
						{starting
							? "Kör loop..."
							: selectedCategory
								? `Kör loop för ${CATEGORY_LABELS[selectedCategory] || selectedCategory}`
								: "Starta loop"}
					</Button>
				</div>
			</div>

			{/* Stats */}
			<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
				<StatCard label="Totalt körningar" value={String(runs.length)} />
				<StatCard
					label="Godkända förslag"
					value={String(
						runs.reduce((sum, r) => sum + (r.approved_proposals || 0), 0),
					)}
				/>
				<StatCard
					label="Senaste status"
					value={runs.length > 0 ? runs[0].status : "—"}
				/>
			</div>

			{/* Run history */}
			{runs.length === 0 ? (
				<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
					Inga loop-körningar ännu. Klicka &quot;Starta loop&quot; för att börja.
				</div>
			) : (
				<div className="rounded-lg border bg-card">
					<div className="p-4 border-b">
						<h4 className="font-semibold">Körningshistorik</h4>
					</div>
					<div className="divide-y">
						{runs.map((run) => (
							<div
								key={run.id}
								className="flex items-center justify-between p-4"
							>
								<div className="flex items-center gap-3">
									<StatusIcon status={run.status} />
									<div>
										<p className="text-sm font-medium">
											Loop #{run.loop_number}
										</p>
										<p className="text-xs text-muted-foreground">
											{run.started_at
												? new Date(run.started_at).toLocaleString("sv-SE")
												: "Ej startad"}
										</p>
									</div>
								</div>
								<div className="flex items-center gap-4 text-sm">
									{run.total_tests !== null && (
										<span className="text-muted-foreground">
											{run.failures || 0}/{run.total_tests} fel
										</span>
									)}
									{run.approved_proposals !== null &&
										run.approved_proposals > 0 && (
											<span className="text-green-600 font-medium">
												{run.approved_proposals} godkända
											</span>
										)}
									<StatusBadge status={run.status} />
								</div>
							</div>
						))}
					</div>
				</div>
			)}
		</div>
	);
}

function StatCard({ label, value }: { label: string; value: string }) {
	return (
		<div className="rounded-lg border bg-card p-4">
			<p className="text-sm text-muted-foreground">{label}</p>
			<p className="text-2xl font-bold mt-1">{value}</p>
		</div>
	);
}

function StatusIcon({ status }: { status: string }) {
	switch (status) {
		case "approved":
		case "deployed":
			return <CheckCircle2 className="h-5 w-5 text-green-600" />;
		case "rejected":
		case "failed":
			return <XCircle className="h-5 w-5 text-red-600" />;
		case "running":
		case "analyzing":
		case "proposing":
			return <Loader2 className="h-5 w-5 text-blue-600 animate-spin" />;
		default:
			return <Clock className="h-5 w-5 text-muted-foreground" />;
	}
}

function StatusBadge({ status }: { status: string }) {
	const colors: Record<string, string> = {
		pending: "bg-gray-100 text-gray-700",
		running: "bg-blue-100 text-blue-700",
		analyzing: "bg-blue-100 text-blue-700",
		proposing: "bg-purple-100 text-purple-700",
		review: "bg-yellow-100 text-yellow-700",
		approved: "bg-green-100 text-green-700",
		rejected: "bg-red-100 text-red-700",
		deployed: "bg-green-100 text-green-700",
		failed: "bg-red-100 text-red-700",
	};
	const color = colors[status] || "bg-gray-100 text-gray-700";

	return (
		<span className={`text-xs px-2 py-0.5 rounded ${color}`}>{status}</span>
	);
}
