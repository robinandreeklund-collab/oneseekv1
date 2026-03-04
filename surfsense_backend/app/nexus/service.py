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
from app.nexus.routing.shadow_observer import ShadowObserver
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
        # Shadow observer — reads from real platform routing pipeline
        self.shadow_observer = ShadowObserver()

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
        """Return all zone configurations from DB.

        Filters out stale zone names (e.g. old 'myndigheter', 'handling')
        that no longer match the current ZONE_PREFIXES config.
        """
        from app.nexus.config import ZONE_PREFIXES

        valid_zones = set(ZONE_PREFIXES.keys())

        result = await session.execute(select(NexusZoneConfig))
        rows = result.scalars().all()

        # Filter to only valid current zones
        valid_rows = [r for r in rows if r.zone in valid_zones]

        if not valid_rows:
            # Return default zone config if DB is empty or all stale
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
            for row in valid_rows
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
                If None, auto-builds from the platform tool registry.
        """
        from app.nexus.embeddings import nexus_rerank

        start_time = time.monotonic()

        # Step 1: QUL
        analysis = self.analyze_query(query)

        # Auto-build tool_entries from platform registry if not provided
        if tool_entries is None:
            tool_entries = self._build_tool_entries_from_platform(analysis)

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
        If no DB snapshots exist, dynamically builds from platform tools.
        """
        from app.nexus.embeddings import nexus_embed

        # Try to get recent snapshots from DB
        result = await session.execute(
            select(NexusSpaceSnapshot)
            .order_by(NexusSpaceSnapshot.snapshot_at.desc())
            .limit(500)
        )
        snapshots = result.scalars().all()

        # Group snapshots into tool points — prefer real embeddings
        tools: list[ToolPoint] = []
        seen: set[str] = set()

        if snapshots:
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
                    tools.append(
                        ToolPoint(
                            tool_id=snap.tool_id,
                            namespace=snap.namespace,
                            zone=zone,
                            embedding=[snap.umap_x, snap.umap_y],
                        )
                    )

        # If no snapshots in DB, build from live platform tools
        if not tools:
            tools = self._build_tool_points_from_platform()

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
        """Get latest UMAP snapshot for visualization.

        Falls back to dynamically generating points from live platform tools
        if no DB snapshots exist.
        """
        import random
        from datetime import datetime

        result = await session.execute(
            select(NexusSpaceSnapshot)
            .order_by(NexusSpaceSnapshot.snapshot_at.desc())
            .limit(500)
        )
        snapshots = result.scalars().all()

        if snapshots:
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

        # No DB snapshots — build dynamically from platform tools
        from app.nexus.platform_bridge import get_platform_tools

        platform_tools = get_platform_tools()
        if not platform_tools:
            return SpaceSnapshot(
                snapshot_at=datetime.now(tz=UTC),
                points=[],
            )

        # Generate UMAP-like 2D coordinates clustered by zone
        zone_centers = {
            "kunskap": (-1.0, 1.5),
            "skapande": (2.0, -1.0),
            "jämförelse": (3.0, 2.0),
            "konversation": (-3.0, -2.0),
        }
        zone_list = list(zone_centers.keys())

        points = []
        for pt in platform_tools:
            if pt.category == "external_model":
                continue
            cx, cy = zone_centers.get(pt.zone, (0, 0))
            cluster = zone_list.index(pt.zone) if pt.zone in zone_list else 0
            points.append(
                {
                    "tool_id": pt.tool_id,
                    "x": cx + random.uniform(-0.8, 0.8),
                    "y": cy + random.uniform(-0.8, 0.8),
                    "zone": pt.zone,
                    "cluster": cluster,
                }
            )

        return SpaceSnapshot(
            snapshot_at=datetime.now(tz=UTC),
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
        category: str | None = None,
        namespace: str | None = None,
        zone: str | None = None,
        difficulties: list[str] | None = None,
        questions_per_difficulty: int = 4,
    ) -> dict:
        """Run Synth Forge generation with the configured LLM.

        Args:
            tool_ids: Specific tool IDs to generate for. If None, uses all.
            category: Filter by tool category (e.g. "smhi", "scb", "kolada",
                      "riksdagen", "trafikverket", "bolagsverket", "marketplace",
                      "skolverket", "builtin", "external_model").
            namespace: Filter by namespace prefix (e.g. "tools/weather").
            zone: Filter by intent zone (e.g. "kunskap", "skapande").
            difficulties: Override difficulty levels.
            questions_per_difficulty: Questions per difficulty per tool.
        """
        from app.nexus.llm import nexus_llm_call
        from app.nexus.platform_bridge import get_platform_tools

        # Build tool metadata from REAL platform tool registry
        platform_tools = get_platform_tools()
        tools: list[dict] = []
        for pt in platform_tools:
            # Always exclude external model tools — they are for compare mode
            # only and must never be invoked by forge or auto_loop
            if pt.category == "external_model":
                continue
            # Filter by category if specified
            if category and pt.category != category:
                continue
            # Filter by namespace prefix if specified
            if namespace and not "/".join(pt.namespace).startswith(namespace):
                continue
            # Filter by zone if specified
            if zone and pt.zone != zone:
                continue
            tools.append(
                {
                    "tool_id": pt.tool_id,
                    "name": pt.name,
                    "description": pt.description,
                    "namespace": "/".join(pt.namespace),
                    "keywords": pt.keywords,
                    "excludes": pt.excludes,
                    "geographic_scope": pt.geographic_scope,
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
        """Get latest pipeline metrics from DB, deduplicated per stage.

        Returns only the most recent metric row per stage_name, so the
        Ledger tab shows the latest values rather than historical duplicates.
        """
        result = await session.execute(
            select(NexusPipelineMetric)
            .order_by(NexusPipelineMetric.recorded_at.desc())
            .limit(100)
        )
        rows = result.scalars().all()

        # Deduplicate: keep only the latest row per stage_name
        seen_stages: set[str] = set()
        unique_rows = []
        for row in rows:
            if row.stage_name not in seen_stages:
                seen_stages.add(row.stage_name)
                unique_rows.append(row)

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
            for row in unique_rows
        ]

        # Sort by stage number
        stages.sort(key=lambda s: s.stage)

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
    # Tool Entry Builder
    # ------------------------------------------------------------------

    def _build_tool_entries_from_platform(self, analysis: QueryAnalysis) -> list[dict]:
        """Build tool_entries from the platform registry with QUL-based scoring.

        When route_query() is called without pre-scored tool_entries, this
        method creates them from the real platform tool registry, scoring
        each tool based on keyword overlap, zone match, and domain hints.

        Scores are normalized to [0, 1] to match the band threshold scale
        (Band 0 ≥ 0.95, Band 1 ≥ 0.80, Band 2 ≥ 0.60, Band 3 ≥ 0.40).
        """
        from app.nexus.embeddings import nexus_embed_score
        from app.nexus.platform_bridge import get_platform_tools

        tools = get_platform_tools()
        if not tools:
            return []

        query_lower = analysis.normalized_query.lower()
        query_tokens = set(query_lower.split())
        zone_candidates = set(analysis.zone_candidates)
        domain_hints = set(analysis.domain_hints)

        raw_entries: list[tuple[dict, float]] = []
        for pt in tools:
            # Skip external model tools — compare mode only
            if pt.category == "external_model":
                continue

            score = 0.0

            # Zone match bonus
            if pt.zone in zone_candidates:
                score += 0.15

            # Keyword overlap scoring
            tool_keywords = {k.lower() for k in pt.keywords}
            keyword_hits = query_tokens & tool_keywords
            if keyword_hits:
                score += min(0.20, len(keyword_hits) * 0.07)

            # Domain hint match (category matches QUL domain hints)
            if pt.category in domain_hints:
                score += 0.10

            # Name/ID match — direct substring match in query
            tool_name_lower = pt.tool_id.lower().replace("_", " ")
            if any(
                tok in query_lower for tok in tool_name_lower.split() if len(tok) > 3
            ):
                score += 0.10

            # Description similarity (embedding-based — primary signal)
            emb_score = nexus_embed_score(
                query_lower,
                f"{pt.tool_id} {pt.description}",
            )
            if emb_score is not None and emb_score > 0:
                # Cosine similarity is the main scoring signal
                score += emb_score * 0.60

            raw_entries.append(
                (
                    {
                        "tool_id": pt.tool_id,
                        "namespace": "/".join(pt.namespace),
                        "zone": pt.zone,
                        "description": pt.description,
                    },
                    score,
                )
            )

        if not raw_entries:
            return []

        # Sort by raw score descending, take top 20
        raw_entries.sort(key=lambda e: e[1], reverse=True)
        top_entries = raw_entries[:20]

        # Normalize scores to [0, 1] using min-max on the top-20 range
        # This ensures the best match gets a high score (~0.95-1.0)
        # and poor matches get low scores, matching band thresholds.
        scores = [e[1] for e in top_entries]
        max_score = max(scores) if scores else 1.0
        min_score = min(scores) if scores else 0.0
        score_range = max_score - min_score

        entries: list[dict] = []
        for entry_dict, raw_score in top_entries:
            if score_range > 0 and max_score > 0:
                # Normalize to [0.3, 1.0] — the best match gets ~1.0,
                # the worst of top-20 gets ~0.3
                normalized = 0.3 + 0.7 * (raw_score - min_score) / score_range
            else:
                normalized = 0.5

            entry_dict["score"] = round(normalized, 4)
            entries.append(entry_dict)

        return entries

    def _build_tool_points_from_platform(self) -> list[ToolPoint]:
        """Build ToolPoints from the live platform registry for space analysis.

        Used when no DB snapshots exist — dynamically creates tool points
        from the real platform tool registry with real embeddings when possible.
        """
        from app.nexus.embeddings import nexus_embed
        from app.nexus.platform_bridge import get_platform_tools

        platform_tools = get_platform_tools()
        points: list[ToolPoint] = []
        for pt in platform_tools:
            if pt.category == "external_model":
                continue
            ns_str = "/".join(pt.namespace)
            prefixed_text = f"[{pt.zone.upper()[:5]}] {pt.tool_id} {ns_str}"
            emb = nexus_embed(prefixed_text)
            if emb is not None:
                points.append(
                    ToolPoint(
                        tool_id=pt.tool_id,
                        namespace=ns_str,
                        zone=pt.zone,
                        embedding=emb,
                    )
                )
            else:
                # Fallback: use zone-based synthetic 2D coordinates
                import random

                zone_centers = {
                    "kunskap": (-1.0, 1.5),
                    "skapande": (2.0, -1.0),
                    "jämförelse": (3.0, 2.0),
                    "konversation": (-3.0, -2.0),
                }
                cx, cy = zone_centers.get(pt.zone, (0, 0))
                points.append(
                    ToolPoint(
                        tool_id=pt.tool_id,
                        namespace=ns_str,
                        zone=pt.zone,
                        embedding=[
                            cx + random.uniform(-0.8, 0.8),
                            cy + random.uniform(-0.8, 0.8),
                        ],
                    )
                )
        return points

    # ------------------------------------------------------------------
    # Deploy Control (Sprint 4)
    # ------------------------------------------------------------------

    async def _compute_gate_metrics(
        self, tool_id: str, session: AsyncSession
    ) -> dict:
        """Compute real metrics for deploy gates from DB and platform data."""
        # Gate 1: Silhouette score from space snapshots
        silhouette_score: float | None = None
        sil_result = await session.execute(
            select(NexusSpaceSnapshot.silhouette_score)
            .where(
                NexusSpaceSnapshot.tool_id == tool_id,
                NexusSpaceSnapshot.silhouette_score.isnot(None),
            )
            .order_by(NexusSpaceSnapshot.snapshot_at.desc())
            .limit(1)
        )
        sil_row = sil_result.scalar_one_or_none()
        if sil_row is not None:
            silhouette_score = float(sil_row)
        else:
            # Fallback: use zone-level silhouette from zone config
            zone_result = await session.execute(
                select(NexusZoneConfig.silhouette_score).where(
                    NexusZoneConfig.silhouette_score.isnot(None)
                )
            )
            zone_sils = [float(r) for r in zone_result.scalars().all() if r is not None]
            if zone_sils:
                silhouette_score = sum(zone_sils) / len(zone_sils)

        # Gate 2: Success rate from routing events
        success_rate: float | None = None
        total_events = await session.scalar(
            select(func.count()).select_from(NexusRoutingEvent).where(
                NexusRoutingEvent.selected_tool == tool_id
            )
        )
        if total_events and total_events > 0:
            positive_events = await session.scalar(
                select(func.count()).select_from(NexusRoutingEvent).where(
                    NexusRoutingEvent.selected_tool == tool_id,
                    NexusRoutingEvent.explicit_feedback == 1,
                )
            )
            negative_events = await session.scalar(
                select(func.count()).select_from(NexusRoutingEvent).where(
                    NexusRoutingEvent.selected_tool == tool_id,
                    NexusRoutingEvent.explicit_feedback == -1,
                )
            )
            feedback_events = (positive_events or 0) + (negative_events or 0)
            if feedback_events > 0:
                success_rate = (positive_events or 0) / feedback_events
            else:
                # No explicit feedback — use band-0 rate as proxy
                band0_events = await session.scalar(
                    select(func.count()).select_from(NexusRoutingEvent).where(
                        NexusRoutingEvent.selected_tool == tool_id,
                        NexusRoutingEvent.band == 0,
                    )
                )
                success_rate = (band0_events or 0) / total_events
        else:
            # No routing events for this tool — use pipeline metrics P@1
            pm_result = await session.execute(
                select(NexusPipelineMetric.precision_at_1)
                .where(
                    NexusPipelineMetric.stage_name == "e2e",
                    NexusPipelineMetric.precision_at_1.isnot(None),
                )
                .order_by(NexusPipelineMetric.recorded_at.desc())
                .limit(1)
            )
            pm_row = pm_result.scalar_one_or_none()
            if pm_row is not None:
                success_rate = float(pm_row)

        # Gate 3: Description clarity from platform tool metadata
        description_clarity: float | None = None
        keyword_relevance: float | None = None
        try:
            from app.nexus.platform_bridge import get_platform_tools

            pt_tools = get_platform_tools()
            tool_meta = next((t for t in pt_tools if t.tool_id == tool_id), None)
            if tool_meta:
                desc = tool_meta.description or ""
                kws = tool_meta.keywords or []
                # Heuristic scoring (0-5 scale):
                # Description clarity: based on length and specificity
                desc_len = len(desc)
                if desc_len > 100:
                    description_clarity = 4.5
                elif desc_len > 50:
                    description_clarity = 4.0
                elif desc_len > 20:
                    description_clarity = 3.5
                elif desc_len > 0:
                    description_clarity = 2.5
                else:
                    description_clarity = 1.0
                # Keyword relevance: based on keyword count
                if len(kws) >= 5:
                    keyword_relevance = 4.5
                elif len(kws) >= 3:
                    keyword_relevance = 4.0
                elif len(kws) >= 1:
                    keyword_relevance = 3.5
                else:
                    keyword_relevance = 2.0
        except Exception:
            pass

        return {
            "silhouette_score": silhouette_score,
            "success_rate": success_rate,
            "description_clarity": description_clarity,
            "keyword_relevance": keyword_relevance,
        }

    async def get_gate_status(
        self, tool_id: str, session: AsyncSession
    ) -> GateStatusSchema:
        """Evaluate all deployment gates for a tool."""
        metrics = await self._compute_gate_metrics(tool_id, session)
        gate_status = self.deploy_control.evaluate_all_gates(
            tool_id,
            silhouette_score=metrics["silhouette_score"],
            success_rate=metrics["success_rate"],
            description_clarity=metrics["description_clarity"],
            keyword_relevance=metrics.get("keyword_relevance"),
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

    async def run_auto_loop(
        self,
        session: AsyncSession,
        *,
        category: str | None = None,
    ) -> dict:
        """Run a complete auto-loop iteration inline.

        Steps: Load test cases → Route each (NEXUS + platform) → Compare → Cluster → Propose.

        Evaluates both NEXUS routing AND real platform routing
        (via smart_retrieve_tools_with_breakdown) to find discrepancies.

        Args:
            category: Optional category to filter test cases by (e.g. "smhi", "scb").
                      Only runs on test cases whose tool_id belongs to tools in that category.
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

        # Load test cases — optionally filtered by category
        result = await session.execute(select(NexusSyntheticCase).limit(500))
        all_cases = result.scalars().all()

        # Filter by category if specified
        if category:
            from app.nexus.platform_bridge import get_platform_tools

            cat_tool_ids = {
                t.tool_id for t in get_platform_tools() if t.category == category
            }
            cases = [c for c in all_cases if c.tool_id in cat_tool_ids]
        else:
            cases = list(all_cases)

        if not cases:
            db_run.status = "failed"
            db_run.completed_at = datetime.now(tz=UTC)
            await session.commit()
            return {
                "status": "failed",
                "run_id": str(run_id),
                "message": "Inga testfall hittade. Kör forge/generate först.",
            }

        # Evaluate using both NEXUS routing and real platform retrieval
        total_tests = 0
        failures = 0
        failed_queries: list[dict] = []
        platform_comparisons = 0
        platform_agreements = 0
        # Track per-stage metrics for the ledger
        band_counts = [0, 0, 0, 0, 0]
        correct_at_1 = 0
        correct_at_5 = 0
        reciprocal_ranks: list[float] = []

        for case in cases:
            total_tests += 1
            try:
                # NEXUS routing
                decision = await self.route_query(case.question, session)
                nexus_tool = decision.selected_tool
                band_counts[min(decision.band, 4)] += 1

                # Track ranking metrics
                candidate_ids = [c.tool_id for c in decision.candidates]
                if case.expected_tool:
                    if nexus_tool == case.expected_tool:
                        correct_at_1 += 1
                    if case.expected_tool in candidate_ids[:5]:
                        correct_at_5 += 1
                    if case.expected_tool in candidate_ids:
                        rank = candidate_ids.index(case.expected_tool) + 1
                        reciprocal_ranks.append(1.0 / rank)
                    else:
                        reciprocal_ranks.append(0.0)

                # Also run through real platform retrieval for comparison
                platform_result = await self.shadow_observer.run_platform_retrieval(
                    case.question, session=session
                )
                platform_tool = platform_result.get("top1")

                if platform_tool:
                    platform_comparisons += 1
                    if nexus_tool == platform_tool:
                        platform_agreements += 1

                # Check against expected tool
                if case.expected_tool and nexus_tool != case.expected_tool:
                    failures += 1
                    failed_queries.append(
                        {
                            "query": case.question,
                            "expected_tool": case.expected_tool,
                            "got_tool": nexus_tool or "(none)",
                            "platform_tool": platform_tool or "(none)",
                        }
                    )
            except Exception as e:
                failures += 1
                logger.warning("Loop eval error: %s", e)

        # Cluster failures and create proposals
        clusters = self.auto_loop.cluster_failures(failed_queries)
        proposals = self.auto_loop.create_proposals(clusters)

        # Compute pipeline metrics
        p_at_1 = correct_at_1 / total_tests if total_tests > 0 else 0.0
        p_at_5 = correct_at_5 / total_tests if total_tests > 0 else 0.0
        mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0

        # Persist pipeline metrics to the ledger only if we have enough data
        # to produce meaningful metrics (avoid overwriting good seed data with 0s)
        if total_tests >= 3:
            metric_stages = [
                (1, "intent", p_at_1, p_at_5, mrr, None, None, None),
                (2, "route", p_at_1, p_at_5, mrr, mrr, None, None),
                (
                    3,
                    "rerank",
                    p_at_1,
                    p_at_5,
                    mrr,
                    mrr,
                    (
                        platform_agreements / platform_comparisons
                        if platform_comparisons > 0
                        else None
                    ),
                    None,
                ),
                (4, "e2e", p_at_1, p_at_5, mrr, mrr, None, None),
            ]
            for stage, name, p1, p5, mrr_val, ndcg, hn_p, delta in metric_stages:
                metric = NexusPipelineMetric(
                    run_id=run_id,
                    stage=stage,
                    stage_name=name,
                    precision_at_1=p1,
                    precision_at_5=p5,
                    mrr_at_10=mrr_val,
                    ndcg_at_5=ndcg,
                    hard_negative_precision=hn_p,
                    reranker_delta=delta,
                    recorded_at=datetime.now(tz=UTC),
                )
                session.add(metric)

        # Update run
        db_run.total_tests = total_tests
        db_run.failures = failures
        db_run.metadata_proposals = {
            "proposals": [
                {"tool_id": p.tool_id, "field": p.field_name, "reason": p.reason}
                for p in proposals
            ],
            "platform_comparisons": platform_comparisons,
            "platform_agreements": platform_agreements,
            "band_distribution": band_counts,
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
            "platform_comparisons": platform_comparisons,
            "platform_agreements": platform_agreements,
            "platform_agreement_rate": (
                round(platform_agreements / platform_comparisons, 3)
                if platform_comparisons > 0
                else None
            ),
            "precision_at_1": round(p_at_1, 3),
            "precision_at_5": round(p_at_5, 3),
            "mrr": round(mrr, 3),
            "band_distribution": band_counts,
        }

    # ------------------------------------------------------------------
    # Shadow Observer (Platform Integration)
    # ------------------------------------------------------------------

    async def get_shadow_report(self, session: AsyncSession) -> dict:
        """Get a report on how NEXUS routing compares to real platform routing.

        Reads from the platform's retrieval_feedback_store and returns
        insights about routing accuracy and discrepancies.
        """
        feedback = self.shadow_observer.get_retrieval_feedback_snapshot()

        # Get current live routing config
        try:
            from app.nexus.platform_bridge import get_retrieval_tuning

            tuning = await get_retrieval_tuning(session)
        except Exception:
            tuning = {"live_routing_enabled": False, "live_routing_phase": "shadow"}

        return {
            "feedback_store": {
                "total_patterns": feedback.get("count", 0),
                "sample_rows": feedback.get("rows", [])[:20],
            },
            "live_routing": tuning,
        }

    async def compare_single_query(
        self,
        query: str,
        session: AsyncSession,
    ) -> dict:
        """Route a query through both NEXUS and real platform, return comparison."""
        # NEXUS routing
        nexus_decision = await self.route_query(query, session)

        # Real platform routing
        platform_result = await self.shadow_observer.run_platform_retrieval(
            query, session=session
        )

        comparison = self.shadow_observer.compare_routing(
            query=query,
            nexus_tool=nexus_decision.selected_tool,
            nexus_score=nexus_decision.calibrated_confidence,
            nexus_band=nexus_decision.band,
            platform_result=platform_result,
        )

        return {
            "query": query,
            "nexus": {
                "selected_tool": nexus_decision.selected_tool,
                "confidence": nexus_decision.calibrated_confidence,
                "band": nexus_decision.band,
                "zone": nexus_decision.resolved_zone,
                "is_ood": nexus_decision.is_ood,
            },
            "platform": {
                "top1": platform_result.get("top1"),
                "top2": platform_result.get("top2"),
                "top1_score": platform_result.get("top1_score", 0.0),
                "top2_score": platform_result.get("top2_score", 0.0),
                "margin": platform_result.get("margin"),
                "candidates": platform_result.get("ranked_ids", []),
            },
            "agreement": comparison.agreement,
        }
