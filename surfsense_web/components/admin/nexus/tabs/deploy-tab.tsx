"use client";

import { useEffect, useState } from "react";
import {
	AlertCircle,
	ArrowRight,
	CheckCircle2,
	Loader2,
	Rocket,
	RotateCcw,
	Shield,
	XCircle,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
	nexusApiService,
	type GateStatusResponse,
} from "@/lib/apis/nexus-api.service";

export function DeployTab() {
	const [toolId, setToolId] = useState("");
	const [gateStatus, setGateStatus] = useState<GateStatusResponse | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [actionMessage, setActionMessage] = useState<string | null>(null);

	const checkGates = () => {
		if (!toolId.trim()) return;
		setLoading(true);
		setError(null);
		setActionMessage(null);
		nexusApiService
			.getDeployGates(toolId.trim())
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

			{/* Tool ID input */}
			<div className="flex items-center gap-3">
				<input
					type="text"
					value={toolId}
					onChange={(e) => setToolId(e.target.value)}
					placeholder="Ange tool_id..."
					className="flex-1 px-3 py-2 rounded-md border bg-background text-sm"
					onKeyDown={(e) => e.key === "Enter" && checkGates()}
				/>
				<Button onClick={checkGates} disabled={loading || !toolId.trim()}>
					{loading ? (
						<Loader2 className="h-4 w-4 animate-spin mr-2" />
					) : (
						<Shield className="h-4 w-4 mr-2" />
					)}
					Kontrollera gates
				</Button>
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
			{gateStatus && (
				<div className="space-y-4">
					{/* Summary */}
					<div className="rounded-lg border bg-card p-4">
						<div className="flex items-center justify-between">
							<div>
								<p className="text-sm text-muted-foreground">Verktyg</p>
								<p className="text-lg font-mono font-bold">
									{gateStatus.tool_id}
								</p>
							</div>
							<div className="flex items-center gap-3">
								<RecommendationBadge
									recommendation={gateStatus.recommendation}
								/>
								<Button
									variant="outline"
									size="sm"
									onClick={handlePromote}
									disabled={!gateStatus.all_passed}
								>
									<ArrowRight className="h-4 w-4 mr-1" />
									Promote
								</Button>
								<Button
									variant="outline"
									size="sm"
									onClick={handleRollback}
								>
									<RotateCcw className="h-4 w-4 mr-1" />
									Rollback
								</Button>
							</div>
						</div>
					</div>

					{/* Gates */}
					<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
						{gateStatus.gates.map((gate) => (
							<div
								key={gate.gate_number}
								className="rounded-lg border bg-card p-4"
							>
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
								<p className="text-xs text-muted-foreground mt-1">
									{gate.details}
								</p>
							</div>
						))}
					</div>
				</div>
			)}

			{/* Empty state */}
			{!gateStatus && !loading && !error && (
				<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
					Ange ett tool_id och klicka "Kontrollera gates" för att se deploymentstatus.
				</div>
			)}
		</div>
	);
}

function RecommendationBadge({
	recommendation,
}: {
	recommendation: string;
}) {
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
