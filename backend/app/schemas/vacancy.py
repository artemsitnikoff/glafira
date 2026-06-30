from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from .base import ORMBase
from .user import UserShort


class StageInput(BaseModel):
    """Schema for custom stage input when creating vacancy"""
    stage_key: str = Field(..., max_length=20)
    label: str = Field(..., max_length=60)
    order_index: int
    is_terminal: bool = False
    description: str | None = None  # инструкции/контекст этапа для команды


class RejectReasonInput(BaseModel):
    """Schema for reject reason input when creating vacancy (форма «Воронка»)"""
    side: str = Field(..., max_length=20)  # 'candidate' | 'company'
    label: str = Field(..., max_length=120)
    order_index: int = 0
    is_system: bool = False


class VacancySidebarItem(ORMBase):
    id: UUID
    name: str
    count: int
    new_count: int


class VacancySidebar(BaseModel):
    items: list[VacancySidebarItem]
    archived_count: int


class ArchivedVacancyItem(BaseModel):
    """Архивная вакансия с агрегатами для страницы Архив."""
    id: UUID
    name: str
    client_name: str | None = None
    recruiter_name: str | None = None
    archive_result: str | None = None  # hired | cancelled | frozen
    closed_at: date | None = None
    created_at: datetime
    candidates: int  # всего заявок прошло
    hired: int       # заявок в этапе hired


class VacancyStageCount(BaseModel):
    stage_key: str
    label: str
    color: str
    count: int
    is_terminal: bool
    description: str | None = None


class VacancyDetail(ORMBase):
    id: UUID
    name: str
    sort_order: int
    client_id: UUID | None = None
    client_name: str | None = None
    city: str | None = None
    deadline: date | None = None
    positions_count: int
    department: str | None = None
    employment_type: str | None = None
    is_confidential: bool
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str
    description: str | None = None
    recruiter_scoring_instructions: str | None = None
    status: str
    glafira_mode: str
    responsible_user_id: UUID | None = None
    responsible_user: UserShort | None = None
    team: list[UserShort] = Field(default_factory=list)
    external_source: str | None = None
    external_url: str | None = None
    hh_vacancy_id: str | None = None
    habr_vacancy_id: str | None = None
    avito_vacancy_id: str | None = None
    archive_result: str | None = None
    closed_at: date | None = None
    created_at: datetime

    # Automation fields
    auto_move: bool
    auto_move_threshold: int
    auto_move_stage: str | None = None
    auto_qa: bool
    auto_reject: bool
    auto_reject_message: bool
    rejection_text: str | None = None

    @field_validator('team', mode='before')
    @classmethod
    def validate_team(cls, v):
        """Convert VacancyTeam objects to UserShort objects if needed"""
        if not v:
            return v

        # If first element has 'user' attribute, it's a VacancyTeam object
        if hasattr(v[0], 'user'):
            return [team_member.user for team_member in v]

        # Otherwise, assume it's already UserShort objects or compatible
        return v


class VacancyCreate(BaseModel):
    name: str
    sort_order: int = 500
    client_id: UUID | None = None
    city: str | None = None
    deadline: date | None = None
    positions_count: int = 1
    department: str | None = None
    employment_type: str | None = None
    is_confidential: bool = False
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str = "RUB"
    description: str | None = None
    recruiter_scoring_instructions: str | None = None
    funnel_template: str = "default"
    glafira_mode: Literal["A", "B", "C"] = "A"
    team: list[UUID] = []
    auto_move: bool = False
    auto_move_threshold: int = Field(default=80, ge=0, le=100)
    auto_move_stage: str | None = None
    auto_qa: bool = False
    auto_reject: bool = False
    auto_reject_message: bool = False
    rejection_text: str | None = None
    stages: list[StageInput] | None = None
    reject_reasons: list[RejectReasonInput] | None = None

    @field_validator('stages')
    @classmethod
    def validate_stages(cls, v):
        if v is not None and len(v) < 3:
            raise ValueError('Minimum 3 stages required for custom funnel')
        return v


class VacancyUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None
    client_id: UUID | None = None
    city: str | None = None
    deadline: date | None = None
    positions_count: int | None = None
    department: str | None = None
    employment_type: str | None = None
    is_confidential: bool | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str | None = None
    description: str | None = None
    recruiter_scoring_instructions: str | None = None
    status: str | None = None
    glafira_mode: Literal["A", "B", "C"] | None = None
    team: list[UUID] | None = None
    auto_move: bool | None = None
    auto_move_threshold: int | None = Field(default=None, ge=0, le=100)
    auto_move_stage: str | None = None
    auto_qa: bool | None = None
    auto_reject: bool | None = None
    auto_reject_message: bool | None = None
    rejection_text: str | None = None


class VacancyArchive(BaseModel):
    result: str  # hired|cancelled|frozen


class VacancyStageCreate(BaseModel):
    """Schema for creating a new stage"""
    stage_key: str = Field(..., max_length=20, pattern=r"^[a-z0-9_]+$")
    label: str = Field(..., max_length=60)
    order_index: int
    is_terminal: bool = False
    description: str | None = None


class VacancyStageUpdate(BaseModel):
    """Schema for updating stage (label и/или описание; stage_key неизменен)"""
    label: str = Field(..., max_length=60)
    description: str | None = None


class VacancyStageReorder(BaseModel):
    """Schema for reordering stages"""
    order: list[str] = Field(..., description="List of stage_keys in new order")


class ParseVacancyResponse(BaseModel):
    """Ответ эндпоинта POST /vacancies/parse-file"""
    parsed: bool
    reason: str | None = None
    fields: dict


class GenerateRubricRequest(BaseModel):
    """Тело запроса POST /vacancies/generate-rubric (stateless, вакансия может быть не создана)"""
    name: str | None = None
    description: str | None = None
    city: str | None = None
    department: str | None = None
    employment_type: str | None = None
    salary_from: int | None = None
    salary_to: int | None = None


class GenerateRubricResponse(BaseModel):
    """Ответ эндпоинта POST /vacancies/generate-rubric"""
    generated: bool
    reason: str | None = None
    rubric: str | None = None