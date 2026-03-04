"""Add nexus_deploy_state table and update zone seed data

Revision ID: 109
Revises: 108
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "109"
down_revision: str | None = "108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 10. nexus_deploy_state — persisted deploy lifecycle
    op.create_table(
        "nexus_deploy_state",
        sa.Column("tool_id", sa.Text(), primary_key=True),
        sa.Column("stage", sa.String(20), nullable=False, server_default=sa.text("'review'")),
        sa.Column("promoted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.Text(), nullable=True),
        sa.Column("gate1_score", sa.Float(), nullable=True),
        sa.Column("gate2_score", sa.Float(), nullable=True),
        sa.Column("gate3_score", sa.Float(), nullable=True),
        sa.Column("gate3_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )



def downgrade() -> None:
    op.drop_table("nexus_deploy_state")
