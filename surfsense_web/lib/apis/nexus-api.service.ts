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

export interface AgentCandidateResponse {
	name: string;
	zone: string;
	score: number;
	matched_keywords: string[];
}

export interface AgentResolution {
	selected_agents: string[];
	candidates: AgentCandidateResponse[];
	tool_namespaces: string[];
}

export interface LlmJudgeToolResult {
	chosen_tool: string | null;
	reasoning: string;
	nexus_rank_of_chosen: number;
	agreement: boolean;
}

export interface LlmGateStepResult {
	chosen: string;
	reasoning: string;
	candidates_shown: number;
}

export interface LlmGateResult {
	intent_step: LlmGateStepResult | null;
	agent_step: LlmGateStepResult | null;
	tool_step: LlmGateStepResult | null;
}

export interface RoutingDecision {
	query_analysis: QueryAnalysis;
	agent_resolution: AgentResolution | null;
	band: number;
	band_name: string;
	candidates: RoutingCandidate[];
	selected_tool: string | null;
	selected_agent: string | null;
	resolved_zone: string | null;
	calibrated_confidence: number;
	is_ood: boolean;
	schema_verified: boolean;
	latency_ms: number;
	llm_judge: LlmJudgeToolResult | null;
	llm_gate: LlmGateResult | null;
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
	cluster_purity: number | null;
	confusion_risk: number | null;
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
	namespace?: string;
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
	total_cases_available?: number | null;
	iterations_completed?: number | null;
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
	selected_agent: string | null;
	selected_tool: string | null;
	calibrated_confidence: number | null;
	is_multi_intent: boolean | null;
	is_ood: boolean;
	routed_at: string;
}

// ---------------------------------------------------------------------------
// Overview Metrics Types
// ---------------------------------------------------------------------------

