from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable


class TokenBucketRateLimiter:
    def __init__(
        self,
        requests_per_second: float,
        burst: int = 1,
        jitter_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than 0")
        if burst < 1:
            raise ValueError("burst must be at least 1")
        if jitter_seconds < 0:
            raise ValueError("jitter_seconds must be nonnegative")
        self.rate = requests_per_second
        self.capacity = float(burst)
        self.jitter_seconds = jitter_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._tokens = float(burst)
        self._last_refill = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                elapsed = max(0.0, now - self._last_refill)
                self._tokens = min(
                    self.capacity,
                    self._tokens + elapsed * self.rate,
                )
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_seconds = (1.0 - self._tokens) / self.rate
                if self.jitter_seconds:
                    wait_seconds += random.uniform(0, self.jitter_seconds)
            self._sleeper(wait_seconds)
