from pydantic import BaseModel
from datetime import datetime
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
    messengers: list[str]
    salary_expectation: int | None
    currency: str
    city: str | None
    stage: str
    stage_color: str
    selected_at: datetime | None


class MoveRequest(BaseModel):
    to_stage: str


class RejectRequest(BaseModel):
    reason: str
    side: str  # candidate|company


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