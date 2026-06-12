import pytest
from pydantic import ValidationError

from config import Settings


def make_settings(**overrides) -> Settings:
    kwargs = {
        "plaid_client_id": "id",
        "plaid_secret": "secret",
        "database_url": "sqlite:///:memory:",
        "encryption_key": "key",
        "app_password_hash": "hash",
        "session_secret": "session",
    }
    kwargs.update(overrides)
    # _env_file is a runtime-only pydantic-settings kwarg ty can't see.
    return Settings(_env_file=None, **kwargs)  # ty: ignore[unknown-argument, invalid-argument-type]


@pytest.fixture(autouse=True)
def clean_plaid_env(monkeypatch):
    monkeypatch.delenv("PLAID_ENV", raising=False)


def test_plaid_env_defaults_to_sandbox():
    assert make_settings().plaid_env == "sandbox"


def test_plaid_env_accepts_production():
    assert make_settings(plaid_env="production").plaid_env == "production"


def test_plaid_env_rejects_retired_development():
    with pytest.raises(ValidationError):
        make_settings(plaid_env="development")


def test_email_settings_default_empty():
    settings = make_settings()
    assert settings.resend_api_key == ""
    assert settings.alert_from_email == ""
    assert settings.alert_to_email == ""


def test_auth_settings_are_required(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    kwargs = {
        "plaid_client_id": "id",
        "plaid_secret": "secret",
        "database_url": "sqlite:///:memory:",
        "encryption_key": "key",
    }
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)  # ty: ignore[unknown-argument, invalid-argument-type]
