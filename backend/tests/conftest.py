import os

from argon2 import PasswordHasher
from cryptography.fernet import Fernet

TEST_PASSWORD = "test-password"

# config.Settings() reads the environment at import time, so these must be set
# before any app module is imported.
os.environ.setdefault("PLAID_CLIENT_ID", "test-plaid-client-id")
os.environ.setdefault("PLAID_SECRET", "test-plaid-secret")
os.environ.setdefault("PLAID_ENV", "sandbox")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("APP_PASSWORD_HASH", PasswordHasher().hash(TEST_PASSWORD))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from config import settings  # noqa: E402
from database import Base, get_db  # noqa: E402


@pytest.fixture
def engine():
    """Fresh in-memory SQLite engine with all tables created."""
    import models  # noqa: F401 — registers models on Base

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db_session(engine):
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = factory()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def reset_login_rate_limiter():
    from auth import login_rate_limiter

    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()


@pytest.fixture
def override_settings(monkeypatch):
    """Temporarily override attributes on the global settings object."""

    def _override(**kwargs):
        for key, value in kwargs.items():
            monkeypatch.setattr(settings, key, value)

    return _override


class FakePlaidClient:
    """In-memory stand-in for plaid_client.PlaidClient. No network, ever.

    Tests may mutate the canned data before exercising routes/services.
    """

    def __init__(self):
        self.link_token = "link-sandbox-fake-token"
        self.exchanges = {
            "public-token-1": {"item_id": "plaid-item-1", "access_token": "access-token-1"}
        }
        self.accounts = {
            "access-token-1": [
                {
                    "plaid_account_id": "acct-checking-1",
                    "name": "Everyday Checking",
                    "type": "depository",
                    "subtype": "checking",
                    "balance": 1500.25,
                },
                {
                    "plaid_account_id": "acct-credit-1",
                    "name": "Travel Card",
                    "type": "credit",
                    "subtype": "credit card",
                    "balance": 432.10,
                },
            ]
        }

    def create_link_token(self) -> str:
        return self.link_token

    def exchange_public_token(self, public_token: str) -> dict:
        return dict(self.exchanges[public_token])

    def get_accounts(self, access_token: str) -> list[dict]:
        return [dict(account) for account in self.accounts[access_token]]


@pytest.fixture
def fake_plaid():
    return FakePlaidClient()


@pytest.fixture
def client(db_session, fake_plaid):
    """TestClient with the test DB session and fake Plaid client injected."""
    from main import app
    from plaid_client import get_plaid_client

    def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_plaid_client] = lambda: fake_plaid
    # https base_url so Secure session cookies are stored and sent by the test client.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
