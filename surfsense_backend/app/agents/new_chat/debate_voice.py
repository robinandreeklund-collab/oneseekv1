"""Live Voice Debate — TTS pipeline with Cartesia Sonic-3 and OpenAI fallback.

Supports two TTS providers:
  - **Cartesia** (default): Sonic-3 model, 40ms time-to-first-audio.
    Uses ``/tts/bytes`` endpoint returning raw PCM (pcm_s16le, 24 kHz).
    All voices are multilingual and speak Swedish with ``language: "sv"``.
  - **OpenAI**: gpt-4o-mini-tts / tts-1 models.  Streaming PCM via
    ``/audio/speech`` with ``response_format="pcm"``.

Architecture (sentence-level TTS):
  1. When a participant's full text response arrives, it is split into
     sentences (~8-20 words each).
  2. For each sentence:
     a) A ``debate_voice_sentence`` event marks TTS progress.
     b) TTS generates audio for that sentence only (~0.3-3s of audio).
     c) PCM chunks are emitted as ``debate_voice_chunk`` events.
  3. The frontend queues chunks and plays them sequentially through an
     AudioContext.

The voice map and API key are loaded from the ``debate_voice_settings``
state key (populated by the admin Debatt settings tab or env fallback).
"""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Default voice maps ────────────────────────────────────────────────

# OpenAI voices (13 built-in): alloy, ash, ballad, coral, echo, fable,
# nova, onyx, sage, shimmer, verse, marin, cedar
DEFAULT_OPENAI_VOICE_MAP: dict[str, str] = {
    "Grok": "ash",
    "Claude": "ballad",
    "ChatGPT": "coral",
    "Gemini": "sage",
    "DeepSeek": "verse",
    "Perplexity": "onyx",
    "Qwen": "marin",
    "OneSeek": "nova",
}

# Cartesia voice IDs — any voice speaks Swedish with language="sv".
# These are example IDs from Cartesia's public docs / SDK examples.
# Configure specific voices via Admin → Debatt or CARTESIA_VOICE_MAP env.
DEFAULT_CARTESIA_VOICE_MAP: dict[str, str] = {
    "Grok": "c961b81c-a935-4c17-bfb3-ba2239de8c2f",       # Kyle
    "Claude": "6ccbfb76-1fc6-48f7-b71d-91ac6298247b",      # Tessa
    "ChatGPT": "a167e0f3-df7e-4d52-a9c3-f949145efdab",     # Customer Support Man
    "Gemini": "e07c00bc-4134-4eae-9ea4-1a55fb45746b",      # SDK example
    "DeepSeek": "694f9389-aac1-45b6-b726-9d9369183238",    # docs example
    "Perplexity": "a0e99841-438c-4a64-b679-ae501e7d6091",  # WebSocket ref
    "Qwen": "f786b574-daa5-4673-aa0c-cbe3e8534c02",       # LiveKit default
    "OneSeek": "6ccbfb76-1fc6-48f7-b71d-91ac6298247b",     # Tessa (shared)
}

# Keep backward-compat alias for imports
DEFAULT_DEBATE_VOICE_MAP = DEFAULT_OPENAI_VOICE_MAP

# PCM format constants (same for both OpenAI and Cartesia)
PCM_SAMPLE_RATE = 24000   # 24 kHz
PCM_BIT_DEPTH = 16        # 16-bit signed little-endian
PCM_CHANNELS = 1          # mono

# Default chunk size in bytes to accumulate before dispatching an SSE event.
# ~100 ms of audio at 24 kHz/16-bit/mono = 4800 bytes.
DEFAULT_CHUNK_BYTES = 4800

# Default models
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_CARTESIA_MODEL = "sonic-3"

# Cartesia API version
CARTESIA_API_VERSION = "2025-04-16"


# ── Sentence splitting ──────────────────────────────────────────────────

# Split after sentence-ending punctuation followed by whitespace.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…;:–])\s+")

