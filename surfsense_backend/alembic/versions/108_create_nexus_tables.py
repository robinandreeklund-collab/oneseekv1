"""Create NEXUS Retrieval Intelligence Platform tables

Revision ID: 108
Revises: 107
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "108"
down_revision: str | None = "107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 1. nexus_synthetic_cases
    op.create_table(
        "nexus_synthetic_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tool_id", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(20), nullable=False),
        sa.Column("expected_tool", sa.Text(), nullable=True),
        sa.Column("expected_not_tools", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("generation_model", sa.Text(), nullable=True),
        sa.Column("generation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("roundtrip_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_nexus_synth_tool_id", "nexus_synthetic_cases", ["tool_id"])
    op.create_index("ix_nexus_synth_difficulty", "nexus_synthetic_cases", ["difficulty"])
    op.create_index("ix_nexus_synth_created_at", "nexus_synthetic_cases", ["created_at"])

    # 2. nexus_space_snapshots
    op.create_table(
        "nexus_space_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("snapshot_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("tool_id", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("umap_x", sa.Float(), nullable=True),
        sa.Column("umap_y", sa.Float(), nullable=True),
        sa.Column("cluster_label", sa.Integer(), nullable=True),
        sa.Column("silhouette_score", sa.Float(), nullable=True),
        sa.Column("nearest_neighbor_tool", sa.Text(), nullable=True),
        sa.Column("nearest_neighbor_distance", sa.Float(), nullable=True),
    )
    op.create_index("ix_nexus_space_snapshot_at", "nexus_space_snapshots", ["snapshot_at"])
    op.create_index("ix_nexus_space_tool_id", "nexus_space_snapshots", ["tool_id"])

    # 3. nexus_auto_loop_runs
    op.create_table(
        "nexus_auto_loop_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("loop_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("total_tests", sa.Integer(), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=True),
        sa.Column("metadata_proposals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved_proposals", sa.Integer(), nullable=True),
        sa.Column("embedding_delta", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
    )
    op.create_index("ix_nexus_loop_status", "nexus_auto_loop_runs", ["status"])

    # 4. nexus_pipeline_metrics
    op.create_table(
        "nexus_pipeline_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(20), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=True),
        sa.Column("precision_at_1", sa.Float(), nullable=True),
        sa.Column("precision_at_5", sa.Float(), nullable=True),
        sa.Column("mrr_at_10", sa.Float(), nullable=True),
        sa.Column("ndcg_at_5", sa.Float(), nullable=True),
        sa.Column("hard_negative_precision", sa.Float(), nullable=True),
        sa.Column("reranker_delta", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_nexus_pipeline_run_id", "nexus_pipeline_metrics", ["run_id"])
    op.create_index("ix_nexus_pipeline_stage", "nexus_pipeline_metrics", ["stage"])

    # 5. nexus_calibration_params
    op.create_table(
        "nexus_calibration_params",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("zone", sa.Text(), nullable=False),
        sa.Column("calibration_method", sa.String(20), nullable=False),
        sa.Column("param_a", sa.Float(), nullable=True),
        sa.Column("param_b", sa.Float(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("ece_score", sa.Float(), nullable=True),
        sa.Column("fitted_on_samples", sa.Integer(), nullable=True),
        sa.Column("fitted_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_nexus_calib_zone", "nexus_calibration_params", ["zone"])

    # 6. nexus_dark_matter_queries
    op.create_table(
        "nexus_dark_matter_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("energy_score", sa.Float(), nullable=False),
        sa.Column("knn_distance", sa.Float(), nullable=True),
        sa.Column("uaq_category", sa.String(30), nullable=True),
        sa.Column("cluster_id", sa.Integer(), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("new_tool_candidate", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_nexus_dm_cluster", "nexus_dark_matter_queries", ["cluster_id"])
    op.create_index("ix_nexus_dm_reviewed", "nexus_dark_matter_queries", ["reviewed"])

    # 7. nexus_hard_negatives
    op.create_table(
        "nexus_hard_negatives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("anchor_tool", sa.Text(), nullable=False),
        sa.Column("negative_tool", sa.Text(), nullable=False),
        sa.Column("mining_method", sa.String(30), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("is_false_negative", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("adversarial_query", sa.Text(), nullable=True),
        sa.Column("confusion_frequency", sa.Float(), nullable=True),
        sa.Column("added_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("anchor_tool", "negative_tool", name="uq_nexus_hn_pair"),
    )
    op.create_index("ix_nexus_hn_anchor", "nexus_hard_negatives", ["anchor_tool"])

    # 8. nexus_zone_config
    op.create_table(
        "nexus_zone_config",
        sa.Column("zone", sa.Text(), primary_key=True),
        sa.Column("prefix_token", sa.Text(), nullable=False),
        sa.Column("silhouette_score", sa.Float(), nullable=True),
        sa.Column("inter_zone_min_distance", sa.Float(), nullable=True),
        sa.Column("last_reindexed", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ood_energy_threshold", sa.Float(), nullable=False, server_default=sa.text("-5.0")),
        sa.Column("band0_rate", sa.Float(), nullable=True),
        sa.Column("ece_score", sa.Float(), nullable=True),
    )
    # Add vector column via raw SQL (pgvector requires special type)
    op.execute("ALTER TABLE nexus_zone_config ADD COLUMN centroid_embedding vector(768)")

    # Seed default zone configurations (aligned with config.py Zone enum)
    op.execute("""
        INSERT INTO nexus_zone_config (zone, prefix_token, ood_energy_threshold) VALUES
        ('kunskap', '[KUNSK] ', -5.0),
        ('skapande', '[SKAP] ', -5.0),
        ('jämförelse', '[JAMFR] ', -5.0),
        ('konversation', '[KONV] ', -5.0)
        ON CONFLICT (zone) DO NOTHING
    """)

    # 9. nexus_routing_events
    op.create_table(
        "nexus_routing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("query_hash", sa.Text(), nullable=True),
        sa.Column("band", sa.Integer(), nullable=False),
        sa.Column("resolved_zone", sa.Text(), nullable=True),
        sa.Column("selected_tool", sa.Text(), nullable=True),
        sa.Column("raw_reranker_score", sa.Float(), nullable=True),
        sa.Column("calibrated_confidence", sa.Float(), nullable=True),
        sa.Column("is_multi_intent", sa.Boolean(), nullable=True),
        sa.Column("sub_query_count", sa.Integer(), nullable=True),
        sa.Column("schema_verified", sa.Boolean(), nullable=True),
        sa.Column("is_ood", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("implicit_feedback", sa.String(20), nullable=True),
        sa.Column("explicit_feedback", sa.Integer(), nullable=True),
        sa.Column("routed_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_nexus_routing_band", "nexus_routing_events", ["band"])
    op.create_index("ix_nexus_routing_zone", "nexus_routing_events", ["resolved_zone"])
    op.create_index("ix_nexus_routing_at", "nexus_routing_events", ["routed_at"])


def downgrade() -> None:
    op.drop_table("nexus_routing_events")
    op.drop_table("nexus_zone_config")
    op.drop_table("nexus_hard_negatives")
    op.drop_table("nexus_dark_matter_queries")
    op.drop_table("nexus_calibration_params")
    op.drop_table("nexus_pipeline_metrics")
    op.drop_table("nexus_auto_loop_runs")
    op.drop_table("nexus_space_snapshots")
    op.drop_table("nexus_synthetic_cases")
