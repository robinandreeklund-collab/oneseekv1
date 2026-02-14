"""MCP Tool Factory.

This module creates LangChain tools from MCP servers using the Model Context Protocol.
Tools are dynamically discovered from MCP servers - no manual configuration needed.

Supports both transport types:
- stdio: Local process-based MCP servers (command, args, env)
- streamable-http/http/sse: Remote HTTP-based MCP servers (url, headers)

This implements real MCP protocol support similar to Cursor's implementation.
"""

import logging
import json
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel, create_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.tools.mcp_client import MCPClient, normalize_mcp_http_url
from app.db import SearchSourceConnector, SearchSourceConnectorType

logger = logging.getLogger(__name__)


def _create_dynamic_input_model_from_schema(
    tool_name: str,
    input_schema: dict[str, Any],
) -> type[BaseModel]:
    """Create a Pydantic model from MCP tool's JSON schema.

    Args:
        tool_name: Name of the tool (used for model class name)
        input_schema: JSON schema from MCP server

    Returns:
        Pydantic model class for tool input validation

    """
    properties = input_schema.get("properties", {})
    required_fields = input_schema.get("required", [])

    # Build Pydantic field definitions
    field_definitions = {}
    for param_name, param_schema in properties.items():
        param_description = param_schema.get("description", "")
        is_required = param_name in required_fields

        # Use Any type for complex schemas to preserve structure
        # This allows the MCP server to do its own validation
        from typing import Any as AnyType

        from pydantic import Field

        if is_required:
            field_definitions[param_name] = (
                AnyType,
                Field(..., description=param_description),
            )
        else:
            field_definitions[param_name] = (
                AnyType | None,
                Field(None, description=param_description),
            )

    # Create dynamic model
    model_name = f"{tool_name.replace(' ', '').replace('-', '_')}Input"
    return create_model(model_name, **field_definitions)


