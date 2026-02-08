"""Add agent prompt override history table

Revision ID: 95
Revises: 94
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "95"
down_revision: str | None = "94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_override_history",
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
        sa.Column("search_space_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["search_space_id"],
            ["searchspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_agent_prompt_override_history_id",
        "agent_prompt_override_history",
        ["id"],
    )
    op.create_index(
        "ix_agent_prompt_override_history_key",
        "agent_prompt_override_history",
        ["key"],
    )
    op.create_index(
        "ix_agent_prompt_override_history_space",
        "agent_prompt_override_history",
        ["search_space_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_prompt_override_history_space",
        table_name="agent_prompt_override_history",
    )
    op.drop_index(
        "ix_agent_prompt_override_history_key",
        table_name="agent_prompt_override_history",
    )
    op.drop_index(
        "ix_agent_prompt_override_history_id",
        table_name="agent_prompt_override_history",
    )
    op.drop_table("agent_prompt_override_history")
