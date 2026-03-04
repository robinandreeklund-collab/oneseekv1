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
// Synth Forge Types (Sprint 3)
// ---------------------------------------------------------------------------

export interface SyntheticCaseResponse {
	id: string;
	tool_id: string;
	namespace: string;
	question: string;
	difficulty: string;
	expected_tool: string | null;
	roundtrip_verified: boolean;
	quality_score: number | null;
	created_at: string;
}

export interface ForgeGenerateRequest {
	tool_ids?: string[];
	category?: string;
	namespace?: string;
	zone?: string;
	difficulties?: string[];
	questions_per_difficulty?: number;
}

export interface ForgeRunResult {
	run_id: string;
	total_generated: number;
	total_verified: number;
	by_difficulty: Record<string, number>;
}

export interface PlatformToolResponse {
	tool_id: string;
	name: string;
	description: string;
	category: string;
	namespace: string;
	zone: string;
	keywords: string[];
}

// ---------------------------------------------------------------------------
// Auto Loop Types (Sprint 3)
// ---------------------------------------------------------------------------

export interface AutoLoopRunResponse {
	id: string;
	loop_number: number;
	status: string;
	started_at: string | null;
	completed_at: string | null;
	total_tests: number | null;
	failures: number | null;
	approved_proposals: number | null;
	embedding_delta: number | null;
}

// ---------------------------------------------------------------------------
// Eval Ledger Types (Sprint 3)
// ---------------------------------------------------------------------------

export interface StageMetrics {
	stage: number;
	stage_name: string;
	namespace: string | null;
	precision_at_1: number | null;
	precision_at_5: number | null;
	mrr_at_10: number | null;
	ndcg_at_5: number | null;
	hard_negative_precision: number | null;
	reranker_delta: number | null;
	recorded_at: string | null;
}

export interface PipelineMetricsSummary {
	stages: StageMetrics[];
	overall_e2e: StageMetrics | null;
}

// ---------------------------------------------------------------------------
// Dark Matter Types (Sprint 3)
// ---------------------------------------------------------------------------

export interface DarkMatterCluster {
	cluster_id: number;
	query_count: number;
	sample_queries: string[];
	suggested_tool: string | null;
	reviewed: boolean;
}

// ---------------------------------------------------------------------------
// Routing Events Types (Sprint 3)
// ---------------------------------------------------------------------------

export interface RoutingEventResponse {
	id: string;
	query_text: string | null;
	band: number;
	resolved_zone: string | null;
	selected_tool: string | null;
	calibrated_confidence: number | null;
	is_multi_intent: boolean | null;
	is_ood: boolean;
	routed_at: string;
}

// ---------------------------------------------------------------------------
// Deploy Control Types (Sprint 4)
// ---------------------------------------------------------------------------

export interface GateResultResponse {
	gate_number: number;
	gate_name: string;
	passed: boolean;
	score: number | null;
	threshold: number | null;
	details: string;
}

export interface GateStatusResponse {
	tool_id: string;
	gates: GateResultResponse[];
	all_passed: boolean;
	recommendation: string;
}

export interface PromotionResultResponse {
	tool_id: string;
	success: boolean;
	message: string;
}

export interface RollbackResultResponse {
	tool_id: string;
	success: boolean;
	message: string;
}

// ---------------------------------------------------------------------------
// Calibration Types (Sprint 4)
// ---------------------------------------------------------------------------

export interface CalibrationParamsResponse {
	id: string;
	zone: string;
	calibration_method: string;
	param_a: number | null;
	param_b: number | null;
	temperature: number | null;
	ece_score: number | null;
	fitted_on_samples: number | null;
	fitted_at: string;
	is_active: boolean;
}

export interface ECEReportResponse {
	global_ece: number | null;
	per_zone: Record<string, number>;
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

	// Platform Tools
	getPlatformTools = (category?: string) =>
		fetchNexus<{ tools: PlatformToolResponse[]; categories: string[] }>(
			`/tools${category ? `?category=${category}` : ""}`,
		);

	// Synth Forge (Sprint 3)
	forgeGenerate = (request: ForgeGenerateRequest) =>
		fetchNexus<ForgeRunResult>("/forge/generate", {
			method: "POST",
			body: JSON.stringify(request),
		});

	getForgeCases = (toolId?: string) =>
		fetchNexus<SyntheticCaseResponse[]>(
			`/forge/cases${toolId ? `?tool_id=${toolId}` : ""}`,
		);

	// Auto Loop (Sprint 3)
	startLoop = (request?: { category?: string }) =>
		fetchNexus<Record<string, string>>("/loop/start", {
			method: "POST",
			body: JSON.stringify(request || {}),
		});

	getLoopRuns = () => fetchNexus<AutoLoopRunResponse[]>("/loop/runs");

	approveLoopRun = (runId: string) =>
		fetchNexus<Record<string, string>>(`/loop/runs/${runId}/approve`, {
			method: "POST",
			body: JSON.stringify({}),
		});

	// Eval Ledger (Sprint 3)
	getLedgerMetrics = () =>
		fetchNexus<PipelineMetricsSummary>("/ledger/metrics");

	getLedgerTrend = (days = 30) =>
		fetchNexus<Record<string, unknown>>(`/ledger/trend?days=${days}`);

	// Dark Matter (Sprint 3)
	getDarkMatterClusters = () =>
		fetchNexus<DarkMatterCluster[]>("/dark-matter/clusters");

	// Routing Events (Sprint 3)
	getRoutingEvents = (limit = 50) =>
		fetchNexus<RoutingEventResponse[]>(`/routing/events?limit=${limit}`);

	getBandDistribution = () =>
		fetchNexus<{ distribution: number[]; total: number; percentages: number[] }>(
			"/routing/band-distribution",
		);

	logFeedback = (eventId: string, feedback: { implicit?: string; explicit?: number }) =>
		fetchNexus<Record<string, string>>(`/routing/events/${eventId}/feedback`, {
			method: "POST",
			body: JSON.stringify(feedback),
		});

	// Deploy Control (Sprint 4)
	getDeployGates = (toolId: string) =>
		fetchNexus<GateStatusResponse>(`/deploy/gates/${toolId}`);

	promoteTool = (toolId: string) =>
		fetchNexus<PromotionResultResponse>(`/deploy/promote/${toolId}`, {
			method: "POST",
		});

	rollbackTool = (toolId: string) =>
		fetchNexus<RollbackResultResponse>(`/deploy/rollback/${toolId}`, {
			method: "POST",
		});

	// Calibration (Sprint 4)
	getCalibrationParams = () =>
		fetchNexus<CalibrationParamsResponse[]>("/calibration/params");

	fitCalibration = () =>
		fetchNexus<Record<string, string>>("/calibration/fit", { method: "POST" });

	getCalibrationECE = () =>
		fetchNexus<ECEReportResponse>("/calibration/ece");
}

export const nexusApiService = new NexusApiService();
