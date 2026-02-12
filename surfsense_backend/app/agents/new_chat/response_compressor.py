"""Compress worker responses before returning to Supervisor context."""

from __future__ import annotations

import json
from typing import Any

from app.utils.context_metrics import estimate_tokens_from_text

# Maximum tokens for compressed responses - balances context efficiency vs information retention
# 800 tokens ≈ 600 words, enough for key data while reducing supervisor context by ~70%
MAX_RESPONSE_TOKENS = 800

# Maximum number of top-level keys to include from Bolagsverket inner data
# Limits detail while preserving essential company information
MAX_BOLAG_KEYS = 10

# Sentence boundary detection threshold (0.7 = last 30% of text)
# Ensures truncation happens at natural sentence breaks for readability
SENTENCE_BOUNDARY_THRESHOLD = 0.7


def extract_key_data(response_text: str, agent_name: str) -> str | None:
    """Extract structured key data from JSON responses without LLM call."""
    try:
        data = json.loads(response_text)
    except (json.JSONDecodeError, TypeError):
        return None
    
    if not isinstance(data, dict):
        return None
    
    if agent_name == "statistics":
        compact = {
            "status": data.get("status"),
            "table": data.get("table_title") or data.get("title"),
            "rows": len(data.get("data", [])) if isinstance(data.get("data"), list) else None,
            "warnings": data.get("warnings"),
        }
        values = data.get("data")
        if isinstance(values, list):
            compact["sample"] = values[:10]
        return json.dumps({k: v for k, v in compact.items() if v is not None}, ensure_ascii=False)
    
    if agent_name == "bolag":
        inner = data.get("data", {})
        if isinstance(inner, dict):
            compact = {
                "status": data.get("status"),
                "company": inner.get("name") or inner.get("namn"),
                "orgnr": data.get("query", {}).get("orgnr"),
                "form": inner.get("form") or inner.get("foretagsform"),
            }
            # Keep up to MAX_BOLAG_KEYS top-level keys from inner data
            for i, (k, v) in enumerate(inner.items()):
                if i >= MAX_BOLAG_KEYS:
                    break
                if k not in compact:
                    compact[k] = v if not isinstance(v, (list, dict)) else str(v)[:200]
            return json.dumps({k: v for k, v in compact.items() if v is not None}, ensure_ascii=False)
        return None
    
    if agent_name == "trafik":
        compact = {
            "status": data.get("status"),
            "objecttype": data.get("objecttype"),
            "count": len(data.get("data", [])) if isinstance(data.get("data"), list) else None,
        }
        values = data.get("data")
        if isinstance(values, list):
            compact["sample"] = values[:5]
        return json.dumps({k: v for k, v in compact.items() if v is not None}, ensure_ascii=False)
    
    # Generic: keep status + truncate
    if "status" in data:
        compact = {"status": data["status"]}
        for key in ("data", "results", "result", "response"):
            val = data.get(key)
            if val is not None:
                if isinstance(val, list):
                    compact[key] = val[:10]
                elif isinstance(val, str) and len(val) > 500:
                    compact[key] = val[:500] + "..."
                else:
                    compact[key] = val
                break
        return json.dumps(compact, ensure_ascii=False)
    
    return None


def truncate_response(text: str, max_chars: int = 3000) -> str:
    """Simple truncation with boundary detection."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Try to cut at sentence boundary
    last_period = truncated.rfind(".")
    if last_period > max_chars * SENTENCE_BOUNDARY_THRESHOLD:
        truncated = truncated[:last_period + 1]
    return truncated + "\n[response truncated]"


def compress_response(response_text: str, agent_name: str) -> str:
    """Compress a worker response for Supervisor context.
    
    The full response is already persisted via ConnectorService.ingest_tool_output,
    so we can safely compress here without data loss.
    
    Strategy:
    1. Under threshold → keep as-is
    2. JSON responses → extract key data
    3. Fallback → truncate to max chars
    """
    if not response_text:
        return response_text
    
    tokens = estimate_tokens_from_text(response_text)
    
    if tokens <= MAX_RESPONSE_TOKENS:
        return response_text
    
    # Try structured extraction
    key_data = extract_key_data(response_text, agent_name)
    if key_data and estimate_tokens_from_text(key_data) <= MAX_RESPONSE_TOKENS:
        return key_data
    
    # Fallback: truncate
    return truncate_response(response_text, max_chars=MAX_RESPONSE_TOKENS * 4)
