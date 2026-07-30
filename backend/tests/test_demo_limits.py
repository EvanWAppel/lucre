import demo_limits
from auth import DEMO_COOKIE
from rate_limit import SlidingWindowRateLimiter
from services.demo_store import DemoStoreManager

# --- LRU cap on demo stores --------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _seed(session) -> None:  # noqa: ANN001 — trivial test seed
    pass


def test_cap_evicts_least_recently_used():
    clock = FakeClock()
    mgr = DemoStoreManager(seed=_seed, max_stores=2, clock=clock)
    mgr.get_or_create("a")
    clock.now += 1
    mgr.get_or_create("b")
    clock.now += 1
    mgr.get_or_create("a")  # touch a, so b is now least-recently-used
    clock.now += 1
    mgr.get_or_create("c")  # admits c, evicts b
    assert mgr.active_session_ids() == {"a", "c"}


# --- Middleware rate limiting -------------------------------------------------


def test_demo_creation_rate_limited(client, monkeypatch):
    monkeypatch.setattr(
        demo_limits, "create_limiter", SlidingWindowRateLimiter(max_events=1, window_seconds=60)
    )
    first = client.get("/robots.txt")  # mints a demo session
    assert first.status_code == 200
    client.cookies.delete(DEMO_COOKIE)  # next request looks like a brand-new visitor
    blocked = client.get("/robots.txt")
    assert blocked.status_code == 429


def test_demo_writes_rate_limited(client, monkeypatch):
    monkeypatch.setattr(
        demo_limits, "write_limiter", SlidingWindowRateLimiter(max_events=1, window_seconds=60)
    )
    assert client.post("/api/sync").status_code != 429  # first write allowed
    assert client.post("/api/sync").status_code == 429  # second write blocked


def test_safe_methods_not_write_limited(client, monkeypatch):
    monkeypatch.setattr(
        demo_limits, "write_limiter", SlidingWindowRateLimiter(max_events=1, window_seconds=60)
    )
    assert client.get("/robots.txt").status_code == 200
    assert client.get("/robots.txt").status_code == 200  # GETs never hit the write limiter
