from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

from .base import ORMBase


class CommentOut(ORMBase):
    id: UUID
    author_name: str
    author_role: str
    body: str
    mentions: list[UUID] = []
    created_at: datetime


class CommentCreate(BaseModel):
    body: str
    application_id: UUID | None = None