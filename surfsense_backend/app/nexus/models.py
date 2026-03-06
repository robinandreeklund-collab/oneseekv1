"""NEXUS SQLAlchemy models — all tables use nexus_ prefix.

These models are registered in the shared SQLAlchemy Base metadata
but are completely independent of legacy eval tables.
"""

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    Boolean,
    Column,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db import Base


def _utcnow():
    return datetime.now(UTC)


def _genuuid():
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# 1. Syntetiska testfall (Synth Forge)
# ---------------------------------------------------------------------------


class NexusSyntheticCase(Base):
    __tablename__ = "nexus_synthetic_cases"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=_genuuid)
    tool_id = Column(Text, nullable=False, index=True)
    namespace = Column(Text, nullable=False)
    question = Column(Text, nullable=False)
    difficulty = Column(String(20), nullable=False, index=True)
    expected_tool = Column(Text, nullable=True)
    expected_intent = Column(Text, nullable=True)
    expected_agent = Column(Text, nullable=True)
    expected_not_tools = Column(ARRAY(Text), nullable=True)
    generation_model = Column(Text, nullable=True)
    generation_run_id = Column(UUID(as_uuid=True), nullable=True)
    roundtrip_verified = Column(Boolean, default=False, nullable=False)
    quality_score = Column(Float, nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, index=True
    )


# ---------------------------------------------------------------------------
# 2. Embedding-rymd snapshots (Space Auditor)
# ---------------------------------------------------------------------------


class NexusSpaceSnapshot(Base):
    __tablename__ = "nexus_space_snapshots"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=_genuuid)
    snapshot_at = Column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, index=True
    )
    tool_id = Column(Text, nullable=False, index=True)
    namespace = Column(Text, nullable=False)
    embedding_model = Column(Text, nullable=False)
    umap_x = Column(Float, nullable=True)
    umap_y = Column(Float, nullable=True)
    cluster_label = Column(Integer, nullable=True)
    silhouette_score = Column(Float, nullable=True)
    nearest_neighbor_tool = Column(Text, nullable=True)
    nearest_neighbor_distance = Column(Float, nullable=True)


# ---------------------------------------------------------------------------
# 3. Auto-loop körningar
# ---------------------------------------------------------------------------


class NexusAutoLoopRun(Base):
    __tablename__ = "nexus_auto_loop_runs"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=_genuuid)
    loop_number = Column(Integer, nullable=False)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    total_tests = Column(Integer, nullable=True)
    failures = Column(Integer, nullable=True)
    metadata_proposals = Column(JSONB, nullable=True)
    approved_proposals = Column(Integer, nullable=True)
    embedding_delta = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)


# ---------------------------------------------------------------------------
# 4. Pipeline-steg metriker (Eval Ledger)
# ---------------------------------------------------------------------------


class NexusPipelineMetric(Base):
    __tablename__ = "nexus_pipeline_metrics"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=_genuuid)
    run_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    stage = Column(Integer, nullable=False, index=True)
    stage_name = Column(String(20), nullable=False)
    namespace = Column(Text, nullable=True)
    precision_at_1 = Column(Float, nullable=True)
    precision_at_5 = Column(Float, nullable=True)
    mrr_at_10 = Column(Float, nullable=True)
    ndcg_at_5 = Column(Float, nullable=True)
    hard_negative_precision = Column(Float, nullable=True)
    reranker_delta = Column(Float, nullable=True)
    recorded_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_utcnow)


# ---------------------------------------------------------------------------
# 5. Confidence calibration per zon
# ---------------------------------------------------------------------------


class NexusCalibrationParam(Base):
    __tablename__ = "nexus_calibration_params"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=_genuuid)
    zone = Column(Text, nullable=False, index=True)
    calibration_method = Column(String(20), nullable=False)
    param_a = Column(Float, nullable=True)
    param_b = Column(Float, nullable=True)
    temperature = Column(Float, nullable=True)
    ece_score = Column(Float, nullable=True)
    fitted_on_samples = Column(Integer, nullable=True)
    fitted_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_utcnow)
    is_active = Column(Boolean, default=True, nullable=False)


