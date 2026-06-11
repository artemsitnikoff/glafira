"""Схемы для поиска по собственной базе кандидатов"""

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, model_validator


class BaseSearchRequest(BaseModel):
    """Запрос поиска по собственной базе"""
    search_type: Literal["prompt", "vacancy"]
    query: Optional[str] = Field(None, min_length=3, description="Текст запроса (для типа 'prompt')")
    vacancy_id: Optional[UUID] = Field(None, description="ID вакансии (для типа 'vacancy')")
    # Критерии для типа 'vacancy' — переданы фронтом (автофильтры из вакансии, уже
    # отредактированные рекрутёром). Если не присланы — бек сам derive'ит из вакансии.
    role: Optional[str] = Field(None, description="Должность/роль (vacancy)")
    skills: Optional[list[str]] = Field(None, description="Навыки (vacancy)")
    city: Optional[str] = Field(None, description="Город (vacancy)")
    salary_from: Optional[int] = Field(None, description="ЗП от (vacancy)")
    salary_to: Optional[int] = Field(None, description="ЗП до (vacancy)")

    @model_validator(mode='after')
    def validate_fields(self):
        if self.search_type == 'prompt' and not self.query:
            raise ValueError("Для типа 'prompt' обязательно поле 'query'")
        if self.search_type == 'vacancy' and not self.vacancy_id:
            raise ValueError("Для типа 'vacancy' обязательно поле 'vacancy_id'")
        return self


class BaseSearchCriteria(BaseModel):
    """Критерии поиска"""
    role: str
    skills: list[str]
    city: str
    salary_from: Optional[int]
    salary_to: Optional[int]


class BaseSearchCandidate(BaseModel):
    """Кандидат в результатах поиска"""
    id: UUID
    full_name: str
    age: Optional[int]
    last_position: Optional[str]
    last_company: Optional[str]
    last_period: Optional[str]  # last_tenure
    city: Optional[str]
    ai_score: Optional[int]
    source: str
    salary_expectation: Optional[int]
    matched_skills: list[str]
    all_skills: list[str]
    match_percent: Optional[int]
    has_pdn: bool
    scored_by: str = 'cosine'

    model_config = ConfigDict(from_attributes=True)


class BaseSearchResponse(BaseModel):
    """Ответ поиска по базе (теперь возвращает только run_id)"""
    run_id: UUID


class BaseSearchRetrieveResponse(BaseModel):
    """Ответ фазы RETRIEVE (лёгкой): прогон создан, фронт спрашивает N для AI-оценки.
    total — размер базы, доступной для семантического поиска (проиндексированные резюме)."""
    run_id: UUID
    total: int


class BaseEvaluateRequest(BaseModel):
    """Запрос фазы EVALUATE (асинхронной)"""
    evaluate_n: int = Field(..., ge=1)


class BaseSearchRunResponse(BaseModel):
    """История поиска"""
    id: UUID
    search_type: str
    query_text: str
    vacancy_id: Optional[UUID]
    found: int
    added_to_funnel: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BaseSearchCountResponse(BaseModel):
    """Количество кандидатов в базе"""
    count: int


class BaseSearchRunStatus(BaseModel):
    """Статус выполнения поиска по базе"""
    id: UUID
    status: str  # 'running', 'done', 'error'
    stage: Optional[str] = None  # 'retrieve', 'rerank', 'done'
    found: int
    to_evaluate: int
    evaluated: int
    results: list[BaseSearchCandidate]
    criteria: Optional[BaseSearchCriteria] = None
    query_echo: Optional[str] = None
    vacancy_title: Optional[str] = None
    error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MarkAddedRequest(BaseModel):
    """Запрос отметки добавления в воронку"""
    pass  # Пустой body