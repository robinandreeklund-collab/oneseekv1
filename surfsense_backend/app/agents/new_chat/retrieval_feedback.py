from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import re
import threading
from typing import Any


def _normalize_query_pattern(query: str) -> str:
    normalized = str(query or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9åäö\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    tokens = [token for token in normalized.split(" ") if token]
    return " ".join(tokens[:16])


def query_pattern_hash(query: str) -> str:
    normalized = _normalize_query_pattern(query)
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


# Backward-compatible alias for existing internal callers.
def _query_pattern_hash(query: str) -> str:
    return query_pattern_hash(query)


@dataclass
class FeedbackSignal:
    successes: int = 0
    failures: int = 0
    # Track which competitor tools won when this tool lost.
    competitor_wins: dict[str, int] | None = None

    @property
    def score(self) -> float:
        total = self.successes + self.failures
        if total <= 0:
            return 0.0
        return (self.successes - self.failures) / total

    def record_competitor(self, competitor_tool_id: str) -> None:
        """Record that *competitor_tool_id* was selected instead of this tool."""
        if not competitor_tool_id:
            return
        if self.competitor_wins is None:
            self.competitor_wins = {}
        normalized = str(competitor_tool_id).strip().lower()
        self.competitor_wins[normalized] = self.competitor_wins.get(normalized, 0) + 1

    @property
    def top_competitors(self) -> list[tuple[str, int]]:
        """Return competitors sorted by win count descending."""
        if not self.competitor_wins:
            return []
        return sorted(self.competitor_wins.items(), key=lambda x: x[1], reverse=True)


class RetrievalFeedbackStore:
    def __init__(self, *, max_patterns: int = 2000):
        self._max_patterns = max(100, int(max_patterns))
        self._signals: OrderedDict[tuple[str, str], FeedbackSignal] = OrderedDict()
        self._lock = threading.RLock()

    def _key(self, tool_id: str, query: str) -> tuple[str, str] | None:
        normalized_tool_id = str(tool_id or "").strip().lower()
        pattern_hash = query_pattern_hash(query)
        if not normalized_tool_id or not pattern_hash:
            return None
        return normalized_tool_id, pattern_hash

    def record(
        self,
        *,
        tool_id: str,
        query: str,
        success: bool,
        competitor_tool_id: str | None = None,
    ) -> None:
        key = self._key(tool_id, query)
        if key is None:
            return
        with self._lock:
            signal = self._signals.get(key)
            if signal is None:
                signal = FeedbackSignal()
                self._signals[key] = signal
            if success:
                signal.successes = int(signal.successes) + 1
            else:
                signal.failures = int(signal.failures) + 1
                if competitor_tool_id:
                    signal.record_competitor(competitor_tool_id)
            self._signals.move_to_end(key)
            while len(self._signals) > self._max_patterns:
                self._signals.popitem(last=False)

    def get_boost(self, *, tool_id: str, query: str) -> float:
        key = self._key(tool_id, query)
        if key is None:
            return 0.0
        with self._lock:
            signal = self._signals.get(key)
            if signal is None:
                return 0.0
            self._signals.move_to_end(key)
            raw_score = float(signal.score)
            # Map score [-1, 1] into [-2, 2] as retrieval adjustment.
            boost = max(-2.0, min(2.0, raw_score * 2.0))
            return round(boost, 4)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            rows: list[dict[str, Any]] = []
            for (tool_id, pattern_hash), signal in self._signals.items():
                row: dict[str, Any] = {
                    "tool_id": tool_id,
                    "query_pattern_hash": pattern_hash,
                    "successes": int(signal.successes),
                    "failures": int(signal.failures),
                    "score": float(signal.score),
                }
                if signal.top_competitors:
                    row["top_competitors"] = [
                        {"tool_id": cid, "wins": wins}
                        for cid, wins in signal.top_competitors[:5]
                    ]
                rows.append(row)
            return {"rows": rows, "count": len(rows)}

    def clear(self) -> None:
        with self._lock:
            self._signals.clear()

    def hydrate_rows(
        self,
        rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> int:
        """Merge persisted feedback rows into the in-process store.

        Existing in-memory counters are preserved when they are already higher than
        persisted values. This prevents temporary regressions when local writes are
        ahead of the latest DB snapshot.
        """
        if not isinstance(rows, (list, tuple)):
            return 0
        applied = 0
        with self._lock:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tool_id = str(row.get("tool_id") or "").strip().lower()
                pattern_hash = str(row.get("query_pattern_hash") or "").strip().lower()
                if not tool_id or not pattern_hash:
                    continue
                try:
                    successes = max(0, int(row.get("successes") or 0))
                    failures = max(0, int(row.get("failures") or 0))
                except (TypeError, ValueError):
                    continue
                key = (tool_id, pattern_hash)
                existing = self._signals.get(key)
                if existing is None:
                    self._signals[key] = FeedbackSignal(
                        successes=successes,
                        failures=failures,
                    )
                else:
                    existing.successes = max(int(existing.successes), successes)
                    existing.failures = max(int(existing.failures), failures)
                self._signals.move_to_end(key)
                applied += 1
            while len(self._signals) > self._max_patterns:
                self._signals.popitem(last=False)
        return applied


_global_feedback_lock = threading.RLock()
_global_feedback_store: RetrievalFeedbackStore | None = None


def get_global_retrieval_feedback_store() -> RetrievalFeedbackStore:
    global _global_feedback_store
    with _global_feedback_lock:
        if _global_feedback_store is None:
            _global_feedback_store = RetrievalFeedbackStore(max_patterns=2000)
        return _global_feedback_store


def hydrate_global_retrieval_feedback_store(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> int:
    store = get_global_retrieval_feedback_store()
    return store.hydrate_rows(rows)
