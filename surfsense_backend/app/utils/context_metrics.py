import json
import math
from typing import Any

try:
    import tiktoken
except Exception:  # pragma: no cover - fallback if dependency missing at runtime
    tiktoken = None


_TOKENIZER_CACHE: dict[str, object] = {}
_DEFAULT_ENCODING = "cl100k_base"


def _get_tokenizer(model: str | None = None):
    if tiktoken is None:
        return None
    cache_key = model or _DEFAULT_ENCODING
    cached = _TOKENIZER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        if model:
            encoding = tiktoken.encoding_for_model(model)
        else:
            encoding = tiktoken.get_encoding(_DEFAULT_ENCODING)
    except Exception:
        encoding = tiktoken.get_encoding(_DEFAULT_ENCODING)
    _TOKENIZER_CACHE[cache_key] = encoding
    return encoding


def estimate_tokens_from_text(text: str, *, model: str | None = None) -> int:
    if not text:
        return 0
    tokenizer = _get_tokenizer(model)
    if tokenizer is not None:
        try:
            return len(tokenizer.encode(text))
        except Exception:
            pass
    return max(1, math.ceil(len(text) / 4))


def serialize_context_payload(payload: Any) -> str:
    if payload is None:
        return ""
    try:
        return json.dumps(payload, ensure_ascii=True, default=str)
    except (TypeError, ValueError):
        return str(payload)
