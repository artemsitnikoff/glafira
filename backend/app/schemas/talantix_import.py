"""Схемы для интеграции/импорта из Talantix (talantix.ru)."""

from typing import Literal

from pydantic import BaseModel, Field


class TalantixConnectRequest(BaseModel):
    """Подключение Talantix: пользователь вставляет ЦЕЛИКОМ JSON токенов из ЛК Talantix.

    `token` — весь блок `{access_token, expires_in, refresh_token, created_at, ...}` как
    текст (или, для совместимости, голая строка refresh_token). Парсинг — в сервисе.
    Токены write-only, шифруются Fernet, наружу/в логи НЕ возвращаются.
    """
    token: str = Field(..., min_length=1, description="JSON-блок токенов из ЛК Talantix (весь {…})")


class TalantixStatusResponse(BaseModel):
    """Статус подключения Talantix (БЕЗ раскрытия токенов)."""
    connected: bool
    connected_at: str | None = None
    expires_at: str | None = None


class TalantixImportRequest(BaseModel):
    """Запрос превью/импорта из Talantix. Токен уже сохранён (connect) — в теле только режим."""
    dedup_mode: Literal["skip", "update"] = Field(..., description="Режим обработки дублей")


class TalantixImportResponse(BaseModel):
    """Ответ на запуск импорта."""
    job_id: str = Field(..., description="ID задачи для отслеживания прогресса")
