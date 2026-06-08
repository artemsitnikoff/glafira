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


class SmartSearchResponse(BaseModel):
    """Ответ на запуск умного поиска"""
    run_id: UUID


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


class SmartRunStatus(BaseModel):
    """Статус выполнения умного поиска"""
    id: UUID
    status: Literal['running', 'done', 'error']
    stage: Literal['search', 'eval', 'invite', 'done'] = 'search'
    found: int = 0
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


class SmartCountResponse(BaseModel):
    """Ответ с количеством найденных резюме"""
    found: Optional[int] = None