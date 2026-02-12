from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.agents.new_chat.tools.trafikverket_definitions import (
    TRAFIKVERKET_TOOL_DEFINITION_MAP,
    TRAFIKVERKET_TOOL_DEFINITIONS,
)
from app.agents.new_chat.tools.trafikverket_types import (
    TrafikverketToolDefinition,
    TrafikverketToolInput,
    TrafikverketIntent,
    TrafikverketToolResult,
    TrafikverketToolType,
)
from app.agents.new_chat.tools.trafikverket_validators import (
    has_results,
    infer_filter_value,
    infer_intent,
    infer_time_window,
    intent_to_tool_id,
    normalize_limit,
    normalize_tool_input,
)
from app.services.connector_service import ConnectorService
from app.services.trafikverket_service_v2 import (
    TRAFIKVERKET_SOURCE,
    TrafikverketServiceV2,
)

logger = logging.getLogger(__name__)


def _build_payload(
    *,
    tool_name: str,
    base_path: str,
    query: dict[str, Any],
    data: dict[str, Any] | None,
    cached: bool,
    resolved_filter_field: str | None,
    resolved_filter_value: str | None,
    resolved_intent: str | None = None,
    error: str | None = None,
    error_type: str | None = None,
) -> TrafikverketToolResult:
    payload: TrafikverketToolResult = {
        "status": "success" if not error else "error",
        "tool": tool_name,
        "source": TRAFIKVERKET_SOURCE,
        "base_path": base_path,
        "query": query,
        "cached": cached,
        "data": data,
        "error": error,
        "error_type": error_type,
        "resolved_filter_field": resolved_filter_field,
        "resolved_filter_value": resolved_filter_value,
        "resolved_intent": resolved_intent,
    }
    return payload


async def _ingest_output(
    *,
    connector_service: ConnectorService | None,
    tool_name: str,
    title: str,
    payload: dict[str, Any],
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
) -> None:
    if not connector_service:
        return
    await connector_service.ingest_tool_output(
        tool_name=tool_name,
        tool_output=payload,
        title=title,
        metadata={
            "source": TRAFIKVERKET_SOURCE,
            "base_path": payload.get("base_path"),
            "query": payload.get("query"),
            "resolved_filter_field": payload.get("resolved_filter_field"),
            "resolved_filter_value": payload.get("resolved_filter_value"),
        },
        user_id=user_id,
        origin_search_space_id=search_space_id,
        thread_id=thread_id,
    )


