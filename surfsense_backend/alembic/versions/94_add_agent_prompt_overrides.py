"""Add agent prompt overrides table

Revision ID: 94
Revises: 93
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "94"
down_revision: str | None = "93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False, server_default=""),
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
        sa.UniqueConstraint(
            "search_space_id",
            "key",
            name="uq_agent_prompt_override_space_key",
        ),
    )
    op.create_index(
        "ix_agent_prompt_overrides_id",
        "agent_prompt_overrides",
        ["id"],
    )
    op.create_index(
        "ix_agent_prompt_overrides_key",
        "agent_prompt_overrides",
        ["key"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_prompt_overrides_key", table_name="agent_prompt_overrides")
    op.drop_index("ix_agent_prompt_overrides_id", table_name="agent_prompt_overrides")
    op.drop_table("agent_prompt_overrides")
