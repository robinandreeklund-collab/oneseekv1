"""Add global tool lifecycle status table

Revision ID: 104
Revises: 103
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "104"
down_revision: str | None = "103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enum type for tool lifecycle status
    tool_lifecycle_status = sa.Enum(
        'review', 
        'live', 
        name='toollifecyclestatus'
    )
    tool_lifecycle_status.create(op.get_bind(), checkfirst=True)
    
    # Create global_tool_lifecycle_status table
    op.create_table(
        "global_tool_lifecycle_status",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("tool_id", sa.String(length=160), nullable=False),
        sa.Column(
            "status",
            sa.Enum('review', 'live', name='toollifecyclestatus'),
            nullable=False,
            server_default='review',
        ),
        sa.Column("success_rate", sa.Float(), nullable=True),
        sa.Column("total_tests", sa.Integer(), nullable=True),
        sa.Column(
            "last_eval_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "required_success_rate",
            sa.Float(),
            nullable=False,
            server_default="0.80",
        ),
        sa.Column("changed_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "changed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "tool_id",
            name="uq_global_tool_lifecycle_status_tool_id",
        ),
    )
    
    # Create indexes
    op.create_index(
        "ix_global_tool_lifecycle_status_id",
        "global_tool_lifecycle_status",
        ["id"],
    )
    op.create_index(
        "ix_global_tool_lifecycle_status_tool_id",
        "global_tool_lifecycle_status",
        ["tool_id"],
        unique=True,
    )
    op.create_index(
        "ix_global_tool_lifecycle_status_status",
        "global_tool_lifecycle_status",
        ["status"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index(
        "ix_global_tool_lifecycle_status_status",
        table_name="global_tool_lifecycle_status",
    )
    op.drop_index(
        "ix_global_tool_lifecycle_status_tool_id",
        table_name="global_tool_lifecycle_status",
    )
    op.drop_index(
        "ix_global_tool_lifecycle_status_id",
        table_name="global_tool_lifecycle_status",
    )
    
    # Drop table
    op.drop_table("global_tool_lifecycle_status")
    
    # Drop enum type
    sa.Enum(name='toollifecyclestatus').drop(op.get_bind(), checkfirst=True)