export interface OverviewMetricsResponse {
	band0_rate: number | null;
	ece_global: number | null;
	ood_rate: number | null;
	namespace_purity: number | null;
	platt_calibrated: boolean;
	total_events: number;
	total_tools: number;
	total_hard_negatives: number;
	multi_intent_rate: number | null;
	schema_match_rate: number | null;
	reranker_delta: number | null;
	silhouette_global: number | null;
	inter_zone_distance: number | null;
	hubness_rate: number | null;
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
// Metrics Trend Types
// ---------------------------------------------------------------------------

export interface MetricsTrendPoint {
	date: string | null;
	stage: string;
	precision_at_1: number | null;
	mrr_at_10: number | null;
}

export interface MetricsTrend {
	period_days: number;
	data_points: MetricsTrendPoint[];
}

// ---------------------------------------------------------------------------
// Loop Run Detail Types
// ---------------------------------------------------------------------------

export interface LoopIterationDetail {
	iteration: number;
	total_tests: number;
	failures: number;
	precision_at_1: number;
	precision_at_5: number;
	mrr: number;
	band_distribution: number[];
	platform_comparisons: number;
	platform_agreements: number;
	llm_judge_total?: number;
	llm_judge_agreements?: number;
	llm_judge_correct?: number;
	llm_judge_agreement_rate?: number | null;
	llm_judge_accuracy?: number | null;
	llm_judge_disagreements?: LlmJudgeDisagreement[];
	intent_accuracy?: number | null;
	agent_accuracy?: number | null;
}

export interface LlmJudgeDisagreement {
	query: string;
	nexus_tool: string;
	llm_tool: string;
	expected_tool: string;
	reasoning: string;
	nexus_rank_of_chosen: number;
	winner: "nexus" | "llm" | "neither" | "tie";
}

export interface LlmJudgeSummary {
	total: number;
	agreements: number;
	correct: number;
	agreement_rate: number;
	accuracy: number;
	nexus_accuracy: number;
	llm_accuracy: number;
	both_correct: number;
	nexus_only_correct: number;
	llm_only_correct: number;
	both_wrong: number;
	disagreements: LlmJudgeDisagreement[];
}

export interface LoopProposalFailedQuery {
	query: string;
	expected_tool: string;
	got_tool: string;
	resolved_zone: string;
	selected_agent: string;
	band: number;
	confidence: number;
	difficulty: string;
	llm_judge_tool?: string | null;
	llm_judge_reasoning?: string;
}

export interface LoopProposal {
	tool_id: string;
	field: string;
	reason: string;
	current_value: string;
	proposed_value: string;
	embedding_delta: number;
	failed_queries: LoopProposalFailedQuery[];
}

export interface LoopRunDetail {
	id: string;
	loop_number: number;
	status: string;
	started_at: string | null;
	completed_at: string | null;
	total_tests: number | null;
	failures: number | null;
	approved_proposals: number | null;
	embedding_delta: number | null;
	proposals: LoopProposal[];
	band_distribution: number[];
	platform_comparisons: number;
	platform_agreements: number;
	iterations?: LoopIterationDetail[];
	total_cases_available?: number;
	llm_judge?: LlmJudgeSummary | null;
}

// ---------------------------------------------------------------------------
// Live Routing Config Types
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Loop Stream Event Types
// ---------------------------------------------------------------------------

export interface LoopStreamEvent {
	type: "progress" | "batch" | "iteration" | "done" | "error";
	step?: string;
	detail?: string;
	message?: string;
	run_id?: string;
	loop_number?: number;
	iteration?: number;
	total_iterations?: number;
	batch?: number;
	total_batches?: number;
	cases_processed?: number;
	total_cases?: number;
	max_iterations?: number;
	batch_size?: number;
	failures?: number;
	total_tests?: number;
	precision_at_1?: number;
	mrr?: number;
	proposals_count?: number;
	proposals?: number;
	iterations_completed?: number;
	embedding_delta?: number;
	status?: string;
	llm_judge_total?: number;
	llm_judge_agreements?: number;
	llm_judge_correct?: number;
	llm_judge_agreement_rate?: number | null;
	llm_judge_accuracy?: number | null;
	llm_judge_disagreements?: LlmJudgeDisagreement[];
	intent_accuracy?: number | null;
	agent_accuracy?: number | null;
}

// ---------------------------------------------------------------------------
// Concurrency Settings Types
// ---------------------------------------------------------------------------

export interface ConcurrencySettingsResponse {
	max_concurrency: number;
	active_tasks: number;
	peak_active: number;
}

export interface ConcurrencyUpdateResponse {
	max_concurrency: number;
	previous: number;
}

export interface LiveRoutingConfigResponse {
	phases: Record<string, number>;
	current_config: {
		live_routing_enabled: boolean;
		live_routing_phase: string;
		name_match_weight: number;
		keyword_weight: number;
		description_token_weight: number;
		example_query_weight: number;
		namespace_boost: number;
		embedding_weight: number;
		semantic_embedding_weight: number;
		structural_embedding_weight: number;
		rerank_candidates: number;
		tool_auto_score_threshold: number;
		tool_auto_margin_threshold: number;
		agent_auto_score_threshold: number;
		agent_auto_margin_threshold: number;
		intent_candidate_top_k: number;
		agent_candidate_top_k: number;
		tool_candidate_top_k: number;
		[key: string]: unknown;
	};
}

// ---------------------------------------------------------------------------
// Shadow Observer Types
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Metadata Optimizer Types
// ---------------------------------------------------------------------------

export interface ToolSuggestionResponse {
	tool_id: string;
	current: Record<string, unknown>;
	suggested: Record<string, unknown>;
	reasoning: string;
	fields_changed: string[];
}

export interface OptimizerResultResponse {
	category: string;
	total_tools: number;
	suggestions: ToolSuggestionResponse[];
	model_used: string;
	error: string | null;
}

export interface OptimizerApplyResponse {
	applied: number;
	skipped: number;
}

export interface IntentLayerItemSuggestion {
	item_id: string;
	item_type: "domain" | "agent";
	current: Record<string, unknown>;
	suggested: Record<string, unknown>;
	reasoning: string;
	fields_changed: string[];
}

export interface IntentLayerResultResponse {
	total_domains: number;
	total_agents: number;
	suggestions: IntentLayerItemSuggestion[];
	model_used: string;
	error: string | null;
}

export interface IntentLayerApplyResponse {
	applied_domains: number;
	applied_agents: number;
	skipped: number;
}

export interface ShadowReportResponse {
	feedback_store: {
		total_patterns: number;
		sample_rows: Record<string, unknown>[];
	};
	live_routing: Record<string, unknown>;
}

export interface DomainMetadata {
	domain_id: string;
	label: string;
	description: string;
	keywords: string[];
	fallback_route: string;
	enabled: boolean;
	priority: number;
}

export interface CategoryMetadata {
	category_id: string;
	label: string;
	tool_count: number;
}

export interface AgentMetadataResponse {
	agent_id: string;
	label: string;
	description: string;
	domain_id: string;
	keywords: string[];
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

	routeQuery = (query: string, options?: { llm_judge?: boolean; llm_gate?: boolean }) =>
		fetchNexus<RoutingDecision>("/routing/route", {
			method: "POST",
			body: JSON.stringify({
				query,
				llm_judge: options?.llm_judge ?? false,
				llm_gate: options?.llm_gate ?? false,
			}),
		});

	// Space Auditor (Sprint 2)
	getSpaceHealth = () => fetchNexus<SpaceHealthReport>("/space/health");

	getSpaceSnapshot = () => fetchNexus<SpaceSnapshot>("/space/snapshot");

	refreshSpaceSnapshot = () =>
		fetchNexus<{ refreshed: number }>("/space/refresh", { method: "POST" });

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
	startLoop = (
		request?: {
			category?: string;
			tool_ids?: string[];
			namespace?: string;
			batch_size?: number;
			max_iterations?: number;
		},
	) =>
		fetchNexus<Record<string, string>>("/loop/start", {
			method: "POST",
			body: JSON.stringify(request || {}),
		});

