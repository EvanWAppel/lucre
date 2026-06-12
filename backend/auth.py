import logging
import time
from collections import deque
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from config import settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "lucre_session"
SESSION_MAX_AGE_SECONDS = 365 * 24 * 3600

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    # A malformed hash (InvalidHashError) is a configuration error — let it propagate.


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="lucre-session")


def create_session_token() -> str:
    return _serializer().dumps({"v": 1})


def session_token_valid(token: str) -> bool:
    try:
        _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return True
    except BadSignature:
        return False


class LoginRateLimiter:
    """Locks out logins after max_attempts failures within window_seconds."""

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 900,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: deque[float] = deque()

    def record_failure(self) -> None:
        self._failures.append(self._clock())

    def reset(self) -> None:
        self._failures.clear()

    def is_locked(self) -> bool:
        cutoff = self._clock() - self.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()
        return len(self._failures) >= self.max_attempts


login_rate_limiter = LoginRateLimiter()


def require_login(request: Request) -> None:
    """Dependency: redirect anonymous requests to the login page."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token or not session_token_valid(token):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