def _normalize_skolverket_adult_education_args(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Normalize known Skolverket adult-education argument quirks.

    The upstream MCP tool schemas and backend implementation are currently a bit
    inconsistent for municipality/town and scalar formats. We normalize here so
    callers can use the documented schema while avoiding avoidable upstream errors.
    """
    normalized = dict(arguments or {})
    if tool_name not in {"search_adult_education", "count_adult_education_events"}:
        return normalized

    # search_adult_education currently behaves more reliably with municipality.
    if "town" in normalized and "municipality" not in normalized:
        normalized["municipality"] = normalized.pop("town")

    # paceOfStudy is effectively treated as string in upstream.
    if "paceOfStudy" in normalized and normalized["paceOfStudy"] is not None:
        if not isinstance(normalized["paceOfStudy"], str):
            normalized["paceOfStudy"] = str(normalized["paceOfStudy"])

    # distance is modeled as string ("true"/"false") for these adult tools.
    if "distance" in normalized and isinstance(normalized["distance"], bool):
        normalized["distance"] = "true" if normalized["distance"] else "false"

    return normalized


def _extract_mcp_response_text(response: Any) -> str:
    parts: list[str] = []
    for content in getattr(response, "content", []) or []:
        if hasattr(content, "text"):
            parts.append(str(content.text))
        elif hasattr(content, "data"):
            parts.append(str(content.data))
        else:
            parts.append(str(content))
    return "\n".join(parts) if parts else ""


def _looks_like_skolverket_count_404_error(text: str) -> bool:
    lowered = str(text or "").lower()
    return "fel vid rakning av vuxenutbildningar" in lowered or (
        "fel vid räkning av vuxenutbildningar" in lowered
    ) or ("skolverket api error" in lowered and "404" in lowered)


async def _fallback_count_adult_education_events(
    session: ClientSession,
    *,
    arguments: dict[str, Any],
) -> str | None:
    """Fallback count via search_adult_education when count endpoint returns 404."""
    fallback_args = _normalize_skolverket_adult_education_args(
        "search_adult_education",
        arguments,
    )
    try:
        response = await session.call_tool("search_adult_education", arguments=fallback_args)
        result_text = _extract_mcp_response_text(response).strip()
        if not result_text:
            return None

        payload = json.loads(result_text)
        if not isinstance(payload, dict):
            return None
        total_results = payload.get("totalResults")
        if total_results is None:
            return None

        normalized_payload = {
            "totalResults": total_results,
            "currentPage": payload.get("currentPage"),
            "totalPages": payload.get("totalPages"),
            "showing": payload.get("showing"),
            "source": "fallback_via_search_adult_education",
            "note": "count_adult_education_events returned upstream 404; count derived from search_adult_education.totalResults",
        }
        return json.dumps(normalized_payload, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception(
            "Fallback for count_adult_education_events via search_adult_education failed"
        )
        return None


async def _create_mcp_tool_from_definition_stdio(
    tool_def: dict[str, Any],
    mcp_client: MCPClient,
    *,
    connector_id: int | None = None,
    connector_name: str | None = None,
) -> StructuredTool:
    """Create a LangChain tool from an MCP tool definition (stdio transport).

    Args:
        tool_def: Tool definition from MCP server with name, description, input_schema
        mcp_client: MCP client instance for calling the tool

    Returns:
        LangChain StructuredTool instance

    """
    tool_name = tool_def.get("name", "unnamed_tool")
    tool_description = tool_def.get("description", "No description provided")
    input_schema = tool_def.get("input_schema", {"type": "object", "properties": {}})

    # Log the actual schema for debugging
    logger.info(f"MCP tool '{tool_name}' input schema: {input_schema}")

    # Create dynamic input model from schema
    input_model = _create_dynamic_input_model_from_schema(tool_name, input_schema)

    async def mcp_tool_call(**kwargs) -> str:
        """Execute the MCP tool call via the client with retry support."""
        normalized_kwargs = _normalize_skolverket_adult_education_args(tool_name, kwargs)
        logger.info(f"MCP tool '{tool_name}' called with params: {normalized_kwargs}")

        try:
            # Connect to server and call tool (connect has built-in retry logic)
            async with mcp_client.connect():
                result = await mcp_client.call_tool(tool_name, normalized_kwargs)
                return str(result)
        except RuntimeError as e:
            # Connection failures after all retries
            error_msg = f"MCP tool '{tool_name}' connection failed after retries: {e!s}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        except Exception as e:
            # Tool execution or other errors
            error_msg = f"MCP tool '{tool_name}' execution failed: {e!s}"
            logger.exception(error_msg)
            return f"Error: {error_msg}"

    # Create StructuredTool with response_format to preserve exact schema
    metadata: dict[str, Any] = {
        "mcp_input_schema": input_schema,
        "mcp_transport": "stdio",
    }
    if connector_id is not None:
        metadata["mcp_connector_id"] = connector_id
    if connector_name:
        metadata["mcp_connector_name"] = connector_name

    tool = StructuredTool(
        name=tool_name,
        description=tool_description,
        coroutine=mcp_tool_call,
        args_schema=input_model,
        # Store the original MCP schema as metadata so we can access it later
        metadata=metadata,
    )

    logger.info(f"Created MCP tool (stdio): '{tool_name}'")
    return tool


async def _create_mcp_tool_from_definition_http(
    tool_def: dict[str, Any],
    url: str,
    headers: dict[str, str],
    *,
    connector_id: int | None = None,
    connector_name: str | None = None,
) -> StructuredTool:
    """Create a LangChain tool from an MCP tool definition (HTTP transport).

    Args:
        tool_def: Tool definition from MCP server with name, description, input_schema
        url: URL of the MCP server
        headers: HTTP headers for authentication

    Returns:
        LangChain StructuredTool instance

    """
    tool_name = tool_def.get("name", "unnamed_tool")
    tool_description = tool_def.get("description", "No description provided")
    input_schema = tool_def.get("input_schema", {"type": "object", "properties": {}})

    # Log the actual schema for debugging
    logger.info(f"MCP HTTP tool '{tool_name}' input schema: {input_schema}")

    # Create dynamic input model from schema
    input_model = _create_dynamic_input_model_from_schema(tool_name, input_schema)

    async def mcp_http_tool_call(**kwargs) -> str:
        """Execute the MCP tool call via HTTP transport."""
        normalized_kwargs = _normalize_skolverket_adult_education_args(tool_name, kwargs)
        logger.info(
            f"MCP HTTP tool '{tool_name}' called with params: {normalized_kwargs}"
        )

        try:
            async with (
                streamablehttp_client(url, headers=headers) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()

                # Call the tool
                response = await session.call_tool(
                    tool_name, arguments=normalized_kwargs
                )
                result_str = _extract_mcp_response_text(response)
                if (
                    tool_name == "count_adult_education_events"
                    and _looks_like_skolverket_count_404_error(result_str)
                ):
                    fallback_result = await _fallback_count_adult_education_events(
                        session,
                        arguments=normalized_kwargs,
                    )
                    if fallback_result:
                        logger.info(
                            "Applied fallback for count_adult_education_events via search_adult_education"
                        )
                        return fallback_result

                logger.info(
                    f"MCP HTTP tool '{tool_name}' succeeded: {result_str[:200]}"
                )
                return result_str

        except Exception as e:
            error_msg = f"MCP HTTP tool '{tool_name}' execution failed: {e!s}"
            logger.exception(error_msg)
            return f"Error: {error_msg}"

    # Create StructuredTool
    metadata: dict[str, Any] = {
        "mcp_input_schema": input_schema,
        "mcp_transport": "http",
        "mcp_url": url,
    }
    if connector_id is not None:
        metadata["mcp_connector_id"] = connector_id
    if connector_name:
        metadata["mcp_connector_name"] = connector_name

    tool = StructuredTool(
        name=tool_name,
        description=tool_description,
        coroutine=mcp_http_tool_call,
        args_schema=input_model,
        metadata=metadata,
    )

    logger.info(f"Created MCP tool (HTTP): '{tool_name}'")
    return tool


async def _load_stdio_mcp_tools(
    connector_id: int,
    connector_name: str,
    server_config: dict[str, Any],
) -> list[StructuredTool]:
    """Load tools from a stdio-based MCP server.

    Args:
        connector_id: Connector ID for logging
        connector_name: Connector name for logging
        server_config: Server configuration with command, args, env

    Returns:
        List of tools from the MCP server
    """
    tools: list[StructuredTool] = []

    # Validate required command field
    command = server_config.get("command")
    if not command or not isinstance(command, str):
        logger.warning(
            f"MCP connector {connector_id} (name: '{connector_name}') missing or invalid command field, skipping"
        )
        return tools

    # Validate args field (must be list if present)
    args = server_config.get("args", [])
    if not isinstance(args, list):
        logger.warning(
            f"MCP connector {connector_id} (name: '{connector_name}') has invalid args field (must be list), skipping"
        )
        return tools

    # Validate env field (must be dict if present)
    env = server_config.get("env", {})
    if not isinstance(env, dict):
        logger.warning(
            f"MCP connector {connector_id} (name: '{connector_name}') has invalid env field (must be dict), skipping"
        )
        return tools

    # Create MCP client
    mcp_client = MCPClient(command, args, env)

    # Connect and discover tools
    async with mcp_client.connect():
        tool_definitions = await mcp_client.list_tools()

        logger.info(
            f"Discovered {len(tool_definitions)} tools from stdio MCP server "
            f"'{command}' (connector {connector_id})"
        )

    # Create LangChain tools from definitions
    for tool_def in tool_definitions:
        try:
            tool = await _create_mcp_tool_from_definition_stdio(
                tool_def,
                mcp_client,
                connector_id=connector_id,
                connector_name=connector_name,
            )
            tools.append(tool)
        except Exception as e:
            logger.exception(
                f"Failed to create tool '{tool_def.get('name')}' "
                f"from connector {connector_id}: {e!s}"
            )

    return tools


async def _load_http_mcp_tools(
    connector_id: int,
    connector_name: str,
    server_config: dict[str, Any],
) -> list[StructuredTool]:
    """Load tools from an HTTP-based MCP server.

    Args:
        connector_id: Connector ID for logging
        connector_name: Connector name for logging
        server_config: Server configuration with url, headers

    Returns:
        List of tools from the MCP server
    """
    tools: list[StructuredTool] = []

    # Validate required url field
    raw_url = server_config.get("url")
    url = normalize_mcp_http_url(raw_url) if isinstance(raw_url, str) else raw_url
    if not url or not isinstance(url, str):
        logger.warning(
            f"MCP connector {connector_id} (name: '{connector_name}') missing or invalid url field, skipping"
        )
        return tools
    if isinstance(raw_url, str) and url != raw_url:
        logger.info(
            "Normalized MCP connector %s URL: %s -> %s",
            connector_id,
            raw_url,
            url,
        )

    # Validate headers field (must be dict if present)
    headers = server_config.get("headers", {})
    if not isinstance(headers, dict):
        logger.warning(
            f"MCP connector {connector_id} (name: '{connector_name}') has invalid headers field (must be dict), skipping"
        )
        return tools

    # Connect and discover tools via HTTP
    try:
        async with (
            streamablehttp_client(url, headers=headers) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            # List available tools
            response = await session.list_tools()
            tool_definitions = []
            for tool in response.tools:
                tool_definitions.append(
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema
                        if hasattr(tool, "inputSchema")
                        else {},
                    }
                )

            logger.info(
                f"Discovered {len(tool_definitions)} tools from HTTP MCP server "
                f"'{url}' (connector {connector_id})"
            )

        # Create LangChain tools from definitions
        for tool_def in tool_definitions:
            try:
                tool = await _create_mcp_tool_from_definition_http(
                    tool_def,
                    url,
                    headers,
                    connector_id=connector_id,
                    connector_name=connector_name,
                )
                tools.append(tool)
            except Exception as e:
                logger.exception(
                    f"Failed to create HTTP tool '{tool_def.get('name')}' "
                    f"from connector {connector_id}: {e!s}"
                )

    except Exception as e:
        logger.exception(
            f"Failed to connect to HTTP MCP server at '{url}' (connector {connector_id}): {e!s}"
        )

    return tools


async def load_mcp_tools(
    session: AsyncSession,
    search_space_id: int,
) -> list[StructuredTool]:
    """Load all MCP tools from user's active MCP server connectors.

    This discovers tools dynamically from MCP servers using the protocol.
    Supports both stdio (local process) and HTTP (remote server) transports.

    Args:
        session: Database session
        search_space_id: User's search space ID

    Returns:
        List of LangChain StructuredTool instances

    """
    try:
        # Fetch all MCP connectors for this search space
        result = await session.execute(
            select(SearchSourceConnector).filter(
                SearchSourceConnector.connector_type
                == SearchSourceConnectorType.MCP_CONNECTOR,
                SearchSourceConnector.search_space_id == search_space_id,
            ),
        )

        tools: list[StructuredTool] = []
        for connector in result.scalars():
            try:
                # Early validation: Extract and validate connector config
                config = connector.config or {}
                server_config = config.get("server_config", {})

                # Validate server_config exists and is a dict
                if not server_config or not isinstance(server_config, dict):
                    logger.warning(
                        f"MCP connector {connector.id} (name: '{connector.name}') has invalid or missing server_config, skipping"
                    )
                    continue

                # Determine transport type
                transport = server_config.get("transport", "stdio")

                if transport in ("streamable-http", "http", "sse"):
                    # HTTP-based MCP server
                    connector_tools = await _load_http_mcp_tools(
                        connector.id, connector.name, server_config
                    )
                else:
                    # stdio-based MCP server (default)
                    connector_tools = await _load_stdio_mcp_tools(
                        connector.id, connector.name, server_config
                    )

                tools.extend(connector_tools)

            except Exception as e:
                logger.exception(
                    f"Failed to load tools from MCP connector {connector.id}: {e!s}"
                )

        logger.info(f"Loaded {len(tools)} MCP tools for search space {search_space_id}")
        return tools

    except Exception as e:
        logger.exception(f"Failed to load MCP tools: {e!s}")
        return []
