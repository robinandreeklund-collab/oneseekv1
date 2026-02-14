"""Add global tool evaluation runs table

Revision ID: 101
Revises: 100
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "101"
down_revision: str | None = "100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_evaluation_runs_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("search_space_id", sa.Integer(), nullable=False),
        sa.Column("eval_name", sa.String(length=160), nullable=True),
        sa.Column("total_tests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_tests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="0"),
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
        "ix_tool_evaluation_runs_global_id",
        "tool_evaluation_runs_global",
        ["id"],
    )
    op.create_index(
        "ix_tool_evaluation_runs_global_search_space_id",
        "tool_evaluation_runs_global",
        ["search_space_id"],
    )
    op.create_index(
        "ix_tool_evaluation_runs_global_created_at",
        "tool_evaluation_runs_global",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_evaluation_runs_global_created_at",
        table_name="tool_evaluation_runs_global",
    )
    op.drop_index(
        "ix_tool_evaluation_runs_global_search_space_id",
        table_name="tool_evaluation_runs_global",
    )
    op.drop_index(
        "ix_tool_evaluation_runs_global_id",
        table_name="tool_evaluation_runs_global",
    )
    op.drop_table("tool_evaluation_runs_global")
