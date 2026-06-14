from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime

from .base import ORMBase


# Profile schemas
class ProfileOut(ORMBase):
    id: UUID
    full_name: str
    email: str
    phone: Optional[str]
    position: Optional[str]
    timezone: str
    language: str
    date_format: str
    avatar_url: Optional[str]
    role: str


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    date_format: Optional[str] = None
    avatar_url: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str


# Glafira Settings schemas
class GlafiraSettingsOut(ORMBase):
    id: UUID
    company_id: UUID
    tone: Literal['friendly', 'formal', 'business']
    use_informal: bool
    emoji_level: str
    auto_reject_below: int
    auto_select_above: int
    days_no_response: int
    stop_words: dict
    default_mode: Literal['A', 'B', 'C']
    turnover_source: Literal['none', 'bitrix24']
    default_rejection_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator('stop_words', mode='before')
    @classmethod
    def _normalize_stop_words(cls, v):
        # Историческая рассинхронизация: базовый seed раньше писал [] (list),
        # а поле объявлено dict. Нормализуем любой не-dict (list/None) к {}.
        return v if isinstance(v, dict) else {}


class GlafiraSettingsUpdate(BaseModel):
    tone: Optional[Literal['friendly', 'formal', 'business']] = None
    use_informal: Optional[bool] = None
    emoji_level: Optional[str] = None
    auto_reject_below: Optional[int] = None
    auto_select_above: Optional[int] = None
    days_no_response: Optional[int] = None
    stop_words: Optional[dict] = None
    default_mode: Optional[Literal['A', 'B', 'C']] = None
    turnover_source: Optional[Literal['none', 'bitrix24']] = None
    default_rejection_text: Optional[str] = None


# Reject Reasons schemas
class RejectReasonOut(ORMBase):
    id: UUID
    side: str
    label: str
    order_index: int
    is_active: bool
    is_system: bool = False


class RejectReasonCreate(BaseModel):
    side: str
    label: str
    order_index: int = 0


class RejectReasonUpdate(BaseModel):
    label: Optional[str] = None
    order_index: Optional[int] = None
    is_active: Optional[bool] = None


class RejectReasonReorder(BaseModel):
    side: str = Field(..., description="Side: 'candidate' or 'company'")
    reason_ids: list[UUID] = Field(..., description="List of reason IDs in new order")


# Email Templates schemas
class EmailTemplateOut(ORMBase):
    id: UUID
    company_id: UUID
    name: str
    event_type: str
    subject: str
    body: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class EmailTemplateCreate(BaseModel):
    name: str
    event_type: str
    subject: str
    body: str
    is_enabled: bool = True


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    event_type: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    is_enabled: Optional[bool] = None


# Message Templates schemas
class MessageTemplateOut(ORMBase):
    id: UUID
    company_id: UUID
    name: str
    body: str
    order_index: int
    created_at: datetime
    updated_at: datetime


class MessageTemplateCreate(BaseModel):
    name: str
    body: str
    order_index: int = 0


class MessageTemplateUpdate(BaseModel):
    name: Optional[str] = None
    body: Optional[str] = None
    order_index: Optional[int] = None


# Survey Templates schemas
class SurveyTemplateOut(ORMBase):
    id: UUID
    company_id: UUID
    name: str
    trigger_day: Optional[int]
    interval_days: Optional[int]
    channels: dict
    questions: list | dict  # список вопросов [{id,text,goal,scale,...}] либо dict-вариант
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class SurveyTemplateCreate(BaseModel):
    name: str
    trigger_day: Optional[int] = None
    interval_days: Optional[int] = None
    channels: dict
    questions: list | dict
    is_enabled: bool = True


class SurveyTemplateUpdate(BaseModel):
    name: Optional[str] = None
    trigger_day: Optional[int] = None
    interval_days: Optional[int] = None
    channels: Optional[dict] = None
    questions: Optional[list | dict] = None
    is_enabled: Optional[bool] = None


# Integrations schemas
class IntegrationOut(ORMBase):
    id: UUID
    provider: str
    status: str
    config: dict  # Will be masked in response


class IntegrationUpdate(BaseModel):
    status: Optional[str] = None
    config: Optional[dict] = None


# Billing schemas
class BillingOut(BaseModel):
    plan: str                    # "MVP" — config-заглушка тарифа
    is_demo: bool                # True: реальной оплаты нет (MVP)
    users_limit: int             # config-заглушка
    candidates_limit: int        # config-заглушка
    vacancies_limit: int         # config-заглушка
    current_users: int           # РЕАЛЬНЫЙ count (is_active если есть; иначе все)
    current_candidates: int      # РЕАЛЬНЫЙ count (deleted_at IS NULL)
    current_vacancies: int       # РЕАЛЬНЫЙ count (status='active' AND deleted_at IS NULL)
    billing_until: Optional[datetime]


# Company Default Stage schemas
class CompanyDefaultStageOut(ORMBase):
    stage_key: str
    label: str
    order_index: int
    is_terminal: bool
    color: Optional[str] = None  # Computed from STAGES
    description: Optional[str] = None


class CompanyDefaultStageCreate(BaseModel):
    stage_key: str
    label: str
    order_index: int = 0
    is_terminal: bool = False
    description: Optional[str] = None


class CompanyDefaultStageUpdate(BaseModel):
    label: str
    description: Optional[str] = None


class CompanyDefaultStageReorder(BaseModel):
    order: list[str]  # List of stage_keys in new order


# Funnel Template schemas (настраиваемые пресеты воронок для формы вакансии)
class FunnelTemplateOut(ORMBase):
    id: UUID
    name: str
    order_index: int
    is_default: bool = False  # синтетический флаг (true только у строки «По умолчанию»)


class FunnelTemplateCreate(BaseModel):
    name: str


class FunnelTemplateUpdate(BaseModel):
    name: str


# AI Model schemas
class AiModelOption(BaseModel):
    value: str  # slug модели
    label: str  # человекочитаемое название


class AiModelSettingsOut(BaseModel):
    current: str  # текущая выбранная модель
    options: list[AiModelOption]  # белый список доступных моделей
    has_openrouter_key: bool  # есть ли API-ключ OpenRouter у компании


class AiModelUpdate(BaseModel):
    model: str  # новая модель из белого списка
    openrouter_api_key: str | None = None  # API-ключ OpenRouter (write-only)