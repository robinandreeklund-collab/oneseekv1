"""NEXUS FastAPI routes — /api/v1/nexus/...

Sprint 5: All endpoints are fully integrated — no placeholders.
"""

from __future__ import annotations

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import User, get_async_session
from app.nexus.models import NexusAutoLoopRun, NexusDarkMatterQuery
from app.nexus.schemas import (
    AnalyzeQueryRequest,
    AutoLoopRunResponse,
    CalibrationParamsResponse,
    ConfusionPair,
    DarkMatterCluster,
    ECEReport,
    ForgeGenerateRequest,
    GateStatus,
    HubnessReport,
    MetricsTrend,
    NexusConfigResponse,
    NexusHealthResponse,
    PipelineMetricsSummary,
    PromotionResult,
    QueryAnalysis,
    RollbackResult,
    RouteQueryRequest,
    RoutingDecision,
    RoutingEventResponse,
    SpaceHealthReport,
    SpaceSnapshot,
    SyntheticCaseResponse,
    ZoneConfigResponse,
)
from app.nexus.service import NexusService
from app.users import current_active_user

nexus_router = APIRouter(prefix="/nexus", tags=["nexus"])

# Singleton service instance
_service = NexusService()


def _get_service() -> NexusService:
    return _service


# ------------------------------------------------------------------
# Health & Config
# ------------------------------------------------------------------


