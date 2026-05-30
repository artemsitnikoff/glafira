from pydantic import BaseModel
from datetime import datetime, date
from uuid import UUID
from typing import Literal

from .base import ORMBase


class TagOut(ORMBase):
    id: UUID
    name: str
    color: str | None = None


class CandidateExperienceOut(ORMBase):
    position: str
    company: str | None = None
    period: str | None = None
    description: str | None = None


class CandidateEducationOut(ORMBase):
    institution: str | None = None
    specialty: str | None = None
    years: str | None = None


class CandidateCardVacancy(BaseModel):
    application_id: UUID
    vacancy_id: UUID
    vacancy_name: str
    stage: str
    stage_color: str
    is_last: bool


class CandidateGridItem(ORMBase):
    id: UUID
    display_number: str | None = None
    full_name: str
    age: int | None = None
    last_position: str | None = None
    last_company: str | None = None
    last_period: str | None = None
    ai_score: int | None = None
    avatar_url: str | None = None
    is_duplicate: bool = False
    has_pdn: bool = False
    last_vacancy: CandidateCardVacancy | None = None
    other_vacancies_count: int = 0


class CandidateDetail(ORMBase):
    id: UUID
    display_number: str | None = None
    last_name: str
    first_name: str
    middle_name: str | None = None
    full_name: str
    age: int | None = None
    birth_date: date | None = None
    gender: str | None = None
    city: str | None = None
    region: str | None = None
    phone: str | None = None
    email: str | None = None
    # Обе формы: старые засиженные — список строк-каналов (["telegram",...]);
    # новые из формы добавления — объекты {type, url}. Фронт рендерит обе.
    messengers: list[dict | str] = []
    salary_expectation: int | None = None
    currency: str = "RUB"
    last_position: str | None = None
    last_company: str | None = None
    last_period: str | None = None
    source: str
    preferred_channel: str = "telegram"
    resume_text: str | None = None
    resume_summary: str | None = None
    ai_score: int | None = None
    has_pdn: bool = False
    is_duplicate: bool = False
    duplicate_of: UUID | None = None
    is_anonymized: bool = False
    tags: list[TagOut] = []
    experience: list[CandidateExperienceOut] = []
    education: list[CandidateEducationOut] = []
    skills: list[str] = []
    extra: dict | None = None
    created_at: datetime


class ApplicationHistoryItem(ORMBase):
    application_id: UUID
    vacancy_id: UUID
    vacancy_name: str
    vacancy_status: str
    stage: str
    stage_color: str
    client_name: str | None = None
    recruiter_name: str | None = None
    ai_score: int | None = None
    selected_at: datetime | None = None
    stage_changed_at: datetime | None = None
    reject_reason: str | None = None


class MessengerEntry(BaseModel):
    type: Literal["tg", "wa", "max", "vk", "linkedin"]
    url: str


class CandidateCreate(BaseModel):
    last_name: str
    first_name: str
    middle_name: str | None = None
    source: str
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    city: str | None = None
    salary_expectation: int | None = None
    currency: str = "RUB"
    add_type: str = "manual"
    vacancy_id: UUID | None = None
    comment: str | None = None
    messengers: list[MessengerEntry] | None = None


class CandidateUpdate(BaseModel):
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    city: str | None = None
    region: str | None = None
    salary_expectation: int | None = None
    currency: str | None = None
    last_position: str | None = None
    last_company: str | None = None
    last_period: str | None = None
    preferred_channel: str | None = None
    resume_text: str | None = None
    resume_summary: str | None = None


class AddTagRequest(BaseModel):
    tag_id: UUID


class AssignToVacancyRequest(BaseModel):
    vacancy_id: UUID
    stage: str = "response"