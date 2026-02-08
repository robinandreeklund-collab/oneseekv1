from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TraceSpanRead(BaseModel):
    id: str
    parent_id: str | None = None
    name: str
    kind: str
    status: str
    sequence: int
    start_ts: datetime
    end_ts: datetime | None = None
    duration_ms: int | None = None
    input: Any | None = None
    output: Any | None = None
    meta: Any | None = None


class TraceSessionRead(BaseModel):
    session_id: str
    thread_id: int
    message_id: int | None = None
    created_at: datetime
    ended_at: datetime | None = None
    spans: list[TraceSpanRead]


class TraceSessionAttachRequest(BaseModel):
    message_id: int
