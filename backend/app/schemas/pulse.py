from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from typing import Literal
from .base import ORMBase


class EmployeeListItem(ORMBase):
    id: UUID
    full_name: str
    position: str | None = None
    department: str | None = None
    avatar_url: str | None = None
    probation_days: int
    start_date: date
    adapt_day: int = 0  # computed
    status: str
    risk_level: str = "low"
    enps: int | None = None
    manager_full_name: str | None = None
    last_survey_date: datetime | None = None
    last_survey_mood: float | None = None


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
    public_token: str | None = None
    questions: list = []

    @field_validator("answers", "questions", mode="before")
    @classmethod
    def _normalize_list(cls, v):
        # Толерантность к легаси-форме JSONB: иногда answers/questions лежат как
        # {"items": [...]} (а не как список) — нормализуем, чтобы не падать 500.
        if v is None:
            return []
        if isinstance(v, dict):
            items = v.get("items")
            return items if isinstance(items, list) else []
        if isinstance(v, list):
            return v
        return []


class SurveyCreate(BaseModel):
    # Запуск опроса по выбранному шаблону. Вопросы снапшотятся из шаблона,
    # генерится публичная ссылка (public_token).
    template_id: UUID


# ===== Публичная (без авторизации) страница опроса =====

class PublicSurveyQuestion(BaseModel):
    id: str
    text: str
    kind: str          # emoji5 | scale5 | yesno | nps11 | text
    scale: str | None = None
    optional: bool = False


class PublicSurveyOut(BaseModel):
    company_name: str
    employee_first_name: str
    type: str
    answered: bool
    questions: list[PublicSurveyQuestion] = []


class PublicAnswer(BaseModel):
    id: str
    answer: str


class PublicSurveySubmit(BaseModel):
    answers: list[PublicAnswer]


class PublicSurveySubmitResult(BaseModel):
    status: str = "success"
    overall_score: float | None = None


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


class EmployeeStatusUpdate(BaseModel):
    status: Literal['onboarding', 'passed', 'left']
    left_at: date | None = None
    left_reason: str | None = None


class BulkRunSurveyRequest(BaseModel):
    employee_ids: list[UUID]
    template_key: str
    send_at: datetime | None = None


class BulkRunSurveyResult(BaseModel):
    launched_count: int


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
    candidate_id: UUID  # для ссылки на карточку соискателя + Chat/Actions табов
    left_at: date | None = None  # для баннера «Уволен»
    left_reason: str | None = None  # для баннера «Уволен»
    ai_summary: str | None = None
    ai_summary_generated_at: datetime | None = None
    plan: list[PlanItemOut] = Field(default_factory=list)
    surveys: list[SurveyOut] = Field(default_factory=list)
    alerts: list[AlertOut] = Field(default_factory=list)
    notes: list[NoteOut] = Field(default_factory=list)


class EmployeeSummaryResponse(BaseModel):
    summary: str | None = None
    generated_at: datetime | None = None


class PulseKPI(BaseModel):
    onboarding_count: int
    passed_probation: int
    passed_probation_delta: int  # vs предыдущий период
    left_in_90d: int
    left_in_90d_pct: float
    enps: int | None = None