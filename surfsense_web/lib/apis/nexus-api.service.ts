/**
 * NEXUS API Service — client for all /api/v1/nexus/ endpoints.
 *
 * Sprint 1: health, zones, config, routing/analyze
 * Expanded in subsequent sprints.
 */

import { getBearerToken } from "../auth-utils";

const getBackendUrl = (): string => {
	return process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "http://localhost:8000";
};

async function fetchNexus<T>(
	path: string,
	options: RequestInit = {},
): Promise<T> {
	const url = `${getBackendUrl()}/api/v1/nexus${path}`;
	const token = getBearerToken();

	const res = await fetch(url, {
		...options,
		headers: {
			"Content-Type": "application/json",
			...(token ? { Authorization: `Bearer ${token}` } : {}),
			...options.headers,
		},
	});

	if (!res.ok) {
		const text = await res.text().catch(() => "Unknown error");
		throw new Error(`NEXUS API error ${res.status}: ${text}`);
	}

	return res.json();
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface NexusHealthResponse {
	status: string;
	version: string;
	zones_configured: number;
	total_routing_events: number;
	total_synthetic_cases: number;
}

export interface ZoneConfigResponse {
	zone: string;
	prefix_token: string;
	silhouette_score: number | null;
	inter_zone_min_distance: number | null;
	ood_energy_threshold: number;
	band0_rate: number | null;
	ece_score: number | null;
	last_reindexed: string | null;
}

export interface NexusConfigResponse {
	zones: ZoneConfigResponse[];
	band_thresholds: Record<string, number>;
	ood_energy_threshold: number;
	multi_intent_margin: number;
}

export interface QueryEntities {
	locations: string[];
	times: string[];
	organizations: string[];
	topics: string[];
}

export interface QueryAnalysis {
	original_query: string;
	normalized_query: string;
	sub_queries: string[];
	entities: QueryEntities;
	domain_hints: string[];
	zone_candidates: string[];
	complexity: string;
	is_multi_intent: boolean;
	ood_risk: number;
}

export interface RoutingCandidate {
	tool_id: string;
	zone: string;
	raw_score: number;
	calibrated_score: number;
	rank: number;
}

export interface RoutingDecision {
	query_analysis: QueryAnalysis;
	band: number;
	band_name: string;
	candidates: RoutingCandidate[];
	selected_tool: string | null;
	resolved_zone: string | null;
	calibrated_confidence: number;
	is_ood: boolean;
	schema_verified: boolean;
	latency_ms: number;
}

// ---------------------------------------------------------------------------
// Space Auditor Types (Sprint 2)
// ---------------------------------------------------------------------------

export interface ConfusionPair {
	tool_a: string;
	tool_b: string;
	similarity: number;
	zone_a: string | null;
	zone_b: string | null;
}

export interface HubnessReport {
	tool_id: string;
	hubness_score: number;
	times_as_nearest_neighbor: number;
}

export interface SpaceHealthReport {
	global_silhouette: number | null;
	zone_metrics: ZoneConfigResponse[];
	top_confusion_pairs: ConfusionPair[];
	hubness_alerts: HubnessReport[];
	total_tools: number;
}

export interface SpaceSnapshotPoint {
	tool_id: string;
	x: number;
	y: number;
	zone: string;
	cluster: number;
}

export interface SpaceSnapshot {
	snapshot_at: string;
	points: SpaceSnapshotPoint[];
}

// ---------------------------------------------------------------------------
// API Methods
// ---------------------------------------------------------------------------

class NexusApiService {
	// Health & Config
	getHealth = () => fetchNexus<NexusHealthResponse>("/health");

	getZones = () => fetchNexus<ZoneConfigResponse[]>("/zones");

	getConfig = () => fetchNexus<NexusConfigResponse>("/config");

	// Routing
	analyzeQuery = (query: string) =>
		fetchNexus<QueryAnalysis>("/routing/analyze", {
			method: "POST",
			body: JSON.stringify({ query }),
		});

	routeQuery = (query: string) =>
		fetchNexus<RoutingDecision>("/routing/route", {
			method: "POST",
			body: JSON.stringify({ query }),
		});

	// Space Auditor (Sprint 2)
	getSpaceHealth = () => fetchNexus<SpaceHealthReport>("/space/health");

	getSpaceSnapshot = () => fetchNexus<SpaceSnapshot>("/space/snapshot");

	getConfusion = () => fetchNexus<ConfusionPair[]>("/space/confusion");

	getHubness = () => fetchNexus<HubnessReport[]>("/space/hubness");

	getZoneMetrics = (zone: string) =>
		fetchNexus<ZoneConfigResponse>(`/zones/${zone}/metrics`);
}

export const nexusApiService = new NexusApiService();
