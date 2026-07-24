from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from typing import Literal
from uuid import UUID

from .base import ORMBase


class ApplicationRow(ORMBase):
    id: UUID
    candidate_id: UUID
    display_number: str | None
    full_name: str
    avatar_url: str | None
    age: int | None
    last_position: str | None
    ai_score: int | None
    has_pdn: bool
    phone: str | None
    # Обе формы: старые засиженные — список строк-каналов (["telegram",...]);
    # новые из формы добавления — объекты {type, url}. Фронт рендерит обе.
    messengers: list[dict | str]
    salary_expectation: int | None
    salary_from: int | None
    salary_to: int | None
    currency: str
    city: str | None
    stage: str
    stage_color: str
    selected_at: datetime | None


class MoveRequest(BaseModel):
    to_stage: str
    # Дата выхода — только при to_stage='hired'. Становится start_date сотрудника в
    # Пульсе (двигает «День X» и дедлайны плана). None → сегодня (прежнее поведение).
    hire_date: date | None = None


class RejectRequest(BaseModel):
    reason: str
    side: Literal['candidate', 'company']  # невалидное значение → 422, а не молчаливое сохранение


class BulkMoveRequest(BaseModel):
    application_ids: list[UUID]
    to_stage: str


class BulkRejectRequest(BaseModel):
    application_ids: list[UUID]
    reason: str
    side: Literal['candidate', 'company']


class StageHistoryItem(ORMBase):
    from_stage: str | None
    to_stage: str
    actor_type: str
    actor_name: str | None
    reason: str | None
    created_at: datetime


class StageActionResult(BaseModel):
    new_stage: str


class BulkMoveResult(BaseModel):
    moved_count: int


class BulkRejectResult(BaseModel):
    rejected_count: int
    skipped_count: int = 0  # уже отклонённые / ненайденные — пропущены, не ошибка


# ── Оффер (этап «Оффер») ──────────────────────────────────────────────────────
class OfferPreviewOut(BaseModel):
    body: str      # сгенерированное (или фолбэк) тело оффера — рекрутёр правит
    header: str    # эффективное приветствие, которым сервер обрамит письмо (read-only)
    footer: str    # эффективная подпись, которой сервер обрамит письмо (read-only)


class OfferSendRequest(BaseModel):
    # Тело оффера из попапа (возможно отредактированное). Пустой оффер не шлём → 422.
    # min_length считает пробелы, а send_offer делает body.strip() → строка из одних
    # пробелов прошла бы min_length и ушла бы пустым письмом; поэтому явный strip-валидатор.
    body: str = Field(..., min_length=1)

    @field_validator("body")
    @classmethod
    def _body_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Тело оффера не может быть пустым")
        return v


class OfferStatusOut(BaseModel):
    status: str