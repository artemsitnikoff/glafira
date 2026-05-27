from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    DEFAULT_COMPANY_ID: str = "00000000-0000-0000-0000-000000000001"

    ANTHROPIC_API_KEY: str = ""
    GLAFIRA_MODEL: str = "anthropic/claude-sonnet-4-5"
    GLAFIRA_VERIFY_MODE: str = "mock"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    HH_CLIENT_ID: str = ""
    HH_CLIENT_SECRET: str = ""
    AVITO_CLIENT_ID: str = ""
    AVITO_CLIENT_SECRET: str = ""

    FERNET_KEY: str | None = None


settings = Settings()