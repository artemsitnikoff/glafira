from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

from .base import ORMBase


class ConsentOut(ORMBase):
    id: UUID
    candidate_id: UUID
    number: str
    status: str
    channel: str | None = None
    signed_at: datetime | None = None
    requested_at: datetime | None = None


class ConsentRequest(BaseModel):
    channel: str = "telegram"