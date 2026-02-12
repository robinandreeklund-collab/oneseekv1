"""Circuit breaker for external API resilience."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Simple circuit breaker for external service calls."""
    
    name: str
    failure_threshold: int = 3
    reset_timeout: float = 60.0
    _failures: int = field(init=False, default=0)
    _last_failure: float = field(init=False, default=0.0)
    _state: CircuitState = field(init=False, default=CircuitState.CLOSED)
    _last_success: float = field(init=False, default=0.0)
    
    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure > self.reset_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state
    
    def can_execute(self) -> bool:
        current_state = self.state
        return current_state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)
    
    def record_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._last_success = time.time()
    
    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure = time.time()
        if self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
    
    def get_status(self) -> dict[str, object]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self._failures,
            "threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout,
        }


# Global registry of circuit breakers
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str,
    failure_threshold: int = 3,
    reset_timeout: float = 60.0,
) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            reset_timeout=reset_timeout,
        )
    return _breakers[name]


def get_all_breaker_statuses() -> list[dict[str, object]]:
    """Get status of all circuit breakers."""
    return [breaker.get_status() for breaker in _breakers.values()]
