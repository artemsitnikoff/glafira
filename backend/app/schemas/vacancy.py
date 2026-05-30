from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from uuid import UUID

from .base import ORMBase
from .user import UserShort


class StageInput(BaseModel):
    """Schema for custom stage input when creating vacancy"""
    stage_key: str = Field(..., max_length=20)
    label: str = Field(..., max_length=60)
    order_index: int
    is_terminal: bool = False


class VacancySidebarItem(ORMBase):
    id: UUID
    name: str
    count: int
    new_count: int


class VacancySidebar(BaseModel):
    items: list[VacancySidebarItem]
    archived_count: int


class VacancyStageCount(BaseModel):
    stage_key: str
    label: str
    color: str
    count: int
    is_terminal: bool


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
    status: str
    glafira_mode: str
    responsible_user_id: UUID | None = None
    responsible_user: UserShort | None = None
    team: list[UserShort] = Field(default_factory=list)
    external_source: str | None = None
    external_url: str | None = None
    archive_result: str | None = None
    closed_at: date | None = None
    created_at: datetime


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
    funnel_template: str = "default"
    glafira_mode: str = "A"
    team: list[UUID] = []
    auto_move: bool = False
    auto_move_threshold: int | None = None
    auto_qa_from: str | None = None
    auto_qa_to: str | None = None
    auto_reject: bool = False
    stages: list[StageInput] | None = None

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
    status: str | None = None
    glafira_mode: str | None = None
    team: list[UUID] | None = None
    auto_move: bool | None = None
    auto_move_threshold: int | None = None
    auto_qa_from: str | None = None
    auto_qa_to: str | None = None
    auto_reject: bool | None = None


class VacancyArchive(BaseModel):
    result: str  # hired|cancelled|frozen