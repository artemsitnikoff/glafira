from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Literal

from .base import ORMBase

# Роли пользователя компании. hiring_manager — нанимающий менеджер (видит только свои заявки).
UserRole = Literal["admin", "recruiter", "manager", "hiring_manager"]


class UserShort(ORMBase):
    id: UUID
    full_name: str
    position: str | None
    avatar_url: str | None
    role: str


class UserListItem(ORMBase):
    """Extended user info for the users list page"""
    id: UUID
    full_name: str
    email: str
    role: str
    position: str | None
    avatar_url: str | None
    is_active: bool
    source: str
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole
    position: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    position: str | None = None
    is_active: bool | None = None


class UserCreateResult(UserShort):
    """Returned by POST /users — temp_password (once) + emailed (отправлено ли письмо)."""
    temp_password: str
    emailed: bool = False