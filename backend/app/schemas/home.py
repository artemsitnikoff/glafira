"""Pydantic схемы для Home домена"""

from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID

from .base import ORMBase


class KpiCard(BaseModel):
    key: str
    value: float
    unit: str | None = None
    delta: float | None = None
    delta_dir: str  # up|down|up-bad|down-good|flat
    caption: str | None = None


class HomeKpi(BaseModel):
    period: str
    cards: list[KpiCard]


class AttentionItem(BaseModel):
    vacancy_id: UUID
    vacancy_name: str
    kind: str  # urgent|warn|deadline
    text: str


class EventOut(ORMBase):
    id: UUID
    type: str
    text: str
    entities: list = Field(default_factory=list)
    created_at: datetime


class AttentionHrItem(BaseModel):
    employee_id: UUID
    full_name: str
    position: str | None = None
    reason: str
    adapt_day: int
    risk_score: int


class PulseSummary(BaseModel):
    onboarding_count: int
    onboarding_delta: int
    risk_split: dict[str, int]
    satisfaction_avg: float | None = None
    answered_pct: float
    silent_pct: float
    enps: int | None = None
    enps_delta: int | None = None
    attention_hr: list[AttentionHrItem]


class SourceItem(BaseModel):
    source: str
    count: int