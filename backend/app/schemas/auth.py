from pydantic import BaseModel, EmailStr
from uuid import UUID

from .base import ORMBase


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMe(ORMBase):
    id: UUID
    email: str
    full_name: str
    role: str
    position: str | None
    avatar_url: str | None
    timezone: str