# ---------------------------------------------------------------------------
# 6. OOD / Dark Matter register
# ---------------------------------------------------------------------------


class NexusDarkMatterQuery(Base):
    __tablename__ = "nexus_dark_matter_queries"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=_genuuid)
    query_text = Column(Text, nullable=False)
    energy_score = Column(Float, nullable=False)
    knn_distance = Column(Float, nullable=True)
    uaq_category = Column(String(30), nullable=True)
    cluster_id = Column(Integer, nullable=True, index=True)
    reviewed = Column(Boolean, default=False, nullable=False, index=True)
    new_tool_candidate = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_utcnow)


# ---------------------------------------------------------------------------
# 7. Hard negative bank
# ---------------------------------------------------------------------------


class NexusHardNegative(Base):
    __tablename__ = "nexus_hard_negatives"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=_genuuid)
    anchor_tool = Column(Text, nullable=False, index=True)
    negative_tool = Column(Text, nullable=False)
    mining_method = Column(String(30), nullable=False)
    similarity_score = Column(Float, nullable=True)
    is_false_negative = Column(Boolean, default=False, nullable=False)
    adversarial_query = Column(Text, nullable=True)
    confusion_frequency = Column(Float, nullable=True)
    added_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("anchor_tool", "negative_tool", name="uq_nexus_hn_pair"),
    )


# ---------------------------------------------------------------------------
# 8. Zone-konfiguration + hälsa
# ---------------------------------------------------------------------------


class NexusZoneConfig(Base):
    __tablename__ = "nexus_zone_config"
    __allow_unmapped__ = True

    zone = Column(Text, primary_key=True)
    prefix_token = Column(Text, nullable=False)
    centroid_embedding = Column(Vector(768), nullable=True)
    silhouette_score = Column(Float, nullable=True)
    inter_zone_min_distance = Column(Float, nullable=True)
    last_reindexed = Column(TIMESTAMP(timezone=True), nullable=True)
    ood_energy_threshold = Column(Float, default=-5.0, nullable=False)
    band0_rate = Column(Float, nullable=True)
    ece_score = Column(Float, nullable=True)


# ---------------------------------------------------------------------------
# 9. Routing precision events
# ---------------------------------------------------------------------------


class NexusRoutingEvent(Base):
    __tablename__ = "nexus_routing_events"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=_genuuid)
    query_text = Column(Text, nullable=True)
    query_hash = Column(Text, nullable=True)
    band = Column(Integer, nullable=False, index=True)
    resolved_zone = Column(Text, nullable=True, index=True)
    selected_agent = Column(Text, nullable=True, index=True)
    selected_tool = Column(Text, nullable=True)
    raw_reranker_score = Column(Float, nullable=True)
    calibrated_confidence = Column(Float, nullable=True)
    is_multi_intent = Column(Boolean, nullable=True)
    sub_query_count = Column(Integer, nullable=True)
    schema_verified = Column(Boolean, nullable=True)
    is_ood = Column(Boolean, default=False, nullable=False)
    implicit_feedback = Column(String(20), nullable=True)
    explicit_feedback = Column(Integer, nullable=True)
    routed_at = Column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, index=True
    )


# ---------------------------------------------------------------------------
# 10. Deploy lifecycle state (persisted — survives restarts)
# ---------------------------------------------------------------------------


class NexusDeployState(Base):
    __tablename__ = "nexus_deploy_state"
    __allow_unmapped__ = True

    tool_id = Column(Text, primary_key=True)
    stage = Column(
        String(20), nullable=False, default="review"
    )  # review|staging|live|rolled_back
    promoted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    promoted_by = Column(Text, nullable=True)
    gate1_score = Column(Float, nullable=True)
    gate2_score = Column(Float, nullable=True)
    gate3_score = Column(Float, nullable=True)
    gate3_details = Column(JSONB, nullable=True)  # LLM judge output
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_utcnow)
