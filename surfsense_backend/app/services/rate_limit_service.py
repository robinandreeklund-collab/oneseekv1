import asyncio
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitStatus:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> RateLimitStatus:
        if self._max_requests <= 0 or self._window_seconds <= 0:
            return RateLimitStatus(
                allowed=True,
                limit=self._max_requests,
                remaining=self._max_requests,
                reset_seconds=0,
            )

        now = time.monotonic()
        window_start = now - self._window_seconds

        async with self._lock:
            queue = self._requests.setdefault(key, deque())
            while queue and queue[0] <= window_start:
                queue.popleft()

            if len(queue) >= self._max_requests:
                retry_after = int(queue[0] + self._window_seconds - now)
                return RateLimitStatus(
                    allowed=False,
                    limit=self._max_requests,
                    remaining=0,
                    reset_seconds=max(retry_after, 1),
                )

            queue.append(now)
            remaining = max(self._max_requests - len(queue), 0)
            reset_seconds = int(queue[0] + self._window_seconds - now)
            return RateLimitStatus(
                allowed=True,
                limit=self._max_requests,
                remaining=remaining,
                reset_seconds=max(reset_seconds, 0),
            )

    def clear(self) -> None:
        self._requests.clear()
