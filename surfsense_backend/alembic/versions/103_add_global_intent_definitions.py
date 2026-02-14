"""Add global intent definitions tables

Revision ID: 103
Revises: 102
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "103"
down_revision: str | None = "102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intent_definitions_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("intent_id", sa.String(length=80), nullable=False),
        sa.Column(
            "definition_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "intent_id",
            name="uq_intent_definitions_global_intent_id",
        ),
    )
    op.create_index(
        "ix_intent_definitions_global_id",
        "intent_definitions_global",
        ["id"],
    )
    op.create_index(
        "ix_intent_definitions_global_created_at",
        "intent_definitions_global",
        ["created_at"],
    )
    op.create_index(
        "ix_intent_definitions_global_intent_id",
        "intent_definitions_global",
        ["intent_id"],
    )
    op.create_index(
        "ix_intent_definitions_global_updated_at",
        "intent_definitions_global",
        ["updated_at"],
    )

    op.create_table(
        "intent_definition_history_global",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("intent_id", sa.String(length=80), nullable=False),
        sa.Column(
            "previous_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "new_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_intent_definition_history_global_id",
        "intent_definition_history_global",
        ["id"],
    )
    op.create_index(
        "ix_intent_definition_history_global_created_at",
        "intent_definition_history_global",
        ["created_at"],
    )
    op.create_index(
        "ix_intent_definition_history_global_intent_id",
        "intent_definition_history_global",
        ["intent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intent_definition_history_global_intent_id",
        table_name="intent_definition_history_global",
    )
    op.drop_index(
        "ix_intent_definition_history_global_created_at",
        table_name="intent_definition_history_global",
    )
    op.drop_index(
        "ix_intent_definition_history_global_id",
        table_name="intent_definition_history_global",
    )
    op.drop_table("intent_definition_history_global")

    op.drop_index(
        "ix_intent_definitions_global_updated_at",
        table_name="intent_definitions_global",
    )
    op.drop_index(
        "ix_intent_definitions_global_intent_id",
        table_name="intent_definitions_global",
    )
    op.drop_index(
        "ix_intent_definitions_global_created_at",
        table_name="intent_definitions_global",
    )
    op.drop_index(
        "ix_intent_definitions_global_id",
        table_name="intent_definitions_global",
    )
    op.drop_table("intent_definitions_global")
