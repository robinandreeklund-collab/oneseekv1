"""Admin API routes for Debate Mode settings.

Stores voice map, TTS API key, TTS model, and speed in Redis
under the key ``debate:voice_settings``.  These settings are loaded
by the debate executor when ``/dvoice`` triggers a voice debate.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SearchSpaceMembership, User, get_async_session
from app.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

REDIS_KEY = "debate:voice_settings"

# ── Default voice map ────────────────────────────────────────────────
DEFAULT_VOICE_MAP = {
    "Grok": "fable",
    "Claude": "nova",
    "ChatGPT": "echo",
    "Gemini": "shimmer",
    "DeepSeek": "alloy",
    "Perplexity": "onyx",
    "Qwen": "fable",
    "OneSeek": "nova",
}


# ── Pydantic schemas ────────────────────────────────────────────────

class DebateVoiceSettings(BaseModel):
    api_key: str = Field(default="", description="OpenAI TTS API key")
    api_base: str = Field(default="https://api.openai.com/v1", description="TTS API base URL")
    model: str = Field(default="tts-1", description="TTS model ID")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="TTS speed multiplier")
    voice_map: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_VOICE_MAP))
    language_instructions: dict[str, str] = Field(
        default_factory=dict,
        description="Per-modell språk/accent-instruktioner. Nyckel = modellnamn (t.ex. 'Grok'), värde = instruktion. '__default__' gäller alla utan egen.",
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


def _get_redis():
    """Get the Redis client from celery broker URL."""
    try:
        import os

        import redis

        broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        return redis.Redis.from_url(broker_url, decode_responses=True)
    except Exception as exc:
        logger.warning("debate_settings: Redis connection failed: %s", exc)
        return None


# ── GET /admin/debate/voice-settings ─────────────────────────────────

@router.get("/debate/voice-settings", response_model=DebateVoiceSettingsResponse)
async def get_debate_voice_settings(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_admin(session, user)

    r = _get_redis()
    if r:
        raw = r.get(REDIS_KEY)
        if raw:
            try:
                data = json.loads(raw)
                return DebateVoiceSettingsResponse(
                    settings=DebateVoiceSettings(**data),
                    stored=True,
                )
            except Exception:
                pass

    return DebateVoiceSettingsResponse(settings=DebateVoiceSettings())


# ── PUT /admin/debate/voice-settings ─────────────────────────────────

@router.put("/debate/voice-settings", response_model=DebateVoiceSettingsResponse)
async def update_debate_voice_settings(
    body: DebateVoiceSettings,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_admin(session, user)

    r = _get_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    data = body.model_dump()
    r.set(REDIS_KEY, json.dumps(data))

    return DebateVoiceSettingsResponse(settings=body, stored=True)


# ── Helper: load settings for debate executor ────────────────────────

def load_debate_voice_settings() -> dict | None:
    """Load voice settings from Redis (used by debate_executor at runtime)."""
    r = _get_redis()
    if not r:
        return None
    raw = r.get(REDIS_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None
