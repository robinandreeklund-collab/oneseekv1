"""NEXUS Service — orchestrates all routing components.

Central coordination layer that connects QUL → OOD → StR → Bands → Zone
into a single routing pipeline.  Sprint 2 adds Select-Then-Route, Schema
Verifier, DATS calibration, ECE monitoring, and Space Auditor.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.nexus.calibration.dats_scaler import ZonalTemperatureScaler
from app.nexus.calibration.platt_scaler import PlattCalibratedReranker, PlattParams
from app.nexus.layers.auto_loop import AutoLoop
from app.nexus.layers.deploy_control import DeployControl
from app.nexus.layers.eval_ledger import EvalLedger
from app.nexus.layers.space_auditor import SpaceAuditor, ToolPoint
from app.nexus.layers.synth_forge import SynthForge
from app.nexus.models import (
    NexusAutoLoopRun,
    NexusCalibrationParam,
    NexusDarkMatterQuery,
    NexusPipelineMetric,
    NexusRoutingEvent,
    NexusSpaceSnapshot,
    NexusSyntheticCase,
    NexusZoneConfig,
)
from app.nexus.routing.confidence_bands import ConfidenceBandCascade
from app.nexus.routing.hard_negative_bank import HardNegativeMiner
from app.nexus.routing.ood_detector import DarkMatterDetector
from app.nexus.routing.qul import QueryUnderstandingLayer
from app.nexus.routing.schema_verifier import SchemaVerifier
from app.nexus.routing.select_then_route import SelectThenRoute
from app.nexus.routing.zone_manager import ZoneManager
from app.nexus.schemas import (
    AutoLoopRunResponse,
    CalibrationParamsResponse,
    ConfusionPair,
    DarkMatterCluster,
    ECEReport,
    GateResult as GateResultSchema,
    GateStatus as GateStatusSchema,
    HubnessReport,
    NexusConfigResponse,
    NexusHealthResponse,
    OODResult,
    PipelineMetricsSummary,
    PromotionResult as PromotionResultSchema,
    QueryAnalysis,
    QueryEntities,
    RollbackResult as RollbackResultSchema,
    RoutingCandidate,
    RoutingDecision,
    RoutingEventResponse,
    SpaceHealthReport,
    SpaceSnapshot,
    StageMetrics,
    SyntheticCaseResponse,
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
        # Sprint 2 additions
        self.str_pipeline = SelectThenRoute(zone_manager=self.zone_manager)
        self.schema_verifier = SchemaVerifier()
        self.dats_scaler = ZonalTemperatureScaler()
        self.space_auditor = SpaceAuditor()
        # Sprint 3 additions
        self.synth_forge = SynthForge()
        self.hard_negative_miner = HardNegativeMiner()
        self.eval_ledger = EvalLedger()
        self.auto_loop = AutoLoop()
        # Sprint 4 additions
        self.deploy_control = DeployControl()

    # ------------------------------------------------------------------
    # Health & Config
    # ------------------------------------------------------------------

    async def get_health(self, session: AsyncSession) -> NexusHealthResponse:
        """Return system health summary including model info."""
        from app.nexus.embeddings import get_embedding_info, get_reranker_info

        zones_count = (
            await session.scalar(select(func.count()).select_from(NexusZoneConfig)) or 0
        )
        events_count = (
            await session.scalar(select(func.count()).select_from(NexusRoutingEvent))
            or 0
        )
        synth_count = (
            await session.scalar(select(func.count()).select_from(NexusSyntheticCase))
            or 0
        )

        return NexusHealthResponse(
            status="ok",
            version="2.0.0",
            zones_configured=zones_count,
            total_routing_events=events_count,
            total_synthetic_cases=synth_count,
            embedding_model=get_embedding_info(),
            reranker=get_reranker_info(),
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
    # Full Routing Pipeline (Sprint 2: QUL → StR → OOD → Bands → Schema)
    # ------------------------------------------------------------------

    async def route_query(
        self,
        query: str,
        session: AsyncSession,
        *,
        tool_entries: list[dict] | None = None,
    ) -> RoutingDecision:
        """Run the full precision routing pipeline.

        Pipeline: QUL → StR → Rerank → Calibrate → OOD → Band → Schema verify.

        Args:
            query: User query.
            session: DB session.
            tool_entries: Pre-scored tool entries with zone/score.
                If None, runs QUL-only analysis (no retrieval).
        """
        from app.nexus.embeddings import nexus_rerank

        start_time = time.monotonic()

        # Step 1: QUL
        analysis = self.analyze_query(query)

        candidates: list[RoutingCandidate] = []
        selected_tool: str | None = None
        top_score = 0.0
        second_score = 0.0
        raw_top_score: float | None = None
        schema_verified = False

        if tool_entries:
            # Step 2: Select-Then-Route
            str_result = self.str_pipeline.run(
                query,
                analysis.zone_candidates,
                tool_entries,
            )

            # Step 2b: Rerank with real cross-encoder if available
            rerank_docs = [
                {
                    "document_id": c.tool_id,
                    "content": f"{c.tool_id} {c.namespace} {c.description}",
                    "score": c.raw_score,
                    "document": {
                        "id": c.tool_id,
                        "title": c.tool_id,
                        "document_type": "TOOL",
                    },
                }
                for c in str_result.candidates
            ]
            reranked = nexus_rerank(query, rerank_docs)

            # Build reranked score map
            rerank_scores: dict[str, float] = {}
            for doc in reranked:
                doc_id = doc.get("document_id", "")
                rerank_scores[doc_id] = doc.get("score", 0.0)

            top_score = str_result.top_score
            second_score = str_result.second_score

            # Step 3: Calibrate scores (use reranked scores when available)
            for rank, c in enumerate(str_result.candidates):
                raw = rerank_scores.get(c.tool_id, c.raw_score)
                calibrated = self.platt_scaler.calibrate(raw)
                candidates.append(
                    RoutingCandidate(
                        tool_id=c.tool_id,
                        zone=c.zone,
                        raw_score=raw,
                        calibrated_score=calibrated,
                        rank=rank,
                    )
                )

            # Re-sort by calibrated score after reranking
            candidates.sort(key=lambda rc: rc.calibrated_score, reverse=True)
            for i, rc in enumerate(candidates):
                rc.rank = i

            if candidates:
                raw_top_score = candidates[0].raw_score
                top_score = candidates[0].calibrated_score
                second_score = (
                    candidates[1].calibrated_score if len(candidates) > 1 else 0.0
                )
                selected_tool = candidates[0].tool_id

            # Step 4: Schema verification on top candidate
            if selected_tool:
                sv_result = self.schema_verifier.verify(
                    selected_tool,
                    query=query,
                    entities_locations=analysis.entities.locations,
                    entities_times=analysis.entities.times,
                    entities_organizations=analysis.entities.organizations,
                )
                schema_verified = sv_result.verified
                if sv_result.confidence_penalty > 0:
                    top_score = max(0.0, top_score - sv_result.confidence_penalty)

        # Step 5: OOD check
        if top_score > 0:
            ood_result = self.ood_detector.detect([top_score, second_score])
        else:
            ood_result = OODResult(is_ood=False, energy_score=0.0)

        # Step 6: Band classification
        band_result = self.band_cascade.classify(
            top_score=top_score,
            second_score=second_score,
        )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        decision = RoutingDecision(
            query_analysis=analysis,
            band=band_result.band,
            band_name=band_result.band_name,
            candidates=candidates,
            selected_tool=selected_tool,
            resolved_zone=(
                analysis.zone_candidates[0] if analysis.zone_candidates else None
            ),
            calibrated_confidence=top_score,
            is_ood=ood_result.is_ood,
            schema_verified=schema_verified,
            latency_ms=elapsed_ms,
        )

        # Log routing event
        await self._log_routing_event(session, query, decision, raw_top_score)

        return decision

    # ------------------------------------------------------------------
    # Space Auditor (Sprint 2)
    # ------------------------------------------------------------------

    async def get_space_health(self, session: AsyncSession) -> SpaceHealthReport:
        """Compute space health from latest snapshot or live tool data.

        Uses real embeddings from the configured embedding model when available,
        falling back to stored UMAP coordinates from DB snapshots.
        """
        from app.nexus.embeddings import nexus_embed

        # Try to get recent snapshots from DB
        result = await session.execute(
            select(NexusSpaceSnapshot)
            .order_by(NexusSpaceSnapshot.snapshot_at.desc())
            .limit(500)
        )
        snapshots = result.scalars().all()

        if not snapshots:
            return SpaceHealthReport(total_tools=0)

        # Group snapshots into tool points — prefer real embeddings
        tools: list[ToolPoint] = []
        seen: set[str] = set()
        for snap in snapshots:
            if snap.tool_id in seen:
                continue
            seen.add(snap.tool_id)

            zone = snap.namespace.split("/")[1] if "/" in snap.namespace else ""

            # Try real embedding from the configured model
            prefixed_text = f"[{zone.upper()[:5]}] {snap.tool_id} {snap.namespace}"
            real_emb = nexus_embed(prefixed_text)

            if real_emb is not None:
                tools.append(
                    ToolPoint(
                        tool_id=snap.tool_id,
                        namespace=snap.namespace,
                        zone=zone,
                        embedding=real_emb,
                    )
                )
            elif snap.umap_x is not None and snap.umap_y is not None:
                # Fallback to stored UMAP coords
                tools.append(
                    ToolPoint(
                        tool_id=snap.tool_id,
                        namespace=snap.namespace,
                        zone=zone,
                        embedding=[snap.umap_x, snap.umap_y],
                    )
                )

        if len(tools) < 2:
            return SpaceHealthReport(total_tools=len(tools))

        report = self.space_auditor.compute_separation_matrix(tools)

        zones = await self.get_zones(session)

        return SpaceHealthReport(
            global_silhouette=report.global_silhouette,
            zone_metrics=zones,
            top_confusion_pairs=[
                ConfusionPair(
                    tool_a=cp.tool_a,
                    tool_b=cp.tool_b,
                    similarity=cp.similarity,
                    zone_a=cp.zone_a,
                    zone_b=cp.zone_b,
                )
                for cp in report.confusion_pairs[:10]
            ],
            hubness_alerts=[
                HubnessReport(
                    tool_id=h.tool_id,
                    hubness_score=h.actual_rate,
                    times_as_nearest_neighbor=h.times_as_nn,
                )
                for h in report.hubness_alerts[:5]
            ],
            total_tools=report.total_tools,
        )

    async def get_space_snapshot(self, session: AsyncSession) -> SpaceSnapshot:
        """Get latest UMAP snapshot for visualization."""
        from datetime import datetime

        result = await session.execute(
            select(NexusSpaceSnapshot)
            .order_by(NexusSpaceSnapshot.snapshot_at.desc())
            .limit(500)
        )
        snapshots = result.scalars().all()

        if not snapshots:
            return SpaceSnapshot(
                snapshot_at=datetime.now(tz=UTC),
                points=[],
            )

        points = []
        for snap in snapshots:
            points.append(
                {
                    "tool_id": snap.tool_id,
                    "x": snap.umap_x,
                    "y": snap.umap_y,
                    "zone": snap.namespace.split("/")[1]
                    if "/" in snap.namespace
                    else "",
                    "cluster": snap.cluster_label,
                }
            )

        return SpaceSnapshot(
            snapshot_at=snapshots[0].snapshot_at,
            points=points,
        )

    async def get_confusion_pairs(
        self, session: AsyncSession, *, limit: int = 20
    ) -> list[ConfusionPair]:
        """Get top confusion pairs from latest space analysis."""
        report = await self.get_space_health(session)
        return report.top_confusion_pairs[:limit]

    async def get_hubness_alerts(
        self, session: AsyncSession, *, limit: int = 10
    ) -> list[HubnessReport]:
        """Get hubness alerts from latest space analysis."""
        report = await self.get_space_health(session)
        return report.hubness_alerts[:limit]

    async def get_zone_metrics(
        self, zone: str, session: AsyncSession
    ) -> ZoneConfigResponse | None:
        """Get metrics for a specific zone."""
        result = await session.execute(
            select(NexusZoneConfig).where(NexusZoneConfig.zone == zone)
        )
        row = result.scalars().first()
        if not row:
            return None
        return ZoneConfigResponse(
            zone=row.zone,
            prefix_token=row.prefix_token,
            silhouette_score=row.silhouette_score,
            inter_zone_min_distance=row.inter_zone_min_distance,
            ood_energy_threshold=row.ood_energy_threshold,
            band0_rate=row.band0_rate,
            ece_score=row.ece_score,
            last_reindexed=row.last_reindexed,
        )

    # ------------------------------------------------------------------
    # Synth Forge (Sprint 3)
    # ------------------------------------------------------------------

    async def forge_generate(
        self,
        session: AsyncSession,
        *,
        tool_ids: list[str] | None = None,
        difficulties: list[str] | None = None,
        questions_per_difficulty: int = 4,
    ) -> dict:
        """Run Synth Forge generation with the configured LLM.

        Calls the LLM to generate test questions, persists them to DB,
        and returns a summary.
        """
        from app.nexus.llm import nexus_llm_call
        from app.nexus.routing.schema_verifier import TOOL_SCHEMAS

        # Build tool metadata from schema registry
        tools: list[dict] = []
        for tid, schema in TOOL_SCHEMAS.items():
            tools.append(
                {
                    "tool_id": tid,
                    "name": tid.replace("_", " ").title(),
                    "description": schema.get("description", ""),
                    "namespace": f"tools/{tid}",
                    "keywords": schema.get("keywords", []),
                    "excludes": [],
                    "geographic_scope": schema.get("geographic_scope", ""),
                }
            )

        if not tools:
            return {"status": "error", "message": "No tools found in schema registry"}

        # Configure forge
        if difficulties:
            self.synth_forge.difficulties = difficulties
        self.synth_forge.questions_per_difficulty = questions_per_difficulty

        # Run forge with real LLM
        result = await self.synth_forge.run(
            tools,
            llm_call=nexus_llm_call,
            tool_ids=tool_ids,
        )

        # Persist generated cases to DB
        from app.nexus.llm import get_nexus_llm_info

        model_name = get_nexus_llm_info().get("model")

        persisted = 0
        for case in result.cases:
            db_case = NexusSyntheticCase(
                tool_id=case.tool_id,
                namespace=case.namespace,
                question=case.question,
                difficulty=case.difficulty,
                expected_tool=case.expected_tool,
                roundtrip_verified=case.roundtrip_verified,
                quality_score=case.quality_score,
                generation_run_id=result.run_id,
                generation_model=model_name,
            )
            session.add(db_case)
            persisted += 1

        if persisted > 0:
            await session.commit()

        return {
            "status": "completed",
            "run_id": str(result.run_id),
            "total_generated": result.total_generated,
            "total_verified": result.total_verified,
            "persisted_to_db": persisted,
            "by_difficulty": result.by_difficulty,
            "errors": result.errors,
        }

    async def get_synthetic_cases(
        self, session: AsyncSession, *, tool_id: str | None = None, limit: int = 100
    ) -> list[SyntheticCaseResponse]:
        """Get synthetic test cases from DB."""
        q = select(NexusSyntheticCase).order_by(NexusSyntheticCase.created_at.desc())
        if tool_id:
            q = q.where(NexusSyntheticCase.tool_id == tool_id)
        q = q.limit(limit)
        result = await session.execute(q)
        rows = result.scalars().all()
        return [
            SyntheticCaseResponse(
                id=row.id,
                tool_id=row.tool_id,
                namespace=row.namespace,
                question=row.question,
                difficulty=row.difficulty,
                expected_tool=row.expected_tool,
                roundtrip_verified=row.roundtrip_verified,
                quality_score=row.quality_score,
                created_at=row.created_at,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Auto Loop (Sprint 3)
    # ------------------------------------------------------------------

    async def get_loop_runs(
        self, session: AsyncSession, *, limit: int = 20
    ) -> list[AutoLoopRunResponse]:
        """Get auto-loop run history from DB."""
        result = await session.execute(
            select(NexusAutoLoopRun)
            .order_by(NexusAutoLoopRun.started_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            AutoLoopRunResponse(
                id=row.id,
                loop_number=row.loop_number,
                status=row.status,
                started_at=row.started_at,
                completed_at=row.completed_at,
                total_tests=row.total_tests,
                failures=row.failures,
                approved_proposals=row.approved_proposals,
                embedding_delta=row.embedding_delta,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Eval Ledger (Sprint 3)
    # ------------------------------------------------------------------

    async def get_pipeline_metrics(
        self, session: AsyncSession
    ) -> PipelineMetricsSummary:
        """Get latest pipeline metrics from DB."""
        result = await session.execute(
            select(NexusPipelineMetric)
            .order_by(NexusPipelineMetric.recorded_at.desc())
            .limit(50)
        )
        rows = result.scalars().all()

        stages = [
            StageMetrics(
                stage=row.stage,
                stage_name=row.stage_name,
                namespace=row.namespace,
                precision_at_1=row.precision_at_1,
                precision_at_5=row.precision_at_5,
                mrr_at_10=row.mrr_at_10,
                ndcg_at_5=row.ndcg_at_5,
                hard_negative_precision=row.hard_negative_precision,
                reranker_delta=row.reranker_delta,
                recorded_at=row.recorded_at,
            )
            for row in rows
        ]

        e2e = next((s for s in stages if s.stage_name == "e2e"), None)
        return PipelineMetricsSummary(stages=stages, overall_e2e=e2e)

    # ------------------------------------------------------------------
    # Dark Matter (Sprint 3)
    # ------------------------------------------------------------------

    async def get_dark_matter_clusters(
        self, session: AsyncSession
    ) -> list[DarkMatterCluster]:
        """Get dark matter OOD query clusters."""
        result = await session.execute(
            select(NexusDarkMatterQuery)
            .where(NexusDarkMatterQuery.reviewed.is_(False))
            .order_by(NexusDarkMatterQuery.created_at.desc())
            .limit(200)
        )
        rows = result.scalars().all()

        if not rows:
            return []

        ood_queries = [
            {"query_text": row.query_text, "energy_score": row.energy_score}
            for row in rows
        ]

        raw_clusters = self.ood_detector.cluster_dark_matter(ood_queries)
        return [
            DarkMatterCluster(
                cluster_id=c["cluster_id"],
                query_count=c["query_count"],
                sample_queries=c["sample_queries"],
                suggested_tool=c.get("suggested_tool"),
                reviewed=c.get("reviewed", False),
            )
            for c in raw_clusters
        ]

    # ------------------------------------------------------------------
    # Routing Events (Sprint 3)
    # ------------------------------------------------------------------

    async def get_routing_events(
        self, session: AsyncSession, *, limit: int = 50
    ) -> list[RoutingEventResponse]:
        """Get recent routing events."""
        result = await session.execute(
            select(NexusRoutingEvent)
            .order_by(NexusRoutingEvent.routed_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            RoutingEventResponse(
                id=row.id,
                query_text=row.query_text,
                band=row.band,
                resolved_zone=row.resolved_zone,
                selected_tool=row.selected_tool,
                calibrated_confidence=row.calibrated_confidence,
                is_multi_intent=row.is_multi_intent,
                is_ood=row.is_ood,
                routed_at=row.routed_at,
            )
            for row in rows
        ]

    async def log_feedback(
        self,
        session: AsyncSession,
        event_id: str,
        *,
        implicit: str | None = None,
        explicit: int | None = None,
    ) -> bool:
        """Log feedback for a routing event.

        Args:
            event_id: UUID of the routing event.
            implicit: 'reformulation' | 'follow_up' | None.
            explicit: -1 (bad), 0 (neutral), 1 (good).
        """
        import uuid as uuid_mod

        try:
            uid = uuid_mod.UUID(event_id)
        except ValueError:
            return False

        result = await session.execute(
            select(NexusRoutingEvent).where(NexusRoutingEvent.id == uid)
        )
        event = result.scalars().first()
        if not event:
            return False

        if implicit is not None:
            event.implicit_feedback = implicit
        if explicit is not None:
            event.explicit_feedback = explicit

        await session.flush()
        return True

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
            logger.info(
                "Loaded Platt calibration: A=%.4f, B=%.4f", row.param_a, row.param_b
            )

    # ------------------------------------------------------------------
    # Event Logging
    # ------------------------------------------------------------------

    async def _log_routing_event(
        self,
        session: AsyncSession,
        query: str,
        decision: RoutingDecision,
        raw_score: float | None = None,
    ) -> None:
        """Persist a routing decision to the database."""
        event = NexusRoutingEvent(
            query_text=query,
            query_hash=hashlib.sha256(query.encode()).hexdigest()[:16],
            band=decision.band,
            resolved_zone=decision.resolved_zone,
            selected_tool=decision.selected_tool,
            raw_reranker_score=raw_score,
            calibrated_confidence=decision.calibrated_confidence,
            is_multi_intent=decision.query_analysis.is_multi_intent,
            sub_query_count=len(decision.query_analysis.sub_queries),
            schema_verified=decision.schema_verified,
            is_ood=decision.is_ood,
        )
        session.add(event)
        await session.flush()

    # ------------------------------------------------------------------
    # Deploy Control (Sprint 4)
    # ------------------------------------------------------------------

    async def get_gate_status(
        self, tool_id: str, session: AsyncSession
    ) -> GateStatusSchema:
        """Evaluate all deployment gates for a tool."""
        gate_status = self.deploy_control.evaluate_all_gates(
            tool_id,
            # In production, these would come from DB/computed metrics
            silhouette_score=None,
            success_rate=None,
            description_clarity=None,
        )
        return GateStatusSchema(
            tool_id=gate_status.tool_id,
            gates=[
                GateResultSchema(
                    gate_number=g.gate_number,
                    gate_name=g.gate_name,
                    passed=g.passed,
                    score=g.score,
                    threshold=g.threshold,
                    details=g.details,
                )
                for g in gate_status.gates
            ],
            all_passed=gate_status.all_passed,
            recommendation=gate_status.recommendation,
        )

    async def promote_tool(
        self, tool_id: str, session: AsyncSession
    ) -> PromotionResultSchema:
        """Promote a tool to the next lifecycle stage."""
        result = self.deploy_control.promote(tool_id)
        return PromotionResultSchema(
            tool_id=result.tool_id,
            success=result.success,
            message=result.message,
        )

    async def rollback_tool(
        self, tool_id: str, session: AsyncSession
    ) -> RollbackResultSchema:
        """Rollback a tool to ROLLED_BACK stage."""
        result = self.deploy_control.rollback(tool_id)
        return RollbackResultSchema(
            tool_id=result.tool_id,
            success=result.success,
            message=result.message,
        )

    # ------------------------------------------------------------------
    # Calibration (Sprint 4)
    # ------------------------------------------------------------------

    async def get_calibration_params(
        self, session: AsyncSession
    ) -> list[CalibrationParamsResponse]:
        """Get all calibration parameters."""
        result = await session.execute(
            select(NexusCalibrationParam).order_by(
                NexusCalibrationParam.fitted_at.desc()
            )
        )
        rows = result.scalars().all()
        return [
            CalibrationParamsResponse(
                id=row.id,
                zone=row.zone,
                calibration_method=row.calibration_method,
                param_a=row.param_a,
                param_b=row.param_b,
                temperature=row.temperature,
                ece_score=row.ece_score,
                fitted_on_samples=row.fitted_on_samples,
                fitted_at=row.fitted_at,
                is_active=row.is_active,
            )
            for row in rows
        ]

    async def get_ece_report(self, session: AsyncSession) -> ECEReport:
        """Get ECE report across all zones."""
        result = await session.execute(
            select(NexusCalibrationParam).where(
                NexusCalibrationParam.is_active.is_(True)
            )
        )
        rows = result.scalars().all()

        per_zone: dict[str, float] = {}
        for row in rows:
            if row.ece_score is not None:
                per_zone[row.zone] = row.ece_score

        global_ece = sum(per_zone.values()) / len(per_zone) if per_zone else None

        return ECEReport(global_ece=global_ece, per_zone=per_zone)

    async def fit_calibration(self, session: AsyncSession) -> dict:
        """Fit Platt calibration using routing event data.

        Collects (raw_score, band) pairs from routing events and fits
        the Platt sigmoid to produce calibrated confidence scores.
        """
        from datetime import UTC, datetime

        # Load routing events with scores
        result = await session.execute(
            select(NexusRoutingEvent)
            .where(NexusRoutingEvent.raw_reranker_score.isnot(None))
            .order_by(NexusRoutingEvent.routed_at.desc())
            .limit(1000)
        )
        events = result.scalars().all()

        if len(events) < 10:
            return {
                "status": "insufficient_data",
                "message": f"Need at least 10 scored events, got {len(events)}",
            }

        # Build training data: raw_score → binary label (band 0/1 = correct)
        scores = []
        labels = []
        for ev in events:
            scores.append(ev.raw_reranker_score)
            labels.append(1.0 if ev.band <= 1 else 0.0)

        # Fit Platt scaler
        params = self.platt_scaler.fit(scores, labels)

        # Persist calibration per zone
        from app.nexus.config import ZONE_PREFIXES

        fitted_count = 0
        for zone in ZONE_PREFIXES:
            # Deactivate old params
            old = await session.execute(
                select(NexusCalibrationParam).where(
                    NexusCalibrationParam.zone == zone,
                    NexusCalibrationParam.is_active.is_(True),
                )
            )
            for old_row in old.scalars().all():
                old_row.is_active = False

            # Insert new
            cal = NexusCalibrationParam(
                zone=zone,
                calibration_method="platt",
                param_a=params.a,
                param_b=params.b,
                temperature=1.0,
                ece_score=None,
                fitted_on_samples=len(scores),
                fitted_at=datetime.now(tz=UTC),
                is_active=True,
            )
            session.add(cal)
            fitted_count += 1

        await session.commit()

        return {
            "status": "completed",
            "fitted_on_samples": len(scores),
            "param_a": params.a,
            "param_b": params.b,
            "zones_updated": fitted_count,
        }

    # ------------------------------------------------------------------
    # Band Distribution (Sprint 5)
    # ------------------------------------------------------------------

    async def get_band_distribution(self, session: AsyncSession) -> dict:
        """Get band distribution from routing events."""
        result = await session.execute(
            select(
                NexusRoutingEvent.band,
                func.count(NexusRoutingEvent.id),
            ).group_by(NexusRoutingEvent.band)
        )
        rows = result.all()

        distribution = [0, 0, 0, 0, 0]
        for band, count in rows:
            if 0 <= band <= 4:
                distribution[band] = count

        total = sum(distribution)
        return {
            "distribution": distribution,
            "total": total,
            "percentages": [
                round(d / total * 100, 1) if total > 0 else 0 for d in distribution
            ],
        }

    # ------------------------------------------------------------------
    # Ledger Trend (Sprint 5)
    # ------------------------------------------------------------------

    async def get_ledger_trend(self, session: AsyncSession, *, days: int = 30) -> dict:
        """Get metrics trend over time."""
        from datetime import timedelta

        from app.nexus.schemas import MetricsTrend

        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        result = await session.execute(
            select(NexusPipelineMetric)
            .where(NexusPipelineMetric.recorded_at >= cutoff)
            .order_by(NexusPipelineMetric.recorded_at.asc())
        )
        rows = result.scalars().all()

        data_points = []
        for row in rows:
            data_points.append(
                {
                    "date": row.recorded_at.isoformat() if row.recorded_at else None,
                    "stage": row.stage_name,
                    "precision_at_1": row.precision_at_1,
                    "mrr_at_10": row.mrr_at_10,
                }
            )

        return MetricsTrend(period_days=days, data_points=data_points)

    # ------------------------------------------------------------------
    # Auto Loop Run (Sprint 5)
    # ------------------------------------------------------------------

    async def run_auto_loop(self, session: AsyncSession) -> dict:
        """Run a complete auto-loop iteration inline.

        Steps: Load test cases → Route each → Compare → Cluster → Propose
        """
        import uuid

        now = datetime.now(tz=UTC)

        # Count existing runs
        run_count = (
            await session.scalar(select(func.count()).select_from(NexusAutoLoopRun))
            or 0
        )
        loop_number = run_count + 1
        run_id = uuid.uuid4()

        # Create run record
        db_run = NexusAutoLoopRun(
            id=run_id,
            loop_number=loop_number,
            started_at=now,
            status="running",
        )
        session.add(db_run)
        await session.flush()

        # Load test cases
        result = await session.execute(select(NexusSyntheticCase).limit(200))
        cases = result.scalars().all()

        if not cases:
            db_run.status = "failed"
            db_run.completed_at = datetime.now(tz=UTC)
            await session.commit()
            return {
                "status": "failed",
                "run_id": str(run_id),
                "message": "Inga testfall hittade. Kör forge/generate först.",
            }

        # Evaluate
        total_tests = 0
        failures = 0
        failed_queries: list[dict] = []

        for case in cases:
            total_tests += 1
            try:
                decision = await self.route_query(case.question, session)
                if case.expected_tool and decision.selected_tool != case.expected_tool:
                    failures += 1
                    failed_queries.append(
                        {
                            "query": case.question,
                            "expected_tool": case.expected_tool,
                            "got_tool": decision.selected_tool or "(none)",
                        }
                    )
            except Exception as e:
                failures += 1
                logger.warning("Loop eval error: %s", e)

        # Cluster failures and create proposals
        clusters = self.auto_loop.cluster_failures(failed_queries)
        proposals = self.auto_loop.create_proposals(clusters)

        # Update run
        db_run.total_tests = total_tests
        db_run.failures = failures
        db_run.metadata_proposals = {
            "proposals": [
                {"tool_id": p.tool_id, "field": p.field_name, "reason": p.reason}
                for p in proposals
            ]
        }
        db_run.approved_proposals = 0
        db_run.status = "review" if proposals else "approved"
        db_run.completed_at = datetime.now(tz=UTC)
        await session.commit()

        return {
            "status": "completed",
            "run_id": str(run_id),
            "loop_number": loop_number,
            "total_tests": total_tests,
            "failures": failures,
            "proposals": len(proposals),
        }
