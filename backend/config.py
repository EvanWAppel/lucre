from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    plaid_client_id: str
    plaid_secret: str
    plaid_env: str = "development"
    database_url: str
    encryption_key: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]
