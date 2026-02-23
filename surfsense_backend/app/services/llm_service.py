import logging
from typing import Any
from urllib.parse import urlparse

import litellm
from langchain_core.messages import HumanMessage
from langchain_litellm import ChatLiteLLM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import config, initialize_llm_router_force
from app.db import NewLLMConfig, SearchSpace
from app.services.llm_router_service import (
    AUTO_MODE_ID,
    ChatLiteLLMRouter,
    LLMRouterService,
    is_auto_mode,
)

# Configure litellm to automatically drop unsupported parameters
litellm.drop_params = True

# ---------------------------------------------------------------------------
# Monkey-patch litellm's skip_empty_text_blocks to prevent it from converting
# content: "" → content: null on assistant messages with tool_calls.
#
# LM Studio's Jinja templates crash with
#   "Cannot apply filter 'string' to type: NullValue"
# when content is null.  Our LMStudioCompatibleChatLiteLLM._sanitize_message_dicts
# sets content to "" for exactly this reason, but litellm's internal
# skip_empty_text_blocks (called from process_empty_text_blocks during
# litellm.completion) reverts the fix.  Patching the function to be a no-op
# is safe: it only skips cosmetic cleanup that the OpenAI API doesn't require.
# ---------------------------------------------------------------------------
try:
    import litellm.litellm_core_utils.prompt_templates.factory as _prompt_factory

    _original_skip_empty_text_blocks = _prompt_factory.skip_empty_text_blocks

    def _patched_skip_empty_text_blocks(message):
        """Return message unchanged — preserve content: '' for LM Studio."""
        return message

    _prompt_factory.skip_empty_text_blocks = _patched_skip_empty_text_blocks
except Exception:
    pass  # Non-critical: worst-case the original NullValue error surfaces

logger = logging.getLogger(__name__)


def _is_lm_studio_api_base(api_base: str | None) -> bool:
    value = str(api_base or "").strip()
    if not value:
        return False
    lowered = value.lower()
    if "lmstudio" in lowered:
        return True
    try:
        parsed = urlparse(value if "://" in value else f"http://{value}")
    except Exception:
        return False
    host = str(parsed.hostname or "").strip().lower()
    port = parsed.port
    return host in {"localhost", "127.0.0.1", "::1"} and port == 1234


