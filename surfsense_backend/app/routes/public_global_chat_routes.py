import logging
from datetime import UTC, datetime

from deepagents import create_deep_agent
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
try:
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:  # pragma: no cover - fallback for older langgraph layouts
    from langgraph.checkpoint import MemorySaver

from app.agents.new_chat.context import SurfSenseContextSchema
from app.agents.new_chat.llm_config import (
    AgentConfig,
    create_chat_litellm_from_agent_config,
    create_chat_litellm_from_config,
    load_llm_config_from_yaml,
)
from app.agents.new_chat.prompt_registry import resolve_prompt
from app.agents.new_chat.system_prompt import (
    SURFSENSE_CITATION_INSTRUCTIONS,
    SURFSENSE_SYSTEM_INSTRUCTIONS,
)
from app.agents.new_chat.tools.registry import get_tool_by_name, build_tools_async
from app.config import config
from app.db import async_session_maker
from app.schemas.public_global_chat import PublicGlobalChatRequest
from app.services.agent_prompt_service import get_global_prompt_overrides
from app.services.anonymous_session_service import (
    ANON_SESSION_COOKIE_NAME,
    get_or_create_anonymous_session,
)
from app.services.new_streaming_service import VercelStreamingService
from app.services.rate_limit_service import SlidingWindowRateLimiter
from app.tasks.chat.stream_public_global_chat import stream_public_global_chat
from app.users import current_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/global", tags=["public"])

_rate_limiter = SlidingWindowRateLimiter(
    config.ANON_CHAT_RATE_LIMIT_MAX_REQUESTS,
    config.ANON_CHAT_RATE_LIMIT_WINDOW_SECONDS,
)

PUBLIC_SYSTEM_PROMPT = (
    "Public chat constraints:\n"
    "- Do not access or imply access to any private user data, connectors, or saved chats.\n"
    "- If a request needs personal data or account-specific actions, ask the user to sign in."
)

PUBLIC_TOOL_HINT = "Only use tools that are available in your tool list."


def get_public_chat_rate_limiter() -> SlidingWindowRateLimiter:
    return _rate_limiter


def _resolve_default_llm_config_id() -> int:
    if config.GLOBAL_LLM_CONFIGS:
        if config.ANON_CHAT_DEFAULT_LLM_ID is not None:
            if config.ANON_CHAT_DEFAULT_LLM_ID > 0:
                raise HTTPException(
                    status_code=500,
                    detail="ANON_CHAT_DEFAULT_LLM_ID must be 0 or negative.",
                )
            return config.ANON_CHAT_DEFAULT_LLM_ID
        first_config = _get_first_global_config()
        if first_config:
            first_id = first_config.get("id")
            if isinstance(first_id, int) and first_id <= 0:
                return first_id
        return 0
    raise HTTPException(
        status_code=503,
        detail="Global LLM configuration is not available for public chat.",
    )


def _resolve_llm_config_id(requested_id: int | None) -> int:
    if config.ANON_CHAT_DEFAULT_LLM_ID is not None:
        llm_config_id = config.ANON_CHAT_DEFAULT_LLM_ID
        if llm_config_id > 0:
            raise HTTPException(
                status_code=500,
                detail="ANON_CHAT_DEFAULT_LLM_ID must be 0 or negative.",
            )
        return llm_config_id

    llm_config_id = (
        requested_id if requested_id is not None else _resolve_default_llm_config_id()
    )

    if llm_config_id > 0:
        raise HTTPException(
            status_code=400,
            detail="Only global LLM configurations are allowed for public chat.",
        )
    return llm_config_id


def _build_tool_instructions(enabled_tools: list[str]) -> str:
    lines = ["<tools>", "You have access to the following public tools:"]
    for tool_name in enabled_tools:
        tool_def = get_tool_by_name(tool_name)
        description = tool_def.description if tool_def else "No description."
        lines.append(f"- {tool_name}: {description}")
    lines.append(PUBLIC_TOOL_HINT)
    lines.append("</tools>")
    return "\n".join(lines)


