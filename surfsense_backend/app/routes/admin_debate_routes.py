"""Admin API routes for Debate Mode settings.

Stores voice map, TTS API key, TTS model, and speed in Redis
under the key ``debate:voice_settings``.  These settings are loaded
by the debate executor when ``/dvoice`` triggers a voice debate.

Fixes applied:
- BUG-08: Use async Redis client to avoid blocking the event loop
- SEC-01: Obfuscate sensitive API keys before storing in Redis
- SEC-02: Simple rate limiting on settings write endpoints
- KQ-02: Import voice map from debate_voice.py (single source of truth)
"""

import base64
import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.new_chat.debate_voice import DEFAULT_OPENAI_VOICE_MAP
from app.db import SearchSpaceMembership, User, get_async_session
from app.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

REDIS_KEY = "debate:voice_settings"

# KQ-02: Use the single source of truth from debate_voice.py
DEFAULT_VOICE_MAP = DEFAULT_OPENAI_VOICE_MAP

# Default max token budget per participant response
DEFAULT_MAX_TOKENS = 500

# SEC-02: Simple in-memory rate limiting (per-user, 10 writes per minute)
_rate_limit_store: dict[str, list[float]] = {}
_RATE_LIMIT_WINDOW = 60.0  # seconds
_RATE_LIMIT_MAX = 10  # max requests per window


def _check_rate_limit(user_id: str) -> None:
    """SEC-02: Check rate limit for write operations."""
    now = time.monotonic()
    timestamps = _rate_limit_store.get(user_id, [])
    # Remove expired entries
    timestamps = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
    if len(timestamps) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {_RATE_LIMIT_MAX} updates per minute.",
        )
    timestamps.append(now)
    _rate_limit_store[user_id] = timestamps


# SEC-01: Simple obfuscation for API keys in Redis.
# Not true encryption, but prevents casual exposure in Redis CLI/dumps.
# For production, consider Fernet encryption with a proper key from env.
_OBFUSCATION_PREFIX = "obf:"
_SENSITIVE_FIELDS = {"api_key", "cartesia_api_key"}


def _obfuscate_value(value: str) -> str:
    """Simple base64 obfuscation for API keys stored in Redis."""
    if not value or value.startswith(_OBFUSCATION_PREFIX):
        return value
    return _OBFUSCATION_PREFIX + base64.b64encode(value.encode()).decode()


def _deobfuscate_value(value: str) -> str:
    """Reverse the obfuscation."""
    if not value or not value.startswith(_OBFUSCATION_PREFIX):
        return value
    return base64.b64decode(value[len(_OBFUSCATION_PREFIX):].encode()).decode()


def _obfuscate_settings(data: dict) -> dict:
    """Obfuscate sensitive fields before Redis storage."""
    result = dict(data)
    for field in _SENSITIVE_FIELDS:
        if result.get(field):
            result[field] = _obfuscate_value(result[field])
    return result


def _deobfuscate_settings(data: dict) -> dict:
    """Deobfuscate sensitive fields after Redis retrieval."""
    result = dict(data)
    for field in _SENSITIVE_FIELDS:
        if result.get(field):
            result[field] = _deobfuscate_value(result[field])
    return result


# ── Pydantic schemas ────────────────────────────────────────────────

