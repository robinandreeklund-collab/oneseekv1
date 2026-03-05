"""Add intent domain hierarchy tables (domain → agent → tool) and registry version

Revision ID: 111
Revises: 110
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "111"
down_revision: str | None = "110"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_intent_domains() -> None:
    op.create_table(
        "intent_domains",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("domain_id", sa.String(length=80), nullable=False),
        sa.Column(
            "definition_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("domain_id", name="uq_intent_domains_domain_id"),
    )
    op.create_index("ix_intent_domains_id", "intent_domains", ["id"])
    op.create_index("ix_intent_domains_domain_id", "intent_domains", ["domain_id"])
    op.create_index("ix_intent_domains_created_at", "intent_domains", ["created_at"])
    op.create_index("ix_intent_domains_updated_at", "intent_domains", ["updated_at"])


def _create_intent_domain_history() -> None:
    op.create_table(
        "intent_domain_history",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("domain_id", sa.String(length=80), nullable=False),
        sa.Column(
            "previous_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "new_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_intent_domain_history_id", "intent_domain_history", ["id"])
    op.create_index(
        "ix_intent_domain_history_domain_id", "intent_domain_history", ["domain_id"]
    )
    op.create_index(
        "ix_intent_domain_history_created_at", "intent_domain_history", ["created_at"]
    )


def _create_agent_definitions() -> None:
    op.create_table(
        "agent_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("domain_id", sa.String(length=80), nullable=False),
        sa.Column(
            "definition_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["domain_id"], ["intent_domains.domain_id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("agent_id", name="uq_agent_definitions_agent_id"),
    )
    op.create_index("ix_agent_definitions_id", "agent_definitions", ["id"])
    op.create_index("ix_agent_definitions_agent_id", "agent_definitions", ["agent_id"])
    op.create_index(
        "ix_agent_definitions_domain_id", "agent_definitions", ["domain_id"]
    )
    op.create_index(
        "ix_agent_definitions_created_at", "agent_definitions", ["created_at"]
    )
    op.create_index(
        "ix_agent_definitions_updated_at", "agent_definitions", ["updated_at"]
    )


def _create_agent_definition_history() -> None:
    op.create_table(
        "agent_definition_history",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column(
            "previous_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "new_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_agent_definition_history_id", "agent_definition_history", ["id"]
    )
    op.create_index(
        "ix_agent_definition_history_agent_id", "agent_definition_history", ["agent_id"]
    )
    op.create_index(
        "ix_agent_definition_history_created_at",
        "agent_definition_history",
        ["created_at"],
    )


def _create_tool_definitions() -> None:
    op.create_table(
        "tool_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("tool_id", sa.String(length=160), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column(
            "definition_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agent_definitions.agent_id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tool_id", name="uq_tool_definitions_tool_id"),
    )
    op.create_index("ix_tool_definitions_id", "tool_definitions", ["id"])
    op.create_index("ix_tool_definitions_tool_id", "tool_definitions", ["tool_id"])
    op.create_index("ix_tool_definitions_agent_id", "tool_definitions", ["agent_id"])
    op.create_index(
        "ix_tool_definitions_created_at", "tool_definitions", ["created_at"]
    )
    op.create_index(
        "ix_tool_definitions_updated_at", "tool_definitions", ["updated_at"]
    )


def _create_tool_definition_history() -> None:
    op.create_table(
        "tool_definition_history",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("tool_id", sa.String(length=160), nullable=False),
        sa.Column(
            "previous_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "new_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_tool_definition_history_id", "tool_definition_history", ["id"])
    op.create_index(
        "ix_tool_definition_history_tool_id", "tool_definition_history", ["tool_id"]
    )
    op.create_index(
        "ix_tool_definition_history_created_at",
        "tool_definition_history",
        ["created_at"],
    )


def _create_registry_version() -> None:
    op.create_table(
        "registry_version",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("key", sa.String(length=40), nullable=False, server_default="global"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("key", name="uq_registry_version_key"),
    )
    op.create_index("ix_registry_version_id", "registry_version", ["id"])
    op.create_index("ix_registry_version_key", "registry_version", ["key"])
    op.create_index(
        "ix_registry_version_created_at", "registry_version", ["created_at"]
    )
    op.create_index(
        "ix_registry_version_updated_at", "registry_version", ["updated_at"]
    )

    # Seed the initial version row
    op.execute(
        "INSERT INTO registry_version (key, version, updated_at, created_at) "
        "VALUES ('global', 0, NOW(), NOW())"
    )


def upgrade() -> None:
    _create_intent_domains()
    _create_intent_domain_history()
    _create_agent_definitions()
    _create_agent_definition_history()
    _create_tool_definitions()
    _create_tool_definition_history()
    _create_registry_version()


def downgrade() -> None:
    op.drop_table("tool_definition_history")
    op.drop_table("tool_definitions")
    op.drop_table("agent_definition_history")
    op.drop_table("agent_definitions")
    op.drop_table("intent_domain_history")
    op.drop_table("intent_domains")
    op.drop_table("registry_version")
