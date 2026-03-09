"""Registry invalidation events via PostgreSQL NOTIFY/LISTEN.

Provides cross-process cache invalidation so that all uvicorn workers
and Celery processes pick up admin changes without restart.

Usage in admin mutation endpoints::

    new_version = await bump_registry_version(session)
    await session.commit()
    await notify_registry_changed(session, new_version)
    await RegistryCache.invalidate()
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable

from sqlalchemy import func, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import RegistryVersion

logger = logging.getLogger(__name__)

REGISTRY_CHANNEL = "registry_invalidation"


async def bump_registry_version(session: AsyncSession) -> int:
    """Increment the global registry version counter.

    Must be called within the same transaction as the entity mutation
    so that the version bump is atomic with the data change.
    """
    result = await session.execute(
        update(RegistryVersion)
        .where(RegistryVersion.key == "global")
        .values(
            version=RegistryVersion.version + 1,
            updated_at=func.now(),
        )
        .returning(RegistryVersion.version)
    )
    new_version = result.scalar_one_or_none()
    if new_version is None:
        # First call — row doesn't exist yet, seed it
        session.add(RegistryVersion(key="global", version=1))
        await session.flush()
        return 1
    return int(new_version)


async def notify_registry_changed(session: AsyncSession, version: int) -> None:
    """Send a PG NOTIFY on the registry invalidation channel.

    Other processes listening on this channel will invalidate their
    local ``RegistryCache`` in response.
    """
    payload = json.dumps({"version": version, "timestamp": time.time()})
    try:
        await session.execute(
            text(f"NOTIFY {REGISTRY_CHANNEL}, :payload"),
            {"payload": payload},
        )
    except Exception:
        logger.warning("Failed to send PG NOTIFY for registry version %d", version)


async def listen_registry_changes(
    dsn: str,
    on_change: Callable[[int], Awaitable[None]],
) -> None:
    """Background task: listen for PG NOTIFY and invoke callback.

    This should be started as a long-running asyncio task during app
    lifespan.  It uses a raw asyncpg connection to LISTEN on the
    channel.

    Args:
        dsn: PostgreSQL connection string (asyncpg format).
        on_change: Async callback receiving the new version number.
    """
    try:
        import asyncpg
    except ImportError:
        logger.warning(
            "asyncpg not available — PG LISTEN for registry changes disabled"
        )
        return

    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(dsn)
        logger.info(
            "Listening for registry invalidation on channel %r", REGISTRY_CHANNEL
        )

        async def _on_notification(
            connection: asyncpg.Connection,
            pid: int,
            channel: str,
            payload_str: str,
        ) -> None:
            try:
                data = json.loads(payload_str)
                version = int(data.get("version", 0))
            except Exception:
                version = 0
            logger.info(
                "Received registry invalidation notification (version=%d)", version
            )
            try:
                await on_change(version)
            except Exception:
                logger.exception("Error in registry change callback")

        await conn.add_listener(REGISTRY_CHANNEL, _on_notification)

        # Keep connection alive until cancelled
        while True:
            await asyncio.sleep(60)

    except asyncio.CancelledError:
        logger.info("Registry listener task cancelled")
    except Exception:
        logger.exception("Registry listener failed")
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close()
