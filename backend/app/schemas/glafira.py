"""Схемы для Glafira API"""

from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from .base import ORMBase


class ScoreRequest(BaseModel):
    candidate_id: UUID
    vacancy_id: UUID | None = None  # ← ОПЦИОНАЛЬНО (общая оценка резюме)


class RequirementMatch(BaseModel):
    criterion: str  # критерий оценки
    weight: int  # максимальный вес критерия
    points: int  # набранные баллы (≤ weight)
    comment: str | None  # комментарий по критерию


class EvaluationOut(ORMBase):
    id: UUID
    candidate_id: UUID
    vacancy_id: UUID | None = None  # ← вернуть в схему
    application_id: UUID | None = None
    score: int
    verdict: str  # 'auto_reject'|'interview'|'auto_select' (по TZ; уточни)
    summary: str
    strengths: list[str]
    risks: list[str]
    requirements_match: list[RequirementMatch]  # ← НЕ dict
    forecast: str
    questions: list[str] = []
    model: str | None = None
    created_at: datetime  # ← ОБЯЗАТЕЛЬНО


class ScreeningStartRequest(BaseModel):
    candidate_id: UUID
    application_id: UUID | None = None
    script_key: str | None = None  # опционально — какой сценарий


class ScreeningReplyRequest(BaseModel):
    candidate_id: UUID
    message: str  # текст ответа кандидата


class ScreeningOut(BaseModel):
    message: str  # ответ Глафиры
    finished: bool  # True = скрининг завершён, диалог можно закрывать
    extracted: dict  # извлечённые из диалога факты {salary_expectation, ready_relocate, ...}