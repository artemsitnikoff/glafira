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
    GLAFIRA_VERIFY_MODEL: str = ""  # пустая строка → используется GLAFIRA_MODEL

    # Интернет-разведка кандидата (верификация) идёт через claude CLI с WebSearch/WebFetch
    # (как в ArkadyJarvis) — НЕ через OpenRouter. Нужен долгоживущий OAuth-токен из
    # `claude setup-token` в CLAUDE_CODE_OAUTH_TOKEN. Пусто → разведка не выполняется
    # (блоки «Публичная экспертиза»/«Упоминания» честно покажут «не выполнялась»).
    CLAUDE_CODE_OAUTH_TOKEN: str = ""
    # Общий токен-файл claude (формат ArkadyJarvis: {access_token, refresh_token, expires_at}).
    # Читаем access_token из него на каждый вызов (свежесть держит ArkadyJarvis, мы НЕ рефрешим —
    # иначе гонка single-use refresh). Имеет приоритет над CLAUDE_CODE_OAUTH_TOKEN. Симлинк/маунт
    # общей папки в контейнер настраивается на VPS (см. docker-compose.prod.yml volume).
    CLAUDE_TOKEN_FILE: str = ""
    CLAUDE_CLI_PATH: str = "claude"
    # Модель разведки (шаг «найти»). sonnet — НЕ opus: опус слишком осторожен, отбрасывает
    # реальные находки (проверено на живом кандидате). alias 'sonnet'/'opus' или полный id.
    GLAFIRA_OSINT_MODEL: str = "sonnet"
    # Сек на разведку (шаг «найти»). Идёт В ФОНЕ (fill_candidate_osint), не блокирует HTTP →
    # держим с большим запасом: свободная разведка с веб-поиском доходит до ~170с, бывает дольше.
    GLAFIRA_OSINT_TIMEOUT: int = 240
    # Сколько откликов авто-оценивать за один проход cron (раз в 5 мин). Каждая
    # оценка = платный вызов LLM, поэтому потолок расхода регулируется этим числом.
    GLAFIRA_AUTOSCORE_BATCH: int = 10
    # Текстовый журнал оценок (авто + по кнопке). Пишется на том backend_storage
    # (общий для веб- и cron-контейнера, переживает рестарт). Пусто → не вести.
    SCORING_LOG_PATH: str = "/app/storage/scoring.log"
    # Текстовый журнал чатов (исходящие по всем каналам + входящие hh). Тот же том.
    CHAT_LOG_PATH: str = "/app/storage/chat.log"
    # Текстовый журнал умного подбора (полный лог каждого прогона). Тот же том.
    SMART_SEARCH_LOG_PATH: str = "/app/storage/smart_search.log"

    # Семантический поиск по собственной базе
    GLAFIRA_EMBED_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Умный подбор (hh-ветка) и rerank своей базы используют get_company_llm_model — модель компании
    # из Настройки→AI, с фолбэком на GLAFIRA_MODEL. Переменная GLAFIRA_MODEL_BULK зарезервирована
    # под будущую отдельную bulk-модель (сейчас не используется).
    GLAFIRA_MODEL_BULK: str = ""  # зарезервировано; сейчас не используется
    GLAFIRA_RETRIEVE_CAP: int = 150  # Максимум кандидатов в шорт-листе retrieve
    GLAFIRA_RERANK_CAP: int = 24  # Максимум кандидатов для LLM rerank (синхронный HTTP-таймаут)
    # HNSW ef_search параметр для pgvector (должно быть >= GLAFIRA_RETRIEVE_CAP для полного top-k)
    GLAFIRA_HNSW_EF_SEARCH: int = 300

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Mango Office звонки - транскрибация
    GLAFIRA_TRANSCRIBE_MODEL: str = "google/gemini-2.5-pro"

    HH_CLIENT_ID: str = ""
    HH_CLIENT_SECRET: str = ""
    HH_REDIRECT_URI: str = ""
    HH_USER_AGENT: str = "Glafira/1.0 (glafira.dclouds.ru)"
    HH_AUTHORIZE_URL: str = "https://hh.ru/oauth/authorize"
    HH_TOKEN_URL: str = "https://api.hh.ru/token"
    HH_API_BASE: str = "https://api.hh.ru"
    AVITO_CLIENT_ID: str = ""
    AVITO_CLIENT_SECRET: str = ""

    # Хабр Карьера OAuth — одно приложение Глафиры (один client_id/secret) на все компании.
    # Каждый арендатор подключает свой Хабр-аккаунт через общий Redirect URI, различаясь по state.
    HABR_CLIENT_ID: str = ""
    HABR_CLIENT_SECRET: str = ""
    HABR_REDIRECT_URI: str = ""  # Заказчик задаёт: https://glafira.dclouds.ru/api/v1/integrations/habr/callback
    HABR_AUTHORIZE_URL: str = "https://career.habr.com/integrations/oauth/authorize"  # подтверждён
    # ⚠️ HABR_TOKEN_URL НЕ подтверждён документально — дефолт-догадка.
    # Пиннинг после одобрения приложения Хабром: задать реальный URL в .env на VPS.
    HABR_TOKEN_URL: str = "https://career.habr.com/integrations/oauth/token"
    HABR_SCOPE: str = ""  # scope неизвестен — добавляется в authorize URL ТОЛЬКО если непустой

    # HABR_API_BASE — base URL API Хабр Карьера (подтверждён документацией).
    # Конфигурируемый через .env на VPS при необходимости смены пути.
    HABR_API_BASE: str = "https://career.habr.com/v1/integrations"

    # Telegram MTProto user-аккаунт (my.telegram.org) — одно приложение на инстанс.
    # TELETHON_* имеют приоритет над TELEGRAM_* (так можно задать любые из двух пар).
    TELEGRAM_API_ID: int = 0
    TELEGRAM_API_HASH: str = ""
    TELETHON_API_ID: int = 0
    TELETHON_API_HASH: str = ""

    # Potok.io API integration
    POTOK_API_BASE: str = "https://app.potok.io"
    POTOK_TIMEOUT: int = 30

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