"""Add expected_intent and expected_agent columns to nexus_synthetic_cases

Revision ID: 112
Revises: 111
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "112"
down_revision: str = "111"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nexus_synthetic_cases",
        sa.Column("expected_intent", sa.Text(), nullable=True),
    )
    op.add_column(
        "nexus_synthetic_cases",
        sa.Column("expected_agent", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("nexus_synthetic_cases", "expected_agent")
    op.drop_column("nexus_synthetic_cases", "expected_intent")
