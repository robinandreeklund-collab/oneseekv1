"""Add global tool metadata override tables

Revision ID: 99
Revises: 98
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "99"
down_revision: str | None = "98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_metadata_overrides_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("tool_id", sa.String(length=160), nullable=False),
        sa.Column(
            "override_payload",
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
            "tool_id",
            name="uq_tool_metadata_override_global_tool_id",
        ),
    )
    op.create_index(
        "ix_tool_metadata_overrides_global_id",
        "tool_metadata_overrides_global",
        ["id"],
    )
    op.create_index(
        "ix_tool_metadata_overrides_global_tool_id",
        "tool_metadata_overrides_global",
        ["tool_id"],
    )
    op.create_index(
        "ix_tool_metadata_overrides_global_updated_at",
        "tool_metadata_overrides_global",
        ["updated_at"],
    )

    op.create_table(
        "tool_metadata_override_history_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("tool_id", sa.String(length=160), nullable=False),
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
        "ix_tool_metadata_override_history_global_id",
        "tool_metadata_override_history_global",
        ["id"],
    )
    op.create_index(
        "ix_tool_metadata_override_history_global_tool_id",
        "tool_metadata_override_history_global",
        ["tool_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_metadata_override_history_global_tool_id",
        table_name="tool_metadata_override_history_global",
    )
    op.drop_index(
        "ix_tool_metadata_override_history_global_id",
        table_name="tool_metadata_override_history_global",
    )
    op.drop_table("tool_metadata_override_history_global")

    op.drop_index(
        "ix_tool_metadata_overrides_global_updated_at",
        table_name="tool_metadata_overrides_global",
    )
    op.drop_index(
        "ix_tool_metadata_overrides_global_tool_id",
        table_name="tool_metadata_overrides_global",
    )
    op.drop_index(
        "ix_tool_metadata_overrides_global_id",
        table_name="tool_metadata_overrides_global",
    )
    op.drop_table("tool_metadata_overrides_global")
