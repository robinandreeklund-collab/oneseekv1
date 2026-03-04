"""NEXUS Service — orchestrates all routing components.

Central coordination layer that connects QUL → OOD → Bands → Zone
into a single routing pipeline.
"""

from __future__ import annotations

import hashlib
import logging
import time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.nexus.calibration.platt_scaler import PlattCalibratedReranker, PlattParams
from app.nexus.models import (
    NexusCalibrationParam,
    NexusRoutingEvent,
    NexusZoneConfig,
)
from app.nexus.routing.confidence_bands import ConfidenceBandCascade
from app.nexus.routing.ood_detector import DarkMatterDetector
from app.nexus.routing.qul import QueryUnderstandingLayer
from app.nexus.routing.zone_manager import ZoneManager
from app.nexus.schemas import (
    NexusConfigResponse,
    NexusHealthResponse,
    OODResult,
    QueryAnalysis,
    QueryEntities,
    RoutingDecision,
    ZoneConfigResponse,
)

logger = logging.getLogger(__name__)


class NexusService:
    """Orchestrates the full NEXUS precision routing pipeline."""

    def __init__(self):
        self.qul = QueryUnderstandingLayer()
        self.ood_detector = DarkMatterDetector()
        self.band_cascade = ConfidenceBandCascade()
        self.zone_manager = ZoneManager()
        self.platt_scaler = PlattCalibratedReranker()

    # ------------------------------------------------------------------
    # Health & Config
    # ------------------------------------------------------------------

    async def get_health(self, session: AsyncSession) -> NexusHealthResponse:
        """Return system health summary."""
        zones_count = await session.scalar(
            select(func.count()).select_from(NexusZoneConfig)
        ) or 0
        events_count = await session.scalar(
            select(func.count()).select_from(NexusRoutingEvent)
        ) or 0

        return NexusHealthResponse(
            status="ok",
            version="1.0.0",
            zones_configured=zones_count,
            total_routing_events=events_count,
        )

    async def get_zones(self, session: AsyncSession) -> list[ZoneConfigResponse]:
        """Return all zone configurations from DB."""
        result = await session.execute(select(NexusZoneConfig))
        rows = result.scalars().all()

        if not rows:
            # Return default zone config if DB is empty
            return [
                ZoneConfigResponse(
                    zone=z["zone"],
                    prefix_token=z["prefix_token"],
                )
                for z in self.zone_manager.get_zone_config_data()
            ]

        return [
            ZoneConfigResponse(
                zone=row.zone,
                prefix_token=row.prefix_token,
                silhouette_score=row.silhouette_score,
                inter_zone_min_distance=row.inter_zone_min_distance,
                ood_energy_threshold=row.ood_energy_threshold,
                band0_rate=row.band0_rate,
                ece_score=row.ece_score,
                last_reindexed=row.last_reindexed,
            )
            for row in rows
        ]

    async def get_config(self, session: AsyncSession) -> NexusConfigResponse:
        """Return full NEXUS configuration."""
        zones = await self.get_zones(session)
        from app.nexus.config import (
            BAND_THRESHOLDS,
            MULTI_INTENT_MARGIN_THRESHOLD,
            OOD_ENERGY_THRESHOLD,
        )

        return NexusConfigResponse(
            zones=zones,
            band_thresholds={
                "band_0_min_score": BAND_THRESHOLDS.band_0_min_score,
                "band_0_min_margin": BAND_THRESHOLDS.band_0_min_margin,
                "band_1_min_score": BAND_THRESHOLDS.band_1_min_score,
                "band_1_min_margin": BAND_THRESHOLDS.band_1_min_margin,
                "band_2_min_score": BAND_THRESHOLDS.band_2_min_score,
                "band_3_min_score": BAND_THRESHOLDS.band_3_min_score,
            },
            ood_energy_threshold=OOD_ENERGY_THRESHOLD,
            multi_intent_margin=MULTI_INTENT_MARGIN_THRESHOLD,
        )

    # ------------------------------------------------------------------
    # Query Analysis (QUL only)
    # ------------------------------------------------------------------

    def analyze_query(self, query: str) -> QueryAnalysis:
        """Run QUL analysis on a query (no DB, no LLM)."""
        result = self.qul.analyze(query)

        return QueryAnalysis(
            original_query=result.original_query,
            normalized_query=result.normalized_query,
            sub_queries=result.sub_queries,
            entities=QueryEntities(
                locations=result.entities.locations,
                times=result.entities.times,
                organizations=result.entities.organizations,
                topics=result.entities.topics,
            ),
            domain_hints=result.domain_hints,
            zone_candidates=result.zone_candidates,
            complexity=result.complexity,
            is_multi_intent=result.is_multi_intent,
        )

    # ------------------------------------------------------------------
    # Full Routing Pipeline
    # ------------------------------------------------------------------

    async def route_query(
        self, query: str, session: AsyncSession
    ) -> RoutingDecision:
        """Run the full precision routing pipeline.

        Pipeline: QUL → OOD check → Band classification → Zone resolution

        Note: In Sprint 1, this runs without actual tool retrieval.
        Sprint 2 adds Select-Then-Route with real embeddings.
        """
        start_time = time.monotonic()

        # Step 1: QUL
        analysis = self.analyze_query(query)

        # Step 2: OOD check (placeholder logits until StR is implemented)
        # In Sprint 2, this will use actual retrieval scores
        ood_result = OODResult(is_ood=False, energy_score=0.0)

        # Step 3: Band classification (placeholder scores)
        # In Sprint 2, this will use calibrated reranker scores
        band_result = self.band_cascade.classify(top_score=0.0, second_score=0.0)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        decision = RoutingDecision(
            query_analysis=analysis,
            band=band_result.band,
            band_name=band_result.band_name,
            candidates=[],
            selected_tool=None,
            resolved_zone=(
                analysis.zone_candidates[0] if analysis.zone_candidates else None
            ),
            calibrated_confidence=band_result.top_score,
            is_ood=ood_result.is_ood,
            schema_verified=False,
            latency_ms=elapsed_ms,
        )

        # Log routing event
        await self._log_routing_event(session, query, decision)

        return decision

    # ------------------------------------------------------------------
    # Calibration Loading
    # ------------------------------------------------------------------

    async def load_calibration(self, session: AsyncSession) -> None:
        """Load active calibration parameters from DB."""
        result = await session.execute(
            select(NexusCalibrationParam).where(
                NexusCalibrationParam.is_active.is_(True),
                NexusCalibrationParam.calibration_method == "platt",
            )
        )
        row = result.scalars().first()
        if row and row.param_a is not None and row.param_b is not None:
            self.platt_scaler = PlattCalibratedReranker(
                PlattParams(
                    a=row.param_a,
                    b=row.param_b,
                    fitted=True,
                    n_samples=row.fitted_on_samples or 0,
                )
            )
            logger.info("Loaded Platt calibration: A=%.4f, B=%.4f", row.param_a, row.param_b)

    # ------------------------------------------------------------------
    # Event Logging
    # ------------------------------------------------------------------

    async def _log_routing_event(
        self, session: AsyncSession, query: str, decision: RoutingDecision
    ) -> None:
        """Persist a routing decision to the database."""
        event = NexusRoutingEvent(
            query_text=query,
            query_hash=hashlib.sha256(query.encode()).hexdigest()[:16],
            band=decision.band,
            resolved_zone=decision.resolved_zone,
            selected_tool=decision.selected_tool,
            raw_reranker_score=None,
            calibrated_confidence=decision.calibrated_confidence,
            is_multi_intent=decision.query_analysis.is_multi_intent,
            sub_query_count=len(decision.query_analysis.sub_queries),
            schema_verified=decision.schema_verified,
            is_ood=decision.is_ood,
        )
        session.add(event)
        await session.flush()
