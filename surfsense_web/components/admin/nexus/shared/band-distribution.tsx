"use client";

import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";

const BANDS = [
	{
		band: 0,
		name: "DIREKT",
		description: "Direkt route, ingen LLM",
		color: "bg-green-500",
		target: "> 80%",
	},
	{
		band: 1,
		name: "VERIFY",
		description: "Namespace-verifiering, minimal LLM",
		color: "bg-blue-500",
		target: "< 10%",
	},
	{
		band: 2,
		name: "TOP-3 LLM",
		description: "Top-3 kandidater, LLM väljer",
		color: "bg-amber-500",
		target: "< 5%",
	},
	{
		band: 3,
		name: "DECOMPOSE",
		description: "Omformulera eller dela upp",
		color: "bg-orange-500",
		target: "< 3%",
	},
	{
		band: 4,
		name: "OOD",
		description: "Okänd frågetyp, fallback",
		color: "bg-red-500",
		target: "< 3%",
	},
];

export function BandDistribution() {
	// Placeholder data — replaced with real data when routing events exist
	const distribution = [0, 0, 0, 0, 0];
	const total = distribution.reduce((a, b) => a + b, 0);

	return (
		<Card>
			<CardHeader>
				<CardTitle>Confidence Band Fördelning</CardTitle>
				<CardDescription>
					Hur frågor fördelas över 5 confidence bands. Mål: Band-0 throughput
					&gt; 80%
				</CardDescription>
			</CardHeader>
			<CardContent>
				<div className="space-y-3">
					{BANDS.map((band) => {
						const count = distribution[band.band];
						const pct = total > 0 ? (count / total) * 100 : 0;

						return (
							<div key={band.band} className="space-y-1">
								<div className="flex items-center justify-between text-sm">
									<div className="flex items-center gap-2">
										<div
											className={`h-3 w-3 rounded-sm ${band.color}`}
										/>
										<span className="font-medium">
											Band {band.band}: {band.name}
										</span>
										<span className="text-muted-foreground text-xs">
											{band.description}
										</span>
									</div>
									<div className="flex items-center gap-3">
										<span className="text-xs text-muted-foreground">
											Mål: {band.target}
										</span>
										<span className="font-mono text-sm tabular-nums w-12 text-right">
											{total > 0 ? `${pct.toFixed(0)}%` : "—"}
										</span>
									</div>
								</div>
								<div className="h-2 rounded-full bg-muted overflow-hidden">
									<div
										className={`h-full rounded-full transition-all ${band.color}`}
										style={{ width: `${pct}%` }}
									/>
								</div>
							</div>
						);
					})}
				</div>

				{total === 0 && (
					<p className="text-center text-sm text-muted-foreground mt-6">
						Inga routing-händelser registrerade ännu. Kör{" "}
						<code className="text-xs bg-muted px-1 py-0.5 rounded">
							POST /api/v1/nexus/routing/route
						</code>{" "}
						för att börja samla data.
					</p>
				)}
			</CardContent>
		</Card>
	);
}