def _build_system_prompt(
    llm_config: dict | None,
    enabled_tools: list[str],
    citation_instructions: str | bool | None = None,
    default_system_instructions: str | None = None,
) -> str:
    now = datetime.now(UTC).astimezone(UTC)
    resolved_today = now.date().isoformat()
    resolved_time = now.strftime("%H:%M:%S")
    public_guard = PUBLIC_SYSTEM_PROMPT.strip()

    system_instructions = ""
    system_default_template = str(
        default_system_instructions or SURFSENSE_SYSTEM_INSTRUCTIONS
    )
    if llm_config:
        custom_instructions = llm_config.get("system_instructions") or ""
        use_default = llm_config.get("use_default_system_instructions", True)
        if custom_instructions.strip():
            system_instructions = custom_instructions.format(
                resolved_today=resolved_today,
                resolved_time=resolved_time,
            ).strip()
        elif use_default:
            system_instructions = system_default_template.format(
                resolved_today=resolved_today,
                resolved_time=resolved_time,
            ).strip()
    else:
        system_instructions = system_default_template.format(
            resolved_today=resolved_today,
            resolved_time=resolved_time,
        ).strip()

    tool_instructions = _build_tool_instructions(enabled_tools)
    if isinstance(citation_instructions, bool):
        explicit_citation_instructions = (
            SURFSENSE_CITATION_INSTRUCTIONS.strip()
            if citation_instructions
            else ""
        )
    else:
        explicit_citation_instructions = str(citation_instructions or "").strip()

    parts = [
        part
        for part in [
            system_instructions,
            public_guard,
            tool_instructions,
            explicit_citation_instructions,
        ]
        if part and part.strip()
    ]
    return "\n\n".join(parts).strip()


def _get_first_global_config() -> dict | None:
    for cfg in config.GLOBAL_LLM_CONFIGS:
        if isinstance(cfg, dict) and cfg.get("id") is not None:
            return cfg
    return None


def _build_messages(request: PublicGlobalChatRequest) -> list:
    history_limit = max(config.ANON_CHAT_MAX_HISTORY_MESSAGES, 0)
    history = request.messages or []
    if history_limit > 0:
        history = history[-history_limit:]

    messages = []
    for message in history:
        if message.role == "assistant":
            messages.append(AIMessage(content=message.content))
        else:
            messages.append(HumanMessage(content=message.content))

    messages.append(HumanMessage(content=request.user_query))
    return messages


async def resolve_public_llm(
    request: PublicGlobalChatRequest,
):
    if not config.GLOBAL_LLM_CONFIGS:
        raise HTTPException(
            status_code=503,
            detail="Global LLM configuration is not available for public chat.",
        )

    llm_config_id = _resolve_llm_config_id(request.llm_config_id)

    if llm_config_id == 0:
        agent_config = AgentConfig.from_auto_mode()
        llm = create_chat_litellm_from_agent_config(agent_config)
        if not llm:
            fallback_config = _get_first_global_config()
            if fallback_config:
                llm = create_chat_litellm_from_config(fallback_config)
                if llm:
                    return llm, fallback_config, fallback_config.get("id")
            raise HTTPException(
                status_code=503,
                detail="Auto mode routing is not available for public chat.",
            )
        return llm, None, llm_config_id

    llm_config = load_llm_config_from_yaml(llm_config_id=llm_config_id)
    if not llm_config:
        raise HTTPException(
            status_code=404,
            detail="Requested global LLM configuration was not found.",
        )

    llm = create_chat_litellm_from_config(llm_config)
    if not llm:
        raise HTTPException(
            status_code=503,
            detail="Failed to initialize the global LLM for public chat.",
        )
    return llm, llm_config, llm_config_id


def _resolve_public_tools() -> list[str]:
    dependencies = {"firecrawl_api_key": config.FIRECRAWL_API_KEY}
    enabled_tools: list[str] = []
    for tool_name in config.ANON_CHAT_ENABLED_TOOLS:
        tool_def = get_tool_by_name(tool_name)
        if not tool_def:
            logger.warning("Unknown public tool configured: %s", tool_name)
            continue
        missing_deps = [dep for dep in tool_def.requires if dep not in dependencies]
        if missing_deps:
            logger.warning(
                "Skipping public tool '%s' due to missing deps: %s",
                tool_name,
                ", ".join(missing_deps),
            )
            continue
        enabled_tools.append(tool_name)
    return enabled_tools


