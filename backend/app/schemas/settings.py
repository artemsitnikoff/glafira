from pydantic import BaseModel, ConfigDict
from typing import Optional
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
    avatar_url: Optional[str]
    role: str


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    timezone: Optional[str] = None
    avatar_url: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str


# Glafira Settings schemas
class GlafiraSettingsOut(ORMBase):
    id: UUID
    company_id: UUID
    tone: str
    use_informal: bool
    emoji_level: str
    auto_reject_below: int
    auto_select_above: int
    days_no_response: int
    stop_words: dict
    default_mode: str
    created_at: datetime
    updated_at: datetime


class GlafiraSettingsUpdate(BaseModel):
    tone: Optional[str] = None
    use_informal: Optional[bool] = None
    emoji_level: Optional[str] = None
    auto_reject_below: Optional[int] = None
    auto_select_above: Optional[int] = None
    days_no_response: Optional[int] = None
    stop_words: Optional[dict] = None
    default_mode: Optional[str] = None


# Reject Reasons schemas
class RejectReasonOut(ORMBase):
    id: UUID
    side: str
    label: str
    order_index: int
    is_active: bool


class RejectReasonCreate(BaseModel):
    side: str
    label: str
    order_index: int = 0


class RejectReasonUpdate(BaseModel):
    label: Optional[str] = None
    order_index: Optional[int] = None
    is_active: Optional[bool] = None


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


# Survey Templates schemas
class SurveyTemplateOut(ORMBase):
    id: UUID
    company_id: UUID
    name: str
    trigger_day: Optional[int]
    interval_days: Optional[int]
    channels: dict
    questions: dict
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class SurveyTemplateCreate(BaseModel):
    name: str
    trigger_day: Optional[int] = None
    interval_days: Optional[int] = None
    channels: dict
    questions: dict
    is_enabled: bool = True


class SurveyTemplateUpdate(BaseModel):
    name: Optional[str] = None
    trigger_day: Optional[int] = None
    interval_days: Optional[int] = None
    channels: Optional[dict] = None
    questions: Optional[dict] = None
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
    plan: str
    users_limit: int
    candidates_limit: int
    billing_until: Optional[datetime]