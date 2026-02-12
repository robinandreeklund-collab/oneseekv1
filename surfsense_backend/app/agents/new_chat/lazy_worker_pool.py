"""Lazy worker pool - initializes workers on first use."""

from __future__ import annotations

import asyncio
from typing import Any

from langgraph.types import Checkpointer

from app.agents.new_chat.bigtool_workers import WorkerConfig, create_bigtool_worker


class LazyWorkerPool:
    """Pool that creates workers lazily on first access."""
    
    def __init__(
        self,
        configs: dict[str, WorkerConfig],
        llm: Any,
        dependencies: dict[str, Any],
        checkpointer: Checkpointer | None,
    ):
        self._configs = configs
        self._llm = llm
        self._dependencies = dependencies
        self._checkpointer = checkpointer
        self._workers: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {
            name: asyncio.Lock() for name in configs
        }
    
    async def get(self, name: str) -> Any | None:
        """Get or create a worker by name. Returns None if name not in configs."""
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
            )
            self._workers[name] = worker
            return worker
    
    def __contains__(self, name: str) -> bool:
        return name in self._configs
    
    def available_names(self) -> list[str]:
        return list(self._configs.keys())
