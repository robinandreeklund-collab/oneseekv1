"""
PostgreSQL-based checkpointer for LangGraph agents.

This module provides a persistent checkpointer using AsyncPostgresSaver
that stores conversation state in the PostgreSQL database.
"""

import asyncio
import re
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import config

# Global checkpointer instance (initialized lazily)
_checkpointer: AsyncPostgresSaver | None = None
_checkpointer_context = None  # Store the context manager for cleanup
_checkpointer_initialized: bool = False
_checkpointer_lock = asyncio.Lock()


def build_checkpoint_namespace(
    *,
    user_id: str | None,
    flow: str = "new_chat_v2",
) -> str:
    """Build a stable checkpoint namespace for graph/state isolation."""
    flow_token = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(flow or "new_chat_v2")).strip("_")
    user_token = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(user_id or "anonymous")).strip("_")
    if not flow_token:
        flow_token = "new_chat_v2"
    if not user_token:
        user_token = "anonymous"
    return f"{flow_token}_user_{user_token}"


async def namespace_has_checkpoints(
    *,
    checkpointer: Any,
    thread_id: str | int,
    checkpoint_ns: str | None = None,
) -> bool:
    """Return True if at least one checkpoint exists in the namespace."""
    configurable: dict[str, Any] = {"thread_id": str(thread_id)}
    normalized_ns = str(checkpoint_ns or "").strip()
    if normalized_ns:
        configurable["checkpoint_ns"] = normalized_ns
    config = {"configurable": configurable}
    try:
        async for _tuple in checkpointer.alist(config):
            return True
    except Exception:
        return False
    return False


async def resolve_checkpoint_namespace_for_thread(
    *,
    checkpointer: Any,
    thread_id: str | int,
    preferred_namespace: str | None,
) -> str:
    """Prefer new namespace but fall back to legacy namespace when needed."""
    preferred = str(preferred_namespace or "").strip()
    if preferred:
        if await namespace_has_checkpoints(
            checkpointer=checkpointer,
            thread_id=thread_id,
            checkpoint_ns=preferred,
        ):
            return preferred
    if await namespace_has_checkpoints(
        checkpointer=checkpointer,
        thread_id=thread_id,
        checkpoint_ns=None,
    ):
        return ""
    return preferred


def get_postgres_connection_string() -> str:
    """
    Convert the async DATABASE_URL to a sync postgres connection string for psycopg3.

    The DATABASE_URL is typically in format:
    postgresql+asyncpg://user:pass@host:port/dbname

    We need to convert it to:
    postgresql://user:pass@host:port/dbname
    """
    db_url = config.DATABASE_URL

    # Handle asyncpg driver prefix
    if db_url.startswith("postgresql+asyncpg://"):
        return db_url.replace("postgresql+asyncpg://", "postgresql://")

    # Handle other async prefixes
    if "+asyncpg" in db_url:
        return db_url.replace("+asyncpg", "")

    return db_url


async def get_checkpointer() -> AsyncPostgresSaver:
    """
    Get or create the global AsyncPostgresSaver instance.

    This function:
    1. Creates the checkpointer if it doesn't exist
    2. Sets up the required database tables on first call
    3. Returns the cached instance on subsequent calls

    Returns:
        AsyncPostgresSaver: The configured checkpointer instance
    """
    global _checkpointer, _checkpointer_context, _checkpointer_initialized

    if _checkpointer is not None and _checkpointer_initialized:
        return _checkpointer

    async with _checkpointer_lock:
        if _checkpointer is None:
            conn_string = get_postgres_connection_string()
            # from_conn_string returns an async context manager
            # We need to enter the context to get the actual checkpointer
            _checkpointer_context = AsyncPostgresSaver.from_conn_string(conn_string)
            _checkpointer = await _checkpointer_context.__aenter__()

        # Setup tables on first call (idempotent)
        if not _checkpointer_initialized:
            await _checkpointer.setup()
            _checkpointer_initialized = True

        return _checkpointer


async def setup_checkpointer_tables() -> None:
    """
    Explicitly setup the checkpointer tables.

    This can be called during application startup to ensure
    tables exist before any agent calls.
    """
    await get_checkpointer()
    print("[Checkpointer] PostgreSQL checkpoint tables ready")


async def close_checkpointer() -> None:
    """
    Close the checkpointer connection.

    This should be called during application shutdown.
    """
    global _checkpointer, _checkpointer_context, _checkpointer_initialized

    async with _checkpointer_lock:
        if _checkpointer_context is not None:
            await _checkpointer_context.__aexit__(None, None, None)
            _checkpointer = None
            _checkpointer_context = None
            _checkpointer_initialized = False
            print("[Checkpointer] PostgreSQL connection closed")
