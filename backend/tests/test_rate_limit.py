from rate_limit import SlidingWindowRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_limit_then_blocks():
    limiter = SlidingWindowRateLimiter(max_events=3, window_seconds=60, clock=FakeClock())
    assert [limiter.allow("k") for _ in range(4)] == [True, True, True, False]


def test_separate_keys_are_independent():
    limiter = SlidingWindowRateLimiter(max_events=1, window_seconds=60, clock=FakeClock())
    assert limiter.allow("a")
    assert limiter.allow("b")
    assert not limiter.allow("a")


def test_window_slides():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(max_events=1, window_seconds=60, clock=clock)
    assert limiter.allow("k")
    assert not limiter.allow("k")
    clock.now += 61
    assert limiter.allow("k")
