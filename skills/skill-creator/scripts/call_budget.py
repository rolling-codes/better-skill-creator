"""One thread-safe call allowance shared by all model work in an operation."""
from __future__ import annotations

from threading import Lock

DEFAULT_MAX_CALLS = 20


class CallBudget:
    def __init__(self, limit=DEFAULT_MAX_CALLS):
        if type(limit) is not int or limit < 1:
            raise ValueError('max-calls must be a positive integer')
        self.limit = limit
        self.used = 0
        self._lock = Lock()

    def require(self, count):
        with self._lock:
            if count > self.limit - self.used:
                raise ValueError(f'Operation needs up to {count} calls; only {self.limit-self.used} remain. Explicitly raise --max-calls to authorize more.')

    def consume(self):
        with self._lock:
            if self.used >= self.limit:
                raise ValueError('Model call budget exhausted')
            self.used += 1  # A failed launch/response still consumes an attempt.

    def report(self):
        with self._lock:
            return {'limit': self.limit, 'used': self.used, 'remaining': self.limit-self.used}