@nexus_router.get("/health", response_model=NexusHealthResponse)
async def get_nexus_health(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get NEXUS system health summary."""
    return await service.get_health(session)


@nexus_router.get("/zones", response_model=list[ZoneConfigResponse])
async def get_nexus_zones(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get all zone configurations."""
    return await service.get_zones(session)


@nexus_router.get("/config", response_model=NexusConfigResponse)
async def get_nexus_config(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get full NEXUS configuration."""
    return await service.get_config(session)


@nexus_router.get("/overview/metrics")
async def get_overview_metrics(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get overview metrics: Band-0 rate, ECE, OOD rate, namespace purity."""
    return await service.get_overview_metrics(session)


# ------------------------------------------------------------------
# Platform Tools Registry
# ------------------------------------------------------------------


@nexus_router.get("/tools")
async def get_platform_tools_list(
    category: str | None = Query(None),
    zone: str | None = Query(None),
    namespace: str | None = Query(None),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """List all real platform tools visible to NEXUS.

    Returns the full tool catalog auto-discovered from the live platform,
    enriched with lifecycle status (LIVE/REVIEW) from the DB.

    Filters:
    - `?category=smhi` — filter by domain category
    - `?zone=kunskap` — filter by intent zone
    - `?namespace=tools/weather` — filter by namespace prefix
    """
    from app.nexus.platform_bridge import (
        get_category_names,
        get_platform_tools,
        get_tool_lifecycle_statuses,
    )

    tools = get_platform_tools()
    if category:
        tools = [t for t in tools if t.category == category]
    if zone:
        tools = [t for t in tools if t.zone == zone]
    if namespace:
        tools = [t for t in tools if "/".join(t.namespace).startswith(namespace)]

    # Enrich with lifecycle status from DB
    lifecycle = await get_tool_lifecycle_statuses(session)

    return {
        "total": len(tools),
        "categories": get_category_names(),
        "tools": [
            {
                "tool_id": t.tool_id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "zone": t.zone,
                "namespace": "/".join(t.namespace),
                "keywords": t.keywords[:5],
                "geographic_scope": t.geographic_scope,
                "lifecycle_status": (
                    lifecycle.get(t.tool_id, {}).get("status", "unknown")
                    if lifecycle
                    else "unknown"
                ),
            }
            for t in tools
        ],
    }


@nexus_router.get("/tools/categories")
async def get_tool_categories(
    user: User = Depends(current_active_user),
):
    """List available tool categories with counts."""
    from app.nexus.platform_bridge import get_platform_tools_by_category

    by_cat = get_platform_tools_by_category()
    return {
        "categories": [
            {"name": cat, "count": len(tools)} for cat, tools in sorted(by_cat.items())
        ]
    }


@nexus_router.get("/tools/agents")
async def get_platform_agents(
    user: User = Depends(current_active_user),
):
    """List all platform agents and their zone mappings."""
    from app.nexus.platform_bridge import PLATFORM_AGENTS

    return {"agents": PLATFORM_AGENTS}


@nexus_router.get("/tools/intents")
async def get_platform_intents_endpoint(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get effective intent definitions (defaults + DB overrides).

    This is the REAL routing intent configuration that the supervisor uses.
    """
    from app.nexus.platform_bridge import get_effective_intents_from_db

    intents = await get_effective_intents_from_db(session)
    return {"intents": intents}


@nexus_router.get("/tools/live-routing")
async def get_live_routing_config(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get current live routing configuration.

    Shows the active phase (shadow/tool_gate/agent_auto/adaptive/intent_finetune),
    thresholds, and whether live routing is enabled.
    """
    from app.nexus.platform_bridge import LIVE_ROUTING_PHASES, get_retrieval_tuning

    tuning = await get_retrieval_tuning(session)
    return {
        "phases": LIVE_ROUTING_PHASES,
        "current_config": tuning,
    }


# ------------------------------------------------------------------
# Shadow Observer (Platform Integration)
# ------------------------------------------------------------------


@nexus_router.get("/shadow/report")
async def get_shadow_report(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get shadow observer report — how NEXUS compares to real platform routing.

    Shows retrieval feedback store state and live routing configuration.
    """
    return await service.get_shadow_report(session)


@nexus_router.get("/shadow/feedback/{tool_id}")
async def get_shadow_feedback_for_tool(
    tool_id: str,
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get retrieval feedback signals for a specific tool from the real pipeline."""
    return service.shadow_observer.get_feedback_for_tool(tool_id)


class ShadowCompareRequest(BaseModel):
    query: str


@nexus_router.post("/shadow/compare")
async def shadow_compare(
    request: ShadowCompareRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Route a query through NEXUS AND the real platform, return comparison.

    Shows whether NEXUS agrees with the production routing pipeline.
    """
    return await service.compare_single_query(request.query, session)


# ------------------------------------------------------------------
# Routing — Precision Stack
# ------------------------------------------------------------------


@nexus_router.post("/routing/analyze", response_model=QueryAnalysis)
async def analyze_query(
    request: AnalyzeQueryRequest,
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Run QUL analysis on a query (no DB, no LLM)."""
    return service.analyze_query(request.query)


@nexus_router.post("/routing/route", response_model=RoutingDecision)
async def route_query(
    request: RouteQueryRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Run the full precision routing pipeline."""
    return await service.route_query(request.query, session)


# ------------------------------------------------------------------
# Space Auditor (Sprint 2)
# ------------------------------------------------------------------


@nexus_router.get("/space/health", response_model=SpaceHealthReport)
async def get_space_health(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get space auditor health report."""
    return await service.get_space_health(session)


@nexus_router.get("/space/snapshot", response_model=SpaceSnapshot)
async def get_space_snapshot(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get latest UMAP 2D projection for visualization."""
    return await service.get_space_snapshot(session)


@nexus_router.get("/space/confusion", response_model=list[ConfusionPair])
async def get_confusion_pairs(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get top confusion pairs."""
    return await service.get_confusion_pairs(session)


@nexus_router.get("/space/hubness", response_model=list[HubnessReport])
async def get_hubness_alerts(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get hubness alerts."""
    return await service.get_hubness_alerts(session)


# ------------------------------------------------------------------
# Zone-specific Metrics (Sprint 2)
# ------------------------------------------------------------------


@nexus_router.get("/zones/{zone}/metrics", response_model=ZoneConfigResponse)
async def get_zone_metrics(
    zone: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get detailed metrics for a specific zone."""
    result = await service.get_zone_metrics(zone, session)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Zone '{zone}' not found")
    return result


# ------------------------------------------------------------------
# Synth Forge (Sprint 3)
# ------------------------------------------------------------------


@nexus_router.post("/forge/generate")
async def forge_generate(
    request: ForgeGenerateRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Generate synthetic test cases using the configured LLM.

    Pass `category` to generate for a specific tool domain:
    smhi, scb, kolada, riksdagen, trafikverket, bolagsverket,
    marketplace, skolverket, builtin, external_model, geoapify.
    """
    return await service.forge_generate(
        session,
        tool_ids=request.tool_ids,
        category=request.category,
        namespace=request.namespace,
        zone=request.zone,
        difficulties=request.difficulties,
        questions_per_difficulty=request.questions_per_difficulty or 4,
    )


@nexus_router.get("/forge/cases", response_model=list[SyntheticCaseResponse])
async def get_forge_cases(
    tool_id: str | None = Query(None, description="Filter by tool ID"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get synthetic test cases, optionally filtered by tool."""
    return await service.get_synthetic_cases(session, tool_id=tool_id, limit=limit)


@nexus_router.delete("/forge/cases/{case_id}")
async def delete_forge_case(
    case_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Delete a synthetic test case."""
    from app.nexus.models import NexusSyntheticCase

    try:
        uid = uuid_mod.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case_id format") from None

    result = await session.execute(
        select(NexusSyntheticCase).where(NexusSyntheticCase.id == uid)
    )
    case = result.scalars().first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    await session.delete(case)
    await session.commit()
    return {"status": "deleted", "case_id": case_id}


# ------------------------------------------------------------------
# Auto Loop (Sprint 3)
# ------------------------------------------------------------------


class LoopStartRequest(BaseModel):
    category: str | None = None


@nexus_router.post("/loop/start")
async def loop_start(
    request: LoopStartRequest | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Start an auto-improvement loop run.

    Runs synchronously: loads test cases, evaluates routing, clusters
    failures, creates proposals, and returns results.

    Pass `category` to run only on test cases for a specific domain (e.g. "smhi").
    """
    cat = request.category if request else None
    return await service.run_auto_loop(session, category=cat)


@nexus_router.get("/loop/runs", response_model=list[AutoLoopRunResponse])
async def get_loop_runs(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get auto-loop run history."""
    return await service.get_loop_runs(session, limit=limit)


@nexus_router.get("/loop/runs/{run_id}")
async def get_loop_run_detail(
    run_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get detailed info for a single auto-loop run.

    Returns proposals, band distribution, platform comparisons,
    and hard negative count from the run's metadata.
    """
    try:
        uid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format") from None

    result = await session.execute(
        select(NexusAutoLoopRun).where(NexusAutoLoopRun.id == uid)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    meta = run.metadata_proposals or {}
    return {
        "id": str(run.id),
        "loop_number": run.loop_number,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "total_tests": run.total_tests,
        "failures": run.failures,
        "approved_proposals": run.approved_proposals,
        "embedding_delta": run.embedding_delta,
        "proposals": meta.get("proposals", []),
        "band_distribution": meta.get("band_distribution", []),
        "platform_comparisons": meta.get("platform_comparisons", 0),
        "platform_agreements": meta.get("platform_agreements", 0),
    }


class ApproveProposalRequest(BaseModel):
    proposal_ids: list[int] | None = None


@nexus_router.post("/loop/runs/{run_id}/approve")
async def approve_loop_run(
    run_id: str,
    request: ApproveProposalRequest | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Approve proposals from an auto-loop run.

    Updates the run status to 'approved' and increments approved_proposals.
    """
    try:
        uid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format") from None

    result = await session.execute(
        select(NexusAutoLoopRun).where(NexusAutoLoopRun.id == uid)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if run.status not in ("review", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Run is in '{run.status}' state, cannot approve",
        )

    # Count proposals to approve
    proposals = run.metadata_proposals or {}
    proposal_list = proposals.get("proposals", [])
    approved_count = len(proposal_list)

    run.status = "approved"
    run.approved_proposals = approved_count
    await session.commit()

    return {
        "status": "approved",
        "run_id": run_id,
        "approved_proposals": approved_count,
    }


# ------------------------------------------------------------------
# Eval Ledger (Sprint 3)
# ------------------------------------------------------------------


@nexus_router.get("/ledger/metrics", response_model=PipelineMetricsSummary)
async def get_ledger_metrics(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get pipeline metrics across all 5 stages."""
    return await service.get_pipeline_metrics(session)


@nexus_router.get("/ledger/trend", response_model=MetricsTrend)
async def get_ledger_trend(
    days: int = Query(30, ge=1, le=90),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get metrics trend over time."""
    return await service.get_ledger_trend(session, days=days)


# ------------------------------------------------------------------
# Dark Matter (Sprint 3)
# ------------------------------------------------------------------


@nexus_router.get("/dark-matter/clusters", response_model=list[DarkMatterCluster])
async def get_dark_matter_clusters(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get OOD query clusters (dark matter)."""
    return await service.get_dark_matter_clusters(session)


class ReviewDarkMatterRequest(BaseModel):
    new_tool_candidate: str | None = None


@nexus_router.post("/dark-matter/{cluster_id}/review")
async def review_dark_matter(
    cluster_id: int,
    request: ReviewDarkMatterRequest | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Mark dark matter queries in a cluster as reviewed.

    Updates all unreviewed queries matching the cluster_id.
    """
    # Update all queries in this cluster
    result = await session.execute(
        update(NexusDarkMatterQuery)
        .where(
            NexusDarkMatterQuery.cluster_id == cluster_id,
            NexusDarkMatterQuery.reviewed.is_(False),
        )
        .values(
            reviewed=True,
            new_tool_candidate=(request.new_tool_candidate if request else None),
        )
        .returning(NexusDarkMatterQuery.id)
    )
    updated_ids = result.scalars().all()
    await session.commit()

    return {
        "status": "reviewed",
        "cluster_id": cluster_id,
        "updated_count": len(updated_ids),
        "new_tool_candidate": request.new_tool_candidate if request else None,
    }


# ------------------------------------------------------------------
# Routing Events & Feedback (Sprint 3)
# ------------------------------------------------------------------


@nexus_router.get("/routing/events", response_model=list[RoutingEventResponse])
async def get_routing_events(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get recent routing events."""
    return await service.get_routing_events(session, limit=limit)


@nexus_router.get("/routing/band-distribution")
async def get_band_distribution(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get band distribution from routing events."""
    return await service.get_band_distribution(session)


class FeedbackRequest(BaseModel):
    implicit: str | None = None  # "reformulation" | "follow_up"
    explicit: int | None = None  # -1, 0, 1


@nexus_router.post("/routing/events/{event_id}/feedback")
async def log_routing_feedback(
    event_id: str,
    request: FeedbackRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Log feedback for a routing event."""
    success = await service.log_feedback(
        session,
        event_id,
        implicit=request.implicit,
        explicit=request.explicit,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return {"status": "ok", "event_id": event_id}


# ------------------------------------------------------------------
# Deploy Control (Sprint 4)
# ------------------------------------------------------------------


@nexus_router.get("/deploy/gates/{tool_id}", response_model=GateStatus)
async def get_deploy_gates(
    tool_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get deployment gate status for a tool."""
    return await service.get_gate_status(tool_id, session)


@nexus_router.post("/deploy/promote/{tool_id}", response_model=PromotionResult)
async def promote_tool(
    tool_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Promote a tool to the next lifecycle stage."""
    return await service.promote_tool(tool_id, session)


@nexus_router.post("/deploy/rollback/{tool_id}", response_model=RollbackResult)
async def rollback_tool(
    tool_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Rollback a tool to previous stage."""
    return await service.rollback_tool(tool_id, session)


# ------------------------------------------------------------------
# Calibration (Sprint 4)
# ------------------------------------------------------------------


@nexus_router.get("/calibration/params", response_model=list[CalibrationParamsResponse])
async def get_calibration_params(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get all calibration parameters."""
    return await service.get_calibration_params(session)


@nexus_router.post("/calibration/fit")
async def fit_calibration(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Trigger calibration fitting using routing event data."""
    return await service.fit_calibration(session)


@nexus_router.get("/calibration/ece", response_model=ECEReport)
async def get_calibration_ece(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get ECE report across all zones."""
    return await service.get_ece_report(session)


# ------------------------------------------------------------------
# Seed Data
# ------------------------------------------------------------------


@nexus_router.post("/seed")
async def seed_data(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Populate NEXUS with infrastructure seed data.

    Inserts zone configs, routing events, space snapshots,
    loop runs, pipeline metrics, dark matter queries, and calibration params.
    Synthetic test cases are generated separately via /forge/generate.
    """
    from app.nexus.seed import seed_nexus_data

    return await seed_nexus_data(session)
