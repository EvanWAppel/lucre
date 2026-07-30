"""A small in-memory sliding-window rate limiter, keyed by an arbitrary string.

Used to bound anonymous demo traffic (session creation per IP, write actions per
session). Single-process and in-memory, matching the app's single-service shape.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_events: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Record an event for ``key`` and return whether it is within the limit."""
        now = self._clock()
        cutoff = now - self.window_seconds
        events = self._events[key]
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= self.max_events:
            return False
        events.append(now)
        return True

    def reset(self) -> None:
        self._events.clear()
