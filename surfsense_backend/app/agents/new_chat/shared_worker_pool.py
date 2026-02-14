"""Process-wide shared worker pool factory for supervisor graphs.

This module centralizes worker-pool lifecycle so graph builders don't create
ad-hoc pools inline. Pools are keyed by runtime dependencies to avoid leaking
state between unrelated requests.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from langgraph.types import Checkpointer

from app.agents.new_chat.bigtool_workers import WorkerConfig
from app.agents.new_chat.lazy_worker_pool import LazyWorkerPool

_MAX_SHARED_POOLS = 32
_shared_pool_lock = asyncio.Lock()
_shared_pools: OrderedDict["WorkerPoolKey", LazyWorkerPool] = OrderedDict()


@dataclass(frozen=True)
class WorkerPoolKey:
    llm_id: int
    checkpointer_id: int
    db_session_id: int
    connector_service_id: int
    search_space_id: str
    user_id: str
    thread_id: str
    checkpoint_ns: str
    firecrawl_fingerprint: str
    config_signature: tuple[
        tuple[
            str,
            tuple[tuple[str, ...], ...],
            tuple[tuple[str, ...], ...],
            int,
        ],
        ...,
    ]


def _fingerprint_firecrawl_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key:
        return ""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _serialize_worker_configs(
    configs: dict[str, WorkerConfig],
) -> tuple[
    tuple[
        str,
        tuple[tuple[str, ...], ...],
        tuple[tuple[str, ...], ...],
        int,
    ],
    ...,
]:
    normalized: list[
        tuple[
            str,
            tuple[tuple[str, ...], ...],
            tuple[tuple[str, ...], ...],
            int,
        ]
    ] = []
    for name in sorted(configs.keys()):
        config = configs[name]
        normalized.append(
            (
                name,
                tuple(tuple(ns) for ns in config.primary_namespaces),
                tuple(tuple(ns) for ns in config.fallback_namespaces),
                int(config.tool_limit),
            )
        )
    return tuple(normalized)


def _build_worker_pool_key(
    *,
    configs: dict[str, WorkerConfig],
    llm: Any,
    dependencies: dict[str, Any],
    checkpointer: Checkpointer | None,
) -> WorkerPoolKey:
    return WorkerPoolKey(
        llm_id=id(llm),
        checkpointer_id=id(checkpointer) if checkpointer is not None else 0,
        db_session_id=id(dependencies.get("db_session")),
        connector_service_id=id(dependencies.get("connector_service")),
        search_space_id=str(dependencies.get("search_space_id") or ""),
        user_id=str(dependencies.get("user_id") or ""),
        thread_id=str(dependencies.get("thread_id") or ""),
        checkpoint_ns=str(dependencies.get("checkpoint_ns") or ""),
        firecrawl_fingerprint=_fingerprint_firecrawl_key(
            dependencies.get("firecrawl_api_key")
        ),
        config_signature=_serialize_worker_configs(configs),
    )


async def get_or_create_shared_worker_pool(
    *,
    configs: dict[str, WorkerConfig],
    llm: Any,
    dependencies: dict[str, Any],
    checkpointer: Checkpointer | None,
) -> LazyWorkerPool:
    """Return a cached worker pool for the current runtime signature."""
    key = _build_worker_pool_key(
        configs=configs,
        llm=llm,
        dependencies=dependencies,
        checkpointer=checkpointer,
    )
    existing = _shared_pools.get(key)
    if existing is not None:
        _shared_pools.move_to_end(key)
        return existing

    async with _shared_pool_lock:
        existing = _shared_pools.get(key)
        if existing is not None:
            _shared_pools.move_to_end(key)
            return existing

        pool = LazyWorkerPool(
            configs=configs,
            llm=llm,
            dependencies=dependencies,
            checkpointer=checkpointer,
        )
        _shared_pools[key] = pool
        _shared_pools.move_to_end(key)
        while len(_shared_pools) > _MAX_SHARED_POOLS:
            _shared_pools.popitem(last=False)
        return pool


async def clear_shared_worker_pools() -> None:
    """Clear cached pools (useful in tests)."""
    async with _shared_pool_lock:
        _shared_pools.clear()
