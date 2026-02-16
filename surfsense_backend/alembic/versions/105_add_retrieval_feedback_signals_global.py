"""Add global retrieval feedback signals table

Revision ID: 105
Revises: 104
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "105"
down_revision: str | None = "104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retrieval_feedback_signals_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("tool_id", sa.String(length=160), nullable=False),
        sa.Column("query_pattern_hash", sa.String(length=32), nullable=False),
        sa.Column("successes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "tool_id",
            "query_pattern_hash",
            name="uq_retrieval_feedback_signals_global_tool_pattern",
        ),
    )
    op.create_index(
        "ix_retrieval_feedback_signals_global_id",
        "retrieval_feedback_signals_global",
        ["id"],
    )
    op.create_index(
        "ix_retrieval_feedback_signals_global_created_at",
        "retrieval_feedback_signals_global",
        ["created_at"],
    )
    op.create_index(
        "ix_retrieval_feedback_signals_global_tool_id",
        "retrieval_feedback_signals_global",
        ["tool_id"],
    )
    op.create_index(
        "ix_retrieval_feedback_signals_global_query_pattern_hash",
        "retrieval_feedback_signals_global",
        ["query_pattern_hash"],
    )
    op.create_index(
        "ix_retrieval_feedback_signals_global_updated_at",
        "retrieval_feedback_signals_global",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrieval_feedback_signals_global_updated_at",
        table_name="retrieval_feedback_signals_global",
    )
    op.drop_index(
        "ix_retrieval_feedback_signals_global_query_pattern_hash",
        table_name="retrieval_feedback_signals_global",
    )
    op.drop_index(
        "ix_retrieval_feedback_signals_global_tool_id",
        table_name="retrieval_feedback_signals_global",
    )
    op.drop_index(
        "ix_retrieval_feedback_signals_global_created_at",
        table_name="retrieval_feedback_signals_global",
    )
    op.drop_index(
        "ix_retrieval_feedback_signals_global_id",
        table_name="retrieval_feedback_signals_global",
    )
    op.drop_table("retrieval_feedback_signals_global")
