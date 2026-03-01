"""Live Voice Debate — TTS pipeline using OpenAI SDK directly.

Uses OpenAI's TTS API with ``response_format="pcm"`` + streaming to produce
24 kHz 16-bit mono PCM chunks that are base64-encoded and dispatched as SSE
events.  The frontend decodes chunks via Web Audio API for near-instant
playback.

Architecture (Strategy B — pipelined asyncio):
  1. As each participant's text response arrives in debate_executor,
     ``schedule_voice_generation`` fires an asyncio.Task.
  2. The task streams PCM chunks via ``generate_voice_stream`` and emits
     ``debate_voice_chunk`` custom events through the LangGraph callback.
  3. The frontend ``useDebateAudio`` hook queues chunks and plays them
     sequentially through an AudioContext.

The voice map and API key are loaded from the ``debate_voice_settings``
state key (populated by the admin Debatt settings tab or env fallback).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Voice map — 8 distinct voices for 8 participants ────────────────────
# Keys are the debate participant display names (case-insensitive lookup).
# Values are OpenAI TTS voice IDs.
# This default can be overridden from admin settings (``debate_voice_settings``).
DEFAULT_DEBATE_VOICE_MAP: dict[str, str] = {
    "Grok": "fable",
    "Claude": "nova",
    "ChatGPT": "echo",
    "Gemini": "shimmer",
    "DeepSeek": "alloy",
    "Perplexity": "onyx",
    "Qwen": "fable",
    "OneSeek": "nova",
}

# PCM format constants (OpenAI TTS with response_format=pcm)
PCM_SAMPLE_RATE = 24000   # 24 kHz
PCM_BIT_DEPTH = 16        # 16-bit signed little-endian
PCM_CHANNELS = 1          # mono

# Default chunk size in bytes to accumulate before dispatching an SSE event.
# ~100 ms of audio at 24 kHz/16-bit/mono = 4800 bytes.
DEFAULT_CHUNK_BYTES = 4800

# Default TTS model
DEFAULT_TTS_MODEL = "tts-1"


def _resolve_voice_settings(state: dict[str, Any]) -> dict[str, Any]:
    """Extract voice settings from graph state or fall back to env/defaults."""
    settings = state.get("debate_voice_settings") or {}
    return {
        "api_key": settings.get("api_key") or _env_api_key(),
        "api_base": settings.get("api_base") or "https://api.openai.com/v1",
        "model": settings.get("model") or DEFAULT_TTS_MODEL,
        "voice_map": settings.get("voice_map") or dict(DEFAULT_DEBATE_VOICE_MAP),
        "speed": float(settings.get("speed", 1.0)),
    }


def _env_api_key() -> str:
    """Fall back to env-var for the TTS API key."""
    import os
    return os.getenv("DEBATE_VOICE_API_KEY", "") or os.getenv("TTS_SERVICE_API_KEY", "")


def get_voice_for_participant(display_name: str, voice_map: dict[str, str]) -> str:
    """Look up the TTS voice for a given participant display name."""
    return voice_map.get(display_name, "alloy")


async def generate_voice_stream(
    *,
    text: str,
    voice: str,
    api_key: str,
    api_base: str = "https://api.openai.com/v1",
    model: str = DEFAULT_TTS_MODEL,
    speed: float = 1.0,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
):
    """Async generator yielding base64-encoded PCM chunks from OpenAI TTS.

    Uses httpx streaming POST to ``/audio/speech`` with
    ``response_format="pcm"``.

    Yields:
        ``bytes`` — raw PCM data (caller base64-encodes for SSE).
    """
    url = f"{api_base.rstrip('/')}/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "pcm",
        "speed": speed,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            buffer = bytearray()
            async for raw_chunk in resp.aiter_bytes(chunk_size=chunk_bytes):
                buffer.extend(raw_chunk)
                while len(buffer) >= chunk_bytes:
                    yield bytes(buffer[:chunk_bytes])
                    buffer = buffer[chunk_bytes:]
            # flush remainder
            if buffer:
                yield bytes(buffer)


async def _emit_voice_events(
    *,
    text: str,
    participant_display: str,
    participant_key: str,
    round_num: int,
    voice_settings: dict[str, Any],
    config: Any,
) -> int:
    """Stream TTS for one participant and emit SSE events.

    Returns the total number of bytes dispatched (for tracking).
    """
    from langchain_core.callbacks import adispatch_custom_event

    voice = get_voice_for_participant(
        participant_display, voice_settings["voice_map"],
    )
    total_bytes = 0
    chunk_index = 0

    # Emit speaker-changed event
    await adispatch_custom_event(
        "debate_voice_speaker",
        {
            "model": participant_display,
            "model_key": participant_key,
            "round": round_num,
            "voice": voice,
            "timestamp": time.time(),
        },
        config=config,
    )

    try:
        async for pcm_chunk in generate_voice_stream(
            text=text,
            voice=voice,
            api_key=voice_settings["api_key"],
            api_base=voice_settings["api_base"],
            model=voice_settings["model"],
            speed=voice_settings.get("speed", 1.0),
        ):
            b64 = base64.b64encode(pcm_chunk).decode("ascii")
            total_bytes += len(pcm_chunk)
            chunk_index += 1

            await adispatch_custom_event(
                "debate_voice_chunk",
                {
                    "model": participant_display,
                    "model_key": participant_key,
                    "round": round_num,
                    "chunk_index": chunk_index,
                    "pcm_b64": b64,
                    "sample_rate": PCM_SAMPLE_RATE,
                    "bit_depth": PCM_BIT_DEPTH,
                    "channels": PCM_CHANNELS,
                    "timestamp": time.time(),
                },
                config=config,
            )

    except httpx.HTTPStatusError as exc:
        logger.error(
            "debate_voice: TTS API error for %s: %s %s",
            participant_display, exc.response.status_code, exc.response.text[:200],
        )
        await adispatch_custom_event(
            "debate_voice_error",
            {
                "model": participant_display,
                "round": round_num,
                "error": f"TTS API error: {exc.response.status_code}",
                "timestamp": time.time(),
            },
            config=config,
        )
    except Exception as exc:
        logger.error("debate_voice: TTS error for %s: %s", participant_display, exc)
        await adispatch_custom_event(
            "debate_voice_error",
            {
                "model": participant_display,
                "round": round_num,
                "error": str(exc)[:200],
                "timestamp": time.time(),
            },
            config=config,
        )

    # Emit playback-ready (marks end of audio for this participant)
    await adispatch_custom_event(
        "debate_voice_done",
        {
            "model": participant_display,
            "model_key": participant_key,
            "round": round_num,
            "total_bytes": total_bytes,
            "total_chunks": chunk_index,
            "timestamp": time.time(),
        },
        config=config,
    )

    return total_bytes


async def schedule_voice_generation(
    *,
    text: str,
    participant_display: str,
    participant_key: str,
    round_num: int,
    state: dict[str, Any],
    config: Any,
) -> asyncio.Task | None:
    """Schedule TTS generation as an asyncio task (pipelined).

    Returns the Task so the caller can optionally await it for sequencing.
    Returns ``None`` if voice mode is disabled or the API key is missing.
    """
    voice_settings = _resolve_voice_settings(state)
    if not voice_settings["api_key"]:
        logger.debug("debate_voice: no API key, skipping TTS for %s", participant_display)
        return None

    task = asyncio.create_task(
        _emit_voice_events(
            text=text,
            participant_display=participant_display,
            participant_key=participant_key,
            round_num=round_num,
            voice_settings=voice_settings,
            config=config,
        ),
        name=f"tts-{participant_key}-r{round_num}",
    )
    return task


async def collect_all_audio_for_export(
    *,
    round_responses: dict[int, dict[str, str]],
    participant_order: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[tuple[str, int, bytes]]:
    """Generate full audio for all rounds (for MP3 export).

    Returns a list of ``(participant_display, round_num, pcm_bytes)`` tuples
    in presentation order.
    """
    voice_settings = _resolve_voice_settings(state)
    if not voice_settings["api_key"]:
        return []

    results: list[tuple[str, int, bytes]] = []
    for round_num in sorted(round_responses.keys()):
        round_data = round_responses[round_num]
        for p in participant_order:
            display = p["display"]
            text = round_data.get(display, "")
            if not text:
                continue
            voice = get_voice_for_participant(display, voice_settings["voice_map"])
            pcm_parts: list[bytes] = []
            async for chunk in generate_voice_stream(
                text=text,
                voice=voice,
                api_key=voice_settings["api_key"],
                api_base=voice_settings["api_base"],
                model=voice_settings["model"],
                speed=voice_settings.get("speed", 1.0),
            ):
                pcm_parts.append(chunk)
            results.append((display, round_num, b"".join(pcm_parts)))

    return results