	/**
	 * Start a loop run with SSE progress streaming.
	 * Returns a ReadableStream of parsed event objects.
	 */
	startLoopStream = async (
		request?: {
			category?: string;
			tool_ids?: string[];
			namespace?: string;
			batch_size?: number;
			max_iterations?: number;
		},
		onEvent?: (event: LoopStreamEvent) => void,
	): Promise<void> => {
		const url = `${getBackendUrl()}/api/v1/nexus/loop/start-stream`;
		const token = getBearerToken();

		const res = await fetch(url, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				...(token ? { Authorization: `Bearer ${token}` } : {}),
			},
			body: JSON.stringify(request || {}),
		});

		if (!res.ok) {
			const text = await res.text();
			throw new Error(`Loop stream failed: ${res.status} ${text}`);
		}

		const reader = res.body?.getReader();
		if (!reader) throw new Error("No response body");

		const decoder = new TextDecoder();
		let buffer = "";

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split("\n");
			buffer = lines.pop() || "";

			for (const line of lines) {
				const trimmed = line.trim();
				if (trimmed.startsWith("data: ")) {
					try {
						const parsed = JSON.parse(trimmed.slice(6)) as LoopStreamEvent;
						onEvent?.(parsed);
					} catch {
						// skip malformed lines
					}
				}
			}
		}
	};

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

	fitCalibration = (options?: { zone?: string; category?: string }) =>
		fetchNexus<Record<string, string>>("/calibration/fit", {
			method: "POST",
			body: JSON.stringify(options ?? {}),
		});

	getCalibrationECE = () =>
		fetchNexus<ECEReportResponse>("/calibration/ece");

	// Overview Metrics
	getOverviewMetrics = () =>
		fetchNexus<OverviewMetricsResponse>("/overview/metrics");

	// Forge: Delete case
	deleteForgeCase = (caseId: string) =>
		fetchNexus<{ status: string }>(`/forge/cases/${caseId}`, { method: "DELETE" });

	// Loop: Run detail
	getLoopRunDetail = (runId: string) =>
		fetchNexus<LoopRunDetail>(`/loop/runs/${runId}`);

	// Ledger: Trend
	getLedgerTrendTyped = (days = 30) =>
		fetchNexus<MetricsTrend>(`/ledger/trend?days=${days}`);

	// Concurrency Settings
	getConcurrencySettings = () =>
		fetchNexus<ConcurrencySettingsResponse>("/settings/concurrency");

	updateConcurrency = (maxConcurrency: number) =>
		fetchNexus<ConcurrencyUpdateResponse>("/settings/concurrency", {
			method: "PUT",
			body: JSON.stringify({ max_concurrency: maxConcurrency }),
		});

	// Live Routing Config
	getLiveRoutingConfig = () =>
		fetchNexus<LiveRoutingConfigResponse>("/tools/live-routing");

	// Reset all NEXUS dev data
	resetAll = () =>
		fetchNexus<{ status: string; deleted: Record<string, number> }>("/reset", {
			method: "POST",
		});

	// Shadow Observer
	getShadowReport = () =>
		fetchNexus<ShadowReportResponse>("/shadow/report");

	// Dark Matter: Review cluster
	reviewDarkMatter = (clusterId: number, newToolCandidate?: string) =>
		fetchNexus<{ status: string }>(`/dark-matter/${clusterId}/review`, {
			method: "POST",
			body: JSON.stringify({ new_tool_candidate: newToolCandidate }),
		});

	// Metadata Optimizer
	getOptimizerCategories = () =>
		fetchNexus<{ categories: string[] }>("/optimizer/categories");

	optimizerGenerate = (request: {
		category?: string;
		namespace?: string;
		llm_config_id?: number;
	}) =>
		fetchNexus<OptimizerResultResponse>("/optimizer/generate", {
			method: "POST",
			body: JSON.stringify(request),
		});

	optimizerApply = (suggestions: Record<string, unknown>[]) =>
		fetchNexus<OptimizerApplyResponse>("/optimizer/apply", {
			method: "POST",
			body: JSON.stringify({ suggestions }),
		});

	// Intent Layer Optimizer
	intentLayerGenerate = (request?: { llm_config_id?: number }) =>
		fetchNexus<IntentLayerResultResponse>("/optimizer/intent-layer/generate", {
			method: "POST",
			body: JSON.stringify(request || {}),
		});

	intentLayerApply = (suggestions: Record<string, unknown>[]) =>
		fetchNexus<IntentLayerApplyResponse>("/optimizer/intent-layer/apply", {
			method: "POST",
			body: JSON.stringify({ suggestions }),
		});

	// Dynamic domain/agent metadata
	getDomainMetadata = () =>
		fetchNexus<{ domains: DomainMetadata[] }>("/config/domains");

	getAgentMetadata = () =>
		fetchNexus<{ agents: AgentMetadataResponse[] }>("/config/agents");

	getCategoryMetadata = () =>
		fetchNexus<{ categories: CategoryMetadata[] }>("/config/categories");
}

export const nexusApiService = new NexusApiService();
