"""NEXUS Service — orchestrates all routing components.

Central coordination layer that connects QUL → Agent → StR → Bands → Zone
into a single routing pipeline.  The agent layer sits between intent/zone
resolution and tool retrieval: Intent → Agent → Tool.
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
    NexusDeployState,
    NexusHardNegative,
    NexusPipelineMetric,
    NexusRoutingEvent,
    NexusSpaceSnapshot,
    NexusSyntheticCase,
    NexusZoneConfig,
)
from app.nexus.routing.agent_resolver import AgentResolver
from app.nexus.routing.confidence_bands import ConfidenceBandCascade
from app.nexus.routing.hard_negative_bank import HardNegativeMiner
from app.nexus.routing.ood_detector import DarkMatterDetector
from app.nexus.routing.qul import QueryUnderstandingLayer
from app.nexus.routing.schema_verifier import SchemaVerifier
from app.nexus.routing.select_then_route import SelectThenRoute
from app.nexus.routing.shadow_observer import ShadowObserver
from app.nexus.routing.zone_manager import ZoneManager
from app.nexus.schemas import (
    AgentCandidateResponse,
    AgentResolution,
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


# ---------------------------------------------------------------------------
# Helpers for mapping namespaces to real zone domain_ids
# ---------------------------------------------------------------------------


def _zone_from_namespace_str(namespace: str) -> str:
    """Derive the real zone domain_id from a namespace string.

    Uses NAMESPACE_ZONE_MAP so "tools/trafik/trafikverket_trafikinfo"
    resolves to "trafik-och-transport" instead of just "trafik".
    """
    from app.nexus.config import NAMESPACE_ZONE_MAP

    if "/" not in namespace:
        return namespace
    parts = namespace.split("/")
    if len(parts) >= 2:
        prefix = f"{parts[0]}/{parts[1]}"
        if prefix in NAMESPACE_ZONE_MAP:
            return NAMESPACE_ZONE_MAP[prefix]
    return parts[1] if len(parts) > 1 else namespace


def _all_zone_centers() -> dict[str, tuple[float, float]]:
    """Return 2D cluster centers for all 17 domains.

    Spread across a grid so each domain gets a distinct visual cluster
    in the UMAP space map.
    """
    return {
        # Row 1 (top)
        "väder-och-klimat": (-4.0, 3.0),
        "trafik-och-transport": (-2.0, 3.0),
        "energi-och-miljö": (0.0, 3.0),
        "hälsa-och-vård": (2.0, 3.0),
        # Row 2
        "ekonomi-och-skatter": (-4.0, 1.0),
        "arbetsmarknad": (-2.0, 1.0),
        "befolkning-och-demografi": (0.0, 1.0),
        "utbildning": (2.0, 1.0),
        # Row 3
        "näringsliv-och-bolag": (-4.0, -1.0),
        "fastighet-och-mark": (-2.0, -1.0),
        "handel-och-marknad": (0.0, -1.0),
        "politik-och-beslut": (2.0, -1.0),
        "rättsväsende": (4.0, -1.0),
        # Row 4 (bottom)
        "kunskap": (-3.0, -3.0),
        "skapande": (-1.0, -3.0),
        "konversation": (1.0, -3.0),
        "jämförelse": (3.0, -3.0),
    }


class NexusService:
    """Orchestrates the full NEXUS precision routing pipeline."""

    def __init__(self):
        self.qul = QueryUnderstandingLayer()
        self.agent_resolver = AgentResolver()
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
    # Dynamic Agent Loading (from admin flow DB)
    # ------------------------------------------------------------------

    async def _load_db_agents(
        self, session: AsyncSession
    ) -> tuple[dict | None, dict | None, dict | None, dict | None]:
        """Load agent definitions and hints from DB (admin flow routing).

        Returns (agent_by_name, agents_by_zone, domain_hints, category_hints)
        or (None, None, None, None) if no overrides exist, in which case
        static config.py values are used.
        """
        try:
            from app.nexus.config import (
                build_agents_from_metadata,
                build_hints_from_metadata,
            )
            from app.services.agent_metadata_service import (
                get_effective_agent_metadata,
            )

            metadata = await get_effective_agent_metadata(session)
            if not metadata:
                return None, None, None, None
            by_name, by_zone = build_agents_from_metadata(metadata)
            domain_hints, category_hints = build_hints_from_metadata(metadata)
            if by_name:
                return by_name, by_zone, domain_hints, category_hints
        except Exception as e:
            logger.warning("Failed to load DB agents, using static config: %s", e)
        return None, None, None, None

    # ------------------------------------------------------------------
    # Health & Config
    # ------------------------------------------------------------------

    async def get_health(self, session: AsyncSession) -> NexusHealthResponse:
        """Return system health summary including model info.

        Also auto-loads calibration and deploy state on first call.
        """
        from app.nexus.embeddings import get_embedding_info, get_reranker_info

        # Auto-load Platt calibration from DB if not fitted
        if not self.platt_scaler.is_fitted:
            await self.load_calibration(session)

        # Auto-load deploy state from DB
        if not self.deploy_control.is_loaded:
            await self._ensure_deploy_state_loaded(session)

        # Ensure zones are auto-seeded before counting
        await self.get_zones(session)
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
            version="2.1.0",
            zones_configured=zones_count,
            total_routing_events=events_count,
            total_synthetic_cases=synth_count,
            embedding_model=get_embedding_info(),
            reranker=get_reranker_info(),
        )

    async def get_zones(self, session: AsyncSession) -> list[ZoneConfigResponse]:
        """Return all zone configurations from DB.

        Auto-seeds missing zones into DB so that all domains appear.
        Uses ``get_all_zone_prefixes()`` which includes both legacy 4 zones
        and the new 17 domain zones.
        """
        from app.nexus.config import get_all_zone_prefixes

        valid_zones = set(get_all_zone_prefixes().keys())

        result = await session.execute(select(NexusZoneConfig))
        rows = result.scalars().all()

        # Filter to only valid current zones
        existing_zones = {r.zone for r in rows if r.zone in valid_zones}

        # Auto-seed any missing zones into DB
        missing_zones = valid_zones - existing_zones
        if missing_zones:
            for zone_data in self.zone_manager.get_zone_config_data():
                if zone_data["zone"] in missing_zones:
                    new_zone = NexusZoneConfig(
                        zone=zone_data["zone"],
                        prefix_token=zone_data["prefix_token"],
                    )
                    await session.merge(new_zone)
            await session.flush()
            # Re-query to get all rows
            result = await session.execute(select(NexusZoneConfig))
            rows = result.scalars().all()

        valid_rows = [r for r in rows if r.zone in valid_zones]

        # Compute zone-level metrics on-demand from routing events
        # so that band0_rate, ece_score, and silhouette are populated.
        try:
            await self._update_zone_metrics(session)
        except Exception as e:
            logger.warning("Failed to update zone metrics in get_zones: %s", e)

        # Re-query to get updated values
        result = await session.execute(select(NexusZoneConfig))
        valid_rows = [r for r in result.scalars().all() if r.zone in valid_zones]

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

    def _analyze_query_with_hints(
        self,
        query: str,
        *,
        domain_hints_map: dict[str, list[str]] | None = None,
        category_hints_map: dict[str, list[str]] | None = None,
    ) -> QueryAnalysis:
        """Run QUL analysis with optional dynamic hints from DB."""
        result = self.qul.analyze(
            query,
            domain_hints_map=domain_hints_map,
            category_hints_map=category_hints_map,
        )

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

    def analyze_query(self, query: str) -> QueryAnalysis:
        """Run QUL analysis on a query (no DB, no LLM). Uses static hints."""
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
    # Full Routing Pipeline: QUL → Agent → StR → OOD → Bands → Schema
    # ------------------------------------------------------------------

    async def route_query(
        self,
        query: str,
        session: AsyncSession,
        *,
        tool_entries: list[dict] | None = None,
        run_llm_judge: bool = False,
    ) -> RoutingDecision:
        """Run the full precision routing pipeline.

        Pipeline: QUL → Agent Resolution → StR → Rerank → Calibrate → OOD → Band → Schema.

        The agent layer is the key difference from the old pipeline:
        Intent (zone) → Agent (narrow) → Tool (specific).

        Args:
            query: User query.
            session: DB session.
            tool_entries: Pre-scored tool entries with zone/score.
                If None, auto-builds from the platform tool registry.
        """
        from app.nexus.embeddings import nexus_rerank

        start_time = time.monotonic()

        # Load dynamic agents and hints from DB (admin flow) if available
        (
            db_agent_by_name,
            db_agents_by_zone,
            db_domain_hints,
            db_category_hints,
        ) = await self._load_db_agents(session)

        # Step 1: QUL — Intent/Zone resolution (with dynamic hints)
        analysis = self._analyze_query_with_hints(
            query,
            domain_hints_map=db_domain_hints,
            category_hints_map=db_category_hints,
        )

        # Step 2: Agent Resolution — narrow from zone to specific agent(s)
        agent_result = self.agent_resolver.resolve(
            analysis.normalized_query,
            analysis.zone_candidates,
            domain_hints=analysis.domain_hints,
            organizations=analysis.entities.organizations,
            agent_by_name=db_agent_by_name,
            agents_by_zone=db_agents_by_zone,
        )
        agent_namespaces = agent_result.get_tool_namespaces(db_agent_by_name)
        selected_agent = agent_result.top_agent

        agent_resolution = AgentResolution(
            selected_agents=agent_result.selected_agents,
            candidates=[
                AgentCandidateResponse(
                    name=c.agent.name,
                    zone=c.agent.zone,
                    score=round(c.score, 3),
                    matched_keywords=c.matched_keywords,
                )
                for c in agent_result.candidates[:5]
            ],
            tool_namespaces=agent_namespaces,
        )

        # Auto-build tool_entries from platform registry if not provided
        if tool_entries is None:
            tool_entries = self._build_tool_entries_from_platform(analysis)

        candidates: list[RoutingCandidate] = []
        selected_tool: str | None = None
        top_score = 0.0
        second_score = 0.0
        raw_top_score: float | None = None
        raw_margin: float | None = None
        schema_verified = False

        if tool_entries:
            # Step 3: Select-Then-Route — filtered by agent namespaces
            str_result = self.str_pipeline.run(
                query,
                analysis.zone_candidates,
                tool_entries,
                agent_namespaces=agent_namespaces if agent_namespaces else None,
            )

            # Step 3b: Rerank with real cross-encoder if available
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

            # Step 4: Calibrate scores (use reranked scores when available)
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
            # Use raw_score as tiebreaker when calibrated scores are equal
            # (e.g. when Platt scaler produces degenerate all-zero outputs)
            candidates.sort(
                key=lambda rc: (rc.calibrated_score, rc.raw_score), reverse=True
            )
            for i, rc in enumerate(candidates):
                rc.rank = i

            if candidates:
                raw_top_score = candidates[0].raw_score
                raw_second = candidates[1].raw_score if len(candidates) > 1 else 0.0
                raw_margin = raw_top_score - raw_second
                top_score = candidates[0].calibrated_score
                second_score = (
                    candidates[1].calibrated_score if len(candidates) > 1 else 0.0
                )
                selected_tool = candidates[0].tool_id

            # Step 5: Schema verification on top candidate
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

        # Step 6: OOD check
        if top_score > 0:
            ood_result = self.ood_detector.detect([top_score, second_score])
        else:
            ood_result = OODResult(is_ood=False, energy_score=0.0)

        # Step 7: Band classification — use raw margin to avoid Platt
        # compression collapsing the gap between top candidates.
        band_result = self.band_cascade.classify(
            top_score=top_score,
            second_score=second_score,
            raw_margin=raw_margin,
        )

        # Optional: LLM Tool Judge
        llm_judge_result = None
        if run_llm_judge and candidates:
            from app.nexus.platform_bridge import get_platform_tools as _gpt
            from app.nexus.schemas import LlmJudgeResult

            _desc_map = {t.tool_id: t.description for t in _gpt()}
            judge_candidates = [
                {
                    "tool_id": c.tool_id,
                    "name": c.tool_id,
                    "description": _desc_map.get(c.tool_id, ""),
                    "score": c.calibrated_score,
                }
                for c in candidates[:5]
            ]
            try:
                judge_raw = await self.llm_judge_tools(query, judge_candidates)
                llm_judge_result = LlmJudgeResult(
                    chosen_tool=judge_raw.get("chosen_tool"),
                    reasoning=judge_raw.get("reasoning", ""),
                    nexus_rank_of_chosen=judge_raw.get("nexus_rank_of_chosen", -1),
                    agreement=judge_raw.get("agreement", False),
                )
            except Exception:
                pass  # LLM judge is optional — don't fail routing

        elapsed_ms = (time.monotonic() - start_time) * 1000

        decision = RoutingDecision(
            query_analysis=analysis,
            agent_resolution=agent_resolution,
            band=band_result.band,
            band_name=band_result.band_name,
            candidates=candidates,
            selected_tool=selected_tool,
            selected_agent=selected_agent,
            resolved_zone=(
                analysis.zone_candidates[0] if analysis.zone_candidates else None
            ),
            calibrated_confidence=top_score,
            is_ood=ood_result.is_ood,
            schema_verified=schema_verified,
            latency_ms=elapsed_ms,
            llm_judge=llm_judge_result,
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

                zone = _zone_from_namespace_str(snap.namespace)

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

        # Update zone_config DB rows with latest silhouette scores
        try:
            for zone_name, sil_score in (report.per_zone_silhouette or {}).items():
                zc_result = await session.execute(
                    select(NexusZoneConfig).where(NexusZoneConfig.zone == zone_name)
                )
                zc_row = zc_result.scalars().first()
                if zc_row and sil_score is not None:
                    zc_row.silhouette_score = round(sil_score, 4)
            await session.flush()
        except Exception as e:
            logger.warning("Failed to update zone silhouette scores: %s", e)

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
            cluster_purity=report.cluster_purity
            if hasattr(report, "cluster_purity")
            else None,
            confusion_risk=(
                round(len(report.confusion_pairs) / max(report.total_tools, 1), 3)
                if report.confusion_pairs
                else 0.0
            ),
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
                        "zone": _zone_from_namespace_str(snap.namespace),
                        "namespace": snap.namespace,
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
        # All 17 domains get distinct cluster centers
        zone_centers = _all_zone_centers()
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
                    "namespace": "/".join(pt.namespace) if isinstance(pt.namespace, (list, tuple)) else pt.namespace,
                    "cluster": cluster,
                }
            )

        return SpaceSnapshot(
            snapshot_at=datetime.now(tz=UTC),
            points=points,
        )

    async def refresh_space_snapshot(self, session: AsyncSession) -> int:
        """Recompute space snapshot from current tool embeddings.

        Embeds all platform tools, runs PCA/UMAP to 2D, and saves the
        result to NexusSpaceSnapshot so the Space tab shows real positions.

        Returns:
            Number of tool points saved.
        """
        from app.nexus.embeddings import nexus_embed_np
        from app.nexus.platform_bridge import get_platform_tools

        tools = get_platform_tools()
        filtered = [t for t in tools if t.category != "external_model"]
        if not filtered:
            return 0

        # Build ToolPoints with real embeddings
        from app.nexus.layers.space_auditor import ToolPoint

        tool_points: list[ToolPoint] = []
        for pt in filtered:
            emb = nexus_embed_np(f"{pt.tool_id} {pt.description}")
            if emb is not None:
                tool_points.append(
                    ToolPoint(
                        tool_id=pt.tool_id,
                        zone=pt.zone,
                        embedding=emb.tolist(),
                        namespace="/".join(pt.namespace) if isinstance(pt.namespace, (list, tuple)) else pt.namespace,
                    )
                )

        if len(tool_points) < 3:
            return 0

        # Compute 2D projection via space auditor
        import numpy as np

        embeddings = np.array([tp.embedding for tp in tool_points], dtype=np.float32)
        umap_points = self.space_auditor._compute_umap(embeddings, tool_points)

        # Build namespace lookup from ToolPoints
        ns_map = {tp.tool_id: tp.namespace for tp in tool_points}

        # Delete old snapshots and insert new ones
        from sqlalchemy import delete

        await session.execute(delete(NexusSpaceSnapshot))

        now = datetime.now(tz=UTC)
        for up in umap_points:
            session.add(
                NexusSpaceSnapshot(
                    tool_id=up.tool_id,
                    namespace=ns_map.get(up.tool_id, up.zone),
                    embedding_model="refresh",
                    umap_x=up.x,
                    umap_y=up.y,
                    cluster_label=up.cluster_label,
                    snapshot_at=now,
                )
            )
        await session.commit()

        logger.info("Refreshed space snapshot: %d tool points", len(umap_points))
        return len(umap_points)

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

        # Build namespace → agent lookup for expected_agent on test cases
        from app.nexus.config import NEXUS_AGENTS

        _ns_to_agent: dict[str, str] = {}
        for ag in NEXUS_AGENTS:
            for ns_prefix in ag.primary_namespaces:
                _ns_to_agent[ns_prefix] = ag.name

        def _find_agent_for_tool(pt_obj) -> str | None:
            ns_str = "/".join(pt_obj.namespace[:2])
            if ns_str in _ns_to_agent:
                return _ns_to_agent[ns_str]
            # Try single segment
            if pt_obj.namespace and pt_obj.namespace[0] in _ns_to_agent:
                return _ns_to_agent[pt_obj.namespace[0]]
            return None

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
                    "zone": pt.zone,
                    "agent": _find_agent_for_tool(pt),
                }
            )

        if not tools:
            return {"status": "error", "message": "No tools found in schema registry"}

        # Configure forge
        if difficulties:
            self.synth_forge.difficulties = difficulties
        self.synth_forge.questions_per_difficulty = questions_per_difficulty

        # Build a retrieve_fn for roundtrip verification
        # This calls the real embedding scorer to check if the expected
        # tool appears in the top-k results for a given query.
        from app.nexus.config import SYNTH_ROUNDTRIP_TOP_K
        from app.nexus.embeddings import nexus_embed_score

        def retrieve_fn(query: str) -> list[str]:
            """Score all tools against the query and return top-k tool IDs."""
            scored = []
            for t in tools:
                tid = t.get("tool_id", "")
                desc = t.get("description", "")
                score = nexus_embed_score(query, f"{tid} {desc}")
                scored.append((tid, score if score is not None else 0.0))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [tid for tid, _ in scored[:SYNTH_ROUNDTRIP_TOP_K]]

        # Run forge with real LLM and real roundtrip verification
        result = await self.synth_forge.run(
            tools,
            llm_call=nexus_llm_call,
            retrieve_fn=retrieve_fn,
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
                expected_intent=case.expected_intent,
                expected_agent=case.expected_agent,
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
        results = []
        for row in rows:
            meta = row.metadata_proposals or {}
            iterations = meta.get("iterations", [])
            results.append(
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
                    total_cases_available=meta.get("total_cases_available"),
                    iterations_completed=len(iterations) if iterations else None,
                )
            )
        return results

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
                selected_agent=getattr(row, "selected_agent", None),
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
            # Sanity check: reject degenerate params that crush all outputs
            import numpy as _np

            _test = _np.array([0.1, 0.3, 0.5, 0.7, 0.9])
            _out = 1.0 / (1.0 + _np.exp(row.param_a * _test + row.param_b))
            if _np.max(_out) < 0.01 or _np.min(_out) > 0.99:
                logger.warning(
                    "Loaded Platt params degenerate (A=%.4f, B=%.4f → max=%.6f). "
                    "Using unfitted pass-through instead.",
                    row.param_a,
                    row.param_b,
                    float(_np.max(_out)),
                )
            else:
                self.platt_scaler = PlattCalibratedReranker(
                    PlattParams(
                        a=row.param_a,
                        b=row.param_b,
                        fitted=True,
                        n_samples=row.fitted_on_samples or 0,
                    )
                )
                logger.info(
                    "Loaded Platt calibration: A=%.4f, B=%.4f",
                    row.param_a,
                    row.param_b,
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
        """Persist a routing decision to the database.

        If OOD, also logs a dark matter query with UAEval4RAG category.
        """
        event = NexusRoutingEvent(
            query_text=query,
            query_hash=hashlib.sha256(query.encode()).hexdigest()[:16],
            band=decision.band,
            resolved_zone=decision.resolved_zone,
            selected_agent=decision.selected_agent,
            selected_tool=decision.selected_tool,
            raw_reranker_score=raw_score,
            calibrated_confidence=decision.calibrated_confidence,
            is_multi_intent=decision.query_analysis.is_multi_intent,
            sub_query_count=len(decision.query_analysis.sub_queries),
            schema_verified=decision.schema_verified,
            is_ood=decision.is_ood,
        )
        session.add(event)

        # If OOD, classify with UAEval4RAG and log dark matter query
        if decision.is_ood:
            uaq_category = self.ood_detector.classify_ood_category(
                query,
                entities_locations=decision.query_analysis.entities.locations,
                entities_times=decision.query_analysis.entities.times,
                zone_candidates=decision.query_analysis.zone_candidates,
                tool_count=len(decision.candidates),
            )
            dm_query = NexusDarkMatterQuery(
                query_text=query,
                energy_score=0.0,
                uaq_category=uaq_category,
            )
            session.add(dm_query)

        await session.flush()

    # ------------------------------------------------------------------
    # Tool Entry Builder
    # ------------------------------------------------------------------

    def _build_tool_entries_from_platform(self, analysis: QueryAnalysis) -> list[dict]:
        """Build tool_entries from the platform registry with embedding-first scoring.

        Scoring strategy (aligned with vision):
        1. Embedding cosine similarity is the BASE signal (0.0-1.0)
        2. Zone match, keywords, and domain hints are small BONUSES
        3. NO min-max normalization — scores must reflect real similarity
           so that band thresholds (0.95/0.80/0.60/0.40) work correctly.

        Uses nexus_batch_score to embed the query once and score all tools
        via vectorized cosine similarity in a single operation.
        """
        from app.nexus.config import get_all_zone_prefixes
        from app.nexus.embeddings import nexus_batch_score
        from app.nexus.platform_bridge import get_platform_tools

        tools = get_platform_tools()
        if not tools:
            return []

        all_prefixes = get_all_zone_prefixes()
        query_lower = analysis.normalized_query.lower()
        query_tokens = set(query_lower.split())
        zone_candidates = set(analysis.zone_candidates)
        domain_hints = set(analysis.domain_hints)

        # Build zone-prefixed query for embedding (vision: prefix trick)
        # Use all_prefixes so new domains (e.g. trafik-och-transport) get prefixed too
        zone_hint = analysis.zone_candidates[0] if analysis.zone_candidates else None
        prefixed_query = query_lower
        if zone_hint and zone_hint in all_prefixes:
            prefixed_query = f"{all_prefixes[zone_hint]}{query_lower}"

        # Filter tools and build tool texts for batch scoring
        # Include keywords and example queries for better intra-category
        # discrimination (e.g. störningar vs olyckor vs köer)
        filtered_tools = [pt for pt in tools if pt.category != "external_model"]
        tool_texts = []
        for pt in filtered_tools:
            zone_prefix = all_prefixes.get(pt.zone, "")
            kw_text = " ".join(pt.keywords[:8]) if pt.keywords else ""
            ex_text = " | ".join(pt.example_queries[:2]) if pt.example_queries else ""
            tool_texts.append(
                f"{zone_prefix}{pt.tool_id} {pt.description} {kw_text} {ex_text}"
            )

        # Batch score: embed query once, all tool texts in one pass,
        # vectorized cosine similarity
        emb_scores = nexus_batch_score(prefixed_query, tool_texts)

        raw_entries: list[tuple[dict, float]] = []
        for i, pt in enumerate(filtered_tools):
            # PRIMARY SIGNAL: Embedding cosine similarity (0.0-1.0)
            emb_score = emb_scores[i] if emb_scores is not None else None

            # Fallback to 0.20 when embedding model is unavailable
            score = emb_score if emb_score is not None and emb_score > 0 else 0.20

            # BONUS: Zone match (+0.05 — modest boost for matching zone)
            if pt.zone in zone_candidates:
                score += 0.05

            # BONUS: Keyword overlap (+0.05 per exact hit, max +0.15)
            # Strong enough to discriminate between similar tools in same category
            # (e.g. störningar vs olyckor vs köer within trafikverket_trafikinfo)
            tool_keywords = {k.lower() for k in pt.keywords}
            keyword_hits = query_tokens & tool_keywords
            if keyword_hits:
                score += min(0.15, len(keyword_hits) * 0.05)

            # BONUS: Substring keyword match for Swedish compound words (+0.04 per hit, max +0.12)
            # Handles cases like "signalproblem" matching keyword "signal",
            # "trafikstockning" matching "stockning", "vägavstängningar" matching "avstängning"
            substring_hits = 0
            for kw in tool_keywords - keyword_hits:  # skip already-matched
                if len(kw) >= 4 and kw in query_lower:
                    substring_hits += 1
            if substring_hits:
                score += min(0.12, substring_hits * 0.04)

            # BONUS: Domain hint match (+0.10)
            if pt.category in domain_hints:
                score += 0.10

            # BONUS: Name/ID direct match (+0.05)
            tool_name_lower = pt.tool_id.lower().replace("_", " ")
            if any(
                tok in query_lower for tok in tool_name_lower.split() if len(tok) > 3
            ):
                score += 0.05

            # Cap at 1.0
            score = min(1.0, score)

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

        # Sort by score descending, take top 20
        raw_entries.sort(key=lambda e: e[1], reverse=True)
        top_entries = raw_entries[:20]

        # NO normalization — scores are already in [0, 1] from cosine similarity.
        # Band thresholds (0.95/0.80/0.60/0.40) are designed for this scale.
        entries: list[dict] = []
        for entry_dict, raw_score in top_entries:
            entry_dict["score"] = round(raw_score, 4)
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

                all_centers = _all_zone_centers()
                cx, cy = all_centers.get(pt.zone, (0, 0))
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

    async def _compute_gate_metrics(self, tool_id: str, session: AsyncSession) -> dict:
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
            select(func.count())
            .select_from(NexusRoutingEvent)
            .where(NexusRoutingEvent.selected_tool == tool_id)
        )
        if total_events and total_events > 0:
            positive_events = await session.scalar(
                select(func.count())
                .select_from(NexusRoutingEvent)
                .where(
                    NexusRoutingEvent.selected_tool == tool_id,
                    NexusRoutingEvent.explicit_feedback == 1,
                )
            )
            negative_events = await session.scalar(
                select(func.count())
                .select_from(NexusRoutingEvent)
                .where(
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
                    select(func.count())
                    .select_from(NexusRoutingEvent)
                    .where(
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

        # Gate 3: Real LLM judge evaluation (no heuristics)
        description_clarity: float | None = None
        keyword_relevance: float | None = None
        disambiguation_quality: float | None = None

        # First check if we already have cached LLM judge scores in deploy state
        deploy_state = await session.execute(
            select(NexusDeployState).where(NexusDeployState.tool_id == tool_id)
        )
        deploy_row = deploy_state.scalars().first()
        if deploy_row and deploy_row.gate3_details:
            g3 = deploy_row.gate3_details
            description_clarity = g3.get("description_clarity")
            keyword_relevance = g3.get("keyword_relevance")
            disambiguation_quality = g3.get("disambiguation_quality")
        else:
            # Run real LLM judge evaluation
            try:
                from app.nexus.llm import nexus_llm_call
                from app.nexus.platform_bridge import get_platform_tools

                pt_tools = get_platform_tools()
                tool_meta = next((t for t in pt_tools if t.tool_id == tool_id), None)
                if tool_meta:
                    # Find similar tools in same zone for disambiguation check
                    similar = [
                        t.tool_id
                        for t in pt_tools
                        if t.zone == tool_meta.zone and t.tool_id != tool_id
                    ][:5]

                    prompt = self.deploy_control.build_llm_judge_prompt(
                        tool_id=tool_id,
                        tool_name=tool_meta.name,
                        description=tool_meta.description,
                        keywords=tool_meta.keywords,
                        namespace="/".join(tool_meta.namespace),
                        category=tool_meta.category,
                        similar_tools=similar,
                    )
                    response = await nexus_llm_call(prompt)
                    scores = self.deploy_control.parse_llm_judge_response(response)
                    description_clarity = scores.get("description_clarity")
                    keyword_relevance = scores.get("keyword_relevance")
                    disambiguation_quality = scores.get("disambiguation_quality")

                    # Cache the LLM judge results in deploy state
                    if deploy_row:
                        deploy_row.gate3_score = (
                            sum(
                                s
                                for s in [
                                    description_clarity,
                                    keyword_relevance,
                                    disambiguation_quality,
                                ]
                                if s
                            )
                            / 3.0
                        )
                        deploy_row.gate3_details = scores
                    else:
                        new_state = NexusDeployState(
                            tool_id=tool_id,
                            stage="review",
                            gate3_score=(
                                sum(
                                    s
                                    for s in [
                                        description_clarity,
                                        keyword_relevance,
                                        disambiguation_quality,
                                    ]
                                    if s
                                )
                                / 3.0
                            ),
                            gate3_details=scores,
                        )
                        session.add(new_state)
                    await session.flush()
            except Exception as e:
                logger.warning("LLM judge evaluation failed for %s: %s", tool_id, e)

        return {
            "silhouette_score": silhouette_score,
            "success_rate": success_rate,
            "description_clarity": description_clarity,
            "keyword_relevance": keyword_relevance,
            "disambiguation_quality": disambiguation_quality,
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
            disambiguation_quality=metrics.get("disambiguation_quality"),
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
        """Promote a tool to the next lifecycle stage. Persists to DB."""
        # Load deploy state from DB if not loaded
        await self._ensure_deploy_state_loaded(session)

        result = self.deploy_control.promote(tool_id)
        if result.success:
            await self._persist_deploy_state(session, tool_id, result.to_stage)
        return PromotionResultSchema(
            tool_id=result.tool_id,
            success=result.success,
            message=result.message,
        )

    async def rollback_tool(
        self, tool_id: str, session: AsyncSession
    ) -> RollbackResultSchema:
        """Rollback a tool to ROLLED_BACK stage. Persists to DB."""
        await self._ensure_deploy_state_loaded(session)

        result = self.deploy_control.rollback(tool_id)
        if result.success:
            await self._persist_deploy_state(session, tool_id, result.to_stage)
        return RollbackResultSchema(
            tool_id=result.tool_id,
            success=result.success,
            message=result.message,
        )

    async def _ensure_deploy_state_loaded(self, session: AsyncSession) -> None:
        """Load deploy state from DB into DeployControl cache if not loaded."""
        if self.deploy_control.is_loaded:
            return
        result = await session.execute(select(NexusDeployState))
        rows = result.scalars().all()
        db_rows = [{"tool_id": r.tool_id, "stage": r.stage} for r in rows]
        self.deploy_control.load_from_db_rows(db_rows)

    async def _persist_deploy_state(
        self, session: AsyncSession, tool_id: str, stage: str
    ) -> None:
        """Persist a deploy state change to DB."""
        result = await session.execute(
            select(NexusDeployState).where(NexusDeployState.tool_id == tool_id)
        )
        existing = result.scalars().first()
        if existing:
            existing.stage = stage
            existing.promoted_at = datetime.now(tz=UTC)
        else:
            session.add(
                NexusDeployState(
                    tool_id=tool_id,
                    stage=stage,
                    promoted_at=datetime.now(tz=UTC),
                )
            )
        await session.flush()

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
        """Get ECE report across all zones.

        Tries calibration params first; if none exist, computes ECE
        directly from routing events as |avg_confidence - accuracy|.
        """
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

        # If no calibration params, compute ECE from zone_config DB rows
        if not per_zone:
            zc_result = await session.execute(select(NexusZoneConfig))
            for zc in zc_result.scalars().all():
                if zc.ece_score is not None:
                    per_zone[zc.zone] = zc.ece_score

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

        # Persist calibration per zone (all 17 domain zones)
        from app.nexus.config import get_all_zone_prefixes

        all_zones = get_all_zone_prefixes()
        fitted_count = 0
        for zone in all_zones:
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
    # Overview Metrics (ECE, Band-0, OOD rate, namespace purity)
    # ------------------------------------------------------------------

    async def _update_zone_metrics(self, session: AsyncSession) -> None:
        """Recompute zone-level metrics from routing events and update DB.

        Called when overview metrics are requested to keep zone rows fresh.
        """
        from app.nexus.config import get_all_zone_prefixes

        for zone_name in get_all_zone_prefixes():
            # Count band-0 events for this zone
            zone_total = (
                await session.scalar(
                    select(func.count())
                    .select_from(NexusRoutingEvent)
                    .where(NexusRoutingEvent.resolved_zone == zone_name)
                )
                or 0
            )
            if zone_total == 0:
                continue

            zone_band0 = (
                await session.scalar(
                    select(func.count())
                    .select_from(NexusRoutingEvent)
                    .where(
                        NexusRoutingEvent.resolved_zone == zone_name,
                        NexusRoutingEvent.band == 0,
                    )
                )
                or 0
            )
            band0_rate = zone_band0 / zone_total

            # Average calibrated confidence as proxy for ECE quality
            avg_conf = await session.scalar(
                select(func.avg(NexusRoutingEvent.calibrated_confidence)).where(
                    NexusRoutingEvent.resolved_zone == zone_name,
                    NexusRoutingEvent.calibrated_confidence.isnot(None),
                )
            )

            # Update zone config row
            result = await session.execute(
                select(NexusZoneConfig).where(NexusZoneConfig.zone == zone_name)
            )
            zone_row = result.scalars().first()
            if not zone_row:
                # Auto-create zone config row for new domain zones
                all_prefixes = get_all_zone_prefixes()
                zone_row = NexusZoneConfig(
                    zone=zone_name,
                    prefix_token=all_prefixes.get(zone_name, f"[{zone_name[:5].upper()}] "),
                )
                session.add(zone_row)
            zone_row.band0_rate = round(band0_rate, 4)
            if avg_conf is not None:
                # ECE approximation: |average_confidence - accuracy|
                # accuracy proxy: proportion of events in bands 0-1
                zone_b01 = (
                    await session.scalar(
                        select(func.count())
                        .select_from(NexusRoutingEvent)
                        .where(
                            NexusRoutingEvent.resolved_zone == zone_name,
                            NexusRoutingEvent.band <= 1,
                        )
                    )
                    or 0
                )
                accuracy_proxy = zone_b01 / zone_total
                zone_row.ece_score = round(abs(avg_conf - accuracy_proxy), 4)

        await session.flush()

    async def get_overview_metrics(self, session: AsyncSession) -> dict:
        """Get key metrics for the overview tab.

        Returns:
            Dict with band0_rate, ece_global, ood_rate, namespace_purity,
            platt_calibrated, total_events, total_tools, total_hard_negatives.
        """
        # Update zone-level metrics from routing events
        try:
            await self._update_zone_metrics(session)
        except Exception as e:
            logger.warning("Failed to update zone metrics: %s", e)

        # Band distribution
        band_dist = await self.get_band_distribution(session)
        total = band_dist["total"]
        band0_rate = band_dist["percentages"][0] / 100.0 if total > 0 else 0.0

        # OOD rate
        ood_count = (
            await session.scalar(
                select(func.count())
                .select_from(NexusRoutingEvent)
                .where(NexusRoutingEvent.is_ood.is_(True))
            )
            or 0
        )
        ood_rate = ood_count / total if total > 0 else 0.0

        # ECE from calibration
        ece_report = await self.get_ece_report(session)

        # Schema verification rate (namespace purity proxy)
        # Only count non-OOD events to avoid ratio > 1.0
        non_ood_count = total - ood_count
        schema_verified_count = (
            await session.scalar(
                select(func.count())
                .select_from(NexusRoutingEvent)
                .where(
                    NexusRoutingEvent.schema_verified.is_(True),
                    NexusRoutingEvent.is_ood.is_(False),
                )
            )
            or 0
        )
        namespace_purity = (
            schema_verified_count / non_ood_count if non_ood_count > 0 else 0.0
        )

        # Hard negatives count
        hn_count = (
            await session.scalar(select(func.count()).select_from(NexusHardNegative))
            or 0
        )

        # Tool count from platform
        try:
            from app.nexus.platform_bridge import get_platform_tools

            tool_count = len(
                [t for t in get_platform_tools() if t.category != "external_model"]
            )
        except Exception:
            tool_count = 0

        # Multi-intent rate
        multi_intent_count = (
            await session.scalar(
                select(func.count())
                .select_from(NexusRoutingEvent)
                .where(NexusRoutingEvent.is_multi_intent.is_(True))
            )
            or 0
        )
        multi_intent_rate = multi_intent_count / total if total > 0 else None

        # Reranker delta from latest pipeline metrics
        reranker_delta = None
        try:
            reranker_row = (
                (
                    await session.execute(
                        select(NexusPipelineMetric)
                        .where(NexusPipelineMetric.stage_name == "rerank")
                        .order_by(NexusPipelineMetric.recorded_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if reranker_row and reranker_row.reranker_delta is not None:
                reranker_delta = round(reranker_row.reranker_delta, 4)
        except Exception:
            pass

        # Embedding health from space auditor
        silhouette_global = None
        inter_zone_distance = None
        hubness_rate = None
        try:
            space_health = await self.get_space_health(session)
            silhouette_global = space_health.global_silhouette
            if space_health.zone_metrics:
                inter_zone_distances = [
                    zm.inter_zone_min_distance
                    for zm in space_health.zone_metrics
                    if zm.inter_zone_min_distance is not None
                ]
                if inter_zone_distances:
                    inter_zone_distance = round(
                        sum(inter_zone_distances) / len(inter_zone_distances), 4
                    )
            if space_health.hubness_alerts and space_health.total_tools > 0:
                hubness_rate = round(
                    len(space_health.hubness_alerts) / space_health.total_tools, 4
                )
        except Exception:
            pass

        return {
            "band0_rate": round(band0_rate, 4),
            "ece_global": ece_report.global_ece,
            "ood_rate": round(ood_rate, 4),
            "namespace_purity": round(namespace_purity, 4),
            "platt_calibrated": self.platt_scaler.is_fitted,
            "total_events": total,
            "total_tools": tool_count,
            "total_hard_negatives": hn_count,
            "band_distribution": band_dist["distribution"],
            "band_percentages": band_dist["percentages"],
            "multi_intent_rate": round(multi_intent_rate, 4)
            if multi_intent_rate is not None
            else None,
            "schema_match_rate": round(namespace_purity, 4),
            "reranker_delta": reranker_delta,
            "silhouette_global": silhouette_global,
            "inter_zone_distance": inter_zone_distance,
            "hubness_rate": hubness_rate,
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
    # LLM Tool Judge — let an LLM pick the best tool from NEXUS candidates
    # ------------------------------------------------------------------

    async def llm_judge_tools(
        self,
        query: str,
        candidates: list[dict],
        *,
        top_k: int = 5,
    ) -> dict:
        """Ask an LLM to choose the best tool from NEXUS-ranked candidates.

        Args:
            query: The user query.
            candidates: NEXUS-ranked tool dicts with tool_id, name, description, score.
            top_k: How many top candidates to present to the LLM.

        Returns:
            Dict with chosen_tool, reasoning, nexus_rank_of_chosen, agreement.
        """
        from app.nexus.llm import nexus_llm_call

        shortlist = candidates[:top_k]
        if not shortlist:
            return {
                "chosen_tool": None,
                "reasoning": "Inga kandidater att bedöma.",
                "nexus_rank_of_chosen": -1,
                "agreement": False,
            }

        tool_lines = []
        for i, c in enumerate(shortlist, 1):
            score = c.get("score", c.get("calibrated_confidence", 0))
            tool_lines.append(
                f"{i}. {c.get('tool_id', c.get('name', '?'))} "
                f"(poäng {score:.3f}) — {c.get('description', '')[:120]}"
            )

        prompt = (
            f"Du är en verktygsväljare. Givet användarens fråga, välj ETT verktyg "
            f"från listan som bäst kan besvara frågan.\n\n"
            f"Fråga: {query}\n\n"
            f"Kandidater:\n" + "\n".join(tool_lines) + "\n\n"
            f"Svara EXAKT i detta format (inget annat):\n"
            f"VERKTYG: <tool_id>\n"
            f"MOTIVERING: <en mening>\n"
        )

        try:
            response = await nexus_llm_call(prompt)
            chosen_tool = None
            reasoning = ""
            for line in response.strip().splitlines():
                line_stripped = line.strip()
                if line_stripped.upper().startswith("VERKTYG:"):
                    chosen_tool = line_stripped.split(":", 1)[1].strip()
                elif line_stripped.upper().startswith("MOTIVERING:"):
                    reasoning = line_stripped.split(":", 1)[1].strip()

            # Find the NEXUS rank of the chosen tool
            nexus_rank = -1
            candidate_ids = [
                c.get("tool_id", c.get("name", "")) for c in shortlist
            ]
            if chosen_tool and chosen_tool in candidate_ids:
                nexus_rank = candidate_ids.index(chosen_tool) + 1
            elif chosen_tool:
                # Fuzzy match — LLM might return slightly different name
                for idx, cid in enumerate(candidate_ids):
                    if chosen_tool.lower() in cid.lower() or cid.lower() in chosen_tool.lower():
                        chosen_tool = cid  # Normalize to actual tool_id
                        nexus_rank = idx + 1
                        break

            nexus_top1 = candidate_ids[0] if candidate_ids else None
            agreement = chosen_tool == nexus_top1

            return {
                "chosen_tool": chosen_tool,
                "reasoning": reasoning,
                "nexus_rank_of_chosen": nexus_rank,
                "agreement": agreement,
            }
        except Exception as e:
            logger.warning("LLM judge failed: %s", e)
            return {
                "chosen_tool": None,
                "reasoning": f"LLM-anrop misslyckades: {e}",
                "nexus_rank_of_chosen": -1,
                "agreement": False,
            }

    # ------------------------------------------------------------------
    # Auto Loop Run (Sprint 5)
    # ------------------------------------------------------------------

    async def run_auto_loop(
        self,
        session: AsyncSession,
        *,
        category: str | None = None,
        tool_ids: list[str] | None = None,
        namespace: str | None = None,
        batch_size: int = 200,
        max_iterations: int = 1,
    ) -> dict:
        """Run a complete auto-loop iteration inline.

        Steps: Load ALL test cases → Route each (NEXUS + platform) → Compare → Cluster → Propose.

        Evaluates both NEXUS routing AND real platform routing
        (via smart_retrieve_tools_with_breakdown) to find discrepancies.

        Processes all matching test cases in batches and supports multiple
        iterations for re-evaluation after proposals are generated.

        Args:
            category: Optional category to filter test cases by (e.g. "smhi", "scb").
            tool_ids: Optional list of specific tool IDs to run on.
            namespace: Optional namespace prefix to filter by (e.g. "tools/weather").
            batch_size: Number of test cases to process per batch (default 200).
            max_iterations: Number of evaluation passes (default 1).
                           >1 allows re-evaluation after proposals are applied.
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

        # Build filtered query at DB level (no .limit — load ALL matching cases)
        stmt = select(NexusSyntheticCase)

        if tool_ids:
            stmt = stmt.where(NexusSyntheticCase.tool_id.in_(tool_ids))
        elif namespace:
            stmt = stmt.where(NexusSyntheticCase.namespace.startswith(namespace))
        elif category:
            from app.nexus.platform_bridge import get_platform_tools

            cat_tool_ids = list(
                {t.tool_id for t in get_platform_tools() if t.category == category}
            )
            if cat_tool_ids:
                stmt = stmt.where(NexusSyntheticCase.tool_id.in_(cat_tool_ids))
            else:
                stmt = stmt.where(False)  # No tools in category

        # Order by created_at to ensure consistent batching
        stmt = stmt.order_by(NexusSyntheticCase.created_at)

        result = await session.execute(stmt)
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

        total_case_count = len(cases)
        logger.info(
            "Auto-loop #%d: evaluating %d test cases in batches of %d (%d iterations)",
            loop_number,
            total_case_count,
            batch_size,
            max_iterations,
        )

        # Pre-warm embedding cache: batch-embed all query texts + tool texts
        # in efficient GPU passes BEFORE the eval loop starts.
        from app.nexus.config import get_all_zone_prefixes
        from app.nexus.embeddings import nexus_precompute
        from app.nexus.platform_bridge import get_platform_tools

        ZONE_PREFIXES = get_all_zone_prefixes()
        all_query_texts = [c.question.lower() for c in cases]
        # Also precompute zone-prefixed variants
        platform_tools = get_platform_tools()
        zone_prefixed_queries = set()
        for q in all_query_texts:
            zone_prefixed_queries.add(q)
            for prefix in ZONE_PREFIXES.values():
                zone_prefixed_queries.add(f"{prefix}{q}")
        tool_texts = set()
        for pt in platform_tools:
            if pt.category == "external_model":
                continue
            zone_prefix = ZONE_PREFIXES.get(pt.zone, "")
            # Match the exact format used by _build_tool_entries_from_platform
            kw_text = " ".join(pt.keywords[:8]) if pt.keywords else ""
            ex_text = " | ".join(pt.example_queries[:2]) if pt.example_queries else ""
            tool_texts.add(
                f"{zone_prefix}{pt.tool_id} {pt.description} {kw_text} {ex_text}".strip()
            )

        precompute_texts = list(zone_prefixed_queries | tool_texts)
        n_precomputed = nexus_precompute(precompute_texts)
        logger.info(
            "Auto-loop #%d: pre-computed %d embeddings (%d texts submitted)",
            loop_number,
            n_precomputed,
            len(precompute_texts),
        )

        # Cumulative metrics across all iterations
        all_iteration_results: list[dict] = []
        cumulative_failed_queries: list[dict] = []
        cumulative_proposals = []
        cumulative_root_causes: list[str] = []

        for iteration in range(1, max_iterations + 1):
            # Evaluate using both NEXUS routing and real platform retrieval
            total_tests = 0
            failures = 0
            failed_queries: list[dict] = []
            platform_comparisons = 0
            platform_agreements = 0
            band_counts = [0, 0, 0, 0, 0]
            correct_at_1 = 0
            correct_at_5 = 0
            reciprocal_ranks: list[float] = []
            llm_judge_total = 0
            llm_judge_agreements = 0
            llm_judge_correct = 0
            llm_judge_disagreements: list[dict] = []
            # Dual-sided accuracy quadrants
            both_correct = 0
            nexus_only_correct = 0
            llm_only_correct = 0
            both_wrong = 0
            # Platt calibration data — collect raw scores + labels
            platt_raw_scores: list[float] = []
            platt_labels: list[int] = []
            # 3-level accuracy: intent, agent, tool
            intent_correct = 0
            intent_total = 0
            agent_correct = 0
            agent_total = 0

            # --- Parallel evaluation helper --------------------------------
            # Each case gets its own DB session to avoid SQLAlchemy
            # AsyncSession concurrency issues.  The forge pool bounds
            # overall concurrency (default 12).

            from app.agents.new_chat.forge_pool import forge_pool
            from app.db import async_session_maker

            # Build tool description lookup for LLM judge
            _tool_desc_map: dict[str, str] = {
                pt.tool_id: pt.description
                for pt in platform_tools
                if pt.category != "external_model"
            }

            async def _eval_one_case(case_obj):
                """Evaluate a single test case (runs inside forge pool slot)."""
                async with async_session_maker() as case_session:
                    decision = await self.route_query(case_obj.question, case_session)
                    nexus_tool = decision.selected_tool
                    candidate_ids = [c.tool_id for c in decision.candidates]
                    # Capture raw top-1 score for Platt calibration fitting
                    raw_top1 = (
                        decision.candidates[0].raw_score
                        if decision.candidates
                        else 0.0
                    )

                    platform_result = await self.shadow_observer.run_platform_retrieval(
                        case_obj.question, session=case_session
                    )
                    platform_tool = platform_result.get("top1")

                    # LLM judge: let LLM pick from NEXUS candidates
                    llm_judge_result = None
                    if decision.candidates:
                        judge_candidates = [
                            {
                                "tool_id": c.tool_id,
                                "name": c.tool_id,
                                "description": _tool_desc_map.get(c.tool_id, ""),
                                "score": c.calibrated_score,
                            }
                            for c in decision.candidates[:5]
                        ]
                        llm_judge_result = await self.llm_judge_tools(
                            case_obj.question, judge_candidates, top_k=5
                        )

                    await case_session.commit()

                return {
                    "case": case_obj,
                    "nexus_tool": nexus_tool,
                    "band": decision.band,
                    "candidate_ids": candidate_ids,
                    "platform_tool": platform_tool,
                    "resolved_zone": decision.resolved_zone or "",
                    "selected_agent": decision.selected_agent or "",
                    "confidence": round(decision.calibrated_confidence, 3),
                    "llm_judge": llm_judge_result,
                    "raw_top1": raw_top1,
                    "sub_queries": decision.query_analysis.sub_queries if decision.query_analysis else [],
                }

            # Process in batches — each batch runs concurrently via forge pool
            for batch_start in range(0, len(cases), batch_size):
                batch = cases[batch_start : batch_start + batch_size]
                logger.info(
                    "Auto-loop #%d iter %d: batch %d-%d / %d (concurrency=%d)",
                    loop_number,
                    iteration,
                    batch_start + 1,
                    min(batch_start + len(batch), len(cases)),
                    len(cases),
                    forge_pool.max_concurrency,
                )

                # Run all cases in this batch concurrently
                batch_results = await forge_pool.gather(
                    [_eval_one_case(c) for c in batch],
                    label=f"auto_loop_iter{iteration}",
                )

                for br in batch_results:
                    total_tests += 1

                    if isinstance(br, BaseException):
                        failures += 1
                        logger.warning("Loop eval error: %s", br)
                        continue

                    case_obj = br["case"]
                    nexus_tool = br["nexus_tool"]
                    band_counts[min(br["band"], 4)] += 1

                    # 3-level accuracy: intent and agent
                    exp_intent = getattr(case_obj, "expected_intent", None)
                    exp_agent = getattr(case_obj, "expected_agent", None)
                    if exp_intent:
                        intent_total += 1
                        if br["resolved_zone"] == exp_intent:
                            intent_correct += 1
                    if exp_agent:
                        agent_total += 1
                        if br["selected_agent"] == exp_agent:
                            agent_correct += 1

                    candidate_ids = br["candidate_ids"]
                    if case_obj.expected_tool:
                        is_correct = nexus_tool == case_obj.expected_tool
                        if is_correct:
                            correct_at_1 += 1
                        # Collect data for Platt calibration fitting
                        platt_raw_scores.append(br.get("raw_top1", 0.0))
                        platt_labels.append(1 if is_correct else 0)
                        if case_obj.expected_tool in candidate_ids[:5]:
                            correct_at_5 += 1
                        if case_obj.expected_tool in candidate_ids:
                            rank = candidate_ids.index(case_obj.expected_tool) + 1
                            reciprocal_ranks.append(1.0 / rank)
                        else:
                            reciprocal_ranks.append(0.0)

                    platform_tool = br["platform_tool"]
                    if platform_tool:
                        platform_comparisons += 1
                        if nexus_tool == platform_tool:
                            platform_agreements += 1

                    # LLM judge tracking
                    llm_judge = br.get("llm_judge")
                    if llm_judge and llm_judge.get("chosen_tool"):
                        llm_judge_total += 1
                        llm_chosen = llm_judge["chosen_tool"]
                        if llm_chosen == nexus_tool:
                            llm_judge_agreements += 1
                        if case_obj.expected_tool and llm_chosen == case_obj.expected_tool:
                            llm_judge_correct += 1

                        # Dual-sided accuracy: who was right?
                        if case_obj.expected_tool:
                            n_right = nexus_tool == case_obj.expected_tool
                            l_right = llm_chosen == case_obj.expected_tool
                            if n_right and l_right:
                                both_correct += 1
                            elif n_right and not l_right:
                                nexus_only_correct += 1
                            elif not n_right and l_right:
                                llm_only_correct += 1
                            else:
                                both_wrong += 1

                        if llm_chosen != nexus_tool:
                            # Determine winner for this disagreement
                            winner = "tie"
                            if case_obj.expected_tool:
                                if nexus_tool == case_obj.expected_tool:
                                    winner = "nexus"
                                elif llm_chosen == case_obj.expected_tool:
                                    winner = "llm"
                                else:
                                    winner = "neither"
                            llm_judge_disagreements.append({
                                "query": case_obj.question,
                                "nexus_tool": nexus_tool or "(none)",
                                "llm_tool": llm_chosen,
                                "expected_tool": case_obj.expected_tool or "(unknown)",
                                "reasoning": llm_judge.get("reasoning", ""),
                                "nexus_rank_of_chosen": llm_judge.get("nexus_rank_of_chosen", -1),
                                "winner": winner,
                            })

                    if case_obj.expected_tool and nexus_tool != case_obj.expected_tool:
                        failures += 1
                        failed_queries.append(
                            {
                                "query": case_obj.question,
                                "expected_tool": case_obj.expected_tool,
                                "got_tool": nexus_tool or "(none)",
                                "platform_tool": platform_tool or "(none)",
                                "case_id": str(case_obj.id),
                                "resolved_zone": br["resolved_zone"],
                                "selected_agent": br["selected_agent"],
                                "band": br["band"],
                                "confidence": br["confidence"],
                                "difficulty": getattr(case_obj, "difficulty", ""),
                                "llm_judge_tool": (
                                    llm_judge.get("chosen_tool")
                                    if llm_judge
                                    else None
                                ),
                                "llm_judge_reasoning": (
                                    llm_judge.get("reasoning", "")
                                    if llm_judge
                                    else ""
                                ),
                                "sub_queries": br.get("sub_queries", []),
                            }
                        )

            # Per-iteration metrics
            p_at_1 = correct_at_1 / total_tests if total_tests > 0 else 0.0
            p_at_5 = correct_at_5 / total_tests if total_tests > 0 else 0.0
            mrr = (
                sum(reciprocal_ranks) / len(reciprocal_ranks)
                if reciprocal_ranks
                else 0.0
            )

            llm_judge_agreement_rate = (
                llm_judge_agreements / llm_judge_total
                if llm_judge_total > 0
                else None
            )
            llm_judge_accuracy = (
                llm_judge_correct / llm_judge_total
                if llm_judge_total > 0
                else None
            )

            iter_result = {
                "iteration": iteration,
                "total_tests": total_tests,
                "failures": failures,
                "precision_at_1": round(p_at_1, 3),
                "precision_at_5": round(p_at_5, 3),
                "mrr": round(mrr, 3),
                "band_distribution": band_counts,
                "platform_comparisons": platform_comparisons,
                "platform_agreements": platform_agreements,
                "llm_judge_total": llm_judge_total,
                "llm_judge_agreements": llm_judge_agreements,
                "llm_judge_correct": llm_judge_correct,
                "llm_judge_agreement_rate": (
                    round(llm_judge_agreement_rate, 3)
                    if llm_judge_agreement_rate is not None
                    else None
                ),
                "llm_judge_accuracy": (
                    round(llm_judge_accuracy, 3)
                    if llm_judge_accuracy is not None
                    else None
                ),
                "llm_judge_disagreements": llm_judge_disagreements[:20],
                "both_correct": both_correct,
                "nexus_only_correct": nexus_only_correct,
                "llm_only_correct": llm_only_correct,
                "both_wrong": both_wrong,
                "intent_correct": intent_correct,
                "intent_total": intent_total,
                "intent_accuracy": (
                    round(intent_correct / intent_total, 3) if intent_total > 0 else None
                ),
                "agent_correct": agent_correct,
                "agent_total": agent_total,
                "agent_accuracy": (
                    round(agent_correct / agent_total, 3) if agent_total > 0 else None
                ),
            }
            all_iteration_results.append(iter_result)

            logger.info(
                "Auto-loop #%d iter %d: %d/%d failures (P@1=%.3f, LLM-agree=%.1f%%)",
                loop_number,
                iteration,
                failures,
                total_tests,
                p_at_1,
                (llm_judge_agreement_rate or 0) * 100,
            )

            # Cluster failures and create proposals
            clusters = self.auto_loop.cluster_failures(failed_queries)

            # LLM root cause analysis per cluster — parallel via forge pool
            root_causes: list[str] = []
            try:
                from app.nexus.llm import nexus_llm_call

                async def _root_cause_for_cluster(cluster_obj):
                    if not cluster_obj.sample_queries:
                        return ""
                    rc_prompt = (
                        f"Analysera varför dessa frågor routades fel.\n"
                        f"Förväntade verktyg: {', '.join(cluster_obj.tool_ids)}\n"
                        f"Exempelfrågor:\n"
                        + "\n".join(f"- {q}" for q in cluster_obj.sample_queries[:3])
                        + "\n\nSvara med EN mening som förklarar rotorsaken."
                    )
                    try:
                        result_text = await nexus_llm_call(rc_prompt)
                        return result_text.strip()
                    except Exception as e:
                        logger.warning(
                            "LLM root cause failed for cluster %d: %s",
                            cluster_obj.cluster_id,
                            e,
                        )
                        return ""

                rc_results = await forge_pool.gather(
                    [_root_cause_for_cluster(c) for c in clusters],
                    label="root_cause",
                )
                root_causes = [r if isinstance(r, str) else "" for r in rc_results]
            except ImportError:
                logger.warning("LLM not available for root cause analysis")

            proposals = self.auto_loop.create_proposals(
                clusters, root_causes=root_causes or None
            )

            cumulative_failed_queries.extend(failed_queries)
            cumulative_proposals.extend(proposals)
            cumulative_root_causes.extend(root_causes)

            # ── Auto-fit Platt calibration after first iteration ──────────
            # The first pass gives us (raw_score, correct/incorrect) pairs —
            # exactly what Platt sigmoid needs.  Fitting once makes band
            # thresholds meaningful for subsequent iterations.
            if iteration == 1 and not self.platt_scaler.is_fitted and len(platt_raw_scores) >= 10:
                try:
                    self.platt_scaler.fit(platt_raw_scores, platt_labels)
                    logger.info(
                        "Auto-loop #%d: Auto-fitted Platt calibration from %d samples",
                        loop_number, len(platt_raw_scores),
                    )
                except Exception as e:
                    logger.warning("Auto-loop Platt fitting failed: %s", e)

            # If no failures or last iteration, stop iterating
            if failures == 0 or iteration == max_iterations:
                break

            # ── Apply optimizer suggestions between iterations ────────
            # Run MetadataOptimizer on namespaces of confused tools, apply
            # changes to DB, populate proposed_value, and clear caches so
            # the next iteration evaluates against updated metadata.
            try:
                from app.nexus.embeddings import nexus_clear_embed_cache
                from app.nexus.optimizer import MetadataOptimizer
                from app.nexus.platform_bridge import (
                    apply_overrides_to_cache,
                    get_platform_tools as _get_pt,
                )

                # Map tool_id → namespace string for failed tools
                tool_ns_map: dict[str, str] = {}
                for pt in _get_pt():
                    tool_ns_map[pt.tool_id] = "/".join(pt.namespace[:2])

                # Collect unique namespaces from proposals
                ns_set: set[str] = set()
                for p in proposals:
                    ns = tool_ns_map.get(p.tool_id, "")
                    if ns:
                        ns_set.add(ns)

                optimizer = MetadataOptimizer()
                applied_tool_ids: set[str] = set()
                # Collect all overrides to patch in-memory cache
                memory_overrides: dict[str, dict] = {}

                for ns in ns_set:
                    try:
                        opt_result = await optimizer.generate_suggestions(
                            session, namespace=ns,
                            llm_config_id=-1,  # Use local model in loop (cost control)
                        )
                        if opt_result.suggestions:
                            # Apply to DB
                            apply_list = [
                                {
                                    "tool_id": s.tool_id,
                                    **s.suggested,
                                }
                                for s in opt_result.suggestions
                                if s.suggested.get("description")
                            ]
                            if apply_list:
                                await optimizer.apply_suggestions(
                                    session, apply_list
                                )
                                await session.commit()

                            # Collect overrides + update proposed_value on proposals
                            for s in opt_result.suggestions:
                                if s.suggested.get("description"):
                                    memory_overrides[s.tool_id] = s.suggested
                                    applied_tool_ids.add(s.tool_id)
                            desc_map = {
                                tid: ov.get("description", "")
                                for tid, ov in memory_overrides.items()
                            }
                            for p in proposals:
                                if p.tool_id in desc_map:
                                    p.proposed_value = desc_map[p.tool_id]
                    except Exception as e:
                        logger.warning(
                            "Auto-loop optimizer failed for ns=%s: %s", ns, e
                        )

                if applied_tool_ids:
                    # Patch in-memory tool cache so route_query sees new metadata
                    apply_overrides_to_cache(memory_overrides)
                    # Clear embedding cache so next iteration uses new metadata
                    nexus_clear_embed_cache()
                    # Re-precompute embeddings for updated tools — match the
                    # exact text format used by _build_tool_entries_from_platform
                    updated_tools = [
                        pt
                        for pt in _get_pt()
                        if pt.tool_id in applied_tool_ids
                    ]
                    recompute_texts = []
                    for pt in updated_tools:
                        zone_prefix = ZONE_PREFIXES.get(pt.zone, "")
                        kw_text = " ".join(pt.keywords[:8]) if pt.keywords else ""
                        ex_text = (
                            " | ".join(pt.example_queries[:2])
                            if pt.example_queries
                            else ""
                        )
                        full_text = (
                            f"{zone_prefix}{pt.tool_id} {pt.description}"
                            f" {kw_text} {ex_text}".strip()
                        )
                        recompute_texts.append(full_text)
                    if recompute_texts:
                        nexus_precompute(recompute_texts)

                    logger.info(
                        "Auto-loop #%d iter %d: applied optimizer suggestions "
                        "for %d tools, cleared embedding cache",
                        loop_number,
                        iteration,
                        len(applied_tool_ids),
                    )
            except Exception as e:
                logger.warning(
                    "Auto-loop inter-iteration optimizer failed: %s", e
                )

        # Use last iteration's values for final metrics
        last_iter = all_iteration_results[-1]
        final_p_at_1 = last_iter["precision_at_1"]
        final_p_at_5 = last_iter["precision_at_5"]
        final_mrr = last_iter["mrr"]
        final_band_counts = last_iter["band_distribution"]
        final_total_tests = last_iter["total_tests"]
        final_failures = last_iter["failures"]
        final_platform_comparisons = last_iter["platform_comparisons"]
        final_platform_agreements = last_iter["platform_agreements"]

        # Compute real embedding delta for each proposal
        try:
            from app.nexus.embeddings import nexus_embed_score

            for proposal in cumulative_proposals:
                if proposal.current_value and proposal.proposed_value:
                    current_score = nexus_embed_score(
                        proposal.tool_id, proposal.current_value
                    )
                    proposed_score = nexus_embed_score(
                        proposal.tool_id, proposal.proposed_value
                    )
                    if current_score is not None and proposed_score is not None:
                        proposal.embedding_delta = proposed_score - current_score
        except Exception as e:
            logger.warning("Embedding delta computation failed: %s", e)

        # Mine hard negatives from confusion pairs in failures
        if cumulative_failed_queries:
            confusion_data = [
                {
                    "tool_a": fq.get("expected_tool", ""),
                    "tool_b": fq.get("got_tool", ""),
                    "similarity": 0.85,
                }
                for fq in cumulative_failed_queries
                if fq.get("expected_tool") and fq.get("got_tool")
            ]
            hn_result = self.hard_negative_miner.mine_from_confusion(confusion_data)
            logger.info(
                "Hard negative mining: %d total, %d new pairs",
                hn_result.total_pairs,
                hn_result.new_pairs,
            )

            # Persist hard negatives to DB
            for pair in self.hard_negative_miner.pairs:
                try:
                    existing = await session.execute(
                        select(NexusHardNegative).where(
                            NexusHardNegative.anchor_tool == pair.anchor_tool,
                            NexusHardNegative.negative_tool == pair.negative_tool,
                        )
                    )
                    if not existing.scalars().first():
                        session.add(
                            NexusHardNegative(
                                anchor_tool=pair.anchor_tool,
                                negative_tool=pair.negative_tool,
                                mining_method=pair.mining_method,
                                similarity_score=pair.similarity_score,
                                confusion_frequency=pair.confusion_frequency,
                            )
                        )
                except Exception:
                    pass  # Unique constraint violation — already exists

        # Compute overall embedding delta
        total_embedding_delta = (
            sum(p.embedding_delta for p in cumulative_proposals)
            / len(cumulative_proposals)
            if cumulative_proposals
            else 0.0
        )

        # Persist pipeline metrics to the ledger — all 5 stages per vision
        # (1=intent, 2=route, 3=bigtool, 4=rerank, 5=e2e)
        if final_total_tests >= 3:
            reranker_delta = (
                (final_platform_agreements / final_platform_comparisons - final_p_at_1)
                if final_platform_comparisons > 0
                else None
            )
            hn_precision = (
                final_platform_agreements / final_platform_comparisons
                if final_platform_comparisons > 0
                else None
            )
            metric_stages = [
                (
                    1,
                    "intent",
                    final_p_at_1,
                    final_p_at_5,
                    final_mrr,
                    final_mrr,
                    None,
                    None,
                ),
                (
                    2,
                    "route",
                    final_p_at_1,
                    final_p_at_5,
                    final_mrr,
                    final_mrr,
                    None,
                    None,
                ),
                (
                    3,
                    "bigtool",
                    final_p_at_5,
                    final_p_at_5,
                    final_mrr,
                    final_mrr,
                    hn_precision,
                    None,
                ),
                (
                    4,
                    "rerank",
                    final_p_at_1,
                    final_p_at_5,
                    final_mrr,
                    final_mrr,
                    hn_precision,
                    reranker_delta,
                ),
                (
                    5,
                    "e2e",
                    final_p_at_1,
                    final_p_at_5,
                    final_mrr,
                    final_mrr,
                    None,
                    None,
                ),
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
        db_run.total_tests = final_total_tests
        db_run.failures = final_failures
        # Build enriched proposals with failed queries per tool
        enriched_proposals = []
        for p in cumulative_proposals:
            # Find failed queries related to this proposal's tool
            related_queries = [
                fq
                for fq in cumulative_failed_queries
                if fq.get("expected_tool") == p.tool_id
                or fq.get("got_tool") == p.tool_id
            ]
            enriched_proposals.append(
                {
                    "tool_id": p.tool_id,
                    "field": p.field_name,
                    "reason": p.reason,
                    "current_value": p.current_value or "",
                    "proposed_value": p.proposed_value or "",
                    "embedding_delta": round(p.embedding_delta, 4)
                    if p.embedding_delta
                    else 0.0,
                    "failed_queries": [
                        {
                            "query": fq.get("query", ""),
                            "expected_tool": fq.get("expected_tool", ""),
                            "got_tool": fq.get("got_tool", ""),
                            "resolved_zone": fq.get("resolved_zone", ""),
                            "selected_agent": fq.get("selected_agent", ""),
                            "band": fq.get("band", -1),
                            "confidence": fq.get("confidence", 0.0),
                            "difficulty": fq.get("difficulty", ""),
                            "llm_judge_tool": fq.get("llm_judge_tool"),
                            "llm_judge_reasoning": fq.get("llm_judge_reasoning", ""),
                        }
                        for fq in related_queries[:10]  # Cap at 10 queries per proposal
                    ],
                }
            )

        # Aggregate LLM judge stats from all iterations
        llm_judge_summary = None
        all_disagreements: list[dict] = []
        total_llm_total = 0
        total_llm_agree = 0
        total_llm_correct = 0
        for ir in all_iteration_results:
            total_llm_total += ir.get("llm_judge_total", 0)
            total_llm_agree += ir.get("llm_judge_agreements", 0)
            total_llm_correct += ir.get("llm_judge_correct", 0)
            all_disagreements.extend(ir.get("llm_judge_disagreements", []))
        if total_llm_total > 0:
            # Aggregate quadrants from all iterations
            total_both_correct = sum(ir.get("both_correct", 0) for ir in all_iteration_results)
            total_nexus_only = sum(ir.get("nexus_only_correct", 0) for ir in all_iteration_results)
            total_llm_only = sum(ir.get("llm_only_correct", 0) for ir in all_iteration_results)
            total_both_wrong = sum(ir.get("both_wrong", 0) for ir in all_iteration_results)
            nexus_accuracy = (
                round((total_both_correct + total_nexus_only) / total_llm_total, 3)
            )
            llm_accuracy = (
                round((total_both_correct + total_llm_only) / total_llm_total, 3)
            )
            llm_judge_summary = {
                "total": total_llm_total,
                "agreements": total_llm_agree,
                "correct": total_llm_correct,
                "agreement_rate": round(total_llm_agree / total_llm_total, 3),
                "accuracy": round(total_llm_correct / total_llm_total, 3),
                "nexus_accuracy": nexus_accuracy,
                "llm_accuracy": llm_accuracy,
                "both_correct": total_both_correct,
                "nexus_only_correct": total_nexus_only,
                "llm_only_correct": total_llm_only,
                "both_wrong": total_both_wrong,
                "disagreements": all_disagreements[:30],
            }

        db_run.metadata_proposals = {
            "proposals": enriched_proposals,
            "platform_comparisons": final_platform_comparisons,
            "platform_agreements": final_platform_agreements,
            "band_distribution": final_band_counts,
            "iterations": all_iteration_results,
            "total_cases_available": total_case_count,
            "llm_judge": llm_judge_summary,
        }
        db_run.approved_proposals = 0
        db_run.embedding_delta = total_embedding_delta
        db_run.status = "review" if cumulative_proposals else "approved"
        db_run.completed_at = datetime.now(tz=UTC)
        await session.commit()

        return {
            "status": "completed",
            "run_id": str(run_id),
            "loop_number": loop_number,
            "total_tests": final_total_tests,
            "total_cases_available": total_case_count,
            "iterations_completed": len(all_iteration_results),
            "failures": final_failures,
            "proposals": len(cumulative_proposals),
            "embedding_delta": round(total_embedding_delta, 4),
            "root_causes": cumulative_root_causes,
            "hard_negatives_mined": self.hard_negative_miner.get_stats().get(
                "total_pairs", 0
            ),
            "platform_comparisons": final_platform_comparisons,
            "platform_agreements": final_platform_agreements,
            "platform_agreement_rate": (
                round(final_platform_agreements / final_platform_comparisons, 3)
                if final_platform_comparisons > 0
                else None
            ),
            "precision_at_1": final_p_at_1,
            "precision_at_5": final_p_at_5,
            "mrr": final_mrr,
            "band_distribution": final_band_counts,
            "iteration_details": all_iteration_results,
        }

    async def run_auto_loop_stream(
        self,
        session: AsyncSession,
        *,
        category: str | None = None,
        tool_ids: list[str] | None = None,
        namespace: str | None = None,
        batch_size: int = 200,
        max_iterations: int = 1,
    ):
        """Run auto-loop with SSE progress events.

        Yields dicts with ``type`` in {progress, batch, iteration, done, error}.
        """
        import uuid

        now = datetime.now(tz=UTC)

        run_count = (
            await session.scalar(select(func.count()).select_from(NexusAutoLoopRun))
            or 0
        )
        loop_number = run_count + 1
        run_id = uuid.uuid4()

        db_run = NexusAutoLoopRun(
            id=run_id,
            loop_number=loop_number,
            started_at=now,
            status="running",
        )
        session.add(db_run)
        await session.flush()

        yield {
            "type": "progress",
            "step": "init",
            "detail": f"Loop #{loop_number} startad",
            "run_id": str(run_id),
            "loop_number": loop_number,
        }

        # Build filtered query (same as run_auto_loop)
        stmt = select(NexusSyntheticCase)
        if tool_ids:
            stmt = stmt.where(NexusSyntheticCase.tool_id.in_(tool_ids))
        elif namespace:
            stmt = stmt.where(NexusSyntheticCase.namespace.startswith(namespace))
        elif category:
            from app.nexus.platform_bridge import get_platform_tools

            cat_tool_ids = list(
                {t.tool_id for t in get_platform_tools() if t.category == category}
            )
            if cat_tool_ids:
                stmt = stmt.where(NexusSyntheticCase.tool_id.in_(cat_tool_ids))
            else:
                stmt = stmt.where(False)

        stmt = stmt.order_by(NexusSyntheticCase.created_at)
        result = await session.execute(stmt)
        cases = result.scalars().all()

        if not cases:
            db_run.status = "failed"
            db_run.completed_at = datetime.now(tz=UTC)
            await session.commit()
            yield {
                "type": "error",
                "message": "Inga testfall hittade. Kör forge/generate först.",
            }
            return

        total_case_count = len(cases)
        yield {
            "type": "progress",
            "step": "loaded",
            "detail": f"{total_case_count} testfall laddade",
            "total_cases": total_case_count,
            "max_iterations": max_iterations,
            "batch_size": batch_size,
        }

        # Pre-warm embedding cache: batch-embed all texts in efficient GPU passes
        yield {
            "type": "progress",
            "step": "precompute",
            "detail": "Forbereder embeddings (batch GPU)...",
        }

        from app.nexus.config import get_all_zone_prefixes
        from app.nexus.embeddings import nexus_precompute
        from app.nexus.platform_bridge import get_platform_tools as _get_pt

        ZONE_PREFIXES = get_all_zone_prefixes()
        _pt_tools = _get_pt()
        all_query_texts = [c.question.lower() for c in cases]
        zone_prefixed_queries = set()
        for q in all_query_texts:
            zone_prefixed_queries.add(q)
            for prefix in ZONE_PREFIXES.values():
                zone_prefixed_queries.add(f"{prefix}{q}")
        tool_texts = set()
        for pt in _pt_tools:
            if pt.category == "external_model":
                continue
            zp = ZONE_PREFIXES.get(pt.zone, "")
            # Match the exact format used by _build_tool_entries_from_platform
            kw_text = " ".join(pt.keywords[:8]) if pt.keywords else ""
            ex_text = " | ".join(pt.example_queries[:2]) if pt.example_queries else ""
            tool_texts.add(
                f"{zp}{pt.tool_id} {pt.description} {kw_text} {ex_text}".strip()
            )

        precompute_texts = list(zone_prefixed_queries | tool_texts)
        n_precomputed = nexus_precompute(precompute_texts)

        yield {
            "type": "progress",
            "step": "precompute_done",
            "detail": f"{n_precomputed} embeddings forberaknade (av {len(precompute_texts)})",
        }

        from app.agents.new_chat.forge_pool import forge_pool
        from app.db import async_session_maker

        all_iteration_results: list[dict] = []
        cumulative_failed_queries: list[dict] = []
        cumulative_proposals = []
        cumulative_root_causes: list[str] = []

        # Tool description lookup for LLM judge — mutable dict so it can be
        # refreshed between iterations when the optimizer patches tools.
        _tool_desc_map: dict[str, str] = {
            pt.tool_id: pt.description
            for pt in _pt_tools
            if pt.category != "external_model"
        }

        async def _eval_one_case(case_obj):
            async with async_session_maker() as case_session:
                decision = await self.route_query(case_obj.question, case_session)
                nexus_tool = decision.selected_tool
                candidate_ids = [c.tool_id for c in decision.candidates]
                raw_top1 = (
                    decision.candidates[0].raw_score
                    if decision.candidates
                    else 0.0
                )
                platform_result = await self.shadow_observer.run_platform_retrieval(
                    case_obj.question, session=case_session
                )
                platform_tool = platform_result.get("top1")

                # LLM judge: let LLM pick from NEXUS candidates
                llm_judge_result = None
                if decision.candidates:
                    judge_candidates = [
                        {
                            "tool_id": c.tool_id,
                            "name": c.tool_id,
                            "description": _tool_desc_map.get(c.tool_id, ""),
                            "score": c.calibrated_score,
                        }
                        for c in decision.candidates[:5]
                    ]
                    llm_judge_result = await self.llm_judge_tools(
                        case_obj.question, judge_candidates, top_k=5
                    )

                await case_session.commit()
            return {
                "case": case_obj,
                "nexus_tool": nexus_tool,
                "band": decision.band,
                "candidate_ids": candidate_ids,
                "platform_tool": platform_tool,
                "resolved_zone": decision.resolved_zone or "",
                "selected_agent": decision.selected_agent or "",
                "confidence": round(decision.calibrated_confidence, 3),
                "llm_judge": llm_judge_result,
                "raw_top1": raw_top1,
                "sub_queries": decision.query_analysis.sub_queries if decision.query_analysis else [],
            }

        for iteration in range(1, max_iterations + 1):
            # Refresh tool description map (picks up optimizer patches)
            _tool_desc_map.clear()
            _tool_desc_map.update({
                pt.tool_id: pt.description
                for pt in _get_pt()
                if pt.category != "external_model"
            })
            yield {
                "type": "progress",
                "step": "eval_start",
                "detail": f"Iteration {iteration}/{max_iterations} — evaluerar",
                "iteration": iteration,
                "total_iterations": max_iterations,
            }

            total_tests = 0
            failures = 0
            failed_queries: list[dict] = []
            platform_comparisons = 0
            platform_agreements = 0
            band_counts = [0, 0, 0, 0, 0]
            correct_at_1 = 0
            correct_at_5 = 0
            reciprocal_ranks: list[float] = []
            llm_judge_total = 0
            llm_judge_agreements = 0
            llm_judge_correct = 0
            llm_judge_disagreements: list[dict] = []
            # Dual-sided accuracy quadrants
            both_correct = 0
            nexus_only_correct = 0
            llm_only_correct = 0
            both_wrong = 0
            # Platt calibration data
            platt_raw_scores: list[float] = []
            platt_labels: list[int] = []
            # 3-level accuracy: intent, agent, tool
            intent_correct = 0
            intent_total = 0
            agent_correct = 0
            agent_total = 0

            num_batches = (len(cases) + batch_size - 1) // batch_size
            for batch_idx, batch_start in enumerate(
                range(0, len(cases), batch_size)
            ):
                batch = cases[batch_start : batch_start + batch_size]

                yield {
                    "type": "batch",
                    "step": "eval_batch",
                    "detail": f"Batch {batch_idx + 1}/{num_batches} ({len(batch)} fall)",
                    "iteration": iteration,
                    "batch": batch_idx + 1,
                    "total_batches": num_batches,
                    "cases_processed": batch_start,
                    "total_cases": total_case_count,
                }

                batch_results = await forge_pool.gather(
                    [_eval_one_case(c) for c in batch],
                    label=f"auto_loop_stream_iter{iteration}",
                )

                for br in batch_results:
                    total_tests += 1
                    if isinstance(br, BaseException):
                        failures += 1
                        continue
                    case_obj = br["case"]
                    nexus_tool = br["nexus_tool"]
                    band_counts[min(br["band"], 4)] += 1
                    candidate_ids = br["candidate_ids"]
                    if case_obj.expected_tool:
                        is_correct = nexus_tool == case_obj.expected_tool
                        if is_correct:
                            correct_at_1 += 1
                        platt_raw_scores.append(br.get("raw_top1", 0.0))
                        platt_labels.append(1 if is_correct else 0)
                        if case_obj.expected_tool in candidate_ids[:5]:
                            correct_at_5 += 1
                        if case_obj.expected_tool in candidate_ids:
                            rank = candidate_ids.index(case_obj.expected_tool) + 1
                            reciprocal_ranks.append(1.0 / rank)
                        else:
                            reciprocal_ranks.append(0.0)
                    platform_tool = br["platform_tool"]
                    if platform_tool:
                        platform_comparisons += 1
                        if nexus_tool == platform_tool:
                            platform_agreements += 1
                    # LLM judge tracking
                    llm_judge = br.get("llm_judge")
                    if llm_judge and llm_judge.get("chosen_tool"):
                        llm_judge_total += 1
                        llm_chosen = llm_judge["chosen_tool"]
                        if llm_chosen == nexus_tool:
                            llm_judge_agreements += 1
                        if case_obj.expected_tool and llm_chosen == case_obj.expected_tool:
                            llm_judge_correct += 1

                        # Dual-sided accuracy: who was right?
                        if case_obj.expected_tool:
                            n_right = nexus_tool == case_obj.expected_tool
                            l_right = llm_chosen == case_obj.expected_tool
                            if n_right and l_right:
                                both_correct += 1
                            elif n_right and not l_right:
                                nexus_only_correct += 1
                            elif not n_right and l_right:
                                llm_only_correct += 1
                            else:
                                both_wrong += 1

                        if llm_chosen != nexus_tool:
                            # Determine winner for this disagreement
                            winner = "tie"
                            if case_obj.expected_tool:
                                if nexus_tool == case_obj.expected_tool:
                                    winner = "nexus"
                                elif llm_chosen == case_obj.expected_tool:
                                    winner = "llm"
                                else:
                                    winner = "neither"
                            llm_judge_disagreements.append({
                                "query": case_obj.question,
                                "nexus_tool": nexus_tool or "(none)",
                                "llm_tool": llm_chosen,
                                "expected_tool": case_obj.expected_tool or "(unknown)",
                                "reasoning": llm_judge.get("reasoning", ""),
                                "nexus_rank_of_chosen": llm_judge.get("nexus_rank_of_chosen", -1),
                                "winner": winner,
                            })

                    if case_obj.expected_tool and nexus_tool != case_obj.expected_tool:
                        failures += 1
                        failed_queries.append(
                            {
                                "query": case_obj.question,
                                "expected_tool": case_obj.expected_tool,
                                "got_tool": nexus_tool or "(none)",
                                "platform_tool": platform_tool or "(none)",
                                "case_id": str(case_obj.id),
                                "resolved_zone": br["resolved_zone"],
                                "selected_agent": br["selected_agent"],
                                "band": br["band"],
                                "confidence": br["confidence"],
                                "difficulty": getattr(case_obj, "difficulty", ""),
                                "llm_judge_tool": (
                                    llm_judge.get("chosen_tool")
                                    if llm_judge
                                    else None
                                ),
                                "llm_judge_reasoning": (
                                    llm_judge.get("reasoning", "")
                                    if llm_judge
                                    else ""
                                ),
                                "sub_queries": br.get("sub_queries", []),
                            }
                        )

            p_at_1 = correct_at_1 / total_tests if total_tests > 0 else 0.0
            p_at_5 = correct_at_5 / total_tests if total_tests > 0 else 0.0
            mrr = (
                sum(reciprocal_ranks) / len(reciprocal_ranks)
                if reciprocal_ranks
                else 0.0
            )

            llm_judge_agreement_rate = (
                llm_judge_agreements / llm_judge_total
                if llm_judge_total > 0
                else None
            )
            llm_judge_accuracy = (
                llm_judge_correct / llm_judge_total
                if llm_judge_total > 0
                else None
            )

            iter_result = {
                "iteration": iteration,
                "total_tests": total_tests,
                "failures": failures,
                "precision_at_1": round(p_at_1, 3),
                "precision_at_5": round(p_at_5, 3),
                "mrr": round(mrr, 3),
                "band_distribution": band_counts,
                "platform_comparisons": platform_comparisons,
                "platform_agreements": platform_agreements,
                "llm_judge_total": llm_judge_total,
                "llm_judge_agreements": llm_judge_agreements,
                "llm_judge_correct": llm_judge_correct,
                "llm_judge_agreement_rate": (
                    round(llm_judge_agreement_rate, 3)
                    if llm_judge_agreement_rate is not None
                    else None
                ),
                "llm_judge_accuracy": (
                    round(llm_judge_accuracy, 3)
                    if llm_judge_accuracy is not None
                    else None
                ),
                "llm_judge_disagreements": llm_judge_disagreements[:20],
                "both_correct": both_correct,
                "nexus_only_correct": nexus_only_correct,
                "llm_only_correct": llm_only_correct,
                "both_wrong": both_wrong,
                "intent_correct": intent_correct,
                "intent_total": intent_total,
                "intent_accuracy": (
                    round(intent_correct / intent_total, 3) if intent_total > 0 else None
                ),
                "agent_correct": agent_correct,
                "agent_total": agent_total,
                "agent_accuracy": (
                    round(agent_correct / agent_total, 3) if agent_total > 0 else None
                ),
            }
            all_iteration_results.append(iter_result)

            yield {
                "type": "iteration",
                "step": "eval_done",
                "detail": (
                    f"Iteration {iteration} klar — {failures}/{total_tests} fel, "
                    f"P@1={p_at_1:.1%}"
                    + (f", Intent={intent_correct}/{intent_total}" if intent_total > 0 else "")
                    + (f", Agent={agent_correct}/{agent_total}" if agent_total > 0 else "")
                ),
                "iteration": iteration,
                "total_iterations": max_iterations,
                "failures": failures,
                "total_tests": total_tests,
                "precision_at_1": round(p_at_1, 3),
                "mrr": round(mrr, 3),
                "intent_accuracy": (
                    round(intent_correct / intent_total, 3) if intent_total > 0 else None
                ),
                "agent_accuracy": (
                    round(agent_correct / agent_total, 3) if agent_total > 0 else None
                ),
            }

            # Emit LLM judge summary event per iteration
            if llm_judge_total > 0:
                yield {
                    "type": "progress",
                    "step": "llm_judge",
                    "detail": (
                        f"LLM-judge: {llm_judge_agreements}/{llm_judge_total} överens med NEXUS "
                        f"({((llm_judge_agreement_rate or 0) * 100):.0f}%), "
                        f"LLM korrekt: {llm_judge_correct}/{llm_judge_total}"
                    ),
                    "iteration": iteration,
                    "llm_judge_total": llm_judge_total,
                    "llm_judge_agreements": llm_judge_agreements,
                    "llm_judge_correct": llm_judge_correct,
                    "llm_judge_agreement_rate": (
                        round(llm_judge_agreement_rate, 3)
                        if llm_judge_agreement_rate is not None
                        else None
                    ),
                    "llm_judge_accuracy": (
                        round(llm_judge_accuracy, 3)
                        if llm_judge_accuracy is not None
                        else None
                    ),
                    "llm_judge_disagreements": llm_judge_disagreements[:10],
                }

            # Cluster + root cause
            yield {
                "type": "progress",
                "step": "clustering",
                "detail": f"Klustrar {failures} fel och kör root cause-analys",
                "iteration": iteration,
            }

            clusters = self.auto_loop.cluster_failures(failed_queries)

            root_causes: list[str] = []
            try:
                from app.nexus.llm import nexus_llm_call

                async def _root_cause_for_cluster(cluster_obj):
                    if not cluster_obj.sample_queries:
                        return ""
                    rc_prompt = (
                        f"Analysera varför dessa frågor routades fel.\n"
                        f"Förväntade verktyg: {', '.join(cluster_obj.tool_ids)}\n"
                        f"Exempelfrågor:\n"
                        + "\n".join(
                            f"- {q}" for q in cluster_obj.sample_queries[:3]
                        )
                        + "\n\nSvara med EN mening som förklarar rotorsaken."
                    )
                    try:
                        result_text = await nexus_llm_call(rc_prompt)
                        return result_text.strip()
                    except Exception:
                        return ""

                rc_results = await forge_pool.gather(
                    [_root_cause_for_cluster(c) for c in clusters],
                    label="root_cause_stream",
                )
                root_causes = [r if isinstance(r, str) else "" for r in rc_results]
            except ImportError:
                pass

            proposals = self.auto_loop.create_proposals(
                clusters, root_causes=root_causes or None
            )

            cumulative_failed_queries.extend(failed_queries)
            cumulative_proposals.extend(proposals)
            cumulative_root_causes.extend(root_causes)

            yield {
                "type": "progress",
                "step": "proposals",
                "detail": f"{len(proposals)} förslag genererade i iteration {iteration}",
                "iteration": iteration,
                "proposals_count": len(proposals),
            }

            if failures == 0 or iteration == max_iterations:
                break

            # ── Auto-fit Platt calibration after first iteration ──────────
            if iteration == 1 and not self.platt_scaler.is_fitted and len(platt_raw_scores) >= 10:
                try:
                    self.platt_scaler.fit(platt_raw_scores, platt_labels)
                    yield {
                        "type": "progress",
                        "step": "platt_fitted",
                        "detail": f"Platt-kalibrering anpassad från {len(platt_raw_scores)} samples",
                        "iteration": iteration,
                    }
                except Exception as e:
                    logger.warning("Auto-loop Platt fitting failed: %s", e)

            # ── Apply optimizer suggestions between iterations ────────
            yield {
                "type": "progress",
                "step": "optimizing",
                "detail": f"Kör optimizer på felaktiga verktyg (iteration {iteration}→{iteration + 1})",
                "iteration": iteration,
            }

            try:
                from app.nexus.embeddings import nexus_clear_embed_cache
                from app.nexus.optimizer import MetadataOptimizer
                from app.nexus.platform_bridge import apply_overrides_to_cache

                # Map tool_id → namespace string for failed tools
                tool_ns_map: dict[str, str] = {}
                for pt in _get_pt():
                    tool_ns_map[pt.tool_id] = "/".join(pt.namespace[:2])

                # Collect unique namespaces from proposals
                ns_set: set[str] = set()
                for p in proposals:
                    ns = tool_ns_map.get(p.tool_id, "")
                    if ns:
                        ns_set.add(ns)

                optimizer = MetadataOptimizer()
                applied_tool_ids: set[str] = set()
                # Collect all overrides to patch in-memory cache
                memory_overrides: dict[str, dict] = {}

                for ns in ns_set:
                    try:
                        opt_result = await optimizer.generate_suggestions(
                            session, namespace=ns,
                            llm_config_id=-1,  # Use local model in loop (cost control)
                        )
                        if opt_result.suggestions:
                            apply_list = [
                                {
                                    "tool_id": s.tool_id,
                                    **s.suggested,
                                }
                                for s in opt_result.suggestions
                                if s.suggested.get("description")
                            ]
                            if apply_list:
                                await optimizer.apply_suggestions(
                                    session, apply_list
                                )
                                await session.commit()

                            # Collect overrides + update proposed_value on proposals
                            for s in opt_result.suggestions:
                                if s.suggested.get("description"):
                                    memory_overrides[s.tool_id] = s.suggested
                                    applied_tool_ids.add(s.tool_id)
                            desc_map = {
                                tid: ov.get("description", "")
                                for tid, ov in memory_overrides.items()
                            }
                            for p in proposals:
                                if p.tool_id in desc_map:
                                    p.proposed_value = desc_map[p.tool_id]
                    except Exception as e:
                        logger.warning(
                            "Auto-loop stream optimizer failed for ns=%s: %s",
                            ns, e,
                        )

                if applied_tool_ids:
                    # Patch in-memory tool cache so route_query sees new metadata
                    apply_overrides_to_cache(memory_overrides)
                    nexus_clear_embed_cache()
                    # Re-precompute embeddings — match the exact text format
                    # used by _build_tool_entries_from_platform
                    updated_tools = [
                        pt for pt in _get_pt() if pt.tool_id in applied_tool_ids
                    ]
                    recompute_texts = []
                    for pt in updated_tools:
                        zone_prefix = ZONE_PREFIXES.get(pt.zone, "")
                        kw_text = " ".join(pt.keywords[:8]) if pt.keywords else ""
                        ex_text = (
                            " | ".join(pt.example_queries[:2])
                            if pt.example_queries
                            else ""
                        )
                        full_text = (
                            f"{zone_prefix}{pt.tool_id} {pt.description}"
                            f" {kw_text} {ex_text}".strip()
                        )
                        recompute_texts.append(full_text)
                    if recompute_texts:
                        nexus_precompute(recompute_texts)

                    yield {
                        "type": "progress",
                        "step": "optimized",
                        "detail": f"Optimerade {len(applied_tool_ids)} verktyg, rensat cache",
                        "iteration": iteration,
                        "tools_optimized": len(applied_tool_ids),
                    }
            except Exception as e:
                logger.warning(
                    "Auto-loop stream inter-iteration optimizer failed: %s", e
                )

        # Compute embedding delta
        yield {
            "type": "progress",
            "step": "embedding",
            "detail": "Beräknar embedding-delta",
        }

        try:
            from app.nexus.embeddings import nexus_embed_score

            for proposal in cumulative_proposals:
                if proposal.current_value and proposal.proposed_value:
                    current_score = nexus_embed_score(
                        proposal.tool_id, proposal.current_value
                    )
                    proposed_score = nexus_embed_score(
                        proposal.tool_id, proposal.proposed_value
                    )
                    if current_score is not None and proposed_score is not None:
                        proposal.embedding_delta = proposed_score - current_score
        except Exception:
            pass

        # Mine hard negatives
        if cumulative_failed_queries:
            confusion_data = [
                {
                    "tool_a": fq.get("expected_tool", ""),
                    "tool_b": fq.get("got_tool", ""),
                    "similarity": 0.85,
                }
                for fq in cumulative_failed_queries
                if fq.get("expected_tool") and fq.get("got_tool")
            ]
            self.hard_negative_miner.mine_from_confusion(confusion_data)

            for pair in self.hard_negative_miner.pairs:
                try:
                    existing = await session.execute(
                        select(NexusHardNegative).where(
                            NexusHardNegative.anchor_tool == pair.anchor_tool,
                            NexusHardNegative.negative_tool == pair.negative_tool,
                        )
                    )
                    if not existing.scalars().first():
                        session.add(
                            NexusHardNegative(
                                anchor_tool=pair.anchor_tool,
                                negative_tool=pair.negative_tool,
                                mining_method=pair.mining_method,
                                similarity_score=pair.similarity_score,
                                confusion_frequency=pair.confusion_frequency,
                            )
                        )
                except Exception:
                    pass

        total_embedding_delta = (
            sum(p.embedding_delta for p in cumulative_proposals)
            / len(cumulative_proposals)
            if cumulative_proposals
            else 0.0
        )

        # Persist pipeline metrics
        last_iter = all_iteration_results[-1]
        final_p_at_1 = last_iter["precision_at_1"]
        final_p_at_5 = last_iter["precision_at_5"]
        final_mrr = last_iter["mrr"]
        final_band_counts = last_iter["band_distribution"]
        final_total_tests = last_iter["total_tests"]
        final_failures = last_iter["failures"]
        final_platform_comparisons = last_iter["platform_comparisons"]
        final_platform_agreements = last_iter["platform_agreements"]

        if final_total_tests >= 3:
            reranker_delta = (
                (
                    final_platform_agreements / final_platform_comparisons
                    - final_p_at_1
                )
                if final_platform_comparisons > 0
                else None
            )
            hn_precision = (
                final_platform_agreements / final_platform_comparisons
                if final_platform_comparisons > 0
                else None
            )
            metric_stages = [
                (1, "intent", final_p_at_1, final_p_at_5, final_mrr, None, None),
                (2, "route", final_p_at_1, final_p_at_5, final_mrr, None, None),
                (
                    3,
                    "bigtool",
                    final_p_at_5,
                    final_p_at_5,
                    final_mrr,
                    hn_precision,
                    None,
                ),
                (
                    4,
                    "rerank",
                    final_p_at_1,
                    final_p_at_5,
                    final_mrr,
                    hn_precision,
                    reranker_delta,
                ),
                (5, "e2e", final_p_at_1, final_p_at_5, final_mrr, None, None),
            ]
            for stage, name, p1, p5, mrr_val, hn_p, delta in metric_stages:
                metric = NexusPipelineMetric(
                    run_id=run_id,
                    stage=stage,
                    stage_name=name,
                    precision_at_1=p1,
                    precision_at_5=p5,
                    mrr_at_10=mrr_val,
                    ndcg_at_5=mrr_val,
                    hard_negative_precision=hn_p,
                    reranker_delta=delta,
                    recorded_at=datetime.now(tz=UTC),
                )
                session.add(metric)

        # Update run record
        enriched_proposals = []
        for p in cumulative_proposals:
            related_queries = [
                fq
                for fq in cumulative_failed_queries
                if fq.get("expected_tool") == p.tool_id
                or fq.get("got_tool") == p.tool_id
            ]
            enriched_proposals.append(
                {
                    "tool_id": p.tool_id,
                    "field": p.field_name,
                    "reason": p.reason,
                    "current_value": p.current_value or "",
                    "proposed_value": p.proposed_value or "",
                    "embedding_delta": round(p.embedding_delta, 4)
                    if p.embedding_delta
                    else 0.0,
                    "failed_queries": [
                        {
                            "query": fq.get("query", ""),
                            "expected_tool": fq.get("expected_tool", ""),
                            "got_tool": fq.get("got_tool", ""),
                            "resolved_zone": fq.get("resolved_zone", ""),
                            "selected_agent": fq.get("selected_agent", ""),
                            "band": fq.get("band", -1),
                            "confidence": fq.get("confidence", 0.0),
                            "difficulty": fq.get("difficulty", ""),
                            "llm_judge_tool": fq.get("llm_judge_tool"),
                            "llm_judge_reasoning": fq.get("llm_judge_reasoning", ""),
                        }
                        for fq in related_queries[:10]
                    ],
                }
            )

        # Aggregate LLM judge stats from all iterations
        llm_judge_summary = None
        all_disagreements: list[dict] = []
        total_llm_total = 0
        total_llm_agree = 0
        total_llm_correct = 0
        for ir in all_iteration_results:
            total_llm_total += ir.get("llm_judge_total", 0)
            total_llm_agree += ir.get("llm_judge_agreements", 0)
            total_llm_correct += ir.get("llm_judge_correct", 0)
            all_disagreements.extend(ir.get("llm_judge_disagreements", []))
        if total_llm_total > 0:
            # Aggregate quadrants from all iterations
            total_both_correct = sum(ir.get("both_correct", 0) for ir in all_iteration_results)
            total_nexus_only = sum(ir.get("nexus_only_correct", 0) for ir in all_iteration_results)
            total_llm_only = sum(ir.get("llm_only_correct", 0) for ir in all_iteration_results)
            total_both_wrong = sum(ir.get("both_wrong", 0) for ir in all_iteration_results)
            nexus_accuracy = (
                round((total_both_correct + total_nexus_only) / total_llm_total, 3)
            )
            llm_accuracy = (
                round((total_both_correct + total_llm_only) / total_llm_total, 3)
            )
            llm_judge_summary = {
                "total": total_llm_total,
                "agreements": total_llm_agree,
                "correct": total_llm_correct,
                "agreement_rate": round(total_llm_agree / total_llm_total, 3),
                "accuracy": round(total_llm_correct / total_llm_total, 3),
                "nexus_accuracy": nexus_accuracy,
                "llm_accuracy": llm_accuracy,
                "both_correct": total_both_correct,
                "nexus_only_correct": total_nexus_only,
                "llm_only_correct": total_llm_only,
                "both_wrong": total_both_wrong,
                "disagreements": all_disagreements[:30],
            }

        db_run.total_tests = final_total_tests
        db_run.failures = final_failures
        db_run.metadata_proposals = {
            "proposals": enriched_proposals,
            "platform_comparisons": final_platform_comparisons,
            "platform_agreements": final_platform_agreements,
            "band_distribution": final_band_counts,
            "iterations": all_iteration_results,
            "total_cases_available": total_case_count,
            "llm_judge": llm_judge_summary,
        }
        db_run.approved_proposals = 0
        db_run.embedding_delta = total_embedding_delta
        db_run.status = "review" if cumulative_proposals else "approved"
        db_run.completed_at = datetime.now(tz=UTC)
        await session.commit()

        yield {
            "type": "done",
            "run_id": str(run_id),
            "loop_number": loop_number,
            "status": "completed",
            "total_tests": final_total_tests,
            "total_cases_available": total_case_count,
            "iterations_completed": len(all_iteration_results),
            "failures": final_failures,
            "proposals": len(cumulative_proposals),
            "embedding_delta": round(total_embedding_delta, 4),
            "precision_at_1": final_p_at_1,
            "mrr": final_mrr,
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
