from pydantic import BaseModel
from datetime import datetime
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


class RejectRequest(BaseModel):
    reason: str
    side: Literal['candidate', 'company']  # невалидное значение → 422, а не молчаливое сохранение


class BulkMoveRequest(BaseModel):
    application_ids: list[UUID]
    to_stage: str


class BulkRejectRequest(BaseModel):
    application_ids: list[UUID]
    reason: str
    side: str


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