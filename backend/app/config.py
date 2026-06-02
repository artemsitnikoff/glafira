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
    GLAFIRA_MODEL: str = "anthropic/claude-sonnet-4-6"
    GLAFIRA_VERIFY_MODE: str = "mock"
    # Сколько откликов авто-оценивать за один проход cron (раз в 5 мин). Каждая
    # оценка = платный вызов LLM, поэтому потолок расхода регулируется этим числом.
    GLAFIRA_AUTOSCORE_BATCH: int = 10

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    HH_CLIENT_ID: str = ""
    HH_CLIENT_SECRET: str = ""
    HH_REDIRECT_URI: str = ""
    HH_USER_AGENT: str = "Glafira/1.0 (glafira.dclouds.ru)"
    HH_AUTHORIZE_URL: str = "https://hh.ru/oauth/authorize"
    HH_TOKEN_URL: str = "https://api.hh.ru/token"
    HH_API_BASE: str = "https://api.hh.ru"
    AVITO_CLIENT_ID: str = ""
    AVITO_CLIENT_SECRET: str = ""

    # Telegram MTProto user-аккаунт (my.telegram.org) — одно приложение на инстанс.
    TELEGRAM_API_ID: int = 0
    TELEGRAM_API_HASH: str = ""

    # DaData — подсказки городов (suggestions API использует только API_KEY/Token;
    # SECRET_KEY нужен лишь для Clean API стандартизации, держим на будущее).
    DADATA_API_KEY: str = ""
    DADATA_SECRET_KEY: str = ""

    FERNET_KEY: str | None = None

    # Deployment
    CORS_ORIGINS: str = "http://localhost:5173"  # comma-separated list
    SESSION_COOKIE_SECURE: bool = False  # True in production with HTTPS
    FRONTEND_BASE_URL: str = "https://glafira.dclouds.ru"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()