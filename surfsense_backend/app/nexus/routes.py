"""NEXUS FastAPI routes — /api/v1/nexus/..."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import User, get_async_session
from app.nexus.schemas import (
    AnalyzeQueryRequest,
    ConfusionPair,
    HubnessReport,
    NexusConfigResponse,
    NexusHealthResponse,
    QueryAnalysis,
    RouteQueryRequest,
    RoutingDecision,
    SpaceHealthReport,
    SpaceSnapshot,
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


# ------------------------------------------------------------------
# Routing — Precision Stack
# ------------------------------------------------------------------


@nexus_router.post("/routing/analyze", response_model=QueryAnalysis)
async def analyze_query(
    request: AnalyzeQueryRequest,
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Run QUL analysis on a query (no DB, no LLM).

    Returns entity extraction, multi-intent detection, zone candidates,
    and complexity classification.
    """
    return service.analyze_query(request.query)


@nexus_router.post("/routing/route", response_model=RoutingDecision)
async def route_query(
    request: RouteQueryRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Run the full precision routing pipeline.

    Sprint 2: QUL → StR → OOD → Calibrate → Bands → Schema verify.
    """
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
    """Get space auditor health report — silhouette, confusion, hubness."""
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
    """Get top confusion pairs — tools that are dangerously similar."""
    return await service.get_confusion_pairs(session)


@nexus_router.get("/space/hubness", response_model=list[HubnessReport])
async def get_hubness_alerts(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    service: NexusService = Depends(_get_service),
):
    """Get hubness alerts — tools that dominate nearest-neighbor results."""
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
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Zone '{zone}' not found")
    return result
