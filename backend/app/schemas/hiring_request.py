"""Pydantic-схемы модуля «Заявки на подбор» (v2)."""
from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .base import ORMBase


# ── Тред уточнений ────────────────────────────────────────────────────────────
class RequestCommentOut(ORMBase):
    id: UUID
    side: str
    author_name: Optional[str] = None
    author_user_id: Optional[UUID] = None
    body: str
    created_at: datetime


class RequestCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


# ── История (события заявки) ──────────────────────────────────────────────────
class RequestHistoryItem(BaseModel):
    label: str
    at: datetime


# ── Прогресс найма из связанной вакансии ─────────────────────────────────────
class RequestVacancyProgress(BaseModel):
    vacancy_id: UUID
    vacancy_name: str
    candidates: int          # всего кандидатов в воронке
    new_count: int           # новых (этапы response/added)
    hired: int               # РЕАЛЬНО нанято (кандидаты на этапе hired)
    positions: int           # сколько нужно нанять


# ── Заявка ────────────────────────────────────────────────────────────────────
class HiringRequestBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    department: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=120)
    positions: int = Field(default=1, ge=1, le=999)
    deadline: Optional[date] = None
    salary_from: Optional[int] = Field(default=None, ge=0)
    salary_to: Optional[int] = Field(default=None, ge=0)
    employment_format: Optional[Literal["office", "hybrid", "remote"]] = None
    priority: Literal["normal", "high"] = "normal"


class HiringRequestCreate(HiringRequestBase):
    # Только для via=manual (рекрутер вносит со слов внешнего заказчика).
    # Для hiring_manager автор проставляется сервером = current_user, эти поля игнорируются.
    author_name: Optional[str] = Field(default=None, max_length=160)
    author_role: Optional[str] = Field(default=None, max_length=160)
    author_contact: Optional[str] = Field(default=None, max_length=200)


class HiringRequestListItem(ORMBase):
    id: UUID
    num: int
    title: str
    department: Optional[str] = None
    city: Optional[str] = None
    positions: int
    deadline: Optional[date] = None
    priority: str
    status: str
    via: str
    author_name: Optional[str] = None
    author_role: Optional[str] = None
    created_at: datetime
    # Прогресс — только у заявок в подборе (иначе None)
    progress: Optional[RequestVacancyProgress] = None


class HiringRequestDetail(HiringRequestListItem):
    description: str
    salary_from: Optional[int] = None
    salary_to: Optional[int] = None
    employment_format: Optional[str] = None
    author_contact: Optional[str] = None
    author_user_id: Optional[UUID] = None
    vacancy_id: Optional[UUID] = None
    vacancy_name: Optional[str] = None
    reject_reason: Optional[str] = None
    closed_note: Optional[str] = None
    comments: list[RequestCommentOut] = []
    history: list[RequestHistoryItem] = []


class HiringRequestListResponse(BaseModel):
    items: list[HiringRequestListItem]
    total: int


class RequestMoveRequest(BaseModel):
    target: str = Field(min_length=1, max_length=40)


class RequestRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class RequestCloseRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=4000)


# ── Сайдбар ───────────────────────────────────────────────────────────────────
class RequestSidebarCounts(BaseModel):
    active: int   # заявки в нетерминальных стадиях
    new: int      # только «Новая»


# ── Воронка заявок (кастомные этапы) ──────────────────────────────────────────
class RequestStageOut(BaseModel):
    key: str
    label: str
    color: str
    system: bool
    terminal: bool
    custom: bool
    description: Optional[str] = None


class RequestStageCreate(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    description: Optional[str] = None


class RequestStageUpdate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=60)
    description: Optional[str] = None


class RequestStageReorder(BaseModel):
    stage_keys: list[str]


# ── Настройки модуля ──────────────────────────────────────────────────────────
class RequestSettingsOut(BaseModel):
    autoclose_on: bool
    question_moves_to_work: bool
    notify_manager_on_stage: bool
    form_enabled: bool


class RequestSettingsUpdate(BaseModel):
    autoclose_on: Optional[bool] = None
    question_moves_to_work: Optional[bool] = None
    notify_manager_on_stage: Optional[bool] = None
    form_enabled: Optional[bool] = None


class RequestFormLinkOut(BaseModel):
    url: Optional[str] = None       # полная ссылка публичной формы (None если не активирована)
    enabled: bool


# ── Публичная форма ───────────────────────────────────────────────────────────
class PublicFormInfo(BaseModel):
    company_name: str
    enabled: bool


class PublicRequestSubmit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    author_name: Optional[str] = Field(default=None, max_length=160)
    author_role: Optional[str] = Field(default=None, max_length=160)
    author_contact: Optional[str] = Field(default=None, max_length=200)
    department: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=120)
    positions: int = Field(default=1, ge=1, le=999)
    deadline: Optional[date] = None
    salary_from: Optional[int] = Field(default=None, ge=0)
    salary_to: Optional[int] = Field(default=None, ge=0)
    employment_format: Optional[Literal["office", "hybrid", "remote"]] = None
    priority: Literal["normal", "high"] = "normal"
    # Honeypot: реальные люди это поле не заполняют; непусто → бот.
    website: Optional[str] = None


class PublicRequestResult(BaseModel):
    ok: bool
    num: Optional[int] = None
