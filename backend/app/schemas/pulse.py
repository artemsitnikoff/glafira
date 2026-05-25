from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, Field
from .base import ORMBase


class EmployeeListItem(ORMBase):
    id: UUID
    full_name: str
    position: str | None = None
    department: str | None = None
    start_date: date
    adapt_day: int = 0  # computed
    status: str
    risk_level: str = "low"
    enps: int | None = None
    manager_full_name: str | None = None


class PlanItemOut(ORMBase):
    id: UUID
    phase: str
    title: str
    deadline_day: int | None = None
    responsible: str
    is_done: bool = False
    done_at: datetime | None = None
    order_index: int


class PlanItemUpdate(BaseModel):
    is_done: bool | None = None


class SurveyOut(ORMBase):
    id: UUID
    type: str
    template_key: str | None = None
    sent_at: datetime
    answered_at: datetime | None = None
    overall_score: float | None = None
    answers: list = []


class SurveyCreate(BaseModel):
    type: str  # weekly|monthly|special|enps
    template_key: str | None = None


class AlertOut(ORMBase):
    id: UUID
    employee_id: UUID
    level: str
    title: str
    context: str | None = None
    action_type: str | None = None
    is_dismissed: bool = False
    created_at: datetime


class NoteCreate(BaseModel):
    text: str


class NoteOut(BaseModel):
    text: str
    author_user_id: str
    created_at: str


class EmployeeDetail(ORMBase):
    id: UUID
    full_name: str
    position: str | None = None
    department: str | None = None
    start_date: date
    probation_days: int
    adapt_day: int = 0
    status: str
    risk_level: str = "low"
    enps: int | None = None
    manager_full_name: str | None = None
    recruiter_full_name: str | None = None
    hire_source: str | None = None
    plan: list[PlanItemOut] = Field(default_factory=list)
    surveys: list[SurveyOut] = Field(default_factory=list)
    alerts: list[AlertOut] = Field(default_factory=list)
    notes: list[NoteOut] = Field(default_factory=list)


class PulseKPI(BaseModel):
    onboarding_count: int
    passed_probation: int
    passed_probation_delta: int  # vs предыдущий период
    left_in_90d: int
    left_in_90d_pct: float
    enps: int | None = None