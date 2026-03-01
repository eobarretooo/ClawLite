from __future__ import annotations

import random
import time
from collections import deque
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    retries: int = 3,
    base_delay_s: float = 0.4,
    max_delay_s: float = 5.0,
    jitter: float = 0.15,
) -> T:
    """Executa função com retry exponencial + jitter.

    Levanta a última exceção após esgotar tentativas.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception:
            if attempt >= retries:
                raise
            sleep_s = min(max_delay_s, base_delay_s * (2 ** attempt))
            sleep_s += random.uniform(0, jitter)
            time.sleep(sleep_s)
            attempt += 1


class RateLimiter:
    """Token-bucket simples para evitar flood em canais."""

    def __init__(self, rate_per_sec: float, burst: int):
        self.rate = max(0.1, float(rate_per_sec))
        self.burst = max(1, int(burst))
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        now = time.time()
        window = self.burst / self.rate
        while self._events and now - self._events[0] > window:
            self._events.popleft()
        if len(self._events) >= self.burst:
            return False
        self._events.append(now)
        return True
