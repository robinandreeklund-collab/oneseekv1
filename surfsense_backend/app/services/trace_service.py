from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import ChatTraceSession, ChatTraceSpan
from app.services.new_streaming_service import VercelStreamingService

logger = logging.getLogger(__name__)


def _safe_payload(value: Any) -> Any | None:
    if value is None:
        return None
    try:
        return jsonable_encoder(value)
    except Exception:
        return str(value)


class TraceRecorder:
    def __init__(
        self,
        db_session: AsyncSession,
        trace_session: ChatTraceSession,
        streaming_service: VercelStreamingService,
        root_name: str,
        root_input: Any | None = None,
        root_meta: dict[str, Any] | None = None,
    ):
        self.db_session = db_session
        self.trace_session = trace_session
        self.streaming_service = streaming_service
        self.sequence = 0
        self.lock = asyncio.Lock()
        self.span_cache: dict[str, ChatTraceSpan] = {}
        self.span_output_buffers: dict[str, Any] = {}
        self.root_span_id = f"root-{uuid4().hex}"
        self.root_name = root_name
        self.root_input = root_input
        self.root_meta = root_meta or {}

    async def emit_session_start(self) -> str:
        return self.streaming_service.format_trace_session(
            trace_session_id=self.trace_session.session_id,
            thread_id=self.trace_session.thread_id,
        )

    async def start_root_span(self) -> str | None:
        return await self.start_span(
            span_id=self.root_span_id,
            name=self.root_name,
            kind="chain",
            parent_id=None,
            input_data=self.root_input,
            meta=self.root_meta,
        )

    async def start_span(
        self,
        span_id: str,
        name: str,
        kind: str,
        parent_id: str | None = None,
        input_data: Any | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str | None:
        if not span_id:
            return None
        if span_id in self.span_cache:
            return None
        async with self.lock:
            self.sequence += 1
            sequence = self.sequence
            start_ts = datetime.now(UTC)
            parent_span_id = parent_id
            if parent_span_id is None and span_id != self.root_span_id:
                parent_span_id = self.root_span_id
            span = ChatTraceSpan(
                session_id=self.trace_session.id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                name=name or "unknown",
                kind=kind or "chain",
                status="running",
                sequence=sequence,
                start_ts=start_ts,
                input=_safe_payload(input_data),
                meta=_safe_payload(meta),
            )
            try:
                self.db_session.add(span)
                await self.db_session.commit()
                await self.db_session.refresh(span)
                self.span_cache[span_id] = span
            except Exception:
                await self.db_session.rollback()
                logger.exception("[trace] Failed to persist span start")
                return None
        payload = self._serialize_span(span)
        return self.streaming_service.format_trace_span(
            trace_session_id=self.trace_session.session_id,
            event="start",
            span=payload,
        )

    async def append_span_output(self, span_id: str, output_delta: Any) -> str | None:
        if not span_id:
            return None
        if span_id not in self.span_cache:
            return None
        current = self.span_output_buffers.get(span_id)
        if isinstance(current, str) and isinstance(output_delta, str):
            updated = current + output_delta
        elif current is None:
            updated = output_delta
        else:
            try:
                updated = str(current) + str(output_delta)
            except Exception:
                updated = output_delta
        self.span_output_buffers[span_id] = updated
        span = self.span_cache.get(span_id)
        if not span:
            return None
        payload = self._serialize_span(
            span,
            output_override=_safe_payload(updated),
            status_override="running",
        )
        return self.streaming_service.format_trace_span(
            trace_session_id=self.trace_session.session_id,
            event="update",
            span=payload,
        )

    async def end_span(
        self,
        span_id: str,
        output_data: Any | None = None,
        status: str = "completed",
        meta: dict[str, Any] | None = None,
    ) -> str | None:
        if not span_id:
            return None
        span = self.span_cache.get(span_id)
        if not span:
            return None
        end_ts = datetime.now(UTC)
        duration_ms = int((end_ts - span.start_ts).total_seconds() * 1000)
        final_output = (
            output_data
            if output_data is not None
            else self.span_output_buffers.get(span_id)
        )
        values = {
            "status": status,
            "end_ts": end_ts,
            "duration_ms": duration_ms,
            "output": _safe_payload(final_output),
        }
        if meta:
            values["meta"] = _safe_payload(meta)
        async with self.lock:
            try:
                await self.db_session.execute(
                    update(ChatTraceSpan)
                    .where(ChatTraceSpan.id == span.id)
                    .values(**values)
                )
                await self.db_session.commit()
            except Exception:
                await self.db_session.rollback()
                logger.exception("[trace] Failed to persist span end")
        span.status = status
        span.end_ts = end_ts
        span.duration_ms = duration_ms
        span.output = values.get("output")
        if meta:
            span.meta = values.get("meta")
        payload = self._serialize_span(span)
        return self.streaming_service.format_trace_span(
            trace_session_id=self.trace_session.session_id,
            event="end",
            span=payload,
        )

    async def end_session(self) -> None:
        async with self.lock:
            try:
                await self.db_session.execute(
                    update(ChatTraceSession)
                    .where(ChatTraceSession.id == self.trace_session.id)
                    .values(ended_at=datetime.now(UTC))
                )
                await self.db_session.commit()
            except Exception:
                await self.db_session.rollback()
                logger.exception("[trace] Failed to mark session ended")

    def _serialize_span(
        self,
        span: ChatTraceSpan,
        output_override: Any | None = None,
        status_override: str | None = None,
    ) -> dict[str, Any]:
        end_ts = span.end_ts.isoformat() if span.end_ts else None
        return {
            "id": span.span_id,
            "parent_id": span.parent_span_id,
            "name": span.name,
            "kind": span.kind,
            "status": status_override or span.status,
            "sequence": span.sequence,
            "start_ts": span.start_ts.isoformat(),
            "end_ts": end_ts,
            "duration_ms": span.duration_ms,
            "input": span.input,
            "output": output_override if output_override is not None else span.output,
            "meta": span.meta,
        }
