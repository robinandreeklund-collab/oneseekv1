"""
Incremental JSON parser for streaming structured LLM output.

Sprint P1 Extra: Parses JSON tokens as they arrive during ``astream()``,
extracting the ``thinking`` field progressively so it can be streamed
as reasoning-delta events while the rest of the schema fills in.

Uses ``partial-json-parser`` for robust partial JSON parsing — handles
all edge cases (nested objects, escaped strings, incomplete arrays)
that the previous regex-based approach missed.
"""

from __future__ import annotations

import json
from typing import Any

from partial_json_parser import loads as partial_loads


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
        """Best-effort parse of the current buffer using partial-json-parser.

        ``partial_loads`` handles incomplete JSON gracefully — it can parse
        ``{"thinking": "partial text`` and return ``{"thinking": "partial text"}``
        without needing regex fallbacks or suffix-guessing heuristics.
        """
        buf = self._buffer.strip()
        if not buf:
            return None

        try:
            obj = partial_loads(buf)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        return None
