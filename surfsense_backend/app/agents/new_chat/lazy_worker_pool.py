"""Lazy worker pool - initializes workers on first use."""

from __future__ import annotations

import asyncio
from typing import Any

from langgraph.types import Checkpointer

from app.agents.new_chat.bigtool_workers import WorkerConfig, create_bigtool_worker


class LazyWorkerPool:
    """Pool that creates workers lazily on first access.
    
    This reduces startup time by deferring worker initialization until needed.
    Thread-safe via async locks to prevent race conditions during concurrent access.
    
    Attributes:
        _configs: Worker configuration mapping
        _workers: Cache of initialized workers
        _locks: Per-worker locks for thread-safe initialization
    """
    
    def __init__(
        self,
        configs: dict[str, WorkerConfig],
        llm: Any,
        dependencies: dict[str, Any],
        checkpointer: Checkpointer | None,
        stub_tool_registry: dict[str, Any] | None = None,
    ):
        """Initialize the lazy worker pool.
        
        Args:
            configs: Worker configurations by name
            llm: Language model instance to use for workers
            dependencies: Shared dependencies for worker initialization
            checkpointer: Optional checkpointer for state persistence
            stub_tool_registry: Optional stub tools for evaluation mode (no real API calls)
        """
        self._configs = configs
        self._llm = llm
        self._dependencies = dependencies
        self._checkpointer = checkpointer
        self._stub_tool_registry = stub_tool_registry
        self._workers: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {
            name: asyncio.Lock() for name in configs
        }
    
    async def get(self, name: str) -> Any | None:
        """Get or create a worker by name.
        
        Uses double-checked locking pattern to ensure thread-safe initialization
        while minimizing lock contention for already-initialized workers.
        
        Args:
            name: Worker name (e.g., 'statistics', 'bolag', 'trafik')
            
        Returns:
            Worker instance if found, None if name not in configs
        """
        if name not in self._configs:
            return None
        
        if name in self._workers:
            return self._workers[name]
        
        async with self._locks[name]:
            # Double-check after acquiring lock
            if name in self._workers:
                return self._workers[name]
            
            worker = await create_bigtool_worker(
                llm=self._llm,
                dependencies=self._dependencies,
                checkpointer=self._checkpointer,
                config=self._configs[name],
                stub_tool_registry=self._stub_tool_registry,
            )
            self._workers[name] = worker
            return worker
    
    def __contains__(self, name: str) -> bool:
        return name in self._configs
    
    def available_names(self) -> list[str]:
        return list(self._configs.keys())
