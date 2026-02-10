"""Add agent combination cache table

Revision ID: 98
Revises: 97
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "98"
down_revision: str | None = "97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_combo_cache",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("cache_key", sa.String(length=128), nullable=False),
        sa.Column("route_hint", sa.String(length=32), nullable=True),
        sa.Column("pattern", sa.Text(), nullable=True),
        sa.Column("recent_agents", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_used_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("cache_key", name="uq_agent_combo_cache_key"),
    )
    op.create_index(
        "ix_agent_combo_cache_cache_key",
        "agent_combo_cache",
        ["cache_key"],
    )
    op.create_index(
        "ix_agent_combo_cache_route_hint",
        "agent_combo_cache",
        ["route_hint"],
    )
    op.create_index(
        "ix_agent_combo_cache_updated_at",
        "agent_combo_cache",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_combo_cache_updated_at", table_name="agent_combo_cache")
    op.drop_index("ix_agent_combo_cache_route_hint", table_name="agent_combo_cache")
    op.drop_index("ix_agent_combo_cache_cache_key", table_name="agent_combo_cache")
    op.drop_table("agent_combo_cache")
