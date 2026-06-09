"""Схемы для умного подбора кандидатов через hh.ru"""

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SmartAccessResponse(BaseModel):
    """Ответ на проверку доступа к умному подбору"""
    has_access: bool
    has_paid_access: bool = False
    reason: Optional[str] = None


class SmartVacancyItem(BaseModel):
    """Вакансия с предзаполненными фильтрами для умного подбора"""
    id: UUID
    title: str
    city: Optional[str] = None
    area: Optional[str] = None  # ID региона в hh.ru
    professional_role: Optional[str] = None
    experience: Optional[str] = None
    salary_from: Optional[int] = None
    salary_to: Optional[int] = None
    skills: list[str] = Field(default_factory=list)
    found: Optional[int] = None  # количество найденных резюме
    hh_published: bool = False  # опубликована ли на hh.ru


class SmartSearchRequest(BaseModel):
    """Запрос на запуск умного поиска"""
    vacancy_id: UUID
    area: Optional[str] = None
    professional_role: Optional[str] = None
    experience: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    salary_from: Optional[int] = None
    salary_to: Optional[int] = None
    include_no_salary: bool = True
    scan_n: int = Field(ge=1, le=400)  # количество резюме для сканирования
    invite_m: int = Field(ge=1, le=100)  # количество лучших для приглашения
    threshold: int = Field(ge=0, le=100)  # минимальный балл для приглашения
    confirm_cost: bool = False  # подтверждение расхода для scan_n > 50
    area_id: Optional[str] = None  # ID региона из справочника hh
    period: Optional[int] = None  # дни свежести резюме (1/3/7/30/365)


class SmartSearchResponse(BaseModel):
    """Ответ на запуск умного поиска"""
    run_id: UUID


class SmartRequirementMatch(BaseModel):
    """Соответствие требованию при скоринге в умном подборе"""
    criterion: str  # критерий оценки
    weight: int  # максимальный вес критерия
    points: int  # набранные баллы (≤ weight)
    comment: Optional[str] = None  # комментарий по критерию


class SmartScoredExperience(BaseModel):
    """Опыт работы в компактном резюме"""
    position: Optional[str] = None
    company: Optional[str] = None
    period: Optional[str] = None
    description: Optional[str] = None


class SmartScoredResume(BaseModel):
    """Компактное резюме для отображения"""
    title: Optional[str] = None
    total_experience_months: Optional[int] = None
    city: Optional[str] = None
    age: Optional[int] = None
    salary: Optional[str] = None  # Форматированная строка
    experience: list[SmartScoredExperience] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: Optional[str] = None


class InvitedCandidate(BaseModel):
    """Приглашенный кандидат"""
    candidate_id: Optional[UUID] = None  # None для превью режима
    name: str
    age: Optional[int] = None
    experience_years: Optional[int] = None
    last_company: Optional[str] = None
    city: Optional[str] = None
    score: int
    verdict: str
    passed: Optional[bool] = None  # для переиспользования в scored_candidates
    # Новые поля с полным разбором (необязательные для обратной совместимости)
    summary: Optional[str] = None
    strengths: Optional[list[str]] = None
    risks: Optional[list[str]] = None
    forecast: Optional[str] = None
    requirements_match: Optional[list[SmartRequirementMatch]] = None
    resume: Optional[SmartScoredResume] = None
    # Новые поля для ручного приглашения
    hh_resume_id: Optional[str] = None
    invited: Optional[bool] = None


class SmartRunStatus(BaseModel):
    """Статус выполнения умного поиска"""
    id: UUID
    status: Literal['running', 'done', 'error']
    stage: Literal['search', 'eval', 'finalizing', 'invite', 'done'] = 'search'
    found: int = 0
    scan_n: int = 0  # план скана (для прогресса: оценено из min(scan_n, found))
    scanned: int = 0
    evaluated: int = 0
    invited: int = 0
    error: Optional[str] = None
    invites_skipped: bool = False
    invited_candidates: list[InvitedCandidate] = Field(default_factory=list)
    scored_candidates: list[InvitedCandidate] = Field(default_factory=list)
    passed_threshold: int = 0
    note: Optional[str] = None
    log: list[str] = Field(default_factory=list)


class SmartRunHistoryItem(BaseModel):
    """Элемент истории умного поиска"""
    id: UUID
    vacancy_id: UUID
    vacancy_title: str
    created_at: datetime
    found: int
    evaluated: int
    invited: int


class SmartVacancyFilters(BaseModel):
    """AI-фильтры для умного подбора по вакансии"""
    area: str
    professional_role: str
    experience: str
    skills: list[str]


class SmartCountRequest(BaseModel):
    """Запрос на превью количества резюме"""
    vacancy_id: UUID
    area: Optional[str] = None
    professional_role: Optional[str] = None
    experience: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    salary_from: Optional[int] = None
    salary_to: Optional[int] = None
    include_no_salary: bool = True
    area_id: Optional[str] = None  # ID региона из справочника hh
    period: Optional[int] = None  # дни свежести резюме (1/3/7/30/365)


class SmartAreaSuggestItem(BaseModel):
    """Элемент подсказок регионов"""
    id: str
    text: str


class SmartCountResponse(BaseModel):
    """Ответ с количеством найденных резюме"""
    found: Optional[int] = None


class SmartInviteRequest(BaseModel):
    """Запрос на ручное приглашение выбранных кандидатов"""
    resume_ids: list[str] = Field(description="Список hh_resume_id для приглашения")


class SmartInviteResultItem(BaseModel):
    """Результат приглашения одного кандидата"""
    resume_id: str
    status: Literal['invited', 'already', 'error']
    message: Optional[str] = None
    candidate_id: Optional[UUID] = None
    name: Optional[str] = None


class SmartInviteResponse(BaseModel):
    """Ответ на ручное приглашение кандидатов"""
    results: list[SmartInviteResultItem]
    invited_count: int