async def build_public_agent(
    request: PublicGlobalChatRequest,
):
    llm, llm_config, llm_config_id = await resolve_public_llm(request)
    prompt_overrides: dict[str, str] = {}
    try:
        async with async_session_maker() as session:
            prompt_overrides = await get_global_prompt_overrides(session)
    except Exception:
        logger.exception("Failed to load global prompt overrides for public chat")

    default_system_prompt = resolve_prompt(
        prompt_overrides,
        "system.default.instructions",
        SURFSENSE_SYSTEM_INSTRUCTIONS,
    )
    citation_payload: str | bool | None = request.citation_instructions
    if isinstance(citation_payload, bool):
        citation_payload = (
            resolve_prompt(
                prompt_overrides,
                "citation.instructions",
                SURFSENSE_CITATION_INSTRUCTIONS,
            )
            if citation_payload
            else None
        )

    dependencies = {"firecrawl_api_key": config.FIRECRAWL_API_KEY}
    enabled_tools = _resolve_public_tools()
    tools = await build_tools_async(
        dependencies=dependencies,
        enabled_tools=enabled_tools,
    )
    system_prompt = _build_system_prompt(
        llm_config,
        enabled_tools,
        citation_instructions=citation_payload,
        default_system_instructions=default_system_prompt,
    )
    checkpointer = MemorySaver()
    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        context_schema=SurfSenseContextSchema,
        checkpointer=checkpointer,
    )
    return agent, llm_config, llm_config_id, enabled_tools


@router.post("/chat")
async def public_global_chat(
    request: PublicGlobalChatRequest,
    http_request: Request,
    # Avoid Depends() on body to prevent 422 validation issues.
    user=Depends(current_optional_user),
):
    if not config.ANON_ACCESS_ENABLED:
        raise HTTPException(status_code=403, detail="Public chat is disabled.")

    agent, llm_config, llm_config_id, enabled_tools = await build_public_agent(request)
    cookie_value = http_request.cookies.get(ANON_SESSION_COOKIE_NAME)
    anon_session = get_or_create_anonymous_session(cookie_value)

    rate_limit_key = (
        f"user:{user.id}" if user else f"anon:{anon_session.session_id}"
    )
    rate_status = await _rate_limiter.check(rate_limit_key)

    if not rate_status.allowed:
        logger.warning(
            "Public chat rate limit exceeded for key=%s",
            rate_limit_key,
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for public chat.",
            headers={"Retry-After": str(rate_status.reset_seconds)},
        )

    client_host = http_request.client.host if http_request.client else "unknown"
    logger.info(
        "Public chat request from %s (user=%s, session=%s, llm_config=%s, tools=%s)",
        client_host,
        getattr(user, "id", None),
        anon_session.session_id,
        llm_config_id,
        ",".join(enabled_tools),
    )

    messages = _build_messages(request)
    input_state = {
        "messages": messages,
        "search_space_id": 0,
    }
    thread_id = (
        f"user:{user.id}" if user else f"anon:{anon_session.session_id}"
    )
    stream_config = {
        "recursion_limit": config.ANON_CHAT_RECURSION_LIMIT,
        "configurable": {"thread_id": thread_id},
    }

    headers = VercelStreamingService.get_response_headers()
    headers.update(
        {
            "X-RateLimit-Limit": str(rate_status.limit),
            "X-RateLimit-Remaining": str(rate_status.remaining),
            "X-RateLimit-Reset": str(rate_status.reset_seconds),
        }
    )

    response = StreamingResponse(
        stream_public_global_chat(
            agent=agent,
            input_state=input_state,
            stream_config=stream_config,
        ),
        headers=headers,
        media_type="text/event-stream",
    )

    if anon_session.is_new and not user:
        secure_cookie = config.BACKEND_URL and config.BACKEND_URL.startswith(
            "https://"
        )
        response.set_cookie(
            key=ANON_SESSION_COOKIE_NAME,
            value=anon_session.cookie_value,
            max_age=config.ANON_SESSION_TTL_SECONDS,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
        )

    return response
