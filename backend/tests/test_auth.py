from auth import LoginRateLimiter, hash_password, verify_password
from tests.conftest import TEST_PASSWORD


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_verify_password_roundtrip():
    password_hash = hash_password("hunter2")
    assert verify_password("hunter2", password_hash)
    assert not verify_password("wrong", password_hash)


def test_rate_limiter_locks_after_max_failures():
    clock = FakeClock()
    limiter = LoginRateLimiter(max_attempts=5, window_seconds=900, clock=clock)
    for _ in range(4):
        limiter.record_failure()
    assert not limiter.is_locked()
    limiter.record_failure()
    assert limiter.is_locked()


def test_rate_limiter_unlocks_after_window():
    clock = FakeClock()
    limiter = LoginRateLimiter(max_attempts=5, window_seconds=900, clock=clock)
    for _ in range(5):
        limiter.record_failure()
    assert limiter.is_locked()
    clock.now += 901
    assert not limiter.is_locked()


def test_anonymous_request_redirects_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "password" in response.text.lower()


def test_login_wrong_password_rejected(client):
    response = client.post("/login", data={"password": "wrong"})
    assert response.status_code == 401


def test_login_right_password_grants_access(client):
    response = client.post("/login", data={"password": TEST_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    home = client.get("/")
    assert home.status_code == 200
    assert "Lucre" in home.text


def test_session_cookie_secure_by_default(client):
    response = client.post("/login", data={"password": TEST_PASSWORD}, follow_redirects=False)
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie


def test_session_cookie_not_secure_when_disabled(client, override_settings):
    override_settings(cookie_secure=False)
    response = client.post("/login", data={"password": TEST_PASSWORD}, follow_redirects=False)
    assert "Secure" not in response.headers["set-cookie"]


def test_logout_clears_session(client):
    client.post("/login", data={"password": TEST_PASSWORD})
    assert client.get("/").status_code == 200
    client.post("/logout")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303


def test_lockout_after_five_failures(client):
    for _ in range(5):
        client.post("/login", data={"password": "wrong"})
    response = client.post("/login", data={"password": TEST_PASSWORD})
    assert response.status_code == 429
