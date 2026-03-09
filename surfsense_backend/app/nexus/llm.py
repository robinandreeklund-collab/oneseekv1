"""NEXUS LLM Helper — connects to the configured LLM via LiteLLM.

Loads the global LLM config (id=-1) from global_llm_config.yaml and provides
a simple async call interface for NEXUS components (Synth Forge, Auto Loop, etc.)
"""

from __future__ import annotations

import logging

import litellm

logger = logging.getLogger(__name__)

# Cached LLM config
_llm_config: dict | None = None
_model_string: str | None = None
_api_key: str | None = None
_api_base: str | None = None
_litellm_params: dict = {}


def _load_config() -> bool:
    """Load LLM config from YAML (id=-1). Returns True if successful."""
    global _llm_config, _model_string, _api_key, _api_base, _litellm_params

    if _model_string is not None:
        return True  # Already loaded

    from app.agents.new_chat.llm_config import load_llm_config_from_yaml

    config = load_llm_config_from_yaml(llm_config_id=-1)
    if not config:
        logger.error("NEXUS LLM: Could not load global LLM config (id=-1)")
        return False

    _llm_config = config

    # Build model string (same logic as llm_config.py)
    if config.get("custom_provider"):
        _model_string = f"{config['custom_provider']}/{config['model_name']}"
    else:
        from app.agents.new_chat.llm_config import PROVIDER_MAP

        provider = config.get("provider", "").upper()
        prefix = PROVIDER_MAP.get(provider, provider.lower())
        _model_string = f"{prefix}/{config['model_name']}"

    _api_key = config.get("api_key", "")
    _api_base = config.get("api_base", "")
    _litellm_params = config.get("litellm_params", {})

    logger.info(
        "NEXUS LLM loaded: model=%s, api_base=%s",
        _model_string,
        _api_base or "(default)",
    )
    return True


async def nexus_llm_call(prompt: str) -> str:
    """Make an LLM call using the configured global model.

    Args:
        prompt: The prompt text to send.

    Returns:
        The LLM response text.

    Raises:
        RuntimeError: If LLM config cannot be loaded.
        Exception: If the LLM call fails.
    """
    if not _load_config():
        raise RuntimeError("NEXUS: Failed to load LLM config (id=-1)")

    kwargs: dict = {
        "model": _model_string,
        "messages": [{"role": "user", "content": prompt}],
    }

    if _api_key:
        kwargs["api_key"] = _api_key
    if _api_base:
        from app.services.llm_service import _sanitize_api_base_for_provider

        _provider = (_llm_config or {}).get("provider", "")
        sanitized = _sanitize_api_base_for_provider(_api_base, _provider)
        if sanitized:
            kwargs["api_base"] = sanitized

    # Add litellm_params (temperature, max_tokens, etc.)
    for key, value in _litellm_params.items():
        if key not in ("api_base",):  # Don't override api_base from params
            kwargs[key] = value

    logger.debug("NEXUS LLM call: model=%s, prompt_len=%d", _model_string, len(prompt))

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content or ""

    logger.debug("NEXUS LLM response: len=%d", len(content))
    return content


def get_nexus_llm_info() -> dict:
    """Return info about the configured LLM (for health endpoint)."""
    if not _load_config():
        return {"status": "not_configured", "model": None}

    return {
        "status": "configured",
        "model": _model_string,
        "api_base": _api_base or "(default)",
        "provider": _llm_config.get("provider", "") if _llm_config else "",
    }
