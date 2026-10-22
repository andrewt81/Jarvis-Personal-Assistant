from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True, slots=True)
class RateLimit:
    attempts: int
    window_seconds: int


DEFAULT_CLIENT_LIMIT = RateLimit(20, 300)
DEFAULT_ACCOUNT_LIMIT = RateLimit(10, 900)


class AuthenticationRateLimiter:
    """Small bounded limiter for the single-instance MVP deployment."""

    def __init__(
        self,
        *,
        now: Callable[[], float] = time.monotonic,
        client_limit: RateLimit = DEFAULT_CLIENT_LIMIT,
        account_limit: RateLimit = DEFAULT_ACCOUNT_LIMIT,
        maximum_keys: int = 10_000,
    ) -> None:
        self._now = now
        self._limits = {"client": client_limit, "account": account_limit}
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._maximum_keys = maximum_keys
        self._lock = Lock()

    def retry_after(self, client_key: str, account_key: str) -> int | None:
        with self._lock:
            now = self._now()
            waits = [
                self._wait_for(f"client:{client_key}", self._limits["client"], now),
                self._wait_for(f"account:{account_key}", self._limits["account"], now),
            ]
            pending = [wait for wait in waits if wait is not None]
            return max(pending) if pending else None

    def failure(self, client_key: str, account_key: str) -> None:
        with self._lock:
            now = self._now()
            self._record(f"client:{client_key}", now)
            self._record(f"account:{account_key}", now)
            if len(self._failures) > self._maximum_keys:
                self._discard_stale_then_oldest(now)

    def success(self, account_key: str) -> None:
        with self._lock:
            self._failures.pop(f"account:{account_key}", None)

    def _wait_for(self, key: str, limit: RateLimit, now: float) -> int | None:
        failures = self._failures.get(key)
        if failures is None:
            return None
        threshold = now - limit.window_seconds
        while failures and failures[0] <= threshold:
            failures.popleft()
        if not failures:
            self._failures.pop(key, None)
            return None
        if len(failures) < limit.attempts:
            return None
        return max(1, int(failures[0] + limit.window_seconds - now) + 1)

    def _record(self, key: str, now: float) -> None:
        failures = self._failures[key]
        failures.append(now)
        limit = self._limits[key.partition(":")[0]]
        threshold = now - limit.window_seconds
        while failures and failures[0] <= threshold:
            failures.popleft()

    def _discard_stale_then_oldest(self, now: float) -> None:
        for key in list(self._failures):
            group = key.partition(":")[0]
            self._wait_for(key, self._limits[group], now)
            if len(self._failures) <= self._maximum_keys:
                return
        while len(self._failures) > self._maximum_keys:
            oldest_key = min(self._failures, key=lambda key: self._failures[key][-1])
            self._failures.pop(oldest_key, None)
