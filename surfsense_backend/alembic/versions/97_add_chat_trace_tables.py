"""Add chat trace tables

Revision ID: 97
Revises: 96
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "97"
down_revision: str | None = "96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_trace_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["new_chat_threads.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["new_chat_messages.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("session_id", name="uq_chat_trace_session_id"),
    )
    op.create_index(
        "ix_chat_trace_sessions_id",
        "chat_trace_sessions",
        ["id"],
    )
    op.create_index(
        "ix_chat_trace_sessions_session_id",
        "chat_trace_sessions",
        ["session_id"],
    )
    op.create_index(
        "ix_chat_trace_sessions_thread_id",
        "chat_trace_sessions",
        ["thread_id"],
    )
    op.create_index(
        "ix_chat_trace_sessions_message_id",
        "chat_trace_sessions",
        ["message_id"],
    )
    op.create_index(
        "ix_chat_trace_sessions_created_by_id",
        "chat_trace_sessions",
        ["created_by_id"],
    )

    op.create_table(
        "chat_trace_spans",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("span_id", sa.String(length=80), nullable=False),
        sa.Column("parent_span_id", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="running",
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("start_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("end_ts", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_trace_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "session_id",
            "span_id",
            name="uq_chat_trace_span_session_span",
        ),
    )
    op.create_index(
        "ix_chat_trace_spans_id",
        "chat_trace_spans",
        ["id"],
    )
    op.create_index(
        "ix_chat_trace_spans_session_id",
        "chat_trace_spans",
        ["session_id"],
    )
    op.create_index(
        "ix_chat_trace_spans_span_id",
        "chat_trace_spans",
        ["span_id"],
    )
    op.create_index(
        "ix_chat_trace_spans_parent_span_id",
        "chat_trace_spans",
        ["parent_span_id"],
    )
    op.create_index(
        "ix_chat_trace_spans_sequence",
        "chat_trace_spans",
        ["sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_trace_spans_sequence", table_name="chat_trace_spans")
    op.drop_index("ix_chat_trace_spans_parent_span_id", table_name="chat_trace_spans")
    op.drop_index("ix_chat_trace_spans_span_id", table_name="chat_trace_spans")
    op.drop_index("ix_chat_trace_spans_session_id", table_name="chat_trace_spans")
    op.drop_index("ix_chat_trace_spans_id", table_name="chat_trace_spans")
    op.drop_table("chat_trace_spans")

    op.drop_index(
        "ix_chat_trace_sessions_created_by_id",
        table_name="chat_trace_sessions",
    )
    op.drop_index(
        "ix_chat_trace_sessions_message_id",
        table_name="chat_trace_sessions",
    )
    op.drop_index(
        "ix_chat_trace_sessions_thread_id",
        table_name="chat_trace_sessions",
    )
    op.drop_index(
        "ix_chat_trace_sessions_session_id",
        table_name="chat_trace_sessions",
    )
    op.drop_index("ix_chat_trace_sessions_id", table_name="chat_trace_sessions")
    op.drop_table("chat_trace_sessions")
