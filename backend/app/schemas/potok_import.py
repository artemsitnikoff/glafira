"""Схемы для импорта из Potok.io"""

from pydantic import BaseModel, Field
from typing import Literal


class PotokImportRequest(BaseModel):
    """Запрос импорта из Potok.io"""
    token: str = Field(..., min_length=1, description="API токен Potok.io")
    dedup_mode: Literal["skip", "update"] = Field(..., description="Режим обработки дублей")


class PotokImportResponse(BaseModel):
    """Ответ на запрос импорта"""
    job_id: str = Field(..., description="ID задачи для отслеживания прогресса")