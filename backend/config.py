from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the repo root, one level above backend/. Resolved from this file
# so it works regardless of the current working directory; real env vars always
# take precedence (e.g. on Railway, where no .env exists).
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    plaid_client_id: str
    plaid_secret: str
    # Plaid retired the "development" environment in June 2024.
    plaid_env: Literal["sandbox", "production"] = "sandbox"
    # OAuth redirect URI (e.g. https://<app>/link). Required for OAuth institutions
    # like Chase; must be registered in the Plaid dashboard. Empty disables OAuth.
    plaid_redirect_uri: str = ""
    database_url: str
    encryption_key: str
    app_password_hash: str
    session_secret: str
    # Set false only for local http development (Safari rejects Secure cookies on http://localhost)
    cookie_secure: bool = True
    resend_api_key: str = ""
    alert_from_email: str = ""
    alert_to_email: str = ""

    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8")


# Populated from the environment / .env file at import time.
settings = Settings()  # ty: ignore[missing-argument]
