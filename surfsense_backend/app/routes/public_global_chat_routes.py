import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.new_chat.llm_config import (
    AgentConfig,
    create_chat_litellm_from_agent_config,
    create_chat_litellm_from_config,
    load_llm_config_from_yaml,
)
from app.config import config
from app.schemas.public_global_chat import PublicGlobalChatRequest
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
    "You are SurfSense's public assistant. "
    "Do not access or imply access to any private user data, connectors, or saved "
    "chats. If a request needs personal data or account-specific actions, ask the "
    "user to sign in."
)


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
        return 0
    raise HTTPException(
        status_code=503,
        detail="Global LLM configuration is not available for public chat.",
    )


def _resolve_llm_config_id(requested_id: int | None) -> int:
    llm_config_id = (
        requested_id
        if requested_id is not None
        else _resolve_default_llm_config_id()
    )

    if llm_config_id > 0:
        raise HTTPException(
            status_code=400,
            detail="Only global LLM configurations are allowed for public chat.",
        )
    return llm_config_id


def _build_system_prompt(llm_config: dict | None) -> str:
    today = datetime.now(UTC).date().isoformat()
    base_prompt = f"{PUBLIC_SYSTEM_PROMPT}\n\nToday's date (UTC): {today}"

    if llm_config:
        extra = llm_config.get("system_instructions") or ""
        if extra.strip():
            return f"{base_prompt}\n\n{extra.strip()}"
    return base_prompt


def _get_first_global_config() -> dict | None:
    for cfg in config.GLOBAL_LLM_CONFIGS:
        if isinstance(cfg, dict) and cfg.get("id") is not None:
            return cfg
    return None


def _build_messages(request: PublicGlobalChatRequest, system_prompt: str) -> list:
    history_limit = max(config.ANON_CHAT_MAX_HISTORY_MESSAGES, 0)
    history = request.messages or []
    if history_limit > 0:
        history = history[-history_limit:]

    messages = [SystemMessage(content=system_prompt)]
    for message in history:
        if message.role == "assistant":
            messages.append(AIMessage(content=message.content))
        else:
            messages.append(HumanMessage(content=message.content))

    messages.append(HumanMessage(content=request.user_query))
    return messages


async def get_public_llm(
    request: PublicGlobalChatRequest = Depends(),
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


@router.post("/chat")
async def public_global_chat(
    request: PublicGlobalChatRequest,
    http_request: Request,
    llm_bundle=Depends(get_public_llm),
    user=Depends(current_optional_user),
):
    if not config.ANON_ACCESS_ENABLED:
        raise HTTPException(status_code=403, detail="Public chat is disabled.")

    llm, llm_config, llm_config_id = llm_bundle
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
        "Public chat request from %s (user=%s, session=%s, llm_config=%s)",
        client_host,
        getattr(user, "id", None),
        anon_session.session_id,
        llm_config_id,
    )

    system_prompt = _build_system_prompt(llm_config)
    messages = _build_messages(request, system_prompt)
    llm_kwargs = {"temperature": config.ANON_CHAT_TEMPERATURE}

    headers = VercelStreamingService.get_response_headers()
    headers.update(
        {
            "X-RateLimit-Limit": str(rate_status.limit),
            "X-RateLimit-Remaining": str(rate_status.remaining),
            "X-RateLimit-Reset": str(rate_status.reset_seconds),
        }
    )

    response = StreamingResponse(
        stream_public_global_chat(llm=llm, messages=messages, llm_kwargs=llm_kwargs),
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