class TrafikverketToolFactory:
    def __init__(
        self,
        *,
        service: TrafikverketServiceV2,
        connector_service: ConnectorService | None,
        search_space_id: int,
        user_id: str | None,
        thread_id: int | None,
    ) -> None:
        self.service = service
        self.connector_service = connector_service
        self.search_space_id = search_space_id
        self.user_id = user_id
        self.thread_id = thread_id

    async def _run_definition(
        self,
        definition: TrafikverketToolDefinition,
        raw_input: TrafikverketToolInput,
    ) -> TrafikverketToolResult:
        normalized = normalize_tool_input(definition, raw_input)
        limit = normalize_limit(normalized.get("limit"), default=definition.default_limit)
        filter_value = infer_filter_value(definition, normalized)
        time_window = normalized.get("time_window_hours")
        if definition.requires_filter and not filter_value:
            return _build_payload(
                tool_name=definition.tool_id,
                base_path=definition.base_path,
                query={**normalized, "limit": limit},
                data=None,
                cached=False,
                resolved_filter_field=None,
                resolved_filter_value=None,
                error="Missing required filter input (road/station/region).",
                error_type="validation",
            )

        try:
            data, cached, used_field = await self.service.query(
                objecttype=definition.objecttype or "",
                schema_version=definition.schema_version,
                namespace=definition.namespace,
                filter_fields=definition.filter_fields,
                filter_value=filter_value,
                raw_filter=normalized.get("raw_filter"),
                limit=limit,
                time_window_hours=time_window,
                allow_unfiltered=not definition.requires_filter,
            )
        except Exception as exc:
            logger.warning(
                "Trafikverket tool failed",
                extra={
                    "tool": definition.tool_id,
                    "objecttype": definition.objecttype,
                    "namespace": definition.namespace,
                    "filter_value": filter_value,
                    "error": str(exc),
                },
            )
            return _build_payload(
                tool_name=definition.tool_id,
                base_path=definition.base_path,
                query={**normalized, "limit": limit},
                data=None,
                cached=False,
                resolved_filter_field=None,
                resolved_filter_value=filter_value,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        payload = _build_payload(
            tool_name=definition.tool_id,
            base_path=definition.base_path,
            query={**normalized, "limit": limit},
            data=data,
            cached=cached,
            resolved_filter_field=used_field,
            resolved_filter_value=filter_value,
        )
        logger.info(
            "Trafikverket tool success",
            extra={
                "tool": definition.tool_id,
                "objecttype": definition.objecttype,
                "namespace": definition.namespace,
                "filter_field": used_field,
                "filter_value": filter_value,
                "limit": limit,
                "cached": cached,
            },
        )
        await _ingest_output(
            connector_service=self.connector_service,
            tool_name=definition.tool_id,
            title=f"Trafikverket {definition.name}",
            payload=payload,
            search_space_id=self.search_space_id,
            user_id=self.user_id,
            thread_id=self.thread_id,
        )
        return payload

    async def _run_with_fallbacks(
        self,
        definition: TrafikverketToolDefinition,
        raw_input: TrafikverketToolInput,
    ) -> TrafikverketToolResult:
        payload = await self._run_definition(definition, raw_input)
        if payload.get("status") == "success" and payload.get("data"):
            if has_results(payload["data"]):
                return payload
        for fallback_id in definition.fallback_tool_ids:
            fallback_def = TRAFIKVERKET_TOOL_DEFINITION_MAP.get(fallback_id)
            if not fallback_def:
                continue
            fallback_payload = await self._run_definition(fallback_def, raw_input)
            if fallback_payload.get("status") == "success" and fallback_payload.get("data"):
                if has_results(fallback_payload["data"]):
                    fallback_payload["resolved_intent"] = fallback_id
                    return fallback_payload
        return payload

    def build_tool(self, definition: TrafikverketToolDefinition) -> BaseTool:
        if definition.tool_type == TrafikverketToolType.AUTO:

            @tool(definition.tool_id, description=definition.description)
            async def trafikverket_auto(
                query: str,
                limit: int | None = 10,
                region: str | None = None,
                road: str | None = None,
                station: str | None = None,
                kamera_id: str | None = None,
                time_window_hours: int | None = None,
                intent: str | None = None,
                filter: dict[str, Any] | None = None,
                from_location: str | None = None,
                to_location: str | None = None,
            ) -> TrafikverketToolResult:
                if time_window_hours is None:
                    time_window_hours = infer_time_window(query)
                raw_input: TrafikverketToolInput = {
                    "query": query,
                    "limit": limit,
                    "region": region,
                    "road": road,
                    "station": station,
                    "kamera_id": kamera_id,
                    "time_window_hours": time_window_hours,
                    "intent": intent,
                    "filter": filter,
                    "from_location": from_location,
                    "to_location": to_location,
                }
                resolved_intent = infer_intent(query)
                if intent:
                    try:
                        resolved_intent = TrafikverketIntent(intent)
                    except Exception:
                        pass
                tool_id = intent_to_tool_id(resolved_intent)
                definition_to_use = (
                    TRAFIKVERKET_TOOL_DEFINITION_MAP.get(tool_id)
                    if tool_id
                    else None
                )
                if not definition_to_use:
                    definition_to_use = TRAFIKVERKET_TOOL_DEFINITION_MAP.get(
                        "trafikverket_trafikinfo_storningar"
                    )
                if not definition_to_use:
                    return _build_payload(
                        tool_name=definition.tool_id,
                        base_path=definition.base_path,
                        query=raw_input,
                        data=None,
                        cached=False,
                        resolved_filter_field=None,
                        resolved_filter_value=None,
                        resolved_intent=resolved_intent.value,
                        error="No matching Trafikverket tool definition found.",
                        error_type="routing",
                    )
                logger.info(
                    "Trafikverket auto route",
                    extra={
                        "intent": resolved_intent.value,
                        "tool": definition_to_use.tool_id if definition_to_use else None,
                        "query": query,
                    },
                )
                payload = await self._run_with_fallbacks(
                    definition_to_use, raw_input
                )
                payload["resolved_intent"] = resolved_intent.value
                return payload

            return trafikverket_auto

        @tool(definition.tool_id, description=definition.description)
        async def trafikverket_tool(
            region: str | None = None,
            road: str | None = None,
            station: str | None = None,
            kamera_id: str | None = None,
            query: str | None = None,
            limit: int | None = None,
            raw_filter: str | None = None,
            time_window_hours: int | None = None,
            filter: dict[str, Any] | None = None,
            from_location: str | None = None,
            to_location: str | None = None,
        ) -> TrafikverketToolResult:
            raw_input: TrafikverketToolInput = {
                "region": region,
                "road": road,
                "station": station,
                "kamera_id": kamera_id,
                "query": query,
                "limit": limit,
                "raw_filter": raw_filter,
                "time_window_hours": time_window_hours,
                "filter": filter,
                "from_location": from_location,
                "to_location": to_location,
            }
            return await self._run_with_fallbacks(definition, raw_input)

        return trafikverket_tool


def build_trafikverket_tool_registry(
    *,
    connector_service: ConnectorService | None,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    api_key: str | None = None,
) -> dict[str, BaseTool]:
    service = TrafikverketServiceV2(api_key=api_key)
    factory = TrafikverketToolFactory(
        service=service,
        connector_service=connector_service,
        search_space_id=search_space_id,
        user_id=user_id,
        thread_id=thread_id,
    )
    registry: dict[str, BaseTool] = {}
    for definition in TRAFIKVERKET_TOOL_DEFINITIONS:
        registry[definition.tool_id] = factory.build_tool(definition)
    return registry


def create_trafikverket_tool(
    definition: TrafikverketToolDefinition,
    *,
    connector_service: ConnectorService | None,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    api_key: str | None = None,
) -> BaseTool:
    service = TrafikverketServiceV2(api_key=api_key)
    factory = TrafikverketToolFactory(
        service=service,
        connector_service=connector_service,
        search_space_id=search_space_id,
        user_id=user_id,
        thread_id=thread_id,
    )
    return factory.build_tool(definition)
