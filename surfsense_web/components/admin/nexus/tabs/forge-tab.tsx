"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, Sparkles, Play, CheckCircle2, XCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
	nexusApiService,
	type SyntheticCaseResponse,
} from "@/lib/apis/nexus-api.service";

export function ForgeTab() {
	const [cases, setCases] = useState<SyntheticCaseResponse[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [generating, setGenerating] = useState(false);

	const loadCases = () => {
		setLoading(true);
		nexusApiService
			.getForgeCases()
			.then(setCases)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	};

	useEffect(() => {
		loadCases();
	}, []);

	const handleGenerate = () => {
		setGenerating(true);
		nexusApiService
			.forgeGenerate({})
			.then(() => {
				loadCases();
			})
			.catch((err) => setError(err.message))
			.finally(() => setGenerating(false));
	};

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground p-4">
				<Loader2 className="h-4 w-4 animate-spin" />
				Laddar syntetiska testfall...
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
			{/* Header + Generate Button */}
			<div className="flex items-center justify-between">
				<div>
					<h3 className="text-lg font-semibold flex items-center gap-2">
						<Sparkles className="h-5 w-5" />
						Synth Forge — Testgenerering
					</h3>
					<p className="text-sm text-muted-foreground">
						LLM-genererade testfrågor vid 4 svårighetsgrader per verktyg
					</p>
				</div>
				<Button onClick={handleGenerate} disabled={generating}>
					{generating ? (
						<Loader2 className="h-4 w-4 animate-spin mr-2" />
					) : (
						<Play className="h-4 w-4 mr-2" />
					)}
					{generating ? "Genererar..." : "Generera testfall"}
				</Button>
			</div>

			{/* Stats */}
			<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
				<StatCard
					label="Totalt testfall"
					value={String(cases.length)}
				/>
				<StatCard
					label="Verifierade"
					value={String(cases.filter((c) => c.roundtrip_verified).length)}
				/>
				<StatCard
					label="Svårighetsgrader"
					value={String(new Set(cases.map((c) => c.difficulty)).size)}
				/>
				<StatCard
					label="Verktyg"
					value={String(new Set(cases.map((c) => c.tool_id)).size)}
				/>
			</div>

			{/* Cases by difficulty */}
			{cases.length === 0 ? (
				<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
					Inga syntetiska testfall genererade ännu. Klicka "Generera testfall" för att börja.
				</div>
			) : (
				<div className="rounded-lg border bg-card">
					<div className="p-4 border-b">
						<h4 className="font-semibold">Testfall ({cases.length})</h4>
					</div>
					<div className="divide-y max-h-96 overflow-y-auto">
						{cases.map((c) => (
							<div
								key={c.id}
								className="flex items-start justify-between p-4 gap-4"
							>
								<div className="flex-1 min-w-0">
									<p className="text-sm font-medium truncate">
										{c.question}
									</p>
									<p className="text-xs text-muted-foreground mt-1">
										{c.tool_id} &middot; {c.namespace}
									</p>
								</div>
								<div className="flex items-center gap-2 shrink-0">
									<DifficultyBadge difficulty={c.difficulty} />
									{c.roundtrip_verified ? (
										<CheckCircle2 className="h-4 w-4 text-green-600" />
									) : (
										<XCircle className="h-4 w-4 text-muted-foreground" />
									)}
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

function DifficultyBadge({ difficulty }: { difficulty: string }) {
	const colors: Record<string, string> = {
		easy: "bg-green-100 text-green-700",
		medium: "bg-yellow-100 text-yellow-700",
		hard: "bg-orange-100 text-orange-700",
		adversarial: "bg-red-100 text-red-700",
	};
	const color = colors[difficulty] || "bg-gray-100 text-gray-700";

	return (
		<span className={`text-xs px-2 py-0.5 rounded ${color}`}>
			{difficulty}
		</span>
	);
}
