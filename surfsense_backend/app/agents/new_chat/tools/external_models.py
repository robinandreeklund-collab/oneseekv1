"""
External LLM tools for SurfSense compare flow.

These tools wrap globally configured models (global_llm_config.yaml) and expose
them as tool calls so the UI can render tool cards consistently.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import litellm
from langchain_core.tools import tool

from app.agents.new_chat.llm_config import PROVIDER_MAP, load_llm_config_from_yaml

DEFAULT_EXTERNAL_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question clearly and concisely."
)
EXTERNAL_MODEL_TIMEOUT_SECONDS = 90
MAX_EXTERNAL_MODEL_RESPONSE_CHARS = 12000
MAX_EXTERNAL_MODEL_SUMMARY_CHARS = 280

_PROVIDER_SOURCE_LABELS = {
    "XAI": "xAI",
    "OPENAI": "OpenAI",
    "ANTHROPIC": "Anthropic",
    "GOOGLE": "Google",
    "DEEPSEEK": "DeepSeek",
    "PERPLEXITY": "Perplexity",
    "ALIBABA_QWEN": "Qwen",
}


@dataclass(frozen=True)
class ExternalModelSpec:
    key: str
    display: str
    config_id: int
    tool_name: str


EXTERNAL_MODEL_SPECS: list[ExternalModelSpec] = [
    ExternalModelSpec(key="grok", display="Grok", config_id=-20, tool_name="call_grok"),
    ExternalModelSpec(
        key="deepseek", display="DeepSeek", config_id=-21, tool_name="call_deepseek"
    ),
    ExternalModelSpec(
        key="gemini", display="Gemini", config_id=-22, tool_name="call_gemini"
    ),
    ExternalModelSpec(key="gpt", display="ChatGPT", config_id=-23, tool_name="call_gpt"),
    ExternalModelSpec(
        key="claude", display="Claude", config_id=-24, tool_name="call_claude"
    ),
    ExternalModelSpec(
        key="perplexity",
        display="Perplexity",
        config_id=-25,
        tool_name="call_perplexity",
    ),
    ExternalModelSpec(key="qwen", display="Qwen", config_id=-26, tool_name="call_qwen"),
]


def get_external_model_specs() -> list[ExternalModelSpec]:
    return list(EXTERNAL_MODEL_SPECS)


def _describe_key_format(api_key: str) -> str:
    key = api_key.strip()
    if key.startswith("xai-"):
        return "xAI"
    if key.startswith("AIza"):
        return "Google AI Studio"
    if key.startswith("sk-or-"):
        return "OpenRouter"
    if key.startswith("sk-ant-"):
        return "Anthropic"
    if key.startswith("sk-"):
        return "OpenAI-like"
    return "Unknown"


def _apply_provider_env(provider: str, api_key: str) -> None:
    provider_key = provider.strip().upper()
    if not api_key:
        return
    if provider_key == "XAI":
        import os

        os.environ.setdefault("XAI_API_KEY", api_key)
    elif provider_key == "DEEPSEEK":
        import os

        os.environ.setdefault("DEEPSEEK_API_KEY", api_key)
    elif provider_key == "GOOGLE":
        import os

        os.environ.setdefault("GEMINI_API_KEY", api_key)
        os.environ.setdefault("GOOGLE_API_KEY", api_key)
    elif provider_key == "OPENROUTER":
        import os

        os.environ.setdefault("OPENROUTER_API_KEY", api_key)
    elif provider_key == "OPENAI":
        import os

        os.environ.setdefault("OPENAI_API_KEY", api_key)
    elif provider_key == "ANTHROPIC":
        import os

        os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
    elif provider_key == "PERPLEXITY":
        import os

        os.environ.setdefault("PERPLEXITY_API_KEY", api_key)
    elif provider_key == "ALIBABA_QWEN":
        import os

        os.environ.setdefault("DASHSCOPE_API_KEY", api_key)


def _build_model_string(config: dict) -> str:
    if config.get("custom_provider"):
        return f"{config['custom_provider']}/{config['model_name']}"
    provider = str(config.get("provider") or "").upper()
    provider_prefix = PROVIDER_MAP.get(provider, provider.lower())
    return f"{provider_prefix}/{config['model_name']}"


def _resolve_api_base(config: dict) -> str:
    api_base = str(config.get("api_base") or "").strip()
    provider = str(config.get("provider") or "").upper()

    # LiteLLM's native Anthropic handler already appends /v1/messages,
    # so passing api_base with a trailing /v1 causes /v1/v1/messages.
    # Strip it to prevent the duplication.
    if provider == "ANTHROPIC":
        if api_base:
            api_base = api_base.rstrip("/")
            if api_base.endswith("/v1"):
                api_base = api_base[:-3]
            # If the user only set the default Anthropic URL, drop it
            # entirely — LiteLLM handles it natively.
            if api_base in ("https://api.anthropic.com", ""):
                return ""
            return api_base
        return ""

    if api_base:
        return api_base
    if provider == "OPENAI":
        return "https://api.openai.com/v1"
    if provider == "GOOGLE":
        return "https://generativelanguage.googleapis.com/v1beta"
    if provider == "ALIBABA_QWEN":
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"
    return ""


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "...", True


def _summarize(text: str) -> str:
    summary, _ = _truncate_text(text, MAX_EXTERNAL_MODEL_SUMMARY_CHARS)
    return summary


def _normalize_usage(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        normalized: dict[str, int] = {}
        for key, value in usage.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                normalized[key] = int(value)
            elif isinstance(value, str) and value.isdigit():
                normalized[key] = int(value)
        return normalized or None
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    normalized = {}
    if isinstance(prompt_tokens, (int, float)):
        normalized["prompt_tokens"] = int(prompt_tokens)
    if isinstance(completion_tokens, (int, float)):
        normalized["completion_tokens"] = int(completion_tokens)
    if isinstance(total_tokens, (int, float)):
        normalized["total_tokens"] = int(total_tokens)
    return normalized or None


def _resolve_source_label(provider: str | None) -> str:
    if not provider:
        return "External model"
    upper = provider.strip().upper()
    if upper in _PROVIDER_SOURCE_LABELS:
        return _PROVIDER_SOURCE_LABELS[upper]
    return provider.strip().title()


def describe_external_model_config(config: dict) -> dict[str, str]:
    api_key = str(config.get("api_key") or "").strip()
    provider = str(config.get("provider") or "").strip()
    model_name = str(config.get("model_name") or "").strip()
    model_string = _build_model_string(config) if model_name else ""
    api_base = _resolve_api_base(config)
    return {
        "provider": provider,
        "model_name": model_name,
        "model_string": model_string,
        "api_base": api_base,
        "key_format": _describe_key_format(api_key) if api_key else "",
        "source": _resolve_source_label(provider),
    }


async def _call_litellm(
    config: dict,
    query: str,
    timeout_seconds: int,
    system_prompt: str,
    max_tokens: int | None = None,
) -> tuple[str, dict[str, int] | None]:
    model_string = _build_model_string(config)
    api_key = str(config.get("api_key") or "").strip()
    api_base = _resolve_api_base(config)
    litellm_params = config.get("litellm_params") or {}

    # Explicit max_tokens takes precedence over litellm_params
    call_params = {**litellm_params}
    if max_tokens is not None:
        call_params["max_tokens"] = max_tokens

    async def _run():
        response = await litellm.acompletion(
            model=model_string,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            api_key=api_key,
            api_base=api_base or None,
            **call_params,
        )
        message = response.choices[0].message
        if hasattr(message, "content"):
            content = str(message.content or "").strip()
        else:
            content = str(message.get("content", "")).strip()
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        usage = _normalize_usage(usage)
        return content, usage

    return await asyncio.wait_for(_run(), timeout=timeout_seconds)


async def call_external_model(
    spec: ExternalModelSpec,
    query: str,
    timeout_seconds: int = EXTERNAL_MODEL_TIMEOUT_SECONDS,
    config: dict | None = None,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    config = config or load_llm_config_from_yaml(spec.config_id)
    if not config:
        return {
            "status": "error",
            "error": f"Missing global config id {spec.config_id}",
            "model_display_name": spec.display,
        }

    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        return {
            "status": "error",
            "error": "Missing API key",
            "model_display_name": spec.display,
        }

    provider = str(config.get("provider") or "").strip()
    if provider:
        _apply_provider_env(provider, api_key)

    metadata = describe_external_model_config(config)
    model_name = metadata.get("model_name") or ""
    model_string = metadata.get("model_string") or ""
    api_base = metadata.get("api_base") or ""

    start = time.monotonic()
    try:
        content, usage = await _call_litellm(
            config,
            query,
            timeout_seconds,
            system_prompt or DEFAULT_EXTERNAL_SYSTEM_PROMPT,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "error",
            "error": str(exc),
            "model_display_name": spec.display,
            "provider": provider,
            "model": model_name,
            "model_string": model_string,
            "api_base": api_base,
            "source": metadata.get("source") or "",
            "latency_ms": latency_ms,
        }

    latency_ms = int((time.monotonic() - start) * 1000)
    if not content:
        return {
            "status": "error",
            "error": "Empty response",
            "model_display_name": spec.display,
            "provider": provider,
            "model": model_name,
            "model_string": model_string,
            "api_base": api_base,
            "source": metadata.get("source") or "",
            "latency_ms": latency_ms,
        }

    response_text, truncated = _truncate_text(
        content, MAX_EXTERNAL_MODEL_RESPONSE_CHARS
    )

    return {
        "status": "success",
        "model_display_name": spec.display,
        "provider": provider,
        "model": model_name,
        "model_string": model_string,
        "api_base": api_base,
        "source": metadata.get("source") or "",
        "latency_ms": latency_ms,
        "usage": usage,
        "summary": _summarize(content),
        "response": response_text,
        "truncated": truncated,
    }


def create_external_model_tool(spec: ExternalModelSpec):
    """
    Factory for a single external model tool.

    The tool uses the global LLM config ID specified in the spec.
    """

    async def external_model_tool(query: str) -> dict[str, Any]:
        """
        Call an externally configured model for compare mode.

        Args:
            query: The user query (with any additional context included).

        Returns:
            A structured response with model metadata and raw output.
        """

        return await call_external_model(spec=spec, query=query)

    return tool(
        spec.tool_name,
        description=f"Call the external model {spec.display} for compare.",
    )(external_model_tool)
