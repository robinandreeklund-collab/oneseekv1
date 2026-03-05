"""Shared concurrency pool for parallel LLM and tool execution.

Provides a process-wide ``ForgePool`` that bounds the number of
concurrent async tasks (LLM calls, tool invocations, subagent runs)
to avoid overwhelming model endpoints and to maximize throughput
within rate-limit budgets.

Usage::

    from app.agents.new_chat.forge_pool import forge_pool

    # Run N coroutines with bounded concurrency
    results = await forge_pool.gather(coros)

    # Use as an async context manager for a single slot
    async with forge_pool.slot():
        result = await some_llm_call()

The pool is configured via the ``MAX_FORGE_CONCURRENCY`` environment
variable (default **12**).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_DEFAULT_MAX_CONCURRENCY = 12


class ForgePool:
    """Process-wide bounded concurrency pool for async tasks.

    Wraps an ``asyncio.Semaphore`` with convenience methods for
    batch execution (``gather``) and single-slot reservation (``slot``).

    The semaphore is created lazily on first use so that the pool
    works correctly even when the event loop is not yet running at
    import time.
    """

    def __init__(self, max_concurrency: int | None = None) -> None:
        self._max = max_concurrency or int(
            os.environ.get("MAX_FORGE_CONCURRENCY", str(_DEFAULT_MAX_CONCURRENCY))
        )
        self._sem: asyncio.Semaphore | None = None
        self._lock = None  # lazy asyncio.Lock
        # Metrics
        self._total_tasks = 0
        self._active_tasks = 0
        self._peak_active = 0

    @property
    def max_concurrency(self) -> int:
        return self._max

    @property
    def active_tasks(self) -> int:
        return self._active_tasks

    @property
    def peak_active(self) -> int:
        return self._peak_active

    def _ensure_sem(self) -> asyncio.Semaphore:
        """Create the semaphore lazily (must be called inside an event loop)."""
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._max)
        return self._sem

    @asynccontextmanager
    async def slot(self):
        """Acquire a single concurrency slot.

        Use this when you need fine-grained control over a single
        async operation::

            async with forge_pool.slot():
                result = await litellm.acompletion(...)
        """
        sem = self._ensure_sem()
        self._active_tasks += 1
        self._total_tasks += 1
        if self._active_tasks > self._peak_active:
            self._peak_active = self._active_tasks
        try:
            async with sem:
                yield
        finally:
            self._active_tasks -= 1

    async def gather(
        self,
        coros: list[Coroutine[Any, Any, T] | Awaitable[T]],
        *,
        return_exceptions: bool = True,
        label: str = "forge",
    ) -> list[T | BaseException]:
        """Run coroutines concurrently, bounded by the pool's semaphore.

        Semantically equivalent to ``asyncio.gather(*coros)`` but each
        coroutine waits for a pool slot before starting.

        Args:
            coros: Awaitables to execute.
            return_exceptions: If True, exceptions are returned in the
                result list instead of being raised.
            label: Label for log messages.

        Returns:
            List of results (or exceptions if *return_exceptions* is True).
        """
        if not coros:
            return []

        sem = self._ensure_sem()
        t0 = time.monotonic()
        n = len(coros)

        async def _guarded(idx: int, coro: Awaitable[T]) -> T:
            self._active_tasks += 1
            self._total_tasks += 1
            if self._active_tasks > self._peak_active:
                self._peak_active = self._active_tasks
            try:
                async with sem:
                    return await coro  # type: ignore[misc]
            finally:
                self._active_tasks -= 1

        results = await asyncio.gather(
            *[_guarded(i, c) for i, c in enumerate(coros)],
            return_exceptions=return_exceptions,
        )

        elapsed = (time.monotonic() - t0) * 1000
        ok_count = sum(1 for r in results if not isinstance(r, BaseException))
        logger.info(
            "forge_pool[%s]: %d/%d ok, %.0fms, peak_active=%d, max=%d",
            label,
            ok_count,
            n,
            elapsed,
            self._peak_active,
            self._max,
        )

        return results  # type: ignore[return-value]

    def stats(self) -> dict[str, Any]:
        """Return pool statistics for observability."""
        return {
            "max_concurrency": self._max,
            "active_tasks": self._active_tasks,
            "peak_active": self._peak_active,
            "total_tasks": self._total_tasks,
        }


# ── Process-wide singleton ──────────────────────────────────────────

forge_pool = ForgePool()
