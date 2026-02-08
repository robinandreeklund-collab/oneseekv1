"""Add global agent prompt overrides tables

Revision ID: 96
Revises: 95
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "96"
down_revision: str | None = "95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_overrides_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "key",
            name="uq_agent_prompt_override_global_key",
        ),
    )
    op.create_index(
        "ix_agent_prompt_overrides_global_id",
        "agent_prompt_overrides_global",
        ["id"],
    )
    op.create_index(
        "ix_agent_prompt_overrides_global_key",
        "agent_prompt_overrides_global",
        ["key"],
    )

    op.create_table(
        "agent_prompt_override_history_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("previous_prompt_text", sa.Text(), nullable=True),
        sa.Column("new_prompt_text", sa.Text(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_agent_prompt_override_history_global_id",
        "agent_prompt_override_history_global",
        ["id"],
    )
    op.create_index(
        "ix_agent_prompt_override_history_global_key",
        "agent_prompt_override_history_global",
        ["key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_prompt_override_history_global_key",
        table_name="agent_prompt_override_history_global",
    )
    op.drop_index(
        "ix_agent_prompt_override_history_global_id",
        table_name="agent_prompt_override_history_global",
    )
    op.drop_table("agent_prompt_override_history_global")

    op.drop_index(
        "ix_agent_prompt_overrides_global_key",
        table_name="agent_prompt_overrides_global",
    )
    op.drop_index(
        "ix_agent_prompt_overrides_global_id",
        table_name="agent_prompt_overrides_global",
    )
    op.drop_table("agent_prompt_overrides_global")
