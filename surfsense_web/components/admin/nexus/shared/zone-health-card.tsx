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
} from "@/lib/apis/nexus-api.service";

const ZONE_LABELS: Record<string, string> = {
	// Legacy zones
	kunskap: "Allmän kunskap",
	skapande: "Skapande & Produktion",
	konversation: "Konversation",
	"jämförelse": "Jämförelse & Analys",
	// Domain zones
	"väder-och-klimat": "Väder & Klimat",
	"trafik-och-transport": "Trafik & Transport",
	"ekonomi-och-skatter": "Ekonomi & Skatter",
	arbetsmarknad: "Arbetsmarknad",
	"befolkning-och-demografi": "Befolkning & Demografi",
	utbildning: "Utbildning",
	"näringsliv-och-bolag": "Näringsliv & Bolag",
	"fastighet-och-mark": "Fastighet & Mark",
	"energi-och-miljö": "Energi & Miljö",
	"handel-och-marknad": "Handel & Marknad",
	"politik-och-beslut": "Politik & Beslut",
	"hälsa-och-vård": "Hälsa & Vård",
	"rättsväsende": "Rättsväsende",
};

const ZONE_DESCRIPTIONS: Record<string, string> = {
	kunskap: "Dokumentsökning, kunskapsbas, webbsökning",
	skapande: "Sandbox, podcast, bildgenerering, kartor, kod",
	konversation: "Småprat, hälsningar",
	"jämförelse": "Multi-modell jämförelser",
	"väder-och-klimat": "SMHI prognoser, temperatur, nederbörd, vind",
	"trafik-och-transport": "Trafikverket realtid, störningar, resplanering",
	"ekonomi-och-skatter": "SCB statistik, Kolada kommundata",
	arbetsmarknad: "Arbetsförmedlingen, jobb, lönestatistik",
	"befolkning-och-demografi": "SCB befolkningsdata, kommuner",
	utbildning: "Skolverket, läroplaner, betyg",
	"näringsliv-och-bolag": "Bolagsverket, företagsregister",
	"fastighet-och-mark": "Lantmäteriet, bostadsmarknad",
	"energi-och-miljö": "Elpriser, miljödata, klimatmål",
	"handel-och-marknad": "Blocket, Tradera, marknadsplatser",
	"politik-och-beslut": "Riksdagen, propositioner, voteringar",
	"hälsa-och-vård": "Socialstyrelsen, sjukvård",
	"rättsväsende": "Domstolar, BRÅ, brottsstatistik",
};

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
	const [loading, setLoading] = useState(true);

	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		nexusApiService
			.getZones()
			.then(setZones)
			.catch((err) => setError(err.message || "Kunde inte hämta zondata"))
			.finally(() => setLoading(false));
	}, []);

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
									{ZONE_LABELS[zone.zone] || zone.zone}
								</h4>
								<Badge variant="outline" className="text-xs font-mono">
									{zone.prefix_token.trim()}
								</Badge>
							</div>
							<p className="text-xs text-muted-foreground">
								{ZONE_DESCRIPTIONS[zone.zone] || ""}
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
