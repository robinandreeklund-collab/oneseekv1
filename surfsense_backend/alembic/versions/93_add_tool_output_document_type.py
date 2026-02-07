"""Add TOOL_OUTPUT to documenttype enum

Revision ID: 93
Revises: 92
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "93"
down_revision: str | None = "92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add TOOL_OUTPUT to documenttype enum."""
    op.execute("ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'TOOL_OUTPUT'")


def downgrade() -> None:
    """
    Downgrade is not supported for enum value removal in PostgreSQL.
    """
    pass