# Minimum words for a standalone sentence — shorter fragments merge backward.
_MIN_SENTENCE_WORDS = 5


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences suitable for per-sentence TTS.

    Sentences shorter than ``_MIN_SENTENCE_WORDS`` are merged with the
    previous sentence to avoid tiny TTS calls with choppy output.
    """
    raw = _SENTENCE_SPLIT_RE.split(text.strip())
    merged: list[str] = []
    for fragment in raw:
        fragment = fragment.strip()
        if not fragment:
            continue
        if merged and len(fragment.split()) < _MIN_SENTENCE_WORDS:
            merged[-1] = merged[-1] + " " + fragment
        else:
            merged.append(fragment)
    return merged if merged else [text.strip()]


def _find_sentence_end(full_text: str, sentence: str, search_from: int) -> int:
    """Find the end position of a sentence within the full text."""
    idx = full_text.find(sentence, search_from)
    if idx >= 0:
        return idx + len(sentence)
    # Fuzzy fallback: advance by sentence length
    return min(len(full_text), search_from + len(sentence))


# ── Core functions ──────────────────────────────────────────────────────


def _resolve_voice_settings(state: dict[str, Any]) -> dict[str, Any]:
    """Extract voice settings from graph state or fall back to env/defaults."""
    settings = state.get("debate_voice_settings") or {}
    provider = settings.get("tts_provider") or _env_tts_provider()

    if provider == "cartesia":
        api_key = settings.get("cartesia_api_key") or _env_cartesia_api_key()
        default_map = DEFAULT_CARTESIA_VOICE_MAP
        default_model = DEFAULT_CARTESIA_MODEL
    else:
        api_key = settings.get("api_key") or _env_api_key()
        default_map = DEFAULT_OPENAI_VOICE_MAP
        default_model = DEFAULT_TTS_MODEL

    # Resolve model: ignore cross-provider model names.
    # e.g. "gpt-4o-mini-tts" saved in settings must not be sent to Cartesia.
    model_setting = settings.get("model") or ""
    if provider == "cartesia":
        model = model_setting if model_setting.startswith("sonic") else default_model
    else:
        model = model_setting or default_model

    return {
        "tts_provider": provider,
        "api_key": api_key,
        "api_base": settings.get("api_base") or "https://api.openai.com/v1",
        "model": model,
        "voice_map": settings.get("voice_map") or dict(default_map),
        "speed": float(settings.get("speed", 1.0)),
        "language_instructions": settings.get("language_instructions") or {},
        "language": settings.get("language") or "sv",
    }


def _env_api_key() -> str:
    """Fall back to env-var for the OpenAI TTS API key."""
    import os
    return os.getenv("DEBATE_VOICE_API_KEY", "") or os.getenv("TTS_SERVICE_API_KEY", "")


def _env_cartesia_api_key() -> str:
    """Fall back to env-var for the Cartesia API key."""
    import os
    return os.getenv("CARTESIA_API_KEY", "")


def _env_tts_provider() -> str:
    """Fall back to env-var for the TTS provider."""
    import os
    return os.getenv("DEBATE_TTS_PROVIDER", "cartesia")


def get_voice_for_participant(display_name: str, voice_map: dict[str, str]) -> str:
    """Look up the TTS voice for a given participant display name."""
    return voice_map.get(display_name, "alloy")


# ── Cartesia TTS ───────────────────────────────────────────────────────


async def generate_voice_stream_cartesia(
    *,
    text: str,
    voice_id: str,
    api_key: str,
    model: str = DEFAULT_CARTESIA_MODEL,
    speed: float = 1.0,
    language: str = "sv",
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
):
    """Async generator yielding raw PCM chunks from Cartesia TTS.

    Uses ``POST /tts/bytes`` with ``pcm_s16le`` at 24 kHz — same format
    as OpenAI, so the frontend audio pipeline needs no changes.

    Cartesia Sonic-3 has ~40ms time-to-first-audio, making per-sentence
    TTS extremely fast (~100-500ms per sentence vs ~2-5s with OpenAI).
    """
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "Cartesia-Version": CARTESIA_API_VERSION,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {
        "model_id": model,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": PCM_SAMPLE_RATE,
        },
        "language": language,
    }

    # Speed control via generation_config (Sonic-3 supports 0.6-1.5x)
    if speed != 1.0:
        clamped = max(0.6, min(1.5, speed))
        payload["generation_config"] = {"speed": clamped}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code >= 400:
            logger.error(
                "debate_voice: Cartesia TTS error %d: %s",
                response.status_code, response.text[:300],
            )
            raise httpx.HTTPStatusError(
                f"Cartesia TTS API error {response.status_code}",
                request=response.request,
                response=response,
            )

        # Response is raw PCM binary — split into chunks
        pcm_data = response.content
        for i in range(0, len(pcm_data), chunk_bytes):
            yield pcm_data[i:i + chunk_bytes]


# ── OpenAI TTS ─────────────────────────────────────────────────────────


async def generate_voice_stream(
    *,
    text: str,
    voice: str,
    api_key: str,
    api_base: str = "https://api.openai.com/v1",
    model: str = DEFAULT_TTS_MODEL,
    speed: float = 1.0,
    instructions: str = "",
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

    is_mini_tts = "mini-tts" in model.lower()

    payload: dict[str, Any] = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "pcm",
    }

    if is_mini_tts:
        if instructions:
            payload["instructions"] = instructions
    else:
        payload["speed"] = speed

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                logger.error(
                    "debate_voice: TTS %s error %d: %s",
                    model, resp.status_code, resp.text[:300],
                )
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
            if buffer:
                yield bytes(buffer)


# ── TTS dispatch ───────────────────────────────────────────────────────


def _get_tts_generator(
    *,
    sentence: str,
    voice: str,
    voice_settings: dict[str, Any],
    instructions: str,
):
    """Return the appropriate TTS async generator based on provider."""
    provider = voice_settings.get("tts_provider", "cartesia")

    if provider == "cartesia":
        return generate_voice_stream_cartesia(
            text=sentence,
            voice_id=voice,
            api_key=voice_settings["api_key"],
            model=voice_settings.get("model") or DEFAULT_CARTESIA_MODEL,
            speed=voice_settings.get("speed", 1.0),
            language=voice_settings.get("language", "sv"),
        )
    else:
        tts_model = voice_settings.get("model") or DEFAULT_TTS_MODEL
        is_mini_tts = "mini-tts" in tts_model.lower()
        if is_mini_tts:
            sent_text = sentence
        else:
            sent_text = f"[{instructions}]\n\n{sentence}" if instructions else sentence

        return generate_voice_stream(
            text=sent_text,
            voice=voice,
            api_key=voice_settings["api_key"],
            api_base=voice_settings["api_base"],
            model=tts_model,
            speed=voice_settings.get("speed", 1.0),
            instructions=instructions if is_mini_tts else "",
        )


# ── Voice event emission ──────────────────────────────────────────────


async def _emit_voice_events(
    *,
    text: str,
    participant_display: str,
    participant_key: str,
    round_num: int,
    voice_settings: dict[str, Any],
    config: Any,
) -> int:
    """Stream TTS for one participant, sentence-by-sentence.

    Returns the total number of bytes dispatched.
    """
    from langchain_core.callbacks import adispatch_custom_event

    voice = get_voice_for_participant(
        participant_display, voice_settings["voice_map"],
    )
    total_bytes = 0
    chunk_index = 0
    provider = voice_settings.get("tts_provider", "cartesia")

    # Resolve per-model language/accent instructions (OpenAI only).
    lang_instructions = voice_settings.get("language_instructions") or {}
    if isinstance(lang_instructions, str):
        instr = lang_instructions.strip()
    else:
        instr = (
            lang_instructions.get(participant_display, "").strip()
            or lang_instructions.get("__default__", "").strip()
        )

    tts_model = voice_settings.get("model") or (DEFAULT_CARTESIA_MODEL if provider == "cartesia" else DEFAULT_TTS_MODEL)

    # Split into sentences for per-sentence TTS
    sentences = _split_into_sentences(text)
    text_len = len(text)

    logger.info(
        "debate_voice: starting TTS for %s (provider=%s, voice=%s, model=%s, sentences=%d, text_len=%d)",
        participant_display, provider, voice, tts_model, len(sentences), text_len,
    )

    # Emit speaker-changed event
    await adispatch_custom_event(
        "debate_voice_speaker",
        {
            "model": participant_display,
            "model_key": participant_key,
            "round": round_num,
            "voice": voice,
            "text_length": text_len,
            "total_sentences": len(sentences),
            "provider": provider,
            "timestamp": time.time(),
        },
        config=config,
    )

    # Process each sentence: emit TTS audio
    reveal_cursor = 0

    for sent_idx, sentence in enumerate(sentences):
        reveal_cursor = _find_sentence_end(text, sentence, reveal_cursor)

        # Emit sentence event (TTS progress tracking)
        await adispatch_custom_event(
            "debate_voice_sentence",
            {
                "model": participant_display,
                "round": round_num,
                "si": sent_idx,
                "ts": len(sentences),
                "tri": reveal_cursor,
                "sentence": sentence,
                "timestamp": time.time(),
            },
            config=config,
        )

        # Generate TTS for this sentence via the configured provider
        try:
            async for pcm_chunk in _get_tts_generator(
                sentence=sentence,
                voice=voice,
                voice_settings=voice_settings,
                instructions=instr,
            ):
                b64 = base64.b64encode(pcm_chunk).decode("ascii")
                total_bytes += len(pcm_chunk)
                chunk_index += 1

                await adispatch_custom_event(
                    "debate_voice_chunk",
                    {
                        "model": participant_display,
                        "round": round_num,
                        "ci": chunk_index,
                        "pcm_b64": b64,
                        "tri": reveal_cursor,
                    },
                    config=config,
                )

        except httpx.HTTPStatusError as exc:
            body_preview = ""
            try:
                body_preview = exc.response.text[:300]
            except Exception:
                body_preview = "(could not read response body)"
            logger.error(
                "debate_voice: %s TTS API error for %s sentence %d: status=%s body=%s",
                provider, participant_display, sent_idx, exc.response.status_code, body_preview,
            )
            await adispatch_custom_event(
                "debate_voice_error",
                {
                    "model": participant_display,
                    "round": round_num,
                    "error": f"{provider} TTS error sentence {sent_idx}: {exc.response.status_code} — {body_preview[:100]}",
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception as exc:
            logger.error(
                "debate_voice: %s TTS error for %s sentence %d: %s",
                provider, participant_display, sent_idx, exc,
            )
            try:
                await adispatch_custom_event(
                    "debate_voice_error",
                    {
                        "model": participant_display,
                        "round": round_num,
                        "error": f"{provider} TTS error sentence {sent_idx}: {type(exc).__name__}: {str(exc)[:200]}",
                        "timestamp": time.time(),
                    },
                    config=config,
                )
            except Exception:
                pass
            continue

    logger.info(
        "debate_voice: finished TTS for %s — %d bytes, %d chunks, %d sentences (provider=%s)",
        participant_display, total_bytes, chunk_index, len(sentences), provider,
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
            "total_sentences": len(sentences),
            "timestamp": time.time(),
        },
        config=config,
    )

    return total_bytes


# ── Synced text + voice streaming ─────────────────────────────────────

# PCM bytes per second: 24 000 Hz × 2 bytes × 1 channel = 48 000 B/s
_BYTES_PER_SECOND = PCM_SAMPLE_RATE * (PCM_BIT_DEPTH // 8) * PCM_CHANNELS


async def _generate_full_audio(
    *,
    text: str,
    voice: str,
    voice_settings: dict[str, Any],
    instructions: str = "",
) -> tuple[bytes, float]:
    """Generate TTS audio for the **full text** in one call.

    Returns ``(pcm_data, audio_duration_seconds)``.  The duration is
    computed from the raw PCM byte count:
    ``pcm_bytes / (sample_rate × bytes_per_sample × channels)``.
    """
    chunks: list[bytes] = []
    async for chunk in _get_tts_generator(
        sentence=text,          # full text, not a sentence
        voice=voice,
        voice_settings=voice_settings,
        instructions=instructions,
    ):
        chunks.append(chunk)

    pcm_data = b"".join(chunks)
    audio_duration = len(pcm_data) / _BYTES_PER_SECOND if pcm_data else 0.0
    return pcm_data, audio_duration


async def prepare_tts_audio(
    *,
    text: str,
    participant_display: str,
    state: dict[str, Any],
) -> tuple[bytes, float]:
    """Pre-generate TTS audio for a participant (used by prefetch pipeline).

    Returns ``(pcm_data, audio_duration_seconds)``.  Returns ``(b"", 0.0)``
    if TTS fails or no API key is configured.
    """
    voice_settings = _resolve_voice_settings(state)
    has_api_key = bool(voice_settings["api_key"])
    if not has_api_key:
        return b"", 0.0

    voice = get_voice_for_participant(
        participant_display, voice_settings["voice_map"],
    )

    lang_instructions = voice_settings.get("language_instructions") or {}
    if isinstance(lang_instructions, str):
        instr = lang_instructions.strip()
    else:
        instr = (
            lang_instructions.get(participant_display, "").strip()
            or lang_instructions.get("__default__", "").strip()
        )

    try:
        return await _generate_full_audio(
            text=text,
            voice=voice,
            voice_settings=voice_settings,
            instructions=instr,
        )
    except Exception as exc:
        logger.error(
            "debate_voice: prefetch TTS error for %s: %s",
            participant_display, exc,
        )
        return b"", 0.0


async def stream_text_and_voice_synced(
    *,
    text: str,
    participant_display: str,
    participant_key: str,
    round_num: int,
    state: dict[str, Any],
    config: Any,
    prepared_audio: tuple[bytes, float] | None = None,
) -> int:
    """Stream text word-by-word **synced** to TTS audio for one participant.

    Pipeline:

    1. Send the **full text** to TTS in one call — no sentence splitting.
       (Skipped if ``prepared_audio`` is supplied by the prefetch pipeline.)
    2. Compute ``audio_duration = pcm_bytes / 48 000``.
    3. Derive ``delay_per_word = audio_duration / word_count``.
    4. Interleave ``debate_participant_chunk`` (text, 2 words at a time)
       and ``debate_voice_chunk`` (audio) events at that exact pace.

    Text appearance and audio playback are therefore perfectly synced to
    the natural speaking speed of the synthesised voice.

    Returns total audio bytes dispatched.
    """
    import asyncio

    from langchain_core.callbacks import adispatch_custom_event

    voice_settings = _resolve_voice_settings(state)
    provider = voice_settings.get("tts_provider", "cartesia")
    has_api_key = bool(voice_settings["api_key"])

    if not has_api_key:
        provider_label = "Cartesia" if provider == "cartesia" else "OpenAI"
        key_name = "CARTESIA_API_KEY" if provider == "cartesia" else "DEBATE_VOICE_API_KEY"
        logger.warning(
            "debate_voice: no %s API key — streaming text at fallback pace for %s",
            provider_label, participant_display,
        )
        try:
            await adispatch_custom_event(
                "debate_voice_error",
                {
                    "model": participant_display,
                    "round": round_num,
                    "error": (
                        f"Ingen {provider_label} TTS API-nyckel konfigurerad. "
                        f"Sätt {key_name} eller gå till Admin → Debatt."
                    ),
                    "timestamp": time.time(),
                },
                config=config,
            )
        except Exception:
            pass
        # Fall through — text will still stream at estimated pace (no audio).

    voice = get_voice_for_participant(
        participant_display, voice_settings["voice_map"],
    )

    # Resolve per-model language/accent instructions (OpenAI only)
    lang_instructions = voice_settings.get("language_instructions") or {}
    if isinstance(lang_instructions, str):
        instr = lang_instructions.strip()
    else:
        instr = (
            lang_instructions.get(participant_display, "").strip()
            or lang_instructions.get("__default__", "").strip()
        )

    words = text.split()
    word_count = len(words)

    tts_model = voice_settings.get("model") or (
        DEFAULT_CARTESIA_MODEL if provider == "cartesia" else DEFAULT_TTS_MODEL
    )

    logger.info(
        "debate_voice: synced stream for %s (provider=%s, voice=%s, "
        "model=%s, words=%d, has_key=%s)",
        participant_display, provider, voice, tts_model,
        word_count, has_api_key,
    )

    # ── Emit speaker-changed event ──────────────────────────────────
    await adispatch_custom_event(
        "debate_voice_speaker",
        {
            "model": participant_display,
            "model_key": participant_key,
            "round": round_num,
            "voice": voice,
            "text_length": len(text),
            "provider": provider,
            "timestamp": time.time(),
        },
        config=config,
    )

    # ── 1. Get TTS audio (prefetched or generate now) ──────────────
    pcm_data = b""
    audio_duration = 0.0

    if prepared_audio is not None:
        pcm_data, audio_duration = prepared_audio
        logger.info(
            "debate_voice: using prefetched audio for %s — %.2fs, %d bytes",
            participant_display, audio_duration, len(pcm_data),
        )
    elif has_api_key:
        try:
            pcm_data, audio_duration = await _generate_full_audio(
                text=text,
                voice=voice,
                voice_settings=voice_settings,
                instructions=instr,
            )
        except Exception as exc:
            logger.error(
                "debate_voice: TTS error for %s: %s",
                participant_display, exc,
            )
            try:
                await adispatch_custom_event(
                    "debate_voice_error",
                    {
                        "model": participant_display,
                        "round": round_num,
                        "error": (
                            f"TTS error: {type(exc).__name__}: "
                            f"{str(exc)[:200]}"
                        ),
                        "timestamp": time.time(),
                    },
                    config=config,
                )
            except Exception:
                pass

    # ── 2. Calculate per-word delay from audio duration ─────────────
    # Formula: delay_per_word = audio_duration / word_count
    # Fallback: conversational Swedish ≈ 6.5 words/sec ≈ 150 ms/word.
    if audio_duration > 0 and word_count > 0:
        delay_per_word = audio_duration / word_count
    else:
        delay_per_word = 0.15

    logger.info(
        "debate_voice: %s — %d words, %.2fs audio, %.0fms/word, %d PCM bytes",
        participant_display, word_count, audio_duration,
        delay_per_word * 1000, len(pcm_data),
    )

    # ── 3. Prepare audio chunks ─────────────────────────────────────
    audio_chunks: list[bytes] = []
    if pcm_data:
        for i in range(0, len(pcm_data), DEFAULT_CHUNK_BYTES):
            audio_chunks.append(pcm_data[i : i + DEFAULT_CHUNK_BYTES])

    # ── 4. Prepare text events (2 words per chunk) ──────────────────
    text_chunk_size = 2
    text_events: list[str] = []
    text_word_counts: list[int] = []  # actual words per event

    for wi in range(0, word_count, text_chunk_size):
        word_group = " ".join(words[wi : wi + text_chunk_size])
        delta = word_group if wi == 0 else (" " + word_group)
        text_events.append(delta)
        text_word_counts.append(min(text_chunk_size, word_count - wi))

    # ── 5. Interleave text + audio ──────────────────────────────────
    num_text = len(text_events)
    num_audio = len(audio_chunks)
    audio_per_text = num_audio / max(num_text, 1) if num_audio > 0 else 0
    audio_emit_idx = 0
    total_audio_bytes = 0
    chunk_index = 0

    for te_idx, delta in enumerate(text_events):
        # Emit text chunk
        try:
            await adispatch_custom_event(
                "debate_participant_chunk",
                {
                    "model": participant_display,
                    "model_key": participant_key,
                    "round": round_num,
                    "delta": delta,
                },
                config=config,
            )
        except Exception:
            pass

        # Emit proportional share of audio chunks
        if audio_chunks:
            target_audio_idx = int((te_idx + 1) * audio_per_text)
            while (
                audio_emit_idx < target_audio_idx
                and audio_emit_idx < num_audio
            ):
                b64 = base64.b64encode(
                    audio_chunks[audio_emit_idx],
                ).decode("ascii")
                chunk_index += 1
                total_audio_bytes += len(audio_chunks[audio_emit_idx])
                try:
                    await adispatch_custom_event(
                        "debate_voice_chunk",
                        {
                            "model": participant_display,
                            "round": round_num,
                            "ci": chunk_index,
                            "pcm_b64": b64,
                        },
                        config=config,
                    )
                except Exception:
                    pass
                audio_emit_idx += 1

        # Wait at calculated pace (exact speech rate)
        await asyncio.sleep(delay_per_word * text_word_counts[te_idx])

    # Flush remaining audio chunks (rounding leftovers)
    while audio_emit_idx < num_audio:
        b64 = base64.b64encode(
            audio_chunks[audio_emit_idx],
        ).decode("ascii")
        chunk_index += 1
        total_audio_bytes += len(audio_chunks[audio_emit_idx])
        try:
            await adispatch_custom_event(
                "debate_voice_chunk",
                {
                    "model": participant_display,
                    "round": round_num,
                    "ci": chunk_index,
                    "pcm_b64": b64,
                },
                config=config,
            )
        except Exception:
            pass
        audio_emit_idx += 1

    # ── Emit playback-ready (end of audio for this participant) ─────
    await adispatch_custom_event(
        "debate_voice_done",
        {
            "model": participant_display,
            "model_key": participant_key,
            "round": round_num,
            "total_bytes": total_audio_bytes,
            "total_chunks": chunk_index,
            "audio_duration": round(audio_duration, 2),
            "timestamp": time.time(),
        },
        config=config,
    )

    logger.info(
        "debate_voice: synced stream done for %s — "
        "%d audio bytes, %d chunks, %.1fs audio (provider=%s)",
        participant_display, total_audio_bytes, chunk_index,
        audio_duration, provider,
    )

    return total_audio_bytes


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
    provider = voice_settings.get("tts_provider", "cartesia")

    if not voice_settings["api_key"]:
        provider_label = "Cartesia" if provider == "cartesia" else "OpenAI"
        key_name = "CARTESIA_API_KEY" if provider == "cartesia" else "DEBATE_VOICE_API_KEY"
        logger.warning("debate_voice: no %s API key configured, skipping TTS for %s", provider_label, participant_display)
        try:
            from langchain_core.callbacks import adispatch_custom_event
            await adispatch_custom_event(
                "debate_voice_error",
                {
                    "model": participant_display,
                    "round": round_num,
                    "error": f"Ingen {provider_label} TTS API-nyckel konfigurerad. Sätt {key_name} eller gå till Admin → Debatt.",
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

    provider = voice_settings.get("tts_provider", "cartesia")

    # Resolve instructions once (OpenAI only)
    lang_instr = voice_settings.get("language_instructions") or {}

    results: list[tuple[str, int, bytes]] = []
    for round_num in sorted(round_responses.keys()):
        round_data = round_responses[round_num]
        for p in participant_order:
            display = p["display"]
            text = round_data.get(display, "")
            if not text:
                continue
            voice = get_voice_for_participant(display, voice_settings["voice_map"])

            if isinstance(lang_instr, str):
                instr = lang_instr.strip()
            else:
                instr = (
                    lang_instr.get(display, "").strip()
                    or lang_instr.get("__default__", "").strip()
                )

            sentences = _split_into_sentences(text)
            pcm_parts: list[bytes] = []

            for sentence in sentences:
                async for chunk in _get_tts_generator(
                    sentence=sentence,
                    voice=voice,
                    voice_settings=voice_settings,
                    instructions=instr,
                ):
                    pcm_parts.append(chunk)

            results.append((display, round_num, b"".join(pcm_parts)))

    return results
