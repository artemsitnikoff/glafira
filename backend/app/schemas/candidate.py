from pydantic import BaseModel, Field
from datetime import datetime, date
from uuid import UUID
from typing import Literal

from .base import ORMBase

# Допустимые значения source — синхронизированы с CHECK-констрейнтом модели
# (app/models/candidate.py). Невалидное значение → 422 от Pydantic, НЕ 500 IntegrityError.
CandidateSource = Literal[
    "hh", "avito", "superjob", "telegram", "referral",
    "direct", "agency", "import", "manual", "linkedin", "potok", "other",
]


class TagOut(ORMBase):
    id: UUID
    name: str
    color: str | None = None


class TagManageOut(ORMBase):
    id: UUID
    name: str
    color: str | None = None
    usage_count: int = 0
    created_at: datetime


class TagCreate(BaseModel):
    name: str
    color: str | None = None


class TagUpdate(BaseModel):
    name: str | None = None
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
    last_tenure: str | None = None  # стаж на последнем месте, напр. «2 года»
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
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str = "RUB"
    last_position: str | None = None
    last_company: str | None = None
    last_period: str | None = None
    last_tenure: str | None = None        # стаж на последнем месте, напр. «2 года 3 мес»
    total_experience: str | None = None   # общий стаж по резюме (сумма), напр. «6 лет 7 мес»
    source: str
    source_url: str | None = Field(default=None, max_length=500)
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
    from_smart_search: bool = False  # резюме найдено через «Умный подбор» (по scored_candidates)
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


# Вложенные схемы для создания кандидата с опытом/навыками/образованием
class ExperienceCreate(BaseModel):
    position: str = Field(min_length=1)
    company: str | None = None
    period: str | None = None
    description: str | None = None


class EducationCreate(BaseModel):
    institution: str | None = None
    specialty: str | None = None
    years: str | None = None


class CandidateCreate(BaseModel):
    last_name: str
    first_name: str
    middle_name: str | None = None
    source: CandidateSource
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    city: str | None = None
    region: str | None = None
    salary_expectation: int | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str = "RUB"
    add_type: str = "manual"
    vacancy_id: UUID | None = None
    comment: str | None = None
    messengers: list[MessengerEntry] | None = None
    source_url: str | None = Field(default=None, max_length=500)
    # Поля для автозаполнения из парсинга
    last_position: str | None = None
    last_company: str | None = None
    last_period: str | None = None
    # Структурированные данные
    experience: list[ExperienceCreate] = []
    skills: list[str] = []
    education: list[EducationCreate] = []


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
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str | None = None
    source: CandidateSource | None = None
    source_url: str | None = Field(default=None, max_length=500)
    last_position: str | None = None
    last_company: str | None = None
    last_period: str | None = None
    preferred_channel: str | None = None
    resume_text: str | None = None
    resume_summary: str | None = None
    # Редактирование мессенджеров из карточки. None — не трогать (сохраняет существующие,
    # в т.ч. несколько); [] — очистить; [{type,url}] — заменить.
    messengers: list[MessengerEntry] | None = None


class AddTagRequest(BaseModel):
    tag_id: UUID


# Схемы для парсинга резюме
class ParseResumeResponse(BaseModel):
    parsed: bool
    reason: str | None = None
    fields: dict | None = None


class AssignToVacancyRequest(BaseModel):
    vacancy_id: UUID
    stage: str = "response"