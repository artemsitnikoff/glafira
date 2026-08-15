"""Схемы для интеграции/импорта из Talantix (talantix.ru)."""

from typing import Literal

from pydantic import BaseModel, Field


class TalantixConnectRequest(BaseModel):
    """Подключение Talantix: пара токенов из json в ЛК Talantix.

    refresh_token — обязателен (долгоживущий, из него минтим access). access_token —
    опционален (ЛК отдаёт оба, но нам достаточно refresh). Токены write-only, шифруются
    Fernet, наружу НЕ возвращаются.
    """
    refresh_token: str = Field(..., min_length=1, description="refresh_token Talantix из ЛК")
    access_token: str | None = Field(default=None, description="access_token Talantix из ЛК (опционально)")


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
