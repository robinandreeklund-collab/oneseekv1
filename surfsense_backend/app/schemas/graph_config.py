"""Pydantic schemas for the graph configuration admin API."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Domain schemas ────────────────────────────────────────────────────


class DomainPayload(BaseModel):
    domain_id: str = Field(..., min_length=1, max_length=80)
    label: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    priority: int = Field(default=500, ge=1, le=10000)
    enabled: bool = True
    fallback_route: str = "kunskap"
    citations_enabled: bool = True
    main_identifier: str = ""
    core_activity: str = ""
    unique_scope: str = ""
    geographic_scope: str = ""
    excludes: list[str] = Field(default_factory=list)
    complexity_override: str | None = None
    execution_strategy_hint: str | None = None


class DomainResponse(BaseModel):
    status: str = "ok"
    version: int = 0
    domain: dict = Field(default_factory=dict)


class DomainDeleteResponse(BaseModel):
    status: str = "ok"
    version: int = 0
    deleted: bool = False


# ── Agent schemas ─────────────────────────────────────────────────────


class WorkerConfigPayload(BaseModel):
    max_concurrency: int = Field(default=4, ge=1, le=100)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)


class AgentPayload(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=80)
    domain_id: str = Field(..., min_length=1, max_length=80)
    label: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    priority: int = Field(default=500, ge=1, le=10000)
    enabled: bool = True
    prompt_key: str = ""
    prompt_text: str | None = None
    primary_namespaces: list[list[str]] = Field(default_factory=list)
    fallback_namespaces: list[list[str]] = Field(default_factory=list)
    worker_config: WorkerConfigPayload = Field(default_factory=WorkerConfigPayload)
    main_identifier: str = ""
    core_activity: str = ""
    unique_scope: str = ""
    geographic_scope: str = ""
    excludes: list[str] = Field(default_factory=list)


class AgentResponse(BaseModel):
    status: str = "ok"
    version: int = 0
    agent: dict = Field(default_factory=dict)


class AgentDeleteResponse(BaseModel):
    status: str = "ok"
    version: int = 0
    deleted: bool = False


# ── Tool schemas ──────────────────────────────────────────────────────


class ToolPayload(BaseModel):
    tool_id: str = Field(..., min_length=1, max_length=160)
    agent_id: str = Field(..., min_length=1, max_length=80)
    label: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    example_queries: list[str] = Field(default_factory=list)
    category: str = ""
    enabled: bool = True
    priority: int = Field(default=500, ge=1, le=10000)
    namespace: list[str] = Field(default_factory=list)
    main_identifier: str = ""
    core_activity: str = ""
    unique_scope: str = ""
    geographic_scope: str = ""
    excludes: list[str] = Field(default_factory=list)
    callable_path: str | None = None


class ToolResponse(BaseModel):
    status: str = "ok"
    version: int = 0
    tool: dict = Field(default_factory=dict)


class ToolDeleteResponse(BaseModel):
    status: str = "ok"
    version: int = 0
    deleted: bool = False


# ── Registry schemas ──────────────────────────────────────────────────


class RegistrySnapshotResponse(BaseModel):
    version: int = 0
    domain_count: int = 0
    agent_count: int = 0
    tool_count: int = 0
    domains: list[dict] = Field(default_factory=list)
    agents_by_domain: dict[str, list[dict]] = Field(default_factory=dict)
    tools_by_agent: dict[str, list[dict]] = Field(default_factory=dict)


class RegistryReloadResponse(BaseModel):
    status: str = "ok"
    version: int = 0
    domain_count: int = 0
    agent_count: int = 0
    tool_count: int = 0
