"use client";

import { AlertCircle, CheckCircle, Ghost, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { type DarkMatterCluster, nexusApiService } from "@/lib/apis/nexus-api.service";

export function DarkMatterPanel() {
	const [clusters, setClusters] = useState<DarkMatterCluster[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [reviewing, setReviewing] = useState<number | null>(null);

	useEffect(() => {
		nexusApiService
			.getDarkMatterClusters()
			.then(setClusters)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	}, []);

	const handleReview = async (clusterId: number) => {
		setReviewing(clusterId);
		try {
			await nexusApiService.reviewDarkMatter(clusterId);
			setClusters((prev) =>
				prev.map((c) => (c.cluster_id === clusterId ? { ...c, reviewed: true } : c))
			);
		} catch {
			// ignore
		} finally {
			setReviewing(null);
		}
	};

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground p-4">
				<Loader2 className="h-4 w-4 animate-spin" />
				Laddar dark matter-kluster...
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

	if (clusters.length === 0) {
		return (
			<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
				Inga OOD-kluster hittade. Systemet har inte detekterat tillräckligt med
				out-of-distribution-frågor ännu.
			</div>
		);
	}

	return (
		<div className="rounded-lg border bg-card">
			<div className="p-4 border-b">
				<h3 className="font-semibold flex items-center gap-2">
					<Ghost className="h-4 w-4" />
					Dark Matter — OOD-kluster
				</h3>
				<p className="text-sm text-muted-foreground">
					Frågor som inte matchar något verktyg, grupperade efter liknande mönster
				</p>
			</div>
			<div className="divide-y">
				{clusters.map((cluster) => (
					<div key={cluster.cluster_id} className="p-4">
						<div className="flex items-center justify-between mb-2">
							<span className="text-sm font-medium">Kluster #{cluster.cluster_id}</span>
							<div className="flex items-center gap-2">
								<span className="text-xs text-muted-foreground">{cluster.query_count} frågor</span>
								{cluster.suggested_tool && (
									<span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">
										Föreslaget: {cluster.suggested_tool}
									</span>
								)}
								{cluster.reviewed ? (
									<span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700 flex items-center gap-1">
										<CheckCircle className="h-3 w-3" />
										Granskad
									</span>
								) : (
									<Button
										size="sm"
										variant="outline"
										className="h-6 text-xs"
										disabled={reviewing === cluster.cluster_id}
										onClick={() => handleReview(cluster.cluster_id)}
									>
										{reviewing === cluster.cluster_id ? (
											<Loader2 className="h-3 w-3 animate-spin mr-1" />
										) : null}
										Markera granskad
									</Button>
								)}
							</div>
						</div>
						<div className="space-y-1">
							{cluster.sample_queries.map((q, i) => (
								<p
									key={`${cluster.cluster_id}-${i}`}
									className="text-xs text-muted-foreground font-mono pl-3 border-l-2 border-muted"
								>
									{q}
								</p>
							))}
						</div>
					</div>
				))}
			</div>
		</div>
	);
}