class DebateVoiceSettings(BaseModel):
    tts_provider: str = Field(default="cartesia", description="TTS provider: 'cartesia' or 'openai'")
    api_key: str = Field(default="", description="OpenAI TTS API key")
    cartesia_api_key: str = Field(default="", description="Cartesia API key")
    api_base: str = Field(default="https://api.openai.com/v1", description="OpenAI TTS API base URL")
    model: str = Field(default="", description="TTS model ID (leave empty for provider default)")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="TTS speed multiplier")
    voice_map: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_VOICE_MAP))
    language: str = Field(default="sv", description="Cartesia language code (e.g. 'sv' for Swedish)")
    language_instructions: dict[str, str] = Field(
        default_factory=dict,
        description="Per-modell språk/accent-instruktioner. Nyckel = modellnamn (t.ex. 'Grok'), värde = instruktion. '__default__' gäller alla utan egen.",
    )
    max_tokens: int = Field(
        default=DEFAULT_MAX_TOKENS,
        ge=50,
        le=4096,
        description="Standard max tokens per debattdeltagare per runda.",
    )
    max_tokens_map: dict[str, int] = Field(
        default_factory=dict,
        description="Per-modell max tokens. Nyckel = modellnamn, värde = max tokens. Åsidosätter standard max_tokens.",
    )
    typing_speed_multiplier: float = Field(
        default=1.0,
        ge=0.3,
        le=3.0,
        description="Multiplier för text-reveal-hastighet. <1 = snabbare text, >1 = långsammare.",
    )


class DebateVoiceSettingsResponse(BaseModel):
    settings: DebateVoiceSettings
    stored: bool = False


# ── Admin check ──────────────────────────────────────────────────────

async def _require_admin(session: AsyncSession, user: User) -> None:
    result = await session.execute(
        select(SearchSpaceMembership)
        .filter(
            SearchSpaceMembership.user_id == user.id,
            SearchSpaceMembership.is_owner.is_(True),
        )
        .limit(1)
    )
    if result.scalars().first() is None:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to manage debate settings",
        )


# BUG-08: Use async Redis client to avoid blocking the event loop
async def _get_async_redis():
    """Get an async Redis client from celery broker URL."""
    try:
        import redis.asyncio as aioredis

        broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        return aioredis.from_url(broker_url, decode_responses=True)
    except Exception as exc:
        logger.warning("debate_settings: async Redis connection failed: %s", exc)
        return None


# ── GET /admin/debate/voice-settings ─────────────────────────────────

@router.get("/debate/voice-settings", response_model=DebateVoiceSettingsResponse)
async def get_debate_voice_settings(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_admin(session, user)

    r = await _get_async_redis()
    if r:
        try:
            raw = await r.get(REDIS_KEY)
            if raw:
                data = json.loads(raw)
                data = _deobfuscate_settings(data)
                return DebateVoiceSettingsResponse(
                    settings=DebateVoiceSettings(**data),
                    stored=True,
                )
        except Exception as exc:
            logger.warning("debate_settings: failed to load from Redis: %s", exc)
        finally:
            await r.aclose()

    return DebateVoiceSettingsResponse(settings=DebateVoiceSettings())


# ── PUT /admin/debate/voice-settings ─────────────────────────────────

@router.put("/debate/voice-settings", response_model=DebateVoiceSettingsResponse)
async def update_debate_voice_settings(
    body: DebateVoiceSettings,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_admin(session, user)

    # SEC-02: Rate limiting
    _check_rate_limit(str(user.id))

    r = await _get_async_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    try:
        data = body.model_dump()
        data = _obfuscate_settings(data)
        await r.set(REDIS_KEY, json.dumps(data))
    finally:
        await r.aclose()

    return DebateVoiceSettingsResponse(settings=body, stored=True)


# ── Helper: load settings for debate executor ────────────────────────

async def load_debate_voice_settings_async() -> dict | None:
    """Load voice settings from Redis (async version for debate_executor)."""
    r = await _get_async_redis()
    if not r:
        return None
    try:
        raw = await r.get(REDIS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        return _deobfuscate_settings(data)
    except Exception:
        return None
    finally:
        await r.aclose()


def load_debate_voice_settings() -> dict | None:
    """Load voice settings from Redis (sync fallback).

    BUG-08: Kept for backward compat. Prefer load_debate_voice_settings_async.
    """
    try:
        import redis

        broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(broker_url, decode_responses=True)
        raw = r.get(REDIS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        return _deobfuscate_settings(data)
    except Exception as exc:
        logger.warning("debate_settings: sync Redis load failed: %s", exc)
        return None
