from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

from .base import ORMBase


class CommentOut(ORMBase):
    id: UUID
    author_name: str
    # У импортированного с hh комментария роли нашего юзера нет → None.
    author_role: str | None = None
    body: str
    mentions: list[UUID] = []
    created_at: datetime
    # 'manual' — наш комментарий, 'hh' — заметка работодателя с hh (read-only).
    source: str = "manual"


class CommentCreate(BaseModel):
    body: str
    application_id: UUID | None = None
