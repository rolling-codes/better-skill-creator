"""One thread-safe call allowance shared by all model work in an operation."""
from __future__ import annotations

from threading import Lock
from math import isfinite

DEFAULT_MAX_CALLS = 20


def result_usage(event: dict) -> dict:
    """Return provider-reported values without replacing unavailable fields with zero."""
    usage = event.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return {key: value for key, value in {
        "cost_usd": event.get("total_cost_usd"),
        "duration_ms": event.get("duration_ms"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
    }.items() if (type(value) is int and 0 <= value < 2**63)
        or (isinstance(value, float) and isfinite(value) and value >= 0)}


class CallBudget:
    def __init__(self, limit=DEFAULT_MAX_CALLS):
        """Create an unused allowance; reject limits that are not positive integers."""
        if type(limit) is not int or limit < 1:
            raise ValueError('max-calls must be a positive integer')
        self.limit = limit
        self.used = 0
        self._lock = Lock()
        self._attempts: dict[int, dict] = {}

    def require(self, count):
        """Raise ValueError if count exceeds the remaining allowance, without reserving it."""
        with self._lock:
            if count > self.limit - self.used:
                raise ValueError(f'Operation needs up to {count} calls; only {self.limit-self.used} remain. Explicitly raise --max-calls to authorize more.')

    def consume(self, stage: str | None = None) -> int:
        """Atomically charge one attempt, raising ValueError if the allowance is exhausted."""
        with self._lock:
            if self.used >= self.limit:
                raise ValueError('Model call budget exhausted')
            self.used += 1  # A failed launch/response still consumes an attempt.
            if stage:
                self._attempts[self.used] = {"stage": stage, "reported_usage": None}
            return self.used

    def record_usage(self, attempt: int, usage: dict | None) -> None:
        with self._lock:
            self._attempts[attempt]["reported_usage"] = usage or None

    def usage_report(self) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self._attempts.values()]

    def report(self):
        """Return a consistent snapshot of the limit, used calls, and remaining calls."""
        with self._lock:
            return {'limit': self.limit, 'used': self.used, 'remaining': self.limit-self.used}