class LMStudioCompatibleChatLiteLLM(ChatLiteLLM):
    """
    LM Studio chat templates are strict around null values in request payloads.
    Sanitize every call so `None` never reaches Jinja rendering context.
    """

    # Keys that model templates access unconditionally — dropping them produces
    # NullValue in LM Studio's Jinja engine.
    _KEEP_AS_EMPTY_STRING = {"description"}

    @staticmethod
    def _sanitize_schema_value(value):
        if isinstance(value, dict):
            sanitized: dict = {}
            for key, item in value.items():
                if item is None:
                    if key in LMStudioCompatibleChatLiteLLM._KEEP_AS_EMPTY_STRING:
                        sanitized[key] = ""
                    continue
                if key in {"anyOf", "oneOf", "allOf"} and isinstance(item, list):
                    variants: list = []
                    for variant in item:
                        cleaned = LMStudioCompatibleChatLiteLLM._sanitize_schema_value(
                            variant
                        )
                        if (
                            isinstance(cleaned, dict)
                            and str(cleaned.get("type") or "").strip().lower()
                            == "null"
                        ):
                            continue
                        variants.append(cleaned)
                    if variants:
                        sanitized[key] = variants
                    continue
                sanitized[key] = LMStudioCompatibleChatLiteLLM._sanitize_schema_value(
                    item
                )

            properties = sanitized.get("properties")
            required = sanitized.get("required")
            if isinstance(properties, dict):
                cleaned_properties: dict = {}
                for prop_name, prop_schema in properties.items():
                    normalized_name = str(prop_name or "").strip()
                    if normalized_name == "state":
                        # Injected runtime state should not be visible to the model schema.
                        continue
                    cleaned_properties[
                        normalized_name
                    ] = LMStudioCompatibleChatLiteLLM._sanitize_schema_value(prop_schema)
                sanitized["properties"] = cleaned_properties

                if isinstance(required, list):
                    kept_required = [
                        str(field).strip()
                        for field in required
                        if isinstance(field, str) and str(field).strip() in cleaned_properties
                    ]
                    if kept_required:
                        sanitized["required"] = kept_required
                    else:
                        sanitized.pop("required", None)
            return sanitized
        if isinstance(value, list):
            return [LMStudioCompatibleChatLiteLLM._sanitize_schema_value(item) for item in value if item is not None]
        return value

    @staticmethod
    def _deep_replace_none(value: Any) -> Any:
        """Recursively replace None with '' in dicts/lists.

        LM Studio's Jinja templates crash on NullValue for *any* field,
        not just ``content``.  A recursive pass is the safest way to
        guarantee no null value reaches the template engine.
        """
        if value is None:
            return ""
        if isinstance(value, dict):
            return {
                k: LMStudioCompatibleChatLiteLLM._deep_replace_none(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [
                LMStudioCompatibleChatLiteLLM._deep_replace_none(item)
                for item in value
            ]
        return value

    @staticmethod
    def _sanitize_message_dicts(message_dicts: list) -> list:
        """Post-process message dicts to replace null values for LM Studio's strict Jinja templates.

        `_convert_message_to_dict` in langchain_litellm starts with
        ``{"content": message.content}`` which can be ``None`` for tool-call
        assistant turns. llama.cpp's Jinja evaluator cannot apply the ``|string``
        filter to a NullValue, producing "Cannot apply filter 'string' to type:
        NullValue". Same problem applies to tool call id/name/arguments and
        any other field the model template accesses.

        This method is called from our ``_create_message_dicts`` override which
        covers *all* code paths: _generate, _agenerate, _stream, and _astream.
        """
        result = []
        for msg in message_dicts:
            if not isinstance(msg, dict):
                result.append(msg)
                continue
            # Deep-replace all None values recursively
            msg = LMStudioCompatibleChatLiteLLM._deep_replace_none(msg)
            # Ensure tool_calls have sensible defaults for required fields
            raw_calls = msg.get("tool_calls")
            if isinstance(raw_calls, list):
                fixed = []
                for idx, tc in enumerate(raw_calls):
                    if not isinstance(tc, dict):
                        fixed.append(tc)
                        continue
                    # Ensure id is always a non-empty string
                    if not tc.get("id"):
                        tc["id"] = f"call_{idx}"
                    if isinstance(tc.get("function"), dict):
                        fn = tc["function"]
                        if not fn.get("name"):
                            fn["name"] = "tool_call"
                        if not fn.get("arguments"):
                            fn["arguments"] = "{}"
                    fixed.append(tc)
                msg["tool_calls"] = fixed
            # Ensure content is always a string (never null/missing)
            if "content" not in msg or msg["content"] is None:
                msg["content"] = ""
            # Tool messages: ensure name and tool_call_id are present
            if msg.get("role") == "tool":
                if not msg.get("tool_call_id"):
                    msg["tool_call_id"] = "unknown"
                msg.setdefault("name", "tool")
            result.append(msg)
        return result

    def _create_message_dicts(self, messages, stop):
        """Override to sanitize message dicts right before they reach litellm."""
        message_dicts, params = super()._create_message_dicts(messages, stop)
        return self._sanitize_message_dicts(message_dicts), params

    @staticmethod
    def _sanitize_input_messages(input_data: Any) -> Any:
        """Pre-sanitize LangChain message objects before internal dict conversion.

        LangChain/LiteLLM converts AIMessage(content="", tool_calls=[...]) to
        {"content": null, "tool_calls": [...]} following OpenAI convention.
        LM Studio's Jinja templates cannot apply the |string filter to null,
        so we ensure content is always a string before conversion happens.
        """
        if not isinstance(input_data, list):
            return input_data
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        sanitized: list = []
        for msg in input_data:
            if isinstance(msg, AIMessage) and msg.content is None:
                try:
                    msg = msg.model_copy(update={"content": ""})
                except Exception:
                    msg = AIMessage(
                        content="",
                        tool_calls=getattr(msg, "tool_calls", []) or [],
                        additional_kwargs=dict(getattr(msg, "additional_kwargs", {}) or {}),
                        response_metadata=dict(getattr(msg, "response_metadata", {}) or {}),
                        id=getattr(msg, "id", None),
                    )
            elif isinstance(msg, (HumanMessage, SystemMessage, ToolMessage)):
                if getattr(msg, "content", None) is None:
                    try:
                        msg = msg.model_copy(update={"content": ""})
                    except Exception:
                        pass
            sanitized.append(msg)
        return sanitized

    @classmethod
    def _ensure_tool_completeness(cls, tool_def: Any) -> Any:
        """Ensure every tool dict has all fields that strict Jinja templates access.

        Nemotron-3-nano (and similar LM Studio templates) access
        ``tool.function.name``, ``tool.function.description``, and
        ``tool.function.parameters`` unconditionally.  If any of these keys
        are missing (e.g. because ``_sanitize_schema_value`` dropped a null
        value), Jinja resolves them to NullValue which crashes the
        ``| string`` filter.

        This method also deep-replaces any remaining ``None`` → ``""`` in the
        entire tool dict as a final safety net.
        """
        if not isinstance(tool_def, dict):
            return tool_def
        # Deep-replace any leftover None values in the entire tool dict.
        tool_def = cls._deep_replace_none(tool_def)
        tool_def.setdefault("type", "function")
        func = tool_def.get("function")
        if not isinstance(func, dict):
            func = {}
            tool_def["function"] = func
        func.setdefault("name", "tool")
        func.setdefault("description", "")
        params = func.get("parameters")
        if not isinstance(params, dict):
            func["parameters"] = {"type": "object", "properties": {}}
        else:
            params.setdefault("type", "object")
            params.setdefault("properties", {})
        return tool_def

    @classmethod
    def _sanitize_request_kwargs(cls, kwargs: dict) -> dict:
        updated: dict = {}
        for key, value in dict(kwargs or {}).items():
            if value is None:
                continue
            updated[key] = value

        if "tools" in updated:
            tools_payload = updated.get("tools")
            if isinstance(tools_payload, list):
                sanitized_tools = [
                    cls._ensure_tool_completeness(
                        cls._sanitize_schema_value(tool_def)
                    )
                    for tool_def in tools_payload
                    if tool_def is not None
                ]
                updated["tools"] = sanitized_tools
            else:
                updated["tools"] = []
        elif "functions" not in updated:
            # Keep explicit empty tool list to avoid LM Studio null-tool handling bugs.
            updated["tools"] = []

        if updated.get("tools"):
            if updated.get("tool_choice") is None:
                updated["tool_choice"] = "auto"
        else:
            updated.pop("tool_choice", None)

        return updated

    @property
    def _default_params(self):
        base = super()._default_params
        if not isinstance(base, dict):
            return base
        return self._sanitize_request_kwargs(dict(base))

    def invoke(self, input, config=None, **kwargs):
        return super().invoke(
            self._sanitize_input_messages(input),
            config=config,
            **self._sanitize_request_kwargs(kwargs),
        )

    async def ainvoke(self, input, config=None, **kwargs):
        return await super().ainvoke(
            self._sanitize_input_messages(input),
            config=config,
            **self._sanitize_request_kwargs(kwargs),
        )

    def stream(self, input, config=None, **kwargs):
        return super().stream(
            self._sanitize_input_messages(input),
            config=config,
            **self._sanitize_request_kwargs(kwargs),
        )

    async def astream(self, input, config=None, **kwargs):
        async for chunk in super().astream(
            self._sanitize_input_messages(input),
            config=config,
            **self._sanitize_request_kwargs(kwargs),
        ):
            yield chunk

    def completion_with_retry(self, run_manager=None, **kwargs):
        """Final null-safety pass right before litellm.completion().

        Even after _create_message_dicts and _sanitize_request_kwargs,
        litellm's internal processing can re-introduce None values
        (e.g. via skip_empty_text_blocks or prompt template helpers).
        Deep-replacing None → '' in the entire kwargs dict at this point
        guarantees no null reaches LM Studio's strict Jinja template.
        """
        kwargs = self._deep_replace_none(kwargs)
        return super().completion_with_retry(run_manager=run_manager, **kwargs)

    async def acompletion_with_retry(self, run_manager=None, **kwargs):
        """Async variant of the final null-safety pass."""
        kwargs = self._deep_replace_none(kwargs)
        return await super().acompletion_with_retry(run_manager=run_manager, **kwargs)


def _ensure_auto_mode_router_initialized() -> bool:
    if LLMRouterService.is_initialized():
        return True
    try:
        initialize_llm_router_force()
    except Exception as exc:
        logger.error(f"Failed lazy initialization of LLM Router: {exc}")
        return False
    return LLMRouterService.is_initialized()


class LLMRole:
    AGENT = "agent"  # For agent/chat operations
    DOCUMENT_SUMMARY = "document_summary"  # For document summarization


def get_global_llm_config(llm_config_id: int) -> dict | None:
    """
    Get a global LLM configuration by ID.
    Global configs have negative IDs. ID 0 is reserved for Auto mode.

    Args:
        llm_config_id: The ID of the global config (should be negative or 0 for Auto)

    Returns:
        dict: Global config dictionary or None if not found
    """
    # Auto mode (ID 0) is handled separately via the router
    if llm_config_id == AUTO_MODE_ID:
        return {
            "id": AUTO_MODE_ID,
            "name": "Auto (Load Balanced)",
            "description": "Automatically routes requests across available LLM providers for optimal performance and rate limit handling",
            "provider": "AUTO",
            "model_name": "auto",
            "is_auto_mode": True,
        }

    if llm_config_id > 0:
        return None

    for cfg in config.GLOBAL_LLM_CONFIGS:
        if cfg.get("id") == llm_config_id:
            return cfg

    return None


async def validate_llm_config(
    provider: str,
    model_name: str,
    api_key: str,
    api_base: str | None = None,
    custom_provider: str | None = None,
    litellm_params: dict | None = None,
) -> tuple[bool, str]:
    """
    Validate an LLM configuration by attempting to make a test API call.

    Args:
        provider: LLM provider (e.g., 'OPENAI', 'ANTHROPIC')
        model_name: Model identifier
        api_key: API key for the provider
        api_base: Optional custom API base URL
        custom_provider: Optional custom provider string
        litellm_params: Optional additional litellm parameters

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if config works, False otherwise
        - error_message: Empty string if valid, error description if invalid
    """
    try:
        # Build the model string for litellm
        if custom_provider:
            model_string = f"{custom_provider}/{model_name}"
        else:
            # Map provider enum to litellm format
            provider_map = {
                "OPENAI": "openai",
                "ANTHROPIC": "anthropic",
                "GROQ": "groq",
                "COHERE": "cohere",
                "GOOGLE": "gemini",
                "OLLAMA": "ollama_chat",
                "MISTRAL": "mistral",
                "AZURE_OPENAI": "azure",
                "OPENROUTER": "openrouter",
                "COMETAPI": "cometapi",
                "XAI": "xai",
                "BEDROCK": "bedrock",
                "AWS_BEDROCK": "bedrock",  # Legacy support (backward compatibility)
                "VERTEX_AI": "vertex_ai",
                "TOGETHER_AI": "together_ai",
                "FIREWORKS_AI": "fireworks_ai",
                "REPLICATE": "replicate",
                "PERPLEXITY": "perplexity",
                "ANYSCALE": "anyscale",
                "DEEPINFRA": "deepinfra",
                "CEREBRAS": "cerebras",
                "SAMBANOVA": "sambanova",
                "AI21": "ai21",
                "CLOUDFLARE": "cloudflare",
                "DATABRICKS": "databricks",
                # Chinese LLM providers
                "DEEPSEEK": "openai",
                "ALIBABA_QWEN": "openai",
                "MOONSHOT": "openai",
                "ZHIPU": "openai",  # GLM needs special handling
            }
            provider_prefix = provider_map.get(provider, provider.lower())
            model_string = f"{provider_prefix}/{model_name}"

        # Create ChatLiteLLM instance
        litellm_kwargs = {
            "model": model_string,
            "api_key": api_key,
            "timeout": 30,  # Set a timeout for validation
        }

        # Add optional parameters
        if api_base:
            litellm_kwargs["api_base"] = api_base

        # Add any additional litellm parameters
        if litellm_params:
            litellm_kwargs.update(litellm_params)

        chat_cls = (
            LMStudioCompatibleChatLiteLLM
            if _is_lm_studio_api_base(api_base)
            else ChatLiteLLM
        )
        llm = chat_cls(**litellm_kwargs)

        # Make a simple test call
        test_message = HumanMessage(content="Hello")
        response = await llm.ainvoke([test_message])

        # If we got here without exception, the config is valid
        if response and response.content:
            logger.info(f"Successfully validated LLM config for model: {model_string}")
            return True, ""
        else:
            logger.warning(
                f"LLM config validation returned empty response for model: {model_string}"
            )
            return False, "LLM returned an empty response"

    except Exception as e:
        error_msg = f"Failed to validate LLM configuration: {e!s}"
        logger.error(error_msg)
        return False, error_msg


async def get_search_space_llm_instance(
    session: AsyncSession, search_space_id: int, role: str
) -> ChatLiteLLM | ChatLiteLLMRouter | None:
    """
    Get a ChatLiteLLM instance for a specific search space and role.

    LLM preferences are stored at the search space level and shared by all members.

    If Auto mode (ID 0) is configured, returns a ChatLiteLLMRouter that uses
    LiteLLM Router for automatic load balancing across available providers.

    Args:
        session: Database session
        search_space_id: Search Space ID
        role: LLM role ('agent' or 'document_summary')

    Returns:
        ChatLiteLLM or ChatLiteLLMRouter instance, or None if not found
    """
    try:
        # Get the search space with its LLM preferences
        result = await session.execute(
            select(SearchSpace).where(SearchSpace.id == search_space_id)
        )
        search_space = result.scalars().first()

        if not search_space:
            logger.error(f"Search space {search_space_id} not found")
            return None

        # Get the appropriate LLM config ID based on role
        llm_config_id = None
        if role == LLMRole.AGENT:
            llm_config_id = search_space.agent_llm_id
        elif role == LLMRole.DOCUMENT_SUMMARY:
            llm_config_id = search_space.document_summary_llm_id
        else:
            logger.error(f"Invalid LLM role: {role}")
            return None

        if llm_config_id is None:
            logger.error(f"No {role} LLM configured for search space {search_space_id}")
            return None

        # Check for Auto mode (ID 0) - use router for load balancing
        if is_auto_mode(llm_config_id):
            if not _ensure_auto_mode_router_initialized():
                logger.error(
                    "Auto mode requested but LLM Router not initialized. "
                    "Ensure global_llm_config.yaml exists with valid configs."
                )
                return None

            try:
                logger.debug(
                    f"Using Auto mode (LLM Router) for search space {search_space_id}, role {role}"
                )
                return ChatLiteLLMRouter()
            except Exception as e:
                logger.error(f"Failed to create ChatLiteLLMRouter: {e}")
                return None

        # Check if this is a global config (negative ID)
        if llm_config_id < 0:
            global_config = get_global_llm_config(llm_config_id)
            if not global_config:
                logger.error(f"Global LLM config {llm_config_id} not found")
                return None

            # Build model string for global config
            if global_config.get("custom_provider"):
                model_string = (
                    f"{global_config['custom_provider']}/{global_config['model_name']}"
                )
            else:
                provider_map = {
                    "OPENAI": "openai",
                    "ANTHROPIC": "anthropic",
                    "GROQ": "groq",
                    "COHERE": "cohere",
                    "GOOGLE": "gemini",
                    "OLLAMA": "ollama_chat",
                    "MISTRAL": "mistral",
                    "AZURE_OPENAI": "azure",
                    "OPENROUTER": "openrouter",
                    "COMETAPI": "cometapi",
                    "XAI": "xai",
                    "BEDROCK": "bedrock",
                    "AWS_BEDROCK": "bedrock",
                    "VERTEX_AI": "vertex_ai",
                    "TOGETHER_AI": "together_ai",
                    "FIREWORKS_AI": "fireworks_ai",
                    "REPLICATE": "replicate",
                    "PERPLEXITY": "perplexity",
                    "ANYSCALE": "anyscale",
                    "DEEPINFRA": "deepinfra",
                    "CEREBRAS": "cerebras",
                    "SAMBANOVA": "sambanova",
                    "AI21": "ai21",
                    "CLOUDFLARE": "cloudflare",
                    "DATABRICKS": "databricks",
                    "DEEPSEEK": "openai",
                    "ALIBABA_QWEN": "openai",
                    "MOONSHOT": "openai",
                    "ZHIPU": "openai",
                }
                provider_prefix = provider_map.get(
                    global_config["provider"], global_config["provider"].lower()
                )
                model_string = f"{provider_prefix}/{global_config['model_name']}"

            # Create ChatLiteLLM instance from global config
            litellm_kwargs = {
                "model": model_string,
                "api_key": global_config["api_key"],
            }

            if global_config.get("api_base"):
                litellm_kwargs["api_base"] = global_config["api_base"]

            if global_config.get("litellm_params"):
                litellm_kwargs.update(global_config["litellm_params"])

            chat_cls = (
                LMStudioCompatibleChatLiteLLM
                if _is_lm_studio_api_base(global_config.get("api_base"))
                else ChatLiteLLM
            )
            return chat_cls(**litellm_kwargs)

        # Get the LLM configuration from database (NewLLMConfig)
        result = await session.execute(
            select(NewLLMConfig).where(
                NewLLMConfig.id == llm_config_id,
                NewLLMConfig.search_space_id == search_space_id,
            )
        )
        llm_config = result.scalars().first()

        if not llm_config:
            logger.error(
                f"LLM config {llm_config_id} not found in search space {search_space_id}"
            )
            return None

        # Build the model string for litellm
        if llm_config.custom_provider:
            model_string = f"{llm_config.custom_provider}/{llm_config.model_name}"
        else:
            # Map provider enum to litellm format
            provider_map = {
                "OPENAI": "openai",
                "ANTHROPIC": "anthropic",
                "GROQ": "groq",
                "COHERE": "cohere",
                "GOOGLE": "gemini",
                "OLLAMA": "ollama_chat",
                "MISTRAL": "mistral",
                "AZURE_OPENAI": "azure",
                "OPENROUTER": "openrouter",
                "COMETAPI": "cometapi",
                "XAI": "xai",
                "BEDROCK": "bedrock",
                "AWS_BEDROCK": "bedrock",
                "VERTEX_AI": "vertex_ai",
                "TOGETHER_AI": "together_ai",
                "FIREWORKS_AI": "fireworks_ai",
                "REPLICATE": "replicate",
                "PERPLEXITY": "perplexity",
                "ANYSCALE": "anyscale",
                "DEEPINFRA": "deepinfra",
                "CEREBRAS": "cerebras",
                "SAMBANOVA": "sambanova",
                "AI21": "ai21",
                "CLOUDFLARE": "cloudflare",
                "DATABRICKS": "databricks",
                "DEEPSEEK": "openai",
                "ALIBABA_QWEN": "openai",
                "MOONSHOT": "openai",
                "ZHIPU": "openai",
            }
            provider_prefix = provider_map.get(
                llm_config.provider.value, llm_config.provider.value.lower()
            )
            model_string = f"{provider_prefix}/{llm_config.model_name}"

        # Create ChatLiteLLM instance
        litellm_kwargs = {
            "model": model_string,
            "api_key": llm_config.api_key,
        }

        # Add optional parameters
        if llm_config.api_base:
            litellm_kwargs["api_base"] = llm_config.api_base

        # Add any additional litellm parameters
        if llm_config.litellm_params:
            litellm_kwargs.update(llm_config.litellm_params)

        chat_cls = (
            LMStudioCompatibleChatLiteLLM
            if _is_lm_studio_api_base(llm_config.api_base)
            else ChatLiteLLM
        )
        return chat_cls(**litellm_kwargs)

    except Exception as e:
        logger.error(
            f"Error getting LLM instance for search space {search_space_id}, role {role}: {e!s}"
        )
        return None


async def get_agent_llm(
    session: AsyncSession, search_space_id: int
) -> ChatLiteLLM | ChatLiteLLMRouter | None:
    """Get the search space's agent LLM instance for chat operations."""
    return await get_search_space_llm_instance(session, search_space_id, LLMRole.AGENT)


async def get_document_summary_llm(
    session: AsyncSession, search_space_id: int
) -> ChatLiteLLM | ChatLiteLLMRouter | None:
    """Get the search space's document summary LLM instance."""
    return await get_search_space_llm_instance(
        session, search_space_id, LLMRole.DOCUMENT_SUMMARY
    )


# Backward-compatible alias (LLM preferences are now per-search-space, not per-user)
async def get_user_long_context_llm(
    session: AsyncSession, user_id: str, search_space_id: int
) -> ChatLiteLLM | ChatLiteLLMRouter | None:
    """
    Deprecated: Use get_document_summary_llm instead.
    The user_id parameter is ignored as LLM preferences are now per-search-space.
    """
    return await get_document_summary_llm(session, search_space_id)
