"""Live Voice Debate — TTS pipeline using OpenAI API directly.

Uses OpenAI's TTS API with ``response_format="pcm"`` + streaming to produce
24 kHz 16-bit mono PCM chunks that are base64-encoded and dispatched as SSE
events.  The frontend decodes chunks via Web Audio API for near-instant
playback.

Architecture (inline await — same call stack):
  1. As each participant's text response arrives in debate_executor,
     ``schedule_voice_generation`` is awaited **directly** (not via
     ``asyncio.create_task``).  This keeps ``adispatch_custom_event``
     on the LangGraph callback call stack so SSE events reach the
     stream bridge.
  2. PCM chunks are streamed via ``generate_voice_stream`` and emitted
     as ``debate_voice_chunk`` custom events.
  3. The frontend ``useDebateAudio`` hook queues chunks and plays them
     sequentially through an AudioContext.

The voice map and API key are loaded from the ``debate_voice_settings``
state key (populated by the admin Debatt settings tab or env fallback).
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Voice map — 8 distinct voices for 8 participants ────────────────────
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

# Estimated speaking rate: ~2.5 words/second at 1.0x → ~10 chunks/second
# This is used to estimate text reveal position per audio chunk.
_ESTIMATED_CHUNKS_PER_WORD = 4


def _resolve_voice_settings(state: dict[str, Any]) -> dict[str, Any]:
    """Extract voice settings from graph state or fall back to env/defaults."""
    settings = state.get("debate_voice_settings") or {}
    return {
        "api_key": settings.get("api_key") or _env_api_key(),
        "api_base": settings.get("api_base") or "https://api.openai.com/v1",
        "model": settings.get("model") or DEFAULT_TTS_MODEL,
        "voice_map": settings.get("voice_map") or dict(DEFAULT_DEBATE_VOICE_MAP),
        "speed": float(settings.get("speed", 1.0)),
        "language_instructions": settings.get("language_instructions") or {},
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
    """Async generator yielding raw PCM chunks from OpenAI TTS.

    Uses httpx streaming POST to ``/audio/speech`` with
    ``response_format="pcm"``.
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
            if resp.status_code >= 400:
                # Must read the body before accessing .text on a streaming response
                await resp.aread()
                raise httpx.HTTPStatusError(
                    f"TTS API error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
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
    """Stream TTS for one participant and emit SSE events with text sync.

    Each chunk event includes ``text_reveal_index`` so the frontend can
    progressively reveal the response text in sync with the audio.

    Returns the total number of bytes dispatched.
    """
    from langchain_core.callbacks import adispatch_custom_event

    voice = get_voice_for_participant(
        participant_display, voice_settings["voice_map"],
    )
    total_bytes = 0
    chunk_index = 0

    # Apply per-model language/accent instructions if configured.
    tts_text = text
    lang_instructions = voice_settings.get("language_instructions") or {}
    if isinstance(lang_instructions, str):
        # Backwards compat: global string (deprecated)
        instr = lang_instructions.strip()
    else:
        # Per-model dict: look up participant, fall back to global "__default__"
        instr = (
            lang_instructions.get(participant_display, "").strip()
            or lang_instructions.get("__default__", "").strip()
        )
    if instr:
        tts_text = f"[{instr}]\n\n{text}"

    # Estimate total chunks for proportional text reveal
    word_count = max(1, len(text.split()))
    estimated_total_chunks = max(1, word_count * _ESTIMATED_CHUNKS_PER_WORD)
    text_len = len(text)

    logger.info(
        "debate_voice: starting TTS for %s (voice=%s, model=%s, text_len=%d, est_chunks=%d)",
        participant_display, voice, voice_settings["model"], len(tts_text), estimated_total_chunks,
    )

    # Emit speaker-changed event with text length for frontend sync
    await adispatch_custom_event(
        "debate_voice_speaker",
        {
            "model": participant_display,
            "model_key": participant_key,
            "round": round_num,
            "voice": voice,
            "text_length": text_len,
            "estimated_total_chunks": estimated_total_chunks,
            "timestamp": time.time(),
        },
        config=config,
    )

    try:
        async for pcm_chunk in generate_voice_stream(
            text=tts_text,
            voice=voice,
            api_key=voice_settings["api_key"],
            api_base=voice_settings["api_base"],
            model=voice_settings["model"],
            speed=voice_settings.get("speed", 1.0),
        ):
            b64 = base64.b64encode(pcm_chunk).decode("ascii")
            total_bytes += len(pcm_chunk)
            chunk_index += 1

            # Calculate proportional text reveal position
            reveal_frac = min(1.0, chunk_index / estimated_total_chunks)
            text_reveal_index = min(text_len, int(text_len * reveal_frac))

            # Slim payload — constant PCM format fields sent once in speaker event
            await adispatch_custom_event(
                "debate_voice_chunk",
                {
                    "model": participant_display,
                    "round": round_num,
                    "ci": chunk_index,
                    "pcm_b64": b64,
                    "tri": text_reveal_index,
                },
                config=config,
            )

    except httpx.HTTPStatusError as exc:
        # Response body was read before raising (see generate_voice_stream)
        body_preview = ""
        try:
            body_preview = exc.response.text[:300]
        except Exception:
            body_preview = "(could not read response body)"
        logger.error(
            "debate_voice: TTS API error for %s: status=%s body=%s",
            participant_display, exc.response.status_code, body_preview,
        )
        await adispatch_custom_event(
            "debate_voice_error",
            {
                "model": participant_display,
                "round": round_num,
                "error": f"TTS API error {exc.response.status_code}: {body_preview[:100]}",
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

    logger.info(
        "debate_voice: finished TTS for %s — %d bytes, %d chunks",
        participant_display, total_bytes, chunk_index,
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
) -> int:
    """Run TTS for a single participant and stream PCM chunks as SSE events.

    Returns total bytes dispatched (0 if skipped).
    """
    voice_settings = _resolve_voice_settings(state)
    if not voice_settings["api_key"]:
        logger.warning("debate_voice: no API key configured, skipping TTS for %s", participant_display)
        try:
            from langchain_core.callbacks import adispatch_custom_event
            await adispatch_custom_event(
                "debate_voice_error",
                {
                    "model": participant_display,
                    "round": round_num,
                    "error": "Ingen TTS API-nyckel konfigurerad. Gå till Admin → Debatt och spara din OpenAI API-nyckel.",
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception:
            pass
        return 0

    return await _emit_voice_events(
        text=text,
        participant_display=participant_display,
        participant_key=participant_key,
        round_num=round_num,
        voice_settings=voice_settings,
        config=config,
    )


async def collect_all_audio_for_export(
    *,
    round_responses: dict[int, dict[str, str]],
    participant_order: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[tuple[str, int, bytes]]:
    """Generate full audio for all rounds (for MP3 export)."""
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
