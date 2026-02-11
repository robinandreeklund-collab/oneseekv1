"""Add external search document types to documenttype enum

Revision ID: 92
Revises: 91
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92"
down_revision: str | None = "91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add external search document types to documenttype enum."""
    op.execute("ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'TAVILY_API'")
    op.execute("ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'SEARXNG_API'")
    op.execute("ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'LINKUP_API'")
    op.execute("ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'BAIDU_SEARCH_API'")


def downgrade() -> None:
    """
    Downgrade is not supported for enum value removal in PostgreSQL.
    """
    pass
