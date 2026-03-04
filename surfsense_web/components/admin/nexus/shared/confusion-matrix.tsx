"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	nexusApiService,
	type ConfusionPair,
} from "@/lib/apis/nexus-api.service";

export function ConfusionMatrix() {
	const [pairs, setPairs] = useState<ConfusionPair[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		nexusApiService
			.getConfusion()
			.then(setPairs)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	}, []);

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground p-4">
				<Loader2 className="h-4 w-4 animate-spin" />
				Laddar confusion-par...
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

	if (pairs.length === 0) {
		return (
			<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
				Inga confusion-par hittade. Kör en space-snapshot för att generera data.
			</div>
		);
	}

	return (
		<div className="rounded-lg border bg-card">
			<div className="p-4 border-b">
				<h3 className="font-semibold">Confusion Register</h3>
				<p className="text-sm text-muted-foreground">
					Verktygspar med hög similarity (risk för felrouting)
				</p>
			</div>
			<div className="divide-y">
				{pairs.map((pair) => (
					<div
						key={`${pair.tool_a}-${pair.tool_b}`}
						className="flex items-center justify-between p-4"
					>
						<div className="flex items-center gap-3">
							<span className="font-mono text-sm">{pair.tool_a}</span>
							<span className="text-muted-foreground">↔</span>
							<span className="font-mono text-sm">{pair.tool_b}</span>
						</div>
						<div className="flex items-center gap-4">
							{pair.zone_a !== pair.zone_b && (
								<span className="text-xs px-2 py-0.5 rounded bg-orange-100 text-orange-700">
									Cross-zone
								</span>
							)}
							<SimilarityBadge value={pair.similarity} />
						</div>
					</div>
				))}
			</div>
		</div>
	);
}

function SimilarityBadge({ value }: { value: number }) {
	const pct = (value * 100).toFixed(1);
	const color =
		value >= 0.95
			? "text-red-700 bg-red-100"
			: value >= 0.90
				? "text-orange-700 bg-orange-100"
				: "text-yellow-700 bg-yellow-100";

	return (
		<span className={`text-xs font-mono px-2 py-0.5 rounded ${color}`}>
			{pct}%
		</span>
	);
}
