"""Resize vector embedding columns for KBLab/sentence-bert-swedish-cased

The new model produces 768-dimensional embeddings (up from 384 with
all-MiniLM-L6-v2).  This migration changes every ``vector(384)`` column
to ``vector(768)``.

After running this migration, execute the companion re-embed script to
populate the new 768-dim vectors:

    python scripts/reembed_all.py

Revision ID: 106
Revises: 105
"""

from collections.abc import Sequence

from alembic import op

from app.config import config

# revision identifiers, used by Alembic.
revision: str = "106"
down_revision: str | None = "105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_DIM = config.embedding_model_instance.dimension  # 768 for KBLab
OLD_DIM = 384  # previous model (all-MiniLM-L6-v2)

# Every table + column that stores an embedding vector.
_EMBEDDING_TABLES = [
    "documents",
    "chunks",
    "user_memories",
    "surfsense_docs_documents",
    "surfsense_docs_chunks",
]


def upgrade() -> None:
    """Widen embedding columns to the new model dimension.

    Existing rows will have their embedding set to NULL because a
    384-dim vector cannot be stored in a 768-dim column without
    re-computing.  Run ``scripts/reembed_all.py`` after this migration.
    """
    for table in _EMBEDDING_TABLES:
        # Set existing embeddings to NULL first — they are the wrong
        # dimension and cannot be cast.
        op.execute(f"UPDATE {table} SET embedding = NULL")
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN embedding TYPE vector({NEW_DIM})"
        )


def downgrade() -> None:
    """Shrink embedding columns back to 384 dimensions."""
    for table in _EMBEDDING_TABLES:
        op.execute(f"UPDATE {table} SET embedding = NULL")
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN embedding TYPE vector({OLD_DIM})"
        )
