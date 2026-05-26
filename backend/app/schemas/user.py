from pydantic import BaseModel, EmailStr
from uuid import UUID

from .base import ORMBase


class UserShort(ORMBase):
    id: UUID
    full_name: str
    position: str | None
    avatar_url: str | None
    role: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: str
    position: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    position: str | None = None
    is_active: bool | None = None


class UserCreateResult(UserShort):
    """Returned by POST /users — includes one-time temp_password for admin to show."""
    temp_password: str