"""GraphHolder — hot-swappable compiled graph container.

Holds a reference to the latest compiled LangGraph ``StateGraph`` and
replaces it atomically when the ``GraphRegistry`` version changes.
Workers call ``GraphHolder.get()`` at session start to obtain the
current graph; if the registry has been bumped, the graph is rebuilt
from the new registry snapshot before being returned.

This is intentionally separate from ``RegistryCache`` because the
compiled graph is an expensive artifact that should only be rebuilt
when the registry actually changes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.services.graph_registry_service import GraphRegistry, RegistryCache

logger = logging.getLogger(__name__)


class GraphHolder:
    """Process-level singleton for the compiled LangGraph graph.

    The holder stores a ``(graph, registry_version)`` pair.  When a
    caller requests the graph and the registry has been bumped, the
    holder recompiles from the latest ``GraphRegistry`` snapshot.
    """

    _graph: Any | None = None
    _registry_version: int = 0
    _built_at: float = 0.0
    _lock: asyncio.Lock | None = None
    _build_fn: Any | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    def set_build_fn(cls, fn: Any) -> None:
        """Register the graph-build callback.

        The function must accept ``(registry: GraphRegistry, **kwargs)``
        and return a compiled graph object.  It is called whenever the
        registry version changes.
        """
        cls._build_fn = fn
        logger.info("GraphHolder build function registered")

    @classmethod
    async def get(
        cls,
        session: Any,
        **build_kwargs: Any,
    ) -> Any:
        """Return the current compiled graph, rebuilding if needed.

        Args:
            session: SQLAlchemy ``AsyncSession`` for registry lookup.
            **build_kwargs: Extra keyword arguments forwarded to the
                build function (LLM, dependencies, etc.).

        Returns:
            The compiled graph (type depends on the build function).

        Raises:
            RuntimeError: If no build function has been registered.
        """
        registry = await RegistryCache.get(session)
        if cls._graph is not None and registry.version == cls._registry_version:
            return cls._graph

        async with cls._get_lock():
            # Double-check after lock acquisition
            registry = await RegistryCache.get(session)
            if cls._graph is not None and registry.version == cls._registry_version:
                return cls._graph
            return await cls._rebuild(registry, **build_kwargs)

    @classmethod
    async def _rebuild(
        cls,
        registry: GraphRegistry,
        **build_kwargs: Any,
    ) -> Any:
        """Compile a new graph from the given registry snapshot."""
        if cls._build_fn is None:
            raise RuntimeError("GraphHolder.set_build_fn() must be called before get()")
        logger.info(
            "GraphHolder rebuilding graph for registry version %d …",
            registry.version,
        )
        start = time.monotonic()
        graph = await cls._build_fn(registry=registry, **build_kwargs)
        elapsed = time.monotonic() - start
        cls._graph = graph
        cls._registry_version = registry.version
        cls._built_at = time.monotonic()
        logger.info(
            "GraphHolder rebuilt graph in %.2fs (version=%d)",
            elapsed,
            registry.version,
        )
        return graph

    @classmethod
    async def invalidate(cls) -> None:
        """Force next ``get()`` to rebuild.

        Typically called from the PG LISTEN callback.
        """
        cls._graph = None
        cls._registry_version = 0
        logger.info("GraphHolder invalidated — will rebuild on next access")

    @classmethod
    def current_version(cls) -> int:
        """Return the registry version of the currently held graph."""
        return cls._registry_version

    @classmethod
    def is_ready(cls) -> bool:
        """Return True if a compiled graph is available."""
        return cls._graph is not None
