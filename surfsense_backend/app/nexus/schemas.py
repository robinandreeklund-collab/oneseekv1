"""NEXUS Pydantic schemas — request/response types for all endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class NexusHealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    zones_configured: int = 0
    total_routing_events: int = 0
    total_synthetic_cases: int = 0
    embedding_model: dict | None = None
    reranker: dict | None = None


# ---------------------------------------------------------------------------
# QUL — Query Understanding Layer
# ---------------------------------------------------------------------------


class QueryEntities(BaseModel):
    locations: list[str] = Field(default_factory=list)
    times: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class QueryAnalysis(BaseModel):
    original_query: str
    normalized_query: str
    sub_queries: list[str]
    entities: QueryEntities
    domain_hints: list[str] = Field(default_factory=list)
    zone_candidates: list[str] = Field(default_factory=list)
    complexity: str = "simple"  # "trivial" | "simple" | "compound" | "complex"
    is_multi_intent: bool = False
    ood_risk: float = 0.0


class AnalyzeQueryRequest(BaseModel):
    query: str
    include_entities: bool = True
    include_zone_hints: bool = True


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class RoutingCandidate(BaseModel):
    tool_id: str
    zone: str
    raw_score: float
    calibrated_score: float
    rank: int


class AgentCandidateResponse(BaseModel):
    name: str
    zone: str
    score: float
    matched_keywords: list[str] = Field(default_factory=list)


class AgentResolution(BaseModel):
    selected_agents: list[str] = Field(default_factory=list)
    candidates: list[AgentCandidateResponse] = Field(default_factory=list)
    tool_namespaces: list[str] = Field(default_factory=list)


class RoutingDecision(BaseModel):
    query_analysis: QueryAnalysis
    agent_resolution: AgentResolution | None = None
    band: int  # 0-4
    band_name: str
    candidates: list[RoutingCandidate] = Field(default_factory=list)
    selected_tool: str | None = None
    selected_agent: str | None = None
    resolved_zone: str | None = None
    calibrated_confidence: float = 0.0
    is_ood: bool = False
    schema_verified: bool = False
    latency_ms: float = 0.0


class RouteQueryRequest(BaseModel):
    query: str


# ---------------------------------------------------------------------------
# Zone Config
# ---------------------------------------------------------------------------


class ZoneConfigResponse(BaseModel):
    zone: str
    prefix_token: str
    silhouette_score: float | None = None
    inter_zone_min_distance: float | None = None
    ood_energy_threshold: float = -5.0
    band0_rate: float | None = None
    ece_score: float | None = None
    last_reindexed: datetime | None = None


class NexusConfigResponse(BaseModel):
    zones: list[ZoneConfigResponse] = Field(default_factory=list)
    band_thresholds: dict[str, float] = Field(default_factory=dict)
    ood_energy_threshold: float = -5.0
    multi_intent_margin: float = 0.15


# ---------------------------------------------------------------------------
# Confidence Bands
# ---------------------------------------------------------------------------


class BandClassification(BaseModel):
    band: int
    band_name: str
    top_score: float
    margin: float
    action: str  # "direct" | "verify" | "top3_llm" | "decompose" | "ood"


# ---------------------------------------------------------------------------
# OOD Detection
# ---------------------------------------------------------------------------


class OODResult(BaseModel):
    is_ood: bool
    method: str | None = None  # "energy" | "knn" | None
    energy_score: float = 0.0
    knn_distance: float | None = None
    nearest_zone: str | None = None


# ---------------------------------------------------------------------------
# Space Auditor
# ---------------------------------------------------------------------------


class ConfusionPair(BaseModel):
    tool_a: str
    tool_b: str
    similarity: float
    zone_a: str | None = None
    zone_b: str | None = None


class HubnessReport(BaseModel):
    tool_id: str
    hubness_score: float
    times_as_nearest_neighbor: int


class SpaceHealthReport(BaseModel):
    global_silhouette: float | None = None
    cluster_purity: float | None = None
    confusion_risk: float | None = None
    zone_metrics: list[ZoneConfigResponse] = Field(default_factory=list)
    top_confusion_pairs: list[ConfusionPair] = Field(default_factory=list)
    hubness_alerts: list[HubnessReport] = Field(default_factory=list)
    total_tools: int = 0


class SpaceSnapshot(BaseModel):
    snapshot_at: datetime
    points: list[dict] = Field(default_factory=list)  # {tool_id, x, y, zone, cluster}


# ---------------------------------------------------------------------------
# Synth Forge
# ---------------------------------------------------------------------------


class ForgeGenerateRequest(BaseModel):
    tool_ids: list[str] | None = None  # None = all tools
    category: str | None = None  # e.g. "smhi", "scb", "riksdagen", "marketplace"
    namespace: str | None = None  # e.g. "tools/weather" — filters by namespace prefix
    zone: str | None = None  # e.g. "kunskap" — filters by intent zone
    difficulties: list[str] | None = None  # None = all 4
    questions_per_difficulty: int = 4


class SyntheticCaseResponse(BaseModel):
    id: UUID
    tool_id: str
    namespace: str
    question: str
    difficulty: str
    expected_tool: str | None = None
    roundtrip_verified: bool = False
    quality_score: float | None = None
    created_at: datetime


class ForgeRunResult(BaseModel):
    run_id: UUID
    total_generated: int = 0
    total_verified: int = 0
    by_difficulty: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Auto Loop
# ---------------------------------------------------------------------------


class AutoLoopRunResponse(BaseModel):
    id: UUID
    loop_number: int
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_tests: int | None = None
    failures: int | None = None
    approved_proposals: int | None = None
    embedding_delta: float | None = None
    total_cases_available: int | None = None
    iterations_completed: int | None = None


class AutoLoopRunDetail(AutoLoopRunResponse):
    metadata_proposals: list[dict] | None = None


# ---------------------------------------------------------------------------
# Eval Ledger
# ---------------------------------------------------------------------------


class StageMetrics(BaseModel):
    stage: int
    stage_name: str
    namespace: str | None = None
    precision_at_1: float | None = None
    precision_at_5: float | None = None
    mrr_at_10: float | None = None
    ndcg_at_5: float | None = None
    hard_negative_precision: float | None = None
    reranker_delta: float | None = None
    recorded_at: datetime | None = None


class PipelineMetricsSummary(BaseModel):
    stages: list[StageMetrics] = Field(default_factory=list)
    overall_e2e: StageMetrics | None = None


class MetricsTrend(BaseModel):
    period_days: int = 30
    data_points: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Deploy Control
# ---------------------------------------------------------------------------


class GateResult(BaseModel):
    gate_number: int
    gate_name: str
    passed: bool
    score: float | None = None
    threshold: float | None = None
    details: str = ""


class GateStatus(BaseModel):
    tool_id: str
    gates: list[GateResult] = Field(default_factory=list)
    all_passed: bool = False
    recommendation: str = ""  # "promote" | "fix_required" | "review"


class PromotionResult(BaseModel):
    tool_id: str
    success: bool
    message: str = ""


class RollbackResult(BaseModel):
    tool_id: str
    success: bool
    message: str = ""


# ---------------------------------------------------------------------------
# Dark Matter
# ---------------------------------------------------------------------------


class DarkMatterCluster(BaseModel):
    cluster_id: int
    query_count: int
    sample_queries: list[str] = Field(default_factory=list)
    suggested_tool: str | None = None
    reviewed: bool = False


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


class CalibrationParamsResponse(BaseModel):
    id: UUID
    zone: str
    calibration_method: str
    param_a: float | None = None
    param_b: float | None = None
    temperature: float | None = None
    ece_score: float | None = None
    fitted_on_samples: int | None = None
    fitted_at: datetime
    is_active: bool = True


class ECEReport(BaseModel):
    global_ece: float | None = None
    per_zone: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Routing Events
# ---------------------------------------------------------------------------


class RoutingEventResponse(BaseModel):
    id: UUID
    query_text: str | None = None
    band: int
    resolved_zone: str | None = None
    selected_agent: str | None = None
    selected_tool: str | None = None
    calibrated_confidence: float | None = None
    is_multi_intent: bool | None = None
    is_ood: bool = False
    routed_at: datetime


# ---------------------------------------------------------------------------
# Metadata Optimizer
# ---------------------------------------------------------------------------


class OptimizerGenerateRequest(BaseModel):
    category: str | None = None
    namespace: str | None = None
    llm_config_id: int = -24  # Claude Sonnet default


class ToolSuggestionResponse(BaseModel):
    tool_id: str
    current: dict = Field(default_factory=dict)
    suggested: dict = Field(default_factory=dict)
    reasoning: str = ""
    fields_changed: list[str] = Field(default_factory=list)


class OptimizerResultResponse(BaseModel):
    category: str
    total_tools: int = 0
    suggestions: list[ToolSuggestionResponse] = Field(default_factory=list)
    model_used: str = ""
    error: str | None = None


class OptimizerApplyRequest(BaseModel):
    suggestions: list[dict] = Field(
        ..., description="List of tool metadata dicts with tool_id + fields to apply"
    )
