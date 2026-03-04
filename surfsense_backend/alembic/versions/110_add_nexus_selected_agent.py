"""Add selected_agent column to nexus_routing_events

Revision ID: 110
Revises: 109
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "110"
down_revision: str | None = "109"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nexus_routing_events",
        sa.Column("selected_agent", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_nexus_routing_agent",
        "nexus_routing_events",
        ["selected_agent"],
    )


def downgrade() -> None:
    op.drop_index("ix_nexus_routing_agent", table_name="nexus_routing_events")
    op.drop_column("nexus_routing_events", "selected_agent")
