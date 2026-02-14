"""Add global tool retrieval tuning tables

Revision ID: 100
Revises: 99
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "100"
down_revision: str | None = "99"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_retrieval_tuning_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("config_key", sa.String(length=40), nullable=False),
        sa.Column(
            "tuning_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "config_key",
            name="uq_tool_retrieval_tuning_global_key",
        ),
    )
    op.create_index(
        "ix_tool_retrieval_tuning_global_id",
        "tool_retrieval_tuning_global",
        ["id"],
    )
    op.create_index(
        "ix_tool_retrieval_tuning_global_config_key",
        "tool_retrieval_tuning_global",
        ["config_key"],
    )
    op.create_index(
        "ix_tool_retrieval_tuning_global_updated_at",
        "tool_retrieval_tuning_global",
        ["updated_at"],
    )

    op.create_table(
        "tool_retrieval_tuning_history_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("config_key", sa.String(length=40), nullable=False),
        sa.Column(
            "previous_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "new_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_tool_retrieval_tuning_history_global_id",
        "tool_retrieval_tuning_history_global",
        ["id"],
    )
    op.create_index(
        "ix_tool_retrieval_tuning_history_global_config_key",
        "tool_retrieval_tuning_history_global",
        ["config_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_retrieval_tuning_history_global_config_key",
        table_name="tool_retrieval_tuning_history_global",
    )
    op.drop_index(
        "ix_tool_retrieval_tuning_history_global_id",
        table_name="tool_retrieval_tuning_history_global",
    )
    op.drop_table("tool_retrieval_tuning_history_global")

    op.drop_index(
        "ix_tool_retrieval_tuning_global_updated_at",
        table_name="tool_retrieval_tuning_global",
    )
    op.drop_index(
        "ix_tool_retrieval_tuning_global_config_key",
        table_name="tool_retrieval_tuning_global",
    )
    op.drop_index(
        "ix_tool_retrieval_tuning_global_id",
        table_name="tool_retrieval_tuning_global",
    )
    op.drop_table("tool_retrieval_tuning_global")
