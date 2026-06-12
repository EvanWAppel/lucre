from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    plaid_client_id: str
    plaid_secret: str
    # Plaid retired the "development" environment in June 2024.
    plaid_env: Literal["sandbox", "production"] = "sandbox"
    database_url: str
    encryption_key: str
    app_password_hash: str
    session_secret: str
    resend_api_key: str = ""
    alert_from_email: str = ""
    alert_to_email: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Populated from the environment / .env file at import time.
settings = Settings()  # ty: ignore[missing-argument]
