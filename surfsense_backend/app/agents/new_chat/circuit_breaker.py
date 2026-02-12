"""Circuit breaker for external API resilience.

Implements the circuit breaker pattern to prevent cascading failures when
external services are unavailable. The breaker has three states:

- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold exceeded, requests blocked
- HALF_OPEN: Testing recovery after timeout, limited requests allowed

State transitions:
    CLOSED --[failures >= threshold]--> OPEN
    OPEN --[timeout elapsed]--> HALF_OPEN
    HALF_OPEN --[success]--> CLOSED
    HALF_OPEN --[failure]--> OPEN
"""

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
    """Simple circuit breaker for external service calls.
    
    Tracks failure count and transitions between states to protect against
    cascading failures. When the breaker is OPEN, calls are immediately rejected
    without attempting the external service call.
    
    Example:
        breaker = get_breaker("my_service")
        if not breaker.can_execute():
            return {"error": "Service temporarily unavailable"}
        
        try:
            result = await external_service.call()
            breaker.record_success()
            return result
        except Exception:
            breaker.record_failure()
            raise
    """
    
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
