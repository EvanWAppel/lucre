from starlette.requests import Request

from auth import (
    SESSION_COOKIE,
    SessionRole,
    create_session_token,
    current_role,
    is_demo,
    is_owner,
)


def _request(cookie: str | None = None) -> Request:
    """Build a minimal Request carrying (or not) a session cookie."""
    headers: list[tuple[bytes, bytes]] = []
    if cookie is not None:
        headers.append((b"cookie", f"{SESSION_COOKIE}={cookie}".encode()))
    return Request({"type": "http", "headers": headers})


def test_no_cookie_is_demo():
    req = _request()
    assert current_role(req) is SessionRole.DEMO
    assert is_demo(req)
    assert not is_owner(req)


def test_valid_session_is_owner():
    req = _request(create_session_token())
    assert current_role(req) is SessionRole.OWNER
    assert is_owner(req)
    assert not is_demo(req)


def test_invalid_cookie_is_demo():
    req = _request("garbage-not-a-valid-token")
    assert current_role(req) is SessionRole.DEMO
    assert is_demo(req)
    assert not is_owner(req)
