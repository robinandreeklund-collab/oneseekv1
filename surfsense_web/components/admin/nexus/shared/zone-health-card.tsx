"use client";

import { useEffect, useState } from "react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";
import {
	nexusApiService,
	type ZoneConfigResponse,
	type DomainMetadata,
} from "@/lib/apis/nexus-api.service";

function MetricBar({
	label,
	value,
	target,
	max = 1,
}: {
	label: string;
	value: number | null;
	target?: number;
	max?: number;
}) {
	const pct = value != null ? Math.min((value / max) * 100, 100) : 0;
	const isGood = target != null && value != null && value >= target;

	return (
		<div className="space-y-1">
			<div className="flex justify-between text-xs">
				<span className="text-muted-foreground">{label}</span>
				<span className={isGood ? "text-green-600 font-medium" : ""}>
					{value != null ? value.toFixed(2) : "—"}
				</span>
			</div>
			<div className="h-1.5 rounded-full bg-muted overflow-hidden">
				<div
					className={`h-full rounded-full transition-all ${
						isGood ? "bg-green-500" : "bg-amber-500"
					}`}
					style={{ width: `${pct}%` }}
				/>
			</div>
		</div>
	);
}

export function ZoneHealthCard() {
	const [zones, setZones] = useState<ZoneConfigResponse[]>([]);
	const [domains, setDomains] = useState<DomainMetadata[]>([]);
	const [loading, setLoading] = useState(true);

	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		Promise.all([
			nexusApiService.getZones(),
			nexusApiService.getDomainMetadata().catch(() => ({ domains: [] })),
		])
			.then(([z, d]) => {
				setZones(z);
				setDomains(d.domains);
			})
			.catch((err) => setError(err.message || "Kunde inte hämta zondata"))
			.finally(() => setLoading(false));
	}, []);

	// Build dynamic label/description lookups from domain metadata
	const domainLabels: Record<string, string> = {};
	const domainDescriptions: Record<string, string> = {};
	for (const d of domains) {
		domainLabels[d.domain_id] = d.label;
		domainDescriptions[d.domain_id] = d.description;
	}

	if (loading) {
		return (
			<Card>
				<CardContent className="flex items-center justify-center h-32">
					<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
				</CardContent>
			</Card>
		);
	}

	if (error) {
		return (
			<Card>
				<CardContent className="flex items-center justify-center h-32 text-muted-foreground">
					<p className="text-sm">{error}</p>
				</CardContent>
			</Card>
		);
	}

	return (
		<Card>
			<CardHeader>
				<CardTitle>Zonhälsa</CardTitle>
				<CardDescription>
					Embedding-zoner med hälsometriker — {zones.length} domänzoner styr precision routing
				</CardDescription>
			</CardHeader>
			<CardContent>
				<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
					{zones.map((zone) => (
						<div
							key={zone.zone}
							className="rounded-lg border p-4 space-y-3"
						>
							<div className="flex items-center justify-between">
								<h4 className="font-medium">
									{domainLabels[zone.zone] || zone.zone}
								</h4>
								<Badge variant="outline" className="text-xs font-mono">
									{zone.prefix_token.trim()}
								</Badge>
							</div>
							<p className="text-xs text-muted-foreground">
								{domainDescriptions[zone.zone] || ""}
							</p>

							<div className="space-y-2">
								<MetricBar
									label="Band-0 rate"
									value={zone.band0_rate}
									target={0.8}
								/>
								<MetricBar
									label="Silhouette"
									value={zone.silhouette_score}
									target={0.6}
								/>
								<MetricBar
									label="ECE"
									value={zone.ece_score != null ? 1 - zone.ece_score : null}
									target={0.95}
								/>
							</div>
						</div>
					))}
				</div>
			</CardContent>
		</Card>
	);
}
