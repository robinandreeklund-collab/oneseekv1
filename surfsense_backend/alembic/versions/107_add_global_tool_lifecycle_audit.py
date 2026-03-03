"""Add global_tool_lifecycle_audit table for v2 admin tools

Revision ID: 107
Revises: 106
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "107"
down_revision: str | None = "106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "global_tool_lifecycle_audit",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("tool_id", sa.String(length=160), nullable=False),
        sa.Column("old_status", sa.String(length=10), nullable=True),
        sa.Column("new_status", sa.String(length=10), nullable=False),
        sa.Column("success_rate", sa.Float(), nullable=True),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_global_tool_lifecycle_audit_id",
        "global_tool_lifecycle_audit",
        ["id"],
    )
    op.create_index(
        "ix_global_tool_lifecycle_audit_tool_id",
        "global_tool_lifecycle_audit",
        ["tool_id"],
    )
    op.create_index(
        "ix_global_tool_lifecycle_audit_created_at",
        "global_tool_lifecycle_audit",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_global_tool_lifecycle_audit_created_at",
        table_name="global_tool_lifecycle_audit",
    )
    op.drop_index(
        "ix_global_tool_lifecycle_audit_tool_id",
        table_name="global_tool_lifecycle_audit",
    )
    op.drop_index(
        "ix_global_tool_lifecycle_audit_id",
        table_name="global_tool_lifecycle_audit",
    )
    op.drop_table("global_tool_lifecycle_audit")
