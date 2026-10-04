"""One thread-safe call allowance shared by all model work in an operation."""
from __future__ import annotations

from threading import Lock

DEFAULT_MAX_CALLS = 20


class CallBudget:
    def __init__(self, limit=DEFAULT_MAX_CALLS):
        """Create an unused allowance; reject limits that are not positive integers."""
        if type(limit) is not int or limit < 1:
            raise ValueError('max-calls must be a positive integer')
        self.limit = limit
        self.used = 0
        self._lock = Lock()

    def require(self, count):
        """Raise ValueError if count exceeds the remaining allowance, without reserving it."""
        with self._lock:
            if count > self.limit - self.used:
                raise ValueError(f'Operation needs up to {count} calls; only {self.limit-self.used} remain. Explicitly raise --max-calls to authorize more.')

    def consume(self):
        """Atomically charge one attempt, raising ValueError if the allowance is exhausted."""
        with self._lock:
            if self.used >= self.limit:
                raise ValueError('Model call budget exhausted')
            self.used += 1  # A failed launch/response still consumes an attempt.

    def report(self):
        """Return a consistent snapshot of the limit, used calls, and remaining calls."""
        with self._lock:
            return {'limit': self.limit, 'used': self.used, 'remaining': self.limit-self.used}
