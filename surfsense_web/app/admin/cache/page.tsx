"use client";

import { Database, HardDrive, Loader2, Server, ShieldOff, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { adminCacheApiService } from "@/lib/apis/admin-cache-api.service";

export default function AdminCacheRoute() {
	const [cacheDisabled, setCacheDisabled] = useState(false);
	const [loading, setLoading] = useState(true);
	const [clearing, setClearing] = useState(false);
	const [lastClearResult, setLastClearResult] = useState<Record<string, unknown> | null>(null);

	const fetchState = useCallback(async () => {
		try {
			const state = await adminCacheApiService.getCacheState();
			setCacheDisabled(state.disabled);
		} catch {
			toast.error("Kunde inte hämta cache-status");
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		fetchState();
	}, [fetchState]);

	const handleToggle = async (disabled: boolean) => {
		try {
			const result = await adminCacheApiService.updateCacheState({ disabled });
			setCacheDisabled(result.disabled);
			toast.success(disabled ? "Cache avaktiverad" : "Cache aktiverad");
		} catch {
			toast.error("Kunde inte uppdatera cache-status");
		}
	};

	const handleClearAll = async () => {
		setClearing(true);
		setLastClearResult(null);
		try {
			const result = await adminCacheApiService.clearCaches();
			setLastClearResult(result.cleared);
			toast.success("Alla cacher har tömts");
		} catch {
			toast.error("Kunde inte tömma cacher");
		} finally {
			setClearing(false);
		}
	};

	if (loading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-6 w-6 animate-spin" />
			</div>
		);
	}

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold">Cache Management</h1>
				<p className="text-muted-foreground mt-2">
					Hantera och rensa applikationens alla cache-lager
				</p>
			</div>

			{/* Master toggle */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<ShieldOff className="h-5 w-5" />
						Cache-läge
					</CardTitle>
					<CardDescription>
						Slå av all cachning för testning och felsökning. När cache är avaktiverad görs alla
						anrop direkt utan att läsa eller skriva till cache.
					</CardDescription>
				</CardHeader>
				<CardContent className="flex items-center gap-4">
					<Switch id="cache-toggle" checked={cacheDisabled} onCheckedChange={handleToggle} />
					<Label htmlFor="cache-toggle" className="flex items-center gap-2">
						{cacheDisabled ? (
							<Badge variant="destructive">Cache avaktiverad</Badge>
						) : (
							<Badge variant="secondary">Cache aktiv</Badge>
						)}
					</Label>
				</CardContent>
			</Card>

			{/* Clear all */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Trash2 className="h-5 w-5" />
						Töm alla cacher
					</CardTitle>
					<CardDescription>
						Rensar alla cache-lager i hela systemet: in-memory agent combo, tool embeddings,
						rerank-trace, service TTL-cacher (SCB, Elpris, Riksbank, Trafikanalys), agent
						combo-rader i databasen, och Redis.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<Button
						variant="destructive"
						className="gap-2"
						onClick={handleClearAll}
						disabled={clearing}
					>
						{clearing ? (
							<Loader2 className="h-4 w-4 animate-spin" />
						) : (
							<Trash2 className="h-4 w-4" />
						)}
						Töm alla cacher nu
					</Button>

					{lastClearResult && (
						<div className="rounded-md border p-4 space-y-2">
							<p className="text-sm font-medium">Resultat:</p>
							<div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
								{Object.entries(lastClearResult).map(([key, value]) => (
									<div key={key} className="flex items-center gap-2 text-sm">
										{key.includes("redis") ? (
											<Server className="h-4 w-4 text-muted-foreground" />
										) : key.includes("db") ? (
											<Database className="h-4 w-4 text-muted-foreground" />
										) : (
											<HardDrive className="h-4 w-4 text-muted-foreground" />
										)}
										<span className="text-muted-foreground">{key}:</span>
										<Badge variant="outline">{String(value)}</Badge>
									</div>
								))}
							</div>
						</div>
					)}
				</CardContent>
			</Card>

			{/* Cache layers overview */}
			<Card>
				<CardHeader>
					<CardTitle>Cache-lager i systemet</CardTitle>
					<CardDescription>Alla cache-nivåer som påverkas av ovanstående åtgärder</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="space-y-3 text-sm">
						<div className="flex items-start gap-3">
							<HardDrive className="h-4 w-4 mt-0.5 text-muted-foreground" />
							<div>
								<p className="font-medium">Agent Combo Cache (in-memory)</p>
								<p className="text-muted-foreground">
									Cachade routing-beslut med 20 min TTL. Nycklar byggs från query-tokens, senaste
									agenter och sub-intents.
								</p>
							</div>
						</div>
						<div className="flex items-start gap-3">
							<HardDrive className="h-4 w-4 mt-0.5 text-muted-foreground" />
							<div>
								<p className="font-medium">Agent &amp; Tool Embeddings (in-memory)</p>
								<p className="text-muted-foreground">
									Embeddings för agent- och verktygsnamn. Används vid semantic similarity-matchning.
								</p>
							</div>
						</div>
						<div className="flex items-start gap-3">
							<HardDrive className="h-4 w-4 mt-0.5 text-muted-foreground" />
							<div>
								<p className="font-medium">Tool Rerank Trace (in-memory)</p>
								<p className="text-muted-foreground">Debug-spårning av verktygsrankning.</p>
							</div>
						</div>
						<div className="flex items-start gap-3">
							<HardDrive className="h-4 w-4 mt-0.5 text-muted-foreground" />
							<div>
								<p className="font-medium">Service TTL-cacher (in-memory)</p>
								<p className="text-muted-foreground">
									SCB (noder, metadata, kodlistor), Elpris (idag, historik), Riksbank (räntor,
									meta), Trafikanalys (data, meta).
								</p>
							</div>
						</div>
						<div className="flex items-start gap-3">
							<Database className="h-4 w-4 mt-0.5 text-muted-foreground" />
							<div>
								<p className="font-medium">Agent Combo Cache (databas)</p>
								<p className="text-muted-foreground">
									Persistenta routing-beslut i PostgreSQL. Raderas helt vid cache-tömning.
								</p>
							</div>
						</div>
						<div className="flex items-start gap-3">
							<Server className="h-4 w-4 mt-0.5 text-muted-foreground" />
							<div>
								<p className="font-medium">Redis (Trafikverket)</p>
								<p className="text-muted-foreground">
									API-svar från Trafikverket med 5 min TTL. Töms via flushdb.
								</p>
							</div>
						</div>
					</div>
				</CardContent>
			</Card>
		</div>
	);
}
