import json
import math
from typing import Any


def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def serialize_context_payload(payload: Any) -> str:
    if payload is None:
        return ""
    try:
        return json.dumps(payload, ensure_ascii=True, default=str)
    except (TypeError, ValueError):
        return str(payload)
