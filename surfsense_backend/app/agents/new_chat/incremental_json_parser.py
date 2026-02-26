"""
Incremental JSON parser for streaming structured LLM output.

Sprint P1 Extra: Parses JSON tokens as they arrive during ``astream()``,
extracting the ``thinking`` field progressively so it can be streamed
as reasoning-delta events while the rest of the schema fills in.

Uses ``json.JSONDecoder().raw_decode`` for best-effort partial parsing
(no external dependency).
"""

from __future__ import annotations

import json
import re
from typing import Any


class IncrementalSchemaParser:
    """Parse JSON incrementally during LLM streaming.

    Feed chunks one at a time via :meth:`feed`.  The parser extracts the
    ``thinking`` field progressively and returns deltas of new text.

    Example::

        parser = IncrementalSchemaParser()
        async for chunk in llm.astream(messages, ...):
            thinking_delta, partial = parser.feed(chunk.content)
            if thinking_delta:
                yield {"reasoning_delta": thinking_delta}
        result = parser.finalize()
    """

    def __init__(self) -> None:
        self._buffer: str = ""
        self._last_thinking_len: int = 0
        self._last_response_len: int = 0

    # ── regex for extracting a complete string value ──────────────
    _THINKING_RE = re.compile(
        r'"thinking"\s*:\s*"', re.DOTALL
    )
    _RESPONSE_RE = re.compile(
        r'"response"\s*:\s*"', re.DOTALL
    )

    def feed(self, chunk: str) -> tuple[str, dict[str, Any] | None]:
        """Feed a new chunk.  Returns ``(thinking_delta, partial_result)``.

        *thinking_delta* is the new text added to the ``thinking`` field
        since the last call (empty string if nothing new).
        *partial_result* is the best-effort parsed dict so far, or
        ``None`` if parsing is not yet possible.
        """
        self._buffer += chunk
        partial = self._try_partial_parse()

        thinking_delta = ""
        if isinstance(partial, dict) and "thinking" in partial:
            full_thinking = str(partial["thinking"])
            if len(full_thinking) > self._last_thinking_len:
                thinking_delta = full_thinking[self._last_thinking_len:]
                self._last_thinking_len = len(full_thinking)

        return thinking_delta, partial

    def feed_all(self, chunk: str) -> tuple[str, str, dict[str, Any] | None]:
        """Feed a new chunk.  Returns ``(thinking_delta, response_delta, partial)``.

        Combines thinking and response tracking in a single call — useful for
        output pipeline nodes where the streaming handler needs both deltas.
        """
        self._buffer += chunk
        partial = self._try_partial_parse()

        thinking_delta = ""
        if isinstance(partial, dict) and "thinking" in partial:
            full_thinking = str(partial["thinking"])
            if len(full_thinking) > self._last_thinking_len:
                thinking_delta = full_thinking[self._last_thinking_len:]
                self._last_thinking_len = len(full_thinking)

        response_delta = ""
        if isinstance(partial, dict) and "response" in partial:
            full_response = str(partial["response"])
            if len(full_response) > self._last_response_len:
                response_delta = full_response[self._last_response_len:]
                self._last_response_len = len(full_response)

        return thinking_delta, response_delta, partial

    def feed_response(self, chunk: str) -> tuple[str, dict[str, Any] | None]:
        """Feed a new chunk and also track ``response`` field deltas.

        Returns ``(response_delta, partial_result)``.
        """
        self._buffer += chunk
        partial = self._try_partial_parse()

        response_delta = ""
        if isinstance(partial, dict) and "response" in partial:
            full_response = str(partial["response"])
            if len(full_response) > self._last_response_len:
                response_delta = full_response[self._last_response_len:]
                self._last_response_len = len(full_response)

        return response_delta, partial

    def finalize(self) -> dict[str, Any]:
        """Return the final parsed JSON object.

        Raises ``json.JSONDecodeError`` if the buffer is not valid JSON.
        """
        return json.loads(self._buffer)

    # ── internals ─────────────────────────────────────────────────

    def _try_partial_parse(self) -> dict[str, Any] | None:
        """Best-effort parse of the current buffer.

        Strategy:
        1. Try ``json.loads`` on the buffer directly.
        2. If that fails, try appending closing braces/brackets.
        3. If that fails, try extracting string values via regex.
        """
        buf = self._buffer.strip()
        if not buf:
            return None

        # 1. Direct parse (complete JSON)
        try:
            obj = json.loads(buf)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. Try closing incomplete JSON
        for suffix in ("}", '"}', '"]}', '"}]}', '"}],"reason":""}'):
            try:
                obj = json.loads(buf + suffix)
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, ValueError):
                continue

        # 3. Regex extraction of string fields
        result: dict[str, Any] = {}
        for field_name, pattern in [
            ("thinking", self._THINKING_RE),
            ("response", self._RESPONSE_RE),
        ]:
            match = pattern.search(buf)
            if match:
                start = match.end()
                value = self._extract_json_string(buf, start)
                if value is not None:
                    result[field_name] = value

        return result if result else None

    @staticmethod
    def _extract_json_string(buf: str, start: int) -> str | None:
        """Extract a JSON string value starting at *start* (after opening quote).

        Handles escape sequences.  Returns ``None`` if no content found.
        """
        chars: list[str] = []
        i = start
        while i < len(buf):
            c = buf[i]
            if c == "\\":
                # Escape sequence — take next char as-is
                if i + 1 < len(buf):
                    next_c = buf[i + 1]
                    if next_c == "n":
                        chars.append("\n")
                    elif next_c == "t":
                        chars.append("\t")
                    elif next_c == '"':
                        chars.append('"')
                    elif next_c == "\\":
                        chars.append("\\")
                    else:
                        chars.append(next_c)
                    i += 2
                else:
                    break
            elif c == '"':
                # End of string
                break
            else:
                chars.append(c)
                i += 1
        return "".join(chars) if chars else None
