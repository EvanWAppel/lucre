import demo_limits
from auth import DEMO_COOKIE
from rate_limit import SlidingWindowRateLimiter
from tests.conftest import TEST_PASSWORD


def test_demo_cookie_minted_for_anonymous(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert DEMO_COOKIE in response.headers.get("set-cookie", "")


def test_demo_cookie_not_reminted_when_present(client):
    client.get("/robots.txt")  # mints it
    response = client.get("/robots.txt")  # cookie now sent back; no re-mint
    assert DEMO_COOKIE not in response.headers.get("set-cookie", "")


def test_no_demo_cookie_for_owner(client):
    client.post("/login", data={"password": TEST_PASSWORD})
    response = client.get("/robots.txt")
    assert DEMO_COOKIE not in response.headers.get("set-cookie", "")


def test_health_bypasses_demo_middleware(client, monkeypatch):
    """The platform healthcheck (Railway) is anonymous and cookieless. /health
    must skip the demo-session middleware entirely: never mint a demo session and
    never be subject to the demo create-limiter — otherwise repeated healthchecks
    exhaust the limiter and return 429, failing the deploy."""
    monkeypatch.setattr(
        demo_limits,
        "create_limiter",
        SlidingWindowRateLimiter(max_events=1, window_seconds=60),
    )
    for _ in range(5):
        response = client.get("/health")
        assert response.status_code == 200
        assert DEMO_COOKIE not in response.headers.get("set-cookie", "")
